# Phase 1.1 Verdict — Kundur CVS v3 NR (lossy 16-bus)

> **Status: PASS — proceed to Phase 1.3 (build .slx) on user GO.**
> **Date:** 2026-04-26
> **Spec:** [`quality_reports/plans/2026-04-26_cvs_v3_topology_spec.md`](../../../../quality_reports/plans/2026-04-26_cvs_v3_topology_spec.md)
> **Plan:** [`quality_reports/plans/2026-04-26_kundur_cvs_v3_plan.md`](../../../../quality_reports/plans/2026-04-26_kundur_cvs_v3_plan.md)

---

## 1. NR convergence

| Metric | Value | Gate | Pass |
|---|---|---|---|
| Outer converged | true | true | ✅ |
| Outer iterations | 8 | ≤ 30 | ✅ |
| Inner iterations (total) | 40 | < 60·30 | ✅ |
| Inner max mismatch (pu) | 9.131 e-13 | < 1 e-10 | ✅ |
| G1 residual (pu) | 8.825 e-10 | < 1 e-9 (no hidden slack) | ✅ |
| Closure aggregate residual (pu) | 8.822 e-10 | < 1 e-3 | ✅ |
| ESS per-bus dispatch dev (pu) | 3.519 e-13 | < 1 e-10 | ✅ |

Outer loop = G1-as-numerical-slack + ESS-distributed-residual. After 8 outer iters G1 actual injection equals paper P0_G1 = 7.000 sys-pu within 9 e-10 pu. **No bus carries hidden slack.**

---

## 2. Global active-power balance (sys-pu, 100 MVA base)

| Term | Value | Source |
|---|---|---|
| ΣP_gen_paper (G1 + G2 + G3) | +21.19 | paper-fixed |
| ΣP_wind_paper (W1 + W2)    |  +8.00 | paper-fixed |
| ΣP_load (Bus 7 + Bus 9)    | −27.34 | paper-fixed |
| ΣP_ESS (4 × derived)       |  −1.476 | NR derived |
| P_loss (Π-line lossy)      |  +0.3736 | NR derived |
| **Identity check** | `ΣP_gen + ΣP_wind + ΣP_ESS + ΣP_load = P_loss` | residual 8.8 e-10 ✓ |

**Loss = 1.37 % of |load|** ⇒ inside spec §9 R2 sanity band [1.0 %, 3.0 %]. ✅

---

## 3. Derived ESS dispatch

| Metric | Value | Spec band §3.1 | In-band |
|---|---|---|---|
| `P_ES_each` (sys-pu)   | −0.3691 | [−0.4625, −0.20] | ✅ |
| `P_ES_each` (MW)       | −36.91  | [−46.25, −20]    | ✅ |
| `P_ES_each` (vsg-pu)   | −0.1845 | [−0.2313, −0.10] | ✅ |
| Sign convention        | Pm < 0 = ESS absorbs / charges | locked §3.1 | ✅ |

ESS group absorbs 147.6 MW at steady state — consistent with paper-faithful gen (2919 MW) > load (2734 MW) surplus minus 37.4 MW loss = 147.6 MW.

---

## 4. Bus voltage / angle ranges (NR result)

| Quantity | Min | Max |
|---|---|---|
| `|V|` (pu)             | 1.0000 (PQ buses) | 1.0300 (Bus 1, G1 V_spec) |
| Angle (PF-relative, deg) | −16.60 (Bus 9_load) | 0.00 (Bus 1, ref) |
| Angle (sim absolute, deg) | +3.40 | +20.00 |

PQ bus voltages basically pinned to 1.000 — Q net at load buses (+1.0 / +2.5 sys-pu cap surplus) holds them. No voltage collapse risk.

---

## 5. Dynamic-source δ₀ ranges (internal EMF, sim absolute frame)

| Source | Bus | δ₀ (deg) | |V_emf| (pu) | P_inj (sys-pu) |
|---|---|---|---|---|
| G1  | 1  | +29.92 | 1.160 | +7.000 |
| G2  | 2  | +27.28 | 1.113 | +7.000 |
| G3  | 3  | +19.36 | 1.158 | +7.190 |
| ES1 | 12 | +11.19 | 0.840 | −0.369 |
| ES2 | 16 |  +1.43 | 0.982 | −0.369 |
| ES3 | 14 | +11.16 | 0.722 | −0.369 |
| ES4 | 15 |  +0.51 | 0.975 | −0.369 |

Wind farms (no swing-eq):
- W1 @ Bus 4  : V_term = 1.000 ∠ +5.11°
- W2 @ Bus 11 : V_term = 1.000 ∠ +4.48°

δ₀ spread 0.51 ° → 29.92 ° (29.4 ° total). All within `(−π/2, π/2)` IntD-safe band ([−85 °, 85 °]). ✅

---

## 6. Observations to carry into Phase 1.3 / Phase 2

1. **ES3 |V_emf| = 0.72 pu ⇒ Q absorption ~188 Mvar** (94 % of 200 MVA nameplate). Bus 10 corner has tight Q balance because G3 is the only nearby +Q source and Bus 9 has 250 Mvar net cap surplus. **Build script Phase 1.3 must source CVS Amplitude from `vsg_emf_mag_pu` field, NOT hardcode 1.0** (this is different from v2, where the ESS V_emf was near 1.0 and the build worked with `Vmag_i = 1·Vbase`).
2. All 4 ESS |V_emf| ∈ [0.72, 0.98] — confirms steady-state absorption mode. Visualises the dispatch decision Q1 = (a) physically.
3. NR uses constant-PQ; Simulink build uses constant-Z. Load-bus V = 1.0003 (Bus 7), 1.0000 (Bus 9) ⇒ V² effect is < 1 e-4 pu, well inside closure tolerance 1 e-3. v2-style closure handling carries over.
4. Outer-loop relaxation factor δ/4 (i.e. equal split of G1 deviation) gave 8-iter convergence. Under-relaxation not needed.

---

## 7. Boundary-respect audit

| Boundary | Status |
|---|---|
| v2 files (kundur_cvs.slx, kundur_ic_cvs.json, build_kundur_cvs.m, compute_kundur_cvs_powerflow.m, model_profiles/kundur_cvs.json) | **untouched** |
| NE39 files (`scenarios/new_england/`)                  | **untouched** |
| SAC code (`agents/`)                                    | **untouched** |
| Shared bridge (`engine/simulink_bridge.py`)            | **untouched** |
| Env (`env/simulink/kundur_simulink_env.py`)            | **untouched** |
| Profile schema (`scenarios/kundur/model_profiles/schema.json`) | **untouched** |
| Training config (`scenarios/kundur/config_simulink.py`) | **untouched** |
| Simulink models / library load                         | **none** (Phase 1.1 has no .slx work) |

Phase 1 file allow-list (spec §8) honoured: only the new v3 NR script + IC JSON + Phase 1.1 verdict / summary written.

---

## 8. Files emitted

```
scenarios/kundur/matlab_scripts/compute_kundur_cvs_v3_powerflow.m   (new, ~430 lines)
scenarios/kundur/kundur_ic_cvs_v3.json                              (new, schema_version=3)
results/harness/kundur/cvs_v3_phase1/nr_summary.json                (this report's machine view)
results/harness/kundur/cvs_v3_phase1/phase1_1_verdict.md            (this file)
```

Plus the prior spec edits (band correction, R1/R2 wording).

---

## 9. Decision gate → Phase 1.3

All Phase 1.1 PASS criteria from spec §10 met:
- NR converged AND `max_mismatch_pu < 1e-10` ✅
- `closure_ok = true` ✅
- `total_loss_pu ∈ [0.01, 0.03]` (0.0137) ✅
- `|P_ES_each| ∈ [0.20, 0.4625]` sys-pu (0.3691) ✅
- `no_hidden_slack = true` (G1_residual 8.8 e-10) ✅

**STOP for user GO before Phase 1.3** (`build_kundur_cvs_v3.m` — write 16-bus
.slx with 7 swing-eq closures, 2 PVS, 18 lines, 2 LoadStep clusters,
7 Pm-step clusters, Phasor solver + ToWorkspace loggers).

If user wants to revisit Q1/Q2 or revise dispatch convention before Phase 1.3
(e.g. lower ESS V_spec from 1.0 to 0.99 to relieve ES3 Q burden), this is the
moment.
