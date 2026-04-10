"""
ANDES VSG 波形校准脚本
====================

对比论文 Fig.6/Fig.8 无控制基线波形, 校准 VSG 的 M₀(=2H₀) 和 D₀.

校准目标 (Yang et al. TPWRS 2023, Fig.6, Load Step 1):
  - 稳态频率偏差: +0.075 Hz
  - 频率峰值 (最大): +0.13 Hz
  - 振荡周期: ≈ 1.8 s
  - 5% 整定时间: ≈ 4-5 s

校准优先级:
  1. D₀ → 决定稳态 Δf (大 D → 小 Δf)
  2. M₀ → 决定振荡周期 (大 M → 慢振荡)

运行方式 (WSL):
    source ~/andes_venv/bin/activate
    cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"

    # 单次运行 (当前参数)
    python3 calibrate_andes.py

    # 参数扫描
    python3 calibrate_andes.py --sweep

    # 指定 M₀, D₀
    python3 calibrate_andes.py --M0 10.0 --D0 5.0

    # Load Step 2 验证
    python3 calibrate_andes.py --step2
"""

import sys
import os
import argparse
import numpy as np
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


# ─── 校准目标 (从论文 Fig.6 / Fig.8 提取) ───
TARGETS = {
    "step1": {
        "label": "Load Step 1 (Bus14 reduce 248MW)",
        "pq_idx": "PQ_Bus14",      # 扩展拓扑中 Bus 14 的负荷
        "delta_p": -2.48,           # 减载 248 MW (100MVA base)
        "ss_freq_hz": +0.075,       # 稳态频率偏差 (Hz)
        "peak_freq_hz": +0.13,      # 频率峰值 (Hz)
        "osc_period_s": 1.8,        # 振荡周期 (s)
        "settling_s": 4.5,          # 5% 整定时间
    },
    "step2": {
        "label": "Load Step 2 (Bus15 increase 188MW)",
        "pq_idx": "PQ_Bus15",      # 扩展拓扑中 Bus 15 的负荷
        "delta_p": +1.88,           # 增载 188 MW
        "ss_freq_hz": -0.055,
        "peak_freq_hz": -0.08,
        "osc_period_s": 1.8,
        "settling_s": 4.5,
    },
}


def run_no_control(M0, D0, pq_idx, delta_p, n_steps=100, dt=0.1):
    """运行无控制基线仿真 (使用扩展拓扑).

    Parameters
    ----------
    M0 : float
        VSG 惯量 M = 2H (s)
    D0 : float
        VSG 阻尼 D (p.u.)
    pq_idx : str
        PQ 负荷 idx (如 "PQ_Bus14")
    delta_p : float
        负荷增量 (p.u., 正=增载, 负=减载)
    n_steps : int
        仿真步数
    dt : float
        每步时长 (s), 默认 0.1s 获取更细分辨率

    Returns
    -------
    dict with keys: time, freq_hz (N_AGENTS,), P_es (N_AGENTS,), omega_pu
    """
    from env.andes_vsg_env import AndesMultiVSGEnv

    # 临时覆盖类属性
    orig_M0, orig_D0 = AndesMultiVSGEnv.VSG_M0, AndesMultiVSGEnv.VSG_D0
    AndesMultiVSGEnv.VSG_M0 = M0
    AndesMultiVSGEnv.VSG_D0 = D0
    # 更新 scale (因为类属性在定义时计算, 需手动更新)
    scale_m = 0.5 * M0
    scale_d = 0.5 * D0
    AndesMultiVSGEnv._SCALE_M = scale_m
    AndesMultiVSGEnv._SCALE_D = scale_d
    AndesMultiVSGEnv.DM_MIN = -1.0 * scale_m
    AndesMultiVSGEnv.DM_MAX = 3.0 * scale_m
    AndesMultiVSGEnv.DD_MIN = -1.0 * scale_d
    AndesMultiVSGEnv.DD_MAX = 3.0 * scale_d

    try:
        env = AndesMultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
        env.M0 = np.full(4, M0)
        env.D0 = np.full(4, D0)

        env.reset(delta_u={pq_idx: delta_p})
        ss = env.ss

        # 无控制动作: 映射到 ΔM=0, ΔD=0
        a0 = (0 - env.DM_MIN) / (env.DM_MAX - env.DM_MIN) * 2 - 1
        a1 = (0 - env.DD_MIN) / (env.DD_MAX - env.DD_MIN) * 2 - 1
        no_ctrl_actions = {i: np.array([a0, a1]) for i in range(4)}

        times = []
        freq_hz_list = []
        P_es_list = []

        for step in range(n_steps):
            obs, rewards, done, info = env.step(no_ctrl_actions)
            times.append(info["time"] - 0.5)
            freq_hz_list.append(info["freq_hz"].copy())
            P_es_list.append(info["P_es"].copy())

        # 获取完整时间序列
        t_full, genrou_omega, vsg_omega_ts = env.get_all_omega_timeseries()

        return {
            "time": np.array(times),
            "freq_hz": np.array(freq_hz_list),
            "P_es": np.array(P_es_list),
            "omega_pu": np.array(freq_hz_list) / 50.0,
            "t_full": t_full,
            "genrou_omega": genrou_omega,
            "vsg_omega_ts": vsg_omega_ts,
            "Sn": AndesMultiVSGEnv.VSG_SN,
        }
    finally:
        # 恢复原始类属性
        AndesMultiVSGEnv.VSG_M0 = orig_M0
        AndesMultiVSGEnv.VSG_D0 = orig_D0
        scale_m = 0.5 * orig_M0
        scale_d = 0.5 * orig_D0
        AndesMultiVSGEnv._SCALE_M = scale_m
        AndesMultiVSGEnv._SCALE_D = scale_d
        AndesMultiVSGEnv.DM_MIN = -1.0 * scale_m
        AndesMultiVSGEnv.DM_MAX = 3.0 * scale_m
        AndesMultiVSGEnv.DD_MIN = -1.0 * scale_d
        AndesMultiVSGEnv.DD_MAX = 3.0 * scale_d


def extract_metrics(data, target):
    """从仿真数据提取校准指标.

    Returns
    -------
    dict with keys: ss_freq_hz, peak_freq_hz, osc_period_s, power_peaks_MW
    """
    time = data["time"]
    freq = data["freq_hz"]       # (n_steps, 4)
    P_es = data["P_es"]          # (n_steps, 4)
    Sn = data["Sn"]

    # 频率偏差 (相对 50 Hz)
    df = freq - 50.0             # (n_steps, 4)
    df_mean = np.mean(df, axis=1)  # 4 台 VSG 平均

    # 1. 稳态频率偏差: 最后 2s 平均
    n_last = max(1, int(2.0 / (time[1] - time[0])))
    ss_freq = np.mean(df_mean[-n_last:])

    # 2. 峰值频率偏差
    if target["delta_p"] < 0:  # 减载 → 频率上升
        peak_freq = np.max(df_mean)
    else:                       # 增载 → 频率下降
        peak_freq = np.min(df_mean)

    # 3. 振荡周期: 从频率偏差的零交叉分析
    # 使用 df_mean - ss_freq 去除直流偏移
    df_ac = df_mean - ss_freq
    zero_crossings = []
    for k in range(1, len(df_ac)):
        if df_ac[k-1] * df_ac[k] < 0:
            # 线性插值找零点
            t_cross = time[k-1] + (time[k] - time[k-1]) * abs(df_ac[k-1]) / (abs(df_ac[k-1]) + abs(df_ac[k]))
            zero_crossings.append(t_cross)

    if len(zero_crossings) >= 3:
        # 半周期 → 全周期
        half_periods = np.diff(zero_crossings)
        osc_period = np.mean(half_periods[:4]) * 2  # 取前几个半周期
    else:
        osc_period = float('nan')

    # 4. 各 ES 功率峰值 (MW)
    power_peaks = np.max(np.abs(P_es - P_es[0:1, :]), axis=0) * Sn  # MW

    # 5. ES4 vs ES1 功率比
    if power_peaks[0] > 1e-3:
        power_ratio_4to1 = power_peaks[3] / power_peaks[0]
    else:
        power_ratio_4to1 = float('inf')

    return {
        "ss_freq_hz": ss_freq,
        "peak_freq_hz": peak_freq,
        "osc_period_s": osc_period,
        "power_peaks_MW": power_peaks,
        "power_ratio_4to1": power_ratio_4to1,
    }


def print_comparison(metrics, target):
    """打印指标对比."""
    print(f"\n{'Metric':<25} {'Simulated':>12} {'Target':>12} {'Error':>10}")
    print("-" * 62)

    ss = metrics["ss_freq_hz"]
    ss_t = target["ss_freq_hz"]
    print(f"{'SS freq (Hz)':<25} {ss:>+12.4f} {ss_t:>+12.4f} {ss - ss_t:>+10.4f}")

    pk = metrics["peak_freq_hz"]
    pk_t = target["peak_freq_hz"]
    print(f"{'Peak freq (Hz)':<25} {pk:>+12.4f} {pk_t:>+12.4f} {pk - pk_t:>+10.4f}")

    osc = metrics["osc_period_s"]
    osc_t = target["osc_period_s"]
    if np.isnan(osc):
        print(f"{'Osc period (s)':<25} {'N/A':>12} {osc_t:>12.2f} {'N/A':>10}")
    else:
        print(f"{'Osc period (s)':<25} {osc:>12.3f} {osc_t:>12.2f} {osc - osc_t:>+10.3f}")

    print(f"\n  Power peaks (MW): ", end="")
    for i in range(4):
        print(f"ES{i+1}={metrics['power_peaks_MW'][i]:.1f}  ", end="")
    print(f"\n  ES4/ES1 ratio: {metrics['power_ratio_4to1']:.1f}")

    # 综合误差得分
    err_ss = abs(ss - ss_t)
    err_pk = abs(pk - pk_t)
    err_osc = 0 if np.isnan(osc) else abs(osc - osc_t)
    score = err_ss * 100 + err_pk * 50 + err_osc * 10
    print(f"\n  Calibration score (lower=better): {score:.3f}")
    return score


def plot_results(data, target, M0, D0, save_path=None):
    """绘制频率和功率时域图 (对标 Fig.6 格式)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    time = data["time"]
    freq = data["freq_hz"]
    P_es = data["P_es"]
    Sn = data["Sn"]

    fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    fig.suptitle(
        f"ANDES No-Control Baseline — {target['label']}\n"
        f"M₀={M0:.1f} (H₀={M0/2:.1f}), D₀={D0:.1f}, Sn={Sn:.0f} MVA",
        fontsize=12
    )

    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    labels = ["ES1", "ES2", "ES3", "ES4"]

    # 上图: 功率
    ax = axes[0]
    for i in range(4):
        P_mw = (P_es[:, i] - P_es[0, i]) * Sn  # 功率变化量 (MW)
        ax.plot(time, P_mw, color=colors[i], label=labels[i], linewidth=1.2)
    ax.set_ylabel("ΔP (MW)")
    ax.legend(loc="upper right", ncol=4, fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.axhline(0, color="gray", linewidth=0.5)

    # 下图: 频率偏差
    ax = axes[1]
    for i in range(4):
        df = freq[:, i] - 50.0
        ax.plot(time, df, color=colors[i], label=labels[i], linewidth=1.2)

    # 标注目标线
    ax.axhline(target["ss_freq_hz"], color="red", linestyle="--",
               linewidth=0.8, label=f'Target SS={target["ss_freq_hz"]:+.3f} Hz')
    ax.axhline(target["peak_freq_hz"], color="orange", linestyle=":",
               linewidth=0.8, label=f'Target Peak={target["peak_freq_hz"]:+.3f} Hz')

    ax.set_ylabel("Δf (Hz)")
    ax.set_xlabel("Time (s)")
    ax.legend(loc="upper right", ncol=3, fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"\n  Figure saved: {save_path}")
    plt.close(fig)


def run_sweep(target_key="step1"):
    """参数扫描, 找最优 M₀/D₀ 组合."""
    target = TARGETS[target_key]
    print(f"\n{'='*60}")
    print(f"PARAMETER SWEEP — {target['label']}")
    print(f"{'='*60}")

    # 扫描范围
    M0_range = [4.0, 6.0, 8.0, 10.0, 14.0, 20.0]
    D0_range = [2.0, 5.0, 10.0, 15.0, 20.0, 30.0]

    results = []

    for M0 in M0_range:
        for D0 in D0_range:
            print(f"\n--- M₀={M0:.1f} (H₀={M0/2:.1f}), D₀={D0:.1f} ---")
            try:
                data = run_no_control(
                    M0, D0,
                    target["pq_idx"], target["delta_p"],
                    n_steps=100, dt=0.1
                )
                metrics = extract_metrics(data, target)
                score = print_comparison(metrics, target)
                results.append({
                    "M0": M0, "D0": D0, "score": score,
                    "metrics": metrics,
                })
            except Exception as e:
                print(f"  FAILED: {e}")
                results.append({"M0": M0, "D0": D0, "score": 999.0})

    # 排名
    results.sort(key=lambda r: r["score"])
    print(f"\n{'='*60}")
    print("TOP 5 PARAMETER COMBINATIONS")
    print(f"{'='*60}")
    print(f"{'Rank':>4} {'M₀':>6} {'H₀':>6} {'D₀':>6} {'Score':>8} "
          f"{'SS Δf':>8} {'Peak':>8} {'Period':>8}")
    print("-" * 62)

    for rank, r in enumerate(results[:5]):
        if "metrics" in r:
            m = r["metrics"]
            print(f"{rank+1:>4} {r['M0']:>6.1f} {r['M0']/2:>6.1f} {r['D0']:>6.1f} "
                  f"{r['score']:>8.3f} {m['ss_freq_hz']:>+8.4f} "
                  f"{m['peak_freq_hz']:>+8.4f} "
                  f"{m['osc_period_s']:>8.3f}" if not np.isnan(m['osc_period_s']) else "N/A")
        else:
            print(f"{rank+1:>4} {r['M0']:>6.1f} {r['M0']/2:>6.1f} {r['D0']:>6.1f} "
                  f"{r['score']:>8.3f}")

    best = results[0]
    print(f"\nBest: M₀={best['M0']:.1f} (H₀={best['M0']/2:.1f}), D₀={best['D0']:.1f}")
    print(f"  → Update andes_vsg_env.py: VSG_M0 = {best['M0']:.1f}, VSG_D0 = {best['D0']:.1f}")
    print(f"  → Update config.py: H_ES0 = [{best['M0']/2:.1f}]*4, D_ES0 = [{best['D0']:.1f}]*4")

    # 生成最优参数的图
    if "metrics" in best:
        data = run_no_control(
            best["M0"], best["D0"],
            target["pq_idx"], target["delta_p"],
            n_steps=100, dt=0.1
        )
        plot_results(
            data, target, best["M0"], best["D0"],
            save_path=os.path.join("results", "figures", f"calibration_best_{target_key}.png")
        )

    return results


def main():
    parser = argparse.ArgumentParser(description="ANDES VSG calibration")
    parser.add_argument("--M0", type=float, default=6.0, help="VSG M0 (=2H)")
    parser.add_argument("--D0", type=float, default=2.0, help="VSG D0")
    parser.add_argument("--sweep", action="store_true", help="Run parameter sweep")
    parser.add_argument("--step2", action="store_true", help="Use Load Step 2 instead of 1")
    parser.add_argument("--dt", type=float, default=0.1, help="Simulation time step (s)")
    parser.add_argument("--steps", type=int, default=100, help="Number of steps")
    args = parser.parse_args()

    target_key = "step2" if args.step2 else "step1"
    target = TARGETS[target_key]

    if args.sweep:
        run_sweep(target_key)
        return

    # 单次运行
    M0, D0 = args.M0, args.D0
    print(f"\n{'='*60}")
    print(f"ANDES Calibration — {target['label']}")
    print(f"M₀={M0:.1f} (H₀={M0/2:.1f}), D₀={D0:.1f}")
    print(f"{'='*60}")

    data = run_no_control(M0, D0, target["pq_idx"], target["delta_p"],
                          n_steps=args.steps, dt=args.dt)
    metrics = extract_metrics(data, target)
    print_comparison(metrics, target)

    # 保存图
    save_path = os.path.join("results", "figures",
                             f"calibration_M{M0:.0f}_D{D0:.0f}_{target_key}.png")
    plot_results(data, target, M0, D0, save_path=save_path)


if __name__ == "__main__":
    main()
