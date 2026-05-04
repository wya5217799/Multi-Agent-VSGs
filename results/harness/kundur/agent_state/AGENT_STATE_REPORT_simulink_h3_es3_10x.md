# Agent State Probe Report

- timestamp: 2026-05-04T05:29:51
- schema_version: 1
- implementation_version: 0.1.0
- ckpt_dir: `results/sim_kundur/runs/screen_h3_es3_10x_20260503T124521/checkpoints`
- ckpt_kind: best

## Verdicts (A1-A3)

| Gate | Verdict | Reason codes |
|---|---|---|
| A1 | PASS | A1_SPECIALIZED |
| A2 | ERROR | A2_PHASE_NOT_RUN |
| A3 | ERROR | A3_PHASE_NOT_RUN |

## A1 ¡ª Specialization

- offdiag cosine mean: **-0.0822** (max 0.3883, min -0.5676)
- n_obs samples: 200

Pairwise cosine matrix:
```
  +1.000  -0.275  +0.254  +0.118
  -0.275  +1.000  -0.410  -0.568
  +0.254  -0.410  +1.000  +0.388
  +0.118  -0.568  +0.388  +1.000
```

Per-agent action stats (synthetic obs):
| agent | a0 (¦¤M) ¦Ì | a0 ¦Ò | a1 (¦¤D) ¦Ì | a1 ¦Ò |
|---|---|---|---|---|
| 0 | +0.013 | 0.130 | +0.023 | 0.100 |
| 1 | +0.047 | 0.133 | -0.077 | 0.074 |
| 2 | -0.125 | 0.123 | -0.020 | 0.088 |
| 3 | -0.055 | 0.123 | +0.062 | 0.107 |

