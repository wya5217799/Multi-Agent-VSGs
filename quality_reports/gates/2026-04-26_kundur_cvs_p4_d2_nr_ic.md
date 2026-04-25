# Stage 2 Day 2 — Kundur CVS Newton-Raphson IC Verdict

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg`
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** GATE — D2 NR IC validation (Pm/Pe consistency + zero-action 0.5 s)
**Predecessors:**
- Stage 2 plan §1 D2 + §3 — `quality_reports/gates/2026-04-25_kundur_cvs_stage2_readiness_plan.md`
- D1 verdict — `quality_reports/gates/2026-04-26_kundur_cvs_p4_d1_topology.md`
- Engineering contract — `docs/design/cvs_design.md`
- Legacy NR (untouched) — `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m`

---

## Verdict: PASS

All 4 IC validation indicators green at 0.5 s zero-action sim with NR-derived
initial condition. Plan §3 strict thresholds met, with zero drift.

---

## Artifacts

| File | Role | SHA-256 |
|---|---|---|
| `scenarios/kundur/matlab_scripts/compute_kundur_cvs_powerflow.m` | NEW — 7-bus NR (PV/PQ/SLACK + load Y-shunt) | `5338ef3b…41541a` |
| `scenarios/kundur/kundur_ic_cvs.json` | NEW — NR IC, plan §3 schema | `4850f784…9d9b0b` |
| `scenarios/kundur/simulink_models/build_kundur_cvs.m` | EVOLVED — added 4-VSG swing-eq closure, reads JSON | (current HEAD) |
| `scenarios/kundur/simulink_models/kundur_cvs.slx` | REBUILT — D2 model with swing-eq | `0a7114de…38194d` |
| `probes/kundur/gates/p4_d2_nr_ic_validate.py` | NEW — 4-indicator gate orchestrator | (current HEAD) |
| `quality_reports/gates/2026-04-26_kundur_cvs_p4_d2_nr_ic.md` | This verdict | — |

Plan §1 D2 禁止项 honored:
- ❌ legacy `compute_kundur_powerflow.m` UNCHANGED
- ❌ `kundur_ic.json` UNCHANGED (new file is `kundur_ic_cvs.json`)
- ❌ NE39 / bridge / `slx_helpers/vsg_bridge/*` / `contract.py::KUNDUR` UNCHANGED
- ❌ no SAC / no RL / no disturbance — only swing-eq closure + zero-action

---

## NR Result

NR converged on a 7-bus polar Newton-Raphson formulation with
constant-impedance loads modelled as Y-shunts (G = P_load_pu = 0.4 each at
Bus_A and Bus_B):

| Iteration | 5 |
|---|---|
| Max mismatch | 3.56e-15 pu |
| Converged | true |

Bus solution:

| Bus | Type | \|V\| (pu) | angle (deg) | P (pu) | Q (pu) |
|---|---|---|---|---|---|
| Bus_V1 | PV | 1.0000 | +16.840 | +0.5000 | +0.0515 |
| Bus_V2 | PV | 1.0000 | +16.840 | +0.5000 | +0.0515 |
| Bus_V3 | PV | 1.0000 |  +6.341 | +0.5000 | +0.0426 |
| Bus_V4 | PV | 1.0000 |  +6.341 | +0.5000 | +0.0426 |
| Bus_A  | PQ | 0.9961 | +13.963 |  0.0000 |  0.0000 |
| Bus_B  | PQ | 0.9970 |  +3.466 |  0.0000 |  0.0000 |
| Bus_INF| SLACK | 1.0000 | 0.000 | -1.2055 | +0.0966 |

Per-VSG IC:

| VSG | δ₀ (rad) | δ₀ (deg) | \|V\| (pu) | Pm₀ (pu) | Pe_target (pu) |
|---|---|---|---|---|---|
| VSG1 | 0.293922 | 16.84 | 1.0 | 0.5 | 0.5 |
| VSG2 | 0.293922 | 16.84 | 1.0 | 0.5 | 0.5 |
| VSG3 | 0.110666 |  6.34 | 1.0 | 0.5 | 0.5 |
| VSG4 | 0.110666 |  6.34 | 1.0 | 0.5 | 0.5 |

Power balance audit: ΣPm = 4 × 0.5 = 2.000 pu; ΣP_load = 0.795 pu;
P_INF (slack absorbed) = 1.205 pu. (2.000 − 0.795 = 1.205 ✓)

---

## D2 Pass Criteria — all PASS

| # | Criterion | Threshold | Result | Verdict |
|---|---|---|---|---|
| 1 | Pe ≈ Pm₀ per agent | \|Pe_tail − Pm₀\| / Pm₀ < 5 % | VSG1..4 Pe_tail = 0.5000 (0.00 % deviation) | PASS |
| 2 | ω ≈ 1 per agent | \|ω_tail_mean − 1\| < 1e-3 | VSG1..4 ω_tail = 1.000000 (dev 0.00e+00) | PASS |
| 3 | IntD margin | \|δ\|_max < π/2 − 0.05 (≈ 1.521 rad) | VSG1/2 \|δ\|max = 0.2939; VSG3/4 \|δ\|max = 0.1107 | PASS |
| 4 | Inter-agent sync | (max ω − min ω) over agents < 1e-3 | spread = 0.000e+00 | PASS |

Tail window = last 0.2 s of a 0.5 s sim (plan §3).
No NaN / Inf / early termination. No `nontunable` warning. Compile + sim
diagnostics: 0 errors / 0 warnings.

---

## Convention fix recorded for future gates

D2 first iteration revealed a **factor-2 mismatch** between NR's per-unit
basis and the Simulink `Pe_scale` formula inherited from P2/P3:

- NR computes `P_pu = V_pu · conj(I_pu)` directly (system-base, no 0.5 factor).
- P2/P3 used `Pe_scale = 0.5 / Sbase` (single-phase peak-phasor convention),
  which produces `Pe_t0 = 0.25 pu` when NR predicts `P_inj = 0.5 pu`.
- P3 still PASS-ed at 10 s tail because the closed swing-equation
  self-corrected δ to a *different* equilibrium where `Pe_observed = Pm`,
  but at much larger \|δ\|max than NR predicted (P3: 1.21 rad vs NR: 0.36).
  This worked as a smoke test but is not a validated NR-IC consistency.
- D2 fix: `Pe_scale = 1.0 / Sbase` so that the static (t = 0⁺) measured Pe
  exactly equals NR's P_inj. The swing-equation is then at equilibrium from
  t = 0 — ω stays at 1, δ stays at δ₀, no transient.

This fix only changes `build_kundur_cvs.m` (the D2+ active model).
`build_kundur_cvs_p2.m` (spike artefact) is untouched. The convention is
documented inline in `build_kundur_cvs.m` next to the `Pe_scale` assignment.

---

## NR IC schema (`kundur_ic_cvs.json`)

```json
{
  "schema_version": 1,
  "source": "compute_kundur_cvs_powerflow",
  "source_hash": "sha256:c63055590d…",
  "timestamp": "2026-04-25T18:05:45+08:00",
  "powerflow": {
    "converged": true,
    "max_mismatch_pu": 3.56e-15,
    "iterations": 5
  },
  "vsg_internal_emf_angle_rad":     [0.2939, 0.2939, 0.1107, 0.1107],
  "vsg_terminal_voltage_mag_pu":    [1.0,    1.0,    1.0,    1.0   ],
  "vsg_terminal_voltage_angle_rad": [0.2939, 0.2939, 0.1107, 0.1107],
  "vsg_pm0_pu":                     [0.5,    0.5,    0.5,    0.5   ],
  "vsg_pe_target_pu":               [0.5,    0.5,    0.5,    0.5   ],
  "bus_voltages":                   { "Bus_V1": {…}, …, "Bus_INF": {…} },
  "x_v_pu":   0.10,
  "x_tie_pu": 0.30,
  "x_inf_pu": 0.05,
  "physical_invariants_checked": [
    "p_balance_per_bus", "pv_bus_ang_eq_internal_delta"
  ]
}
```

In the CVS path the VSG terminal voltage IS the CVS output — there is no
internal EMF behind a step-up filter — so
`vsg_internal_emf_angle_rad ≡ vsg_terminal_voltage_angle_rad`. This is
recorded explicitly in the JSON schema invariant
`pv_bus_ang_eq_internal_delta`.

---

## Engineering contracts honored (cvs_design.md)

| ID | Contract | Status |
|---|---|---|
| H1   | Driven CVS Source_Type=DC, Initialize=off, Measurements=None | ✅ all 4 |
| H2   | RI2C complex input — uniform across all 4 VSGs | ✅ |
| H3   | inf-bus = AC Voltage Source (no inport) | ✅ |
| H4   | powergui Phasor 50 Hz, ode23t variable-step, MaxStep=0.005 | ✅ |
| H5   | Every base-ws numeric `double()` | ✅ M_i, D_i, Pm_i, delta0_i, Vmag_i, wn, Vbase, Sbase, Pe_scale, L_*, R_load* |
| H6   | Phasor solver Mux constraints | ✅ no Mux errors at compile or sim |
| D-CVS-9/10/11 | DC + Init=off ; AC src for inf-bus ; double types | ✅ |

Plan §3 hand-calc IC ban: NR is now the sole IC source for D2+ gates
(`compute_kundur_cvs_powerflow.m` produces `kundur_ic_cvs.json`; the
build script asserts `ic.powerflow.converged` and the JSON schema is the
audit trail).

---

## Reproduction

```bash
# From the worktree root, with MCP MATLAB shared session running:
"C:/Users/27443/miniconda3/envs/andes_env/python.exe" \
  probes/kundur/gates/p4_d2_nr_ic_validate.py
```

Expected output: `OVERALL: PASS` with 4 PASS lines.

Pre-condition: `matlab.engine.shareEngine('mcp_shared')` was issued in MATLAB.

---

## Next gate

**D3 — 30 s zero-action stability gate (Gate 1)** — Stage 2 plan §1 D3 + §4:
- Probe: `probes/kundur/gates/p4_d3_gate1_30s_zero_action.py`
- Pass criteria: 4 VSG ω in [0.999, 1.001] over the full 30 s; \|δ\|max
  margin to π/2 − 0.05; Pe within ±5 % of IC nominal; no ω clip touches;
  inter-agent sync < 1e-3 over the tail 5 s.
- Outputs: `results/cvs_gate1/<timestamp>/{omega_ts,delta_ts,Pe_ts}.npz`
  (worktree-only; `results/` is not promoted to main per Stage 2 plan §4).
