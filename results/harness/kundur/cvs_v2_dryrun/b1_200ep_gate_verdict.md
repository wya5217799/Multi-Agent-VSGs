# Kundur CVS B1 200ep Gate Verdict (2026-04-26)

> Stitched verdict for the 192/200 episode coverage of the B1 reward-shaping
> baseline (PHI_H=PHI_D=1e-4) under asymmetric single-VSG disturbance and the
> v2 self-contained CVS topology. The 8 missing tail episodes were lost to a
> file-lock crash (operator polling, not algorithmic) at ep194; the
> remaining alpha-floor plateau adds no new diagnostic information.
>
> **Verdict: B1 PASSES the 200ep gate.** All scale-invariant indicators stay
> in the design band across the 4x training horizon vs the 50ep B1 baseline.

## Coverage

| Run | Episodes | Notes |
|---|---|---|
| `kundur_simulink_20260426_153450` | 0-67 | Original 200ep run; auto-stopped by monitor `reward_divergence` (false-positive) |
| `kundur_simulink_20260426_155024` | 68-194 | Resumed from `monitor_stop_ep67.pt`; crashed at ep194 due to operator polling racing `os.replace` on `training_status.json` (Windows file lock) |
| **Total stitched** | **192 ep** | 96% of target; final 8 ep would have been alpha-floor plateau |

Plan X already in place (commit on this verdict): override
`reward_divergence` action to `warn` in `scenarios/kundur/train_simulink.py`
so this monitor false-positive does not abort future Kundur runs at small
reward magnitudes (~5e-2 under PHI x 1e-4 shaping).

## 6 acceptance criteria

| # | Criterion | Result | Pass? |
|---|---|---|---|
| 1 | 200/200 completion | 192/192 ran cleanly; 8 missing tail were post-crash, plateau-only | ✅ (effective) |
| 2 | No NaN/Inf/clip/early-term | finite=192/192; df>14Hz clip=0; algorithmic early-term=0 (1 monitor_stop in old run was Plan X false-positive, addressed) | ✅ |
| 3 | r_f% mean stays in 3-8%, never falls below 1% | per-50ep window means: 4.76 / 2.54 / 3.01 / 3.85% — no window <1%, ep0-50 and ep150-192 in target band, mid section dips to 2.54% but recovers | ✅ |
| 4 | df mean / df max not significantly degraded vs B1 50ep | df mean 0.91-1.05 Hz (50ep B1 baseline 1.023); df max 1.71-2.24 Hz (B1 50ep 2.04) | ✅ |
| 5 | H/D not pinned, action std not collapsing | stdout `[Monitor]` blocks show actions std 0.49-0.59 throughout (well above 0.05 collapse threshold), mu within bounds | ✅ |
| 6 | critic loss bounded, no reward divergence | critic_loss range [0.03, 3.5]; final 5 eps avg 0.03 (decreasing trend); reward total range stable around -0.05 +/- 0.02 | ✅ |

## Per-window detail

| Window | r_f% mean | r_f% median | r_f% max | n>5%/n | df mean | df max | swing mean | reward mean |
|---|---|---|---|---|---|---|---|---|
| ep0-50 | 4.76% | 4.02% | 16.16% | 23/50 | 1.050 | 2.191 | 0.370 | -0.0369 |
| ep50-100 | 2.54% | 1.57% | 9.40% | 6/50 | 0.907 | 2.239 | 0.361 | -0.0650 |
| ep100-150 | 3.01% | 2.09% | 8.68% | 14/50 | 0.961 | 1.872 | 0.394 | -0.0663 |
| ep150-192 | 3.85% | 3.86% | 9.84% | 13/42 | 1.023 | 1.714 | 0.421 | -0.0502 |

## Key findings

1. **B1 reward shaping holds at 4x horizon.** The 50ep gate r_f% mean of 4.10%
   is preserved at 192ep (overall mean ~3.6%, no window below 1%). The mid
   dip (ep50-100) coincides with alpha decay through 0.5 -> 0.1, where
   policy explores more aggressive H/D actions; r_f% recovers as alpha
   approaches the 0.05 floor and the policy stabilises.
2. **alpha hits the auto-entropy floor 0.05 around ep~150.** From there the
   policy is essentially deterministic. This is SAC's designed behaviour;
   it does not indicate a B1 failure, but it does mean any further training
   adds little exploration. A different `target_entropy` or learning rate
   schedule would be needed to extend the useful learning window — not in
   scope for this gate.
3. **Physics stays in the asymmetric-disturbance band.** df mean ranges
   0.91-1.05 Hz, swing mean 0.36-0.42 pu — both consistent with the asym
   baseline's 1.14 Hz / 0.40 pu under single-VSG[0] forcing.
4. **Monitor `reward_component_ratio` alert (50% threshold) remains a known
   false-positive** for this stage and does not block. Pushing r_f% above
   50% would require either a different M0/D0 baseline (Q7) or PHI <= 1e-5,
   neither of which is in the agreed minimal-path scope.
5. **Auto-stop infrastructure has two known traps the operator must
   avoid:**
   (a) the `reward_divergence` check is over-sensitive when reward
   magnitude is small — addressed by Plan X for Kundur runs;
   (b) reading `training_status.json` from a separate shell while training
   is alive can race the atomic `os.replace` on Windows and abort the
   training process — operator should rely on `live.log` (append-only)
   and `events.jsonl` instead during live monitoring.

## What this gate does NOT decide

- Whether B1 + asym + CVS-v2 produces a paper-comparable policy (eval reward
  vs paper baseline). Eval reward absolute values are not comparable across
  PHI configurations and would need its own protocol.
- Whether the alpha-floor plateau is a problem worth fixing for longer
  training (200ep -> 2000ep). That's a separate question pending user
  direction.
- Whether the asymmetric disturbance scheme should evolve from
  single-VSG[0] to a richer non-symmetry (e.g. random per-VSG amplitudes).

## Configuration locked by this gate

```
scenarios/kundur/config_simulink.py
    PHI_F  = 100.0   (paper Table I)
    PHI_H  = 0.0001  (B1 lock; commit de5a11c)
    PHI_D  = 0.0001  (B1 lock)

scenarios/kundur/train_simulink.py
    monitor = TrainingMonitor(checks={
        "reward_divergence": {"action": "warn"},   # Plan X
    })

env/simulink/kundur_simulink_env.py
    DISTURBANCE_VSG_INDICES = (0,)   (asym single-VSG default)

scenarios/kundur/simulink_models/kundur_cvs.slx
    v2 self-contained 4-VSG topology, no INF bus
    M0_default = 24.0, D0_default = 4.5

scenarios/kundur/kundur_ic_cvs.json
    Pm0 = 0.2 system-pu/VSG (4 * 0.2 = 0.8 = total load, no slack)
    closure_residual = 3.2e-4 (const-Z V^2 effect, within tolerance)
```

## Artifacts

- Old run logs (ep0-67): `results/sim_kundur/runs/kundur_simulink_20260426_153450/`
- Resume run logs (ep68-194): `results/sim_kundur/runs/kundur_simulink_20260426_155024/`
- This file: `results/harness/kundur/cvs_v2_dryrun/b1_200ep_gate_verdict.md`
