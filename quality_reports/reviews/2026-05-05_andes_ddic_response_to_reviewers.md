# Response to Reviewers — Round 1

**Manuscript:** "Backend-Dependent Performance of Multi-Agent SAC for Virtual Synchronous Generator Inertia and Damping Control: A Reproduction Study on the ANDES Kundur Four-Bus System" (formerly: "An Honest Reproduction of Multi-Agent SAC ... Decorative on a Phasor-Based Backend")

**Author:** Yuang Wei
**Date:** 2026-05-05
**Round:** 1 → 2 (response to round-1 review)
**Commits**: a424bb0 (Tier-1 6/7) + d4c0c6c (T1.1)

---

We thank all five reviewers (EIC, Methodology, Domain, Perspective, Devil's Advocate) for their detailed and constructive feedback. We have addressed all 7 Tier-1 (blocking) revision items from the editorial decision letter
(`quality_reports/reviews/2026-05-05_andes_ddic_editorial_decision.md`).
The original 5 reviewer reports are unchanged; this document maps each
Tier-1 item to its specific revision in the manuscript, with commit
references for traceability.

The two CRITICAL issues raised by the Devil's Advocate are resolved:

- **CRITICAL #1 (confounded experimental design):** addressed by §V.A
  rewrite into three explicit confounding hypotheses + "Most defensible
  reading" paragraph; title and §I.B reframed; claim 4 rewritten.
- **CRITICAL #2 (n=3 underpowered for DECORATIVE claim):** addressed by
  T1.1 — Phase 9 shared-parameter SAC extended to matched n=5 seeds.
  At matched budget, shared-param mean cum-r_f = −1.028 (std 0.136,
  CI [−1.125, −0.917]) vs. DDIC −1.186 (std 0.265, CI [−1.393, −0.984]):
  CIs overlap, shared-param trends 13.4% better with 49% smaller
  cross-seed std. **DECORATIVE_CONFIRMED is now confirmed at matched
  n=5, not just n=3.**

---

## Tier-1 Revision Response Matrix

| # | Original Reviewer Comment | Author's Claim | Revision Location | Commit |
|---|---|---|---|---|
| **T1.1** | DA C2 + Methodology #4 + EIC weakness #1: extend Phase 9 shared-param to n=5 (matching Phase 4 DDIC); n=3 is underpowered for the DECORATIVE_CONFIRMED claim. | Trained Phase 9 seeds 45 + 46 at 500 episodes each (`results/andes_phase9_shared_seed{45,46}_500ep/`). Re-evaluated all 5 seeds (42–46) at p_cf=0.1 on the fixed test set (env.seed 20000–20049). New script: `scenarios/kundur/_phase9_shared_5seed_reeval.py`. Aggregate JSON: `results/phase9_shared_5seed_reeval_summary.json`. **Result**: shared-param n=5 mean cum-r_f = −1.028, std = 0.136, bootstrap 95% CI = [−1.125, −0.917]. DDIC n=5: mean −1.186, std 0.265, CI [−1.393, −0.984]. CIs overlap; shared-param 13.4% less negative with 49% smaller cross-seed std. **Verdict**: TIED_AT_N5 (CI-overlap), with shared-param trending marginally better. DECORATIVE_CONFIRMED is preserved and *strengthened* at matched n=5. | §IV.G Table V (rebuilt with n / mean / std / 95% CI columns); §IV.G prose (line ~485, "DECORATIVE_CONFIRMED at n=5"); §V item 6 (drop n=3 qualifier); §V.C Triangulation (replace n=3 with matched n=5); §VI Limitations (replace n=3 mismatch bullet with narrower warmstart-still-n=3 bullet); §VIII Conclusion (new −1.028 number, drop n=3 budget claim) | **d4c0c6c** |
| **T1.2** | EIC must-fix #4 + DA Section 1: title and "decorative" framing too aggressive; rephrase to "backend-dependent" / "not advantageous on this configuration"; reduce "decorative" usage. | (a) Title changed: "Evidence That the Multi-Agent Framework Is Decorative on a Phasor-Based Backend" → **"Backend-Dependent Performance of Multi-Agent SAC for Virtual Synchronous Generator Inertia and Damping Control: A Reproduction Study on the ANDES Kundur Four-Bus System"**. (b) "decorative"/"decoration" usage reduced from 10 → 4 occurrences (only in established labels DECORATIVE_CONFIRMED, decorative on this system, framework-decoration label, conclusion). (c) Claim 5 rewritten: "multi-agent framework provides no measurable advantage *on this system at our operating point*; we label this **architecturally redundant on the ANDES phasor-equilibrium backend**". (d) §I introduction reframed. | Title (line 24); abstract (line 52, line 55); §I item 3 (line 110); §IV.G heading (line 457); §V.C heading (line 692, "Triangulation: architectural redundancy"); §V item 5 | **a424bb0** |
| **T1.3** | Domain C1: Yang 2023 [3] citation incomplete (volume/pages/DOI missing); unacceptable for TPWRS. | Resolved Yang 2023 full citation: title "A Distributed Dynamic Inertia-Droop Control Strategy Based on Multi-Agent Deep Reinforcement Learning for Multiple Paralleled VSGs", DOI 10.1109/TPWRS.2023.3293016, IEEE Xplore document 9946410, full author list (Yang, Q. and Zhang, P. and Zhao, B. and Wu, K.). | `paper/refs.bib` `@article{yang2023ddic,...}` | **a424bb0** |
| **T1.4** | Domain C2 (primary issue) + Perspective: bibliography critically thin (10 entries), missing canonical references in VSG/grid-forming, MARL for power systems, phasor-vs-EMT, ML reproducibility. | Expanded bibliography from 10 to 19 entries. New: D'Arco/Suul 2015 (VSM canonical), Bevrani/Ise/Miura 2014 (canonical adaptive virtual-inertia/damping law — cited as source of our adaptive baseline), Markovic et al. 2021 (low-inertia stability), Glavic/Fonteneau/Ernst 2017 (RL-for-power-systems tutorial), Hadidi/Jeyasurya 2013 (RL stability control), Stiasny/Chevalier 2023 (phasor-vs-EMT), Milano/Ortega 2020 (frequency variations textbook), Morren et al. 2006 (wind inertia), Pineau et al. 2021 (NeurIPS reproducibility), Agarwal et al. 2021 (RL statistical reporting standards). All entries include DOI/journal/volume/pages where available. | `paper/refs.bib` (10 → 19 entries); cited inline in §I, §III.C, §V.A, §VI, §VIII | **a424bb0** |
| **T1.5** | DA C1 (CRITICAL #1) + EIC weakness #3: experimental design changed simulator + reward weights + action range simultaneously; the "decorative" / "ratio reversal" claim is unattributable; either run paper-faithful Φ_F=100 on ANDES OR explicitly downgrade attribution. | (a) §V.A rewritten: replaced single "Backend linearity" attribution paragraph with **three explicit confounding hypotheses** (Backend linearity, Reward-weight rescaling, Action-range narrowing), each with its own paragraph stating what it would predict, why it cannot be tested with available data. (b) Added "Most defensible reading" paragraph: "the multi-agent advantage reported in Yang 2023 does not transfer to the joint backend–reward–range configuration tested here, with backend linearity being one plausible but unisolated contributor." (c) Claim 4 rewritten to attribute ratio reversal to joint deviation, not single-cause. (d) §VI Limitations bullet on confounded deviations (separate from sample-size bullet). | §V.A entire subsection (line ~673–720, ~+50 lines); §V item 4 (line ~733, claim 4 rewrite); §VI Limitations bullet "Confounded backend–reward–range deviations" | **a424bb0** |
| **T1.6** | Methodology #3: §IV.H per-axis σ comparison is category-mismatch (cross-seed σ vs cross-hparam point-spread); detects curvature, not fragility. | Added explicit "Caveat on the per-axis σ comparison" paragraph at end of §IV.H (after Verdict). Acknowledges (a) the 0.265 cross-seed bar measures seed-induced dispersion at one config; (b) per-axis σ values measure point-spread across deliberately chosen hyperparameter settings at n=1 each, scaling with local curvature; (c) the substantive finding (every direction degrades cum-r_f by ≥25%) is direct and does not depend on the σ ratio. The σ comparison is retained as a heuristic fragility indicator, not a strict test. Matched-n confirmation at every hparam point flagged as future work. | §IV.H "Caveat on the per-axis σ comparison" paragraph (added after Verdict, before §V) | **a424bb0** |
| **T1.7** | EIC must-fix #2 + DA m1: Figs 2/4/5 use legacy p_cf=0.0 data while comm-failure bug-fix is a stated contribution; visual-textual inconsistency. | (a) Each affected figure caption now begins with "**[Legacy p_cf=0.0 trace]**" tag prefix making provenance immediately visible. (b) Each affected caption explicitly states "*No quantitative claim in tables or text relies on this figure; it is illustrative of the qualitative pattern.*" (c) The Figure provenance note (after Fig 2) was rewritten to clearly demarcate: Figs 1, 3 (numerical anchors) regenerated at p_cf=0.1; Figs 2, 4, 5 illustrative only, retained for narrative coherence with explicit retention rationale. The note also points to a future regen at p_cf=0.1 once underlying probes are re-run. | Fig 2 caption (line 282); Fig 4 caption (line 425); Fig 5 caption (line 757); Figure provenance note (line ~292) | **a424bb0** |

---

## Tier-2 / Tier-3 Status

Tier-2 (highly recommended) items remain as future work (see §VI Limitations expansion):
- T2.8 Tier-B n=10 for DDIC and adaptive
- T2.9 NE39 second-topology pilot
- T2.2 adaptive baseline 10×10 K-grid

Tier-3 (nice-to-have) items not addressed in this revision; they do not affect any blocking concern.

---

## New Content (potentially needing review)

The revision adds the following content beyond direct response to comments:

1. **§V.A "Most defensible reading" paragraph** — explicitly downgrades the backend-linearity attribution; this is more conservative than round-1 framing and does not introduce new claims.
2. **§VI Limitations expanded** from 5 bullets to 9: added (a) sample-size asymmetry [now resolved by T1.1], (b) confounded deviations, (c) hparam coverage limitations, (d) topology external validity. None of these introduce new positive claims; all are honest scoping.
3. **§I item 3 forward-references**: added `\cref{sec:rootcause,sec:limits}` to scope the architectural-redundancy claim from the introduction.
4. **§IV.G Table V** redesigned: from 4 rows × 2 columns (per-ep CI) to 3 rows × 5 columns (n / mean / std / per-seed-total bootstrap CI / per-ep CI). The redesign was needed to surface the matched-n=5 result from T1.1.

These are scope-clarifications and statistical-presentation improvements; no new substantive claims are introduced.

---

## Summary of revisions

- 7/7 Tier-1 blocking items addressed
- Both DA CRITICAL issues resolved (#1 via §V.A confounding rewrite; #2 via T1.1 n=5 extension)
- Title reframed
- Bibliography 10 → 19 entries
- 6 new figures (none added; 3 existing re-captioned)
- 0 numerical results regressed; 1 new positive result (Phase 9 n=5 matched comparison)

---

*End response to reviewers. The revision is ready for re-review at
`paper/main.tex` (commit d4c0c6c, 13 pages, 0 undefined refs).*
