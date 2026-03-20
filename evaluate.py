"""
评估脚本 — 生成论文 Fig 4-13 所有图表

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

sys.path.insert(0, os.path.dirname(__file__))
import config as cfg
from env.multi_vsg_env import MultiVSGEnv
from agents.ma_manager import MultiAgentManager

COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
ES_LABELS = [f'ES{i+1}' for i in range(cfg.N_AGENTS)]

# ─── 论文测试场景 (从 config 读取) ───
LOAD_STEP_1 = cfg.LOAD_STEP_1
LOAD_STEP_2 = cfg.LOAD_STEP_2


# ═══════════════════════════════════════════════════════
#  通用工具函数
# ═══════════════════════════════════════════════════════

def _adaptive_inertia_action(obs_dict, k_h=2.0):
    """
    Adaptive inertia control baseline (论文 ref [25]).

    当频率下降 (Δω<0 且 dω/dt<0): 增大 H
    当频率恢复 (Δω<0 且 dω/dt>0): 减小 H
    D 不调整 (ΔD=0).

    ΔH_i = -k_h * Δω_i * dω_i/dt  (线性自适应)
    """
    actions = {}
    for i in range(cfg.N_AGENTS):
        o = obs_dict[i]
        # obs 已归一化: o[1]=omega/3, o[2]=omega_dot/5
        omega = o[1] * 3.0
        omega_dot = o[2] * 5.0

        # 自适应惯量修正
        delta_H = -k_h * omega * omega_dot
        delta_H = np.clip(delta_H, cfg.DH_MIN, cfg.DH_MAX)

        # 映射到 [-1, 1] 动作空间
        a0 = (delta_H - cfg.DH_MIN) / (cfg.DH_MAX - cfg.DH_MIN) * 2 - 1
        a1 = (0 - cfg.DD_MIN) / (cfg.DD_MAX - cfg.DD_MIN) * 2 - 1  # ΔD = 0
        actions[i] = np.array([a0, a1], dtype=np.float32)
    return actions


def run_episode(env, manager=None, delta_u=None, deterministic=True,
                control_mode='rl'):
    """
    运行一个 episode, 返回完整轨迹.

    control_mode: 'rl' | 'fixed' | 'adaptive_inertia'
    """
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
            a0 = (0 - cfg.DH_MIN) / (cfg.DH_MAX - cfg.DH_MIN) * 2 - 1
            a1 = (0 - cfg.DD_MIN) / (cfg.DD_MAX - cfg.DD_MIN) * 2 - 1
            actions = {i: np.array([a0, a1], dtype=np.float32)
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


def run_test_set(manager, n_episodes, comm_fail_prob=0.0, comm_delay_steps=0,
                 forced_link_failures=None, seed_base=9999,
                 include_adaptive=False):
    """跑一组测试 episode, 返回频率同步奖励列表."""
    env = MultiVSGEnv(random_disturbance=True, comm_fail_prob=comm_fail_prob,
                      comm_delay_steps=comm_delay_steps,
                      forced_link_failures=forced_link_failures)
    rewards_rl = []
    rewards_fixed = []
    rewards_adaptive = []
    for ep in range(n_episodes):
        env.seed(seed_base + ep)
        traj_r = run_episode(env, manager=manager, control_mode='rl')
        env.seed(seed_base + ep)
        traj_f = run_episode(env, control_mode='fixed')
        rewards_rl.append(compute_freq_sync_reward(traj_r['freq']))
        rewards_fixed.append(compute_freq_sync_reward(traj_f['freq']))
        if include_adaptive:
            env.seed(seed_base + ep)
            traj_a = run_episode(env, control_mode='adaptive_inertia')
            rewards_adaptive.append(compute_freq_sync_reward(traj_a['freq']))
    result = (np.array(rewards_rl), np.array(rewards_fixed))
    if include_adaptive:
        result = result + (np.array(rewards_adaptive),)
    return result


# ═══════════════════════════════════════════════════════
#  Fig 4: 训练曲线
# ═══════════════════════════════════════════════════════

def plot_fig4(log_path, save_path):
    """Fig 4: Training performance of the multiagent learning."""
    log = np.load(log_path)
    fig, axes = plt.subplots(1 + cfg.N_AGENTS, 1,
                             figsize=(10, 2.8 * (1 + cfg.N_AGENTS)), sharex=True)
    fig.suptitle('Fig 4. Training performance of the multiagent learning',
                 fontsize=13, fontweight='bold')
    window = 50
    sub_labels = ['(a)', '(b)', '(c)', '(d)', '(e)']
    titles = ['Total episode reward',
              'ES1 episode reward', 'ES2 episode reward',
              'ES3 episode reward', 'ES4 episode reward']
    keys = ['episode_total_rewards'] + [f'episode_rewards_agent_{i}' for i in range(cfg.N_AGENTS)]

    for idx, (ax, key) in enumerate(zip(axes, keys)):
        r = log[key]
        ax.plot(r, alpha=0.25, color='#6baed6', lw=0.5)
        if len(r) >= window:
            avg = np.convolve(r, np.ones(window) / window, mode='valid')
            ax.plot(np.arange(window - 1, len(r)), avg, '#2171b5', lw=2)
        ax.set_ylabel('Reward')
        ax.set_title(f'{sub_labels[idx]} {titles[idx]}', fontsize=10)
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel('Episode')
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  [Fig 4] {save_path}")


# ═══════════════════════════════════════════════════════
#  Fig 5: 累积频率奖励
# ═══════════════════════════════════════════════════════

def plot_fig5(rewards_rl, rewards_fixed, save_path, rewards_adaptive=None):
    """Fig 5. Cumulative reward on the test set (3 methods)."""
    fig, ax = plt.subplots(figsize=(8, 5))
    eps = np.arange(1, len(rewards_rl) + 1)
    ax.plot(eps, np.cumsum(rewards_rl), 'b-', lw=2,
            label=f'Proposed MADRL (avg={np.mean(rewards_rl):.2f})')
    if rewards_adaptive is not None:
        ax.plot(eps, np.cumsum(rewards_adaptive), 'g--', lw=2,
                label=f'Adaptive inertia [25] (avg={np.mean(rewards_adaptive):.2f})')
    ax.plot(eps, np.cumsum(rewards_fixed), 'r:', lw=2,
            label=f'Without control (avg={np.mean(rewards_fixed):.2f})')
    ax.set_xlabel('Test Episode')
    ax.set_ylabel('Cumulative Frequency Reward')
    ax.set_title('Fig 5. Cumulative reward on the test set')
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  [Fig 5] {save_path}")
    print(f"    Proposed: {np.mean(rewards_rl):.4f}")
    if rewards_adaptive is not None:
        print(f"    Adaptive: {np.mean(rewards_adaptive):.4f}")
    print(f"    No ctrl:  {np.mean(rewards_fixed):.4f}")


# ═══════════════════════════════════════════════════════
#  Fig 6/8: 无控制时域 (2×1)
# ═══════════════════════════════════════════════════════

def plot_no_control(traj, title_suffix, save_path):
    """Fig 6/8 style: system dynamics without proposed control."""
    fig, axes = plt.subplots(2, 1, figsize=(10, 7))
    fig.suptitle(f'System dynamics without the proposed control in {title_suffix}',
                 fontsize=13, fontweight='bold')

    # (a) Frequency
    ax = axes[0]
    for i in range(cfg.N_AGENTS):
        ax.plot(traj['t'], traj['freq'][:, i], color=COLORS[i], lw=1.5, label=ES_LABELS[i])
    ax.axhline(50, color='gray', ls=':', alpha=0.3)
    ax.set_ylabel('Frequency (Hz)')
    ax.set_title('(a) Frequency of ES buses')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # (b) Power
    ax = axes[1]
    for i in range(cfg.N_AGENTS):
        ax.plot(traj['t'], traj['P_es'][:, i], color=COLORS[i], lw=1.5, label=ES_LABELS[i])
    ax.axhline(0, color='gray', ls=':', alpha=0.3)
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('$\\Delta P_{es}$ (p.u.)')
    ax.set_title('(b) Output power of ES')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  [Fig] {save_path}")


# ═══════════════════════════════════════════════════════
#  Fig 7/9/11/13: RL 控制时域 (2×2)
# ═══════════════════════════════════════════════════════

def plot_rl_control(traj, title_suffix, save_path):
    """Fig 7/9/11/13 style: system dynamics with proposed control."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle(f'System dynamics with the proposed control in {title_suffix}',
                 fontsize=13, fontweight='bold')

    # (a) Frequency
    ax = axes[0, 0]
    for i in range(cfg.N_AGENTS):
        ax.plot(traj['t'], traj['freq'][:, i], color=COLORS[i], lw=1.5, label=ES_LABELS[i])
    ax.axhline(50, color='gray', ls=':', alpha=0.3)
    ax.set_ylabel('Frequency (Hz)')
    ax.set_title('(a) Frequency of ES buses')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # (b) Power
    ax = axes[0, 1]
    for i in range(cfg.N_AGENTS):
        ax.plot(traj['t'], traj['P_es'][:, i], color=COLORS[i], lw=1.5, label=ES_LABELS[i])
    ax.axhline(0, color='gray', ls=':', alpha=0.3)
    ax.set_ylabel('$\\Delta P_{es}$ (p.u.)')
    ax.set_title('(b) Output power of ES')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # (c) Inertia H
    ax = axes[1, 0]
    H_avg = traj['H_es'].mean(axis=1)
    for i in range(cfg.N_AGENTS):
        ax.plot(traj['t'], traj['H_es'][:, i], color=COLORS[i], lw=1.5, label=ES_LABELS[i])
    ax.plot(traj['t'], H_avg, 'k--', lw=1.5, alpha=0.7, label='$H_{avg}$')
    ax.axhline(cfg.H_ES0[0], color='gray', ls=':', alpha=0.4)
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Virtual Inertia $H_{es}$')
    ax.set_title('(c) Inertia parameter')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # (d) Droop D
    ax = axes[1, 1]
    D_avg = traj['D_es'].mean(axis=1)
    for i in range(cfg.N_AGENTS):
        ax.plot(traj['t'], traj['D_es'][:, i], color=COLORS[i], lw=1.5, label=ES_LABELS[i])
    ax.plot(traj['t'], D_avg, 'k--', lw=1.5, alpha=0.7, label='$D_{avg}$')
    ax.axhline(cfg.D_ES0[0], color='gray', ls=':', alpha=0.4)
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Virtual Droop $D_{es}$')
    ax.set_title('(d) Droop parameter')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  [Fig] {save_path}")


# ═══════════════════════════════════════════════════════
#  Fig 10/12: 累积奖励对比 (3 条线)
# ═══════════════════════════════════════════════════════

def plot_reward_comparison(rewards_dict, title, save_path):
    """Fig 10/12 style: cumulative reward comparison bar/line chart."""
    fig, ax = plt.subplots(figsize=(8, 5))
    styles = {'Proposed (normal)': ('b-', 2),
              'Proposed (failure)': ('g--', 2),
              'Proposed (delay)': ('g--', 2),
              'Without control': ('r:', 2)}

    for label, rewards in rewards_dict.items():
        eps = np.arange(1, len(rewards) + 1)
        ls, lw = styles.get(label, ('k-', 1.5))
        ax.plot(eps, np.cumsum(rewards), ls, lw=lw, label=f'{label} (avg={np.mean(rewards):.4f})')

    ax.set_xlabel('Test Episode')
    ax.set_ylabel('Cumulative Frequency Reward')
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  [Fig] {save_path}")


# ═══════════════════════════════════════════════════════
#  主函数
# ═══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="MADRL-SAC 评估 (全部论文图表)")
    parser.add_argument('--model', type=str, default=None)
    parser.add_argument('--test-episodes', type=int, default=50)
    parser.add_argument('--cpu', action='store_true')
    args = parser.parse_args()

    save_dir = os.path.join(os.path.dirname(__file__), 'results')
    fig_dir = os.path.join(save_dir, 'figures')
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
    print(f"\n=== Fig 5: Cumulative reward ({args.test_episodes} test episodes) ===")
    test_result = run_test_set(manager, args.test_episodes, include_adaptive=True)
    r_rl, r_fixed, r_adaptive = test_result
    plot_fig5(r_rl, r_fixed, os.path.join(fig_dir, 'fig5_cumulative_reward.png'),
              rewards_adaptive=r_adaptive)

    # ═════════════════════════════════════════════════
    #  Fig 6-7: Load Step 1 (bus 2 负荷突减)
    # ═════════════════════════════════════════════════
    print("\n=== Fig 6-7: Load Step 1 ===")
    env_ls1 = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
    traj_nc_1 = run_episode(env_ls1, manager=None, delta_u=LOAD_STEP_1)
    traj_rl_1 = run_episode(env_ls1, manager=manager, delta_u=LOAD_STEP_1)
    plot_no_control(traj_nc_1, 'load step 1', os.path.join(fig_dir, 'fig6_load_step1_no_ctrl.png'))
    plot_rl_control(traj_rl_1, 'load step 1', os.path.join(fig_dir, 'fig7_load_step1_rl.png'))
    print(f"    No ctrl freq sync = {compute_freq_sync_reward(traj_nc_1['freq']):.4f}")
    print(f"    RL ctrl freq sync = {compute_freq_sync_reward(traj_rl_1['freq']):.4f}")

    # ═════════════════════════════════════════════════
    #  Fig 8-9: Load Step 2 (bus 3 负荷突增)
    # ═════════════════════════════════════════════════
    print("\n=== Fig 8-9: Load Step 2 ===")
    env_ls2 = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
    traj_nc_2 = run_episode(env_ls2, manager=None, delta_u=LOAD_STEP_2)
    traj_rl_2 = run_episode(env_ls2, manager=manager, delta_u=LOAD_STEP_2)
    plot_no_control(traj_nc_2, 'load step 2', os.path.join(fig_dir, 'fig8_load_step2_no_ctrl.png'))
    plot_rl_control(traj_rl_2, 'load step 2', os.path.join(fig_dir, 'fig9_load_step2_rl.png'))
    print(f"    No ctrl freq sync = {compute_freq_sync_reward(traj_nc_2['freq']):.4f}")
    print(f"    RL ctrl freq sync = {compute_freq_sync_reward(traj_rl_2['freq']):.4f}")

    # ═════════════════════════════════════════════════
    #  Fig 10-11: 通信故障
    # ═════════════════════════════════════════════════
    print(f"\n=== Fig 10-11: Communication failure ({args.test_episodes} episodes) ===")
    # 随机通信故障测试集
    r_rl_fail, _ = run_test_set(manager, args.test_episodes, comm_fail_prob=0.3)
    plot_reward_comparison(
        {'Proposed (normal)': r_rl, 'Proposed (failure)': r_rl_fail, 'Without control': r_fixed},
        'Fig 10. Cumulative reward comparison under communication failure',
        os.path.join(fig_dir, 'fig10_comm_failure_reward.png'),
    )
    print(f"    Normal avg = {np.mean(r_rl):.4f}")
    print(f"    Failure avg = {np.mean(r_rl_fail):.4f}")

    # Fig 11: 特定链路故障 (ES1↔ES2) 下的时域仿真
    env_fail = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0,
                           forced_link_failures=[(0, 1), (1, 0)])
    traj_rl_fail = run_episode(env_fail, manager=manager, delta_u=LOAD_STEP_1)
    plot_rl_control(traj_rl_fail, 'load step 1 under communication failure',
                    os.path.join(fig_dir, 'fig11_comm_failure_td.png'))

    # ═════════════════════════════════════════════════
    #  Fig 12-13: 通信延迟
    # ═════════════════════════════════════════════════
    print(f"\n=== Fig 12-13: Communication delay ({args.test_episodes} episodes) ===")
    # 0.2s 延迟 = 1 个控制步
    r_rl_delay, _ = run_test_set(manager, args.test_episodes, comm_delay_steps=1)
    plot_reward_comparison(
        {'Proposed (normal)': r_rl, 'Proposed (delay)': r_rl_delay, 'Without control': r_fixed},
        'Fig 12. Cumulative reward comparison under communication delay',
        os.path.join(fig_dir, 'fig12_comm_delay_reward.png'),
    )
    print(f"    Normal avg = {np.mean(r_rl):.4f}")
    print(f"    Delay avg  = {np.mean(r_rl_delay):.4f}")

    # Fig 13: 0.2s 通信延迟下时域仿真
    env_delay = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0, comm_delay_steps=1)
    traj_rl_delay = run_episode(env_delay, manager=manager, delta_u=LOAD_STEP_1)
    plot_rl_control(traj_rl_delay, 'load step 1 under 0.2s communication delay',
                    os.path.join(fig_dir, 'fig13_comm_delay_td.png'))

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
