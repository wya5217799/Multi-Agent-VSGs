# Agent State Probe Report

- timestamp: 2026-05-04T06:03:36
- schema_version: 1
- implementation_version: 0.1.0
- ckpt_dir: `results/andes_phase4_noPHIabs_seed42`
- ckpt_kind: final

## Verdicts (A1-A3)

| Gate | Verdict | Reason codes |
|---|---|---|
| A1 | PASS | A1_SPECIALIZED |
| A2 | REJECT | A2_FREERIDER_DETECTED |
| A3 | REJECT | A3_CLUSTERED_BUS, A3_CLUSTERED_SIGN, A3_HIGH_MAGNITUDE_FAILURES |

## A1 — Specialization

- offdiag cosine mean: **0.3521** (max 0.5909, min 0.1604)
- n_obs samples: 200

Pairwise cosine matrix:
```
  +1.000  +0.305  +0.465  +0.160
  +0.305  +1.000  +0.591  +0.295
  +0.465  +0.591  +1.000  +0.296
  +0.160  +0.295  +0.296  +1.000
```

Per-agent action stats (synthetic obs):
| agent | a0 (ΔM) μ | a0 σ | a1 (ΔD) μ | a1 σ |
|---|---|---|---|---|
| 0 | -0.293 | 0.443 | +0.509 | 0.528 |
| 1 | +0.292 | 0.631 | +0.811 | 0.495 |
| 2 | +0.008 | 0.358 | +0.697 | 0.483 |
| 3 | +0.224 | 0.707 | +0.418 | 0.551 |

## A2 — Ablation

- baseline cum_rf: **-0.4191** (20 eps)

| agent | ablated cum_rf | Δ cum_rf | share |
|---|---|---|---|
| 0 |   -0.4362 |  +0.0171 |   3.0% |
| 1 |   -0.8151 |  +0.3961 |  68.3% |
| 2 |   -0.4983 |  +0.0792 |  13.7% |
| 3 |   -0.5064 |  +0.0873 |  15.1% |

_Δ > 0 = agent contributes; share is normalized contribution._

## A3 — Failure Forensics

- n_episodes: 50 (errors: 0)
- max_df overall p50/p95/max: 0.2194 / 0.3289 / 0.4308
- n over 0.4 Hz threshold: 1
- worst-K most-common bus: **PQ_Bus14** (4 of 5)
- worstk magnitude median (pu): 1.800  (overall: 1.132)
- clustered_by_bus: True, clustered_by_sign: True

Worst K episodes:
| seed | max_df | dist_bus | dist_mag (pu) | sign | spread peak step | action L1 mean |
|---|---|---|---|---|---|---|
| 20036 | 0.4308 | PQ_Bus14 | +1.947 | +1 | 0 | 0.583 |
| 20023 | 0.3829 | PQ_Bus14 | +1.702 | +1 | 0 | 0.553 |
| 20031 | 0.3320 | PQ_Bus14 | +1.525 | +1 | 0 | 0.535 |
| 20041 | 0.3252 | PQ_1 | +1.802 | +1 | 4 | 0.536 |
| 20048 | 0.3233 | PQ_Bus14 | -1.800 | -1 | 1 | 0.569 |

