"""P0 + P1 前置核实条件验收测试.

P0-测试: scalability/NE39-ODE 路径的固定评估集生成器
  - 绑 cfg.N_TEST_SCENARIOS，不绕过 cfg 硬编码
  - 同 seed 下扰动完全一致 (跨 run 可复现)
  - metadata 导出完整 (seed / n_test / generator_version)

P1: 完整 seed 协议
  - seed_everything 覆盖 python/numpy/torch 全部随机源
  - 同 seed 两次调用后首次随机输出一致
  - 环境可复现 (env.seed + reset 返回确定 obs)
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import config as cfg
from scenarios.scalability.train import (
    ScalableVSGEnv,
    NE_TEST_SEED,
    TEST_SET_GENERATOR_VERSION,
    generate_ne_test_scenarios,
    build_test_set_metadata,
)
from utils.seed_utils import seed_everything


# ────────────────────────────────────────────────────────────────
#  P0-测试: 固定评估集
# ────────────────────────────────────────────────────────────────

def test_generate_ne_test_scenarios_default_binds_cfg():
    """默认 n 读 cfg.N_TEST_SCENARIOS, 不得绕过 cfg."""
    scenarios = generate_ne_test_scenarios(n_agents=8)
    assert len(scenarios) == cfg.N_TEST_SCENARIOS, (
        f"默认场景数 {len(scenarios)} 未绑 cfg.N_TEST_SCENARIOS={cfg.N_TEST_SCENARIOS}"
    )


def test_generate_ne_test_scenarios_reproducible():
    """同 seed 两次生成完全一致."""
    a = generate_ne_test_scenarios(n_agents=8, seed=NE_TEST_SEED)
    b = generate_ne_test_scenarios(n_agents=8, seed=NE_TEST_SEED)
    assert len(a) == len(b)
    for sa, sb in zip(a, b):
        assert np.array_equal(sa, sb), "同 seed 扰动应完全一致"


def test_generate_ne_test_scenarios_different_seeds_differ():
    """不同 seed 扰动应不同."""
    a = generate_ne_test_scenarios(n_agents=8, seed=NE_TEST_SEED)
    b = generate_ne_test_scenarios(n_agents=8, seed=NE_TEST_SEED + 1)
    # 至少有一个场景不同 (概率上几乎必然)
    any_diff = any(not np.array_equal(sa, sb) for sa, sb in zip(a, b))
    assert any_diff, "不同 seed 扰动不应完全相同"


def test_generate_ne_test_scenarios_shape():
    """扰动向量 shape 与 n_agents 一致."""
    for N in (2, 4, 8):
        scenarios = generate_ne_test_scenarios(n_agents=N, n=5)
        for s in scenarios:
            assert s.shape == (N,), f"N={N} 场景 shape {s.shape} 错误"


def test_generate_ne_test_scenarios_disturbance_in_range():
    """扰动幅值落在 cfg.DISTURBANCE_MIN/MAX 边界内."""
    scenarios = generate_ne_test_scenarios(n_agents=8, n=50, seed=NE_TEST_SEED)
    for s in scenarios:
        nonzero = np.abs(s[s != 0])
        assert np.all(nonzero >= cfg.DISTURBANCE_MIN - 1e-9)
        assert np.all(nonzero <= cfg.DISTURBANCE_MAX + 1e-9)


def test_build_test_set_metadata_complete():
    """metadata 含 seed / n_test / generator / version (P0 产物要求)."""
    meta = build_test_set_metadata(n_agents=8)
    for key in ("n_test", "seed", "n_agents", "generator", "generator_version",
                "config_source"):
        assert key in meta, f"metadata 缺字段 {key}"
    assert meta["n_test"] == cfg.N_TEST_SCENARIOS
    assert meta["seed"] == NE_TEST_SEED
    assert meta["generator_version"] == TEST_SET_GENERATOR_VERSION
    assert meta["config_source"] == "cfg.N_TEST_SCENARIOS"


def test_fixed_set_env_random_disturbance_off():
    """固定集下环境扰动来自 delta_u, random_disturbance 必须关闭."""
    scenarios = generate_ne_test_scenarios(n_agents=4, n=3, seed=NE_TEST_SEED)
    env = ScalableVSGEnv(n_agents=4, random_disturbance=False, comm_fail_prob=0.0)

    # 连续两次 reset 同一 delta_u, current_delta_u 一致
    env.reset(delta_u=scenarios[0])
    du1 = env.current_delta_u.copy()
    env.reset(delta_u=scenarios[0])
    du2 = env.current_delta_u.copy()
    assert np.array_equal(du1, du2)
    assert np.array_equal(du1, scenarios[0])


# ────────────────────────────────────────────────────────────────
#  P1: 完整 seed 协议
# ────────────────────────────────────────────────────────────────

def test_seed_everything_covers_numpy():
    """seed_everything 后 np.random 输出可复现."""
    seed_everything(123)
    a = np.random.uniform(0, 1, size=10)
    seed_everything(123)
    b = np.random.uniform(0, 1, size=10)
    assert np.allclose(a, b), "seed_everything 后 numpy 全局随机输出不一致"


def test_seed_everything_covers_python_random():
    """seed_everything 后 Python random 可复现."""
    import random
    seed_everything(456)
    a = [random.random() for _ in range(5)]
    seed_everything(456)
    b = [random.random() for _ in range(5)]
    assert a == b


def test_seed_everything_covers_torch():
    """seed_everything 后 torch 随机可复现."""
    torch = pytest.importorskip("torch")
    seed_everything(789)
    a = torch.randn(5)
    seed_everything(789)
    b = torch.randn(5)
    assert torch.allclose(a, b), "seed_everything 后 torch 随机不一致"


def test_seed_everything_returns_metadata():
    """seed_everything 返回 dict 包含所有已 seed 组件."""
    info = seed_everything(42)
    for key in ("python_random", "numpy", "python_hash"):
        assert key in info
    # torch 可选
    try:
        import torch  # noqa: F401
        assert "torch_cpu" in info
    except ImportError:
        pass


def test_seed_everything_rejects_invalid():
    """非法 seed 值应报错."""
    with pytest.raises(ValueError):
        seed_everything(-1)
    with pytest.raises(ValueError):
        seed_everything("abc")  # type: ignore[arg-type]


def test_env_seed_reproducible_after_seed_everything():
    """seed_everything + env.seed 后 reset/step 结果可复现 (端到端协议)."""
    seed_everything(42)
    env1 = ScalableVSGEnv(n_agents=4, random_disturbance=True, comm_fail_prob=0.0)
    env1.seed(100)
    obs1 = env1.reset()
    du1 = env1.current_delta_u.copy()

    seed_everything(42)
    env2 = ScalableVSGEnv(n_agents=4, random_disturbance=True, comm_fail_prob=0.0)
    env2.seed(100)
    obs2 = env2.reset()
    du2 = env2.current_delta_u.copy()

    assert np.array_equal(du1, du2), "env.seed 扰动不可复现"
    for i in range(4):
        assert np.allclose(obs1[i], obs2[i]), f"agent {i} 初始 obs 不一致"


def test_compute_test_reward_deterministic():
    """固定集 + 固定 manager 下 compute_test_reward 两次结果一致."""
    from scenarios.scalability.train import compute_no_control_reward
    a = compute_no_control_reward(n_agents=4, n_test=5, seed=NE_TEST_SEED)
    b = compute_no_control_reward(n_agents=4, n_test=5, seed=NE_TEST_SEED)
    assert np.allclose(a, b), "固定集无控制基线奖励跨 run 不一致"
