"""ANDES V2 env training script — D0 hetero [20,16,4,8] + NEW_LINE_X=0.20.

Wraps train_andes.py: imports V2 env class, monkey-patches the V1 export so
all train_andes.py downstream logic uses V2 baseline.

Usage (WSL):
    source ~/andes_venv/bin/activate
    cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"
    python3 scenarios/kundur/train_andes_v2.py --episodes 500 \\
        --save-dir results/andes_v2_phase1_seed42 --seed 42

V1 完整保留. V2 SAC actor 不可与 V1 互换 (baseline H/D + action range mapping 不一致).

⚠ 6-axis 真实评估: V2-trained actor 在 V2 env 下 zero-shot 比 V1 actor (phase3v2_seed44)
   在 V2 env 下 zero-shot **更差**. 推测 V2 训练数值不稳 (TDS fails ~7%).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# 切到 V2 env, 在 train_andes 导入 AndesMultiVSGEnv 之前完成 patch.
from env.andes.andes_vsg_env_v2 import AndesMultiVSGEnvV2

import env.andes_vsg_env as _v1_module  # legacy path used by train_andes
_v1_module.AndesMultiVSGEnv = AndesMultiVSGEnvV2  # type: ignore[attr-defined]
print(f"[train_andes_v2] V2 env active: {AndesMultiVSGEnvV2.deviation_summary()}")


def main() -> None:
    from scenarios.kundur import train_andes  # type: ignore
    train_andes.main()


if __name__ == "__main__":
    main()
