"""
Prop.1 三条件数值验证 (M5)
===========================

论文 Prop.1: 在以下三个条件同时满足时，所有节点 Δω_i 在数值精度内收敛到同一值:

  1. H/D 比例条件: H_i/D_i = c (常数) 对所有 i 成立
     等价: H_i = k_i * H_ref, D_i = k_i * D_ref
  2. 输入比例条件: Δu_i = k_i * u_0 (各节点扰动与 k_i 成比例)
  3. 网络连通条件: L 为连通图 Laplacian (L 仅一个零特征值)

任一条不满足时, 节点间 Δω 应当出现分歧 (不等).

参考: env/ode/power_system.py, env/ode/NOTES.md
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from env.ode.power_system import PowerSystem
from env.network_topology import build_laplacian


# ────────────────────────────────────────────────────────
#  工具函数
# ────────────────────────────────────────────────────────

def _make_ring_L(N, b=4.0):
    """N 节点环形 Laplacian (连通图)."""
    B = np.zeros((N, N))
    for i in range(N):
        j = (i + 1) % N
        B[i, j] = b
        B[j, i] = b
    return build_laplacian(B, np.ones(N))


def _run_sim(L, H_arr, D_arr, delta_u, T=10.0, dt=0.1, fn=50.0):
    """运行仿真并返回最终 Δω 向量."""
    ps = PowerSystem(L, H_arr, D_arr, dt=dt, fn=fn)
    ps.reset(delta_u=delta_u)
    steps = int(T / dt)
    result = None
    for _ in range(steps):
        result = ps.step()
    return result['omega']


# ────────────────────────────────────────────────────────
#  Test 1: 三条件全满足 → 所有节点 Δω 一致
# ────────────────────────────────────────────────────────

def test_prop1_all_conditions_met():
    """H/D 比例 + 输入比例 + 连通 L → 所有 Δω 应在数值精度内一致."""
    N = 4
    k = np.array([1.0, 1.5, 0.8, 1.2])   # 各节点缩放系数
    H_ref, D_ref = 24.0, 18.0
    u0 = 1.0                               # 公共参考扰动

    H_arr = k * H_ref                     # H_i/D_i = H_ref/D_ref 对所有 i 成立
    D_arr = k * D_ref
    delta_u = k * u0                      # Δu_i = k_i * u0

    L = _make_ring_L(N, b=4.0)            # 连通环形 Laplacian (条件 3)

    omega_final = _run_sim(L, H_arr, D_arr, delta_u)

    omega_mean = omega_final.mean()
    max_dev = np.max(np.abs(omega_final - omega_mean))
    assert max_dev < 1e-3, (
        f"Prop.1 三条件均满足时所有节点 Δω 应收敛一致, "
        f"但最大偏差 = {max_dev:.6f} rad/s"
    )


# ────────────────────────────────────────────────────────
#  Test 2: H/D 比例条件不满足 → 节点 Δω 不一致
# ────────────────────────────────────────────────────────

def test_prop1_hd_ratio_violated():
    """H/D 比例条件不满足 → Δω 不等 (验证测试能够失败)."""
    N = 4
    # 不同 H/D 比: 节点 0 和节点 2 的 H/D 差 2 倍
    H_arr = np.array([24.0, 24.0, 48.0, 24.0])
    D_arr = np.array([18.0, 18.0,  9.0, 18.0])   # H2/D2 = 48/9 ≠ 24/18
    delta_u = np.array([1.0, 1.0, 1.0, 1.0])     # 均匀扰动 (非比例)

    L = _make_ring_L(N, b=4.0)

    omega_final = _run_sim(L, H_arr, D_arr, delta_u)
    max_dev = np.max(np.abs(omega_final - omega_final.mean()))

    # 条件不满足时, 节点应当分歧
    assert max_dev > 1e-4, (
        f"H/D 比例条件不满足时应出现节点间分歧, 但 max_dev={max_dev:.6f}"
    )


# ────────────────────────────────────────────────────────
#  Test 3: 输入比例条件不满足 → 节点 Δω 不一致
# ────────────────────────────────────────────────────────

def test_prop1_input_ratio_violated():
    """Δu 不与 k_i 成比例 → Δω 不等."""
    N = 4
    k = np.array([1.0, 1.5, 0.8, 1.2])
    H_arr = k * 24.0
    D_arr = k * 18.0

    # 扰动不按 k_i 缩放 (打破输入比例条件)
    delta_u = np.array([2.4, 0.0, -2.4, 0.0])

    L = _make_ring_L(N, b=4.0)

    omega_final = _run_sim(L, H_arr, D_arr, delta_u)
    max_dev = np.max(np.abs(omega_final - omega_final.mean()))

    assert max_dev > 1e-4, (
        f"输入比例条件不满足时应出现节点间分歧, 但 max_dev={max_dev:.6f}"
    )


# ────────────────────────────────────────────────────────
#  Test 4: 网络条件 — L 是真实连通 Laplacian (非对角或断开)
# ────────────────────────────────────────────────────────

def test_prop1_network_laplacian_connected():
    """验证测试用 L 的连通性: 恰好一个零特征值 (Prop.1 前提)."""
    N = 4
    L = _make_ring_L(N, b=4.0)
    eigenvalues = np.linalg.eigvalsh(L)
    n_zero = np.sum(np.abs(eigenvalues) < 1e-10)
    assert n_zero == 1, (
        f"连通图 Laplacian 应有且仅有 1 个零特征值, 得到 {n_zero}; "
        f"eigenvalues={eigenvalues}"
    )


# ────────────────────────────────────────────────────────
#  Test 5: 断开网络 (两个孤立子图) — Prop.1 不成立
# ────────────────────────────────────────────────────────

def test_prop1_disconnected_network_fails():
    """断开图 → 两个孤立子图各自平衡, 全局 Δω 不等."""
    N = 4
    # 两条断链: {0-1} 和 {2-3} 各自独立
    B = np.zeros((N, N))
    B[0, 1] = B[1, 0] = 4.0
    B[2, 3] = B[3, 2] = 4.0
    L = build_laplacian(B, np.ones(N))

    k = np.array([1.0, 1.0, 1.0, 1.0])
    H_arr = k * 24.0
    D_arr = k * 18.0

    # 在两个子图上施加不同量级扰动
    delta_u = np.array([3.0, 3.0, 0.5, 0.5])

    omega_final = _run_sim(L, H_arr, D_arr, delta_u)
    max_dev = np.max(np.abs(omega_final - omega_final.mean()))

    # 断开网络: 两子图各自平衡, 全局 Δω 不一致
    assert max_dev > 1e-4, (
        f"断开网络时两子图 Δω 应不同, 但 max_dev={max_dev:.6f}"
    )
