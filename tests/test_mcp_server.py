"""Tests for engine.mcp_server public MCP contract."""
import asyncio
import os

import pytest


def test_public_tools_list_matches_expected_contract():
    from engine import mcp_server

    names = {tool.__name__ for tool in mcp_server.PUBLIC_TOOLS}

    # Training tools
    assert "training_status" in names
    assert "training_diagnose" in names
    assert "training_evaluate_run" in names
    assert "training_compare_runs" in names

    # Harness tools
    assert "harness_scenario_status" in names
    assert "harness_train_smoke_minimal" in names
    assert "harness_train_smoke_start" in names
    assert "harness_train_smoke_poll" in names

    # Core Simulink tools
    assert "simulink_load_model" in names
    assert "simulink_query_params" in names
    assert "simulink_run_script" in names
    assert "simulink_run_script_async" in names
    assert "simulink_poll_script" in names


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


def test_server_instructions_reference_agents_md_for_harness():
    from engine import mcp_server

    assert "agents.md" in mcp_server.mcp.instructions.lower()


