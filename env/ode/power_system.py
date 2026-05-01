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
from env.network_topology import build_laplacian
from utils.ode_events import (
    DisturbanceEvent,
    LineTripEvent,
    EventSchedule,
)

# D3 (2026-05-02): Fixed-step RK4 for byte-level reproducibility.
# See docs/paper/ode_paper_alignment_deviations.md §D3 for rationale.
_RK4_DT_SUBSTEP: float = 0.01            # boundary doc §12 recommends 0.005-0.01s
# §15 numerical safety thresholds — calibrated to project unit convention.
# Note: boundary doc §15 suggests |dw|<10, |theta|<10 in dimensionless form.
# This codebase keeps omega in rad/s (NOT pu) and theta in rad (linearized swing
# without governor → drift expected). Thresholds therefore raised to catch
# numerical runaway only, not normal linear-model drift.
_MAX_ABS_OMEGA: float = 50.0             # rad/s — ~8 Hz deviation, far past any physical scenario
_MAX_ABS_THETA: float = 100.0            # rad — ~16 cycles; linear model has no restoring mean


class PowerSystem:
    """4 母线两区域系统频率动态仿真."""

    def __init__(self, L, H_es0, D_es0, dt=0.2, fn=50.0,
                 B_matrix=None, V_bus=None, network_mode='linear',
                 governor_enabled=False, governor_R=0.05, governor_tau_g=0.5):
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

        # 扰动
        self.delta_u = np.zeros(self.N)

        # 时间
        self.current_time = 0.0

        self._event_schedule = None
        self._step_count = 0  # integer step counter for event scheduling

        if network_mode not in ('linear', 'nonlinear'):
            raise ValueError(f"network_mode must be 'linear' or 'nonlinear', got {network_mode!r}")
        self.network_mode = network_mode
        if B_matrix is not None:
            self.B_matrix = B_matrix.astype(np.float64).copy()
            self._B_matrix0 = B_matrix.astype(np.float64).copy()
        else:
            self.B_matrix = None
            self._B_matrix0 = None
        self._L0 = self.L.copy()
        self.V_bus = (V_bus.astype(np.float64) if V_bus is not None else None)
        if network_mode == 'nonlinear' and (B_matrix is None or V_bus is None):
            raise ValueError("network_mode='nonlinear' requires B_matrix and V_bus")

        self.governor_enabled = bool(governor_enabled)
        if governor_R <= 0:
            raise ValueError(f"governor_R must be > 0, got {governor_R}")
        if governor_tau_g <= 0:
            raise ValueError(f"governor_tau_g must be > 0, got {governor_tau_g}")
        self.governor_R = float(governor_R)
        self.governor_tau_g = float(governor_tau_g)

        state_dim = 3 * self.N if self.governor_enabled else 2 * self.N
        self.state = np.zeros(state_dim)

        # D3 RK4 substep config
        self._rk4_dt_substep = _RK4_DT_SUBSTEP
        self._n_substeps = max(1, int(round(self.dt / self._rk4_dt_substep)))
        self._rk4_dt_actual = self.dt / self._n_substeps

        # §15 termination tracking: empty string = healthy, non-empty = failed
        self._termination_reason: str = ""

    def reset(self, delta_u=None, event_schedule=None):
        """重置系统到稳态.

        Parameters
        ----------
        delta_u : np.ndarray, shape (N,), optional
            静态扰动 — 兼容旧路径.
        event_schedule : EventSchedule, optional
            时变扰动/拓扑事件序列. 事件在 step 起始时刻生效.
        """
        self.state = np.zeros(self.state.shape[0])
        self.H_es = self.H_es0.copy()
        self.D_es = self.D_es0.copy()
        self._termination_reason = ""
        # Restore original topology so each episode starts from intact network
        if self._B_matrix0 is not None:
            self.B_matrix = self._B_matrix0.copy()
        self.L = self._L0.copy()
        self.current_time = 0.0
        self._step_count = 0
        self._event_schedule = event_schedule
        if event_schedule is not None:
            self.delta_u = np.zeros(self.N)
            for ev in event_schedule.events:
                if ev.t == 0.0:
                    if isinstance(ev, DisturbanceEvent):
                        self.delta_u = ev.delta_u.copy()
                    elif isinstance(ev, LineTripEvent):
                        if self.B_matrix is None or self.V_bus is None:
                            raise RuntimeError(
                                "LineTripEvent requires B_matrix and V_bus."
                            )
                        self.B_matrix[ev.bus_i, ev.bus_j] = 0.0
                        self.B_matrix[ev.bus_j, ev.bus_i] = 0.0
                        self.L = build_laplacian(self.B_matrix, self.V_bus)
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
                elif isinstance(ev, LineTripEvent):
                    if self.B_matrix is None or self.V_bus is None:
                        raise RuntimeError(
                            "LineTripEvent requires PowerSystem to be constructed with "
                            "B_matrix and V_bus."
                        )
                    self.B_matrix[ev.bus_i, ev.bus_j] = 0.0
                    self.B_matrix[ev.bus_j, ev.bus_i] = 0.0
                    self.L = build_laplacian(self.B_matrix, self.V_bus)

    def set_params(self, H_es, D_es):
        """设置当前惯量和阻尼参数."""
        self.H_es = H_es.copy()
        self.D_es = D_es.copy()

    def _coupling(self, theta):
        """Network power injection: L·θ (linear) or Σ V_i V_j B_ij sin(θ_i-θ_j) (nonlinear)."""
        if self.network_mode == 'linear':
            return self.L @ theta
        diff = theta[:, None] - theta[None, :]           # θ_i - θ_j
        coupling = self.V_bus[:, None] * self.V_bus[None, :] * self.B_matrix * np.sin(diff)
        return coupling.sum(axis=1)

    def _dynamics(self, t, state):
        """
        ODE 右端项 (Eq. 4).

        Without governor (2N state):
            state = [Δθ_0..Δθ_{N-1}, Δω_0..Δω_{N-1}]
            Δθ̇ = Δω
            Δω̇ = (2H)⁻¹ · (Δu - L · Δθ - D · Δω)

        With governor (3N state):
            state = [Δθ, Δω, P_gov]
            Δθ̇ = Δω
            2H · Δω̇ = ω_s · (Δu + P_gov - coupling) - D · Δω
            τ_G · dP_gov/dt = -(P_gov + (ω/ω_s) / R)
        """
        theta = state[:self.N]
        omega = state[self.N:2 * self.N]
        M_inv = 1.0 / (2.0 * self.H_es)
        coupling = self._coupling(theta)
        dtheta_dt = omega

        if self.governor_enabled:
            P_gov = state[2 * self.N:3 * self.N]
            domega_dt = M_inv * (
                self.omega_s * (self.delta_u + P_gov - coupling) - self.D_es * omega
            )
            dP_gov_dt = -(P_gov + (omega / self.omega_s) / self.governor_R) / self.governor_tau_g
            return np.concatenate([dtheta_dt, domega_dt, dP_gov_dt])

        domega_dt = M_inv * (self.omega_s * (self.delta_u - coupling) - self.D_es * omega)
        return np.concatenate([dtheta_dt, domega_dt])

    def _rk4_integrate(self, t_start: float, x0: np.ndarray, dt_total: float) -> np.ndarray:
        """Fixed-step classical RK4 integrator over [t_start, t_start+dt_total].

        Subdivides into ``self._n_substeps`` substeps of width ``self._rk4_dt_actual``.
        D3 (2026-05-02): replaces ``scipy.integrate.solve_ivp`` for byte-level
        reproducibility. See docs/paper/ode_paper_alignment_deviations.md §D3.
        """
        x = x0.copy()
        h = self._rk4_dt_actual
        t = t_start
        for _ in range(self._n_substeps):
            k1 = self._dynamics(t,         x)
            k2 = self._dynamics(t + h / 2, x + (h / 2) * k1)
            k3 = self._dynamics(t + h / 2, x + (h / 2) * k2)
            k4 = self._dynamics(t + h,     x + h * k3)
            x = x + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
            t += h
        return x

    def _check_safety(self, state: np.ndarray) -> str:
        """§15 numerical-safety gate. Returns reason string ('' = healthy).

        Checks (in priority order):
            1. NaN / Inf in state
            2. |Δω| beyond threshold (loss of synch / runaway)
            3. |Δθ| beyond threshold (angle wrap / pole-slip)

        H/D positivity is enforced upstream by env clip floor; not re-checked here.
        """
        if not np.all(np.isfinite(state)):
            return "non_finite_state"
        omega = state[self.N:2 * self.N]
        if np.any(np.abs(omega) > _MAX_ABS_OMEGA):
            return "omega_exceeds_threshold"
        theta = state[:self.N]
        if np.any(np.abs(theta) > _MAX_ABS_THETA):
            return "theta_exceeds_threshold"
        return ""

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
            termination_reason : str — '' if healthy, else §15 failure reason

        Notes
        -----
        D3 (2026-05-02): integration is fixed-step RK4 with ``n_substeps``
        per control step. State is kept advanced even on safety failure so
        the env layer can inspect the failure mode; ``termination_reason``
        signals the env to set ``done=True``.
        """
        t_start = self.current_time
        t_end = t_start + self.dt

        # Apply events whose nominal time maps to current step index
        self._apply_events()

        # D3: fixed-step RK4 (replaces solve_ivp(RK45))
        self.state = self._rk4_integrate(t_start, self.state, self.dt)

        # §15: numerical safety gate
        self._termination_reason = self._check_safety(self.state)

        self.current_time = t_end
        self._step_count += 1

        theta = self.state[:self.N]
        omega = self.state[self.N:2 * self.N]
        M_inv = 1.0 / (2.0 * self.H_es)
        coupling = self._coupling(theta)
        if self.governor_enabled:
            P_gov = self.state[2 * self.N:3 * self.N]
            omega_dot = M_inv * (
                self.omega_s * (self.delta_u + P_gov - coupling) - self.D_es * omega
            )
        else:
            omega_dot = M_inv * (
                self.omega_s * (self.delta_u - coupling) - self.D_es * omega
            )
        P_es = coupling
        freq_hz = self.fn + omega / (2 * np.pi)

        return {
            'theta': theta.copy(),
            'omega': omega.copy(),
            'omega_dot': omega_dot.copy(),
            'P_es': P_es.copy(),
            'freq_hz': freq_hz.copy(),
            'time': self.current_time,
            'termination_reason': self._termination_reason,
        }

    def get_state(self):
        """返回当前状态的快照."""
        theta = self.state[:self.N]
        omega = self.state[self.N:2 * self.N]
        M_inv = 1.0 / (2.0 * self.H_es)
        coupling = self._coupling(theta)
        if self.governor_enabled:
            P_gov = self.state[2 * self.N:3 * self.N]
            omega_dot = M_inv * (
                self.omega_s * (self.delta_u + P_gov - coupling) - self.D_es * omega
            )
        else:
            omega_dot = M_inv * (
                self.omega_s * (self.delta_u - coupling) - self.D_es * omega
            )
        P_es = coupling
        freq_hz = self.fn + omega / (2 * np.pi)
        return {
            'theta': theta.copy(),
            'omega': omega.copy(),
            'omega_dot': omega_dot.copy(),
            'P_es': P_es.copy(),
            'freq_hz': freq_hz.copy(),
            'time': self.current_time,
        }
