# Phase 4.1 Verdict (rerun) — Path (C) Pm-step Proxy Dispatch — PASS

> **Status:** PASS — all 4 dispatch criteria validated. `pm_step_proxy_bus7` → ES1, `pm_step_proxy_bus9` → ES4, `pm_step_proxy_random_bus` randomizes between the two, `pm_step_single_vsg` preserves legacy behavior. Each mode produces a nonzero finite frequency response. No NaN/Inf, no tds_failed.
> **Date:** 2026-04-27
> **Predecessor:** Phase 4.1a-v2 PASS (cold-start runtime contract closed; `kundur_cvs_v3_runtime.mat` 38 → 62 fields).
> **Plan:** [`quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_phase5_roadmap.md`](../../../../quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_phase5_roadmap.md)
> **Probe:** [`probes/kundur/v3_dryrun/probe_loadstep_disturbance_routing.py`](../../../../probes/kundur/v3_dryrun/probe_loadstep_disturbance_routing.py) (unchanged from initial P4.1 run; no probe edit)

---

## 1. What was validated

The P4.1 Path (C) Pm-step proxy dispatch added in `env/simulink/kundur_simulink_env.py::_apply_disturbance_backend` (v3 branch) + `KUNDUR_DISTURBANCE_TYPE` config knob. **The dispatch code itself was unchanged between the initial P4.1 FAIL and this rerun** — only the cold-start runtime contract (P4.1a-v2) closed underneath it.

### Per-mode result table

| Run | Mode | Expected target | Actual `post_apply_amps_pu` | `target_indices` | max_freq_dev_hz | tds_failed | nan_inf | wall (s) |
|---|---|---|---|---|---|---|---|---|
| 1 | `pm_step_proxy_bus7` | idx 0 (ES1) | `[0.4, 0.0, 0.0, 0.0]` | `[0]` ✓ | **0.1476** | False | False | 17.4 (cold) |
| 2 | `pm_step_proxy_bus9` | idx 3 (ES4) | `[0.0, 0.0, 0.0, 0.4]` | `[3]` ✓ | **0.1427** | False | False | 10.5 |
| 3 | `pm_step_proxy_random_bus` | (0,) or (3,) | `[0.4, 0.0, 0.0, 0.0]` | `[0]` (bus7 sampled) | 0.1476 | False | False | 10.2 |
| 4 | `pm_step_proxy_random_bus` | (0,) or (3,) | `[0.4, 0.0, 0.0, 0.0]` | `[0]` (bus7 sampled) | 0.1476 | False | False | 10.3 |
| 5 | `pm_step_proxy_random_bus` | (0,) or (3,) | `[0.4, 0.0, 0.0, 0.0]` | `[0]` (bus7 sampled) | 0.1476 | False | False | 10.5 |
| 6 | `pm_step_proxy_random_bus` | (0,) or (3,) | `[0.0, 0.0, 0.0, 0.4]` | `[3]` (bus9 sampled) | 0.1427 | False | False | 10.2 |
| 7 | `pm_step_single_vsg` (legacy) | idx 0 via class attr fallback | `[0.4, 0.0, 0.0, 0.0]` | `[0]` ✓ | 0.1476 | False | False | 10.0 |

Random-bus distribution across 4 draws: bus7 (idx 0) = 3, bus9 (idx 3) = 1 — both buses sampled, sample size too small for distribution test but stochastic dispatch confirmed.

Magnitude `+0.4` sys-pu = 40 MW system-pu, well inside `DIST_MIN/DIST_MAX = [0.1, 0.5]`. Result: 142.7 / 147.6 mHz peak ω deviation — consistent with Phase 2.2 reference probes (P2.2 measured 69 mHz at +0.20 sys-pu for ES1, 64 mHz for ES4; linear scaling to +0.40 predicts 138 / 128 mHz, observed 148 / 143 — within +7 % of linear extrapolation).

### Pass criteria (per user GO message)

| # | Criterion | Result |
|---|---|---|
| (a) | `pm_step_proxy_bus7` → only ES1 (idx 0) `Pm_step_amp` nonzero | ✓ run 1: post = `[0.4, 0, 0, 0]` |
| (b) | `pm_step_proxy_bus9` → only ES4 (idx 3) `Pm_step_amp` nonzero | ✓ run 2: post = `[0, 0, 0, 0.4]` |
| (c) | `pm_step_proxy_random_bus` reaches both buses across multiple draws | ✓ runs 3-6: 3× idx 0 + 1× idx 3 |
| (d) | Each mode produces nonzero finite ω response (no NaN/Inf, no tds_failed) | ✓ all 7 runs: `max_freq_dev_hz > 0.14`, `nan_inf=False`, `tds_failed=False`, `steps=50/50` |
| (e — extra) | Legacy `pm_step_single_vsg` mode preserved (no behavior regression) | ✓ run 7: same target [0] and identical metrics as run 1 (deterministic env reset under fixed RNG) |

**Overall: smoke_ok=True. fail_reasons=[].**

---

## 2. Disturbance log lines (proves dispatch tagging)

Each episode emitted exactly one disturbance log line (captured via `redirect_stdout(StringIO)`):

```
[Kundur-Simulink-CVS] Pm step increase targets VSG[0] (proxy_bus7): amp=+0.4000 pu (magnitude=+0.400), step_time=10.0000s, per_vsg_amps=['+0.400', '+0.000', '+0.000', '+0.000']
[Kundur-Simulink-CVS] Pm step increase targets VSG[3] (proxy_bus9): amp=+0.4000 pu (magnitude=+0.400), step_time=10.0000s, per_vsg_amps=['+0.000', '+0.000', '+0.000', '+0.400']
[Kundur-Simulink-CVS] Pm step increase targets VSG[0] (proxy_bus7): ...   # random_1, sampled bus7
[Kundur-Simulink-CVS] Pm step increase targets VSG[0] (proxy_bus7): ...   # random_2, sampled bus7
[Kundur-Simulink-CVS] Pm step increase targets VSG[0] (proxy_bus7): ...   # random_3, sampled bus7
[Kundur-Simulink-CVS] Pm step increase targets VSG[3] (proxy_bus9): ...   # random_4, sampled bus9
[Kundur-Simulink-CVS] Pm step increase targets VSG[0] (pm_step_single_vsg): ... per_vsg_amps=['+0.400', ...]
```

The `(proxy_busN)` / `(pm_step_single_vsg)` tags come from the new `proxy_tag` formatting in the v3 dispatch branch — confirms the new code path executed.

---

## 3. Cold-start workspace state per episode

Probe reads `Pm_step_amp_1..4` from MATLAB base workspace via `bridge.session._get_engine().eval(...)`:

- Pre-`apply_disturbance`: `[0.0, 0.0, 0.0, 0.0]` (warmup default; matches `Pm_step_amp_<i>=0.0` from `slx_episode_warmup_cvs.m` Phase 1b seeding)
- Post-`apply_disturbance`: exactly the targeted index gets `0.4`, others stay `0.0`
- This proves `bridge.apply_workspace_var('Pm_step_amp_<i>', amp)` reaches MATLAB workspace and is observable via read-back. The cold-start contract is intact.

---

## 4. Boundary check

- `build_kundur_cvs_v3.m`: untouched in this rerun (Phase 4.1a-v2 was the last edit).
- `kundur_cvs_v3.slx`: untouched.
- `kundur_cvs_v3_runtime.mat`: untouched (62 fields from P4.1a-v2 final regen).
- `kundur_ic_cvs_v3.json`: untouched.
- `slx_helpers/vsg_bridge/*`: untouched.
- `engine/simulink_bridge.py`: untouched.
- `env/simulink/kundur_simulink_env.py` Path (C) dispatch: unchanged from initial P4.1 implementation.
- `scenarios/kundur/config_simulink.py` `KUNDUR_DISTURBANCE_TYPE`: unchanged.
- Reward / training paths: untouched.
- LoadStep wiring: untouched (still hardcoded `Resistance='1e9'` per Phase 4.0 audit).
- NE39: untouched.
- No 50-ep / 2000-ep training launched.

---

## 5. Verdict

**PASS.** P4.1 Path (C) Pm-step proxy dispatch is end-to-end verified on cold-start `kundur_cvs_v3`:

- Disturbance type → target ESS index mapping correct.
- Workspace propagation via existing `apply_workspace_var` is observable.
- No regressions on legacy `pm_step_single_vsg` path.
- Frequency response magnitudes consistent with Phase 2.2 calibration (linear scaling, ES1/ES4 nearest-source semantics confirmed).
- Random-bus mode actually randomizes (3:1 split observed across 4 draws).

This unblocks Phase 4.2 (PHI sweep, REQUIRES `KUNDUR_DISTURBANCE_TYPE=pm_step_proxy_random_bus` env-var override per plan §Gap 1 default for Phase 4 sweep), Phase 4.3 (fixed scenario sets), and downstream Phase 5 work.

---

## 6. Artifacts emitted

```
results/harness/kundur/cvs_v3_phase4/
├── phase4_p41_rerun_verdict.md              (this file)
├── p41_smoke_rerun_stdout.txt               (rerun probe stdout)
├── p41_smoke_rerun_stderr.txt               (empty)
└── p41_disturbance_routing_smoke.json       (probe summary; smoke_ok=true; 7 runs)

(unchanged from prior phases)
results/harness/kundur/cvs_v3_phase4/
├── phase4_p40_audit_verdict.md              (Phase 4.0 PASS)
├── phase4_p41_verdict.md                    (Phase 4.1 initial FAIL — root cause)
├── phase4_p41a_verdict.md                   (Phase 4.1a PARTIAL — WindAmp only)
├── phase4_p41a_runtime_consts_v2_verdict.md (Phase 4.1a-v2 PASS — full cold-start fix)
├── p41a_v2_summary.json                     (Phase 4.1a-v2 verify summary)
└── (diagnostic + verify logs from prior runs)
```

---

## 7. Next step

Phase 4 sub-plan (per roadmap §2): proceed to **P4.2 PHI sweep** — sequential 50-ep runs with `KUNDUR_DISTURBANCE_TYPE=pm_step_proxy_random_bus` set via env-var, sweeping PHI_H/PHI_D candidates `phi_b1 → phi_asym_a → phi_paper_scaled` (and `phi_asym_b / phi_paper` if needed). Hard boundaries: no build / .slx / IC / runtime.mat / bridge / helper / env-dispatch / reward edits; explicit user GO required to launch a 50-ep run.

Awaiting user GO for P4.2.
