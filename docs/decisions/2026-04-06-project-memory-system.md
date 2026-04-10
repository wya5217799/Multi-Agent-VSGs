# 2026-04-06 Project Memory System

## Context

The repository already has a stable fact path:

- `AGENTS.md` defines where agents start
- `docs/harness/2026-04-05-simulink-harness-v1.md` defines harness task contracts
- `results/harness/` stores run evidence
- `MEMORY.md` exists as a lightweight navigation file

What is missing is a shared, repo-native way to preserve:

- development process notes
- stable project decisions
- paper-facing evidence trails

Without that layer, important reasoning stays in chat history or temporary context, which is hard to share across Claude and Codex and hard to reuse for paper writing.

## Decision

Adopt a lightweight layered project memory system as the primary project memory.

The layers are:

1. Fact layer: `results/harness/`
2. Process layer: `docs/devlog/`
3. Decision layer: `docs/decisions/`
4. Navigation layer: `MEMORY.md`
5. Paper layer: `docs/paper/`

Model-private memory and chat history are only auxiliary recall aids. The repository remains the source of truth.

## Layer Definitions

### Fact Layer

Path: `results/harness/`

Purpose:

- store run facts
- store task inputs and outputs
- store diagnose and smoke evidence
- store references to native artifacts

Boundary:

- describes what happened
- does not replace process notes or decisions

Primary keys:

- `run_id`
- `scenario_id`

### Process Layer

Path: `docs/devlog/`

Purpose:

- capture important debugging and upgrade notes
- record why an important commit was made
- preserve short reasoning trails that may matter later

Boundary:

- written only for important commits or key technical turning points
- should link to harness evidence instead of copying it

Primary keys:

- `note_id`
- `related_run_id`
- `related_commit`

### Decision Layer

Path: `docs/decisions/`

Purpose:

- capture stable project rules
- record interface, workflow, or architecture decisions
- define what should be followed in future work

Boundary:

- records final decisions, not long debugging narratives

Primary keys:

- `decision_id`
- `related_run_id`
- `related_note_id`
- `related_commit`

### Navigation Layer

Path: `MEMORY.md`

Purpose:

- index important runs, devlogs, decisions, and paper notes
- tell agents where to look next

Boundary:

- no long explanations
- no duplicated document bodies

### Paper Layer

Path: `docs/paper/`

Purpose:

- extract paper-relevant material from the other layers
- keep method evolution and experiment evidence easy to find

Boundary:

- not a replacement for devlogs or decisions
- only stores curated summaries and links

## Write Rules

Use these minimum rules:

1. Every important harness run must have a `run_id`.
2. Every important commit with meaningful technical reasoning should have a devlog.
3. Every stable rule should have a decision record.
4. Every devlog or decision should link to evidence through `related_run_id`, `related_commit`, or both.
5. `MEMORY.md` stays an index only.

## Trigger Rules

Write a devlog when:

- a run identifies a new root cause
- an important commit captures a non-trivial judgment
- a debugging path rules out an important wrong direction
- the process may later matter for paper writing

Write a decision when:

- a workflow rule should become default
- an interface or task contract becomes stable
- a diagnostic or patch path should be treated as the standard approach

Update `MEMORY.md` when:

- a key run lands
- a devlog is added
- a decision is added
- a paper-facing note is added

## Harness Integration

Harness remains the fact layer. It should not absorb the full project memory role.

Harness should, however, remind agents when a process or decision document is needed.

The preferred reminder point is `model_report`, which may include a compact hint such as:

```json
{
  "memory_hints": {
    "should_write_devlog": true,
    "should_write_decision": false,
    "reason": [
      "new_root_cause_identified",
      "important_commit_expected"
    ]
  }
}
```

Important commits should also trigger a lightweight reminder to add a devlog or decision when needed.

These reminders are guidance, not hard blocking checks.

## Consequences

Future work should follow this order:

1. Harness writes facts.
2. Important commits write devlogs.
3. Stable rules write decisions.
4. `MEMORY.md` links the important records.
5. `docs/paper/` extracts paper-facing material as needed.

This keeps the memory system shared, auditable, lightweight, and usable for both development continuity and paper writing.
