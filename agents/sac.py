"""
SAC (Soft Actor-Critic) 智能体

每个 VSG 储能对应一个独立的 SAC agent.
- Actor: 高斯策略, tanh 压缩
- Critic: Double-Q
- 自动熵调节 (learnable α)
- 软目标网络更新
"""

import copy
import math
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.optim.lr_scheduler import CosineAnnealingLR

from agents.networks import GaussianActor, DoubleQCritic
from agents.replay_buffer import ReplayBuffer


class SACAgent:
    """单个 SAC 智能体."""

    def __init__(
        self,
        obs_dim,
        action_dim,
        hidden_sizes,
        lr=3e-4,
        gamma=0.99,
        tau=0.005,
        buffer_size=10000,
        batch_size=256,
        device='cpu',
        total_updates=100000,
        alpha_min=0.005,
        alpha_max=5.0,
    ):
        self.obs_dim = obs_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.tau = tau
        self.batch_size = batch_size
        self.device = device

        # ── 网络 ──
        self.actor = GaussianActor(obs_dim, action_dim, hidden_sizes).to(device)
        self.critic = DoubleQCritic(obs_dim, action_dim, hidden_sizes).to(device)
        self.critic_target = copy.deepcopy(self.critic).to(device)

        # 冻结目标网络梯度
        for p in self.critic_target.parameters():
            p.requires_grad = False

        # ── 优化器 ──
        self.actor_optimizer = optim.Adam(self.actor.parameters(), lr=lr)
        self.critic_optimizer = optim.Adam(self.critic.parameters(), lr=lr)

        # ── 自动熵调节 ──
        self.target_entropy = -float(action_dim)
        self.log_alpha = torch.zeros(1, requires_grad=True, device=device)
        self.alpha_optimizer = optim.Adam([self.log_alpha], lr=lr)
        self._log_alpha_min = math.log(alpha_min)
        self._log_alpha_max = math.log(alpha_max)

        # ── 经验回放 ──
        self.buffer = ReplayBuffer(obs_dim, action_dim, capacity=buffer_size)

        # ── LR 衰减 (cosine annealing: lr → lr*0.1) ──
        self.actor_scheduler = CosineAnnealingLR(
            self.actor_optimizer, T_max=total_updates, eta_min=lr * 0.1)
        self.critic_scheduler = CosineAnnealingLR(
            self.critic_optimizer, T_max=total_updates, eta_min=lr * 0.1)

        # ── 梯度裁剪 ──
        self.max_grad_norm = 1.0

    @property
    def alpha(self):
        return self.log_alpha.exp()

    def select_action(self, obs, deterministic=False):
        """
        选择动作.

        Parameters
        ----------
        obs : np.ndarray, shape (obs_dim,)
        deterministic : bool

        Returns
        -------
        action : np.ndarray, shape (action_dim,), 范围 [-1, 1]
        """
        obs_t = torch.FloatTensor(obs).unsqueeze(0).to(self.device)
        with torch.no_grad():
            if deterministic:
                action = self.actor.deterministic(obs_t)
            else:
                action, _ = self.actor.sample(obs_t)
        return action.cpu().numpy().flatten()

    def store_transition(self, obs, action, reward, next_obs, done):
        self.buffer.add(obs, action, reward, next_obs, done)

    def update(self):
        """执行一步 SAC 更新. 返回 loss 字典."""
        if len(self.buffer) < self.batch_size:
            return None

        batch = self.buffer.sample(self.batch_size, self.device)
        obs = batch['obs']
        actions = batch['actions']
        rewards = batch['rewards']
        next_obs = batch['next_obs']
        dones = batch['dones']

        # ═══ Critic 更新 ═══
        with torch.no_grad():
            next_actions, next_log_prob = self.actor.sample(next_obs)
            q1_target, q2_target = self.critic_target(next_obs, next_actions)
            q_target = torch.min(q1_target, q2_target)
            y = rewards + self.gamma * (1 - dones) * (q_target - self.alpha * next_log_prob)

        q1, q2 = self.critic(obs, actions)
        critic_loss = F.mse_loss(q1, y) + F.mse_loss(q2, y)

        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        nn.utils.clip_grad_norm_(self.critic.parameters(), self.max_grad_norm)
        self.critic_optimizer.step()

        # ═══ Actor 更新 ═══
        new_actions, log_prob = self.actor.sample(obs)
        q1_new, q2_new = self.critic(obs, new_actions)
        q_new = torch.min(q1_new, q2_new)
        actor_loss = (self.alpha.detach() * log_prob - q_new).mean()

        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        nn.utils.clip_grad_norm_(self.actor.parameters(), self.max_grad_norm)
        self.actor_optimizer.step()

        # ═══ Alpha 更新 ═══
        alpha_loss = -(self.log_alpha * (log_prob.detach() + self.target_entropy)).mean()

        self.alpha_optimizer.zero_grad()
        alpha_loss.backward()
        nn.utils.clip_grad_norm_([self.log_alpha], self.max_grad_norm)
        self.alpha_optimizer.step()
        with torch.no_grad():
            self.log_alpha.data.clamp_(self._log_alpha_min, self._log_alpha_max)

        # ═══ 软目标更新 ═══
        self._soft_update()

        # ═══ LR 衰减 ═══
        self.actor_scheduler.step()
        self.critic_scheduler.step()

        return {
            'critic_loss': critic_loss.item(),
            'actor_loss': actor_loss.item(),
            'alpha_loss': alpha_loss.item(),
            'alpha': self.alpha.item(),
        }

    def _soft_update(self):
        """目标网络软更新: θ_tgt ← τ·θ + (1-τ)·θ_tgt."""
        for p, p_tgt in zip(self.critic.parameters(), self.critic_target.parameters()):
            p_tgt.data.mul_(1 - self.tau).add_(self.tau * p.data)

    def save(self, path, metadata: dict | None = None):
        torch.save({
            'actor': self.actor.state_dict(),
            'critic': self.critic.state_dict(),
            'critic_target': self.critic_target.state_dict(),
            'log_alpha': self.log_alpha.data,
            'actor_opt': self.actor_optimizer.state_dict(),
            'critic_opt': self.critic_optimizer.state_dict(),
            'alpha_opt': self.alpha_optimizer.state_dict(),
            'metadata': metadata or {},
        }, path)

    def load(self, path) -> dict:
        """加载 checkpoint，返回 metadata dict（无 metadata 时返回 {}）。"""
        ckpt = torch.load(path, map_location=self.device, weights_only=False)
        self.actor.load_state_dict(ckpt['actor'])
        self.critic.load_state_dict(ckpt['critic'])
        self.critic_target.load_state_dict(ckpt['critic_target'])
        self.log_alpha.data = ckpt['log_alpha']
        self.actor_optimizer.load_state_dict(ckpt['actor_opt'])
        self.critic_optimizer.load_state_dict(ckpt['critic_opt'])
        self.alpha_optimizer.load_state_dict(ckpt['alpha_opt'])
        return ckpt.get('metadata', {})
