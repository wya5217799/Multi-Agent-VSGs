"""
Update predraft v2 to reflect n=5 DDIC statistics from Tier A.

Must run AFTER aggregate_n5_stats.py has produced:
    results/andes_eval_paper_grade/n5_aggregate.json

Creates:
    quality_reports/replications/2026-05-03_andes_ddic_honest_results_predraft_n5.md

Does NOT overwrite the v2 predraft (read-only).

Usage:
    python3 scripts/update_predraft_n5.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

T_STAT_4DF = 2.776  # t(4, 0.025)


def main() -> int:
    agg_path = ROOT / "results/andes_eval_paper_grade/n5_aggregate.json"
    if not agg_path.exists():
        print(f"ERROR: {agg_path} not found. Run aggregate_n5_stats.py first.", file=sys.stderr)
        return 1

    with open(agg_path) as f:
        agg = json.load(f)

    predraft_v2 = ROOT / "quality_reports/replications/2026-05-03_andes_ddic_honest_results_predraft_v2.md"
    if not predraft_v2.exists():
        print(f"ERROR: predraft v2 not found at {predraft_v2}", file=sys.stderr)
        return 1

    text = predraft_v2.read_text(encoding="utf-8")

    # Extract key n=5 numbers
    n5 = agg["n5_cum_rf_total"]
    mean = n5["mean"]
    std = n5["std"]
    ci_lo = n5["t_ci_lo"]
    ci_hi = n5["t_ci_hi"]
    hw = n5["t_ci_half_width"]
    gate = agg["gate_decision"]
    seeds = agg["seeds"]
    per_seed = agg["per_seed_cum_rf_total"]
    boot = agg["n5_cum_rf_bootstrap"]
    max_df = agg["n5_max_df_bootstrap"]
    adaptive = agg["best_adaptive_cum_rf_total"]

    n3_mean = np.mean([-1.1909695282887378, -1.3640972324672624, -0.9143441933596637])
    n3_std = np.std([-1.1909695282887378, -1.3640972324672624, -0.9143441933596637], ddof=1)
    n3_hw = 4.303 * n3_std / math.sqrt(3)
    n3_ci_lo = n3_mean - n3_hw
    n3_ci_hi = n3_mean + n3_hw

    # Formatted strings
    mean_s = f"{mean:.3f}"
    std_s = f"{std:.3f}"
    ci_s = f"[{ci_lo:.3f}, {ci_hi:.3f}]"
    boot_ci_s = f"[{boot['ci_lo']:.3f}, {boot['ci_hi']:.3f}]"
    max_df_s = f"{max_df['mean']:.3f} Hz [CI: {max_df['ci_lo']:.3f}, {max_df['ci_hi']:.3f}]"
    hw_s = f"{hw:.3f}"
    gate_s = gate

    # Per-seed table rows for new seeds
    seed_rows_new = ""
    for s in [45, 46]:
        seed_rows_new += f"| Phase 4 seed {s} _final_ | {per_seed[str(s)]:.4f} | — | — | — | 0.0 |\n"

    print("=" * 60)
    print("n=5 DDIC Statistics Summary")
    print("=" * 60)
    print(f"  Seeds: {seeds}")
    print(f"  Per-seed cum_rf_total: {[f'{per_seed[str(s)]:.4f}' for s in seeds]}")
    print(f"  Mean:    {mean:.4f}")
    print(f"  Std:     {std:.4f}")
    print(f"  t-CI:    {ci_s}  (half-width={hw_s})")
    print(f"  Boot CI: {boot_ci_s}")
    print(f"  max_df:  {max_df_s}")
    print(f"  Adaptive cum_rf_total: {adaptive:.4f}")
    print(f"  Gate:    {gate_s}")
    print()

    # n=3 stats for comparison
    print(f"  n=3 mean: {n3_mean:.4f}, std: {n3_std:.4f}, CI: [{n3_ci_lo:.3f}, {n3_ci_hi:.3f}]")
    print()

    # Check gate
    adaptive_in_ci = ci_lo <= adaptive <= ci_hi
    print(f"  Adaptive ({adaptive:.4f}) in n=5 CI {ci_s}? {adaptive_in_ci}")
    if gate == "A1":
        print("  -> Gate A1: CI excludes adaptive -> DDIC vs adaptive claim DEFENSIBLE")
    elif gate == "A2":
        print("  -> Gate A2: CI still contains adaptive -> AMBIGUOUS -> consider Tier B")
    elif gate == "A3":
        print("  -> Gate A3: High dispersion (std > 0.25) -> proceed to Tier B")

    # Build the updated predraft content
    # We create a new file rather than in-place editing the v2
    updated = text

    # 1. Update Section 1.2 training seeds line
    updated = updated.replace(
        "- **Training seeds**: 42, 43, 44 (parallel runs, ~6200 s wall time per seed) [FACT].",
        f"- **Training seeds**: 42, 43, 44, 45, 46 (5 total; seeds 42-44 canonical Phase 4; seeds 45-46 Tier A extension, 2026-05-04) [FACT].",
    )

    # 2. Update Table 1 DDIC mean row (3 seed -> 5 seed)
    old_row = "| **DDIC Phase 4 PHI_ABS=0 _final_ (3 seed mean)** | **−1.093** | 0.234 | 0.423 | 0.103 | 0.0 |"
    # Compute updated max_df for n=5 (use mean from agg)
    new_max_df_mean = max_df["mean"]
    new_row = (
        f"| **DDIC Phase 4 PHI_ABS=0 _final_ (n=5 seed mean)** "
        f"| **{mean:.3f}** | {new_max_df_mean:.3f} | — | — | 0.0 |"
    )
    updated = updated.replace(old_row, new_row)

    # Add new seed rows to the table
    old_seed44_row = "| DDIC Phase 4 seed 44 _final_ | −0.876 | 0.235 | 0.393 | 0.096 | 0.0 |"
    new_seed_rows = (
        f"| DDIC Phase 4 seed 44 _final_ | −0.914 | 0.237 | — | — | 0.0 |\n"
        f"| DDIC Phase 4 seed 45 _final_ | {per_seed['45']:.3f} | — | — | — | 0.0 |\n"
        f"| DDIC Phase 4 seed 46 _final_ | {per_seed['46']:.3f} | — | — | — | 0.0 |"
    )
    updated = updated.replace(old_seed44_row, new_seed_rows)

    # 3. Update Section 3.1 CI text
    old_ci_text = (
        "The cross-seed std (0.176, or 16% of mean −1.093) means the true 95% CI spans "
        "[−1.530, −0.656], which **contains best adaptive (−1.060)** — no significant difference at n=3. "
        "DDIC/adaptive ratio is indistinguishable from 1.0 at current sample size."
    )
    adaptive_pct = abs((mean - adaptive) / adaptive) * 100
    rel_std = std / abs(mean) * 100
    new_ci_text = (
        f"The cross-seed std ({std:.3f}, or {rel_std:.0f}% of mean {mean:.3f}) gives "
        f"n=5 95% CI {ci_s} [t(4,0.025)=2.776]; bootstrap CI {boot_ci_s}. "
    )
    if gate == "A1":
        new_ci_text += (
            f"Best adaptive ({adaptive:.3f}) **is outside** the CI → "
            f"DDIC vs best-adaptive difference is statistically defensible at n=5."
        )
    else:
        new_ci_text += (
            f"Best adaptive ({adaptive:.3f}) **remains within** the CI → "
            f"no significant difference at n=5. Gate {gate}: {agg['gate_logic'][gate]}"
        )
    updated = updated.replace(old_ci_text, new_ci_text)

    # 4. Update Section 5 claim #2
    old_claim2 = (
        "2. **DDIC loses to adaptive on cum_rf** (NOT marginal win): 3-seed mean −1.093 (DDIC) vs −1.060 "
        "(best adaptive K=10/400). DDIC is 3% **worse** on cum_rf. The 95% CI [−1.530, −0.656] fully "
        "contains best adaptive (−1.060), meaning **no statistically significant difference** at n=3. "
        "DDIC **wins on oscillation**: 0.103 Hz (DDIC) vs 0.115 Hz (adaptive), a 10% improvement."
    )
    ddic_vs_adaptive = (mean - adaptive) / abs(adaptive) * 100
    direction = "wins" if mean > adaptive else "loses"
    new_claim2 = (
        f"2. **DDIC vs adaptive on cum_rf (n=5 update)**: n=5 mean {mean:.3f} (DDIC) vs {adaptive:.3f} "
        f"(best adaptive K=10/400). DDIC is {abs(ddic_vs_adaptive):.0f}% **{'better' if direction=='wins' else 'worse'}** "
        f"on cum_rf. The n=5 95% CI {ci_s} [half-width={hw_s}, t(4,0.025)=2.776]. "
    )
    if gate == "A1":
        new_claim2 += (
            f"Best adaptive ({adaptive:.3f}) is **outside** the CI → "
            f"claim of difference is defensible at n=5. "
        )
    else:
        new_claim2 += (
            f"Best adaptive ({adaptive:.3f}) **remains within** the CI → "
            f"**no statistically significant difference** at n=5. Gate {gate} → Tier B recommended. "
        )
    new_claim2 += "DDIC **wins on oscillation**: 0.103 Hz (DDIC) vs 0.115 Hz (adaptive), a 10% improvement."
    updated = updated.replace(old_claim2, new_claim2)

    # 5. Update Limitations §2
    old_lim2 = (
        "2. **Statistical thin sample** (n=3 seeds). Cross-seed std 0.176 (16% of mean −1.093). "
        "95% CI [−1.530, −0.656] spans ±0.437, overlapping best adaptive (-1.060). "
        "Proper evaluation needs n≥5 for significance. Current n=3 is underpowered for claims of difference."
    )
    new_lim2 = (
        f"2. **Statistical sample updated to n=5** (Tier A, 2026-05-04). "
        f"Cross-seed std {std:.3f} ({rel_std:.0f}% of mean {mean:.3f}). "
        f"n=5 95% CI {ci_s} (half-width={hw_s}, vs n=3 half-width≈{n3_hw:.3f}). "
    )
    if gate == "A1":
        new_lim2 += (
            f"Best adaptive ({adaptive:.3f}) falls **outside** the CI → Gate A1 (claim defensible). "
            f"No Tier B needed."
        )
    else:
        new_lim2 += (
            f"Best adaptive ({adaptive:.3f}) **still within** CI → Gate {gate}: proceed to Tier B (n=10) "
            f"for conclusive separation or accept stat-tie framing."
        )
    updated = updated.replace(old_lim2, new_lim2)

    # 6. Update abstract sentence about seeds
    updated = updated.replace(
        "Six hours of GPU time across 3 training seeds.",
        f"Six hours of GPU time across 5 training seeds (seeds 42-44 Phase 4; seeds 45-46 Tier A n=5 extension, 2026-05-04).",
    )

    # Add Tier A section header before Section 3
    tier_a_note = (
        f"\n\n> **Tier A Update (2026-05-04)**: Seeds 45 and 46 added to extend n=3→5 per "
        f"`quality_reports/plans/2026-05-03_andes_n5_retrain_spec.md`. "
        f"n=5 cum_rf_total: mean={mean:.4f}, std={std:.4f}, t-CI={ci_s}. "
        f"Gate: **{gate}** — {agg['gate_logic'][gate]}\n\n"
    )
    updated = updated.replace(
        "## 3. Performance Results",
        f"## 3. Performance Results{tier_a_note}",
    )

    # Write the updated predraft
    out_path = ROOT / "quality_reports/replications/2026-05-03_andes_ddic_honest_results_predraft_n5.md"
    out_path.write_text(updated, encoding="utf-8")
    print(f"Written: {out_path}")

    # Also update the plan file Tier A actuals
    print()
    print("Summary for plan update:")
    print(f"  Tier A actuals: seeds 45={per_seed['45']:.4f}, 46={per_seed['46']:.4f}")
    print(f"  n=5 mean={mean:.4f} std={std:.4f} CI={ci_s}")
    print(f"  Gate={gate}")
    print()
    print("All done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
