"""Tests for engine.harness_repair — repair hint generation.

All tests are written BEFORE the implementation (TDD).
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Unit tests for generate_repair_hints
# ---------------------------------------------------------------------------

def test_unknown_errors_return_empty_hints():
    from engine.harness_repair import generate_repair_hints

    hints = generate_repair_hints(["some completely unknown error with no pattern"])
    assert hints == []


def test_empty_error_list_returns_empty_hints():
    from engine.harness_repair import generate_repair_hints

    hints = generate_repair_hints([])
    assert hints == []


def test_d1_breaker_param_name_matched():
    """D1: R2025b Breaker parameter rename — TransitionTimes keyword."""
    from engine.harness_repair import generate_repair_hints

    errors = ["set_param failed: 'TransitionTimes' is not a valid parameter for Breaker"]
    hints = generate_repair_hints(errors)

    assert len(hints) == 1
    h = hints[0]
    assert h["hint_id"] == "D1"
    assert h["match_confidence"] in ("high", "low")
    assert isinstance(h["suggested_action"], str) and len(h["suggested_action"]) > 0
    assert isinstance(h["rationale"], str)
    assert isinstance(h["evidence"], list) and len(h["evidence"]) > 0


def test_d2_ic_convergence_matched():
    """D2: SM initial-condition solver failure — convergence keyword."""
    from engine.harness_repair import generate_repair_hints

    errors = ["警告: First solve for initial conditions failed to converge."]
    hints = generate_repair_hints(errors)

    assert len(hints) == 1
    assert hints[0]["hint_id"] == "D2"


def test_d2_vfd_domain_reference_matched():
    """D2:励磁子域悬浮 — Vfd.p.v keyword."""
    from engine.harness_repair import generate_repair_hints

    errors = ["将变量 'Vfd_G1.p.v' (电压) 与确定值绑定，例如通过连接适当的域参考模块"]
    hints = generate_repair_hints(errors)

    assert len(hints) == 1
    assert hints[0]["hint_id"] == "D2"


def test_d3_addconnection_domain_mismatch_matched():
    """D3: SM stator composite port connection failure."""
    from engine.harness_repair import generate_repair_hints

    errors = ["Cannot add connection: domain mismatch between SM stator port and RLC"]
    hints = generate_repair_hints(errors)

    assert len(hints) == 1
    assert hints[0]["hint_id"] == "D3"


def test_d4_mechanical_port_unconnected_matched():
    """D4: SynchronousMachineInit.p crash — mechanical port R not connected."""
    from engine.harness_repair import generate_repair_hints

    errors = ["SynchronousMachineInit.p internal error: mechanical port R is unconnected"]
    hints = generate_repair_hints(errors)

    assert len(hints) == 1
    assert hints[0]["hint_id"] == "D4"


def test_d5_matlab_call_error_matched():
    """D5: MatlabCallError / engine disconnect."""
    from engine.harness_repair import generate_repair_hints

    errors = ["MatlabCallError: eval() failed, engine disconnected"]
    hints = generate_repair_hints(errors)

    assert len(hints) == 1
    assert hints[0]["hint_id"] == "D5"


def test_multiple_distinct_patterns_produce_multiple_hints():
    """Two different known errors → two hints, one per pattern."""
    from engine.harness_repair import generate_repair_hints

    errors = [
        "set_param failed: 'TransitionTimes' is not valid",           # D1
        "SynchronousMachineInit.p internal error: port R unconnected", # D4
    ]
    hints = generate_repair_hints(errors)

    hint_ids = {h["hint_id"] for h in hints}
    assert "D1" in hint_ids
    assert "D4" in hint_ids


def test_same_pattern_matched_twice_deduplicates():
    """Two errors matching the same pattern → only one hint."""
    from engine.harness_repair import generate_repair_hints

    errors = [
        "TransitionTimes not valid on Breaker",
        "set_param TransitionTimes error",
    ]
    hints = generate_repair_hints(errors)

    assert sum(1 for h in hints if h["hint_id"] == "D1") == 1


def test_hint_schema_is_complete():
    """Every hint must have all required keys."""
    from engine.harness_repair import generate_repair_hints

    errors = ["TransitionTimes not valid"]
    hints = generate_repair_hints(errors)

    required_keys = {"hint_id", "match_confidence", "evidence", "suggested_action", "rationale"}
    for h in hints:
        assert required_keys.issubset(h.keys()), f"Missing keys in hint: {h}"


def test_evidence_contains_matched_text():
    """evidence list should contain the error string that triggered the match."""
    from engine.harness_repair import generate_repair_hints

    error = "TransitionTimes is not a valid Breaker parameter"
    hints = generate_repair_hints([error])

    assert any(error in ev for ev in hints[0]["evidence"])


# ---------------------------------------------------------------------------
# Integration: model_diagnose output includes repair_hints
# ---------------------------------------------------------------------------

def test_model_diagnose_output_has_repair_hints_field(tmp_path, monkeypatch):
    """model_diagnose must always return a repair_hints key (even when empty)."""
    from engine import harness_reports, harness_tasks, modeling_tasks

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")

    # Stub out MATLAB IPC calls.
    # After Phase 2 decomposition, these live in modeling_tasks, not harness_tasks.
    monkeypatch.setattr(
        modeling_tasks, "simulink_compile_diagnostics",
        lambda model, mode="update": {"ok": True, "errors": []},
    )
    monkeypatch.setattr(
        modeling_tasks, "simulink_step_diagnostics",
        lambda model, start, stop, capture_warnings=True: {
            "status": "success",
            "top_warnings": [],
            "top_errors": [],
        },
    )
    monkeypatch.setattr(
        modeling_tasks, "_ensure_loaded",
        lambda spec: {"ok": True, "model_name": spec.model_name, "skipped_load": True},
    )

    result = harness_tasks.harness_model_diagnose(
        scenario_id="kundur",
        run_id="repair-test",
        diagnostic_window={"start_time": 0.0, "stop_time": 1.0},
    )

    assert "repair_hints" in result
    assert isinstance(result["repair_hints"], list)


def test_model_diagnose_populates_repair_hints_on_known_error(tmp_path, monkeypatch):
    """model_diagnose with a D1-matching compile error must produce a D1 hint."""
    from engine import harness_reports, harness_tasks, modeling_tasks

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")

    monkeypatch.setattr(
        modeling_tasks, "simulink_compile_diagnostics",
        lambda model, mode="update": {
            "ok": False,
            "errors": [{"message": "set_param failed: TransitionTimes is not valid"}],
        },
    )
    monkeypatch.setattr(
        modeling_tasks, "simulink_step_diagnostics",
        lambda model, start, stop, capture_warnings=True: {
            "status": "sim_error",
            "top_warnings": [],
            "top_errors": [],
        },
    )
    monkeypatch.setattr(
        modeling_tasks, "_ensure_loaded",
        lambda spec: {"ok": True, "model_name": spec.model_name, "skipped_load": True},
    )

    result = harness_tasks.harness_model_diagnose(
        scenario_id="kundur",
        run_id="repair-test-d1",
        diagnostic_window={"start_time": 0.0, "stop_time": 1.0},
    )

    assert any(h["hint_id"] == "D1" for h in result["repair_hints"])
