"""Integration tests for evaluate_policy using a stub env (no MATLAB).

Plan §P-tests (2026-05-03): the runner-level helpers (P0c / P0b / P3a /
P0a / P2a) are tested in test_paper_eval_runner.py via direct unit
calls. The big remaining gap was ``evaluate_policy`` itself — its 200+
line per-episode loop with embedded scenario dispatch + reward
aggregation + per-agent metrics was untested. This file closes that
gap with a stub ``KundurSimulinkEnv`` that simulates the gym-style
``reset()`` / ``step()`` interface deterministically.

Stub returns synthetic omega traces driven by ``(scenario_idx,
agent_idx)`` so each (scenario, agent) cell has a distinct trajectory.
We then assert evaluate_policy:

- Runs end-to-end without exceptions on small n_scenarios
- Produces a ``summary`` dict with all P2a CI fields
- Produces a ``EvalResult`` with ``schema_version=3`` (post-P3b)
- Threads ``scenarios_override`` through correctly (manifest mode)
- Honors ``settle_tol_hz`` override (P3a)
- Is deterministic given identical inputs (no hidden RNG)
- Records per-episode r_f / r_h / r_d totals from info["reward_components"]
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from evaluation.metrics import EvalResult
from evaluation.paper_eval import (
    SETTLE_TOL_HZ,
    SETTLE_WINDOW_S,
    evaluate_policy,
    make_zero_action_selector,
)

pytestmark = pytest.mark.offline


# ---------------------------------------------------------------------------
# Stub env (deterministic, no MATLAB)
# ---------------------------------------------------------------------------


class _StubKundurEnv:
    """Minimal env stub matching the surface evaluate_policy uses.

    Surface required by evaluate_policy:
      - attrs: N_ESS, T_EPISODE, DT, _F_NOM
      - reset(seed, scenario, options) → (obs, info)
      - step(action) → (obs, reward, terminated, truncated, info)
        info must include 'omega' (np array shape (N,)),
        'reward_components' dict with r_f / r_h / r_d, and
        optional 'tds_failed' bool.

    Stub generates omega = 1.0 + 0.001 * t * (scenario_idx + 1) * (i + 1)
    so each (scenario, step, agent) cell has a distinct, reproducible
    value. Reward components are constant per step for simplicity.
    """

    N_ESS: int = 4
    T_EPISODE: float = 0.4  # 10 steps × 0.04s
    DT: float = 0.04
    _F_NOM: float = 50.0
    # PHI for runner_config (P0b path). Not used by evaluate_policy itself.
    _PHI_F: float = 100.0
    _PHI_H: float = 5e-4
    _PHI_D: float = 5e-4
    _PHI_H_PER_AGENT = None
    _PHI_D_PER_AGENT = None

    def __init__(self) -> None:
        self._scenario_idx: int = 0
        self._step: int = 0

    def reset(self, *, seed: int = 0, scenario: Any = None,
              options: Any = None) -> tuple[np.ndarray, dict]:
        # Extract scenario_idx for omega-trace shape (mirrors real env's
        # use of seed_base + 1009 * scenario_idx for determinism).
        if scenario is not None and hasattr(scenario, "scenario_idx"):
            self._scenario_idx = scenario.scenario_idx
        else:
            # Loadstep / option path: derive from seed (paper_eval does
            # seed=seed_base + 1009 * scenario_idx).
            self._scenario_idx = (seed - 42) // 1009 if seed >= 42 else 0
        self._step = 0
        obs = np.zeros((self.N_ESS, 4), dtype=np.float64)  # OBS_DIM=4 per agent
        return obs, {"reset_ok": True}

    def step(self, action: np.ndarray) -> tuple[np.ndarray, np.ndarray, bool, bool, dict]:
        self._step += 1
        # Synthetic omega: per-agent linear ramp scaled by scenario_idx.
        omega = np.array([
            1.0 + 0.001 * self._step * (self._scenario_idx + 1) * (i + 1)
            for i in range(self.N_ESS)
        ], dtype=np.float64)
        obs = np.zeros((self.N_ESS, 4), dtype=np.float64)
        reward = np.zeros(self.N_ESS, dtype=np.float64)
        info = {
            "omega": omega,
            "reward_components": {"r_f": -0.1, "r_h": -0.001, "r_d": -0.001},
            "tds_failed": False,
        }
        terminated = False
        truncated = False
        return obs, reward, terminated, truncated, info


# ---------------------------------------------------------------------------
# Smoke: evaluate_policy runs end-to-end on stub env
# ---------------------------------------------------------------------------


def test_evaluate_policy_smoke_runs_without_error() -> None:
    """Two-scenario zero-action run completes; result is well-formed."""
    env = _StubKundurEnv()
    select_fn = make_zero_action_selector(env.N_ESS, action_dim=2)
    result = evaluate_policy(
        env=env,
        n_scenarios=2,
        seed_base=42,
        policy_label="test_smoke",
        checkpoint_path=None,
        select_action_fn=select_fn,
        fnom=env._F_NOM,
        dt_s=env.DT,
        dist_min=-0.5,
        dist_max=0.5,
        bus_choices=(7, 9),
        scenarios_override=None,
        disturbance_mode="bus",
        settle_tol_hz=SETTLE_TOL_HZ,
        settle_window_s=SETTLE_WINDOW_S,
    )
    assert isinstance(result, EvalResult)
    assert result.n_scenarios == 2
    assert result.policy_label == "test_smoke"
    assert len(result.per_episode_metrics) == 2


def test_evaluate_policy_emits_schema_version_3() -> None:
    """Result has schema_version=3 (post-P3b rh_abs_share rename)."""
    env = _StubKundurEnv()
    result = evaluate_policy(
        env=env, n_scenarios=1, seed_base=42, policy_label="x",
        checkpoint_path=None,
        select_action_fn=make_zero_action_selector(env.N_ESS, 2),
        fnom=env._F_NOM, dt_s=env.DT,
        dist_min=-0.5, dist_max=0.5, bus_choices=(7, 9),
        scenarios_override=None, disturbance_mode="bus",
        settle_tol_hz=SETTLE_TOL_HZ, settle_window_s=SETTLE_WINDOW_S,
    )
    assert result.schema_version == 3


# ---------------------------------------------------------------------------
# Summary shape: all expected fields present
# ---------------------------------------------------------------------------


def test_evaluate_policy_summary_has_all_p2a_ci_fields() -> None:
    """Summary includes all 4 bootstrap CI fields added in P2a."""
    env = _StubKundurEnv()
    result = evaluate_policy(
        env=env, n_scenarios=3, seed_base=42, policy_label="x",
        checkpoint_path=None,
        select_action_fn=make_zero_action_selector(env.N_ESS, 2),
        fnom=env._F_NOM, dt_s=env.DT,
        dist_min=-0.5, dist_max=0.5, bus_choices=(7, 9),
        scenarios_override=None, disturbance_mode="bus",
        settle_tol_hz=SETTLE_TOL_HZ, settle_window_s=SETTLE_WINDOW_S,
    )
    s = result.summary
    for ci_field in ("max_freq_dev_hz_ci95", "rocof_hz_per_s_ci95",
                     "rh_abs_share_pct_ci95", "r_f_global_unnorm_ci95"):
        assert ci_field in s, f"missing P2a CI field: {ci_field}"
        ci = s[ci_field]
        for k in ("mean", "std", "ci_lo", "ci_hi", "n", "n_resample", "alpha"):
            assert k in ci, f"{ci_field} missing sub-key {k!r}"


def test_evaluate_policy_summary_uses_p3b_renamed_field() -> None:
    """rh_abs_share_pct_mean (P3b) present; legacy rh_share_pct_mean absent."""
    env = _StubKundurEnv()
    result = evaluate_policy(
        env=env, n_scenarios=2, seed_base=42, policy_label="x",
        checkpoint_path=None,
        select_action_fn=make_zero_action_selector(env.N_ESS, 2),
        fnom=env._F_NOM, dt_s=env.DT,
        dist_min=-0.5, dist_max=0.5, bus_choices=(7, 9),
        scenarios_override=None, disturbance_mode="bus",
        settle_tol_hz=SETTLE_TOL_HZ, settle_window_s=SETTLE_WINDOW_S,
    )
    assert "rh_abs_share_pct_mean" in result.summary
    assert "rh_share_pct_mean" not in result.summary


def test_evaluate_policy_per_episode_metrics_have_per_agent_fields() -> None:
    """Probe B per-agent decomposition fields populated per episode."""
    env = _StubKundurEnv()
    result = evaluate_policy(
        env=env, n_scenarios=2, seed_base=42, policy_label="x",
        checkpoint_path=None,
        select_action_fn=make_zero_action_selector(env.N_ESS, 2),
        fnom=env._F_NOM, dt_s=env.DT,
        dist_min=-0.5, dist_max=0.5, bus_choices=(7, 9),
        scenarios_override=None, disturbance_mode="bus",
        settle_tol_hz=SETTLE_TOL_HZ, settle_window_s=SETTLE_WINDOW_S,
    )
    for ep in result.per_episode_metrics:
        assert len(ep.r_f_global_per_agent) == env.N_ESS
        assert len(ep.max_abs_df_hz_per_agent) == env.N_ESS
        assert len(ep.nadir_hz_per_agent) == env.N_ESS
        assert len(ep.peak_hz_per_agent) == env.N_ESS
        assert len(ep.omega_trace_summary_per_agent) == env.N_ESS
        # per-agent omega summary: each entry has sha256 fingerprint
        for fp in ep.omega_trace_summary_per_agent:
            assert "sha256_16" in fp
            assert len(fp["sha256_16"]) == 16


# ---------------------------------------------------------------------------
# Determinism: same inputs → byte-equal output
# ---------------------------------------------------------------------------


def test_evaluate_policy_deterministic_for_same_inputs() -> None:
    """Two runs with identical inputs produce identical EvalResult.

    Catches accidental non-determinism (e.g., uninitialized RNG, hash
    randomization, undeclared global state).
    """
    def _run() -> EvalResult:
        env = _StubKundurEnv()
        return evaluate_policy(
            env=env, n_scenarios=2, seed_base=42, policy_label="det",
            checkpoint_path=None,
            select_action_fn=make_zero_action_selector(env.N_ESS, 2),
            fnom=env._F_NOM, dt_s=env.DT,
            dist_min=-0.5, dist_max=0.5, bus_choices=(7, 9),
            scenarios_override=None, disturbance_mode="bus",
            settle_tol_hz=SETTLE_TOL_HZ, settle_window_s=SETTLE_WINDOW_S,
        )
    a = _run()
    b = _run()
    # Spot-check key numeric fields.
    assert a.summary["max_freq_dev_hz_mean"] == b.summary["max_freq_dev_hz_mean"]
    assert a.summary["max_freq_dev_hz_ci95"] == b.summary["max_freq_dev_hz_ci95"]
    assert a.cumulative_reward_global_rf == b.cumulative_reward_global_rf
    # Per-episode r_f_global byte-equal.
    for ea, eb in zip(a.per_episode_metrics, b.per_episode_metrics):
        assert ea.r_f_global_unnormalized == eb.r_f_global_unnormalized
        assert ea.max_freq_dev_hz == eb.max_freq_dev_hz


# ---------------------------------------------------------------------------
# Manifest override: scenarios_override replaces inline RNG path
# ---------------------------------------------------------------------------


def test_evaluate_policy_uses_scenarios_override_when_provided() -> None:
    """Manifest mode: scenarios_override list controls the loop, not RNG."""
    env = _StubKundurEnv()
    override = [
        {"scenario_idx": 0, "bus": 7, "magnitude_sys_pu": 0.3},
        {"scenario_idx": 1, "bus": 9, "magnitude_sys_pu": -0.2},
        {"scenario_idx": 2, "bus": 7, "magnitude_sys_pu": 0.1},
    ]
    result = evaluate_policy(
        env=env, n_scenarios=999,  # ignored (overridden by len(override))
        seed_base=42, policy_label="manifest",
        checkpoint_path=None,
        select_action_fn=make_zero_action_selector(env.N_ESS, 2),
        fnom=env._F_NOM, dt_s=env.DT,
        dist_min=-0.5, dist_max=0.5, bus_choices=(7, 9),
        scenarios_override=override, disturbance_mode="bus",
        settle_tol_hz=SETTLE_TOL_HZ, settle_window_s=SETTLE_WINDOW_S,
    )
    assert result.n_scenarios == 3
    # Per-episode metrics record the overridden bus + magnitude.
    assert [ep.proxy_bus for ep in result.per_episode_metrics] == [7, 9, 7]
    assert [ep.magnitude_sys_pu for ep in result.per_episode_metrics] \
        == pytest.approx([0.3, -0.2, 0.1])


# ---------------------------------------------------------------------------
# settle_tol_hz override (P3a) flows into per-episode settling time calc
# ---------------------------------------------------------------------------


def test_evaluate_policy_settle_tol_override_changes_settling_classification() -> None:
    """Tighter tol_hz → fewer episodes settle (synthetic omega exceeds tol)."""
    env = _StubKundurEnv()
    common = dict(
        n_scenarios=3, seed_base=42, policy_label="x",
        checkpoint_path=None,
        select_action_fn=make_zero_action_selector(env.N_ESS, 2),
        fnom=env._F_NOM, dt_s=env.DT,
        dist_min=-0.5, dist_max=0.5, bus_choices=(7, 9),
        scenarios_override=None, disturbance_mode="bus",
        settle_window_s=SETTLE_WINDOW_S,
    )
    loose = evaluate_policy(env=env, settle_tol_hz=1.0, **common)
    env2 = _StubKundurEnv()  # fresh env so step counters reset
    tight = evaluate_policy(env=env2, settle_tol_hz=1e-9, **common)
    # Loose tol → more episodes count as settled.
    assert loose.summary["settled_pct"] >= tight.summary["settled_pct"]
    # Tight tol on this synthetic ramp → never settled (None mean).
    assert tight.summary["settled_time_s_mean"] is None


# ---------------------------------------------------------------------------
# Reward component aggregation
# ---------------------------------------------------------------------------


def test_evaluate_policy_aggregates_reward_components_from_info() -> None:
    """Per-episode r_f / r_h / r_d totals = sum of info['reward_components']."""
    env = _StubKundurEnv()
    result = evaluate_policy(
        env=env, n_scenarios=1, seed_base=42, policy_label="x",
        checkpoint_path=None,
        select_action_fn=make_zero_action_selector(env.N_ESS, 2),
        fnom=env._F_NOM, dt_s=env.DT,
        dist_min=-0.5, dist_max=0.5, bus_choices=(7, 9),
        scenarios_override=None, disturbance_mode="bus",
        settle_tol_hz=SETTLE_TOL_HZ, settle_window_s=SETTLE_WINDOW_S,
    )
    ep = result.per_episode_metrics[0]
    n_steps = ep.n_steps
    # Stub returns r_f=-0.1, r_h=-0.001, r_d=-0.001 every step.
    assert ep.r_f_local_total == pytest.approx(-0.1 * n_steps)
    assert ep.r_h_total == pytest.approx(-0.001 * n_steps)
    assert ep.r_d_total == pytest.approx(-0.001 * n_steps)


# ---------------------------------------------------------------------------
# Cumulative + paper baseline accounting
# ---------------------------------------------------------------------------


def test_evaluate_policy_cumulative_includes_paper_baselines() -> None:
    """cumulative_reward_global_rf includes paper targets + delta calcs."""
    env = _StubKundurEnv()
    result = evaluate_policy(
        env=env, n_scenarios=2, seed_base=42, policy_label="x",
        checkpoint_path=None,
        select_action_fn=make_zero_action_selector(env.N_ESS, 2),
        fnom=env._F_NOM, dt_s=env.DT,
        dist_min=-0.5, dist_max=0.5, bus_choices=(7, 9),
        scenarios_override=None, disturbance_mode="bus",
        settle_tol_hz=SETTLE_TOL_HZ, settle_window_s=SETTLE_WINDOW_S,
    )
    cum = result.cumulative_reward_global_rf
    assert "unnormalized" in cum
    assert "per_M" in cum
    assert "per_M_per_N" in cum
    assert cum["paper_target_unnormalized"] == -8.04
    assert cum["paper_no_control_unnormalized"] == -15.20
    assert "vs_ddic_unnorm" in cum["deltas_vs_paper"]
