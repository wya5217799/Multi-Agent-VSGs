"""Policy loader — discovery > declaration.

Reads N_AGENTS / OBS_DIM from env class, agent ckpts from given dir.
Supports `_best.pt` and `_final.pt` selection.

Backends
--------
andes    (default): per-file layout agent_{i}_{kind}.pt, agents.sac.SACAgent
simulink           : single bundle best.pt/final.pt with per_agent list schema,
                     env.simulink.sac_agent_standalone.SACAgent
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import torch

import config as cfg

# Lazy imports — avoid loading ANDES (requires andes package) unless actually needed.
_AndesSACAgent = None
_AndesMultiVSGEnv = None
_SimSACAgent = None


def _get_andes_sac_agent():
    global _AndesSACAgent
    if _AndesSACAgent is None:
        from agents.sac import SACAgent as _SA
        _AndesSACAgent = _SA
    return _AndesSACAgent


def _get_andes_env_class():
    global _AndesMultiVSGEnv
    if _AndesMultiVSGEnv is None:
        from env.andes.andes_vsg_env import AndesMultiVSGEnv as _E
        _AndesMultiVSGEnv = _E
    return _AndesMultiVSGEnv


def _get_sim_sac_agent():
    global _SimSACAgent
    if _SimSACAgent is None:
        from env.simulink.sac_agent_standalone import SACAgent as _SA
        _SimSACAgent = _SA
    return _SimSACAgent


# N_AGENTS / OBS_DIM / action_dim are identical across both backends; use contract directly
# to avoid triggering ANDES import chain.
def _get_dims():
    from scenarios.contract import KUNDUR as _CONTRACT
    return _CONTRACT.n_agents, _CONTRACT.obs_dim, _CONTRACT.act_dim


@dataclass
class LoadedPolicy:
    agents: list                 # list[SACAgent]
    n_agents: int
    obs_dim: int
    action_dim: int
    ckpt_dir: str
    ckpt_kind: str               # 'best' or 'final'
    backend: str = "andes"       # 'andes' | 'simulink'


def load(ckpt_dir: str, ckpt_kind: str = "final", backend: str = "andes") -> LoadedPolicy:
    """Load N agents from ckpt_dir, kind ∈ {best, final}.

    N_AGENTS / OBS_DIM discovered from env class constants (identical across backends).

    Parameters
    ----------
    ckpt_dir : str
        Directory containing checkpoints.
    ckpt_kind : str
        'best' or 'final'.
    backend : str
        'andes' (default) — per-file layout; 'simulink' — single bundle per_agent schema.
    """
    if ckpt_kind not in ("best", "final"):
        raise ValueError(f"ckpt_kind must be 'best' or 'final', got {ckpt_kind!r}")
    if backend not in ("andes", "simulink"):
        raise ValueError(f"backend must be 'andes' or 'simulink', got {backend!r}")
    if not os.path.isdir(ckpt_dir):
        raise FileNotFoundError(ckpt_dir)

    # N_AGENTS and OBS_DIM are identical across both backends (both 4 and 7).
    # Read from contract to avoid triggering ANDES import chain for simulink probes.
    N, obs_dim, action_dim = _get_dims()

    if backend == "andes":
        # ANDES env class may augment obs_dim at runtime — check the class attribute.
        AndesEnv = _get_andes_env_class()
        if getattr(AndesEnv, "INCLUDE_OWN_ACTION_OBS", False):
            obs_dim += getattr(AndesEnv, "OBS_DIM_AUGMENT_OWN_ACTION", 0)
        return _load_andes(ckpt_dir, ckpt_kind, N, obs_dim, action_dim)
    else:
        return _load_simulink(ckpt_dir, ckpt_kind, N, obs_dim, action_dim)


def _load_andes(ckpt_dir: str, ckpt_kind: str, N: int, obs_dim: int, action_dim: int) -> LoadedPolicy:
    """Load per-file ANDES checkpoints using agents.sac.SACAgent."""
    AndesSACAgent = _get_andes_sac_agent()
    agents = []
    for i in range(N):
        agent = AndesSACAgent(
            obs_dim=obs_dim, action_dim=action_dim,
            hidden_sizes=cfg.HIDDEN_SIZES,
            lr=cfg.LR, gamma=cfg.GAMMA, tau=cfg.TAU_SOFT,
            buffer_size=cfg.BUFFER_SIZE, batch_size=cfg.BATCH_SIZE,
        )
        ckpt = os.path.join(ckpt_dir, f"agent_{i}_{ckpt_kind}.pt")
        if not os.path.exists(ckpt):
            raise FileNotFoundError(f"Missing ckpt: {ckpt}")
        agent.load(ckpt)
        agents.append(agent)
    return LoadedPolicy(
        agents=agents, n_agents=N, obs_dim=obs_dim, action_dim=action_dim,
        ckpt_dir=ckpt_dir, ckpt_kind=ckpt_kind, backend="andes",
    )


def _load_simulink(ckpt_dir: str, ckpt_kind: str, N: int, obs_dim: int, action_dim: int) -> LoadedPolicy:
    """Load Simulink bundle checkpoint using sac_agent_standalone.SACAgent.

    Supports two schemas:
    - Bundle (2026-05-03 screen format): single file with
      {multi_agent: True, n_agents, obs_dim, act_dim, per_agent: list[...]}
    - Per-agent standalone: individual policy/critic dicts without per_agent wrapper.
    """
    SACAgent = _get_sim_sac_agent()
    bundle_path = os.path.join(ckpt_dir, f"{ckpt_kind}.pt")
    if not os.path.exists(bundle_path):
        raise FileNotFoundError(f"Missing Simulink ckpt bundle: {bundle_path}")

    raw = torch.load(bundle_path, map_location="cpu", weights_only=False)

    if "per_agent" in raw:
        # Bundle schema: load each agent from per_agent[i] sub-dict
        per_agent_list = raw["per_agent"]
        if len(per_agent_list) < N:
            raise ValueError(
                f"Bundle has {len(per_agent_list)} agents, expected {N}"
            )
        agents = []
        for i in range(N):
            agent = SACAgent(obs_dim=obs_dim, act_dim=action_dim)
            sub = per_agent_list[i]
            agent.policy.load_state_dict(sub["policy"])
            agent.critic.load_state_dict(sub["critic"])
            agent.critic_target.load_state_dict(sub["critic_target"])
            agents.append(agent)
    else:
        # Single-agent standalone schema: all agents share the same weights
        agent_proto = SACAgent(obs_dim=obs_dim, act_dim=action_dim)
        agent_proto.policy.load_state_dict(raw["policy"])
        agent_proto.critic.load_state_dict(raw["critic"])
        agent_proto.critic_target.load_state_dict(raw["critic_target"])
        # Replicate for N agents (parameter-sharing: identical weights)
        agents = [agent_proto] * N

    return LoadedPolicy(
        agents=agents, n_agents=N, obs_dim=obs_dim, action_dim=action_dim,
        ckpt_dir=ckpt_dir, ckpt_kind=ckpt_kind, backend="simulink",
    )
