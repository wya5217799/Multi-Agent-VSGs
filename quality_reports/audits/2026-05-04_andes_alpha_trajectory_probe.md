# Andes Alpha Trajectory Probe — 5 Seeds DDIC Phase 4
**Date:** 2026-05-04
**Status:** COMPLETE
**Data source:** `results/andes_phase4_noPHIabs_seed{42..46}/monitor_checkpoint.json` [FACT — current HEAD files]

---

## 1. Was Alpha Logged?

**Yes.** Alpha is in `monitor_checkpoint.json → _sac_losses[ep][agent]["alpha"]`.
Not present in `training_log.json` (only aggregate rewards) or `monitor_data.csv` (only env metrics).

---

## 2. Per-Seed Final Alpha Table (last 50-episode mean)

| Seed | Final Alpha (mean) | Osc Std (last 50ep) | Cum r_f (total) |
|------|--------------------|---------------------|-----------------|
| 42 | 0.9807 | 0.0491 | -1.1910 |
| 43 | 1.0342 | 0.0509 | -1.3641 |
| 44 | 0.9616 | 0.0434 | -0.9143 |
| 45 | 0.9022 | 0.0379 | -1.5234 |
| 46 | 1.0061 | 0.0495 | -0.9385 |

---

## 3. Cross-Seed Statistics [CLAIM — derived from logged values]

| Metric | Value |
|--------|-------|
| Cross-seed mean final alpha | 0.9770 |
| Cross-seed std final alpha | 0.0446 |
| Coefficient of variation (CV = std/mean) | 0.046 |
| Corr(final_alpha, cum_rf) | 0.341 |

---

## 4. Plot

`results/andes_alpha_trajectory_5seed.png`

Left panel: episode-by-episode alpha trajectory for all 5 seeds.
Right panel: scatter of final alpha vs. cumulative r_f with linear fit.

---

## 5. Verdict [CLAIM]

**ALPHA_STABLE**

Threshold definitions:
- ALPHA_HIGH_VARIANCE: cross-seed CV > 0.30
- ALPHA_STABLE: CV < 0.10
- ALPHA_MODERATE_VARIANCE: CV in [0.10, 0.30]
- ALPHA_NOT_CONVERGED(seedX): last-50ep std > 50% of mean alpha for that seed
- NO_CORRELATION: |corr(final_alpha, cum_rf)| < 0.3

---

## 6. Recommendation [CLAIM]

Cross-seed CV < 0.10 → alpha NOT the variance source (std=0.0446 on mean=0.9770). Look elsewhere for the root cause of std=0.265 in cum_rf_total: likely policy/value function initialization sensitivity, reward sparsity, or env stochasticity. No alpha tuning recommended at this stage.
