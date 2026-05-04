"""Smoke test: PHI_ABS is per-agent local frequency penalty.

Verifies:
1. _compute_rewards returns N_AGENTS=4 finite rewards at PHI_ABS=0.0 (default).
2. Setting PHI_ABS=10.0 changes every agent's reward when d_omega != 0.
3. PHI_ABS=0.0 and PHI_ABS=10.0 differ in proportion to d_omega[i]^2.

Decision from code inspection (2026-05-03):
  r_abs = -(d_omega[i])**2  (line ~476 of env/andes/base_env.py)
  is per-agent local — uses agent i's OWN d_omega, not a global mean.
  Therefore PHI_ABS IS the LOCAL_RF_WEIGHT term. No new flag is needed.
  Suggested next experiment: re-enable PHI_ABS=10 to restore per-agent
  credit-assignment signal removed in Phase 4.
"""
from __future__ import annotations

import sys
import math
import types
import numpy as np

# ---------------------------------------------------------------------------
# Minimal stub: creates a fake env object with enough attributes to call
# _compute_rewards without starting ANDES or touching any network/model files.
# ---------------------------------------------------------------------------

# Import base_env directly via importlib to bypass env/andes/__init__.py
# which eagerly imports AndesMultiVSGEnv (requires `andes` package).
# This smoke test only needs AndesBaseEnv._compute_rewards which has no
# andes runtime dependency.
import importlib.util
import pathlib

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
# Ensure project root is on sys.path so base_env.py can resolve its own
# module-level imports (scenarios.contract, etc.) without triggering the
# env/andes/__init__.py chain that requires `andes`.
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_BASE_ENV_PATH = _PROJECT_ROOT / "env" / "andes" / "base_env.py"
_spec = importlib.util.spec_from_file_location("andes_base_env_smoke", _BASE_ENV_PATH)
_mod = importlib.util.module_from_spec(_spec)
# Register in sys.modules under the name "env.andes.base_env" so that any
# internal relative references resolve, but as a detached module so that
# env/andes/__init__.py is NOT executed.
sys.modules["andes_base_env_smoke"] = _mod
_spec.loader.exec_module(_mod)
AndesBaseEnv = _mod.AndesBaseEnv

N = 4

# Build a minimal concrete subclass — no abstract methods required for
# _compute_rewards, but ABC mandates _build_system and _apply_disturbance.
class _MinimalEnv(AndesBaseEnv):
    N_AGENTS = N
    COMM_ADJ = {0: [1], 1: [0, 2], 2: [1, 3], 3: [2]}  # chain topology

    def _build_system(self):  # pragma: no cover
        raise NotImplementedError

    def _apply_disturbance(self):  # pragma: no cover
        raise NotImplementedError


def _make_env(phi_abs: float = 0.0) -> _MinimalEnv:
    env = _MinimalEnv.__new__(_MinimalEnv)
    # Replicate __init__ state minimally (no ANDES ss needed)
    env.N_AGENTS = N
    env.COMM_ADJ = _MinimalEnv.COMM_ADJ
    env.FN = 50.0
    env.PHI_F = AndesBaseEnv.PHI_F
    env.PHI_H = AndesBaseEnv.PHI_H
    env.PHI_D = AndesBaseEnv.PHI_D
    env.PHI_ABS = phi_abs
    # All links active
    env.comm_eta = {(i, j): 1
                    for i, nbrs in _MinimalEnv.COMM_ADJ.items()
                    for j in nbrs}
    env._last_raw = {}
    return env


def _run(env: _MinimalEnv, omega: np.ndarray,
         omega_dot: np.ndarray,
         delta_M: np.ndarray,
         delta_D: np.ndarray) -> dict:
    rewards, *_ = env._compute_rewards(omega, omega_dot, delta_M, delta_D)
    return rewards


def main() -> int:
    rng = np.random.default_rng(0)

    # Non-trivial state: agents 0/2 have small deviations, agent 1 large.
    omega = np.array([1.0 - 0.001, 1.0 - 0.008, 1.0 - 0.002, 1.0 + 0.001])
    omega_dot = rng.standard_normal(N) * 0.001
    delta_M = rng.standard_normal(N) * 1.0
    delta_D = rng.standard_normal(N) * 0.5

    # ── Test 1: N_AGENTS rewards, all finite ──
    env0 = _make_env(phi_abs=0.0)
    r0 = _run(env0, omega, omega_dot, delta_M, delta_D)
    assert len(r0) == N, f"Expected {N} rewards, got {len(r0)}"
    for i, v in r0.items():
        assert math.isfinite(v), f"r[{i}] = {v} is not finite"
    print(f"[TEST 1 PASS] PHI_ABS=0: {N} finite rewards: "
          f"{[round(r0[i], 4) for i in range(N)]}")

    # ── Test 2: PHI_ABS=10 changes every reward ──
    env10 = _make_env(phi_abs=10.0)
    r10 = _run(env10, omega, omega_dot, delta_M, delta_D)
    diffs = [r10[i] - r0[i] for i in range(N)]
    for i, d in enumerate(diffs):
        assert d != 0.0, f"r[{i}] unchanged between PHI_ABS=0 and PHI_ABS=10"
    print(f"[TEST 2 PASS] PHI_ABS=10 shifts rewards: "
          f"{[round(d, 6) for d in diffs]}")

    # ── Test 3: delta proportional to -d_omega[i]^2 * 10 ──
    d_omega = (omega - 1.0) * 50.0
    expected_deltas = [-(d_omega[i] ** 2) * 10.0 for i in range(N)]
    for i in range(N):
        assert abs(diffs[i] - expected_deltas[i]) < 1e-9, (
            f"r[{i}] delta {diffs[i]:.9f} != expected {expected_deltas[i]:.9f}"
        )
    print(f"[TEST 3 PASS] Deltas match -d_omega[i]^2 * 10: "
          f"{[round(e, 6) for e in expected_deltas]}")

    # ── Test 4: r_f_local_raw key NOT yet in _last_raw (no new key added) ──
    assert "r_f_local_raw_per_agent" not in env0._last_raw, (
        "Unexpected new key r_f_local_raw_per_agent found — PHI_ABS reuse "
        "means no new raw key is needed"
    )
    assert "r_abs_raw_per_agent" in env0._last_raw, (
        "r_abs_raw_per_agent missing from _last_raw"
    )
    print("[TEST 4 PASS] r_abs_raw_per_agent present, no spurious new key")

    print("\nPASS - PHI_ABS is already per-agent local frequency penalty.")
    print("Conclusion: No new LOCAL_RF_WEIGHT flag needed.")
    print("Recommended next experiment: set PHI_ABS=10 and retrain.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
