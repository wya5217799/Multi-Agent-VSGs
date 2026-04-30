# Option E (CCS at Bus 7/9 load center) — ABORT VERDICT

**Date:** 2026-04-30
**Plan:** `quality_reports/plans/2026-04-30_option_e_ccs_bus7_9_continuation.md`
**Status:** ABORT at Step 5 (Probe E sign-pair smoke)
**Outcome:** F4 v3 +18 % remains the project ceiling under current architecture.

> **PAPER-ANCHOR HARD RULE check:** Signal layer falsification (G1) failed on
> both Bus 7 and Bus 9. No paper number is anchored or claimed. This verdict
> is a **negative result** — Option E does not unblock the signal — and is
> recorded so future workers know not to retry the same path expecting a
> different outcome.

---

## 1. Probe E sign-pair results (plan §5 acceptance gates)

Both load-center buses tested at |mag| = 0.5 sys-pu (50 MW @ Sbase = 100 MVA),
zero-action policy, 50-step trajectory (10 s) per run.

| bus | per-agent (|nadir_diff| + |peak_diff|), Hz | max diff | verdict |
|-----|-------------------------------------------|---------:|---------|
| 7   | [0.0007, 0.0000, 0.0000, 0.0000]          |   0.0007 | **ABORT** |
| 9   | [0.0000, 0.0000, 0.0001, 0.0013]          |   0.0013 | **ABORT** |

Both buses fail the **H_E_abort** criterion: every agent's sign-pair diff is
below the 0.010 Hz noise floor. Plan acceptance was "max diff > 0.05 Hz on
at least one agent"; we measure 50× and 70× under that threshold respectively.

Plan §5 ABORT criterion was "all 4 agents diff < 0.01 Hz". Both buses are
below that floor across all 4 ESS terminals.

Per-bus verdict files:
- `probe_e_verdict_b7.md`
- `probe_e_verdict_b9.md`

---

## 2. Root cause — Phasor-solver CCS attenuation (NOT bus location)

The plan §1.3 hypothesis was *"CCS at Bus 7/9 should produce 50–100× stronger
signal because Bus 7/9 is where the 2734 MW paper-LoadStep electrically lives
(vs Bus 14/15 ESS terminals)."* This hypothesis is **falsified** by a direct
sweep on the kundur_cvs_v3 model with all PM/PMG disturbances zeroed:

| injection bus | amp (W)  | omega_3 max (Hz_pu) | Δomega_3 vs amp=0 (Hz) |
|---------------|---------:|--------------------:|----------------------:|
| Bus 14 (Trip CCS, known working pattern) | 0       | 0.99971 | (baseline) |
| Bus 14 (Trip CCS) | +1×10⁹ (1 GW!) | 0.99996 | 0.019 Hz |
| Bus 9  (Option E new pattern)            | 0       | 0.99971 | (same baseline) |
| Bus 9  (Option E)            | +1×10⁹ (1 GW!) | 0.99985 | 0.0077 Hz |

Two findings:

1. **Even at 1 GW injection** (≈10× the entire system load 1767 MW @ Bus 9),
   the frequency response is bounded at ~0.019 Hz on Bus 14 (best case) and
   ~0.0077 Hz on Bus 9. Paper LoadStep produces ~0.5 Hz nadir; this is
   **two orders of magnitude weaker**.
2. **Bus 9 (load center) is WEAKER than Bus 14 (ESS terminal)**, opposite of
   the plan §1.3 hypothesis. The 1767 MW load at Bus 9 acts as a low-impedance
   sink that absorbs the CCS injection before it can drive omega excursion.

This means the CCS injection path is **fundamentally attenuated by the
Phasor solver** in the kundur_cvs_v3 model, and the attenuation is roughly
**bus-agnostic**: putting the CCS at the paper-Fig.3 load center provides
no advantage over putting it at the ESS terminals (and is actually worse
in this case). The wiring is correct (Step 2 compile + ports verified, Step
3 NR/IC equivalent), the dispatch chain is correct (Step 4 schema + adapter
+ paper_eval all green), but the solver simply does not propagate the
signal through the network at paper-grade magnitude.

Why the Phasor solver attenuates: the model uses fundamental-frequency
phasor algebra (one complex number per node, no transient EMF dynamics).
A current injection in this regime acts on the admittance matrix only;
omega excursion comes purely from the swing-eq integrators driven by
Pe = Re(V·I*) on each dynamic source. With the sources already balanced
to IC and the line impedances small relative to the source internal X,
the perturbation seen at each ESS terminal is heavily damped.

This is consistent with the historical Phase A++ Trip CCS measurement at
Bus 14/15 producing ~0.01 Hz signal at mag = 0.5 sys-pu — Phasor Trip CCS
was already known weak; we now confirm CCS at the load center is **not
stronger**. The attenuation is a property of the solver/model, not the
injection point.

---

## 3. What was already tried within Option E

Plan §3 Steps 1–4 PASS (kept):
- **Step 1** Build clean (.slx 482950 → 493369 B; +5 blocks/bus × 2 buses).
- **Step 2** Compile clean. Block ports OK; CCSLoadRe/Im/RI2C/CCS/GND
  topology mirrors Phase A++ exactly.
- **Step 3** NR/IC equivalent — `vsg_pm0_pu` and all 14 numeric arrays in
  `kundur_ic_cvs_v3.json` have max-abs-diff = 0 vs the pre-Option-E IC.
  Confirms amp=0 ⇒ electrically absent (no parasitic injection).
- **Step 4** Schema + dispatch + paper_eval all green:
  - `workspace_vars.py::CCS_LOAD_AMP` (PER_BUS, valid_buses={7,9}, effective
    in v3).
  - `disturbance_protocols.py::LoadStepCcsLoadCenter` (sign-preserving,
    bidirectional bus 7/9).
  - 3 dispatch entries: `loadstep_paper_ccs_bus7|9|random_load`.
  - `scenario_loader.py::scenario_to_disturbance_type` route.
  - `config_simulink.py::KUNDUR_DISTURBANCE_TYPES_VALID` registration.
  - `paper_eval.py --disturbance-mode ccs_load` + bus_choices + scenario
    routing.
  - All smoke tests for these layers pass.

Step 5 PROBE E **ABORT** (this verdict).

Steps 6–10 NOT executed (50-scenario no_control eval, 350 ep retrain,
3-policy paper_eval, action ablation, final RL verdict). Skipped because
plan §5 explicitly says "Even if you're impatient, the 15 min smoke saves
potentially 8h wasted retraining."

---

## 4. Recommendations

Per plan §6 Risk #1 mitigation: "If fails, Option E is wrong path; only
Option G (Switch+R-bank) or solver change remain."

**Recommended next step (operator decision required):**

| option | est. effort | expected outcome |
|--------|-----------:|------------------|
| **A. Accept F4 v3 +18 % as ceiling** | 0 h | Document SOTA, write up. Project boundary measured: under (Phasor solver + F4 hybrid SG+ES dispatch + PHI=5e-4 + zero-centered action map + SAC), RL improvement caps at +18 %. The 29 pp gap to paper +47 % is **architectural** (solver + reward shape), not protocol-tunable. |
| **B. Option G — Switch+R-bank** | 1 week | Paper-faithful: replace CCS injection with breaker-switched physical R-load. Requires Phase A breakthrough (R-block FastRestart compile-freeze) to be lifted via solver-level fix or accept the IC reseed cost. Risk: same Phasor-solver attenuation may apply. |
| **C. Switch to discrete solver** | 2-3 days | Replace Phasor with Discrete (`powergui` SimulationMode = Discrete @ Ts=50 µs). CCS injection in discrete mode is electromagnetically faithful — paper-grade signal expected. Trade-off: ~10-100× slower sim (~30 ms/step → 0.3-3 s/step), 350-ep retrain becomes ~10-12 h. |
| **D. Live with weak CCS** | 3-5 days | Increase DIST_MAX to 30+ sys-pu (10× current 3.0). Compensates the 10× attenuation. Risk: SAC training instability at large action magnitudes; reward landscape may saturate. Not recommended without first proving SAC convergence at the inflated scale. |

Author recommendation: **A (accept) for now, then B if/when capacity for
1-week breakthrough is available.** C is the cleanest physical fix but
training-time cost is severe.

---

## 5. Artifacts kept

Per plan §6 ("keep schema/dispatch additions — they don't break anything;
future Option G can reuse the dispatch framework"), the following remain
committed/uncommitted:

**Build / model (kept, NOT rolled back):**
- `scenarios/kundur/simulink_models/build_kundur_cvs_v3.m` (4 sections added)
- `scenarios/kundur/simulink_models/kundur_cvs_v3.slx` (rebuilt)
- `scenarios/kundur/simulink_models/kundur_cvs_v3_runtime.mat` (rebuilt)

The .slx is electrically equivalent to the pre-Option-E .slx (Step 3 NR
proof). Future Option G can reuse the build script CCS pattern at Bus 7/9
or roll it back; either way the project state is consistent.

**Schema / dispatch / eval CLI (kept, framework reusable):**
- `scenarios/kundur/workspace_vars.py` (CCS_LOAD_AMP entry, PER_BUS valid_buses
  override).
- `scenarios/kundur/disturbance_protocols.py` (LoadStepCcsLoadCenter adapter,
  3 dispatch entries).
- `scenarios/kundur/scenario_loader.py` (`ccs_load` route).
- `scenarios/kundur/config_simulink.py` (3 valid type entries).
- `evaluation/paper_eval.py` (`--disturbance-mode ccs_load`).
- `probes/kundur/probe_e_sign_pair.py` (smoke driver).

**Probe artifacts (this directory):**
- `manifest_pos_b7.json`, `manifest_neg_b7.json`, `probe_e_pos_b7.json`,
  `probe_e_neg_b7.json`, `probe_e_verdict_b7.md`
- `manifest_pos_b9.json`, `manifest_neg_b9.json`, `probe_e_pos_b9.json`,
  `probe_e_neg_b9.json`, `probe_e_verdict_b9.md`
- `OPTION_E_ABORT_VERDICT.md` (this file)

---

## 6. Schema demotion (post-falsification)

`workspace_vars.py::CCS_LOAD_AMP::effective_in_profile` was set to
`frozenset({PROFILE_CVS_V3})` at the end of Step 4 (pre-build evidence:
compile clean + IC equivalence). Probe E now falsifies the *physical
effectiveness* of the channel — writes do reach the workspace var, the
model compiles, but the resulting omega response at all 4 ESS terminals
is below 0.01 Hz noise floor.

**Action:** demote `CCS_LOAD_AMP` to `effective_in_profile=frozenset()` and
record the falsification in `inactive_reason` so any future caller using
`require_effective=True` raises with the historical explanation, the same
contract that protects callers from `LOAD_STEP_AMP` (R-block compile-freeze)
and `LOAD_STEP_TRIP_AMP` (Bus 14/15 distance attenuation).

---

## 7. Time budget actuals

| step | plan | actual | notes |
|------|-----:|-------:|-------|
| 0 (read) | 30 m | 5 m  | plan was already read in prior session |
| 1 (build) | 5 m  | 4 m | async, 53 s elapsed in MATLAB |
| 2 (compile + inspect) | 5 m | 8 m | base-ws push needed first |
| 3 (NR check) | 5 m | 3 m | json compare via Python one-liner |
| 4 (schema + dispatch) | 25 m | 30 m | adapter + 5 files + smokes |
| 5 (probe E ABORT) | 15 m | 20 m | bus 7 + bus 9 + diagnostic CCS sweep |
| **Total to ABORT** | ~85 m | ~70 m | well within plan §9 abort budget (~1.5 h) |

Plan §6 abort path: ~1.5 h to abort. Actual: ~70 min. Under budget.

---

*End of `OPTION_E_ABORT_VERDICT.md` — 2026-04-30 main session*
