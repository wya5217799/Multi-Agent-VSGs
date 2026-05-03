# Phase 1 Progress + Next Steps — Single Source of Truth

**Status:** AUTHORITATIVE as of 2026-05-03 EOD session
**Branch:** `discrete-rebuild`
**Worktree:** `C:\Users\27443\Desktop\Multi-Agent-VSGs-discrete`
**Supersedes:** `2026-05-03_phase1_next_steps.md` (early/stale, kept for history)

---

## §1 Completed (Phase 0 + Pre-flights + Phase 1.1 + Phase 1.1+)

### Phase 0 — SMIB Discrete Oracle ✅ PASS
- File: `probes/kundur/spike/build_minimal_smib_discrete.m`
- Result: 248 MW LoadStep → max\|Δf\| = **4.9 Hz** (16× the 0.3 Hz threshold)
- Speed: 5s sim in 0.96s wall (5.2× real-time)
- **Falsified the 2026-05-01 REJECT verdict** — Discrete is feasible
- Verdict doc: `2026-05-03_phase0_smib_discrete_verdict.md`

### Pre-flight Micro-experiments — F11/F12/F13 ALL PASS
| # | Goal | Result |
|---|---|---|
| F11 | 3-phase Π Section Line + 3-phase Load at v3-scale (230kV/100MW/100km) | I_err 0.8%, P_err 1.6%, 2.2× real-time |
| F12 | Multi-source coupling (2 ESS sharing Π line + load) | ω diff = 0, both sources synchronize |
| F13 | NR IC `(V_emf_pu, δ)` time-domain mapping with non-zero δ0 | Pe_err 0.6%, ω = 0.999999 |

**Implication**: All 3 highest-risk module unknowns locked down before integration.

### Phase 1.1 — Source-chain Helper + LoadStep + v3 Compiles
- New helper: `scenarios/kundur/simulink_models/build_dynamic_source_discrete.m`
  - Encapsulates SMIB pattern (theta + sin + 3 single-phase CVS + Y-config + VImeas + Pe via V·I)
  - Validated end-to-end on 1-source test (4.93 Hz vs Phase 0's 4.90 Hz, < 1% drift)
- v3 build script: `scenarios/kundur/simulink_models/build_kundur_cvs_v3_discrete.m`
  - 7 source chains migrated to helper (replaces ~270 lines inline pattern)
  - LoadStep R-block (compile-frozen) replaced with Three-Phase Breaker + Three-Phase Series RLC Load
  - CCS injection blocks wrapped in `if false` (Phase 1.5 to restore with sin pattern)

### Phase 1.1+ — Full Network 3-phase Migration
- 19× single-phase Pi Section Line → `sps_lib/Power Grid Elements/Three-Phase PI Section Line`
  (positive-seq + zero-seq params, propagation-speed clamp for short lines)
- 2× single-phase loads → `sps_lib/Passives/Three-Phase Series RLC Load` (Y-grounded)
- 2× single-phase shunts → Three-Phase Series RLC Load capacitive mode
- 2× Wind PVS: AC Voltage Source → Three-Phase Source NonIdeal Yg
- Bus net wiring: per-phase anchor maps (A/B/C), 3-port-per-block registration

**v3 Discrete IC Settle Test result** (`probes/kundur/spike/test_v3_discrete_ic_settle.m`):
```
G1: PASS  ω=0.99534 ± 0.00029
G2: PASS  ω=0.99545 ± 0.00026
G3: PASS  ω=0.99642 ± 0.00041
ES1: PASS ω=0.99546 ± 0.00042
ES2: PASS ω=0.99649 ± 0.00093
ES3: FAIL ω=0.99663 ± 0.00177  (oscillate)
ES4: FAIL ω=0.99669 ± 0.00102  (oscillate)
Wall: 1.74s for 1s sim (1.7× real-time)
5/7 sources settle.
```

---

## §2 Key Findings (Surprises + Constraints)

| # | Finding | Source | Impact |
|---|---|---|---|
| K1 | v3 CVS block accepts sin signal in Discrete; rejects complex phasor | F1 (test_cvs_disc_input.m) | Source chain rewrite scope = sin generators only, not CVS replacement |
| K2 | Series RLC R-block compile-frozen in BOTH Phasor and Discrete + FastRestart | F2 (test_r_fastrestart_disc.m) | Must use Breaker+Load for LoadStep, not R-block |
| K3 | Variable Resistor IS dynamic in Discrete + FastRestart (alternative LoadStep) | F3 (test_var_resistor_disc.m, parallel agent) | 2nd LoadStep mechanism available if needed |
| K4 | Continuous Integrator FAILS in FixedStepDiscrete solver | F9 (test_integrator_options.m, parallel agent) | Currently using FixedStepAuto so OK; switch to Discrete-Time Integrator if going pure Discrete |
| K5 | Three-Phase Source MUST have NonIdealSource='on' when connected to Π line | F11 + Phase 1.1+ surprise | "Ideal V parallel C" compile error otherwise |
| K6 | Helper needed per-phase Zvsg (R+L) between CVS and VImeas (was missing) | F12 surprise | Without it, ideal CVS in parallel with downstream Π-line shunt-C breaks compile |
| K7 | v3 short-line params (L_short × C_short) give v_propagation > c | Phase 1.1+ surprise | Auto-clamp C in build script to keep speed ≤ 280,000 km/s |
| K8 | NR IC `(V_emf_pu, δ_rad)` directly transferable to time-domain via Vpk·sin(ωt+δ) | F13 | No NR re-derive needed — saves 2-3 days estimated work |

---

## §3 Current State

**v3 Discrete model** (`scenarios/kundur/simulink_models/kundur_cvs_v3_discrete.slx`):
- Compiles 0 errors / 0 warnings
- 70 runtime workspace vars (matches Phasor v3)
- 5/7 sources settle to ω = 0.995 ± 0.0009 within 1s
- 2/7 (ES3, ES4) oscillate at std 0.001-0.002 around ω = 0.997
- Sim wall: 1.74s for 1s sim → ~1.7× real-time

**What works structurally**:
- Source chain (helper-based) ✓
- 3-phase network (lines + loads + shunts + wind) ✓
- LoadStep mechanism (Breaker+Load) ✓
- Bus net wiring (per-phase anchor maps) ✓
- IC numerics (V_emf_pu × sin pattern) ✓ (mostly)

**What's incomplete**:
- CCS injection (disabled, Phase 1.5)
- Continuous Integrator → Discrete-Time Integrator (FixedStepAuto bypass; Phase 1.5+ optimization)
- Pe FIR filter (currently instantaneous V·I, oscillates at 100 Hz; Phase 1.5+ optimization)

---

## §4 Known Issues — Phase 1.3 To Diagnose

### Issue 1.3a — ES3/ES4 oscillation (std 0.001-0.002)

**Symptoms**:
- ES3 at Bus 14, ES4 at Bus 15
- Both have LoadStep Breaker on their bus
- Bus 14 LS1 InitialState='closed' (paper Task 2 pre-engaged 248 MW)
- ES1 (Bus 12) and ES2 (Bus 16) settle fine — same ESS topology, different bus

**Hypotheses to test** (cheapest first):
1. LS1 closed-state transient interacting with Π-line shunt-C → temporarily set both LoadSteps `InitialState='open'` and re-test
2. Bus 14 / Bus 15 power flow imbalance from LS1 pre-engaged → re-derive NR with LS1 active and use updated Pm
3. Solver step too coarse for Breaker-Load-Π interaction → try 25 μs step
4. Three-Phase PI Section Line zero-seq params wrong → use [Lk, 1.5×Lk] instead of [Lk, 3×Lk]

**Estimated effort**: 1-2 hours

### Issue 1.3b — Steady-state ω = 0.995 (0.5% below 1.0)

**Symptoms**: All 7 sources sit at 0.995-0.997 instead of exactly 1.0 (after 1s)

**Hypotheses**:
1. Insufficient settle time — try 5s sim
2. Source Pm0 + wind output ≠ load + line losses (small mismatch)
3. NR Phasor solution has small residual that's compatible with complex-phasor steady state but not perfectly time-domain neutral

**Note**: 0.5% ω deviation = 0.25 Hz absolute. For RL training this might be acceptable (inside reward tolerance band), but worth understanding.

**Estimated effort**: 1-3 hours

---

## §5 Forward Path

| Phase | Goal | Estimated effort |
|---|---|---|
| **1.3a** | Diagnose + fix ES3/ES4 oscillation → 7/7 settle | 1-2 hours |
| **1.3b** | Diagnose ω = 0.995 vs 1.0 (or accept as tolerance) | 1-3 hours |
| **1.4** | 248 MW LoadStep oracle on full v3 Discrete (paper anchor) | 2-4 hours |
| **1.5** | Restore CCS injection (sin-driven 3-phase pattern) | 4-6 hours |
| **1.5+** | Speed optimization tests F14-F17 (see §6) | 4-8 hours |
| **1.6** | Update env config + paper_eval to use v3 Discrete | 2-4 hours |
| **1.7** | First trained policy run on v3 Discrete | 1-2 days |

**Optimistic remaining**: 4-6 days (vs original 8-12 day Phase 1 estimate)
**Realistic remaining**: 1-2 weeks (with surprise budget)

---

## §6 Training Speed Optimization — F14-F17 Roadmap

**Why deferred to Phase 1.5+**: F8 in parallel agent's work tested solver/sample-time on TRIVIAL networks (1 source + 1 load). v3-scale has 7 sources + 19 lines + complex coupling — performance can be very different. Tests must run on actual v3 Discrete model.

| # | Test | Goal | Acceptance |
|---|---|---|---|
| F14 | SampleTime sweep (50/100/200 μs on full v3) | Find fastest dt with no signal degradation | Pe accuracy < 1% degradation; wall < 1.5× of 50μs baseline |
| F15 | FastRestart speedup measurement at v3 scale | Quantify episode reset savings | FastRestart gives ≥ 5× speedup on 5s episode reset |
| F16 | Pe filter on/off speed/quality trade-off | Decide if FIR Mean (20ms) worth ~4% overhead | Cleaner Pe ≥ 50% std reduction on RL signal |
| F17 | Single-episode total wall projection | Project 200-episode training time | Single 5s episode + reset < 5s wall ⇒ 200 episodes ≤ ~30 min |

**Estimated total**: 4-8 hours after Phase 1.5 done.

---

## §7 Phase 1 Effort vs Original Estimate

| Sub-task | Original estimate | Actual (so far) | Notes |
|---|---|---|---|
| 1.1 Source-chain rewrite | 2-3 days | ~2 hours | Helper pattern + scaling factor 7 |
| 1.2 IC re-derivation | 2-3 days | **0 (F13 confirmed direct reuse)** | Major saving |
| 1.3 Measurement blocks | 2-3 days | ~1 hour | V-I Measurement directly compatible |
| 1.4 Integration + first oracle | 1-2 days | TBD (Phase 1.4 not done) | |
| 1.5 CCS restoration | (not in original) | TBD (~half day) | |
| Network 3-phase | (not in original — surprise) | ~3 hours | F11+F12+F13 pre-flights crucial |
| Pre-flight micro-experiments | (not in original) | ~2 hours | F11/F12/F13 + helper validation |

**Pattern**: when pre-flights are done, integration goes 5-10× faster than estimated. The "surprise budget" gets eaten by pre-flight discoveries (which is what they're for).

---

## §8 Architecture Decision Log (additions since 2026-05-03)

1. **Helper-based source-chain instead of inline rewrite**:
   - Pros: 1 build_dynamic_source_discrete.m owns all swing-eq + sin + CVS + V-I + Pe per source. Easier to fix bugs, test in isolation, reuse.
   - Cons: helper signature changes propagate to multiple sites. Mitigated by struct-input pattern.

2. **LoadStep: Breaker+Load (not Variable Resistor)**:
   - F3 confirmed Variable Resistor works in Discrete, but it's single-phase × 3.
   - Breaker+Load is 2 blocks, directly 3-phase, cleaner.
   - Choice locked at 2026-05-03.

3. **Solver = FixedStepAuto (not FixedStepDiscrete)**:
   - F9 says Continuous Integrator FAILS in FixedStepDiscrete.
   - Helper currently uses Continuous Integrator.
   - FixedStepAuto auto-selects ode4 (handles continuous), works for our IC test.
   - Phase 1.5+ optimization: switch to FixedStepDiscrete + Discrete-Time Integrator if speed gain warrants.

4. **CCS injection: deferred to Phase 1.5**:
   - F4 confirmed CCS works in Discrete with sin signal.
   - Not blocking Phase 1.4 oracle (LoadStep Breaker+Load is sufficient).
   - Will be restored when needed for paper-protocol comparison or freq-rise scenarios.

---

*end — Phase 1 progress + next steps as of 2026-05-03 EOD.*
