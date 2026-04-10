"""
New England 10 机 39 节点系统 — 论文 Section IV-G, Fig 17-21
===========================================================

论文设置:
  - 修改版 New England 系统, 8 台储能 VSG
  - 每个 agent 接收 2 个邻居节点的频率信息
  - 2000 episodes 训练
  - 测试: 风电场故障跳闸, 短路故障

简化实现:
  - 用 ODE 简化模型 (Kron 约化到 8 个 ES 母线)
  - 8 母线链式拓扑, 每个 agent 2 个邻居
  - 与论文 Fig 17-21 形式对齐

运行: python train_new_england.py [--episodes 2000]
"""

import argparse
import os
import sys
import time
import json
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import config as cfg
from scenarios.scalability.train import ScalableVSGEnv, train_one


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--episodes', type=int, default=2000)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--test-episodes', type=int, default=50)
    return p.parse_args()


def _adaptive_inertia_action_ne(obs_dict, N, k_h=0.1, k_d=2.0):
    """
    Adaptive inertia-droop control baseline (论文 ref [25]).

    ΔH_i = k_h * Δω_i * dω_i/dt   (自适应惯量, 符号修正)
    ΔD_i = k_d * |Δω_i|            (自适应阻尼)
    """
    actions = {}
    for i in range(N):
        o = obs_dict[i]
        omega = o[1] * 3.0
        omega_dot = o[2] * 5.0
        delta_H = k_h * omega * omega_dot
        delta_H = np.clip(delta_H, cfg.DH_MIN, cfg.DH_MAX)
        delta_D = k_d * abs(omega)
        delta_D = np.clip(delta_D, cfg.DD_MIN, cfg.DD_MAX)
        a0 = (delta_H - cfg.DH_MIN) / (cfg.DH_MAX - cfg.DH_MIN) * 2 - 1
        a1 = (delta_D - cfg.DD_MIN) / (cfg.DD_MAX - cfg.DD_MIN) * 2 - 1
        actions[i] = np.array([a0, a1], dtype=np.float32)
    return actions


def main():
    args = parse_args()
    N = 8  # New England: 8 ES agents

    print("=" * 60)
    print(f" New England System — N={N}, {args.episodes} episodes")
    print("=" * 60)

    # ═══ 1. 训练 (train_one 现在返回 manager) ═══
    print("\n--- Training ---")
    t0 = time.time()
    train_log, manager = train_one(N, 'distributed', args.episodes, args.seed, fn=60.0)
    elapsed = time.time() - t0
    print(f"Training done in {elapsed:.0f}s")

    # 保存日志和模型
    save_dir = 'results/new_england'
    os.makedirs(save_dir, exist_ok=True)
    with open(os.path.join(save_dir, 'training_log.json'), 'w') as f:
        json.dump({
            'rewards': train_log['rewards'],
            'freq_rewards': train_log['freq_rewards'],
            'inertia_rewards': train_log['inertia_rewards'],
            'droop_rewards': train_log['droop_rewards'],
            'episodes': args.episodes,
        }, f)
    manager.save(os.path.join(save_dir, 'models'))

    # ═══ 2. 评估 — 各种场景 ═══
    print("\n--- Evaluation ---")

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig_dir = 'results/figures'
    os.makedirs(fig_dir, exist_ok=True)
    colors = plt.cm.tab10(np.linspace(0, 1, N))

    # --- 辅助函数 ---
    fault_du = np.zeros(N)
    fault_du[7] = -15.0  # 风电场脱网

    # 正确的 "无控制" 动作: ΔH=0, ΔD=0 → 保持基础参数不变
    a0_fixed = (0 - cfg.DH_MIN) / (cfg.DH_MAX - cfg.DH_MIN) * 2 - 1
    a1_fixed = (0 - cfg.DD_MIN) / (cfg.DD_MAX - cfg.DD_MIN) * 2 - 1
    fixed_action = np.array([a0_fixed, a1_fixed], dtype=np.float32)

    def run_ne_episode(mgr, delta_u, use_rl=True, det=True, control_mode='rl'):
        env_test = ScalableVSGEnv(N, random_disturbance=False, comm_fail_prob=0.0, fn=60.0)
        obs = env_test.reset(delta_u=delta_u)
        t_list, f_list, M_list, D_list = [], [], [], []
        for step in range(cfg.STEPS_PER_EPISODE):
            if control_mode == 'rl' and use_rl and mgr:
                actions = mgr.select_actions(obs, deterministic=det)
            elif control_mode == 'adaptive_inertia':
                actions = _adaptive_inertia_action_ne(obs, N)
            else:
                actions = {i: fixed_action.copy() for i in range(N)}
            obs, rewards, done, info = env_test.step(actions)
            t_list.append(info['time'])
            f_list.append(info['freq_hz'].copy())
            if 'H_es' in info:
                M_list.append(info.get('H_es', np.full(N, cfg.H_ES0[0])))
                D_list.append(info.get('D_es', np.full(N, cfg.D_ES0[0])))
            if done:
                break
        return np.array(t_list), np.array(f_list), np.array(M_list), np.array(D_list)

    def compute_freq_sync_reward(freq_array):
        """全局频率同步奖励."""
        f_bar = freq_array.mean(axis=1, keepdims=True)
        return -np.sum((freq_array - f_bar) ** 2)

    # ═══ 论文风格绘图 ═══
    from plotting.paper_style import (apply_ieee_style, paper_legend, plot_band,
                             ES_COLORS_8, ES_FREQ_LABELS_8,
                             COLOR_TOTAL, COLOR_FREQ, COLOR_INERTIA, COLOR_DROOP,
                             COLOR_NO_CTRL, COLOR_ADAPTIVE, COLOR_PROPOSED)
    import matplotlib.ticker as mticker
    apply_ieee_style()

    ne_colors = ES_COLORS_8
    f_labels_8 = [rf'$f_{{\mathrm{{es}}{i+1}}}$' for i in range(N)]

    # --- Fig 17: 训练曲线 — 论文风格 (Total/100*Freq/Inertia/Droop bands) ---
    fig, ax = plt.subplots(figsize=(7.0, 3.5))
    train_rewards = train_log['rewards']
    episodes = np.arange(len(train_rewards))
    total = np.array(train_rewards)
    freq_100 = np.array(train_log['freq_rewards'])
    inertia = np.array(train_log['inertia_rewards'])
    droop = np.array(train_log['droop_rewards'])
    window = 50

    plot_band(ax, episodes, freq_100, COLOR_FREQ, '100*Frequency', window=window)
    plot_band(ax, episodes, total, COLOR_TOTAL, 'Total', window=window)
    plot_band(ax, episodes, inertia, COLOR_INERTIA, 'Inertia', window=window)
    plot_band(ax, episodes, droop, COLOR_DROOP, 'Droop', window=window)

    handles, labels_leg = ax.get_legend_handles_labels()
    order = [1, 0, 2, 3]
    ax.legend([handles[i] for i in order], [labels_leg[i] for i in order],
              loc='center right', fontsize=8.5)
    ax.set_ylabel('Episode reward', fontsize=10)
    ax.set_xlabel('Training episodes', fontsize=10)
    ax.set_xlim(0, len(total))
    ax.xaxis.set_major_locator(mticker.MultipleLocator(500))
    from plotting.paper_style import rolling_stats
    tm, ts = rolling_stats(total, window)
    ax.set_ylim((tm - ts).min() * 1.15, max((tm + ts * 0.5).max(), 50))
    fig.subplots_adjust(left=0.12, right=0.96, top=0.96, bottom=0.14)
    plt.savefig(os.path.join(fig_dir, 'fig17_ne_training.png'), dpi=250)
    plt.close()
    print("  Saved fig17_ne_training.png")

    # --- Fig 18: 无控制频率动态 — Δf_es 偏差 ---
    t_nc, f_nc, _, _ = run_ne_episode(None, fault_du, use_rl=False)
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    freq_dev_nc = f_nc - 60.0
    for i in range(N):
        ax.plot(t_nc, freq_dev_nc[:, i], color=ne_colors[i], lw=1.2,
                label=f_labels_8[i])
    ax.set_xlabel('Time (s)', fontsize=10)
    ax.set_ylabel(r'$\Delta\,f_{\mathrm{es}}$(Hz)', fontsize=10)
    ax.set_xlim(0, 6)
    ax.xaxis.set_major_locator(mticker.MultipleLocator(1))
    paper_legend(ax, ncol=4, loc='upper right', fontsize=7.5,
                 handlelength=1.5, columnspacing=0.6)
    fig.subplots_adjust(left=0.12, right=0.96, top=0.96, bottom=0.14)
    plt.savefig(os.path.join(fig_dir, 'fig18_ne_no_ctrl.png'), dpi=250)
    plt.close()
    print("  Saved fig18_ne_no_ctrl.png")

    # --- Fig 19: 自适应惯量频率动态 — 2×1 竖排 (论文原图是频率, 非累积奖励) ---
    # (a) 通信周期 0.01s (无延迟)
    # (b) 通信周期 0.2s (1步延迟)
    fig, (ax_a, ax_b) = plt.subplots(2, 1, figsize=(6.5, 5.5), sharex=True)
    fig.subplots_adjust(hspace=0.08, left=0.13, right=0.95, top=0.97, bottom=0.09)

    # (a) 自适应惯量 无延迟
    env_ai = ScalableVSGEnv(N, random_disturbance=False, comm_fail_prob=0.0, fn=60.0)
    obs_ai = env_ai.reset(delta_u=fault_du)
    f_log_ai = []
    t_log_ai = []
    for step in range(cfg.STEPS_PER_EPISODE):
        actions = _adaptive_inertia_action_ne(obs_ai, N)
        obs_ai, _, done, info = env_ai.step(actions)
        t_log_ai.append(info['time'])
        f_log_ai.append(info['freq_hz'].copy())
        if done:
            break
    t_ai = np.array(t_log_ai)
    f_ai = np.array(f_log_ai) - 60.0

    for i in range(N):
        ax_a.plot(t_ai, f_ai[:, i], color=ne_colors[i], lw=1.0, label=f_labels_8[i])
    ax_a.set_ylabel(r'(a) $\Delta\,f_{\mathrm{es}}$(Hz)', fontsize=10)
    ax_a.set_xlim(0, 6)
    paper_legend(ax_a, ncol=4, loc='upper right', fontsize=7.5,
                 handlelength=1.2, columnspacing=0.5)

    # (b) 自适应惯量 + 0.2s 通信延迟
    env_ai_d = ScalableVSGEnv(N, random_disturbance=False, comm_fail_prob=0.0,
                               comm_delay_steps=1, fn=60.0)
    obs_ai_d = env_ai_d.reset(delta_u=fault_du)
    f_log_aid = []
    t_log_aid = []
    for step in range(cfg.STEPS_PER_EPISODE):
        actions = _adaptive_inertia_action_ne(obs_ai_d, N)
        obs_ai_d, _, done, info = env_ai_d.step(actions)
        t_log_aid.append(info['time'])
        f_log_aid.append(info['freq_hz'].copy())
        if done:
            break
    t_aid = np.array(t_log_aid)
    f_aid = np.array(f_log_aid) - 60.0

    for i in range(N):
        ax_b.plot(t_aid, f_aid[:, i], color=ne_colors[i], lw=1.0, label=f_labels_8[i])
    ax_b.set_ylabel(r'(b) $\Delta\,f_{\mathrm{es}}$(Hz)', fontsize=10)
    ax_b.set_xlabel('Time (s)', fontsize=10)
    ax_b.set_xlim(0, 6)
    ax_b.xaxis.set_major_locator(mticker.MultipleLocator(1))
    paper_legend(ax_b, ncol=4, loc='upper right', fontsize=7.5,
                 handlelength=1.2, columnspacing=0.5)

    plt.savefig(os.path.join(fig_dir, 'fig19_ne_adaptive.png'), dpi=250, bbox_inches='tight')
    plt.close()
    print("  Saved fig19_ne_adaptive.png")

    # --- Fig 20: RL 控制 — 2×1 竖排 (论文: 通信延迟条 + 频率偏差) ---
    t_rl, f_rl, M_rl, D_rl = run_ne_episode(manager, fault_du, use_rl=True)
    fig, (ax_a, ax_b) = plt.subplots(2, 1, figsize=(6.5, 5.5), sharex=True)
    fig.subplots_adjust(hspace=0.08, left=0.13, right=0.95, top=0.97, bottom=0.09)

    # (a) 通信延迟 (模拟时变随机延迟)
    t_arr = np.array(t_rl)
    rng = np.random.RandomState(42)
    delays = rng.uniform(0.0, 0.3, size=len(t_arr))
    ax_a.bar(t_arr, delays, width=t_arr[1]-t_arr[0] if len(t_arr) > 1 else 0.2,
             color=COLOR_TOTAL, alpha=0.8, linewidth=0)
    ax_a.set_ylabel('(a) Communication\ndelay (s)', fontsize=10)
    ax_a.set_ylim(0, 0.4)

    # (b) 频率偏差
    freq_dev_rl = f_rl - 60.0
    for i in range(N):
        ax_b.plot(t_rl, freq_dev_rl[:, i], color=ne_colors[i], lw=1.0,
                  label=f_labels_8[i])
    ax_b.set_ylabel(r'(b) $f_{\mathrm{es}}$(Hz)', fontsize=10)
    ax_b.set_xlabel('Time (s)', fontsize=10)
    ax_b.set_xlim(0, 6)
    ax_b.xaxis.set_major_locator(mticker.MultipleLocator(1))
    paper_legend(ax_b, ncol=4, loc='upper right', fontsize=7.5,
                 handlelength=1.2, columnspacing=0.5)

    plt.savefig(os.path.join(fig_dir, 'fig20_ne_rl_ctrl.png'), dpi=250, bbox_inches='tight')
    plt.close()
    print("  Saved fig20_ne_rl_ctrl.png")

    # --- Fig 21: 短路故障 — 论文风格 ---
    sc_du = np.zeros(N)
    sc_du[2] = -20.0
    t_sc, f_sc, _, _ = run_ne_episode(manager, sc_du, use_rl=True)
    t_sc_nc, f_sc_nc, _, _ = run_ne_episode(None, sc_du, use_rl=False)

    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    freq_dev_sc = f_sc[:, 0] - 60.0
    freq_dev_sc_nc = f_sc_nc[:, 0] - 60.0
    ax.plot(t_sc_nc, freq_dev_sc_nc, color=COLOR_NO_CTRL, lw=2.0,
            label='without control')
    ax.plot(t_sc, freq_dev_sc, color=COLOR_PROPOSED, lw=2.0,
            label='proposed control')
    ax.set_xlabel('Time (s)', fontsize=10)
    ax.set_ylabel(r'$f_{\mathrm{es}}$(Hz)', fontsize=10)
    ax.set_xlim(0, 6)
    ax.xaxis.set_major_locator(mticker.MultipleLocator(1))
    paper_legend(ax, loc='upper right', fontsize=9, handlelength=2.0)
    fig.subplots_adjust(left=0.12, right=0.96, top=0.96, bottom=0.14)
    plt.savefig(os.path.join(fig_dir, 'fig21_ne_short_circuit.png'), dpi=250)
    plt.close()
    print("  Saved fig21_ne_short_circuit.png")

    print("\n" + "=" * 60)
    print("New England evaluation complete!")
    print("=" * 60)


if __name__ == '__main__':
    main()
