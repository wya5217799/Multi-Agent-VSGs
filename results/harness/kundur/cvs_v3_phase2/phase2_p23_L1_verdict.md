# Phase 2.3-L1 Verdict — LoadStep Transient-Peak Reach (kundur_cvs_v3)

> **Status: CONDITIONAL PASS — Bus 7 reach confirmed in band; Bus 9 reach detected, below-floor by physics.**
> **Original P2.3 FAIL was a probe-metric defect (steady-Δω = 0 by δ-integrator construction), NOT a model failure.**
> **Date:** 2026-04-26
> **Probe:** [`probes/kundur/v3_dryrun/probe_loadstep_reach.m`](../../../../probes/kundur/v3_dryrun/probe_loadstep_reach.m)
> **Summary JSON:** [`p23_loadstep_reach_L1.json`](p23_loadstep_reach_L1.json)
> **L0 verdict (replaced):** [`phase2_p23_verdict.md`](phase2_p23_verdict.md)

---

## 1. L1 metric definition (probe-only edit; no build / IC / NR change)

```
df_peak = max_t  max_src  |ω_step(t) − ω_baseline(t)| · fn          [Hz]
```

- Baseline = case A: both LoadStep blocks open (R = 1 e9 Ω).
- Step  = case B (Bus 7) or case C (Bus 9): set the relevant LoadStep R = V²/ΔP_W.
- Subtraction removes the inductor-IC kick that is **common** to baseline and step (the kick is identical in both cases since initial conditions are NR-derived).
- Captures the load-step-induced excursion regardless of when in the trajectory it peaks.
- Steady-state is correctly forced to zero (δ-integrator); the L0 metric measured this zero. L1 measures the peak transient envelope instead.

Gate: `df_peak ∈ [0.05, 5] Hz` for at least one ΔP in list, **per load bus**.

---

## 2. Reach scan results

| ΔP (sys-pu / MW) | Bus 7 df_peak | t at peak | peak src | Bus 9 df_peak | t at peak | peak src |
|---|---|---|---|---|---|---|
| 1.00 / 100  | 0.0222 Hz | 0.40 s | ES1 | 0.0022 Hz | 0.25 s | ES4 |
| 2.00 / 200  | 0.0443 Hz | 0.40 s | ES1 | 0.0043 Hz | 0.25 s | ES4 |
| 5.00 / 500  | **0.1101 Hz ✅** | 0.40 s | ES1 | 0.0108 Hz | 0.25 s | ES4 |
| 9.67 / 967  | **0.2099 Hz ✅** | 0.40 s | ES1 | 0.0209 Hz | 0.24 s | ES4 |

Linear scaling confirmed (df_peak ∝ ΔP) for both buses → response is **physical**, not numerical noise.

Gate evaluation:
- **Bus 7 in_band**: ΔP ∈ {500 MW, 967 MW} → in [0.05, 5] Hz ✅
- **Bus 9 in_band**: NONE in tested range → all four ΔP below 0.05 Hz ❌

---

## 3. Why Bus 9 is ~10 × less responsive than Bus 7 (physical, not bug)

For the same ΔP magnitude, peak Δω at Bus 9 is **10×** smaller than at Bus 7.

Network-side reasoning:
- **Bus 7** is in Area 1, served via L_6_7a / L_6_7b (10 km × 2 parallel) from G1 / G2. Local Thevenin impedance toward generation is moderate. ES1 (its electrically nearest VSG) sits at Bus 12 connected via L_7_12 (1 km short line); ES1 sees the Bus 7 transient strongly.
- **Bus 9** is in Area 2 with much stiffer local sourcing: G3 (719 MW) at Bus 3 connects directly via L_3_10 (5 km) → L_9_10a/b (25 km × 2); W1 (700 MW) connects directly via L_4_9 (5 km, 1 hop). The combined Thevenin impedance is much smaller. ES4 connects via L_9_15 (1 km).
- A given ΔP injected at Bus 9 is split among many parallel low-impedance return paths → less voltage perturbation at Bus 9 → smaller Pe step seen by ES4 → smaller transient ω excursion.

In paper terms: Bus 7 is the "weak load bus", Bus 9 is the "stiff load bus". The 0.05 Hz reach floor was set in spec without per-bus tuning. With v3 paper-faithful network impedances, Bus 9 simply produces smaller transient frequency events than Bus 7 for the same load step magnitude.

To bring Bus 9 into a uniform 50 mHz gate would require:
- ΔP ≈ 2.4 GW (extrapolated from 21 mHz @ 967 MW, linear) — exceeds Bus 9 nominal load 1767 MW. Not paper-compatible.

---

## 4. P2.3-L1 verdict

**CONDITIONAL PASS.**

- Reach principle confirmed: model produces linear, source-localised, transient frequency response to LoadStep at both load buses. Peak occurs ~0.25 – 0.40 s after t = 0 at the electrically-nearest ESS (ES1 for Bus 7; ES4 for Bus 9). Original P2.3 L0 FAIL was a metric defect (steady-Δω = 0 from δ-integrator), not a model failure.
- **Bus 7 LoadStep**: ✅ in [0.05, 5] Hz at ΔP ≥ 500 MW (paper test scenarios use load steps 100 – 500 MW range, so Bus 7 falls within paper-faithful test envelope at the upper end).
- **Bus 9 LoadStep**: ❌ never reaches 0.05 Hz in paper-feasible ΔP range due to network stiffness. Detected and linear, but below the spec gate floor.

The model is **physically correct**; the gate floor is a poor fit for the heterogeneous v3 network. Two interpretations:
- (i) **Pragmatic**: model does respond to load step at Bus 9 (linearity + correct peak source ES4 confirm). Phase 2 reach intent satisfied. Use spec follow-up to lower Bus 9 floor or normalise per local Thevenin.
- (ii) **Strict**: gate definition unmet for Bus 9 → escalate to L2 (mid-sim step event). L2 would resolve the ambiguity by removing inductor-IC contamination from the peak measurement, but if Bus 9 is genuinely network-stiff, L2 would still produce sub-50 mHz peaks at paper-feasible ΔP.

---

## 5. Boundary respected

| Item | Status |
|---|---|
| `build_kundur_cvs_v3.m` | unchanged since fix-A2 |
| `kundur_cvs_v3.slx` / `_runtime.mat` | unchanged since fix-A2 |
| `compute_kundur_cvs_v3_powerflow.m` / `kundur_ic_cvs_v3.json` | **untouched** |
| Topology / dispatch / V_spec / line params | **untouched** |
| v2 / NE39 / SAC / shared bridge / env / profile / training | **untouched** |
| Phase 1 commit `a40adc5` | **untouched** |

Only edits in this iteration:
- `probes/kundur/v3_dryrun/probe_loadstep_reach.m` (metric reformulation: steady-mean → transient-peak; ΔP sweep instead of single value)
- new outputs `p23_loadstep_reach_L1.json` and this verdict

L0 verdict (`phase2_p23_verdict.md`) and L0 summary (`p23_loadstep_reach.json`) preserved as audit trail.

---

## 6. Decision menu (request user choice)

### Option A — Accept "Bus 7 PASS, Bus 9 detected" as P2.3 outcome
Document Bus 9 as physically stiff (paper-faithful), proceed to P2.4 (wind trip — same δ-integrator structure but check via L1-style transient peak).

### Option B — Lower gate floor for Bus 9 only (per-bus normalisation)
Re-define gate as "df_peak/ΔP_pu > 2.0 mHz/sys-pu" (linear gain). Bus 7 = 22 mHz/sys-pu (10× threshold ✅). Bus 9 = 2.2 mHz/sys-pu (1× threshold ✅). Both pass under a sensitivity gate. Spec edit needed.

### Option C — Implement L2 (build edit, mid-sim LoadStep gate)
Replace static-R LoadStep with Pm-step-style cluster: `Clock_global → ≥ LoadStep_t_k → × LoadStep_amp_k → drives a Variable Resistor / equivalent`. Then probe applies the step at t = 30 s and measures df_peak in [30, 35 s] post-step window. Removes inductor-IC contamination cleanly. Estimated 1 – 2 hr build edit + Phasor-compatible Variable R lookup.

### Option D — Defer Phase 2.3 to Phase 3 env wrapper
Phase 3 env can apply LoadStep mid-sim by `set_param` between `step()` calls. Skip the static probe; rely on Phase 4 50 ep gate's r_f signal to confirm load disturbance is learnable.

---

## 7. Recommendation

**Recommend Option A** (accept the L1 finding as the answer for Phase 2.3). The model demonstrably responds to load steps; the gate floor is a spec-side artifact. P2.4 (wind trip) and P2.5 (H/D sensitivity) can use the same L1-style transient-peak metric. Spec follow-up should adopt the per-bus / per-source sensitivity gate (Option B) without blocking Phase 2 progress.

**Halt for user GO** before P2.4 — per user instruction "在 L1 结果出来前，不允许进入 P2.4 / P2.5".

---

## 8. Files emitted in P2.3-L1

```
probes/kundur/v3_dryrun/probe_loadstep_reach.m              (modified — L1 metric)
results/harness/kundur/cvs_v3_phase2/p23_loadstep_reach_L1.json  (new)
results/harness/kundur/cvs_v3_phase2/phase2_p23_L1_verdict.md    (this file)
```

L0 artifacts preserved for audit:
- `results/harness/kundur/cvs_v3_phase2/p23_loadstep_reach.json`
- `results/harness/kundur/cvs_v3_phase2/phase2_p23_verdict.md`
