"""
ANDES 版训练脚本
================
在 WSL 中运行:
    source ~/andes_venv/bin/activate
    cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"
    python3 train_andes.py --episodes 500

论文: Yang et al., IEEE TPWRS 2023
使用 ANDES Kundur 两区域系统 + 4 VSG 储能
"""

import argparse
import os
import sys
import time
import json
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ─── 检测运行环境 ───
try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    print("[WARN] torch not found in WSL, installing...")
    os.system("pip install torch --index-url https://download.pytorch.org/whl/cpu -q")
    import torch
    HAS_TORCH = True

from env.andes_vsg_env import AndesMultiVSGEnv
from agents.sac import SACAgent


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--episodes", type=int, default=500)
    p.add_argument("--warmup", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--save-dir", type=str, default="results/andes_models")
    p.add_argument("--log-interval", type=int, default=10)
    p.add_argument("--resume", type=str, default=None,
                   help="从指定目录加载模型继续训练, 如 results/andes_models_r3")
    p.add_argument("--seed-offset", type=int, default=0,
                   help="seed 偏移量, 避免与之前训练重复 (如之前训练了600ep, 设为600)")
    return p.parse_args()


def main():
    args = parse_args()

    print("=" * 60)
    print(f" ANDES MADRL Training — {args.episodes} episodes")
    print("=" * 60)

    os.makedirs(args.save_dir, exist_ok=True)
    os.makedirs("results/figures", exist_ok=True)

    # ─── 环境 & Agent ───
    N = AndesMultiVSGEnv.N_AGENTS
    obs_dim = AndesMultiVSGEnv.OBS_DIM
    action_dim = 2

    # SAC 超参数 (论文 Table I)
    hidden_sizes = [128, 128, 128, 128]
    lr = 3e-4
    gamma = 0.99
    tau = 0.005
    buffer_size = 10000
    batch_size = 256

    agents = []
    for i in range(N):
        agent = SACAgent(
            obs_dim=obs_dim,
            action_dim=action_dim,
            hidden_sizes=hidden_sizes,
            lr=lr,
            gamma=gamma,
            tau=tau,
            buffer_size=buffer_size,
            batch_size=batch_size,
        )
        agents.append(agent)

    # 从检查点恢复
    if args.resume:
        for i in range(N):
            model_path = os.path.join(args.resume, f"agent_{i}_final.pt")
            if os.path.exists(model_path):
                agents[i].load(model_path)
                print(f"  Resumed agent {i} from {model_path}")
            else:
                print(f"  [WARN] {model_path} not found, starting fresh")

    # ─── 训练日志 ───
    episode_rewards = {i: [] for i in range(N)}
    total_rewards = []
    total_steps = 0
    t_start = time.time()

    for ep in range(args.episodes):
        env = AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=0.1)
        env.seed(args.seed + args.seed_offset + ep)

        try:
            obs = env.reset()
        except Exception as e:
            print(f"  [ep {ep}] reset failed: {e}, skipping")
            continue

        ep_reward = {i: 0.0 for i in range(N)}

        for step in range(AndesMultiVSGEnv.STEPS_PER_EPISODE):
            # 选择动作
            actions = {}
            for i in range(N):
                if total_steps < args.warmup:
                    actions[i] = np.random.uniform(-1, 1, size=action_dim)
                else:
                    actions[i] = agents[i].select_action(obs[i])

            # 执行
            try:
                next_obs, rewards, done, info = env.step(actions)
            except Exception as e:
                print(f"  [ep {ep}, step {step}] step failed: {e}")
                break

            # 存储经验并更新
            for i in range(N):
                agents[i].buffer.add(obs[i], actions[i], rewards[i],
                                      next_obs[i], float(done))
                ep_reward[i] += rewards[i]

                if total_steps >= args.warmup and len(agents[i].buffer) >= batch_size:
                    agents[i].update()

            obs = next_obs
            total_steps += 1

            if done:
                break

        # 记录
        for i in range(N):
            episode_rewards[i].append(ep_reward[i])
        total_ep_reward = sum(ep_reward.values())
        total_rewards.append(total_ep_reward)

        if (ep + 1) % args.log_interval == 0:
            elapsed = time.time() - t_start
            avg_reward = np.mean(total_rewards[-args.log_interval:])
            print(f"  Ep {ep+1}/{args.episodes} | "
                  f"Avg Reward: {avg_reward:.1f} | "
                  f"Steps: {total_steps} | "
                  f"Time: {elapsed:.0f}s")

        # 定期保存
        if (ep + 1) % 100 == 0:
            for i in range(N):
                agents[i].save(os.path.join(args.save_dir, f"agent_{i}_ep{ep+1}.pt"))

    # ─── 保存最终模型和日志 ───
    for i in range(N):
        agents[i].save(os.path.join(args.save_dir, f"agent_{i}_final.pt"))

    log = {
        "episode_rewards": {str(i): episode_rewards[i] for i in range(N)},
        "total_rewards": total_rewards,
        "total_steps": total_steps,
        "episodes": args.episodes,
    }
    log_path = os.path.join(args.save_dir, "training_log.json")
    with open(log_path, "w") as f:
        json.dump(log, f)
    print(f"\nTraining log saved to {log_path}")

    # ─── 画训练曲线 ───
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(15, 8))
        fig.suptitle("ANDES MADRL Training (SAC)")

        # 总奖励
        ax = axes[0, 0]
        window = max(1, len(total_rewards) // 20)
        smoothed = np.convolve(total_rewards, np.ones(window)/window, mode="valid")
        ax.plot(total_rewards, alpha=0.3, color="blue")
        ax.plot(range(window-1, len(total_rewards)), smoothed, color="blue")
        ax.set_title("Total Episode Reward")
        ax.set_xlabel("Episode")
        ax.grid(True, alpha=0.3)

        # 各 agent 奖励
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
        for i in range(N):
            ax = axes[(i+1) // 3, (i+1) % 3]
            r = episode_rewards[i]
            sm = np.convolve(r, np.ones(window)/window, mode="valid")
            ax.plot(r, alpha=0.3, color=colors[i])
            ax.plot(range(window-1, len(r)), sm, color=colors[i])
            ax.set_title(f"ES{i+1} Reward")
            ax.set_xlabel("Episode")
            ax.grid(True, alpha=0.3)

        # 空的第6格
        axes[1, 2].axis("off")

        plt.tight_layout()
        fig_path = "results/figures/andes_training_curves.png"
        plt.savefig(fig_path, dpi=150)
        print(f"Training curves saved to {fig_path}")
    except Exception as e:
        print(f"Plot error: {e}")

    print(f"\nTotal time: {time.time() - t_start:.0f}s")
    print("Done!")


if __name__ == "__main__":
    main()
