# Simulink Harness V1

## Goal

This first harness version is a thin task layer above the current MCP Simulink tools. It exists to make model-building runs more stable and repeatable for the two active scenarios:

- `kundur`
- `ne39`

It does not replace MCP as the execution interface, and it does not introduce a script-led control plane.

## Memory Relationship

Harness is the fact layer of the project memory system.

- Write run evidence under `results/harness/`
- Use `docs/devlog/` for important process notes
- Use `docs/decisions/` for stable rules
- Use `MEMORY.md` as the cross-layer index

Harness outputs should not absorb full debugging narratives or long-term project decisions.

## Non-Goals

- ODE mainline
- ANDES model-building mainline
- convergence proof
- hyperparameter tuning framework
- multi-agent orchestration beyond a single harness run

## Shared Run Contract

Each harness run resolves one scenario and one immediate modeling goal.

Required run inputs:

```json
{
  "run_id": "20260405-220000-kundur-build-fix",
  "scenario_id": "kundur",
  "goal": "stabilize compile path for the active Simulink model",
  "requested_tasks": [
    "scenario_status",
    "model_inspect",
    "model_patch_verify",
    "model_diagnose",
    "model_report"
  ]
}
```

Scenario resolution is fixed in V1:

| scenario_id | model_name | model_dir | train_entry |
| --- | --- | --- | --- |
| `kundur` | `kundur_vsg` | `scenarios/kundur/simulink_models/` | `scenarios/kundur/train_simulink.py` |
| `ne39` | `NE39bus_v2` | `scenarios/new_england/simulink_models/` | `scenarios/new_england/train_simulink.py` |

For NE39, `scenario_id` is `ne39`. `NE39bus_v2` is the Simulink
`model_name`, not a supported `scenario_id`.

Every task writes a compact JSON record with the same top-level envelope:

```json
{
  "task": "model_inspect",
  "scenario_id": "kundur",
  "run_id": "20260405-220000-kundur-build-fix",
  "status": "ok",
  "started_at": "2026-04-05T22:00:00+08:00",
  "finished_at": "2026-04-05T22:01:10+08:00",
  "inputs": {},
  "summary": [],
  "artifacts": [],
  "failures": []
}
```

Allowed `status` values:

- `ok`
- `warning`
- `failed`
- `skipped`

Allowed failure classes:

- `precondition_failed`
- `tool_error`
- `model_error`
- `timed_out`
- `contract_error`
- `smoke_failed`

## Task List

### 1. `scenario_status`

Purpose:

- Resolve the scenario to the exact model name, directories, and training entry.
- Confirm that the selected scenario is inside the supported V1 mainline.

Inputs:

```json
{
  "scenario_id": "kundur"
}
```

Allowed actions:

- Read repo files and config only.
- No model mutation.

Preferred evidence sources:

- `scenarios/*/config_simulink.py`
- model files under `scenarios/*/simulink_models/`

Required outputs:

```json
{
  "resolved_model_name": "kundur_vsg",
  "resolved_model_dir": "scenarios/kundur/simulink_models",
  "resolved_train_entry": "scenarios/kundur/train_simulink.py",
  "supported": true,
  "notes": []
}
```

Stops the run if:

- `scenario_id` is not `kundur` or `ne39`
- the model file cannot be resolved

### 2. `model_inspect`

Purpose:

- Establish the current model state before any patching.
- Gather only the minimum structure needed to decide the next edit or diagnosis step.

Inputs:

```json
{
  "scenario_id": "kundur",
  "focus_paths": [
    "kundur_vsg/VSG_ES1"
  ],
  "query_params": [
    "StopTime",
    "Solver"
  ]
}
```

Allowed actions:

- `simulink_load_model`
- `simulink_loaded_models`
- `simulink_inspect_model`
- `simulink_get_block_tree`
- `simulink_query_params`
- `simulink_solver_audit`
- `simulink_check_params`

Disallowed actions:

- block creation
- parameter writes
- training launch

Required outputs:

```json
{
  "model_loaded": true,
  "loaded_models": [
    "kundur_vsg"
  ],
  "focus_blocks": [],
  "solver_audit": {},
  "param_suspects": [],
  "recommended_next_task": "model_patch_verify"
}
```

### 3. `model_patch_verify`

Purpose:

- Apply a bounded edit set and verify that the requested values are actually present afterward.

Inputs:

```json
{
  "scenario_id": "kundur",
  "edits": [
    {
      "block_path": "kundur_vsg/SomeBlock",
      "params": {
        "Value": "2"
      }
    }
  ],
  "run_update": true,
  "smoke_test_stop_time": 0.1
}
```

Allowed actions:

- `simulink_patch_and_verify`
- `simulink_query_params`
- `simulink_check_params`

Disallowed actions:

- broad manual edit sequences when `simulink_patch_and_verify` can express the change
- training launch

Required outputs:

```json
{
  "applied_edits": [],
  "readback": [],
  "update_ok": true,
  "smoke_test_ok": true,
  "smoke_test_summary": {},
  "recommended_next_task": "model_report"
}
```

Escalate to `model_diagnose` if:

- update fails
- smoke test fails
- readback differs from requested edits

### 4. `model_diagnose`

Purpose:

- Explain why a model still does not compile or run after inspection or patch verification.
- For NE39 closed-loop feedback issues, run the repeatable helper
  `vsg_probe_ne39_phang_sensitivity` through `simulink_run_script`.
  Prefix any additional diagnostic output with `RESULT:`; ordinary MATLAB
  `disp` or `fprintf` output is intentionally suppressed by the quiet runner.

Inputs:

```json
{
  "scenario_id": "kundur",
  "diagnostic_window": {
    "start_time": 0.0,
    "stop_time": 0.1
  },
  "signals": [],
  "capture_warnings": true
}
```

Allowed actions:

- `simulink_compile_diagnostics`
- `simulink_step_diagnostics`
- `simulink_solver_audit`
- `simulink_solver_warning_summary`
- `simulink_signal_snapshot`
- `simulink_check_params`

Disallowed actions:

- opportunistic patching inside the same task
- training launch

Required outputs:

```json
{
  "compile_ok": false,
  "compile_errors": [],
  "step_status": "sim_error",
  "warning_groups": [],
  "signal_snapshot": {},
  "suspected_root_causes": [],
  "recommended_next_task": "model_patch_verify"
}
```

NE39 closed-loop helper output should include these stable `RESULT:` fields:

- `phAng param exists`
- `baseline Pe/omega`
- `phAng +30deg Pe/omega`
- `M/D low omega/delta/Pe`
- `M/D base omega/delta/Pe`
- `M/D high omega/delta/Pe`
- `open-loop no-delta Pe drift`
- `delta range`
- `warmup init phAng preserved`
- `classification`

### 5. `model_report`

Purpose:

- Summarize the run in a stable machine-readable record plus an optional short human summary.

Inputs:

```json
{
  "scenario_id": "kundur",
  "include_summary_md": true
}
```

Allowed actions:

- Read prior harness task outputs
- Aggregate prior task evidence

Disallowed actions:

- further model mutation
- training launch

Required outputs:

```json
{
  "run_status": "warning",
  "completed_tasks": [
    "scenario_status",
    "model_inspect",
    "model_patch_verify",
    "model_diagnose"
  ],
  "blocked_tasks": [],
  "key_findings": [],
  "next_actions": [],
  "memory_hints": {
    "should_write_devlog": false,
    "should_write_decision": false,
    "reason": []
  }
}
```

`memory_hints` is a lightweight reminder field. Use it when a run introduces:

- a new root cause
- a new repair path
- an important process conclusion
- a stable rule worth promoting to `docs/decisions/`

### 6. `train_smoke`

Purpose:

- Run the smallest training check after the modeling path is green.
- Validate that the current scenario still reaches the training entry point.

V1 limit:

- smoke only
- no claim of learning quality
- no tuning loop
- no convergence language

Preconditions:

- `scenario_status` is `ok`
- modeling tasks are not `failed`
- `model_report.run_status` is `ok` or `warning`

Inputs:

```json
{
  "scenario_id": "kundur",
  "episodes": 1,
  "mode": "simulink"
}
```

Allowed actions:

- invoke the existing scenario training entry as a last-mile validation step
- read the produced native training log and checkpoint paths

Disallowed actions:

- custom training harnesses
- hyperparameter search
- automatic reruns for score chasing

Required outputs:

```json
{
  "command": "python scenarios/kundur/train_simulink.py --mode simulink --episodes 1",
  "exit_code": 0,
  "native_log_paths": [],
  "native_checkpoint_paths": [],
  "smoke_passed": true
}
```

## Default Flow

V1 default flow is linear:

1. `scenario_status`
2. `model_inspect`
3. `model_patch_verify` if a bounded fix is already known
4. `model_diagnose` if verification or compile fails
5. `model_report`
6. `train_smoke` only when modeling is stable enough

## Reminder Policy

Harness should remind, not block.

Recommended reminder points:

1. `model_report` should indicate whether a devlog or decision is likely needed.
2. Important commits associated with a run should prompt the agent to check whether a devlog or decision should be added.

These reminders should stay lightweight and should not turn the harness into a full memory-management system.

## Why This Is Still MCP-First

- The harness defines task boundaries, not a new execution substrate.
- The primary action surface remains the MCP tool layer in `engine/mcp_simulink_tools.py`.
- `train_smoke` is the only task that may touch a scenario training entry, and even there it is a terminal validation step, not the main control path.
