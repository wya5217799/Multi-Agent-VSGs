"""state.json schema 检查 (硬契约).

Daemon + AI 每写 state.json 前调 check_state_dict(state). schema 见
quality_reports/specs/2026-05-07_research_loop_design.md §4.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SUPPORTED_VERSIONS = {"1.0"}

REQUIRED_TOP = {
    "version", "round_idx", "started_at_utc",
    "budget", "ram", "gates", "stagnation",
    "pending", "running", "done", "killed",
    "ai_session_log", "handoff_pointers",
}
REQUIRED_BUDGET = {
    "rounds_used", "rounds_cap",
    "wall_hr_used", "wall_hr_cap",
    "tokens_used", "tokens_cap",
}
REQUIRED_RAM = {"free_gb_min_hard", "per_run_estimate_gb"}
REQUIRED_GATES = {"G1", "G2", "G3", "G4", "G5", "G6"}
REQUIRED_STAGN = {"last_3_overall", "delta_pct"}


class StateSchemaError(ValueError):
    pass


def check_state_dict(state: dict) -> None:
    """Raise StateSchemaError on schema violation. Return None on legal."""
    if not isinstance(state, dict):
        raise StateSchemaError("state must be dict")

    version = state.get("version")
    if version not in SUPPORTED_VERSIONS:
        raise StateSchemaError(
            f"version {version!r} not in SUPPORTED_VERSIONS={SUPPORTED_VERSIONS}"
        )

    missing_top = REQUIRED_TOP - set(state.keys())
    if missing_top:
        raise StateSchemaError(f"missing top-level keys: {sorted(missing_top)}")

    for sub_key, required in [
        ("budget", REQUIRED_BUDGET),
        ("ram", REQUIRED_RAM),
        ("gates", REQUIRED_GATES),
        ("stagnation", REQUIRED_STAGN),
    ]:
        sub = state[sub_key]
        if not isinstance(sub, dict):
            raise StateSchemaError(f"{sub_key} must be dict")
        missing = required - set(sub.keys())
        if missing:
            raise StateSchemaError(f"{sub_key} missing: {sorted(missing)}")

    for list_key in ["pending", "running", "done", "killed",
                     "ai_session_log", "handoff_pointers"]:
        if not isinstance(state[list_key], list):
            raise StateSchemaError(f"{list_key} must be list")


def check_state_file(path: str | Path) -> None:
    """Read JSON file and check schema.

    `path` 可为 str 或 Path; resolve 后打开 (防 relative-path 歧义).
    """
    resolved = Path(path).resolve()
    with open(resolved, encoding="utf-8") as f:
        state = json.load(f)
    check_state_dict(state)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: check_state.py <state.json>", file=sys.stderr)
        sys.exit(2)
    try:
        check_state_file(sys.argv[1])
        print("OK")
    except StateSchemaError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
