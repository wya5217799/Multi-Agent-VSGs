# Phase 4.3 + G5 (200-ep retrain) Verdict — REGRESSION on test manifest

> **Status:** FAIL — DDIC under (Phase 4.3 train manifest + G5 BUFFER_SIZE=10 000 + Z1 winner PHI + 200 ep) is **9.96 % WORSE than zero-action no-control** on the test manifest. Compared to Z1 50-ep (which beat no-control by +15.4 % under the same disturbance topology), the combined change of 4 axes regressed the policy by ~26 percentage points. Three variables changed at once; root cause not isolated. Recommend single-axis ablation before further training.
> **Date:** 2026-04-27
> **Predecessor:** Z1 PASS (50 ep, BUFFER=100 000, inline-gen, +15.4 %).
> **Wall:** 1 hr 6 min (no_ctrl 8 min + train 41.5 min + eval 8 min + overhead).

---

## 1. Headline result

| Stage | Config | cum_unnorm | vs no-control | per_M |
|---|---|---:|---:|---:|
| Z1 phi_h_d_lower | 50 ep, BUFFER=100k, inline-gen seed=42 | −3.56 | **+15.4 % BETTER** | −0.0713 |
| **P4.3+G5** | **200 ep, BUFFER=10k, train manifest, eval test manifest** | **−4.62** | **−9.96 % WORSE** | −0.0923 |
| no_control_test | n/a (zero-action) | −4.20 | — | −0.0840 |
| no_control_z1 (Z1 reference, inline-gen) | n/a | −4.21 | — | −0.0842 |

The two zero-action baselines (test manifest vs Z1 inline-gen) match within 0.3 % — confirms test manifest distribution is statistically equivalent to Z1's inline-gen distribution. **The regression is in policy quality, not in eval distribution change.**

Paper-direction-correct DDIC outcome from Z1 was lost.

---

## 2. Variables changed simultaneously

Z1 baseline → P4.3+G5 final, 4 axes flipped:

| Axis | Z1 | P4.3+G5 | Hypothesized impact |
|---|---|---|---|
| Episodes | 50 | **200** | +4× training; could overtrain plateau |
| BUFFER_SIZE | 100 000 | **10 000** (paper Table I) | 10× smaller; SAC sees only most-recent 50 ep |
| Train scenarios | inline-gen seed=42 (random per ep) | **train manifest** (cycle k mod 100) | manifest restricts variety; same scenario every 100 ep |
| Test scenarios | inline-gen seed=42 | **test manifest** (different from Z1's inline) | confirmed equivalent (no_ctrl matches within 0.3 %) — NOT the regressor |

Of the three real axes (ep / buffer / train-scenarios), no isolated experiment ran. **Cannot attribute the regression without an ablation.**

---

## 3. Live training observation

- avg10 reward stable at **−0.01** across ep 1–200 (vs P4.2-overnight `phi_b1` plateau at −0.04 at PHI_H=1e-4). Smaller absolute reward magnitude is consistent with PHI_H=1e-5 reducing r_h penalty 10×.
- df_max range 0.05–0.21 Hz (in band).
- α=0.0500 floor (auto-entropy collapsed by ep ~50, same as P4.2-overnight).
- Buffer hit 10000 cap by ep ~50 (= 50 × 200 transitions = exactly 10k). After that, every new transition pushes out an old one; by ep 200 the buffer holds ep 150–200 only. **Diversity floor.**

---

## 4. Z1 50-ep checkpoint sanity

Z1 winner ckpt (50-ep, BUFFER=100k) had `best.pt` saved by `evaluate()` based on internal eval reward (deterministic disturbance magnitude=2.0 at bus=0, OOD per P5.1 finding). The fact that Z1's 50-ep best.pt evaluated to −3.56 on the same topology + DIST range — and P4.3+G5's 200-ep best.pt evaluated to −4.62 — is reproducible evidence the regression is real, not a noise/seed-random anomaly.

P4.3+G5 best.pt was selected by the same train_simulink eval criterion (not by paper-style global r_f). The Z1 vs P4.3+G5 mismatch suggests internal-eval criterion is uncorrelated with paper-style global r_f — the OOD eval distorts which checkpoint is selected as `best`.

---

## 5. Per-physics breakdown (P4.3+G5 vs no_control_test)

| Metric | no_control_test | P4.3+G5 ddic_test | Δ |
|---|---:|---:|---:|
| cum_unnorm | −4.198 | −4.616 | +10 % WORSE |
| max\|Δf\| mean (Hz) | 0.106 | (read from metrics.json) | (TBD if needed) |
| ROCOF mean (Hz/s) | 0.66 | (TBD) | (TBD) |
| settled% | 0 % | 0 % | tie |

(Detailed P4.3+G5 ddic_test summary fields available in `p43_ddic_test_metrics.json`.)

---

## 6. Possible root causes (ranked by hypothesis strength)

### (a) BUFFER_SIZE = 10000 is too small for v3's training cadence (LIKELY)

Each ep produces 200 transitions (4 agents × 50 steps). BUFFER=10000 = exactly 50 ep capacity. After ep 50, every new transition evicts an old one. By ep 200, the buffer holds **only ep 150–200 transitions**. SAC samples mini-batches of 256 from this 10k window only, and these 50 ep all use the same fully-trained policy (post-α-floor). Sample diversity is minimal and homogeneous, leading to local-optimum lock-in.

Z1 50-ep + BUFFER=100k never hit this regime — buffer was filling, only 10k of capacity used by ep 50, samples included the entire training trajectory's diverse experiences (warm-up exploration + early policy + recent policy).

**Test:** roll back to BUFFER=100000, re-run 200 ep on train manifest. If that recovers Z1-style improvement, G5 is the regressor.

### (b) 200-ep over-training drifts past the optimum (LIKELY)

P4.2-overnight evidence (`phi_b1`, BUFFER=100k, inline-gen) showed ep 50–150 was when r_f% climbed and reward magnitude moved; afterwards it plateaued. 200 ep here may be past whatever optimum existed, pulling toward "do nothing" via continued α-floor exploitation.

**Test:** keep BUFFER=10k + train manifest, but re-eval ep50.pt / ep100.pt / ep150.pt explicitly. If any earlier checkpoint beats no-control, the issue is over-training, not buffer.

### (c) Train manifest cycling reduces effective scenario diversity (UNCERTAIN)

train_simulink picks `manifest.scenarios[ep % 100]` so 200 ep visits each scenario exactly twice. Inline-gen visits 200 unique random scenarios. Could affect SAC's generalization to test manifest.

**Test:** unlikely — random per-ep was already in [DIST_MIN, DIST_MAX] uniform; manifest is also uniform-sampled (just deterministic). Diversity-of-magnitudes is statistically equal.

### (d) test manifest scenarios are harder (RULED OUT)

Test manifest's 50 scenarios produced no_ctrl = −4.20, almost identical to Z1's inline-gen no_ctrl = −4.21. Distributions are statistically equivalent. NOT the regressor.

---

## 7. What was paper-explicitly closed

- **G3 (Phase 4.3, fixed scenario manifests)**: ✓ JSON manifests checked into repo, loader module exists, env/train/eval CLI flags wired and verified working under live training.
- **G5 (BUFFER_SIZE 100k → 10k)**: ✓ Configuration is now paper Table I literal. **Paper-explicit closure was achieved**, but exposed that the project's earlier 100k override may have been compensating for some other v3 deficiency.

The **closure** of G3 and G5 is structural (code & data conform to paper). The **outcome** (DDIC regression) is a secondary finding that says "paper-faithful settings + Z1 winner PHI under v3 implementation does NOT reproduce paper's DDIC > no-control result".

---

## 8. Boundary check

- `build_kundur_cvs_v3.m`, `kundur_cvs_v3.slx`, `kundur_ic_cvs_v3.json`, `kundur_cvs_v3_runtime.mat`: untouched ✓
- `slx_helpers/vsg_bridge/*`, `engine/simulink_bridge.py`: untouched ✓
- `agents/`, `scenarios/contract.py`, `scenarios/config_simulink_base.py`: untouched ✓
- Reward formula: untouched ✓
- LoadStep wiring: untouched ✓
- NE39: untouched ✓
- G1 / G2 / G6 / Z2: NOT touched ✓ (per user instruction)

Edits in this step:
- `evaluation/paper_eval.py`: `--scenario-set {none|train|test}` + scenarios_override.
- `scenarios/kundur/train_simulink.py`: `--scenario-set` + scenario manifest cycling in train loop.
- `scenarios/kundur/config_simulink.py`: BUFFER_SIZE 100000 → 10000 (paper Table I literal).

---

## 9. Recommended next steps (ranked)

| Priority | Action | Cost | Expected information gain |
|---|---|---|---|
| ★★★★★ | **Eval ep50/ep100/ep150/ep200 of P4.3+G5 run on test manifest** | ~30 min (4× 8 min eval; no retrain) | Isolates over-training (b) — if ep50.pt > ep200.pt on test, over-training confirmed; if ep50.pt is also < no_ctrl, then BUFFER=10k is the regressor. **Highest ROI.** |
| ★★★★ | **Re-run 200 ep with BUFFER=100000** (rollback G5 only) on train manifest | ~50 min | Isolates (a). If it recovers Z1-style improvement, G5 is the regressor. |
| ★★★ | **Re-run 50 ep with BUFFER=10k** on train manifest | ~15 min | Isolates (a) at small ep — direct compare to Z1. |
| ★★ | Phase 4.3 closure verdict + G5 partial rollback documented; defer further training | low | Accept regression as a real finding; revisit after G6 (independent learners) is implemented |
| ★ | G6 / Z2 escalation | high | per user, deferred |

**Recommend ★★★★★ (cheap checkpoint sweep) FIRST** — uses already-trained checkpoints (ep50/100/150/200 in `kundur_simulink_20260427_133927/checkpoints/`), 4× paper_eval runs, no retraining. Likely closes the over-training-vs-buffer question in ~30 min.

---

## 10. Artifacts

```
scenarios/kundur/
├── config_simulink.py                       (EDITED: BUFFER_SIZE=10000, G5)
├── train_simulink.py                        (EDITED: --scenario-set + manifest loader)

evaluation/paper_eval.py                     (EDITED: --scenario-set + scenarios_override)

probes/kundur/v3_dryrun/_p43_g5_200ep_retrain.py   (NEW: orchestrator)

results/harness/kundur/cvs_v3_phase4/
├── phase4_p43_g5_200ep_verdict.md           (this file)
├── p43_g5_aggregate_summary.json            (machine-readable)
├── p43_no_control_test_metrics.json
├── p43_no_control_test_stdout.txt
├── p43_200ep_train_stdout.txt               (~16 MB, 200-ep live log)
├── p43_200ep_train_stderr.txt
├── p43_ddic_test_metrics.json
├── p43_ddic_test_stdout.txt
└── p43_runner_stdout.txt + stderr.txt

results/sim_kundur/runs/kundur_simulink_20260427_133927/
├── checkpoints/ep50.pt, ep100.pt, ep150.pt, ep200.pt, best.pt, final.pt
└── logs/, tb/, run_meta.json, run_status.json, training_status.json
```

---

## 11. Decision point

**Choose next step:**

- **A. Eval-only checkpoint sweep** (★★★★★): 4× paper_eval on ep50/100/150/200 — cheapest path to isolate over-training vs buffer.
- **B. Rollback G5 only** + re-run 200 ep — isolates buffer.
- **C. Accept regression, document, halt training**.
- **D. Authorize G2 / G6 / Z2** scope expansion (per user, deferred unless explicit GO).

**Recommend A first** — no retrain, just 4 evals, ~30 min. Result decides next step.
