"""Tests for simulink_screenshot and simulink_capture_figure.

These tests mock MatlabSession so no MATLAB engine is needed.
"""
import base64
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _png_stub(tmp_path: Path, name: str = "test.png") -> Path:
    """Create a tiny valid PNG file for testing."""
    # Minimal 1x1 white PNG (67 bytes)
    data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
        b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
        b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    p = tmp_path / name
    p.write_bytes(data)
    return p


def _mock_session():
    """Return a MagicMock that behaves like MatlabSession."""
    session = MagicMock()
    session._bootstrapped = set()
    return session


# ---------------------------------------------------------------------------
# simulink_screenshot
# ---------------------------------------------------------------------------

class TestSimulinkScreenshot:

    def test_returns_artifact_path_on_success(self, tmp_path):
        from engine.mcp_simulink_tools import simulink_screenshot

        def fake_vsg_screenshot(target, out_path, resolution):
            # Simulate MATLAB writing a PNG
            _png_stub(Path(out_path).parent, Path(out_path).name)
            return {"ok": True, "width": 1, "height": 1, "error_msg": ""}

        session = _mock_session()
        session.call.side_effect = lambda func, *a, **kw: (
            fake_vsg_screenshot(*a) if func == "vsg_screenshot"
            else None
        )

        with patch("engine.mcp_simulink_tools.MatlabSession") as MockMS, \
             patch("engine.mcp_simulink_tools._ensure_model_bootstrapped", return_value="test_model"):
            MockMS.get.return_value = session
            result = simulink_screenshot("test_model")

        assert result["ok"] is True
        assert result["artifact_path"].endswith(".png")
        assert result["format"] == "png"
        assert result["width"] == 1
        assert result["height"] == 1
        assert len(result["sha256"]) == 64
        assert "image_base64" not in result

    def test_returns_base64_when_requested(self, tmp_path):
        from engine.mcp_simulink_tools import simulink_screenshot

        def fake_vsg_screenshot(target, out_path, resolution):
            _png_stub(Path(out_path).parent, Path(out_path).name)
            return {"ok": True, "width": 1, "height": 1, "error_msg": ""}

        session = _mock_session()
        session.call.side_effect = lambda func, *a, **kw: (
            fake_vsg_screenshot(*a) if func == "vsg_screenshot"
            else None
        )

        with patch("engine.mcp_simulink_tools.MatlabSession") as MockMS, \
             patch("engine.mcp_simulink_tools._ensure_model_bootstrapped", return_value="test_model"):
            MockMS.get.return_value = session
            result = simulink_screenshot("test_model", return_base64=True)

        assert result["ok"] is True
        assert "image_base64" in result
        # Verify it's valid base64
        decoded = base64.b64decode(result["image_base64"])
        assert decoded[:4] == b"\x89PNG"

    def test_passes_system_path_to_matlab(self):
        from engine.mcp_simulink_tools import simulink_screenshot

        session = _mock_session()
        session.call.return_value = {"ok": False, "width": 0, "height": 0, "error_msg": "test"}

        with patch("engine.mcp_simulink_tools.MatlabSession") as MockMS, \
             patch("engine.mcp_simulink_tools._ensure_model_bootstrapped", return_value="m"):
            MockMS.get.return_value = session
            simulink_screenshot("m", system_path="m/SubSys1")

        # The first positional arg to vsg_screenshot should be the subsystem
        call_args = session.call.call_args_list[-1]
        assert call_args[0][1] == "m/SubSys1"

    def test_error_returns_empty_path(self):
        from engine.mcp_simulink_tools import simulink_screenshot

        session = _mock_session()
        session.call.return_value = {
            "ok": False, "width": 0, "height": 0,
            "error_msg": "Model not loaded",
        }

        with patch("engine.mcp_simulink_tools.MatlabSession") as MockMS, \
             patch("engine.mcp_simulink_tools._ensure_model_bootstrapped", return_value="m"):
            MockMS.get.return_value = session
            result = simulink_screenshot("m")

        assert result["ok"] is False
        assert result["artifact_path"] == ""
        assert result["error_message"] == "Model not loaded"


# ---------------------------------------------------------------------------
# simulink_capture_figure
# ---------------------------------------------------------------------------

class TestSimulinkCaptureFigure:

    def test_captures_single_figure(self, tmp_path):
        from engine.mcp_simulink_tools import simulink_capture_figure

        def fake_capture(out_dir, fig_id, capture_all, resolution):
            png_path = str(Path(out_dir) / "figure_1.png")
            _png_stub(Path(out_dir), "figure_1.png")
            return {
                "ok": True,
                "count": 1,
                "figures": [
                    {"id": 1, "path": png_path, "title": "Figure 1",
                     "width": 1, "height": 1},
                ],
                "error_msg": "",
            }

        session = _mock_session()
        session.call.side_effect = lambda func, *a, **kw: fake_capture(*a)

        with patch("engine.mcp_simulink_tools.MatlabSession") as MockMS:
            MockMS.get.return_value = session
            result = simulink_capture_figure()

        assert result["ok"] is True
        assert result["count"] == 1
        assert len(result["figures"]) == 1
        fig = result["figures"][0]
        assert fig["id"] == 1
        assert fig["format"] == "png"
        assert len(fig["sha256"]) == 64
        assert "image_base64" not in fig

    def test_capture_all_returns_multiple(self, tmp_path):
        from engine.mcp_simulink_tools import simulink_capture_figure

        def fake_capture(out_dir, fig_id, capture_all, resolution):
            for i in (1, 2):
                _png_stub(Path(out_dir), f"figure_{i}.png")
            return {
                "ok": True,
                "count": 2,
                "figures": [
                    {"id": 1, "path": str(Path(out_dir) / "figure_1.png"),
                     "title": "Fig 1", "width": 1, "height": 1},
                    {"id": 2, "path": str(Path(out_dir) / "figure_2.png"),
                     "title": "Fig 2", "width": 1, "height": 1},
                ],
                "error_msg": "",
            }

        session = _mock_session()
        session.call.side_effect = lambda func, *a, **kw: fake_capture(*a)

        with patch("engine.mcp_simulink_tools.MatlabSession") as MockMS:
            MockMS.get.return_value = session
            result = simulink_capture_figure(capture_all=True)

        assert result["count"] == 2
        assert len(result["figures"]) == 2

    def test_error_returns_empty_figures(self):
        from engine.mcp_simulink_tools import simulink_capture_figure

        session = _mock_session()
        session.call.return_value = {
            "ok": False, "count": 0, "figures": [],
            "error_msg": "No open figures found",
        }

        with patch("engine.mcp_simulink_tools.MatlabSession") as MockMS:
            MockMS.get.return_value = session
            result = simulink_capture_figure()

        assert result["ok"] is False
        assert result["count"] == 0
        assert result["figures"] == []
        assert result["error_message"] == "No open figures found"

    def test_base64_included_when_requested(self, tmp_path):
        from engine.mcp_simulink_tools import simulink_capture_figure

        def fake_capture(out_dir, fig_id, capture_all, resolution):
            _png_stub(Path(out_dir), "figure_1.png")
            return {
                "ok": True, "count": 1,
                "figures": [
                    {"id": 1, "path": str(Path(out_dir) / "figure_1.png"),
                     "title": "T", "width": 1, "height": 1},
                ],
                "error_msg": "",
            }

        session = _mock_session()
        session.call.side_effect = lambda func, *a, **kw: fake_capture(*a)

        with patch("engine.mcp_simulink_tools.MatlabSession") as MockMS:
            MockMS.get.return_value = session
            result = simulink_capture_figure(return_base64=True)

        assert "image_base64" in result["figures"][0]

    def test_explicit_figure_id_passed_to_matlab(self):
        from engine.mcp_simulink_tools import simulink_capture_figure

        session = _mock_session()
        session.call.return_value = {
            "ok": False, "count": 0, "figures": [],
            "error_msg": "not found",
        }

        with patch("engine.mcp_simulink_tools.MatlabSession") as MockMS:
            MockMS.get.return_value = session
            simulink_capture_figure(figure_id=42)

        call_args = session.call.call_args
        # figure_id should be passed as 42.0
        assert call_args[0][2] == 42.0


# ---------------------------------------------------------------------------
# Contract: these tools ARE in PUBLIC_TOOLS (exposed in B1b)
# ---------------------------------------------------------------------------

class TestPublicContract:
    def test_screenshot_in_public_tools(self):
        from engine import mcp_server
        names = [t.__name__ for t in mcp_server.PUBLIC_TOOLS]
        assert "simulink_screenshot" in names

    def test_capture_figure_in_public_tools(self):
        from engine import mcp_server
        names = [t.__name__ for t in mcp_server.PUBLIC_TOOLS]
        assert "simulink_capture_figure" in names
