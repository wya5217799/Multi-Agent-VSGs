"""Navigation documentation link integrity test.

Ensures that all file path references in CLAUDE.md, AGENTS.md,
and MEMORY.md point to files/directories that actually exist.
Catches dead links before they mislead agents or developers.
"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_navigation_links_valid():
    """All path references in navigation docs must resolve to existing files."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "lint_nav.py")],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"Navigation link check failed:\n{result.stdout}"
    )
