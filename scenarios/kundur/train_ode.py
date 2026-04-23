"""
训练脚本 — 多智能体 SAC 分布式惯量-阻尼控制

论文: Yang et al., IEEE TPWRS 2023

关键实现细节 (与论文对齐):
  - 每 episode 结束后清空 buffer (Algorithm 1 line 16)
  - r_h/r_d 使用全局平均 ΔH^avg / ΔD^avg (Eq.17-18)
  - ΔH ∈ [-100, 300], ΔD ∈ [-200, 600] (Fig.7(c)(d))
  - 固定训练场景集 100 scenarios (Sec IV-A)

用法:
    python train.py                     # 默认 2000 episodes
    python train.py --episodes 500      # 快速测试
"""

import argparse
import os
import sys
import time
import numpy as np
import torch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config as cfg
from env.multi_vsg_env import MultiVSGEnv
from agents.ma_manager import MultiAgentManager
from utils.monitor import TrainingMonitor


def generate_scenario_set(n_scenarios, seed=0):
    """
    预生成固定的扰动场景集 (论文 Sec IV-A).
    每个场景: (delta_u, comm_fail_links)
    """
    rng = np.random.default_rng(seed)
    scenarios = []
    for _ in range(n_scenarios):
        # 随机 1-2 个母线施加扰动
        n_disturbed = rng.integers(1, 3)
        buses = rng.choice(cfg.N_AGENTS, size=n_disturbed, replace=False)
        delta_u = np.zeros(cfg.N_AGENTS)
        for bus in buses:
            magnitude = rng.uniform(cfg.DISTURBANCE_MIN, cfg.DISTURBANCE_MAX)
            sign = rng.choice([-1, 1])
            delta_u[bus] = sign * magnitude

        # 随机通信链路故障
        failed_links = []
        for i, neighbors in cfg.COMM_ADJACENCY.items():
            for j in neighbors:
                if (j, i) not in failed_links and rng.random() < cfg.COMM_FAIL_PROB:
                    failed_links.append((i, j))
                    failed_links.append((j, i))

        scenarios.append((delta_u, failed_links if failed_links else None))
    return scenarios


def train(args):
    device = 'cuda' if torch.cuda.is_available() and not args.cpu else 'cpu'

    # ── P1: 完整 seed 协议，必须在 manager/网络构造前完成 ──
    from utils.seed_utils import seed_everything
    seed_info = seed_everything(args.seed)
    warmup_rng = np.random.default_rng(args.seed)

    # ── 生成固定训练场景集 ──
    train_scenarios = generate_scenario_set(cfg.N_TRAIN_SCENARIOS, seed=args.seed)

    # ── 环境 (不使用内部随机扰动, 由外部指定) ──
    env = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)

    # ── 多智能体 (seed 已在上方统一设置) ──
    manager = MultiAgentManager(
        n_agents=cfg.N_AGENTS,
        obs_dim=cfg.OBS_DIM,
        action_dim=cfg.ACTION_DIM,
        hidden_sizes=cfg.HIDDEN_SIZES,
        lr=cfg.LR,
        gamma=cfg.GAMMA,
        tau=cfg.TAU_SOFT,
        buffer_size=cfg.BUFFER_SIZE,
        batch_size=cfg.BATCH_SIZE,
        device=device,
    )

    # ── 日志 ──
    save_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'results')
    os.makedirs(os.path.join(save_dir, 'models'), exist_ok=True)

    episode_rewards = {i: [] for i in range(cfg.N_AGENTS)}
    episode_total_rewards = []
    episode_freq_rewards = []    # PHI_F * sum(r_f)
    episode_inertia_rewards = [] # PHI_H * sum(r_h)
    episode_droop_rewards = []   # PHI_D * sum(r_d)

    print("=" * 65)
    print("  MADRL-SAC Training — Multi-VSG Distributed Inertia-Droop")
    print("=" * 65)
    print(f"  Device        = {device}")
    print(f"  N agents      = {cfg.N_AGENTS}")
    print(f"  Episodes      = {args.episodes}")
    print(f"  Steps/episode = {cfg.STEPS_PER_EPISODE}")
    print(f"  DT            = {cfg.DT}s, Episode = {cfg.T_EPISODE}s")
    print(f"  H_ES0         = {cfg.H_ES0[0]}, D_ES0 = {cfg.D_ES0[0]}")
    print(f"  dH in [{cfg.DH_MIN}, {cfg.DH_MAX}], dD in [{cfg.DD_MIN}, {cfg.DD_MAX}]")
    print(f"  Network       = {cfg.HIDDEN_SIZES}")
    print(f"  Disturbance   = [{cfg.DISTURBANCE_MIN}, {cfg.DISTURBANCE_MAX}] p.u.")
    print(f"  Train scenes  = {len(train_scenarios)}")
    print(f"  Buffer        = {'clear per ep (Alg.1)' if cfg.CLEAR_BUFFER_PER_EPISODE else 'accumulate across eps (Table I)'}")
    print(f"  Warmup steps  = {cfg.WARMUP_STEPS}")
    print(f"  Seed          = {args.seed}")
    print("=" * 65)

    monitor = TrainingMonitor()

    total_steps = 0
    t_start = time.time()

    for episode in range(args.episodes):
        # 从固定场景集中循环选取
        scenario_idx = episode % len(train_scenarios)
        delta_u, forced_failures = train_scenarios[scenario_idx]

        # 设置强制链路故障
        env.forced_link_failures = forced_failures
        obs = env.reset(delta_u=delta_u)

        ep_rewards = {i: 0.0 for i in range(cfg.N_AGENTS)}
        ep_r_f, ep_r_h, ep_r_d = 0.0, 0.0, 0.0
        ep_actions_list = []
        ep_max_freq = 0.0

        for step in range(cfg.STEPS_PER_EPISODE):
            # 选择动作
            if total_steps < cfg.WARMUP_STEPS:
                # P1: 本地 RNG 替代全局 np.random 保证可复现
                actions = {i: warmup_rng.uniform(-1, 1, size=cfg.ACTION_DIM)
                           for i in range(cfg.N_AGENTS)}
            else:
                actions = manager.select_actions(obs)

            # 环境步进
            next_obs, rewards, done, info = env.step(actions)

            # 存储经验
            manager.store_transitions(obs, actions, rewards, next_obs, done)

            # 更新网络
            if total_steps >= cfg.WARMUP_STEPS:
                manager.update()

            for i in range(cfg.N_AGENTS):
                ep_rewards[i] += rewards[i]

            # 累计分项奖励
            ep_r_f += info['r_f']
            ep_r_h += info['r_h']
            ep_r_d += info['r_d']

            # Monitor: collect actions and freq deviation
            ep_actions_list.append(np.array([actions[i] for i in range(cfg.N_AGENTS)]))
            ep_max_freq = max(ep_max_freq, info.get('max_freq_deviation_hz', 0.0))

            obs = next_obs
            total_steps += 1

        # 论文 Algorithm 1 line 16: 每 episode 结束后清空 buffer
        # 可通过 config.CLEAR_BUFFER_PER_EPISODE 切换 (对比实验)
        if cfg.CLEAR_BUFFER_PER_EPISODE:
            manager.clear_buffers()

        # Monitor: check for training issues
        should_stop = monitor.log_and_check(
            episode=episode,
            rewards=sum(ep_rewards[i] for i in range(cfg.N_AGENTS)),
            reward_components={"r_f": ep_r_f, "r_h": ep_r_h, "r_d": ep_r_d},
            actions=np.array(ep_actions_list),
            info={"tds_failed": False, "max_freq_deviation_hz": ep_max_freq},
        )
        if should_stop:
            break

        # 记录奖励
        total_r = 0.0
        for i in range(cfg.N_AGENTS):
            episode_rewards[i].append(ep_rewards[i])
            total_r += ep_rewards[i]
        episode_total_rewards.append(total_r)
        episode_freq_rewards.append(ep_r_f)
        episode_inertia_rewards.append(ep_r_h)
        episode_droop_rewards.append(ep_r_d)

        # 打印进度
        if (episode + 1) % 50 == 0 or episode == 0:
            avg_total = np.mean(episode_total_rewards[-50:])
            elapsed = time.time() - t_start
            per_agent = [np.mean(episode_rewards[i][-50:]) for i in range(cfg.N_AGENTS)]
            print(f"  Ep {episode+1:5d}/{args.episodes} | "
                  f"Total R = {total_r:10.2f} | "
                  f"Avg50 = {avg_total:10.2f} | "
                  f"Per-agent = [{', '.join(f'{r:.1f}' for r in per_agent)}] | "
                  f"{elapsed:.0f}s")

        # 定期保存
        if (episode + 1) % 500 == 0:
            model_dir = os.path.join(save_dir, 'models', f'ep_{episode+1}')
            manager.save(model_dir)

    monitor.summary()

    # ── 最终保存 ──
    final_dir = os.path.join(save_dir, 'models', 'final')
    manager.save(final_dir)

    log_path = os.path.join(save_dir, 'training_log.npz')
    log_data = {
        'episode_total_rewards': np.array(episode_total_rewards),
        'episode_freq_rewards': np.array(episode_freq_rewards),
        'episode_inertia_rewards': np.array(episode_inertia_rewards),
        'episode_droop_rewards': np.array(episode_droop_rewards),
    }
    for i in range(cfg.N_AGENTS):
        log_data[f'episode_rewards_agent_{i}'] = np.array(episode_rewards[i])
    np.savez(log_path, **log_data)

    # P0 + P1: run metadata sidecar (完整 seed 协议 + 固定训练集标识)
    import json as _json
    meta = {
        "scenario": "kundur_ode",
        "train_seed": int(args.seed),
        "seed_protocol": seed_info,
        "n_episodes": int(args.episodes),
        "train_set": {
            "n_train": int(cfg.N_TRAIN_SCENARIOS),
            "seed": int(args.seed),
            "generator": "generate_scenario_set",
        },
        "note": "Kundur 训练侧固定集已绑 cfg.N_TRAIN_SCENARIOS (train_ode.py:64)",
    }
    meta_path = os.path.join(save_dir, 'run_meta.json')
    with open(meta_path, 'w') as f:
        _json.dump(meta, f, indent=2)
    print(f"  [P0/P1 metadata] {meta_path}")

    elapsed = time.time() - t_start
    print(f"\n{'=' * 65}")
    print(f"  Training complete!")
    print(f"  Episodes: {args.episodes}, Time: {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  Final 50ep avg reward: {np.mean(episode_total_rewards[-50:]):.2f}")
    print(f"  Model: {final_dir}")
    print(f"{'=' * 65}")


def main():
    parser = argparse.ArgumentParser(description="MADRL-SAC Training")
    parser.add_argument('--episodes', type=int, default=cfg.N_EPISODES)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--cpu', action='store_true')
    args = parser.parse_args()
    train(args)


if __name__ == '__main__':
    main()
