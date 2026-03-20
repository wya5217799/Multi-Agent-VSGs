"""
SAC 神经网络 — Actor (高斯策略) + Critic (Double-Q)

论文 Section IV-A: 4 层全连接, 每层 128 单元
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Normal

LOG_STD_MIN = -20.0
LOG_STD_MAX = 2.0
EPS = 1e-6


def build_mlp(input_dim, hidden_sizes, output_dim):
    """构建多层感知机."""
    layers = []
    prev = input_dim
    for h in hidden_sizes:
        layers.append(nn.Linear(prev, h))
        layers.append(nn.ReLU())
        prev = h
    layers.append(nn.Linear(prev, output_dim))
    return nn.Sequential(*layers)


class GaussianActor(nn.Module):
    """
    高斯策略网络, tanh 压缩输出.

    obs → 4×128 hidden → (mean, log_std) → tanh(sample)
    """

    def __init__(self, obs_dim, action_dim, hidden_sizes):
        super().__init__()
        self.trunk = build_mlp(obs_dim, hidden_sizes, hidden_sizes[-1])
        # trunk 输出经过 ReLU, 但 build_mlp 最后一层没有激活
        # 重新构建: 共享隐藏层 + 分别输出 mean 和 log_std
        layers = []
        prev = obs_dim
        for h in hidden_sizes:
            layers.append(nn.Linear(prev, h))
            layers.append(nn.ReLU())
            prev = h
        self.net = nn.Sequential(*layers)
        self.mean_head = nn.Linear(prev, action_dim)
        self.log_std_head = nn.Linear(prev, action_dim)

    def forward(self, obs):
        h = self.net(obs)
        mean = self.mean_head(h)
        log_std = self.log_std_head(h)
        log_std = torch.clamp(log_std, LOG_STD_MIN, LOG_STD_MAX)
        return mean, log_std

    def sample(self, obs):
        """
        重参数化采样 + tanh 压缩.

        Returns
        -------
        action : Tensor, shape (..., action_dim), 范围 [-1, 1]
        log_prob : Tensor, shape (..., 1)
        """
        mean, log_std = self.forward(obs)
        std = log_std.exp()
        dist = Normal(mean, std)

        # 重参数化采样
        u = dist.rsample()
        action = torch.tanh(u)

        # log_prob 修正 tanh 压缩
        log_prob = dist.log_prob(u) - torch.log(1 - action.pow(2) + EPS)
        log_prob = log_prob.sum(dim=-1, keepdim=True)

        return action, log_prob

    def deterministic(self, obs):
        """确定性输出 (评估用)."""
        mean, _ = self.forward(obs)
        return torch.tanh(mean)


class QNetwork(nn.Module):
    """Q 值网络: (obs, action) → Q(s, a)."""

    def __init__(self, obs_dim, action_dim, hidden_sizes):
        super().__init__()
        self.net = build_mlp(obs_dim + action_dim, hidden_sizes, 1)

    def forward(self, obs, action):
        x = torch.cat([obs, action], dim=-1)
        return self.net(x)


class DoubleQCritic(nn.Module):
    """Double-Q Critic: 两个独立的 Q 网络."""

    def __init__(self, obs_dim, action_dim, hidden_sizes):
        super().__init__()
        self.q1 = QNetwork(obs_dim, action_dim, hidden_sizes)
        self.q2 = QNetwork(obs_dim, action_dim, hidden_sizes)

    def forward(self, obs, action):
        return self.q1(obs, action), self.q2(obs, action)
