# Phase 5.1 Verdict — Paper-Style Evaluator + best.pt Re-evaluation — POLICY UNDERPERFORMS NO-CONTROL

> **Status:** EVALUATOR BUILT + RAN. **Critical finding:** v3 DDIC (`best.pt` from `phi_b1` overnight) is **worse than zero-action no-control by 19 %** under the paper §IV-C global r_f formula. Paper DDIC reportedly beats paper no-control by 47 %. Direction is **inverted** — confirms P4.2-overnight I1/I2 (reward shape problem). Phase 5 main run NOT recommended on current `phi_b1` checkpoint.
> **Date:** 2026-04-27
> **Predecessor:** P4.2-overnight (stopped at ep 670 due to reward plateau).
> **Plan:** roadmap §3 / §5.1.1.

---

## 1. What was built

| Path | Lines | Purpose |
|---|---|---|
| `evaluation/__init__.py` | NEW | package marker |
| `evaluation/paper_eval.py` | NEW (~530 LOC) | paper §IV-C global r_f formula `−ΣΣ(Δf − f̄)²` + ROCOF/nadir/peak/settling-time + 3 normalization variants (unnormalized / per-M / per-M·N) per roadmap §3.4 |
| `probes/kundur/v3_dryrun/_p51_paper_eval_runner.py` | NEW | sequential runner: zero-action baseline + `best.pt` |

Schema matches roadmap §5.1.1: `cumulative_reward_global_rf {unnormalized, per_M, per_M_per_N, paper_target_unnormalized, paper_no_control_unnormalized}` + `per_episode_metrics[]`.

50 deterministic scenarios (seed=42) generated inline (Phase 4.3 manifest TBD): 23× bus 7 + 27× bus 9, magnitudes uniform on [DIST_MIN=0.1, DIST_MAX=0.5] sys-pu × ±sign. Same scenarios reused across both policies.

---

## 2. Headline result

| Policy | unnormalized | per_M | per_M·N | vs paper DDIC | vs v3 no_control |
|---|---:|---:|---:|---:|---:|
| paper no_control (Sec.IV-C) | −15.20 | −0.304 | −0.076 | — | — |
| paper DDIC (Sec.IV-C) | **−8.04** | −0.161 | −0.040 | 1.00× | — |
| **v3 no_control** (zero action) | **−7.48** | −0.150 | −0.037 | 0.93× | 1.00 |
| **v3 DDIC** (`phi_b1` best.pt ep 549) | **−8.90** | −0.178 | −0.045 | 1.11× | **1.19× (WORSE)** |

**Improvement v3 DDIC over v3 no_control: −19 %** (DDIC is worse by 19 %).
**Improvement paper DDIC over paper no_control: +47 %** (DDIC is 47 % better).

**Direction is inverted.** Paper claims learning helps; current v3 trained policy hurts.

---

## 3. Per-physics breakdown (50 scenarios, deterministic)

| Metric | no_control | ddic_phi_b1 | Δ |
|---|---:|---:|---:|
| max\|Δf\| mean (Hz) | 0.132 | 0.146 | **+11 % worse** |
| max\|Δf\| max (Hz) | 0.249 | 0.232 | −7 % better |
| ROCOF mean (Hz/s) | 0.91 | **1.08** | **+19 % worse** |
| ROCOF max (Hz/s) | 1.68 | **1.93** | **+15 % worse** |
| settled% (5 mHz × 1 s) | 0 % | 0 % | tie |
| sum r_f_local (50 ep) | −0.200 | **−0.237** | **+19 % worse** |
| sum r_h (50 ep) | 0.000 (no Δ) | **−0.088** | DDIC pays h-penalty |
| sum r_d (50 ep) | 0.000 | −0.014 | DDIC pays d-penalty |
| rh_share% mean | 0 % | **29.6 %** | DDIC active on H |

Per-bus split:
- bus 7 mean max\|Δf\|: no_control 0.139 → DDIC 0.146 (+5 %)
- bus 9 mean max\|Δf\|: no_control 0.127 → DDIC 0.146 (+15 %)

DDIC actively touches H (29.6 % r_h share) but the H actions **make the system worse**, not better — across ROCOF, max\|Δf\|, and r_f_local globally.

---

## 4. v3 vs paper magnitude check

v3 cumulative numbers (~−7 to −9) are in the **same OoM** as paper (~−8 to −15) — evaluator output is plausibly correct.

But:
- **v3 no_control = −7.48** is **half** of paper no_control = −15.20.
- This means v3 disturbance distribution is **weaker** than paper's:
  - v3: `pm_step_proxy_random_bus` at magnitude ∈ [0.1, 0.5] sys-pu = 10–50 MW per ESS (Path C proxy of Bus 7/Bus 9)
  - paper §IV-C "Load Step 1": **248 MW** load drop at Bus 14
  - paper §IV-C "Load Step 2": **188 MW** load surge at Bus 15
  - v3 magnitudes are **5–25× smaller** than paper scenarios
- Roadmap §Gap 1 already flagged this — v3 currently can't run paper-magnitude disturbances because LoadStep wiring is dead (§R2-Blocker1) and Path C uses Pm-step proxy at ESS terminal scale.

So the evaluator is plausibly working but compares two different-disturbance regimes. **The DDIC-vs-no-control inversion within v3's regime is the hard finding** (same disturbances in both).

---

## 5. Why DDIC is worse — root cause

P4.2-overnight I1 + I2 already flagged this:

- During training, r_h dominated 70 % of reward, r_f only ~12 %.
- Policy gradient pulls toward minimizing the dominant component (r_h) — that means **keep ΔH small**.
- But "keep ΔH small" at runtime doesn't mean "ΔH = 0" because the actor stochastic policy still emits non-zero ΔH/ΔD.
- Those non-zero ΔH/ΔD perturb M and D away from baseline (M=24, D=4.5) by amounts that turn out to **hurt frequency stability** more than help.
- Critic learned a value function that incorrectly maps "small ΔH penalty" to "high reward", masking the secondary effect that the chosen ΔH is **physically destabilizing**.

The 50-ep PHI sweep gate passed `phi_b1` because the gate criteria looked at **r_f% in band** + **freq reach in band** but did NOT compare absolute frequency response vs zero-action baseline. The gate is necessary but insufficient.

---

## 6. Direct upgrades for the gate (P4.2 v2 / Phase 4.3)

| # | Upgrade | Fix |
|---|---|---|
| **G1** | Add zero-action-baseline comparison to PHI sweep gate | Each PHI candidate run a 50-ep no-control eval alongside training; require `cum_unnorm_DDIC < cum_unnorm_no_control × 1.0` (= DDIC must beat no-control on paper-style global r_f formula) |
| **G2** | Add ROCOF + max\|Δf\| direct compare | Same: DDIC ≤ no-control on these |
| **G3** | Lower r_h dominance | Either PHI_F=500 or PHI_H=1e-5 (both reduce r_h share) |
| **G4** | Increase disturbance magnitude | Phase 5 path-A LoadStep (per Gap 1 path table) — gets to paper scenarios; or raise DIST_MAX in proxy mode |

---

## 7. Recommended next actions (ordered)

| Priority | Action | Wall | Why |
|---|---|---|---|
| ★★★★★ | **Re-run PHI sweep with paper-style global r_f gate** | ~3 hr | gate signal is wrong; current 50-ep gate doesn't catch policy regression |
| ★★★★★ | **Try `phi_paper_scaled` (1e-2/1e-2) + `phi_f_500` (PHI_F=500)** | ~3 hr | both push r_f share up; either could break the plateau |
| ★★★★ | **Reward formula audit** | ~30 min | confirm `_compute_reward` r_f / r_h mapping matches paper before tuning |
| ★★★ | **Phase 4.3 fixed scenario sets** | ~1 day | needed for paper-faithful Phase 5 verdict |
| ★★ | **LoadStep wiring (Path A scope expansion)** | ~1-2 days | gets v3 to paper-magnitude scenarios; only do if proxy approach can't close the gap |
| ★ | **Q7/Q2 ablation (P5.2)** | ~half day | diagnostic only; cheap re-eval of best.pt under both H=M and H=M/2 conventions |

---

## 8. Cross-check / sanity

- evaluator emits 3 normalization variants per roadmap §3.4 ✓
- 50-scenario deterministic generator (seed-stable; will be replaced by Phase 4.3 manifest) ✓
- bus distribution 23/27 ≈ 50/50 ± SD ✓
- `tds_failed=0`, `nan_inf=0` on both runs — engine + dispatch healthy ✓
- per_M = unnormalized / 50, per_M_per_N = unnormalized / 200 ✓ (matches table)
- v3 DDIC unnormalized −8.90 happens to coincidentally land near paper DDIC −8.04, but this is the **wrong** direction — DDIC should be ≤ no-control (more negative, but smaller magnitude than paper no-control −15.20).

---

## 9. Boundary check

- `build_kundur_cvs_v3.m` / `kundur_cvs_v3.slx` / `kundur_ic_cvs_v3.json` / `kundur_cvs_v3_runtime.mat`: untouched ✓
- `slx_helpers/vsg_bridge/*` / `engine/simulink_bridge.py`: untouched ✓
- `env/simulink/kundur_simulink_env.py` Path (C) dispatch: untouched ✓
- `agents/`, `scenarios/contract.py`, `scenarios/config_simulink_base.py`: untouched ✓
- Reward formula: untouched ✓
- LoadStep wiring: untouched ✓
- NE39: untouched ✓
- No 50-ep / 2000-ep training launched in P5.1 ✓ (eval-only, deterministic)

---

## 10. Artifacts

```
evaluation/
├── __init__.py
└── paper_eval.py                          (NEW; ~530 LOC; paper §IV-C global r_f impl + CLI)

probes/kundur/v3_dryrun/
└── _p51_paper_eval_runner.py              (NEW; sequential 2-policy runner)

results/harness/kundur/cvs_v3_phase4/
├── phase5_p51_paper_eval_verdict.md       (this file)
├── p51_runner_stdout.txt                  (orchestrator log)
├── p51_runner_stderr.txt                  (empty)
├── p51_aggregate_summary.json             (machine-readable)
├── p51_no_control_metrics.json            (50 scenarios, per-ep + summary + cumulative)
├── p51_no_control_stdout.txt              (per-scenario log)
├── p51_no_control_stderr.txt
├── p51_ddic_phi_b1_best_metrics.json      (50 scenarios, ditto)
├── p51_ddic_phi_b1_best_stdout.txt
└── p51_ddic_phi_b1_best_stderr.txt
```

---

## 11. Decision point

**Before any further training:** which path?

- **R1.** Reward formula audit (30 min, read-only) → catches any unintended scaling
- **R2.** PHI re-sweep with paper-style gate → use new evaluator as gate criterion (DDIC must beat zero-action baseline on cum_unnorm)
- **R3.** Try `phi_paper_scaled` (1e-2/1e-2) and/or PHI_F bump (100→500) before committing to long training
- **R4.** Phase 4.3 (fixed scenario sets) before any further training so all comparisons are reproducible

Recommend **R1 → R2 (with R3 candidates) → R4** in that order. R1 first because if reward formula has a bug, all PHI tuning is wasted.

Awaiting decision.
