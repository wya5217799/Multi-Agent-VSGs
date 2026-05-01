"""ODE Gate 3 — Reward sanity (boundary doc §18 G3 + §10.2 hard rule).

Plan: quality_reports/plans/2026-05-02_ode_paper_alignment.md (Stage 3)

Verifies the boundary doc §10.2 mean-then-square invariant and the
training/evaluation split:

  G3.a  ΔH = [+a, -a, 0, 0]  →  mean(ΔH) == 0  →  r_h_total ≡ 0   (within fp eps)
  G3.b  ΔH = [+a, +a, +a, +a] → mean(ΔH) == a  →  r_h_total == -N * φ_h * a^2
  G3.c  evaluation_reward_global on constant freq trace == 0
        evaluation_reward_global on diverging trace < 0
  G3.d  Legacy ``info['r_f' / 'r_h' / 'r_d']`` numerically equal to new
        ``info['reward_components']['r_*_total']`` (refactor preserves semantics)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from env.ode.multi_vsg_env import MultiVSGEnv  # noqa: E402
from env.ode.reward import (                    # noqa: E402
    training_reward_local,
    evaluation_reward_global,
)
import config as cfg                              # noqa: E402


def gate_3a_zero_mean_dh() -> bool:
    print("\n=== G3.a · ΔH=[+a,-a,0,0] (mean=0) → r_h_total ≡ 0 ===")
    a = 5.0
    delta_H = np.array([+a, -a, 0.0, 0.0])
    delta_D = np.zeros(4)
    omega = np.zeros(4)  # synchronous → r_f_total also 0
    out = training_reward_local(
        omega=omega, delta_H=delta_H, delta_D=delta_D,
        comm_neighbors=cfg.COMM_ADJACENCY,
        comm_eta={(i, j): 1 for i, ns in cfg.COMM_ADJACENCY.items() for j in ns},
    )
    if abs(out["r_h_total"]) > 1e-12:
        print(f"  FAIL  r_h_total={out['r_h_total']:.6e} (expected 0)")
        return False
    if abs(out["r_d_total"]) > 1e-12:
        print(f"  FAIL  r_d_total={out['r_d_total']:.6e} (expected 0)")
        return False
    print(f"  PASS  r_h_total={out['r_h_total']:.3e}, r_d_total={out['r_d_total']:.3e}")
    return True


def gate_3b_uniform_dh_penalty() -> bool:
    print("\n=== G3.b · ΔH=[+a,+a,+a,+a] (mean=a) → r_h_total == -N*φ_h*a^2 ===")
    a = 5.0
    delta_H = np.full(4, a)
    delta_D = np.zeros(4)
    omega = np.zeros(4)
    out = training_reward_local(
        omega=omega, delta_H=delta_H, delta_D=delta_D,
        comm_neighbors=cfg.COMM_ADJACENCY,
        comm_eta={(i, j): 1 for i, ns in cfg.COMM_ADJACENCY.items() for j in ns},
    )
    expected = -cfg.N_AGENTS * cfg.PHI_H * (a ** 2)   # N copies of -(a)² then weighted
    err = abs(out["r_h_total"] - expected)
    if err > 1e-9:
        print(f"  FAIL  r_h_total={out['r_h_total']:.6e}, expected={expected:.6e}, err={err:.3e}")
        return False
    print(f"  PASS  r_h_total={out['r_h_total']:.3f} (expected {expected:.3f})")
    return True


def gate_3c_eval_reward_signs() -> bool:
    print("\n=== G3.c · evaluation_reward_global: constant→0, diverging<0 ===")
    # Constant trace
    f_const = np.full((51, 4), 50.0)
    r_const = evaluation_reward_global(f_const)
    if abs(r_const) > 1e-12:
        print(f"  FAIL  constant trace gave R={r_const:.6e} (expected 0)")
        return False

    # Diverging trace
    t = np.linspace(0, 10, 51).reshape(-1, 1)
    spread = np.array([[0.0, 0.1, -0.1, 0.05]])
    f_div = 50.0 + t * spread / 10.0
    r_div = evaluation_reward_global(f_div)
    if r_div >= 0:
        print(f"  FAIL  diverging trace gave R={r_div:.6e} (expected < 0)")
        return False
    print(f"  PASS  R(const)={r_const:.3e}, R(diverging)={r_div:.3f}")
    return True


def gate_3d_legacy_keys_match_breakdown() -> bool:
    print("\n=== G3.d · info['r_*'] (legacy) == info['reward_components']['r_*_total'] ===")
    env = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
    env.reset(delta_u=np.array([1.0, 0.0, -0.5, 0.0]))
    actions = {i: np.array([0.3, -0.2], dtype=np.float32) for i in range(cfg.N_AGENTS)}
    _, _, _, info = env.step(actions)
    rc = info.get('reward_components')
    if rc is None:
        print(f"  FAIL  info['reward_components'] missing")
        return False
    err_f = abs(info['r_f'] - rc['r_f_total'])
    err_h = abs(info['r_h'] - rc['r_h_total'])
    err_d = abs(info['r_d'] - rc['r_d_total'])
    if max(err_f, err_h, err_d) > 1e-12:
        print(f"  FAIL  err_f={err_f:.3e}, err_h={err_h:.3e}, err_d={err_d:.3e}")
        return False
    # Per-agent shape sanity
    for k in ('r_f_per_agent', 'r_h_per_agent', 'r_d_per_agent'):
        if len(rc[k]) != cfg.N_AGENTS:
            print(f"  FAIL  rc['{k}'] has length {len(rc[k])}, expected {cfg.N_AGENTS}")
            return False
    print(f"  PASS  all 3 totals match within 1e-12; per-agent shapes OK")
    return True


def gate_3e_isolated_agent_rf_zero() -> bool:
    """C-1 (2026-05-02 review): isolated agent under full comm failure
    must have r_f = 0 by paper Eq.15-16 construction (only sees self).

    This is intentionally documented behaviour — paper Sec.IV-D's empirical
    'comm failure degrades synchrony' is consistent with the local synchrony
    signal vanishing for isolated agents. We assert it here so any future
    refactor that 'helpfully' falls back to a global mean trips the gate.
    """
    print("\n=== G3.e · Isolated agent (all links failed) → r_f = 0 ===")
    # Heterogeneous omega so an "honest" global mean would NOT give r_f = 0
    omega = np.array([+0.5, -0.5, +1.0, -1.0])  # rad/s
    delta_H = np.zeros(4)
    delta_D = np.zeros(4)
    out = training_reward_local(
        omega=omega, delta_H=delta_H, delta_D=delta_D,
        comm_neighbors=cfg.COMM_ADJACENCY,
        # All links failed → each agent isolated
        comm_eta={(i, j): 0 for i, ns in cfg.COMM_ADJACENCY.items() for j in ns},
    )
    rf_per = out["r_f_per_agent"]
    if any(abs(x) > 1e-12 for x in rf_per):
        print(f"  FAIL  expected r_f=0 for all isolated agents; got {rf_per}")
        return False
    print(f"  PASS  r_f_per_agent = {[round(x, 3) for x in rf_per]} "
          f"(omega heterogeneous, links all failed → isolation enforces 0)")
    return True


def main() -> int:
    print("=" * 65)
    print("  ODE Gate 3 · Reward sanity (boundary §10.2 + §11 train/eval split)")
    print("=" * 65)
    results = {
        "3a_zero_mean_dh": gate_3a_zero_mean_dh(),
        "3b_uniform_dh_penalty": gate_3b_uniform_dh_penalty(),
        "3c_eval_reward_signs": gate_3c_eval_reward_signs(),
        "3d_legacy_keys_match_breakdown": gate_3d_legacy_keys_match_breakdown(),
        "3e_isolated_agent_rf_zero": gate_3e_isolated_agent_rf_zero(),
    }
    print("\n" + "=" * 65)
    for k, v in results.items():
        print(f"  {'PASS' if v else 'FAIL':6s}  G{k}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
