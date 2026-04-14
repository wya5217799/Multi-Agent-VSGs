# AGENTS.md

## Scope

- Repo control model: dual control lines.
- **Model Control** governs model correctness, diagnosis, repair, and smoke readiness.
- **Training Control** governs run lifecycle, verdicts, and comparison of training outputs.
- Default execution layer: MCP tools in `engine/mcp_simulink_tools.py` (model side); training-side MCP surface is thin and currently centered on smoke bridge behavior.
- Current phase: model issues may still exist, but training is acknowledged as a parallel control line, not a permanent afterthought.

## Start Here

> Governed by `docs/navigation_manifest.toml` (single source of truth).
> Update the manifest when entries change; AGENTS.md is validated against it.

1. Read `engine/harness_reference.py` - Authoritative harness state; read before any agent action (Re-evaluate when: harness architecture change)
   - **Exception — pure launch query**: call `get_training_launch_status(scenario_id)` from `engine/training_launch.py` instead; no need to read harness file directly
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

## Training Launch Flow (Simulink)

Bootstrap sequence enforced in `scenarios/*/train_simulink.py`:
1. **Init** — parse args, generate `run_id`, resolve `run_dir` path (no mkdir yet)
2. **Backend-ready** — `env.reset()` triggers MATLAB startup + warmup; if this fails, no orphaned directories are created
3. **Commit outputs** — create {run_dir}/checkpoints/, {run_dir}/logs/, write training_status.json (status: running)
4. **Train loop** — episode iterations with periodic checkpointing

To launch from shell: `scripts/launch_training.ps1 [kundur|ne39|both]`
To query before launch: `engine/training_launch.py::get_training_launch_status(scenario_id)` → returns `launch.python_executable`, `launch.script`, `launch.args`

## Training Monitor (AI Observation)

Two MCP tools for observing live and post-mortem RL training runs (implemented in `engine/training_tasks.py`):

- **`training_status(scenario_id, run_id=None)`** — Tier 1 poll: merges heartbeat fields from `utils/run_protocol.py::read_training_status` with the latest_state.json snapshot. Use for routine progress checks (cheap — no JSONL scan).
- **`training_diagnose(scenario_id, run_id=None)`** — Tier 2 deep scan: parses `events.jsonl`, classifies alerts / eval rewards / checkpoints / monitor_stop. Use only when anomalies are suspected.

Both default to the most-recent run via `utils/run_protocol.py::find_latest_run` (status-aware; never raw mtime). Pass `run_id` to target a specific run.

## Default Working Mode

1. Use **Model Control** when the question is about model validity, closed-loop semantics, or patching.
2. Use **Training Control** when the question is about run quality, verdicts, comparison, or artifact interpretation.
3. Route from training back to model work when training evidence indicates model-side physical or semantic faults.

## Default Harness Order (Model Control)

1. `scenario_status`
2. `model_inspect`
3. `model_patch_verify`
4. `model_diagnose`
5. `model_report`
6. `train_smoke_start` / `train_smoke_poll` only after modeling tasks are green

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

For relational navigation and drift discovery, graph output may be consulted as a secondary aid. See `docs/agent_layer/graph-policy.md`.
