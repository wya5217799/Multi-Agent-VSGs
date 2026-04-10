# AGENTS.md

## Scope

- Primary line: Simulink-only model building for `kundur` and `ne39`.
- First priority: make agents complete Simulink modeling more reliably.
- Default execution layer: MCP tools in `engine/mcp_simulink_tools.py`.
- Training scope: `train_smoke` only. Do not design convergence loops, tuning frameworks, ODE, or ANDES modeling mainlines here.

## Start Here

1. Read `docs/decisions/2026-04-05-harness-architecture.md`.
2. Read `docs/decisions/2026-04-06-project-memory-system.md`.
3. Follow task contracts in `docs/harness/2026-04-05-simulink-harness-v1.md`.
4. Write harness outputs under `results/harness/` as defined in `results/harness/README.md`.
5. Use `MEMORY.md` as the index into project facts, process notes, decisions, and paper notes.
6. Use `docs/devlog/commit-guidelines.md` when preparing commits that may need a devlog or decision.

## Scenario Registry

- `kundur`
  - model: `kundur_vsg`
  - model dir: `scenarios/kundur/simulink_models/`
  - training entry: `scenarios/kundur/train_simulink.py`
- `ne39`
  - model: `NE39bus_v2`
  - model dir: `scenarios/new_england/simulink_models/`
  - training entry: `scenarios/new_england/train_simulink.py`

## Default Harness Order

1. `scenario_status`
2. `model_inspect`
3. `model_patch_verify`
4. `model_diagnose`
5. `model_report`
6. `train_smoke` only after modeling tasks are green

## Guardrails

- Prefer MCP tools over ad hoc MATLAB or shell scripts.
- Use scripts only when the task contract explicitly allows them.
- Keep reports machine-first and compact.
- Do not mix harness outputs into legacy `results/sim_*` folders.
- Keep project memory layered:
  - facts in `results/harness/`
  - process notes in `docs/devlog/`
  - stable rules in `docs/decisions/`
  - paper-facing summaries in `docs/paper/`
