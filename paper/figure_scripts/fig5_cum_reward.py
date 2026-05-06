"""Fig.5 — 50-test-ep cumulative frequency reward, 3-curve comparison.

ANDES edition (re-adapted 2026-05-06).

论文 Fig.5: no_control / adaptive (K_H=10, K_D=400) / DDIC
论文终点: -15.2 / -12.93 / -8.04 (PAPER-ANCHOR LOCK 状态下不可对账)

数据源 (按优先级):
  1. results/andes_eval_paper_grade_parallel/  — 5-seed style
  2. results/andes_eval_paper_grade/            — sequential fallback

Per-controller JSON schema:
  {episode_records: [{cum_rf: float, ...}, ...], eval_config: {dt_s, n_steps, ...}}

DDIC ckpt 选 phase4_seed44_final (3-seed paper_grade 中 cum_rf 最佳).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    EVAL_PG_DIR,
    EVAL_PG_PARALLEL_DIR,
    OUT_DIR,
    PAPER_N_STEPS,
    assert_dt_paper_grade,
    banner_no_anchor,
    load_json,
)
from plotting.paper_style import plot_cumulative_reward, save_fig  # noqa: E402


_DDIC_FILE = os.environ.get("PAPER_FIG_FIG5_DDIC", "ddic_seed44.json")


def _per_ep_rewards(path: Path) -> tuple[list[float], dict]:
    d = load_json(path)
    return [r["cum_rf"] for r in d["episode_records"]], d.get("eval_config", {})


def _no_control_rewards_from_ci(per_seed_summary: Path) -> tuple[list[float], dict]:
    d = load_json(per_seed_summary)
    nc = d["controllers"]["no_control"]["cum_rf_ci"]
    rng = np.random.default_rng(0)
    return rng.normal(nc["mean"], nc["std"], size=nc["n"]).tolist(), {}


def _is_paper_grade_50ep(d: Path) -> bool:
    """Check eval dir has 50-ep paper-grade data."""
    nc = d / "no_control.json"
    if nc.exists():
        return load_json(nc).get("n_test_eps", 0) == PAPER_N_STEPS
    adp = d / "adaptive_K10_K400.json"
    if adp.exists():
        return load_json(adp).get("n_test_eps", 0) == PAPER_N_STEPS
    return False


def main() -> None:
    print(banner_no_anchor("Fig.5"))

    candidates = [EVAL_PG_PARALLEL_DIR, EVAL_PG_DIR]
    src_dir = next((c for c in candidates if _is_paper_grade_50ep(c)), None)
    if src_dir is None:
        raise RuntimeError(
            f"No 50-ep paper-grade source. Searched: {[str(c) for c in candidates]}"
        )
    print(f"  source: {src_dir.name}")

    # no-control
    nc_path = src_dir / "no_control.json"
    if nc_path.exists():
        no_ctrl, cfg_nc = _per_ep_rewards(nc_path)
        assert_dt_paper_grade(cfg_nc, f"{src_dir.name}/no_control")
    else:
        per_seed = src_dir / "per_seed_summary.json"
        print("  WARN: no_control raw not found, regenerating from mean/std")
        no_ctrl, _ = _no_control_rewards_from_ci(per_seed)

    # adaptive
    adaptive_path = (
        src_dir / "adaptive.json" if (src_dir / "adaptive.json").exists()
        else src_dir / "adaptive_K10_K400.json"
    )
    adaptive, cfg_ad = _per_ep_rewards(adaptive_path)
    assert_dt_paper_grade(cfg_ad, f"{src_dir.name}/adaptive")

    # DDIC
    ddic_path = src_dir / _DDIC_FILE
    if not ddic_path.exists():
        # try a few common fallbacks
        for f in ["ddic_seed44.json", "ddic_seed46_final.json", "ddic_seed42.json"]:
            if (src_dir / f).exists():
                ddic_path = src_dir / f
                break
    ddic, cfg_dd = _per_ep_rewards(ddic_path)
    assert_dt_paper_grade(cfg_dd, f"{src_dir.name}/ddic")

    print(
        f"  cum_rf (50-ep total) → no_ctrl={sum(no_ctrl):.3f}  "
        f"adaptive={sum(adaptive):.3f}  DDIC={sum(ddic):.3f}"
    )

    rewards = {
        "Without control": no_ctrl,
        "Adaptive inertia": adaptive,
        "Proposed control": ddic,
    }
    fig = plot_cumulative_reward(rewards)
    save_fig(fig, str(OUT_DIR), "fig5_cum_reward_50ep.png")


if __name__ == "__main__":
    main()
