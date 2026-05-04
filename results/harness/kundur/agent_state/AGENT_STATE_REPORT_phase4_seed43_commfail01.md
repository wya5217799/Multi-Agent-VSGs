# Agent State Probe Report

- timestamp: 2026-05-04T13:30:58
- schema_version: 1
- implementation_version: 0.1.0
- ckpt_dir: `results/andes_phase4_noPHIabs_seed43`
- ckpt_kind: final

## Verdicts (A1-A3)

| Gate | Verdict | Reason codes |
|---|---|---|
| A1 | PASS | A1_SPECIALIZED |
| A2 | PENDING | A2_IMBALANCED_CONTRIBUTION |
| A3 | REJECT | A3_CLUSTERED_BUS, A3_HIGH_MAGNITUDE_FAILURES |

## A1 — Specialization

- offdiag cosine mean: **0.3183** (max 0.5485, min 0.1224)
- n_obs samples: 200

Pairwise cosine matrix:
```
  +1.000  +0.122  +0.267  +0.199
  +0.122  +1.000  +0.286  +0.549
  +0.267  +0.286  +1.000  +0.487
  +0.199  +0.549  +0.487  +1.000
```

Per-agent action stats (synthetic obs):
| agent | a0 (ΔM) μ | a0 σ | a1 (ΔD) μ | a1 σ |
|---|---|---|---|---|
| 0 | +0.236 | 0.418 | +0.283 | 0.752 |
| 1 | +0.349 | 0.539 | +0.407 | 0.654 |
| 2 | +0.281 | 0.470 | +0.698 | 0.455 |
| 3 | +0.219 | 0.419 | +0.734 | 0.485 |

## A2 — Ablation

- baseline cum_rf: **-0.4770** (20 eps)

| agent | ablated cum_rf | Δ cum_rf | share |
|---|---|---|---|
| 0 |   -0.5115 |  +0.0345 |   5.1% |
| 1 |   -0.8456 |  +0.3686 |  54.6% |
| 2 |   -0.5773 |  +0.1003 |  14.9% |
| 3 |   -0.6481 |  +0.1711 |  25.4% |

_Δ > 0 = agent contributes; share is normalized contribution._

## A3 — Failure Forensics

- n_episodes: 50 (errors: 0)
- max_df overall p50/p95/max: 0.2218 / 0.3673 / 0.4234
- n over 0.4 Hz threshold: 2
- worst-K most-common bus: **PQ_Bus14** (4 of 5)
- worstk magnitude median (pu): 1.800  (overall: 1.132)
- clustered_by_bus: True, clustered_by_sign: False

Worst K episodes:
| seed | max_df | dist_bus | dist_mag (pu) | sign | spread peak step | action L1 mean |
|---|---|---|---|---|---|---|
| 20048 | 0.4234 | PQ_Bus14 | -1.800 | -1 | 2 | 0.687 |
| 20001 | 0.4082 | PQ_Bus14 | -1.692 | -1 | 2 | 0.681 |
| 20036 | 0.3900 | PQ_Bus14 | +1.947 | +1 | 0 | 0.573 |
| 20000 | 0.3396 | PQ_Bus15 | +1.853 | +1 | 1 | 0.567 |
| 20023 | 0.3340 | PQ_Bus14 | +1.702 | +1 | 0 | 0.577 |

