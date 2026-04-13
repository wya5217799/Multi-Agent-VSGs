"""Phase F: Agent Layer Evaluation Tests — harness flow contract.

Tests exercise the public Python functions (same as MCP routes) in scripted
sequences with injected state. No live MATLAB session required — engine calls
run in bootstrap/pure-Python mode; faults are injected via monkeypatching.

Coverage per evolution plan Phase F:
  - Scenario-based integration (full task chains, pure-Python legs)
  - Illegal transition enforcement (structured rejection)
  - Fault injection (HarnessFailure propagation via monkeypatch)
  - Idempotency (repeated calls don't corrupt persisted state)
"""
from __future__ import annotations

import pytest

from engine import harness_reports
from engine.modeling_tasks import (
    harness_model_diagnose,
    harness_model_inspect,
    harness_model_report,
    harness_scenario_status,
)
from engine.smoke_tasks import _train_smoke_preconditions, harness_train_smoke_start
from engine.task_primitives import load_task_record
from engine.task_state import allowed_next_tasks, infer_phase
from engine.harness_models import TaskPhase


# ── helpers ──────────────────────────────────────────────────────────────────

_GOAL = "flow contract test"


def _redirect(scenario_id: str, run_id: str, tmp_path, monkeypatch):
    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    return harness_reports.ensure_run_dir(scenario_id, run_id)


def _scenario_ok(scenario_id: str, run_id: str) -> dict:
    return harness_scenario_status(
        scenario_id=scenario_id, goal=_GOAL, run_id=run_id
    )


def _inject_load_error(monkeypatch):
    """Patch _ensure_loaded to raise RuntimeError so model_inspect returns failed."""
    import engine.modeling_tasks as mt
    monkeypatch.setattr(mt, "_ensure_loaded",
                        lambda _spec: (_ for _ in ()).throw(
                            RuntimeError("injected load error")
                        ))


# ── 1. Scenario-based integration ─────────────────────────────────────────────

class TestChainScenarioToReport:
    """Happy-path chain without live MATLAB: scenario_status → model_report."""

    def test_scenario_status_ok_then_model_report_ok(self, tmp_path, monkeypatch):
        """scenario_status ok followed by model_report produces ok run_status."""
        _redirect("kundur", "fc-chain-001", tmp_path, monkeypatch)

        r1 = _scenario_ok("kundur", "fc-chain-001")
        assert r1["status"] == "ok"
        assert r1["scenario_id"] == "kundur"

        r2 = harness_model_report(scenario_id="kundur", run_id="fc-chain-001",
                                  include_summary_md=False)
        assert r2["status"] == "ok"
        assert r2["run_status"] == "ok"

    def test_scenario_status_ok_allowed_next_is_model_inspect(
        self, tmp_path, monkeypatch
    ):
        """After scenario_status ok, the advisory next task is model_inspect."""
        run_dir = _redirect("kundur", "fc-chain-002", tmp_path, monkeypatch)
        _scenario_ok("kundur", "fc-chain-002")

        # scenario_status doesn't embed recommended_next_task in its return dict;
        # the advisory is exposed via allowed_next_tasks() on the run directory.
        nexts = allowed_next_tasks(run_dir)
        assert "model_inspect" in nexts

    def test_model_report_after_inspect_failure_shows_failed_run_status(
        self, tmp_path, monkeypatch
    ):
        """model_report after a failed model_inspect shows failed run_status."""
        _redirect("kundur", "fc-chain-003", tmp_path, monkeypatch)
        _scenario_ok("kundur", "fc-chain-003")

        # Inject load error so model_inspect records status=failed
        import engine.modeling_tasks as mt

        def _raise(_spec):
            raise RuntimeError("injected load error")

        monkeypatch.setattr(mt, "_ensure_loaded", _raise)
        r_inspect = harness_model_inspect(scenario_id="kundur", run_id="fc-chain-003")
        assert r_inspect["status"] == "failed"

        r_report = harness_model_report(scenario_id="kundur", run_id="fc-chain-003",
                                        include_summary_md=False)
        assert r_report["run_status"] in {"failed", "warning"}

    def test_model_report_recommends_smoke_when_ok(self, tmp_path, monkeypatch):
        """model_report ok → recommended_followups includes train_smoke_start."""
        _redirect("kundur", "fc-chain-004", tmp_path, monkeypatch)
        _scenario_ok("kundur", "fc-chain-004")

        r = harness_model_report(scenario_id="kundur", run_id="fc-chain-004",
                                 include_summary_md=False)
        assert r["status"] == "ok"
        # model_report returns recommended_followups (a list of human-readable strings)
        followups = r.get("recommended_followups", [])
        assert any("train_smoke" in f for f in followups), (
            f"Expected a train_smoke suggestion in recommended_followups, got: {followups}"
        )


# ── 2. Illegal transition enforcement ─────────────────────────────────────────

class TestIllegalTransitions:
    """Out-of-order task calls are rejected or advisory-annotated."""

    def test_smoke_start_blocked_without_model_report(self, tmp_path, monkeypatch):
        """_train_smoke_preconditions fails when model_report has not run."""
        run_dir = _redirect("kundur", "fc-illegal-001", tmp_path, monkeypatch)
        _scenario_ok("kundur", "fc-illegal-001")

        ok, failures = _train_smoke_preconditions(run_dir)
        assert ok is False
        hard = [f for f in failures if not f.startswith("transition_advisory:")]
        assert any("model_report" in f for f in hard)

    def test_smoke_start_blocked_without_scenario_status(self, tmp_path, monkeypatch):
        """_train_smoke_preconditions fails on a completely empty run."""
        run_dir = _redirect("kundur", "fc-illegal-002", tmp_path, monkeypatch)

        ok, failures = _train_smoke_preconditions(run_dir)
        assert ok is False

    def test_model_diagnose_out_of_order_gets_transition_advisory(
        self, tmp_path, monkeypatch
    ):
        """model_diagnose called before model_inspect → advisory in summary."""
        _redirect("kundur", "fc-illegal-003", tmp_path, monkeypatch)
        _scenario_ok("kundur", "fc-illegal-003")

        r = harness_model_diagnose(
            scenario_id="kundur",
            run_id="fc-illegal-003",
            diagnostic_window={"start_time": 0.0, "stop_time": 1.0},
        )
        advisories = [s for s in r.get("summary", []) if "transition_advisory" in s]
        assert len(advisories) >= 1, (
            f"Expected transition advisory in summary but got: {r.get('summary', [])}"
        )

    def test_smoke_start_mcp_returns_failed_with_precondition_failure(
        self, tmp_path, monkeypatch
    ):
        """harness_train_smoke_start returns status=failed for precondition violation."""
        _redirect("kundur", "fc-illegal-004", tmp_path, monkeypatch)
        _scenario_ok("kundur", "fc-illegal-004")

        result = harness_train_smoke_start(
            scenario_id="kundur",
            run_id="fc-illegal-004",
            episodes=10,
            mode="simulink",
        )
        assert result["status"] == "failed"
        classes = [f["failure_class"] for f in result.get("failures", [])]
        assert "precondition_failed" in classes


# ── 3. Fault injection: HarnessFailure propagation ───────────────────────────

class TestFaultInjection:
    """Force failures via monkeypatch and verify HarnessFailure propagates."""

    def test_model_inspect_load_error_produces_harness_failure(
        self, tmp_path, monkeypatch
    ):
        """Injected load error → model_inspect status=failed, failure_class=load_error."""
        _redirect("kundur", "fc-fault-001", tmp_path, monkeypatch)
        _scenario_ok("kundur", "fc-fault-001")

        import engine.modeling_tasks as mt

        def _raise(_spec):
            raise RuntimeError("injected load error")

        monkeypatch.setattr(mt, "_ensure_loaded", _raise)
        result = harness_model_inspect(scenario_id="kundur", run_id="fc-fault-001")

        assert result["status"] == "failed"
        classes = [f["failure_class"] for f in result.get("failures", [])]
        # Injected generic RuntimeError → classified as tool_error; load_error requires
        # a message containing "load_system", "bdIsLoaded", or "model_name".
        assert any(c in {"load_error", "tool_error"} for c in classes)

    def test_model_inspect_load_error_is_persisted(self, tmp_path, monkeypatch):
        """Injected load error is written to disk as a task record."""
        run_dir = _redirect("kundur", "fc-fault-002", tmp_path, monkeypatch)
        _scenario_ok("kundur", "fc-fault-002")

        import engine.modeling_tasks as mt

        monkeypatch.setattr(mt, "_ensure_loaded",
                            lambda _: (_ for _ in ()).throw(RuntimeError("injected")))
        harness_model_inspect(scenario_id="kundur", run_id="fc-fault-002")

        record = load_task_record(run_dir, "model_inspect")
        assert record is not None
        assert record["status"] == "failed"
        assert len(record["failures"]) >= 1

    def test_harness_failure_class_is_nonempty_string(self, tmp_path, monkeypatch):
        """Every HarnessFailure in a failed task has a non-empty failure_class str."""
        _redirect("kundur", "fc-fault-003", tmp_path, monkeypatch)
        _scenario_ok("kundur", "fc-fault-003")

        import engine.modeling_tasks as mt
        monkeypatch.setattr(mt, "_ensure_loaded",
                            lambda _: (_ for _ in ()).throw(RuntimeError("injected")))
        result = harness_model_inspect(scenario_id="kundur", run_id="fc-fault-003")

        assert result["status"] == "failed"
        assert len(result.get("failures", [])) >= 1
        for f in result["failures"]:
            assert isinstance(f["failure_class"], str) and f["failure_class"]

    def test_harness_failure_message_is_nonempty_string(self, tmp_path, monkeypatch):
        """Every HarnessFailure has a non-empty message string."""
        _redirect("kundur", "fc-fault-004", tmp_path, monkeypatch)
        _scenario_ok("kundur", "fc-fault-004")

        import engine.modeling_tasks as mt
        monkeypatch.setattr(mt, "_ensure_loaded",
                            lambda _: (_ for _ in ()).throw(RuntimeError("injected")))
        result = harness_model_inspect(scenario_id="kundur", run_id="fc-fault-004")

        assert result["status"] == "failed"
        for f in result["failures"]:
            assert isinstance(f["message"], str) and f["message"]


# ── 4. Idempotency ─────────────────────────────────────────────────────────────

class TestIdempotency:
    """Repeated calls must not corrupt persisted state."""

    def test_scenario_status_twice_returns_ok_both_times(
        self, tmp_path, monkeypatch
    ):
        _redirect("kundur", "fc-idem-001", tmp_path, monkeypatch)
        r1 = _scenario_ok("kundur", "fc-idem-001")
        r2 = _scenario_ok("kundur", "fc-idem-001")
        assert r1["status"] == "ok"
        assert r2["status"] == "ok"

    def test_scenario_status_twice_last_record_wins(self, tmp_path, monkeypatch):
        """Second scenario_status overwrites; disk record is still readable."""
        run_dir = _redirect("kundur", "fc-idem-002", tmp_path, monkeypatch)
        _scenario_ok("kundur", "fc-idem-002")
        _scenario_ok("kundur", "fc-idem-002")

        record = load_task_record(run_dir, "scenario_status")
        assert record is not None
        assert record["status"] == "ok"

    def test_model_report_twice_is_idempotent(self, tmp_path, monkeypatch):
        """Calling model_report twice: run_status is the same both times."""
        _redirect("kundur", "fc-idem-003", tmp_path, monkeypatch)
        _scenario_ok("kundur", "fc-idem-003")

        r1 = harness_model_report(scenario_id="kundur", run_id="fc-idem-003",
                                  include_summary_md=False)
        r2 = harness_model_report(scenario_id="kundur", run_id="fc-idem-003",
                                  include_summary_md=False)
        assert r1["status"] == r2["status"]
        assert r1["run_status"] == r2["run_status"]

    def test_phase_after_two_scenario_status_calls_is_resolved(
        self, tmp_path, monkeypatch
    ):
        """infer_phase after two scenario_status calls = SCENARIO_RESOLVED."""
        run_dir = _redirect("kundur", "fc-idem-004", tmp_path, monkeypatch)
        _scenario_ok("kundur", "fc-idem-004")
        _scenario_ok("kundur", "fc-idem-004")

        phase, _ = infer_phase(run_dir)
        assert phase == TaskPhase.SCENARIO_RESOLVED

    def test_allowed_next_stable_after_repeated_scenario_status(
        self, tmp_path, monkeypatch
    ):
        """allowed_next_tasks is the same after one or two scenario_status calls."""
        run_dir = _redirect("kundur", "fc-idem-005", tmp_path, monkeypatch)
        _scenario_ok("kundur", "fc-idem-005")
        after_one = allowed_next_tasks(run_dir)

        _scenario_ok("kundur", "fc-idem-005")
        after_two = allowed_next_tasks(run_dir)

        assert after_one == after_two
