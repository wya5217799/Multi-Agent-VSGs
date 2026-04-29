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
    WorkspaceVarSpec,
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


# ===========================================================================
# C3c: effectiveness layer (name-valid vs physically-effective)
# ===========================================================================


# ---------------------------------------------------------------------------
# Field invariants on WorkspaceVarSpec.
# ---------------------------------------------------------------------------


class TestEffectivenessFieldInvariants:
    """Schema-wide invariants on the new effective_in_profile / inactive_reason
    fields (C3b/C3c)."""

    def test_effective_subset_of_profiles_for_all_keys(self) -> None:
        for k in keys():
            spec = spec_for(k)
            assert spec.effective_in_profile.issubset(spec.profiles), (
                f"{k}: effective_in_profile {sorted(spec.effective_in_profile)} "
                f"not subset of profiles {sorted(spec.profiles)}"
            )

    def test_inactive_reason_keys_are_name_valid_but_not_effective(self) -> None:
        for k in keys():
            spec = spec_for(k)
            allowed = spec.profiles - spec.effective_in_profile
            assert set(spec.inactive_reason).issubset(allowed), (
                f"{k}: inactive_reason has keys outside "
                f"profiles - effective_in_profile"
            )

    def test_post_init_rejects_effective_outside_profiles(self) -> None:
        # effective_in_profile contains a profile not in profiles → reject.
        with pytest.raises(ValueError, match="not in profiles"):
            WorkspaceVarSpec(
                template="X_{i}",
                family=IndexFamily.PER_AGENT,
                profiles=frozenset({"a"}),
                description="bad",
                effective_in_profile=frozenset({"a", "b"}),
            )

    def test_post_init_rejects_orphan_inactive_reason(self) -> None:
        # inactive_reason key is in effective_in_profile (not allowed —
        # only name-valid-but-not-effective profiles may carry a reason).
        with pytest.raises(ValueError, match="inactive_reason keys"):
            WorkspaceVarSpec(
                template="X_{i}",
                family=IndexFamily.PER_AGENT,
                profiles=frozenset({"a"}),
                description="bad",
                effective_in_profile=frozenset({"a"}),
                inactive_reason={"a": "bogus"},
            )

    def test_post_init_rejects_inactive_reason_for_unknown_profile(self) -> None:
        # inactive_reason key is not in profiles at all.
        with pytest.raises(ValueError, match="inactive_reason keys"):
            WorkspaceVarSpec(
                template="X_{i}",
                family=IndexFamily.PER_AGENT,
                profiles=frozenset({"a"}),
                description="bad",
                effective_in_profile=frozenset(),
                inactive_reason={"zzz": "ghost"},
            )

    def test_default_effective_equals_profiles(self) -> None:
        # When effective_in_profile is omitted at construction, it defaults
        # to profiles itself (back-compat, "assume effective until demoted").
        spec = WorkspaceVarSpec(
            template="X_{i}",
            family=IndexFamily.PER_AGENT,
            profiles=frozenset({"a", "b"}),
            description="default",
        )
        assert spec.effective_in_profile == frozenset({"a", "b"})


# ---------------------------------------------------------------------------
# Default behavior (require_effective=False) — C3a back-compat.
# ---------------------------------------------------------------------------


class TestRequireEffectiveDefaultUnchanged:
    """C3c MUST NOT change behavior when require_effective is omitted."""

    def test_load_step_amp_v3_default_returns_name(self) -> None:
        # No raise; name resolves verbatim — IC seeding path relies on this.
        assert resolve(
            "LOAD_STEP_AMP", profile=PROFILE_CVS_V3, bus=14
        ) == "LoadStep_amp_bus14"

    def test_load_step_trip_amp_v3_default_returns_name(self) -> None:
        assert resolve(
            "LOAD_STEP_TRIP_AMP", profile=PROFILE_CVS_V3, bus=15
        ) == "LoadStep_trip_amp_bus15"

    def test_explicit_false_is_explicit_default(self) -> None:
        # require_effective=False is identical to omitting it.
        assert resolve(
            "LOAD_STEP_AMP", profile=PROFILE_CVS_V3, bus=14,
            require_effective=False,
        ) == "LoadStep_amp_bus14"


# ---------------------------------------------------------------------------
# require_effective=True — must reject the name-valid-but-not-effective set
# in v3, must pass everything else.
# ---------------------------------------------------------------------------


class TestRequireEffectiveStrict:

    def test_load_step_amp_v3_rejected(self) -> None:
        with pytest.raises(WorkspaceVarError, match="not effective"):
            resolve(
                "LOAD_STEP_AMP", profile=PROFILE_CVS_V3, bus=14,
                require_effective=True,
            )

    def test_load_step_amp_v3_message_cites_compile_freeze(self) -> None:
        with pytest.raises(WorkspaceVarError) as exc:
            resolve(
                "LOAD_STEP_AMP", profile=PROFILE_CVS_V3, bus=14,
                require_effective=True,
            )
        msg = str(exc.value)
        assert "compile-frozen" in msg
        assert "NOTES.md" in msg

    def test_load_step_trip_amp_v3_rejected(self) -> None:
        with pytest.raises(WorkspaceVarError, match="not effective"):
            resolve(
                "LOAD_STEP_TRIP_AMP", profile=PROFILE_CVS_V3, bus=14,
                require_effective=True,
            )

    def test_load_step_trip_amp_v3_message_cites_weak_signal(self) -> None:
        with pytest.raises(WorkspaceVarError) as exc:
            resolve(
                "LOAD_STEP_TRIP_AMP", profile=PROFILE_CVS_V3, bus=15,
                require_effective=True,
            )
        msg = str(exc.value)
        assert "0.01 Hz" in msg
        assert "NOTES.md" in msg

    def test_message_mentions_escape_hatch(self) -> None:
        with pytest.raises(WorkspaceVarError) as exc:
            resolve(
                "LOAD_STEP_AMP", profile=PROFILE_CVS_V3, bus=14,
                require_effective=True,
            )
        assert "require_effective=False" in str(exc.value)

    def test_pm_step_amp_v3_passes(self) -> None:
        assert resolve(
            "PM_STEP_AMP", profile=PROFILE_CVS_V3, i=1,
            require_effective=True,
        ) == "Pm_step_amp_1"

    def test_pmg_step_amp_v3_passes(self) -> None:
        assert resolve(
            "PMG_STEP_AMP", profile=PROFILE_CVS_V3, g=2,
            require_effective=True,
        ) == "PmgStep_amp_2"

    def test_M_per_agent_v3_passes(self) -> None:
        assert resolve(
            "M_PER_AGENT", profile=PROFILE_CVS_V3, i=4,
            require_effective=True,
        ) == "M_4"

    def test_D_per_agent_v2_passes(self) -> None:
        # v2 effective set inherits default (== profiles), so v2 passes.
        assert resolve(
            "D_PER_AGENT", profile=PROFILE_CVS_V2, i=2,
            require_effective=True,
        ) == "D_2"


# ---------------------------------------------------------------------------
# Validation order — effectiveness must not swallow earlier checks.
# ---------------------------------------------------------------------------


class TestRequireEffectivePreservesOtherChecks:

    def test_unknown_key_still_raises_unknown_under_strict(self) -> None:
        with pytest.raises(WorkspaceVarError, match="Unknown workspace var key"):
            resolve("NOT_A_KEY", profile=PROFILE_CVS_V3, require_effective=True)

    def test_unknown_profile_raises_name_error_not_effective_error(self) -> None:
        # Profile not in spec.profiles → name-validity error wins; we never
        # reach the effectiveness check.
        with pytest.raises(WorkspaceVarError, match="not declared for profile"):
            resolve(
                "LOAD_STEP_AMP", profile="kundur_vsg", bus=14,
                require_effective=True,
            )

    def test_index_bounds_still_raise_under_strict_for_effective_var(self) -> None:
        # PM_STEP_AMP is effective, so we proceed past the strict gate and
        # then trip on the index bound.
        with pytest.raises(WorkspaceVarError, match=r"i in \[1, 4\]"):
            resolve(
                "PM_STEP_AMP", profile=PROFILE_CVS_V3, i=99,
                require_effective=True,
            )

    def test_strict_check_precedes_index_for_not_effective_var(self) -> None:
        # LOAD_STEP_AMP is not effective in v3. Even with a bogus bus value
        # we expect the not-effective error first (validation order:
        # name → effective → bounds).
        with pytest.raises(WorkspaceVarError, match="not effective"):
            resolve(
                "LOAD_STEP_AMP", profile=PROFILE_CVS_V3, bus=7,
                require_effective=True,
            )


# ---------------------------------------------------------------------------
# Introspection — schema readers can see effectiveness state.
# ---------------------------------------------------------------------------


class TestEffectivenessIntrospection:

    def test_load_step_amp_v3_marked_not_effective(self) -> None:
        spec = spec_for("LOAD_STEP_AMP")
        assert PROFILE_CVS_V3 in spec.profiles
        assert PROFILE_CVS_V3 not in spec.effective_in_profile
        assert PROFILE_CVS_V3 in spec.inactive_reason
        assert "compile-frozen" in spec.inactive_reason[PROFILE_CVS_V3]

    def test_load_step_trip_amp_v3_marked_not_effective(self) -> None:
        spec = spec_for("LOAD_STEP_TRIP_AMP")
        assert PROFILE_CVS_V3 in spec.profiles
        assert PROFILE_CVS_V3 not in spec.effective_in_profile
        assert "0.01 Hz" in spec.inactive_reason[PROFILE_CVS_V3]

    def test_pm_step_amp_effective_everywhere_name_valid(self) -> None:
        spec = spec_for("PM_STEP_AMP")
        assert spec.effective_in_profile == spec.profiles
        assert spec.inactive_reason == {}

    def test_pmg_step_amp_v3_effective(self) -> None:
        spec = spec_for("PMG_STEP_AMP")
        assert PROFILE_CVS_V3 in spec.effective_in_profile
        assert spec.inactive_reason == {}
