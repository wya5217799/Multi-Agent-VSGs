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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import config as cfg
from env.power_system import PowerSystem
from env.network_topology import build_laplacian, CommunicationGraph
from env.multi_vsg_env import MultiVSGEnv
from agents.ma_manager import MultiAgentManager
from agents.centralized_sac import CentralizedSACManager
from utils.ode_events import DisturbanceEvent, EventSchedule


# ═══════════════════════════════════════════════════════
#  可变 N 的环境工厂
# ═══════════════════════════════════════════════════════

def make_ring_topology(N):
    """环形通信拓扑: i ↔ (i+1)%N."""
    adj = {}
    for i in range(N):
        adj[i] = [(i - 1) % N, (i + 1) % N]
    return adj


def make_chain_BV(N, b_intra=10.0, b_tie=2.0):
    """链式/环形电气网络 B 矩阵和母线电压向量 (M6a: 供 LineTripEvent/nonlinear 用).

    Area 1: bus 0..N//2-1,  Area 2: bus N//2..N-1
    """
    B = np.zeros((N, N))
    for i in range(N):
        j = (i + 1) % N
        area_i = 0 if i < N // 2 else 1
        area_j = 0 if j < N // 2 else 1
        b = b_intra if area_i == area_j else b_tie
        B[i, j] = b
        B[j, i] = b
    V = np.ones(N)
    return B, V


def make_chain_laplacian(N, b_intra=10.0, b_tie=2.0):
    """链式/环形电气网络 Laplacian."""
    B, V = make_chain_BV(N, b_intra, b_tie)
    return build_laplacian(B, V)


class ScalableVSGEnv:
    """可变规模的 VSG 环境 (基于 ODE 简化模型)."""

    def __init__(self, n_agents, random_disturbance=True, comm_fail_prob=0.1,
                 comm_delay_steps=0, fn=50.0, governor_enabled=False,
                 network_mode='linear', comm_delay_gaussian=None):
        """
        M7 (2026-04-21) 时变时延三要素:
            comm_delay_gaussian = {
                'mean_range': (mu_lo, mu_hi),   # 每条链路 μ_ij ~ U(lo, hi)
                'std': float,                    # 全链路共享 σ
                'rng_seed': int,                 # 可复现
            }
            - 高斯分布: 每步每链路 d ~ N(μ_ij, σ), clip ≥ 0
            - 多链路不同均值: μ_ij 由 rng_seed 固定, 跨 reset 可复用 (同 env 内)
            - 真实进入观测链路: delay 决定 obs 从哪个历史 tick 取邻居 ω/ω̇
            - 记录 _delay_trace: 供 Fig.20(a) 画柱图与 (b) 频率共用同一序列

        与 comm_delay_steps 互斥 (同时传报错).
        """
        self.N = n_agents
        self.random_disturbance = random_disturbance
        self.max_neighbors = 2  # 环形拓扑
        self.comm_delay_steps = comm_delay_steps

        # M7 时变时延校验
        if comm_delay_gaussian is not None and comm_delay_steps > 0:
            raise ValueError(
                "comm_delay_steps 与 comm_delay_gaussian 互斥, 不能同时传入"
            )
        self.comm_delay_gaussian = comm_delay_gaussian

        # M6a: 构建 B, V, L 并保存（LineTripEvent / nonlinear 共用前置）
        self.B_matrix, self.V_bus = make_chain_BV(n_agents)
        self.L = build_laplacian(self.B_matrix, self.V_bus)
        self.comm_adj = make_ring_topology(n_agents)
        self.comm = CommunicationGraph(self.comm_adj, fail_prob=comm_fail_prob)

        # 系统参数 (从 config 读取基值)
        self.H_es0 = np.full(n_agents, cfg.H_ES0[0])
        self.D_es0 = np.full(n_agents, cfg.D_ES0[0])

        self.fn = fn

        # M8b (2026-04-21): nonlinear 模式放开，B/V 已保存并透传给 PowerSystem
        if network_mode not in ('linear', 'nonlinear'):
            raise ValueError(
                f"network_mode must be 'linear' or 'nonlinear', got {network_mode!r}"
            )
        self.network_mode = network_mode
        self.ps = PowerSystem(
            self.L, self.H_es0, self.D_es0, dt=cfg.DT, fn=fn,
            B_matrix=self.B_matrix, V_bus=self.V_bus,
            network_mode=network_mode, governor_enabled=governor_enabled,
        )
        self.rng = np.random.default_rng()

        self.obs_dim = 3 + 2 * self.max_neighbors  # = 7
        self.step_count = 0

        # 通信延迟缓冲 (固定步数路径)
        self._delayed_omega = {}
        self._delayed_omega_dot = {}

        # M7 时变时延状态
        self._delay_trace = []           # list of dict {(i,j): delay_seconds}
        self._link_means = {}            # dict {(i,j): μ_ij}
        self._gaussian_buffers = {}      # dict {(i,j,'omega'|'omega_dot'): deque}
        self._max_delay_steps = 0
        self._delay_rng = None

    def seed(self, s):
        self.rng = np.random.default_rng(s)

    def reset(self, delta_u=None, event_schedule=None):
        # M6b1: event_schedule 与 random_disturbance / delta_u 互斥
        if event_schedule is not None:
            if delta_u is not None:
                raise ValueError(
                    "reset() 不能同时传入 delta_u 和 event_schedule；"
                    "使用 event_schedule 时请令 delta_u=None。"
                )
            # current_delta_u 设为 t=0 DisturbanceEvent 的值，或零向量
            self.current_delta_u = np.zeros(self.N)
            for ev in event_schedule.events:
                if ev.t == 0.0 and isinstance(ev, DisturbanceEvent):
                    self.current_delta_u = ev.delta_u.copy()
                    break
            self.ps.reset(event_schedule=event_schedule)
        elif delta_u is not None:
            self.current_delta_u = delta_u.copy()
            self.ps.reset(delta_u=self.current_delta_u)
        elif self.random_disturbance:
            n_disturbed = self.rng.integers(1, min(3, self.N + 1))
            buses = self.rng.choice(self.N, size=n_disturbed, replace=False)
            self.current_delta_u = np.zeros(self.N)
            for bus in buses:
                mag = self.rng.uniform(cfg.DISTURBANCE_MIN, cfg.DISTURBANCE_MAX)
                self.current_delta_u[bus] = self.rng.choice([-1, 1]) * mag
            self.ps.reset(delta_u=self.current_delta_u)
        else:
            self.current_delta_u = np.zeros(self.N)
            self.ps.reset(delta_u=self.current_delta_u)
        self.step_count = 0
        self.comm.reset(rng=self.rng)

        # 重置通信延迟缓冲
        self._delayed_omega = {}
        self._delayed_omega_dot = {}
        from collections import deque
        if self.comm_delay_steps > 0:
            for i in range(self.N):
                for j in self.comm.get_neighbors(i):
                    self._delayed_omega[(i, j)] = deque(
                        [0.0] * self.comm_delay_steps, maxlen=self.comm_delay_steps)
                    self._delayed_omega_dot[(i, j)] = deque(
                        [0.0] * self.comm_delay_steps, maxlen=self.comm_delay_steps)

        # M7 时变时延初始化
        self._delay_trace = []
        if self.comm_delay_gaussian is not None:
            cfg_d = self.comm_delay_gaussian
            seed = cfg_d.get('rng_seed', 2023)
            rng_d = np.random.default_rng(seed)
            mu_lo, mu_hi = cfg_d['mean_range']
            std = float(cfg_d['std'])
            self._delay_std = std
            self._delay_rng = rng_d

            # per-link μ_ij (对称: (i,j) 与 (j,i) 共享)
            self._link_means = {}
            for i in range(self.N):
                for j in self.comm.get_neighbors(i):
                    if (i, j) not in self._link_means:
                        mu_ij = float(rng_d.uniform(mu_lo, mu_hi))
                        self._link_means[(i, j)] = mu_ij
                        self._link_means[(j, i)] = mu_ij

            # buffer 长度: μ_max + 4σ 覆盖 >99.99% 尾部
            max_d_sec = mu_hi + 4.0 * std
            self._max_delay_steps = max(1, int(np.ceil(max_d_sec / cfg.DT))) + 1
            self._gaussian_buffers = {}
            for i in range(self.N):
                for j in self.comm.get_neighbors(i):
                    self._gaussian_buffers[(i, j, 'omega')] = deque(
                        [0.0] * self._max_delay_steps, maxlen=self._max_delay_steps)
                    self._gaussian_buffers[(i, j, 'omega_dot')] = deque(
                        [0.0] * self._max_delay_steps, maxlen=self._max_delay_steps)

        return self._build_obs(self.ps.get_state())

    def step(self, actions):
        H_es = np.copy(self.H_es0)
        D_es = np.copy(self.D_es0)
        delta_H = np.zeros(self.N)
        delta_D = np.zeros(self.N)

        for i in range(self.N):
            a = np.clip(actions[i], -1.0, 1.0)
            # Zero-centered mapping: a=0 → ΔH=0 (保持基准参数，与论文 Eq.12-13 语义一致)
            delta_H[i] = a[0] * cfg.DH_MAX if a[0] >= 0 else a[0] * (-cfg.DH_MIN)
            delta_D[i] = a[1] * cfg.DD_MAX if a[1] >= 0 else a[1] * (-cfg.DD_MIN)
            H_es[i] = max(self.H_es0[i] + delta_H[i], 0.1)
            D_es[i] = max(self.D_es0[i] + delta_D[i], 0.1)

        self.ps.set_params(H_es, D_es)
        result = self.ps.step()
        self.step_count += 1

        obs = self._build_obs(result)
        rewards, r_f_sum, r_h_sum, r_d_sum = self._compute_rewards(
            result, delta_H, delta_D)
        done = self.step_count >= cfg.STEPS_PER_EPISODE

        # 添加 H/D 到 info
        result['H_es'] = H_es.copy()
        result['D_es'] = D_es.copy()
        result['r_f'] = r_f_sum
        result['r_h'] = r_h_sum
        result['r_d'] = r_d_sum

        return obs, rewards, done, result

    def _build_obs(self, state):
        # M7: 高斯时变时延分支
        if self.comm_delay_gaussian is not None:
            return self._build_obs_gaussian_delay(state)

        obs = {}
        for i in range(self.N):
            o = np.zeros(self.obs_dim, dtype=np.float32)
            o[0] = state['P_es'][i] / 5.0
            o[1] = state['omega'][i] / 3.0
            o[2] = state['omega_dot'][i] / 5.0
            neighbors = self.comm.get_neighbors(i)
            for k, j in enumerate(neighbors):
                if k >= self.max_neighbors:
                    break
                if self.comm.is_link_active(i, j):
                    if self.comm_delay_steps > 0 and (i, j) in self._delayed_omega:
                        o[3 + k] = self._delayed_omega[(i, j)][0] / 3.0
                        o[3 + self.max_neighbors + k] = self._delayed_omega_dot[(i, j)][0] / 5.0
                        self._delayed_omega[(i, j)].append(state['omega'][j])
                        self._delayed_omega_dot[(i, j)].append(state['omega_dot'][j])
                    else:
                        o[3 + k] = state['omega'][j] / 3.0
                        o[3 + self.max_neighbors + k] = state['omega_dot'][j] / 5.0
            obs[i] = o
        return obs

    def _build_obs_gaussian_delay(self, state):
        """M7: 高斯时变时延 obs 构造.

        每步每链路独立采样 d ~ N(μ_ij, σ), clip≥0, round(d/dt)→steps.
        从 buffer 末尾回溯 steps 取历史邻居 ω/ω̇, 然后 append 当前值.
        记录 delay_trace: {(i,j): d_seconds}.
        """
        obs = {}
        current_delays = {}
        for i in range(self.N):
            o = np.zeros(self.obs_dim, dtype=np.float32)
            o[0] = state['P_es'][i] / 5.0
            o[1] = state['omega'][i] / 3.0
            o[2] = state['omega_dot'][i] / 5.0
            neighbors = self.comm.get_neighbors(i)
            for k, j in enumerate(neighbors):
                if k >= self.max_neighbors:
                    break
                if self.comm.is_link_active(i, j):
                    mu_ij = self._link_means[(i, j)]
                    d_sec = float(self._delay_rng.normal(mu_ij, self._delay_std))
                    d_sec = max(0.0, d_sec)
                    current_delays[(i, j)] = d_sec
                    d_steps = int(round(d_sec / cfg.DT))
                    d_steps = min(d_steps, self._max_delay_steps - 1)
                    buf_w = self._gaussian_buffers[(i, j, 'omega')]
                    buf_d = self._gaussian_buffers[(i, j, 'omega_dot')]
                    # 先 append 当前值, 再回溯: d_steps=0 = 当前即时, d_steps=K = K 步前.
                    buf_w.append(state['omega'][j])
                    buf_d.append(state['omega_dot'][j])
                    idx = -1 - d_steps
                    o[3 + k] = buf_w[idx] / 3.0
                    o[3 + self.max_neighbors + k] = buf_d[idx] / 5.0
            obs[i] = o
        self._delay_trace.append(current_delays)
        return obs

    def _compute_rewards(self, state, delta_H, delta_D):
        """计算奖励 (Eq. 14-18).

        r_f: 局部邻居平均频率 (Eq.15-16)
        r_h: -(ΔH_avg)² 物理惯量调整均值 (Eq.17)
        r_d: -(ΔD_avg)² 物理阻尼调整均值 (Eq.18)
        """
        rewards = {}
        r_f_total, r_h_total, r_d_total = 0.0, 0.0, 0.0

        # Eq.17-18: 物理调整量全局均值 (先均值再平方)
        ah_avg = float(np.mean(delta_H))   # ΔH_avg
        ad_avg = float(np.mean(delta_D))   # ΔD_avg

        for i in range(self.N):
            omega_i = state['omega'][i]
            neighbors = self.comm.get_neighbors(i)

            # Eq. 15-16: frequency sync (局部)
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

            # Eq. 17: r_h = -(ΔH_avg)²
            r_h = -(ah_avg) ** 2

            # Eq. 18: r_d = -(ΔD_avg)²
            r_d = -(ad_avg) ** 2

            rewards[i] = cfg.PHI_F * r_f + cfg.PHI_H * r_h + cfg.PHI_D * r_d
            r_f_total += cfg.PHI_F * r_f
            r_h_total += cfg.PHI_H * r_h
            r_d_total += cfg.PHI_D * r_d
        return rewards, r_f_total, r_h_total, r_d_total


# ═══════════════════════════════════════════════════════
#  训练函数
# ═══════════════════════════════════════════════════════

def train_one(n_agents, method, n_episodes, seed=42, fn=50.0):
    """训练一种方法, 返回 (训练日志, manager)."""
    obs_dim = 7
    action_dim = 2
    hidden = cfg.HIDDEN_SIZES

    # ── P1: 完整 seed 协议必须在 manager/网络构造前执行 ──
    from utils.seed_utils import seed_everything
    seed_everything(int(seed))
    # per-episode env.seed(seed + ep) 保留，用于扰动采样可复现
    # warmup action 用本地 RNG（见循环内）
    warmup_rng = np.random.default_rng(seed)

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

    env = ScalableVSGEnv(n_agents, random_disturbance=True, fn=fn)
    total_rewards = []
    freq_rewards = []
    inertia_rewards = []
    droop_rewards = []
    total_steps = 0
    warmup = cfg.WARMUP_STEPS

    for ep in range(n_episodes):
        env.seed(seed + ep)
        obs = env.reset()
        ep_reward = 0.0
        ep_rf, ep_rh, ep_rd = 0.0, 0.0, 0.0

        for step in range(cfg.STEPS_PER_EPISODE):
            if total_steps < warmup:
                # P1: 用本地 RNG (warmup_rng) 而非全局 np.random 保证可复现
                actions = {i: warmup_rng.uniform(-1, 1, size=action_dim)
                           for i in range(n_agents)}
            else:
                actions = manager.select_actions(obs)

            next_obs, rewards, done, info = env.step(actions)
            manager.store_transitions(obs, actions, rewards, next_obs, float(done))
            ep_reward += sum(rewards.values())
            ep_rf += info.get('r_f', 0.0)
            ep_rh += info.get('r_h', 0.0)
            ep_rd += info.get('r_d', 0.0)

            if total_steps >= warmup:
                manager.update()

            obs = next_obs
            total_steps += 1
            if done:
                break

        # 论文 Algorithm 1 line 16: 每 episode 结束后清空 buffer
        if cfg.CLEAR_BUFFER_PER_EPISODE:
            manager.clear_buffers()

        total_rewards.append(ep_reward)
        freq_rewards.append(ep_rf)
        inertia_rewards.append(ep_rh)
        droop_rewards.append(ep_rd)

        if (ep + 1) % 100 == 0:
            avg = np.mean(total_rewards[-100:])
            print(f"    N={n_agents} {method}: Ep {ep+1}/{n_episodes} "
                  f"avg_reward={avg:.1f}")

    log = {
        'rewards': total_rewards,
        'freq_rewards': freq_rewards,
        'inertia_rewards': inertia_rewards,
        'droop_rewards': droop_rewards,
    }
    return log, manager


# ═══════════════════════════════════════════════════════
#  P0: 固定评估集 (scalability / NE39-ODE 路径)
# ═══════════════════════════════════════════════════════

# 生成器版本号：扰动语义或拓扑口径变化时递增
TEST_SET_GENERATOR_VERSION = "v1.0"

# 固定评估集 seed。硬编码保留，写入 metadata 以供跨 run 校验。
NE_TEST_SEED = 2000


def generate_ne_test_scenarios(n_agents, n=None, seed=None):
    """生成 scalability/NE39-ODE 路径的固定评估扰动集.

    Args:
        n_agents: 环境节点数 N.
        n: 场景数。None 时读 cfg.N_TEST_SCENARIOS (P0 硬规则)。
        seed: 固定 seed。None 时用 NE_TEST_SEED。

    Returns:
        scenarios: List[np.ndarray], 每项 shape=(n_agents,) 为 delta_u 向量。
        与 ScalableVSGEnv.reset(delta_u=...) 语义一致，`random_disturbance` 须关闭。
    """
    if n is None:
        n = cfg.N_TEST_SCENARIOS
    if seed is None:
        seed = NE_TEST_SEED
    rng = np.random.default_rng(seed)
    scenarios = []
    for _ in range(n):
        n_disturbed = rng.integers(1, min(3, n_agents + 1))
        buses = rng.choice(n_agents, size=n_disturbed, replace=False)
        delta_u = np.zeros(n_agents)
        for bus in buses:
            mag = rng.uniform(cfg.DISTURBANCE_MIN, cfg.DISTURBANCE_MAX)
            sign = rng.choice([-1, 1])
            delta_u[bus] = sign * mag
        scenarios.append(delta_u)
    return scenarios


def build_test_set_metadata(n_agents, n=None, seed=None):
    """返回固定评估集 metadata (写入 sidecar / run log 用)."""
    return {
        "n_test": int(n if n is not None else cfg.N_TEST_SCENARIOS),
        "seed": int(seed if seed is not None else NE_TEST_SEED),
        "n_agents": int(n_agents),
        "generator": "generate_ne_test_scenarios",
        "generator_version": TEST_SET_GENERATOR_VERSION,
        "config_source": "cfg.N_TEST_SCENARIOS",
    }


def compute_test_reward(n_agents, manager, scenarios=None, n_test=None, seed=None):
    """RL 控制下固定评估集上的全局频率奖励 (P0 标准化).

    Args:
        scenarios: 固定扰动列表。None 时调 generate_ne_test_scenarios(n_agents)。
        n_test/seed: 仅当 scenarios=None 时用于生成 (均 None 时读 cfg)。
    """
    if scenarios is None:
        scenarios = generate_ne_test_scenarios(n_agents, n=n_test, seed=seed)

    env = ScalableVSGEnv(n_agents, random_disturbance=False, comm_fail_prob=0.0)
    rewards_list = []

    for delta_u in scenarios:
        obs = env.reset(delta_u=delta_u)
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


def compute_no_control_reward(n_agents, scenarios=None, n_test=None, seed=None):
    """无控制基线 (ΔH=0, ΔD=0) 在固定评估集上的频率奖励 (P0 标准化)."""
    if scenarios is None:
        scenarios = generate_ne_test_scenarios(n_agents, n=n_test, seed=seed)

    env = ScalableVSGEnv(n_agents, random_disturbance=False, comm_fail_prob=0.0)
    # Zero-centered mapping: action=0 → ΔH=0, ΔD=0 (no parameter change)
    fixed_action = np.array([0.0, 0.0], dtype=np.float32)
    rewards_list = []

    for delta_u in scenarios:
        obs = env.reset(delta_u=delta_u)
        ep_reward = 0.0

        for step in range(cfg.STEPS_PER_EPISODE):
            actions = {i: fixed_action.copy() for i in range(n_agents)}
            obs, rewards, done, info = env.step(actions)

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
            log, _ = train_one(N, method, args.episodes, args.seed)
            elapsed = time.time() - t0
            print(f"    Done in {elapsed:.0f}s, final avg={np.mean(log['rewards'][-100:]):.1f}")
            results[key] = log['rewards']

    # 保存日志
    save_dir = 'results/scalability'
    os.makedirs(save_dir, exist_ok=True)
    log = {k: v for k, v in results.items()}
    with open(os.path.join(save_dir, 'scalability_log.json'), 'w') as f:
        json.dump(log, f)

    # P0 + P1: run metadata sidecar (固定评估集 + 训练 seed 协议)
    meta = {
        "train_seed": int(args.seed),
        "n_agents_list": list(args.n_agents),
        "methods": list(methods),
        "n_episodes": int(args.episodes),
        "test_set": {N: build_test_set_metadata(N) for N in args.n_agents},
    }
    with open(os.path.join(save_dir, 'run_meta.json'), 'w') as f:
        json.dump(meta, f, indent=2)
    print(f"    [P0/P1 metadata] {os.path.join(save_dir, 'run_meta.json')}")

    # 画图
    plot_results(results, args.n_agents, methods, args.episodes, save_dir)


def plot_results(results, n_agents_list, methods, n_episodes, save_dir):
    """生成 Fig 14 和 Fig 15 — 论文风格 (3×1 竖排)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    from plotting.paper_style import apply_ieee_style, paper_legend, rolling_stats, plot_band
    from plotting.paper_style import COLOR_DISTRIBUTED, COLOR_CENTRALIZED

    apply_ieee_style()
    fig_dir = 'results/figures'
    os.makedirs(fig_dir, exist_ok=True)

    n_plots = len(n_agents_list)
    window = max(1, n_episodes // 20)
    labels = {'distributed': 'Proposed DRL', 'centralized': 'Centralized DRL'}
    colors = {'distributed': COLOR_DISTRIBUTED, 'centralized': COLOR_CENTRALIZED}

    # ═══ Fig 14: 训练曲线对比 — 3×1 竖排 ═══
    fig, axes = plt.subplots(n_plots, 1, figsize=(6.5, 3.0 * n_plots))
    if n_plots == 1:
        axes = [axes]
    fig.subplots_adjust(hspace=0.35, left=0.14, right=0.96, top=0.97, bottom=0.07)
    sub_labels = ['(a)', '(b)', '(c)']

    for idx, N in enumerate(n_agents_list):
        ax = axes[idx]
        all_mins, all_maxs = [], []
        for method in methods:
            key = f"N{N}_{method}"
            if key not in results:
                continue
            r = np.array(results[key])
            plot_band(ax, np.arange(len(r)), r,
                      colors[method], labels[method], lw=1.5, window=window)
            from plotting.paper_style import rolling_stats as _rs
            m, s = _rs(r, window=window)
            all_mins.append((m - s).min())
            all_maxs.append((m + s).max())

        # 使用平滑数据设置 y 轴范围, 避免 spike 压缩
        if all_mins and all_maxs:
            y_lo = min(all_mins) * 1.15
            y_hi = max(all_maxs) * 1.15 if max(all_maxs) > 0 else max(all_maxs) * 0.85
            ax.set_ylim(y_lo, y_hi)

        ax.text(0.95, 0.92, f'$N={N}$', transform=ax.transAxes,
                fontsize=12, ha='right', va='top',
                bbox=dict(boxstyle='square,pad=0.3', fc='white', ec='black', lw=0.5))
        ax.set_ylabel('Episode reward', fontsize=10)
        ax.set_xlim(0, n_episodes)
        ax.xaxis.set_major_locator(mticker.MultipleLocator(500))
        paper_legend(ax, loc='lower right', fontsize=8)
        ax.set_xlabel(f'{sub_labels[idx]} Training episodes', fontsize=10, labelpad=3)

    path14 = os.path.join(fig_dir, 'fig14_scalability_training.png')
    plt.savefig(path14, dpi=250, bbox_inches='tight')
    plt.close()
    print(f"\nSaved {path14}")

    # ═══ Fig 15: 累积奖励对比 — 3×1 竖排 ═══
    # 论文配色: without control=棕红, Proposed=绿, Centralized=橙
    from plotting.paper_style import COLOR_NO_CTRL, COLOR_PROPOSED
    cum_colors = {'distributed': COLOR_CENTRALIZED,  # 绿
                  'centralized': COLOR_PROPOSED}  # 橙
    cum_labels = {'distributed': 'Proposed control',
                  'centralized': 'Centralized DRL control'}

    fig, axes = plt.subplots(n_plots, 1, figsize=(6.5, 3.5 * n_plots))
    if n_plots == 1:
        axes = [axes]
    fig.subplots_adjust(hspace=0.35, left=0.14, right=0.96, top=0.97, bottom=0.07)

    n_test_cfg = cfg.N_TEST_SCENARIOS
    for idx, N in enumerate(n_agents_list):
        ax = axes[idx]
        # 真实无控制基线 (P0: 固定评估集, n_test/seed 绑 cfg)
        no_ctrl = compute_no_control_reward(N)
        x_axis = np.arange(len(no_ctrl))
        ax.plot(x_axis, np.cumsum(no_ctrl), color=COLOR_NO_CTRL, lw=2.0,
                label='without control')
        for method in methods:
            key = f"N{N}_{method}"
            if key not in results:
                continue
            test_rewards = results[key][-n_test_cfg:]
            ax.plot(np.arange(len(test_rewards)), np.cumsum(test_rewards),
                    color=cum_colors[method], lw=2.0, label=cum_labels[method])
        ax.text(0.05, 0.08, f'$N={N}$', transform=ax.transAxes,
                fontsize=12, ha='left', va='bottom',
                bbox=dict(boxstyle='square,pad=0.3', fc='white', ec='black', lw=0.5))
        ax.set_ylabel('Cumulative\nreward', fontsize=10)
        ax.set_xlim(0, max(0, n_test_cfg - 1))
        ax.xaxis.set_major_locator(mticker.MultipleLocator(10))
        paper_legend(ax, loc='lower left', fontsize=8, handlelength=2.0)
        ax.set_xlabel(f'{sub_labels[idx]} Test episodes', fontsize=10, labelpad=3)

    path15 = os.path.join(fig_dir, 'fig15_scalability_cumulative.png')
    plt.savefig(path15, dpi=250, bbox_inches='tight')
    plt.close()
    print(f"Saved {path15}")


if __name__ == '__main__':
    main()
