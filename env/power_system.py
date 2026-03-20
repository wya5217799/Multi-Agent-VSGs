"""
多母线电力系统频率动态模型

论文 Eq. (4) — 2N 状态系统:
    Δθ̇ = Δω
    Δω̇ = H_es⁻¹ · Δu - H_es⁻¹ · L · Δθ - H_es⁻¹ · D_es · Δω

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


class PowerSystem:
    """4 母线两区域系统频率动态仿真."""

    def __init__(self, L, H_es0, D_es0, dt=0.2):
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
        """
        self.L = L.astype(np.float64)
        self.N = L.shape[0]
        self.H_es0 = H_es0.copy()
        self.D_es0 = D_es0.copy()
        self.dt = dt

        # 当前参数 (可被 RL agent 修改)
        self.H_es = H_es0.copy()
        self.D_es = D_es0.copy()

        # 状态: [Δθ_0..Δθ_{N-1}, Δω_0..Δω_{N-1}]
        self.state = np.zeros(2 * self.N)

        # 扰动
        self.delta_u = np.zeros(self.N)

        # 时间
        self.current_time = 0.0

    def reset(self, delta_u=None):
        """
        重置系统到稳态.

        Parameters
        ----------
        delta_u : np.ndarray, shape (N,), optional
            扰动功率向量 (p.u.). 若为 None 则全零.
        """
        self.state = np.zeros(2 * self.N)
        self.H_es = self.H_es0.copy()
        self.D_es = self.D_es0.copy()
        self.current_time = 0.0

        if delta_u is not None:
            self.delta_u = delta_u.copy()
        else:
            self.delta_u = np.zeros(self.N)

    def set_params(self, H_es, D_es):
        """设置当前惯量和阻尼参数."""
        self.H_es = H_es.copy()
        self.D_es = D_es.copy()

    def _dynamics(self, t, state):
        """
        ODE 右端项 (Eq. 4).

        state = [Δθ_0..Δθ_{N-1}, Δω_0..Δω_{N-1}]

        Δθ̇ = Δω
        Δω̇ = H_es⁻¹ · (Δu - L · Δθ - D_es · Δω)
        """
        theta = state[:self.N]
        omega = state[self.N:]
        H_inv = 1.0 / self.H_es

        dtheta_dt = omega
        domega_dt = H_inv * (self.delta_u - self.L @ theta - self.D_es * omega)

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

        theta = self.state[:self.N]
        omega = self.state[self.N:]

        # 频率变化率 (从动力学方程直接计算)
        H_inv = 1.0 / self.H_es
        omega_dot = H_inv * (self.delta_u - self.L @ theta - self.D_es * omega)

        # 储能输出功率 ΔP_es = (L · Δθ)_i (Eq. 3)
        P_es = self.L @ theta

        # 频率 (Hz)
        freq_hz = 50.0 + omega / (2 * np.pi)

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
        H_inv = 1.0 / self.H_es
        omega_dot = H_inv * (self.delta_u - self.L @ theta - self.D_es * omega)
        P_es = self.L @ theta
        freq_hz = 50.0 + omega / (2 * np.pi)
        return {
            'theta': theta.copy(),
            'omega': omega.copy(),
            'omega_dot': omega_dot.copy(),
            'P_es': P_es.copy(),
            'freq_hz': freq_hz.copy(),
            'time': self.current_time,
        }
