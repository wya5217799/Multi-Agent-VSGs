# Phase 4.1a Verdict — Cold-start runtime-const fix (WindAmp_w) — PARTIAL

> **Status:** PARTIAL — `WindAmp_1/2` fix landed and verified at the .mat layer. Cold-start sim() verification then exposed **22 additional missing workspace vars** of the same class (build-time `assignin('base')` not propagated to `runtime.mat`). Scope-bounded as authorized: STOP at WindAmp-only and surface the broader gap for explicit user decision before extending P4.1a or proceeding to P4.1 rerun.
> **Date:** 2026-04-27
> **Predecessor:** Phase 4.1 verdict (FAIL, root cause: WindAmp_w missing). Commit at start: `a5bc173`.
> **Plan:** [`quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_phase5_roadmap.md`](../../../../quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_phase5_roadmap.md)
> **Authorization:** user GO message — "走 A，但单独开 P4.1a cold-start runtime-const fix … 只修 build_kundur_cvs_v3.m 的 runtime_consts 写出逻辑，把 WindAmp_1/2 加入 kundur_cvs_v3_runtime.mat".
> **NOT** counted as P4.1 dispatch verification.

---

## 1. Change applied (WindAmp_1/2 fix)

[`scenarios/kundur/simulink_models/build_kundur_cvs_v3.m:768-783`](../../../../scenarios/kundur/simulink_models/build_kundur_cvs_v3.m): inside the existing `for w = 1:2` runtime_consts emission loop, added `runtime_consts.(sprintf('WindAmp_%d', w)) = double(1.0);` with explanatory comment citing P4.1 root-cause analysis.

Surface scope kept exactly as authorized:
- ✓ Edited `build_kundur_cvs_v3.m` runtime_consts wind block only.
- ✓ `kundur_cvs_v3.slx` topology unchanged (deterministic build; pre-fix sha256 = `e9a6f223…`, post-fix sha256 = `4a69f317…`; binary differs only in MATLAB save metadata, no add_block / set_param differences. Build log: `lines=20, loads=2, shunts=2, loadsteps=2, ESS Pm0_sys_pu=[-0.3691 …], SG Pm0_sys_pu=[7.0000 7.0000 7.1900]` — identical to pre-fix run).
- ✓ `kundur_ic_cvs_v3.json` untouched.
- ✓ `simulink_bridge.py` untouched.
- ✓ `env/simulink/kundur_simulink_env.py` dispatch path untouched (P4.1 commits stand).
- ✓ Reward / training paths untouched.
- ✓ NE39 untouched.
- ✓ No 50-ep / 2000-ep training launched.

Mat-level verification ([`p41a_regen_stdout.txt`](p41a_regen_stdout.txt)):
- pre-fix mat sha256 = `bff39964…` (38 fields)
- post-fix mat sha256 = `e9cb4997…` (40 fields)
- `WindAmp_1 = 1.0` ✓
- `WindAmp_2 = 1.0` ✓

---

## 2. Cold-start helper-warmup verification ([`p41a_coldstart_verify_stdout.txt`](p41a_coldstart_verify_stdout.txt))

Re-ran `_diag_p41_via_helper_extended.py` (Diag 5 from P4.1) post-fix. Result:

- `runtime.mat exists=1` ✓
- 40 fields including **`WindAmp_1`, `WindAmp_2`** ✓
- `slx_episode_warmup_cvs(do_recompile=true)` Phase 0 loads all 40 fields into base workspace ✓
- Workspace post Phase 0 + Phase 1b includes WindAmp_1/2, Wphase_1/2, WVmag_1/2 ✓
- **`helper.success = 0`** — sim() still fails, but with a DIFFERENT error chain.

The new sim() error chain (from `getReport(extended)` written via `unicode2native(...,'UTF-8')`, [`p41_helper_native_err_extended.txt`](p41_helper_native_err_extended.txt)) lists 28 unrecognized variables across 28 Simulink blocks. The previous `WindAmp_1/2` errors are gone. The new gap is structurally identical — build-time `assignin('base', …)` workspace seeds NOT propagated to `runtime.mat`, but for a different set of variables.

---

## 3. Newly exposed gap (22 problematic vars + 6 dead-path vars)

Cross-referenced `build_kundur_cvs_v3.m` `assignin('base', …)` calls (lines 163-205) against current `kundur_cvs_v3_runtime.mat` field list and `slx_episode_warmup_cvs.m` Phase 1b runtime seeds.

### 3.1 SG dynamics (15 vars; reference live Simulink blocks)

| Variable | Build-time line | Referenced by block | Build-time value | Why missing |
|---|---|---|---|---|
| `Mg_{1,2,3}` | L170 | `Mgain_G{1,2,3}` Gain | `2 * sg_H_paper(g)` (G1=14.0, G2=14.0, G3=23.4) | not in runtime_consts |
| `Dg_{1,2,3}` | L171 | `Dgain_G{1,2,3}` Gain | `sg_D_paper(g)` | not in runtime_consts |
| `Rg_{1,2,3}` | L172 | `InvR_G{1,2,3}` Gain | `sg_R_paper(g)` | not in runtime_consts |
| `PmgStep_t_{1,2,3}` | L177 | `Pm_step_t_c_G{1,2,3}` Constant.Value | `5.0` | not in runtime_consts AND not in helper Phase 1b |
| `PmgStep_amp_{1,2,3}` | L178 | `Pm_step_amp_c_G{1,2,3}` Constant.Value | `0.0` | not in runtime_consts AND not in helper Phase 1b |

Note: `runtime.mat` does carry `SG_M_paper / SG_D_paper / SG_R_paper` as **3-element row vectors**, but the .slx blocks reference scalar names `Mg_<g>` etc. The vector form is unused by the model. Either option (a) materialize per-source scalars during runtime or (b) re-emit per-source scalars in runtime_consts — both are P4.1a-extended.

### 3.2 Source scale factors (7 vars; reference live Simulink blocks)

| Variable | Build-time line | Referenced by block | Build-time value | Why missing |
|---|---|---|---|---|
| `VSGScale_{1,2,3,4}` | L186 | `SCvar_c_ES{1..4}` Constant.Value AND `Sscale_c_ES{1..4}` Constant.Value | `Sbase / VSG_SN` | not in runtime_consts |
| `SGScale_{1,2,3}` | L174 | `SCvar_c_G{1,2,3}` Constant.Value AND `Sscale_c_G{1,2,3}` Constant.Value | `Sbase / SG_SN` | not in runtime_consts |

### 3.3 LoadStep workspace (6 vars; DEAD per Phase 4.0 audit §R2-Blocker1 — benign)

`G_perturb_{1,2}_S`, `LoadStep_t_{1,2}`, `LoadStep_amp_{1,2}` are `assignin('base', …)` at L202-204 but NOT referenced by any Simulink block (build script hardcodes `Resistance='1e9'` at L316-336; verified Phase 4.0 audit). **Their absence in `runtime.mat` does NOT trigger sim() errors.** Skip these in any P4.1a extension.

---

## 4. Path C dispatch verification — STILL BLOCKED, NOT RUN

Per user GO instruction: "5. 再回到 P4.1，重新运行 Path C dispatch smoke" — this step requires cold-start warmup to succeed. With 22 still-missing vars, the cold-start probe would fail at warmup again (different error class but same probe outcome). Holding the rerun until user authorizes P4.1a-extended.

---

## 5. Why P3.4 5-ep smoke at commit `a5bc173` still passed

Same explanation as Phase 4.1 verdict §4: P3.4 ran via the **MCP-shared MATLAB engine** that had `assignin('base', …)` workspace state lingering from earlier same-day `build_kundur_cvs_v3` invocations. All 28 (now 22 problematic + 6 dead) build-time workspace assigns were already in the warm engine's base workspace; helper Phase 0 loading the .mat just over-wrote those (with overlapping subset) but the WindAmp/Mg/Dg/etc. survived. **Cold-start engine** (Python smoke probe + future Phase 4.x training launches via `scripts/launch_training.ps1`) starts empty.

This is a single class of bug (incomplete runtime contract), worse than the WindAmp diagnosis suggested. Same fix pattern works for all 22 problematic vars.

---

## 6. Decision points for user (P4.1a continuation)

1. **Authorize P4.1a-extended (RECOMMENDED):** add the 22 problematic vars (15 SG dynamics + 7 scale factors) to `build_kundur_cvs_v3.m` runtime_consts emission alongside the existing WindAmp_w block. Re-run build, regenerate `_runtime.mat` once more (40 → ~62 fields), re-run Diag 5 to confirm `helper.success=1` and sim() completes the warmup. Then resume P4.1 dispatch smoke rerun.
   - Surface: build script edit only; same allow-list as P4.1a-WindAmp; deterministic re-emission.
   - Risk: low. Each var has a build-time computed value already in scope at L745 (Vbase, Sbase, sg_H_paper, sg_D_paper, sg_R_paper, ESS_M0/D0, SG_SN, VSG_SN). Just lift them into `runtime_consts` like WindAmp.
   - Wall: ~5 min build + verification.

2. **Alternative — extend `slx_episode_warmup_cvs.m` Phase 1b:** make the helper seed Mg/Dg/Rg/PmgStep_t/PmgStep_amp/VSGScale/SGScale at every reset using `cfg` fields. Closer to the existing helper contract; touches `slx_helpers/vsg_bridge/`, which is locked under §0 (would need explicit R-h-class lift).

3. **Alternative — env-side seed:** `_reset_backend` pushes the 22 vars via `apply_workspace_var` before `bridge.warmup`. Allowed by env edit scope, but persistent runtime overhead and widens P4.1 dispatch scope.

4. **Hold P4.1a here, do not extend:** keep WindAmp-only fix; defer cold-start unblocking; P4.1 smoke remains UNVERIFIED. Phase 4.2 PHI sweep would then require running on MCP-shared engine (operational workaround) until a future scope-extension authorization.

5. Current state (P4.1a partial): no extra mitigation, return to user input.

---

## 7. Artifacts emitted

```
scenarios/kundur/simulink_models/
├── build_kundur_cvs_v3.m            (EDITED L773-783: WindAmp_w added to runtime_consts)
├── kundur_cvs_v3.slx                 (re-saved by build; topology unchanged; sha256 e9a6f223 -> 4a69f317)
└── kundur_cvs_v3_runtime.mat         (re-emitted; 38 -> 40 fields; sha256 bff39964 -> e9cb4997)

probes/kundur/v3_dryrun/
└── _p41a_regen_runtime_mat.py        (new diagnostic helper to invoke build + verify mat)

results/harness/kundur/cvs_v3_phase4/
├── phase4_p41a_verdict.md            (this file)
├── p41a_regen_stdout.txt             (build invocation log; mat 38->40 confirmed)
├── p41a_regen_stderr.txt             (empty)
├── p41a_coldstart_verify_stdout.txt  (cold-start helper run post-fix; helper.success=0 with new error)
├── p41a_coldstart_verify_stderr.txt  (empty)
└── p41_helper_native_err_extended.txt (overwritten by post-fix run; 22 missing vars listed in causes)
```

Awaiting user decision (item 1–4 above) before continuing.
