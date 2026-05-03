"""Unit tests for engine.path_guard — P2-cleanup-pathguard.

Verifies (2026-05-04 plan §P2-pathguard):
  1. PASS in correct worktree (top-level dir matches)
  2. PASS in nested correct worktree (parent walk finds the match)
  3. FAIL in wrong worktree (double-space main worktree)
  4. FAIL in unrelated dir
  5. Env override MAVSGS_DISABLE_WORKTREE_ASSERT=1 bypasses the assert
  6. Custom expected_basename works
  7. --help short-circuit (structural: guard fires after parse_args)

No MATLAB engine required — pure Python.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from engine.path_guard import (
    ENV_OVERRIDE,
    EXPECTED_WORKTREE_BASENAME,
    WrongWorktreeError,
    assert_active_worktree,
)


# ---------------------------------------------------------------------------
# §1 — PASS in correct worktree (exact basename match)
# ---------------------------------------------------------------------------


class TestCorrectWorktree:
    def test_pass_when_cwd_is_exact_basename(self) -> None:
        """assert_active_worktree must not raise when cwd IS the worktree root."""
        assert_active_worktree(cwd=Path("/tmp/Multi-Agent-VSGs-discrete"))

    def test_pass_when_cwd_is_nested_under_correct_worktree(self) -> None:
        """Parent-walk must find the worktree root even from a nested dir."""
        assert_active_worktree(cwd=Path("/tmp/Multi-Agent-VSGs-discrete/foo/bar"))

    def test_pass_when_correct_basename_in_middle_of_path(self) -> None:
        """Intermediate path component that matches should also pass."""
        assert_active_worktree(
            cwd=Path("/home/user/Multi-Agent-VSGs-discrete/scenarios/kundur")
        )


# ---------------------------------------------------------------------------
# §2 — FAIL in wrong worktrees
# ---------------------------------------------------------------------------


class TestWrongWorktree:
    def test_fail_for_double_space_main_worktree(self) -> None:
        """The double-space main worktree must be rejected."""
        with pytest.raises(WrongWorktreeError, match="not in expected worktree"):
            assert_active_worktree(cwd=Path("/tmp/Multi-Agent  VSGs/"))

    def test_fail_for_unrelated_dir(self) -> None:
        """A totally unrelated directory must be rejected."""
        with pytest.raises(WrongWorktreeError, match="not in expected worktree"):
            assert_active_worktree(cwd=Path("/tmp/random"))

    def test_fail_error_message_contains_cwd(self) -> None:
        """Error message must include the offending cwd for diagnostics."""
        bad_cwd = Path("/tmp/some-other-project")
        with pytest.raises(WrongWorktreeError) as exc_info:
            assert_active_worktree(cwd=bad_cwd)
        assert str(bad_cwd) in str(exc_info.value)

    def test_fail_error_message_contains_expected_basename(self) -> None:
        """Error message must include the expected basename."""
        with pytest.raises(WrongWorktreeError) as exc_info:
            assert_active_worktree(cwd=Path("/tmp/random"))
        assert EXPECTED_WORKTREE_BASENAME in str(exc_info.value)

    def test_fail_error_message_contains_override_var(self) -> None:
        """Error message must mention the env override var."""
        with pytest.raises(WrongWorktreeError) as exc_info:
            assert_active_worktree(cwd=Path("/tmp/random"))
        assert ENV_OVERRIDE in str(exc_info.value)


# ---------------------------------------------------------------------------
# §3 — Env override bypasses the assert
# ---------------------------------------------------------------------------


class TestEnvOverride:
    def test_override_allows_bad_cwd(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MAVSGS_DISABLE_WORKTREE_ASSERT=1 must allow any cwd without raising."""
        monkeypatch.setenv(ENV_OVERRIDE, "1")
        # Must not raise even from a completely wrong directory.
        assert_active_worktree(cwd=Path("/tmp/random"))

    def test_override_value_0_does_not_bypass(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only '1' is the magic override value; '0' must still enforce."""
        monkeypatch.setenv(ENV_OVERRIDE, "0")
        with pytest.raises(WrongWorktreeError):
            assert_active_worktree(cwd=Path("/tmp/random"))

    def test_override_empty_string_does_not_bypass(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty string must still enforce the guard."""
        monkeypatch.setenv(ENV_OVERRIDE, "")
        with pytest.raises(WrongWorktreeError):
            assert_active_worktree(cwd=Path("/tmp/random"))

    def test_override_absent_enforces_guard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When env var is unset, the guard must be active."""
        monkeypatch.delenv(ENV_OVERRIDE, raising=False)
        with pytest.raises(WrongWorktreeError):
            assert_active_worktree(cwd=Path("/tmp/random"))


# ---------------------------------------------------------------------------
# §4 — Custom expected_basename
# ---------------------------------------------------------------------------


class TestCustomBasename:
    def test_custom_basename_pass(self) -> None:
        """Caller-supplied basename must override the default."""
        assert_active_worktree("my-custom-name", cwd=Path("/tmp/my-custom-name"))

    def test_custom_basename_fail(self) -> None:
        """Custom basename must be required, not the default."""
        with pytest.raises(WrongWorktreeError):
            assert_active_worktree(
                "my-custom-name",
                cwd=Path("/tmp/Multi-Agent-VSGs-discrete"),
            )

    def test_custom_basename_nested_pass(self) -> None:
        """Custom basename must also work via parent walk."""
        assert_active_worktree(
            "my-custom-name",
            cwd=Path("/tmp/my-custom-name/sub/dir"),
        )
