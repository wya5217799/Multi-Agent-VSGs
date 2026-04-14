"""
ANDES 多智能体 VSG 环境基类
===========================

提取 Kundur / New England / REGCA1 三个环境的共享逻辑:
  - step(): 动作解码 → 修改 GENCLS 参数 → TDS 推进 → 读取状态 → 计算观测/奖励
  - reset(): 系统构建 → 潮流 → TDS(0.5s) → 施加扰动 → 重置通信
  - 观测构建 (_build_obs), 奖励计算 (_compute_rewards)
  - GENCLS 状态读取 (_get_vsg_omega, _get_vsg_power, _compute_omega_dot)
  - 通信链路管理 (_reset_comm)
  - 时间序列导出 (get_genrou_omega, get_all_omega_timeseries)

子类只需实现:
  - _build_system(): 构建 ANDES 系统 (加载 case, 添加设备)
  - _apply_disturbance(): 在 t=0.5s 后施加扰动

论文: Yang et al., IEEE TPWRS 2023
"""

from abc import ABC, abstractmethod
from collections import deque
import numpy as np

from scenarios.contract import KUNDUR as _DEFAULT_CONTRACT


class AndesBaseEnv(ABC):
    """ANDES 多智能体 VSG 控制环境基类."""

    # Action encoding: a=0 → delta=0 (zero-centered). Used by _get_zero_action().
    # Fixed 2026-04-14: old affine formula gave a=0 → ΔM=+10 (non-zero default).
    # See docs/paper/yang2023-fact-base.md §10 for rationale (Eq.12-13 increment semantics).
    ACTION_ENCODING: str = "zero_centered"

    # ─── 共享默认常量 (子类可覆盖) ───
    # 基类默认使用 Kundur 契约值; NE 子类覆盖 FN/N_AGENTS
    FN = _DEFAULT_CONTRACT.fn        # 标称频率 (Hz), NE 子类覆盖为 60.0
    DT = _DEFAULT_CONTRACT.dt        # 控制步长 (s)
    T_EPISODE = 10.0                 # episode 总时长
    STEPS_PER_EPISODE = 50

    # VSG 基础参数 (GENCLS: M = 2H)
    # 校准值: M0=20 (H0=10), D0=4 — 与 v1 收敛训练一致
    # BackendProfile: ANDES-specific calibration. VSG_M0=20.0 (H0=10s) differs intentionally
    # from Simulink side (VSG_M0=12.0, H0=6s). Both are backend-specific calibrations, not errors.
    # Also note: root config.py still contains old H_ES0=3/D_ES0=2 (v0 system, to be retired).
    VSG_M0 = 20.0                    # 基础惯量 M = 2H (s)
    VSG_D0 = 4.0                     # 基础阻尼 D (p.u.)
    VSG_SN = 200.0                   # 额定容量 (MVA)

    # 动作范围 — see docs/decisions/2026-04-14-action-bounds-audit.md
    # DM: BackendProfile — ANDES M0=20 vs Simulink M0=12; ratio 5/3 explains all differences. OK.
    DM_MIN = -10.0                   # = 2 * DH_MIN = 2 * (-5)
    DM_MAX = 30.0                    # = 2 * DH_MAX = 2 * 15
    # DD: PENDING AUDIT — v1 legacy artefact. D0-proportional estimate: [-2, 6].
    # Do NOT change until ANDES training completes (risk of breaking trained policies).
    DD_MIN = -10.0                   # v1 config; proportional target: -2.0
    DD_MAX = 30.0                    # v1 config; proportional target:  6.0

    # 传输线路参数 (校准值)
    NEW_LINE_R = 0.001
    NEW_LINE_X = 0.10
    NEW_LINE_B = 0.0175

    # 观测空间 — from contract
    MAX_NEIGHBORS = _DEFAULT_CONTRACT.max_neighbors
    OBS_DIM = 3 + 2 * MAX_NEIGHBORS  # = 7

    # 奖励权重 (论文 Eq. 14)
    PHI_F = 100.0
    PHI_H = 1.0
    PHI_D = 1.0
    # BackendProfile (ANDES-family augmentation): PHI_ABS adds an absolute frequency
    # deviation penalty term to the reward. This is NOT in the paper formula (Yang et al.
    # TPWRS 2023 Eq.15-18) and does NOT exist in the Simulink backend.
    # Added to address Kundur tight-coupling instability in ANDES simulations.
    # Do NOT port to Simulink without validating on that backend first.
    PHI_ABS = 50.0  # 绝对频率偏差惩罚权重 (补充项, 解决 Kundur 紧耦合问题)

    # 参数平滑过渡 (避免 ANDES TDS 因参数突变发散)
    N_SUBSTEPS = 5                   # 每个控制步分成 5 小段渐变

    # 通信
    COMM_FAIL_PROB = 0.1

    # ─── 子类必须定义 ───
    N_AGENTS: int                    # agent 数量
    COMM_ADJ: dict                   # 通信邻接表

    def __init__(self, random_disturbance=True, comm_fail_prob=None,
                 comm_delay_steps=0, forced_link_failures=None, **kwargs):
        self.random_disturbance = random_disturbance
        self.comm_fail_prob = comm_fail_prob if comm_fail_prob is not None else self.COMM_FAIL_PROB
        self.comm_delay_steps = comm_delay_steps
        self.forced_link_failures = forced_link_failures
        self.rng = np.random.default_rng(42)

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
        self._omega_scale = self.FN * 2 * np.pi  # 转换到 rad/s 偏差

    def close(self):
        """Clean up ANDES system resources."""
        self.ss = None

    def seed(self, s):
        self.rng = np.random.default_rng(s)

    # ─── 抽象方法 (子类必须实现) ───

    @abstractmethod
    def _build_system(self):
        """构建 ANDES 系统并返回 ss 对象.

        子类需:
          1. 加载 case 文件
          2. 添加设备 (Bus, Line, PV, GENCLS 等)
          3. 调用 ss.setup()
          4. 设置 self.vsg_idx
          5. 返回 ss
        """

    @abstractmethod
    def _apply_disturbance(self, delta_u=None, **kwargs):
        """在 t=0.5s 稳态建立后施加扰动.

        Parameters
        ----------
        delta_u : dict or None
            指定扰动. None 则由子类按场景随机生成.

        子类需在施加 PQ 负荷变化后设置 self.ss.TDS.custom_event = True.
        """

    # ─── reset (模板方法) ───

    def reset(self, delta_u=None, scenario_idx=None, **kwargs):
        """重置环境 (模板方法).

        子类可通过 _pre_build(**kwargs) 做预处理 (如设置 gen_trip).
        """
        # 预处理 (子类可覆盖)
        self._pre_build(**kwargs)

        # 重新构建系统 (ANDES 不支持完全 reset, 需重新加载)
        self.ss = self._build_system()

        # PQ 负荷模式: 常功率 (p2p=1.0), 否则 ANDES 默认用常阻抗模式
        # 常阻抗模式下修改 p0/Ppf 无效 (实际用的是 Req/Xeq)
        if hasattr(self.ss, 'PQ') and self.ss.PQ.n > 0:
            self.ss.PQ.config.p2p = 1.0
            self.ss.PQ.config.p2z = 0.0
            self.ss.PQ.config.q2q = 1.0
            self.ss.PQ.config.q2z = 0.0

        # 潮流计算
        self.ss.PFlow.run()
        if not self.ss.PFlow.converged:
            raise RuntimeError("Power flow did not converge!")

        # 运行到 t=0.5s 建立稳态
        self.ss.TDS.config.tf = 0.5
        self.ss.TDS.run()

        # 清除 busted 标志 — ANDES IEEE 39-bus 初始 TDS 可能误报 busted=True
        # (仿真到达 tf 但 busted 仍被设置, 导致后续 segmented TDS 立即终止)
        self.ss.TDS.busted = False

        # 施加扰动 (子类实现)
        self._apply_disturbance(delta_u=delta_u, **kwargs)

        # 重置通信
        self._reset_comm()
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

        # 记录当前 M/D 值, 用于 substep 插值的起点
        self._prev_M = self.M0.copy()
        self._prev_D = self.D0.copy()

        return self._build_obs()

    def _pre_build(self, **kwargs):
        """子类可覆盖: 在 _build_system() 前的预处理 (如存储 gen_trip)."""
        pass

    # ─── step ───

    def step(self, actions):
        """执行一步控制.

        Parameters
        ----------
        actions : dict[int, np.ndarray]
            每个 agent 的动作, shape (2,), 范围 [-1, 1]
            actions[i] = [ΔM_norm, ΔD_norm]

        Returns
        -------
        obs, rewards, done, info
        """
        # 1. 解码动作 → 目标 M/D
        M_new = np.zeros(self.N_AGENTS)
        D_new = np.zeros(self.N_AGENTS)
        delta_M = np.zeros(self.N_AGENTS)
        delta_D = np.zeros(self.N_AGENTS)

        for i in range(self.N_AGENTS):
            a = np.clip(actions[i], -1.0, 1.0)
            # Zero-centered mapping: a=0 → ΔM=0 (保持基准参数，与论文 Eq.12-13 语义一致)
            # a>0 → [0, DM_MAX]; a<0 → [DM_MIN, 0]
            delta_M[i] = a[0] * self.DM_MAX if a[0] >= 0 else a[0] * (-self.DM_MIN)
            delta_D[i] = a[1] * self.DD_MAX if a[1] >= 0 else a[1] * (-self.DD_MIN)
            M_new[i] = max(self.M0[i] + delta_M[i], 0.2)
            D_new[i] = max(self.D0[i] + delta_D[i], 0.1)

        # 2. 分 N_SUBSTEPS 小段渐变推进仿真, 避免参数突变导致 TDS 发散
        current_t = self.ss.dae.t
        target_t = current_t + self.DT
        dt_sub = self.DT / self.N_SUBSTEPS
        tds_failed = False

        for k in range(self.N_SUBSTEPS):
            alpha = (k + 1) / self.N_SUBSTEPS
            for i in range(self.N_AGENTS):
                M_interp = self._prev_M[i] + alpha * (M_new[i] - self._prev_M[i])
                D_interp = self._prev_D[i] + alpha * (D_new[i] - self._prev_D[i])
                self.ss.GENCLS.set("M", self.vsg_idx[i], M_interp, attr='v')
                self.ss.GENCLS.set("D", self.vsg_idx[i], D_interp, attr='v')

            sub_target = current_t + (k + 1) * dt_sub
            self.ss.TDS.config.tf = sub_target
            self.ss.TDS.busted = False
            self.ss.TDS.run()

            if self.ss.dae.t < sub_target - 1e-6:
                tds_failed = True
                break

        # 更新 prev M/D (无论是否 TDS 失败, 下次 reset 会重置)
        self._prev_M = M_new.copy()
        self._prev_D = D_new.copy()

        self.step_count += 1

        # 3. 读取状态
        omega = self._get_vsg_omega()
        P_es = self._get_vsg_power()
        omega_dot = self._compute_omega_dot(omega, P_es)

        # 4. 构建观测
        obs = self._build_obs(omega, omega_dot, P_es)

        # 5. 计算奖励 (Eq. 17-18: 物理 delta_M/delta_D，与论文公式和 Simulink 路径一致)
        rewards, r_f_sum, r_h_sum, r_d_sum = self._compute_rewards(
            omega, omega_dot, delta_M, delta_D)

        # 6. 终止条件
        done = self.step_count >= self.STEPS_PER_EPISODE

        # TDS 失败: 提前终止 + 惩罚奖励
        if tds_failed:
            rewards = {i: -50.0 for i in range(self.N_AGENTS)}
            done = True

        # 频率 (Hz)
        freq_hz = omega * self.FN

        # Max frequency deviation from nominal 50 Hz (per-step, not episode-peak)
        max_freq_deviation_hz = float(np.max(np.abs(freq_hz - self.FN)))

        info = {
            "time": float(self.ss.dae.t),
            "freq_hz": freq_hz.copy(),
            "omega": omega.copy(),
            "omega_dot": omega_dot.copy(),
            "P_es": P_es.copy(),
            "M_es": M_new.copy(),
            "D_es": D_new.copy(),
            "delta_M": delta_M.copy(),
            "delta_D": delta_D.copy(),
            "r_f": r_f_sum,
            "r_h": r_h_sum,
            "r_d": r_d_sum,
            "max_freq_deviation_hz": max_freq_deviation_hz,
            "tds_failed": tds_failed,
        }

        self._prev_omega = omega.copy()
        return obs, rewards, done, info

    # ─── GENCLS 状态读取 ───

    def _get_vsg_omega(self):
        """获取 VSG 的转速 (p.u.)."""
        omega = np.zeros(self.N_AGENTS)
        for i, idx in enumerate(self.vsg_idx):
            pos = list(self.ss.GENCLS.idx.v).index(idx)
            omega[i] = self.ss.GENCLS.omega.v[pos]
        return omega

    def _get_vsg_power(self):
        """获取 VSG 的有功出力 (p.u.)."""
        P = np.zeros(self.N_AGENTS)
        for i, idx in enumerate(self.vsg_idx):
            pos = list(self.ss.GENCLS.idx.v).index(idx)
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
            Pm = self.ss.GENCLS.p0.v[pos]  # 潮流解出的初始机械功率
            Pe = P[i]
            omega_dot[i] = (Pm - Pe - D * (omega[i] - 1.0)) / max(M, 0.1)
        return omega_dot

    # ─── 通信 ───

    def _reset_comm(self):
        """重置通信链路状态."""
        self.comm_eta = {}
        for i, neighbors in self.COMM_ADJ.items():
            for j in neighbors:
                if (j, i) in self.comm_eta:
                    self.comm_eta[(i, j)] = self.comm_eta[(j, i)]
                else:
                    self.comm_eta[(i, j)] = 0 if self.rng.random() < self.comm_fail_prob else 1

    # ─── 观测 ───

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
            o[0] = P_es[i] / 2.0
            o[1] = d_omega[i] / 3.0
            o[2] = omega_dot[i] * self._omega_scale / 5.0

            # 邻居信息 (支持通信延迟)
            for k, j in enumerate(self.COMM_ADJ[i]):
                if k >= self.MAX_NEIGHBORS:
                    break
                if self.comm_eta.get((i, j), 0) == 1:
                    d_omega_j = (omega[j] - 1.0) * self._omega_scale
                    od_j = omega_dot[j] * self._omega_scale

                    if self.comm_delay_steps > 0 and (i, j) in self._delayed_omega:
                        o[3 + k] = self._delayed_omega[(i, j)][0] / 3.0
                        o[3 + self.MAX_NEIGHBORS + k] = self._delayed_omega_dot[(i, j)][0] / 5.0
                        self._delayed_omega[(i, j)].append(d_omega_j)
                        self._delayed_omega_dot[(i, j)].append(od_j)
                    else:
                        o[3 + k] = d_omega_j / 3.0
                        o[3 + self.MAX_NEIGHBORS + k] = od_j / 5.0

            obs[i] = o
        return obs

    # ─── 奖励 ───

    def _compute_rewards(self, omega, omega_dot, delta_M, delta_D):
        """计算每个 agent 的奖励 (Eq. 14-18 + 绝对频率偏差补充项).

        - r_f (Eq.15-16): 局部邻居平均频率同步惩罚
        - r_abs: -d_omega_i^2, 绝对频率偏差惩罚 (解决紧耦合系统 r_f 信号过弱)
        - r_h (Eq.17): -(ΔH_avg)^2, 物理惯量调整均值 (ΔH = ΔM/2, M = 2H)
        - r_d (Eq.18): -(ΔD_avg)^2, 物理阻尼调整均值

        Args:
            omega: shape (N,), 转速 p.u.
            omega_dot: shape (N,), 转速变化率
            delta_M: shape (N,), 物理惯量增量 ΔM (s); ΔH = ΔM/2
            delta_D: shape (N,), 物理阻尼增量 ΔD (p.u.)
        """
        d_omega = (omega - 1.0) * self.FN  # Hz 偏差

        # Eq.17-18: 物理调整量全局均值 (先均值再平方, 与 Simulink 路径一致)
        ah_avg = float(np.mean(delta_M)) / 2.0   # ΔH_avg = mean(ΔM)/2
        ad_avg = float(np.mean(delta_D))          # ΔD_avg

        rewards = {}
        r_f_total, r_h_total, r_d_total = 0.0, 0.0, 0.0
        for i in range(self.N_AGENTS):
            # Eq. 16: 局部加权平均频率
            sum_w = d_omega[i]
            n_active = 1
            for j in self.COMM_ADJ[i]:
                if self.comm_eta.get((i, j), 0) == 1:
                    sum_w += d_omega[j]
                    n_active += 1
            omega_bar = sum_w / n_active

            # Eq. 15: 频率同步惩罚 (局部)
            r_f = -(d_omega[i] - omega_bar) ** 2
            for j in self.COMM_ADJ[i]:
                if self.comm_eta.get((i, j), 0) == 1:
                    r_f -= (d_omega[j] - omega_bar) ** 2

            # 绝对频率偏差惩罚 (补充项: 给 agent "把频率拉回 50Hz" 的信号)
            r_abs = -(d_omega[i]) ** 2

            r_h = -(ah_avg) ** 2
            r_d = -(ad_avg) ** 2

            rewards[i] = (self.PHI_F * r_f + self.PHI_ABS * r_abs
                          + self.PHI_H * r_h + self.PHI_D * r_d)
            r_f_total += self.PHI_F * r_f + self.PHI_ABS * r_abs
            r_h_total += self.PHI_H * r_h
            r_d_total += self.PHI_D * r_d

        return rewards, r_f_total, r_h_total, r_d_total

    # ─── 分析工具 ───

    def get_genrou_omega(self):
        """获取 GENROU 同步发电机的转速."""
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
