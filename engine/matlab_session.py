# engine/matlab_session.py
"""Layer 1: MatlabSession — MATLAB Engine lifecycle management.

Provides a singleton-per-session_id wrapper around matlab.engine with:
- Lazy initialization (engine starts on first call)
- Passive reconnect (no health-check ping; reconnect only on failure)
- Auto addpath for slx_helpers/ on first connect; vsg_bridge/ added lazily via add_vsg_bridge_path()
- Structured error wrapping via MatlabCallError
- DEBUG-level logging of every call() with elapsed time
"""

from __future__ import annotations

import io
import logging
import os
import time
from typing import Any, Optional

from engine.exceptions import MatlabCallError

logger = logging.getLogger(__name__)

matlab_engine = None  # lazy-loaded in _get_matlab_engine()


def _get_matlab_engine():
    """Lazy import of matlab.engine to avoid hanging on zombie MATLAB processes."""
    global matlab_engine
    if matlab_engine is None:
        try:
            import matlab.engine as _me
            matlab_engine = _me
        except ImportError:
            pass
    return matlab_engine


def _log_matlab_output(label: str, stdout: Any, stderr: Any) -> None:
    """Route any captured MATLAB console output to the Python logger."""
    stdout_text = stdout.getvalue() if hasattr(stdout, "getvalue") else ""
    stderr_text = stderr.getvalue() if hasattr(stderr, "getvalue") else ""
    if stdout_text.strip():
        logger.debug("MATLAB stdout [%s]: %s", label, stdout_text.strip())
    if stderr_text.strip():
        logger.warning("MATLAB stderr [%s]: %s", label, stderr_text.strip())


class MatlabSession:
    """Singleton MATLAB Engine session keyed by session_id.

    Usage::

        session = MatlabSession.get()          # default session
        result = session.call('sqrt', 4.0)     # calls MATLAB sqrt(4.0)
        session.close()                        # quit engine
    """

    _instances: dict[str, MatlabSession] = {}

    def __init__(self) -> None:
        self._eng: Any = None
        self._session_id: Optional[str] = None
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._helper_paths: list[str] = [
            os.path.join(project_root, "slx_helpers"),
        ]
        self._vsg_bridge_path: str = os.path.join(project_root, "slx_helpers", "vsg_bridge")
        self._vsg_bridge_added: bool = False

    @classmethod
    def get(cls, session_id: str = "default") -> MatlabSession:
        """Get or create a session instance by ID."""
        if session_id not in cls._instances:
            inst = cls()
            inst._session_id = session_id
            cls._instances[session_id] = inst
        return cls._instances[session_id]

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        """Start MATLAB engine and add helper paths."""
        if self._eng is not None:
            return
        me = _get_matlab_engine()
        if me is None:
            raise RuntimeError(
                "matlab.engine not available. Install via: "
                "pip install matlabengine"
            )
        logger.info("Starting MATLAB engine (session=%s) ...", self._session_id)
        self._eng = me.start_matlab()
        self._vsg_bridge_added = False  # reset so add_vsg_bridge_path() re-fires on next call
        # Auto-addpath for MATLAB helper layers. Keep these explicit instead
        # of using genpath so cache/build folders are not added accidentally.
        for helper_path in self._helper_paths:
            if os.path.isdir(helper_path):
                self._eng.addpath(helper_path, nargout=0)
                logger.debug("Added to MATLAB path: %s", helper_path)
            else:
                logger.warning("MATLAB helper dir not found: %s", helper_path)
        # Force UTF-8 character set so MATLAB stdout (e.g. Chinese error
        # messages) round-trips cleanly through MCP rather than getting
        # GBK-decoded as mojibake (Phase A.1 / plan §3.A.1).
        try:
            self._eng.feature("DefaultCharacterSet", "UTF-8", nargout=0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not set MATLAB DefaultCharacterSet=UTF-8: %s", exc)
        logger.info("MATLAB engine ready (session=%s).", self._session_id)

    def _get_engine(self) -> Any:
        """Return cached engine, connecting if needed."""
        if self._eng is None:
            self._connect()
        return self._eng

    def add_vsg_bridge_path(self) -> None:
        """Add slx_helpers/vsg_bridge/ to MATLAB path (lazy, idempotent).

        Called by SimulinkBridge on construction so that generic MCP tools
        that only use slx_helpers/ cannot accidentally resolve vsg_bridge-
        specific helpers (slx_step_and_read, slx_episode_warmup, etc.).
        """
        if self._vsg_bridge_added:
            return
        if not os.path.isdir(self._vsg_bridge_path):
            logger.warning("vsg_bridge helper dir not found: %s", self._vsg_bridge_path)
            return
        eng = self._get_engine()
        eng.addpath(self._vsg_bridge_path, nargout=0)
        self._vsg_bridge_added = True
        logger.debug("Added to MATLAB path: %s", self._vsg_bridge_path)

    @staticmethod
    def _is_communication_error(exc: Exception) -> bool:
        """Check if exception indicates a dead engine connection."""
        msg = str(exc).lower()
        return any(
            kw in msg
            for kw in ("rpc", "connection", "pipe", "broken", "terminated")
        )

    @staticmethod
    def _format_exception_message(exc: Exception) -> str:
        """Extract the most specific available error message from engine exceptions."""
        generic_messages = {"unknown exception", "exception", exc.__class__.__name__.lower()}
        ordered: list[str] = []

        def add(candidate: Any) -> None:
            if candidate in (None, ""):
                return
            text = str(candidate).strip()
            if text and text not in ordered:
                ordered.append(text)

        add(getattr(exc, "message", None))
        for arg in getattr(exc, "args", ()):
            add(arg)
        add(str(exc))
        add(getattr(exc, "reason", None))
        add(getattr(exc, "cause", None))
        if exc.__cause__ is not None:
            add(exc.__cause__)
        if exc.__context__ is not None and exc.__context__ is not exc.__cause__:
            add(exc.__context__)

        specific = [text for text in ordered if text.lower() not in generic_messages]
        if specific:
            return "; ".join(specific)
        if ordered:
            return ordered[0]
        return exc.__class__.__name__

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def call(
        self,
        func_name: str,
        *args: Any,
        nargout: int = 1,
        **kwargs: Any,
    ) -> Any:
        """Call a MATLAB function by name.

        Preferred over eval() – enables passive reconnect and structured
        error reporting.

        MATLAB console output (disp, fprintf, warnings) is captured into
        io.StringIO() by default to prevent it from leaking into Python's
        stdout and corrupting MCP's JSON-RPC transport.  Callers may supply
        their own ``stdout``/``stderr`` streams via kwargs to override.
        """
        eng = self._get_engine()
        t0 = time.perf_counter()
        timeout = kwargs.pop("timeout", None)
        # Pop stdout/stderr so we control where MATLAB output lands.
        # Default: io.StringIO() — output is captured and routed to logger.
        # background=True calls use a different code path; stdout/stderr are
        # not passed there because the async future pattern doesn't support it.
        _stdout: Any = kwargs.pop("stdout", io.StringIO())
        _stderr: Any = kwargs.pop("stderr", io.StringIO())

        def _invoke(target_eng: Any) -> Any:
            if timeout is None:
                return getattr(target_eng, func_name)(
                    *args, nargout=nargout, stdout=_stdout, stderr=_stderr, **kwargs
                )

            # background=True: skip stdout/stderr redirect (unsupported for async calls)
            call_kwargs = dict(kwargs)
            call_kwargs["background"] = True
            future = getattr(target_eng, func_name)(*args, nargout=nargout, **call_kwargs)
            if not hasattr(future, "result"):
                return future
            try:
                return future.result(timeout=timeout)
            except Exception as exc:
                exc_name = exc.__class__.__name__.lower()
                if "timeout" in exc_name:
                    raise TimeoutError(f"Timed out after {timeout}s") from exc
                raise

        try:
            result = _invoke(eng)
        except Exception as exc:
            if self._is_communication_error(exc):
                logger.warning(
                    "MATLAB engine communication lost, reconnecting ..."
                )
                self._eng = None
                eng = self._get_engine()
                try:
                    result = _invoke(eng)
                except Exception as exc2:
                    raise MatlabCallError(
                        func_name,
                        args,
                        self._format_exception_message(exc2),
                    ) from exc2
            else:
                raise MatlabCallError(
                    func_name,
                    args,
                    self._format_exception_message(exc),
                ) from exc

        elapsed = (time.perf_counter() - t0) * 1000
        logger.debug("MATLAB %s() -> %.1f ms", func_name, elapsed)

        # Log any MATLAB console output at debug/warning level
        _log_matlab_output(func_name, _stdout, _stderr)
        return result

    def eval(self, code: str, nargout: int = 0) -> Any:
        """Execute raw MATLAB code string (escape hatch).

        Prefer call() when possible — but unlike the original, this now
        wraps errors in MatlabCallError and handles reconnect identically
        to call().

        MATLAB console output is captured into io.StringIO() to prevent
        it from leaking into Python's stdout and corrupting MCP's JSON-RPC
        transport.  Captured text is routed to the Python logger instead.
        """
        eng = self._get_engine()
        _stdout = io.StringIO()
        _stderr = io.StringIO()
        try:
            result = eng.eval(code, nargout=nargout, stdout=_stdout, stderr=_stderr)
            _log_matlab_output(f"eval({code!r})", _stdout, _stderr)
            return result
        except Exception as exc:
            if self._is_communication_error(exc):
                # Log anything captured before the connection dropped, then retry
                _log_matlab_output(f"eval({code!r})", _stdout, _stderr)
                logger.warning(
                    "MATLAB engine communication lost, reconnecting ..."
                )
                self._eng = None
                eng = self._get_engine()
                _stdout2 = io.StringIO()
                _stderr2 = io.StringIO()
                try:
                    result = eng.eval(code, nargout=nargout, stdout=_stdout2, stderr=_stderr2)
                    _log_matlab_output(f"eval({code!r})", _stdout2, _stderr2)
                    return result
                except Exception as exc2:
                    raise MatlabCallError(
                        f"eval({code!r})",
                        (),
                        self._format_exception_message(exc2),
                    ) from exc2
            else:
                raise MatlabCallError(
                    f"eval({code!r})",
                    (),
                    self._format_exception_message(exc),
                ) from exc

    @property
    def engine(self) -> Any:
        """Direct engine access for interop with existing MCP tools."""
        return self._get_engine()

    def close(self) -> None:
        """Quit MATLAB engine and remove from instance registry."""
        if self._eng is not None:
            try:
                self._eng.quit()
            except Exception:
                pass
            self._eng = None
        if self._session_id and self._session_id in self._instances:
            del self._instances[self._session_id]
        logger.info("MATLAB session '%s' closed.", self._session_id)
