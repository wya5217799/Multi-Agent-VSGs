"""
评估脚本 — 生成论文 Fig 4-13 所有图表 (IEEE 论文风格)

用法:
    python evaluate.py                                           # 默认
    python evaluate.py --checkpoint ../results/checkpoints/best.pt
    python evaluate.py --mode simulink                           # Simulink 后端
    python evaluate.py --test-episodes 30                        # 测试集大小

Fig 4:  训练曲线 (5 subplots)
Fig 5:  累积奖励 (MADRL / adaptive / no-control)
Fig 6-7: Load Step 1 时域仿真 (有/无控制)
Fig 8-9: Load Step 2 时域仿真
Fig 10-11: 通信故障测试
Fig 12-13: 通信延迟测试

Reference: Yang et al., IEEE TPWRS 2023
"""

import argparse
import os
import sys
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from env.simulink.kundur_simulink_env import (
    KundurStandaloneEnv, KundurSimulinkEnv,
    N_AGENTS, F_NOM, DM_MIN, DM_MAX, DD_MIN, DD_MAX, VSG_M0, VSG_D0,
)
from env.simulink.sac_agent_standalone import SACAgent
from scenarios.kundur.config_simulink import (
    OBS_DIM, ACT_DIM, HIDDEN_SIZES, LR, GAMMA, TAU_SOFT,
    BUFFER_SIZE, BATCH_SIZE, WARMUP_STEPS,
    SCENARIO1_BUS, SCENARIO1_MAG,
    SCENARIO2_BUS, SCENARIO2_MAG,
    ADAPTIVE_KH, ADAPTIVE_KD,
    DIST_MIN, DIST_MAX,
)

# Import paper style from Multi-Agent VSGs project
from plotting.paper_style import (
    apply_ieee_style, paper_legend, rolling_stats, plot_band, save_fig,
    plot_time_domain_2x2, plot_cumulative_reward as plot_cum_reward_generic,
    plot_training_curves as plot_train_curves_generic,
    compute_freq_sync_reward,
    ES_COLORS_4,
    COLOR_TOTAL, COLOR_FREQ, COLOR_INERTIA, COLOR_DROOP,
    COLOR_NO_CTRL, COLOR_ADAPTIVE, COLOR_PROPOSED,
    COLOR_FAILURE, COLOR_DELAY, COLOR_AVG,
)


def parse_args():
    parser = argparse.ArgumentParser(description="评估 MARL-VSG on Kundur")
    parser.add_argument(
        "--checkpoint",
        default=os.path.join("..", "results", "checkpoints", "best.pt"),
    )
    parser.add_argument(
        "--mode", choices=["standalone", "simulink"], default="standalone"
    )
    parser.add_argument(
        "--log-file",
        default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', '..', 'results', 'sim_kundur', 'logs', 'training_log.json'),
    )
    parser.add_argument(
        "--fig-dir", default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', '..', 'results', 'sim_kundur', 'figures'),
    )
    parser.add_argument("--test-episodes", type=int, default=30)
    parser.add_argument("--comm-delay", type=int, default=0)
    return parser.parse_args()


# ═══════════════════════════════════════════════════════
#  通用工具函数
# ═══════════════════════════════════════════════════════

def make_env(mode, comm_delay=0, training=False):
    if mode == "standalone":
        return KundurStandaloneEnv(
            comm_delay_steps=comm_delay, training=training,
        )
    else:
        return KundurSimulinkEnv(
            comm_delay_steps=comm_delay, training=training,
        )


def _no_control_actions():
    """动作映射: ΔM=0, ΔD=0 → normalized action."""
    a0 = (0 - DM_MIN) / (DM_MAX - DM_MIN) * 2 - 1
    a1 = (0 - DD_MIN) / (DD_MAX - DD_MIN) * 2 - 1
    return np.full((N_AGENTS, 2), [a0, a1], dtype=np.float32)


def _adaptive_inertia_action(obs):
    """
    自适应惯量+阻尼控制基线 (Fu et al. 2022, 论文 ref [25]).
    ΔH = k_h * |Δω * dω/dt|, ΔD = k_d * |Δω|
    """
    actions = np.zeros((N_AGENTS, 2), dtype=np.float32)
    for i in range(N_AGENTS):
        omega = obs[i, 1] * 3.0      # de-normalize
        omega_dot = obs[i, 2] * 5.0
        delta_H = ADAPTIVE_KH * omega * omega_dot
        delta_D = ADAPTIVE_KD * abs(omega)
        delta_H = np.clip(delta_H, DM_MIN, DM_MAX)
        delta_D = np.clip(delta_D, DD_MIN, DD_MAX)
        actions[i, 0] = np.clip((delta_H - DM_MIN) / (DM_MAX - DM_MIN) * 2 - 1, -1, 1)
        actions[i, 1] = np.clip((delta_D - DD_MIN) / (DD_MAX - DD_MIN) * 2 - 1, -1, 1)
    return actions


def run_episode(env, agent=None, bus_idx=None, magnitude=None,
                control_mode='rl', seed=None):
    """运行一个 episode, 返回完整轨迹 dict."""
    if seed is not None:
        obs, _ = env.reset(seed=seed)
    else:
        obs, _ = env.reset()

    steps = int(env.T_EPISODE / env.DT)

    data = {
        'time': [], 'freq_hz': [], 'P_es': [],
        'M_es': [], 'D_es': [], 'reward': [],
    }

    for step in range(steps):
        # 扰动: t=0.5s
        if step == int(0.5 / env.DT):
            if magnitude is not None:
                env.apply_disturbance(bus_idx=bus_idx, magnitude=magnitude)

        # 控制动作
        if control_mode == 'rl' and agent is not None:
            actions = agent.select_actions_multi(obs, deterministic=True)
        elif control_mode == 'adaptive':
            actions = _adaptive_inertia_action(obs)
        else:
            actions = _no_control_actions()

        obs, rewards, terminated, truncated, info = env.step(actions)

        data['time'].append(info['sim_time'])
        data['freq_hz'].append(info['omega'] * F_NOM)
        data['P_es'].append(info['P_es'].copy())
        data['M_es'].append(info['M'].copy())
        data['D_es'].append(info['D'].copy())
        data['reward'].append(rewards.copy())

        if terminated:
            break

    for key in data:
        data[key] = np.array(data[key])

    return data


def run_test_set(env, agent, n_episodes, control_mode='rl', seed_base=9999):
    """跑一组测试 episode, 返回频率同步奖励列表."""
    rewards = []
    for ep in range(n_episodes):
        data = run_episode(
            env, agent=agent,
            bus_idx=None, magnitude=float(np.random.uniform(DIST_MIN, DIST_MAX)) * (1 if np.random.random() > 0.5 else -1),
            control_mode=control_mode, seed=seed_base + ep,
        )
        rewards.append(compute_freq_sync_reward(data))
    return np.array(rewards)


# ═══════════════════════════════════════════════════════
#  Fig 4: 训练曲线
# ═══════════════════════════════════════════════════════

def plot_fig4(log, fig_dir):
    """Fig 4: Training performance — 论文 IEEE 风格."""
    apply_ieee_style()

    rewards = log.get("episode_rewards", [])
    if not rewards:
        print("  No training data found.")
        return

    n_ep = len(rewards)
    episodes = np.arange(n_ep)
    total = np.array(rewards)
    window = min(50, n_ep // 4) if n_ep > 20 else max(1, n_ep // 2)

    fig = plt.figure(figsize=(7.5, 4.5))
    gs = GridSpec(1, 1, figure=fig, left=0.12, right=0.96, top=0.98, bottom=0.12)

    ax = fig.add_subplot(gs[0, 0])
    plot_band(ax, episodes, total, COLOR_TOTAL, 'Total', window=window)

    ax.set_ylabel('Episode\nreward', fontsize=10.5, rotation=0,
                  labelpad=35, va='center')
    ax.set_xlim(0, n_ep)
    ax.set_xlabel('(a) Training episodes', fontsize=10.5, labelpad=5)
    paper_legend(ax, loc='center right', fontsize=8.5)

    # Eval reward overlay
    evals = log.get("eval_rewards", [])
    if evals:
        ax2 = ax.twinx()
        eps = [e["episode"] for e in evals]
        rews = [e["reward"] for e in evals]
        ax2.plot(eps, rews, 'ko-', ms=3, lw=1, label='Eval')
        ax2.set_ylabel('Eval Reward', fontsize=9)
        paper_legend(ax2, loc='lower right', fontsize=7)

    save_fig(fig, fig_dir, 'fig4_training_curves.png')


# ═══════════════════════════════════════════════════════
#  Fig 5: 累积频率奖励
# ═══════════════════════════════════════════════════════

def plot_fig5(rewards_rl, rewards_fixed, rewards_adaptive, fig_dir):
    """Fig 5: Cumulative reward on test set."""
    rewards_dict = {
        'Proposed MADRL': rewards_rl.tolist(),
        'Adaptive inertia': rewards_adaptive.tolist(),
        'Without control': rewards_fixed.tolist(),
    }
    fig = plot_cum_reward_generic(rewards_dict, fig_label='(a)')
    save_fig(fig, fig_dir, 'fig5_cumulative_reward.png')


# ═══════════════════════════════════════════════════════
#  Fig 6-9: Load Step 时域仿真
# ═══════════════════════════════════════════════════════

def plot_load_step_figs(data_rl, data_nc, data_ad, scenario_name,
                        fig_nums, fig_dir):
    """Fig 6-9: Load step with/without control — 2×2 时域图."""

    # Fig N: Without control
    fig_nc = plot_time_domain_2x2(
        {'time': data_nc['time'], 'freq_hz': data_nc['freq_hz'],
         'P_es': data_nc['P_es'], 'M_es': data_nc['M_es'],
         'D_es': data_nc['D_es']},
        n_agents=N_AGENTS, f_nom=F_NOM,
        fig_label=f'Fig{fig_nums[0]}-',
    )
    save_fig(fig_nc, fig_dir,
             f'fig{fig_nums[0]}_{scenario_name}_no_control.png')

    # Fig N+1: With RL control
    fig_rl = plot_time_domain_2x2(
        {'time': data_rl['time'], 'freq_hz': data_rl['freq_hz'],
         'P_es': data_rl['P_es'], 'M_es': data_rl['M_es'],
         'D_es': data_rl['D_es']},
        n_agents=N_AGENTS, f_nom=F_NOM,
        fig_label=f'Fig{fig_nums[1]}-',
    )
    save_fig(fig_rl, fig_dir,
             f'fig{fig_nums[1]}_{scenario_name}_rl_control.png')


# ═══════════════════════════════════════════════════════
#  Fig 10-11: 通信故障测试
# ═══════════════════════════════════════════════════════

def plot_fig10_11(rewards_normal, rewards_failure, data_fail, fig_dir):
    """Fig 10: Cumulative reward, Fig 11: Time-domain under failure."""
    # Fig 10: Cumulative reward comparison
    rewards_dict = {
        'Proposed (normal)': rewards_normal.tolist(),
        'Proposed (failure)': rewards_failure.tolist(),
    }
    fig10 = plot_cum_reward_generic(rewards_dict, fig_label='(a)')
    save_fig(fig10, fig_dir, 'fig10_comm_failure_reward.png')

    # Fig 11: Time-domain under 100% comm failure
    fig11 = plot_time_domain_2x2(
        {'time': data_fail['time'], 'freq_hz': data_fail['freq_hz'],
         'P_es': data_fail['P_es'], 'M_es': data_fail['M_es'],
         'D_es': data_fail['D_es']},
        n_agents=N_AGENTS, f_nom=F_NOM,
        fig_label='Fig11-',
    )
    save_fig(fig11, fig_dir, 'fig11_comm_failure_timedomain.png')


# ═══════════════════════════════════════════════════════
#  Fig 12-13: 通信延迟测试
# ═══════════════════════════════════════════════════════

def plot_fig12_13(delay_results, fig_dir):
    """Fig 12: Cumulative reward vs delay, Fig 13: Time-domain."""
    apply_ieee_style()

    # Fig 12: Cumulative reward for different delays
    rewards_dict = {}
    for delay, rewards in delay_results.items():
        label = f'delay={delay}' if delay > 0 else 'no delay'
        rewards_dict[label] = rewards.tolist()

    fig12 = plot_cum_reward_generic(rewards_dict, fig_label='(a)')
    save_fig(fig12, fig_dir, 'fig12_comm_delay_reward.png')

    # Fig 13: Bar chart of total reward vs delay
    fig13, ax = plt.subplots(figsize=(4.5, 3.2))
    delays = sorted(delay_results.keys())
    means = [np.mean(delay_results[d]) for d in delays]
    stds = [np.std(delay_results[d]) for d in delays]

    bars = ax.bar(range(len(delays)), means, yerr=stds,
                  color=[COLOR_PROPOSED if d == 0 else COLOR_DELAY for d in delays],
                  capsize=4, edgecolor='black', linewidth=0.5)
    ax.set_xticks(range(len(delays)))
    ax.set_xticklabels([f'{d} step' + ('s' if d != 1 else '') for d in delays])
    ax.set_ylabel('Mean Freq Sync Reward', fontsize=9)
    ax.set_xlabel('(b) Communication delay', fontsize=10)

    save_fig(fig13, fig_dir, 'fig13_comm_delay_bar.png')


# ═══════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════

def main():
    args = parse_args()
    os.makedirs(args.fig_dir, exist_ok=True)

    # Load agent
    agent = SACAgent(
        obs_dim=OBS_DIM, act_dim=ACT_DIM,
        hidden_sizes=HIDDEN_SIZES,
        lr=LR, gamma=GAMMA, tau=TAU_SOFT,
        buffer_size=BUFFER_SIZE, batch_size=BATCH_SIZE,
        warmup_steps=WARMUP_STEPS, reward_scale=1e-3,
    )
    if os.path.exists(args.checkpoint):
        agent.load(args.checkpoint)
    else:
        print(f"WARNING: {args.checkpoint} not found. Using random policy.")

    # ── Fig 4: 训练曲线 ──
    print("\n=== Fig 4: Training Curves ===")
    if os.path.exists(args.log_file):
        with open(args.log_file) as f:
            log = json.load(f)
        plot_fig4(log, args.fig_dir)
    else:
        print(f"  No log at {args.log_file}")

    # ── Fig 5: 累积奖励 (测试集) ──
    print("\n=== Fig 5: Cumulative Reward ===")
    env = make_env(args.mode, comm_delay=0, training=False)
    np.random.seed(42)
    rewards_rl = run_test_set(env, agent, args.test_episodes, 'rl')
    rewards_nc = run_test_set(env, agent, args.test_episodes, 'none')
    rewards_ad = run_test_set(env, agent, args.test_episodes, 'adaptive')
    plot_fig5(rewards_rl, rewards_nc, rewards_ad, args.fig_dir)
    print(f"  RL: {np.mean(rewards_rl):.2f}, NC: {np.mean(rewards_nc):.2f}, "
          f"AD: {np.mean(rewards_ad):.2f}")

    # ── Fig 6-7: Load Step 1 ──
    print("\n=== Fig 6-7: Load Step 1 ===")
    data_rl = run_episode(env, agent, SCENARIO1_BUS, SCENARIO1_MAG, 'rl', seed=100)
    data_nc = run_episode(env, None, SCENARIO1_BUS, SCENARIO1_MAG, 'none', seed=100)
    data_ad = run_episode(env, None, SCENARIO1_BUS, SCENARIO1_MAG, 'adaptive', seed=100)
    plot_load_step_figs(data_rl, data_nc, data_ad, 'load_step1', (6, 7), args.fig_dir)

    # ── Fig 8-9: Load Step 2 ──
    print("\n=== Fig 8-9: Load Step 2 ===")
    data_rl = run_episode(env, agent, SCENARIO2_BUS, SCENARIO2_MAG, 'rl', seed=200)
    data_nc = run_episode(env, None, SCENARIO2_BUS, SCENARIO2_MAG, 'none', seed=200)
    data_ad = run_episode(env, None, SCENARIO2_BUS, SCENARIO2_MAG, 'adaptive', seed=200)
    plot_load_step_figs(data_rl, data_nc, data_ad, 'load_step2', (8, 9), args.fig_dir)
    env.close()

    # ── Fig 10-11: 通信故障 ──
    print("\n=== Fig 10-11: Communication Failure ===")
    env_normal = make_env(args.mode, comm_delay=0, training=False)
    rewards_normal = run_test_set(env_normal, agent, args.test_episodes, 'rl')

    # 30% link failure
    env_fail = make_env(args.mode, comm_delay=0, training=False)
    env_fail._comm_mask = np.zeros((N_AGENTS, 2), dtype=bool)
    rewards_fail = run_test_set(env_fail, agent, args.test_episodes, 'rl')

    # 100% failure time-domain
    data_fail = run_episode(env_fail, agent, SCENARIO1_BUS, SCENARIO1_MAG, 'rl', seed=300)
    plot_fig10_11(rewards_normal, rewards_fail, data_fail, args.fig_dir)
    env_normal.close()
    env_fail.close()

    # ── Fig 12-13: 通信延迟 ──
    print("\n=== Fig 12-13: Communication Delay ===")
    delay_results = {}
    for delay in [0, 1, 3, 5]:
        env_d = make_env(args.mode, comm_delay=delay, training=False)
        delay_results[delay] = run_test_set(
            env_d, agent, args.test_episodes, 'rl'
        )
        env_d.close()
        print(f"  delay={delay}: mean={np.mean(delay_results[delay]):.2f}")

    plot_fig12_13(delay_results, args.fig_dir)

    print(f"\n=== All figures saved to {args.fig_dir} ===")


if __name__ == "__main__":
    main()
