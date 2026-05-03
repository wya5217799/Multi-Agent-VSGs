# G3-prep F OD-F-3 — Disturbance Reach MCP Probe Verdict

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg` @ `6d46c75`
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** PROBE VERDICT — read-only MCP investigation. **No code change.** Resolves OD-F-3 from 50-ep observation spec.
**Predecessors:**
- F-1.A + F-2.A instrumentation patch — `feat(cvs-g3prep-F)` (commit `6d46c75`)
- 50-ep observation spec — `2026-04-26_kundur_cvs_g3prep_F_50ep_observation_spec.md` (commit `1c328fc`)
- G3-prep-E A3+B1 + 5-ep smoke PASS — `2026-04-26_kundur_cvs_g3prep_E_AB_smoke_PASS.md` (commit `5db751a`)

---

## Verdict

| Outcome | Result |
|---|---|
| **Probe execution** | PASS — both sub-tests ran cleanly, conclusive evidence captured |
| **Hypothesis under test** | **H1.A CONFIRMED** — `apply_disturbance` does not reach the CVS .slx |
| **Operational consequence** | The 5-ep smoke `max_freq_dev_hz ≈ 6.5e-12 Hz` (display "0.00Hz") is a TRUE STABLE state under TWO concurrent reasons: (a) CVS NR IC is genuinely stable AND (b) the disturbance mechanism is a no-op for CVS. Both must be addressed before disturbance-driven learning can be claimed. |

This verdict resolves spec Dimension 1 (disturbance reach). **No code is changed by this report.** Recommended follow-up (out of scope, requires separate authorisation): replace the TripLoad-based disturbance with a CVS-native `Pm_step_amp_<i>` injection — this path already exists in `build_kundur_cvs.m` and `slx_episode_warmup_cvs.m` but is currently set to amplitude = 0.

---

## 0. Strict scope

| Item | Status |
|---|---|
| `engine/simulink_bridge.py` | UNCHANGED |
| `slx_helpers/vsg_bridge/*.m` (CVS + shared) | UNCHANGED |
| `scenarios/kundur/*` source | UNCHANGED |
| `env/simulink/kundur_simulink_env.py` | UNCHANGED |
| `kundur_cvs.slx`, `kundur_cvs_runtime.mat`, `kundur_ic_cvs.json` | UNCHANGED |
| NE39 / legacy / shared / agents / config / contract / reward / SAC | UNCHANGED |
| 50-ep / Gate 3 / 2000-ep | NOT RUN |

This probe is read-only on the codebase. It performs only `assignin`, `sim`, `find_system`, and `get_param` calls in the MATLAB shared session — no `set_param` writes, no .slx save, no .mat overwrite, no Python source edit.

---

## 1. Probe design

Two complementary tests against `kundur_cvs.slx`:

### 1.1 Test A — Static reference scan (OD-F-3.a)

**Question**: Do any blocks in `kundur_cvs.slx` reference the workspace variables `TripLoad1_P` or `TripLoad2_P` in any of their dialog parameters?

**Method**: `find_system('kundur_cvs', 'LookUnderMasks','all', 'FollowLinks','on', 'Type','block')` returns 278 blocks. For each block, enumerate `DialogParameters`, fetch each param value via `get_param`, test for substring match against the target var name. Repeat against `kundur_vsg_sps.slx` (legacy SPS, known to use TripLoad) as a positive control.

**Expected if H1.A**: 0 references in CVS; ≥1 in SPS legacy.

### 1.2 Test B — Closed-loop differential sim (OD-F-3.b)

**Question**: If we set `TripLoad1_P` or `TripLoad2_P` to wildly different values in the base workspace (e.g. 1 GW vs default), does the `kundur_cvs.slx` simulation produce a different `omega_ts_<i>` trajectory?

**Method**: 3 sequential 2-second sims of `kundur_cvs.slx` from identical NR IC (delta0_rad, M=24, D=18, Pm0=0.5, sidecar constants):
- **Run A** (control): default base ws (only sidecar + NR IC + per-VSG tunables, no `TripLoad?_P` set)
- **Run B**: assignin `TripLoad1_P = 1e9` (1 GW; vs legacy default 248 MW for SPS); rerun
- **Run C**: restore `TripLoad1_P = 248e6/3` (per-phase legacy default), then assignin `TripLoad2_P = 1e9`; rerun

Compare `omega_ts_1.Data` arrays element-wise. Threshold for "no effect": max |trace_X - trace_A| < 1e-12 (machine epsilon × dt).

**Expected if H1.A**: All three traces byte-identical → `max diff = 0.0`.

---

## 2. Evidence

### 2.1 Test A — Static reference scan

```
total blocks scanned = 278
TripLoad1_P: 0 block-param references in kundur_cvs.slx
TripLoad2_P: 0 block-param references in kundur_cvs.slx

---legacy comparison: kundur_vsg_sps.slx (positive control)---
legacy SPS TripLoad1_P: 1 block-param references
legacy SPS TripLoad2_P: 1 block-param references
```

CVS `.slx` literally has zero blocks that read `TripLoad1_P` or `TripLoad2_P`. Legacy SPS has exactly one each (the Three-Phase Dynamic Load blocks `TripLoad_1` / `TripLoad_2`, per `build_powerlib_kundur.m`). Positive control fires; CVS does not.

### 2.2 Test B — Closed-loop differential sim

```
Run A (default):              omega_1 final = 0.999999999019222
Run B (TripLoad1_P=1GW):      omega_1 final = 0.999999999019222
Run C (TripLoad2_P=1GW):      omega_1 final = 0.999999999019222
|B - A| = 0.000000e+00
|C - A| = 0.000000e+00
trace shape match: 402 samples
max|trace_B - trace_A| = 0.000000e+00
max|trace_C - trace_A| = 0.000000e+00
VERDICT: H1.A CONFIRMED — TripLoad1_P/TripLoad2_P do not affect CVS sim
```

402-sample omega trajectories are **byte-identical** across A / B / C. A 1 GW perturbation in either tripload var produces zero effect on the CVS sim — exactly what Test A's zero-reference result predicts.

---

## 3. Mechanism explanation

The disturbance write chain (Python side) is correctly wired and was never the failing link:

```
env.apply_disturbance(magnitude)            # kundur_simulink_env.py L342
  -> _apply_disturbance_backend(...)        # L713-746 (simulink override)
     -> bridge.apply_disturbance_load(var, value_w)  # bridge.py L683-697
        -> session.eval(f"assignin('base', '{var}', {value_w}}", ...)  # MATLAB base ws write
```

The Python-side `[Kundur-Simulink] Load reduction: TripLoad1_P=...MW` console messages observed in every 5-ep run **truly reflect** that `assignin` calls fire and the values land in base workspace. What's missing is the **Simulink-side consumer**:

- In legacy SPS path (`kundur_vsg_sps.slx`), the `TripLoad_1` / `TripLoad_2` Three-Phase Dynamic Load blocks reference these workspace vars in their `Active power P` parameter → assignin → set_param effect via `RunTimeObject` → live load magnitude during sim.
- In CVS path (`kundur_cvs.slx`), the loads are modelled as **fixed Series RLC Branch Resistance** blocks (`Load_A` / `Load_B`, see `build_kundur_cvs.m` L152 + L161) that reference scalars `R_loadA` / `R_loadB`. These scalars are loaded from the sidecar at episode warmup and **never re-written mid-episode**. The CVS .slx has no Dynamic Load block at all, no breaker Step block, and no workspace var that varies during a step.

The CVS .slx **does** have a wired-in disturbance path: per-VSG `Pm_step_t_<i>` / `Pm_step_amp_<i>` workspace scalars driving a step-time + step-amplitude Constant pair into each swing-equation's Pm input (`build_kundur_cvs.m` block instantiation, plus `slx_episode_warmup_cvs.m` Phase 1 init). Currently `Pm_step_amp_<i>` defaults to 0 → no perturbation. The `apply_disturbance` env override does not write to these vars.

---

## 4. Operational impact for the 50-ep observation spec

### 4.1 What this resolves

| Spec Dimension | OD-F-3 outcome |
|---|---|
| Dim 1 — Disturbance reach | **H1.A confirmed**. Python-side fires; CVS .slx does not consume. NO-OP for current configuration. |
| Dim 2 — physics_summary all-zero | **Re-confirmed as TRUE STABLE** (5-ep sanity already showed omega drift ~5e-14, r_f ~ -7.9e-24). The all-zero arises from CVS NR IC stiffness AND the no-op disturbance — two reinforcing causes. |

### 4.2 What this changes about the 50-ep run plan

The 50-ep observation smoke as currently spec'd would still succeed mechanically (sim runs to completion, SAC fires post-warmup at ep 40, schema reports correctly), but it would **not exercise the disturbance pathway** for CVS at all. Concretely:

- 50-ep run will show `max_freq_dev_hz ≈ 5e-12` for all 50 ep (same as 5-ep)
- `r_f` will be ~ -7.9e-24 for all 50 ep (action-independent under stable-omega)
- Reward gradient will come **entirely** from `r_h` + `r_d` action-magnitude penalties
- SAC post-warmup will learn to drive ΔH and ΔD towards 0 (minimise action magnitude only); no frequency-control signal is in the loss landscape

This is still useful as a **plumbing observation** (Dim 5 — SAC update fires; Dim 4 — reward decomposition is real and r_h/r_d dominate). But it is **not** a learning observation for any frequency-control policy claim.

### 4.3 Out-of-scope follow-up (recorded, NOT proposed by this report)

A future, separately-authorised step would need to choose how to inject disturbance into CVS. Three candidate paths exist (this report does not recommend among them):

| Path | Surface |
|---|---|
| Re-wire `kundur_simulink_env.py::_apply_disturbance_backend` so its CVS branch writes `Pm_step_t_<i>` / `Pm_step_amp_<i>` via `bridge.apply_disturbance_load` (already-wired CVS-side primitives) | env script + bridge unchanged |
| Replace `Load_A` / `Load_B` Series RLC Branch with a Dynamic Load that references a workspace scalar updatable mid-episode | `build_kundur_cvs.m` topology change |
| Add a separate disturbance-only block (e.g. ΔPm at the VSG terminal) | new build script content |

All three are blocked by user authorisation; none is touched here.

---

## 5. What this probe does NOT do

- Does NOT modify any source file (verified by §0 + §6 boundary check)
- Does NOT alter sim semantics (probe writes `assignin` to a workspace var that the CVS .slx demonstrably ignores; nothing else)
- Does NOT propose a fix for the disturbance reach gap
- Does NOT run the 50-ep observation smoke
- Does NOT enter Gate 3 / SAC training / 2000-ep
- Does NOT modify reward / agent / SAC / config / NE39 / legacy / shared

---

## 6. Boundary check

Tracked tree post-probe:

```
?? quality_reports/gates/2026-04-26_kundur_cvs_g3prep_F_OD3_disturbance_reach_VERDICT.md  (this file)
?? quality_reports/patches/                                                              (pre-existing)
?? results/sim_kundur/runs/...                                                           (gitignored)
?? results/sim_ne39/runs/...                                                             (gitignored)
```

No tracked file modified. The `kundur_cvs.slx` re-load triggered MATLAB to print `磁盘上包含模块图 'kundur_cvs' 的文件自加载后已更改` because the file's mtime on disk changed (from prior CVS rebuild step in another verification — not this probe); no save happened in this probe.

---

## 7. Status snapshot

```
HEAD:                6d46c75  feat(cvs-g3prep-F): F-1.A + F-2.A instrumentation
G3-prep-F spec:      PASS, committed 1c328fc
F instrumentation:   PASS, committed 6d46c75
OD-F-3 probe:        PASS — H1.A confirmed (this report)
50-ep observation:   NOT RUN, awaits user authorisation
Gate 3 / SAC / 2000-ep:  LOCKED
```

---

## 8. Next step (gated on user)

| Choice | Effect |
|---|---|
| **Authorise 50-ep observation smoke as-is** | runs ~14 min; will confirm Dim 5 (SAC update fires post ep 40) and quantify Dim 4 (r_h/r_d magnitudes over 50 ep); will NOT exercise disturbance (no-op per this verdict) |
| **Defer 50-ep until disturbance reach is fixed** | requires a separate ladder: pick one of §4.3 paths, plan + commit + 5-ep re-sanity + then 50-ep |
| **Commit this verdict only** | locks the OD-F-3 conclusion on disk; everything else stays deferred |
| **Hold** | no commit, no run |

Probe halts here. No further action without explicit user authorisation.
