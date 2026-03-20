"""
ANDES 版多智能体 VSG 环境
========================

在 ANDES Kundur 两区域系统上:
  - 保留 4 台 GENROU 同步发电机
  - 额外添加 4 台 GENCLS 作为 VSG 储能 (经典摇摆方程 ≈ VSG)
  - RL agent 实时调节 VSG 的 M(=2H) 和 D
  - 通过 TDS 暂停-修改-恢复 实现 RL 控制循环

运行环境: WSL + Python 3.12 + ANDES 2.0.0

论文对应: Yang et al., IEEE TPWRS 2023
  "A Distributed Dynamic Inertia-Droop Control Strategy
   Based on Multi-Agent Deep Reinforcement Learning
   for Multiple Paralleled VSGs"
"""

from collections import deque
import numpy as np
import andes
import warnings
import copy

warnings.filterwarnings("ignore")


class AndesMultiVSGEnv:
    """基于 ANDES 的多并联 VSG 分布式控制环境.

    系统拓扑: 修改版 Kundur 两区域系统
      - Area 1: Gen1 (bus1), Gen2 (bus2), VSG1 (bus5), VSG2 (bus6)
      - Area 2: Gen3 (bus3), Gen4 (bus4), VSG3 (bus9), VSG4 (bus10)
      - 4 台 GENCLS 模拟 VSG 储能

    控制步长: 0.2s (与论文一致)
    Episode 总长: 10s (50 步)
    """

    # ─── 系统参数 ───
    N_AGENTS = 4
    DT = 0.2                         # 控制步长 (s)
    T_EPISODE = 10.0                 # episode 总时长
    STEPS_PER_EPISODE = 50

    # VSG 基础参数 (GENCLS: M = 2H)
    VSG_M0 = 6.0                     # 基础惯量 M = 2H (s)
    VSG_D0 = 2.0                     # 基础阻尼 D (p.u.)
    VSG_SN = 100.0                   # 额定容量 (MVA)

    # 动作范围 (论文 Section IV-B)
    DM_MIN, DM_MAX = -5.0, 30.0     # ΔM 范围 (M = 2H)
    DD_MIN, DD_MAX = -1.5, 20.0     # ΔD 范围

    # VSG 接入母线 (Kundur 系统中的 non-generator buses)
    VSG_BUSES = [5, 6, 9, 10]

    # 通信拓扑: 环形
    COMM_ADJ = {0: [1, 3], 1: [0, 2], 2: [1, 3], 3: [2, 0]}
    MAX_NEIGHBORS = 2
    OBS_DIM = 3 + 2 * 2             # = 7

    # 奖励权重
    PHI_F = 100.0
    PHI_H = 1.0
    PHI_D = 1.0

    # 扰动范围 (PQ 负荷增量, p.u. on system base 100MVA)
    DIST_MIN = 0.5                   # 最小扰动
    DIST_MAX = 2.0                   # 最大扰动

    # 通信
    COMM_FAIL_PROB = 0.1

    def __init__(self, random_disturbance=True, comm_fail_prob=None,
                 comm_delay_steps=0, forced_link_failures=None):
        self.random_disturbance = random_disturbance
        self.comm_fail_prob = comm_fail_prob or self.COMM_FAIL_PROB
        self.comm_delay_steps = comm_delay_steps
        self.forced_link_failures = forced_link_failures
        self.rng = np.random.default_rng(42)

        self.case_path = andes.get_case("kundur/kundur_full.xlsx")

        # VSG 参数
        self.M0 = np.full(self.N_AGENTS, self.VSG_M0)
        self.D0 = np.full(self.N_AGENTS, self.VSG_D0)

        # 运行时状态
        self.ss = None
        self.step_count = 0
        self.vsg_idx = []             # GENCLS idx list
        self.comm_eta = {}            # 通信链路状态

        # 通信延迟缓冲
        self._delayed_omega = {}
        self._delayed_omega_dot = {}

        # omega 归一化系数 (ANDES omega 以 p.u. 表示, 1.0=标称)
        self._omega_scale = 50.0 * 2 * np.pi  # 转换到 rad/s 偏差

    def seed(self, s):
        self.rng = np.random.default_rng(s)

    def _build_system(self):
        """加载 Kundur 系统并添加 4 台 VSG (GENCLS)."""
        ss = andes.load(self.case_path, default_config=True, setup=False)

        # 获取 Bus idx → Vn 映射
        bus_idx_list = list(ss.Bus.idx.v)
        bus_vn_list = list(ss.Bus.Vn.v)
        bus_vn_map = dict(zip(bus_idx_list, bus_vn_list))

        # 添加 4 台 GENCLS 作为 VSG 储能
        # ANDES 需要先添加 StaticGen, 再添加 GENCLS (通过 gen 参数关联)
        self.vsg_idx = []
        for i, bus in enumerate(self.VSG_BUSES):
            vsg_id = f"VSG_{i+1}"
            gen_id = f"SG_VSG_{i+1}"

            # 添加 StaticGen (静态发电机入口)
            ss.add("PV", {
                "idx": gen_id,
                "name": f"VSG{i+1}",
                "bus": bus,
                "Vn": bus_vn_map[bus],
                "Sn": self.VSG_SN,
                "p0": 0.5,
                "q0": 0.0,
                "pmax": 5.0,
                "pmin": 0.0,
                "qmax": 5.0,
                "qmin": -5.0,
                "v0": 1.0,
            })

            # 添加 GENCLS (动态模型, 关联到 PV)
            ss.add("GENCLS", {
                "idx": vsg_id,
                "bus": bus,
                "gen": gen_id,
                "Vn": bus_vn_map[bus],
                "Sn": self.VSG_SN,
                "M": self.M0[i],
                "D": self.D0[i],
                "ra": 0.001,
                "xd1": 0.15,
            })
            self.vsg_idx.append(vsg_id)

        ss.setup()
        return ss

    def _reset_comm(self):
        """重置通信链路状态."""
        self.comm_eta = {}
        for i, neighbors in self.COMM_ADJ.items():
            for j in neighbors:
                if (j, i) in self.comm_eta:
                    self.comm_eta[(i, j)] = self.comm_eta[(j, i)]
                else:
                    self.comm_eta[(i, j)] = 0 if self.rng.random() < self.comm_fail_prob else 1

    def _get_vsg_omega(self):
        """获取 4 台 VSG 的转速 (p.u.)."""
        omega = np.zeros(self.N_AGENTS)
        for i, idx in enumerate(self.vsg_idx):
            # 找到该 GENCLS 设备在数组中的位置
            pos = list(self.ss.GENCLS.idx.v).index(idx)
            omega[i] = self.ss.GENCLS.omega.v[pos]
        return omega

    def _get_vsg_power(self):
        """获取 4 台 VSG 的有功出力 (p.u.)."""
        P = np.zeros(self.N_AGENTS)
        for i, idx in enumerate(self.vsg_idx):
            pos = list(self.ss.GENCLS.idx.v).index(idx)
            # GENCLS 的电磁功率
            P[i] = self.ss.GENCLS.Pe.v[pos]
        return P

    def _compute_omega_dot(self, omega, P):
        """从摇摆方程估计 dω/dt.

        M * dω/dt = Pm - Pe - D*(ω - 1)
        近似: dω/dt ≈ (Pm - Pe - D*(ω-1)) / M
        """
        omega_dot = np.zeros(self.N_AGENTS)
        for i in range(self.N_AGENTS):
            pos = list(self.ss.GENCLS.idx.v).index(self.vsg_idx[i])
            M = self.ss.GENCLS.M.v[pos]
            D = self.ss.GENCLS.D.v[pos]
            Pm = 0.5  # 机械功率 (近似恒定)
            Pe = P[i]
            omega_dot[i] = (Pm - Pe - D * (omega[i] - 1.0)) / max(M, 0.1)
        return omega_dot

    def reset(self, delta_u=None, scenario_idx=None):
        """
        重置环境.

        Parameters
        ----------
        delta_u : dict or None
            指定扰动, 如 {pq_idx: delta_p}. None 则随机生成.
        """
        # 重新构建系统 (ANDES 不支持完全 reset, 需重新加载)
        self.ss = self._build_system()

        # 潮流计算
        self.ss.PFlow.run()
        if not self.ss.PFlow.converged:
            raise RuntimeError("Power flow did not converge!")

        # 运行到 t=0.5s 建立稳态
        self.ss.TDS.config.tf = 0.5
        self.ss.TDS.run()

        # 施加扰动
        if delta_u is not None:
            for pq_idx, dp in delta_u.items():
                self.ss.PQ.alter("p0", pq_idx, self.ss.PQ.p0.v[
                    list(self.ss.PQ.idx.v).index(pq_idx)] + dp)
        elif self.random_disturbance:
            # 随机选择一个 PQ 负荷施加扰动
            n_pq = self.ss.PQ.n
            if n_pq > 0:
                pq_pos = self.rng.integers(0, n_pq)
                pq_idx = self.ss.PQ.idx.v[pq_pos]
                magnitude = self.rng.uniform(self.DIST_MIN, self.DIST_MAX)
                sign = self.rng.choice([-1, 1])
                current_p0 = self.ss.PQ.p0.v[pq_pos]
                self.ss.PQ.alter("p0", pq_idx, current_p0 + sign * magnitude)

        self.ss.TDS.custom_event = True

        # 重置通信
        self._reset_comm()

        # 强制指定链路故障
        if self.forced_link_failures:
            for i, j in self.forced_link_failures:
                self.comm_eta[(i, j)] = 0

        # 重置通信延迟缓冲
        self._delayed_omega = {}
        self._delayed_omega_dot = {}
        if self.comm_delay_steps > 0:
            for i in range(self.N_AGENTS):
                for j in self.COMM_ADJ[i]:
                    self._delayed_omega[(i, j)] = deque(
                        [0.0] * self.comm_delay_steps,
                        maxlen=self.comm_delay_steps)
                    self._delayed_omega_dot[(i, j)] = deque(
                        [0.0] * self.comm_delay_steps,
                        maxlen=self.comm_delay_steps)

        self.step_count = 0
        self._prev_omega = self._get_vsg_omega()

        return self._build_obs()

    def step(self, actions):
        """
        执行一步控制.

        Parameters
        ----------
        actions : dict[int, np.ndarray]
            每个 agent 的动作, shape (2,), 范围 [-1, 1]
            actions[i] = [ΔM_norm, ΔD_norm]

        Returns
        -------
        obs, rewards, done, info
        """
        # 1. 解码动作并修改 VSG 参数
        M_new = np.zeros(self.N_AGENTS)
        D_new = np.zeros(self.N_AGENTS)
        delta_M = np.zeros(self.N_AGENTS)
        delta_D = np.zeros(self.N_AGENTS)

        for i in range(self.N_AGENTS):
            a = np.clip(actions[i], -1.0, 1.0)
            delta_M[i] = (a[0] + 1) / 2 * (self.DM_MAX - self.DM_MIN) + self.DM_MIN
            delta_D[i] = (a[1] + 1) / 2 * (self.DD_MAX - self.DD_MIN) + self.DD_MIN
            M_new[i] = max(self.M0[i] + delta_M[i], 0.2)
            D_new[i] = max(self.D0[i] + delta_D[i], 0.1)

            # 修改 ANDES 中的参数
            self.ss.GENCLS.alter("M", self.vsg_idx[i], M_new[i])
            self.ss.GENCLS.alter("D", self.vsg_idx[i], D_new[i])

        # 2. 推进仿真 DT 秒
        current_t = self.ss.dae.t
        self.ss.TDS.config.tf = current_t + self.DT
        self.ss.TDS.run()

        self.step_count += 1

        # 3. 读取状态
        omega = self._get_vsg_omega()
        P_es = self._get_vsg_power()
        omega_dot = self._compute_omega_dot(omega, P_es)

        # 4. 构建观测
        obs = self._build_obs(omega, omega_dot, P_es)

        # 5. 计算奖励
        rewards = self._compute_rewards(omega, omega_dot, delta_M, delta_D)

        # 6. 终止条件
        done = self.step_count >= self.STEPS_PER_EPISODE

        # 频率 (Hz)
        freq_hz = omega * 50.0

        info = {
            "time": self.ss.dae.t,
            "freq_hz": freq_hz.copy(),
            "omega": omega.copy(),
            "omega_dot": omega_dot.copy(),
            "P_es": P_es.copy(),
            "M_es": M_new.copy(),
            "D_es": D_new.copy(),
            "delta_M": delta_M.copy(),
            "delta_D": delta_D.copy(),
        }

        self._prev_omega = omega.copy()
        return obs, rewards, done, info

    def _build_obs(self, omega=None, omega_dot=None, P_es=None):
        """构建每个 agent 的观测 (Eq. 11)."""
        if omega is None:
            omega = self._get_vsg_omega()
        if P_es is None:
            P_es = self._get_vsg_power()
        if omega_dot is None:
            omega_dot = self._compute_omega_dot(omega, P_es)

        # 转换为偏差量 (标称值 = 1.0 p.u.)
        d_omega = (omega - 1.0) * self._omega_scale   # rad/s 偏差

        obs = {}
        for i in range(self.N_AGENTS):
            o = np.zeros(self.OBS_DIM, dtype=np.float32)

            # 本地信息 (归一化)
            o[0] = P_es[i] / 2.0                      # P_es 范围约 [-2, 2] p.u.
            o[1] = d_omega[i] / 3.0                    # omega 偏差
            o[2] = omega_dot[i] * self._omega_scale / 5.0  # dω/dt

            # 邻居信息 (支持通信延迟)
            for k, j in enumerate(self.COMM_ADJ[i]):
                if k >= self.MAX_NEIGHBORS:
                    break
                if self.comm_eta.get((i, j), 0) == 1:
                    d_omega_j = (omega[j] - 1.0) * self._omega_scale
                    od_j = omega_dot[j] * self._omega_scale

                    if self.comm_delay_steps > 0 and (i, j) in self._delayed_omega:
                        # 读取延迟值, 并将当前真实值压入缓冲
                        o[3 + k] = self._delayed_omega[(i, j)][0] / 3.0
                        o[3 + self.MAX_NEIGHBORS + k] = self._delayed_omega_dot[(i, j)][0] / 5.0
                        self._delayed_omega[(i, j)].append(d_omega_j)
                        self._delayed_omega_dot[(i, j)].append(od_j)
                    else:
                        o[3 + k] = d_omega_j / 3.0
                        o[3 + self.MAX_NEIGHBORS + k] = od_j / 5.0

            obs[i] = o
        return obs

    def _compute_rewards(self, omega, omega_dot, delta_M, delta_D):
        """计算每个 agent 的奖励 (Eq. 14-18)."""
        d_omega = (omega - 1.0) * self._omega_scale  # rad/s

        rewards = {}
        for i in range(self.N_AGENTS):
            # Eq. 16: 加权平均频率
            sum_w = d_omega[i]
            n_active = 1
            for j in self.COMM_ADJ[i]:
                if self.comm_eta.get((i, j), 0) == 1:
                    sum_w += d_omega[j]
                    n_active += 1
            omega_bar = sum_w / n_active

            # Eq. 15: 频率同步惩罚
            r_f = -(d_omega[i] - omega_bar) ** 2
            for j in self.COMM_ADJ[i]:
                if self.comm_eta.get((i, j), 0) == 1:
                    r_f -= (d_omega[j] - omega_bar) ** 2

            # Eq. 17-18: 参数调整惩罚 (训练期间 avg ≈ 0)
            r_h = 0.0
            r_d = 0.0

            rewards[i] = self.PHI_F * r_f + self.PHI_H * r_h + self.PHI_D * r_d

        return rewards

    def get_genrou_omega(self):
        """获取 4 台同步发电机的转速 (用于对比分析)."""
        omega = np.zeros(self.ss.GENROU.n)
        for i in range(self.ss.GENROU.n):
            omega[i] = self.ss.GENROU.omega.v[i]
        return omega

    def get_all_omega_timeseries(self):
        """获取所有发电机 omega 的时间序列 (TDS 结束后调用)."""
        ts = self.ss.dae.ts
        t = np.array(ts.t)
        x = np.array(ts.x)

        # GENROU omega
        genrou_omega = {}
        for i in range(self.ss.GENROU.n):
            addr = self.ss.GENROU.omega.a[i]
            genrou_omega[f"Gen_{self.ss.GENROU.idx.v[i]}"] = x[:, addr]

        # GENCLS (VSG) omega
        vsg_omega = {}
        for i, idx in enumerate(self.vsg_idx):
            pos = list(self.ss.GENCLS.idx.v).index(idx)
            addr = self.ss.GENCLS.omega.a[pos]
            vsg_omega[f"VSG_{i+1}"] = x[:, addr]

        return t, genrou_omega, vsg_omega
