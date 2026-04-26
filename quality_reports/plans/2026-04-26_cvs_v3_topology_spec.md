# Kundur CVS v3 — Topology & Parameter Spec (Phase 0 freeze)

> **Scope:** Phase 0 of `2026-04-26_kundur_cvs_v3_plan.md`. Design-freeze + asset
> audit only. **No `.slx`, no training, no env edits, no NE39, no SAC.**
> **Constraint reminder:** Do NOT use SPS, powerlib v1, breaker / topology switch,
> or `phang_feedback` step strategy. v3 is an additive path; v2 (`kundur_cvs.slx`,
> `kundur_ic_cvs.json`, profile `kundur_cvs.json`) remains the trainable baseline
> and is NOT modified.
> **Status:** DRAFT pending user approval. Phase 1 starts only on explicit GO.

---

## 1. Bases and per-unit conventions (LOCKED)

| Quantity | Value | Source |
|---|---|---|
| `fn` | 50 Hz | [build_powerlib_kundur.m:66](scenarios/kundur/simulink_models/build_powerlib_kundur.m), v2 [build_kundur_cvs.m:45](scenarios/kundur/simulink_models/build_kundur_cvs.m) |
| `ωn` | `2π·fn` = 314.159 rad/s | derived |
| `Sbase` | 100 MVA = 100e6 VA | both files agree |
| `Vbase` | 230 kV (single voltage level, no transformers) | both files agree |
| `Zbase` | `Vbase²/Sbase` = 529 Ω | derived |
| Pbase (Sbase) | 100 MW per 1.0 sys-pu | derived |

**Per-unit rule:** every parameter in this spec is on **system base (100 MVA)
unless suffixed with `_gen_base` / `_vsg_base`**. The build script must convert
machine-base impedances explicitly:

- `X_gen_sys = 0.30 · (100/900) = 0.0333 pu` (SG, G1–G3, Sn = 900 MVA)
- `X_vsg_sys = 0.30 · (100/200) = 0.15 pu` (ESS, Sn = 200 MVA)
- `X_w1_sys = 0.30 · (100/900) = 0.0333 pu` (W1, Sn = 900 MVA, if treated as
  PVS-behind-X, otherwise N/A)
- `X_w2_sys = 0.30 · (100/200) = 0.15 pu` (W2, Sn = 200 MVA)

**Source:** `build_powerlib_kundur.m:78–79, 118–119`. Already correct in v2.

---

## 2. Bus inventory (LOCKED — 16-numbered, 15-active)

Bus 13 is **intentionally skipped** (matches paper Fig.3 / `compute_kundur_powerflow.m`
"15 母线 (1–16, 跳过 13)" comment). v3 keeps the same numbering.

| Bus | Role | Type (NR) | V_spec (pu) | P_sched (sys-pu) | Q_sched | Notes |
|----|----|----|----|----|----|----|
| 1 | G1 internal CVS terminal | PV | 1.03 | +7.00 | 0 | Yang Sec.IV-A; P_sched = 700 MW / Sbase |
| 2 | G2 internal CVS terminal | PV | 1.01 | +7.00 | 0 | 700 MW |
| 3 | G3 internal CVS terminal | PV | 1.01 | +7.19 | 0 | 719 MW |
| 4 | W1 internal source terminal | PV (constant power) | 1.00 | +7.00 | 0 | 700 MW programmable; not a swing source |
| 5 | Area-1 transmission node | PQ | — | 0 | 0 | passive junction |
| 6 | Area-1 transmission node | PQ | — | 0 | 0 | passive junction |
| 7 | Area-1 load + shunt cap bus | PQ | — | −9.67 | −1.00 + Q_shunt7 | load 967 MW + 100 Mvar; shunt cap 200 Mvar (capacitive) |
| 8 | Inter-area / W2-area node | PQ | — | 0 | 0 | passive junction; W2 + ES2 inject through Bus 11 / 16 |
| 9 | Area-2 load + shunt cap bus | PQ | — | −17.67 | −1.00 + Q_shunt9 | load 1767 MW + 100 Mvar; shunt cap 350 Mvar |
| 10 | Area-2 transmission node | PQ | — | 0 | 0 | passive junction |
| 11 | W2 internal source terminal | PV (constant power) | 1.00 | +1.00 | 0 | 100 MW programmable |
| 12 | ES1 internal CVS terminal | PV | 1.00 | +Pm0_ES1 | 0 | see §3 — ESS Pm0 closure rule |
| 14 | ES3 internal CVS terminal | PV | 1.00 | +Pm0_ES3 | 0 | |
| 15 | ES4 internal CVS terminal | PV | 1.00 | +Pm0_ES4 | 0 | |
| 16 | ES2 internal CVS terminal | PV | 1.00 | +Pm0_ES2 | 0 | |

**Angle reference:** Bus 1 (G1) θ = 0 fixed. Same convention as v2
(`compute_kundur_cvs_powerflow.m:108–109`) and as `compute_kundur_powerflow.m`
absolute frame. **No slack bus.** Global P-balance is enforced **before** NR
(see §3.1 closure rule).

**Q convention:** loads enter as constant impedance (R-only for P, parallel L
for Q). Shunt caps enter as constant +Q at bus voltage. This matches v2 const-Z
load semantics and avoids the const-PQ Newton instability.

---

## 3. Source models and Pm0 closure (LOCKED with one open decision)

### 3.1 Global P-balance closure (NR pre-check) — RESOLVED Q1 = (a)

**User decision (2026-04-26):** preserve paper dispatch for all non-ESS sources
(G1/G2/G3 P0 = 700/700/719 MW; W1/W2 = 700/100 MW). The 4 ESS absorb the system
net active surplus (no `hidden slack`, no G1 down-dispatch).

**Sign convention (LOCKED):**
- `Pm > 0` = source **injects** active power into the network (generating mode).
- `Pm < 0` = source **absorbs** active power from the network (ESS charging mode).
- All values quoted in **system pu (Sbase = 100 MVA)** unless suffixed.

**ESS dispatch formula (per source, equal split — no preferential bus):**

```
P_ES_each  =  − (P_gen_total + P_wind_total − P_load_total − P_loss) / 4

   where
     P_gen_total  = ΣP0_SG  on system pu      (3 SG, paper-fixed)
     P_wind_total = ΣPref_W on system pu      (2 wind, paper-fixed)
     P_load_total = Σ|P_load| at solved |V|² (const-Z effect included)
     P_loss       = Σ R_line · |I_line|²      (NR output, NOT pre-estimated)
```

**Lossless reference (sanity bound, NOT the locked value):**

- ΣP_gen + ΣP_wind = 700+700+719 + 700+100 = 2919 MW
- ΣP_load (nominal at |V|=1) = 967 + 1767 = 2734 MW
- Lossless surplus = +185 MW
- Equal-split lossless ESS: `P_ES_each = −185/4 = −46.25 MW = −0.4625 sys-pu`
  ≈ −0.2313 vsg-base pu (Sn_VSG = 200 MVA)

**v3 lossy NR will return a SMALLER-magnitude (less negative) number**, because
`P_loss > 0` is consumed by the network and reduces what the ESS group must
absorb. Sign rearrangement of the closure formula:

```
P_ES_each = − (P_gen + P_wind − P_load − P_loss) / 4
          = − (surplus_lossless − P_loss) / 4
```

With the §9 R2 loss budget `total_loss_pu ∈ [0.01, 0.03]` of 27.34 sys-pu
load → losses 0.27–0.82 sys-pu → loss reduces the lossless ESS-absorption of
1.85 sys-pu (0.4625 each) by 0.07–0.21 sys-pu per ESS. Therefore:

| Regime | Expected `P_ES_each` |
|---|---|
| Lossless reference | −46.25 MW = −0.4625 sys-pu = −0.2313 vsg-pu |
| Lossy lower bound (1 % loss) | ≈ −39.4 MW ≈ −0.394 sys-pu |
| Lossy upper bound (3 % loss) | ≈ −25.7 MW ≈ −0.257 sys-pu |

`|P_ES_each| > 0.4625 sys-pu` ⇒ NR returned **more** absorption than lossless,
which is physically impossible with `P_loss ≥ 0`. Treat as a base / sign /
loss-accounting bug; trigger the §10 diagnostic-only path.

**Implementation:** `compute_kundur_cvs_v3_powerflow.m` must:
1. Pre-NR: declare `P_ES_each` as an UNKNOWN, not as a scheduled value.
2. Solve NR with all 4 ESS treated as **PV with V|spec=1.0 and P|sched =
   placeholder** that gets corrected in an outer loop, OR equivalently
   formulate ESS as a single 4-bus group whose total P injection equals the
   negative of (gen + wind − load_at_V − losses) and split equally.
3. Post-NR: report `P_ES_each` as a **derived quantity**, not an input.
4. Closure check: `|4·P_ES_each + (P_gen + P_wind − P_load_at_V − P_loss)|
   < 1e-3 sys-pu`. The same 1e-3 tol the v2 closure uses for the const-Z
   V² residual.

### 3.2 G1, G2, G3 — CVS swing closure (NEW)

Implemented as v2-pattern CVS + closure, with 3 additions vs v2 ESS:

| Slot | Value | Note |
|---|---|---|
| Sn | 900 MVA | gen base, used to scale Pe back to sys-pu |
| H | G1=6.5 / G2=6.5 / G3=6.175 s | paper §IV-A; M = 2H |
| D | 5.0 (gen-base pu) | paper §IV-A |
| R (governor droop) | 0.05 (gen-base pu) | paper §IV-A |
| Pm0 (sys-pu) | +7.00 / +7.00 / +7.19 | from paper P0_MW / Sbase |
| Internal X | 0.30 gen-base = 0.0333 sys-pu | already correct in v2 [build_powerlib_kundur.m:79](scenarios/kundur/simulink_models/build_powerlib_kundur.m) |
| Governor term | `Pm_total = Pm0 − (1/R)·(ω−1)` | NEW vs v2 |

Swing equation form, identical to v2 ESS (`build_kundur_cvs.m:238–267`) **except M
and D are gen-base pu and frozen** (G1/G2/G3 are NOT RL-controlled):

```
M_g · dω/dt = (Pm0 − (1/R)(ω−1)) − Pe_gen_pu − D_g · (ω−1)
dδ/dt = ωn · (ω−1)
Pe_gen_pu = Re(V·conj(I)) · Sbase / Sn_gen          # convert from W to gen-pu
```

### 3.3 ESS1–4 — CVS swing closure, RL-controlled (REUSE v2)

**100 % v2 pattern**, 4 instances. Only changes:
- bus connection (Bus 12 / 16 / 14 / 15 instead of v2's Bus_A/Bus_B junctions)
- Pm0 from §3.1 dispatch instead of v2 fixed +0.2
- M0 = 24 / D0 = 4.5 (the v2 promoted defaults; locked in §B1 verdict)
- M_i / D_i base-ws variables remain RL-tunable

### 3.4 W1, W2 — Programmable Voltage Source, no swing eq (NEW pattern)

**Not** ee_lib `Wind Farm`. Modelled as Programmable Voltage Source with two
workspace levers:

| Knob | Default | Disturbance use |
|---|---|---|
| `Pref_W1`, `Pref_W2` | 700 MW / 100 MW | constant for v3-baseline |
| `WindAmp_W1`, `WindAmp_W2` | 1.0 | set to 0 mid-episode → wind trip |

The PVS is configured as a behind-X equivalent of a constant-power injector:
the Pref → V_mag mapping is solved at NR time, V_phase comes from NR θ_W. No
internal dynamics. This is a deliberate fidelity reduction (DECISION-Q2 below).

> **DECISION-Q2 RESOLVED (2026-04-26) = (a):** const-power Programmable Voltage
> Source + `WindAmp_Wk` workspace knob. **NO Type-3/4 wind turbine in v3.**
> Type-3/4 is reconsidered only if Phase 5 paper-baseline mismatch (DDIC vs
> adaptive vs no-control −8.04 / −12.93 / −15.2) is traceable to missing wind
> dynamics. Documented in plan §11.

---

## 4. Branch (line) inventory (LOCKED — direct reuse from powerlib)

All taken verbatim from `build_powerlib_kundur.m:230–267`. Per-km values:

- **Standard (R_std):** R = 0.053 Ω/km, L = 1.41 mH/km, C = 0.009 μF/km
- **Short connect (R_short):** R = 0.01 Ω/km, L = 0.5 mH/km, C = 0.009 μF/km

| Line | From | To | Length km | R/L/C class |
|----|----|----|----|----|
| L_1_5 | 1 | 5 | 5 | std |
| L_2_6 | 2 | 6 | 5 | std |
| L_3_10 | 3 | 10 | 5 | std |
| L_4_9 | 4 | 9 | 5 | std |
| L_5_6a, L_5_6b | 5 | 6 | 25 | std (×2 parallel) |
| L_6_7a, L_6_7b | 6 | 7 | 10 | std (×2 parallel) |
| L_7_8a/b/c | 7 | 8 | 110 | std (×3 parallel) — inter-area weak tie |
| L_8_9a, L_8_9b | 8 | 9 | 10 | std (×2 parallel) |
| L_9_10a, L_9_10b | 9 | 10 | 25 | std (×2 parallel) |
| L_7_12 | 7 | 12 | 1 | short — ES1 connect |
| L_8_16 | 8 | 16 | 1 | short — ES2 connect |
| L_10_14 | 10 | 14 | 1 | short — ES3 connect |
| L_9_15 | 9 | 15 | 1 | short — ES4 connect |
| L_8_W2 | 8 | 11 | 1 | short — W2 connect |

**Implementation:** v2 `build_kundur_cvs.m` represents lines as
`powerlib/Elements/Series RLC Branch` with `BranchType='L'` (pure reactance)
and `Inductance = X_pu·Zbase/ωn`. v3 extends this to all 18 branches above.

**For NR**, the line admittance equals `1/(R + jωL)` per km × length, plus
shunt capacitance `jωC·length/2` at each end (Π model). v2's `compute_kundur_cvs_powerflow.m`
currently uses **lossless Y** (only `1/(jX)` per branch); v3 NR must include
R and shunt C correctly because the heterogeneous load + 110 km tie line will
have non-trivial losses (~30–50 MW estimate). This is captured in the
`P_losses` term of §3.1 closure.

---

## 5. Loads & shunts

| Bus | Element | Value | Model | Source |
|---|---|---|---|---|
| 7 | Load7 | 967 MW + 100 Mvar | Constant Z (R-L parallel) | `build_powerlib_kundur.m:269–276` |
| 9 | Load9 | 1767 MW + 100 Mvar | Constant Z | same |
| 7 | Shunt7 | 200 Mvar capacitive | jωC shunt | `build_powerlib_kundur.m:279–284` |
| 9 | Shunt9 | 350 Mvar capacitive | jωC shunt | same |

**Constant-Z policy:** matches v2's R-only Load_A/Load_B convention
(`build_kundur_cvs.m:113–128`). Reactive component handled as parallel inductive
branch. NR closure tolerance must reuse v2's "const-Z V² effect ≤ 1e-3 pu" rule
(`compute_kundur_cvs_powerflow.m:194`).

### 5.1 Disturbance loads (NEW for v3, paper-faithful)

Two parallel R loads, conductance set by workspace variable, at Bus 7 and Bus 9
(real load buses, replacing the v2 single-VSG Pm-step gating only for
training; v2 Pm-step disturbance is **preserved per §3.3** for the
`pm_step_random_source` mode).

```
G_perturb_k(t) = LoadStep_amp_k(t) · (Sbase / Vbase²)
```

Wired with the same Clock+Relational+Cast+Constant+Product gating cluster v2
already uses (`build_kundur_cvs.m:215–236`). Paper-aligned amplitude bound:
±2 sys-pu = ±200 MW (well within 1767 MW Load9 / 967 MW Load7 budget; matches
paper Sec.IV-C "load step" disturbance class).

---

## 6. Initial-condition flow

```
build_kundur_cvs_v3.m
   ├─ reads kundur_ic_cvs_v3.json            (must exist; built before this step)
   ├─ writes 16-bus electrical layer + 7 swing-eq closures (G1/G2/G3 + ES1-4)
   ├─ writes 2 PVS clusters (W1, W2) with workspace knobs Pref / WindAmp
   ├─ writes 7 Pm-step gating clusters (3 SG + 4 ESS)
   ├─ writes 2 LoadStep gating clusters (Bus 7, Bus 9)
   ├─ saves .slx + sidecar runtime .mat (immutable constants)
   └─ refuses to build if NR did not converge or closure_ok = false

compute_kundur_cvs_v3_powerflow.m
   ├─ builds Y-bus (15-active-bus, with R+jX+jωC/2)
   ├─ NR with Bus 1 angle ref, no slack
   ├─ pre-NR: enforce ΣP_sched + ΣPm_ESS = ΣP_load_at_V=1 (within 1e-9)
   ├─ post-NR: closure check VSG1 / G1 P_inj == P_sched within 1e-3
   ├─ outputs: per-source (delta0, V_mag, Pm0, Pe_target, theta_internal)
   ├─ JSON schema: extends v2 schema_version=2 with G/W slots, additive
   └─ topology_variant = "v3_paper_kundur_16bus"
```

JSON output schema (extends v2 `kundur_ic_cvs.json`, additive only — v2 readers
that pull only ESS slots remain compatible):

```jsonc
{
  "schema_version": 3,
  "source": "compute_kundur_cvs_v3_powerflow",
  "source_hash": "sha256:...",
  "timestamp": "...",
  "topology_variant": "v3_paper_kundur_16bus",
  "powerflow": { "converged", "max_mismatch_pu", "iterations",
                 "closure_ok", "closure_residual_pu",
                 "closure_tolerance_pu": 1e-3,
                 "closure_residual_origin": "const_z_load_v_squared_effect" },
  "global_balance": { "total_Pm_pu", "total_load_pu_at_v1",
                      "total_loss_pu", "pre_residual_pu",
                      "no_hidden_slack": true },

  // Existing v2-compatible slots (only the ESS array is filled; SG/W stay zero
  // for legacy readers that index 1..4 == ESS):
  "vsg_internal_emf_angle_rad":      [Pm0_ES1..4],
  "vsg_terminal_voltage_mag_pu":     [|V|_ES1..4],
  "vsg_terminal_voltage_angle_rad":  [δ_ES1..4],
  "vsg_pm0_pu":                      [Pm0_ES1..4],
  "vsg_pe_target_pu":                [Pe_target_ES1..4],

  // NEW v3 slots:
  "sg_internal_emf_angle_rad":       [δ_G1..3],
  "sg_terminal_voltage_mag_pu":      [|V|_G1..3],
  "sg_pm0_sys_pu":                   [Pm0_G1..3],
  "wind_terminal_voltage_mag_pu":    [|V|_W1, |V|_W2],
  "wind_terminal_voltage_angle_rad": [θ_W1, θ_W2],
  "wind_pref_sys_pu":                [Pref_W1, Pref_W2],

  "bus_voltages": {  /* per-bus |V|, ang, by Bus_<n> key */ },
  "x_v_pu":  { "ES": 0.15, "G": 0.0333, "W2": 0.15, "W1_const_power": null },
  "x_tie_pu": "embedded in line_defs",
  "physical_invariants_checked": [
     "p_balance_per_bus", "global_balance_no_hidden_slack",
     "pv_bus_ang_eq_internal_delta", "shunt_q_consistency"
  ]
}
```

---

## 7. Asset reuse table (Phase 0 audit verdict)

### 7.1 Direct reuse — ZERO modification

| Asset | Why reusable | Evidence |
|---|---|---|
| `agents/`, `utils/run_protocol`, `utils/monitor`, `engine/training_*`, `engine/run_schema` | Profile-aware, model-agnostic | not v3-touched |
| `engine/matlab_session.py`, `engine/simulink_bridge.py::cvs_signal` step strategy | Already built and tested for v2 | [simulink_bridge.py](engine/simulink_bridge.py) `STEP_STRATEGY_MODES = ("phang_feedback", "cvs_signal")` |
| `slx_helpers/vsg_bridge/{slx_step_and_read_cvs.m, slx_episode_warmup_cvs.m, slx_extract_state.m}` | CVS-specific, reads `omega_ts_<i>`, `delta_ts_<i>`, `Pe_ts_<i>` Timeseries | matches v2 logger naming |
| `scenarios/contract.py::KUNDUR` (n_agents=4, fn=50, dt=0.2, obs=7, act=2) | RL contract; ESS-count is the only tunable, kept at 4 | not v3-touched |
| `scenarios/config_simulink_base.py` (SAC LR, gamma, MAX_NEIGHBORS, COMM_FAIL_PROB, etc.) | Hyperparameters | not v3-touched |
| `scenarios/kundur/model_profiles/schema.json` | Schema accepts the new profile via `solver_family=sps_phasor`, `pe_measurement=vi`, `phase_command_mode=passthrough`, `warmup_mode=technical_reset_only` | exactly the v2 profile shape |
| Probes `probes/kundur/gates/{p4_d2, d3, d4, smoke, dispatch_verify}` | Profile-driven, run against the model selected by `KUNDUR_MODEL_PROFILE` env var | reusable for v3 sanity, may need v3-specific tuning of pass thresholds |
| `kundur_ic_cvs.json` v2 IC | Stays alongside v3 IC; not edited | v2 baseline preserved per plan §2.1 |

### 7.2 Reuse after adaptation (clearly identified parent → child)

| Source asset | Target | Adaptation |
|---|---|---|
| `compute_kundur_cvs_powerflow.m` (5-bus, 6 buses) | `compute_kundur_cvs_v3_powerflow.m` (16-bus, 15 active) | Extend bus_table to 15, line_defs from §4, add G/W slots, include R+jωC/2 (lossy) instead of pure jX, extend output JSON per §6 |
| `compute_kundur_powerflow.m` (15-bus powerlib NR) | merge into v3 NR | Lift its line_defs / Ybus build pattern (already correct R+L+C). Drop dependency on `kundur_ic.json` VSG-base p0 (use sys-pu directly). |
| `build_kundur_cvs.m` (4 ESS CVS clusters + Pm-step gating + ToWorkspace loggers + 0.5s StopTime + Phasor solver) | `build_kundur_cvs_v3.m` | Loop over 7 dynamic sources (3 SG + 4 ESS), wire per-source X internal as `L_v_H_<src>` from §1 sys-pu, add 2 PVS clusters, add 2 LoadStep gating clusters at Bus 7/9, build 18 branches per §4 between 15 active buses. Promote 0.5s StopTime to whatever bridge uses. |
| `build_powerlib_kundur.m` parameter table (`gen_cfg`, `wind_cfg`, VSG_*, `R_std/L_std/C_std`, `R_short/L_short/C_short`, `ess_bus`, `ess_main`) | data only, COPIED into v3 build | All values verbatim. Do **NOT** import the powerlib `.m` script — only its constants. v3 build is independent of ee_lib. |
| `scenarios/kundur/config_simulink.py` (CVS branch starting at L120) | extend with v3 branch | Add `if KUNDUR_MODEL_PROFILE.model_name == 'kundur_cvs_v3': … load v3 IC, set `pe0_default_vsg`, set `delta0_deg`. Keep v2 branch and legacy/SPS branch untouched. |
| `env/simulink/kundur_simulink_env.py::apply_disturbance` (current single Pm-step on VSG[0]) | extend with `disturbance_type` param | New types: `pm_step_random_source` (existing logic, bus_idx in 0..6 = 3 SG + 4 ESS), `load_step_random_bus` (Bus 7 / Bus 9 conductance toggle), `wind_trip` (set WindAmp_W2 = 0 or WindAmp_W1 = 0). Default = current `pm_step_single_vsg` so v2 contract is unchanged. |

### 7.3 Must build new (Phase 1 deliverables)

| File | Type | Phase | Estimated lines |
|---|---|---|---|
| `scenarios/kundur/matlab_scripts/compute_kundur_cvs_v3_powerflow.m` | new | 1 | ~350 (NR + 15-bus Y-bus + closure + JSON) |
| `scenarios/kundur/simulink_models/build_kundur_cvs_v3.m` | new | 1 | ~700 (CVS clusters ×7 + PVS ×2 + lines ×18 + loads + LoadStep gating ×2 + Pm-step gating ×7 + Phasor solver + loggers) |
| `scenarios/kundur/kundur_ic_cvs_v3.json` | new (NR output) | 1 | auto-generated |
| `scenarios/kundur/simulink_models/kundur_cvs_v3.slx` | new (build output) | 1 | auto-generated |
| `scenarios/kundur/simulink_models/kundur_cvs_v3_runtime.mat` | new (build output) | 1 | auto-generated |

### 7.4 Forbidden assets (negative confirmation)

| Asset | Why forbidden | Plan §-ref |
|---|---|---|
| `build_kundur_sps.m`, `kundur_vsg_sps.slx`, `model_profiles/kundur_sps_candidate.json` | RC-A (Three-Phase Source PhaseAngle semantics) unresolved | plan §2.2.4 |
| `kundur_vsg.slx` (v1 powerlib) | IntW saturation root cause | plan §2.2.6 |
| `add_disturbance_and_interface.m` Switch-based load swap | FastRestart killer | plan §2.2.5 |
| Bridge `phang_feedback` step strategy | SPS-era; v3 uses `cvs_signal` exclusively | plan §2.2 |
| `build_kundur_simulink.m`, `kundur_two_area.slx`, `legacy_component_tests/`, `build_kundur_cvs_v1_legacy.m`, `kundur_cvs_v1_legacy.slx` | 60 Hz era / legacy | plan §6 "Do NOT reuse" |

---

## 8. Phase 1 minimum file list (ONLY these are edited / created)

```
NEW   scenarios/kundur/matlab_scripts/compute_kundur_cvs_v3_powerflow.m
NEW   scenarios/kundur/simulink_models/build_kundur_cvs_v3.m
NEW   scenarios/kundur/kundur_ic_cvs_v3.json                        (NR output)
NEW   scenarios/kundur/simulink_models/kundur_cvs_v3.slx            (build output)
NEW   scenarios/kundur/simulink_models/kundur_cvs_v3_runtime.mat    (build output)
NEW   results/harness/kundur/cvs_v3_phase1/{nr_summary.json,
                                            build_summary.json,
                                            phase1_verdict.md}
```

**Untouched in Phase 1:**
- `scenarios/kundur/config_simulink.py` (Phase 3)
- `env/simulink/kundur_simulink_env.py` (Phase 3)
- `scenarios/kundur/model_profiles/*.json` (Phase 3)
- `engine/simulink_bridge.py` (cvs_signal already exists)
- All NE39 paths, all SAC code, all training entry points
- v2 artefacts (`kundur_cvs.slx`, `kundur_ic_cvs.json`, `build_kundur_cvs.m`,
  `compute_kundur_cvs_powerflow.m`, `model_profiles/kundur_cvs.json`)

---

## 9. Risks surfaced in Phase 0 (must accept before Phase 1)

| ID | Risk | Severity | Mitigation in Phase 1 |
|---|---|---|---|
| R1 | **Negative ESS Pm0 at steady state** (lossless surplus 185 MW = 4·46.25 MW; lossy NR returns smaller magnitude per-ESS, expected band ≈ −26 to −40 MW = −0.26 to −0.40 sys-pu). Implies ESS *charging* in baseline; v2 has all sources at +0.2 sys-pu, very different operating point. | High | DECISION-Q1 = (a) accepted (§3.1). `P_ES_each` is a derived quantity from NR, not input. Phase 1.1 verdict reports the value. Out-of-band triggers (diagnostic-only): `\|P_ES_each\| > 0.4625 sys-pu` (impossible: more absorption than lossless reference) OR `\|P_ES_each\| < 0.20 sys-pu` (loss > 3 %, see R2). |
| R2 | **Lossy NR vs lossless v2** — 110 km tie line + 967/1767 MW loads → real losses. v2 NR uses `Ybus = 1/(jX)` only; v3 must include R + jωC/2. New verification path. | Medium | Phase 1.1 NR verdict checks `total_loss_pu` is in plausible range (1–3 % of ΣLoad ≈ 27–82 MW). **If outside range, do NOT auto-modify topology / dispatch.** Diagnose first: (a) line per-km R/L/C value transcription; (b) Sbase/Vbase consistency; (c) Π-model shunt cap placement; (d) load Q model unit error. Report root cause to user; only then propose a parameter fix. |
| R3 | **3 SG + governor droop interaction with ESS RL signal**. Paper R=0.05 means 1 Hz drop → +20 % Pm. RL r_f signal could be dominated by SG governor instead of ESS H/D. | Medium | Defer to Phase 2.3/2.4 (load step probes); if signal hidden, flag for plan §11 follow-up (paper Sec.II-A is silent on SG control). |
| R4 | **PVS-as-wind-farm fidelity**. Setting `WindAmp_W2=0` removes 100 MW instantly (no spin-down); paper does not specify wind dynamics. | Low | DECISION-Q2 ownership; Phase 2.5 records nadir; revisit at Phase 5 if baseline mismatch. |
| R5 | **NR convergence** with mixed PV (4 ESS + 3 SG + 2 wind = 9 PV nodes) on a 15-bus system. Current `compute_kundur_powerflow.m` already converges on the same network with 4 PV (ESS only); adding 5 more PV is well-posed but Jacobian conditioning untested. | Low | Phase 1.1 must converge in <50 iter, max_mismatch < 1e-10. If not, fall back to flat-start + linear-AC initialiser. |
| R6 | **Build cost on 16-bus** — Phasor compile + FastRestart init estimated 10–15 s (5× v2). | Low | Per-run cost only, not per-step. Acceptable. Verify in Phase 1.4. |
| R7 | **DECISION-Q1 (ESS dispatch) and DECISION-Q2 (wind model)** are paper-undetermined. Both locked = (a) by user 2026-04-26 (§3.1, §3.4). Phase 5 paper-baseline mismatch is the trigger to revisit. | Resolved | n/a |
| R9 | **Scope creep into v2 / NE39 / SAC / shared bridge** during Phase 1 implementation. v2 is the locked RL baseline; modification breaks the comparison surface. | High | Phase 1 file allow-list in §8 is the contract. Any edit outside that list = STOP and ask. `engine/simulink_bridge.py` is read-only in Phase 1 (cvs_signal already exists). NE39 paths are read-only forever in v3. |
| R8 | **`schema_version` bump 2 → 3** in IC JSON. v2 build script asserts `topology_variant == 'v2_no_inf_bus'` ([build_kundur_cvs.m:41–42](scenarios/kundur/simulink_models/build_kundur_cvs.m)) — already gated, will refuse to load v3 IC. v3 build must symmetrically refuse to load v2 IC. | Low | `build_kundur_cvs_v3.m` asserts `topology_variant == 'v3_paper_kundur_16bus'`. Mechanical addition. |

---

## 10. Phase 0 verdict — APPROVED 2026-04-26

**User decisions (locked):**
- **Q1 = (a)**: paper dispatch preserved; 4 ESS equally absorb net surplus;
  `P_ES_each` is a derived NR quantity, sign convention `Pm < 0 = absorption`.
- **Q2 = (a)**: const-power PVS for W1/W2; no Type-3/4 in v3.
- **Spec §1–§7 frozen as updated** (this file).

**Two additional Phase 1 constraints (locked):**

1. **File allow-list is binding.** Phase 1 may ONLY create / write the 5 new
   v3 files in §8. Any edit to v2 artefacts, `scenarios/new_england/`,
   `agents/`, or `engine/simulink_bridge.py` = STOP and request user
   authorization. `cvs_signal` step strategy is reused as-is.

2. **Sanity-check failures are diagnostic-only.** If
   `total_loss_pu ∉ [0.01, 0.03]` OR `|P_ES_each| > 1.0 sys-pu` OR NR fails to
   converge, Phase 1 emits a verdict with root-cause diagnosis (parameter /
   unit / line model / IC) but does NOT auto-modify topology, dispatch, or
   per-km line values. User decides the next step.

**Phase 1 execution order (now unblocked):**

1. Write `compute_kundur_cvs_v3_powerflow.m` (Phase 1.1).
2. Run NR; emit `kundur_ic_cvs_v3.json` + `results/harness/kundur/cvs_v3_phase1/nr_summary.json`
   + per-bus dispatch table + `P_ES_each` value + `total_loss_pu`.
3. Gate-check (PASS = all of):
   - NR converged AND `max_mismatch_pu < 1e-10`
   - `closure_ok = true` (ESS-group balance residual < 1e-3)
   - `total_loss_pu ∈ [0.01, 0.03]` (sanity, diagnostic-only on fail)
   - `|P_ES_each| ≤ 0.4625 sys-pu` AND `|P_ES_each| ≥ 0.20 sys-pu` (sanity,
     diagnostic-only on fail; bounds derived in §3.1 lossy table)
4. **Only on PASS**, write `build_kundur_cvs_v3.m` (Phase 1.3), run it,
   verify .slx compiles + `sim()` runs StopTime=0.5s without crash.
5. Phase 1 verdict to `results/harness/kundur/cvs_v3_phase1/phase1_verdict.md`,
   then STOP and request GO for Phase 2.

---

## 11. References

- Plan: `quality_reports/plans/2026-04-26_kundur_cvs_v3_plan.md`
- v2 build:    [scenarios/kundur/simulink_models/build_kundur_cvs.m](scenarios/kundur/simulink_models/build_kundur_cvs.m)
- v2 NR:       [scenarios/kundur/matlab_scripts/compute_kundur_cvs_powerflow.m](scenarios/kundur/matlab_scripts/compute_kundur_cvs_powerflow.m)
- v2 IC:       [scenarios/kundur/kundur_ic_cvs.json](scenarios/kundur/kundur_ic_cvs.json)
- v2 profile:  [scenarios/kundur/model_profiles/kundur_cvs.json](scenarios/kundur/model_profiles/kundur_cvs.json)
- profile schema: [scenarios/kundur/model_profiles/schema.json](scenarios/kundur/model_profiles/schema.json)
- Paper params source: [scenarios/kundur/simulink_models/build_powerlib_kundur.m:60–294](scenarios/kundur/simulink_models/build_powerlib_kundur.m)
- powerlib NR (line model reference): `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m`
- Bridge dispatch: [engine/simulink_bridge.py](engine/simulink_bridge.py) `cvs_signal` mode
- Env disturbance: [env/simulink/kundur_simulink_env.py:313–322, 678–745](env/simulink/kundur_simulink_env.py)
- Paper fact base: [docs/paper/yang2023-fact-base.md](docs/paper/yang2023-fact-base.md) §IV-A
