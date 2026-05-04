# n=5 DDIC Aggregate Statistics (Tier A)

**Generated**: from seeds [42, 43, 44, 45, 46]

## Per-Seed cum_rf_total (50 episodes each)

| Seed | cum_rf_total |
|------|-------------|
| 42 | -1.1910 |
| 43 | -1.3641 |
| 44 | -0.9143 |
| 45 | -1.5234 |
| 46 | -0.9385 |

## n=5 Aggregate (cum_rf_total across 50 test episodes per seed)

| Statistic | Value |
|-----------|-------|
| n | 5 |
| Mean | -1.1863 |
| Std (sample) | 0.2649 |
| t-CI 95% [t(4,0.025)=2.776] | [-1.5151, -0.8574] |
| t-CI half-width | 0.3288 |
| Bootstrap 95% CI | [-1.3932, -0.9841] |
| Best adaptive cum_rf_total | -1.0600 |

## Per-episode values (divide by 50)

| Statistic | Value |
|-----------|-------|
| Mean per-ep | -0.023725 |
| t-CI per-ep | [-0.030302, -0.017148] |

## max_df mean across seeds (n=5 bootstrap)

| Statistic | Value |
|-----------|-------|
| Mean | 0.2384 Hz |
| Bootstrap 95% CI | [0.2351, 0.2418] Hz |

## Gate Decision (spec §8)

**Gate: A3**

- Gate A1 (CI excludes adaptive → defensible claim): best_adaptive=-1.0600 in CI=[-1.5151,-0.8574]? YES (in CI)
- Gate A2 (ambiguous, Tier B): std=0.2649 >= 0.25
- Gate A3 (high dispersion, Tier B): std=0.2649 > 0.25 -> fires

**Decision**: std > 0.25 -> high dispersion -> proceed to Tier B; flag in risk log
