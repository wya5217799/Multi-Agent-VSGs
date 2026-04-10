"""
SAC (Soft Actor-Critic) Agent for Multi-Agent VSG Control.

Each ESS agent has its own SAC networks (decentralized execution).
Parameter sharing: all agents share the same network weights (CTDE paradigm).
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from collections import deque
import random
import os


# ===== Neural Network Architectures =====

class MLP(nn.Module):
    """4-layer fully connected network (128×4)."""

    def __init__(self, input_dim: int, output_dim: int, hidden_sizes=(128, 128, 128, 128)):
        super().__init__()
        layers = []
        prev_dim = input_dim
        for h in hidden_sizes:
            layers.append(nn.Linear(prev_dim, h))
            layers.append(nn.ReLU())
            prev_dim = h
        layers.append(nn.Linear(prev_dim, output_dim))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


class GaussianPolicy(nn.Module):
    """SAC policy network: outputs mean and log_std for Gaussian distribution."""

    LOG_STD_MIN = -20
    LOG_STD_MAX = 2

    def __init__(self, obs_dim: int, act_dim: int, hidden_sizes=(128, 128, 128, 128)):
        super().__init__()
        layers = []
        prev = obs_dim
        for h in hidden_sizes:
            layers.append(nn.Linear(prev, h))
            layers.append(nn.ReLU())
            prev = h
        self.features = nn.Sequential(*layers)
        self.mean_head = nn.Linear(prev, act_dim)
        self.log_std_head = nn.Linear(prev, act_dim)

    def forward(self, obs):
        features = self.features(obs)
        mean = self.mean_head(features)
        log_std = self.log_std_head(features)
        log_std = torch.clamp(log_std, self.LOG_STD_MIN, self.LOG_STD_MAX)
        return mean, log_std

    def sample(self, obs):
        """Sample action with reparameterization trick."""
        mean, log_std = self.forward(obs)
        std = log_std.exp()
        normal = torch.randn_like(mean)
        x_t = mean + std * normal  # reparameterization
        action = torch.tanh(x_t)   # squash to [-1, 1]

        # Log probability with correction for tanh squashing
        log_prob = -0.5 * (((x_t - mean) / (std + 1e-6)) ** 2 + 2 * log_std + np.log(2 * np.pi))
        log_prob = log_prob.sum(dim=-1, keepdim=True)
        log_prob -= (2 * (np.log(2) - x_t - F.softplus(-2 * x_t))).sum(dim=-1, keepdim=True)

        return action, log_prob, mean

    def deterministic(self, obs):
        """Deterministic action (for evaluation)."""
        mean, _ = self.forward(obs)
        return torch.tanh(mean)


class TwinQNetwork(nn.Module):
    """Twin Q-networks for SAC (clipped double Q)."""

    def __init__(self, obs_dim: int, act_dim: int, hidden_sizes=(128, 128, 128, 128)):
        super().__init__()
        self.q1 = MLP(obs_dim + act_dim, 1, hidden_sizes)
        self.q2 = MLP(obs_dim + act_dim, 1, hidden_sizes)

    def forward(self, obs, action):
        x = torch.cat([obs, action], dim=-1)
        return self.q1(x), self.q2(x)

    def q1_forward(self, obs, action):
        x = torch.cat([obs, action], dim=-1)
        return self.q1(x)


# ===== Replay Buffer =====

class ReplayBuffer:
    """Experience replay buffer for SAC."""

    def __init__(self, capacity: int = 2500):
        self.buffer = deque(maxlen=capacity)

    def push(self, obs, action, reward, next_obs, done):
        self.buffer.append((obs, action, reward, next_obs, done))

    def sample(self, batch_size: int = 32):
        batch = random.sample(self.buffer, min(batch_size, len(self.buffer)))
        obs, actions, rewards, next_obs, dones = zip(*batch)
        return (
            np.array(obs, dtype=np.float32),
            np.array(actions, dtype=np.float32),
            np.array(rewards, dtype=np.float32).reshape(-1, 1),
            np.array(next_obs, dtype=np.float32),
            np.array(dones, dtype=np.float32).reshape(-1, 1),
        )

    def __len__(self):
        return len(self.buffer)

    def clear(self):
        self.buffer.clear()


# ===== SAC Agent =====

class SACAgent:
    """
    Soft Actor-Critic agent for VSG parameter control.

    Shared network weights across all 8 ESS agents (parameter sharing).
    """

    def __init__(
        self,
        obs_dim: int = 7,
        act_dim: int = 2,
        hidden_sizes: tuple = (128, 128, 128, 128),
        lr: float = 3e-4,
        gamma: float = 0.99,
        tau: float = 0.005,
        buffer_size: int = 100000,
        batch_size: int = 256,
        warmup_steps: int = 2000,
        auto_entropy: bool = True,
        reward_scale: float = 1e-3,
        alpha_max: float = 5.0,
        alpha_min: float = 0.005,
        device: str = None,
    ):
        self.obs_dim = obs_dim
        self.act_dim = act_dim
        self.gamma = gamma
        self.tau = tau
        self.batch_size = batch_size
        self.warmup_steps = warmup_steps
        self.auto_entropy = auto_entropy
        self.reward_scale = reward_scale
        self.alpha_max = alpha_max
        self.alpha_min = alpha_min

        # Device
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        # Networks
        self.policy = GaussianPolicy(obs_dim, act_dim, hidden_sizes).to(self.device)
        self.critic = TwinQNetwork(obs_dim, act_dim, hidden_sizes).to(self.device)
        self.critic_target = TwinQNetwork(obs_dim, act_dim, hidden_sizes).to(self.device)
        self.critic_target.load_state_dict(self.critic.state_dict())

        # Optimizers
        self.policy_optim = optim.Adam(self.policy.parameters(), lr=lr)
        self.critic_optim = optim.Adam(self.critic.parameters(), lr=lr)

        # Automatic entropy tuning
        if auto_entropy:
            self.target_entropy = -act_dim
            self.log_alpha = torch.zeros(1, requires_grad=True, device=self.device)
            self.alpha_optim = optim.Adam([self.log_alpha], lr=lr)
            self.alpha = self.log_alpha.exp().item()
        else:
            self.alpha = 0.2

        # Replay buffer
        self.buffer = ReplayBuffer(buffer_size)
        self.total_steps = 0

        # Gradient clipping bound (applied to all three optimizers)
        self.max_grad_norm = 1.0

    def select_action(self, obs: np.ndarray, deterministic: bool = False) -> np.ndarray:
        """
        Select action for a single agent observation.

        Args:
            obs: shape (obs_dim,)
            deterministic: if True, use mean action

        Returns:
            action: shape (act_dim,), in [-1, 1]
        """
        with torch.no_grad():
            obs_t = torch.FloatTensor(obs).unsqueeze(0).to(self.device)
            if deterministic:
                action = self.policy.deterministic(obs_t)
            else:
                action, _, _ = self.policy.sample(obs_t)
            return action.cpu().numpy().flatten()

    def select_actions_multi(
        self, obs_all: np.ndarray, deterministic: bool = False
    ) -> np.ndarray:
        """
        Select actions for all agents at once.

        Args:
            obs_all: shape (n_agents, obs_dim)
            deterministic: if True, use mean action

        Returns:
            actions: shape (n_agents, act_dim)
        """
        n_agents = obs_all.shape[0]
        actions = np.zeros((n_agents, self.act_dim), dtype=np.float32)
        for i in range(n_agents):
            actions[i] = self.select_action(obs_all[i], deterministic)
        return actions

    def store_transition(self, obs, action, reward, next_obs, done):
        """Store single transition (per agent)."""
        self.buffer.push(obs, action, reward, next_obs, done)
        self.total_steps += 1

    def store_multi_transitions(self, obs_all, actions_all, rewards_all, next_obs_all, dones_all):
        """Store transitions for all agents."""
        n_agents = obs_all.shape[0]
        for i in range(n_agents):
            done = dones_all if isinstance(dones_all, (bool, int, float)) else dones_all[i]
            self.store_transition(
                obs_all[i], actions_all[i], rewards_all[i], next_obs_all[i], float(done)
            )

    def update(self) -> dict:
        """
        Perform one SAC update step.

        Returns:
            dict with loss values for logging
        """
        if len(self.buffer) < self.warmup_steps:
            return {}

        # Sample batch
        obs_b, act_b, rew_b, next_obs_b, done_b = self.buffer.sample(self.batch_size)
        obs_t = torch.FloatTensor(obs_b).to(self.device)
        act_t = torch.FloatTensor(act_b).to(self.device)
        rew_t = torch.FloatTensor(rew_b).to(self.device)
        next_obs_t = torch.FloatTensor(next_obs_b).to(self.device)
        done_t = torch.FloatTensor(done_b).to(self.device)

        # Scale rewards to stabilize Q-value magnitudes
        rew_t = rew_t * self.reward_scale

        # ---- Critic update ----
        with torch.no_grad():
            next_act, next_log_prob, _ = self.policy.sample(next_obs_t)
            q1_target, q2_target = self.critic_target(next_obs_t, next_act)
            q_target = torch.min(q1_target, q2_target) - self.alpha * next_log_prob
            target_q = rew_t + (1 - done_t) * self.gamma * q_target

        q1_pred, q2_pred = self.critic(obs_t, act_t)
        critic_loss = F.mse_loss(q1_pred, target_q) + F.mse_loss(q2_pred, target_q)

        self.critic_optim.zero_grad()
        critic_loss.backward()
        nn.utils.clip_grad_norm_(self.critic.parameters(), self.max_grad_norm)
        self.critic_optim.step()

        # ---- Policy update ----
        new_act, log_prob, _ = self.policy.sample(obs_t)
        q1_new, q2_new = self.critic(obs_t, new_act)
        q_new = torch.min(q1_new, q2_new)
        policy_loss = (self.alpha * log_prob - q_new).mean()

        self.policy_optim.zero_grad()
        policy_loss.backward()
        nn.utils.clip_grad_norm_(self.policy.parameters(), self.max_grad_norm)
        self.policy_optim.step()

        # ---- Entropy tuning ----
        alpha_loss = 0.0
        if self.auto_entropy:
            alpha_loss = -(self.log_alpha * (log_prob + self.target_entropy).detach()).mean()
            self.alpha_optim.zero_grad()
            alpha_loss.backward()
            nn.utils.clip_grad_norm_([self.log_alpha], self.max_grad_norm)
            self.alpha_optim.step()
            # Clamp log_alpha to [log(alpha_min), log(alpha_max)] to prevent
            # divergence in both directions.  A collapsed alpha (~0) can cause
            # the optimizer to overcorrect and spike back to 1.0+ on the next
            # update, triggering the "alpha reset" collapse we observed.
            with torch.no_grad():
                self.log_alpha.data.clamp_(
                    min=np.log(self.alpha_min),
                    max=np.log(self.alpha_max),
                )
            self.alpha = self.log_alpha.exp().item()

        # ---- Soft update target networks ----
        for param, target_param in zip(
            self.critic.parameters(), self.critic_target.parameters()
        ):
            target_param.data.copy_(
                self.tau * param.data + (1 - self.tau) * target_param.data
            )

        return {
            "critic_loss": critic_loss.item(),
            "policy_loss": policy_loss.item(),
            "alpha": self.alpha,
            "alpha_loss": float(alpha_loss) if isinstance(alpha_loss, float) else alpha_loss.item(),
            "buffer_size": len(self.buffer),
        }

    def save(self, path: str, metadata: dict | None = None):
        """Save model checkpoint.

        Args:
            path: File path for the checkpoint.
            metadata: Optional dict of extra values (e.g. {"start_episode": N})
                      stored under the key "_metadata" and returned by load().
        """
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        torch.save({
            "policy": self.policy.state_dict(),
            "critic": self.critic.state_dict(),
            "critic_target": self.critic_target.state_dict(),
            "policy_optim": self.policy_optim.state_dict(),
            "critic_optim": self.critic_optim.state_dict(),
            "log_alpha": self.log_alpha.detach().cpu() if self.auto_entropy else None,
            "alpha_optim": self.alpha_optim.state_dict() if self.auto_entropy else None,
            "total_steps": self.total_steps,
            "_metadata": metadata or {},
        }, path)
        print(f"[SAC] Checkpoint saved: {path}")

    def load(self, path: str) -> dict:
        """Load model checkpoint.

        Returns:
            The metadata dict that was passed to save() (empty dict if none).
            Callers can read e.g. ``meta["start_episode"]`` for resume.
        """
        ckpt = torch.load(path, map_location=self.device, weights_only=False)
        self.policy.load_state_dict(ckpt["policy"])
        self.critic.load_state_dict(ckpt["critic"])
        self.critic_target.load_state_dict(ckpt["critic_target"])
        self.policy_optim.load_state_dict(ckpt["policy_optim"])
        self.critic_optim.load_state_dict(ckpt["critic_optim"])
        if self.auto_entropy and ckpt.get("log_alpha") is not None:
            self.log_alpha.data.copy_(ckpt["log_alpha"])
            self.alpha_optim.load_state_dict(ckpt["alpha_optim"])
            self.alpha = self.log_alpha.exp().item()
        self.total_steps = ckpt.get("total_steps", 0)
        print(f"[SAC] Checkpoint loaded: {path} (steps={self.total_steps})")
        return ckpt.get("_metadata", {})
