"""
archive_superseded_plans.py — Move superseded plan/gate files to _archive/ subdirs.

Usage:
    python scripts/archive_superseded_plans.py [--dry-run | --apply] [--verbose]

Default mode is --dry-run (no files moved). Pass --apply to move files.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Repository root (two levels up from this script)
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
PLANS_DIR = REPO_ROOT / "quality_reports" / "plans"
GATES_DIR = REPO_ROOT / "quality_reports" / "gates"

# ---------------------------------------------------------------------------
# Retain list — these files must NEVER be archived regardless of other rules
# ---------------------------------------------------------------------------
RETAIN_PLANS: set[str] = {
    "2026-05-03_phase1_progress_and_next_steps.md",
    "2026-05-03_phase1_5_ccs_restoration.md",
    "2026-05-03_engineering_philosophy.md",
    "2026-05-04_loadstep_bus15_hybrid_dispatch_fix.md",
    "2026-05-04_p0-3_gate_eval_auto.md",
    "2026-05-03_phase4_speedup_p2_plan.md",
    # Anything 2026-05-03 or later is implicitly retained by date; the hardcoded
    # list below only targets earlier dates or specific files.
}

# Minimum date for auto-retain: any YYYY-MM-DD file >= this date is retained.
# Set to 2026-05-03 per spec ("anything dated 2026-05-03 or later").
RETAIN_AFTER_DATE = datetime(2026, 5, 3).date()

# ---------------------------------------------------------------------------
# Hardcoded superseded list (Rule 3 — primary mechanism for this cycle)
# ---------------------------------------------------------------------------

# Glob patterns relative to PLANS_DIR
SUPERSEDED_PLANS_GLOBS: list[str] = [
    "2026-04-26_*.md",
    "2026-04-28-task-1*.md",
    "2026-04-28-task-2*.md",
    "2026-04-28-task-3*.md",
    "phase_b_findings_cvs_discrete_unlock.md",
    "phase_b_extended_module_selection.md",
    "2026-05-03_phase0_smib_discrete_verdict.md",
]

# Glob patterns relative to GATES_DIR
SUPERSEDED_GATES_GLOBS: list[str] = [
    "2026-04-26_kundur_cvs_g3prep_*.md",
]

# ---------------------------------------------------------------------------
# Rule 1: detect "Status: SUPERSEDED" in file content
# ---------------------------------------------------------------------------
_STATUS_SUPERSEDED_RE = re.compile(
    r"^\s*\*{0,2}Status\*{0,2}\s*:\s*SUPERSEDED",
    re.IGNORECASE | re.MULTILINE,
)


def _has_superseded_marker(path: Path) -> bool:
    """Return True if file contains a Status: SUPERSEDED header."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(_STATUS_SUPERSEDED_RE.search(text))


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------
_DATE_PREFIX_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _file_date(filename: str) -> datetime | None:
    """Extract YYYY-MM-DD from filename prefix, return None if absent."""
    m = _DATE_PREFIX_RE.match(filename)
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _is_date_retained(filename: str) -> bool:
    """Return True if the file's date prefix is on or after RETAIN_AFTER_DATE."""
    d = _file_date(filename)
    if d is None:
        return False
    return d.date() >= RETAIN_AFTER_DATE


# ---------------------------------------------------------------------------
# Core detection logic
# ---------------------------------------------------------------------------

def _collect_candidates(
    directory: Path,
    glob_patterns: list[str],
    retain_set: set[str],
    *,
    verbose: bool,
) -> list[tuple[Path, str]]:
    """
    Return list of (path, reason) pairs for files to be archived from `directory`.

    Detection order:
      1. Retain set — skip immediately.
      2. Date-based retain — skip if file date >= RETAIN_AFTER_DATE.
      3. Rule 3 (hardcoded globs) — flag as superseded.
      4. Rule 1 (Status: SUPERSEDED marker) — flag as superseded.
    """
    candidates: list[tuple[Path, str]] = []
    if not directory.is_dir():
        if verbose:
            print(f"  [skip] {directory} does not exist")
        return candidates

    all_files = sorted(directory.glob("*.md"))

    # Build rule-3 set from globs
    rule3_files: set[Path] = set()
    for pattern in glob_patterns:
        rule3_files.update(directory.glob(pattern))

    for fpath in all_files:
        fname = fpath.name

        # --- Retain set (explicit names)
        if fname in retain_set:
            if verbose:
                print(f"  [retain:explicit]    {fname}")
            continue

        # --- Date-based retain
        if _is_date_retained(fname):
            if verbose:
                print(f"  [retain:date>=2026-05-03] {fname}")
            continue

        reason: str | None = None

        # --- Rule 3: hardcoded glob
        if fpath in rule3_files:
            reason = "rule3:hardcoded-glob"

        # --- Rule 1: Status: SUPERSEDED marker (additive)
        if reason is None and _has_superseded_marker(fpath):
            reason = "rule1:status-superseded"

        if reason:
            candidates.append((fpath, reason))
            if verbose:
                print(f"  [candidate:{reason}] {fname}")
        else:
            if verbose:
                print(f"  [keep]               {fname}")

    return candidates


# ---------------------------------------------------------------------------
# Archive action
# ---------------------------------------------------------------------------

def _archive_file(src: Path, dry_run: bool, *, verbose: bool) -> bool:
    """
    Move src into src.parent/_archive/. Preserves mtime via shutil.move.
    If target already exists, skip silently (idempotent).
    Returns True if a move occurred (or would occur in dry-run).
    """
    archive_dir = src.parent / "_archive"
    dest = archive_dir / src.name

    if dest.exists():
        if verbose:
            print(f"  [skip:already-archived] {src.name}")
        return False

    if dry_run:
        print(f"  [dry-run] would move: {src.name} -> _archive/{src.name}")
        return True

    archive_dir.mkdir(exist_ok=True)
    _ensure_readme(archive_dir)
    shutil.move(str(src), str(dest))
    print(f"  [moved] {src.name} -> _archive/{src.name}")
    return True


def _ensure_readme(archive_dir: Path) -> None:
    """Write a minimal README.md into _archive/ if it doesn't exist."""
    readme = archive_dir / "README.md"
    if readme.exists():
        return
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    readme.write_text(
        f"# _archive/\n\n"
        f"Files moved here by `scripts/archive_superseded_plans.py` on {timestamp}.\n\n"
        "These files are superseded by active plans and are kept for reference.\n"
        "Use `git log -- <original-path>` to recover full history.\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(*, dry_run: bool, verbose: bool) -> int:
    mode_label = "DRY-RUN" if dry_run else "APPLY"
    print(f"archive_superseded_plans.py [{mode_label}]")
    print(f"  plans dir : {PLANS_DIR}")
    print(f"  gates dir : {GATES_DIR}")
    print()

    # --- Plans
    print("=== Scanning plans/ ===")
    plan_candidates = _collect_candidates(
        PLANS_DIR, SUPERSEDED_PLANS_GLOBS, RETAIN_PLANS, verbose=verbose
    )

    # --- Gates (no explicit retain set for gates)
    print("\n=== Scanning gates/ ===")
    gate_candidates = _collect_candidates(
        GATES_DIR, SUPERSEDED_GATES_GLOBS, set(), verbose=verbose
    )

    print()
    moved_plans = 0
    moved_gates = 0

    if plan_candidates:
        print(f"--- Archiving {len(plan_candidates)} plan(s) ---")
        for path, reason in plan_candidates:
            if _archive_file(path, dry_run=dry_run, verbose=verbose):
                moved_plans += 1
    else:
        print("--- No plans to archive ---")

    if gate_candidates:
        print(f"\n--- Archiving {len(gate_candidates)} gate(s) ---")
        for path, reason in gate_candidates:
            if _archive_file(path, dry_run=dry_run, verbose=verbose):
                moved_gates += 1
    else:
        print("\n--- No gates to archive ---")

    print()
    print("=== Summary ===")
    print(f"  Plans archived : {moved_plans}")
    print(f"  Gates archived : {moved_gates}")
    print(f"  Total          : {moved_plans + moved_gates}")
    if dry_run:
        print("\n  (dry-run: no files were moved — pass --apply to move them)")
    else:
        print("\n  Done.")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Archive superseded plan/gate files to _archive/ subdirs."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Print what would be moved without moving (default).",
    )
    mode.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="Actually move the files.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-file decision rationale.",
    )
    args = parser.parse_args()
    sys.exit(run(dry_run=args.dry_run, verbose=args.verbose))


if __name__ == "__main__":
    main()
