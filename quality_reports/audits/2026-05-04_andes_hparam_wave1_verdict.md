# ANDES Hparam Sensitivity — Wave 1 Verdict

**Date**: 2026-05-04
**Branch**: main (post-spec, pre-wave2)
**Spec**: `quality_reports/plans/2026-05-04_andes_hparam_sensitivity_spec.md`
**Status**: Wave 1 complete (4/4 runs done); wave 2 launching next

---

## 1. Scope

Wave 1 = 4-way parallel screening of high-information-density configs:
`f_low / f_high / d_high / a_high`. Single seed (42), 100 ep target.
All runs launched 2026-05-04 20:48 via tmux detached sessions; pre-flight
verified hparam injection through `training_log.json::hparam_effective`.

| Run | PHI_F | PHI_D | DM range | DD range | Purpose |
|---|---|---|---|---|---|
| `f_low`  | 3000  | 0.02 | [-10, 30] | [-10, 30] | F-axis lower neighborhood |
| `f_high` | 30000 | 0.02 | [-10, 30] | [-10, 30] | F-axis upper neighborhood |
| `d_high` | 10000 | 0.06 | [-10, 30] | [-10, 30] | D-axis upper neighborhood |
| `a_high` | 10000 | 0.02 | [-20, 60] | [-20, 60] | action upper neighborhood (±2×) |

Reuse points (Wave 0): `f_mid` ← `phase4_noPHIabs_seed{42..46}` (5×500ep);
`f_anchor` ← `phase2_pdf002` (50ep, paper PHI_F=100); `a_anchor` ←
`phase11_ddic_wide_seed42` (77ep, action ×20, TDS-divergent).

---

## 2. Final State per Run

| Run | episodes | wall (s) | termination |
|---|---|---|---|
| `f_low`  | 100/100 | 1358 | natural completion |
| `f_high` | 100/100 | 1354 | natural completion |
| `d_high` | 100/100 | 1362 | natural completion |
| `a_high` |  51/100 |  704 | **monitor early-stop @ ep 50: `reward_divergence`** (slope -284.7/ep, total change 14236, R²=0.30) |

All runs: `tds_failed = 0/total` over the full trace. `hparam_effective`
in each `training_log.json` matches the requested overrides byte-for-byte.

---

## 3. Health Metrics

Window for late-training metrics: `ep[N//2 : N]` where N = episodes
completed. Window for early baseline: `ep[0:10]`.

`rf_share`, `rh_share`, `rd_share` use **absolute values** of the
weighted reward components per spec §2 (revised 2026-05-04).

| Run | rf% | rh% | rd% | sat% | tds% | max_df (Hz) | mean_reward[late] | mean_reward[early] | drift |
|---|---|---|---|---|---|---|---|---|---|
| `f_low`  | 43.7 | 50.5 | 5.8 | 0.1 | 0.0 | 0.451 |   −748.8 |  −3543.3 | **+2794** |
| `f_high` | 84.8 | 13.2 | 2.0 | 0.1 | 0.0 | 0.442 |  −3326.8 |  −6316.2 | **+2989** |
| `d_high` | 69.0 | 26.1 | 4.9 | 0.0 | 0.0 | 0.481 |  −1937.9 |  −4748.2 | **+2810** |
| `a_high` | 32.7 | 65.1 | 2.2 |14.5 | 0.0 | 0.848 | −19078.6 | −14075.0 | **−5004** |

Source: `results/andes_hparam_sweep/<id>_seed42/monitor_data.csv`.
Aggregate JSON: `results/andes_hparam_sweep/wave1_health.json`.

---

## 4. Pre-Registered Gate Verdicts

Spec §2 ACCEPT thresholds applied **without modification**.

| Run | rf_share ∈ [5%, 50%] | sat < 70% | tds < 5% | drift > 0 | OVERALL |
|---|---|---|---|---|---|
| `f_low`  | 43.7% ✓ | 0.1% ✓ | 0.0% ✓ | +2794 ✓ | **PASS** |
| `f_high` | 84.8% ✗ (over) | 0.1% ✓ | 0.0% ✓ | +2989 ✓ | **FAIL** (rf_share) |
| `d_high` | 69.0% ✗ (over) | 0.0% ✓ | 0.0% ✓ | +2810 ✓ | **FAIL** (rf_share) |
| `a_high` | 32.7% ✓ | 14.5% ✓ | 0.0% ✓ | −5004 ✗ | **FAIL** (drift, divergence) |

**Note on rf_share thresholds**: spec §2 is pre-registered at [5%, 50%]
with IDEAL [10%, 40%]. Two of four runs (`f_high`, `d_high`) fail by
exceeding 50%. Threshold is **not modified** in this verdict per
governance rule (no post-hoc renegotiation). The audit must report
these as FAILs and the paper-§V claim must reflect this.

---

## 5. Per-Hypothesis Status

| Hypothesis | Wave | Required points | Status after wave 1 |
|---|---|---|---|
| `H_robust_PHI_F` | W1 (3 points: f_low/f_mid/f_high) | f_low ✓, f_mid (reuse, ✓), f_high ✓ | **All 3 points collected**; cum_rf eval still pending; max_df ∈ {0.451, ~0.40, 0.442} (~Hz) — physical-stability variance < 0.05 Hz |
| `H_robust_PHI_D` | W1+W2 (3 points: d_low/f_mid/d_high) | d_low **missing**, f_mid ✓, d_high ✓ | **2/3 points**; need `d_low` for final verdict |
| `H_robust_action` | W1+W2 (3 points: a_low/f_mid/a_high) | a_low **missing**, f_mid ✓, a_high ✓ (FAIL via divergence) | **2/3 points**; `a_high` already FAIL, but `a_low` needed to test asymmetry (is failure two-sided or one-sided?) |
| `H_anchor_paper_F` | W0 reuse | `phase2_pdf002` (50ep) | reuse pending health-metric extraction |
| `H_anchor_paper_action` | W0 reuse | `phase11_ddic_wide` (77ep TDS-divergent) | **FAIL satisfied** (TDS divergence in log) |
| `H_decorative_robust` | W0 reuse | `phase9_shared_seed{42..44}_500ep` | pending (separate analysis) |

---

## 6. Key Findings

**1. Physical stability ≠ training-reward magnitude.**
The three neighborhood points (`f_low`, `f_high`, `d_high`) all show
`max_df` between 0.44 and 0.48 Hz (variance < 0.05 Hz, well below the
0.265 cum-rf cross-seed std bar from §1). However, raw training reward
magnitudes differ by 2–4× because PHI_F and PHI_D enter the reward
multiplicatively. Cross-config training-reward comparison is therefore
**not a valid robustness signal**; only physical metrics
(`max_df`, `tds_rate`, `saturation`) and post-hoc test-set evaluation
of `cum_rf_total` are valid for `H_robust_*` gates.

**2. `f_high` and `d_high` fail rf_share gate by over-saturating
frequency contribution, not by collapsing it.**
Both push r_f to dominate (>69%) while r_h shrinks to <30%. The pre-
registered ACCEPT range was symmetric around r_f's "balanced" share;
exceeding the upper bound means the gradient is dominated by frequency
alone. This is a real config-quality signal — gradient diversity matters
for SAC exploration — but it does **not** mean the trained policy
performs worse on the physical task. Test-set evaluation is the
disambiguator.

**3. `a_high` is the only run with a behavioral failure mode.**
- Reward divergence at ep 50 (monitor auto-halt).
- `max_df` 0.848 Hz (~2× the other three runs).
- `r_h` share 65% — the wider action range makes |Δa_h| penalties
  dominate, redirecting the gradient away from frequency control.
- `tds_failed = 0%` — the simulator is fine; the **policy** is bad.

This contrasts with `a_anchor` (action ×20, reused from
`phase11_ddic_wide`), which fails by **physical TDS divergence**.
Two distinct failure modes on the action axis: behavioral at ×2,
physical at ×20.

**4. The 4 runs collectively suggest the action axis is the most
fragile.**
- F axis: max_df spread 0.009 Hz across ±3× neighborhood
- D axis: max_df spread (vs f_mid) ≈ 0.08–0.14 Hz at +3×
- action axis: max_df 0.848 Hz at +2× (training broke at ep 50)

`a_low` is required to confirm whether the failure is one-sided
(only wider) or two-sided (also narrower).

---

## 7. Wave 2 Decision

Per spec §9 decision tree, the relevant trigger is:
> "`d_high` or `a_high` health FAIL severely (TDS > 25% **OR**
> D_floor > 70%) → run opposite-side point on the failed axis"

`a_high` failed via reward divergence (not TDS, not D_floor — but the
spec language was written for backend-failure modes; behavioral
divergence is the equivalent severity). `d_high` failed via rf_share
over-saturation (not TDS, not D_floor — milder severity, but still a
gate FAIL).

**Wave 2 launch**: 2 runs in parallel
- `a_low`: action range ×0.5 ([-5, 15]), to test action-axis asymmetry
- `d_low`: PHI_D = 0.006, to complete D-axis 3-point coverage

This satisfies §9 row 1 (axis verdicts complete) and §9 row 3 (failed-
side opposite test) simultaneously. Wall budget: 2 × ~22 min ÷ 2-parallel
= ~22 min wall.

Wave 3 (cum_rf evaluation of all 5 wave-1+2 final.pt + reuse points,
then audit + paper §IV.E insertion) follows wave 2.

---

## 8. Open Items Before Final Audit

- [ ] Eval `f_low_seed42/agent_*_final.pt` on test set (env.seed
      20000–20049, comm_fail_prob=0.1) → cum_rf_total
- [ ] Same for `f_high`, `d_high` (a_high skip — diverged)
- [ ] Same for `a_low`, `d_low` after wave 2 finishes
- [ ] Pull `phase4_noPHIabs_seed{42..46}` ep[50:100] window health
      metrics for f_mid (currently only test-set cum_rf is on hand)
- [ ] Pull `phase2_pdf002` 50-ep health for f_anchor
- [ ] Compute final std(cum_rf) across 3 points per axis vs 0.265 bar
- [ ] Write `2026-05-XX_andes_hparam_sensitivity_verdict.md` (final)
- [ ] Insert paper §IV.E

---

## 9. File References

**Inputs (wave 1 outputs)**:
- `results/andes_hparam_sweep/{f_low,f_high,d_high,a_high}_seed42/`
  - `training_log.json` (episodes_completed, hparam_effective,
    episode_rewards)
  - `monitor_data.csv` (per-ep reward components, action stats, TDS)
  - `monitor_checkpoint.json` (calibration baselines)
  - `agent_{0..3}_final.pt` (policy checkpoints, ready for eval)
- `results/andes_hparam_sweep/wave1_health.json` (aggregate)
- `results/andes_hparam_sweep/{f_low,f_high,d_high,a_high}_seed42.log`
  (stdout/stderr trace)

**Spec / source**:
- `quality_reports/plans/2026-05-04_andes_hparam_sensitivity_spec.md`
- `scenarios/kundur/train_andes.py` (line 50–65 CLI flags;
  line 75–89 monkey-patch injection)

---

*End wave 1 verdict. Pre-registered gates evaluated without
modification; wave 2 launching with `a_low` + `d_low`.*
