# Agent State Probe Report

- timestamp: 2026-05-04T08:27:12
- schema_version: 1
- implementation_version: 0.1.0
- ckpt_dir: `results/andes_phase4_noPHIabs_seed46`
- ckpt_kind: final

## Verdicts (A1-A3)

| Gate | Verdict | Reason codes |
|---|---|---|
| A1 | PASS | A1_SPECIALIZED |
| A2 | PENDING | A2_IMBALANCED_CONTRIBUTION |
| A3 | REJECT | A3_CLUSTERED_SIGN, A3_HIGH_MAGNITUDE_FAILURES |

## A1 — Specialization

- offdiag cosine mean: **0.3066** (max 0.6220, min -0.1094)
- n_obs samples: 200

Pairwise cosine matrix:
```
  +1.000  +0.365  +0.060  -0.109
  +0.365  +1.000  +0.622  +0.458
  +0.060  +0.622  +1.000  +0.443
  -0.109  +0.458  +0.443  +1.000
```

Per-agent action stats (synthetic obs):
| agent | a0 (ΔM) μ | a0 σ | a1 (ΔD) μ | a1 σ |
|---|---|---|---|---|
| 0 | +0.419 | 0.394 | +0.163 | 0.744 |
| 1 | +0.621 | 0.295 | +0.809 | 0.227 |
| 2 | +0.365 | 0.379 | +0.421 | 0.681 |
| 3 | +0.124 | 0.303 | +0.368 | 0.629 |

## A2 — Ablation

- baseline cum_rf: **-0.3560** (20 eps)

| agent | ablated cum_rf | Δ cum_rf | share |
|---|---|---|---|
| 0 |   -0.4100 |  +0.0539 |   6.2% |
| 1 |   -0.8487 |  +0.4927 |  56.2% |
| 2 |   -0.5444 |  +0.1884 |  21.5% |
| 3 |   -0.4979 |  +0.1419 |  16.2% |

_Δ > 0 = agent contributes; share is normalized contribution._

## A3 — Failure Forensics

- n_episodes: 50 (errors: 0)
- max_df overall p50/p95/max: 0.2402 / 0.3501 / 0.4080
- n over 0.4 Hz threshold: 1
- worst-K most-common bus: **PQ_Bus14** (2 of 5)
- worstk magnitude median (pu): 1.802  (overall: 1.132)
- clustered_by_bus: False, clustered_by_sign: True

Worst K episodes:
| seed | max_df | dist_bus | dist_mag (pu) | sign | spread peak step | action L1 mean |
|---|---|---|---|---|---|---|
| 20036 | 0.4080 | PQ_Bus14 | +1.947 | +1 | 0 | 0.552 |
| 20023 | 0.3539 | PQ_Bus14 | +1.702 | +1 | 0 | 0.586 |
| 20041 | 0.3517 | PQ_1 | +1.802 | +1 | 2 | 0.581 |
| 20013 | 0.3481 | PQ_1 | +1.695 | +1 | 5 | 0.589 |
| 20000 | 0.3472 | PQ_Bus15 | +1.853 | +1 | 1 | 0.633 |

