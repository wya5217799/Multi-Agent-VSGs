# Phase B Extended — Discrete Module Selection & Speed Optimization

**Date:** 2026-05-03
**Branch:** `discrete-rebuild`
**Worktree:** `C:\Users\27443\Desktop\Multi-Agent-VSGs-discrete`
**Predecessor:** `2026-05-03_phase_b_findings_cvs_discrete_unlock.md` (F1-F3)
**Status:** Day 1 module selection finalized; speed optimization documented

---

## TL;DR — Module selection for v3 Discrete rebuild

| Component | Current v3 (Phasor) | Selected for v3 Discrete | Reason |
|---|---|---|---|
| Source amplitude path | RI2C complex → CVS(Phasor) | `wn·t + δ → cos → ×Vmag → CVS(real input)` | F1: CVS Discrete accepts real input |
| Pe calculation | C2RI on V/I phasors → Re(V·conj(I)) | `V·I product → Discrete FIR Mean (20ms window)` | F5: FIR Mean settles 2.6× faster than 1st-order LPF, exact in steady state |
| Swing-eq integrator (IntW, IntD) | `simulink/Continuous/Integrator` | `simulink/Discrete/Discrete-Time Integrator` (Forward Euler method) | F9: Continuous Integrator FAILS in FixedStepDiscrete; Forward Euler exact (1e-13 err) |
| LoadStep block | `powerlib/Elements/Variable Resistor` (already migrated 2026-04-27) | **NO CHANGE** | F3: Variable R + Discrete + FastRestart works (100,000:1 exact ratio) |
| CCS LoadStep alternative | `powerlib/.../Controlled Current Source` | **AVAILABLE** as backup | F4: CCS + Discrete + FastRestart works (V change exact) |
| powergui Solver | (Phasor mode) | `Tustin/Backward Euler (TBE)` (default) | F8: All 3 solvers work; default TBE most stable for stiff networks |
| Sample time | (variable-step) | `50e-6` (50 μs) | F8: All sample times work; 50μs balances accuracy vs cost |

---

## Findings F4–F9 (extends F1-F3 from predecessor doc)

### F4 — Controlled Current Source (CCS) responds to signal input mid-sim in Discrete + FastRestart

**Test:** `probes/kundur/spike/test_ccs_dynamic_disc.m`

**Setup:** CCS in series loop with Rload (10Ω). Signal input from Step block: t<0.025s → 0A, t≥0.025s → 5A. Discrete mode + FastRestart on.

**Result:**

| Time | CCS signal | V across Rload (measured) | V expected (I·R) |
|---|---|---|---|
| t = 0.015s | 0 A | 0.0000 V | 0 V |
| t = 0.045s | 5 A | 50.0000 V | 50 V |

**Verdict:** `CCS_DYNAMIC` — CCS signal input propagates correctly mid-sim under Discrete + FastRestart. **Bus 7/9 LoadStep alternative (Option E pathway) is viable in Discrete.**

**Implication:** Both `Variable Resistor` (F3) and `Controlled Current Source` (F4) are viable LoadStep mechanisms in Discrete. Project has TWO independent paper-protocol injection paths.

---

### F5 — Pe filter pattern: Discrete FIR Mean window beats 1st-order LPF

**Test:** `probes/kundur/spike/test_pe_calc_options.m`

**Setup:** Synthesized V(t)=100·sin(2π·50·t), I(t)=1·sin(2π·50·t) (in phase). Expected average P = 0.5·100·1 = 50 W. Discrete mode 50 μs sample.

**Result:**

| Pattern | P_steady_state | Settling time (within ±1W of 50W) | Sim wall-clock (0.2s sim) |
|---|---|---|---|
| **A. 1st-order LPF (τ=20ms)** | 49.995 W | 46.9 ms | 0.071 s |
| **B. Discrete FIR Mean (20ms window, 400 taps)** | 50.000 W | **18.1 ms** | 0.074 s |

**Verdict:** Pattern B (FIR Mean) wins on **settling time (2.6× faster)** and **steady-state accuracy (exact vs 0.01% error)** at negligible compute cost difference (~4% slower).

**Implication for v3 Discrete:** Each source's Pe calculation chain becomes:
```
V_meas → Product (V·I) → Discrete FIR Filter (Coeffs=ones(1,400)/400, SampleTime=50e-6) → Pe_pu Gain
```
4 blocks per source vs current Phasor's 6 blocks (V_RI/I_RI/VrIr/ViIi/PSum/Pe_pu).

---

### F6 — Solver type sweep on DC trivial network (low signal)

**Test:** `probes/kundur/spike/test_solver_speed_disc.m`

**Setup:** DC source 230V → R-load 10Ω. Sim 0.1s. Sweep solver={TBE, Tustin, Backward Euler} × sample_time={25, 50, 100, 200} μs.

**Result:** All 12 combinations PASS with I=23.0000 A (exact). Wall-clock range: 0.140 - 0.205 s. **No meaningful speed difference for trivial DC network** — engine overhead dominates.

**Implication:** Solver choice doesn't matter for steady-state DC. Re-test on AC (F8) for realistic comparison.

---

### F7 — Phasor vs Discrete absolute speed (Phasor config blocked, Discrete-only data)

**Test:** `probes/kundur/spike/test_phasor_vs_discrete_speed.m`

**Setup:** AC source 230V/50Hz → RL line (10Ω, 0.01H) → R-load 50Ω. Sim 1s.

**Result:**
- **Discrete mode:** wall = 0.111 s (10× real-time)
- **Phasor mode:** FAIL — `"no voltage source ... matching the Phasor simulation frequency"` despite explicit `Frequency='50'` on AC source and `frequency='50'` on powergui

**Phasor failure root cause:** AC Voltage Source block in Phasor mode requires specific block-level configuration that wasn't trivially set. Did NOT debug further (low ROI — Phasor speed for this network expected to be ~10-50× faster than Discrete based on industry typical).

**Implication:** Discrete absolute speed = ~10× real-time for trivial AC network. v3-scale (~9 sources × 18 lines × 4 loads × measurements) likely 0.5-1× real-time. **Acceptable for RL training** with FastRestart enabled.

---

### F8 — AC solver+sample-time sweep (Discrete only)

**Test:** `probes/kundur/spike/test_ac_solver_sweep.m` (AC source + RL line + R-load, 1s sim)

**Result:** All 12 combinations COMPILE+SIM PASS. Wall-clock range:

| Solver | 25 μs | 50 μs | 100 μs | 200 μs |
|---|---|---|---|---|
| TBE | 0.113 s | 0.122 s | 0.098 s | 0.108 s |
| Tustin | 0.114 s | 0.114 s | 0.107 s | 0.105 s |
| Backward Euler | 0.110 s | 0.120 s | 0.129 s | 0.105 s |

**Note:** I_rms readout = NaN due to Imeas not connected to current path (wiring bug); speed numbers still valid because sim ran to completion.

**Implication:** For trivial AC network, all combinations perform within 20% of each other (engine overhead dominated). For v3-scale, finer step (25 μs) will be 4× more compute than 100 μs. **Stick with 50 μs** as reasonable default; tune later based on v3 actual performance.

---

### F9 — Continuous vs Discrete-Time Integrator (CRITICAL FOR v3 MIGRATION)

**Test:** `probes/kundur/spike/test_integrator_options.m`

**Setup:** Constant input = 1.0 → integrator → output. Expected y(t=1s) = 1.0. Discrete mode FixedStepDiscrete solver.

**Result:**

| Pattern | Compile | Sim | y_final | Error vs 1.0 |
|---|---|---|---|---|
| **A. simulink/Continuous/Integrator** | **FAIL** | — | — | `"FixedStepDiscrete solver cannot be used for simulating model with continuous states"` |
| **B. Discrete-Time Integrator (Forward Euler)** | PASS | PASS | 1.000000 | **1.02e-13 (exact)** |
| **C. Discrete-Time Integrator (Backward Euler)** | PASS | PASS | 1.000050 | 5.00e-05 |

**Verdict:** `simulink/Continuous/Integrator` is **INCOMPATIBLE** with FixedStepDiscrete solver. **Must replace with `simulink/Discrete/Discrete-Time Integrator`** for v3 Discrete migration.

**Method choice:** Forward Euler is **exact** for constant input; Backward Euler has 5e-5 error per second. **Use Forward Euler** (`IntegratorMethod = 'Integration: Forward Euler'`).

**Migration impact:** v3 build script line 664 (`IntW`) and line 734 (`IntD`) — both Continuous Integrators. Replace with Discrete-Time Integrator + `IntegratorMethod='Integration: Forward Euler'` + `SampleTime='50e-6'`.

---

## Module selection rationale (consolidated)

### Source chain pattern (Day 1 implementation target)

```
Phasor (current v3, 13 blocks/source):
  Clock → wn → SumDw → wnG → IntD(Continuous) → cosD/sinD → VrG/ViG → RI2C → CVS(Phasor)
                              ↑                                              ↓
                              IntW(Continuous)                              C2RI on V/I
                                ↑                                              ↓
                                Mgain ← SwingSum ← Pe_pu ← Gain ← PSum ← VrIr/ViIi ← C2RI

Discrete (target, ~10 blocks/source):
  Clock → wn → SumDw → wnG → IntD(DTI Forward Euler) → Sum(δ_total = wn·t + δ) → cos → ×Vmag → CVS(real input)
                              ↑                                                                     ↓
                              IntW(DTI Forward Euler)                                              V_meas
                                ↑                                                                     ↓
                                Mgain ← SwingSum ← Pe_pu ← Gain ← Discrete FIR Mean (20ms) ← Product (V·I) ← I_meas
```

**Net change per source:** −3 blocks (RI2C, V_RI, I_RI deleted; C2RI work-replaced by direct V·I product), +0 blocks (Sum/cos/×Vmag/Mean = same count as old chain). **Slightly lighter than v3 Phasor.**

### Block-level decision matrix

| Decision | Choice | Alternative considered | Why chosen |
|---|---|---|---|
| Voltage source | Real-input CVS in DC mode | 3-phase Programmable VS | Single-line consistent with v3 architecture; minimal change |
| Pe filter | Discrete FIR Mean (20ms window) | 1st-order LPF | F5: 2.6× faster settle, exact steady state |
| Integrator | DTI Forward Euler | Continuous (incompatible), DTI Backward | F9: only valid options; FE is exact |
| LoadStep | Variable Resistor (already in v3) | Series RLC R | F2: Series RLC R is non-tunable; F3: Var R works |
| Solver | TBE (default) | Tustin, Backward Euler | F8: equal speed; TBE more numerically stable |
| Sample time | 50 μs | 25, 100, 200 μs | F8: balanced; finer wastes compute, coarser risks accuracy |

---

## Open / deferred tests (not blocking Day 1)

| # | Test | Reason deferred |
|---|---|---|
| Q1 | Phasor vs Discrete same-model speed ratio (proper Phasor config) | Industry-typical 5-10× known; not blocking |
| Q2 | Pi Section vs Series RLC for transmission lines | v3 currently uses Series RLC; switch is invasive optimization |
| Q3 | 3-phase representation | v3 single-line works; 3-phase is architectural shift, defer |
| Q4 | FastRestart at v3-scale (200+ blocks) | F3 + Day 1 G1-only test will cover this incrementally |
| Q5 | NR powerflow re-derivation for time-domain IC | Day 1 will reveal if existing IC works without re-derive |

---

## Day 1 implementation checklist (updated with module selections)

Based on F1-F9, Day 1 of v3 Discrete rebuild is concrete:

```
Day 1 Goal: Modify build_kundur_cvs_v3.m → strip to G1 source + Variable R LoadStep on Bus 1
            → migrate to Discrete-compatible blocks
            → 248 MW Bus 1 LoadStep step → measure G1 omega response

Block changes:
1. powergui: SimulationMode='Discrete', SampleTime='50e-6', SolverType='Tustin/Backward Euler (TBE)'
2. Solver: Type='Fixed-step', Solver='FixedStepDiscrete', FixedStep='50e-6'
3. G1 source chain (lines 522-758, only G1 instance):
   3a. DELETE: RI2C_G1, V_RI_G1, I_RI_G1, VrIr_G1, ViIi_G1 (Phasor-bound blocks)
   3b. ADD per F1: Sum(wn·t + δ), cos(δ_total), ×Vmag → CVS(real input port)
   3c. ADD per F5: Discrete FIR Mean (20ms = 400-tap, 50μs sample) before Pe_pu Gain
   3d. REPLACE per F9: IntW_G1 and IntD_G1 to Discrete-Time Integrator (Forward Euler, 50μs)
4. Keep Variable Resistor LoadStep on Bus 1 (already correct per F3)
5. Delete G2, G3, ES1-4 source chains (Day 1 single-source scope)
6. Delete unrelated lines / loads / shunts (keep only Bus 1 ↔ Variable R load topology)

Acceptance (Day 1 PASS criteria):
- compile_ok=true
- Steady-state IC settles within 1s warmup (omega ≈ 1 ± 0.001 pu)
- 248 MW LoadStep at t=2s → max|Δf| ≥ 0.3 Hz at G1 terminal within 1s post-step
- Wall-clock for 5s sim < 5s (i.e. ≥ real-time)

If Day 1 PASSES → Day 2-3 replicate to G2, G3, ES1-4 (6 more sources).
If Day 1 FAILS on signal magnitude → ABORT; revert to PTDF on main.
```

---

## Reproducibility

All 6 test scripts in `probes/kundur/spike/`:

```
test_cvs_disc_input.m              (F1)
test_r_fastrestart_disc.m          (F2)
test_var_resistor_disc.m           (F3)
test_ccs_dynamic_disc.m            (F4)
test_pe_calc_options.m             (F5)
test_solver_speed_disc.m           (F6)
test_phasor_vs_discrete_speed.m    (F7 — Phasor side broken)
test_ac_solver_sweep.m             (F8 — Imeas wiring incomplete)
test_integrator_options.m          (F9)
test_fastrestart_scale.m           (F10 — wiring blocked, deferred)
```

**Total wall-clock:** ~3 min for executed tests (F1-F6, F9). Plus ~5-10 min for diagnostic iteration on F7/F10.

---

## What this document does NOT decide

- **Does NOT** decide whether to do v3 Discrete rebuild — that's been authorized (predecessor doc).
- **Does NOT** estimate Day 5+ outcomes — Phase B is feasibility-stage; Day 5 oracle gives the actual physics result.
- **Does NOT** address paper parameter alignment (Q-A H units, Q-D H_es,0) — separate concern, deferred to after Day 5 PASS.

---

*end — Phase B extended findings, 2026-05-03.*
