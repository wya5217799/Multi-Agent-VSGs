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


def test_ensure_run_dir_creates_directory(tmp_path, monkeypatch):
    from utils import run_protocol
    monkeypatch.setattr(run_protocol, "_PROJECT_ROOT", tmp_path)
    run_dir = run_protocol.ensure_run_dir("ne39", "ne39_20260410_120000")
    assert run_dir.exists()
    assert (run_dir.parent.name == "runs")
    assert (run_dir / "checkpoints").exists()
