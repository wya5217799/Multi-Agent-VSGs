# Methodology Referee Review — TPWRS Submission

**Paper:** Wei, "An Honest Reproduction of Multi-Agent SAC for VSG Inertia/Damping Control..." (commit 8f35406)
**Reviewer role:** Methodology referee (Reviewer 1 of 5)
**Date:** 2026-05-05
**Target venue:** IEEE Transactions on Power Systems (Reproduction Study track)
**Recommendation:** Minor Revision
**Composite score:** 78 / 100

---

## Executive Summary

This is a methodologically transparent reproduction with above-average rigor for an RL-in-power-systems paper, but several statistical-reporting weaknesses prevent a clean Accept. **Strengths:** pre-registered hparam sweep with frozen gates, fixed test seeds, bootstrap-CI–based "tied" claim (not "better"), open release of training/eval artifacts, and explicit Gate A3 self-flagging at n=5. **Weaknesses:** (1) the 0.265 dispersion threshold for §IV.H per-axis robustness is a category-mismatch comparison — cross-seed variance and cross-hparam point-spread are different quantities, so the "fragile" verdict, while directionally defensible, rests on a fairness assumption the paper does not justify; (2) the n=5 confirmation only patches one of four single-seed perturbation points (f_high), leaving d_low / d_high / a_low untested; (3) Welch's t and a paired-by-test-episode comparison are absent despite being the natural complement to overlapping bootstrap CIs; (4) effect-size reporting is partial (no Cohen's d, mixed Δ-conventions); (5) bootstrap unit-of-analysis (per-episode pooled vs per-seed) is not stated. Recommendation: **Minor Revision** — issues are mechanical and do not affect the headline DECORATIVE_CONFIRMED conclusion. Methodology rating: **78/100**.

---

## 1. Methodology Summary

The paper is a computational reproduction study with a pre-registered local sensitivity sweep. Design family: between-subjects comparison of four controllers (Uncontrolled, tuned Adaptive K=10/400, multi-agent DDIC, shared-parameter SAC, and a warmstart variant) on a fixed 50-episode test set under matched communication-failure conditions. Inference: bootstrap 95% CIs on per-episode cum_rf, with overlap-test logic for the "tied" claim and disjoint-test logic for the f_high vs baseline degradation claim. A pre-registered Tier-A gate (A3, σ > 0.25 cross-seed dispersion) is applied as a self-flag for n=5 underpowering. The §IV.H sensitivity sweep adds a single-seed log-symmetric perturbation grid across three axes (Φ_F, Φ_D, action range) with frozen acceptance gates.

## 2. Sampling Strategy Review

**Training-seed sample (n=5, seeds 42–46), §IV-A and Table II.**

- **Adequacy at n=5.** With observed σ = 0.265 on cum_rf totals (22% of mean) and an effect size of |Δ| = 0.126 between DDIC (-1.186) and adaptive (-1.060), the post-hoc detectable difference at α=0.05, power=0.8 is roughly Δ ≈ 0.47 — far larger than the observed gap. The paper correctly does not claim DDIC is better; it claims a tie. Gate A3 is honestly fired and the limitation is explicit (§VI bullet 1).
- **What's missing.** A formal power calculation for the n=10 Tier-B recommendation is asserted but not derived. Replace "Tier-B (n=10) recommended" (line 117, line 371) with "Tier-B sample size ≥ N derived from observed σ = 0.265 and a target minimum detectable Δ of X (power 0.8, α=0.05)".
- **Phase 9 / Phase 10 sample (n=3).** Tables III and IV both rely on n=3 seeds. With n=3 the bootstrap CI is over 50×3=150 per-episode pseudo-observations, which masks how few independent training trajectories are behind it. The DECORATIVE_CONFIRMED claim depends critically on this comparison; n=3 vs n=5 baseline is a sample-size mismatch that should be either matched (extend Phase 9 to n=5) or explicitly disclosed at the claim site (§IV-G last paragraph).

**Test-set construction (env.seed 20000–20049, 50 episodes, p_cf=0.1), §III-A.**

- **Adequate and well-described.** Fixed seeds, identical for all controllers, p_cf matched to training. The Phase 3 v2 audit (§III-D) explicitly catches and reports a previous test-set asymmetry — this is exactly the kind of error a reproduction paper exists to surface.
- **Possible improvement.** A stratification-by-bus check on the test set would strengthen external validity (currently relying on uniform sampling to deliver representative coverage).

## 3. Statistical Analysis Review

### 3.1 Bootstrap CI (n_resample=1000, α=0.05, seed=7919)

**Defensible but under-specified.**

- 1000 resamples is at the low end for α=0.05 endpoint stability; standard recommendation ≥2000, ideally 5000–10000 for publication. Report Monte-Carlo error on CI endpoints, or rerun at n_resample=10000.
- **Critical specification gap (line 354–365):** the paper states "bootstrap CI on per-episode cum_rf values" — but the unit of resampling is ambiguous. With 5 seeds × 50 episodes = 250 observations, are episodes resampled iid (ignoring seed clustering) or hierarchical (resample seeds, then episodes within seed)? **Concrete fix:** state explicitly. Given cross-seed σ = 0.265 is the dominant variance component, a cluster bootstrap by seed is correct — and would *widen* the CI. If the current CI is iid-pooled, the "tied" verdict is conservative (good); the f_high disjoint claim (§IV-H) however becomes more fragile under cluster bootstrap and should be re-checked.

### 3.2 Interpretation logic

- **Phase 4 vs adaptive (overlap test, line 360–365).** Correct usage: each controller's mean lies inside the other's CI, so "tied" is the right call.
- **f_high vs baseline (disjoint test, §IV-H).** Disjoint with 0.055-unit gap. Correct in form. **But:** disjoint CIs are *sufficient* for significance, not necessary; this is a directional claim where Welch's t or Mann–Whitney would be more powerful and standard. Add Welch's t at line 622.

### 3.3 Gate A3 logic (σ = 0.265 > 0.25 dispersion threshold)

- **Pre-registered or post-hoc?** The 0.25 threshold is referenced without citation to where it was pre-registered. Audit `2026-05-04_andes_tier_a_n5_verdict.md` plausibly contains it, but the paper does not state the threshold was frozen *before* observing σ=0.265. **Concrete fix (line 367–371):** add footnote: "The σ > 0.25 threshold is from the Tier-A spec [audit citation], frozen prior to n=5 retraining."
- **Observed σ=0.265 is barely above threshold (6% margin).** Paper correctly treats this as flag, not definitive failure.

### 3.4 Welch's t / paired analysis: appropriate but missing

This is a real gap.

- **Per-episode paired test.** The 50 test episodes are *the same scenarios* across controllers (env.seed 20000–20049). This is a paired design, and a paired-t or Wilcoxon signed-rank on (DDIC_episode_i − Adaptive_episode_i) would have substantially more power than the current pooled bootstrap. **What would change my mind:** add Table II row "Paired Δ vs adaptive (mean, 95% CI, p)" computed as paired-t over 50 episodes. Most informative comparison currently missing.
- **Welch's t for n=5 vs n=5 seed means.** At line 358–365 (Phase 4 vs Adaptive) and line 615–620 (f_high vs Phase 4), report Welch's t on seed-mean cum_rf totals.

## 4. Sensitivity Sweep Methodology (§IV.H)

### 4.1 Pre-registered protocol — defensible

The pre-registration is real (cited at line 543 footnote, plan file `quality_reports/plans/2026-05-04_andes_hparam_sensitivity_spec.md` exists in repo and predates audit verdict). Frozen gate (per-axis σ < 0.265) was set before data collection. **Exemplary practice** for RL reproductions and should be highlighted, not buried in a footnote.

### 4.2 Single-seed (n=1) for 6 perturbation points — only borderline-adequate as a screen

- Defensible as screening tool (Stage 1).
- **But:** at seed 42 alone, f_high single-seed value of -1.488 turned out to be on the optimistic tail (n=5 confirmation gave -1.735). Could seed 42 be pessimistic at d_low (-1.607) or a_low (-2.416)? **Concrete fix at §IV.H "Verdict" paragraph (lines 628–637):** add: "We confirmed only one of six points (f_high) at n=5; d_low / d_high / a_low single-seed values are screening estimates and may shift by ±0.25 (cross-seed σ at baseline) under n=5 confirmation. Qualitative conclusion (no direction yields viable alternative) is robust to ±0.25 shift on every point because all six perturbations exceed baseline by >0.4."

### 4.3 Per-axis std vs 0.265 baseline-cross-seed — category-mismatch comparison

**Most significant methodology weakness.**

The §IV.H verdict computes per-axis σ across 2–3 hparam-perturbation points (e.g., F-axis σ = 0.608 over {f_low, f_mid, f_high}) and compares it to the n=5 cross-seed σ = 0.265. Labels gates FAIL when per-axis σ > 0.265.

- **The two quantities are not the same kind of dispersion.**
  - 0.265 is *random-effects* sample std of seed-induced variation at one config.
  - 0.608, 0.839, 0.866 are *systematic* point-spreads across deliberately chosen hparam settings (each at n=1).
- The point-spread will exceed cross-seed σ by construction whenever the axis has any local curvature, regardless of fragility. Perfectly smooth quadratic basin centered at f_mid with curvature κ gives F-axis σ = κ·step²/√3 even with zero seed noise — comparison detects curvature, not fragility.
- **Fairness fix.** Either (a) reframe gate as curvature/slope test, or (b) compare cross-hparam variance against cross-seed variance *at multiple points* (n=5 at each hparam setting). Option (b) expensive but correct.
- **What would change my mind:** Either (a) add paragraph at line 583–593 acknowledging "0.265 bar is cross-seed reference, not strict baseline; we use it as heuristic threshold and the headline finding (every direction degrades ≥25%) does not depend on the σ comparison" — cheapest fix, OR (b) confirm one more point at n=5 and recompute.

The current §IV.H verdict reads as clean three-way gate failure. It is not — gate is mis-specified. The verdict's *substance* (every direction degrades ≥25%) is correct and well-supported; only the σ-comparison framing is wrong.

### 4.4 n=5 confirmation only at f_high

- Reasonable triage (most-promising point first).
- **But the asymmetry should be stated.** Either confirm d_low at n=5 (additional ~3h wall) or add sentence at line 626: "Confirmation at n=5 was prioritized for f_high as the closest-to-baseline direction; d_low (single-seed -1.607) is the next-most-promising direction and remains a screening estimate."

## 5. Reproducibility Review

**Strong.** Comparable to or exceeds typical IEEE TPWRS reproduction-study expectations.

- Training scripts, evaluator (single + parallel orchestrator), agent-state probe, and audit reports all enumerated in §VIII.
- Bootstrap parameters explicitly stated at line 357.
- Pre-registered plan file pre-dates audit verdict.
- Comm-failure bug fix identified, characterized, fix described.

**Minor reproducibility gaps:**
- Hyperparameter table (Table I) lists deviations but not SAC training hyperparameters themselves (LR, batch size, replay buffer, target update, α auto-tune). Add as Table I-bis or appendix.
- Bootstrap unit-of-analysis (§3.1 above) is reproducibility blocker.

## 6. Effect Sizes

- Δ in absolute units: reported.
- Δ in % relative: mostly reported but inconsistently.
- **Cohen's d / standardized effect size: not reported.** Real gap. DDIC vs adaptive Cohen's d ≈ |Δ|/σ ≈ 0.126/0.265 ≈ 0.48 (small-to-medium). Add to Table II and Table V.
- **PHI_F scaling confound.** §IV-D paragraph honest about it, but quantify: "Of the 5–7× absolute-magnitude gap, X is attributable to Φ_F rebalance (since cum_rf scales linearly in Φ_F at fixed |Δω|); residual Y is genuine backend-driven gap."

## 7. Threats to Validity

### 7.1 Internal validity — partially addressed

- SAC seed noise vs hparam variation confound. §IV.H sweep at single seed conflates these. f_high n=5 confirmation breaks for one point only. Severity: Medium.
- Phase 9 / Phase 10 n=3 vs Phase 4 n=5. Severity: Medium-high.
- Reward-weight tuning is on-policy with test set. §IV.H sweep partially addresses. Acceptable.

### 7.2 External validity — well-bounded

- ANDES vs Simulink: paper upfront. Cross-backend cosine probe is partial check. **No revision required.**
- Generalization beyond Kundur 4-bus: not addressed. Add to §VI.

### 7.3 Construct validity — cum_rf as frequency-quality proxy

- cum_rf embeds Φ_F weight. Two papers with different Φ_F cannot be compared on cum_rf without rescaling. Paper acknowledges (§IV-D) but does not validate against backend-independent quantity.
- **What would change my mind:** add Σ |Δf(t)| dt (integrated absolute frequency deviation, in Hz·s) column to Table II.

## 8. Statistical Reporting Standards (IEEE)

| Item | Status |
|---|---|
| n stated | ✓ |
| Random-seed protocol | ✓ |
| Test/train separation | ✓ |
| Effect size (raw + %) | Partial (% inconsistent) |
| Effect size (standardized, Cohen's d) | **Missing** |
| 95% CI | ✓ |
| CI computation method | ✓ |
| Bootstrap parameters | ✓ |
| Bootstrap unit of analysis | **Missing** (iid vs cluster) |
| p-values / hypothesis test | **Missing** (paired-t and Welch's-t both absent) |
| Multiple-comparison correction | Not needed at current scale |
| Pre-registration | ✓ for §IV.H |
| Negative/null results reported | ✓ (Phase 7, Phase 10, §IV.H verdict) |

## 9. Methodology Rating

| # | Dimension | Weight | Score | Weighted |
|---|---|---|---|---|
| 1 | Identification (experimental design rigor) | 25% | 80 | 20.0 |
| 2 | Estimation (training/eval pipeline correctness) | 25% | 88 | 22.0 |
| 3 | Inference (CIs, MHT, bootstrap unit) | 20% | 65 | 13.0 |
| 4 | Robustness (sensitivity sweep methodology) | 20% | 70 | 14.0 |
| 5 | Replication (artifact release, pre-reg) | 10% | 92 | 9.2 |
| **Total** | | **100%** | | **78.2** |

### Pre-scoring sanity checks

| Check | PASS / FAIL |
|---|---|
| Sign check (DDIC > Uncontrolled) | PASS |
| Magnitude (Δ within reasonable range) | PASS |
| Dynamics (training convergence) | PASS |
| Clustering (CIs match seed structure) | **AMBIGUOUS** (bootstrap unit not specified) |
| Sample construction (test set reported) | PASS |
| Pre-registration of §IV.H gates | PASS |
| Honest reporting of nulls | PASS |

No FAILs. One AMBIGUOUS does not cap the score, but is a Major concern.

## 10. Recommended Revisions (Prioritized)

### MAJOR (must fix for acceptance)

1. **Specify bootstrap unit of analysis.** Line 354–365. State whether per-episode resampling is iid-pooled or hierarchical-by-seed. **Effort: low.**
2. **Add paired and Welch's t-tests.** Table II (DDIC vs Adaptive) and Table V (f_high vs Baseline). Paired-t over 50 test episodes. **Effort: low (one-day).**
3. **Reframe §IV.H per-axis σ comparison.** Lines 540–546, 583–593. The 0.265 cross-seed bar is not a fair reference for cross-hparam point-spread. Either reframe as curvature/slope test, or caveat explicitly. **Effort: low (rewrite ~half page).**

### MINOR (should fix for quality)

4. **Phase 9 sample size.** Extend Phase 9 to n=5 to match Phase 4. **Effort: medium (3 additional training runs).**
5. **Cohen's d in Tables II and V. Effort: trivial.**
6. **Bootstrap n_resample: 1000 → 5000.** Or report MC error on endpoints. **Trivial.**
7. **Hyperparameter table completeness.** Add SAC training hyperparameters inline. **Trivial.**
8. **Construct validation.** Add integrated |Δf| · dt to Table II. **Low.**
9. **Φ_F rebalance decomposition.** §IV-D, line 408–412. **Low.**
10. **External-validity bullet for topology.** §VI Limitations. Add: "Findings specific to Kundur 4-VSG; NE39 / 68-bus untested." **Trivial.**
11. **Power calculation for Tier-B.** Line 117, line 371. **Trivial.**

### Nice-to-have

12. d_low n=5 confirmation. Line 626.
13. Pre-registration footnote at line 367–371 for σ > 0.25 Gate A3 threshold.

## Summary

**Minor Revision.** Headline conclusions (DDIC ties tuned adaptive, multi-agent decorative on this backend, §IV.H verdict that no nearby hparam direction recovers advantage) are well-supported. Methodology weaknesses are either (a) reporting gaps fixable in a week (items 1, 2, 5, 6, 7, 8, 9, 10, 11) or (b) framing issues that do not change substantive conclusions (item 3). The single methodologically substantive concern (item 4, Phase 9 n=3 mismatch) is a quality issue rather than a fatal flaw because three independent lines of evidence (Phases 7, 9, 10) converge.

Above-average reproduction paper. Pre-registration of §IV.H + honest reporting of Gate A3 firing + comm-failure bug + all three null-result phases (7, 10, §IV.H) put it ahead of typical IEEE TPWRS RL submissions on transparency.
