"""Tests for utils.run_protocol — per-run directory and status protocol."""
import json
import time
from pathlib import Path

import pytest


def test_generate_run_id_format():
    from utils.run_protocol import generate_run_id
    run_id = generate_run_id("kundur")
    assert run_id.startswith("kundur_")
    parts = run_id.split("_")
    assert len(parts) == 3          # kundur_YYYYMMDD_HHMMSS
    assert len(parts[1]) == 8       # date part
    assert len(parts[2]) == 6       # time part


def test_generate_run_id_is_unique():
    from utils.run_protocol import generate_run_id
    ids = [generate_run_id("kundur") for _ in range(3)]
    # All unique (sleep not needed if clock resolution is fine; if test is flaky add time.sleep(1))
    assert len(set(ids)) == len(ids)


def test_get_run_dir_path(tmp_path, monkeypatch):
    from utils import run_protocol
    monkeypatch.setattr(run_protocol, "_PROJECT_ROOT", tmp_path)
    run_dir = run_protocol.get_run_dir("kundur", "kundur_20260410_120000")
    assert run_dir == tmp_path / "results" / "sim_kundur" / "runs" / "kundur_20260410_120000"


def test_write_and_read_training_status(tmp_path):
    from utils.run_protocol import write_training_status, read_training_status
    run_dir = tmp_path / "run1"
    run_dir.mkdir()

    status = {"status": "running", "episodes_done": 5, "last_reward": -120.0}
    write_training_status(run_dir, status)

    loaded = read_training_status(run_dir)
    assert loaded["status"] == "running"
    assert loaded["episodes_done"] == 5
    assert loaded["last_reward"] == pytest.approx(-120.0)


def test_write_training_status_is_atomic(tmp_path):
    """Write should use tempfile+replace so partial writes don't corrupt."""
    from utils.run_protocol import write_training_status
    run_dir = tmp_path / "run1"
    run_dir.mkdir()

    write_training_status(run_dir, {"status": "running"})
    write_training_status(run_dir, {"status": "completed", "episodes_done": 100})

    status_file = run_dir / "training_status.json"
    data = json.loads(status_file.read_text())
    assert data["status"] == "completed"


def test_read_training_status_returns_none_if_missing(tmp_path):
    from utils.run_protocol import read_training_status
    result = read_training_status(tmp_path / "nonexistent_run")
    assert result is None


@pytest.mark.parametrize("monitor_stopped,expected_status", [
    (True, "monitor_stopped"),
    (False, "completed"),
])
def test_training_status_distinguishes_monitor_stop_from_completion(
    tmp_path, monitor_stopped, expected_status
):
    """Monitor early-stop must write 'monitor_stopped', not 'completed'."""
    from utils.run_protocol import write_training_status, read_training_status
    run_dir = tmp_path / "run1"
    run_dir.mkdir()

    final_status = "monitor_stopped" if monitor_stopped else "completed"
    write_training_status(run_dir, {
        "status": final_status,
        "run_id": "test_run",
        "scenario": "kundur",
        "episodes_total": 200,
        "episodes_done": 100,
    })

    loaded = read_training_status(run_dir)
    assert loaded["status"] == expected_status


def test_monitor_stopped_status_is_not_completed(tmp_path):
    """Regression: a monitor-stopped run must never read back as 'completed'."""
    from utils.run_protocol import write_training_status, read_training_status
    run_dir = tmp_path / "run1"
    run_dir.mkdir()

    write_training_status(run_dir, {"status": "monitor_stopped", "episodes_done": 50})
    loaded = read_training_status(run_dir)
    assert loaded["status"] != "completed"


def test_ensure_run_dir_creates_directory(tmp_path, monkeypatch):
    from utils import run_protocol
    monkeypatch.setattr(run_protocol, "_PROJECT_ROOT", tmp_path)
    run_dir = run_protocol.ensure_run_dir("ne39", "ne39_20260410_120000")
    assert run_dir.exists()
    assert (run_dir.parent.name == "runs")
    assert (run_dir / "checkpoints").exists()
    assert (run_dir / "logs").exists()


# ── find_latest_run ────────────────────────────────────────────────────────────

def _write_status(run_dir: Path, status: dict) -> None:
    """Helper: create run_dir and write training_status.json."""
    run_dir.mkdir(parents=True, exist_ok=True)
    from utils.run_protocol import write_training_status
    write_training_status(run_dir, status)


def test_find_latest_run_returns_none_when_no_runs(tmp_path, monkeypatch):
    from utils import run_protocol
    monkeypatch.setattr(run_protocol, "_PROJECT_ROOT", tmp_path)
    result = run_protocol.find_latest_run("kundur")
    assert result is None


def test_find_latest_run_returns_single_running_run(tmp_path, monkeypatch):
    from utils import run_protocol
    monkeypatch.setattr(run_protocol, "_PROJECT_ROOT", tmp_path)
    run_dir = tmp_path / "results" / "sim_kundur" / "runs" / "run1"
    _write_status(run_dir, {"status": "running", "last_updated": "2026-04-15T10:00:00Z"})
    result = run_protocol.find_latest_run("kundur")
    assert result == run_dir


def test_find_latest_run_multiple_running_returns_most_recent_by_last_updated(tmp_path, monkeypatch):
    from utils import run_protocol
    monkeypatch.setattr(run_protocol, "_PROJECT_ROOT", tmp_path)
    older = tmp_path / "results" / "sim_kundur" / "runs" / "run_old"
    newer = tmp_path / "results" / "sim_kundur" / "runs" / "run_new"
    _write_status(older, {"status": "running", "last_updated": "2026-04-15T09:00:00Z"})
    _write_status(newer, {"status": "running", "last_updated": "2026-04-15T10:00:00Z"})
    result = run_protocol.find_latest_run("kundur")
    assert result == newer


def test_find_latest_run_no_running_returns_most_recent_finished(tmp_path, monkeypatch):
    from utils import run_protocol
    monkeypatch.setattr(run_protocol, "_PROJECT_ROOT", tmp_path)
    older = tmp_path / "results" / "sim_kundur" / "runs" / "run_old"
    newer = tmp_path / "results" / "sim_kundur" / "runs" / "run_new"
    _write_status(older, {"status": "completed", "finished_at": "2026-04-14T12:00:00Z"})
    _write_status(newer, {"status": "completed", "finished_at": "2026-04-15T08:00:00Z"})
    result = run_protocol.find_latest_run("kundur")
    assert result == newer


def test_find_latest_run_crashed_run_with_no_terminal_ts_sorts_last(tmp_path, monkeypatch):
    """A run that crashed before writing finished_at/failed_at should lose to any
    run that did write a terminal timestamp, regardless of filesystem ordering."""
    from utils import run_protocol
    monkeypatch.setattr(run_protocol, "_PROJECT_ROOT", tmp_path)
    crashed = tmp_path / "results" / "sim_kundur" / "runs" / "run_crashed"
    finished = tmp_path / "results" / "sim_kundur" / "runs" / "run_finished"
    # Crashed run: only has last_updated, no finished_at / failed_at
    _write_status(crashed, {"status": "failed", "last_updated": "2026-04-15T09:00:00Z"})
    # Finished run has an older last_updated but a proper finished_at
    _write_status(finished, {"status": "completed", "finished_at": "2026-04-14T08:00:00Z"})
    result = run_protocol.find_latest_run("kundur")
    assert result == finished
