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
    """Tighter tol_hz → fewer episodes settle (synthetic omega exceeds tol).

    Uses ``settle_window_s=0.1`` (= 2 steps at dt=0.04) so the loose-tol
    path can actually count early steps as settled within a 10-step
    episode. The default ``SETTLE_WINDOW_S=1.0`` would be 25 steps and
    never trigger on a 10-step trace — making this test vacuous (both
    loose and tight would return None for all episodes).

    Per code reviewer feedback (I-1, 2026-05-03 follow-up commit): with
    the original window=1.0s, both ``loose.settled_pct`` and
    ``tight.settled_pct`` were 0.0 and the inequality was satisfied
    trivially without exercising the tol_hz parameter.
    """
    env = _StubKundurEnv()
    common = dict(
        n_scenarios=3, seed_base=42, policy_label="x",
        checkpoint_path=None,
        select_action_fn=make_zero_action_selector(env.N_ESS, 2),
        fnom=env._F_NOM, dt_s=env.DT,
        dist_min=-0.5, dist_max=0.5, bus_choices=(7, 9),
        scenarios_override=None, disturbance_mode="bus",
        settle_window_s=0.1,  # 2 steps at dt=0.04 — fits inside 10-step episode
    )
    loose = evaluate_policy(env=env, settle_tol_hz=1.0, **common)
    env2 = _StubKundurEnv()  # fresh env so step counters reset
    tight = evaluate_policy(env=env2, settle_tol_hz=1e-9, **common)
    # Synthetic ramp |Δf|_max(t) = 0.05 * t * (scenario_idx+1) * 4 Hz.
    # Loose tol=1.0 Hz with window=0.1s (2 steps):
    #   - scenario 0 (s+1=1): t=1→0.20, t=2→0.40 → window [T,T] → settles at t=0
    #   - scenario 1 (s+1=2): t=1→0.40, t=2→0.80 → window [T,T] → settles at t=0
    #   - scenario 2 (s+1=3): t=1→0.60, t=2→1.20 → window [T,F] → never
    # Expected: loose.settled_pct ≈ 66.67% (2/3); tight.settled_pct = 0% (none).
    assert loose.summary["settled_pct"] > tight.summary["settled_pct"], (
        f"loose tol should settle more episodes than tight: "
        f"loose={loose.summary['settled_pct']}, "
        f"tight={tight.summary['settled_pct']}"
    )
    assert loose.summary["settled_pct"] > 0.0, (
        f"loose tol failed to settle any scenario: "
        f"settled_pct={loose.summary['settled_pct']}"
    )
    assert tight.summary["settled_pct"] == 0.0
    assert tight.summary["settled_time_s_mean"] is None
    # Loose-tol settlers all converge at t=0 (first window), so the mean
    # settling time across settlers is 0.0s.
    assert loose.summary["settled_time_s_mean"] == pytest.approx(0.0)


def test_evaluate_policy_handles_early_termination(monkeypatch) -> None:
    """terminated=True mid-episode → loop breaks; per-ep n_steps reflects
    actual run length, not steps_per_ep_expected.

    Per code reviewer feedback (I-2, 2026-05-03 follow-up): the default
    stub never terminates, so the early-break branch in evaluate_policy
    (`if terminated or truncated: break`) was untested. This stub
    subclass terminates after step 5; the resulting per-episode metric
    should record n_steps=5 (not the full 10-step expected length).
    """
    class _EarlyTermStub(_StubKundurEnv):
        TERMINATE_AT_STEP: int = 5

        def step(self, action):
            obs, reward, _, _, info = super().step(action)
            terminated = self._step >= self.TERMINATE_AT_STEP
            return obs, reward, terminated, False, info

    env = _EarlyTermStub()
    result = evaluate_policy(
        env=env, n_scenarios=2, seed_base=42, policy_label="x",
        checkpoint_path=None,
        select_action_fn=make_zero_action_selector(env.N_ESS, 2),
        fnom=env._F_NOM, dt_s=env.DT,
        dist_min=-0.5, dist_max=0.5, bus_choices=(7, 9),
        scenarios_override=None, disturbance_mode="bus",
        settle_tol_hz=SETTLE_TOL_HZ, settle_window_s=SETTLE_WINDOW_S,
    )
    expected_steps_full = int(round(env.T_EPISODE / env.DT))  # 10
    assert expected_steps_full == 10
    for ep in result.per_episode_metrics:
        # Step 5 returns terminated=True → loop appended that step's omega
        # then broke; n_steps == 5 (not 10).
        assert ep.n_steps == 5, (
            f"early-termination stub returned n_steps={ep.n_steps}, "
            f"expected 5 (terminated at step 5)"
        )
        # Defensive zeros from helpers shouldn't trigger — n_steps > 0
        # branch should run in evaluate_policy.
        assert ep.r_f_global_unnormalized != 0.0 or all(
            o == 0.0 for o in ep.r_f_global_per_agent
        )  # not strict, just sanity


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
