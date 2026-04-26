# Phase 3.0 Verdict — Read-Only Dependency Audit (Kundur CVS v3)

> **Status: AUDIT COMPLETE — one BLOCKER discovered, three risks identified, P3.3b mandatory before P3.4 smoke.**
> **Date:** 2026-04-26
> **Plan:** [`quality_reports/plans/2026-04-26_kundur_cvs_v3_phase3_plan.md`](../../../../quality_reports/plans/2026-04-26_kundur_cvs_v3_phase3_plan.md)
> **Mode:** read-only — zero file edits.

---

## 1. Files inspected

| File | Lines | Purpose |
|---|---|---|
| `scenarios/kundur/model_profile.py` | 75 (full) | profile JSON loader + `KundurModelProfile` dataclass + enum validators |
| `scenarios/kundur/config_simulink.py` | 100–253 | profile dispatch ladder + `KUNDUR_BRIDGE_CONFIG` ternaries |
| `engine/simulink_bridge.py` | 1–200 | bridge registry + `BridgeConfig` dataclass + `STEP_STRATEGY_MODES` enum |
| `env/simulink/kundur_simulink_env.py` | 678–761 | `_apply_disturbance_backend` for `kundur_cvs` Pm-step path |
| `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m` | 1–120 | CVS step strategy MATLAB helper — reads loggers from simOut |
| `scenarios/kundur/train_simulink.py` | 1–80 | argparse + env construction (env-var-driven `KUNDUR_MODEL_PROFILE`) |

Read-only access only. No write, no compile, no MATLAB call.

---

## 2. Insertion points for P3.1 / P3.2 / P3.3

### P3.1 — `scenarios/kundur/model_profiles/kundur_cvs_v3.json` (NEW file)

Loader (`load_kundur_model_profile`, [`model_profile.py:72`](../../../../scenarios/kundur/model_profile.py)) is **schema-driven and profile-name-agnostic**. v3 JSON drops in cleanly with the same shape as the v2 [`kundur_cvs.json`](../../../../scenarios/kundur/model_profiles/kundur_cvs.json):

```jsonc
{
  "scenario_id": "kundur",
  "profile_id": "kundur_cvs_v3",
  "model_name": "kundur_cvs_v3",
  "solver_family": "sps_phasor",     // valid enum
  "pe_measurement": "vi",            // valid enum
  "phase_command_mode": "passthrough",
  "warmup_mode": "technical_reset_only",
  "feature_flags": {
    "allow_pref_ramp": false,
    "allow_simscape_solver_config": false,
    "allow_feedback_only_pe_chain": false
  }
}
```

No code change needed in `model_profile.py`.

### P3.2 — `scenarios/kundur/config_simulink.py` two edits

**Edit A** (IC dispatch ladder), insert at L127 between the existing `if` and `else`:

```python
elif KUNDUR_MODEL_PROFILE.model_name == 'kundur_cvs_v3':
    import json as _json
    _v3_ic_path = Path(__file__).resolve().parent / 'kundur_ic_cvs_v3.json'
    with _v3_ic_path.open(encoding='utf-8') as _f:
        _v3_ic_raw = _json.load(_f)
    VSG_PE0_DEFAULT_SYS = np.asarray(_v3_ic_raw['vsg_pm0_pu'], dtype=np.float64)   # [-0.369]*4
    VSG_DELTA0_RAD      = np.asarray(_v3_ic_raw['vsg_internal_emf_angle_rad'], dtype=np.float64)
```

**Edit B** (BridgeConfig ternaries L210–228), extend each predicate from `model_name == 'kundur_cvs'` to `model_name in {'kundur_cvs', 'kundur_cvs_v3'}`. This propagates the CVS-pattern bridge configuration to v3:

| field | v2 / v3 value | v3 contract notes |
|---|---|---|
| `omega_signal` | `'omega_ts_{idx}'` | **MISMATCH** — see §3 BLOCKER below |
| `m_var_template` | `'M_{idx}'` | ✅ v3 build emits `M_1..M_4` workspace vars |
| `d_var_template` | `'D_{idx}'` | ✅ v3 build emits `D_1..D_4` |
| `step_strategy` | `'cvs_signal'` | ✅ existing dispatch covers v3 if signal names align |
| `m0_default` | `24.0` | ✅ matches v3 build defaults |
| `d0_default` | `4.5` | ✅ matches v3 build defaults |
| `pe0_default_vsg` | from v3 IC `vsg_pm0_pu` (`[-0.369]*4`) | works via Edit A |

### P3.3 — `env/simulink/kundur_simulink_env.py:692-729` (apply_disturbance)

Current `if cfg.model_name == 'kundur_cvs':` branch already uses the `Pm_step_amp_<i>` workspace mechanism that v3 build inherits unchanged. **Minimal v3 path = include `'kundur_cvs_v3'` in the same branch predicate** — same disturbance routing works because v3 build wires `Pm_step_t_1..4` and `Pm_step_amp_1..4` exactly the same as v2 CVS.

For the **first smoke (P3.4)** the minimal extension is sufficient. Richer disturbance types (LoadStep R-toggle, WindAmp gating, SG Pm-step) can be added later as additional `disturbance_type` parameters.

---

## 3. Logger naming decision — BLOCKER discovered

[`slx_helpers/vsg_bridge/slx_step_and_read_cvs.m:111-113`](../../../../slx_helpers/vsg_bridge/slx_step_and_read_cvs.m) hardcodes the logger names with `%d` integer formatting:

```matlab
omega_ts = simOut.get(sprintf('omega_ts_%d', idx));
delta_ts = simOut.get(sprintf('delta_ts_%d', idx));
pe_ts    = simOut.get(sprintf('Pe_ts_%d',    idx));
```

This helper does **NOT** consult `cfg.omega_signal` / `cfg.delta_signal` — those bridge config fields exist but are unused by the CVS dispatch path. v2 build emits `omega_ts_1..4` (integer), which matches the hardcoded `%d` format. **v3 build emits `omega_ts_ES1..ES4`** (`sname` = `'ES1'` etc., per `add_block(... 'VariableName', sprintf('omega_ts_%s', sname), ...)` in `build_kundur_cvs_v3.m`).

When `slx_step_and_read_cvs.m` runs against the v3 .slx, `simOut.get('omega_ts_1')` will return empty → `step_cvs_extract_state` falls through the `if isempty(...)` guard → state stays zero → **bridge.step() returns zero ω/Pe/δ for every step**. RL training would receive constant observations and learn nothing.

**This is the dominant Phase 3 BLOCKER.**

### Resolution options (all require user authorization — outside Phase 3 allow-list)

| Option | Edit | Allowed by current allow-list? | Estimated effort |
|---|---|---|---|
| **R1** Build-side rename: change v3 build's logger `VariableName` from `omega_ts_<sname>` to `omega_ts_<int_idx>` for ESS only (G/W loggers can keep ES suffix or be renamed too) | `build_kundur_cvs_v3.m` (one line per logger × 4 ESS × 3 channels = 12 lines) + rebuild + re-validate fix-A2 probes | ❌ build is Phase-1 + fix-A2 locked | ~30 min (build + sanity sweep) |
| **R2** Helper-side template fix: edit `slx_step_and_read_cvs.m` to read `cfg.omega_signal` / `cfg.delta_signal` / a new `cfg.pe_signal` and use `strrep` for `{idx}` | `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m` + add `pe_signal` field to `BridgeConfig` | ❌ slx_helpers is implicit-deny (shared MATLAB layer); also touches `engine/simulink_bridge.py` | ~45 min |
| **R3** Profile-aware logger rename via post-build hook: add a tiny `slx_helpers/vsg_bridge/slx_rename_v3_loggers.m` that reads the v3 .slx, renames ESS logger VariableName fields to `omega_ts_<int>` style, and re-saves | new file under `slx_helpers/vsg_bridge/` | ❌ same boundary issue as R2 | ~30 min |
| **R4** Helper signal-name fallback: edit helper to try `omega_ts_<int>` first, then `omega_ts_ES<int>` if empty | `slx_step_and_read_cvs.m` only | ❌ same as R2 | ~15 min |

**Recommendation**: option **R1 (build-side rename)** is the smallest, cleanest fix and keeps the helper / bridge contract simple. It does require breaking the Phase 1 / fix-A2 build lock, which is a user-authorization decision. R4 is the lowest-risk alternative if the helper is allowed to grow a fallback.

### Compromise option (in-spirit, not in-allow-list)

The Phase 3 plan §3 P3.2 sub-task already anticipated `omega_signal` override in v3 BridgeConfig — but the helper ignores `cfg.omega_signal`. Either:
- the plan's R-P3-1 mitigation needs to be re-scoped to require a helper edit (R2), or
- the build needs to be re-locked to allow the rename (R1).

**Either way, P3.0 cannot be resolved purely within the original allow-list. User decision required.**

---

## 4. Disturbance routing decision for v3 (first smoke)

For P3.4 (5-ep smoke), the **minimal route** is:

- Treat `kundur_cvs_v3` like `kundur_cvs` in `_apply_disturbance_backend`.
- Use the existing `Pm_step_amp_<i>` mechanism on ESS only (build emits the same workspace gating as v2 CVS).
- Default `DISTURBANCE_VSG_INDICES=(0,)` → asymmetric single-VSG[0] disturbance, matching the B1 reward-shaping baseline.

This reuses 100 % of the v2 CVS apply_disturbance logic with one predicate-extension edit.

**Richer disturbance types** (`load_step_random_bus` via `set_param` on LoadStep7/9 R, `wind_trip` via `assignin` of WindAmp_w, `pm_step_random_source` covering all 7 dynamic sources) are **deferred to Phase 4** dataset design. Phase 2 verdicts already document the LoadStep / WindAmp limitations — Phase 4 will choose the disturbance mix based on r_f signal shape under the dual-PHI experiment.

---

## 5. Warmup risk assessment

### Phase 2 measurements
- P2.1 zero-action: full settling at t = 30 s post-reset (ES3 has slowest decay, τ ≈ 5 s).
- Trajectory milestones (G1 ω): t=1 s `0.961`, t=5 s `1.000`, t=10 s `1.0025`, t=30 s `0.99999...`
- After t = 5 s, residual |Δω| at G1 < 5 mHz; after t = 10 s, < 0.5 mHz.

### Current Kundur warmup
[`scenarios/kundur/config_simulink.py:46`](../../../../scenarios/kundur/config_simulink.py): `T_WARMUP = 3.0` overrides the v2 base default 0.5 s.

### Trade-off
- (a) raise `T_WARMUP` to 30 s → clean physics, +30 s wall per episode → 50-ep wall ≈ 25 min, 2000-ep training ≈ 16 hr (vs v2 baseline 2 hr).
- (b) keep `T_WARMUP` at 3 s, accept residual:
  - residual at t = 3 s ≈ 1 % ω (per P2.1 trajectory) — **larger than typical RL signal magnitude**
  - during the first observation window (t = 3 – 3.2 s), the agent sees a transient that's NOT caused by its action
  - Phase 4 reward shaping (PHI_F = 100) would amplify this noise into the loss
  - **NOT recommended without further evidence**.
- (c) intermediate T_WARMUP = 10 s: residual < 0.5 mHz, +10 s wall per ep, 2000-ep ≈ 5.5 hr. Reasonable middle ground.
- (d) build-side fix (preload inductor IC): RC-A inductor IC option from earlier; FORBIDDEN by Phase 3 allow-list.

### P3.3b decision required

Per the user-mandated P3.3b gate (§3 of plan), **a feasibility doc is required before P3.4** answering:
1. which option (a / b / c / d) is viable WITHOUT violating the Phase 3 allow-list?
2. what is the minimum-overhead choice?

P3.3b can be written without any code change — it is a planning / cost analysis step.

**My recommendation for P3.3b**: option **(c) T_WARMUP = 10 s** as the minimum-overhead allow-list-compliant choice. Edit point: `scenarios/kundur/config_simulink.py:46` — single line. This is in-allow-list (config file). Phase 4 dual-PHI experiment will tell us whether the residual at t = 10 s is too noisy; if so, raise to 20-30 s.

---

## 6. Updated allow / deny boundary confirmation

**Allow-list unchanged** from plan §2:
- `scenarios/kundur/model_profiles/kundur_cvs_v3.json` (new)
- `scenarios/kundur/config_simulink.py` (extend dispatch + ternaries + possibly T_WARMUP)
- `env/simulink/kundur_simulink_env.py` (extend apply_disturbance branch predicate)
- `probes/kundur/v3_dryrun/probe_5ep_smoke.py` (new)
- `results/harness/kundur/cvs_v3_phase3/`
- `quality_reports/plans/2026-04-26_kundur_cvs_v3_phase3_plan.md`

**Deny-list confirmed unchanged** but **violated by the BLOCKER**:
- The logger-naming BLOCKER cannot be resolved within the current allow-list.
- User must EITHER expand allow-list to include either `build_kundur_cvs_v3.m` (R1) OR `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m` (R2/R4) OR a new `slx_helpers/vsg_bridge/slx_rename_v3_loggers.m` (R3) — each is a one-time scope expansion for this specific issue.

**P3.0 itself**: 0 edits, fully read-only ✅.

---

## 7. P3.0 deliverable summary

| Question | Answer |
|---|---|
| Files inspected | 6 (model_profile, config_simulink, simulink_bridge, kundur_simulink_env, slx_step_and_read_cvs, train_simulink) |
| P3.1 insertion point | `scenarios/kundur/model_profiles/kundur_cvs_v3.json` (new file, schema-compatible) |
| P3.2 insertion point | `config_simulink.py:127` elif branch + `:210-228` ternary extensions |
| P3.3 insertion point | `kundur_simulink_env.py:699` predicate extension |
| Logger naming decision | **BLOCKER** — needs user choice between R1 / R2 / R3 / R4 (all outside current allow-list) |
| Disturbance routing for first smoke | reuse v2 CVS Pm-step mechanism unchanged; richer types deferred to Phase 4 |
| Warmup risk assessment | recommend P3.3b option (c): T_WARMUP = 10 s; final decision in P3.3b doc |
| P3.3b required before P3.4 | YES (per user amendment) |
| Allow / deny boundary | unchanged on paper, but logger BLOCKER demands a one-time scope expansion |

---

## 8. Files emitted in P3.0

```
results/harness/kundur/cvs_v3_phase3/phase3_p30_audit_verdict.md   (this file — read-only audit)
quality_reports/plans/2026-04-26_kundur_cvs_v3_phase3_plan.md       (modified to add P3.3b gate before P3.4)
```

No code, model, profile, env, bridge, SAC, reward, or training files touched.

---

## 9. Halt — request user decision on three items

1. **Approve the BLOCKER resolution**: choose one of R1 (build rename) / R2 (helper template) / R3 (rename hook) / R4 (helper fallback). My recommendation is **R1** for cleanliness, **R4** for minimum scope creep.
2. **Approve P3.3b warmup recommendation**: T_WARMUP = 10 s as the allow-list-compliant minimum-overhead choice, OR pick (a) 30 s / (b) 3 s residual / (d) build-edit IC inject.
3. **GO for P3.1** (write v3 profile JSON) once items 1–2 above are decided. Note: P3.1 is itself safe even before BLOCKER resolution — the profile JSON only describes the model, doesn't run it.
