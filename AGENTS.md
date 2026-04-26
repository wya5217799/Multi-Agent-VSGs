# AGENTS.md

## Purpose

This repository is a **reproduction of Yang et al. TPWRS 2023**: multi-agent SAC
controlling virtual synchronous generator inertia (H) and damping (D).

Everything here serves this single goal. When in doubt about whether to add,
keep, or remove something, ask: **does this help reproduce a paper result, or
does it standardize a repeated AI operation on the repo?** If neither, do not do it.

- Paper facts: `docs/paper/yang2023-fact-base.md`
- Reproduction status: `docs/paper/experiment-index.md`

The **Simulink backend is the active reproduction path**. ANDES and ODE backends
exist historically but are not the current focus — do not spend effort on them
unless the user explicitly asks. **When ODE work is requested**: entry point is
`env/ode/` (`power_system.py`, `multi_vsg_env.py`) + `env/ode/NOTES.md`.

## Scope

This repo has two layers with a strict hierarchy:

1. **Paper Track** (primary) — `agents/` + `env/simulink/` + `scenarios/*/train_simulink.py` + `plotting/` + `config.py`
   - The actual work: simulate, train, plot, compare with paper.
2. **AI Collaboration Track** (supporting) — `engine/` + `utils/` + MCP tools
   - Exists to let Claude Code operate the Paper Track reliably across sessions.
   - Must not absorb Paper Track logic.

Within Track 2, control splits into three layers (see `docs/decisions/2026-04-17-control-surface-convention.md`):
- **Model Harness** — model correctness gate: scenario_status / model_inspect / model_patch_verify / model_diagnose / model_report.
- **Smoke Bridge** — entry verification bridge connecting Model Harness → Training Control Surface: train_smoke_* tools.
- **Training Control Surface** — training observation / diagnosis / evaluation (NOT a harness): get_training_launch_status / training_status / training_diagnose / training_evaluate_run / training_compare_runs.

> **Terminology**: `harness` = Model Harness only. `train_smoke_*` = Smoke Bridge (not harness).
> `training_*` = Control Surface observation tools (not harness).
> `scenario_id` accepts only `kundur` or `ne39`; all other variants are invalid.

Default execution layer for Track 2: MCP tools in `engine/mcp_simulink_tools.py`.

**Directory roles** (helper scripts layer):
- `scripts/` — general repo helper scripts (launch, lint, profiling, workspace hygiene).
- `probes/` — scenario-specific, reusable regression probes bound to concrete model semantics. `probes/<scenario>/gates/` holds pipeline gate scripts for the active development phase. One-off debugging does NOT go here — archive it when done.

## Non-Goals

AGENTS.md and the AI Collaboration Track do NOT aim to:
- become a general AI agent framework
- replace `env/` / `agents/` / `plotting/` with harness tasks
- orchestrate multi-agent AI workflows (single Claude session + MCP is enough)
- absorb ad-hoc debugging into permanent tasks (use `probes/` or throwaway scripts)
- invest in ANDES or ODE backends beyond their current state
- track metrics beyond what paper reproduction requires

## Start Here

> Governed by `docs/control_manifest.toml` (single source of truth).
> Update the manifest when entries change; AGENTS.md is validated against it.

1. Read `engine/harness_reference.py` - Authoritative harness state; read before any agent action (Re-evaluate when: harness architecture change)
   - **Exception — pure launch query**: call `get_training_launch_status(scenario_id)` from `engine/training_launch.py` instead; no need to read harness file directly
2. Read `scenarios/contract.py` - ScenarioContract; single source of truth for scenario constants (Re-evaluate when: scenario parameter schema change)
3. Read `docs/harness/2026-04-05-simulink-harness-v1.md` - Task contracts; defines harness task I/O and sequencing (Re-evaluate when: harness task definition change)
4. Read `results/harness/README.md` - Output directory structure; where to write harness evidence (Re-evaluate when: output artifact policy change)
5. Read `docs/devlog/commit-guidelines.md` - Commit and devlog standards for preparing commits (Re-evaluate when: commit workflow change)

For paper reproduction / physics / RL: start from `docs/paper/yang2023-fact-base.md` + `config.py`.

For project memory index, see `MEMORY.md`. For historical architecture decisions, see `docs/decisions/`.

Registry source of truth: `scenarios/contract.py` + `engine/harness_registry.py`

Launch entry: `engine/training_launch.py::get_training_launch_status(scenario_id)`

Monitor tools: see `engine/mcp_*.py` docstrings

## Default Working Mode

0. **Paper Track first** — if the request is about reproducing a paper result
   (figure/table/claim), start from `docs/paper/yang2023-fact-base.md` and
   the relevant `scenarios/*/train_simulink.py`. Do not route into Model Harness / Training Control Surface
   unless training evidence demands it.
1. Use **Model Harness** when the question is about model validity, closed-loop semantics, or patching.
2. Use **Smoke Bridge** (`train_smoke_*`) only after Model Harness tasks are green.
3. Use **Training Control Surface** when the question is about run quality, verdicts, comparison, or artifact interpretation.
4. Route from Training Control Surface back to Model Harness when training evidence indicates model-side physical or semantic faults.

## Default Orders

### Paper Track
1. Check `docs/paper/yang2023-fact-base.md` for the paper claim to reproduce
2. Verify `config.py` matches paper hyperparameters (values from the paper must cite it)
3. Run training (via Training Control below)
4. Generate figure via `plotting/` scripts
5. Compare with paper; log outcome to `docs/paper/experiment-index.md`

### Model Harness
1. `scenario_status`
2. `model_inspect`
3. `model_patch_verify`
4. `model_diagnose`
5. `model_report`

### Smoke Bridge
1. `train_smoke_start` — only after all Model Harness tasks are green
2. `train_smoke_poll` — poll until pass/fail verdict

### Training Control Surface
1. `get_training_launch_status` → 2. launch script
→ 3. `training_status` (routine) → 4. `training_diagnose` (on anomaly)
→ 5. update `scenarios/<topo>/NOTES.md` (post-run, manual)

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
- **Anti-drift rule**: before adding a new harness task / engine module / utils helper,
  answer in one sentence: *which paper result does this help reproduce, or which
  repeated AI operation does this standardize?* If neither, do not add it.
- **Paper parameter tracing**: any value in `config.py` that comes from the paper
  must cite it (e.g. `# Yang 2023 Table II`).
- **Non-paper experiments** (hyperparameter exploration, ablation) must live
  under `scenarios/<name>/experiments/` and not pollute the scenario's `scenarios/*/train_simulink.py`.

For relational navigation and drift discovery, graph output may be consulted as a secondary aid. See `docs/agent_layer/graph-policy.md`.

Repository-specific Simulink routing overlays live in `docs/agent_layer/simulink-project-routing/`; Kundur/NE39 model-specific notes live under `docs/agent_layer/simulink-project-routing/models/`.
