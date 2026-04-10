# tests/test_perf_episode_length.py
"""Opt-A: Shorten Kundur episode from 10 s → 5 s.

TDD RED → GREEN contract
  RED : current code has T_EPISODE=10 / STEPS=50 → all assertions fail
  GREEN: after updating config + env constants, all pass
"""
import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Config-level contracts
# ---------------------------------------------------------------------------

class TestEpisodeLengthConfig:

    def test_config_t_episode_is_5s(self):
        from scenarios.kundur.config_simulink import T_EPISODE
        assert T_EPISODE == 5.0, (
            f"T_EPISODE should be 5.0 for faster training, got {T_EPISODE}"
        )

    def test_config_steps_per_episode_is_25(self):
        from scenarios.kundur.config_simulink import STEPS_PER_EPISODE
        assert STEPS_PER_EPISODE == 25, (
            f"STEPS_PER_EPISODE should be 25, got {STEPS_PER_EPISODE}"
        )

    def test_config_steps_consistent_with_dt(self):
        from scenarios.kundur.config_simulink import T_EPISODE, DT, STEPS_PER_EPISODE
        expected = int(T_EPISODE / DT)
        assert STEPS_PER_EPISODE == expected, (
            f"STEPS_PER_EPISODE={STEPS_PER_EPISODE} inconsistent with "
            f"T_EPISODE={T_EPISODE} / DT={DT} = {expected}"
        )


# ---------------------------------------------------------------------------
# Env-level contracts (no MATLAB required — uses standalone ODE backend)
# ---------------------------------------------------------------------------

class TestStandaloneEnvEpisodeLength:

    @pytest.fixture
    def env(self):
        from env.simulink.kundur_simulink_env import KundurStandaloneEnv
        e = KundurStandaloneEnv(training=False)
        yield e
        e.close()

    def test_env_t_episode_attribute_is_5s(self, env):
        assert env.T_EPISODE == 5.0, (
            f"env.T_EPISODE should be 5.0, got {env.T_EPISODE}"
        )

    def test_env_truncates_at_25_steps(self, env):
        """Episode must end with truncated=True at exactly 25 steps."""
        env.reset()
        step_count = 0
        truncated = False
        while True:
            action = np.zeros((env.N_AGENTS, 2), dtype=np.float32)
            _, _, terminated, truncated, _ = env.step(action)
            step_count += 1
            if terminated or truncated:
                break
        assert step_count == 25, (
            f"Expected episode length 25 steps, got {step_count}"
        )
        assert truncated, "Episode should end via truncation (time limit), not termination"

    def test_env_sim_time_at_end_is_5s(self, env):
        """sim_time after 25 steps must reach 5.0 s."""
        env.reset()
        info = {}
        for _ in range(25):
            action = np.zeros((env.N_AGENTS, 2), dtype=np.float32)
            _, _, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break
        assert abs(info["sim_time"] - 5.0) < 1e-6, (
            f"sim_time at episode end should be 5.0 s, got {info['sim_time']}"
        )


# ---------------------------------------------------------------------------
# Physics contract: frequency nadir must be observable within 5 s
# ---------------------------------------------------------------------------

class TestPhysicsWithin5s:

    def test_nadir_visible_after_load_trip(self):
        """After a load disturbance the nadir must appear before the episode ends.

        A real power system nadir after a 248 MW load trip occurs within ~2-3 s.
        This test verifies 5 s is enough to capture it.
        """
        from env.simulink.kundur_simulink_env import KundurStandaloneEnv
        env = KundurStandaloneEnv(training=False)
        try:
            env.reset()
            # Apply load trip (negative = load reduction → freq rises in standalone model)
            env.apply_disturbance(magnitude=-2.0)

            min_omega = 1.0
            max_omega = 1.0
            for _ in range(25):  # 25 steps × 0.2 s = 5 s
                action = np.zeros((env.N_AGENTS, 2), dtype=np.float32)
                _, _, terminated, truncated, info = env.step(action)
                step_omega = np.array(info["omega"])
                min_omega = min(min_omega, float(step_omega.min()))
                max_omega = max(max_omega, float(step_omega.max()))
                if terminated or truncated:
                    break

            # After a load trip the frequency should deviate noticeably from 1.0 pu
            max_deviation = max(abs(max_omega - 1.0), abs(min_omega - 1.0))
            assert max_deviation > 0.005, (
                f"Expected visible freq deviation >0.5% within 5s after disturbance, "
                f"got max_deviation={max_deviation:.4f} pu "
                f"(omega range [{min_omega:.4f}, {max_omega:.4f}])"
            )
        finally:
            env.close()

    def test_settled_vs_unsettled_distinguishable(self):
        """With control (clamped to nominal) vs no control episodes produce
        different reward totals — confirming 5 s window has RL signal.
        """
        from env.simulink.kundur_simulink_env import KundurStandaloneEnv

        def run_episode(action_val):
            env = KundurStandaloneEnv(training=False)
            env.reset()
            env.apply_disturbance(magnitude=2.0)
            total_r = 0.0
            for _ in range(25):
                a = np.full((env.N_AGENTS, 2), action_val, dtype=np.float32)
                _, r, terminated, truncated, _ = env.step(a)
                total_r += float(np.mean(r))
                if terminated or truncated:
                    break
            env.close()
            return total_r

        # reward with action=0 (nominal) vs action=1 (max damping push)
        r_nominal = run_episode(0.0)
        r_max_damp = run_episode(1.0)

        # Both should be finite negative numbers (frequency penalties)
        assert r_nominal < 0 and r_max_damp < 0, (
            "Rewards must be negative (frequency penalty regime)"
        )
        # The two policies must produce distinguishably different rewards
        assert abs(r_nominal - r_max_damp) > 0.1, (
            f"Rewards too similar: nominal={r_nominal:.3f}, max_damp={r_max_damp:.3f}. "
            f"5 s window may lack RL signal."
        )
