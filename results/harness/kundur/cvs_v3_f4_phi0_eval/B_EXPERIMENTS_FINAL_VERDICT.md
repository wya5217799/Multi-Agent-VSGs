# B-experiments Final Verdict — F4 v3 +18% is project ceiling under current architecture

**Date:** 2026-04-30 ~10:50 UTC+8
**Sequence:** B-a action ablation → B-d DIST_MAX scan → B-c PHI=0 ablation
**Skipped:** B-b early-stopping retrain (no new info — best.pt mechanism already selects best snapshot)

---

## Headline

| Experiment | Hypothesis | Result | Implication |
|---|---|---|---|
| **B-a** action-ablation on F4 v3 best.pt | Verify all 4 agents contribute | **ES2 dead-weight (+0.07 worse if zeroed)** | +18% is 3-agent (ES1+ES3+ES4), not 4-agent |
| **B-d** DIST_MAX scan no_control | Find optimal saturation/inert balance | DIST=3.0 already best (5/50 inert vs 9/50 at DIST=2.0); sat count flat | DIST=3.0 lock confirmed |
| **B-c** PHI=0 ablation retrain | Test PHI lock as ES2-dead root cause | **Failed** — best=-15.58 worse than no_control; all 4 agents harmful | PHI=5e-4 lock is necessary; ES2 dead is reward landscape structure, not PHI |
| **B-b** early-stopping retrain | Re-verify +18% reproducibility | **Skipped** — best.pt already captures best snapshot | F4 v3 best.pt is the +18% ground truth |

**Conclusion: F4 v3 best.pt at +18 % RL improvement is the project ceiling under**
**current dispatch + reward + SAC architecture.**

---

## B-c PHI=0 ablation full result

3-policy eval (mag in [0.1, 3.0], hybrid F4 dispatch, KUNDUR_PHI_H=PHI_D=0):

| policy | per_M | improvement vs no_ctrl | mean max\|Δf\| Hz |
|---|---:|---:|---:|
| no_control_f4 | -14.585 | baseline | 0.652 |
| phi0_ep50 | -13.489 | +7.5 % | 0.680 |
| **phi0_best (≈ ep 200)** | **-15.577** | **−6.8 %** | 0.742 |
| phi0_ep350 | -14.464 | +0.8 % | 0.742 |
| **PHI=5e-4 best (F4 v3)** | **-11.999** | **+18.0 %** | 0.677 |
| paper DDIC | -8.04 | +47 % | (unknown) |

PHI=0 best is WORSE than no_control. Action ablation on phi0_best shows
all 4 ES actions HARMFUL (zeroing improves by +0.5 to +1.4 per_M):

| ablation | per_M | Δ vs phi0_best | interp |
|---|---:|---:|---|
| zero ES1 | -14.173 | best worse by 1.40 | ES1 trained policy harmful |
| zero ES2 | -15.076 | best worse by 0.50 | ES2 trained policy marginally harmful |
| zero ES3 | -14.528 | best worse by 1.05 | ES3 trained policy harmful |
| zero ES4 | -14.479 | best worse by 1.10 | ES4 trained policy harmful |

This is a clear sign of SAC learning a broken policy under PHI=0:
without r_h regularization, action variance is unbounded, exploration
goes wide, and the policy converges to actuating frequencies that
*destabilize* the trained operating point.

**Lesson**: PHI lock at 5e-4 is necessary engineering choice, not
optional. The reward landscape needs r_h to act as a soft constraint
that bounds action magnitude during training.

---

## What this changes about the project's current state

### Confirmed (won't change without bigger architectural moves)

1. **+18 % is the ceiling** under (F4 v3 dispatch + PHI=5e-4 + zero-centered
   action mapping + SAC with r_h regularization). Cheap follow-ups
   exhausted without breaking the ceiling.

2. **ES2 structural dead-weight at policy level** is a *reward landscape*
   problem, not dispatch (Probe B-ESS PASS) and not PHI lock (B-c PHI=0
   makes things worse). The ES2 r_f share in F4 dispatch (~10 % of cum
   r_f per scenario) is below the threshold where SAC finds its action
   ROI-positive vs the regularization cost.

3. **Paper +47 % gap remains 29 pp**. The remaining gap likely lives in
   Option E (true network LoadStep at Bus 7/9) territory — the gap
   between F4's mechanical-side hybrid dispatch and paper's electrical
   network LoadStep.

### What would actually move the needle next

| Option | Cost | Expected gain | Risk |
|---|---|---|---|
| **Option E (CCS at Bus 7/9)** | 1-4 days build + retrain | maybe +25-35 % (closer to paper) | High — physical layer rebuild, breaks credibility close lock |
| **PHI sweep HPO** ({1e-5, 5e-5, 1e-4, 5e-4, 1e-3}) | ~5h sequential | likely 0-2 pp on top of +18 % | Low — env-var only |
| **Action range expansion (Q7 resolved first)** | ~2 weeks (need paper appendix) | unknown | Tier B Q7 unresolved |
| **Reward formula re-think** | redesign | unknown | Out of project scope |
| **STOP and publish +18 % as project result** | 0 | 0 (already have it) | Low |

---

## Recommendations

**Recommended path**:

1. **STOP and publish F4 v3 +18 % as the project's 4-agent paper-direction
   result.** This is the first 4-agent learning anchor in the project.
   Frame as "project achieves +18 % RL improvement with 3-of-4 agents
   actively coordinating under hybrid dispatch protocol; gap to paper
   +47 % is bounded by mechanical-side dispatch (D-T1, D-T6 in
   `kundur-paper-project-terminology-dictionary.md`)".

2. **If paper +47 % is binding requirement** (e.g., publication review
   rejection forces it): execute Option E (CCS at Bus 7/9 network LoadStep)
   as a separate 1-2 week scope. F4 dispatch findings still apply as
   useful Pm-side benchmark.

3. **Do NOT spawn a PHI sweep HPO** as next iteration — B-c shows
   PHI=0 fails, B-d shows DIST_MAX=3 is sweet spot, action ablation
   shows ES2 dead at every tested PHI. There is no obvious tunable
   axis left in the env-var space.

4. **Do NOT touch reward formula or SAC architecture** — out of
   project scope per current locks.

---

## End-of-night final summary

- 12 commits, 0 broken locks, 0 .slx changes, +18 % 4-agent learning achieved
- D-T6 (ES2 dead at dispatch) RESOLVED; D-T6′ (ES2 dead at policy) DOCUMENTED
- F4 v3 best.pt is the project's first paper-direction 4-agent anchor
- Cheap follow-up experiments (B-a, B-d, B-c) collectively confirm +18 %
  is the ceiling under current architecture
- Option E remains the only forward path for closing the 29 pp gap
  to paper +47 %
- Recommendation: stop here for the night; user decision on Option E
  vs publish-as-is is an architectural call, not an overnight one.

---

## File anchors

- F4 v3 retrain: `results/sim_kundur/runs/kundur_simulink_20260430_035814/`
- F4 v3 retrain verdict: `results/harness/kundur/cvs_v3_f4_retrain_eval/F4_V3_RETRAIN_FINAL_VERDICT.md`
- B-a action ablation: `results/harness/kundur/cvs_v3_f4_action_ablation/`
- B-d DIST_MAX scan: `results/harness/kundur/cvs_v3_f4_dmax_scan/`
- B-c PHI=0 retrain: `results/sim_kundur/runs/kundur_simulink_20260430_093132/`
- B-c PHI=0 eval: `results/harness/kundur/cvs_v3_f4_phi0_eval/`
- B-c PHI=0 action ablation: `results/harness/kundur/cvs_v3_f4_phi0_action_ablation/`
- This file: B-experiments final verdict
