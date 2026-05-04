# Agent State Probe Report

- timestamp: 2026-05-04T05:29:47
- schema_version: 1
- implementation_version: 0.1.0
- ckpt_dir: `results/sim_kundur/runs/screen_h2_es3_4x_20260503T124521/checkpoints`
- ckpt_kind: best

## Verdicts (A1-A3)

| Gate | Verdict | Reason codes |
|---|---|---|
| A1 | PASS | A1_SPECIALIZED |
| A2 | ERROR | A2_PHASE_NOT_RUN |
| A3 | ERROR | A3_PHASE_NOT_RUN |

## A1 ¡ª Specialization

- offdiag cosine mean: **0.1451** (max 0.5408, min -0.2475)
- n_obs samples: 200

Pairwise cosine matrix:
```
  +1.000  -0.096  -0.247  +0.045
  -0.096  +1.000  +0.250  +0.541
  -0.247  +0.250  +1.000  +0.379
  +0.045  +0.541  +0.379  +1.000
```

Per-agent action stats (synthetic obs):
| agent | a0 (¦¤M) ¦Ì | a0 ¦Ò | a1 (¦¤D) ¦Ì | a1 ¦Ò |
|---|---|---|---|---|
| 0 | +0.031 | 0.079 | -0.035 | 0.058 |
| 1 | -0.026 | 0.077 | +0.005 | 0.044 |
| 2 | -0.025 | 0.149 | +0.025 | 0.115 |
| 3 | -0.014 | 0.086 | -0.013 | 0.054 |

