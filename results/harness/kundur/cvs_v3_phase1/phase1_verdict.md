# Phase 1 Verdict — Kundur CVS v3 (Phase 1.1 + Phase 1.3)

> **Status: PASS — proceed to Phase 2 on user GO.**
> **Date:** 2026-04-26
> **Spec:** [`quality_reports/plans/2026-04-26_cvs_v3_topology_spec.md`](../../../../quality_reports/plans/2026-04-26_cvs_v3_topology_spec.md)
> **Plan:** [`quality_reports/plans/2026-04-26_kundur_cvs_v3_plan.md`](../../../../quality_reports/plans/2026-04-26_kundur_cvs_v3_plan.md)
> **Phase 1.1 detail verdict:** [`phase1_1_verdict.md`](phase1_1_verdict.md)

---

## 1. Phase 1.1 (NR) — recap

All 5 NR gates PASS. Outer-loop converged 8 iters; G1 actual injection equals paper 7.000 sys-pu (residual 8.8 e-10). **No hidden slack.** ESS group derived dispatch −0.3691 sys-pu/source (−36.91 MW each, −0.1845 vsg-pu). Loss 1.37 % of |load|. See `phase1_1_verdict.md` for full table.

---

## 2. Phase 1.3 (build) — gates

| Gate | Got | Want | ✅ |
|---|---|---|---|
| Build script ok | `build_kundur_cvs_v3.m` runs to completion | 0 errors | ✅ |
| `.slx` saved      | `scenarios/kundur/simulink_models/kundur_cvs_v3.slx` | yes | ✅ |
| Runtime `.mat` saved | `kundur_cvs_v3_runtime.mat` (38 fields) | yes | ✅ |
| Compile (model update) | 0 errors / 0 warnings | 0 / 0 | ✅ |
| Smoke `sim(StopTime=0.5)` | reaches 0.5 s, 0 errs / 0 warns | reach 0.5 s no crash | ✅ |
| Simscape constraint violation | not detected | none | ✅ |
| NaN / Inf / clip in 0.5 s window | none observed | none | ✅ |
| Build wall time (incl. powerlib load) | 9.9 s | < 30 s informational | ✅ |
| Smoke wall time | 1.35 s | informational | ✅ |

---

## 3. Build inventory

| Component | Count | Notes |
|---|---|---|
| Series RLC branches (lines) | 20 | Spec §8 narrative said 18; correct count is 20 — 5 single std + 4 parallels (2+2+3+2+2 = 11) + 5 short = 5+15 = 20. Spec §4 table is consistent with 20. |
| Constant-Z loads (R+L) | 2 | Bus 7, Bus 9 |
| Shunt caps (C) | 2 | Bus 7 (200 Mvar), Bus 9 (350 Mvar) |
| LoadStep R-only branches | 2 | Bus 7, Bus 9 — default disabled (R = 1 e9 Ω). Phase 3 env will modulate `G_perturb_k_S` ws var. |
| Dynamic source CVS clusters (swing-eq) | 7 | G1, G2, G3 (with governor droop) + ES1..4 |
| Wind PVS (`AC Voltage Source`) | 2 | W1 @ Bus 4, W2 @ Bus 11 |
| Pm-step gating clusters | 7 | one per dynamic source (default amp = 0) |
| ToWorkspace loggers | 21 | 3 per source × 7 sources (omega, delta, Pe), `MaxDataPoints=2` |
| Global Clock | 1 | feeds Pm-step gates |
| Phasor powergui | 1 | 50 Hz, ode23t, MaxStep 5 ms, StopTime 0.5 s |

---

## 4. CVS Amplitude source — Phase 1.1 observation honoured

| Source | CVS Amplitude (V) | From IC field | NOT hardcoded? |
|---|---|---|---|
| G1 | 266 773 | `sg_emf_mag_pu(1) * Vbase` = 1.1599 × 230 kV | ✅ |
| G2 | 256 052 | `sg_emf_mag_pu(2) * Vbase` = 1.1128 × 230 kV | ✅ |
| G3 | 266 439 | `sg_emf_mag_pu(3) * Vbase` = 1.1584 × 230 kV | ✅ |
| ES1 | 193 224 | `vsg_emf_mag_pu(1) * Vbase` = 0.8401 × 230 kV | ✅ |
| ES2 | 225 764 | `vsg_emf_mag_pu(2) * Vbase` = 0.9816 × 230 kV | ✅ |
| ES3 | 165 948 | `vsg_emf_mag_pu(3) * Vbase` = 0.7215 × 230 kV — note ES3 obs from Phase 1.1 | ✅ |
| ES4 | 224 194 | `vsg_emf_mag_pu(4) * Vbase` = 0.9748 × 230 kV | ✅ |
| W1 | 230 000 × WindAmp_1 | `wind_terminal_voltage_mag_pu(1) * Vbase` × 1.0 | ✅ |
| W2 | 230 000 × WindAmp_2 | `wind_terminal_voltage_mag_pu(2) * Vbase` × 1.0 | ✅ |

ES3 amplitude 0.72 pu is the Phase 1.1 observation made flesh — Q absorption ~188 Mvar at Bus 14 region. Build accepts it as-is per user instruction.

---

## 5. Smoke state snapshot at t = 0.5 s

| Source | ω (pu) | δ (rad) | Pe (sys-pu) | δ NR target (rad) |
|---|---|---|---|---|
| G1  | +1.003097 | +1.069242 | +9.4607 | 0.5221 |
| G2  | +1.002342 | +0.966726 | +8.5825 | 0.4762 |
| G3  | +0.991202 | +0.439646 | +8.0979 | 0.3378 |
| ES1 | +0.994153 | +0.252244 | −1.8430 | 0.1953 |
| ES2 | +0.999982 | +0.025141 | −0.3825 | 0.0250 |
| ES3 | +1.002475 | +0.159685 | −0.1072 | 0.1949 |
| ES4 | +1.000370 | +0.009900 | −0.5932 | 0.0089 |

Bounds:
- ω ∈ [0.991, 1.003] — well inside ±5 % IntW soft band; no clip.
- |δ| ≤ 1.069 rad (61.2 °) — inside `(−π/2, π/2)` IntD-safe band of ±84.7 °.
- Pe spread reflects transient: SG Pe overshoot ~1.13–1.35× Pm, ESS Pe wide vs NR steady. **Expected** — Phasor solver settles inductor currents over L/R (~5–10 ms) and swing-eq settles over 1/(2π·D/M) ~ seconds. 0.5 s is too short for steady; Phase 2.1 (30 s zero-action) will measure settling.

---

## 6. Boundary-respect audit (cumulative Phase 1.1 + Phase 1.3)

| Boundary | Status |
|---|---|
| v2 files (`kundur_cvs.slx`, `kundur_ic_cvs.json`, `build_kundur_cvs.m`, `compute_kundur_cvs_powerflow.m`, `model_profiles/kundur_cvs.json`) | **untouched** |
| NE39 (`scenarios/new_england/`) | **untouched** |
| SAC (`agents/`) | **untouched** |
| Shared bridge (`engine/simulink_bridge.py`) | **untouched** |
| Env (`env/simulink/kundur_simulink_env.py`) | **untouched** |
| Profile (`scenarios/kundur/model_profiles/*.json`) | **untouched** |
| Training config (`scenarios/kundur/config_simulink.py`) | **untouched** |
| Profile schema | **untouched** |
| Training started | **no** |

---

## 7. Files emitted (Phase 1.1 + Phase 1.3 cumulative)

```
scenarios/kundur/matlab_scripts/compute_kundur_cvs_v3_powerflow.m   (new)
scenarios/kundur/kundur_ic_cvs_v3.json                              (new, schema_version=3)
scenarios/kundur/simulink_models/build_kundur_cvs_v3.m              (new)
scenarios/kundur/simulink_models/kundur_cvs_v3.slx                  (new, build output)
scenarios/kundur/simulink_models/kundur_cvs_v3_runtime.mat          (new, build output)
results/harness/kundur/cvs_v3_phase1/nr_summary.json                (Phase 1.1)
results/harness/kundur/cvs_v3_phase1/phase1_1_verdict.md            (Phase 1.1)
results/harness/kundur/cvs_v3_phase1/build_summary.json             (Phase 1.3)
results/harness/kundur/cvs_v3_phase1/phase1_verdict.md              (Phase 1, this file)
```

---

## 8. Decision gate → Phase 2

All Phase 1 PASS criteria from spec §10 met:
- NR converged AND `max_mismatch_pu < 1 e-10` ✅
- `closure_ok = true` ✅
- `total_loss_pu ∈ [0.01, 0.03]` (0.0137) ✅
- `|P_ES_each| ∈ [0.20, 0.4625]` sys-pu (0.3691) ✅
- `no_hidden_slack = true` ✅
- `.slx` builds AND `sim()` runs StopTime = 0.5 s without crash ✅

**STOP for user GO before Phase 2** (dry-run physics probes — 30 s zero-action stability, per-source Pm-step reach, Bus 7 / Bus 9 load step, W2 trip, H/D sensitivity, ODE oracle cross-check).

If user wants to revise dispatch / IC / Vmag / line model before Phase 2 (e.g. relieve ES3 Q burden by lowering ESS V_spec), now is the moment. Otherwise Phase 2 will use the .slx as built.
