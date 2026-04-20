# Harness Type Contracts, Decomposition, and Explicit Flow State

> P0 + P0.5 refactor plan for the current harness control layer.

**Goal:** Refactor [engine/harness_tasks.py](/Users/27443/Desktop/Multi-Agent%20%20VSGs/engine/harness_tasks.py) into a type-safer, better-separated, and more explicit control layer without changing any external MCP behavior.

## Non-goals

- Do not introduce LangGraph, Temporal, or PydanticAI as runtime dependencies.
- Do not change public MCP tool names or top-level return shape.
- Do not change training loop behavior in `train_*.py`.
- Do not change the public interfaces of:
  - [engine/harness_reports.py](/Users/27443/Desktop/Multi-Agent%20%20VSGs/engine/harness_reports.py)
  - [engine/harness_registry.py](/Users/27443/Desktop/Multi-Agent%20%20VSGs/engine/harness_registry.py)
  - [engine/harness_reference.py](/Users/27443/Desktop/Multi-Agent%20%20VSGs/engine/harness_reference.py)
  - [engine/harness_repair.py](/Users/27443/Desktop/Multi-Agent%20%20VSGs/engine/harness_repair.py)

## Constraints

- No new external dependencies. Use stdlib plus existing `dataclasses`.
- All existing `tests/test_harness_*.py` must continue to pass.
- After decomposition, `harness_tasks.py` should be a thin compatibility entrypoint only.

## Current Problems

[engine/harness_models.py](/Users/27443/Desktop/Multi-Agent%20%20VSGs/engine/harness_models.py) already defines:

```python
ScenarioId
HarnessTaskName
HarnessStatus
FailureClass
ScenarioSpec
HarnessFailure
```

But [engine/harness_tasks.py](/Users/27443/Desktop/Multi-Agent%20%20VSGs/engine/harness_tasks.py) still builds records as loose `dict[str, Any]` values:

- `_base_record()` returns a plain dict.
- `_record_failure()` mutates a dict with untyped failure payloads.
- every task uses `record.update({...})` with no field-level validation.
- `recommended_next_task` is hard-coded inline.
- Zone A / Zone B exists only as comments, not as module boundaries.

This creates three different issues:

1. field drift risk in task envelopes
2. poor separation between modeling and smoke process management
3. implicit flow logic that is hard to test and easy to regress

## Phase 1: Typed Task Contracts

**Objective:** Make task envelope construction type-safe while preserving the current external JSON shape.

### Step 1.1: Extend `engine/harness_models.py`

Add typed dataclasses for the harness envelope and task-specific payloads.

```python
from dataclasses import dataclass, field
from typing import Any

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
```

Add task-specific payload dataclasses for:

- `ScenarioStatusResult`
- `ModelInspectResult`
- `ModelPatchResult`
- `ModelDiagnoseResult`
- `ModelReportResult`
- `SmokeStartResult`
- `SmokePollResult`

These payload classes are internal construction helpers. MCP tools still return `dict[str, Any]` at the boundary.

### Step 1.2: Introduce `engine/task_primitives.py`

Extract record lifecycle helpers from `harness_tasks.py`.

```python
def create_record(task: HarnessTaskName, scenario_id: ScenarioId, run_id: str, inputs: dict[str, Any]) -> TaskRecord: ...
def record_failure(record: TaskRecord, failure_class: FailureClass, message: str, detail: dict[str, Any] | None = None) -> None: ...
def finish(record: TaskRecord) -> dict[str, Any]: ...
def load_task_record(run_dir: Path, task_name: str) -> dict[str, Any] | None: ...
def list_existing_task_records(run_dir: Path) -> list[dict[str, Any]]: ...
```

`finish()` should call `record.to_dict()` and then persist through `harness_reports.write_task_record()`.

### Step 1.3: Build task results through typed payloads

Pattern:

```python
# Before
record.update({
    "model_loaded": bool(...),
    "loaded_models": ...,
    "focus_blocks": ...,
})

# After
result = ModelInspectResult(
    model_loaded=bool(...),
    loaded_models=...,
    focus_blocks=...,
)
```

Then merge the typed payload into the final dict only at the boundary.

### Step 1.4: Envelope rule

`TaskRecord` is the canonical outer envelope.

Do not add ad hoc fields such as `notes` in later phases unless Phase 1 explicitly models them and updates:

- `TaskRecord`
- `to_dict()`
- snapshot tests
- envelope documentation

Until then, advisory text must reuse `summary`.

### Step 1.5: Tests

- existing `tests/test_harness_tasks.py` still passes
- add `tests/test_harness_models.py`

New tests should verify:

- `TaskRecord.to_dict()` matches the legacy envelope field-for-field
- `HarnessFailure` serializes identically to the old format
- task result dataclasses have sensible defaults

### Files

- Modify: [engine/harness_models.py](/Users/27443/Desktop/Multi-Agent%20%20VSGs/engine/harness_models.py)
- Create: `engine/task_primitives.py`
- Modify: [engine/harness_tasks.py](/Users/27443/Desktop/Multi-Agent%20%20VSGs/engine/harness_tasks.py)
- Create: `tests/test_harness_models.py`

**Commit:** `refactor(harness): type-safe task records via dataclass contracts`

## Phase 2: Module Decomposition

**Objective:** Split the current single-file harness implementation into clear module boundaries.

### Target structure

```text
engine/
  harness_models.py
  harness_reports.py
  harness_registry.py
  harness_reference.py
  harness_repair.py
  task_primitives.py
  modeling_tasks.py
  smoke_tasks.py
  harness_tasks.py
```

### Step 2.1: Create `engine/modeling_tasks.py`

Move Zone A logic here:

- `harness_scenario_status()`
- `harness_model_inspect()`
- `harness_model_patch_verify()`
- `harness_model_diagnose()`
- `harness_model_report()`

Move supporting helpers here:

- `_ensure_loaded()`
- `_read_prior_evidence()`
- `_collect_findings()`
- `_build_memory_hints()`
- `_write_summary()`

### Step 2.2: Create `engine/smoke_tasks.py`

Move Zone B logic here:

- `harness_train_smoke()` (deprecated shim)
- `harness_train_smoke_start()`
- `harness_train_smoke_poll()`

Move supporting helpers here:

- `_train_smoke_paths()`
- `_train_smoke_preconditions()`
- `_recover_pid_from_disk()`
- `_is_pid_alive()`
- `_parse_training_summary()`
- `_collect_finished()`

Keep module-level runtime state here:

- `_SMOKE_PROCESSES`
- `_SMOKE_LOG_HANDLES`

### Step 2.3: Reduce `engine/harness_tasks.py` to a compatibility shim

`harness_tasks.py` should re-export the public task functions so MCP imports do not change.

### Step 2.4: Tests

- existing `tests/test_harness_tasks.py` still passes
- add `tests/test_modeling_tasks.py`
- add `tests/test_smoke_tasks.py`

### Files

- Create: `engine/modeling_tasks.py`
- Create: `engine/smoke_tasks.py`
- Modify: [engine/harness_tasks.py](/Users/27443/Desktop/Multi-Agent%20%20VSGs/engine/harness_tasks.py)
- Create: `tests/test_modeling_tasks.py`
- Create: `tests/test_smoke_tasks.py`

**Commit:** `refactor(harness): decompose harness_tasks into modeling and smoke modules`

## Phase 3: Explicit Flow State Without Weakening Gates

**Objective:** Make flow state explicit for recommendation, reporting, and testing, without collapsing richer gate logic into a simplistic transition table.

### Current issue

Today the flow logic is implicit in:

1. hard-coded `recommended_next_task`
2. `_train_smoke_preconditions()`
3. Zone A / Zone B boundary comments

The flow is real, but not modeled directly.

### Design rule for Phase 3

Split the concept into two layers:

1. `TaskPhase + TRANSITIONS`
   - describes persisted run flow
   - powers recommendation and operator visibility
   - should stay advisory at first

2. explicit gate predicates
   - decide whether a sensitive action is actually allowed
   - may depend on richer run facts than the latest persisted phase
   - example: `model_report.run_status` and "no failed modeling tasks"

Do not use the transition table as the sole truth for `train_smoke_start`.

### Step 3.1: Define `TaskPhase` and transition tables

Add to `engine/harness_models.py`:

```python
from enum import Enum

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
```

Important: this table is only an advisory flow model for persisted task state. It is not enough to decide all gates.

### Step 3.2: Add `engine/task_state.py`

Expose persisted-state helpers:

```python
def infer_phase(run_dir: Path) -> tuple[TaskPhase, HarnessStatus]: ...
def allowed_next_tasks(run_dir: Path) -> list[HarnessTaskName]: ...
def check_transition(run_dir: Path, target_task: HarnessTaskName) -> tuple[bool, str]: ...
```

Also add an in-memory helper for the current task result:

```python
def recommended_next_tasks_for(
    task_name: HarnessTaskName,
    task_status: HarnessStatus,
    *,
    run_status: HarnessStatus | None = None,
) -> list[HarnessTaskName]: ...
```

Rule:

- `allowed_next_tasks(run_dir)` is for already-persisted run state
- `recommended_next_tasks_for(...)` is for use inside a task body before the current record has been written

This avoids stale recommendations inside the current task.

### Step 3.3: Use transition checks as advisory only

Pattern:

```python
transition_ok, transition_reason = check_transition(run_dir, "model_inspect")
if not transition_ok:
    record.summary.append(f"transition_advisory: {transition_reason}")
```

Do not write advisory data into undeclared fields such as `record.notes`.

For next-task recommendation inside a task body:

```python
next_tasks = recommended_next_tasks_for("model_inspect", record.status)
result.recommended_next_task = next_tasks[0] if next_tasks else None
```

Do not compute this from `allowed_next_tasks(run_dir)` before the current task is persisted.

### Step 3.4: Keep explicit smoke gate predicates

Do not replace `_train_smoke_preconditions()` with `check_transition(run_dir, "train_smoke_start")`.

Instead:

```python
def _train_smoke_preconditions(run_dir):
    failures = []

    transition_ok, transition_reason = check_transition(run_dir, "train_smoke_start")
    if not transition_ok:
        failures.append(f"transition_advisory: {transition_reason}")

    scenario_status = load_task_record(run_dir, "scenario_status")
    if not scenario_status or scenario_status.get("status") != "ok":
        failures.append("scenario_status must exist with status ok")

    model_report = load_task_record(run_dir, "model_report")
    report_run_status = None if model_report is None else model_report.get("run_status")
    if report_run_status not in {"ok", "warning"}:
        failures.append("model_report must exist with run_status ok or warning")

    for task_name in _MODELING_TASKS:
        record = load_task_record(run_dir, task_name)
        if record and record.get("status") == "failed":
            failures.append(f"{task_name} is failed")

    hard_failures = [item for item in failures if not item.startswith("transition_advisory:")]
    return (not hard_failures), failures
```

This preserves the stronger existing gate while still exposing flow-state diagnostics.

### Step 3.5: Tests

Add `tests/test_task_state.py` covering:

- `test_infer_phase_empty_run`
- `test_infer_phase_after_scenario_status`
- `test_allowed_next_after_inspect_ok`
- `test_allowed_next_after_inspect_failed`
- `test_check_transition_blocks_smoke_before_report`
- `test_transition_table_covers_all_phases`

Add regression tests for the review findings:

- `test_recommended_next_tasks_for_inspect_ok_uses_in_memory_status`
- `test_transition_advisory_appends_to_summary_not_notes`
- `test_train_smoke_preconditions_require_model_report_run_status`
- `test_train_smoke_preconditions_reject_failed_modeling_task_even_if_phase_is_model_reported`

### Files

- Modify: [engine/harness_models.py](/Users/27443/Desktop/Multi-Agent%20%20VSGs/engine/harness_models.py)
- Create: `engine/task_state.py`
- Modify: `engine/modeling_tasks.py`
- Modify: `engine/smoke_tasks.py`
- Create: `tests/test_task_state.py`

**Commit:** `refactor(harness): make flow state explicit without weakening gates`

## PR Strategy

| PR | Scope | Depends on |
|---|---|---|
| PR 1 | Phase 1: typed task contracts + task primitives | none |
| PR 2 | Phase 2: modeling/smoke decomposition | PR 1 |
| PR 3 | Phase 3A: explicit task phase + advisory transition helpers | PR 2 |
| PR 4 | Phase 3B: gate normalization if still needed after review | PR 3 |

Each PR should be independently reviewable and safely revertible.

## Final Target Layout

```text
engine/
  harness_models.py
  harness_reports.py
  harness_registry.py
  harness_reference.py
  harness_repair.py
  task_primitives.py
  task_state.py
  modeling_tasks.py
  smoke_tasks.py
  harness_tasks.py
  mcp_simulink_tools.py
```

## Phase 4 (P1): Training Callback Unification

> **Status:** directional only — concrete design deferred until overall refactor scope is clear.

**Core problem:** Each `train_*.py` script reimplements monitoring, checkpointing, early-stop, and metrics logging inline. Adding a new cross-cutting concern (e.g. physics summary) means editing every training script independently. There is no shared extension point.

**Abstraction boundary:** A callback protocol sits between the training loop and its side-effects. The training loop calls hooks at well-defined moments; callbacks decide what to do. The training loop does not know which callbacks are registered. Callbacks do not mutate RL algorithm state — they observe and optionally signal abort.

**Direction of change:**
- Extract a minimal callback ABC with lifecycle hooks (episode boundaries, eval, checkpoint, end)
- Existing `TrainingMonitor` becomes one callback implementation, not the orchestrator
- Training scripts compose a callback list at startup; the loop drives it
- SB3's `on_step → bool` abort pattern is the reference design, not a runtime dependency

**What this does NOT decide yet:** hook granularity (per-step vs per-episode), callback ordering semantics, whether callbacks are registered declaratively or imperatively, or how this interacts with a potential future training orchestration layer.

---

## Phase 5 (P2): Agent Layer Evaluation

> **Status:** directional only — scope depends on how the Agent Control Layer restructure (separate plan) lands.

**Core problem:** There is no automated way to verify that the MCP tool surface behaves correctly as a _sequence_ — individual tools are tested, but the flow contract (transition ordering, precondition enforcement, failure propagation, idempotency) is only validated manually by running the harness end-to-end.

**Abstraction boundary:** Evaluation tests sit above the MCP tool surface. They call the same public Python functions that MCP routes to, but in scripted sequences with injected faults. They do not test MATLAB or Simulink behavior — they test the harness's _control logic_ in isolation.

**Direction of change:**
- Scenario-based integration tests that exercise full task chains against mock engine state
- Illegal transition tests (e.g. smoke before report) verify structured rejection
- Fault injection tests verify that `HarnessFailure` records propagate correctly
- Idempotency tests verify that repeated calls don't corrupt persisted state
- Inspect AI remains a candidate for adversarial evaluation if the tool surface grows; not a near-term dependency

**What this does NOT decide yet:** whether evaluation lives alongside unit tests or in a separate `tests/eval/` tree, the boundary between harness control tests and future training control tests, or whether LLM-in-the-loop evaluation is ever needed.

---

## Phase 6 (P2): Tiered Failure Recovery

> **Status:** directional only — tier boundaries depend on operational experience with the current `FailureClass` taxonomy.

**Core problem:** All failures are currently treated uniformly: record and surface. But failures have very different recovery profiles — a transient MATLAB IPC timeout is fundamentally different from a missing model file. Without classification, the agent (or operator) cannot make informed recovery decisions.

**Abstraction boundary:** Recovery tiers annotate existing `HarnessFailure` records. The tier system classifies _what kind of recovery is appropriate_, not _how to recover_. Actual recovery logic (retry, restart, escalate) is implemented by the caller or a future recovery orchestrator, not baked into the failure record itself.

**Direction of change:**
- Tier 1 (transient): auto-retryable without state change — IPC timeouts, brief engine stalls
- Tier 2 (process-level): recoverable via engine restart — MATLAB crash, corrupted session
- Tier 3 (escalate): requires human or agent decision — missing files, unknown errors, repeated Tier 2
- Classification is a property of the failure, not the task — the same task can produce failures at different tiers
- DLRover's three-tier model is the reference pattern; distributed recovery aspects (node restart, Flash Checkpoint) are out of scope for single-machine setup

**What this does NOT decide yet:** whether `recovery_tier` is a field on `HarnessFailure` or a lookup table keyed by `FailureClass`, whether auto-retry lives in `task_primitives` or in a separate recovery module, or how tiered recovery interacts with the transition state machine.

---

## Phase 7 (P3): FastMCP Migration

> **Status:** directional only — blocked on FastMCP stability assessment and Claude Code MCP client compatibility verification.

**Core problem:** `engine/mcp_server.py` uses hand-rolled tool registration with manual schema construction. Adding or modifying a tool requires editing both the implementation and the schema in lockstep. There is no automatic validation that function signatures match declared schemas.

**Abstraction boundary:** FastMCP replaces the _protocol and schema layer_ only. Tool implementations stay in `modeling_tasks.py`, `smoke_tasks.py`, and any future task modules. The MCP server file becomes a thin registration surface — decorators on top of existing functions — not a new implementation layer.

**Direction of change:**
- `@mcp.tool` decorators auto-generate schemas from type hints, eliminating manual schema drift
- Tool organization by category (model_mgmt / inspection / modification / simulation / training) for discoverability
- Stdout isolation (à la simulink-mcp) to prevent MATLAB output from corrupting JSON-RPC transport
- The `harness_tasks.py` re-export shim remains as the stable import path for non-MCP consumers

**What this does NOT decide yet:** whether to adopt FastMCP's server composition (`mount`) for multi-domain tool namespacing, whether progress reporting (`ctx.report_progress`) is feasible given Claude Code's current lack of MCP progress notification support, or whether this migration should happen before or after the Agent Control Layer restructure adds new tool families.

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| task envelope drift breaks MCP consumers | snapshot-test `TaskRecord.to_dict()` against the legacy envelope |
| import path changes break MCP server | keep `harness_tasks.py` as the stable re-export module |
| transition model becomes too strict too early | keep Phase 3 advisory-first; do not gate on `TRANSITIONS` alone |
| smoke gate becomes weaker than today | preserve explicit precondition predicates in `smoke_tasks.py` |
| module split loses `_SMOKE_PROCESSES` behavior | keep process registries module-local in `smoke_tasks.py` |
