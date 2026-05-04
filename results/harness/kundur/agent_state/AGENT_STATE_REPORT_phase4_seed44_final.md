# Agent State Probe Report

- timestamp: 2026-05-03T18:49:30
- schema_version: 1
- implementation_version: 0.1.0
- ckpt_dir: `results/andes_phase4_noPHIabs_seed44`
- ckpt_kind: final

## Verdicts (A1-A3)

| Gate | Verdict | Reason codes |
|---|---|---|
| A1 | PASS | A1_SPECIALIZED |
| A2 | PENDING | A2_IMBALANCED_CONTRIBUTION |
| A3 | REJECT | A3_HIGH_MAGNITUDE_FAILURES |

## A1 — Specialization

- offdiag cosine mean: **0.3096** (max 0.5380, min 0.1760)
- n_obs samples: 200

Pairwise cosine matrix:
```
  +1.000  +0.176  +0.361  +0.195
  +0.176  +1.000  +0.340  +0.538
  +0.361  +0.340  +1.000  +0.247
  +0.195  +0.538  +0.247  +1.000
```

Per-agent action stats (synthetic obs):
| agent | a0 (ΔM) μ | a0 σ | a1 (ΔD) μ | a1 σ |
|---|---|---|---|---|
| 0 | +0.073 | 0.344 | +0.309 | 0.591 |
| 1 | -0.339 | 0.401 | +0.668 | 0.409 |
| 2 | +0.535 | 0.328 | +0.745 | 0.275 |
| 3 | -0.118 | 0.430 | +0.400 | 0.532 |

## A2 — Ablation

- baseline cum_rf: **-0.2724** (20 eps)

| agent | ablated cum_rf | Δ cum_rf | share |
|---|---|---|---|
| 0 |   -0.3592 |  +0.0867 |  11.1% |
| 1 |   -0.8544 |  +0.5820 |  74.4% |
| 2 |   -0.3168 |  +0.0444 |   5.7% |
| 3 |   -0.3420 |  +0.0695 |   8.9% |

_Δ > 0 = agent contributes; share is normalized contribution._

## A3 — Failure Forensics

- n_episodes: 50 (errors: 0)
- max_df overall p50/p95/max: 0.2264 / 0.3491 / 0.3931
- n over 0.4 Hz threshold: 0
- worst-K most-common bus: **PQ_Bus14** (3 of 5)
- worstk magnitude median (pu): 1.800  (overall: 1.132)
- clustered_by_bus: False, clustered_by_sign: False

Worst K episodes:
| seed | max_df | dist_bus | dist_mag (pu) | sign | spread peak step | action L1 mean |
|---|---|---|---|---|---|---|
| 20048 | 0.3931 | PQ_Bus14 | -1.800 | -1 | 2 | 0.519 |
| 20001 | 0.3765 | PQ_Bus14 | -1.692 | -1 | 2 | 0.505 |
| 20041 | 0.3542 | PQ_1 | +1.802 | +1 | 3 | 0.485 |
| 20013 | 0.3427 | PQ_1 | +1.695 | +1 | 3 | 0.467 |
| 20036 | 0.3142 | PQ_Bus14 | +1.947 | +1 | 0 | 0.504 |

