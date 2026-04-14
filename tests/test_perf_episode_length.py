# tests/test_perf_episode_length.py
"""Episode length contract for Kundur Simulink training.

Yang et al. TPWRS 2023 Sec.IV-A: M=50 control steps × DT=0.2s = T_EPISODE=10s.

This file was previously written as "Opt-A: Shorten to 5s" but the 5s change
has been reverted — the paper's OMEGA_TERM_THRESHOLD guard (which caused 100%
episode termination) has been removed instead.  Episodes now run the full 10s
per the paper specification.
"""
import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Config-level contracts
# ---------------------------------------------------------------------------

class TestEpisodeLengthConfig:

    def test_config_t_episode_is_10s(self):
        from scenarios.kundur.config_simulink import T_EPISODE
        assert T_EPISODE == 10.0, (
            f"T_EPISODE should be 10.0 (paper Sec.IV-A M=50), got {T_EPISODE}"
        )

    def test_config_steps_per_episode_is_50(self):
        from scenarios.kundur.config_simulink import STEPS_PER_EPISODE
        assert STEPS_PER_EPISODE == 50, (
            f"STEPS_PER_EPISODE should be 50, got {STEPS_PER_EPISODE}"
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

    def test_env_t_episode_attribute_is_10s(self, env):
        assert env.T_EPISODE == 10.0, (
            f"env.T_EPISODE should be 10.0, got {env.T_EPISODE}"
        )

    def test_env_truncates_at_50_steps(self, env):
        """Episode must end with truncated=True at exactly 50 steps."""
        env.reset()
        step_count = 0
        truncated = False
        while True:
            action = np.zeros((env.N_AGENTS, 2), dtype=np.float32)
            _, _, terminated, truncated, _ = env.step(action)
            step_count += 1
            if terminated or truncated:
                break
        assert step_count == 50, (
            f"Expected episode length 50 steps, got {step_count}"
        )
        assert truncated, "Episode should end via truncation (time limit), not termination"

    def test_env_sim_time_at_end_is_10s(self, env):
        """sim_time after 50 steps must reach 10.0 s."""
        env.reset()
        info = {}
        for _ in range(50):
            action = np.zeros((env.N_AGENTS, 2), dtype=np.float32)
            _, _, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break
        assert abs(info["sim_time"] - 10.0) < 1e-6, (
            f"sim_time at episode end should be 10.0 s, got {info['sim_time']}"
        )


# ---------------------------------------------------------------------------
# Physics contract: frequency nadir must be observable within 10 s
# ---------------------------------------------------------------------------

class TestPhysicsWithin10s:

    def test_nadir_visible_after_load_trip(self):
        """After a load disturbance the nadir must appear before the episode ends.

        A real power system nadir after a 248 MW load trip occurs within ~2-3 s.
        10 s easily captures it.
        """
        from env.simulink.kundur_simulink_env import KundurStandaloneEnv
        env = KundurStandaloneEnv(training=False)
        try:
            env.reset()
            # Apply load trip (negative = load reduction → freq rises in standalone model)
            env.apply_disturbance(magnitude=-2.0)

            min_omega = 1.0
            max_omega = 1.0
            for _ in range(50):  # 50 steps × 0.2 s = 10 s
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
                f"Expected visible freq deviation >0.5% within 10s after disturbance, "
                f"got max_deviation={max_deviation:.4f} pu "
                f"(omega range [{min_omega:.4f}, {max_omega:.4f}])"
            )
        finally:
            env.close()

    def test_settled_vs_unsettled_distinguishable(self):
        """With control (clamped to nominal) vs no control episodes produce
        different reward totals — confirming 10 s window has RL signal.
        """
        from env.simulink.kundur_simulink_env import KundurStandaloneEnv

        def run_episode(action_val):
            env = KundurStandaloneEnv(training=False)
            env.reset()
            env.apply_disturbance(magnitude=2.0)
            total_r = 0.0
            for _ in range(50):
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
            f"10 s window may lack RL signal."
        )
