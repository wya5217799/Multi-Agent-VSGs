"""R02 diagnostic — extract per-agent action trajectories and per-episode reward
from 5 R02 train logs. Produces 2 figures into paper/figures/r02_diag/:

  fig_r02_action_mu_traj.png  — 5 seed × 4 agent action mu over episodes (collapse signal)
  fig_r02_per_agent_reward.png — per-agent reward over episodes (dominance signal)

Pure log-parse, no env / agent runtime.
"""
from __future__ import annotations

import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUN_BASE = ROOT / "results" / "research_loop"
OUT_DIR = ROOT / "paper" / "figures" / "r02_diag"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SEEDS = [42, 43, 44, 45, 46]
ARMS = [f"r02_A_lam0p01_200ep_s{s}" for s in SEEDS]


def parse_action_mu(log_text):
    """All `Actions mu: [a, b, c, d]  std: [...]` lines, with episode if present."""
    pat = re.compile(r"Ep\s+(\d+)\s*\|.*?Actions mu:\s*\[([\-\d\.,\s]+)\]\s*std:\s*\[([\-\d\.,\s]+)\]",
                     re.DOTALL)
    eps, mus, stds = [], [], []
    for m in pat.finditer(log_text):
        ep = int(m.group(1))
        mu = [float(x.strip()) for x in m.group(2).split(",") if x.strip()]
        sd = [float(x.strip()) for x in m.group(3).split(",") if x.strip()]
        if len(mu) == 4 and len(sd) == 4:
            eps.append(ep); mus.append(mu); stds.append(sd)
    return np.array(eps), np.array(mus), np.array(stds)


def parse_per_agent_reward(log_text):
    """`Per-agent rewards: [a0: -X, a1: -Y, a2: -Z, a3: -W]` extraction.

    Uses the preceding `Ep N |` line as the episode tag.
    """
    pat = re.compile(
        r"Ep\s+(\d+)\s*\|.*?Per-agent rewards:\s*\[a0:\s*([\-\d\.]+),\s*a1:\s*([\-\d\.]+),\s*"
        r"a2:\s*([\-\d\.]+),\s*a3:\s*([\-\d\.]+)\]",
        re.DOTALL,
    )
    eps, rews = [], []
    for m in pat.finditer(log_text):
        ep = int(m.group(1))
        r = [float(m.group(i)) for i in (2, 3, 4, 5)]
        eps.append(ep); rews.append(r)
    return np.array(eps), np.array(rews)


def main():
    fig1, axes1 = plt.subplots(5, 1, figsize=(8, 12), sharex=True)
    fig2, axes2 = plt.subplots(5, 1, figsize=(8, 12), sharex=True)

    AGENT_COLORS = ["C0", "C1", "C2", "C3"]
    AGENT_LABELS = [
        "a0 (ES1@Bus7  far,  D=20)",
        "a1 (ES2@Bus8  far,  D=16)",
        "a2 (ES3@Bus10 LS1!, D=4)",
        "a3 (ES4@Bus9  LS2!, D=8)",
    ]

    for idx, (seed, arm) in enumerate(zip(SEEDS, ARMS)):
        log = RUN_BASE / f"{arm}.train.log"
        if not log.exists():
            print(f"[skip] {log}")
            continue
        text = log.read_text(encoding="utf-8", errors="ignore")

        eps, mu, sd = parse_action_mu(text)
        ax1 = axes1[idx]
        for a in range(4):
            ax1.plot(eps, mu[:, a], color=AGENT_COLORS[a], label=AGENT_LABELS[a], lw=1.0)
        ax1.set_ylabel(f"seed{seed}\naction mu")
        ax1.axhline(0.0, color="k", lw=0.5, ls="--")
        ax1.grid(alpha=0.3)
        ax1.set_ylim([-1, 1])
        if idx == 0:
            ax1.set_title("R02 200ep · per-agent action mu (mean of policy) over episodes\n"
                          "[期望: paper Fig.7 显示 ΔH 大正 mu>0, 项目却收敛到 mu<0 全负 = action collapse]")
        if idx == 4:
            ax1.legend(loc="lower right", fontsize=8, ncol=2)
            ax1.set_xlabel("Episode")

        eps_r, rews = parse_per_agent_reward(text)
        ax2 = axes2[idx]
        for a in range(4):
            ax2.plot(eps_r, rews[:, a], color=AGENT_COLORS[a], label=AGENT_LABELS[a], lw=0.8, alpha=0.7)
        ax2.set_ylabel(f"seed{seed}\nper-agent R")
        ax2.grid(alpha=0.3)
        if idx == 0:
            ax2.set_title("R02 200ep · per-agent reward per episode\n"
                          "[期望: 4 agent 均衡; 'agent close to disturbance dominates' 应表现为 a2/a3 (LS bus) 显著低于 a0/a1]")
        if idx == 4:
            ax2.legend(loc="lower right", fontsize=8, ncol=2)
            ax2.set_xlabel("Episode")

    fig1.tight_layout()
    fig2.tight_layout()
    fig1.savefig(OUT_DIR / "fig_r02_action_mu_traj.png", dpi=120, bbox_inches="tight")
    fig2.savefig(OUT_DIR / "fig_r02_per_agent_reward.png", dpi=120, bbox_inches="tight")
    print(f"wrote {OUT_DIR / 'fig_r02_action_mu_traj.png'}")
    print(f"wrote {OUT_DIR / 'fig_r02_per_agent_reward.png'}")


if __name__ == "__main__":
    main()
