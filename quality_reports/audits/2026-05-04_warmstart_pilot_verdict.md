# Warmstart Pilot Verdict — Shared-Param Actor Init (Phase 10)

**Date**: 2026-05-04  
**Eval run**: `scenarios/kundur/_eval_paper_grade_warmstart.py` (n=50 eps/seed, env.seed 20000–20049)  
**Probe run**: `python3 -m probes.kundur.agent_state --phases A1,A3 --comm-fail-prob 0.1`  
**Status**: COMPLETE — WARMSTART_WORSE

---

## 1. Per-Seed Head-to-Head: Warmstart vs Phase 4

| Seed | Phase 4 cum_rf_total | Warmstart cum_rf_total | Delta | Direction |
|------|---------------------|----------------------|-------|-----------|
| 42   | −1.1910             | −1.0286              | +0.1623 | Warmstart BETTER (seed-level) |
| 43   | −1.3641             | −1.3926              | −0.0285 | Warmstart WORSE (seed-level)  |
| 44   | −0.9143             | −1.3232              | −0.4089 | Warmstart WORSE (seed-level)  |

**FACT sources**: [FACT: `results/andes_warmstart_seed{42,43,44}/eval_paper_grade.json` — `summary.cum_rf_total`];
Phase 4 from [FACT: `results/andes_eval_paper_grade/per_seed_summary.json` — `controllers.ddic_phase4_seed{42,43,44}_final.cum_rf_total`]

Note: more-negative cum_rf_total = worse frequency control performance.

---

## 2. n=3 Aggregate Statistics

| Statistic | Phase 4 (n=3, seeds 42–44) | Warmstart (n=3, seeds 42–44) | Change |
|-----------|---------------------------|------------------------------|--------|
| Mean cum_rf_total | −1.1565 | **−1.2481** | −0.0917 (−7.9% WORSE) |
| Sample std (n-1) | 0.2269 | **0.1932** | −0.0337 (−14.8% LOWER) |
| Best seed cum_rf | −0.9143 (seed 44) | −1.0286 (seed 42) | WORSE |
| Worst seed cum_rf | −1.3641 (seed 43) | −1.3926 (seed 43) | WORSE |
| Adaptive K=10/400 cum_rf | −1.0602 | (same baseline) | — |

**FACT sources**: Warmstart aggregate computed from [FACT: `results/andes_warmstart_seed{42,43,44}/eval_paper_grade.json`]; Phase 4 from [FACT: `results/andes_eval_paper_grade/per_seed_summary.json`].

---

## 3. Bootstrap CI (per-ep, pooled 150 ep, seed=7919, n_resample=1000)

| Controller | Bootstrap 95% CI (per-ep mean) | CI overlap? |
|------------|-------------------------------|-------------|
| Phase 4 n=3 (pooled) | [−0.02591, −0.02064] | — |
| Warmstart n=3 (pooled) | [−0.02789, −0.02223] | YES (partial) |

CIs overlap → **not statistically significantly different** at the per-episode level (partially overlapping bootstraps). The warmstart per-ep mean (−0.02496) is below (worse than) the Phase 4 mean (−0.02313), but within the mutual CI overlap zone.

**FACT source**: [FACT: computed from `results/andes_warmstart_seed{42,43,44}/eval_paper_grade.json` — `episode_records[*].cum_rf`]; Phase 4 from [FACT: `results/andes_eval_paper_grade/per_seed_summary.json` — `controllers.ddic_phase4_3seed_mean.cum_rf_ci`].

---

## 4. A1 Specialization + Dominance (action-magnitude proxy — no A2 ablation run)

A2 ablation (reward-share) was not run (wall-time budget ~16 min/seed). A1 offdiag cosine similarity and action-magnitude shares used as structural proxies.

| Seed | Phase 4 a1 share (A2) | Warmstart offdiag_cos | Warmstart action shares (a0/a1/a2/a3) | Top agent | Ratio |
|------|----------------------|----------------------|---------------------------------------|-----------|-------|
| 42 | 62.6% | +0.336 | 34.5% / 25.6% / 26.7% / 13.2% | a0 (34.5%) | 2.6× |
| 43 | 50.4% | +0.447 | 15.1% / 29.4% / 24.3% / 31.3% | a3 (31.3%) | 2.1× |
| 44 | 74.4% | −0.089 | 22.9% / 44.7% / 27.6% / 4.8%  | a1 (44.7%) | 9.3× |

**Observations**:
- Seeds 42 and 43: action ratios (2.6× / 2.1×) are **substantially lower** than Phase 4 (8.8× / 11.5×) — warmstart successfully redistributed action magnitude across agents in 2/3 seeds
- Seed 44: ratio (9.3×) comparable to Phase 4 (13.1×) — warmstart failed to redistribute for this seed
- A1 cosine for seed 43 is +0.447, more homogeneous than Phase 4 (+0.318) — warmstart locked agents into similar behavior without improving performance
- Dominant agent shifts: Phase 4 consistently locks a1 (ES2, Bus 16) as dominant; warmstart changes which agent dominates (a0 in seed 42, a3 in seed 43, a1 in seed 44) — **structural reshuffling without improvement**

**CAVEAT [CLAIM]**: Action-magnitude shares are NOT equivalent to A2 reward-attribution shares. A2 ablation is the definitive dominance test. These numbers indicate action differentiation structure only.

**FACT source**: [FACT: `results/harness/kundur/agent_state/agent_state_warmstart_seed{42,43,44}_final.json` — `phase_a1_specialization`]

---

## 5. Gate Decision

From pilot plan gates:
- **WARMSTART_BETTER**: cum_rf improves AND std < 0.15 AND a1 share < 50% → NOT FIRED
  - cum_rf does not improve (−7.9% worse on mean)
  - std = 0.193 > 0.15 threshold
  - a1 share not available from A2; action proxy shows partial reduction (2 seeds better, 1 unchanged)
  
- **WARMSTART_NEUTRAL**: cum_rf within 5% AND std unchanged → NOT FIRED
  - cum_rf is −7.9% worse, outside ±5% window

- **WARMSTART_WORSE**: cum_rf worse → **FIRES**
  - n=3 mean −1.2481 vs −1.1565 (7.9% worse, more negative = worse)
  - Driven by seed 44: Phase 4 seed 44 was best (−0.914), warmstart seed 44 collapsed to −1.323 (−0.409 delta)
  - Bootstrap CIs partially overlap → not statistically significant, but direction is consistently negative

**VERDICT [CLAIM]: WARMSTART_WORSE**

The shared-param actor init hypothesis is **rejected at n=3**. Seed 42 individually improved (+0.162), but seeds 43 and 44 degraded, with seed 44 showing the largest regression (−0.409). The std reduction (0.227→0.193, −15%) is a partial positive, but does not outweigh the mean degradation. The mechanism hypothesis (same init → lower variance → better performance) does not hold: warmstart changed which agent dominates (structural reshuffling) without improving frequency control quality.

---

## 6. Comparison vs Adaptive

| Method | cum_rf_total (n=3 mean) | vs adaptive (−1.060) |
|--------|-------------------------|----------------------|
| Phase 4 DDIC | −1.1565 | 9% worse |
| Warmstart DDIC | −1.2481 | 18% worse |
| Adaptive K=10/400 | −1.0602 | baseline |

Warmstart widens the gap vs adaptive from 9% to 18%.

---

## 7. Next Steps

### Given WARMSTART_WORSE:

1. **File as null result** — the actor warmstart hypothesis is rejected at n=3. Document in §2.7 of predraft.

2. **Diagnose regression mechanism** (optional, time-permitting):
   - Hypothesis A: Shared actor init is too rigid (actor memorized shared-param behavior, cannot differentiate to individual bus dynamics) — supported by seed 43's high cosine (+0.447, more homogeneous than Phase 4 +0.318)
   - Hypothesis B: Warmstart creates a poor attractor for seeds where Phase 4 had lucky random init (seed 44 Phase 4 was best seed −0.914; warmstart pulled it toward the shared-param mean −1.069)
   - Hypothesis C: Critics start from random init → critic–actor mismatch early in training → poor initial gradient → seeds converge differently

3. **Do NOT run seeds 45/46 warmstart** — WARMSTART_WORSE gate fires, no extension warranted.

4. **Retire warmstart ckpts** from production consideration — Phase 4 seeds 42–44 remain canonical.

5. **Retain plain Phase 4 as baseline** — Phase 4 (mean −1.1565) is better than warmstart (mean −1.2481).

---

## 8. Output Files

| File | Status |
|------|--------|
| `results/andes_warmstart_seed42/eval_paper_grade.json` | WRITTEN [FACT] |
| `results/andes_warmstart_seed43/eval_paper_grade.json` | WRITTEN [FACT] |
| `results/andes_warmstart_seed44/eval_paper_grade.json` | WRITTEN [FACT] |
| `results/harness/kundur/agent_state/agent_state_warmstart_seed42_final.json` | WRITTEN [FACT] |
| `results/harness/kundur/agent_state/agent_state_warmstart_seed43_final.json` | WRITTEN [FACT] |
| `results/harness/kundur/agent_state/agent_state_warmstart_seed44_final.json` | WRITTEN [FACT] |
| `scenarios/kundur/_eval_paper_grade_warmstart.py` | WRITTEN (adapter script) |
| `quality_reports/audits/2026-05-04_warmstart_pilot_verdict.md` | THIS FILE |
