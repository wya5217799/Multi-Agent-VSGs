"""M7 时变时延三要素验收测试.

三要素 (计划 §M7):
  1. 高斯分布: delay ~ N(μ, σ)
  2. 多链路不同均值: 每 (i,j) 独立 μ_ij
  3. 真实进入观测链路: delay 决定 obs 从历史哪个 tick 取邻居 ω
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import config as cfg
from scenarios.scalability.train import ScalableVSGEnv


DELAY_CFG = {
    'mean_range': (0.1, 0.3),
    'std': 0.03,
    'rng_seed': 42,
}


# ────────────────────────────────────────────────────────────────
#  要素 1: 高斯采样 (不是 uniform)
# ────────────────────────────────────────────────────────────────

def test_delay_samples_are_gaussian():
    """大量采样后 delay 均值/方差接近高斯预期."""
    env = ScalableVSGEnv(n_agents=4, random_disturbance=False,
                         comm_fail_prob=0.0, comm_delay_gaussian=DELAY_CFG)
    env.reset(delta_u=np.zeros(4))

    # 运行足够多步收集样本
    for _ in range(cfg.STEPS_PER_EPISODE):
        env.step({i: np.zeros(2) for i in range(4)})

    # 汇总所有链路所有步的 delay
    all_delays = []
    for step_delays in env._delay_trace:
        for d in step_delays.values():
            all_delays.append(d)
    all_delays = np.array(all_delays)

    assert len(all_delays) > 50, "样本不足"
    # 样本均值应落在 mean_range 内
    mu_hat = all_delays.mean()
    assert 0.05 < mu_hat < 0.35, f"样本均值 {mu_hat} 越界"
    # σ 接近 config std (clip>=0 会稍微改动, 但 σ≈0.03 不能跑偏太多)
    sigma_hat = all_delays.std()
    assert 0.01 < sigma_hat < 0.08, f"样本 σ={sigma_hat} 与 config 不符"


# ────────────────────────────────────────────────────────────────
#  要素 2: 不同链路不同均值
# ────────────────────────────────────────────────────────────────

def test_per_link_means_differ():
    """不同 (i,j) 链路 μ_ij 不同 (seed 固定下确定)."""
    env = ScalableVSGEnv(n_agents=8, random_disturbance=False,
                         comm_fail_prob=0.0, comm_delay_gaussian=DELAY_CFG)
    env.reset(delta_u=np.zeros(8))

    # 取所有唯一链路 μ
    unique_mus = set()
    for (i, j), mu in env._link_means.items():
        if i < j:  # 去对称
            unique_mus.add(round(mu, 4))

    # N=8 环形有 8 条链路; μ 应该不全相同
    assert len(unique_mus) >= 3, f"只有 {len(unique_mus)} 个不同 μ_ij, 多链路均值未分化"


def test_link_means_symmetric():
    """(i,j) 与 (j,i) 共享 μ_ij."""
    env = ScalableVSGEnv(n_agents=4, random_disturbance=False,
                         comm_fail_prob=0.0, comm_delay_gaussian=DELAY_CFG)
    env.reset(delta_u=np.zeros(4))

    for (i, j), mu in env._link_means.items():
        assert env._link_means[(j, i)] == mu, (
            f"链路 ({i},{j}) μ={mu} 与反向 ({j},{i}) μ={env._link_means[(j,i)]} 不一致"
        )


# ────────────────────────────────────────────────────────────────
#  要素 3: delay 真进入观测链路
# ────────────────────────────────────────────────────────────────

def test_delay_affects_observation():
    """非零 delay 下 obs 邻居 ω 与实时 ω 不同 (真延迟生效)."""
    # 用大均值保证 delay > 0
    env = ScalableVSGEnv(n_agents=4, random_disturbance=False,
                         comm_fail_prob=0.0,
                         comm_delay_gaussian={'mean_range': (0.4, 0.6),
                                              'std': 0.01,
                                              'rng_seed': 1})
    # 非零扰动使 ω 发散
    env.reset(delta_u=np.array([2.0, 0.0, -2.0, 0.0]))

    # 跑几步使 ω 有变化
    for _ in range(5):
        _, _, _, info = env.step({i: np.zeros(2) for i in range(4)})

    obs, _, _, info = env.step({i: np.zeros(2) for i in range(4)})
    real_omega = info['omega']

    # agent 0 观测中的邻居 ω (idx 3 / idx 4 对应邻居 0, 1)
    # 归一化系数 /3.0 → 反推
    o0 = obs[0]
    obs_neighbor1 = o0[3] * 3.0
    obs_neighbor2 = o0[4] * 3.0

    # delay≈0.5 s 对应 ~2.5 steps, 实时邻居 ω 与 buffer 历史值不同
    neighbors = env.comm.get_neighbors(0)
    real_n1 = real_omega[neighbors[0]]
    real_n2 = real_omega[neighbors[1]]

    diff1 = abs(obs_neighbor1 - real_n1)
    diff2 = abs(obs_neighbor2 - real_n2)
    max_diff = max(diff1, diff2)
    assert max_diff > 1e-4, (
        f"delay≈0.5s 下 obs 邻居 ω={obs_neighbor1:.4f}/{obs_neighbor2:.4f} "
        f"与实时 ω={real_n1:.4f}/{real_n2:.4f} 无差异, delay 未生效"
    )


def test_zero_delay_matches_nondelayed_obs():
    """μ=0, σ→0 时 obs 应接近无延迟 baseline."""
    # 极小延迟配置
    zero_cfg = {'mean_range': (0.0, 0.0), 'std': 1e-9, 'rng_seed': 7}
    env_delayed = ScalableVSGEnv(n_agents=4, random_disturbance=False,
                                 comm_fail_prob=0.0,
                                 comm_delay_gaussian=zero_cfg)
    env_nodelay = ScalableVSGEnv(n_agents=4, random_disturbance=False,
                                 comm_fail_prob=0.0)

    du = np.array([1.0, 0.0, -1.0, 0.0])
    obs_d = env_delayed.reset(delta_u=du)
    obs_n = env_nodelay.reset(delta_u=du)

    for _ in range(5):
        obs_d, _, _, _ = env_delayed.step({i: np.zeros(2) for i in range(4)})
        obs_n, _, _, _ = env_nodelay.step({i: np.zeros(2) for i in range(4)})

    for i in range(4):
        diff = np.abs(obs_d[i] - obs_n[i]).max()
        assert diff < 1e-3, f"agent {i} 零延迟配置下 obs 与无延迟基线差 {diff}"


# ────────────────────────────────────────────────────────────────
#  互斥性
# ────────────────────────────────────────────────────────────────

def test_comm_delay_steps_and_gaussian_are_mutually_exclusive():
    with pytest.raises(ValueError):
        ScalableVSGEnv(n_agents=4, comm_delay_steps=1,
                       comm_delay_gaussian=DELAY_CFG)


# ────────────────────────────────────────────────────────────────
#  trace 可用于 Fig.20 共享序列
# ────────────────────────────────────────────────────────────────

def test_delay_trace_length_matches_steps():
    env = ScalableVSGEnv(n_agents=4, random_disturbance=False,
                         comm_fail_prob=0.0, comm_delay_gaussian=DELAY_CFG)
    env.reset(delta_u=np.zeros(4))
    n_steps = 10
    for _ in range(n_steps):
        env.step({i: np.zeros(2) for i in range(4)})
    # reset 时 _build_obs 也会推一次; 共 n_steps+1
    assert len(env._delay_trace) == n_steps + 1, (
        f"_delay_trace 长度 {len(env._delay_trace)} 不等于 steps+1={n_steps+1}"
    )
