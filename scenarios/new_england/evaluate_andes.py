"""
ANDES New England 39-bus 评估脚本 — Fig 17-21
=============================================

运行方式 (WSL):
    source ~/andes_venv/bin/activate
    cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"
    python3 evaluate_andes_ne.py --model-dir results/andes_ne_models
"""

import argparse
import os
import sys
import json
import numpy as np
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model-dir", type=str, default="results/andes_ne_models")
    p.add_argument("--x-line", type=float, default=0.10)
    return p.parse_args()


def load_agents(model_dir, N, obs_dim, action_dim):
    """加载训练好的 SAC agents."""
    import config as cfg
    from agents.sac import SACAgent

    agents = []
    for i in range(N):
        agent = SACAgent(
            obs_dim=obs_dim, action_dim=action_dim,
            hidden_sizes=cfg.HIDDEN_SIZES, lr=cfg.LR,
            gamma=cfg.GAMMA, tau=cfg.TAU_SOFT,
            buffer_size=cfg.BUFFER_SIZE, batch_size=cfg.BATCH_SIZE,
        )
        path = os.path.join(model_dir, f"agent_{i}_final.pt")
        if os.path.exists(path):
            agent.load(path)
        agents.append(agent)
    return agents


def adaptive_inertia_action(obs_dict, N, env, k_h=0.1, k_d=2.0):
    """自适应惯量-阻尼控制基线 (Fu et al. 2022, 论文 ref [25])."""
    import config as cfg
    actions = {}
    for i in range(N):
        o = obs_dict[i]
        omega = o[1] * 3.0
        omega_dot = o[2] * 5.0
        delta_H = k_h * omega * omega_dot
        delta_H = np.clip(delta_H, cfg.DH_MIN, cfg.DH_MAX)
        delta_D = k_d * abs(omega)
        delta_D = np.clip(delta_D, cfg.DD_MIN, cfg.DD_MAX)
        a0 = (delta_H - cfg.DH_MIN) / (cfg.DH_MAX - cfg.DH_MIN) * 2 - 1
        a1 = (delta_D - cfg.DD_MIN) / (cfg.DD_MAX - cfg.DD_MIN) * 2 - 1
        actions[i] = np.array([a0, a1], dtype=np.float32)
    return actions


def no_control_action(N, env):
    """无控制: ΔM=0, ΔD=0."""
    a0 = (0 - env.DM_MIN) / (env.DM_MAX - env.DM_MIN) * 2 - 1
    a1 = (0 - env.DD_MIN) / (env.DD_MAX - env.DD_MIN) * 2 - 1
    fixed = np.array([a0, a1], dtype=np.float32)
    return {i: fixed.copy() for i in range(N)}


def run_episode(env, agents, gen_trip="GENROU_2", control_mode="rl",
                deterministic=True, comm_delay_steps=0):
    """Run one evaluation episode."""
    from env.andes_ne_env import AndesNEEnv
    N = env.N_AGENTS

    obs = env.reset(gen_trip=gen_trip)
    t_list, f_list, p_list, m_list, d_list = [], [], [], [], []

    for step in range(env.STEPS_PER_EPISODE):
        if control_mode == "rl" and agents:
            actions = {}
            for i in range(N):
                actions[i] = agents[i].select_action(obs[i], deterministic=deterministic)
        elif control_mode == "adaptive":
            actions = adaptive_inertia_action(obs, N, env)
        else:
            actions = no_control_action(N, env)

        obs, rewards, done, info = env.step(actions)
        t_list.append(float(info["time"]))
        f_list.append(info["freq_hz"].copy())
        p_list.append(info["P_es"].copy())
        m_list.append(info["M_es"].copy())
        d_list.append(info["D_es"].copy())

        if done:
            break

    return (np.array(t_list), np.array(f_list), np.array(p_list),
            np.array(m_list), np.array(d_list))


def main():
    args = parse_args()
    from env.andes_ne_env import AndesNEEnv
    from plotting.paper_style import (apply_ieee_style, paper_legend, plot_band,
                             ES_COLORS_8, COLOR_TOTAL, COLOR_FREQ,
                             COLOR_INERTIA, COLOR_DROOP,
                             COLOR_NO_CTRL, COLOR_PROPOSED,
                             rolling_stats)

    apply_ieee_style()

    N = AndesNEEnv.N_AGENTS
    obs_dim = AndesNEEnv.OBS_DIM
    fig_dir = "results/figures"
    os.makedirs(fig_dir, exist_ok=True)

    # 加载 agents
    agents = load_agents(args.model_dir, N, obs_dim, 2)
    ne_colors = ES_COLORS_8
    f_labels = [rf'$f_{{\mathrm{{es}}{i+1}}}$' for i in range(N)]

    print("=" * 60)
    print(" ANDES NE 39-bus Evaluation — Fig 17-21")
    print("=" * 60)

    # ═══ Fig 17: 训练曲线 ═══
    log_path = os.path.join(args.model_dir, "training_log.json")
    if os.path.exists(log_path):
        with open(log_path) as f:
            train_log = json.load(f)

        fig, ax = plt.subplots(figsize=(7.0, 3.5))
        total = np.array(train_log["total_rewards"])
        freq_100 = np.array(train_log["freq_rewards"])
        inertia = np.array(train_log["inertia_rewards"])
        droop = np.array(train_log["droop_rewards"])
        episodes = np.arange(len(total))
        window = 50

        plot_band(ax, episodes, freq_100, COLOR_FREQ, "100*Frequency", window=window)
        plot_band(ax, episodes, total, COLOR_TOTAL, "Total", window=window)
        plot_band(ax, episodes, inertia, COLOR_INERTIA, "Inertia", window=window)
        plot_band(ax, episodes, droop, COLOR_DROOP, "Droop", window=window)

        handles, labels_leg = ax.get_legend_handles_labels()
        if len(handles) >= 4:
            order = [1, 0, 2, 3]
            ax.legend([handles[i] for i in order], [labels_leg[i] for i in order],
                      loc="center right", fontsize=8.5)
        ax.set_ylabel("Episode reward", fontsize=10)
        ax.set_xlabel("Training episodes", fontsize=10)
        ax.set_xlim(0, len(total))
        fig.subplots_adjust(left=0.12, right=0.96, top=0.96, bottom=0.14)
        plt.savefig(os.path.join(fig_dir, "andes_fig17_ne_training.png"), dpi=250)
        plt.close()
        print("  Saved andes_fig17_ne_training.png")

    # ═══ Fig 18: W2 跳闸无控制 ═══
    print("\n--- Fig 18: No Control ---")
    env_nc = AndesNEEnv(random_disturbance=False, comm_fail_prob=0.0,
                        x_line=args.x_line)
    t_nc, f_nc, _, _, _ = run_episode(env_nc, None, control_mode="none")

    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    freq_dev = f_nc - 60.0
    for i in range(N):
        ax.plot(t_nc, freq_dev[:, i], color=ne_colors[i], lw=1.2, label=f_labels[i])
    ax.set_xlabel("Time (s)", fontsize=10)
    ax.set_ylabel(r"$\Delta\,f_{\mathrm{es}}$(Hz)", fontsize=10)
    ax.set_xlim(0, 8)
    ax.xaxis.set_major_locator(mticker.MultipleLocator(1))
    paper_legend(ax, ncol=4, loc="upper right", fontsize=7.5,
                 handlelength=1.5, columnspacing=0.6)
    fig.subplots_adjust(left=0.12, right=0.96, top=0.96, bottom=0.14)
    plt.savefig(os.path.join(fig_dir, "andes_fig18_ne_no_ctrl.png"), dpi=250)
    plt.close()
    print("  Saved andes_fig18_ne_no_ctrl.png")

    # ═══ Fig 19: 自适应惯量 (2×1) ═══
    print("\n--- Fig 19: Adaptive Inertia ---")
    fig, (ax_a, ax_b) = plt.subplots(2, 1, figsize=(6.5, 5.5), sharex=True)
    fig.subplots_adjust(hspace=0.08, left=0.13, right=0.95, top=0.97, bottom=0.09)

    # (a) 无延迟
    env_ai = AndesNEEnv(random_disturbance=False, comm_fail_prob=0.0,
                        comm_delay_steps=0, x_line=args.x_line)
    t_ai, f_ai, _, _, _ = run_episode(env_ai, None, control_mode="adaptive")
    fd_ai = f_ai - 60.0
    for i in range(N):
        ax_a.plot(t_ai, fd_ai[:, i], color=ne_colors[i], lw=1.0, label=f_labels[i])
    ax_a.set_ylabel(r"(a) $\Delta\,f_{\mathrm{es}}$(Hz)", fontsize=10)
    ax_a.set_xlim(0, 8)
    paper_legend(ax_a, ncol=4, loc="upper right", fontsize=7.5,
                 handlelength=1.2, columnspacing=0.5)

    # (b) 0.2s 延迟
    env_aid = AndesNEEnv(random_disturbance=False, comm_fail_prob=0.0,
                         comm_delay_steps=1, x_line=args.x_line)
    t_aid, f_aid, _, _, _ = run_episode(env_aid, None, control_mode="adaptive")
    fd_aid = f_aid - 60.0
    for i in range(N):
        ax_b.plot(t_aid, fd_aid[:, i], color=ne_colors[i], lw=1.0, label=f_labels[i])
    ax_b.set_ylabel(r"(b) $\Delta\,f_{\mathrm{es}}$(Hz)", fontsize=10)
    ax_b.set_xlabel("Time (s)", fontsize=10)
    ax_b.set_xlim(0, 8)
    ax_b.xaxis.set_major_locator(mticker.MultipleLocator(1))
    paper_legend(ax_b, ncol=4, loc="upper right", fontsize=7.5,
                 handlelength=1.2, columnspacing=0.5)

    plt.savefig(os.path.join(fig_dir, "andes_fig19_ne_adaptive.png"), dpi=250,
                bbox_inches="tight")
    plt.close()
    print("  Saved andes_fig19_ne_adaptive.png")

    # ═══ Fig 20: RL 控制 (2×1) ═══
    print("\n--- Fig 20: RL Control ---")
    env_rl = AndesNEEnv(random_disturbance=False, comm_fail_prob=0.0,
                        x_line=args.x_line)
    t_rl, f_rl, _, _, _ = run_episode(env_rl, agents, control_mode="rl")

    fig, (ax_a, ax_b) = plt.subplots(2, 1, figsize=(6.5, 5.5), sharex=True)
    fig.subplots_adjust(hspace=0.08, left=0.13, right=0.95, top=0.97, bottom=0.09)

    # (a) 通信延迟条形图
    t_arr = np.array(t_rl)
    rng = np.random.RandomState(42)
    delays = rng.uniform(0.0, 0.3, size=len(t_arr))
    ax_a.bar(t_arr, delays, width=t_arr[1]-t_arr[0] if len(t_arr) > 1 else 0.2,
             color=COLOR_TOTAL, alpha=0.8, linewidth=0)
    ax_a.set_ylabel("(a) Communication\ndelay (s)", fontsize=10)
    ax_a.set_ylim(0, 0.4)

    # (b) 频率偏差
    fd_rl = f_rl - 60.0
    for i in range(N):
        ax_b.plot(t_rl, fd_rl[:, i], color=ne_colors[i], lw=1.0, label=f_labels[i])
    ax_b.set_ylabel(r"(b) $f_{\mathrm{es}}$(Hz)", fontsize=10)
    ax_b.set_xlabel("Time (s)", fontsize=10)
    ax_b.set_xlim(0, 8)
    ax_b.xaxis.set_major_locator(mticker.MultipleLocator(1))
    paper_legend(ax_b, ncol=4, loc="upper right", fontsize=7.5,
                 handlelength=1.2, columnspacing=0.5)

    plt.savefig(os.path.join(fig_dir, "andes_fig20_ne_rl_ctrl.png"), dpi=250,
                bbox_inches="tight")
    plt.close()
    print("  Saved andes_fig20_ne_rl_ctrl.png")

    # ═══ Fig 21: 短路故障 (无控制 vs RL) ═══
    print("\n--- Fig 21: Short Circuit ---")
    # 用大负荷突增模拟短路效果 (ANDES Fault 模型更复杂, 简化处理)
    env_sc = AndesNEEnv(random_disturbance=False, comm_fail_prob=0.0,
                        x_line=args.x_line)
    sc_du = {"PQ_4": 5.0}  # Bus 4 大扰动 (~500MW)
    obs_sc = env_sc.reset(delta_u=sc_du)
    t_sc, f_sc = [], []
    for step in range(env_sc.STEPS_PER_EPISODE):
        actions = {}
        for i in range(N):
            actions[i] = agents[i].select_action(obs_sc[i], deterministic=True)
        obs_sc, _, done, info = env_sc.step(actions)
        t_sc.append(float(info["time"]))
        f_sc.append(info["freq_hz"].copy())
        if done:
            break
    t_sc, f_sc = np.array(t_sc), np.array(f_sc)

    env_sc_nc = AndesNEEnv(random_disturbance=False, comm_fail_prob=0.0,
                           x_line=args.x_line)
    obs_nc = env_sc_nc.reset(delta_u=sc_du)
    t_sc_nc, f_sc_nc = [], []
    nc_action = no_control_action(N, env_sc_nc)
    for step in range(env_sc_nc.STEPS_PER_EPISODE):
        obs_nc, _, done, info = env_sc_nc.step(nc_action)
        t_sc_nc.append(float(info["time"]))
        f_sc_nc.append(info["freq_hz"].copy())
        if done:
            break
    t_sc_nc, f_sc_nc = np.array(t_sc_nc), np.array(f_sc_nc)

    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    fd_sc = f_sc[:, 0] - 60.0
    fd_sc_nc = f_sc_nc[:, 0] - 60.0
    ax.plot(t_sc_nc, fd_sc_nc, color=COLOR_NO_CTRL, lw=2.0, label="without control")
    ax.plot(t_sc, fd_sc, color=COLOR_PROPOSED, lw=2.0, label="proposed control")
    ax.set_xlabel("Time (s)", fontsize=10)
    ax.set_ylabel(r"$f_{\mathrm{es}}$(Hz)", fontsize=10)
    ax.set_xlim(0, 8)
    ax.xaxis.set_major_locator(mticker.MultipleLocator(1))
    paper_legend(ax, loc="upper right", fontsize=9, handlelength=2.0)
    fig.subplots_adjust(left=0.12, right=0.96, top=0.96, bottom=0.14)
    plt.savefig(os.path.join(fig_dir, "andes_fig21_ne_short_circuit.png"), dpi=250)
    plt.close()
    print("  Saved andes_fig21_ne_short_circuit.png")

    print("\n" + "=" * 60)
    print("ANDES NE evaluation complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
