"""Tests for simulink_run_script_async and simulink_poll_script (D1).

All tests mock simulink_run_script so no MATLAB engine is needed.
"""
import threading
from unittest.mock import patch

from engine.mcp_simulink_tools import (
    _SCRIPT_JOBS,
    _SCRIPT_JOB_LOCK,
    simulink_poll_script,
    simulink_run_script_async,
)


def _clear_jobs():
    """Helper: drain the module-level job registry between tests."""
    with _SCRIPT_JOB_LOCK:
        _SCRIPT_JOBS.clear()


def _wait_done(job_id: str, timeout: float = 3.0) -> None:
    """Block until the done_event for job_id is set."""
    with _SCRIPT_JOB_LOCK:
        job = _SCRIPT_JOBS.get(job_id)
    if job:
        job["done_event"].wait(timeout=timeout)


# ---------------------------------------------------------------------------
# simulink_run_script_async
# ---------------------------------------------------------------------------

class TestRunScriptAsync:

    def setup_method(self):
        _clear_jobs()

    def test_returns_job_id_immediately(self):
        gate = threading.Event()

        def slow_run_script(code_or_file, timeout_sec=120):
            gate.wait(timeout=5)
            return {"ok": True, "elapsed": 1.0, "n_warnings": 0, "n_errors": 0,
                    "error_message": "", "important_lines": []}

        with patch("engine.mcp_simulink_tools.simulink_run_script", side_effect=slow_run_script):
            result = simulink_run_script_async("test_script")

        try:
            assert result["ok"] is True
            assert len(result["job_id"]) == 8
            assert result["status"] == "running"
            assert result["job_id"] in result["message"]
        finally:
            gate.set()

    def test_job_registered_in_dict(self):
        gate = threading.Event()

        def slow_run_script(code_or_file, timeout_sec=120):
            gate.wait(timeout=5)
            return {"ok": True, "elapsed": 0.5, "n_warnings": 0, "n_errors": 0,
                    "error_message": "", "important_lines": []}

        with patch("engine.mcp_simulink_tools.simulink_run_script", side_effect=slow_run_script):
            result = simulink_run_script_async("test_script")
            job_id = result["job_id"]
            with _SCRIPT_JOB_LOCK:
                assert job_id in _SCRIPT_JOBS

        gate.set()

    def test_busy_when_job_already_running(self):
        gate = threading.Event()

        def slow_run_script(code_or_file, timeout_sec=120):
            gate.wait(timeout=5)
            return {"ok": True, "elapsed": 0.5, "n_warnings": 0, "n_errors": 0,
                    "error_message": "", "important_lines": []}

        with patch("engine.mcp_simulink_tools.simulink_run_script", side_effect=slow_run_script):
            simulink_run_script_async("first_script")
            second = simulink_run_script_async("second_script")

        try:
            assert second["ok"] is False
            assert second["status"] == "busy"
            assert "already running" in second["error_message"].lower()
        finally:
            gate.set()


# ---------------------------------------------------------------------------
# simulink_poll_script
# ---------------------------------------------------------------------------

class TestPollScript:

    def setup_method(self):
        _clear_jobs()

    def test_not_found_for_unknown_job_id(self):
        result = simulink_poll_script("deadbeef")
        assert result["ok"] is False
        assert result["status"] == "not_found"
        assert result["job_id"] == "deadbeef"

    def test_running_while_in_progress(self):
        gate = threading.Event()

        def slow_run_script(code_or_file, timeout_sec=120):
            gate.wait(timeout=5)
            return {"ok": True, "elapsed": 0.5, "n_warnings": 0, "n_errors": 0,
                    "error_message": "", "important_lines": []}

        with patch("engine.mcp_simulink_tools.simulink_run_script", side_effect=slow_run_script):
            start_result = simulink_run_script_async("my_build")
            job_id = start_result["job_id"]
            poll_result = simulink_poll_script(job_id)

        try:
            assert poll_result["ok"] is True
            assert poll_result["status"] == "running"
            assert poll_result["elapsed_sec"] >= 0
        finally:
            gate.set()

    def test_done_after_completion(self):
        def fast_run_script(code_or_file, timeout_sec=120):
            return {"ok": True, "elapsed": 0.1, "n_warnings": 1, "n_errors": 0,
                    "error_message": "", "important_lines": ["RESULT: done"]}

        with patch("engine.mcp_simulink_tools.simulink_run_script", side_effect=fast_run_script):
            start_result = simulink_run_script_async("quick_script")
            job_id = start_result["job_id"]
            _wait_done(job_id)
            poll_result = simulink_poll_script(job_id)

        assert poll_result["ok"] is True
        assert poll_result["status"] == "done"
        assert poll_result["n_warnings"] == 1
        assert poll_result["n_errors"] == 0
        assert poll_result["important_lines"] == ["RESULT: done"]
        assert poll_result["elapsed_sec"] >= 0

    def test_done_evicts_job_from_registry(self):
        """Polling a completed job removes it from _SCRIPT_JOBS (no memory leak)."""
        def fast_run_script(code_or_file, timeout_sec=120):
            return {"ok": True, "elapsed": 0.0, "n_warnings": 0, "n_errors": 0,
                    "error_message": "", "important_lines": []}

        with patch("engine.mcp_simulink_tools.simulink_run_script", side_effect=fast_run_script):
            start_result = simulink_run_script_async("evict_script")
            job_id = start_result["job_id"]
            _wait_done(job_id)
            poll_result = simulink_poll_script(job_id)

        assert poll_result["status"] == "done"
        with _SCRIPT_JOB_LOCK:
            assert job_id not in _SCRIPT_JOBS

    def test_evicted_job_returns_not_found_on_second_poll(self):
        """Second poll after eviction returns not_found (expected caller behaviour)."""
        def fast_run_script(code_or_file, timeout_sec=120):
            return {"ok": True, "elapsed": 0.0, "n_warnings": 0, "n_errors": 0,
                    "error_message": "", "important_lines": []}

        with patch("engine.mcp_simulink_tools.simulink_run_script", side_effect=fast_run_script):
            start_result = simulink_run_script_async("evict_script2")
            job_id = start_result["job_id"]
            _wait_done(job_id)
            simulink_poll_script(job_id)           # first poll — evicts
            second_poll = simulink_poll_script(job_id)  # second poll — not_found

        assert second_poll["status"] == "not_found"

    def test_done_with_script_failure(self):
        def failing_run_script(code_or_file, timeout_sec=120):
            return {"ok": False, "elapsed": 0.2, "n_warnings": 0, "n_errors": 1,
                    "error_message": "Undefined function 'bad_func'",
                    "important_lines": ["error: bad_func"]}

        with patch("engine.mcp_simulink_tools.simulink_run_script", side_effect=failing_run_script):
            start_result = simulink_run_script_async("bad_script")
            job_id = start_result["job_id"]
            _wait_done(job_id)
            poll_result = simulink_poll_script(job_id)

        assert poll_result["ok"] is False
        assert poll_result["status"] == "done"
        assert poll_result["n_errors"] == 1
        assert "bad_func" in poll_result["error_message"]

    def test_done_when_run_script_raises(self):
        def raising_run_script(code_or_file, timeout_sec=120):
            raise RuntimeError("Engine crashed")

        with patch("engine.mcp_simulink_tools.simulink_run_script", side_effect=raising_run_script):
            start_result = simulink_run_script_async("crash_script")
            job_id = start_result["job_id"]
            _wait_done(job_id)
            poll_result = simulink_poll_script(job_id)

        assert poll_result["ok"] is False
        assert poll_result["status"] == "done"
        assert "Engine crashed" in poll_result["error_message"]

    def test_second_job_allowed_after_first_completes(self):
        """busy guard releases once done_event is set — no thread.join() needed."""
        def fast_run_script(code_or_file, timeout_sec=120):
            return {"ok": True, "elapsed": 0.0, "n_warnings": 0, "n_errors": 0,
                    "error_message": "", "important_lines": []}

        with patch("engine.mcp_simulink_tools.simulink_run_script", side_effect=fast_run_script):
            first = simulink_run_script_async("script_1")
            # Wait only for done_event — this is what the busy guard checks
            _wait_done(first["job_id"])
            second = simulink_run_script_async("script_2")

        assert second["ok"] is True
        assert second["status"] == "running"
        assert second["job_id"] != first["job_id"]
        _wait_done(second["job_id"])


# ---------------------------------------------------------------------------
# PUBLIC_TOOLS contract
# ---------------------------------------------------------------------------

class TestPublicToolsD1:

    def test_async_tools_in_public_tools(self):
        from engine import mcp_server
        names = [t.__name__ for t in mcp_server.PUBLIC_TOOLS]
        assert "simulink_run_script_async" in names
        assert "simulink_poll_script" in names

    def test_async_tools_adjacent_to_run_script(self):
        from engine import mcp_server
        names = [t.__name__ for t in mcp_server.PUBLIC_TOOLS]
        run_idx = names.index("simulink_run_script")
        async_idx = names.index("simulink_run_script_async")
        poll_idx = names.index("simulink_poll_script")
        assert async_idx == run_idx + 1
        assert poll_idx == run_idx + 2
