# Editorial Decision Letter — Synthesis of 5-Reviewer Panel

**Manuscript:** "An Honest Reproduction of Multi-Agent SAC for VSG Inertia/Damping Control on the ANDES Kundur 4-Bus System"
**Author:** Yuang Wei
**Date:** 2026-05-05
**Synthesizer:** Editorial Synthesizer Agent
**Round:** 1 (post commit 8f35406)

---

## Decision: **Major Revision**

**Rationale**: 4 of 5 reviewers explicitly recommend Major Revision (EIC, Domain, Perspective, Devil's Advocate); 1 reviewer (Methodology) recommends Minor Revision. **IRON RULE #4 binds**: Devil's Advocate identified **2 CRITICAL issues** (confounded experimental design + n=3 underpowered for decorative claim), so Editorial Decision **cannot be Accept**. The paper has genuine contribution (decorative-MARL finding, evaluation bug catch, pre-registered sensitivity sweep) and exemplary transparency, but framing and statistical-power gaps require revision before it meets TPWRS standard.

---

## Reviewer Scores Summary

| Reviewer | Score | Recommendation | Severity |
|---|---|---|---|
| EIC (TPWRS area chair) | 72/100 | Major Revision | borderline-fit, needs reframing |
| Methodology Referee | 78/100 | Minor Revision | reporting gaps + framing issue |
| Domain Referee | 68/100 | Major Revision | literature critically thin (10 refs) |
| Perspective (ML reproducibility) | 78/100 | Major Revision | reproducibility lit uncited |
| Devil's Advocate | — | Major Revision | SIGNIFICANT CONCERNS, 2 CRITICAL |

**Average score: 74/100** (range 68–78). Convergence on Major Revision is strong.

---

## Consensus Findings (≥3 reviewers agree)

### CONSENSUS-1: "Decorative" framing overgeneralizes from confounded experimental design
**Cited by:** Devil's Advocate (CRITICAL C1), EIC (weakness #3), Methodology (item 9 §IV-D), Domain (M5)

The paper changed simulator (ANDES vs Simulink), reward weights (Φ_F 100×, Φ_D 50×), and action range (20× narrower) simultaneously. The headline "multi-agent framework is decorative" cannot be attributed to architecture alone — could be attributed to any single deviation. **Action**: reframe to "not statistically advantageous on this system and configuration"; scope conclusion to ANDES + tested hyperparameter point.

### CONSENSUS-2: Shared-parameter / decorative claim is underpowered at n=3
**Cited by:** Devil's Advocate (CRITICAL C2), Methodology (sample size §2), EIC (weakness #1)

DECORATIVE_CONFIRMED rests on shared-param (n=3) vs DDIC (n=5). Paper's own Gate A3 fires at n=5 (σ=0.265 > 0.25 threshold) for the easier DDIC-vs-adaptive comparison. The decorative claim — arguably the paper's strongest contribution — rests on weaker n=3 evidence. **Action**: extend Phase 9 shared-param to n=5, recompute CI, explicitly compare to baseline.

### CONSENSUS-3: Literature coverage is critically thin
**Cited by:** Domain (C2, primary issue), Perspective (ML reproducibility lit gap), EIC (originality weakness)

Bibliography has only 10 entries. Missing entire sub-domains: VSG/grid-forming (D'Arco/Suul, Bevrani, Markovic), MARL for power systems (Glavic, Hadidi, Roozbehani, Yan), phasor-vs-EMT (Demiray, Milano, Stiasny), ML reproducibility (Pineau, Engstrom, Agarwal, Schroeder de Witt 2020 — direct decorative-architecture precedent). **Action**: expand to ~25–30 entries; minimum 15 pre-submission for TPWRS.

### CONSENSUS-4: §IV.H sensitivity sweep methodology has a category-mismatch comparison
**Cited by:** Methodology (item 3, MAJOR revision), Devil's Advocate (M2), EIC (implicit in "exemplary discipline" + concerns)

The σ_hparam (0.608, 0.839, 0.866) compared against σ_seed (0.265) is detecting curvature, not fragility. Two quantities are different kinds of dispersion. Substantive finding (every direction degrades ≥25%) is correct and well-supported; only the σ-comparison framing is wrong. **Action**: reframe gate as curvature/slope test, OR caveat explicitly that "0.265 bar is heuristic, headline finding does not depend on σ ratio".

### CONSENSUS-5: Adaptive baseline is undertested for the tie claim
**Cited by:** Devil's Advocate (M3), EIC (must-fix #3), Methodology (implicit)

Adaptive uses 5×5 K-grid; DDIC uses 500 episodes × 5 seeds. Asymmetric tuning effort. **Action**: 10×10 K-grid or Bayesian optimization, OR documented-procedure justification.

### CONSENSUS-6: Figure provenance is mixed
**Cited by:** EIC (must-fix #2), Devil's Advocate (m1), Methodology (implicit reproducibility)

Figs 2, 4, 5 use legacy p_cf=0.0 data while comm-failure bug-fix is a stated contribution. Visual-textual inconsistency. **Action**: regenerate at p_cf=0.1 or move to appendix.

### CONSENSUS-7: Paired-t / Welch's t missing from inferential framework
**Cited by:** Methodology (item 2, MAJOR), Perspective (RL credibility lens)

50 test episodes are paired across controllers (env.seed 20000–20049 fixed). Paired-t / Wilcoxon would be more powerful than overlapping bootstrap CI. **Action**: add Table II row "Paired Δ vs adaptive (mean, 95% CI, p)".

---

## Divergence (reviewer disagreement)

### DIVERGENCE-1: Severity of n=5 with σ/μ=22%
- **EIC, Methodology, Devil's Advocate**: serious concern, blocks Accept
- **Methodology**: nonetheless argues paper "correctly does not claim DDIC is better" — design is internally consistent

**Synthesis**: paper's claims are internally consistent given n=5, but for "tied" to be a publishable finding (not just a non-rejection), Tier-B n=10 is needed. EIC + DA argue stronger; Methodology argues paper acknowledges adequately. **Tilts toward majority**: extend to n=10 for headline claim.

### DIVERGENCE-2: Title and "decorative" wording
- **EIC**: title too aggressive, replace "Decorative" with "Backend-Dependent"
- **Devil's Advocate**: "decorative" used 6× is rhetorical, not scientific
- **Domain, Perspective**: don't directly object to title but suggest scoping

**Synthesis**: change title to "Backend-Dependent Performance of Multi-Agent SAC for VSG Inertia/Damping Control: A Reproduction Study on the ANDES Kundur 4-Bus System" (EIC's recommendation). Reduce "decorative" usage to ≤2 instances (introduction + claim 5), with explicit scoping each time.

### DIVERGENCE-3: Whether to add second-topology pilot (NE39)
- **EIC**: must-fix #5 (would dramatically strengthen significance)
- **Methodology, Domain**: acknowledge gap but treat as nice-to-have / future work

**Synthesis**: not a must-fix for round 1, but explicit limitation bullet in §VI required ("Findings specific to Kundur 4-VSG; NE39 / 68-bus untested"). Add as concrete future-work item. If NE39 pilot is feasible (n=3, ~6h wall), strongly recommended.

---

## Devil's Advocate CRITICAL Issues (cannot be ignored per IRON RULE #4)

### CRITICAL #1: Confounded experimental design (DA C1)
- **Status**: must address before Accept.
- **Resolution path**: 
  - (a) Run paper-original Φ_F=100 + paper action range on ANDES — disentangle backend vs tuning. **OR**
  - (b) Explicitly downgrade §V.A "backend linearity" attribution to "combined backend + tuning + range deviations, which we cannot separately identify at n=5".
- **Editorial verdict**: option (b) is achievable in revision; option (a) is preferred but expensive.

### CRITICAL #2: n=3 underpowered for shared-parameter decorative claim (DA C2)
- **Status**: must address before Accept.
- **Resolution path**: extend Phase 9 shared-param to n=5 (3 additional training runs at ~22 min each ÷ parallelism). Recompute CI. Report whether DDIC vs shared-param CIs overlap at n=5.
- **Editorial verdict**: this is a real gap. Run the additional seeds.

---

## Revision Roadmap (Prioritized)

### Tier 1: BLOCKING (must complete for round 2)

| # | Task | Source reviewer | Effort |
|---|---|---|---|
| T1.1 | Extend Phase 9 shared-param to n=5 (matching Phase 4) | DA C2, Methodology #4, EIC | Medium (3 trainings + eval) |
| T1.2 | Reframe title and "decorative" framing throughout: replace with "not advantageous on this system / Backend-Dependent" | EIC, DA, Domain M5 | Low |
| T1.3 | Resolve full citation for Yang 2023 [3] (volume, issue, pages, DOI) | Domain C1 | Trivial |
| T1.4 | Expand bibliography to ≥15 entries (preferably 25–30): D'Arco/Suul, Bevrani, Markovic, Glavic, Hadidi, Stiasny, Pineau | Domain C2, Perspective | Medium |
| T1.5 | Discuss confounding (backend vs reward-weight vs action-range) explicitly in §V.A; downgrade attribution | DA C1, EIC | Low |
| T1.6 | Reframe §IV.H per-axis σ comparison (curvature/slope test, OR explicit caveat that 0.265 is heuristic) | Methodology #3, DA | Low |
| T1.7 | Regenerate Figs 2, 4, 5 at p_cf=0.1 OR move to appendix with stronger provenance disclaimers | EIC, DA m1 | Medium |

### Tier 2: HIGHLY RECOMMENDED (significantly strengthens revision)

| # | Task | Source reviewer | Effort |
|---|---|---|---|
| T2.1 | Add paired-t and Welch's t-tests to Tables II, V | Methodology #2, Perspective | Low |
| T2.2 | Strengthen adaptive baseline tuning (10×10 K-grid OR Bayesian optimization) | EIC, DA M3 | Medium |
| T2.3 | Add §II equation block: explicit swing equation, M=2H, reward-component formulation | Domain C3 | Low |
| T2.4 | Add §II one-line diagram of modified Kundur 4-bus | Domain C4 | Medium |
| T2.5 | Specify bootstrap unit of analysis (iid pooled vs cluster-by-seed) | Methodology #1 | Trivial |
| T2.6 | Add §II paragraph on GENCLS-as-VSG modeling limitations | Domain M1 | Low |
| T2.7 | Add §II paragraph justifying Bus 8 W2 = GENCLS(M=0.1) as low-inertia surrogate | Domain M2 | Low |
| T2.8 | Tier-B n=10 for DDIC and adaptive (resolve Gate A3) | EIC, Methodology, DA | Medium-high (5 + 5 trainings) |
| T2.9 | NE39 second-topology pilot (n=3) | EIC, DA Alt 1 | High (6h wall) |
| T2.10 | Add Cohen's d to Tables II, V; standardize % reporting | Methodology #5, #9 | Trivial |

### Tier 3: NICE-TO-HAVE (reviewer preferences, not blocking)

| # | Task | Source reviewer | Effort |
|---|---|---|---|
| T3.1 | d_low n=5 confirmation | Methodology #12 | Medium |
| T3.2 | Bootstrap n_resample 1000 → 5000 | Methodology #6 | Trivial |
| T3.3 | Add SAC training hyperparameters inline (Table I-bis) | Methodology #7 | Trivial |
| T3.4 | Σ\|Δf(t)\|dt construct-validity column to Table II | Methodology #8 | Low |
| T3.5 | Φ_F rebalance decomposition in §IV.D | Methodology #9 | Low |
| T3.6 | Cite Bevrani-Ise / Alipoor as adaptive baseline source | Domain M3 | Trivial |
| T3.7 | §V.A "position-driven observability" caveat or formalize | Domain M4 | Low |
| T3.8 | Power calculation for n=10 Tier-B recommendation | Methodology #11 | Low |
| T3.9 | External-validity bullet for topology in §VI | Methodology, EIC | Trivial |
| T3.10 | TOST equivalence test for shared-param vs DDIC | DA Logic Chain Claim 1 | Low |

### Tier 4: VENUE STRATEGY (post round 2)

| # | Suggestion | Source |
|---|---|---|
| T4.1 | Consider companion paper at NeurIPS Reproducibility Track or ReScience C, leading with the eval-leak finding | Perspective |
| T4.2 | Frame "decorative MARL on phasor backend" as primary thesis (not "Yang 2023 doesn't reproduce") | EIC, DA |

---

## Outcome Forecast

- **Round 1 (current)**: Major Revision.
- **Round 2 (after T1 + T2 completion)**: Likely Accept with Minor Revisions.
- **If only T1 completed (no T2)**: Likely second Major Revision or Reject.
- **Critical CRITICAL items**: T1.1 (n=5 shared-param) and T1.5 (confounding discussion) are the must-fix items for the Devil's Advocate's CRITICAL flag to lift.

---

## Files

**5 reviewer reports**:
- `quality_reports/reviews/2026-05-05_andes_ddic_review_eic.md`
- `quality_reports/reviews/2026-05-05_andes_ddic_review_methodology.md`
- `quality_reports/reviews/2026-05-05_andes_ddic_review_domain.md`
- `quality_reports/reviews/2026-05-05_andes_ddic_review_perspective.md`
- `quality_reports/reviews/2026-05-05_andes_ddic_review_devils_advocate.md`

**This editorial decision**: `quality_reports/reviews/2026-05-05_andes_ddic_editorial_decision.md`

---

## IRON RULE Compliance

| # | Rule | Status |
|---|---|---|
| 1 | Synthesizer cannot fabricate review comments | ✓ Every consensus point traces to ≥1 reviewer report |
| 2 | 5 reviewers reviewed independently (forked sub-agents, fresh context each) | ✓ Sub-agents launched in parallel via Agent tool |
| 3 | Devil's Advocate CRITICAL → cannot Accept | ✓ DA found 2 CRITICAL; decision is Major Revision |
| 4 | Phase 2.5 Revision Coaching only if Decision != Accept | Available but not auto-triggered (user can request) |
| 5 | READ-ONLY: reviewers do not modify manuscript | ✓ All output is markdown reports; main.tex untouched |

---

*End editorial decision. Author may invoke Phase 2.5 (Revision Coaching, Socratic dialogue) if desired, or proceed directly to revision via `academic-paper` revision mode.*
