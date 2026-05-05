# Devil's Advocate Review — Andes DDIC Reproduction

**Paper:** Wei, "An Honest Reproduction of Multi-Agent SAC for VSG Inertia/Damping Control..." (commit 8f35406)
**Reviewer role:** Devil's Advocate (Reviewer 5 of 5)
**Date:** 2026-05-05
**Final Severity:** SIGNIFICANT CONCERNS
**Recommendation:** Major Revision

---

## Section 1: Strongest Counter-Argument (283 words)

The paper's core thesis — that multi-agent SAC is "decorative" — is built on a confounded experimental design that cannot distinguish between two hypotheses: (H1) the multi-agent architecture adds no value for VSG control, or (H2) the multi-agent architecture adds no value specifically on a phasor-equilibrium backend with 100x reweighted rewards and 20x narrowed action ranges. The paper tests H2 but presents its conclusions as if it has tested H1.

The deviations from Yang 2023 are not incidental. PHI_F was increased from 100 to 10,000 (100x), PHI_D reduced from 1.0 to 0.02 (50x), and the action range narrowed by 20x. These are not minor calibration adjustments — they fundamentally reshape the optimization landscape. The paper's own sensitivity analysis (Section IV.H) demonstrates this: every perturbation within ±3x degrades cum-r_f by at least 25%, and the system sits on what the authors themselves call "a sensitive ridge." The DDIC numbers are "conditional on the specific hyperparameter point" (Claim 9).

The paper then compares this highly-tuned DDIC against an adaptive baseline with only 25 grid-searched gain combinations (5x5 K-grid), declares them "tied," and concludes the multi-agent framework is decorative. But a proportional-derivative controller on a linearized phasor system is expected to be near-optimal by construction — the system dynamics are approximately linear (the paper admits this in Section V.A). Testing multi-agent RL on a nearly-linear system and finding no advantage over a linear controller is a tautology about the test system, not a finding about the architecture.

The word "decorative" — used 6 times in the paper — is rhetorical framing, not a scientific conclusion. The evidence supports at most: "on this system, with these deviations, the multi-agent advantage is not statistically detectable at n=5."

---

## Section 2: Issue List

### [CRITICAL] C1: Confounded experimental design makes "decorative" claim unattributable

- **Dimension**: overgeneralization / missing control
- **Location**: Title, Abstract (lines 37-66), Section IV.G (lines 438-471), Conclusion (lines 769-808)
- **Argument**: The paper changed the simulator (ANDES vs Simulink), the reward weights (100x on PHI_F, 50x on PHI_D), the action range (20x narrower), and added/removed reward terms (PHI_ABS). Each could independently explain the null result. Without ablating which deviation is responsible, "multi-agent framework is decorative" is unattributable.
- **Confidence**: HIGH
- **Why CRITICAL**: Headline claim ("decorative") is logically unsupported if null result could be caused by any single deviation rather than the architecture itself.
- **Fix**: Replace "decorative" with "not statistically advantageous on this system and configuration." Add explicit discussion of confounding. Scope the conclusion.

### [CRITICAL] C2: Shared-parameter baseline claim at n=3 is underpowered

- **Dimension**: unfounded claim / cherry-data
- **Location**: Section IV.G (Table VI, lines 438-471), Abstract line 55-56
- **Argument**: DECORATIVE_CONFIRMED rests on shared-param (n=3, mean -1.069) vs DDIC (n=3, mean -1.156). With n=3, SE of mean is large enough that 7.5% difference is well within noise. Paper's own Gate A3 fires at n=5 for DDIC-adaptive (std/mean = 22%); at n=3 worse. Calling this "DECORATIVE_CONFIRMED" from n=3 is premature. Even DDIC baseline used 5 seeds because 3 were insufficient.
- **Confidence**: HIGH
- **Why CRITICAL**: If shared-parameter result is not statistically robust, "three converging lines of evidence" collapse to two (dominance + warmstart), and warmstart only has n=3 too.
- **Fix**: Run shared-parameter at n=5 (matching DDIC). Report overlapping CIs explicitly. Downgrade "DECORATIVE_CONFIRMED" label until n=5 data available.

### [MAJOR] M1: The "1/5 budget" claim for shared-parameter is misleading

- **Dimension**: unfounded claim
- **Location**: Abstract line 55, Section IV.G, Conclusion
- **Argument**: Paper claims shared-param SAC trains at "1/5 the budget." This refers to 1 set of NN parameters vs 4 sets. However, the shared agent receives 4x the transitions per timestep (all 4 agents' experiences feed single buffer) and performs 40 updates per episode (10 epochs x 4 agents). In DDIC each agent gets 10 updates on its own transitions. Shared policy receives comparable or greater gradient signal per wall-clock episode. "1/5 budget" framing implies dramatic efficiency when actual compute savings are modest (fewer parameters, not fewer gradient updates).
- **Confidence**: HIGH
- **Fix**: Replace "1/5 budget" with "1/4 the network parameters" or "a single actor-critic" and clarify data throughput per episode is equivalent.

### [MAJOR] M2: Sensitivity sweep avoids 2D combinations that could rescue multi-agent

- **Dimension**: cherry-picking / missing control
- **Location**: Section IV.H (lines 514-636)
- **Argument**: Sensitivity sweep is single-axis only: PHI_F varied while PHI_D fixed, vice versa. No 2D probe (PHI_F x PHI_D). Interaction could produce region where multi-agent SAC outperforms shared-parameter — paper cannot rule this out. Sweep tests 6 perturbations of DDIC baseline but does not test whether same perturbations affect shared-parameter or adaptive differently. If all three controllers degrade equally, sweep shows system sensitivity, not architecture-specific sensitivity.
- **Confidence**: MEDIUM
- **Fix**: Acknowledge single-axis limitation. Test at least one 2D combination. Run sweep on shared-parameter baseline.

### [MAJOR] M3: Adaptive baseline is undertested

- **Dimension**: missing control
- **Location**: Section IV.A (Table IV), Limitations (lines 749-753)
- **Argument**: Adaptive baseline uses single (K_H=10, K_D=400) from a 5x5 grid search. Acknowledged as heuristic. But DDIC used 500 episodes x 5 seeds to find its operating point, while adaptive got 25-point grid. If adaptive optimized with same compute (e.g., Bayesian optimization over continuous K_H, K_D), might substantially outperform DDIC.
- **Confidence**: MEDIUM
- **Fix**: Acknowledge asymmetric tuning effort. Either invest more in adaptive tuning or discuss implications.

### [MAJOR] M4: The paper compares absolute reward magnitudes between Simulink and ANDES

- **Dimension**: logic chain gap
- **Location**: Table V (lines 384-398), Section IV.C
- **Argument**: Table V presents DDIC/no-control and DDIC/adaptive ratios side by side (paper: 0.53, 0.62; this work: 0.30, 1.12). But ratios on different reward scales with different weights (PHI_F=100 vs 10000), different action ranges, different simulators. Ratio is not a dimensionless performance index that transfers across setups. "Reversal" (0.62 to 1.12) could simply reflect reward function changed so much that ratio is meaningless.
- **Confidence**: HIGH
- **Fix**: Add explicit caveats that ratios are computed on incommensurable scales.

### [MINOR] m1: Figure provenance mixing

- **Location**: Figures 2, 4, 5 (lines 285-298, 419-425, 680-689)
- **Argument**: 3 of 5 figures use legacy p_cf=0.0 data while all numerical claims use corrected p_cf=0.1. Provenance caveats honest but visual-textual inconsistency weakens paper.

### [MINOR] m2: Bootstrap CI methodology

- **Location**: Section IV.B (lines 354-370)
- **Argument**: Bootstrap CIs on n=5 seed-level means bootstrap over 50 per-episode cum_rf values that are correlated (same trained policy across episodes). CI width depends on within-seed episode variance, not cross-seed variance.

### [MINOR] m3: Settled/50 column is always 0

- **Location**: Table IV (line 330)
- **Argument**: "Settled/50" zero for all controllers, meaning settling never occurs. Adds no discriminative information; suggests settling tolerance (0.005 Hz) too tight.

---

## Section 3: Ignored Alternative Explanations

### Claim 1: Multi-agent framework is decorative
- **Alt. 1**: ANDES phasor-equilibrium produces nearly-identical local frequency observations across all 4 buses (tight coupling), making multi-agent observation diversity irrelevant. On a more electrically distant network (e.g., NE39), multi-agent could still provide value.
- **Alt. 2**: 20x narrower action range constrains agents to operate in regime where individual specialization provides no benefit. At paper's original action range, agent-specific policies might diverge productively.
- **Alt. 3**: Training at 500 episodes vs paper's 2000 episodes may not allow sufficient exploration for multi-agent coordination to emerge. Authors dismiss (§VI bullet 3) but only cite checkpoint trajectory from single seed.

### Claim 2: DDIC/adaptive ratio reversal
- **Alt. 1**: Ratio reversal is artifact of reward function change (100x PHI_F), not backend. Under PHI_F=100, r_f was gradient-invisible (1.52% share); both DDIC and adaptive would have had different relative performance.
- **Alt. 2**: Adaptive controller (K_H * |omega_dot|, K_D * |Delta_omega|) happens to be well-matched to ANDES phasor dynamics specifically. Different adaptive law on Simulink might also tie with DDIC.

### Claim 3: PHI_F=100 produces gradient-invisible frequency signal
- **Alt. 1**: Gradient invisibility could be artifact of ANDES backend's smaller frequency deviation magnitudes (5-7x smaller per §IV.D), not reward weight itself. On Simulink, PHI_F=100 with larger frequency deviations could produce adequate gradient signal.
- **Alt. 2**: Paper uses PHI_ABS=0 (disabled). If PHI_ABS>0 used alongside PHI_F=100, might rescue frequency signal without 100x PHI_F deviation.

### Claim 4: Single-agent dominance is structural
- **Alt. 1**: Dominance could be artifact of independent random initialization combined with ring communication topology. With different topology (e.g., all-to-all), dominance might not emerge.
- **Alt. 2**: Dominance metric (ablation share) may be misleading. Agent a1 "dominating" does not necessarily mean others useless — they might provide essential supporting roles invisible in ablation metric.

### Claim 5: Sensitivity sweep confirms baseline is local minimum
- **Alt. 1**: Sweep tested only 6 perturbations on 3 axes. Hyperparameter space is at least 5-dimensional (PHI_F, PHI_D, PHI_H, action range, learning rate). Local minimum on 3 of 5 axes does not guarantee local minimum in full space.
- **Alt. 2**: n=5 confirmation at f_high (PHI_F=30000) showed seed-42 was optimistic outlier (-1.488 vs n=5 mean -1.735). By analogy, baseline seed-42 (-1.191) might also be outlier relative to "true" optimum nearby.

---

## Section 4: Missing Stakeholder Perspectives

1. **Yang et al. (original authors)**: Their rebuttal absent. They would likely argue: (a) entire experiment is on different simulator with dramatically different hyperparameters, making negative conclusions about their architecture invalid; (b) action range narrowing 20x eliminates regime where multi-agent coordination provides value; (c) ANDES phasor model ignores electromagnetic transients where their EMT-based Simulink model shows multi-agent advantage.

2. **Power system practitioners**: Paper focuses on cum-r_f and max-Delta-f. Practitioner would also want: inertia distribution fairness across ESS units, ramping behavior, interaction with existing governor controls, performance under sequential disturbances.

3. **MARL theory community**: Paper uses "decorative" in way that could be generalized as "MARL doesn't work for cooperative control" — but MARL community would note that CTDE architectures, communication protocols (QMIX, MAPPO), and credit assignment mechanisms were never tested. Paper tests only simplest possible multi-agent setup (fully independent learners) and declares multi-agent decorative.

4. **ANDES developer community**: Paper attributes limitations to "backend linearity" without characterizing what ANDES actually models vs what it omits relative to Simulink EMT. ANDES developers (Cui et al.) would want comparison to be precise.

---

## Section 5: Cherry-Picking / Confirmation-Bias Detection

1. **Selective reporting of seed-44**: Abstract and multiple sections highlight seed-44 as "best DDIC" (cum-r_f = -0.914, Table IV). Cherry-picks best of 5 seeds. Paper also uses seed-42 for single-seed sweeps (closest to 5-seed mean). seed-42 for sweeps defensible (representative); highlighting seed-44 selectively creates impression of DDIC being better than mean.

2. **Evaluation metric selection**: cum-r_f primary metric is reward-formulation-specific (dependent on PHI_F, PHI_D weightings). Not physics-based metric like max frequency deviation, ROCOF, or energy-not-served. cum-r_f makes DDIC/adaptive comparison depend on reward function rather than physical performance. On max-Delta-f (physics metric), DDIC actually loses to adaptive by 9-11% (Claim 3) — reported honestly but not emphasized.

3. **Pre-registered gates were not softened**: hparam sensitivity gates (std < 0.265) pre-registered and reported as FAIL without modification. Commendable.

4. **Sensitivity sweep design avoids most dangerous test for decorative claim**: 2D probe of (PHI_F x PHI_D) at multiple points + running shared-parameter at each point would directly test whether there exists hyperparameter combination where DDIC outperforms shared-parameter. Paper only tests decorative claim at single hyperparameter point. If DDIC outperforms shared-param at PHI_F=3000, decorative claim fails — but never tested.

5. **DDIC and shared-param comparison uses n=3 while DDIC-vs-adaptive uses n=5**: Asymmetry suspicious. Authors knew n=3 insufficient for DDIC-adaptive (extended to n=5). But decorative claim — arguably paper's strongest contribution — rests on weaker n=3.

---

## Section 6: Logic Chain Validation

### Claim 1: DDIC is decorative
- **Data**: DDIC cum-r_f = -1.186 (n=5); shared-param = -1.069 (n=3); bootstrap CIs overlap.
- **Leap 1**: "Overlap at n=3" equated with "no difference." Absence of evidence ≠ evidence of absence. Equivalence test (TOST) not performed.
- **Leap 2**: "Matches within 7.5%" declared as "equivalent." 7.5% gap in direction favoring shared-param, not DDIC.
- **Leap 3**: From "shared-param matches DDIC on this system" to "multi-agent framework is decorative" omits that system was modified substantially.

### Claim 2: DDIC/adaptive ratio reversal suggests learning advantage doesn't transfer
- **Data**: Paper ratio 0.62; this work 1.12.
- **Leap**: Ratios on different reward scales, different simulators. "Reversal" could mean reward landscape changed, not architecture lost capability.
- **Missing**: No discussion of whether ratio is even valid comparison metric across 100x weight changes.

### Claim 3: Sensitivity sweep confirms local minimum
- **Data**: 6 perturbations, all worse; f_high confirmed worse at n=5.
- **Leap**: "Local minimum within ±3x" valid for tested axes. But "baseline is the local minimum" implies it was found by optimization, when in fact found by Phase 2 manual calibration.
- **Missing**: No comparison of sensitivity between DDIC and shared-param. If shared-param equally sensitive, it's system property, not architecture property.

### Claim 4: PHI_F=100 is gradient-invisible
- **Data**: r_f weighted share = 1.52% at PHI_F=100.
- **Sound**: Most solidly supported claim in paper.
- **Minor caveat**: 1.52% measured at PHI_ABS=50 and PHI_D=4.0, not paper's PHI_D=1.0 with PHI_ABS=0. At PHI_D=1.0 r_d share would be smaller, potentially raising r_f share above 5% threshold.

### Claim 5: Single-agent dominance is structural
- **Data**: Agent a1 shares of 54.6-74.7% across 5 seeds; warmstart redistributes but doesn't improve.
- **Sound**: Consistency across seeds is strong evidence of structural dominance.
- **Caveat**: "Structural" could mean "structural to ANDES Kundur network topology" rather than "structural to multi-agent architecture."

---

## Section 7: "So What?" Test

**If decorative claim is true:**
- **Power-system practitioners**: Minimal impact. Practitioners would use MPC or adaptive control anyway; multi-agent RL for 4-bus systems was never close to deployment. Paper confirms what most practitioners already believe: RL is overkill for small, well-characterized systems.
- **ML researchers**: Moderate interest as negative result, but confounded design (different simulator, different hyperparameters) limits generalizability. ML researcher would want test on original Simulink to confirm.
- **TPWRS readership**: Reproduction effort and evaluation bug discovery valuable. Decorative claim provocative but would need Simulink-side replication to be compelling.

**Could this paper be 2 pages instead of 11?**
Core intellectual contribution could indeed be compressed: "We reproduced Yang 2023 on ANDES instead of Simulink. With necessary hyperparameter adjustments, DDIC ties adaptive at n=5. One agent dominates. A single shared-parameter actor matches DDIC." That is a 2-page technical note. Remaining 9 pages are diagnostic narrative (Phases 1-10) — valuable as research log but not as publication contribution. Paper is honest but padded.

---

## Section 8: Observations (Non-Defects)

1. **Commendable transparency**: Paper remarkably honest about limitations, evaluation bugs, provenance caveats, and conditional nature of claims. Rare and valuable in reproduction studies.
2. **Pre-registered gates**: hparam sensitivity gates pre-registered and reported without modification, even when producing inconvenient results (all FAIL). Good scientific practice.
3. **Three evaluation bugs identified**: Discovery and fix of same-class evaluation bugs is genuine contribution, regardless of decorative claim.
4. **Code released**: Complete training scripts, evaluators, audit reports released. Reproducibility section thorough.
5. **Bootstrap CI methodology correctly implemented**: Verified — percentile bootstrap with n_resample=1000, seed=7919 for reproducibility.
6. **Paper correctly does not anchor absolute cum-r_f to paper's -8.04**: Authors recognize values on different scales (Table V note).

---

## Section 9: Final Verdict

- **Overall severity**: SIGNIFICANT CONCERNS
- **Recommendation**: Major Revision

Two CRITICAL issues:
- **C1**: confounded experimental design means "decorative" label cannot be attributed to architecture vs experimental setup
- **C2**: strongest evidence for "decorative" (shared-param comparison) rests on n=3 seeds, which paper itself acknowledges insufficient power for DDIC-adaptive comparison but does not extend for decorative comparison

These do not invalidate underlying data (which appears sound), but they invalidate headline framing.

**DA finds CRITICAL issues; Editorial Decision cannot be Accept (per academic-paper-reviewer skill IRON RULE #4).**

Path to acceptance requires:
1. Reframing "decorative" to "not advantageous on this system and configuration"
2. Extending shared-parameter to n=5
3. Explicit discussion of confounding between simulator change, reward reweighting, and action range narrowing
4. Either running sensitivity sweep on shared-parameter baseline or acknowledging this gap
5. Reducing paper to length appropriate for its contribution (technical note or short paper)
