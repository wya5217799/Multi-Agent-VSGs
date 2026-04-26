# CVS v2 Dry-Run Verdict (2026-04-26)

> **Scope**: validate that `kundur_cvs_v2.slx` (CVS topology with `AC_INF` /
> `GND_INF` / `L_inf` removed) is a valid self-contained 4-node swing system
> aligned with Yang TPWRS 2023 Eq.(4), without touching any v1 main-path
> artifact.
>
> **Boundary respected**: v1 files (`kundur_cvs.slx`, `build_kundur_cvs.m`,
> `compute_kundur_cvs_powerflow.m`, `kundur_ic_cvs.json`) untouched.
> No SAC training, no NE39 changes, no shared-bridge / reward / agent edits.

## TL;DR

**v2 物理正确 ✅；可 promote 成主路径，但 RL 训练前需要调 D₀ 默认值。**

| Question | Answer |
|---|---|
| v2 是否物理上更接近论文 Eq.4 自治 swing 系统？ | **是** |
| 是否存在 common-mode drift？ | **否**（30s 内 0.0002 Hz，远低于物理意义阈值） |
| 是否需要弱 governor / average-frequency damping？ | **不需要** |
| 是否值得 promote 成主路径？ | **是**（在 RL 训练默认 D₀ 调小到 3-6 后） |

---

## Artifacts produced (v2 dry-run only)

```
scenarios/kundur/matlab_scripts/compute_kundur_cvs_powerflow_v2.m   (new)
scenarios/kundur/simulink_models/build_kundur_cvs_v2.m              (new)
scenarios/kundur/simulink_models/kundur_cvs_v2.slx                  (new)
scenarios/kundur/simulink_models/kundur_cvs_v2_runtime.mat          (new)
scenarios/kundur/kundur_ic_cvs_v2.json                              (new)
scripts/_tmp_run_pf_v2.py                                           (probe driver)
scripts/_tmp_run_build_v2.py                                        (probe driver)
scripts/_tmp_run_probes_v2.py                                       (probe driver)
results/harness/kundur/cvs_v2_dryrun/probes_summary.json            (raw)
results/harness/kundur/cvs_v2_dryrun/verdict.md                     (this file)
```

## Topology change (v1 → v2)

| Element | v1 | v2 |
|---|---|---|
| Buses | 7 (Bus_V1..V4, Bus_A, Bus_B, Bus_INF) | **5** (Bus_V1..V4, Bus_A, Bus_B) |
| Branches | 6 (L_v_1..4, L_tie, L_inf) | **5** (L_v_1..4, L_tie) |
| AC source | `AC_INF` ideal voltage source @ Bus_INF | **none** |
| Slack/reference | Bus_INF (NR slack), absolute frame | **VSG1 angle = 0** (relative frame, no slack) |
| Total Pm injection | 4 × 0.5 = 2.0 pu (1.2 pu absorbed by INF) | **4 × 0.2 = 0.8 pu** = total load (no hidden absorption) |
| NR closure check | implicit (slack absorbs) | **explicit** (`closure_residual_pu = 3.2e-4`, ≪ 1e-3 const-Z V² threshold) |

**Why Pm0 changed 0.5 → 0.2**: in v1, INF absorbed surplus (lossless network can't dissipate). Removing INF forces global balance `sum(Pm) = sum(load)` exactly. With Load_A + Load_B = 0.4 + 0.4 = 0.8 pu, Pm0 = 0.2 per VSG is the unique balanced setpoint. Documented in `kundur_ic_cvs_v2.json::global_balance.no_hidden_slack=true`.

## Probe results

### Probe 1 — zero-action 30s

| Metric | Value | Pass |
|---|---|---|
| All states finite (ω, δ, Pe) | True | ✅ |
| ω clip violation (>1.3 or <0.7) | False | ✅ |
| δ clip violation (>±π/2 - 0.05) | False | ✅ |
| df_max overall | **0.0002 Hz** | ✅ noise-floor |
| Common-mode drift over 30s | **+0.00016 Hz** | ✅ effectively zero |

→ **Self-contained 4-node swing is dynamically stable without external grounding.** D=18 alone provides sufficient damping to suppress drift even with no slack reference.

### Probe 2 — disturbance reach (VSG1 +0.2 pu Pm step at t=5s)

| Metric | v1 (with INF) | **v2** | Δ |
|---|---|---|---|
| df_max overall | 0.05 Hz (training-time observation) | **0.141 Hz** | +2.8x |
| Per-VSG df_max | — | [0.141, 0.141, 0.140, 0.140] Hz | strong synchronisation |

→ **Disturbance reaches the swing equation; INF is no longer pinning frequency.** All 4 VSGs respond near-identically (Proposition 1 holds when H/D are uniform).

### Probe 3 — H sensitivity at D=18

| Probe | M (=2H) | D | df_max [Hz] | ROCOF_max [Hz/s] |
|---|---|---|---|---|
| 3a | 6 | 18 | 0.146 | (computed) |
| 3b | 30 | 18 | 0.141 | (computed) |
| **Ratio H6/H30** | | | **1.04x** | **4.99x** |

→ **df peak insensitive to H** because system is over-damped (df ≈ steady-state ω_ss = ΔP/(N·D) = 0.2/72 = 0.139 Hz, exact match with 0.141). H only affects settling speed in this regime, not peak.

→ **ROCOF strictly 5x ratio = 30/6** (H ratio inverted). Confirms swing equation H ω̇ = ΔP - ... at the disturbance instant: dω/dt ∝ 1/H. **H is a valid dynamic control variable; it just shows up in ROCOF, not in steady-state df at high D.**

### Probe 4 — H sensitivity at D=3 (paper-baseline-range damping)

| Probe | M | D | df_max [Hz] | ROCOF_max [Hz/s] |
|---|---|---|---|---|
| 4a | 6 | 3 | **0.835** | **1.665** |
| 4b | 30 | 3 | **0.546** | **0.334** |
| **Ratio H6/H30** | | | **1.53x** | **4.99x** |

→ At D=3, transient peaks dominate (15s sim insufficient to settle for H=30, hence df ratio < 5x). df_max(H=6) = 0.835Hz matches ω_ss(D=3) = 0.2/(4·3) = 0.833Hz exactly — over-damped equilibrium reached for low H.

→ **Both df and ROCOF show H as a learnable control axis under D=3**.

## Comparison to paper Eq.(4)

Paper Eq.(4):
```
Δθ̇ = Δω
H Δω̇ = Δu − L Δθ − D Δω    (Kron-reduced N-node swing)
```

| Aspect | Paper | v2 |
|---|---|---|
| Per-node swing closure (H, D, Pm−Pe) | ✓ | ✓ (each VSG: IntW + IntD + RI2C + Pe = V·conj(I)) |
| Network coupling matrix | Kron-reduced N×N L on ESS nodes | 5-bus explicit network (4 ESS + 2 junctions Bus_A/B with const-Z load) — **mathematically equivalent** to a Kron-reduced 4×4 L plus distributed load injections |
| External grounding (slack / INF) | none | **none** ✅ |
| Common-mode drift | bounded by D | bounded by D (verified: 0.00016 Hz/30s) |
| Disturbance scaling | Δu_i directly into swing | Pm step into swing-eq summing junction directly ✅ |

**Verdict**: v2 is structurally aligned with Eq.(4). The only non-Kron simplification is keeping Bus_A/B as explicit junction nodes (rather than collapsing them into the L matrix), but the dynamics are identical because the loads are constant-impedance and lossless lines have no R — algebraically equivalent.

## Drift / governor analysis

The user-flagged risk was: removing INF leaves the system "ungrounded" (zero eigenvalue of L for common-mode). Probe 1 settles this:

- **Measured drift over 30s**: +0.00016 Hz (≈ 5 µpu/s).
- **Theoretical drift rate** under perfect symmetry: 0 (initial Pm = Pe ≈ 0.2 = exact balance per VSG by NR construction).
- The 0.00016 Hz residual is numerical solver noise, not a physical drift.

**Conclusion**: D-induced common-mode damping (D=18 at zero-state ω=1) is sufficient. **No virtual governor / average-ω feedback needed**. If future runs use D < 1 (extreme low-damping research), revisit.

## Promotion recommendation

**Recommend promoting v2 to main path** with these conditions:

1. **Promotion mechanics** (when ready):
   - Rename: `build_kundur_cvs.m` → `build_kundur_cvs_v1_legacy.m` (keep for diff/audit)
   - Rename: `kundur_cvs.slx` → `kundur_cvs_v1_legacy.slx`
   - Rename: `kundur_ic_cvs.json` → `kundur_ic_cvs_v1_legacy.json`
   - Promote v2: `build_kundur_cvs_v2.m` → `build_kundur_cvs.m` (and patch internal `mdl='kundur_cvs_v2'` back to `'kundur_cvs'`)
   - Same for `compute_kundur_cvs_powerflow_v2.m`, `kundur_ic_cvs_v2.json`, `kundur_cvs_v2.slx`
   - Update `model_profiles/kundur_cvs.json` if any field references v1 specifics (currently doesn't)
   - **No bridge code changes needed** — `step_strategy='cvs_signal'` dispatch is topology-agnostic

2. **Pre-training adjustment** (NOT in this dry-run scope, requires user authorization):
   - Default `D0_default` in build script: **18 → ~3-6** so that H is a learnable control axis
   - Or equivalently: keep D0=18 but train at D ∈ [1.5, 7.5] (i.e. `DD_MIN/DD_MAX` already span this)
   - The current `config_simulink.py::D_HI = 7.5` means D0=18 + ΔD ∈ [-1.5, 4.5] → D ∈ [16.5, 22.5] — entirely in over-damped regime
   - **Decision required**: align D0 with paper-feasible range or expand DD range to allow D ∈ [1, 30]

3. **Pe0 reset value in bridge config**:
   - Currently `pe0_default_vsg=tuple(VSG_P0_VSG_BASE.tolist())` reads from v1 IC → 0.5 pu
   - After promotion, this auto-tracks v2 IC → 0.2 pu via the same loader, **no code change needed**

## Items deliberately NOT done (per dry-run boundary)

- ❌ Did not modify `kundur_cvs.slx` (v1 main-path .slx untouched)
- ❌ Did not modify `build_kundur_cvs.m` / `compute_kundur_cvs_powerflow.m` / `kundur_ic_cvs.json`
- ❌ Did not modify NE39 anything
- ❌ Did not modify shared bridge `engine/simulink_bridge.py`, reward, or agent code
- ❌ Did not run any SAC episode (no 50ep / 200ep / 2000ep)
- ❌ Did not change `config_simulink.py` D0/M0 defaults
- ❌ Did not delete or overwrite any prior CVS Gate result

## Open questions for user

1. **Promote now or after a fuller H/D sweep?** Current dry-run only tested H ∈ {6, 30} × D ∈ {3, 18}. A 4×4 grid (H × D) would map the full operating envelope but takes ~2 minutes more sim time.
2. **Default D0 adjustment**: should I draft a separate config-only PR proposing `D0_default: 18 → 3` (or expanding DD range), or leave that decision for after promotion?
3. **What's the right way to dispose of v1 artifacts?** Rename to `_legacy` (preserves history, large repo footprint) vs delete vs git-mv to an archive subdir?

## Raw data

Full numerical traces and per-VSG metrics: `probes_summary.json` in this directory.
