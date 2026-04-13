# engine/mcp_simulink_tools.py
"""Layer 3b: MCP Simulink Tools — Claude perception of Simulink models.

These functions are designed to be registered as MCP tool endpoints,
giving Claude direct access to Simulink model structure during conversations.
All tools share the same MATLAB engine via MatlabSession.get().
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Annotated, Any

from pydantic import BeforeValidator

from engine.exceptions import MatlabCallError
from engine.matlab_session import MatlabSession

logger = logging.getLogger(__name__)

_WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
# Module-level name kept for test inspection only.  Actual per-session cache
# lives on the MatlabSession instance as _bootstrapped (set[str]) so it is
# automatically invalidated when MatlabSession._instances.clear() is called.
_BOOTSTRAPPED: set[str] = set()  # never populated; kept so tests can assert the name exists

# Async script job registry — keyed by job_id (8-char hex).
# Jobs are lost on MCP server restart (MATLAB engine is in-process).
_SCRIPT_JOBS: dict[str, dict[str, Any]] = {}
_SCRIPT_JOB_LOCK = threading.Lock()
_MATLAB_MODEL_REF_RE = re.compile(
    r"(?:get_param|set_param|sim|open_system|close_system|bdIsLoaded|find_system)\s*\(\s*'([^']+)'",
    re.IGNORECASE,
)

# MCP clients (including Claude Code) serialize all <parameter> values as JSON
# strings regardless of schema type. These validators coerce strings before
# Pydantic's strict type check fires.
_IntArg = Annotated[int, BeforeValidator(lambda v: int(v) if isinstance(v, str) else v)]
_BoolArg = Annotated[bool, BeforeValidator(lambda v: v.lower() in ("1", "true", "yes") if isinstance(v, str) else v)]
_ParamNamesArg = Annotated[
    list[str] | str | None,
    BeforeValidator(lambda v: [v] if isinstance(v, str) else v),
]


def simulink_inspect_model(
    model_name: str,
    depth: _IntArg = 3,
    max_blocks: _IntArg = 60,
    include_params: _BoolArg = False,
    subsystem_prefix: str | None = None,
) -> dict:
    """Inspect Simulink model structure: blocks, types, params, signals.

    Args:
        model_name: Simulink model name (without .slx extension)
        depth: Search depth for block discovery (default 3)
        max_blocks: Maximum blocks to return in detail (default 60); full count still reported
        include_params: Include key_params per block (default False — use
            simulink_query_params for per-block params to avoid token overflow)
        subsystem_prefix: Only return blocks whose path starts with this string
            (e.g. 'kundur_vsg/VSG_ES1'). Useful for large models to avoid token overflow.

    Returns:
        dict with block_count (total), filtered_count (after prefix filter),
        blocks (truncated to max_blocks), signal_count, subsystems, truncated (bool)
    """
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    info = session.call("vsg_inspect_model", loaded_model_name, float(depth))
    all_blocks = _convert_blocks(info["blocks"])
    if subsystem_prefix:
        all_blocks = [b for b in all_blocks if b["path"].startswith(subsystem_prefix)]
    if not include_params:
        all_blocks = [{"path": b["path"], "type": b["type"], "name": b["name"]} for b in all_blocks]
    truncated = len(all_blocks) > max_blocks
    return {
        "block_count": int(info["block_count"]),
        "filtered_count": len(all_blocks),
        "blocks": all_blocks[:max_blocks],
        "signal_count": int(info["signal_count"]),
        "subsystems": _to_list(info["subsystems"]),
        "truncated": truncated,
    }



def simulink_trace_signal(model_name: str, signal_name: str) -> dict:
    """Trace a signal from source to all sinks.

    Args:
        model_name: Simulink model name
        signal_name: Signal/port name to trace

    Returns:
        dict with source (str), sinks (list[str])
    """
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    path = session.call("vsg_trace_signal", loaded_model_name, signal_name)
    return {
        "source": str(path["source"]),
        "sinks": _to_list(path["sinks"]),
    }


def simulink_get_block_tree(
    model_name: str, root_path: str | None = None, max_depth: _IntArg = 3
) -> dict:
    """Get hierarchical block tree from a model or subsystem.

    Args:
        model_name: Simulink model name
        root_path: Starting path (default: model root)
        max_depth: Maximum tree depth (default 3)

    Returns:
        Nested dict with name, type, path, children
    """
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    if root_path is None:
        tree = session.call("vsg_get_block_tree", loaded_model_name, loaded_model_name, float(max_depth))
    else:
        tree = session.call("vsg_get_block_tree", loaded_model_name, root_path, float(max_depth))
    return _convert_tree(tree)


def simulink_get_block_params(model_name: str, block_path: str) -> dict:
    """Query all dialog parameters of a specific block.

    .. deprecated::
        Use :func:`simulink_query_params` instead (unified replacement).


    Args:
        model_name: Simulink model name
        block_path: Full block path (e.g. 'kundur_vsg/VSG_ES1/M0')

    Returns:
        dict of parameter name -> value (dialog params only, all in one IPC call)
    """
    import warnings
    warnings.warn(
        "simulink_get_block_params is deprecated; use simulink_query_params instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    # Route through the MATLAB helper instead of building an inline eval(...)
    # string. This is more robust on Windows and avoids parser/encoding issues
    # seen in real MATLAB Engine calls.
    raw = session.call("vsg_batch_query", loaded_model_name, [block_path], nargout=1)
    if isinstance(raw, list):
        raw = raw[0] if raw else {}
    if not isinstance(raw, dict):
        return {}
    if raw.get("error"):
        return {"__error__": str(raw["error"])}

    params_raw = raw.get("params", {})
    if not isinstance(params_raw, dict):
        return {}

    params = {}
    for k, v in params_raw.items():
        try:
            params[str(k)] = v if isinstance(v, str) else str(v)
        except Exception:
            params[str(k)] = "<unconvertible>"
    return params


def simulink_get_multiple_block_params(model_name: str, block_paths: list[str]) -> dict:
    """Query dialog parameters for multiple blocks in one MATLAB call.

    .. deprecated::
        Use :func:`simulink_query_params` instead (unified replacement).
    """
    import warnings
    warnings.warn(
        "simulink_get_multiple_block_params is deprecated; use simulink_query_params instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    raw = session.call("vsg_batch_query_cell", loaded_model_name, block_paths, nargout=1)
    items = []
    for row in _to_list(raw):
        if not isinstance(row, dict):
            continue
        params_raw = row.get("params", {})
        params = (
            {str(k): str(v) for k, v in params_raw.items()}
            if isinstance(params_raw, dict) else {}
        )
        items.append({
            "block_path": str(row.get("block", "")),
            "params": params,
            "error": str(row.get("error", "")),
        })
    return {"items": items}


def simulink_load_model(model_name: str) -> dict:
    """Load a Simulink model into the shared MATLAB engine."""
    session = MatlabSession.get()
    load_target, loaded_model_name, bootstrap_paths = _resolve_model_load_target(model_name)
    _ensure_model_bootstrapped(session, model_name)
    return {
        "ok": True,
        "model_name": loaded_model_name,
        "load_target": load_target,
        "bootstrap_paths": bootstrap_paths,
        "loaded_models": simulink_loaded_models(),
    }


def simulink_create_model(model_name: str, open_model: _BoolArg = True) -> dict:
    """Create a new unsaved Simulink model in the shared MATLAB engine."""
    session = MatlabSession.get()
    summary = session.call("vsg_create_model", model_name, bool(open_model), nargout=1)
    return {
        "ok": bool(summary.get("ok", False)),
        "model_name": str(summary.get("model_name", model_name)),
        "loaded_models": simulink_loaded_models() if bool(summary.get("ok", False)) else [],
        "important_lines": _to_list(summary.get("important_lines", [])),
        "error_message": str(summary.get("error_message", "")),
    }


def simulink_close_model(model_name: str, save: _BoolArg = False) -> dict:
    """Close a Simulink model in the shared MATLAB engine."""
    session = MatlabSession.get()
    if bool(save):
        session.call("save_system", model_name, nargout=0)
    session.call("vsg_close_model", model_name, nargout=0)
    return {
        "ok": True,
        "model_name": model_name,
        "loaded_models": simulink_loaded_models(),
    }


def simulink_set_block_params(model_name: str, block_path: str, params: dict[str, str]) -> dict:
    """Set one or more dialog parameters on a block with structured output."""
    session = MatlabSession.get()
    _ensure_model_bootstrapped(session, model_name)
    summary = session.call("vsg_set_block_params", block_path, params, nargout=1)
    return {
        "ok": bool(summary.get("ok", False)),
        "block_path": str(summary.get("block_path", block_path)),
        "params_written": int(summary.get("params_written", 0)),
        "important_lines": _to_list(summary.get("important_lines", [])),
        "error_message": str(summary.get("error_message", "")),
    }


def simulink_add_block(
    model_name: str,
    source_block: str,
    destination_block: str,
    params: dict[str, str] | None = None,
    make_name_unique: _BoolArg = True,
) -> dict:
    """Add a block into a model using a full block path destination.

    Args:
        model_name: Simulink model name
        source_block: Library block path (for example 'simulink/Math Operations/Gain')
        destination_block: Full block path inside the model
            (for example 'mdl/Sub1/Gain1')
        params: Optional dialog parameters to apply after placement
        make_name_unique: Whether Simulink may uniquify the destination name
    """
    _validate_destination_block_path(model_name, destination_block)
    session = MatlabSession.get()
    _ensure_model_bootstrapped(session, model_name)
    summary = session.call(
        "vsg_add_block",
        source_block,
        destination_block,
        params or {},
        bool(make_name_unique),
        nargout=1,
    )
    return {
        "ok": bool(summary.get("ok", False)),
        "block_path": str(summary.get("block_path", destination_block)),
        "important_lines": _to_list(summary.get("important_lines", [])),
        "error_message": str(summary.get("error_message", "")),
    }


def simulink_delete_block(
    model_name: str,
    block_path: str,
    delete_attached_lines: _BoolArg = True,
) -> dict:
    """Delete a block from a model, optionally removing attached lines first.

    Args:
        model_name: Simulink model name
        block_path: Full block path
        delete_attached_lines: Remove lines connected to the block before
            deleting (default True). Set False only if lines are already gone.

    Returns:
        dict with ok, block_path, deleted_lines (if applicable), error_message
    """
    session = MatlabSession.get()
    _ensure_model_bootstrapped(session, model_name)
    if bool(delete_attached_lines):
        raw = session.call(
            "vsg_delete_block_with_connections",
            model_name,
            block_path,
            True,
            nargout=1,
        )
        return {
            "ok": bool(raw.get("ok", False)),
            "block_path": str(raw.get("block_path", block_path)),
            "deleted_lines": [_to_int(x) for x in _to_list(raw.get("deleted_lines", [])) if _to_int(x) > 0],
            "error_message": str(raw.get("error_message", "")),
        }
    else:
        summary = session.call("vsg_delete_block", block_path, nargout=1)
        return {
            "ok": bool(summary.get("ok", False)),
            "block_path": str(summary.get("block_path", block_path)),
            "deleted_lines": [],
            "important_lines": _to_list(summary.get("important_lines", [])),
            "error_message": str(summary.get("error_message", "")),
        }


def simulink_connect_blocks(
    model_name: str,
    source_port: str,
    destination_port: str,
    autorouting: _BoolArg = True,
    system_path: str | None = None,
) -> dict:
    """Connect two block ports using add_line."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    target_system = system_path or loaded_model_name
    summary = session.call(
        "vsg_connect_blocks",
        target_system,
        source_port,
        destination_port,
        bool(autorouting),
        nargout=1,
    )
    return {
        "ok": bool(summary.get("ok", False)),
        "important_lines": _to_list(summary.get("important_lines", [])),
        "error_message": str(summary.get("error_message", "")),
    }


def simulink_update_diagram(model_name: str) -> dict:
    """Trigger a model update/compile refresh."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    summary = session.call("vsg_update_diagram", loaded_model_name, nargout=1)
    return {
        "ok": bool(summary.get("ok", False)),
        "important_lines": _to_list(summary.get("important_lines", [])),
        "error_message": str(summary.get("error_message", "")),
    }


def simulink_delete_line(
    model_name: str,
    source_port: str,
    destination_port: str,
    system_path: str | None = None,
) -> dict:
    """Delete a signal line between two ports."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    target_system = system_path or loaded_model_name
    summary = session.call(
        "vsg_delete_line",
        target_system,
        source_port,
        destination_port,
        nargout=1,
    )
    return {
        "ok": bool(summary.get("ok", False)),
        "important_lines": _to_list(summary.get("important_lines", [])),
        "error_message": str(summary.get("error_message", "")),
    }


def simulink_add_line_branch(
    model_name: str,
    source_port: str,
    destination_port: str,
    autorouting: _BoolArg = True,
    system_path: str | None = None,
) -> dict:
    """Add a branch line from an existing source port to another destination."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    target_system = system_path or loaded_model_name
    summary = session.call(
        "vsg_add_line_branch",
        target_system,
        source_port,
        destination_port,
        bool(autorouting),
        nargout=1,
    )
    return {
        "ok": bool(summary.get("ok", False)),
        "important_lines": _to_list(summary.get("important_lines", [])),
        "error_message": str(summary.get("error_message", "")),
    }


def simulink_add_annotation(model_name: str, text: str, position: list[int] | None = None) -> dict:
    """Add a model annotation with optional position."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    summary = session.call(
        "vsg_add_annotation",
        loaded_model_name,
        text,
        position or [],
        nargout=1,
    )
    return {
        "ok": bool(summary.get("ok", False)),
        "important_lines": _to_list(summary.get("important_lines", [])),
        "error_message": str(summary.get("error_message", "")),
    }


def simulink_set_block_position(model_name: str, block_path: str, position: list[int]) -> dict:
    """Set a block position [left, top, right, bottom]."""
    session = MatlabSession.get()
    _ensure_model_bootstrapped(session, model_name)
    summary = session.call(
        "vsg_set_block_position",
        block_path,
        position,
        nargout=1,
    )
    return {
        "ok": bool(summary.get("ok", False)),
        "block_path": str(summary.get("block_path", block_path)),
        "important_lines": _to_list(summary.get("important_lines", [])),
        "error_message": str(summary.get("error_message", "")),
    }


def simulink_add_subsystem(
    model_name: str,
    subsystem_path: str,
    position: list[int] | None = None,
    make_name_unique: _BoolArg = True,
) -> dict:
    """Add a blank subsystem block to a model."""
    session = MatlabSession.get()
    _ensure_model_bootstrapped(session, model_name)
    summary = session.call(
        "vsg_add_subsystem",
        subsystem_path,
        position or [],
        bool(make_name_unique),
        nargout=1,
    )
    return {
        "ok": bool(summary.get("ok", False)),
        "block_path": str(summary.get("block_path", subsystem_path)),
        "important_lines": _to_list(summary.get("important_lines", [])),
        "error_message": str(summary.get("error_message", "")),
    }


def simulink_open_system(system_path: str) -> dict:
    """Open a model or subsystem in the shared MATLAB session."""
    session = MatlabSession.get()
    _ensure_model_bootstrapped(session, str(system_path).split("/")[0])
    summary = session.call("vsg_open_system", system_path, nargout=1)
    return {
        "ok": bool(summary.get("ok", False)),
        "system_path": str(summary.get("system_path", system_path)),
        "important_lines": _to_list(summary.get("important_lines", [])),
        "error_message": str(summary.get("error_message", "")),
    }


def simulink_list_ports(system_path: str) -> dict:
    """List child inports/outports of a subsystem or top-level model."""
    session = MatlabSession.get()
    _ensure_model_bootstrapped(session, str(system_path).split("/")[0])
    result = session.call("vsg_list_ports", system_path, nargout=1)
    return {
        "system_path": str(result.get("system_path", system_path)),
        "inports": _to_list(result.get("inports", [])),
        "outports": _to_list(result.get("outports", [])),
    }


def simulink_autolayout_subsystem(system_path: str) -> dict:
    """Run Simulink autolayout on a model or subsystem."""
    session = MatlabSession.get()
    _ensure_model_bootstrapped(session, str(system_path).split("/")[0])
    summary = session.call("vsg_autolayout_subsystem", system_path, nargout=1)
    return {
        "ok": bool(summary.get("ok", False)),
        "system_path": str(summary.get("system_path", system_path)),
        "important_lines": _to_list(summary.get("important_lines", [])),
        "error_message": str(summary.get("error_message", "")),
    }


def simulink_build_chain(
    model_name: str,
    system_path: str,
    blocks: list[dict[str, Any]],
    start_port: str | None = None,
    end_port: str | None = None,
    autorouting: _BoolArg = True,
    autolayout: _BoolArg = True,
) -> dict:
    """Build a linear chain of blocks inside a model/subsystem.

    Each block item supports:
      - source_block: library path
      - name: destination block name inside system_path
      - params: optional dict[str, str]
      - position: optional [l, t, r, b]
      - input_port: optional port name/number, default '1'
      - output_port: optional port name/number, default '1'
    """
    session = MatlabSession.get()
    _ensure_model_bootstrapped(session, model_name)
    summary = session.call(
        "vsg_build_chain",
        system_path,
        blocks,
        start_port or "",
        end_port or "",
        bool(autorouting),
        bool(autolayout),
        nargout=1,
    )
    return {
        "ok": bool(summary.get("ok", False)),
        "system_path": str(summary.get("system_path", system_path)),
        "blocks_added": _to_list(summary.get("blocks_added", [])),
        "important_lines": _to_list(summary.get("important_lines", [])),
        "error_message": str(summary.get("error_message", "")),
    }


def simulink_build_signal_chain(
    model_name: str,
    system_path: str,
    names: list[str],
    source_blocks: list[str],
    params_list: list[dict[str, Any]] | None = None,
    start_port: str | None = None,
    end_port: str | None = None,
    autolayout: _BoolArg = True,
) -> dict:
    """Convenience wrapper for building a signal-domain linear chain."""
    blocks = []
    params_list = params_list or []
    for i, (name, source_block) in enumerate(zip(names, source_blocks)):
        params = params_list[i] if i < len(params_list) else {}
        blocks.append({
            "name": name,
            "source_block": source_block,
            "params": params,
        })
    return simulink_build_chain(
        model_name=model_name,
        system_path=system_path,
        blocks=blocks,
        start_port=start_port,
        end_port=end_port,
        autorouting=True,
        autolayout=autolayout,
    )


def simulink_clone_subsystem_n_times(
    model_name: str,
    source_subsystem_path: str,
    destination_prefix: str,
    count: _IntArg,
    start_index: _IntArg = 1,
    position_offset: list[int] | None = None,
) -> dict:
    """Clone a subsystem multiple times with numbered names."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    summary = session.call(
        "vsg_clone_subsystem_n_times",
        source_subsystem_path,
        destination_prefix,
        int(count),
        int(start_index),
        position_offset or [],
        nargout=1,
    )
    return {
        "ok": bool(summary.get("ok", False)),
        "clones": _to_list(summary.get("clones", [])),
        "important_lines": _to_list(summary.get("important_lines", [])),
        "error_message": str(summary.get("error_message", "")),
    }


def simulink_build_vsg_stub(
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


def simulink_preflight(lib_name: str, block_display_name: str) -> dict:
    """Query parameters and ports of a library block without placing it in a model.

    Args:
        lib_name: Library name (e.g. 'ee_lib', 'simscape')
        block_display_name: Block display name (e.g. 'Transmission Line (Three-Phase)')

    Returns:
        dict with found (bool), handle (float), params_main (list), params_unit (list),
        defaults (dict of name->value), ports (list of dicts), error (str)
    """
    session = MatlabSession.get()
    result = session.call("vsg_preflight", lib_name, block_display_name, nargout=1)
    ports_raw = result.get("ports", [])
    ports = []
    for p in _to_list(ports_raw):
        if isinstance(p, dict):
            ports.append({
                "name":      str(p.get("name", "")),
                "label":     str(p.get("label", "")),
                "domain":    str(p.get("domain", "")),
                "port_type": str(p.get("port_type", "")),
            })
    defaults_raw = result.get("defaults", {})
    defaults = {str(k): str(v) for k, v in defaults_raw.items()} if isinstance(defaults_raw, dict) else {}
    return {
        "found":       bool(result.get("found", False)),
        "handle":      float(result.get("handle", 0)),
        "params_main": _to_list(result.get("params_main", [])),
        "params_unit": _to_list(result.get("params_unit", [])),
        "defaults":    defaults,
        "ports":       ports,
        "error":       str(result.get("error", "")),
    }


def simulink_run_script(code_or_file: str, timeout_sec: _IntArg = 120) -> dict:
    """Run a MATLAB script or code string with noise suppression.

    Wraps vsg_run_quiet: captures full stdout but only surfaces three categories
    of lines in ``important_lines``:
      1. Lines that start with (case-insensitive) "warning" or "error"
      2. Lines that *contain* "warning" or "error"
      3. Lines that start with "result" — i.e. the RESULT: prefix convention

    **Output capture convention** — to make your own disp/fprintf visible in
    ``important_lines``, prefix the line with ``RESULT:`` in your MATLAB code:
        fprintf('RESULT: block count = %d\\n', n);
        disp('RESULT: patch applied');
    Plain disp() / fprintf() output that does NOT match the patterns above is
    intentionally suppressed to keep MCP responses compact.

    Use for build scripts, set_param operations, and other side-effect operations.
    For purely exploratory queries (getting param values), prefer simulink_query_params.

    Args:
        code_or_file: MATLAB code string or script name (e.g. 'build_powerlib_kundur')
        timeout_sec: Engine-level timeout in seconds (default 120). Increase for large
            build scripts — e.g. 600 for NE39 full model build.

    Returns:
        dict with ok (bool), elapsed (float), n_warnings (int), n_errors (int),
        error_message (str), important_lines (list[str])
    """
    session = MatlabSession.get()
    for model_name in _extract_known_model_references(code_or_file):
        _ensure_model_bootstrapped(session, model_name)
    summary = session.call("vsg_run_quiet", code_or_file, nargout=1, timeout=timeout_sec)
    return {
        "ok":                bool(summary.get("ok", False)),
        "elapsed":           float(summary.get("elapsed", 0.0)),
        "n_warnings":        int(summary.get("n_warnings", 0)),
        "n_errors":          int(summary.get("n_errors", 0)),
        "error_message":     str(summary.get("error_message", "")),
        "important_lines":   _to_list(summary.get("important_lines", [])),
    }


def simulink_run_script_async(
    code_or_file: str,
    timeout_sec: _IntArg = 300,
) -> dict:
    """Start a MATLAB script in the background; returns immediately with a job_id.

    The MATLAB engine is single-threaded — only one async job can run at a time.
    Use :func:`simulink_poll_script` to check completion.

    Jobs are **not** preserved across MCP server restarts; if the server
    restarts while a script is running, re-submit the script.

    Args:
        code_or_file: MATLAB code string or script name (same as simulink_run_script).
        timeout_sec: Engine-level timeout in seconds (default 300). Increase for
            large build scripts — e.g. 600 for NE39 full model build.

    Returns:
        dict with ok (bool), job_id (str), status ("running" | "busy"),
        message (str).
    """
    with _SCRIPT_JOB_LOCK:
        running = [jid for jid, j in _SCRIPT_JOBS.items() if not j["done"]]
        if running:
            return {
                "ok": False,
                "job_id": "",
                "status": "busy",
                "error_message": (
                    f"A script is already running (job_id={running[0]!r}). "
                    "Poll it with simulink_poll_script first."
                ),
            }
        job_id = uuid.uuid4().hex[:8]
        job: dict[str, Any] = {
            "code_or_file": code_or_file,
            "timeout_sec": int(timeout_sec),
            "result": None,
            "done": False,
            "started_at": time.monotonic(),
        }
        _SCRIPT_JOBS[job_id] = job

    def _worker() -> None:
        try:
            job["result"] = simulink_run_script(code_or_file, int(timeout_sec))
        except Exception as exc:
            job["result"] = {
                "ok": False,
                "elapsed": 0.0,
                "n_warnings": 0,
                "n_errors": 1,
                "error_message": str(exc),
                "important_lines": [],
            }
        finally:
            job["done"] = True

    t = threading.Thread(target=_worker, daemon=True, name=f"slx_script_{job_id}")
    job["thread"] = t
    t.start()

    return {
        "ok": True,
        "job_id": job_id,
        "status": "running",
        "message": (
            f"Script started in background (job_id={job_id!r}). "
            f"Use simulink_poll_script(job_id={job_id!r}) to check completion."
        ),
    }


def simulink_poll_script(job_id: str) -> dict:
    """Poll whether a background script job has completed.

    Args:
        job_id: The job_id returned by simulink_run_script_async.

    Returns:
        dict with ok (bool), job_id (str), status ("running" | "done" | "not_found"),
        elapsed_sec (float), and on completion: n_warnings, n_errors, error_message,
        important_lines (mirrors simulink_run_script output).
    """
    job = _SCRIPT_JOBS.get(job_id)
    if job is None:
        return {
            "ok": False,
            "job_id": job_id,
            "status": "not_found",
            "elapsed_sec": 0.0,
            "error_message": (
                f"No job found for job_id={job_id!r}. "
                "Jobs are lost on MCP server restart — re-run the script if needed."
            ),
        }

    elapsed = round(time.monotonic() - job["started_at"], 1)

    if not job["done"]:
        return {
            "ok": True,
            "job_id": job_id,
            "status": "running",
            "elapsed_sec": elapsed,
            "message": "Script still running — poll again later.",
        }

    result: dict = job.get("result") or {}
    return {
        "ok": bool(result.get("ok", False)),
        "job_id": job_id,
        "status": "done",
        "elapsed_sec": elapsed,
        "n_warnings": int(result.get("n_warnings", 0)),
        "n_errors": int(result.get("n_errors", 0)),
        "error_message": str(result.get("error_message", "")),
        "important_lines": list(result.get("important_lines", [])),
    }


def simulink_check_params(model_name: str, depth: _IntArg = 5) -> dict:
    """Audit Simulink block parameters against physical ranges.

    Catches silent unit errors (e.g. L=1.41 when block expects mH/km not H/km).
    Must be called after every modeling session. Returns structured suspects list
    so the caller can decide whether to proceed or stop for confirmation.

    Coverage (frozen — only ee_lib blocks verified in R2025b):
        Transmission Line 3ph, Wye Load, RLC 3ph, Circuit Breaker 3ph, CVS, SwingEq constants.
        Uncovered blocks contribute to n_skipped, not false positives.

    Args:
        model_name: Simulink model name (without .slx extension)
        depth: Block scan depth (default 5)

    Returns:
        dict with passed (bool), n_checked, n_suspect, n_skipped,
        suspects (list of {block, param, value, actual_unit, expected_unit,
        expected_range, reason, hint})
    """
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    report = session.call("vsg_check_params", loaded_model_name, "depth", float(depth))
    suspects = []
    for s in _to_list(report.get("suspects", [])):
        if not isinstance(s, dict):
            continue
        val = s.get("value", 0)
        if hasattr(val, "__iter__") and not isinstance(val, str):
            val = list(val)
        else:
            try:
                val = float(val)
            except (TypeError, ValueError):
                val = str(val)
        suspects.append({
            "block":          str(s.get("block", "")),
            "param":          str(s.get("param", "")),
            "value":          val,
            "actual_unit":    str(s.get("actual_unit", "")),
            "expected_unit":  str(s.get("expected_unit", "")),
            "expected_range": _to_list(s.get("expected_range", [])),
            "reason":         str(s.get("reason", "")),
            "hint":           str(s.get("hint", "")),
        })
    n_suspect = int(report.get("n_suspect", 0))
    return {
        "passed":    n_suspect == 0,
        "n_checked": int(report.get("n_checked", 0)),
        "n_suspect": n_suspect,
        "n_skipped": int(report.get("n_skipped", 0)),
        "suspects":  suspects,
    }


def simulink_query_params(
    model_name: str,
    block_paths: list[str],
    param_names: _ParamNamesArg = None,
) -> dict:
    """Query parameters from one or more blocks in a single call.

    Unified replacement for get_block_params / get_multiple_block_params / bulk_get_params.

    Args:
        model_name: Simulink model name
        block_paths: List of block paths (use a single-element list for one block)
        param_names: Specific parameter names to read. None = all dialog params.

    Returns:
        dict with items: list of {block_path, params, error, missing_params}
    """
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    param_names = _normalize_param_names(param_names)

    if param_names is not None and len(param_names) > 0:
        # Selective params → use vsg_bulk_get_params
        raw = session.call("vsg_bulk_get_params", loaded_model_name, block_paths, param_names, nargout=1)
        return {"items": _convert_bulk_param_items(raw.get("items", []))}
    else:
        # All params → use vsg_batch_query.
        # MATLAB returns a scalar struct (dict) for a single block path and a
        # cell array (list) for multiple paths.  Normalise both to a list so the
        # loop below works in either case.
        raw = session.call("vsg_batch_query", loaded_model_name, block_paths, nargout=1)
        if isinstance(raw, dict):
            raw = [raw]  # scalar struct → 1-element list
        elif not isinstance(raw, list):
            raw = []     # unexpected type → emit no items rather than crash
        items = []
        for row in raw:
            if not isinstance(row, dict):
                continue
            params_raw = row.get("params", {})
            params = (
                {str(k): str(v) for k, v in params_raw.items()}
                if isinstance(params_raw, dict) else {}
            )
            items.append({
                "block_path": str(row.get("block", "")),
                "params": params,
                "error": str(row.get("error", "")),
                "missing_params": [],
            })
        return {"items": items}


def simulink_connect_ports(
    model_name: str,
    source_port: str,
    destination_port: str,
    addressing: str = "name",
    allow_branch: _BoolArg | None = None,
    autorouting: _BoolArg = True,
    system_path: str | None = None,
) -> dict:
    """Connect two ports using name-based or handle-based addressing.

    Unified replacement for connect_blocks / add_line_branch / add_line_by_handles.

    Args:
        model_name: Simulink model name
        source_port: Source port identifier. For name addressing, this must be
            relative to system_path (for example 'Const/1' or 'Sub/Const/1').
            For handle addressing, pass the numeric port handle.
        destination_port: Destination port identifier. For name addressing,
            this must be relative to system_path.
        addressing: "name" for relative 'Block/1' strings, "handle" for numeric
            port handles
        allow_branch: Allow branching from an already-connected source. When
            omitted, defaults to False for name addressing and True for handle
            addressing to preserve the previous handle-tool behavior.
        autorouting: Use Simulink autorouting (default True)
        system_path: Parent system path (default: model root). Use this together
            with name-mode ports relative to system_path rather than full
            'model/block/port' paths.

    Returns:
        dict with ok, error_message, line_handle (handle mode), created_branch, important_lines
    """
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    target_system = system_path or loaded_model_name
    normalized_addressing = str(addressing).strip().lower()
    if normalized_addressing not in {"name", "handle"}:
        raise ValueError("addressing must be 'name' or 'handle'")
    if allow_branch is None:
        allow_branch_value = normalized_addressing == "handle"
    else:
        allow_branch_value = bool(allow_branch)

    if normalized_addressing == "handle":
        raw = session.call(
            "vsg_add_line_by_handles",
            target_system,
            float(source_port),
            float(destination_port),
            allow_branch_value,
            bool(autorouting),
            nargout=1,
        )
        return {
            "ok": bool(raw.get("ok", False)),
            "line_handle": _to_int(raw.get("line_handle", 0)),
            "created_branch": bool(raw.get("created_branch", False)),
            "important_lines": _to_list(raw.get("important_lines", [])),
            "error_message": str(raw.get("error_message", "")),
        }
    else:
        _validate_relative_port_reference(model_name, target_system, source_port, "source_port")
        _validate_relative_port_reference(model_name, target_system, destination_port, "destination_port")
        # Name-based: use branch helper if allow_branch, else normal connect
        if allow_branch_value:
            raw = session.call(
                "vsg_add_line_branch",
                target_system,
                source_port,
                destination_port,
                bool(autorouting),
                nargout=1,
            )
        else:
            raw = session.call(
                "vsg_connect_blocks",
                target_system,
                source_port,
                destination_port,
                bool(autorouting),
                nargout=1,
            )
        return {
            "ok": bool(raw.get("ok", False)),
            "important_lines": _to_list(raw.get("important_lines", [])),
            "error_message": str(raw.get("error_message", "")),
        }


def simulink_list_models() -> list[str]:
    """List available .slx files in the project scenarios/ directories.

    Returns:
        List of model file paths found on disk
    """
    import glob
    import os

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    patterns = [
        os.path.join(project_root, "scenarios", "**", "*.slx"),
    ]
    models = []
    for pat in patterns:
        models.extend(glob.glob(pat, recursive=True))
    return models


def simulink_loaded_models() -> list[str]:
    """List Simulink models currently open in the MATLAB engine.

    Queries MATLAB's live block diagram registry — shows only models that
    are actually loaded, not just files on disk. Call this at the start of
    a debugging session to confirm which models are available before using
    inspect/params/tree tools.

    Returns:
        List of model names currently loaded in MATLAB (e.g. ['kundur_vsg'])
    """
    session = MatlabSession.get()
    result = session.eval("find_system('type', 'block_diagram')", nargout=1)
    return _to_list(result)


def simulink_bridge_status(model_name: str = "kundur_vsg") -> dict:
    """Return the runtime state of the active SimulinkBridge for a model.

    Useful during training to inspect the bridge's current time step, last
    feedback signals, and disturbance load configuration — without pausing
    training or reading log files.

    Args:
        model_name: Simulink model name (e.g. 'kundur_vsg', 'NE39bus_v2').
            Defaults to 'kundur_vsg'.

    Returns:
        dict with:
          active (bool): False if no bridge is registered for model_name
          model_name (str)
          t_current (float): simulation time at end of last step (s)
          n_agents (int)
          dt_control (float): control step size (s)
          Pe_prev (list|None): last measured Pe per agent (p.u.), None before first step
          delta_prev_deg (list|None): last rotor angle per agent (deg), None before first step
          tripload_state (dict): current disturbance load workspace vars (W)
          available_bridges (list[str]): all registered model names
    """
    from engine.simulink_bridge import get_active_bridge, list_active_bridges
    bridge = get_active_bridge(model_name)
    available = list_active_bridges()
    if bridge is None:
        return {
            "active": False,
            "model_name": model_name,
            "available_bridges": available,
        }
    return {
        "active":            True,
        "model_name":        model_name,
        "t_current":         bridge.t_current,
        "n_agents":          bridge.cfg.n_agents,
        "dt_control":        bridge.cfg.dt_control,
        "Pe_prev":           bridge._Pe_prev.tolist() if bridge._Pe_prev is not None else None,
        "delta_prev_deg":    bridge._delta_prev_deg.tolist() if bridge._delta_prev_deg is not None else None,
        "tripload_state":    dict(bridge._tripload_state),
        "available_bridges": available,
    }


def simulink_describe_block_ports(model_name: str, block_path: str) -> dict:
    """Describe block ports in stable order with connection metadata."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    raw = session.call("vsg_describe_block_ports", loaded_model_name, block_path, nargout=1)
    return {
        "block_path": str(raw.get("block_path", block_path)),
        "ports": _convert_port_descriptions(raw.get("ports", [])),
        "error_message": str(raw.get("error_message", "")),
    }


def simulink_trace_port_connections(
    model_name: str,
    block_path: str,
    port_kind: str,
    port_index: _IntArg,
) -> dict:
    """Trace the full line tree attached to a specific block port."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    raw = session.call(
        "vsg_trace_port_connections",
        loaded_model_name,
        block_path,
        port_kind,
        int(port_index),
        nargout=1,
    )
    return {
        "ok": bool(raw.get("ok", False)),
        "src": _convert_port_endpoint(raw.get("src", {})),
        "dsts": _convert_port_endpoints(raw.get("dsts", [])),
        "branch_count": int(raw.get("branch_count", 0)),
        "line_handle": _to_int(raw.get("line_handle", 0)),
        "all_connected_ports": _to_list(raw.get("all_connected_ports", [])),
        "error_message": str(raw.get("error_message", "")),
    }


def simulink_explore_block(
    model_name: str,
    block_path: str,
    trace_connections: _BoolArg = True,
) -> dict:
    """One-shot exploration of a block: ports + all connection targets.

    Single MATLAB IPC call — uses connected_block_paths already returned by
    vsg_describe_block_ports.  No separate trace-per-port round-trips needed.

    Args:
        model_name: Simulink model name (without .slx extension)
        block_path: Full block path to explore (e.g. 'kundur_vsg/VSG_ES1')
        trace_connections: Ignored (kept for API compatibility). Connection data
            is always included from the single vsg_describe_block_ports call.

    Returns:
        dict with:
          block_path (str)
          ports (list of dicts):
            - kind (str): "Inport" | "Outport" | "LConn" | "RConn" etc.
            - index (int): port index within that kind
            - handle (int): port handle
            - is_connected (bool): whether a line is attached
            - connections (list of dicts): [{block: str}] — connected block paths
          error_message (str)
    """
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)

    raw_ports = session.call("vsg_describe_block_ports", loaded_model_name, block_path, nargout=1)
    ports_desc = _convert_port_descriptions(raw_ports.get("ports", []))
    error_message = str(raw_ports.get("error_message", ""))

    # connected_block_paths is already populated by vsg_describe_block_ports —
    # no second MATLAB call needed.
    result_ports = []
    for port in ports_desc:
        connections = [
            {"block": str(bp)}
            for bp in port.get("connected_block_paths", [])
            if bp
        ]
        result_ports.append({
            "kind":         str(port.get("kind", "")),
            "index":        _to_int(port.get("index", 0)),
            "handle":       _to_int(port.get("handle", 0)),
            "is_connected": bool(port.get("is_connected", False)),
            "connections":  connections,
        })

    return {
        "block_path":    block_path,
        "ports":         result_ports,
        "error_message": error_message,
    }


def simulink_add_line_by_handles(
    system_path: str,
    src_handle: _IntArg,
    dst_handle: _IntArg,
    allow_branch: _BoolArg = True,
    autorouting: _BoolArg = True,
) -> dict:
    """Connect ports using raw port handles for robust physical-port wiring.

    .. deprecated::
        Use :func:`simulink_connect_ports` with ``addressing='handle'`` instead.
    """
    import warnings
    warnings.warn(
        "simulink_add_line_by_handles is deprecated; use simulink_connect_ports(addressing='handle') instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    session = MatlabSession.get()
    model_name = str(system_path).split("/")[0]
    _ensure_model_bootstrapped(session, model_name)
    raw = session.call(
        "vsg_add_line_by_handles",
        system_path,
        float(src_handle),
        float(dst_handle),
        bool(allow_branch),
        bool(autorouting),
        nargout=1,
    )
    return {
        "ok": bool(raw.get("ok", False)),
        "line_handle": _to_int(raw.get("line_handle", 0)),
        "created_branch": bool(raw.get("created_branch", False)),
        "important_lines": _to_list(raw.get("important_lines", [])),
        "error_message": str(raw.get("error_message", "")),
    }


def simulink_compile_diagnostics(model_name: str, mode: str = "update") -> dict:
    """Run update/compile analysis and return structured diagnostics."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    raw = session.call("vsg_compile_diagnostics", loaded_model_name, mode, nargout=1)
    return {
        "ok": bool(raw.get("ok", False)),
        "mode": str(raw.get("mode", mode)),
        "errors": _convert_diagnostic_entries(raw.get("errors", [])),
        "warnings": _convert_diagnostic_entries(raw.get("warnings", [])),
        "raw_summary": str(raw.get("raw_summary", "")),
    }


def simulink_step_diagnostics(
    model_name: str,
    start_time: float,
    stop_time: float,
    timeout_sec: _IntArg = 120,
    simulation_mode: str = "normal",
    capture_warnings: _BoolArg = True,
    max_warning_lines: _IntArg = 20,
) -> dict:
    """Run a short controlled simulation window and classify the outcome."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    try:
        raw = session.call(
            "vsg_step_diagnostics",
            loaded_model_name,
            float(start_time),
            float(stop_time),
            "timeout_sec",
            int(timeout_sec),
            "simulation_mode",
            simulation_mode,
            "capture_warnings",
            bool(capture_warnings),
            "max_warning_lines",
            int(max_warning_lines),
            nargout=1,
            timeout=int(timeout_sec),
        )
    except MatlabCallError as exc:
        if "timed out" in str(exc).lower():
            return {
                "ok": False,
                "status": "engine_timeout",
                "elapsed_sec": float(timeout_sec),
                "sim_time_reached": None,
                "warning_count": 0,
                "error_count": 1,
                "top_warnings": [],
                "top_errors": [{
                    "signature": "engine_timeout",
                    "count": 1,
                    "example": str(exc),
                    "time": None,
                }],
                "timed_out_in": "python",
                "raw_summary": str(exc),
                "simscape_constraint_violation": {"detected": False},
            }
        raise
    return _normalize_step_diagnostics(raw)


def simulink_solver_audit(
    model_name: str,
    include_model_solver: _BoolArg = True,
    include_simscape_solver: _BoolArg = True,
    include_diagnostics: _BoolArg = True,
) -> dict:
    """Read solver settings from model-level and Simscape configuration blocks."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    raw = session.call(
        "vsg_solver_audit",
        loaded_model_name,
        bool(include_model_solver),
        bool(include_simscape_solver),
        bool(include_diagnostics),
        nargout=1,
    )
    model_solver = raw.get("model_solver", {})
    suspicions = _to_list(raw.get("suspicions", []))
    _maybe_add_fastrestart_suspicion(session, loaded_model_name, model_solver, suspicions)
    return {
        "ok": bool(raw.get("ok", False)),
        "model_solver": _convert_string_dict(model_solver),
        "solver_type": str(raw.get("solver_type", "")),
        "max_step": str(raw.get("max_step", "")),
        "rel_tol": str(raw.get("rel_tol", "")),
        "abs_tol": str(raw.get("abs_tol", "")),
        "stop_time": str(raw.get("stop_time", "")),
        "diagnostics": _convert_string_dict(raw.get("diagnostics", {})),
        "solver_config_blocks": _convert_solver_config_blocks(raw.get("solver_config_blocks", [])),
        "suspicions": suspicions,
    }


def simulink_prepare_model_workspace(
    model_name: str,
    model_dir: str,
    run_preload: _BoolArg = True,
    scripts: list[str] | None = None,
    base_vars: dict[str, Any] | None = None,
) -> dict:
    """Prepare base workspace variables and preload callbacks for a model."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    raw = session.call(
        "vsg_prepare_model_workspace",
        loaded_model_name,
        model_dir,
        bool(run_preload),
        scripts or [],
        base_vars or {},
        nargout=1,
    )
    return {
        "ok": bool(raw.get("ok", False)),
        "ran_scripts": _to_list(raw.get("ran_scripts", [])),
        "vars_loaded": _to_list(raw.get("vars_loaded", [])),
        "callback_errors": _to_list(raw.get("callback_errors", [])),
        "warnings": _to_list(raw.get("warnings", [])),
    }


def simulink_event_source_audit(
    model_name: str,
    path_prefix: str | None = None,
    block_types: list[str] | None = None,
    warmup_start: float | None = None,
    warmup_end: float | None = None,
    boundary_eps: float = 0.02,
) -> dict:
    """Scan discrete event source blocks and flag suspicious configurations."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    raw = session.call(
        "vsg_event_source_audit",
        loaded_model_name,
        path_prefix or "",
        block_types or [],
        [] if warmup_start is None else float(warmup_start),
        [] if warmup_end is None else float(warmup_end),
        float(boundary_eps),
        nargout=1,
    )
    return {
        "ok": bool(raw.get("ok", False)),
        "items": _convert_event_items(raw.get("items", [])),
        "summary": _to_list(raw.get("summary", [])),
    }


def simulink_patch_and_verify(
    model_name: str,
    edits: list[dict[str, Any]],
    run_update: _BoolArg = True,
    smoke_test_stop_time: float | None = None,
    timeout_sec: _IntArg = 60,
) -> dict:
    """Apply parameter edits, read them back, update, and optionally smoke test."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    raw = session.call(
        "vsg_patch_and_verify",
        loaded_model_name,
        edits,
        bool(run_update),
        [] if smoke_test_stop_time is None else float(smoke_test_stop_time),
        int(timeout_sec),
        nargout=1,
        timeout=int(timeout_sec),
    )
    return {
        "ok": bool(raw.get("ok", False)),
        "applied_edits": _convert_applied_edits(raw.get("applied_edits", [])),
        "readback": _convert_readback_items(raw.get("readback", [])),
        "update_ok": bool(raw.get("update_ok", False)),
        "smoke_test_ok": _to_optional_bool(raw.get("smoke_test_ok")),
        "smoke_test_summary": _convert_smoke_summary(raw.get("smoke_test_summary")),
        "warnings": _to_list(raw.get("warnings", [])),
        "errors": _to_list(raw.get("errors", [])),
    }


def simulink_describe_library_block(library_path: str) -> dict:
    """Describe a library block by exact library path."""
    session = MatlabSession.get()
    raw = session.call("vsg_describe_library_block", library_path, nargout=1)
    return {
        "exists": bool(raw.get("exists", False)),
        "dialog_params": _to_list(raw.get("dialog_params", [])),
        "default_values": _convert_string_dict(raw.get("default_values", {})),
        "port_schema": _convert_library_port_schema(raw.get("port_schema", [])),
        "mask_type": str(raw.get("mask_type", "")),
        "reference_block": str(raw.get("reference_block", "")),
        "error": str(raw.get("error", "")),
    }


def simulink_find_blocks_by_mask_or_ref(
    model_name: str,
    mask_type: str = "",
    reference_block: str = "",
    name_regex: str = "",
) -> dict:
    """Find blocks by mask type, reference block, and optional name regex."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    raw = session.call(
        "vsg_find_blocks_by_mask_or_ref",
        loaded_model_name,
        mask_type,
        reference_block,
        name_regex,
        nargout=1,
    )
    return {
        "matches": _to_list(raw.get("matches", [])),
    }


def simulink_clone_model(
    src_model: str,
    dst_model: str,
    src_dir: str,
    dst_dir: str,
    overwrite: _BoolArg = False,
) -> dict:
    """Clone an .slx model to a new file and load the destination model."""
    session = MatlabSession.get()
    raw = session.call(
        "vsg_clone_model",
        src_model,
        dst_model,
        src_dir,
        dst_dir,
        bool(overwrite),
        nargout=1,
    )
    return {
        "ok": bool(raw.get("ok", False)),
        "dst_file": str(raw.get("dst_file", "")),
        "loaded_model_name": str(raw.get("loaded_model_name", "")),
        "error_message": str(raw.get("error_message", "")),
    }


def simulink_delete_block_with_connections(
    model_name: str,
    block_path: str,
    delete_attached_lines: _BoolArg = True,
) -> dict:
    """Delete a block and optionally remove attached lines first."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    raw = session.call(
        "vsg_delete_block_with_connections",
        loaded_model_name,
        block_path,
        bool(delete_attached_lines),
        nargout=1,
    )
    return {
        "ok": bool(raw.get("ok", False)),
        "block_path": str(raw.get("block_path", block_path)),
        "deleted_lines": [_to_int(x) for x in _to_list(raw.get("deleted_lines", [])) if _to_int(x) > 0],
        "error_message": str(raw.get("error_message", "")),
    }


def simulink_summarize_signal_fanout(
    model_name: str,
    block_path: str,
    outport_index: _IntArg,
) -> dict:
    """Summarize the fanout of one output port."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    raw = session.call(
        "vsg_summarize_signal_fanout",
        loaded_model_name,
        block_path,
        int(outport_index),
        nargout=1,
    )
    return {
        "block_path": str(raw.get("block_path", block_path)),
        "outport_index": _to_int(raw.get("outport_index", outport_index)),
        "destinations": _convert_port_endpoints(raw.get("destinations", [])),
        "fanout_count": _to_int(raw.get("fanout_count", 0)),
        "line_handle": _to_int(raw.get("line_handle", 0)),
        "error_message": str(raw.get("error_message", "")),
    }


def simulink_bulk_get_params(
    model_name: str,
    block_paths: list[str],
    param_names: list[str],
) -> dict:
    """Read selected parameters from many blocks in one call."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    raw = session.call(
        "vsg_bulk_get_params",
        loaded_model_name,
        block_paths,
        param_names,
        nargout=1,
    )
    return {
        "items": _convert_bulk_param_items(raw.get("items", [])),
    }


def simulink_model_diff(before_model: str, after_model: str) -> dict:
    """Compare two loaded models and summarize block/parameter/line changes."""
    session = MatlabSession.get()
    loaded_before_model = _ensure_model_bootstrapped(session, before_model)
    loaded_after_model = _ensure_model_bootstrapped(session, after_model)
    raw = session.call("vsg_model_diff", loaded_before_model, loaded_after_model, nargout=1)
    return {
        "added_blocks": _to_list(raw.get("added_blocks", [])),
        "removed_blocks": _to_list(raw.get("removed_blocks", [])),
        "param_changes": _convert_param_changes(raw.get("param_changes", [])),
        "added_lines": _to_list(raw.get("added_lines", [])),
        "removed_lines": _to_list(raw.get("removed_lines", [])),
    }


def simulink_solver_warning_summary(
    model_name: str,
    run_code_or_file: str,
    timeout_sec: _IntArg = 60,
    warning_patterns: list[str] | None = None,
    collapse_duplicates: _BoolArg = True,
) -> dict:
    """Collapse repeated solver warnings from captured MATLAB output."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    try:
        raw = session.call(
            "vsg_solver_warning_summary",
            loaded_model_name,
            run_code_or_file,
            int(timeout_sec),
            warning_patterns or [],
            bool(collapse_duplicates),
            nargout=1,
            timeout=int(timeout_sec),
        )
    except MatlabCallError as exc:
        if "timed out" in str(exc).lower():
            return {
                "ok": False,
                "first_occurrence_time": None,
                "last_occurrence_time": None,
                "unique_warning_types": 0,
                "collapsed_warnings": [],
                "stiffness_detected": False,
                "likely_stuck_time": None,
                "suggested_next_checks": [
                    "Shorten the diagnostic run or use simulink_step_diagnostics around the suspected stuck time.",
                ],
                "raw_summary": str(exc),
                "error_message": str(exc),
            }
        raise
    return {
        "ok": bool(raw.get("ok", False)),
        "first_occurrence_time": _to_optional_float(raw.get("first_occurrence_time")),
        "last_occurrence_time": _to_optional_float(raw.get("last_occurrence_time")),
        "unique_warning_types": _to_int(raw.get("unique_warning_types", 0)),
        "collapsed_warnings": _convert_collapsed_warnings(raw.get("collapsed_warnings", [])),
        "stiffness_detected": bool(raw.get("stiffness_detected", False)),
        "likely_stuck_time": _to_optional_float(raw.get("likely_stuck_time")),
        "suggested_next_checks": _to_list(raw.get("suggested_next_checks", [])),
        "raw_summary": str(raw.get("raw_summary", "")),
        "error_message": str(raw.get("error_message", "")),
    }


def simulink_signal_snapshot(
    model_name: str,
    time_s: float,
    signals: list[Any],
    allow_partial: _BoolArg = False,
) -> dict:
    """Read signal values near a target simulation time from logsout, ToWorkspace, or block outputs."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    raw = session.call(
        "vsg_signal_snapshot",
        loaded_model_name,
        float(time_s),
        signals,
        bool(allow_partial),
        nargout=1,
    )
    values, units = _convert_snapshot_items(raw.get("values", []))
    units_from_raw = _convert_snapshot_units(raw.get("units", []))
    units.update({k: v for k, v in units_from_raw.items() if k not in units})
    return {
        "time_s": _to_optional_float(raw.get("time_s")) or float(time_s),
        "values": values,
        "missing_signals": _to_list(raw.get("missing_signals", [])),
        "units": units,
        "read_ok": bool(raw.get("read_ok", False)),
        "warnings": _to_list(raw.get("warnings", [])),
        "error_message": str(raw.get("error_message", "")),
    }


# ------------------------------------------------------------------
# Visual capture (internal — not in PUBLIC_TOOLS yet)
# ------------------------------------------------------------------


def simulink_screenshot(
    model_name: str,
    system_path: str | None = None,
    resolution: _IntArg = 150,
    return_base64: _BoolArg = False,
) -> dict:
    """Capture a Simulink model or subsystem diagram as a PNG image.

    The image is saved to a temporary file.  By default only the file path
    and metadata are returned (compact JSON).  Set *return_base64=True* to
    also include the raw image bytes as a base64 string — use sparingly as
    this inflates the response payload.

    Args:
        model_name: Simulink model name (without .slx).  The model will be
            loaded automatically if needed.
        system_path: Optional subsystem path (e.g. 'kundur_vsg/VSG_ES1').
            When *None*, the top-level model diagram is captured.
        resolution: DPI for the output PNG (default 150).
        return_base64: If True, add an ``image_base64`` field to the result.

    Returns:
        dict with ok, artifact_path, width, height, format, sha256,
        and optionally image_base64.
    """
    import base64
    import hashlib
    import tempfile

    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    target = system_path if system_path else loaded_model_name

    tmp_dir = tempfile.mkdtemp(prefix="slx_screenshot_")
    out_path = str(Path(tmp_dir) / f"{target.replace('/', '__')}.png")

    raw = session.call("vsg_screenshot", target, out_path, float(resolution))
    ok = bool(raw.get("ok", False))

    result: dict = {
        "ok": ok,
        "artifact_path": out_path if ok else "",
        "width": int(raw.get("width", 0)),
        "height": int(raw.get("height", 0)),
        "format": "png",
        "sha256": "",
        "error_message": str(raw.get("error_msg", "")),
    }

    if ok and Path(out_path).exists():
        data = Path(out_path).read_bytes()
        result["sha256"] = hashlib.sha256(data).hexdigest()
        if return_base64:
            result["image_base64"] = base64.b64encode(data).decode("ascii")

    return result


def simulink_capture_figure(
    figure_id: _IntArg | None = None,
    capture_all: _BoolArg = False,
    resolution: _IntArg = 150,
    return_base64: _BoolArg = False,
) -> dict:
    """Capture one or more open MATLAB figure windows as PNG images.

    By default captures the most recent figure (gcf).  Pass an explicit
    *figure_id* to target a specific figure, or set *capture_all=True* to
    capture every open figure window.

    Args:
        figure_id: MATLAB figure number to capture.  *None* means the most
            recent figure (gcf).  Ignored when *capture_all* is True.
        capture_all: When True, capture all open figure windows.
        resolution: DPI for the output PNG (default 150).
        return_base64: If True, add ``image_base64`` to each figure entry.

    Returns:
        dict with ok, count, figures (list of dicts with id, artifact_path,
        title, width, height, format, sha256, and optionally image_base64),
        and error_message.
    """
    import base64
    import hashlib
    import tempfile

    session = MatlabSession.get()
    tmp_dir = tempfile.mkdtemp(prefix="slx_figure_")

    matlab_fig_id = float(figure_id) if figure_id is not None else 0.0

    raw = session.call(
        "vsg_capture_figure",
        tmp_dir,
        matlab_fig_id,
        bool(capture_all),
        float(resolution),
    )

    ok = bool(raw.get("ok", False))
    error_msg = str(raw.get("error_msg", ""))

    figures: list[dict] = []
    if ok:
        raw_figs = raw.get("figures", [])
        if isinstance(raw_figs, dict):
            raw_figs = [raw_figs]
        for fig in _to_list(raw_figs) if not isinstance(raw_figs, list) else raw_figs:
            if not isinstance(fig, dict):
                continue
            fig_path = str(fig.get("path", ""))
            entry: dict = {
                "id": int(fig.get("id", 0)),
                "artifact_path": fig_path,
                "title": str(fig.get("title", "")),
                "width": int(fig.get("width", 0)),
                "height": int(fig.get("height", 0)),
                "format": "png",
                "sha256": "",
            }
            if fig_path and Path(fig_path).exists():
                data = Path(fig_path).read_bytes()
                entry["sha256"] = hashlib.sha256(data).hexdigest()
                if return_base64:
                    entry["image_base64"] = base64.b64encode(data).decode("ascii")
            figures.append(entry)

    return {
        "ok": ok,
        "count": len(figures),
        "figures": figures,
        "error_message": error_msg,
    }


# ------------------------------------------------------------------
# Internal conversion helpers
# ------------------------------------------------------------------

def _convert_element(x: Any) -> Any:
    """Coerce a single MATLAB-engine value to a JSON-safe Python type.

    int and float are preserved for precision; dict and list pass through;
    everything else (bytes, MATLAB opaque types, etc.) is stringified.
    """
    return x if isinstance(x, (dict, list, int, float)) else str(x)


def _to_list(obj: Any) -> list:
    """Convert MATLAB cell arrays or other iterables to Python lists.

    Applies _convert_element uniformly regardless of whether the source is
    a list, tuple, or other iterable, so numeric precision is preserved
    across all MATLAB Engine return-type variants.
    """
    if obj is None:
        return []
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, (list, tuple)):
        return [_convert_element(x) for x in obj]
    try:
        return [_convert_element(x) for x in obj]
    except TypeError:
        return [_convert_element(obj)]


def _resolve_model_load_target(model_name: str) -> tuple[str, str, list[str]]:
    model_path = _find_model_file(model_name)
    if model_path is None:
        normalized_name = Path(model_name).stem if Path(model_name).suffix.lower() == ".slx" else model_name
        return model_name, normalized_name, []

    resolved = model_path.resolve()
    return str(resolved), resolved.stem, _collect_model_bootstrap_paths(resolved)


def _ensure_model_bootstrapped(session: MatlabSession, model_name: str) -> str:
    load_target, loaded_model_name, bootstrap_paths = _resolve_model_load_target(model_name)
    # Per-session cache: invalidated automatically when MatlabSession is recreated
    if not hasattr(session, "_bootstrapped"):
        session._bootstrapped: set[str] = set()
    if loaded_model_name in session._bootstrapped:
        return loaded_model_name
    for bootstrap_path in bootstrap_paths:
        session.call("addpath", bootstrap_path, nargout=0)
    session.call("load_system", load_target, nargout=0)
    session._bootstrapped.add(loaded_model_name)
    return loaded_model_name


def _extract_known_model_references(code_or_file: str) -> list[str]:
    content = _read_matlab_script_if_available(code_or_file)
    source = content if content is not None else str(code_or_file)
    model_names: list[str] = []
    for raw_target in _MATLAB_MODEL_REF_RE.findall(source):
        candidate = raw_target.split("/", 1)[0].strip()
        if not candidate:
            continue
        if _find_model_file(candidate) is None:
            continue
        if candidate not in model_names:
            model_names.append(candidate)
    return model_names


def _read_matlab_script_if_available(code_or_file: str) -> str | None:
    candidate = Path(str(code_or_file))
    if candidate.exists():
        try:
            return candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return candidate.read_text(encoding="utf-8", errors="ignore")

    if candidate.suffix.lower() == ".m":
        rooted_candidate = _WORKSPACE_ROOT / candidate
        if rooted_candidate.exists():
            try:
                return rooted_candidate.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return rooted_candidate.read_text(encoding="utf-8", errors="ignore")

    if not candidate.suffix:
        matches = sorted(_WORKSPACE_ROOT.glob(f"**/{candidate.name}.m"))
        if len(matches) == 1:
            try:
                return matches[0].read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return matches[0].read_text(encoding="utf-8", errors="ignore")

    return None


def _find_model_file(model_name: str) -> Path | None:
    candidate = Path(model_name)
    if candidate.exists():
        return candidate

    if candidate.suffix.lower() == ".slx":
        rooted_candidate = _WORKSPACE_ROOT / candidate
        if rooted_candidate.exists():
            return rooted_candidate
        return None

    matches = sorted(_WORKSPACE_ROOT.glob(f"scenarios/**/simulink_models/{model_name}.slx"))
    if len(matches) == 1:
        return matches[0]
    return None


def _collect_model_bootstrap_paths(model_file: Path) -> list[str]:
    paths: list[str] = []
    candidates = [
        model_file.parent,
        model_file.parent.parent,
        model_file.parent.parent / "matlab_scripts",
    ]
    for candidate in candidates:
        if candidate.exists():
            path_str = str(candidate.resolve())
            if path_str not in paths:
                paths.append(path_str)
    return paths


def _validate_destination_block_path(model_name: str, destination_block: str) -> None:
    expected_prefix = f"{model_name}/"
    if destination_block.startswith(expected_prefix):
        return
    raise ValueError(
        f"destination_block must be a full block path inside the model, "
        f"for example '{model_name}/Gain'."
    )


def _normalize_param_names(param_names: list[str] | str | None) -> list[str] | None:
    if param_names is None:
        return None

    raw_items = [param_names] if isinstance(param_names, str) else list(param_names)
    normalized: list[str] = []
    for raw_item in raw_items:
        if raw_item is None:
            continue
        text = str(raw_item).strip()
        if not text:
            continue
        parts = text.split(",") if "," in text else [text]
        for part in parts:
            value = part.strip()
            if value:
                normalized.append(value)
    return normalized or None


def _validate_relative_port_reference(
    model_name: str,
    target_system: str,
    port_ref: str,
    field_name: str,
) -> None:
    absolute_prefixes = {
        f"{model_name}/",
        f"{target_system}/",
    }
    if any(port_ref.startswith(prefix) for prefix in absolute_prefixes):
        raise ValueError(
            f"{field_name} must be relative to system_path. "
            f"Pass system_path='{target_system}' with ports like 'Const/1' instead of '{port_ref}'."
        )


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _convert_string_dict(obj: Any) -> dict[str, str]:
    if not isinstance(obj, dict):
        return {}
    return {str(k): str(v) for k, v in obj.items()}


def _convert_blocks(blocks: Any) -> list[dict]:
    """Convert MATLAB block cell array to list of dicts."""
    result = []
    if blocks is None:
        return result
    for b in _to_list(blocks):
        if isinstance(b, dict):
            raw_kp = b.get("key_params", {})
            key_params = (
                {str(k): str(v) for k, v in raw_kp.items()}
                if isinstance(raw_kp, dict) else {}
            )
            result.append({
                "path": str(b.get("path", "")),
                "type": str(b.get("type", "")),
                "name": str(b.get("name", "")),
                "key_params": key_params,
            })
    return result


def _convert_tree(tree: Any) -> dict:
    """Convert MATLAB nested struct tree to Python dict."""
    if not isinstance(tree, dict):
        return {"name": str(tree), "type": "unknown", "path": "", "children": []}
    children = []
    raw_children = tree.get("children", [])
    for c in _to_list(raw_children):
        children.append(_convert_tree(c))
    return {
        "name": str(tree.get("name", "")),
        "type": str(tree.get("type", "")),
        "path": str(tree.get("path", "")),
        "children": children,
    }


def _convert_port_descriptions(items: Any) -> list[dict]:
    ports = []
    for item in _to_list(items):
        if not isinstance(item, dict):
            continue
        ports.append({
            "kind": str(item.get("kind", "")),
            "index": _to_int(item.get("index", 0)),
            "handle": _to_int(item.get("handle", 0)),
            "is_connected": bool(item.get("is_connected", False)),
            "line_handles": [_to_int(x) for x in _to_list(item.get("line_handles", [])) if _to_int(x) > 0],
            "connected_block_paths": _to_list(item.get("connected_block_paths", [])),
        })
    return ports


def _convert_port_endpoint(item: Any) -> dict:
    if not isinstance(item, dict):
        return {
            "block_path": "",
            "port_kind": "",
            "port_index": 0,
            "handle": 0,
        }
    return {
        "block_path": str(item.get("block_path", "")),
        "port_kind": str(item.get("port_kind", "")),
        "port_index": _to_int(item.get("port_index", 0)),
        "handle": _to_int(item.get("handle", 0)),
    }


def _convert_port_endpoints(items: Any) -> list[dict]:
    return [_convert_port_endpoint(item) for item in _to_list(items)]


def _convert_diagnostic_entries(items: Any) -> list[dict]:
    result = []
    for item in _to_list(items):
        if not isinstance(item, dict):
            continue
        result.append({
            "block_path": str(item.get("block_path", "")),
            "param_name": str(item.get("param_name", "")),
            "message": str(item.get("message", "")),
            "severity": str(item.get("severity", "")),
            "phase": str(item.get("phase", "")),
        })
    return result


def _convert_warning_groups(items: Any) -> list[dict]:
    groups = []
    for item in _to_list(items):
        if not isinstance(item, dict):
            continue
        time_value = item.get("time")
        try:
            time_value = float(time_value) if time_value not in ("", None) else None
        except (TypeError, ValueError):
            time_value = None
        groups.append({
            "signature": str(item.get("signature", "")),
            "count": _to_int(item.get("count", 0)),
            "example": str(item.get("example", "")),
            "time": time_value,
        })
    return groups


def _maybe_add_fastrestart_suspicion(
    session: "MatlabSession",
    loaded_model_name: str,
    model_solver: dict,
    suspicions: list,
) -> None:
    """Append a FastRestart + topology-switch warning when the combination is dangerous.

    FastRestart with on-model discrete event sources (Step/Pulse/Signal Builder
    blocks that drive breakers) can silently break Simscape IC solver topology
    assumptions, causing DAE constraint failures at the event time.
    """
    fast_restart = str(model_solver.get("FastRestart", "off")).lower()
    if fast_restart != "on":
        return
    try:
        event_blocks = session.call(
            "find_system",
            loaded_model_name,
            "BlockType",
            "Step",
            nargout=1,
        )
        has_events = bool(_to_list(event_blocks))
    except Exception as exc:
        logger.debug(
            "FastRestart suspicion check: find_system failed for %s (%s); skipping warning",
            loaded_model_name,
            exc,
        )
        has_events = False
    if has_events:
        suspicions.append(
            "FastRestart=on with discrete Step blocks detected. "
            "Step block transitions mid-simulation may violate Simscape IC solver "
            "topology assumptions, causing DAE constraint failures at the event time. "
            "Consider pre-scheduling disturbances via breaker initial states instead."
        )


_SIMSCAPE_CONSTRAINT_PATTERNS = re.compile(
    r"derivative of state|is not finite|constraint.*violated|"
    r"simscape.*dae|index.*1 dae|simscape.*algebraic loop|"
    r"discontinuity in the state",
    re.IGNORECASE,
)


def _detect_simscape_constraint_violation(
    top_errors: list[dict],
    raw_summary: str,
    sim_time_reached: float | None,
) -> dict:
    """Detect Simscape DAE constraint violations from error lists and raw summary."""
    detected = False
    approx_time: float | None = None

    for err in top_errors:
        text = str(err.get("example", "")) + " " + str(err.get("signature", ""))
        if _SIMSCAPE_CONSTRAINT_PATTERNS.search(text):
            detected = True
            t = err.get("time")
            if t is not None:
                try:
                    approx_time = float(t)
                except (TypeError, ValueError):
                    pass
            break

    if not detected and _SIMSCAPE_CONSTRAINT_PATTERNS.search(raw_summary):
        detected = True

    if not detected:
        return {"detected": False}

    if approx_time is None:
        approx_time = sim_time_reached

    return {
        "detected": True,
        "approx_time": approx_time,
        "hint": (
            "Simscape DAE constraint violation detected. "
            "If FastRestart is on and a Step/Pulse block switches topology at this time, "
            "the IC solver's topological assumptions are broken. "
            "Consider pre-scheduling disturbances via breaker initial states "
            "instead of mid-episode set_param calls."
        ),
    }


def _normalize_step_diagnostics(raw: Any) -> dict:
    if not isinstance(raw, dict):
        return {
            "ok": False,
            "status": "sim_error",
            "elapsed_sec": 0.0,
            "sim_time_reached": None,
            "warning_count": 0,
            "error_count": 1,
            "top_warnings": [],
            "top_errors": [{
                "signature": "invalid_response",
                "count": 1,
                "example": str(raw),
                "time": None,
            }],
            "timed_out_in": "",
            "raw_summary": str(raw),
        }
    sim_time_reached = raw.get("sim_time_reached")
    try:
        sim_time_reached = float(sim_time_reached) if sim_time_reached not in ("", None) else None
    except (TypeError, ValueError):
        sim_time_reached = None
    top_errors = _convert_warning_groups(raw.get("top_errors", []))
    raw_summary = str(raw.get("raw_summary", ""))
    result = {
        "ok": bool(raw.get("ok", False)),
        "status": str(raw.get("status", "")),
        "elapsed_sec": float(raw.get("elapsed_sec", 0.0)),
        "sim_time_reached": sim_time_reached,
        "warning_count": int(raw.get("warning_count", 0)),
        "error_count": int(raw.get("error_count", 0)),
        "top_warnings": _convert_warning_groups(raw.get("top_warnings", [])),
        "top_errors": top_errors,
        "timed_out_in": str(raw.get("timed_out_in", "")),
        "raw_summary": raw_summary,
        "simscape_constraint_violation": _detect_simscape_constraint_violation(
            top_errors, raw_summary, sim_time_reached
        ),
    }
    return result


def _convert_solver_config_blocks(items: Any) -> list[dict]:
    blocks = []
    for item in _to_list(items):
        if not isinstance(item, dict):
            continue
        blocks.append({
            "block_path": str(item.get("block_path", "")),
            "mask_type": str(item.get("mask_type", "")),
            "params": _convert_string_dict(item.get("params", {})),
            "missing_expected_params": _to_list(item.get("missing_expected_params", [])),
        })
    return blocks


def _convert_event_items(items: Any) -> list[dict]:
    result = []
    for item in _to_list(items):
        if not isinstance(item, dict):
            continue
        result.append({
            "block_path": str(item.get("block_path", "")),
            "block_type": str(item.get("block_type", "")),
            "sample_time": str(item.get("sample_time", "")),
            "time": str(item.get("time", "")),
            "before": str(item.get("before", "")),
            "after": str(item.get("after", "")),
            "suspicious": bool(item.get("suspicious", False)),
            "reason": str(item.get("reason", "")),
        })
    return result


def _convert_applied_edits(items: Any) -> list[dict]:
    result = []
    for item in _to_list(items):
        if not isinstance(item, dict):
            continue
        result.append({
            "block_path": str(item.get("block_path", "")),
            "params": _convert_string_dict(item.get("params", {})),
        })
    return result


def _convert_readback_items(items: Any) -> list[dict]:
    result = []
    for item in _to_list(items):
        if not isinstance(item, dict):
            continue
        result.append({
            "block_path": str(item.get("block_path", "")),
            "params": _convert_string_dict(item.get("params", {})),
            "error": str(item.get("error", "")),
        })
    return result


def _to_optional_bool(value: Any) -> bool | None:
    if value in ("", None, []):
        return None
    return bool(value)


def _to_optional_float(value: Any) -> float | None:
    if value in ("", None, []):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _convert_smoke_summary(item: Any) -> dict | None:
    if item in ("", None, []):
        return None
    if isinstance(item, dict):
        summary = dict(item)
        if "sim_time_reached" in summary and summary["sim_time_reached"] not in ("", None):
            try:
                summary["sim_time_reached"] = float(summary["sim_time_reached"])
            except (TypeError, ValueError):
                pass
        return summary
    return {"raw": str(item)}


def _convert_library_port_schema(items: Any) -> list[dict]:
    result = []
    for item in _to_list(items):
        if not isinstance(item, dict):
            continue
        result.append({
            "name": str(item.get("name", "")),
            "label": str(item.get("label", "")),
            "domain": str(item.get("domain", "")),
            "port_type": str(item.get("port_type", "")),
        })
    return result


def _convert_bulk_param_items(items: Any) -> list[dict]:
    result = []
    for item in _to_list(items):
        if not isinstance(item, dict):
            continue
        result.append({
            "block_path": str(item.get("block_path", "")),
            "params": _convert_string_dict(item.get("params", {})),
            "missing_params": _to_list(item.get("missing_params", [])),
            "error": str(item.get("error", "")),
        })
    return result


def _convert_param_changes(items: Any) -> list[dict]:
    result = []
    for item in _to_list(items):
        if not isinstance(item, dict):
            continue
        result.append({
            "block_path": str(item.get("block_path", "")),
            "param_name": str(item.get("param_name", "")),
            "before": str(item.get("before", "")),
            "after": str(item.get("after", "")),
        })
    return result


def _convert_collapsed_warnings(items: Any) -> list[dict]:
    groups = []
    for item in _to_list(items):
        if not isinstance(item, dict):
            continue
        groups.append({
            "signature": str(item.get("signature", "")),
            "count": _to_int(item.get("count", 0)),
            "first_time": _to_optional_float(item.get("first_time")),
            "last_time": _to_optional_float(item.get("last_time")),
            "example": str(item.get("example", "")),
            "min_step": _to_optional_float(item.get("min_step")),
        })
    return groups


def _convert_snapshot_items(items: Any) -> tuple[dict[str, Any], dict[str, str]]:
    values: dict[str, Any] = {}
    units: dict[str, str] = {}
    if isinstance(items, dict):
        for key, value in items.items():
            values[str(key)] = value
        return values, units
    for item in _to_list(items):
        if not isinstance(item, dict):
            continue
        signal = str(item.get("signal", ""))
        if not signal:
            continue
        values[signal] = item.get("value")
        units[signal] = str(item.get("unit", ""))
    return values, units


def _convert_snapshot_units(items: Any) -> dict[str, str]:
    if isinstance(items, dict):
        return {str(k): str(v) for k, v in items.items()}
    units: dict[str, str] = {}
    for item in _to_list(items):
        if not isinstance(item, dict):
            continue
        signal = str(item.get("signal", ""))
        if signal:
            units[signal] = str(item.get("unit", ""))
    return units
