"""
Regenerate fig1 and fig3 with paper-faithful comm_fail_prob=0.1 data.
Run:
  wsl bash -c 'source ~/andes_venv/bin/activate && \
    cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs" && \
    python3 scenarios/kundur/_regen_fig1_fig3.py'
"""

import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parent.parent.parent
OUTDIR = REPO / "results" / "andes_predraft_figures"
PAPER_FIG_DIR = REPO / "paper" / "figures"
OUTDIR.mkdir(parents=True, exist_ok=True)
PAPER_FIG_DIR.mkdir(parents=True, exist_ok=True)

DPI = 300
VIRIDIS = plt.cm.viridis

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.dpi": DPI,
})


def vir_color(idx, n):
    return VIRIDIS(idx / max(n - 1, 1))


def save_fig(fig, name):
    path = OUTDIR / name
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved: {path}")
    # Copy to paper/figures/
    import shutil
    shutil.copy2(path, PAPER_FIG_DIR / name)
    print(f"  copied to: {PAPER_FIG_DIR / name}")
    return path


# ---------------------------------------------------------------------------
# Fig 1 — Per-agent share, 5 seeds, comm_fail_prob=0.1
# ---------------------------------------------------------------------------
def fig1_agent_share_5seeds():
    print("Fig 1: 5-seed agent share (comm_fail_prob=0.1) ...")
    agent_dir = REPO / "results" / "harness" / "kundur" / "agent_state"

    seeds = [42, 43, 44, 45, 46]
    filenames = [
        "agent_state_phase4_seed42_commfail01.json",
        "agent_state_phase4_seed43_commfail01.json",
        "agent_state_phase4_seed44_commfail01.json",
        "agent_state_phase4ext_seed45_final.json",
        "agent_state_phase4ext_seed46_final.json",
    ]
    n_agents = 4
    agent_labels = ["a0 (SG1)", "a1 (ES2\n@Bus16)", "a2 (ES3\n@Bus14)", "a3 (ES4)"]

    shares = {}
    for seed, fn in zip(seeds, filenames):
        d = json.load(open(agent_dir / fn))
        pa2 = d["phase_a2_ablation"]["per_agent_ablation"]
        shares[seed] = [pa2[i]["share"] * 100 for i in range(n_agents)]
        print(f"  seed{seed}: " + " ".join(f"a{i}={shares[seed][i]:.1f}%" for i in range(n_agents)))

    n_seeds = len(seeds)
    x = np.arange(n_agents)
    width = 0.15
    offsets = np.linspace(-(n_seeds - 1) / 2 * width, (n_seeds - 1) / 2 * width, n_seeds)
    seed_colors = [vir_color(i, n_seeds) for i in range(n_seeds)]

    fig, ax = plt.subplots(figsize=(8.0, 4.5))

    for idx, seed in enumerate(seeds):
        bars = ax.bar(
            x + offsets[idx],
            shares[seed],
            width=width,
            color=seed_colors[idx],
            label=f"seed {seed}",
            edgecolor="white",
            linewidth=0.5,
        )
        for bar, val in zip(bars, shares[seed]):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.7,
                f"{val:.0f}%",
                ha="center",
                va="bottom",
                fontsize=6.5,
                color="black",
            )

    ax.set_xticks(x)
    ax.set_xticklabels(agent_labels, ha="center")
    ax.set_ylabel("Reward contribution share (%)")
    ax.set_title(
        "Per-agent ablation share, 5 seeds, paper-faithful comm_fail_prob=0.1\n"
        "a1 mean 64.0%  range 54.6–74.7%"
    )
    ax.set_ylim(0, 95)
    ax.legend(loc="upper left", ncol=3)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.spines[["top", "right"]].set_visible(False)

    # Annotate a1 dominance
    a1_vals = [shares[s][1] for s in seeds]
    a1_mean = np.mean(a1_vals)
    a1_min, a1_max = min(a1_vals), max(a1_vals)
    ax.annotate(
        f"a1 dominant\nmean {a1_mean:.1f}%\n{a1_min:.0f}–{a1_max:.0f}%",
        xy=(1, a1_max + 1),
        xytext=(1.8, a1_max + 14),
        arrowprops=dict(arrowstyle="->", color="#333333", lw=1.2),
        fontsize=8,
        color="#333333",
    )

    fig.tight_layout()
    # Save both filenames: new canonical + legacy name (overwrite so paper picks up)
    save_fig(fig, "fig1_agent_share_5seeds.png")

    # Re-open and save as the legacy name too so paper compile picks it up
    fig2, ax2 = plt.subplots(figsize=(8.0, 4.5))
    for idx, seed in enumerate(seeds):
        bars = ax2.bar(
            x + offsets[idx],
            shares[seed],
            width=width,
            color=seed_colors[idx],
            label=f"seed {seed}",
            edgecolor="white",
            linewidth=0.5,
        )
        for bar, val in zip(bars, shares[seed]):
            ax2.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.7,
                f"{val:.0f}%",
                ha="center",
                va="bottom",
                fontsize=6.5,
                color="black",
            )
    ax2.set_xticks(x)
    ax2.set_xticklabels(agent_labels, ha="center")
    ax2.set_ylabel("Reward contribution share (%)")
    ax2.set_title(
        "Per-agent ablation share, 5 seeds, paper-faithful comm_fail_prob=0.1\n"
        "a1 mean 64.0%  range 54.6–74.7%"
    )
    ax2.set_ylim(0, 95)
    ax2.legend(loc="upper left", ncol=3)
    ax2.grid(axis="y", alpha=0.3, linestyle="--")
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.annotate(
        f"a1 dominant\nmean {a1_mean:.1f}%\n{a1_min:.0f}–{a1_max:.0f}%",
        xy=(1, a1_max + 1),
        xytext=(1.8, a1_max + 14),
        arrowprops=dict(arrowstyle="->", color="#333333", lw=1.2),
        fontsize=8,
        color="#333333",
    )
    fig2.tight_layout()
    save_fig(fig2, "fig1_agent_share_3seeds.png")  # overwrite legacy name


# ---------------------------------------------------------------------------
# Fig 3 — Cumulative freq reward, paper-grade data + bootstrap CI bands
# ---------------------------------------------------------------------------
def fig3_cum_rf_paper_grade():
    print("Fig 3: cum_rf comparison (paper-grade, n=5 bootstrap CI) ...")

    base = REPO / "results" / "andes_eval_paper_grade"
    per_seed = json.load(open(base / "per_seed_summary.json"))
    n5 = json.load(open(base / "n5_aggregate.json"))

    c = per_seed["controllers"]

    # Values (total over 50 episodes)
    no_ctrl_total     = c["no_control"]["cum_rf_total"]
    adap_total        = c["adaptive_K10_K400"]["cum_rf_total"]
    s42_total         = c["ddic_phase4_seed42_final"]["cum_rf_total"]
    s43_total         = c["ddic_phase4_seed43_final"]["cum_rf_total"]
    s44_total         = c["ddic_phase4_seed44_final"]["cum_rf_total"]
    ddic3_mean        = np.mean([s42_total, s43_total, s44_total])

    n5_mean           = n5["n5_cum_rf_total"]["mean"]
    n5_ci_lo          = n5["n5_cum_rf_bootstrap"]["ci_lo"]
    n5_ci_hi          = n5["n5_cum_rf_bootstrap"]["ci_hi"]

    # Bootstrap CI for adaptive (per_seed ci is per-episode; scale to total x50)
    adap_ci = c["adaptive_K10_K400"]["cum_rf_ci"]
    adap_ci_lo_total  = adap_ci["ci_lo"] * 50
    adap_ci_hi_total  = adap_ci["ci_hi"] * 50

    print(f"  no_control total: {no_ctrl_total:.4f}")
    print(f"  adaptive total:   {adap_total:.4f}  CI [{adap_ci_lo_total:.4f}, {adap_ci_hi_total:.4f}]")
    print(f"  ddic s42 total:   {s42_total:.4f}")
    print(f"  ddic s43 total:   {s43_total:.4f}")
    print(f"  ddic s44 total:   {s44_total:.4f}")
    print(f"  ddic 3-seed mean: {ddic3_mean:.4f}")
    print(f"  ddic n=5 mean:    {n5_mean:.4f}  bootstrap CI [{n5_ci_lo:.4f}, {n5_ci_hi:.4f}]")

    # Bars: (label, value_total, ci_lo_total, ci_hi_total, color)
    bars = [
        ("No control",             no_ctrl_total, None, None,              "#cccccc"),
        ("Adaptive\nK=10/400",     adap_total,    adap_ci_lo_total, adap_ci_hi_total, vir_color(1, 5)),
        ("DDIC\nseed42",           s42_total,     None, None,              vir_color(2, 5)),
        ("DDIC\nseed43",           s43_total,     None, None,              vir_color(3, 5)),
        ("DDIC\nseed44",           s44_total,     None, None,              vir_color(4, 5)),
        ("DDIC\n3-seed\nmean",     ddic3_mean,    None, None,              "#1a5276"),
        ("DDIC n=5\nmean\n(paper)", n5_mean,      n5_ci_lo, n5_ci_hi,     "#0e6b5e"),
    ]

    labels = [b[0] for b in bars]
    vals   = np.array([b[1] for b in bars])
    ci_los = [b[2] for b in bars]
    ci_his = [b[3] for b in bars]
    colors = [b[4] for b in bars]

    fig, ax = plt.subplots(figsize=(10.0, 5.0))
    x = np.arange(len(bars))
    bar_width = 0.6

    for i, (v, ci_lo, ci_hi, c_color) in enumerate(zip(vals, ci_los, ci_his, colors)):
        ax.bar(x[i], v, width=bar_width, color=c_color, edgecolor="white", linewidth=0.5)
        if ci_lo is not None and ci_hi is not None:
            # Error bar: center at v, extend to ci bounds
            yerr_lo = abs(v - ci_lo)
            yerr_hi = abs(ci_hi - v)
            ax.errorbar(
                x[i], v,
                yerr=[[yerr_lo], [yerr_hi]],
                fmt="none", ecolor="black",
                elinewidth=1.8, capsize=5, capthick=1.5,
            )
            # CI range text
            ax.text(
                x[i], ci_hi + 0.01,
                f"[{ci_lo:.2f},\n {ci_hi:.2f}]",
                ha="center", va="bottom", fontsize=6.5, color="#222222",
            )

    # Reference line: best adaptive total
    ax.axhline(y=adap_total, color="#e74c3c", linestyle="--",
               linewidth=1.2, alpha=0.8,
               label=f"Adaptive K=10/400 total = {adap_total:.3f}")

    # Divider between per-seed and aggregate bars
    ax.axvline(x=4.5, color="#aaaaaa", linestyle=":", linewidth=1.0)
    ax.text(4.55, vals.min() * 0.85, "aggregate\n→", ha="left", fontsize=7.5, color="#666666")

    # Value labels on bars
    for xi, v in enumerate(vals):
        ax.text(xi, v - 0.04, f"{v:.3f}", ha="center", va="top",
                fontsize=7, color="white", fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, ha="center")
    ax.set_ylabel("Cumulative frequency reward total over 50 episodes (less negative = better)")
    ax.set_title(
        "Cumulative frequency reward — paper-grade eval, comm_fail_prob=0.1\n"
        "n=5 DDIC mean −1.186, bootstrap 95% CI [−1.39, −0.98]  |  Adaptive −1.060 → statistically TIED"
    )
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.spines[["top", "right"]].set_visible(False)

    fig.tight_layout()
    save_fig(fig, "fig3_cum_rf_comparison.png")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Regenerating fig1 + fig3 with paper-faithful data ...")
    fig1_agent_share_5seeds()
    fig3_cum_rf_paper_grade()
    print("\nDone.")
