"""scripts/regen_skill_index.py — Regenerate ~/.claude/skills/simulink-toolbox/index.json
from the single source of truth: engine.mcp_server.PUBLIC_TOOLS.

Usage:
    python scripts/regen_skill_index.py          # overwrite index.json
    python scripts/regen_skill_index.py --check  # exit 0 if consistent, 1+diff if not

Environment:
    SKILL_DIR   Override skill directory (default: ~/.claude/skills/simulink-toolbox/)
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so engine.mcp_server can be imported
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Tool metadata tables — used to assign group/description per tool name.
# These mirror what is currently in index.json (ground truth for display info).
# ---------------------------------------------------------------------------

_SIMULINK_META: dict[str, dict[str, str]] = {
    "simulink_add_block":            {"group": "construct", "description": "Add a single block to a model"},
    "simulink_add_subsystem":        {"group": "construct", "description": "Add a subsystem container"},
    "simulink_bridge_status":        {"group": "training_bridge", "description": "VSG/training bridge runtime state (step, Pe, delta, tripload) — NOT a connectivity check"},
    "simulink_capture_figure":       {"group": "capture",   "description": "Capture a MATLAB figure window"},
    "simulink_close_model":          {"group": "construct", "description": "Close an open model from MATLAB session"},
    "simulink_compile_diagnostics":  {"group": "verify",    "description": "Full compile with error/warning report"},
    "simulink_connect_ports":        {"group": "wire",      "description": "Connect two block ports (1-indexed)"},
    "simulink_create_model":         {"group": "construct", "description": "Create a new empty .slx file"},
    "simulink_delete_block":         {"group": "modify",    "description": "Delete a block by path"},
    "simulink_describe_block_ports": {"group": "wire",      "description": "List all port names and directions for a block"},
    "simulink_explore_block":        {"group": "discover",  "description": "Deep inspect a single block (type, params, ports)"},
    "simulink_get_block_tree":       {"group": "discover",  "description": "Get full block hierarchy of a model"},
    "simulink_library_lookup":       {"group": "discover",  "description": "Query library block params/defaults/ports (pre-placement); NOT model-level verification"},
    "simulink_load_model":           {"group": "construct", "description": "Open an existing .slx into MATLAB"},
    "simulink_loaded_models":        {"group": "discover",  "description": "List models currently loaded in MATLAB session"},
    "simulink_patch_and_verify":     {"group": "verify",    "description": "Atomic: set param + immediate verify"},
    "simulink_poll_script":          {"group": "execute",   "description": "Poll status of async script job"},
    "simulink_query_params":         {"group": "query",     "description": "Read current parameter values (read-only)"},
    "simulink_run_script":           {"group": "execute",   "description": "Run MATLAB script synchronously (<=30s); no audit required — MCP escape hatch"},
    "simulink_run_script_async":     {"group": "execute",   "description": "Run MATLAB script asynchronously; no audit required — use poll_script for results"},
    "simulink_screenshot":           {"group": "capture",   "description": "Screenshot the Simulink canvas"},
    "simulink_set_block_params":     {"group": "modify",    "description": "Set block parameter values"},
    "simulink_solver_audit":         {"group": "verify",    "description": "Check solver configuration (step size, tolerance)"},
    "simulink_step_diagnostics":     {"group": "diagnose",  "description": "Single-step run with per-step diagnostics"},
    "simulink_trace_port_connections": {"group": "wire",    "description": "Trace signal chain from a port upstream/downstream"},
    "simulink_model_status":         {"group": "discover",  "description": "Return loaded/dirty/runtime status for one model"},
    "simulink_save_model":           {"group": "construct", "description": "Save a model, optionally to a target path"},
    "simulink_workspace_set":        {"group": "workspace", "description": "Set MATLAB base-workspace variables in one call"},
    "simulink_run_window":           {"group": "runtime",   "description": "Run a model over a controlled simulation window"},
    "simulink_runtime_reset":        {"group": "runtime",   "description": "Reset FastRestart/runtime state without project semantics"},
    "simulink_signal_snapshot":      {"group": "signals",   "description": "Read logged/ToWorkspace/block-output values at one time point"},
}

_PROJECT_ONLY_TOOLS: set[str] = {
    "simulink_bridge_status",
}

# harness_* and training_* tools use a flat description string (no "group" field)
# because they are project-specific harness tools, not general Simulink tools.
_HARNESS_META: dict[str, str] = {
    "harness_model_diagnose":       "Diagnose harness model errors",
    "harness_model_inspect":        "Inspect harness model structure",
    "harness_model_patch_verify":   "Patch and verify harness model",
    "harness_model_report":         "Generate harness model report",
    "harness_scenario_status":      "Check scenario run status",
    "harness_train_smoke_minimal":  "Run minimal harness smoke training",
    "harness_train_smoke_start":    "Start harness smoke training",
    "harness_train_smoke_poll":     "Poll harness smoke training status",
}

_TRAINING_META: dict[str, str] = {
    "training_compare_runs":  "Compare training runs",
    "training_diagnose":      "Diagnose training errors",
    "training_evaluate_run":  "Evaluate a training run",
    "training_status":        "Get training status",
}


def _get_skill_dirs() -> list[Path]:
    """Return target skill directories for both Codex and Claude installs."""
    env_multi = os.environ.get("SKILL_DIRS")
    if env_multi:
        return [
            Path(item).expanduser().resolve()
            for item in env_multi.split(os.pathsep)
            if item.strip()
        ]

    env_single = os.environ.get("SKILL_DIR")
    if env_single:
        return [Path(env_single).expanduser().resolve()]

    return [
        Path("~/.codex/skills/simulink-toolbox").expanduser().resolve(),
        Path("~/.claude/skills/simulink-toolbox").expanduser().resolve(),
    ]


def _load_public_tool_names() -> list[str]:
    """Import PUBLIC_TOOLS from engine.mcp_server and return function names."""
    # FastMCP tries to bind to a port during import only if __main__ runs it.
    # The module-level import is safe; we just need the list attribute.
    try:
        from engine.mcp_server import PUBLIC_TOOLS  # noqa: PLC0415
    except ImportError as exc:
        print(f"ERROR: could not import engine.mcp_server: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    return [fn.__name__ for fn in PUBLIC_TOOLS]


def _build_index(tool_names: list[str]) -> dict:
    """Build the generic simulink-toolbox index from public tool names.

    The installed skill is shared across projects, so the generated inventory
    intentionally excludes this repository's harness, training, and VSG bridge
    tools even though those tools remain public in this MCP server.
    """
    simulink_tools = []
    skipped_project_tools = []

    for name in tool_names:
        if name in _PROJECT_ONLY_TOOLS:
            skipped_project_tools.append(name)
            continue
        if name.startswith(("harness_", "training_")):
            skipped_project_tools.append(name)
            continue
        if name.startswith("simulink_"):
            meta = _SIMULINK_META.get(name, {})
            entry: dict[str, str] = {"name": name}
            if "group" in meta:
                entry["group"] = meta["group"]
            entry["description"] = meta.get("description", "")
            simulink_tools.append(entry)
        else:
            print(f"WARNING: unclassified tool skipped: {name}", file=sys.stderr)

    return {
        "meta": {
            "source": "generated from mcp_server.PUBLIC_TOOLS filtered for generic simulink-toolbox use",
            "note": (
                "This file is the L0 authority for the generic installed skill inventory. "
                "It intentionally excludes project-specific harness, training, and VSG bridge tools. "
                "Regenerate with: python scripts/regen_skill_index.py"
            ),
            "excluded_project_tools": skipped_project_tools,
        },
        "simulink_tools": simulink_tools,
        "summary": {
            "simulink_count": len(simulink_tools),
            "total": len(simulink_tools),
        },
    }


def _serialize(data: dict[str, Any]) -> str:
    """Serialize index data to JSON string (2-space indent, trailing newline)."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _run_check(index_path: Path, generated: str) -> int:
    """Compare generated JSON to on-disk file. Return 0 if identical, 1 if different."""
    if not index_path.exists():
        print(f"ERROR: {index_path} does not exist. Run without --check to create it.", file=sys.stderr)
        return 1

    raw = index_path.read_text(encoding="utf-8")
    try:
        # Normalize key order by round-tripping through parse+re-serialize so that
        # insertion-order differences from older script versions don't cause false failures.
        normalized = _serialize(json.loads(raw))
    except json.JSONDecodeError as exc:
        print(f"ERROR: {index_path} contains invalid JSON: {exc}", file=sys.stderr)
        return 1

    if normalized == generated:
        print(f"OK: {index_path} is consistent with PUBLIC_TOOLS.")
        return 0

    # Show a simple line-by-line diff
    diff = list(difflib.unified_diff(
        normalized.splitlines(keepends=True),
        generated.splitlines(keepends=True),
        fromfile="index.json (on-disk)",
        tofile="index.json (generated)",
    ))
    print("DIFF: index.json is OUT OF SYNC with PUBLIC_TOOLS.")
    print("Run `python scripts/regen_skill_index.py` to fix.")
    print("".join(diff))
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate generic simulink-toolbox index.json files from PUBLIC_TOOLS."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare generated output to on-disk index.json; exit 0 if identical.",
    )
    args = parser.parse_args(argv)

    tool_names = _load_public_tool_names()
    index_data = _build_index(tool_names)
    generated = _serialize(index_data)

    skill_dirs = _get_skill_dirs()

    if args.check:
        exit_code = 0
        for skill_dir in skill_dirs:
            index_path = skill_dir / "index.json"
            result = _run_check(index_path, generated)
            if result != 0:
                exit_code = result
        return exit_code

    # Default: overwrite all targets
    for skill_dir in skill_dirs:
        index_path = skill_dir / "index.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(generated, encoding="utf-8")
        print(f"Written {index_path} ({index_data['summary']['total']} tools total).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
