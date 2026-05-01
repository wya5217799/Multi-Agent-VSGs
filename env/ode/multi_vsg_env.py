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
from utils.ode_heterogeneity import generate_heterogeneous_params


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

        # 异质化基准参数
        H_base = cfg.H_ES0.copy()
        D_base = cfg.D_ES0.copy()
        if getattr(cfg, 'ODE_HETEROGENEOUS', False):
            seed = getattr(cfg, 'ODE_HETEROGENEITY_SEED', 2023)
            H_base = generate_heterogeneous_params(
                H_base, getattr(cfg, 'ODE_H_SPREAD', 0.30), seed,
            )
            D_base = generate_heterogeneous_params(
                D_base, getattr(cfg, 'ODE_D_SPREAD', 0.30), seed + 1,
            )
        self._H_base = H_base
        self._D_base = D_base

        # 电力系统
        self.ps = PowerSystem(
            self.L, H_base, D_base,
            dt=cfg.DT, fn=cfg.OMEGA_N / (2 * np.pi),
            B_matrix=getattr(cfg, 'B_MATRIX', None),
            V_bus=getattr(cfg, 'V_BUS', None),
            network_mode=getattr(cfg, 'ODE_NETWORK_MODE', 'linear'),
            governor_enabled=getattr(cfg, 'ODE_GOVERNOR_ENABLED', False),
            governor_R=getattr(cfg, 'ODE_GOVERNOR_R', 0.05),
            governor_tau_g=getattr(cfg, 'ODE_GOVERNOR_TAU_G', 0.5),
        )

        # 随机数生成器
        self.rng = np.random.default_rng()

        # 通信延迟
        self.comm_delay_steps = comm_delay_steps
        self._delayed_omega = {}      # 缓存: {(i,j): deque of omega values}
        self._delayed_omega_dot = {}

        self.step_count = 0
        self.current_delta_u = np.zeros(self.N)

        # I-1 fix 2026-05-02: pre-init breakdown cache so info dict access is
        # safe even if a caller introspects info before any step() runs (rare
        # but possible via subclass / future code path).
        self._last_reward_breakdown: dict | None = None

    def seed(self, s):
        self.rng = np.random.default_rng(s)

    def reset(self, delta_u=None, event_schedule=None, scenario=None):
        """重置环境.

        Parameters
        ----------
        delta_u : np.ndarray or None
            静态扰动 (legacy).
        event_schedule : EventSchedule or None
            时变事件. 若给出则优先于 delta_u, 并禁用 random_disturbance.
        scenario : ODEScenario or None
            (D2 2026-05-02 加性扩展) 若给出则优先于 delta_u；从 VO 读取
            ``delta_u`` 和 ``comm_failed_links`` 一起套用，等价于旧 caller
            手动 ``env.forced_link_failures = ...`` + ``env.reset(delta_u=...)``。
            参见 docs/paper/ode_paper_alignment_deviations.md §D2。
        """
        # D2 (2026-05-02): scenario= takes precedence over legacy delta_u.
        if scenario is not None:
            from env.ode.ode_scenario import ODEScenario  # local to avoid cycle on import
            if not isinstance(scenario, ODEScenario):
                raise TypeError(
                    f"scenario must be ODEScenario, got {type(scenario).__name__}"
                )
            du, fl = scenario.to_legacy_tuple()
            self.current_delta_u = du
            self.forced_link_failures = fl
            self.ps.reset(delta_u=self.current_delta_u)
        elif event_schedule is not None:
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
        # M3 fix 2026-05-02: when forced failures are specified (either by
        # legacy ``forced_link_failures`` attr or by ODEScenario.comm_failed_links),
        # the scenario VO is authoritative — env-level probabilistic
        # ``comm_fail_prob`` MUST NOT layer extra random failures on top.
        # Previously ``comm.reset(rng)`` randomized eta first, then forced
        # overrides only set 0s, leaving prob-failed-but-not-forced links 0.
        # See critic verdict M3 in quality_reports/verdicts/2026-05-02_ode_gate_1to5.md.
        if self.forced_link_failures:
            self.comm.reset_no_failure()
            for i, j in self.forced_link_failures:
                self.comm.eta[(i, j)] = 0
        else:
            self.comm.reset(rng=self.rng)
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
        H_es = np.copy(self._H_base)
        D_es = np.copy(self._D_base)
        delta_H = np.zeros(self.N)
        delta_D = np.zeros(self.N)

        for i in range(self.N):
            a = np.clip(actions[i], -1.0, 1.0)
            # Zero-centered mapping: a=0 → ΔH=0 (保持基准参数，与论文 Eq.12-13 语义一致)
            delta_H[i] = a[0] * cfg.DH_MAX if a[0] >= 0 else a[0] * (-cfg.DH_MIN)
            delta_D[i] = a[1] * cfg.DD_MAX if a[1] >= 0 else a[1] * (-cfg.DD_MIN)
            H_es[i] = self._H_base[i] + delta_H[i]
            D_es[i] = self._D_base[i] + delta_D[i]

        # 确保 H > 0, D > 0 (物理约束)
        # §15 (D2): track clip events for transparency (no silent floor-clipping)
        _H_FLOOR = 8.0
        _D_FLOOR = 0.1
        H_pre_clip = H_es.copy()
        D_pre_clip = D_es.copy()
        H_es = np.maximum(H_es, _H_FLOOR)
        D_es = np.maximum(D_es, _D_FLOOR)
        H_clipped = bool(np.any(H_pre_clip < _H_FLOOR))
        D_clipped = bool(np.any(D_pre_clip < _D_FLOOR))

        # 2. 设置参数并积分一步
        self.ps.set_params(H_es, D_es)
        result = self.ps.step()

        self.step_count += 1

        # 3. 构建观测
        obs = self._build_observations(result)

        # 4. 计算奖励 (Eq. 17-18: 物理 delta_H/delta_D，与论文公式一致)
        rewards, r_f_sum, r_h_sum, r_d_sum = self._compute_rewards(result, delta_H, delta_D)

        # 5. 终止条件: episode 长度耗尽 OR §15 数值安全失败
        termination_reason = result.get('termination_reason', '')
        done = (self.step_count >= cfg.STEPS_PER_EPISODE) or bool(termination_reason)

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
            # D2 (2026-05-02 Stage 3): full reward decomposition (paper §10.3).
            # Legacy keys r_f/r_h/r_d preserved above for backwards compat.
            'reward_components': {
                'r_f_per_agent': list(self._last_reward_breakdown['r_f_per_agent']),
                'r_h_per_agent': list(self._last_reward_breakdown['r_h_per_agent']),
                'r_d_per_agent': list(self._last_reward_breakdown['r_d_per_agent']),
                'r_f_total': self._last_reward_breakdown['r_f_total'],
                'r_h_total': self._last_reward_breakdown['r_h_total'],
                'r_d_total': self._last_reward_breakdown['r_d_total'],
                'phi_f': self._last_reward_breakdown['phi_f'],
                'phi_h': self._last_reward_breakdown['phi_h'],
                'phi_d': self._last_reward_breakdown['phi_d'],
            },
            # D2 (2026-05-02): explicit safety/clip telemetry, see §15 + ode_paper_alignment_deviations.md
            'action_clip': {
                'H_clipped': H_clipped,
                'D_clipped': D_clipped,
                'H_min_pre_clip': float(H_pre_clip.min()),
                'D_min_pre_clip': float(D_pre_clip.min()),
                'H_floor': _H_FLOOR,
                'D_floor': _D_FLOOR,
            },
            'termination_reason': termination_reason,
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

        Stage 3 (2026-05-02): delegates to ``env.ode.reward.training_reward_local``
        for paper-anchored formula. Signature preserved for legacy callers
        (4-tuple: rewards, r_f_total, r_h_total, r_d_total).

        See:
          - env/ode/reward.py — pure reward functions
          - docs/paper/python_ode_env_boundary_cn.md §10 / §11
          - docs/paper/ode_paper_alignment_deviations.md §D2

        Args:
            state: ODE 积分结果
            delta_H: shape (N,), 物理惯量增量 ΔH (s)
            delta_D: shape (N,), 物理阻尼增量 ΔD (p.u.)
        """
        from env.ode.reward import training_reward_local

        # Build a {(i,j): eta} dict from CommunicationGraph for the pure func.
        comm_eta: dict[tuple[int, int], int] = {}
        for i in range(self.N):
            for j in self.comm.get_neighbors(i):
                comm_eta[(i, j)] = 1 if self.comm.is_link_active(i, j) else 0

        out = training_reward_local(
            omega=state['omega'],
            delta_H=delta_H,
            delta_D=delta_D,
            comm_neighbors={i: list(self.comm.get_neighbors(i)) for i in range(self.N)},
            comm_eta=comm_eta,
        )
        # Cache the full breakdown so step() can attach it to info without recomputing.
        self._last_reward_breakdown = out
        return out["rewards"], out["r_f_total"], out["r_h_total"], out["r_d_total"]
