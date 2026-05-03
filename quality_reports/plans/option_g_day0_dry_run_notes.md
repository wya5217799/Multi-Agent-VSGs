# Option G — Day 0 Discrete Dry-Run Notes

**Date:** 2026-04-30
**Plan:** `quality_reports/plans/2026-04-30_option_g_switch_rbank_phasor_first_then_discrete.md`
**Day 0 spec:** plan §0.1 – §0.4
**Build copy:** `scenarios/kundur/simulink_models/build_kundur_cvs_v3_discrete_test.m`
   (kept on disk untracked; powergui SimulationMode='Discrete' + SampleTime='50e-6';
   solver kept Variable-step ode23t to discover friction)

---

## 1. Outcome at a glance

| step | result |
|------|--------|
| 0.1 build copy + edits | ✓ done (function rename, mdl rename, powergui Discrete + SampleTime=50e-6) |
| 0.2 build async        | ✓ **0 errors / 0 warnings**, 107 s wall, .slx + runtime.mat saved |
| 0.3a base-workspace seed | ✓ 86 fields seeded from runtime.mat + per-VSG M_i/D_i = 1 |
| 0.3b compile (`update`) | ✗ **FAIL** — 2 cause `Simulink:DataType:*ComplexSignalMismatch` |
| 0.3c sim (`sim()`)      | ✗ **FAIL** — same 2 causes |
| 0.4 cleanup             | ✓ deleted .slx + runtime.mat; kept .m for future B-path use |

**Day 0 GO/NO-GO verdict (vs plan §0.3 acceptance table):** the failure
mode is **NOT** "Discrete-Time Integrator required" (the plan-anticipated
+2 day case) and **NOT** "FastRestart broken" (LOW risk). It is a **CCS
Re/Im → complex chain incompatibility with the Discrete EquivalentModel
auto-generator**, a different friction point that the plan did not
explicitly enumerate. Cost estimate: **+2 day** (closest tier match).

---

## 2. Cause detail

```
cause1: Simulink:DataType:InputPortComplexSignalMismatch
  block: kundur_cvs_v3_disc_test/powergui/EquivalentModel1/Sources/Mux
  port:  Inport 1 expects complex; driven by real signal
cause2: Simulink:DataType:OutputPortComplexSignalMismatch
  block: kundur_cvs_v3_disc_test/powergui/EquivalentModel1/Sources/From1
  port:  Outport 1 is real; drives complex consumer
```

### Why this happens

The Discrete-mode `powergui` block auto-generates an internal
`EquivalentModel1` that treats every electrical source as a 3-phase real
signal pipeline (sin/cos balanced 3-phase voltage, fed into `Sources/Mux`).
The current build (`build_kundur_cvs_v3.m`) feeds CCS sources via a
**Real–Imag → Complex** chain (`*Re_busN`, `*Im_busN`, `Real-Imag to
Complex` block) — this chain produces a single complex scalar, the
representation `powergui Phasor` mode expects but `powergui Discrete`
mode does not.

The `From1` mismatch is the symmetric output side: a Discrete
EquivalentModel `From` block exposes a real-typed scalar at its Outport,
but downstream consumers still expect the Phasor-style complex scalar.

This is a pervasive structural mismatch — every CCS injector
(`CCSLoadIRe_busN` / `CCSLoadIIm_busN` / `CCSLoad_RI2C_busN`) and every
trip-CCS injector (`ITripRe_busN` / `ITripIm_busN` / `ITripRI2C_busN`)
participates in this pattern. Counted from the build script:
- 2 × Bus 7/9 CCS Load (Option E dormant; ABORT'd)
- 2 × Bus 14/15 LoadStep Trip CCS (Phase A++ dormant)

Total **4 CCS chains** to rewrite for Discrete compatibility, plus a
re-validate pass on the ESS / SG voltage-source side because they may
also use complex internal scaffolding. (Worth noting: the build's
`add_block` calls finished cleanly — the friction is purely inside the
auto-generated `EquivalentModel1`, which means the base topology
defined by the build script is structurally sound; the issue is at the
solver-driver wiring layer.)

### Why "Discrete-Time Integrator" did NOT come up

The 9 dynamic-source swing-equation integrators are inside ESS / SG
masked subsystems that the build script imports as full subsystem libs
(not raw Continuous Integrator blocks). MATLAB R2025b (or whatever the
session is using) appears to handle the Continuous integrators
gracefully under `'SolverType', 'Variable-step', 'Solver', 'ode23t'` —
they aren't blocking compile. So the plan §0.3 "compile errors re
Discrete-Time Integrator" prediction does not apply here; the swing-eq
side is Discrete-clean (or at least Discrete-tolerant).

This is **good news** for the eventual B path: the swing-eq core is
not the bottleneck; only the source-injection chain needs rework.

---

## 3. A→B upgrade cost estimate

**Most likely tier match: +2 day** (was "rewrite 9 source swing-eq
integrator blocks" in the plan; for our actual failure, swap to "rewrite
4 CCS injection chains to Discrete-compatible form: real-imag → 3-phase
sin/cos balanced source").

Concrete work for the B path:
- 4 × CCS injector blocks: replace `Real-Imag to Complex` + complex CCS
  source with a Discrete-compatible Three-Phase Programmable Voltage /
  Current source (or use `powerlib/Electrical Sources/Three-Phase Source`)
  driven by 3-phase real signals computed from amplitude + phase.
- ~½ day per chain × 4 chains ≈ 2 days, conservative.
- Re-validate IC equivalence after solver swap (Pm0 within 1e-5 instead
  of 1e-12 because Discrete is numerical-time-stepped).

**Optimistic A→B path** (if Bus 7/9 CCS chains can be deleted entirely
because Option E was ABORT'd and the chains are dead anyway): only the
2 × Bus 14/15 Trip CCS chains need rework. That cuts ~half the work to
**~+1 day**. This is worth pursuing because deleting electrically-dormant
CCS blocks is cheap and reduces the surface area of the B-path edit.

---

## 4. Decision (per plan §0.3 final paragraph)

> "If Discrete dry-run signals > +2 day upgrade cost, discuss with
> operator before proceeding to Day 1. A becomes 'single-shot — if it
> fails we accept F4 v3 +18 % ceiling and write up.'"

Our finding maps to the **+2 day boundary** (slightly below if dead
Bus 7/9 CCS chains are pruned first). This sits at the *threshold* of
the operator-discussion trigger but does not exceed it. Recommendation:

- **Default**: **proceed to Day 1 (build A — Phasor primary)**, treating
  the B fallback as a known +1–2 day cost if A's signal is insufficient.
- **Side-task** to do during Day 1 async windows: prune the dormant
  Option E Bus 7/9 CCS chain from the build script. That alone trims
  the future B-path cost ~50 %. Low risk because Option E was ABORT'd
  with formal verdict (`OPTION_E_ABORT_VERDICT.md`).
- **Operator escalation trigger**: if Day 1 build edits surface
  unexpected friction and the running cost estimate climbs > +3 day,
  pause and re-decide.

## 5. Artifacts

- `scenarios/kundur/simulink_models/build_kundur_cvs_v3_discrete_test.m`
  — kept on disk untracked. Used as the seed for B-path build edits;
  do **NOT** delete.
- `kundur_cvs_v3_disc_test.slx` — deleted (would re-confuse intent).
- `kundur_cvs_v3_disc_test_runtime.mat` — deleted.
- This notes file — committed alongside Option G plan, no source code
  change attached.
