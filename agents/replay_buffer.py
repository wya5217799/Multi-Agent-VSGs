"""
经验回放缓冲区 — 每个 agent 独立一个.
"""

import numpy as np
import torch


class ReplayBuffer:
    """循环 numpy 缓冲区, 支持随机批量采样."""

    def __init__(self, obs_dim, action_dim, capacity=10000):
        self.capacity = capacity
        self.ptr = 0
        self.size = 0

        self.obs = np.zeros((capacity, obs_dim), dtype=np.float32)
        self.actions = np.zeros((capacity, action_dim), dtype=np.float32)
        self.rewards = np.zeros(capacity, dtype=np.float32)
        self.next_obs = np.zeros((capacity, obs_dim), dtype=np.float32)
        self.dones = np.zeros(capacity, dtype=np.float32)

    def add(self, obs, action, reward, next_obs, done):
        self.obs[self.ptr] = obs
        self.actions[self.ptr] = action
        self.rewards[self.ptr] = reward
        self.next_obs[self.ptr] = next_obs
        self.dones[self.ptr] = float(done)

        self.ptr = (self.ptr + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)

    def sample(self, batch_size, device='cpu'):
        idx = np.random.randint(0, self.size, size=batch_size)
        return {
            'obs': torch.FloatTensor(self.obs[idx]).to(device),
            'actions': torch.FloatTensor(self.actions[idx]).to(device),
            'rewards': torch.FloatTensor(self.rewards[idx]).unsqueeze(1).to(device),
            'next_obs': torch.FloatTensor(self.next_obs[idx]).to(device),
            'dones': torch.FloatTensor(self.dones[idx]).unsqueeze(1).to(device),
        }

    def __len__(self):
        return self.size
