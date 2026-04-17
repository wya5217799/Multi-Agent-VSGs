# Simulink Harness V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the V1 harness documents into a working MCP-first framework for `kundur` and `ne39`, including task execution, report writing, and `train_smoke`.

**Architecture:** Add a thin Python harness layer above `engine/mcp_simulink_tools.py` that owns scenario resolution, task contracts, report emission, and stable failure mapping. Keep existing Simulink MCP tools as the execution substrate, then expose the six harness tasks through `engine/mcp_server.py` so agents can enter through task-level tools first and drop down only when needed.

**Tech Stack:** Python 3.x, Pydantic/dataclasses style typed contracts, existing FastMCP server, existing Simulink MCP tools, pytest

**Spec:** `docs/harness/2026-04-05-simulink-harness-v1.md`

---

## File Map

| File | Action | Responsibility |
| --- | --- | --- |
| `engine/harness_models.py` | Create | Typed scenario registry, task names, status values, failure classes, run/task result schemas |
| `engine/harness_registry.py` | Create | Resolve `kundur` / `ne39` to model names, paths, and train entry points |
| `engine/harness_reports.py` | Create | Create `results/harness/<scenario>/<run_id>/`, write manifest and task JSON, optional `summary.md` |
| `engine/harness_tasks.py` | Create | Implement `scenario_status`, `model_inspect`, `model_patch_verify`, `model_diagnose`, `model_report`, `train_smoke` using existing Simulink tools |
| `engine/mcp_server.py` | Modify | Register harness task tools in FastMCP and keep existing low-level tools intact |
| `tests/test_harness_registry.py` | Create | Validate scenario resolution and unsupported-scenario behavior |
| `tests/test_harness_reports.py` | Create | Validate report directory layout and JSON envelope writing |
| `tests/test_harness_tasks.py` | Create | Validate task behavior with mocked Simulink tool calls and failure mapping |
| `tests/test_mcp_server.py` | Modify | Assert harness tools are publicly exposed with stable names |
| `results/harness/.gitkeep` | Create | Keep harness output root present in git without checking in run artifacts |

---

### Task 1: Add Harness Contracts And Scenario Registry

**Files:**
- Create: `engine/harness_models.py`
- Create: `engine/harness_registry.py`
- Test: `tests/test_harness_registry.py`

- [ ] **Step 1: Write the failing registry tests**

Create `tests/test_harness_registry.py` with:

```python
from pathlib import Path


def test_known_scenario_registry_entries_resolve():
    from engine.harness_registry import resolve_scenario

    kundur = resolve_scenario("kundur")
    ne39 = resolve_scenario("ne39")

    assert kundur.scenario_id == "kundur"
    assert kundur.model_name == "kundur_vsg"
    assert kundur.train_entry.as_posix().endswith("scenarios/kundur/train_simulink.py")
    assert ne39.scenario_id == "ne39"
    assert ne39.model_name == "NE39bus_v2"


def test_unknown_scenario_raises_value_error():
    from engine.harness_registry import resolve_scenario

    try:
        resolve_scenario("andes")
    except ValueError as exc:
        assert "kundur" in str(exc)
        assert "ne39" in str(exc)
    else:
        raise AssertionError("resolve_scenario should reject unsupported scenarios")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_harness_registry.py -v`
Expected: FAIL with `ModuleNotFoundError` for `engine.harness_registry`

- [ ] **Step 3: Write minimal contract and registry implementation**

Create `engine/harness_models.py` with:

```python
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
]
HarnessStatus = Literal["ok", "warning", "failed", "skipped"]
FailureClass = Literal[
    "precondition_failed",
    "tool_error",
    "model_error",
    "timed_out",
    "contract_error",
    "smoke_failed",
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
```

Create `engine/harness_registry.py` with:

```python
from __future__ import annotations

from pathlib import Path

from engine.harness_models import ScenarioSpec

_ROOT = Path(__file__).resolve().parents[1]

_REGISTRY = {
    "kundur": ScenarioSpec(
        scenario_id="kundur",
        model_name="kundur_vsg",
        model_dir=_ROOT / "scenarios" / "kundur" / "simulink_models",
        train_entry=_ROOT / "scenarios" / "kundur" / "train_simulink.py",
    ),
    "ne39": ScenarioSpec(
        scenario_id="ne39",
        model_name="NE39bus_v2",
        model_dir=_ROOT / "scenarios" / "new_england" / "simulink_models",
        train_entry=_ROOT / "scenarios" / "new_england" / "train_simulink.py",
    ),
}


def resolve_scenario(scenario_id: str) -> ScenarioSpec:
    try:
        spec = _REGISTRY[scenario_id]
    except KeyError as exc:
        raise ValueError("Unsupported scenario_id. Expected one of: kundur, ne39") from exc

    model_file = spec.model_dir / f"{spec.model_name}.slx"
    if not model_file.exists():
        raise ValueError(f"Resolved model file does not exist: {model_file}")
    if not spec.train_entry.exists():
        raise ValueError(f"Resolved train entry does not exist: {spec.train_entry}")
    return spec
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_harness_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/harness_models.py engine/harness_registry.py tests/test_harness_registry.py
git commit -m "feat(harness): add scenario registry and task contract models"
```

### Task 2: Add Harness Report Writer

**Files:**
- Create: `engine/harness_reports.py`
- Create: `results/harness/.gitkeep`
- Test: `tests/test_harness_reports.py`

- [ ] **Step 1: Write the failing report tests**

Create `tests/test_harness_reports.py` with:

```python
import json


def test_report_writer_creates_run_layout(tmp_path, monkeypatch):
    from engine import harness_reports

    monkeypatch.setattr(harness_reports, "_RESULTS_ROOT", tmp_path / "results" / "harness")

    run_dir = harness_reports.ensure_run_dir("kundur", "run-001")
    assert run_dir.name == "run-001"
    assert run_dir.parent.name == "kundur"


def test_report_writer_writes_manifest_and_task_json(tmp_path, monkeypatch):
    from engine import harness_reports

    monkeypatch.setattr(harness_reports, "_RESULTS_ROOT", tmp_path / "results" / "harness")
    harness_reports.write_manifest(
        scenario_id="kundur",
        run_id="run-001",
        goal="smoke",
        requested_tasks=["scenario_status"],
    )
    harness_reports.write_task_record(
        scenario_id="kundur",
        run_id="run-001",
        task_name="scenario_status",
        payload={"task": "scenario_status", "status": "ok"},
    )

    manifest = json.loads((tmp_path / "results" / "harness" / "kundur" / "run-001" / "manifest.json").read_text())
    task_json = json.loads((tmp_path / "results" / "harness" / "kundur" / "run-001" / "scenario_status.json").read_text())
    assert manifest["scenario_id"] == "kundur"
    assert task_json["task"] == "scenario_status"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_harness_reports.py -v`
Expected: FAIL with `ModuleNotFoundError` for `engine.harness_reports`

- [ ] **Step 3: Write minimal report writer**

Create `engine/harness_reports.py` with:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_RESULTS_ROOT = _ROOT / "results" / "harness"


def ensure_run_dir(scenario_id: str, run_id: str) -> Path:
    run_dir = _RESULTS_ROOT / scenario_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_manifest(*, scenario_id: str, run_id: str, goal: str, requested_tasks: list[str]) -> Path:
    run_dir = ensure_run_dir(scenario_id, run_id)
    payload = {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "goal": goal,
        "requested_tasks": requested_tasks,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    target = run_dir / "manifest.json"
    _dump_json(target, payload)
    return target


def write_task_record(*, scenario_id: str, run_id: str, task_name: str, payload: dict[str, Any]) -> Path:
    run_dir = ensure_run_dir(scenario_id, run_id)
    target = run_dir / f"{task_name}.json"
    _dump_json(target, payload)
    return target
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_harness_reports.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/harness_reports.py results/harness/.gitkeep tests/test_harness_reports.py
git commit -m "feat(harness): add report directory and json writers"
```

### Task 3: Implement `scenario_status` And `model_inspect`

**Files:**
- Create: `engine/harness_tasks.py`
- Test: `tests/test_harness_tasks.py`

- [ ] **Step 1: Write failing tests for the first two tasks**

Start `tests/test_harness_tasks.py` with:

```python
from unittest.mock import MagicMock


def test_scenario_status_returns_registry_fields():
    from engine.harness_tasks import harness_scenario_status

    result = harness_scenario_status(
        scenario_id="kundur",
        run_id="run-001",
        goal="inspect",
    )

    assert result["status"] == "ok"
    assert result["resolved_model_name"] == "kundur_vsg"


def test_model_inspect_calls_underlying_simulink_tools(monkeypatch):
    from engine import harness_tasks

    monkeypatch.setattr(harness_tasks, "simulink_load_model", lambda model_name: {"ok": True, "loaded_models": [model_name]})
    monkeypatch.setattr(harness_tasks, "simulink_get_block_tree", lambda model_name, root_path=None, max_depth=3: {"path": root_path or model_name, "children": []})
    monkeypatch.setattr(harness_tasks, "simulink_query_params", lambda model_name, block_paths, param_names=None: {"items": []})
    monkeypatch.setattr(harness_tasks, "simulink_solver_audit", lambda model_name: {"ok": True, "solver_type": "Fixed-step"})
    monkeypatch.setattr(harness_tasks, "simulink_check_params", lambda model_name, depth=5: {"passed": True, "suspects": []})

    result = harness_tasks.harness_model_inspect(
        scenario_id="kundur",
        run_id="run-001",
        focus_paths=["kundur_vsg/VSG_ES1"],
        query_params=["StopTime"],
    )

    assert result["status"] == "ok"
    assert result["model_loaded"] is True
    assert result["recommended_next_task"] == "model_patch_verify"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_harness_tasks.py -v`
Expected: FAIL with `ModuleNotFoundError` for `engine.harness_tasks`

- [ ] **Step 3: Implement `scenario_status` and `model_inspect`**

Create `engine/harness_tasks.py` with:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from engine.harness_registry import resolve_scenario
from engine.harness_reports import write_task_record
from engine.mcp_simulink_tools import (
    simulink_check_params,
    simulink_get_block_tree,
    simulink_load_model,
    simulink_query_params,
    simulink_solver_audit,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_record(task: str, scenario_id: str, run_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": task,
        "scenario_id": scenario_id,
        "run_id": run_id,
        "status": "ok",
        "started_at": _now(),
        "finished_at": None,
        "inputs": inputs,
        "summary": [],
        "artifacts": [],
        "failures": [],
    }


def _finish(record: dict[str, Any]) -> dict[str, Any]:
    record["finished_at"] = _now()
    write_task_record(
        scenario_id=record["scenario_id"],
        run_id=record["run_id"],
        task_name=record["task"],
        payload=record,
    )
    return record


def harness_scenario_status(*, scenario_id: str, run_id: str, goal: str) -> dict[str, Any]:
    record = _base_record("scenario_status", scenario_id, run_id, {"goal": goal})
    spec = resolve_scenario(scenario_id)
    record.update(
        {
            "resolved_model_name": spec.model_name,
            "resolved_model_dir": str(spec.model_dir),
            "resolved_train_entry": str(spec.train_entry),
            "supported": True,
            "notes": [],
        }
    )
    return _finish(record)


def harness_model_inspect(*, scenario_id: str, run_id: str, focus_paths: list[str] | None = None, query_params: list[str] | None = None) -> dict[str, Any]:
    record = _base_record(
        "model_inspect",
        scenario_id,
        run_id,
        {"focus_paths": focus_paths or [], "query_params": query_params or []},
    )
    spec = resolve_scenario(scenario_id)
    loaded = simulink_load_model(spec.model_name)
    focus_blocks = [simulink_get_block_tree(spec.model_name, root_path=path, max_depth=3) for path in (focus_paths or [])]
    params = simulink_query_params(spec.model_name, focus_paths or [spec.model_name], query_params or None)
    solver = simulink_solver_audit(spec.model_name)
    param_audit = simulink_check_params(spec.model_name)
    record.update(
        {
            "model_loaded": bool(loaded.get("ok", False)),
            "loaded_models": loaded.get("loaded_models", []),
            "focus_blocks": focus_blocks,
            "queried_params": params,
            "solver_audit": solver,
            "param_suspects": param_audit.get("suspects", []),
            "recommended_next_task": "model_patch_verify",
        }
    )
    if not loaded.get("ok", False):
        record["status"] = "failed"
        record["failures"].append({"failure_class": "tool_error", "message": "Failed to load model", "detail": loaded})
    return _finish(record)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_harness_tasks.py -v`
Expected: PASS for the first two tests

- [ ] **Step 5: Commit**

```bash
git add engine/harness_tasks.py tests/test_harness_tasks.py
git commit -m "feat(harness): implement scenario status and model inspect tasks"
```

### Task 4: Implement `model_patch_verify`, `model_diagnose`, And `model_report`

**Files:**
- Modify: `engine/harness_tasks.py`
- Modify: `tests/test_harness_tasks.py`

- [ ] **Step 1: Add failing tests for patch, diagnose, and report**

Append to `tests/test_harness_tasks.py`:

```python
def test_model_patch_verify_maps_patch_result(monkeypatch):
    from engine import harness_tasks

    monkeypatch.setattr(harness_tasks, "simulink_patch_and_verify", lambda *args, **kwargs: {
        "ok": True,
        "applied_edits": [{"block_path": "kundur_vsg/Const", "params": {"Value": "2"}}],
        "readback": [{"block_path": "kundur_vsg/Const", "params": {"Value": "2"}, "error": ""}],
        "update_ok": True,
        "smoke_test_ok": True,
        "smoke_test_summary": {"status": "success"},
    })

    result = harness_tasks.harness_model_patch_verify(
        scenario_id="kundur",
        run_id="run-001",
        edits=[{"block_path": "kundur_vsg/Const", "params": {"Value": "2"}}],
        run_update=True,
        smoke_test_stop_time=0.1,
    )

    assert result["status"] == "ok"
    assert result["smoke_test_ok"] is True


def test_model_diagnose_maps_compile_failure(monkeypatch):
    from engine import harness_tasks

    monkeypatch.setattr(harness_tasks, "simulink_compile_diagnostics", lambda model_name, mode="update": {
        "ok": False,
        "errors": [{"block_path": "kundur_vsg/Const", "message": "bad param", "phase": "update"}],
        "warnings": [],
        "raw_summary": "compile failed",
    })
    monkeypatch.setattr(harness_tasks, "simulink_step_diagnostics", lambda *args, **kwargs: {
        "ok": False,
        "status": "sim_error",
        "top_warnings": [],
        "top_errors": [],
        "raw_summary": "sim failed",
    })
    monkeypatch.setattr(harness_tasks, "simulink_solver_audit", lambda model_name: {"ok": True})
    monkeypatch.setattr(harness_tasks, "simulink_check_params", lambda model_name, depth=5: {"passed": True, "suspects": []})

    result = harness_tasks.harness_model_diagnose(
        scenario_id="kundur",
        run_id="run-001",
        diagnostic_window={"start_time": 0.0, "stop_time": 0.1},
        signals=[],
        capture_warnings=True,
    )

    assert result["status"] == "failed"
    assert result["recommended_next_task"] == "model_patch_verify"


def test_model_report_summarizes_prior_task_records(tmp_path, monkeypatch):
    from engine import harness_reports, harness_tasks

    monkeypatch.setattr(harness_reports, "_RESULTS_ROOT", tmp_path / "results" / "harness")
    harness_reports.write_task_record(
        scenario_id="kundur",
        run_id="run-001",
        task_name="scenario_status",
        payload={"task": "scenario_status", "status": "ok"},
    )

    result = harness_tasks.harness_model_report(
        scenario_id="kundur",
        run_id="run-001",
        include_summary_md=False,
    )

    assert result["run_status"] in {"ok", "warning"}
    assert "scenario_status" in result["completed_tasks"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_harness_tasks.py -v`
Expected: FAIL with missing task functions

- [ ] **Step 3: Implement the three tasks**

Add to `engine/harness_tasks.py`:

```python
from pathlib import Path

from engine import harness_reports
from engine.mcp_simulink_tools import (
    simulink_compile_diagnostics,
    simulink_patch_and_verify,
    simulink_signal_snapshot,
    simulink_step_diagnostics,
)


def harness_model_patch_verify(*, scenario_id: str, run_id: str, edits: list[dict[str, Any]], run_update: bool = True, smoke_test_stop_time: float | None = None) -> dict[str, Any]:
    record = _base_record(
        "model_patch_verify",
        scenario_id,
        run_id,
        {"edits": edits, "run_update": run_update, "smoke_test_stop_time": smoke_test_stop_time},
    )
    spec = resolve_scenario(scenario_id)
    patch = simulink_patch_and_verify(spec.model_name, edits=edits, run_update=run_update, smoke_test_stop_time=smoke_test_stop_time, timeout_sec=60)
    record.update(
        {
            "applied_edits": patch.get("applied_edits", []),
            "readback": patch.get("readback", []),
            "update_ok": patch.get("update_ok"),
            "smoke_test_ok": patch.get("smoke_test_ok"),
            "smoke_test_summary": patch.get("smoke_test_summary"),
            "recommended_next_task": "model_report" if patch.get("ok", False) else "model_diagnose",
        }
    )
    if not patch.get("ok", False):
        record["status"] = "failed"
        record["failures"].append({"failure_class": "model_error", "message": "Patch or verification failed", "detail": patch})
    return _finish(record)


def harness_model_diagnose(*, scenario_id: str, run_id: str, diagnostic_window: dict[str, float], signals: list[Any], capture_warnings: bool = True) -> dict[str, Any]:
    record = _base_record(
        "model_diagnose",
        scenario_id,
        run_id,
        {"diagnostic_window": diagnostic_window, "signals": signals, "capture_warnings": capture_warnings},
    )
    spec = resolve_scenario(scenario_id)
    compile_info = simulink_compile_diagnostics(spec.model_name, mode="update")
    step_info = simulink_step_diagnostics(
        spec.model_name,
        diagnostic_window["start_time"],
        diagnostic_window["stop_time"],
        capture_warnings=capture_warnings,
    )
    signal_info = simulink_signal_snapshot(spec.model_name, diagnostic_window["stop_time"], signals, allow_partial=True) if signals else {}
    solver = simulink_solver_audit(spec.model_name)
    param_audit = simulink_check_params(spec.model_name)
    record.update(
        {
            "compile_ok": compile_info.get("ok", False),
            "compile_errors": compile_info.get("errors", []),
            "step_status": step_info.get("status", ""),
            "warning_groups": step_info.get("top_warnings", []),
            "signal_snapshot": signal_info,
            "solver_audit": solver,
            "param_suspects": param_audit.get("suspects", []),
            "suspected_root_causes": [],
            "recommended_next_task": "model_patch_verify",
        }
    )
    if (not compile_info.get("ok", False)) or (step_info.get("status") not in {"success", "ok"}):
        record["status"] = "failed"
    return _finish(record)


def harness_model_report(*, scenario_id: str, run_id: str, include_summary_md: bool = True) -> dict[str, Any]:
    record = _base_record("model_report", scenario_id, run_id, {"include_summary_md": include_summary_md})
    run_dir = harness_reports.ensure_run_dir(scenario_id, run_id)
    completed_tasks = []
    for path in sorted(run_dir.glob("*.json")):
        if path.name == "manifest.json":
            continue
        completed_tasks.append(path.stem)
    record.update(
        {
            "run_status": "ok",
            "completed_tasks": completed_tasks,
            "blocked_tasks": [],
            "key_findings": [],
            "next_actions": [],
        }
    )
    if include_summary_md:
        summary_path = run_dir / "summary.md"
        summary_path.write_text(f"# Harness Summary\n\nRun: `{run_id}`\n\nTasks: {', '.join(completed_tasks)}\n", encoding="utf-8")
        record["artifacts"].append(str(summary_path))
    return _finish(record)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_harness_tasks.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/harness_tasks.py tests/test_harness_tasks.py
git commit -m "feat(harness): add patch verify, diagnose, and report tasks"
```

### Task 5: Implement `train_smoke` With Explicit Scope Limit

**Files:**
- Modify: `engine/harness_tasks.py`
- Modify: `tests/test_harness_tasks.py`

- [ ] **Step 1: Add failing `train_smoke` test**

Append to `tests/test_harness_tasks.py`:

```python
def test_train_smoke_runs_existing_train_entry(monkeypatch):
    from engine import harness_tasks

    class DummyCompleted:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(harness_tasks.subprocess, "run", lambda *args, **kwargs: DummyCompleted())

    result = harness_tasks.harness_train_smoke(
        scenario_id="kundur",
        run_id="run-001",
        episodes=1,
        mode="simulink",
    )

    assert result["status"] == "ok"
    assert result["smoke_passed"] is True
    assert "--episodes" in result["command"]
```

- [ ] **Step 2: Run tests to verify it fails**

Run: `pytest tests/test_harness_tasks.py -v`
Expected: FAIL with missing `harness_train_smoke`

- [ ] **Step 3: Implement `train_smoke`**

Add to `engine/harness_tasks.py`:

```python
import subprocess
import sys


def harness_train_smoke(*, scenario_id: str, run_id: str, episodes: int = 1, mode: str = "simulink") -> dict[str, Any]:
    record = _base_record(
        "train_smoke",
        scenario_id,
        run_id,
        {"episodes": episodes, "mode": mode},
    )
    spec = resolve_scenario(scenario_id)
    command = [
        sys.executable,
        str(spec.train_entry),
        "--mode",
        mode,
        "--episodes",
        str(episodes),
    ]
    completed = subprocess.run(
        command,
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        check=False,
    )
    record.update(
        {
            "command": " ".join(command),
            "exit_code": completed.returncode,
            "native_log_paths": [],
            "native_checkpoint_paths": [],
            "smoke_passed": completed.returncode == 0,
        }
    )
    if completed.returncode != 0:
        record["status"] = "failed"
        record["failures"].append(
            {
                "failure_class": "smoke_failed",
                "message": "Training smoke command failed",
                "detail": {"stdout": completed.stdout, "stderr": completed.stderr},
            }
        )
    return _finish(record)
```

- [ ] **Step 4: Run tests to verify it passes**

Run: `pytest tests/test_harness_tasks.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/harness_tasks.py tests/test_harness_tasks.py
git commit -m "feat(harness): add terminal train smoke task"
```

### Task 6: Expose Harness Tasks Through MCP Server

**Files:**
- Modify: `engine/mcp_server.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Add failing MCP server contract test**

Add to `tests/test_mcp_server.py`:

```python
def test_harness_tools_are_exposed_in_public_contract():
    from engine import mcp_server

    expected = [
        "harness_scenario_status",
        "harness_model_inspect",
        "harness_model_patch_verify",
        "harness_model_diagnose",
        "harness_model_report",
        "harness_train_smoke",
    ]

    public_names = [tool.__name__ for tool in mcp_server.PUBLIC_TOOLS]
    for name in expected:
        assert name in public_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mcp_server.py -v`
Expected: FAIL because harness tools are not yet registered

- [ ] **Step 3: Register harness tools**

Modify `engine/mcp_server.py` imports and `PUBLIC_TOOLS`:

```python
from engine.harness_tasks import (
    harness_model_diagnose,
    harness_model_inspect,
    harness_model_patch_verify,
    harness_model_report,
    harness_scenario_status,
    harness_train_smoke,
)
```

Insert at the top of `PUBLIC_TOOLS`:

```python
    harness_scenario_status,
    harness_model_inspect,
    harness_model_patch_verify,
    harness_model_diagnose,
    harness_model_report,
    harness_train_smoke,
```

Update the MCP instructions string to include one sentence:

```python
        "Prefer the harness_* task tools for Kundur/NE39 Simulink workflows; "
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_mcp_server.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/mcp_server.py tests/test_mcp_server.py
git commit -m "feat(mcp): expose harness task tools in server contract"
```

### Task 7: End-To-End Verification

**Files:**
- No new files

- [ ] **Step 1: Run unit tests for the harness layer**

Run: `pytest tests/test_harness_registry.py tests/test_harness_reports.py tests/test_harness_tasks.py tests/test_mcp_server.py -v`
Expected: PASS

- [ ] **Step 2: Run a smoke call through Python, not direct MATLAB**

Run:

```bash
python -c "from engine.harness_tasks import harness_scenario_status; print(harness_scenario_status(scenario_id='kundur', run_id='local-check', goal='verify-contract')['resolved_model_name'])"
```

Expected output:

```text
kundur_vsg
```

- [ ] **Step 3: Run one inspection task against a real model if MATLAB is available**

Run:

```bash
python -c "from engine.harness_tasks import harness_model_inspect; r=harness_model_inspect(scenario_id='kundur', run_id='local-inspect', focus_paths=['kundur_vsg/VSG_ES1'], query_params=['StopTime']); print(r['status'])"
```

Expected output:

```text
ok
```

- [ ] **Step 4: Verify report files were written**

Run:

```bash
Get-ChildItem 'results/harness/kundur/local-inspect'
```

Expected output includes:

```text
manifest.json
model_inspect.json
```

- [ ] **Step 5: Final commit**

```bash
git add engine/harness_models.py engine/harness_registry.py engine/harness_reports.py engine/harness_tasks.py engine/mcp_server.py tests/test_harness_registry.py tests/test_harness_reports.py tests/test_harness_tasks.py tests/test_mcp_server.py results/harness/.gitkeep
git commit -m "feat(harness): implement simulink harness v1 task layer"
```

---

## Self-Review

Spec coverage:

- `AGENTS.md` navigation is already done and this plan does not reopen it.
- Harness task contracts are covered by Tasks 1, 3, 4, and 5.
- `results/harness/` report writing is covered by Task 2.
- MCP-first exposure is covered by Task 6.
- `train_smoke` remains terminal-only and is covered by Task 5.

No-placeholder scan:

- No `TODO`, `TBD`, or deferred “add tests later” steps remain.

Type consistency:

- Task names stay aligned with the V1 spec: `scenario_status`, `model_inspect`, `model_patch_verify`, `model_diagnose`, `model_report`, `train_smoke`.
- Public MCP function names are consistently prefixed as `harness_*`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-05-simulink-harness-v1-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
