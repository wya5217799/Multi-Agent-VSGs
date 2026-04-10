#!/usr/bin/env python3
"""Auto-generate scenario path table from codebase structure.

Scans scenarios/ and env/ to derive the "Backend × Topology → Key Files"
table, then compares with CLAUDE.md's current table and prints a diff.

Usage:
    python scripts/gen_nav_table.py          # show diff
    python scripts/gen_nav_table.py --emit   # print generated table (for copy-paste)
"""
import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Backend display names
BACKEND_NAMES = {"andes": "ANDES", "ode": "ODE", "simulink": "Simulink"}
TOPOLOGY_NAMES = {"kundur": "Kundur", "new_england": "NE39"}


def find_training_scripts() -> list[dict]:
    """Discover all train_*.py scripts and extract metadata."""
    entries = []
    for train_py in sorted(REPO_ROOT.glob("scenarios/*/train_*.py")):
        topology = train_py.parent.name  # kundur or new_england
        backend = train_py.stem.replace("train_", "")  # andes, ode, simulink

        if topology not in TOPOLOGY_NAMES or backend not in BACKEND_NAMES:
            continue

        entry = {
            "backend": backend,
            "topology": topology,
            "label": f"{BACKEND_NAMES[backend]} {TOPOLOGY_NAMES[topology]}",
            "train_script": str(train_py.relative_to(REPO_ROOT)).replace("\\", "/"),
            "env_file": None,
            "env_class": None,
            "config_file": None,
        }

        # Extract env import and config import from source
        _extract_imports(train_py, entry)

        # Find config file
        _find_config(entry)

        entries.append(entry)

    return entries


def _resolve_redirect(file_path: Path) -> Path:
    """If file_path is a redirect shim (<= 5 lines, import *), follow it."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return file_path

    # Only follow very short files that are clearly redirect shims
    lines = [l for l in content.splitlines() if l.strip() and not l.startswith("#")]
    if len(lines) > 5:
        return file_path
    if not any("import *" in l or "import *" in l for l in content.splitlines()):
        return file_path

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return file_path

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            real_path = REPO_ROOT / (node.module.replace(".", "/") + ".py")
            if real_path.exists() and real_path != file_path:
                return real_path
    return file_path


def _extract_imports(train_py: Path, entry: dict) -> None:
    """Parse training script imports to find env class and module."""
    try:
        tree = ast.parse(train_py.read_text(encoding="utf-8"))
    except SyntaxError:
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module
            # env imports: from env.* import SomeEnv
            if mod.startswith("env."):
                names = [a.name for a in (node.names or [])]
                env_names = [n for n in names if "Env" in n]
                # Only use this import if it contains an Env class
                # (skip utility imports like sac_agent_standalone)
                if env_names:
                    mod_path = mod.replace(".", "/") + ".py"
                    candidate = REPO_ROOT / mod_path
                    if candidate.exists():
                        # Follow redirect shims to canonical location
                        real = _resolve_redirect(candidate)
                        entry["env_file"] = str(
                            real.relative_to(REPO_ROOT)
                        ).replace("\\", "/")
                    else:
                        entry["env_file"] = mod_path
                    entry["env_class"] = env_names[0]

            # config imports: from scenarios.*.config_* import ...
            if "config" in mod:
                mod_path = mod.replace(".", "/") + ".py"
                candidate = REPO_ROOT / mod_path
                if candidate.exists():
                    entry["config_file"] = mod_path


def _find_config(entry: dict) -> None:
    """Resolve config file if not found via import."""
    if entry["config_file"]:
        return

    backend = entry["backend"]
    topology = entry["topology"]

    if backend == "simulink":
        cfg = f"scenarios/{topology}/config_simulink.py"
        if (REPO_ROOT / cfg).exists():
            entry["config_file"] = cfg
    else:
        if (REPO_ROOT / "config.py").exists():
            entry["config_file"] = "config.py"


def format_table(entries: list[dict]) -> str:
    """Format entries as a Markdown table matching CLAUDE.md style."""
    lines = [
        "| 场景 | 环境类 | 训练脚本 | 配置 |",
        "|------|--------|----------|------|",
    ]
    for e in entries:
        if e["env_file"]:
            env_col = f"`{e['env_file']}"
            if e["env_class"]:
                env_col += f"::{e['env_class']}"
            env_col += "`"
        else:
            env_col = "*(indirect import)*"
        lines.append(
            f"| {e['label']} "
            f"| {env_col} "
            f"| `{e['train_script']}` "
            f"| `{e['config_file'] or '?'}` |"
        )
    return "\n".join(lines)


def parse_claude_table(claude_md: Path) -> list[str]:
    """Extract the scenario table rows from CLAUDE.md."""
    text = claude_md.read_text(encoding="utf-8")
    rows = []
    in_table = False
    for line in text.splitlines():
        # Detect the scenario table by its header
        if "环境类" in line and "训练脚本" in line and "配置" in line:
            in_table = True
            rows.append(line)
            continue
        if in_table:
            if line.startswith("|"):
                rows.append(line)
            else:
                break
    return rows


def diff_tables(current_lines: list[str], generated: str) -> list[str]:
    """Compare current and generated tables, return diff lines."""
    gen_lines = generated.splitlines()
    diffs = []

    # Normalize for comparison (strip whitespace around |)
    def norm(line: str) -> str:
        return re.sub(r"\s*\|\s*", "|", line.strip()).strip("|")

    curr_set = {norm(l) for l in current_lines if not l.startswith("|--")}
    gen_set = {norm(l) for l in gen_lines if not l.startswith("|--")}

    # Find entries in generated but not in current
    for gl in gen_lines:
        if gl.startswith("|--"):
            continue
        if norm(gl) not in curr_set:
            diffs.append(f"+ {gl}")

    # Find entries in current but not in generated
    for cl in current_lines:
        if cl.startswith("|--"):
            continue
        if norm(cl) not in gen_set:
            diffs.append(f"- {cl}")

    return diffs


def main() -> int:
    emit_only = "--emit" in sys.argv

    entries = find_training_scripts()
    if not entries:
        print("WARN: No training scripts found.")
        return 1

    generated = format_table(entries)

    if emit_only:
        print(generated)
        return 0

    claude_md = REPO_ROOT / "CLAUDE.md"
    if not claude_md.exists():
        print("WARN: CLAUDE.md not found, printing generated table:")
        print(generated)
        return 0

    current = parse_claude_table(claude_md)
    if not current:
        print("WARN: Could not parse scenario table from CLAUDE.md")
        print("\nGenerated table:")
        print(generated)
        return 1

    diffs = diff_tables(current, generated)
    if not diffs:
        print(f"OK: Scenario table in sync ({len(entries)} scenarios).")
        return 0

    print(f"DRIFT: {len(diffs)} difference(s) between CLAUDE.md and codebase:\n")
    for d in diffs:
        print(f"  {d}")
    print(f"\nGenerated table ({len(entries)} scenarios):")
    print(generated)
    return 1


if __name__ == "__main__":
    sys.exit(main())
