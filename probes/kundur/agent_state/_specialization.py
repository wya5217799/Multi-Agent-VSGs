"""Phase A1 — multi-agent specialization.

Question: do the 4 SAC agents converge to distinct policies, or homogenize?

Method: feed each agent the SAME N_OBS synthetic observations, collect
deterministic actions. Compute pairwise similarity (cosine on action vectors).
Plus a rollout-based correlation matrix.

Outputs:
- pairwise_action_cos_matrix: 4×4
- mean_offdiag_cos: scalar
- rollout_action_corr_matrix: 4×4 (per-step actions during 1 rollout)
- per_agent_action_stats: μ, σ per dim
"""
from __future__ import annotations

import numpy as np

from probes.kundur.agent_state._loader import LoadedPolicy
from probes.kundur.agent_state.probe_config import ProbeThresholds


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _generate_synthetic_obs(n: int, obs_dim: int, rng: np.random.Generator) -> np.ndarray:
    """Plausible obs samples in observed normalized range.

    Project obs already normalized (P/2, dω/3, dω̇·scale/5, neighbor scaled).
    Sample uniform in [-1, 1] which covers the observed envelope.
    """
    return rng.uniform(-1.0, 1.0, size=(n, obs_dim)).astype(np.float32)


def run(policy: LoadedPolicy, thresholds: ProbeThresholds, seed: int = 12345) -> dict:
    """Phase A1 entry. Returns snapshot section."""
    rng = np.random.default_rng(seed)
    N = policy.n_agents
    n_samples = thresholds.a1_n_obs_samples

    obs_samples = _generate_synthetic_obs(n_samples, policy.obs_dim, rng)

    # For each agent, deterministic action on each obs sample
    actions = np.zeros((N, n_samples, policy.action_dim), dtype=np.float32)
    for i in range(N):
        for k in range(n_samples):
            actions[i, k] = policy.agents[i].select_action(obs_samples[k], deterministic=True)

    # Pairwise cosine similarity between agents (concatenate action vectors)
    flat = actions.reshape(N, -1)
    cos_mat = np.zeros((N, N), dtype=np.float32)
    for i in range(N):
        for j in range(N):
            cos_mat[i, j] = _cosine(flat[i], flat[j])
    offdiag = cos_mat[~np.eye(N, dtype=bool)]
    mean_offdiag = float(np.mean(offdiag))
    max_offdiag = float(np.max(offdiag))
    min_offdiag = float(np.min(offdiag))

    # Per-agent action stats (over the synthetic samples)
    per_agent_stats = []
    for i in range(N):
        per_agent_stats.append({
            "agent": i,
            "a0_mean": float(np.mean(actions[i, :, 0])),
            "a0_std": float(np.std(actions[i, :, 0])),
            "a1_mean": float(np.mean(actions[i, :, 1])),
            "a1_std": float(np.std(actions[i, :, 1])),
        })

    # Verdict shape (logic in _verdict.py)
    return {
        "n_agents": N,
        "n_obs_samples": n_samples,
        "pairwise_cos_matrix": cos_mat.tolist(),
        "offdiag_cos_mean": mean_offdiag,
        "offdiag_cos_max": max_offdiag,
        "offdiag_cos_min": min_offdiag,
        "per_agent_action_stats": per_agent_stats,
    }
