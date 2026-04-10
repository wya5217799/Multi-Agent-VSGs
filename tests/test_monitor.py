import numpy as np
import pytest
from utils.monitor import TrainingMonitor


class TestMonitorSkeleton:
    def test_default_construction(self):
        m = TrainingMonitor()
        assert m.calibration_episodes == 20
        assert m.log_interval == 10

    def test_custom_construction(self):
        m = TrainingMonitor(calibration_episodes=10, log_interval=5)
        assert m.calibration_episodes == 10
        assert m.log_interval == 5

    def test_log_and_check_returns_false_during_calibration(self):
        m = TrainingMonitor(calibration_episodes=5)
        actions = np.random.randn(50, 4, 2)  # (steps, agents, action_dim)
        result = m.log_and_check(
            episode=0,
            rewards=-1500.0,
            reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
            actions=actions,
            info={"tds_failed": False, "max_freq_deviation_hz": 0.3},
        )
        assert result is False

    def test_data_accumulates(self):
        m = TrainingMonitor(calibration_episodes=5)
        actions = np.random.randn(50, 4, 2)
        for ep in range(3):
            m.log_and_check(
                episode=ep, rewards=-1500.0 + ep * 10,
                reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                actions=actions,
                info={"tds_failed": False, "max_freq_deviation_hz": 0.3},
            )
        assert len(m._episode_rewards) == 3
        assert len(m._reward_components) == 3
        assert len(m._action_stats) == 3
        assert len(m._env_health) == 3


class TestCalibration:
    def _feed_episodes(self, m, n, reward=-1500.0, action_std=0.5, tds_fail=False):
        """Helper: feed n episodes with given characteristics."""
        for ep in range(n):
            actions = np.random.randn(50, 4, 2) * action_std
            m.log_and_check(
                episode=ep, rewards=reward,
                reward_components={"r_f": reward * 0.95, "r_h": reward * 0.025, "r_d": reward * 0.025},
                actions=actions,
                info={"tds_failed": tds_fail, "max_freq_deviation_hz": 0.3},
            )

    def test_calibration_triggers_after_n_episodes(self):
        m = TrainingMonitor(calibration_episodes=10)
        self._feed_episodes(m, 9)
        assert not m._calibrated
        self._feed_episodes(m, 1)  # 10th episode
        assert m._calibrated

    def test_calibration_sets_reward_baseline(self):
        m = TrainingMonitor(calibration_episodes=5)
        rewards = [-1500, -1400, -1600, -1450, -1550]
        for ep, r in enumerate(rewards):
            actions = np.random.randn(50, 4, 2) * 0.5
            m.log_and_check(
                episode=ep, rewards=r,
                reward_components={"r_f": r * 0.95, "r_h": r * 0.025, "r_d": r * 0.025},
                actions=actions,
                info={"tds_failed": False, "max_freq_deviation_hz": 0.3},
            )
        assert "reward_mean" in m._calibration_data
        assert "reward_std" in m._calibration_data
        assert abs(m._calibration_data["reward_mean"] - np.mean(rewards)) < 1e-6

    def test_calibration_sets_action_std_baseline(self):
        m = TrainingMonitor(calibration_episodes=5)
        self._feed_episodes(m, 5, action_std=0.5)
        assert "action_std_baseline" in m._calibration_data
        assert m._calibration_data["action_std_baseline"] > 0

    def test_calibration_sets_tds_failure_baseline(self):
        m = TrainingMonitor(calibration_episodes=10)
        for ep in range(10):
            actions = np.random.randn(50, 4, 2)
            m.log_and_check(
                episode=ep, rewards=-1500,
                reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                actions=actions,
                info={"tds_failed": (ep % 10 == 0), "max_freq_deviation_hz": 0.3},
            )
        assert "tds_failure_baseline" in m._calibration_data

    def test_incomplete_calibration(self):
        """Training ends before calibration completes."""
        m = TrainingMonitor(calibration_episodes=20)
        self._feed_episodes(m, 5)
        assert not m._calibrated


class TestRewardMagnitude:
    def test_manual_range_triggers_stop(self):
        m = TrainingMonitor(
            calibration_episodes=5,
            checks={"reward_magnitude": {"expected_range": (-3000, -200), "action": "stop"}},
        )
        actions = np.random.randn(50, 4, 2)
        for ep in range(5):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        # Episode 5: reward way out of range
        result = m.log_and_check(5, rewards=-10_000_000, reward_components={"r_f": -1400, "r_h": -5e6, "r_d": -5e6},
                                 actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert result is True  # stop triggered

    def test_manual_range_no_trigger_in_range(self):
        m = TrainingMonitor(
            calibration_episodes=5,
            checks={"reward_magnitude": {"expected_range": (-3000, -200), "action": "stop"}},
        )
        actions = np.random.randn(50, 4, 2)
        for ep in range(6):
            result = m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                                     actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert result is False

    def test_auto_mode_relative_detection(self):
        """Without manual expected_range, uses relative detection from baseline."""
        m = TrainingMonitor(calibration_episodes=5)
        actions = np.random.randn(50, 4, 2)
        # Calibration: reward ~ -1500
        for ep in range(5):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        # Sudden jump to 200x baseline
        result = m.log_and_check(5, rewards=-300_000, reward_components={"r_f": -1400, "r_h": -150000, "r_d": -150000},
                                 actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert result is True

    def test_ignore_action(self):
        m = TrainingMonitor(
            calibration_episodes=5,
            checks={"reward_magnitude": {"expected_range": (-3000, -200), "action": "ignore"}},
        )
        actions = np.random.randn(50, 4, 2)
        for ep in range(5):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        result = m.log_and_check(5, rewards=-10_000_000, reward_components={"r_f": -1400, "r_h": -5e6, "r_d": -5e6},
                                 actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert result is False  # ignored


class TestRewardComponentRatio:
    def test_dominant_below_threshold_triggers_warn(self):
        m = TrainingMonitor(
            calibration_episodes=3,
            checks={"reward_component_ratio": {"dominant": "r_f", "dominance_threshold": 0.5, "action": "warn"}},
        )
        actions = np.random.randn(50, 4, 2)
        for ep in range(3):
            m.log_and_check(ep, rewards=-10e6, reward_components={"r_f": -1400, "r_h": -5e6, "r_d": -5e6},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        # r_f is 0.01% - way below 50% threshold. Warn but don't stop.
        result = m.log_and_check(3, rewards=-10e6, reward_components={"r_f": -1400, "r_h": -5e6, "r_d": -5e6},
                                 actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert result is False  # warn, not stop
        assert any(t["check"] == "reward_component_ratio" for t in m._trigger_history)

    def test_dominant_above_threshold_no_trigger(self):
        m = TrainingMonitor(calibration_episodes=3)
        actions = np.random.randn(50, 4, 2)
        for ep in range(4):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert not any(t["check"] == "reward_component_ratio" for t in m._trigger_history)


class TestActionCollapse:
    def test_single_agent_collapse_triggers(self):
        m = TrainingMonitor(
            calibration_episodes=5,
            checks={"action_collapse": {"std_threshold": 0.05, "window": 3, "action": "warn"}},
        )
        for ep in range(5):
            actions = np.random.randn(50, 4, 2) * 0.5
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        # Agent 2 collapses to near-zero std, others stay active
        for ep in range(5, 8):
            actions = np.random.randn(50, 4, 2) * 0.5
            actions[:, 2, :] = 0.001 * np.random.randn(50, 2)  # Agent 2 near zero
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert any(t["check"] == "action_collapse" for t in m._trigger_history)

    def test_no_collapse_when_std_healthy(self):
        m = TrainingMonitor(calibration_episodes=3, checks={"action_collapse": {"std_threshold": 0.05, "window": 3, "action": "warn"}})
        for ep in range(6):
            actions = np.random.randn(50, 4, 2) * 0.5
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert not any(t["check"] == "action_collapse" for t in m._trigger_history)


class TestActionSaturation:
    def test_saturation_triggers(self):
        m = TrainingMonitor(
            calibration_episodes=3,
            checks={"action_saturation": {"threshold": 0.8, "action": "warn"}},
        )
        for ep in range(3):
            actions = np.random.randn(50, 4, 2) * 0.5
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        # 90% of actions at boundaries
        actions = np.ones((50, 4, 2)) * 0.99
        result = m.log_and_check(3, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                                 actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert any(t["check"] == "action_saturation" for t in m._trigger_history)

    def test_no_saturation_when_normal(self):
        m = TrainingMonitor(calibration_episodes=3)
        for ep in range(4):
            actions = np.random.randn(50, 4, 2) * 0.3
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert not any(t["check"] == "action_saturation" for t in m._trigger_history)


class TestRewardPlateau:
    def test_plateau_triggers_after_flat_window(self):
        m = TrainingMonitor(
            calibration_episodes=5,
            checks={"reward_plateau": {"window": 10, "improvement_threshold": 0.01, "action": "warn"}},
        )
        actions = np.random.randn(50, 4, 2) * 0.5
        # 5 calibration + 10 flat episodes
        for ep in range(15):
            m.log_and_check(ep, rewards=-1500.0, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert any(t["check"] == "reward_plateau" for t in m._trigger_history)

    def test_no_plateau_when_improving(self):
        m = TrainingMonitor(
            calibration_episodes=5,
            checks={"reward_plateau": {"window": 10, "improvement_threshold": 0.01, "action": "warn"}},
        )
        actions = np.random.randn(50, 4, 2) * 0.5
        for ep in range(15):
            m.log_and_check(ep, rewards=-1500.0 + ep * 50, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert not any(t["check"] == "reward_plateau" for t in m._trigger_history)


class TestRewardDivergence:
    def test_divergence_triggers_on_declining_trend(self):
        m = TrainingMonitor(
            calibration_episodes=5,
            checks={"reward_divergence": {"window": 10, "action": "stop"}},
        )
        actions = np.random.randn(50, 4, 2) * 0.5
        # 5 calibration at -1500, then 10 episodes of worsening rewards
        for ep in range(5):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        result = False
        for ep in range(5, 15):
            result = m.log_and_check(ep, rewards=-1500 - (ep - 5) * 500,
                                     reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                                     actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
            if result:
                break
        assert result is True

    def test_no_divergence_when_stable(self):
        m = TrainingMonitor(calibration_episodes=5, checks={"reward_divergence": {"window": 10, "action": "stop"}})
        actions = np.random.randn(50, 4, 2) * 0.5
        for ep in range(15):
            m.log_and_check(ep, rewards=-1500 + np.random.randn() * 10,
                            reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert not any(t["check"] == "reward_divergence" for t in m._trigger_history)


class TestTdsFailureRate:
    def test_high_failure_rate_triggers(self):
        m = TrainingMonitor(
            calibration_episodes=5,
            checks={"tds_failure_rate": {"threshold": 0.2, "window": 5, "action": "warn"}},
        )
        actions = np.random.randn(50, 4, 2) * 0.5
        for ep in range(5):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        # 3/5 episodes fail -> 60% > 20% threshold
        for ep in range(5, 10):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": (ep < 8), "max_freq_deviation_hz": 0.3})
        assert any(t["check"] == "tds_failure_rate" for t in m._trigger_history)


class TestFreqOutOfRange:
    def test_persistent_freq_violation_triggers(self):
        m = TrainingMonitor(
            calibration_episodes=3,
            checks={"freq_out_of_range": {"threshold_hz": 2.0, "window": 5, "min_episodes": 2, "action": "warn"}},
        )
        actions = np.random.randn(50, 4, 2) * 0.5
        for ep in range(3):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        # 3 episodes with freq > 2 Hz (exceeds min_episodes=2)
        for ep in range(3, 8):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 3.5})
        assert any(t["check"] == "freq_out_of_range" for t in m._trigger_history)

    def test_single_spike_no_trigger(self):
        m = TrainingMonitor(
            calibration_episodes=3,
            checks={"freq_out_of_range": {"threshold_hz": 2.0, "window": 5, "min_episodes": 3, "action": "warn"}},
        )
        actions = np.random.randn(50, 4, 2) * 0.5
        for ep in range(3):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        # 1 spike, rest normal
        m.log_and_check(3, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                        actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 5.0})
        for ep in range(4, 8):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert not any(t["check"] == "freq_out_of_range" for t in m._trigger_history)


class TestPhysicsFrozen:
    def test_zero_power_swing_window_triggers_stop_before_calibration_complete(self):
        """Frozen electrical response is severe enough to stop without waiting for calibration."""
        m = TrainingMonitor(
            calibration_episodes=20,
            checks={"physics_frozen": {"window": 10, "epsilon": 0.0, "action": "stop"}},
        )
        actions = np.random.randn(50, 4, 2) * 0.5

        result = False
        for ep in range(10):
            result = m.log_and_check(
                ep,
                rewards=-1500,
                reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                actions=actions,
                info={
                    "tds_failed": False,
                    "max_freq_deviation_hz": 0.3,
                    "max_power_swing": 0.0,
                },
            )

        assert result is True
        assert any(t["check"] == "physics_frozen" for t in m._trigger_history)

    def test_nonzero_power_swing_does_not_trigger_physics_frozen(self):
        m = TrainingMonitor(
            calibration_episodes=3,
            checks={"physics_frozen": {"window": 5, "epsilon": 1e-9, "action": "stop"}},
        )
        actions = np.random.randn(50, 4, 2) * 0.5

        for ep in range(8):
            result = m.log_and_check(
                ep,
                rewards=-1500,
                reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                actions=actions,
                info={
                    "tds_failed": False,
                    "max_freq_deviation_hz": 0.3,
                    "max_power_swing": 0.02,
                },
            )

        assert result is False
        assert not any(t["check"] == "physics_frozen" for t in m._trigger_history)


class TestOutputFormatting:
    def test_log_summary_prints(self, capsys):
        m = TrainingMonitor(calibration_episodes=3, log_interval=5)
        actions = np.random.randn(50, 4, 2) * 0.5
        for ep in range(5):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        captured = capsys.readouterr()
        assert "[Monitor]" in captured.out
        assert "Ep 4" in captured.out  # 0-indexed, logged at ep 4 (5th episode)

    def test_summary_prints_final_report(self, capsys):
        m = TrainingMonitor(calibration_episodes=3, log_interval=100)
        actions = np.random.randn(50, 4, 2) * 0.5
        for ep in range(5):
            m.log_and_check(ep, rewards=-1500 + ep * 100,
                            reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        m.summary()
        captured = capsys.readouterr()
        assert "Training Summary" in captured.out
        assert "Episodes: 5" in captured.out

    def test_summary_with_incomplete_calibration(self, capsys):
        m = TrainingMonitor(calibration_episodes=20, log_interval=100)
        actions = np.random.randn(50, 4, 2) * 0.5
        for ep in range(3):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        m.summary()
        captured = capsys.readouterr()
        assert "incomplete" in captured.out.lower() or "not complete" in captured.out.lower()


class TestEnvInfoCompat:
    def test_ode_env_info_has_max_freq_deviation(self):
        """ODE env step() info dict must include max_freq_deviation_hz."""
        pytest.importorskip("scipy")
        import config as cfg
        from env.ode.multi_vsg_env import MultiVSGEnv
        env = MultiVSGEnv()
        obs = env.reset()
        actions = {i: np.zeros(cfg.ACTION_DIM) for i in range(cfg.N_AGENTS)}
        _, _, _, info = env.step(actions)
        assert "max_freq_deviation_hz" in info
        assert isinstance(info["max_freq_deviation_hz"], float)


class TestEndToEnd:
    def test_monitor_with_real_ode_env(self):
        """Full integration: ODE env + random actions + monitor."""
        pytest.importorskip("scipy")
        import config as cfg
        from env.ode.multi_vsg_env import MultiVSGEnv

        env = MultiVSGEnv()
        monitor = TrainingMonitor(calibration_episodes=3, log_interval=2)

        for episode in range(5):
            obs = env.reset()
            ep_actions_list = []
            ep_r_f, ep_r_h, ep_r_d = 0.0, 0.0, 0.0
            ep_max_freq = 0.0

            for step in range(10):  # Short episodes for test speed
                actions = {i: np.random.uniform(-1, 1, size=cfg.ACTION_DIM) for i in range(cfg.N_AGENTS)}
                obs, rewards, done, info = env.step(actions)
                ep_actions_list.append(np.array([actions[i] for i in range(cfg.N_AGENTS)]))
                ep_r_f += info['r_f']
                ep_r_h += info['r_h']
                ep_r_d += info['r_d']
                ep_max_freq = max(ep_max_freq, info.get('max_freq_deviation_hz', 0.0))
                if done:
                    break

            total_reward = sum(rewards.values()) if isinstance(rewards, dict) else rewards
            should_stop = monitor.log_and_check(
                episode=episode,
                rewards=float(total_reward),
                reward_components={"r_f": ep_r_f, "r_h": ep_r_h, "r_d": ep_r_d},
                actions=np.array(ep_actions_list),
                info={"tds_failed": False, "max_freq_deviation_hz": ep_max_freq},
            )

        monitor.summary()
        assert len(monitor._episode_rewards) == 5
