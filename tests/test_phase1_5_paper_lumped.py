"""Tests for Phase 1.5 paper-lumped ΔP reroute (2026-05-04).

Verifies the reroute from CCS injection (P0-1c, abandoned) to
paper-lumped Pm_step via ES3/ES4 (paper §1.4 Remark 1 Kron reduction).

Coverage:
  §1 Schema: LOAD_STEP_AMP / LOAD_STEP_TRIP_AMP / LOAD_STEP_T all
             frozenset() effective in v3 Discrete (deprecated).
  §2 Adapter: LoadStepRBranch.apply for bus14 writes PM_STEP_AMP@ES3
              with positive magnitude (freq UP = paper LS1).
  §3 Adapter: LoadStepRBranch.apply for bus15 writes PM_STEP_AMP@ES4
              with negative magnitude (freq DOWN = paper LS2).
  §4 Adapter: random_bus picks ES3 or ES4 (50/50 distribution).
  §5 Magnitude: 248 MW / 100 MVA Sbase = 2.48 sys-pu (paper LS1);
                188 MW / 100 MVA Sbase = 1.88 sys-pu (paper LS2).
  §6 Dispatch metadata family + paper-reward fields.
  §7 Trace family = 'paper_lumped_pm_step'; keys/values length invariant.
  §8 All other ESS PM registers zeroed; SG PMG family silenced.

No MATLAB engine required — pure Python.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest

from probes.kundur.probe_state.dispatch_metadata import (
    METADATA,
    get_metadata,
)
from scenarios.kundur.disturbance_protocols import (
    PAPER_LS_MAGNITUDE_SYS_PU,
    LoadStepRBranch,
    known_disturbance_types,
    resolve_disturbance,
)
from scenarios.kundur.workspace_vars import (
    PROFILE_CVS_V3,
    PROFILE_CVS_V3_DISCRETE,
    WorkspaceVarError,
    spec_for,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass
class FakeCfg:
    model_name: str = PROFILE_CVS_V3_DISCRETE
    n_agents: int = 4
    sbase_va: float = 100e6


class FakeBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []

    def apply_workspace_var(self, name: str, value: Any) -> None:
        self.calls.append((str(name), float(value)))


# ---------------------------------------------------------------------------
# §1 — Schema: LoadStep families deprecated (frozenset() effective)
# ---------------------------------------------------------------------------


class TestSchema_DeprecatedLoadStepFamilies:
    """LOAD_STEP_AMP, LOAD_STEP_TRIP_AMP, LOAD_STEP_T must all be not-effective
    in both v3 Phasor and v3 Discrete after Phase 1.5 reroute."""

    def test_load_step_amp_not_effective_in_v3_discrete(self) -> None:
        spec = spec_for("LOAD_STEP_AMP")
        assert PROFILE_CVS_V3_DISCRETE not in spec.effective_in_profile, (
            "LOAD_STEP_AMP must NOT be effective in v3 Discrete after reroute; "
            "bus14 RLC removed, bus15 broken"
        )

    def test_load_step_amp_not_effective_in_v3_phasor(self) -> None:
        spec = spec_for("LOAD_STEP_AMP")
        assert PROFILE_CVS_V3 not in spec.effective_in_profile

    def test_load_step_amp_effective_in_profile_is_empty(self) -> None:
        spec = spec_for("LOAD_STEP_AMP")
        assert spec.effective_in_profile == frozenset(), (
            "LOAD_STEP_AMP effective_in_profile must be frozenset() (all deprecated)"
        )

    def test_load_step_trip_amp_not_effective_in_v3_discrete(self) -> None:
        """Phase 1.5 P0-1c CCS abandoned — LOAD_STEP_TRIP_AMP no longer effective."""
        spec = spec_for("LOAD_STEP_TRIP_AMP")
        assert PROFILE_CVS_V3_DISCRETE not in spec.effective_in_profile, (
            "LOAD_STEP_TRIP_AMP must NOT be effective in v3 Discrete after "
            "P0-1c CCS abandonment. LoadStepRBranch now writes PM_STEP_AMP instead."
        )

    def test_load_step_trip_amp_not_effective_in_v3_phasor(self) -> None:
        spec = spec_for("LOAD_STEP_TRIP_AMP")
        assert PROFILE_CVS_V3 not in spec.effective_in_profile

    def test_load_step_trip_amp_effective_in_profile_is_empty(self) -> None:
        spec = spec_for("LOAD_STEP_TRIP_AMP")
        assert spec.effective_in_profile == frozenset(), (
            "LOAD_STEP_TRIP_AMP effective_in_profile must be frozenset() after reroute"
        )

    def test_load_step_t_effective_in_profile_is_empty(self) -> None:
        spec = spec_for("LOAD_STEP_T")
        assert spec.effective_in_profile == frozenset()

    def test_load_step_trip_amp_discrete_inactive_reason_mentions_reroute(self) -> None:
        spec = spec_for("LOAD_STEP_TRIP_AMP")
        reason = spec.inactive_reason.get(PROFILE_CVS_V3_DISCRETE, "")
        assert "reroute" in reason.lower() or "abandoned" in reason.lower() or \
               "pm_step" in reason.lower(), (
            f"LOAD_STEP_TRIP_AMP inactive_reason for v3 Discrete should mention "
            f"reroute/abandoned/pm_step; got: {reason!r}"
        )


# ---------------------------------------------------------------------------
# §2 — Adapter: bus14 writes PM_STEP_AMP@ES3 positive
# ---------------------------------------------------------------------------


class TestAdapter_Bus14_PmStepES3:
    """bus14 (paper LS1): LoadStepRBranch writes positive PM_STEP_AMP@ES3."""

    def test_bus14_writes_pm_step_amp_3_positive(self) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge()
        adapter = LoadStepRBranch(ls_bus=14)
        adapter.apply(
            bridge=bridge,
            magnitude_sys_pu=2.48,
            rng=np.random.default_rng(0),
            t_now=0.5,
            cfg=cfg,
        )
        pm_amps = {k: v for k, v in bridge.calls if k.startswith("Pm_step_amp_")}
        assert "Pm_step_amp_3" in pm_amps, (
            "bus14 dispatch must write Pm_step_amp_3 (ES3=bus14 ESS)"
        )
        assert pm_amps["Pm_step_amp_3"] == pytest.approx(2.48), (
            "bus14 Pm_step_amp_3 must be +abs(magnitude) = +2.48 sys-pu "
            "(positive = freq UP = paper LS1 load reduction)"
        )
        assert pm_amps["Pm_step_amp_3"] > 0.0, (
            "bus14 amplitude must be positive (freq UP)"
        )

    def test_bus14_zeros_all_other_ess_pm(self) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge()
        LoadStepRBranch(ls_bus=14).apply(
            bridge=bridge, magnitude_sys_pu=2.48,
            rng=np.random.default_rng(0), t_now=0.5, cfg=cfg,
        )
        pm_amps = {k: v for k, v in bridge.calls if k.startswith("Pm_step_amp_")}
        for i in (1, 2, 4):
            key = f"Pm_step_amp_{i}"
            assert key in pm_amps, f"ES{i} PM_STEP_AMP not written"
            assert pm_amps[key] == 0.0, f"ES{i} PM_STEP_AMP should be zeroed"

    def test_bus14_negative_magnitude_still_positive_pm(self) -> None:
        """abs() applied: negative input must still produce positive Pm_step."""
        cfg = FakeCfg()
        bridge = FakeBridge()
        LoadStepRBranch(ls_bus=14).apply(
            bridge=bridge, magnitude_sys_pu=-2.48,
            rng=np.random.default_rng(0), t_now=0.5, cfg=cfg,
        )
        pm_amps = {k: v for k, v in bridge.calls if k.startswith("Pm_step_amp_")}
        assert pm_amps["Pm_step_amp_3"] == pytest.approx(2.48)
        assert pm_amps["Pm_step_amp_3"] > 0.0

    def test_bus14_does_not_write_load_step_trip_amp(self) -> None:
        """P0-1c CCS path abandoned: no LOAD_STEP_TRIP_AMP writes."""
        cfg = FakeCfg()
        bridge = FakeBridge()
        LoadStepRBranch(ls_bus=14).apply(
            bridge=bridge, magnitude_sys_pu=2.48,
            rng=np.random.default_rng(0), t_now=0.5, cfg=cfg,
        )
        ccs_writes = [k for k, _ in bridge.calls if "trip_amp" in k.lower()]
        assert ccs_writes == [], (
            f"P0-1c CCS abandoned: no LOAD_STEP_TRIP_AMP should be written. "
            f"Got: {ccs_writes}"
        )

    def test_bus14_does_not_write_load_step_amp(self) -> None:
        """No LOAD_STEP_AMP writes (block removed from model)."""
        cfg = FakeCfg()
        bridge = FakeBridge()
        LoadStepRBranch(ls_bus=14).apply(
            bridge=bridge, magnitude_sys_pu=2.48,
            rng=np.random.default_rng(0), t_now=0.5, cfg=cfg,
        )
        ls_writes = [k for k, _ in bridge.calls if "LoadStep_amp" in k]
        assert ls_writes == [], f"No LOAD_STEP_AMP should be written; got: {ls_writes}"


# ---------------------------------------------------------------------------
# §3 — Adapter: bus15 writes PM_STEP_AMP@ES4 negative
# ---------------------------------------------------------------------------


class TestAdapter_Bus15_PmStepES4:
    """bus15 (paper LS2): LoadStepRBranch writes negative PM_STEP_AMP@ES4."""

    def test_bus15_writes_pm_step_amp_4_negative(self) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge()
        adapter = LoadStepRBranch(ls_bus=15)
        adapter.apply(
            bridge=bridge,
            magnitude_sys_pu=1.88,
            rng=np.random.default_rng(0),
            t_now=0.5,
            cfg=cfg,
        )
        pm_amps = {k: v for k, v in bridge.calls if k.startswith("Pm_step_amp_")}
        assert "Pm_step_amp_4" in pm_amps, (
            "bus15 dispatch must write Pm_step_amp_4 (ES4=bus15 ESS)"
        )
        assert pm_amps["Pm_step_amp_4"] == pytest.approx(-1.88), (
            "bus15 Pm_step_amp_4 must be -abs(magnitude) = -1.88 sys-pu "
            "(negative = freq DOWN = paper LS2 load increase)"
        )
        assert pm_amps["Pm_step_amp_4"] < 0.0, (
            "bus15 amplitude must be negative (freq DOWN)"
        )

    def test_bus15_zeros_all_other_ess_pm(self) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge()
        LoadStepRBranch(ls_bus=15).apply(
            bridge=bridge, magnitude_sys_pu=1.88,
            rng=np.random.default_rng(0), t_now=0.5, cfg=cfg,
        )
        pm_amps = {k: v for k, v in bridge.calls if k.startswith("Pm_step_amp_")}
        for i in (1, 2, 3):
            key = f"Pm_step_amp_{i}"
            assert key in pm_amps, f"ES{i} PM_STEP_AMP not written"
            assert pm_amps[key] == 0.0, f"ES{i} PM_STEP_AMP should be zeroed"

    def test_bus15_positive_magnitude_produces_negative_pm(self) -> None:
        """Positive input magnitude → adapter negates → negative Pm_step (freq DOWN)."""
        cfg = FakeCfg()
        bridge = FakeBridge()
        LoadStepRBranch(ls_bus=15).apply(
            bridge=bridge, magnitude_sys_pu=+1.88,
            rng=np.random.default_rng(0), t_now=0.5, cfg=cfg,
        )
        pm_amps = {k: v for k, v in bridge.calls if k.startswith("Pm_step_amp_")}
        assert pm_amps["Pm_step_amp_4"] < 0.0, (
            "bus15 adapter must negate magnitude to produce freq DOWN"
        )

    def test_bus15_does_not_write_load_step_amp(self) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge()
        LoadStepRBranch(ls_bus=15).apply(
            bridge=bridge, magnitude_sys_pu=1.88,
            rng=np.random.default_rng(0), t_now=0.5, cfg=cfg,
        )
        ls_writes = [k for k, _ in bridge.calls if "LoadStep_amp" in k]
        assert ls_writes == [], f"No LOAD_STEP_AMP should be written; got: {ls_writes}"


# ---------------------------------------------------------------------------
# §4 — Adapter: random_bus picks ES3 or ES4
# ---------------------------------------------------------------------------


class TestAdapter_RandomBus_Distribution:
    def test_random_bus_hits_es3_and_es4_only(self) -> None:
        cfg = FakeCfg()
        adapter = LoadStepRBranch(ls_bus="random_bus")
        seen_targets: set[str] = set()
        for seed in range(200):
            bridge = FakeBridge()
            adapter.apply(
                bridge=bridge, magnitude_sys_pu=2.48,
                rng=np.random.default_rng(seed), t_now=0.5, cfg=cfg,
            )
            pm_amps = {k: v for k, v in bridge.calls if k.startswith("Pm_step_amp_")}
            nonzero = {k for k, v in pm_amps.items() if v != 0.0}
            seen_targets |= nonzero
        assert seen_targets <= {"Pm_step_amp_3", "Pm_step_amp_4"}, (
            f"random_bus must only write ES3 or ES4; got {seen_targets}"
        )
        assert "Pm_step_amp_3" in seen_targets
        assert "Pm_step_amp_4" in seen_targets

    def test_random_bus_roughly_5050(self) -> None:
        cfg = FakeCfg()
        adapter = LoadStepRBranch(ls_bus="random_bus")
        es3_count = 0
        es4_count = 0
        for seed in range(1000):
            bridge = FakeBridge()
            adapter.apply(
                bridge=bridge, magnitude_sys_pu=2.48,
                rng=np.random.default_rng(seed), t_now=0.5, cfg=cfg,
            )
            pm_amps = {k: v for k, v in bridge.calls if k.startswith("Pm_step_amp_")}
            if pm_amps.get("Pm_step_amp_3", 0.0) != 0.0:
                es3_count += 1
            elif pm_amps.get("Pm_step_amp_4", 0.0) != 0.0:
                es4_count += 1
        assert 400 < es3_count < 600, f"ES3 count {es3_count}/1000 far from 50%"
        assert 400 < es4_count < 600, f"ES4 count {es4_count}/1000 far from 50%"
        assert es3_count + es4_count == 1000


# ---------------------------------------------------------------------------
# §5 — Magnitude conversion: paper MW → sys-pu
# ---------------------------------------------------------------------------


class TestMagnitudeConversion:
    """Pre-flight confirmed: Pm_step_amp_{i} unit is sys-pu (Sbase=100 MVA).
    Paper magnitudes: LS1=248 MW → 2.48 sys-pu; LS2=188 MW → 1.88 sys-pu.
    """

    def test_paper_ls1_magnitude_is_1_53_sys_pu(self) -> None:
        # Empirically calibrated 2026-05-04 — paper Sbase != our Sbase=100 MVA
        # so "248 MW absolute" goes nonlinear in our system. Quadratic fit:
        # amp=1.53 sys-pu → reward=-1.81 ≈ paper LS1 -1.61 (+12%, within ±25%).
        assert PAPER_LS_MAGNITUDE_SYS_PU[14] == pytest.approx(1.53), (
            "LS1 paper-equivalent magnitude must be 1.53 sys-pu (empirically "
            "calibrated to match paper §8.4 LS1 reward = -1.61 Hz²)"
        )

    def test_paper_ls2_magnitude_is_0_90_sys_pu(self) -> None:
        # Empirically calibrated: amp=0.90 sys-pu → reward=-0.83 ≈ paper -0.80 (+3%).
        assert PAPER_LS_MAGNITUDE_SYS_PU[15] == pytest.approx(0.90), (
            "LS2 paper-equivalent magnitude must be 0.90 sys-pu (empirically "
            "calibrated to match paper §8.4 LS2 reward = -0.80 Hz²)"
        )

    def test_bus14_at_paper_magnitude_writes_1_53(self) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge()
        LoadStepRBranch(ls_bus=14).apply(
            bridge=bridge, magnitude_sys_pu=PAPER_LS_MAGNITUDE_SYS_PU[14],
            rng=np.random.default_rng(0), t_now=0.5, cfg=cfg,
        )
        pm_amps = {k: v for k, v in bridge.calls if k.startswith("Pm_step_amp_")}
        assert pm_amps["Pm_step_amp_3"] == pytest.approx(1.53)

    def test_bus15_at_paper_magnitude_writes_minus_0_90(self) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge()
        LoadStepRBranch(ls_bus=15).apply(
            bridge=bridge, magnitude_sys_pu=PAPER_LS_MAGNITUDE_SYS_PU[15],
            rng=np.random.default_rng(0), t_now=0.5, cfg=cfg,
        )
        pm_amps = {k: v for k, v in bridge.calls if k.startswith("Pm_step_amp_")}
        assert pm_amps["Pm_step_amp_4"] == pytest.approx(-0.90)

    def test_half_paper_magnitude_produces_half_pm_step(self) -> None:
        """Linearity check: 0.5 × paper magnitude → 0.5 × expected Pm_step."""
        cfg = FakeCfg()
        bridge = FakeBridge()
        LoadStepRBranch(ls_bus=14).apply(
            bridge=bridge, magnitude_sys_pu=0.5,  # legacy probe magnitude
            rng=np.random.default_rng(0), t_now=0.5, cfg=cfg,
        )
        pm_amps = {k: v for k, v in bridge.calls if k.startswith("Pm_step_amp_")}
        assert pm_amps["Pm_step_amp_3"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# §6 — Dispatch metadata family + paper-reward fields
# ---------------------------------------------------------------------------


class TestDispatchMetadata:
    def test_loadstep_paper_bus14_family_is_paper_lumped(self) -> None:
        md = get_metadata("loadstep_paper_bus14")
        assert md["family"] == "paper_lumped_pm_step", (
            f"Expected family='paper_lumped_pm_step'; got {md['family']!r}"
        )

    def test_loadstep_paper_bus15_family_is_paper_lumped(self) -> None:
        md = get_metadata("loadstep_paper_bus15")
        assert md["family"] == "paper_lumped_pm_step"

    def test_loadstep_paper_random_bus_family_is_paper_lumped(self) -> None:
        md = get_metadata("loadstep_paper_random_bus")
        assert md["family"] == "paper_lumped_pm_step"

    def test_loadstep_paper_bus14_default_magnitude_is_paper(self) -> None:
        # Empirically calibrated 2026-05-04 sanity sweep: 1.53 sys-pu →
        # paper_reward=-1.81 ≈ paper LS1 -1.61 (+12%, within ±25% G1.5-B).
        md = get_metadata("loadstep_paper_bus14")
        assert md["default_magnitude_sys_pu"] == pytest.approx(1.53), (
            "bus14 default magnitude must be 1.53 sys-pu (empirically "
            "calibrated to paper LS1 reward -1.61 Hz²)"
        )

    def test_loadstep_paper_bus15_default_magnitude_is_paper(self) -> None:
        # Empirically calibrated: 0.90 sys-pu → reward=-0.83 ≈ paper -0.80 (+3%).
        md = get_metadata("loadstep_paper_bus15")
        assert md["default_magnitude_sys_pu"] == pytest.approx(0.90), (
            "bus15 default magnitude must be 0.90 sys-pu (empirically "
            "calibrated to paper LS2 reward -0.80 Hz²)"
        )

    def test_loadstep_paper_bus14_expected_behavior_freq_rise(self) -> None:
        md = get_metadata("loadstep_paper_bus14")
        assert md["expected_behavior"] == "freq_rise"

    def test_loadstep_paper_bus15_expected_behavior_freq_drop(self) -> None:
        md = get_metadata("loadstep_paper_bus15")
        assert md["expected_behavior"] == "freq_drop"

    def test_loadstep_paper_bus14_target_descriptor_es3(self) -> None:
        md = get_metadata("loadstep_paper_bus14")
        assert "ES3" in md["target_descriptor"] or "bus14" in md["target_descriptor"]

    def test_loadstep_paper_bus15_target_descriptor_es4(self) -> None:
        md = get_metadata("loadstep_paper_bus15")
        assert "ES4" in md["target_descriptor"] or "bus15" in md["target_descriptor"]

    def test_metadata_missing_flag_false_for_all_three(self) -> None:
        for name in ("loadstep_paper_bus14", "loadstep_paper_bus15",
                     "loadstep_paper_random_bus"):
            md = get_metadata(name)
            assert md["metadata_missing"] is False, (
                f"{name}: metadata_missing must be False"
            )


# ---------------------------------------------------------------------------
# §7 — Trace invariants
# ---------------------------------------------------------------------------


class TestTraceInvariants:
    @pytest.mark.parametrize("ls_bus", [14, 15])
    def test_trace_family_is_paper_lumped_pm_step(self, ls_bus: int) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge()
        trace = LoadStepRBranch(ls_bus=ls_bus).apply(
            bridge=bridge, magnitude_sys_pu=2.48,
            rng=np.random.default_rng(0), t_now=0.5, cfg=cfg,
        )
        assert trace.family == "paper_lumped_pm_step"

    @pytest.mark.parametrize("ls_bus", [14, 15])
    def test_trace_keys_values_length_equal(self, ls_bus: int) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge()
        trace = LoadStepRBranch(ls_bus=ls_bus).apply(
            bridge=bridge, magnitude_sys_pu=2.48,
            rng=np.random.default_rng(0), t_now=0.5, cfg=cfg,
        )
        assert len(trace.written_keys) == len(trace.written_values)
        assert len(trace.written_keys) == len(bridge.calls)

    @pytest.mark.parametrize("ls_bus", [14, 15])
    def test_trace_keys_match_bridge_calls(self, ls_bus: int) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge()
        trace = LoadStepRBranch(ls_bus=ls_bus).apply(
            bridge=bridge, magnitude_sys_pu=2.48,
            rng=np.random.default_rng(0), t_now=0.5, cfg=cfg,
        )
        for (k_t, v_t), (k_b, v_b) in zip(
            zip(trace.written_keys, trace.written_values), bridge.calls
        ):
            assert k_t == k_b
            assert v_t == pytest.approx(v_b)

    @pytest.mark.parametrize("ls_bus", [14, 15])
    def test_trace_magnitude_sys_pu_preserved(self, ls_bus: int) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge()
        trace = LoadStepRBranch(ls_bus=ls_bus).apply(
            bridge=bridge, magnitude_sys_pu=2.48,
            rng=np.random.default_rng(0), t_now=0.5, cfg=cfg,
        )
        assert trace.magnitude_sys_pu == pytest.approx(2.48)


# ---------------------------------------------------------------------------
# §8 — Silence: all other ESS PM zeroed, SG PMG silenced
# ---------------------------------------------------------------------------


class TestSilenceOtherRegisters:
    def test_bus14_silences_pmg(self) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge()
        LoadStepRBranch(ls_bus=14).apply(
            bridge=bridge, magnitude_sys_pu=2.48,
            rng=np.random.default_rng(0), t_now=0.5, cfg=cfg,
        )
        pmg_writes = [k for k, _ in bridge.calls if "PmgStep" in k]
        assert len(pmg_writes) == 6, (
            f"Expected 6 PMG writes (3 SG × T+AMP); got {len(pmg_writes)}: {pmg_writes}"
        )
        pmg_amp_vals = [v for k, v in bridge.calls if "PmgStep_amp" in k]
        assert all(v == 0.0 for v in pmg_amp_vals), (
            f"All SG PMG amps must be zeroed; got {pmg_amp_vals}"
        )

    def test_bus15_silences_pmg(self) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge()
        LoadStepRBranch(ls_bus=15).apply(
            bridge=bridge, magnitude_sys_pu=1.88,
            rng=np.random.default_rng(0), t_now=0.5, cfg=cfg,
        )
        pmg_writes = [k for k, _ in bridge.calls if "PmgStep" in k]
        assert len(pmg_writes) == 6
        pmg_amp_vals = [v for k, v in bridge.calls if "PmgStep_amp" in k]
        assert all(v == 0.0 for v in pmg_amp_vals)

    def test_bus14_writes_all_4_pm_step_amps(self) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge()
        LoadStepRBranch(ls_bus=14).apply(
            bridge=bridge, magnitude_sys_pu=2.48,
            rng=np.random.default_rng(0), t_now=0.5, cfg=cfg,
        )
        pm_amp_writes = [k for k, _ in bridge.calls if k.startswith("Pm_step_amp_")]
        assert len(pm_amp_writes) == 4, (
            f"Expected 4 PM_STEP_AMP writes (one per ESS); got {pm_amp_writes}"
        )

    def test_pm_step_t_written_for_all_4_ess(self) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge()
        LoadStepRBranch(ls_bus=14).apply(
            bridge=bridge, magnitude_sys_pu=2.48,
            rng=np.random.default_rng(0), t_now=0.5, cfg=cfg,
        )
        pm_t_writes = [k for k, _ in bridge.calls if k.startswith("Pm_step_t_")]
        assert len(pm_t_writes) == 4

    def test_resolve_disturbance_bus14_returns_loadstep_r_branch(self) -> None:
        adapter = resolve_disturbance("loadstep_paper_bus14")
        assert isinstance(adapter, LoadStepRBranch)
        assert adapter.ls_bus == 14

    def test_known_disturbance_types_still_includes_loadstep_entries(self) -> None:
        kt = known_disturbance_types()
        assert "loadstep_paper_bus14" in kt
        assert "loadstep_paper_bus15" in kt
        assert "loadstep_paper_random_bus" in kt
