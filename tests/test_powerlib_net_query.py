# tests/test_powerlib_net_query.py
"""Phase D.1: simulink_powerlib_net_query unit tests.

Mocks MATLAB engine; verifies input validation + return-shape normalization.
Live-MATLAB integration goes through probes/kundur/v3_dryrun/.

Plan §3.D.1.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestInputValidation:
    def setup_method(self) -> None:
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    def test_rejects_empty_start_block(self) -> None:
        from engine.mcp_simulink_tools import simulink_powerlib_net_query
        with pytest.raises(ValueError, match="start_block and start_port required"):
            simulink_powerlib_net_query("any_model", "", "LConn1")

    def test_rejects_empty_start_port(self) -> None:
        from engine.mcp_simulink_tools import simulink_powerlib_net_query
        with pytest.raises(ValueError, match="start_block and start_port required"):
            simulink_powerlib_net_query("any_model", "blockA", "")


class TestReturnShape:
    def setup_method(self) -> None:
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_supported_returns_member_list(self, mock_me) -> None:
        """Mock helper returns 4-member net (typical powerlib bus)."""
        from engine.mcp_simulink_tools import simulink_powerlib_net_query

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        mock_eng.slx_powerlib_net_query = MagicMock(return_value={
            "net_id": "kundur_cvs_v3/L_6_7a/RConn1",
            "members": [
                {"block": "kundur_cvs_v3/L_6_7a", "port": "RConn1"},
                {"block": "kundur_cvs_v3/L_6_7b", "port": "RConn1"},
                {"block": "kundur_cvs_v3/Load7", "port": "LConn1"},
                {"block": "kundur_cvs_v3/Shunt7", "port": "LConn1"},
            ],
            "anchor": {"block": "kundur_cvs_v3/L_6_7a", "port": "RConn1"},
            "supported": True,
            "reason": "",
        })

        result = simulink_powerlib_net_query(
            "kundur_cvs_v3", "kundur_cvs_v3/L_6_7a", "RConn1"
        )

        assert result["supported"] is True
        assert result["reason"] == ""
        assert len(result["members"]) == 4
        assert {m["block"] for m in result["members"]} == {
            "kundur_cvs_v3/L_6_7a",
            "kundur_cvs_v3/L_6_7b",
            "kundur_cvs_v3/Load7",
            "kundur_cvs_v3/Shunt7",
        }
        assert result["anchor"]["block"] == "kundur_cvs_v3/L_6_7a"

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_unsupported_block_returns_reason(self, mock_me) -> None:
        """Non-powerlib block: helper returns supported=False with reason."""
        from engine.mcp_simulink_tools import simulink_powerlib_net_query

        mock_eng = MagicMock()
        mock_me.start_matlab.return_value = mock_eng

        mock_eng.slx_powerlib_net_query = MagicMock(return_value={
            "net_id": "",
            "members": [],
            "anchor": {"block": "test/Const", "port": "Outport1"},
            "supported": False,
            "reason": "block has no LConn/RConn ports — not a powerlib physical block",
        })

        result = simulink_powerlib_net_query("test", "test/Const", "Outport1")

        assert result["supported"] is False
        assert "powerlib physical" in result["reason"]
        assert result["members"] == []
