# FACT: structured gate verdict computation from two probe snapshots.
# CLAIM: anything in README describing gate thresholds without referencing this module.
"""Structured gate evaluation for P2 cycle comparison.

Computes GATE-PHYS, GATE-G15, and GATE-WALL verdicts from two
``state_snapshot_*.json`` files and returns a machine-readable dict.

Typical usage::

    from probes.kundur.probe_state._gate_eval import evaluate_gates
    result = evaluate_gates("serial/state_snapshot_latest.json",
                            "parallel/state_snapshot_latest.json")
    print(result["overall_verdict"])   # "PASS" or "FAIL"

CLI usage::

    python -m probes.kundur.probe_state --gate-eval PREV CURR [--gate-eval-tol 1e-9]

Design notes:
- GATE-PHYS tolerance 1e-9 is the immutable acceptance contract for P2
  (engineering_philosophy §6 anti-goalpost rule).  Do not loosen it.
- GATE-WALL is purely informational; its verdict (PASS/FAIL/INFO) does NOT
  block overall_verdict.  Only GATE-PHYS + GATE-G15 determine overall_verdict.
- Schema version mismatch raises ValueError so callers can detect stale pairs.
- Wall time extraction tries (1) phase4_per_dispatch.wall_s, then (2)
  phase4_per_dispatch.parallel_metadata.worker_meta max(wall_s) as a
  fallback for parallel runs where the top-level field is unpopulated.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Literal, TypedDict

GateVerdict = Literal["PASS", "FAIL", "INFO"]

# ---------------------------------------------------------------------------
# TypedDicts for structured output
# ---------------------------------------------------------------------------


class GatePhysResult(TypedDict):
    verdict: GateVerdict          # PASS if all per-dispatch deltas <= tol
    tol: float                    # threshold used
    n_passed: int
    n_total: int
    max_delta: float              # max abs delta across all dispatches+fields
    per_dispatch: dict[str, dict]  # name -> {delta_global, delta_per_agent_max, delta_responding_count, max_field_delta}
    failures: list[str]           # dispatch names that failed (empty if PASS)


class GateG15Result(TypedDict):
    verdict: GateVerdict          # PASS if all G1-G5 verdicts match exactly
    per_gate: dict[str, dict]     # G1..G5 -> {prev_verdict, curr_verdict, match: bool}
    drift: list[str]              # gate IDs with mismatched verdicts
    note: str                     # one-line summary


class GateWallResult(TypedDict):
    verdict: GateVerdict          # PASS if speedup; INFO if no wall data
    prev_wall_s: float | None
    curr_wall_s: float | None
    speedup: float | None         # prev / curr
    threshold_ratio: float        # default 0.55
    note: str


class GateEvalResult(TypedDict):
    schema_version: int           # always 1
    prev_path: str
    curr_path: str
    overall_verdict: GateVerdict  # PASS if PHYS+G15 PASS (WALL is informational)
    gate_phys: GatePhysResult
    gate_g15: GateG15Result
    gate_wall: GateWallResult


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GATES_G1_TO_G5 = ("G1_signal", "G2_measurement", "G3_gradient", "G4_position", "G5_trace")
# G6_trained_policy is Phase 5/6 — out of scope for P2 gate comparison.

_DEFAULT_PHYS_TOL = 1e-9
_DEFAULT_WALL_THRESHOLD_RATIO = 0.55


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_gates(
    prev_path: Path | str,
    curr_path: Path | str,
    *,
    phys_tol: float = _DEFAULT_PHYS_TOL,
    wall_threshold_ratio: float = _DEFAULT_WALL_THRESHOLD_RATIO,
) -> GateEvalResult:
    """Compute structured gate verdicts from two probe snapshots.

    Args:
        prev_path: path to baseline snapshot JSON (e.g. serial run).
        curr_path: path to current snapshot JSON (e.g. parallel run).
        phys_tol: GATE-PHYS absolute tolerance. Default 1e-9 (engineering_philosophy
            §6 anti-goalpost; immutable acceptance contract for P2).
        wall_threshold_ratio: GATE-WALL fraction (curr_wall / prev_wall must be <=
            this for PASS). Default 0.55 = 1/4 + 0.3 overhead per P2 spec §5.

    Returns:
        GateEvalResult dict with overall_verdict + per-gate detail.

    Raises:
        FileNotFoundError: if either snapshot is missing.
        ValueError: if snapshots have incompatible schema_version.
    """
    prev_path = Path(prev_path).expanduser().resolve()
    curr_path = Path(curr_path).expanduser().resolve()

    if not prev_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {prev_path}")
    if not curr_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {curr_path}")

    prev = json.loads(prev_path.read_text(encoding="utf-8"))
    curr = json.loads(curr_path.read_text(encoding="utf-8"))

    # Schema version sanity check.
    prev_sv = prev.get("schema_version")
    curr_sv = curr.get("schema_version")
    if prev_sv != curr_sv:
        raise ValueError(
            f"Snapshot schema_version mismatch: prev={prev_sv!r}, curr={curr_sv!r}. "
            "Cannot compare snapshots with different schema versions."
        )

    gate_phys = _compute_gate_phys(prev, curr, phys_tol)
    gate_g15 = _compute_gate_g15(prev, curr)
    gate_wall = _compute_gate_wall(prev, curr, wall_threshold_ratio)

    # Overall: PASS only if PHYS and G15 both PASS.
    # WALL is purely informational.
    if gate_phys["verdict"] == "PASS" and gate_g15["verdict"] == "PASS":
        overall: GateVerdict = "PASS"
    else:
        overall = "FAIL"

    return GateEvalResult(
        schema_version=1,
        prev_path=str(prev_path),
        curr_path=str(curr_path),
        overall_verdict=overall,
        gate_phys=gate_phys,
        gate_g15=gate_g15,
        gate_wall=gate_wall,
    )


# ---------------------------------------------------------------------------
# GATE-PHYS
# ---------------------------------------------------------------------------


def _compute_gate_phys(prev: dict, curr: dict, tol: float) -> GatePhysResult:
    """Compute GATE-PHYS: per-dispatch numeric field agreement."""
    prev_dispatches: dict = (prev.get("phase4_per_dispatch") or {}).get("dispatches") or {}
    curr_dispatches: dict = (curr.get("phase4_per_dispatch") or {}).get("dispatches") or {}

    prev_names = set(prev_dispatches)
    curr_names = set(curr_dispatches)
    all_names = prev_names | curr_names

    per_dispatch: dict[str, dict] = {}
    failures: list[str] = []
    overall_max_delta = 0.0

    if prev_names != curr_names:
        # Mismatched dispatch sets — report missing ones as failures.
        for name in sorted(prev_names - curr_names):
            per_dispatch[name] = {
                "delta_global": None,
                "delta_per_agent_max": None,
                "delta_responding_count": None,
                "max_field_delta": float("inf"),
                "missing_in": "curr",
            }
            failures.append(f"{name}: missing in curr snapshot")
        for name in sorted(curr_names - prev_names):
            per_dispatch[name] = {
                "delta_global": None,
                "delta_per_agent_max": None,
                "delta_responding_count": None,
                "max_field_delta": float("inf"),
                "missing_in": "prev",
            }
            failures.append(f"{name}: missing in prev snapshot")

    # Evaluate dispatches present in both.
    common_names = sorted(prev_names & curr_names)
    n_passed = 0
    for name in common_names:
        p_d = prev_dispatches[name]
        c_d = curr_dispatches[name]

        # --- max_abs_f_dev_hz_global (scalar) ---
        delta_global = _abs_delta(p_d.get("max_abs_f_dev_hz_global"),
                                   c_d.get("max_abs_f_dev_hz_global"))

        # --- max_abs_f_dev_hz_per_agent (list) ---
        delta_per_agent_max = _list_max_abs_delta(
            p_d.get("max_abs_f_dev_hz_per_agent"),
            c_d.get("max_abs_f_dev_hz_per_agent"),
        )

        # --- agents_responding_above_1mHz (int, exact match required) ---
        p_count = p_d.get("agents_responding_above_1mHz")
        c_count = c_d.get("agents_responding_above_1mHz")
        if p_count is None and c_count is None:
            delta_responding = 0.0
        elif p_count is None or c_count is None:
            delta_responding = float("inf")
        elif p_count == c_count:
            delta_responding = 0.0
        else:
            # Exact match required — any mismatch is treated as infinite delta.
            delta_responding = float("inf")

        max_field_delta = _safe_max(delta_global, delta_per_agent_max, delta_responding)
        overall_max_delta = _safe_max(overall_max_delta, max_field_delta)

        dispatch_pass = _is_finite(max_field_delta) and max_field_delta <= tol

        per_dispatch[name] = {
            "delta_global": delta_global,
            "delta_per_agent_max": delta_per_agent_max,
            "delta_responding_count": delta_responding,
            "max_field_delta": max_field_delta,
        }

        if dispatch_pass:
            n_passed += 1
        else:
            failures.append(
                f"{name}: delta_global={delta_global:.3g}, "
                f"delta_per_agent_max={delta_per_agent_max:.3g}, "
                f"delta_responding={delta_responding:.3g}"
            )

    n_total = len(all_names)  # all unique dispatch names across both snapshots
    # Additional failures from missing dispatches already added above.
    n_passed_total = n_passed  # missing dispatches never PASS

    verdict: GateVerdict
    if prev_names != curr_names or n_passed < len(common_names):
        verdict = "FAIL"
    else:
        verdict = "PASS"

    # Clamp infinite to something JSON-serialisable.
    reported_max = overall_max_delta if _is_finite(overall_max_delta) else float("inf")

    return GatePhysResult(
        verdict=verdict,
        tol=tol,
        n_passed=n_passed_total,
        n_total=n_total,
        max_delta=reported_max,
        per_dispatch=per_dispatch,
        failures=failures,
    )


# ---------------------------------------------------------------------------
# GATE-G15
# ---------------------------------------------------------------------------


def _compute_gate_g15(prev: dict, curr: dict) -> GateG15Result:
    """Compute GATE-G15: G1-G5 verdict string consistency."""
    prev_gates: dict = prev.get("falsification_gates") or {}
    curr_gates: dict = curr.get("falsification_gates") or {}

    per_gate: dict[str, dict] = {}
    drift: list[str] = []

    for gate_id in _GATES_G1_TO_G5:
        prev_verdict = (prev_gates.get(gate_id) or {}).get("verdict", None)
        curr_verdict = (curr_gates.get(gate_id) or {}).get("verdict", None)
        match = prev_verdict == curr_verdict
        per_gate[gate_id] = {
            "prev_verdict": prev_verdict,
            "curr_verdict": curr_verdict,
            "match": match,
        }
        if not match:
            drift.append(gate_id)

    verdict: GateVerdict = "PASS" if not drift else "FAIL"

    # Build human-readable note.
    n_match = len(_GATES_G1_TO_G5) - len(drift)
    parts = []
    for gate_id, info in per_gate.items():
        short = gate_id.split("_")[0]  # G1, G2, ...
        v = info["curr_verdict"] or "?"
        parts.append(f"{short} {v}")
    note = f"{n_match}/{len(_GATES_G1_TO_G5)} match: {', '.join(parts)}"

    return GateG15Result(
        verdict=verdict,
        per_gate=per_gate,
        drift=drift,
        note=note,
    )


# ---------------------------------------------------------------------------
# GATE-WALL
# ---------------------------------------------------------------------------


def _compute_gate_wall(
    prev: dict,
    curr: dict,
    threshold_ratio: float,
) -> GateWallResult:
    """Compute GATE-WALL: parallel speedup gate (informational only)."""
    prev_wall = _extract_wall_s(prev)
    curr_wall = _extract_wall_s(curr)

    missing: list[str] = []
    if prev_wall is None:
        missing.append("prev")
    if curr_wall is None:
        missing.append("curr")

    if missing:
        note = f"wall data missing in {' and '.join(missing)} snapshot(s)"
        return GateWallResult(
            verdict="INFO",
            prev_wall_s=prev_wall,
            curr_wall_s=curr_wall,
            speedup=None,
            threshold_ratio=threshold_ratio,
            note=note,
        )

    speedup = prev_wall / curr_wall  # type: ignore[operator]
    curr_ratio = curr_wall / prev_wall  # type: ignore[operator]
    if curr_ratio <= threshold_ratio:
        verdict: GateVerdict = "PASS"
        note = (
            f"speedup={speedup:.2f}x "
            f"(curr={curr_wall:.1f}s, prev={prev_wall:.1f}s, "
            f"ratio={curr_ratio:.3f} <= {threshold_ratio})"
        )
    else:
        verdict = "FAIL"
        note = (
            f"speedup={speedup:.2f}x insufficient "
            f"(curr={curr_wall:.1f}s, prev={prev_wall:.1f}s, "
            f"ratio={curr_ratio:.3f} > {threshold_ratio})"
        )

    return GateWallResult(
        verdict=verdict,
        prev_wall_s=prev_wall,
        curr_wall_s=curr_wall,
        speedup=speedup,
        threshold_ratio=threshold_ratio,
        note=note,
    )


def _extract_wall_s(snapshot: dict) -> float | None:
    """Extract total wall time from a snapshot.

    Priority:
    1. phase4_per_dispatch.wall_s  (direct field, preferred)
    2. max(phase4_per_dispatch.parallel_metadata.worker_meta[*].wall_s)
       (fallback for parallel runs where top-level wall_s is unpopulated)
    """
    p4: dict = snapshot.get("phase4_per_dispatch") or {}

    # Primary: top-level wall_s.
    wall = p4.get("wall_s")
    if wall is not None:
        return float(wall)

    # Fallback: parallel_metadata.worker_meta max wall.
    pm: dict = p4.get("parallel_metadata") or {}
    worker_meta: list = pm.get("worker_meta") or []
    if worker_meta:
        walls = [w.get("wall_s") for w in worker_meta if w.get("wall_s") is not None]
        if walls:
            return float(max(walls))

    return None


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------


def _abs_delta(a: object, b: object) -> float:
    """Absolute delta between two scalars. Returns inf if either is None."""
    if a is None and b is None:
        return 0.0
    if a is None or b is None:
        return float("inf")
    try:
        return abs(float(a) - float(b))
    except (TypeError, ValueError):
        return float("inf")


def _list_max_abs_delta(a: object, b: object) -> float:
    """Element-wise max abs delta between two lists. Returns inf on mismatch."""
    if a is None and b is None:
        return 0.0
    if not isinstance(a, list) or not isinstance(b, list):
        if a is None and isinstance(b, list):
            return float("inf")
        if isinstance(a, list) and b is None:
            return float("inf")
        return float("inf")
    if len(a) != len(b):
        return float("inf")
    if not a:
        return 0.0
    return max(abs(float(x) - float(y)) for x, y in zip(a, b))


def _safe_max(*values: float) -> float:
    """Max of floats; inf propagates."""
    result = 0.0
    for v in values:
        if math.isinf(v):
            return float("inf")
        if v > result:
            result = v
    return result


def _is_finite(v: float) -> bool:
    return math.isfinite(v)
