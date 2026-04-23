"""
生成 Fig 16: 可扩展性分析图 (维度/时间/性能对比)
================================================

**编号说明（N6 · 2026-04-21）**：
本图为项目自定义"Fig.16 可扩展性条形图"，**非论文 Fig.16 单线图**（论文 Fig.16
是改进 New England 系统的单线图）。项目 ODE 训练使用 `make_chain_BV(N=8)` 合成
链状拓扑，非论文真实 NE39 Kron 约化；拓扑差异见 `env/ode/NOTES.md` 「NE39 拓扑」节。

需要先完成 train_scalability.py 训练.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import json
import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    log_path = "results/scalability/scalability_log.json"
    if not os.path.exists(log_path):
        print("[ERROR] scalability_log.json not found. Run train_scalability.py first.")
        return 1

    with open(log_path) as f:
        data = json.load(f)

    N_list = []
    r_dist, r_cent = [], []
    for N in [2, 4, 8]:
        dk = f"N{N}_distributed"
        ck = f"N{N}_centralized"
        if dk in data and ck in data:
            N_list.append(N)
            r_dist.append(np.mean(data[dk][-100:]))
            r_cent.append(np.mean(data[ck][-100:]))

    if not N_list:
        print("[ERROR] No scalability data found.")
        return 1

    # 维度
    obs_dist = [7] * len(N_list)
    obs_cent = [n * 7 for n in N_list]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    fig.suptitle('Fig 16. Scalability analysis: Distributed MADRL vs. Centralized DRL',
                 fontsize=13, fontweight='bold')

    x = np.arange(len(N_list))
    w = 0.35

    # (a) 观测空间维度
    ax = axes[0]
    b1 = ax.bar(x - w/2, obs_cent, w, label='Centralized', color='#d62728', alpha=0.8)
    b2 = ax.bar(x + w/2, obs_dist, w, label='Distributed (per agent)', color='#1f77b4', alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f'N={n}' for n in N_list])
    ax.set_ylabel('Observation Dimension')
    ax.set_title('(a) Observation space')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis='y')
    for bar in b1:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f'{int(bar.get_height())}', ha='center', va='bottom', fontsize=9)
    for bar in b2:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f'{int(bar.get_height())}', ha='center', va='bottom', fontsize=9)

    # (b) 训练集数
    ax = axes[1]
    n_ep = len(data.get(f"N{N_list[0]}_distributed", []))
    ax.text(0.5, 0.6, f'Training: {n_ep} episodes each',
            ha='center', va='center', transform=ax.transAxes, fontsize=12)
    ax.text(0.5, 0.4, f'Distributed: N independent SAC agents\n'
            f'Centralized: 1 SAC with obs={N_list[-1]*7}, act={N_list[-1]*2}',
            ha='center', va='center', transform=ax.transAxes, fontsize=10, color='gray')
    ax.set_title('(b) Training configuration')
    ax.set_xticks([])
    ax.set_yticks([])

    # (c) 最终性能
    ax = axes[2]
    b1 = ax.bar(x - w/2, [-r for r in r_cent], w, label='Centralized DRL', color='#d62728', alpha=0.8)
    b2 = ax.bar(x + w/2, [-r for r in r_dist], w, label='Distributed MADRL', color='#1f77b4', alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f'N={n}' for n in N_list])
    ax.set_ylabel('Avg. Penalty (lower is better)')
    ax.set_title('(c) Final performance')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    save_path = 'results/figures/fig16_scalability_analysis.png'
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"Saved {save_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
