"""Direct tests for engine.smoke_tasks (Zone B)."""


def test_smoke_tasks_imports_and_parse_training_summary(tmp_path):
    """Verify smoke_tasks is importable and _parse_training_summary works."""
    from engine.smoke_tasks import _parse_training_summary

    # Non-existent file returns None.
    assert _parse_training_summary(tmp_path / "absent.json") is None

    # Empty JSON object returns zero-episode summary.
    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    result = _parse_training_summary(empty)
    assert result is not None
    assert result["episodes_completed"] == 0
    assert result["last_10_reward_mean"] is None


def test_smoke_tasks_preconditions_reject_without_records(tmp_path, monkeypatch):
    """_train_smoke_preconditions rejects when no prior task records exist."""
    from engine import harness_reports, smoke_tasks

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    run_dir = harness_reports.ensure_run_dir("kundur", "run-st-001")

    ok, failures = smoke_tasks._train_smoke_preconditions(run_dir)
    assert ok is False
    assert len(failures) >= 1


def test_smoke_processes_dict_accessible():
    """_SMOKE_PROCESSES is a module-level dict in smoke_tasks."""
    from engine.smoke_tasks import _SMOKE_PROCESSES, _SMOKE_LOG_HANDLES

    assert isinstance(_SMOKE_PROCESSES, dict)
    assert isinstance(_SMOKE_LOG_HANDLES, dict)


def test_deprecated_train_smoke_fails_fast(tmp_path, monkeypatch):
    """harness_train_smoke returns contract_error without launching subprocess."""
    from engine import harness_reports, smoke_tasks

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    harness_reports.ensure_run_dir("kundur", "run-st-dep")

    result = smoke_tasks.harness_train_smoke(
        scenario_id="kundur",
        run_id="run-st-dep",
        episodes=1,
        mode="simulink",
    )
    assert result["status"] == "failed"
    assert result["failures"][0]["failure_class"] == "contract_error"
