# Agent State Probe Report

- timestamp: 2026-05-04T13:07:00
- schema_version: 1
- implementation_version: 0.1.0
- ckpt_dir: `results/andes_warmstart_seed42`
- ckpt_kind: final

## Verdicts (A1-A3)

| Gate | Verdict | Reason codes |
|---|---|---|
| A1 | PASS | A1_SPECIALIZED |
| A2 | ERROR | A2_PHASE_NOT_RUN |
| A3 | REJECT | A3_CLUSTERED_SIGN, A3_HIGH_MAGNITUDE_FAILURES |

## A1 — Specialization

- offdiag cosine mean: **0.3361** (max 0.5608, min -0.0386)
- n_obs samples: 200

Pairwise cosine matrix:
```
  +1.000  +0.561  +0.521  +0.283
  +0.561  +1.000  +0.371  -0.039
  +0.521  +0.371  +1.000  +0.319
  +0.283  -0.039  +0.319  +1.000
```

Per-agent action stats (synthetic obs):
| agent | a0 (ΔM) μ | a0 σ | a1 (ΔD) μ | a1 σ |
|---|---|---|---|---|
| 0 | -0.309 | 0.337 | +0.777 | 0.278 |
| 1 | -0.248 | 0.492 | +0.570 | 0.640 |
| 2 | +0.267 | 0.500 | +0.591 | 0.488 |
| 3 | +0.163 | 0.560 | +0.276 | 0.680 |

## A3 — Failure Forensics

- n_episodes: 50 (errors: 0)
- max_df overall p50/p95/max: 0.2319 / 0.3621 / 0.4018
- n over 0.4 Hz threshold: 1
- worst-K most-common bus: **PQ_Bus14** (2 of 5)
- worstk magnitude median (pu): 1.743  (overall: 1.132)
- clustered_by_bus: False, clustered_by_sign: True

Worst K episodes:
| seed | max_df | dist_bus | dist_mag (pu) | sign | spread peak step | action L1 mean |
|---|---|---|---|---|---|---|
| 20036 | 0.4018 | PQ_Bus14 | +1.947 | +1 | 0 | 0.545 |
| 20015 | 0.3783 | PQ_0 | +1.743 | +1 | 2 | 0.448 |
| 20023 | 0.3681 | PQ_Bus14 | +1.702 | +1 | 0 | 0.465 |
| 20013 | 0.3548 | PQ_1 | +1.695 | +1 | 5 | 0.483 |
| 20041 | 0.3509 | PQ_1 | +1.802 | +1 | 4 | 0.451 |

