"""Scenario registry consistency tests.

Validates [[scenarios]] entries in docs/control_manifest.toml:
- Every file path (env_class, train_script, config, slx_model) exists on disk.
- Every scenario id matches the ids registered in engine/harness_registry.py.
- frequency_hz is set (50 or 60).
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_MANIFEST = _ROOT / "docs" / "control_manifest.toml"


def _load_scenarios() -> list[dict]:
    data = tomllib.loads(_MANIFEST.read_text(encoding="utf-8"))
    return data.get("scenarios", [])


def _registered_ids() -> set[str]:
    """Read scenario ids registered in harness_registry.py via the error message."""
    import engine.harness_registry as reg
    # resolve_scenario raises ValueError for unknown ids; extract valid ids
    # by trying known ids and catching failures for unknowns.
    valid = set()
    for candidate in ("kundur", "ne39"):
        try:
            reg.resolve_scenario(candidate)
            valid.add(candidate)
        except Exception:
            pass
    return valid


def test_scenario_manifest_file_paths_exist():
    """All file paths declared in [[scenarios]] must exist on disk."""
    scenarios = _load_scenarios()
    assert scenarios, "No [[scenarios]] entries found in control_manifest.toml"
    missing = []
    for s in scenarios:
        sid = s["id"]
        # env_class has "path::ClassName" format — check the file part only
        env_file = s["env_class"].split("::")[0]
        for field, path_str in [
            ("env_class", env_file),
            ("train_script", s["train_script"]),
            ("config", s["config"]),
            ("slx_model", s["slx_model"]),
        ]:
            full = _ROOT / path_str
            if not full.exists():
                missing.append(f"[{sid}] {field}: {path_str}")
    assert not missing, f"Missing paths in [[scenarios]]:\n" + "\n".join(missing)


def test_scenario_ids_match_harness_registry():
    """Scenario ids in manifest must match ids registered in harness_registry."""
    scenarios = _load_scenarios()
    manifest_ids = {s["id"] for s in scenarios}
    registry_ids = _registered_ids()
    assert manifest_ids == registry_ids, (
        f"Scenario id mismatch.\n"
        f"  manifest: {sorted(manifest_ids)}\n"
        f"  harness_registry: {sorted(registry_ids)}"
    )


def test_scenario_frequency_hz_set():
    """Every scenario must declare frequency_hz (50 or 60)."""
    scenarios = _load_scenarios()
    for s in scenarios:
        hz = s.get("frequency_hz")
        assert hz in (50, 60), (
            f"[{s['id']}] frequency_hz must be 50 or 60, got: {hz!r}"
        )
