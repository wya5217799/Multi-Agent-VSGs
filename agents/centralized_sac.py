"""
集中式 SAC — 单个 agent 控制所有 N 个 VSG.

用于可扩展性实验 (Fig 14-15) 对比:
  - 分布式: N 个独立 SAC, 每个 obs_dim=7, action_dim=2
  - 集中式: 1 个 SAC, obs_dim=N*7, action_dim=N*2

论文核心结论: 集中式方法在 N 增大时网络维度增长导致训练不稳定,
而分布式方法因网络维度不随 N 增长, 具有更好的可扩展性.
"""

import numpy as np
from agents.sac import SACAgent


class CentralizedSACManager:
    """集中式 SAC — 拼接所有 agent 的观测/动作."""

    def __init__(self, n_agents, obs_dim_per_agent, action_dim_per_agent,
                 hidden_sizes, **kwargs):
        self.n_agents = n_agents
        self.obs_per = obs_dim_per_agent
        self.act_per = action_dim_per_agent
        self.total_obs = n_agents * obs_dim_per_agent
        self.total_act = n_agents * action_dim_per_agent

        # 单个 SAC agent, 输入/输出维度随 N 增长
        self.agent = SACAgent(
            obs_dim=self.total_obs,
            action_dim=self.total_act,
            hidden_sizes=hidden_sizes,
            **kwargs,
        )

    def select_actions(self, obs_dict, deterministic=False):
        """拼接所有观测 → 单 agent 决策 → 拆分为各 agent 动作."""
        # 拼接观测
        global_obs = np.concatenate([obs_dict[i] for i in range(self.n_agents)])
        # 集中式决策
        global_action = self.agent.select_action(global_obs, deterministic)
        # 拆分动作
        actions = {}
        for i in range(self.n_agents):
            start = i * self.act_per
            actions[i] = global_action[start:start + self.act_per]
        return actions

    def store_transitions(self, obs, actions, rewards, next_obs, done):
        """拼接后存入单个 buffer."""
        global_obs = np.concatenate([obs[i] for i in range(self.n_agents)])
        global_act = np.concatenate([actions[i] for i in range(self.n_agents)])
        global_next = np.concatenate([next_obs[i] for i in range(self.n_agents)])
        # 奖励取所有 agent 平均
        global_reward = np.mean([rewards[i] for i in range(self.n_agents)])
        self.agent.buffer.add(global_obs, global_act, global_reward, global_next, done)

    def update(self):
        return [self.agent.update()]

    def save(self, dir_path):
        import os
        os.makedirs(dir_path, exist_ok=True)
        self.agent.save(os.path.join(dir_path, 'centralized_agent.pt'))

    def load(self, dir_path):
        import os
        self.agent.load(os.path.join(dir_path, 'centralized_agent.pt'))
