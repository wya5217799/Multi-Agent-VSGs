# FACT: 这是合约本身（搬自 paper_eval.py:1-4，2026-05-03 抽离）。本模块所有
# helper 输出在 PAPER-ANCHOR LOCK 解锁前 INVALID per LOCK，不得作为 paper
# claim 引用。"paper-style" 是 CLAIM —— 公式是否真的与 paper Eq. 对齐要逐项核对 paper。
# 详见 paper_eval.py:1-4 + docs/paper/archive/yang2023-fact-base.md §10
# + docs/EVIDENCE_PROTOCOL.md。

"""Paper §IV-C metric helpers — pure-numpy, env-free.

Extracted from paper_eval.py 2026-05-03; behavior byte-equivalent. Helpers
operate on (omega_trace, f_nom, ...) pure inputs and return float / list /
dict — no env, no torch, no MATLAB. Safe for unit testing.

Contents:

- ``PerEpisodeMetrics``, ``EvalResult`` — output schema dataclasses
  (field order is JSON contract; do not reorder)
- ``generate_scenarios`` — deterministic scenario list given seed
- ``_compute_global_rf_unnorm`` — paper Eq. r_f_global
- ``_compute_global_rf_per_agent`` — per-agent decomposition (Probe B)
- ``_compute_per_agent_max_abs_df`` — per-agent max|Δf|
- ``_compute_per_agent_nadir_peak`` — per-agent nadir / peak
- ``_compute_per_agent_omega_summary`` — sha256 fingerprint + stats
- ``_compute_r_f_local_per_agent_eta1`` — local r_f under η=1 upper bound
- ``_rocof_max`` — peak rate of change of frequency
- ``_settling_time_s`` — first sustained-window settle time
- ``_is_finite_arr`` — finite-value check helper

Hard boundaries (inherited from paper_eval.py:19-23):
- No env / bridge / helper / build / .slx / IC / runtime.mat / reward edits.
- No NE39, no training, no checkpoint mutation.

This module is READ-ONLY computation; no I/O, no side effects.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Result dataclasses (JSON schema contract — field order is part of the API)
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
    # 2026-04-30 Probe B: per-agent decomposition for 4-agent collapse falsification
    r_f_global_per_agent: list[float] = field(default_factory=list)
    max_abs_df_hz_per_agent: list[float] = field(default_factory=list)
    # 2026-04-30 Probe B extension (user request): full per-agent diagnostics
    nadir_hz_per_agent: list[float] = field(default_factory=list)
    peak_hz_per_agent: list[float] = field(default_factory=list)
    omega_trace_summary_per_agent: list[dict] = field(default_factory=list)
    r_f_local_per_agent_eta1: list[float] = field(default_factory=list)


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
    # 2026-04-30 Probe B: omega-source metadata (cvs_v3-specific)
    omega_source_paths: list[dict] = field(default_factory=list)


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


def _compute_global_rf_per_agent(
    omega_trace: np.ndarray,  # shape (T, N_agents)
    f_nom: float,
) -> list[float]:
    """Per-agent contribution to r_f_global: -Σ_t (Δf_i,t - mean_j Δf_j,t)².

    2026-04-30 (Probe B for fresh-context falsification audit): per-agent
    decomposition is needed to falsify the "4-agent measurement collapse"
    hypothesis surfaced by the 2026-04-30 audit (5 scenarios bit-identical
    in cvs_v3_eval_fix_smoke/loadstep_metrics.json suggested per-agent
    omega traces may not be electrically separated). If max - min over
    the returned list is ~ 0 across all scenarios, the 4 agents are
    receiving collapsed measurements — broken mode-shape distribution.
    """
    if omega_trace.size == 0:
        return [0.0]
    delta_f = (omega_trace - 1.0) * f_nom  # (T, N)
    mean_t = delta_f.mean(axis=1, keepdims=True)  # (T, 1)
    centered = delta_f - mean_t  # (T, N)
    per_agent = -(centered ** 2).sum(axis=0)  # (N,)
    return [float(x) for x in per_agent]


def _compute_per_agent_max_abs_df(
    omega_trace: np.ndarray,  # shape (T, N_agents)
    f_nom: float,
) -> list[float]:
    """Per-agent max|Δf| in Hz. 2026-04-30 Probe B companion: smoking-gun
    test for 4-agent measurement collapse. If all N entries are bit-equal
    across scenarios, omega_ts_i may be wired to a single shared signal.
    """
    if omega_trace.size == 0:
        return [0.0]
    delta_f_abs = np.abs((omega_trace - 1.0) * f_nom)  # (T, N)
    per_agent = delta_f_abs.max(axis=0)  # (N,)
    return [float(x) for x in per_agent]


def _compute_per_agent_nadir_peak(
    omega_trace: np.ndarray, f_nom: float,
) -> tuple[list[float], list[float]]:
    """Per-agent nadir (most-negative Δf) and peak (most-positive Δf) in Hz.

    2026-04-30 Probe B: a +0.5 / -0.5 magnitude pair must produce
    sign-asymmetric per-agent nadir/peak. If both magnitudes give same
    sign across all 4 agents → dispatch sign convention is broken; if
    all 4 agents show identical nadir → measurement collapse.
    """
    if omega_trace.size == 0:
        return [0.0], [0.0]
    delta_f = (omega_trace - 1.0) * f_nom  # (T, N)
    nadir = delta_f.min(axis=0)  # (N,)
    peak = delta_f.max(axis=0)  # (N,)
    return [float(x) for x in nadir], [float(x) for x in peak]


def _compute_per_agent_omega_summary(
    omega_trace: np.ndarray,
) -> list[dict]:
    """Per-agent omega trace fingerprint for byte-equality detection.

    2026-04-30 Probe B: returns mean / std / first / last / sha256 of
    each agent's full omega trajectory. Two agents with byte-identical
    sha256 are demonstrably aliased to the same MATLAB signal. Different
    sha256 with similar nadir/peak are physically coupled (legitimate)
    rather than aliased (broken).
    """
    if omega_trace.size == 0:
        return []
    out = []
    T, N = omega_trace.shape
    for i in range(N):
        col = omega_trace[:, i]
        h = hashlib.sha256(col.tobytes()).hexdigest()[:16]
        out.append({
            "agent_idx": i,
            "n_samples": int(T),
            "mean": float(col.mean()),
            "std": float(col.std()),
            "first": float(col[0]),
            "last": float(col[-1]),
            "sha256_16": h,
        })
    return out


def _compute_r_f_local_per_agent_eta1(
    omega_trace: np.ndarray, f_nom: float,
    comm_adj: dict[int, list[int]],
) -> list[float]:
    """Per-agent local r_f under η=1 (no comm failure) upper bound.

    Mirror of _base.py reward formula r_f_i (Eq.15-16) recomputed from
    omega trace alone — assumes all comm links active. Cannot match
    online r_f exactly (comm fail samples differ per step), but
    differential between two scenarios is meaningful for collapse
    detection. Sum across agents == _compute_global_rf only if
    comm_adj fully connected (it isn't here — ring topology).
    """
    if omega_trace.size == 0:
        return [0.0]
    delta_f = (omega_trace - 1.0) * f_nom  # (T, N) Hz
    delta_w_pu = delta_f / f_nom  # back to pu (paper Eq.15-16 in pu)
    T, N = delta_w_pu.shape
    out = [0.0] * N
    for i in range(N):
        nbrs = comm_adj.get(i, [])
        # local mean: agent + neighbors (η=1)
        local_idxs = [i] + list(nbrs)
        omega_bar = delta_w_pu[:, local_idxs].mean(axis=1)  # (T,)
        # r_f_i = -(dw_i - omega_bar)^2 - sum_j (dw_j - omega_bar)^2 (η=1)
        own = -((delta_w_pu[:, i] - omega_bar) ** 2)
        nb_sum = sum(
            -((delta_w_pu[:, j] - omega_bar) ** 2) for j in nbrs
        )
        r_f_i_per_step = own + (nb_sum if nbrs else 0.0)
        out[i] = float(r_f_i_per_step.sum())
    return out


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
