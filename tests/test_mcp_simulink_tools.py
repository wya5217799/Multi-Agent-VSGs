# tests/test_mcp_simulink_tools.py
"""Tests for engine.mcp_simulink_tools."""
from pathlib import Path

import pytest
from unittest.mock import ANY, MagicMock, patch


class TestSimulinkHelperInventory:
    def test_required_helper_files_exist(self):
        helper_dir = Path(__file__).resolve().parents[1] / "vsg_helpers"
        required = [
            "vsg_preflight.m",
            "vsg_describe_library_block.m",
            "vsg_create_model.m",
            "vsg_close_model.m",
            "vsg_describe_block_ports.m",
            "vsg_compile_diagnostics.m",
            "vsg_solver_audit.m",
            "vsg_check_params.m",
            "vsg_add_block.m",
            "vsg_connect_blocks.m",
            "vsg_run_quiet.m",
            "vsg_step_diagnostics.m",
            "vsg_patch_and_verify.m",
            "vsg_bulk_get_params.m",
        ]

        missing = [name for name in required if not (helper_dir / name).exists()]

        assert missing == []


class TestSimulinkInspectModel:
    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_returns_block_count_and_subsystems(self, mock_me):
        from engine.mcp_simulink_tools import simulink_inspect_model

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        mock_info = {
            "block_count": 42.0,
            "blocks": [{"path": "mdl/A", "type": "SubSystem", "name": "A", "key_params": {}}],
            "signal_count": 10.0,
            "subsystems": ["mdl/A"],
        }
        mock_eng.vsg_inspect_model = MagicMock(return_value=mock_info)

        result = simulink_inspect_model("test_model", depth=3)

        assert result["block_count"] == 42
        assert result["signal_count"] == 10
        assert len(result["subsystems"]) == 1


class TestSimulinkGetBlockParams:
    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_uses_batch_query_helper(self, mock_me):
        from engine.mcp_simulink_tools import simulink_get_block_params

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        mock_report = {
            "block": "mdl/Breaker_1",
            "params": {
                "R_closed": "0.001",
                "threshold": "0.5",
            },
            "error": "",
        }
        mock_eng.vsg_batch_query = MagicMock(return_value=mock_report)

        result = simulink_get_block_params("test_model", "mdl/Breaker_1")

        mock_eng.load_system.assert_called_once_with("test_model", nargout=0, stdout=ANY, stderr=ANY)
        assert result["R_closed"] == "0.001"
        assert result["threshold"] == "0.5"

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_multiple_blocks_returns_structured_items(self, mock_me):
        from engine.mcp_simulink_tools import simulink_get_multiple_block_params

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        mock_eng.vsg_batch_query_cell = MagicMock(return_value=[
            {"block": "mdl/G1", "params": {"Gain": "2"}, "error": ""},
            {"block": "mdl/G2", "params": {}, "error": "bad block"},
        ])

        result = simulink_get_multiple_block_params("test_model", ["mdl/G1", "mdl/G2"])

        assert len(result["items"]) == 2
        assert result["items"][0]["params"]["Gain"] == "2"
        assert result["items"][1]["error"] == "bad block"


class TestSimulinkMergedFacades:
    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_query_params_reads_all_dialog_params_via_batch_query(self, mock_me):
        from engine.mcp_simulink_tools import simulink_query_params

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_batch_query = MagicMock(return_value=[
            {"block": "mdl/G1", "params": {"Gain": "2"}, "error": ""},
            {"block": "mdl/G2", "params": {"Gain": "3"}, "error": ""},
        ])

        result = simulink_query_params("mdl", ["mdl/G1", "mdl/G2"])

        mock_eng.vsg_batch_query.assert_called_once_with(
            "mdl",
            ["mdl/G1", "mdl/G2"],
            nargout=1,
            stdout=ANY,
            stderr=ANY,
        )
        assert result["items"][1]["params"]["Gain"] == "3"
        assert result["items"][0]["missing_params"] == []

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_query_params_reads_selected_params_via_bulk_helper(self, mock_me):
        from engine.mcp_simulink_tools import simulink_query_params

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_bulk_get_params = MagicMock(return_value={
            "items": [{
                "block_path": "mdl/G1",
                "params": {"Gain": "2"},
                "missing_params": ["SampleTime"],
                "error": "",
            }]
        })

        result = simulink_query_params("mdl", ["mdl/G1"], ["Gain", "SampleTime"])

        mock_eng.vsg_bulk_get_params.assert_called_once_with(
            "mdl",
            ["mdl/G1"],
            ["Gain", "SampleTime"],
            nargout=1,
            stdout=ANY,
            stderr=ANY,
        )
        assert result["items"][0]["missing_params"] == ["SampleTime"]

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_query_params_accepts_single_param_name_string(self, mock_me):
        from engine.mcp_simulink_tools import simulink_query_params

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_bulk_get_params = MagicMock(return_value={
            "items": [{
                "block_path": "mdl/G1",
                "params": {"Gain": "2"},
                "missing_params": [],
                "error": "",
            }]
        })

        result = simulink_query_params("mdl", ["mdl/G1"], "Gain")

        mock_eng.vsg_bulk_get_params.assert_called_once_with(
            "mdl",
            ["mdl/G1"],
            ["Gain"],
            nargout=1,
            stdout=ANY,
            stderr=ANY,
        )
        assert result["items"][0]["params"]["Gain"] == "2"

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_query_params_splits_comma_separated_param_names(self, mock_me):
        from engine.mcp_simulink_tools import simulink_query_params

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_bulk_get_params = MagicMock(return_value={
            "items": [{
                "block_path": "mdl/G1",
                "params": {"Gain": "2", "SampleTime": "0"},
                "missing_params": [],
                "error": "",
            }]
        })

        result = simulink_query_params("mdl", ["mdl/G1"], "Gain, SampleTime")

        mock_eng.vsg_bulk_get_params.assert_called_once_with(
            "mdl",
            ["mdl/G1"],
            ["Gain", "SampleTime"],
            nargout=1,
            stdout=ANY,
            stderr=ANY,
        )
        assert result["items"][0]["params"]["SampleTime"] == "0"

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_connect_ports_uses_handle_mode_branching_by_default(self, mock_me):
        from engine.mcp_simulink_tools import simulink_connect_ports

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_add_line_by_handles = MagicMock(return_value={
            "ok": True,
            "line_handle": 401.0,
            "created_branch": True,
            "important_lines": [],
            "error_message": "",
        })

        result = simulink_connect_ports(
            "mdl",
            "11",
            "22",
            addressing="handle",
        )

        mock_eng.vsg_add_line_by_handles.assert_called_once_with(
            "mdl",
            11.0,
            22.0,
            True,
            True,
            nargout=1,
            stdout=ANY,
            stderr=ANY,
        )
        assert result["created_branch"] is True

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_connect_ports_rejects_unknown_addressing(self, mock_me):
        from engine.mcp_simulink_tools import simulink_connect_ports

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        with pytest.raises(ValueError, match="addressing"):
            simulink_connect_ports(
                "mdl",
                "src/1",
                "dst/1",
                addressing="handles",
            )

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_connect_ports_name_mode_rejects_model_prefixed_port_paths(self, mock_me):
        from engine.mcp_simulink_tools import simulink_connect_ports

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        with pytest.raises(ValueError, match="relative to system_path"):
            simulink_connect_ports(
                "mdl",
                "mdl/Const/1",
                "mdl/Term/1",
                addressing="name",
            )


class TestSimulinkStructuredOps:
    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_load_model_returns_loaded_models(self, mock_me):
        from engine.mcp_simulink_tools import simulink_load_model

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.eval = MagicMock(return_value=["mdl"])

        result = simulink_load_model("mdl")

        assert result["ok"] is True
        assert result["model_name"] == "mdl"
        assert result["loaded_models"] == ["mdl"]

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_load_model_resolves_repo_model_name_and_bootstraps_paths(self, mock_me):
        from engine.mcp_simulink_tools import simulink_load_model

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.eval = MagicMock(return_value=["NE39bus_v2"])

        result = simulink_load_model("NE39bus_v2")

        repo_root = Path(__file__).resolve().parents[1]
        expected_model = repo_root / "scenarios" / "new_england" / "simulink_models" / "NE39bus_v2.slx"
        expected_model_dir = str(expected_model.parent)
        expected_script_dir = str(expected_model.parent.parent / "matlab_scripts")

        mock_eng.load_system.assert_called_once_with(str(expected_model), nargout=0, stdout=ANY, stderr=ANY)
        addpath_paths = [call.args[0] for call in mock_eng.addpath.call_args_list]
        assert expected_model_dir in addpath_paths
        assert expected_script_dir in addpath_paths
        assert result["ok"] is True
        assert result["model_name"] == "NE39bus_v2"
        assert result["loaded_models"] == ["NE39bus_v2"]

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_query_params_reuses_repo_bootstrap_for_known_models(self, mock_me):
        from engine.mcp_simulink_tools import simulink_query_params

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_bulk_get_params = MagicMock(return_value={
            "items": [{
                "block_path": "NE39bus_v2/VSrc_ES1",
                "params": {"ReferenceBlock": "spsThreePhaseSourceLib/Three-Phase Source"},
                "missing_params": [],
                "error": "",
            }]
        })

        result = simulink_query_params(
            "NE39bus_v2",
            ["NE39bus_v2/VSrc_ES1"],
            ["ReferenceBlock"],
        )

        repo_root = Path(__file__).resolve().parents[1]
        expected_model = repo_root / "scenarios" / "new_england" / "simulink_models" / "NE39bus_v2.slx"
        expected_model_dir = str(expected_model.parent)
        expected_scenario_dir = str(expected_model.parent.parent)
        expected_script_dir = str(expected_model.parent.parent / "matlab_scripts")

        mock_eng.load_system.assert_called_once_with(str(expected_model), nargout=0, stdout=ANY, stderr=ANY)
        addpath_paths = [call.args[0] for call in mock_eng.addpath.call_args_list]
        assert expected_model_dir in addpath_paths
        assert expected_scenario_dir in addpath_paths
        assert expected_script_dir in addpath_paths
        mock_eng.vsg_bulk_get_params.assert_called_once_with(
            "NE39bus_v2",
            ["NE39bus_v2/VSrc_ES1"],
            ["ReferenceBlock"],
            nargout=1,
            stdout=ANY,
            stderr=ANY,
        )
        assert result["items"][0]["params"]["ReferenceBlock"] == "spsThreePhaseSourceLib/Three-Phase Source"

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_describe_block_ports_reuses_repo_bootstrap_for_known_models(self, mock_me):
        from engine.mcp_simulink_tools import simulink_describe_block_ports

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_describe_block_ports = MagicMock(return_value={
            "block_path": "NE39bus_v2/VSG_ES1",
            "ports": [],
            "error_message": "",
        })

        result = simulink_describe_block_ports("NE39bus_v2", "NE39bus_v2/VSG_ES1")

        repo_root = Path(__file__).resolve().parents[1]
        expected_model = repo_root / "scenarios" / "new_england" / "simulink_models" / "NE39bus_v2.slx"

        mock_eng.load_system.assert_called_once_with(str(expected_model), nargout=0, stdout=ANY, stderr=ANY)
        mock_eng.vsg_describe_block_ports.assert_called_once_with(
            "NE39bus_v2",
            "NE39bus_v2/VSG_ES1",
            nargout=1,
            stdout=ANY,
            stderr=ANY,
        )
        assert result["block_path"] == "NE39bus_v2/VSG_ES1"

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_get_block_tree_reuses_repo_bootstrap_for_known_models(self, mock_me):
        from engine.mcp_simulink_tools import simulink_get_block_tree

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_get_block_tree = MagicMock(return_value={
            "name": "VSG_ES1",
            "type": "SubSystem",
            "path": "NE39bus_v2/VSG_ES1",
            "children": [],
        })

        result = simulink_get_block_tree(
            "NE39bus_v2",
            root_path="NE39bus_v2/VSG_ES1",
            max_depth=4,
        )

        repo_root = Path(__file__).resolve().parents[1]
        expected_model = repo_root / "scenarios" / "new_england" / "simulink_models" / "NE39bus_v2.slx"

        mock_eng.load_system.assert_called_once_with(str(expected_model), nargout=0, stdout=ANY, stderr=ANY)
        mock_eng.vsg_get_block_tree.assert_called_once_with(
            "NE39bus_v2",
            "NE39bus_v2/VSG_ES1",
            4.0,
            nargout=1,
            stdout=ANY,
            stderr=ANY,
        )
        assert result["path"] == "NE39bus_v2/VSG_ES1"

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_run_script_bootstraps_known_model_reference_before_exec(self, mock_me):
        from engine.mcp_simulink_tools import simulink_run_script

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_run_quiet = MagicMock(return_value={
            "ok": True,
            "elapsed": 0.05,
            "n_warnings": 0.0,
            "n_errors": 0.0,
            "error_message": "",
            "important_lines": ["RESULT=spsThreePhaseSourceLib/Three-Phase Source"],
        })

        code = "disp(['RESULT=' get_param('NE39bus_v2/VSrc_ES1','ReferenceBlock')])"
        result = simulink_run_script(code, timeout_sec=30)

        repo_root = Path(__file__).resolve().parents[1]
        expected_model = repo_root / "scenarios" / "new_england" / "simulink_models" / "NE39bus_v2.slx"
        expected_model_dir = str(expected_model.parent)
        expected_scenario_dir = str(expected_model.parent.parent)
        expected_script_dir = str(expected_model.parent.parent / "matlab_scripts")

        mock_eng.load_system.assert_called_once_with(str(expected_model), nargout=0, stdout=ANY, stderr=ANY)
        addpath_paths = [call.args[0] for call in mock_eng.addpath.call_args_list]
        assert expected_model_dir in addpath_paths
        assert expected_scenario_dir in addpath_paths
        assert expected_script_dir in addpath_paths
        mock_eng.vsg_run_quiet.assert_called_once_with(code, nargout=1, background=True)
        assert result["ok"] is True
        assert result["important_lines"] == ["RESULT=spsThreePhaseSourceLib/Three-Phase Source"]

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_create_model_returns_loaded_models(self, mock_me):
        from engine.mcp_simulink_tools import simulink_create_model

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_create_model = MagicMock(return_value={
            "ok": True,
            "model_name": "mdl",
            "important_lines": ["Created model mdl"],
            "error_message": "",
        })
        mock_eng.eval = MagicMock(return_value=["mdl"])

        result = simulink_create_model("mdl")

        assert result["ok"] is True
        assert result["model_name"] == "mdl"

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_set_block_params_returns_summary(self, mock_me):
        from engine.mcp_simulink_tools import simulink_set_block_params

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_set_block_params = MagicMock(return_value={
            "ok": True,
            "block_path": "mdl/Gain",
            "params_written": 1,
            "important_lines": ["Updated 1 parameter(s) on mdl/Gain"],
            "error_message": "",
        })

        result = simulink_set_block_params("mdl", "mdl/Gain", {"Gain": "2"})

        assert result["ok"] is True
        assert result["params_written"] == 1

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_add_block_returns_summary(self, mock_me):
        from engine.mcp_simulink_tools import simulink_add_block

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_add_block = MagicMock(return_value={
            "ok": True,
            "block_path": "mdl/Gain",
            "important_lines": ["Added block mdl/Gain"],
            "error_message": "",
        })

        result = simulink_add_block("mdl", "simulink/Math Operations/Gain", "mdl/Gain", {"Gain": "2"})

        assert result["ok"] is True
        assert result["block_path"] == "mdl/Gain"

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_add_block_requires_full_destination_block_path(self, mock_me):
        from engine.mcp_simulink_tools import simulink_add_block

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        with pytest.raises(ValueError, match="full block path"):
            simulink_add_block("mdl", "simulink/Math Operations/Gain", "Gain", {"Gain": "2"})

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_connect_blocks_returns_summary(self, mock_me):
        from engine.mcp_simulink_tools import simulink_connect_blocks

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_connect_blocks = MagicMock(return_value={
            "ok": True,
            "important_lines": ["Connected A/1 -> B/1"],
            "error_message": "",
        })

        result = simulink_connect_blocks("mdl", "A/1", "B/1")

        assert result["ok"] is True

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_connect_blocks_accepts_system_path(self, mock_me):
        from engine.mcp_simulink_tools import simulink_connect_blocks

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_connect_blocks = MagicMock(return_value={
            "ok": True,
            "important_lines": ["Connected In1/1 -> Gain1/1"],
            "error_message": "",
        })

        result = simulink_connect_blocks("mdl", "In1/1", "Gain1/1", system_path="mdl/Sub1")

        assert result["ok"] is True

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_update_diagram_returns_summary(self, mock_me):
        from engine.mcp_simulink_tools import simulink_update_diagram

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_update_diagram = MagicMock(return_value={
            "ok": True,
            "important_lines": ["Updated diagram mdl"],
            "error_message": "",
        })

        result = simulink_update_diagram("mdl")

        assert result["ok"] is True

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_delete_line_returns_summary(self, mock_me):
        from engine.mcp_simulink_tools import simulink_delete_line

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_delete_line = MagicMock(return_value={
            "ok": True,
            "important_lines": ["Deleted line A/1 -> B/1"],
            "error_message": "",
        })

        result = simulink_delete_line("mdl", "A/1", "B/1")

        assert result["ok"] is True

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_delete_line_accepts_system_path(self, mock_me):
        from engine.mcp_simulink_tools import simulink_delete_line

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_delete_line = MagicMock(return_value={
            "ok": True,
            "important_lines": ["Deleted line In1/1 -> Gain1/1"],
            "error_message": "",
        })

        result = simulink_delete_line("mdl", "In1/1", "Gain1/1", system_path="mdl/Sub1")

        assert result["ok"] is True

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_add_annotation_returns_summary(self, mock_me):
        from engine.mcp_simulink_tools import simulink_add_annotation

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_add_annotation = MagicMock(return_value={
            "ok": True,
            "important_lines": ["Added annotation to mdl"],
            "error_message": "",
        })

        result = simulink_add_annotation("mdl", "hello", [10, 10, 80, 30])

        assert result["ok"] is True

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_set_block_position_returns_summary(self, mock_me):
        from engine.mcp_simulink_tools import simulink_set_block_position

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_set_block_position = MagicMock(return_value={
            "ok": True,
            "block_path": "mdl/Gain",
            "important_lines": ["Moved block mdl/Gain"],
            "error_message": "",
        })

        result = simulink_set_block_position("mdl", "mdl/Gain", [100, 100, 130, 130])

        assert result["ok"] is True

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_add_subsystem_returns_summary(self, mock_me):
        from engine.mcp_simulink_tools import simulink_add_subsystem

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_add_subsystem = MagicMock(return_value={
            "ok": True,
            "block_path": "mdl/Sub1",
            "important_lines": ["Added subsystem mdl/Sub1"],
            "error_message": "",
        })

        result = simulink_add_subsystem("mdl", "mdl/Sub1", [20, 20, 120, 120])

        assert result["ok"] is True
        assert result["block_path"] == "mdl/Sub1"

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_open_system_returns_summary(self, mock_me):
        from engine.mcp_simulink_tools import simulink_open_system

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_open_system = MagicMock(return_value={
            "ok": True,
            "system_path": "mdl/Sub1",
            "important_lines": ["Opened system mdl/Sub1"],
            "error_message": "",
        })

        result = simulink_open_system("mdl/Sub1")

        assert result["ok"] is True

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_list_ports_returns_lists(self, mock_me):
        from engine.mcp_simulink_tools import simulink_list_ports

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_list_ports = MagicMock(return_value={
            "system_path": "mdl/Sub1",
            "inports": ["mdl/Sub1/In1"],
            "outports": ["mdl/Sub1/Out1"],
        })

        result = simulink_list_ports("mdl/Sub1")

        assert result["inports"] == ["mdl/Sub1/In1"]
        assert result["outports"] == ["mdl/Sub1/Out1"]

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_autolayout_returns_summary(self, mock_me):
        from engine.mcp_simulink_tools import simulink_autolayout_subsystem

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_autolayout_subsystem = MagicMock(return_value={
            "ok": True,
            "system_path": "mdl/Sub1",
            "important_lines": ["Auto-arranged system mdl/Sub1"],
            "error_message": "",
        })

        result = simulink_autolayout_subsystem("mdl/Sub1")

        assert result["ok"] is True

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_build_chain_returns_summary(self, mock_me):
        from engine.mcp_simulink_tools import simulink_build_chain

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_build_chain = MagicMock(return_value={
            "ok": True,
            "system_path": "mdl/Sub1",
            "blocks_added": ["mdl/Sub1/G1", "mdl/Sub1/G2"],
            "important_lines": ["Built chain with 2 block(s) in mdl/Sub1"],
            "error_message": "",
        })

        result = simulink_build_chain(
            "mdl",
            "mdl/Sub1",
            [
                {"source_block": "simulink/Math Operations/Gain", "name": "G1", "params": {"Gain": "2"}},
                {"source_block": "simulink/Math Operations/Gain", "name": "G2", "params": {"Gain": "3"}},
            ],
            start_port="In1/1",
            end_port="Out1/1",
        )

        assert result["ok"] is True
        assert result["blocks_added"] == ["mdl/Sub1/G1", "mdl/Sub1/G2"]

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_build_chain_allows_explicit_ports(self, mock_me):
        from engine.mcp_simulink_tools import simulink_build_chain

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_build_chain = MagicMock(return_value={
            "ok": True,
            "system_path": "mdl/Sub1",
            "blocks_added": ["mdl/Sub1/Sum1", "mdl/Sub1/Gain1"],
            "important_lines": ["Built chain with 2 block(s) in mdl/Sub1"],
            "error_message": "",
        })

        result = simulink_build_chain(
            "mdl",
            "mdl/Sub1",
            [
                {"source_block": "simulink/Math Operations/Add", "name": "Sum1", "params": {"Inputs": "++"}, "input_port": "1", "output_port": "1"},
                {"source_block": "simulink/Math Operations/Gain", "name": "Gain1", "input_port": "1", "output_port": "1"},
            ],
            start_port="In1/1",
            end_port="Out1/1",
        )

        assert result["ok"] is True

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_build_signal_chain_returns_summary(self, mock_me):
        from engine.mcp_simulink_tools import simulink_build_signal_chain

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_build_chain = MagicMock(return_value={
            "ok": True,
            "system_path": "mdl/Sub1",
            "blocks_added": ["mdl/Sub1/Sum1", "mdl/Sub1/Gain1"],
            "important_lines": ["Built chain with 2 block(s) in mdl/Sub1"],
            "error_message": "",
        })

        result = simulink_build_signal_chain(
            "mdl",
            "mdl/Sub1",
            names=["Sum1", "Gain1"],
            source_blocks=["simulink/Math Operations/Add", "simulink/Math Operations/Gain"],
            params_list=[{"Inputs": "++"}, {"Gain": "2"}],
            start_port="In1/1",
            end_port="Out1/1",
        )

        assert result["ok"] is True

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_clone_subsystem_n_times_returns_clones(self, mock_me):
        from engine.mcp_simulink_tools import simulink_clone_subsystem_n_times

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_clone_subsystem_n_times = MagicMock(return_value={
            "ok": True,
            "clones": ["mdl/Sub2", "mdl/Sub3"],
            "important_lines": ["Cloned 2 subsystem(s) from mdl/Sub1"],
            "error_message": "",
        })

        result = simulink_clone_subsystem_n_times("mdl", "mdl/Sub1", "mdl/Sub", 2, start_index=2)

        assert result["ok"] is True
        assert result["clones"] == ["mdl/Sub2", "mdl/Sub3"]

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_build_vsg_stub_returns_subsystems(self, mock_me):
        from engine.mcp_simulink_tools import simulink_build_vsg_stub

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_build_vsg_stub = MagicMock(return_value={
            "ok": True,
            "system_path": "mdl",
            "subsystems": ["mdl/VSG_ES1", "mdl/VSG_ES2"],
            "important_lines": ["Built 2 VSG stub subsystem(s) under mdl"],
            "error_message": "",
        })

        result = simulink_build_vsg_stub("mdl", 2)

        assert result["ok"] is True
        assert result["subsystems"] == ["mdl/VSG_ES1", "mdl/VSG_ES2"]


class TestSimulinkListModels:
    def test_returns_list(self):
        from engine.mcp_simulink_tools import simulink_list_models
        result = simulink_list_models()
        assert isinstance(result, list)


class TestSimulinkDiagnosticsWave1:
    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_describe_block_ports_returns_structured_ports(self, mock_me):
        from engine.mcp_simulink_tools import simulink_describe_block_ports

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_describe_block_ports = MagicMock(return_value={
            "block_path": "mdl/Gain",
            "ports": [{
                "kind": "Inport",
                "index": 1.0,
                "handle": 101.0,
                "is_connected": True,
                "line_handles": [201.0],
                "connected_block_paths": ["mdl/In1"],
            }],
        })

        result = simulink_describe_block_ports("mdl", "mdl/Gain")

        assert result["block_path"] == "mdl/Gain"
        assert result["ports"][0]["kind"] == "Inport"
        assert result["ports"][0]["line_handles"] == [201]

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_trace_port_connections_returns_fanout_summary(self, mock_me):
        from engine.mcp_simulink_tools import simulink_trace_port_connections

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_trace_port_connections = MagicMock(return_value={
            "ok": True,
            "src": {"block_path": "mdl/Gain", "port_kind": "Outport", "port_index": 1.0},
            "dsts": [
                {"block_path": "mdl/Out1", "port_kind": "Inport", "port_index": 1.0},
                {"block_path": "mdl/Terminator", "port_kind": "Inport", "port_index": 1.0},
            ],
            "branch_count": 1.0,
            "line_handle": 301.0,
            "all_connected_ports": [
                "mdl/Gain:Outport:1",
                "mdl/Out1:Inport:1",
                "mdl/Terminator:Inport:1",
            ],
            "error_message": "",
        })

        result = simulink_trace_port_connections("mdl", "mdl/Gain", "Outport", 1)

        assert result["ok"] is True
        assert result["branch_count"] == 1
        assert len(result["dsts"]) == 2

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_add_line_by_handles_returns_line_metadata(self, mock_me):
        from engine.mcp_simulink_tools import simulink_add_line_by_handles

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_add_line_by_handles = MagicMock(return_value={
            "ok": True,
            "line_handle": 401.0,
            "created_branch": False,
            "error_message": "",
            "important_lines": ["Connected handle 11 -> 22"],
        })

        result = simulink_add_line_by_handles("mdl", 11, 22)

        assert result["ok"] is True
        assert result["line_handle"] == 401
        assert result["created_branch"] is False

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_compile_diagnostics_returns_structured_errors(self, mock_me):
        from engine.mcp_simulink_tools import simulink_compile_diagnostics

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_compile_diagnostics = MagicMock(return_value={
            "ok": False,
            "mode": "update",
            "errors": [{
                "block_path": "mdl/Const",
                "param_name": "Value",
                "message": "Undefined function or variable 'missing_var'.",
                "severity": "error",
                "phase": "update",
            }],
            "warnings": [],
            "raw_summary": "Undefined variable during update.",
        })

        result = simulink_compile_diagnostics("mdl", mode="update")

        assert result["ok"] is False
        assert result["errors"][0]["block_path"] == "mdl/Const"
        assert result["errors"][0]["phase"] == "update"

    @patch("engine.mcp_simulink_tools.MatlabSession.get")
    def test_step_diagnostics_maps_engine_timeout(self, mock_get):
        from engine.exceptions import MatlabCallError
        from engine.mcp_simulink_tools import simulink_step_diagnostics

        mock_session = MagicMock()

        def fake_call(func_name, *args, **kwargs):
            if func_name == "vsg_step_diagnostics":
                raise MatlabCallError(
                    "vsg_step_diagnostics",
                    ("mdl", 0.0, 0.1),
                    "Timed out after 5s",
                )
            return None

        mock_session.call.side_effect = fake_call
        mock_get.return_value = mock_session

        result = simulink_step_diagnostics("mdl", 0.0, 0.1, timeout_sec=5)

        assert result["ok"] is False
        assert result["status"] == "engine_timeout"
        assert result["timed_out_in"] == "python"

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_solver_audit_returns_solver_config_summary(self, mock_me):
        from engine.mcp_simulink_tools import simulink_solver_audit

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_solver_audit = MagicMock(return_value={
            "ok": True,
            "model_solver": {
                "SolverType": "Variable-step",
                "Solver": "ode45",
                "MaxStep": "auto",
                "RelTol": "1e-3",
                "AbsTol": "auto",
                "StopTime": "10.0",
            },
            "solver_type": "Variable-step",
            "max_step": "auto",
            "rel_tol": "1e-3",
            "abs_tol": "auto",
            "stop_time": "10.0",
            "diagnostics": {"AlgebraicLoopMsg": "warning"},
            "solver_config_blocks": [{
                "block_path": "mdl/Solver Configuration",
                "mask_type": "Solver Configuration",
                "params": {"UseLocalSolver": "off"},
                "missing_expected_params": ["MaxNonlinIter"],
            }],
            "suspicions": ["Local solver disabled"],
        })

        result = simulink_solver_audit("mdl")

        assert result["ok"] is True
        assert result["solver_type"] == "Variable-step"
        assert result["solver_config_blocks"][0]["missing_expected_params"] == ["MaxNonlinIter"]


class TestSimulinkDiagnosticsWave2:
    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_prepare_model_workspace_returns_loaded_vars_and_callbacks(self, mock_me):
        from engine.mcp_simulink_tools import simulink_prepare_model_workspace

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_prepare_model_workspace = MagicMock(return_value={
            "ok": True,
            "ran_scripts": ["prep_script_wave2"],
            "vars_loaded": ["base_gain_wave2", "script_value_wave2", "callback_value_wave2"],
            "callback_errors": [],
            "warnings": [],
        })

        result = simulink_prepare_model_workspace(
            "mdl",
            "C:/tmp/modeldir",
            run_preload=True,
            scripts=["prep_script_wave2"],
            base_vars={"base_gain_wave2": 3.0},
        )

        assert result["ok"] is True
        assert "script_value_wave2" in result["vars_loaded"]
        assert result["callback_errors"] == []

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_event_source_audit_marks_back_inherited_sample_time(self, mock_me):
        from engine.mcp_simulink_tools import simulink_event_source_audit

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_event_source_audit = MagicMock(return_value={
            "ok": True,
            "items": [{
                "block_path": "mdl/BrkCtrl_1",
                "block_type": "Step",
                "sample_time": "-1",
                "time": "0.49",
                "before": "0",
                "after": "1",
                "suspicious": True,
                "reason": "SampleTime=-1; event occurs near warmup boundary",
            }],
            "summary": [
                "1 event blocks use back-inherited sample time",
                "1 breaker event occurs inside warmup window boundary",
            ],
        })

        result = simulink_event_source_audit("mdl", warmup_end=0.5, boundary_eps=0.02)

        assert result["ok"] is True
        assert result["items"][0]["suspicious"] is True
        assert result["items"][0]["sample_time"] == "-1"

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_patch_and_verify_returns_readback_and_smoke_summary(self, mock_me):
        from engine.mcp_simulink_tools import simulink_patch_and_verify

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_patch_and_verify = MagicMock(return_value={
            "ok": True,
            "applied_edits": [{
                "block_path": "mdl/Const",
                "params": {"Value": "2"},
            }],
            "readback": [{
                "block_path": "mdl/Const",
                "params": {"Value": "2"},
                "error": "",
            }],
            "update_ok": True,
            "smoke_test_ok": True,
            "smoke_test_summary": {
                "status": "success",
                "sim_time_reached": 0.1,
            },
            "warnings": [],
            "errors": [],
        })

        result = simulink_patch_and_verify(
            "mdl",
            edits=[{"block_path": "mdl/Const", "params": {"Value": "2"}}],
            run_update=True,
            smoke_test_stop_time=0.1,
            timeout_sec=10,
        )

        assert result["ok"] is True
        assert result["readback"][0]["params"]["Value"] == "2"
        assert result["smoke_test_summary"]["status"] == "success"


class TestSimulinkDiagnosticsWave3:
    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_describe_library_block_returns_port_schema(self, mock_me):
        from engine.mcp_simulink_tools import simulink_describe_library_block

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_describe_library_block = MagicMock(return_value={
            "exists": True,
            "dialog_params": ["Value", "SampleTime"],
            "default_values": {"Value": "1", "SampleTime": "inf"},
            "port_schema": [{
                "name": "Outport",
                "label": "",
                "domain": "",
                "port_type": "simulink",
            }],
            "mask_type": "",
            "reference_block": "simulink/Sources/Constant",
            "error": "",
        })

        result = simulink_describe_library_block("simulink/Sources/Constant")

        assert result["exists"] is True
        assert result["default_values"]["Value"] == "1"
        assert result["reference_block"] == "simulink/Sources/Constant"

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_find_blocks_by_mask_or_ref_filters_matches(self, mock_me):
        from engine.mcp_simulink_tools import simulink_find_blocks_by_mask_or_ref

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_find_blocks_by_mask_or_ref = MagicMock(return_value={
            "matches": [
                "mdl/Const1",
                "mdl/Const2",
            ],
        })

        result = simulink_find_blocks_by_mask_or_ref(
            "mdl",
            reference_block="simulink/Sources/Constant",
            name_regex="Const",
        )

        assert result["matches"] == ["mdl/Const1", "mdl/Const2"]

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_clone_model_returns_new_model_name(self, mock_me):
        from engine.mcp_simulink_tools import simulink_clone_model

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_clone_model = MagicMock(return_value={
            "ok": True,
            "dst_file": "C:/tmp/copied_model.slx",
            "loaded_model_name": "copied_model",
            "error_message": "",
        })

        result = simulink_clone_model(
            "src_model",
            "copied_model",
            "C:/tmp/src",
            "C:/tmp/dst",
            overwrite=True,
        )

        assert result["ok"] is True
        assert result["loaded_model_name"] == "copied_model"


class TestSimulinkDiagnosticsWave4:
    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_delete_block_with_connections_returns_deleted_lines(self, mock_me):
        from engine.mcp_simulink_tools import simulink_delete_block_with_connections

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_delete_block_with_connections = MagicMock(return_value={
            "ok": True,
            "block_path": "mdl/Gain",
            "deleted_lines": [101.0, 102.0],
            "error_message": "",
        })

        result = simulink_delete_block_with_connections("mdl", "mdl/Gain", delete_attached_lines=True)

        assert result["ok"] is True
        assert result["deleted_lines"] == [101, 102]

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_summarize_signal_fanout_returns_connected_blocks(self, mock_me):
        from engine.mcp_simulink_tools import simulink_summarize_signal_fanout

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_summarize_signal_fanout = MagicMock(return_value={
            "block_path": "mdl/Gain",
            "outport_index": 1.0,
            "destinations": [
                {"block_path": "mdl/Out1", "port_kind": "Inport", "port_index": 1.0},
                {"block_path": "mdl/Terminator", "port_kind": "Inport", "port_index": 1.0},
            ],
            "fanout_count": 2.0,
            "line_handle": 501.0,
            "error_message": "",
        })

        result = simulink_summarize_signal_fanout("mdl", "mdl/Gain", 1)

        assert result["fanout_count"] == 2
        assert result["destinations"][1]["block_path"] == "mdl/Terminator"

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_bulk_get_params_returns_matrix_like_items(self, mock_me):
        from engine.mcp_simulink_tools import simulink_bulk_get_params

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_bulk_get_params = MagicMock(return_value={
            "items": [
                {
                    "block_path": "mdl/Const1",
                    "params": {"Value": "1", "SampleTime": "inf"},
                    "missing_params": [],
                    "error": "",
                },
                {
                    "block_path": "mdl/Const2",
                    "params": {"Value": "2"},
                    "missing_params": ["SampleTime"],
                    "error": "",
                },
            ]
        })

        result = simulink_bulk_get_params("mdl", ["mdl/Const1", "mdl/Const2"], ["Value", "SampleTime"])

        assert result["items"][0]["params"]["SampleTime"] == "inf"
        assert result["items"][1]["missing_params"] == ["SampleTime"]


class TestSimulinkDiagnosticsWave5:
    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_model_diff_returns_block_param_and_line_changes(self, mock_me):
        from engine.mcp_simulink_tools import simulink_model_diff

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_model_diff = MagicMock(return_value={
            "added_blocks": ["NewGain"],
            "removed_blocks": ["OldGain"],
            "param_changes": [{
                "block_path": "Const1",
                "param_name": "Value",
                "before": "1",
                "after": "2",
            }],
            "added_lines": ["Const1:Outport:1->NewGain:Inport:1"],
            "removed_lines": ["OldGain:Outport:1->Out1:Inport:1"],
        })

        result = simulink_model_diff("before_model", "after_model")

        assert result["added_blocks"] == ["NewGain"]
        assert result["param_changes"][0]["param_name"] == "Value"
        assert result["removed_lines"] == ["OldGain:Outport:1->Out1:Inport:1"]


class TestSimulinkDiagnosticsWave6:
    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_solver_warning_summary_collapses_duplicate_warnings(self, mock_me):
        from engine.mcp_simulink_tools import simulink_solver_warning_summary

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_solver_warning_summary = MagicMock(return_value={
            "ok": True,
            "first_occurrence_time": 4.9008,
            "last_occurrence_time": 4.9008,
            "unique_warning_types": 1.0,
            "collapsed_warnings": [{
                "signature": "warning: minimum step size violation at t=<num>; min step = <num>",
                "count": 3.0,
                "first_time": 4.9008,
                "last_time": 4.9008,
                "example": "Warning: Minimum step size violation at t=4.9008; min step = 1.74e-14",
            }],
            "stiffness_detected": True,
            "likely_stuck_time": 4.9008,
            "suggested_next_checks": [
                "Audit discontinuous event sources near the stuck time.",
                "Reduce MaxStep or tighten solver diagnostics.",
            ],
            "raw_summary": "Repeated minimum step warnings detected.",
            "error_message": "",
        })

        result = simulink_solver_warning_summary(
            "mdl",
            "disp('Warning: Minimum step size violation at t=4.9008; min step = 1.74e-14')",
            timeout_sec=10,
        )

        assert result["ok"] is True
        assert result["unique_warning_types"] == 1
        assert result["collapsed_warnings"][0]["count"] == 3
        assert result["stiffness_detected"] is True
        assert result["likely_stuck_time"] == pytest.approx(4.9008)

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_signal_snapshot_allows_partial_reads(self, mock_me):
        from engine.mcp_simulink_tools import simulink_signal_snapshot

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_signal_snapshot = MagicMock(return_value={
            "time_s": 0.5,
            "values": {
                "logsout:sine_logged": 1.25,
                "toworkspace:sine_ws": 1.25,
                "block:mdl/Gain:1": 2.5,
            },
            "missing_signals": ["logsout:missing_signal"],
            "units": {
                "logsout:sine_logged": "",
                "toworkspace:sine_ws": "",
                "block:mdl/Gain:1": "",
            },
            "read_ok": True,
            "warnings": ["1 signals could not be resolved."],
        })

        result = simulink_signal_snapshot(
            "mdl",
            0.5,
            [
                "logsout:sine_logged",
                "toworkspace:sine_ws",
                {"block_path": "mdl/Gain", "port_index": 1},
                "logsout:missing_signal",
            ],
            allow_partial=True,
        )

        assert result["read_ok"] is True
        assert result["values"]["block:mdl/Gain:1"] == pytest.approx(2.5)
        assert result["missing_signals"] == ["logsout:missing_signal"]


@pytest.mark.slow
def test_step_diagnostics_counts_localized_warnings_from_real_matlab():
    from engine.matlab_session import MatlabSession
    from engine.mcp_simulink_tools import (
        simulink_add_block,
        simulink_close_model,
        simulink_connect_blocks,
        simulink_create_model,
        simulink_step_diagnostics,
    )

    MatlabSession._instances.clear()
    model_name = "codex_tmp_diag_localized"

    try:
        simulink_create_model(model_name, open_model=False)
        simulink_add_block(
            model_name,
            "simulink/Sources/Constant",
            f"{model_name}/Const",
            {"Position": "[30 30 60 60]"},
        )
        simulink_add_block(
            model_name,
            "simulink/Math Operations/Gain",
            f"{model_name}/Gain",
            {"Position": "[110 30 140 60]"},
        )
        simulink_add_block(
            model_name,
            "simulink/Sinks/Terminator",
            f"{model_name}/Term",
            {"Position": "[190 30 220 60]"},
        )
        simulink_connect_blocks(model_name, "Const/1", "Gain/1")
        simulink_connect_blocks(model_name, "Gain/1", "Term/1")

        result = simulink_step_diagnostics(model_name, 0.0, 0.1, timeout_sec=10)
    except RuntimeError as exc:
        pytest.skip(f"MATLAB integration unavailable: {exc}")
    finally:
        try:
            simulink_close_model(model_name, save=False)
        except RuntimeError:
            pass

    assert result["ok"] is True
    assert result["warning_count"] == 1
    assert len(result["top_warnings"]) == 1
    assert ("warning" in result["top_warnings"][0]["example"].lower()) or ("警告" in result["top_warnings"][0]["example"])


@pytest.mark.slow
def test_preflight_finds_sps_controlled_voltage_source_from_real_matlab():
    from engine.matlab_session import MatlabSession
    from engine.mcp_simulink_tools import simulink_preflight

    MatlabSession._instances.clear()

    try:
        result = simulink_preflight("sps_lib", "Controlled Voltage Source")
    except RuntimeError as exc:
        pytest.skip(f"MATLAB integration unavailable: {exc}")

    assert result["found"] is True
    assert "Amplitude" in result["params_main"]
    port_types = [port["port_type"] for port in result["ports"]]
    assert "Inport" in port_types
    assert "LConn" in port_types
    assert "RConn" in port_types


@pytest.mark.slow
def test_run_script_bootstraps_known_model_reference_from_real_matlab():
    from engine.matlab_session import MatlabSession
    from engine.mcp_simulink_tools import simulink_run_script

    MatlabSession._instances.clear()

    try:
        result = simulink_run_script(
            "disp(['RESULT=' get_param('NE39bus_v2/VSrc_ES1','ReferenceBlock')])",
            timeout_sec=30,
        )
    except RuntimeError as exc:
        pytest.skip(f"MATLAB integration unavailable: {exc}")

    assert result["ok"] is True
    assert any(
        "RESULT=spsThreePhaseSourceLib/Three-Phase Source" in line
        for line in result["important_lines"]
    )


class TestConversionHelpers:
    def test_to_list_converts_generic_iterables(self):
        from engine.mcp_simulink_tools import _to_list

        assert _to_list(("a", "b")) == ["a", "b"]

    def test_to_list_preserves_numeric_scalar(self):
        from engine.mcp_simulink_tools import _to_list

        assert _to_list(42) == [42]
        assert isinstance(_to_list(42)[0], int)

    # OPT-5: _to_list should preserve int and float types (not stringify them)
    def test_to_list_preserves_int_values(self):
        from engine.mcp_simulink_tools import _to_list

        result = _to_list([1, 2, 3])
        assert result == [1, 2, 3]
        assert all(isinstance(v, int) for v in result)

    def test_to_list_preserves_float_values(self):
        from engine.mcp_simulink_tools import _to_list

        result = _to_list([1.5, 2.718, 3.14])
        assert result[0] == 1.5
        assert isinstance(result[0], float)

    def test_to_list_still_stringifies_other_scalars(self):
        from engine.mcp_simulink_tools import _to_list

        # bytes and other non-numeric scalars should still become strings
        result = _to_list([b"hello"])
        assert result == ["b'hello'"]


class TestBootstrapCache:
    """OPT-1: _ensure_model_bootstrapped must not call load_system twice for the same model."""

    def setup_method(self):
        from engine.matlab_session import MatlabSession
        # Clearing _instances creates a new session with empty _bootstrapped cache
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_second_call_skips_load_system(self, mock_me):
        from engine.mcp_simulink_tools import simulink_get_block_params

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_batch_query = MagicMock(return_value={
            "block": "mdl/A", "params": {"Gain": "1"}, "error": "",
        })

        simulink_get_block_params("mdl", "mdl/A")
        simulink_get_block_params("mdl", "mdl/A")

        # load_system should only have been called once across both tool calls
        assert mock_eng.load_system.call_count == 1

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_different_models_each_call_load_system_once(self, mock_me):
        from engine.mcp_simulink_tools import simulink_get_block_params

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_batch_query = MagicMock(return_value={
            "block": "mdl/A", "params": {}, "error": "",
        })

        simulink_get_block_params("mdl_a", "mdl_a/X")
        simulink_get_block_params("mdl_b", "mdl_b/X")
        simulink_get_block_params("mdl_a", "mdl_a/Y")  # second call, same model

        # mdl_a loaded once, mdl_b loaded once → total 2
        assert mock_eng.load_system.call_count == 2

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_session_bootstrapped_attribute_is_populated_after_first_call(self, mock_me):
        from engine.matlab_session import MatlabSession
        from engine.mcp_simulink_tools import simulink_get_block_params

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_batch_query = MagicMock(return_value={
            "block": "mdl/A", "params": {}, "error": "",
        })

        simulink_get_block_params("mdl", "mdl/A")

        session = MatlabSession.get()
        # Real cache lives on the session instance, not a module global
        assert hasattr(session, "_bootstrapped")
        assert isinstance(session._bootstrapped, set)
        assert "mdl" in session._bootstrapped


class TestDeprecatedToolWarnings:
    """OPT-2: superseded tools must emit DeprecationWarning."""

    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_get_block_params_emits_deprecation_warning(self, mock_me):
        from engine.mcp_simulink_tools import simulink_get_block_params

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_batch_query = MagicMock(return_value={
            "block": "mdl/A", "params": {}, "error": "",
        })

        with pytest.warns(DeprecationWarning, match="simulink_query_params"):
            simulink_get_block_params("mdl", "mdl/A")

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_get_multiple_block_params_emits_deprecation_warning(self, mock_me):
        from engine.mcp_simulink_tools import simulink_get_multiple_block_params

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_batch_query_cell = MagicMock(return_value=[])

        with pytest.warns(DeprecationWarning, match="simulink_query_params"):
            simulink_get_multiple_block_params("mdl", ["mdl/A"])

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_add_line_by_handles_emits_deprecation_warning(self, mock_me):
        from engine.mcp_simulink_tools import simulink_add_line_by_handles

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_add_line_by_handles = MagicMock(return_value={
            "ok": True, "line_handle": 1.0,
            "created_branch": False, "important_lines": [], "error_message": "",
        })

        with pytest.warns(DeprecationWarning, match="simulink_connect_ports"):
            simulink_add_line_by_handles("mdl", 11, 22)


class TestStepDiagnosticsSimscapeConstraint:
    """OPT-3: simulink_step_diagnostics should detect and structure Simscape constraint violations."""

    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_detects_simscape_constraint_violation_in_error_message(self, mock_me):
        from engine.mcp_simulink_tools import simulink_step_diagnostics

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_step_diagnostics = MagicMock(return_value={
            "ok": False,
            "status": "sim_error",
            "elapsed_sec": 1.2,
            "sim_time_reached": 0.91,
            "warning_count": 0.0,
            "error_count": 1.0,
            "top_warnings": [],
            "top_errors": [{
                "signature": "simscape_dae_failure",
                "count": 1.0,
                "example": (
                    "Derivative of state '3' in block 'kundur_vsg/Breaker_1' at time 0.91"
                    " is not finite. There may be a discontinuity in the state or its "
                    "derivative. If a discontinuity is expected, use Events."
                ),
                "time": 0.91,
            }],
            "timed_out_in": "",
            "raw_summary": "Simulation failed at t=0.91",
        })

        result = simulink_step_diagnostics("kundur_vsg", 0.0, 2.0)

        assert "simscape_constraint_violation" in result
        cv = result["simscape_constraint_violation"]
        assert cv["detected"] is True
        assert cv["approx_time"] == pytest.approx(0.91)
        assert "topology" in cv["hint"].lower() or "fastrestart" in cv["hint"].lower()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_no_violation_field_when_sim_succeeds(self, mock_me):
        from engine.mcp_simulink_tools import simulink_step_diagnostics

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_step_diagnostics = MagicMock(return_value={
            "ok": True,
            "status": "ok",
            "elapsed_sec": 0.5,
            "sim_time_reached": 2.0,
            "warning_count": 0.0,
            "error_count": 0.0,
            "top_warnings": [],
            "top_errors": [],
            "timed_out_in": "",
            "raw_summary": "",
        })

        result = simulink_step_diagnostics("kundur_vsg", 0.0, 2.0)

        cv = result.get("simscape_constraint_violation", {})
        assert cv.get("detected", False) is False

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_detects_constraint_in_raw_summary_when_errors_empty(self, mock_me):
        from engine.mcp_simulink_tools import simulink_step_diagnostics

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_step_diagnostics = MagicMock(return_value={
            "ok": False,
            "status": "sim_error",
            "elapsed_sec": 0.95,
            "sim_time_reached": 0.91,
            "warning_count": 0.0,
            "error_count": 0.0,
            "top_warnings": [],
            "top_errors": [],
            "timed_out_in": "",
            "raw_summary": "Derivative of state '1' is not finite at t=0.910",
        })

        result = simulink_step_diagnostics("kundur_vsg", 0.0, 2.0)

        cv = result.get("simscape_constraint_violation", {})
        assert cv.get("detected") is True


class TestSolverAuditFastRestartWarning:
    """OPT-4: simulink_solver_audit should warn when FastRestart + event sources are both present."""

    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_no_warning_when_fastrestart_off(self, mock_me):
        from engine.mcp_simulink_tools import simulink_solver_audit

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_solver_audit = MagicMock(return_value={
            "ok": True,
            "model_solver": {"FastRestart": "off"},
            "solver_type": "ode23t",
            "max_step": "auto",
            "rel_tol": "1e-3",
            "abs_tol": "auto",
            "stop_time": "10",
            "diagnostics": {},
            "solver_config_blocks": [],
            "suspicions": [],
        })

        result = simulink_solver_audit("mdl")

        fastrestart_warnings = [
            s for s in result["suspicions"]
            if "fastrestart" in s.lower() or "fast_restart" in s.lower()
               or "FastRestart" in s
        ]
        assert fastrestart_warnings == []

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_warns_when_fastrestart_on_and_step_block_in_model(self, mock_me):
        from engine.mcp_simulink_tools import simulink_solver_audit

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng
        mock_eng.vsg_solver_audit = MagicMock(return_value={
            "ok": True,
            "model_solver": {"FastRestart": "on"},
            "solver_type": "ode23t",
            "max_step": "auto",
            "rel_tol": "1e-3",
            "abs_tol": "auto",
            "stop_time": "10",
            "diagnostics": {},
            "solver_config_blocks": [],
            "suspicions": [],
        })
        # Simulate find_system finding a Step block
        mock_eng.find_system = MagicMock(return_value=["mdl/BrkCtrl"])

        result = simulink_solver_audit("mdl")

        fastrestart_warnings = [
            s for s in result["suspicions"]
            if "FastRestart" in s or "fastrestart" in s.lower()
        ]
        assert len(fastrestart_warnings) >= 1
        combined = " ".join(fastrestart_warnings).lower()
        assert "topology" in combined or "step" in combined or "discrete" in combined
