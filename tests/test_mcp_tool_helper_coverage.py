"""P0.2 — MCP tool helper coverage: static + contract smoke.

Layer 1 (no MATLAB required):
  - Parse PUBLIC_TOOLS from mcp_server.py
  - Scan matching function bodies in mcp_simulink_tools.py for session.call("slx_*")
  - Assert every referenced .m exists in slx_helpers/

Layer 2 (requires MATLAB, @pytest.mark.matlab):
  - For each new helper added in P0.1, run minimal legal call
  - Assert response shape contract: ok (bool), error_message when ok=False
"""

import ast
import os
import re
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
MCP_SERVER = REPO_ROOT / "engine" / "mcp_server.py"
MCP_TOOLS  = REPO_ROOT / "engine" / "mcp_simulink_tools.py"
SLX_HELPERS = REPO_ROOT / "slx_helpers"


# ---------------------------------------------------------------------------
# Layer 1 helpers
# ---------------------------------------------------------------------------

def _parse_public_tool_names() -> list[str]:
    """Extract function names listed in PUBLIC_TOOLS from mcp_server.py via AST."""
    source = MCP_SERVER.read_text(encoding="utf-8")
    tree   = ast.parse(source)
    names  = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "PUBLIC_TOOLS":
                    if isinstance(node.value, ast.List):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Name):
                                names.append(elt.id)
    return names


def _extract_slx_calls_in_function(func_node: ast.FunctionDef) -> list[str]:
    """Return slx_* helper names referenced via session.call("slx_...", ...) literals."""
    results = []
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue
        # Match session.call(...)
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "call"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
            continue
        helper = first.value
        if helper.startswith("slx_"):
            results.append(helper)
    return results


def _map_public_functions_to_slx_calls() -> dict[str, list[str]]:
    """Parse mcp_simulink_tools.py: for each public tool, list slx_* calls."""
    public_names = set(_parse_public_tool_names())
    source = MCP_TOOLS.read_text(encoding="utf-8")
    tree   = ast.parse(source)
    mapping: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in public_names:
            calls = _extract_slx_calls_in_function(node)
            if calls:
                mapping[node.name] = calls
    return mapping


def _existing_helpers() -> set[str]:
    """Return the set of .m file stems in slx_helpers/."""
    return {p.stem for p in SLX_HELPERS.glob("*.m")}


# ---------------------------------------------------------------------------
# Layer 1 — static tests (no MATLAB)
# ---------------------------------------------------------------------------

def test_public_tools_list_nonempty():
    names = _parse_public_tool_names()
    assert len(names) > 0, "PUBLIC_TOOLS in mcp_server.py parsed as empty"


def test_all_slx_helpers_exist():
    """Every slx_* literal inside a public tool body must have a matching .m file."""
    mapping  = _map_public_functions_to_slx_calls()
    existing = _existing_helpers()
    missing  = {}
    for fn_name, helpers in mapping.items():
        for h in helpers:
            if h not in existing:
                missing.setdefault(fn_name, []).append(h)
    assert not missing, (
        "Public tools reference missing slx_helpers/*.m files:\n"
        + "\n".join(f"  {fn}: {', '.join(hs)}" for fn, hs in missing.items())
    )


def test_build_chain_not_in_public_tools():
    names = _parse_public_tool_names()
    assert "simulink_build_chain" not in names, (
        "simulink_build_chain must not be in PUBLIC_TOOLS (helper slx_build_chain.m is missing)"
    )


def test_check_params_not_in_public_tools():
    names = _parse_public_tool_names()
    assert "simulink_check_params" not in names, (
        "simulink_check_params must not be in PUBLIC_TOOLS (placeholder implementation)"
    )


# ---------------------------------------------------------------------------
# Layer 2 — contract smoke (requires live MATLAB, mark with matlab)
# ---------------------------------------------------------------------------

def _get_matlab_session():
    """Import MatlabSession only when MATLAB is actually needed."""
    sys.path.insert(0, str(REPO_ROOT))
    from engine.matlab_session import MatlabSession
    return MatlabSession.get()


@pytest.mark.matlab
def test_contract_slx_set_block_params_shape():
    """slx_set_block_params must return ok+params_written even on error."""
    session = _get_matlab_session()
    result = session.call("slx_set_block_params", "nonexistent/Block", {}, nargout=1)
    assert isinstance(result, dict), "slx_set_block_params must return struct/dict"
    assert "ok" in result, "missing 'ok' field"
    assert isinstance(result.get("ok"), (bool, int)), "'ok' must be bool"
    assert "params_written" in result, "missing 'params_written'"
    assert "error_message" in result, "missing 'error_message'"
    if not bool(result.get("ok")):
        assert result.get("error_message"), "ok=False requires non-empty error_message"


@pytest.mark.matlab
def test_contract_slx_delete_block_shape():
    """slx_delete_block must return ok+error_message even on error."""
    session = _get_matlab_session()
    result = session.call("slx_delete_block", "nonexistent/Block", nargout=1)
    assert isinstance(result, dict)
    assert "ok" in result
    assert "error_message" in result
    if not bool(result.get("ok")):
        assert result.get("error_message")


@pytest.mark.matlab
def test_contract_slx_add_subsystem_shape():
    """slx_add_subsystem must return ok+block_path+error_message."""
    session = _get_matlab_session()
    result = session.call("slx_add_subsystem", "nonexistent/Sub", [], True, nargout=1)
    assert isinstance(result, dict)
    assert "ok" in result
    assert "block_path" in result
    assert "error_message" in result
    if not bool(result.get("ok")):
        assert result.get("error_message")


@pytest.mark.matlab
def test_contract_slx_trace_port_connections_shape():
    """slx_trace_port_connections must return ok+src+dsts+error_message."""
    session = _get_matlab_session()
    result = session.call(
        "slx_trace_port_connections", "nonexistent", "nonexistent/Block", "Outport", 1, nargout=1
    )
    assert isinstance(result, dict)
    assert "ok" in result
    assert "error_message" in result
    if not bool(result.get("ok")):
        assert result.get("error_message")
    else:
        assert "src" in result
        assert "dsts" in result
        assert "branch_count" in result
