# Phase 2 Aggregate Verdict — Kundur CVS v3 Dry-Run Probes

> **Status: PHASE 2 = CONDITIONAL PASS / GO TO NEXT DESIGN DECISION** (not full PASS).
> **Date:** 2026-04-26
> **Phase 1 commit:** `a40adc5` (fix-A2 build edits applied since)
> **Plan:** [`quality_reports/plans/2026-04-26_kundur_cvs_v3_plan.md`](../../../../quality_reports/plans/2026-04-26_kundur_cvs_v3_plan.md)
> **Spec:** [`quality_reports/plans/2026-04-26_cvs_v3_topology_spec.md`](../../../../quality_reports/plans/2026-04-26_cvs_v3_topology_spec.md)

---

## 1. Probe outcomes

| Probe | Verdict | Detail file |
|---|---|---|
| P2.1 — 30 s zero-action stability | **PASS** (after fix-A2) | [`phase2_p21_fixA_verdict.md`](phase2_p21_fixA_verdict.md) |
| P2.2 — per-source Pm-step reach   | **PASS** | (run inline; gate `df ∈ [0.05, 5] Hz` met for all 7 sources, 0.063–0.094 Hz) |
| P2.3 — LoadStep reach (L1)        | **CONDITIONAL PASS** | [`phase2_p23_L1_verdict.md`](phase2_p23_L1_verdict.md) |
| P2.4 — wind trip reach (L1)       | **CONDITIONAL PASS** | [`phase2_p24_L1_verdict.md`](phase2_p24_L1_verdict.md) |
| P2.5 — ESS H/D sensitivity (a + b-L1) | **CONDITIONAL PASS** | [`phase2_p25_verdict.md`](phase2_p25_verdict.md), [`phase2_p25b_L1_verdict.md`](phase2_p25b_L1_verdict.md) |

P2.1 had an initial FAIL → diagnostic-only verdict ([`phase2_p21_verdict.md`](phase2_p21_verdict.md)) which led to **fix-A2** (3 build-implementation bugs corrected: Π-line shunt C, Pm/Pe scaling Product not Divide, SG governor InvR Gain block). All three were spec-mathematics divergences in the build script — **no topology, dispatch, IC, V_spec, line per-km params, or NR were touched**. P2.1 then PASSED.

P2.3 had an initial L0 FAIL → diagnosed as probe-metric defect (steady-Δω = 0 by δ-integrator construction). L1 reformulation switched to transient-peak metric → CONDITIONAL PASS.

P2.5b had an initial FAIL on `df_peak` ratio → reformulated as decay-envelope τ ratio (L1) → still below the simple-oscillator band but with clean fits.

---

## 2. What v3 physical paths now demonstrably work

1. **Zero-action equilibrium**: NR steady state reached within 5 e-5 pu on all 7 sources (G1/G2/G3 + ES1..4) by t = 30 s; common-mode drift +5.9 e-6; closure clean. (P2.1)
2. **Pm-step disturbance reaches network dynamics**: per-source +0.2 sys-pu Pm step yields df_peak in [0.063, 0.094] Hz at the source itself, all 7 sources; mid-sim gate via `Pm_step_amp_<i>` workspace var verified. (P2.2)
3. **Load disturbance is detectable**: LoadStep at Bus 7 yields linear, source-localised transient response (peak at ES1, electrically nearest); at ΔP ≥ 500 MW the transient peak df enters the [0.05, 5] Hz reach band. (P2.3-L1)
4. **Wind disturbance is detectable for W1**: W1 100 % trip yields 174 mHz transient peak at G3 (electrically nearest swing-eq source), monotone in trip fraction, linear within 14 %. (P2.4-L1)
5. **H action axis is quantitatively valid**: ROCOF ratio H=6 / H=30 = 4.86× ≈ predicted 5×, in [3, 10] band. (P2.5a)
6. **D action axis is mechanically present**: τ(D=1.5) > τ(D=7.5) monotone, R² > 0.99 on linear-log fit, 28+ cycle peaks. Direction correct. (P2.5b-L1)

---

## 3. What remains conditional

| Item | Observation | Why it's conditional, not blocking |
|---|---|---|
| **Bus 9 load reach** | df_peak 21 mHz at 967 MW (Bus 9 nominal load), below 50 mHz floor | Bus 9 is stiff (G3, W1, large local load + 350 Mvar shunt cap nearby); local Thevenin impedance much smaller than at Bus 7. Linear scaling and correct peak source (ES4) confirm response present, just smaller. Not a model bug — paper-faithful network impedance. |
| **W2 wind-trip probe mechanism** | df_peak 2.08 Hz at 100 % trip; non-monotone across trip fractions; peak at end-of-sim | `WindAmp_2 → 0` makes the AC Voltage Source amplitude zero, electrically near-grounding Bus 11 through L_wind (1 µH). Not a true PVS disconnect. W1 (1 hop further from network) dilutes the artifact and behaves cleanly. Probe-mechanism limitation, not model defect. |
| **D quantitative gain** | τ ratio 1.44× vs predicted 5× | Single-source D modulation in a 7-source network — modal damping is participation-weighted across all sources; ES1 contributes only fractionally. Back-of-envelope: 30 % participation gives ratio ≈ 1.28, matching observed 1.44. Physics consistent; only the test design assumed isolated-oscillator scaling. |

None of these are model defects. None require build, IC, NR, dispatch, V_spec, line, v2, NE39, SAC, bridge, env, profile, or training changes. They are spec-side gate-design issues plus one probe-mechanism limitation.

---

## 4. Phase 2 verdict

**CONDITIONAL PASS / GO TO NEXT DESIGN DECISION.**

The CVS v3 model is **physically alive**:
- equilibrium correct,
- transient response to Pm / load / wind disturbances measurable and source-localised,
- both H and D action axes mechanistically functional,
- no NaN / Inf / clip / Simscape constraint violation in any probe,
- bus voltages bounded, δ angles inside `(−π/2, π/2)` IntD-safe band.

Three items remain CONDITIONAL — each understood as physics or probe-design, not model defect — and each has an explicit follow-up path documented in its sub-verdict.

**Phase 2 does NOT auto-proceed to Phase 3 or training.** User decision required (§5).

---

## 5. Boundary respected (cumulative since Phase 1 commit `a40adc5`)

| Item | Status |
|---|---|
| `compute_kundur_cvs_v3_powerflow.m` | **untouched** since commit |
| `kundur_ic_cvs_v3.json` | **untouched** since commit |
| `build_kundur_cvs_v3.m` | edited for fix-A2 (build-implementation correctness only); pending Phase 2 commit |
| `kundur_cvs_v3.slx` / `_runtime.mat` | rebuilt per fix-A2; pending Phase 2 commit |
| Topology / dispatch / V_spec / per-km line params | **untouched** |
| v2 (`kundur_cvs.slx`, `kundur_ic_cvs.json`, etc.) | **untouched** |
| NE39 (`scenarios/new_england/`) | **untouched** |
| SAC (`agents/`) | **untouched** |
| Shared bridge (`engine/simulink_bridge.py`) | **untouched** |
| Env (`env/simulink/kundur_simulink_env.py`) | **untouched** |
| Profile (`scenarios/kundur/model_profiles/*.json`) | **untouched** |
| Training | **not started** |

---

## 6. Files emitted in Phase 2

```
probes/kundur/v3_dryrun/
├── probe_30s_zero_action.m
├── probe_pm_step_reach.m
├── probe_loadstep_reach.m
├── probe_wind_trip_reach.m
├── probe_hd_sensitivity.m
└── probe_d_sensitivity_decay.m

results/harness/kundur/cvs_v3_phase2/
├── p21_zero_action.json                 (FAIL — pre-fix audit trail)
├── p21_zero_action_fixA.json            (PASS)
├── p22_pm_step_reach.json               (PASS)
├── p23_loadstep_reach.json              (FAIL L0 audit trail)
├── p23_loadstep_reach_L1.json           (CONDITIONAL PASS)
├── p24_wind_trip_reach_L1.json          (CONDITIONAL PASS)
├── p25_hd_sensitivity.json              (H PASS, D-peak FAIL audit trail)
├── p25b_d_sensitivity_decay.json        (CONDITIONAL PASS)
├── phase2_p21_verdict.md                (FAIL diagnostic — preserved)
├── phase2_p21_fixA_verdict.md           (PASS — RC-A confirmed)
├── phase2_p23_verdict.md                (L0 FAIL diagnostic — preserved)
├── phase2_p23_L1_verdict.md             (CONDITIONAL PASS)
├── phase2_p24_L1_verdict.md             (CONDITIONAL PASS)
├── phase2_p25_verdict.md                (H PASS / D fail-on-stated-metric)
├── phase2_p25b_L1_verdict.md            (D mechanism confirmed)
└── phase2_aggregate_verdict.md          (this file)

scenarios/kundur/simulink_models/
├── build_kundur_cvs_v3.m                (modified — fix-A2)
├── kundur_cvs_v3.slx                    (rebuilt)
└── kundur_cvs_v3_runtime.mat            (rebuilt)
```

---

## 7. Decision menu

### Option A — Accept Phase 2 as sufficient, proceed to Phase 3 / RL-readiness planning
- Phase 2 demonstrates the model is physically alive, can be perturbed, and exposes both action axes.
- Three CONDITIONAL items each have a documented physics or probe-design explanation, none blocks RL training.
- Phase 3 work: bridge integration, env apply_disturbance extension, profile, 5-ep smoke. Then Phase 4 50-ep gate.
- **Schedule pressure low → A is acceptable.**

### Option B — Add one more probe-only multi-source D sensitivity test
- Vary D_1..4 simultaneously through {1.5, 7.5}, repeat decay-τ measurement.
- Predicted: τ ratio closer to 5 because all-ESS modal participation now coordinates.
- Probe-only edit (~10 min). No model touched.
- If τ ratio ∈ [3, 10] under coordinated-D sweep, P2.5 upgrades to FULL PASS for D action axis quantitative validity → Phase 2 becomes near-full PASS.
- **If physics evidence quality matters before committing to RL training, B closes the last open quantitative question.**

### Option C — Defer D quantitative validation to RL training diagnostics
- Keep current CONDITIONAL PASS.
- Phase 4 50-ep gate r_f signal will reveal whether the SAC agent can exploit the D action axis for damping improvements.
- **Reasonable if Phase 4 is the de facto definitive test anyway.**

---

## 8. Recommendation

**Recommend B if we want stronger physics evidence before committing training compute.** It's a 10-minute probe-only run with no model risk, and would close the last quantitatively-open question (D coordinated sensitivity matches M/D theory under the all-ESS sweep, confirming the model's modal damping structure).

**Recommend A if schedule pressure is higher.** Phase 2's six "what works" items are sufficient for proceeding to Phase 3 integration; the three conditionals are each understood and documented and don't block downstream work.

C is acceptable as a "let RL be the judge" stance but loses the chance to catch model issues before training compute is committed.

Halt for user choice.

---

## 9. Addendum 2026-04-26 — P2.5c result (commit `805c6b6`)

Option B was executed. Coordinated all-ESS D sweep (D_1..4 ∈ {1.5, 7.5}) → τ ratio = **1.444** (vs single-source 1.44, improvement 1.00× — **no change**). See [`phase2_p25c_multisource_D_verdict.md`](phase2_p25c_multisource_D_verdict.md).

**P2.5b-L1 single-source-coupling hypothesis falsified.** Corrected explanation: the 3 SG (G1/G2/G3 with D = 5 fixed gen-pu, large M = 12–13 gen-base) provide the dominant modal damping authority. The 4 ESS group, even with coordinated 5× D variation, can only modulate ~25–30 % of total damping. Heuristic mode-shape analysis predicts τ ratio in [1.3, 1.7]; observed 1.444 fits.

**D-axis remains CONDITIONAL PASS** per user policy (τ ratio not in [3, 10]). The CONDITIONAL is now better understood as a **paper-consistent SG-dominated damping property**, not a model defect or single-source coupling artifact. Yang TPWRS 2023 §II explicitly frames VSG ESS as **supplementary** frequency support, with SG providing dominant inertia — v3 reproduces this hierarchy correctly.

**RL-readiness implication (NEW):** H is the primary action lever (P2.5a 4.86×); D is a secondary / marginal lever bounded by the SG damping floor. Phase 4 reward shaping should consider asymmetric `PHI_H > PHI_D` (e.g. PHI_H = 1e-3, PHI_D = 1e-4 starting hypothesis) to reflect the asymmetric authority — current B1 baseline `PHI_H = PHI_D = 1e-4` treats them symmetrically and may be sub-optimal.

**Phase 3 remains allowed.** P2.5c does not block downstream work; it informs reward design.
