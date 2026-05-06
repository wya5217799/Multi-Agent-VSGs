"""ANDES V3 env training script (V2 + governor + AVR).

Wraps train_andes.py, monkey-patches V3 env in.

⚠ V3 ckpts NOT cross-compatible with V1/V2 (env physics differ).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from env.andes.andes_vsg_env_v3 import AndesMultiVSGEnvV3

import env.andes_vsg_env as _v1_module
_v1_module.AndesMultiVSGEnv = AndesMultiVSGEnvV3
print(f"[train_andes_v3] V3 env active: {AndesMultiVSGEnvV3.deviation_summary()}")


def main() -> None:
    from scenarios.kundur import train_andes
    train_andes.main()


if __name__ == "__main__":
    main()
