from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

HARNESS_ROOT = Path(__file__).resolve().parents[1] / "results" / "harness"

_VALID_SCENARIO = re.compile(r"^(kundur|ne39)$")
_VALID_RUN_ID = re.compile(r"^[\w\-]{1,64}$")


def _validate_path_inputs(scenario_id: str, run_id: str) -> None:
    if not _VALID_SCENARIO.match(scenario_id):
        raise ValueError(f"Invalid scenario_id: {scenario_id!r}")
    if not _VALID_RUN_ID.match(run_id):
        raise ValueError(f"Invalid run_id: {run_id!r}")


def ensure_run_dir(scenario_id: str, run_id: str) -> Path:
    _validate_path_inputs(scenario_id, run_id)
    run_dir = (HARNESS_ROOT / scenario_id / run_id).resolve()
    try:
        run_dir.relative_to(HARNESS_ROOT.resolve())
    except ValueError:
        raise ValueError(f"Resolved path escapes HARNESS_ROOT: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_manifest(
    run_dir: Path | str,
    *,
    run_id: str,
    scenario_id: str,
    goal: str,
    requested_tasks: list[str],
    created_at: str,
) -> Path:
    payload = {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "goal": goal,
        "requested_tasks": requested_tasks,
        "created_at": created_at,
    }
    return _write_json(Path(run_dir) / "manifest.json", payload)


def write_task_record(run_dir: Path | str, task_name: str, record: Mapping[str, Any]) -> Path:
    return _write_json(Path(run_dir) / f"{task_name}.json", dict(record))


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path
