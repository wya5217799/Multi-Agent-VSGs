"""
从已有 scalability_log.json 重新绘制 Fig 14/15 (论文风格).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from plotting.paper_style import (apply_ieee_style, paper_legend, plot_band, rolling_stats,
                                  COLOR_DISTRIBUTED, COLOR_CENTRALIZED,
                                  COLOR_NO_CTRL, COLOR_PROPOSED)
from scenarios.scalability.train import compute_no_control_reward

apply_ieee_style()

LOG_PATH = 'results/scalability/scalability_log.json'
FIG_DIR = 'results/figures_paper_style'
os.makedirs(FIG_DIR, exist_ok=True)

with open(LOG_PATH) as f:
    data = json.load(f)

n_agents_list = [2, 4, 8]
methods = ['distributed', 'centralized']
labels = {'distributed': 'Proposed DRL', 'centralized': 'Centralized DRL'}
colors = {'distributed': COLOR_DISTRIBUTED, 'centralized': COLOR_CENTRALIZED}
sub_labels = ['(a)', '(b)', '(c)']

# ═══ Fig 14: 训练曲线对比 — 3×1 竖排 ═══
fig, axes = plt.subplots(3, 1, figsize=(6.5, 8.5))
fig.subplots_adjust(hspace=0.35, left=0.14, right=0.96, top=0.97, bottom=0.06)

for idx, N in enumerate(n_agents_list):
    ax = axes[idx]
    window = 50
    mean_mins, mean_maxs = [], []
    for method in methods:
        key = f"N{N}_{method}"
        if key not in data:
            continue
        r = np.array(data[key])
        plot_band(ax, np.arange(len(r)), r, colors[method], labels[method],
                  lw=1.5, window=window)
        m, s = rolling_stats(r, window=window)
        mean_mins.append(m.min())
        mean_maxs.append(m.max())

    # y 轴基于平滑均值范围, 留 30% 余量, 截掉 spike
    if mean_mins and mean_maxs:
        rng_span = max(mean_maxs) - min(mean_mins)
        y_lo = min(mean_mins) - rng_span * 0.3
        y_hi = max(mean_maxs) + rng_span * 0.3
        ax.set_ylim(y_lo, y_hi)

    ax.text(0.95, 0.92, f'$N={N}$', transform=ax.transAxes,
            fontsize=12, ha='right', va='top',
            bbox=dict(boxstyle='square,pad=0.3', fc='white', ec='black', lw=0.5))
    ax.set_ylabel('Episode reward', fontsize=10)
    ax.set_xlim(0, len(data[f'N{N}_distributed']))
    ax.xaxis.set_major_locator(mticker.MultipleLocator(500))
    paper_legend(ax, loc='lower right', fontsize=8)
    ax.set_xlabel(f'{sub_labels[idx]} Training episodes', fontsize=10, labelpad=3)

plt.savefig(os.path.join(FIG_DIR, 'fig14_scalability_training.png'),
            dpi=250, bbox_inches='tight')
plt.close()
print('Saved fig14_scalability_training.png')

# ═══ Fig 15: 累积奖励对比 — 3×1 竖排 ═══
cum_colors = {'distributed': COLOR_CENTRALIZED, 'centralized': COLOR_PROPOSED}
cum_labels = {'distributed': 'Proposed control', 'centralized': 'Centralized DRL control'}

fig, axes = plt.subplots(3, 1, figsize=(6.5, 9.5))
fig.subplots_adjust(hspace=0.35, left=0.14, right=0.96, top=0.97, bottom=0.06)

for idx, N in enumerate(n_agents_list):
    ax = axes[idx]

    # 真实无控制基线
    no_ctrl = compute_no_control_reward(N, n_test=50, seed=2000)
    ax.plot(range(50), np.cumsum(no_ctrl), color=COLOR_NO_CTRL, lw=2.0,
            label='without control')

    for method in methods:
        key = f"N{N}_{method}"
        if key not in data:
            continue
        test_rewards = np.array(data[key][-50:])
        ax.plot(range(50), np.cumsum(test_rewards), color=cum_colors[method],
                lw=2.0, label=cum_labels[method])

    ax.text(0.05, 0.08, f'$N={N}$', transform=ax.transAxes,
            fontsize=12, ha='left', va='bottom',
            bbox=dict(boxstyle='square,pad=0.3', fc='white', ec='black', lw=0.5))
    ax.set_ylabel('Cumulative\nreward', fontsize=10)
    ax.set_xlim(0, 49)
    ax.xaxis.set_major_locator(mticker.MultipleLocator(10))
    paper_legend(ax, loc='lower left', fontsize=8, handlelength=2.0)
    ax.set_xlabel(f'{sub_labels[idx]} Test episodes', fontsize=10, labelpad=3)

plt.savefig(os.path.join(FIG_DIR, 'fig15_scalability_cumulative.png'),
            dpi=250, bbox_inches='tight')
plt.close()
print('Saved fig15_scalability_cumulative.png')
