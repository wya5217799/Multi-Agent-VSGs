"""Tests for engine.mcp_server public MCP contract."""
import asyncio
import os

import pytest


def test_public_tools_list_matches_expected_contract():
    from engine import mcp_server

    expected_names = [
        "harness_scenario_status",
        "harness_model_inspect",
        "harness_model_patch_verify",
        "harness_model_diagnose",
        "harness_model_report",
        "harness_train_smoke_start",
        "harness_train_smoke_poll",
        "simulink_load_model",
        "simulink_create_model",
        "simulink_close_model",
        "simulink_loaded_models",
        "simulink_bridge_status",
        "simulink_get_block_tree",
        "simulink_describe_block_ports",
        "simulink_trace_port_connections",
        "simulink_explore_block",
        "simulink_query_params",
        "simulink_set_block_params",
        "simulink_check_params",
        "simulink_preflight",
        "simulink_add_block",
        "simulink_add_subsystem",
        "simulink_connect_ports",
        "simulink_delete_block",
        "simulink_build_chain",
        "simulink_compile_diagnostics",
        "simulink_step_diagnostics",
        "simulink_solver_audit",
        "simulink_patch_and_verify",
        "simulink_run_script",
    ]

    assert [tool.__name__ for tool in mcp_server.PUBLIC_TOOLS] == expected_names


def test_public_tools_contract_has_stable_size():
    from engine import mcp_server

    assert len(mcp_server.PUBLIC_TOOLS) == 30


def test_prepare_process_environment_sets_project_root_cwd(monkeypatch, tmp_path):
    from engine import mcp_server

    monkeypatch.chdir(tmp_path)

    project_root = mcp_server._prepare_process_environment()

    assert project_root == mcp_server._project_root
    assert os.getcwd() == mcp_server._project_root


def test_query_params_schema_accepts_single_string_param_name():
    from engine import mcp_server

    tools = asyncio.run(mcp_server.mcp.list_tools())
    query_tool = next(tool for tool in tools if tool.name == "simulink_query_params")
    param_names_schema = query_tool.parameters["properties"]["param_names"]
    allowed_types = {
        entry.get("type")
        for entry in param_names_schema["anyOf"]
    }

    assert {"string", "array", "null"} <= allowed_types


def test_add_block_and_connect_ports_docs_explain_path_conventions():
    from engine import mcp_server

    tools = asyncio.run(mcp_server.mcp.list_tools())
    add_block_tool = next(tool for tool in tools if tool.name == "simulink_add_block")
    connect_tool = next(tool for tool in tools if tool.name == "simulink_connect_ports")

    assert "full block path" in add_block_tool.description.lower()
    assert "relative to system_path" in connect_tool.description.lower()


def test_server_instructions_prefer_harness_tools():
    from engine import mcp_server

    assert "prefer the harness_* task tools" in mcp_server.mcp.instructions.lower()
