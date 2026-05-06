"""Plan §2 Fig.5 — 3-seed cross-run consistency at ep 0-99.

Plan §5.2 (verified):
    seed 100: mean=-0.2016, std(within-seed)=0.0405
    seed 200: mean=-0.2039, std(within-seed)=0.0369
    seed 300: mean=-0.2081, std(within-seed)=0.0367
    Cross-seed mean = -0.2045, cross-seed std = 0.0027 (CV = 1.3%)

Output: paper/figures/fig_seed_consistency.png + .pdf

Visual: side-by-side bars
    Left:  per-seed within-seed std (intrinsic episode noise) — 3 bars
    Right: cross-seed std (algorithm-stable across initialization) — 1 bar

Interpretation framing (plan §5.2):
    "Inter-seed variance NEGLIGIBLE at 100 ep. NOT a statistical
     significance test (n=3 underpowered) — framed as consistency check."
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    RUN_DIRS, OUT_DIR,
    load_metrics_jsonl, get_episode_rewards, banner_no_anchor,
)
from plotting.paper_style import (  # noqa: E402
    apply_ieee_style, paper_legend, save_fig, ES_COLORS_4,
)


SEED_RUNS = [
    ("trial3",         100, ES_COLORS_4[0]),
    ("trial3_seed200", 200, ES_COLORS_4[1]),
    ("trial3_seed300", 300, ES_COLORS_4[2]),
]

BLOCK_HI = 100  # ep [0, 100)


def main() -> None:
    print(banner_no_anchor("Seed consistency"))
    apply_ieee_style()

    seed_means: list[float] = []
    seed_stds: list[float] = []
    seed_labels: list[str] = []
    seed_colors: list[str] = []

    for key, seed, color in SEED_RUNS:
        rd = RUN_DIRS[key]
        m = load_metrics_jsonl(rd)
        if not m:
            print(f"  [WARN] {key} (seed {seed}) missing — skipping")
            continue
        r = get_episode_rewards(m)
        block = r[:BLOCK_HI]
        block = block[~np.isnan(block)]
        if block.size < BLOCK_HI:
            print(f"  [WARN] {key} only {block.size} ep (< {BLOCK_HI})")
        seed_means.append(float(block.mean()))
        seed_stds.append(float(block.std()))
        seed_labels.append(f"seed {seed}\n(n={block.size})")
        seed_colors.append(color)
        print(f"  {key}: mean={block.mean():+.4f}, "
              f"within-seed std={block.std():.4f}")

    if len(seed_means) < 2:
        print("  ERROR: need ≥2 seeds for consistency check")
        return

    cross_seed_mean = float(np.mean(seed_means))
    cross_seed_std = float(np.std(seed_means))
    cv = abs(cross_seed_std / cross_seed_mean) * 100 if cross_seed_mean else float("nan")
    print(f"  cross-seed mean={cross_seed_mean:+.4f}, "
          f"cross-seed std={cross_seed_std:.4f} (CV={cv:.1f}%)")

    # ── Figure: 2 panels ──
    fig, (ax_l, ax_r) = plt.subplots(1, 2, figsize=(7.16, 3.0),
                                     gridspec_kw={"width_ratios": [3, 1]})
    fig.subplots_adjust(left=0.10, right=0.97, top=0.88, bottom=0.20, wspace=0.50)

    # Left: within-seed std bars
    n = len(seed_stds)
    x = np.arange(n)
    bars_l = ax_l.bar(x, seed_stds, color=seed_colors, edgecolor="black", lw=0.8)
    for bar, val in zip(bars_l, seed_stds):
        ax_l.annotate(f"{val:.4f}", xy=(bar.get_x() + bar.get_width() / 2, val),
                      xytext=(0, 3), textcoords="offset points",
                      ha="center", va="bottom", fontsize=8)
    ax_l.set_xticks(x)
    ax_l.set_xticklabels(seed_labels, fontsize=8.5)
    ax_l.set_ylabel("Within-seed std\n(intrinsic ep noise)",
                    fontsize=9.5, rotation=0, labelpad=42, va="center")
    ax_l.set_title("Per-seed episode reward variability",
                    fontsize=10, pad=4)
    ax_l.set_ylim(0, max(seed_stds) * 1.30)

    # Right: cross-seed std (single bar)
    ax_r.bar([0], [cross_seed_std], color="#8B3A3A",
             edgecolor="black", lw=0.8, width=0.5)
    ax_r.annotate(f"{cross_seed_std:.4f}\n(CV={cv:.1f}%)",
                  xy=(0, cross_seed_std),
                  xytext=(0, 3), textcoords="offset points",
                  ha="center", va="bottom", fontsize=8.5)
    ax_r.set_xticks([0])
    ax_r.set_xticklabels([f"cross-seed\n(n={n} seeds)"], fontsize=8.5)
    ax_r.set_ylabel("Cross-seed std\n(algorithm consistency)",
                    fontsize=9.5, rotation=0, labelpad=42, va="center")
    ax_r.set_title("Inter-run", fontsize=10, pad=4)
    ax_r.set_ylim(0, max(seed_stds) * 1.30)  # same y-scale for visual contrast

    fig.suptitle(
        f"3-seed consistency at ep [0, {BLOCK_HI}): "
        f"within-seed >> cross-seed std → algorithm-stable",
        fontsize=10, y=0.995,
    )
    save_fig(fig, str(OUT_DIR), "fig_seed_consistency.png")


if __name__ == "__main__":
    main()
