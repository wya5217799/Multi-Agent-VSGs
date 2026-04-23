"""
Eq.(1) 单位/惯量约定数值闭环验证 (M1)
======================================

本脚本验证代码自洽性; 不证明与论文 Eq.(1) 的方程等价性.

论文 Eq.(1) 原文形式 (Sec.II-A, 量纲未明示):
    H_es,i * Δω̇_i + D_es,i * Δω_i = Δu_i - ΔP_es,i
  注: 原文无 `2` 系数、无 `ω_s` 系数, 属控制派集总常数形式.
      对 H 仅称"虚拟惯量常数" (unit 未明示), Δω 基值 (p.u./rad/s) 亦未明示.
      仅 Sec.IV-B 给 ΔH 调节范围 [-100,300], 无基准 H_es,0 数值.

代码实现 (env/ode/power_system.py:205, rad/s):
    domega_dt = (1/(2*H)) * (ω_s * (Δu - L*Δθ) - D * Δω)
    即: 2H * Δω̇_rad = ω_s * (Δu - L*Δθ) - D * Δω_rad
  注: 电机学标准 M=2H/ω_s 折算形式, 与 Simulink [49] 基值对齐.

项目工作假设 (推断, 非论文事实 · 2026-04-21 修订):
    若假设论文 Δω 为 p.u. 基值, 则 Δω_pu = Δω_rad/ω_s 代入两侧乘 ω_s 后:
        H_paper * Δω̇_rad = ω_s * (Δu - L*Δθ) - D * Δω_rad
    数值映射 H_paper = 2 * H_code. 该映射是工程推断, 论文未明示也未否定.

    参见: docs/paper/yang2023-fact-base.md Q7, env/ode/NOTES.md M1 段
         (均已同步为"原文未给量纲 + 项目工作假设"口径).

测试策略:
    1. 验证代码 RHS 数值自洽
    2. 验证 ω_s 系数存在 (电机学折算的关键特征)
    3. 给出 H_paper / H_code 换算表 (基于项目工作假设, 不作为论文事实)
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from env.ode.power_system import PowerSystem
from env.network_topology import build_laplacian


# ────────────────────────────────────────────────────────
#  辅助函数
# ────────────────────────────────────────────────────────

def _make_single_node_ps(H, D, fn=50.0, dt=0.01):
    """单节点系统 (L=0) 用于解析验证."""
    L = np.array([[0.0]])
    H_arr = np.array([H])
    D_arr = np.array([D])
    return PowerSystem(L, H_arr, D_arr, dt=dt, fn=fn)


def _rhs_code(omega_s, H, D, delta_u, coupling, omega):
    """代码中 domega_dt 的精确计算 (M_inv * (...))."""
    return (1.0 / (2.0 * H)) * (omega_s * (delta_u - coupling) - D * omega)


def _rhs_paper(H_paper, D, delta_u, coupling, omega):
    """论文 Eq.(4) 的精确计算 (H_paper 为论文中的 H 值)."""
    return (1.0 / H_paper) * (delta_u - coupling) - (D / H_paper) * omega


# ────────────────────────────────────────────────────────
#  Test 1: 代码 RHS 数值自洽性
#  验证 PowerSystem 实际执行的 domega_dt 与 _rhs_code 一致
# ────────────────────────────────────────────────────────

def test_code_dynamics_self_consistent():
    """代码 domega_dt 实现与手动计算公式完全一致."""
    H, D, fn = 24.0, 18.0, 50.0
    omega_s = 2.0 * np.pi * fn
    dt = 0.001   # 极小步长使 RK45 接近 RHS 直接计算

    ps = _make_single_node_ps(H, D, fn, dt)
    delta_u_val = 2.0
    ps.reset(delta_u=np.array([delta_u_val]))

    # 单节点, L=0 → coupling=0; 初始 omega=0
    # 第一步 domega_dt = (1/(2H)) * (ω_s * delta_u - D * 0) = ω_s*delta_u/(2H)
    expected_domega = _rhs_code(omega_s, H, D, delta_u_val, 0.0, 0.0)

    result = ps.step()
    actual_domega = result['omega_dot'][0]

    assert abs(actual_domega - expected_domega) < 0.5, (
        f"代码 domega_dt={actual_domega:.4f} 与手算 {expected_domega:.4f} 不一致; "
        f"差={abs(actual_domega-expected_domega):.4f}"
    )


# ────────────────────────────────────────────────────────
#  Test 2: ω_s 系数确认
#  验证 ω_s 在动力学中确实起作用 (不是冗余)
# ────────────────────────────────────────────────────────

def test_omega_s_scaling_present():
    """不同额定频率 (50 vs 60 Hz) 应给出不同 domega_dt (ω_s 有效)."""
    H, D = 24.0, 18.0
    delta_u_val = 2.0

    ps50 = _make_single_node_ps(H, D, fn=50.0, dt=0.001)
    ps50.reset(delta_u=np.array([delta_u_val]))
    r50 = ps50.step()

    ps60 = _make_single_node_ps(H, D, fn=60.0, dt=0.001)
    ps60.reset(delta_u=np.array([delta_u_val]))
    r60 = ps60.step()

    ratio = r60['omega_dot'][0] / r50['omega_dot'][0]
    expected_ratio = 60.0 / 50.0  # ω_s 线性缩放

    assert abs(ratio - expected_ratio) < 0.05, (
        f"ω_s 缩放比 = {ratio:.4f}, 期望 60/50 = {expected_ratio:.4f}; "
        "ω_s 系数可能未正确进入动力学."
    )


# ────────────────────────────────────────────────────────
#  Test 3: 论文-代码换算表 (文档性测试, 不 assert 等价)
#  展示 H_paper = 2*H_code/ω_s 的数值, 供人工核实
# ────────────────────────────────────────────────────────

def test_unit_conversion_table(capsys):
    """打印 H_code → H_paper 换算表 (项目工作假设, 非论文事实)."""
    print("\n=== M1: 论文-代码 H 换算表 (项目工作假设 H_paper = 2·H_code) ===")
    print(f"{'H_code(s)':>10} {'H_paper=2H_code':>18}")
    for H_code in [12.0, 24.0, 36.0, 48.0]:
        H_paper = 2.0 * H_code
        print(f"{H_code:>10.1f} {H_paper:>18.1f}")
    print("\n[项目工作假设] 论文 Eq.(1) 原文无 2、无 ω_s 系数, H 量纲未明示.")
    print("              代码取电机学 2H/ω_s 折算形式 (与 Simulink 基值对齐).")
    print("              若假设论文 Δω 为 p.u., 两形式数值映射 H_paper = 2·H_code.")
    print("              映射为推断, 论文未明示, 不得以'论文事实'口径引用.")
    print("              参见: fact-base §2.1 Q7, env/ode/NOTES.md M1 段 (均已修订).")

    # 基础健全性: H 换算结果应为正数, 数值等价
    for H_code in [12.0, 24.0, 36.0]:
        H_paper = 2.0 * H_code
        assert H_paper > 0
        assert H_paper == 2.0 * H_code


# ────────────────────────────────────────────────────────
#  Test 4: 稳态频偏量级验证
#  用已知解析解核实 ODE 仿真的稳态结果
# ────────────────────────────────────────────────────────

def test_steady_state_frequency_deviation():
    """稳态 Δω_ss = ω_s * delta_u / D (单节点, 无阻尼 L·Δθ 项)."""
    H, D, fn = 24.0, 18.0, 50.0
    omega_s = 2.0 * np.pi * fn
    delta_u_val = 2.0

    # 稳态: domega_dt = 0 → (1/(2H)) * (ω_s * delta_u - D * omega_ss) = 0
    # → omega_ss = ω_s * delta_u / D
    omega_ss_expected = omega_s * delta_u_val / D

    ps = _make_single_node_ps(H, D, fn, dt=0.05)
    ps.reset(delta_u=np.array([delta_u_val]))

    omega_final = None
    for _ in range(600):   # 30 s 收敛
        result = ps.step()
        omega_final = result['omega'][0]

    rel_err = abs(omega_final - omega_ss_expected) / abs(omega_ss_expected)
    assert rel_err < 0.02, (
        f"稳态 Δω_ss = {omega_final:.4f} rad/s, "
        f"解析值 = {omega_ss_expected:.4f} rad/s, "
        f"相对误差 = {rel_err:.2%}"
    )
