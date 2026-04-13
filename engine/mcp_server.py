"""engine/mcp_server.py - Python MCP server for structured Simulink access.

Registers a curated set of ~25 workflow-level tools for Claude.
Lower-level helpers remain importable from mcp_simulink_tools but are NOT
exposed to the model, reducing tool-selection confusion.

Run via claude_desktop_config.json:
    "command": "C:\\...\\python.exe",
    "args": ["C:\\...\\engine\\mcp_server.py"]
    "env": {"PYTHONPATH": "C:\\...\\Multi-Agent  VSGs"}
"""

import sys
import os

# Ensure project root is on path when invoked as a subprocess
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def _prepare_process_environment() -> str:
    """Align subprocess cwd with the project root for relative-file behavior."""
    os.chdir(_project_root)
    return _project_root


from fastmcp import FastMCP
from engine.harness_tasks import (
    harness_model_diagnose,
    harness_model_inspect,
    harness_model_patch_verify,
    harness_model_report,
    harness_scenario_status,
    harness_train_smoke_start,
    harness_train_smoke_poll,
)
from engine.mcp_simulink_tools import (
    # --- Model lifecycle (4) ---
    simulink_load_model,
    simulink_create_model,
    simulink_close_model,
    simulink_loaded_models,
    # --- Training state (1) ---
    simulink_bridge_status,          # inspect active SimulinkBridge runtime state
    # --- Structure viewing (4) ---
    simulink_get_block_tree,
    simulink_describe_block_ports,
    simulink_trace_port_connections,
    simulink_explore_block,          # 1-call block exploration: ports + connected_block_paths
    # --- Parameter operations (4) ---
    simulink_query_params,          # merged: get_block_params + get_multiple + bulk_get
    simulink_set_block_params,
    simulink_check_params,
    simulink_preflight,
    # --- Modeling operations (5) ---
    simulink_add_block,
    simulink_add_subsystem,
    simulink_connect_ports,         # merged: connect_blocks + add_line_branch + add_line_by_handles
    simulink_delete_block,          # merged: delete_block + delete_block_with_connections
    simulink_build_chain,
    # --- Diagnostics (3) ---
    simulink_compile_diagnostics,
    simulink_step_diagnostics,
    simulink_solver_audit,
    # --- Advanced (1) ---
    simulink_patch_and_verify,
    # --- Escape hatch (1) ---
    simulink_run_script,
    # --- Visual capture (2) ---
    simulink_screenshot,
    simulink_capture_figure,
)

mcp = FastMCP(
    "simulink-tools",
    instructions=(
        "Structured Simulink model inspection and execution (~25 tools). "
        "Prefer the harness_* task tools for Kundur/NE39 Simulink workflows. "
        "Use simulink_preflight to discover block parameters before placing. "
        "Use simulink_run_script to run build scripts or set_param operations "
        "(prefix output lines with 'RESULT: ' to surface them in important_lines). "
        "Use simulink_query_params for reading params (1 or N blocks, all or selected params). "
        "Use simulink_connect_ports for all connection operations (name or handle addressing). "
        "Use simulink_explore_block to get ports + all connections of one block in a single call "
        "(replaces describe_block_ports + multiple trace_port_connections round-trips). "
        "All tools share one MATLAB engine (lazy-started on first call, ~20s cold start)."
    ),
)

PUBLIC_TOOLS = [
    harness_scenario_status,
    harness_model_inspect,
    harness_model_patch_verify,
    harness_model_diagnose,
    harness_model_report,
    harness_train_smoke_start,
    harness_train_smoke_poll,
    simulink_load_model,
    simulink_create_model,
    simulink_close_model,
    simulink_loaded_models,
    simulink_bridge_status,
    simulink_get_block_tree,
    simulink_describe_block_ports,
    simulink_trace_port_connections,
    simulink_explore_block,
    simulink_query_params,
    simulink_set_block_params,
    simulink_check_params,
    simulink_preflight,
    simulink_add_block,
    simulink_add_subsystem,
    simulink_connect_ports,
    simulink_delete_block,
    simulink_build_chain,
    simulink_compile_diagnostics,
    simulink_step_diagnostics,
    simulink_solver_audit,
    simulink_patch_and_verify,
    simulink_run_script,
    simulink_screenshot,
    simulink_capture_figure,
]

for tool in PUBLIC_TOOLS:
    mcp.add_tool(tool)

if __name__ == "__main__":
    _prepare_process_environment()
    mcp.run()
