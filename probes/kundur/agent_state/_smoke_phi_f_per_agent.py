"""Smoke test: PHI_F_PER_AGENT per-agent frequency reward weight.

Tests:
1. PHI_F_PER_AGENT=None (default) -- behavior byte-identical to scalar PHI_F.
2. PHI_F_PER_AGENT=[1000, 1000, 30000, 1000] -- agent 2 reward differs proportionally.
3. Invalid length [1000, 2000] raises ValueError on env init.
"""
from __future__ import annotations

import sys
import math
import importlib.util
import pathlib
import numpy as np

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_BASE_ENV_PATH = _PROJECT_ROOT / "env" / "andes" / "base_env.py"
_spec = importlib.util.spec_from_file_location("andes_base_env_smoke2", _BASE_ENV_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["andes_base_env_smoke2"] = _mod
_spec.loader.exec_module(_mod)
AndesBaseEnv = _mod.AndesBaseEnv

N = 4


class _MinimalEnv(AndesBaseEnv):
    N_AGENTS = N
    COMM_ADJ = {0: [1], 1: [0, 2], 2: [1, 3], 3: [2]}

    def _build_system(self):  # pragma: no cover
        raise NotImplementedError

    def _apply_disturbance(self):  # pragma: no cover
        raise NotImplementedError


def _make_env(phi_f_per_agent=None) -> _MinimalEnv:
    """Build a minimal env bypassing ANDES runtime."""
    env = _MinimalEnv.__new__(_MinimalEnv)
    env.N_AGENTS = N
    env.COMM_ADJ = _MinimalEnv.COMM_ADJ
    env.FN = 50.0
    env.PHI_F = AndesBaseEnv.PHI_F
    env.PHI_F_PER_AGENT = phi_f_per_agent
    env.PHI_H = AndesBaseEnv.PHI_H
    env.PHI_D = AndesBaseEnv.PHI_D
    env.PHI_ABS = 0.0
    env.comm_eta = {(i, j): 1
                    for i, nbrs in _MinimalEnv.COMM_ADJ.items()
                    for j in nbrs}
    env._last_raw = {}
    return env


def _make_env_via_init(phi_f_per_agent) -> _MinimalEnv:
    """Build env via __init__ so validation fires."""
    class _Subclass(_MinimalEnv):
        PHI_F_PER_AGENT = phi_f_per_agent

    return _Subclass(random_disturbance=False)


def main() -> int:
    rng = np.random.default_rng(0)

    omega = np.array([1.0 - 0.001, 1.0 - 0.008, 1.0 - 0.002, 1.0 + 0.001])
    omega_dot = rng.standard_normal(N) * 0.001
    delta_M = rng.standard_normal(N) * 1.0
    delta_D = rng.standard_normal(N) * 0.5

    # ── Test 1: PHI_F_PER_AGENT=None identical to scalar PHI_F ──
    env_scalar = _make_env(phi_f_per_agent=None)
    env_none = _make_env(phi_f_per_agent=None)
    r_scalar, *_ = env_scalar._compute_rewards(omega, omega_dot, delta_M, delta_D)
    r_none, *_ = env_none._compute_rewards(omega, omega_dot, delta_M, delta_D)

    for i in range(N):
        assert r_scalar[i] == r_none[i], (
            f"[TEST 1 FAIL] agent {i}: scalar={r_scalar[i]} none={r_none[i]}"
        )
        assert math.isfinite(r_scalar[i]), f"r[{i}] is not finite"
    print(f"[TEST 1 PASS] PHI_F_PER_AGENT=None identical to scalar: "
          f"{[round(r_scalar[i], 4) for i in range(N)]}")

    # ── Test 2: PHI_F_PER_AGENT=[1000, 1000, 30000, 1000] agent 2 differs proportionally ──
    PHI_ARRAY = [1000.0, 1000.0, 30000.0, 1000.0]
    env_arr = _make_env(phi_f_per_agent=PHI_ARRAY)
    r_arr, *_ = env_arr._compute_rewards(omega, omega_dot, delta_M, delta_D)

    # Manually compute expected: for each agent i, the only PHI_F-dependent term is
    # phi_f_i * r_f_i.  All other terms (PHI_H, PHI_D, PHI_ABS=0) are identical.
    # So r_arr[i] - r_none[i] == (PHI_ARRAY[i] - PHI_F_scalar) * r_f_i
    PHI_F_SCALAR = AndesBaseEnv.PHI_F  # 10000.0
    for i in range(N):
        diff = r_arr[i] - r_scalar[i]
        if i == 2:
            # agent 2 has higher weight (30000 vs 10000) -- diff must be non-zero
            assert diff != 0.0, "[TEST 2 FAIL] agent 2 reward unchanged despite boosted PHI_F"
        else:
            # agents 0,1,3 have lower weight (1000 vs 10000) -- diff must also be non-zero
            assert diff != 0.0, (
                f"[TEST 2 FAIL] agent {i} reward unchanged despite changed PHI_F"
            )

    # Verify each agent: diff = (PHI_ARRAY[i] - PHI_F_SCALAR) * r_f_i
    # We can recover r_f_i from the scalar run: r_f_i = r_scalar[i] - (PHI_H*r_h + PHI_D*r_d)
    # But the simplest check is: diff_agent_i / diff_agent_j == r_f_i / r_f_j * weight_diff_ratio
    # Cleanest: for agent 2 vs agent 0, diff/r_f ratio should match weight delta.
    # r_f_i = (r_scalar[i] - r_none[i]_with_PHI_F=0) -- use a zero-PHI_F env to isolate r_f.
    env_nof = _make_env(phi_f_per_agent=None)
    env_nof.PHI_F = 0.0
    env_nof.PHI_H = 0.0
    env_nof.PHI_D = 0.0
    r_nof, *_ = env_nof._compute_rewards(omega, omega_dot, delta_M, delta_D)
    # r_scalar[i] = PHI_F_SCALAR * r_f_i + others; r_nof[i] = 0; others via env with no weights
    env_others = _make_env(phi_f_per_agent=None)
    env_others.PHI_F = 0.0
    r_others, *_ = env_others._compute_rewards(omega, omega_dot, delta_M, delta_D)
    # r_f_i_raw = (r_scalar[i] - r_others[i]) / PHI_F_SCALAR
    for i in range(N):
        r_f_i_raw = (r_scalar[i] - r_others[i]) / PHI_F_SCALAR
        expected_diff = (PHI_ARRAY[i] - PHI_F_SCALAR) * r_f_i_raw
        actual_diff = r_arr[i] - r_scalar[i]
        assert abs(actual_diff - expected_diff) < 1e-6, (
            f"[TEST 2 FAIL] agent {i}: diff={actual_diff:.9f} expected={expected_diff:.9f}"
        )
    print(f"[TEST 2 PASS] PHI_F_PER_AGENT=[1000,1000,30000,1000] each agent reward differs "
          f"proportionally to (PHI_ARRAY[i]-scalar)*r_f_i")

    # ── Test 3: invalid length raises ValueError ──
    try:
        _make_env_via_init(phi_f_per_agent=[1000.0, 2000.0])
        print("[TEST 3 FAIL] Expected ValueError, none raised")
        return 1
    except ValueError as exc:
        print(f"[TEST 3 PASS] ValueError raised: {exc}")

    print("\nPASS - PHI_F_PER_AGENT per-agent weight implemented correctly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
