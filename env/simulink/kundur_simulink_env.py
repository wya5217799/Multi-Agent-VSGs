"""
Modified Kundur Two-Area System -- Gymnasium Environment
=========================================================

⚠️ 修改前先读 scenarios/kundur/NOTES.md（已知事实 / 试过没用的 / 当前在修）



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

import logging
import os
import warnings
from dataclasses import replace
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)
from utils.gym_compat import gym, spaces
from env.simulink._base import _SimVsgBase
from scenarios.contract import KUNDUR as _CONTRACT
from scenarios.config_simulink_base import (
    VSG_M0, VSG_D0, VSG_SN,
    DM_MIN, DM_MAX, DD_MIN, DD_MAX,
)
from scenarios.kundur.scenario_loader import (
    Scenario,
    scenario_to_disturbance_type,
)
from scenarios.kundur.config_simulink import (
    KUNDUR_BRIDGE_CONFIG,
    T_WARMUP, PHI_F, PHI_H, PHI_D,
    COMM_ADJ, T_EPISODE, N_SUBSTEPS, STEPS_PER_EPISODE,
    NORM_P, NORM_FREQ, NORM_ROCOF,
    DIST_MIN, DIST_MAX,
    TRIPLOAD2_P_MAX_W,
    VSG_P0_SBASE,
)
from scenarios.kundur.workspace_vars import (
    PROFILES_CVS,
    PROFILES_CVS_V3,
    resolve as _ws_resolve,
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
OMEGA_SAT_DETECT_HZ: float = 13.5  # detect within 1.5 Hz of IntW clip (±15 Hz @ 50 Hz)

# Rate limits for M/D parameter transitions (per DT=0.2s step).
# Prevents abrupt jumps that excite the Kundur 0.5 Hz inter-area mode.
# Full-range traversal takes ~10 steps (2 seconds), longer than one inter-area cycle.
# Physics: random white-noise M/D changes at 5 Hz (1/DT) excite the 0.5 Hz mode
# and cause IntW saturation even before any disturbance is applied.
DELTA_M_MAX_PER_STEP: float = 2.4  # pu/step  (DM range=24, full range in ~10 steps)
DELTA_D_MAX_PER_STEP: float = 0.6  # pu/step  (DD range=6,  full range in ~10 steps)

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
        self._P_es: np.ndarray = VSG_P0_SBASE.copy()  # system-base pu, shape (N_AGENTS,)
        self._M: np.ndarray = np.full(N_AGENTS, VSG_M0)
        self._D: np.ndarray = np.full(N_AGENTS, VSG_D0)

        # C4 (2026-04-29): per-episode disturbance state. See
        # docs/superpowers/plans/2026-04-29-c4-scenario-vo-design.md.
        # Default: trigger DISARMED (legacy probe path drives via
        # apply_disturbance(...)). reset(scenario=...) or
        # reset(options={'disturbance_magnitude': ...}) ARMS the trigger.
        self._episode_scenario: Optional[Scenario] = None
        self._episode_magnitude: Optional[float] = None
        self._trigger_at_step: int = int(0.5 / DT) if DT > 0 else 0
        self._disturbance_triggered: bool = True
        # §1.5b: resolved disturbance_type recorded per episode for audit.
        # Set at reset(); exposed via info dict in step().
        self._episode_resolved_disturbance_type: Optional[str] = None

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
        *,
        scenario: Optional[Scenario] = None,
    ) -> Tuple[np.ndarray, dict]:
        """Reset env with optional Scenario VO and/or options dict.

        Disturbance source priority (C4):
          1. ``scenario`` — typed Scenario; resolves to
             ``_disturbance_type`` via
             ``scenarios.kundur.scenario_loader.scenario_to_disturbance_type``;
             magnitude from ``scenario.magnitude_sys_pu``.
          2. ``options['disturbance_magnitude']`` — magnitude only;
             ``_disturbance_type`` stays at constructor / env-var default.
          3. Neither — internal trigger DISARMED; legacy
             ``apply_disturbance(...)`` drives dispatch (probes).

        ``options`` may also carry:
          - ``trigger_at_step`` (int): step index at which the trigger
            fires; default ``int(0.5/DT)`` (= 2 for DT=0.2s). paper_eval
            uses 0 for immediate post-warmup dispatch.
        """
        super().reset(seed=seed)

        self._step_count = 0
        self._sim_time = 0.0
        self._omega = np.ones(N_AGENTS)
        self._omega_prev = np.ones(N_AGENTS)
        self._P_es = VSG_P0_SBASE.copy()  # system-base pu, shape (N_AGENTS,)
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

        # ---- C4 disturbance resolution (§1.5b: record resolved type) ----
        opts = options or {}
        self._trigger_at_step = int(
            opts.get("trigger_at_step", int(0.5 / DT) if DT > 0 else 0)
        )
        self._episode_scenario = None
        self._episode_magnitude = None
        self._episode_resolved_disturbance_type = None

        if scenario is not None:
            self._episode_scenario = scenario
            self._episode_resolved_disturbance_type = (
                scenario_to_disturbance_type(scenario)
            )
            # Update _disturbance_type so the protocol layer reads the
            # resolved string at trigger time. (Legacy attribute kept as
            # regular instance var per P3 design §1.5c.)
            if hasattr(self, "_disturbance_type"):
                self._disturbance_type = (
                    self._episode_resolved_disturbance_type
                )
            self._episode_magnitude = float(scenario.magnitude_sys_pu)
            self._disturbance_triggered = False
        elif "disturbance_magnitude" in opts:
            # Magnitude-only path: type stays at constructor default.
            self._episode_resolved_disturbance_type = getattr(
                self, "_disturbance_type", None
            )
            self._episode_magnitude = float(opts["disturbance_magnitude"])
            self._disturbance_triggered = False
        else:
            # Legacy / probe path: internal trigger disarmed.
            self._disturbance_triggered = True

        self._reset_backend(options=options)

        obs = self._build_obs()
        info: Dict[str, Any] = {
            "sim_time": self._sim_time,
            "resolved_disturbance_type":
                self._episode_resolved_disturbance_type,
            "episode_magnitude_sys_pu": self._episode_magnitude,
        }
        return obs, info

    def step(
        self, action: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, bool, bool, dict]:
        action = np.clip(np.asarray(action, dtype=np.float32), -1.0, 1.0)

        # C4 internal disturbance trigger: fires once at step ==
        # _trigger_at_step (set by reset()). Default = int(0.5/DT) = 2
        # (matches legacy train-loop timing). Skipped when
        # _disturbance_triggered is already True (probe legacy path or
        # apply_disturbance(...) was already called).
        if (
            not self._disturbance_triggered
            and self._step_count == self._trigger_at_step
            and self._episode_magnitude is not None
        ):
            self._apply_disturbance_backend(
                bus_idx=None,
                magnitude=float(self._episode_magnitude),
            )
            self._disturbance_triggered = True

        # Preserve zero action as the nominal M0/D0 operating point.
        delta_M = _map_zero_centered_action(action[:, 0], DM_MIN, DM_MAX)
        delta_D = _map_zero_centered_action(action[:, 1], DD_MIN, DD_MAX)

        M_target = np.clip(VSG_M0 + delta_M, M_LO, M_HI)
        D_target = np.clip(VSG_D0 + delta_D, D_LO, D_HI)

        # Rate-limit M/D transitions: prevent abrupt per-step jumps that excite
        # the Kundur two-area 0.5 Hz inter-area mode (opt_kd_20260417_04).
        M_target = np.clip(M_target, self._M - DELTA_M_MAX_PER_STEP,
                           self._M + DELTA_M_MAX_PER_STEP)
        D_target = np.clip(D_target, self._D - DELTA_D_MAX_PER_STEP,
                           self._D + DELTA_D_MAX_PER_STEP)

        sim_ok = True
        try:
            self._step_backend(M_target, D_target)
            self._read_measurements()
        except Exception:
            # logger.exception captures the full traceback so dev errors
            # (AttributeError, NameError) surface in logs instead of being
            # silently absorbed by sim_ok=False -> tds_failed reward.
            logger.exception(
                "[KundurEnv] Simulation step failed at t=%.2f", self._sim_time
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
        _omega_saturated = _max_freq_dev >= OMEGA_SAT_DETECT_HZ
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
            "omega_saturated": _omega_saturated,
            "hit_freq_clip": _omega_saturated,
            "reward_components": components,
            # §1.5b: resolved per-episode disturbance state for audit.
            "resolved_disturbance_type":
                self._episode_resolved_disturbance_type,
            "episode_magnitude_sys_pu": self._episode_magnitude,
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
        """Legacy disturbance entry — deprecated (C4, 2026-04-29).

        Prefer ``env.reset(scenario=Scenario(...))`` or
        ``env.reset(options={'disturbance_magnitude': mag})``. External
        callers (probes / scripts / tests) continue to work; calls
        bypass the internal step==trigger_at_step trigger and dispatch
        immediately to the disturbance protocol layer.
        """
        warnings.warn(
            "env.apply_disturbance() is deprecated; pass a Scenario via "
            "env.reset(scenario=...) or magnitude via "
            "env.reset(options={'disturbance_magnitude': ...}). "
            "External calls bypass the internal step trigger.",
            DeprecationWarning,
            stacklevel=2,
        )
        if magnitude is None:
            magnitude = float(self.np_random.uniform(DIST_MIN, DIST_MAX))
            if self.np_random.random() > 0.5:
                magnitude = -magnitude
        self._apply_disturbance_backend(bus_idx, magnitude)
        # Mark triggered so internal trigger doesn't double-fire if a
        # caller mixes new + legacy patterns in the same episode.
        self._disturbance_triggered = True

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
        # TODO(2026-04-18 Kundur Pe contract fix): _P_mech=0.5 is VSG-base pu,
        # inconsistent with SimulinkEnv path which uses VSG_P0_SBASE. ODE backend
        # not in scope for this fix. Track in scenarios/kundur/NOTES.md.
        self._P_mech: np.ndarray = np.full(N_AGENTS, 0.5)

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
        # TODO(2026-04-18 Kundur Pe contract fix): _P_mech=0.5 is VSG-base pu,
        # inconsistent with SimulinkEnv path which uses VSG_P0_SBASE. ODE backend
        # not in scope for this fix. Track in scenarios/kundur/NOTES.md.
        self._P_mech = np.full(N_AGENTS, 0.5)
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
        logger.info(
            "[Standalone] Disturbance at ES%d: %+.2f p.u. (sys base)",
            bus_idx + 1, magnitude,
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
        model_name: Optional[str] = None,
        model_dir: Optional[str] = None,
        comm_delay_steps: int = 0,
        render_mode: Optional[str] = None,
        training: bool = True,
        model_profile_path: Optional[str] = None,
        disturbance_type: Optional[str] = None,
        t_warmup_s: Optional[float] = None,
        fast_restart: Optional[bool] = None,
    ):
        """``t_warmup_s`` overrides the module-level ``T_WARMUP`` for this
        env instance only — useful for probe / smoke contexts that don't
        need the production 10 s reward-shaping settle (Phase 1.3a/1.3b
        motivation, Z 2026-05-03). ``None`` = use ``T_WARMUP`` default.

        ``fast_restart`` override (None = use BridgeConfig default, currently
        False). Validated for v3 Discrete only (probe microtest 2026-05-03,
        physics rel err 2.46e-08). Not safe for v3 Phasor or production
        training without separate validation.
        """
        from scenarios.kundur.config_simulink import (
            DEFAULT_KUNDUR_MODEL_PROFILE,
            KUNDUR_DISTURBANCE_TYPE,
            KUNDUR_DISTURBANCE_TYPES_VALID,
        )
        from scenarios.kundur.model_profile import load_kundur_model_profile
        selected_path = model_profile_path or os.getenv(
            "KUNDUR_MODEL_PROFILE",
            str(DEFAULT_KUNDUR_MODEL_PROFILE),
        )
        self._runtime_profile = load_kundur_model_profile(selected_path)

        # Task 2 hard guard (2026-04-27 freeze blockers): if user explicitly
        # passes model_name, it MUST agree with the resolved profile's
        # model_name. Refuse to silently fall back to v2 when v3 was
        # requested (or vice versa). Catches the failure mode where
        # KUNDUR_MODEL_PROFILE env-var is unset (defaults to v2 .json) but
        # caller passes model_name='kundur_cvs_v3' expecting v3 behavior —
        # without this guard, the BridgeConfig would silently load v2 IC.
        if (
            model_name is not None
            and model_name != self._runtime_profile.model_name
        ):
            raise ValueError(
                f"model_name override {model_name!r} conflicts with "
                f"resolved profile {self._runtime_profile.model_name!r} "
                f"(loaded from {selected_path!r}). To select a different "
                f"model use KUNDUR_MODEL_PROFILE env-var or the "
                f"model_profile_path= constructor arg; do NOT override "
                f"model_name independently — it would desync the IC."
            )

        # CVS profile filename guard: catches a hand-edited or renamed profile
        # JSON whose model_name does not match its file basename (e.g. a JSON
        # claiming model_name='kundur_cvs_v3' but actually holding v2 IC
        # contents). One rule for every CVS profile, including v3 Discrete
        # (Z 2026-05-03): basename must contain the model_name.
        if self._runtime_profile.model_name in PROFILES_CVS:
            expected_basename_token = self._runtime_profile.model_name
            if expected_basename_token not in os.path.basename(str(selected_path)):
                raise ValueError(
                    f"profile model_name={expected_basename_token!r} but "
                    f"profile JSON path {selected_path!r} basename does not "
                    f"contain that token. Refusing to launch with a "
                    f"non-canonical profile file (silent IC fallback risk)."
                )

        # Phase 4 Gap 1 Path (C): resolve disturbance_type from explicit
        # constructor arg, env-var-driven config default, or legacy fallback.
        # Class attribute DISTURBANCE_VSG_INDICES still honored for legacy
        # `pm_step_single_vsg` (preserves existing training behavior).
        resolved_dtype = disturbance_type or KUNDUR_DISTURBANCE_TYPE
        if resolved_dtype not in KUNDUR_DISTURBANCE_TYPES_VALID:
            raise ValueError(
                f"disturbance_type={resolved_dtype!r} not in "
                f"{KUNDUR_DISTURBANCE_TYPES_VALID}"
            )
        self._disturbance_type = resolved_dtype

        super().__init__(
            comm_delay_steps=comm_delay_steps,
            render_mode=render_mode,
            training=training,
        )
        from engine.simulink_bridge import SimulinkBridge
        from scenarios.kundur.config_simulink import make_bridge_config

        resolved_dir = model_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', '..', 'scenarios', 'kundur', 'simulink_models'
        )
        # C2 fix: build BridgeConfig from the runtime profile end-to-end via
        # the factory, so pe0_default_vsg / delta0_deg / step_strategy /
        # m_var_template / m0_default all match the active profile. Avoids
        # the old `replace(KUNDUR_BRIDGE_CONFIG, ...)` footgun where only
        # model_name/model_dir got patched while every other field stayed
        # frozen from the import-time KUNDUR_MODEL_PROFILE env-var.
        # model_name is now guaranteed to equal self._runtime_profile.model_name
        # (or be None); guard above blocks any divergence. No replace() needed.
        cfg = make_bridge_config(self._runtime_profile, model_dir=resolved_dir)
        if fast_restart is not None:
            cfg = replace(cfg, fast_restart=bool(fast_restart))
        self.bridge = SimulinkBridge(cfg)
        # Warmup duration: per-instance override (e.g. probe contexts) or
        # module-level T_WARMUP. Stored on env instance to avoid env-var
        # leakage into other code paths.
        self._t_warmup_s = (
            float(t_warmup_s) if t_warmup_s is not None else float(T_WARMUP)
        )

    # ------------------------------------------------------------------
    # Backend hooks
    # ------------------------------------------------------------------

    def _ws(self, key: str, **idx: Any) -> str:
        """Resolve a Kundur CVS workspace var name via the typed schema.

        Thin wrapper around ``scenarios.kundur.workspace_vars.resolve``;
        fixes ``profile`` to the active model_name and ``n_agents`` to the
        bridge config. Raises ``WorkspaceVarError`` on profile/index mismatch
        — this is the only intended raise path from this method, so callers
        do not need to handle it.
        """
        cfg = self.bridge.cfg
        return _ws_resolve(
            key, profile=cfg.model_name, n_agents=cfg.n_agents, **idx
        )

    def _reset_backend(self, options: Optional[dict] = None) -> None:
        try:
            self.bridge.load_model()
            self.bridge.reset()
            self._sim_time = 0.0

            # Restore nominal load state: Bus14 load on, Bus15 load off.
            # Disturbance is applied mid-episode via apply_disturbance_load()
            # (no topology change — Dynamic Load PS signal, FastRestart-safe).
            #
            # Task 3 (2026-04-27 freeze blockers): v3 build_kundur_cvs_v3.m
            # has no Three-Phase Dynamic Load block consuming TripLoad1_P /
            # TripLoad2_P (LoadStep R-only branches hardcode Resistance='1e9'
            # — Phase 4.0 audit §R2-Blocker1). Skip the writes under v3 to
            # avoid silent dead workspace assignments. v2 (kundur_cvs) and
            # legacy SPS paths unchanged.
            #
            # Z (2026-05-03): v3 Discrete also bypasses the tripload path —
            # it uses Three-Phase Breaker + RLC Load reading LoadStep_amp_bus*
            # directly (workspace var, no Dynamic Load block). Same restore
            # logic as v3 Phasor. LOAD_STEP_TRIP_AMP is now name-valid in
            # v3 Discrete (schema updated 2026-05-03); LoadStepRBranch writes
            # use require_effective=False (state-reset semantics).
            cfg = self.bridge.cfg
            if cfg.model_name not in PROFILES_CVS_V3:
                self.bridge.set_disturbance_load(
                    cfg.tripload1_p_var, cfg.tripload1_p_default
                )
                self.bridge.set_disturbance_load(
                    cfg.tripload2_p_var, cfg.tripload2_p_default
                )
            else:
                # v3 LoadStep IC restoration (2026-04-29 fix to paper_eval
                # weak-signal observation): build_kundur_cvs_v3.m defaults
                # have Bus 14 LS1 pre-engaged at 248e6 W (paper line 993)
                # and Bus 15 LS2 = 0 (paper line 994). After
                # apply_disturbance_backend writes mid-episode (e.g. LS1
                # trip writes LoadStep_amp_bus14=0), those workspace vars
                # PERSIST across env.reset() under FastRestart — the next
                # episode's apply_disturbance_backend may write 0 again
                # (if random pick is LS1 trip), producing zero transient
                # because the var was already 0. Restoring the IC every
                # reset ensures every episode starts from the paper-IC
                # condition: Bus 14 carries 248 MW, Bus 15 is open.
                # Also zeros the Phase A++ CCS trip injection amps so a
                # prior cc_inject dispatch does not leak (skipped in
                # v3 Discrete where CCS blocks don't exist).
                self.bridge.apply_workspace_var(
                    self._ws('LOAD_STEP_AMP', bus=14), 248e6
                )
                self.bridge.apply_workspace_var(
                    self._ws('LOAD_STEP_AMP', bus=15), 0.0
                )
                # LOAD_STEP_T: reset breaker SwitchTimes to far-future so
                # warmup (0..t_warmup_s) does not accidentally fire the
                # breaker. The adapter (LoadStepRBranch.apply) writes a
                # within-window time (t_now+0.1) after warmup completes.
                # Without this reset a prior episode's trigger_t could be
                # smaller than t_warmup_s on the next reset, causing warmup
                # to fire the breaker with IC-state amp values (the bug
                # diagnosed 2026-05-03). 100.0 s is well beyond any
                # reasonable sim window. require_effective omitted — _ws()
                # uses name-validity only (default).
                self.bridge.apply_workspace_var(
                    self._ws('LOAD_STEP_T', bus=14), 100.0
                )
                self.bridge.apply_workspace_var(
                    self._ws('LOAD_STEP_T', bus=15), 100.0
                )
                # CCS trip injection vars: name-valid in both v3 profiles.
                # v3 Phasor: CCS Constant block reads it (name-valid, not
                # effective due to ~0.01 Hz ESS-terminal signal).
                # v3 Discrete: CCS blocks wrapped in `if false` (Phase 1.5
                # to restore); write lands in dangling base-ws, no consumer.
                # Both cases: write 0.0 as state-reset (no require_effective
                # needed). Guard uses schema membership to stay profile-agnostic.
                from scenarios.kundur.workspace_vars import (
                    _SCHEMA as _WS_SCHEMA,
                )
                if cfg.model_name in _WS_SCHEMA['LOAD_STEP_TRIP_AMP'].profiles:
                    self.bridge.apply_workspace_var(
                        self._ws('LOAD_STEP_TRIP_AMP', bus=14), 0.0
                    )
                    self.bridge.apply_workspace_var(
                        self._ws('LOAD_STEP_TRIP_AMP', bus=15), 0.0
                    )

            self.bridge.warmup(self._t_warmup_s)
            self._sim_time = self.bridge.t_current
        except Exception:
            logger.exception("[Kundur-Simulink] Reset failed")
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
        """Apply load disturbance mid-episode.

        CVS profiles (``kundur_cvs`` / ``kundur_cvs_v3``) delegate to the
        :mod:`scenarios.kundur.disturbance_protocols` adapter layer
        (P2 of the algorithm-layer refactor, 2026-04-29). Adapter
        selection is keyed by ``self._disturbance_type``; legacy
        ``pm_step_single_vsg`` honors the class-level
        ``DISTURBANCE_VSG_INDICES`` attribute.

        SPS legacy (``kundur_vsg_sps``) keeps the inline dispatch via
        :class:`engine.simulink_bridge.SimulinkBridge.apply_disturbance_load`.
        ``magnitude`` is in system-base p.u. (100 MW per +1.0); the
        SPS path treats negative magnitudes as Bus14 reduction and
        positive as Bus15 addition.
        """
        cfg = self.bridge.cfg
        if cfg.model_name in PROFILES_CVS:
            from scenarios.kundur.disturbance_protocols import (
                resolve_disturbance,
            )
            protocol = resolve_disturbance(
                getattr(self, '_disturbance_type', 'pm_step_single_vsg'),
                vsg_indices=getattr(self, 'DISTURBANCE_VSG_INDICES', None),
            )
            protocol.apply(
                bridge=self.bridge,
                magnitude_sys_pu=float(magnitude),
                rng=self.np_random,
                t_now=float(self.bridge.t_current),
                cfg=cfg,
            )
            return
        # SPS legacy fall-through (kundur_vsg_sps profile only).
        # CVS profiles already returned above via the protocol layer.

        delta_per_phase_w = abs(float(magnitude)) * cfg.sbase_va / 3.0
        if magnitude < 0:
            tripload1_w = max(0.0, cfg.tripload1_p_default - delta_per_phase_w)
            self.bridge.apply_disturbance_load(cfg.tripload1_p_var, tripload1_w)
            total_mw = tripload1_w * 3.0 / 1e6
            logger.info(
                "[Kundur-Simulink] Load reduction: %s=%.2fMW total "
                "(Bus14 remaining load)",
                cfg.tripload1_p_var, total_mw,
            )
        else:
            tripload2_w = min(
                TRIPLOAD2_P_MAX_W,
                cfg.tripload2_p_default + delta_per_phase_w,
            )
            self.bridge.apply_disturbance_load(cfg.tripload2_p_var, tripload2_w)
            total_mw = tripload2_w * 3.0 / 1e6
            logger.info(
                "[Kundur-Simulink] Load increase: %s=%.2fMW total "
                "(Bus15 applied load)",
                cfg.tripload2_p_var, total_mw,
            )

    def _close_backend(self) -> None:
        self.bridge.close()


# ---------------------------------------------------------------------------
# Backward-compatible aliases
# ---------------------------------------------------------------------------

KundurEnv = KundurSimulinkEnv
