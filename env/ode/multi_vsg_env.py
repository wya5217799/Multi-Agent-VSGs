"""
多智能体 VSG 环境

将 PowerSystem 封装为多智能体 RL 环境:
- 每个 agent 观测本地 + 邻居频率信息
- 动作: 惯量/阻尼修正量 ΔH, ΔD
- 奖励: 频率同步惩罚 (Eq. 14-18)
"""

from collections import deque
import numpy as np
from env.ode.power_system import PowerSystem
from env.network_topology import build_laplacian, CommunicationGraph
import config as cfg


class MultiVSGEnv:
    """多并联 VSG 分布式控制环境."""

    def __init__(self, random_disturbance=True, comm_fail_prob=None,
                 comm_delay_steps=0, forced_link_failures=None):
        """
        Parameters
        ----------
        random_disturbance : bool
            是否随机生成扰动 (训练用 True, 测试用 False)
        comm_fail_prob : float or None
            通信链路故障概率, None 则使用 config 默认值
        comm_delay_steps : int
            通信延迟步数 (0.2s/step, 如 1 表示 0.2s 延迟)
        forced_link_failures : list of tuple or None
            强制指定故障链路, 如 [(0,1),(1,0)] 表示 ES1↔ES2 断开
        """
        self.N = cfg.N_AGENTS
        self.random_disturbance = random_disturbance

        # 构建电气网络
        self.L = build_laplacian(cfg.B_MATRIX, cfg.V_BUS)

        # 构建通信图
        fail_prob = comm_fail_prob if comm_fail_prob is not None else cfg.COMM_FAIL_PROB
        self.comm = CommunicationGraph(cfg.COMM_ADJACENCY, fail_prob=fail_prob)
        self.forced_link_failures = forced_link_failures

        # 电力系统
        self.ps = PowerSystem(
            self.L, cfg.H_ES0, cfg.D_ES0,
            dt=cfg.DT, fn=cfg.OMEGA_N / (2 * np.pi),
            B_matrix=cfg.B_MATRIX, V_bus=cfg.V_BUS,
            network_mode=getattr(cfg, 'ODE_NETWORK_MODE', 'linear'),
        )

        # 随机数生成器
        self.rng = np.random.default_rng()

        # 通信延迟
        self.comm_delay_steps = comm_delay_steps
        self._delayed_omega = {}      # 缓存: {(i,j): deque of omega values}
        self._delayed_omega_dot = {}

        self.step_count = 0
        self.current_delta_u = np.zeros(self.N)

    def seed(self, s):
        self.rng = np.random.default_rng(s)

    def reset(self, delta_u=None, event_schedule=None):
        """重置环境.

        Parameters
        ----------
        delta_u : np.ndarray or None
            静态扰动 (测试兼容).
        event_schedule : EventSchedule or None
            时变事件. 若给出则优先于 delta_u, 并禁用 random_disturbance.
        """
        if event_schedule is not None:
            self.current_delta_u = np.zeros(self.N)
            self.ps.reset(event_schedule=event_schedule)
        else:
            if delta_u is not None:
                self.current_delta_u = np.asarray(delta_u, dtype=np.float64).copy()
            elif self.random_disturbance:
                n_disturbed = self.rng.integers(1, 3)
                buses = self.rng.choice(self.N, size=n_disturbed, replace=False)
                self.current_delta_u = np.zeros(self.N)
                for bus in buses:
                    magnitude = self.rng.uniform(cfg.DISTURBANCE_MIN, cfg.DISTURBANCE_MAX)
                    sign = self.rng.choice([-1, 1])
                    self.current_delta_u[bus] = sign * magnitude
            else:
                self.current_delta_u = np.zeros(self.N)
            self.ps.reset(delta_u=self.current_delta_u)

        self.step_count = 0
        self.comm.reset(rng=self.rng)
        if self.forced_link_failures:
            for i, j in self.forced_link_failures:
                self.comm.eta[(i, j)] = 0
        self._delayed_omega = {}
        self._delayed_omega_dot = {}
        if self.comm_delay_steps > 0:
            for i in range(self.N):
                for j in self.comm.get_neighbors(i):
                    self._delayed_omega[(i, j)] = deque([0.0] * self.comm_delay_steps,
                                                        maxlen=self.comm_delay_steps)
                    self._delayed_omega_dot[(i, j)] = deque([0.0] * self.comm_delay_steps,
                                                            maxlen=self.comm_delay_steps)
        return self._build_observations(self.ps.get_state())

    def step(self, actions):
        """
        执行一步.

        Parameters
        ----------
        actions : dict[int, np.ndarray]
            每个 agent 的动作, shape (2,), 范围 [-1, 1]
            actions[i] = [ΔH_norm, ΔD_norm]

        Returns
        -------
        obs : dict[int, np.ndarray]
        rewards : dict[int, float]
        done : bool
        info : dict
        """
        # 1. 解码动作: [-1,1] → [min, max]
        H_es = np.copy(cfg.H_ES0)
        D_es = np.copy(cfg.D_ES0)
        delta_H = np.zeros(self.N)
        delta_D = np.zeros(self.N)

        for i in range(self.N):
            a = np.clip(actions[i], -1.0, 1.0)
            # Zero-centered mapping: a=0 → ΔH=0 (保持基准参数，与论文 Eq.12-13 语义一致)
            delta_H[i] = a[0] * cfg.DH_MAX if a[0] >= 0 else a[0] * (-cfg.DH_MIN)
            delta_D[i] = a[1] * cfg.DD_MAX if a[1] >= 0 else a[1] * (-cfg.DD_MIN)
            H_es[i] = cfg.H_ES0[i] + delta_H[i]
            D_es[i] = cfg.D_ES0[i] + delta_D[i]

        # 确保 H > 0, D > 0 (物理约束)
        H_es = np.maximum(H_es, 8.0)
        D_es = np.maximum(D_es, 0.1)

        # 2. 设置参数并积分一步
        self.ps.set_params(H_es, D_es)
        result = self.ps.step()

        self.step_count += 1

        # 3. 构建观测
        obs = self._build_observations(result)

        # 4. 计算奖励 (Eq. 17-18: 物理 delta_H/delta_D，与论文公式一致)
        rewards, r_f_sum, r_h_sum, r_d_sum = self._compute_rewards(result, delta_H, delta_D)

        # 5. 终止条件
        done = self.step_count >= cfg.STEPS_PER_EPISODE

        # Max frequency deviation from nominal 50 Hz (per-step, not episode-peak)
        max_freq_deviation_hz = float(np.max(np.abs(result['freq_hz'] - cfg.OMEGA_N / (2 * np.pi))))

        info = {
            'time': result['time'],
            'freq_hz': result['freq_hz'].copy(),
            'omega': result['omega'].copy(),
            'P_es': result['P_es'].copy(),
            'H_es': H_es.copy(),
            'D_es': D_es.copy(),
            'delta_H': delta_H.copy(),
            'delta_D': delta_D.copy(),
            'r_f': r_f_sum,
            'r_h': r_h_sum,
            'r_d': r_d_sum,
            'max_freq_deviation_hz': max_freq_deviation_hz,
        }

        return obs, rewards, done, info

    def _build_observations(self, state):
        """
        构建每个 agent 的观测 (Eq. 11).

        o_i = [ΔP_esi, Δωi, Δω̇i,
               Δω_c_j1, Δω_c_j2,
               Δω̇_c_j1, Δω̇_c_j2]

        维度 = 3 + 2 * MAX_NEIGHBORS = 7
        """
        obs = {}
        for i in range(self.N):
            o = np.zeros(cfg.OBS_DIM, dtype=np.float32)

            # 本地信息 (归一化到 ~[-1, 1])
            o[0] = state['P_es'][i] / 5.0         # P_es 范围 ~[-5, 5] with B_tie=4
            o[1] = state['omega'][i] / 3.0        # omega 范围 ~[-3, 3]
            o[2] = state['omega_dot'][i] / 25.0   # omega_dot 范围 ~[-25, 25] with H=24

            # 邻居信息 (通信获取, 支持延迟)
            neighbors = self.comm.get_neighbors(i)
            for k, j in enumerate(neighbors):
                if k >= cfg.MAX_NEIGHBORS:
                    break
                if self.comm.is_link_active(i, j):
                    if self.comm_delay_steps > 0 and (i, j) in self._delayed_omega:
                        # 读取延迟值, 并将当前真实值压入缓冲
                        o[3 + k] = self._delayed_omega[(i, j)][0] / 3.0
                        o[3 + cfg.MAX_NEIGHBORS + k] = self._delayed_omega_dot[(i, j)][0] / 25.0
                        self._delayed_omega[(i, j)].append(state['omega'][j])
                        self._delayed_omega_dot[(i, j)].append(state['omega_dot'][j])
                    else:
                        o[3 + k] = state['omega'][j] / 3.0
                        o[3 + cfg.MAX_NEIGHBORS + k] = state['omega_dot'][j] / 25.0
                # 链路故障 → 保持为 0

            obs[i] = o
        return obs

    def _compute_rewards(self, state, delta_H, delta_D):
        """计算每个 agent 的奖励 (Eq. 14-18).

        ODE 的 omega 是 rad/s 偏差, 转换为 pu 以对齐论文 reward 量级:
            pu 偏差 = rad/s 偏差 / (2π × 50)

        Args:
            state: ODE 积分结果
            delta_H: shape (N,), 物理惯量增量 ΔH (s)
            delta_D: shape (N,), 物理阻尼增量 ΔD (p.u.)
        """
        # rad/s → Hz 转换因子 (论文 Simulink 用 Hz, 反推自 Fig.4 量级)
        _TO_HZ = 1.0 / (2 * np.pi)

        # Eq.17-18: 物理调整量全局均值 (先均值再平方)
        ah_avg = float(np.mean(delta_H))   # ΔH_avg
        ad_avg = float(np.mean(delta_D))   # ΔD_avg

        rewards = {}
        r_f_total, r_h_total, r_d_total = 0.0, 0.0, 0.0
        for i in range(self.N):
            # === Eq. (16): 加权平均频率 (Hz 偏差) ===
            omega_i_hz = state['omega'][i] * _TO_HZ
            neighbors = self.comm.get_neighbors(i)

            sum_omega = omega_i_hz
            n_active = 1
            for j in neighbors:
                if self.comm.is_link_active(i, j):
                    sum_omega += state['omega'][j] * _TO_HZ
                    n_active += 1
            omega_bar = sum_omega / n_active

            # === Eq. (15): 频率同步惩罚 (Hz 单位) ===
            r_f = -(omega_i_hz - omega_bar) ** 2
            for j in neighbors:
                if self.comm.is_link_active(i, j):
                    r_f -= (state['omega'][j] * _TO_HZ - omega_bar) ** 2

            # === Eq. (17): r_h = -(ΔH_avg_norm)^2  (normalized to [-1,1] range) ===
            # PHI_H=1 assumes normalized values; divide by max physical range
            _dh_scale = max(abs(cfg.DH_MAX), abs(cfg.DH_MIN))  # = 72.0
            r_h = -(ah_avg / _dh_scale) ** 2

            # === Eq. (18): r_d = -(ΔD_avg_norm)^2  (normalized to [-1,1] range) ===
            _dd_scale = max(abs(cfg.DD_MAX), abs(cfg.DD_MIN))  # = 54.0
            r_d = -(ad_avg / _dd_scale) ** 2

            # === Eq. (14): 总奖励 ===
            rewards[i] = cfg.PHI_F * r_f + cfg.PHI_H * r_h + cfg.PHI_D * r_d
            r_f_total += cfg.PHI_F * r_f
            r_h_total += cfg.PHI_H * r_h
            r_d_total += cfg.PHI_D * r_d

        return rewards, r_f_total, r_h_total, r_d_total
