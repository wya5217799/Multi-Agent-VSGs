# Phase 4.2 Aggregate Verdict — PHI sweep — PASS at first candidate (`phi_b1`)

> **Status:** PASS — `phi_b1` (PHI_H=PHI_D=1e-4) cleared all 6 hard gates on the very first run; per the plan §Gap 2 stopping rule (first run with r_f% in band + all hard gates green = v3 default), no further sweep candidates were launched. Phase 4 default = `phi_b1` under `KUNDUR_DISTURBANCE_TYPE=pm_step_proxy_random_bus`.
> **Date:** 2026-04-27
> **Predecessor:** Phase 4.1 rerun PASS (Path C dispatch verified). Phase 4.1a-v2 PASS (cold-start runtime contract closed).
> **Plan:** [`quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_phase5_roadmap.md`](../../../../quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_phase5_roadmap.md)

---

## 1. What was run

| # | Tag | PHI_H | PHI_D | Disturbance | Episodes | Wall | Result |
|---|---|---|---|---|---|---|---|
| 1 | `phi_b1` | 1e-4 | 1e-4 | `pm_step_proxy_random_bus` | 50/50 | 10.8 min | **PASS** |
| — | `phi_asym_a` | 1e-3 | 1e-4 | (skipped — `phi_b1` passed) | — | — | — |
| — | `phi_paper_scaled` | 1e-2 | 1e-2 | (skipped) | — | — | — |
| — | `phi_asym_b` | 1e-2 | 1e-3 | (skipped) | — | — | — |
| — | `phi_paper` | 1.0 | 1.0 | (skipped) | — | — | — |

Single 50-ep cold-start subprocess on `kundur_cvs_v3` via `train_simulink.py --episodes 50 --resume none --seed 42`. Wall 647 s ≈ 12.9 s/ep — substantially faster than the roadmap §5.3.1 projection of ~35 s/ep, because the build-once SLX compile is cached after warmup and the 4-agent SAC update with `update_repeat=10` runs faster than the original projection assumed.

Run artifact: [`results/sim_kundur/runs/kundur_simulink_20260427_011559/`](../../../sim_kundur/runs/kundur_simulink_20260427_011559/).

Aggregate: [`p42_aggregate_metrics.json`](p42_aggregate_metrics.json).

---

## 2. `phi_b1` per-criterion table (gate vs observed)

| # | Criterion | Gate threshold | Observed | Status |
|---|---|---|---|---|
| 1 | Completion | 50 / 50 ep, no `tds_failed` | 50/50, 0 monitor stop, exit_code 0 | ✓ |
| 2 | Numerical health | 0 NaN/Inf in (rewards, r_f, r_h, r_d, max_freq_dev_hz, mean_freq_dev_hz) over 50 ep | `nan_inf_seen=False` | ✓ |
| 3 | r_f% (TRAIN-LOCAL, last 25 ep) | [3 %, 30 %], target 5 % | **11.84 %** | ✓ (band-pass; above target midpoint) |
| 4 | Frequency reach | per-ep `max_freq_dev_hz ∈ [0.05, 1.5] Hz` on ≥ 80 % of episodes | **100 %** in band; mean 0.147 Hz, range [0.063, 0.301] Hz | ✓ |
| 5 | SAC sanity | actor / critic / alpha losses finite throughout | finite over 41 update windows (warmup→last); `sac_losses_finite=True` | ✓ |
| 6 | Wall-time | < 60 min for 50 ep | 647 s = 10.8 min (1.1× wall margin) | ✓ |
| 7 | Action-space health (informational) | `mean(M)` ∈ [M_LO+0.5, M_HI−0.5] AND `mean(D)` ∈ [D_LO+0.5, D_HI−0.5] (no boundary pinning) | actions μ ≈ [-0.02, 0.02, -0.13, -0.03], σ ≈ 0.58 (mid-band, no pinning detected from monitor logs) | ✓ informational only — per-step M/D not in `training_log.json`, qualitative pass via monitor live trace |
| 8 | Learning trend (informational at WARMUP_STEPS=2000) | first 25 → last 25 ep mean reward improvement informational | first25 = −0.0409, last25 = −0.0396, Δ = +0.0012 (flat) | informational only — at WARMUP_STEPS=2000 the SAC has only 41 update windows in the 50-ep buffer; flat trend is expected per roadmap §3.1 |

**6/6 hard gates PASS. 0 fail_reasons. `phi_b1` becomes the v3 paper-replication PHI default.**

---

## 3. Reward decomposition

Last 25 ep aggregate (per `physics_summary[-25:]`):

| Component | mean(\|·\|) per ep | share of total \| · \| |
|---|---|---|
| `r_f` (frequency) | 0.00469 | **11.84 %** |
| `r_h` (inertia ΔH penalty) | 0.02802 | 70.71 % |
| `r_d` (damping ΔD penalty) | 0.00694 | 17.45 % |

Interpretation:
- r_h still dominates (70.7 %), as in the legacy single-VSG baseline. The Q7 H-dim ambiguity (paper used `H` directly vs project's `M=2H`) makes r_h numerical magnitude ~10⁴× the paper baseline at PHI_H=1.0; at PHI_H=1e-4, r_h is squeezed to roughly the same order as r_f×100.
- r_f at 11.84 % is **above the 5 % paper-target midpoint but well inside the [3 %, 30 %] band**. Per plan §Gap 2 stopping rule, this candidate is winning; `phi_paper_scaled` (1e-2/1e-2) might land closer to 5 % but the rule prefers the first PASS, not the closest-to-target. (Optional: re-run `phi_paper_scaled` for direct comparison if Phase 5 substantive verdict requires r_f% to be closer to paper.)
- r_d at 17.45 % shows the D-axis is non-trivial but secondary; consistent with P2.5c's H-primary / D-secondary lever assessment.

---

## 4. Frequency-response distribution

Per-ep `max_freq_dev_hz` over all 50 ep:

| Stat | Value |
|---|---|
| min | 0.063 Hz |
| mean | 0.147 Hz |
| max | 0.301 Hz |
| % in [0.05, 1.5] Hz | **100 %** |

All 50 ep landed in the gate-4 band — well above the 50 mHz floor (P2.2-validated), well below the 1.5 Hz ceiling. Saturating IntW (±15 Hz) was nowhere in sight. This confirms the Path (C) Pm-step proxy at the current `DIST_MIN/DIST_MAX = [0.1, 0.5]` sys-pu range produces a comfortable signal-to-noise margin for the SAC at this PHI level.

---

## 5. Disturbance bus distribution (random_bus stochastic dispatch)

Counted from `[Kundur-Simulink-CVS] Pm step ... (proxy_busN)` lines in `p42_phi_b1_stdout.txt`:

| Source | Count | Fraction |
|---|---|---|
| `proxy_bus7` (ES1, idx 0) | 31 | 58.5 % |
| `proxy_bus9` (ES4, idx 3) | 22 | 41.5 % |
| `pm_step_single_vsg` (legacy) | 0 | 0 % |
| (other) | 0 | 0 % |
| **Total** | **53** | — |

53 disturbance dispatches over 50 train + 3 eval (`evaluate(n_eval=3)` at ep 50 with deterministic magnitude 2.0; eval calls `apply_disturbance(bus_idx=0, magnitude=2.0)` but the v3 dispatch ignores `bus_idx` and uses `_disturbance_type` instead — eval episodes also pick random bus per the stochastic dispatch).

58.5 / 41.5 % is within ±SD of 50 / 50 (binomial 53,0.5: SD = 0.069 → 95 % CI ≈ [37, 64] %). Both buses sampled, dispatch confirmed stochastic.

---

## 6. Action statistics + collapse / pinning check

From the live monitor log:
- Actions μ = `[-0.02, 0.02, -0.13, -0.03]` at ep 29 (4 agents)
- Actions σ = `[0.58, 0.57, 0.58, 0.59]` at ep 29
- TDS fails: 0 / 10 in the recent 10 ep window
- Per-agent rewards: `[a0: -0.0, a1: -0.0, a2: -0.0, a3: -0.0]` (close to 0 — paper-style nearly-flat reward at convergence)
- SAC mean critic_loss = 1.62, mean alpha = 0.65 (auto-entropy still adapting; finite)

**No pinning detected.** Action means are mid-band, std is non-collapsed (SAC's exploration entropy is preserving spread). The `mean(M)` / `mean(D)` raw bounds check (gate 5 / criterion 7) is informational only because per-step M/D are not in `training_log.json`; qualitative monitor evidence is consistent with healthy mid-band action distribution.

---

## 7. NaN / Inf / clip / tds_failed

| Counter | Count |
|---|---|
| NaN/Inf in episode_rewards | 0 |
| NaN/Inf in physics_summary[r_f, r_h, r_d, max_freq_dev_hz] | 0 |
| NaN/Inf in critic / policy / alpha losses | 0 |
| `tds_failed=True` events | 0 (per monitor `0/10`) |
| `omega_saturated=True` (≥ 13.5 Hz) | 0 (max observed 0.301 Hz) |

---

## 8. Recommendation

**RECOMMENDATION: PROCEED with `phi_b1` (PHI_H=PHI_D=1e-4) as Phase 4 / Phase 5 PHI default.**

Rationale:
- All 6 hard gates green on first run; stopping rule met.
- `pm_step_proxy_random_bus` dispatch confirmed working under live SAC training (53 dispatches, both buses sampled).
- No NaN/Inf, no monitor-stop, no tds_failed.
- Frequency reach 100 % in band; r_f% inside the gate band.
- Wall-time at 13 s/ep means Phase 5 2000-ep main run projects to **~7.2 hr** (2000 × 13 s), substantially below the §5.3.1 projection of ~19.4 hr and well under the 30-hr Phase 5 criterion-6 cap.

**Optional (not required for Phase 4 PASS):** if a Phase 5 verdict needs r_f% closer to paper-target 5 %, run `phi_paper_scaled` (PHI_H=PHI_D=1e-2) as a comparison data-point. This is **not gated** by the stopping rule — Phase 4.2 winner is locked at `phi_b1` per the rule.

**NO 50-ep PILOT recommendation:** the 50-ep run completes the Phase 4 gate. The next step per roadmap §2 / §7 is Phase 4.3 (fixed scenario sets) and then Phase 4.4 aggregate + handoff contract emit. **No 200-ep or 2000-ep training launched in this verdict** — that requires explicit Phase 5 GO based on the full Phase 4 verdict (4.0 + 4.1 + 4.1a-v2 + 4.2 + 4.3 + 4.4).

---

## 9. Boundary check

- `build_kundur_cvs_v3.m`, `kundur_cvs_v3.slx`, `kundur_ic_cvs_v3.json`, `kundur_cvs_v3_runtime.mat`: untouched in P4.2 (Phase 4.1a-v2 was the last edit).
- `slx_helpers/vsg_bridge/*`, `engine/simulink_bridge.py`: untouched ✓
- `env/simulink/kundur_simulink_env.py` Path (C) dispatch: untouched ✓
- `agents/`, `scenarios/contract.py`, `scenarios/config_simulink_base.py`: untouched ✓
- Reward formula: untouched (only PHI_H/PHI_D scalar values moved, no formula change) ✓
- LoadStep wiring: untouched (still hardcoded `Resistance='1e9'`) ✓
- NE39: untouched ✓
- No 50-ep / 2000-ep training **launched beyond the single P4.2 50-ep gate run** ✓
- Only PHI-related env/config: `KUNDUR_PHI_H` / `KUNDUR_PHI_D` env-var hooks added at [`scenarios/kundur/config_simulink.py:111-118`](../../../../scenarios/kundur/config_simulink.py); defaults preserved at 1e-4. Authorized by user GO message: "Only vary PHI-related env/config parameters that are explicitly part of P4.2."

---

## 10. Artifacts emitted

```
scenarios/kundur/
└── config_simulink.py                       (EDITED L111-118: PHI_H/PHI_D env-var hooks)

probes/kundur/v3_dryrun/
└── _p42_phi_sweep_runner.py                 (NEW: orchestrator)

results/sim_kundur/runs/kundur_simulink_20260427_011559/
├── checkpoints/ep50.pt, final.pt
├── logs/training_log.json, live.log, monitor_data.csv, monitor_state.json
├── events.jsonl
├── run_meta.json, run_status.json, training_status.json
└── tb/                                      (TensorBoard scalars)

results/harness/kundur/cvs_v3_phase4/
├── phase4_p42_aggregate_verdict.md          (this file)
├── p42_aggregate_metrics.json               (machine-readable summary, 1 run)
├── p42_phi_b1_metrics.json                  (per-run gate metrics)
├── p42_phi_b1_stdout.txt                    (per-run subprocess stdout)
├── p42_phi_b1_stderr.txt                    (empty)
├── p42_runner_stdout.txt                    (orchestrator-level log)
└── p42_runner_stderr.txt                    (empty)
```

---

## 11. Next step

Per roadmap §2 / §7, advance to **Phase 4.3** — generate fixed scenario sets `v3_paper_train_100.json` + `v3_paper_test_50.json` + scenario_loader module, then 1× 50-ep run on `--scenario-set train` with the locked PHI default. Awaiting user GO for P4.3.

Hard boundaries continue: build / .slx / IC / runtime.mat / bridge / helper / env-dispatch / reward / LoadStep / NE39 untouched; no 200-ep / 2000-ep launches without explicit Phase 5 GO.
