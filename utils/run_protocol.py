"""utils/run_protocol.py — Per-run training directory and status protocol.

Defines:
  - generate_run_id(scenario)  → "kundur_20260410_120305"
  - get_run_dir(scenario, run_id) → Path to run output directory
  - ensure_run_dir(scenario, run_id) → creates and returns run_dir
  - write_training_status(run_dir, status) → atomic JSON write
  - read_training_status(run_dir) → dict | None

Output layout:
    results/sim_{scenario}/runs/{run_id}/
        training_status.json   ← atomic-written; polled by sidecar
        run_meta.json          ← written once at training start
        metrics.jsonl          ← appended per episode
        events.jsonl           ← appended per event
        verdict.json           ← written at training end
        checkpoints/           ← model files

This layout intentionally separates native training outputs from
results/harness/ (the modeling quality-gate fact layer).
See docs/decisions/2026-04-09-harness-boundary-convention.md.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Guard uniqueness across rapid successive calls within the same second.
_run_id_lock = threading.Lock()
_last_run_ts: datetime | None = None


def generate_run_id(scenario: str) -> str:
    """Return a unique run identifier: '{scenario}_{YYYYMMDD}_{HHMMSS}'.

    Example: 'kundur_20260410_143022'

    Uniqueness is guaranteed even when called multiple times within a single
    second by advancing the timestamp by one second on each collision.
    """
    global _last_run_ts
    with _run_id_lock:
        now = datetime.now().replace(microsecond=0)
        if _last_run_ts is not None and now <= _last_run_ts:
            now = _last_run_ts + timedelta(seconds=1)
        _last_run_ts = now
    ts = now.strftime("%Y%m%d_%H%M%S")
    return f"{scenario}_{ts}"


def get_run_dir(scenario: str, run_id: str) -> Path:
    """Return the run output directory path (does NOT create it)."""
    return _PROJECT_ROOT / "results" / f"sim_{scenario}" / "runs" / run_id


def ensure_run_dir(scenario: str, run_id: str) -> Path:
    """Create run directory (and subdirs) and return the path."""
    run_dir = get_run_dir(scenario, run_id)
    (run_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    return run_dir


def write_training_status(run_dir: Path, status: dict[str, Any]) -> None:
    """Atomically write training_status.json to run_dir.

    Uses tempfile + os.replace so readers never see a partial write.
    """
    target = run_dir / "training_status.json"
    fd, tmp_path = tempfile.mkstemp(dir=run_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(status, f)
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_training_status(run_dir: Path) -> dict[str, Any] | None:
    """Read training_status.json, returning None if file does not exist."""
    path = run_dir / "training_status.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
