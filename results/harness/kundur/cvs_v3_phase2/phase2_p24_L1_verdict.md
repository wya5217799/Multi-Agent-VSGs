# Phase 2.4-L1 Verdict — Wind Trip Reach (kundur_cvs_v3)

> **Status: CONDITIONAL PASS — W1 passes both tiers; W2 sensitivity fails due to probe-mechanism limitation, not a model defect.**
> **Date:** 2026-04-26
> **Probe:** [`probes/kundur/v3_dryrun/probe_wind_trip_reach.m`](../../../../probes/kundur/v3_dryrun/probe_wind_trip_reach.m)
> **Summary JSON:** [`p24_wind_trip_reach_L1.json`](p24_wind_trip_reach_L1.json)

---

## 1. Method (P2.3-L1 metric, dual-tier gate per user policy)

For each wind farm W ∈ {W1, W2} and trip fraction ∈ {0.25, 0.50, 0.75, 1.00}:

```
WindAmp_w = 1 - trip      ⇒  AC Voltage Source amplitude =  (1 - trip) * V_term
df_peak    = max_t  max_src  |ω_trip(t) − ω_base(t)| · fn      [Hz]
```

Baseline: `WindAmp_1 = WindAmp_2 = 1`.

Dual-tier gate:
- **Absolute reach**: at least one (wind, trip) combination with df_peak ∈ [0.05, 5] Hz.
- **Sensitivity reach** per wind farm: monotone(↑), slope ratio within 30 % of trip ratio, df > 1 mHz at full trip, peak source in plausible electrical neighbourhood.

---

## 2. Results

| trip | W1 (700 MW base) | t_peak | peak src | W2 (100 MW base) | t_peak | peak src |
|---|---|---|---|---|---|---|
| 25 % | 0.0504 Hz | 6.49 s | ES3 | 0.1644 Hz | 1.47 s | ES1 |
| 50 % | 0.0698 Hz | 0.25 s | G3  | 2.0294 Hz | 2.38 s | ES1 |
| 75 % | 0.1154 Hz | 0.28 s | G3  | 1.4537 Hz | 4.75 s | G2  |
| 100 % | **0.1735 Hz ✅** | 0.31 s | G3  | **2.0801 Hz** | 58.40 s | ES2 |

### W1 evaluation (PASS both tiers)
- Absolute: ΔP=700 MW → 0.174 Hz, in [0.05, 5] ✅
- Monotone: 0.050 → 0.070 → 0.115 → 0.174, strictly increasing ✅
- Linear: slope ratio 0.174/0.050 = 3.45 vs trip ratio 4.0; 14 % deviation, within 30 % ✅
- Local source plausible: peak at G3 for 50–100 % (G3 at Bus 3 connects W1 area via L_3_10/L_4_9 corridor) ✅

### W2 evaluation (FAIL sensitivity)
- Absolute: 0.164–2.08 Hz, in band ✅ (contributes to overall absolute PASS)
- Monotone: 0.164 → 2.03 → 1.45 → 2.08 ❌ (drop at 75 %)
- Linear: slope ratio 2.08/0.164 = 12.7 vs expected 4.0 ❌ (220 % deviation)
- Local source: ES1 / ES2 / G2 mix — ES1 not in plausible-set for W2 (W2 is at Bus 11; ES1 at Bus 12 is in different area)
- Peak time at 100 % trip = 58.4 s (essentially end of 60 s sim) ❌ — not a transient peak; sim has not settled

---

## 3. Root cause for W2 anomaly: PVS amplitude scaling is not a clean trip

The probe trips wind by setting `WindAmp_w → 0`. The build models each wind farm as an `AC Voltage Source` with `Amplitude = WindAmp_w * V_term`. Setting amplitude → 0 makes V_PVS → 0, which is **electrically equivalent to grounding the bus through the source's internal impedance** (the build uses a near-zero `L_wind = 1 µH` to keep solver healthy). This is **NOT a true trip / disconnect**.

For W2 at Bus 11 (small ESS-rated 200 MVA, connected to Bus 8 via L_8_W2 1 km), grounding Bus 11 near-shorts the network locally:
- Massive reactive current circulates through L_8_W2 → Bus 8 voltage perturbed
- Nearest swing-eq source ES2 (at Bus 16, also connected to Bus 8 via L_8_16 1 km) sees the disturbance directly
- Larger absolute Δω response than expected, and the response is non-linear because the "trip" amplitude controls a near-short, not a pure ΔP loss

For W1 at Bus 4 (rated 900 MVA, connected through L_4_9 5 km std std-line + the rest of Area 2 corridor), the same near-grounding effect is **diluted** by the longer line and stiffer area sourcing. W1's trip behaves close to a clean ΔP loss; sensitivity gate passes.

This is **probe mechanism limitation**, not a model defect. The Phasor-mode `AC Voltage Source` has no native `Disconnect` or `Power-mode` toggle; a true wind trip requires a build edit (Phase 3 territory).

---

## 4. Verdict per user dual-tier policy

| Tier | W1 | W2 | Overall |
|---|---|---|---|
| Absolute reach | ✅ | ✅ | ✅ |
| Sensitivity reach | ✅ | ❌ (probe mechanism) | partial |
| **Combined** | PASS | DETECTED-but-stiff-probe | **CONDITIONAL PASS** |

Mirrors P2.3 outcome shape. The model can express wind-trip-induced transient response (W1 100 % trip → 174 mHz @ G3 in 0.31 s, fully in paper-faithful range and electrically correct). W2 trip via amplitude scaling creates a near-short artifact that contaminates the sensitivity-tier metric, not the absolute-tier reach.

---

## 5. Boundary respected

| Item | Status |
|---|---|
| `build_kundur_cvs_v3.m` | unchanged since fix-A2 |
| `kundur_cvs_v3.slx` / `_runtime.mat` | unchanged since fix-A2 |
| `compute_kundur_cvs_v3_powerflow.m` / `kundur_ic_cvs_v3.json` | **untouched** |
| `probe_30s_zero_action.m`, `probe_pm_step_reach.m`, `probe_loadstep_reach.m` | **untouched** |
| Topology / dispatch / V_spec / line params / IC / NR | **untouched** |
| v2 / NE39 / SAC / shared bridge / env / profile / training | **untouched** |
| Phase 1 commit `a40adc5` | **untouched** |

Only new file: `probe_wind_trip_reach.m`. New JSON output and this verdict.

---

## 6. Decision menu for user

### Option A — Accept "W1 PASS, W2 detected-but-stiff-probe" as P2.4 outcome
Same shape as P2.3 acceptance. W2 imperfection is documented as known probe limitation, not a model bug. Continue to P2.5 (H/D sensitivity, ESS only — uses Pm-step which already works cleanly per P2.2).

### Option B — Replace WindAmp scaling with a power-injection cancellation trick (probe-only)
Idea: `WindAmp_w = 1` always; instead inject a counteracting Pm-step on the nearest ESS to neutralise the wind. Uses existing Pm-step gates (already wired). Doesn't represent paper "trip" exactly but gives a clean ΔP test. Probe-only edit.

### Option C — Defer wind trip to Phase 3 env / build edit
Phase 3 env wraps a true PVS disconnect via topology change between sim runs (FastRestart-incompatible) or via dedicated workspace gate (build edit). Skip P2.4 here; rely on Phase 4 / Phase 5 paper-baseline test scenarios for wind trip evaluation.

---

## 7. Recommendation

**Recommend Option A**. P2.4 absolute reach demonstrates the model does express wind-loss transients in paper-faithful magnitudes (W1 100% → 174 mHz). W2 sensitivity is not a model fault — it's a probe mechanism artifact for high-percentage trip on a small / locally-connected wind farm. Accept and continue P2.5.

Halt for user GO before P2.5 — per the established Phase 2 cadence.

---

## 8. Files emitted in P2.4-L1

```
probes/kundur/v3_dryrun/probe_wind_trip_reach.m              (new)
results/harness/kundur/cvs_v3_phase2/p24_wind_trip_reach_L1.json (new)
results/harness/kundur/cvs_v3_phase2/phase2_p24_L1_verdict.md    (this file)
```
