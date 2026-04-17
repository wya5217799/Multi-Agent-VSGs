"""
Tests for docs/control_manifest.toml.

Validates:
- manifest file exists
- declared reference_py exists
- all reference_paths in model_harness and training_control_surface sections exist
- model_harness, smoke_bridge, and training_control_surface are declared
"""
from __future__ import annotations

import tomllib
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_MANIFEST = _ROOT / "docs" / "control_manifest.toml"


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
    for section in ("model_harness", "training_control_surface"):
        for rel in data[section]["reference_paths"]:
            path = _ROOT / rel
            assert path.exists(), f"[{section}] reference_path not found: {rel}"


def test_agent_control_manifest_declares_two_control_lines():
    data = _load()
    assert "model_harness" in data, "missing model_harness section"
    assert "training_control_surface" in data, "missing training_control_surface section"


def test_agent_control_manifest_task_families_nonempty():
    data = _load()
    for section in ("model_harness", "smoke_bridge", "training_control_surface"):
        assert data[section]["task_family"], f"[{section}] task_family must not be empty"


def test_agent_control_manifest_version_is_int():
    data = _load()
    assert isinstance(data.get("version"), int), "version must be an integer"
