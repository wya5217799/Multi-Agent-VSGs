# Agent State Probe Report

- timestamp: 2026-05-04T08:00:19
- schema_version: 1
- implementation_version: 0.1.0
- ckpt_dir: `results/andes_phase4_noPHIabs_seed45`
- ckpt_kind: final

## Verdicts (A1-A3)

| Gate | Verdict | Reason codes |
|---|---|---|
| A1 | PASS | A1_SPECIALIZED |
| A2 | REJECT | A2_FREERIDER_DETECTED |
| A3 | REJECT | A3_CLUSTERED_SIGN, A3_HIGH_MAGNITUDE_FAILURES |

## A1 — Specialization

- offdiag cosine mean: **0.1426** (max 0.5164, min -0.2524)
- n_obs samples: 200

Pairwise cosine matrix:
```
  +1.000  -0.252  -0.092  -0.121
  -0.252  +1.000  +0.478  +0.327
  -0.092  +0.478  +1.000  +0.516
  -0.121  +0.327  +0.516  +1.000
```

Per-agent action stats (synthetic obs):
| agent | a0 (ΔM) μ | a0 σ | a1 (ΔD) μ | a1 σ |
|---|---|---|---|---|
| 0 | -0.153 | 0.595 | -0.091 | 0.662 |
| 1 | +0.498 | 0.524 | +0.740 | 0.448 |
| 2 | +0.075 | 0.629 | +0.881 | 0.214 |
| 3 | +0.166 | 0.531 | +0.488 | 0.726 |

## A2 — Ablation

- baseline cum_rf: **-0.5547** (20 eps)

| agent | ablated cum_rf | Δ cum_rf | share |
|---|---|---|---|
| 0 |   -0.5515 |  -0.0032 |   0.6% |
| 1 |   -0.9413 |  +0.3865 |  66.4% |
| 2 |   -0.6351 |  +0.0803 |  13.8% |
| 3 |   -0.6668 |  +0.1120 |  19.2% |

_Δ > 0 = agent contributes; share is normalized contribution._

## A3 — Failure Forensics

- n_episodes: 50 (errors: 0)
- max_df overall p50/p95/max: 0.2253 / 0.3687 / 0.3893
- n over 0.4 Hz threshold: 0
- worst-K most-common bus: **PQ_1** (2 of 5)
- worstk magnitude median (pu): 1.800  (overall: 1.132)
- clustered_by_bus: False, clustered_by_sign: True

Worst K episodes:
| seed | max_df | dist_bus | dist_mag (pu) | sign | spread peak step | action L1 mean |
|---|---|---|---|---|---|---|
| 20041 | 0.3893 | PQ_1 | +1.802 | +1 | 2 | 0.466 |
| 20048 | 0.3746 | PQ_Bus14 | -1.800 | -1 | 2 | 0.522 |
| 20000 | 0.3702 | PQ_Bus15 | +1.853 | +1 | 1 | 0.509 |
| 20013 | 0.3669 | PQ_1 | +1.695 | +1 | 3 | 0.510 |
| 20023 | 0.3636 | PQ_Bus14 | +1.702 | +1 | 0 | 0.473 |

