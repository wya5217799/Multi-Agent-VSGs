"""Unit tests for P1-1: g4_position_hz threshold wired into G4_position verdict.

Verifies (2026-05-04 plan §P1-1):
  1. Three dispatches with per-agent max|Δf| values straddling the 0.10 Hz boundary
     produce 3 distinct responder signatures → G4 PASS.
  2. The same payload evaluated with the old 1 mHz floor (g1_respond_hz) collapses all
     dispatches to one signature → G4 REJECT (confirms threshold matters).
  3. A custom ProbeThresholds(g4_position_hz=0.5) is respected in the verdict.

No MATLAB engine required — pure Python.
"""
from __future__ import annotations

from typing import Any

import pytest

from probes.kundur.probe_state import _verdict
from probes.kundur.probe_state.probe_config import ProbeThresholds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_snap(dispatches: dict[str, Any]) -> dict[str, Any]:
    """Minimal snapshot carrying only the phase4_per_dispatch data needed by G4."""
    return {
        "phase4_per_dispatch": {
            "dispatches": dispatches,
        }
    }


def _dispatch(per_agent_hz: list[float]) -> dict[str, Any]:
    """Build a minimal dispatch entry with per-agent max|Δf| values."""
    return {
        "max_abs_f_dev_hz_per_agent": per_agent_hz,
        # G4 only reads max_abs_f_dev_hz_per_agent; include this for schema completeness.
        "max_abs_f_dev_hz_global": max(per_agent_hz),
        "agents_responding_above_1mHz": sum(1 for v in per_agent_hz if v > 1e-3),
    }


# ---------------------------------------------------------------------------
# §1 — Threshold wiring: 3 dispatches → 3 distinct signatures → G4 PASS
# ---------------------------------------------------------------------------


class TestG4ThresholdWiring:
    """At 0.10 Hz floor, different dispatch sites produce different mode-shape buckets."""

    # dispatch_a: only agent 0 is above 0.10 Hz  → signature (0,)
    # dispatch_b: only agent 1 is above 0.10 Hz  → signature (1,)
    # dispatch_c: agents 0 and 1 above 0.10 Hz   → signature (0, 1)
    DISPATCHES = {
        "dispatch_a": _dispatch([0.50, 0.05, 0.05, 0.05]),
        "dispatch_b": _dispatch([0.05, 0.50, 0.05, 0.05]),
        "dispatch_c": _dispatch([0.50, 0.50, 0.05, 0.05]),
    }

    def test_three_distinct_signatures_yield_pass(self) -> None:
        snap = _make_snap(self.DISPATCHES)
        result = _verdict._g4_position(snap)
        assert result["verdict"] == "PASS", (
            f"Expected G4 PASS with 3 distinct signatures; got {result['verdict']!r}. "
            f"signatures={result.get('signatures')}"
        )

    def test_signature_count_is_three(self) -> None:
        snap = _make_snap(self.DISPATCHES)
        result = _verdict._g4_position(snap)
        sigs = result.get("signatures", {})
        unique_sigs = {tuple(v) for v in sigs.values()}
        assert len(unique_sigs) == 3, (
            f"Expected 3 distinct signatures; got {len(unique_sigs)}: {sigs}"
        )

    def test_evidence_string_mentions_3_distinct(self) -> None:
        snap = _make_snap(self.DISPATCHES)
        result = _verdict._g4_position(snap)
        evidence = result.get("evidence", "")
        assert "3 distinct" in evidence, (
            f"Evidence string should mention '3 distinct'; got: {evidence!r}"
        )

    def test_dispatch_a_signature_is_agent_0_only(self) -> None:
        snap = _make_snap(self.DISPATCHES)
        result = _verdict._g4_position(snap)
        assert result["signatures"]["dispatch_a"] == [0], (
            f"dispatch_a: only agent 0 above 0.10 Hz; got {result['signatures']['dispatch_a']}"
        )

    def test_dispatch_b_signature_is_agent_1_only(self) -> None:
        snap = _make_snap(self.DISPATCHES)
        result = _verdict._g4_position(snap)
        assert result["signatures"]["dispatch_b"] == [1], (
            f"dispatch_b: only agent 1 above 0.10 Hz; got {result['signatures']['dispatch_b']}"
        )

    def test_dispatch_c_signature_is_agents_0_and_1(self) -> None:
        snap = _make_snap(self.DISPATCHES)
        result = _verdict._g4_position(snap)
        assert result["signatures"]["dispatch_c"] == [0, 1], (
            f"dispatch_c: agents 0+1 above 0.10 Hz; got {result['signatures']['dispatch_c']}"
        )


# ---------------------------------------------------------------------------
# §2 — Old threshold (1 mHz) would collapse to one signature → G4 REJECT
# ---------------------------------------------------------------------------


class TestOldThresholdCollapse:
    """With 1 mHz floor every agent (min value = 0.05 Hz >> 1 mHz) always responds.

    All three dispatches produce signature (0, 1, 2, 3) → only 1 distinct → G4 REJECT.
    Confirms the new 0.10 Hz threshold is not cosmetic.
    """

    DISPATCHES = {
        "dispatch_a": _dispatch([0.50, 0.05, 0.05, 0.05]),
        "dispatch_b": _dispatch([0.05, 0.50, 0.05, 0.05]),
        "dispatch_c": _dispatch([0.50, 0.50, 0.05, 0.05]),
    }

    def test_one_mHz_floor_collapses_to_single_signature(self) -> None:
        """Monkeypatch THRESHOLDS so g4_position_hz = 1e-3 (old behaviour)."""
        import probes.kundur.probe_state.probe_config as pc

        old_thresholds = pc.THRESHOLDS
        pc.THRESHOLDS = ProbeThresholds(g4_position_hz=1e-3)  # 1 mHz — old value
        try:
            snap = _make_snap(self.DISPATCHES)
            result = _verdict._g4_position(snap)
            sigs = result.get("signatures", {})
            unique_sigs = {tuple(v) for v in sigs.values()}
            assert len(unique_sigs) == 1, (
                f"At 1 mHz floor all agents respond (min value 0.05 Hz >> 1 mHz); "
                f"expected 1 distinct signature, got {len(unique_sigs)}: {sigs}"
            )
            assert result["verdict"] == "REJECT", (
                f"At 1 mHz floor G4 should REJECT (signature collapse); "
                f"got {result['verdict']!r}"
            )
        finally:
            pc.THRESHOLDS = old_thresholds

    def test_new_threshold_is_not_1mHz(self) -> None:
        """Confirm the production threshold is NOT the old 1 mHz value."""
        import probes.kundur.probe_state.probe_config as pc

        assert pc.THRESHOLDS.g4_position_hz != 1e-3, (
            "Production g4_position_hz must not be 1 mHz (the collapsing old value); "
            f"got {pc.THRESHOLDS.g4_position_hz}"
        )


# ---------------------------------------------------------------------------
# §3 — Threshold override via ProbeThresholds
# ---------------------------------------------------------------------------


class TestThresholdOverride:
    """Custom ProbeThresholds(g4_position_hz=0.5) is respected by the verdict."""

    # With a 0.50 Hz floor all values at 0.50 are exactly at the boundary.
    # Values strictly > 0.50 respond; values at or below 0.50 do not.
    # dispatch_x: agent 0 = 0.60 Hz (above 0.50) → signature (0,)
    # dispatch_y: agent 1 = 0.60 Hz (above 0.50) → signature (1,)
    # → 2 distinct → G4 PASS under 0.50 Hz floor
    # But under the default 0.10 Hz floor:
    #   all values (0.60, 0.50, ...) would be above 0.10 → signature (0,1,2,3) for both
    #   Wait: 0.50 > 0.10 is True, so we need values that separate only under 0.50 floor.
    # dispatch_x: [0.60, 0.30, 0.30, 0.30] — agent 0 > 0.50, others ≤ 0.50  → (0,)
    # dispatch_y: [0.30, 0.60, 0.30, 0.30] — agent 1 > 0.50, others ≤ 0.50  → (1,)
    # Under 0.10 Hz default floor all four agents respond in both dispatches → same sig.
    DISPATCHES_FOR_OVERRIDE = {
        "dispatch_x": _dispatch([0.60, 0.30, 0.30, 0.30]),
        "dispatch_y": _dispatch([0.30, 0.60, 0.30, 0.30]),
    }

    def test_default_floor_collapses(self) -> None:
        """Under default 0.10 Hz floor [0.60, 0.30, 0.30, 0.30] all > 0.10 → same sig."""
        import probes.kundur.probe_state.probe_config as pc

        # Confirm 0.30 > 0.10 (default) = True → all agents respond under default floor.
        assert pc.THRESHOLDS.g4_position_hz < 0.30, (
            "Pre-condition: default floor must be below 0.30 Hz for this test"
        )
        snap = _make_snap(self.DISPATCHES_FOR_OVERRIDE)
        result = _verdict._g4_position(snap)
        sigs = result.get("signatures", {})
        unique_sigs = {tuple(v) for v in sigs.values()}
        assert len(unique_sigs) == 1, (
            f"Under 0.10 Hz default floor all agents (min 0.30 Hz) respond; "
            f"expected 1 distinct sig; got {len(unique_sigs)}: {sigs}"
        )
        assert result["verdict"] == "REJECT"

    def test_custom_05hz_floor_separates_signatures(self) -> None:
        """ProbeThresholds(g4_position_hz=0.5) buckets [0.60 vs 0.30] distinctly."""
        import probes.kundur.probe_state.probe_config as pc

        old_thresholds = pc.THRESHOLDS
        pc.THRESHOLDS = ProbeThresholds(g4_position_hz=0.50)
        try:
            snap = _make_snap(self.DISPATCHES_FOR_OVERRIDE)
            result = _verdict._g4_position(snap)
            sigs = result.get("signatures", {})
            unique_sigs = {tuple(v) for v in sigs.values()}
            assert len(unique_sigs) == 2, (
                f"Under 0.50 Hz floor only agent with 0.60 Hz responds; "
                f"expected 2 distinct sigs; got {len(unique_sigs)}: {sigs}"
            )
            assert result["verdict"] == "PASS", (
                f"Under 0.50 Hz floor 2 distinct signatures → G4 PASS; "
                f"got {result['verdict']!r}"
            )
        finally:
            pc.THRESHOLDS = old_thresholds
