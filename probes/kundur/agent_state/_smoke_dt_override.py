"""Smoke test: DT_OVERRIDE feature-flag for control step override.

Tests:
1. DT_OVERRIDE=None (default) -- _dt_runtime==0.2, _steps_per_episode_runtime==50,
   mock ss.dae.t advances by 5 * 0.2 = 1.0s over 5 step() calls.
2. DT_OVERRIDE=0.1 -- _dt_runtime==0.1, _steps_per_episode_runtime==100,
   mock ss.dae.t advances by 5 * 0.1 = 0.5s over 5 step() calls.
3. DT_OVERRIDE=-1 raises ValueError on env init.
4. After test 2, reset DT_OVERRIDE back to None; default behavior restored.
"""
from __future__ import annotations

import sys
import types
import pathlib
import numpy as np

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Load base_env without executing ANDES-dependent imports
# ---------------------------------------------------------------------------
import importlib.util
_BASE_ENV_PATH = _PROJECT_ROOT / "env" / "andes" / "base_env.py"
_spec = importlib.util.spec_from_file_location("andes_base_env_dt_smoke", _BASE_ENV_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["andes_base_env_dt_smoke"] = _mod
_spec.loader.exec_module(_mod)
AndesBaseEnv = _mod.AndesBaseEnv

N = 4


class _MinimalEnv(AndesBaseEnv):
    N_AGENTS = N
    COMM_ADJ = {0: [1], 1: [0, 2], 2: [1, 3], 3: [2]}

    def _build_system(self):  # pragma: no cover
        raise NotImplementedError

    def _apply_disturbance(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError


def _make_env_via_init(dt_override=None) -> _MinimalEnv:
    """Instantiate via __init__ so DT_OVERRIDE validation and runtime init fire."""
    class _Sub(_MinimalEnv):
        DT_OVERRIDE = dt_override

    return _Sub(random_disturbance=False)


# ---------------------------------------------------------------------------
# Minimal mock for ss.dae and ss.TDS / ss.GENCLS so step() can run
# ---------------------------------------------------------------------------

def _make_mock_ss(t_start: float = 0.5):
    """Return a mock ss object whose dae.t advances when TDS.run() is called."""

    class _DAE:
        def __init__(self):
            self.t = t_start

    class _TDS:
        def __init__(self, dae):
            self._dae = dae
            self.busted = False

        def run(self):
            # Advance dae.t to tf
            self._dae.t = self.config.tf

        class config:
            tf = 0.0

        def __init__(self, dae):
            self._dae = dae
            self.busted = False
            self.config = type("cfg", (), {"tf": t_start})()

        def run(self):
            self._dae.t = self.config.tf

    class _GENCLS:
        def __init__(self, n):
            self.idx = types.SimpleNamespace(v=list(range(n)))
            self.omega = types.SimpleNamespace(v=[1.0] * n)
            self.Pe = types.SimpleNamespace(v=[0.5] * n)
            self.M = types.SimpleNamespace(v=[20.0] * n)
            self.D = types.SimpleNamespace(v=[4.0] * n)
            self.p0 = types.SimpleNamespace(v=[0.5] * n)

        def set(self, *args, **kw):
            pass  # no-op for smoke

    dae = _DAE()
    tds = _TDS(dae)
    gencls = _GENCLS(N)
    ss = types.SimpleNamespace(dae=dae, TDS=tds, GENCLS=gencls)
    return ss


def _inject_ss(env, t_start: float = 0.5):
    """Attach mock ss to env and initialise step-related state."""
    env.ss = _make_mock_ss(t_start)
    env.vsg_idx = list(range(N))
    env.step_count = 0
    env._prev_omega = np.ones(N)
    env._prev_M = env.M0.copy()
    env._prev_D = env.D0.copy()
    env.comm_eta = {(i, j): 1
                    for i, nbrs in _MinimalEnv.COMM_ADJ.items()
                    for j in nbrs}
    env._delayed_omega = {}
    env._delayed_omega_dot = {}
    env._last_raw = {}


def _zero_actions():
    return {i: np.zeros(2) for i in range(N)}


def _run_steps(env, n: int):
    """Run n step() calls ignoring obs/rewards/done."""
    for _ in range(n):
        env.step(_zero_actions())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def main() -> int:
    failures = 0

    # ── Test 1: DT_OVERRIDE=None (default) ──────────────────────────────────
    env1 = _make_env_via_init(dt_override=None)
    assert abs(env1._dt_runtime - 0.2) < 1e-9, (
        f"[TEST 1 FAIL] _dt_runtime={env1._dt_runtime}, expected 0.2")
    assert env1._steps_per_episode_runtime == 50, (
        f"[TEST 1 FAIL] _steps_per_episode_runtime={env1._steps_per_episode_runtime}, expected 50")

    _inject_ss(env1, t_start=0.5)
    t_before = env1.ss.dae.t
    _run_steps(env1, 5)
    t_after = env1.ss.dae.t
    t_advance = t_after - t_before
    expected_advance = 5 * 0.2

    if abs(t_advance - expected_advance) < 1e-6:
        print(f"[TEST 1 PASS] _dt_runtime=0.2, _steps_per_episode_runtime=50, "
              f"dae.t advanced {t_advance:.4f}s (expected {expected_advance:.4f}s)")
    else:
        print(f"[TEST 1 FAIL] dae.t advanced {t_advance:.6f}s, expected {expected_advance:.6f}s")
        failures += 1

    # ── Test 2: DT_OVERRIDE=0.1 ─────────────────────────────────────────────
    env2 = _make_env_via_init(dt_override=0.1)
    if abs(env2._dt_runtime - 0.1) > 1e-9:
        print(f"[TEST 2 FAIL] _dt_runtime={env2._dt_runtime}, expected 0.1")
        failures += 1
    elif env2._steps_per_episode_runtime != 100:
        print(f"[TEST 2 FAIL] _steps_per_episode_runtime={env2._steps_per_episode_runtime}, expected 100")
        failures += 1
    else:
        _inject_ss(env2, t_start=0.5)
        t_before2 = env2.ss.dae.t
        _run_steps(env2, 5)
        t_after2 = env2.ss.dae.t
        t_advance2 = t_after2 - t_before2
        expected_advance2 = 5 * 0.1

        if abs(t_advance2 - expected_advance2) < 1e-6:
            print(f"[TEST 2 PASS] _dt_runtime=0.1, _steps_per_episode_runtime=100, "
                  f"dae.t advanced {t_advance2:.4f}s (expected {expected_advance2:.4f}s)")
        else:
            print(f"[TEST 2 FAIL] dae.t advanced {t_advance2:.6f}s, expected {expected_advance2:.6f}s")
            failures += 1

    # ── Test 3: DT_OVERRIDE=-1 raises ValueError ─────────────────────────────
    try:
        _make_env_via_init(dt_override=-1.0)
        print("[TEST 3 FAIL] Expected ValueError, none raised")
        failures += 1
    except ValueError as exc:
        print(f"[TEST 3 PASS] ValueError raised as expected: {exc}")

    # ── Test 4: Reset DT_OVERRIDE to None; class attr STEPS_PER_EPISODE preserved ──
    _MinimalEnv.DT_OVERRIDE = None  # explicit reset (was already None, paranoia check)
    env4 = _make_env_via_init(dt_override=None)
    if (abs(env4._dt_runtime - 0.2) < 1e-9
            and env4._steps_per_episode_runtime == 50
            and _MinimalEnv.STEPS_PER_EPISODE == 50):
        print(f"[TEST 4 PASS] After DT_OVERRIDE reset to None: _dt_runtime=0.2, "
              f"_steps_per_episode_runtime=50, class STEPS_PER_EPISODE=50 (unchanged)")
    else:
        print(f"[TEST 4 FAIL] _dt_runtime={env4._dt_runtime}, "
              f"_steps_per_episode_runtime={env4._steps_per_episode_runtime}, "
              f"STEPS_PER_EPISODE={_MinimalEnv.STEPS_PER_EPISODE}")
        failures += 1

    if failures == 0:
        print("\nPASS - DT_OVERRIDE feature flag implemented correctly.")
        return 0
    else:
        print(f"\nFAIL - {failures} test(s) failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
