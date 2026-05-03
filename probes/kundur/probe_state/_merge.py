"""Module δ — snapshot merge for P2 parallel mode.

Combines N partial snapshots (one per worker) into a single canonical
snapshot whose schema is byte-compatible with serial mode (M5: schema_version
unchanged). Verdict recompute happens at the orchestrator level via
_verdict.compute_gates(merged) — δ does not invoke verdict.

Decision 4.3 (trust-worker-0): phases 2/3 come from worker 0; merge does
NOT cross-validate phase 1/2/3 across workers. Parent owns phase 1.

Decision 4.4 (centrally recomputed verdict): δ does NOT compute G1-G5;
the orchestrator runs _verdict.compute_gates(merged) AFTER merge.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MergeError(ValueError):
    """Raised when worker snapshots can't be merged consistently."""


def load_worker_snapshot(worker_dir: Path) -> dict[str, Any]:
    """Load state_snapshot_latest.json from a worker output dir."""
    p = Path(worker_dir) / "state_snapshot_latest.json"
    if not p.exists():
        raise MergeError(f"worker snapshot missing: {p}")
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def merge_snapshots(
    parent_partial: dict[str, Any],
    worker_snapshots: list[dict[str, Any]],
    worker_meta: list[dict[str, Any]],
    expected_dispatches_per_worker: list[list[str]],
) -> dict[str, Any]:
    """Merge N worker snapshots into a single canonical snapshot.

    Args:
        parent_partial: parent's snapshot dict; contains phase1_topology
            (run by parent), config, errors, schema_version, etc.
        worker_snapshots: list of N worker snapshot dicts in order [0..N-1].
            worker_snapshots[0] supplies phase2_nr_ic and phase3_open_loop.
            All N supply phase4_per_dispatch.dispatches.* fragments.
        worker_meta: list of N dicts {"idx": int, "exit_code": int,
            "wall_s": float, "subset": list[str], "worker_dir": str}.
        expected_dispatches_per_worker: the slice each worker was assigned
            (from slice_targets); used to detect dropped dispatches.

    Returns:
        Merged canonical snapshot with same schema as serial-mode output.

    Raises:
        MergeError on overlap (two workers claim same dispatch) — this is
        a programming bug (slicing should yield disjoint subsets).
    """
    if len(worker_snapshots) != len(worker_meta):
        raise MergeError(
            f"len(worker_snapshots)={len(worker_snapshots)} != "
            f"len(worker_meta)={len(worker_meta)}"
        )
    if len(worker_snapshots) == 0:
        raise MergeError("merge_snapshots called with zero workers")

    merged = dict(parent_partial)  # shallow; we'll deep-copy modifications below

    # ── Phases 2/3: trust worker 0 (Decision 4.3) ─────────────────────────
    w0 = worker_snapshots[0]
    if "phase2_nr_ic" in w0:
        merged["phase2_nr_ic"] = w0["phase2_nr_ic"]
    if "phase3_open_loop" in w0:
        merged["phase3_open_loop"] = w0["phase3_open_loop"]

    # ── Phase 4: combine all workers' dispatches (disjoint) ───────────────
    combined_dispatches: dict[str, Any] = {}
    skipped_unrecognised: list[str] = []
    metadata_warnings: list[str] = []
    probe_default_magnitude_sys_pu: float | None = None
    probe_default_sim_duration_s: float | None = None
    settle_window_s: float | None = None

    for w_idx, ws in enumerate(worker_snapshots):
        p4 = ws.get("phase4_per_dispatch", {})
        # First non-empty worker provides the parent-level defaults.
        if probe_default_magnitude_sys_pu is None:
            probe_default_magnitude_sys_pu = p4.get(
                "probe_default_magnitude_sys_pu"
            )
            probe_default_sim_duration_s = p4.get(
                "probe_default_sim_duration_s"
            )
            settle_window_s = p4.get("settle_window_s")
        # Collect dispatches.
        for d_name, d_data in p4.get("dispatches", {}).items():
            if d_name in combined_dispatches:
                raise MergeError(
                    f"dispatch {d_name!r} produced by multiple workers; "
                    f"slice_targets should yield disjoint subsets"
                )
            # Annotate with worker provenance for Y3 telemetry.
            d_data = dict(d_data)
            d_data["worker_id"] = w_idx
            combined_dispatches[d_name] = d_data
        # Collect skipped + warnings (deduplicate later).
        for s in p4.get("skipped_unrecognised", []):
            if s not in skipped_unrecognised:
                skipped_unrecognised.append(s)
        for w in p4.get("metadata_warnings", []):
            if w not in metadata_warnings:
                metadata_warnings.append(w)

    # ── Detect dropped dispatches (S6 graceful degradation) ───────────────
    expected_all = {
        d for slice_ in expected_dispatches_per_worker for d in slice_
    }
    actually_received = set(combined_dispatches.keys())
    dropped = sorted(expected_all - actually_received)
    if dropped:
        merged.setdefault("errors", []).append({
            "phase": "phase4_per_dispatch",
            "error": f"dispatches dropped by workers: {dropped}",
        })

    # ── Build merged phase4 dict ──────────────────────────────────────────
    phase4_merged: dict[str, Any] = {
        "probe_default_magnitude_sys_pu": probe_default_magnitude_sys_pu,
        "probe_default_sim_duration_s": probe_default_sim_duration_s,
        "settle_window_s": settle_window_s,
        "skipped_unrecognised": skipped_unrecognised,
        "dispatches": combined_dispatches,
        "metadata_warnings": metadata_warnings,
        "parallel_metadata": {
            "n_workers": len(worker_snapshots),
            "worker_subsets": list(expected_dispatches_per_worker),
            "worker_meta": list(worker_meta),
            "dropped_dispatches": dropped,
        },
    }
    merged["phase4_per_dispatch"] = phase4_merged

    # ── Surface worker exit codes / errors ────────────────────────────────
    nonzero = [
        m for m in worker_meta if m.get("exit_code", 0) != 0
    ]
    if nonzero:
        merged.setdefault("errors", []).append({
            "phase": "p2_workers",
            "error": (
                f"{len(nonzero)} worker(s) exited non-zero: "
                + "; ".join(
                    f"worker_{m['idx']}=exit_code={m['exit_code']}"
                    for m in nonzero
                )
            ),
        })

    # Forward any worker-side errors[] entries (deduplicate).
    seen = {(e.get("phase"), e.get("error")) for e in merged.get("errors", [])}
    for ws in worker_snapshots:
        for e in ws.get("errors", []):
            key = (e.get("phase"), e.get("error"))
            if key not in seen:
                merged.setdefault("errors", []).append(dict(e))
                seen.add(key)

    return merged
