# 2026-04-23 Simulink Toolbox Generic Skill Boundary

## Status

Adopted.

## Context

The installed `simulink-toolbox` skill is intended to be reused across multiple
Simulink projects. It currently includes project-specific Yang 2023 VSG
reproduction routing such as `harness_*`, `training_*`, Kundur/NE39, VSG bridge,
agent, episode, and paper reproduction language.

That makes the global skill too specific. A second similar VSG-specific skill
would also be harmful because two near-duplicate Simulink skills can compete for
the same user prompts and make tool routing less predictable.

## Decision

Keep exactly one installed skill named `simulink-toolbox`.

The skill may specialize in the Simulink domain, but it must not specialize in
this repository's Yang/VSG project. Its routing docs and generated inventory
must cover only general Simulink concepts:

- model lifecycle
- block and subsystem structure
- lines and ports
- block and model parameters
- workspace variables
- controlled simulation windows
- logged signals and `SimulationOutput`
- solver configuration and diagnostics
- screenshots and MATLAB figures
- script execution as an escape hatch

The following project-specific concepts must stay out of the installed generic
skill:

- Yang 2023
- Kundur
- NE39
- VSG
- `harness_*`
- `training_*`
- `simulink_bridge_status`
- `SimulinkBridge`
- `get_training_launch_status`
- agent
- episode
- reward
- Pe/omega/delta interpretation
- paper reproduction workflow

Project-specific routing belongs in this repository's `AGENTS.md`, scenario
contracts, harness docs, training docs, and decisions.

## Consequences

The same `simulink-toolbox` skill can be reused safely in unrelated Simulink
projects.

This repository still keeps its paper-reproduction routing, but those rules are
provided by repository context rather than the global skill.

The index generator must emit a generic skill inventory by default for both:

- `C:\Users\27443\.codex\skills\simulink-toolbox`
- `C:\Users\27443\.claude\skills\simulink-toolbox`
