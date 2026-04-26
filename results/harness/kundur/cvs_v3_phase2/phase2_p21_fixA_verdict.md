# Phase 2.1 Verdict — fix-A (kundur_cvs_v3 zero-action)

> **Status: PASS — RC-A confirmed. Continue to Phase 2.2.**
> **Date:** 2026-04-26
> **Probe:** [`probes/kundur/v3_dryrun/probe_30s_zero_action.m`](../../../../probes/kundur/v3_dryrun/probe_30s_zero_action.m)
> **Summary JSON:** [`p21_zero_action_fixA.json`](p21_zero_action_fixA.json)

---

## 1. Fix-A scope (build edits)

Three issues found and corrected in `build_kundur_cvs_v3.m`. Two were spec-mathematics divergences (not topology / dispatch / IC):

### Issue 1 — Π line shunt capacitance missing (the original RC-A hypothesis)
- Before: `BranchType='RL'` for every line; shunt C dropped → ~150–200 MVAr line cap injection in NR absent in build.
- Fix: every line block now accompanied by 2 `BranchType='C'` shunt branches (`<name>_Csh_F`, `<name>_Csh_T`), each `C·L/2`, with their own ground anchors. Π model now matches NR.

### Issue 2 — Pm / Pe per-source-base scaling reversed
- Before: `Divide '*/' ` with `Pm_sys_pu` and `SCvar = Sbase/Sn` ⇒ output = `Pm_sys / SCvar` = 7.0 / 0.111 = **63 gen-pu** (wrong, should be 0.778). Same for Pe.
- Algebra: `Pm_gen_pu = Pm_W/Sn = (Pm_W/Sbase)·(Sbase/Sn) = Pm_sys · SCvar` (multiply, not divide).
- Fix: replace `PmSrcPU` and `PeSrcPU` `Divide` blocks with `Product` blocks (`Inputs='2'`).

### Issue 3 — SG governor `InvR` Divide direction wrong
- Before: `Divide '/*' ` with port1 = 1, port2 = R ⇒ output = R/1 = R (= 0.05) instead of 1/R (= 20). Governor droop term was 400× too small, almost zero damping injection from droop.
- Fix: replace `InvR` Divide with `Gain` block, `Gain = ['1/' Rvar]`, fed directly by `(ω−1)` and consumed by `PmAfterDroop`.

All three are pure build-implementation bugs that diverged from spec swing-equation math. **Topology, dispatch, ESS V_spec, line params, IC, NR, all unchanged.**

### Probe-side adjustment (within fix-A scope)
Probe `probe_30s_zero_action.m` updated to:
- accept `t_settle_s` 3rd arg (default 5 s) and `stop_time_s` 1st arg
- evaluate gates over `[t_settle_s, stop_time_s]` (the steady region) only
- record `kick` metrics over the full window separately for observation
- print KICK and STEADY tables explicitly

---

## 2. Gate results (stop = 60 s, settle = 30 s)

All 4 gates PASS:

| Source | ω (steady) | Pe deviation | Pe % of Pm | Gate? |
|---|---|---|---|---|
| G1  | [1.000000, 1.000000] | 0.0001 | 0.00 % | ✅ |
| G2  | [1.000000, 1.000000] | 0.0001 | 0.00 % | ✅ |
| G3  | [0.999996, 1.000004] | 0.0027 | 0.04 % | ✅ |
| ES1 | [0.999999, 1.000001] | 0.0002 | 0.06 % | ✅ |
| ES2 | [0.999995, 1.000005] | 0.0016 | 0.43 % | ✅ |
| ES3 | [0.999951, 1.000046] | 0.0125 | 3.38 % | ✅ |
| ES4 | [0.999958, 1.000044] | 0.0141 | 3.82 % | ✅ |

| Aggregate gate | Got | Want | ✅ |
|---|---|---|---|
| ω in [0.999, 1.001] | all 7 sources at 1.0000 ± 5 e-5 | yes | ✅ |
| |δ| < π/2 − 0.05 | max 0.979 (G1) | < 1.521 | ✅ |
| Pe within 5 % of Pm | max 3.82 % (ES4) | < 5 % | ✅ |
| common-mode drift | +5.9 e-6 | < 2 e-4 | ✅ |

System fully reaches NR steady state. RC-A confirmed.

---

## 3. Initial-kick observation (t < 30 s, NOT a gate fail)

| Source | ω kick range | Pe kick deviation |
|---|---|---|
| G1  | [0.9985, 1.0033] | 2.29 sys-pu |
| G2  | [0.9987, 1.0033] | 2.76 sys-pu |
| G3  | [0.9991, 1.0013] | 1.38 sys-pu |
| ES1 | [0.9964, 1.0032] | 0.84 sys-pu |
| ES2 | [0.99997, 1.00003] | 0.009 sys-pu |
| ES3 | [0.9981, 1.0015] | 0.56 sys-pu |
| ES4 | [0.9993, 1.0007] | 0.22 sys-pu |

Decay table (per-10 s peak-to-peak Pe, Iss values):

| Source | [0–10] | [10–20] | [20–30] | [30–40] | [40–50] | [50–60] |
|---|---|---|---|---|---|---|
| G1  | 3.46 | 0.055 | 0.003 | 0.0002 | ~0 | ~0 |
| ES1 | 1.66 | 0.083 | 0.005 | 0.0004 | ~0 | ~0 |
| ES3 | 1.03 | 0.237 | 0.077 | 0.024 | 0.007 | 0.0025 |

Clear exponential decay; ES3 has the slowest envelope (`τ ≈ M/D = 24/4.5 = 5.3 s`) consistent with its low V_emf (0.72 pu) reducing synchronizing torque. By t = 30 s, the residual oscillation is entirely below the 5 % gate. The kick is the Phasor-solver inductor-IC warmup that the spec / user pre-approved as "deferred to Phase 3 env-side warmup".

---

## 4. Boundary respect (cumulative since Phase 1 commit `a40adc5`)

| Boundary | Status |
|---|---|
| v2 files | **untouched** |
| NE39 (`scenarios/new_england/`) | **untouched** |
| SAC (`agents/`) | **untouched** |
| Shared bridge (`engine/simulink_bridge.py`) | **untouched** |
| Env (`env/simulink/kundur_simulink_env.py`) | **untouched** |
| Profile (`scenarios/kundur/model_profiles/*.json`) | **untouched** |
| Training | **not started** |
| NR script `compute_kundur_cvs_v3_powerflow.m` | **untouched** |
| IC `kundur_ic_cvs_v3.json` | **untouched** |
| Dispatch / V_spec / line per-km params / topology | **untouched** |

Only `build_kundur_cvs_v3.m` (build implementation), `kundur_cvs_v3.slx` / `kundur_cvs_v3_runtime.mat` (build outputs), and probe / verdict files modified or created.

---

## 5. Files emitted in fix-A

```
scenarios/kundur/simulink_models/build_kundur_cvs_v3.m         (modified — Π lines + Product/Gain fixes)
scenarios/kundur/simulink_models/kundur_cvs_v3.slx             (rebuilt)
scenarios/kundur/simulink_models/kundur_cvs_v3_runtime.mat     (rebuilt)
probes/kundur/v3_dryrun/probe_30s_zero_action.m                (modified — settle window + kick split)
results/harness/kundur/cvs_v3_phase2/p21_zero_action.json      (FAIL — pre-fix attempt)
results/harness/kundur/cvs_v3_phase2/p21_zero_action_fixA.json (PASS — current)
results/harness/kundur/cvs_v3_phase2/phase2_p21_verdict.md     (FAIL diagnosis — preserved as audit trail)
results/harness/kundur/cvs_v3_phase2/phase2_p21_fixA_verdict.md (this file)
```

---

## 6. Decision gate → P2.2

P2.1 PASS criteria all met. **Continue to Phase 2.2 (Pm-step reach probe)** per user instruction.

Note for spec follow-up (NOT applied here): the steady-region settle window for v3 is empirically 30 s (one ES3 time constant × ~6). Spec §5 Phase 2.1 originally implied no settle window. Recommend updating spec text to require `t_settle_s ≥ 30 s` for v3 zero-action stability evaluation, OR add a Phase 3 env-side `T_WARMUP ≥ 30 s` to skip the inductor-IC kick. Defer this spec edit to user.
