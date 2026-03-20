"""
可扩展性实验 — 论文 Section IV-F, Fig 14-15
============================================

对比分布式 MADRL vs 集中式 DRL 在 N=2,4,8 下的训练性能和控制效果.
论文核心结论:
  - 集中式 DRL 网络维度随 N 增长, N=8 时训练不稳定
  - 分布式 MADRL 网络维度不变, 各规模下均稳定收敛

运行: python train_scalability.py [--n_agents 2|4|8] [--method distributed|centralized|both]
"""

import argparse
import os
import sys
import time
import json
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as cfg
from env.power_system import PowerSystem
from env.network_topology import build_laplacian, CommunicationGraph
from env.multi_vsg_env import MultiVSGEnv
from agents.ma_manager import MultiAgentManager
from agents.centralized_sac import CentralizedSACManager


# ═══════════════════════════════════════════════════════
#  可变 N 的环境工厂
# ═══════════════════════════════════════════════════════

def make_ring_topology(N):
    """环形通信拓扑: i ↔ (i+1)%N."""
    adj = {}
    for i in range(N):
        adj[i] = [(i - 1) % N, (i + 1) % N]
    return adj


def make_chain_laplacian(N, b_intra=10.0, b_tie=2.0):
    """链式/环形电气网络 Laplacian.

    两两相连, 区域内连接强 (b_intra), 跨区域连接弱 (b_tie).
    Area 1: bus 0..N//2-1,  Area 2: bus N//2..N-1
    """
    B = np.zeros((N, N))
    for i in range(N):
        j = (i + 1) % N
        # 同区域 → 强连接, 跨区域 → 弱连接
        area_i = 0 if i < N // 2 else 1
        area_j = 0 if j < N // 2 else 1
        b = b_intra if area_i == area_j else b_tie
        B[i, j] = b
        B[j, i] = b

    V = np.ones(N)
    return build_laplacian(B, V)


class ScalableVSGEnv:
    """可变规模的 VSG 环境 (基于 ODE 简化模型)."""

    def __init__(self, n_agents, random_disturbance=True, comm_fail_prob=0.1):
        self.N = n_agents
        self.random_disturbance = random_disturbance
        self.max_neighbors = 2  # 环形拓扑

        # 构建网络
        self.L = make_chain_laplacian(n_agents)
        self.comm_adj = make_ring_topology(n_agents)
        self.comm = CommunicationGraph(self.comm_adj, fail_prob=comm_fail_prob)

        # 系统参数
        self.H_es0 = np.full(n_agents, 3.0)
        self.D_es0 = np.full(n_agents, 2.0)

        self.ps = PowerSystem(self.L, self.H_es0, self.D_es0, dt=cfg.DT)
        self.rng = np.random.default_rng()

        self.obs_dim = 3 + 2 * self.max_neighbors  # = 7
        self.step_count = 0

    def seed(self, s):
        self.rng = np.random.default_rng(s)

    def reset(self, delta_u=None):
        if delta_u is not None:
            self.current_delta_u = delta_u.copy()
        elif self.random_disturbance:
            n_disturbed = self.rng.integers(1, min(3, self.N + 1))
            buses = self.rng.choice(self.N, size=n_disturbed, replace=False)
            self.current_delta_u = np.zeros(self.N)
            for bus in buses:
                mag = self.rng.uniform(cfg.DISTURBANCE_MIN, cfg.DISTURBANCE_MAX)
                self.current_delta_u[bus] = self.rng.choice([-1, 1]) * mag
        else:
            self.current_delta_u = np.zeros(self.N)

        self.ps.reset(delta_u=self.current_delta_u)
        self.step_count = 0
        self.comm.reset(rng=self.rng)
        return self._build_obs(self.ps.get_state())

    def step(self, actions):
        H_es = np.copy(self.H_es0)
        D_es = np.copy(self.D_es0)
        delta_H = np.zeros(self.N)
        delta_D = np.zeros(self.N)

        for i in range(self.N):
            a = np.clip(actions[i], -1.0, 1.0)
            delta_H[i] = (a[0] + 1) / 2 * (cfg.DH_MAX - cfg.DH_MIN) + cfg.DH_MIN
            delta_D[i] = (a[1] + 1) / 2 * (cfg.DD_MAX - cfg.DD_MIN) + cfg.DD_MIN
            H_es[i] = max(self.H_es0[i] + delta_H[i], 0.1)
            D_es[i] = max(self.D_es0[i] + delta_D[i], 0.1)

        self.ps.set_params(H_es, D_es)
        result = self.ps.step()
        self.step_count += 1

        obs = self._build_obs(result)
        rewards = self._compute_rewards(result)
        done = self.step_count >= cfg.STEPS_PER_EPISODE

        # 添加 H/D 到 info
        result['H_es'] = H_es.copy()
        result['D_es'] = D_es.copy()

        return obs, rewards, done, result

    def _build_obs(self, state):
        obs = {}
        for i in range(self.N):
            o = np.zeros(self.obs_dim, dtype=np.float32)
            o[0] = state['P_es'][i] / 15.0
            o[1] = state['omega'][i] / 3.0
            o[2] = state['omega_dot'][i] / 5.0
            neighbors = self.comm.get_neighbors(i)
            for k, j in enumerate(neighbors):
                if k >= self.max_neighbors:
                    break
                if self.comm.is_link_active(i, j):
                    o[3 + k] = state['omega'][j] / 3.0
                    o[3 + self.max_neighbors + k] = state['omega_dot'][j] / 5.0
            obs[i] = o
        return obs

    def _compute_rewards(self, state):
        rewards = {}
        for i in range(self.N):
            omega_i = state['omega'][i]
            neighbors = self.comm.get_neighbors(i)
            sum_w, n_active = omega_i, 1
            for j in neighbors:
                if self.comm.is_link_active(i, j):
                    sum_w += state['omega'][j]
                    n_active += 1
            omega_bar = sum_w / n_active

            r_f = -(omega_i - omega_bar) ** 2
            for j in neighbors:
                if self.comm.is_link_active(i, j):
                    r_f -= (state['omega'][j] - omega_bar) ** 2
            rewards[i] = cfg.PHI_F * r_f
        return rewards


# ═══════════════════════════════════════════════════════
#  训练函数
# ═══════════════════════════════════════════════════════

def train_one(n_agents, method, n_episodes, seed=42):
    """训练一种方法, 返回 (训练日志, manager)."""
    obs_dim = 7
    action_dim = 2
    hidden = cfg.HIDDEN_SIZES

    if method == 'distributed':
        manager = MultiAgentManager(
            n_agents=n_agents, obs_dim=obs_dim, action_dim=action_dim,
            hidden_sizes=hidden, buffer_size=cfg.BUFFER_SIZE,
            batch_size=cfg.BATCH_SIZE,
        )
    else:
        manager = CentralizedSACManager(
            n_agents=n_agents, obs_dim_per_agent=obs_dim,
            action_dim_per_agent=action_dim, hidden_sizes=hidden,
            buffer_size=cfg.BUFFER_SIZE, batch_size=cfg.BATCH_SIZE,
        )

    env = ScalableVSGEnv(n_agents, random_disturbance=True)
    total_rewards = []
    total_steps = 0
    warmup = cfg.WARMUP_STEPS

    for ep in range(n_episodes):
        env.seed(seed + ep)
        obs = env.reset()
        ep_reward = 0.0

        for step in range(cfg.STEPS_PER_EPISODE):
            if total_steps < warmup:
                actions = {i: np.random.uniform(-1, 1, size=action_dim)
                           for i in range(n_agents)}
            else:
                actions = manager.select_actions(obs)

            next_obs, rewards, done, info = env.step(actions)
            manager.store_transitions(obs, actions, rewards, next_obs, float(done))
            ep_reward += sum(rewards.values())

            if total_steps >= warmup:
                manager.update()

            obs = next_obs
            total_steps += 1
            if done:
                break

        total_rewards.append(ep_reward)

        if (ep + 1) % 100 == 0:
            avg = np.mean(total_rewards[-100:])
            print(f"    N={n_agents} {method}: Ep {ep+1}/{n_episodes} "
                  f"avg_reward={avg:.1f}")

    return total_rewards, manager


def compute_test_reward(n_agents, manager, n_test=50, seed=2000):
    """计算测试集上的全局频率奖励."""
    env = ScalableVSGEnv(n_agents, random_disturbance=True, comm_fail_prob=0.0)
    rewards_list = []

    for ep in range(n_test):
        env.seed(seed + ep)
        obs = env.reset()
        ep_reward = 0.0

        for step in range(cfg.STEPS_PER_EPISODE):
            actions = manager.select_actions(obs, deterministic=True)
            obs, rewards, done, info = env.step(actions)

            # 全局频率同步奖励
            omega = info['omega']
            omega_bar = omega.mean()
            ep_reward -= np.sum((omega - omega_bar) ** 2)

            if done:
                break

        rewards_list.append(ep_reward)

    return rewards_list


# ═══════════════════════════════════════════════════════
#  主程序
# ═══════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--n_agents', type=int, nargs='+', default=[2, 4, 8])
    p.add_argument('--method', choices=['distributed', 'centralized', 'both'],
                   default='both')
    p.add_argument('--episodes', type=int, default=2000)
    p.add_argument('--seed', type=int, default=42)
    return p.parse_args()


def main():
    args = parse_args()

    methods = ['distributed', 'centralized'] if args.method == 'both' else [args.method]
    results = {}

    print("=" * 60)
    print(f" Scalability Experiment: N={args.n_agents}, {args.episodes} episodes")
    print("=" * 60)

    for N in args.n_agents:
        for method in methods:
            key = f"N{N}_{method}"
            print(f"\n--- Training {key} ---")
            t0 = time.time()
            rewards, _ = train_one(N, method, args.episodes, args.seed)
            elapsed = time.time() - t0
            print(f"    Done in {elapsed:.0f}s, final avg={np.mean(rewards[-100:]):.1f}")
            results[key] = rewards

    # 保存日志
    save_dir = 'results/scalability'
    os.makedirs(save_dir, exist_ok=True)
    log = {k: v for k, v in results.items()}
    with open(os.path.join(save_dir, 'scalability_log.json'), 'w') as f:
        json.dump(log, f)

    # 画图
    plot_results(results, args.n_agents, methods, args.episodes, save_dir)


def plot_results(results, n_agents_list, methods, n_episodes, save_dir):
    """生成 Fig 14 和 Fig 15."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig_dir = 'results/figures'
    os.makedirs(fig_dir, exist_ok=True)

    # ═══ Fig 14: 训练曲线对比 ═══
    n_plots = len(n_agents_list)
    fig, axes = plt.subplots(1, n_plots, figsize=(5 * n_plots, 4))
    if n_plots == 1:
        axes = [axes]
    fig.suptitle('Fig 14. Training performance comparison', fontsize=14)

    window = max(1, n_episodes // 20)
    labels = {'distributed': 'Proposed (distributed)', 'centralized': 'Centralized DRL'}
    colors = {'distributed': '#1f77b4', 'centralized': '#d62728'}

    for idx, N in enumerate(n_agents_list):
        ax = axes[idx]
        for method in methods:
            key = f"N{N}_{method}"
            if key not in results:
                continue
            r = results[key]
            sm = np.convolve(r, np.ones(window)/window, mode='valid')
            ax.plot(r, alpha=0.15, color=colors[method])
            ax.plot(range(window-1, len(r)), sm, color=colors[method],
                    lw=2, label=labels[method])
        ax.set_title(f'N = {N}')
        ax.set_xlabel('Episode')
        ax.set_ylabel('Total Reward')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path14 = os.path.join(fig_dir, 'fig14_scalability_training.png')
    plt.savefig(path14, dpi=150)
    print(f"\nSaved {path14}")

    # ═══ Fig 15: 累积奖励对比 ═══
    fig, axes = plt.subplots(1, n_plots, figsize=(5 * n_plots, 4))
    if n_plots == 1:
        axes = [axes]
    fig.suptitle('Fig 15. Cumulative reward comparison', fontsize=14)

    for idx, N in enumerate(n_agents_list):
        ax = axes[idx]
        for method in methods:
            key = f"N{N}_{method}"
            if key not in results:
                continue
            # 用最后 50 个 episode 作为测试集性能估算
            test_rewards = results[key][-50:]
            cum = np.cumsum(test_rewards)
            ax.plot(range(1, 51), cum, color=colors[method], lw=2,
                    label=f'{labels[method]} (avg={np.mean(test_rewards):.1f})')
        ax.set_title(f'N = {N}')
        ax.set_xlabel('Test Episode')
        ax.set_ylabel('Cumulative Reward')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path15 = os.path.join(fig_dir, 'fig15_scalability_cumulative.png')
    plt.savefig(path15, dpi=150)
    print(f"Saved {path15}")


if __name__ == '__main__':
    main()
