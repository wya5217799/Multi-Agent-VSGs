"""Phase A3 — failure forensics.

Question: where does max_df_max excursion come from?

Method: rollout 50 fixed-test eps, log per-step state + disturbance metadata.
Sort by max_df_max desc, inspect worst-K. Look for clustering in:
- disturbance bus (which load got stepped?)
- disturbance magnitude / sign
- response timing (did agent act at all? when?)

Outputs:
- worst_k_episodes: list of {seed, max_df, dist_bus, dist_magnitude, action_total_norm, ...}
- pattern flags: clustered_by_bus, clustered_by_magnitude, etc.
"""
from __future__ import annotations

from collections import Counter

import numpy as np

from probes.kundur.agent_state._loader import LoadedPolicy
from probes.kundur.agent_state.probe_config import ProbeThresholds


def _get_andes_env():
    from env.andes.andes_vsg_env import AndesMultiVSGEnv
    return AndesMultiVSGEnv


def _rollout_with_trace(policy: LoadedPolicy, seed: int,
                        comm_fail_prob: float | None = None) -> dict:
    """One rollout, capturing per-step state + disturbance metadata.

    Handles ANDES (4-tuple step, dict action, env.ss.PQ.* introspection) and
    Simulink (5-tuple step, array action, info-key disturbance metadata).

    Simulink note: raw_signals["d_omega_global_spread"] is always 0.0 — spread_peak
    analysis is blind. spread_peak_step/spread_peak_value are set to NaN for Simulink.

    Parameters
    ----------
    comm_fail_prob : float | None
        Communication failure probability for ANDES backend.
        None (default) defers to AndesMultiVSGEnv.COMM_FAIL_PROB (= 0.1, matching training).
    """
    backend = getattr(policy, "backend", "andes")

    if backend == "simulink":
        from env.simulink.kundur_simulink_env import KundurSimulinkEnv
        from scenarios.kundur.config_simulink import STEPS_PER_EPISODE
        env = KundurSimulinkEnv(training=False)
        obs, info_reset = env.reset(seed=seed)
        steps = STEPS_PER_EPISODE
        # Disturbance metadata: read from step info (not available at reset; populated on first step)
        dist_bus = "n/a"
        dist_magnitude = float("nan")
    else:
        AndesMultiVSGEnv = _get_andes_env()
        env = AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=comm_fail_prob)
        env.seed(seed)
        obs = env.reset()
        steps = AndesMultiVSGEnv.STEPS_PER_EPISODE
        # Discover applied disturbance from PQ.Ppf change vs p0
        pq_idx_list = list(env.ss.PQ.idx.v) if hasattr(env.ss, "PQ") else []
        if pq_idx_list:
            p0 = env.ss.PQ.p0.v.copy()
            ppf = env.ss.PQ.Ppf.v.copy()
            delta = ppf - p0
            pq_pos = int(np.argmax(np.abs(delta)))
            dist_bus = pq_idx_list[pq_pos] if pq_pos < len(pq_idx_list) else "unknown"
            dist_magnitude = float(delta[pq_pos])
        else:
            dist_bus = "n/a"
            dist_magnitude = 0.0

    N = policy.n_agents
    max_df = 0.0
    cum_rf = 0.0
    per_step_action_l1 = []
    spread_trace = []
    for _step in range(steps):
        if backend == "simulink":
            action_arr = np.array(
                [policy.agents[i].select_action(obs[i], deterministic=True) for i in range(N)],
                dtype=np.float32,
            )
            per_step_action_l1.append(float(np.mean(np.abs(action_arr).sum(axis=1))))
            obs, _, term, trunc, info = env.step(action_arr)
            done = term or trunc
            # Disturbance info available from step info (first step has it)
            if _step == 0:
                dist_bus = str(info.get("resolved_disturbance_type", "n/a"))
                raw_mag = info.get("episode_magnitude_sys_pu", float("nan"))
                dist_magnitude = float(raw_mag) if raw_mag is not None else float("nan")
        else:
            actions = {i: policy.agents[i].select_action(obs[i], deterministic=True) for i in range(N)}
            per_step_action_l1.append(float(np.mean([np.abs(actions[i]).sum() for i in range(N)])))
            obs, _, done, info = env.step(actions)

        f = info["freq_hz"]
        f_bar = float(np.mean(f))
        cum_rf -= float(np.sum((f - f_bar) ** 2))
        max_df = max(max_df, info["max_freq_deviation_hz"])
        raw = info.get("raw_signals", {})
        spread_trace.append(raw.get("d_omega_global_spread", 0.0))
        if done:
            break

    if backend == "simulink":
        try:
            env.close()
        except Exception:
            pass

    # Spread-peak analysis (blind for Simulink — raw_signals always empty)
    if backend == "simulink":
        peak_step = float("nan")
        peak_value = float("nan")
    else:
        spread_arr = np.asarray(spread_trace) if spread_trace else np.zeros(1)
        peak_step = int(np.argmax(spread_arr))
        peak_value = float(spread_arr.max())

    dist_sign = (
        int(np.sign(dist_magnitude))
        if not (isinstance(dist_magnitude, float) and np.isnan(dist_magnitude))
        else 0
    )

    return {
        "seed": seed,
        "max_df_hz": max_df,
        "cum_rf": cum_rf,
        "dist_bus": str(dist_bus),
        "dist_magnitude_pu": dist_magnitude,
        "dist_sign": dist_sign,
        "spread_peak_step": peak_step,
        "spread_peak_value": peak_value,
        "action_l1_mean": float(np.mean(per_step_action_l1)) if per_step_action_l1 else 0.0,
        "action_l1_max": float(np.max(per_step_action_l1)) if per_step_action_l1 else 0.0,
    }


def run(policy: LoadedPolicy, thresholds: ProbeThresholds,
        comm_fail_prob: float | None = None) -> dict:
    """Phase A3 entry.

    Parameters
    ----------
    comm_fail_prob : float | None
        Passed through to _rollout_with_trace. None defers to env default (0.1).
    """
    from probes.kundur.agent_state._ablation import FIXED_TEST_SEEDS
    seeds = FIXED_TEST_SEEDS[: thresholds.a3_n_total_eps]

    eps = []
    for seed in seeds:
        try:
            eps.append(_rollout_with_trace(policy, seed, comm_fail_prob=comm_fail_prob))
        except Exception as e:
            eps.append({"seed": seed, "error": str(e)})

    valid = [e for e in eps if "error" not in e]
    valid_sorted = sorted(valid, key=lambda e: -e["max_df_hz"])  # worst (highest) first
    worst_k = valid_sorted[: thresholds.a3_worst_k]

    # Pattern detection on worst-K
    bus_counts = Counter(e["dist_bus"] for e in worst_k)
    sign_counts = Counter(e["dist_sign"] for e in worst_k)
    mag_p50 = float(np.median([abs(e["dist_magnitude_pu"]) for e in worst_k])) if worst_k else 0.0
    mag_overall_p50 = float(np.median([abs(e["dist_magnitude_pu"]) for e in valid])) if valid else 0.0
    most_common_bus, most_common_bus_count = bus_counts.most_common(1)[0] if bus_counts else ("n/a", 0)

    # Number of episodes exceeding threshold
    over_threshold = sum(1 for e in valid if e["max_df_hz"] > thresholds.a3_max_df_threshold_hz)

    return {
        "n_episodes": len(valid),
        "n_errors": len(eps) - len(valid),
        "worst_k": worst_k,
        "max_df_overall_p50": float(np.median([e["max_df_hz"] for e in valid])) if valid else 0.0,
        "max_df_overall_p95": float(np.percentile([e["max_df_hz"] for e in valid], 95)) if valid else 0.0,
        "max_df_overall_max": float(np.max([e["max_df_hz"] for e in valid])) if valid else 0.0,
        "n_over_threshold": over_threshold,
        "threshold_hz": thresholds.a3_max_df_threshold_hz,
        "worstk_bus_distribution": dict(bus_counts),
        "worstk_sign_distribution": {str(k): v for k, v in sign_counts.items()},
        "worstk_most_common_bus": most_common_bus,
        "worstk_most_common_bus_count": most_common_bus_count,
        "worstk_magnitude_median_pu": mag_p50,
        "overall_magnitude_median_pu": mag_overall_p50,
        # cluster signal: if K worst all share same bus or sign
        "clustered_by_bus": most_common_bus_count >= max(3, thresholds.a3_worst_k - 1),
        "clustered_by_sign": (sign_counts.most_common(1)[0][1] >= thresholds.a3_worst_k - 1) if sign_counts else False,
        "comm_fail_prob_used": comm_fail_prob,
    }
