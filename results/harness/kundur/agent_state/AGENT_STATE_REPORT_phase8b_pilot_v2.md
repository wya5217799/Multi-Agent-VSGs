# Agent State Probe Report

- timestamp: 2026-05-04T02:13:21
- schema_version: 1
- implementation_version: 0.1.0
- ckpt_dir: `results/andes_phase8b_ownact_seed42`
- ckpt_kind: final

## Verdicts (A1-A3)

| Gate | Verdict | Reason codes |
|---|---|---|
| A1 | PASS | A1_SPECIALIZED |
| A2 | REJECT | A2_FREERIDER_DETECTED |
| A3 | REJECT | A3_CLUSTERED_SIGN, A3_HIGH_MAGNITUDE_FAILURES |

## A1 — Specialization

- offdiag cosine mean: **0.2297** (max 0.6997, min -0.1790)
- n_obs samples: 200

Pairwise cosine matrix:
```
  +1.000  -0.179  +0.139  +0.004
  -0.179  +1.000  +0.506  +0.700
  +0.139  +0.506  +1.000  +0.208
  +0.004  +0.700  +0.208  +1.000
```

Per-agent action stats (synthetic obs):
| agent | a0 (ΔM) μ | a0 σ | a1 (ΔD) μ | a1 σ |
|---|---|---|---|---|
| 0 | -0.200 | 0.249 | -0.111 | 0.339 |
| 1 | -0.257 | 0.162 | +0.523 | 0.331 |
| 2 | -0.244 | 0.210 | +0.243 | 0.253 |
| 3 | -0.141 | 0.231 | +0.200 | 0.232 |

## A2 — Ablation

- baseline cum_rf: **-0.8013** (20 eps)

| agent | ablated cum_rf | Δ cum_rf | share |
|---|---|---|---|
| 0 |   -0.8016 |  +0.0003 |   0.1% |
| 1 |   -1.0724 |  +0.2711 |  73.3% |
| 2 |   -0.8220 |  +0.0208 |   5.6% |
| 3 |   -0.8787 |  +0.0775 |  21.0% |

_Δ > 0 = agent contributes; share is normalized contribution._

## A3 — Failure Forensics

- n_episodes: 50 (errors: 0)
- max_df overall p50/p95/max: 0.2519 / 0.3924 / 0.4964
- n over 0.4 Hz threshold: 2
- worst-K most-common bus: **PQ_Bus14** (2 of 5)
- worstk magnitude median (pu): 1.802  (overall: 1.132)
- clustered_by_bus: False, clustered_by_sign: True

Worst K episodes:
| seed | max_df | dist_bus | dist_mag (pu) | sign | spread peak step | action L1 mean |
|---|---|---|---|---|---|---|
| 20000 | 0.4964 | PQ_Bus15 | +1.853 | +1 | 2 | 0.463 |
| 20036 | 0.4186 | PQ_Bus14 | +1.947 | +1 | 0 | 0.451 |
| 20015 | 0.3936 | PQ_0 | +1.743 | +1 | 3 | 0.408 |
| 20041 | 0.3910 | PQ_1 | +1.802 | +1 | 5 | 0.433 |
| 20023 | 0.3820 | PQ_Bus14 | +1.702 | +1 | 0 | 0.425 |

