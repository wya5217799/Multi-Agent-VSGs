"""Navigation manifest consistency tests.

Validates that:
1. AGENTS.md "Start Here" matches docs/control_manifest.toml exactly.
2. All paths in the manifest exist on disk.
3. MEMORY.md does not maintain a parallel "Start Here" section.
"""
import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        import tomli as tomllib  # type: ignore[import-untyped,no-redef]

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_manifest() -> list[dict]:
    manifest_path = REPO_ROOT / "docs" / "control_manifest.toml"
    data = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    return data["start_here"]


def _extract_agents_start_here_entries() -> list[dict[str, str]]:
    """Extract path/purpose/trigger entries from the Start Here section of AGENTS.md."""
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    in_section = False
    entries = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## Start Here"):
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue

        match = re.search(
            r"^\d+\.\s+.+?`([^`]+)`\s+-\s+(.+?)\s+\(Re-evaluate when:\s+(.+?)\)\s*$",
            stripped,
        )
        if match:
            entries.append(
                {
                    "path": match.group(1),
                    "purpose": match.group(2),
                    "trigger": match.group(3),
                }
            )
    return entries


def test_manifest_paths_exist():
    """Every path in control_manifest.toml must exist on disk."""
    entries = _load_manifest()
    missing = []
    for entry in entries:
        full = REPO_ROOT / entry["path"]
        if not full.exists():
            missing.append(entry["path"])
    assert not missing, f"Manifest references missing files: {missing}"


def test_agents_matches_manifest():
    """AGENTS.md Start Here must render manifest entries exactly."""
    manifest_entries = [
        {
            "path": entry["path"],
            "purpose": entry["purpose"],
            "trigger": entry["trigger"],
        }
        for entry in _load_manifest()
    ]
    agents_entries = _extract_agents_start_here_entries()
    assert agents_entries == manifest_entries, (
        f"AGENTS.md Start Here does not match manifest.\n"
        f"  manifest: {manifest_entries}\n"
        f"  AGENTS.md: {agents_entries}"
    )


def test_memory_no_start_here():
    """MEMORY.md must not maintain a parallel Start Here section."""
    text = (REPO_ROOT / "MEMORY.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip().lower()
        assert not (
            stripped.startswith("#") and "start here" in stripped
        ), (
            "MEMORY.md contains a 'Start Here' section. "
            "Navigation entry points belong only in AGENTS.md "
            "(governed by docs/control_manifest.toml)."
        )
