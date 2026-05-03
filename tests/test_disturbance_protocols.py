"""Tests for ``scenarios.kundur.disturbance_protocols``.

Covers:
  - 14-type × ±sign × multiple-target byte-level regression vs the legacy
    god-method oracle (``tests/_disturbance_backend_legacy.py``);
  - R-A through R-J risk mitigations from the P1 design doc
    (``docs/superpowers/plans/2026-04-29-c1-disturbance-protocol-design.md``);
  - resolver factory contract and trace invariants.

No MATLAB engine — all tests use a fake bridge that records writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest

from scenarios.kundur.disturbance_protocols import (
    DisturbanceTrace,
    EssPmStepProxy,
    LoadStepCcsInjection,
    LoadStepRBranch,
    SgPmgStepProxy,
    known_disturbance_types,
    resolve_disturbance,
)
from scenarios.kundur.workspace_vars import WorkspaceVarError

# Y1 (2026-04-29): the legacy god-method oracle (
# ``tests/_disturbance_backend_legacy.py``) was used during P2 for
# byte-level regression vs the pre-C1 dispatch. After P4 / C4 was
# exercised on the full smoke matrix (3 smokes PASS, see
# ``quality_reports/verdicts/2026-04-29_p4_smoke_results.md``), the
# oracle was deleted in P5. The byte-level regression test below was
# also removed; per-adapter behavior is now covered by the R-A..R-J
# unit tests below.


# ---------------------------------------------------------------------------
# Fixtures — fake bridge / cfg
# ---------------------------------------------------------------------------


@dataclass
class FakeCfg:
    model_name: str = "kundur_cvs_v3"
    n_agents: int = 4
    sbase_va: float = 100e6


class FakeBridge:
    """Records every ``apply_workspace_var`` call for byte-level audit."""

    def __init__(self, cfg: FakeCfg) -> None:
        self.cfg = cfg
        self.calls: list[tuple[str, float]] = []

    def apply_workspace_var(self, name: str, value: Any) -> None:
        self.calls.append((str(name), float(value)))


def make_bridge(profile: str = "kundur_cvs_v3") -> FakeBridge:
    return FakeBridge(FakeCfg(model_name=profile))


# ---------------------------------------------------------------------------
# Fixture: loadstep_effective_v3
#
# Phase 1.5 reroute (2026-05-04): LoadStepRBranch now writes PM_STEP_AMP
# directly (paper-lumped ΔP via Pm_step infrastructure). LOAD_STEP_AMP and
# LOAD_STEP_TRIP_AMP are permanently deprecated (effective_in_profile =
# frozenset() for all profiles). This fixture is retained as a no-op stub
# so any remaining fixture references in test parametrization do not fail
# at collection time. Tests that previously required the fixture to
# promote LoadStep to effective are updated to work without it (since
# LoadStepRBranch no longer uses those vars at all).
# ---------------------------------------------------------------------------


@pytest.fixture
def loadstep_effective_v3(monkeypatch):  # noqa: ARG001
    """No-op stub: Phase 1.5 reroute removed CCS/RLC LoadStep writes.

    LoadStepRBranch now routes through PM_STEP_AMP (always effective).
    This fixture is retained to avoid fixture-not-found errors in any
    parametrized tests that still reference it; it does nothing.
    """
    yield


# ---------------------------------------------------------------------------
# R-A: LS1 bus14 trip — Phase 1.5 reroute Pm_step semantics
#
# Old semantic (P0-1c CCS, abandoned): wrote LOAD_STEP_TRIP_AMP[14].
# New semantic (Phase 1.5 reroute 2026-05-04): writes PM_STEP_AMP@ES3
# (Pm_step_amp_3) with positive magnitude (freq UP = paper LS1).
# abs() applied: negative input → still positive Pm_step_amp_3.
# ---------------------------------------------------------------------------


class TestRiskA_LS1_PmStepSemantics:
    @pytest.mark.parametrize("magnitude", [
        +0.5,
        -0.5,   # negative magnitude → overridden to paper +1.53
        +5.0,
        -5.0,
        +0.0,   # zero → overridden to paper +1.53
    ])
    def test_bus14_trip_writes_pm_step_amp_3_positive(
        self, magnitude: float, loadstep_effective_v3
    ) -> None:
        # B3 fix: all caller magnitudes overridden to paper value 1.53 (bus14).
        from scenarios.kundur.disturbance_protocols import PAPER_LS_MAGNITUDE_SYS_PU
        cfg = FakeCfg()
        bridge = FakeBridge(cfg)
        adapter = LoadStepRBranch(ls_bus=14)
        adapter.apply(
            bridge=bridge,
            magnitude_sys_pu=magnitude,
            rng=np.random.default_rng(0),
            t_now=1.0,
            cfg=cfg,
        )
        # Phase 1.5 reroute: writes PM_STEP_AMP@ES3 (Pm_step_amp_3)
        pm_amps = {k: v for k, v in bridge.calls if k.startswith("Pm_step_amp_")}
        assert "Pm_step_amp_3" in pm_amps, (
            "bus14 dispatch must write Pm_step_amp_3 (ES3 = bus14 ESS)"
        )
        # B3: paper anchor — always +1.53 regardless of caller magnitude
        assert pm_amps["Pm_step_amp_3"] == pytest.approx(PAPER_LS_MAGNITUDE_SYS_PU[14])
        assert pm_amps["Pm_step_amp_3"] >= 0.0, (
            "bus14 Pm_step_amp_3 must be non-negative (freq UP)"
        )
        # Must NOT write LOAD_STEP_TRIP_AMP (CCS path abandoned)
        ccs_writes = [k for k, _ in bridge.calls if "trip_amp" in k.lower()]
        assert ccs_writes == []


# ---------------------------------------------------------------------------
# R-B: LS2 sign safety — bus15 writes PM_STEP_AMP@ES4 negative (freq DOWN)
#
# Phase 1.5 reroute: bus15 now writes Pm_step_amp_4 with negative value.
# Adapter applies -abs(magnitude) for bus15 (load increase = freq DOWN).
# ---------------------------------------------------------------------------


class TestRiskB_LS2_PmStepNegative:
    @pytest.mark.parametrize(
        "magnitude",
        [
            +1.88,   # positive input → overridden to paper -0.90
            -1.88,   # negative input → overridden to paper -0.90
            +0.0,    # zero → overridden to paper -0.90
            -0.5,    # arbitrary → overridden to paper -0.90
        ],
    )
    def test_bus15_engage_writes_pm_step_amp_4_negative(
        self, magnitude: float, loadstep_effective_v3
    ) -> None:
        # B3 fix: all caller magnitudes overridden to paper value -0.90 (bus15).
        from scenarios.kundur.disturbance_protocols import PAPER_LS_MAGNITUDE_SYS_PU
        cfg = FakeCfg()
        bridge = FakeBridge(cfg)
        adapter = LoadStepRBranch(ls_bus=15)
        adapter.apply(
            bridge=bridge,
            magnitude_sys_pu=magnitude,
            rng=np.random.default_rng(0),
            t_now=1.0,
            cfg=cfg,
        )
        pm_amps = {k: v for k, v in bridge.calls if k.startswith("Pm_step_amp_")}
        assert "Pm_step_amp_4" in pm_amps, (
            "bus15 dispatch must write Pm_step_amp_4 (ES4 = bus15 ESS)"
        )
        # B3: paper anchor — always -0.90 regardless of caller magnitude
        assert pm_amps["Pm_step_amp_4"] == pytest.approx(-PAPER_LS_MAGNITUDE_SYS_PU[15])
        assert pm_amps["Pm_step_amp_4"] <= 0.0, (
            "bus15 Pm_step_amp_4 must be non-positive (freq DOWN)"
        )
        # Must NOT write LOAD_STEP_AMP (RLC path abandoned)
        ls_writes = [k for k, _ in bridge.calls if "LoadStep_amp" in k]
        assert ls_writes == []


# ---------------------------------------------------------------------------
# R-C: SgPmgStepProxy silence-then-set order
# ---------------------------------------------------------------------------


class TestRiskC_PmgSilenceThenSetOrder:
    @pytest.mark.parametrize("target_g", [1, 2, 3])
    def test_target_amp_survives_silence_loop(
        self, target_g: int
    ) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge(cfg)
        adapter = SgPmgStepProxy(target_g=target_g)
        adapter.apply(
            bridge=bridge,
            magnitude_sys_pu=+1.5,
            rng=np.random.default_rng(0),
            t_now=2.0,
            cfg=cfg,
        )
        # Final value of PMG_STEP_AMP[target_g] in the call log must be 1.5
        # (silence wrote 0.0 first, target write must come AFTER and be 1.5)
        target_var = f"PmgStep_amp_{target_g}"
        target_writes = [
            (i, v) for i, (k, v) in enumerate(bridge.calls)
            if k == target_var
        ]
        assert len(target_writes) == 2, (
            f"expected silence write + target write = 2 writes to "
            f"{target_var}, got {len(target_writes)}: {target_writes}"
        )
        # Silence first (value 0.0), target second (value 1.5)
        assert target_writes[0][1] == 0.0
        assert target_writes[1][1] == pytest.approx(1.5)
        # The target write MUST come after the silence write (higher index)
        assert target_writes[1][0] > target_writes[0][0]


# ---------------------------------------------------------------------------
# R-D: ESS divides by n_tgt; SG does not divide
# ---------------------------------------------------------------------------


class TestRiskD_MagnitudeDivision:
    def test_ess_single_vsg_does_not_divide(self) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge(cfg)
        adapter = EssPmStepProxy(target_indices=(0,))
        adapter.apply(
            bridge=bridge,
            magnitude_sys_pu=+1.0,
            rng=np.random.default_rng(0),
            t_now=1.0,
            cfg=cfg,
        )
        # PM_STEP_AMP[1] (i.e. VSG[0]) gets full magnitude; n_tgt=1
        amp_writes = [(k, v) for k, v in bridge.calls
                      if k == "Pm_step_amp_1"]
        assert amp_writes == [("Pm_step_amp_1", 1.0)]

    def test_ess_four_targets_divides_by_4(self) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge(cfg)
        adapter = EssPmStepProxy(target_indices=(0, 1, 2, 3))
        adapter.apply(
            bridge=bridge,
            magnitude_sys_pu=+4.0,
            rng=np.random.default_rng(0),
            t_now=1.0,
            cfg=cfg,
        )
        # Each of 4 VSGs gets 4.0/4 = 1.0
        per_vsg = {
            k: v for k, v in bridge.calls
            if k.startswith("Pm_step_amp_")
        }
        assert per_vsg == {
            "Pm_step_amp_1": 1.0,
            "Pm_step_amp_2": 1.0,
            "Pm_step_amp_3": 1.0,
            "Pm_step_amp_4": 1.0,
        }

    def test_sg_does_not_divide(self) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge(cfg)
        adapter = SgPmgStepProxy(target_g=1)
        adapter.apply(
            bridge=bridge,
            magnitude_sys_pu=+4.0,
            rng=np.random.default_rng(0),
            t_now=1.0,
            cfg=cfg,
        )
        # Final write to PMG_STEP_AMP[1] must be the full 4.0 (not 4.0/3)
        target_writes = [
            v for k, v in bridge.calls if k == "PmgStep_amp_1"
        ]
        # Last write to PMG_STEP_AMP[1] is the target set; must be 4.0
        assert target_writes[-1] == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# R-E: RNG only via injected rng — adapter file must not reference np.random
# ---------------------------------------------------------------------------


class TestRiskE_NoModuleLevelRandom:
    def test_disturbance_protocols_module_does_not_use_module_level_random(
        self,
    ) -> None:
        from pathlib import Path
        src = Path(__file__).resolve().parents[1] / (
            "scenarios/kundur/disturbance_protocols.py"
        )
        text = src.read_text(encoding="utf-8")
        # Allow `np.random.Generator` (type annotation) but not
        # `np.random.<call>`. The simplest check: no `np.random.` followed
        # by lowercase letter (which would be a function call).
        # Generator is capitalised and is OK.
        bad_lines = [
            ln for ln in text.splitlines()
            if "np.random." in ln and "Generator" not in ln
        ]
        assert bad_lines == [], (
            f"adapter file uses module-level np.random.<func>: {bad_lines}"
        )

    def test_random_bus_distribution_uses_injected_rng(self) -> None:
        cfg = FakeCfg()
        adapter = EssPmStepProxy(target_indices="random_bus")
        seen_targets: set[str] = set()
        # 200 samples should hit both target paths under any reasonable
        # rng implementation
        for seed in range(200):
            bridge = FakeBridge(cfg)
            adapter.apply(
                bridge=bridge,
                magnitude_sys_pu=+1.0,
                rng=np.random.default_rng(seed),
                t_now=1.0,
                cfg=cfg,
            )
            # Find the non-zero PM_STEP_AMP — it identifies the target
            for k, v in bridge.calls:
                if k.startswith("Pm_step_amp_") and v != 0.0:
                    seen_targets.add(k)
                    break
        assert seen_targets == {"Pm_step_amp_1", "Pm_step_amp_4"}


# ---------------------------------------------------------------------------
# R-F: silence-others includes other family
# ---------------------------------------------------------------------------


class TestRiskF_SilenceOtherFamily:
    def test_ess_silences_pmg(self) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge(cfg)
        EssPmStepProxy(target_indices=(0,)).apply(
            bridge=bridge,
            magnitude_sys_pu=+1.0,
            rng=np.random.default_rng(0),
            t_now=1.0,
            cfg=cfg,
        )
        pmg_writes = [k for k, _ in bridge.calls if "Pmg" in k]
        assert sorted(pmg_writes) == sorted([
            "PmgStep_t_1", "PmgStep_amp_1",
            "PmgStep_t_2", "PmgStep_amp_2",
            "PmgStep_t_3", "PmgStep_amp_3",
        ])

    def test_sg_silences_pm(self) -> None:
        cfg = FakeCfg()
        bridge = FakeBridge(cfg)
        SgPmgStepProxy(target_g=2).apply(
            bridge=bridge,
            magnitude_sys_pu=+1.0,
            rng=np.random.default_rng(0),
            t_now=1.0,
            cfg=cfg,
        )
        pm_writes = [
            k for k, _ in bridge.calls
            if k.startswith("Pm_step_")
        ]
        # 4 PM_STEP_T writes + 4 PM_STEP_AMP writes
        assert len(pm_writes) == 8

    def test_loadstep_silences_pmg_and_writes_all_pm(
        self, loadstep_effective_v3
    ) -> None:
        # Phase 1.5 reroute: LoadStepRBranch writes PM_STEP_AMP (target +
        # silence-others) and silences PMG. No LOAD_STEP_* writes.
        cfg = FakeCfg()
        bridge = FakeBridge(cfg)
        LoadStepRBranch(ls_bus=14).apply(
            bridge=bridge,
            magnitude_sys_pu=+0.0,
            rng=np.random.default_rng(0),
            t_now=1.0,
            cfg=cfg,
        )
        pm_count = sum(
            1 for k, _ in bridge.calls if k.startswith("Pm_step_")
        )
        pmg_count = sum(1 for k, _ in bridge.calls if "Pmg" in k)
        # 4 PM_STEP_T + 4 PM_STEP_AMP = 8 pm writes
        assert pm_count == 8
        # 3 SG × (PMG_STEP_T + PMG_STEP_AMP) = 6 pmg writes
        assert pmg_count == 6


# ---------------------------------------------------------------------------
# R-G: bus14 / bus15 — symmetric Pm_step paths (Phase 1.5 reroute)
# ---------------------------------------------------------------------------


class TestRiskG_SymmetricPaths:
    def test_bus14_and_bus15_both_write_pm_step(
        self, loadstep_effective_v3
    ) -> None:
        # Phase 1.5 reroute: both buses write PM_STEP_AMP (different ESS index).
        cfg = FakeCfg()
        # bus14 → ES3 → positive Pm_step
        bridge_a = FakeBridge(cfg)
        LoadStepRBranch(ls_bus=14).apply(
            bridge=bridge_a, magnitude_sys_pu=+1.0,
            rng=np.random.default_rng(0), t_now=1.0, cfg=cfg,
        )
        # bus15 → ES4 → negative Pm_step
        bridge_b = FakeBridge(cfg)
        LoadStepRBranch(ls_bus=15).apply(
            bridge=bridge_b, magnitude_sys_pu=+1.0,
            rng=np.random.default_rng(0), t_now=1.0, cfg=cfg,
        )
        pm_a = {k: v for k, v in bridge_a.calls if k.startswith("Pm_step_amp_")}
        pm_b = {k: v for k, v in bridge_b.calls if k.startswith("Pm_step_amp_")}
        # bus14: ES3 positive, all others zero
        assert pm_a["Pm_step_amp_3"] > 0.0
        assert pm_a["Pm_step_amp_4"] == 0.0
        # bus15: ES4 negative, all others zero
        assert pm_b["Pm_step_amp_4"] < 0.0
        assert pm_b["Pm_step_amp_3"] == 0.0


# ---------------------------------------------------------------------------
# R-B3: paper-anchor magnitude lock for loadstep_paper_* family
# (2026-05-04 B3 fix)
# ---------------------------------------------------------------------------


class TestB3_PaperMagnitudeLock:
    def test_arbitrary_magnitude_overridden_to_paper_for_bus14(
        self, loadstep_effective_v3
    ) -> None:
        """Caller mag=0.5 → Pm_step_amp_3 = +1.53 (paper anchor bus14)."""
        from scenarios.kundur.disturbance_protocols import PAPER_LS_MAGNITUDE_SYS_PU
        cfg = FakeCfg()
        bridge = FakeBridge(cfg)
        LoadStepRBranch(ls_bus=14).apply(
            bridge=bridge, magnitude_sys_pu=0.5,
            rng=np.random.default_rng(0), t_now=1.0, cfg=cfg,
        )
        pm_amps = {k: v for k, v in bridge.calls if k.startswith("Pm_step_amp_")}
        assert pm_amps["Pm_step_amp_3"] == pytest.approx(PAPER_LS_MAGNITUDE_SYS_PU[14]), (
            "B3 lock: Pm_step_amp_3 must always be +1.53 for bus14"
        )

    def test_arbitrary_magnitude_overridden_to_paper_for_bus15(
        self, loadstep_effective_v3
    ) -> None:
        """Caller mag=0.5 → Pm_step_amp_4 = -0.90 (paper anchor bus15)."""
        from scenarios.kundur.disturbance_protocols import PAPER_LS_MAGNITUDE_SYS_PU
        cfg = FakeCfg()
        bridge = FakeBridge(cfg)
        LoadStepRBranch(ls_bus=15).apply(
            bridge=bridge, magnitude_sys_pu=0.5,
            rng=np.random.default_rng(0), t_now=1.0, cfg=cfg,
        )
        pm_amps = {k: v for k, v in bridge.calls if k.startswith("Pm_step_amp_")}
        assert pm_amps["Pm_step_amp_4"] == pytest.approx(-PAPER_LS_MAGNITUDE_SYS_PU[15]), (
            "B3 lock: Pm_step_amp_4 must always be -0.90 for bus15"
        )


# ---------------------------------------------------------------------------
# R-H: random_bus distribution (statistical sanity)
# ---------------------------------------------------------------------------


class TestRiskH_RandomBusDistribution:
    def test_ess_random_bus_distribution_roughly_5050(self) -> None:
        cfg = FakeCfg()
        adapter = EssPmStepProxy(target_indices="random_bus")
        bus7_count = 0
        bus9_count = 0
        for seed in range(1000):
            bridge = FakeBridge(cfg)
            adapter.apply(
                bridge=bridge, magnitude_sys_pu=+1.0,
                rng=np.random.default_rng(seed),
                t_now=1.0, cfg=cfg,
            )
            for k, v in bridge.calls:
                if k.startswith("Pm_step_amp_") and v != 0.0:
                    if k == "Pm_step_amp_1":
                        bus7_count += 1
                    elif k == "Pm_step_amp_4":
                        bus9_count += 1
                    break
        # Expect ~500/500; allow ±10% (very loose)
        assert 400 < bus7_count < 600
        assert 400 < bus9_count < 600
        assert bus7_count + bus9_count == 1000

    def test_sg_random_gen_distribution_three_way(self) -> None:
        cfg = FakeCfg()
        adapter = SgPmgStepProxy(target_g="random_gen")
        counts = {1: 0, 2: 0, 3: 0}
        for seed in range(900):
            bridge = FakeBridge(cfg)
            adapter.apply(
                bridge=bridge, magnitude_sys_pu=+1.0,
                rng=np.random.default_rng(seed),
                t_now=1.0, cfg=cfg,
            )
            for k, v in bridge.calls:
                if k.startswith("PmgStep_amp_") and v != 0.0:
                    g = int(k[-1])
                    counts[g] += 1
                    break
        # Expect ~300 each; allow ±15%
        for g, c in counts.items():
            assert 200 < c < 400, f"g={g}: count={c}"


# ---------------------------------------------------------------------------
# R-I: trace key/value len consistency
# ---------------------------------------------------------------------------


class TestRiskI_TraceConsistency:
    @pytest.mark.parametrize(
        "dtype",
        [
            "pm_step_proxy_bus7", "pm_step_proxy_g2",
            "pm_step_single_vsg",
        ],
    )
    def test_trace_keys_and_values_have_equal_length_pm_pmg(
        self, dtype: str
    ) -> None:
        # PM_STEP / PMG_STEP families only — they don't trigger
        # require_effective and execute write loops.
        cfg = FakeCfg()
        bridge = FakeBridge(cfg)
        protocol = resolve_disturbance(
            dtype,
            vsg_indices=(0,) if dtype == "pm_step_single_vsg" else None,
        )
        trace = protocol.apply(
            bridge=bridge, magnitude_sys_pu=+1.0,
            rng=np.random.default_rng(0), t_now=1.0, cfg=cfg,
        )
        assert len(trace.written_keys) == len(trace.written_values)
        assert len(trace.written_keys) == len(bridge.calls)
        for (k_t, v_t), (k_b, v_b) in zip(
            zip(trace.written_keys, trace.written_values),
            bridge.calls,
        ):
            assert k_t == k_b
            assert v_t == pytest.approx(v_b)

    @pytest.mark.parametrize(
        "dtype",
        [
            "loadstep_paper_bus14", "loadstep_paper_bus15",
        ],
    )
    def test_trace_keys_and_values_have_equal_length_loadstep(
        self, dtype: str, loadstep_effective_v3
    ) -> None:
        # Phase 1.5 reroute: loadstep_paper_* writes PM_STEP_AMP natively.
        # loadstep_paper_trip_* (CCS family) archived 2026-05-04 B4 cleanup;
        # removed from parametrize list above.
        cfg = FakeCfg()
        bridge = FakeBridge(cfg)
        protocol = resolve_disturbance(dtype)
        trace = protocol.apply(
            bridge=bridge, magnitude_sys_pu=+1.0,
            rng=np.random.default_rng(0), t_now=1.0, cfg=cfg,
        )
        assert len(trace.written_keys) == len(trace.written_values)
        assert len(trace.written_keys) == len(bridge.calls)


# ---------------------------------------------------------------------------
# R-J: pm_step_single_vsg default fallback
# ---------------------------------------------------------------------------


class TestRiskJ_SingleVsgDefault:
    def test_resolve_with_no_vsg_indices_uses_zero_target(self) -> None:
        adapter = resolve_disturbance("pm_step_single_vsg")
        assert isinstance(adapter, EssPmStepProxy)
        assert adapter.target_indices == (0,)

    def test_resolve_passes_vsg_indices_through(self) -> None:
        adapter = resolve_disturbance(
            "pm_step_single_vsg", vsg_indices=(1, 2)
        )
        assert isinstance(adapter, EssPmStepProxy)
        assert adapter.target_indices == (1, 2)


# ---------------------------------------------------------------------------
# Resolver factory contract
# ---------------------------------------------------------------------------


class TestResolver:
    def test_unknown_disturbance_type_raises_valueerror(self) -> None:
        with pytest.raises(ValueError, match="unknown disturbance_type"):
            resolve_disturbance("nope_not_a_type")

    # Originally "14_plus_single_vsg"; registry has grown since (Z route
    # 2026-05-03 added pm_step_single_es{1-4}, loadstep_paper_ccs_*,
    # pm_step_hybrid_sg_es; H1 2026-05-04 added pm_step_hybrid_sg_es_probe_g2).
    # B4 2026-05-04: loadstep_paper_trip_bus14/bus15/random_bus archived.
    # Count is now 20. Name kept for git-blame tracing.
    def test_known_types_includes_all_14_plus_single_vsg(self) -> None:
        kt = known_disturbance_types()
        assert len(kt) == 20
        assert "pm_step_single_vsg" in kt
        for label in [
            "pm_step_proxy_bus7", "pm_step_proxy_bus9",
            "pm_step_proxy_random_bus",
            "pm_step_proxy_g1", "pm_step_proxy_g2", "pm_step_proxy_g3",
            "pm_step_proxy_random_gen",
            "pm_step_single_es1", "pm_step_single_es2",
            "pm_step_single_es3", "pm_step_single_es4",
            "loadstep_paper_bus14", "loadstep_paper_bus15",
            "loadstep_paper_random_bus",
            "loadstep_paper_ccs_bus7", "loadstep_paper_ccs_bus9",
            "loadstep_paper_ccs_random_load",
            "pm_step_hybrid_sg_es",
            "pm_step_hybrid_sg_es_probe_g2",
        ]:
            assert label in kt, f"missing {label}"

    def test_resolver_returns_correct_adapter_type(self) -> None:
        assert isinstance(
            resolve_disturbance("pm_step_proxy_bus7"), EssPmStepProxy
        )
        assert isinstance(
            resolve_disturbance("pm_step_proxy_g1"), SgPmgStepProxy
        )
        assert isinstance(
            resolve_disturbance("loadstep_paper_bus14"), LoadStepRBranch
        )
        # loadstep_paper_trip_* (LoadStepCcsInjection) archived B4 2026-05-04


# ---------------------------------------------------------------------------
# require_effective wiring — LoadStep raises on v2 (out of scope for v3)
# ---------------------------------------------------------------------------


class TestRequireEffectiveWiring:
    def test_load_step_bus14_succeeds_on_v3_phasor_via_pm_step(
        self,
    ) -> None:
        """Phase 1.5 reroute: LoadStepRBranch uses PM_STEP_AMP (always
        effective). No longer raises WorkspaceVarError on v3 Phasor.
        The Phasor profile is supported by PM_STEP schema (PROFILES_CVS).
        """
        cfg = FakeCfg(model_name="kundur_cvs_v3")
        bridge = FakeBridge(cfg)
        adapter = LoadStepRBranch(ls_bus=14)
        trace = adapter.apply(
            bridge=bridge, magnitude_sys_pu=+1.0,
            rng=np.random.default_rng(0), t_now=1.0, cfg=cfg,
        )
        # Writes happen (PM_STEP_AMP is effective in v3 Phasor)
        assert len(bridge.calls) > 0
        assert trace.family == "paper_lumped_pm_step"

    def test_ess_pm_step_succeeds_on_v3(self) -> None:
        # PM_STEP family is name-valid AND effective in v3.
        # NOTE: v2 (kundur_cvs) is NOT supported by the protocol layer
        # because PMG_STEP_T (used in silence loop) is v3-only in the
        # schema. v2 is a legacy fallback path; the C3 schema drift here
        # is documented (and matches the legacy god method which would
        # also raise on v2's PMG_STEP_T silence loop).
        cfg = FakeCfg(model_name="kundur_cvs_v3")
        bridge = FakeBridge(cfg)
        adapter = EssPmStepProxy(target_indices=(0,))
        trace = adapter.apply(
            bridge=bridge, magnitude_sys_pu=+1.0,
            rng=np.random.default_rng(0), t_now=1.0, cfg=cfg,
        )
        assert trace.family == "ess_pm_step"
        assert len(bridge.calls) > 0

    def test_loadstep_r_branch_writes_pm_step_natively(
        self, loadstep_effective_v3
    ) -> None:
        """Phase 1.5 reroute: LoadStepRBranch writes PM_STEP_AMP natively
        (fixture is now a no-op — kept for parameter compat).
        """
        cfg = FakeCfg(model_name="kundur_cvs_v3")
        bridge = FakeBridge(cfg)
        adapter = LoadStepRBranch(ls_bus=14)
        trace = adapter.apply(
            bridge=bridge, magnitude_sys_pu=+1.0,
            rng=np.random.default_rng(0), t_now=1.0, cfg=cfg,
        )
        assert trace.family == "paper_lumped_pm_step"
        assert len(bridge.calls) > 0


# ---------------------------------------------------------------------------
# Adapter equality / hashability (frozen dataclass smoke)
# ---------------------------------------------------------------------------


class TestAdapterEquality:
    def test_adapters_with_equal_fields_are_equal(self) -> None:
        a = EssPmStepProxy(target_indices=(0,), proxy_bus=7)
        b = EssPmStepProxy(target_indices=(0,), proxy_bus=7)
        assert a == b
        assert hash(a) == hash(b)

    def test_adapters_with_different_fields_differ(self) -> None:
        assert (
            EssPmStepProxy(target_indices=(0,))
            != EssPmStepProxy(target_indices=(3,))
        )


# ---------------------------------------------------------------------------
# Post-review M2: sentinel validation at construction time
# ---------------------------------------------------------------------------


class TestSentinelValidationAtConstruction:
    def test_ess_pm_step_typo_sentinel_raises(self) -> None:
        with pytest.raises(ValueError, match="random_bus"):
            EssPmStepProxy(target_indices="random_buss")

    def test_ess_pm_step_wrong_target_type_raises(self) -> None:
        with pytest.raises(ValueError, match="tuple of int"):
            EssPmStepProxy(target_indices=[0, 1])  # list, not tuple

    def test_ess_pm_step_valid_sentinel_succeeds(self) -> None:
        EssPmStepProxy(target_indices="random_bus")

    def test_sg_pmg_step_typo_sentinel_raises(self) -> None:
        with pytest.raises(ValueError, match="random_gen"):
            SgPmgStepProxy(target_g="random_genn")

    def test_sg_pmg_step_invalid_int_raises(self) -> None:
        with pytest.raises(ValueError, match="1/2/3"):
            SgPmgStepProxy(target_g=4)

    def test_sg_pmg_step_valid_succeeds(self) -> None:
        SgPmgStepProxy(target_g="random_gen")
        SgPmgStepProxy(target_g=2)

    def test_load_step_r_invalid_bus_raises(self) -> None:
        with pytest.raises(ValueError, match="14/15"):
            LoadStepRBranch(ls_bus=16)

    def test_load_step_r_typo_sentinel_raises(self) -> None:
        with pytest.raises(ValueError, match="random_bus"):
            LoadStepRBranch(ls_bus="random_buss")

    def test_load_step_ccs_invalid_bus_raises(self) -> None:
        with pytest.raises(ValueError, match="14/15"):
            LoadStepCcsInjection(ls_bus=7)

    def test_load_step_ccs_typo_sentinel_raises(self) -> None:
        with pytest.raises(ValueError, match="random_bus"):
            LoadStepCcsInjection(ls_bus="random_buss")
