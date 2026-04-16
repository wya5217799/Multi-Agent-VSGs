# engine/optimization_log.py
"""Append-only optimization memory layer for RL training decisions.

Storage: scenarios/contracts/optimization_log_{scenario}.jsonl
One file per scenario (kundur | ne39), append-only JSONL.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONTRACTS_DIR = _REPO_ROOT / "scenarios" / "contracts"

_VALID_SCENARIOS = {"kundur", "ne39"}
_SCENARIO_PREFIX = {"kundur": "kd", "ne39": "ne"}
_VALID_VERDICTS = {"effective", "ineffective", "inconclusive", "harmful"}
_OPT_REQUIRED = {"scenario", "scope", "status", "problem", "hypothesis", "changes"}


def _log_path(scenario: str) -> Path:
    return _CONTRACTS_DIR / f"optimization_log_{scenario}.jsonl"


def load_log(scenario: str) -> list[dict[str, Any]]:
    """Read all optimization records for a scenario in time order.

    Returns empty list if the file does not exist.
    Skips blank lines and JSON-decode failures silently.
    """
    path = _log_path(scenario)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return records


def _next_opt_id(scenario: str, today_str: str) -> str:
    """Generate next opt_id for today by scanning existing records."""
    prefix = _SCENARIO_PREFIX[scenario]
    existing = load_log(scenario)
    max_seq = 0
    for r in existing:
        oid = r.get("opt_id", "")
        # format: opt_{prefix}_{YYYYMMDD}_{seq}
        parts = oid.split("_")
        if len(parts) == 4 and parts[0] == "opt" and parts[1] == prefix and parts[2] == today_str:
            try:
                max_seq = max(max_seq, int(parts[3]))
            except ValueError:
                pass
    seq = max_seq + 1
    return f"opt_{prefix}_{today_str}_{seq:02d}"


def append_optimization(scenario: str, record: dict[str, Any]) -> str:
    """Append an optimization record. Returns the generated opt_id.

    Auto-fills: type, ts, opt_id.
    Validates: scenario is valid, all required fields are present.
    record must NOT include type/ts/opt_id — they are overwritten.
    """
    if scenario not in _VALID_SCENARIOS:
        raise ValueError(f"scenario must be one of {_VALID_SCENARIOS}, got {scenario!r}")
    missing = _OPT_REQUIRED - set(record.keys())
    if missing:
        raise ValueError(f"Missing required fields: {sorted(missing)}")

    now = datetime.now(tz=timezone.utc).astimezone()
    today_str = now.strftime("%Y%m%d")
    opt_id = _next_opt_id(scenario, today_str)
    ts = now.isoformat()

    row = {
        "type": "optimization",
        "opt_id": opt_id,
        "ts": ts,
        **{k: v for k, v in record.items() if k not in ("type", "ts", "opt_id")},
    }

    path = _log_path(scenario)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return opt_id


def append_outcome(
    scenario: str,
    opt_id: str,
    verdict: str,
    summary: str,
    **kwargs: Any,
) -> None:
    """Append an outcome record linked to opt_id.

    Auto-fills: type, ts.
    Validates: opt_id exists in log, verdict is valid.
    kwargs: result_run, transferable, transfer_notes, confidence.
    """
    if verdict not in _VALID_VERDICTS:
        raise ValueError(f"verdict must be one of {_VALID_VERDICTS}, got {verdict!r}")

    existing = load_log(scenario)
    known_ids = {r["opt_id"] for r in existing if r.get("type") == "optimization"}
    if opt_id not in known_ids:
        raise ValueError(f"opt_id {opt_id!r} not found in {scenario} log")

    ts = datetime.now(tz=timezone.utc).astimezone().isoformat()
    row: dict[str, Any] = {
        "type": "outcome",
        "opt_id": opt_id,
        "ts": ts,
        "verdict": verdict,
        "summary": summary,
    }
    allowed_kwargs = {"result_run", "transferable", "transfer_notes", "confidence"}
    for k, v in kwargs.items():
        if k in allowed_kwargs:
            row[k] = v

    path = _log_path(scenario)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _build_opt_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a merged summary dict for injection into training_diagnose output."""
    optimizations = [r for r in records if r.get("type") == "optimization"]
    outcomes: dict[str, dict[str, Any]] = {}
    for r in records:
        if r.get("type") == "outcome":
            outcomes[r["opt_id"]] = r  # later record overwrites earlier

    merged = []
    for opt in optimizations:
        entry = dict(opt)
        if opt["opt_id"] in outcomes:
            entry["outcome"] = outcomes[opt["opt_id"]]
        merged.append(entry)

    verdict_counts: dict[str, int] = {}
    for o in outcomes.values():
        v = o.get("verdict", "unknown")
        verdict_counts[v] = verdict_counts.get(v, 0) + 1

    return {
        "total": len(optimizations),
        "with_outcome": len(outcomes),
        "by_verdict": verdict_counts,
        "records": merged,
    }
