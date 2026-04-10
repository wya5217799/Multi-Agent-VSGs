# 2026-04-05 Harness Architecture Decision

## Context

Current priority is to make the agent complete Simulink model-building more reliably.

Stable constraints:

- Keep MCP as the main execution interface.
- Do not pivot to a script-led architecture.
- Focus the mainline on Simulink for `kundur` and `ne39`.
- Keep training scope to smoke only.
- Do not design convergence proof, tuning frameworks, ODE mainline, or ANDES model-building mainline here.

## Decision

Adopt `MCP-first + light harness`.

This means:

- The existing MCP tool layer remains the primary way the agent acts on Simulink models.
- A thin harness layer defines a small set of stable task contracts above those tools.
- A very short repo navigation layer tells agents where to start and where to write evidence.

This does not mean:

- replacing MCP with scripts
- building a heavyweight orchestration framework
- expanding scope to non-Simulink modeling lines

## V1 Landing Scope

This first landing includes only:

1. a minimal `AGENTS.md` navigation skeleton
2. a harness task list with explicit input and output contracts
3. a reporting spec under `results/harness/`

It explicitly excludes:

- ODE mainline
- ANDES model-building mainline
- convergence proof
- tuning framework design
- broad multi-agent scheduling design

## Recommended Task Set

The first stable task set is:

1. `scenario_status`
2. `model_inspect`
3. `model_patch_verify`
4. `model_diagnose`
5. `model_report`
6. `train_smoke`

The purpose of this set is to constrain:

- call order
- task intent
- input and output shape
- failure classes
- report location

## Repo Entry Points

- Navigation skeleton: `AGENTS.md`
- Harness contracts: `docs/harness/2026-04-05-simulink-harness-v1.md`
- Report spec: `results/harness/README.md`

## Reporting Decision

Harness evidence should live under `results/harness/` and stay separate from legacy training outputs such as `results/sim_kundur/` and `results/sim_ne39/`.

Machine-readable JSON is the default artifact format.

Short Markdown summaries are optional.

## Rationale

This approach keeps the main risk low:

- it preserves the MCP investment already made in `engine/mcp_simulink_tools.py`
- it gives agents a stable default task order
- it creates a single place to inspect run evidence
- it limits training to a final smoke check instead of turning the project back toward training-system design

## Next Session Entry

Next round should begin by reading:

- `MEMORY.md`
- `docs/decisions/2026-04-05-harness-architecture.md`
