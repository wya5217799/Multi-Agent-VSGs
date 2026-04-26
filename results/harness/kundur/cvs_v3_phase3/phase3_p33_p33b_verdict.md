# Phase 3.3 + 3.3b Verdict — env disturbance routing + smoke-stage warmup

> **Status: PASS — v3 disturbance routing now selects CVS Pm-step path (verbatim from v2 CVS); T_WARMUP=10s recorded as smoke-stage decision (NOT permanent for 2000-ep training).**
> **Date:** 2026-04-26
> **Plan:** [`quality_reports/plans/2026-04-26_kundur_cvs_v3_phase3_plan.md`](../../../../quality_reports/plans/2026-04-26_kundur_cvs_v3_phase3_plan.md) §P3.3, §P3.3b

---

## 1. Edits

### Edit A — P3.3: env predicate extension

[`env/simulink/kundur_simulink_env.py:699`](../../../../env/simulink/kundur_simulink_env.py)

```diff
-        if cfg.model_name == 'kundur_cvs':
+        if cfg.model_name in ('kundur_cvs', 'kundur_cvs_v3'):
```

Plus a one-paragraph comment recording that v3 uses the same per-ESS `Pm_step_t_<i>` / `Pm_step_amp_<i>` workspace gating cluster wired by `build_kundur_cvs_v3.m` (verified via P3.0c readout sanity probe).

**Magnitude / sign / timing / strategy unchanged.** The CVS branch body is reused verbatim:
- target = `DISTURBANCE_VSG_INDICES` default `(0,)` (asymmetric single-VSG[0] step, B1 baseline)
- `amp_focused_pu = magnitude * 100e6 / n_tgt / cfg.sbase_va`
- timing = `t_now = bridge.t_current`
- workspace writes via `bridge.apply_workspace_var('Pm_step_t_<i>', t_now)` / `'Pm_step_amp_<i>', amps[i]`

Legacy SPS `TripLoad` branch (lines 731-750) preserved untouched — still reachable for any future legacy / NE39-style profile.

### Edit B — P3.3b: smoke-stage T_WARMUP raise

[`scenarios/kundur/config_simulink.py:46`](../../../../scenarios/kundur/config_simulink.py)

```diff
-T_WARMUP = 3.0  # overrides config_simulink_base.T_WARMUP = 0.5
+T_WARMUP = 10.0  # smoke-stage; was 3.0 (v2 baseline), bumped per P3.3b
```

Plus comment explicitly recording:
- This is a **smoke-stage only** decision per Phase 3 plan §P3.3b.
- **NOT a permanent 2000-episode training decision.** Phase 4 / Phase 5 may revisit and either keep 10 s, raise to 20-30 s, or pursue an inductor-IC pre-loading fix (build edit, out of scope for current Phase 3 allow-list).
- Empirical justification: Phase 2 P2.1 fix-A2 verdict observed full settling at t=30 s, residual `|ω - 1| < 0.5 mHz` at t=10 s — below typical RL signal magnitude.
- Side effect: v2 (`kundur_cvs`) callers also get T_WARMUP=10 s (was 3 s). Acceptable: v2 also benefits from extra settle margin; wall-clock cost is uniform per episode.

---

## 2. Validation (config-only dry parse, no MATLAB / no smoke / no training)

### 2.1 v3 dispatch

| Check | Got | Want | ✅ |
|---|---|---|---|
| `KUNDUR_MODEL_PROFILE.model_name` | `kundur_cvs_v3` | `kundur_cvs_v3` | ✅ |
| `T_WARMUP` | `10.0` | `10.0` | ✅ |
| env predicate tuple | `('kundur_cvs', 'kundur_cvs_v3')` | both present | ✅ |
| `BridgeConfig.model_name` | `kundur_cvs_v3` | ✅ |
| `BridgeConfig.step_strategy` | `cvs_signal` | ✅ |
| Legacy SPS TripLoad branch (`tripload1_p_var`, `tripload2_p_var`) preserved in env | yes | ✅ |

### 2.2 v2 regression (must keep CVS Pm-step path)

| Check | Got | Want | ✅ |
|---|---|---|---|
| `KUNDUR_MODEL_PROFILE.model_name` | `kundur_cvs` | `kundur_cvs` | ✅ |
| `T_WARMUP` | `10.0` | `10.0` (shared, expected) | ✅ |
| Predicate `'kundur_cvs' in ('kundur_cvs','kundur_cvs_v3')` | True | True | ✅ |

v2 disturbance routing is bit-identical to before (same branch, same magnitude / sign / timing / strategy).

### 2.3 NE39 / legacy SPS untouched

- `env/simulink/ne39_simulink_env.py` — present, untouched.
- Legacy SPS path inside `kundur_simulink_env.py` (TripLoad branch) — present, untouched.
- `scenarios/new_england/` — untouched.

**ALL_PASS = 1.**

---

## 3. State after P3.3 + P3.3b

What works now:
- `KUNDUR_MODEL_PROFILE=…/kundur_cvs_v3.json` resolves to v3 IC + bridge + env disturbance routing all correctly.
- v2 (`kundur_cvs`) path still resolves identically (regression-clean), gets the same shared T_WARMUP bump.
- v3 RL contract is end-to-end consistent: profile JSON ⇒ config dispatch ⇒ bridge config ⇒ env apply_disturbance ⇒ build's Pm-step gating clusters ⇒ helper readout via integer-suffix loggers.

What does NOT yet exist (Phase 4 territory):
- richer disturbance types (`load_step_random_bus`, `wind_trip`, `pm_step_random_source` over G1..G3+ES1..4) — current path covers ESS Pm-step only, sufficient for first 5-ep smoke.
- Phase 4 50-ep gate / dual-PHI experiment.

P3.4 5-ep smoke is now **unblocked from a wiring perspective** but still **requires user GO** per cadence.

---

## 4. Boundary respected (this turn)

| Item | Status |
|---|---|
| `env/simulink/kundur_simulink_env.py` | **edited** (1 predicate line + 4-line comment) |
| `scenarios/kundur/config_simulink.py` | **edited** (1 numeric value + 1 comment block) — total 1 line of code change in T_WARMUP |
| `scenarios/kundur/model_profiles/kundur_cvs_v3.json` | **untouched** since `5874234` |
| `scenarios/kundur/kundur_ic_cvs_v3.json` / NR / build / `.slx` / `.mat` | **untouched** since `cbc5dda` |
| `engine/simulink_bridge.py` | **untouched** |
| `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m` | **untouched** |
| `scenarios/contract.py`, `scenarios/config_simulink_base.py`, `agents/`, training scripts, `utils/` | **untouched** |
| Other model_profiles / schema | **untouched** |
| Topology / IC / NR / dispatch values / V_spec / line per-km params / disturbance physics | **untouched** |
| Reward shaping (PHI_*) / SAC / training loop | **untouched** |
| v2 `kundur_cvs.slx`, `kundur_ic_cvs.json`, `build_kundur_cvs.m`, etc. | **untouched** |
| NE39 (`scenarios/new_england/`, `env/simulink/ne39_simulink_env.py`) | **untouched** |

No build, no MATLAB call, no smoke, no training. Validation is `python -c "..."` config dry-parse + static regex on env source.

---

## 5. Files emitted

```
env/simulink/kundur_simulink_env.py                          (modified — predicate ext)
scenarios/kundur/config_simulink.py                          (modified — T_WARMUP smoke-stage)
results/harness/kundur/cvs_v3_phase3/phase3_p33_p33b_verdict.md  (this file)
```

---

## 6. Halt — request user GO for P3.4

P3.3 + P3.3b complete. v3 RL contract end-to-end:

```
KUNDUR_MODEL_PROFILE=…/kundur_cvs_v3.json
   ↓ profile loader
KundurModelProfile(model_name='kundur_cvs_v3', solver_family='sps_phasor', …)
   ↓ config_simulink.py dispatch
VSG_PE0_DEFAULT_SYS = [-0.369]*4  (from kundur_ic_cvs_v3.json)
T_WARMUP = 10.0 s  (smoke-stage)
KUNDUR_BRIDGE_CONFIG.step_strategy = cvs_signal
KUNDUR_BRIDGE_CONFIG.omega_signal = omega_ts_{idx}
KUNDUR_BRIDGE_CONFIG.m_var_template = M_{idx}
   ↓ KundurSimulinkEnv constructor
SimulinkBridge dispatched to cvs_signal step strategy
   ↓ env.apply_disturbance
CVS Pm-step branch (Pm_step_t_<i>, Pm_step_amp_<i>) — works for v3 build verbatim
   ↓ slx_step_and_read_cvs.m helper
simOut.get(omega_ts_<int>) — integer-suffix names, P3.0b rename ensures match
   ↓ returns non-empty finite ω/Pe/δ
```

**Awaiting GO for P3.4 (5-ep smoke probe).** Recommended invocation:

```
KUNDUR_MODEL_PROFILE=scenarios/kundur/model_profiles/kundur_cvs_v3.json \
  python -m scenarios.kundur.train_simulink \
    --episodes 5 --mode simulink \
    --output results/harness/kundur/cvs_v3_phase3/p34_5ep_smoke
```

(Exact CLI flag set TBD when reading current train script options; can be a probe wrapper instead.)
