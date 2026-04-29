"""C4 Scenario VO env API tests.

Covers R-1 (trigger time), R-2 (mixed-API double-fire), R-4 (external
``_disturbance_type`` write compat) from the P3 design risk table.

Uses ``KundurStandaloneEnv`` so no MATLAB engine is required — the
C4 trigger logic lives in ``_KundurBaseEnv.step()`` and is shared
with the Simulink backend. ``_apply_disturbance_backend`` is replaced
with an in-test recorder so we observe trigger semantics without
running physics.
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pytest

from env.simulink.kundur_simulink_env import KundurStandaloneEnv
from scenarios.kundur.scenario_loader import Scenario


# ---------------------------------------------------------------------------
# Fixture: standalone env with recording disturbance backend
# ---------------------------------------------------------------------------


@pytest.fixture
def env() -> Any:
    """Standalone env with ``_apply_disturbance_backend`` patched to record."""
    e = KundurStandaloneEnv(comm_delay_steps=0, training=False)
    e._recorded_calls: list[tuple[int | None, float]] = []  # type: ignore[attr-defined]

    def _recorder(bus_idx: int | None, magnitude: float) -> None:
        e._recorded_calls.append((bus_idx, float(magnitude)))  # type: ignore[attr-defined]
        # Do NOT mutate physics — we only care about WHEN the trigger fires.

    e._apply_disturbance_backend = _recorder  # type: ignore[method-assign]
    yield e


def _zero_action(env: Any) -> np.ndarray:
    return np.zeros((env.N_AGENTS, env.ACT_DIM), dtype=np.float32)


def _make_scenario(magnitude: float = 1.5) -> Scenario:
    return Scenario(
        scenario_idx=0,
        disturbance_kind="gen",
        target=2,
        magnitude_sys_pu=magnitude,
    )


# ---------------------------------------------------------------------------
# R-1: trigger time
# ---------------------------------------------------------------------------


class TestR1_TriggerTime:
    def test_default_trigger_fires_at_step_2(self, env: Any) -> None:
        """Default trigger_at_step = int(0.5/DT) = 2 for DT=0.2s."""
        env.reset(scenario=_make_scenario(1.5))
        # Steps 0, 1: no trigger expected
        env.step(_zero_action(env))
        assert env._recorded_calls == [], (
            f"trigger fired before step 2: {env._recorded_calls!r}"
        )
        env.step(_zero_action(env))
        assert env._recorded_calls == [], (
            f"trigger fired before step 2: {env._recorded_calls!r}"
        )
        # Step 2: trigger fires (BEFORE _step_backend, so it's recorded
        # at the START of the step==2 env.step call)
        env.step(_zero_action(env))
        assert env._recorded_calls == [(None, 1.5)], (
            f"step 2 trigger missing: {env._recorded_calls!r}"
        )

    def test_trigger_at_step_0_fires_immediately(self, env: Any) -> None:
        """paper_eval pattern: trigger_at_step=0 fires before step 0's bridge.step."""
        env.reset(
            scenario=_make_scenario(2.0),
            options={"trigger_at_step": 0},
        )
        env.step(_zero_action(env))
        assert env._recorded_calls == [(None, 2.0)], (
            f"trigger should fire at step 0 with trigger_at_step=0: "
            f"{env._recorded_calls!r}"
        )

    def test_trigger_fires_only_once_across_full_episode(
        self, env: Any
    ) -> None:
        """Trigger flag prevents re-fire across all subsequent steps."""
        env.reset(scenario=_make_scenario(1.0))
        for _ in range(10):
            env.step(_zero_action(env))
        assert len(env._recorded_calls) == 1, (
            f"expected exactly one trigger, got "
            f"{len(env._recorded_calls)}: {env._recorded_calls!r}"
        )

    def test_no_scenario_no_options_disarms_trigger(self, env: Any) -> None:
        """Legacy probe path: reset() with neither scenario nor magnitude
        leaves trigger DISARMED so the internal trigger never fires."""
        env.reset()
        for _ in range(10):
            env.step(_zero_action(env))
        assert env._recorded_calls == [], (
            f"trigger fired when not armed: {env._recorded_calls!r}"
        )

    def test_options_disturbance_magnitude_path(self, env: Any) -> None:
        """`options={'disturbance_magnitude': mag}` arms the trigger
        without a Scenario; resolved type is the constructor default."""
        # Standalone has no _disturbance_type, so resolved_type stays None.
        env.reset(options={"disturbance_magnitude": 0.7})
        for _ in range(3):
            env.step(_zero_action(env))
        assert env._recorded_calls == [(None, 0.7)]


# ---------------------------------------------------------------------------
# R-2: mixed-API double-fire prevention
# ---------------------------------------------------------------------------


class TestR2_NoDoubleFire:
    def test_apply_disturbance_then_internal_trigger_no_double(
        self, env: Any
    ) -> None:
        """If caller mixes legacy apply_disturbance() with reset(scenario=...),
        the internal trigger MUST NOT also fire."""
        env.reset(scenario=_make_scenario(1.5))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            env.apply_disturbance(magnitude=2.0)
        # Now step past trigger_at_step=2 — internal trigger should be
        # suppressed because apply_disturbance set _disturbance_triggered=True.
        for _ in range(5):
            env.step(_zero_action(env))
        assert env._recorded_calls == [(None, 2.0)], (
            f"expected exactly the apply_disturbance call, got "
            f"{env._recorded_calls!r}"
        )

    def test_apply_disturbance_emits_deprecation_warning(
        self, env: Any
    ) -> None:
        env.reset()  # No scenario — irrelevant for this test
        with warnings.catch_warnings(record=True) as warning_log:
            warnings.simplefilter("always", DeprecationWarning)
            env.apply_disturbance(magnitude=1.0)
        deprecation_warnings = [
            w for w in warning_log
            if issubclass(w.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) >= 1, (
            "apply_disturbance should emit DeprecationWarning"
        )
        msg = str(deprecation_warnings[0].message)
        assert "deprecated" in msg.lower()
        assert "scenario" in msg.lower() or "reset" in msg.lower()


# ---------------------------------------------------------------------------
# R-4: external _disturbance_type write compat
# ---------------------------------------------------------------------------


class TestR4_DisturbanceTypeAttrCompat:
    def test_external_write_then_apply_disturbance(self, env: Any) -> None:
        """Probe pattern: write _disturbance_type, call apply_disturbance.
        The legacy path must work without AttributeError or warning side-effects."""
        # Standalone doesn't auto-set _disturbance_type — simulate Simulink's
        # behavior by setting it dynamically.
        env._disturbance_type = "pm_step_proxy_bus7"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            env.apply_disturbance(magnitude=0.8)
        assert env._recorded_calls == [(None, 0.8)]
        # Field still readable after the call
        assert env._disturbance_type == "pm_step_proxy_bus7"

    def test_reset_with_scenario_updates_disturbance_type_attr(
        self, env: Any
    ) -> None:
        """When the env has _disturbance_type, reset(scenario=...)
        updates it to the resolved type."""
        env._disturbance_type = "pm_step_single_vsg"  # legacy default
        scenario = Scenario(
            scenario_idx=0,
            disturbance_kind="gen",
            target=2,
            magnitude_sys_pu=1.0,
        )
        env.reset(scenario=scenario)
        assert env._disturbance_type == "pm_step_proxy_g2", (
            f"_disturbance_type should be updated to resolved type, "
            f"got {env._disturbance_type!r}"
        )

    def test_reset_without_disturbance_type_attr_does_not_break(
        self, env: Any
    ) -> None:
        """Standalone has no _disturbance_type. reset(scenario=...) must
        succeed (the hasattr guard skips the legacy attr update)."""
        assert not hasattr(env, "_disturbance_type")
        scenario = _make_scenario(1.0)
        # Should not raise
        obs, info = env.reset(scenario=scenario)
        assert info["resolved_disturbance_type"] == "pm_step_proxy_g2"


# ---------------------------------------------------------------------------
# §1.5b: resolved_disturbance_type recorded in info
# ---------------------------------------------------------------------------


class TestResolvedDisturbanceTypeInInfo:
    def test_reset_info_includes_resolved_type_when_scenario(
        self, env: Any
    ) -> None:
        scenario = Scenario(
            scenario_idx=42, disturbance_kind="bus", target=7,
            magnitude_sys_pu=0.5,
        )
        _, info = env.reset(scenario=scenario)
        assert info["resolved_disturbance_type"] == "pm_step_proxy_bus7"
        assert info["episode_magnitude_sys_pu"] == 0.5

    def test_step_info_carries_resolved_type(self, env: Any) -> None:
        env.reset(scenario=_make_scenario(1.5))
        _, _, _, _, info = env.step(_zero_action(env))
        assert info["resolved_disturbance_type"] == "pm_step_proxy_g2"
        assert info["episode_magnitude_sys_pu"] == 1.5

    def test_reset_info_resolved_type_none_when_legacy(
        self, env: Any
    ) -> None:
        _, info = env.reset()
        assert info["resolved_disturbance_type"] is None
        assert info["episode_magnitude_sys_pu"] is None

    def test_reset_info_resolved_type_constructor_default_for_options_path(
        self, env: Any
    ) -> None:
        """When options['disturbance_magnitude'] used, resolved_type is the
        constructor's _disturbance_type (None on standalone, env-var
        default on Simulink)."""
        env._disturbance_type = "loadstep_paper_random_bus"
        _, info = env.reset(options={"disturbance_magnitude": 0.3})
        assert (
            info["resolved_disturbance_type"]
            == "loadstep_paper_random_bus"
        )
        assert info["episode_magnitude_sys_pu"] == 0.3
