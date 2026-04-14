"""Tests for engine.training_tasks monitoring tools."""
import json
from pathlib import Path

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_run(tmp_path: Path, scenario: str, run_id: str, status: dict) -> Path:
    """Create a minimal run directory with training_status.json."""
    run_dir = tmp_path / "results" / f"sim_{scenario}" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "training_status.json").write_text(
        json.dumps(status), encoding="utf-8"
    )
    return run_dir


def _make_logs(run_dir: Path) -> Path:
    """Create logs subdirectory and return its path."""
    logs = run_dir / "logs"
    logs.mkdir(exist_ok=True)
    return logs


# ── training_status ────────────────────────────────────────────────────────────

def test_training_status_no_run(tmp_path, monkeypatch):
    import utils.run_protocol as rp
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)
    from engine.training_tasks import training_status
    result = training_status("kundur")
    assert result["status"] == "no_run"
    assert result["scenario_id"] == "kundur"


def test_training_status_running(tmp_path, monkeypatch):
    import utils.run_protocol as rp
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)
    # Build run_dir path first so logs_dir can reference it without a NameError.
    run_dir = tmp_path / "results" / "sim_kundur" / "runs" / "run1"
    run_dir.mkdir(parents=True, exist_ok=True)
    from utils.run_protocol import write_training_status
    write_training_status(run_dir, {
        "status": "running",
        "run_id": "run1",
        "scenario": "kundur",
        "episodes_total": 500,
        "episodes_done": 120,
        "last_reward": -45.3,
        "last_updated": "2026-04-15T10:00:00Z",
        "started_at": "2026-04-15T09:00:00Z",
        "logs_dir": str(run_dir / "logs"),
        "last_eval_reward": -38.1,
    })
    from engine.training_tasks import training_status
    result = training_status("kundur")
    assert result["status"] == "running"
    assert result["run_id"] == "run1"
    assert result["episodes_done"] == 120
    assert result["episodes_total"] == 500
    assert result["progress_pct"] == pytest.approx(24.0)
    assert result["last_reward"] == pytest.approx(-45.3)
    assert result["last_eval_reward"] == pytest.approx(-38.1)
    assert result["started_at"] == "2026-04-15T09:00:00Z"
    assert result["latest_snapshot"] is None  # no latest_state.json yet


def test_training_status_with_latest_state(tmp_path, monkeypatch):
    import utils.run_protocol as rp
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)
    run_dir = _make_run(tmp_path, "kundur", "run1", {
        "status": "running",
        "run_id": "run1",
        "episodes_total": 500,
        "episodes_done": 200,
        "last_reward": -30.0,
        "last_updated": "2026-04-15T11:00:00Z",
    })
    logs = _make_logs(run_dir)
    (logs / "latest_state.json").write_text(json.dumps({
        "episode": 150,
        "reward_mean_50": -55.2,
        "alpha": 0.12,
        "settled_rate_50": 0.72,
        "buffer_size": 8000,
    }), encoding="utf-8")
    from engine.training_tasks import training_status
    result = training_status("kundur")
    snap = result["latest_snapshot"]
    assert snap is not None
    assert snap["episode"] == 150
    assert snap["reward_mean_50"] == pytest.approx(-55.2)
    assert snap["snapshot_age_episodes"] == 50  # 200 - 150
    assert snap["snapshot_freshness"] == "~50-episode intervals"


def test_training_status_malformed_latest_state_returns_no_snapshot(tmp_path, monkeypatch):
    import utils.run_protocol as rp
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)
    run_dir = _make_run(tmp_path, "kundur", "run1", {
        "status": "running", "run_id": "run1",
        "episodes_total": 500, "episodes_done": 60,
    })
    logs = _make_logs(run_dir)
    (logs / "latest_state.json").write_text("not valid json{", encoding="utf-8")
    from engine.training_tasks import training_status
    result = training_status("kundur")
    assert result["latest_snapshot"] is None


def test_training_status_without_latest_state(tmp_path, monkeypatch):
    import utils.run_protocol as rp
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)
    _make_run(tmp_path, "kundur", "run1", {
        "status": "completed",
        "run_id": "run1",
        "episodes_total": 500,
        "episodes_done": 500,
        "finished_at": "2026-04-15T12:00:00Z",
    })
    from engine.training_tasks import training_status
    result = training_status("kundur")
    assert result["status"] == "completed"
    assert result["latest_snapshot"] is None


# ── training_diagnose ──────────────────────────────────────────────────────────

def test_training_diagnose_empty_events(tmp_path, monkeypatch):
    import utils.run_protocol as rp
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)
    run_dir = _make_run(tmp_path, "kundur", "run1", {
        "status": "running", "run_id": "run1",
        "episodes_total": 500, "episodes_done": 10,
    })
    logs = _make_logs(run_dir)
    (logs / "events.jsonl").write_text("", encoding="utf-8")
    from engine.training_tasks import training_diagnose
    result = training_diagnose("kundur")
    assert result["event_count"] == 0
    assert result["alerts"] == []
    assert result["monitor_stop"] is None
    assert result["eval_rewards"] == []
    assert result["training_start"] is None
    assert result["training_end"] is None


def test_training_diagnose_parses_events(tmp_path, monkeypatch):
    import utils.run_protocol as rp
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)
    run_dir = _make_run(tmp_path, "kundur", "run1", {
        "status": "monitor_stopped", "run_id": "run1",
        "episodes_total": 500, "episodes_done": 87,
    })
    logs = _make_logs(run_dir)
    events = [
        {"episode": 0, "ts": "2026-04-15T09:00:00Z", "type": "training_start",
         "mode": "simulink", "start_episode": 0, "end_episode": 500},
        {"episode": 50, "ts": "2026-04-15T09:30:00Z", "type": "eval",
         "eval_reward": -42.5},
        {"episode": 85, "ts": "2026-04-15T09:55:00Z", "type": "monitor_alert",
         "rule": "reward_divergence"},
        {"episode": 87, "ts": "2026-04-15T09:57:00Z", "type": "monitor_stop",
         "triggered_by": "monitor"},
        {"episode": 100, "ts": "2026-04-15T10:10:00Z", "type": "checkpoint",
         "file": "ep100.pt"},
    ]
    (logs / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events), encoding="utf-8"
    )
    from engine.training_tasks import training_diagnose
    result = training_diagnose("kundur")
    assert result["event_count"] == 5
    assert result["training_start"] == {"episode": 0, "mode": "simulink"}
    assert result["eval_rewards"] == [{"episode": 50, "eval_reward": -42.5}]
    assert result["alerts"] == [
        {"check": "reward_divergence", "action": None, "count": 1,
         "first_episode": 85, "last_episode": 85}
    ]
    assert result["monitor_stop"] == {"episode": 87}
    assert result["checkpoints"] == [{"episode": 100, "file": "ep100.pt"}]
    assert result["training_end"] is None


# ── _diagnose_physics ──────────────────────────────────────────────────────────

def _write_metrics(logs_dir: Path, rows: list[dict]) -> None:
    (logs_dir / "metrics.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8"
    )


def _make_metrics_run(tmp_path: Path, scenario: str, run_id: str, rows: list[dict]) -> Path:
    run_dir = _make_run(tmp_path, scenario, run_id, {
        "status": "completed", "run_id": run_id,
        "episodes_total": len(rows), "episodes_done": len(rows),
    })
    logs = _make_logs(run_dir)
    _write_metrics(logs, rows)
    return run_dir


def test_diagnose_physics_early_termination_pattern(tmp_path, monkeypatch):
    """All episodes capped at 15 Hz from ep0 → early_termination pattern."""
    import utils.run_protocol as rp
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)

    rows = [
        {"episode": i, "max_freq_dev_hz": 15.0, "reward": -500.0, "settled": False}
        for i in range(50)
    ]
    _make_metrics_run(tmp_path, "kundur", "run1", rows)

    from engine.training_tasks import training_diagnose
    result = training_diagnose("kundur")
    pd = result["physics_diagnosis"]
    assert pd["pattern"] == "early_termination"
    assert "early_termination" in pd["pattern"]
    assert pd["recommendation"] is not None
    assert "DIST_MAX" in pd["recommendation"]


def test_diagnose_physics_no_pattern_healthy(tmp_path, monkeypatch):
    """Healthy training with declining freq dev → no pattern detected."""
    import utils.run_protocol as rp
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)

    rows = [
        {"episode": i, "max_freq_dev_hz": max(2.0, 12.0 - i * 0.1),
         "reward": -5000.0 + i * 20, "settled": i > 20}
        for i in range(100)
    ]
    _make_metrics_run(tmp_path, "kundur", "run1", rows)

    from engine.training_tasks import training_diagnose
    result = training_diagnose("kundur")
    pd = result["physics_diagnosis"]
    assert pd["pattern"] is None


def test_diagnose_physics_no_progress_pattern(tmp_path, monkeypatch):
    """Flat reward for 20+ episodes with zero settled rate → no_progress."""
    import utils.run_protocol as rp
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)

    rows = [
        {"episode": i, "max_freq_dev_hz": 8.0, "reward": -50000.0, "settled": False}
        for i in range(30)
    ]
    _make_metrics_run(tmp_path, "kundur", "run1", rows)

    from engine.training_tasks import training_diagnose
    result = training_diagnose("kundur")
    pd = result["physics_diagnosis"]
    assert pd["pattern"] == "no_progress"
    assert "WARMUP_STEPS" in pd["recommendation"] or "NORM_FREQ" in pd["recommendation"]


def test_diagnose_physics_no_run_returns_no_pattern(tmp_path, monkeypatch):
    """No run directory → _empty schema includes physics_diagnosis with no pattern."""
    import utils.run_protocol as rp
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)

    from engine.training_tasks import training_diagnose
    result = training_diagnose("kundur")
    assert "physics_diagnosis" in result           # C1 fix: key must always be present
    assert result["physics_diagnosis"]["pattern"] is None


def test_diagnose_physics_no_metrics_file(tmp_path, monkeypatch):
    """Run dir exists but no metrics.jsonl → no pattern, not a crash."""
    import utils.run_protocol as rp
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)

    _make_run(tmp_path, "kundur", "run1", {
        "status": "running", "run_id": "run1",
        "episodes_total": 500, "episodes_done": 10,
    })
    _make_logs(tmp_path / "results" / "sim_kundur" / "runs" / "run1")

    from engine.training_tasks import training_diagnose
    result = training_diagnose("kundur")
    pd = result["physics_diagnosis"]
    assert pd["pattern"] is None
    assert "not found" in pd["evidence"]
