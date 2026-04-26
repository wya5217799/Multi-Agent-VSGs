# Phase 4.1a-v2 Verdict — Cold-start runtime-const fix (extended) — PASS

> **Status:** PASS — `runtime.mat` now carries the full set of v3 cold-start workspace contract (40 → 62 fields). Fresh-engine `slx_episode_warmup_cvs` + 2-second zero-action sim both succeed. Cold-start path unblocked. P4.1 dispatch smoke can now rerun.
> **Date:** 2026-04-27
> **Predecessor:** Phase 4.1a (PARTIAL — only WindAmp fix). Phase 4.1 (FAIL — warmup blocked).
> **Plan:** [`quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_phase5_roadmap.md`](../../../../quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_phase5_roadmap.md)
> **Authorization:** user GO message — "继续 P4.1a Path A，但只扩展 cold-start runtime-const fix … 在已加入 WindAmp_1/2 的基础上，继续加入 22 个 …".

---

## 1. Edits applied

[`scenarios/kundur/simulink_models/build_kundur_cvs_v3.m:762-797`](../../../../scenarios/kundur/simulink_models/build_kundur_cvs_v3.m): extend `runtime_consts` emission inside the existing per-source loops. Added 22 fields routed through the same .mat sidecar that `slx_episode_warmup_cvs.m` Phase 0 already loads:

| Block of vars | Added at | Build-time value source |
|---|---|---|
| `Mg_{1,2,3}`, `Dg_{1,2,3}`, `Rg_{1,2,3}` (SG dynamics) | inside `for g = 1:3` | `2 * sg_H_paper(g)`, `sg_D_paper(g)`, `sg_R_paper(g)` |
| `PmgStep_t_{1,2,3}` = 5.0, `PmgStep_amp_{1,2,3}` = 0.0 (SG Pm-step gating) | inside `for g = 1:3` | matches build L177-178 default |
| `SGScale_{1,2,3}` (SG gen-pu → sys-pu scale) | inside `for g = 1:3` | `Sbase / SG_SN` (matches build L174) |
| `VSGScale_{1,2,3,4}` (ESS vsg-pu → sys-pu scale) | inside `for i = 1:4` | `Sbase / VSG_SN` (matches build L186) |

`WindAmp_{1,2}` (Phase 4.1a v1) preserved.

LoadStep workspace (`G_perturb_*`, `LoadStep_t_*`, `LoadStep_amp_*`) explicitly NOT added — Phase 4.0 audit §R2-Blocker1 confirmed these are dead-path (no Simulink block reads them; build hardcodes `Resistance='1e9'`). Adding them would mislead future readers about the LoadStep path's status.

Surface scope kept exactly as authorized:
- ✓ Edited `build_kundur_cvs_v3.m` runtime_consts emission only.
- ✓ `kundur_ic_cvs_v3.json` untouched.
- ✓ `slx_helpers/vsg_bridge/*` untouched (helper Phase 0 contract preserved; just gets a richer .mat to load).
- ✓ `engine/simulink_bridge.py` untouched.
- ✓ `env/simulink/kundur_simulink_env.py` (P4.1 dispatch code) untouched.
- ✓ Reward / training paths untouched.
- ✓ NE39 untouched.
- ✓ No 50-ep / 2000-ep training launched.
- ✓ LoadStep wiring path NOT touched (per user instruction "当前不是 LoadStep wiring fix").

---

## 2. .slx topology preservation evidence

The build re-saves `kundur_cvs_v3.slx` as a side effect (deterministic `save_system` after `add_block`/`add_line` calls). To document that **topology is unchanged**, the build's structural diagnostic prints are byte-identical across all v2/v3 regen invocations:

```
RESULT: 16-bus paper topology, 3 SG + 4 ESS swing-eq + 2 PVS
RESULT: lines=20, loads=2, shunts=2, loadsteps=2
RESULT: ESS Pm0_sys_pu = [-0.3691 -0.3691 -0.3691 -0.3691]
RESULT: SG  Pm0_sys_pu = [7.0000 7.0000 7.1900]
RESULT: ESS Vemf_pu    = [0.8401 0.9816 0.7215 0.9748]
RESULT: SG  Vemf_pu    = [1.1599 1.1128 1.1584]
```

(identical to the pre-fix Phase 1.3 / Phase 4.1a v1 build outputs). The `.slx` binary differs only in MATLAB save metadata (timestamps embedded in the .slx zip), not in topological content.

| Stage | .slx sha256 | .mat sha256 | .mat field count |
|---|---|---|---|
| Pre-Phase 4.1a (initial state) | `e9a6f223…` | `bff39964…` | 38 |
| After Phase 4.1a v1 (WindAmp only) | `4a69f317…` | `e9cb4997…` | 40 |
| After Phase 4.1a-v2 first regen | `eb47b63b…` | `cbb378d6…` | 62 |
| After Phase 4.1a-v2 confirmation regen | `90ac7754…` | `9825a49b…` | 62 |
| After Phase 4.1a-v2 final rerun (this verdict) | `de674209…` | `b4a3af52…` | 62 |

---

## 3. Cold-start verification ([`p41a_v2_summary.json`](p41a_v2_summary.json), [`p41a_v2_stdout.txt`](p41a_v2_stdout.txt))

Two-engine sequence: engine #1 = regen, then quit; engine #2 = fresh cold-start verify. The verify engine's pre-helper base workspace is empty (`ws_pre_count = 0`) — true cold-start condition.

Result on engine #2:

| Check | Outcome |
|---|---|
| `runtime.mat exists=1` | ✓ |
| `runtime.mat field count = 62` | ✓ |
| 22/22 expected-new fields present | ✓ |
| `WindAmp_1=True, WindAmp_2=True` | ✓ |
| `slx_episode_warmup_cvs(do_recompile=true)` `helper.success=True` | ✓ |
| `omega` 4-vec finite, max\|dev\| = 4.61e-4 (≈ 23 mHz residual at t_warmup=10s) | ✓ |
| `Pe` 4-vec finite, ∈ [−0.4067, −0.3250] sys-pu (paper-faithful: ESS absorbing surplus) | ✓ |
| 2-second StopTime=12.0 zero-action `sim('kundur_cvs_v3')` | ✓ no error |
| Overall | **PASS** |

omega per-ESS values:

```
omega = [1.0000070270, 1.0000128026, 1.0004608584, 1.0003146689]
```

Residual ω−1 ~ O(1e−4) at t_warmup=10s is consistent with the v3 Phasor inductor-IC settle profile documented in `scenarios/kundur/NOTES.md` (P3.3b WARMUP=10s decision); below the typical RL learning signal magnitude.

---

## 4. Why this matters for P4.1 / Phase 4.x

The runtime contract for v3 was previously coupled to **build-process workspace persistence** — only worked under MCP-shared engines that had build-time `assignin('base', …)` state still around. Cold-start engines (Python smoke probes; future training launches via `scripts/launch_training.ps1`) had an empty workspace and the helper-loaded .mat was missing 24 vars referenced by Simulink Constant/Gain blocks.

Post-Phase-4.1a-v2:
- `runtime.mat` now self-contained for the **physically referenced** workspace contract.
- `slx_episode_warmup_cvs.m` Phase 0 loads it; sim() resolves all referenced workspace vars.
- LoadStep path remains dead (intentional; Phase 4.0 §R2-Blocker1 confirmed). Future LoadStep wiring would require Path (A) build-edit per the roadmap §Gap 1, separately authorized.

P4.1 dispatch smoke can now rerun on cold-start engines.

---

## 5. Boundary check (always-on)

- `kundur_ic_cvs_v3.json`: untouched ✓
- `slx_helpers/vsg_bridge/slx_episode_warmup_cvs.m`: untouched ✓
- `engine/simulink_bridge.py`: untouched ✓
- `env/simulink/kundur_simulink_env.py` P4.1 dispatch (`_apply_disturbance_backend` v3 branch + `__init__` `disturbance_type` kwarg): untouched ✓
- `scenarios/kundur/config_simulink.py` (`KUNDUR_DISTURBANCE_TYPE` constant): untouched ✓
- Reward path: untouched ✓
- LoadStep wiring (`G_perturb_*`, `LoadStep_t/amp_*`, `kundur_cvs_v3/LoadStep7`, `kundur_cvs_v3/LoadStep9`): untouched ✓
- `kundur_cvs_v3.slx` topology (block names, parameters, connections, IC): untouched ✓
- NE39: untouched ✓
- No 50-ep / 2000-ep training launched ✓

---

## 6. Verdict

**PASS** — Phase 4.1a-v2 runtime-const fix complete. Cold-start contract for `kundur_cvs_v3` is now self-contained. Ready for P4.1 dispatch smoke rerun.

---

## 7. Artifacts emitted

```
scenarios/kundur/simulink_models/
├── build_kundur_cvs_v3.m                  (EDITED L762-797: SG/scale/WindAmp added to runtime_consts)
├── kundur_cvs_v3.slx                       (re-saved; topology unchanged; metadata-only binary diff)
└── kundur_cvs_v3_runtime.mat               (regen; 38 -> 62 fields)

probes/kundur/v3_dryrun/
└── _p41a_v2_regen_and_verify.py            (regen + 2-engine cold-start verify)

results/harness/kundur/cvs_v3_phase4/
├── phase4_p41a_runtime_consts_v2_verdict.md  (this file)
├── p41a_v2_stdout.txt                       (verify run log)
├── p41a_v2_stderr.txt                       (empty)
└── p41a_v2_summary.json                     (machine-readable summary)
```

---

## 8. Next step

Re-run **P4.1 dispatch smoke** (`probes/kundur/v3_dryrun/probe_loadstep_disturbance_routing.py`) on cold-start engine to verify Path (C) `pm_step_proxy_bus7 / bus9 / random_bus` actually reach `apply_disturbance` and produce the expected target-index workspace state + nonzero finite ω response. Result will land in `phase4_p41_rerun_verdict.md`.

Hard boundaries remain: no env / bridge / helper / build / .slx / IC / reward / NE39 edits; no 50-ep / 2000-ep training.
