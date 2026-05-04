# Agent State Probe Report

- timestamp: 2026-05-04T02:11:03
- schema_version: 1
- implementation_version: 0.1.0
- ckpt_dir: `results/andes_phase8a_dt01_seed42`
- ckpt_kind: final

## Verdicts (A1-A3)

| Gate | Verdict | Reason codes |
|---|---|---|
| A1 | PASS | A1_SPECIALIZED |
| A2 | REJECT | A2_FREERIDER_DETECTED |
| A3 | REJECT | A3_CLUSTERED_SIGN, A3_HIGH_MAGNITUDE_FAILURES |

## A1 — Specialization

- offdiag cosine mean: **0.2877** (max 0.3560, min 0.1188)
- n_obs samples: 200

Pairwise cosine matrix:
```
  +1.000  +0.303  +0.356  +0.321
  +0.303  +1.000  +0.327  +0.301
  +0.356  +0.327  +1.000  +0.119
  +0.321  +0.301  +0.119  +1.000
```

Per-agent action stats (synthetic obs):
| agent | a0 (ΔM) μ | a0 σ | a1 (ΔD) μ | a1 σ |
|---|---|---|---|---|
| 0 | -0.403 | 0.207 | +0.420 | 0.276 |
| 1 | -0.216 | 0.140 | +0.156 | 0.433 |
| 2 | -0.000 | 0.242 | +0.153 | 0.305 |
| 3 | -0.081 | 0.256 | +0.137 | 0.263 |

## A2 — Ablation

- baseline cum_rf: **-2.0509** (20 eps)

| agent | ablated cum_rf | Δ cum_rf | share |
|---|---|---|---|
| 0 |   -2.0510 |  +0.0001 |   0.0% |
| 1 |   -2.5758 |  +0.5248 |  29.4% |
| 2 |   -1.9714 |  -0.0796 |   4.5% |
| 3 |   -3.2325 |  +1.1816 |  66.2% |

_Δ > 0 = agent contributes; share is normalized contribution._

## A3 — Failure Forensics

- n_episodes: 50 (errors: 0)
- max_df overall p50/p95/max: 0.2946 / 0.4520 / 0.4973
- n over 0.4 Hz threshold: 10
- worst-K most-common bus: **PQ_Bus14** (3 of 5)
- worstk magnitude median (pu): 1.702  (overall: 1.132)
- clustered_by_bus: False, clustered_by_sign: True

Worst K episodes:
| seed | max_df | dist_bus | dist_mag (pu) | sign | spread peak step | action L1 mean |
|---|---|---|---|---|---|---|
| 20036 | 0.4973 | PQ_Bus14 | +1.947 | +1 | 1 | 0.517 |
| 20023 | 0.4651 | PQ_Bus14 | +1.702 | +1 | 3 | 0.483 |
| 20041 | 0.4602 | PQ_1 | +1.802 | +1 | 6 | 0.497 |
| 20013 | 0.4420 | PQ_1 | +1.695 | +1 | 6 | 0.483 |
| 20031 | 0.4334 | PQ_Bus14 | +1.525 | +1 | 8 | 0.459 |

