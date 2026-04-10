"""
ANDES New England 39-bus 校准脚本
================================

校准 NE ANDES 环境的基线频率响应, 对照论文 Fig.17 (W2 跳闸无控制).

校准步骤:
  1. 验证 PFlow 收敛 + bus 电压
  2. M_wind 扫描 (确认残余惯量无影响)
  3. X_line 扫描 (调节 VSG-系统耦合强度)
  4. W2 跳闸无控制基线绘图

论文 Fig.17 参考值 (从图中估读):
  - 8 台 ES 频率偏差曲线
  - 稳态频偏: ~-0.15 Hz (论文为 Simulink 全阶模型)
  - 最大瞬时频偏: ~-0.4 Hz
  - 振荡周期: ~2s
  - ES2 (最近 G2) 偏差最大

运行方式 (WSL):
    source ~/andes_venv/bin/activate
    cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"
    python3 calibrate_andes_ne.py
    python3 calibrate_andes_ne.py --sweep-xline
"""

import sys
import os
import argparse
import numpy as np
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--sweep-mwind", action="store_true",
                   help="Sweep M_wind values {0.1, 0.5, 1.0, 2.0}")
    p.add_argument("--sweep-xline", action="store_true",
                   help="Sweep X_line values {0.01, 0.05, 0.10, 0.20}")
    p.add_argument("--M0", type=float, default=20.0, help="VSG M0")
    p.add_argument("--D0", type=float, default=4.0, help="VSG D0")
    p.add_argument("--x-line", type=float, default=0.10, help="Line reactance")
    return p.parse_args()


def run_no_control_episode(env, gen_trip="GENROU_2"):
    """W2 跳闸无控制: actions = ΔM=0, ΔD=0."""
    from env.andes_ne_env import AndesNEEnv

    obs = env.reset(gen_trip=gen_trip)
    N = env.N_AGENTS

    # 无控制: ΔM=0, ΔD=0 → action = inverse map of (0,0)
    DM_MIN, DM_MAX = env.DM_MIN, env.DM_MAX
    DD_MIN, DD_MAX = env.DD_MIN, env.DD_MAX
    a0 = (0 - DM_MIN) / (DM_MAX - DM_MIN) * 2 - 1
    a1 = (0 - DD_MIN) / (DD_MAX - DD_MIN) * 2 - 1
    fixed_action = np.array([a0, a1], dtype=np.float32)

    t_list, f_list, p_list = [], [], []
    for step in range(env.STEPS_PER_EPISODE):
        actions = {i: fixed_action.copy() for i in range(N)}
        obs, rewards, done, info = env.step(actions)
        t_list.append(float(info["time"]))
        f_list.append(info["freq_hz"].copy())
        p_list.append(info["P_es"].copy())
        if done:
            break

    return np.array(t_list), np.array(f_list), np.array(p_list)


def check_bus_voltages(env):
    """检查 PFlow 后所有 bus 电压."""
    n_bus = env.ss.Bus.n
    v = env.ss.Bus.v.v
    idx = list(env.ss.Bus.idx.v)
    ok = True
    for i in range(n_bus):
        if v[i] < 0.90 or v[i] > 1.10:
            print(f"  WARNING: Bus {idx[i]} V={float(v[i]):.4f}")
            ok = False
    return ok


def main():
    args = parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from env.andes_ne_env import AndesNEEnv

    os.makedirs("results/figures", exist_ok=True)

    N = AndesNEEnv.N_AGENTS

    print("=" * 60)
    print(" ANDES New England 39-bus Calibration")
    print("=" * 60)

    # ═══ 1. 基本验证 ═══
    print("\n--- Step 1: Basic Verification ---")
    env = AndesNEEnv(random_disturbance=False, comm_fail_prob=0.0,
                     x_line=args.x_line)
    obs = env.reset(gen_trip="GENROU_2")

    print("  PFlow converged:", env.ss.PFlow.converged)
    v_ok = check_bus_voltages(env)
    print("  Bus voltages OK:", v_ok)

    # G2 跳闸验证
    g2_pos = list(env.ss.GENROU.idx.v).index("GENROU_2")
    print(f"  G2 u = {float(env.ss.GENROU.u.v[g2_pos])}")
    print(f"  G2 Pe = {float(env.ss.GENROU.Pe.v[g2_pos]):.4f} pu")

    # ═══ 2. M_wind 扫描 ═══
    if args.sweep_mwind:
        print("\n--- Step 2: M_wind Sweep ---")
        m_values = [0.1, 0.5, 1.0, 2.0]
        fig, ax = plt.subplots(figsize=(8, 5))

        for M_wf in m_values:
            env_m = AndesNEEnv(random_disturbance=False, comm_fail_prob=0.0,
                               x_line=args.x_line)
            # Temporarily override wind farm M
            env_m.WIND_FARM_M = M_wf
            t, f, p = run_no_control_episode(env_m)
            freq_dev = f - 60.0
            ax.plot(t, freq_dev[:, 0], label=f"M_wind={M_wf}")
            print(f"  M_wind={M_wf}: SS df={float(freq_dev[-1, 0]):.4f} Hz, "
                  f"Peak df={float(freq_dev[:, 0].min()):.4f} Hz")

        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Δf VSG_1 (Hz)")
        ax.set_title("M_wind Sweep (X_line=" + str(args.x_line) + ")")
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig("results/figures/calibration_ne_mwind.png", dpi=150)
        print("  Saved calibration_ne_mwind.png")
        plt.close()

    # ═══ 3. X_line 扫描 ═══
    if args.sweep_xline:
        print("\n--- Step 3: X_line Sweep ---")
        x_values = [0.01, 0.05, 0.10, 0.20]
        fig, axes = plt.subplots(2, 2, figsize=(12, 8))

        for idx_x, x_val in enumerate(x_values):
            env_x = AndesNEEnv(random_disturbance=False, comm_fail_prob=0.0,
                               x_line=x_val)
            t, f, p = run_no_control_episode(env_x)
            freq_dev = f - 60.0

            ax = axes[idx_x // 2, idx_x % 2]
            colors = plt.cm.tab10(np.linspace(0, 1, N))
            for i in range(N):
                ax.plot(t, freq_dev[:, i], color=colors[i], lw=1.0,
                        label=f"ES{i+1}")
            ax.set_title(f"X_line={x_val}")
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Δf (Hz)")
            ax.grid(True, alpha=0.3)
            if idx_x == 0:
                ax.legend(fontsize=6, ncol=4)

            ss_df = float(np.mean(freq_dev[-1, :]))
            peak_df = float(freq_dev.min())
            print(f"  X_line={x_val}: SS df_mean={ss_df:.4f} Hz, "
                  f"Peak df={peak_df:.4f} Hz")

            # 功率分布
            ss_p = p[-1, :]
            print(f"    Power: " +
                  " ".join([f"ES{i+1}={float(ss_p[i])*200:.0f}MW" for i in range(N)]))

        plt.tight_layout()
        plt.savefig("results/figures/calibration_ne_xline.png", dpi=150)
        print("  Saved calibration_ne_xline.png")
        plt.close()

    # ═══ 4. 默认参数基线 ═══
    print(f"\n--- Step 4: Baseline (M0={args.M0}, D0={args.D0}, X={args.x_line}) ---")
    env_base = AndesNEEnv(random_disturbance=False, comm_fail_prob=0.0,
                          x_line=args.x_line)
    t, f, p = run_no_control_episode(env_base)
    freq_dev = f - 60.0

    print("  Steady-state freq deviations:")
    for i in range(N):
        print(f"    VSG_{i+1}: df={float(freq_dev[-1, i]):.4f} Hz, "
              f"peak={float(freq_dev[:, i].min()):.4f} Hz, "
              f"P_ss={float(p[-1, i])*200:.1f} MW")

    # 绘制基线图 (论文 Fig.17 风格)
    fig, ax = plt.subplots(figsize=(7, 4))
    colors = plt.cm.tab10(np.linspace(0, 1, N))
    for i in range(N):
        ax.plot(t, freq_dev[:, i], color=colors[i], lw=1.2,
                label=f"$f_{{es{i+1}}}$")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Δf (Hz)")
    ax.set_title("W2 Trip - No Control (ANDES NE 39-bus)")
    ax.legend(ncol=4, fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 8)
    plt.tight_layout()
    plt.savefig("results/figures/calibration_ne_baseline.png", dpi=150)
    print("  Saved calibration_ne_baseline.png")
    plt.close()

    print("\nCalibration complete!")


if __name__ == "__main__":
    main()
