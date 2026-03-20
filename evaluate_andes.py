"""
ANDES 版评估脚本 — 生成论文对齐的图表
=====================================
在 WSL 中运行:
    source ~/andes_venv/bin/activate
    cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"
    python3 evaluate_andes.py

生成:
  Fig 4: 训练曲线 (合并 3 轮训练日志)
  Fig 6-7: Load Step 1 — 无控制 vs RL 控制
  Fig 8-9: Load Step 2 — 无控制 vs RL 控制
  Fig 5: 累积频率奖励 (测试集)
"""

import os
import sys
import json
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from env.andes_vsg_env import AndesMultiVSGEnv
from agents.sac import SACAgent


SAVE_DIR = "results/figures"
MODEL_DIR = "results/andes_models_r4"  # 第4轮续训 (总计2000ep)
os.makedirs(SAVE_DIR, exist_ok=True)

N = 4
OBS_DIM = 7
ACTION_DIM = 2
HIDDEN = [128, 128, 128, 128]


def load_agents():
    """加载训练好的 agent."""
    agents = []
    for i in range(N):
        agent = SACAgent(
            obs_dim=OBS_DIM, action_dim=ACTION_DIM,
            hidden_sizes=HIDDEN, buffer_size=100, batch_size=32,
        )
        model_path = os.path.join(MODEL_DIR, f"agent_{i}_final.pt")
        if os.path.exists(model_path):
            agent.load(model_path)
            print(f"  Loaded agent {i} from {model_path}")
        else:
            print(f"  [WARN] {model_path} not found, using random agent")
        agents.append(agent)
    return agents


# 正确的 "无控制" 动作: ΔM=0, ΔD=0 → 保持基础参数不变
_a0_fixed = (0 - AndesMultiVSGEnv.DM_MIN) / (AndesMultiVSGEnv.DM_MAX - AndesMultiVSGEnv.DM_MIN) * 2 - 1
_a1_fixed = (0 - AndesMultiVSGEnv.DD_MIN) / (AndesMultiVSGEnv.DD_MAX - AndesMultiVSGEnv.DD_MIN) * 2 - 1
FIXED_ACTION = np.array([_a0_fixed, _a1_fixed], dtype=np.float32)


def run_episode(env, agents, use_rl=True, deterministic=True):
    """运行一个 episode, 收集轨迹数据."""
    obs = env.reset()
    trajectory = {
        "time": [], "freq_hz": [], "P_es": [],
        "M_es": [], "D_es": [], "rewards": {i: [] for i in range(N)},
    }

    for step in range(AndesMultiVSGEnv.STEPS_PER_EPISODE):
        if use_rl and agents is not None:
            actions = {i: agents[i].select_action(obs[i], deterministic=deterministic)
                       for i in range(N)}
        else:
            actions = {i: FIXED_ACTION.copy() for i in range(N)}

        obs, rewards, done, info = env.step(actions)

        trajectory["time"].append(info["time"])
        trajectory["freq_hz"].append(info["freq_hz"].copy())
        trajectory["P_es"].append(info["P_es"].copy())
        trajectory["M_es"].append(info["M_es"].copy())
        trajectory["D_es"].append(info["D_es"].copy())
        for i in range(N):
            trajectory["rewards"][i].append(rewards[i])

        if done:
            break

    # 转为 numpy
    for key in ["time", "freq_hz", "P_es", "M_es", "D_es"]:
        trajectory[key] = np.array(trajectory[key])
    return trajectory


def plot_training_curves():
    """Fig 4: 合并训练曲线."""
    print("\n=== Fig 4: Training Curves ===")

    all_rewards = {str(i): [] for i in range(N)}
    total_rewards = []

    for rdir in ["results/andes_models", "results/andes_models_r2", "results/andes_models_r3", "results/andes_models_r4"]:
        log_path = os.path.join(rdir, "training_log.json")
        if os.path.exists(log_path):
            with open(log_path) as f:
                log = json.load(f)
            total_rewards.extend(log["total_rewards"])
            for i in range(N):
                all_rewards[str(i)].extend(log["episode_rewards"][str(i)])

    if not total_rewards:
        print("  No training logs found!")
        return

    n_ep = len(total_rewards)
    print(f"  Total episodes: {n_ep}")

    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    fig.suptitle("Fig 4: Training Performance (ANDES)", fontsize=14)

    window = max(1, n_ep // 20)
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]

    # (a) Total
    ax = axes[0, 0]
    sm = np.convolve(total_rewards, np.ones(window)/window, mode="valid")
    ax.plot(total_rewards, alpha=0.2, color="blue")
    ax.plot(range(window-1, n_ep), sm, color="blue", lw=2)
    ax.set_title("(a) Total Episode Reward")
    ax.set_xlabel("Episode")
    ax.grid(True, alpha=0.3)

    # (b)-(e) Per agent
    for i in range(N):
        ax = axes[(i+1)//3, (i+1)%3]
        r = all_rewards[str(i)]
        sm = np.convolve(r, np.ones(window)/window, mode="valid")
        ax.plot(r, alpha=0.2, color=colors[i])
        ax.plot(range(window-1, len(r)), sm, color=colors[i], lw=2)
        ax.set_title(f"({chr(98+i)}) ES{i+1} Reward")
        ax.set_xlabel("Episode")
        ax.grid(True, alpha=0.3)

    axes[1, 2].axis("off")
    plt.tight_layout()
    plt.savefig(os.path.join(SAVE_DIR, "andes_fig4_training.png"), dpi=150)
    print(f"  Saved andes_fig4_training.png")


def plot_load_step(agents, load_step_name, delta_u, fig_no_ctrl, fig_ctrl):
    """Fig 6-9: Load step 时域仿真."""
    print(f"\n=== {load_step_name} ===")

    # 无控制
    env_nc = AndesMultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
    env_nc.reset(delta_u=delta_u)
    traj_nc = run_episode(env_nc, None, use_rl=False)

    # RL 控制
    env_rl = AndesMultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
    env_rl.reset(delta_u=delta_u)
    traj_rl = run_episode(env_rl, agents, use_rl=True)

    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    labels = ["ES1", "ES2", "ES3", "ES4"]

    for traj, title_suffix, fig_name in [
        (traj_nc, "Without Control", fig_no_ctrl),
        (traj_rl, "With Proposed Control", fig_ctrl),
    ]:
        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        fig.suptitle(f"{load_step_name} — {title_suffix} (ANDES)", fontsize=13)

        # Frequency
        ax = axes[0, 0]
        for i in range(N):
            ax.plot(traj["time"], traj["freq_hz"][:, i], color=colors[i], label=labels[i])
        ax.set_ylabel("Frequency (Hz)")
        ax.set_xlabel("Time (s)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.set_title("Bus Frequency")

        # Power
        ax = axes[0, 1]
        for i in range(N):
            ax.plot(traj["time"], traj["P_es"][:, i], color=colors[i], label=labels[i])
        ax.set_ylabel("P_es (p.u.)")
        ax.set_xlabel("Time (s)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.set_title("ES Output Power")

        # Inertia M
        ax = axes[1, 0]
        for i in range(N):
            ax.plot(traj["time"], traj["M_es"][:, i], color=colors[i], label=labels[i])
        ax.set_ylabel("M (=2H)")
        ax.set_xlabel("Time (s)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.set_title("Virtual Inertia")

        # Droop D
        ax = axes[1, 1]
        for i in range(N):
            ax.plot(traj["time"], traj["D_es"][:, i], color=colors[i], label=labels[i])
        ax.set_ylabel("D")
        ax.set_xlabel("Time (s)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.set_title("Virtual Droop")

        plt.tight_layout()
        plt.savefig(os.path.join(SAVE_DIR, fig_name), dpi=150)
        print(f"  Saved {fig_name}")


def plot_cumulative_reward(agents):
    """Fig 5: 累积频率奖励 (测试集)."""
    print("\n=== Fig 5: Cumulative Reward on Test Set ===")

    n_test = 30  # 测试集大小
    methods = {
        "No Control": False,
        "Proposed MADRL": True,
    }

    results = {}
    for method_name, use_rl in methods.items():
        rewards_per_ep = []
        for ep in range(n_test):
            env = AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=0.0)
            env.seed(1000 + ep)
            obs = env.reset()

            # 全局频率奖励 (不是局部)
            ep_freq_reward = 0.0
            for step in range(AndesMultiVSGEnv.STEPS_PER_EPISODE):
                if use_rl:
                    actions = {i: agents[i].select_action(obs[i], deterministic=True)
                               for i in range(N)}
                else:
                    actions = {i: FIXED_ACTION.copy() for i in range(N)}

                obs, rewards, done, info = env.step(actions)

                # 全局频率奖励: -Σ(fi - f_bar)²
                f = info["freq_hz"]
                f_bar = f.mean()
                ep_freq_reward -= np.sum((f - f_bar) ** 2)

                if done:
                    break

            rewards_per_ep.append(ep_freq_reward)
        results[method_name] = rewards_per_ep
        avg = np.mean(rewards_per_ep)
        print(f"  {method_name}: avg={avg:.2f}")

    # 画图
    fig, ax = plt.subplots(figsize=(8, 5))
    x = range(1, n_test + 1)
    for method_name, rewards in results.items():
        cum = np.cumsum(rewards)
        ax.plot(x, cum, label=method_name, lw=2)
    ax.set_xlabel("Test Episode")
    ax.set_ylabel("Cumulative Frequency Reward")
    ax.set_title("Fig 5: Cumulative Reward on Test Set (ANDES)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(SAVE_DIR, "andes_fig5_cumulative.png"), dpi=150)
    print(f"  Saved andes_fig5_cumulative.png")


def run_test_set(agents, n_episodes, comm_fail_prob=0.0, comm_delay_steps=0,
                 forced_link_failures=None, seed_base=9999):
    """跑一组测试 episode, 返回频率同步奖励列表."""
    rewards_rl = []
    rewards_fixed = []

    for ep in range(n_episodes):
        # RL
        env = AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=comm_fail_prob,
                               comm_delay_steps=comm_delay_steps,
                               forced_link_failures=forced_link_failures)
        env.seed(seed_base + ep)
        traj_r = run_episode(env, agents, use_rl=True)
        f = traj_r["freq_hz"]
        f_bar = f.mean(axis=1, keepdims=True)
        rewards_rl.append(-np.sum((f - f_bar) ** 2))

        # No control
        env_nc = AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=comm_fail_prob,
                                  comm_delay_steps=comm_delay_steps,
                                  forced_link_failures=forced_link_failures)
        env_nc.seed(seed_base + ep)
        traj_f = run_episode(env_nc, None, use_rl=False)
        f = traj_f["freq_hz"]
        f_bar = f.mean(axis=1, keepdims=True)
        rewards_fixed.append(-np.sum((f - f_bar) ** 2))

    return np.array(rewards_rl), np.array(rewards_fixed)


def plot_reward_comparison(rewards_dict, title, save_path):
    """累积奖励对比图 (Fig 10/12 style)."""
    fig, ax = plt.subplots(figsize=(8, 5))
    styles = {'Proposed (normal)': ('b-', 2),
              'Proposed (failure)': ('g--', 2),
              'Proposed (delay)': ('g--', 2),
              'Without control': ('r:', 2)}

    for label, rewards in rewards_dict.items():
        eps = np.arange(1, len(rewards) + 1)
        ls, lw = styles.get(label, ('k-', 1.5))
        ax.plot(eps, np.cumsum(rewards), ls, lw=lw,
                label=f'{label} (avg={np.mean(rewards):.4f})')

    ax.set_xlabel('Test Episode')
    ax.set_ylabel('Cumulative Frequency Reward')
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  Saved {os.path.basename(save_path)}")


def plot_rl_control_andes(traj, title_suffix, save_path):
    """RL 控制时域仿真 (2x2)."""
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    labels = ["ES1", "ES2", "ES3", "ES4"]

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle(f"System dynamics with proposed control — {title_suffix} (ANDES)", fontsize=13)

    ax = axes[0, 0]
    for i in range(N):
        ax.plot(traj["time"], traj["freq_hz"][:, i], color=colors[i], label=labels[i])
    ax.set_ylabel("Frequency (Hz)")
    ax.set_title("(a) Frequency")
    ax.legend()
    ax.grid(True, alpha=0.3)

    ax = axes[0, 1]
    for i in range(N):
        ax.plot(traj["time"], traj["P_es"][:, i], color=colors[i], label=labels[i])
    ax.set_ylabel("P_es (p.u.)")
    ax.set_title("(b) Output Power")
    ax.legend()
    ax.grid(True, alpha=0.3)

    ax = axes[1, 0]
    for i in range(N):
        ax.plot(traj["time"], traj["M_es"][:, i], color=colors[i], label=labels[i])
    ax.set_ylabel("M (=2H)")
    ax.set_xlabel("Time (s)")
    ax.set_title("(c) Virtual Inertia")
    ax.legend()
    ax.grid(True, alpha=0.3)

    ax = axes[1, 1]
    for i in range(N):
        ax.plot(traj["time"], traj["D_es"][:, i], color=colors[i], label=labels[i])
    ax.set_ylabel("D")
    ax.set_xlabel("Time (s)")
    ax.set_title("(d) Virtual Droop")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  Saved {os.path.basename(save_path)}")


def plot_comm_failure_test(agents, n_test=20):
    """Fig 10-11 ANDES版: 通信故障测试."""
    print("\n=== Fig 10-11: Communication Failure (ANDES) ===")

    # 正常条件
    r_rl_normal, r_fixed = run_test_set(agents, n_test, comm_fail_prob=0.0)

    # 30% 通信故障
    r_rl_fail, _ = run_test_set(agents, n_test, comm_fail_prob=0.3)

    # Fig 10: 累积奖励
    plot_reward_comparison(
        {'Proposed (normal)': r_rl_normal,
         'Proposed (failure)': r_rl_fail,
         'Without control': r_fixed},
        'Fig 10. Cumulative reward under communication failure (ANDES)',
        os.path.join(SAVE_DIR, 'andes_fig10_comm_failure_reward.png'),
    )
    print(f"    Normal avg = {np.mean(r_rl_normal):.4f}")
    print(f"    Failure avg = {np.mean(r_rl_fail):.4f}")

    # Fig 11: 特定链路故障 (ES1↔ES2) 时域
    env_fail = AndesMultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0,
                                forced_link_failures=[(0, 1), (1, 0)])
    env_fail.reset(delta_u={"PQ_0": 1.5})
    traj = run_episode(env_fail, agents, use_rl=True)
    plot_rl_control_andes(traj, "load step 1 under comm failure",
                          os.path.join(SAVE_DIR, 'andes_fig11_comm_failure_td.png'))


def plot_comm_delay_test(agents, n_test=20):
    """Fig 12-13 ANDES版: 通信延迟测试."""
    print("\n=== Fig 12-13: Communication Delay (ANDES) ===")

    # 正常条件
    r_rl_normal, r_fixed = run_test_set(agents, n_test, comm_fail_prob=0.0)

    # 1步 (0.2s) 通信延迟
    r_rl_delay, _ = run_test_set(agents, n_test, comm_delay_steps=1)

    # Fig 12: 累积奖励
    plot_reward_comparison(
        {'Proposed (normal)': r_rl_normal,
         'Proposed (delay)': r_rl_delay,
         'Without control': r_fixed},
        'Fig 12. Cumulative reward under communication delay (ANDES)',
        os.path.join(SAVE_DIR, 'andes_fig12_comm_delay_reward.png'),
    )
    print(f"    Normal avg = {np.mean(r_rl_normal):.4f}")
    print(f"    Delay avg  = {np.mean(r_rl_delay):.4f}")

    # Fig 13: 0.2s 延迟下时域
    env_delay = AndesMultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0,
                                 comm_delay_steps=1)
    env_delay.reset(delta_u={"PQ_0": 1.5})
    traj = run_episode(env_delay, agents, use_rl=True)
    plot_rl_control_andes(traj, "load step 1 under 0.2s comm delay",
                          os.path.join(SAVE_DIR, 'andes_fig13_comm_delay_td.png'))


if __name__ == "__main__":
    print("=" * 60)
    print(" ANDES MADRL Evaluation")
    print("=" * 60)

    agents = load_agents()

    # Fig 4: 训练曲线
    plot_training_curves()

    # Fig 6-7: Load Step 1 (增加负荷 at PQ_0)
    plot_load_step(agents, "Load Step 1",
                   delta_u={"PQ_0": 1.5},
                   fig_no_ctrl="andes_fig6_ls1_no_ctrl.png",
                   fig_ctrl="andes_fig7_ls1_ctrl.png")

    # Fig 8-9: Load Step 2 (减少负荷 at PQ_1)
    plot_load_step(agents, "Load Step 2",
                   delta_u={"PQ_1": -1.0},
                   fig_no_ctrl="andes_fig8_ls2_no_ctrl.png",
                   fig_ctrl="andes_fig9_ls2_ctrl.png")

    # Fig 5: 累积奖励
    plot_cumulative_reward(agents)

    # Fig 10-11: 通信故障
    plot_comm_failure_test(agents, n_test=20)

    # Fig 12-13: 通信延迟
    plot_comm_delay_test(agents, n_test=20)

    print("\n" + "=" * 60)
    print("All figures saved to results/figures/")
    print("=" * 60)
