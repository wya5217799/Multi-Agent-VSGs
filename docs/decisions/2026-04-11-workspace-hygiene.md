# 2026-04-11 Workspace Hygiene Decision

## Context

The project root has repeatedly accumulated local-only files: paper drafts,
reference folders, Python caches, Claude/Codex work directories, and legacy run
outputs. These files make the workspace harder to inspect and can be confused
with source changes.

The repository already uses `.gitignore`, but ignore rules only protect Git
history. They do not keep the local working tree visually clean.

## Decision

Adopt a lightweight workspace hygiene mechanism:

1. `tools/workspace_hygiene.toml` is the single rule source.
2. `tools/workspace_clean.py check` reports local pollution.
3. `tools/workspace_clean.py clean` dry-runs the move plan.
4. `tools/workspace_clean.py clean --apply` moves matched files to
   `C:\Users\27443\Desktop\一切\论文\Multi-Agent VSGs_cleanup_<timestamp>\`
   and writes `manifest.json`.
5. `tools/workspace_clean.py install-hook` may install a local pre-commit hook,
   but the hook only checks. It does not move files.

Tracked files must not be moved. If a movable directory contains a tracked file,
the directory is reported instead of moved.

## Scope

The mechanism targets local-only workspace pollution:

- personal/reference folders such as `论文/`, `其他/`, and `Figure.paper/`
- local drafts such as `paper_draft.tex`
- agent/worktree folders such as `.claude/` and `.worktrees/`
- Python caches
- legacy run output under `results/sim_kundur/` and `results/sim_ne39/`

It does not replace the harness fact path under `results/harness/`.

## Non-Goals

- no background cleaner
- no scheduled automatic move
- no pre-commit auto-move
- no broad restructuring of result output paths

## Rationale

This balances four constraints:

- low false-positive risk: dry-run is default and tracked files are guarded
- low interruption: cleanup is explicit
- recoverability: moved files are quarantined with a manifest
- maintainability: all hygiene rules live in one TOML file

## Follow-Up

If the rule set proves stable, a pre-commit hook can be installed locally with:

```powershell
python tools/workspace_clean.py install-hook
```

The hook should remain check-only.
