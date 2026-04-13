"""
Tests for docs/agent_control_manifest.toml.

Validates:
- manifest file exists
- declared reference_py exists
- all reference_paths in both control sections exist
- both control lines are declared
"""
from __future__ import annotations

import tomllib
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_MANIFEST = _ROOT / "docs" / "agent_control_manifest.toml"


def _load() -> dict:
    return tomllib.loads(_MANIFEST.read_text(encoding="utf-8"))


def test_agent_control_manifest_exists():
    assert _MANIFEST.exists(), f"Missing: {_MANIFEST}"


def test_agent_control_manifest_reference_py_exists():
    data = _load()
    ref = _ROOT / data["reference_py"]
    assert ref.exists(), f"reference_py not found: {ref}"


def test_agent_control_manifest_reference_paths_exist():
    data = _load()
    for section in ("model_control", "training_control"):
        for rel in data[section]["reference_paths"]:
            path = _ROOT / rel
            assert path.exists(), f"[{section}] reference_path not found: {rel}"


def test_agent_control_manifest_declares_two_control_lines():
    data = _load()
    assert "model_control" in data, "missing model_control section"
    assert "training_control" in data, "missing training_control section"


def test_agent_control_manifest_task_families_nonempty():
    data = _load()
    for section in ("model_control", "training_control"):
        assert data[section]["task_family"], f"[{section}] task_family must not be empty"


def test_agent_control_manifest_version_is_int():
    data = _load()
    assert isinstance(data.get("version"), int), "version must be an integer"
