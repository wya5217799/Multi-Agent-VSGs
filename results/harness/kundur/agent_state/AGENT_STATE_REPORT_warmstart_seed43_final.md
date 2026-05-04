# Agent State Probe Report

- timestamp: 2026-05-04T13:07:00
- schema_version: 1
- implementation_version: 0.1.0
- ckpt_dir: `results/andes_warmstart_seed43`
- ckpt_kind: final

## Verdicts (A1-A3)

| Gate | Verdict | Reason codes |
|---|---|---|
| A1 | PASS | A1_SPECIALIZED |
| A2 | ERROR | A2_PHASE_NOT_RUN |
| A3 | REJECT | A3_CLUSTERED_BUS, A3_HIGH_MAGNITUDE_FAILURES |

## A1 — Specialization

- offdiag cosine mean: **0.4467** (max 0.6157, min 0.1939)
- n_obs samples: 200

Pairwise cosine matrix:
```
  +1.000  +0.581  +0.194  +0.492
  +0.581  +1.000  +0.324  +0.616
  +0.194  +0.324  +1.000  +0.473
  +0.492  +0.616  +0.473  +1.000
```

Per-agent action stats (synthetic obs):
| agent | a0 (ΔM) μ | a0 σ | a1 (ΔD) μ | a1 σ |
|---|---|---|---|---|
| 0 | +0.068 | 0.346 | +0.347 | 0.450 |
| 1 | -0.039 | 0.365 | +0.688 | 0.297 |
| 2 | +0.318 | 0.468 | +0.473 | 0.568 |
| 3 | +0.240 | 0.439 | +0.694 | 0.395 |

## A3 — Failure Forensics

- n_episodes: 50 (errors: 0)
- max_df overall p50/p95/max: 0.2315 / 0.3696 / 0.4020
- n over 0.4 Hz threshold: 1
- worst-K most-common bus: **PQ_Bus14** (5 of 5)
- worstk magnitude median (pu): 1.702  (overall: 1.132)
- clustered_by_bus: True, clustered_by_sign: False

Worst K episodes:
| seed | max_df | dist_bus | dist_mag (pu) | sign | spread peak step | action L1 mean |
|---|---|---|---|---|---|---|
| 20048 | 0.4020 | PQ_Bus14 | -1.800 | -1 | 2 | 0.555 |
| 20023 | 0.3760 | PQ_Bus14 | +1.702 | +1 | 0 | 0.523 |
| 20001 | 0.3736 | PQ_Bus14 | -1.692 | -1 | 2 | 0.551 |
| 20031 | 0.3647 | PQ_Bus14 | +1.525 | +1 | 2 | 0.517 |
| 20036 | 0.3641 | PQ_Bus14 | +1.947 | +1 | 0 | 0.570 |

