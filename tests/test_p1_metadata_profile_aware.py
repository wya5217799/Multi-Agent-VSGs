"""Unit tests for P1-2 — dispatch_metadata per-sys-pu linear floor scaling.

Verifies (2026-05-04 plan, retro §3.5, D2 follow-up):
  1. Schema: DispatchMetadata accepts expected_df_hz_per_sys_pu field without
     breaking existing fields.
  2. Per-sys-pu scaling: effective_floor = expected_df_hz_per_sys_pu * |mag|;
     floor check triggers correctly at boundary values.
  3. Backward compat: dispatches with expected_df_hz_per_sys_pu=None still use
     static expected_min_df_hz (no regression on the ~22 other entries).
  4. Hybrid-specific recalibration: METADATA["pm_step_hybrid_sg_es"] has
     expected_df_hz_per_sys_pu ≈ 0.42 and expected_min_df_hz=None.

No MATLAB engine required — pure Python.
"""

from __future__ import annotations

import pytest

from probes.kundur.probe_state.dispatch_metadata import (
    METADATA,
    DispatchMetadata,
    get_metadata,
)


# ---------------------------------------------------------------------------
# §1 — Schema: new field is constructible alongside existing fields
# ---------------------------------------------------------------------------


class TestDispatchMetadataSchema:
    def test_field_accepted_with_value(self) -> None:
        md = DispatchMetadata(
            name="test_dispatch",
            family="ess_pm_step",
            target_descriptor="bus_7",
            default_magnitude_sys_pu=0.5,
            default_sim_duration_s=5.0,
            expected_behavior="either",
            expected_min_df_hz=None,
            expected_df_hz_per_sys_pu=0.42,
        )
        assert md.expected_df_hz_per_sys_pu == pytest.approx(0.42)

    def test_field_defaults_to_none(self) -> None:
        md = DispatchMetadata(
            name="test_dispatch",
            family="ess_pm_step",
            target_descriptor="bus_7",
            default_magnitude_sys_pu=0.5,
            default_sim_duration_s=5.0,
            expected_behavior="either",
        )
        assert md.expected_df_hz_per_sys_pu is None

    def test_existing_fields_unaffected(self) -> None:
        """Existing field set unchanged when only new field is added."""
        md = DispatchMetadata(
            name="test_dispatch",
            family="hybrid",
            target_descriptor="sg+ess_compensate",
            default_magnitude_sys_pu=0.5,
            default_sim_duration_s=5.0,
            expected_behavior="either",
            expected_min_df_hz=0.30,
            expected_max_df_hz=1.0,
            expected_df_hz_per_sys_pu=None,
        )
        assert md.expected_min_df_hz == pytest.approx(0.30)
        assert md.expected_max_df_hz == pytest.approx(1.0)
        assert md.expected_df_hz_per_sys_pu is None


# ---------------------------------------------------------------------------
# §2 — Per-sys-pu floor scaling logic (simulated, no env needed)
# ---------------------------------------------------------------------------


class TestPerSysPuFloorScaling:
    """Validate the floor-computation math that _dynamics.py applies."""

    _PER_SYS_PU = 0.42
    _MAG = 0.5

    @property
    def effective_floor(self) -> float:
        return self._PER_SYS_PU * abs(self._MAG)

    def test_effective_floor_value(self) -> None:
        """0.42 * 0.5 = 0.21 Hz — no longer below historical 0.30 Hz."""
        assert self.effective_floor == pytest.approx(0.21, rel=1e-3)

    def test_observed_below_effective_floor(self) -> None:
        """Observed 0.20 Hz < effective_floor 0.21 Hz → below_floor=True."""
        observed = 0.20
        below_floor = observed < self.effective_floor
        assert below_floor is True

    def test_observed_above_effective_floor(self) -> None:
        """Observed 0.25 Hz > effective_floor 0.21 Hz → below_floor=False."""
        observed = 0.25
        below_floor = observed < self.effective_floor
        assert below_floor is False

    def test_magnitude_scaling_is_linear(self) -> None:
        """Floor scales linearly: mag=1.55 → floor ≈ 0.65 Hz (historical anchor)."""
        floor_at_historical_mag = self._PER_SYS_PU * 1.55
        assert floor_at_historical_mag == pytest.approx(0.651, abs=0.01)


# ---------------------------------------------------------------------------
# §3 — Backward compat: static expected_min_df_hz path unaffected
# ---------------------------------------------------------------------------


class TestBackwardCompatStaticFloor:
    def test_get_metadata_returns_none_per_sys_pu_for_existing_dispatch(
        self,
    ) -> None:
        """pm_step_proxy_g1 uses static floor; new field must be None."""
        md = get_metadata("pm_step_proxy_g1")
        assert md["expected_df_hz_per_sys_pu"] is None

    def test_get_metadata_static_floor_intact(self) -> None:
        """pm_step_proxy_g1 static floor 0.05 Hz unchanged."""
        md = get_metadata("pm_step_proxy_g1")
        assert md["expected_min_df_hz"] == pytest.approx(0.05)

    def test_missing_metadata_includes_new_field(self) -> None:
        """Unknown dispatch: get_metadata returns expected_df_hz_per_sys_pu=None."""
        md = get_metadata("nonexistent_dispatch_xyz")
        assert "expected_df_hz_per_sys_pu" in md
        assert md["expected_df_hz_per_sys_pu"] is None

    def test_all_non_hybrid_dispatches_have_none_per_sys_pu(self) -> None:
        """Only pm_step_hybrid_sg_es should have per_sys_pu set; others None."""
        for name, entry in METADATA.items():
            if name == "pm_step_hybrid_sg_es":
                continue  # tested separately
            assert entry.expected_df_hz_per_sys_pu is None, (
                f"Dispatch {name!r} unexpectedly has expected_df_hz_per_sys_pu set "
                f"(value={entry.expected_df_hz_per_sys_pu}). Only pm_step_hybrid_sg_es "
                "should have this field populated in P1-2."
            )


# ---------------------------------------------------------------------------
# §4 — Hybrid-specific recalibration: pm_step_hybrid_sg_es
# ---------------------------------------------------------------------------


class TestHybridRecalibration:
    def test_per_sys_pu_set(self) -> None:
        """Hybrid entry must have expected_df_hz_per_sys_pu populated."""
        entry = METADATA["pm_step_hybrid_sg_es"]
        assert entry.expected_df_hz_per_sys_pu is not None

    def test_per_sys_pu_value_approx_0_42(self) -> None:
        """Value should be ~0.42 Hz/sys-pu (0.65 Hz / 1.55 sys-pu)."""
        entry = METADATA["pm_step_hybrid_sg_es"]
        assert entry.expected_df_hz_per_sys_pu == pytest.approx(0.42, abs=0.02)

    def test_static_min_df_hz_is_none(self) -> None:
        """Static floor nulled out; per-sys-pu field is sole floor authority."""
        entry = METADATA["pm_step_hybrid_sg_es"]
        assert entry.expected_min_df_hz is None

    def test_ceiling_unchanged(self) -> None:
        """expected_max_df_hz must remain 1.0 Hz (not touched by P1-2)."""
        entry = METADATA["pm_step_hybrid_sg_es"]
        assert entry.expected_max_df_hz == pytest.approx(1.0)

    def test_get_metadata_exposes_per_sys_pu(self) -> None:
        """get_metadata dict includes the new field for downstream consumers."""
        md = get_metadata("pm_step_hybrid_sg_es")
        assert "expected_df_hz_per_sys_pu" in md
        assert md["expected_df_hz_per_sys_pu"] == pytest.approx(0.42, abs=0.02)

    def test_get_metadata_static_floor_is_none(self) -> None:
        """get_metadata must expose None for static floor on hybrid."""
        md = get_metadata("pm_step_hybrid_sg_es")
        assert md["expected_min_df_hz"] is None

    def test_effective_floor_at_probe_mag_no_longer_triggers(self) -> None:
        """Effective floor at probe mag=0.5 ≈ 0.21 Hz; observed 0.21 Hz is ok."""
        entry = METADATA["pm_step_hybrid_sg_es"]
        probe_mag = 0.5
        effective_floor = entry.expected_df_hz_per_sys_pu * abs(probe_mag)
        # Probe observed 0.18-0.21 Hz historically flagged as false alarm.
        # With linear scaling, 0.21 is right at the boundary — test that
        # observed values at or just above do NOT trigger below_floor.
        assert not (0.21 < effective_floor), (
            f"At probe mag=0.5, effective_floor={effective_floor:.4f} Hz "
            f"should be <= 0.21 Hz (observed range). Got floor={effective_floor:.4f}"
        )
