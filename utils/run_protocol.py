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

Current Simulink training writes metrics/events/training_log.json under the
run's logs/ subdirectory and keeps checkpoint files under checkpoints/.

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
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    return run_dir


def infer_run_dir_from_output_paths(
    checkpoint_dir: str | os.PathLike[str],
    log_file: str | os.PathLike[str],
) -> Path | None:
    """Infer a run root from '<root>/checkpoints' and '<root>/logs/training_log.json'.

    Explicit callers such as harness smoke pass checkpoint and log paths instead
    of a run_dir. When they use the standard run layout, metadata and status
    files should stay under that same root.
    """
    checkpoint_path = Path(checkpoint_dir)
    log_path = Path(log_file)
    if (
        checkpoint_path.name == "checkpoints"
        and log_path.name == "training_log.json"
        and log_path.parent.name == "logs"
        and checkpoint_path.parent == log_path.parent.parent
    ):
        return checkpoint_path.parent
    return None


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


def find_latest_run(scenario_id: str) -> Path | None:
    """Return the active or most-recently-updated run_dir, or None.

    Resolution priority (do NOT use raw mtime):
    1. Exactly one run with status "running" → return it.
    2. Multiple "running" runs → return the one with the most recent last_updated.
    3. No running runs → return the run with the most recent finished_at / failed_at.
    4. No runs at all → return None.
    """
    runs_dir = _PROJECT_ROOT / "results" / f"sim_{scenario_id}" / "runs"
    if not runs_dir.exists():
        return None

    candidates: list[tuple[Path, dict]] = []
    for entry in runs_dir.iterdir():
        if not entry.is_dir():
            continue
        status = read_training_status(entry)
        if status is not None:
            candidates.append((entry, status))

    if not candidates:
        return None

    def _terminal_ts(item: tuple[Path, dict]) -> str:
        s = item[1]
        return s.get("finished_at") or s.get("failed_at") or ""

    running = [(d, s) for d, s in candidates if s.get("status") == "running"]
    terminal = [(d, s) for d, s in candidates if s.get("status") != "running"]

    if running:
        best_running = max(running, key=lambda item: item[1].get("last_updated") or "")
        best_running_ts = best_running[1].get("last_updated") or ""

        # Ghost-run guard: if a completed/failed run has a terminal timestamp
        # *after* the best running heartbeat, the running status is stale (process
        # died without writing a final status).  Prefer the terminal run instead.
        if terminal:
            best_terminal = max(terminal, key=_terminal_ts)
            if _terminal_ts(best_terminal) > best_running_ts:
                return best_terminal[0]

        return best_running[0]

    # No running runs: use finished_at or failed_at timestamp from file content.
    # Runs that lack both timestamps (e.g. crashed before writing them) return ""
    # and sort last — the most-recently-terminated run wins, which is the desired
    # behaviour: a clean finish beats an incomplete/crashed run of similar vintage.
    if not terminal:
        return None
    return max(terminal, key=_terminal_ts)[0]
