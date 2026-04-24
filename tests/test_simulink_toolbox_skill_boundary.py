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


def _resolve_unique_skill_dirs() -> list[Path]:
    """Return existing install dirs, deduplicated by canonical resolved path.

    When both install paths are junctions to the same shared root, scanning
    both would double-count every file. Deduplication prevents false positives.
    """
    existing = [path for path in SKILL_DIRS if path.exists()]
    unique: list[Path] = []
    seen: set[str] = set()
    for path in existing:
        try:
            key = str(path.resolve()).lower()
        except OSError:
            key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _existing_skill_dirs() -> list[Path]:
    return _resolve_unique_skill_dirs()


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
def test_installed_simulink_toolbox_no_training_smoke_debug_pattern() -> None:
    if not _existing_skill_dirs():
        pytest.skip("No installed simulink-toolbox skill directories found.")
    for skill_dir in _existing_skill_dirs():
        assert not (skill_dir / "patterns" / "training-smoke-debug.md").exists(), (
            f"{skill_dir}/patterns/training-smoke-debug.md must not exist in the "
            f"generic skill. Move it to docs/agent_layer/simulink-project-routing/."
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
