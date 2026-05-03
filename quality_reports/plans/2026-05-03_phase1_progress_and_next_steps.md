# Phase 1 Progress + Next Steps — Single Source of Truth

**Status:** AUTHORITATIVE as of 2026-05-03 EOD session
**Branch:** `discrete-rebuild`
**Worktree:** `C:\Users\27443\Desktop\Multi-Agent-VSGs-discrete`
**Supersedes:** `2026-05-03_phase1_next_steps.md` (early/stale, kept for history)

---

## §0 Quickstart for Fresh Session

> If you're a new AI agent picking up this work, read this section FIRST — it
> gives you the minimum context to verify state and choose next action.

### §0.1 Project background (1 paragraph)

Reproducing **Yang et al. TPWRS 2023** — multi-agent SAC reinforcement learning
controls 4 energy storage system (ESS) units' virtual inertia H and damping D
in a **Kundur 2-area power system**. The original Phasor-mode v3 model hit a
fundamental wall: **electrical disturbances (LoadStep, CCS injection) don't
propagate** in Phasor's static Y-matrix solver. The 2026-05-01 verdict
initially REJECTED Discrete migration on cost grounds, but on 2026-05-03 user
authorized override + Phase 0 SMIB Oracle (4.9 Hz @ 248 MW) falsified the
REJECT. The `discrete-rebuild` branch is the migration to Discrete EMT mode
with all module choices re-verified by pre-flights F11/F12/F13.

### §0.2 Worktree + branch (CRITICAL)

```
Path:  C:\Users\27443\Desktop\Multi-Agent-VSGs-discrete
Branch: discrete-rebuild
```

⚠️  **NOT the same as the main worktree** — main is at
`C:\Users\27443\Desktop\Multi-Agent  VSGs` (double-space in path!) on `main`
branch. The main worktree's `kundur_cvs_v3.slx` and helpers may **shadow**
this branch's files in MATLAB path. If you see "shadowing" warnings, ensure
this worktree's `scenarios/kundur/simulink_models/` is FIRST in `addpath`.

### §0.3 Key new files (created on this branch, not in main)

| File | Purpose |
|---|---|
| `scenarios/kundur/simulink_models/build_dynamic_source_discrete.m` | Per-source helper (sin → 3 single-phase CVS in Y-config + Pe via V·I) |
| `scenarios/kundur/simulink_models/build_kundur_cvs_v3_discrete.m` | v3 Discrete build script (uses helper × 7) |
| `probes/kundur/spike/build_minimal_smib_discrete.m` | Phase 0 SMIB Oracle (validated 4.9 Hz) |
| `probes/kundur/spike/test_v3_discrete_ic_settle.m` | **Layer 2 TDD test — RUN THIS to verify state** |
| `probes/kundur/spike/test_{3phase_network,multisrc_coupling,ic_delta_mapping}_disc.m` | F11/F12/F13 pre-flight tests |
| `probes/kundur/spike/test_{cvs_disc_input,r_fastrestart_disc,var_resistor_disc,ccs_dynamic_disc,...}.m` | F1-F10 micro-experiments (parallel agent) |

### §0.4 Verify current state (1 command)

Via simulink-tools MCP (recommended):
```matlab
addpath('C:/Users/27443/Desktop/Multi-Agent-VSGs-discrete/probes/kundur/spike');
addpath('C:/Users/27443/Desktop/Multi-Agent-VSGs-discrete/scenarios/kundur/simulink_models');
test_v3_discrete_ic_settle();
```

**Expected output (2026-05-03 EOD baseline, 1s sim, window [0.5,1]s):**
```
RESULT: G1: PASS  ω=0.99534 ± 0.00029
RESULT: G2: PASS  ω=0.99545 ± 0.00026
RESULT: G3: PASS  ω=0.99642 ± 0.00041
RESULT: ES1: PASS ω=0.99546 ± 0.00042
RESULT: ES2: PASS ω=0.99649 ± 0.00093
RESULT: ES3: FAIL ω=0.99663 ± 0.00177  (oscillate)
RESULT: ES4: FAIL ω=0.99669 ± 0.00102  (oscillate)
RESULT: 5/7 sources settled
```

**Branching logic:**
- 5/7 PASS as above → state matches doc; proceed with Phase 1.3a (ES3/ES4 oscillation diagnosis, see §4)
- **7/7 PASS** → someone solved 1.3a between sessions; update §3 + §4, move to Phase 1.4
- **< 5/7 PASS** → regression; `git log --oneline -10` to see what changed; diagnose before touching code
- **Build fails** → MATLAB engine state issue; `restart_engine` or `simulink_runtime_reset`

### §0.5 Read order (15 min total)

1. **This doc §1-§5** — completed work + key findings + current state + next actions (5 min)
2. **`2026-05-03_phase0_smib_discrete_verdict.md`** — Phase 0 4.9 Hz oracle PASS evidence (3 min)
3. **`2026-05-03_phase_b_extended_module_selection.md`** — F1-F9 micro-experiments + module decisions (5 min)
4. **Main worktree `CLAUDE.md`** — project-wide coding conventions (skim, 2 min). Note: branch-specific paths are in §0.3 above, not in CLAUDE.md.

After this 15-min read-up, you have full context to either:
- Continue Phase 1.3a (ES3/ES4 oscillation diagnosis) — top of forward path
- OR pick a different sub-task from §5

### §0.6 Common pitfalls

1. **Wrong worktree** — running `git status` in `Multi-Agent  VSGs` (main) instead of `Multi-Agent-VSGs-discrete` will mislead you. Always verify `git rev-parse --abbrev-ref HEAD` returns `discrete-rebuild`.
2. **Shadow warnings** — MATLAB picks the wrong v3 build if main worktree is on path before this branch. Use absolute paths in `addpath` calls.
3. **`MaxDataPoints=2`** on To Workspace blocks — helper sets this for live RL training; in tests set to `'inf'` BEFORE `sim()` to capture full trace.
4. **CCS blocks disabled** — wrapped in `if false` in build script. Phase 1.5 sub-task. Don't enable yet.
5. **Continuous Integrator + FixedStepDiscrete = compile FAIL** (F9). Helper currently uses Continuous Integrator + FixedStepAuto (works). Don't change solver to FixedStepDiscrete without first migrating helper to Discrete-Time Integrator.
6. **DON'T MOVE THE GOALPOSTS** — if a test FAILS, do NOT relax acceptance criteria to make it pass. This is the #1 hallucination-disguised-as-progress trap.
   - Diagnose with the §4 hypothesis list (cheapest-first, falsifiable). Test each hypothesis with a concrete change (e.g. toggle a flag, modify one param) and observe whether the failure mode disappears.
   - Only AFTER root cause is confirmed by evidence, propose a fix. The fix may include relaxing acceptance criteria — but justified by physics (e.g. "swing mode damping time constant = 2s, so [4,5]s window is the correct physical acceptance"), not by "this makes the test pass".
   - Verdict claims like "Phase 1.X closed" REQUIRE evidence: actual sim output captured, FFT plot if frequency claimed, damping calc if mode-based, NR re-derive if IC-related. Anything stated in `RESULT:` lines that's not in the actual sim output IS HALLUCINATION.
   - If you find yourself thinking "the obvious answer is X, let me just write the verdict" — STOP. Run the falsification test for X first. If X is the right answer, the test confirms it cheaply. If X is wrong, you've avoided enshrining hallucination as truth.

   **Real example (2026-05-03 cross-session review)**: an agent extended the IC settle test window from 1s → [4,5]s, claimed "ES3/ES4 oscillation is 2 Hz electromechanical swing mode (ES3 amp 28× G1)", and marked Phase 1.3a closed. NONE of these had evidence: no FFT was run, no §4 hypothesis was tested, no LoadStep `InitialState` toggle. The window extension may be correct (if H1 is the cause, swing damps in 4-5s), but it must be VALIDATED by hypothesis testing, not assumed.

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
- Sim wall (1s): 1.74s
- Sim wall (5s, measured 2026-05-03): 4.99s (1.0× real-time, init overhead amortized)
- Sim wall (10s, measured 2026-05-03): 8.95s (1.1× real-time)

**What works structurally**:
- Source chain (helper-based) ✓
- 3-phase network (lines + loads + shunts + wind) ✓
- LoadStep mechanism (Breaker+Load) ✓
- Bus net wiring (per-phase anchor maps) ✓
- IC numerics (V_emf_pu × sin pattern) ✓ (mostly)

**What's incomplete**:
- ES3/ES4 oscillation root cause (Phase 1.3a — diagnosis pending, see §4)
- CCS injection (disabled, Phase 1.5)
- Continuous Integrator → Discrete-Time Integrator (FixedStepAuto bypass; Phase 1.5+ optimization)
- Pe FIR filter (currently instantaneous V·I, oscillates at 100 Hz; Phase 1.5+ optimization)

---

## §4 Known Issues — Phase 1.3 To Diagnose

### Issue 1.3a — ES3/ES4 oscillation (UNRESOLVED, root cause not proven)

**Symptoms** (1s sim, window [0.5,1]):
- ES3 (Bus 14) std=0.00177, ES4 (Bus 15) std=0.00102 — failed std<0.001 threshold
- ES1 (Bus 12) and ES2 (Bus 16) settle fine — same ESS topology, different bus
- Bus 14/15 differ from Bus 12/16 in having a Three-Phase Breaker + Three-Phase Series RLC Load
  attached. Bus 14 LS1 InitialState='closed' (paper Task 2 pre-engaged 248 MW); Bus 15 LS2 InitialState='open'.

**Spectrum diagnostic finding** (1s sim, raw FFT @ window [0.5,1], data in `phase1_3a_spectrum_diag.mat`):
- All 7 sources show same dominant 2 Hz / 4 Hz / 6 Hz harmonic structure
- BUT: shared frequency does NOT prove same root cause — Bus 14/15 attachments could excite the
  same natural mode preferentially. Magnitude ordering is not yet code-verified beyond raw FFT power.

**Hypotheses to test** (cheapest first, in original §4 order):
1. **H1**: LS1 closed-state × Π-line shunt-C transient. **Test**: rebuild + override
   `LoadStepBreaker_bus14` `InitialState` to `'open'`, re-run **1s** test, check ES3/ES4 settle at
   original gate.
2. **H2**: Bus 14/15 power-flow imbalance from LS1 pre-engaged → re-derive NR with LS1 active and use updated Pm.
3. **H3**: Solver step too coarse for Breaker-Load-Π interaction → try 25 μs step.
4. **H4**: Three-Phase PI Section Line zero-seq params wrong → try [Lk, 1.5×Lk] instead of [Lk, 3×Lk].

**Status**: H1 falsification test pending (per §0.6 pitfall #6 — DO NOT widen acceptance to bypass diagnosis).

### Issue 1.3b — Steady-state ω = 0.995 (UNRESOLVED, root cause not proven)

**Symptoms**: All 7 sources sit at 0.995-0.997 instead of exactly 1.0 (after 1s).

10s observation (read-only data in `phase1_3a_10s_settle.mat`, not a fix): mean ω trajectory
0.995 (@1s) → 0.9998 (@5s) → 1.0000 (@10s). Could be either (a) physical damping of 2 Hz swing mode,
or (b) latent NR/EMT phasor mismatch slowly draining via shunt losses. Diagnosis pending H1 outcome
— if H1 PASSES (open breaker → ES3/ES4 settle in 1s), then 1.3b is also a breaker-driven transient
artifact. If H1 fails, 1.3a/1.3b need separate root-causing.

---

## §5 Forward Path

| Phase | Goal | Estimated effort |
|---|---|---|
| **1.3a** | Diagnose + fix ES3/ES4 oscillation → 7/7 settle | 1-2 hours |
| **1.3b** | Diagnose ω = 0.995 vs 1.0 (or accept as tolerance) | 1-3 hours |
| **1.4** | 248 MW LoadStep oracle on full v3 Discrete (paper anchor) | 2-4 hours |
| **1.5** | Restore CCS injection (sin-driven 3-phase pattern) | 4-6 hours |
| **1.5+** | Speed optimization (TRIGGERED ONLY — see §6) | 0 hours default; 30 min if triggered |
| **1.6** | Update env config + paper_eval to use v3 Discrete | 2-4 hours |
| **1.7** | First trained policy run on v3 Discrete | 1-2 days |

**Optimistic remaining**: 4-6 days (vs original 8-12 day Phase 1 estimate)
**Realistic remaining**: 1-2 weeks (with surprise budget)

---

## §6 Training Time Risk Mitigation — Lean / Trigger-on-Demand

**Methodology shift (2026-05-03 EOD review)**: Original F14-F17 list was "test for testing's sake" — pre-optimization with no decision context. Replaced with measure-first / optimize-only-if-needed.

### §6.1 Baseline projection from existing data

From Phase 1.1+ IC test (1s sim → 1.74s wall, 1.7× real-time at v3 scale):

```
Single 5s episode sim   ≈ 1.7 × 5s = 8.5s wall
Single episode reset    ≈ 1s wall (FastRestart, assumed)
Per-episode total       ≈ 9.5s wall
200 episodes pure sim   ≈ 32 min wall
+ RL overhead (SAC, replay buffer, etc.) ≈ +30-50%
TOTAL TRAINING WALL     ≈ 40-60 min  (acceptable)
```

This projection comes from data we already have (v3 IC test). **No additional speed tests needed if projection holds.**

Read-only longer-sim measurements (2026-05-03, NOT yet a verified baseline — depends on Phase 1.3a outcome):
- 5s sim wall = 4.99s (1.0× real-time)
- 10s sim wall = 8.95s (1.1× real-time)

These look better than the 1.7× projection (init overhead amortizes), but only become the planning
baseline once Phase 1.3a closes with a proven root cause.

### §6.2 Trigger condition for speed tests

Defer all speed optimization to AFTER trial training:

```
Phase 1.6 接 paper_eval / probe_state
   ↓
Run TRIAL training: 10-20 episodes on v3 Discrete
   ↓
Measure actual wall-clock per episode + reset
   ↓
Extrapolate to 200 episodes
   ├─ < 2 hr  → ship as-is, no speed tests needed
   ├─ 2-4 hr  → run minimal speed test (D5 only, ~10 min) — FastRestart toggle
   └─ > 4 hr  → run full triggered speed test bundle (~30 min)
```

### §6.3 Triggered Speed Test Bundle (run only if 200-episode projection > 2 hr)

If the trigger fires, run a SINGLE combined test that resolves the 3 highest-ROI module decisions in ~30 min:

| Decision | Variables | Acceptance |
|---|---|---|
| **D2** Sample time | dt ∈ {50, 100, 200} μs | largest dt with Pe error < 1% and IC settle stable |
| **D3** Integrator+Solver pair | (Continuous + FixedStepAuto) vs (Discrete-Time + FixedStepDiscrete) | faster pair if speedup ≥ 1.5× |
| **D5** FastRestart | on vs off (only matters at v3-scale; trivial result expected to be similar to F3/F4) | adopt if reset speedup ≥ 3× |

Combined sweep: 3 dt × 2 integrator-solver × 2 FastRestart = 12 configs × ~5s wall each = 60s + setup. Total wall < 30 min including writing the test.

**Skipped from earlier roadmap** (low ROI relative to cost):
- D1 Solver type sweep — F8 trivial result said all similar; v3 retest probably wastes time
- D4 Pe filter — quality issue not speed (deferred to RL signal-quality review, not speed)
- D6 3-phase line variant — invasive change for unclear gain
- D7 Source NonIdeal SCL — minor effect
- D8 Training parallelism (multi-env) — infrastructure decision, separate scope

### §6.4 Why this is the right framing

YAGNI: don't optimize what's not measured to be slow. Existing data already projects 40-60 min training, comfortably under any reasonable threshold. If projection holds → 0 wasted hours. If it fails → 30 min of targeted tests (not 4-8 hr).

Pre-optimization risk mitigation is not free — it costs hours of design + execution that could go to actual training, RL agent tuning, or paper-anchor validation. By deferring optimization to "triggered on miss", we preserve that budget for higher-leverage work.

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

## §9 Phase 1.3a Diagnostic Artifacts (read-only data, 2026-05-03)

These are MEASUREMENTS, not verdicts. Used as inputs to the §4 H1-H4 hypothesis tests, which are
still pending (see §0.6 pitfall #6 — measurements ≠ root cause).

Saved to `scenarios/kundur/simulink_models/`:
- `phase1_3a_spectrum_diag.mat` — 1s sim ω time series for all 7 sources
- `phase1_3a_10s_settle.mat` — 10s sim ω time series

Per-window mean / max-std observations (10s sim, 7 sources):

| Window | mean ω | max std (which src) |
|---|---|---|
| 0.5–1s | 0.995–0.997 | 0.00177 (ES3) |
| 1–2s | 0.999 | 0.00165 (ES1) |
| 4–5s | 0.9997–0.9999 | 0.00053 (ES3) |
| 5–9s | 1.0000 | 0.00017 (ES4) |
| 9–10s | 1.0000 | 0.00013 (ES3) |

FFT peak power per source @ window [0.5, 1] s, dominant freq = 2 Hz across all 7 sources:

| Source | P @ 2 Hz |
|---|---|
| G1 | 0.000375 |
| G2 | 0.000309 |
| G3 | 0.000511 |
| ES1 | 0.000607 |
| ES2 | 0.00293 |
| ES4 | 0.00357 |
| ES3 | 0.0107 |

The shared 2 Hz frequency is consistent with an electromechanical swing mode, but does NOT prove
H1-H4 are falsified — Bus 14/15 attachments could excite the same natural mode preferentially.
Hypothesis tests are needed before any verdict.

---

*end — Phase 1 progress + next steps as of 2026-05-03 EOD.*
