# G3-prep E — Kundur CVS 5-Episode Plumbing Smoke FAILURE Report

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg` @ `4785cc9` (post-D-config commit)
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** FAILURE REPORT — diagnostic only. **No code change. No additional fix attempted.** Halt + await user decision.
**Predecessors:**
- G3-prep-D-config — `2026-04-26_kundur_cvs_g3prep_D_config_verdict.md` (commit `4785cc9`)
- D/E smoke spec — `2026-04-26_kundur_cvs_g3prep_DE_smoke_spec.md` (commit `0b22f49`)
- G3-prep-C — `2026-04-26_kundur_cvs_g3prep_C_verdict.md` (commit `90a0314`)

---

## Verdict: ABORT

5-ep CVS plumbing smoke crashed in **first ep `env.reset()`** during `bridge.warmup` → `_warmup_cvs` → `slx_episode_warmup_cvs.m` `sim()` call. Exit code 0 (Python handled the SimulinkError and exited cleanly), no run dir created under `results/sim_kundur/runs/`.

Two **independent** plumbing gaps confirmed by clean MCP repro (no production code touched):

1. **CVS `.slx` references base-workspace constants written ONLY by `build_kundur_cvs.m`** (`L_v_H`, `L_tie_H`, `L_inf_H`, `R_loadA`, `R_loadB`, `Vbase_const`, `wn_const`, `Sbase_const`, `Pe_scale`, `Vmag_<i>`). `_warmup_cvs` does not re-push them; a fresh MATLAB session that loads the `.slx` without rebuilding has none of these variables → 8-cause `Simulink:Parameters:BlkParamUndefined` cascade → sim fail.
2. **`KUNDUR_BRIDGE_CONFIG` (config_simulink.py) does not set CVS-specific BridgeConfig fields**, so the bridge inherits legacy defaults: `m_var_template='M0_val_ES{idx}'` (CVS .slx expects `M_<i>`), `d_var_template='D0_val_ES{idx}'` (expects `D_<i>`), `m0_default=12.0` (CVS needs 24.0), `d0_default=3.0` (CVS needs 18.0), `omega_signal='omega_ES{idx}'` (CVS uses `omega_ts_{idx}`). If gap (1) were fixed, the next sim attempt would fail at `M_<i>` undefined.

D-config OD-1 fix (commit `4785cc9`) only flipped `step_strategy='cvs_signal'` — necessary but not sufficient. Both (1) and (2) remained unaddressed, and were masked by the verify probe's same-session build-then-run pattern.

**Per user instruction**: "smoke 完成后停手汇报" + "若 ... FAIL: 5. 只写 failure report，不做额外修复". No fix is attempted in this commit. Boundary is clean.

---

## 1. Smoke command + observed crash

### 1.1 Command

```bash
KUNDUR_MODEL_PROFILE="$(pwd)/scenarios/kundur/model_profiles/kundur_cvs.json" \
"C:/Users/27443/miniconda3/envs/andes_env/python.exe" \
  scenarios/kundur/train_simulink.py \
  --mode simulink --episodes 5 --resume none --seed 42
```

### 1.2 Observed traceback

```
[Kundur-Simulink] Reset failed: slx_episode_warmup_cvs failed: Warmup sim failed: <cp936 garbled MATLAB msg>
Traceback (most recent call last):
  File "scenarios/kundur/train_simulink.py", line 695, in <module>
    train(args)
  File "scenarios/kundur/train_simulink.py", line 292, in train
    obs, _ = env.reset(options={"disturbance_magnitude": dist_mag})
  File "env/simulink/kundur_simulink_env.py", line 235, in reset
    self._reset_backend(options=options)
  File "env/simulink/kundur_simulink_env.py", line 653, in _reset_backend
    self.bridge.warmup(T_WARMUP)
  File "engine/simulink_bridge.py", line 476, in warmup
    self._warmup_cvs(duration)
  File "engine/simulink_bridge.py", line 650, in _warmup_cvs
    raise SimulinkError(f"slx_episode_warmup_cvs failed: ...")
engine.exceptions.SimulinkError: slx_episode_warmup_cvs failed: Warmup sim failed: <cp936 garbled>
Failed to close Simulink model kundur_cvs cleanly: <cp936 garbled "MATLAB has terminated">
```

### 1.3 Wall-clock + artefacts

- Smoke wall-clock: < 30 s (crashed before first ep step)
- `results/sim_kundur/runs/`: **no new run dir created** (latest is `kundur_simulink_20260417_160625/` from 2026-04-17, unrelated to this session). Train script crashed before `init_run_id` materialised.
- `results/cvs_smoke_*/`: not created.

---

## 2. Boundary check (post-ABORT, 12 files)

All §0 boundary files SHA-256 byte-equivalent to D-pre / G3-prep-C / D-config locks:

| File | SHA-256 | Status |
|---|---|---|
| `slx_helpers/vsg_bridge/slx_step_and_read.m` | `3175a5af…df5300` | ✅ verbatim |
| `slx_helpers/vsg_bridge/slx_episode_warmup.m` | `8ff0c8ed…7ed6a` | ✅ verbatim |
| `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m` | `d3f732e3…824e0` | ✅ verbatim |
| `slx_helpers/vsg_bridge/slx_episode_warmup_cvs.m` | `87efaa74…dcfb` | ✅ verbatim |
| `engine/simulink_bridge.py` | `aa348711…8b27d2` | ✅ post-C verbatim |
| `scenarios/kundur/model_profiles/kundur_cvs.json` | `ab89e82e…f869` | ✅ verbatim |
| `scenarios/kundur/kundur_ic_cvs.json` | `b5c3e786…0e34b` | ✅ verbatim |
| `scenarios/kundur/simulink_models/kundur_cvs.slx` | `224c294c…4447` | ✅ verbatim |
| `env/simulink/_base.py` | `542bbdb2…4d90` | ✅ verbatim |
| `env/simulink/ne39_simulink_env.py` | `ec2392c6…c56b` | ✅ verbatim |
| `scenarios/contract.py` | `77e67161…3c67` | ✅ verbatim |
| `scenarios/config_simulink_base.py` | `cb737a4b…a9625` | ✅ verbatim |

`scenarios/kundur/config_simulink.py` is at post-D-config SHA `534621b0…489dd0f0b` (committed in `4785cc9`). No additional file modified by smoke.

`git status --short` (CVS worktree, post-ABORT):

```
?? quality_reports/patches/                                   (audit, pre-existing)
?? results/sim_ne39/runs/ne39_simulink_20260425_194644/      (gitignored, D-pre)
?? results/sim_ne39/runs/ne39_simulink_20260425_204049/      (gitignored, post-C)
?? results/sim_ne39/runs/ne39_simulink_20260425_212223/      (gitignored, post-D-config)
```

**Tracked tree clean.** No NE39 / legacy / shared / `.m` / `.slx` / production `.py` mutated by the failed smoke.

---

## 3. Root-cause diagnosis (clean MCP repro, no production code touched)

### 3.1 Repro sequence (run via `mcp__simulink-tools__simulink_run_script`)

```matlab
evalin('base', 'clear all');                  % fresh ws (mimics fresh MATLAB session post-train-script-startup)
load_system('kundur_cvs');                    % mimics bridge.load_model() — DOES NOT rebuild
% Mimic _warmup_cvs assignin loop with LEGACY default templates
% (because KUNDUR_BRIDGE_CONFIG never set m_var_template / d_var_template):
for i = 1:4
  assignin('base', sprintf('M0_val_ES%d', i), 12.0);
  assignin('base', sprintf('D0_val_ES%d', i), 3.0);
  assignin('base', sprintf('Pm_%d', i), 0.5);
  assignin('base', sprintf('delta0_%d', i), 0.0);
  assignin('base', sprintf('Pm_step_t_%d', i), 5.0);
  assignin('base', sprintf('Pm_step_amp_%d', i), 0.0);
end
sim('kundur_cvs', 'StopTime', '0.5');
```

### 3.2 Captured English-clean error (8 causes, first 2 quoted)

```
MATLAB:MException:MultipleErrors  "多种原因导致错误"

cause[1]  Simulink:Parameters:BlkParamUndefined
   evaluating 'kundur_cvs/L_inf' parameter 'Inductance'
cause[2]  Simulink:Parameters:BlkParamUndefined
   evaluating 'kundur_cvs/L_tie' parameter 'Inductance'
cause[3]  Simulink:Parameters:BlkParamUndefined
   evaluating 'kundur_cvs/L_v_1' parameter 'Inductance'
cause[4]  Simulink:Parameters:BlkParamUndefined
   evaluating 'kundur_cvs/L_v_2' parameter 'Inductance'
cause[5]  Simulink:Parameters:BlkParamUndefined
   evaluating 'kundur_cvs/L_v_3' parameter 'Inductance'
cause[6]  Simulink:Parameters:BlkParamUndefined
   evaluating 'kundur_cvs/L_v_4' parameter 'Inductance'
cause[7]  Simulink:Parameters:BlkParamUndefined
   evaluating 'kundur_cvs/Load_A' parameter 'Resistance'
cause[8]  Simulink:Parameters:BlkParamUndefined
   evaluating 'kundur_cvs/Load_B' parameter 'Resistance'
```

### 3.3 Why these symbols are undefined in smoke but defined in probe

`build_kundur_cvs.m` writes the following to the base workspace **at build time** (per `_warmup_cvs.m` header comments lines 73-77):

```
Vmag_<i> (Volts), wn_const, Vbase_const, Sbase_const, Pe_scale,
L_v_H, L_tie_H, L_inf_H, R_loadA, R_loadB
```

These are read by:

| Block | Param | base-ws var | Source |
|---|---|---|---|
| `L_v_<i>`, `L_tie`, `L_inf` | `Inductance` | `L_v_H`, `L_tie_H`, `L_inf_H` | `build_kundur_cvs.m` line ~?? |
| `Load_A`, `Load_B` | `Resistance` | `R_loadA`, `R_loadB` | same |
| (other) | — | `Vbase_const`, `wn_const`, `Sbase_const`, `Pe_scale`, `Vmag_<i>` | same |

`_warmup_cvs` (engine/simulink_bridge.py line ~617-637) writes ONLY:
- `kundur_cvs_ip` struct (M0, D0, Pm0_pu, delta0_rad, Pm_step_t, Pm_step_amp, t_warmup) → handed as struct arg to `slx_episode_warmup_cvs.m`
- `tripload_state` vars from BridgeConfig
- whatever `slx_episode_warmup_cvs.m` then does internally (which itself writes per-VSG `Pm_<i>`, `delta0_<i>`, `Pm_step_t_<i>`, `Pm_step_amp_<i>`, plus `M0_val_ES<i>` / `D0_val_ES<i>` via legacy default templates)

**Build-time constants are NEVER re-pushed by `_warmup_cvs` or `slx_episode_warmup_cvs.m`.** The .slx itself does not embed them — they are inline references to base-ws variables.

`g3prep_C_cvs_dispatch_verify.py` (the probe) is `[Read]` clean to verify this:
- Line 138-142: probe explicitly calls `compute_kundur_cvs_powerflow()` + `build_kundur_cvs()` immediately before `bridge.warmup()` in the same MATLAB session
- Build pushes the constants → `bridge.warmup()` works
- `_warmup_cvs.m` header lines 73-77 explicitly state the design assumption: "build-time values are authoritative and bridge.warmup() must not depend on them being re-pushed every episode" — **valid only when build and runtime share the same MATLAB session**

The smoke goes through `train_simulink.py`, which does not run `build_kundur_cvs()` — it just calls `bridge.load_model()`. The MATLAB session is fresh (or at least has a workspace cleared by intervening Python work). Constants are missing → sim fail.

### 3.4 Second-order failure (would surface if 3.3 were fixed)

If the build constants were re-pushed by `_warmup_cvs` (or by some new pre-warmup step), the next `sim()` would fail with `Simulink:Parameters:BlkParamUndefined` on the `M_<i>` / `D_<i>` Constant blocks of each VSG swing-equation closure.

`kundur_cvs.slx` Constant blocks reference workspace symbols `M_<i>` and `D_<i>`. `slx_episode_warmup_cvs.m` writes `assignin('base', sprintf(strrep(cfg.m_var_template,'{idx}','%d'), idx), m_val)`. With `cfg.m_var_template = 'M0_val_ES{idx}'` (BridgeConfig default — `KUNDUR_BRIDGE_CONFIG` did not override), the assignin writes `M0_val_ES1..4` instead of `M_1..4`. Sim looks up `M_1` → undefined.

Field gaps in `KUNDUR_BRIDGE_CONFIG` (config_simulink.py L161-200):

| Field | BridgeConfig default | CVS needs | Currently set by config_simulink.py |
|---|---|---|---|
| `m_var_template` | `'M0_val_ES{idx}'` | `'M_{idx}'` | NO (inherits default) |
| `d_var_template` | `'D0_val_ES{idx}'` | `'D_{idx}'` | NO |
| `m0_default` | `12.0` | `24.0` | NO |
| `d0_default` | `3.0` | `18.0` | NO |
| `omega_signal` | (no default; required arg) | `'omega_ts_{idx}'` | YES — set to legacy `'omega_ES{idx}'` |
| `pe_path_template` | `''` | (CVS `.m` ignores; reads `Pe_ts_<i>` Timeseries instead) | set to legacy `'{model}/Pe_{idx}'` (harmless) |

The verify probe sets all 5 CVS-correct values directly (`g3prep_C_cvs_dispatch_verify.py` lines 103-117); `KUNDUR_BRIDGE_CONFIG` sets none.

### 3.5 Third-order: `pe_measurement='vi'` validator + `vabc_signal`

`config_simulink.py` L173-174 still sets `vabc_signal='Vabc_ES{idx}'` / `iabc_signal='Iabc_ES{idx}'` (legacy SPS naming). CVS `.m` files do NOT read these signals (per G3-prep-C verdict §1.1) so the smoke would not fail on this — the validator passes because the templates are non-empty. Recorded for completeness; does not block.

---

## 4. Why each prior verification missed this

| Verification | Result | What it actually checked | Why it didn't catch the smoke gap |
|---|---|---|---|
| Static dispatch (D-config §3) | PASS | Only `step_strategy` enum value | Did not import `train_simulink.py` flow or `_warmup_cvs`; checked field equality, not behavioural correctness |
| CVS route probe (D-config §4) | PASS | `bridge.warmup` end-to-end | Built `BridgeConfig` directly with all CVS fields; **also called `build_kundur_cvs()` in same session** |
| NE39 contamination tripwire (D-config §5) | PASS | NE39 path numerics | NE39 does not exercise CVS dispatch; orthogonal |

The verify probe + the design comment in `_warmup_cvs.m` lines 73-77 together form a coherent (but smoke-incomplete) story: "build writes the constants, warmup doesn't need to re-push them". This is true **within a session**; it breaks **across sessions**, which is the smoke's actual operating environment.

---

## 5. What this report does NOT do

- ❌ Modify any source file (`engine/simulink_bridge.py`, any `.m`, any `.slx`, any `.py` in `scenarios/`, `env/`, `agents/`)
- ❌ Re-attempt the smoke
- ❌ Rebuild `kundur_cvs.slx` or regenerate `kundur_ic_cvs.json` (probe-side rebuild artefacts already preserved as `quality_reports/patches/2026-04-25_*.patch` from D-config session)
- ❌ Touch any §0 boundary file
- ❌ Propose a specific fix or commit one
- ❌ Modify `BridgeConfig` interface
- ❌ Add new fields, new `.m` files, or new MATLAB code
- ❌ Authorise any subsequent run (Gate 3 / 50 ep / re-smoke)

---

## 6. Open decisions for user (not made by this report)

The fix surface for re-attempting smoke is at minimum 2-layered. Each layer is its own authorisation gate.

### OD-A — Where to re-push build-time constants every episode

| Path | Surface | Risk |
|---|---|---|
| **A1** Push in `_warmup_cvs` (engine/simulink_bridge.py) before sim | Python-side, ~10 lines, hard-coded constant values mirroring `build_kundur_cvs.m` | Couples bridge to model internals; constants change in build → sim drift |
| **A2** Push in `slx_episode_warmup_cvs.m` (NEW MATLAB code in existing CVS-only `.m`) | MATLAB-side, ~10 lines; either copy values from a sibling `.mat` file or hard-code | Same coupling concern |
| **A3** Make `build_kundur_cvs.m` write a sidecar `.mat`; `_warmup_cvs` loads it once per session | Adds artifact + filesystem dependency; cleanest | Touches build script (currently in CVS scope but recently committed) |
| **A4** Embed constants in `.slx` block dialogues directly (no base-ws ref) | Touches `.slx` (already committed at SHA `224c294c…`); changes the model | Largest blast radius |
| **A5** Re-run `build_kundur_cvs()` once at bridge init (one-time cost) | `_warmup_cvs` first call adds `compute_powerflow + build`; subsequent calls skip | Build wall-clock added to first ep; rebuild changes IC `.json` timestamp every session |

### OD-B — How to plumb CVS fields into `KUNDUR_BRIDGE_CONFIG`

| Path | Surface | Risk |
|---|---|---|
| **B1** Add CVS-vs-legacy conditionals to each affected field in `config_simulink.py` (similar to D-config edit, but for 4-5 fields, ~10-12 lines additive) | Smallest, follows D-config precedent | Pollutes config_simulink.py with profile-discriminator branches (5 of them) |
| **B2** Move CVS-specific fields into `kundur_cvs.json` profile + extend `model_profile.py` schema, then read them in config_simulink.py | Cleanest separation; requires schema + loader update | Wider blast radius (3 files vs 1) |
| **B3** Subclass / branch the entire `KUNDUR_BRIDGE_CONFIG` based on `KUNDUR_MODEL_PROFILE.model_name == 'kundur_cvs'` | Cleanest call site; biggest refactor | Largest delta |

### OD-C — Smoke failure ⇒ revert D-config?

D-config commit `4785cc9` is itself correct (CVS profile → `cvs_signal` dispatch is well-formed; the bridge-side dispatch path works in the verify probe). The reason smoke fails is **upstream of the D-config edit**: missing build constants + missing CVS field plumbing in BridgeConfig assembly. D-config is necessary even if neither OD-A nor OD-B is taken (without `step_strategy='cvs_signal'`, future smoke would silently misroute to `phang_feedback`).

| Choice | Effect |
|---|---|
| **C1** Keep `4785cc9` | D-config remains correct; smoke remains blocked until OD-A + OD-B are addressed |
| **C2** Revert `4785cc9` | Wipes a correct change; OD-A / OD-B still required separately; misleading history |

Recommendation (per usual ladder discipline): keep `4785cc9` (C1).

---

## 7. Status snapshot

```
HEAD:    4785cc9 feat(cvs-g3prep): plumb cvs_signal step_strategy in Kundur config (D-config)
Gate 1:  PASS  (commit 307952e)
Gate 2:  PASS  (commit 74428d7, D4-rev-B)
Gate 3:  LOCKED — RL/SAC entry not authorised
G3-prep-A: PASS, committed 4587f66
G3-prep-B: PASS, committed c97cabb
G3-prep-C: PASS, committed 90a0314
D-pre:    PASS, committed a12189e
D/E spec: PASS, committed 0b22f49 (smoke spec, OD-1 raised)
D-config: PASS, committed 4785cc9 (OD-1 partially resolved)
G3-prep-E (5-ep smoke): FAIL — this report
```

Smoke wall-clock: < 30 s, no `results/sim_kundur/runs/` dir created.
SAC gradient updates this run: 0 (crashed before any actor init).
NE39 path: not exercised this run; D-config tripwire already locked PASS at `4785cc9` (D-config verdict §5).
Boundary: clean (§2).

---

## 8. Reproduction (read-only diagnosis only)

To reproduce the captured English error:

```matlab
% In an MCP MATLAB shared session with kundur_cvs.slx on path:
evalin('base', 'clear all');
load_system('kundur_cvs');
for i = 1:4
  assignin('base', sprintf('M0_val_ES%d', i), 12.0);
  assignin('base', sprintf('D0_val_ES%d', i),  3.0);
  assignin('base', sprintf('Pm_%d', i), 0.5);
  assignin('base', sprintf('delta0_%d', i), 0.0);
  assignin('base', sprintf('Pm_step_t_%d', i), 5.0);
  assignin('base', sprintf('Pm_step_amp_%d', i), 0.0);
end
sim('kundur_cvs', 'StopTime', '0.5');
% Expected: Simulink:Parameters:BlkParamUndefined on 8 blocks
%           (L_inf, L_tie, L_v_1..4 / Inductance; Load_A, Load_B / Resistance)
```

Re-confirms the build-time constant gap. Does not touch source files.

---

## 9. Next step (gated on user)

| Choice | Effect |
|---|---|
| **Authorise OD-A + OD-B path selection** | User picks combination (e.g., A5 + B1 = "build once at init + 5 conditionals"); separate plan + commit + verification chain |
| **Re-spec smoke** | If OD-A path changes ep wall-clock or session model, spec §1.3 / §2 thresholds may need update |
| **Halt** | Gate 3 / SAC / RL remain LOCKED; smoke remains blocked; D-config remains committed; no further work |
| **Revert D-config** | Not recommended; D-config is independently correct (see OD-C / C1) |

Per session contract: no further code change, no smoke re-attempt, no Gate 3 entry until user explicitly authorises a specific OD-A + OD-B combination.
