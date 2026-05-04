# Agent State Probe — `comm_fail_prob` Condition Check

**Date**: 2026-05-04
**Probe version**: 0.1.0
**Status**: RERUN COMPLETE — dominance verdict STRENGTHENED under paper-faithful condition

---

## 1. Bug Found: `comm_fail_prob=0.0` Hardcoded in Rollout Phases

Inspection of probe source revealed:

| File | Line | Code (original) | Phase affected |
|---|---|---|---|
| `probes/kundur/agent_state/_ablation.py` | 41 | `AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=0.0)` | A2 (ablation rollouts) |
| `probes/kundur/agent_state/_failure.py` | 52 | `AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=0.0)` | A3 (failure forensics rollouts) |

Training uses `comm_fail_prob=0.1` (`scenarios/kundur/train_andes.py:136`). The existing 3-seed verdict (2026-05-03) was produced with A2/A3 rollouts at `comm_fail_prob=0.0` — a mismatch against training condition.

**Phase A1 (specialization) is unaffected**: it feeds synthetic observations directly to the policy with no env instantiation. The `offdiag_cos` values in the prior verdict are valid regardless.

---

## 2. Fix Applied

Added `--comm-fail-prob` CLI flag (default `None` = env default `COMM_FAIL_PROB=0.1`). The `None` default preserves paper-faithful behavior without breaking the original `0.0`-equivalent invocation (callers that want the legacy behavior pass `--comm-fail-prob 0.0`).

Files modified (all in `probes/kundur/agent_state/`):

- `_ablation.py`: `_make_env`, `_rollout_with_mask`, `run` — `comm_fail_prob` param threaded through; `comm_fail_prob_used` recorded in snapshot.
- `_failure.py`: `_rollout_with_trace`, `run` — same treatment.
- `agent_state.py`: `AgentStateProbe.comm_fail_prob` field added; `comm_fail_prob` in snapshot header; lambda closures pass `cfp` to A2/A3 phases.
- `__main__.py`: `--comm-fail-prob` argparse flag wired into `AgentStateProbe(comm_fail_prob=...)`.

---

## 3. Rerun: Phase 4 seed42, `comm_fail_prob=0.1`

**[FACT]** Run executed 2026-05-04 06:03–06:41 (wall 2272s = 37.9 min).

```
Checkpoint : results/andes_phase4_noPHIabs_seed42  (final)
Backend    : andes
Phases     : A1, A2, A3
comm_fail_prob : 0.1 (paper-faithful, matching training)
run_id     : phase4_seed42_commfail01
Snapshot   : results/harness/kundur/agent_state/agent_state_phase4_seed42_commfail01.json
```

---

## 4. Results Comparison Table (FACT)

### A1 — Specialization (env-free; identical across both runs)

| | Old @comm=0.0 | New @comm=0.1 | Change |
|---|---:|---:|---|
| offdiag_cos_mean | 0.352 | 0.352 | no change (expected — A1 is env-free) |
| Verdict | PASS | PASS | — |

A1 is confirmed identical — the phase does not instantiate an env.

### A2 — Counterfactual Ablation (env rollout; affected by comm_fail_prob)

| | Old @comm=0.0 | New @comm=0.1 | Change |
|---|---:|---:|---|
| baseline_cum_rf | −0.367 | −0.419 | −14.2% (worse under comm failure, expected) |
| Agent 0 share | 7.1% | 3.0% | ↓ — A0 now a stronger free-rider |
| Agent 1 share | 62.6% | **68.3%** | ↑ dominance increases |
| Agent 2 share | 13.1% | 13.7% | ≈ stable |
| Agent 3 share | 17.2% | 15.1% | ↓ slight decrease |
| max/min ratio | 8.8× | **23.1×** | ↑ imbalance more severe |
| Verdict | PENDING (old: REJECT) | REJECT | A2_FREERIDER_DETECTED (A0 share 3.0% < 5% threshold) |

**Key finding [FACT]**: Under paper-faithful `comm_fail_prob=0.1`, Agent 1 dominance rises from 62.6% to 68.3%, and Agent 0's contribution collapses from 7.1% to 3.0%. The max/min ratio increases from 8.8× to 23.1×. The imbalance is *worse* under training conditions, not better.

Note: The old seed42 A2 verdict was listed as "PENDING" in the 3-seed cross-seed table despite "REJECT" in the JSON (thresholds: `a2_freerider_max_share=0.05`; old A0 share 7.1% > 5%, so old verdict was technically PENDING, not REJECT). New verdict is a clean REJECT: A0 share 3.0% < 5% threshold.

### A3 — Failure Forensics (env rollout; affected by comm_fail_prob)

| | Old @comm=0.0 | New @comm=0.1 |
|---|---|---|
| clustered_by_bus | True | True |
| clustered_by_sign | True | True |
| worstk_most_common_bus | PQ_Bus14 (4/5) | PQ_Bus14 (4/5) |
| worstk_magnitude_median_pu | 1.80 | 1.80 |
| Verdict | REJECT | REJECT |

A3 failure clustering is unchanged: PQ_Bus14 remains the dominant failure bus (4/5 worst-k), median magnitude is identical at 1.80 pu.

---

## 5. Assessment of Existing 3-Seed Verdict

**[CLAIM]** The existing verdict (`2026-05-03_andes_agent_state_3seed_verdict.md`) under-reported A1 dominance for A2 due to the `comm_fail_prob=0.0` mismatch.

Under paper-faithful eval (`comm_fail_prob=0.1`):
- A1 dominance is **higher** (68.3% vs 62.6% for seed42)
- Free-rider severity is **higher** (A0 at 3.0% vs 7.1%)
- A3 failure clustering is **unchanged**
- A1 specialization is **unchanged** (A1 is env-free)

The prior verdict's qualitative conclusion — "Agent 1 dominance is STRUCTURAL, consistent across seeds" — is **strengthened** by this rerun, not weakened. The `comm_fail_prob=0.0` mismatch caused the prior verdict to *underestimate* the imbalance. The correct paper-faithful figure for seed42 is A1 share ~68%, not ~63%.

**The 3-seed verdict's cross-seed summary row for seed42 should be treated as a lower bound.** Running seeds 43 and 44 under `comm_fail_prob=0.1` would further solidify this, but given seed42 shows the same structural pattern with increased imbalance, the dominance claim stands.

---

## 6. What Was Verified in This Session [FACT]

1. [FACT] `_ablation.py:41` and `_failure.py:52` hardcode `comm_fail_prob=0.0` in the original probe code.
2. [FACT] `train_andes.py:136` uses `comm_fail_prob=0.1` — training condition mismatch confirmed.
3. [FACT] Phase A1 (`_specialization.py`) has no env instantiation — `offdiag_cos` values are independent of `comm_fail_prob`.
4. [FACT] New probe run (seed42, `comm_fail_prob=0.1`) completed successfully (exit 0, wall 2272s).
5. [FACT] New A2 result: A1 share=68.3%, A0 share=3.0%, ratio=23.1× (snapshot `agent_state_phase4_seed42_commfail01.json`).
6. [FACT] New A3 result: PQ_Bus14 clustered (4/5), median magnitude 1.80 pu — identical to old verdict.
7. [FACT] `--comm-fail-prob` flag added to probe CLI; default `None` uses env default (0.1).

---

## 7. Artifacts

| Path | Content |
|---|---|
| `results/harness/kundur/agent_state/agent_state_phase4_seed42_commfail01.json` | New probe snapshot (comm=0.1) |
| `results/harness/kundur/agent_state/AGENT_STATE_REPORT_phase4_seed42_commfail01.md` | Auto-generated probe report |
| `probes/kundur/agent_state/_ablation.py` | Fixed: `comm_fail_prob` param threaded through |
| `probes/kundur/agent_state/_failure.py` | Fixed: `comm_fail_prob` param threaded through |
| `probes/kundur/agent_state/agent_state.py` | `comm_fail_prob` field + snapshot header |
| `probes/kundur/agent_state/__main__.py` | `--comm-fail-prob` CLI flag |

---

*Probe implementation version 0.1.0. Rerun: seed42 only, per task constraint. Seeds 43/44 not rerun (training agents active, CPU budget reserved).*
