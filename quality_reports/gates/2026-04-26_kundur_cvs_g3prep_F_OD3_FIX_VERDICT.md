# G3-prep F OD-F-3 FIX — CVS Pm-Step Disturbance Verdict

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg` @ `710aa3f`
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** GATE — minimal additive `engine/simulink_bridge.py` + `env/simulink/kundur_simulink_env.py` patches resolving the disturbance-reach gap exposed by OD-F-3 (commit `a62c1e9`).
**Predecessors:**
- OD-F-3 FIX design note — commit `710aa3f`
- OD-F-3 verdict (H1.A confirmed) — commit `a62c1e9`
- F instrumentation — commit `6d46c75`
- 50-ep observation spec — commit `1c328fc`

---

## Verdict: PASS

All 4 verification checks PASS. CVS path now actually receives mid-episode disturbance via the per-VSG `Pm_step_amp_<i>` / `Pm_step_t_<i>` workspace scalars (already wired in `kundur_cvs.slx` since D4). Sign convention matches the design note (positive amp → ω rises, negative amp → ω falls). Legacy SPS / NE39 / shared `.m` paths are byte-identical.

---

## 1. Implementation summary (per design note §3)

### 1.1 `engine/simulink_bridge.py` (+17 lines additive)

New method `apply_workspace_var(var_name, value)` placed after `apply_disturbance_load`. Pure `assignin` to MATLAB base workspace; does not touch `_tripload_state` (which is reserved for SPS TripLoad batch-write semantics in warmup).

```python
def apply_workspace_var(self, var_name: str, value: float) -> None:
    self.session.eval(
        f"assignin('base', '{var_name}', {float(value):.6g})", nargout=0
    )
```

### 1.2 `env/simulink/kundur_simulink_env.py` (+20 lines additive)

CVS branch added at top of `_apply_disturbance_backend`, gated on `cfg.model_name == 'kundur_cvs'`:

```python
if cfg.model_name == 'kundur_cvs':
    amp_per_vsg_pu = float(magnitude) * 100e6 / cfg.n_agents / cfg.sbase_va
    t_now = float(self.bridge.t_current)
    for i in range(1, cfg.n_agents + 1):
        self.bridge.apply_workspace_var(f'Pm_step_t_{i}',   t_now)
        self.bridge.apply_workspace_var(f'Pm_step_amp_{i}', amp_per_vsg_pu)
    sign = 'increase' if magnitude > 0 else 'decrease'
    print(
        f"[Kundur-Simulink-CVS] Pm step {sign}: per-VSG amp="
        f"{amp_per_vsg_pu:+.4f} pu (magnitude={float(magnitude):+.3f}), "
        f"step_time={t_now:.4f}s"
    )
    return

# Legacy SPS path (UNCHANGED below this line)
delta_per_phase_w = abs(float(magnitude)) * cfg.sbase_va / 3.0
if magnitude < 0:
    ...
```

Mapping per design note §2: `magnitude × 100 MW / N_AGENTS / Sbase = magnitude × 0.25 pu` per VSG. Sign passes through (positive magnitude → positive Pm step → ω rises).

### 1.3 What's NOT changed

- No `.m` files (Pm_step topology pre-wired in `kundur_cvs.slx` since D4)
- No `.slx` files
- No `kundur_cvs_runtime.mat` (sidecar holds only build-time scalars)
- No `BridgeConfig` field
- No `KUNDUR_BRIDGE_CONFIG` field set
- No `train_simulink.py` / agents / SAC / reward / NE39 / legacy SPS / shared
- No disturbance range `[DIST_MIN, DIST_MAX]` change
- No `physics_summary` schema change

---

## 2. Verification chain results

### 2.1 V-FIX-1 — Static reach scan (PASS)

`find_system` over 278 blocks in `kundur_cvs.slx` for the 8 target workspace vars:

```
Pm_step_amp_1: 1 ref  [kundur_cvs/Pm_step_amp_c_1]
Pm_step_amp_2: 1 ref  [kundur_cvs/Pm_step_amp_c_2]
Pm_step_amp_3: 1 ref  [kundur_cvs/Pm_step_amp_c_3]
Pm_step_amp_4: 1 ref  [kundur_cvs/Pm_step_amp_c_4]
Pm_step_t_1:   1 ref  [kundur_cvs/Pm_step_t_c_1]
Pm_step_t_2:   1 ref  [kundur_cvs/Pm_step_t_c_2]
Pm_step_t_3:   1 ref  [kundur_cvs/Pm_step_t_c_3]
Pm_step_t_4:   1 ref  [kundur_cvs/Pm_step_t_c_4]
total = 8 (expected 8)
```

8 Constant blocks, 1 reference each. Names match exactly what the new env code writes via `assignin`.

### 2.2 V-FIX-2 — Closed-loop differential sim (PASS)

3 × 2-second sims from identical NR IC (delta0_rad=[0.2939, 0.2939, 0.1107, 0.1107], M=24, D=18, Pm0=0.5):

| Run | Setting | omega_1 final | trace samples |
|---|---|---|---|
| A (control) | `Pm_step_amp = 0`, `Pm_step_t = 5.0` | 0.999999999 | 402 |
| B (positive) | `Pm_step_amp = +0.05 pu`, `Pm_step_t = 0.0` | **1.000297** | 403 |
| C (negative) | `Pm_step_amp = -0.05 pu`, `Pm_step_t = 0.0` | **0.999703** | 403 |

Common-range comparison (truncated to n=402):

| Metric | Value | Threshold | Verdict |
|---|---|---|---|
| `max\|trace_B - trace_A\|` | 5.246e-4 | > 1e-6 | PASS (~525× margin) |
| `max\|trace_C - trace_A\|` | 5.231e-4 | > 1e-6 | PASS (~523× margin) |
| `\|end_B - end_A\|` | 2.972e-4 | > 1e-6 | PASS |
| `\|end_C - end_A\|` | 2.973e-4 | > 1e-6 | PASS |

Trace-length difference (402 vs 403) by itself is also evidence of non-trivial response: variable-step solver took different sample counts because the perturbation altered the dynamics — exactly opposite of OD-F-3.b where TripLoad perturbation gave byte-identical 402-sample traces.

### 2.3 V-FIX-3 — Sign-convention sanity (PASS)

| Run | Pm_step_amp | omega_1 final | min(omega_1) | max(omega_1) | finite | clip touch |
|---|---|---|---|---|---|---|
| B | +0.05 pu | 1.000297 | 0.999624 | 1.000525 | yes | no (\|delta\| < 0.0006) |
| C | -0.05 pu | 0.999703 | 0.999477 | 1.000378 | yes | no |

- **Run B** (positive amp): final ω > 1 ✅ (rises as predicted by `Pm_total = Pm + amp` with amp>0 → mechanical excess)
- **Run C** (negative amp): final ω < 1 ✅ (falls as predicted)
- Both finite, no NaN/Inf, neither touches `[0.7, 1.3]` clip
- Symmetric magnitude (B 2.97e-4 above 1, C 2.97e-4 below 1) confirms linearity in this small-perturbation regime

Sign convention exactly matches design note §2.

### 2.4 V-FIX-4 — Boundary check (PASS)

22 source files SHA-256 byte-equivalent to commit `710aa3f`:

| Group | Files | Status |
|---|---|---|
| NE39+legacy shared `.m` | `slx_step_and_read.m`, `slx_episode_warmup.m` | UNCHANGED |
| CVS `.m` (G3-prep-C / E) | `slx_step_and_read_cvs.m`, `slx_episode_warmup_cvs.m` | UNCHANGED |
| `env/simulink/_base.py` | shared base | UNCHANGED |
| NE39 path | `ne39_simulink_env.py`, `new_england/*`, `NE39bus_v2.slx` | UNCHANGED |
| Cross-cutting | `scenarios/contract.py`, `config_simulink_base.py` | UNCHANGED |
| legacy Kundur (6 files) | `kundur_ic.json`, `compute_powerflow.m`, `build_powerlib.m`, `build_kundur_sps.m`, `kundur_vsg.slx`, `kundur_vsg_sps.slx` | UNCHANGED |
| CVS model | `build_kundur_cvs.m`, `kundur_cvs.slx`, `kundur_ic_cvs.json`, `kundur_cvs_runtime.mat`, `kundur_cvs.json` profile | UNCHANGED |
| `scenarios/kundur/config_simulink.py` | post-E-AB at `01d26606…` | UNCHANGED (committed in `5db751a`) |

Two expected changes (per design note §3):

| File | Pre-fix SHA | Post-fix SHA | Lines |
|---|---|---|---|
| `engine/simulink_bridge.py` | `aa348711…cd08b27d2` | `c8eef07e6913b0984c194bf85894bb718f7bea88e40c2b80658fe3ee00003bc7` | +17 / -0 |
| `env/simulink/kundur_simulink_env.py` | (committed prior baseline) | `2462b1c3fe1a3d93d817f6640107fdae3dc717cdcdf157fbee84b00f518caf04` | +20 / -0 |

Both pure additive; no existing line removed; no method signature change; no behaviour change for `model_name != 'kundur_cvs'`.

---

## 3. What this fix does NOT do

- Does NOT enter Gate 3 / SAC training / 50-ep / 2000-ep
- Does NOT modify reward / observation / action / SAC / agent / hyperparameter
- Does NOT change disturbance magnitude range (`[DIST_MIN, DIST_MAX]` per `scenarios/config_simulink_base.py`)
- Does NOT change `physics_summary` schema
- Does NOT modify NE39 / legacy SPS / shared `.m` / agents / config / contract
- Does NOT modify `BridgeConfig` interface
- Does NOT touch `kundur_cvs.slx` / `kundur_cvs_runtime.mat` / sidecar
- Does NOT run any Python smoke (the OD-FIX scope is reach verification only; further runs need new authorisation)

---

## 4. Operational consequences

After this fix, the next 5-ep / 50-ep CVS run via `train_simulink.py` will exhibit:
- Mid-episode (at `step == 2`, t = 0.5 s post-warmup): per-VSG Pm step injection of `magnitude × 0.25 pu` into the swing equation
- Console line changes from `[Kundur-Simulink] Load reduction: TripLoad1_P=…MW total` to `[Kundur-Simulink-CVS] Pm step decrease: per-VSG amp=±0.XXXX pu (magnitude=±X.XXX), step_time=…s`
- Non-trivial ω response: per V-FIX-2, |ω - 1.0| of order O(1e-4) for `magnitude = ±0.2` (= `±0.05 pu / VSG`); proportionally larger for the in-spec magnitude range `[DIST_MIN, DIST_MAX]` (typically `[1.0, 3.0]`)
- `max_freq_dev_hz` will become non-trivial (estimated O(1e-2) to O(1e-1) Hz at typical disturbance magnitudes; subject to confirmation in the next observation run)
- `r_f` reward component will become non-zero (proportional to Δω²) and can begin to drive the SAC policy gradient

---

## 5. Open observations (recorded, NOT acted on)

1. **Per-VSG-equal injection is not paper-aligned**. Legacy SPS injects all disturbance at one bus (Bus14 or Bus15). CVS now injects equally at all 4 generators. Inter-area mode response will differ from SPS at the same total magnitude. This was a deliberate design-note choice (see design note §2) to avoid topology bias and stay minimal; if paper-fidelity inter-area dynamics matter for the eventual Gate 3 claim, a follow-up would re-route to a single VSG (e.g., always VSG_1, or random per-ep choice). NOT in this fix scope.
2. **Pm_step_t = 0** means the step indicator latches high from t=0 going forward. Because `_apply_disturbance_backend` is called at `bridge.t_current = warmup_end (~0.5 s)`, in practice the step takes effect from that t onward. If a future ep needs the step deferred to a specific later time, it can be done by passing a different `bridge.t_current` (no code change needed).
3. **`Pm_step_amp_<i>` accumulates across episodes** unless `_warmup_cvs` Phase 1 reinitialises it. Per `slx_episode_warmup_cvs.m`, `Pm_step_amp_<i>` IS rewritten every episode reset (init_params field defaulting to 0); so previous-ep disturbances are correctly cleared at the next reset. ✅

---

## 6. Status snapshot

```
HEAD (post-commit): <new>  feat(cvs-g3prep-F-OD3-fix): CVS Pm-step disturbance routing
G3-prep-F spec:     PASS, committed 1c328fc
F instrumentation:  PASS, committed 6d46c75
OD-F-3 verdict:     PASS, committed a62c1e9
OD3-FIX design:     PASS, committed 710aa3f
OD3-FIX impl+verify: PASS — this report
50-ep observation:  NOT RUN, awaits user authorisation
Gate 3 / SAC / 2000-ep:  LOCKED
```

---

## 7. Next step (gated on user)

| Choice | Effect |
|---|---|
| Authorise 50-ep observation smoke (per spec `1c328fc`) | runs ~14 min; will exercise disturbance pathway end-to-end; will quantify Dim 1/2/4/5 with non-trivial ω response |
| Authorise small re-sanity 5-ep CVS smoke first | ~80 s; quick confirmation that env-end disturbance writes work via `_apply_disturbance_backend` (not just direct base-ws assignin as in V-FIX-2) |
| Hold | no further run; commit and pause |
| Defer paper-alignment inter-area mode work | recorded in §5; not in this fix |

OD3-FIX commit recommendation: bundle this verdict + the 2 source edits into one atomic commit (per CLAUDE.md commit-layering — verdict + impl belong together since the verdict cites SHA-256 of the impl files). Halts here until user picks next step.
