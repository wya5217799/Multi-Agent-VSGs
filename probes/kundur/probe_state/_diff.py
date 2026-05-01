# FACT: this module's diff output (printed to stdout) is the contract.
# Anything in README about diff format is CLAIM until verified against
# the actual stdout text emitted here.
"""Snapshot diff — F2 (design §5.6).

Field-level deep-diff between two ``state_snapshot_*.json`` files.
Used for regression check after build / schema / dispatch changes:
"this snapshot vs the last green baseline — what changed?".

CLI usage::

    python -m probes.kundur.probe_state --diff prev.json curr.json

Output: human-readable summary of changed scalar fields, added/removed
keys, and verdict transitions (G1..G6 PASS↔REJECT↔PENDING). Numeric
fields show absolute + relative delta when both sides are numbers.

Out of scope:
- Diffing entire `omega_trace_summary` arrays (too noisy)
- Auto-marshalling between schema versions (F5 migration is separate)
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

# Keys whose values are large arrays / cells that we summarise rather than
# diff field-by-field. Added rolling as new noisy fields surface.
_SUMMARISE_KEYS = frozenset({
    "omega_trace_summary_per_agent",
    "per_episode_metrics",
    "results",
    "checkpoints",
})


def diff_snapshots(prev_path: Path, curr_path: Path) -> int:
    """Print field-level diff. Returns shell exit code (0 = no diffs)."""
    prev = json.loads(prev_path.read_text(encoding="utf-8"))
    curr = json.loads(curr_path.read_text(encoding="utf-8"))

    print(f"--- prev: {prev_path}")
    print(f"+++ curr: {curr_path}")
    _print_versions(prev, curr)
    print()

    changes = _walk(prev, curr, path="")
    if not changes:
        print("(no field-level changes)")
        return 0

    # Group by section for readability.
    grouped: dict[str, list[str]] = {}
    for path, msg in changes:
        section = path.split(".", 1)[0] if "." in path else path
        grouped.setdefault(section, []).append(f"  {path}: {msg}")

    for section in sorted(grouped):
        print(f"[{section}]")
        for line in grouped[section]:
            print(line)
        print()

    print(f"total changes: {len(changes)}")
    return 1


def _print_versions(prev: dict, curr: dict) -> None:
    """Surface schema_version + implementation_version up front (F5)."""
    p_s = prev.get("schema_version")
    c_s = curr.get("schema_version")
    p_i = prev.get("implementation_version")
    c_i = curr.get("implementation_version")
    # ASCII-only output: Windows GBK consoles cannot encode emoji / arrows,
    # and pipes / log files are safer with plain ASCII.
    print(f"schema_version: {p_s} -> {c_s}")
    print(f"implementation_version: {p_i} -> {c_i}")
    if p_s != c_s:
        print("  [WARN] schema bump - diff may not be field-comparable")
    if p_i != c_i:
        print("  [WARN] implementation bump - verdict semantics may differ; see CHANGELOG")


def _walk(prev: Any, curr: Any, *, path: str) -> list[tuple[str, str]]:
    """Recursively collect (path, message) tuples for changed leaves."""
    changes: list[tuple[str, str]] = []

    if isinstance(prev, dict) and isinstance(curr, dict):
        keys_p = set(prev)
        keys_c = set(curr)
        for k in sorted(keys_p - keys_c):
            changes.append((_join(path, k), "REMOVED"))
        for k in sorted(keys_c - keys_p):
            changes.append((_join(path, k), f"ADDED = {_summarise(curr[k])}"))
        for k in sorted(keys_p & keys_c):
            sub = _join(path, k)
            if k in _SUMMARISE_KEYS:
                # Summarise length + first-element gist instead of deep-diff.
                p_sum = _summarise(prev[k])
                c_sum = _summarise(curr[k])
                if p_sum != c_sum:
                    changes.append((sub, f"{p_sum} -> {c_sum} (summarised)"))
                continue
            changes.extend(_walk(prev[k], curr[k], path=sub))
    elif isinstance(prev, list) and isinstance(curr, list):
        if len(prev) != len(curr):
            changes.append(
                (path, f"list length {len(prev)} → {len(curr)}")
            )
        for i, (p, c) in enumerate(zip(prev, curr)):
            changes.extend(_walk(p, c, path=_join(path, f"[{i}]")))
    else:
        if not _equal(prev, curr):
            changes.append((path, _format_scalar_diff(prev, curr)))

    return changes


def _equal(a: Any, b: Any) -> bool:
    """Float-tolerant equality (NaN-safe)."""
    if isinstance(a, float) or isinstance(b, float):
        if a is None or b is None:
            return a is b
        try:
            af, bf = float(a), float(b)
        except (TypeError, ValueError):
            return a == b
        if math.isnan(af) and math.isnan(bf):
            return True
        return af == bf
    return a == b


def _format_scalar_diff(prev: Any, curr: Any) -> str:
    if isinstance(prev, (int, float)) and isinstance(curr, (int, float)):
        delta = float(curr) - float(prev)
        if abs(prev) > 0:
            rel = delta / abs(float(prev)) * 100
            return f"{prev} -> {curr}  (delta={delta:+.4g}, {rel:+.2f}%)"
        return f"{prev} -> {curr}  (delta={delta:+.4g})"
    return f"{prev!r} -> {curr!r}"


def _summarise(v: Any) -> str:
    if isinstance(v, list):
        return f"<list len={len(v)}>"
    if isinstance(v, dict):
        return f"<dict keys={len(v)}>"
    if isinstance(v, str) and len(v) > 60:
        return f"<str len={len(v)}: {v[:30]!r}...>"
    return repr(v)


def _join(path: str, key: str) -> str:
    if not path:
        return key
    if key.startswith("["):
        return f"{path}{key}"
    return f"{path}.{key}"
