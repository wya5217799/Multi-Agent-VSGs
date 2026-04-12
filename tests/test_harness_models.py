"""Tests for engine.harness_models (TaskRecord + payload dataclasses)
and engine.task_primitives (record lifecycle helpers)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.harness_models import (
    HarnessFailure,
    ModelDiagnoseResult,
    ModelInspectResult,
    ModelPatchResult,
    ModelReportResult,
    ScenarioStatusResult,
    SmokePollResult,
    SmokeStartResult,
    TaskRecord,
)
from engine.task_primitives import (
    create_record,
    finish,
    list_existing_task_records,
    load_task_record,
    record_failure,
)


# ---------------------------------------------------------------------------
# TaskRecord envelope
# ---------------------------------------------------------------------------


def test_task_record_to_dict_matches_legacy_envelope():
    """TaskRecord.to_dict() must produce exactly the envelope keys
    that the legacy _base_record() dict had."""
    rec = TaskRecord(
        task="scenario_status",
        scenario_id="kundur",
        run_id="run-001",
        status="ok",
        started_at="2026-04-12T00:00:00+00:00",
        finished_at=None,
        inputs={"goal": "test"},
        summary=["line1"],
        artifacts=["/tmp/a.json"],
        failures=[],
    )
    d = rec.to_dict()
    expected_keys = {
        "task", "scenario_id", "run_id", "status",
        "started_at", "finished_at", "inputs",
        "summary", "artifacts", "failures",
    }
    assert set(d.keys()) == expected_keys
    assert d["task"] == "scenario_status"
    assert d["scenario_id"] == "kundur"
    assert d["run_id"] == "run-001"
    assert d["status"] == "ok"
    assert d["started_at"] == "2026-04-12T00:00:00+00:00"
    assert d["finished_at"] is None
    assert d["inputs"] == {"goal": "test"}
    assert d["summary"] == ["line1"]
    assert d["artifacts"] == ["/tmp/a.json"]
    assert d["failures"] == []


def test_harness_failure_serializes_identically():
    """HarnessFailure in TaskRecord.to_dict() must match the old dict format."""
    failure = HarnessFailure(
        failure_class="tool_error",
        message="something broke",
        detail={"code": 42},
    )
    rec = TaskRecord(
        task="model_inspect",
        scenario_id="kundur",
        run_id="run-002",
        status="failed",
        started_at="2026-04-12T00:00:00+00:00",
        finished_at="2026-04-12T00:00:01+00:00",
        inputs={},
        summary=[],
        artifacts=[],
        failures=[failure],
    )
    d = rec.to_dict()
    assert len(d["failures"]) == 1
    f = d["failures"][0]
    assert f == {
        "failure_class": "tool_error",
        "message": "something broke",
        "detail": {"code": 42},
    }


# ---------------------------------------------------------------------------
# Payload dataclasses — defaults
# ---------------------------------------------------------------------------


def test_task_result_dataclasses_have_defaults():
    """Each payload dataclass can be constructed with zero arguments."""
    s = ScenarioStatusResult()
    assert s.resolved_model_name == ""
    assert s.supported is False

    mi = ModelInspectResult()
    assert mi.model_loaded is False
    assert mi.loaded_models == []

    mp = ModelPatchResult()
    assert mp.update_ok is False
    assert mp.smoke_test_ok is None

    md = ModelDiagnoseResult()
    assert md.compile_ok is False
    assert md.suspected_root_causes == []

    mr = ModelReportResult()
    assert mr.run_status == ""
    assert mr.completed_tasks == []

    ss = SmokeStartResult()
    assert ss.command == ""
    assert ss.pid is None

    sp = SmokePollResult()
    assert sp.process_status == ""
    assert sp.smoke_passed is False


def test_payload_to_dict_omits_none():
    """Payload to_dict() omits None-valued optional fields."""
    s = SmokeStartResult(command="cmd", smoke_started=True)
    d = s.to_dict()
    assert "command" in d
    assert "smoke_started" in d
    # pid is None, should be omitted
    assert "pid" not in d


# ---------------------------------------------------------------------------
# task_primitives — create_record
# ---------------------------------------------------------------------------


def test_create_record_returns_task_record():
    rec = create_record("scenario_status", "kundur", "run-001", {"goal": "test"})
    assert isinstance(rec, TaskRecord)
    assert rec.task == "scenario_status"
    assert rec.scenario_id == "kundur"
    assert rec.run_id == "run-001"
    assert rec.status == "ok"
    assert rec.started_at  # non-empty
    assert rec.finished_at is None
    assert rec.inputs == {"goal": "test"}
    assert rec.summary == []
    assert rec.artifacts == []
    assert rec.failures == []


# ---------------------------------------------------------------------------
# task_primitives — record_failure
# ---------------------------------------------------------------------------


def test_record_failure_mutates_status_and_appends():
    rec = create_record("model_inspect", "kundur", "run-001", {})
    assert rec.status == "ok"
    assert rec.failures == []

    record_failure(rec, "tool_error", "boom", {"code": 1})

    assert rec.status == "failed"
    assert len(rec.failures) == 1
    f = rec.failures[0]
    assert isinstance(f, HarnessFailure)
    assert f.failure_class == "tool_error"
    assert f.message == "boom"
    assert f.detail == {"code": 1}

    # Append a second failure
    record_failure(rec, "model_error", "another")
    assert len(rec.failures) == 2


# ---------------------------------------------------------------------------
# task_primitives — finish
# ---------------------------------------------------------------------------


def test_finish_persists_and_returns_dict(tmp_path, monkeypatch):
    from engine import harness_reports
    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")

    rec = create_record("scenario_status", "kundur", "run-fin", {"goal": "test"})
    rec.summary = ["done"]

    result = finish(rec, extra={"resolved_model_name": "kundur_vsg", "supported": True})

    # Returns a dict
    assert isinstance(result, dict)
    assert result["task"] == "scenario_status"
    assert result["status"] == "ok"
    assert result["finished_at"] is not None
    assert result["resolved_model_name"] == "kundur_vsg"
    assert result["supported"] is True
    assert result["summary"] == ["done"]

    # Persisted to disk
    written = tmp_path / "results" / "harness" / "kundur" / "run-fin" / "scenario_status.json"
    assert written.exists()
    disk = json.loads(written.read_text(encoding="utf-8"))
    assert disk["task"] == "scenario_status"
    assert disk["resolved_model_name"] == "kundur_vsg"


def test_finish_without_extra(tmp_path, monkeypatch):
    from engine import harness_reports
    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")

    rec = create_record("model_report", "ne39", "run-noextra", {})
    result = finish(rec)

    assert isinstance(result, dict)
    assert result["task"] == "model_report"
    assert "resolved_model_name" not in result


# ---------------------------------------------------------------------------
# task_primitives — load / list
# ---------------------------------------------------------------------------


def test_load_task_record_and_list(tmp_path):
    from engine import harness_reports

    # Write two records manually
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    (run_dir / "scenario_status.json").write_text(
        json.dumps({"task": "scenario_status", "status": "ok"}),
        encoding="utf-8",
    )
    (run_dir / "model_inspect.json").write_text(
        json.dumps({"task": "model_inspect", "status": "warning"}),
        encoding="utf-8",
    )
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "run-001"}),
        encoding="utf-8",
    )

    # load_task_record
    rec = load_task_record(run_dir, "scenario_status")
    assert rec is not None
    assert rec["task"] == "scenario_status"

    assert load_task_record(run_dir, "no_such_task") is None

    # list_existing_task_records (excludes manifest)
    records = list_existing_task_records(run_dir)
    assert len(records) == 2
    tasks = [r["task"] for r in records]
    assert "scenario_status" in tasks
    assert "model_inspect" in tasks
