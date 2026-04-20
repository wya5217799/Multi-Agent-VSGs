"""
多母线电力系统频率动态模型

论文 Eq. (4) — 2N 状态系统:
    Δθ̇ = Δω
    2H · Δω̇ = Δu - L · Δθ - D · Δω
    即 Δω̇ = (2H)⁻¹ · (Δu - L · Δθ - D · Δω)

其中:
    Δθ ∈ R^N : 电压角偏差
    Δω ∈ R^N : 频率偏差
    H_es     : 虚拟惯量对角矩阵
    D_es     : 虚拟阻尼对角矩阵
    L        : 加权 Laplacian 矩阵
    Δu       : 外部扰动 (负荷变化)
"""

import numpy as np
from scipy.integrate import solve_ivp
from utils.ode_events import (
    DisturbanceEvent,
    LineTripEvent,  # noqa: F401 — used in Task 5 (line-trip events)
    EventSchedule,
)


class PowerSystem:
    """4 母线两区域系统频率动态仿真."""

    def __init__(self, L, H_es0, D_es0, dt=0.2, fn=50.0):
        """
        Parameters
        ----------
        L : np.ndarray, shape (N, N)
            加权 Laplacian 矩阵
        H_es0 : np.ndarray, shape (N,)
            基础虚拟惯量
        D_es0 : np.ndarray, shape (N,)
            基础虚拟阻尼
        dt : float
            控制步长 (s)
        fn : float
            标称频率 (Hz), 50.0 for Kundur, 60.0 for NE
        """
        self.L = L.astype(np.float64)
        self.N = L.shape[0]
        self.H_es0 = H_es0.copy()
        self.D_es0 = D_es0.copy()
        self.dt = dt
        self.fn = fn
        self.omega_s = 2.0 * np.pi * fn  # 314.16 rad/s (50Hz)

        # 当前参数 (可被 RL agent 修改)
        self.H_es = H_es0.copy()
        self.D_es = D_es0.copy()

        # 状态: [Δθ_0..Δθ_{N-1}, Δω_0..Δω_{N-1}]
        self.state = np.zeros(2 * self.N)

        # 扰动
        self.delta_u = np.zeros(self.N)

        # 时间
        self.current_time = 0.0

        self._event_schedule = None
        self._step_count = 0  # integer step counter for event scheduling

    def reset(self, delta_u=None, event_schedule=None):
        """重置系统到稳态.

        Parameters
        ----------
        delta_u : np.ndarray, shape (N,), optional
            静态扰动 — 兼容旧路径.
        event_schedule : EventSchedule, optional
            时变扰动/拓扑事件序列. 事件在 step 起始时刻生效.
        """
        self.state = np.zeros(2 * self.N)
        self.H_es = self.H_es0.copy()
        self.D_es = self.D_es0.copy()
        self.current_time = 0.0
        self._step_count = 0

        self._event_schedule = event_schedule
        if event_schedule is not None:
            # Apply t=0 events immediately; later events fire during step()
            self.delta_u = np.zeros(self.N)
            for ev in event_schedule.events:
                if ev.t == 0.0 and isinstance(ev, DisturbanceEvent):
                    self.delta_u = ev.delta_u.copy()
        elif delta_u is not None:
            self.delta_u = np.asarray(delta_u, dtype=np.float64).copy()
        else:
            self.delta_u = np.zeros(self.N)

    def _apply_events(self) -> None:
        """Apply scheduled events whose nominal time falls within the current step.

        Event time t fires on the step that integrates the interval ending at t:
            ev_step = round(t / dt) - 1  (for t > 0)
        This avoids float accumulation errors and ensures the ODE integration
        across t uses the updated parameters.

        Events at t=0 are applied during reset() and skipped here.
        """
        if self._event_schedule is None:
            return
        current_step = self._step_count
        for ev in self._event_schedule.events:
            if ev.t == 0.0:
                continue  # already applied in reset()
            ev_step = max(0, int(round(ev.t / self.dt)) - 1)
            if ev_step == current_step:
                if isinstance(ev, DisturbanceEvent):
                    self.delta_u = ev.delta_u.copy()
                # LineTripEvent handled in Task 5

    def set_params(self, H_es, D_es):
        """设置当前惯量和阻尼参数."""
        self.H_es = H_es.copy()
        self.D_es = D_es.copy()

    def _dynamics(self, t, state):
        """
        ODE 右端项 (Eq. 4).

        state = [Δθ_0..Δθ_{N-1}, Δω_0..Δω_{N-1}]

        Δθ̇ = Δω
        Δω̇ = (2H)⁻¹ · (Δu - L · Δθ - D · Δω)   ← 论文 Eq.4: 2H·Δω̇ = ...
        """
        theta = state[:self.N]
        omega = state[self.N:]
        M_inv = 1.0 / (2.0 * self.H_es)  # 论文 Eq.4: 2H·dω/dt = ..., 所以 dω/dt = 1/(2H)·(...)

        dtheta_dt = omega
        domega_dt = M_inv * (self.omega_s * (self.delta_u - self.L @ theta) - self.D_es * omega)

        return np.concatenate([dtheta_dt, domega_dt])

    def step(self):
        """
        积分一步 (dt 秒).

        Returns
        -------
        result : dict
            theta : np.ndarray (N,) — 角度偏差
            omega : np.ndarray (N,) — 频率偏差 (rad/s)
            omega_dot : np.ndarray (N,) — 频率变化率 (rad/s²)
            P_es : np.ndarray (N,) — 储能输出功率 ΔP_es = (L · Δθ)_i
            freq_hz : np.ndarray (N,) — 频率 (Hz)
        """
        t_start = self.current_time
        t_end = t_start + self.dt

        # Apply events whose nominal time maps to current step index
        self._apply_events()

        sol = solve_ivp(
            self._dynamics,
            [t_start, t_end],
            self.state,
            method='RK45',
            rtol=1e-6,
            atol=1e-8,
            max_step=self.dt / 10,
        )

        self.state = sol.y[:, -1]
        self.current_time = t_end
        self._step_count += 1

        theta = self.state[:self.N]
        omega = self.state[self.N:]

        # 频率变化率 (从动力学方程直接计算)
        M_inv = 1.0 / (2.0 * self.H_es)  # Eq.4: 2H·dω/dt = ...
        omega_dot = M_inv * (self.omega_s * (self.delta_u - self.L @ theta) - self.D_es * omega)

        # 储能输出功率 ΔP_es = (L · Δθ)_i (Eq. 3)
        P_es = self.L @ theta

        # 频率 (Hz)
        freq_hz = self.fn + omega / (2 * np.pi)

        return {
            'theta': theta.copy(),
            'omega': omega.copy(),
            'omega_dot': omega_dot.copy(),
            'P_es': P_es.copy(),
            'freq_hz': freq_hz.copy(),
            'time': self.current_time,
        }

    def get_state(self):
        """返回当前状态的快照."""
        theta = self.state[:self.N]
        omega = self.state[self.N:]
        M_inv = 1.0 / (2.0 * self.H_es)  # Eq.4: 2H·dω/dt = ...
        omega_dot = M_inv * (self.omega_s * (self.delta_u - self.L @ theta) - self.D_es * omega)
        P_es = self.L @ theta
        freq_hz = self.fn + omega / (2 * np.pi)
        return {
            'theta': theta.copy(),
            'omega': omega.copy(),
            'omega_dot': omega_dot.copy(),
            'P_es': P_es.copy(),
            'freq_hz': freq_hz.copy(),
            'time': self.current_time,
        }
