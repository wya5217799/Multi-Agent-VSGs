"""
Modified Kundur Two-Area System -- Gymnasium Environment
=========================================================

Two simulation backends (following NE39 project pattern):

1. **Standalone ODE mode** (``KundurStandaloneEnv``):
   Pure-Python 4-machine swing-equation model with RK4 integration.
   No external dependencies beyond NumPy.  Suitable for fast RL training.

2. **MATLAB/Simulink mode** (``KundurSimulinkEnv``):
   Interfaces with kundur_vsg.slx via ``matlab.engine``.
   Sets VSG parameters (M, D) through ``set_param``, reads omega / P_e
   from the MATLAB workspace via ToWorkspace loggers.

Both environments expose the same Gymnasium ``(obs, reward, terminated,
truncated, info)`` API.

Reference
---------
Yang et al., IEEE TPWRS 2023 — Multi-Agent SAC for Distributed VSG Control.
"""

from __future__ import annotations

import os
import warnings
from dataclasses import replace
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import gymnasium as gym
from gymnasium import spaces
from scenarios.contract import KUNDUR as _CONTRACT
from scenarios.kundur.config_simulink import (
    KUNDUR_BRIDGE_CONFIG,
    T_WARMUP as CONFIG_T_WARMUP,
)

warnings.filterwarnings("ignore", category=UserWarning, module="matlab")

# ---------------------------------------------------------------------------
# Constants — contract values from scenarios.contract, rest inlined
# ---------------------------------------------------------------------------

N_AGENTS: int = _CONTRACT.n_agents
OBS_DIM: int = _CONTRACT.obs_dim
ACT_DIM: int = _CONTRACT.act_dim

VSG_M0: float = 12.0
VSG_D0: float = 3.0
VSG_SN: float = 200.0     # MVA
VSG_RA: float = 0.003
VSG_XD1: float = 0.30
VSG_P0: float = 0.5       # p.u. on VSG base

DM_MIN: float = -6.0
DM_MAX: float = 18.0
DD_MIN: float = -1.5
DD_MAX: float = 4.5

M_LO: float = VSG_M0 + DM_MIN
M_HI: float = VSG_M0 + DM_MAX
D_LO: float = VSG_D0 + DD_MIN
D_HI: float = VSG_D0 + DD_MAX

DT: float = _CONTRACT.dt
T_EPISODE: float = 5.0   # shortened for training speed (nadir captured within 2-3 s)
STEPS_PER_EPISODE: int = 25
N_SUBSTEPS: int = 5
T_WARMUP: float = CONFIG_T_WARMUP


F_NOM: float = _CONTRACT.fn
OMEGA_N: float = 2.0 * np.pi * F_NOM
SBASE: float = 100.0      # MVA

PHI_F: float = 100.0
PHI_H: float = 1.0
PHI_D: float = 1.0
TDS_FAIL_PENALTY: float = -50.0

COMM_ADJ: Dict[int, List[int]] = {0: [1, 3], 1: [0, 2], 2: [1, 3], 3: [2, 0]}
MAX_NEIGHBORS: int = _CONTRACT.max_neighbors
COMM_FAIL_PROB: float = 0.1

NORM_P: float = 2.0
NORM_FREQ: float = 3.0
NORM_ROCOF: float = 5.0

DIST_MIN: float = 1.0
DIST_MAX: float = 3.0

VSG_BUS_VN: float = 20.0  # kV


# ---------------------------------------------------------------------------
# Base Environment
# ---------------------------------------------------------------------------

class _KundurBaseEnv(gym.Env):
    """
    Abstract base for both standalone-ODE and MATLAB/Simulink backends.

    Subclasses must implement:
        ``_reset_backend``, ``_step_backend``, ``_read_measurements``,
        ``_apply_disturbance_backend``, ``_close_backend``.
    """

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        comm_delay_steps: int = 0,
        render_mode: Optional[str] = None,
        training: bool = True,
    ):
        super().__init__()
        self.comm_delay_steps = comm_delay_steps
        self.render_mode = render_mode
        self.training = training

        self.action_space = spaces.Box(
            low=-1.0, high=1.0,
            shape=(N_AGENTS, ACT_DIM), dtype=np.float32,
        )
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf,
            shape=(N_AGENTS, OBS_DIM), dtype=np.float32,
        )

        # Convenience aliases for train.py / sac_agent.py
        self.N_AGENTS = N_AGENTS
        self.N_ESS = N_AGENTS  # NE compatibility alias
        self.OBS_DIM = OBS_DIM
        self.ACT_DIM = ACT_DIM
        self.DT = DT
        self.T_EPISODE = T_EPISODE
        self.DIST_MIN = DIST_MIN
        self.DIST_MAX = DIST_MAX

        # Internal state
        self._step_count: int = 0
        self._sim_time: float = 0.0
        self._omega: np.ndarray = np.ones(N_AGENTS)
        self._omega_prev: np.ndarray = np.ones(N_AGENTS)
        self._P_es: np.ndarray = np.full(N_AGENTS, VSG_P0)
        self._M: np.ndarray = np.full(N_AGENTS, VSG_M0)
        self._D: np.ndarray = np.full(N_AGENTS, VSG_D0)

        # Communication delay buffers
        self._comm_buffer: Dict[Tuple[int, int], Dict[str, list]] = {}
        for i in range(N_AGENTS):
            for nb in COMM_ADJ[i]:
                self._comm_buffer[(i, nb)] = {
                    "omega": [0.0] * (comm_delay_steps + 1),
                    "rocof": [0.0] * (comm_delay_steps + 1),
                }

        # Communication failure mask
        self._comm_mask: np.ndarray = np.ones(
            (N_AGENTS, MAX_NEIGHBORS), dtype=bool
        )

    # ------------------------------------------------------------------
    # Gymnasium interface
    # ------------------------------------------------------------------

    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[dict] = None,
    ) -> Tuple[np.ndarray, dict]:
        super().reset(seed=seed)

        self._step_count = 0
        self._sim_time = 0.0
        self._omega = np.ones(N_AGENTS)
        self._omega_prev = np.ones(N_AGENTS)
        self._P_es = np.full(N_AGENTS, VSG_P0)
        self._M = np.full(N_AGENTS, VSG_M0)
        self._D = np.full(N_AGENTS, VSG_D0)

        if self.training:
            self._comm_mask = (
                self.np_random.random((N_AGENTS, MAX_NEIGHBORS))
                > COMM_FAIL_PROB
            )
        else:
            self._comm_mask = np.ones((N_AGENTS, MAX_NEIGHBORS), dtype=bool)

        for key in self._comm_buffer:
            self._comm_buffer[key]["omega"] = [0.0] * (self.comm_delay_steps + 1)
            self._comm_buffer[key]["rocof"] = [0.0] * (self.comm_delay_steps + 1)

        self._reset_backend(options=options)

        obs = self._build_obs()
        info: Dict[str, Any] = {"sim_time": self._sim_time}
        return obs, info

    def step(
        self, action: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, bool, bool, dict]:
        action = np.clip(np.asarray(action, dtype=np.float32), -1.0, 1.0)

        # Map [-1, 1] -> physical delta values
        delta_M = 0.5 * (action[:, 0] + 1.0) * (DM_MAX - DM_MIN) + DM_MIN
        delta_D = 0.5 * (action[:, 1] + 1.0) * (DD_MAX - DD_MIN) + DD_MIN

        M_target = np.clip(VSG_M0 + delta_M, M_LO, M_HI)
        D_target = np.clip(VSG_D0 + delta_D, D_LO, D_HI)

        sim_ok = True
        try:
            self._step_backend(M_target, D_target)
            self._read_measurements()
        except Exception as exc:
            print(
                f"[KundurEnv] Simulation step failed at t={self._sim_time:.2f}: "
                f"{exc}"
            )
            sim_ok = False

        self._step_count += 1
        self._update_comm_buffers()

        obs = self._build_obs()

        if sim_ok:
            reward, components = self._compute_reward(action)
        else:
            reward = np.full(N_AGENTS, TDS_FAIL_PENALTY, dtype=np.float32)
            components = {"r_f": float(TDS_FAIL_PENALTY), "r_h": 0.0, "r_d": 0.0}

        terminated = not sim_ok
        truncated = self._step_count >= STEPS_PER_EPISODE

        _max_freq_dev = float(np.max(np.abs((self._omega - 1.0) * F_NOM)))
        info: Dict[str, Any] = {
            "sim_time": self._sim_time,
            "omega": self._omega.copy(),
            "M": self._M.copy(),
            "D": self._D.copy(),
            "P_es": self._P_es.copy(),
            "sim_ok": sim_ok,
            "freq_hz": self._omega * F_NOM,
            "max_freq_dev_hz": _max_freq_dev,
            "max_freq_deviation_hz": _max_freq_dev,
            "tds_failed": not sim_ok,
            "reward_components": components,
        }

        return obs, reward, terminated, truncated, info

    # ------------------------------------------------------------------
    # Observation (Sec. III-C)
    # ------------------------------------------------------------------

    def _build_obs(self) -> np.ndarray:
        obs = np.zeros((N_AGENTS, OBS_DIM), dtype=np.float32)

        for i in range(N_AGENTS):
            freq_dev_norm = (self._omega[i] - 1.0) * OMEGA_N / NORM_FREQ
            if self.DT > 0:
                rocof_norm = (
                    (self._omega[i] - self._omega_prev[i])
                    / self.DT * OMEGA_N / NORM_ROCOF
                )
            else:
                rocof_norm = 0.0

            obs[i, 0] = self._P_es[i] / NORM_P
            obs[i, 1] = freq_dev_norm
            obs[i, 2] = rocof_norm

            for n_idx, nb in enumerate(COMM_ADJ[i]):
                if self._comm_mask[i, n_idx]:
                    nb_data = self._get_comm_data(i, nb)
                    obs[i, 3 + n_idx] = nb_data["omega"]
                    obs[i, 5 + n_idx] = nb_data["rocof"]

        return obs

    # ------------------------------------------------------------------
    # Communication helpers
    # ------------------------------------------------------------------

    def _update_comm_buffers(self) -> None:
        for i in range(N_AGENTS):
            for nb in COMM_ADJ[i]:
                freq_dev_norm = (self._omega[nb] - 1.0) * OMEGA_N / NORM_FREQ
                if self.DT > 0:
                    rocof_norm = (
                        (self._omega[nb] - self._omega_prev[nb])
                        / self.DT * OMEGA_N / NORM_ROCOF
                    )
                else:
                    rocof_norm = 0.0

                buf = self._comm_buffer[(i, nb)]
                buf["omega"].append(freq_dev_norm)
                buf["rocof"].append(rocof_norm)
                max_len = self.comm_delay_steps + 2
                if len(buf["omega"]) > max_len:
                    buf["omega"].pop(0)
                    buf["rocof"].pop(0)

    def _get_comm_data(self, agent: int, neighbor: int) -> Dict[str, float]:
        buf = self._comm_buffer[(agent, neighbor)]
        idx = max(0, len(buf["omega"]) - 1 - self.comm_delay_steps)
        return {
            "omega": buf["omega"][idx],
            "rocof": buf["rocof"][idx],
        }

    # ------------------------------------------------------------------
    # Reward (Eq. 15-18)
    # ------------------------------------------------------------------

    def _compute_reward(self, action: np.ndarray) -> Tuple[np.ndarray, Dict[str, float]]:
        """Reward per paper Eq. 14-18 (see docs/decisions/2026-04-10-paper-baseline-contract.md).

        r_f (Eq. 15-16): relative sync penalty — penalises deviation from the
            *local group average* frequency, not deviation from nominal.
            ω̄_i = mean(Δω_i, Δω_{active neighbours})
            r_f_i = -(Δω_i - ω̄_i)² - Σ_j (Δω_j - ω̄_i)² · η_j

        r_h (Eq. 17): -(mean_i ΔH_i)²   where ΔH_i = delta_M_i / 2
        r_d (Eq. 18): -(mean_i ΔD_i)²

        r_i = φ_f · r_f_i + φ_h · r_h + φ_d · r_d
        """
        rewards = np.zeros(N_AGENTS, dtype=np.float32)
        r_f_total = 0.0

        # Recover physical parameter adjustments from normalized actions
        delta_M = 0.5 * (action[:, 0] + 1.0) * (DM_MAX - DM_MIN) + DM_MIN  # p.u.
        delta_D = 0.5 * (action[:, 1] + 1.0) * (DD_MAX - DD_MIN) + DD_MIN  # p.u.

        # Frequency deviations in Hz for all agents
        dw_hz = (self._omega - 1.0) * F_NOM  # shape (N_AGENTS,)

        # r_f (Eq. 15-16): relative sync penalty per agent
        for i in range(N_AGENTS):
            # Local group: agent i + active neighbours (masked by comm_mask)
            group_dw = [dw_hz[i]]
            for n_idx, nb in enumerate(COMM_ADJ[i]):
                if self._comm_mask[i, n_idx]:
                    group_dw.append(dw_hz[nb])
            omega_bar_i = float(np.mean(group_dw))  # local average (Hz)

            # Self term
            r_f_i = -(dw_hz[i] - omega_bar_i) ** 2

            # Neighbour terms weighted by communication success (η_j)
            for n_idx, nb in enumerate(COMM_ADJ[i]):
                eta_j = 1.0 if self._comm_mask[i, n_idx] else 0.0
                r_f_i -= (dw_hz[nb] - omega_bar_i) ** 2 * eta_j

            step_r_f = PHI_F * r_f_i  # r_f_i is already negative
            rewards[i] += step_r_f
            r_f_total += step_r_f

        # r_h (Eq. 17): penalise mean inertia adjustment — (ΔH̄)² = (mean(ΔM/2))²
        delta_H_mean = float(np.mean(delta_M)) / 2.0
        r_h_val = delta_H_mean ** 2
        rewards -= PHI_H * r_h_val

        # r_d (Eq. 18): penalise mean damping adjustment — (ΔD̄)²
        delta_D_mean = float(np.mean(delta_D))
        r_d_val = delta_D_mean ** 2
        rewards -= PHI_D * r_d_val

        components: Dict[str, float] = {
            "r_f": r_f_total / N_AGENTS,
            "r_h": -PHI_H * r_h_val,
            "r_d": -PHI_D * r_d_val,
        }
        return rewards, components

    # ------------------------------------------------------------------
    # Disturbance
    # ------------------------------------------------------------------

    def apply_disturbance(
        self,
        bus_idx: Optional[int] = None,
        magnitude: Optional[float] = None,
    ) -> None:
        if magnitude is None:
            magnitude = float(self.np_random.uniform(DIST_MIN, DIST_MAX))
            if self.np_random.random() > 0.5:
                magnitude = -magnitude
        self._apply_disturbance_backend(bus_idx, magnitude)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._close_backend()
        super().close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Abstract backend hooks
    # ------------------------------------------------------------------

    def _reset_backend(self, options: Optional[dict] = None) -> None:
        raise NotImplementedError

    def _step_backend(
        self, M_target: np.ndarray, D_target: np.ndarray
    ) -> None:
        raise NotImplementedError

    def _read_measurements(self) -> None:
        raise NotImplementedError

    def _apply_disturbance_backend(
        self, bus_idx: Optional[int], magnitude: float
    ) -> None:
        raise NotImplementedError

    def _close_backend(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Standalone ODE Backend
# ---------------------------------------------------------------------------

class KundurStandaloneEnv(_KundurBaseEnv):
    """
    Pure-Python 4-machine swing-equation model with RK4 integration.

    Kundur Two-Area topology (Kron-reduced 4-bus):
        Area 1: Bus 0 -- B=10 -- Bus 1
        Area 2: Bus 2 -- B=10 -- Bus 3
        Tie:    Bus 1 -- B=2  -- Bus 2
    """

    # Kron-reduced susceptance matrix
    _B = np.array([
        [ 10, -10,   0,   0],
        [-10,  12,  -2,   0],
        [  0,  -2,  12, -10],
        [  0,   0, -10,  10],
    ], dtype=np.float64)

    def __init__(
        self,
        comm_delay_steps: int = 0,
        render_mode: Optional[str] = None,
        training: bool = True,
    ):
        super().__init__(
            comm_delay_steps=comm_delay_steps,
            render_mode=render_mode,
            training=training,
        )
        self._delta: np.ndarray = np.zeros(N_AGENTS)
        self._P_mech: np.ndarray = np.full(N_AGENTS, VSG_P0)

        # Load conductance (for power balance at steady state)
        # Total gen on sys base: 4 * 0.5 * 200/100 = 4.0 p.u.
        # Distributed to buses 1 and 2 (load centers)
        self._g_load = np.array([0.0, 2.0, 2.0, 0.0])  # p.u. on Sbase

    # ------------------------------------------------------------------
    # Electrical power
    # ------------------------------------------------------------------

    def _compute_Pe(
        self, delta: np.ndarray
    ) -> np.ndarray:
        """
        P_e_i = sum_j |V_i||V_j|(-B_ij) sin(delta_i - delta_j) + g_load_i * V^2

        Returns P_e on system base (100 MVA).
        Assumes |V| = 1.0 p.u. (classical model).
        """
        V = 1.0
        n = N_AGENTS
        P_e = np.zeros(n)
        for i in range(n):
            for j in range(n):
                if i != j:
                    P_e[i] += (
                        V * V * (-self._B[i, j])
                        * np.sin(delta[i] - delta[j])
                    )
            P_e[i] += self._g_load[i] * V * V
        return P_e

    # ------------------------------------------------------------------
    # RK4 integrator
    # ------------------------------------------------------------------

    def _rk4_step(self, M: np.ndarray, D: np.ndarray, dt: float) -> None:
        """
        Single RK4 step for all swing equations.

        M_i * d(omega_i)/dt = P_mech_i - P_e_i - D_i*(omega_i - 1)
        d(delta_i)/dt       = omega_n * (omega_i - 1)

        All quantities in the swing equation are on VSG base (200 MVA).
        P_mech is stored on VSG base; P_e from _compute_Pe is on system
        base (100 MVA) and must be converted.
        """
        omega = self._omega.copy()
        delta = self._delta.copy()

        def derivs(w, d):
            P_e_sys = self._compute_Pe(d)
            # Convert P_e from system base to VSG base
            P_e_vsg = P_e_sys * (SBASE / VSG_SN)
            d_omega = (self._P_mech - P_e_vsg - D * (w - 1.0)) / M
            d_delta = OMEGA_N * (w - 1.0)
            return d_omega, d_delta, P_e_vsg

        k1 = derivs(omega, delta)
        k2 = derivs(omega + 0.5 * dt * k1[0], delta + 0.5 * dt * k1[1])
        k3 = derivs(omega + 0.5 * dt * k2[0], delta + 0.5 * dt * k2[1])
        k4 = derivs(omega + dt * k3[0], delta + dt * k3[1])

        def combine(y, k1y, k2y, k3y, k4y):
            return y + (dt / 6.0) * (k1y + 2.0 * k2y + 2.0 * k3y + k4y)

        self._omega_prev = self._omega.copy()
        self._omega = np.clip(
            combine(omega, k1[0], k2[0], k3[0], k4[0]), 0.9, 1.1
        )
        self._delta = combine(delta, k1[1], k2[1], k3[1], k4[1])
        self._P_es = k1[2]  # start-of-step P_e on VSG base

    # ------------------------------------------------------------------
    # Backend hooks
    # ------------------------------------------------------------------

    def _reset_backend(self, options: Optional[dict] = None) -> None:
        self._P_mech = np.full(N_AGENTS, VSG_P0)
        self._delta = np.zeros(N_AGENTS)

        # Solve for initial angles (Newton-Raphson power flow)
        P_mech_sys = self._P_mech * (VSG_SN / SBASE)
        delta_all = np.zeros(N_AGENTS)
        ref = 0  # Bus 0 is reference (delta=0)

        converged = False
        for _iter in range(50):
            P_e = self._compute_Pe(delta_all)
            mismatch = np.zeros(N_AGENTS)
            for i in range(N_AGENTS):
                if i != ref:
                    mismatch[i] = P_mech_sys[i] - P_e[i]

            if np.max(np.abs(mismatch)) < 1e-8:
                converged = True
                break

            # Jacobian dP_e/d(delta) (skip reference bus)
            n = N_AGENTS
            idx = [i for i in range(n) if i != ref]
            J = np.zeros((len(idx), len(idx)))
            for ii, i in enumerate(idx):
                for jj, j in enumerate(idx):
                    if i == j:
                        for k in range(n):
                            if k != i:
                                J[ii, ii] += (
                                    -self._B[i, k]
                                    * np.cos(delta_all[i] - delta_all[k])
                                )
                    else:
                        J[ii, jj] = (
                            self._B[i, j]
                            * np.cos(delta_all[i] - delta_all[j])
                        )

            try:
                d_delta = np.linalg.solve(J, mismatch[idx])
                for ii, i in enumerate(idx):
                    delta_all[i] += d_delta[ii]
            except np.linalg.LinAlgError:
                warnings.warn(
                    "[KundurEnv] Power flow Jacobian singular — "
                    "initial angles may be inaccurate."
                )
                break

        if not converged:
            warnings.warn(
                f"[KundurEnv] Power flow did not converge after {_iter + 1} "
                f"iterations (max mismatch: "
                f"{np.max(np.abs(mismatch)):.2e})."
            )

        self._delta = delta_all

    def _step_backend(
        self, M_target: np.ndarray, D_target: np.ndarray
    ) -> None:
        dt_sub = DT / N_SUBSTEPS
        M_start = self._M.copy()
        D_start = self._D.copy()

        for s in range(N_SUBSTEPS):
            alpha = (s + 1) / N_SUBSTEPS
            M_now = M_start + alpha * (M_target - M_start)
            D_now = D_start + alpha * (D_target - D_start)
            self._rk4_step(M_now, D_now, dt_sub)

        self._M = M_target.copy()
        self._D = D_target.copy()
        self._sim_time += DT

    def _read_measurements(self) -> None:
        pass  # computed inline by RK4

    def _apply_disturbance_backend(
        self, bus_idx: Optional[int], magnitude: float
    ) -> None:
        if bus_idx is None:
            bus_idx = int(self.np_random.integers(0, N_AGENTS))
        bus_idx = min(max(bus_idx, 0), N_AGENTS - 1)

        # Convert magnitude from system base to VSG base
        self._P_mech[bus_idx] += magnitude * (SBASE / VSG_SN)
        print(
            f"[Standalone] Disturbance at ES{bus_idx + 1}: "
            f"{magnitude:+.2f} p.u. (sys base)"
        )

    def _close_backend(self) -> None:
        pass


# ---------------------------------------------------------------------------
# MATLAB / Simulink Backend
# ---------------------------------------------------------------------------

class KundurSimulinkEnv(_KundurBaseEnv):
    """
    Gymnasium environment backed by MATLAB/Simulink.

    Delegates simulation to SimulinkBridge which batches all N-agent
    parameter sets and state reads into a single MATLAB IPC call per step.

    Requirements
    ------------
    - MATLAB R2021b+ with Simulink and Simscape Electrical.
    - ``matlab.engine`` Python package.
    - kundur_vsg.slx built by ``build_powerlib_kundur.m``.
    """

    def __init__(
        self,
        model_name: str = "kundur_vsg",
        model_dir: Optional[str] = None,
        comm_delay_steps: int = 0,
        render_mode: Optional[str] = None,
        training: bool = True,
    ):
        super().__init__(
            comm_delay_steps=comm_delay_steps,
            render_mode=render_mode,
            training=training,
        )
        from engine.simulink_bridge import SimulinkBridge

        resolved_dir = model_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', '..', 'scenarios', 'kundur', 'simulink_models'
        )
        cfg = replace(
            KUNDUR_BRIDGE_CONFIG,
            model_name=model_name,
            model_dir=resolved_dir,
        )
        self.bridge = SimulinkBridge(cfg)

    # ------------------------------------------------------------------
    # Backend hooks
    # ------------------------------------------------------------------

    def _reset_backend(self, options: Optional[dict] = None) -> None:
        try:
            self.bridge.load_model()
            self.bridge.reset()
            self._sim_time = 0.0

            # Restore nominal load state: Bus14 load on, Bus15 load off.
            # Disturbance is applied mid-episode via apply_disturbance_load()
            # (no topology change — Dynamic Load PS signal, FastRestart-safe).
            cfg = self.bridge.cfg
            self.bridge.set_disturbance_load(
                cfg.tripload1_p_var, cfg.tripload1_p_default
            )
            self.bridge.set_disturbance_load(
                cfg.tripload2_p_var, cfg.tripload2_p_default
            )

            self.bridge.warmup(T_WARMUP)
            self._sim_time = self.bridge.t_current
        except Exception as exc:
            print(f"[Kundur-Simulink] Reset failed: {exc}")
            raise

    def _step_backend(
        self, M_target: np.ndarray, D_target: np.ndarray
    ) -> None:
        from engine.exceptions import SimulinkError
        try:
            state = self.bridge.step(M_target, D_target)
        except SimulinkError:
            raise
        self._omega_prev = self._omega.copy()
        self._omega = state["omega"]
        self._P_es = state["Pe"]
        self._M = M_target.copy()
        self._D = D_target.copy()
        self._sim_time = self.bridge.t_current

    def _read_measurements(self) -> None:
        # Measurements already read in _step_backend via bridge.step()
        pass

    def _apply_disturbance_backend(
        self, bus_idx: Optional[int], magnitude: float
    ) -> None:
        """Apply load disturbance mid-episode via Dynamic Load PS signal.

        Sets a workspace variable that the Simulink Constant block reads on the
        next FastRestart sim() call.  No topology change — no Simscape re-solve.

        magnitude < 0: load reduction — Bus14 TripLoad1 goes from 248/3 MW → 0
        magnitude > 0: load increase  — Bus15 TripLoad2 goes from 0 → 188/3 MW
        """
        cfg = self.bridge.cfg
        if magnitude < 0:
            # Remove Bus14 load: TripLoad1_P = 0 (3 phases × 0 W = 0 total)
            self.bridge.apply_disturbance_load(cfg.tripload1_p_var, 0.0)
            print(f"[Kundur-Simulink] Load reduction: {cfg.tripload1_p_var}=0 (Bus14 248MW off)")
        else:
            # Add Bus15 load: TripLoad2_P = 188e6/3 W per phase = 188MW total
            self.bridge.apply_disturbance_load(cfg.tripload2_p_var, 188e6 / 3.0)
            print(f"[Kundur-Simulink] Load increase: {cfg.tripload2_p_var}=62.67MW/ph (Bus15 188MW on)")

    def _close_backend(self) -> None:
        self.bridge.close()


# ---------------------------------------------------------------------------
# Backward-compatible aliases
# ---------------------------------------------------------------------------

KundurEnv = KundurSimulinkEnv
