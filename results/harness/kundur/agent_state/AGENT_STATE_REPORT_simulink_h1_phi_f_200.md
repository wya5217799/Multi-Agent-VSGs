# Agent State Probe Report

- timestamp: 2026-05-04T05:29:43
- schema_version: 1
- implementation_version: 0.1.0
- ckpt_dir: `results/sim_kundur/runs/screen_h1_phi_f_200_20260503T124521/checkpoints`
- ckpt_kind: best

## Verdicts (A1-A3)

| Gate | Verdict | Reason codes |
|---|---|---|
| A1 | PASS | A1_SPECIALIZED |
| A2 | ERROR | A2_PHASE_NOT_RUN |
| A3 | ERROR | A3_PHASE_NOT_RUN |

## A1 ¡ª Specialization

- offdiag cosine mean: **-0.0401** (max 0.3484, min -0.3351)
- n_obs samples: 200

Pairwise cosine matrix:
```
  +1.000  -0.308  -0.335  +0.277
  -0.308  +1.000  +0.348  -0.091
  -0.335  +0.348  +1.000  -0.131
  +0.277  -0.091  -0.131  +1.000
```

Per-agent action stats (synthetic obs):
| agent | a0 (¦¤M) ¦Ì | a0 ¦Ò | a1 (¦¤D) ¦Ì | a1 ¦Ò |
|---|---|---|---|---|
| 0 | -0.001 | 0.092 | +0.017 | 0.086 |
| 1 | +0.013 | 0.149 | +0.002 | 0.104 |
| 2 | +0.008 | 0.198 | +0.016 | 0.087 |
| 3 | -0.061 | 0.107 | -0.044 | 0.108 |

