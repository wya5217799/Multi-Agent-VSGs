# tests/test_simulink_bridge.py
"""Tests for engine.simulink_bridge."""
import pytest
from unittest.mock import MagicMock, patch
import numpy as np


class TestBridgeConfig:
    def test_kundur_config_has_correct_agents(self):
        from scenarios.kundur.config_simulink import KUNDUR_BRIDGE_CONFIG
        assert KUNDUR_BRIDGE_CONFIG.n_agents == 4
        assert KUNDUR_BRIDGE_CONFIG.model_name == "kundur_vsg"
        assert "{idx}" in KUNDUR_BRIDGE_CONFIG.m_path_template
        assert KUNDUR_BRIDGE_CONFIG.sbase_va == 100e6
        assert KUNDUR_BRIDGE_CONFIG.tripload1_p_default == 248e6
        assert KUNDUR_BRIDGE_CONFIG.tripload2_p_default == 188e6

    def test_ne39_config_has_correct_agents(self):
        from scenarios.new_england.config_simulink import NE39_BRIDGE_CONFIG
        assert NE39_BRIDGE_CONFIG.n_agents == 8
        assert NE39_BRIDGE_CONFIG.model_name == "NE39bus_v2"
        assert "{idx}" in NE39_BRIDGE_CONFIG.m_path_template
        assert NE39_BRIDGE_CONFIG.sbase_va == 100e6


def _make_test_config(tmp_path=None):
    """Create a BridgeConfig for testing."""
    from engine.simulink_bridge import BridgeConfig
    return BridgeConfig(
        model_name="test_model",
        model_dir=str(tmp_path or "/tmp/test"),
        n_agents=4,
        dt_control=0.2,
        sbase_va=100e6,
        m_path_template="{model}/VSG_ES{idx}/M0",
        d_path_template="{model}/VSG_ES{idx}/D0",
        omega_signal="omega_ES{idx}",
        vabc_signal="Vabc_ES{idx}",
        iabc_signal="Iabc_ES{idx}",
    )


class TestSimulinkBridge:
    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_step_returns_dict_with_omega_pe_rocof(self, mock_me):
        from engine.simulink_bridge import SimulinkBridge

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        mock_state = {"omega": [[1.0, 1.0, 1.0, 1.0]],
                      "Pe": [[0.5, 0.5, 0.5, 0.5]],
                      "rocof": [[0.0, 0.0, 0.0, 0.0]],
                      "delta": [[0.0, 0.0, 0.0, 0.0]],
                      "delta_deg": [[0.0, 0.0, 0.0, 0.0]]}
        mock_status = {"success": True, "error": "", "elapsed_ms": 10.0}
        mock_eng.vsg_step_and_read = MagicMock(
            return_value=(mock_state, mock_status)
        )

        cfg = _make_test_config()
        bridge = SimulinkBridge(cfg)
        bridge._matlab_cfg = MagicMock()
        bridge._SimulinkBridge__mdbl = lambda x: x  # mock matlab.double

        M = np.array([12.0, 12.0, 12.0, 12.0])
        D = np.array([3.0, 3.0, 3.0, 3.0])
        result = bridge.step(M, D)

        assert "omega" in result
        assert "Pe" in result
        assert "rocof" in result
        assert result["omega"].shape == (4,)

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_step_advances_time(self, mock_me):
        from engine.simulink_bridge import SimulinkBridge

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        mock_state = {"omega": [[1.0]*4], "Pe": [[0.5]*4], "rocof": [[0.0]*4], "delta": [[0.0]*4], "delta_deg": [[0.0]*4]}
        mock_status = {"success": True, "error": "", "elapsed_ms": 5.0}
        mock_eng.vsg_step_and_read = MagicMock(
            return_value=(mock_state, mock_status)
        )

        cfg = _make_test_config()
        bridge = SimulinkBridge(cfg)
        bridge._matlab_cfg = MagicMock()
        bridge._SimulinkBridge__mdbl = lambda x: x

        assert bridge.t_current == 0.0
        bridge.step(np.ones(4) * 12, np.ones(4) * 3)
        assert abs(bridge.t_current - 0.2) < 1e-9

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_step_raises_on_sim_failure(self, mock_me):
        from engine.simulink_bridge import SimulinkBridge
        from engine.exceptions import SimulinkError

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        mock_state = {"omega": [[0]*4], "Pe": [[0]*4], "rocof": [[0]*4], "delta": [[0]*4], "delta_deg": [[0.0]*4]}
        mock_status = {"success": False, "error": "Divergence at t=0.1", "elapsed_ms": 5.0}
        mock_eng.vsg_step_and_read = MagicMock(
            return_value=(mock_state, mock_status)
        )

        cfg = _make_test_config()
        bridge = SimulinkBridge(cfg)
        bridge._matlab_cfg = MagicMock()
        bridge._SimulinkBridge__mdbl = lambda x: x

        with pytest.raises(SimulinkError, match="Divergence"):
            bridge.step(np.ones(4) * 12, np.ones(4) * 3)

    def test_reset_clears_time_without_ghost_state_attrs(self):
        from engine.simulink_bridge import SimulinkBridge
        cfg = _make_test_config()
        bridge = SimulinkBridge(cfg)
        bridge.t_current = 5.0

        assert not hasattr(bridge, "_xFinal")
        assert not hasattr(bridge, "_Pe_prev")

        bridge.reset()

        assert bridge.t_current == 0.0


class _FakeKundurBridge:
    def __init__(self, cfg):
        self.cfg = cfg
        self._tripload_state = {
            cfg.tripload1_p_var: cfg.tripload1_p_default,
            cfg.tripload2_p_var: cfg.tripload2_p_default,
        }
        self.breaker_events = []
        self.loaded = 0
        self.reset_calls = 0
        self.warmups = []
        self.t_current = 0.0

    def load_model(self):
        self.loaded += 1

    def reset(self):
        self.reset_calls += 1

    def warmup(self, duration):
        self.warmups.append(duration)
        self.t_current = duration

    def configure_breaker_event(self, breaker_idx, *, time_s, before, after):
        self.breaker_events.append(
            {
                "breaker_idx": breaker_idx,
                "time_s": time_s,
                "before": before,
                "after": after,
            }
        )

    def close(self):
        pass


@patch("engine.simulink_bridge.SimulinkBridge", new=_FakeKundurBridge)
def test_kundur_reset_keeps_nominal_triploads_and_schedules_breakers():
    from env.simulink.kundur_simulink_env import KundurSimulinkEnv, T_WARMUP

    env = KundurSimulinkEnv(training=False)
    env._reset_backend(options={"disturbance_magnitude": -1.0})

    cfg = env.bridge.cfg
    assert env.bridge._tripload_state[cfg.tripload1_p_var] == cfg.tripload1_p_default
    assert env.bridge._tripload_state[cfg.tripload2_p_var] == cfg.tripload2_p_default
    assert env.bridge.warmups == [T_WARMUP]
    assert env.bridge.breaker_events == [
        {"breaker_idx": 1, "time_s": pytest.approx(T_WARMUP + 1e-3), "before": 1.0, "after": 0.0},
        {"breaker_idx": 2, "time_s": pytest.approx(100.0), "before": 0.0, "after": 0.0},
    ]
