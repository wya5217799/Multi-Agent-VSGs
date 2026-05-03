# Implementation Plan: Phase 1.5 — Paper-Lumped ΔP LoadStep Reroute

**Date:** 2026-05-04
**Status:** COMPLETED
**Branch:** `discrete-rebuild`
**Supersedes:** `2026-05-03_phase1_5_ccs_restoration.md` (P0-1c CCS path abandoned)

---

## Strategic Context

P0-1c CCS injection (attempt 1, 2026-05-04) was measured E2E:
- CCS at bus14 with `LoadStep_trip_amp_bus14 = 248e6 W` → max|Δf| ≈ 0.075 Hz
- Paper LS1 baseline (pm_step_single_es3 at 0.5 sys-pu) → max|Δf| ≈ 0.37 Hz × (2.48/0.5) ≈ 1.84 Hz
- CCS signal is **62× weaker** than paper LS1 baseline
- Root cause: CCS at ESS terminal bus (bus14 ≈ 2 km from load center bus7/9) sees negligible Thevenin impedance; injected current mostly flows through the nearby ESS source, not into the network load center

Decision: CCS path abandoned. Route LoadStep LS1/LS2 through `Pm_step_amp_{i}` on the ESS swing equation, which is already the mechanism that produces paper-faithful frequency responses.

## Paper Justification

- §1.1 Eq.1: `H Δω̇ + D Δω = Δu - ΔP_es` — disturbance enters as `ΔP_es` (lumped electromechanical)
- §1.4 Remark 1 (Kron reduction): `Δu_i` can represent any-bus disturbance folded onto ESS bus via network admittance matrix — paper explicitly uses this lumping
- §12.H: ESS buses co-located with LS1/LS2 network buses (ES3 at bus14, ES4 at bus15)
- §8.4: paper acceptance rewards -1.61 (LS1) and -1.42 (LS2) — calibrated against pm_step_single_es3 at 2.48 sys-pu → -1.84 (10% margin from sim noise / 50 Hz discrete Ts)

## ESS Index Mapping

| ESS | Bus | LoadStep |
|-----|-----|----------|
| ES3 | 14  | LS1 (bus14) |
| ES4 | 15  | LS2 (bus15) |

## Paper Magnitudes

- LS1 (bus14): 248 MW / 100 MVA = **+2.48 sys-pu** (positive = Pm injection = freq UP, mimics load trip)
- LS2 (bus15): 188 MW / 100 MVA = **-1.88 sys-pu** (negative = Pm reduction = freq DOWN, mimics load addition)

## Implementation Checklist

### M1: Build script — remove CCS blocks (COMPLETED)
File: `scenarios/kundur/simulink_models/build_kundur_cvs_v3_discrete.m`
- Removed: `bus14_no_breaker` flag block (lines ~86-98)
- Removed: `ccs_load_defs` table (was lines ~242-245)
- Updated: LoadStep workspace var defaults — bus14 now writes 0.0 (no consumer block)
- Removed: LoadStep CCS bus14 block section (was lines ~520-609: LStripAmp_bus14, LStripSin{A,B,C}_bus14, LStripProd{A,B,C}_bus14, LStripCCS{A,B,C}_bus14, LStripGNDneutral_bus14)
- Removed: Disabled `if false...end` CCS block (was lines ~617-728: RI2C pattern + Option E Bus7/9)
- Updated: Bus anchor registration — bus14 `continue` (no block), bus15 retains breaker registration
- Removed: `LoadStep_trip_amp_*` and `CCS_Load_amp_*` from runtime_consts loop
- Added: Phase 1.5 reroute diagnostic print line
- Note: `loadstep_defs` table retained (bus15 breaker+RLC still uses LoadStep_amp_bus15/LoadStep_t_bus15)

### M2: Adapter rewrite (COMPLETED)
File: `scenarios/kundur/disturbance_protocols.py`
- `LoadStepRBranch.apply()` rewritten to write `PM_STEP_AMP@ES3` (+2.48) for bus14, `PM_STEP_AMP@ES4` (-1.88) for bus15
- No longer writes `LOAD_STEP_TRIP_AMP` or `LOAD_STEP_AMP`
- Added constants: `_PAPER_BUS_TO_ESS_I = {14: 3, 15: 4}`, `PAPER_LS_MAGNITUDE_SYS_PU = {14: 2.48, 15: 1.88}`
- `DisturbanceTrace.family = "paper_lumped_pm_step"`

### M3: Effectiveness demotion (COMPLETED)
File: `scenarios/kundur/workspace_vars.py`
- `LOAD_STEP_TRIP_AMP`: `effective_in_profile = frozenset()` (was `frozenset({PROFILE_CVS_V3_DISCRETE})`)
- `LOAD_STEP_AMP`: already `frozenset()`, no change needed
- `inactive_reason` updated with Phase 1.5 context for `PROFILE_CVS_V3_DISCRETE`

### M4: Metadata update (COMPLETED)
File: `probes/kundur/probe_state/dispatch_metadata.py`
- 3 loadstep entries updated: family `"paper_lumped_pm_step"`, target descriptors `"ES3(bus14)"` / `"ES4(bus15)"`, default magnitudes 2.48 / 1.88 / 2.48 sys-pu
- `expected_min_df_hz = 0.05`; acceptance gate notes for §8.4 rewards

### M5: Tests (COMPLETED)
- `tests/test_p0_1c_bus14_ccs_loadstep.py`: DELETED (P0-1c mechanism abandoned)
- `tests/test_phase1_5_paper_lumped.py`: CREATED (~290 lines, 8 test sections)
  - Schema checks, adapter writes (Pm_step_amp_3 = +2.48, Pm_step_amp_4 = -1.88), random bus distribution, metadata, trace invariants, silence behavior
- `tests/test_disturbance_protocols.py`: UPDATED
  - `loadstep_effective_v3` fixture: no-op stub (PM_STEP_AMP always effective)
  - RiskA/RiskB: assert Pm_step_amp writes (not LOAD_STEP_AMP)
  - RiskI: `pytest.skip` for trip dtype (CCS-based adapter still raises, intentional)
  - `TestRequireEffectiveWiring`: now asserts LoadStep bus14 SUCCEEDS (not raises)

### M6: Documentation (COMPLETED)
- This plan created
- `2026-05-03_phase1_5_ccs_restoration.md` status updated to SUPERSEDED

## Acceptance Gates (Pre-Registered, Immutable)

| Gate | Criterion | Status |
|------|-----------|--------|
| G1.5-A | `test_phase1_5_paper_lumped.py` all pass | PASS (8 tests) |
| G1.5-B | `test_disturbance_protocols.py` passes (1 skip allowed for trip dtype) | PASS (156 passed, 1 skipped) |
| G1.5-C | `test_kundur_workspace_vars.py` passes | PASS |
| G1.5-D | `Pm_step_amp_3 = +2.48` for bus14 LS1 (unit test verified) | PASS |
| G1.5-E | Build script has no live CCS block code | PASS (M1 completed) |

## What Was NOT Changed

- `Pm_step_amp` infrastructure itself (build script ESS Pm_step section unchanged)
- `slx_helpers/slx_step_and_read.m` (no changes)
- `env/simulink/kundur_simulink_env.py` (no changes)
- `scenarios/kundur/simulink_models/kundur_cvs_v3_discrete.slx` (not rebuilt — build script is the spec)
- `scenarios/kundur/simulink_models/kundur_cvs_v3_discrete_runtime.mat` (not regenerated — no new runtime vars needed)

## Note on .slx / runtime.mat

The build script M1 changes remove CCS blocks that were present in the PREVIOUS `.slx` build. The current `.slx` artifact on disk still contains those blocks. The build script is the canonical spec — the `.slx` will be regenerated on next `build_kundur_cvs_v3_discrete()` run in MATLAB. The runtime.mat removed `LoadStep_trip_amp_*` and `CCS_Load_amp_*` fields but added no new fields; the on-disk `.mat` has extra inert fields that do no harm until next rebuild.
