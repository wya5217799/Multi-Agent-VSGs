"""Experiment metadata recording for training runs.

Writes a run_meta.json to the output directory at training start,
and allows appending fields (e.g., finished_at) at the end.

Usage in train_simulink.py:
    from utils.run_meta import save_run_meta, update_run_meta
    import config_simulink as cfg

    save_run_meta(args.checkpoint_dir, args, cfg)
    # ... training loop ...
    update_run_meta(args.checkpoint_dir, {"finished_at": datetime.now().isoformat(),
                                          "total_episodes": ep + 1})
"""
from __future__ import annotations

import datetime
import json
import math
import os
import subprocess
import tempfile
import types
from argparse import Namespace
from typing import Any


_SCALAR_TYPES = (int, float, str, bool)
_LIST_TYPES = (list, tuple)


def _git_hash(repo_dir: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_dir,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode().strip()
    except Exception:
        return "unknown"


def _git_dirty(repo_dir: str) -> bool:
    try:
        output = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode().strip()
        return bool(output)
    except Exception:
        return False


def _filter_config(module: types.ModuleType) -> dict[str, Any]:
    """Extract JSON-serialisable scalar fields, excluding private names."""
    result: dict[str, Any] = {}
    for key, val in vars(module).items():
        if key.startswith("_"):
            continue
        if isinstance(val, float) and not math.isfinite(val):
            continue
        if isinstance(val, _SCALAR_TYPES):
            result[key] = val
        elif isinstance(val, _LIST_TYPES):
            # Only include if all elements are finite scalars
            if all(
                isinstance(v, _SCALAR_TYPES)
                and not (isinstance(v, float) and not math.isfinite(v))
                for v in val
            ):
                result[key] = list(val)
    return result


def save_run_meta(
    output_dir: str,
    args: Namespace,
    config_module: types.ModuleType,
) -> None:
    """Write run_meta.json to output_dir at training start.

    Creates output_dir if it does not exist.
    On resume (run_meta.json already exists), preserves original metadata
    and adds a resumed_at timestamp instead of overwriting.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Resume path: preserve original metadata, just record resume time
    path = os.path.join(output_dir, "run_meta.json")
    if os.path.isfile(path):
        update_run_meta(output_dir, {"resumed_at": datetime.datetime.now().isoformat()})
        return

    # Fresh start
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    meta: dict[str, Any] = {
        "git_hash": _git_hash(repo_dir),
        "git_dirty": _git_dirty(repo_dir),
        "started_at": datetime.datetime.now().isoformat(),
        "args": vars(args),
        "config": _filter_config(config_module),
    }

    _write(output_dir, meta)


def update_run_meta(output_dir: str, updates: dict[str, Any]) -> None:
    """Merge updates into an existing run_meta.json.

    Raises FileNotFoundError if run_meta.json does not exist.
    """
    path = os.path.join(output_dir, "run_meta.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"run_meta.json not found in {output_dir}")
    with open(path, encoding="utf-8") as f:
        meta = json.load(f)
    meta.update(updates)
    _write(output_dir, meta)


def _write(output_dir: str, meta: dict[str, Any]) -> None:
    """Atomically write meta to run_meta.json via temp-file + rename."""
    path = os.path.join(output_dir, "run_meta.json")
    fd, tmp = tempfile.mkstemp(dir=output_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, default=str)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
