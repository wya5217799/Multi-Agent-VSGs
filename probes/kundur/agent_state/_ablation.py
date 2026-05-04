"""Phase A2 — per-agent counterfactual ablation.

Question: which agents are pulling weight, which are freeriders?

Method: rollout DDIC on N_EVAL fixed-test eps as baseline. Then for each
agent_i, replace its action with zero (= no control), rerun same eps. Compute
cum_rf_global delta = baseline - ablated. Larger positive delta = agent
contributing more.

Outputs:
- baseline_cum_rf
- per_agent_ablation: list of {agent, ablated_cum_rf, delta, share}
- verdict-relevant: any freerider (share < threshold)?
"""
from __future__ import annotations

import numpy as np

from probes.kundur.agent_state._loader import LoadedPolicy
from probes.kundur.agent_state.probe_config import ProbeThresholds


def _get_andes_env():
    from env.andes.andes_vsg_env import AndesMultiVSGEnv
    return AndesMultiVSGEnv

# Fixed test seeds — same convention as _phase3_eval_v2.py
FIXED_TEST_SEEDS = [20000 + i for i in range(50)]


def _make_env(backend: str, seed: int, comm_fail_prob: float | None = None):
    """Construct env for given backend + seed. Returns (env, obs, steps_per_episode).

    Parameters
    ----------
    comm_fail_prob : float | None
        Communication failure probability for ANDES backend.
        None (default) defers to AndesMultiVSGEnv.COMM_FAIL_PROB (= 0.1, matching training).
    """
    if backend == "simulink":
        from env.simulink.kundur_simulink_env import KundurSimulinkEnv
        from scenarios.kundur.config_simulink import STEPS_PER_EPISODE
        env = KundurSimulinkEnv(training=False)
        obs, _ = env.reset(seed=seed)
        steps = STEPS_PER_EPISODE
    else:
        AndesMultiVSGEnv = _get_andes_env()
        env = AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=comm_fail_prob)
        env.seed(seed)
        obs = env.reset()
        steps = AndesMultiVSGEnv.STEPS_PER_EPISODE
    return env, obs, steps


def _make_actions(policy: LoadedPolicy, obs, N: int, mask_agent: int | None) -> tuple:
    """Return (andes_dict, simulink_array) actions for current obs."""
    andes_actions = {}
    arr = np.zeros((N, 2), dtype=np.float32)
    for i in range(N):
        if i == mask_agent:
            act = np.zeros(2, dtype=np.float32)
        else:
            act = policy.agents[i].select_action(obs[i], deterministic=True)
        andes_actions[i] = act
        arr[i] = act
    return andes_actions, arr


def _rollout_with_mask(policy: LoadedPolicy, env_seeds: list[int],
                       mask_agent: int | None = None,
                       comm_fail_prob: float | None = None) -> dict:
    """Run rollout. If mask_agent is set, that agent outputs zero action.

    Handles ANDES (4-tuple step, dict action) and Simulink (5-tuple step, array action).
    """
    N = policy.n_agents
    backend = getattr(policy, "backend", "andes")
    cum = 0.0
    per_ep = []
    for seed in env_seeds:
        env, obs, steps = _make_env(backend, seed, comm_fail_prob=comm_fail_prob)
        ep_cum = 0.0
        for _step in range(steps):
            andes_actions, sim_actions = _make_actions(policy, obs, N, mask_agent)
            if backend == "simulink":
                obs, _, term, trunc, info = env.step(sim_actions)
                done = term or trunc
            else:
                obs, _, done, info = env.step(andes_actions)
            f = info["freq_hz"]
            f_bar = float(np.mean(f))
            ep_cum -= float(np.sum((f - f_bar) ** 2))
            if done:
                break
        cum += ep_cum
        per_ep.append({"seed": seed, "cum_rf": ep_cum})
        if backend == "simulink":
            try:
                env.close()
            except Exception:
                pass
    return {"cum_rf_total": cum, "per_ep": per_ep, "n_eps": len(env_seeds)}


def run(policy: LoadedPolicy, thresholds: ProbeThresholds,
        comm_fail_prob: float | None = None) -> dict:
    """Phase A2 entry. Returns snapshot section.

    Parameters
    ----------
    comm_fail_prob : float | None
        Passed through to _rollout_with_mask → _make_env. None defers to env default (0.1).
    """
    eval_seeds = FIXED_TEST_SEEDS[: thresholds.a2_n_eval_eps]
    N = policy.n_agents

    # Baseline (all agents active)
    baseline = _rollout_with_mask(policy, eval_seeds, mask_agent=None,
                                  comm_fail_prob=comm_fail_prob)
    baseline_cum = baseline["cum_rf_total"]

    # Ablation per agent
    per_agent = []
    for ai in range(N):
        ablated = _rollout_with_mask(policy, eval_seeds, mask_agent=ai,
                                     comm_fail_prob=comm_fail_prob)
        # delta_cum = baseline - ablated; if positive, agent was helping (worsening when removed)
        # cum_rf is negative; "less negative" = better. If ablated > baseline (more negative),
        # then agent was helping. delta = baseline - ablated should be POSITIVE for contributing
        # agents. Wait — sign:
        #   baseline_cum = -1.1 (better, less negative)
        #   ablated_cum  = -1.5 (worse when agent removed)
        #   delta = baseline - ablated = -1.1 - (-1.5) = +0.4  → POSITIVE = contributing
        delta = baseline_cum - ablated["cum_rf_total"]
        per_agent.append({
            "agent": ai,
            "ablated_cum_rf": ablated["cum_rf_total"],
            "delta_cum_rf": delta,  # >0 means agent contributes
        })

    # Share normalization: |delta_i| / sum(|delta|)
    total_abs = sum(abs(r["delta_cum_rf"]) for r in per_agent)
    for r in per_agent:
        r["share"] = float(abs(r["delta_cum_rf"]) / total_abs) if total_abs > 1e-12 else 0.0

    return {
        "n_eval_eps": len(eval_seeds),
        "baseline_cum_rf": baseline_cum,
        "per_agent_ablation": per_agent,
        "comm_fail_prob_used": comm_fail_prob,
    }
