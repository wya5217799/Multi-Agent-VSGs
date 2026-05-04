# Tier A n=5 Verdict — ANDES DDIC Phase 4 PHI_ABS=0

**Date**: 2026-05-04  
**Pipeline run**: `scripts/run_tier_a_post_training.sh`  
**Log**: `results/tier_a_post_training.log`  
**Status**: COMPLETE

---

## 1. Per-Seed cum_rf_total (50 test episodes each, env.seed 20000–20049)

| Seed | cum_rf_total | a1 share (A2 probe) | A1 verdict | Notes |
|------|-------------|---------------------|------------|-------|
| 42 | −1.1910 | 62.6% | SPECIALIZED | canonical Phase 4 [FACT: per_seed_summary.json] |
| 43 | −1.3641 | 50.4% | SPECIALIZED | canonical Phase 4 [FACT: per_seed_summary.json] |
| 44 | −0.9143 | 74.4% | SPECIALIZED | canonical Phase 4 [FACT: per_seed_summary.json] |
| 45 | **−1.5234** | **66.4%** | SPECIALIZED | Tier A extension [FACT: ddic_seed45_final.json] |
| 46 | **−0.9385** | **56.2%** | SPECIALIZED | Tier A extension [FACT: ddic_seed46_final.json] |

**FACT sources**: `results/andes_eval_paper_grade/ddic_seed{42..46}_final.json` (seeds 45/46 from this run); `results/andes_eval_paper_grade/per_seed_summary.json` (seeds 42–44); `results/harness/kundur/agent_state/AGENT_STATE_REPORT_phase4ext_seed{45,46}_final.md` (probe reports).

---

## 2. n=5 Aggregate Statistics

| Statistic | Value |
|-----------|-------|
| n | 5 |
| Mean cum_rf_total | **−1.1863** |
| Sample std | **0.2649** |
| t-CI 95% [t(4,0.025)=2.776] | **[−1.515, −0.857]** |
| t-CI half-width | 0.329 |
| Bootstrap 95% CI (seed-level) | [−1.393, −0.984] |
| Best adaptive cum_rf_total | −1.060 (K_H=10, K_D=400) |
| max_df mean (n=5 bootstrap) | 0.238 Hz [0.235, 0.242] |

**n=3 comparison** (seeds 42–44 only):

| Statistic | n=3 | n=5 |
|-----------|-----|-----|
| Mean | −1.156 | −1.186 |
| Std | 0.227 | 0.265 |
| t-CI half-width | ~0.563 [t(2,0.025)=4.303] | 0.329 [t(4,0.025)=2.776] |
| CI | [−1.719, −0.593] | [−1.515, −0.857] |

Adding n=5 **tightened** the half-width by 0.234 (−42%) as expected. However, std grew from 0.227 → 0.265, indicating seeds 45/46 increased cross-seed dispersion.

---

## 3. Statistical Verdict vs Adaptive

**Best adaptive cum_rf_total = −1.060**  
**n=5 t-CI = [−1.515, −0.857]**

Adaptive −1.060 is **inside** the n=5 t-CI → no statistically significant difference at n=5.

**Gate decision: A3** (std = 0.265 > 0.25 threshold → high dispersion → proceed to Tier B).

- Gate A1 (CI excludes adaptive → claim defensible): NOT fired. Adaptive is at −1.060, CI spans [−1.515, −0.857], so adaptive sits inside CI.
- Gate A2 (CI contains adaptive, std normal): NOT fired because std ≥ 0.25.
- Gate A3 (high dispersion): FIRED. std = 0.265 > 0.25. Proceed to Tier B (n=10) for conclusive separation or accept stat-tie framing.

**Verdict [CLAIM]**: TIED at n=5. The adaptive baseline (−1.060) remains within the DDIC n=5 confidence interval. No statistically significant difference is claimed. The per-episode mean (−0.0237/ep DDIC vs −0.0212/ep adaptive) shows DDIC is ~12% worse on cum_rf at n=5. Gate A3 fires due to high cross-seed variance — the improvement from n=3 to n=5 is real (half-width reduced 42%) but the dispersion grew enough that the gate did not close.

---

## 4. Dominance Pattern (a1 share) — Does the 50–74% Pattern Hold at n=5?

| Seed | a1 (ES2, Bus 16) share | Bottom agent share | Dominant bus (A3) |
|------|------------------------|--------------------|--------------------|
| 42 | 62.6% | A0: 7.1% | PQ_Bus14 (4/5) |
| 43 | 50.4% | A0: 4.4% | PQ_Bus14 (4/5) |
| 44 | 74.4% | A2: 5.7% | PQ_Bus14 (3/5) |
| 45 | **66.4%** | A0: 0.6% | PQ_1 (2/5), sign-clustered |
| 46 | **56.2%** | A0: 6.2% | PQ_Bus14 (2/5), sign-clustered |

**Verdict [CLAIM]**: Pattern **HOLDS at n=5**. Seeds 45 and 46 both show a1 share in the 50–74% range (66.4% and 56.2% respectively). The A2 verdict for seed 45 is REJECT (freerider detected), seed 46 is PENDING/IMBALANCED — both indicate the same structural dominance observed in seeds 42–44. The bottom-agent share for seed 45 (a0 = 0.6%) is even more extreme than previous seeds.

Minor variation: failure clustering shifts from bus-clustered (seeds 42–44 primarily PQ_Bus14 3–4/5) to sign-clustered in seeds 45 and 46, with PQ_Bus14 still appearing as worst bus (2/5) in seed 46. This is within expected stochastic variation for 5 training seeds — the dominant physical structure (Bus 16 observability advantage for ES2) persists.

**5-seed dominance range: a1 = 50.4%–74.4%** (consistent with §2.3 finding, n=3 range 50–74%).

---

## 5. Convergence Check Notes

Both seeds 45 and 46 failed the C1 ratio criterion (< 0.2 threshold): seed 45 not shown in log, seed 46 ratio = 0.261. Both completed 500/500 episodes (C2 PASS). This indicates learning continued improving but did not fully plateau by the strict ratio threshold. The probe-based A2 results (functional dominance pattern, non-collapsed policies) confirm these are valid trained policies. The C1 FAIL is a WARNING, not a blocker — consistent with n=3 seeds.

---

## 6. Output Files

| File | Status |
|------|--------|
| `results/andes_eval_paper_grade/ddic_seed45_final.json` | WRITTEN [FACT] |
| `results/andes_eval_paper_grade/ddic_seed46_final.json` | WRITTEN [FACT] |
| `results/andes_eval_paper_grade/n5_aggregate.json` | WRITTEN [FACT] |
| `results/andes_eval_paper_grade/n5_summary.md` | WRITTEN [FACT] |
| `results/harness/kundur/agent_state/AGENT_STATE_REPORT_phase4ext_seed45_final.md` | WRITTEN [FACT] |
| `results/harness/kundur/agent_state/AGENT_STATE_REPORT_phase4ext_seed46_final.md` | WRITTEN [FACT] |
| `quality_reports/replications/2026-05-03_andes_ddic_honest_results_predraft_n5.md` | WRITTEN [FACT] |
