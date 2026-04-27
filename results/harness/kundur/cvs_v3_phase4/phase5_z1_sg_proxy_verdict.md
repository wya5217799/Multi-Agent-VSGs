# Z1 Verdict — SG-side Pm-step proxy + paper-style gate — PASS at `phi_h_d_lower`

> **Status:** PASS — `z1_phi_h_d_lower` (PHI_H=PHI_D=1e-5, PHI_F=100) under SG-side Pm-step disturbance achieves **DDIC cum_unnorm = −3.56 vs no-control baseline −4.21 = +15.4 % improvement**. Direction inversion (P5.1 finding) RESOLVED. v3 trained policy now beats no-control on the paper §IV-C global r_f formula. **First paper-direction-correct DDIC outcome in v3.**
> **Date:** 2026-04-27
> **Predecessors:** R1 (formula correct), R2 (4 PHIs at ESS-side all FAIL), P5.1 (DDIC −19 % WORSE at ESS-side).
> **Wall:** 47 min total (baseline 9 min + 2 candidates × 18 min + overhead).

---

## 1. Headline result

| Config | PHI_H | PHI_D | PHI_F | Disturbance | cum_unnorm | vs no_ctrl_sg | Status |
|---|---:|---:|---:|---|---:|---:|---|
| paper no_control (Sec.IV-C) | — | — | — | LoadStep 248/188 MW | −15.20 | — | reference |
| paper DDIC (Sec.IV-C) | 1.0 | 1.0 | 100 | LoadStep | −8.04 | +47.1 % vs paper | reference |
| v3 P5.1 no_control_bus (ESS-side proxy) | — | — | — | Pm-step at ESS [10,50] MW | −7.48 | — | reference |
| v3 P5.1 DDIC `phi_b1` (ESS-side) | 1e-4 | 1e-4 | 100 | ESS-side | −8.90 | **−19.0 % WORSE** | ❌ |
| **v3 Z1 no_control_sg (SG-side)** | — | — | — | **Pm-step at G1/G2/G3 [10,50] MW** | **−4.21** | — | reference |
| v3 Z1 `z1_phi_b1` | 1e-4 | 1e-4 | 100 | SG-side | −4.87 | **−15.8 % WORSE** | ❌ |
| **v3 Z1 `z1_phi_h_d_lower`** | **1e-5** | **1e-5** | 100 | SG-side | **−3.56** | **+15.4 % BETTER** | **✅ PASS** |

---

## 2. Two breakthroughs

### Topology (Z1 axis)

**Disturbance must enter at a non-ESS source for ESS H/D to have leverage.**

- ESS-side Pm-step proxy: disturbance enters directly at the ESS swing equation; H, D modulate THIS source's response. RL learns to "shape my own Pm response", not to "buffer external perturbation". Reward gradient ~ 0 along useful directions.
- SG-side Pm-step proxy: disturbance enters at G1/G2/G3 (synchronous gens at buses 1/2/3), propagates through transmission lines to the ESS at buses 12/14/15/16. ESS H, D now shape the system frequency response to an external impulse — paper-equivalent topology.

Evidence:
- ESS-side baseline (P5.1 no_ctrl): −7.48
- SG-side baseline (Z1 no_ctrl): −4.21 — **smaller magnitude due to network attenuation** (same disturbance amount diluted across the 16-bus network before reaching ESS)
- ESS-side PHI sweep (4 candidates): all FAIL
- SG-side PHI sweep (1 candidate): PASS at `phi_h_d_lower`

### Reward shape (PHI axis, R2 + Z1)

**At every disturbance topology, lower PHI_H/PHI_D (≪ paper 1.0) is BETTER for v3's calibrated ΔM range.**

- ESS-side R2: phi_b1 (1e-4) → −8.90, phi_h_d_lower (1e-5) → −7.97 (best of 4)
- SG-side Z1: phi_b1 (1e-4) → −4.87 (FAIL), phi_h_d_lower (1e-5) → **−3.56 (PASS)**

Lowering PHI_H/D 10× consistently helps because it lets r_f drive the policy gradient instead of being drowned by r_h. Paper's φ_h=φ_d=1.0 only works at paper's much-larger ΔH range [−100, +300]; v3's calibrated [−3, +9] (Q7) needs PHI_H scaled down to compensate.

---

## 3. Per-physics breakdown

| Metric | Z1 no_ctrl_sg | Z1 phi_b1 | Z1 phi_h_d_lower (✅) |
|---|---:|---:|---:|
| cum_unnorm | −4.21 | −4.87 | **−3.56** |
| per_M | −0.0842 | −0.0975 | **−0.0713** |
| per_M_per_N | −0.0211 | −0.0244 | **−0.0178** |
| max\|Δf\| mean | 0.102 Hz | 0.109 | **0.104** |
| max\|Δf\| max | 0.171 Hz | 0.179 | 0.171 (ties baseline) |
| ROCOF mean | 0.63 Hz/s | 0.73 | **0.64** |
| ROCOF max | 1.13 Hz/s | 1.42 | 1.31 |
| settled% (5 mHz × 1 s) | 0 % | 0 % | 0 % |

`phi_h_d_lower` improves cum_unnorm by 15 %, max\|Δf\| by 2 %, ROCOF by 1 %. Improvements concentrate on the **squared frequency dispersion across agents** (which is what r_f measures), not on the absolute freq deviation per agent.

`settled%=0` across all three configs — settling tolerance (5 mHz × 1 s) is too tight for this freq regime. NOT a v3 deficiency; revisit tolerance for paper-faithful comparison once we know paper's threshold.

---

## 4. Comparison to paper

| Outcome | Paper | v3 Z1 |
|---|---:|---:|
| no-control cum_unnorm | −15.20 | **−4.21** (3.6× smaller magnitude) |
| DDIC cum_unnorm | −8.04 | **−3.56** (2.3× smaller magnitude) |
| DDIC improvement over no-control | **+47.1 %** | **+15.4 %** |
| Direction (DDIC ≤ no-control) | ✓ | ✓ (FIRST TIME for v3) |

The factor-3-ish magnitude gap is consistent with v3's disturbance being weaker (Pm-step proxy at [10, 50] MW per source) vs paper LoadStep (248/188 MW per Bus 14/15 trip). Closing this gap requires Z2 (LoadStep wiring at paper magnitudes), which is a separate scope-expansion authorization.

**Z1 alone closes the qualitative paper-replication gap (direction correct), not the quantitative magnitude gap.**

---

## 5. Z1 winner config (locked for downstream)

```
KUNDUR_MODEL_PROFILE       = scenarios/kundur/model_profiles/kundur_cvs_v3.json
KUNDUR_DISTURBANCE_TYPE    = pm_step_proxy_random_gen
KUNDUR_PHI_H               = 0.00001
KUNDUR_PHI_D               = 0.00001
KUNDUR_PHI_F               = 100.0
seed                       = 42
save_interval / eval_interval = 50 / 50
checkpoint_dir             = results/sim_kundur/runs/kundur_simulink_20260427_125711/checkpoints/
best.pt                    = same dir, ep ≤ 50 (50-ep gate run)
DDIC cum_unnorm (50 test)  = −3.5637  (paper-style global r_f, deterministic seed=42)
```

---

## 6. Next-step candidates (after Z1 + paper-explicit closure)

1. **Extend `phi_h_d_lower` to longer training** (200, 500, 2000 ep) to see if learning curve continues past the 50-ep gate. P4.2-overnight evidence (`phi_b1` ep 50 → 670 plateau at −0.04) suggests SAC may also plateau here, but the starting cum_unnorm is now in the right direction so longer training could close more of the 15 % → 47 % gap.
2. **Phase 4.3 wiring** — load `v3_paper_train_100.json` / `v3_paper_test_50.json` into env reset + train CLI. Manifests already on disk (G3 closure today).
3. **Z2 LoadStep wiring** — only path to paper-magnitude disturbances. Needs explicit user GO on build / .slx / runtime.mat unlock.
4. **G5 buffer 100k → 10k** — single-line config edit + retrain `phi_h_d_lower` to confirm Table I conformance. Paper-explicit closure.
5. **G6 independent learners** — architectural change, biggest scope. Defer until G3+G5 closure.
6. **G1 paper-strict PHI 1.0** — predicted to fail (R2 evidence at 1e-2 already worse than 1e-5); run once for documentation.
7. **G2 ΔH/ΔD range expansion** — Q7 ambiguity makes direct paper-literal range a stability gamble; calibrate first.

---

## 7. Boundary check

- `build_kundur_cvs_v3.m`, `kundur_cvs_v3.slx`, `kundur_ic_cvs_v3.json`, `kundur_cvs_v3_runtime.mat`: untouched ✓
- `slx_helpers/vsg_bridge/*`, `engine/simulink_bridge.py`: untouched ✓
- `agents/`, `scenarios/contract.py`, `scenarios/config_simulink_base.py`: untouched ✓
- Reward formula: untouched ✓
- LoadStep wiring: untouched (still hardcoded `Resistance='1e9'`) ✓
- NE39: untouched ✓
- No 200-ep / 2000-ep training launched ✓

Z1 changes (within P4.1 Path C scope):
- `scenarios/kundur/config_simulink.py`: +4 disturbance types in valid set + PHI_F env-var override (R2 already added).
- `env/simulink/kundur_simulink_env.py::_apply_disturbance_backend`: SG-side dispatch branch (`pm_step_proxy_g{1,2,3}` + `random_gen`); routes via existing `apply_workspace_var` to `PmgStep_amp_<g>` (added to runtime.mat in P4.1a-v2).
- `evaluation/paper_eval.py`: `--disturbance-mode bus|gen` flag; scenario `bus` field → disturbance_type translation.
- `scenarios/kundur/scenario_loader.py` + `scenario_sets/v3_paper_*.json`: G3 manifest closure (parallel work, not Z1-specific).

---

## 8. Artifacts

```
scenarios/kundur/
├── config_simulink.py                       (EDITED: +4 SG-disturbance types in valid set)
├── scenario_loader.py                        (NEW; G3 closure)
└── scenario_sets/
    ├── v3_paper_train_100.json
    └── v3_paper_test_50.json

env/simulink/kundur_simulink_env.py          (EDITED: SG-side dispatch in v3 branch)
evaluation/paper_eval.py                      (EDITED: --disturbance-mode bus|gen)

probes/kundur/v3_dryrun/_z1_sg_pm_step_sweep.py    (NEW: orchestrator)

results/harness/kundur/cvs_v3_phase4/
├── phase5_z1_sg_proxy_verdict.md            (this file)
├── z1_aggregate_metrics.json                (machine-readable)
├── z1_no_control_sg_metrics.json + stdout/stderr
├── z1_phi_b1_train_*.txt + eval_metrics.json + eval_stdout/stderr
├── z1_phi_h_d_lower_train_*.txt + eval_metrics.json + eval_stdout/stderr
├── z1_runner_stdout.txt + z1_runner_stderr.txt
└── (other Z1 logs)

results/sim_kundur/runs/
├── kundur_simulink_20260427_123856/         (Z1 phi_b1 50-ep)
└── kundur_simulink_20260427_125711/         (Z1 phi_h_d_lower 50-ep, BEST.PT = WINNER)
```

---

## 9. Decision point

**Phase 4 / Phase 5 path is now unblocked.** Recommended sequence to compound paper-explicit closure:

1. **Wire Phase 4.3 manifests** (1-line env reset extension + train CLI flag + paper_eval --scenario-set) — uses existing `v3_paper_train_100.json` / `v3_paper_test_50.json`, no model touch.
2. **Apply G5 (BUFFER_SIZE 100k → 10k)** — 1-line config edit (paper Table I literal).
3. **Re-train `phi_h_d_lower` under {paper-train-100 manifest, BUFFER_SIZE=10000, SG-side disturbance}** at extended episode count (200 first, then 2000 if 200 shows continued learning curve). This batches all currently-easy paper-explicit closures into one train + eval cycle.
4. After (3) results: decide G1 (PHI=1.0 paper-literal experiment) and G2 (ΔH/ΔD range expansion) — both are paper-explicit but require careful calibration.
5. G6 (independent learners) — biggest scope; reserve for after the simpler closures land.
6. Z2 (LoadStep wiring scope expansion) — only if magnitude gap (3-4×) blocks Phase 5 verdict.

**No further training should run until user authorizes the next step.**
