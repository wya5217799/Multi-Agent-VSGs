from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine import harness_reports
from engine.harness_models import (
    FailureClass,
    HarnessFailure,
    HarnessStatus,
    HarnessTaskName,
    ScenarioId,
    TaskRecord,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_record(
    task: HarnessTaskName,
    scenario_id: ScenarioId,
    run_id: str,
    inputs: dict[str, Any],
) -> TaskRecord:
    """Create a new TaskRecord with current timestamp and sensible defaults."""
    return TaskRecord(
        task=task,
        scenario_id=scenario_id,
        run_id=run_id,
        status="ok",
        started_at=_now(),
        finished_at=None,
        inputs=dict(inputs),
        summary=[],
        artifacts=[],
        failures=[],
    )


def record_failure(
    record: TaskRecord,
    failure_class: FailureClass,
    message: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """Mutate the record: set status to 'failed' and append a HarnessFailure."""
    record.status = "failed"
    record.failures.append(
        HarnessFailure(
            failure_class=failure_class,
            message=message,
            detail=dict(detail or {}),
        )
    )


def finish(
    record: TaskRecord,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert TaskRecord to dict, merge extra fields, persist to disk, and return."""
    record.finished_at = _now()
    result = record.to_dict()
    if extra:
        result.update(extra)
    run_dir = harness_reports.ensure_run_dir(record.scenario_id, record.run_id)
    harness_reports.write_task_record(run_dir, record.task, result)
    return result


def load_task_record(run_dir: Path, task_name: str) -> dict[str, Any] | None:
    """Load a task record JSON from disk, or return None if not found."""
    path = run_dir / f"{task_name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_existing_task_records(run_dir: Path) -> list[dict[str, Any]]:
    """List all task record JSONs in a run directory (excluding manifest)."""
    records: list[dict[str, Any]] = []
    for path in sorted(run_dir.glob("*.json")):
        if path.name == "manifest.json":
            continue
        records.append(json.loads(path.read_text(encoding="utf-8")))
    return records
