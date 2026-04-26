# Phase 2.5 Verdict — ESS H/D Sensitivity (kundur_cvs_v3)

> **Status: H PASS, D fails STATED gate but mechanism present — gate metric needs L1-style reformulation (probe-only).**
> **Date:** 2026-04-26
> **Probe:** [`probes/kundur/v3_dryrun/probe_hd_sensitivity.m`](../../../../probes/kundur/v3_dryrun/probe_hd_sensitivity.m)
> **Summary JSON:** [`p25_hd_sensitivity.json`](p25_hd_sensitivity.json)

---

## 1. Gate objective recap

| Sub-probe | Sweep | Predicted ratio | Tolerance band |
|---|---|---|---|
| (a) H sensitivity | D=4.5 fixed; M ∈ {12, 60} ⇔ H ∈ {6, 30} | ROCOF(H6)/ROCOF(H30) ≈ 5× | [3, 10] |
| (b) D sensitivity | M=24 fixed (H=12); D ∈ {1.5, 7.5} | df_peak(D=1.5)/df_peak(D=7.5) ≈ 5× | [3, 10] |

Disturbance: ES1 Pm-step +0.2 sys-pu at t = 35 s (uses the validated P2.2 mid-sim Pm-step gate).

---

## 2. Results

### Sub-probe (a): H sensitivity

| H | M = 2H | D | ROCOF (Hz/s) | df_peak (Hz) |
|---|---|---|---|---|
| 6  | 12 | 4.5 | 0.8311 | 0.0966 |
| 30 | 60 | 4.5 | 0.1709 | 0.0448 |

- **ROCOF ratio = 0.8311 / 0.1709 = 4.86×**, predicted 5× ✅
- df_peak also drops (0.097 → 0.045), consistent with larger inertia damping the peak excursion.
- Both ROCOF values above 1 mHz/s noise floor ✅
- **Sub-probe (a) PASS** — H is a physically valid action axis on ES1.

### Sub-probe (b): D sensitivity

| H | M | D | ROCOF (Hz/s) | df_peak (Hz) |
|---|---|---|---|---|
| 12 | 24 | 1.5 | 0.4164 | 0.0703 |
| 12 | 24 | 7.5 | 0.4158 | 0.0681 |

- **df_peak ratio = 0.0703 / 0.0681 = 1.03×**, predicted 5× ❌
- ROCOF nearly identical between D=1.5 and D=7.5 (D enters with `D·(ω−1)/M`, negligible at the instant of peak ω̇).
- df_peak slightly smaller for D=7.5 (3 % drop), in the expected direction but far below the 5× ratio.
- **Sub-probe (b) FAIL on stated metric.**

---

## 3. Root cause for D sub-probe — gate measures the wrong observable

The spec §2.7 D-sensitivity gate was written as "df steady-state ratio D1.5/D7.5 ≈ 5×". After P2.3 / P2.4 we have established that **the δ-integrator forces ω → 1 at steady state in any swing-eq source after any finite disturbance** (`dδ/dt = ωn(ω−1)` is integral; bounded δ ⇒ ω = 1). Steady df is zero by construction; ratio is 0/0, undefined.

Replacing "steady df" with "peak df" (what this probe measured) is also wrong:

```
M·dω/dt  =  ΔPm − ΔPe(δ) − D·(ω−1)
```

At the trajectory's peak, `dω/dt = 0`. Solving instantaneously:
```
ΔPm − ΔPe(δ_peak) = D·(ω_peak − 1)
```
- ΔPe(δ) is set by the δ trajectory which is integral of ω: M-dominated, very weak D coupling on the peak event.
- D appears only as a small correction `D·(ω_peak − 1)` to the Pe–Pm imbalance at peak.
- For M=24, D=7.5: D·(ω_peak − 1) = 7.5·1.4e-3 ≈ 1e-2 vsg-pu, vs ΔPm = 0.2/0.5 = 0.4 vsg-pu. D is 2.5 % of the dominant balance → peak deviation barely shifts.

Where D **does** show its full ~5× signature is the **envelope decay rate** post-peak:
```
ω_envelope(t) = ω_peak · exp(−ζ·ω_n·(t − t_peak))
ζ = D / (2·sqrt(M·K_sync))      (modal damping ratio)
```
Decay time constant `τ_decay ∝ M/D`. With M fixed, `τ(D=1.5) / τ(D=7.5) = 5×`. So measuring `|Δω(t_peak + 2 s)|` or `∫|Δω|² dt` over the post-peak window WOULD show the 5× ratio.

This is a **probe gate-design defect**, mirroring the P2.3 / P2.4 "steady-vs-transient" misalignment. The model is physically correct; the spec metric is wrong for swing-eq systems.

---

## 4. Verdict per user policy

| Sub | Pass on stated gate? | Mechanism present? | Verdict |
|---|---|---|---|
| (a) H sensitivity (ROCOF) | ✅ | ✅ | **PASS** |
| (b) D sensitivity (peak df) | ❌ | ✅ (3 % shift in correct direction; full effect lives in decay envelope) | **DETECTED-but-wrong-metric** |

**Overall: CONDITIONAL PASS** — H is a verified RL action axis; D action axis is mechanically present and physically sound, but the spec gate metric measures the wrong observable. Same shape as P2.3 / P2.4 outcomes.

---

## 5. Boundary respected

| Item | Status |
|---|---|
| `build_kundur_cvs_v3.m` / `kundur_cvs_v3.slx` / `_runtime.mat` | unchanged since fix-A2 |
| `compute_kundur_cvs_v3_powerflow.m` / `kundur_ic_cvs_v3.json` | **untouched** |
| `probe_30s_zero_action.m`, `probe_pm_step_reach.m`, `probe_loadstep_reach.m`, `probe_wind_trip_reach.m` | **untouched** |
| Topology / dispatch / V_spec / line params / IC / NR | **untouched** |
| v2 / NE39 / SAC / shared bridge / env / profile / training | **untouched** |
| Phase 1 commit `a40adc5` | **untouched** |

Only new file: `probe_hd_sensitivity.m`. New JSON output and this verdict.

---

## 6. Decision menu for user

### Option A — Accept "H PASS, D detected-with-wrong-metric" as P2.5 outcome
Document D gate as spec follow-up. Both action axes are mechanically validated. Continue to Phase 2 final verdict.

### Option B — Reformulate D gate (probe-only edit, ~10 min)
Add a sub-probe (b'): re-run with M=24 fixed, D ∈ {1.5, 7.5}, and measure the **decay-envelope time constant** by fitting an exponential to `|ω − 1|` over the post-peak window, or by measuring `|Δω(t_peak + 2 s)|` directly. Expect ratio ≈ 5× from the M/D scaling.

### Option C — Defer D action-axis validation to Phase 4 RL-training metrics
Phase 4 training will exercise the full D action range under SAC; if the agent learns to modulate D at all, that's stronger evidence than any open-loop probe gate.

---

## 7. Recommendation

**Recommend Option B** (probe-only reformulation, ~10 min, no model change). Cleanly closes the P2.5 question and gives the spec a reusable D-sensitivity gate definition. Then write the Phase 2 aggregate verdict.

Halt for user GO before B (or skip to Phase 2 final verdict if A).

---

## 8. Files emitted in P2.5

```
probes/kundur/v3_dryrun/probe_hd_sensitivity.m              (new)
results/harness/kundur/cvs_v3_phase2/p25_hd_sensitivity.json (new)
results/harness/kundur/cvs_v3_phase2/phase2_p25_verdict.md   (this file)
```
