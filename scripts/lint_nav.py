#!/usr/bin/env python3
"""Navigation link integrity checker.

Scans CLAUDE.md, AGENTS.md, and MEMORY.md for file/directory path
references (backtick-quoted paths and standard [text](path) links)
and verifies they exist on disk.

Also cross-checks CLAUDE.md scenario table against
scenarios/*/harness_reference.json for consistency.

Exit code 0 = all clear, 1 = broken references found.

Usage:
    python scripts/lint_nav.py
"""
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Navigation files to scan (relative to repo root)
NAV_FILES = ["CLAUDE.md", "AGENTS.md", "MEMORY.md"]

# Files that live in Claude private memory (~/.claude/.../memory/),
# not in the repo.  These are legitimate references for Claude agents
# but cannot be verified from the repo tree.
PRIVATE_MEMORY_FILES = {
    "sim_kundur_status.md",
    "sim_ne39_status.md",
    "andes_kundur_status.md",
    "andes_ne39_status.md",
}

# Extensions that signal "this backtick content is probably a file path"
FILE_EXTENSIONS = frozenset({
    ".py", ".m", ".md", ".json", ".slx", ".toml",
    ".yaml", ".yml", ".pt", ".csv", ".txt",
})

# Characters that indicate a backtick string is NOT a file path
NON_PATH_CHARS = frozenset("(=→+,{[>")


def _is_path_like(s: str) -> bool:
    """Heuristic: does this backtick-quoted string look like a file path?"""
    # Strip ::ClassName or ::function() suffix first
    stem = s.split("::")[0]
    if any(c in stem for c in NON_PATH_CHARS):
        return False
    if "*" in stem:  # glob pattern
        return False
    if " " in stem:  # prose, not a path
        return False
    has_sep = "/" in stem or "\\" in stem
    has_ext = Path(stem).suffix.lower() in FILE_EXTENSIONS
    # UPPER_SNAKE_CASE segments joined by / are variable lists, not paths
    # e.g. "H_MIN/H_MAX/D_MIN/D_MAX"
    if has_sep and not has_ext:
        parts = [p for p in stem.split("/") if p]
        if all(re.match(r"^[A-Z_0-9]+$", p) for p in parts):
            return False
    return has_sep or has_ext


def extract_backtick_refs(line, line_num):
    """Extract file-path references from `backtick` quotes."""
    refs = []
    for m in re.finditer(r"`([^`]+)`", line):
        raw = m.group(1)
        if not _is_path_like(raw):
            continue
        path_str = raw.split("::")[0].strip()
        refs.append((line_num, path_str, raw))
    return refs


def extract_markdown_links(line, line_num):
    """Extract [text](target) references, skipping URLs and anchors."""
    refs = []
    for m in re.finditer(r"\[([^\]]*)\]\(([^)]+)\)", line):
        target = m.group(2).split("#")[0]  # strip fragment
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        if not target:
            continue
        refs.append((line_num, target, m.group(0)))
    return refs


def check_file(nav_path):
    """Check all path references in one navigation file."""
    if not nav_path.exists():
        return []

    errors = []
    lines = nav_path.read_text(encoding="utf-8").splitlines()
    in_code_block = False

    for i, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        all_refs = extract_backtick_refs(line, i) + extract_markdown_links(line, i)

        for line_num, path_str, raw_ref in all_refs:
            # Whitelist: private memory files (basename match)
            if Path(path_str).name in PRIVATE_MEMORY_FILES:
                continue

            target = (REPO_ROOT / path_str).resolve()
            # Reject references that escape the repo tree
            if not str(target).startswith(str(REPO_ROOT.resolve())):
                errors.append(
                    f"  {nav_path.name}:{line_num}  `{raw_ref}`  -> OUTSIDE REPO"
                )
                continue
            if target.exists():
                continue
            # Directory ref with trailing slash
            if path_str.endswith("/"):
                dir_path = REPO_ROOT / path_str.rstrip("/")
                if dir_path.is_dir():
                    continue

            errors.append(
                f"  {nav_path.name}:{line_num}  `{raw_ref}`  -> NOT FOUND"
            )

    return errors


def check_harness_consistency() -> list[str]:
    """Cross-check CLAUDE.md scenario table against harness_reference.json."""
    errors = []
    claude_md = REPO_ROOT / "CLAUDE.md"
    if not claude_md.exists():
        return errors

    # Parse training script paths from CLAUDE.md scenario table
    table_scripts: dict[str, str] = {}  # scenario_label -> train script path
    text = claude_md.read_text(encoding="utf-8")
    in_table = False
    for line in text.splitlines():
        if "环境类" in line and "训练脚本" in line:
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                break
            if line.startswith("|--"):
                continue
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 3:
                label = cells[0].strip()
                # Extract path from backtick: `path/to/file.py`
                m = re.search(r"`([^`]+)`", cells[2])
                if m:
                    table_scripts[label] = m.group(1)

    # Load harness_reference.json files
    for ref_json in sorted(REPO_ROOT.glob("scenarios/*/harness_reference.json")):
        try:
            data = json.loads(ref_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            errors.append(
                f"  harness: {ref_json.relative_to(REPO_ROOT)} -> INVALID JSON"
            )
            continue

        scenario_id = data.get("scenario_id", "?")
        ref_items = {}
        for r in data.get("reference_items", []):
            k = r.get("key")
            v = r.get("value")
            if k is not None:
                ref_items[k] = v

        harness_entry = ref_items.get("training_entry")
        if not harness_entry:
            continue

        # Check that harness training_entry exists on disk
        if not (REPO_ROOT / harness_entry).exists():
            errors.append(
                f"  harness: {scenario_id} training_entry "
                f"`{harness_entry}` -> NOT FOUND"
            )

        # Check that CLAUDE.md scenario table includes this training entry
        # Use normalized path equality, not substring match
        norm_harness = harness_entry.replace("\\", "/")
        found = any(
            script_path.replace("\\", "/") == norm_harness
            for script_path in table_scripts.values()
        )
        if not found:
            errors.append(
                f"  harness: {scenario_id} training_entry "
                f"`{harness_entry}` not in CLAUDE.md scenario table"
            )

    return errors


def check_agent_control_manifest() -> list[str]:
    """Validate docs/control_manifest.toml structural integrity."""
    try:
        import tomllib
    except ImportError:
        return []  # Python < 3.11 without tomllib: skip silently

    errors = []
    manifest_path = REPO_ROOT / "docs" / "control_manifest.toml"

    if not manifest_path.exists():
        errors.append("  control_manifest.toml -> NOT FOUND at docs/control_manifest.toml")
        return errors

    try:
        data = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"  control_manifest.toml -> PARSE ERROR: {exc}")
        return errors

    # Check reference_py
    ref_py = data.get("reference_py", "")
    if not (REPO_ROOT / ref_py).exists():
        errors.append(f"  control_manifest.toml: reference_py `{ref_py}` -> NOT FOUND")

    # Check reference_paths for both control sections
    for section in ("model_harness", "training_control_surface"):
        sec = data.get(section, {})
        for rel in sec.get("reference_paths", []):
            if not (REPO_ROOT / rel).exists():
                errors.append(
                    f"  control_manifest.toml [{section}]: `{rel}` -> NOT FOUND"
                )

    # Check manifest declares all three canonical sections
    for section in ("model_harness", "smoke_bridge", "training_control_surface"):
        if section not in data:
            errors.append(f"  control_manifest.toml: missing section [{section}]")

    return errors


def main():
    all_errors = []
    checked = 0

    for name in NAV_FILES:
        nav_file = REPO_ROOT / name
        if nav_file.exists():
            checked += 1
            all_errors.extend(check_file(nav_file))

    # Cross-check harness consistency
    all_errors.extend(check_harness_consistency())

    # Validate agent control manifest
    all_errors.extend(check_agent_control_manifest())

    if not checked:
        print("FAIL: No navigation files found (wrong working directory?).")
        return 1

    if all_errors:
        print(f"FAIL: {len(all_errors)} broken reference(s):\n")
        for e in all_errors:
            print(e)
        print(
            f"\nIf a reference is in Claude private memory, "
            f"add it to PRIVATE_MEMORY_FILES in {Path(__file__).name}"
        )
        return 1

    print(f"OK: All path references valid ({checked} file(s) checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
