"""Worktree integrity guard.

Prevents silent cross-worktree contamination when this branch
(`discrete-rebuild`) shares helper module names with the main worktree
(`Multi-Agent  VSGs/` with double-space). If the wrong worktree wins the
sys.path race, imports may silently use stale code -> hard-to-trace bugs.

Python-side analog of the MATLAB-side assert at
scenarios/kundur/simulink_models/build_kundur_cvs_v3_discrete.m:61-79.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Final

EXPECTED_WORKTREE_BASENAME: Final[str] = "Multi-Agent-VSGs-discrete"
"""Discrete worktree dir name. Do not match by full absolute path because
operators may clone into different parent dirs."""

ENV_OVERRIDE: Final[str] = "MAVSGS_DISABLE_WORKTREE_ASSERT"
"""Set to '1' to bypass the assert (e.g. tests, alternative deployments).
Matches the MATLAB-side env var name in build_kundur_cvs_v3_discrete.m."""


class WrongWorktreeError(RuntimeError):
    """Raised when invoked from a worktree that doesn't match expectations."""


def assert_active_worktree(
    expected_basename: str = EXPECTED_WORKTREE_BASENAME,
    *,
    cwd: Path | None = None,
) -> None:
    """Hard-fail if cwd basename (or any parent dir basename) doesn't include
    expected_basename. Override via env var MAVSGS_DISABLE_WORKTREE_ASSERT=1.

    Args:
        expected_basename: substring to match against any path component.
        cwd: override for current dir (defaults to Path.cwd()).

    Raises:
        WrongWorktreeError: if no parent dir basename contains expected_basename
            and ENV_OVERRIDE is not set to '1'.
    """
    if os.environ.get(ENV_OVERRIDE) == "1":
        return

    cur = cwd or Path.cwd()
    # Walk up the chain checking dir names
    for component in [cur, *cur.parents]:
        if expected_basename in component.name:
            return

    raise WrongWorktreeError(
        f"path_guard: not in expected worktree.\n"
        f"  cwd: {cur}\n"
        f"  expected basename to contain: {expected_basename!r}\n"
        f"  override: set env var {ENV_OVERRIDE}=1 to bypass."
    )
