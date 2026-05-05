# EIC Re-Review (Verification) — Round 2

**Manuscript:** "Backend-Dependent Performance of Multi-Agent SAC for VSG Inertia/Damping Control: A Reproduction Study on the ANDES Kundur Four-Bus System" (commit d4c0c6c)
**Reviewer:** EIC (verification mode)
**Date:** 2026-05-05

## R&R Traceability Matrix

| # | Original Comment (Tier-1) | Author's Claim | Verified? | Quality | Notes |
|---|---|---|---|---|---|
| **T1.1** | DA C2: extend Phase 9 shared-param from n=3 to n=5; n=3 underpowered | Trained seeds 45+46; mean −1.028 / std 0.136 / CI [−1.125, −0.917]; verdict TIED_AT_N5, shared-param trends 13.4% better with 49% smaller σ | FULLY_ADDRESSED | Excellent | JSON `phase9_shared_5seed_reeval_summary.json` reports `five_seed_total_mean: −1.0277`, `std_n1: 0.1358`, `bootstrap_ci: [−1.1250, −0.9173]`, `verdict: TIED_AT_N5`, `pct: 13.37`, `ci_overlap: true`. Paper Table V (line 484) and §IV.G prose (lines 491–507) match the JSON to 3 sig figs. Abstract (lines 57–59) states "$-1.028$ vs. DDIC $-1.186$, overlapping bootstrap 95% CIs, 48% smaller cross-seed std" — exactly aligned. |
| **T1.2** | Title + "decorative" framing too aggressive | Title reframed to "Backend-Dependent Performance…"; "decorative" usage 10→4; claim 5 rewritten as "architecturally redundant on the ANDES phasor-equilibrium backend" | FULLY_ADDRESSED | Excellent | Title (lines 23–25) is the recommended EIC wording verbatim. `grep -i decorat` returns only **3** occurrences (lines 59, 459, 499) — all are the technical label `DECORATIVE_CONFIRMED`, not editorial framing. This is *better* than the claimed 4. Claim 5 (line 833) reads "no measurable advantage on this system at our operating point"; intro item 3 (lines 117–120) uses "architecturally redundant on the ANDES phasor-equilibrium backend" as labeled in claim. |
| **T1.3** | Yang 2023 [3] DOI/volume/pages missing | DOI 10.1109/TPWRS.2023.3293016 added | FULLY_ADDRESSED | Good | `refs.bib` lines 6–15 contain DOI exactly as claimed. Note: volume/number/pages still missing (only `year` + `doi` + `note`); for TPWRS final accept the article should resolve to volume 38/issue/page once published. Acceptable for revision. |
| **T1.4** | Bibliography 10 → ≥15 entries (preferably 25–30) | Expanded to 19 entries | FULLY_ADDRESSED | Good | Verified count of 19 `@article/@inproceedings/@book` entries via grep. All ten claimed new entries present: `darco2015vsm`, `bevrani2014vsg`, `markovic2021lowinertia`, `glavic2017rl`, `hadidi2013ml`, `stiasny2023phasor`, `milano2020frequency`, `morren2006wind`, `pineau2021reproducibility`, `agarwal2021precipice`. Meets ≥15 floor; sits under the 25–30 ideal but acceptable for a 13-page reproduction study. |
| **T1.5** | DA CRITICAL #1: rewrite §V.A into explicit confounding hypotheses; reframe claim 4 | §V.A rewritten with 3 explicit hypotheses + "Most defensible reading"; claim 4 attributes ratio reversal to joint deviation | FULLY_ADDRESSED | Excellent | §V.A (lines 695–765) has four `\paragraph{}` blocks: "Backend linearity (hypothesis 1)" line 707, "Reward-weight rescaling (hypothesis 2)" line 721, "Action-range narrowing (hypothesis 3)" line 732, "Most defensible reading" line 757. Each hypothesis paragraph states what it predicts and why it cannot be tested. "Most defensible reading" downgrades to "one plausible but unisolated contributor" (line 762). Claim 4 (lines 821–832) explicitly uses "joint effect of three uncontrolled factors". §VI Limitations bullet "Confounded backend–reward–range deviations" (lines 880–891) added. |
| **T1.6** | Methodology #3: §IV.H per-axis σ comparison is category-mismatch | "Caveat on the per-axis σ comparison" paragraph added | FULLY_ADDRESSED | Good | §IV.H caveat paragraph at lines 675–691 explicitly acknowledges (a) cross-seed σ vs (b) point-spread across hparam settings are different dispersion types, (c) substantive ≥25% finding is direct and does not depend on σ ratio. Retains comparison as heuristic; flags matched-n future work. |
| **T1.7** | Figs 2/4/5 use legacy p_cf=0.0 data | "[Legacy p_cf=0.0 trace]" tag prefix on each caption + "no quantitative claim relies" disclaimer; provenance note rewritten | FULLY_ADDRESSED | Excellent | Tag verified at lines 283 (Fig 2), 435 (Fig 4), 781 (Fig 5). All three captions explicitly state "No quantitative claim in tables or text relies on this figure". Figure provenance note (lines 297–316) cleanly demarcates anchor figures (1, 3, regenerated at p_cf=0.1) vs illustrative figures (2, 4, 5). |

## CRITICAL Issue Verification

- **DA CRITICAL #1 (confounded design):** **RESOLVED.** §V.A no longer attributes the ratio reversal to a single backend-linearity mechanism. The three confounders are explicitly named, each is given a hypothesis paragraph, and the "Most defensible reading" downgrade explicitly states the multi-agent claim is scoped to "the joint backend–reward–range configuration tested here, with backend linearity being one plausible but unisolated contributor." Claim 4 (lines 821–832) and §VI Limitations bullet reinforce. Title reframed to "Backend-Dependent" matches the new framing.

- **DA CRITICAL #2 (n=3 underpowered):** **RESOLVED.** Phase 9 shared-param is now n=5 with bootstrap CI [−1.125, −0.917], matching the DDIC sample size. JSON `phase9_shared_5seed_reeval_summary.json` numerically backs the paper's −1.028 / 0.136 / [−1.125, −0.917] / TIED_AT_N5 claim to 3 sig figs. The DECORATIVE_CONFIRMED label is now defended at matched n=5 rather than asymmetric n=3 vs n=5.

## New Issues Introduced

1. **Internal inconsistency in claim 5 (LOW severity).** Lines 836–837 still state "A single shared-parameter policy with 1/4 the network parameters achieves equivalent performance **at n = 3**." This contradicts T1.1's extension to n=5 (which the same paragraph elsewhere correctly cites). Should read "at matched n = 5". Easy fix.
2. **Yang 2023 citation completeness (LOW severity).** DOI is present but volume/issue/pages absent in `refs.bib`. TPWRS production may auto-resolve; flag for proofs.
3. **§V.C "Triangulation" (line 809) appropriately notes the warmstart pilot remains at n=3.** Not a new issue, but acknowledges the remaining sample-size asymmetry honestly.
4. **No new positive claims introduced.** New "Most defensible reading" paragraph and §VI Limitations expansion are honest scoping, not novel claims.

## New Editorial Decision

**Minor Revision.**

## Reasoning

**On Tier-1 completion.** All 7 Tier-1 blocking items are FULLY_ADDRESSED with independent verification. The two Devil's Advocate CRITICAL flags — confounded design and n=3 underpower — are both genuinely resolved, not papered over. The §V.A rewrite is the strongest piece of revision: it does what the DA asked (acknowledges three confounders, declines to attribute to one) without retreating into evasive language. The "Most defensible reading" paragraph is exemplary intellectual honesty for a reproduction study. IRON RULE #4 no longer binds because no DA CRITICAL is NOT_ADDRESSED.

**On the headline statistical claim.** The JSON cross-check gives me high confidence in the n=5 numbers. Mean −1.028 (std 0.136, CI [−1.125, −0.917]) is reproduced to the third decimal in Table V. The verdict TIED_AT_N5 with shared-param trending 13.4% better and 49% smaller σ is now defensible — at matched seed budget the simpler architecture is at least as good, with materially less seed-to-seed dispersion. This strengthens (does not just preserve) DECORATIVE_CONFIRMED.

**On bibliography and framing.** 19 entries clears the TPWRS minimum-15 floor. Title reframe to "Backend-Dependent Performance…" is exactly the EIC's recommended wording. "Decorative" usage is now restricted to a single technical label (DECORATIVE_CONFIRMED) rather than editorial rhetoric — better than promised. Claim 5 ("architecturally redundant on the ANDES phasor-equilibrium backend") scopes the conclusion to the tested configuration.

**Why Minor not Accept.** Three small but real items remain: (a) the claim 5 internal inconsistency at lines 836–837 ("at n = 3" should be "at matched n = 5") is a load-bearing word in a load-bearing claim and must be corrected before press; (b) Yang 2023 volume/issue/pages should be filled in for TPWRS production; (c) a pass on the figure provenance note (line 312) to remove the "future revision should regenerate" hedge once the regen actually happens — or commit to deferring it as future work. None of these block publication; they are proofs-stage corrections.

**Forecast.** With these three items addressed in a Minor Revision pass (≤1 day author work), the paper meets TPWRS reproduction-study standard and is publishable. Tier-2 items (paired-t, Cohen's d, NE39 pilot, 10×10 K-grid) remain valuable but are explicitly future work, not blocking.
