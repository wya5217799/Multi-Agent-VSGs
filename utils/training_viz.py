"""Training diagnostics visualizer for Multi-Agent VSG training runs.

Usage:
    python -m utils.training_viz results/sim_kundur/logs/training_log.json
    python -m utils.training_viz results/sim_kundur/logs/training_log.json -o summary.png

Reads:
    training_log.json  — episode_rewards, eval_rewards, critic_losses, policy_losses,
                         alphas, physics_summary (optional)
    monitor_data.csv   — reward components, action stats (optional, auto-detected
                         if present in same directory as training_log.json)

Produces:
    2x2 PNG diagnostic figure (+ optional 3rd row if physics_summary present)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Optional

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

try:
    from plotting.paper_style import (
        rolling_stats, COLOR_TOTAL, COLOR_FREQ, COLOR_INERTIA, COLOR_DROOP,
        apply_ieee_style, save_fig,
    )
    _HAS_PAPER_STYLE = True
except ImportError:
    _HAS_PAPER_STYLE = False

_C_TOTAL    = COLOR_TOTAL    if _HAS_PAPER_STYLE else "#8B3A3A"
_C_FREQ     = COLOR_FREQ     if _HAS_PAPER_STYLE else "#D2691E"
_C_INERTIA  = COLOR_INERTIA  if _HAS_PAPER_STYLE else "#2E8B57"
_C_DROOP    = COLOR_DROOP    if _HAS_PAPER_STYLE else "#6A0DAD"
_C_EVAL     = "#2171B5"
_C_SETTLED  = "#2CA02C"
_C_UNSETTLED = "#D62728"

_WINDOW = 50


def _rolling(data: list, window: int = _WINDOW):
    if _HAS_PAPER_STYLE:
        return rolling_stats(np.array(data), window)
    arr = np.array(data)
    n = len(arr)
    w = min(window, n)
    # Reflect-pad to avoid zero-fill bias at boundaries, then convolve valid
    half = w // 2
    padded = np.pad(arr, (half, half), mode="reflect")
    mean = np.convolve(padded, np.ones(w) / w, mode="valid")[:n]
    std = np.array([
        np.std(arr[max(0, i - half):min(n, i + half + 1)])
        for i in range(n)
    ])
    return mean, std


def _load_log(log_path: str) -> dict:
    try:
        with open(log_path) as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"[training_viz] {log_path} is not valid JSON (truncated write?): {exc}"
        ) from exc


def _load_monitor_csv(log_path: str) -> Optional[dict]:
    """Auto-detect and load monitor_data.csv from same dir as training_log.json."""
    csv_path = Path(log_path).parent / "monitor_data.csv"
    if not csv_path.exists():
        return None
    try:
        rows = []
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        if not rows:
            return None
        result: dict = {k: [] for k in rows[0]}
        for row in rows:
            for k, v in row.items():
                try:
                    result[k].append(float(v))
                except ValueError:
                    result[k].append(v)
        return result
    except Exception:
        return None


def plot_training_summary(
    log_path: str,
    save_path: Optional[str] = None,
    compare_paths: Optional[list] = None,
    show: bool = False,
) -> str:
    """Generate 2x2 (+ optional physics row) diagnostic PNG.

    Args:
        log_path: Path to training_log.json
        save_path: Output PNG path. Defaults to <log_dir>/../training_summary.png
        compare_paths: Reserved for future multi-run comparison. Not implemented.
        show: If True, call plt.show() (blocks; for interactive use only).

    Returns:
        Path to saved PNG.
    """
    if compare_paths is not None:
        raise NotImplementedError(
            "compare_paths is not yet implemented. "
            "Call plot_training_summary() separately for each run."
        )

    if _HAS_PAPER_STYLE:
        apply_ieee_style()

    log = _load_log(log_path)
    mon = _load_monitor_csv(log_path)

    rewards = log.get("episode_rewards", [])
    eval_rewards = log.get("eval_rewards", [])
    critic_losses = log.get("critic_losses", [])
    alphas = log.get("alphas", [])
    physics = log.get("physics_summary", [])

    n_ep = len(rewards)
    episodes = np.arange(n_ep)

    n_physics = len(physics)
    has_physics = n_physics == n_ep and n_ep > 0
    if 0 < n_physics < n_ep:
        print(
            f"[training_viz] WARNING: physics_summary has {n_physics} entries "
            f"but episode_rewards has {n_ep}. Physics row omitted "
            f"(resume from pre-physics log?)."
        )
    has_components = mon is not None and "r_f" in mon and len(mon.get("r_f", [])) > 0
    has_action_stats = mon is not None and "action_std_agent_0" in mon

    n_rows = 3 if has_physics else 2
    fig = plt.figure(figsize=(12, 4 * n_rows))
    gs = gridspec.GridSpec(n_rows, 2, figure=fig, hspace=0.45, wspace=0.35)

    # (a) Episode reward
    ax_r = fig.add_subplot(gs[0, 0])
    ax_r.scatter(episodes, rewards, s=2, alpha=0.25, color=_C_TOTAL, label="_nolegend_")
    if n_ep >= _WINDOW:
        mean_r, std_r = _rolling(rewards)
        ax_r.fill_between(episodes, mean_r - std_r, mean_r + std_r,
                          color=_C_TOTAL, alpha=0.15)
        ax_r.plot(episodes, mean_r, color=_C_TOTAL, lw=1.6,
                  label=f"Reward (avg{_WINDOW})")
    if eval_rewards:
        eval_ep = [e["episode"] for e in eval_rewards]
        eval_val = [e["reward"] for e in eval_rewards]
        ax_r.scatter(eval_ep, eval_val, s=30, color=_C_EVAL, zorder=5,
                     marker="^", label="Eval reward")
        best_idx = int(np.argmax(eval_val))
        ax_r.annotate(f"best\n{eval_val[best_idx]:.0f}",
                      xy=(eval_ep[best_idx], eval_val[best_idx]),
                      xytext=(8, 8), textcoords="offset points", fontsize=7,
                      color=_C_EVAL)
    ax_r.set_xlabel("Episode")
    ax_r.set_ylabel("Mean reward")
    ax_r.set_title("(a) Episode Reward")
    ax_r.legend(fontsize=7)

    # (b) Reward components
    ax_c = fig.add_subplot(gs[0, 1])
    if has_components:
        comp_ep = np.arange(len(mon["r_f"]))
        for key, color, label in [
            ("r_f", _C_FREQ,    r"$r_f$ (freq sync)"),
            ("r_h", _C_INERTIA, r"$r_h$ (inertia cost)"),
            ("r_d", _C_DROOP,   r"$r_d$ (damping cost)"),
        ]:
            vals = [abs(v) for v in mon.get(key, [])]
            if vals and len(vals) == len(comp_ep):
                w = min(_WINDOW, len(vals))
                mean_v, _ = _rolling(vals, w)
                ax_c.plot(comp_ep, mean_v, color=color, lw=1.4, label=label)
        ax_c.set_xlabel("Episode")
        ax_c.set_ylabel("|reward component|")
        ax_c.set_title("(b) Reward Components")
        ax_c.legend(fontsize=7)
    else:
        ax_c.text(0.5, 0.5, "No monitor_data.csv\n(run with monitor export enabled)",
                  ha="center", va="center", transform=ax_c.transAxes, fontsize=9,
                  color="gray")
        ax_c.set_title("(b) Reward Components — No Data")

    # (c) SAC loss & alpha
    ax_l = fig.add_subplot(gs[1, 0])
    if critic_losses:
        c_ep = np.arange(len(critic_losses))
        w = min(_WINDOW, len(critic_losses))
        mean_cl, _ = _rolling(critic_losses, w)
        ax_l.plot(c_ep, mean_cl, color=_C_FREQ, lw=1.4, label="Critic loss")
    if alphas:
        ax_a = ax_l.twinx()
        a_ep = np.arange(len(alphas))
        w = min(_WINDOW, len(alphas))
        mean_al, _ = _rolling(alphas, w)
        ax_a.plot(a_ep, mean_al, color=_C_INERTIA, lw=1.2, ls="--",
                  label="Alpha (entropy)")
        ax_a.set_ylabel("Alpha", color=_C_INERTIA, fontsize=8)
        ax_a.tick_params(axis="y", labelcolor=_C_INERTIA, labelsize=7)
        ax_a.legend(fontsize=7, loc="upper right")
    ax_l.set_xlabel("Episode")
    ax_l.set_ylabel("Critic loss", fontsize=8)
    ax_l.set_title("(c) SAC Loss & Entropy")
    ax_l.legend(fontsize=7, loc="upper left")

    # (d) Action statistics
    ax_act = fig.add_subplot(gs[1, 1])
    if has_action_stats:
        std_keys = [k for k in mon if k.startswith("action_std_agent_")]
        if std_keys:
            stds = np.mean([[float(v) for v in mon[k]] for k in std_keys], axis=0)
            act_ep = np.arange(len(stds))
            w = min(_WINDOW, len(stds))
            mean_std, _ = _rolling(stds.tolist(), w)
            ax_act.plot(act_ep, mean_std, color=_C_TOTAL, lw=1.4,
                        label="Action std (mean agents)")
        if "saturation_ratio" in mon:
            ax_sat = ax_act.twinx()
            sat = mon["saturation_ratio"]
            w = min(_WINDOW, len(sat))
            mean_sat, _ = _rolling(sat, w)
            ax_sat.plot(np.arange(len(sat)), mean_sat, color=_C_DROOP,
                        lw=1.0, ls=":", label="Saturation ratio")
            ax_sat.set_ylabel("Saturation ratio", color=_C_DROOP, fontsize=8)
            ax_sat.tick_params(axis="y", labelcolor=_C_DROOP, labelsize=7)
            ax_sat.set_ylim(0, 1)
            ax_sat.legend(fontsize=7, loc="upper right")
        ax_act.set_xlabel("Episode")
        ax_act.set_ylabel("Action std")
        ax_act.set_title("(d) Action Statistics")
        ax_act.legend(fontsize=7, loc="upper left")
    else:
        ax_act.text(0.5, 0.5, "No monitor_data.csv",
                    ha="center", va="center", transform=ax_act.transAxes,
                    fontsize=9, color="gray")
        ax_act.set_title("(d) Action Statistics — No Data")

    # (e) Physics summary (optional 3rd row, spans both columns)
    if has_physics:
        ax_ph = fig.add_subplot(gs[2, :])
        phys_ep = np.arange(len(physics))
        max_f = [p["max_freq_dev_hz"] for p in physics]
        mean_f = [p["mean_freq_dev_hz"] for p in physics]
        settled = [p["settled"] for p in physics]

        w = min(_WINDOW, len(max_f))
        mean_mf, _ = _rolling(max_f, w)
        mean_af, _ = _rolling(mean_f, w)

        ax_ph.plot(phys_ep, mean_mf, color=_C_FREQ, lw=1.4,
                   label=r"Max $\Delta f$ (Hz)")
        ax_ph.plot(phys_ep, mean_af, color=_C_INERTIA, lw=1.0, ls="--",
                   label=r"Mean $\Delta f$ (Hz)")
        ax_ph.axhline(0.1, color="gray", lw=0.8, ls=":",
                      label="0.1 Hz settled threshold")

        unsettled_ep = [i for i, s in enumerate(settled) if not s]
        if unsettled_ep:
            unsettled_f = [max_f[i] for i in unsettled_ep]
            ax_ph.scatter(unsettled_ep, unsettled_f, s=4, color=_C_UNSETTLED,
                          alpha=0.4, label="Not settled", zorder=3)

        settled_rate = sum(settled) / max(len(settled), 1)
        ax_ph.set_title(
            f"(e) Frequency Deviation  —  settled rate: {settled_rate:.1%}"
        )
        ax_ph.set_xlabel("Episode")
        ax_ph.set_ylabel(r"$\Delta f$ (Hz)")
        ax_ph.legend(fontsize=7, ncol=4)

    run_name = Path(log_path).parent.parent.name
    fig.suptitle(f"Training Diagnostics — {run_name}  ({n_ep} episodes)",
                 fontsize=11)

    if save_path is None:
        save_path = str(Path(log_path).parent.parent / "training_summary.png")
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)
    print(f"[training_viz] Saved: {save_path}")
    return save_path


def _parse_args():
    p = argparse.ArgumentParser(description="Generate training diagnostic plot")
    p.add_argument("log_path", help="Path to training_log.json")
    p.add_argument("-o", "--output", default=None, help="Output PNG path")
    p.add_argument("--show", action="store_true",
                   help="Display plot interactively")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    out = plot_training_summary(args.log_path, save_path=args.output, show=args.show)
    print(f"Done: {out}")
