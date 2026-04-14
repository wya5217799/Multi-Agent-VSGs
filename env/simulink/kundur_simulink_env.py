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
from utils.gym_compat import gym, spaces
from env.simulink._base import _SimVsgBase
from scenarios.contract import KUNDUR as _CONTRACT
from scenarios.config_simulink_base import (
    VSG_M0, VSG_D0, VSG_SN,
    DM_MIN, DM_MAX, DD_MIN, DD_MAX,
)
from scenarios.kundur.config_simulink import (
    KUNDUR_BRIDGE_CONFIG,
    T_WARMUP, PHI_F, PHI_H, PHI_D,
    COMM_ADJ, T_EPISODE, N_SUBSTEPS, STEPS_PER_EPISODE,
    NORM_P, NORM_FREQ, NORM_ROCOF,
    DIST_MIN, DIST_MAX,
    TRIPLOAD2_P_MAX_W,
)

warnings.filterwarnings("ignore", category=UserWarning, module="matlab")

# ---------------------------------------------------------------------------
# Constants — imported from scenario config chain, Kundur-specific inlined
# ---------------------------------------------------------------------------

N_AGENTS: int = _CONTRACT.n_agents
OBS_DIM: int = _CONTRACT.obs_dim
ACT_DIM: int = _CONTRACT.act_dim

# Kundur-specific VSG parameters (not in base/scenario config)
VSG_RA: float = 0.003
VSG_XD1: float = 0.30
VSG_P0: float = 0.5       # p.u. on VSG base

# Derived physical limits
M_LO: float = VSG_M0 + DM_MIN
M_HI: float = VSG_M0 + DM_MAX
D_LO: float = VSG_D0 + DD_MIN
D_HI: float = VSG_D0 + DD_MAX

DT: float = _CONTRACT.dt

F_NOM: float = _CONTRACT.fn
OMEGA_N: float = 2.0 * np.pi * F_NOM
SBASE: float = 100.0      # MVA

TDS_FAIL_PENALTY: float = -50.0

MAX_NEIGHBORS: int = _CONTRACT.max_neighbors
COMM_FAIL_PROB: float = 0.1

VSG_BUS_VN: float = 20.0  # kV


def _map_zero_centered_action(
    action_col: np.ndarray,
    delta_min: float,
    delta_max: float,
) -> np.ndarray:
    """Map [-1, 1] to [delta_min, 0, delta_max] while preserving 0 -> 0."""
    action_col = np.asarray(action_col, dtype=np.float32)
    return np.where(
        action_col >= 0.0,
        action_col * delta_max,
        action_col * (-delta_min),
    )


# ---------------------------------------------------------------------------
# Base Environment
# ---------------------------------------------------------------------------

class _KundurBaseEnv(_SimVsgBase):
    """
    Abstract base for both standalone-ODE and MATLAB/Simulink backends.

    Subclasses must implement:
        ``_reset_backend``, ``_step_backend``, ``_read_measurements``,
        ``_apply_disturbance_backend``, ``_close_backend``.
    """

    metadata = {"render_modes": ["human"]}

    # Action encoding: a=0 → delta=0 (zero-centered). Used by _get_zero_action().
    ACTION_ENCODING: str = "zero_centered"

    # ── _SimVsgBase config (Kundur 4-agent 50 Hz) ───────────────────────────
    _N_AGENTS   = N_AGENTS
    _COMM_ADJ   = COMM_ADJ
    _F_NOM      = F_NOM
    _OMEGA_N    = OMEGA_N
    _NORM_P     = NORM_P
    _NORM_FREQ  = NORM_FREQ
    _NORM_ROCOF = NORM_ROCOF
    _PHI_F      = PHI_F
    _PHI_H      = PHI_H
    _PHI_D      = PHI_D
    _DM_MIN     = DM_MIN
    _DM_MAX     = DM_MAX
    _DD_MIN     = DD_MIN
    _DD_MAX     = DD_MAX

    def _decode_action(self, action: np.ndarray):
        """Zero-centered: a=0 → delta=0 (ACTION_ENCODING='zero_centered')."""
        return (
            _map_zero_centered_action(action[:, 0], DM_MIN, DM_MAX),
            _map_zero_centered_action(action[:, 1], DD_MIN, DD_MAX),
        )

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

        # Preserve zero action as the nominal M0/D0 operating point.
        delta_M = _map_zero_centered_action(action[:, 0], DM_MIN, DM_MAX)
        delta_D = _map_zero_centered_action(action[:, 1], DD_MIN, DD_MAX)

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

        # Paper (Yang et al. TPWRS 2023) runs fixed-length episodes (M=50 steps).
        # Episodes only terminate on MATLAB sim() crash.  Frequency deviations are
        # handled by the Simulink integrator saturation (±15 Hz hardware limit) and
        # do not need a Python-level early-termination guard.
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

        magnitude is in system-base p.u. (100 MW per +1.0). The backend keeps
        the paper's sign convention while making the magnitude observable:

        magnitude < 0: reduce Bus14 TripLoad1 by |magnitude| * 100 MW
        magnitude > 0: add    Bus15 TripLoad2 by  magnitude  * 100 MW
        """
        cfg = self.bridge.cfg
        delta_per_phase_w = abs(float(magnitude)) * cfg.sbase_va / 3.0
        if magnitude < 0:
            tripload1_w = max(0.0, cfg.tripload1_p_default - delta_per_phase_w)
            self.bridge.apply_disturbance_load(cfg.tripload1_p_var, tripload1_w)
            total_mw = tripload1_w * 3.0 / 1e6
            print(
                f"[Kundur-Simulink] Load reduction: {cfg.tripload1_p_var}="
                f"{total_mw:.2f}MW total (Bus14 remaining load)"
            )
        else:
            tripload2_w = min(
                TRIPLOAD2_P_MAX_W,
                cfg.tripload2_p_default + delta_per_phase_w,
            )
            self.bridge.apply_disturbance_load(cfg.tripload2_p_var, tripload2_w)
            total_mw = tripload2_w * 3.0 / 1e6
            print(
                f"[Kundur-Simulink] Load increase: {cfg.tripload2_p_var}="
                f"{total_mw:.2f}MW total (Bus15 applied load)"
            )

    def _close_backend(self) -> None:
        self.bridge.close()


# ---------------------------------------------------------------------------
# Backward-compatible aliases
# ---------------------------------------------------------------------------

KundurEnv = KundurSimulinkEnv
