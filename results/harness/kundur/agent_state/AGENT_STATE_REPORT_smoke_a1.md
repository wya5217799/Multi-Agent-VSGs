# Agent State Probe Report

- timestamp: 2026-05-03T18:18:24
- schema_version: 1
- implementation_version: 0.1.0
- ckpt_dir: `results/andes_phase4_noPHIabs_seed42`
- ckpt_kind: final

## Verdicts (A1-A3)

| Gate | Verdict | Reason codes |
|---|---|---|
| A1 | PASS | A1_SPECIALIZED |
| A2 | ERROR | A2_PHASE_NOT_RUN |
| A3 | ERROR | A3_PHASE_NOT_RUN |

## A1 — Specialization

- offdiag cosine mean: **0.3521** (max 0.5909, min 0.1604)
- n_obs samples: 200

Pairwise cosine matrix:
```
  +1.000  +0.305  +0.465  +0.160
  +0.305  +1.000  +0.591  +0.295
  +0.465  +0.591  +1.000  +0.296
  +0.160  +0.295  +0.296  +1.000
```

Per-agent action stats (synthetic obs):
| agent | a0 (ΔM) μ | a0 σ | a1 (ΔD) μ | a1 σ |
|---|---|---|---|---|
| 0 | -0.293 | 0.443 | +0.509 | 0.528 |
| 1 | +0.292 | 0.631 | +0.811 | 0.495 |
| 2 | +0.008 | 0.358 | +0.697 | 0.483 |
| 3 | +0.224 | 0.707 | +0.418 | 0.551 |

