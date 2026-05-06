"""Plan §2 Fig.4 — PHI sensitivity 3-point bar chart.

Compares ep[38, 48) mean r_f across 3 PHI values:
    PHI=5e-4 (trial3 main, seed=100, fresh)
    PHI=1e-3 (trial3_phi1e3 neighborhood, seed=100, fresh)
    PHI=0.1  (trial2A_baseline, seed=42, resumed from ep10) — confounded

Caveat (plan §5.1, critic M1):
    PHI=0.1 datapoint differs in seed AND init from the other two →
    rendered with diagonal hatching as "seed-confounded".

Output: paper/figures/fig_phi_sweep.png + .pdf
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
    RUN_DIRS, OUT_DIR, PHI_SWEEP_BLOCK,
    load_metrics_jsonl, get_reward_components, block_mean, banner_no_anchor,
)
from plotting.paper_style import (  # noqa: E402
    apply_ieee_style, paper_legend, save_fig,
)


# (run_key, phi_value, seed_match_flag, color)
SWEEP = [
    ("trial3",            5e-4, True,  "#2E8B57"),  # main, seed-matched
    ("trial3_phi1e3",     1e-3, True,  "#4A90D9"),  # matched
    ("trial2A_baseline",  1e-1, False, "#B07DD0"),  # confounded
]


def main() -> None:
    print(banner_no_anchor("PHI sweep"))
    apply_ieee_style()

    phis: list[float] = []
    means: list[float] = []
    seed_match: list[bool] = []
    colors: list[str] = []
    n_eps: list[int] = []

    for key, phi, matched, color in SWEEP:
        rd = RUN_DIRS[key]
        m = load_metrics_jsonl(rd)
        if not m:
            print(f"  [WARN] {key} missing — skipping")
            continue
        rc = get_reward_components(m)
        lo, hi = PHI_SWEEP_BLOCK
        if len(m) < hi:
            hi_eff = len(m)
            print(f"  [WARN] {key} only {len(m)} ep, using ep[{lo}, {hi_eff})")
        else:
            hi_eff = hi
        mean_rf = block_mean(rc["r_f"], lo, hi_eff)
        phis.append(phi)
        means.append(mean_rf)
        seed_match.append(matched)
        colors.append(color)
        n_eps.append(hi_eff - lo)
        flag = "seed-matched" if matched else "seed-confounded"
        print(f"  {key}: PHI={phi:.0e}, r_f={mean_rf:+.4f} ({flag}, n={hi_eff - lo})")

    fig, ax = plt.subplots(figsize=(4.5, 3.2))
    fig.subplots_adjust(left=0.18, right=0.96, top=0.92, bottom=0.18)

    x = np.arange(len(phis))
    bars = ax.bar(x, means, color=colors, edgecolor="black", lw=0.8, width=0.65)
    # Hatch the confounded bar(s)
    for bar, matched in zip(bars, seed_match):
        if not matched:
            bar.set_hatch("///")

    # Add headroom below 0 for legend & headroom above 0 for labels
    ymin_data = min(means)
    ax.set_ylim(ymin_data * 1.30, max(0, ymin_data * -0.10))

    # Value labels INSIDE bar near top edge (closer to 0 for negative bars)
    for bar, val, n in zip(bars, means, n_eps):
        label_y = val * 0.5  # mid-bar
        ax.annotate(
            f"{val:+.3f}\n(n={n})",
            xy=(bar.get_x() + bar.get_width() / 2, label_y),
            ha="center", va="center", fontsize=8,
            color="white" if abs(val) > abs(ymin_data) * 0.5 else "black",
        )

    ax.set_xticks(x)
    ax.set_xticklabels([f"{p:.0e}" for p in phis], fontsize=9)
    ax.set_xlabel(r"$\varphi_h = \varphi_d$", fontsize=10, labelpad=4)
    ax.set_ylabel(r"$r_f$ block mean (ep "
                  f"{PHI_SWEEP_BLOCK[0]}–{PHI_SWEEP_BLOCK[1]})", fontsize=10)
    ax.set_title("PHI sensitivity (3-point sweep)", fontsize=10, pad=4)
    ax.axhline(0, color="gray", lw=0.4, ls=":")

    # Legend explaining hatch — placed above plot area
    matched_patch = plt.Rectangle((0, 0), 1, 1, fc="gray", ec="black", lw=0.8)
    confounded_patch = plt.Rectangle((0, 0), 1, 1, fc="gray", ec="black",
                                     lw=0.8, hatch="///")
    ax.legend([matched_patch, confounded_patch],
              ["seed-matched (fresh)", "seed-confounded"],
              loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2,
              fontsize=7.5, framealpha=0.95,
              edgecolor="black", fancybox=False, borderpad=0.3)
    fig.subplots_adjust(bottom=0.30)

    save_fig(fig, str(OUT_DIR), "fig_phi_sweep.png")


if __name__ == "__main__":
    main()
