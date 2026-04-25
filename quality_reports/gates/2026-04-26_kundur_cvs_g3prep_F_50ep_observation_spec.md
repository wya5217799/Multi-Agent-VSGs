# G3-prep F — Kundur CVS 50-Episode Observation Spec (PRE-50EP)

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg` @ `5db751a`
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** SPEC — observation design only. **No code change. No execution.** Awaits user authorisation to (a) instrument and/or (b) run the 50-ep observation smoke.
**Predecessors:**
- G3-prep-E A3+B1 + 5-ep smoke PASS — `2026-04-26_kundur_cvs_g3prep_E_AB_smoke_PASS.md` (commit `5db751a`)
- G3-prep-E smoke FAIL report — `2026-04-26_kundur_cvs_g3prep_E_smoke_FAIL.md` (commit `f6f6ace`)
- D/E 5-ep smoke spec — `2026-04-26_kundur_cvs_g3prep_DE_smoke_spec.md` (commit `0b22f49`)
- Stage 2 readiness plan §1 D5 (50 ep baseline scope) — `2026-04-25_kundur_cvs_stage2_readiness_plan.md`

---

## TL;DR

50-ep smoke is the **first run that crosses the SAC warmup boundary** (`WARMUP_STEPS = 2000`; 50 ep × 50 step = 2500 transitions). Its job is **not to validate learning**. Its job is to confirm 5 observability questions that the 5-ep smoke could not answer:

1. **Disturbance actually enters** the .slx and produces measurable physical response (5-ep had `apply_disturbance` called but `max_freq_dev_hz=0` everywhere)
2. **`physics_summary` zero values** are explained — either (a) genuinely tiny ω response under current disturbance settings, or (b) instrumentation gap in `_compute_physics_summary` for the CVS env
3. **Schema asymmetry** between Kundur (4 fields) and NE39 (6 fields) — does this hide gating-relevant info under random + early-learning policy
4. **Reward components** `r_f / r_h / r_d` magnitudes and ratios are sane and consistent with the expected zero-`r_f` regime when ω stays at 1.0
5. **SAC `update()` actually fires** after warmup boundary at ep ≈ 40, with finite, non-NaN losses and alpha trajectory

This spec **does not** authorise:
- 50-ep run itself (separate gate)
- 2000-ep paper-replication
- Gate 3 / RL claim
- Reward / network / hyperparameter / disturbance-magnitude tuning
- `physics_summary` schema reconciliation between Kundur and NE39
- `apply_disturbance` mechanism modification
- NE39 / legacy / shared file modification

OD-F-1 through OD-F-4 are the open decisions that may need code edits **before** the 50-ep run; this spec lists them but does not auto-resolve.

---

## 0. Strict scope (boundary)

| Item | Status |
|---|---|
| `engine/simulink_bridge.py` | UNCHANGED (post-C `aa348711…cd08b27d2`) |
| `slx_helpers/vsg_bridge/slx_step_and_read.m` / `slx_episode_warmup.m` (NE39+legacy shared) | UNCHANGED |
| `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m` (G3-prep-C) | UNCHANGED |
| `slx_helpers/vsg_bridge/slx_episode_warmup_cvs.m` (G3-prep-E A3) | UNCHANGED unless OD-F-2 authorises a per-step trace dump (out of spec) |
| NE39 (`scenarios/new_england/*`, `env/simulink/ne39_*.py`, `env/simulink/_base.py`, NE39 `.slx` × 3) | UNCHANGED |
| legacy Kundur (build_powerlib_kundur.m, build_kundur_sps.m, kundur_vsg.slx, kundur_vsg_sps.slx, legacy `kundur_ic.json`, `compute_kundur_powerflow.m`) | UNCHANGED |
| `agents/`, root `config.py`, `scenarios/contract.py`, `scenarios/config_simulink_base.py` | UNCHANGED |
| reward / observation / action / SAC network / hyperparameters | UNCHANGED |
| `BridgeConfig` interface | UNCHANGED |
| `kundur_cvs.slx`, `kundur_ic_cvs.json`, `kundur_cvs_runtime.mat`, `model_profiles/kundur_cvs.json`, `build_kundur_cvs.m`, `compute_kundur_cvs_powerflow.m` | UNCHANGED |
| `M0_default=24, D0_default=18, Pm0=0.5, X_v=0.10, X_tie=0.30, X_inf=0.05, Pe_scale=1.0/Sbase` | UNCHANGED |
| Disturbance magnitude range `[DIST_MIN, DIST_MAX]` | UNCHANGED |
| `WARMUP_STEPS=2000`, `BUFFER_SIZE=10000`, reward weights `φ_f=100, φ_h=1, φ_d=1`, network 4×128 FC | UNCHANGED |
| All D1-D4 / G3-prep-A / B / C / D-config / E verdict reports | UNCHANGED |
| Gate 3 / SAC / 50 ep / 2000 ep | NOT INVOKED until separate authorisation |

---

## 1. The 5 observation dimensions

### 1.1 Dimension 1 — Disturbance actually enters the .slx

**5-ep observed**: `train_simulink.py` L380-381 calls `env.apply_disturbance(magnitude=dist_mag)` once per ep at `step = int(0.5/DT) = 2`. Console log shows per-ep `[Kundur-Simulink] Load reduction: TripLoad1_P=...MW` / `Load increase: TripLoad2_P=...MW` lines with non-zero magnitudes — **the Python-side call fires**.

**Open question**: does the disturbance reach the CVS .slx and modify base-workspace tripload vars / cause a sim-side response?

**5-ep evidence pro/con**:
- PRO disturbance enters: `dist_mag` console line is non-zero per ep; `_warmup_cvs` Phase 1 writes `tripload_state` to base ws via `assignin('base', '<var>', <val>)` (engine/simulink_bridge.py L621-622).
- CON: `max_freq_dev_hz = 0.0` across all 5 ep with multiple disturbance magnitudes — would expect at least transient ω response.

**Two hypotheses to discriminate at 50-ep**:
- **H1.A**: CVS .slx topology has no path from `TripLoad1_P` / `TripLoad2_P` workspace vars to any block. (CVS path uses fixed `R_loadA` / `R_loadB` per `build_kundur_cvs.m` L65-66 + L124-125; tripload_state writes might land on UNREAD vars.)
- **H1.B**: The disturbance does enter but the CVS NR equilibrium is so stiff that the perturbation amplitude `[DIST_MIN, DIST_MAX]` × VSG capacity is below the resolution of `max_freq_dev_hz` measurement in 10s sim window.

**Instrument design (NO code change required at instrument time; just inspect logs after run)**:
- I1.1 — examine `run_meta.json` for `disturbance` field (exists per `_base.py`); record per-ep `magnitude` and `mode`
- I1.2 — examine TB scalar `train/freq_dev_hz` per ep — confirm = 0.0 (already known) or non-zero somewhere
- I1.3 — examine `[Kundur-Simulink] Load …` log lines for **all 50 ep**; confirm Python-side disturbance APIs are firing with non-zero magnitudes
- I1.4 — **MCP probe (post-run, read-only)**: pick one ep run dir; inspect base ws and confirm whether `TripLoad1_P` / `TripLoad2_P` are ever set to values different from `kundur_cvs.slx` build defaults

**Decision boundary if H1.A confirmed (CVS doesn't read tripload vars)**:
- This is a **CVS env mechanism gap, not a smoke fail**. 50-ep run is still a valid observation smoke (its job is to confirm the answer, not to fix CVS).
- Out-of-scope follow-up: `kundur_simulink_env.py::apply_disturbance` may need a CVS-specific path that perturbs `Pm_step_amp_<i>` (already wired in CVS .slx and `_warmup_cvs` Phase 1). NOT in this spec.

**Decision boundary if H1.B confirmed (CVS equilibrium too stiff)**:
- Out-of-scope follow-up: increase `[DIST_MIN, DIST_MAX]` for CVS profile, OR introduce a paper-aligned step disturbance via `Pm_step_amp_<i>` in `_warmup_cvs` per-ep init_params. NOT in this spec.

### 1.2 Dimension 2 — Why `physics_summary` is all zeros

**5-ep observed**: 5/5 ep `max_freq_dev_hz = 0.0`, `mean_freq_dev_hz = 0.0`, `settled = True`, `max_power_swing = 0.0`. Reward magnitude ~-422 from `r_h` + `r_d` action-magnitude penalties only.

**Computation chain (already verified, no change needed)**:
- L289 (`kundur_simulink_env.py::step()`): `_max_freq_dev = float(np.max(np.abs((self._omega - 1.0) * F_NOM)))`
- L392-393 (`train_simulink.py`): `step_freq_dev = info["max_freq_deviation_hz"]; ep_max_freq_dev = max(ep_max_freq_dev, step_freq_dev)`
- L487-491: `physics_summary` logged with `max_freq_dev_hz` = `ep_max_freq_dev`

The chain is correct. The all-zero outcome is **either** (a) `self._omega` actually stays at 1.0 (CVS NR IC is that stable), **or** (b) `self._omega` is not being refreshed correctly from the CVS step output.

**Two hypotheses**:
- **H2.A**: `self._omega` is correctly refreshed; ω truly stays in `[1.000000, 1.000000]` band (D3 verdict 30s zero-action confirmed this for non-action; need to confirm under random ΔH/ΔD too)
- **H2.B**: `self._omega` is stale or zero-initialised; CVS Timeseries `omega_ts_<i>` reading via `slx_step_and_read_cvs.m` is buggy and returns the build-time IC unchanged

**Instrument design**:
- I2.1 — examine `run_meta.json` and 50-ep `training_log.json` for `omega` field history; confirm shape `(50, n_steps, 4)` (exists per `info["omega"]` in env step, but may not be persisted to log)
- I2.2 — examine TB scalar `train/freq_dev_hz` over 50 ep; if the trajectory increases monotonically once SAC learns OR shows ep-to-ep variance, H2.A; if flat at 0.0 throughout, H2.B (or H1.A)
- I2.3 — **MCP probe (post-run, read-only)**: re-run a single CVS warmup + 1-step manual cycle in the shared session, capture `omega_ts_<i>` Timeseries from `simOut`, verify the values reaching the bridge

**Schema-side observability gap**: `info["omega"]` exists per step but is **not** propagated into `physics_summary`. Per-step ω trace is in TB events (one scalar per ep) and in MATLAB Timeseries (one per simOut). **No need to change Python schema in this spec.**

### 1.3 Dimension 3 — Kundur vs NE39 schema asymmetry

**Current Kundur `physics_summary` keys** (`scenarios/kundur/train_simulink.py` L487-492): `max_freq_dev_hz`, `mean_freq_dev_hz`, `settled`, `max_power_swing` (4 keys).

**NE39 `physics_summary` keys** (`scenarios/new_england/train_simulink.py`, observed in D-pre snapshot): `max_freq_dev_hz`, `mean_freq_dev_hz`, `settled`, `settled_moderate`, `settled_paper`, `max_power_swing` (6 keys; +2 graded settled thresholds).

**Asymmetry origin**: Kundur uses single threshold `settled = all(tail_freq_devs < 0.1 Hz)` (L480); NE39 has graded thresholds for stricter / more permissive judgment.

**Impact analysis for 50-ep observation**:
- Under a random / early-learning policy at 50 ep, neither `settled_moderate` nor `settled_paper` would carry decisive learning signal — both NE39 D-pre runs report 0/3 `settled_paper` with random actions.
- For Kundur 50-ep, the missing keys do not block any of the 5 dimensions in this spec.
- For 2000-ep paper-replication (NOT this spec), the asymmetry would matter for cross-scenario comparison.

**Decision**: 50-ep observation **does not** require schema reconciliation. Recorded as follow-up for the 2000-ep stage.

### 1.4 Dimension 4 — Reward components reasonable

**5-ep observed**: `ep_reward` mean -422.91; per-ep `[-377, -419, -486, -466, -365]`. `info["reward_components"]` aggregated as `ep_components = {r_f, r_h, r_d}` (L387-388) **but not logged to `training_log.json`** — only TB `train/reward` and `train/avg10_reward` are scalar-recorded.

**Expected magnitudes at 50-ep with random policy**:
- `r_f`: `-φ_f × |Δω|^2` summed across steps; with ω ≈ 1.0 and Δω ≈ 0 (per H2.A), expect `r_f ≈ 0`
- `r_h`: `-φ_h × |ΔH|^2`; with ΔH random in `[-16.1, 72]` (per `config.py` L49), expect `r_h ~= O(-100)` per step × 50 step → `~ -500..-2000` per ep
- `r_d`: `-φ_d × |ΔD|^2`; with ΔD random in `[-14, 54]`, similar magnitude

**Hypothesis check**: 5-ep mean reward -422.91 / 50 step / 4 agent ≈ -2.1 per step per agent. For random `[H_MIN, H_MAX]` action with `φ_h=1`, this fits `r_h+r_d` dominant regime (within order of magnitude). H4.A: reward components are sane.

**Instrument design (NO code change required for the 50-ep run; logging already in place via TB and `ep_components` accumulator; need explicit dump to JSON)**:
- I4.1 — examine TB scalar `train/reward` per ep; trajectory vs ep should be flat noise during ep 1-39 (random), small mean shift during ep 40-50 (post-warmup learning starts); if flat throughout 50 ep → SAC not updating (Dimension 5)
- I4.2 — extract per-ep `ep_components` from a hooked external aggregation (post-run grep of TB event file or live log file `live.log`), confirm `r_f ≈ 0` (consistent with H2.A) and `r_h + r_d` ≈ ep_reward
- I4.3 — **OD-F-1**: `ep_components` is computed per-ep but never written to `physics_summary` or `log`. To formally verify reward decomposition at 50-ep, an instrumentation patch is needed (see §6 OD-F-1).

### 1.5 Dimension 5 — SAC `update()` actually fires after warmup

**5-ep observed**: `alphas`, `critic_losses`, `policy_losses` all length 0 (no update fired). `WARMUP_STEPS=2000` vs 5×50=250 transitions « 2000.

**At 50-ep**: 50×50=2500 transitions ≥ 2000. After the 2000th transition (ep `int(2000/50) = 40`), `agent.update()` should fire and append to losses arrays.

**Computation chain (already verified, no change needed)**:
- L411-413: `effective_repeat = min(args.update_repeat=10, max(1, len(buffer)//warmup_steps))`
- For ep 1-39 (`len(buffer) < 2000`): `effective_repeat = max(1, 0) = 1` → calls `agent.update()` once per step
- BUT internally `agent.update()` returns empty/falsy when buffer < `warmup_steps` (per SAC convention; need to check `agents/sac.py` to confirm — this spec does NOT authorise that read; rely on the 5-ep empirical: 0 updates means update returned None for those 250 transitions; consistent)

**Hypothesis to confirm at 50-ep**:
- **H5.A**: SAC starts firing at ep 40-41, alphas/critic/policy losses all become non-empty arrays. NaN/Inf absent.
- **H5.B**: SAC never fires (buffer counter bug, gating mis-set, or mid-buffer-size dispatch misroute) → arrays remain empty even at 50-ep.

**Instrument design (NO code change required)**:
- I5.1 — `len(log["alphas"])` after 50-ep run; expected ~10-11 ep × 50 step × 10 effective_repeat = ~5000 entries (or ~500 if effective_repeat doesn't ramp), or 0 if H5.B
- I5.2 — `log["alphas"][0]` first non-empty entry's index → confirm first-fire ep ≈ 40 (within ±2 ep tolerance)
- I5.3 — TB `train/alpha`, `train/critic_loss`, `train/policy_loss` post ep 40 — confirm finite, non-NaN, monotone behaviour
- I5.4 — TB `train/buffer_size` per ep — should grow linearly 50 → 2500 across ep 1-50

---

## 2. PASS / OBSERVATION / ABORT criteria

The 50-ep run is an **observation smoke**, not a Gate. It does not have hard PASS/FAIL boundaries on physics or learning quality. It has:
- Hard ABORT criteria (sim crash, infrastructure failure)
- OBSERVATION outputs (5 dimensions; PASS/FAIL each is informational)
- Spec PASS = 50 ep complete + 5 dimensions answered + no boundary violation

### 2.1 Hard ABORT (any one triggers immediate stop, no retry)

| # | Condition | Action |
|---|---|---|
| A1 | sim / matlab.engine error any ep | stop, dump traces |
| A2 | NaN / Inf in ω, δ, Pe, reward, alpha, critic_loss, policy_loss | stop, capture state |
| A3 | ω hard clip [0.7, 1.3] touch any ep any step | stop |
| A4 | per-ep wall-clock > 5 min (5-ep saw 16 s/ep; 5 min = ~19× margin) | stop, suspect cache/compile pathology |
| A5 | 50-ep total wall-clock > 60 min (5-ep saw 79 s; expected ~14 min for 50 ep) | stop |
| A6 | `physics_summary` field set changes vs 5-ep schema | stop, schema regression |

### 2.2 OBSERVATION outputs (spec PASS = all 5 answered)

| # | Dimension | Answer source | Spec PASS condition |
|---|---|---|---|
| O1 | Disturbance enters | I1.1-I1.4 | answered with H1.A or H1.B (not undecided) |
| O2 | physics_summary zero | I2.1-I2.3 | answered with H2.A or H2.B (not undecided) |
| O3 | Schema asymmetry impact | §1.3 | confirmed not blocking 50-ep observation |
| O4 | Reward decomposition | I4.1-I4.3 (or OD-F-1) | r_h+r_d dominant under random policy; OR explicit gap noted |
| O5 | SAC update fires | I5.1-I5.4 | answered with H5.A or H5.B (not undecided) |

### 2.3 Diagnostic-only (recorded, not gating)

- δ-channel overshoot ratio
- per-ep wall-clock distribution
- `r_f / r_h / r_d` ratios under early-learning policy (not random)
- TB scalar trajectories (`train/reward`, `train/freq_dev_hz`, etc.) shape

---

## 3. Run configuration

| Setting | Value | Source / Lock |
|---|---|---|
| `--mode` | `simulink` | required |
| `--episodes` | **50** | this spec |
| `--resume` | `none` | clean run |
| `--seed` | `42` | reproducibility (same as 5-ep) |
| `--update-repeat` | `10` (default per `config.py`) | UNCHANGED |
| `KUNDUR_MODEL_PROFILE` | `<absolute path>/scenarios/kundur/model_profiles/kundur_cvs.json` | dispatch trigger |
| `T_EPISODE` | 10 s | UNCHANGED |
| `STEPS_PER_EPISODE` | 50 | UNCHANGED |
| `DT` | 0.2 s | UNCHANGED |
| `WARMUP_STEPS` (SAC) | 2000 | UNCHANGED — chosen specifically so ep 40 = first update |
| `BUFFER_SIZE` | 10000 | UNCHANGED |
| Reward weights `φ_f, φ_h, φ_d` | 100, 1, 1 | UNCHANGED |
| Network | 4×128 FC | UNCHANGED |
| `H_MIN/H_MAX/D_MIN/D_MAX` | per `config.py` | UNCHANGED |
| Disturbance | random `[DIST_MIN, DIST_MAX]` per ep | UNCHANGED |

### 3.1 Command (only after OD-F-1..3 are resolved or accepted as-is)

```bash
KUNDUR_MODEL_PROFILE="$(pwd)/scenarios/kundur/model_profiles/kundur_cvs.json" \
"C:/Users/27443/miniconda3/envs/andes_env/python.exe" \
  scenarios/kundur/train_simulink.py \
  --mode simulink \
  --episodes 50 \
  --resume none \
  --seed 42
```

### 3.2 Reproducibility lock

| File | SHA-256 |
|---|---|
| `scenarios/kundur/config_simulink.py` | `01d26606759943f005d5e6478dc448daa7cc459849d6089a32f4a1544fbf3405` |
| `scenarios/kundur/simulink_models/build_kundur_cvs.m` | `cc6ce62f8dfc24609f19ee29f9ab293f5fee06850e11d80b597544e5b1965cfe` |
| `slx_helpers/vsg_bridge/slx_episode_warmup_cvs.m` | `aae43f292cc3e337a5f5c93d6ff782f15eb8dc7375c8a8650a35c86f66cddfbc` |
| `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m` | `d3f732e31530900bed0a39fb35780ecdcbe687a7850e8ab451ddc126ed1824e0` |
| `engine/simulink_bridge.py` | `aa348711dd02dc6acb49d5f28b648a397b9121d2e0f3d608ab14841cd08b27d2` |
| `scenarios/kundur/simulink_models/kundur_cvs.slx` | `c6744abb3bb878bb18522cba0cb6804037334b8ac802fe04ffddfd5d6ae17beb` |
| `scenarios/kundur/simulink_models/kundur_cvs_runtime.mat` | `1af0f52fde75a6c10c2e985f1b093016b2e8d57e9af615d03a9b508509908117` |
| `scenarios/kundur/kundur_ic_cvs.json` | `98d56b24e48efae592790e01b80686825d04b62cf94cc7e54cfadcb763de5780` |
| `scenarios/kundur/model_profiles/kundur_cvs.json` | `ab89e82e62b102c0d1da9284367c22cbe00b8a10940147d4b24d8dd2a0eaf869` |

§0 boundary 16 NE39/legacy/shared files: byte-equivalent to D-pre / G3-prep-E lock.

### 3.3 Expected outputs (gitignored)

| Path | Content |
|---|---|
| `results/sim_kundur/runs/kundur_simulink_<ts>/training_log.json` | `episode_rewards` (50), `physics_summary` (50), `alphas`, `critic_losses`, `policy_losses` (post-warmup non-empty) |
| `results/sim_kundur/runs/kundur_simulink_<ts>/run_meta.json` | seed, git_hash, disturbance_mode, etc. |
| `results/sim_kundur/runs/kundur_simulink_<ts>/logs/live.log` | per-ep `EP {n} R={r} avg10={a} a={alpha} df={f}Hz buf={b} t={s}s` |
| `results/sim_kundur/runs/kundur_simulink_<ts>/tb/` | TensorBoard scalars: `train/reward`, `train/avg10_reward`, `train/alpha`, `train/freq_dev_hz`, `train/buffer_size`, `train/critic_loss`, `train/policy_loss` |
| `results/sim_kundur/runs/kundur_simulink_<ts>/checkpoints/final.pt` | SAC final checkpoint |

Estimated total wall-clock: ~14 min (5-ep was 79 s = 15.83 s/ep × 50 ≈ 13 min; allow some growth for SAC update overhead post ep 40).

---

## 4. Verification chain (post-run, read-only unless OD-F-1 authorised)

| # | Check | Tool | Output |
|---|---|---|---|
| V1 | `episode_rewards` length = 50, no NaN | jq / python | trajectory shape |
| V2 | `physics_summary` length = 50, schema = 4 keys (Kundur convention) | jq | schema parity vs 5-ep |
| V3 | `max_freq_dev_hz` distribution: max, mean, fraction-of-ep > 0.1 Hz | python | distinguishes H2.A vs H2.B vs H1.A |
| V4 | `alphas / critic_losses / policy_losses` length, first non-zero index, NaN check | python | distinguishes H5.A vs H5.B |
| V5 | TB scalar `train/buffer_size` slope (linear 50→2500) | TB inspect | confirms transitions are stored |
| V6 | TB scalar `train/freq_dev_hz` per ep — distribution + ep-40 transition | TB inspect | overlaps with V3 |
| V7 | live.log per-ep counters (df, buf, alpha, t) | grep | observability cross-check |
| V8 | `[Kundur-Simulink] Load …` line count = 50 | grep | confirms apply_disturbance fires every ep |
| V9 | boundary file SHA-256 (16 NE39/legacy/shared) | python sha256 | unchanged contract |
| V10 | CVS-side post-run SHA-256 (5 files) | python sha256 | unchanged source |

### 4.1 NE39 contamination tripwire — DEFERRED unless reward / physics anomaly

50-ep modifies **no** NE39 / shared / legacy files; the SHA-256 list will confirm byte-equivalence. NE39 tripwire 3-ep run (~11 min) is **deferred** by default.

Run only if:
- V9 fails (any §0 file SHA changes)
- V3 reveals freq_dev > 12 Hz any ep (regression vs 5-ep)
- User explicitly requests it

---

## 5. What the run does NOT validate

- ❌ NOT a learning claim. SAC fires only ~10 ep (40-50) post-warmup; that is not a convergence run.
- ❌ NOT a reward shaping verification. Reward weights and components are inherited from `config.py` per paper; this spec does not test their correctness, only observability.
- ❌ NOT a CVS env disturbance mechanism review. If disturbance does not enter (H1.A), this spec records it but does not propose a fix.
- ❌ NOT a Kundur/NE39 schema reconciliation.
- ❌ NOT a Gate 3 entry. Gate 3 needs separate authorisation and the 2000-ep run that follows.

---

## 6. Open decisions (gated on user; spec does not auto-resolve)

### OD-F-1 — Reward components instrumentation

**Problem**: `ep_components = {r_f, r_h, r_d}` is accumulated in `train_simulink.py` (L387-388) but never written to `training_log.json` `physics_summary` or any other JSON field. Only the scalar mean enters TB as `train/reward`.

**Why this matters at 50-ep**: Dimension 4 (reward decomposition) cannot be answered from artefacts alone unless `ep_components` is dumped. With current code, post-run V/I diagnosis can compare `ep_reward` totals only, not the `r_f / r_h / r_d` split.

**Three options for user to pick**:
| Choice | Surface | Risk |
|---|---|---|
| **F-1.A**: minimal `train_simulink.py` patch — add `r_f`, `r_h`, `r_d` keys to `physics_summary` dict (~3 lines in L487-492) | Kundur train script only; no env change | Asymmetric vs NE39 again (NE39 also lacks these keys); need to mirror later |
| **F-1.B**: read `ep_components` from TB events in post-run analysis (`tensorboard.backend.event_processing`) | Zero code change | Adds analysis-tool dependency; values not first-class in JSON |
| **F-1.C**: skip — accept that 50-ep cannot answer Dimension 4 quantitatively; note as follow-up | Zero code change | Dimension 4 becomes "OBSERVATION incomplete" |

### OD-F-2 — Per-step ω trace dump

**Problem**: To distinguish H2.A vs H2.B, ideally we have per-step ω traces (50 ep × 50 step × 4 VSG = 10000 entries). Currently only ep-aggregated `max_freq_dev_hz` is in `physics_summary`; per-step ω is in `info["omega"]` per env step but **not persisted**.

**Three options**:
| Choice | Surface | Risk |
|---|---|---|
| **F-2.A**: add per-step ω trace to `training_log.json` (~5 lines in `train_simulink.py` accumulator + L487 dict) | Train script only; ~10 KB per ep × 50 ep = 500 KB JSON growth | Acceptable file-size; need to mirror in NE39 if NE39 picks it up |
| **F-2.B**: set up MATLAB ToWorkspace / Simulink Data Inspector to capture omega_ts_<i> Timeseries to a `.mat` file per ep | Touches `slx_episode_warmup_cvs.m` or `slx_step_and_read_cvs.m`; out of scope per §0 | Most physical; out of scope |
| **F-2.C**: post-run **MCP probe** — re-run a single warmup + step cycle in shared session and capture the Timeseries on demand | Zero code change; single-ep evidence sufficient if H2.A is decisive | Only ep-1 sample; if H2.A fails for some ep, cannot trace which |

### OD-F-3 — `apply_disturbance` instrumentation under CVS

**Problem**: Console output shows `[Kundur-Simulink] Load reduction: TripLoad1_P=...MW` but does not confirm the value reaches the CVS .slx (H1.A). To distinguish H1.A vs H1.B, we need either:

| Choice | Surface |
|---|---|
| **F-3.A**: post-run **MCP probe** — read base ws after one ep, confirm `TripLoad1_P` / `TripLoad2_P` differ from build defaults | Zero code change; sufficient for binary decision |
| **F-3.B**: add a `bridge.get_workspace_var(name)` API call from `apply_disturbance` to log the post-write value | Touches `engine/simulink_bridge.py` or `kundur_simulink_env.py`; out of scope |
| **F-3.C**: skip — rely on H1.A vs H1.B inference from V3 + V8 alone | Weakest, but zero code change |

### OD-F-4 — Run-time scope authorisation

| Choice | Effect |
|---|---|
| **F-4.A**: authorise 50-ep run with current code (no F-1/2/3 patches) — Dimension 4 + Dimension 2 partially answered via OD-F-1.B / OD-F-2.C / OD-F-3.A read-only paths | safest; less precise |
| **F-4.B**: authorise F-1.A + F-2.A patches first (single train_simulink.py commit), then run | precision answers; one extra commit |
| **F-4.C**: hold — keep spec on disk; user reviews and decides later | no time spent |

### OD-F-5 — Spec commit

| Choice | Effect |
|---|---|
| commit this spec (doc-only) | locks observation design |
| hold | keeps spec on disk only |

---

## 7. Status snapshot

```
HEAD: 5db751a feat(cvs-g3prep-E): A3 sidecar + B1 BridgeConfig fields, 5-ep smoke PASS
Gate 1:  PASS  (commit 307952e)
Gate 2:  PASS  (commit 74428d7, D4-rev-B)
Gate 3:  LOCKED — RL/SAC entry not authorised
G3-prep-A:        PASS, committed 4587f66
G3-prep-B:        PASS, committed c97cabb
G3-prep-C:        PASS, committed 90a0314
D-pre:            PASS, committed a12189e
D/E spec:         PASS, committed 0b22f49
D-config:         PASS, committed 4785cc9
G3-prep-E FAIL:   committed f6f6ace
G3-prep-E A3+B1:  PASS, committed 5db751a (5-ep plumbing smoke)
G3-prep-F (50-ep observation): SPEC ONLY — this report; not committed; not run
```

---

## 8. Next step (gated on user)

| Choice | Effect |
|---|---|
| **F-5 commit** + pick F-4.A/B/C | spec locked; run gated on F-4 pick |
| **F-4.A** authorise + run 50-ep with no F-1/2/3 patches | runs ~14 min; Dimensions 1/2/4 partially answered |
| **F-4.B** authorise F-1.A + F-2.A patches, then run | requires separate commit ladder per CLAUDE.md commit-layering rule (each patch is its own gate) |
| **hold** | no action; spec stays on disk |
| **revert F-4 / F-5** | drop spec |

50-ep / Gate 3 / SAC-claim / 2000-ep paper-replication / NE39 modification all **remain LOCKED** under any choice above.
