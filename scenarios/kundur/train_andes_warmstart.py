"""
ANDES 共享参数预热 + 逐 Agent 微调训练脚本
==========================================
Hypothesis: 用同一个预训练 shared-param actor 初始化 4 个独立 agent,
降低 seed-to-seed 方差 (std 0.265 → <0.15) 并缓解 a1 主导 (56% → <50%).

用法 (WSL):
    source ~/andes_venv/bin/activate
    cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"
    python3 scenarios/kundur/train_andes_warmstart.py --seed 42 --episodes 500 \
        --save-dir results/andes_warmstart_seed42

不修改 train_andes.py — 此文件是独立副本+扩展.
"""

import argparse
import os
import sys
import time
import json
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    print("[WARN] torch not found, installing...")
    os.system("pip install torch --index-url https://download.pytorch.org/whl/cpu -q")
    import torch
    HAS_TORCH = True

from env.andes_vsg_env import AndesMultiVSGEnv
from agents.sac import SACAgent
from utils.monitor import TrainingMonitor

# Default warmstart source (phase9 shared seed42 500ep, mean cum_rf -1.069 paper-grade)
DEFAULT_WARMSTART = "results/andes_phase9_shared_seed42_500ep/agent_shared_final.pt"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--episodes", type=int, default=500)
    p.add_argument("--warmup", type=int, default=None,
                   help="Warmup steps (default: from config.py)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--save-dir", type=str, default="results/andes_warmstart_seed42")
    p.add_argument("--log-interval", type=int, default=10)
    p.add_argument("--warmstart-source", type=str, default=DEFAULT_WARMSTART,
                   help="Path to shared-param .pt checkpoint used as actor warmstart")
    p.add_argument("--warmstart-mode", type=str, default="actor_only",
                   choices=["actor_only", "actor_and_critic"],
                   help="actor_only: warmstart actor, fresh critic (default). "
                        "actor_and_critic: warmstart both.")
    return p.parse_args()


def load_warmstart_state(warmstart_path: str, device: str = "cpu") -> dict:
    """Load and validate warmstart checkpoint. Returns state dict."""
    if not os.path.exists(warmstart_path):
        raise FileNotFoundError(
            f"Warmstart checkpoint not found: {warmstart_path}\n"
            f"Expected: results/andes_phase9_shared_seed42_500ep/agent_shared_final.pt"
        )
    state = torch.load(warmstart_path, map_location=device, weights_only=False)
    if 'actor' not in state:
        raise KeyError(
            f"Warmstart checkpoint missing 'actor' key. Keys found: {list(state.keys())}"
        )
    print(f"[warmstart] Loaded checkpoint from: {warmstart_path}")
    print(f"[warmstart] Keys available: {list(state.keys())}")
    return state


def main():
    args = parse_args()

    import config as cfg
    if args.warmup is None:
        args.warmup = cfg.WARMUP_STEPS

    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    print("=" * 60)
    print(f" ANDES MADRL Warmstart Training — {args.episodes} episodes")
    print(f" Seed: {args.seed}  Mode: {args.warmstart_mode}")
    print(f" Warmstart: {args.warmstart_source}")
    print("=" * 60)

    os.makedirs(args.save_dir, exist_ok=True)
    os.makedirs("results/figures", exist_ok=True)

    # ─── Load warmstart checkpoint (fail fast before any training) ───
    warmstart_state = load_warmstart_state(args.warmstart_source)

    # ─── 环境 & Agent ───
    N = AndesMultiVSGEnv.N_AGENTS
    obs_dim = AndesMultiVSGEnv.OBS_DIM
    action_dim = 2

    hidden_sizes = cfg.HIDDEN_SIZES
    lr = cfg.LR
    gamma = cfg.GAMMA
    tau = cfg.TAU_SOFT
    buffer_size = cfg.BUFFER_SIZE
    batch_size = cfg.BATCH_SIZE

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
        # ── Warmstart: load shared actor weights into each agent ──
        agent.actor.load_state_dict(warmstart_state['actor'])
        print(f"  [warmstart] Agent {i}: actor loaded from shared ckpt")

        if args.warmstart_mode == "actor_and_critic":
            agent.critic.load_state_dict(warmstart_state['critic'])
            agent.critic_target.load_state_dict(warmstart_state['critic_target'])
            print(f"  [warmstart] Agent {i}: critic + critic_target loaded from shared ckpt")
        # critic stays fresh (random init) in actor_only mode — allows per-agent specialization

        agents.append(agent)

    print(f"\n[warmstart] All {N} agents initialized from shared actor. "
          f"Critic: {'warmstarted' if args.warmstart_mode == 'actor_and_critic' else 'fresh (random)'}")

    # Save warmstart config alongside training output
    warmstart_meta = {
        "warmstart_source": args.warmstart_source,
        "warmstart_mode": args.warmstart_mode,
        "seed": args.seed,
        "episodes": args.episodes,
        "n_agents": N,
    }
    with open(os.path.join(args.save_dir, "warmstart_config.json"), "w") as f:
        json.dump(warmstart_meta, f, indent=2)

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
            env.seed(args.seed + ep)

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
                actions = {}
                for i in range(N):
                    if total_steps < args.warmup:
                        actions[i] = np.random.uniform(-1, 1, size=action_dim)
                    else:
                        actions[i] = agents[i].select_action(obs[i])

                try:
                    next_obs, rewards, done, info = env.step(actions)
                except Exception as e:
                    print(f"  [ep {ep}, step {step}] step failed: {e}")
                    break

                ep_actions_list.append(np.array([actions[i] for i in range(N)]))
                ep_r_f += info.get('r_f', 0.0)
                ep_r_h += info.get('r_h', 0.0)
                ep_r_d += info.get('r_d', 0.0)
                ep_max_freq = max(ep_max_freq, info.get('max_freq_deviation_hz', 0.0))
                ep_tds_failed = ep_tds_failed or info.get('tds_failed', False)

                for i in range(N):
                    agents[i].buffer.add(obs[i], actions[i], rewards[i],
                                         next_obs[i], float(done))
                    ep_reward[i] += rewards[i]

                obs = next_obs
                total_steps += 1

                if done:
                    break

            # Episode-end batch update (same as train_andes.py — 10 epochs)
            N_EPOCH = 10
            ep_sac_losses = [None] * N
            if total_steps >= args.warmup:
                for _ in range(N_EPOCH):
                    for i in range(N):
                        if len(agents[i].buffer) >= batch_size:
                            loss_info = agents[i].update()
                            if loss_info is not None:
                                ep_sac_losses[i] = loss_info

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

            if cfg.CLEAR_BUFFER_PER_EPISODE:
                for i in range(N):
                    agents[i].buffer.clear()

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

            if (ep + 1) % 100 == 0:
                for i in range(N):
                    agents[i].save(os.path.join(args.save_dir, f"agent_{i}_ep{ep+1}.pt"))

    except KeyboardInterrupt:
        interrupted = True
        print(f"\n[!] Training interrupted at ep {last_ep + 1}. Saving checkpoint...")

    monitor.summary()
    monitor.save_checkpoint(os.path.join(args.save_dir, "monitor_checkpoint.json"))
    monitor.export_csv(os.path.join(args.save_dir, "monitor_data.csv"))

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
            "warmstart_source": args.warmstart_source,
            "warmstart_mode": args.warmstart_mode,
            "seed": args.seed,
        }
        log_path = os.path.join(args.save_dir, "training_log.json")
        with open(log_path, "w") as f:
            json.dump(log, f)
        print(f"\nTraining log saved to {log_path}")
    else:
        print("\nNo episodes completed, nothing to save.")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(15, 8))
        fig.suptitle(f"ANDES Warmstart Training (SAC) — seed {args.seed}")

        ax = axes[0, 0]
        window = max(1, len(total_rewards) // 20)
        smoothed = np.convolve(total_rewards, np.ones(window)/window, mode="valid")
        ax.plot(total_rewards, alpha=0.3, color="blue")
        ax.plot(range(window-1, len(total_rewards)), smoothed, color="blue")
        ax.set_title("Total Episode Reward")
        ax.set_xlabel("Episode")
        ax.grid(True, alpha=0.3)

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

        axes[1, 2].axis("off")
        plt.tight_layout()
        fig_path = os.path.join(args.save_dir, "training_curves.png")
        plt.savefig(fig_path, dpi=150)
        print(f"Training curves saved to {fig_path}")
    except Exception as e:
        print(f"Plot error: {e}")

    print(f"\nTotal time: {time.time() - t_start:.0f}s")
    print("Done!")


if __name__ == "__main__":
    main()
