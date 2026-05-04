"""Smoke test: own-last-action obs augmentation (F2 hypothesis, 2026-05-03).

Tests:
  1. Default (INCLUDE_OWN_ACTION_OBS=False): reset() obs shape == (7,), OBS_DIM_RUNTIME == 7.
  2. Flag True: reset() obs shape == (9,), last 2 dims == 0 (zero-initialized buffer).
     After step() with random actions, next obs last 2 dims == clipped actions.
  3. Reset flag back to False: default restored, obs shape == (7,).

Runs without ANDES or any simulation engine (uses stubbed env + manual state injection).
"""
from __future__ import annotations

import sys
import math
import numpy as np
import importlib.util
import pathlib

# ---------------------------------------------------------------------------
# Load base_env without triggering env/andes/__init__.py (requires andes pkg)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_BASE_ENV_PATH = _PROJECT_ROOT / "env" / "andes" / "base_env.py"
_spec = importlib.util.spec_from_file_location("andes_base_env_smoke_oa", _BASE_ENV_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["andes_base_env_smoke_oa"] = _mod
_spec.loader.exec_module(_mod)
AndesBaseEnv = _mod.AndesBaseEnv

N = 4

# ---------------------------------------------------------------------------
# Minimal concrete subclass (no ANDES runtime needed)
# ---------------------------------------------------------------------------

class _MinimalEnv(AndesBaseEnv):
    N_AGENTS = N
    COMM_ADJ = {0: [1], 1: [0, 2], 2: [1, 3], 3: [2]}  # chain topology

    def _build_system(self):  # pragma: no cover
        raise NotImplementedError

    def _apply_disturbance(self, **kwargs):  # pragma: no cover
        raise NotImplementedError


def _make_env() -> _MinimalEnv:
    """Construct env with just enough state for _build_obs() to work.

    Bypasses __init__ (which calls self._omega_scale = FN*2*pi after __new__)
    by calling __new__ and then manually running __init__ via super().__init__
    — but __init__ needs N_AGENTS to be set first (it's a class attr here so OK).
    We call the real __init__ to properly initialise _last_action_per_agent.
    """
    env = _MinimalEnv.__new__(_MinimalEnv)
    # Manually set the minimum attributes __init__ reads from class or kwargs
    # before calling __init__ so no KeyError/AttributeError.
    AndesBaseEnv.__init__(env)

    # Inject synthetic ANDES-like state so _build_obs() can run.
    # _build_obs calls _get_vsg_omega / _get_vsg_power / _compute_omega_dot
    # when arguments are not passed explicitly.  We monkey-patch them.
    omega = np.ones(N, dtype=np.float64)
    P = np.ones(N, dtype=np.float64) * 0.5
    od = np.zeros(N, dtype=np.float64)

    env._get_vsg_omega = lambda: omega.copy()
    env._get_vsg_power = lambda: P.copy()
    env._compute_omega_dot = lambda om, p: od.copy()

    # All comm links active (no drop)
    env.comm_eta = {(i, j): 1
                    for i, nbrs in _MinimalEnv.COMM_ADJ.items()
                    for j in nbrs}
    env.comm_delay_steps = 0
    env._delayed_omega = {}
    env._delayed_omega_dot = {}

    return env


def main() -> int:
    fails = 0

    # ── TEST 1: default flag=False → 7-dim obs, OBS_DIM_RUNTIME == 7 ──
    _MinimalEnv.INCLUDE_OWN_ACTION_OBS = False
    env1 = _make_env()
    assert not env1.INCLUDE_OWN_ACTION_OBS, "flag should be False"
    obs1 = env1._build_obs()

    runtime_dim = env1.OBS_DIM_RUNTIME
    if runtime_dim != 7:
        print(f"[TEST 1 FAIL] OBS_DIM_RUNTIME={runtime_dim}, expected 7")
        fails += 1
    else:
        print(f"[TEST 1a PASS] OBS_DIM_RUNTIME == 7")

    for i in range(N):
        if obs1[i].shape != (7,):
            print(f"[TEST 1 FAIL] agent {i} obs shape={obs1[i].shape}, expected (7,)")
            fails += 1
            break
    else:
        print(f"[TEST 1b PASS] default flag=False: all agents obs shape (7,)")

    # ── TEST 2: flag=True → 9-dim obs ──
    _MinimalEnv.INCLUDE_OWN_ACTION_OBS = True
    env2 = _make_env()
    assert env2.INCLUDE_OWN_ACTION_OBS, "flag should be True"

    runtime_dim2 = env2.OBS_DIM_RUNTIME
    if runtime_dim2 != 9:
        print(f"[TEST 2 FAIL] OBS_DIM_RUNTIME={runtime_dim2}, expected 9")
        fails += 1
    else:
        print(f"[TEST 2a PASS] OBS_DIM_RUNTIME == 9 when flag True")

    obs_reset = env2._build_obs()
    for i in range(N):
        if obs_reset[i].shape != (9,):
            print(f"[TEST 2 FAIL] agent {i} reset obs shape={obs_reset[i].shape}, expected (9,)")
            fails += 1
            break
        if not np.all(obs_reset[i][7:] == 0.0):
            print(f"[TEST 2 FAIL] agent {i} last 2 dims at reset not zero: {obs_reset[i][7:]}")
            fails += 1
            break
    else:
        print(f"[TEST 2b PASS] flag=True: all agents obs shape (9,), last 2 dims == 0 after reset")

    # Simulate step: set _last_action_per_agent as if step() ran
    rng = np.random.default_rng(7)
    raw_actions = {i: rng.uniform(-1.5, 1.5, size=(2,)) for i in range(N)}
    clipped_actions = {i: np.clip(raw_actions[i], -1.0, 1.0).astype(np.float32) for i in range(N)}

    # Replicate what step() does: env._last_action_per_agent[i] = np.clip(actions[i], -1.0, 1.0)
    for i in range(N):
        env2._last_action_per_agent[i] = clipped_actions[i]

    obs_post_step = env2._build_obs()
    step_ok = True
    for i in range(N):
        if obs_post_step[i].shape != (9,):
            print(f"[TEST 2 FAIL] post-step agent {i} shape={obs_post_step[i].shape}")
            step_ok = False
            fails += 1
            break
        got = obs_post_step[i][7:]
        want = clipped_actions[i]
        if not np.allclose(got, want, atol=1e-6):
            print(f"[TEST 2 FAIL] agent {i} last 2 dims {got} != clipped action {want}")
            step_ok = False
            fails += 1
            break
    if step_ok:
        print(f"[TEST 2c PASS] post-step obs last 2 dims == clipped actions for all agents")

    # ── TEST 3: Reset flag back to False → 7-dim obs again ──
    _MinimalEnv.INCLUDE_OWN_ACTION_OBS = False
    env3 = _make_env()
    obs3 = env3._build_obs()
    for i in range(N):
        if obs3[i].shape != (7,):
            print(f"[TEST 3 FAIL] agent {i} obs shape={obs3[i].shape} after restoring flag=False")
            fails += 1
            break
    else:
        print(f"[TEST 3 PASS] flag restored to False: all agents obs shape (7,)")

    # ── Summary ──
    if fails == 0:
        print("\nPASS — own-last-action obs augmentation smoke test complete.")
    else:
        print(f"\nFAIL — {fails} assertion(s) failed.")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
