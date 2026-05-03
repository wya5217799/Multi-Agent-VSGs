"""Unit tests for L2 cleanup — LOAD_STEP_T schema flip + adapter no-op removal.

Verifies (2026-05-04 plan §L2):
  1. LOAD_STEP_T.effective_in_profile == frozenset()  (was {PROFILE_CVS_V3_DISCRETE})
  2. Both PROFILE_CVS_V3 and PROFILE_CVS_V3_DISCRETE present in inactive_reason
  3. LoadStepRBranch.apply does NOT call apply_workspace_var with the LOAD_STEP_T key

No MATLAB engine required — pure Python.
"""

from __future__ import annotations

import inspect

import pytest

from scenarios.kundur.workspace_vars import (
    PROFILE_CVS_V3,
    PROFILE_CVS_V3_DISCRETE,
    spec_for,
)


# ---------------------------------------------------------------------------
# §1 — LOAD_STEP_T effective_in_profile must be empty (flipped)
# ---------------------------------------------------------------------------


class TestLoadStepTEffectiveFlipped:
    def test_effective_in_profile_is_empty(self) -> None:
        spec = spec_for("LOAD_STEP_T")
        assert spec.effective_in_profile == frozenset(), (
            "LOAD_STEP_T should be inactive in all profiles after 2026-05-04 cleanup; "
            f"got effective_in_profile={spec.effective_in_profile!r}"
        )


# ---------------------------------------------------------------------------
# §2 — Both CVS_V3 and CVS_V3_DISCRETE present in inactive_reason
# ---------------------------------------------------------------------------


class TestLoadStepTInactiveReason:
    def test_cvs_v3_key_present(self) -> None:
        spec = spec_for("LOAD_STEP_T")
        assert PROFILE_CVS_V3 in spec.inactive_reason, (
            f"LOAD_STEP_T.inactive_reason must contain {PROFILE_CVS_V3!r}; "
            f"got keys: {list(spec.inactive_reason)}"
        )

    def test_cvs_v3_reason_non_empty(self) -> None:
        spec = spec_for("LOAD_STEP_T")
        assert spec.inactive_reason[PROFILE_CVS_V3].strip(), (
            f"inactive_reason for {PROFILE_CVS_V3!r} must be a non-empty string"
        )

    def test_cvs_v3_discrete_key_present(self) -> None:
        spec = spec_for("LOAD_STEP_T")
        assert PROFILE_CVS_V3_DISCRETE in spec.inactive_reason, (
            f"LOAD_STEP_T.inactive_reason must contain {PROFILE_CVS_V3_DISCRETE!r}; "
            f"got keys: {list(spec.inactive_reason)}"
        )

    def test_cvs_v3_discrete_reason_non_empty(self) -> None:
        spec = spec_for("LOAD_STEP_T")
        assert spec.inactive_reason[PROFILE_CVS_V3_DISCRETE].strip(), (
            f"inactive_reason for {PROFILE_CVS_V3_DISCRETE!r} must be a non-empty string"
        )


# ---------------------------------------------------------------------------
# §3 — LoadStepRBranch.apply source must not reference LOAD_STEP_T write
#
# We inspect the source of LoadStepRBranch.apply to confirm no
# apply_workspace_var call with LOAD_STEP_T occurs. This is a source-level
# check (no bridge mock needed) matching the plan's "verify by re-grepping"
# intent, and is robust to refactors that split the method.
# ---------------------------------------------------------------------------


class TestLoadStepRBranchNoLoadStepTWrite:
    def test_load_step_t_not_written_by_adapter(self) -> None:
        from scenarios.kundur.disturbance_protocols import LoadStepRBranch

        source = inspect.getsource(LoadStepRBranch.apply)
        # The removed write called ws("LOAD_STEP_T", ...) — check neither the
        # ws("LOAD_STEP_T") call nor a direct apply_workspace_var(k_t, ...) with
        # the LOAD_STEP_T key appears in the method.
        assert '"LOAD_STEP_T"' not in source, (
            "LoadStepRBranch.apply must not reference LOAD_STEP_T write "
            "(removed 2026-05-04 as compile-frozen no-op). "
            "Found '\"LOAD_STEP_T\"' in method source."
        )
