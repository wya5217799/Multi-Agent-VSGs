# Agent State Probe Report

- timestamp: 2026-05-03T22:15:17
- schema_version: 1
- implementation_version: 0.1.0
- ckpt_dir: `results/andes_phase7_phif_es3_boost_seed42`
- ckpt_kind: final

## Verdicts (A1-A3)

| Gate | Verdict | Reason codes |
|---|---|---|
| A1 | PASS | A1_SPECIALIZED |
| A2 | REJECT | A2_FREERIDER_DETECTED |
| A3 | REJECT | A3_CLUSTERED_SIGN, A3_HIGH_MAGNITUDE_FAILURES |

## A1 — Specialization

- offdiag cosine mean: **0.3317** (max 0.5554, min -0.0550)
- n_obs samples: 200

Pairwise cosine matrix:
```
  +1.000  +0.555  +0.190  +0.463
  +0.555  +1.000  +0.420  +0.418
  +0.190  +0.420  +1.000  -0.055
  +0.463  +0.418  -0.055  +1.000
```

Per-agent action stats (synthetic obs):
| agent | a0 (ΔM) μ | a0 σ | a1 (ΔD) μ | a1 σ |
|---|---|---|---|---|
| 0 | -0.315 | 0.255 | +0.381 | 0.425 |
| 1 | -0.197 | 0.105 | +0.531 | 0.382 |
| 2 | -0.014 | 0.361 | +0.336 | 0.379 |
| 3 | +0.014 | 0.308 | +0.236 | 0.302 |

## A2 — Ablation

- baseline cum_rf: **-0.4883** (20 eps)

| agent | ablated cum_rf | Δ cum_rf | share |
|---|---|---|---|
| 0 |   -0.4974 |  +0.0091 |   1.1% |
| 1 |   -1.0125 |  +0.5242 |  63.2% |
| 2 |   -0.5637 |  +0.0754 |   9.1% |
| 3 |   -0.7097 |  +0.2214 |  26.7% |

_Δ > 0 = agent contributes; share is normalized contribution._

## A3 — Failure Forensics

- n_episodes: 50 (errors: 0)
- max_df overall p50/p95/max: 0.2486 / 0.3692 / 0.3836
- n over 0.4 Hz threshold: 0
- worst-K most-common bus: **PQ_1** (2 of 5)
- worstk magnitude median (pu): 1.800  (overall: 1.132)
- clustered_by_bus: False, clustered_by_sign: True

Worst K episodes:
| seed | max_df | dist_bus | dist_mag (pu) | sign | spread peak step | action L1 mean |
|---|---|---|---|---|---|---|
| 20041 | 0.3836 | PQ_1 | +1.802 | +1 | 3 | 0.497 |
| 20015 | 0.3769 | PQ_0 | +1.743 | +1 | 4 | 0.488 |
| 20036 | 0.3715 | PQ_Bus14 | +1.947 | +1 | 0 | 0.504 |
| 20013 | 0.3665 | PQ_1 | +1.695 | +1 | 3 | 0.488 |
| 20048 | 0.3616 | PQ_Bus14 | -1.800 | -1 | 0 | 0.361 |

