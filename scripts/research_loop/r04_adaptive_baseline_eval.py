"""R04 — adaptive controller baseline eval (no SAC).

K_H=10, K_D=400 adaptive controller. Output paper-spec eval JSON to
`results/research_loop/eval_r04_adaptive/`.

Goal: 解耦 算法 vs 实现 问题. 若 adaptive 6-axis ≥ 0.5 = ANDES 平台 OK + SAC 还有
空间; 若 adaptive 6-axis 也 < 0.05 = 实现/平台问题, R05 必须查 V2 env physics.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from env.andes.andes_vsg_env_v2 import AndesMultiVSGEnvV2  # noqa: E402

K_H = 10.0
K_D = 400.0
DM_RANGE_HALF = (AndesMultiVSGEnvV2.DM_MAX - AndesMultiVSGEnvV2.DM_MIN) / 2
DD_RANGE_HALF = (AndesMultiVSGEnvV2.DD_MAX - AndesMultiVSGEnvV2.DD_MIN) / 2
DM_MID = (AndesMultiVSGEnvV2.DM_MAX + AndesMultiVSGEnvV2.DM_MIN) / 2
DD_MID = (AndesMultiVSGEnvV2.DD_MAX + AndesMultiVSGEnvV2.DD_MIN) / 2
F_NOM = AndesMultiVSGEnvV2.FN
OMEGA_SCALE = F_NOM * 2 * np.pi  # rad/s

SCENARIOS = {
    "load_step_1": {"PQ_Bus14": -2.48},
    "load_step_2": {"PQ_Bus15":  1.88},
}


def adaptive_action_for_obs(o):
    """Adaptive controller per agent: action ∝ K_H * d_omega + K_D * omega_dot.

    obs[i][1] = d_omega[i] / 3.0  (rad/s deviation, normalized)
    obs[i][2] = omega_dot[i] * OMEGA_SCALE / 5.0  (rad/s², normalized)
    """
    d_omega   = o[1] * 3.0
    omega_dot = o[2] * 5.0 / OMEGA_SCALE  # back to p.u./s
    # raw action in physical units (ΔM / ΔD)
    delta_m_phys = K_H * d_omega                # ΔH ∝ K_H * Δω
    delta_d_phys = K_D * omega_dot              # ΔD ∝ K_D * dω/dt
    # normalize to [-1, 1] env action space (zero-centered)
    a0 = delta_m_phys / DM_RANGE_HALF if DM_RANGE_HALF > 0 else 0.0
    a1 = delta_d_phys / DD_RANGE_HALF if DD_RANGE_HALF > 0 else 0.0
    return np.array([np.clip(a0, -1, 1), np.clip(a1, -1, 1)], dtype=np.float32)


def eval_one(scenario_name, delta_u, controller_label, seed=42):
    env = AndesMultiVSGEnvV2(random_disturbance=False, comm_fail_prob=0.0)
    env.seed(seed)
    obs = env.reset(delta_u=delta_u)

    N = env.N_AGENTS
    traces, cum_rf, max_df, osc = [], 0.0, 0.0, 0.0

    for step in range(env.STEPS_PER_EPISODE):
        if controller_label.startswith("adaptive"):
            actions = {i: adaptive_action_for_obs(obs[i]) for i in range(N)}
        else:
            actions = {i: np.zeros(2, dtype=np.float32) for i in range(N)}

        obs, _, done, info = env.step(actions)
        if info.get("tds_failed", False):
            break

        freq_hz = info["freq_hz"].astype(float).tolist()
        delta_f = [(f - F_NOM) for f in freq_hz]
        f_bar = float(np.mean(freq_hz))
        step_rf = float(np.mean([(d - (f_bar - F_NOM)) ** 2 for d in delta_f]))
        cum_rf -= step_rf
        max_df = max(max_df, float(np.max(np.abs(delta_f))))
        osc += float(np.std(delta_f))

        traces.append({
            "step": step, "t": float(info["time"]),
            "freq_hz": freq_hz, "f_bar": f_bar, "step_rf": step_rf,
            "delta_P_es": info["P_es"].astype(float).tolist(),
            "delta_f_es": delta_f,
            "M_es": info["M_es"].astype(float).tolist(),
            "D_es": info["D_es"].astype(float).tolist(),
            "delta_M": info["delta_M"].astype(float).tolist(),
            "delta_D": info["delta_D"].astype(float).tolist(),
        })
        if done:
            break

    env.close()
    return {"controller": controller_label, "scenario": scenario_name,
            "cum_rf_total": cum_rf, "max_df": max_df, "osc": osc,
            "n_steps": len(traces), "traces": traces}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default="results/research_loop/eval_r04_adaptive")
    args = p.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    label = f"adaptive_K{int(K_H)}_K{int(K_D)}"
    print(f"[adaptive] K_H={K_H}, K_D={K_D}")
    for scen, du in SCENARIOS.items():
        print(f"[adaptive] {label} on {scen}")
        rep = eval_one(scen, du, label)
        (out / f"{label}_{scen}.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
        print(f"  cum_rf={rep['cum_rf_total']:+.4f}  max_df={rep['max_df']:.3f} Hz")
    print(f"[adaptive] done -> {out}")


if __name__ == "__main__":
    main()
