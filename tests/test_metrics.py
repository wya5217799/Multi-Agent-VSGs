"""Tests for paper §IV-C metric helpers in ``evaluation.metrics``.

Originally written as characterization tests during the 2026-05-03 extract
from ``evaluation.paper_eval``; now hit ``evaluation.metrics`` directly
(post-extract). The ``paper_eval`` re-export path is verified separately
in the Step 6 import-side smoke check.

Pure-numpy; no MATLAB engine, no env construction, no checkpoints.
Marked offline so they run in any environment.
"""
from __future__ import annotations

from dataclasses import fields

import numpy as np
import pytest

# 2026-05-03 Phase 2 (post-extract): tests now hit evaluation.metrics
# directly. paper_eval.py also re-exports these symbols (backward-compat
# for probes/scenarios callers); separate Step 6 smoke covers that path.
from evaluation.metrics import (
    EvalResult,
    PerEpisodeMetrics,
    _bootstrap_ci,
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

pytestmark = pytest.mark.offline

F_NOM = 50.0  # Kundur nominal frequency (Hz)
DT_S = 0.04  # one bridge step (seconds)


# ---------------------------------------------------------------------------
# Trace fixtures (synthetic, deterministic)
# ---------------------------------------------------------------------------


def _make_synchronous_trace(
    T: int = 10, n_agents: int = 4, omega_pu: float = 1.0
) -> np.ndarray:
    """All agents share identical omega — collapse / aliasing baseline."""
    return np.full((T, n_agents), omega_pu, dtype=np.float64)


def _make_asymmetric_trace(T: int = 10) -> np.ndarray:
    """4 agents with distinct linear drifts — no two columns equal."""
    t = np.arange(T, dtype=np.float64)
    cols = [
        1.0 + 0.0010 * t,  # ES1
        1.0 - 0.0010 * t,  # ES2
        1.0 + 0.0005 * t,  # ES3
        1.0 - 0.0005 * t,  # ES4
    ]
    return np.stack(cols, axis=1)


# ---------------------------------------------------------------------------
# 1. _compute_global_rf_unnorm — paper §IV-C r_f_global
# ---------------------------------------------------------------------------


def test_global_rf_zero_when_synchronous() -> None:
    """4 agents with identical omega ⇒ centered = 0 ⇒ r_f_global = 0 exactly."""
    trace = _make_synchronous_trace(omega_pu=1.001)  # all 0.05 Hz off, together
    assert _compute_global_rf_unnorm(trace, F_NOM) == 0.0


def test_global_rf_negative_for_asymmetric_trace() -> None:
    """Paper formula returns -Σ(centered²) ⇒ ≤ 0; asymmetric trace ⇒ < 0."""
    trace = _make_asymmetric_trace()
    assert _compute_global_rf_unnorm(trace, F_NOM) < 0.0


# ---------------------------------------------------------------------------
# 2. _compute_global_rf_per_agent — per-agent decomposition
# ---------------------------------------------------------------------------


def test_global_rf_per_agent_sums_to_global() -> None:
    """sum(per_agent) == global within float tolerance (decomposition law)."""
    trace = _make_asymmetric_trace()
    global_rf = _compute_global_rf_unnorm(trace, F_NOM)
    per_agent = _compute_global_rf_per_agent(trace, F_NOM)
    assert sum(per_agent) == pytest.approx(global_rf, abs=1e-12)


# ---------------------------------------------------------------------------
# 3. _compute_per_agent_max_abs_df — known-magnitude per-agent peaks
# ---------------------------------------------------------------------------


def test_max_abs_df_per_agent_distinct_for_distinct_traces() -> None:
    """Known per-agent peaks → known per-agent max|Δf| values, all distinct."""
    T, N = 5, 4
    trace = np.ones((T, N), dtype=np.float64)
    trace[2, 0] = 1.010  # ES1 |Δf| = 0.5 Hz
    trace[2, 1] = 1.020  # ES2 |Δf| = 1.0 Hz
    trace[2, 2] = 0.995  # ES3 |Δf| = 0.25 Hz
    trace[2, 3] = 0.985  # ES4 |Δf| = 0.75 Hz
    out = _compute_per_agent_max_abs_df(trace, F_NOM)
    assert out[0] == pytest.approx(0.5, abs=1e-12)
    assert out[1] == pytest.approx(1.0, abs=1e-12)
    assert out[2] == pytest.approx(0.25, abs=1e-12)
    assert out[3] == pytest.approx(0.75, abs=1e-12)
    assert len(set(out)) == 4


# ---------------------------------------------------------------------------
# 4. _compute_per_agent_nadir_peak — sign asymmetry
# ---------------------------------------------------------------------------


def test_per_agent_nadir_peak_sign_asymmetric() -> None:
    """ES1 only-positive excursion ⇒ nadir=0 / peak>0; ES2 only-negative ⇒ flipped."""
    T = 5
    trace = np.ones((T, 4), dtype=np.float64)
    trace[2, 0] = 1.010  # ES1: positive excursion only
    trace[2, 1] = 0.990  # ES2: negative excursion only
    nadir, peak = _compute_per_agent_nadir_peak(trace, F_NOM)
    assert nadir[0] == pytest.approx(0.0, abs=1e-12)
    assert peak[0] == pytest.approx(0.5, abs=1e-12)
    assert nadir[1] == pytest.approx(-0.5, abs=1e-12)
    assert peak[1] == pytest.approx(0.0, abs=1e-12)


# ---------------------------------------------------------------------------
# 5/6. _compute_per_agent_omega_summary — sha256 collapse detection
# ---------------------------------------------------------------------------


def test_omega_summary_sha256_distinct_for_distinct_traces() -> None:
    """4 unique trajectories ⇒ 4 distinct sha256 fingerprints."""
    trace = _make_asymmetric_trace()
    summary = _compute_per_agent_omega_summary(trace)
    assert len(summary) == 4
    assert len({s["sha256_16"] for s in summary}) == 4


def test_omega_summary_sha256_equal_for_aliased_traces() -> None:
    """Byte-identical columns ⇒ identical sha256 (collapse / aliasing detection)."""
    trace = _make_synchronous_trace()
    summary = _compute_per_agent_omega_summary(trace)
    assert len({s["sha256_16"] for s in summary}) == 1


# ---------------------------------------------------------------------------
# 7/8. _settling_time_s — converged vs oscillating
# ---------------------------------------------------------------------------


def test_settling_time_returns_value_when_settled() -> None:
    """Trace settles after step 5 ⇒ returns t = 5 * dt = 0.2 s."""
    T = 50
    trace = np.ones((T, 4), dtype=np.float64)
    trace[:5, :] = 1.001  # |Δf| = 0.05 Hz (ABOVE 5 mHz tol) for first 5 steps
    # remaining steps stay at 1.0 (|Δf| = 0)
    sett = _settling_time_s(trace, DT_S, F_NOM, tol_hz=0.005, window_s=1.0)
    assert sett is not None
    assert sett == pytest.approx(5 * DT_S, abs=1e-12)


def test_settling_time_returns_none_when_never_settled() -> None:
    """Persistent deviation above tolerance ⇒ never settles ⇒ None."""
    T = 50
    trace = np.ones((T, 4), dtype=np.float64)
    trace[:, 0] = 1.0 + 0.0002  # 0.01 Hz constant deviation > 0.005 tol
    sett = _settling_time_s(trace, DT_S, F_NOM, tol_hz=0.005, window_s=1.0)
    assert sett is None


# ---------------------------------------------------------------------------
# 9/10. _rocof_max — constant vs known-step
# ---------------------------------------------------------------------------


def test_rocof_zero_for_constant_trace() -> None:
    """Constant omega ⇒ d ω/dt = 0 ⇒ ROCOF = 0."""
    assert _rocof_max(_make_synchronous_trace(), DT_S, F_NOM) == 0.0


def test_rocof_max_for_known_step_trace() -> None:
    """Step Δω = 0.01 pu / dt = 0.04 s × 50 Hz = 12.5 Hz/s peak ROCOF."""
    T = 5
    trace = np.ones((T, 4), dtype=np.float64)
    trace[2:, 0] = 1.010  # 0.01 pu jump at step 2 in ES1
    rocof = _rocof_max(trace, DT_S, F_NOM)
    assert rocof == pytest.approx(12.5, abs=1e-12)


# ---------------------------------------------------------------------------
# 11. _compute_r_f_local_per_agent_eta1 — ring topology η=1
# ---------------------------------------------------------------------------


def test_r_f_local_per_agent_eta1_ring_topology_synchronous() -> None:
    """Synchronous trace ⇒ each agent's local mean = own value ⇒ all r_f_i = 0.

    Degenerate case (zeros). The asymmetric variant below pins the actual
    ring-topology math.
    """
    trace = _make_synchronous_trace()
    comm_adj = {0: [1, 3], 1: [0, 2], 2: [1, 3], 3: [2, 0]}
    out = _compute_r_f_local_per_agent_eta1(trace, F_NOM, comm_adj)
    assert all(v == 0.0 for v in out)


def test_r_f_local_per_agent_eta1_ring_topology_asymmetric() -> None:
    """Asymmetric trace + ring topology ⇒ r_f_i < 0 for all i, distinct values.

    Pins the non-degenerate path (review I4 follow-up): the synchronous test
    above only exercises the omega_bar = own branch trivially. This case
    forces the (own + neighbor sum) formula with non-zero centered values
    across a ring `comm_adj`, locking the Eq.15-16 implementation.
    """
    trace = _make_asymmetric_trace()
    comm_adj = {0: [1, 3], 1: [0, 2], 2: [1, 3], 3: [2, 0]}
    out = _compute_r_f_local_per_agent_eta1(trace, F_NOM, comm_adj)
    assert len(out) == 4
    assert all(v < 0.0 for v in out), f"asymmetric trace ⇒ all r_f_i < 0, got {out}"
    assert len(set(out)) >= 2, (
        f"ring topology + asymmetric ⇒ at least 2 distinct values, got {out}"
    )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_global_rf_handles_empty_trace() -> None:
    """Empty trace ⇒ 0.0 (defensive default)."""
    empty = np.empty((0, 4), dtype=np.float64)
    assert _compute_global_rf_unnorm(empty, F_NOM) == 0.0


def test_settling_time_handles_empty_trace() -> None:
    """Empty trace ⇒ None (cannot settle if no samples)."""
    empty = np.empty((0, 4), dtype=np.float64)
    assert _settling_time_s(empty, DT_S, F_NOM, 0.005, 1.0) is None


def test_is_finite_arr_detects_nan_inf() -> None:
    """_is_finite_arr returns False on NaN or Inf, True on clean arrays."""
    assert _is_finite_arr(np.array([1.0, 2.0, 3.0])) is True
    assert _is_finite_arr(np.array([1.0, np.nan])) is False
    assert _is_finite_arr(np.array([1.0, np.inf])) is False


# ---------------------------------------------------------------------------
# Empty-trace defensive branches (coverage padding for non-rf empty paths)
# ---------------------------------------------------------------------------


def test_per_agent_helpers_handle_empty_trace() -> None:
    """All per-agent helpers return sensible defaults on empty trace."""
    empty = np.empty((0, 4), dtype=np.float64)
    assert _compute_global_rf_per_agent(empty, F_NOM) == [0.0]
    assert _compute_per_agent_max_abs_df(empty, F_NOM) == [0.0]
    nadir, peak = _compute_per_agent_nadir_peak(empty, F_NOM)
    assert nadir == [0.0] and peak == [0.0]
    assert _compute_per_agent_omega_summary(empty) == []
    assert _compute_r_f_local_per_agent_eta1(empty, F_NOM, {}) == [0.0]


def test_rocof_returns_zero_for_single_step_trace() -> None:
    """T<2 ⇒ no diff possible ⇒ ROCOF defaults to 0."""
    single = np.ones((1, 4), dtype=np.float64)
    assert _rocof_max(single, DT_S, F_NOM) == 0.0


def test_r_f_local_handles_empty_neighbors() -> None:
    """Agent with no neighbors in comm_adj ⇒ omega_bar = own ⇒ r_f_i = 0."""
    trace = _make_asymmetric_trace()
    # Agent 0 isolated (no neighbors), agents 1-3 unconnected too
    out = _compute_r_f_local_per_agent_eta1(trace, F_NOM, {})
    assert out == [0.0, 0.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# Schema lock — dataclass field order is part of JSON contract
# ---------------------------------------------------------------------------


def test_per_episode_metrics_field_order_locked() -> None:
    """PerEpisodeMetrics field order is JSON schema contract (result_to_dict
    iterates fields() in declaration order). Lock against accidental
    reordering during refactor.
    """
    expected = [
        "scenario_idx",
        "proxy_bus",
        "magnitude_sys_pu",
        "n_steps",
        "max_freq_dev_hz",
        "rocof_max_hz_per_s",
        "nadir_hz",
        "peak_hz",
        "settling_time_s",
        "r_f_global_unnormalized",
        "r_f_local_total",
        "r_h_total",
        "r_d_total",
        "total_reward",
        "nan_inf_seen",
        "tds_failed",
        "r_f_global_per_agent",
        "max_abs_df_hz_per_agent",
        "nadir_hz_per_agent",
        "peak_hz_per_agent",
        "omega_trace_summary_per_agent",
        "r_f_local_per_agent_eta1",
    ]
    actual = [f.name for f in fields(PerEpisodeMetrics)]
    assert actual == expected, (
        f"PerEpisodeMetrics field order changed (impacts JSON schema):\n"
        f"  expected: {expected}\n"
        f"  actual:   {actual}"
    )


def test_eval_result_field_order_locked() -> None:
    """EvalResult field order is JSON schema contract."""
    expected = [
        "schema_version",
        "checkpoint_path",
        "policy_label",
        "n_scenarios",
        "seed_base",
        "cumulative_reward_global_rf",
        "per_episode_metrics",
        "summary",
        "figures",
        "omega_source_paths",
    ]
    actual = [f.name for f in fields(EvalResult)]
    assert actual == expected


# ---------------------------------------------------------------------------
# generate_scenarios — determinism + bus_choices respected
# ---------------------------------------------------------------------------


def test_generate_scenarios_deterministic_for_same_seed() -> None:
    """Same seed_base ⇒ identical scenario list."""
    s1 = generate_scenarios(
        n_scenarios=10, seed_base=42, dist_min=-0.5, dist_max=0.5
    )
    s2 = generate_scenarios(
        n_scenarios=10, seed_base=42, dist_min=-0.5, dist_max=0.5
    )
    assert s1 == s2


def test_generate_scenarios_respects_bus_choices() -> None:
    """All generated buses come from bus_choices; magnitudes within range."""
    bus_choices = (7, 9)
    scenarios = generate_scenarios(
        n_scenarios=20,
        seed_base=1,
        dist_min=-0.5,
        dist_max=0.5,
        bus_choices=bus_choices,
    )
    assert len(scenarios) == 20
    for s in scenarios:
        assert s["bus"] in bus_choices
        assert -0.5 <= s["magnitude_sys_pu"] <= 0.5


# ---------------------------------------------------------------------------
# P2a — _bootstrap_ci percentile-bootstrap mean + CI
# ---------------------------------------------------------------------------


def test_bootstrap_ci_empty_returns_zeros() -> None:
    """Empty input → defensive zeros + n=0 (does not raise)."""
    out = _bootstrap_ci([], n_resample=100, alpha=0.05, seed=0)
    assert out["mean"] == 0.0
    assert out["std"] == 0.0
    assert out["ci_lo"] == 0.0
    assert out["ci_hi"] == 0.0
    assert out["n"] == 0


def test_bootstrap_ci_singleton_has_zero_width() -> None:
    """Single value → CI lo == hi == that value (no spread to bootstrap)."""
    out = _bootstrap_ci([3.14], n_resample=100, alpha=0.05, seed=0)
    assert out["mean"] == pytest.approx(3.14)
    assert out["ci_lo"] == pytest.approx(3.14)
    assert out["ci_hi"] == pytest.approx(3.14)
    assert out["n"] == 1


def test_bootstrap_ci_reproducible_with_same_seed() -> None:
    """Same seed → byte-equal CI (reproducibility for cross-run audit)."""
    vals = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    a = _bootstrap_ci(vals, n_resample=200, alpha=0.05, seed=42)
    b = _bootstrap_ci(vals, n_resample=200, alpha=0.05, seed=42)
    assert a == b


def test_bootstrap_ci_different_seeds_give_different_results() -> None:
    """Different seeds produce different bootstrap distributions."""
    vals = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    a = _bootstrap_ci(vals, n_resample=200, alpha=0.05, seed=1)
    b = _bootstrap_ci(vals, n_resample=200, alpha=0.05, seed=2)
    # mean is exact (same input), but CI bounds are stochastic
    assert a["mean"] == b["mean"]
    assert (a["ci_lo"], a["ci_hi"]) != (b["ci_lo"], b["ci_hi"])


def test_bootstrap_ci_brackets_sample_mean() -> None:
    """For symmetric data, CI [lo, hi] should bracket the sample mean."""
    vals = list(range(1, 51))  # 1..50, mean = 25.5
    out = _bootstrap_ci(vals, n_resample=500, alpha=0.05, seed=0)
    assert out["ci_lo"] < out["mean"] < out["ci_hi"]
    assert out["mean"] == pytest.approx(25.5)


def test_bootstrap_ci_records_config_fields() -> None:
    """Output records n_resample / alpha / n for downstream auditing."""
    out = _bootstrap_ci([1.0, 2.0, 3.0], n_resample=123, alpha=0.10, seed=0)
    assert out["n_resample"] == 123
    assert out["alpha"] == 0.10
    assert out["n"] == 3
