# Agent State Probe Report

- timestamp: 2026-05-04T02:11:03
- schema_version: 1
- implementation_version: 0.1.0
- ckpt_dir: `results/andes_phase8b_ownact_seed42`
- ckpt_kind: final

## Verdicts (A1-A3)

| Gate | Verdict | Reason codes |
|---|---|---|
| A1 | PASS | A1_SPECIALIZED |
| A2 | ERROR | A2_PHASE_NOT_RUN |
| A3 | PASS | A3_SCATTERED_FAILURES |

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

## A3 — Failure Forensics

- n_episodes: 0 (errors: 50)
- max_df overall p50/p95/max: 0.0000 / 0.0000 / 0.0000
- n over 0.4 Hz threshold: 0
- worst-K most-common bus: **n/a** (0 of 0)
- worstk magnitude median (pu): 0.000  (overall: 0.000)
- clustered_by_bus: False, clustered_by_sign: False

Worst K episodes:
| seed | max_df | dist_bus | dist_mag (pu) | sign | spread peak step | action L1 mean |
|---|---|---|---|---|---|---|

## Errors

- phase_a2_ablation: mat1 and mat2 shapes cannot be multiplied (1x11 and 9x128)
