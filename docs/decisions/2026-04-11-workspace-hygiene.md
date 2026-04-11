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
5. Local git hook orchestration is managed via `.pre-commit-config.yaml`,
   and the hygiene hook remains check-only. It does not move files.

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

## Hook Management

Hook orchestration is delegated to [pre-commit](https://pre-commit.com/).
The repo ships a `.pre-commit-config.yaml` that registers two hooks:

1. **workspace-hygiene** — runs `python tools/workspace_clean.py check`
   (check-only, never moves files)
2. **check-merge-conflict** — catches unresolved conflict markers

To activate locally after cloning:

```bash
pip install pre-commit   # one-time
pre-commit install       # registers the git hook
```

This is a local activation step, not a repo-internal state change.
The hand-written `install_pre_commit_hook()` function was removed to avoid
maintaining two hook installation paths.
