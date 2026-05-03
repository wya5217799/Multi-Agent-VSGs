"""
Tests for scripts/archive_superseded_plans.py.

Uses tmp_path pytest fixture for fully sandboxed test directories.
"""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helper: import the script as a module (works without installing)
# ---------------------------------------------------------------------------

def _import_archive_module() -> types.ModuleType:
    """Import archive_superseded_plans without executing main()."""
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    spec = importlib.util.spec_from_file_location(
        "archive_superseded_plans",
        scripts_dir / "archive_superseded_plans.py",
    )
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


archive = _import_archive_module()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sandbox(tmp_path: Path) -> dict[str, Path]:
    """
    Create a minimal sandbox mimicking the repo layout.

    Returns dict with keys: root, plans, gates.
    """
    plans = tmp_path / "quality_reports" / "plans"
    gates = tmp_path / "quality_reports" / "gates"
    plans.mkdir(parents=True)
    gates.mkdir(parents=True)
    return {"root": tmp_path, "plans": plans, "gates": gates}


# ---------------------------------------------------------------------------
# Test 1: Rule 1 — Status: SUPERSEDED marker in content
# ---------------------------------------------------------------------------

class TestRule1SupersededMarker:
    def test_file_with_superseded_status_is_detected(self, sandbox: dict[str, Path]) -> None:
        plans = sandbox["plans"]
        fpath = plans / "2026-04-20_old_plan.md"
        fpath.write_text("# Old plan\n\nStatus: SUPERSEDED\n\nSome content.\n")

        # Patch PLANS_DIR / GATES_DIR to point at sandbox
        orig_plans = archive.PLANS_DIR
        orig_gates = archive.GATES_DIR
        try:
            archive.PLANS_DIR = plans
            archive.GATES_DIR = sandbox["gates"]
            candidates = archive._collect_candidates(
                plans,
                [],          # no glob patterns
                set(),       # no retain set
                verbose=False,
            )
        finally:
            archive.PLANS_DIR = orig_plans
            archive.GATES_DIR = orig_gates

        names = [c[0].name for c in candidates]
        assert "2026-04-20_old_plan.md" in names

    def test_file_without_marker_is_not_detected_by_rule1(self, sandbox: dict[str, Path]) -> None:
        plans = sandbox["plans"]
        fpath = plans / "2026-04-20_active_plan.md"
        fpath.write_text("# Active plan\n\nStatus: APPROVED\n\nSome content.\n")

        candidates = archive._collect_candidates(
            plans, [], set(), verbose=False
        )
        assert not candidates

    def test_marker_case_insensitive(self, sandbox: dict[str, Path]) -> None:
        plans = sandbox["plans"]
        fpath = plans / "2026-04-20_case_plan.md"
        fpath.write_text("**Status**: superseded\n\nOld work.\n")

        candidates = archive._collect_candidates(
            plans, [], set(), verbose=False
        )
        assert len(candidates) == 1

    def test_marker_with_bold_formatting(self, sandbox: dict[str, Path]) -> None:
        """Template format: **Status**: SUPERSEDED"""
        plans = sandbox["plans"]
        fpath = plans / "2026-04-21_bold_plan.md"
        fpath.write_text("# Plan\n\n**Status**: SUPERSEDED\n")

        candidates = archive._collect_candidates(
            plans, [], set(), verbose=False
        )
        assert len(candidates) == 1


# ---------------------------------------------------------------------------
# Test 2: Rule 3 — hardcoded glob detection
# ---------------------------------------------------------------------------

class TestRule3HardcodedGlob:
    def test_file_matching_glob_pattern_is_detected(self, sandbox: dict[str, Path]) -> None:
        plans = sandbox["plans"]
        target = plans / "2026-04-26_some_old_plan.md"
        target.write_text("# Old plan\n")

        candidates = archive._collect_candidates(
            plans,
            ["2026-04-26_*.md"],   # glob pattern matching the file
            set(),
            verbose=False,
        )
        names = [c[0].name for c in candidates]
        assert "2026-04-26_some_old_plan.md" in names

    def test_file_not_matching_glob_is_kept(self, sandbox: dict[str, Path]) -> None:
        plans = sandbox["plans"]
        other = plans / "2026-04-27_another_plan.md"
        other.write_text("# Another plan\n")

        candidates = archive._collect_candidates(
            plans,
            ["2026-04-26_*.md"],
            set(),
            verbose=False,
        )
        assert not candidates

    def test_task_1_2_3_globs(self, sandbox: dict[str, Path]) -> None:
        plans = sandbox["plans"]
        t1 = plans / "2026-04-28-task-1-execution-plan.md"
        t2 = plans / "2026-04-28-task-2-execution-plan.md"
        t3 = plans / "2026-04-28-task-3-doc-plan.md"
        for f in (t1, t2, t3):
            f.write_text("# Task\n")

        candidates = archive._collect_candidates(
            plans,
            ["2026-04-28-task-1*.md", "2026-04-28-task-2*.md", "2026-04-28-task-3*.md"],
            set(),
            verbose=False,
        )
        detected = {c[0].name for c in candidates}
        assert t1.name in detected
        assert t2.name in detected
        assert t3.name in detected


# ---------------------------------------------------------------------------
# Test 3: Retain list — phase1_progress_and_next_steps must NOT be detected
# ---------------------------------------------------------------------------

class TestRetainList:
    def test_retain_explicit_name_not_detected(self, sandbox: dict[str, Path]) -> None:
        plans = sandbox["plans"]
        retain = plans / "2026-05-03_phase1_progress_and_next_steps.md"
        retain.write_text("# SoT plan\n\nStatus: SUPERSEDED\n")  # even with marker

        candidates = archive._collect_candidates(
            plans,
            ["2026-05-03_*.md"],   # broad glob
            {"2026-05-03_phase1_progress_and_next_steps.md"},
            verbose=False,
        )
        names = [c[0].name for c in candidates]
        assert retain.name not in names

    def test_date_based_retain_2026_05_03_and_later(self, sandbox: dict[str, Path]) -> None:
        plans = sandbox["plans"]
        recent = plans / "2026-05-03_new_plan.md"
        recent.write_text("# New plan\n")

        # Even with a matching glob, date >= RETAIN_AFTER_DATE keeps it
        candidates = archive._collect_candidates(
            plans,
            ["2026-05-03_*.md"],
            set(),                 # no explicit retain set
            verbose=False,
        )
        # Should be retained by date logic
        assert not candidates

    def test_older_file_not_retained_by_date(self, sandbox: dict[str, Path]) -> None:
        plans = sandbox["plans"]
        old = plans / "2026-04-26_old.md"
        old.write_text("# Old\n")

        candidates = archive._collect_candidates(
            plans,
            ["2026-04-26_*.md"],
            set(),
            verbose=False,
        )
        assert len(candidates) == 1


# ---------------------------------------------------------------------------
# Test 4: Move semantics — --apply moves; --dry-run doesn't
# ---------------------------------------------------------------------------

class TestMoveSemantics:
    def _make_file(self, directory: Path, name: str, content: str = "# f\n") -> Path:
        f = directory / name
        f.write_text(content)
        return f

    def test_dry_run_does_not_move_files(self, sandbox: dict[str, Path]) -> None:
        plans = sandbox["plans"]
        fpath = self._make_file(plans, "2026-04-26_old.md")

        archive._archive_file(fpath, dry_run=True, verbose=False)

        assert fpath.exists(), "dry-run must not move the file"
        assert not (plans / "_archive" / fpath.name).exists()

    def test_apply_moves_file_to_archive(self, sandbox: dict[str, Path]) -> None:
        plans = sandbox["plans"]
        fpath = self._make_file(plans, "2026-04-26_old.md")

        result = archive._archive_file(fpath, dry_run=False, verbose=False)

        assert result is True
        assert not fpath.exists(), "file must be moved away"
        assert (plans / "_archive" / fpath.name).exists()

    def test_apply_creates_archive_dir_if_missing(self, sandbox: dict[str, Path]) -> None:
        plans = sandbox["plans"]
        fpath = self._make_file(plans, "2026-04-26_create_dir.md")

        assert not (plans / "_archive").exists()
        archive._archive_file(fpath, dry_run=False, verbose=False)
        assert (plans / "_archive").is_dir()

    def test_apply_creates_readme_in_archive_dir(self, sandbox: dict[str, Path]) -> None:
        plans = sandbox["plans"]
        fpath = self._make_file(plans, "2026-04-26_create_readme.md")

        archive._archive_file(fpath, dry_run=False, verbose=False)

        readme = plans / "_archive" / "README.md"
        assert readme.exists()
        assert "_archive/" in readme.read_text()


# ---------------------------------------------------------------------------
# Test 5: Idempotency — running --apply twice doesn't fail
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_second_apply_skips_already_archived(self, sandbox: dict[str, Path]) -> None:
        plans = sandbox["plans"]
        fpath = plans / "2026-04-26_already_archived.md"
        fpath.write_text("# f\n")

        # First move
        archive._archive_file(fpath, dry_run=False, verbose=False)
        assert not fpath.exists()
        dest = plans / "_archive" / fpath.name
        assert dest.exists()

        # Second call — file is in _archive, should skip silently (return False)
        result = archive._archive_file(fpath, dry_run=False, verbose=False)
        assert result is False   # nothing happened
        assert dest.exists()     # dest still intact

    def test_dry_run_after_apply_returns_false_for_already_moved(
        self, sandbox: dict[str, Path]
    ) -> None:
        plans = sandbox["plans"]
        fpath = plans / "2026-04-26_once_moved.md"
        fpath.write_text("# f\n")

        archive._archive_file(fpath, dry_run=False, verbose=False)

        # dry-run on the (now-gone) src: dest already exists → skip
        result = archive._archive_file(fpath, dry_run=True, verbose=False)
        assert result is False
