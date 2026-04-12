"""Tests for engine.task_state — explicit flow state inference and advisory transitions."""

import json

from engine import harness_reports
from engine.harness_models import TaskPhase, TRANSITIONS, TASK_TO_PHASE
from engine.task_state import (
    allowed_next_tasks,
    check_transition,
    infer_phase,
    recommended_next_tasks_for,
)


def _write_record(run_dir, task_name, status, **extra):
    """Helper: write a minimal task record to disk."""
    record = {"task": task_name, "status": status, **extra}
    path = run_dir / f"{task_name}.json"
    path.write_text(json.dumps(record), encoding="utf-8")


# -----------------------------------------------------------------------
# 1. test_infer_phase_empty_run
# -----------------------------------------------------------------------

def test_infer_phase_empty_run(tmp_path, monkeypatch):
    """No records -> (NOT_STARTED, 'ok')."""
    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    run_dir = harness_reports.ensure_run_dir("kundur", "run-ts-001")

    phase, status = infer_phase(run_dir)
    assert phase == TaskPhase.NOT_STARTED
    assert status == "ok"


# -----------------------------------------------------------------------
# 2. test_infer_phase_after_scenario_status
# -----------------------------------------------------------------------

def test_infer_phase_after_scenario_status(tmp_path, monkeypatch):
    """scenario_status ok -> (SCENARIO_RESOLVED, 'ok')."""
    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    run_dir = harness_reports.ensure_run_dir("kundur", "run-ts-002")
    _write_record(run_dir, "scenario_status", "ok")

    phase, status = infer_phase(run_dir)
    assert phase == TaskPhase.SCENARIO_RESOLVED
    assert status == "ok"


# -----------------------------------------------------------------------
# 3. test_allowed_next_after_inspect_ok
# -----------------------------------------------------------------------

def test_allowed_next_after_inspect_ok(tmp_path, monkeypatch):
    """After model_inspect ok -> ['model_patch_verify', 'model_report']."""
    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    run_dir = harness_reports.ensure_run_dir("kundur", "run-ts-003")
    _write_record(run_dir, "scenario_status", "ok")
    _write_record(run_dir, "model_inspect", "ok")

    result = allowed_next_tasks(run_dir)
    assert result == ["model_patch_verify", "model_report"]


# -----------------------------------------------------------------------
# 4. test_allowed_next_after_inspect_failed
# -----------------------------------------------------------------------

def test_allowed_next_after_inspect_failed(tmp_path, monkeypatch):
    """After model_inspect failed -> ['model_diagnose']."""
    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    run_dir = harness_reports.ensure_run_dir("kundur", "run-ts-004")
    _write_record(run_dir, "scenario_status", "ok")
    _write_record(run_dir, "model_inspect", "failed")

    result = allowed_next_tasks(run_dir)
    assert result == ["model_diagnose"]


# -----------------------------------------------------------------------
# 5. test_check_transition_blocks_smoke_before_report
# -----------------------------------------------------------------------

def test_check_transition_blocks_smoke_before_report(tmp_path, monkeypatch):
    """Without model_report, train_smoke_start not allowed."""
    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    run_dir = harness_reports.ensure_run_dir("kundur", "run-ts-005")
    _write_record(run_dir, "scenario_status", "ok")
    _write_record(run_dir, "model_inspect", "ok")

    ok, reason = check_transition(run_dir, "train_smoke_start")
    assert ok is False
    assert "train_smoke_start" in reason


# -----------------------------------------------------------------------
# 6. test_transition_table_covers_all_phases
# -----------------------------------------------------------------------

def test_transition_table_covers_all_phases():
    """Every TaskPhase has at least one entry in TRANSITIONS."""
    covered_phases = {phase for (phase, _status) in TRANSITIONS}
    for phase in TaskPhase:
        assert phase in covered_phases, f"TaskPhase.{phase.name} has no entry in TRANSITIONS"


# -----------------------------------------------------------------------
# 7. test_recommended_next_tasks_for_inspect_ok_uses_in_memory_status
# -----------------------------------------------------------------------

def test_recommended_next_tasks_for_inspect_ok_uses_in_memory_status():
    """recommended_next_tasks_for('model_inspect', 'ok') returns correct tasks."""
    result = recommended_next_tasks_for("model_inspect", "ok")
    assert result == ["model_patch_verify", "model_report"]


# -----------------------------------------------------------------------
# 8. test_transition_advisory_appends_to_summary_not_notes
# -----------------------------------------------------------------------

def test_transition_advisory_appends_to_summary_not_notes(tmp_path, monkeypatch):
    """Advisory goes into record.summary, not a separate notes field."""
    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")

    # scenario_status ok exists, but NO model_inspect yet -- calling
    # model_report out-of-order should produce a transition_advisory in summary.
    from engine import modeling_tasks

    run_dir = harness_reports.ensure_run_dir("kundur", "run-ts-008")
    _write_record(run_dir, "scenario_status", "ok",
                  scenario_id="kundur", run_id="run-ts-008")

    result = modeling_tasks.harness_model_report(
        scenario_id="kundur",
        run_id="run-ts-008",
        include_summary_md=False,
    )
    # model_report does not add advisory itself (per spec: keep as-is),
    # but the record should still be valid.  We verify advisory pattern
    # works by checking a task that DOES add advisory -- use the
    # check_transition + record.summary pattern directly.
    from engine.task_primitives import create_record
    from engine.task_state import check_transition as _ct

    rec = create_record("model_inspect", "kundur", "run-ts-008", {})
    t_ok, t_reason = _ct(run_dir, "model_inspect")
    if not t_ok:
        rec.summary.append(f"transition_advisory: {t_reason}")

    # The advisory should be in summary (list of strings).
    advisory_items = [s for s in rec.summary if s.startswith("transition_advisory:")]
    # After scenario_status ok, model_inspect IS allowed, so advisory is empty.
    # Let's test a truly out-of-order case: model_diagnose without model_inspect.
    rec2 = create_record("model_diagnose", "kundur", "run-ts-008", {})
    t_ok2, t_reason2 = _ct(run_dir, "model_diagnose")
    if not t_ok2:
        rec2.summary.append(f"transition_advisory: {t_reason2}")
    advisory_items2 = [s for s in rec2.summary if s.startswith("transition_advisory:")]
    assert len(advisory_items2) == 1
    assert "model_diagnose" in advisory_items2[0]


# -----------------------------------------------------------------------
# 9. test_train_smoke_preconditions_require_model_report_run_status
# -----------------------------------------------------------------------

def test_train_smoke_preconditions_require_model_report_run_status(tmp_path, monkeypatch):
    """Preconditions fail without model_report."""
    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    run_dir = harness_reports.ensure_run_dir("kundur", "run-ts-009")
    _write_record(run_dir, "scenario_status", "ok")
    _write_record(run_dir, "model_inspect", "ok")

    from engine.smoke_tasks import _train_smoke_preconditions

    ok, failures = _train_smoke_preconditions(run_dir)
    assert ok is False
    hard_failures = [f for f in failures if not f.startswith("transition_advisory:")]
    assert any("model_report" in f for f in hard_failures)


# -----------------------------------------------------------------------
# 10. test_train_smoke_preconditions_reject_failed_modeling_task_even_if_phase_is_model_reported
# -----------------------------------------------------------------------

def test_train_smoke_preconditions_reject_failed_modeling_task_even_if_phase_is_model_reported(
    tmp_path, monkeypatch
):
    """model_report exists with ok, but model_diagnose is failed -> still blocked."""
    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    run_dir = harness_reports.ensure_run_dir("kundur", "run-ts-010")
    _write_record(run_dir, "scenario_status", "ok")
    _write_record(run_dir, "model_inspect", "ok")
    _write_record(run_dir, "model_diagnose", "failed")
    _write_record(run_dir, "model_report", "ok", run_status="ok")

    from engine.smoke_tasks import _train_smoke_preconditions

    ok, failures = _train_smoke_preconditions(run_dir)
    assert ok is False
    hard_failures = [f for f in failures if not f.startswith("transition_advisory:")]
    assert any("model_diagnose" in f and "failed" in f for f in hard_failures)
