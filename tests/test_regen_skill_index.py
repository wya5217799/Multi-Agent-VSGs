"""tests/test_regen_skill_index.py — Verify that index.json is consistent with PUBLIC_TOOLS.

Runs entirely offline (no MATLAB needed).
"""

import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _PROJECT_ROOT / "scripts" / "regen_skill_index.py"


@pytest.mark.offline
def test_skill_index_consistent_with_public_tools():
    """index.json must match what regen_skill_index.py would generate from PUBLIC_TOOLS."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "index.json is out of sync with PUBLIC_TOOLS.\n"
        "Run `python scripts/regen_skill_index.py` to fix.\n\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
