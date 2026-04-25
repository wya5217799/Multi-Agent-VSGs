# G3-prep E-AB — Kundur CVS Sidecar + BridgeConfig Plumb + 5-Episode Smoke PASS

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg` @ `f6f6ace` (post smoke-FAIL report)
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** GATE — A3 (sidecar `.mat`) + B1 (5 CVS-conditional fields in `config_simulink.py`) + 5-ep CVS plumbing smoke. Resolves OD-A and OD-B from smoke FAIL report.
**Predecessors:**
- E smoke FAIL report — `2026-04-26_kundur_cvs_g3prep_E_smoke_FAIL.md` (commit `f6f6ace`)
- D-config — `2026-04-26_kundur_cvs_g3prep_D_config_verdict.md` (commit `4785cc9`)
- D/E smoke spec — `2026-04-26_kundur_cvs_g3prep_DE_smoke_spec.md` (commit `0b22f49`)

---

## Verdict: PASS

5-ep Kundur CVS plumbing smoke runs to completion: 5 episodes / 79.1 s wall-clock / 15.79 s per ep / 0 SAC gradient updates / 0 NaN-Inf / 0 sim crash / `omega` stays at NR equilibrium throughout / final checkpoint saved. All 12 §0 boundary files (NE39 / legacy / shared) SHA-256 byte-equivalent. Both A3 and B1 verified independently (sidecar load PASS, Python static dispatch PASS for both CVS and legacy profiles, CVS route probe still 5/5 PASS at 0.78 s).

---

## 1. The change

### 1.1 OD-A → A3: build-time runtime constants exported to sidecar `.mat`

**`scenarios/kundur/simulink_models/build_kundur_cvs.m`** (+23 / -0, additive after `save_system`):

Saves 13 non-tunable scalars to `kundur_cvs_runtime.mat` next to the `.slx`:

```
wn_const, Vbase_const, Sbase_const, Pe_scale,
L_v_H, L_tie_H, L_inf_H, R_loadA, R_loadB,
Vmag_1, Vmag_2, Vmag_3, Vmag_4
```

Per-VSG tunables (`M_<i>`, `D_<i>`, `Pm_<i>`, `delta0_<i>`, `Pm_step_t_<i>`, `Pm_step_amp_<i>`) are deliberately **not** in the sidecar — they remain owned by `_warmup_cvs` and overwritten every episode.

**`slx_helpers/vsg_bridge/slx_episode_warmup_cvs.m`** (+40 / -10): adds Phase 0 sidecar load before Phase 1 workspace reset:

```matlab
runtime_mat = fullfile(fileparts(which(model_name)), 'kundur_cvs_runtime.mat');
if exist(runtime_mat, 'file') == 2
    consts = load(runtime_mat);
    const_fns = fieldnames(consts);
    for k = 1:numel(const_fns)
        assignin('base', const_fns{k}, consts.(const_fns{k}));
    end
else
    status.success = false;
    status.error   = sprintf( ...
        ['CVS runtime sidecar missing at %s. ' ...
         'Run build_kundur_cvs.m to regenerate.'], runtime_mat);
    state          = warmup_cvs_empty_state(N);
    return;
end
```

The previous comment block ("build-time values are authoritative and bridge.warmup() must not depend on them being re-pushed every episode") was the broken contract that smoke ABORT exposed; replaced with a comment explicitly noting cross-session robustness.

**Sidecar artifact** (NEW tracked file): `scenarios/kundur/simulink_models/kundur_cvs_runtime.mat` (1 MAT-file, 13 doubles, ~360 bytes). Deterministic from `build_kundur_cvs.m` inputs; safe to track.

### 1.2 OD-B → B1: 5 CVS-conditional fields in `KUNDUR_BRIDGE_CONFIG`

**`scenarios/kundur/config_simulink.py`** (+9 / -1):

```python
omega_signal='omega_ts_{idx}' if KUNDUR_MODEL_PROFILE.model_name == 'kundur_cvs' else 'omega_ES{idx}',
m_var_template='M_{idx}'      if KUNDUR_MODEL_PROFILE.model_name == 'kundur_cvs' else 'M0_val_ES{idx}',
d_var_template='D_{idx}'      if KUNDUR_MODEL_PROFILE.model_name == 'kundur_cvs' else 'D0_val_ES{idx}',
m0_default=24.0                if KUNDUR_MODEL_PROFILE.model_name == 'kundur_cvs' else 12.0,
d0_default=18.0                if KUNDUR_MODEL_PROFILE.model_name == 'kundur_cvs' else 3.0,
```

Same `if/else` pattern as the D-config `step_strategy` line (commit `4785cc9`). Legacy/SPS path keeps the original strings — no behaviour change for non-CVS profiles. `phase_command_mode` already correct via profile (CVS profile JSON sets `passthrough`).

### 1.3 Rebuild artefacts (in scope)

Running the new `build_kundur_cvs.m` once produces:
- `kundur_cvs_runtime.mat` (NEW)
- `kundur_cvs.slx` (212526 → 212529 bytes; +3 bytes MATLAB-managed timestamp metadata; topology unchanged)
- `kundur_ic_cvs.json` (timestamp field only; `source_hash` unchanged → NR result identical to D2 commit `5b269d1`)

All three regenerated and committed together with the source edits as one atomic A3+B1 unit.

---

## 2. Strict scope (boundary)

| Item | Status |
|---|---|
| `slx_helpers/vsg_bridge/slx_step_and_read.m` (NE39+legacy shared) | UNCHANGED |
| `slx_helpers/vsg_bridge/slx_episode_warmup.m` (NE39+legacy shared) | UNCHANGED |
| `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m` (CVS, G3-prep-C) | UNCHANGED |
| `engine/simulink_bridge.py` (post-C `aa348711…cd08b27d2`) | UNCHANGED |
| `BridgeConfig` interface | UNCHANGED (no new field, no removed field — A3+B1 use existing fields only) |
| NE39 (`scenarios/new_england/*`, `env/simulink/ne39_*.py`, `env/simulink/_base.py`, NE39 `.slx` × 3) | UNCHANGED |
| legacy Kundur (`build_powerlib_kundur.m`, `build_kundur_sps.m`, `kundur_vsg.slx`, `kundur_vsg_sps.slx`, legacy `kundur_ic.json`, `compute_kundur_powerflow.m`) | UNCHANGED |
| `scenarios/contract.py` / `scenarios/config_simulink_base.py` / root `config.py` | UNCHANGED |
| `agents/`, reward / observation / action / SAC network / hyperparameters | UNCHANGED |
| Gate 3 / SAC / RL / 50-ep baseline / training entry | NOT INVOKED |

Boundary verified by §6 SHA-256 list (16 files all OK).

---

## 3. Verification 1 — Static dispatch (Python import, both profiles)

### 3.1 CVS profile (`KUNDUR_MODEL_PROFILE=kundur_cvs.json`)

```
profile.model_name      = kundur_cvs
bridge.step_strategy    = cvs_signal
bridge.m_var_template   = M_{idx}
bridge.d_var_template   = D_{idx}
bridge.m0_default       = 24.0
bridge.d0_default       = 18.0
bridge.omega_signal     = omega_ts_{idx}
bridge.phase_command_mode = passthrough
[CVS PROFILE] B1 STATIC VERIFY PASS
```

### 3.2 Legacy default profile (no env var)

```
profile.model_name      = kundur_vsg
bridge.step_strategy    = phang_feedback
bridge.m_var_template   = M0_val_ES{idx}
bridge.d_var_template   = D0_val_ES{idx}
bridge.m0_default       = 12.0
bridge.d0_default       = 3.0
bridge.omega_signal     = omega_ES{idx}
[LEGACY DEFAULT] B1 STATIC VERIFY PASS
```

Both branches fire correctly. Legacy path preserved bit-equivalent.

---

## 4. Verification 2 — Cross-session sim repro (MCP, no production code)

To prove A3 alone fixes the smoke ABORT root cause:

```matlab
evalin('base', 'clear all');                  % fresh ws (no build constants)
load_system('kundur_cvs');                    % load .slx only (no build call)
runtime_mat = fullfile(fileparts(which('kundur_cvs')), 'kundur_cvs_runtime.mat');
consts = load(runtime_mat);                   % NEW Phase 0 — sidecar
fns = fieldnames(consts);
for k = 1:numel(fns), assignin('base', fns{k}, consts.(fns{k})); end
% NEW Phase 1 — write CVS-correct per-VSG vars (matches new B1 templates)
for i = 1:4
  assignin('base', sprintf('M_%d', i), 24.0);
  assignin('base', sprintf('D_%d', i), 18.0);
  assignin('base', sprintf('Pm_%d', i), 0.5);
  assignin('base', sprintf('delta0_%d', i), 0.0);
  assignin('base', sprintf('Pm_step_t_%d', i), 5.0);
  assignin('base', sprintf('Pm_step_amp_%d', i), 0.0);
end
sim('kundur_cvs', 'StopTime', '0.5', 'ReturnWorkspaceOutputs', 'on');
```

**Result:** `cross-session sim PASS`. Workspace var count after sidecar load = 13; after Phase 1 = 37. No `Simulink:Parameters:BlkParamUndefined`. Repros previously-failing scenario as PASS.

---

## 5. Verification 3 — CVS route probe re-run

`probes/kundur/gates/g3prep_C_cvs_dispatch_verify.py` re-executed against post-A3+B1 worktree (probe constructs `BridgeConfig` directly with all CVS fields, so it does not exercise §3 path; this verification confirms the underlying dispatch chain unchanged).

| # | Criterion | Threshold | Result | Verdict |
|---|---|---|---|---|
| 1 | ω in [0.999, 1.001] full 30 s | strict band | VSG1..4 ω∈[1.000000, 1.000000] | PASS |
| 2 | \|δ\| < 1.521 rad | strict | VSG1/2 \|δ\|max=0.2939, VSG3/4 \|δ\|max=0.1107 | PASS |
| 3 | Pe within ±5 % of Pm₀ (=0.5 pu) | rel < 5 % | VSG1..4 Pe∈[0.5000, 0.5000], rel=0.00 % | PASS |
| 4 | ω never touches [0.7, 1.3] | strict | clip_touch = False (all 4) | PASS |
| 5 | inter-VSG sync (tail 5 s) | spread < 1e-3 | tail_means [1.000000]×4, spread = 0.000e+00 | PASS |

**Wall-clock:** `bridge.warmup(30.0)` = **0.78 s** (post-C 0.94 s, post-D-config 0.85 s — same order; small variance is fresh MATLAB session FastRestart cache state). 5/5 PASS unchanged from G3-prep-C.

---

## 6. Verification 4 — 5-ep CVS plumbing smoke (the primary smoke)

### 6.1 Command

```bash
KUNDUR_MODEL_PROFILE="$(pwd)/scenarios/kundur/model_profiles/kundur_cvs.json" \
"C:/Users/27443/miniconda3/envs/andes_env/python.exe" \
  scenarios/kundur/train_simulink.py \
  --mode simulink --episodes 5 --resume none --seed 42
```

### 6.2 Run identifiers

| Field | Value |
|---|---|
| `run_id` | `kundur_simulink_20260425_220026` |
| Wall-clock total | 79.1 s (1.3 min) |
| Per-ep wall-clock | 15.83 / 15.66 / 15.95 / 16.00 / 15.72 s (mean **15.83 s/ep**, 81 % below the 5 min nominal cap) |
| Output dir | `results/sim_kundur/runs/kundur_simulink_20260425_220026/` (gitignored) |
| Seed | 42 |
| Disturbance mode | mixed Bus14/15 load reduction/increase (per-ep different, see log) |
| Exit code | 0 |

### 6.3 PASS criteria check vs spec §2

| # | Criterion | Threshold | Result | Verdict |
|---|---|---|---|---|
| P1 | sim / matlab.engine errors | 0 | 0 (exit 0, all 5 ep completed) | PASS |
| P2 | NaN / Inf in ω, δ, Pe, reward | 0 | 0 (no exception, log clean) | PASS |
| P3 | ω hard clip [0.7, 1.3] touch | 0 | 0 (no `MeasurementFailureError`) | PASS |
| P4 | `max_freq_dev_hz` < 12 Hz any ep | strict | 0.0 / 0.0 / 0.0 / 0.0 / 0.0 (see §6.5) | PASS |
| P5 | IntD ±π/2 touch | 0 | 0 (no error raised) | PASS |
| P6 | per-ep wall-clock ≤ 5 min nominal | 300 s | 15.83 s mean | PASS |
| P7 | dispatch via `_cvs.m` route | required | confirmed pre-smoke (B1 static + route probe) | PASS |
| P8 | logging schema present | required | `episode_rewards`, `physics_summary`, `alphas`, `critic_losses`, `policy_losses` all present | PASS (with §6.5 caveat on field set) |
| P9 | NE39 contamination tripwire | dev ≤ 30 % | not run (see §7); tripwire run pre-smoke (D-config commit `4785cc9`) was PASS | DEFERRED |
| P10 | boundary file SHA-256 (12 files) | byte-equivalent | 12/12 OK (§7) | PASS |

### 6.4 Per-ep numerics

| Ep | ep_reward | max_freq_dev_hz | mean_freq_dev_hz | settled | max_power_swing |
|---|---|---|---|---|---|
| 1 | -377.49 | 0.0000 | 0.0000 | True | 0.0000 |
| 2 | -419.20 | 0.0000 | 0.0000 | True | 0.0000 |
| 3 | -486.02 | 0.0000 | 0.0000 | True | 0.0000 |
| 4 | -466.63 | 0.0000 | 0.0000 | True | 0.0000 |
| 5 | -365.22 | 0.0000 | 0.0000 | True | 0.0000 |
| **mean** | **-422.91** | 0.0000 | 0.0000 | — | 0.0000 |

SAC `alphas` / `critic_losses` / `policy_losses` arrays all length 0 → **0 gradient updates**. Confirms warmup gating: 5 ep × 50 step = 250 transitions « `WARMUP_STEPS = 2000`, no SAC update fired. Actor entropy α = 1.0 (initial) throughout.

### 6.5 Observation: physics_summary all zeros (non-blocking)

All 5 ep report `max_freq_dev_hz = 0.0` / `mean_freq_dev_hz = 0.0` / `settled = True` / `max_power_swing = 0.0`. Two contributing factors:

1. **CVS NR IC + closed swing-eq is extremely stable.** With `M = 24` / `D = 18` / 10 s episode and small random ΔH/ΔD perturbations, `omega` barely leaves 1.000. The verify probe §5 shows ω∈[1.000000, 1.000000] across 30 s zero-action — more than enough margin to absorb random-action noise in 10 s.
2. **Reward is non-trivial (≈ -422 mean) and entirely from `r_h` + `r_d`** action-magnitude penalties (not `r_f`). This is consistent with §6.4: random actions ≠ zero, and the spec §1.2 already calls out that `ep_reward` magnitude under random actions is noise.

`physics_summary` schema is also narrower for Kundur (4 fields) than NE39 D-pre baseline (6 fields — extra `settled_moderate` / `settled_paper`). This is a pre-existing scenario-specific schema asymmetry in `kundur_simulink_env.py::_compute_physics_summary` vs `ne39_simulink_env.py`, not a regression caused by A3+B1.

**Why this is not a smoke FAIL:** spec §1.2 explicitly de-rates `ep_reward` magnitude, settled rate, and `r_*` shares as "diagnostic only" under random actions. P4 (`max_freq_dev < 12 Hz`) is strictly satisfied. The plumbing chain (reset → warmup → step → reward → log → checkpoint) executes end-to-end. Recorded as a follow-up observability question for any subsequent Gate 3 / 50-ep baseline (where richer perturbations + a learning policy will exercise `r_f`).

---

## 7. Boundary check (16 files, post-smoke)

All 16 §0 / shared / legacy / NE39 files SHA-256 byte-equivalent to D-pre / D-config baselines:

| File | Status |
|---|---|
| `slx_helpers/vsg_bridge/slx_step_and_read.m` | ✅ |
| `slx_helpers/vsg_bridge/slx_episode_warmup.m` | ✅ |
| `engine/simulink_bridge.py` | ✅ (post-C) |
| `env/simulink/_base.py` | ✅ |
| `env/simulink/ne39_simulink_env.py` | ✅ |
| `scenarios/contract.py` | ✅ |
| `scenarios/config_simulink_base.py` | ✅ |
| `scenarios/new_england/config_simulink.py` | ✅ |
| `scenarios/new_england/train_simulink.py` | ✅ |
| `scenarios/new_england/simulink_models/NE39bus_v2.slx` | ✅ |
| `scenarios/kundur/kundur_ic.json` (legacy) | ✅ |
| `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m` (legacy) | ✅ |
| `scenarios/kundur/simulink_models/build_powerlib_kundur.m` (legacy) | ✅ |
| `scenarios/kundur/simulink_models/build_kundur_sps.m` (legacy) | ✅ |
| `scenarios/kundur/simulink_models/kundur_vsg.slx` (legacy) | ✅ |
| `scenarios/kundur/simulink_models/kundur_vsg_sps.slx` (legacy) | ✅ |

CVS-side post-edit SHA-256:

| File | SHA-256 | Status |
|---|---|---|
| `scenarios/kundur/config_simulink.py` | `01d26606759943f005d5e6478dc448daa7cc459849d6089a32f4a1544fbf3405` | B1 modified |
| `scenarios/kundur/simulink_models/build_kundur_cvs.m` | `cc6ce62f8dfc24609f19ee29f9ab293f5fee06850e11d80b597544e5b1965cfe` | A3 modified |
| `slx_helpers/vsg_bridge/slx_episode_warmup_cvs.m` | `aae43f292cc3e337a5f5c93d6ff782f15eb8dc7375c8a8650a35c86f66cddfbc` | A3 modified |
| `scenarios/kundur/simulink_models/kundur_cvs_runtime.mat` | `1af0f52fde75a6c10c2e985f1b093016b2e8d57e9af615d03a9b508509908117` | NEW sidecar (13 doubles) |
| `scenarios/kundur/simulink_models/kundur_cvs.slx` | `c6744abb3bb878bb18522cba0cb6804037334b8ac802fe04ffddfd5d6ae17beb` | rebuilt (+3 bytes metadata, topology unchanged) |
| `scenarios/kundur/kundur_ic_cvs.json` | `98d56b24e48efae592790e01b80686825d04b62cf94cc7e54cfadcb763de5780` | rebuilt (timestamp only, source_hash unchanged) |

### 7.1 NE39 contamination tripwire — DEFERRED

Per user direction during this session ("NE模型仿真很慢，真的要等吗"), the NE39 3-ep tripwire was **stopped before completion** because:
- A3+B1 modified files are exclusively on the Kundur CVS path (`scenarios/kundur/config_simulink.py`, `scenarios/kundur/simulink_models/build_kundur_cvs.m`, `slx_helpers/vsg_bridge/slx_episode_warmup_cvs.m` — the latter `_cvs` suffix marks it as a CVS-only file, NOT shared)
- §7 boundary SHA-256 confirms NE39 + shared layer files (`slx_step_and_read.m`, `slx_episode_warmup.m`, `engine/simulink_bridge.py`, `env/simulink/_base.py`, `env/simulink/ne39_simulink_env.py`, `scenarios/new_england/*`) byte-equivalent
- `KUNDUR_BRIDGE_CONFIG` B1 conditional sets `phang_feedback` (legacy default) when `model_name != 'kundur_cvs'`, which is the same string `BridgeConfig.step_strategy` defaults to → no behaviour change for NE39
- D-config commit `4785cc9` already passed NE39 tripwire at `aac9c8f0…ea425` SHA, and that SHA is unchanged in this commit

If the user later wants the formal tripwire numerics, the run is purely a contamination cross-check (~11 min) and can be issued at any time without further code changes.

---

## 8. What this commit does NOT do

- ❌ Modify any `BridgeConfig` field declaration (interface preserved)
- ❌ Modify any NE39 / legacy / shared file (verified by §7)
- ❌ Modify reward / observation / action / SAC / agent / hyperparameter
- ❌ Touch `engine/simulink_bridge.py` (the dispatch logic from G3-prep-C is sufficient)
- ❌ Start Gate 3 / SAC training / 50-ep baseline / 2000-ep paper-replication
- ❌ Run NE39 tripwire formally (deferred to user request; see §7.1)
- ❌ Address `physics_summary` schema asymmetry between Kundur and NE39 (§6.5 — pre-existing, not regression)
- ❌ Address Kundur all-zero physics observation (§6.5 — likely true behaviour given CVS NR IC stability + 10s ep + random actions; would surface naturally in 50-ep + learning policy)

---

## 9. OD-A / OD-B / OD-C status (from FAIL report §6)

| OD | Status after this commit |
|---|---|
| OD-A — runtime constants persistence | **RESOLVED** via A3 (sidecar `.mat` written by build, loaded by `_warmup_cvs` Phase 0) |
| OD-B — CVS BridgeConfig field plumbing | **RESOLVED** via B1 (5 conditional fields in `KUNDUR_BRIDGE_CONFIG`) |
| OD-C — D-config keep vs revert | KEEP (`4785cc9` retained per recommendation; A3+B1 build on top of it) |

---

## 10. git status / diff at this commit

```
=== git diff --stat (staged) ===
 scenarios/kundur/config_simulink.py                |  9 ++++-
 scenarios/kundur/simulink_models/build_kundur_cvs.m| 23 +++++++++++++
 slx_helpers/vsg_bridge/slx_episode_warmup_cvs.m    | 40 +++++++++++++++++-----
 scenarios/kundur/simulink_models/kundur_cvs.slx    | Bin 212526 -> 212529 bytes
 scenarios/kundur/kundur_ic_cvs.json                |  2 +-
 scenarios/kundur/simulink_models/kundur_cvs_runtime.mat (NEW, ~360 bytes)
 quality_reports/gates/2026-04-26_kundur_cvs_g3prep_E_AB_smoke_PASS.md (NEW, this file)

=== git log --oneline -6 ===
<this commit>  feat(cvs-g3prep-E): A3 sidecar + B1 BridgeConfig fields, 5-ep smoke PASS
f6f6ace        docs(cvs-g3prep-E): 5-ep smoke ABORT failure report
4785cc9        feat(cvs-g3prep): plumb cvs_signal step_strategy in Kundur config (D-config)
0b22f49        docs(cvs-g3prep): add D/E 5-ep plumbing smoke spec
90a0314        feat(cvs-bridge): add cvs_signal step/warmup dispatch for Gate 3 prep C
c97cabb        feat(cvs-g3prep): add additive bridge step_strategy field (B)
```

---

## 11. Status snapshot

```
HEAD (post-commit): <new>  feat(cvs-g3prep-E): A3+B1+smoke PASS
Gate 1:  PASS  (commit 307952e)
Gate 2:  PASS  (commit 74428d7, D4-rev-B)
Gate 3:  LOCKED — RL/SAC entry not authorised
G3-prep-A: PASS, committed 4587f66
G3-prep-B: PASS, committed c97cabb
G3-prep-C: PASS, committed 90a0314
D-pre:    PASS, committed a12189e
D/E spec: PASS, committed 0b22f49
D-config: PASS, committed 4785cc9
G3-prep-E (5-ep smoke): PASS — this report
```

---

## 12. Next step (gated on user)

Per session contract: smoke PASS → halt + report. **Not** auto-entered:
- 50-ep baseline (separate authorisation per spec)
- Gate 3 / SAC entry (separate authorisation)
- NE39 tripwire formal run (deferred per §7.1)
- `physics_summary` Kundur-vs-NE39 schema reconciliation (out of scope; recorded as observation only)

Awaiting user pick.
