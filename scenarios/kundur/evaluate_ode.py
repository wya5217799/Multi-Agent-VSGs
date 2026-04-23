"""
评估脚本 — 生成论文 Fig 4-13 所有图表 (IEEE 论文风格)

用法:
    python evaluate.py                      # 默认参数
    python evaluate.py --model path/to/dir  # 指定模型
    python evaluate.py --test-episodes 50   # 测试 episode 数
"""

import argparse
import os
import sys
import numpy as np
import torch
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config as cfg
from env.multi_vsg_env import MultiVSGEnv
from agents.ma_manager import MultiAgentManager
from plotting.paper_style import (apply_ieee_style, paper_legend, rolling_stats, plot_band,
                                  ES_COLORS_4, ES_FREQ_LABELS_4, ES_H_LABELS_4, ES_D_LABELS_4,
                                  COLOR_TOTAL, COLOR_FREQ, COLOR_INERTIA, COLOR_DROOP,
                                  COLOR_NO_CTRL, COLOR_ADAPTIVE, COLOR_PROPOSED,
                                  COLOR_FAILURE, COLOR_DELAY, COLOR_AVG)

# ─── 论文测试场景 (从 config 读取) ───
LOAD_STEP_1 = cfg.LOAD_STEP_1
LOAD_STEP_2 = cfg.LOAD_STEP_2

# ─── 论文 ES 标签 ───
P_LABELS = [rf'$\Delta\,P_{{\mathrm{{es}}{i+1}}}$' for i in range(cfg.N_AGENTS)]
F_LABELS = [rf'$\Delta\,f_{{\mathrm{{es}}{i+1}}}$' for i in range(cfg.N_AGENTS)]
H_LABELS = [rf'$\Delta\,H_{{\mathrm{{es}}{i+1}}}$' for i in range(cfg.N_AGENTS)]
D_LABELS = [rf'$\Delta\,D_{{\mathrm{{es}}{i+1}}}$' for i in range(cfg.N_AGENTS)]


# ═══════════════════════════════════════════════════════
#  通用工具函数
# ═══════════════════════════════════════════════════════

def _adaptive_inertia_action(obs_dict, k_h=2.0):
    """
    Adaptive inertia control baseline (论文 ref [25]).

    ΔH_i = k_h * Δω_i * dω_i/dt
    Δω<0, dω/dt<0 (频率下降) → ΔH>0 (增大 H)
    Δω<0, dω/dt>0 (频率恢复) → ΔH<0 (减小 H)
    D 不调整 (ΔD=0).
    """
    actions = {}
    for i in range(cfg.N_AGENTS):
        o = obs_dict[i]
        omega = o[1] * 3.0
        omega_dot = o[2] * 25.0   # match /25.0 normalization in multi_vsg_env.py
        delta_H = k_h * omega * omega_dot
        delta_H = np.clip(delta_H, cfg.DH_MIN, cfg.DH_MAX)
        # 零中心映射: a=delta_H/DH_MAX (正) or delta_H/(-DH_MIN) (负)
        a0 = float(delta_H / cfg.DH_MAX if delta_H >= 0 else delta_H / (-cfg.DH_MIN))
        actions[i] = np.array([a0, 0.0], dtype=np.float32)  # ΔD=0
    return actions


def run_episode(env, manager=None, delta_u=None, deterministic=True,
                control_mode='rl'):
    """运行一个 episode, 返回完整轨迹."""
    obs = env.reset(delta_u=delta_u)

    t_log = [0.0]
    freq_log = [env.ps.get_state()['freq_hz']]
    P_es_log = [env.ps.get_state()['P_es']]
    H_log = [cfg.H_ES0.copy()]
    D_log = [cfg.D_ES0.copy()]
    per_agent_rewards = {i: 0.0 for i in range(cfg.N_AGENTS)}

    for step in range(cfg.STEPS_PER_EPISODE):
        if control_mode == 'rl' and manager is not None:
            actions = manager.select_actions(obs, deterministic=deterministic)
        elif control_mode == 'adaptive_inertia':
            actions = _adaptive_inertia_action(obs)
        else:
            # fixed: a=0 → ΔH=0, ΔD=0 (零中心映射, 保持基准参数)
            actions = {i: np.zeros(cfg.ACTION_DIM, dtype=np.float32)
                       for i in range(cfg.N_AGENTS)}

        next_obs, rewards, done, info = env.step(actions)

        t_log.append(info['time'])
        freq_log.append(info['freq_hz'])
        P_es_log.append(info['P_es'])
        H_log.append(info['H_es'])
        D_log.append(info['D_es'])
        for i in range(cfg.N_AGENTS):
            per_agent_rewards[i] += rewards[i]
        obs = next_obs

    return {
        't': np.array(t_log),
        'freq': np.array(freq_log),
        'P_es': np.array(P_es_log),
        'H_es': np.array(H_log),
        'D_es': np.array(D_log),
        'rewards': per_agent_rewards,
        'total_reward': sum(per_agent_rewards.values()),
    }


def compute_freq_sync_reward(freq_array):
    """论文全局频率同步奖励: -sum_t sum_i (f_i,t - f_bar_t)^2."""
    f_bar = freq_array.mean(axis=1, keepdims=True)
    return -np.sum((freq_array - f_bar) ** 2)


TEST_SEED = 99  # P0: 固定测试集 seed，写入 run metadata 以保证跨 run 可复验

def generate_test_scenarios(n=None, seed=TEST_SEED):
    """生成固定测试场景集 (Sec.IV-A: 50 randomly generated test scenarios).

    n 默认读取 cfg.N_TEST_SCENARIOS（P0 要求：不得绕过 cfg 硬编码）。
    """
    if n is None:
        n = cfg.N_TEST_SCENARIOS
    rng = np.random.default_rng(seed)
    scenarios = []
    for _ in range(n):
        n_disturbed = rng.integers(1, 3)
        buses = rng.choice(cfg.N_AGENTS, size=n_disturbed, replace=False)
        delta_u = np.zeros(cfg.N_AGENTS)
        for bus in buses:
            mag = rng.uniform(cfg.DISTURBANCE_MIN, cfg.DISTURBANCE_MAX)
            sign = rng.choice([-1, 1])
            delta_u[bus] = sign * mag
        failed_links = []
        for i, neighbors in cfg.COMM_ADJACENCY.items():
            for j in neighbors:
                if (j, i) not in failed_links and rng.random() < cfg.COMM_FAIL_PROB:
                    failed_links.append((i, j))
                    failed_links.append((j, i))
        scenarios.append((delta_u, failed_links if failed_links else None))
    return scenarios


def run_test_set(manager, scenarios, comm_fail_prob=0.0, comm_delay_steps=0,
                 forced_link_failures=None, include_adaptive=False):
    """跑固定测试场景集, 返回频率同步奖励列表 (论文 Sec.IV-C)."""
    env = MultiVSGEnv(random_disturbance=False, comm_fail_prob=comm_fail_prob,
                      comm_delay_steps=comm_delay_steps,
                      forced_link_failures=forced_link_failures)
    rewards_rl, rewards_fixed, rewards_adaptive = [], [], []
    for delta_u, fail_links in scenarios:
        env.forced_link_failures = fail_links
        traj_r = run_episode(env, manager=manager, delta_u=delta_u, control_mode='rl')
        traj_f = run_episode(env, delta_u=delta_u, control_mode='fixed')
        rewards_rl.append(compute_freq_sync_reward(traj_r['freq']))
        rewards_fixed.append(compute_freq_sync_reward(traj_f['freq']))
        if include_adaptive:
            traj_a = run_episode(env, delta_u=delta_u, control_mode='adaptive_inertia')
            rewards_adaptive.append(compute_freq_sync_reward(traj_a['freq']))
    result = (np.array(rewards_rl), np.array(rewards_fixed))
    if include_adaptive:
        result = result + (np.array(rewards_adaptive),)
    return result


# ═══════════════════════════════════════════════════════
#  Fig 4: 训练曲线 (由 plot_fig4_paper.py 生成)
# ═══════════════════════════════════════════════════════

def plot_fig4(log_path, save_path):
    """Fig 4: Training performance — 使用 plot_fig4_paper.py 的格式."""
    apply_ieee_style()
    log = np.load(log_path)
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
        freq_100 = total.copy()
        inertia = np.zeros(n_ep)
        droop = np.zeros(n_ep)

    fig = plt.figure(figsize=(7.5, 8.5))
    gs = GridSpec(3, 2, figure=fig, height_ratios=[1.5, 1, 1],
                  hspace=0.55, wspace=0.42,
                  left=0.12, right=0.96, top=0.98, bottom=0.06)

    # (a) 顶部大图
    ax_a = fig.add_subplot(gs[0, :])
    plot_band(ax_a, episodes, freq_100, COLOR_FREQ, '100*Frequency')
    plot_band(ax_a, episodes, total, COLOR_TOTAL, 'Total')
    plot_band(ax_a, episodes, inertia, COLOR_INERTIA, 'Inertia')
    plot_band(ax_a, episodes, droop, COLOR_DROOP, 'Droop')

    handles, labels = ax_a.get_legend_handles_labels()
    order = [1, 0, 2, 3]
    ax_a.legend([handles[i] for i in order], [labels[i] for i in order],
                loc='center right', fontsize=8.5)
    ax_a.set_ylabel('Episode\nreward', fontsize=10.5)
    ax_a.set_xlim(0, n_ep)
    ax_a.xaxis.set_major_locator(ticker.MultipleLocator(500))
    total_m, total_s = rolling_stats(total)
    ax_a.set_ylim((total_m - total_s).min() * 1.15,
                  max((total_m + total_s * 0.5).max(), 50))
    ax_a.set_xlabel('(a) Training episodes', fontsize=10.5, labelpad=5)

    # (b)-(e) 底部 2×2
    positions = [(1, 0), (1, 1), (2, 0), (2, 1)]
    sub_labels = ['(b)', '(c)', '(d)', '(e)']
    es_names = ['ES1', 'ES2', 'ES3', 'ES4']
    sm = [rolling_stats(a) for a in agents]
    y_min = min((m - s).min() for m, s in sm) * 1.05
    y_max = max((m + s).max() for m, s in sm)
    y_max = y_max * 0.95 if y_max < 0 else y_max * 1.05
    y_lim = (y_min, y_max + abs(y_max) * 0.1)

    for idx, (row, col) in enumerate(positions):
        ax = fig.add_subplot(gs[row, col])
        plot_band(ax, episodes, agents[idx], COLOR_TOTAL, None, lw=1.2)
        ax.set_ylabel('Episode\nreward', fontsize=9)
        ax.set_xlim(0, n_ep)
        ax.set_ylim(y_lim)
        ax.xaxis.set_major_locator(ticker.MultipleLocator(1000))
        ax.xaxis.set_major_formatter(
            ticker.FuncFormatter(lambda x, _: f'{int(x):,}'))
        leg_line = Line2D([0], [0], color=COLOR_TOTAL, lw=1.5)
        ax.legend([leg_line], [f'{es_names[idx]}-Total'],
                  loc='lower right', fontsize=7.5)
        ax.set_xlabel(f'{sub_labels[idx]} Training episodes', fontsize=9.5, labelpad=3)

    plt.savefig(save_path, dpi=250, bbox_inches='tight')
    plt.close()
    print(f"  [Fig 4] {save_path}")


# ═══════════════════════════════════════════════════════
#  Fig 5: 累积频率奖励
# ═══════════════════════════════════════════════════════

def plot_fig5(rewards_rl, rewards_fixed, save_path, rewards_adaptive=None):
    """Fig 5. Cumulative reward on the test set — 论文风格."""
    apply_ieee_style()
    fig, ax = plt.subplots(figsize=(6.0, 4.2))
    eps = np.arange(0, len(rewards_rl))

    ax.plot(eps, np.cumsum(rewards_fixed), color=COLOR_NO_CTRL, lw=2.0,
            label='without control')
    if rewards_adaptive is not None:
        ax.plot(eps, np.cumsum(rewards_adaptive), color=COLOR_ADAPTIVE, lw=2.0,
                label='with adaptive control')
    ax.plot(eps, np.cumsum(rewards_rl), color=COLOR_PROPOSED, lw=2.0,
            label='with proposed control')

    ax.set_xlabel('Test episodes', fontsize=11, labelpad=5)
    ax.set_ylabel('Frequency\ncumulative reward', fontsize=11)
    ax.set_xlim(0, len(rewards_rl) - 1)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(10))
    paper_legend(ax, loc='lower left', fontsize=9.5, handlelength=2.0)
    fig.subplots_adjust(left=0.16, right=0.96, top=0.96, bottom=0.13)
    plt.savefig(save_path, dpi=250)
    plt.close()
    print(f"  [Fig 5] {save_path}")
    print(f"    Proposed: {np.mean(rewards_rl):.4f}")
    if rewards_adaptive is not None:
        print(f"    Adaptive: {np.mean(rewards_adaptive):.4f}")
    print(f"    No ctrl:  {np.mean(rewards_fixed):.4f}")


# ═══════════════════════════════════════════════════════
#  Fig 6/8: 无控制时域 — 2×1 竖排 (ΔP_es, Δf_es)
# ═══════════════════════════════════════════════════════

def plot_no_control(traj, title_suffix, save_path):
    """Fig 6/8: system dynamics without proposed control — 论文风格."""
    apply_ieee_style()
    t = traj['t']
    N = traj['freq'].shape[1]
    colors = ES_COLORS_4[:N]
    t_max = 6.0  # 论文 x 轴 0-6s

    fig, (ax_a, ax_b) = plt.subplots(2, 1, figsize=(6.0, 5.0), sharex=True)
    fig.subplots_adjust(hspace=0.08, left=0.15, right=0.95, top=0.97, bottom=0.10)

    # (a) ΔP_es (MW)
    P_mw = traj['P_es'] * cfg.S_BASE
    for i in range(N):
        ax_a.plot(t, P_mw[:, i], color=colors[i], lw=1.2,
                  label=P_LABELS[i])
    ax_a.set_ylabel(r'(a) $\Delta\,P_{\mathrm{es}}$(MW)', fontsize=10)
    ax_a.set_xlim(0, t_max)
    paper_legend(ax_a, loc='upper right', ncol=2, fontsize=8,
                 handlelength=1.5, columnspacing=0.8)

    # (b) Δf_es (Hz) — 频率偏差
    freq_dev = traj['freq'] - 50.0
    for i in range(N):
        ax_b.plot(t, freq_dev[:, i], color=colors[i], lw=1.2,
                  label=F_LABELS[i])
    ax_b.set_ylabel(r'(b) $\Delta\,f_{\mathrm{es}}$(Hz)', fontsize=10)
    ax_b.set_xlabel('Time (s)', fontsize=10)
    ax_b.set_xlim(0, t_max)
    ax_b.xaxis.set_major_locator(ticker.MultipleLocator(1))
    paper_legend(ax_b, loc='upper right', ncol=2, fontsize=8,
                 handlelength=1.5, columnspacing=0.8)

    plt.savefig(save_path, dpi=250, bbox_inches='tight')
    plt.close()
    print(f"  [Fig] {save_path}")


# ═══════════════════════════════════════════════════════
#  Fig 7/9: RL 控制时域 — 4×1 竖排
# ═══════════════════════════════════════════════════════

def plot_rl_control(traj, title_suffix, save_path):
    """Fig 7/9: system dynamics with proposed control — 论文 4×1 竖排."""
    apply_ieee_style()
    t = traj['t']
    N = traj['freq'].shape[1]
    colors = ES_COLORS_4[:N]
    t_max = 6.0

    fig, axes = plt.subplots(4, 1, figsize=(6.0, 9.0), sharex=True)
    fig.subplots_adjust(hspace=0.08, left=0.15, right=0.95, top=0.98, bottom=0.06)

    # (a) ΔP_es (MW)
    ax = axes[0]
    P_mw = traj['P_es'] * cfg.S_BASE
    for i in range(N):
        ax.plot(t, P_mw[:, i], color=colors[i], lw=1.2, label=P_LABELS[i])
    ax.set_ylabel(r'(a) $\Delta\,P_{\mathrm{es}}$(MW)', fontsize=10)
    paper_legend(ax, loc='upper right', ncol=2, fontsize=7.5,
                 handlelength=1.5, columnspacing=0.8)

    # (b) Δf_es (Hz)
    ax = axes[1]
    freq_dev = traj['freq'] - 50.0
    for i in range(N):
        ax.plot(t, freq_dev[:, i], color=colors[i], lw=1.2, label=F_LABELS[i])
    ax.set_ylabel(r'(b) $\Delta\,f_{\mathrm{es}}$(Hz)', fontsize=10)
    paper_legend(ax, loc='upper right', ncol=2, fontsize=7.5,
                 handlelength=1.5, columnspacing=0.8)

    # (c) ΔH_es
    ax = axes[2]
    H_dev = traj['H_es'] - cfg.H_ES0[np.newaxis, :]
    H_avg = H_dev.mean(axis=1)
    for i in range(N):
        ax.plot(t, H_dev[:, i], color=colors[i], lw=1.2, label=H_LABELS[i])
    ax.plot(t, H_avg, color=COLOR_AVG, ls='--', lw=1.2, label=r'$\Delta\,H_{\mathrm{avg}}$')
    ax.set_ylabel(r'(c) $\Delta\,H_{\mathrm{es}}$', fontsize=10)
    paper_legend(ax, loc='upper right', ncol=2, fontsize=7.5,
                 handlelength=1.5, columnspacing=0.8)

    # (d) ΔD_es
    ax = axes[3]
    D_dev = traj['D_es'] - cfg.D_ES0[np.newaxis, :]
    D_avg = D_dev.mean(axis=1)
    for i in range(N):
        ax.plot(t, D_dev[:, i], color=colors[i], lw=1.2, label=D_LABELS[i])
    ax.plot(t, D_avg, color=COLOR_AVG, ls='--', lw=1.2, label=r'$\Delta\,D_{\mathrm{avg}}$')
    ax.set_ylabel(r'(d) $\Delta\,D_{\mathrm{es}}$', fontsize=10)
    ax.set_xlabel('Time (s)', fontsize=10)
    paper_legend(ax, loc='upper right', ncol=2, fontsize=7.5,
                 handlelength=1.5, columnspacing=0.8)

    for ax in axes:
        ax.set_xlim(0, t_max)
    axes[-1].xaxis.set_major_locator(ticker.MultipleLocator(1))

    plt.savefig(save_path, dpi=250, bbox_inches='tight')
    plt.close()
    print(f"  [Fig] {save_path}")


# ═══════════════════════════════════════════════════════
#  Fig 10: 通信故障 累积奖励
# ═══════════════════════════════════════════════════════

def plot_fig10(rewards_rl, rewards_fail, rewards_fixed, save_path):
    """Fig 10: Cumulative reward under communication failure — 论文风格."""
    apply_ieee_style()
    fig, ax = plt.subplots(figsize=(6.0, 4.2))
    eps = np.arange(0, len(rewards_rl))

    ax.plot(eps, np.cumsum(rewards_fixed), color=COLOR_NO_CTRL, lw=2.0,
            label='without proposed control')
    ax.plot(eps, np.cumsum(rewards_rl), color=COLOR_PROPOSED, lw=2.0,
            label='with proposed control')
    ax.plot(eps, np.cumsum(rewards_fail), color=COLOR_FAILURE, lw=2.0,
            label='under communication failure')

    ax.set_xlabel('Test episodes', fontsize=11, labelpad=5)
    ax.set_ylabel('Frequency\ncumulative reward', fontsize=11)
    ax.set_xlim(0, len(rewards_rl) - 1)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(10))
    paper_legend(ax, loc='lower left', fontsize=9, handlelength=2.0)
    fig.subplots_adjust(left=0.16, right=0.96, top=0.96, bottom=0.13)
    plt.savefig(save_path, dpi=250)
    plt.close()
    print(f"  [Fig 10] {save_path}")


# ═══════════════════════════════════════════════════════
#  Fig 11: 通信故障 时域 (2×1, 同 Fig 6 风格)
# ═══════════════════════════════════════════════════════

def plot_fig11(traj, save_path):
    """Fig 11: System dynamics under communication failure — 2×1."""
    # 论文 Fig 11 没有单独的图, 复用 Fig 6 的 no-control 风格
    # 但显示 RL 控制 + 通信故障, 保持 2×1 (ΔP_es, Δf_es)
    plot_no_control(traj, 'communication failure', save_path)


# ═══════════════════════════════════════════════════════
#  Fig 12: 通信延迟 累积奖励
# ═══════════════════════════════════════════════════════

def plot_fig12(rewards_rl, rewards_delay, rewards_fixed, save_path):
    """Fig 12: Cumulative reward under communication delay — 论文风格."""
    apply_ieee_style()
    fig, ax = plt.subplots(figsize=(6.0, 4.2))
    eps = np.arange(0, len(rewards_rl))

    ax.plot(eps, np.cumsum(rewards_fixed), color=COLOR_NO_CTRL, lw=2.0,
            label='without proposed control')
    ax.plot(eps, np.cumsum(rewards_rl), color=COLOR_PROPOSED, lw=2.0,
            label='with proposed control')
    ax.plot(eps, np.cumsum(rewards_delay), color=COLOR_DELAY, lw=2.0,
            label='under communication delay')

    ax.set_xlabel('Test episodes', fontsize=11, labelpad=5)
    ax.set_ylabel('Frequency\ncumulative reward', fontsize=11)
    ax.set_xlim(0, len(rewards_rl) - 1)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(10))
    paper_legend(ax, loc='lower left', fontsize=9, handlelength=2.0)
    fig.subplots_adjust(left=0.16, right=0.96, top=0.96, bottom=0.13)
    plt.savefig(save_path, dpi=250)
    plt.close()
    print(f"  [Fig 12] {save_path}")


# ═══════════════════════════════════════════════════════
#  Fig 13: 通信延迟 时域 — 2×1 (ΔP_es, Δf_es)
# ═══════════════════════════════════════════════════════

def plot_fig13(traj, save_path):
    """Fig 13: System dynamics under 0.2s communication delay — 2×1."""
    apply_ieee_style()
    t = traj['t']
    N = traj['freq'].shape[1]
    colors = ES_COLORS_4[:N]
    t_max = 10.0  # 论文 Fig 13 x 轴 0-10s

    fig, (ax_a, ax_b) = plt.subplots(2, 1, figsize=(6.0, 5.0), sharex=True)
    fig.subplots_adjust(hspace=0.08, left=0.15, right=0.95, top=0.97, bottom=0.10)

    # (a) ΔP_es (MW)
    P_mw = traj['P_es'] * cfg.S_BASE
    for i in range(N):
        ax_a.plot(t, P_mw[:, i], color=colors[i], lw=1.2,
                  label=P_LABELS[i])
    ax_a.set_ylabel(r'(a) $\Delta\,P_{\mathrm{es}}$(MW)', fontsize=10)
    ax_a.set_xlim(0, t_max)
    paper_legend(ax_a, loc='upper right', ncol=2, fontsize=8,
                 handlelength=1.5, columnspacing=0.8)

    # (b) Δf_es (Hz)
    freq_dev = traj['freq'] - 50.0
    for i in range(N):
        ax_b.plot(t, freq_dev[:, i], color=colors[i], lw=1.2,
                  label=F_LABELS[i])
    ax_b.set_ylabel(r'(b) $\Delta\,f_{\mathrm{es}}$(Hz)', fontsize=10)
    ax_b.set_xlabel('Time (s)', fontsize=10)
    ax_b.set_xlim(0, t_max)
    ax_b.xaxis.set_major_locator(ticker.MultipleLocator(2))
    paper_legend(ax_b, loc='upper right', ncol=2, fontsize=8,
                 handlelength=1.5, columnspacing=0.8)

    plt.savefig(save_path, dpi=250, bbox_inches='tight')
    plt.close()
    print(f"  [Fig 13] {save_path}")


# ═══════════════════════════════════════════════════════
#  主函数
# ═══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="MADRL-SAC 评估 (全部论文图表)")
    parser.add_argument('--model', type=str, default=None)
    parser.add_argument('--test-episodes', type=int, default=50)
    parser.add_argument('--cpu', action='store_true')
    args = parser.parse_args()

    save_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'results')
    fig_dir = os.path.join(save_dir, 'figures_paper_style')
    os.makedirs(fig_dir, exist_ok=True)

    model_dir = args.model or os.path.join(save_dir, 'models', 'final')
    device = 'cuda' if torch.cuda.is_available() and not args.cpu else 'cpu'

    if not os.path.exists(model_dir):
        print(f"[ERROR] Model not found: {model_dir}")
        print("Run: python train.py")
        return

    # ── 加载模型 ──
    print(f"Loading model: {model_dir}")
    manager = MultiAgentManager(
        n_agents=cfg.N_AGENTS, obs_dim=cfg.OBS_DIM, action_dim=cfg.ACTION_DIM,
        hidden_sizes=cfg.HIDDEN_SIZES, device=device,
    )
    manager.load(model_dir)

    # ═════════════════════════════════════════════════
    #  Fig 4: 训练曲线
    # ═════════════════════════════════════════════════
    log_path = os.path.join(save_dir, 'training_log.npz')
    if os.path.exists(log_path):
        print("\n=== Fig 4: Training curves ===")
        plot_fig4(log_path, os.path.join(fig_dir, 'fig4_training_curves.png'))

    # ═════════════════════════════════════════════════
    #  Fig 5: 累积频率奖励 (50 test episodes)
    # ═════════════════════════════════════════════════
    n_test = cfg.N_TEST_SCENARIOS
    print(f"\n=== Fig 5: Cumulative reward ({n_test} test episodes) ===")
    print(f"    [P0 metadata] test_set: n={n_test}, seed={TEST_SEED}, "
          f"generator=generate_test_scenarios, config=cfg.N_TEST_SCENARIOS")
    test_scenarios = generate_test_scenarios(n=n_test, seed=TEST_SEED)
    test_result = run_test_set(manager, test_scenarios, include_adaptive=True)
    r_rl, r_fixed, r_adaptive = test_result
    plot_fig5(r_rl, r_fixed, os.path.join(fig_dir, 'fig5_cumulative_reward.png'),
              rewards_adaptive=r_adaptive)

    # ═════════════════════════════════════════════════
    #  Fig 6-7: Load Step 1
    # ═════════════════════════════════════════════════
    print("\n=== Fig 6-7: Load Step 1 ===")
    env_ls1 = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
    traj_nc_1 = run_episode(env_ls1, delta_u=LOAD_STEP_1, control_mode='fixed')
    traj_rl_1 = run_episode(env_ls1, manager=manager, delta_u=LOAD_STEP_1)
    plot_no_control(traj_nc_1, 'load step 1',
                    os.path.join(fig_dir, 'fig6_load_step1_no_ctrl.png'))
    plot_rl_control(traj_rl_1, 'load step 1',
                    os.path.join(fig_dir, 'fig7_load_step1_rl.png'))
    print(f"    No ctrl freq sync = {compute_freq_sync_reward(traj_nc_1['freq']):.4f}")
    print(f"    RL ctrl freq sync = {compute_freq_sync_reward(traj_rl_1['freq']):.4f}")

    # ═════════════════════════════════════════════════
    #  Fig 8-9: Load Step 2
    # ═════════════════════════════════════════════════
    print("\n=== Fig 8-9: Load Step 2 ===")
    env_ls2 = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
    traj_nc_2 = run_episode(env_ls2, delta_u=LOAD_STEP_2, control_mode='fixed')
    traj_rl_2 = run_episode(env_ls2, manager=manager, delta_u=LOAD_STEP_2)
    plot_no_control(traj_nc_2, 'load step 2',
                    os.path.join(fig_dir, 'fig8_load_step2_no_ctrl.png'))
    plot_rl_control(traj_rl_2, 'load step 2',
                    os.path.join(fig_dir, 'fig9_load_step2_rl.png'))
    print(f"    No ctrl freq sync = {compute_freq_sync_reward(traj_nc_2['freq']):.4f}")
    print(f"    RL ctrl freq sync = {compute_freq_sync_reward(traj_rl_2['freq']):.4f}")

    # ═════════════════════════════════════════════════
    #  Fig 10-11: 通信故障
    # ═════════════════════════════════════════════════
    print(f"\n=== Fig 10-11: Communication failure ({args.test_episodes} episodes) ===")
    # 剥离预烘焙的 fail_links，让 comm_fail_prob=0.3 独立控制链路故障
    base_scenarios = [(du, None) for du, _ in test_scenarios]
    r_rl_fail, _ = run_test_set(manager, base_scenarios, comm_fail_prob=0.3)
    plot_fig10(r_rl, r_rl_fail, r_fixed,
               os.path.join(fig_dir, 'fig10_comm_failure_reward.png'))
    print(f"    Normal avg = {np.mean(r_rl):.4f}")
    print(f"    Failure avg = {np.mean(r_rl_fail):.4f}")

    # Fig 11: 特定链路故障下时域
    env_fail = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0,
                           forced_link_failures=[(0, 1), (1, 0)])
    traj_rl_fail = run_episode(env_fail, manager=manager, delta_u=LOAD_STEP_1)
    plot_fig11(traj_rl_fail, os.path.join(fig_dir, 'fig11_comm_failure_td.png'))

    # ═════════════════════════════════════════════════
    #  Fig 12-13: 通信延迟
    # ═════════════════════════════════════════════════
    print(f"\n=== Fig 12-13: Communication delay ({args.test_episodes} episodes) ===")
    r_rl_delay, _ = run_test_set(manager, base_scenarios, comm_delay_steps=1)
    plot_fig12(r_rl, r_rl_delay, r_fixed,
               os.path.join(fig_dir, 'fig12_comm_delay_reward.png'))
    print(f"    Normal avg = {np.mean(r_rl):.4f}")
    print(f"    Delay avg  = {np.mean(r_rl_delay):.4f}")

    # Fig 13: 0.2s 通信延迟下时域
    env_delay = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0, comm_delay_steps=1)
    traj_rl_delay = run_episode(env_delay, manager=manager, delta_u=LOAD_STEP_1)
    plot_fig13(traj_rl_delay, os.path.join(fig_dir, 'fig13_comm_delay_td.png'))

    # ═════════════════════════════════════════════════
    #  汇总
    # ═════════════════════════════════════════════════
    print(f"\n{'='*60}")
    print(f"  All figures saved to: {fig_dir}")
    figs = [f for f in os.listdir(fig_dir) if f.startswith('fig')]
    for f in sorted(figs):
        print(f"    {f}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
