"""Standard Markdown link check via lychee (auxiliary).

Checks [text](path) links and external URLs in Markdown files.
Skips if lychee is not installed — this is an optional enhancement.
The primary path checker is scripts/lint_nav.py.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(
    shutil.which("lychee") is None,
    reason="lychee not installed (optional dependency)",
)
def test_markdown_links_lychee():
    """All standard Markdown links pass lychee check."""
    result = subprocess.run(
        ["lychee", "--no-progress", "*.md", "docs/**/*.md"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"lychee found broken links:\n{result.stdout}\n{result.stderr}"
    )
