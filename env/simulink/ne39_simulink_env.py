"""
Modified New England 39-Bus System -- Gymnasium Environment
===========================================================

Implements the Multi-Agent VSG (Virtual Synchronous Generator) control
framework for the IEEE 39-bus (New England) test system with 8 wind-farm
buses replaced by PMSG wind turbines and 8 co-located ESS units operating
under VSG control.

Two simulation backends are provided:

1. **Standalone ODE mode** (``NE39BusStandaloneEnv``):
   Pure-Python multi-machine swing-equation model with RK4 integration.
   No external dependencies beyond NumPy.  Suitable for fast prototyping
   and large-scale RL training.

2. **MATLAB/Simulink mode** (``NE39BusSimulinkEnv``):
   Interfaces with NE39bus_v2.slx via ``matlab.engine``.  Sets VSG
   parameters (M, D) through ``set_param``, reads omega / P_e from the
   MATLAB workspace, and supports sub-step parameter interpolation.

Both environments expose the same Gymnasium ``(obs, reward, terminated,
truncated, info)`` API and are fully interchangeable from the perspective
of the training loop.

Reference
---------
Multi-Agent VSGs project -- ``base_env.py`` and ``andes_ne_env.py``.
"""

from __future__ import annotations

import os
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from utils.gym_compat import gym, spaces

warnings.filterwarnings("ignore", category=UserWarning, module="matlab")

from scenarios.contract import NE39 as _CONTRACT
from scenarios.config_simulink_base import (
    VSG_M0, VSG_D0, VSG_SN,
    DM_MIN, DM_MAX, DD_MIN, DD_MAX,
)
from scenarios.new_england.config_simulink import (
    PHI_F, PHI_H, PHI_D,
    COMM_ADJ, T_EPISODE, N_SUBSTEPS, STEPS_PER_EPISODE,
    T_WARMUP,
)

# ---------------------------------------------------------------------------
# Constants — imported from scenario config chain, NE39-specific inlined
# ---------------------------------------------------------------------------

# Number of ESS agents
N_ESS: int = _CONTRACT.n_agents

# Observation / action dimensions
OBS_DIM: int = _CONTRACT.obs_dim   # [P_norm, freq_dev, rocof, nb1_freq, nb2_freq, nb1_rocof, nb2_rocof]
ACT_DIM: int = _CONTRACT.act_dim   # [delta_M, delta_D]

# NE39-specific VSG parameters (not in base/scenario config)
VSG_RA: float = 0.001     # armature resistance (p.u.)
VSG_XD1: float = 0.15     # transient reactance (p.u.)

# Derived physical limits
M_LO: float = VSG_M0 + DM_MIN   # 6.0
M_HI: float = VSG_M0 + DM_MAX   # 30.0
D_LO: float = VSG_D0 + DD_MIN   # 1.5
D_HI: float = VSG_D0 + DD_MAX   # 7.5

# New ESS connecting line parameters (p.u.)
NEW_LINE_R: float = 0.001
NEW_LINE_X: float = 0.10
NEW_LINE_B: float = 0.0175

# Bus voltage
VSG_BUS_VN: float = 22.0  # kV

# Simulation timing
DT: float = _CONTRACT.dt  # control time-step (s)

# System frequency
F_NOM: float = _CONTRACT.fn
OMEGA_N: float = 2.0 * np.pi * F_NOM  # rad/s

TDS_FAIL_PENALTY: float = -50.0

# Omega-based early-termination guard.
# If any VSG's per-unit frequency deviates beyond this threshold the system
# has transient-instability; continuing the episode wastes Simulink compute
# and fills the buffer with useless diverged experience.
# 15 Hz / 60 Hz = 0.25 pu
# Set to 15 Hz (rather than the original 10 Hz) to allow the early-training
# random-exploration episodes to run longer and collect more diverse
# experience before pole-slip; 10 Hz was causing near-immediate termination
# every episode during buffer warm-up.
OMEGA_TERM_THRESHOLD: float = 15.0 / F_NOM   # 0.25 pu
OMEGA_TERM_PENALTY: float = -500.0            # per agent, lump-sum terminal reward

MAX_NEIGHBORS: int = _CONTRACT.max_neighbors
COMM_FAIL_PROB: float = 0.1

# Observation normalisation (from base_env.py)
NORM_P: float = 2.0               # P / 2.0
NORM_FREQ: float = 3.0            # freq_dev * omega_n / 3.0
NORM_ROCOF: float = 5.0           # rocof * omega_n / 5.0

# Disturbance range (p.u.)
DIST_MIN: float = 1.0
DIST_MAX: float = 3.0

# Wind-farm / PV interface defaults (from andes_ne_env.py)
WIND_FARM_M: float = 0.1
WIND_FARM_D: float = 0.0
WIND_FARM_GOV_R: float = 999.0
PV_P0: float = 0.5
PV_Q0: float = 0.0
PV_PMAX: float = 5.0
PV_PMIN: float = 0.0
PV_QMAX: float = 5.0
PV_QMIN: float = -5.0
PV_V0: float = 1.0

# PQ load mode (constant-power)
PQ_P2P: float = 1.0
PQ_P2Z: float = 0.0
PQ_Q2Q: float = 1.0
PQ_Q2Z: float = 0.0

# Bus mapping (andes_ne_env.py):
#   Wind farms replace G1-G8 on buses 30-37
#   ESS on new buses 40-47, parent buses 30-37
WIND_BUSES: List[int] = list(range(30, 38))     # [30..37]
ESS_BUSES: List[int] = list(range(40, 48))       # [40..47]
PARENT_MAP: Dict[int, int] = {40 + i: 30 + i for i in range(N_ESS)}

# Retained synchronous generators
SYNC_BUS_G9: int = 38
SYNC_BUS_G10: int = 39
SYNC_H: np.ndarray = np.array([3.45, 50.0])      # H values for G9, G10
SYNC_D: np.ndarray = np.array([0.0, 0.0])


# ---------------------------------------------------------------------------
# Base Environment
# ---------------------------------------------------------------------------

class _NE39BaseEnv(gym.Env):
    """
    Abstract base for both standalone-ODE and MATLAB/Simulink backends.

    Defines the Gymnasium interface, observation construction, communication
    topology with optional link failures and delays, and the paper's reward
    function (Eq. 15-18).

    Subclasses must implement:
        ``_init_backend``, ``_reset_backend``, ``_step_backend``,
        ``_read_measurements``, ``_apply_disturbance_backend``,
        ``_gen_trip_backend``, ``_close_backend``.
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

        # Action space: N_ESS agents x 2 actions, normalised to [-1, 1]
        self.action_space = spaces.Box(
            low=-1.0,
            high=1.0,
            shape=(N_ESS, ACT_DIM),
            dtype=np.float32,
        )

        # Observation space: N_ESS agents x OBS_DIM features
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(N_ESS, OBS_DIM),
            dtype=np.float32,
        )

        # Convenience aliases expected by train.py / sac_agent.py
        self.N_ESS = N_ESS
        self.OBS_DIM = OBS_DIM
        self.ACT_DIM = ACT_DIM
        self.DT = DT
        self.T_EPISODE = T_EPISODE
        self.DIST_MIN = DIST_MIN
        self.DIST_MAX = DIST_MAX

        # Internal state
        self._step_count: int = 0
        self._sim_time: float = 0.0
        self._omega: np.ndarray = np.ones(N_ESS)
        self._omega_prev: np.ndarray = np.ones(N_ESS)
        self._P_es: np.ndarray = np.zeros(N_ESS)
        self._M: np.ndarray = np.full(N_ESS, VSG_M0)
        self._D: np.ndarray = np.full(N_ESS, VSG_D0)

        # Communication delay buffers: (agent, neighbor) -> deques
        self._comm_buffer: Dict[Tuple[int, int], Dict[str, list]] = {}
        for i in range(N_ESS):
            for nb in COMM_ADJ[i]:
                self._comm_buffer[(i, nb)] = {
                    "omega": [0.0] * (comm_delay_steps + 1),
                    "rocof": [0.0] * (comm_delay_steps + 1),
                }

        # Communication failure mask (refreshed each episode)
        self._comm_mask: np.ndarray = np.ones(
            (N_ESS, MAX_NEIGHBORS), dtype=bool
        )

    # ------------------------------------------------------------------
    # Gymnasium interface
    # ------------------------------------------------------------------

    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[dict] = None,
    ) -> Tuple[np.ndarray, dict]:
        """Reset the environment for a new episode."""
        super().reset(seed=seed)

        self._step_count = 0
        self._sim_time = 0.0
        self._omega = np.ones(N_ESS)
        self._omega_prev = np.ones(N_ESS)
        self._P_es = np.full(N_ESS, PV_P0)
        self._M = np.full(N_ESS, VSG_M0)
        self._D = np.full(N_ESS, VSG_D0)

        # Randomise communication failures during training
        if self.training:
            self._comm_mask = (
                self.np_random.random((N_ESS, MAX_NEIGHBORS))
                > COMM_FAIL_PROB
            )
        else:
            self._comm_mask = np.ones((N_ESS, MAX_NEIGHBORS), dtype=bool)

        # Reset delay buffers
        for key in self._comm_buffer:
            self._comm_buffer[key]["omega"] = [0.0] * (self.comm_delay_steps + 1)
            self._comm_buffer[key]["rocof"] = [0.0] * (self.comm_delay_steps + 1)

        # Backend-specific reset
        self._reset_backend()

        obs = self._build_obs()
        info: Dict[str, Any] = {"sim_time": self._sim_time}
        return obs, info

    def step(
        self, action: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, bool, bool, dict]:
        """
        Execute one control step.

        Parameters
        ----------
        action : ndarray, shape (N_ESS, 2)
            Normalised actions in [-1, 1].
            ``action[:, 0]`` -> inertia adjustment (delta_M).
            ``action[:, 1]`` -> damping adjustment (delta_D).

        Returns
        -------
        obs : ndarray, shape (N_ESS, OBS_DIM)
        reward : ndarray, shape (N_ESS,)
        terminated : bool
        truncated : bool
        info : dict
        """
        action = np.clip(np.asarray(action, dtype=np.float32), -1.0, 1.0)

        # Map [-1, 1] -> physical delta values
        delta_M = 0.5 * (action[:, 0] + 1.0) * (DM_MAX - DM_MIN) + DM_MIN
        delta_D = 0.5 * (action[:, 1] + 1.0) * (DD_MAX - DD_MIN) + DD_MIN

        # Target parameter values (clipped to physical bounds)
        M_target = np.clip(VSG_M0 + delta_M, M_LO, M_HI)
        D_target = np.clip(VSG_D0 + delta_D, D_LO, D_HI)

        # Advance the backend with sub-step interpolation
        sim_ok = True
        try:
            self._step_backend(M_target, D_target)
            self._read_measurements()
        except Exception as exc:
            print(
                f"[NE39Bus] Simulation step failed at t={self._sim_time:.2f}: "
                f"{exc}"
            )
            sim_ok = False

        self._step_count += 1

        # Update communication delay buffers
        self._update_comm_buffers()

        # Observation
        obs = self._build_obs()

        # Omega instability guard: if any VSG deviates beyond threshold, the
        # system has entered transient instability.  Terminate immediately so we
        # don't waste Simulink compute on diverged trajectories and avoid
        # polluting the replay buffer with useless post-instability experience.
        omega_unstable = sim_ok and bool(
            np.any(np.abs(self._omega - 1.0) > OMEGA_TERM_THRESHOLD)
        )

        # Reward
        if omega_unstable:
            reward = np.full(N_ESS, OMEGA_TERM_PENALTY, dtype=np.float32)
            components = {"r_f": float(OMEGA_TERM_PENALTY), "r_h": 0.0, "r_d": 0.0}
        elif sim_ok:
            reward, components = self._compute_reward(action)
        else:
            reward = np.full(N_ESS, TDS_FAIL_PENALTY, dtype=np.float32)
            components = {"r_f": float(TDS_FAIL_PENALTY), "r_h": 0.0, "r_d": 0.0}

        terminated = (not sim_ok) or omega_unstable
        truncated = self._step_count >= STEPS_PER_EPISODE

        _max_freq_dev = float(np.max(np.abs((self._omega - 1.0) * F_NOM)))
        info: Dict[str, Any] = {
            "sim_time": self._sim_time,
            "omega": self._omega.copy(),
            "M": self._M.copy(),
            "D": self._D.copy(),
            "P_es": self._P_es.copy(),
            "sim_ok": sim_ok,
            "max_freq_deviation_hz": _max_freq_dev,
            "tds_failed": (not sim_ok) or omega_unstable,
            "omega_unstable": omega_unstable,
            "reward_components": components,
        }

        return obs, reward, terminated, truncated, info

    # ------------------------------------------------------------------
    # Observation (Sec. III-C of the paper)
    # ------------------------------------------------------------------

    def _build_obs(self) -> np.ndarray:
        """
        Construct per-agent observations.

        For each agent *i* the observation vector is::

            [P_i / NORM_P,
             freq_dev_i * omega_n / NORM_FREQ,
             rocof_i * omega_n / NORM_ROCOF,
             nb1_freq_dev (normalised),
             nb2_freq_dev (normalised),
             nb1_rocof    (normalised),
             nb2_rocof    (normalised)]

        Neighbour entries are zeroed when a communication link is failed.
        """
        obs = np.zeros((N_ESS, OBS_DIM), dtype=np.float32)

        for i in range(N_ESS):
            # Local measurements
            freq_dev_norm = (self._omega[i] - 1.0) * OMEGA_N / NORM_FREQ
            if self.DT > 0:
                rocof_norm = (
                    (self._omega[i] - self._omega_prev[i])
                    / self.DT
                    * OMEGA_N
                    / NORM_ROCOF
                )
            else:
                rocof_norm = 0.0

            obs[i, 0] = self._P_es[i] / NORM_P
            obs[i, 1] = freq_dev_norm
            obs[i, 2] = rocof_norm

            # Neighbour data (with possible comm failure)
            for n_idx, nb in enumerate(COMM_ADJ[i]):
                if self._comm_mask[i, n_idx]:
                    nb_data = self._get_comm_data(i, nb)
                    obs[i, 3 + n_idx] = nb_data["omega"]
                    obs[i, 5 + n_idx] = nb_data["rocof"]
                # else: zeros (link failed)

        return obs

    # ------------------------------------------------------------------
    # Communication helpers
    # ------------------------------------------------------------------

    def _update_comm_buffers(self) -> None:
        """Push the latest normalised measurements into delay buffers."""
        for i in range(N_ESS):
            for nb in COMM_ADJ[i]:
                freq_dev_norm = (self._omega[nb] - 1.0) * OMEGA_N / NORM_FREQ
                if self.DT > 0:
                    rocof_norm = (
                        (self._omega[nb] - self._omega_prev[nb])
                        / self.DT
                        * OMEGA_N
                        / NORM_ROCOF
                    )
                else:
                    rocof_norm = 0.0

                buf = self._comm_buffer[(i, nb)]
                buf["omega"].append(freq_dev_norm)
                buf["rocof"].append(rocof_norm)
                # Keep buffer bounded
                max_len = self.comm_delay_steps + 2
                if len(buf["omega"]) > max_len:
                    buf["omega"].pop(0)
                    buf["rocof"].pop(0)

    def _get_comm_data(self, agent: int, neighbor: int) -> Dict[str, float]:
        """Retrieve (possibly delayed) normalised data from *neighbor*."""
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
        rewards = np.zeros(N_ESS, dtype=np.float32)
        r_f_total = 0.0

        # Recover physical parameter adjustments from normalized actions
        delta_M = 0.5 * (action[:, 0] + 1.0) * (DM_MAX - DM_MIN) + DM_MIN  # p.u.
        delta_D = 0.5 * (action[:, 1] + 1.0) * (DD_MAX - DD_MIN) + DD_MIN  # p.u.

        # Frequency deviations in Hz for all agents
        dw_hz = (self._omega - 1.0) * F_NOM  # shape (N_ESS,)

        # r_f (Eq. 15-16): relative sync penalty per agent
        for i in range(N_ESS):
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
            "r_f": r_f_total / N_ESS,
            "r_h": -PHI_H * r_h_val,
            "r_d": -PHI_D * r_d_val,
        }
        return rewards, components

    # ------------------------------------------------------------------
    # Public disturbance helpers
    # ------------------------------------------------------------------

    def apply_disturbance(
        self,
        bus_name: Optional[str] = None,
        magnitude: Optional[float] = None,
    ) -> None:
        """
        Apply a load / generation disturbance.

        Parameters
        ----------
        bus_name : str or None
            Target bus identifier (e.g. ``"PQ_4"``).  ``None`` picks one at
            random.
        magnitude : float or None
            Disturbance size in p.u.  ``None`` samples uniformly from
            ``[DIST_MIN, DIST_MAX]`` with random sign.
        """
        if magnitude is None:
            magnitude = float(
                self.np_random.uniform(DIST_MIN, DIST_MAX)
            )
            if self.np_random.random() > 0.5:
                magnitude = -magnitude

        self._apply_disturbance_backend(bus_name, magnitude)

    def gen_trip(
        self, gen_name: str = "GENROU_2", trip_time: float = 0.5
    ) -> None:
        """Simulate a generator trip event."""
        self._gen_trip_backend(gen_name, trip_time)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release resources."""
        self._close_backend()
        super().close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Abstract backend hooks (implemented by subclasses)
    # ------------------------------------------------------------------

    def _reset_backend(self) -> None:
        raise NotImplementedError

    def _step_backend(
        self, M_target: np.ndarray, D_target: np.ndarray
    ) -> None:
        """Advance the simulation by DT with sub-step interpolation."""
        raise NotImplementedError

    def _read_measurements(self) -> None:
        """Populate ``_omega``, ``_omega_prev``, ``_P_es`` from the backend."""
        raise NotImplementedError

    def _apply_disturbance_backend(
        self, bus_name: Optional[str], magnitude: float
    ) -> None:
        raise NotImplementedError

    def _gen_trip_backend(self, gen_name: str, trip_time: float) -> None:
        raise NotImplementedError

    def _close_backend(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Standalone ODE Backend
# ---------------------------------------------------------------------------

class NE39BusStandaloneEnv(_NE39BaseEnv):
    """
    Pure-Python multi-machine swing-equation model with RK4 integration.

    Models:
        - 8 VSGs (GENCLS-style swing equation) on buses 40-47.
        - 2 retained synchronous machines: G9 (Bus 38, H=3.45 s) and
          G10 (Bus 39, H=50.0 s).
        - Simplified admittance matrix coupling through line reactances.

    No external dependencies beyond NumPy -- suitable for fast RL training.
    """

    def __init__(
        self,
        x_line: float = NEW_LINE_X,
        comm_delay_steps: int = 0,
        render_mode: Optional[str] = None,
        training: bool = True,
    ):
        super().__init__(
            comm_delay_steps=comm_delay_steps,
            render_mode=render_mode,
            training=training,
        )
        self.x_line = x_line

        # ODE state for VSGs
        self._delta: np.ndarray = np.zeros(N_ESS)
        self._P_mech: np.ndarray = np.full(N_ESS, PV_P0)

        # Retained synchronous machines (G9, G10)
        self._omega_sync: np.ndarray = np.ones(2)
        self._delta_sync: np.ndarray = np.zeros(2)

        # Simplified admittance matrix (built once on first reset)
        self._Y_bus: Optional[np.ndarray] = None

    # ------------------------------------------------------------------
    # Admittance matrix (simplified)
    # ------------------------------------------------------------------

    def _build_admittance(self) -> None:
        """
        Build a simplified (N_ESS + 2) x (N_ESS + 2) susceptance matrix.

        Nodes 0..7  = VSG buses (40-47)
        Nodes 8     = G9  (Bus 38)
        Nodes 9     = G10 (Bus 39)

        Topology (from IEEE 39-bus):
        - Each VSG connects to its parent bus via x_line
        - Parent buses interconnect via the 345kV network
        - G9 (Bus 38) connects via Bus 29 (x=0.0156+0.025=0.04 pu)
        - G10 (Bus 39) connects via Bus 1/9 (x=0.025 pu)

        We use the reduced admittance matrix seen at generator buses
        (Kron reduction of the full 39-bus network). The equivalent
        transfer reactances between generator buses are approximated
        from typical IEEE 39-bus reduced Y_bus values.
        """
        n = N_ESS + 2  # 8 VSGs + 2 sync machines
        B = np.zeros((n, n))

        # Approximate transfer reactances between gen buses (from IEEE 39-bus
        # Kron reduction). These represent the effective electrical distance
        # between generator internal nodes after eliminating load buses.
        # Values in p.u. on 100 MVA base.
        x_transfer = np.full((n, n), 2.0)  # default: weakly coupled

        # G10 (node 9) is the system reference / infinite bus equivalent
        # Connected to most generators via moderate reactance
        x_g10 = [0.30, 0.35, 0.30, 0.35, 0.40, 0.25, 0.35, 0.30, 0.04, 0.0]
        for i in range(n - 1):
            x_transfer[i, n - 1] = x_g10[i]
            x_transfer[n - 1, i] = x_g10[i]

        # G9 (node 8) connects through Bus 29-38
        x_g9 = [0.50, 0.45, 0.40, 0.45, 0.55, 0.35, 0.45, 0.40, 0.0, 0.04]
        for i in range(n):
            if i != 8:
                x_transfer[8, i] = x_g9[i]
                x_transfer[i, 8] = x_g9[i]

        # Nearby generators have stronger coupling
        # G1(30)-G10(39) via Bus 1-39: x~0.025+0.025=0.05
        x_transfer[0, 9] = 0.15; x_transfer[9, 0] = 0.15
        # G2(31)-G6(35) via Bus 6: x~0.20
        x_transfer[1, 5] = 0.20; x_transfer[5, 1] = 0.20
        # G3(32)-G4(33) close: x~0.25
        x_transfer[2, 3] = 0.25; x_transfer[3, 2] = 0.25
        # G7(36)-G8(37) close via Bus 23-25: x~0.30
        x_transfer[6, 7] = 0.30; x_transfer[7, 6] = 0.30

        # Build B matrix from transfer reactances
        for i in range(n):
            for j in range(n):
                if i != j and x_transfer[i, j] > 0:
                    b_ij = 1.0 / x_transfer[i, j]
                    B[i, j] = -b_ij
                    B[i, i] += b_ij

        self._Y_bus = B

        # Compute equivalent load conductance so the system is balanced.
        # Each generator's P_mech should equal P_e at the initial operating
        # point.  We solve for g_load values that achieve this.
        #
        # At steady state with small angles, P_e ≈ transfers + g_load.
        # We want P_mech(sys) = transfers + g_load, so
        # g_load = P_mech(sys) - transfers(delta=0... which is 0).
        # But we'll solve it properly via iteration.

        # Generator outputs on system base (100 MVA)
        # VSGs: PV_P0 * VSG_SN / Sbase = 0.5 * 200 / 100 = 1.0
        # G9: 830/100 = 8.3, G10: 250/100 = 2.5
        P_gen_sys = np.concatenate([
            np.full(N_ESS, PV_P0 * VSG_SN / 100.0),
            np.array([8.3, 2.5]),
        ])

        # Wind farm outputs on system base (these inject into parent buses)
        # W1-W8 outputs: 250, 520.81, 650, 632, 508, 650, 560, 540 MW
        wind_p_mw = np.array([250, 520.81, 650, 632, 508, 650, 560, 540])
        P_wind_sys = wind_p_mw / 100.0

        # Total generation at each bus = ESS + wind farm
        P_total_gen = P_gen_sys.copy()
        P_total_gen[:N_ESS] += P_wind_sys

        # IEEE 39-bus total load ≈ 6097 MW, distributed to generator buses
        # after Kron reduction. Use generation dispatch as proxy.
        g_load = P_total_gen  # At V=1 and delta=0, P_load = g_load

        self._g_load = g_load

    # ------------------------------------------------------------------
    # Electrical power computation
    # ------------------------------------------------------------------

    def _compute_electrical_power(
        self,
        omega_vsg: np.ndarray,
        delta_vsg: np.ndarray,
        omega_sync: np.ndarray,
        delta_sync: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute electrical power injections for all machines.

        Uses the classical power-angle relation:

            P_e_i = sum_j |V_i| |V_j| |B_ij| sin(delta_i - delta_j)

        with |V| = 1.0 p.u. everywhere (classical model).

        Returns
        -------
        P_e_vsg  : ndarray, shape (N_ESS,)
        P_e_sync : ndarray, shape (2,)
        """
        B = self._Y_bus
        n = N_ESS + 2
        V = 1.0  # flat voltage profile (classical assumption)

        # Assemble full angle vector
        delta_all = np.concatenate([delta_vsg, delta_sync])

        P_e_all = np.zeros(n)
        for i in range(n):
            for j in range(n):
                if i != j:
                    P_e_all[i] += (
                        V * V * (-B[i, j])
                        * np.sin(delta_all[i] - delta_all[j])
                    )
            # Load power absorption (included in Kron-reduced diagonal)
            P_e_all[i] += self._g_load[i] * V * V

        return P_e_all[:N_ESS], P_e_all[N_ESS:]

    # ------------------------------------------------------------------
    # RK4 integrator
    # ------------------------------------------------------------------

    def _rk4_step(
        self, M: np.ndarray, D: np.ndarray, dt: float
    ) -> None:
        """
        Single RK4 step for all swing equations (VSGs + sync machines).

        VSG swing equation (GENCLS):
            M_i * d(omega_i)/dt = P_mech_i - P_e_i - D_i*(omega_i - 1)
            d(delta_i)/dt       = omega_n * (omega_i - 1)

        Sync machine swing equation (same form):
            2*H_j * d(omega_j)/dt = P_mech_j - P_e_j - D_j*(omega_j - 1)
            d(delta_j)/dt         = omega_n * (omega_j - 1)
        """
        omega_v = self._omega.copy()
        delta_v = self._delta.copy()
        omega_s = self._omega_sync.copy()
        delta_s = self._delta_sync.copy()

        # Mechanical power for sync machines on MACHINE base (1000 MVA)
        # G9: 830 MW / 1000 MVA = 0.83, G10: 250 MW / 1000 MVA = 0.25
        P_mech_sync = np.array([0.83, 0.25])

        def derivs(ov, dv, os_, ds_):
            # P_e is on system base (100 MVA) from admittance matrix
            P_e_v, P_e_s = self._compute_electrical_power(ov, dv, os_, ds_)

            # Convert P_e to machine base for swing equation
            # VSG: Sn=200 MVA -> factor = Sbase/Sn = 100/200 = 0.5
            P_e_v_pu = P_e_v * (100.0 / VSG_SN)
            # Sync: Sn=1000 MVA -> factor = 100/1000 = 0.1
            P_e_s_pu = P_e_s * (100.0 / 1000.0)

            # VSGs (all on VSG_SN base)
            d_omega_v = (self._P_mech - P_e_v_pu - D * (ov - 1.0)) / M
            d_delta_v = OMEGA_N * (ov - 1.0)

            # Sync machines (on 1000 MVA base)
            # P_mech_sync on 1000 MVA base: G9=830/1000, G10=250/1000
            M_sync = 2.0 * SYNC_H  # M = 2H on machine base
            d_omega_s = (P_mech_sync - P_e_s_pu - SYNC_D * (os_ - 1.0)) / M_sync
            d_delta_s = OMEGA_N * (os_ - 1.0)

            return d_omega_v, d_delta_v, d_omega_s, d_delta_s, P_e_v_pu

        k1 = derivs(omega_v, delta_v, omega_s, delta_s)
        k2 = derivs(
            omega_v + 0.5 * dt * k1[0],
            delta_v + 0.5 * dt * k1[1],
            omega_s + 0.5 * dt * k1[2],
            delta_s + 0.5 * dt * k1[3],
        )
        k3 = derivs(
            omega_v + 0.5 * dt * k2[0],
            delta_v + 0.5 * dt * k2[1],
            omega_s + 0.5 * dt * k2[2],
            delta_s + 0.5 * dt * k2[3],
        )
        k4 = derivs(
            omega_v + dt * k3[0],
            delta_v + dt * k3[1],
            omega_s + dt * k3[2],
            delta_s + dt * k3[3],
        )

        def rk4_combine(y, k1y, k2y, k3y, k4y):
            return y + (dt / 6.0) * (k1y + 2.0 * k2y + 2.0 * k3y + k4y)

        self._omega_prev = self._omega.copy()
        self._omega = np.clip(
            rk4_combine(omega_v, k1[0], k2[0], k3[0], k4[0]), 0.9, 1.1
        )
        self._delta = rk4_combine(delta_v, k1[1], k2[1], k3[1], k4[1])
        self._omega_sync = np.clip(
            rk4_combine(omega_s, k1[2], k2[2], k3[2], k4[2]), 0.9, 1.1
        )
        self._delta_sync = rk4_combine(delta_s, k1[3], k2[3], k3[3], k4[3])

        # Record electrical power for observations
        self._P_es = k1[4]  # use start-of-step value

    # ------------------------------------------------------------------
    # Backend hooks
    # ------------------------------------------------------------------

    # Wind farm power outputs on VSG base (MW / VSG_SN)
    # W1-W8: 250, 520.81, 650, 632, 508, 650, 560, 540 MW
    _WIND_P_VSG_BASE: np.ndarray = np.array(
        [250, 520.81, 650, 632, 508, 650, 560, 540]
    ) / VSG_SN

    def _reset_backend(self) -> None:
        """Initialise ODE state variables with steady-state power flow."""
        if self._Y_bus is None:
            self._build_admittance()

        # P_mech = ESS output + wind farm injection (both on VSG base)
        self._P_mech = np.full(N_ESS, PV_P0) + self._WIND_P_VSG_BASE
        self._omega_sync = np.ones(2)

        # Solve for initial angles that give P_e = P_mech at omega=1.0
        # Using Newton-Raphson on the power balance equations
        self._delta = np.zeros(N_ESS)
        self._delta_sync = np.zeros(2)

        # P_mech for sync machines on their base
        P_mech_sync = np.array([0.83, 0.25])

        # All P_mech on system base for power flow
        P_mech_all_sys = np.concatenate([
            self._P_mech * (VSG_SN / 100.0),  # VSG: 200/100=2
            P_mech_sync * (1000.0 / 100.0),    # Sync: 1000/100=10
        ])

        n = N_ESS + 2
        delta_all = np.zeros(n)
        # G10 (node n-1) is the reference bus (delta=0)

        for _iter in range(50):
            # Compute P_e on system base (must match _compute_electrical_power)
            P_e = np.zeros(n)
            for i in range(n):
                for j in range(n):
                    if i != j:
                        P_e[i] += (
                            -self._Y_bus[i, j]
                            * np.sin(delta_all[i] - delta_all[j])
                        )
                # Local load absorption
                P_e[i] += self._g_load[i]

            # Power mismatch (skip reference bus n-1)
            mismatch = P_mech_all_sys[:n-1] - P_e[:n-1]
            if np.max(np.abs(mismatch)) < 1e-6:
                break

            # Jacobian
            J = np.zeros((n-1, n-1))
            for i in range(n-1):
                for j in range(n-1):
                    if i == j:
                        for k in range(n):
                            if k != i:
                                J[i, i] += (
                                    -self._Y_bus[i, k]
                                    * np.cos(delta_all[i] - delta_all[k])
                                )
                    else:
                        J[i, j] = (
                            self._Y_bus[i, j]
                            * np.cos(delta_all[i] - delta_all[j])
                        )

            try:
                d_delta = np.linalg.solve(J, mismatch)
                delta_all[:n-1] += d_delta
            except np.linalg.LinAlgError:
                break

        self._delta = delta_all[:N_ESS]
        self._delta_sync = delta_all[N_ESS:]

    def _step_backend(
        self, M_target: np.ndarray, D_target: np.ndarray
    ) -> None:
        """
        Advance ODE by DT with N_SUBSTEPS sub-step parameter interpolation.
        """
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
        """Measurements are computed inline by the RK4 integrator."""
        pass

    def _apply_disturbance_backend(
        self, bus_name: Optional[str], magnitude: float
    ) -> None:
        """Apply a mechanical-power step disturbance."""
        if bus_name is None:
            idx = int(self.np_random.integers(0, N_ESS))
        else:
            try:
                idx = min(
                    int(bus_name.split("_")[1]) % N_ESS, N_ESS - 1
                )
            except (IndexError, ValueError):
                idx = 0

        # Distribute impact across the system (scaled by system size)
        self._P_mech[idx] += magnitude / (N_ESS * 2)
        print(
            f"[Standalone] Disturbance at ES{idx + 1}: "
            f"{magnitude:+.2f} p.u."
        )

    def _gen_trip_backend(self, gen_name: str, trip_time: float) -> None:
        """
        Simulate wind farm trip as sudden power deficit.

        When a wind farm trips, the system loses its power output. This
        creates a generation-load imbalance that all remaining machines
        must compensate for, causing frequency to drop.

        The lost power is distributed as additional mechanical load on
        nearby VSGs (primarily the one at the tripped bus location),
        weighted by electrical distance.
        """
        try:
            gen_idx = int(gen_name.split("_")[1]) - 1
        except (IndexError, ValueError):
            gen_idx = 0

        if 0 <= gen_idx < N_ESS:
            # Wind farm W(gen_idx+1) output on system base (100 MVA)
            # Original gen outputs from IEEE 39-bus data:
            wind_p_mw = [250, 520.81, 650, 632, 508, 650, 560, 540]
            lost_power_pu = wind_p_mw[gen_idx] / 100.0  # system base

            # Convert to VSG machine base (200 MVA)
            lost_power_vsg = lost_power_pu * (100.0 / VSG_SN)

            # Distribute: 60% on nearest ESS, rest shared equally
            for i in range(N_ESS):
                if i == gen_idx:
                    self._P_mech[i] -= 0.6 * lost_power_vsg
                else:
                    self._P_mech[i] -= 0.4 * lost_power_vsg / (N_ESS - 1)

            print(
                f"[Standalone] Wind farm trip: {gen_name} "
                f"(lost {wind_p_mw[gen_idx]:.0f} MW, "
                f"P_deficit={lost_power_vsg:.3f} p.u. on VSG base)"
            )

    def _close_backend(self) -> None:
        """Nothing to release."""
        pass


# ---------------------------------------------------------------------------
# MATLAB / Simulink Backend
# ---------------------------------------------------------------------------

class NE39BusSimulinkEnv(_NE39BaseEnv):
    """
    Gymnasium environment backed by MATLAB/Simulink.

    Delegates simulation to SimulinkBridge which batches all 8-agent
    parameter sets and state reads into a single MATLAB IPC call per step.

    Requirements
    ------------
    - MATLAB R2021b or later with Simulink.
    - ``matlab.engine`` Python package.
    - NE39bus_v2.slx and data files in model_dir.
    """

    def __init__(
        self,
        model_name: str = "NE39bus_v2",
        model_dir: Optional[str] = None,
        x_line: float = NEW_LINE_X,
        comm_delay_steps: int = 0,
        render_mode: Optional[str] = None,
        training: bool = True,
    ):
        super().__init__(
            comm_delay_steps=comm_delay_steps,
            render_mode=render_mode,
            training=training,
        )
        self.x_line = x_line

        from engine.simulink_bridge import BridgeConfig, SimulinkBridge

        resolved_dir = model_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', '..', 'scenarios', 'new_england', 'simulink_models'
        )
        cfg = BridgeConfig(
            model_name=model_name,
            model_dir=resolved_dir,
            n_agents=N_ESS,
            dt_control=DT,
            sbase_va=100e6,  # 100 MVA system base
            m_path_template='{model}/VSG_ES{idx}/M0',
            d_path_template='{model}/VSG_ES{idx}/D0',
            omega_signal='omega_ES{idx}',
            vabc_signal='Vabc_ES{idx}',
            iabc_signal='Iabc_ES{idx}',
        )
        self.bridge = SimulinkBridge(cfg)

    # ------------------------------------------------------------------
    # Backend hooks
    # ------------------------------------------------------------------

    # Initial phase angles (degrees) from NE39bus_v2 load-flow.
    # Must match patch_ne39_faststart.m init_phAng vector.
    _INIT_PHANG = [-3.646, 0.0, 2.466, 4.423, 3.398, 5.698, 8.494, 2.181]

    def _reset_backend(self) -> None:
        try:
            self.bridge.load_model()
            self.bridge.reset()  # clears t_current, Pe_prev, delta_prev_deg
            self._sim_time = 0.0

            # Build vsg_warmup init_params struct in MATLAB base workspace.
            # MATLAB variable names cannot start with underscore.
            phang_str = ", ".join(f"{v:.4f}" for v in self._INIT_PHANG)
            self.bridge.session.eval(
                f"ne39_ip.M0 = {VSG_M0}; "
                f"ne39_ip.D0 = {VSG_D0}; "
                f"ne39_ip.phAng = [{phang_str}]; "
                f"ne39_ip.Pe0 = 0.5; "
                f"ne39_ip.t_warmup = {T_WARMUP};",
                nargout=0,
            )

            # Call vsg_warmup with full NE39 5-arg signature
            # Returns [state, status] but we only need status for error checking.
            mdbl = self.bridge._matlab_double
            agent_ids = mdbl(list(range(1, N_ESS + 1)))
            warmup_state, warmup_status = self.bridge.session.call(
                "vsg_warmup",
                self.bridge.cfg.model_name,
                agent_ids,
                float(self.bridge.cfg.sbase_va),
                self.bridge._matlab_cfg,
                self.bridge.session.eval("ne39_ip", nargout=1),
                nargout=2,
            )

            if warmup_status and not warmup_status.get("success", True):
                raise RuntimeError(
                    f"vsg_warmup failed: {warmup_status.get('error', 'unknown')}"
                )

            self.bridge.t_current = T_WARMUP

            # Seed feedback state from warmup result so first step has valid Pe/delta
            if warmup_state:
                self.bridge._delta_prev_deg = np.array(
                    warmup_state.get("delta_deg", [0.0] * N_ESS)
                ).flatten()
                self.bridge._Pe_prev = np.array(
                    warmup_state.get("Pe", [0.5] * N_ESS)
                ).flatten()

        except Exception as exc:
            print(f"[NE39Bus-Simulink] Reset failed: {exc}")
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
        pass  # Already read in _step_backend via bridge.step()

    def _apply_disturbance_backend(
        self, bus_name: Optional[str], magnitude: float
    ) -> None:
        """Apply disturbance via workspace variable Pe_ES{k}.

        NE39bus_v2 has no breaker blocks.  Instead we step the electrical
        power reference of one VSG agent, simulating a load-step or
        generation-change event that excites frequency dynamics.

        bus_name: ignored (random agent selected).  magnitude is in p.u.
        on sbase; clipped to VSG base before writing.
        """
        try:
            vsg_sn = 200e6
            pe_scale = self.bridge.cfg.sbase_va / vsg_sn  # 0.5 (sbase 100MVA / VSG 200MVA)
            # Pick random VSG agent (0-indexed)
            agent_idx = int(self.np_random.integers(0, N_ESS)) + 1
            # _Pe_prev is in sbase p.u.  Convert to VSG base p.u. for workspace.
            if self.bridge._Pe_prev is not None:
                pe_cur_sbase = float(self.bridge._Pe_prev[agent_idx - 1])
            else:
                pe_cur_sbase = 0.25  # 0.5 sbase → 0.25 VSG base nominal

            # Disturbance step in sbase p.u., then convert to VSG base
            pe_new_sbase = pe_cur_sbase + magnitude * pe_scale * 0.1
            pe_new_vsg   = float(np.clip(pe_new_sbase * pe_scale, 0.0, 1.5))
            pe_cur_vsg   = pe_cur_sbase * pe_scale
            self.bridge.session.eval(
                f"assignin('base', 'Pe_ES{agent_idx}', {pe_new_vsg:.6f});",
                nargout=0,
            )
            print(
                f"[NE39-Simulink] Disturbance: Pe_ES{agent_idx} "
                f"{pe_cur_vsg:.3f} -> {pe_new_vsg:.3f} p.u. (VSG base)"
            )
        except Exception as exc:
            print(f"[NE39-Simulink] Disturbance failed: {exc}")

    def _gen_trip_backend(self, gen_name: str, trip_time: float) -> None:
        """Simulate wind-farm trip by zeroing Pe of a VSG agent.

        gen_name: 'GENROU_N' — N maps to VSG agent N (1-indexed).
        Writes Pe_ES{N}=0 into the workspace; takes effect on the next
        FastRestart step boundary (no model recompilation needed).
        """
        try:
            try:
                agent_idx = int(gen_name.split("_")[-1])
                agent_idx = max(1, min(agent_idx, N_ESS))
            except (ValueError, IndexError):
                agent_idx = 1
            self.bridge.session.eval(
                f"assignin('base', 'Pe_ES{agent_idx}', 0.0);",
                nargout=0,
            )
            print(
                f"[NE39-Simulink] Gen trip: Pe_ES{agent_idx} -> 0 "
                f"(simulates {gen_name} trip)"
            )
        except Exception as exc:
            print(f"[NE39-Simulink] Gen trip failed: {exc}")

    def _close_backend(self) -> None:
        self.bridge.close()


# ---------------------------------------------------------------------------
# Backward-compatible aliases used by train.py
# ---------------------------------------------------------------------------

#: Alias kept so ``from ne39_env import NE39BusEnv`` continues to work.
NE39BusEnv = NE39BusSimulinkEnv
