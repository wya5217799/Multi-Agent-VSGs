"""Static boundary tests for installed simulink-toolbox skill copies.

The global skill is shared across Simulink projects. It must stay generic and
must not contain this repository's Yang/VSG harness or training routing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


SKILL_DIRS = [
    Path.home() / ".codex" / "skills" / "simulink-toolbox",
    Path.home() / ".claude" / "skills" / "simulink-toolbox",
]

PROJECT_ONLY_PATTERNS = [
    r"\bYang\b",
    r"\bKundur\b",
    r"\bNE39\b",
    r"\bVSG\b",
    r"\bharness_",
    r"\btraining_",
    r"\bsimulink_bridge_status\b",
    r"\bSimulinkBridge\b",
    r"\bagent\b",
    r"\bagents\b",
    r"\bepisode\b",
    r"\breward\b",
    r"\bPe\b",
    r"\bomega\b",
    r"\bdelta\b",
    r"\bget_training_launch_status\b",
]

GENERIC_ALLOWED_TOOL_PREFIX = "simulink_"
PROJECT_ONLY_SIMULINK_TOOLS = {"simulink_bridge_status"}


def _existing_skill_dirs() -> list[Path]:
    return [path for path in SKILL_DIRS if path.exists()]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.offline
def test_installed_simulink_toolbox_skill_copies_exist_when_checked() -> None:
    if not _existing_skill_dirs():
        pytest.skip("No installed simulink-toolbox skill directories found.")
    for skill_dir in _existing_skill_dirs():
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "map.md").exists()
        assert (skill_dir / "index.json").exists()


@pytest.mark.offline
def test_installed_simulink_toolbox_docs_are_project_neutral() -> None:
    if not _existing_skill_dirs():
        pytest.skip("No installed simulink-toolbox skill directories found.")

    for skill_dir in _existing_skill_dirs():
        for filename in ("SKILL.md", "map.md"):
            text = _read_text(skill_dir / filename)
            for pattern in PROJECT_ONLY_PATTERNS:
                assert not re.search(pattern, text), (
                    f"{skill_dir / filename} contains project-only pattern {pattern!r}"
                )


@pytest.mark.offline
def test_installed_simulink_toolbox_index_is_generic_only() -> None:
    if not _existing_skill_dirs():
        pytest.skip("No installed simulink-toolbox skill directories found.")

    for skill_dir in _existing_skill_dirs():
        payload = json.loads((skill_dir / "index.json").read_text(encoding="utf-8"))
        assert "harness_tools" not in payload
        assert "training_tools" not in payload

        tools = payload.get("simulink_tools", [])
        assert tools, f"{skill_dir / 'index.json'} has no simulink_tools"
        for tool in tools:
            name = tool["name"]
            assert name.startswith(GENERIC_ALLOWED_TOOL_PREFIX)
            assert name not in PROJECT_ONLY_SIMULINK_TOOLS
            assert tool.get("group") != "training_bridge"
            description = tool.get("description", "")
            for pattern in PROJECT_ONLY_PATTERNS:
                assert not re.search(pattern, description), (
                    f"{skill_dir / 'index.json'} tool {name!r} description "
                    f"contains project-only pattern {pattern!r}"
                )
