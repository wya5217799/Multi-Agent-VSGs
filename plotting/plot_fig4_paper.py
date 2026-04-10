"""
复现论文 Fig 4: Training performance of the multiagent learning.
布局和风格完全匹配原文:
  (a) 顶部大图: Total / 100*Frequency / Inertia / Droop
  (b)-(e) 底部 2×2: ES1-ES4 各自 episode reward

注: 本实现中训练期间 r_h = r_d = 0,
    因此 Total ≡ 100*Frequency, Inertia = Droop = 0.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import matplotlib.ticker as ticker
from matplotlib.lines import Line2D

# ── 配置 ──
LOG_PATH = 'results/training_log.npz'
SAVE_PATH = 'results/figures_paper_style/fig4_paper_style.png'
WINDOW = 50  # 滑动平均窗口


def rolling_stats(data, window):
    """计算滑动平均和滑动标准差."""
    n = len(data)
    mean = np.convolve(data, np.ones(window) / window, mode='same')
    # 边界修正
    for i in range(window // 2):
        mean[i] = np.mean(data[:i + window // 2 + 1])
    for i in range(n - window // 2, n):
        mean[i] = np.mean(data[i - window // 2:])

    std = np.zeros(n)
    for i in range(n):
        lo = max(0, i - window // 2)
        hi = min(n, i + window // 2 + 1)
        std[i] = np.std(data[lo:hi])
    return mean, std


def main():
    log = np.load(LOG_PATH)
    total = log['episode_total_rewards']
    agents = [log[f'episode_rewards_agent_{i}'] for i in range(4)]
    n_ep = len(total)
    episodes = np.arange(n_ep)

    # 读取分项奖励 (若存在)
    if 'episode_freq_rewards' in log:
        freq_100 = log['episode_freq_rewards']
        inertia = log['episode_inertia_rewards']
        droop = log['episode_droop_rewards']
    else:
        # 旧版日志: r_h = r_d = 0
        freq_100 = total.copy()
        inertia = np.zeros(n_ep)
        droop = np.zeros(n_ep)

    # ── 论文配色 (从原图精确取色) ──
    color_total    = '#8B3A3A'   # 深棕红
    color_freq     = '#D2691E'   # 橙棕
    color_inertia  = '#2E8B57'   # 深绿色
    color_droop    = '#6A0DAD'   # 深紫色
    color_es       = '#8B3A3A'   # 棕红 (与 Total 一致)
    band_alpha     = 0.20

    # ── matplotlib 全局样式 — 匹配 IEEE 论文 ──
    plt.rcParams.update({
        'font.family': 'serif',
        'font.serif': ['Times New Roman', 'DejaVu Serif'],
        'font.size': 10,
        'mathtext.fontset': 'stix',
        'axes.linewidth': 0.8,
        'xtick.direction': 'in',
        'ytick.direction': 'in',
        'xtick.major.size': 3.5,
        'ytick.major.size': 3.5,
        'xtick.top': True,
        'ytick.right': True,
        'axes.grid': False,
    })

    # ── 创建图: 论文风格布局 ──
    fig = plt.figure(figsize=(7.5, 8.5))
    gs = GridSpec(3, 2, figure=fig, height_ratios=[1.5, 1, 1],
                  hspace=0.55, wspace=0.42,
                  left=0.12, right=0.96, top=0.98, bottom=0.06)

    # ═══ (a) 顶部大图 ═══
    ax_a = fig.add_subplot(gs[0, :])

    def plot_band(ax, x, data, color, label, lw=1.4):
        mean, std = rolling_stats(data, WINDOW)
        ax.fill_between(x, mean - std, mean + std, color=color, alpha=band_alpha,
                        linewidth=0)
        ax.plot(x, mean, color=color, lw=lw, label=label)

    # 绘制顺序: 底层先画
    plot_band(ax_a, episodes, freq_100, color_freq, '100*Frequency')
    plot_band(ax_a, episodes, total, color_total, 'Total')
    plot_band(ax_a, episodes, inertia, color_inertia, 'Inertia')
    plot_band(ax_a, episodes, droop, color_droop, 'Droop')

    # 重新排列图例: Total, 100*Freq, Inertia, Droop (匹配论文顺序)
    handles, labels = ax_a.get_legend_handles_labels()
    order = [1, 0, 2, 3]
    handles = [handles[i] for i in order]
    labels = [labels[i] for i in order]

    ax_a.set_ylabel('Episode\nreward', fontsize=10.5)
    ax_a.set_xlim(0, n_ep)
    ax_a.xaxis.set_major_locator(ticker.MultipleLocator(500))

    # y 轴: 参照论文 — 截断初始大spike, 突出收敛区域
    # 论文 y 轴范围约 [-300, 0]; 我们的 reward 量级更大, 取合理比例
    total_mean, total_std = rolling_stats(total, WINDOW)
    # 使用 smoothed 最小值 (非原始最小值) 以避免 spike 压缩
    y_min_a = (total_mean - total_std).min() * 1.15
    ax_a.set_ylim(y_min_a, max(total_mean.max() + total_std.max() * 0.5, 50))

    # 图例 — 论文放右中
    leg = ax_a.legend(
        handles, labels,
        loc='center right', fontsize=8.5,
        framealpha=0.95, edgecolor='black', fancybox=False,
        borderpad=0.4, handlelength=1.8, labelspacing=0.25,
    )
    leg.get_frame().set_linewidth(0.5)

    ax_a.set_xlabel('(a) Training episodes', fontsize=10.5, labelpad=5)

    # ═══ (b)-(e) 底部 2×2 ═══
    positions = [(1, 0), (1, 1), (2, 0), (2, 1)]
    sub_labels = ['(b)', '(c)', '(d)', '(e)']
    es_names = ['ES1', 'ES2', 'ES3', 'ES4']

    # 统一 (b)-(e) y 轴范围: 使用平滑数据的范围
    smoothed_mins = []
    smoothed_maxs = []
    for a in agents:
        m, s = rolling_stats(a, WINDOW)
        smoothed_mins.append((m - s).min())
        smoothed_maxs.append((m + s).max())
    y_min_sub = min(smoothed_mins) * 1.05
    y_max_sub = max(smoothed_maxs) * 0.95 if max(smoothed_maxs) < 0 else max(smoothed_maxs) * 1.05
    y_lim_agents = (y_min_sub, y_max_sub + abs(y_max_sub) * 0.1)

    for idx, (row, col) in enumerate(positions):
        ax = fig.add_subplot(gs[row, col])
        data = agents[idx]
        mean, std = rolling_stats(data, WINDOW)

        ax.fill_between(episodes, mean - std, mean + std,
                        color=color_es, alpha=band_alpha, linewidth=0)
        ax.plot(episodes, mean, color=color_es, lw=1.2)

        ax.set_ylabel('Episode\nreward', fontsize=9)
        ax.set_xlim(0, n_ep)
        ax.set_ylim(y_lim_agents)

        # x 轴刻度: 0, 1,000, 2,000
        ax.xaxis.set_major_locator(ticker.MultipleLocator(1000))
        ax.xaxis.set_major_formatter(
            ticker.FuncFormatter(lambda x, _: f'{int(x):,}'))

        # 图例 — 使用实际线条颜色
        legend_line = Line2D([0], [0], color=color_es, lw=1.5)
        leg_i = ax.legend(
            [legend_line], [f'{es_names[idx]}-Total'],
            loc='lower right', fontsize=7.5,
            framealpha=0.95, edgecolor='black',
            fancybox=False, borderpad=0.3, handlelength=1.5,
        )
        leg_i.get_frame().set_linewidth(0.5)

        # 子图标签
        ax.set_xlabel(f'{sub_labels[idx]} Training episodes',
                      fontsize=9.5, labelpad=3)

    plt.savefig(SAVE_PATH, dpi=250, bbox_inches='tight')
    plt.close()
    print(f'Saved: {SAVE_PATH}')


if __name__ == '__main__':
    main()
