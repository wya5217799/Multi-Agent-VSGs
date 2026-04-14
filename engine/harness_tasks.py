from __future__ import annotations

# Compatibility shim — real implementations live in modeling_tasks / smoke_tasks.
# MCP tools import from here; do not add new logic.

import subprocess  # noqa: F401 — tests monkeypatch harness_tasks.subprocess

from engine.modeling_tasks import (  # noqa: F401
    harness_model_diagnose,
    harness_model_inspect,
    harness_model_patch_verify,
    harness_model_report,
    harness_scenario_status,
    # Helpers re-exported so monkeypatch targets on harness_tasks still resolve.
    # The actual task functions in modeling_tasks import these from their own module,
    # so patching here does NOT affect runtime behaviour.  Tests that need to mock
    # these must patch on engine.modeling_tasks (see test_harness_tasks.py).
)
from engine.smoke_tasks import (  # noqa: F401
    _SMOKE_LOG_HANDLES,
    _SMOKE_PROCESSES,
    _parse_training_summary,
    harness_train_smoke,
    harness_train_smoke_full,
    harness_train_smoke_poll,
    harness_train_smoke_start,
)

# Re-export task_primitives helpers used by tests
from engine.task_primitives import (  # noqa: F401
    list_existing_task_records,
    load_task_record,
)

# Re-export _PROJECT_ROOT so tests that monkeypatch it still work.
# smoke_tasks defines its own _PROJECT_ROOT; patching it there is the correct
# approach (tests updated accordingly).
from engine.smoke_tasks import _PROJECT_ROOT  # noqa: F401

__all__ = [
    "harness_scenario_status",
    "harness_model_inspect",
    "harness_model_patch_verify",
    "harness_model_diagnose",
    "harness_model_report",
    "harness_train_smoke",
    "harness_train_smoke_full",
    "harness_train_smoke_start",
    "harness_train_smoke_poll",
]
