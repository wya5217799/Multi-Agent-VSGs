# 2026-04-24 Simulink Toolbox Single-Source Layout

## Status

Adopted.

## Context

The installed `simulink-toolbox` skill is currently duplicated under both
`~/.codex/skills/` and `~/.claude/skills/`. This causes content drift, hook
drift, and repeated manual edits.

The same skill also mixes three concerns:

- generic Simulink routing
- platform-specific hook implementation
- Yang/VSG/Kundur/NE39 project routing

## Decision

Use one canonical installed skill directory:

- `C:\Users\27443\.shared-skills\simulink-toolbox`

Use directory junctions for:

- `C:\Users\27443\.codex\skills\simulink-toolbox`
- `C:\Users\27443\.claude\skills\simulink-toolbox`

Keep generic Simulink content in the shared installed skill.

Move project/model-specific routing to:

- `docs/agent_layer/simulink-project-routing/`
- `docs/agent_layer/simulink-project-routing/models/`

## Consequences

- Future edits happen in one place only.
- Platform-specific hooks remain supported via subfolders under one shared tree.
- Generic skill validation and project overlay validation become separable.
