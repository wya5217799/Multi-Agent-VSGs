"""Tests for engine.run_schema — typed view of training_status.json.

Locks the field contract relied on by the Launcher
(engine/training_launch.py) and the Observer
(engine/training_tasks.py::training_status).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from engine.run_schema import (
    RunStatus,
    list_episode_checkpoints,
    latest_resume_candidate,
    read_run_status,
)
from utils.run_protocol import write_training_status


def test_read_run_status_missing_returns_none(tmp_path: Path) -> None:
    run_dir = tmp_path / "empty_run"
    run_dir.mkdir()
    assert read_run_status(run_dir) is None


def test_read_run_status_full_payload(tmp_path: Path) -> None:
    run_dir = tmp_path / "kundur_20260410_120000"
    run_dir.mkdir()
    payload = {
        "scenario": "kundur",
        "run_id": "kundur_20260410_120000",
        "status": "running",
        "episodes_done": 12,
        "episodes_total": 500,
        "last_reward": -123.45,
        "last_eval_reward": -110.5,
        "last_updated": "2026-04-26T01:23:45",
        "started_at": "2026-04-26T01:00:00",
        "logs_dir": str(run_dir / "logs"),
    }
    write_training_status(run_dir, payload)

    rs = read_run_status(run_dir)
    assert rs is not None
    assert isinstance(rs, RunStatus)
    assert rs.scenario == "kundur"
    assert rs.run_id == "kundur_20260410_120000"
    assert rs.status == "running"
    assert rs.episodes_done == 12
    assert rs.episodes_total == 500
    assert rs.last_reward == pytest.approx(-123.45)
    assert rs.last_eval_reward == pytest.approx(-110.5)
    assert rs.logs_dir == str(run_dir / "logs")
    assert rs.progress_pct == pytest.approx(2.4)
    # raw preserves source dict for forward-compat
    assert rs.raw == payload


def test_read_run_status_tolerates_missing_fields(tmp_path: Path) -> None:
    run_dir = tmp_path / "minimal"
    run_dir.mkdir()
    write_training_status(run_dir, {"status": "finished"})

    rs = read_run_status(run_dir)
    assert rs is not None
    assert rs.status == "finished"
    assert rs.episodes_done == 0
    assert rs.episodes_total == 0
    assert rs.last_reward is None
    assert rs.progress_pct == 0.0


def test_read_run_status_coerces_bad_types(tmp_path: Path) -> None:
    run_dir = tmp_path / "weird"
    run_dir.mkdir()
    write_training_status(
        run_dir,
        {
            "episodes_done": "not-an-int",
            "last_reward": "not-a-float",
            "episodes_total": "20",  # string-int OK
        },
    )

    rs = read_run_status(run_dir)
    assert rs is not None
    assert rs.episodes_done == 0
    assert rs.last_reward is None
    assert rs.episodes_total == 20


def test_logs_path_prefers_status_field(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    custom_logs = tmp_path / "elsewhere" / "logs"
    rs_with = RunStatus(logs_dir=str(custom_logs))
    rs_without = RunStatus()
    assert rs_with.logs_path(run_dir) == custom_logs
    assert rs_without.logs_path(run_dir) == run_dir / "logs"


def test_to_observer_dict_full_shape(tmp_path: Path) -> None:
    """Locks the MCP Observer dict shape consumed by training_tasks.training_status."""
    run_dir = tmp_path / "kundur_x"
    run_dir.mkdir()
    rs = RunStatus(
        scenario="kundur",
        run_id="kundur_x",
        status="failed",
        episodes_done=10,
        episodes_total=500,
        last_reward=-50.0,
        last_eval_reward=-45.0,
        last_updated="2026-04-26T01:00:00",
        started_at="2026-04-26T00:30:00",
        failed_at="2026-04-26T01:05:00",
        error="boom",
        logs_dir=str(run_dir / "logs"),
    )
    out = rs.to_observer_dict(run_dir, "kundur", latest_snapshot={"episode": 5})

    expected_keys = {
        "scenario_id", "scenario", "run_id", "status",
        "episodes_done", "episodes_total", "progress_pct",
        "last_reward", "last_updated", "started_at",
        "finished_at", "failed_at", "error", "stop_reason",
        "last_eval_reward", "logs_dir", "run_dir", "latest_snapshot",
    }
    assert set(out.keys()) == expected_keys
    assert out["scenario_id"] == "kundur"
    assert out["scenario"] == "kundur"
    assert out["run_id"] == "kundur_x"
    assert out["status"] == "failed"
    assert out["failed_at"] == "2026-04-26T01:05:00"
    assert out["error"] == "boom"
    assert out["episodes_done"] == 10
    assert out["progress_pct"] == 2.0
    assert out["latest_snapshot"] == {"episode": 5}
    assert out["logs_dir"] == str(run_dir / "logs")
    assert out["run_dir"] == str(run_dir)


def test_to_observer_dict_empty_status(tmp_path: Path) -> None:
    """Empty RunStatus still returns full key set; logs_dir falls back."""
    run_dir = tmp_path / "empty"
    run_dir.mkdir()
    out = RunStatus().to_observer_dict(run_dir, "ne39")
    assert out["status"] is None
    assert out["episodes_done"] == 0
    assert out["progress_pct"] == 0.0
    assert out["latest_snapshot"] is None
    assert out["logs_dir"] == str(run_dir / "logs")


def test_run_status_is_frozen() -> None:
    rs = RunStatus(run_id="kundur_x")
    with pytest.raises(Exception):
        rs.run_id = "mutated"  # type: ignore[misc]


def test_list_episode_checkpoints_empty_dir(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assert list_episode_checkpoints(run_dir) == []


def test_list_episode_checkpoints_sorted(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    ckpt = run_dir / "checkpoints"
    ckpt.mkdir(parents=True)
    # Out-of-order on disk; numerical sort expected.
    for name in ["ep10.pt", "ep2.pt", "ep100.pt", "final.pt", "other.txt"]:
        (ckpt / name).write_bytes(b"")

    files = list_episode_checkpoints(run_dir)
    assert [p.name for p in files] == ["ep2.pt", "ep10.pt", "ep100.pt"]


def test_latest_resume_candidate_prefers_episode(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    ckpt = run_dir / "checkpoints"
    ckpt.mkdir(parents=True)
    (ckpt / "ep5.pt").write_bytes(b"")
    (ckpt / "final.pt").write_bytes(b"")

    candidate = latest_resume_candidate(run_dir)
    assert candidate is not None
    assert candidate.name == "ep5.pt"


def test_latest_resume_candidate_falls_back_to_final(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    ckpt = run_dir / "checkpoints"
    ckpt.mkdir(parents=True)
    (ckpt / "final.pt").write_bytes(b"")

    candidate = latest_resume_candidate(run_dir)
    assert candidate is not None
    assert candidate.name == "final.pt"


def test_latest_resume_candidate_none(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assert latest_resume_candidate(run_dir) is None
