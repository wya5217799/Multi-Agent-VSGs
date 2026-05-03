"""Module γ — orchestrator unit tests (no MATLAB required).

Tests target pure-logic helpers in
``probes.kundur.probe_state._orchestrator``.  No subprocess is spawned
against a real probe run; the ``spawn_worker`` test uses a trivial
executable that exits 0 immediately.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from probes.kundur.probe_state._orchestrator import (
    slice_targets,
    spawn_worker,
    wait_for_all,
)


# ---------------------------------------------------------------------------
# slice_targets
# ---------------------------------------------------------------------------


class TestSliceTargets:
    def test_round_robin_balanced(self):
        result = slice_targets(["a", "b", "c", "d", "e", "f"], 2)
        assert result == [["a", "c", "e"], ["b", "d", "f"]]

    def test_round_robin_unbalanced(self):
        result = slice_targets(["a", "b", "c", "d", "e"], 2)
        assert result == [["a", "c", "e"], ["b", "d"]]

    def test_n_greater_than_targets(self):
        """N=4 with 2 targets: last 2 slices are empty."""
        result = slice_targets(["a", "b"], 4)
        assert result == [["a"], ["b"], [], []]

    def test_empty_targets(self):
        result = slice_targets([], 3)
        assert result == [[], [], []]

    def test_single_worker(self):
        """N=1 returns one slice containing all targets."""
        result = slice_targets(["a", "b", "c"], 1)
        assert result == [["a", "b", "c"]]

    def test_single_target_multiple_workers(self):
        result = slice_targets(["only"], 3)
        assert result == [["only"], [], []]

    def test_invalid_n_workers_zero(self):
        with pytest.raises(ValueError, match="n_workers must be >= 1"):
            slice_targets(["a"], 0)

    def test_invalid_n_workers_negative(self):
        with pytest.raises(ValueError, match="n_workers must be >= 1"):
            slice_targets(["a"], -1)

    def test_unsupported_strategy(self):
        with pytest.raises(NotImplementedError, match="unsupported slicing strategy"):
            slice_targets(["a"], 1, strategy="random")

    def test_round_robin_four_workers_six_targets(self):
        """Verify round-robin interleaving for 6 targets / 4 workers."""
        # targets[k::4] for k in 0..3
        result = slice_targets(["a", "b", "c", "d", "e", "f"], 4)
        assert result == [["a", "e"], ["b", "f"], ["c"], ["d"]]

    def test_returns_list_of_lists(self):
        """Return type is list[list[str]], not generator or tuple."""
        result = slice_targets(["x"], 2)
        assert isinstance(result, list)
        assert all(isinstance(s, list) for s in result)

    def test_preserves_order_within_slice(self):
        """Round-robin order within each slice matches source order."""
        targets = ["a", "b", "c", "d", "e", "f"]
        result = slice_targets(targets, 3)
        # Worker 0: a, d; Worker 1: b, e; Worker 2: c, f
        assert result[0] == ["a", "d"]
        assert result[1] == ["b", "e"]
        assert result[2] == ["c", "f"]


# ---------------------------------------------------------------------------
# spawn_worker + wait_for_all (using trivial "python -c exit(0)" subprocess)
# ---------------------------------------------------------------------------


class TestSpawnWorkerDummy:
    """Test spawn_worker mechanics using a subprocess that exits 0 immediately.

    Uses ``python -c "raise SystemExit(0)"`` as a dummy worker so the
    test never invokes ``python -m probes.kundur.probe_state``.
    Validates: argv construction, log file creation, process exit code
    collection via wait_for_all.

    The dummy process is not ``python -m probes.kundur.probe_state``; it
    exits immediately with code 0 without touching MATLAB.
    """

    def test_spawn_worker_empty_subset_raises(self, tmp_path):
        """spawn_worker with empty subset raises ValueError."""
        with pytest.raises(ValueError, match="empty subset"):
            spawn_worker(
                worker_idx=0,
                subset=[],
                worker_dir=tmp_path,
                base_args={},
                log_path=tmp_path / "probe.log",
            )

    def test_spawn_worker_creates_log_file(self, tmp_path, monkeypatch):
        """spawn_worker opens log_path for writing; dummy process writes nothing."""
        # Patch sys.executable to run a trivial command.
        # We monkeypatch subprocess.Popen to avoid spawning a real child that
        # calls python -m probes.kundur.probe_state.
        captured_argv = []
        original_popen = subprocess.Popen

        class FakePopen:
            def __init__(self, argv, stdout, stderr, env):
                captured_argv.extend(argv)
                self.pid = 99999
                # Immediately exit 0.
                self._returncode = 0

            def wait(self, timeout=None):
                return self._returncode

        monkeypatch.setattr(subprocess, "Popen", FakePopen)

        log_path = tmp_path / "probe.log"
        proc, log_handle = spawn_worker(
            worker_idx=0,
            subset=["dispatch_a"],
            worker_dir=tmp_path,
            base_args={},
            log_path=log_path,
        )
        log_handle.close()

        # Log file must have been created (opened for write).
        assert log_path.exists()

        # argv must contain the expected flags.
        assert "--phase" in captured_argv
        assert "1,2,3,4" in captured_argv  # worker 0 gets phases 1+2+3+4 (Phase 1 needed for subset validation)
        assert "--workers" in captured_argv
        assert "1" in captured_argv
        assert "--dispatch-subset" in captured_argv
        assert "dispatch_a" in captured_argv

    def test_spawn_worker_idx1_phase1_4(self, tmp_path, monkeypatch):
        """Worker index >= 1 receives --phase 1,4 (Phase 1 needed for subset validation)."""
        captured_argv = []

        class FakePopen:
            def __init__(self, argv, stdout, stderr, env):
                captured_argv.extend(argv)
                self.pid = 99998
                self._returncode = 0

            def wait(self, timeout=None):
                return self._returncode

        monkeypatch.setattr(subprocess, "Popen", FakePopen)
        log_path = tmp_path / "probe.log"
        proc, log_handle = spawn_worker(
            worker_idx=1,
            subset=["dispatch_b"],
            worker_dir=tmp_path,
            base_args={},
            log_path=log_path,
        )
        log_handle.close()

        idx_phase = captured_argv.index("--phase")
        phase_value = captured_argv[idx_phase + 1]
        assert phase_value == "1,4"  # workers 1..N-1 get phases 1+4 (Phase 1 needed for subset validation)

    def test_spawn_worker_base_args_passthrough(self, tmp_path, monkeypatch):
        """sim_duration, dispatch_mag, t_warmup_s are passed to worker argv."""
        captured_argv = []

        class FakePopen:
            def __init__(self, argv, stdout, stderr, env):
                captured_argv.extend(argv)
                self.pid = 99997
                self._returncode = 0

            def wait(self, timeout=None):
                return self._returncode

        monkeypatch.setattr(subprocess, "Popen", FakePopen)
        log_path = tmp_path / "probe.log"
        proc, log_handle = spawn_worker(
            worker_idx=0,
            subset=["d"],
            worker_dir=tmp_path,
            base_args={
                "sim_duration": 3.0,
                "dispatch_mag": 0.7,
                "t_warmup_s": 5.0,
            },
            log_path=log_path,
        )
        log_handle.close()

        argv_str = " ".join(str(a) for a in captured_argv)
        assert "--sim-duration" in argv_str
        assert "3.0" in argv_str
        assert "--dispatch-mag" in argv_str
        assert "0.7" in argv_str
        assert "--t-warmup-s" in argv_str
        assert "5.0" in argv_str

    def test_spawn_worker_fast_restart_true(self, tmp_path, monkeypatch):
        """fast_restart=True passes --fast-restart flag."""
        captured_argv = []

        class FakePopen:
            def __init__(self, argv, stdout, stderr, env):
                captured_argv.extend(argv)
                self.pid = 99996
                self._returncode = 0

            def wait(self, timeout=None):
                return self._returncode

        monkeypatch.setattr(subprocess, "Popen", FakePopen)
        log_path = tmp_path / "probe.log"
        proc, log_handle = spawn_worker(
            worker_idx=0,
            subset=["d"],
            worker_dir=tmp_path,
            base_args={"fast_restart": True},
            log_path=log_path,
        )
        log_handle.close()
        assert "--fast-restart" in captured_argv

    def test_spawn_worker_fast_restart_false(self, tmp_path, monkeypatch):
        """fast_restart=False passes --no-fast-restart flag."""
        captured_argv = []

        class FakePopen:
            def __init__(self, argv, stdout, stderr, env):
                captured_argv.extend(argv)
                self.pid = 99995
                self._returncode = 0

            def wait(self, timeout=None):
                return self._returncode

        monkeypatch.setattr(subprocess, "Popen", FakePopen)
        log_path = tmp_path / "probe.log"
        proc, log_handle = spawn_worker(
            worker_idx=0,
            subset=["d"],
            worker_dir=tmp_path,
            base_args={"fast_restart": False},
            log_path=log_path,
        )
        log_handle.close()
        assert "--no-fast-restart" in captured_argv


# ---------------------------------------------------------------------------
# wait_for_all (with real tiny subprocesses that exit immediately)
# ---------------------------------------------------------------------------


class TestWaitForAll:
    """Use real ``python -c "import sys; sys.exit(0)"`` subprocesses.

    These processes start and exit in < 1 second, never invoking MATLAB.
    """

    def _make_quick_worker(self, tmp_path: Path, exit_code: int, idx: int):
        """Spawn a subprocess that immediately exits with exit_code."""
        log_path = tmp_path / f"worker_{idx}.log"
        log_handle = log_path.open("w")
        proc = subprocess.Popen(
            [sys.executable, "-c", f"import sys; sys.exit({exit_code})"],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        return proc, log_handle

    def test_wait_for_all_exit_zero(self, tmp_path):
        """Two workers exit 0 — results contain (idx, 0, wall_s)."""
        proc0, lh0 = self._make_quick_worker(tmp_path, 0, 0)
        proc1, lh1 = self._make_quick_worker(tmp_path, 0, 1)
        workers = [(0, proc0, lh0), (1, proc1, lh1)]
        results = wait_for_all(workers, timeout_s=30.0)
        assert len(results) == 2
        exit_codes = {idx: ec for idx, ec, _ in results}
        assert exit_codes[0] == 0
        assert exit_codes[1] == 0
        assert all(w >= 0 for _, _, w in results)

    def test_wait_for_all_non_zero_exit(self, tmp_path):
        """Worker exits with non-zero — exit_code preserved in result."""
        proc, lh = self._make_quick_worker(tmp_path, 2, 0)
        results = wait_for_all([(0, proc, lh)], timeout_s=30.0)
        assert len(results) == 1
        idx, ec, w = results[0]
        assert idx == 0
        assert ec == 2

    def test_wait_for_all_closes_log_handles(self, tmp_path):
        """Log handle is closed after wait_for_all returns."""
        proc, lh = self._make_quick_worker(tmp_path, 0, 0)
        wait_for_all([(0, proc, lh)], timeout_s=30.0)
        assert lh.closed

    def test_wait_for_all_returns_wall_seconds(self, tmp_path):
        """Wall time is a non-negative float."""
        proc, lh = self._make_quick_worker(tmp_path, 0, 0)
        results = wait_for_all([(0, proc, lh)], timeout_s=30.0)
        assert len(results) == 1
        _, _, w = results[0]
        assert isinstance(w, float)
        assert w >= 0.0

    def test_wait_for_all_empty_workers(self):
        """Empty workers list returns empty results."""
        results = wait_for_all([], timeout_s=30.0)
        assert results == []

    def test_wait_for_all_no_timeout(self, tmp_path):
        """timeout_s=None (no timeout) works correctly."""
        proc, lh = self._make_quick_worker(tmp_path, 0, 0)
        results = wait_for_all([(0, proc, lh)], timeout_s=None)
        assert results[0][1] == 0
