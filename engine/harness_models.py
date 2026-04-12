from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal

ScenarioId = Literal["kundur", "ne39"]
HarnessTaskName = Literal[
    "scenario_status",
    "model_inspect",
    "model_patch_verify",
    "model_diagnose",
    "model_report",
    "train_smoke",
    "train_smoke_start",
    "train_smoke_poll",
]
HarnessStatus = Literal["ok", "warning", "failed", "skipped", "running"]
FailureClass = Literal[
    "precondition_failed",
    "tool_error",
    "model_error",
    "timed_out",
    "contract_error",
    "smoke_failed",
    # Specialised tool-error subtypes used in model_inspect / model_diagnose.
    "load_error",         # model file could not be loaded via load_system
    "matlab_return_type", # MATLAB returned an unexpected type (e.g. scalar struct)
    "compile_error",      # compile/update_diagram diagnostics failed
    "simulation_error",   # sim() or step_diagnostics call failed
]


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: ScenarioId
    model_name: str
    model_dir: Path
    train_entry: Path


@dataclass
class HarnessFailure:
    failure_class: FailureClass
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Typed task envelope
# ---------------------------------------------------------------------------

@dataclass
class TaskRecord:
    task: HarnessTaskName
    scenario_id: ScenarioId
    run_id: str
    status: HarnessStatus
    started_at: str
    finished_at: str | None
    inputs: dict[str, Any]
    summary: list[str]
    artifacts: list[str]
    failures: list[HarnessFailure]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "scenario_id": self.scenario_id,
            "run_id": self.run_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "inputs": self.inputs,
            "summary": self.summary,
            "artifacts": self.artifacts,
            "failures": [
                {
                    "failure_class": f.failure_class,
                    "message": f.message,
                    "detail": f.detail,
                }
                for f in self.failures
            ],
        }


# ---------------------------------------------------------------------------
# Task-specific payload dataclasses (internal construction helpers)
# ---------------------------------------------------------------------------

def _payload_to_dict(obj: object) -> dict[str, Any]:
    """Convert a payload dataclass to a dict, omitting None-valued optional fields."""
    result: dict[str, Any] = {}
    for k, v in obj.__dict__.items():
        if v is not None:
            result[k] = v
    return result


@dataclass
class ScenarioStatusResult:
    resolved_model_name: str = ""
    resolved_model_dir: str = ""
    resolved_train_entry: str = ""
    supported: bool = False
    reference_manifest_path: str = ""
    reference_summary: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    recommended_next_task: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _payload_to_dict(self)


@dataclass
class ModelInspectResult:
    model_loaded: bool = False
    loaded_models: list[str] = field(default_factory=list)
    focus_blocks: list[Any] = field(default_factory=list)
    queried_params: dict[str, Any] = field(default_factory=dict)
    solver_audit: dict[str, Any] = field(default_factory=dict)
    param_suspects: list[Any] = field(default_factory=list)
    reference_validation: dict[str, Any] = field(default_factory=dict)
    recommended_next_task: str | None = None
    _timings: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _payload_to_dict(self)


@dataclass
class ModelPatchResult:
    applied_edits: list[Any] = field(default_factory=list)
    readback: list[Any] = field(default_factory=list)
    update_ok: bool = False
    smoke_test_ok: bool | None = None
    smoke_test_summary: dict[str, Any] = field(default_factory=dict)
    recommended_next_task: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _payload_to_dict(self)


@dataclass
class ModelDiagnoseResult:
    compile_ok: bool = False
    compile_errors: list[Any] = field(default_factory=list)
    step_status: str = ""
    warning_groups: list[Any] = field(default_factory=list)
    signal_snapshot: dict[str, Any] = field(default_factory=dict)
    prior_solver_audit: dict[str, Any] = field(default_factory=dict)
    prior_param_suspects: list[Any] = field(default_factory=list)
    suspected_root_causes: list[str] = field(default_factory=list)
    repair_hints: list[str] = field(default_factory=list)
    recommended_next_task: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _payload_to_dict(self)


@dataclass
class ModelReportResult:
    run_status: str = ""
    completed_tasks: list[str] = field(default_factory=list)
    blocked_tasks: list[str] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    recommended_followups: list[str] = field(default_factory=list)
    memory_hints: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _payload_to_dict(self)


@dataclass
class SmokeStartResult:
    command: str = ""
    pid: int | None = None
    smoke_started: bool = False
    stdout_path: str | None = None
    stderr_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _payload_to_dict(self)


@dataclass
class SmokePollResult:
    process_status: str = ""
    pid: int | None = None
    exit_code: int | None = None
    native_log_paths: list[str] = field(default_factory=list)
    native_checkpoint_paths: list[str] = field(default_factory=list)
    smoke_passed: bool = False
    training_summary: dict[str, Any] | None = None
    recovered_from_disk: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return _payload_to_dict(self)


# ---------------------------------------------------------------------------
# Explicit flow state (Phase 3) — ADVISORY ONLY
# ---------------------------------------------------------------------------


class TaskPhase(str, Enum):
    NOT_STARTED = "not_started"
    SCENARIO_RESOLVED = "scenario_resolved"
    MODEL_INSPECTED = "model_inspected"
    MODEL_PATCHED = "model_patched"
    MODEL_DIAGNOSED = "model_diagnosed"
    MODEL_REPORTED = "model_reported"
    SMOKE_STARTED = "smoke_started"
    SMOKE_COMPLETED = "smoke_completed"


TRANSITIONS: dict[tuple[TaskPhase, HarnessStatus], list[HarnessTaskName]] = {
    (TaskPhase.NOT_STARTED, "ok"): ["scenario_status"],
    (TaskPhase.SCENARIO_RESOLVED, "ok"): ["model_inspect"],
    (TaskPhase.SCENARIO_RESOLVED, "failed"): [],
    (TaskPhase.MODEL_INSPECTED, "ok"): ["model_patch_verify", "model_report"],
    (TaskPhase.MODEL_INSPECTED, "warning"): ["model_patch_verify", "model_diagnose"],
    (TaskPhase.MODEL_INSPECTED, "failed"): ["model_diagnose"],
    (TaskPhase.MODEL_PATCHED, "ok"): ["model_report"],
    (TaskPhase.MODEL_PATCHED, "failed"): ["model_diagnose"],
    (TaskPhase.MODEL_DIAGNOSED, "ok"): ["model_patch_verify"],
    (TaskPhase.MODEL_DIAGNOSED, "failed"): ["model_patch_verify"],
    (TaskPhase.MODEL_REPORTED, "ok"): ["train_smoke_start"],
    (TaskPhase.MODEL_REPORTED, "warning"): ["train_smoke_start"],
    (TaskPhase.MODEL_REPORTED, "failed"): ["model_inspect", "model_diagnose"],
    (TaskPhase.SMOKE_STARTED, "running"): ["train_smoke_poll"],
    (TaskPhase.SMOKE_COMPLETED, "ok"): [],
    (TaskPhase.SMOKE_COMPLETED, "failed"): ["model_diagnose"],
}

TASK_TO_PHASE: dict[HarnessTaskName, TaskPhase] = {
    "scenario_status": TaskPhase.SCENARIO_RESOLVED,
    "model_inspect": TaskPhase.MODEL_INSPECTED,
    "model_patch_verify": TaskPhase.MODEL_PATCHED,
    "model_diagnose": TaskPhase.MODEL_DIAGNOSED,
    "model_report": TaskPhase.MODEL_REPORTED,
    "train_smoke_start": TaskPhase.SMOKE_STARTED,
    "train_smoke_poll": TaskPhase.SMOKE_COMPLETED,
}
