"""tests/test_regen_skill_index.py — Verify that index.json is consistent with PUBLIC_TOOLS.

Runs entirely offline (no MATLAB needed).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _PROJECT_ROOT / "scripts" / "regen_skill_index.py"


def _load_generated_index(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))


@pytest.mark.offline
def test_skill_index_consistent_with_public_tools(tmp_path: Path) -> None:
    """index.json must match what regen_skill_index.py would generate from PUBLIC_TOOLS."""
    env = {**os.environ, "SKILL_DIR": str(tmp_path)}

    # First generate the index into the temp dir.
    gen = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert gen.returncode == 0, f"regen failed:\n{gen.stdout}\n{gen.stderr}"

    # Then verify --check agrees with what was just written.
    check = subprocess.run(
        [sys.executable, str(_SCRIPT), "--check"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert check.returncode == 0, (
        "index.json is out of sync with PUBLIC_TOOLS.\n"
        "Run `python scripts/regen_skill_index.py` to fix.\n\n"
        f"--- stdout ---\n{check.stdout}\n"
        f"--- stderr ---\n{check.stderr}"
    )


@pytest.mark.offline
def test_generated_skill_index_is_generic_only(tmp_path: Path) -> None:
    """Generated index must exclude project-only tools even though they are public in the MCP server."""
    env = {**os.environ, "SKILL_DIR": str(tmp_path)}

    gen = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert gen.returncode == 0, f"regen failed:\n{gen.stdout}\n{gen.stderr}"

    payload = _load_generated_index(tmp_path)
    assert "harness_tools" not in payload
    assert "training_tools" not in payload

    names = {tool["name"] for tool in payload["simulink_tools"]}
    assert "simulink_bridge_status" not in names
    assert all(name.startswith("simulink_") for name in names)

    excluded = set(payload["meta"]["excluded_project_tools"])
    assert "simulink_bridge_status" in excluded
    assert any(name.startswith("harness_") for name in excluded)
    assert any(name.startswith("training_") for name in excluded)
