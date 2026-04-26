# Phase 3.0b + 3.0c Verdict — Logger Interface Rename + Readout Sanity

> **Status: PASS — v3 .slx logger names now match the shared CVS helper contract; bridge round-trip returns non-empty finite state.**
> **Date:** 2026-04-26
> **Plan amendments:** P3.3b warmup gate added before P3.4 (per user); T_WARMUP = 10 s **smoke-stage only** approved (NOT a permanent 2000-ep training decision).

---

## 1. Resolution chosen — R1 (build-side rename, interface-only)

Per user decision, the BLOCKER discovered in P3.0 is resolved by aligning v3 build output names to the existing CVS helper contract — **without** editing the helper, the bridge config, or adding fallback logic.

### Edit summary

[`scenarios/kundur/simulink_models/build_kundur_cvs_v3.m:599-636`](../../../../scenarios/kundur/simulink_models/build_kundur_cvs_v3.m): the per-source ToWorkspace logger block now selects its `VariableName` based on source type:

```matlab
if strcmp(stype, 'ess')
    ess_idx = sscanf(sname, 'ES%d');
    var_omega = sprintf('omega_ts_%d', ess_idx);   % matches helper %d format
    var_delta = sprintf('delta_ts_%d', ess_idx);
    var_pe    = sprintf('Pe_ts_%d',    ess_idx);
else
    var_omega = sprintf('omega_ts_%s', sname);     % SG diagnostic (G1..G3)
    var_delta = sprintf('delta_ts_%s', sname);
    var_pe    = sprintf('Pe_ts_%s',    sname);
end
```

ESS (consumed by the helper) → integer suffix `1..4`; SG (diagnostic only, helper does not read) → string suffix `G1..G3` preserved. **Block paths** `W_omega_<sname>` etc. retain the descriptive suffix for in-model readability — only the `VariableName` field (which controls `simOut.get(...)` access) changes.

### Scope statement

This is a **logger / interface naming change only**. Verified untouched in this iteration:

| Untouched | Status |
|---|---|
| Topology (16 buses, 20 lines, 7 sources, 2 PVS, 2 LoadStep, 2 loads, 2 shunts) | ✅ |
| IC (`kundur_ic_cvs_v3.json`) | ✅ untouched since Phase 1 commit `a40adc5` |
| NR (`compute_kundur_cvs_v3_powerflow.m`) | ✅ untouched |
| Dispatch / V_spec / line per-km params / disturbance physics | ✅ |
| Shared bridge (`engine/simulink_bridge.py`) | ✅ |
| Shared helper (`slx_helpers/vsg_bridge/slx_step_and_read_cvs.m`) | ✅ |
| Profile hyperparameters / env / SAC / reward / training | ✅ |
| v2 / NE39 | ✅ |

Build itself was rebuilt as a side effect of the rename (necessary to write the new `VariableName` strings into the .slx). Compile diagnostics PASS (0 errors / 0 warnings).

---

## 2. P3.0c readout sanity probe — exact helper signature exercised

[`probes/kundur/v3_dryrun/probe_logger_readout_sanity.m`](../../../../probes/kundur/v3_dryrun/probe_logger_readout_sanity.m) — runs a 0.5 s sim of `kundur_cvs_v3` then performs four tier checks:

| Tier | Check | Result |
|---|---|---|
| 1 | `simOut.get('omega_ts_<int>')` / `delta_ts_<int>` / `Pe_ts_<int>` for int ∈ {1,2,3,4}: present + finite | 12/12 ✅ |
| 2 | `simOut.get('omega_ts_<sname>')` for sname ∈ {G1, G2, G3} (diagnostic loggers): present + finite | 9/9 ✅ |
| 3 | Legacy `omega_ts_ES<int>` MUST be absent (proves rename worked) | 0/4 present ✅ |
| 4 | `[state, status] = slx_step_and_read_cvs(mdl, 1:4, M, D, t, sbase, cfg, ...)` — actual helper round-trip: returns non-empty finite non-zero ω/Pe/δ for all 4 ESS | success ✅ |

Round-trip helper output at t = 1 s:

```
omega = [+0.996905  +0.999970  +1.000765  +1.000076]   pu
Pe    = [+0.099983  -0.367634  -0.067018  -0.581117]   sys-pu
delta = [+0.552481  +0.027029  +0.156213  +0.009731]   rad
```

ω all in [0.997, 1.001] (Phasor-solver mid-transient at t = 1 s, consistent with Phase 2 inductor-IC kick window); Pe / δ all finite non-zero. Helper now correctly extracts state from the renamed loggers. The pre-fix failure mode (helper returns all-zero state because `simOut.get('omega_ts_1')` returned empty when build emitted `omega_ts_ES1`) is closed.

**ALL_PASS = 1.**

---

## 3. Side effect: existing Phase 2 probes need refresh on next invocation

The 6 Phase 2 probes (`probe_30s_zero_action.m`, `probe_pm_step_reach.m`, `probe_loadstep_reach.m`, `probe_wind_trip_reach.m`, `probe_hd_sensitivity.m`, `probe_d_*_decay.m`) all access ESS loggers as `simOut.get(['omega_ts_' s])` where `s` ∈ `{'ES1', 'ES2', 'ES3', 'ES4'}`. After the rename these calls would return empty (or throw, depending on Simulink version).

**Action: NONE** for Phase 2 probes (their committed JSON / verdict outputs remain valid as historical evidence of the pre-rename model). When/if any Phase 2 probe is re-run in a future session it must be updated to use integer suffix for ESS — that's a separate scope and is NOT part of P3.0b/c.

---

## 4. P3.3b smoke-stage warmup decision — APPROVED

User approval recorded: **`T_WARMUP = 10 s` is approved for the Phase 3 smoke (P3.4) stage only.**

**Not** a permanent 2000-episode training decision. Phase 4 / Phase 5 may revisit:
- Empirical: if 50-ep gate r_f signal shape under T_WARMUP=10 s is acceptable, keep it.
- If residual (~ 0.5 mHz at t = 10 s per Phase 2 trajectory) contaminates r_f signal under PHI_F = 100 amplification, raise to 20–30 s (cost: 2 – 4 hr extra wall on 2000-ep training).
- Alternative permanent solution (post-Phase-4): inductor IC pre-loading via NR-derived currents (build edit, scope expansion needed).

For the smoke-stage value, the edit point is `scenarios/kundur/config_simulink.py:46` (the existing `T_WARMUP = 3.0` Kundur override → `T_WARMUP = 10.0`). Edit deferred to P3.2/P3.3 when other config-side edits are made.

---

## 5. Boundary respected (cumulative since P3.0 audit)

| Item | Status |
|---|---|
| `compute_kundur_cvs_v3_powerflow.m` / `kundur_ic_cvs_v3.json` | **untouched** since Phase 1 commit `a40adc5` |
| `build_kundur_cvs_v3.m` | **edited (interface only)**: ESS logger `VariableName` → integer suffix |
| `kundur_cvs_v3.slx` / `_runtime.mat` | **rebuilt** (necessary side effect of rename) |
| `engine/simulink_bridge.py` | **untouched** |
| `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m` | **untouched** |
| `env/simulink/kundur_simulink_env.py` | **untouched** |
| `scenarios/kundur/model_profiles/*.json` | **untouched** |
| `scenarios/kundur/config_simulink.py` | **untouched** (T_WARMUP edit deferred to P3.2/P3.3) |
| `agents/`, `scenarios/contract.py`, training scripts | **untouched** |
| v2 / NE39 | **untouched** |
| Topology / IC / NR / dispatch / V_spec / line per-km params / disturbance physics | **untouched** |

Files emitted in this iteration:
```
scenarios/kundur/simulink_models/build_kundur_cvs_v3.m         (modified — interface rename only)
scenarios/kundur/simulink_models/kundur_cvs_v3.slx             (rebuilt)
scenarios/kundur/simulink_models/kundur_cvs_v3_runtime.mat     (rebuilt — same 38 fields)
probes/kundur/v3_dryrun/probe_logger_readout_sanity.m          (new — P3.0c sanity probe)
results/harness/kundur/cvs_v3_phase3/p30c_logger_readout_sanity.json  (new — sanity output)
results/harness/kundur/cvs_v3_phase3/phase3_p30bc_verdict.md   (this file)
```

---

## 6. Halt — request user GO for P3.1

P3.0b interface rename + P3.0c readout sanity both PASS. v3 model is now bridge-helper-compatible. P3.3b warmup decision approved (`T_WARMUP = 10 s` for smoke).

**Awaiting GO for P3.1** (write `scenarios/kundur/model_profiles/kundur_cvs_v3.json`).

P3.1 is a single new JSON file with no code dependencies; safe to proceed when authorized.
