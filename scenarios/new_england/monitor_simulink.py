"""
Training Monitor for Multi-Agent VSG on Modified NE 39-Bus System.

Usage:
    # Plot saved training log:
    python monitor.py

    # Live monitoring (refreshes every 10s):
    python monitor.py --live

    # Custom log file:
    python monitor.py --log training_log.json
"""

import argparse
import json
import os
import time
import numpy as np

try:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


def load_log(path="training_log.json"):
    with open(path, "r") as f:
        return json.load(f)


def smooth(data, window=20):
    if len(data) < window:
        return data
    kernel = np.ones(window) / window
    return np.convolve(data, kernel, mode="valid")


def plot_training(log, save_path="training_curves.png", show=True):
    """Generate 4-panel training dashboard."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Multi-Agent VSG Training Monitor", fontsize=14, fontweight="bold")

    # 1. Episode rewards
    ax = axes[0, 0]
    rewards = log["episode_rewards"]
    ax.plot(rewards, alpha=0.3, color="blue", linewidth=0.5, label="Raw")
    if len(rewards) > 20:
        sm = smooth(rewards, 20)
        ax.plot(range(19, 19 + len(sm)), sm, color="blue", linewidth=2, label="Smooth(20)")
    # Eval rewards
    if log.get("eval_rewards"):
        eval_eps = [e["episode"] for e in log["eval_rewards"]]
        eval_rs = [e["reward"] for e in log["eval_rewards"]]
        ax.scatter(eval_eps, eval_rs, color="red", s=40, zorder=5, label="Eval")
    ax.set_xlabel("Episode")
    ax.set_ylabel("Total Reward")
    ax.set_title("Episode Rewards")
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(True, alpha=0.3)

    # 2. Critic loss
    ax = axes[0, 1]
    if log.get("critic_losses"):
        losses = log["critic_losses"]
        ax.plot(losses, alpha=0.3, color="orange", linewidth=0.5)
        if len(losses) > 20:
            sm = smooth(losses, 20)
            ax.plot(range(19, 19 + len(sm)), sm, color="orange", linewidth=2)
        ax.set_yscale("log")
    ax.set_xlabel("Episode")
    ax.set_ylabel("Critic Loss (log)")
    ax.set_title("Critic Loss")
    ax.grid(True, alpha=0.3)

    # 3. Policy loss
    ax = axes[1, 0]
    if log.get("policy_losses"):
        losses = log["policy_losses"]
        ax.plot(losses, alpha=0.3, color="green", linewidth=0.5)
        if len(losses) > 20:
            sm = smooth(losses, 20)
            ax.plot(range(19, 19 + len(sm)), sm, color="green", linewidth=2)
    ax.set_xlabel("Episode")
    ax.set_ylabel("Policy Loss")
    ax.set_title("Policy Loss")
    ax.grid(True, alpha=0.3)

    # 4. Alpha (entropy temperature)
    ax = axes[1, 1]
    if log.get("alphas"):
        alphas = log["alphas"]
        ax.plot(alphas, color="purple", linewidth=1.5)
        ax.axhline(y=0.2, color="gray", linestyle="--", alpha=0.5, label="Default=0.2")
    ax.set_xlabel("Episode")
    ax.set_ylabel("Alpha")
    ax.set_title("Entropy Temperature (Alpha)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"Saved: {save_path}")
    if show:
        plt.show()
    plt.close()


def print_summary(log):
    """Print text summary of training progress."""
    rewards = log["episode_rewards"]
    n = len(rewards)
    print(f"\n{'='*60}")
    print(f"Training Summary ({n} episodes)")
    print(f"{'='*60}")

    # Reward progression
    chunks = min(10, n)
    chunk_size = n // chunks
    print(f"\n{'Period':<15} {'Avg Reward':>12} {'Min':>12} {'Max':>12}")
    print("-" * 55)
    for i in range(chunks):
        start = i * chunk_size
        end = start + chunk_size
        chunk = rewards[start:end]
        print(f"Ep {start+1:4d}-{end:4d}  {np.mean(chunk):>12.0f} {np.min(chunk):>12.0f} {np.max(chunk):>12.0f}")

    # Eval rewards
    if log.get("eval_rewards"):
        print(f"\nEvaluation Checkpoints:")
        for e in log["eval_rewards"]:
            print(f"  Ep {e['episode']:4d}: {e['reward']:+.0f}")

    # Alpha
    if log.get("alphas"):
        alphas = log["alphas"]
        print(f"\nAlpha: start={alphas[0]:.4f}, end={alphas[-1]:.4f}, "
              f"min={min(alphas):.4f}, max={max(alphas):.4f}")

    # Learning signal
    if n >= 100:
        first_100 = np.mean(rewards[:100])
        last_100 = np.mean(rewards[-100:])
        improvement = last_100 - first_100
        print(f"\nLearning: first100={first_100:.0f}, last100={last_100:.0f}, "
              f"delta={improvement:+.0f} ({improvement/abs(first_100)*100:+.1f}%)")


def live_monitor(log_path, interval=10):
    """Live monitoring mode — refreshes plot every N seconds."""
    print(f"Live monitoring: {log_path} (refresh every {interval}s)")
    print("Press Ctrl+C to stop.\n")

    plt.ion()
    fig = None

    try:
        while True:
            if os.path.exists(log_path):
                log = load_log(log_path)
                if log["episode_rewards"]:
                    if fig is not None:
                        plt.close(fig)
                    plot_training(log, save_path="training_curves.png", show=False)
                    print_summary(log)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")


def main():
    parser = argparse.ArgumentParser(description="Training Monitor")
    parser.add_argument("--log", default="training_log.json")
    parser.add_argument("--live", action="store_true", help="Live refresh mode")
    parser.add_argument("--interval", type=int, default=10, help="Refresh interval (s)")
    parser.add_argument("--no-show", action="store_true", help="Save only, don't display")
    args = parser.parse_args()

    if args.live:
        if not HAS_MPL:
            print("matplotlib required for live mode. Install: pip install matplotlib")
            return
        live_monitor(args.log, args.interval)
    else:
        log = load_log(args.log)
        print_summary(log)
        if HAS_MPL:
            plot_training(log, show=not args.no_show)
        else:
            print("\nInstall matplotlib for plots: pip install matplotlib")


if __name__ == "__main__":
    main()
