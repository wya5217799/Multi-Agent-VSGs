"""Build artefact freshness check for the v3 Discrete model.

Used by Module β (``_ensure_build_current``) before forking parallel workers
to avoid race-on-rebuild when multiple matlab.engine instances each call
build_kundur_cvs_v3_discrete().

Pure-Python; no MATLAB import. Returns True iff the .slx is newer than all
its build-script dependencies.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


def is_build_current(slx_path: Path, deps: Iterable[Path]) -> bool:
    """Return True if slx exists and its mtime >= max mtime of deps.

    Args:
        slx_path: Path to the .slx file.
        deps: Iterable of dependency Paths (build script + helper + IC JSON
              + any other input files whose change should invalidate the build).

    Returns False if slx_path doesn't exist, or any dep is newer than slx.
    """
    slx_path = Path(slx_path)
    if not slx_path.exists():
        return False
    slx_mtime = slx_path.stat().st_mtime
    for d in deps:
        d = Path(d)
        if not d.exists():
            # Treat missing dep as a stale-build signal — better to rebuild
            # than silently use a model whose source is gone.
            return False
        if d.stat().st_mtime > slx_mtime:
            return False
    return True


def discrete_build_dependencies(repo_root: Path) -> list[Path]:
    """Return the canonical dep list for kundur_cvs_v3_discrete.slx."""
    base = Path(repo_root) / "scenarios" / "kundur"
    sim_models = base / "simulink_models"
    return [
        sim_models / "build_kundur_cvs_v3_discrete.m",
        sim_models / "build_dynamic_source_discrete.m",
        base / "kundur_ic_cvs_v3.json",
    ]
