# FACT: 这是合约本身。reward 公式实现 = 训练/评估的真值。
# Eq.14-18 来自 paper Sec.III-A；§11 训练/评价分离来自 boundary doc 条款。

"""ODE-side reward functions — training (local) and evaluation (global) split.

Plan: quality_reports/plans/2026-05-02_ode_paper_alignment.md (Stage 3)
Boundary: docs/paper/python_ode_env_boundary_cn.md §10 / §11 / §22.

Two reward kinds, KEEP THEM SEPARATE (boundary §11 hard rule):

  training_reward_local()
      Per-agent reward used during SAC training. Only the local agent's
      omega + active-neighbour omega contribute. Mean-then-square for
      r_h / r_d (Eq.17-18). Returned alongside per-component breakdown.

  evaluation_reward_global()
      Episode-aggregated reward used at evaluation. Pure frequency
      synchrony objective (Sec.IV-C):

          R = -Σ_t Σ_i (f_i,t - mean_i(f_t))^2

      No H/D regularization at evaluation time. Single scalar over a full
      episode. NOT used during training to avoid leaking global info.

Both functions are pure (no env state mutation, no logging, no IO).
"""

from __future__ import annotations

from typing import Mapping

import numpy as np

import config as cfg

# rad/s → Hz factor (project unit convention: omega is rad/s deviation)
_TO_HZ: float = 1.0 / (2.0 * np.pi)


# ---------------------------------------------------------------------------
# Training reward (Eq.14-18, local)
# ---------------------------------------------------------------------------


def training_reward_local(
    omega: np.ndarray,
    delta_H: np.ndarray,
    delta_D: np.ndarray,
    comm_neighbors: Mapping[int, list[int]],
    comm_eta: Mapping[tuple[int, int], int],
    *,
    phi_f: float | None = None,
    phi_h: float | None = None,
    phi_d: float | None = None,
) -> dict:
    """Compute per-agent training rewards (Eq.14-18).

    Parameters
    ----------
    omega : (N,) ndarray
        Frequency deviation (rad/s) at each ESS.
    delta_H, delta_D : (N,) ndarray
        Physical inertia / damping increments selected this step.
    comm_neighbors : dict[int, list[int]]
        Static neighbour topology (e.g., ``cfg.COMM_ADJACENCY``).
    comm_eta : dict[(int,int), int]
        Live link-state map (1 = active, 0 = failed) for the current episode.
    phi_*: float | None
        Reward weights; default to ``cfg.PHI_*``.

    Returns
    -------
    dict with keys:
        rewards          : dict[int, float]      total reward per agent
        r_f_per_agent    : list[float]            phi_f * r_f for each i
        r_h_per_agent    : list[float]            phi_h * r_h (broadcast over agents)
        r_d_per_agent    : list[float]            phi_d * r_d (broadcast)
        r_f_total        : float                  sum_i phi_f * r_f_i
        r_h_total        : float                  sum_i phi_h * r_h_i  (== N * phi_h * r_h)
        r_d_total        : float                  sum_i phi_d * r_d_i
        phi_f, phi_h, phi_d : float               weights actually used

    Notes
    -----
    Eq.17-18 (paper, project M3 settled 2026-04-21): mean-then-square for
    H / D regularizers. NOT mean-of-squares. See `multi_vsg_env._compute_rewards`
    historic comment + ode_paper_alignment_deviations.md.
    """
    if phi_f is None: phi_f = float(cfg.PHI_F)
    if phi_h is None: phi_h = float(cfg.PHI_H)
    if phi_d is None: phi_d = float(cfg.PHI_D)

    n = omega.shape[0]
    omega_hz = omega * _TO_HZ

    # Eq.17-18: mean-then-square (broadcast equally to every agent)
    ah_avg = float(np.mean(delta_H))
    ad_avg = float(np.mean(delta_D))
    r_h = -(ah_avg) ** 2
    r_d = -(ad_avg) ** 2

    rewards: dict[int, float] = {}
    r_f_per_agent: list[float] = []
    r_h_per_agent: list[float] = []
    r_d_per_agent: list[float] = []

    for i in range(n):
        # Eq.16: locally-weighted average over self + active neighbours.
        #
        # ISOLATION SEMANTICS (2026-05-02 review C-1, paper-intended):
        # When all neighbour links are failed (n_active stays at 1, just the
        # agent itself), omega_bar = omega_i_hz, so r_f = 0 below regardless
        # of how badly this agent diverges from the rest of the network. This
        # is paper Eq.15-16 by construction: distributed control sees only
        # locally-observable state — what cannot be observed cannot be
        # rewarded. Sec.IV-D ("communication failure") empirically shows
        # degraded synchrony — consistent with this signal vanishing for
        # isolated agents. See ode_paper_alignment_deviations.md note for
        # the gate that asserts this behaviour.
        omega_i_hz = float(omega_hz[i])
        sum_omega = omega_i_hz
        n_active = 1
        for j in comm_neighbors.get(i, []):
            if comm_eta.get((i, j), 0) == 1:
                sum_omega += float(omega_hz[j])
                n_active += 1
        omega_bar = sum_omega / n_active

        # Eq.15: synchrony penalty (self + each active neighbour deviation from local mean)
        r_f = -(omega_i_hz - omega_bar) ** 2
        for j in comm_neighbors.get(i, []):
            if comm_eta.get((i, j), 0) == 1:
                r_f -= (float(omega_hz[j]) - omega_bar) ** 2

        total = phi_f * r_f + phi_h * r_h + phi_d * r_d
        rewards[i] = total
        r_f_per_agent.append(phi_f * r_f)
        r_h_per_agent.append(phi_h * r_h)
        r_d_per_agent.append(phi_d * r_d)

    return {
        "rewards": rewards,
        "r_f_per_agent": r_f_per_agent,
        "r_h_per_agent": r_h_per_agent,
        "r_d_per_agent": r_d_per_agent,
        "r_f_total": float(sum(r_f_per_agent)),
        "r_h_total": float(sum(r_h_per_agent)),
        "r_d_total": float(sum(r_d_per_agent)),
        "phi_f": phi_f,
        "phi_h": phi_h,
        "phi_d": phi_d,
    }


# ---------------------------------------------------------------------------
# Evaluation reward (Sec.IV-C, global)
# ---------------------------------------------------------------------------


def evaluation_reward_global(freq_trace_hz: np.ndarray) -> float:
    """Episode-level frequency-synchrony reward (Sec.IV-C).

        R = -Σ_t Σ_i (f_i,t - <f_t>)^2,
        where <f_t> = (1/N) Σ_i f_i,t  is the cross-agent mean at time t.

    Parameters
    ----------
    freq_trace_hz : ndarray, shape (T+1, N)
        Per-step Hz frequency at each ESS for one episode.
        T = ``cfg.STEPS_PER_EPISODE``; rows 0..T inclusive (initial + T steps).
        axis=0 indexes time, axis=1 indexes agents.

    Returns
    -------
    float
        Single scalar; more negative = larger inter-agent disagreement.
        Returns 0.0 if all agents synchronised exactly at every step.

    Notes
    -----
    NOT used inside the training loop. Training reward in
    ``training_reward_local`` is local + has H/D regularisation; mixing
    them leaks global information to local actors and breaks paper-
    aligned MDP semantics (boundary doc §11).
    """
    arr = np.asarray(freq_trace_hz, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError(f"freq_trace_hz must be 2-D (T+1, N); got shape {arr.shape}")
    f_bar = arr.mean(axis=1, keepdims=True)
    return float(-np.sum((arr - f_bar) ** 2))
