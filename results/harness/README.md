# results/harness

This directory stores harness outputs only. Do not mix these records into legacy `results/sim_*` folders.

This directory is the fact layer of the project memory system. It records what happened in a run, but it does not replace:

- `docs/devlog/` for process notes
- `docs/decisions/` for stable rules
- `docs/paper/` for paper-facing summaries
- `MEMORY.md` for cross-layer navigation

## Layout

```text
results/harness/
  <scenario_id>/
    <run_id>/
      manifest.json
      scenario_status.json
      model_inspect.json
      model_patch_verify.json
      model_diagnose.json
      model_report.json
      train_smoke.json
      summary.md
      attachments/
```

Rules:

- `train_smoke.json` is optional.
- `summary.md` is optional.
- `attachments/` is optional and only for compact supporting payloads that do not fit the main task JSON files.

## Naming

- `scenario_id` must be `kundur` or `ne39`.
- `run_id` should be stable and sortable, for example `20260405-220000-kundur-build-fix`.
- Task files must use the exact task name as the filename.

## Required Files

### `manifest.json`

Minimal run metadata:

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
  ],
  "created_at": "2026-04-05T22:00:00+08:00"
}
```

### Task JSON files

Each task JSON must include:

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

### `summary.md`

Optional human-facing digest. Keep it short:

- run status
- key findings
- next actions
- pointers to any native training logs or checkpoints
- whether the run should trigger a follow-up devlog or decision

## Artifact Policy

- Prefer references over copies when a native training log already exists elsewhere.
- If a task output is already machine-readable, keep the main result in JSON and only store excerpts in `attachments/`.
- Large MATLAB stdout dumps should not become the primary artifact unless they are the only useful failure evidence.

## Relationship To Existing Results

- Keep existing training outputs in their current scenario folders such as `results/sim_kundur/` and `results/sim_ne39/`.
- Harness reports only record what happened in a run and where native artifacts landed.
- The harness directory is the index of evidence, not a replacement for all historical outputs.
- If a run creates a new root cause, repair path, or durable rule, add a linked devlog or decision outside this directory.
