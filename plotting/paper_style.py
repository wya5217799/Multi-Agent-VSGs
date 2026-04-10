"""
论文 IEEE 风格绘图模块 — 共享配色、字体、布局、通用绘图函数.
Yang et al., TPWRS 2023 复现.

使用方法:
    from plotting.paper_style import *

通用绘图函数:
    plot_time_domain_2x2()   — Fig 6-9, 11, 13, 18-21 时域仿真 2×2
    plot_cumulative_reward() — Fig 5, 10, 12, 15 累积奖励对比
    plot_training_curves()   — Fig 4, 17 训练曲线 (顶部大图 + 底部 agent 子图)
    plot_freq_comparison()   — Fig 21 频率对比 (RL vs no-ctrl)
"""
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D

# ═══════════════════════════════════════════════════════════
#  论文精确配色 (从原图取色)
# ═══════════════════════════════════════════════════════════

# Fig 6-9: 4-agent ES 颜色 (与论文 Fig 6 一致)
ES_COLORS_4 = ['#E8548A', '#F5A623', '#36D7B7', '#4A90D9']
ES_LABELS_4 = [r'$\Delta\,P_{\mathrm{es}1}$', r'$\Delta\,P_{\mathrm{es}2}$',
               r'$\Delta\,P_{\mathrm{es}3}$', r'$\Delta\,P_{\mathrm{es}4}$']
ES_FREQ_LABELS_4 = [r'$\Delta\,f_{\mathrm{es}1}$', r'$\Delta\,f_{\mathrm{es}2}$',
                     r'$\Delta\,f_{\mathrm{es}3}$', r'$\Delta\,f_{\mathrm{es}4}$']
ES_H_LABELS_4 = [r'$\Delta\,H_{\mathrm{es}1}$', r'$\Delta\,H_{\mathrm{es}2}$',
                  r'$\Delta\,H_{\mathrm{es}3}$', r'$\Delta\,H_{\mathrm{es}4}$']
ES_D_LABELS_4 = [r'$\Delta\,D_{\mathrm{es}1}$', r'$\Delta\,D_{\mathrm{es}2}$',
                  r'$\Delta\,D_{\mathrm{es}3}$', r'$\Delta\,D_{\mathrm{es}4}$']

# Fig 18-21: 8-agent NE 颜色
ES_COLORS_8 = ['#E8548A', '#F5A623', '#F0C040', '#6BBF59',
               '#36D7B7', '#4A90D9', '#8B8B8B', '#B07DD0']
ES_FREQ_LABELS_8 = [f'$f_{{\\mathrm{{es}}{i+1}}}$' for i in range(8)]
ES_H_LABELS_8 = [f'$H_{{\\mathrm{{es}}{i+1}}}$' for i in range(8)]
ES_D_LABELS_8 = [f'$D_{{\\mathrm{{es}}{i+1}}}$' for i in range(8)]
ES_P_LABELS_8 = [f'$\\Delta P_{{\\mathrm{{es}}{i+1}}}$' for i in range(8)]

# Fig 4 训练曲线配色
COLOR_TOTAL   = '#8B3A3A'
COLOR_FREQ    = '#D2691E'
COLOR_INERTIA = '#2E8B57'
COLOR_DROOP   = '#6A0DAD'

# Fig 5/10/12 累积奖励配色
COLOR_NO_CTRL  = '#6B2A2A'
COLOR_ADAPTIVE = '#1B5E20'
COLOR_PROPOSED = '#E8863A'
COLOR_FAILURE  = '#2E8B57'
COLOR_DELAY    = '#7B2D8E'

# Fig 14/15 可扩展性配色
COLOR_DISTRIBUTED = '#8B3A3A'
COLOR_CENTRALIZED = '#2E8B57'

# H_avg / D_avg 虚线
COLOR_AVG = '#1A1A1A'


def _es_config(n_agents):
    """根据 agent 数量返回 (colors, freq_labels, p_labels, h_labels, d_labels)."""
    if n_agents <= 4:
        return (ES_COLORS_4[:n_agents], ES_FREQ_LABELS_4[:n_agents],
                ES_LABELS_4[:n_agents], ES_H_LABELS_4[:n_agents],
                ES_D_LABELS_4[:n_agents])
    else:
        return (ES_COLORS_8[:n_agents], ES_FREQ_LABELS_8[:n_agents],
                ES_P_LABELS_8[:n_agents], ES_H_LABELS_8[:n_agents],
                ES_D_LABELS_8[:n_agents])


# ═══════════════════════════════════════════════════════════
#  全局 IEEE 论文样式
# ═══════════════════════════════════════════════════════════

def apply_ieee_style():
    """应用 IEEE Transactions 论文的 matplotlib 全局样式."""
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
        'xtick.minor.size': 2.0,
        'ytick.minor.size': 2.0,
        'xtick.top': True,
        'ytick.right': True,
        'axes.grid': False,
        'legend.framealpha': 0.95,
        'legend.edgecolor': 'black',
        'legend.fancybox': False,
        'legend.fontsize': 8,
        'legend.borderpad': 0.3,
        'legend.handlelength': 1.8,
        'savefig.dpi': 250,
        'savefig.bbox': 'tight',
    })


# ═══════════════════════════════════════════════════════════
#  基础工具函数
# ═══════════════════════════════════════════════════════════

def paper_legend(ax, **kwargs):
    """创建论文风格的图例."""
    defaults = dict(fontsize=8, framealpha=0.95, edgecolor='black',
                    fancybox=False, borderpad=0.3, handlelength=1.8,
                    labelspacing=0.25)
    defaults.update(kwargs)
    leg = ax.legend(**defaults)
    leg.get_frame().set_linewidth(0.5)
    return leg


def rolling_stats(data, window=50):
    """计算滑动平均和标准差 (带边界修正)."""
    n = len(data)
    mean = np.convolve(data, np.ones(window) / window, mode='same')
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


def plot_band(ax, x, data, color, label, lw=1.4, window=50, alpha=0.20):
    """绘制滑动平均 + 标准差带."""
    mean, std = rolling_stats(data, window)
    ax.fill_between(x, mean - std, mean + std, color=color, alpha=alpha, linewidth=0)
    ax.plot(x, mean, color=color, lw=lw, label=label)
    return mean, std


def save_fig(fig, save_dir, name, dpi=300, also_pdf=True):
    """保存 PNG + PDF."""
    os.makedirs(save_dir, exist_ok=True)
    png_path = os.path.join(save_dir, name)
    fig.savefig(png_path, dpi=dpi, bbox_inches='tight')
    if also_pdf:
        fig.savefig(png_path.replace('.png', '.pdf'), bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: {name}')


# ═══════════════════════════════════════════════════════════
#  通用绘图函数 — 可跨场景 (Kundur / NE / Scalability) 复用
# ═══════════════════════════════════════════════════════════

def plot_time_domain_2x2(traj, n_agents=4, f_nom=50.0, fig_label=''):
    """论文 Fig 6-9/11/13/18-21 风格 2×2 时域图.

    Parameters
    ----------
    traj : dict
        必须包含 keys: 'time', 'freq_hz', 'P_es', 'M_es', 'D_es'
        每个值为 np.ndarray, shape (n_steps,) 或 (n_steps, n_agents)
    fig_label : str
        子图标签前缀, 如 'Fig6-' → 子图标签为 '(Fig6-a)', '(Fig6-b)', ...
    n_agents : int
        agent 数量 (4 或 8)
    f_nom : float
        标称频率 (50.0 Hz)
    """
    # Accept both dict and Trajectory dataclass
    if not isinstance(traj, dict):
        traj = {
            'time': traj.time, 'freq_hz': traj.freq_hz,
            'P_es': traj.P_es, 'M_es': traj.M_es, 'D_es': traj.D_es,
        }
    apply_ieee_style()
    colors, labels_f, labels_p, labels_h, labels_d = _es_config(n_agents)

    fig, axes = plt.subplots(2, 2, figsize=(7.16, 5.0))
    fig.subplots_adjust(hspace=0.45, wspace=0.38, left=0.10, right=0.97,
                        top=0.95, bottom=0.08)

    t = traj['time']

    # (a) Frequency deviation
    ax = axes[0, 0]
    for i in range(n_agents):
        ax.plot(t, traj['freq_hz'][:, i] - f_nom, color=colors[i],
                lw=1.2, label=labels_f[i])
    ax.set_ylabel(r'$\Delta f$ (Hz)', fontsize=9)
    ax.axhline(0, color='gray', lw=0.5, ls='--')
    ncol = 2 if n_agents <= 4 else 4
    paper_legend(ax, loc='best', fontsize=7, ncol=ncol)
    ax.set_xlabel(f'({fig_label}a) Time (s)', fontsize=9, labelpad=3)

    # (b) ES output power
    ax = axes[0, 1]
    for i in range(n_agents):
        ax.plot(t, traj['P_es'][:, i], color=colors[i],
                lw=1.2, label=labels_p[i])
    ax.set_ylabel(r'$\Delta P_{\mathrm{es}}$ (p.u.)', fontsize=9)
    paper_legend(ax, loc='best', fontsize=7, ncol=ncol)
    ax.set_xlabel(f'({fig_label}b) Time (s)', fontsize=9, labelpad=3)

    # (c) Virtual inertia H
    ax = axes[1, 0]
    for i in range(n_agents):
        ax.plot(t, traj['M_es'][:, i] / 2.0, color=colors[i],
                lw=1.2, label=labels_h[i])
    H_avg = np.mean(traj['M_es'] / 2.0, axis=1)
    ax.plot(t, H_avg, color=COLOR_AVG, lw=1.0, ls='--',
            label=r'$H_{\mathrm{avg}}$')
    ax.set_ylabel(r'$H$ (s)', fontsize=9)
    paper_legend(ax, loc='best', fontsize=7, ncol=ncol)
    ax.set_xlabel(f'({fig_label}c) Time (s)', fontsize=9, labelpad=3)

    # (d) Virtual droop D
    ax = axes[1, 1]
    for i in range(n_agents):
        ax.plot(t, traj['D_es'][:, i], color=colors[i],
                lw=1.2, label=labels_d[i])
    D_avg = np.mean(traj['D_es'], axis=1)
    ax.plot(t, D_avg, color=COLOR_AVG, lw=1.0, ls='--',
            label=r'$D_{\mathrm{avg}}$')
    ax.set_ylabel(r'$D$ (p.u.)', fontsize=9)
    paper_legend(ax, loc='best', fontsize=7, ncol=ncol)
    ax.set_xlabel(f'({fig_label}d) Time (s)', fontsize=9, labelpad=3)

    return fig


def plot_cumulative_reward(rewards_dict, fig_label='(a)'):
    """论文 Fig 5/10/12/15 风格累积奖励对比图.

    Parameters
    ----------
    rewards_dict : dict[str, list[float]]
        {'方法名': [ep1_reward, ep2_reward, ...], ...}
        方法名会自动匹配颜色和线型.
    """
    apply_ieee_style()

    _color_map = {
        'No control': COLOR_NO_CTRL,
        'Without control': COLOR_NO_CTRL,
        'without control': COLOR_NO_CTRL,
        'Adaptive inertia': COLOR_ADAPTIVE,
        'Proposed MADRL': COLOR_PROPOSED,
        'Proposed control': COLOR_PROPOSED,
        'Proposed (normal)': COLOR_PROPOSED,
        'Proposed (failure)': COLOR_FAILURE,
        'Proposed (delay)': COLOR_DELAY,
        'Centralized DRL control': COLOR_CENTRALIZED,
    }
    _ls_map = {
        'No control': ':', 'Without control': ':', 'without control': ':',
        'Adaptive inertia': '--',
        'Proposed MADRL': '-', 'Proposed control': '-',
        'Proposed (normal)': '-',
        'Proposed (failure)': '--',
        'Proposed (delay)': '--',
        'Centralized DRL control': '-.',
    }

    fig, ax = plt.subplots(figsize=(4.5, 3.2))
    fig.subplots_adjust(left=0.16, right=0.96, top=0.95, bottom=0.15)

    for label, rewards in rewards_dict.items():
        eps = np.arange(1, len(rewards) + 1)
        cum = np.cumsum(rewards)
        c = _color_map.get(label, 'black')
        ls = _ls_map.get(label, '-')
        ax.plot(eps, cum, color=c, ls=ls, lw=1.5, label=label)

    ax.set_xlabel(f'{fig_label} Test episodes', fontsize=10)
    ax.set_ylabel('Cumulative\nreward', fontsize=10, rotation=0,
                  labelpad=40, va='center')
    paper_legend(ax, loc='best', fontsize=8)

    return fig


def plot_training_curves(total_rewards, agent_rewards,
                          freq_rewards=None, inertia_rewards=None,
                          droop_rewards=None, n_agents=4, window=50):
    """论文 Fig 4/17 风格训练曲线.

    布局: (a) 顶部大图 Total/Freq/Inertia/Droop, (b)-(e) 底部 agent 子图.

    Parameters
    ----------
    total_rewards : np.ndarray, shape (n_episodes,)
    agent_rewards : list[np.ndarray], 长度 n_agents, 每个 shape (n_episodes,)
    freq_rewards, inertia_rewards, droop_rewards : np.ndarray or None
        若 None, 则只画 Total.
    """
    apply_ieee_style()
    colors = ES_COLORS_4[:n_agents] if n_agents <= 4 else ES_COLORS_8[:n_agents]

    n_ep = len(total_rewards)
    episodes = np.arange(n_ep)

    # 底部子图布局: 2 列, ceil(n_agents/2) 行
    n_rows_sub = (n_agents + 1) // 2
    n_cols_sub = min(n_agents, 2)

    fig = plt.figure(figsize=(7.16, 3.5 + 2.5 * n_rows_sub))
    gs = GridSpec(1 + n_rows_sub, n_cols_sub, figure=fig,
                  height_ratios=[1.5] + [1] * n_rows_sub,
                  hspace=0.50, wspace=0.40,
                  left=0.11, right=0.97, top=0.98, bottom=0.06)

    # ── (a) 顶部大图 ──
    ax_a = fig.add_subplot(gs[0, :])
    plot_band(ax_a, episodes, total_rewards, COLOR_TOTAL, 'Total', window=window)
    if freq_rewards is not None:
        plot_band(ax_a, episodes, freq_rewards, COLOR_FREQ, 'Frequency', window=window)
    if inertia_rewards is not None:
        plot_band(ax_a, episodes, inertia_rewards, COLOR_INERTIA, 'Inertia', window=window)
    if droop_rewards is not None:
        plot_band(ax_a, episodes, droop_rewards, COLOR_DROOP, 'Droop', window=window)

    ax_a.set_ylabel('Episode\nreward', fontsize=10.5, rotation=0,
                    labelpad=35, va='center')
    ax_a.set_xlim(0, n_ep)
    ax_a.xaxis.set_major_locator(ticker.MultipleLocator(500))

    total_mean, total_std = rolling_stats(total_rewards, window)
    y_lo = min((total_mean - total_std).min(), -200) * 1.1
    y_hi = max((total_mean + total_std).max(), 0) * 0.9 + 20
    ax_a.set_ylim(y_lo, y_hi)
    paper_legend(ax_a, loc='center right', fontsize=8.5)
    ax_a.set_xlabel('(a) Training episodes', fontsize=10.5, labelpad=5)

    # ── (b)-(e+) 底部子图 ──
    sub_labels = [f'({chr(98 + i)})' for i in range(n_agents)]
    es_names = [f'ES{i+1}' for i in range(n_agents)]

    # 统一 y 轴 — skip if no per-agent data
    if n_agents == 0 or len(agent_rewards) == 0:
        plt.tight_layout()
        return fig

    smoothed_ranges = []
    for a in agent_rewards:
        m, s = rolling_stats(a, window)
        smoothed_ranges.append(((m - s).min(), (m + s).max()))
    y_min_sub = min(r[0] for r in smoothed_ranges) * 1.05
    y_max_sub = max(r[1] for r in smoothed_ranges)
    y_max_sub = y_max_sub * 0.95 if y_max_sub < 0 else y_max_sub * 1.05 + 2

    for idx in range(n_agents):
        row = 1 + idx // n_cols_sub
        col = idx % n_cols_sub
        ax = fig.add_subplot(gs[row, col])
        color = colors[idx]

        plot_band(ax, episodes, agent_rewards[idx], color, None, window=window)

        ax.set_ylabel('Episode\nreward', fontsize=9, rotation=0,
                      labelpad=30, va='center')
        ax.set_xlim(0, n_ep)
        ax.set_ylim(y_min_sub, y_max_sub)
        ax.xaxis.set_major_locator(ticker.MultipleLocator(500))
        ax.xaxis.set_major_formatter(
            ticker.FuncFormatter(lambda x, _: f'{int(x):,}'))

        legend_line = Line2D([0], [0], color=color, lw=1.5)
        leg_i = ax.legend(
            [legend_line], [f'{es_names[idx]}-Total'],
            loc='lower right', fontsize=7.5,
            framealpha=0.95, edgecolor='black',
            fancybox=False, borderpad=0.3, handlelength=1.5,
        )
        leg_i.get_frame().set_linewidth(0.5)
        ax.set_xlabel(f'{sub_labels[idx]} Training episodes',
                      fontsize=9.5, labelpad=3)

    return fig


def plot_freq_comparison(trajs_dict, agent_idx=0, f_nom=50.0):
    """论文 Fig 21 风格: 多种控制方法的频率响应对比 (单 agent).

    Parameters
    ----------
    trajs_dict : dict[str, dict]
        {'方法名': traj_dict, ...}, 每个 traj_dict 含 'time', 'freq_hz'
    agent_idx : int
        画哪个 agent 的频率
    """
    _trajs = {}
    for label, traj in trajs_dict.items():
        if not isinstance(traj, dict):
            traj = {'time': traj.time, 'freq_hz': traj.freq_hz}
        _trajs[label] = traj
    trajs_dict = _trajs
    apply_ieee_style()
    _color_map = {
        'without control': COLOR_NO_CTRL,
        'Without control': COLOR_NO_CTRL,
        'proposed control': COLOR_PROPOSED,
        'Proposed control': COLOR_PROPOSED,
        'adaptive inertia': COLOR_ADAPTIVE,
        'Adaptive inertia': COLOR_ADAPTIVE,
    }

    fig, ax = plt.subplots(figsize=(6.5, 3.8))

    for label, traj in trajs_dict.items():
        c = _color_map.get(label, 'black')
        ax.plot(traj['time'], traj['freq_hz'][:, agent_idx] - f_nom,
                color=c, lw=2.0, label=label)

    ax.set_xlabel('Time (s)', fontsize=10)
    ax.set_ylabel(r'$\Delta f$ (Hz)', fontsize=10)
    paper_legend(ax, loc='upper right', fontsize=9, handlelength=2.0)
    fig.subplots_adjust(left=0.12, right=0.96, top=0.96, bottom=0.14)

    return fig


def compute_freq_sync_reward(traj):
    """计算频率同步奖励: -Σ(fi - f_bar)².

    Parameters
    ----------
    traj : dict
        含 'freq_hz' key, shape (n_steps, n_agents)
    """
    f = traj['freq_hz']
    f_bar = f.mean(axis=1, keepdims=True)
    return -np.sum((f - f_bar) ** 2)
