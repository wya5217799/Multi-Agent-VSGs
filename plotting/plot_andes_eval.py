"""
ANDES Kundur 评估图 — 论文 IEEE 风格 (Fig 5-13).
调用 paper_style.py 通用绘图函数.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
from plotting.paper_style import (
    plot_time_domain_2x2, plot_cumulative_reward, compute_freq_sync_reward,
    save_fig
)
from env.andes_vsg_env import AndesMultiVSGEnv
from agents.sac import SACAgent

# ── 配置 ──
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(BASE, 'results', 'andes_models_fixed')
SAVE_DIR = os.path.join(BASE, 'results', 'figures_paper_style')

N = 4
OBS_DIM = 7
ACTION_DIM = 2
HIDDEN = [128, 128, 128, 128]

# 无控制动作 (ΔM=0, ΔD=0)
_a0 = (0 - AndesMultiVSGEnv.DM_MIN) / (AndesMultiVSGEnv.DM_MAX - AndesMultiVSGEnv.DM_MIN) * 2 - 1
_a1 = (0 - AndesMultiVSGEnv.DD_MIN) / (AndesMultiVSGEnv.DD_MAX - AndesMultiVSGEnv.DD_MIN) * 2 - 1
FIXED_ACTION = np.array([_a0, _a1], dtype=np.float32)

K_ADAPTIVE_H = 5.0


def load_agents():
    agents = []
    for i in range(N):
        agent = SACAgent(obs_dim=OBS_DIM, action_dim=ACTION_DIM,
                         hidden_sizes=HIDDEN, buffer_size=10000, batch_size=256)
        path = os.path.join(MODEL_DIR, f'agent_{i}_final.pt')
        if os.path.exists(path):
            agent.load(path)
            print(f'  Loaded agent {i}')
        else:
            print(f'  [WARN] {path} not found')
        agents.append(agent)
    return agents


def run_episode(env, agents, use_rl=True, adaptive=False, deterministic=True):
    """运行一个 episode, 收集轨迹."""
    obs = env.reset()
    traj = {'time': [], 'freq_hz': [], 'P_es': [], 'M_es': [], 'D_es': []}

    for step in range(AndesMultiVSGEnv.STEPS_PER_EPISODE):
        if use_rl and agents is not None:
            actions = {i: agents[i].select_action(obs[i], deterministic=deterministic)
                       for i in range(N)}
        elif adaptive:
            actions = {}
            for i in range(N):
                delta_f = obs[i][0] if len(obs[i]) > 0 else 0.0
                dH = np.clip(-K_ADAPTIVE_H * delta_f,
                             AndesMultiVSGEnv.DM_MIN, AndesMultiVSGEnv.DM_MAX)
                a0 = (dH - AndesMultiVSGEnv.DM_MIN) / (AndesMultiVSGEnv.DM_MAX - AndesMultiVSGEnv.DM_MIN) * 2 - 1
                actions[i] = np.array([a0, _a1], dtype=np.float32)
        else:
            actions = {i: FIXED_ACTION.copy() for i in range(N)}

        obs, rewards, done, info = env.step(actions)
        traj['time'].append(info['time'])
        traj['freq_hz'].append(info['freq_hz'].copy())
        traj['P_es'].append(info['P_es'].copy())
        traj['M_es'].append(info['M_es'].copy())
        traj['D_es'].append(info['D_es'].copy())
        if done:
            break

    for key in traj:
        traj[key] = np.array(traj[key])
    return traj


def main():
    print('=' * 60)
    print(' ANDES Kundur Evaluation — Paper-style Figures')
    print('=' * 60)
    agents = load_agents()

    LS1 = {'PQ_0': -2.0}  # Load Step 1: 增负荷 2.0 p.u.
    LS2 = {'PQ_1': 2.0}   # Load Step 2: 甩负荷 2.0 p.u.

    # ── Fig 6-9: 时域仿真 ──
    for ls_name, delta_u, fig_nc, fig_rl in [
        ('Load Step 1', LS1, 'fig6_ls1_no_ctrl.png', 'fig7_ls1_ctrl.png'),
        ('Load Step 2', LS2, 'fig8_ls2_no_ctrl.png', 'fig9_ls2_ctrl.png'),
    ]:
        print(f'\n--- {ls_name} ---')
        env_nc = AndesMultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
        env_nc.reset(delta_u=delta_u)
        traj_nc = run_episode(env_nc, None, use_rl=False)
        fig = plot_time_domain_2x2(traj_nc, n_agents=N,
                                    fig_label=fig_nc.split('_')[0].replace('fig', 'Fig') + '-')
        save_fig(fig, SAVE_DIR, fig_nc)

        env_rl = AndesMultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
        env_rl.reset(delta_u=delta_u)
        traj_rl = run_episode(env_rl, agents, use_rl=True)
        fig = plot_time_domain_2x2(traj_rl, n_agents=N,
                                    fig_label=fig_rl.split('_')[0].replace('fig', 'Fig') + '-')
        save_fig(fig, SAVE_DIR, fig_rl)

    # ── Fig 5: 累积奖励 ──
    print('\n--- Fig 5: Cumulative Reward ---')
    n_test = 30
    results = {}
    for method_name, use_rl, adaptive in [
        ('No control', False, False),
        ('Adaptive inertia', False, True),
        ('Proposed MADRL', True, False),
    ]:
        rews = []
        for ep in range(n_test):
            env = AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=0.0)
            env.seed(1000 + ep)
            traj = run_episode(env, agents, use_rl=use_rl, adaptive=adaptive)
            rews.append(compute_freq_sync_reward(traj))
        results[method_name] = rews
        print(f'  {method_name}: avg={np.mean(rews):.4f}')
    fig = plot_cumulative_reward(results)
    save_fig(fig, SAVE_DIR, 'fig5_cumulative_reward.png')

    # ── Fig 10-11: 通信故障 ──
    print('\n--- Fig 10-11: Communication Failure ---')
    n_comm = 20
    rews_normal, rews_fixed, rews_fail = [], [], []
    for ep in range(n_comm):
        for use_rl, store in [(True, rews_normal), (False, rews_fixed)]:
            env = AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=0.0)
            env.seed(9999 + ep)
            store.append(compute_freq_sync_reward(
                run_episode(env, agents if use_rl else None, use_rl=use_rl)))
        env_f = AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=0.3)
        env_f.seed(9999 + ep)
        rews_fail.append(compute_freq_sync_reward(
            run_episode(env_f, agents, use_rl=True)))

    fig = plot_cumulative_reward(
        {'Proposed (normal)': rews_normal,
         'Proposed (failure)': rews_fail,
         'Without control': rews_fixed})
    save_fig(fig, SAVE_DIR, 'fig10_comm_failure_reward.png')

    env_f = AndesMultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0,
                              forced_link_failures=[(0, 1), (1, 0)])
    env_f.reset(delta_u=LS1)
    fig = plot_time_domain_2x2(run_episode(env_f, agents, use_rl=True),
                               n_agents=N, fig_label='Fig11-')
    save_fig(fig, SAVE_DIR, 'fig11_comm_failure_td.png')

    # ── Fig 12-13: 通信延迟 ──
    print('\n--- Fig 12-13: Communication Delay ---')
    rews_delay = []
    for ep in range(n_comm):
        env_d = AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=0.0,
                                  comm_delay_steps=1)
        env_d.seed(9999 + ep)
        rews_delay.append(compute_freq_sync_reward(
            run_episode(env_d, agents, use_rl=True)))

    fig = plot_cumulative_reward(
        {'Proposed (normal)': rews_normal,
         'Proposed (delay)': rews_delay,
         'Without control': rews_fixed})
    save_fig(fig, SAVE_DIR, 'fig12_comm_delay_reward.png')

    env_d = AndesMultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0,
                              comm_delay_steps=1)
    env_d.reset(delta_u=LS1)
    fig = plot_time_domain_2x2(run_episode(env_d, agents, use_rl=True),
                               n_agents=N, fig_label='Fig13-')
    save_fig(fig, SAVE_DIR, 'fig13_comm_delay_td.png')

    print('\n' + '=' * 60)
    print(f'All figures saved to {SAVE_DIR}')
    print('=' * 60)


if __name__ == '__main__':
    main()
