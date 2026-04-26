# Phase 4.1 Verdict — Disturbance-Routing Smoke FAILED at Warmup (Pre-existing Latent Gap)

> **Status:** SMOKE FAIL — root cause is a **pre-existing build-side runtime-contract gap**, NOT the P4.1 Path (C) disturbance_type dispatch. STOP with diagnosis only per user instruction; no fix attempted; no scope widening.
> **Date:** 2026-04-27
> **Predecessor:** Phase 4.0 audit PASS at commit `a5bc173`.
> **Plan:** [`quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_phase5_roadmap.md`](../../../../quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_phase5_roadmap.md)

---

## 1. What was implemented (P4.1 scope)

| File | Change | Status |
|---|---|---|
| `scenarios/kundur/config_simulink.py` | NEW `KUNDUR_DISTURBANCE_TYPE` constant + `KUNDUR_DISTURBANCE_TYPES_VALID` enum + env-var override + validator. Default `pm_step_single_vsg` (preserves legacy behavior). | ✓ implemented |
| `env/simulink/kundur_simulink_env.py::__init__` | NEW `disturbance_type` kwarg with config-default fallback + valid-set validator → stored as `self._disturbance_type`. | ✓ implemented |
| `env/simulink/kundur_simulink_env.py::_apply_disturbance_backend` v3 branch | NEW dispatch: `pm_step_proxy_bus7` → `(0,)` (ES1) / `pm_step_proxy_bus9` → `(3,)` (ES4) / `pm_step_proxy_random_bus` → per-call 50/50 / `pm_step_single_vsg` → legacy `getattr(self, 'DISTURBANCE_VSG_INDICES', (0,))`. | ✓ implemented |
| `probes/kundur/v3_dryrun/probe_loadstep_disturbance_routing.py` | NEW Python smoke probe: 7 episodes (bus7 ×1, bus9 ×1, random_bus ×4, single_vsg ×1), reads back `Pm_step_amp_1..4` from MATLAB workspace, runs 50 zero-action steps, validates target_idx + freq_dev + finite + tds_failed. | ✓ implemented |

**Boundaries upheld (per user GO message):**
- `build_kundur_cvs_v3.m`, `kundur_cvs_v3.slx`, `kundur_ic_cvs_v3.json`, `kundur_cvs_v3_runtime.mat`: **untouched** ✓
- `engine/simulink_bridge.py`: **untouched** ✓
- `slx_helpers/vsg_bridge/*`: **untouched** ✓
- NE39 (`scenarios/new_england/`, `env/simulink/ne39_simulink_env.py`): **untouched** ✓
- No 50-ep / 2000-ep training launched ✓

**Static checks (pre-MATLAB):**
- Config import + valid-set assert: PASS
- Env constructor signature exposes `disturbance_type`: PASS
- Invalid `disturbance_type='bad_value'` raises ValueError before MATLAB engine starts: PASS

---

## 2. Smoke result

```
RESULT: smoke_ok=False
RESULT: 7/7 episodes FAILED at env.reset() warmup
```

All 7 episodes (including legacy `pm_step_single_vsg` — which uses NO new code) failed identically at `bridge.warmup(T_WARMUP=10.0)` → `slx_episode_warmup_cvs` → Phase 2 `sim('kundur_cvs_v3')`. The Path (C) disturbance_type dispatch code was **never reached** — failure is at the first warmup, before `apply_disturbance` is called.

Artifact: [`p41_disturbance_routing_smoke.json`](p41_disturbance_routing_smoke.json), [`p41_smoke_stdout.txt`](p41_smoke_stdout.txt), [`p41_smoke_stderr.txt`](p41_smoke_stderr.txt).

The matlab.engine str round-trip lost the native Chinese-locale bytes (`status.error` came through as mojibake `Warmup sim failed: ����ԭ���´���`). Four cumulative diagnostics reconstructed the underlying error:

| Diag | Approach | Output |
|---|---|---|
| 1 | Read mojibake bytes from `p41_smoke_stdout.txt` and decode as gb18030/cp936 | All replacement chars — bytes already corrupted upstream by matlab.engine wrapper |
| 2 [`p41_diag_native_stdout.txt`](p41_diag_native_stdout.txt) | Cold-start engine + invoke helper, capture `status.error` and matlab stdout/stderr | Same mojibake; engine.eval truncated at first non-ASCII boundary |
| 3 [`p41_native_err_utf8.txt`](p41_native_err_utf8.txt) | Cold-start engine + manual seed + direct `sim()` + write `unicode2native(ME.message,'UTF-8')` to file | Got: `多种原因导致错误。` (`MATLAB:MException:MultipleErrors` placeholder; depth-1 cause chain traversal exhausted) |
| 4 [`p41_native_err_extended.txt`](p41_native_err_extended.txt) | Same setup + `getReport(ME, 'extended', 'hyperlinks', 'off')` to UTF-8 file | Full Simulink diagnostic chain unrolled |
| 5 [`p41_helper_native_err_extended.txt`](p41_helper_native_err_extended.txt) | Helper-mediated path: call `slx_episode_warmup_cvs` (which loads `runtime.mat` Phase 0), then on `status.success=0` re-run `sim()` ourselves under the same workspace and capture `getReport(extended)` | Distinguishes WHAT helper Phase 0 seeded vs WHAT is still missing — definitive root cause |

---

## 3. Root cause (pre-existing latent gap, NOT Path C)

**Incomplete build-side runtime contract for `kundur_cvs_v3`:**

`build_kundur_cvs_v3.m:194-198` seeds 6 wind-related workspace variables at build time via `assignin('base', ...)`:
- `WindAmp_1`, `WindAmp_2` (defaulted to 1.0)
- `Wphase_1`, `Wphase_2` (per-NR rotor angle)
- `WVmag_1`, `WVmag_2` (terminal voltage magnitude × Vbase)

These are referenced at runtime by `PVS_W1` / `PVS_W2` (the wind-bus Programmable Voltage Sources) for `Amplitude`, `Phase`, and base voltage parameters.

`build_kundur_cvs_v3.m:768-776` saves `runtime_consts` to `kundur_cvs_v3_runtime.mat`, but the wind block only writes:
```matlab
for w = 1:2
    runtime_consts.(sprintf('Wphase_%d', w)) = double(wind_term_a_rad(w));
    runtime_consts.(sprintf('WVmag_%d',  w)) = double(wind_term_v_pu(w) * Vbase);
end
% NOTE: WindAmp_w is NOT saved to runtime_consts.
```

`slx_episode_warmup_cvs.m:75-98` (Phase 0) loads `kundur_cvs_v3_runtime.mat` on `do_recompile=true` and assigns every field into base workspace. Since `WindAmp_1/WindAmp_2` are NOT in the .mat, they are NOT in the post-Phase-0 workspace. Phase 1b also does not seed them. `sim('kundur_cvs_v3')` therefore raises:

```
MATLAB:MException:MultipleErrors
原因:
    计算 'kundur_cvs_v3/PVS_W1' 中的参数 'Amplitude' 时出错
        函数或变量 'WindAmp_1' 无法识别。
            变量 'WindAmp_1' 不存在。
    计算 'kundur_cvs_v3/PVS_W2' 中的参数 'Amplitude' 时出错
        函数或变量 'WindAmp_2' 无法识别。
            变量 'WindAmp_2' 不存在。
```

(Diag 5 also confirmed `Wphase_1/Wphase_2` and `WVmag_1/WVmag_2` ARE in the post-Phase-0 workspace, so only `Amplitude` fails — `Phase` resolves correctly. This isolates the gap to `WindAmp_w` only.)

Diag 5 workspace dump (post helper Phase 0 + Phase 1b, before sim):
```
M_1..4, D_1..4, Pm_1..4, delta0_1..4, Pm_step_t_1..4, Pm_step_amp_1..4,
Vmag_1..4, VemfG_1..3, deltaG0_1..3, Pmg_1..3,
Wphase_1, Wphase_2, WVmag_1, WVmag_2,
ESS_M0, ESS_D0, SG_M_paper, SG_D_paper, SG_R_paper, SG_SN, VSG_SN,
Sbase_const, Vbase_const, wn_const, Pe_scale, L_gen_H, L_vsg_H
```

**`WindAmp_1/WindAmp_2` are absent.**

---

## 4. Why P3.4 5-episode smoke passed at the same commit `a5bc173`

P3.4 ran via the MCP-shared MATLAB engine (`probe_5ep_smoke_mcp.m`). That engine had accumulated **build-time** base-workspace state from earlier `build_kundur_cvs_v3` invocations on the same day (Phase 1.3 / Phase 2 probe runs) — including the `assignin('base', 'WindAmp_w', 1.0)` from line 195 of the build script. Since MCP-shared engine never quit, those vars persisted into the warmup window.

**Cold-start engine (Python smoke probe) starts with empty base workspace** → Phase 0 loads only what `runtime.mat` contains → `WindAmp_w` missing → sim() fails.

This means **the P3.4 PASS verdict is not invalidated** for the MCP-shared-engine path, but the runtime contract is fragile:
- ANY cold-start runner (a fresh Python `KundurSimulinkEnv()` outside an MCP-warm engine) will hit this exact failure on first reset.
- Phase 4 SAC training launched via `scripts/launch_training.ps1` cold-starts a Python process with its own MATLAB engine — same gap.

---

## 5. Path C dispatch verification (deferred — cannot run until warmup gap is closed)

The P4.1 smoke probe never reached `apply_disturbance`. So the four behavioral assertions on Path C dispatch are **NOT YET VERIFIED**:

- (a) `pm_step_proxy_bus7` → `Pm_step_amp_1` nonzero, `Pm_step_amp_{2,3,4}` zero — UNVERIFIED
- (b) `pm_step_proxy_bus9` → `Pm_step_amp_4` nonzero, `Pm_step_amp_{1,2,3}` zero — UNVERIFIED
- (c) `pm_step_proxy_random_bus` × 4 draws → mix of `(0,)` and `(3,)` — UNVERIFIED
- (d) Each mode produces nonzero finite ω response over 50 zero-action steps — UNVERIFIED

The dispatch code is statically correct (mapping logic + RNG path inspected, error path tested via ValueError), but no runtime evidence yet.

---

## 6. Fix candidates (NOT applied — user instructed stop-and-diagnose only)

Each candidate violates the P4.1 scope or §0 hard non-goals. Reporting for user decision.

| Candidate | Surface | Why it fixes | Why it widens scope |
|---|---|---|---|
| **A — build edit** | `build_kundur_cvs_v3.m:768-776` add `runtime_consts.(sprintf('WindAmp_%d', w)) = 1.0;` then re-run build to re-emit `kundur_cvs_v3_runtime.mat` (file regeneration only — same .slx) | `runtime.mat` then carries `WindAmp_w`; helper Phase 0 seeds it → sim() finds it | Touches `build_kundur_cvs_v3.m` (locked in §0); regenerates `_runtime.mat` (locked in §0). Requires explicit user authorization. |
| **B — helper edit** | `slx_episode_warmup_cvs.m` Phase 1b: add `vars.(sprintf('WindAmp_%d', w)) = 1.0;` for w=1..2 | Helper seeds it on every reset → independent of .mat content | Touches shared helper (locked in §0). Requires R-h-class authorization. |
| **C — env edit** | `env/simulink/kundur_simulink_env.py::_reset_backend` after bridge.load_model + before bridge.warmup, call `self.bridge.apply_workspace_var('WindAmp_1', 1.0)` and `WindAmp_2` | Env-only change inside P4.1 allow-list | Widens beyond Path (C) **disturbance dispatch**; user GO message limited P4.1 env edit to `_apply_disturbance_backend`. |
| **D — operational** | Pre-launch hook: run a short MATLAB script (or eng.eval) in the env's MATLAB engine that does `assignin('base', 'WindAmp_w', 1.0)` for w=1..2, before any reset | No allow-list edit; runs at probe / training startup | Adds a documented launch contract. The cleanest minimal-intervention; could be done as a 2-line Python eval inside the probe itself if user authorizes "probe-side workspace seeding only". |

---

## 7. Verdict

**FAIL** — Phase 4.1 smoke could not validate the Path (C) disturbance_type dispatch because the warmup chain fails on cold-start MATLAB engines due to a pre-existing, P4.1-unrelated runtime-contract gap (`WindAmp_w` missing from `kundur_cvs_v3_runtime.mat`).

**Path (C) dispatch code is statically correct and not the cause.** Diag 5 isolates the failure to `WindAmp_1`/`WindAmp_2` being unrecognized at sim-time, originating in `build_kundur_cvs_v3.m:768-776` not saving them to the runtime sidecar.

**No fix applied.** Stopping with diagnosis only per user GO message: "If smoke fails, stop with diagnosis only; do not widen scope."

---

## 8. Decision points for user

1. Authorize **Candidate D (operational)** — pre-warmup workspace seeding inside the probe (no allow-list breach)? Smallest delta to validate Path (C) dispatch.
2. Authorize **Candidate C (env edit, widened)** — env-side `_reset_backend` seeds WindAmp_w before warmup? Persistent runtime fix, scoped to env.
3. Authorize **Candidate A (build edit, scope expansion)** — fix at the source (`build_kundur_cvs_v3.m`) and regenerate `kundur_cvs_v3_runtime.mat`? Requires explicit lift of the §0 lock on build/runtime.mat.
4. Authorize **Candidate B (helper edit, scope expansion)** — fix in `slx_episode_warmup_cvs.m`? Requires R-h-class authorization and impacts v2 path as well (low risk, both v2 and v3 wind PVS use the same naming).
5. Defer Phase 4 work pending decision; current state is reproducible and benign.

---

## 9. Artifacts emitted

```
results/harness/kundur/cvs_v3_phase4/
├── phase4_p40_audit_verdict.md            (Phase 4.0 — PASS, prior session)
├── phase4_p41_verdict.md                  (this file)
├── p41_disturbance_routing_smoke.json     (probe summary; smoke_ok=false)
├── p41_smoke_stdout.txt                   (probe stdout; mojibake error)
├── p41_smoke_stderr.txt                   (probe stderr; mojibake stack)
├── p41_diag_native_stdout.txt             (Diag 2 — engine reachable, MATLAB 2025b)
├── p41_diag_native_stderr.txt             (Diag 2 — wrapper stderr in mojibake)
├── p41_native_err_utf8.txt                (Diag 3 — placeholder MultipleErrors)
├── p41_diag2_stdout.txt / stderr.txt      (Diag 3 invocation log)
├── p41_native_err_extended.txt            (Diag 4 — full Wind error chain via direct sim)
├── p41_diag3_stdout.txt / stderr.txt      (Diag 4 invocation log)
└── p41_helper_native_err_extended.txt     (Diag 5 — runtime.mat contents + post-Phase-0 ws + sim error;
                                                       definitive isolation to WindAmp_w only)

probes/kundur/v3_dryrun/
├── probe_loadstep_disturbance_routing.py  (P4.1 routing smoke; PASS-status when warmup gap is closed)
├── _diag_p41_warmup_native_error.py       (Diag 2/3 — captures status.error and matlab stderr in raw bytes)
├── _diag_p41_native_err_utf8.py           (Diag 4 — direct sim() + ME.message via UTF-8 file)
└── _diag_p41_via_helper_extended.py       (Diag 5 — runtime.mat probe + helper invocation + replay sim getReport)
```

Awaiting user decision (item 1–4 above) before resuming Phase 4 sequencing.
