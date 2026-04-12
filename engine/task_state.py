from __future__ import annotations

"""Explicit flow state inference and advisory transition checks.

The TRANSITIONS table is ADVISORY ONLY.  It is NOT the sole authority for
gate decisions — smoke gates use richer predicates in smoke_tasks.py.
"""

from pathlib import Path

from engine.harness_models import (
    HarnessStatus,
    HarnessTaskName,
    TaskPhase,
    TASK_TO_PHASE,
    TRANSITIONS,
)
from engine.task_primitives import list_existing_task_records

# Canonical phase ordering derived from TASK_TO_PHASE dict insertion order.
_PHASE_ORDER: list[TaskPhase] = list(dict.fromkeys(TASK_TO_PHASE.values()))


def infer_phase(run_dir: Path) -> tuple[TaskPhase, HarnessStatus]:
    """Infer the current phase from persisted task records.

    Reads all task records in *run_dir*, finds the latest completed task
    that has an entry in TASK_TO_PHASE, and maps it to a phase.

    The "latest" task is determined by the TASK_TO_PHASE ordering:
    scenario_status < model_inspect < model_patch_verify < model_diagnose
    < model_report < train_smoke_start < train_smoke_poll

    Special cases:
    - No records -> (NOT_STARTED, "ok")
    - train_smoke_poll with status "running" -> (SMOKE_STARTED, "running")
    """
    records = list_existing_task_records(run_dir)
    if not records:
        return TaskPhase.NOT_STARTED, "ok"

    best_phase_idx = -1
    best_status: HarnessStatus = "ok"

    for rec in records:
        task_name = rec.get("task")
        if task_name not in TASK_TO_PHASE:
            continue
        phase = TASK_TO_PHASE[task_name]
        phase_idx = _PHASE_ORDER.index(phase) if phase in _PHASE_ORDER else -1

        if phase_idx > best_phase_idx:
            best_phase_idx = phase_idx
            status = rec.get("status", "ok")
            # smoke_poll "running" means we are still in SMOKE_STARTED
            if task_name == "train_smoke_poll" and status == "running":
                best_status = "running"
                # Override phase to SMOKE_STARTED (not SMOKE_COMPLETED)
                best_phase_idx = _PHASE_ORDER.index(TaskPhase.SMOKE_STARTED)
            else:
                best_status = status

    if best_phase_idx < 0:
        return TaskPhase.NOT_STARTED, "ok"

    return _PHASE_ORDER[best_phase_idx], best_status


def allowed_next_tasks(run_dir: Path) -> list[HarnessTaskName]:
    """Look up allowed next tasks from the TRANSITIONS table based on persisted state."""
    phase, status = infer_phase(run_dir)
    return TRANSITIONS.get((phase, status), [])


def check_transition(
    run_dir: Path,
    target_task: HarnessTaskName,
) -> tuple[bool, str]:
    """Check whether *target_task* is allowed by the transition table.

    Returns ``(True, "")`` if allowed, ``(False, reason)`` if not.
    This is ADVISORY -- callers may proceed even if transition check fails.
    """
    allowed = allowed_next_tasks(run_dir)
    if target_task in allowed:
        return True, ""
    phase, status = infer_phase(run_dir)
    return False, f"transition from ({phase.value}, {status}) does not include {target_task}"


def recommended_next_tasks_for(
    task_name: HarnessTaskName,
    task_status: HarnessStatus,
) -> list[HarnessTaskName]:
    """In-memory recommendation for use INSIDE a task body before persistence.

    Uses TASK_TO_PHASE to map *task_name* -> phase, then looks up TRANSITIONS.
    This avoids stale recommendations from reading run_dir before the current
    task is persisted.
    """
    phase = TASK_TO_PHASE.get(task_name)
    if phase is None:
        return []
    return TRANSITIONS.get((phase, task_status), [])
