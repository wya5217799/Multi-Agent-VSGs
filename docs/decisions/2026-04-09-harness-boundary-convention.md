# 2026-04-09 Harness Boundary Convention

## Status

Adopted.

## Context

As of 2026-04-09, the project has three independent runtime layers that operate
alongside each other:

1. **Harness layer** — Simulink modeling quality gate + training smoke trigger
   (`engine/harness_*.py`, results written to `results/harness/`)
2. **Training layer** — RL training loops, TrainingMonitor, checkpointing
   (`scenarios/*/train_*.py`, `utils/monitor.py`, results to `results/sim_*/`)
3. **Agent memory layer** — project knowledge persistence across conversations
   (`.claude/projects/*/memory/`, MEMORY.md index)

The harness and training layers are currently **zero-coupled at import level**:
training scripts do not import any `engine.harness_*` module, and harness tasks
do not import `TrainingMonitor` or any training-layer code. The only interface
between them is the subprocess launch in `harness_train_smoke_start` and the
shared filesystem paths used by `harness_train_smoke_poll`.

This decision records the boundary rules that must be maintained as both layers
evolve, and marks the internal responsibility split inside `harness_tasks.py`.

## Boundary Rules

### Rule 1: No cross-layer imports

```
harness layer  ──import──>  training layer    FORBIDDEN
training layer ──import──>  harness layer     FORBIDDEN
```

The only permitted interface is **filesystem + subprocess**:
- Harness may launch a training entry point as a subprocess.
- Harness may read training output files (e.g. `training_status.json`,
  `training_log.json`) from agreed-upon paths.
- Training scripts must NOT read `results/harness/` JSON records at runtime.

### Rule 2: Harness stays Simulink-scoped

Harness tasks (`scenario_status`, `model_inspect`, `model_patch_verify`,
`model_diagnose`, `model_report`) must remain meaningful without any training
run having taken place. A "modeling-only" workflow (inspect → diagnose → patch →
report, stop) must be fully functional with zero training involvement.

`train_smoke_start/poll` are the **only** harness tasks that touch training
infrastructure, and they do so only via subprocess + file reads.

### Rule 3: Agent memory stays out of the Python runtime

The `.claude/projects/*/memory/` markdown files are read and written by the
agent (Claude) during conversation. No Python module should import, parse, or
write to this layer at runtime. The `memory_hints` dict emitted by
`harness_model_report` is a **suggestion to the agent**, not a direct write.

### Rule 4: Shared capabilities are extracted only when a second consumer exists

Currently, the record primitives (`_base_record`, `_record_failure`, `_finish`,
`harness_reports`) live inside the harness layer. If a second independent
consumer (e.g. a standalone evaluation runner, a future ODE harness) needs the
same status-persistence primitives, extract them to `engine/run_support.py`.

Do NOT extract preemptively based on anticipated need — wait for the second
consumer to exist.

## Internal Structure of harness_tasks.py

`harness_tasks.py` intentionally contains two responsibility zones. These are
**not** separate modules today (no second consumer justifies the split), but
they must remain conceptually distinct:

```
harness_tasks.py
├── Zone A: Modeling task orchestration
│   scenario_status, model_inspect, model_patch_verify,
│   model_diagnose, model_report
│   — Pure modeling quality gate; must work without any training
│
└── Zone B: Training smoke process management
    train_smoke (deprecated), train_smoke_start, train_smoke_poll
    — Thin subprocess launcher + status reader
    — Does NOT own training logic; only invokes the training entry point
```

If a third responsibility zone appears (e.g. evaluation pipeline, ODE model
smoke), that is the signal to split `harness_tasks.py`.

## What This Does NOT Address

- **Training status protocol (Stage 2)**: having training scripts write a
  `training_status.json` every N episodes for `train_smoke_poll` to read.
  This is a separate decision, triggered when `train_smoke_poll` proves
  insufficient without it.

- **Unified run_id across modeling and training**: desirable in the future;
  not blocked on this decision.

- **Memory hint schema expansion**: `memory_hints` is currently an informal
  dict. Formalising its schema is deferred until the agent consuming it needs
  a richer contract.

## Supersedes / Extends

- Extends `2026-04-05-harness-architecture.md` (MCP-first, light harness)
- Consistent with `2026-04-06-project-memory-system.md` (three-layer memory,
  harness = fact layer only)
