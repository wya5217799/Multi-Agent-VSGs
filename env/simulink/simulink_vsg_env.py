"""
DEPRECATED: This module is superseded by engine/simulink_bridge.py
and the refactored KundurSimulinkEnv / NE39BusSimulinkEnv classes.

The segmented simulation TODO on line 267 is now implemented in
vsg_helpers/vsg_step_and_read.m via SimulinkBridge.

This file is kept for reference only. Do not use in new code.

Original docstring:
SimulinkMultiVSGEnv — Python-Simulink co-simulation environment for MADRL VSG control.

Mirrors the interface of AndesMultiVSGEnv (env/andes/base_env.py) but uses
MATLAB/Simulink as the simulation backend via the MATLAB Engine for Python.

Usage:
    env = SimulinkMultiVSGEnv()
    obs = env.reset()
    for step in range(50):
        actions = {i: agent.select_action(obs[i]) for i in range(4)}
        obs, rewards, done, info = env.step(actions)
        if done:
            break

Requirements:
    - MATLAB R2025b with Simscape Electrical
    - MinGW-w64 compiler (setenv MW_MINGW64_LOC)
    - kundur_two_area.slx built by build_kundur_simulink.m + upgrade_generators.m
    - pip install matlabengine
"""

import numpy as np
from collections import deque
from typing import Dict, Optional, Tuple, Any

# Import config from project root (with fallback for VSG_M0/D0 naming)
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config as _cfg

N_AGENTS = _cfg.N_AGENTS
DT = _cfg.DT
T_EPISODE = _cfg.T_EPISODE
STEPS_PER_EPISODE = _cfg.STEPS_PER_EPISODE
OBS_DIM = _cfg.OBS_DIM
ACTION_DIM = _cfg.ACTION_DIM
MAX_NEIGHBORS = _cfg.MAX_NEIGHBORS
COMM_ADJACENCY = _cfg.COMM_ADJACENCY
COMM_FAIL_PROB = _cfg.COMM_FAIL_PROB
PHI_F = _cfg.PHI_F
PHI_H = _cfg.PHI_H
PHI_D = _cfg.PHI_D
# Root config uses H_ES0 (array) / D_ES0 (array); derive scalar defaults
VSG_M0 = getattr(_cfg, 'VSG_M0', _cfg.H_ES0[0] if hasattr(_cfg, 'H_ES0') else 12.0)
VSG_D0 = getattr(_cfg, 'VSG_D0', _cfg.D_ES0[0] if hasattr(_cfg, 'D_ES0') else 3.0)

# Action scaling (from config)
_SCALE_M = 0.2 * VSG_M0  # 2.4
_SCALE_D = 0.3 * VSG_D0  # 0.9
DM_MIN = -1.0 * _SCALE_M  # -2.4
DM_MAX =  3.0 * _SCALE_M  #  7.2
DD_MIN = -1.0 * _SCALE_D  # -0.9
DD_MAX =  3.0 * _SCALE_D  #  2.7

# Observation normalization
_OMEGA_SCALE = 50.0  # Convert p.u. deviation to Hz


class SimulinkMultiVSGEnv:
    """Multi-agent VSG environment using Simulink as simulation backend."""

    def __init__(
        self,
        model_name: str = 'kundur_two_area',
        model_dir: Optional[str] = None,
        random_disturbance: bool = True,
        comm_fail_prob: float = COMM_FAIL_PROB,
        comm_delay_steps: int = 0,
        seed: Optional[int] = None,
        mingw_path: str = r'D:\mingw64',
    ):
        self.model_name = model_name
        self.model_dir = model_dir or os.path.join(
            os.path.dirname(__file__), '..', '..', 'scenarios', 'kundur'
        )
        self.random_disturbance = random_disturbance
        self.comm_fail_prob = comm_fail_prob
        self.comm_delay_steps = comm_delay_steps
        self.mingw_path = mingw_path

        self.n_agents = N_AGENTS
        self.obs_dim = OBS_DIM
        self.action_dim = ACTION_DIM
        self.dt = DT
        self.steps_per_episode = STEPS_PER_EPISODE

        # VSG base parameters (per agent)
        self.M0 = np.full(N_AGENTS, VSG_M0)
        self.D0 = np.full(N_AGENTS, VSG_D0)

        # State tracking
        self.step_count = 0
        self._prev_omega = np.ones(N_AGENTS)
        self._current_M = self.M0.copy()
        self._current_D = self.D0.copy()

        # Communication state
        self.comm_eta = {}
        self._delayed_omega = {}
        self._delayed_omega_dot = {}

        # RNG
        self.rng = np.random.default_rng(seed)

        # MATLAB engine (lazy init)
        self._eng = None
        self._model_loaded = False

    # ------------------------------------------------------------------
    # MATLAB Engine Management
    # ------------------------------------------------------------------

    def _ensure_engine(self):
        """Start MATLAB engine if not already running."""
        if self._eng is not None:
            return
        import matlab.engine
        print("Starting MATLAB engine...")
        self._eng = matlab.engine.start_matlab()
        # Set compiler path
        self._eng.setenv('MW_MINGW64_LOC', self.mingw_path, nargout=0)
        # Change to model directory
        self._eng.cd(self.model_dir, nargout=0)
        print("MATLAB engine started.")

    def _load_model(self):
        """Load the Simulink model if not already loaded."""
        if self._model_loaded:
            return
        self._ensure_engine()
        eng = self._eng
        # Check if model file exists
        if not eng.exist(f'{self.model_name}.slx', 'file'):
            print(f"Building model with build_kundur_simulink.m...")
            eng.run('build_kundur_simulink.m', nargout=0)
            eng.run('add_disturbance_and_interface.m', nargout=0)
            eng.run('upgrade_generators.m', nargout=0)
        # Load model
        if not eng.bdIsLoaded(self.model_name):
            eng.load_system(self.model_name, nargout=0)
        self._model_loaded = True
        print(f"Model '{self.model_name}' loaded.")

    # ------------------------------------------------------------------
    # Environment Interface
    # ------------------------------------------------------------------

    def seed(self, seed: int):
        """Set random seed."""
        self.rng = np.random.default_rng(seed)

    def reset(
        self,
        delta_u: Optional[dict] = None,
        scenario_idx: Optional[int] = None,
        **kwargs,
    ) -> Dict[int, np.ndarray]:
        """Reset the environment and return initial observations."""
        self._load_model()
        eng = self._eng
        mdl = self.model_name

        # Reset step counter
        self.step_count = 0
        self._current_M = self.M0.copy()
        self._current_D = self.D0.copy()

        # Configure simulation
        eng.set_param(mdl, 'StopTime', str(T_EPISODE), nargout=0)
        eng.set_param(mdl, 'SimscapeLogType', 'all', nargout=0)
        eng.set_param(mdl, 'SimscapeLogName', 'simlog', nargout=0)

        # Configure disturbance
        if delta_u is not None:
            trip14_time = delta_u.get('trip14_time', T_EPISODE + 1)
            trip15_time = delta_u.get('trip15_time', T_EPISODE + 1)
        elif self.random_disturbance:
            # Random disturbance: pick Bus14 or Bus15, random time
            trip14_time = T_EPISODE + 1
            trip15_time = T_EPISODE + 1
            if self.rng.random() < 0.5:
                trip14_time = float(self.rng.uniform(0.5, 2.0))
            else:
                trip15_time = float(self.rng.uniform(0.5, 2.0))
        else:
            trip14_time = T_EPISODE + 1
            trip15_time = T_EPISODE + 1

        eng.set_param(f'{mdl}/Trip14', 'Time', str(trip14_time), nargout=0)
        eng.set_param(f'{mdl}/Trip15', 'Time', str(trip15_time), nargout=0)

        # Reset communication state
        self._reset_comm()

        # Run initial simulation segment (0 to 0.5s) for steady state
        # Then continue from 0.5s with RL control
        # For Simulink: we run the full episode in step() calls
        # Initial observation: all at nominal (steady state)
        self._prev_omega = np.ones(N_AGENTS)

        # Build initial observation (all zeros deviation = steady state)
        obs = {}
        for i in range(N_AGENTS):
            obs[i] = np.zeros(OBS_DIM, dtype=np.float32)

        return obs

    def step(
        self, actions: Dict[int, np.ndarray]
    ) -> Tuple[Dict[int, np.ndarray], Dict[int, float], bool, Dict[str, Any]]:
        """
        Execute one control step (DT seconds) in the Simulink model.

        Args:
            actions: dict[agent_id → np.array([ΔM_norm, ΔD_norm])], range [-1, 1]

        Returns:
            obs, rewards, done, info
        """
        eng = self._eng
        mdl = self.model_name

        # 1. Decode actions → physical M, D
        norm_actions = np.zeros((N_AGENTS, ACTION_DIM))
        delta_M = np.zeros(N_AGENTS)
        delta_D = np.zeros(N_AGENTS)

        for i in range(N_AGENTS):
            a = np.clip(actions[i], -1.0, 1.0)
            norm_actions[i] = a

            delta_M[i] = (a[0] + 1) / 2 * (DM_MAX - DM_MIN) + DM_MIN
            delta_D[i] = (a[1] + 1) / 2 * (DD_MAX - DD_MIN) + DD_MIN

            self._current_M[i] = max(self.M0[i] + delta_M[i], 0.2)
            self._current_D[i] = max(self.D0[i] + delta_D[i], 0.1)

        # 2. Update VSG parameters in Simulink
        #    ES1-ES4 are Simplified Generator blocks with RotorInertia and RotorDamping
        vsg_names = ['ES1', 'ES2', 'ES3', 'ES4']
        omega_s = 2 * np.pi * 60
        for i, name in enumerate(vsg_names):
            # Convert M (seconds) to J (kg*m^2): J = M * Sn / omega_s^2
            Sn = 200e6  # 200 MVA
            J = self._current_M[i] * Sn / omega_s**2
            D_phys = self._current_D[i] * Sn / omega_s**2

            eng.set_param(
                f'{mdl}/{name}', 'RotorInertia', str(J), nargout=0
            )
            eng.set_param(
                f'{mdl}/{name}', 'RotorDamping', str(D_phys), nargout=0
            )

        # 3. Advance simulation by DT
        #    Simulink runs the full episode; we use segmented simulation
        #    via sim() with StartTime/StopTime for each segment
        t_start = self.step_count * self.dt
        t_end = t_start + self.dt
        self.step_count += 1

        # For segmented Simulink simulation, we'd need to use
        # the Simulink simulation stepper API or pause/resume.
        # Simpler approach: run full episode once in reset(),
        # then extract data at each timestep.
        # TODO: Implement proper segmented simulation

        # 4. Read state from simlog (after full simulation)
        #    This is a placeholder - proper implementation needs
        #    segmented simulation or pre-computed trajectory
        omega = self._read_vsg_omega(t_end)
        P_es = self._read_vsg_power(t_end)
        omega_dot = self._compute_omega_dot(omega, P_es)

        # 5. Build observations
        obs = self._build_obs(omega, omega_dot, P_es)

        # 6. Compute rewards
        rewards, r_f, r_h, r_d = self._compute_rewards(
            omega, omega_dot, norm_actions
        )

        # 7. Check termination
        done = self.step_count >= self.steps_per_episode

        # 8. Info dict
        info = {
            'time': t_end,
            'omega': omega.copy(),
            'omega_dot': omega_dot.copy(),
            'P_es': P_es.copy(),
            'M_es': self._current_M.copy(),
            'D_es': self._current_D.copy(),
            'delta_M': delta_M.copy(),
            'delta_D': delta_D.copy(),
            'r_f': r_f,
            'r_h': r_h,
            'r_d': r_d,
            'freq_hz': omega * 60.0,
            'max_freq_deviation_hz': float(np.max(np.abs((omega - 1.0) * 60.0))),
        }

        # Update state
        self._prev_omega = omega.copy()

        return obs, rewards, done, info

    # ------------------------------------------------------------------
    # State Reading (from Simscape simlog)
    # ------------------------------------------------------------------

    def _read_vsg_omega(self, t: float) -> np.ndarray:
        """Read VSG angular velocities at time t from simlog."""
        omega = np.ones(N_AGENTS)
        eng = self._eng
        vsg_names = ['ES1', 'ES2', 'ES3', 'ES4']
        for i, name in enumerate(vsg_names):
            try:
                # Access simlog.ESx.omegaDel at time t
                od_val = eng.eval(
                    f"interp1(out.simlog.{name}.omegaDel.series.time, "
                    f"out.simlog.{name}.omegaDel.series.values, {t})"
                )
                omega[i] = 1.0 + float(od_val)
            except Exception:
                omega[i] = 1.0
        return omega

    def _read_vsg_power(self, t: float) -> np.ndarray:
        """Read VSG active power at time t from simlog."""
        P = np.zeros(N_AGENTS)
        eng = self._eng
        vsg_names = ['ES1', 'ES2', 'ES3', 'ES4']
        for i, name in enumerate(vsg_names):
            try:
                p_val = eng.eval(
                    f"interp1(out.simlog.{name}.activeElectricalPower.series.time, "
                    f"out.simlog.{name}.activeElectricalPower.series.values, {t})"
                )
                # Convert W to p.u. (Sn = 200 MVA)
                P[i] = float(p_val) / 200e6
            except Exception:
                P[i] = 0.0
        return P

    # ------------------------------------------------------------------
    # Observation & Reward (same logic as base_env.py)
    # ------------------------------------------------------------------

    def _build_obs(
        self, omega: np.ndarray, omega_dot: np.ndarray, P_es: np.ndarray
    ) -> Dict[int, np.ndarray]:
        """Build per-agent observations, matching base_env._build_obs."""
        obs = {}
        for i in range(N_AGENTS):
            o = np.zeros(OBS_DIM, dtype=np.float32)

            # Local: [P_es/2, Δω*scale/3, ω̇*scale/5]
            o[0] = P_es[i] / 2.0
            d_omega_i = (omega[i] - 1.0) * _OMEGA_SCALE
            od_i = omega_dot[i] * _OMEGA_SCALE
            o[1] = d_omega_i / 3.0
            o[2] = od_i / 5.0

            # Neighbor info
            neighbors = COMM_ADJACENCY[i]
            for k, j in enumerate(neighbors[:MAX_NEIGHBORS]):
                d_omega_j = (omega[j] - 1.0) * _OMEGA_SCALE
                od_j = omega_dot[j] * _OMEGA_SCALE

                if self.comm_eta.get((i, j), 0) == 1:
                    if self.comm_delay_steps > 0:
                        o[3 + k] = self._delayed_omega[(i, j)][0] / 3.0
                        o[3 + MAX_NEIGHBORS + k] = (
                            self._delayed_omega_dot[(i, j)][0] / 5.0
                        )
                        self._delayed_omega[(i, j)].append(d_omega_j)
                        self._delayed_omega_dot[(i, j)].append(od_j)
                    else:
                        o[3 + k] = d_omega_j / 3.0
                        o[3 + MAX_NEIGHBORS + k] = od_j / 5.0
                # else: link failed, stays 0

            obs[i] = o
        return obs

    def _compute_omega_dot(
        self, omega: np.ndarray, P_es: np.ndarray
    ) -> np.ndarray:
        """Compute frequency derivative from swing equation."""
        omega_dot = np.zeros(N_AGENTS)
        for i in range(N_AGENTS):
            M = self._current_M[i]
            D = self._current_D[i]
            Pm = 0.5  # Mechanical power setpoint (p.u.)
            Pe = P_es[i]
            omega_dot[i] = (Pm - Pe - D * (omega[i] - 1.0)) / max(M, 0.1)
        return omega_dot

    def _compute_rewards(
        self,
        omega: np.ndarray,
        omega_dot: np.ndarray,
        norm_actions: np.ndarray,
    ) -> Tuple[Dict[int, float], float, float, float]:
        """Compute per-agent rewards, matching base_env._compute_rewards."""
        d_omega_hz = (omega - 1.0) * _OMEGA_SCALE  # Hz deviation

        # Global average normalized actions (Eq. 17-18)
        ah_avg = float(np.mean(norm_actions[:, 0]))
        ad_avg = float(np.mean(norm_actions[:, 1]))

        rewards = {}
        r_f_total = 0.0
        r_h_total = 0.0
        r_d_total = 0.0

        for i in range(N_AGENTS):
            # Eq. 16: weighted average frequency with neighbors
            sum_w = d_omega_hz[i]
            n_active = 1
            for j in COMM_ADJACENCY[i]:
                if self.comm_eta.get((i, j), 0) == 1:
                    sum_w += d_omega_hz[j]
                    n_active += 1
            omega_bar = sum_w / n_active

            # Eq. 15: frequency synchronization penalty
            r_f = -(d_omega_hz[i] - omega_bar) ** 2
            for j in COMM_ADJACENCY[i]:
                if self.comm_eta.get((i, j), 0) == 1:
                    r_f -= (d_omega_hz[j] - omega_bar) ** 2

            # Eq. 17-18: action regularization (normalized actions)
            r_h = -(ah_avg) ** 2
            r_d = -(ad_avg) ** 2

            rewards[i] = PHI_F * r_f + PHI_H * r_h + PHI_D * r_d

            r_f_total += PHI_F * r_f
            r_h_total += PHI_H * r_h
            r_d_total += PHI_D * r_d

        return rewards, r_f_total, r_h_total, r_d_total

    # ------------------------------------------------------------------
    # Communication
    # ------------------------------------------------------------------

    def _reset_comm(self):
        """Reset communication state (link failures + delay buffers)."""
        self.comm_eta = {}
        for i, neighbors in COMM_ADJACENCY.items():
            for j in neighbors:
                if (j, i) in self.comm_eta:
                    self.comm_eta[(i, j)] = self.comm_eta[(j, i)]
                else:
                    fail = self.rng.random() < self.comm_fail_prob
                    self.comm_eta[(i, j)] = 0 if fail else 1

        if self.comm_delay_steps > 0:
            self._delayed_omega = {}
            self._delayed_omega_dot = {}
            for i in range(N_AGENTS):
                for j in COMM_ADJACENCY[i]:
                    self._delayed_omega[(i, j)] = deque(
                        [0.0] * self.comm_delay_steps,
                        maxlen=self.comm_delay_steps,
                    )
                    self._delayed_omega_dot[(i, j)] = deque(
                        [0.0] * self.comm_delay_steps,
                        maxlen=self.comm_delay_steps,
                    )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self):
        """Shut down MATLAB engine."""
        if self._eng is not None:
            try:
                self._eng.quit()
            except Exception:
                pass
            self._eng = None
            self._model_loaded = False
