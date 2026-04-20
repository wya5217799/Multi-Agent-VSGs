"""
闸门检查 — Task 1+2 完成后运行，验证 no-control 基线是否匹配论文目标。

通过条件（3项全满足）:
  主振荡频率 ∈ [0.8, 1.5] Hz
  Δf 峰值   ∈ [0.08, 0.18] Hz
  ΔP_es 峰值 ∈ [200, 500] MW

注：settle_t 已去除。ODE 模型无一次调频，H=80/D=1 → τ≈160s，
物理上不可能在 10s 内回到 ±0.02 Hz。闸门只验证区间振荡特性。
"""
import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import config as cfg
from env.ode.multi_vsg_env import MultiVSGEnv


def main():
    env = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
    obs = env.reset(delta_u=cfg.LOAD_STEP_1)

    t_log = [0.0]
    freq_log = [env.ps.get_state()['freq_hz']]
    P_log = [env.ps.get_state()['P_es']]

    for _ in range(50):   # 50步 × 0.2s = 10s
        fixed = {i: np.zeros(cfg.ACTION_DIM, dtype=np.float32) for i in range(cfg.N_AGENTS)}
        _, _, done, info = env.step(fixed)
        t_log.append(info['time'])
        freq_log.append(info['freq_hz'])
        P_log.append(info['P_es'])

    freq = np.array(freq_log)   # shape (51, 4)
    P    = np.array(P_log)      # shape (51, 4)

    freq_dev = freq - 50.0
    peak_df  = float(np.abs(freq_dev).max())
    peak_P   = float(np.abs(P * cfg.S_BASE).max())

    # FFT 估计主振荡频率
    dt = cfg.DT if hasattr(cfg, 'DT') else 0.2
    signal = freq_dev[:, 0]
    fft    = np.abs(np.fft.rfft(signal))
    freqs  = np.fft.rfftfreq(len(signal), d=dt)
    dom_f  = float(freqs[np.argmax(fft[1:]) + 1])

    print(f"主振荡频率: {dom_f:.3f} Hz  (目标 0.8~1.5)")
    print(f"Δf 峰值:   {peak_df:.4f} Hz  (目标 0.08~0.18)")
    print(f"ΔP_es 峰值:{peak_P:.1f} MW   (目标 200~500)")

    ok = ((0.8 <= dom_f <= 1.5)
          and (0.08 <= peak_df <= 0.18)
          and (200 <= peak_P <= 500))
    msg_pass = "\n[PASS] 闸门通过，可进入 RL 训练"
    msg_fail = "\n[FAIL] 闸门未通过，需调参后重新检查"
    print(msg_pass if ok else msg_fail)


if __name__ == '__main__':
    main()
