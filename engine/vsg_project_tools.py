# engine/vsg_project_tools.py
"""Project-specific VSG build helpers for the Yang et al. TPWRS 2023 reproduction.

These tools are NOT part of the generic Simulink MCP toolbox.
They encode Kundur/NE39 model conventions and belong here, not in mcp_simulink_tools.py.
"""

from __future__ import annotations

from pydantic import BeforeValidator

from engine.matlab_session import MatlabSession
from engine.mcp_simulink_tools import _ensure_model_bootstrapped, _to_list, _IntArg, _BoolArg


def vsg_build_stub(
    model_name: str,
    count: _IntArg,
    start_index: _IntArg = 1,
    subsystem_prefix: str = "VSG_ES",
    system_path: str | None = None,
    add_workspace_logs: _BoolArg = True,
    add_measurement_outports: _BoolArg = True,
) -> dict:
    """Build project-aligned VSG stub subsystems for this repository.

    Generated block naming follows the current bridge convention:
      - subsystems: VSG_ES{i}
      - constants: M0 / D0 with Value=M0_val_ES{i} / D0_val_ES{i}

    Workspace logs intentionally use stub-specific names to avoid being
    mistaken for production bridge signals.
    """
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    parent_system = system_path or loaded_model_name
    summary = session.call(
        "vsg_build_vsg_stub",
        parent_system,
        int(count),
        int(start_index),
        subsystem_prefix,
        bool(add_workspace_logs),
        bool(add_measurement_outports),
        nargout=1,
    )
    return {
        "ok": bool(summary.get("ok", False)),
        "system_path": str(summary.get("system_path", parent_system)),
        "subsystems": _to_list(summary.get("subsystems", [])),
        "important_lines": _to_list(summary.get("important_lines", [])),
        "error_message": str(summary.get("error_message", "")),
    }
