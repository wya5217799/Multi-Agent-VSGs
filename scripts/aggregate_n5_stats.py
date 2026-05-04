"""
Aggregate n=5 DDIC statistics for Tier A predraft update.

Usage (run after seeds 45+46 evals complete):
    wsl bash -c "source ~/andes_venv/bin/activate && \\
        cd '/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs' && \\
        python3 scripts/aggregate_n5_stats.py"

Reads:
    results/andes_eval_paper_grade/per_seed_summary.json  (seeds 42-44)
    results/andes_eval_paper_grade/ddic_seed45_final.json
    results/andes_eval_paper_grade/ddic_seed46_final.json

Writes:
    results/andes_eval_paper_grade/n5_aggregate.json
    results/andes_eval_paper_grade/n5_summary.md

Also prints gate decision (Gate A1/A2/A3 from spec §8).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

SEEDS = [42, 43, 44, 45, 46]
# t(4, 0.025) = 2.776
T_STAT_4DF = 2.776
ADAPTIVE_CUM_RF = -1.060        # best adaptive cum_rf_total from per_seed_summary.json
ADAPTIVE_CUM_RF_PER_EP = -1.060 / 50.0  # per-episode value


def _bootstrap_ci_simple(vals: list[float], n_resample: int = 1000, alpha: float = 0.05,
                          seed: int = 7919) -> dict:
    rng = np.random.default_rng(seed)
    arr = np.array(vals)
    means = [np.mean(rng.choice(arr, size=len(arr), replace=True)) for _ in range(n_resample)]
    lo = float(np.percentile(means, 100 * alpha / 2))
    hi = float(np.percentile(means, 100 * (1 - alpha / 2)))
    return {"mean": float(np.mean(arr)), "std": float(np.std(arr, ddof=1)),
            "ci_lo": lo, "ci_hi": hi, "n": len(arr), "n_resample": n_resample, "alpha": alpha}


def load_per_seed_summary(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def extract_seed_cum_rf_total(per_seed_data: dict, seed: int) -> float:
    """Extract cum_rf_total for a given ddic seed from per_seed_summary.json."""
    key = f"ddic_phase4_seed{seed}_final"
    return per_seed_data["controllers"][key]["cum_rf_total"]


def extract_seed_cum_rf_total_from_file(path: Path) -> float:
    """Extract cum_rf_total from a single-seed eval JSON."""
    with open(path) as f:
        data = json.load(f)
    return data["summary"]["cum_rf_total"]


def extract_seed_metrics(per_seed_data: dict, seed: int) -> dict:
    key = f"ddic_phase4_seed{seed}_final"
    ctrl = per_seed_data["controllers"][key]
    return {
        "cum_rf_total": ctrl["cum_rf_total"],
        "cum_rf_per_ep": ctrl["cum_rf_total"] / ctrl["n_scenarios"],
        "max_df_mean": ctrl["max_df_hz"]["mean"],
        "rocof_mean": ctrl["rocof_max"]["mean"],
        "n_scenarios": ctrl["n_scenarios"],
    }


def extract_seed_metrics_from_file(path: Path, n_test_eps: int = 50) -> dict:
    with open(path) as f:
        data = json.load(f)
    s = data["summary"]
    return {
        "cum_rf_total": s["cum_rf_total"],
        "cum_rf_per_ep": s["cum_rf_total"] / data["n_test_eps"],
        "max_df_mean": s["max_df_hz"]["mean"],
        "rocof_mean": s["rocof_max"]["mean"],
        "n_scenarios": data["n_test_eps"],
    }


def t_ci_half_width(vals: list[float]) -> float:
    n = len(vals)
    std = float(np.std(vals, ddof=1))
    return T_STAT_4DF * std / math.sqrt(n)


def main() -> int:
    per_seed_path = ROOT / "results/andes_eval_paper_grade/per_seed_summary.json"
    if not per_seed_path.exists():
        print(f"ERROR: {per_seed_path} not found", file=sys.stderr)
        return 1

    per_seed_data = load_per_seed_summary(per_seed_path)

    metrics_per_seed: dict[int, dict] = {}

    # Seeds 42-44 from per_seed_summary
    for s in [42, 43, 44]:
        metrics_per_seed[s] = extract_seed_metrics(per_seed_data, s)

    # Seeds 45-46 from individual files
    for s in [45, 46]:
        p = ROOT / f"results/andes_eval_paper_grade/ddic_seed{s}_final.json"
        if not p.exists():
            print(f"ERROR: {p} not found. Has seed {s} eval run yet?", file=sys.stderr)
            return 1
        metrics_per_seed[s] = extract_seed_metrics_from_file(p)

    # Aggregate across n=5
    cum_rf_totals = [metrics_per_seed[s]["cum_rf_total"] for s in SEEDS]
    cum_rf_per_ep = [metrics_per_seed[s]["cum_rf_per_ep"] for s in SEEDS]
    max_df_means = [metrics_per_seed[s]["max_df_mean"] for s in SEEDS]

    n5_mean = float(np.mean(cum_rf_totals))
    n5_std = float(np.std(cum_rf_totals, ddof=1))
    n5_hw = t_ci_half_width(cum_rf_totals)
    n5_ci_lo = n5_mean - n5_hw
    n5_ci_hi = n5_mean + n5_hw

    boot_ci = _bootstrap_ci_simple(cum_rf_totals)
    max_df_ci = _bootstrap_ci_simple(max_df_means)

    # Gate logic from spec §8
    # adaptive cum_rf_total = -1.060 (50 ep run = raw total)
    best_adaptive_total = ADAPTIVE_CUM_RF
    gate = None
    if best_adaptive_total < n5_ci_lo or best_adaptive_total > n5_ci_hi:
        gate = "A1"  # CI does not contain adaptive -> claim DDIC > adaptive defensible
    elif n5_std > 0.25:
        gate = "A3"  # std grows materially
    else:
        gate = "A2"  # CI still contains adaptive, std normal -> ambiguous -> Tier B

    result = {
        "n": len(SEEDS),
        "seeds": SEEDS,
        "per_seed_cum_rf_total": {str(s): float(metrics_per_seed[s]["cum_rf_total"]) for s in SEEDS},
        "per_seed_max_df_mean": {str(s): float(metrics_per_seed[s]["max_df_mean"]) for s in SEEDS},
        "n5_cum_rf_total": {
            "mean": n5_mean,
            "std": n5_std,
            "t_ci_half_width": n5_hw,
            "t_ci_lo": n5_ci_lo,
            "t_ci_hi": n5_ci_hi,
            "t_df": 4,
            "t_alpha": 0.05,
        },
        "n5_cum_rf_bootstrap": boot_ci,
        "n5_max_df_bootstrap": max_df_ci,
        "best_adaptive_cum_rf_total": best_adaptive_total,
        "gate_decision": gate,
        "gate_logic": {
            "A1": "CI does not contain best adaptive -> DDIC vs adaptive claim defensible -> stop",
            "A2": "CI contains best adaptive, std normal -> ambiguous -> proceed to Tier B",
            "A3": "std > 0.25 -> high dispersion -> proceed to Tier B; flag in risk log",
        },
    }

    out_dir = ROOT / "results/andes_eval_paper_grade"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "n5_aggregate.json"
    with open(json_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Wrote: {json_path}")

    # Per-ep values for predraft (divide by 50 episodes)
    n5_mean_per_ep = n5_mean / 50.0
    n5_ci_lo_per_ep = n5_ci_lo / 50.0
    n5_ci_hi_per_ep = n5_ci_hi / 50.0

    md = f"""# n=5 DDIC Aggregate Statistics (Tier A)

**Generated**: from seeds {SEEDS}

## Per-Seed cum_rf_total (50 episodes each)

| Seed | cum_rf_total |
|------|-------------|
"""
    for s in SEEDS:
        md += f"| {s} | {metrics_per_seed[s]['cum_rf_total']:.4f} |\n"

    md += f"""
## n=5 Aggregate (cum_rf_total across 50 test episodes per seed)

| Statistic | Value |
|-----------|-------|
| n | {len(SEEDS)} |
| Mean | {n5_mean:.4f} |
| Std (sample) | {n5_std:.4f} |
| t-CI 95% [t(4,0.025)={T_STAT_4DF}] | [{n5_ci_lo:.4f}, {n5_ci_hi:.4f}] |
| t-CI half-width | {n5_hw:.4f} |
| Bootstrap 95% CI | [{boot_ci['ci_lo']:.4f}, {boot_ci['ci_hi']:.4f}] |
| Best adaptive cum_rf_total | {best_adaptive_total:.4f} |

## Per-episode values (divide by 50)

| Statistic | Value |
|-----------|-------|
| Mean per-ep | {n5_mean_per_ep:.6f} |
| t-CI per-ep | [{n5_ci_lo_per_ep:.6f}, {n5_ci_hi_per_ep:.6f}] |

## max_df mean across seeds (n=5 bootstrap)

| Statistic | Value |
|-----------|-------|
| Mean | {max_df_ci['mean']:.4f} Hz |
| Bootstrap 95% CI | [{max_df_ci['ci_lo']:.4f}, {max_df_ci['ci_hi']:.4f}] Hz |

## Gate Decision (spec §8)

**Gate: {gate}**

- Gate A1 (CI excludes adaptive → defensible claim): best_adaptive={best_adaptive_total:.4f} in CI=[{n5_ci_lo:.4f},{n5_ci_hi:.4f}]? {"NO (not in CI) -> A1 fires" if gate == "A1" else "YES (in CI)"}
- Gate A2 (ambiguous, Tier B): std={n5_std:.4f} {'< 0.25' if n5_std < 0.25 else '>= 0.25'}
- Gate A3 (high dispersion, Tier B): std={n5_std:.4f} {'> 0.25 -> fires' if n5_std > 0.25 else '<= 0.25'}

**Decision**: {result['gate_logic'][gate]}
"""

    md_path = out_dir / "n5_summary.md"
    with open(md_path, "w") as f:
        f.write(md)
    print(f"Wrote: {md_path}")

    # Print summary
    print()
    print("=" * 60)
    print(f"n=5 DDIC cum_rf_total: mean={n5_mean:.4f}, std={n5_std:.4f}")
    print(f"  95% t-CI: [{n5_ci_lo:.4f}, {n5_ci_hi:.4f}]  (half-width={n5_hw:.4f})")
    print(f"  Bootstrap CI: [{boot_ci['ci_lo']:.4f}, {boot_ci['ci_hi']:.4f}]")
    print(f"  Best adaptive: {best_adaptive_total:.4f}")
    print(f"GATE: {gate} -> {result['gate_logic'][gate]}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
