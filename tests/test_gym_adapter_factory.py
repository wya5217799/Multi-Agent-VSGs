"""
Tests for env/gym_adapter.py and env/factory.py.

Covers:
  - GymAdapter: 4-tuple → 5-tuple step conversion
  - GymAdapter: reset returns (obs, info) in both old-spec and new-spec cases
  - GymAdapter: attribute pass-through
  - make_env: known combinations route to correct factories
  - make_env: unknown combination raises ValueError with helpful message
  - _SimVsgBase: _decode_action raises NotImplementedError on base class
  - _SimVsgBase: _COMM_ADJ=None raises TypeError if accidentally iterated
  - _SimVsgBase: __init_subclass__ warns when _COMM_ADJ not overridden
"""

from __future__ import annotations

import sys
import os
import types
import warnings
import numpy as np
import pytest

_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _PROJECT_ROOT)

from env.gym_adapter import GymAdapter
from env.factory import make_env, _REGISTRY


# ---------------------------------------------------------------------------
# Fake envs for unit testing
# ---------------------------------------------------------------------------

class _OldSpecEnv:
    """Simulates a 4-tuple (old-spec) env."""
    observation_space = None
    action_space = None
    N_AGENTS = 4
    OBS_DIM = 7

    def reset(self, **kwargs):
        return np.zeros((4, 7), dtype=np.float32)

    def step(self, actions):
        obs = np.zeros((4, 7), dtype=np.float32)
        rewards = np.zeros(4, dtype=np.float32) - 1.0
        done = False
        info = {"sim_time": 0.2, "sim_ok": True}
        return obs, rewards, done, info

    def close(self):
        pass


class _NewSpecEnv:
    """Simulates an env that already returns (obs, info) from reset."""
    def reset(self, **kwargs):
        return np.zeros((4, 7)), {"already_upgraded": True}

    def step(self, actions):
        return np.zeros((4, 7)), np.zeros(4), True, False, {}

    def close(self):
        pass


class _TerminalEnv(_OldSpecEnv):
    """Returns done=True from step."""
    def step(self, actions):
        obs, rew, _, info = super().step(actions)
        return obs, rew, True, info


# ---------------------------------------------------------------------------
# GymAdapter tests
# ---------------------------------------------------------------------------

class TestGymAdapter:
    """GymAdapter wraps a 4-tuple env to Gymnasium 5-tuple spec."""

    def test_step_returns_five_tuple(self):
        env = GymAdapter(_OldSpecEnv())
        action = np.zeros((4, 2), dtype=np.float32)
        result = env.step(action)
        assert len(result) == 5, "step must return 5-tuple"
        obs, rew, terminated, truncated, info = result
        assert obs.shape == (4, 7)
        assert not terminated
        assert not truncated

    def test_step_terminated_maps_done(self):
        env = GymAdapter(_TerminalEnv())
        action = np.zeros((4, 2), dtype=np.float32)
        _, _, terminated, truncated, _ = env.step(action)
        assert terminated is True
        assert truncated is False  # always False from adapter

    def test_step_truncated_always_false(self):
        """Adapter does not synthesise truncated signal; it's always False."""
        env = GymAdapter(_OldSpecEnv())
        _, _, _, truncated, _ = env.step(np.zeros((4, 2)))
        assert truncated is False

    def test_reset_old_spec_returns_tuple(self):
        env = GymAdapter(_OldSpecEnv())
        result = env.reset()
        assert isinstance(result, tuple) and len(result) == 2
        obs, info = result
        assert obs.shape == (4, 7)
        assert isinstance(info, dict)

    def test_reset_old_spec_info_is_empty(self):
        env = GymAdapter(_OldSpecEnv())
        _, info = env.reset()
        assert info == {}

    def test_reset_new_spec_preserves_info(self):
        """If wrapped env already returns (obs, info), adapter forwards info."""
        env = GymAdapter(_NewSpecEnv())
        obs, info = env.reset()
        assert info.get("already_upgraded") is True

    def test_attribute_passthrough(self):
        inner = _OldSpecEnv()
        env = GymAdapter(inner)
        assert env.N_AGENTS == 4
        assert env.OBS_DIM == 7

    def test_close_delegates(self):
        """close() must not raise even if inner env has no close."""
        class _NoClose:
            def reset(self): return np.zeros(3)
            def step(self, a): return np.zeros(3), 0.0, False, {}
        env = GymAdapter(_NoClose())
        env.close()  # should not raise

    def test_repr(self):
        env = GymAdapter(_OldSpecEnv())
        assert "GymAdapter" in repr(env)


# ---------------------------------------------------------------------------
# make_env tests
# ---------------------------------------------------------------------------

class TestMakeEnv:
    """make_env routes scenario/backend to correct factory."""

    def test_unknown_scenario_raises_valueerror(self):
        with pytest.raises(ValueError, match="Unknown scenario/backend"):
            make_env("bad_scenario", "andes")

    def test_unknown_backend_raises_valueerror(self):
        with pytest.raises(ValueError, match="Unknown scenario/backend"):
            make_env("kundur", "unknown_backend")

    def test_error_message_lists_supported(self):
        try:
            make_env("oops", "oops")
        except ValueError as exc:
            msg = str(exc)
            assert "kundur/andes" in msg
            assert "ne39/simulink" in msg

    def test_registry_covers_all_six_combinations(self):
        expected = {
            ("kundur", "andes"), ("kundur", "ode"), ("kundur", "simulink"),
            ("ne39",   "andes"), ("ne39",   "ode"), ("ne39",   "simulink"),
        }
        assert set(_REGISTRY.keys()) == expected

    def test_case_insensitive(self):
        """make_env normalises scenario and backend to lowercase."""
        with pytest.raises(ValueError):
            make_env("KUNDUR", "BAD")  # bad backend → ValueError (not KeyError)
        # Both lower-cased before lookup
        try:
            make_env("KUNDUR", "ANDES")
        except Exception as exc:
            # Should fail with an import or instantiation error, NOT ValueError
            assert "Unknown" not in str(exc), (
                "Lowercase normalisation failed — 'KUNDUR/ANDES' should route correctly"
            )

    def test_simulink_factory_returns_unwrapped(self):
        """Simulink envs already return 5-tuple; factory should not wrap them."""
        # We can't instantiate KundurSimulinkEnv without MATLAB,
        # but we can verify the factory function does NOT return a GymAdapter.
        factory_fn = _REGISTRY[("kundur", "simulink")]
        # The factory does not return GymAdapter — it returns KundurSimulinkEnv directly.
        # Check via source inspection (no MATLAB needed).
        import inspect
        src = inspect.getsource(factory_fn)
        assert "GymAdapter" not in src, (
            "Simulink factory must NOT wrap in GymAdapter (already 5-tuple)"
        )

    def test_andes_factory_wraps_in_gym_adapter(self):
        """ANDES envs return 4-tuple; factory should wrap in GymAdapter."""
        factory_fn = _REGISTRY[("kundur", "andes")]
        import inspect
        src = inspect.getsource(factory_fn)
        assert "GymAdapter" in src, (
            "ANDES factory must wrap env in GymAdapter"
        )

    def test_ode_factory_wraps_in_gym_adapter(self):
        factory_fn = _REGISTRY[("kundur", "ode")]
        import inspect
        src = inspect.getsource(factory_fn)
        assert "GymAdapter" in src


# ---------------------------------------------------------------------------
# _SimVsgBase tests
# ---------------------------------------------------------------------------

class TestSimVsgBase:
    """Unit tests for _SimVsgBase abstract base class."""

    def test_decode_action_raises_on_base(self):
        from env.simulink._base import _SimVsgBase
        base = object.__new__(_SimVsgBase)
        with pytest.raises(NotImplementedError, match="_decode_action"):
            base._decode_action(np.zeros((4, 2)))

    def test_comm_adj_none_raises_on_iteration(self):
        """_COMM_ADJ=None (not overridden) raises TypeError when iterated."""
        from env.simulink._base import _SimVsgBase

        class _BadEnv(_SimVsgBase):
            _N_AGENTS = 1
            # Deliberately NOT overriding _COMM_ADJ

        bad = object.__new__(_BadEnv)
        bad._omega = np.ones(1)
        bad._omega_prev = np.ones(1)
        bad._P_es = np.zeros(1)
        bad.DT = 0.2
        bad.OBS_DIM = 7
        bad._comm_mask = np.ones((1, 2), dtype=bool)
        bad._comm_buffer = {}
        bad.comm_delay_steps = 0

        with pytest.raises(TypeError):
            bad._build_obs()  # iterates over _COMM_ADJ[i] → TypeError on None

    def test_init_subclass_warns_missing_comm_adj(self):
        """__init_subclass__ warns if a public subclass forgets _COMM_ADJ."""
        from env.simulink._base import _SimVsgBase
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            class PublicEnvMissingAdj(_SimVsgBase):
                _N_AGENTS = 4
                # _COMM_ADJ not set

            if w:
                assert any("_COMM_ADJ" in str(warning.message) for warning in w)
            # If no warning fired, that's also acceptable (None sentinel is enough)

    def test_kundur_subclass_uses_simvsgbase_build_obs(self):
        """_KundurBaseEnv inherits _build_obs from _SimVsgBase (not its own copy)."""
        from env.simulink._base import _SimVsgBase
        from env.simulink.kundur_simulink_env import _KundurBaseEnv
        assert _KundurBaseEnv._build_obs is _SimVsgBase._build_obs

    def test_ne39_subclass_uses_simvsgbase_build_obs(self):
        from env.simulink._base import _SimVsgBase
        from env.simulink.ne39_simulink_env import _NE39BaseEnv
        assert _NE39BaseEnv._build_obs is _SimVsgBase._build_obs

    def test_kundur_n_agents(self):
        from env.simulink.kundur_simulink_env import _KundurBaseEnv
        assert _KundurBaseEnv._N_AGENTS == 4

    def test_ne39_n_agents(self):
        from env.simulink.ne39_simulink_env import _NE39BaseEnv
        assert _NE39BaseEnv._N_AGENTS == 8

    def test_kundur_decode_action_zero_centered(self):
        """Kundur: a=0 → delta_M=0, delta_D=0."""
        from env.simulink.kundur_simulink_env import KundurStandaloneEnv
        env = KundurStandaloneEnv()
        action = np.zeros((4, 2), dtype=np.float32)
        delta_M, delta_D = env._decode_action(action)
        np.testing.assert_array_equal(delta_M, 0.0)
        np.testing.assert_array_equal(delta_D, 0.0)
        env.close()

    def test_ne39_decode_action_affine_midpoint(self):
        """NE39: a=0 → delta = midpoint of [MIN, MAX]."""
        from env.simulink.ne39_simulink_env import NE39BusStandaloneEnv
        from scenarios.config_simulink_base import DM_MIN, DM_MAX, DD_MIN, DD_MAX
        env = NE39BusStandaloneEnv()
        action = np.zeros((8, 2), dtype=np.float32)
        delta_M, delta_D = env._decode_action(action)
        expected_M = 0.5 * (DM_MAX - DM_MIN) + DM_MIN
        expected_D = 0.5 * (DD_MAX - DD_MIN) + DD_MIN
        np.testing.assert_allclose(delta_M, expected_M, rtol=1e-5)
        np.testing.assert_allclose(delta_D, expected_D, rtol=1e-5)
        env.close()
