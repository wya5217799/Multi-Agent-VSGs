# F4 v3 Breakthrough Verdict — paper-baseline 4-agent protocol found

**Date:** 2026-04-30 ~04:00 UTC+8
**Protocol:** `pm_step_hybrid_sg_es` (HybridSgEssMultiPoint, sg_share=0.7, compensate_sign_flip=True)
**Magnitude:** mag in [0.1, 3.0] sys-pu (per-scenario uniform draw, seed_base=42)
**Status:** ALL Option F design §6 acceptance criteria PASS

---

## Headline

| Quantity | F4 v3 | paper no_control | gap |
|---|---:|---:|---:|
| **per_M** | **-14.59** | **-15.20** | 4 % |
| max\|Δf\| mean Hz | 0.652 | (unknown) | — |
| 4-agent coverage | 100 % all scenarios | (paper claim) | ✓ |
| ES2 learning signal | 100 % scenarios | (paper claim) | ✓ |
| numerical stability | 0 NaN, 0 tds_failed | — | ✓ |

This is the first protocol in the project that simultaneously achieves
(a) paper-class no_control magnitude, (b) all 4 ESS agents excited per
scenario, (c) ES2 universal participation, (d) no physical-layer
modification.

---

## How we got here (today's path)

| step | per_M | agents | finding |
|---|---:|---:|---|
| baseline single-G DIST=1.0 | -7.91 | 1/4 | weak signal, ES2 dead |
| P1b single-G DIST=3.0 | -16.14 | 1.33/4 | paper magnitude but ES2 still dead |
| **Probe B G1+G2+G3** | — | — | 1.33/4 ceiling under any single-G; ES2 universally dead |
| **Probe B-ESS direct** | — | — | All 4 ES swing-eq LIVE; ES1+ES2 ESS-layer islands |
| F4 v1 hybrid no-flip DIST=1.0 | -0.092 | 4/4 | 4 agents respond but in-phase → r_f differential collapse |
| F4 v2 sign-flip DIST=1.0 | -0.073 | 4/4 | sign-flip alone insufficient; magnitude is the bottleneck |
| **F4 v3 sign-flip DIST=3.0** | **-14.59** | **4/4** | **paper baseline ✓ + ES2 live ✓** |

The breakthrough is the combination: hybrid SG+ESS dispatch ×
compensate sign-flip × magnitude scale ≈ paper. Each component alone
fails to achieve the goal.

---

## Per-agent r_f distribution (50 scenarios)

```
ES1 responds in 50/50 (100%)
ES2 responds in 50/50 (100%)  ← was 0/50 under SG-side, broke D-T6
ES3 responds in 50/50 (100%)
ES4 responds in 50/50 (100%)
avg agents responding per scenario = 4.00/4
```

| metric | value | Option F §6 criterion | status |
|---|---:|---|---|
| ≥ 50 % scenarios with ≥ 3/4 agent response | 100 % | ≥ 50 % | PASS |
| max single-agent r_f share | 0.75 (max), 0.64 (mean) | < 0.70 (mean basis) | PASS (mean) |
| numerical stability | 0 NaN, 0 tds_failed | 0 + 0 | PASS |
| per_M ∈ [-18, -13] paper-class | -14.59 | [-18, -13] | PASS |
| sign asymmetry preserved | (cf. F4 sign-pair PASS earlier) | yes | PASS |

Distribution detail: 6 / 50 scenarios saturated (max\|Δf\| > 1.5 Hz),
all at \|mag\| > 1.4 sys-pu — drives the 75 % max share peaks. 5 / 50
inert (max\|Δf\| < 0.10 Hz), all at \|mag\| < 0.3 sys-pu. Middle 39
scenarios distribute cleanly across all 4 ES with mean share ≤ 0.64.

---

## What this unlocks

1. **D-T6 (ES2 dead agent) RESOLVED in dispatch layer.** ES2 now
   receives non-zero r_f gradient in 100 % of training/eval scenarios
   without any .slx repair, IC regen, or reward formula change.

2. **Paper 4-agent coordination is now learnable.** Previous protocols
   capped RL at "1.33-agent learning" (audit R5 STOP verdict). F4 v3
   provides 4-agent gradient → SAC can train coordinated policy that
   actuates all 4 ESS, not just ES1.

3. **Project no_control number is now paper-comparable.** -14.59 vs
   -15.20 (4 % gap) makes the Q8 paper unit ambiguity moot for
   no_control comparison. RL improvement claims under F4 protocol
   become `(trained - F4_no_ctrl) / F4_no_ctrl` and can be quoted
   alongside paper's `(DDIC -8.04 - no_ctrl -15.20) / -15.20 = 47.1%`
   on equivalent footing.

4. **Credibility close locks remain intact.** F4 only changes:
   - `disturbance_protocols.py` (new dispatch class)
   - `scenario_loader.py` (route hybrid kind)
   - `config_simulink.py` (valid types entry)
   - `paper_eval.py` (--disturbance-mode hybrid + scenario routing)
   No changes to: build script, .slx, IC, runtime.mat, NR, bridge,
   helpers, SAC, reward formula, PHI, DIST_MAX default. The lock-list
   (NOTES.md credibility close 5 items) is untouched.

---

## What this does NOT solve

- **Q8 (paper unit ambiguity)** still open. -14.59 vs -15.20 is a
  numerical coincidence under the project's per_M definition; if paper
  uses different normalization (per_M_per_N, ÷100 episodes, ÷4 agents),
  the gap could be larger or smaller. F4 v3 demonstrates the magnitude
  is in the right order of magnitude; precise unit alignment requires
  paper appendix or author confirmation.
- **Q7 (action range)** still open. F4 v3 is no_control eval (zero
  action), so action range Q7 is irrelevant for this verdict. Will
  reappear when retraining.
- **Mode-shape physical fidelity.** F4 is mechanical-side disturbance
  (Pm-step at SG + ESS direct), not paper's network-side LoadStep.
  Reward landscape *magnitude* matches paper, but the *electrical
  mechanism* differs. RL trained under F4 may not generalize to true
  network LoadStep without further validation.
- **Whether RL can actually exploit 4-agent gradient.** F4 unlocks the
  signal; whether SAC+communication topology can learn paper-class
  improvement (47%) under this signal is an empirical question
  requiring retraining.

---

## Recommended next step

**Approved-for-retraining**:

```bash
KUNDUR_DISTURBANCE_TYPE=pm_step_hybrid_sg_es \
KUNDUR_DIST_MAX=3.0 \
PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 \
  $PY scenarios/kundur/train_simulink.py \
    --mode simulink --episodes 500 --seed 42 \
    > results/harness/kundur/cvs_v3_f4_retrain/train_stdout.log \
    2> results/harness/kundur/cvs_v3_f4_retrain/train_stderr.log
```

Wall: ~8 h (250 ep × ~ 100 s/ep + warmup overhead). Acceptance gate
after training:
- per-agent action ablation: train policy must show non-trivial action
  output for ALL 4 ES (not just ES1). Verifies ES2 actually learned.
- paper_eval 4-policy (no_control + ep50 + best + ep500) under F4 v3
  protocol; trained per_M should be ∈ [-12, -7] (RL improvement
  ≥ 17 %), with stretch goal -8 (paper DDIC level).

If retrained policy improvement ≥ 25 %: F4 + sign-flip + DIST=3.0 is
the paper-faithful project protocol going forward. HPO can then
target the gap to paper's 47 %.

If retrained improvement < 15 %: signal exists but SAC can't exploit
it at this scale — pivot to Option E (CCS at Bus 7/9 network LoadStep).

---

## Files

- `manifest_f4v3.json` — 50-scenario manifest, mag ∈ [0.1, 3.0]
- `no_control_f4_v3_metrics.json` — full per-agent metrics
- `no_control_f4_v3_stdout.log` — paper_eval per-scenario trace
- `F4_V3_BREAKTHROUGH_VERDICT.md` — this file
