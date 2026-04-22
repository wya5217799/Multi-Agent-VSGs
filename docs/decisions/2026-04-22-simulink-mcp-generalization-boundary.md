# 2026-04-22 Simulink MCP Generalization Boundary

## Status

Adopted. General MCP primitives are implemented; VSG helpers remain as project
adapter compatibility wrappers under `slx_helpers/vsg_bridge/`.

## Context

The repository currently has two related but different Simulink layers:

1. A general MCP-facing Simulink tool surface in `engine/mcp_simulink_tools.py`
   and `engine/mcp_server.py`.
2. Project-specific VSG training bridge behavior in `engine/simulink_bridge.py`,
   `env/simulink/`, and several MATLAB helpers under `slx_helpers/`.

The long-term goal is to make the Simulink MCP tool surface reusable for general
Simulink model inspection, editing, execution, and diagnosis. The Yang 2023
VSG reproduction must continue to work, but its domain semantics must not define
the general MCP layer.

The current `slx_helpers/` directory contains both:

- General Simulink primitives, such as block creation, port tracing, parameter
  reads, compile diagnostics, screenshots, and figure capture.
- VSG/RL bridge helpers, such as `slx_warmup`, `slx_step_and_read`,
  `slx_extract_state`, and `slx_build_bridge_config`.

Those VSG/RL helpers are useful, but their current names and placement make the
general layer look more domain-specific than it should be.

## Decision

Generalize by splitting the system into:

```text
General Simulink primitives
  model, block, line, port, parameter, workspace variable,
  SimulationInput, SimulationOutput, timeseries, solver, FastRestart,
  diagnostics, screenshot, figure capture

Project adapters
  VSG/RL episode reset, VSG state extraction, M/D action application,
  Pe/omega/delta interpretation, base-power conversion, Kundur/NE39 contracts
```

`slx_helpers/` may contain reusable MATLAB primitives. It must not introduce new
helpers whose primary API is expressed in VSG, RL, or paper-reproduction terms.

Existing VSG/RL helpers may remain as compatibility wrappers under
`slx_helpers/vsg_bridge/`, but new general MCP tools must expose general
Simulink concepts first and must not call those adapter helpers directly.

## Layer Rules

### Rule 1: General MCP tools use Simulink vocabulary

Public `simulink_*` tools should be described in terms of:

- model lifecycle
- block and subsystem structure
- lines and ports
- block and model parameters
- workspace variables
- simulation windows
- logged signals and `SimulationOutput`
- solver configuration and diagnostics
- screenshots and figures

They should not require users to know about agents, episodes, rewards, VSG
state variables, or paper-specific scenarios.

### Rule 2: VSG/RL semantics stay in project adapters

The following concepts belong in `engine/simulink_bridge.py`, `env/simulink/`,
or scenario-specific code, not in the general MCP tool surface:

- `agent_ids`
- `M_values`
- `D_values`
- `Pe`
- `omega`
- `rocof`
- `delta`
- `episode`
- reward or termination semantics
- VSG-base to system-base conversion
- Kundur-specific or NE39-specific assumptions

### Rule 3: Compatibility wrappers are allowed but must not define the future API

The existing helpers `slx_warmup`, `slx_step_and_read`, `slx_extract_state`, and
`slx_build_bridge_config` may remain while the bridge is migrated. They should
be treated as VSG adapter helpers, not as general Simulink primitives.

If they are refactored, they should call lower-level general primitives instead
of embedding all reset, run, workspace, and signal-read behavior internally.

### Rule 4: The skill routes users to the public tool surface

The installed `simulink-toolbox` skill exists in two local agent environments:

- `C:\Users\27443\.codex\skills\simulink-toolbox`
- `C:\Users\27443\.claude\skills\simulink-toolbox`

Both copies are routing layers for AI operators. Their `map.md` files should
route common Simulink intents to public MCP tools and should clearly mark
`harness_*`, `training_*`, and VSG bridge behavior as project-specific.

`index.json` remains generated from `engine.mcp_server.PUBLIC_TOOLS`. Do not
hand-edit generated inventory data. When public tools change, regenerate and
check both installed skill copies.

## Classification

| Current helper or tool family | Classification | Action |
| --- | --- | --- |
| `slx_add_block`, `slx_add_subsystem`, `slx_connect_blocks`, `slx_delete_block` | General primitive | Keep and expose through general MCP tools |
| `slx_batch_query`, `slx_set_block_params`, `slx_patch_and_verify` | General primitive | Keep; preserve readback and verification behavior |
| `slx_get_block_tree`, `slx_describe_block_ports`, `slx_trace_port_connections`, `slx_inspect_model` | General primitive | Keep; prefer these over XML parsing or ad hoc `find_system` use |
| `slx_compile_diagnostics`, `slx_step_diagnostics`, `slx_solver_audit` | General diagnostic primitive | Keep; use as main verification and diagnosis path |
| `slx_screenshot`, `slx_capture_figure` | General capture primitive | Keep |
| `slx_signal_snapshot` | General signal primitive | Promote to a public MCP tool after contract smoke tests |
| `slx_solver_warning_summary` | General diagnostic candidate | Promote only if a stable public use case exists |
| `slx_validate_model` | Mixed/project-specific | Do not expose as general without replacing VSG assumptions with explicit user-supplied checks |
| `slx_warmup` | VSG adapter plus reusable runtime behavior | Extract general FastRestart/runtime reset primitive; keep wrapper temporarily |
| `slx_step_and_read` | VSG adapter plus reusable run/read behavior | Extract workspace-set, run-window, and signal-read primitives; keep wrapper temporarily |
| `slx_extract_state` | VSG adapter | Move semantics to project adapter after general signal reads exist |
| `slx_build_bridge_config` | VSG bridge adapter | Keep project-facing; do not expose as general MCP tool |

## Target Public Tool Families

The general MCP layer should eventually cover these tool families:

```text
construct:
  simulink_create_model
  simulink_load_model
  simulink_close_model
  simulink_save_model

discover:
  simulink_loaded_models
  simulink_model_status
  simulink_get_block_tree
  simulink_explore_block
  simulink_library_lookup

wire:
  simulink_describe_block_ports
  simulink_trace_port_connections
  simulink_connect_ports

modify:
  simulink_set_block_params
  simulink_delete_block

query:
  simulink_query_params
  simulink_signal_snapshot

runtime:
  simulink_workspace_set
  simulink_run_window
  simulink_compile_diagnostics
  simulink_step_diagnostics
  simulink_solver_audit

execute:
  simulink_run_script
  simulink_run_script_async
  simulink_poll_script

capture:
  simulink_screenshot
  simulink_capture_figure
```

The exact final public list may be smaller if an item does not justify its
maintenance cost. The boundary rule matters more than the count.

## Skill Routing Impact

Both installed `simulink-toolbox` skill copies should gain explicit routing
groups for:

- `runtime`: controlled simulation windows and FastRestart/runtime state
- `signals`: logged signals, `SimulationOutput`, and snapshot reads
- `workspace`: base-workspace variable reads/writes used for model control
- `save/status`: dirty state, save operations, loaded model state

The skill should also keep warning users away from:

- direct XML parsing of `.slx`
- ad hoc `find_system` path guessing
- direct MATLAB shell usage when an MCP tool exists
- treating `harness_*`, `training_*`, or VSG bridge helpers as general tools

## Compatibility Policy

The VSG training path is part of the active paper reproduction path and must not
be broken by the generalization.

Migration order:

1. Add general primitives and tests.
2. Expose stable primitives as public MCP tools.
3. Update the skill routing after public tools exist.
4. Refactor VSG wrappers to call the primitives.
5. Keep old VSG helper names until Kundur and NE39 smoke checks pass.
6. Only remove or rename legacy wrappers after all direct callers are migrated.

## Non-Goals

This decision does not:

- move the MCP server out of this repository
- create a new plugin package
- change the paper reproduction training scripts
- redesign SAC training
- replace `harness_*` or `training_*` workflows
- require immediate deletion of existing VSG helpers

## Consequences

Positive consequences:

- The general MCP layer becomes easier to reuse on non-VSG Simulink models.
- VSG/RL bridge behavior remains useful without defining the public API.
- The skill can route operators more reliably because tool groups match user
  intent instead of project internals.
- Future additions have a clear placement rule.

Tradeoffs:

- Some existing helpers will temporarily be wrappers over more general
  primitives.
- The implementation must preserve current bridge behavior while extracting
  shared runtime and signal-reading behavior.
- The skill index and routing docs must be updated together with public tool
  changes to avoid tool-selection drift.
