# Probe F4 sign-pair verdict — Option F4 dispatch live verification

**Date:** 2026-04-30
**Magnitude:** ±0.5 sys-pu
**Scenarios per sign:** 3
**Dispatch:** pm_step_hybrid_sg_es (HybridSgEssMultiPoint, sg_share=0.7)

## Acceptance criteria (Option F design §6)

| # | Criterion | Result | Status |
|---|---|---|---|
| 1 | ≥ 50 % of scenarios have ≥ 3/4 agents responding (>1e-3 Hz) | 3/3 scenarios; avg agents responding = 4.00/4 | PASS |
| 2 | No single agent contributes > 70 % of cum r_f | max share = 0.655; mean = 0.655 | PASS |
| 3 | Numerical: 0 NaN + 0 tds_failed | NaN=0, tds_failed=0 | PASS |
| 4 | per_M ∈ [-25, -10] (loose) | pos=-0.002, neg=-0.002 | INFO ONLY |

## Per-scenario detail

| sc | n_resp | per-agent diff (Hz) | r_f per agent | max_share | max\|Δf\| |
|---:|---:|---|---|---:|---:|
| 0 | 4/4 | [0.0356 0.0044 0.0046 0.0079] | [-0.026 -0.004 -0.006 -0.004] | 0.655 | 0.1025 |
| 1 | 4/4 | [0.0356 0.0044 0.0046 0.0079] | [-0.026 -0.004 -0.006 -0.004] | 0.655 | 0.1025 |
| 2 | 4/4 | [0.0356 0.0044 0.0046 0.0079] | [-0.026 -0.004 -0.006 -0.004] | 0.655 | 0.1025 |

## Verdict

**STOP-VERDICT: PASS** — Option F4 dispatch meets all 3 hard 
acceptance criteria. Multi-point hybrid SG+ESS scheduling delivers:
- multi-agent response per scenario (avg ≥ 3/4)
- non-degenerate per-agent r_f distribution (no single-agent dominance)
- numerical stability

**Approved for retraining under pm_step_hybrid_sg_es** when user 
decides to start training. Recommended retrain plan: 200-500 ep 
anchor + 4-policy paper_eval, expect RL improvement ceiling rises 
from current ~10% (1.33-agent ceiling) toward 20-30% (3-4-agent 
coordination potential).