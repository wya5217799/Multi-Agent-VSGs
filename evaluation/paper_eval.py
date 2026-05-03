# FACT: 这是合约本身。evaluator 的 metric 计算逻辑 = 项目实际评分方式。
# "paper-style" 是 CLAIM —— 公式是否真的与 paper Eq. 对齐要逐项核对 paper。
# 受 PAPER-ANCHOR LOCK：任何 paper 数字引用须连 INVALID_PAPER_ANCHOR.md 一起引。
# 详见 docs/EVIDENCE_PROTOCOL.md。

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
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

# 2026-05-03: Metric helpers + dataclasses + scenario gen extracted to
# evaluation.metrics for unit testability and reuse. Re-exported below
# (see "Re-exports" section) for backward compat with existing callers
# (e.g. probes/kundur/probe_state/_discover.py imports KUNDUR_CVS_V3_*
# from this module — those Kundur-specific dicts deliberately stay here).
from evaluation.metrics import (  # noqa: F401  (re-export, see below)
    EvalResult,
    PerEpisodeMetrics,
    _compute_global_rf_per_agent,
    _compute_global_rf_unnorm,
    _compute_per_agent_max_abs_df,
    _compute_per_agent_nadir_peak,
    _compute_per_agent_omega_summary,
    _compute_r_f_local_per_agent_eta1,
    _is_finite_arr,
    _rocof_max,
    _settling_time_s,
    generate_scenarios,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Paper baselines (roadmap §3.4 table; paper Sec.IV-C)
# ---------------------------------------------------------------------------

PAPER_DDIC_UNNORMALIZED = -8.04
PAPER_NO_CONTROL_UNNORMALIZED = -15.20

# Settling tolerance defaults (paper does not specify; project default
# 0.01 % × f_n = 5 mHz). CLI flag --settle-tol-hz overrides at runtime;
# resolved value lands in JSON output's runner_config.settle_tol_hz.
SETTLE_TOL_HZ = 0.005
SETTLE_WINDOW_S = 1.0

# 2026-05-03: _LOADSTEP_ENV_PREFIXES + _resolve_disturbance_dispatch +
# _build_runner_config moved to evaluation/runner_helpers.py for the
# same reason as the metrics extraction (testability, locality).
# Re-exported below; behavior byte-equivalent.
from evaluation.runner_helpers import (  # noqa: F401  (re-export)
    _LOADSTEP_ENV_PREFIXES,
    _build_runner_config,
    _resolve_disturbance_dispatch,
)

# 2026-04-30 Probe B metadata: kundur_cvs_v3 omega measurement source paths.
# Hardcoded from build_kundur_cvs_v3.m::src_meta (lines 439-442) — IntW
# integrator output → ToWorkspace block W_omega_<sname> → MATLAB workspace
# Timeseries omega_ts_<idx>. Used to verify per-agent omega traces are
# pulled from electrically distinct sources (vs aliased to a single signal).
KUNDUR_CVS_V3_OMEGA_SOURCES: list[dict] = [
    {"agent_idx": 0, "sname": "ES1", "bus": 12,
     "ts_var": "omega_ts_1", "tw_block": "W_omega_ES1",
     "input_block": "IntW_ES1"},
    {"agent_idx": 1, "sname": "ES2", "bus": 16,
     "ts_var": "omega_ts_2", "tw_block": "W_omega_ES2",
     "input_block": "IntW_ES2"},
    {"agent_idx": 2, "sname": "ES3", "bus": 14,
     "ts_var": "omega_ts_3", "tw_block": "W_omega_ES3",
     "input_block": "IntW_ES3"},
    {"agent_idx": 3, "sname": "ES4", "bus": 15,
     "ts_var": "omega_ts_4", "tw_block": "W_omega_ES4",
     "input_block": "IntW_ES4"},
]
KUNDUR_CVS_V3_COMM_ADJ: dict[int, list[int]] = {
    0: [1, 3], 1: [0, 2], 2: [1, 3], 3: [2, 0],  # ring topology
}


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
    disturbance_mode: str = "bus",
    settle_tol_hz: float = SETTLE_TOL_HZ,
    settle_window_s: float = SETTLE_WINDOW_S,
) -> EvalResult:
    """Run `n_scenarios` deterministic episodes; collect per-ep + cumulative metrics.

    If `scenarios_override` is provided, it is used as the scenario list directly
    (G3 / Phase 4.3: load from JSON manifest instead of inline generator).
    Each entry must have keys {scenario_idx, bus, magnitude_sys_pu}; bus ∈
    {7, 9, 1, 2, 3, 4} per the disturbance dispatch translation. The
    ``disturbance_mode`` argument disambiguates bus values 1/2/3 between
    SG-side ('gen') and ESS-side direct ('vsg', extends to bus=4).
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
    # 2026-04-30: extended allowed set with 1-4 for vsg mode + 0 for hybrid F4.
    _allowed_buses = {0, 7, 9, 1, 2, 3, 4}
    _preferred_type = os.environ.get("KUNDUR_DISTURBANCE_TYPE", "")
    # 2026-05-03 Path C: loadstep_ptdf_* is multi-point dispatch (bus
    # informational), shares LoadStep semantics — bypass bus check.
    if not _preferred_type.startswith(("loadstep_paper_", "loadstep_ptdf_")):
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
        # 2026-05-03 Path C: PTDF dispatch shares LoadStep semantics
        # (bus field informational, env-var preserved at construction).
        if preferred_type.startswith(("loadstep_paper_", "loadstep_ptdf_")):
            obs, _info0 = env.reset(
                seed=seed_base + 1009 * sc_idx,
                options={
                    "disturbance_magnitude": mag,
                    "trigger_at_step": 0,
                },
            )
        else:
            if bus in (7, 9) and disturbance_mode == "ccs_load":
                # 2026-04-30 Option E: CCS at paper Fig.3 load centers Bus 7/9
                # (must precede the unconditional bus==7/9 -> kind="bus" branch
                # which routes to ESS-side pm_step_proxy_busN).
                _kind, _target = "ccs_load", int(bus)
            elif bus == 7:
                _kind, _target = "bus", 7
            elif bus == 9:
                _kind, _target = "bus", 9
            elif bus in (1, 2, 3) and disturbance_mode == "gen":
                _kind, _target = "gen", int(bus)
            elif bus in (1, 2, 3, 4) and disturbance_mode == "vsg":
                # 2026-04-30 Probe B-ESS: single-ESS direct Pm injection
                _kind, _target = "vsg", int(bus)
            elif disturbance_mode == "hybrid":
                # 2026-04-30 Option F4: bus field is informational; dispatch
                # picks random G internally
                _kind, _target = "hybrid", int(bus)
            elif bus in (1, 2, 3):  # default: gen if mode unset
                _kind, _target = "gen", int(bus)
            else:
                raise ValueError(f"Unsupported bus/gen/vsg index {bus} for mode {disturbance_mode}")
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
                omega_trace, dt_s, fnom, settle_tol_hz, settle_window_s
            )
            r_f_per_agent = _compute_global_rf_per_agent(omega_trace, fnom)
            max_df_per_agent = _compute_per_agent_max_abs_df(omega_trace, fnom)
            nadir_per_agent, peak_per_agent = _compute_per_agent_nadir_peak(
                omega_trace, fnom
            )
            omega_summary_per_agent = _compute_per_agent_omega_summary(omega_trace)
            r_f_local_per_agent = _compute_r_f_local_per_agent_eta1(
                omega_trace, fnom, KUNDUR_CVS_V3_COMM_ADJ
            )
        else:
            r_f_global = 0.0
            max_dev = 0.0
            nadir_hz = 0.0
            peak_hz = 0.0
            rocof = 0.0
            sett = None
            r_f_per_agent = []
            max_df_per_agent = []
            nadir_per_agent = []
            peak_per_agent = []
            omega_summary_per_agent = []
            r_f_local_per_agent = []

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
            r_f_global_per_agent=r_f_per_agent,
            max_abs_df_hz_per_agent=max_df_per_agent,
            nadir_hz_per_agent=nadir_per_agent,
            peak_hz_per_agent=peak_per_agent,
            omega_trace_summary_per_agent=omega_summary_per_agent,
            r_f_local_per_agent_eta1=r_f_local_per_agent,
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
        # 2026-05-03 schema_version 1 → 2: added top-level "runner_config"
        # block (PHI weights + settle config + dispatch_resolution).
        # Additive change; per-episode metrics layout unchanged. Downstream
        # consumers may use this version to gate the runner_config read.
        schema_version=2,
        checkpoint_path=str(checkpoint_path) if checkpoint_path else "",
        policy_label=policy_label,
        n_scenarios=len(per_ep),
        seed_base=seed_base,
        cumulative_reward_global_rf=cumulative,
        per_episode_metrics=per_ep,
        summary=summary,
        omega_source_paths=KUNDUR_CVS_V3_OMEGA_SOURCES,  # 2026-04-30 Probe B
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


def _wrap_with_zero_agent_ablation(select_fn, zero_agent_idx: int):
    """Wrap a select_fn to force agent at zero_agent_idx to output zeros.

    Used for B-a action ablation (2026-04-30): verify trained policy
    actually uses each agent vs converging to ES1-mimic-only behavior.
    Caller validates zero_agent_idx is within [0, n_agents).
    """
    def _zeroed(obs):
        a = select_fn(obs)
        a = np.array(a, copy=True)
        a[zero_agent_idx, :] = 0.0
        return a
    return _zeroed


# ---------------------------------------------------------------------------
# Agent loading + single-cell + batch (P1a, 2026-05-03)
# ---------------------------------------------------------------------------


def _load_agent_from_checkpoint(
    ckpt_path: Path,
    *,
    n_ess: int,
    obs_dim: int,
    act_dim: int,
    hidden_sizes: tuple,
) -> tuple[object, bool]:
    """Auto-detect single-agent vs multi-agent checkpoint and load it.

    Returns (agent, is_multi_agent). Raises FileNotFoundError if the
    path does not exist; lets torch.load propagate other errors.

    Heavy imports (torch, agent classes) happen inside this function so
    the module top-level stays MATLAB/torch-free.
    """
    if not ckpt_path.exists():
        raise FileNotFoundError(f"checkpoint not found: {ckpt_path}")
    import torch
    _peek = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    is_multi_agent = bool(_peek.get("multi_agent", False))
    del _peek
    if is_multi_agent:
        from agents.multi_agent_sac_manager import MultiAgentSACManager
        agent = MultiAgentSACManager(
            n_agents=n_ess,
            obs_dim=obs_dim,
            act_dim=act_dim,
            hidden_sizes=tuple(hidden_sizes),
            alpha_min=0.05,
            device="cpu",
        )
    else:
        from env.simulink.sac_agent_standalone import SACAgent
        agent = SACAgent(
            obs_dim=obs_dim,
            act_dim=act_dim,
            hidden_sizes=tuple(hidden_sizes),
            alpha_min=0.05,  # match train_simulink.py:249
            device="cpu",
        )
    agent.load(str(ckpt_path))
    return agent, is_multi_agent


def _resolve_bus_choices(effective_mode: str) -> tuple[int, ...]:
    """Map effective disturbance mode to allowed bus_choices for scenario gen.

    Pure function; tested via test_paper_eval_runner. The ``hybrid`` and
    ``ccs_load`` choices are 2026-04-30 dispatch protocol additions.
    """
    if effective_mode == "bus":
        return (7, 9)
    if effective_mode == "gen":
        return (1, 2, 3)
    if effective_mode == "vsg":
        return (1, 2, 3, 4)  # 1-indexed ES{i}
    if effective_mode == "ccs_load":
        return (7, 9)  # 2026-04-30 Option E: CCS at paper Fig.3 load centers
    if effective_mode == "hybrid":
        return (0,)  # 2026-04-30 Option F4: target field informational
    return (7, 9)  # defensive fallback


def run_single_eval(
    env,
    *,
    ckpt_path: Optional[Path],
    zero_agent_idx: Optional[int],
    scenario_set: str,
    scenario_set_path: Optional[Path],
    n_scenarios: int,
    seed_base: int,
    disturbance_mode_cli: Optional[str],
    settle_tol_hz: float,
    output_path: Path,
    policy_label: Optional[str] = None,
    obs_dim: Optional[int] = None,
    act_dim: Optional[int] = None,
    hidden_sizes: Optional[tuple] = None,
    dist_min: Optional[float] = None,
    dist_max: Optional[float] = None,
) -> tuple[EvalResult, dict]:
    """Run one evaluation cell end-to-end and write its JSON.

    Encapsulates: dispatch resolution → agent load (or zero baseline) →
    select_fn (with optional ablation) → scenario manifest load →
    evaluate_policy → runner_config snapshot → write JSON. Single env
    instance is reused across calls (caller controls cold-start cost).

    Returns (result, runner_config) so caller can build batch summaries
    without re-reading the JSON.

    The ``obs_dim`` / ``act_dim`` / ``hidden_sizes`` / ``dist_min`` /
    ``dist_max`` args default to the env's KUNDUR_CVS_V3 config when
    omitted (read from scenarios.kundur.config_simulink at first call).
    """
    if obs_dim is None or act_dim is None or hidden_sizes is None \
       or dist_min is None or dist_max is None:
        from scenarios.kundur.config_simulink import (
            ACT_DIM, DIST_MAX, DIST_MIN, HIDDEN_SIZES, OBS_DIM,
        )
        obs_dim = OBS_DIM if obs_dim is None else obs_dim
        act_dim = ACT_DIM if act_dim is None else act_dim
        hidden_sizes = tuple(HIDDEN_SIZES) if hidden_sizes is None else hidden_sizes
        dist_min = DIST_MIN if dist_min is None else dist_min
        dist_max = DIST_MAX if dist_max is None else dist_max

    fnom = float(env._F_NOM)
    dt_s = float(env.DT)

    # 1. Dispatch resolution (P0c) — may SystemExit on explicit conflict.
    dispatch_resolution = _resolve_disturbance_dispatch(
        cli_mode=disturbance_mode_cli,
        env_type=os.environ.get("KUNDUR_DISTURBANCE_TYPE", ""),
    )
    effective_mode = disturbance_mode_cli if disturbance_mode_cli is not None else "bus"
    bus_choices = _resolve_bus_choices(effective_mode)

    # 2. Agent load (None → zero-action baseline).
    if ckpt_path is not None:
        agent, is_multi_agent = _load_agent_from_checkpoint(
            ckpt_path,
            n_ess=int(env.N_ESS),
            obs_dim=int(obs_dim),
            act_dim=int(act_dim),
            hidden_sizes=tuple(hidden_sizes),
        )
        select_fn = make_policy_selector(agent)
        label = policy_label or ckpt_path.stem
        print(f"[paper_eval] loaded {'MULTI-AGENT' if is_multi_agent else 'SHARED-WEIGHTS'} "
              f"checkpoint {ckpt_path}")
    else:
        select_fn = make_zero_action_selector(int(env.N_ESS), int(act_dim))
        label = policy_label or "zero_action_no_control"
        print(f"[paper_eval] zero-action baseline as '{label}'")

    # 3. Optional ablation wrap.
    if zero_agent_idx is not None:
        if not (0 <= zero_agent_idx < int(env.N_ESS)):
            raise ValueError(
                f"zero_agent_idx={zero_agent_idx} out of range [0, {env.N_ESS})"
            )
        select_fn = _wrap_with_zero_agent_ablation(select_fn, zero_agent_idx)
        print(f"[paper_eval] ablation: agent {zero_agent_idx} (ES{zero_agent_idx+1}) "
              f"actions forced to 0")

    # 4. Scenarios manifest (or inline).
    scenarios_override: Optional[list[dict]] = None
    if scenario_set != "none":
        from scenarios.kundur.scenario_loader import load_manifest
        default_paths = {
            "train": REPO_ROOT / "scenarios" / "kundur" / "scenario_sets" / "v3_paper_train_100.json",
            "test": REPO_ROOT / "scenarios" / "kundur" / "scenario_sets" / "v3_paper_test_50.json",
        }
        manifest_path = Path(scenario_set_path or default_paths[scenario_set])
        manifest = load_manifest(manifest_path)
        scenarios_override = [
            {"scenario_idx": s.scenario_idx, "bus": s.target,
             "magnitude_sys_pu": s.magnitude_sys_pu}
            for s in manifest.scenarios
        ]
        print(f"[paper_eval] manifest {manifest_path.name}: {manifest.n_scenarios} scenarios")

    # 5. Run.
    print(
        f"[paper_eval] running cell '{label}' "
        f"(mode={effective_mode}, dispatch_path={dispatch_resolution['dispatch_path']}, "
        f"settle_tol_hz={settle_tol_hz}) ..."
    )
    result = evaluate_policy(
        env=env,
        n_scenarios=n_scenarios,
        seed_base=seed_base,
        policy_label=label,
        checkpoint_path=str(ckpt_path) if ckpt_path else None,
        select_action_fn=select_fn,
        fnom=fnom,
        dt_s=dt_s,
        dist_min=dist_min,
        dist_max=dist_max,
        bus_choices=bus_choices,
        scenarios_override=scenarios_override,
        disturbance_mode=effective_mode,
        settle_tol_hz=settle_tol_hz,
        settle_window_s=SETTLE_WINDOW_S,
    )

    # 6. Snapshot runner_config + write JSON.
    runner_config = _build_runner_config(
        env=env,
        settle_tol_hz=settle_tol_hz,
        settle_window_s=SETTLE_WINDOW_S,
        dispatch_resolution=dispatch_resolution,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(result_to_dict(result, runner_config=runner_config), f,
                  indent=2, default=str)
    print(f"[paper_eval] wrote {output_path}")

    return result, runner_config


def _load_batch_spec(path: Path) -> dict:
    """Parse + validate batch spec JSON. Raises ValueError on bad shape.

    Required keys:
      - ``checkpoints``: list[str] (≥1) — paths to .pt files (or null for
        zero-action baseline if exactly one entry equals null/None)
      - ``ablations``: list[dict] (≥1) with ``label`` (str) and
        ``zero_agent_idx`` (int or null)
      - ``output_dir``: str — directory for per-cell JSONs

    Optional (override main()-level CLI defaults):
      - ``scenario_set`` (str, default "none")
      - ``scenario_set_path`` (str, default null)
      - ``disturbance_mode`` (str or null, default null = use env-var)
      - ``settle_tol_hz`` (float, default ``SETTLE_TOL_HZ``)
      - ``n_scenarios`` (int, default 50)
      - ``seed_base`` (int, default 42)
    """
    if not path.exists():
        raise FileNotFoundError(f"batch spec not found: {path}")
    spec = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ValueError(f"batch spec must be a JSON object, got {type(spec).__name__}")

    # Required keys.
    for k in ("checkpoints", "ablations", "output_dir"):
        if k not in spec:
            raise ValueError(f"batch spec missing required key {k!r}")
    if not isinstance(spec["checkpoints"], list) or not spec["checkpoints"]:
        raise ValueError("'checkpoints' must be non-empty list")
    if not isinstance(spec["ablations"], list) or not spec["ablations"]:
        raise ValueError("'ablations' must be non-empty list")
    for i, ab in enumerate(spec["ablations"]):
        if not isinstance(ab, dict):
            raise ValueError(f"ablations[{i}] must be a dict, got {type(ab).__name__}")
        if "label" not in ab or not isinstance(ab["label"], str) or not ab["label"]:
            raise ValueError(f"ablations[{i}] missing non-empty 'label' string")
        zai = ab.get("zero_agent_idx")
        if zai is not None and not isinstance(zai, int):
            raise ValueError(f"ablations[{i}].zero_agent_idx must be int or null, "
                             f"got {type(zai).__name__}")

    # Apply defaults for optional keys.
    spec.setdefault("scenario_set", "none")
    spec.setdefault("scenario_set_path", None)
    spec.setdefault("disturbance_mode", None)
    spec.setdefault("settle_tol_hz", SETTLE_TOL_HZ)
    spec.setdefault("n_scenarios", 50)
    spec.setdefault("seed_base", 42)
    return spec


def run_batch(env, batch_spec: dict) -> dict:
    """Run all (checkpoint × ablation) cells with single env reuse.

    Per-cell failures (FileNotFoundError, RuntimeError, ValueError) are
    caught and recorded in the returned summary; the batch continues so
    a 25-min cold-start isn't lost on the first bad ckpt path. Each
    successful cell writes its own JSON to
    ``<output_dir>/<ckpt_stem>_<ablation_label>.json``.

    Returns summary dict:
      {
        "n_cells": int,
        "n_pass": int,
        "n_fail": int,
        "total_time_s": float,
        "results": list[{"ckpt": str, "ablation": str,
                         "status": "PASS"|"FAIL", "output_path": str|null,
                         "error": str|null}],
      }
    """
    out_dir = Path(batch_spec["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    ckpts = batch_spec["checkpoints"]
    ablations = batch_spec["ablations"]
    n_cells = len(ckpts) * len(ablations)
    print(f"[paper_eval] batch: {len(ckpts)} ckpt × {len(ablations)} ablation = "
          f"{n_cells} cells; output_dir={out_dir}")

    results: list[dict] = []
    t_batch = time.time()
    for ckpt_str in ckpts:
        ckpt_path = Path(ckpt_str) if ckpt_str else None
        ckpt_stem = ckpt_path.stem if ckpt_path else "zero_action_no_control"
        for ab in ablations:
            label = ab["label"]
            zai = ab.get("zero_agent_idx")
            cell_id = f"{ckpt_stem}__{label}"
            out_path = out_dir / f"{cell_id}.json"
            print(f"[paper_eval] === cell {len(results)+1}/{n_cells}: {cell_id} ===")
            try:
                run_single_eval(
                    env=env,
                    ckpt_path=ckpt_path,
                    zero_agent_idx=zai,
                    scenario_set=batch_spec["scenario_set"],
                    scenario_set_path=(Path(batch_spec["scenario_set_path"])
                                       if batch_spec["scenario_set_path"] else None),
                    n_scenarios=int(batch_spec["n_scenarios"]),
                    seed_base=int(batch_spec["seed_base"]),
                    disturbance_mode_cli=batch_spec["disturbance_mode"],
                    settle_tol_hz=float(batch_spec["settle_tol_hz"]),
                    output_path=out_path,
                    policy_label=label,
                )
                results.append({
                    "ckpt": str(ckpt_path) if ckpt_path else None,
                    "ablation": label,
                    "status": "PASS",
                    "output_path": str(out_path),
                    "error": None,
                })
            except (FileNotFoundError, ValueError, RuntimeError) as e:
                # Log + continue; preserves cold-start work for remaining cells.
                err_msg = f"{type(e).__name__}: {e}"
                print(f"[paper_eval] cell FAIL: {err_msg}", file=sys.stderr)
                results.append({
                    "ckpt": str(ckpt_path) if ckpt_path else None,
                    "ablation": label,
                    "status": "FAIL",
                    "output_path": None,
                    "error": err_msg,
                })

    total = time.time() - t_batch
    n_pass = sum(1 for r in results if r["status"] == "PASS")
    n_fail = n_cells - n_pass
    summary = {
        "n_cells": n_cells,
        "n_pass": n_pass,
        "n_fail": n_fail,
        "total_time_s": total,
        "results": results,
    }
    summary_path = out_dir / "_batch_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"[paper_eval] batch done: {n_pass}/{n_cells} PASS in {total:.1f}s; "
          f"summary at {summary_path}")
    return summary


# ---------------------------------------------------------------------------
# Result serialization
# ---------------------------------------------------------------------------


def result_to_dict(
    result: EvalResult,
    runner_config: Optional[dict] = None,
) -> dict:
    # 2026-04-30 PAPER-ANCHOR LOCK: hardcoded False until Signal/Measurement/
    # Causality 三层反证 gate (G1-G6) 全部 PASS 且 verdict 文件存在于
    # quality_reports/paper_compliance/three_layer_signoff/ 且 < 7 天。
    # 详见 docs/paper/archive/yang2023-fact-base.md §10 PAPER-ANCHOR LOCK（历史快照）；论文事实查询走 docs/paper/kd_4agent_paper_facts.md
    # 与 docs/paper/disturbance-protocol-mismatch-fix-report.md。
    # 任何 cum_unnorm 与 PAPER_DDIC_UNNORMALIZED / PAPER_NO_CONTROL_UNNORMALIZED
    # 的对账在此字段为 False 时均视为 INVALID。
    #
    # 2026-05-03 (P0b): runner_config (PHI weights + settle config +
    # dispatch_resolution) is now a top-level block. Older callers passing
    # only `result` get an empty {} for backward compat — but should
    # update to provide it (since schema_version=2 implies its presence).
    return {
        "schema_version": result.schema_version,
        "paper_comparison_enabled": False,
        "runner_config": runner_config if runner_config is not None else {},
        "paper_comparison_lock_reason": (
            "INCONCLUSIVE_STOP_REQUIRED (2026-04-30 STOP verdict): "
            "Signal layer LoadStep dead; Measurement layer Probe B verdict "
            "not delivered; Causality layer +10% improvement attributed to "
            "action regularization. cum_unnorm vs paper -8.04 / -15.20 INVALID."
        ),
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
                "r_f_global_per_agent": p.r_f_global_per_agent,
                "max_abs_df_hz_per_agent": p.max_abs_df_hz_per_agent,
                "nadir_hz_per_agent": p.nadir_hz_per_agent,
                "peak_hz_per_agent": p.peak_hz_per_agent,
                "omega_trace_summary_per_agent": p.omega_trace_summary_per_agent,
                "r_f_local_per_agent_eta1": p.r_f_local_per_agent_eta1,
            }
            for p in result.per_episode_metrics
        ],
        "figures": result.figures,
        "omega_source_paths": result.omega_source_paths,  # 2026-04-30 Probe B
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Phase 5.1 paper-style evaluator")
    # 2026-05-03 (P1a): --checkpoint vs --batch-spec are mutually exclusive.
    # Single-cell mode = --checkpoint + --output-json (legacy CLI shape).
    # Batch mode = --batch-spec PATH (writes per-cell JSONs to spec.output_dir;
    # --output-json then becomes optional summary path; ignored if not given).
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--checkpoint",
        type=str,
        default=None,
        help="Path to a SACAgent .pt checkpoint. If omitted (and --batch-spec "
             "also omitted), runs zero-action baseline. Mutually exclusive "
             "with --batch-spec.",
    )
    g.add_argument(
        "--batch-spec",
        type=str,
        default=None,
        help="Path to a batch-spec JSON describing checkpoints × ablations "
             "to evaluate in a single env cold-start. See _load_batch_spec "
             "docstring for required schema. Mutually exclusive with "
             "--checkpoint; --output-json becomes optional in batch mode "
             "(per-cell JSONs land in spec.output_dir).",
    )
    p.add_argument("--n-scenarios", type=int, default=50)
    p.add_argument("--seed-base", type=int, default=42)
    p.add_argument("--policy-label", type=str, default=None)
    p.add_argument(
        "--output-json", type=str, default=None,
        help="Required in single-cell mode (--checkpoint or zero-action). "
             "Ignored in batch mode (per-cell JSONs land in spec.output_dir).",
    )
    p.add_argument(
        "--disturbance-mode",
        choices=["bus", "gen", "vsg", "hybrid", "ccs_load"],
        default=None,  # 2026-05-03 (P0c): default None lets us distinguish
                       # "user didn't specify" from "user explicitly chose
                       # bus" — needed by _resolve_disturbance_dispatch to
                       # tell explicit-conflict (raise) from implicit-conflict
                       # (warn) when KUNDUR_DISTURBANCE_TYPE=loadstep_*.
                       # Backward-compat: missing → resolves to 'bus' unless
                       # env-var forces loadstep dispatch.
        help="bus = ESS-side Pm-step proxy at bus 7/9 (default if neither "
             "this flag nor KUNDUR_DISTURBANCE_TYPE=loadstep_* is set); "
             "gen = SG-side Pm-step proxy at G1/G2/G3 (Z1); "
             "vsg = single-ESS direct Pm injection at ES1/2/3/4 "
             "(2026-04-30 Probe B-ESS prereq for Option F); "
             "hybrid = Option F4 SG-random + ESS-compensate, all 4 ES "
             "agents above 1e-3 Hz per scenario (2026-04-30 design final).",
    )
    p.add_argument(
        "--settle-tol-hz",
        type=float,
        default=SETTLE_TOL_HZ,
        help=f"Settling tolerance in Hz (paper unspecified; project default "
             f"{SETTLE_TOL_HZ} = 0.01%% × 50 Hz). Resolved value lands in "
             f"runner_config.settle_tol_hz of the output JSON.",
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
    p.add_argument(
        "--zero-agent-idx",
        type=int,
        default=None,
        help="2026-04-30 (B-a action ablation): force agent at this 0-based "
             "index to output zero action every step (= keep H/D at "
             "baseline = no_control for this agent). Used to verify whether "
             "trained policy actually uses each agent vs. ES1-only mimic.",
    )
    return p


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT))
    args = _build_arg_parser().parse_args()

    # Single-cell mode requires --output-json; batch mode does not.
    if args.batch_spec is None and args.output_json is None:
        print("[paper_eval] ERROR: --output-json is required in single-cell "
              "mode (no --batch-spec given).", file=sys.stderr)
        return 2

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

    print(f"[paper_eval] constructing KundurSimulinkEnv (cold start) ...")
    t0 = time.time()
    env = KundurSimulinkEnv(training=False)  # eval mode
    print(f"[paper_eval] env constructed ({time.time()-t0:.1f}s)")

    # Batch mode: parse spec, run cartesian product, write summary, exit.
    if args.batch_spec is not None:
        try:
            spec = _load_batch_spec(Path(args.batch_spec))
        except (FileNotFoundError, ValueError) as e:
            print(f"[paper_eval] ERROR: invalid batch spec: {e}", file=sys.stderr)
            return 2
        summary = run_batch(env=env, batch_spec=spec)
        return 0 if summary["n_fail"] == 0 else 1

    # Single-cell mode (legacy CLI shape preserved).
    ckpt_path = Path(args.checkpoint) if args.checkpoint else None
    try:
        result, _ = run_single_eval(
            env=env,
            ckpt_path=ckpt_path,
            zero_agent_idx=args.zero_agent_idx,
            scenario_set=args.scenario_set,
            scenario_set_path=(Path(args.scenario_set_path)
                               if args.scenario_set_path else None),
            n_scenarios=int(args.n_scenarios),
            seed_base=int(args.seed_base),
            disturbance_mode_cli=args.disturbance_mode,
            settle_tol_hz=float(args.settle_tol_hz),
            output_path=Path(args.output_json),
            policy_label=args.policy_label,
        )
    except FileNotFoundError as e:
        print(f"[paper_eval] ERROR: {e}", file=sys.stderr)
        return 1

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
