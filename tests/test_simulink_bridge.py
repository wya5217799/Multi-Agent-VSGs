# tests/test_simulink_bridge.py
"""Tests for engine.simulink_bridge."""
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


def _install_fake_gymnasium(monkeypatch) -> None:
    """Provide a tiny gymnasium shim when the optional dependency is absent."""
    try:
        import gymnasium  # noqa: F401
        return
    except ImportError:
        pass

    fake_gym = types.ModuleType("gymnasium")

    class _Env:
        def reset(self, *args, **kwargs):
            raise NotImplementedError

        def step(self, *args, **kwargs):
            raise NotImplementedError

    class _Box:
        def __init__(self, low, high, shape=None, dtype=None):
            self.low = low
            self.high = high
            self.shape = shape
            self.dtype = dtype

    fake_gym.Env = _Env
    fake_gym.spaces = types.SimpleNamespace(Box=_Box)
    monkeypatch.setitem(sys.modules, "gymnasium", fake_gym)


class TestBridgeConfig:
    def test_kundur_config_has_correct_agents(self):
        from scenarios.kundur.config_simulink import KUNDUR_BRIDGE_CONFIG
        assert KUNDUR_BRIDGE_CONFIG.n_agents == 4
        assert KUNDUR_BRIDGE_CONFIG.model_name == "kundur_vsg"
        assert "{idx}" in KUNDUR_BRIDGE_CONFIG.m_path_template
        assert KUNDUR_BRIDGE_CONFIG.sbase_va == 100e6
        assert KUNDUR_BRIDGE_CONFIG.tripload1_p_default == pytest.approx(248e6 / 3)
        assert KUNDUR_BRIDGE_CONFIG.tripload2_p_default == 0.0

    def test_ne39_config_has_correct_agents(self):
        from scenarios.new_england.config_simulink import NE39_BRIDGE_CONFIG
        assert NE39_BRIDGE_CONFIG.n_agents == 8
        assert NE39_BRIDGE_CONFIG.model_name == "NE39bus_v2"
        assert "{idx}" in NE39_BRIDGE_CONFIG.m_path_template
        assert NE39_BRIDGE_CONFIG.sbase_va == 100e6


class TestNE39FrCompiled:
    """NE39 env must expose _fr_compiled via its bridge and pass do_recompile correctly."""

    def test_fr_compiled_starts_false(self, monkeypatch):
        """bridge._fr_compiled is False before any reset."""
        _install_fake_gymnasium(monkeypatch)
        import types, sys
        fake_matlab = types.ModuleType("matlab")
        fake_matlab.engine = types.ModuleType("matlab.engine")
        monkeypatch.setitem(sys.modules, "matlab", fake_matlab)
        monkeypatch.setitem(sys.modules, "matlab.engine", fake_matlab.engine)

        with patch("engine.simulink_bridge.SimulinkBridge") as MockBridge:
            instance = MockBridge.return_value
            instance._fr_compiled = False
            from env.simulink.ne39_simulink_env import NE39BusSimulinkEnv
            env = NE39BusSimulinkEnv.__new__(NE39BusSimulinkEnv)
            env.bridge = instance
            assert env.bridge._fr_compiled is False

    def test_fr_compiled_set_after_reset(self, monkeypatch):
        """After _reset_backend, bridge._fr_compiled must be True and do_recompile
        must be True on the first call, False on the second."""
        _install_fake_gymnasium(monkeypatch)
        import types, sys
        fake_matlab = types.ModuleType("matlab")
        fake_matlab.engine = types.ModuleType("matlab.engine")
        fake_matlab.double = list
        monkeypatch.setitem(sys.modules, "matlab", fake_matlab)
        monkeypatch.setitem(sys.modules, "matlab.engine", fake_matlab.engine)

        recorded_calls = []

        class FakeBridge:
            _fr_compiled = False
            cfg = MagicMock()
            cfg.model_name = "NE39bus_v2"
            cfg.sbase_va = 100e6
            _matlab_double = list
            _matlab_cfg = {}
            t_current = 0.0
            _delta_prev_deg = [0.0] * 8
            _Pe_prev = [0.5] * 8

            def load_model(self): pass
            def reset(self): pass

            class session:
                @staticmethod
                def eval(expr, nargout=0): return {}

                @staticmethod
                def call(fn, *args, nargout=0):
                    recorded_calls.append((fn, args))
                    if fn == "slx_episode_warmup":
                        return {}, {"success": True}
                    return None

        with patch("engine.simulink_bridge.SimulinkBridge", return_value=FakeBridge()), \
             patch("scenarios.new_england.config_simulink.NE39_BRIDGE_CONFIG"):
            from env.simulink.ne39_simulink_env import NE39BusSimulinkEnv
            env = NE39BusSimulinkEnv.__new__(NE39BusSimulinkEnv)
            env.bridge = FakeBridge()
            env._sim_time = 0.0

            # First reset: do_recompile must be True (bridge._fr_compiled=False)
            env._reset_backend()
            warmup_call = next(c for c in recorded_calls if c[0] == "slx_episode_warmup")
            assert warmup_call[1][-1] is True, "first reset must recompile"
            assert env.bridge._fr_compiled is True

            # Second reset: do_recompile must be False
            recorded_calls.clear()
            env._reset_backend()
            warmup_call2 = next(c for c in recorded_calls if c[0] == "slx_episode_warmup")
            assert warmup_call2[1][-1] is False, "second reset must skip recompile"


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
        pe0_default_vsg=1.87,
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
        mock_eng.slx_step_and_read = MagicMock(
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
        mock_eng.slx_step_and_read = MagicMock(
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
        mock_eng.slx_step_and_read = MagicMock(
            return_value=(mock_state, mock_status)
        )

        cfg = _make_test_config()
        bridge = SimulinkBridge(cfg)
        bridge._matlab_cfg = MagicMock()
        bridge._SimulinkBridge__mdbl = lambda x: x

        with pytest.raises(SimulinkError, match="Divergence"):
            bridge.step(np.ones(4) * 12, np.ones(4) * 3)

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_sim_failure_resets_fr_compiled(self, mock_me):
        """After sim() fails, _fr_compiled must be False so next warmup recompiles.

        Root cause of Apr-2026 training freeze: FastRestart state becomes
        corrupted when sim() crashes.  Without _fr_compiled=False, every
        subsequent episode reset uses do_recompile=False (fast path) and the
        corrupted state is never cleared — all future steps fail permanently.
        """
        from engine.simulink_bridge import SimulinkBridge
        from engine.exceptions import SimulinkError

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        mock_state = {"omega": [[0]*4], "Pe": [[0]*4], "rocof": [[0]*4], "delta": [[0]*4], "delta_deg": [[0.0]*4]}
        mock_status = {"success": False, "error": "NaN at t=14.7", "elapsed_ms": 5.0}
        mock_eng.slx_step_and_read = MagicMock(
            return_value=(mock_state, mock_status)
        )

        cfg = _make_test_config()
        bridge = SimulinkBridge(cfg)
        bridge._matlab_cfg = MagicMock()
        bridge._SimulinkBridge__mdbl = lambda x: x
        bridge._fr_compiled = True  # simulate post-warmup state (compiled model)

        with pytest.raises(SimulinkError):
            bridge.step(np.ones(4) * 12, np.ones(4) * 3)

        assert bridge._fr_compiled is False, (
            "step() sim failure must reset _fr_compiled=False so next warmup() "
            "forces FastRestart recompile and clears the corrupted solver state"
        )

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_sim_failure_before_warmup_leaves_fr_compiled_false(self, mock_me):
        """sim failure before first warmup is idempotent: _fr_compiled stays False."""
        from engine.simulink_bridge import SimulinkBridge
        from engine.exceptions import SimulinkError

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        mock_status = {"success": False, "error": "crash", "elapsed_ms": 1.0}
        mock_state = {"omega": [[0]*4], "Pe": [[0]*4], "rocof": [[0]*4], "delta": [[0]*4], "delta_deg": [[0.0]*4]}
        mock_eng.slx_step_and_read = MagicMock(return_value=(mock_state, mock_status))

        bridge = SimulinkBridge(_make_test_config())
        bridge._matlab_cfg = MagicMock()
        bridge._SimulinkBridge__mdbl = lambda x: x
        assert bridge._fr_compiled is False  # pre-condition: never warmed up

        with pytest.raises(SimulinkError):
            bridge.step(np.ones(4) * 12, np.ones(4) * 3)

        assert bridge._fr_compiled is False, (
            "step() failure before warmup must leave _fr_compiled=False (idempotent)"
        )

    def test_reset_clears_time_and_feedback_state(self):
        from engine.simulink_bridge import SimulinkBridge
        cfg = _make_test_config()
        bridge = SimulinkBridge(cfg)
        bridge.t_current = 5.0
        bridge._Pe_prev = np.array([0.5, 0.5, 0.5, 0.5])
        bridge._delta_prev_deg = np.array([10.0, 10.0, 10.0, 10.0])

        bridge.reset()

        assert bridge.t_current == 0.0
        assert bridge._Pe_prev is None
        assert bridge._delta_prev_deg is None

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_warmup_seeds_pe_prev_from_config_default(self, mock_me):
        from engine.simulink_bridge import SimulinkBridge

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        cfg = _make_test_config()
        bridge = SimulinkBridge(cfg)
        bridge._matlab_cfg = MagicMock()
        bridge.warmup(0.5)

        expected = cfg.pe0_default_vsg * (cfg.vsg_sn_va / cfg.sbase_va)
        assert np.allclose(bridge._Pe_prev, np.full(cfg.n_agents, expected))
        pe_calls = [
            args[0]
            for args, kwargs in mock_eng.eval.call_args_list
            if "assignin('base', 'Pe_ES" in args[0]
        ]
        assert any("1.87" in call for call in pe_calls)

    def test_close_logs_warning_when_close_model_fails(self, caplog):
        from engine.exceptions import MatlabCallError
        from engine.simulink_bridge import SimulinkBridge

        cfg = _make_test_config()
        bridge = SimulinkBridge(cfg)
        bridge.session = MagicMock()
        bridge.session.call.side_effect = MatlabCallError("slx_close_model", (), "close failed")

        with caplog.at_level("WARNING"):
            bridge.close()

        assert "close failed" in caplog.text


class _FakeKundurBridge:
    def __init__(self, cfg):
        self.cfg = cfg
        self._tripload_state = {
            cfg.tripload1_p_var: cfg.tripload1_p_default,
            cfg.tripload2_p_var: cfg.tripload2_p_default,
        }
        self.disturbance_load_calls = []
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

    def set_disturbance_load(self, var_name, value_w):
        self._tripload_state[var_name] = value_w

    def apply_disturbance_load(self, var_name, value_w):
        self._tripload_state[var_name] = value_w
        self.disturbance_load_calls.append((var_name, value_w))

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
def test_kundur_reset_restores_nominal_triploads_and_warms_up(monkeypatch):
    _install_fake_gymnasium(monkeypatch)
    from env.simulink.kundur_simulink_env import KundurSimulinkEnv, T_WARMUP

    env = KundurSimulinkEnv(training=False)
    env._reset_backend(options={"disturbance_magnitude": -1.0})

    cfg = env.bridge.cfg
    assert env.bridge._tripload_state[cfg.tripload1_p_var] == cfg.tripload1_p_default
    assert env.bridge._tripload_state[cfg.tripload2_p_var] == cfg.tripload2_p_default
    assert env.bridge.warmups == [T_WARMUP]
    assert env.bridge.loaded == 1
    assert env.bridge.reset_calls == 1


def test_kundur_config_overrides_power_normalization():
    from scenarios.kundur.config_simulink import NORM_P

    assert NORM_P == 4.0


@patch("engine.simulink_bridge.SimulinkBridge", new=_FakeKundurBridge)
def test_kundur_env_uses_configured_power_normalization(monkeypatch):
    _install_fake_gymnasium(monkeypatch)
    import env.simulink.kundur_simulink_env as kundur_env
    from scenarios.kundur.config_simulink import NORM_P as configured_norm_p

    assert kundur_env.NORM_P == configured_norm_p


@patch("engine.simulink_bridge.SimulinkBridge", new=_FakeKundurBridge)
def test_kundur_negative_disturbance_scales_tripload1_with_magnitude(monkeypatch):
    _install_fake_gymnasium(monkeypatch)
    from env.simulink.kundur_simulink_env import KundurSimulinkEnv

    env = KundurSimulinkEnv(training=False)
    cfg = env.bridge.cfg

    env._apply_disturbance_backend(bus_idx=None, magnitude=-1.0)
    expected_small = (248e6 - 100e6) / 3.0
    assert env.bridge._tripload_state[cfg.tripload1_p_var] == pytest.approx(expected_small)

    env._apply_disturbance_backend(bus_idx=None, magnitude=-3.0)
    assert env.bridge._tripload_state[cfg.tripload1_p_var] == 0.0


@patch("engine.simulink_bridge.SimulinkBridge", new=_FakeKundurBridge)
def test_kundur_positive_disturbance_scales_tripload2_with_magnitude(monkeypatch):
    _install_fake_gymnasium(monkeypatch)
    from env.simulink.kundur_simulink_env import KundurSimulinkEnv

    env = KundurSimulinkEnv(training=False)
    cfg = env.bridge.cfg

    env._apply_disturbance_backend(bus_idx=None, magnitude=1.0)
    expected_small = 100e6 / 3.0
    assert env.bridge._tripload_state[cfg.tripload2_p_var] == pytest.approx(expected_small)

    env._apply_disturbance_backend(bus_idx=None, magnitude=1.88)
    expected_large = 188e6 / 3.0
    assert env.bridge._tripload_state[cfg.tripload2_p_var] == pytest.approx(expected_large)

    env._apply_disturbance_backend(bus_idx=None, magnitude=3.0)
    assert env.bridge._tripload_state[cfg.tripload2_p_var] == pytest.approx(expected_large)


def test_slx_step_and_read_warns_when_pe_measurement_fails():
    helper = (
        Path(__file__).resolve().parents[1]
        / "slx_helpers"
        / "vsg_bridge"
        / "slx_step_and_read.m"
    )
    text = helper.read_text(encoding="utf-8")

    assert "warning('slx_step_and_read:PeReadFailed'" in text


def test_ne39_probe_sets_pe_measurement_mode():
    helper = (
        Path(__file__).resolve().parents[1]
        / "probes"
        / "ne39"
        / "probe_phang_sensitivity.m"
    )
    text = helper.read_text(encoding="utf-8")

    assert "cfg.pe_measurement = 'vi';" in text


def test_kundur_build_script_uses_workspace_backed_m0_d0_constants():
    script = (
        Path(__file__).resolve().parents[1]
        / "scenarios"
        / "kundur"
        / "simulink_models"
        / "build_powerlib_kundur.m"
    )
    text = script.read_text(encoding="utf-8")

    assert "'Value', sprintf('M0_val_ES%d', i)" in text
    assert "'Value', sprintf('D0_val_ES%d', i)" in text


def test_kundur_build_script_uses_dynamic_load_not_breakers():
    """Build script must use Dynamic Load + workspace variables, not breaker Step blocks.

    This locks the requirement that disturbance amplitude is controlled via
    TripLoad1_P / TripLoad2_P workspace variables so that mid-episode
    magnitude changes work under FastRestart without topology changes.
    """
    script = (
        Path(__file__).resolve().parents[1]
        / "scenarios"
        / "kundur"
        / "simulink_models"
        / "build_powerlib_kundur.m"
    )
    text = script.read_text(encoding="utf-8")

    # Workspace variables must be referenced in the build script
    assert "TripLoad1_P" in text, "Missing TripLoad1_P workspace variable reference"
    assert "TripLoad2_P" in text, "Missing TripLoad2_P workspace variable reference"

    # Workspace variables must be initialized via assignin
    assert "assignin" in text, "Missing assignin() call to initialize workspace variables"

    # Dynamic Load block from ee_lib must be used
    assert "dynload_lib" in text or "Dynamic Load" in text, (
        "Missing Dynamic Load block — disturbance subsystem must use ee_lib Dynamic Load"
    )

    # No BrkCtrl_ Step blocks in active (non-comment) add_block calls
    active_brk_add_block = [
        line for line in text.splitlines()
        if "add_block" in line and "BrkCtrl" in line and not line.strip().startswith("%")
    ]
    assert len(active_brk_add_block) == 0, (
        f"Found BrkCtrl_ add_block in non-comment lines (breaker-based disturbance "
        f"blocks not permitted): {active_brk_add_block}"
    )


def test_kundur_build_script_uses_local_solver():
    """SolverConfig must enable Simscape local fixed-step solver.

    Required for Dynamic Load performance: without LocalSolver, variable-step
    ode23t collapses to femtosecond steps when Dynamic Load is present.
    See docs/knowledge/simulink_base.md §14.
    """
    script = (
        Path(__file__).resolve().parents[1]
        / "scenarios"
        / "kundur"
        / "simulink_models"
        / "build_powerlib_kundur.m"
    )
    text = script.read_text(encoding="utf-8")

    assert "UseLocalSolver" in text, "Missing UseLocalSolver in SolverConfig"
    assert "DoFixedCost" in text, "Missing DoFixedCost in SolverConfig"
    assert "LocalSolverSampleTime" in text, "Missing LocalSolverSampleTime in SolverConfig"


# =============================================================================
# P0: Measurement failure detection
# =============================================================================


class TestMeasurementFailureDetection:
    """Tests for structured measurement failure reporting and Pe sanity check."""

    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_consecutive_pe_zero_raises_after_tolerance(self, mock_me):
        """Pe=0 for all agents for N consecutive steps raises MeasurementFailureError."""
        from engine.simulink_bridge import SimulinkBridge, MeasurementFailureError, _PE_ZERO_TOLERANCE_STEPS

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        # All Pe = 0 (broken feedback chain)
        mock_state = {
            "omega": [[1.0]*4], "Pe": [[0.0]*4], "rocof": [[0.0]*4],
            "delta": [[0.0]*4], "delta_deg": [[0.0]*4],
        }
        mock_status = {"success": True, "error": "", "elapsed_ms": 5.0, "measurement_failures": []}
        mock_eng.slx_step_and_read = MagicMock(return_value=(mock_state, mock_status))

        cfg = _make_test_config()
        bridge = SimulinkBridge(cfg)
        bridge._matlab_cfg = MagicMock()
        bridge._SimulinkBridge__mdbl = lambda x: x

        M = np.ones(4) * 12
        D = np.ones(4) * 3

        # Should NOT raise for steps below tolerance
        for _ in range(_PE_ZERO_TOLERANCE_STEPS - 1):
            bridge.step(M, D)

        # Should raise on the tolerance-th step
        with pytest.raises(MeasurementFailureError, match="Pe=0"):
            bridge.step(M, D)

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_pe_zero_counter_resets_on_nonzero(self, mock_me):
        """A single step with Pe>0 resets the consecutive zero counter."""
        from engine.simulink_bridge import SimulinkBridge, _PE_ZERO_TOLERANCE_STEPS

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        cfg = _make_test_config()
        bridge = SimulinkBridge(cfg)
        bridge._matlab_cfg = MagicMock()
        bridge._SimulinkBridge__mdbl = lambda x: x

        M = np.ones(4) * 12
        D = np.ones(4) * 3

        # Two steps with Pe=0
        zero_state = {
            "omega": [[1.0]*4], "Pe": [[0.0]*4], "rocof": [[0.0]*4],
            "delta": [[0.0]*4], "delta_deg": [[0.0]*4],
        }
        zero_status = {"success": True, "error": "", "elapsed_ms": 5.0, "measurement_failures": []}
        mock_eng.slx_step_and_read = MagicMock(return_value=(zero_state, zero_status))
        bridge.step(M, D)
        bridge.step(M, D)
        assert bridge._pe_zero_count == 2

        # One step with Pe>0 resets counter
        nonzero_state = {
            "omega": [[1.0]*4], "Pe": [[0.5]*4], "rocof": [[0.0]*4],
            "delta": [[0.0]*4], "delta_deg": [[0.0]*4],
        }
        mock_eng.slx_step_and_read = MagicMock(return_value=(nonzero_state, zero_status))
        bridge.step(M, D)
        assert bridge._pe_zero_count == 0

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_measurement_failures_logged(self, mock_me, caplog):
        """Measurement failures from MATLAB are surfaced via Python logging."""
        from engine.simulink_bridge import SimulinkBridge

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        mock_state = {
            "omega": [[1.0]*4], "Pe": [[0.5]*4], "rocof": [[0.0]*4],
            "delta": [[0.0]*4], "delta_deg": [[0.0]*4],
        }
        mock_status = {
            "success": True, "error": "", "elapsed_ms": 5.0,
            "measurement_failures": ["omega:agent3:signal not found"],
        }
        mock_eng.slx_step_and_read = MagicMock(return_value=(mock_state, mock_status))

        cfg = _make_test_config()
        bridge = SimulinkBridge(cfg)
        bridge._matlab_cfg = MagicMock()
        bridge._SimulinkBridge__mdbl = lambda x: x

        import logging
        with caplog.at_level(logging.WARNING):
            bridge.step(np.ones(4) * 12, np.ones(4) * 3)

        assert "omega:agent3" in caplog.text

    def test_reset_clears_pe_zero_counter(self):
        """reset() must clear the Pe zero counter."""
        from engine.simulink_bridge import SimulinkBridge

        cfg = _make_test_config()
        bridge = SimulinkBridge(cfg)
        bridge._pe_zero_count = 5
        bridge.reset()
        assert bridge._pe_zero_count == 0


class TestBridgeConfigValidation:
    """Tests for BridgeConfig.__post_init__ validation."""

    def test_vi_mode_without_vabc_raises(self):
        """pe_measurement='vi' but no vabc_signal must raise."""
        from engine.simulink_bridge import BridgeConfig

        with pytest.raises(ValueError, match="pe_measurement='vi'"):
            BridgeConfig(
                model_name="bad_vi",
                model_dir="/tmp",
                n_agents=4,
                dt_control=0.2,
                sbase_va=100e6,
                m_path_template="{model}/M{idx}",
                d_path_template="{model}/D{idx}",
                omega_signal="omega_ES{idx}",
                vabc_signal="",       # empty!
                iabc_signal="",       # empty!
                pe_measurement="vi",
            )

    def test_pout_mode_without_p_out_signal_raises(self):
        """pe_measurement='pout' but no p_out_signal must raise."""
        from engine.simulink_bridge import BridgeConfig

        with pytest.raises(ValueError, match="pe_measurement='pout'"):
            BridgeConfig(
                model_name="bad_pout",
                model_dir="/tmp",
                n_agents=4,
                dt_control=0.2,
                sbase_va=100e6,
                m_path_template="{model}/M{idx}",
                d_path_template="{model}/D{idx}",
                omega_signal="omega_ES{idx}",
                vabc_signal="V{idx}",
                iabc_signal="I{idx}",
                pe_measurement="pout",
                p_out_signal="",      # empty!
            )

    def test_vi_then_pout_with_nothing_raises(self):
        """pe_measurement='vi_then_pout' with no signals at all must raise."""
        from engine.simulink_bridge import BridgeConfig

        with pytest.raises(ValueError, match="vi_then_pout"):
            BridgeConfig(
                model_name="bad_both",
                model_dir="/tmp",
                n_agents=4,
                dt_control=0.2,
                sbase_va=100e6,
                m_path_template="{model}/M{idx}",
                d_path_template="{model}/D{idx}",
                omega_signal="omega_ES{idx}",
                vabc_signal="",
                iabc_signal="",
                pe_measurement="vi_then_pout",
                p_out_signal="",
            )

    def test_invalid_pe_measurement_mode_raises(self):
        """Unknown pe_measurement mode must raise."""
        from engine.simulink_bridge import BridgeConfig

        with pytest.raises(ValueError, match="pe_measurement='bogus'"):
            BridgeConfig(
                model_name="bad_mode",
                model_dir="/tmp",
                n_agents=4,
                dt_control=0.2,
                sbase_va=100e6,
                m_path_template="{model}/M{idx}",
                d_path_template="{model}/D{idx}",
                omega_signal="omega_ES{idx}",
                vabc_signal="V{idx}",
                iabc_signal="I{idx}",
                pe_measurement="bogus",
            )

    def test_valid_config_with_pout_only(self):
        """Config with pe_measurement='pout' and p_out_signal should pass."""
        from engine.simulink_bridge import BridgeConfig

        cfg = BridgeConfig(
            model_name="pout_model",
            model_dir="/tmp",
            n_agents=4,
            dt_control=0.2,
            sbase_va=100e6,
            m_path_template="{model}/M{idx}",
            d_path_template="{model}/D{idx}",
            omega_signal="omega_ES{idx}",
            vabc_signal="",
            iabc_signal="",
            pe_measurement="pout",
            p_out_signal="P_out_ES{idx}",
        )
        assert cfg.pe_measurement == "pout"

    def test_valid_config_vi_mode(self):
        """Config with pe_measurement='vi' and V×I signals should pass."""
        from engine.simulink_bridge import BridgeConfig

        cfg = BridgeConfig(
            model_name="vi_model",
            model_dir="/tmp",
            n_agents=8,
            dt_control=0.2,
            sbase_va=100e6,
            m_path_template="{model}/M{idx}",
            d_path_template="{model}/D{idx}",
            omega_signal="omega_ES{idx}",
            vabc_signal="Vabc_ES{idx}",
            iabc_signal="Iabc_ES{idx}",
            pe_measurement="vi",
        )
        assert cfg.pe_measurement == "vi"

    def test_kundur_config_declares_feedback(self):
        """Kundur main training path must use pe_measurement='feedback' (Phase 1 fix)."""
        from scenarios.kundur.config_simulink import KUNDUR_BRIDGE_CONFIG
        assert KUNDUR_BRIDGE_CONFIG.pe_measurement == "feedback"

    def test_ne39_config_declares_vi(self):
        """NE39 scenario config must declare pe_measurement='vi'."""
        from scenarios.new_england.config_simulink import NE39_BRIDGE_CONFIG
        assert NE39_BRIDGE_CONFIG.pe_measurement == "vi"

    def test_missing_idx_placeholder_raises(self):
        """Template without {idx} should raise ValueError."""
        from engine.simulink_bridge import BridgeConfig

        with pytest.raises(ValueError, match="omega_signal.*missing.*idx"):
            BridgeConfig(
                model_name="bad_tmpl",
                model_dir="/tmp",
                n_agents=4,
                dt_control=0.2,
                sbase_va=100e6,
                m_path_template="{model}/M{idx}",
                d_path_template="{model}/D{idx}",
                omega_signal="omega_ES_FIXED",  # no {idx}!
                vabc_signal="V{idx}",
                iabc_signal="I{idx}",
            )

    def test_invalid_n_agents_raises(self):
        """n_agents < 1 should raise."""
        from engine.simulink_bridge import BridgeConfig

        with pytest.raises(ValueError, match="n_agents"):
            BridgeConfig(
                model_name="zero_agents",
                model_dir="/tmp",
                n_agents=0,
                dt_control=0.2,
                sbase_va=100e6,
                m_path_template="{model}/M{idx}",
                d_path_template="{model}/D{idx}",
                omega_signal="omega_ES{idx}",
                vabc_signal="V{idx}",
                iabc_signal="I{idx}",
            )

    def test_delta0_deg_wrong_length_raises(self):
        """delta0_deg with wrong length must raise."""
        from engine.simulink_bridge import BridgeConfig

        with pytest.raises(ValueError, match="delta0_deg"):
            BridgeConfig(
                model_name="bad_delta",
                model_dir="/tmp",
                n_agents=4,
                dt_control=0.2,
                sbase_va=100e6,
                m_path_template="{model}/M{idx}",
                d_path_template="{model}/D{idx}",
                omega_signal="omega_ES{idx}",
                vabc_signal="V{idx}",
                iabc_signal="I{idx}",
                delta0_deg=(18.0, 10.0),  # length 2, not 4
            )

    def test_delta0_deg_nonfinite_raises(self):
        """delta0_deg with NaN/inf must raise."""
        from engine.simulink_bridge import BridgeConfig

        with pytest.raises(ValueError, match="delta0_deg"):
            BridgeConfig(
                model_name="nan_delta",
                model_dir="/tmp",
                n_agents=4,
                dt_control=0.2,
                sbase_va=100e6,
                m_path_template="{model}/M{idx}",
                d_path_template="{model}/D{idx}",
                omega_signal="omega_ES{idx}",
                vabc_signal="V{idx}",
                iabc_signal="I{idx}",
                delta0_deg=(18.0, float("nan"), 7.0, 12.0),
            )

    def test_kundur_config_has_delta0_deg(self):
        """KUNDUR_BRIDGE_CONFIG must carry vsg_delta0_deg from kundur_ic.json."""
        from scenarios.kundur.config_simulink import KUNDUR_BRIDGE_CONFIG

        assert len(KUNDUR_BRIDGE_CONFIG.delta0_deg) == 4
        assert all(np.isfinite(v) for v in KUNDUR_BRIDGE_CONFIG.delta0_deg)


class TestWarmupDeltaSeeding:
    """Tests for SimulinkBridge.warmup() explicit reset vs episode-warmup dispatch."""

    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    def _make_bridge(self, mock_me, delta0_deg=()):
        from engine.simulink_bridge import BridgeConfig, SimulinkBridge

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        cfg = BridgeConfig(
            model_name="test_model",
            model_dir="/tmp",
            n_agents=4,
            dt_control=0.2,
            sbase_va=100e6,
            m_path_template="{model}/VSG_ES{idx}/M0",
            d_path_template="{model}/VSG_ES{idx}/D0",
            omega_signal="omega_ES{idx}",
            vabc_signal="Vabc_ES{idx}",
            iabc_signal="Iabc_ES{idx}",
            pe0_default_vsg=1.87,
            delta0_deg=delta0_deg,
        )
        bridge = SimulinkBridge(cfg)
        bridge._matlab_cfg = MagicMock()
        bridge._SimulinkBridge__mdbl = lambda x: x
        return bridge, mock_eng

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_warmup_without_delta_uses_fastrestart_reset(self, mock_me):
        """delta0_deg=() uses slx_fastrestart_reset and seeds zero delta."""
        bridge, mock_eng = self._make_bridge(mock_me, delta0_deg=())
        bridge.warmup(0.5)

        call_args_list = mock_eng.slx_fastrestart_reset.call_args_list
        assert len(call_args_list) == 1
        args = call_args_list[0][0]
        assert args[0] == "test_model"
        assert args[1] == pytest.approx(0.5)
        assert isinstance(args[2], bool)  # do_recompile flag
        assert mock_eng.slx_warmup.call_count == 0

        assert np.all(bridge._delta_prev_deg == 0.0)
        assert bridge._delta_prev_deg.shape == (4,)

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_warmup_with_delta_uses_episode_warmup(self, mock_me):
        """delta0_deg non-empty uses slx_episode_warmup and seeds delta from warmup_state."""
        bridge, mock_eng = self._make_bridge(mock_me, delta0_deg=(18.0, 10.0, 7.0, 12.0))

        mock_eng.slx_episode_warmup.return_value = (
            {"delta_deg": [17.8, 9.9, 6.8, 11.9], "Pe": [1.0, 1.0, 1.0, 1.0]},
            {"success": True},
        )
        # session.eval("kundur_ip", nargout=1) returns the struct
        mock_eng.eval.return_value = {}

        bridge.warmup(0.5)

        call_args_list = mock_eng.slx_episode_warmup.call_args_list
        assert len(call_args_list) == 1
        args = call_args_list[0][0]
        assert args[0] == "test_model"
        assert len(args) == 6
        assert mock_eng.slx_warmup.call_count == 0

        # _delta_prev_deg comes from warmup_state (clipped ±90°)
        assert np.allclose(bridge._delta_prev_deg, [17.8, 9.9, 6.8, 11.9], atol=1e-6)

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_warmup_pe_prev_nominal(self, mock_me):
        """_Pe_prev = nominal seed regardless of 3-arg or 6-arg path."""
        for delta0 in [(), (18.0, 10.0, 7.0, 12.0)]:
            from engine.matlab_session import MatlabSession
            MatlabSession._instances.clear()

            bridge, mock_eng = self._make_bridge(mock_me, delta0_deg=delta0)
            if delta0:
                mock_eng.slx_episode_warmup.return_value = (
                    {"delta_deg": list(delta0), "Pe": [1.0, 1.0, 1.0, 1.0]},
                    {"success": True},
                )
                mock_eng.eval.return_value = {}

            bridge.warmup(0.5)

            expected_pe = 1.87 / (100e6 / 200e6)  # pe_nominal_vsg / pe_scale = 1.87 * 2
            assert np.allclose(bridge._Pe_prev, np.full(4, expected_pe), rtol=1e-4), (
                f"delta0_deg={delta0}: _Pe_prev should be nominal {expected_pe:.4f}, "
                f"got {bridge._Pe_prev}"
            )


def test_kundur_default_profile_is_legacy():
    from scenarios.kundur.config_simulink import KUNDUR_MODEL_PROFILE
    assert KUNDUR_MODEL_PROFILE.profile_id == "kundur_ee_legacy"


def test_kundur_candidate_profile_can_be_selected(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "KUNDUR_MODEL_PROFILE",
        str(Path(__file__).resolve().parent.parent / "scenarios/kundur/model_profiles/kundur_sps_candidate.json"),
    )
    import importlib
    import scenarios.kundur.config_simulink as csim
    importlib.reload(csim)
    from scenarios.kundur.config_simulink import load_runtime_kundur_profile
    profile = load_runtime_kundur_profile()
    assert profile.profile_id == "kundur_sps_candidate"
