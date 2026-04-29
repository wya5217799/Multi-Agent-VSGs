"""Phase 5.1 — paper-style evaluator for kundur_cvs_v3 checkpoints.

Implements the paper §IV-C cumulative-reward formula:

    r_f_global = - Σ_t Σ_i (Δf_i,t - mean_j Δf_j,t)²

over per-scenario per-step per-agent frequency deviations, with three
normalization variants per roadmap §3.4 (unnormalized / ÷M / ÷M·N).

Per-episode physics metrics: ROCOF, nadir, peak, settling time, max |Δf|.

Schema: see roadmap §5.1.1. CLI: `python -m evaluation.paper_eval ...`.

Hard boundaries (§0 of the Phase 4 / 5 roadmap):
- No env / bridge / helper / build / .slx / IC / runtime.mat / reward edits.
- No NE39, no training, no checkpoint mutation.

This module READS a checkpoint and READS env state; nothing else.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Paper baselines (roadmap §3.4 table; paper Sec.IV-C)
# ---------------------------------------------------------------------------

PAPER_DDIC_UNNORMALIZED = -8.04
PAPER_NO_CONTROL_UNNORMALIZED = -15.20

# Settling tolerance (paper does not specify; project default 0.01 % × f_n = 5 mHz)
SETTLE_TOL_HZ = 0.005
SETTLE_WINDOW_S = 1.0


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PerEpisodeMetrics:
    scenario_idx: int
    proxy_bus: int  # 7 or 9
    magnitude_sys_pu: float
    n_steps: int
    max_freq_dev_hz: float
    rocof_max_hz_per_s: float
    nadir_hz: float
    peak_hz: float
    settling_time_s: Optional[float]  # None if never settled
    r_f_global_unnormalized: float
    r_f_local_total: float
    r_h_total: float
    r_d_total: float
    total_reward: float
    nan_inf_seen: bool
    tds_failed: bool


@dataclass
class EvalResult:
    schema_version: int
    checkpoint_path: str
    policy_label: str  # 'best.pt' / 'zero_action_no_control' / etc.
    n_scenarios: int
    seed_base: int
    cumulative_reward_global_rf: dict
    per_episode_metrics: list[PerEpisodeMetrics]
    summary: dict
    figures: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Scenario generator (Phase 4.3 placeholder — deterministic per seed)
# ---------------------------------------------------------------------------


def generate_scenarios(
    n_scenarios: int,
    seed_base: int,
    dist_min: float,
    dist_max: float,
    bus_choices: tuple[int, ...] = (7, 9),
) -> list[dict]:
    """Reproducibly generate (bus, magnitude, sign) triples for evaluation.

    Phase 4.3 will replace this with a JSON manifest; until then, this is
    deterministic given (seed_base, n_scenarios) and produces a
    Phase-4.3-compatible record shape.
    """
    rng = np.random.default_rng(seed_base)
    scenarios = []
    for k in range(n_scenarios):
        bus = int(rng.choice(list(bus_choices)))
        # Sign: 50/50 increase / decrease.
        sign = +1.0 if rng.random() < 0.5 else -1.0
        magnitude = float(rng.uniform(dist_min, dist_max)) * sign
        scenarios.append({
            "scenario_idx": k,
            "bus": bus,
            "magnitude_sys_pu": magnitude,
        })
    return scenarios


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------


def _compute_global_rf_unnorm(
    omega_trace: np.ndarray,  # shape (T, N_agents)
    f_nom: float,
) -> float:
    """- Σ_t Σ_i (Δf_i,t - mean_j Δf_j,t)²  (paper §IV-C)."""
    if omega_trace.size == 0:
        return 0.0
    delta_f = (omega_trace - 1.0) * f_nom  # (T, N)
    mean_t = delta_f.mean(axis=1, keepdims=True)  # (T, 1)
    centered = delta_f - mean_t  # (T, N)
    return float(-(centered ** 2).sum())


def _rocof_max(omega_trace: np.ndarray, dt_s: float, f_nom: float) -> float:
    """max |dω/dt| · f_n — peak rate of change of frequency."""
    if omega_trace.shape[0] < 2:
        return 0.0
    dω = np.diff(omega_trace, axis=0)  # (T-1, N)
    rocof_per_agent = np.abs(dω) / dt_s * f_nom
    return float(rocof_per_agent.max())


def _settling_time_s(
    omega_trace: np.ndarray,
    dt_s: float,
    f_nom: float,
    tol_hz: float,
    window_s: float,
) -> Optional[float]:
    """First t (sec) such that all subsequent steps within `window_s` have
    |Δf| < tol_hz across all agents. Returns None if never settled.
    """
    if omega_trace.shape[0] == 0:
        return None
    delta_f = np.abs((omega_trace - 1.0) * f_nom)  # (T, N)
    settled = (delta_f.max(axis=1) < tol_hz)  # (T,)
    window_steps = max(int(round(window_s / dt_s)), 1)
    T = omega_trace.shape[0]
    for t0 in range(T):
        if t0 + window_steps > T:
            break
        if bool(settled[t0:t0 + window_steps].all()):
            return float(t0 * dt_s)
    return None


def _is_finite_arr(x: np.ndarray) -> bool:
    return bool(np.all(np.isfinite(x)))


# ---------------------------------------------------------------------------
# Evaluator core
# ---------------------------------------------------------------------------


def evaluate_policy(
    env,
    n_scenarios: int,
    seed_base: int,
    policy_label: str,
    checkpoint_path: Optional[str],
    select_action_fn,  # callable(obs) -> action array shape (N, ACT)
    fnom: float,
    dt_s: float,
    dist_min: float,
    dist_max: float,
    bus_choices: tuple[int, ...] = (7, 9),
    scenarios_override: Optional[list[dict]] = None,
) -> EvalResult:
    """Run `n_scenarios` deterministic episodes; collect per-ep + cumulative metrics.

    If `scenarios_override` is provided, it is used as the scenario list directly
    (G3 / Phase 4.3: load from JSON manifest instead of inline generator).
    Each entry must have keys {scenario_idx, bus, magnitude_sys_pu}; bus ∈
    {7, 9, 1, 2, 3} per the disturbance dispatch translation.
    """
    if scenarios_override is not None:
        scenarios = scenarios_override
        n_scenarios = len(scenarios)
    else:
        scenarios = generate_scenarios(
            n_scenarios, seed_base, dist_min, dist_max, bus_choices=bus_choices
        )

    # Post-review H3 (2026-04-29): validate bus values at manifest load
    # rather than inside the per-episode loop. Catches manifests that
    # reference bus 14 / 15 (LoadStep paper buses) on the non-LoadStep
    # dispatch path, which would otherwise raise mid-loop after partial
    # work, aborting the eval. Buses 7/9 are ESS-side proxies; 1/2/3 are
    # SG-side proxies — exhaustive set per `scenario_to_disturbance_type`.
    _allowed_buses = {7, 9, 1, 2, 3}
    _preferred_type = os.environ.get("KUNDUR_DISTURBANCE_TYPE", "")
    if not _preferred_type.startswith("loadstep_paper_"):
        _bad = [
            (s.get("scenario_idx"), s.get("bus")) for s in scenarios
            if s.get("bus") not in _allowed_buses
        ]
        if _bad:
            raise ValueError(
                f"paper_eval: scenarios contain bus values outside "
                f"{sorted(_allowed_buses)} on the non-LoadStep dispatch "
                f"path; offending (scenario_idx, bus) pairs: {_bad}. "
                f"Either set KUNDUR_DISTURBANCE_TYPE=loadstep_paper_* "
                f"to use the network-side LoadStep dispatch (where bus "
                f"is informational), or filter the manifest."
            )

    per_ep: list[PerEpisodeMetrics] = []
    sum_global_unnorm = 0.0
    sum_total_steps = 0
    n_agents = int(env.N_ESS)
    steps_per_ep_expected = int(round(env.T_EPISODE / env.DT))

    for sc in scenarios:
        sc_idx = sc["scenario_idx"]
        bus = sc["bus"]
        mag = sc["magnitude_sys_pu"]

        # Per-episode disturbance dispatch (C4, 2026-04-29).
        #
        # Two paths, mirroring the legacy semantics:
        #
        # 1. Operator exported KUNDUR_DISTURBANCE_TYPE=loadstep_paper_* →
        #    paper-faithful LoadStep dispatch. The env-var-set
        #    _disturbance_type is preserved at env construction; we
        #    push only magnitude here. The scenario `bus` field becomes
        #    informational under loadstep_paper_random_bus (env randomises
        #    LS1/LS2 internally per call).
        #
        # 2. Default: ESS-side / SG-side Pm-step proxy — build a typed
        #    Scenario from the manifest's bus/magnitude and let the env
        #    resolve the disturbance_type via
        #    scenario_to_disturbance_type.
        #
        # Both paths use options['trigger_at_step']=0 so the trigger
        # fires before step 0's bridge.sim() advance — byte-equivalent
        # to the legacy paper_eval pattern that called apply_disturbance
        # right after reset and before the step loop.
        from scenarios.kundur.scenario_loader import Scenario as _KdScenario
        preferred_type = os.environ.get("KUNDUR_DISTURBANCE_TYPE", "")
        if preferred_type.startswith("loadstep_paper_"):
            obs, _info0 = env.reset(
                seed=seed_base + 1009 * sc_idx,
                options={
                    "disturbance_magnitude": mag,
                    "trigger_at_step": 0,
                },
            )
        else:
            if bus == 7:
                _kind, _target = "bus", 7
            elif bus == 9:
                _kind, _target = "bus", 9
            elif bus in (1, 2, 3):
                _kind, _target = "gen", int(bus)
            else:
                raise ValueError(f"Unsupported bus/gen index {bus}")
            _scenario = _KdScenario(
                scenario_idx=int(sc_idx),
                disturbance_kind=_kind,
                target=_target,
                magnitude_sys_pu=float(mag),
            )
            obs, _info0 = env.reset(
                seed=seed_base + 1009 * sc_idx,
                scenario=_scenario,
                options={"trigger_at_step": 0},
            )

        omega_steps: list[list[float]] = []
        rew_local_rf = 0.0
        rew_local_rh = 0.0
        rew_local_rd = 0.0
        rew_total = 0.0
        nan_inf = False
        tds_failed = False

        for t in range(steps_per_ep_expected):
            action = select_action_fn(obs)
            obs, reward, terminated, truncated, info = env.step(action)
            ω = np.asarray(info["omega"], dtype=np.float64)
            if not _is_finite_arr(ω):
                nan_inf = True
            omega_steps.append(ω.tolist())
            rew_total += float(np.asarray(reward).mean())
            comp = info.get("reward_components") or {}
            rew_local_rf += float(comp.get("r_f", 0.0))
            rew_local_rh += float(comp.get("r_h", 0.0))
            rew_local_rd += float(comp.get("r_d", 0.0))
            if info.get("tds_failed", False):
                tds_failed = True
            if terminated or truncated:
                break

        omega_trace = np.asarray(omega_steps, dtype=np.float64)
        n_steps = omega_trace.shape[0]
        sum_total_steps += n_steps

        if n_steps > 0:
            r_f_global = _compute_global_rf_unnorm(omega_trace, fnom)
            sum_global_unnorm += r_f_global
            delta_f_abs = np.abs((omega_trace - 1.0) * fnom)
            max_dev = float(delta_f_abs.max()) if delta_f_abs.size else 0.0
            mean_omega_per_step = omega_trace.mean(axis=1)  # (T,)
            nadir_hz = float((mean_omega_per_step.min() - 1.0) * fnom)
            peak_hz = float((mean_omega_per_step.max() - 1.0) * fnom)
            rocof = _rocof_max(omega_trace, dt_s, fnom)
            sett = _settling_time_s(
                omega_trace, dt_s, fnom, SETTLE_TOL_HZ, SETTLE_WINDOW_S
            )
        else:
            r_f_global = 0.0
            max_dev = 0.0
            nadir_hz = 0.0
            peak_hz = 0.0
            rocof = 0.0
            sett = None

        per_ep.append(PerEpisodeMetrics(
            scenario_idx=sc_idx,
            proxy_bus=bus,
            magnitude_sys_pu=float(mag),
            n_steps=int(n_steps),
            max_freq_dev_hz=max_dev,
            rocof_max_hz_per_s=rocof,
            nadir_hz=nadir_hz,
            peak_hz=peak_hz,
            settling_time_s=sett,
            r_f_global_unnormalized=r_f_global,
            r_f_local_total=rew_local_rf,
            r_h_total=rew_local_rh,
            r_d_total=rew_local_rd,
            total_reward=rew_total,
            nan_inf_seen=nan_inf,
            tds_failed=tds_failed,
        ))
        print(
            f"  scenario {sc_idx:3d}  bus={bus}  mag={mag:+.3f}  "
            f"max|Δf|={max_dev:.4f} Hz  ROCOF={rocof:.3f} Hz/s  "
            f"r_f_global={r_f_global:+.5f}  total_reward={rew_total:+.4f}"
        )

    # Cumulative + normalizations
    M = steps_per_ep_expected  # = 50
    N = n_agents               # = 4
    cum_unnorm = sum_global_unnorm
    cum_per_M = cum_unnorm / M if M > 0 else 0.0
    cum_per_M_per_N = cum_unnorm / (M * N) if (M * N) > 0 else 0.0

    # Summary
    max_devs = [p.max_freq_dev_hz for p in per_ep]
    rocofs = [p.rocof_max_hz_per_s for p in per_ep]
    settles = [p.settling_time_s for p in per_ep if p.settling_time_s is not None]
    settled_pct = (len(settles) / max(len(per_ep), 1)) * 100.0
    rh_pcts = []
    for p in per_ep:
        denom = abs(p.r_f_local_total) + abs(p.r_h_total) + abs(p.r_d_total)
        if denom > 0:
            rh_pcts.append(abs(p.r_h_total) / denom * 100.0)
    rh_share_mean = sum(rh_pcts) / max(len(rh_pcts), 1)

    summary = {
        "n_scenarios": len(per_ep),
        "n_steps_per_ep": M,
        "n_agents": N,
        "total_steps": sum_total_steps,
        "max_freq_dev_hz_mean": float(np.mean(max_devs)) if max_devs else 0.0,
        "max_freq_dev_hz_min": float(np.min(max_devs)) if max_devs else 0.0,
        "max_freq_dev_hz_max": float(np.max(max_devs)) if max_devs else 0.0,
        "rocof_hz_per_s_mean": float(np.mean(rocofs)) if rocofs else 0.0,
        "rocof_hz_per_s_max": float(np.max(rocofs)) if rocofs else 0.0,
        "settled_pct": settled_pct,
        "settled_time_s_mean": (sum(settles) / len(settles)) if settles else None,
        "tds_failed_count": sum(1 for p in per_ep if p.tds_failed),
        "nan_inf_count": sum(1 for p in per_ep if p.nan_inf_seen),
        "rh_share_pct_mean": rh_share_mean,
    }

    cumulative = {
        "unnormalized": cum_unnorm,
        "per_M": cum_per_M,
        "per_M_per_N": cum_per_M_per_N,
        "paper_target_unnormalized": PAPER_DDIC_UNNORMALIZED,
        "paper_no_control_unnormalized": PAPER_NO_CONTROL_UNNORMALIZED,
        "deltas_vs_paper": {
            "vs_ddic_unnorm": cum_unnorm - PAPER_DDIC_UNNORMALIZED,
            "vs_no_control_unnorm": cum_unnorm - PAPER_NO_CONTROL_UNNORMALIZED,
            "ratio_vs_ddic": (
                cum_unnorm / PAPER_DDIC_UNNORMALIZED if PAPER_DDIC_UNNORMALIZED != 0 else None
            ),
        },
    }

    return EvalResult(
        schema_version=1,
        checkpoint_path=str(checkpoint_path) if checkpoint_path else "",
        policy_label=policy_label,
        n_scenarios=len(per_ep),
        seed_base=seed_base,
        cumulative_reward_global_rf=cumulative,
        per_episode_metrics=per_ep,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Action selectors
# ---------------------------------------------------------------------------


def make_zero_action_selector(n_agents: int, action_dim: int):
    z = np.zeros((n_agents, action_dim), dtype=np.float32)

    def _sel(_obs):
        return z.copy()

    return _sel


def make_policy_selector(agent):
    def _sel(obs):
        return agent.select_actions_multi(obs, deterministic=True)

    return _sel


# ---------------------------------------------------------------------------
# Result serialization
# ---------------------------------------------------------------------------


def result_to_dict(result: EvalResult) -> dict:
    return {
        "schema_version": result.schema_version,
        "checkpoint_path": result.checkpoint_path,
        "policy_label": result.policy_label,
        "n_scenarios": result.n_scenarios,
        "seed_base": result.seed_base,
        "cumulative_reward_global_rf": result.cumulative_reward_global_rf,
        "summary": result.summary,
        "per_episode_metrics": [
            {
                "scenario_idx": p.scenario_idx,
                "proxy_bus": p.proxy_bus,
                "magnitude_sys_pu": p.magnitude_sys_pu,
                "n_steps": p.n_steps,
                "max_freq_dev_hz": p.max_freq_dev_hz,
                "rocof_max_hz_per_s": p.rocof_max_hz_per_s,
                "nadir_hz": p.nadir_hz,
                "peak_hz": p.peak_hz,
                "settling_time_s": p.settling_time_s,
                "r_f_global_unnormalized": p.r_f_global_unnormalized,
                "r_f_local_total": p.r_f_local_total,
                "r_h_total": p.r_h_total,
                "r_d_total": p.r_d_total,
                "total_reward": p.total_reward,
                "nan_inf_seen": p.nan_inf_seen,
                "tds_failed": p.tds_failed,
            }
            for p in result.per_episode_metrics
        ],
        "figures": result.figures,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Phase 5.1 paper-style evaluator")
    p.add_argument(
        "--checkpoint",
        type=str,
        default=None,
        help="Path to a SACAgent .pt checkpoint. If omitted, runs zero-action baseline.",
    )
    p.add_argument("--n-scenarios", type=int, default=50)
    p.add_argument("--seed-base", type=int, default=42)
    p.add_argument("--policy-label", type=str, default=None)
    p.add_argument("--output-json", type=str, required=True)
    p.add_argument(
        "--disturbance-mode",
        choices=["bus", "gen"],
        default="bus",
        help="bus = ESS-side Pm-step proxy at bus 7/9 (P4.1 default); "
             "gen = SG-side Pm-step proxy at G1/G2/G3 (Z1).",
    )
    p.add_argument(
        "--scenario-set",
        choices=["none", "train", "test"],
        default="none",
        help="Phase 4.3 / G3: load fixed scenarios from JSON manifest. "
             "'none' (default) uses inline deterministic generator. "
             "'train' uses scenario_sets/v3_paper_train_100.json. "
             "'test' uses scenario_sets/v3_paper_test_50.json. "
             "When set, --n-scenarios is overridden by the manifest length.",
    )
    p.add_argument(
        "--scenario-set-path",
        type=str,
        default=None,
        help="Override default manifest path for --scenario-set.",
    )
    return p


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT))
    args = _build_arg_parser().parse_args()

    # Force v3 profile + Path C dispatch (probe sets disturbance_type per ep).
    os.environ["KUNDUR_MODEL_PROFILE"] = str(
        REPO_ROOT / "scenarios" / "kundur" / "model_profiles" / "kundur_cvs_v3.json"
    )
    # 2026-04-30: changed default from "pm_step_proxy_random_bus" (ESS-side,
    # P0' v2 anchor protocol) to "pm_step_proxy_random_gen" (SG-side, P1b
    # validated per_M=-16.14 ≈ paper no_control -15.20). Aligns paper_eval
    # default with config_simulink.py default — eliminates train/eval drift
    # surfaced in 2026-04-30 read-only audit (R2). Operators wanting the
    # legacy ESS-side protocol can still env-var override.
    os.environ.setdefault("KUNDUR_DISTURBANCE_TYPE", "pm_step_proxy_random_gen")

    from env.simulink.kundur_simulink_env import KundurSimulinkEnv
    from env.simulink.sac_agent_standalone import SACAgent
    from scenarios.kundur.config_simulink import (
        DIST_MIN, DIST_MAX, OBS_DIM, ACT_DIM, HIDDEN_SIZES,
    )

    print(f"[paper_eval] constructing KundurSimulinkEnv (cold start) ...")
    t0 = time.time()
    env = KundurSimulinkEnv(training=False)  # eval mode
    print(f"[paper_eval] env constructed ({time.time()-t0:.1f}s)")

    fnom = float(env._F_NOM)
    dt_s = float(env.DT)

    if args.checkpoint:
        ckpt_path = Path(args.checkpoint)
        if not ckpt_path.exists():
            print(f"[paper_eval] ERROR: checkpoint not found: {ckpt_path}")
            return 1
        # Auto-detect: peek at the checkpoint bundle to see if it's a
        # multi-agent G6 bundle or a shared-weights SACAgent checkpoint.
        import torch
        _peek = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
        is_multi_agent = bool(_peek.get("multi_agent", False))
        del _peek
        if is_multi_agent:
            from agents.multi_agent_sac_manager import MultiAgentSACManager
            agent = MultiAgentSACManager(
                n_agents=int(env.N_ESS),
                obs_dim=int(OBS_DIM),
                act_dim=int(ACT_DIM),
                hidden_sizes=tuple(HIDDEN_SIZES),
                alpha_min=0.05,
                device="cpu",
            )
            agent.load(str(ckpt_path))
            print(f"[paper_eval] loaded MULTI-AGENT checkpoint {ckpt_path}")
        else:
            agent = SACAgent(
                obs_dim=int(OBS_DIM),
                act_dim=int(ACT_DIM),
                hidden_sizes=tuple(HIDDEN_SIZES),
                alpha_min=0.05,  # match train_simulink.py:249
                device="cpu",
            )
            agent.load(str(ckpt_path))
            print(f"[paper_eval] loaded SHARED-WEIGHTS checkpoint {ckpt_path}")
        select_fn = make_policy_selector(agent)
        label = args.policy_label or ckpt_path.stem
        print(f"[paper_eval] policy_label='{label}' (multi_agent={is_multi_agent})")
    else:
        select_fn = make_zero_action_selector(env.N_ESS, int(ACT_DIM))
        label = args.policy_label or "zero_action_no_control"
        ckpt_path = None
        print(f"[paper_eval] running zero-action baseline as '{label}'")

    bus_choices = (7, 9) if args.disturbance_mode == "bus" else (1, 2, 3)

    scenarios_override: Optional[list[dict]] = None
    if args.scenario_set != "none":
        from scenarios.kundur.scenario_loader import load_manifest
        default_paths = {
            "train": REPO_ROOT / "scenarios" / "kundur" / "scenario_sets" / "v3_paper_train_100.json",
            "test": REPO_ROOT / "scenarios" / "kundur" / "scenario_sets" / "v3_paper_test_50.json",
        }
        manifest_path = Path(args.scenario_set_path or default_paths[args.scenario_set])
        manifest = load_manifest(manifest_path)
        scenarios_override = [
            {
                "scenario_idx": s.scenario_idx,
                "bus": s.target,  # 7/9 for bus mode, 1/2/3 for gen mode
                "magnitude_sys_pu": s.magnitude_sys_pu,
            }
            for s in manifest.scenarios
        ]
        print(
            f"[paper_eval] loaded manifest {manifest_path.name}: "
            f"{manifest.n_scenarios} scenarios, mode={manifest.disturbance_mode}"
        )

    print(
        f"[paper_eval] running {args.n_scenarios} deterministic scenarios "
        f"(mode={args.disturbance_mode}, bus_choices={bus_choices}, "
        f"seed_base={args.seed_base}, fnom={fnom} Hz, dt={dt_s} s, "
        f"DIST=[{DIST_MIN:.2f}, {DIST_MAX:.2f}] sys-pu, "
        f"scenario_set={args.scenario_set}) ..."
    )

    result = evaluate_policy(
        env=env,
        n_scenarios=args.n_scenarios,
        seed_base=args.seed_base,
        policy_label=label,
        checkpoint_path=str(ckpt_path) if ckpt_path else None,
        select_action_fn=select_fn,
        fnom=fnom,
        dt_s=dt_s,
        dist_min=DIST_MIN,
        dist_max=DIST_MAX,
        bus_choices=bus_choices,
        scenarios_override=scenarios_override,
    )

    out_path = Path(args.output_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result_to_dict(result), f, indent=2, default=str)
    print(f"[paper_eval] wrote {out_path}")

    cum = result.cumulative_reward_global_rf
    print(
        f"[paper_eval] cumulative_global_rf "
        f"unnorm={cum['unnormalized']:+.4f}  "
        f"per_M={cum['per_M']:+.5f}  "
        f"per_M_per_N={cum['per_M_per_N']:+.6f}"
    )
    print(
        f"[paper_eval] paper unnorm: DDIC={PAPER_DDIC_UNNORMALIZED:+.2f}  "
        f"no_control={PAPER_NO_CONTROL_UNNORMALIZED:+.2f}  "
        f"ratio_vs_ddic={cum['deltas_vs_paper']['ratio_vs_ddic']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
