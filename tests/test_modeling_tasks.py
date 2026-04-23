"""Direct tests for engine.modeling_tasks (Zone A)."""

import json


def test_modeling_tasks_imports_and_scenario_status(tmp_path, monkeypatch):
    """Verify modeling_tasks is importable and harness_scenario_status works."""
    from engine import harness_reports, modeling_tasks

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")

    result = modeling_tasks.harness_scenario_status(
        scenario_id="kundur",
        run_id="run-mt-001",
        goal="direct import test",
    )
    assert result["status"] == "ok"
    assert result["resolved_model_name"] == "kundur_vsg"


def test_model_report_via_modeling_tasks(tmp_path, monkeypatch):
    """Verify harness_model_report imported directly from modeling_tasks."""
    from engine import harness_reports, modeling_tasks

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    run_dir = harness_reports.ensure_run_dir("kundur", "run-mt-002")
    harness_reports.write_task_record(
        run_dir,
        "scenario_status",
        {"task": "scenario_status", "scenario_id": "kundur", "run_id": "run-mt-002", "status": "ok"},
    )

    result = modeling_tasks.harness_model_report(
        scenario_id="kundur",
        run_id="run-mt-002",
        include_summary_md=True,
    )
    assert result["status"] == "ok"
    assert result["run_status"] == "ok"
    assert (run_dir / "summary.md").exists()


def test_modeling_tasks_constant():
    """_MODELING_TASKS constant is accessible."""
    from engine.modeling_tasks import _MODELING_TASKS

    assert "scenario_status" in _MODELING_TASKS
    assert "model_report" in _MODELING_TASKS
    assert len(_MODELING_TASKS) == 5


def test_model_inspect_adds_semantic_manifest_artifact(tmp_path):
    result = {
        "semantic_manifest_artifact": str(tmp_path / "semantic_manifest.json"),
        "semantic_alignment": [],
    }
    assert result["semantic_manifest_artifact"].endswith("semantic_manifest.json")
    assert result["semantic_alignment"] == []
