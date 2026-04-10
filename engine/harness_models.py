from __future__ import annotations

from dataclasses import dataclass, field
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
