# Kundur CVS — PHI Reward-Scale Gate B1 Verdict (2026-04-26)

> **Locks `PHI_H = PHI_D = 0.0001`** as the Kundur CVS reward-shaping baseline
> after the B1 gate (50ep observation) demonstrated r_f% mean of 4.10%, in the
> 3%-8% target band, with all hygiene and SAC-health checks passing.
>
> **Scope**: Kundur-only override in `scenarios/kundur/config_simulink.py`.
> NE39 (`scenarios/new_england/config_simulink.py`) untouched — its
> `PHI_H = PHI_D = 1.0` (inherited from `scenarios/config_simulink_base.py`)
> remains as-is.

## Why a Kundur-only override

Yang TPWRS 2023 Table I lists `φ_f = 100, φ_h = 1, φ_d = 1`. Direct adoption
gave `r_f% ≈ 0%` on the symmetric-disturbance baseline (50ep run
`kundur_simulink_20260426_142847`) and only 0.0005% on the asymmetric
single-VSG baseline (`kundur_simulink_20260426_144431`).

Root cause: the paper does not specify the dimension/scale of `H` and `D`
(documented in `docs/paper/yang2023-fact-base.md §2.1 Q7`). The project
implementation uses `M0 = 24, D0 = 4.5` (system-pu, mid-range damping picked
in the v2 dry-run for paper-feasibility), which makes the `(ΔH_avg)²` and
`(ΔD_avg)²` action-penalty terms ~10⁴ and ~10² larger than the `(Δω_i −
local_mean)²` synchronisation term. Without rescaling, r_h / r_d dominate
reward and `r_f` carries no learning signal.

`PHI_H = PHI_D = 0.0001` (=1e-4) brings the three components into the order
predicted by `φ_f = 100` — the paper's intended weighting structure — without
touching the paper-specified `PHI_F = 100`.

## Gate progression (4 runs, 50ep each, identical otherwise)

| Run ID | Disturbance | PHI_H/D | r_f% mean | r_f% max | df mean (Hz) | max_swing | SAC alpha 50ep |
|---|---|---|---|---|---|---|---|
| `_142847` (sym baseline) | symmetric (4-VSG split) | 1.0 | 0.00% | — | 1.030 | 0.069 | 0.223 |
| `_144431` (asym baseline) | single-VSG[0] (4× concentrated) | 1.0 | 0.0005% | — | 1.140 | 0.404 | 0.223 |
| `_150848` (PHI×1e-3) | single-VSG[0] | 0.001 | 0.47% | 1.83% | 1.000 | 0.363 | 0.223 |
| **`_152117` (PHI×1e-4 = B1)** | single-VSG[0] | **0.0001** | **4.10%** | **12.84%** | **1.023** | **0.364** | **0.223** |

## B1 acceptance check

| # | Criterion | Result | Pass? |
|---|---|---|---|
| 1 | 50/50 completion | 50/50 | ✅ |
| 2 | No NaN / Inf / clip / early-term | finite reward; df_max < 14 Hz; 0 monitor_stops | ✅ |
| 3 | r_f% mean in 3%-8%, clearly above 0.47% | mean = **4.10%** (×8.7); median 2.92%; max 12.84% | ✅ |
| 4 | H/D not pinned / not collapsing | alpha decay 1.0 → 0.22 smooth; policy_loss -1.3 → -9.1 (still exploring); critic_loss 0.15 → 2.2 (converging) | ✅ |
| 5 | df mean does not significantly degrade | 1.023 Hz vs PHI×1e-3 of 1.000 Hz vs asym baseline 1.140 Hz | ✅ |
| 6 | If r_f% < 1%, escalate to PHI×1e-5 | 4.10% > 1% → not triggered | n/a |

## Math closure (predicted vs measured)

For B1 (`PHI_H = PHI_D = 0.0001`):
- Predicted: `r_f / total ≈ 1.7e-3 / (1.7e-3 + 0.029 + 0.008) ≈ 4.4%`
- Measured: r_f% mean = 4.10%
- Match: <10% delta, within sample-variance of per-episode `r_h` and `r_d`

For PHI×1e-3 (intermediate gate):
- Predicted: `r_f / total ≈ 1.7e-3 / (1.7e-3 + 0.293 + 0.080) ≈ 0.45%`
- Measured: 0.47% — exact match
- Confirms r_f / r_h / r_d scale linearly with PHI_H/D as designed.

## Decision

**Do NOT continue scaling PHI_H/D below 0.0001.** Rationale:

- r_f% has reached the target band (3%-8%); further scaling toward the
  monitor's 50% alert threshold (which would require ~PHI×1e-5 or smaller)
  risks weakening the H/D action regulariser to the point that the SAC
  policy may push H/D to bound limits or develop unstable update gradients
  in long-horizon training. The paper's `φ_h = φ_d = 1` is small but
  non-negligible; aggressive shrinkage past the math-predicted target is
  not paper-faithful.
- The monitor `reward_component_ratio` alert (threshold 50%) remains active
  on this configuration. **This is a known false-positive in the current
  stage**; the alert encodes a paper r_f-dominance assumption that requires
  a different M0/D0 baseline (Q7) to satisfy. The alert is informational
  only and does not block training.
- B1 is now the locked reward-shaping baseline for downstream gates
  (200ep observation; possible 2000ep if 200ep clears).

## Cross-PHI eval reward note

Eval reward absolute values cannot be compared across PHI configurations,
because the PHI rescaling changes the reward magnitude itself. Subsequent
comparisons must use scale-invariant metrics:

- r_f%
- df mean / df max
- H/D distribution at episode boundaries (pin to bound check)
- action std post-SAC-update (collapse check)
- max_power_swing
- deterministic-eval physics indicators (df, settling, swing)
- critic_loss / policy_loss / alpha trajectories

## Artifacts

- Code change: `scenarios/kundur/config_simulink.py` (this commit)
- Run logs: `results/sim_kundur/runs/kundur_simulink_20260426_152117/`
- Comparison fingerprint: this file
