# Editor-in-Chief Review — TPWRS Submission

**Manuscript:** "An Honest Reproduction of Multi-Agent SAC for Virtual Synchronous Generator Inertia and Damping Control: Evidence That the Multi-Agent Framework Is Decorative on a Phasor-Based Backend"
**Author:** Yuang Wei
**Date:** 2026-05-05
**Reviewer:** EIC, IEEE Transactions on Power Systems
**Length:** 11 pages, IEEE format
**Decision:** Major Revision
**Score:** 72/100

---

## 1. Journal Fit Assessment

**Verdict: Borderline-fit, needs reframing.**

TPWRS scope covers power-system control, frequency regulation, and converter-interfaced resources — the *subject* (VSG inertia/damping control on a Kundur 4-bus system, §II.A) is squarely in scope. However, TPWRS is not a methods-validation venue; it publishes contributions that advance the field's understanding of power-system phenomena or controllers. A pure reproduction-of-failure paper sits awkwardly: TPWRS rarely publishes "Method X from a TPWRS paper does not reproduce on simulator Y" as a standalone contribution, and the manuscript itself is partly addressed *to* a TPWRS-published prior work (Yang et al. 2023). The author should reframe the contribution as a **methodological lesson about backend dependence in MARL-for-power-systems claims** rather than a referendum on the prior paper. With that reframe, fit becomes acceptable; without it, the paper reads as a critique submission better suited to a Replication/Negative-Results venue (e.g., ReScience C, or an arXiv preprint accompanying an IEEE PES letter).

## 2. Originality Assessment

**Standalone contributions identifiable from the text:**

1. **Decorative-MARL finding** (§IV.G–H, §V.C, claims 5–6): the shared-parameter SAC at 1/5 budget matching DDIC, plus 64% single-agent dominance, is a *new* finding not in the original paper. This is the strongest originality lever.
2. **Backend-linearity hypothesis** (§V.A): the testable conjecture that MARL gains require EMT-grade nonlinearity is a contribution worth publishing if developed further.
3. **Three same-class evaluation bugs** (Abstract; §I item 2): a methodological cautionary note about silent `p_cf=0` evaluator drift — useful but minor as a standalone.
4. **Honest negative results pipeline** (§VII Reproducibility): full open-sourcing of training, eval, and audit artifacts is laudable but is process, not science.

**Originality concerns:** The framing leans heavily on the comparison with Yang 2023 rather than presenting decorative-MARL as a positive scientific claim about MARL-for-VSG-control on phasor backends. The paper would be more original if "decorative on phasor backends" were the primary thesis (with Yang 2023 as motivating example) rather than "Yang 2023 doesn't reproduce" (with decoration as supporting evidence).

## 3. Significance Assessment

**Significance to the TPWRS readership: moderate, conditional on reframing.**

- *Positive*: MARL for grid control is a hot area. Several TPWRS papers in the past 24 months claim MARL advantages for inverter coordination; a careful demonstration that some such advantages may be backend-artifacts has cautionary value for the field.
- *Negative*: A single-system, n=5 study on a simplified Kundur case provides weak external validity. The author themselves admits Gate A3 fires (§IV.B) and recommends Tier-B (n=10). Without the larger run or replication on a second system (NE39 is mentioned in the repo but not in the paper), the significance is limited.
- *Significance multiplier*: §IV.H hyperparameter-sensitivity analysis (sweep + n=5 confirmation at f_high) is well-executed and substantially raises confidence that the null result is not a tuning artifact. This is the strongest part of the paper.

## 4. Overall Scientific Quality: 72/100

| Driver | Pts |
|---|---|
| Statistical rigor (bootstrap CIs, pre-registered gate, n=5 confirmation) | +15 |
| Honest documentation of provenance caveats and bug fixes | +10 |
| Negative-result discipline; explicit "decorative" labeling | +10 |
| Hyperparameter sensitivity §IV.H rules out under-tuning | +8 |
| Single backend, single topology, n=5 (not n=10) | −12 |
| Three figures (1, 3) regenerated under p_cf=0.1 but Figs 2, 4, 5 still legacy | −8 |
| DDIC absolute cum-r_f is 6.8× smaller than paper's −8.04, not closed | −6 |
| Adaptive baseline tuning uses only a 5×5 K-grid | −5 |

## 5. Strengths

1. **Pre-registered robustness gate (§IV.H, footnote 4):** σ < 0.265 frozen before the §IV.H sweep — exemplary discipline for negative-results submissions.
2. **n=5 confirmation at f_high (Table VIII, §IV.H):** disjoint bootstrap CIs ([−2.057, −1.449] vs [−1.393, −0.984]) rule out the obvious "under-tuning of Φ_F" objection.
3. **Three converging lines of evidence (§V.C):** per-agent ablation + shared-param SAC + warmstart pilot is genuine triangulation, not narrative repetition.
4. **Bug honesty (Abstract; §I item 2; Conclusion ¶2):** the same-class p_cf=0 evaluator bug fix and the test-set asymmetry fix (§III.D, formerly 65% → 9% margin reversal) are disclosed prominently, not buried.
5. **Open artifact release (§VII):** training scripts, paper-grade evaluator, agent-state probe, and audit reports all named and pathed.

## 6. Weaknesses

1. **n=5 with σ/μ = 22% (Table III, §IV.B):** the author's own Gate A3 fires. The headline tie claim rests on overlapping CIs that have substantial sample-size dependence. Why not n=10?
2. **Figure provenance is mixed (Figure provenance note, p.4–5):** Figs 2, 4, 5 use legacy p_cf=0.0 data. If the bug-fix is a stated contribution, why are 3 of 5 figures still drawn from the buggy regime?
3. **Project deviations (Table II):** ΔH range 20× narrower, Φ_F 100× larger, Φ_D 50× smaller. The cumulative effect: "DDIC" in this paper is structurally not the controller in Yang 2023. The reversed ratio (1.12 vs 0.62) cannot cleanly be attributed to backend linearity (§V.A) when controllers themselves differ this materially. **Central scientific weakness.**
4. **Adaptive baseline tuning is heuristic (§VI bullet 2):** a 5×5 K-grid is thin; the headline "DDIC ties adaptive" claim is sensitive to whether tighter K-search would push adaptive ahead.
5. **No second topology:** repository contains NE39; not running a second system means external validity of "phasor-backend → decorative MARL" is unsupported.

## 7. Editorial Tone Observation

The writing is **disciplined and well-balanced overall**, with one risk:

- **Defensive language is appropriate, not excessive.** Phrases like "not used for headline claims" (§IV.A), "qualitative pattern is unchanged" (Fig 2 caption), "we do not anchor our absolute cum-r_f" (§IV.C) read as appropriate scientific hedging, not apology.
- **The title is too aggressive.** "Evidence That the Multi-Agent Framework Is Decorative on a Phasor-Based Backend" puts a strong negative finding in the title. For TPWRS, a title like "Backend-Dependent Performance of Multi-Agent SAC for VSG Inertia/Damping Control: A Reproduction Study on the ANDES Kundur 4-Bus System" would land better.
- **Section V.C heading "Triangulation: framework decoration"** uses the word "decoration" as an established noun. Construct is interesting but informal for IEEE prose; consider "framework redundancy" or "architectural over-specification."
- No personal attacks on Yang et al. — author maintains professional distance throughout.

## 8. Preliminary Editorial Decision: Major Revision

**Reasons:**

1. The contribution is real and well-instrumented (decorative MARL on phasor backend; bug-fix methodology; pre-registered sensitivity gate), but the headline "tied with adaptive" claim sits on n=5 with Gate A3 fired — by the author's own pre-registered standard, this is underpowered for definitive direction claims.
2. Reframing from "Yang 2023 doesn't reproduce" to "MARL gains may be backend-dependent on phasor models" is necessary for TPWRS fit and is achievable without new science.
3. Project deviations (Table II) materially undermine the cleanest interpretation of the reversed ratio. Either close some deviations or downgrade the §V.A attribution.
4. Mixed-provenance figures need to be regenerated end-to-end at p_cf=0.1 or removed.
5. Adaptive baseline needs a tighter sweep before the tie claim can stand.

**Must-fix items for revision (5):**

1. **Run Tier-B n=10 on DDIC and adaptive** to resolve Gate A3 and produce non-overlapping or definitively-overlapping CIs.
2. **Regenerate Figs 2, 4, 5 at p_cf=0.1** or move them to an appendix with stronger provenance disclaimers.
3. **Strengthen the adaptive baseline tuning** — at minimum a 10×10 K-grid or a documented optimization procedure.
4. **Reframe title and §V.A** to "backend-dependent MARL performance" rather than "MARL is decorative." The latter overgeneralizes from a single (Kundur, ANDES, n=5) configuration.
5. **Add a second-topology pilot** (NE39 in repo) — even an n=3 pilot showing whether decoration replicates on NE39 would dramatically strengthen significance.

## 9. Comments to Authors

This is a thoughtfully instrumented and statistically honest reproduction study. The pre-registered sensitivity gate (§IV.H) and the n=5 confirmation at f_high are exemplary; the explicit labeling of WARMSTART_WORSE and DECORATIVE_CONFIRMED rather than narrative softening is the right scientific posture.

That said, the manuscript at present is one revision away from a TPWRS-publishable contribution. The central scientific issue is that "decorative MARL on phasor backends" is your most original and most generalizable finding, but the manuscript currently leads with "Yang 2023 does not reproduce." Reframing the title and Introduction around backend-dependence — with Yang 2023 as a motivating reference, not a target — would clarify the contribution and improve TPWRS fit substantially.

The empirical concerns are concrete: n=5 with σ/μ=22% and Gate A3 firing means your headline tie claim does not yet meet your own pre-registered standard. Tier-B n=10 is needed. Three of five main figures still use legacy p_cf=0.0 data even though the comm-fail bug-fix is one of your stated contributions; please regenerate end-to-end at p_cf=0.1. The adaptive baseline tuning (§VI bullet 2) is too thin to support the tie claim — please run a denser K-grid.

A second-topology pilot on NE39 (which I understand is available in your repository) would dramatically strengthen the external validity of the backend-dependence claim. Even an n=3 pilot showing whether the decoration phenomenon replicates would change the significance from single-system observation to a tested hypothesis.

The deviations table (Table II) is honest but raises a question you do not currently address: how much of the reversed ratio is backend-linearity vs. the 100×/50×/20× tuning differences? Please either close some deviations or explicitly downgrade the §V.A attribution.

## 10. Confidential Comments to Editors

- **Integrity:** No flags. The author is admirably forthcoming about bugs, provenance issues, and limitations. The acknowledgment that test-set asymmetry shrunk a previously claimed 65% margin to 9% (§III.D) is the kind of disclosure most authors would bury.
- **Conflicts:** The submission critiques a prior TPWRS paper (Yang et al. 2023). Standard practice: avoid Yang et al. as referees; otherwise no conflict.
- **Strategic note:** This is a useful manuscript for TPWRS *if* reframed as a methodological lesson about backend-dependence in MARL claims. As a referendum on a specific prior paper, it is a poor fit.
- **Outcome forecast:** With Tier-B n=10, second-topology pilot, regenerated figures, and reframing, this becomes an Accept with Minor Revisions in round 2. Without those, the major-revision verdict will likely become Reject in round 2.
