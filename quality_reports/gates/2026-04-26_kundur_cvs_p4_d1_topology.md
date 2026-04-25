# Stage 2 Day 1 — Kundur CVS 7-bus Topology Verdict

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg`
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** GATE — D1 structural verification (no swing-eq, no NR, no RL)
**Predecessors:**
- Stage 2 plan §1 D1 — `quality_reports/gates/2026-04-25_kundur_cvs_stage2_readiness_plan.md`
- Engineering contract — `docs/design/cvs_design.md`
- P2 4-VSG swing-eq template — `probes/kundur/gates/build_kundur_cvs_p2.m`

---

## Verdict: PASS

All 6 D1 pass criteria green. Build, compile, 0.5 s static sim, CVS config,
RI2C uniformity, block-count inventory, and powergui mode all match the
Stage 2 plan §1 D1 exit gate.

---

## Artifacts

| File | Role |
|---|---|
| `scenarios/kundur/simulink_models/build_kundur_cvs.m` | NEW — full 7-bus build script |
| `scenarios/kundur/simulink_models/kundur_cvs.slx` | NEW — built model (33 blocks) |
| `probes/kundur/gates/verify_kundur_cvs_topology.m` | NEW — MATLAB structural inventory |
| `probes/kundur/gates/p4_d1_topology_check.py` | NEW — orchestrator for D1 gate |
| `quality_reports/gates/2026-04-26_kundur_cvs_p4_d1_topology.md` | This verdict |

No legacy file was overwritten:
- `scenarios/kundur/simulink_models/build_powerlib_kundur.m` (legacy ee 16-bus) — UNCHANGED
- `scenarios/kundur/simulink_models/build_kundur_sps.m` (legacy SPS) — UNCHANGED
- `scenarios/kundur/kundur_ic.json` — UNCHANGED
- `slx_helpers/vsg_bridge/*` shared layer — UNCHANGED
- `engine/simulink_bridge.py` — UNCHANGED
- NE39 path — UNCHANGED

---

## 7-bus topology (paper Sec.IV-A modified Kundur two-area)

| Bus | Role | Block(s) on bus |
|---|---|---|
| Bus_V1 | VSG1 terminal, area 1 | `CVS_VSG1` (driven), `GND_VSG1` |
| Bus_V2 | VSG2 terminal, area 1 | `CVS_VSG2` (driven), `GND_VSG2` |
| Bus_V3 | VSG3 terminal, area 2 | `CVS_VSG3` (driven), `GND_VSG3` |
| Bus_V4 | VSG4 terminal, area 2 | `CVS_VSG4` (driven), `GND_VSG4` |
| Bus_A  | area 1 junction       | `L_v_1/RConn1`, `L_v_2/RConn1`, `L_tie/LConn1`, `Load_A/LConn1` |
| Bus_B  | area 2 junction       | `L_v_3/RConn1`, `L_v_4/RConn1`, `L_tie/RConn1`, `L_inf/LConn1`, `Load_B/LConn1` |
| Bus_INF| system anchor         | `L_inf/RConn1`, `AC_INF/RConn1` |

Branches (all single-phase Phasor inductive, Series RLC Branch BranchType=L):

| Branch | From | To | X (pu) | Role |
|---|---|---|---|---|
| L_v_1 | Bus_V1 | Bus_A   | 0.10 | VSG1 step-up + feeder |
| L_v_2 | Bus_V2 | Bus_A   | 0.10 | VSG2 step-up + feeder |
| L_v_3 | Bus_V3 | Bus_B   | 0.10 | VSG3 step-up + feeder |
| L_v_4 | Bus_V4 | Bus_B   | 0.10 | VSG4 step-up + feeder |
| L_tie | Bus_A  | Bus_B   | 0.30 | weak inter-area tie |
| L_inf | Bus_B  | Bus_INF | 0.05 | strong system anchor |

Loads (Series RLC Branch, BranchType=R, between bus and ground):

| Load | Bus | R (Ohm) | P at Vbase (pu) |
|---|---|---|---|
| Load_A | Bus_A | 1322.50 | 0.40 |
| Load_B | Bus_B | 1322.50 | 0.40 |

Mapping to paper Sec.IV-A: 4 ESS (= 4 VSGs in this CVS path) connected to
two areas; AC infinite bus anchors the system (single anchor link, not the
canonical multi-bus generator interconnection — this is a deliberate
simplification of the Sec.IV-A 11-bus version into a 7-bus phasor model
for the CVS Phasor route, consistent with cvs_design.md §0 and the
decision to drive all four VSGs from `powerlib/Electrical Sources/Controlled
Voltage Source` rather than ee_lib generators).

> **Paper figure note:** the handoff pack referenced "paper Fig 17" for
> the topology diagram, but the actual paper Kundur diagram is `Fig.3`
> (per `docs/paper/yang2023-fact-base.md` Q5). The paper also does not
> assign explicit bus IDs ("separately connected to different areas"),
> so the bus IDs Bus_V1..V4 / Bus_A / Bus_B / Bus_INF used here are this
> path's choice and are recorded in the table above for reproducibility.

---

## D1 Pass Criteria — all PASS

| # | Criterion | Result | Detail |
|---|---|---|---|
| 1 | `simulink_compile_diagnostics(mode='update')` 0/0 | PASS | 0 errors / 0 warnings (MCP `simulink_compile_diagnostics`) |
| 2 | `simulink_step_diagnostics(0 → 0.5s)` success | PASS | `status=success`, `sim_time_reached=0.5`, `error_count=0`, `warning_count=0`, elapsed 0.77 s |
| 3 | All 4 driven CVS uniform RI2C complex path | PASS | VSG1<-RI2C_1, VSG2<-RI2C_2, VSG3<-RI2C_3, VSG4<-RI2C_4 |
| 4 | `Source_Type=DC`, `Initialize=off`, `Measurements=None` | PASS | Uniform across VSG1..VSG4 |
| 5 | inf-bus = `powerlib/Electrical Sources/AC Voltage Source` | PASS | `AC_INF` Amplitude=230000 V, Phase=0°, Frequency=50 Hz |
| 6 | 7-bus topology cross-check vs paper Sec.IV-A | PASS | Block-count inventory matches `EXPECTED_COUNTS`; bus mapping table above |

**Block-count inventory (33 total):**
`CVS_VSG=4 AC_INF=1 L_v=4 L_tie=1 L_inf=1 Load_A=1 Load_B=1 RI2C=4 Vr=4 Vi=4 GND_VSG=4 GND_LA=1 GND_LB=1 GND_INF=1 powergui=1`

---

## Engineering contracts honored (cvs_design.md)

| ID | Contract | Status |
|---|---|---|
| H1  | Driven CVS: Source_Type=DC, Initialize=off, Measurements=None | ✅ all 4 |
| H2  | CVS input = complex via Real-Imag-to-Complex (uniform across N VSGs) | ✅ all 4 sourced from RI2C_i |
| H3  | inf-bus uses `AC Voltage Source` (not Three-Phase, not 2nd driven CVS) | ✅ |
| H4  | powergui Phasor 50 Hz, ode23t variable-step, MaxStep=0.005 | ✅ |
| H5  | Every base-ws numeric is `double()` | ✅ wn_const, Vbase_const, Sbase_const, L_v_H, L_tie_H, L_inf_H, R_loadA, R_loadB |
| H6  | Phasor solver internal Mux constraints | ✅ no Mux errors at compile or sim |
| D-CVS-9 | DC + Init=off canonical for driven CVS | ✅ |
| D-CVS-10 | inf-bus = AC Voltage Source | ✅ |
| D-CVS-11 | base ws explicit `double` | ✅ |

---

## Day 1 boundaries upheld (Stage 2 plan §1 D1 禁止项)

- ❌ no swing-eq signal chain (IntW/IntD/cosD/sinD/Pe-feedback) — D2 will add
- ❌ no Newton-Raphson IC — D2 will add (`compute_kundur_cvs_powerflow.m`)
- ❌ no `kundur_ic_cvs.json` — D2 will create
- ❌ no NE39 / bridge / reward / agent / `contract.py::KUNDUR` change
- ❌ no ee_lib block reuse (full powerlib SPS-domain only)
- ❌ no SAC / no RL training entry / no `slx_helpers/vsg_bridge/*` modification
- ❌ main worktree untouched (still on `fix/governance-review-followups`)

---

## Notes for D2

1. CVS input is currently a static `Constant Vr + Constant Vi → RI2C → CVS`
   per VSG. D2 will replace each `Vr_i / Vi_i` constant with the swing-eq
   output (cosD_i, sinD_i scaled by Vbase) once the NR IC is available.
2. `delta0_default = asin(0.5 * X_v_pu) ≈ 0.0501 rad` is a SMIB-style
   placeholder. D2 NR will produce per-VSG δ_i, V_i, Pm_i with the four
   IC validation indicators (Pe ≈ Pm, ω ≈ 1, IntD margin, inter-agent sync).
3. The build script writes the following base-ws scalars at build time
   (also forced `double`): `wn_const, Vbase_const, Sbase_const, L_v_H,
   L_tie_H, L_inf_H, R_loadA, R_loadB`. D2 must add per-VSG `M_i, D_i,
   Pm_i, delta0_i, Pe_scale` (mirroring P2) when the swing-eq is wired.
4. Single-line walker for multi-port Simscape physical nodes does not
   work — Simscape realises Bus_A / Bus_B / Bus_INF via implicit branch
   points whose secondary lines have no `DstPortHandle`. D1 verification
   uses block-count inventory + sim PASS + add_line audit instead. Future
   gates needing topology verification should follow the same pattern.

---

## Reproduction

```bash
# From the worktree root:
"C:/Users/27443/miniconda3/envs/andes_env/python.exe" \
  probes/kundur/gates/p4_d1_topology_check.py
```

Pre-condition: MCP MATLAB session running with `matlab.engine.shareEngine('mcp_shared')`.

Expected output: `OVERALL: PASS` with 6 PASS lines.

---

## Next gate

**D2 — Newton-Raphson IC validation** (Stage 2 plan §1 D2 + §3):
- Fork `compute_kundur_powerflow.m` → `compute_kundur_cvs_powerflow.m`
- Output `kundur_ic_cvs.json` (NEW, schema in plan §3)
- Probe: `probes/kundur/gates/p4_d2_nr_ic_validate.py`
- Pass criteria: 4 IC validation indicators (Pe ≈ Pm ±5%, ω ≈ 1 ±1e-3, IntD
  margin < 1.521 rad, inter-agent sync < 1e-3 pu) over 0.5 s sim with
  swing-eq closed.
