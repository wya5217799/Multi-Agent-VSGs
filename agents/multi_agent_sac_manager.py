"""G6 closure — MultiAgentSACManager.

4 independent SACAgents per paper Algorithm 1 ("each agent has its own actor
π_φ_i and critic Q_θ_i"). Wraps `env.simulink.sac_agent_standalone.SACAgent`
4× and exposes the same external interface as the shared-weights variant so
`scenarios/kundur/train_simulink.py` and `evaluation/paper_eval.py` can plug
in via a single CLI flag.

Hard isolation principles:
- Each agent has its own actor, critic (twin Q + target), log_alpha, all 3
  optimizers, replay buffer, and total_steps counter. NO weight sharing.
- store_multi_transitions distributes per-agent transitions to per-agent
  buffers — agent i never sees agent j's experience.
- update() runs SAC step independently for each agent; returns mean loss /
  alpha across agents for compatibility with the existing logging.
- save/load uses a single .pt file containing a list of per-agent state
  bundles + a 'multi_agent' marker so paper_eval can auto-detect.

Boundaries (G6 isolated experiment):
- No env / reward / PHI / disturbance / Simulink / manifest / paper_eval
  semantic edits.
- This module is purely an orchestrator over SACAgent instances.
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np
import torch

from env.simulink.sac_agent_standalone import SACAgent


class _BufferLengthView:
    """Compatibility shim: train_simulink.py logs `len(agent.buffer)`.

    Returns the **min** size across per-agent buffers so the SAC warmup gate
    (`if len(buffer) < warmup_steps: return {}`) is honored only when EVERY
    agent has enough samples. Mean would let an early agent train while
    others are still in warmup.
    """

    def __init__(self, agents: list[SACAgent]):
        self._agents = agents

    def __len__(self) -> int:
        if not self._agents:
            return 0
        return min(len(a.buffer) for a in self._agents)


class MultiAgentSACManager:
    """4 independent SACAgents per paper Algorithm 1."""

    def __init__(
        self,
        n_agents: int,
        obs_dim: int,
        act_dim: int,
        hidden_sizes: tuple = (128, 128, 128, 128),
        lr: float = 3e-4,
        gamma: float = 0.99,
        tau: float = 0.005,
        buffer_size: int = 10000,
        batch_size: int = 256,
        warmup_steps: int = 2000,
        auto_entropy: bool = True,
        reward_scale: float = 1e-3,
        alpha_max: float = 5.0,
        alpha_min: float = 0.05,
        device: str | None = None,
        per_agent_buffer_size: int | None = None,
        per_agent_warmup_steps: int | None = None,
    ):
        self.n_agents = int(n_agents)
        self.obs_dim = int(obs_dim)
        self.act_dim = int(act_dim)
        self.warmup_steps = int(warmup_steps)
        self.batch_size = int(batch_size)

        # Construct N independent agents — each owns full SAC state.
        #
        # Default split: per_agent_warmup = warmup_steps / N, per_agent_buffer
        # = buffer_size / N. This matches "total buffer = paper Table I 10000"
        # interpretation. But G6 500-ep extension showed ckpt-trajectory
        # severe degradation past ep 50 — diagnosis: per-agent buffer of 2500
        # caps too early (50 ep × 50 step/agent/ep = 2500). Eviction kicks in
        # exactly at ep 50, after which only the most-recent 50 ep are
        # represented per agent. Independent-buffer experiment (2026-04-27)
        # tests `per_agent_buffer_size=10000` so each agent has its own full
        # 10k capacity (total 40k), delaying eviction to ep ~200.
        if per_agent_warmup_steps is not None:
            per_agent_warmup = max(int(per_agent_warmup_steps), 1)
        else:
            per_agent_warmup = max(int(round(warmup_steps / n_agents)), 1)
        if per_agent_buffer_size is not None:
            per_agent_buffer = max(int(per_agent_buffer_size), self.batch_size + 1)
        else:
            per_agent_buffer = max(int(round(buffer_size / n_agents)), self.batch_size + 1)
        self.per_agent_buffer_size = per_agent_buffer
        self.per_agent_warmup_steps = per_agent_warmup

        self.agents: list[SACAgent] = []
        for _ in range(self.n_agents):
            self.agents.append(SACAgent(
                obs_dim=obs_dim,
                act_dim=act_dim,
                hidden_sizes=hidden_sizes,
                lr=lr,
                gamma=gamma,
                tau=tau,
                buffer_size=per_agent_buffer,
                batch_size=batch_size,
                warmup_steps=per_agent_warmup,
                auto_entropy=auto_entropy,
                reward_scale=reward_scale,
                alpha_max=alpha_max,
                alpha_min=alpha_min,
                device=device,
            ))
        self._buffer_view = _BufferLengthView(self.agents)
        # SACAgent uses .alpha as a runtime attribute (not a property).
        # We expose `.alpha` as a computed property for read-only consumers.

    # ------------------------------------------------------------------
    # Action selection
    # ------------------------------------------------------------------

    def select_action(self, obs, deterministic: bool = False) -> np.ndarray:
        """Single-agent action — deferred to agent[0] for completeness; the
        normal multi-agent path is `select_actions_multi` so this single-
        agent version is rarely used. Provided for API compatibility.
        """
        return self.agents[0].select_action(obs, deterministic=deterministic)

    def select_actions_multi(
        self, obs_all: np.ndarray, deterministic: bool = False
    ) -> np.ndarray:
        """Per-agent action selection.

        Args:
            obs_all: shape (n_agents, obs_dim)
            deterministic: True for evaluation
        Returns:
            actions: shape (n_agents, act_dim)
        """
        n = obs_all.shape[0]
        if n != self.n_agents:
            raise ValueError(
                f"obs_all has {n} agents, manager expects {self.n_agents}"
            )
        actions = np.zeros((n, self.act_dim), dtype=np.float32)
        for i in range(n):
            actions[i] = self.agents[i].select_action(obs_all[i], deterministic)
        return actions

    # ------------------------------------------------------------------
    # Replay buffer
    # ------------------------------------------------------------------

    def store_transition(self, obs, action, reward, next_obs, done) -> None:
        """Single-agent store — defers to agent[0]. Rarely used directly;
        normal path is `store_multi_transitions`.
        """
        self.agents[0].store_transition(obs, action, reward, next_obs, done)

    def store_multi_transitions(
        self,
        obs_all: np.ndarray,
        actions_all: np.ndarray,
        rewards_all: np.ndarray,
        next_obs_all: np.ndarray,
        dones_all,
    ) -> None:
        """Distribute per-agent transitions to per-agent buffers."""
        for i in range(self.n_agents):
            done = dones_all if isinstance(dones_all, (bool, int, float)) else dones_all[i]
            self.agents[i].store_transition(
                obs_all[i], actions_all[i], rewards_all[i], next_obs_all[i], float(done)
            )

    @property
    def buffer(self):
        """Return a length-providing view; train_simulink only uses `len()`."""
        return self._buffer_view

    @property
    def total_steps(self) -> int:
        return sum(a.total_steps for a in self.agents)

    # ------------------------------------------------------------------
    # SAC update
    # ------------------------------------------------------------------

    def update(self) -> dict:
        """Per-agent SAC update; returns aggregated loss dict."""
        per_agent_infos: list[dict] = []
        for i in range(self.n_agents):
            info = self.agents[i].update()
            if info:
                per_agent_infos.append(info)
        if not per_agent_infos:
            return {}
        # Mean across agents for compatibility with shared-weights logging.
        critic_losses = [x["critic_loss"] for x in per_agent_infos if "critic_loss" in x]
        policy_losses = [x["policy_loss"] for x in per_agent_infos if "policy_loss" in x]
        alphas = [x["alpha"] for x in per_agent_infos if "alpha" in x]
        out = {
            "critic_loss": float(np.mean(critic_losses)) if critic_losses else 0.0,
            "policy_loss": float(np.mean(policy_losses)) if policy_losses else 0.0,
            "alpha": float(np.mean(alphas)) if alphas else 0.0,
            "buffer_size": int(len(self.buffer)),
            "per_agent": per_agent_infos,
        }
        return out

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def alpha(self) -> float:
        """Mean α across agents — compatibility with SACAgent.alpha (scalar)."""
        return float(np.mean([a.alpha for a in self.agents]))

    # ------------------------------------------------------------------
    # Save / load — single-file, multi-agent format
    # ------------------------------------------------------------------

    def save(
        self, path: str, metadata: dict[str, Any] | None = None, save_buffer: bool = False
    ) -> None:
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        per_agent_state = []
        for a in self.agents:
            per_agent_state.append({
                "policy": a.policy.state_dict(),
                "critic": a.critic.state_dict(),
                "critic_target": a.critic_target.state_dict(),
                "policy_optim": a.policy_optim.state_dict(),
                "critic_optim": a.critic_optim.state_dict(),
                "log_alpha": a.log_alpha.detach().cpu() if a.auto_entropy else None,
                "alpha_optim": a.alpha_optim.state_dict() if a.auto_entropy else None,
                "total_steps": int(a.total_steps),
            })
        bundle = {
            "multi_agent": True,
            "n_agents": self.n_agents,
            "obs_dim": self.obs_dim,
            "act_dim": self.act_dim,
            "per_agent": per_agent_state,
            "_metadata": metadata or {},
        }
        torch.save(bundle, path)
        print(f"[MultiAgentSACManager] Checkpoint saved: {path} (n_agents={self.n_agents})")

    def load(self, path: str) -> dict:
        ckpt = torch.load(path, map_location="cpu", weights_only=False)
        if not ckpt.get("multi_agent"):
            raise ValueError(
                f"checkpoint at {path} is not a multi-agent bundle "
                f"(missing 'multi_agent' marker). Use SACAgent.load() instead."
            )
        n = int(ckpt.get("n_agents", 0))
        if n != self.n_agents:
            raise ValueError(
                f"checkpoint n_agents={n} != manager n_agents={self.n_agents}"
            )
        per = ckpt["per_agent"]
        for i in range(self.n_agents):
            a = self.agents[i]
            ps = per[i]
            a.policy.load_state_dict(ps["policy"])
            a.critic.load_state_dict(ps["critic"])
            a.critic_target.load_state_dict(ps["critic_target"])
            a.policy_optim.load_state_dict(ps["policy_optim"])
            a.critic_optim.load_state_dict(ps["critic_optim"])
            if a.auto_entropy and ps.get("log_alpha") is not None:
                a.log_alpha.data.copy_(ps["log_alpha"])
                a.alpha_optim.load_state_dict(ps["alpha_optim"])
                a.alpha = a.log_alpha.exp().item()
            a.total_steps = int(ps.get("total_steps", 0))
        meta = ckpt.get("_metadata", {})
        print(
            f"[MultiAgentSACManager] Checkpoint loaded: {path} "
            f"(n_agents={n}, total_steps={[a.total_steps for a in self.agents]})"
        )
        return meta


__all__ = ["MultiAgentSACManager"]
