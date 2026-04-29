"""Unit tests for ``scenarios.kundur.workspace_vars``.

Typed schema for the Python ↔ MATLAB workspace-var contract on the Kundur
CVS profiles. No MATLAB engine is required — these tests are pure Python.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scenarios.kundur.workspace_vars import (
    PROFILE_CVS_V2,
    PROFILE_CVS_V3,
    IndexFamily,
    WorkspaceVarError,
    keys,
    resolve,
    spec_for,
)


# ---------------------------------------------------------------------------
# Resolve — known keys produce the documented MATLAB names.
# ---------------------------------------------------------------------------


class TestResolveKnownKeys:
    def test_per_agent_M_v3(self) -> None:
        assert resolve("M_PER_AGENT", profile=PROFILE_CVS_V3, i=1) == "M_1"
        assert resolve("M_PER_AGENT", profile=PROFILE_CVS_V3, i=4) == "M_4"

    def test_per_agent_D_v2(self) -> None:
        assert resolve("D_PER_AGENT", profile=PROFILE_CVS_V2, i=2) == "D_2"

    def test_per_agent_pm_step_v3(self) -> None:
        assert resolve("PM_STEP_T",   profile=PROFILE_CVS_V3, i=3) == "Pm_step_t_3"
        assert resolve("PM_STEP_AMP", profile=PROFILE_CVS_V3, i=4) == "Pm_step_amp_4"

    def test_per_sg_v3(self) -> None:
        assert resolve("PMG_STEP_T",   profile=PROFILE_CVS_V3, g=1) == "PmgStep_t_1"
        assert resolve("PMG_STEP_AMP", profile=PROFILE_CVS_V3, g=3) == "PmgStep_amp_3"

    def test_per_bus_v3_load_step(self) -> None:
        assert resolve("LOAD_STEP_AMP", profile=PROFILE_CVS_V3, bus=14) == "LoadStep_amp_bus14"
        assert resolve("LOAD_STEP_AMP", profile=PROFILE_CVS_V3, bus=15) == "LoadStep_amp_bus15"

    def test_per_bus_v3_load_step_trip(self) -> None:
        assert resolve("LOAD_STEP_TRIP_AMP", profile=PROFILE_CVS_V3, bus=14) == "LoadStep_trip_amp_bus14"
        assert resolve("LOAD_STEP_TRIP_AMP", profile=PROFILE_CVS_V3, bus=15) == "LoadStep_trip_amp_bus15"


# ---------------------------------------------------------------------------
# Profile guard — v3-only vars must reject v2 / unknown profiles.
# ---------------------------------------------------------------------------


class TestResolveProfileGuard:
    def test_pmg_step_rejected_for_v2(self) -> None:
        with pytest.raises(WorkspaceVarError, match="not declared for profile"):
            resolve("PMG_STEP_AMP", profile=PROFILE_CVS_V2, g=1)

    def test_load_step_rejected_for_v2(self) -> None:
        with pytest.raises(WorkspaceVarError, match="not declared for profile"):
            resolve("LOAD_STEP_AMP", profile=PROFILE_CVS_V2, bus=14)

    def test_load_step_trip_rejected_for_v2(self) -> None:
        with pytest.raises(WorkspaceVarError, match="not declared for profile"):
            resolve("LOAD_STEP_TRIP_AMP", profile=PROFILE_CVS_V2, bus=15)

    def test_load_step_rejected_for_unknown_profile(self) -> None:
        with pytest.raises(WorkspaceVarError, match="not declared for profile"):
            resolve("LOAD_STEP_AMP", profile="kundur_vsg", bus=14)


# ---------------------------------------------------------------------------
# Index bounds — out-of-range / missing / wrong-type indices must raise.
# ---------------------------------------------------------------------------


class TestResolveIndexBounds:
    def test_per_agent_lower_bound(self) -> None:
        with pytest.raises(WorkspaceVarError, match=r"i in \[1, 4\]"):
            resolve("M_PER_AGENT", profile=PROFILE_CVS_V3, i=0)

    def test_per_agent_upper_bound(self) -> None:
        with pytest.raises(WorkspaceVarError, match=r"i in \[1, 4\]"):
            resolve("M_PER_AGENT", profile=PROFILE_CVS_V3, i=5)

    def test_per_agent_custom_n_agents(self) -> None:
        # n_agents=8 (NE39-like) lifts the upper bound.
        assert resolve("M_PER_AGENT", profile=PROFILE_CVS_V3, n_agents=8, i=8) == "M_8"

    def test_per_sg_out_of_range_high(self) -> None:
        with pytest.raises(WorkspaceVarError, match="g in"):
            resolve("PMG_STEP_T", profile=PROFILE_CVS_V3, g=4)

    def test_per_sg_out_of_range_low(self) -> None:
        with pytest.raises(WorkspaceVarError, match="g in"):
            resolve("PMG_STEP_T", profile=PROFILE_CVS_V3, g=0)

    def test_per_bus_unknown_bus(self) -> None:
        with pytest.raises(WorkspaceVarError, match="bus in"):
            resolve("LOAD_STEP_AMP", profile=PROFILE_CVS_V3, bus=7)

    def test_per_agent_missing_index(self) -> None:
        with pytest.raises(WorkspaceVarError, match="i="):
            resolve("M_PER_AGENT", profile=PROFILE_CVS_V3)

    def test_per_agent_wrong_type(self) -> None:
        with pytest.raises(WorkspaceVarError, match="i="):
            resolve("M_PER_AGENT", profile=PROFILE_CVS_V3, i="1")

    def test_per_sg_missing_index(self) -> None:
        with pytest.raises(WorkspaceVarError, match="g="):
            resolve("PMG_STEP_AMP", profile=PROFILE_CVS_V3)

    def test_per_bus_missing_index(self) -> None:
        with pytest.raises(WorkspaceVarError, match="bus="):
            resolve("LOAD_STEP_AMP", profile=PROFILE_CVS_V3)


# ---------------------------------------------------------------------------
# Unknown keys.
# ---------------------------------------------------------------------------


class TestResolveUnknownKey:
    def test_unknown_key(self) -> None:
        with pytest.raises(WorkspaceVarError, match="Unknown workspace var key"):
            resolve("NOT_A_REAL_KEY", profile=PROFILE_CVS_V3)

    def test_spec_for_unknown_raises(self) -> None:
        with pytest.raises(WorkspaceVarError, match="Unknown"):
            spec_for("NOPE")


# ---------------------------------------------------------------------------
# Schema introspection.
# ---------------------------------------------------------------------------


class TestSchemaIntrospection:
    def test_keys_nonempty_and_complete(self) -> None:
        ks = set(keys())
        assert {
            "M_PER_AGENT", "D_PER_AGENT",
            "PM_STEP_T", "PM_STEP_AMP",
            "PMG_STEP_T", "PMG_STEP_AMP",
            "LOAD_STEP_AMP", "LOAD_STEP_TRIP_AMP",
        } <= ks

    def test_spec_for_per_agent(self) -> None:
        spec = spec_for("M_PER_AGENT")
        assert spec.family is IndexFamily.PER_AGENT
        assert PROFILE_CVS_V3 in spec.profiles
        assert PROFILE_CVS_V2 in spec.profiles

    def test_spec_for_per_sg_v3_only(self) -> None:
        spec = spec_for("PMG_STEP_AMP")
        assert spec.family is IndexFamily.PER_SG
        assert spec.profiles == frozenset({PROFILE_CVS_V3})


# ---------------------------------------------------------------------------
# Cross-check with the existing tests/fixtures/kundur_workspace_vars.json
# fixture (independently maintained against build_kundur_cvs_v3.m).
# If the schema and fixture disagree, one of them is wrong.
# ---------------------------------------------------------------------------


_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "kundur_workspace_vars.json"


@pytest.fixture(scope="module")
def kundur_fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


class TestFixtureCrossCheck:
    """The schema's resolved names for LIVE-verdict per-agent vars must
    appear as LIVE in the fixture."""

    def test_pm_step_amp_v3_per_agent_live(self, kundur_fixture) -> None:
        v3 = kundur_fixture["kundur_cvs_v3"]["expectations"]
        for i in range(1, 5):
            name = resolve("PM_STEP_AMP", profile=PROFILE_CVS_V3, i=i)
            assert name in v3, f"{name} missing from fixture"
            assert v3[name]["verdict"] == "LIVE"

    def test_pm_step_t_v3_per_agent_live(self, kundur_fixture) -> None:
        v3 = kundur_fixture["kundur_cvs_v3"]["expectations"]
        for i in range(1, 5):
            name = resolve("PM_STEP_T", profile=PROFILE_CVS_V3, i=i)
            assert name in v3, f"{name} missing from fixture"
            assert v3[name]["verdict"] == "LIVE"

    def test_M_D_v3_first_agent_live(self, kundur_fixture) -> None:
        v3 = kundur_fixture["kundur_cvs_v3"]["expectations"]
        # fixture only catalogs M_1 / D_1 — sufficient for the LIVE check.
        assert v3[resolve("M_PER_AGENT", profile=PROFILE_CVS_V3, i=1)]["verdict"] == "LIVE"
        assert v3[resolve("D_PER_AGENT", profile=PROFILE_CVS_V3, i=1)]["verdict"] == "LIVE"
