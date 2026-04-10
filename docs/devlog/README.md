# Devlog Notes

This directory stores short process notes for important technical changes.

See also: `docs/devlog/commit-guidelines.md` for the lightweight commit rules that trigger devlogs and decision checks.

Use a devlog when:

- a harness run identifies a new root cause
- an important commit captures a non-trivial technical judgment
- a debugging path rules out an important wrong direction
- the process may later matter for paper writing

Do not use a devlog to duplicate harness JSON outputs. Link the relevant run and summarize only the reasoning and outcome.

## Naming

- File name: `YYYY-MM-DD-<topic>.md`
- `note_id`: `devlog-YYYY-MM-DD-<topic>`

## Required Metadata

```md
---
note_id: devlog-2026-04-06-<topic>
scenario_id: kundur
related_run_id: 20260406-140000-kundur-<goal>
related_commit: <git-sha-or-branch>
status: closed
tags: [harness, debug]
---
```

## Template

```md
---
note_id: devlog-2026-04-06-<topic>
scenario_id: kundur
related_run_id: 20260406-140000-kundur-<goal>
related_commit: <git-sha-or-branch>
status: closed
tags: [harness, debug]
---

# Context

What this change was trying to solve.

# Evidence

- Harness run: `results/harness/kundur/20260406-140000-kundur-<goal>/`
- Key symptom:
- Key diagnostic result:

# What Changed

- Main code or workflow change
- Why this path was chosen

# Outcome

- What improved or failed
- Any remaining issue

# Next

- Next step or `none`
```
