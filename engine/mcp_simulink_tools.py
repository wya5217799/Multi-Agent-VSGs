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
    info = session.call("slx_inspect_model", loaded_model_name, float(depth))
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



def _simulink_trace_signal_raw(model_name: str, signal_name: str) -> dict:
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    path = session.call("slx_trace_signal", loaded_model_name, signal_name)
    return {
        "source": str(path["source"]),
        "sinks": _to_list(path["sinks"]),
    }


def simulink_trace_signal(model_name: str, signal_name: str) -> dict:
    """Trace a signal from source to all sinks.

    Args:
        model_name: Simulink model name
        signal_name: Signal/port name to trace

    Returns:
        dict with ok (bool), data (dict with source/sinks), error (str|None)
    """
    try:
        data = _simulink_trace_signal_raw(model_name, signal_name)
        return {"ok": True, "data": data, "error": None}
    except Exception as exc:
        return {"ok": False, "data": {}, "error": str(exc)}


def _simulink_get_block_tree_raw(
    model_name: str, root_path: str | None = None, max_depth: _IntArg = 3
) -> dict:
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    if root_path is None:
        tree = session.call("slx_get_block_tree", loaded_model_name, loaded_model_name, float(max_depth))
    else:
        tree = session.call("slx_get_block_tree", loaded_model_name, root_path, float(max_depth))
    return _convert_tree(tree)


def simulink_get_block_tree(
    model_name: str, root_path: str | None = None, max_depth: _IntArg = 3
) -> dict:
    """Get hierarchical block tree from a model or subsystem.

    Args:
        model_name: Simulink model name
        root_path: Starting path (default: model root)
        max_depth: Maximum tree depth (default 3)

    Returns:
        dict with ok (bool), data (nested block tree dict), error (str|None)
    """
    try:
        data = _simulink_get_block_tree_raw(model_name, root_path, max_depth)
        return {"ok": True, "data": data, "error": None}
    except Exception as exc:
        return {"ok": False, "data": {}, "error": str(exc)}


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
    raw = session.call("slx_batch_query", loaded_model_name, [block_path], nargout=1)
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
    raise NotImplementedError(
        "simulink_get_multiple_block_params is removed; use simulink_query_params instead. "
        "slx_batch_query_cell.m no longer exists."
    )


def simulink_load_model(model_name: str) -> dict:
    """Load a Simulink model into the shared MATLAB engine."""
    try:
        session = MatlabSession.get()
        load_target, loaded_model_name, bootstrap_paths = _resolve_model_load_target(model_name)
        _ensure_model_bootstrapped(session, model_name)
        return {
            "ok": True,
            "model_name": loaded_model_name,
            "load_target": load_target,
            "bootstrap_paths": bootstrap_paths,
            "loaded_models": _simulink_loaded_models_raw(),
            "error_message": "",
        }
    except Exception as exc:
        return {"ok": False, "error_message": str(exc), "model_name": model_name}


def simulink_create_model(model_name: str, open_model: _BoolArg = True) -> dict:
    """Create a new unsaved Simulink model in the shared MATLAB engine."""
    session = MatlabSession.get()
    summary = session.call("slx_create_model", model_name, bool(open_model), nargout=1)
    return {
        "ok": bool(summary.get("ok", False)),
        "model_name": str(summary.get("model_name", model_name)),
        "loaded_models": _simulink_loaded_models_raw() if bool(summary.get("ok", False)) else [],
        "important_lines": _to_list(summary.get("important_lines", [])),
        "error_message": str(summary.get("error_message", "")),
    }


def simulink_close_model(model_name: str, save: _BoolArg = False) -> dict:
    """Close a Simulink model in the shared MATLAB engine."""
    try:
        session = MatlabSession.get()
        if bool(save):
            session.call("save_system", model_name, nargout=0)
        session.call("slx_close_model", model_name, nargout=0)
        return {
            "ok": True,
            "model_name": model_name,
            "loaded_models": _simulink_loaded_models_raw(),
        }
    except Exception as exc:
        return {"ok": False, "error_message": str(exc)}


def simulink_set_block_params(model_name: str, block_path: str, params: dict[str, str]) -> dict:
    """Set one or more dialog parameters on a block with structured output."""
    session = MatlabSession.get()
    _ensure_model_bootstrapped(session, model_name)
    summary = session.call("slx_set_block_params", block_path, params, nargout=1)
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
        "slx_add_block",
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
            "slx_delete_block_with_connections",
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
        summary = session.call("slx_delete_block", block_path, nargout=1)
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
        "slx_connect_blocks",
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
        "slx_add_subsystem",
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


def simulink_library_lookup(lib_name: str, block_display_name: str) -> dict:
    """Query parameters and ports of a library block before placement.

    Use this to confirm library block definition (params, defaults, ports) before
    calling simulink_add_block. For model-level checks, use simulink_compile_diagnostics.

    Args:
        lib_name: Library name (e.g. 'ee_lib', 'simscape')
        block_display_name: Block display name (e.g. 'Transmission Line (Three-Phase)')

    Returns:
        dict with ok (bool: call succeeded), found (bool: block exists in lib),
        handle (float), params_main (list), params_unit (list),
        defaults (dict of name->value), ports (list of dicts), error (str)

        ok=True even when found=False (block not found is a valid query result,
        not a tool failure).
    """
    session = MatlabSession.get()
    result = session.call("slx_preflight", lib_name, block_display_name, nargout=1)
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
    error_str = str(result.get("error", ""))
    return {
        "ok":          not bool(error_str),
        "found":       bool(result.get("found", False)),
        "handle":      float(result.get("handle", 0)),
        "params_main": _to_list(result.get("params_main", [])),
        "params_unit": _to_list(result.get("params_unit", [])),
        "defaults":    defaults,
        "ports":       ports,
        "error":       error_str,
    }


# DEPRECATED alias — remove after all callers migrated to simulink_library_lookup
simulink_preflight = simulink_library_lookup


def simulink_run_script(code_or_file: str, timeout_sec: _IntArg = 120) -> dict:
    """Run a MATLAB script or code string with noise suppression.

    Wraps slx_run_quiet: captures full stdout but only surfaces three categories
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
    summary = session.call("slx_run_quiet", code_or_file, nargout=1, timeout=timeout_sec)
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
        running = [jid for jid, j in _SCRIPT_JOBS.items() if not j["done_event"].is_set()]
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
        done_event = threading.Event()
        job: dict[str, Any] = {
            "code_or_file": code_or_file,
            "timeout_sec": int(timeout_sec),
            "result": None,
            "done_event": done_event,
            "started_at": time.monotonic(),
        }
        _SCRIPT_JOBS[job_id] = job

    # Capture locals so the closure doesn't depend on mutable enclosing scope.
    _code = code_or_file
    _timeout = int(timeout_sec)
    _done_event = done_event

    def _worker(_job: dict = job, _c: str = _code, _t: int = _timeout,
                _ev: threading.Event = _done_event) -> None:
        try:
            _job["result"] = simulink_run_script(_c, _t)
        except Exception as exc:
            _job["result"] = {
                "ok": False,
                "elapsed": 0.0,
                "n_warnings": 0,
                "n_errors": 1,
                "error_message": str(exc),
                "important_lines": [],
            }
        finally:
            _ev.set()  # atomic signal: result is visible before event is set

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
    with _SCRIPT_JOB_LOCK:
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
    done_event: threading.Event = job["done_event"]

    if not done_event.is_set():
        return {
            "ok": True,
            "job_id": job_id,
            "status": "running",
            "elapsed_sec": elapsed,
            "message": "Script still running — poll again later.",
        }

    # Job is done — read result then evict to prevent unbounded growth.
    result: dict = job.get("result") or {}
    with _SCRIPT_JOB_LOCK:
        _SCRIPT_JOBS.pop(job_id, None)

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

    # Both selective and all-params modes now use slx_batch_query (slx_bulk_get_params removed).
    # With param_names supplied, MATLAB filters to just those params and populates missing_params.
    # Without param_names, MATLAB reads all DialogParameters; missing_params is always [].
    # MATLAB returns a scalar struct (dict) for a single block path and a cell array (list)
    # for multiple paths — normalise both so the converter below always sees a list.
    if param_names is not None and len(param_names) > 0:
        raw = session.call("slx_batch_query", loaded_model_name, block_paths, param_names, nargout=1)
    else:
        raw = session.call("slx_batch_query", loaded_model_name, block_paths, nargout=1)
    if isinstance(raw, dict):
        raw = [raw]  # scalar struct → 1-element list
    elif not isinstance(raw, list):
        raw = []     # unexpected type → emit no items rather than crash
    return {"items": _convert_batch_query_items(raw)}


def simulink_connect_ports(
    model_name: str,
    source_port: str,
    destination_port: str,
    autorouting: _BoolArg = True,
    system_path: str | None = None,
    addressing: str = "name",
    allow_branch: _BoolArg | None = None,
) -> dict:
    """Connect two ports by name (Block/PortIndex format).

    Args:
        model_name: Simulink model name
        source_port: Source port in 'Block/PortIndex' format relative to system_path
            (for example 'Gain1/1' or 'Sub/Gain1/1')
        destination_port: Destination port in 'Block/PortIndex' format relative to system_path
        autorouting: Use Simulink autorouting (default True)
        system_path: Parent system path (default: model root)
        addressing: DEPRECATED — must be "name". Passing "handle" raises an error.
        allow_branch: DEPRECATED — must be False/None. Passing True raises an error.

    Returns:
        dict with ok, important_lines, error_message
    """
    _addr = str(addressing).strip().lower()
    if _addr == "handle":
        raise ValueError(
            "addressing='handle' is no longer supported: slx_add_line_by_handles is not available. "
            "Use name-based port addressing ('Block/PortIndex') instead."
        )
    if _addr != "name":
        raise ValueError(
            f"addressing={addressing!r} is not recognised. Only 'name' is supported."
        )
    if allow_branch is not None and bool(allow_branch):
        raise ValueError(
            "allow_branch=True is no longer supported: slx_add_line_branch is not available. "
            "For fan-out, add multiple simulink_connect_ports calls."
        )
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    target_system = system_path or loaded_model_name
    _validate_relative_port_reference(model_name, target_system, source_port, "source_port")
    _validate_relative_port_reference(model_name, target_system, destination_port, "destination_port")
    raw = session.call(
        "slx_connect_blocks",
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


def _simulink_loaded_models_raw() -> list[str]:
    session = MatlabSession.get()
    result = session.eval("find_system('type', 'block_diagram')", nargout=1)
    return _to_list(result)


def simulink_loaded_models() -> dict:
    """List Simulink models currently open in the MATLAB engine.

    Queries MATLAB's live block diagram registry — shows only models that
    are actually loaded, not just files on disk. Call this at the start of
    a debugging session to confirm which models are available before using
    inspect/params/tree tools.

    Returns:
        dict with ok (bool), data (list[str] of loaded model names), error (str|None)
    """
    try:
        data = _simulink_loaded_models_raw()
        return {"ok": True, "data": data, "error": None}
    except Exception as exc:
        return {"ok": False, "data": [], "error": str(exc)}


def simulink_bridge_status(model_name: str) -> dict:
    """Return the runtime state of the active SimulinkBridge for a model.

    Useful during training to inspect the bridge's current time step, last
    feedback signals, and disturbance load configuration — without pausing
    training or reading log files.

    Args:
        model_name: Simulink model name (e.g. 'kundur_vsg', 'NE39bus_v2').
            Required — no default to avoid silently querying the wrong model.

    Returns:
        dict with:
          ok (bool): True when status query completed without error
          active (bool): False if no bridge is registered for model_name
          model_name (str)
          t_current (float): simulation time at end of last step (s)
          n_agents (int)
          dt_control (float): control step size (s)
          Pe_prev (list|None): last measured Pe per agent (p.u.), None before first step
          delta_prev_deg (list|None): last rotor angle per agent (deg), None before first step
          tripload_state (dict): current disturbance load workspace vars (W)
          available_bridges (list[str]): all registered model names

          ok=True when active=False (no registered bridge is a valid query result).
          ok=False only when the query itself raises an exception.
    """
    try:
        from engine.simulink_bridge import get_active_bridge, list_active_bridges
        bridge = get_active_bridge(model_name)
        available = list_active_bridges()
        if bridge is None:
            return {
                "ok":                True,
                "active":            False,
                "model_name":        model_name,
                "available_bridges": available,
            }
        return {
            "ok":                True,
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
    except Exception as exc:
        return {
            "ok":         False,
            "active":     False,
            "model_name": model_name,
            "error":      str(exc),
        }


def simulink_describe_block_ports(model_name: str, block_path: str) -> dict:
    """Describe block ports in stable order with connection metadata."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    raw = session.call("slx_describe_block_ports", loaded_model_name, block_path, nargout=1)
    error_message = str(raw.get("error_message", ""))
    return {
        "ok":           not bool(error_message),
        "block_path":   str(raw.get("block_path", block_path)),
        "ports":        _convert_port_descriptions(raw.get("ports", [])),
        "error_message": error_message,
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
        "slx_trace_port_connections",
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
    slx_describe_block_ports.  No separate trace-per-port round-trips needed.

    Args:
        model_name: Simulink model name (without .slx extension)
        block_path: Full block path to explore (e.g. 'kundur_vsg/VSG_ES1')
        trace_connections: Ignored (kept for API compatibility). Connection data
            is always included from the single slx_describe_block_ports call.

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

    raw_ports = session.call("slx_describe_block_ports", loaded_model_name, block_path, nargout=1)
    ports_desc = _convert_port_descriptions(raw_ports.get("ports", []))
    error_message = str(raw_ports.get("error_message", ""))

    # connected_block_paths is already populated by slx_describe_block_ports —
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
        "ok":            not bool(error_message),
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
        This function is deprecated and has **no** equivalent handle-based
        replacement.  ``simulink_connect_ports(addressing='handle')`` is
        **not** a valid alternative — it raises :exc:`ValueError` immediately.
        Use name-based port addressing via :func:`simulink_connect_ports`
        with ``src_port='Block/PortIndex'`` / ``dst_port='Block/PortIndex'``
        instead.  If handle-based addressing is required, it is currently
        unsupported; please open an issue.
    """
    raise NotImplementedError(
        "simulink_add_line_by_handles is removed; slx_add_line_by_handles.m no longer exists. "
        "Use simulink_connect_ports(src_port='Block/PortIndex', dst_port='Block/PortIndex') instead."
    )


def simulink_compile_diagnostics(model_name: str, mode: str = "update") -> dict:
    """Run update/compile analysis and return structured diagnostics."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    raw = session.call("slx_compile_diagnostics", loaded_model_name, mode, nargout=1)
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
            "slx_step_diagnostics",
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
        "slx_solver_audit",
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
        "slx_patch_and_verify",
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


def simulink_delete_block_with_connections(
    model_name: str,
    block_path: str,
    delete_attached_lines: _BoolArg = True,
) -> dict:
    """Delete a block and optionally remove attached lines first."""
    session = MatlabSession.get()
    loaded_model_name = _ensure_model_bootstrapped(session, model_name)
    raw = session.call(
        "slx_delete_block_with_connections",
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


# ------------------------------------------------------------------
# Visual capture
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

    raw = session.call("slx_screenshot", target, out_path, float(resolution))
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
        "slx_capture_figure",
        tmp_dir,
        matlab_fig_id,
        bool(capture_all),
        float(resolution),
    )

    ok = bool(raw.get("ok", False))
    error_message = str(raw.get("error_msg", ""))

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
        "error_message": error_message,
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


def _convert_batch_query_items(items: Any) -> list[dict]:
    """Parse the struct array returned by slx_batch_query.

    slx_batch_query returns items with field names: block, params,
    missing_params, error.  This normalises them to the canonical
    Python shape used throughout simulink_query_params: block_path,
    params, missing_params, error.
    """
    result = []
    for item in _to_list(items):
        if not isinstance(item, dict):
            continue
        result.append({
            "block_path": str(item.get("block", item.get("block_path", ""))),
            "params": _convert_string_dict(item.get("params", {})),
            "missing_params": _to_list(item.get("missing_params", [])),
            "error": str(item.get("error", "")),
        })
    return result


def _convert_bulk_param_items(items: Any) -> list[dict]:
    """Legacy converter — kept for any callers outside simulink_query_params.

    Reads both 'block_path' (old slx_bulk_get_params) and 'block'
    (new slx_batch_query) so it degrades gracefully in either case.
    """
    result = []
    for item in _to_list(items):
        if not isinstance(item, dict):
            continue
        result.append({
            "block_path": str(item.get("block_path", item.get("block", ""))),
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
