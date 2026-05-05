# Reviewer 3 (Cross-Disciplinary, ML Reproducibility) — TPWRS Submission
**Manuscript:** "An Honest Reproduction of Multi-Agent SAC for Virtual Synchronous Generator Inertia and Damping Control: Evidence That the Multi-Agent Framework Is Decorative on a Phasor-Based Backend"
**Author:** Yuang Wei
**File:** `paper/main.tex` (838 lines, single-author, IEEEtran journal class)
**Date of review:** 2026-05-05
**Reviewer brief:** ML reproducibility / RL benchmark validity / negative-results norms; not a power-systems methodology review.

---

## Executive recommendation

**Major Revision**, with strong support for publication after revision. This is exactly the kind of submission the broader ML community has been asking power-systems and other application fields to produce — instrumented reproductions, named negative findings, and explicit reward-weight forensics. The manuscript would be unusually strong if reframed as a cross-community contribution rather than a domain-specific reproduction. Perspective rating: **78 / 100** (see §11).

---

## 1. Cross-disciplinary framing

The manuscript sits, whether or not the author cites them, squarely inside three established ML/RL literatures:

1. **Deep RL reproducibility crisis** — Henderson et al., "Deep Reinforcement Learning that Matters," AAAI 2018. Henderson's central findings (seed sensitivity, hyperparameter fragility, non-overlapping CIs across published "improvements") are essentially what this paper rediscovers in the VSG context. The author's Gate A3 firing at $\sigma = 0.265$ ($\approx 22\%$ of mean, §III.B) is textbook Henderson behavior. The paper does not cite Henderson or the follow-up by Colas et al. ("How Many Random Seeds? Statistical Power Analysis in Deep Reinforcement Learning," 2018) — both should be cited in §IV.B (statistical analysis) and §VII (limitations).
2. **Implementation-detail dominance** — Engstrom et al., "Implementation Matters in Deep Policy Gradients" (ICLR 2020), and Andrychowicz et al., "What Matters in On-Policy Reinforcement Learning?" (ICLR 2021), document that small implementation choices (advantage normalization, clipping, optimizer epsilon) can swamp claimed algorithmic advantages. The reward-weight rebalance (§II.C, $\Phi_F: 100 \to 10{,}000$, $\Phi_D: 1 \to 0.02$) and the action-range narrowing ($20\times$, Table I) are exactly the kind of "implementation detail dominates architecture" finding these papers describe. The narrative could be sharpened by explicitly framing "the multi-agent framework is decorative; the reward formula and the bus topology determine outcomes" as an instance of Engstrom's thesis.
3. **Reproducibility checklists / open-science norms** — Pineau et al., "Improving Reproducibility in Machine Learning Research" (JMLR 2021); Kapoor & Narayanan, "Leakage and the Reproducibility Crisis in ML-based Science" (Patterns 2023). The paper's identification of three same-class evaluation bugs (training at $p_{\text{cf}} = 0.1$, evaluating at $p_{\text{cf}} = 0$; §I.contributions, §V.conclusion) is precisely a Kapoor-style train/test condition leak. This deserves explicit naming as a reproducibility-leak finding, not just a domain bug.

**Adjacent literature the paper could engage with:**
- Agarwal et al., "Deep Reinforcement Learning at the Edge of the Statistical Precipice" (NeurIPS 2021) — argues for stratified bootstrap with interquartile mean (IQM) and performance profiles instead of point means. The paper uses bootstrap CI (good) but reports means; IQM would partially mitigate the n=5 dispersion problem.
- Patterson et al., "Empirical Design in Reinforcement Learning" (JMLR 2024) — codifies what counts as a credible RL empirical claim.
- The "decorative architecture" finding has clear analogs in transformer literature: Tay et al., "Long Range Arena" (ICLR 2021) found efficient-transformer variants offer little over vanilla; Merrill & Sabharwal style critiques on attention as not-really-doing-what-we-think; the lottery-ticket / shared-parameter results in NLP (Conneau & Lample 2019 cross-lingual single-encoder; ALBERT's parameter sharing) are direct conceptual cousins of the §IV.G shared-parameter SAC result.

---

## 2. Reproducibility-checklist compliance

I scored the paper against a merged Pineau-NeurIPS checklist:

| Element | Present | Section / artifact |
|---|---|---|
| Random seeds disclosed | Yes | §II.B (training {42,43,44,45,46}); §IV.B (bootstrap seed 7919); §II.A (env seeds 20000–20049) |
| Number of seeds reported | Yes (n=5) | Table II, §IV.A |
| Hyperparameters disclosed | Partial | Table I deviations vs. paper. Full SAC hyperparameters (learning rate, batch size, discount, target smoothing, replay buffer, alpha, network width/depth) NOT in the manuscript — referenced only via `config.py`. **Gap.** |
| Compute described | No | No GPU/CPU type, wall-clock, or training cost. **Gap.** |
| Code released | Yes (claimed) | §Reproducibility — file paths under `scenarios/kundur/`, `quality_reports/`. Repository URL / DOI not given. **Gap (DOI).** |
| Data released | Yes (claimed) | Audit reports under `quality_reports/audits/`. Need archival (Zenodo/figshare) for citability. |
| Eval protocol fixed | Yes | §II.A fixed test set. Strong. |
| Ablations | Yes | Per-agent (Table II), shared-param (Table III), warmstart (Table IV), hparam sweep (Table V/VI). **Above average for the field.** |
| Statistical tests | Partial | Bootstrap CI yes; effect-size, t/Welch/Wilcoxon, multiple-comparison correction not reported. **Gap.** |
| Negative results / failed attempts | Yes | Phase 7 (per-agent shaping rejected), Phase 10 (warmstart rejected), Phase 11 wide-action TDS-divergent. **Excellent.** |
| Model checkpoints released | Implied (file paths) | Best practice: archive `.pt` checkpoints with DOI. |
| Computational budget for sweeps | Partial | "100 episodes, single-seed sweep, n=5 confirmation at f_high" (§IV.I). Acceptable. |
| Random-search vs. grid disclosure | Manual | Sweep is hand-chosen $\pm 3\times$ and $\pm 2\times$. Acknowledged in §V.limitations conditionally. |

**Summary:** This paper is in the upper quartile of TPWRS reproducibility I have seen, and competitive with median NeurIPS/ICLR submissions post-2021. The pre-registration of robustness gates (§IV.I, "protocol and gate definitions were frozen prior to running the sweep," footnote citing `2026-05-04_andes_hparam_sensitivity_spec.md`) is genuinely above the field median and should be highlighted in the abstract.

**Top three checklist gaps to close in revision:**
1. Add a complete SAC hyperparameter table (all values, not just deviations) as appendix or supplementary.
2. Disclose compute budget (GPU type, total training hours, evaluator wall-clock).
3. Mint a Zenodo/figshare DOI for code+checkpoints+audit reports; cite it in the manuscript.

---

## 3. Negative-results community fit

The "honest reproduction" framing reads as a self-aware nod to the negative-results-publishing movement (e.g., the *ML Reproducibility Challenge*, NeurIPS 2019–2024 Reproducibility Track, *ReScience C* journal, *Proceedings of Machine Learning and Systems (MLSys)* reproducibility tracks). Concrete observations:

- **Tone:** "honest", "decorative", "DECORATIVE_CONFIRMED", "WARMSTART_WORSE" — the verdict-tagged terminology is unusual in TPWRS but standard in negative-results venues. It works. I would not soften it.
- **Venue fit:**
  - *ReScience C* is a near-perfect fit for the reproduction framing, but limited reach in the power-systems community.
  - The *NeurIPS Reproducibility Challenge* publishes at OpenReview and would significantly amplify cross-community visibility.
  - *Journal of Machine Learning Research (JMLR)* would accept a fully reframed version that leads with the ML-reproducibility contribution.
  - **TPWRS itself** is the pragmatic choice if the author wants the power-systems community to actually engage. TPWRS rarely publishes negative results, so this would be precedent-setting; I support it editorially.
- **Re-pitch opportunity:** The strongest reframing is *"Three same-class p_cf evaluation leaks in a multi-agent RL benchmark, and what they tell us about reproducing applied-RL papers."* Pitched that way, the paper is a contribution to *applied-RL benchmarking practice*, not just a Yang et al. 2023 reproduction. I would recommend a parallel short version for a reproducibility venue alongside the TPWRS submission — they are complementary, not redundant.

The honest-reproduction framing is also consistent with the recent *"null results in RL"* discussion (e.g., Patterson et al. 2024). The paper does NOT need to claim a "negative" finding — the §IV.G shared-param result is a *positive* finding (single-actor matches multi-agent), framed as a falsifier of the multi-agent architectural claim. That's good science and reads correctly.

---

## 4. RL credibility lens

### n=5 seeds — adequacy
Henderson 2018 recommended $n \geq 5$; Colas 2018 recommended $n \geq 10$ for any difference claim; Agarwal 2021 argued $n = 3$ to $5$ with stratified bootstrap and IQM can be defensible *if* the dispersion is reported and the claim is appropriately hedged. By the **Agarwal standard, n=5 with bootstrap CI and explicit Gate A3 firing is acceptable for the no-difference claim** — which is what the paper actually claims (DDIC tied with adaptive). For a *difference* claim, n=5 is underpowered, and the paper correctly acknowledges this and recommends Tier-B (n=10) for any future strong claim. **This is exemplary discipline.**

A specific tightening: the "$3.36\times$ over uncontrolled" claim (abstract; §VI.1) is a difference claim and should also carry a CI. Currently it is stated as a point ratio. A bootstrap CI on the ratio would strengthen this.

### Single-controller vs. distribution comparison
The paper compares the DDIC five-seed CI against a single adaptive *point estimate* ($-1.060$) — the adaptive baseline does not have a seed dimension because it is deterministic. This is a real but treatable issue:
- The right comparison is Welch's t-test / Mann–Whitney U with the per-episode adaptive scores (50 episodes) vs. the per-episode DDIC scores (50 × 5 = 250 episodes), accounting for the seed structure with a hierarchical model or cluster-bootstrap.
- The current bootstrap CI overlap is a reasonable proxy but not formally a hypothesis test. Mention this caveat in §IV.B.
- A nonparametric alternative (Wilcoxon signed-rank on paired per-episode differences) would be more standard in modern RL papers and is cheap to add.

### SAC implementation pinpointing
Critical issue: **the SAC implementation is not pinpointed in the paper text.** PyTorch version, network architecture (hidden width, depth, activation), discount $\gamma$, target smoothing $\tau$, learning rate, batch size, replay buffer size, exploration entropy target, automatic alpha tuning — none of these appear in Table I or anywhere in the manuscript. They live in `config.py` per the reproducibility appendix. **For a paper whose central claim is reproducibility, this is the largest single gap.** Add a complete hyperparameter table.

### "cum_rf" — community-standard?
"Cum-$r_f$" (cumulative frequency-deviation reward) is paper-specific to Yang et al. 2023 and this reproduction. It is *not* a standard RL benchmark metric. The paper handles this correctly by always reporting alongside max-$\Delta f$ (Hz), ROCoF (Hz/s), and Settled/50 (Table II) — all of which are physically grounded. Recommendation: explicitly define cum-$r_f$ in §II.C with the reward formula (it is currently only inferable from the $\Phi_F, \Phi_D$ discussion). An ML reader skimming the paper will need this in plain-text form.

---

## 5. Cross-disciplinary borrowing opportunities

### For power systems → from ML
- **Task suite approach**: ML benchmarks (Atari ALE, MuJoCo, DM Control, MetaWorld, ProcGen) succeeded by curating *suites* of tasks with shared protocols. Power-systems benchmarks are scattered: Kundur, IEEE 9/14/39/68/118-bus, NESTA, PGLib-OPF, GridLab-D — none with a shared RL-style evaluation harness, fixed seeds, and a leaderboard. The paper's Kundur+50-seed-test-set is a small step toward this. A natural follow-up paper: *"PowerRL: A Reproducible Benchmark Suite for RL on Phasor-Equilibrium Power Systems."*
- **Reward-component decomposition**: standard practice in modular RL (e.g., DeepMind's reward-engineering work, Hierarchical RL literature). The §III.A reward-magnitude diagnostic is exactly this technique applied diligently — naming it as a portable diagnostic ("compute the gradient share of each reward component during early training") would help other power-systems RL authors.
- **Pre-registration of robustness gates**: the paper does this (§IV.I footnote). It is rare in TPWRS. Highlight as borrowable practice.

### For ML → from this paper
- **"Decorative architecture" as a falsifiable claim**: the paper provides three converging falsifiers (per-agent ablation + shared-param + warmstart). This is a cleaner methodology than typical "we ablate one component and call it done" ML papers. The triangulation pattern (§V.C) is reusable for any architecture-vs-flat-baseline ablation in multi-agent RL.
- **Bus-position determinism**: §III.C and §V.B argue that one agent dominates because of *physical position* (proximity to high-frequency wind generator), not learning dynamics. This is a clean instance of *task structure dominating learned representation* — analogous to "convolutions on grid worlds" or "attention on already-relational data" findings. This deserves to be drawn out for an ML audience.

### Analogous "decorative architecture" findings in ML
- **Transformers**: Tay et al. 2021 (Long Range Arena) — efficient transformers ≈ vanilla on most tasks; Merrill & Sabharwal style results that attention does not learn the algorithmic structure people thought it did.
- **Multi-task learning**: Standley et al., "Which Tasks Should Be Learned Together in Multi-Task Learning?" (ICML 2020) — multi-task gains often vanish or reverse versus tuned single-task baselines.
- **Multi-agent RL specifically**: Lauer & Riedmiller 2000 / Foerster's QMIX critiques; Schroeder de Witt et al., "Is Independent Learning All You Need in the StarCraft Multi-Agent Challenge?" (2020) — independent Q-learning matched QMIX on much of SMAC, an exact precedent for the §V.C decoration finding. **Cite this.** It is the closest existing-ML analog to the paper's central claim and would strongly anchor the cross-community framing.
- **Capsule networks / GNN over-smoothing / efficient ViTs** — all genres of "the new architecture isn't doing what the headline claims."

The single highest-leverage citation the paper is currently missing is **Schroeder de Witt et al. 2020**. Adding it would lift the paper from a domain-specific reproduction to a documented instance of a known multi-agent RL phenomenon.

---

## 6. Practical and policy implications

### For power-systems practitioners (TPWRS readers)
The paper does not state strongly enough what an operator or vendor should *take away*. A sharpened "Implications for Practice" subsection should answer:
1. **Should anyone deploy multi-agent SAC for VSG inertia/damping today?** The paper's evidence implies: not on systems whose dynamics are close to phasor-equilibrium-linear; possibly yes on EMT-grade nonlinear backends, but unverified by this work.
2. **What's the minimum-viable controller?** The §IV.A adaptive K=10/400 ties DDIC. Operators can deploy a tuned proportional-derivative law and capture essentially all the benefit. Say this clearly.
3. **What does the bus-position dominance imply for VSG siting?** If one bus dominates control share by 64%, the system would be *more* observable / controllable by placing a *sensor* (not necessarily a VSG) at that bus, and treating the rest as flat. This is a real engineering recommendation the paper hints at but does not state.

### For ML researchers
The lesson is the inverse of the typical "scale up the architecture" trope: when an architecture's claimed advantage rests on a coordination story, *test against a parameter-shared single-actor baseline at matched compute*. This is a standard test in NLP (e.g., Reformer vs. vanilla Transformer ablations) but rarer in multi-agent RL applications. The paper provides a template for that test (§IV.G).

### Audience framing
The current framing leans 80% TPWRS / 20% ML. I would recommend rebalancing the *abstract* to 60/40, leading with "instrumented reproduction" and "three same-class evaluation leaks" before pivoting to the power-systems specifics. This helps cross-citation and review-pool selection. The introduction's first paragraph should briefly nod to the broader RL-reproducibility context.

---

## 7. Stakeholder blind spots

- **VSG vendors / DER operators**: the paper recommends, in effect, that they *not* invest in multi-agent RL controllers on phasor-equilibrium-similar systems. There is no "implications for vendors" or "implications for grid operators" subsection. This is a TPWRS norm gap — practitioner journals usually carry such a section. Add 3–5 sentences in §VI or §VII.
- **Safety / certification**: VSG controllers are deployed on real hardware. The paper does not discuss whether removing "decorative" architectures has any safety implication (e.g., loss of redundancy, single-point-of-failure if the dominant-bus agent goes offline). Even one paragraph acknowledging this would strengthen the paper.
- **Ethics / dual-use**: minimal in this domain, but worth noting that "dominance is structural and bus-specific" is also a *vulnerability* finding (an attacker who knows which bus dominates control has a high-leverage target). This is *not* a reason to redact — the result is published either way — but the paper should briefly acknowledge the security-research adjacency.
- **Reward-engineering ethics**: the project deviates substantially from the reference paper's reward weights. This is documented (Table I), but the paper is silent on whether the reference paper's *reported* weights are even *trainable* in their original simulator. The §II.C "gradient-invisible at $\Phi_F = 100$" finding implies one of: (a) the reference paper had different effective magnitudes that the deviation table does not capture; (b) the reference paper's stated weights are incorrect; (c) backend differences alone explain it. Ruling among these is out of scope, but acknowledging the ambiguity is fair.

---

## 8. Strengths (perspective)

1. **Exemplary negative-results discipline (§I, §IV.F, §IV.H, §V).** Phase 7 (rejected), Phase 10 (rejected), Phase 11 (TDS-divergent and reported anyway), warmstart explicitly tagged WARMSTART_WORSE. This is rare in TPWRS and in applied RL more broadly.
2. **Pre-registration of the hparam sweep robustness gate (§IV.I, footnote 2 to `2026-05-04_andes_hparam_sensitivity_spec.md`).** Above the field median and competitive with NeurIPS-tier reproducibility tracks.
3. **Triangulated falsification (§V.C).** Three independent lines of evidence (per-agent ablation, shared-param baseline, warmstart) all converging on "decorative" is much harder to dismiss than any single ablation.
4. **Honest provenance accounting (§III.C "Figure provenance note").** The paper marks which figures are pre-bug-fix legacy data and verifies qualitative replication post-fix. This is the gold-standard practice for incremental dataset corrections; few papers in any field bother with this rigor.
5. **Clear identification of evaluation-leak class (§I.contributions.2, §VII).** Three same-class bugs found and fixed, with explicit quantification (~6% inflation). This is a contribution to applied-RL methodology, not just a domain reproduction.

## 9. Weaknesses (perspective)

1. **Missing complete SAC hyperparameter table (§II–II.B, Table I).** Table I lists only deviations. A reproducibility paper must provide the full hyperparameter set. **Major.**
2. **No engagement with the directly relevant ML reproducibility literature (§I, §IV.B).** Henderson 2018, Colas 2018, Engstrom 2020, Agarwal 2021, Schroeder de Witt 2020 are all directly applicable and uncited. **Major** — easily fixed.
3. **Statistical tests are CI-only; no Welch's t / Wilcoxon / IQM (§IV.B).** The CI-overlap argument is reasonable but informal. Modern RL papers (post-Agarwal 2021) report bootstrap CI plus IQM plus a nonparametric test. **Moderate.**
4. **Single-author claim of "honest reproduction" lacks an independent verification step (§Reproducibility).** The audits live in `quality_reports/` written by the same author. A reviewer or a co-author independently re-running the eval pipeline would close this loop. As-is, the claim relies on the author's discipline. **Minor but mentionable.**
5. **No archival DOI for code/data (§Reproducibility).** File paths in the project tree are not citable across time. Mint a Zenodo DOI at submission. **Minor, mechanical.**

## 10. Recommended additions

### Citations to add
- Henderson et al., AAAI 2018 — "Deep RL that Matters." (§I, §IV.B)
- Colas et al., 2018 — "How Many Random Seeds?" (§IV.B, §VII)
- Engstrom et al., ICLR 2020 — "Implementation Matters in Deep Policy Gradients." (§II.C, §V)
- Andrychowicz et al., ICLR 2021 — "What Matters in On-Policy RL?" (§II.C)
- Pineau et al., JMLR 2021 — "Improving Reproducibility in ML." (§I, §Reproducibility)
- Agarwal et al., NeurIPS 2021 — "Edge of the Statistical Precipice" (IQM, performance profiles). (§IV.B)
- Schroeder de Witt et al., 2020 — "Is Independent Learning All You Need in SMAC?" (§V.C — direct multi-agent-RL precedent)
- Kapoor & Narayanan, Patterns 2023 — "Leakage and Reproducibility Crisis in ML-based Science." (§I.contributions.2)
- Patterson et al., JMLR 2024 — "Empirical Design in RL." (§IV.B)

### Framing tweaks
- Abstract: open with "instrumented reproduction" and the eval-leak finding before pivoting to power systems. Currently abstract is 100% domain framing.
- §I (introduction): one paragraph placing the work in the deep-RL reproducibility literature.
- §V.C: explicitly invoke "decorative architecture" as a documented multi-agent RL phenomenon (Schroeder de Witt 2020), not a novel observation.
- §VI (claims): add a "for-practitioners" paragraph stating the deployment recommendation.
- §VII (limitations): expand single-controller-vs-distribution caveat; add the Welch/Wilcoxon-not-yet-run note.

### Alternative-venue considerations
- TPWRS is the right primary venue. Editorially novel for TPWRS; supported.
- A short companion paper (4–6 pages) at *NeurIPS Reproducibility Track* or *ReScience C* would substantially amplify cross-community impact and is recommended. The §I.contributions.2 eval-leak finding is the natural lead for that companion.

### Mechanical additions
- Full SAC hyperparameter table (appendix).
- Compute disclosure (GPU type, total training hours).
- Zenodo / figshare DOI for code + checkpoints + audit reports.
- Bootstrap CI on the $3.36\times$ uncontrolled-improvement ratio.
- Wilcoxon signed-rank or paired-bootstrap on per-episode DDIC vs. adaptive.

---

## 11. Perspective rating

**78 / 100.**

Breakdown:
- Reproducibility-checklist compliance: 85/100 (above field median; gaps are mechanical)
- Negative-results discipline: 92/100 (exemplary)
- Statistical-method modernity (post-Agarwal 2021): 65/100 (CI-only; missing IQM, Welch, Wilcoxon)
- Cross-community engagement / citation breadth: 50/100 (no ML reproducibility literature cited; major missed opportunity)
- Framing for TPWRS audience: 80/100 (well-targeted; could explicitly address vendors/operators)
- Framing for ML audience (if reframed): 70/100 (good substance, weak top-of-funnel)
- Honesty and provenance accounting: 95/100 (figure-provenance note is gold-standard)

A revised version that closes the four mechanical gaps (hyperparameter table, compute, DOI, bootstrap on ratio) and adds the eight recommended citations would push the rating to **85+**. The substance of the work is already there; what's missing is the cross-community wrapper.

---

*End of Reviewer 3 (cross-disciplinary perspective) report.*
