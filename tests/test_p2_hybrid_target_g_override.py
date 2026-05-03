"""Unit tests for H1 — HybridSgEssMultiPoint.target_g_override field.

Verifies (2026-05-04 plan §H1):
  1. target_g_override=2 produces deterministic target_g=2 regardless of RNG
  2. target_g_override=None (default) preserves existing RNG behavior
  3. target_g_override=4 raises ValueError (out of range)
  4. target_g_override=0 raises ValueError (out of range)

No MATLAB engine required — pure Python. Uses FakeBridge pattern from
``tests/test_disturbance_protocols.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest

from scenarios.kundur.disturbance_protocols import HybridSgEssMultiPoint


# ---------------------------------------------------------------------------
# Fixtures — minimal fake bridge + cfg (mirrors test_disturbance_protocols.py)
# ---------------------------------------------------------------------------


@dataclass
class FakeCfg:
    model_name: str = "kundur_cvs_v3"
    n_agents: int = 4
    sbase_va: float = 100e6


class FakeBridge:
    """Records apply_workspace_var calls for audit."""

    def __init__(self, cfg: FakeCfg) -> None:
        self.cfg = cfg
        self.calls: list[tuple[str, float]] = []

    def apply_workspace_var(self, name: str, value: Any) -> None:
        self.calls.append((str(name), float(value)))


def _make_bridge() -> FakeBridge:
    return FakeBridge(FakeCfg())


def _apply_hybrid(
    adapter: HybridSgEssMultiPoint,
    rng: np.random.Generator,
) -> list[tuple[str, float]]:
    """Run adapter.apply with a fake bridge and return recorded calls."""
    bridge = _make_bridge()
    adapter.apply(
        bridge=bridge,
        magnitude_sys_pu=0.5,
        rng=rng,
        t_now=1.0,
        cfg=bridge.cfg,
    )
    return bridge.calls


def _extract_target_g(calls: list[tuple[str, float]]) -> int | None:
    """Extract which G was written (PmgStep_amp_g => positive value).

    The adapter silences all PMG amps first (0.0), then writes the target G
    with a non-zero value. Return the 1-based G index of the non-zero write.
    """
    for name, value in calls:
        if name.startswith("PmgStep_amp_") and value != 0.0:
            g_str = name.removeprefix("PmgStep_amp_")
            return int(g_str)
    return None


# ---------------------------------------------------------------------------
# §1 — target_g_override=2 is deterministic regardless of RNG state
# ---------------------------------------------------------------------------


class TestTargetGOverrideDeterministic:
    def test_override_2_uses_g2(self) -> None:
        adapter = HybridSgEssMultiPoint(target_g_override=2)
        rng_a = np.random.default_rng(0)
        calls = _apply_hybrid(adapter, rng_a)
        assert _extract_target_g(calls) == 2

    def test_override_2_independent_of_rng_seed(self) -> None:
        """Different seeds must all produce G2."""
        adapter = HybridSgEssMultiPoint(target_g_override=2)
        for seed in (0, 1, 42, 999, 2**31 - 1):
            rng = np.random.default_rng(seed)
            calls = _apply_hybrid(adapter, rng)
            assert _extract_target_g(calls) == 2, (
                f"target_g_override=2 produced target_g != 2 with seed={seed}"
            )

    def test_override_1_uses_g1(self) -> None:
        adapter = HybridSgEssMultiPoint(target_g_override=1)
        calls = _apply_hybrid(adapter, np.random.default_rng(0))
        assert _extract_target_g(calls) == 1

    def test_override_3_uses_g3(self) -> None:
        adapter = HybridSgEssMultiPoint(target_g_override=3)
        calls = _apply_hybrid(adapter, np.random.default_rng(0))
        assert _extract_target_g(calls) == 3


# ---------------------------------------------------------------------------
# §2 — target_g_override=None (default) preserves RNG behavior
# ---------------------------------------------------------------------------


class TestTargetGOverrideNonePreservesRng:
    def test_same_seed_produces_same_target(self) -> None:
        """Two runs with same seed must pick the same target_g."""
        adapter = HybridSgEssMultiPoint()  # target_g_override=None
        assert adapter.target_g_override is None

        rng_a = np.random.default_rng(42)
        rng_b = np.random.default_rng(42)
        calls_a = _apply_hybrid(adapter, rng_a)
        calls_b = _apply_hybrid(adapter, rng_b)
        assert _extract_target_g(calls_a) == _extract_target_g(calls_b)

    def test_rng_driven_variation_exists(self) -> None:
        """Across many seeds, all three targets (1/2/3) must be reachable."""
        adapter = HybridSgEssMultiPoint()
        seen = set()
        for seed in range(100):
            rng = np.random.default_rng(seed)
            g = _extract_target_g(_apply_hybrid(adapter, rng))
            if g is not None:
                seen.add(g)
        assert seen == {1, 2, 3}, (
            f"RNG-driven dispatch should reach G1/G2/G3; only saw {seen}"
        )


# ---------------------------------------------------------------------------
# §3 — out-of-range override raises ValueError at construction
# ---------------------------------------------------------------------------


class TestTargetGOverrideValidation:
    def test_override_4_raises(self) -> None:
        with pytest.raises(ValueError, match="1, 2, or 3"):
            HybridSgEssMultiPoint(target_g_override=4)

    def test_override_0_raises(self) -> None:
        with pytest.raises(ValueError, match="1, 2, or 3"):
            HybridSgEssMultiPoint(target_g_override=0)

    def test_override_minus1_raises(self) -> None:
        with pytest.raises(ValueError, match="1, 2, or 3"):
            HybridSgEssMultiPoint(target_g_override=-1)

    def test_valid_overrides_do_not_raise(self) -> None:
        for g in (1, 2, 3):
            HybridSgEssMultiPoint(target_g_override=g)  # must not raise
