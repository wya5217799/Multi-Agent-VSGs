# tests/test_workspace_deps_kundur.py
"""Phase B: simulink_block_workspace_dependency unit tests.

Mocks the MATLAB engine (no live MATLAB needed) and verifies:
1. Python entry validates input args.
2. Helper return is correctly normalized into per-var verdict dicts.
3. Fixture-driven expectations: known DEAD vars show DEAD, known LIVE
   vars show LIVE.

Live-MATLAB integration tests live under probes/ — see
probes/kundur/v3_dryrun/ for an end-to-end probe that runs the
helper against the actual loaded v3 model.

Plan §3.B.5.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "kundur_workspace_vars.json"


@pytest.fixture(scope="module")
def kundur_fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


class TestInputValidation:
    """Python entry-side schema validation (no MATLAB engine needed)."""

    def setup_method(self) -> None:
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    def test_rejects_non_list_workspace_vars(self) -> None:
        from engine.mcp_simulink_tools import simulink_block_workspace_dependency
        with pytest.raises(ValueError, match="must be list"):
            simulink_block_workspace_dependency("any_model", "not_a_list")  # type: ignore[arg-type]

    def test_rejects_empty_workspace_vars(self) -> None:
        from engine.mcp_simulink_tools import simulink_block_workspace_dependency
        with pytest.raises(ValueError, match="non-empty"):
            simulink_block_workspace_dependency("any_model", [])

    def test_rejects_non_str_elements(self) -> None:
        from engine.mcp_simulink_tools import simulink_block_workspace_dependency
        with pytest.raises(ValueError, match="must be list"):
            simulink_block_workspace_dependency("any_model", ["ok", 42])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# Mocked-MATLAB return-shape tests
# ---------------------------------------------------------------------------


class TestReturnShape:
    """Verify normalization of MATLAB-side return into per-var dicts."""

    def setup_method(self) -> None:
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_normalizes_live_and_dead_verdicts(self, mock_me) -> None:
        """Mock helper returns: 1 LIVE var (Pm_step_amp_1) + 1 DEAD var (LoadStep_t_1)."""
        from engine.mcp_simulink_tools import simulink_block_workspace_dependency

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        mock_eng.slx_block_workspace_deps = MagicMock(return_value={
            "model": "kundur_cvs_v3",
            "vars": {
                "Pm_step_amp_1": {
                    "var_name": "Pm_step_amp_1",
                    "consumed_by_blocks": [{
                        "block_path": "kundur_cvs_v3/Pm_step_amp_c_ES1",
                        "param": "Value",
                        "expression": "Pm_step_amp_1",
                    }],
                    "consumer_count": 1,
                    "verdict": "LIVE",
                },
                "LoadStep_t_1": {
                    "var_name": "LoadStep_t_1",
                    "consumed_by_blocks": [],
                    "consumer_count": 0,
                    "verdict": "DEAD",
                },
            },
            "scan_summary": {"blocks_scanned": 412.0, "params_scanned": 1840.0, "elapsed_sec": 1.2},
        })

        result = simulink_block_workspace_dependency(
            "kundur_cvs_v3", ["Pm_step_amp_1", "LoadStep_t_1"]
        )

        assert result["model"] == "kundur_cvs_v3"
        assert result["vars"]["Pm_step_amp_1"]["verdict"] == "LIVE"
        assert result["vars"]["Pm_step_amp_1"]["consumer_count"] == 1
        assert result["vars"]["Pm_step_amp_1"]["consumed_by_blocks"][0]["block_path"].endswith("Pm_step_amp_c_ES1")

        assert result["vars"]["LoadStep_t_1"]["verdict"] == "DEAD"
        assert result["vars"]["LoadStep_t_1"]["consumer_count"] == 0
        assert result["vars"]["LoadStep_t_1"]["consumed_by_blocks"] == []

        assert result["scan_summary"]["blocks_scanned"] == 412
        assert result["scan_summary"]["params_scanned"] == 1840

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_handles_missing_var_gracefully(self, mock_me) -> None:
        """If MATLAB doesn't return an entry for a requested var (shouldn't happen,
        but guard anyway), Python entry returns DEAD with zero consumers."""
        from engine.mcp_simulink_tools import simulink_block_workspace_dependency

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        mock_eng.slx_block_workspace_deps = MagicMock(return_value={
            "model": "test_model",
            "vars": {},
            "scan_summary": {"blocks_scanned": 0.0, "params_scanned": 0.0, "elapsed_sec": 0.0},
        })

        result = simulink_block_workspace_dependency("test_model", ["never_returned"])

        assert result["vars"]["never_returned"]["verdict"] == "DEAD"
        assert result["vars"]["never_returned"]["consumer_count"] == 0


# ---------------------------------------------------------------------------
# Fixture-driven expectations (no MATLAB call — verifies the fixture file
# itself is well-formed and contains the verdicts plan §3.B.5 prescribes).
# Live integration goes through probes/kundur/v3_dryrun/.
# ---------------------------------------------------------------------------


class TestFixtureSelfConsistency:
    """The fixture must contain the v3 + v2 expectations the plan declares."""

    def test_v3_known_dead_vars_present(self, kundur_fixture) -> None:
        v3 = kundur_fixture["kundur_cvs_v3"]["expectations"]
        for dead_var in ("G_perturb_1_S", "LoadStep_t_1", "LoadStep_amp_1"):
            assert dead_var in v3, f"fixture missing {dead_var}"
            assert v3[dead_var]["verdict"] == "DEAD"

    def test_v3_known_live_vars_present(self, kundur_fixture) -> None:
        v3 = kundur_fixture["kundur_cvs_v3"]["expectations"]
        for live_var in (
            "wn_const",
            "Pm_step_amp_1", "Pm_step_amp_2", "Pm_step_amp_3", "Pm_step_amp_4",
            "Pm_step_t_1", "Pm_step_t_2", "Pm_step_t_3", "Pm_step_t_4",
            "Pm_1", "M_1", "D_1",
        ):
            assert live_var in v3, f"fixture missing {live_var}"
            assert v3[live_var]["verdict"] == "LIVE"

    def test_v2_regression_set_present(self, kundur_fixture) -> None:
        v2 = kundur_fixture["kundur_cvs"]["expectations"]
        for live_var in ("wn_const", "M_1", "D_1", "Pm_step_amp_1"):
            assert live_var in v2
            assert v2[live_var]["verdict"] == "LIVE"
