"""ArtifactWriter: lightweight structured output for training runs.

Writes three files to a log directory:
  metrics.jsonl     — one JSON line per episode (append)
  events.jsonl      — one JSON line per event: alerts, checkpoints (append)
  latest_state.json — current snapshot, overwritten atomically each update
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _NumpyEncoder(json.JSONEncoder):
    """Coerce numpy scalar types to Python builtins for JSON serialization."""

    def default(self, obj: Any) -> Any:
        try:
            import numpy as np
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
        except ImportError:
            pass
        return super().default(obj)


class ArtifactWriter:
    """Writes structured training artifacts to a log directory."""

    def __init__(self, log_dir: str | Path, reset_existing: bool = False) -> None:
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._metrics_path = self._dir / "metrics.jsonl"
        self._events_path = self._dir / "events.jsonl"
        self._state_path = self._dir / "latest_state.json"
        if reset_existing:
            for path in (self._metrics_path, self._events_path, self._state_path):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass

    def log_metric(self, episode: int, data: dict[str, Any]) -> None:
        """Append one episode's metrics to metrics.jsonl."""
        _RESERVED = {"episode", "ts"}
        if collisions := _RESERVED & data.keys():
            raise ValueError(f"data contains reserved keys: {collisions}")
        record = {"episode": episode, "ts": _now_iso(), **data}
        self._append_jsonl(self._metrics_path, record)

    def log_event(self, episode: int, event_type: str, data: dict[str, Any]) -> None:
        """Append one event (alert, checkpoint, stop) to events.jsonl."""
        _RESERVED = {"episode", "ts", "type"}
        if collisions := _RESERVED & data.keys():
            raise ValueError(f"data contains reserved keys: {collisions}")
        record = {"episode": episode, "ts": _now_iso(), "type": event_type, **data}
        self._append_jsonl(self._events_path, record)

    def update_state(self, data: dict[str, Any]) -> None:
        """Overwrite latest_state.json with the current snapshot.

        Uses tempfile + os.replace for crash-safety. On Windows, os.replace
        raises PermissionError if latest_state.json is concurrently open by
        another process. Safe for single-process training loops.
        """
        record = {"ts": _now_iso(), **data}
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self._dir, prefix=".state_", suffix=".json"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2, ensure_ascii=False, cls=_NumpyEncoder)
            os.replace(tmp_path, self._state_path)
        except OSError as e:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            import warnings
            warnings.warn(f"[ArtifactWriter] Failed to update state: {e}", stacklevel=2)

    @staticmethod
    def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, cls=_NumpyEncoder) + "\n")
        except OSError as e:
            import warnings
            warnings.warn(f"[ArtifactWriter] Failed to write {path.name}: {e}", stacklevel=3)
