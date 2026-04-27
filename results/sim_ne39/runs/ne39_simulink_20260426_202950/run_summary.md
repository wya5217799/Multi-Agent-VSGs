# NE39 Training Run Summary
**run_id**: `ne39_simulink_20260426_202950`
**date**: 2026-04-26 ~ 2026-04-27
**status**: Stopped manually at ep 257 (plateau diagnosis)

## Configuration
- resumed from: `ne39_simulink_20260417_062136/checkpoints/ep150.pt` (step=60000)
- mode: simulink
- episodes planned: 500 (ran 150→257, 107 new episodes)
- disturbance_mode: gen_trip
- episode length: 10s, 50 steps

## Key Metrics at Stop (ep 257)
| metric | value |
|--------|-------|
| episodes_done (this run) | 108 |
| reward_mean_50 | -249 |
| best eval_reward | -175 (ep 249) |
| critic_loss | 0.009 (converged) |
| alpha | 0.005 (minimum) |
| settled_rate | 0 / 108 (0%) |
| freq < 2 Hz | 0 / 108 |
| freq ≥ 10 Hz | 40 / 108 (37%) |

## Reward Trajectory
| bracket | mean reward |
|---------|-------------|
| ep 150-179 | -417 |
| ep 180-199 | -272 |
| ep 200-219 | -236 (best) |
| ep 220-239 | -242 |
| ep 240-257 | -253 (slight degradation) |

## Stop Rationale
1. Policy entropy collapsed: alpha=0.005 (minimum) for 5+ consecutive episodes → no exploration
2. Reward plateau with slight degradation since ep 220
3. Critic converged (loss 0.009) — learning infrastructure exhausted
4. settled_rate = 0/108 throughout — structural issue, not data starvation
5. r_f share still only ~10% (target ~50%) despite growing trend

## Root Cause Hypothesis
gen_trip disturbance (~100 MW) causes 8–12 Hz frequency excursions in a
10-second episode. System cannot physically settle within episode window.
r_f penalty weight (PHI_F) may need retuning to properly incentivise
frequency control before the policy commits to a passive strategy.

## Recommended Next Steps
- Option A: `disturbance_mode=curriculum` — warm up on `apply` (±5–15 MW),
  then switch to gen_trip after settled_rate > 0
- Option B: Extend episode length (10s → 20s) to allow settling time
- Option C: Increase PHI_F until r_f share reaches ~50% of total reward,
  then resume from `latest.pt` (ep 257)

## Checkpoints Saved (gitignored, local only)
- `checkpoints/latest.pt` — ep 257, 2.2 MB
- `checkpoints/ep200.pt` — ep 200, 2.2 MB
- `checkpoints/best.pt` — best eval checkpoint
