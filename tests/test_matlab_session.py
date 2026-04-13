# tests/test_matlab_session.py
"""Tests for engine.exceptions and engine.matlab_session."""
import io
import logging
import pytest
from unittest.mock import ANY, MagicMock, patch


class TestMatlabCallError:
    def test_stores_function_name_and_args(self):
        from engine.exceptions import MatlabCallError
        err = MatlabCallError("vsg_step_and_read", (1, 2), "Division by zero")
        assert err.func_name == "vsg_step_and_read"
        assert err.args_passed == (1, 2)
        assert "vsg_step_and_read" in str(err)
        assert "Division by zero" in str(err)

    def test_is_exception(self):
        from engine.exceptions import MatlabCallError
        err = MatlabCallError("foo", (), "bar")
        assert isinstance(err, RuntimeError)


class TestSimulinkError:
    def test_stores_message(self):
        from engine.exceptions import SimulinkError
        err = SimulinkError("Simulation diverged at t=1.2")
        assert "diverged" in str(err)
        assert isinstance(err, RuntimeError)


class TestMatlabSessionSingleton:
    """Test session_id-keyed singleton pattern."""

    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_get_returns_same_instance(self, mock_me):
        from engine.matlab_session import MatlabSession
        mock_me.start_matlab.return_value = MagicMock()
        s1 = MatlabSession.get("default")
        s2 = MatlabSession.get("default")
        assert s1 is s2

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_different_session_ids_give_different_instances(self, mock_me):
        from engine.matlab_session import MatlabSession
        mock_me.start_matlab.return_value = MagicMock()
        s1 = MatlabSession.get("train")
        s2 = MatlabSession.get("mcp")
        assert s1 is not s2


class TestMatlabSessionCall:
    """Test the call() method — the main entry point."""

    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_call_delegates_to_engine(self, mock_me):
        from engine.matlab_session import MatlabSession
        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.my_func = MagicMock(return_value=42)

        session = MatlabSession.get()
        session._connect()
        result = session.call("my_func", 1, 2, nargout=1)

        # stdout/stderr are now injected by default to prevent JSON-RPC corruption
        mock_eng.my_func.assert_called_once_with(1, 2, nargout=1, stdout=ANY, stderr=ANY)
        assert result == 42

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_call_wraps_error_in_MatlabCallError(self, mock_me):
        from engine.matlab_session import MatlabSession
        from engine.exceptions import MatlabCallError
        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.bad_func = MagicMock(side_effect=Exception("MATLAB error"))
        mock_me.EngineError = type("EngineError", (Exception,), {})
        mock_me.MatlabExecutionError = type("MatlabExecutionError", (Exception,), {})

        session = MatlabSession.get()
        session._connect()
        with pytest.raises(MatlabCallError, match="bad_func"):
            session.call("bad_func", 3)

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_call_uses_background_future_when_timeout_requested(self, mock_me):
        from engine.matlab_session import MatlabSession

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        future = MagicMock()
        future.result.return_value = 42
        mock_eng.my_func = MagicMock(return_value=future)

        session = MatlabSession.get()
        session._connect()
        result = session.call("my_func", 1, nargout=1, timeout=5)

        # background=True path does NOT inject stdout/stderr (async calls don't support it)
        mock_eng.my_func.assert_called_once_with(1, nargout=1, background=True)
        future.result.assert_called_once_with(timeout=5)
        assert result == 42

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_call_preserves_specific_message_when_engine_only_reports_unknown_exception(self, mock_me):
        from engine.matlab_session import MatlabSession
        from engine.exceptions import MatlabCallError

        class FakeUnknownException(Exception):
            def __init__(self):
                super().__init__("Unknown exception", "Undefined function 'load_system_path_bootstrap'")
                self.message = "Undefined function 'load_system_path_bootstrap'"

            def __str__(self):
                return "Unknown exception"

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.bad_func = MagicMock(side_effect=FakeUnknownException())

        session = MatlabSession.get()
        session._connect()

        with pytest.raises(MatlabCallError) as exc_info:
            session.call("bad_func", "mdl")

        message = str(exc_info.value)
        assert "Undefined function 'load_system_path_bootstrap'" in message
        assert "Unknown exception" not in message

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_close_removes_from_instances(self, mock_me):
        from engine.matlab_session import MatlabSession
        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        session = MatlabSession.get("closeme")
        session._connect()
        session.close()
        assert "closeme" not in MatlabSession._instances


class TestMatlabSessionAddpath:
    """Test auto-addpath for vsg_helpers/."""

    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_connect_calls_addpath(self, mock_me):
        from engine.matlab_session import MatlabSession
        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        session = MatlabSession.get()
        session._connect()

        calls = [str(c) for c in mock_eng.addpath.call_args_list]
        assert any("vsg_helpers" in c for c in calls), \
            f"addpath not called with vsg_helpers path. Calls: {calls}"


class TestMatlabSessionEval:
    """Test the eval() method — error wrapping and reconnect logic."""

    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_eval_wraps_error_in_MatlabCallError(self, mock_me):
        from engine.matlab_session import MatlabSession
        from engine.exceptions import MatlabCallError
        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.eval = MagicMock(side_effect=Exception("undefined variable 'x'"))

        session = MatlabSession.get()
        session._connect()
        with pytest.raises(MatlabCallError) as exc_info:
            session.eval("disp(x)", nargout=0)

        assert "eval" in str(exc_info.value).lower()
        assert "undefined variable" in str(exc_info.value)

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_eval_reconnects_on_communication_error(self, mock_me):
        from engine.matlab_session import MatlabSession
        from engine.exceptions import MatlabCallError
        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        call_count = 0
        def fake_eval(code, nargout, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("rpc connection broken")
            return None

        mock_eng.eval = MagicMock(side_effect=fake_eval)

        session = MatlabSession.get()
        session._connect()
        session.eval("x = 1;", nargout=0)
        assert call_count == 2


class TestMatlabStdoutIsolation:
    """Verify MATLAB output is captured and does not leak to sys.stdout."""

    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_call_passes_stringio_stdout_to_engine(self, mock_me):
        """call() injects io.StringIO buffers so MATLAB output never hits sys.stdout."""
        from engine.matlab_session import MatlabSession
        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.my_func = MagicMock(return_value=None)

        session = MatlabSession.get()
        session._connect()
        session.call("my_func", nargout=0)

        call_kwargs = mock_eng.my_func.call_args.kwargs
        assert "stdout" in call_kwargs
        assert "stderr" in call_kwargs
        assert hasattr(call_kwargs["stdout"], "write"), "stdout must be a writable stream"
        assert hasattr(call_kwargs["stderr"], "write"), "stderr must be a writable stream"

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_call_caller_supplied_streams_are_honoured(self, mock_me):
        """A caller-supplied stdout stream overrides the default io.StringIO()."""
        from engine.matlab_session import MatlabSession
        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.my_func = MagicMock(return_value=None)

        custom_stdout = io.StringIO()
        session = MatlabSession.get()
        session._connect()
        session.call("my_func", nargout=0, stdout=custom_stdout)

        assert mock_eng.my_func.call_args.kwargs["stdout"] is custom_stdout

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_call_captured_output_logged_at_debug(self, mock_me, caplog):
        """MATLAB stdout text is forwarded to logger.debug, not printed."""
        from engine.matlab_session import MatlabSession

        def fake_func(*args, nargout=1, stdout=None, stderr=None, **kw):
            if stdout is not None:
                stdout.write("MATLAB disp output\n")
            return None

        mock_eng = MagicMock()
        mock_eng.my_func = MagicMock(side_effect=fake_func)
        mock_me.start_matlab.return_value = mock_eng

        session = MatlabSession.get()
        session._connect()
        with caplog.at_level(logging.DEBUG, logger="engine.matlab_session"):
            session.call("my_func", nargout=0)

        assert any("MATLAB disp output" in r.message for r in caplog.records)

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_eval_passes_stringio_to_engine_eval(self, mock_me):
        """eval() injects io.StringIO so MATLAB output never hits sys.stdout."""
        from engine.matlab_session import MatlabSession
        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.eval = MagicMock(return_value=None)

        session = MatlabSession.get()
        session._connect()
        session.eval("disp('hi')", nargout=0)

        call_kwargs = mock_eng.eval.call_args.kwargs
        assert "stdout" in call_kwargs
        assert "stderr" in call_kwargs
        assert hasattr(call_kwargs["stdout"], "write")
