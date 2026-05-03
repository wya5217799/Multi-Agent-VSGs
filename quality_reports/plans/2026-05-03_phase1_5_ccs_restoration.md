# Implementation Plan: Phase 1.5 — CCS Restoration on v3 Discrete

**Target path:** `quality_reports/plans/2026-05-03_phase1_5_ccs_restoration.md`
**Date:** 2026-05-03
**Status:** BLOCKED ON DESIGN (2026-05-04 attempt 1 reverted): see §0.6 for the deeper finding — Option E `if false` block uses Phasor-only Real-Imag-to-Complex pattern, incompatible with Discrete-mode powergui. Redesign required: 3-phase sin-driven Constant→Product→CCS pattern (similar to `build_dynamic_source_discrete.m` SG/ESS helper). Estimated 1-2 hr design + 3 hr implementation. All first-attempt code reverted; only this plan retains the diagnosis.
**Branch:** `discrete-rebuild`
**Supersedes (relevant section):** §5 row "1.5" of `2026-05-03_phase1_progress_and_next_steps.md`
**Authored by:** planner subagent (2026-05-03), persisted by parent agent

---

## §0.5 P0-1 finding (added 2026-05-04): LoadStep amp also nontunable

P0-1 cycle (`quality_reports/plans/2026-05-04_loadstep_bus15_hybrid_dispatch_fix.md`) discovered that the existing v3 Discrete LoadStep mechanism (Three-Phase Breaker + Three-Phase Series RLC Load) is **fundamentally broken under FastRestart**:

- LoadStep_amp_busN writes go to `Three-Phase Series RLC Load.ActivePower` (nontunable in FR; sim log warning explicit)
- Three-Phase Breaker `SwitchTimes` + `InitialState` also compile-frozen
- Net effect: ALL LoadStep dispatches (bus14, bus15, random_bus) produce silent no-op; the values measured in P2 ADR (e.g., 0.108096 Hz) are residual oscillations from preceding dispatches, not actual LoadStep responses
- Even bus14 (with 248 MW pre-engaged IC) was never producing the paper-anchor disturbance — its prior "PASS" was determinism of silent no-op, not real physics

**Implication for Phase 1.5**: Option E CCS substitution (currently `if false` in build script lines ~532-614) is now the **only viable path** to make LoadStep dispatches physically operative. Both LS1 (Bus 14, paper trip 248 MW reduction) and LS2 (Bus 15, paper engage 188 MW addition) require the CCS-Constant pattern; the existing RLC Load + Breaker pattern cannot be salvaged within FastRestart.

**Acceptance gate addition** (proposed): after Phase 1.5 lands, re-run probe Phase 4 with `--workers=1`; LoadStep dispatch dispatches must produce non-trivial Δf (e.g., bus14 ≥ 1 Hz @ 248 MW, bus15 ≥ 0.5 Hz @ 188 MW). If still silent no-op, root cause beyond CCS substitution.

**P0-1 foundation kept**: `bus15 InitialState='closed' + 1W IC` (L1) is preserved as-is; closed-breaker topology matches future CCS endpoint where load is electrically connected at IC. No revert needed before Phase 1.5.

**Reference**: `quality_reports/plans/2026-05-04_loadstep_bus15_hybrid_dispatch_fix.md` §Done Summary "LoadStep silent no-op finding".

---

## §0.6 Phase 1.5 first-attempt finding (added 2026-05-04): Option E pattern is Phasor-only

**Attempt 1 (2026-05-04 EOD)**: An executor agent removed the `if false` wrapper around Option E CCS Trip + CCS Load blocks in `build_kundur_cvs_v3_discrete.m`, deleted the broken Three-Phase Breaker + RLC Load mechanism, and updated workspace_vars / adapter / dispatch_metadata / tests accordingly. 1071/1056+ pytest pass. **But MATLAB compile FAILED**.

**Compile error (via `feval(model, [], [], [], 'compile')` cause inspection):**
```
cause(1): 复信号不匹配. 'kundur_cvs_v3_discrete/powergui/EquivalentModel1/Sources/Mux'
  的'输入端口 26' 应接受 数值类型 complex 的信号. 但它由 数值类型 real 的信号驱动
cause(2): 复信号不匹配. 'kundur_cvs_v3_discrete/powergui/EquivalentModel1/Sources/From26'
  的'输出端口 1' 的信号类型是 数值类型 real. 但它驱动的是 数值类型 complex 类型的信号
```

**Root cause**: The Option E `if false` block at lines ~530-614 uses the pattern:
```matlab
add_block('simulink/Sources/Constant', re_name, 'Value', 'amp/Vbase_const');
add_block('simulink/Sources/Constant', im_name, 'Value', '0');
add_block('simulink/Math Operations/Real-Imag to Complex', ri2c_name);
add_block('powerlib/Electrical Sources/Controlled Current Source', ccs_name);
% wire: re/im → ri2c → ccs (input)
```

This is a **Phasor-mode pattern**: in Phasor solver, all signals are complex (encoding magnitude + phase). The CCS in Phasor mode accepts a complex input. powergui's auto-generated `EquivalentModel1/Sources/Mux` aggregates all sources expecting Phasor's complex signal type.

In **Discrete mode**, signals are real-valued time-domain. The CCS expects a real time-domain current signal (or uses its built-in `Source_Type=AC` with internal `Amplitude/Phase/Frequency` params — but those are not FR-tunable). The RI2C output is complex → mismatches the Discrete Mux's real signal type → compile error.

**F4 micro-test (`test_ccs_dynamic_disc.m`) only proved CCS-block can respond to a real-signal mid-sim** — it did NOT validate that the RI2C-Phasor-pattern works in Discrete. The §0.5 implication "Option E CCS substitution is the only viable path" was over-interpreting F4: Option E is the right MECHANISM (CCS+Constant), but its Phasor WIRING needs Discrete-mode redesign.

**Required redesign** (next cycle, P0-1c):

1. **3-phase wiring**: One CCS per phase (Y-config), like `build_dynamic_source_discrete.m` does for SG/ESS sources. Three CCS blocks per disturbance bus.
2. **Real time-domain signal**: each CCS driven by `Constant(LoadStep_trip_amp_busN/Vbase_const) × Sine(omega*t + phi_phase)` where phi_phase ∈ {0°, -120°, +120°}.
3. **FR-tunable amp**: only `Constant.Value` is FR-tunable (per `slx_episode_warmup_cvs.m:160-164`). The Sine block's amplitude/phase/frequency are nontunable; thus the Sine output is fixed at `1·sin(...)` and the Constant scales it.
4. **Block topology**:
   ```
   Constant(LoadStep_trip_amp_busN/Vbase_const)  ──┐
                                                    ├→ Product → CCS_a → bus phase A
   Sine_a (Amp=1, Freq=fn, Phase=0)              ──┘
   Sine_b (Amp=1, Freq=fn, Phase=-120°)          ──→ Product → CCS_b → bus phase B  
   Sine_c (Amp=1, Freq=fn, Phase=+120°)          ──→ Product → CCS_c → bus phase C
                                                       (same Constant for all 3 phases)
   ```
5. **Per disturbance bus**: 3 CCS + 3 Sine + 1 Constant + 3 Product = 10 new blocks. × 4 buses (LS1+LS2+CCS_Load_bus7+CCS_Load_bus9) = 40 blocks. Reasonable scope.
6. **Possibly reuse** `build_dynamic_source_discrete.m` helper after refactor — currently produces CVS, would need a CCS variant.

**Estimated cost** (post-redesign):
- Design + sin-CCS pattern micro-test: 1-2 hr
- Build script integration (4 buses × 10 blocks): 2-3 hr
- IC settle + E2E re-validation: ~1.5 hr (rebuild + IC + serial 40min + parallel 13min + gate eval)
- Total: 4-6 hr (vs original 5 hr estimate — similar magnitude)

**Acceptance gates G1.5-A..F (Section 1.2) UNCHANGED** — paper-anchor magnitude requirements survive the redesign; only the implementation pattern shifts.

**Attempt 1 outcome (2026-05-04)**: code changes reverted in commit (next), pytest restored to baseline. The plan-doc finding (§0.6) is the deliverable of this cycle. Phase 1.5 redesign is the next cycle.

---

## Section 1 — Goal

### 1.1 What "restored" means

CCS restoration ≡ both injection adapters (`LoadStepCcsInjection` Bus 14/15, `LoadStepCcsLoadCenter` Bus 7/9) drive a **measurable, paper-grade** electrical disturbance on the v3 Discrete model when the schema is invoked with `require_effective=True`. "Measurable" is defined by §1.2 acceptance gate, not `compile_clean` (FACT: `2026-05-03_engineering_philosophy.md` §3 — "Compile success ≠ physics correctness").

### 1.2 Acceptance gates (paper-anchor magnitude)

Pre-registered, immutable per `engineering_philosophy.md` §6 (no goalpost moves):

| Gate ID | Channel | Stimulus | Threshold | Source citation |
|---|---|---|---|---|
| **G1.5-A** | v3 Discrete IC settle (zero-disturbance, CCS enabled, amp=0) | 1 s sim, window [0.5, 1.0]s | 5/7 sources `std_ω < 0.001` (R1 baseline preserved) | `2026-05-03_phase1_progress_and_next_steps.md` §0.4 baseline |
| **G1.5-B** | Trip CCS at Bus 14 (paper LS1 direction = freq UP) | `LOAD_STEP_TRIP_AMP[14] = 248e6 W` at t=2.0s, 5 s sim | `max|Δf|_per_source ≥ 0.3 Hz` on at least 1 of {ES1..ES4} | Paper Fig.3 floor; CLAUDE.md PAPER-ANCHOR HARD RULE |
| **G1.5-C** | Trip CCS at Bus 15 (paper LS2 site, trip direction) | `LOAD_STEP_TRIP_AMP[15] = 188e6 W` at t=2.0s, 5 s sim | `max|Δf|_per_source ≥ 0.3 Hz` on at least 1 of {ES1..ES4} | Paper Fig.3 floor |
| **G1.5-D** | Load-center CCS at Bus 7, freq DOWN (`amp = -248e6`) | 5 s sim | `max|Δf|_per_source ≥ 0.3 Hz` and **sign(Δf) ≤ 0** (frequency drops) | Paper Fig.3 + `disturbance_protocols.py:629-655` sign convention |
| **G1.5-E** | Load-center CCS at Bus 7, freq UP (`amp = +248e6`) | 5 s sim | `max|Δf|_per_source ≥ 0.3 Hz` and **sign(Δf) ≥ 0** (frequency rises) | Same |
| **G1.5-F** | Load-center CCS at Bus 9, both signs (`±248e6`) | 5 s sim each | Symmetric |Δf| within 20% (sign-pair test) | `disturbance_protocols.py` Probe E pattern |

**Failure handling per §6:** Any G1.5-B…F that misses 0.3 Hz triggers root-cause hypothesis listing **before** any change. CCS amp may NOT be inflated to clear the gate (anti-pattern from `OPTION_E_ABORT_VERDICT.md`). If a gate fails after H1-H4 falsification, the gate stands and Phase 1.5 ships partial (e.g. trip-only) with the failed channel left `effective_in_profile=frozenset()`.

### 1.3 Out-of-scope

- Bus-level voltage transients (only frequency Δf gated)
- Pe filter quality (deferred per `phase1_progress §3 — incomplete`)
- Schema promotion of v3 Phasor entries (those stay ABORT'd, see Section 4)
- Full sign-pair smoke at all 4 ESS (only the 1-of-4 weakest constraint per gate)

---

## Section 2 — Pattern translation (v3 Phasor RI2C → v3 Discrete sin)

### 2.1 v3 Phasor pattern (CURRENT, disabled)

FACT: `build_kundur_cvs_v3_discrete.m:510-553` (Trip Bus 14/15) and `:559-602` (Load Bus 7/9). Per CCS instance:

```
Constant LoadStep_trip_amp_<lb> / Vbase_const  ──┐
                                                  ├──► RI2C ──► CCS (1 block, complex input)
Constant 0                                        ┘                ├── LConn1 ─► GND
                                                                    └── RConn1 ─► <bus> (1-phase)
```

This pattern is Phasor-bound (FACT: F1 `test_cvs_disc_input.m` — "complex phasor FAIL" in Discrete; `phase1_progress §1.0 Tests Registry`).

### 2.2 v3 Discrete pattern (TARGET, sin × 3 single-phase CCS in Y-config)

Mirrors the dynamic-source helper sin-driven topology proven by Phase 0 SMIB Oracle (FACT: `build_dynamic_source_discrete.m:182-219` for sin generation; `:236-254` for 3 single-phase CVS in Y-config + common neutral GND).

**CHOICE:** Re-use the local Clock + sin block triplet pattern but for **CCS** (not CVS). F4 microtest (`test_ccs_dynamic_disc.m`) confirmed CCS with `Source_Type='DC', Initialize='off'` accepts a real-valued signal mid-sim (FACT: `phase1_progress §1.0 Tests Registry — F4 PASS`). For 3-phase AC injection use `Source_Type='AC'` with a sin signal driver — equivalent to the CVS chain modulo block type.

Per-CCS-instance topology:

```
                       ┌─► I_pk_amp = amp_W * sqrt(2/3) / Vbase_const  ◄── workspace var
                       │
       Clock_global ─► theta_ref = wn·t + phi_<bus>  ◄── phi_<bus> matches bus voltage angle
                       │
                       ├─► sin(theta_ref + 0)        × I_pk_amp ─► CCS_<lb>_A
                       ├─► sin(theta_ref - 2π/3)     × I_pk_amp ─► CCS_<lb>_B
                       └─► sin(theta_ref + 2π/3)     × I_pk_amp ─► CCS_<lb>_C
                                                         3 powerlib CCS blocks (Source_Type=AC)
                                                         LConn1 ─► common GND_neutral_<lb>
                                                         RConn1 ─► bus phase A/B/C anchors
```

### 2.3 Phase angle reference `phi_<bus>`

FACT: NR was solved with `BUS1_ABS_DEG = 20.0` (`compute_kundur_cvs_v3_powerflow.m:58`). Bus voltage angles at Bus 14/15/7/9 are stored in `kundur_ic_cvs_v3.json` under `bus_voltage_angle_rad`.

**CHOICE registered:** `phi_<bus>` is the **bus voltage angle from NR IC**, in radians, in the same simulation-absolute frame as Bus 1 = +20°. Pure-active injection (in phase with bus voltage).

**Pre-build verification step:** First inspect `kundur_ic_cvs_v3.json` to confirm `bus_voltage_angle_rad` and `bus_ids` field names. If different, adjust the loader.

### 2.4 Y-grounded vs ungrounded

**CHOICE:** CCS triplet uses common neutral `GND_neutral_CCS_<lb>` (one GND block per CCS, all 3 LConn1 tied to it) — Y-grounded pattern, matches surrounding load conventions (FACT: `build_kundur_cvs_v3_discrete.m:377` Three-Phase Series RLC Load Y-grounded).

### 2.5 Magnitude command translation

**CHOICE registered:** `I_pk = amp_W * sqrt(2/3) / Vbase_const` so 3-phase active power = `amp_W` (matches Phasor convention). Documented as a CHOICE in build script header.

---

## Section 3 — Build script changes (`build_kundur_cvs_v3_discrete.m`)

### 3.1 Replace the `if false` guard with `if enable_ccs`

| Action | Line(s) | Notes |
|---|---|---|
| Replace `if false  % CCS_DISABLED` | **~492** | New guard: `if enable_ccs  % Phase 1.5 sin-driven 3-phase CCS pattern` |
| Add `enable_ccs` flag at top | near `bus14_no_breaker` (line ~74-78) | Default `false`; opt-in per probe context |
| Update banner comment | ~486-491 | Cite this plan |

### 3.2 Replace RI2C trip-CCS pattern (Bus 14/15)

| Action | Line range | Replaces | New blocks |
|---|---|---|---|
| Delete RI2C trip block + 1-phase CCS | **510-553** | 5 blocks per bus | ~13 blocks per bus (3 sin + 3 gain + 3 CCS_AC + 2 sum + 1 phi const + 1 GND) |

### 3.3 Replace RI2C load-center CCS pattern (Bus 7/9)

Same structure as 3.2; sign-preserving (no `abs()`) per `disturbance_protocols.py:706` Load-Center adapter.

### 3.4 Re-enable bus_anchor registration for the 3-phase CCS RConn ports

Replace comment block at line ~770-772 with per-phase RConn registration loops for both trip and load-center CCSs. See section 3.4 of the plan body for code.

### 3.5 Add `CCS_phi_bus<n>` defaults to runtime_consts

Read `ic.bus_voltage_angle_rad` for each CCS bus, store in `runtime_consts` for cold-start consistency.

### 3.6 Mirror in `assignin('base', ...)` block (line 283-300 area)

Same `CCS_phi_bus<n>` assignin so build-time workspace also has them.

### 3.7 No changes outside build script

The `Source_Type='AC'` is per-CCS-block parameter inside the build script. No change to `build_dynamic_source_discrete.m`.

---

## Section 4 — Schema updates (`scenarios/kundur/workspace_vars.py`)

### 4.1 LOAD_STEP_TRIP_AMP — extend to v3 Discrete (CONDITIONAL on G1.5-B/C PASS)

- `profiles=PROFILES_CVS_V3` (currently `frozenset({PROFILE_CVS_V3})`)
- `effective_in_profile`:
  - **If G1.5-B AND G1.5-C BOTH PASS** → `frozenset({PROFILE_CVS_V3_DISCRETE})`. v3 Phasor stays inactive.
  - **If either FAILS** → `frozenset()`. Add v3 Discrete inactive_reason citing the failing gate.
- `inactive_reason` for v3 Phasor unchanged.

### 4.2 CCS_LOAD_AMP — extend to v3 Discrete (CONDITIONAL on G1.5-D/E/F PASS)

Same pattern as 4.1, gates D/E/F.

### 4.3 No changes to `disturbance_protocols.py`

Adapters profile-agnostic; `_ws_resolve` automatically gates on schema.

### 4.4 No changes to `bridge.warmup` / `kundur_cvs_ip` struct

Schema scope guard from `workspace_vars.py:21-32` excludes warmup paths.

---

## Section 5 — Acceptance pre-flight micro-test

### 5.1 Probe location

**File:** `probes/kundur/spike/test_ccs_v3_discrete.m`
**Function:** `test_ccs_v3_discrete()`
**Build flag:** `enable_ccs` (boolean, default `false`).

### 5.2 Pre-registered decisions

```
RESULT: G1.5-A enable_ccs=false baseline 5/7 PASS|FAIL
RESULT: G1.5-A enable_ccs=true  baseline 5/7 PASS|FAIL
RESULT: G1.5-B Trip Bus14 max|Δf|=<v> Hz PASS|FAIL  (≥0.3, on 1-of-4 ESS)
RESULT: G1.5-C Trip Bus15 max|Δf|=<v> Hz PASS|FAIL
RESULT: G1.5-D LoadCtr Bus7 amp=-248MW max|Δf|=<v> sign=<+|-> PASS|FAIL  (≥0.3 AND sign≤0)
RESULT: G1.5-E LoadCtr Bus7 amp=+248MW max|Δf|=<v> sign=<+|-> PASS|FAIL  (≥0.3 AND sign≥0)
RESULT: G1.5-F LoadCtr Bus9 ±248MW symmetric within 20% PASS|FAIL
RESULT: VERDICT_PHASE1_5 = N/6 gates passed. Schema promotion = <YES|NO>.
```

### 5.3 Test phases (in execution order)

| Phase | Action | Decision |
|---|---|---|
| 5.3.0 | `enable_ccs=false`, build, 1 s sim | Verify baseline 5/7 still passes (R1 regression) |
| 5.3.1 | `enable_ccs=true`, build, 1 s sim, all CCS amps=0 | G1.5-A baseline preserved |
| 5.3.2 | Trip Bus 14 (also `LoadStep_amp_bus14:=0` first to isolate, see R4) | G1.5-B |
| 5.3.3 | Trip Bus 15 | G1.5-C |
| 5.3.4 | LoadCtr Bus 7 amp=-248e6 | G1.5-D |
| 5.3.5 | LoadCtr Bus 7 amp=+248e6 | G1.5-E |
| 5.3.6 | LoadCtr Bus 9 ±248e6 | G1.5-F |

Total: 7 sims × ~10 s wall + 2 builds × ~30 s = ~2.5 min wall.

### 5.4 Schema promotion rule

Probe `VERDICT_PHASE1_5` line determines §4 schema state:

| Verdict | LOAD_STEP_TRIP_AMP effective | CCS_LOAD_AMP effective |
|---|---|---|
| 6/6 PASS | `{V3_DISCRETE}` | `{V3_DISCRETE}` |
| Trip 2/2 PASS, Load 0-2/3 FAIL | Trip promoted, Load empty | Load gets v3 Discrete inactive_reason |
| Trip 1/2 PASS | empty | empty |
| Trip 0/2 PASS | empty | empty |

---

## Section 6 — Risks and unknowns

### R1 — Compile failure under FixedStepAuto (HIGH × HIGH)

CCS feeding Three-Phase PI Section Line shunt-C may break compile (similar to F11/F12 surprises around "Ideal V parallel C"; `phase1_progress §2 K6`).

**Falsifiable hypothesis:** First build with `enable_ccs=true` will compile-fail with one of: (a) ideal I-source in series with C error, (b) algebraic loop, (c) inconsistent fixed-step propagation through CCS.

**Cheapest mitigation:** add per-phase shunt-R (10 MΩ) between CCS RConn and bus → numerical drain path. Discrete-mode equivalent of F12 surprise (Zvsg per-phase RL).

**Stop trigger:** if no fix in 90 min, escalate.

### R2 — Phase angle reference frame mismatch (MEDIUM × HIGH)

If `bus_voltage_angle_rad` is bus-local instead of system-absolute, CCS injects mostly Q + small P → magnitude attenuation similar to Option E ABORT (~0.008 Hz at 1 GW).

**Falsifiable hypothesis:** if G1.5-B fails by `< 0.05 Hz` (10× attenuation), suspect frame mismatch.

**Mitigation:** print `phi_<bus>` for all 4 buses during build; cross-reference with NR script output. Should match to 1e-6 rad.

### R3 — Schema activation timing (LOW × MEDIUM)

Risk: schema marks v3 Discrete `effective_in_profile` BEFORE acceptance gate fully passes.

**Mitigation:** Implementation order:
1. Run probe with `enable_ccs=true`
2. Capture VERDICT line to disk: `quality_reports/plans/2026-05-03_phase1_5_ccs_restoration_verdict.md`
3. Only then edit `workspace_vars.py`

### R4 — Bus 14/15 trip CCS fights pre-engaged 248 MW LS1 R-load (MEDIUM × MEDIUM)

Bus 14 has IC-pre-engaged 248 MW load. CCS trip injection at Bus 14 with `+248 MW` superimposes on the existing R-load → net ~0 MW → no Δf signal.

**CHOICE registered:** Probe Phase 5.3.2 sets `LoadStep_amp_bus14 := 0` BEFORE injecting CCS, isolating CCS-only effect.

### R5 — Pe instantaneous oscillation contaminates `max|Δf|` calc (LOW × LOW)

Pe oscillates at 100 Hz under instantaneous V·I. May inflate `std_ω` but not `max|Δf|`.

**Mitigation:** compute `max|Δf|` over a 100 ms moving window (averages out 100 Hz ripple), NOT instantaneous. `df_smooth = movmean(df, round(0.1/dt))`.

### R6 — IC field name `bus_voltage_angle_rad` may not exist in `kundur_ic_cvs_v3.json` (MEDIUM × LOW)

**Mitigation:** First implementation step is `cat kundur_ic_cvs_v3.json | jq 'keys'` to verify. If missing, fall back to bus-1-frame `phi_<bus>=0` and accept R2 risk.

---

## Section 7 — Effort breakdown

| Sub-task | Hours | Notes |
|---|---|---|
| 7.1 Read IC JSON, verify field names | 0.25 | Bash + jq |
| 7.2 Edit `build_kundur_cvs_v3_discrete.m` (§3.1-§3.6) | 1.5 | ~80 LOC, structured per existing helper pattern |
| 7.3 Write `probes/kundur/spike/test_ccs_v3_discrete.m` | 1.0 | ~150 LOC |
| 7.4 Run probe (7 sims × ~10 s + 2 builds × 30 s) | 0.25 | ~3 min wall + engine warm-up |
| 7.5 Surprise budget: R1/R2/R6 | 1.5 | One major surprise allowance |
| 7.6 Schema edits (§4) | 0.25 | ~10 LOC, conditional on verdict |
| 7.7 Verdict file write | 0.25 | Captures gate results + decisions |
| **Total** | **5.0 hr** | Inside 4-6 hr range from `phase1_progress §5` |

**Caveats:**
- If R1 (compile) AND R2 (frame) both fire → 8 hr realistic
- If acceptance gates D/E/F fail → Phase 1.5 ships partial (trip-only). 5.5 hr to verdict.
- If `bus_voltage_angle_rad` missing AND need full NR re-derive → +2 hr; total 7 hr

---

## Implementation order

1. Pre-flight: IC field check (R6 → §7.1)
2. Build script edits (§3.1-§3.6) with `enable_ccs` flag, default false (R3 protection)
3. Probe script (§5)
4. Run probe with `enable_ccs=true`
5. Capture verdict file
6. Schema edits (§4) conditional on verdict
7. Update `phase1_progress §5` row 1.5 to ✅ COMPLETED
8. Commit: `feat(phase1.5): CCS restoration on v3 Discrete — N/6 gates pass`

---

## Cross-references (NOT modified by this plan)

- `disturbance_protocols.py` — adapters profile-agnostic, work post-§4
- `env/simulink/kundur_simulink_env.py` — calls adapters via `resolve_disturbance(...)`
- `bridge.warmup` — out of scope per `workspace_vars.py:21-32` schema scope guard

---

*end — Phase 1.5 plan ready for review. Next step: user approval, then proceed per engineering_philosophy.md §6 (no goalpost moves) and §8 (decision-driven tests).*
