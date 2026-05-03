# Plan: Wire g4_position_hz into G4_position verdict computation

**Status**: DONE
**Estimated**: 0.5 hr | **Actual**: 0.2 hr
**Trigger**: Retro §3.5.2 + P2 ADR D1 follow-up (commit da252fc added field, wiring deferred)
**Supersedes**: none

## §1 Acceptance Gates (PRE-REGISTERED, IMMUTABLE)

| ID | Threshold | Measurement | Verdict |
|---|---|---|---|
| G1 | 10/10 pytest PASS | `pytest tests/test_p1_g4_threshold.py -x -v` | PASS |
| G2 | No regression in module load / gate-eval | `python -m probes.kundur.probe_state --gate-eval <serial> <parallel>` overall_verdict=PASS | PASS |

## §2 TodoWrite Mapping (1:1)

| Todo content | Step |
|---|---|
| Edit `_verdict.py` G4 floor line | §3.1 |
| Write `tests/test_p1_g4_threshold.py` | §3.2 |
| Run pytest | §3.3 |
| Run gate-eval smoke | §3.4 |
| Write plan doc | §3.5 |

## §3 Steps (atomic, file-level)

1. Fix `_verdict.py`
   - 1.1 `probes/kundur/probe_state/_verdict.py:408` — replace `g1_respond_hz` with `g4_position_hz` in G4 path only; add 4-line comment block explaining why.

2. Tests
   - 2.1 Create `tests/test_p1_g4_threshold.py` — 10 tests in 3 classes covering: §1 threshold wiring (3 dispatches → 3 sigs → PASS), §2 old 1mHz floor collapses (REJECT), §3 custom override respected.
   - 2.2 `pytest tests/test_p1_g4_threshold.py -x -v` → 10 passed

3. Smoke
   - 3.1 `python -m probes.kundur.probe_state --gate-eval <serial> <parallel>` → overall_verdict PASS (module load clean, no regression).

4. Docs
   - 4.1 Write this plan file.

## §4 Risks (skip if trivial)

- Monkeypatching `pc.THRESHOLDS` in tests: uses try/finally to restore; thread-safe for sequential pytest.

## §5 Out of scope

- G1, G2, G3, G5, G6 verdict logic — untouched.
- `g1_respond_hz` default value — kept at 0.001 Hz for G1 path.
- `dispatch_metadata.py` — P1-2 territory.
- `_gate_eval.py` — not touched.

## §6 References

- Commit da252fc — P2 parallelization; `g4_position_hz` field added, wiring deferred (D1)
- `probes/kundur/probe_state/probe_config.py::ProbeThresholds.g4_position_hz` docstring — alpha probe 2026-05-03 showed pm_step_proxy_bus7 max|Δf|=0.34 Hz primary, ~0.07-0.10 Hz on other agents
- `IMPLEMENTATION_VERSION` 0.6.0 changelog note: "Not yet wired into _verdict (D1 follow-up 2026-05-03)"

---

# §Done Summary (append-only, post-execution)

**Commit**: not committed (per task spec — DO NOT commit)
**Gate verdicts**: G1 PASS (10/10 tests), G2 PASS (gate-eval overall_verdict=PASS)
**Estimate vs actual**: 0.5 hr est / ~0.2 hr actual
**Surprises**: None. The fix was a single line swap + comment. Tests needed monkeypatching `pc.THRESHOLDS` directly (the singleton) rather than injecting via function parameter since `_g4_position` reads `probe_config.THRESHOLDS` at call time — try/finally restore pattern works cleanly.
