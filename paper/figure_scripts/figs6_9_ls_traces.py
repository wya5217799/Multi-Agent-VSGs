"""Figs.6/7/8/9 — LS1/LS2 time-domain traces.

Ported from Multi-Agent VSGs (ANDES) sister repo, adapted for Simulink
discrete eval JSON schema (see evaluate_simulink._dump_episode_json).

论文 Fig.6: no-ctrl LS1 — 2 子图 (ΔP, Δf)
论文 Fig.7: DDIC LS1 — 4 子图 (ΔP, Δf, ΔH, ΔD + avg dashed)
论文 Fig.8: no-ctrl LS2 — 2 子图
论文 Fig.9: DDIC LS2 — 4 子图

数据源:
    paper/figure_scripts/_common.EVAL_SPEC_DIR
    = results/sim_kundur/runs/phase1_7_trial_3/eval/
    populated by evaluate_simulink.py --dump-eval-json.

Filenames consumed:
    no_control_load_step_{1,2}.json
    ddic_load_step_{1,2}.json
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import os
from _common import (  # noqa: E402
    OUT_DIR,
    banner_no_anchor, load_json, resolve_spec_dir,
)
EVAL_SPEC_DIR = resolve_spec_dir()
from plotting.paper_style import (  # noqa: E402
    apply_ieee_style,
    plot_time_domain_2x2,
    save_fig,
    paper_legend,
    ES_COLORS_4,
    ES_FREQ_LABELS_4,
    ES_LABELS_4,
)


# DDIC ckpt label override (ANDES has many ckpt variants).
# Default = phase3v2_seed44 (V1-trained, V2-env zero-shot, LS1 -6.2% / LS2 +9.4%).
_DDIC_LABEL = os.environ.get("PAPER_FIG_DDIC_LABEL", "ddic_phase3v2_seed44")


def _traces_to_arrays(d: dict) -> dict:
    traces = d["traces"]
    t = np.asarray([s["t"] for s in traces], dtype=float)
    freq_hz = np.asarray([s["freq_hz"] for s in traces], dtype=float)
    P_es = np.asarray([s["delta_P_es"] for s in traces], dtype=float)
    M_es = np.asarray([s["M_es"] for s in traces], dtype=float)
    D_es = np.asarray([s["D_es"] for s in traces], dtype=float)
    return {"time": t, "freq_hz": freq_hz, "P_es": P_es, "M_es": M_es, "D_es": D_es}


def _plot_no_control_2x1(traj: dict, fig_label: str, f_nom: float = 50.0):
    """论文 Fig.6/8 风格 2-row 时域图 (仅 ΔP, Δf)."""
    apply_ieee_style()
    fig, axes = plt.subplots(2, 1, figsize=(5.0, 4.5), sharex=True)
    fig.subplots_adjust(left=0.16, right=0.97, top=0.96, bottom=0.10, hspace=0.35)
    t = traj["time"]

    # (a) ΔP_es
    ax = axes[0]
    for i in range(4):
        ax.plot(t, traj["P_es"][:, i], color=ES_COLORS_4[i], lw=1.2, label=ES_LABELS_4[i])
    ax.set_ylabel(r"$\Delta P_{\mathrm{es}}$ (p.u.)", fontsize=9)
    ax.axhline(0, color="gray", lw=0.5, ls="--")
    paper_legend(ax, loc="best", fontsize=7, ncol=2)
    ax.set_xlabel(f"({fig_label}a) Time (s)", fontsize=9, labelpad=3)

    # (b) Δf_es
    ax = axes[1]
    for i in range(4):
        ax.plot(t, traj["freq_hz"][:, i] - f_nom, color=ES_COLORS_4[i], lw=1.2,
                label=ES_FREQ_LABELS_4[i])
    ax.set_ylabel(r"$\Delta f$ (Hz)", fontsize=9)
    ax.axhline(0, color="gray", lw=0.5, ls="--")
    paper_legend(ax, loc="best", fontsize=7, ncol=2)
    ax.set_xlabel(f"({fig_label}b) Time (s)", fontsize=9, labelpad=3)

    return fig


def _render_no_ctrl(scenario: str, fig_label: str, out_name: str) -> None:
    p = EVAL_SPEC_DIR / f"no_control_{scenario}.json"
    if not p.exists():
        print(f"  WARN: {p.name} missing — skip")
        return
    traj = _traces_to_arrays(load_json(p))
    fig = _plot_no_control_2x1(traj, fig_label=fig_label)
    save_fig(fig, str(OUT_DIR), out_name)


def _render_ddic(scenario: str, fig_label: str, out_name: str) -> None:
    p = EVAL_SPEC_DIR / f"{_DDIC_LABEL}_{scenario}.json"
    if not p.exists():
        print(f"  WARN: {p.name} missing — skip")
        return
    traj = _traces_to_arrays(load_json(p))
    fig = plot_time_domain_2x2(traj, n_agents=4, f_nom=50.0, fig_label=fig_label)
    save_fig(fig, str(OUT_DIR), out_name)


def _check_legacy_dt(traj: dict) -> None:
    t = traj["time"]
    if len(t) < 2:
        return
    dt = float(t[1] - t[0])
    duration = float(t[-1] - t[0])
    if abs(dt - 0.2) > 1e-3 or abs(duration - (50 - 1) * 0.2) > 0.5:
        print(f"  WARN LEGACY data: dt={dt:.2f}s  duration={duration:.1f}s "
              f"(paper expects dt=0.2s, episode=10s)")
        print(f"        Fig.6/7/8/9 shows relative dynamics (ranking ok), "
              f"magnitudes NOT comparable to paper")


def main() -> None:
    print(banner_no_anchor("Fig.6/7/8/9"))
    print(f"  data: {EVAL_SPEC_DIR}")

    # 先 sanity-check 一份
    sample = EVAL_SPEC_DIR / "no_control_load_step_1.json"
    if sample.exists():
        _check_legacy_dt(_traces_to_arrays(load_json(sample)))
    else:
        print(f"  [WARN] {sample.name} not found yet — run evaluate_simulink.py")

    _render_no_ctrl("load_step_1", "Fig6-", "fig6_nocontrol_ls1.png")
    _render_ddic("load_step_1", "Fig7-", "fig7_ddic_ls1.png")
    _render_no_ctrl("load_step_2", "Fig8-", "fig8_nocontrol_ls2.png")
    _render_ddic("load_step_2", "Fig9-", "fig9_ddic_ls2.png")


if __name__ == "__main__":
    main()
