# Phase 1 Next Steps — Resume Guide

**Status as of 2026-05-03:** Phase 0 PASS (committed), Phase 1.1 partial (header + powergui only).

---

## Concrete next session checklist (pick up here)

### Phase 1.1 remaining (estimated 1-2 days focused work)

The build script `scenarios/kundur/simulink_models/build_kundur_cvs_v3_discrete.m`
currently halts with explicit error at line ~225 to prevent partial builds.
Remove the `error(...)` call only after completing all 4 patches below.

#### Patch A: Source-chain RI2C+CVS → sin×3 CVS (per source × 7)

**Source loop iterates over 7 entries** (4 ESS + 3 SG). Each iteration's pattern needs replacement:

**OLD (Phasor, lines ~540-575 + 740-758):**
```
1 CVS subsystem (spsControlledVoltageSourceLib/Controlled Voltage Source)
1 single-phase Vmeas + Imeas
Pe via Complex-to-Real-Imag → Vr·Ir + Vi·Ii
Signal: cos(δ) → VrG → RI2C/1
        sin(δ) → ViG → RI2C/2
        RI2C → CVS/1 (single complex input)
```

**NEW (Discrete, recipe from `probes/kundur/spike/build_minimal_smib_discrete.m`):**
```
3 single-phase CVS blocks (CVS_<src>_A, _B, _C) in Y-config to common GND
Three-Phase V-I Measurement (powerlib, verified Discrete-compatible)
Pe via V·I element-wise + sum-collapse across 3 phases
Signal: theta_<src> = wn·t + δ_<src>  (per-source IntD output)
        sinA = sin(theta_<src>) × Vpk_<src>
        sinB = sin(theta_<src> - 2π/3) × Vpk_<src>
        sinC = sin(theta_<src> + 2π/3) × Vpk_<src>
        sinA → CVS_<src>_A/1 ;  sinB → CVS_<src>_B/1 ;  sinC → CVS_<src>_C/1
```

**Vpk conversion:** `Vpk_<src> = V_emf_pu_<src> × Vbase × sqrt(2/3)` (line-to-neutral peak)

**Where the 7 sources connect to network:** Each source's 3 RConn1 outputs go
to the 3-phase bus where v3 currently connects via `local_register_at_bus(...)`.

#### Patch B: Pe calculation per source (×7)

**OLD (lines ~576-605):**
```matlab
Complex-to-Real-Imag(V) → V_RI/1, /2 = Re/Im
Complex-to-Real-Imag(I) → I_RI/1, /2 = Re/Im
Vr*Ir + Vi*Ii → P (sys-pu after Pe_scale gain)
```

**NEW:**
```matlab
Three-Phase V-I Measurement gives Vabc (3-vec) and Iabc (3-vec)
PeProd = Vabc .* Iabc  (element-wise, gives 3-vec instantaneous power)
PeSum = sum(PeProd, 1)  (collapse 3 dims → scalar)
Pe_pu = PeSum × (1/Sbase)  (convert W → sys-pu)
```

**Caveat:** Discrete instantaneous V·I oscillates at 2× f_n = 100 Hz.
For RL training noise reduction, optionally add a low-pass filter
(Transfer Fcn `1/(s/(2π·5)+1)` for 5Hz LPF) before feeding swing eq.
**For Phase 1.1 verification, skip the LPF** — instantaneous Pe is fine
for compile/IC checks. Add LPF in Phase 1.4 if RL noise becomes an issue.

#### Patch C: LoadStep R-block → Breaker+Load (×2 buses: 14, 15)

**Current v3 (compile-frozen, PROVEN dead — see test_r_fastrestart_disc.m):**
```matlab
add_block('powerlib/Elements/Series RLC Branch', 'LoadStep_<lb>', ...)
set_param(...'Resistance', 'LoadStep_amp_<lb>'_to_R_expression);  % FROZEN
```

**NEW (Phase 0 verified):**
```matlab
add_block('sps_lib/Power Grid Elements/Three-Phase Breaker', 'LoadStepBreaker_<lb>')
set_param(...,'InitialState','open', 'External','off', 'SwitchTimes','[LoadStep_t_<lb>]')
add_block(sprintf('sps_lib/Passives/Three-Phase\nSeries RLC Load'), 'LoadStepLoad_<lb>')
set_param(...,'Configuration','Y (grounded)', 'NominalVoltage',num2str(Vbase),
              'NominalFrequency',num2str(fn), 'ActivePower','LoadStep_amp_<lb>',
              'InductivePower','0', 'CapacitivePower','0')
% Wire bus → Breaker → Load
```

Note: workspace var `LoadStep_amp_<lb>` is now in **Watts active power**, not
the legacy "amp" Watts that resolved to R via `Vbase²/amp`. Schema updated:
`workspace_vars.py` may need a tweak in Phase 1.1 if the LoadStep family
adapter relies on the legacy meaning.

Also note: with Breaker+Load, the load is **physically absent until t=t_step**
(breaker open). NR/IC therefore stays unchanged — `kundur_ic_cvs_v3.json`
schema still correct. The Bus 14 LS1 "pre-engaged 248 MW" Task 2 invariant
needs reinterpretation: under Breaker+Load it means "set initial Breaker
state to 'closed' for LS1, 'open' for LS2". Trigger then = open Breaker.

#### Patch D: CCS RI2C → sin×3 CCS (×4 blocks)

CCS blocks: CCSLoad_bus7, CCSLoad_bus9, ITrip_bus14, ITrip_bus15.

**Pattern (similar to source-chain Patch A but for current sources):**

OLD: 1 CCS block driven by RI2C(I_re, I_im) complex input
NEW: 3 single-phase CCS blocks driven by I_amp × sin(wn·t + θ_inj - k·2π/3)

For paper-style "trip" injection (current FROM ground TO bus = freq UP),
amplitude = workspace var `CCS_amp_<bus>` (Amperes peak), phase reference
= bus voltage angle from IC JSON (or 0 for simplicity if injection is at
network slack reference).

**Block path:** `sps_lib/Sources/Controlled Current Source` (single phase,
takes signal input). Y-config to common neutral GND.

---

### Phase 1.2 (estimated 0.5-1 day, can run in parallel with 1.1)

**Title:** Convert IC JSON numerics for time-domain interpretation.

**What to do:**
- Most IC fields directly transfer (V_emf_mag_pu, delta_rad)
- Build script reads them and converts to Vpk_ph at compile time:
  `Vpk_<src> = V_emf_mag_pu × Vbase × sqrt(2/3)`
- δ becomes IntD initial condition (already done in v3 — `deltaG0_<g>`, `delta0_<i>`)
- No JSON file changes needed — just build-script interpretation differs
- Verify: print compiled Vpk values + IC δ values for cross-check vs hand-calc

**Estimated:** 2-4 hours. Mostly write a small validation print statement
in the build script.

---

### Phase 1.3 (estimated 0.5 day)

Once Phase 1.1 source-chain rewrite + 1.2 IC mapping done:

1. Run `build_kundur_cvs_v3_discrete()` — should produce a clean .slx
2. Run `simulink_compile_diagnostics` — expect 0 errors
3. Run 1s sim with all step amplitudes = 0 → check IC settling
   - All omega should stay at 1.0 ± 0.001 (similar to Phase 0 P0.2)
   - All Pe should match Pm (energy balance at IC)

If IC settles, Phase 1 is structurally sound. Move to 1.4.

---

### Phase 1.4 (estimated 1 day)

Run paper-scale LoadStep oracle on full Discrete v3:

- 248 MW step at Bus 14 (paper LS1)
- 188 MW step at Bus 15 (paper LS2)
- Measure max|Δf| at each ESS
- Compare vs paper Fig.3 ~0.1-0.2 Hz expected
- If matches paper scale → **paper anchor unlocked**, move to RL training side
- If smaller → diagnose (network impedance? IC mismatch?)
- If larger → likely Pm-step / governor missing, calibrate

---

## Files in this worktree (state at 2026-05-03 commit fb2ee91)

### Committed:
- `probes/kundur/spike/build_minimal_smib_discrete.m` — Phase 0 oracle build
- `probes/kundur/spike/minimal_smib_discrete.slx` — Phase 0 oracle model
- `probes/kundur/spike/build_minimal_cvs_phasor.m` — original Phasor SMIB (reference)
- `probes/kundur/spike/test_cvs_disc_input.m` — CVS input pattern test
- `probes/kundur/spike/test_r_fastrestart_disc.m` — R-block freeze test
- `quality_reports/plans/2026-05-03_discrete_rebuild_phase0_smib_first.md` — main plan
- `quality_reports/plans/2026-05-03_phase0_smib_discrete_verdict.md` — Phase 0 verdict (PASS)
- `quality_reports/plans/phase0_oracle_trace.mat` — raw trace data
- `quality_reports/plans/p0_discrete_oracle_verdict.md` — historical 2026-05-01 verdict (now superseded)
- `scenarios/kundur/simulink_models/build_kundur_cvs_v3_discrete_test.m` — historical Day-0 test build
- (plus Option G historical plans)

### Phase 1.1 partial (this commit):
- `scenarios/kundur/simulink_models/build_kundur_cvs_v3_discrete.m` — header + powergui patches only;
  has explicit `error(...)` halt to prevent partial builds. Remove halt after completing patches A-D.

---

## Quickstart for next session

```bash
cd "C:\Users\27443\Desktop\Multi-Agent-VSGs-discrete"
git status   # confirm on discrete-rebuild branch

# Read the patch list:
cat quality_reports/plans/2026-05-03_phase1_next_steps.md

# Read the SMIB recipe to copy from:
cat probes/kundur/spike/build_minimal_smib_discrete.m

# Read the v3 source-chain pattern to replace:
sed -n '540,800p' scenarios/kundur/simulink_models/build_kundur_cvs_v3.m

# When patches A-D done, remove the error() halt at line ~226 and run:
# (in MATLAB) build_kundur_cvs_v3_discrete()
```

---

## Risk register (unchanged from main plan §5)

| Trigger | Detection | Action |
|---|---|---|
| Source-chain rewrite breaks compile | Day 1 of patch A | Diagnose specific block; usually a port-mismatch fix |
| IC settle fails (omega drifts) | Phase 1.3 | Likely Vpk conversion wrong; double-check sqrt(2/3) factor |
| LoadStep oracle gives < 0.05 Hz | Phase 1.4 | Network impedance issue; revisit ESS terminal coupling |
| Sim too slow for RL (> 2× real-time) | Phase 1.4 | Increase SampleTime to 100µs or 200µs |

---

*Phase 1 next-steps — resume from any session with this guide as anchor.*
