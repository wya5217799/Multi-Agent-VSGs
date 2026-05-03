<!--
USAGE:
  - Copy to quality_reports/plans/YYYY-MM-DD_<short-name>.md before starting.
  - Use for 1-3 hr cross-file tasks. For >3 hr / paper-anchor / multi-phase work,
    use the fuller spec template at quality_reports/specs/ instead.
  - Status keyword on line 1 enables: grep "^\*\*Status\*\*" quality_reports/plans/*.md
-->

# Plan: P0-3 — Gate eval auto module (pure Python)

**Status**: DONE
**Estimated**: 1 hr | **Actual**: 0.5 hr
**Trigger**: Retro §3.5.2 — P0-1 gate verdicts computed via 30-line inline script; ≥8 reuses planned for Phase 1.5 and beyond. Need structured, testable module.
**Supersedes**: none

## §1 Acceptance Gates (PRE-REGISTERED, IMMUTABLE)

| ID | Threshold | Measurement | Verdict |
|---|---|---|---|
| G1 | 22/23 tests pass (1 skip allowed) | `pytest tests/test_gate_eval.py -x -v` | PASS |
| G2 | Smoke run on P0-1 snapshots returns `"overall_verdict": "PASS"` with `n_passed=15`, `max_delta=0.0`, exit code 0 | CLI invocation | PASS |

## §2 TodoWrite Mapping (1:1)

skip — single-cycle agent task

## §3 Steps (atomic, file-level)

1. New module
   - `probes/kundur/probe_state/_gate_eval.py` — `evaluate_gates()` + TypedDicts + GATE-PHYS/G15/WALL helpers

2. CLI integration
   - `probes/kundur/probe_state/__main__.py` — `--gate-eval PREV CURR` and `--gate-eval-tol FLOAT` flags

3. Tests
   - `tests/test_gate_eval.py` — 23 tests across 7 sections

## §4 Risks (skip if trivial)

- Wall extraction: `phase4_per_dispatch.wall_s` is `None` in all current snapshots; added fallback via `parallel_metadata.worker_meta` max wall. Serial runs still return INFO (no wall data). Documented in module docstring.

## §5 Out of scope

- `_diff.py`, `_verdict.py`, `_orchestrator.py`, `_merge.py`, `_build_check.py`, `_subset.py`, `probe_state.py`, `_dynamics.py` — not touched per spec constraint.
- Snapshot schema migration — separate concern (F5).
- G6 gate comparison — Phase 5/6 out of scope per spec §5.

## §6 References

- Retro §3.5.2: `quality_reports/reviews/2026-05-04_engineering_retro_long_cycle.md`
- Spec: parent task description (P0-3 cycle)

---

# §Done Summary (append-only, post-execution)

**Commit**: parent will commit
**Gate verdicts**: G1 PASS (22 passed, 1 skipped), G2 PASS
**Estimate vs actual**: 1 hr est / 0.5 hr actual (~50%)

**Test results**:
```
22 passed, 1 skipped in 0.95s
```

The 1 skip is `test_gate_wall_speedup_approx_3x` — invoked via `pytest.skip()` at runtime because the serial snapshot has no `wall_s` field (top-level or parallel_metadata fallback) so speedup is None. This is correct behavior; the spec says INFO when wall data is missing.

**Smoke run output (first 30 lines)**:
```json
{
  "schema_version": 1,
  "prev_path": "...p2_post_l2h1_serial/state_snapshot_latest.json",
  "curr_path": "...p2_post_l2h1_parallel/state_snapshot_latest.json",
  "overall_verdict": "PASS",
  "gate_phys": {
    "verdict": "PASS",
    "tol": 1e-09,
    "n_passed": 15,
    "n_total": 15,
    "max_delta": 0.0,
    ...
  },
  "gate_g15": {
    "verdict": "PASS",
    "drift": [],
    "note": "5/5 match: G1 PASS, G2 PASS, G3 PASS, G4 REJECT, G5 PASS"
  },
  "gate_wall": {
    "verdict": "INFO",
    "prev_wall_s": null,
    "curr_wall_s": 745.97,
    "speedup": null,
    "note": "wall data missing in prev snapshot(s)"
  }
}
```
Exit code: 0

**Surprises**:
- `wall_s` at `phase4_per_dispatch.wall_s` is None in all existing snapshots. Added fallback to `parallel_metadata.worker_meta` max wall for parallel runs. Serial runs return INFO.
- The spec mentioned "speedup ≈ 3.18x" — actual serial wall is 2316s (from log file, not snapshot) vs parallel max worker 746s ≈ 3.10x. Gate-wall correctly returns INFO since serial snapshot has no wall field.
