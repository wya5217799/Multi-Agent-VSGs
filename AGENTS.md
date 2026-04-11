# AGENTS.md

## Scope

- Primary line: Simulink-only model building for `kundur` and `ne39`.
- First priority: make agents complete Simulink modeling more reliably.
- Default execution layer: MCP tools in `engine/mcp_simulink_tools.py`.
- Training scope: `train_smoke` only. Do not design convergence loops, tuning frameworks, ODE, or ANDES modeling mainlines here.

## Start Here

> Governed by `docs/navigation_manifest.toml` (single source of truth).
> Update the manifest when entries change; AGENTS.md is validated against it.

1. Read `engine/harness_reference.py` - Authoritative harness state; read before any agent action (Re-evaluate when: harness architecture change)
2. Read `scenarios/contract.py` - ScenarioContract; single source of truth for scenario constants (Re-evaluate when: scenario parameter schema change)
3. Read `docs/harness/2026-04-05-simulink-harness-v1.md` - Task contracts; defines harness task I/O and sequencing (Re-evaluate when: harness task definition change)
4. Read `results/harness/README.md` - Output directory structure; where to write harness evidence (Re-evaluate when: output artifact policy change)
5. Read `docs/devlog/commit-guidelines.md` - Commit and devlog standards for preparing commits (Re-evaluate when: commit workflow change)

For project memory index, see `MEMORY.md`. For historical architecture decisions, see `docs/decisions/`.

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
