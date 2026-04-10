"""
多智能体管理器 — 协调 N 个独立 SAC 智能体.
"""

import os
import numpy as np
from agents.sac import SACAgent


class MultiAgentManager:
    """管理 N 个独立 SAC agent."""

    def __init__(self, n_agents, obs_dim, action_dim, hidden_sizes,
                 lr=3e-4, gamma=0.99, tau=0.005,
                 buffer_size=10000, batch_size=256, device='cpu'):
        self.n_agents = n_agents
        self.agents = []
        for _ in range(n_agents):
            agent = SACAgent(
                obs_dim=obs_dim,
                action_dim=action_dim,
                hidden_sizes=hidden_sizes,
                lr=lr, gamma=gamma, tau=tau,
                buffer_size=buffer_size,
                batch_size=batch_size,
                device=device,
            )
            self.agents.append(agent)

    def select_actions(self, obs_dict, deterministic=False):
        """
        Parameters
        ----------
        obs_dict : dict[int, np.ndarray]
        deterministic : bool

        Returns
        -------
        actions : dict[int, np.ndarray], 每个 shape (action_dim,)
        """
        actions = {}
        for i in range(self.n_agents):
            actions[i] = self.agents[i].select_action(obs_dict[i], deterministic)
        return actions

    def store_transitions(self, obs, actions, rewards, next_obs, done):
        """存储经验到各自的回放缓冲区."""
        for i in range(self.n_agents):
            self.agents[i].store_transition(
                obs[i], actions[i], rewards[i], next_obs[i], done
            )

    def update(self):
        """更新所有 agent. 返回各 agent 的 loss 字典列表."""
        losses = []
        for i in range(self.n_agents):
            loss = self.agents[i].update()
            losses.append(loss)
        return losses

    def clear_buffers(self):
        """清空所有 agent 的回放缓冲区 (Algorithm 1 line 16)."""
        for agent in self.agents:
            agent.buffer.clear()

    def save(self, dir_path):
        os.makedirs(dir_path, exist_ok=True)
        for i in range(self.n_agents):
            path = os.path.join(dir_path, f'agent_{i}.pt')
            self.agents[i].save(path)

    def load(self, dir_path):
        for i in range(self.n_agents):
            path = os.path.join(dir_path, f'agent_{i}.pt')
            self.agents[i].load(path)
