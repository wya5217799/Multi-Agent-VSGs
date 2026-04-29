# SG-side Pm-step Pilot Verdict (Option B / B+)

**Date:** 2026-04-30
**Trigger:** User decision to validate SG-side disturbance hypothesis before committing to Option E (CCS at Bus 7/9, 1-2 day physical-layer rebuild).
**Scope:** 3 paper_eval no_control runs, 50 scenarios each, `--disturbance-mode gen` (Bus 1/2/3 → SG side via `pm_step_proxy_g{1,2,3}` adapter). DIST_MAX ablation via custom ScenarioSet manifests (config DIST_MAX=1.0 lock untouched).

---

## Results

| Variant | per_M | cum_unnorm | max\|Δf\| mean | saturated >1.5 Hz | inert <0.10 Hz | settled_pct | tds_failed | NaN |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **baseline** DIST_MAX=1.0 | **-7.91** | -395.74 | 0.380 | 0/50 | ~35/50 | 12% | 0 | 0 |
| **P1a** DIST_MAX=2.0 | **-13.14** | -656.85 | 0.808 | 9/50 | 8/50 | 6% | 0 | 0 |
| **P1b** DIST_MAX=3.0 | **-16.14** | -807.14 | 0.818 | 6/50 | 6/50 | 2% | 0 | 0 |
| paper no_control | -15.20 | — | — | — | — | — | — | — |
| paper DDIC | -8.04 | — | — | — | — | — | — | — |

All runs: 50 scenarios × 50 steps × 4 agents = 10000 r_f terms summed; per_M = cum/50 = per-episode equivalent.

## Per-scenario distribution (P1b)

- 6 outlier scenarios with |mag| > 2.5 sys-pu drive ~520/807 = 64% of cum_unnorm
- 6 inert scenarios with |mag| < 0.5 contribute < 0.03 each
- mid-range (0.5-2.5 sys-pu): 38 scenarios, contribute steadily, max|Δf| ∈ [0.1, 0.8] Hz — **the meat of the RL learning signal**

## Verdict

**Option B+ (SG-side + DIST_MAX > 1.0) is VIABLE as a paper-comparable disturbance protocol.**

Evidence:
- P1b per_M = -16.14 lands within ±10% of paper no_control -15.20
- Distribution healthy: 38/50 mid-range scenarios provide non-saturated, non-inert RL signal
- Numerical stability OK across all 100 scenarios (P1a + P1b)
- Saturation tail is structural (large |mag| in [2.5, 3.0] window) — controllable by clamping DIST_MAX to 2.5

## Recommended next protocol

For both training and evaluation:
- `KUNDUR_DISTURBANCE_TYPE = pm_step_proxy_random_gen` (SG-side, Bus 1/2/3)
- `DIST_MAX = 2.5` (sys-pu) — picks up most of P1b's healthy distribution while halving saturation tail
- `DIST_MIN = 0.1` (unchanged)

This breaks the credibility-close lock on:
- `KUNDUR_DISTURBANCE_TYPE` default (was `loadstep_paper_random_bus`, dead per Phase A audit)
- `DIST_MAX` (was 1.0, locked 2026-04-28)

Both lock-breaks are pre-authorized: NOTES.md 2026-04-29 §Eval 协议偏差 (方案 B) acknowledges the LoadStep path is dead; user explicitly green-lit physical/lock changes 2026-04-29 ("不用管锁定问题，只要能解决问题就行").

## Why not Option E (CCS at Bus 7/9)

Option E (network-side CCS at load center) is more paper-faithful in mechanism (electrical injection vs mechanical Pm step), but has:
- 1-2 day build + NR + smoke + IC regen cost
- Three-Phase Dynamic Load already verified incompatible (single-phase Phasor topology)
- CCS path on this model needs Bus 7/9 wiring rework
- Risk of post-build smoke still showing weak signal (same network-far-from-injection-point concern)

Option B+ (SG-side + DIST_MAX≈2.5) achieves comparable per_M magnitude at zero physical-layer change. **If retrained policy still under-performs paper after Option B+ retrain → then escalate to Option E**.

## Limitations

1. **Per_M unit ambiguity (Q8)**: Paper -15.20 may not be per-episode equivalent — could be per-step, per-test-set, or per-N-agent normalized. Project's per_M / per_M_per_N are educated guesses. Magnitude-match to paper is necessary but not sufficient evidence of unit equivalence.

2. **Mechanism gap**: SG-side mechanical Pm step ≠ paper's network bus electrical LoadStep. The 4-ESS sees the disturbance through admittance coupling rather than direct mode-shape excitation. RL gradient *structure* may differ even if magnitude matches.

3. **Sample bias**: 6/50 outliers drive 64% of cum_unnorm. Trained policy may overfit to large-magnitude scenarios while ignoring mid-range ones. Need to monitor per-scenario reward distribution during training, not just cum_unnorm.

## Files

- `manifests/p1a_sg_dist2.json`, `manifests/p1b_sg_dist3.json` — custom ScenarioSet manifests
- `no_control_sg_metrics.json` — DIST_MAX=1.0 baseline (early run)
- `no_control_sg_dist2_metrics.json`, `no_control_sg_dist3_metrics.json` — P1a/P1b artifacts
- `no_control_sg_dist{2,3}_stdout.log` — per-scenario eval traces

## Decision

**Approved for Option B+ retrain pipeline:**
- Phase 1: code R2 fix (env-var pin train+eval to `pm_step_proxy_random_gen`, override DIST_MAX to 2.5)
- Phase 2a: PHI=0 ablation 200 ep (E1 — verify +10% RL improvement causality on baseline protocol)
- Phase 2b: SG-side DIST_MAX=2.5 retrain 500 ep (Option B+ main attack)
- Phase 3: 4-policy paper_eval on both anchors, write final verdict

Option E held in reserve.
