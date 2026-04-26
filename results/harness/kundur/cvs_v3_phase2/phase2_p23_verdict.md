# Phase 2.3 Verdict — LoadStep Reach (kundur_cvs_v3)

> **Status: FAIL — diagnostic-only halt. P2.4 / P2.5 SUSPENDED.**
> **Date:** 2026-04-26
> **Probe:** [`probes/kundur/v3_dryrun/probe_loadstep_reach.m`](../../../../probes/kundur/v3_dryrun/probe_loadstep_reach.m)
> **Summary JSON:** [`p23_loadstep_reach.json`](p23_loadstep_reach.json)

---

## 1. Gate result

| Gate | Got | Want | Pass |
|---|---|---|---|
| Bus 7 LoadStep df_max | 0.0000 Hz | ∈ [0.05, 2] | ❌ |
| Bus 9 LoadStep df_max | 0.0000 Hz | ∈ [0.05, 2] | ❌ |

System reaches new equilibrium, but **ω returns exactly to 1.0** at steady state. df_steady = 0 by construction.

---

## 2. Trajectory evidence (G1 ω, case A=open vs case B=Bus7 +100 MW)

| t (s) | ω_A (pu) | ω_B (pu) | diff (Hz × 50) |
|---|---|---|---|
|  1 | 0.9985 | 0.9987 | +9.2 mHz (still in inductor-IC kick) |
|  5 | 1.0001 | 1.0001 | −1.0 mHz |
| 10 | 1.0000 | 1.0000 | +0.1 mHz |
| 20 | 1.0000 | 1.0000 | +27 µHz |
| 30 | 0.9999999 | 0.9999999 | +2.5 µHz |
| 45 | 1.0000000 | 1.0000000 | +78 nHz |
| 60 | 1.0000000 | 1.0000000 | −5.9 nHz |

The transient diff peaks within the inductor-IC kick window at sub-mHz level, then vanishes. **No persistent Δω.**

---

## 3. Root cause (HIGH confidence)

### 3.1 Why steady Δω = 0

Each swing-equation source has a **δ integrator**: `dδ/dt = ω_n · (ω − 1)`. For δ to remain bounded at steady state, `ω_steady = 1` exactly. There is no other steady-state ω possible (governor droop is **proportional**, not integral, but the δ integrator is integral and dominates).

Mechanism of self-restoration:
1. Load step at t = 0 raises Pe demanded from network at the load bus.
2. SG see Pm < Pe → ω drops.
3. ω < 1 → δ accumulates negative drift across all sources → V_emf phase shifts.
4. Source δ drift continues until new δ-equilibrium is reached, where Pe at the source equals Pm.
5. At this equilibrium, the additional ΔP_load is supplied entirely by sources whose δ has shifted to push more Pe — at the **same Pm level**.
6. ω returns exactly to 1.0; the new operating point has different δ but identical ω.

The droop term `(1/R)·(ω−1)` adds no Pm contribution at ω = 1, so SG output Pm at steady = original Pm0. The δ integrator is the actual frequency-restoration mechanism, not the governor.

This is **correct physics** for a paper-aligned Kundur swing model. Real power systems behave the same way — droop gives only short-term frequency support; long-term restoration comes from the rotor angle redistribution (or AGC, which isn't modelled here).

### 3.2 Why the P2.3 probe design measures the wrong quantity

The probe measures `mean(ω) over [t_settle=30s, t_end=60s]` and compares cases A vs B. By construction, **both cases reach ω = 1.0 at steady state**, so diff = 0 regardless of load step amplitude. The probe captures steady-state error of a self-correcting system, which is structurally zero.

The paper's "load step disturbance" test for r_f signal training relies on the **transient peak Δω** that the RL agent must learn to damp before the δ integrator restores frequency. To measure that, the probe must:
- Apply the load step **mid-sim** (e.g. at t = t_settle + Δ), not from t = 0.
- Measure peak |ω(t) − 1| over a short window around the step event.

### 3.3 What this is NOT

- NOT a model wiring bug. Sanity check: shorting LoadStep7 to R = 1e-3 (≈ 50 GW) produces large transient ω = 1.0266 → confirms LoadStep7 IS in circuit.
- NOT an energy balance error. Pe sum at steady = 21.19 (SG) − 1.477 (ESS) = 19.71 sys-pu, plus implicit wind 8.0 = 27.71. Matches NR exactly.
- NOT a Pm/Pe scaling residual. Per-source Pe at t = 60 s exactly matches per-source NR Pm.

The model is **physically correct**. The probe asked the wrong question.

### 3.4 Note on P2.2 PASS

P2.2 Pm-step reach also faces the same δ-integrator dynamics, but the probe measures `df_max = max_t |ω(t) − 1| · fn` over the post-step window — i.e. it correctly captures the **transient peak**. P2.2 found 0.063 – 0.094 Hz peaks, consistent with paper expectation.

---

## 4. Boundary respected

| Item | Status |
|---|---|
| v2 / NE39 / SAC / bridge / env / profile / training | **untouched** |
| Phase 1 commit `a40adc5` | **untouched** |
| `compute_kundur_cvs_v3_powerflow.m` / `kundur_ic_cvs_v3.json` | **untouched** |
| `build_kundur_cvs_v3.m` | unchanged since fix-A2 (Pi-line + Pm/Pe scaling) |
| Topology / dispatch / V_spec / line params | **untouched** |

Only new file is `probe_loadstep_reach.m` and this verdict + summary JSON. No fixes applied.

---

## 5. Decision menu (request user choice)

To make P2.3 evaluable without changing physics:

### Option L1 — Probe-side: peak-Δω metric over inductor-kick-free window
Re-run probe but compare **trajectory peak** rather than mean. Compute `df_peak_steady = max_{t ∈ [t_settle, t_end]} |ω_B(t) − ω_A(t)| · fn`. With load step applied from t=0, "kick" includes both Phasor inductor IC + load step transient. May still come out ≈0 because both A and B converge to ω = 1 at the same rate after the inductor-IC settling.

### Option L2 — Build-side: wire LoadStep with workspace gate (mid-sim step event)
Match the Pm-step pattern used in build (`Clock_global` → `Relational ≥ LoadStep_t_k` → Cast → × `LoadStep_amp_k`). Replace the static-R LoadStep block with a current-source-driven equivalent or a Variable Resistor (Phasor-compatible: Three-Phase Series RLC Load with `EnableLogarithmicVoltageInput` style). Probe applies step mid-sim at t = settle + δ, measures df_peak in [step_t, step_t + 5 s].

This is a non-trivial build edit — Phasor library does not have a Variable Resistor. Need either:
- (a) Use an `AC Voltage Source` to inject ΔP via current at the bus (matches paper's "Pm step" trick on a fictitious "ESS-equivalent" load injector)
- (b) Migrate LoadStep block to a Simscape `Variable Resistor` (requires Simscape solver, which may conflict with Phasor)
- (c) Use a Pulse Generator block driving a Series RLC with switchable conductance

### Option L3 — Skip P2.3 / P2.4 and accept that load-step reach is implicit in P2.2
Since each ESS / SG already has a `Pm_step_amp` mid-sim gate, training-time load disturbances can be approximated by Pm-step on a nearby ESS (negative Pm step at ES1 ≈ load increase at Bus 7). This doesn't capture the bus-localised transient profile of a real load step, but it provides r_f signal for SAC training. P2.5 (H/D sensitivity) still meaningful if done with ESS Pm-step.

### Option L4 — Defer P2.3 / P2.4 to Phase 3 env wrapper
Phase 3 env layer can apply LoadStep mid-sim by directly calling `set_param` on the LoadStep block between bridge `step()` calls. Probe-only physics validation skipped; r_f signal verification deferred to Phase 4 50 ep gate.

---

## 6. Recommendation

**Recommend L1 first** (~5 min probe edit, no model change). If L1 also yields df ≈ 0, **then L2/L3** (build or scope decision).

P2.4 (wind trip) and P2.5 (H/D sensitivity) are SUSPENDED until P2.3 is reformulated. P2.4 has the same δ-integrator structure issue; P2.5 measures Δf vs M/D ratio post-step, so requires a working step event mechanism.

---

## 7. Files emitted in P2.3 attempt

```
probes/kundur/v3_dryrun/probe_loadstep_reach.m              (new)
results/harness/kundur/cvs_v3_phase2/p23_loadstep_reach.json (FAIL — current)
results/harness/kundur/cvs_v3_phase2/phase2_p23_verdict.md   (this file)
```

No build / IC / NR / dispatch / V_spec / topology / line param changes.
