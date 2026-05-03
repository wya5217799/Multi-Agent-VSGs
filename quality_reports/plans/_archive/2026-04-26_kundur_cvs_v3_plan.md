# Kundur CVS v3 — Paper-Aligned Build Plan

> **Status**: DRAFT (awaiting user approval before Phase 1 execution)
> **Date**: 2026-04-26
> **Goal**: Restore the Yang TPWRS 2023 16-bus Modified Kundur topology
>          (4 SG + 2 wind farms + 4 ESS) on top of the proven CVS clean
>          controlled-source design pattern, using the v2 RL/training stack
>          unchanged. Target: complete paper reproduction including
>          baseline comparisons (-8.04 / -12.93 / -15.2).

---

## 1. Why v3

### 1.1 What v2 achieves

The B1-locked CVS v2 path (commit history `cac007f` → `de5a11c` → `e5ed9d1`
→ `762dab5`) gives us a verified RL/training basement:

- 5-bus self-contained 4-VSG swing system (no INF bus)
- 500/500 ep clean training, no NaN/clip/forced-stop
- r_f% mean 2.5–4.8 % across 500 ep windows
- SAC trajectory healthy (alpha 1.0 → 0.05 floor at ep~57; critic_loss
  converged 4 orders of magnitude)
- Plan X / P1+P2 monitor + file-lock hardening

### 1.2 Why v2 is not paper-faithful

Three explicit divergences from Yang TPWRS 2023:

1. **Network topology** — v2 has 5 buses (4 PV + 2 PQ junctions), 0 SG,
   0 wind farms, 80 MW total load. Paper has 16 buses, 3 SG (G1/G2/G3),
   2 wind farms (W1=700 MW, W2=100 MW), 2 large loads (Bus 7=967 MW,
   Bus 9=1767 MW), tie-line Bus 7→8 (triple parallel 110 km).
2. **Disturbance mechanism** — v2 fires a Pm step on a single hardcoded
   ESS (VSG[0]). Paper randomises both the disturbance bus and the
   magnitude across 100 train + 50 test scenarios (load step / wind
   trip / communication failure).
3. **Reward shaping (B1 PHI = 1e-4)** — direct consequence of (1)+(2).
   v2's symmetric topology + symmetric disturbance forces r_f → 0 by
   construction, so we had to scale `φ_h = φ_d` from paper-level 1.0
   down to 1e-4 to make r_f% visible in reward (achieved 4.10 % mean).
   Paper's φ_f=100, φ_h=φ_d=1 is **not** what v2 actually runs with.

v3 directly attacks (1) and (2). If v3's natural network heterogeneity
plus paper-faithful disturbance structure produce strong-enough r_f
signal, **v3 may also be able to drop the B1 PHI×1e-4 hack** (Phase 4
will determine this empirically).

### 1.3 Goal hierarchy

| Tier | Goal | Status |
|------|------|--------|
| T0 | RL / training plumbing reliable | ✅ done (v2 + B1 + monitor hardening) |
| T1 | Paper-faithful 16-bus topology with multi-source dynamics | this plan (v3) |
| T2 | Paper-style random-bus disturbance (load step + wind trip) | this plan (v3) |
| T3 | Paper-faithful reward shaping (φ_h=φ_d=1) | conditional on T1+T2 success |
| T4 | Paper baseline comparison (DDIC vs adaptive vs no-control) | post-v3 |

This plan covers T1, T2, T3-conditional, sets up T4.

---

## 2. Scope and boundary

### 2.1 v2 stays alive as the clean RL baseline

v2 artefacts are NOT touched:

- `scenarios/kundur/simulink_models/kundur_cvs.slx`
- `scenarios/kundur/simulink_models/build_kundur_cvs.m`
- `scenarios/kundur/matlab_scripts/compute_kundur_cvs_powerflow.m`
- `scenarios/kundur/kundur_ic_cvs.json`
- `scenarios/kundur/model_profiles/kundur_cvs.json`

v3 is an **additive new path**. Same scenario_id (`kundur`), same
contract.py constants (n_agents=4, fn=50, dt=0.2, obs_dim=7, act_dim=2),
selected by setting `KUNDUR_MODEL_PROFILE=…/kundur_cvs_v3.json` env var.

### 2.2 Hard constraints

1. Do NOT touch NE39 (`scenarios/new_england/`).
2. Do NOT touch shared bridge `engine/simulink_bridge.py` step_strategy
   enum unless absolutely required (CVS dispatch already exists via
   `cvs_signal`).
3. Do NOT touch SAC agent / agents/, training_callback, monitor (P2 has
   already configured Kundur warns).
4. Do NOT reuse SPS path (`build_kundur_sps.m`, `kundur_vsg_sps.slx`,
   `kundur_sps_candidate.json`) — RC-A unresolved root cause.
5. Do NOT reuse breaker/topology-switch disturbance (FastRestart killer).
6. Do NOT reuse v1 powerlib `kundur_vsg.slx` (IntW saturation root cause).

### 2.3 Allowed changes outside `scenarios/kundur/`

- `engine/simulink_bridge.py`: only if a NEW step_strategy is genuinely
  required (preferred: extend CVS dispatch path with model_name routing).
- `env/simulink/kundur_simulink_env.py`: extend `apply_disturbance` for
  new disturbance types (`load_step_random_bus`, `wind_trip`). Keep
  default = current asym single-VSG so v2 contract is unchanged.

---

## 3. Physical design

### 3.1 Topology (paper Sec.IV-A)

```
Area 1                          Area 2
┌───────────────────┐          ┌───────────────────┐
│ G1(Bus1)          │          │ G3(Bus3)          │
│ Sn=900MVA P0=700  │          │ Sn=900MVA P0=719  │
│ H=6.5  D=5  R=.05 │          │ H=6.175 D=5 R=.05 │
│                   │          │                   │
│ G2(Bus2)          │          │ W1(Bus4)          │
│ Sn=900 P0=700     │          │ 700 MW const power│
│ H=6.5 D=5 R=.05   │          │ Sn=900 MVA        │
│                   │          │                   │
│  Bus7(967MW load) │  L_tie   │ Bus9(1767MW load) │
│  ←──── triple parallel 110km tie-line ────→     │
└─────────┬─────────┘          └─────────┬─────────┘
          │                              │
       ES1(Bus12→7)                   ES2(Bus16→8 area)
       ES3(Bus14→10)                  ES4(Bus15→9)
       (4 ESS, M0=12, D0=3, Sn=200 MVA each)
                              │
                          W2(Bus11→Bus8 area)
                          100 MW const power
                          Sn=200 MVA
```

### 3.2 Implementation pattern: CVS clean for ALL sources

**Critical design choice**: every dynamic source (G1/G2/G3/ESS1-4) is
implemented as a Controlled Voltage Source driven by a signal-domain
swing equation, identical to v2's ESS pattern. Wind farms (W1/W2) are
Programmable Voltage Sources at constant power (no swing eq), trippable
via base-ws Constant block.

This is NOT the paper's ee_lib/SPS implementation. We deliberately use
CVS clean throughout because:

- v2 has proven CVS clean is numerically stable + Phasor-fast (~9 s/ep)
- avoids the v1 powerlib IntW saturation root cause (Pe feedback chain)
- avoids the SPS RC-A root cause (Three-Phase Source PhaseAngle semantics)
- bridge `cvs_signal` step_strategy is already built and tested

The paper's choice of ee_lib SG blocks vs our CVS swing-eq is a model
implementation choice, not a physical model choice — both implement
Eq.1 `H ω̇ + D Δω = Δu - ΔP`. Equivalence will be verified in Phase 2.

### 3.3 Per-source swing-eq closure (signal domain)

For each generator i ∈ {G1, G2, G3, ES1-4}:

```
   Pm_i(t) → Sum → /M_i → ∫ → ω_i(t) ────────┐
              ↑     ↑                          │
             Pe_i  D_i·(ω-1)                  │
              │                                ↓
              │                            wn_const · (ω-1)
              │                                │
              │                                ↓
              │                                ∫ → δ_i(t)
              │                                │
              │              (Pm/Sn or Pm/Sbase)│
              │                                ↓
              │                         cos/sin → ×Vmag → RI2C → CVS_i (electrical)
              │                                                     │
              └────────────── Pe = Re(V·conj(I))/Sbase ←───────────┘
                                  ^Power Sensor
```

Differences vs v2 ESS swing-eq:

- G1/G2/G3: H, D, Sn = 900 MVA (vs ESS Sn=200 MVA). Add governor
  droop term: `Pm_i = Pm0_i - (1/R_i)·(ω_i - 1)`. R = 0.05 pu.
- W1/W2: no swing eq. Just Programmable Voltage Source with constant
  P0 sourced from real/reactive power injection.
- ESS: identical to v2 (M=12, D=3, Sn=200 MVA), with RL-controlled
  ΔM, ΔD via base-ws variables M_i, D_i.

### 3.4 Pm step disturbance (per source) — PRESERVED from v2

Each dynamic source keeps the v2 Pm-step gating:
```
Clock_global → ≥ Pm_step_t_i → Cast → × Pm_step_amp_i → Sum into Pm_total_i
```
This works for SG-side or ESS-side perturbations.

### 3.5 Load step disturbance (paper-faithful)

NEW for v3: at Bus 7 and Bus 9 (real load buses), add a parallel
toggleable load using the same Constant + Relational Operator pattern:

```
Clock_global → ≥ LoadStep_t_k → × LoadStep_amp_k → drives a parallel
                                                    Series RLC R-only branch's
                                                    conductance variable
```

This replaces the v1 SPST Switch / TripLoad approach (which broke
FastRestart). Implementation: pre-instantiate a parallel R load whose
conductance is computed as `G_perturb_k(t) = LoadStep_amp_k(t) /
(Vbase² / Sbase)`. Setting amp=0 means zero conductance (open circuit
equivalent at load).

### 3.6 Wind farm trip (paper Sec.IV-G test scenario)

For W1 and W2: a Programmable Voltage Source with a workspace-controlled
amplitude scaling. Setting `WindAmp_k = 0` at trip time effectively
isolates the wind farm. This is NOT a topology change — the source is
always present, just at zero output post-trip.

---

## 4. Data flow

```
1. Parameters (constants)
   ↓
   build_powerlib_kundur.m physical params (gen_cfg, wind_cfg, VSG params,
   network impedance) → COPY VALUES into build_kundur_cvs_v3.m

2. Initial Condition (IC)
   ↓
   compute_kundur_cvs_v3_powerflow.m
   ↓ NR solve 16-bus network (4 PV + 2 wind PV + 10 PQ network nodes)
   ↓ output: per-source delta0, Vmag, Pm0
   ↓
   kundur_ic_cvs_v3.json   (closure check: no hidden slack, V² const-Z OK)

3. Simulink model
   ↓
   build_kundur_cvs_v3.m (reads kundur_ic_cvs_v3.json)
   ↓ 16-bus electrical layer + 7 swing-eq closures (3 SG + 4 ESS)
   ↓ + 2 wind farms (programmable voltage source)
   ↓ + 6 Pm-step gating clusters (SG + ESS)
   ↓ + 2 LoadStep clusters (Bus 7 + Bus 9)
   ↓ + 2 WindAmp clusters (W1 + W2)
   ↓ + ToWorkspace loggers (omega/delta/Pe per dynamic source)
   ↓
   kundur_cvs_v3.slx + kundur_cvs_v3_runtime.mat

4. Bridge/Env
   ↓
   model_profiles/kundur_cvs_v3.json (model_name=kundur_cvs_v3,
                                       step_strategy=cvs_signal)
   ↓
   config_simulink.py: profile-aware BridgeConfig dispatch
   ↓
   env/simulink/kundur_simulink_env.py: extended apply_disturbance with
                                        per-disturbance-type routing

5. Training
   ↓
   train_simulink.py (UNCHANGED — picks up new model via env var)
```

---

## 5. Phase-by-phase execution

### Phase 1 — Physical foundation (1 week)

**Goal**: produce kundur_cvs_v3.slx + kundur_ic_cvs_v3.json, both
internally consistent and reading from the paper physical parameters.

| Task | Deliverable | Verdict criterion |
|---|---|---|
| 1.1 Write `compute_kundur_cvs_v3_powerflow.m` (16-bus NR) | new file in `scenarios/kundur/matlab_scripts/` | NR converges (max_mismatch < 1e-10), closure_ok = True |
| 1.2 Run powerflow → `kundur_ic_cvs_v3.json` | new IC file | All 7 dynamic source delta0_deg in (-π/2, π/2); no hidden slack (closure check) |
| 1.3 Write `build_kundur_cvs_v3.m` (extends v2 build to 16-bus + 3 SG swing-eq + 2 wind PVS) | new file in `scenarios/kundur/simulink_models/` | Build completes with 0 errors; 0 algebraic loops; FastRestart compiles |
| 1.4 Run build → `kundur_cvs_v3.slx` + `kundur_cvs_v3_runtime.mat` | new files | sim() runs StopTime=0.5 without crash |

**Artefact location**:
- `scenarios/kundur/matlab_scripts/compute_kundur_cvs_v3_powerflow.m`
- `scenarios/kundur/simulink_models/build_kundur_cvs_v3.m`
- `scenarios/kundur/kundur_ic_cvs_v3.json`
- `scenarios/kundur/simulink_models/kundur_cvs_v3.slx`
- `scenarios/kundur/simulink_models/kundur_cvs_v3_runtime.mat`

**Wall time estimate**: 4-6 days (NR + build + iteration on FastRestart
compile errors).

**Phase 1 GO/NO-GO** → proceed to Phase 2 only if all 4 verdicts pass.

---

### Phase 2 — Dry-run physics probes (3-5 days)

**Goal**: prove v3 physics is correct and well-conditioned BEFORE any
RL training, mirroring the v2 dry-run protocol.

| Probe | Method | Pass criterion |
|---|---|---|
| 2.1 30s zero-action stability | All sources at nominal Pm, no perturbation, sim 30s | ω ∈ [0.999, 1.001] over full 30s; \|δ\| < π/2 - 0.05; Pe within ±5% Pm0; common-mode drift < 0.01 Hz/30s |
| 2.2 Pm step reach (per source) | Apply +0.2 pu Pm step to G1, then G2, G3, ES1-4 individually | Each source's df_max responds in [0.05, 5] Hz; physical signal not pinned |
| 2.3 Bus 7 load step | +200 MW step at Bus 7 t=5s, sim 15s | df_max system-wide in [0.1, 2] Hz; no clip; settle within ~3s |
| 2.4 Bus 9 load step | +200 MW step at Bus 9 t=5s, sim 15s | Same as 2.3 |
| 2.5 W2 trip | Set WindAmp_W2 = 0 at t=5s (100 MW lost), sim 15s | df_max nadir ≈ 100 MW / (Σ H system inertia); no clip |
| 2.6 H sensitivity | Set ESS H to 6 vs 30, fix D=3, single ESS Pm step | ROCOF ratio H6/H30 ≈ 5x (proves H is control axis) |
| 2.7 D sensitivity | H=12 fixed, D ∈ {1.5, 7.5}, single ESS Pm step | df steady-state ratio D1.5/D7.5 ≈ 5x (proves D is control axis) |
| 2.8 Cross-check vs ODE (oracle) | Same Pm step, compare v3 Simulink vs `env/ode/multi_vsg_env.py` (Kron-reduced equivalent) | Reward at episode end agrees to within 5% |

**Artefact**: `results/harness/kundur/cvs_v3_dryrun/{summary.json, verdict.md}`

**Phase 2 GO/NO-GO** → proceed to Phase 3 if (2.1, 2.2, 2.3, 2.6, 2.7) all
PASS. (2.4, 2.5, 2.8) are informational; failures here are diagnosed
but not blocking.

---

### Phase 3 — Bridge + env integration + 5ep smoke (3-5 days)

**Goal**: hook v3 into the existing training pipeline and verify a
5-episode round-trip.

| Task | Deliverable | Pass criterion |
|---|---|---|
| 3.1 New `model_profiles/kundur_cvs_v3.json` | profile JSON | schema.json validation passes; profile loadable |
| 3.2 Extend `scenarios/kundur/config_simulink.py` v3 dispatch | edited file | `KUNDUR_MODEL_PROFILE=…/kundur_cvs_v3.json python -c "from … import KUNDUR_BRIDGE_CONFIG"` returns the right model_name + per-source config |
| 3.3 Extend `env/simulink/kundur_simulink_env.py` apply_disturbance with `disturbance_type` parameter (default = current 'pm_step_single_vsg') | edited file | v2 path (default disturbance) still passes 5ep smoke without changes |
| 3.4 Add new disturbance types: `pm_step_random_source`, `load_step_random_bus`, `wind_trip` | same file | Each produces non-zero df response in 1ep manual test |
| 3.5 Run 5ep smoke under v3 | new run | 5/5 completion; per-ep df ∈ [0.1, 5] Hz; no NaN/Inf/clip; events.jsonl shows correct disturbance routing |

**Phase 3 GO/NO-GO** → if 5ep smoke passes, proceed to Phase 4.

---

### Phase 4 — 50ep gate + dual-PHI experiment (1 week)

**Goal**: determine whether v3's physical heterogeneity + paper-style
disturbance can produce strong-enough r_f signal to **drop B1 PHI×1e-4
back to paper's φ_h = φ_d = 1**.

| Run | Config | Purpose |
|---|---|---|
| 4.1 v3-B1 50ep | v3 + B1 PHI=1e-4 + asym single-VSG[0] | Baseline: v3 with v2's reward shaping, single source disturbance |
| 4.2 v3-paper-φ 50ep | v3 + φ_h=φ_d=1 + paper-style random-bus disturbance | Check if natural physics produces r_f% > 5 % under paper PHI |
| 4.3 v3-mixed 50ep | v3 + φ_h=φ_d=0.01 (intermediate) + paper-style | Compromise option if 4.2 r_f% too small |

**Compare on scale-invariant metrics** (per the lesson from B1 200ep
verdict — eval reward absolute values not comparable across PHI configs):

- r_f% mean (target: > 5 %)
- df mean / df max
- max_power_swing
- H/D action distribution (no pinning)
- action std (no collapse)
- critic_loss bounded
- alpha decay shape (target: NOT hitting floor before ep 200, unlike v2)

**Phase 4 GO/NO-GO**:
- If 4.2 (paper PHI) gives r_f% > 5 % AND all hygiene PASS → drop B1
  override, lock paper PHI for v3.
- If 4.2 fails but 4.3 (intermediate PHI) PASSES → lock 0.01 instead
  of 1e-4. Document as "paper-faithful within 100x of original".
- If neither works → keep B1 PHI=1e-4 for v3 too. Document as
  "v3 reduces topology+disturbance gaps but reward gap persists".

---

### Phase 5 — 200ep / 500ep / 2000ep training + paper baselines (1-2 weeks)

**Goal**: full paper reproduction including comparison baselines.

| Task | Deliverable |
|---|---|
| 5.1 v3 200ep gate (re-run B1 protocol) | results/sim_kundur/runs/kundur_simulink_v3_…/ |
| 5.2 v3 500ep gate | same |
| 5.3 v3 2000ep training (paper-spec full training) | same |
| 5.4 Implement adaptive inertia [25] baseline | `agents/adaptive_inertia.py` (new) |
| 5.5 Implement centralized SAC baseline | `agents/centralized_sac.py` (new) |
| 5.6 50-test-scenario eval protocol (paper Sec.IV-C) | `scenarios/kundur/evaluate_v3_paper.py` |
| 5.7 Direct numerical comparison vs paper -8.04 / -12.93 / -15.2 | results/harness/kundur/cvs_v3_paper_comparison/verdict.md |

**Phase 5 success criterion**: DDIC vs adaptive vs no-control numerical
comparison produces results within ±50% of paper's -8.04 / -12.93 /
-15.2 figures. (Note: exact match unlikely due to: random seed
differences, exact disturbance scenario set unknown — paper Q1, ESS bus
location unknown — paper Q5, SAC implementation differences.)

---

## 6. Asset reuse summary

Detailed audit lives in this session's transcript. Compressed reference:

### Direct reuse (zero changes)
- All RL/SAC code (`agents/`)
- Training infrastructure (`utils/{run_protocol, monitor, training_*}`)
- Engine layer (`engine/{matlab_session, training_launch, run_schema}`)
- General MATLAB helpers (`slx_helpers/*.m` top level, 31 files)
- CVS-specific bridge helpers (`slx_helpers/vsg_bridge/slx_step_and_read_cvs.m`,
  `slx_episode_warmup_cvs.m`, `slx_extract_state.m`)
- Bridge `cvs_signal` step_strategy in `engine/simulink_bridge.py`
- Contract layer (`scenarios/contract.py KUNDUR`)
- SAC hyperparameters (`scenarios/config_simulink_base.py`)
- Profile schema (`scenarios/kundur/model_profiles/schema.json`)
- IC reference data (`scenarios/kundur/kundur_ic.json`)
- Probe templates (`probes/kundur/gates/p4_d2 / d3 / d4 / smoke / dispatch_verify`)

### Reuse after adaptation
- `compute_kundur_powerflow.m` (15-bus → 16-bus)
- `compute_kundur_cvs_powerflow.m` v2 (5-bus algorithm extended to 16-bus)
- `build_kundur_cvs.m` v2 (CVS pattern template extended to multi-source)
- Physical parameter table from `build_powerlib_kundur.m` (gen_cfg / wind_cfg / VSG)
- IEEE Kundur 12.4 SG params from `upgrade_generators.m` (data only, not blocks)
- `scenarios/kundur/config_simulink.py` (add v3 dispatch branch)
- `env/simulink/kundur_simulink_env.py` (extend apply_disturbance)
- ODE/ANDES path as algorithm correctness oracle (cross-check, not direct reuse)

### Do NOT reuse
- All SPS path artefacts (build_kundur_sps.m, kundur_vsg_sps.slx,
  kundur_sps_candidate.json)
- v1 powerlib `kundur_vsg.slx` (IntW saturation root cause)
- `add_disturbance_and_interface.m` Switch-based load swap
  (FastRestart killer)
- `build_kundur_simulink.m` (60Hz, wrong port maps)
- `kundur_two_area.slx` (60Hz, early version)
- `legacy_component_tests/` (60Hz era)
- `build_kundur_cvs_v1_legacy.m` + `kundur_cvs_v1_legacy.slx`
- Bridge `phang_feedback` step_strategy (SPS-era)

### Must build new
- `compute_kundur_cvs_v3_powerflow.m` (Phase 1)
- `build_kundur_cvs_v3.m` (Phase 1)
- `kundur_ic_cvs_v3.json` (Phase 1, NR output)
- `model_profiles/kundur_cvs_v3.json` (Phase 3)
- v3 dispatch in `config_simulink.py` (Phase 3)
- v3 disturbance routing in `env/simulink/kundur_simulink_env.py` (Phase 3)
- v3 probes (Phase 2): `v3_topology_check.py`, `v3_nr_ic_validate.py`,
  `v3_30s_zero_action.py`, `v3_dist_sweep.py`, `v3_h_sensitivity.py`
- `agents/adaptive_inertia.py`, `agents/centralized_sac.py` (Phase 5)
- `scenarios/kundur/evaluate_v3_paper.py` (Phase 5)

---

## 7. Risks and mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| SG swing-eq via CVS not validated; v3 extends ESS pattern to SG with governor droop | **High** | Phase 2.6/2.7 H/D sensitivity probes catch this early; cross-check with ODE oracle in 2.8 |
| Wind farm model unspecified in paper | Medium | First version: constant-power Programmable Voltage Source + workspace amp control. Easy to upgrade later. |
| 16-bus FastRestart compile time (estimate 10-15 s, 5x v2) | Medium | Acceptable: per-run cost only, not per-episode. Monitor in Phase 1.4 |
| B1 PHI=1e-4 still required after v3 | Medium | Phase 4 dual-PHI experiment directly answers; if so, document as "physics gap remains" |
| Paper Q5 ambiguous (ESS bus locations) | Low | Use build_powerlib_kundur.m's choice (Bus 12/16/14/15 → 7/8/10/9), document |
| Paper Q7 ambiguous (H/D dimension) | Medium | Phase 4 will reveal if v3 lets us widen action bounds back to paper [-100,300]/[-200,600] |
| NR powerflow 16-bus convergence | Low | compute_kundur_powerflow.m already converges on 15-bus; +1 bus negligible |
| v3 ep wall-time inflation (estimate 30-60 s/ep vs v2 ~9 s/ep) | Medium | 500ep training: 4-8 hours instead of 75 min. Acceptable but slows iteration. Consider buffer/learning loop tuning if too slow |
| Real load step at Bus 7/9 (large loads, 967/1767 MW) may overshoot disturbance budget | Medium | Use scaled load step (e.g. ±100 MW max) similar to NE39 + adjust DIST_MIN/MAX |
| Governor droop on G1-G3 may interfere with reward signal (mechanical regulation hides r_f) | Medium | Phase 2.3/2.4 will reveal; if so, set R = 0.05 (mild droop) per paper, accept regulation as part of physics |
| Centralized SAC baseline (Phase 5.5) is paper Sec.IV-F, requires understanding paper's exact CTDE setup | Low | Defer until 5.4 done; can use SB3 SAC with all 4 agents' obs/act concatenated |

---

## 8. Decision gates

```
Phase 1 → 2:  IC NR converged AND .slx builds AND sim() runs 0.5s without crash
Phase 2 → 3:  Probes 2.1, 2.2, 2.3, 2.6, 2.7 PASS
              (2.4, 2.5, 2.8 informational)
Phase 3 → 4:  5ep smoke: 5/5 done, no NaN/clip, df responds correctly
              for each disturbance type
Phase 4 → 5:  Dual-PHI experiment: at least ONE of {paper-φ,
              intermediate-φ} produces r_f% > 5 % AND all hygiene PASS
Phase 5 done: Numerical comparison vs paper -8.04/-12.93/-15.2 within
              ±50%, OR documented gap with root cause
```

If a decision gate fails, the next sub-step is **diagnose-only**, NOT
proceed-with-workaround. Failures upstream of Phase 4 mean the v3
physical foundation is unsound and must be fixed before training
investment.

---

## 9. Total time estimate

| Phase | Duration | Cumulative |
|---|---|---|
| 1 — Physical foundation | 1 week | 1 week |
| 2 — Dry-run probes | 3-5 days | ~1.5 weeks |
| 3 — Integration + 5ep smoke | 3-5 days | ~2 weeks |
| 4 — 50ep + dual-PHI gate | 1 week | ~3 weeks |
| 5 — Long training + baselines | 1-2 weeks | ~4-5 weeks |

Buffer for surprises: +1 week.

**Total: 4-6 weeks of focused work**, vs >6 weeks for a full Tier-3-C
NE39-style rewrite.

---

## 10. Out-of-scope (explicit non-goals)

- Touching NE39 in any way
- Modifying SAC algorithm or training loop
- Implementing communication delay model (paper uses for test only,
  not training)
- Reproducing weak-grid experiment (Sec.IV-F N=2,4,8 — separate plan)
- NE39 reproduction with v3 patterns (separate plan, after Kundur v3
  succeeds)
- Resolving paper Q7 (H/D dimension) — accepted as ambiguity, work
  around with measurements

---

## 11. Open questions to resolve during execution

1. **Q5 (ESS bus location)**: Use build_powerlib_kundur.m's Bus
   12/16/14/15 → 7/8/10/9 by default; revisit if Phase 2 reveals
   physics issues.
2. **Wind farm model fidelity**: Start with constant-power
   Programmable Voltage Source. Upgrade to Type-3/4 wind turbine
   only if Phase 5 baseline comparison fails specifically due to
   wind dynamics.
3. **Governor droop on SG**: Paper Sec.II-A doesn't specify SG
   internal control; default to R=0.05 (per build_powerlib_kundur.m)
   = standard practice. Disable if it interferes with r_f signal.
4. **Train scenario set**: Paper says "100 random scenarios" but
   doesn't specify if fixed pool or per-ep resample. Default:
   per-ep resample (current v2 behaviour). Document as project
   choice if it matters.

---

## 12. References

- Yang et al., IEEE TPWRS 2023 (DOI 10.1109/TPWRS.2022.3221439)
- `docs/paper/yang2023-fact-base.md` (project paper fact base)
- v2 dry-run verdict: `results/harness/kundur/cvs_v2_dryrun/verdict.md`
- B1 PHI gate verdict: `results/harness/kundur/cvs_v2_dryrun/phi_b1_verdict.md`
- B1 200ep gate verdict: `results/harness/kundur/cvs_v2_dryrun/b1_200ep_gate_verdict.md`
- Plan X / P1+P2 commits: `e5ed9d1`, `762dab5`
- Asset audit: this session's transcript
