# Agent State Probe Report

- timestamp: 2026-05-04T13:07:00
- schema_version: 1
- implementation_version: 0.1.0
- ckpt_dir: `results/andes_warmstart_seed44`
- ckpt_kind: final

## Verdicts (A1-A3)

| Gate | Verdict | Reason codes |
|---|---|---|
| A1 | PASS | A1_SPECIALIZED |
| A2 | ERROR | A2_PHASE_NOT_RUN |
| A3 | REJECT | A3_CLUSTERED_SIGN, A3_HIGH_MAGNITUDE_FAILURES |

## A1 — Specialization

- offdiag cosine mean: **-0.0893** (max 0.0987, min -0.4738)
- n_obs samples: 200

Pairwise cosine matrix:
```
  +1.000  -0.474  +0.011  -0.208
  -0.474  +1.000  -0.062  +0.099
  +0.011  -0.062  +1.000  +0.098
  -0.208  +0.099  +0.098  +1.000
```

Per-agent action stats (synthetic obs):
| agent | a0 (ΔM) μ | a0 σ | a1 (ΔD) μ | a1 σ |
|---|---|---|---|---|
| 0 | +0.202 | 0.297 | -0.374 | 0.654 |
| 1 | -0.288 | 0.353 | +0.777 | 0.253 |
| 2 | +0.495 | 0.355 | +0.126 | 0.536 |
| 3 | +0.074 | 0.497 | -0.049 | 0.714 |

## A3 — Failure Forensics

- n_episodes: 50 (errors: 0)
- max_df overall p50/p95/max: 0.2357 / 0.3794 / 0.4107
- n over 0.4 Hz threshold: 2
- worst-K most-common bus: **PQ_Bus14** (2 of 5)
- worstk magnitude median (pu): 1.802  (overall: 1.132)
- clustered_by_bus: False, clustered_by_sign: True

Worst K episodes:
| seed | max_df | dist_bus | dist_mag (pu) | sign | spread peak step | action L1 mean |
|---|---|---|---|---|---|---|
| 20036 | 0.4107 | PQ_Bus14 | +1.947 | +1 | 0 | 0.765 |
| 20013 | 0.4078 | PQ_1 | +1.695 | +1 | 3 | 0.618 |
| 20000 | 0.3823 | PQ_Bus15 | +1.853 | +1 | 1 | 0.655 |
| 20041 | 0.3758 | PQ_1 | +1.802 | +1 | 2 | 0.635 |
| 20023 | 0.3652 | PQ_Bus14 | +1.702 | +1 | 0 | 0.707 |

