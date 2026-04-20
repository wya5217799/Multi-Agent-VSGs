# tests/test_perf_warmup_fr.py
"""Opt-B: Skip FastRestart off→on recompile after the first episode.

Profiling showed warmup costs ~13 500 ms/episode (37% of episode time).
The recompile is triggered by FastRestart off→on inside slx_warmup.m.
After the first episode the model is already compiled; only the Simscape
initial state needs to be reset, which happens automatically when sim() is
called with a StopTime lower than the current simulation time.

⚠️  ASSUMPTION (Issue #4, code review):
The fast path relies on Simulink FastRestart resetting Simscape initial
conditions when StopTime < current_sim_time.  This is NOT documented
behavior for Simscape DAE solvers in R2025b.  The Python tests here verify
the flag/dispatch logic only.  The physics correctness MUST be verified by
running `scripts/profile_one_episode.py` with TWO episodes and checking that
omega after warmup is ~1.0 p.u. in both episodes.

Contract:
  - SimulinkBridge grows a `_fr_compiled: bool` flag (starts False)
  - warmup() passes do_recompile=True on the FIRST call  → FR off→on runs
  - warmup() passes do_recompile=False on SUBSEQUENT calls → FR off→on skipped
  - reset() does NOT clear _fr_compiled (no recompile needed between episodes)

TDD RED → GREEN:
  RED : _fr_compiled attribute missing, slx_warmup called without do_recompile arg
  GREEN: all pass after changes to SimulinkBridge + slx_warmup.m
"""
import pytest
from unittest.mock import MagicMock, call, patch
import numpy as np


def _make_cfg():
    from engine.simulink_bridge import BridgeConfig
    return BridgeConfig(
        model_name="kundur_vsg",
        model_dir="/tmp/test",
        n_agents=4,
        dt_control=0.2,
        sbase_va=100e6,
        m_path_template="{model}/VSG_ES{idx}/M0",
        d_path_template="{model}/VSG_ES{idx}/D0",
        omega_signal="omega_ES{idx}",
        vabc_signal="Vabc_ES{idx}",
        iabc_signal="Iabc_ES{idx}",
    )


def _make_bridge_with_mock_session():
    """Return (bridge, mock_eng) with MATLAB engine fully mocked."""
    from engine.matlab_session import MatlabSession
    MatlabSession._instances.clear()

    mock_eng = MagicMock()
    # slx_warmup returns nothing (nargout=0)
    mock_eng.slx_warmup = MagicMock(return_value=None)

    with patch("engine.matlab_session.matlab_engine") as mock_me:
        mock_me.start_matlab.return_value = mock_eng
        from engine.simulink_bridge import SimulinkBridge
        bridge = SimulinkBridge(_make_cfg())
        # Force session to use our mock engine
        bridge.session._eng = mock_eng

    return bridge, mock_eng


# ---------------------------------------------------------------------------
# Attribute presence
# ---------------------------------------------------------------------------

class TestFrCompiledFlag:

    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    def test_bridge_has_fr_compiled_attribute(self):
        from engine.simulink_bridge import SimulinkBridge
        bridge = SimulinkBridge(_make_cfg())
        assert hasattr(bridge, "_fr_compiled"), (
            "SimulinkBridge must have a _fr_compiled attribute for FR optimisation"
        )

    def test_fr_compiled_starts_false(self):
        from engine.simulink_bridge import SimulinkBridge
        bridge = SimulinkBridge(_make_cfg())
        assert bridge._fr_compiled is False, (
            "_fr_compiled must start False so first warmup triggers recompile"
        )

    def test_reset_does_not_clear_fr_compiled(self):
        """reset() is called between episodes; compiled model must be kept."""
        from engine.simulink_bridge import SimulinkBridge
        bridge = SimulinkBridge(_make_cfg())
        bridge._fr_compiled = True   # simulate post-first-warmup state

        bridge.reset()

        assert bridge._fr_compiled is True, (
            "reset() must NOT clear _fr_compiled — model stays compiled between episodes"
        )


# ---------------------------------------------------------------------------
# slx_warmup call signature
# ---------------------------------------------------------------------------

class TestWarmupPassesRecompileFlag:

    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_first_warmup_passes_do_recompile_true(self, mock_me):
        """First warmup must pass do_recompile=True so FR off→on runs."""
        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        from engine.simulink_bridge import SimulinkBridge
        bridge = SimulinkBridge(_make_cfg())

        assert bridge._fr_compiled is False   # guard: starting state

        bridge.warmup(0.5)

        # slx_warmup should have been called with exactly 3 positional args:
        #   (model_name, duration, do_recompile)
        # The 3rd arg must be True on the first call.
        calls = mock_eng.slx_warmup.call_args_list
        assert len(calls) >= 1, "slx_warmup must be called at least once"
        positional_args = calls[0][0]  # first call, positional args tuple
        assert len(positional_args) == 3, (
            f"slx_warmup must receive 3 positional args (model, duration, do_recompile), "
            f"got {len(positional_args)}: {positional_args}"
        )
        assert positional_args[2] is True, (
            f"3rd arg (do_recompile) must be True on first warmup, got {positional_args[2]}"
        )

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_first_warmup_sets_fr_compiled_true(self, mock_me):
        """After the first warmup _fr_compiled must flip to True."""
        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        from engine.simulink_bridge import SimulinkBridge
        bridge = SimulinkBridge(_make_cfg())

        bridge.warmup(0.5)

        assert bridge._fr_compiled is True, (
            "_fr_compiled must be True after first warmup so subsequent calls skip recompile"
        )

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_second_warmup_passes_do_recompile_false(self, mock_me):
        """Subsequent warmups must pass do_recompile=False — skip the expensive recompile."""
        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        from engine.simulink_bridge import SimulinkBridge
        bridge = SimulinkBridge(_make_cfg())

        bridge.warmup(0.5)   # first call  — sets _fr_compiled=True
        bridge.reset()        # episode reset — must NOT clear _fr_compiled
        bridge.warmup(0.5)   # second call — should NOT recompile

        calls = mock_eng.slx_warmup.call_args_list
        assert len(calls) >= 2, "slx_warmup must be called at least twice"
        second_call_args = calls[1][0]
        assert len(second_call_args) == 3, (
            f"Second slx_warmup call must still pass 3 args, got {len(second_call_args)}"
        )
        assert second_call_args[2] is False, (
            f"3rd arg (do_recompile) must be False on second+ warmup, "
            f"got {second_call_args[2]}"
        )

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_ten_episodes_only_compile_once(self, mock_me):
        """Across 10 episode resets, FR recompile must happen exactly once."""
        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        from engine.simulink_bridge import SimulinkBridge
        bridge = SimulinkBridge(_make_cfg())

        for _ in range(10):
            bridge.reset()
            bridge.warmup(0.5)

        calls = mock_eng.slx_warmup.call_args_list
        assert len(calls) == 10

        recompile_flags = [c[0][2] for c in calls]  # 3rd positional arg of each call
        true_count = sum(1 for f in recompile_flags if f is True)
        assert true_count == 1, (
            f"do_recompile=True should appear exactly once across 10 warmups, "
            f"got {true_count} times. Flags: {recompile_flags}"
        )


# ---------------------------------------------------------------------------
# close() must reset flags (code review issue #1/#2)
# ---------------------------------------------------------------------------

class TestCloseResetsFlags:
    """Verify that close() clears _fr_compiled and _model_loaded.

    If close() does not reset these, a reused bridge instance will skip
    recompile on a freshly-loaded (uncompiled) model → silent IC corruption.
    """

    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_close_resets_fr_compiled(self, mock_me):
        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        from engine.simulink_bridge import SimulinkBridge
        bridge = SimulinkBridge(_make_cfg())
        bridge._fr_compiled = True      # simulate post-warmup state

        bridge.close()

        assert bridge._fr_compiled is False, (
            "close() must reset _fr_compiled so next warmup() triggers recompile"
        )

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_close_resets_model_loaded(self, mock_me):
        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        from engine.simulink_bridge import SimulinkBridge
        bridge = SimulinkBridge(_make_cfg())
        bridge._model_loaded = True     # simulate post-load_model state

        bridge.close()

        assert bridge._model_loaded is False, (
            "close() must reset _model_loaded so load_model() reruns on next use"
        )

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_warmup_recompiles_after_close_and_reload(self, mock_me):
        """close() + load_model() + warmup() must recompile even if model was warm."""
        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        from engine.simulink_bridge import SimulinkBridge
        bridge = SimulinkBridge(_make_cfg())

        # Simulate a first training run: warmup runs, model gets compiled
        bridge.warmup(0.5)
        assert bridge._fr_compiled is True

        # Simulate env.close() at end of training
        bridge.close()
        assert bridge._fr_compiled is False

        # Simulate reuse: load_model() + warmup() again
        bridge.load_model()
        bridge.warmup(0.5)

        calls = mock_eng.slx_warmup.call_args_list
        # The second warmup() call (after close) must pass do_recompile=True
        second_call_args = calls[1][0]
        assert second_call_args[2] is True, (
            "warmup() after close()+load_model() must pass do_recompile=True; "
            f"got {second_call_args[2]}"
        )
