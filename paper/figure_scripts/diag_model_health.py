"""Diagnostic — model health 8-panel figure for problem hunting.

Not a paper figure. Used by the AI/user to identify concrete problems
in a training run BEFORE committing to a narrative.

Reads:
    metrics.jsonl per-episode rows with full reward_components + physics +
    action_stats + alpha/critic_loss/policy_loss

Output:
    paper/figures/diag_model_health.png

Run:
    python paper/figure_scripts/diag_model_health.py [--run trial3]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    RUN_DIRS, OUT_DIR,
    load_metrics_jsonl, get_episode_rewards, get_reward_components,
    banner_no_anchor,
)
from plotting.paper_style import (  # noqa: E402
    apply_ieee_style, plot_band, paper_legend, save_fig,
    COLOR_TOTAL, COLOR_FREQ, COLOR_INERTIA, COLOR_DROOP,
)


def _scalar_field(metrics: list[dict], path: list[str], default=np.nan) -> np.ndarray:
    out = []
    for m in metrics:
        cur: any = m
        for k in path:
            if not isinstance(cur, dict):
                cur = None
                break
            cur = cur.get(k)
        out.append(default if cur is None else float(cur))
    return np.asarray(out, dtype=float)


def main(run_key: str = "trial3") -> None:
    print(banner_no_anchor("Diagnostic"))
    apply_ieee_style()

    rd = RUN_DIRS[run_key]
    m = load_metrics_jsonl(rd)
    if not m:
        print(f"  ERROR: no metrics at {rd}")
        return
    n = len(m)
    ep = np.arange(n)
    print(f"  run: {rd.name}  n_ep: {n}")

    rewards = get_episode_rewards(m)
    rc = get_reward_components(m)

    # Physics
    max_freq = _scalar_field(m, ["physics", "max_freq_dev_hz"])
    mean_freq = _scalar_field(m, ["physics", "mean_freq_dev_hz"])
    settled = _scalar_field(m, ["physics", "settled"], default=0)
    max_swing = _scalar_field(m, ["physics", "max_power_swing"])

    # Action stats
    dH_abs = _scalar_field(m, ["action_stats", "delta_H_mean_abs"])
    dD_abs = _scalar_field(m, ["action_stats", "delta_D_mean_abs"])
    dH_clip = _scalar_field(m, ["action_stats", "delta_H_clip_rate"])
    dD_clip = _scalar_field(m, ["action_stats", "delta_D_clip_rate"])

    # SAC internals
    alpha = np.asarray([mm.get("alpha", np.nan) for mm in m], dtype=float)
    critic_loss = np.asarray([mm.get("critic_loss", np.nan) for mm in m], dtype=float)
    policy_loss = np.asarray([mm.get("policy_loss", np.nan) for mm in m], dtype=float)

    fig = plt.figure(figsize=(12, 10))
    gs = GridSpec(4, 2, figure=fig, hspace=0.50, wspace=0.30,
                  left=0.07, right=0.97, top=0.95, bottom=0.05)
    win = max(20, n // 25)

    # (a) Reward trajectory + components
    ax = fig.add_subplot(gs[0, :])
    plot_band(ax, ep, rewards, COLOR_TOTAL, "Total", window=win)
    plot_band(ax, ep, 100 * rc["r_f"], COLOR_FREQ, r"$100\times r_f$", window=win)
    plot_band(ax, ep, rc["r_h"], COLOR_INERTIA, r"$r_h$", window=win)
    plot_band(ax, ep, rc["r_d"], COLOR_DROOP, r"$r_d$", window=win)
    ax.axhline(0, color="gray", lw=0.4, ls=":")
    ax.axvspan(200, 220, color="#E8863A", alpha=0.15, lw=0)
    ax.set_xlabel("(a) Reward trajectory + components", fontsize=10)
    ax.set_ylabel("Episode reward", fontsize=9)
    paper_legend(ax, fontsize=8, ncol=4, loc="lower right")

    # (b) Component dominance (% of |total|)
    ax = fig.add_subplot(gs[1, 0])
    abs_rf = np.abs(rc["r_f"]) * 100  # paper-scale
    abs_rh = np.abs(rc["r_h"])
    abs_rd = np.abs(rc["r_d"])
    total = abs_rf + abs_rh + abs_rd + 1e-12
    ax.stackplot(ep, abs_rf / total, abs_rh / total, abs_rd / total,
                 labels=[r"$|r_f|$ (paper-scale)", r"$|r_h|$", r"$|r_d|$"],
                 colors=[COLOR_FREQ, COLOR_INERTIA, COLOR_DROOP], alpha=0.7)
    ax.set_xlabel("(b) Reward |component| share — who dominates loss?", fontsize=10)
    ax.set_ylabel("Fraction", fontsize=9)
    ax.set_ylim(0, 1)
    paper_legend(ax, fontsize=7.5, loc="upper right", ncol=3)

    # (c) Alpha (entropy temperature) — is exploration dying?
    ax = fig.add_subplot(gs[1, 1])
    ax.plot(ep, alpha, color="#8B0000", lw=1.2)
    ax.set_xlabel("(c) SAC α (entropy temperature)", fontsize=10)
    ax.set_ylabel("α", fontsize=9)
    ax.axhline(0.1, color="gray", lw=0.5, ls="--")
    ax.text(n * 0.02, 0.11, "α=0.1 (low-explore threshold)",
            fontsize=7, color="gray")
    ax.set_yscale("log")

    # (d) Action saturation rate
    ax = fig.add_subplot(gs[2, 0])
    plot_band(ax, ep, dH_clip, "#E8548A", r"$\Delta H$ clip rate", window=win)
    plot_band(ax, ep, dD_clip, "#4A90D9", r"$\Delta D$ clip rate", window=win)
    ax.axhline(0.10, color="red", lw=0.5, ls="--")
    ax.text(n * 0.02, 0.12, "10% (action range too narrow alarm)",
            fontsize=7, color="red")
    ax.set_xlabel("(d) Action clip rate (saturation)", fontsize=10)
    ax.set_ylabel("Clip fraction", fontsize=9)
    ax.set_ylim(0, max(0.4, np.nanmax(dH_clip[~np.isnan(dH_clip)]) * 1.2 if (~np.isnan(dH_clip)).any() else 0.4))
    paper_legend(ax, fontsize=7.5, loc="upper right")

    # (e) Action magnitude (using which fraction of allowed range?)
    ax = fig.add_subplot(gs[2, 1])
    plot_band(ax, ep, dH_abs, "#E8548A", r"$|\Delta H|$ mean", window=win)
    plot_band(ax, ep, dD_abs, "#4A90D9", r"$|\Delta D|$ mean", window=win)
    # config.py says DH range = [-16.1, +72] → effective half-range ~44; DD = [-14, +54] → ~34
    ax.axhline(72.0, color="#E8548A", lw=0.4, ls=":")
    ax.axhline(54.0, color="#4A90D9", lw=0.4, ls=":")
    ax.text(n * 0.02, 73, "ΔH max=72", fontsize=7, color="#E8548A")
    ax.text(n * 0.02, 55, "ΔD max=54", fontsize=7, color="#4A90D9")
    ax.set_xlabel("(e) Action magnitude vs config max", fontsize=10)
    ax.set_ylabel("|action|", fontsize=9)
    paper_legend(ax, fontsize=7.5, loc="center right")

    # (f) Critic / policy loss
    ax = fig.add_subplot(gs[3, 0])
    ax.plot(ep, critic_loss, color="#2E8B57", lw=1.0, label="critic")
    ax2 = ax.twinx()
    ax2.plot(ep, policy_loss, color="#6A0DAD", lw=1.0, label="policy")
    ax.set_xlabel("(f) SAC training losses", fontsize=10)
    ax.set_ylabel("critic loss", fontsize=9, color="#2E8B57")
    ax2.set_ylabel("policy loss", fontsize=9, color="#6A0DAD")
    ax.tick_params(axis="y", labelcolor="#2E8B57")
    ax2.tick_params(axis="y", labelcolor="#6A0DAD")

    # (g) Physics: max freq deviation + settled rate
    ax = fig.add_subplot(gs[3, 1])
    plot_band(ax, ep, max_freq, "#D2691E", r"max $|\Delta f|$ (Hz)", window=win)
    ax.axhline(0.5, color="red", lw=0.4, ls="--")
    ax.text(n * 0.02, 0.51, "0.5 Hz (UFLS threshold)",
            fontsize=7, color="red")
    ax2 = ax.twinx()
    settled_smooth = np.convolve(settled, np.ones(win) / win, mode="same")
    ax2.plot(ep, settled_smooth, color="#1B5E20", lw=1.0, ls="--",
             label="settled rate (rolling)")
    ax2.set_ylim(-0.05, 1.05)
    ax2.set_ylabel("settled fraction", fontsize=9, color="#1B5E20")
    ax2.tick_params(axis="y", labelcolor="#1B5E20")
    ax.set_xlabel("(g) Physics: max Δf + settled rate", fontsize=10)
    ax.set_ylabel("max |Δf| Hz", fontsize=9, color="#D2691E")
    ax.tick_params(axis="y", labelcolor="#D2691E")

    fig.suptitle(
        f"Model health diagnostic — {rd.name} ({n} ep, peak shaded ep 200-220)",
        fontsize=11, y=0.985,
    )
    save_fig(fig, str(OUT_DIR), "diag_model_health.png")

    # ── Numeric problem signals ──
    print("\n=== Problem signals (numeric) ===")
    last_50 = slice(max(0, n - 50), n)
    first_50 = slice(0, min(50, n))

    def _stat(name, arr, fmt=":.4f"):
        v = arr[~np.isnan(arr)] if arr.dtype.kind == "f" else arr
        if v.size == 0:
            return f"  {name}: ALL NaN"
        return f"  {name}: mean={float(v.mean()):{fmt[1:]}}  std={float(v.std()):{fmt[1:]}}  min={float(v.min()):{fmt[1:]}}  max={float(v.max()):{fmt[1:]}}"

    print("Action saturation (last 50 ep):")
    print(_stat("ΔH clip rate", dH_clip[last_50]))
    print(_stat("ΔD clip rate", dD_clip[last_50]))
    print(f"  ΔH clip > 0 episodes: {int((dH_clip > 0).sum())}/{n}")
    print(f"  ΔD clip > 0 episodes: {int((dD_clip > 0).sum())}/{n}")

    print("\nAction magnitude usage (last 50 ep, vs max):")
    last_dH = dH_abs[last_50]
    last_dD = dD_abs[last_50]
    print(f"  |ΔH| mean / max = {np.nanmean(last_dH):.2f} / 72.0 = "
          f"{np.nanmean(last_dH)/72.0*100:.1f}% of allowed range")
    print(f"  |ΔD| mean / max = {np.nanmean(last_dD):.2f} / 54.0 = "
          f"{np.nanmean(last_dD)/54.0*100:.1f}% of allowed range")

    print("\nReward component dominance:")
    rf_share = np.nanmean(np.abs(rc["r_f"][last_50]) * 100)
    rh_share = np.nanmean(np.abs(rc["r_h"][last_50]))
    rd_share = np.nanmean(np.abs(rc["r_d"][last_50]))
    tot = rf_share + rh_share + rd_share + 1e-12
    print(f"  |r_f|·100  share = {rf_share/tot*100:.1f}%")
    print(f"  |r_h|      share = {rh_share/tot*100:.1f}%")
    print(f"  |r_d|      share = {rd_share/tot*100:.1f}%")

    print("\nExploration:")
    a_first = np.nanmean(alpha[first_50])
    a_last = np.nanmean(alpha[last_50])
    print(f"  α first 50 mean: {a_first:.4f}")
    print(f"  α last  50 mean: {a_last:.4f}")
    print(f"  α decay ratio: {a_last/a_first*100:.1f}% of initial")

    print("\nReward trajectory:")
    print(f"  R first 50 mean: {np.nanmean(rewards[first_50]):+.4f}")
    print(f"  R peak ep 200-220: {np.nanmean(rewards[200:220]):+.4f}")
    print(f"  R last  50 mean: {np.nanmean(rewards[last_50]):+.4f}")
    print(f"  Regression from peak: "
          f"{(np.nanmean(rewards[200:220]) - np.nanmean(rewards[last_50])):+.4f} "
          f"({abs(np.nanmean(rewards[last_50]) - np.nanmean(rewards[200:220]))/abs(np.nanmean(rewards[200:220]))*100:.1f}%)")

    print("\nPhysics:")
    print(f"  max |Δf| last 50 ep: {np.nanmean(max_freq[last_50]):.3f} Hz "
          f"(UFLS threshold 0.5 Hz; over-threshold rate "
          f"{int((max_freq > 0.5).sum())}/{n})")
    print(f"  settled rate last 50 ep: {np.nanmean(settled[last_50])*100:.0f}%")

    print("\nLoss stability (last 50 vs first 50 ratio):")
    print(f"  critic loss ratio: {np.nanmean(critic_loss[last_50])/np.nanmean(critic_loss[first_50]):.2f}×")
    print(f"  policy loss ratio: {np.nanmean(policy_loss[last_50])/np.nanmean(policy_loss[first_50]):.2f}×")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="trial3", choices=list(RUN_DIRS.keys()))
    args = ap.parse_args()
    main(args.run)
