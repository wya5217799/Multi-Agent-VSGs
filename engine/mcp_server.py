"""engine/mcp_server.py - Python MCP server for structured Simulink and training access.

Registers a curated set of 43 workflow-level tools for Claude:
  - 4  training_* tools  (Training Monitor: status + diagnose; Training Control: evaluate_run + compare_runs)
  - 8  harness_*  tools  (Model Control: scenario/inspect/patch/diagnose/report/smoke/smoke_full)
  - 31 simulink_* tools  (model building, parameter ops, diagnostics, runtime, signals, visual capture)

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
    harness_train_smoke_minimal,
    harness_train_smoke_start,
    harness_train_smoke_poll,
)
from engine.training_tasks import (
    training_status,
    training_diagnose,
    training_evaluate_run,
    training_compare_runs,
)
from engine.mcp_simulink_tools import (
    # --- Model lifecycle (4) ---
    simulink_load_model,
    simulink_create_model,
    simulink_close_model,
    simulink_loaded_models,
    # --- Save / status (2) ---
    simulink_model_status,
    simulink_save_model,
    # --- Training state (1) ---
    simulink_bridge_status,          # inspect active SimulinkBridge runtime state
    # --- Structure viewing (4) ---
    simulink_get_block_tree,
    simulink_describe_block_ports,
    simulink_trace_port_connections,
    simulink_explore_block,          # 1-call block exploration: ports + source/sink blocks
    # --- Parameter operations (3) ---
    simulink_query_params,          # merged: get_block_params + get_multiple + bulk_get
    simulink_set_block_params,
    simulink_library_lookup,
    # --- Modeling operations (5) ---
    simulink_add_block,
    simulink_add_subsystem,
    simulink_connect_ports,         # merged: connect_blocks + add_line_branch + add_line_by_handles
    simulink_delete_block,          # merged: delete_block + delete_block_with_connections
    # --- Diagnostics (3) ---
    simulink_compile_diagnostics,
    simulink_step_diagnostics,
    simulink_solver_audit,
    # --- Advanced (3) ---
    simulink_patch_and_verify,
    simulink_block_workspace_dependency,  # Phase B: workspace var consumer xref
    simulink_powerlib_net_query,           # Phase D.1: powerlib electrical net member enumeration
    # --- Escape hatch (1) ---
    simulink_run_script,
    # --- Async run (2) ---
    simulink_run_script_async,
    simulink_poll_script,
    # --- Visual capture (2) ---
    simulink_screenshot,
    simulink_capture_figure,
    # --- General runtime (4) ---
    simulink_workspace_set,
    simulink_run_window,
    simulink_runtime_reset,
    simulink_signal_snapshot,
)

mcp = FastMCP(
    "simulink-tools",
    instructions=(
        "Structured Simulink and training control tools (45 total). "
        "Use training_status to poll live training progress (Tier 1). "
        "Use training_diagnose only when training_status shows anomaly/failure (Tier 2). "
        "Use training_evaluate_run / training_compare_runs for post-run Training Control workflows. "
        "Use simulink_library_lookup to discover block parameters before placing. "
        "Use simulink_run_script to run build scripts or set_param operations "
        "(prefix output lines with 'RESULT: ' to surface them in important_lines). "
        "Use simulink_query_params for reading params (1 or N blocks, all or selected params). "
        "Use simulink_connect_ports for all connection operations (name addressing only). "
        "Use simulink_explore_block to get ports + source/sink connections of one block in a single call "
        "(replaces describe_block_ports + multiple trace_port_connections round-trips). "
        "Use simulink_model_status before saving or closing a model when dirty state matters. "
        "Use simulink_signal_snapshot for logged/ToWorkspace/block-output values at one time point. "
        "Use simulink_workspace_set and simulink_run_window for general runtime control. "
        "For project-specific workflows (harness, training) see AGENTS.md. "
        "All tools share one MATLAB engine (lazy-started on first call, ~20s cold start)."
    ),
)

PUBLIC_TOOLS = [
    # --- Training Monitor (2) ---
    training_status,
    training_diagnose,
    # --- Training Control (2) ---
    training_evaluate_run,
    training_compare_runs,
    # --- Model Control harness (8) ---
    harness_scenario_status,
    harness_model_inspect,
    harness_model_patch_verify,
    harness_model_diagnose,
    harness_model_report,
    harness_train_smoke_minimal,
    harness_train_smoke_start,
    harness_train_smoke_poll,
    # --- Model lifecycle ---
    simulink_load_model,
    simulink_create_model,
    simulink_close_model,
    simulink_loaded_models,
    # --- Save / status ---
    simulink_model_status,
    simulink_save_model,
    # --- Training state ---
    simulink_bridge_status,
    # --- Structure viewing ---
    simulink_get_block_tree,
    simulink_describe_block_ports,
    simulink_trace_port_connections,
    simulink_explore_block,
    # --- Parameter operations ---
    simulink_query_params,
    simulink_set_block_params,
    simulink_library_lookup,
    # --- Modeling operations ---
    simulink_add_block,
    simulink_add_subsystem,
    simulink_connect_ports,
    simulink_delete_block,
    # --- Diagnostics ---
    simulink_compile_diagnostics,
    simulink_step_diagnostics,
    simulink_solver_audit,
    # --- Advanced ---
    simulink_patch_and_verify,
    simulink_block_workspace_dependency,
    simulink_powerlib_net_query,
    # --- Escape hatch ---
    simulink_run_script,
    # --- Async run ---
    simulink_run_script_async,
    simulink_poll_script,
    # --- Visual capture ---
    simulink_screenshot,
    simulink_capture_figure,
    # --- General runtime ---
    simulink_workspace_set,
    simulink_run_window,
    simulink_runtime_reset,
    simulink_signal_snapshot,
]

for tool in PUBLIC_TOOLS:
    mcp.add_tool(tool)

if __name__ == "__main__":
    _prepare_process_environment()
    mcp.run()
