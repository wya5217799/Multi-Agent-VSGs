"""Fig.4 — Training performance (paper Sec.IV-B, Fig.4).

Layout (paper Fig.4):
    (a) Total + 100×r_f + r_h + r_d (rolling mean + std band)
    (b)-(e) ES1-ES4 per-agent episode reward

Degraded mode:
    If metrics.jsonl has no `reward_per_agent` field (legacy runs prior to
    P1.2 patch from 2026-05-05_paper_figure_toolkit.md), only (a) is rendered
    and a warning is printed. Re-run training with the patched code to get
    full 5-subplot output.

Annotations:
    Plan §5.3 honest peak: shaded band over ep 200-220, R=-0.120 callout.

Source data:
    paper/figure_scripts/_common.RUN_DIRS["trial3"]/logs/metrics.jsonl
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D

# Allow running from anywhere
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    RUN_DIRS, OUT_DIR, PEAK_EP_RANGE,
    load_metrics_jsonl, get_episode_rewards, get_reward_components,
    get_per_agent_rewards, banner_no_anchor, warn_missing,
)
from plotting.paper_style import (  # noqa: E402
    apply_ieee_style, paper_legend, plot_band, save_fig,
    ES_COLORS_4,
    COLOR_TOTAL, COLOR_FREQ, COLOR_INERTIA, COLOR_DROOP,
)


def _peak_callout(ax, ep_range, label_text, ymin, ymax):
    """Shade peak episode window + add label."""
    lo, hi = ep_range
    ax.axvspan(lo, hi, color="#E8863A", alpha=0.15, lw=0)
    ax.annotate(
        label_text,
        xy=((lo + hi) / 2, ymax),
        xytext=((lo + hi) / 2, ymax - 0.05 * (ymax - ymin)),
        ha="center", va="top", fontsize=8, color="#8B4513",
        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#8B4513", lw=0.5),
    )


def _plot_a_only(metrics, run_label, out_name, window=20):
    """Degraded mode: only (a) Total + r_f + r_h + r_d, no per-agent."""
    apply_ieee_style()
    rewards = get_episode_rewards(metrics)
    rc = get_reward_components(metrics)
    n_ep = len(rewards)
    episodes = np.arange(n_ep)

    fig, ax = plt.subplots(figsize=(7.16, 3.5))
    fig.subplots_adjust(left=0.11, right=0.97, top=0.95, bottom=0.14)

    plot_band(ax, episodes, rewards, COLOR_TOTAL, "Total", window=window)
    # Paper Fig.4 (a) plots 100×Frequency to make it visible alongside Total
    plot_band(ax, episodes, 100 * rc["r_f"], COLOR_FREQ, r"$100\times r_f$", window=window)
    plot_band(ax, episodes, rc["r_h"], COLOR_INERTIA, r"$r_h$", window=window)
    plot_band(ax, episodes, rc["r_d"], COLOR_DROOP, r"$r_d$", window=window)

    ax.set_xlabel("(a) Training episodes", fontsize=10.5, labelpad=4)
    ax.set_ylabel("Episode\nreward", fontsize=10.5,
                  rotation=0, labelpad=35, va="center")
    ax.set_xlim(0, n_ep)
    ax.axhline(0, color="gray", lw=0.4, ls=":")

    # Honest peak band (plan §5.3)
    if n_ep >= PEAK_EP_RANGE[1]:
        ymin, ymax = ax.get_ylim()
        peak_mean = float(np.nanmean(rewards[PEAK_EP_RANGE[0]:PEAK_EP_RANGE[1]]))
        _peak_callout(
            ax, PEAK_EP_RANGE,
            f"PEAK ep {PEAK_EP_RANGE[0]}-{PEAK_EP_RANGE[1]}\nR={peak_mean:+.3f}",
            ymin, ymax,
        )

    paper_legend(ax, loc="lower right", fontsize=8.5, ncol=2)
    ax.text(0.01, 0.98, f"run: {run_label}", transform=ax.transAxes,
            fontsize=7, color="gray", va="top", ha="left",
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.7))

    save_fig(fig, str(OUT_DIR), out_name)


def _plot_full_5sub(metrics, per_agent, run_label, out_name, window=20):
    """Paper-faithful Fig.4: (a) top-wide + (b)-(e) ES1-ES4 grid."""
    apply_ieee_style()
    rewards = get_episode_rewards(metrics)
    rc = get_reward_components(metrics)
    n_ep = len(rewards)
    n_agents = per_agent.shape[0]
    episodes = np.arange(n_ep)
    colors = ES_COLORS_4[:n_agents]

    n_rows_sub = (n_agents + 1) // 2
    fig = plt.figure(figsize=(7.16, 3.5 + 2.5 * n_rows_sub))
    gs = GridSpec(1 + n_rows_sub, 2, figure=fig,
                  height_ratios=[1.5] + [1] * n_rows_sub,
                  hspace=0.50, wspace=0.40,
                  left=0.11, right=0.97, top=0.98, bottom=0.06)

    # ── (a) Total + 100×r_f + r_h + r_d ──
    ax_a = fig.add_subplot(gs[0, :])
    plot_band(ax_a, episodes, rewards, COLOR_TOTAL, "Total", window=window)
    plot_band(ax_a, episodes, 100 * rc["r_f"], COLOR_FREQ, r"$100\times r_f$", window=window)
    plot_band(ax_a, episodes, rc["r_h"], COLOR_INERTIA, r"$r_h$", window=window)
    plot_band(ax_a, episodes, rc["r_d"], COLOR_DROOP, r"$r_d$", window=window)
    ax_a.set_ylabel("Episode\nreward", fontsize=10.5,
                    rotation=0, labelpad=35, va="center")
    ax_a.set_xlim(0, n_ep)
    ax_a.axhline(0, color="gray", lw=0.4, ls=":")
    ax_a.xaxis.set_major_locator(mticker.MaxNLocator(integer=True, nbins=8))

    if n_ep >= PEAK_EP_RANGE[1]:
        ymin, ymax = ax_a.get_ylim()
        peak_mean = float(np.nanmean(rewards[PEAK_EP_RANGE[0]:PEAK_EP_RANGE[1]]))
        _peak_callout(ax_a, PEAK_EP_RANGE,
                      f"PEAK ep {PEAK_EP_RANGE[0]}-{PEAK_EP_RANGE[1]}\nR={peak_mean:+.3f}",
                      ymin, ymax)

    paper_legend(ax_a, loc="lower right", fontsize=8.5, ncol=2)
    ax_a.set_xlabel("(a) Training episodes", fontsize=10.5, labelpad=5)

    # ── (b)-(e) per-ES ──
    sub_labels = [f"({chr(98 + i)})" for i in range(n_agents)]
    es_names = [f"ES{i+1}" for i in range(n_agents)]
    for idx in range(n_agents):
        row = 1 + idx // 2
        col = idx % 2
        ax = fig.add_subplot(gs[row, col])
        plot_band(ax, episodes, per_agent[idx], colors[idx], None, window=window)
        ax.set_ylabel("Episode\nreward", fontsize=9,
                      rotation=0, labelpad=30, va="center")
        ax.set_xlim(0, n_ep)
        ax.axhline(0, color="gray", lw=0.4, ls=":")
        legend_line = Line2D([0], [0], color=colors[idx], lw=1.5)
        leg = ax.legend([legend_line], [f"{es_names[idx]}-Total"],
                        loc="lower right", fontsize=7.5,
                        framealpha=0.95, edgecolor="black", fancybox=False,
                        borderpad=0.3, handlelength=1.5)
        leg.get_frame().set_linewidth(0.5)
        ax.set_xlabel(f"{sub_labels[idx]} Training episodes",
                      fontsize=9.5, labelpad=3)

    fig.text(0.99, 0.005, f"run: {run_label}", fontsize=7, color="gray",
             ha="right", va="bottom")
    save_fig(fig, str(OUT_DIR), out_name)


def main(run_key: str = "trial3", out_name: str = "fig4_training.png") -> None:
    print(banner_no_anchor("Fig.4"))
    run_dir = RUN_DIRS[run_key]
    metrics = load_metrics_jsonl(run_dir)
    if not metrics:
        print(f"  ERROR: no metrics.jsonl at {run_dir}")
        return
    print(f"  run: {run_dir.name}, n_ep: {len(metrics)}")

    per_agent = get_per_agent_rewards(metrics)
    if per_agent is None:
        warn_missing("reward_per_agent", run_dir,
                     "rendering (a)-only — re-run training with P1.2 patch for full Fig.4")
        _plot_a_only(metrics, run_dir.name, out_name)
    else:
        print(f"  per-agent rewards present: shape={per_agent.shape}")
        _plot_full_5sub(metrics, per_agent, run_dir.name, out_name)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="trial3", choices=list(RUN_DIRS.keys()))
    ap.add_argument("--out", default="fig4_training.png")
    args = ap.parse_args()
    main(args.run, args.out)
