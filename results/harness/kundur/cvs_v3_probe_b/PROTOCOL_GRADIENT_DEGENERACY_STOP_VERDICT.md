# STOP Verdict: Protocol Gradient Degeneracy is the Binding Constraint

**Date:** 2026-04-30
**Author:** main session (post-Probe B G1+G2+G3)
**Status:** LOCKED — supersedes any prior interpretation of `+10-12% RL improvement` as paper-comparable

---

## Statement

Under both currently-implemented Pm-step disturbance protocols
(`pm_step_proxy_random_bus` ESS-side and `pm_step_proxy_random_gen`
SG-side), the per-scenario RL learning signal reaches **on average
~1.33 of 4 agents**. **ES2 (Bus 16) receives zero signal in all
scenarios under SG-side**, and ES2 was never tested under ESS-side
single-VSG injection prior to today (see Probe B-ESS, in flight).

This is a **structural constraint of the disturbance protocol**, not
a bug in measurement or reward computation. It cannot be lifted by
hyperparameter tuning, longer training, PHI re-balancing, or any
SAC-side change.

---

## Direct evidence

Per-agent sign-pair response across the 3 SG-side disturbance buses
(`probes/kundur/probe_b_sign_pair.py --protocol gen --bus {1,2,3}`,
mag ±0.5 sys-pu, identical seed=42):

| Disturbance source | agents responding (>1e-3 Hz) | dominant agent | dominant Δf | static agents |
|---|---|---|---:|---|
| G1 (Bus 1) | **1/4** | ES1 | 0.062 Hz | ES2, ES3, ES4 (~ 2 μHz) |
| G2 (Bus 2) | **1/4** | ES1 | 0.097 Hz | ES2, ES3, ES4 (~ 2-3 μHz) |
| G3 (Bus 3) | **2/4** | ES3 + ES4 | 0.021 + 0.017 Hz | ES1, ES2 (1-6 μHz) |

Average across uniform random_gen sampling: **(1+1+2)/3 = 1.33 / 4
agents** receive non-trivial r_f gradient per scenario.

Per-agent silence floor: ES2 has `omega std ≈ 5e-6 pu` ≈ 0.25 mHz
across all 3 SG-side scenarios — within MATLAB's float64 numerical
noise floor, indistinguishable from zero physical response.

Source artifacts:
- `results/harness/kundur/cvs_v3_probe_b/probe_b_{pos,neg}_gen_b{1,2,3}.json`
  (per-episode metrics with per-agent decomposition)
- `results/harness/kundur/cvs_v3_probe_b/PROBE_B_STOP_VERDICT.md`
  (full numerical breakdown + addendum)

---

## What this falsifies

| Claim | Status |
|---|---|
| "+10-12% RL improvement is paper-faithful 4-agent coordination" | **FALSIFIED** — at most 1.33 agents receive signal per scenario; "4-agent coordination" cannot be learned from a 1.33-agent signal |
| "PHI re-balancing will improve eval performance" | **ALREADY FALSIFIED** by phi_resweep_v2 (eval flat at -19.5 across PHI=1e-4 → 5e-4) |
| "Action range [−6,18] is the binding constraint vs paper [−100,300]" | **DOWNGRADED** — even paper-literal action range cannot rescue a missing learning signal in 3-of-4 agents |
| "More SAC training will close the gap to paper -8.04 trained DDIC" | **FALSIFIED** — additional SAC samples on a degenerate-gradient protocol amplify only ES1's learned policy; ES2 stays at random-init forever |

## What this confirms

| Claim | Status |
|---|---|
| 2026-04-30 fresh-context audit R5 (DEGENERATE_GRADIENT) | **CONFIRMED** with direct empirical evidence (G1/G2/G3 sign-pairs) |
| 4-agent omega measurements are NOT aliased | **CONFIRMED** by Probe B G2 (4 distinct sha256 within run, 8 distinct across pos/neg) |
| Earlier `loadstep_metrics.json` 5-scenario bit-identicality was the dead R-block, not measurement collapse | **CONFIRMED** by per-agent variance under live disturbance |

## What this introduces (D-T6)

| Finding | Source |
|---|---|
| ES2 (Bus 16) is a structurally dead agent under all SG-side `pm_step_proxy_g*` protocols | Probe B G1+G2+G3 (zero response std ~ 5e-6 pu) |
| Project-assumed area mapping (ES1+ES2 ∈ area 1, ES3+ES4 ∈ area 2) is empirically WRONG for area 1 | Probe B: G1+G2 reach only ES1; ES2 silent |
| Whether ES2 swing-eq is responsive AT ALL (vs build-script wiring bug) | Currently UNDETERMINED — Probe B-ESS in flight |

Registered in `docs/paper/kundur-paper-project-terminology-dictionary.md`
§3 row D-T6 (Tier A — physics-essential).

---

## Hard locks (effective immediately)

1. **Do NOT resume E1a (PHI=0 ablation)** — its checkpoint was healthy
   but its conclusion would only address "is r_f causal under a 1.33-agent
   signal?" which is downstream of the protocol problem. Snapshot remains
   at `results/harness/kundur/cvs_v3_e1_phi0_ablation/aborted_run_snapshot/`
   for reference.

2. **Do NOT start HPO under any current protocol** — optimal SAC over a
   1.33-agent signal cannot reproduce 4-agent coordination. HPO ceiling
   is bounded structurally; runtime is wasted.

3. **Do NOT publish or compare project `cum_unnorm` against paper -8.04
   / -15.20** — protocol mismatch + degenerate gradient make the
   comparison apples-vs-oranges. Publishable claims are limited to
   "trained vs no_control under same project protocol".

4. **Do NOT continue adding scenarios / DIST_MAX tuning** — magnitude
   does not fix degeneracy. P1b at DIST_MAX=3.0 still shows 1-2/4
   agents responding per scenario.

5. **Do NOT touch build/.slx/reward/obs/SAC code in the next iteration**
   — Option F design is deliberately scoped to env disturbance scheduling
   only. Physical-layer fixes (Option E CCS at Bus 7/9) require a
   separate, larger-scope decision.

---

## Released path

The next valid forward step is **Option F design** (multi-point Pm-step
scheduling in `disturbance_protocols.py` + `_apply_disturbance_backend`),
**conditional on Probe B-ESS** returning ES{i} swing-eq response status.

- **If Probe B-ESS shows all 4 ES{i} respond to direct Pm injection**:
  Option F can include ES2 via multi-point dispatch. Design is
  unblocked.
- **If Probe B-ESS shows ES2 does NOT respond to direct Pm injection**:
  Option F cannot reach ES2 without a build-script repair.  Option F
  design must explicitly mark ES2 as a structural dead agent until
  physical layer is fixed; "best achievable Option F" is a 3-agent
  protocol (ES1 + ES3 + ES4).

In either case, Option F is **design-only this iteration** — no
training, no checkpoint, no env runtime change beyond dispatch
extension. The point is to specify exactly what scheduling change
would deliver paper-faithful multi-agent excitation, and to estimate
the achievable improvement ceiling under that scheduling.

---

## File anchor

`docs/superpowers/plans/2026-04-30-option-f-design.md` (to be written
once Probe B-ESS verdict is in) is the next deliverable. It must
reference:
- This STOP verdict (gradient degeneracy as the binding constraint)
- `kundur-paper-project-terminology-dictionary.md` row D-T6 (ES2 dead)
- Probe B + Probe B-ESS verdicts as the empirical foundation
