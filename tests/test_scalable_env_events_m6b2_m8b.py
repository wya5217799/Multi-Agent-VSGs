"""ScalableVSGEnv 事件与非线性模式验收测试 (M6b2 + M8b).

- M6b2: LineTripEvent 通过 event_schedule 传入后, L 矩阵被重建.
- M8b: network_mode='nonlinear' 可用, 与 linear 在小扰动下数值接近.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scenarios.scalability.train import ScalableVSGEnv
from utils.ode_events import DisturbanceEvent, LineTripEvent, EventSchedule


# ────────────────────────────────────────────────────────────────
#  M6b2: LineTripEvent 接入
# ────────────────────────────────────────────────────────────────

def test_line_trip_event_modifies_L_at_reset():
    """t=0 LineTripEvent 在 reset 后立即生效, B/L 被更新."""
    env = ScalableVSGEnv(n_agents=4, random_disturbance=False)

    # 记录 trip 前 B 和 L
    B_before = env.ps.B_matrix.copy()
    L_before = env.ps.L.copy()

    schedule = EventSchedule(events=(
        DisturbanceEvent(t=0.0, delta_u=np.array([1.0, 0.0, -1.0, 0.0])),
        LineTripEvent(t=0.0, bus_i=0, bus_j=1),
    ))
    env.reset(event_schedule=schedule)

    # trip 后 B[0,1]=B[1,0]=0
    assert env.ps.B_matrix[0, 1] == 0.0
    assert env.ps.B_matrix[1, 0] == 0.0
    # 其他位置保持不变
    assert env.ps.B_matrix[1, 2] == B_before[1, 2]
    # L 矩阵被重建, 与 trip 前不一致
    assert not np.allclose(env.ps.L, L_before)


def test_line_trip_event_midway():
    """t>0 LineTripEvent 在对应 step 边界生效."""
    env = ScalableVSGEnv(n_agents=4, random_disturbance=False)
    # 1.0 s → step_idx=4 (dt=0.2)
    schedule = EventSchedule(events=(
        DisturbanceEvent(t=0.0, delta_u=np.array([1.0, 0.0, -1.0, 0.0])),
        LineTripEvent(t=1.0, bus_i=0, bus_j=1),
    ))
    env.reset(event_schedule=schedule)

    # 前 3 步 B 不变
    for _ in range(3):
        env.step({i: np.zeros(2) for i in range(env.N)})
        assert env.ps.B_matrix[0, 1] != 0.0

    # 第 4 步 (step_idx=4, t=0.8→1.0) 边界生效
    env.step({i: np.zeros(2) for i in range(env.N)})
    env.step({i: np.zeros(2) for i in range(env.N)})
    assert env.ps.B_matrix[0, 1] == 0.0


def test_line_trip_restores_on_reset():
    """连续 episode 不累积 trip — reset 恢复原始 B/L."""
    env = ScalableVSGEnv(n_agents=4, random_disturbance=False)
    B0 = env.ps.B_matrix.copy()
    L0 = env.ps.L.copy()

    schedule = EventSchedule(events=(
        DisturbanceEvent(t=0.0, delta_u=np.zeros(4)),
        LineTripEvent(t=0.0, bus_i=0, bus_j=1),
    ))
    env.reset(event_schedule=schedule)
    assert env.ps.B_matrix[0, 1] == 0.0

    env.reset(delta_u=np.zeros(4))
    assert np.allclose(env.ps.B_matrix, B0)
    assert np.allclose(env.ps.L, L0)


# ────────────────────────────────────────────────────────────────
#  M8b: nonlinear 模式
# ────────────────────────────────────────────────────────────────

def test_nonlinear_mode_accepted():
    """ScalableVSGEnv 接受 network_mode='nonlinear'."""
    env = ScalableVSGEnv(n_agents=4, random_disturbance=False,
                         network_mode='nonlinear')
    assert env.network_mode == 'nonlinear'
    assert env.ps.network_mode == 'nonlinear'


def test_invalid_network_mode_rejected():
    """非法 network_mode 触发 ValueError."""
    with pytest.raises(ValueError):
        ScalableVSGEnv(n_agents=4, network_mode='foobar')


def test_nonlinear_vs_linear_small_disturbance():
    """小扰动下 nonlinear 与 linear 数值接近 (sin(θ)≈θ)."""
    delta_u = np.array([0.1, 0.0, -0.1, 0.0])  # 小扰动

    env_lin = ScalableVSGEnv(n_agents=4, random_disturbance=False,
                             network_mode='linear')
    env_nl = ScalableVSGEnv(n_agents=4, random_disturbance=False,
                            network_mode='nonlinear')

    env_lin.reset(delta_u=delta_u)
    env_nl.reset(delta_u=delta_u)

    for _ in range(10):
        zero_act = {i: np.zeros(2) for i in range(4)}
        _, _, _, r_lin = env_lin.step(zero_act)
        _, _, _, r_nl = env_nl.step(zero_act)

    # 小扰动下 omega 差距应很小 (sin 非线性贡献 ~θ³/6)
    diff = np.abs(r_lin['omega'] - r_nl['omega']).max()
    assert diff < 0.1, f"nonlinear vs linear omega diff = {diff}"


def test_nonlinear_large_disturbance_diverges_from_linear():
    """大扰动下 nonlinear 与 linear 出现可观测差异 (证明 sin 项确实生效)."""
    delta_u = np.array([3.0, 0.0, -3.0, 0.0])  # 大扰动

    env_lin = ScalableVSGEnv(n_agents=4, random_disturbance=False,
                             network_mode='linear')
    env_nl = ScalableVSGEnv(n_agents=4, random_disturbance=False,
                            network_mode='nonlinear')

    env_lin.reset(delta_u=delta_u)
    env_nl.reset(delta_u=delta_u)

    for _ in range(20):
        zero_act = {i: np.zeros(2) for i in range(4)}
        _, _, _, r_lin = env_lin.step(zero_act)
        _, _, _, r_nl = env_nl.step(zero_act)

    # 大扰动下 nonlinear 与 linear 应可观测差异 (sin 项贡献显著)
    diff = np.abs(r_lin['omega'] - r_nl['omega']).max()
    assert diff > 1e-3, f"nonlinear 与 linear 在大扰动下无差异 ({diff}); sin 项未生效?"
