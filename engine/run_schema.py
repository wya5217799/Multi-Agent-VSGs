"""engine/run_schema.py — Typed view of training_status.json.

Why this module exists:
  Both the Launcher (engine/training_launch.py) and the Observer
  (engine/training_tasks.py::training_status) read the same
  training_status.json contract.  Before this module they each called
  `.get("field")` on a raw dict — implicit and silently breakable when
  writers (training scripts) renamed/dropped a field.

Responsibility split:
  utils/run_protocol.py
      File I/O + run-directory layout (atomic write, mtime resolution).
  engine/run_schema.py            ◄── this module
      Typed view (RunStatus dataclass) + uniform reader.
      All process-external consumers go through read_run_status().

See docs/knowledge/training_management.md for the field contract and
the four-role layering (Launcher / Monitor / Observer / Evaluator).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from utils.run_protocol import read_training_status


@dataclass(frozen=True)
class RunStatus:
    """Typed view of training_status.json.

    Every field maps 1:1 to a key written by
    utils/run_protocol.py::write_training_status.

    Optional fields default to None so callers can treat absence and
    null uniformly.  raw is the source dict, kept for forward-compat
    with newly-added fields not yet promoted to typed attributes.
    """

    run_id: str | None = None
    status: str | None = None  # "running" | "finished" | "failed"
    episodes_done: int = 0
    episodes_total: int = 0
    last_reward: float | None = None
    last_eval_reward: float | None = None
    last_updated: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    failed_at: str | None = None
    error: str | None = None
    stop_reason: str | None = None
    logs_dir: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def progress_pct(self) -> float:
        """Episodes_done / episodes_total * 100 (0.0 if total == 0)."""
        if self.episodes_total <= 0:
            return 0.0
        return self.episodes_done / self.episodes_total * 100

    def logs_path(self, run_dir: Path) -> Path:
        """Return logs directory: status.logs_dir if set, else run_dir/logs."""
        return Path(self.logs_dir) if self.logs_dir else (run_dir / "logs")

    def to_observer_dict(
        self,
        run_dir: Path,
        scenario_id: str,
        latest_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Render the MCP Observer-shape dict.

        Centralises the field mapping previously duplicated in
        engine/training_tasks.py::training_status. Adding a field to
        RunStatus AND wanting it surfaced to MCP callers is now a single
        edit here.

        Output shape is locked by tests/test_training_tasks.py — do not
        rename or drop keys without updating that contract.
        """
        return {
            "scenario_id": scenario_id,
            "run_id": self.run_id,
            "status": self.status,
            "episodes_done": self.episodes_done,
            "episodes_total": self.episodes_total,
            "progress_pct": round(self.progress_pct, 2),
            "last_reward": self.last_reward,
            "last_updated": self.last_updated,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "stop_reason": self.stop_reason,
            "last_eval_reward": self.last_eval_reward,
            "logs_dir": str(self.logs_path(run_dir)),
            "run_dir": str(run_dir),
            "latest_snapshot": latest_snapshot,
        }


def read_run_status(run_dir: Path) -> RunStatus | None:
    """Read training_status.json under run_dir, return typed view or None.

    None is returned when the file does not exist.  Field type coercion
    is best-effort: malformed entries fall back to None / 0 rather than
    raising, matching the existing dict-based call sites' tolerance.
    """
    raw = read_training_status(run_dir)
    if raw is None:
        return None
    return _coerce_run_status(raw)


def _coerce_run_status(raw: dict[str, Any]) -> RunStatus:
    """Coerce a raw dict into RunStatus with tolerant typing."""
    return RunStatus(
        run_id=_as_str(raw.get("run_id")),
        status=_as_str(raw.get("status")),
        episodes_done=_as_int(raw.get("episodes_done"), default=0),
        episodes_total=_as_int(raw.get("episodes_total"), default=0),
        last_reward=_as_float(raw.get("last_reward")),
        last_eval_reward=_as_float(raw.get("last_eval_reward")),
        last_updated=_as_str(raw.get("last_updated")),
        started_at=_as_str(raw.get("started_at")),
        finished_at=_as_str(raw.get("finished_at")),
        failed_at=_as_str(raw.get("failed_at")),
        error=_as_str(raw.get("error")),
        stop_reason=_as_str(raw.get("stop_reason")),
        logs_dir=_as_str(raw.get("logs_dir")),
        raw=dict(raw),
    )


def list_episode_checkpoints(run_dir: Path) -> list[Path]:
    """Return episode checkpoint paths sorted by episode number.

    Replaces the ad-hoc walks previously inlined in training_launch.py
    and (test-only) _inspect_latest_run.  Only files matching the
    epNNN.pt pattern are returned; final.pt is intentionally excluded —
    callers can probe it explicitly.
    """
    ckpt_dir = run_dir / "checkpoints"
    if not ckpt_dir.is_dir():
        return []

    def _ep_num(p: Path) -> int:
        try:
            return int(p.stem[2:])
        except (ValueError, IndexError):
            return -1

    candidates = [
        f for f in ckpt_dir.iterdir()
        if f.is_file() and f.name.startswith("ep") and f.name.endswith(".pt")
    ]
    candidates.sort(key=_ep_num)
    return candidates


def latest_resume_candidate(run_dir: Path) -> Path | None:
    """Return the highest-numbered ep*.pt, falling back to final.pt, else None."""
    eps = list_episode_checkpoints(run_dir)
    if eps:
        return eps[-1]
    final = run_dir / "checkpoints" / "final.pt"
    return final if final.exists() else None


# ── coercion helpers ─────────────────────────────────────────────────────────

def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
