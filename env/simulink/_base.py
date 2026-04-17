"""env/simulink/_base.py — Shared VSG observation / reward base class.

Extracted from ``_KundurBaseEnv`` and ``_NE39BaseEnv`` (which were 100% identical
for ``_build_obs``, ``_update_comm_buffers``, ``_get_comm_data``, and
``_compute_reward`` modulo the agent-count constant and action-decoding formula).

Usage
-----
Subclass ``_SimVsgBase`` and define the required class-level configuration
variables.  Implement ``_decode_action`` for the scenario's action encoding.

    class _MyBaseEnv(_SimVsgBase):
        _N_AGENTS   = 4
        _COMM_ADJ   = {0: [1, 3], ...}
        _F_NOM      = 50.0
        _OMEGA_N    = 2 * np.pi * 50.0
        ...

        def _decode_action(self, action):
            # zero-centered or affine — scenario specific
            ...
"""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
from utils.gym_compat import gym


class _SimVsgBase(gym.Env):
    """Shared VSG observation and reward implementation.

    Subclasses MUST define the following as **class-level attributes** before
    calling ``super().__init__()``::

        _N_AGENTS   : int   — number of VSG agents
        _COMM_ADJ   : dict  — adjacency map  {agent_i: [neighbor_j, ...]}
        _F_NOM      : float — nominal frequency (Hz)
        _OMEGA_N    : float — 2 * pi * _F_NOM (rad/s)
        _NORM_P     : float — active-power normalisation scale
        _NORM_FREQ  : float — frequency deviation normalisation scale
        _NORM_ROCOF : float — RoCoF normalisation scale
        _PHI_F      : float — reward weight for r_f
        _PHI_H      : float — reward weight for r_h
        _PHI_D      : float — reward weight for r_d
        _DM_MIN     : float — minimum inertia delta (M units)
        _DM_MAX     : float — maximum inertia delta (M units)
        _DD_MIN     : float — minimum damping delta
        _DD_MAX     : float — maximum damping delta

    Subclasses MUST also implement ``_decode_action``.

    The following **instance attributes** must be initialised by the subclass
    ``__init__`` before any shared method is called (they are inherited, so
    standard ``__init__`` chain is sufficient)::

        self._omega        : np.ndarray  shape (_N_AGENTS,)
        self._omega_prev   : np.ndarray  shape (_N_AGENTS,)
        self._P_es         : np.ndarray  shape (_N_AGENTS,)
        self._comm_buffer  : dict        {(i, nb): {"omega": list, "rocof": list}}
        self._comm_mask    : np.ndarray  shape (_N_AGENTS, MAX_NEIGHBORS)
        self.comm_delay_steps : int
        self.DT            : float
        self.OBS_DIM       : int
    """

    # ── Class-level config (must be overridden by each scenario base class) ──
    # Use None as sentinel for required fields so omitted overrides fail loudly
    # at iteration time rather than silently producing empty loops.
    _N_AGENTS: int = 0
    _COMM_ADJ: Dict[int, list] = None  # type: ignore[assignment]
    _F_NOM: float = 50.0
    _OMEGA_N: float = 2.0 * np.pi * 50.0
    _NORM_P: float = 2.0
    _NORM_FREQ: float = 3.0
    _NORM_ROCOF: float = 5.0
    _PHI_F: float = 100.0
    _PHI_H: float = 1.0
    _PHI_D: float = 1.0
    _DM_MIN: float = -6.0
    _DM_MAX: float = 18.0
    _DD_MIN: float = -1.5
    _DD_MAX: float = 4.5

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Warn at class-definition time if a concrete subclass forgets _COMM_ADJ."""
        super().__init_subclass__(**kwargs)
        if cls._COMM_ADJ is None and not cls.__name__.startswith("_"):
            import warnings
            warnings.warn(
                f"{cls.__name__} does not override _COMM_ADJ; "
                "calls to _build_obs/_update_comm_buffers will raise TypeError.",
                stacklevel=2,
            )

    # ── Observation ──────────────────────────────────────────────────────────

    def _build_obs(self) -> np.ndarray:
        """Construct per-agent observation (paper Sec. III-C, Eq. 11).

        Layout per agent:
            [P_i / NORM_P,
             freq_dev_i * omega_n / NORM_FREQ,
             rocof_i    * omega_n / NORM_ROCOF,
             nb1_freq_dev (normalised, 0 if link failed),
             nb2_freq_dev (normalised, 0 if link failed),
             nb1_rocof    (normalised, 0 if link failed),
             nb2_rocof    (normalised, 0 if link failed)]
        """
        obs = np.zeros((self._N_AGENTS, self.OBS_DIM), dtype=np.float32)

        for i in range(self._N_AGENTS):
            freq_dev_norm = (self._omega[i] - 1.0) * self._OMEGA_N / self._NORM_FREQ
            if self.DT > 0:
                rocof_norm = (
                    (self._omega[i] - self._omega_prev[i])
                    / self.DT * self._OMEGA_N / self._NORM_ROCOF
                )
            else:
                rocof_norm = 0.0

            obs[i, 0] = self._P_es[i] / self._NORM_P
            obs[i, 1] = freq_dev_norm
            obs[i, 2] = rocof_norm

            for n_idx, nb in enumerate(self._COMM_ADJ[i]):
                if self._comm_mask[i, n_idx]:
                    nb_data = self._get_comm_data(i, nb)
                    obs[i, 3 + n_idx] = nb_data["omega"]
                    obs[i, 5 + n_idx] = nb_data["rocof"]
                # else: zeros (link failed, Eq. 11 convention)

        return obs

    # ── Communication helpers ─────────────────────────────────────────────────

    def _update_comm_buffers(self) -> None:
        """Push latest normalised measurements into per-edge delay buffers."""
        for i in range(self._N_AGENTS):
            for nb in self._COMM_ADJ[i]:
                freq_dev_norm = (self._omega[nb] - 1.0) * self._OMEGA_N / self._NORM_FREQ
                if self.DT > 0:
                    rocof_norm = (
                        (self._omega[nb] - self._omega_prev[nb])
                        / self.DT * self._OMEGA_N / self._NORM_ROCOF
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
        """Return (possibly delayed) normalised data from *neighbor* to *agent*."""
        buf = self._comm_buffer[(agent, neighbor)]
        idx = max(0, len(buf["omega"]) - 1 - self.comm_delay_steps)
        return {
            "omega": buf["omega"][idx],
            "rocof": buf["rocof"][idx],
        }

    # ── Action decoding (scenario-specific) ──────────────────────────────────

    def _decode_action(self, action: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Map normalised action [-1, 1] to physical (delta_M, delta_D).

        Must be overridden by each scenario base class.

        Returns
        -------
        delta_M : np.ndarray, shape (_N_AGENTS,)
        delta_D : np.ndarray, shape (_N_AGENTS,)
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement _decode_action()"
        )

    # ── Reward (Eq. 14-18) ────────────────────────────────────────────────────

    def _compute_reward(
        self, action: np.ndarray
    ) -> Tuple[np.ndarray, Dict[str, float]]:
        """Reward per Yang et al. TPWRS 2023 Eq. 14-18.

        r_f (Eq. 15-16): relative sync penalty using Δω in p.u.
            Δω_pu_i = omega_i - 1.0   (dimensionless; 1.0 = nominal)
            ω̄_i     = mean of Δω_pu_i and active-neighbour values
            r_f_i   = -(Δω_pu_i - ω̄_i)² - Σ_j η_j (Δω_pu_j - ω̄_i)²

        NOTE: Δω must be in p.u. (not Hz) to match PHI_F=100 as calibrated
        in the paper (Sec.IV-B). Using Hz would amplify r_f by F_NOM²=2500–3600×,
        causing policy collapse to near-zero ΔH/ΔD actions.

        r_h (Eq. 17): -(mean_i ΔH_i)²  where ΔH_i = delta_M_i / 2
        r_d (Eq. 18): -(mean_i ΔD_i)²

        r_i = φ_f·r_f_i + φ_h·r_h + φ_d·r_d
        """
        n = self._N_AGENTS
        rewards = np.zeros(n, dtype=np.float32)
        r_f_total = 0.0

        delta_M, delta_D = self._decode_action(action)

        # Frequency deviations in p.u. (paper Eq.15-16 uses Δω, dimensionless)
        dw_pu = (self._omega - 1.0)

        # r_f (Eq. 15-16)
        for i in range(n):
            group_dw = [dw_pu[i]]
            for n_idx, nb in enumerate(self._COMM_ADJ[i]):
                if self._comm_mask[i, n_idx]:
                    group_dw.append(dw_pu[nb])
            omega_bar_i = float(np.mean(group_dw))

            r_f_i = -(dw_pu[i] - omega_bar_i) ** 2
            for n_idx, nb in enumerate(self._COMM_ADJ[i]):
                eta_j = 1.0 if self._comm_mask[i, n_idx] else 0.0
                r_f_i -= (dw_pu[nb] - omega_bar_i) ** 2 * eta_j

            step_r_f = self._PHI_F * r_f_i
            rewards[i] += step_r_f
            r_f_total += step_r_f

        # r_h (Eq. 17): (mean ΔH)² = (mean(ΔM) / 2)²
        delta_H_mean = float(np.mean(delta_M)) / 2.0
        r_h_val = delta_H_mean ** 2
        rewards -= self._PHI_H * r_h_val

        # r_d (Eq. 18): (mean ΔD)²
        delta_D_mean = float(np.mean(delta_D))
        r_d_val = delta_D_mean ** 2
        rewards -= self._PHI_D * r_d_val

        components: Dict[str, float] = {
            "r_f": r_f_total / n,
            "r_h": -self._PHI_H * r_h_val,
            "r_d": -self._PHI_D * r_d_val,
        }
        return rewards, components


__all__ = ["_SimVsgBase"]
