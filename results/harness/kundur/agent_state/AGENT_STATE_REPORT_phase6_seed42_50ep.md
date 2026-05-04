# Agent State Probe Report

- timestamp: 2026-05-03T20:09:31
- schema_version: 1
- implementation_version: 0.1.0
- ckpt_dir: `results/andes_phase6_phiabs10_seed42`
- ckpt_kind: final

## Verdicts (A1-A3)

| Gate | Verdict | Reason codes |
|---|---|---|
| A1 | PENDING | A1_INTERMEDIATE |
| A2 | REJECT | A2_FREERIDER_DETECTED |
| A3 | REJECT | A3_HIGH_MAGNITUDE_FAILURES |

## A1 — Specialization

- offdiag cosine mean: **0.7596** (max 0.8753, min 0.6328)
- n_obs samples: 200

Pairwise cosine matrix:
```
  +1.000  +0.778  +0.675  +0.875
  +0.778  +1.000  +0.633  +0.868
  +0.675  +0.633  +1.000  +0.729
  +0.875  +0.868  +0.729  +1.000
```

Per-agent action stats (synthetic obs):
| agent | a0 (ΔM) μ | a0 σ | a1 (ΔD) μ | a1 σ |
|---|---|---|---|---|
| 0 | -0.508 | 0.087 | +0.110 | 0.263 |
| 1 | -0.401 | 0.148 | +0.197 | 0.207 |
| 2 | -0.538 | 0.125 | -0.121 | 0.153 |
| 3 | -0.442 | 0.137 | +0.149 | 0.098 |

## A2 — Ablation

- baseline cum_rf: **-0.5754** (20 eps)

| agent | ablated cum_rf | Δ cum_rf | share |
|---|---|---|---|
| 0 |   -0.5792 |  +0.0038 |   0.5% |
| 1 |   -0.9274 |  +0.3520 |  46.8% |
| 2 |   -0.7590 |  +0.1836 |  24.4% |
| 3 |   -0.7887 |  +0.2133 |  28.3% |

_Δ > 0 = agent contributes; share is normalized contribution._

## A3 — Failure Forensics

- n_episodes: 50 (errors: 0)
- max_df overall p50/p95/max: 0.2366 / 0.4239 / 0.4544
- n over 0.4 Hz threshold: 4
- worst-K most-common bus: **PQ_Bus14** (3 of 5)
- worstk magnitude median (pu): 1.802  (overall: 1.132)
- clustered_by_bus: False, clustered_by_sign: False

Worst K episodes:
| seed | max_df | dist_bus | dist_mag (pu) | sign | spread peak step | action L1 mean |
|---|---|---|---|---|---|---|
| 20048 | 0.4544 | PQ_Bus14 | -1.800 | -1 | 2 | 0.498 |
| 20036 | 0.4375 | PQ_Bus14 | +1.947 | +1 | 1 | 0.545 |
| 20001 | 0.4276 | PQ_Bus14 | -1.692 | -1 | 2 | 0.488 |
| 20000 | 0.4193 | PQ_Bus15 | +1.853 | +1 | 1 | 0.575 |
| 20041 | 0.3971 | PQ_1 | +1.802 | +1 | 3 | 0.545 |

