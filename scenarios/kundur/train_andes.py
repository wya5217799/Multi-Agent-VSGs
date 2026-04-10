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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

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
from utils.monitor import TrainingMonitor


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--episodes", type=int, default=500)
    p.add_argument("--warmup", type=int, default=None,
                   help="Warmup steps (default: from config.py)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--save-dir", type=str, default="results/andes_models_v3")
    p.add_argument("--log-interval", type=int, default=10)
    p.add_argument("--resume", type=str, default=None,
                   help="从指定目录加载模型继续训练, 如 results/andes_models_r3")
    p.add_argument("--seed-offset", type=int, default=0,
                   help="seed 偏移量, 避免与之前训练重复 (如之前训练了600ep, 设为600)")
    return p.parse_args()


def main():
    args = parse_args()

    import config as _cfg_early
    if args.warmup is None:
        args.warmup = _cfg_early.WARMUP_STEPS

    print("=" * 60)
    print(f" ANDES MADRL Training — {args.episodes} episodes")
    print("=" * 60)

    os.makedirs(args.save_dir, exist_ok=True)
    os.makedirs("results/figures", exist_ok=True)

    # ─── 环境 & Agent ───
    N = AndesMultiVSGEnv.N_AGENTS
    obs_dim = AndesMultiVSGEnv.OBS_DIM
    action_dim = 2

    # SAC 超参数 (论文 Table I, 从 config.py 读取)
    import config as cfg
    hidden_sizes = cfg.HIDDEN_SIZES
    lr = cfg.LR
    gamma = cfg.GAMMA
    tau = cfg.TAU_SOFT
    buffer_size = cfg.BUFFER_SIZE
    batch_size = cfg.BATCH_SIZE

    total_updates = args.episodes * AndesMultiVSGEnv.STEPS_PER_EPISODE

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
            total_updates=total_updates,
        )
        agents.append(agent)

    # 从检查点恢复（优先 _final.pt，回退到最新 epN checkpoint）
    if args.resume:
        for i in range(N):
            model_path = os.path.join(args.resume, f"agent_{i}_final.pt")
            if not os.path.exists(model_path):
                import glob
                pattern = os.path.join(args.resume, f"agent_{i}_ep*.pt")
                ckpts = sorted(glob.glob(pattern),
                               key=lambda p: int(p.rsplit("ep", 1)[-1].split(".")[0]))
                if ckpts:
                    model_path = ckpts[-1]
            if os.path.exists(model_path):
                agents[i].load(model_path)
                print(f"  Resumed agent {i} from {model_path}")
            else:
                print(f"  [WARN] No checkpoint found for agent {i}, starting fresh")

    # ─── 训练日志 ───
    episode_rewards = {i: [] for i in range(N)}
    total_rewards = []
    total_steps = 0
    t_start = time.time()
    def on_best_reward(ep, reward):
        print(f"  [Monitor] New best reward: {reward:.1f} @ ep {ep}")
        for i in range(N):
            agents[i].save(os.path.join(args.save_dir, f"agent_{i}_best.pt"))

    monitor = TrainingMonitor(best_reward_callback=on_best_reward)

    interrupted = False
    last_ep = -1
    try:
        for ep in range(args.episodes):
            env = AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=0.1)
            env.seed(args.seed + args.seed_offset + ep)

            try:
                obs = env.reset()
            except Exception as e:
                print(f"  [ep {ep}] reset failed: {e}, skipping")
                continue

            ep_reward = {i: 0.0 for i in range(N)}
            ep_r_f, ep_r_h, ep_r_d = 0.0, 0.0, 0.0
            ep_actions_list = []
            ep_max_freq = 0.0
            ep_tds_failed = False

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

                # Monitor: collect actions and reward components
                ep_actions_list.append(np.array([actions[i] for i in range(N)]))
                ep_r_f += info.get('r_f', 0.0)
                ep_r_h += info.get('r_h', 0.0)
                ep_r_d += info.get('r_d', 0.0)
                ep_max_freq = max(ep_max_freq, info.get('max_freq_deviation_hz', 0.0))
                ep_tds_failed = ep_tds_failed or info.get('tds_failed', False)

                # 存储经验
                for i in range(N):
                    agents[i].buffer.add(obs[i], actions[i], rewards[i],
                                          next_obs[i], float(done))
                    ep_reward[i] += rewards[i]

                obs = next_obs
                total_steps += 1

                if done:
                    break

            # Episode 结束后集中更新 (论文 Algorithm 1 风格)
            # 多轮重复采样, 类似 PPO K-epochs, 充分利用 50 条 transitions
            N_EPOCH = 10  # 每条数据平均被采样 ~6 次 (10*32/50)
            ep_sac_losses = [None] * N
            if total_steps >= args.warmup:
                for _ in range(N_EPOCH):
                    for i in range(N):
                        if len(agents[i].buffer) >= batch_size:
                            loss_info = agents[i].update()
                            if loss_info is not None:
                                ep_sac_losses[i] = loss_info

            # Monitor: check for training issues
            if ep_actions_list:
                should_stop = monitor.log_and_check(
                    episode=ep,
                    rewards=sum(ep_reward.values()),
                    reward_components={"r_f": ep_r_f, "r_h": ep_r_h, "r_d": ep_r_d},
                    actions=np.array(ep_actions_list),
                    info={"tds_failed": ep_tds_failed, "max_freq_deviation_hz": ep_max_freq},
                    per_agent_rewards=ep_reward,
                    sac_losses=[l for l in ep_sac_losses if l is not None] if any(ep_sac_losses) else None,
                )
                if should_stop:
                    break

            # Buffer 策略 (见 config.py 注释: Table I vs Algorithm 1 分析)
            if cfg.CLEAR_BUFFER_PER_EPISODE:
                for i in range(N):
                    agents[i].buffer.clear()

            # 记录
            for i in range(N):
                episode_rewards[i].append(ep_reward[i])
            total_ep_reward = sum(ep_reward.values())
            total_rewards.append(total_ep_reward)

            last_ep = ep

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

    except KeyboardInterrupt:
        interrupted = True
        print(f"\n[!] Training interrupted at ep {last_ep + 1}. Saving checkpoint...")

    monitor.summary()

    # Save monitor data
    monitor.save_checkpoint(os.path.join(args.save_dir, "monitor_checkpoint.json"))
    monitor.export_csv(os.path.join(args.save_dir, "monitor_data.csv"))

    # ─── 保存（正常结束或中断都会执行） ───
    if last_ep >= 0:
        for i in range(N):
            agents[i].save(os.path.join(args.save_dir, f"agent_{i}_final.pt"))

        log = {
            "episode_rewards": {str(i): episode_rewards[i] for i in range(N)},
            "total_rewards": total_rewards,
            "total_steps": total_steps,
            "episodes_completed": last_ep + 1,
            "episodes_planned": args.episodes,
            "interrupted": interrupted,
        }
        log_path = os.path.join(args.save_dir, "training_log.json")
        with open(log_path, "w") as f:
            json.dump(log, f)
        print(f"\nTraining log saved to {log_path}")
    else:
        print("\nNo episodes completed, nothing to save.")

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
