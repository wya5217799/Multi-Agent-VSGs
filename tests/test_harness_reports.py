from __future__ import annotations

import json
from pathlib import Path


def test_ensure_run_dir_creates_scenario_run_directory(tmp_path, monkeypatch):
    from engine import harness_reports

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")

    run_dir = harness_reports.ensure_run_dir("kundur", "run-001")

    assert run_dir == tmp_path / "results" / "harness" / "kundur" / "run-001"
    assert run_dir.is_dir()


def test_write_manifest_writes_pretty_utf8_json(tmp_path, monkeypatch):
    from engine import harness_reports

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    run_dir = harness_reports.ensure_run_dir("ne39", "run-20260405")

    manifest_path = harness_reports.write_manifest(
        run_dir,
        run_id="run-20260405",
        scenario_id="ne39",
        goal="smoke test",
        requested_tasks=["scenario_status", "model_inspect"],
        created_at="2026-04-05T10:00:00Z",
    )

    assert manifest_path == run_dir / "manifest.json"
    raw = manifest_path.read_bytes()
    assert raw.decode("utf-8").startswith("{\n  ")

    manifest = json.loads(raw.decode("utf-8"))
    assert manifest == {
        "run_id": "run-20260405",
        "scenario_id": "ne39",
        "goal": "smoke test",
        "requested_tasks": ["scenario_status", "model_inspect"],
        "created_at": "2026-04-05T10:00:00Z",
    }


def test_write_task_record_writes_task_json_in_run_dir(tmp_path, monkeypatch):
    from engine import harness_reports

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    run_dir = harness_reports.ensure_run_dir("kundur", "run-002")

    task_path = harness_reports.write_task_record(
        run_dir,
        "model_inspect",
        {
            "status": "ok",
            "details": {"blocks": 3},
        },
    )

    assert task_path == run_dir / "model_inspect.json"
    assert task_path.exists()
    assert task_path.read_text(encoding="utf-8").startswith("{\n  ")
    assert json.loads(task_path.read_text(encoding="utf-8")) == {
        "status": "ok",
        "details": {"blocks": 3},
    }


def test_ensure_run_dir_rejects_invalid_scenario(tmp_path, monkeypatch):
    import pytest
    from engine import harness_reports

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    with pytest.raises(ValueError, match="Invalid scenario_id"):
        harness_reports.ensure_run_dir("unknown_scenario", "run-001")


def test_ensure_run_dir_rejects_dotdot_run_id(tmp_path, monkeypatch):
    import pytest
    from engine import harness_reports

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    with pytest.raises(ValueError, match="Invalid run_id"):
        harness_reports.ensure_run_dir("kundur", "../../../etc/passwd")


def test_model_report_surfaces_alignment_warnings():
    payload = {
        "semantic_alignment": ["pref_ramp present while profile forbids it"]
    }
    assert payload["semantic_alignment"][0].startswith("pref_ramp")
