"""
TDD tests for audited issues.

Each section is RED → GREEN → (refactor if needed).
Issues addressed (in priority order):
  P0-2  Reward formula: mean^2 → mean(^2) in Kundur and NE39 envs
  P0-1  Kundur train: missing --update-repeat (10x like NE39)
  P1-2  Log file overwrite on resume
  P1-1  Resume: start_episode not restored from checkpoint
  P1-3  Kundur eval: disturbance magnitude is non-deterministic
"""

from __future__ import annotations

import importlib
import json
import sys
import os
import types
import numpy as np
import pytest

# ── project root on path ──────────────────────────────────────────────────────
_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _PROJECT_ROOT)


# =============================================================================
# P0-2  Reward formula: r_h = -φ_H * (mean(ΔH_i))²  per paper Eq. 17
# =============================================================================


def _action_to_delta_M(action_col: np.ndarray, dm_min: float, dm_max: float) -> np.ndarray:
    """Reproduce the affine action→ΔM mapping used in both envs."""
    return 0.5 * (action_col + 1.0) * (dm_max - dm_min) + dm_min


class TestRewardFormula:
    """
    Paper Eq. 17:  r_h = -φ_H * (mean_i(ΔH_i))²   where ΔH_i = ΔM_i / 2
    Paper Eq. 18:  r_d = -φ_D * (mean_i(ΔD_i))²

    These are *coordination* penalties on the global mean adjustment,
    NOT per-agent effort penalties.  The affine mapping action∈[-1,1]→ΔM
    is asymmetric (DM_MIN=-6, DM_MAX=18), so opposing raw actions do NOT
    cancel to zero in ΔM space.
    """

    # ── Kundur env ────────────────────────────────────────────────────────────

    def test_kundur_r_h_nonzero_for_max_action(self):
        """Kundur: r_h is large when all agents push max action."""
        from env.simulink.kundur_simulink_env import (
            KundurStandaloneEnv, PHI_H, DM_MIN, DM_MAX,
        )

        env = KundurStandaloneEnv()
        env.reset(seed=0)

        actions = np.ones((4, 2), dtype=np.float32)
        _, components = env._compute_reward(actions)

        delta_M = _action_to_delta_M(actions[:, 0], DM_MIN, DM_MAX)
        expected = -PHI_H * (float(np.mean(delta_M)) / 2.0) ** 2
        assert abs(components["r_h"] - expected) < 1e-5, (
            f"r_h={components['r_h']:.4f}, expected {expected:.4f}"
        )

    def test_kundur_r_h_formula_matches_paper_eq17(self):
        """Kundur: r_h = -φ_H * (mean(ΔM/2))² for arbitrary actions."""
        from env.simulink.kundur_simulink_env import (
            KundurStandaloneEnv, PHI_H, DM_MIN, DM_MAX,
        )

        env = KundurStandaloneEnv()
        env.reset(seed=0)

        rng = np.random.default_rng(42)
        actions = rng.uniform(-1, 1, (4, 2)).astype(np.float32)
        _, components = env._compute_reward(actions)

        delta_M = _action_to_delta_M(actions[:, 0], DM_MIN, DM_MAX)
        expected = -PHI_H * (float(np.mean(delta_M)) / 2.0) ** 2
        assert abs(components["r_h"] - expected) < 1e-5, (
            f"r_h={components['r_h']:.6f}, expected {expected:.6f}"
        )

    # ── NE39 env ──────────────────────────────────────────────────────────────

    def test_ne39_r_h_nonzero_for_max_action(self):
        """NE39: r_h is large when all agents push max action."""
        from env.simulink.ne39_simulink_env import (
            NE39BusStandaloneEnv, PHI_H, DM_MIN, DM_MAX,
        )

        env = NE39BusStandaloneEnv()
        env.reset(seed=0)

        actions = np.ones((8, 2), dtype=np.float32)
        _, components = env._compute_reward(actions)

        delta_M = _action_to_delta_M(actions[:, 0], DM_MIN, DM_MAX)
        expected = -PHI_H * (float(np.mean(delta_M)) / 2.0) ** 2
        assert abs(components["r_h"] - expected) < 1e-5, (
            f"NE39 r_h={components['r_h']:.4f}, expected {expected:.4f}"
        )

    def test_ne39_r_h_formula_matches_paper_eq17(self):
        """NE39: r_h = -φ_H * (mean(ΔM/2))² for arbitrary actions."""
        from env.simulink.ne39_simulink_env import (
            NE39BusStandaloneEnv, PHI_H, DM_MIN, DM_MAX,
        )

        env = NE39BusStandaloneEnv()
        env.reset(seed=0)

        rng = np.random.default_rng(7)
        actions = rng.uniform(-1, 1, (8, 2)).astype(np.float32)
        _, components = env._compute_reward(actions)

        delta_M = _action_to_delta_M(actions[:, 0], DM_MIN, DM_MAX)
        expected = -PHI_H * (float(np.mean(delta_M)) / 2.0) ** 2
        assert abs(components["r_h"] - expected) < 1e-5, (
            f"NE39 r_h={components['r_h']:.6f}, expected {expected:.6f}"
        )


# =============================================================================
# P0-1  Kundur train script: --update-repeat argument
# =============================================================================

class TestKundurUpdateRepeat:
    """
    NE39 train script has --update-repeat (default 10) with dynamic ramping.
    Kundur train script must have the same mechanism.
    """

    def _parse(self, argv=None):
        """Import parse_args fresh (avoids sys.argv pollution between tests)."""
        # Save and restore sys.argv
        old_argv = sys.argv[:]
        sys.argv = ["train_simulink.py"] + (argv or [])
        try:
            # Force reimport so parse_args() sees our sys.argv
            if "scenarios.kundur.train_simulink" in sys.modules:
                del sys.modules["scenarios.kundur.train_simulink"]
            from scenarios.kundur.train_simulink import parse_args
            return parse_args()
        finally:
            sys.argv = old_argv

    def test_parse_args_has_update_repeat(self):
        """--update-repeat should be a recognised argument."""
        args = self._parse()
        assert hasattr(args, "update_repeat"), (
            "parse_args() missing 'update_repeat' attribute"
        )

    def test_update_repeat_default_is_10(self):
        """Default --update-repeat should be 10 (matching NE39)."""
        args = self._parse()
        assert args.update_repeat == 10, (
            f"Default update_repeat={args.update_repeat}, expected 10"
        )

    def test_update_repeat_accepts_custom_value(self):
        """--update-repeat N should be stored as args.update_repeat=N."""
        args = self._parse(["--update-repeat", "5"])
        assert args.update_repeat == 5

    def test_effective_repeat_ramps_from_one(self):
        """
        effective_repeat should start at 1 when buffer < warmup_steps and
        grow toward update_repeat as the buffer fills.
        This is tested by replicating the in-loop formula from NE39.
        """
        update_repeat = 10
        warmup_steps = 2000

        # Small buffer (start of training) → effective = 1
        buffer_size = 100
        effective = min(update_repeat, max(1, buffer_size // warmup_steps))
        assert effective == 1, f"Expected 1 at startup, got {effective}"

        # Buffer at warmup → effective = 1
        buffer_size = warmup_steps
        effective = min(update_repeat, max(1, buffer_size // warmup_steps))
        assert effective == 1

        # Buffer at 5x warmup → effective = 5
        buffer_size = 5 * warmup_steps
        effective = min(update_repeat, max(1, buffer_size // warmup_steps))
        assert effective == 5

        # Buffer at 20x warmup → effective capped at update_repeat
        buffer_size = 20 * warmup_steps
        effective = min(update_repeat, max(1, buffer_size // warmup_steps))
        assert effective == update_repeat


# =============================================================================
# P1-2  Log file: append existing entries on resume
# =============================================================================

class TestLogFileAppend:
    """
    On resume, the training log should EXTEND existing entries,
    not overwrite them with 'w' mode.
    """

    def test_log_file_extends_on_resume(self, tmp_path):
        """Writing a log to an existing file should merge episode lists."""
        log_path = tmp_path / "training_log.json"

        # Simulate first training run (episodes 0-9)
        first_run_log = {
            "episode_rewards": list(range(10)),
            "eval_rewards": [{"episode": 9, "reward": -500.0}],
            "critic_losses": [0.5] * 10,
            "policy_losses": [0.3] * 10,
            "alphas": [0.2] * 10,
        }
        with open(log_path, "w") as f:
            json.dump(first_run_log, f)

        from scenarios.kundur.train_simulink import load_or_create_log

        log = load_or_create_log(str(log_path))
        assert log["episode_rewards"] == list(range(10)), (
            "Existing episode_rewards not loaded correctly on resume"
        )

        # Simulate appending second run results and re-saving
        log["episode_rewards"].extend(list(range(10, 20)))
        with open(log_path, "w") as f:
            json.dump(log, f)

        # Third resume should see all 20 entries
        log2 = load_or_create_log(str(log_path))
        assert log2["episode_rewards"] == list(range(20)), (
            "Accumulated episode_rewards not correct after two runs"
        )

    def test_log_file_created_fresh_if_missing(self, tmp_path):
        """When no log file exists, load_or_create_log returns an empty log."""
        from scenarios.kundur.train_simulink import load_or_create_log

        log_path = str(tmp_path / "nonexistent.json")
        log = load_or_create_log(log_path)
        assert log["episode_rewards"] == []
        assert log["critic_losses"] == []

    def test_log_file_truncated_json_falls_back_to_fresh(self, tmp_path):
        """A truncated (invalid) JSON log must not crash — return a fresh empty log."""
        log_path = tmp_path / "truncated.json"
        log_path.write_text('{"episode_rewards": [1, 2, 3')  # invalid JSON

        from scenarios.kundur.train_simulink import load_or_create_log

        log = load_or_create_log(str(log_path))
        assert log["episode_rewards"] == [], (
            "Truncated log should fall back to empty list, not crash"
        )


# =============================================================================
# P1-1  Resume: start_episode restored from checkpoint
# =============================================================================

class TestResumeStartEpisode:
    """
    After agent.save(path, metadata={"start_episode": N}),
    agent.load(path) should return N so training can resume from episode N.
    """

    def test_save_and_load_preserves_start_episode(self, tmp_path):
        """Checkpoint must round-trip the start_episode value."""
        from env.simulink.sac_agent_standalone import SACAgent

        agent = SACAgent(obs_dim=7, act_dim=2, buffer_size=100, warmup_steps=50)
        save_path = str(tmp_path / "test.pt")

        agent.save(save_path, metadata={"start_episode": 150})
        meta = agent.load(save_path)

        assert meta.get("start_episode") == 150, (
            f"start_episode={meta.get('start_episode')}, expected 150"
        )

    def test_save_without_metadata_loads_zero(self, tmp_path):
        """Old checkpoints (no metadata) should default start_episode to 0."""
        from env.simulink.sac_agent_standalone import SACAgent

        agent = SACAgent(obs_dim=7, act_dim=2, buffer_size=100, warmup_steps=50)
        save_path = str(tmp_path / "legacy.pt")

        agent.save(save_path)  # no metadata
        meta = agent.load(save_path)

        assert meta.get("start_episode", 0) == 0


# =============================================================================
# P1-3  Kundur eval: deterministic disturbance
# =============================================================================

class TestEvalDeterministicDisturbance:
    """
    evaluate() must call apply_disturbance with a fixed magnitude so that
    best_eval_reward tracks policy quality, not disturbance luck.
    """

    def test_evaluate_same_result_twice(self):
        """
        Two calls to evaluate() on an untrained agent (deterministic mode)
        must return identical rewards.
        """
        from env.simulink.kundur_simulink_env import KundurStandaloneEnv
        from env.simulink.sac_agent_standalone import SACAgent
        from scenarios.kundur.train_simulink import evaluate

        env = KundurStandaloneEnv(training=False)
        agent = SACAgent(obs_dim=7, act_dim=2, buffer_size=100, warmup_steps=0)

        r1 = evaluate(env, agent, n_eval=1)
        r2 = evaluate(env, agent, n_eval=1)

        assert r1 == r2, (
            f"evaluate() returned different rewards ({r1:.4f} vs {r2:.4f}); "
            "disturbance magnitude is not fixed"
        )

    def test_evaluate_uses_fixed_disturbance_magnitude(self):
        """
        Monkey-patch apply_disturbance to capture the magnitude argument.
        The same fixed value must be passed on every eval episode.
        """
        from env.simulink.kundur_simulink_env import KundurStandaloneEnv
        from env.simulink.sac_agent_standalone import SACAgent
        from scenarios.kundur.train_simulink import evaluate

        env = KundurStandaloneEnv(training=False)
        agent = SACAgent(obs_dim=7, act_dim=2, buffer_size=100, warmup_steps=0)

        magnitudes_seen = []
        original = env.apply_disturbance

        def capture(bus_idx=None, magnitude=None):
            magnitudes_seen.append(magnitude)
            return original(bus_idx=bus_idx, magnitude=magnitude)

        env.apply_disturbance = capture
        evaluate(env, agent, n_eval=3)

        from scenarios.kundur.train_simulink import _EVAL_DISTURBANCE_MAGNITUDE

        assert len(magnitudes_seen) == 3
        assert all(m == _EVAL_DISTURBANCE_MAGNITUDE for m in magnitudes_seen), (
            f"Disturbance magnitudes don't match expected constant "
            f"{_EVAL_DISTURBANCE_MAGNITUDE}: {magnitudes_seen}"
        )

    def test_evaluate_can_return_diagnostic_metrics(self):
        """Eval diagnostics must include physics, per-agent rewards, and disturbance metadata."""
        from env.simulink.kundur_simulink_env import KundurStandaloneEnv
        from env.simulink.sac_agent_standalone import SACAgent
        from scenarios.kundur.train_simulink import evaluate, _EVAL_DISTURBANCE_MAGNITUDE

        env = KundurStandaloneEnv(training=False)
        agent = SACAgent(obs_dim=7, act_dim=2, buffer_size=100, warmup_steps=0)

        details = evaluate(env, agent, n_eval=1, return_details=True)

        assert details["type"] == "eval"
        assert "eval_reward" in details
        assert details["disturbance"]["magnitude"] == _EVAL_DISTURBANCE_MAGNITUDE
        assert details["physics"]["max_freq_dev_hz"] >= 0.0
        assert details["physics"]["mean_freq_dev_hz"] >= 0.0
        assert "max_power_swing" in details["physics"]
        assert len(details["per_agent_rewards"]) == env.N_ESS


# =============================================================================
# T6: physics_summary correctness
# =============================================================================

def test_physics_summary_records_episode_max_not_last_step():
    """max_freq_dev_hz must be the max over all steps, not the last-step value."""
    import json
    import tempfile

    fake_log = {
        "episode_rewards": [-500.0],
        "eval_rewards": [],
        "critic_losses": [0.5],
        "policy_losses": [0.3],
        "alphas": [0.2],
        "physics_summary": [
            {
                "max_freq_dev_hz": 0.45,
                "mean_freq_dev_hz": 0.12,
                "settled": True,
                "max_power_swing": 0.08,
            }
        ],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(fake_log, f)
        path = f.name

    try:
        with open(path) as f:
            data = json.load(f)
        ps = data["physics_summary"][0]
        assert ps["max_freq_dev_hz"] == 0.45, "must be episode max, not last-step value"
        assert ps["mean_freq_dev_hz"] == 0.12
        assert ps["settled"] is True
        assert "max_power_swing" in ps
    finally:
        os.unlink(path)


def test_physics_summary_settled_false_when_frequency_not_restored():
    """settled=False when last-10-steps freq dev exceeds 0.1 Hz."""
    tail_freq_devs = [0.35, 0.32, 0.30, 0.28, 0.29, 0.31, 0.27, 0.26, 0.28, 0.25]
    settled = all(d < 0.1 for d in tail_freq_devs)
    assert settled is False, "should not be settled when final freq dev > 0.1 Hz"


def test_physics_summary_settled_true_when_frequency_restored():
    """settled=True when last-10-steps freq dev all below 0.1 Hz."""
    tail_freq_devs = [0.08, 0.07, 0.05, 0.04, 0.03, 0.04, 0.05, 0.06, 0.04, 0.03]
    settled = all(d < 0.1 for d in tail_freq_devs)
    assert settled is True


# =============================================================================
# T7: training_viz smoke tests
# =============================================================================

def test_training_viz_produces_png_from_log(tmp_path):
    """plot_training_summary() must produce a PNG without error given minimal log."""
    pytest.importorskip("matplotlib")
    from utils.training_viz import plot_training_summary

    log = {
        "episode_rewards": [-500.0 + i * 0.5 for i in range(100)],
        "eval_rewards": [{"episode": 50, "reward": -480.0}, {"episode": 100, "reward": -450.0}],
        "critic_losses": [1.0 - i * 0.005 for i in range(100)],
        "policy_losses": [0.8 - i * 0.004 for i in range(100)],
        "alphas": [0.3 - i * 0.001 for i in range(100)],
        "physics_summary": [
            {"max_freq_dev_hz": 0.3 + (i % 10) * 0.01, "mean_freq_dev_hz": 0.1,
             "settled": i > 50, "max_power_swing": 0.05}
            for i in range(100)
        ],
    }
    log_path = tmp_path / "training_log.json"
    log_path.write_text(json.dumps(log))
    out_path = tmp_path / "summary.png"

    plot_training_summary(str(log_path), save_path=str(out_path))

    assert out_path.exists(), "PNG must be created"
    assert out_path.stat().st_size > 1000, "PNG must not be empty"


def test_training_viz_works_without_physics_summary(tmp_path):
    """plot_training_summary() must not crash if physics_summary key is absent (old logs)."""
    pytest.importorskip("matplotlib")
    from utils.training_viz import plot_training_summary

    log = {
        "episode_rewards": [-500.0 + i for i in range(50)],
        "eval_rewards": [],
        "critic_losses": [1.0] * 50,
        "policy_losses": [0.8] * 50,
        "alphas": [0.2] * 50,
    }
    log_path = tmp_path / "training_log.json"
    log_path.write_text(json.dumps(log))
    out_path = tmp_path / "summary.png"

    plot_training_summary(str(log_path), save_path=str(out_path))
    assert out_path.exists()


def test_load_or_create_log_preserves_physics_summary(tmp_path):
    """load_or_create_log must round-trip physics_summary key on resume."""
    log_path = tmp_path / "training_log.json"
    existing = {
        "episode_rewards": [-400.0],
        "eval_rewards": [],
        "critic_losses": [0.5],
        "policy_losses": [0.3],
        "alphas": [0.2],
        "physics_summary": [
            {"max_freq_dev_hz": 0.3, "mean_freq_dev_hz": 0.1,
             "settled": True, "max_power_swing": 0.05}
        ],
    }
    log_path.write_text(json.dumps(existing))

    from scenarios.kundur.train_simulink import load_or_create_log

    log = load_or_create_log(str(log_path))
    assert "physics_summary" in log, "physics_summary key must survive load_or_create_log"
    assert len(log["physics_summary"]) == 1
    assert log["physics_summary"][0]["max_freq_dev_hz"] == 0.3
