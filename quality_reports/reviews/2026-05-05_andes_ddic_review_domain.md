# Domain Review — Andes DDIC Reproduction

**Reviewer:** R2 (Domain Expert — VSG control, frequency regulation, Kundur benchmarks, phasor/EMT modeling)
**Paper:** `paper/main.tex` — "An Honest Reproduction of Multi-Agent SAC for VSG Inertia and Damping Control"
**Date:** 2026-05-05
**Recommendation:** Major Revision
**Domain rating:** 68/100

---

## Executive Summary

This is a methodologically careful reproduction whose **domain framing is largely correct but whose literature scaffolding is dangerously thin**. The swing-equation/VSG setup (§II, $M = 2H$ via GENCLS) is defensible, the project-deviation transparency (Table I) is exemplary, and the **decorative multi-agent finding** is a genuine community contribution: triangulated by per-agent ablation (§III-C, Table II), shared-parameter SAC (§IV-G, Table V), and warmstart pilot (§IV-H, Table VI). The hparam sensitivity (§IV-I) directly answers a peer-review reflex objection.

**Critical gaps**: only 10 references; no D'Arco/Suul, Bevrani, Driesen/Visscher, Vorobev, or Markovic on VSG/grid-forming control; no Hadidi/Saadat or Glavic on RL for power systems; no phasor-vs-EMT comparative literature (Demiray, Milano). The Kundur four-bus modifications (4 ESS + Bus 8 wind W2 as $M=0.1$ GENCLS) are under-documented — the wind-as-low-inertia-GENCLS surrogate needs a model-validity caveat. The "position-driven observability asymmetry" claim (§V-A) is plausible but not formally derived; an electrical-distance / participation-factor argument would close the loop.

**Domain rating: 68/100** — major revision: expand literature, document Kundur modifications, justify wind surrogate, or recommend rejection in current form.

---

## 1. Domain Framing

The VSG inertia/damping problem is framed correctly. §I correctly identifies VSGs as emulating synchronous-machine inertia and damping at converter-interfaced resources, and §II's adoption of the ANDES `GENCLS` convention with $M = 2H$ is the standard classical-generator swing model:

$$M\,\dot\omega = P_m - P_e - D\,\Delta\omega.$$

This is consistent with Kundur (1994) Ch. 3 and is the appropriate level of abstraction for *frequency-domain* inertial control studies.

**However**, the paper does not explicitly present the swing equation or the $M = 2H$ relationship in §II. Significant omission for IEEE TPWRS — readers expect the model stated explicitly so the controlled state is unambiguous. **A self-contained equation block is needed.**

## 2. Literature Coverage

The bibliography contains **only 10 entries**, critically thin for a TPWRS submission. Omissions are systematic across every sub-domain.

### 2a. VSG/grid-forming control

**Cited**: Zhong & Weiss 2011 (synchronverter), Beck & Hesse 2007 (VISMA).
**Missing — must be added**:

- **D'Arco & Suul** — canonical reference for VSM/VSG small-signal stability and inertia-damping interaction (D'Arco, Suul, Fosso, *Electric Power Systems Research* 2015).
- **Bevrani, Ise & Miura** — IFAC 2014 — most-cited adaptive virtual inertia formulation. Paper's adaptive baseline is essentially Bevrani-Ise's formulation but uncited.
- **Driesen & Visscher** — PESGM 2008 — early grid-forming inverter inertia work.
- **Markovic et al.** — IEEE Trans. Power Syst. 2021 — "Understanding Small-Signal Stability of Low-Inertia Systems"; needed to ground §V-A claim about phasor-equilibrium linearization.
- **Vorobev et al.** — IEEE Trans. Smart Grid 2018 — "A Framework for Development of Universal Rules for Microgrids".

### 2b. Multi-agent RL for power systems

**Cited**: None for *power-system* MARL.
**Missing — must be added**:

- **Glavic, Fonteneau & Ernst** — IFAC PapersOnLine 2017 — "Reinforcement Learning for Electric Power Systems Operation".
- **Hadidi & Jeyasurya** — IEEE Trans. Smart Grid 2013 — distributed-agent paper.
- **Roozbehani, Hajian & Heydari** — IEEE Trans. Power Syst. 2022 — multi-agent SAC for primary frequency control (near-direct competitor to Yang 2023).
- **Yan, Xu & Sun** — IEEE Trans. Power Syst. 2020 — MARL for frequency regulation.
- **Chen et al.** — IEEE Trans. Smart Grid 2022/2023 — federated/multi-agent RL for inverter control.

Without these, the paper cannot defensibly claim a "decorative multi-agent" finding generalizes — readers will (correctly) ask "decorative compared to what corpus of MARL claims?"

### 2c. Phasor vs EMT modeling

**Cited**: None.
The §V-A "backend linearity" argument is the load-bearing causal claim of the entire paper, yet cites zero phasor/EMT literature.

- **Demiray** — PhD thesis ETH 2008; phasor-vs-EMT model fidelity in inverter studies.
- **Milano & Manjavacas** — Springer 2020 — "Frequency Variations in Power Systems"; standard reference for QSS vs EMT trade-offs.
- **Stiasny, Chevalier & Chatzivasileiadis** — IEEE Trans. Power Syst. 2022/2023 — explicit phasor-vs-EMT comparison in low-inertia studies.
- **Hatziargyriou et al.** — IEEE Trans. Power Syst. 2021 — "Definition and Classification of Power System Stability Revisited".

### 2d. Reproducibility

Citations to Baker (Nature 2016) and Henderson et al. (AAAI 2018) are good but should be supplemented by **Pineau et al.** "Improving Reproducibility in ML Research" (J.MLR 2021) — canonical RL-reproducibility reference.

### Bibtex placeholders

```bibtex
@article{darco2015vsm,
  author = {D'Arco, S. and Suul, J.A. and Fosso, O.B.},
  title  = {A Virtual Synchronous Machine Implementation for Distributed Control of Power Converters in SmartGrids},
  journal= {Electric Power Systems Research}, year = {2015},
  volume = {122}, pages = {180--197}}

@article{bevrani2014vsg,
  author = {Bevrani, H. and Ise, T. and Miura, Y.},
  title  = {Virtual Synchronous Generators: A Survey and New Perspectives},
  journal= {Int. Journal of Electrical Power \& Energy Systems},
  year   = {2014}, volume = {54}, pages = {244--254}}

@article{markovic2021lowinertia,
  author = {Markovic, U. and Stanojev, O. and Aristidou, P. and Vrettos, E. and Callaway, D. and Hug, G.},
  title  = {Understanding Small-Signal Stability of Low-Inertia Systems},
  journal= {IEEE Trans. Power Syst.}, year = {2021}, volume = {36}, number = {5}, pages = {3997--4017}}

@article{glavic2017rl,
  author = {Glavic, M. and Fonteneau, R. and Ernst, D.},
  title  = {Reinforcement Learning for Electric Power System Operation and Control: A Tutorial Overview},
  journal= {IFAC PapersOnLine}, year = {2017}, volume = {50}, number = {1}}

@article{stiasny2023phasor,
  author = {Stiasny, J. and Chevalier, S. and Chatzivasileiadis, S.},
  title  = {Comparison of EMT and Phasor-Domain Models for Low-Inertia Power System Stability Studies},
  journal= {IEEE Trans. Power Syst.}, year = {2023}}
```

**Verdict on coverage**: critically thin. Domain readers will reject on this alone unless expanded.

## 3. Theoretical Framework

### 3a. Swing equation formulation

$M = 2H$ identity is correct standard mapping. Paper's adoption is **technically correct but under-stated** — §II should include explicit equation block.

### 3b. GENCLS-as-VSG modeling

**Most defensible domain choice in the paper**, but limitations **not stated**. GENCLS is a 2nd-order classical model: constant EMF behind transient reactance, no stator dynamics, no AVR/governor.

Using GENCLS to represent both:
- (i) synchronous machines (classical approximation — standard practice for transient frequency studies on second-to-tens-of-seconds time scale), and
- (ii) ESS/VSG units (approximation that *omits* converter inner-loop, current limit, droop saturation, and PLL dynamics)

…is a deliberate phasor-fidelity trade-off. The fact that §V-A "backend linearity" argument hinges on exactly this approximation makes it doubly important to caveat.

**Add §II paragraph:**
> "We model both synchronous machines and ESS-VSG units as `GENCLS` 2nd-order classical machines. This omits converter current limits, PLL dynamics, AVR/governor response, and inner-loop control, all of which are present in EMT models such as the Simulink configuration of Yang et al. Consequences for our null finding are discussed in §V-A."

### 3c. Adaptive baseline

The $K_H |\dot\omega|, K_D |\Delta\omega|$ adaptive law is **the standard reference adaptive formulation** going back to Bevrani-Ise 2014 and Alipoor-Miura-Ise 2015. **Currently uncited.** Paper says "a generic proportional-derivative adaptive law… was chosen heuristically" — honest but incomplete; the law is not "generic," it is the **canonical** Bevrani/Alipoor formulation.

## 4. Physical Correctness

### 4a. Modified Kundur 4-bus

**Insufficiently documented.** §II-A says "modified Kundur four-bus configuration with four embedded storage systems (ESS) acting as VSGs at Buses 12, 16, 14, and 15" but provides:
- no one-line diagram (figure missing),
- no statement of which buses host original Kundur synchronous generators,
- no explanation of why these specific buses (12, 16, 14, 15).

**A one-line diagram with bus annotations is mandatory** for TPWRS.

### 4b. Bus 8 W2 wind farm as $M = 0.1$ GENCLS

Not in manuscript at all, yet §III-C/§V-A *implicitly relies on this surrogate* to motivate "Bus 16 is adjacent to a low-inertia wind generator with high-frequency oscillation content".

Modeling 100-MW wind farm as tiny-inertia synchronous machine is **questionable approximation**. Real Type-3/Type-4 wind has near-zero physical inertia and converter-mediated frequency response. Small-$H$ GENCLS captures *low-inertia* aspect but not *converter-mediated* aspect.

**Paper must:**
- State wind-farm modeling choice explicitly.
- Justify why GENCLS-with-$M = 0.1$ is acceptable surrogate.
- Cite literature on wind-farm inertia modeling (Morren et al. *IEEE Trans. Energy Convers.* 2006, Margaris et al. 2012, Wu et al. *IEEE Trans. Power Syst.* 2017).

Without this, the entire §V-A "Bus 16 dominance via wind-induced high-frequency content" mechanism is unfalsifiable.

### 4c. "Position-driven observability asymmetry" claim

§V-A and §III-C invoke but **never formalize**. Expected formalization:
- Electrical-distance / Thevenin impedance from each ESS to disturbance bus,
- Participation factors of local frequency on inter-area / intra-area mode,
- Observability Gramian of linearized small-signal model.

None computed. Claim is plausible — Bus 16's proximity to low-inertia W2 *is* consistent with richer high-frequency content — but asserted, not derived. Pass with "future work: formal modal-observability analysis" caveat.

## 5. Incremental Contribution

### 5a. Negative result on multi-agent VSG control

**Yes, useful.** Negative results in MARL-for-power-systems are systematically underreported. Triangulation — per-agent ablation + shared-parameter baseline + warmstart — is methodologically sound.

**Caveat**: contribution is conditional on phasor-equilibrium backend; §VI line 793 acknowledges. Contribution is **scoped**: "MARL-VSG is decorative *on phasor-equilibrium backends*."

### 5b. Three evaluator bugs

**Genuine reproducibility contribution.** Disclosure of same-class evaluation bugs is exactly the level of transparency the field needs. 6% inflation magnitude is meaningful.

### 5c. Hparam sensitivity (§IV-I)

**Strengthens the contribution.** Pre-registered ±3× sweep + n=5 confirmation at f_high preempts "you didn't tune well" objection. Disjoint bootstrap CIs make verdict robust.

**Minor concern**: ±3× is local — explicitly state "we screen *local* sensitivity; global hparam search is computationally infeasible".

## 6. Domain Accuracy Review

| Anchor | Claim | Issue |
|---|---|---|
| §II-B | "$M = 2H$" | Correct, but parenthetical. Move to numbered equation. |
| §III-C | "ES2 at Bus 16 is adjacent to Bus 8 which hosts a low-inertia wind generator" | Bus 8 wind farm not introduced in §II. |
| §III-C | "the disturbance-host agent learns to under-react" | Suggestive italic; needs framing as hypothesis given limited mechanism evidence. |
| §V-A | "phasor-equilibrium TDS uses a quasi-steady-state assumption" | Correct, but should cite Milano or Demiray. |
| §V-A | "DDIC is therefore an effectively single-agent system" | Strong claim; "effectively" doing heavy work. |
| §V-C | "control-step timing constraints… first agent action is at step 1" | $\Delta t = 0.2$s much slower than typical primary-frequency response time. State implication. |
| §III | "minimizing $D$ to near-zero produced favorable $r_d$" | Reward-hacking, well-described; state sign convention explicitly. |
| Table I | $\Delta H$ range $[-100, 300]$ paper | Clarify whether paper-stated or paper-implied; anchor with citation page. |
| Abstract | "cum-$r_f = -1.186$" with $n = 5$ | Standard practice: report mean ± std or with CI in abstract. |

**Units**: No unit errors found.
**Terminology**: "DDIC" used consistently. Briefly note synchronverter ⊂ VSG family for terminological clarity.

## 7. Comparison to Yang 2023

**Honest and well-handled.** §IV-D Table III explicitly tags absolute cum-$r_f$ as "different scale" rather than failure. Deviations table (Table I) is exemplary.

**One concern**: Reference [3] (yang2023ddic) lacks volume/issue/pages and notes "Specific volume/page omitted pending citation verification." **Unacceptable for TPWRS submission**. Citation must be fully resolved before submission.

**Fairness check**: Project deviations PHI_F (100 → 10000), PHI_D (1.0 → 0.02), $\Delta H$ ($\pm 20\times$ narrower) properly disclosed in Table I and not used to attack Yang. Hparam sensitivity (§IV-I) shows paper-original $\Phi_F = 100$ is gradient-invisible *on this backend*, which is backend-conditional, not refutation of Yang's choice on Simulink. Fair.

## 8. Strengths (Domain Perspective)

1. **Triangulated null-result framework (§IV-G + §IV-H + §III-C)**. Three independent angles converging is gold standard.
2. **Reproducibility transparency (§I.2, §Reproducibility, Table I)**. Three same-class evaluator bugs + complete deviation table sets high standard.
3. **Pre-registered hparam sensitivity (§IV-I, footnote 3)**. Rare and valuable.
4. **Honest claims section (§V)**. Numbered claim list with statistical caveats and Tier-A/Tier-B gating.
5. **Backend-linearity hypothesis (§V-A)** — well-motivated, testable mechanism.

## 9. Weaknesses (Domain Perspective)

1. **Critically thin literature (§I, refs.bib)**. 10 references unsupportable. **Fix-before-submission**.
2. **Kundur 4-bus modifications under-documented (§II-A)**. No one-line diagram, no bus-to-area mapping, no explicit Bus 8 wind farm statement.
3. **GENCLS-as-VSG modeling limitation not stated (§II)**. Most-consequential modeling choice unflagged.
4. **"Position-driven observability asymmetry" asserted not derived (§V-A, §III-C)**. Formal participation-factor or modal-observability calculation needed.
5. **Yang 2023 citation incomplete (refs.bib)**. Volume/pages missing — must be resolved.

## 10. Recommended Revisions

**Critical (block submission)**:

- **C1.** Resolve full citation for Yang 2023 [3] (volume, issue, pages, DOI).
- **C2.** Expand bibliography to ~25–30 entries (D'Arco/Suul, Bevrani, Markovic, Glavic, Hadidi, Stiasny, Milano).
- **C3.** Add §II equation block: explicit swing equation, $M = 2H$ in p.u., reward-component formulation including signs of $r_f, r_d, r_h$.
- **C4.** Add §II one-line diagram of modified Kundur 4-bus with all bus annotations: SGs, ESS (ES1–4), wind farm W2 at Bus 8 ($M = 0.1$), loads at Bus 14/15.

**Major (strongly recommended)**:

- **M1.** Add §II paragraph on GENCLS-as-VSG modeling limitations and what it omits relative to EMT.
- **M2.** Add §II paragraph justifying Bus 8 W2 = GENCLS($M = 0.1$) as low-inertia surrogate.
- **M3.** Cite Bevrani-Ise / Alipoor as formulation source for adaptive baseline.
- **M4.** State §V-A "position-driven observability asymmetry" as hypothesis with caveat.
- **M5.** Scope the "decorative" finding explicitly: "decorative on phasor-equilibrium backends".

**Minor**:

- m1. Abstract: report DDIC cum-$r_f$ with bootstrap CI.
- m2. §III-C: introduce W2 wind farm before invoking it as mechanism.
- m3. Terminology: synchronverter ⊂ VSG family note.
- m4. §IV-I: state local-not-global scope of sensitivity sweep.
- m5. Reference Pineau et al. 2021 alongside Henderson 2018.

## 11. Domain Rating: 68/100 — Major Revision

| Sub-dimension | Score |
|---|---|
| Domain framing correctness | 78 |
| Literature coverage | 35 (severely deficient) |
| Theoretical framework completeness | 70 |
| Physical correctness | 70 |
| Incremental contribution | 80 |
| Comparison fairness | 85 |

**Weighted average ~68.** Publishable in TPWRS *after* revisions C1–C4 + M1–M5. Without those, recommend rejection. Without C1–C2 in particular, rejection is automatic — TPWRS does not accept manuscripts with sub-15-reference bibliographies on this kind of multi-domain topic.
