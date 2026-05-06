"""Fig.4 — Training performance (ANDES, paper Sec.IV-B).

Layout (paper Fig.4):
    (a) Total reward + per-agent agg
    (b)-(e) ES1-ES4 per-agent episode reward

Source data:
    results/<TRAIN_RUN>/training_log.json
    schema: {total_rewards: [...], episode_rewards: {"0":[...], "1":[...], ...}}

Defaults to `andes_phase4_noPHIabs_seed42` (has per-agent rewards).
Override via PAPER_FIG_TRAIN_RUN env var (rel-to-results name).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    ANDES_RESULTS,
    OUT_DIR,
    banner_no_anchor,
    load_json,
)
from plotting.paper_style import plot_training_curves, save_fig  # noqa: E402


def _resolve_train_log() -> Path:
    override = os.environ.get("PAPER_FIG_TRAIN_RUN", "")
    run = override or "andes_phase4_noPHIabs_seed42"
    p = ANDES_RESULTS / run / "training_log.json"
    if not p.exists():
        raise FileNotFoundError(f"training_log.json missing at {p}")
    return p


def main() -> None:
    print(banner_no_anchor("Fig.4"))
    log_path = _resolve_train_log()
    print(f"  source: {log_path.relative_to(ANDES_RESULTS.parent)}")

    d = load_json(log_path)
    total = np.asarray(d["total_rewards"], dtype=float)
    ep_rewards = d.get("episode_rewards", {})
    agents = []
    for i in range(4):
        key = str(i)
        if key in ep_rewards:
            agents.append(np.asarray(ep_rewards[key], dtype=float))
        else:
            print(f"  [WARN] agent {i} per-agent reward missing — degraded fig4(a) only")
            agents = []
            break

    fig = plot_training_curves(
        total_rewards=total,
        agent_rewards=agents,
        freq_rewards=None,
        inertia_rewards=None,
        droop_rewards=None,
        n_agents=4 if agents else 0,
        window=50,
    )
    save_fig(fig, str(OUT_DIR), "fig4_training_curves.png")


if __name__ == "__main__":
    main()
