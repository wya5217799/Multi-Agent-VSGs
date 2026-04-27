# Phase 4.2-overnight Verdict — Sustained `phi_b1` Training (Stopped at ep 670)

> **Status:** STOPPED at user request (avg10 reward + α floor signaled convergence at ep ~500). 13 checkpoints + best.pt preserved. Diagnostic surfaces multiple optimization candidates before any Phase 5 launch.
> **Date:** 2026-04-27
> **Predecessor:** Phase 4.2 PASS at `phi_b1` (PHI_H=PHI_D=1e-4) ep 50.
> **Run:** [`results/sim_kundur/runs/kundur_simulink_20260427_013758/`](../../../sim_kundur/runs/kundur_simulink_20260427_013758/)
> **Wall:** 17:38:19 → 20:40:54 UTC (3.04 hr) for 620 episodes (ep 50 → 669).

---

## 1. Training trajectory (100-ep windows)

| Window (absolute ep) | mean(reward) | mean\|r_f\| | mean\|r_h\| | mean\|r_d\| | r_f% | mean df_max | max df_max | settled% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 50–149 | −0.0422 | 0.00437 | 0.03231 | 0.00554 | 10.3 % | 0.149 Hz | 0.268 Hz | 92 % |
| 150–249 | −0.0410 | 0.00485 | 0.03015 | 0.00599 | 11.8 % | 0.157 Hz | 0.311 Hz | 92 % |
| 250–349 | −0.0370 | 0.00457 | 0.02717 | 0.00523 | 12.4 % | 0.154 Hz | 0.277 Hz | 93 % |
| 350–449 | −0.0377 | 0.00396 | 0.02867 | 0.00509 | 10.5 % | 0.141 Hz | 0.291 Hz | 95 % |
| 450–549 | −0.0403 | 0.00439 | 0.03111 | 0.00480 | 10.9 % | 0.147 Hz | 0.366 Hz | 95 % |
| 550–649 | −0.0402 | 0.00512 | 0.03022 | 0.00483 | 12.7 % | 0.162 Hz | 0.270 Hz | 90 % |
| 650–669 | −0.0395 | 0.00518 | 0.02970 | 0.00466 | 13.1 % | 0.163 Hz | 0.274 Hz | 95 % |

**Reading:** train reward, r_f%, df_max, settled-rate are **all flat across 620 ep**. Policy converged early (≤ep 100) and never broke the plateau.

## 2. SAC convergence trace (50-record windows of post-warmup updates)

| Window | mean α | mean critic_loss | mean policy_loss |
|---|---:|---:|---:|
| 0–49 (warmup→ep~80) | 0.124 | 2.685 | −8.32 |
| 50–99 | **0.0500** | 0.293 | −2.68 |
| 100–149 | 0.0500 | 0.104 | −1.77 |
| … | (α flat at floor) | (decaying) | (decaying) |
| 600–610 | 0.0500 | 0.057 | −1.25 |

**Reading:** α hit the SAC `min_alpha=0.05` floor at idx ~50 (≈ ep 100 absolute) and stayed pinned the rest of the run. Critic_loss decayed cleanly 47× (2.685 → 0.057), policy_loss magnitude shrank 6.6× (−8.32 → −1.25) — value function and policy gradient are both healthy. No NaN/Inf.

## 3. Eval reward history (eval-interval=50, eval magnitude=2.0 sys-pu)

| Eval ep | eval_reward |
|---|---:|
| 99 | −42.76 |
| 149 | −152.07 |
| 199 | −102.47 |
| 249 | −341.28 |
| 299 | −42.90 |
| 349 | −188.20 |
| 399 | −73.34 |
| 449 | −42.06 |
| 499 | −62.31 |
| **549** | **−28.89** ← best.pt (saved 04:02:06) |
| 599 | −193.77 |
| 649 | −158.27 |

Eval reward range is 12×. Best (−28.89) is **3.6× worse than paper DDIC −8.04 and 1.9× worse than paper no-control −15.2**. Eval is wildly noisy and far from paper.

## 4. Monitor alerts

`events.jsonl` filter `event_type == "monitor_alert"`: **0 events**. The earlier per-episode warnings (`'r_f' is only 9.6 % of total reward (threshold: 50%)`) appear to be informational `monitor.log_and_check` output (printed to stdout but not emitted as a `monitor_alert` event). Hard-stop never triggered — training stopped only on user `Stop-Process`.

## 5. Final state

- **PID 80540 STOPPED** (Stop-Process -Force at 04:40 local).
- `training_status.json` left as `status: "running"` because hard-kill bypassed the `finally` block; not a problem.
- **13 checkpoints + best.pt preserved**: ep100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650 + best.pt (= ep 549 by mtime).
- `metrics.jsonl` (632 records) + `events.jsonl` + `live.log` written incrementally — full trajectory recoverable.
- TensorBoard scalars under `tb/` complete.

---

## 6. Issues to optimize (prioritized)

| # | Issue | Severity | Evidence | Phase to address |
|---|---|---|---|---|
| **I1** | **Reward dominated by r_h (~70 %), r_f only ~12 %** — policy has more incentive to keep ΔH ≈ 0 than to suppress frequency. PHI_H=1e-4 still under-weights r_f vs paper target 5 %. | HIGH | §1 windowed table; r_h ≈ 6× r_f throughout | P4.2-extended (run `phi_paper_scaled` 1e-2/1e-2 for comparison) OR P5.2 Q7/Q2 ablation |
| **I2** | **Reward plateau ep 50 → 670 = no learning curve.** avg(reward) ≈ −0.040 stable, settled% stable 90-95 %. Policy converged to "minimize r_h via inaction"; r_f signal too weak to drive further learning. | HIGH | §1 table; eval rewards never trended down despite 12× variance | I1 (root cause); also revisit reward formula |
| **I3** | **Eval distribution OOD**: `_EVAL_DISTURBANCE_MAGNITUDE = 2.0` (= 200 MW @ Sbase=100) is **4× the training `DIST_MAX = 0.5`** (50 MW). Eval probes a regime the policy was never trained on. | HIGH | `train_simulink.py:118`; eval rewards 12× range, paper baseline far away | Phase 4.x or P5.1 — split eval into in-band (0.3 sys-pu) + OOD-stress (2.0) cases |
| **I4** | **Best eval reward = −28.89** is 3.6× worse than paper DDIC (−8.04) and 1.9× worse than paper no-control (−15.2). | HIGH | §3 eval table | Phase 5 verdict — needs Gap 4 evaluator (paper-style global r_f formula, not training-local) before drawing comparison conclusion. Current eval may not be paper-comparable. |
| **I5** | **α saturated at 0.05 floor from ep 100**. SAC auto-entropy tuner couldn't go lower; policy entropy is at the imposed minimum. Either (a) the target_entropy is set too high for this problem, or (b) min_alpha=0.05 is too restrictive. | MED | §2 alpha trace | Tune `agents/sac.py` SAC config — but this is reward-secondary; fix I1 first |
| **I6** | **No fixed scenario set** (Phase 4.3 not yet started). Each episode resamples disturbance magnitude + bus from random uniform. Paper §IV-A specifies fixed 100 train / 50 test. Current run is not paper-comparable. | MED | per roadmap §Gap 3 | Phase 4.3 (manifest JSON + scenario_loader.py + CLI flag) |
| **I7** | **Random-bus dispatch is uniform 50/50**, but bus 9 is structurally stiffer (P2.3-L1: 967 MW for 21 mHz). Policy training on 50/50 mix may under-fit the bus 9 sub-distribution. | LOW | §1 (df_max stable suggests bus mix isn't a problem within `DIST_MIN/DIST_MAX = [0.1, 0.5]`) | Optional Phase 5 sub-experiment if Gap 4 evaluator shows bus 9 weakness |
| **I8** | **Monitor's `reward_component_ratio` rule threshold = 50 %** but our gate band is [3 %, 30 %]. Monitor warns continuously, never stops. | LOW | live.log shows repeated 'r_f only 9.6 %' warnings | `utils/monitor.py` config — defer; warnings don't impede training |
| **I9** | **Q7 mapping ambiguity (M = 2H vs paper-strict H)**: project assumes M = 2H, paper notation may differ. PHI_H tuning is therefore against a possibly-wrong reward dimensional baseline. | MED | per fact-base Q7 (open) | P5.2 Q7/Q2 ablation per roadmap §Gap 6 |
| **I10** | **WARMUP_STEPS = 2000 = 10 ep buffer-fill** is plausibly too short — buffer hit 100,000 (capacity) at ep ~550. After ep 550 the agent samples primarily its own data, increasing local optimum lock-in. | LOW | live.log buffer trace | Future tune; currently not the dominant issue (I1 is) |

---

## 7. Recommended next steps (ordered)

1. **Address I1 / I2 (root cause: reward shape)** — biggest ROI. Two options:
   - **(a) Quick PHI comparison:** spawn a parallel `phi_paper_scaled` (PHI_H=PHI_D=1e-2) 50-ep + ~500-ep extended run for direct compare against `phi_b1`. ~3 hr wall, isolates whether stronger r_f weight breaks the plateau.
   - **(b) PHI_F bump:** raise `PHI_F` from 100 to e.g. 500 instead of changing PHI_H. r_f gets a 5× lift relative to r_h/r_d. ~3 hr wall.
   - **(c) Reward formula audit:** independently audit `_compute_reward` in `env/simulink/_base.py` for any unintended scaling.

2. **Address I3 (eval mismatch)** — a 1-line edit:
   - `train_simulink.py:118` — split into `_EVAL_DISTURBANCE_MAGNITUDE_INBAND = 0.3` and `_EVAL_DISTURBANCE_MAGNITUDE_OOD = 2.0`, run both. Or just lower to 0.3 for in-band assessment.
   - **Caveat:** this is `train_simulink.py` (training loop) edit — not in P4.2 scope. Treat as Phase 4.x or P5.1.

3. **Phase 4.3 (I6)** — fixed scenario sets manifest + loader + CLI flag. Required for paper-comparable Phase 5 verdict.

4. **Phase 5.1 (Gap 4 evaluator + I4)** — paper-style global r_f formula, then re-evaluate `best.pt` (ep 549) against it. The current eval reward is **training-local + OOD** — paper comparison is not valid until Gap 4 evaluator exists.

5. **Phase 5.2 (Q7/Q2 ablation, I9)** — re-evaluate same best.pt under H=M, H=M/2, global vs neighbor mean ΔH. Brackets paper-side ambiguity.

6. **Defer I5, I7, I8, I10** — secondary to I1.

---

## 8. What this run did vs did NOT prove

**Proved:**
- ✓ P4.1a-v2 cold-start contract holds across 670 ep (no NaN/Inf, no crash, all 22 vars survive).
- ✓ P4.1 dispatch (`pm_step_proxy_random_bus`) routes correctly through 670 ep × ≥3 disturbances/ep ≈ 2000+ dispatches (no `(other)`/`single_vsg` leak).
- ✓ Frequency reach gate (criterion 4) holds at scale: 100 % of episodes in [0.05, 1.5] Hz, settled% 90-95 %.
- ✓ SAC training is numerically stable (critic loss converges, no Inf).
- ✓ Wall scaling: 17.4 s/ep avg → 2000 ep would take ~9.7 hr (slightly higher than P4.2's 13 s/ep extrapolation due to SAC update overhead at full buffer).

**Did NOT prove:**
- ✗ Policy quality vs paper baseline (eval is OOD; no Gap 4 evaluator).
- ✗ That `phi_b1` is the right PHI choice — I1 strongly suggests it under-weights r_f.
- ✗ Phase 5 verdict admissibility — need fixed scenario sets (P4.3) + Gap 4 evaluator (P5.1).

---

## 9. Boundary check

- `build_kundur_cvs_v3.m`, `kundur_cvs_v3.slx`, `kundur_ic_cvs_v3.json`, `kundur_cvs_v3_runtime.mat`: **untouched** since P4.1a-v2 ✓
- `slx_helpers/vsg_bridge/*`, `engine/simulink_bridge.py`: **untouched** ✓
- `env/simulink/kundur_simulink_env.py` Path (C) dispatch: **untouched** ✓
- `agents/`, `scenarios/contract.py`, `scenarios/config_simulink_base.py`: **untouched** ✓
- Reward formula: **untouched** (PHI_H/PHI_D scalars only) ✓
- LoadStep wiring: **untouched** ✓
- NE39: **untouched** ✓

---

## 10. Artifacts

```
results/sim_kundur/runs/kundur_simulink_20260427_013758/
├── checkpoints/
│   ├── best.pt           (ep 549, eval_reward=−28.89)
│   ├── ep100..650.pt     (12 stable checkpoints)
│   └── final.pt          NOT WRITTEN (hard-killed before finally block)
├── logs/
│   ├── live.log          (55 KB, per-ep human-readable)
│   ├── metrics.jsonl     (306 KB, 632 records — 620 train + 12 eval)
│   ├── events.jsonl      (169 KB)
│   └── latest_state.json
├── tb/                   (TensorBoard scalars)
└── training_status.json  (frozen at status='running' due to hard-kill)

results/harness/kundur/cvs_v3_phase4/
├── phase4_p42_overnight_verdict.md  (this file)
└── p42_overnight_pid.txt            (80540, dead)

probes/kundur/v3_dryrun/
└── _p42_overnight_continue.py       (overnight launcher)
```

---

## 11. Open question for user

**Which optimization to attack first?**
- **A. Quick PHI experiment** (`phi_paper_scaled` 1e-2/1e-2 50-ep + 500-ep) → tests whether I1/I2 are PHI-driven.
- **B. PHI_F bump** to 500 — same goal, single config edit.
- **C. Phase 4.3 first** (fixed scenario sets) — locks the train/test contract before any further training.
- **D. Phase 5.1 first** (Gap 4 evaluator) — replaces OOD eval with paper-style global r_f formula; re-scores `best.pt` against paper.
- **E. Reward formula audit** — read-only check that nothing's accidentally scaling r_f.

Recommendation: **D first, then A or B**. D unblocks paper comparison and exposes whether the apparent plateau is a real policy weakness or an eval-measurement artefact. A/B then attack reward shape if D confirms the issue.
