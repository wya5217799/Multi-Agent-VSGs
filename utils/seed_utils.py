"""统一 seed 协议 util (P1 前置核实条件).

修改计划 §P1 要求：训练开始前须统一所有随机源。以下五条随机源均须在
manager/网络构造之前完成 seed，并将 seed 值写入 run metadata：

  1. Python ``random``
  2. ``numpy`` 全局 RNG
  3. ``torch`` CPU 种子 + CUDA 种子（若可用）
  4. 环境级 RNG（`env.seed(s)`，在调用方处理）
  5. Replay buffer 采样（buffer 内部依赖全局 numpy，本函数覆盖）

不受本 util 覆盖的随机源（调用方负责）：
  - `ScalableVSGEnv.seed(s)`  —— 每 episode 调用时手动 seed
  - 固定评估集：通过 `generate_*_test_scenarios(seed=...)` 显式固定，
    不依赖全局 RNG

用法::

    from utils.seed_utils import seed_everything
    seed_everything(args.seed)  # manager/网络构造前调用
    manager = MultiAgentManager(...)
"""
from __future__ import annotations

import os
import random
from typing import Dict

import numpy as np


def seed_everything(seed: int, deterministic_torch: bool = False) -> Dict[str, int]:
    """统一 seed 所有随机源 (P1 完整协议).

    Args:
        seed: 基准 seed。必须为非负 int。
        deterministic_torch: 若 True 额外设置 cudnn.deterministic=True（会降速）。

    Returns:
        dict: 已 seed 组件及其值，便于写入 run metadata。
    """
    if not isinstance(seed, int) or seed < 0:
        raise ValueError(f"seed 必须为非负 int, got {seed!r}")

    seeded: Dict[str, int] = {}

    # 1. Python random
    random.seed(seed)
    seeded["python_random"] = seed

    # 2. numpy 全局
    np.random.seed(seed)
    seeded["numpy"] = seed

    # 3. torch (CPU + CUDA)
    try:
        import torch  # 延迟 import: utils 不应强依赖 torch
        torch.manual_seed(seed)
        seeded["torch_cpu"] = seed
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
            seeded["torch_cuda"] = seed
        if deterministic_torch:
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
            seeded["torch_deterministic"] = 1
    except ImportError:
        pass

    # 4. Python hash seed（影响 set/dict 顺序，某些采样路径会受影响）
    os.environ.setdefault("PYTHONHASHSEED", str(seed))
    seeded["python_hash"] = seed

    return seeded
