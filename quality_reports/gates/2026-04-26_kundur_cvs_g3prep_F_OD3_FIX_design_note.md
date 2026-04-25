# G3-prep F OD-F-3 FIX — CVS Disturbance Path Design Note

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg` @ `a62c1e9`
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** DESIGN NOTE — short, before-implementation. **No code change yet. No 50-ep run.**
**Predecessors:**
- OD-F-3 verdict (H1.A confirmed) — `2026-04-26_kundur_cvs_g3prep_F_OD3_disturbance_reach_VERDICT.md` (commit `a62c1e9`)
- F instrumentation patch — commit `6d46c75`
- 50-ep observation spec — commit `1c328fc`

---

## TL;DR

The CVS .slx never reads `TripLoad?_P`; the existing `apply_disturbance` is a no-op for CVS (proved in OD-F-3 verdict). This note designs the **minimal** CVS-only re-route: `_apply_disturbance_backend` CVS branch writes the **already-wired-but-unused** `Pm_step_amp_<i>` and `Pm_step_t_<i>` workspace scalars per VSG. It is a **source-side ΔPm injection**, not a fake dynamic load. Legacy SPS path keeps its existing TripLoad behaviour bit-equivalent.

After implementation, three checks confirm reach:
1. **Static** — Python writes the same names CVS .slx Constant blocks actually reference.
2. **Differential** — perturbed-vs-default sim produces non-byte-identical ω trace.
3. **Sign-convention sanity** — small positive Pm step → ω rises; small negative → ω falls. Magnitudes finite, no NaN/Inf, no clip.

---

## 0. Strict scope

| Item | Status |
|---|---|
| `slx_helpers/vsg_bridge/*.m` (CVS + shared) | UNCHANGED |
| `kundur_cvs.slx` / `build_kundur_cvs.m` / `kundur_cvs_runtime.mat` / `kundur_ic_cvs.json` | UNCHANGED — Pm_step topology was wired at build time, no rebuild needed |
| NE39 (`scenarios/new_england/*`, `env/simulink/ne39_*.py`, `env/simulink/_base.py`, NE39 `.slx`) | UNCHANGED |
| legacy Kundur SPS path (`build_powerlib_kundur.m`, `build_kundur_sps.m`, `kundur_vsg.slx`, `kundur_vsg_sps.slx`, legacy `kundur_ic.json`, `compute_kundur_powerflow.m`) | UNCHANGED |
| `agents/`, root `config.py`, `scenarios/contract.py`, `scenarios/config_simulink_base.py` | UNCHANGED |
| reward / observation / action / SAC network / hyperparameters | UNCHANGED |
| `BridgeConfig` interface (no new field) | UNCHANGED |
| `KUNDUR_BRIDGE_CONFIG` field set (`config_simulink.py`) | UNCHANGED |
| `M0_default=24, D0_default=18, Pm0=0.5` | UNCHANGED |
| Disturbance range `[DIST_MIN, DIST_MAX]` (per `scenarios/config_simulink_base.py`) | UNCHANGED |
| `WARMUP_STEPS=2000`, reward weights, network | UNCHANGED |
| 50-ep / Gate 3 / 2000-ep | NOT INVOKED |

---

## 1. CVS Pm-step disturbance topology (already in .slx)

Per `build_kundur_cvs.m` L257-290, each of the 4 VSGs has a wired-in Pm-step injection chain:

```
Clock_global ─┐
              │
              ├─> GE_<i>  (>=)        ─> Cast_<i> (double) ─┐
Pm_step_t_<i> ┘                                              ├─> PmStepMul_<i> (Product)
Pm_step_amp_<i> ───────────────────────────────────────────  ┘             │
                                                                            │
Pm_<i>_c (Constant, value = Pm_<i>) ──> PmTotal_<i> (Sum '++') <────────────┘
                                            │
                                            ├──> swing_eq: dω/dt = (Pm_total - Pe - D·(ω-1)) / M
```

**Workspace scalars actually referenced by CVS Constant blocks:**

| Var | Block | Type | Default at build |
|---|---|---|---|
| `Pm_step_t_<i>` | `Pm_step_t_c_<i>` Constant | scalar (s) | 5.0 (per `build_kundur_cvs.m` L106) |
| `Pm_step_amp_<i>` | `Pm_step_amp_c_<i>` Constant | scalar (pu, sys-base 100 MVA) | 0.0 (per L107 — no perturbation) |

These are **per-VSG** (i = 1..4). Currently `_warmup_cvs` Phase 1 also writes them (per-ep init_params, with `Pm_step_t = 5.0`, `Pm_step_amp = 0.0` defaults). They are **never modified mid-episode**.

The OD-F-3 verdict already proved the CVS `.slx` Constants for these variables exist and are wired into the swing equation; what's missing is mid-episode `assignin` from `_apply_disturbance_backend`.

---

## 2. Sign convention (formal)

From the swing equation `dω/dt = (Pm_total - Pe - D·(ω-1)) / M`:

| Action | `Pm_step_amp_<i>` sign | `Pm_total = Pm + amp` | Net torque | Resulting ω |
|---|---|---|---|---|
| Pm injection (positive step) | **`> 0`** | rises | excess mechanical | **ω rises** (frequency goes up) |
| Pm withdrawal (negative step) | **`< 0`** | drops | excess electrical | **ω drops** (frequency goes down) |

**Mapping from env `magnitude` to per-VSG `Pm_step_amp_<i>`**:

The existing legacy SPS branch (`_apply_disturbance_backend` L724-727) treats `magnitude` as a **system-level** scalar in units of "100 MW chunks":
- `magnitude < 0`: reduce TripLoad1 by `|mag| × 100 MW`
- `magnitude > 0`: add TripLoad2 by `mag × 100 MW`

To preserve the **same physical magnitude semantics** for CVS (so DIST_MIN/DIST_MAX numbers don't need to change), map the system-level disturbance to a per-VSG share:

```
Pm_step_amp_<i> = magnitude × 100 MW / N_AGENTS / Sbase    [pu, sys-base]
                = magnitude × 100e6 / 4 / 100e6
                = magnitude × 0.25                          [pu]
```

For magnitude = 1.0 (legacy SPS = 100 MW total), each of 4 VSGs gets `+0.25 pu` Pm step → 1.0 pu total = 100 MW total injected → physically equivalent to legacy SPS load reduction of 100 MW. For magnitude = -1.0, each VSG gets `-0.25 pu` Pm withdrawal.

**Deviation from legacy SPS**: legacy injects via load (one bus); CVS injects via Pm (4 generators evenly). Net active power balance is identical at the system level. δ trajectories will differ from SPS at the inter-area mode level (because injection topology differs); ω **mean** trajectories should be comparable. This is recorded as an out-of-scope physics observation; not addressed by this fix.

**Pm_step_t_<i> = current sim time** so the step takes effect **immediately** at the moment `apply_disturbance` is called (env L380-381 calls it at `step == 2 → t = 0.5 s` post-warmup; the step indicator is `Clock_global >= Pm_step_t_<i>`, so setting `Pm_step_t_<i>` to the current sim time makes the indicator latch high from that point onward).

A tighter alternative would be to set `Pm_step_t_<i> = sim_time + dt_control` (next step boundary), but the existing legacy code applies disturbance at "t=0.5 s post-warmup" with no per-step alignment, so we match that convention. **Decision**: `Pm_step_t_<i> = bridge.t_current` (the current `sim_time` at the moment of `apply_disturbance`).

---

## 3. Implementation plan (minimal additive)

### 3.1 `engine/simulink_bridge.py` (additive helper, +~10 lines)

Add a new method `apply_workspace_var(var_name, value)` that does **only** `assignin('base', var, value)` — does NOT touch `_tripload_state` dict (which is reserved for the SPS TripLoad batch-write semantics in warmup).

```python
def apply_workspace_var(self, var_name: str, value: float) -> None:
    """Push a single workspace scalar to MATLAB base ws. CVS-friendly,
    does not pollute _tripload_state. For mid-episode disturbance vars
    (e.g. Pm_step_amp_<i>) that the .slx Constant blocks reference."""
    self.session.eval(
        f"assignin('base', '{var_name}', {float(value):.6g})", nargout=0
    )
```

**No interface change** to `BridgeConfig`. **No change** to existing `apply_disturbance_load` / `set_disturbance_load` methods. Pure additive method.

### 3.2 `env/simulink/kundur_simulink_env.py::_apply_disturbance_backend` (additive branch, +~15 lines)

Existing method (L713-746) has only the legacy SPS path. Add a CVS branch at the top, gated on `cfg.model_name == 'kundur_cvs'`:

```python
def _apply_disturbance_backend(
    self, bus_idx: Optional[int] = None, magnitude: float = 1.0
) -> None:
    cfg = self.bridge.cfg

    # CVS-only path: source-side Pm step (TripLoad vars are no-op for CVS,
    # confirmed by G3-prep-F OD-F-3 verdict).
    if cfg.model_name == 'kundur_cvs':
        amp_per_vsg_pu = magnitude * 100e6 / cfg.n_agents / cfg.sbase_va
        t_now = float(self.bridge.t_current)
        for i in range(1, cfg.n_agents + 1):
            self.bridge.apply_workspace_var(f'Pm_step_t_{i}',   t_now)
            self.bridge.apply_workspace_var(f'Pm_step_amp_{i}', amp_per_vsg_pu)
        sign = 'increase' if magnitude > 0 else 'decrease'
        print(
            f"[Kundur-Simulink-CVS] Pm step {sign}: "
            f"per-VSG amp={amp_per_vsg_pu:+.4f} pu (magnitude={magnitude:+.3f}), "
            f"step_time={t_now:.4f}s"
        )
        return

    # Legacy SPS path (UNCHANGED below this line)
    ...
```

The legacy SPS branch (L723-746) is **not modified** — preserved bit-equivalent for `kundur_vsg` / `kundur_vsg_sps` profiles.

### 3.3 What's NOT changed

- No `.m` files
- No `.slx` files (Pm_step topology already in CVS .slx since D4)
- No `kundur_cvs_runtime.mat` (sidecar holds only build-time scalars; per-VSG tunables remain `_warmup_cvs`'s job)
- No `BridgeConfig` field
- No `KUNDUR_BRIDGE_CONFIG` field set (`config_simulink.py`)
- No `kundur_simulink_env.py::apply_disturbance` (the public wrapper, L342)
- No `train_simulink.py` (the `apply_disturbance` call at L380-381 stays)
- No reward / agent / SAC / NE39 / legacy SPS

---

## 4. Verification chain (post-fix)

### 4.1 Static reach check (V-FIX-1)

Re-run an OD-F-3.a-style scan, but instead of `TripLoad?_P`, look for `Pm_step_amp_<i>` and `Pm_step_t_<i>` references in `kundur_cvs.slx`.

**Expected**: 4 references each (one per VSG). If 0, the fix has the wrong var name vs the .slx (defensive check).

### 4.2 Closed-loop differential sim (V-FIX-2)

Mimic the OD-F-3.b shape:
- **Run A** (control): default ws + sidecar + NR IC, `Pm_step_amp_<i> = 0` for all i, sim 2 s
- **Run B**: `Pm_step_amp_<i> = +0.05 pu` for all i (small positive perturbation), sim 2 s
- **Run C**: `Pm_step_amp_<i> = -0.05 pu` for all i (small negative perturbation), sim 2 s

**PASS condition**: `max|trace_B - trace_A| > 1e-6` AND `max|trace_C - trace_A| > 1e-6`. (Threshold 1e-6 is a generous "obviously not byte-identical" floor; we expect mHz-Hz responses for a 0.05 pu ≈ 5 MW per VSG step.)

### 4.3 Sign-convention sanity (V-FIX-3)

From V-FIX-2 traces:
- **Run B** (positive Pm step): `omega_1.Data[end] > 1.0` (ω rises, since Pm > Pe → mechanical excess)
- **Run C** (negative Pm step): `omega_1.Data[end] < 1.0` (ω falls)
- Both finite, no NaN, no Inf
- Both within `[0.7, 1.3]` (no hard clip touch — given small 0.05 pu step + D=18 damping)

If signs invert (Run B drops, Run C rises), the sum-block convention is opposite to what build script comment says — would require a `-1` flip in the env mapping, NOT a sign change in the .slx. Recorded as a fix-the-env-mapping case if it happens.

### 4.4 Boundary check (V-FIX-4)

Re-confirm 16 §0 boundary files SHA-256 byte-equivalent post-fix. Only `engine/simulink_bridge.py` and `env/simulink/kundur_simulink_env.py` should differ from current commit `a62c1e9`. Both are CVS-side / cross-cutting code; not in §0 strict-scope.

Wait — `env/simulink/_base.py` and `engine/simulink_bridge.py` are in §0 (per E A3+B1 verdict §2). The fix touches `engine/simulink_bridge.py` (additive) and `env/simulink/kundur_simulink_env.py` (additive CVS branch). Per CLAUDE.md commit-layering, these are scoped to "CVS disturbance reach fix" and explicitly authorised by user message. Updated boundary list for V-FIX-4:

| File | Expected | Reason |
|---|---|---|
| `slx_helpers/vsg_bridge/slx_step_and_read.m` | UNCHANGED | shared NE39+legacy |
| `slx_helpers/vsg_bridge/slx_episode_warmup.m` | UNCHANGED | shared NE39+legacy |
| `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m` | UNCHANGED | CVS .m, no signature change needed |
| `slx_helpers/vsg_bridge/slx_episode_warmup_cvs.m` | UNCHANGED | sidecar load already in place |
| `engine/simulink_bridge.py` | **CHANGED** (+~10 lines additive helper) | new `apply_workspace_var`; existing methods unchanged |
| `env/simulink/_base.py` | UNCHANGED | base env logic |
| `env/simulink/ne39_simulink_env.py` | UNCHANGED | NE39 isolation |
| `env/simulink/kundur_simulink_env.py` | **CHANGED** (+~15 lines additive CVS branch) | legacy SPS branch byte-equivalent |
| `scenarios/contract.py` | UNCHANGED | |
| `scenarios/config_simulink_base.py` | UNCHANGED | |
| `scenarios/new_england/*` | UNCHANGED | NE39 isolation |
| `scenarios/kundur/config_simulink.py` | UNCHANGED | |
| legacy Kundur (6 files) | UNCHANGED | |
| CVS .slx / .mat / IC.json / profile.json / build_kundur_cvs.m | UNCHANGED | model unchanged |
| `scenarios/kundur/train_simulink.py` | UNCHANGED | F instrumentation already in `6d46c75` |

### 4.5 What V-FIX does NOT do

- Does NOT run any 50-ep / Gate 3 / 2000-ep
- Does NOT measure SAC update behaviour (out of scope here)
- Does NOT tune disturbance magnitude / `[DIST_MIN, DIST_MAX]`
- Does NOT modify `physics_summary` schema
- Does NOT inject mid-episode in the 5-ep smoke (5-ep doesn't go through SAC; verification is via direct MCP probe at fixed amp, not via env.apply_disturbance)

---

## 5. Open decisions (gated on user)

| OD | Question | Default if silent |
|---|---|---|
| OD-FIX-1 | sign-convention scale (`magnitude × 100MW / N / Sbase = mag × 0.25 pu`) — keep as-is, or scale-down? | KEEP per §2 — preserves legacy semantics; allows small-mag (mag=0.1 → 0.025 pu/VSG) and large-mag (mag=3 → 0.75 pu/VSG) within sane band |
| OD-FIX-2 | `Pm_step_t_<i> = bridge.t_current` (immediate) vs `t_current + dt_control` (next step) | KEEP `t_current` per §2 — matches legacy SPS "fire on call" semantics |
| OD-FIX-3 | Use 4-equal-VSG amp (current §2) vs all-on-VSG-1 / random VSG | KEEP equal — closest to legacy SPS one-bus load (avoids inter-area mode bias) |
| OD-FIX-4 | Replace existing `apply_disturbance_load` with new helper, or add side-by-side | ADD — preserves legacy SPS path; minimal blast radius |
| OD-FIX-5 | Implement after this design note approval, or hold | per user: implement immediately; verify; halt before 50-ep |

This note halts here. Awaiting user authorisation to proceed to §3 implementation + §4 verification.
