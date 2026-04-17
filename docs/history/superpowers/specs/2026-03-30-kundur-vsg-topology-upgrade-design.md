# Design: Upgrade kundur_vsg.slx to Full Modified Kundur Topology

**Date:** 2026-03-30
**Status:** Draft
**Reference:** Yang et al., IEEE TPWRS 2023, DOI: 10.1109/TPWRS.2022.3221439

## Goal

Upgrade `kundur_vsg.slx` from a simplified 4-bus model (4 VSGs only) to the full Modified Kundur Two-Area System described in the Yang2023 paper, while preserving the existing RL training pipeline.

## Decision: Why kundur_vsg over kundur_two_area

| Factor | kundur_vsg (chosen) | kundur_two_area (rejected) |
|---|---|---|
| RL interface | Complete (signal-domain VSG + dM/dD inputs) | None |
| Solver | ode4 fixed-step Phasor (fast) | ode23t variable-step EMT (slow) |
| Frequency | 50 Hz (correct) | 60 Hz (wrong) |
| Block library | powerlib (stable) | ee_lib (shaft-lock bug) |
| Python env | KundurSimulinkEnv + SimulinkBridge | None |

The RL pipeline is the hard part and is already done. Topology expansion is MATLAB scripting work.

## Current State (4-bus)

```
Bus1(VSG_ES1) --[Line_12]-- Bus2(VSG_ES2 + Load_A1)
                                  |
                             [TieLine_23, weak]
                                  |
Bus4(VSG_ES4) --[Line_34]-- Bus3(VSG_ES3 + Load_A2)
```

- 4 VSGs are the only generation (no conventional generators, no wind)
- Loads: 200+200 MW (should be 967+1767 MW)
- 3 transmission lines total

## Target State (16-bus Modified Kundur)

```
Area 1:
  G1(Bus1) --[L_1_5]-- Bus5 --[L_5_6 x2]-- Bus6 --[L_6_7 x2]-- Bus7
  G2(Bus2) --[L_2_6]-- Bus6                                       |
                                                          Load7(967MW)
                                                          Shunt7(200Mvar)
                                                          ES1(Bus12)

Tie (weak):
  Bus7 --[L_7_8 x3, 110km each]-- Bus8 --- W2(100MW)
                                    |        ES2(Bus16)

Area 2:
  Bus8 --[L_8_9 x2]-- Bus9 --[L_9_10 x2]-- Bus10 --[L_3_10]-- G3(Bus3)
                        |                    |
                   Load9(1767MW)        ES3(Bus14)
                   Shunt9(350Mvar)      Load14(248MW, trippable)
                   ES4(Bus15)
                   Load15(188MW, switchable)

  W1(Bus4) --[L_4_9]-- Bus9
```

- 5 generators: G1, G2, G3 (conventional), W1, W2 (wind)
- 4 VSG/ESS: ES1-ES4 (RL-controlled)
- 20 transmission lines
- Loads: 967+1767 MW + shunt compensation

## Architecture Decisions

### AD-1: G1-G3 Conventional Generators → Signal-domain swing equation

Reuse the same VSG subsystem structure but with:
- Fixed H/D (no RL dM/dD input — constants set to 0)
- Governor droop: `P_ref_adjusted = P_ref0 - (omega - 1.0) / R` where R=0.05
- Parameters: H=6.5s (G1,G2), H=6.175s (G3), Sn=900 MVA
- D = 5.0 pu (typical turbine damping)

This ensures G1-G3 respond to frequency deviations (required by paper) while keeping the same block architecture as ESS VSGs.

Implementation: Create a `SG_Gen` subsystem variant with governor droop block inside, or add a `governor_enabled` constant that gates the droop feedback.

### AD-2: Wind Farms W1, W2 → Constant power Three-Phase Source

- W1: 900 MVA at Bus4, fixed V/f, no frequency response
- W2: 100 MW at Bus8, fixed V/f, no frequency response
- Rationale: Type 4 PMSG wind farms don't participate in primary frequency regulation (paper spec doc recommendation)
- Implementation: `Three-Phase Source` with R_gen, L_gen internal impedance (same as current VSG sources)

### AD-3: Transmission Line Parameters

All lines use `powerlib/Elements/Three-Phase PI Section Line` in Phasor mode.

Source: Kundur textbook standard values:
- R = 0.053 Ohm/km, L = 1.41 mH/km, C = 0.009 uF/km
- Already used in `build_kundur_simulink.m`

Line lengths (Kundur standard):
| Line | From | To | Length (km) | Parallel |
|---|---|---|---|---|
| L_1_5 | Bus1 | Bus5 | 5 | 1 |
| L_2_6 | Bus2 | Bus6 | 5 | 1 |
| L_5_6 | Bus5 | Bus6 | 25 | 2 |
| L_6_7 | Bus6 | Bus7 | 10 | 2 |
| L_7_8 | Bus7 | Bus8 | 110 | 3 (weak tie) |
| L_8_9 | Bus8 | Bus9 | 10 | 2 |
| L_9_10 | Bus9 | Bus10 | 25 | 2 |
| L_3_10 | Bus3 | Bus10 | 5 | 1 |
| L_4_9 | Bus4 | Bus9 | 5 | 1 |

VSG connection lines (short, low impedance):
| Line | From | To | R_pu | X_pu |
|---|---|---|---|---|
| L_7_12 | Bus7 | Bus12(ES1) | 0.001 | 0.02 |
| L_8_16 | Bus8 | Bus16(ES2) | 0.001 | 0.02 |
| L_10_14 | Bus10 | Bus14(ES3) | 0.001 | 0.02 |
| L_9_15 | Bus9 | Bus15(ES4) | 0.001 | 0.02 |
| L_8_W2 | Bus8 | W2 | 0.001 | 0.02 |

### AD-4: Loads and Shunt Compensation

| Location | P (MW) | Q (Mvar) | Type |
|---|---|---|---|
| Bus7 (Load7) | 967 | 100 | Constant |
| Bus9 (Load9) | 1767 | 100 | Constant |
| Bus7 (Shunt7) | 0 | -200 (cap) | Shunt compensation |
| Bus9 (Shunt9) | 0 | -350 (cap) | Shunt compensation |
| Bus14 (TripLoad1) | 248 | 0 | Switchable (breaker) |
| Bus15 (TripLoad2) | 188 | 0 | Switchable (breaker) |

### AD-5: Disturbance Mechanism

Keep existing breaker-based approach:
- `Breaker_1` at Bus14: initially closed (248 MW energized), opens to simulate load reduction
- `Breaker_2` at Bus15: initially open (0 MW), closes to simulate load increase of 188 MW
- Python controls via `set_param(Breaker, 'SwitchTimes', '[t_trip]')`

### AD-6: Simulation Settings (unchanged)

- Phasor mode, fn=50 Hz
- ode4 fixed-step, dt=0.001s
- Episode: 10s, control step: 0.2s (50 steps)

## What Changes in Python

### config_simulink.py
- `N_VSG = 4` unchanged (only ES1-ES4 are RL-controlled)
- Block path templates unchanged: `VSG_ES{idx}` names stay the same
- Breaker paths: update from `Breaker_1`/`Breaker_2` (already correct naming)
- May need to add G1-G3 block paths if we want to read their omega for observations

### kundur_simulink_env.py
- Minimal changes expected
- Observation vector stays 7-dim per agent (paper spec)
- If G1-G3 are signal-domain subsystems, their omega is logged via ToWorkspace and available for neighbor frequency calculation — but per the paper, VSG agents only observe their own bus + 2 ring neighbors (other VSGs), not conventional generators

### SimulinkBridge
- No changes needed — it only interacts with VSG_ES blocks

## Validation Criteria

After building, verify against Yang2023 spec:

1. **No-control baseline (Load Step 1: Bus14 shed 248 MW)**
   - All ES frequencies settle to +0.075 Hz steady state
   - ES4 peak: +0.13 Hz (closest to disturbance)
   - Oscillation period ~1.8s
   - ES4 power peak ~-350 MW

2. **Reward magnitude**
   - Random policy episode reward: -250 to -300 (matching Fig.4 initial)

3. **Simulation speed**
   - 10s episode completes in <30s wall time (Phasor mode)

## Files Modified

| File | Change |
|---|---|
| `scenarios/kundur/simulink_models/build_powerlib_kundur.m` | Major rewrite: 4-bus → 16-bus topology |
| `scenarios/kundur/config_simulink.py` | Minor: update breaker paths if needed |
| `env/simulink/kundur_simulink_env.py` | Minor: update block path references if needed |

## Out of Scope

- Communication topology changes (ring ES1↔ES2↔ES3↔ES4↔ES1 stays)
- SAC hyperparameter tuning
- ODE environment changes (separate topology)
- ANDES environment changes
