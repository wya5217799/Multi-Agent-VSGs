from pathlib import Path

import pytest


pytestmark = pytest.mark.matlab


def _session():
    from engine.matlab_session import MatlabSession

    return MatlabSession.get()


def test_model_status_reports_unloaded_model():
    session = _session()
    result = session.call("slx_model_status", "model_that_does_not_exist_123", nargout=1)
    assert isinstance(result, dict)
    assert "ok" in result
    assert "loaded" in result


def test_workspace_set_returns_written_names():
    session = _session()
    result = session.call("slx_workspace_set", {"slx_test_var": 42.0}, nargout=1)
    assert bool(result["ok"])
    assert "slx_test_var" in list(result["vars_written"])


def test_runtime_helpers_on_new_minimal_model(tmp_path):
    session = _session()
    model_name = "slx_general_runtime_smoke"
    target_path = tmp_path / f"{model_name}.slx"
    session.call("slx_create_model", model_name, False, nargout=1)
    try:
        status = session.call("slx_model_status", model_name, nargout=1)
        assert bool(status["ok"])
        assert bool(status["loaded"])

        reset = session.call("slx_runtime_reset", model_name, "off", True, "", nargout=1)
        assert bool(reset["ok"])

        run = session.call("slx_run_window", model_name, 0.0, 0.01, True, nargout=1)
        assert bool(run["ok"])

        saved = session.call("slx_save_model", model_name, str(target_path), nargout=1)
        assert bool(saved["ok"])
        assert Path(target_path).exists()
    finally:
        session.call("slx_close_model", model_name, nargout=0)
