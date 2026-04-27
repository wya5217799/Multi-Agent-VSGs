# Action Range Mapping Deviation — Yang 2023 Paper vs v3 Implementation

**Date:** 2026-04-28
**Status:** Documented deviation (in force until Q7 H-unit ambiguity is resolved)
**Owner:** Project main line
**Related:** Task 3 of `quality_reports/plans/2026-04-28-kundur-cvs-v3-paper-alignment-task-list-FINAL.md`

---

## 1. Paper PRIMARY

### 1.1 Action range — paper line 938-939
> "The parameter range of inertia and droop for each energy storage is
> from **−100 to 300** and from **−200 to 600**, respectively."

Paper-stated ranges (Sec.IV-B):
- **ΔH ∈ [−100, +300]**
- **ΔD ∈ [−200, +600]**

Source: `C:/Users/27443/Desktop/论文/high_accuracy_transcription_v2.md` line 938-939.

### 1.2 Eq.1 (paper line 250)
$$
H_{esi}\,\Delta\dot{\omega}_i + D_{esi}\,\Delta\omega_i = \Delta u_i - \Delta P_{esi}
$$

Paper Eq.1 form (control-派 lumped constant):
- **No `2` coefficient** in front of H
- **No `ω_s` (synchronous speed) coefficient**
- **H unit not stated** in paper (Q7 unresolved — see fact-base §8)
- **H_es,0 baseline value not given** in paper

Source: paper line 250 (Sec.II-A Eq.1).

---

## 2. v3 Implementation State (PRIMARY 源码)

### 2.1 Action range constants
File: `scenarios/config_simulink_base.py:37-38`
```python
DM_MIN, DM_MAX = -6.0, 18.0    # M range: [M0+DM_MIN, M0+DM_MAX]
DD_MIN, DD_MAX = -1.5, 4.5     # D range: [D0+DD_MIN, D0+DD_MAX]
```

### 2.2 Initial baselines (PRIMARY MCP query, this audit session)
- `ESS_M0 = 24.0` (= H_code = 12 in vsg-base 200 MVA, with M=2H convention)
- `ESS_D0 = 4.5` (vsg-pu)

Source: `build_kundur_cvs_v3.m` workspace dump via `simulink_run_script` get_param.

### 2.3 Floor constants
- `M_FLOOR = 1.0` (vsg-base, hard physical lower bound)
- `D_FLOOR = 0.5` (vsg-pu, hard physical lower bound)

Source: project Phase C calibration, `scenarios/config_simulink_base.py`.

---

## 3. The Deviation

### 3.1 Numerical gap

| Param | Paper-literal | v3 (M=2H 项目推断 mapping) | Ratio |
|---|---|---|---|
| ΔH | [−100, +300] | M-range / 2 = [−3, +9] | **33× narrower** |
| ΔD | [−200, +600] | [−1.5, +4.5] | **133× narrower** |

### 3.2 Unit ambiguity (Q7 — fact-base §8)
- Paper Eq.1: `H·ω̇ + D·ω = u − P` — H unit is **NOT specified**
- Possible interpretations: seconds? per-unit? dimensionless?
- Paper Sec.IV-B gives ΔH = [−100, 300] but does not anchor units
- Cannot translate "ΔH = +300" to a v3 ΔM = ?? without a unit decision

### 3.3 H_es,0 baseline ambiguity
- Paper does not state initial H_es,0 value (only the ΔH adjustment range)
- v3 chooses H_code = 12 (= M0 = 24, in M = 2H convention)
- 12 is not derived from paper; it's a project choice anchored in
  classic Kundur reference [49] convention for swing-eq base

---

## 4. Why Not Adopt Paper-Literal Range

### 4.1 Phase C empirical floor-clip evidence

Phase C (`results/harness/kundur/cvs_v3_phase_c/phase_c_action_range_verdict.md`)
calibrated 4 ladders L0–L3 with widening ranges:

| Ladder | ΔM range | ΔD range | Floor-clip rate |
|---|---|---|---|
| L0 (= current v3) | [−6, 18] | [−1.5, 4.5] | 0% (only L0 PASSED Phase C) |
| L1 | [−15, 45] | [−3.75, 11.25] | partial floor clip |
| L2 | [−30, 90] | [−7.5, 22.5] | majority floor clip |
| L3 (paper-equivalent if H_paper=2·H_code) | [−200, 600] | [−400, 1200] | 87% floor clip |

Phase C verdict: only L0 (= current v3) is physically valid. Wider
ladders fail because action vectors enter region where M < 1.0 or D < 0.5,
which are physical lower bounds (negative inertia is non-physical;
near-zero damping is numerically unstable).

### 4.2 Paper-literal ΔM = −100 → M = −76 → clip to floor
If we adopted paper-literal `ΔM_MIN = −100`, then:
- M_target = M0 + ΔM_min = 24 − 100 = **−76**
- Clamped to M_FLOOR = 1.0 (physical lower bound)
- 87% of action space lies below floor → SAC actor outputs in this
  region all clip to the same M = 1.0 → no gradient, no learning

### 4.3 Reverse calibration (= make paper-literal range fit) breaks [49]
Alternative: raise ESS_M0 to make ΔM = −100 still positive after
addition. E.g., ESS_M0 = 150 → ΔM range [50, 450] post-action.
- This abandons classic Kundur [49] H = 6.5 inertia base
- Project loses calibration anchor in well-studied Kundur 2-area system
- Q7 still unresolved — we'd just be guessing in a different direction

---

## 5. Working Assumption (项目推断, NOT paper fact)

### 5.1 H_paper = 2·H_code mapping
Project working assumption (per `env/ode/NOTES.md` M1 segment):
- **H_paper = 2·H_code**
- Rationale: code uses electromechanical convention `M·ω̇ = Pm − Pe − D·(ω−1)`
  with `M = 2H`; if paper Eq.1 is `H·ω̇ + D·ω = u − P` lumped form,
  numerical equivalence requires H_paper = 2·H_code at fixed ω̇.

### 5.2 Paper-equivalent v3 range (under H=2H assumption)
Under this mapping:
- v3 ΔM = [−6, +18] ⇔ paper-equivalent ΔH = [−3, +9]
- v3 ΔD = [−1.5, +4.5] ⇔ paper-equivalent ΔD = [−1.5, +4.5]

### 5.3 Even with this mapping, still 33× narrower than paper-literal
- Paper-equivalent ΔH = [−3, +9] vs paper-literal [−100, +300] = 33× narrower
- Paper-equivalent ΔD = [−1.5, +4.5] vs paper-literal [−200, +600] = 133× narrower

### 5.4 Disclaimer (CRITICAL)
**The H_paper = 2·H_code mapping is a project inference, not a paper-stated
fact.** Paper Eq.1 does not specify H unit; the 2× factor is derived from
project code conventions, not paper text. **Cite as project assumption,
NEVER as paper fact.**

---

## 6. Decision: Document, Don't Adopt

Three paths considered:

| Path | Action | Outcome |
|---|---|---|
| E-doc (CHOSEN) | Document deviation; keep DM/DD constants unchanged | Transparent; physically valid; respects Q7 |
| E-paper-literal | Set DM_MIN=−100, DM_MAX=+300 directly | 87% floor clip; SAC training collapses |
| E-paper-equivalent | Set DM_MIN=−200, DM_MAX=+600 (= 2·paper, M=2H mapping) | Same floor-clip problem as E-paper-literal; mapping unverified |

**Decision:** E-doc.

**Rationale:**
1. **Q7 unresolved** — paper does not specify H unit; any literal/scaled
   adoption is mechanical mimicry without physical justification.
2. **Phase C empirical evidence** — wider ranges hit physical floor;
   no SAC-trainable configuration exists at paper-literal range.
3. **Transparency over pretense** — explicit deviation with documented
   rationale > silent deviation that pretends to align.

---

## 7. Resolution Path (Q7 解决后)

This deviation can be revisited if Q7 is resolved. Possible triggers:

### 7.1 Q7 resolution scenarios
- Email correspondence with paper authors clarifying H unit
- Cross-reference papers in TPWRS using same Eq.1 form with explicit units
- Identification of standard convention in Yang's prior publications

### 7.2 Decision tree if Q7 resolves to specific unit
- If H_paper unit = seconds (electromechanical):
  - May confirm H_paper = 2·H_code mapping → still 33× narrower (no change)
  - Or refute → re-derive mapping and re-evaluate
- If H_paper unit = pu of some base:
  - Need to identify base (Sn, Sbase?) → re-derive ESS_M0 anchor
  - May require re-calibration with classic Kundur values
- If H_paper unit = dimensionless lumped constant:
  - Need to interpret physical meaning of ΔH = +300 in dimensionless space
  - Likely needs project-side simulation re-design

### 7.3 No-action conditions
- Q7 remains unresolved → keep current deviation
- Phase C re-runs with updated mapping show new range is also floor-clipped
  → keep current

---

## 8. References

### 8.1 Paper PRIMARY
- Paper line 938-939 (Sec.IV-B): action range numbers
- Paper line 250 (Sec.II-A Eq.1): VSG dynamics with ambiguous H unit
- Source: `C:/Users/27443/Desktop/论文/high_accuracy_transcription_v2.md`

### 8.2 Phase C verdict
- `results/harness/kundur/cvs_v3_phase_c/phase_c_action_range_verdict.md`
- L0–L3 ladder calibration; only L0 passes physical validity gate

### 8.3 Fact-base
- `docs/paper/yang2023-fact-base.md` §2.1 Q7 (H unit ambiguity)
- `docs/paper/yang2023-fact-base.md` §8 Q7 (待核实问题)
- `docs/paper/yang2023-fact-base.md` §10 偏差备案 (动作范围 row)

### 8.4 ODE notes
- `env/ode/NOTES.md` M1 segment (H_paper = 2·H_code working assumption)

### 8.5 Code anchors
- `scenarios/config_simulink_base.py:37-38` — DM/DD constants
- `scenarios/config_simulink_base.py` — M_FLOOR / D_FLOOR floor constants
- `scenarios/kundur/simulink_models/build_kundur_cvs_v3.m` — ESS_M0=24, ESS_D0=4.5 baselines
- `env/simulink/kundur_simulink_env.py:_map_zero_centered_action` — action-to-physical mapping

---

## 9. Status

### 9.1 Current state
**Documented deviation.** v3 uses ΔM=[−6,+18] / ΔD=[−1.5,+4.5] (33× /
133× narrower than paper-literal). All callers should treat this as a
**known, justified gap**, not as paper alignment.

### 9.2 Status change conditions
This document should be updated when:
1. Q7 is resolved (paper author / cross-ref / convention identification)
2. Phase C is re-run with a new mapping and produces a different conclusion
3. Project decides to adopt a paper-literal range despite floor clip
   (would require accompanying ESS_M0/ESS_D0 re-calibration plan)

### 9.3 Maintenance responsibility
Project main line (i.e., this document is canonical project doc, not a
side note). Update via Git commit + cross-reference fact-base §10 row.

---

*End of action-range-mapping-deviation.md*
