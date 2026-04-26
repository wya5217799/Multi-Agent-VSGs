# Phase 3.2 Verdict — Wire v3 into config_simulink.py Dispatch

> **Status: PASS — `KUNDUR_MODEL_PROFILE=…/kundur_cvs_v3.json` now resolves to v3-specific IC + bridge contract; v2 path unaffected (regression clean).**
> **Date:** 2026-04-26
> **Plan:** [`quality_reports/plans/2026-04-26_kundur_cvs_v3_phase3_plan.md`](../../../../quality_reports/plans/2026-04-26_kundur_cvs_v3_phase3_plan.md) §P3.2

---

## 1. Edits in `scenarios/kundur/config_simulink.py`

### Edit A — IC dispatch ladder (L120-149)

Inserted an `elif KUNDUR_MODEL_PROFILE.model_name == 'kundur_cvs_v3':` branch between the existing v2 `if` and the `else` legacy fallback. The branch:
- reads `scenarios/kundur/kundur_ic_cvs_v3.json` (Phase 1 IC, schema_version=3),
- asserts `schema_version == 3` and `topology_variant == 'v3_paper_kundur_16bus'` (refuses to load a non-v3 IC into v3),
- populates `VSG_PE0_DEFAULT_SYS` from `vsg_pm0_pu` (= 4×−0.3691 sys-pu),
- populates `VSG_DELTA0_RAD` from `vsg_internal_emf_angle_rad`.

The else branch (legacy) is unchanged.

### Edit B — BridgeConfig CVS-pattern unification (L195-238)

Introduced a single helper predicate `_IS_CVS = model_name in ('kundur_cvs', 'kundur_cvs_v3')` and replaced 5 per-field ternaries that previously conditioned on `== 'kundur_cvs'`:

| Field | New value when `_IS_CVS` | When legacy/SPS |
|---|---|---|
| `omega_signal` | `'omega_ts_{idx}'` | `'omega_ES{idx}'` |
| `step_strategy` | `'cvs_signal'` | `'phang_feedback'` |
| `m_var_template` | `'M_{idx}'` | `'M0_val_ES{idx}'` |
| `d_var_template` | `'D_{idx}'` | `'D0_val_ES{idx}'` |
| `m0_default` | `24.0` | `12.0` |
| `d0_default` | `4.5` | `3.0` |

v3 inherits the v2 CVS bridge contract verbatim — confirmed safe by the P3.0c readout sanity probe (helper round-trip returns non-empty finite ω/Pe/δ for v3 ESS loggers `omega_ts_1..4`).

No other config field touched. `T_WARMUP` still 3.0 s (P3.3b smoke-stage edit deferred to its own gate per user instruction).

---

## 2. Validation (config-only dry parse, no MATLAB / no training)

### 2.1 v3 profile dispatch

| Field | Got | Expected |
|---|---|---|
| `KUNDUR_MODEL_PROFILE.model_name` | `kundur_cvs_v3` | `kundur_cvs_v3` ✅ |
| `KUNDUR_MODEL_PROFILE.profile_id` | `kundur_cvs_v3` | `kundur_cvs_v3` ✅ |
| `VSG_PE0_DEFAULT_SYS` | `[-0.36909, -0.36909, -0.36909, -0.36909]` | matches `kundur_ic_cvs_v3.json::vsg_pm0_pu` ✅ |
| `VSG_DELTA0_RAD` | `[0.1953, 0.0250, 0.1949, 0.0089]` | matches `kundur_ic_cvs_v3.json::vsg_internal_emf_angle_rad` ✅ |
| `VSG_PE0_DEFAULT_SYS != v2 IC Pm0 (0.2 sys-pu/source)` | True | True (no v2 fallthrough) ✅ |

### 2.2 v3 BridgeConfig fields

| Field | Got | Expected |
|---|---|---|
| `model_name` | `kundur_cvs_v3` | ✅ |
| `step_strategy` | `cvs_signal` | ✅ (matches helper dispatch path) |
| `omega_signal` | `omega_ts_{idx}` | ✅ (matches P3.0b ESS logger rename) |
| `m_var_template` | `M_{idx}` | ✅ |
| `d_var_template` | `D_{idx}` | ✅ |
| `m0_default` | 24.0 | ✅ |
| `d0_default` | 4.5 | ✅ |
| `pe0_default_vsg` | (-0.369, -0.369, -0.369, -0.369) | ✅ |

### 2.3 Contamination scan

Bridge fields scanned for v2/NE39/legacy/SPS tags (`ne39`, `new_england`, `M0_val_ES`, `D0_val_ES`, `phang`): **zero hits**. ✅

### 2.4 v2 regression

Re-imported config with `KUNDUR_MODEL_PROFILE=…/kundur_cvs.json`:

| Field | Got |
|---|---|
| `model_name` | `kundur_cvs` |
| `VSG_PE0_DEFAULT_SYS` matches v2 IC | ✅ |
| `bridge.model_name` | `kundur_cvs` |
| `bridge.step_strategy` | `cvs_signal` |
| `bridge.omega_signal` | `omega_ts_{idx}` |

v2 path unchanged behaviorally (the new `_IS_CVS` predicate evaluates True for v2 the same way the old `model_name == 'kundur_cvs'` did). No regression. ✅

**ALL_PASS = 1.**

---

## 3. State after P3.2

What works now:
- `KUNDUR_MODEL_PROFILE=…/kundur_cvs_v3.json python -c "from scenarios.kundur.config_simulink import KUNDUR_BRIDGE_CONFIG; print(KUNDUR_BRIDGE_CONFIG)"` returns a v3-correct config.
- The bridge will load `kundur_cvs_v3.slx`, dispatch via `cvs_signal` step strategy, and the helper will read `omega_ts_1..4` (P3.0b interface fix) → state extraction works.
- Pm0 / delta0 default values fed to `kundur_cvs_ip.Pm0_pu` / `delta0_<i>` via warmup come from the v3 IC, not v2 fallback.

What does NOT yet work:
- `env.apply_disturbance` still has `if cfg.model_name == 'kundur_cvs':` predicate (line 699). v3 falls through to the legacy SPS TripLoad branch which is a no-op for the v3 .slx. **P3.3 will extend this predicate to include `kundur_cvs_v3`.**
- `T_WARMUP = 3.0 s` — P3.3b will raise to 10 s for smoke (user-approved).

P3.4 smoke is still BLOCKED until P3.3 + P3.3b both complete.

---

## 4. Boundary respected (this turn)

| Item | Status |
|---|---|
| `scenarios/kundur/config_simulink.py` | **edited** (1 elif insertion, 5 ternary refactors via `_IS_CVS` predicate, T_WARMUP NOT touched) |
| `scenarios/kundur/model_profiles/kundur_cvs_v3.json` | **untouched** since commit `5874234` |
| `scenarios/kundur/kundur_ic_cvs_v3.json` / NR / build / .slx / .mat | **untouched** since commit `cbc5dda` |
| `engine/simulink_bridge.py` | **untouched** |
| `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m` | **untouched** |
| `env/simulink/kundur_simulink_env.py` | **untouched** (P3.3 scope) |
| `scenarios/kundur/train_simulink.py` | **untouched** |
| `scenarios/contract.py`, `scenarios/config_simulink_base.py`, `agents/`, `utils/`, `engine/run_*` | **untouched** |
| `scenarios/kundur/model_profiles/{kundur_cvs.json, kundur_ee_legacy.json, kundur_sps_candidate.json, schema.json}` | **untouched** |
| Topology / IC / NR / dispatch / V_spec / line per-km params / disturbance physics / reward / SAC / training | **untouched** |
| v2 / NE39 | **untouched** |

No build, no MATLAB call, no smoke, no training. Validation used `python -c "..."` config dry-parse only.

---

## 5. Files emitted

```
scenarios/kundur/config_simulink.py                        (modified — Edit A + Edit B)
results/harness/kundur/cvs_v3_phase3/phase3_p32_verdict.md  (this file)
```

---

## 6. Halt — request user GO for P3.3

Awaiting GO for P3.3 (extend `env/simulink/kundur_simulink_env.py:_apply_disturbance_backend` predicate to include `kundur_cvs_v3`, reusing v2 CVS Pm-step path verbatim).

P3.3b warmup decision (`T_WARMUP = 10 s` smoke-stage approved) is queued; can be co-edited with P3.3 in a single config_simulink.py touch, or kept in its own commit. User to decide.
