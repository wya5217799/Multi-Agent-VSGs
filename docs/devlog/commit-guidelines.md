# Commit Guidelines

Use commits as triggers for the project memory system, not just as code snapshots.

The goal is simple:

- make the main intent of each change obvious
- make it easy to decide whether a devlog is needed
- make it easy to decide whether a decision record is needed
- keep commit history useful for later paper writing

## Core Rules

1. One commit should have one main intent.
2. Commit messages should say why the change matters, not only that files changed.
3. Important technical commits should trigger a devlog check.
4. Stable rule or contract changes should trigger a decision check.

## Recommended Prefixes

Use these lightweight prefixes:

- `fix:` for bug fixes and stability repairs
- `feat:` for new capabilities
- `docs:` for documentation, decisions, and paper-facing notes
- `refactor:` for internal restructuring without intended behavior change
- `chore:` for workflow or maintenance changes

## Good Examples

- `fix: stabilize kundur model_report aggregation`
- `fix: handle missing readback in model_patch_verify`
- `docs: define layered project memory system`
- `docs: record diagnose timeout root cause`
- `chore: add memory hints to model_report output`

## Avoid

- `update files`
- `misc fixes`
- `temp`
- `wip`
- `final changes`

These messages do not help the memory system decide what should be written down.

## When To Write A Devlog

Check for a devlog when the commit:

- is driven by a key harness run
- confirms a new root cause
- rules out an important wrong direction
- chooses one repair path over another
- may later matter for paper writing

Recommended metadata:

- `related_run_id`
- `related_commit`

## When To Write A Decision

Check for a decision record when the commit:

- changes a stable workflow rule
- changes a task or interface contract
- establishes a default repair or diagnose path
- changes a project rule that future agents should follow

## Minimal Commit Check

Before committing, ask:

1. Does this commit correspond to a specific run or technical judgment?
2. Does this commit change a rule that should be followed later?

If the answer to 1 is yes, consider a devlog.

If the answer to 2 is yes, consider a decision record.

## Relationship To Other Layers

- `results/harness/` records run facts
- `docs/devlog/` records important process reasoning
- `docs/decisions/` records stable rules
- `docs/paper/` records paper-facing summaries
- `MEMORY.md` links the important records

Commit history should help connect those layers rather than replace them.
