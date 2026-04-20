from __future__ import annotations

"""Zone A — Modeling quality gate tasks.

scenario_status -> model_inspect -> model_patch_verify -> model_diagnose -> model_report

These tasks must work independently of any training run.
Record primitives live in engine.task_primitives.
"""

import time as _time
from pathlib import Path
from typing import Any, Mapping

from engine import harness_reports
from engine.task_primitives import (
    create_record,
    finish,
    list_existing_task_records,
    load_task_record,
    record_failure,
)
from engine.task_state import check_transition, recommended_next_tasks_for
from engine.harness_reference import (
    build_reference_context,
    load_scenario_reference,
    reference_path_for_scenario,
    summarize_reference_manifest,
    validate_reference_items,
)
from engine.harness_registry import resolve_scenario
from engine.harness_repair import generate_repair_hints
from engine.mcp_simulink_tools import (
    _simulink_get_block_tree_raw,
    _simulink_loaded_models_raw,
    simulink_compile_diagnostics,
    simulink_load_model,
    simulink_patch_and_verify,
    simulink_query_params,
    simulink_solver_audit,
    simulink_step_diagnostics,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

from engine.harness_models import MODELING_TASKS as _MODELING_TASKS


def _ensure_loaded(spec) -> dict[str, Any]:
    """Load the scenario model only if it is not already in MATLAB.

    Checks ``spec.model_name in simulink_loaded_models()`` — not just
    "any model loaded" — so a stale model from another scenario never
    causes a false skip.
    """
    already = _simulink_loaded_models_raw()
    if spec.model_name in already:
        return {"ok": True, "model_name": spec.model_name, "loaded_models": already, "skipped_load": True}
    return simulink_load_model(spec.model_name)


def _read_prior_evidence(run_dir: Path, task_name: str, key: str) -> Any | None:
    """Read a field from a prior task record in this run.

    Returns the value if the prior task exists and has the key, else None.
    This is *evidence from a prior step*, not live MATLAB state.
    """
    record = load_task_record(run_dir, task_name)
    if record is None:
        return None
    return record.get(key)


def _collect_findings(records: list[dict[str, Any]]) -> list[str]:
    findings: list[str] = []
    for record in records:
        for failure in record.get("failures", []):
            message = failure.get("message")
            if message:
                findings.append(f"{record.get('task', 'unknown')}: {message}")
    return findings


def _build_memory_hints(records: list[dict[str, Any]]) -> dict[str, Any]:
    reasons: list[str] = []
    diagnose_record = next((record for record in records if record.get("task") == "model_diagnose"), None)
    if diagnose_record and diagnose_record.get("suspected_root_causes"):
        reasons.append("new_root_cause_identified")
    if any(record.get("task") == "model_patch_verify" and record.get("status") == "failed" for record in records):
        reasons.append("repair_path_changed")
    if any(record.get("status") == "warning" for record in records):
        reasons.append("important_warning_recorded")
    return {
        "should_write_devlog": bool(reasons),
        "should_write_decision": False,
        "reason": reasons,
    }


def _write_summary(
    run_dir: Path,
    run_status: str,
    completed_tasks: list[str],
    key_findings: list[str],
    recommended_followups: list[str],
    memory_hints: Mapping[str, Any],
) -> Path:
    lines = [
        f"Run status: `{run_status}`",
        "",
        f"Completed tasks: {', '.join(completed_tasks) if completed_tasks else 'none'}",
    ]
    if key_findings:
        lines.extend(["", "Key findings:"])
        lines.extend([f"- {item}" for item in key_findings])
    if recommended_followups:
        lines.extend(["", "Recommended followups:"])
        lines.extend([f"- {item}" for item in recommended_followups])
    if memory_hints.get("should_write_devlog") or memory_hints.get("should_write_decision"):
        lines.extend(["", "Memory follow-up:"])
        if memory_hints.get("should_write_devlog"):
            lines.append("- Add a devlog entry for this run.")
        if memory_hints.get("should_write_decision"):
            lines.append("- Check whether this run established a stable decision.")
        reasons = memory_hints.get("reason") or []
        if reasons:
            lines.append(f"- Reasons: {', '.join(reasons)}")
    path = run_dir / "summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Zone A public task functions
# ---------------------------------------------------------------------------


def harness_scenario_status(
    *,
    scenario_id: str,
    run_id: str,
    goal: str,
    requested_tasks: list[str] | None = None,
) -> dict[str, Any]:
    record = create_record(
        "scenario_status",
        scenario_id,
        run_id,
        {"goal": goal, "requested_tasks": requested_tasks or ["scenario_status"]},
    )
    run_dir = harness_reports.ensure_run_dir(scenario_id, run_id)
    try:
        spec = resolve_scenario(scenario_id)
    except ValueError as exc:
        record_failure(record, "contract_error", str(exc))
        return finish(record, extra={"supported": False, "notes": []})

    harness_reports.write_manifest(
        run_dir,
        run_id=run_id,
        scenario_id=scenario_id,
        goal=goal,
        requested_tasks=requested_tasks or ["scenario_status"],
        created_at=record.started_at,
    )
    reference_manifest = load_scenario_reference(scenario_id)
    extra = {
        "resolved_model_name": spec.model_name,
        "resolved_model_dir": str(spec.model_dir),
        "resolved_train_entry": str(spec.train_entry),
        "supported": True,
        "reference_manifest_path": reference_path_for_scenario(scenario_id).relative_to(_PROJECT_ROOT).as_posix(),
        "reference_summary": summarize_reference_manifest(reference_manifest),
        "notes": [],
    }
    record.summary.append(f"scenario '{scenario_id}' resolved: model={spec.model_name}")
    return finish(record, extra=extra)


def harness_model_inspect(
    *,
    scenario_id: str,
    run_id: str,
    focus_paths: list[str] | None = None,
    query_params: list[str] | None = None,
    include_block_tree: bool = False,
    include_check_params: bool = False,
) -> dict[str, Any]:
    """Inspect a loaded Simulink model against its reference manifest.

    **Model loading is automatic** — you do NOT need to call simulink_load_model
    before this tool.  Internally, ``_ensure_loaded`` checks whether the scenario
    model is already open in MATLAB and calls ``load_system`` only when needed.
    If loading fails (model file missing, MATLAB engine not running, etc.) the
    record status will be ``"failed"`` with a ``load_error`` failure_class and
    an actionable ``hint`` in ``failures[0].detail``.

    Default (slim) mode: _ensure_loaded + reference_validation (pure Python).
    No MATLAB IPC calls unless focus_paths or include_* opts are set.

    Opt-in heavy operations (set to True when you need them):
      - focus_paths: run query_params on the listed block paths (1 IPC call)
      - include_block_tree: run get_block_tree on each focus_path (1 IPC/path)
      - include_check_params: deprecated no-op (slx_check_params.m removed)
      - query_params: restrict queried params to this list (used with focus_paths)
    """
    focus_paths = focus_paths or []
    query_params = query_params or []
    record = create_record(
        "model_inspect",
        scenario_id,
        run_id,
        {
            "focus_paths": focus_paths,
            "query_params": query_params,
            "include_block_tree": include_block_tree,
            "include_check_params": include_check_params,
        },
    )
    run_dir = harness_reports.ensure_run_dir(scenario_id, run_id)
    transition_ok, transition_reason = check_transition(run_dir, "model_inspect")
    if not transition_ok:
        record.summary.append(f"transition_advisory: {transition_reason}")

    _timings: dict[str, float] = {}
    try:
        _t0 = _time.monotonic()
        spec = resolve_scenario(scenario_id)

        # --- Step 1: ensure model loaded (skips if already in MATLAB) ---
        load_result = _ensure_loaded(spec)
        _timings["ensure_loaded"] = round(_time.monotonic() - _t0, 2)

        # --- Step 2 (pure Python): reference validation ---
        _t1 = _time.monotonic()
        reference_manifest = load_scenario_reference(scenario_id)
        reference_validation = validate_reference_items(
            reference_items=reference_manifest["reference_items"],
            actual_values=build_reference_context(
                scenario_id,
                spec,
                load_result=load_result,
            ),
        )
        _timings["reference_validation"] = round(_time.monotonic() - _t1, 2)

        # --- Step 3 (1 IPC): solver audit — skipped if no focus ---
        _t2 = _time.monotonic()
        solver_audit: dict[str, Any] = {}
        if focus_paths:
            solver_audit = simulink_solver_audit(spec.model_name)
        _timings["solver_audit"] = round(_time.monotonic() - _t2, 2)
        _timings["total"] = round(_time.monotonic() - _t0, 2)

        # --- Opt-in: block tree on focus_paths ---
        focus_blocks: list[Any] = []
        if include_block_tree and focus_paths:
            focus_blocks = [
                _simulink_get_block_tree_raw(spec.model_name, root_path=path, max_depth=3)
                for path in focus_paths
            ]

        # --- Opt-in: query params on focus_paths ---
        queried_params: dict[str, Any] = {"items": []}
        if focus_paths:
            queried_params = simulink_query_params(
                spec.model_name,
                focus_paths,
                query_params or None,
            )

        # param audit removed (slx_check_params.m deleted)
        param_suspects: list[Any] = []

    except Exception as exc:
        exc_str = str(exc)
        # Classify the most common failure modes so the caller can act without
        # reading a raw Python traceback.
        if "load_system" in exc_str or "bdIsLoaded" in exc_str or "model_name" in exc_str.lower():
            failure_class = "load_error"
            hint = (
                "The model could not be loaded.  "
                "Check that the .slx file exists under scenarios/ and that the "
                "MATLAB engine is running (try simulink_loaded_models first)."
            )
        elif "scalar struct" in exc_str or "slx_batch_query" in exc_str:
            failure_class = "matlab_return_type"
            hint = (
                "slx_batch_query returned an unexpected type (likely scalar struct). "
                "This can happen when the model is not fully initialised. "
                "Retry with no focus_paths first to confirm the model loads cleanly."
            )
        else:
            failure_class = "tool_error"
            hint = "Check the MATLAB engine and model file path."
        record_failure(record, failure_class, "Model inspection failed", {"error": exc_str, "hint": hint})
        try:
            loaded = _simulink_loaded_models_raw()
        except Exception:
            loaded = []
        extra = {
            "model_loaded": False,
            "loaded_models": loaded,
            "focus_blocks": [],
            "solver_audit": {},
            "param_suspects": [],
            "reference_validation": {
                "checks": [],
                "mismatch_keys": [],
                "missing_keys": [],
                "has_warnings": False,
            },
            "recommended_next_task": (recommended_next_tasks_for("model_inspect", "failed") or ["model_diagnose"])[0],
        }
        record.summary.append(f"model_inspect FAILED ({failure_class}): {hint}")
        return finish(record, extra=extra)

    extra = {
        "model_loaded": bool(load_result.get("ok", False)),
        "loaded_models": load_result.get("loaded_models", []),
        "focus_blocks": focus_blocks,
        "queried_params": queried_params,
        "solver_audit": solver_audit,
        "param_suspects": param_suspects,
        "reference_validation": reference_validation,
        "recommended_next_task": (recommended_next_tasks_for("model_inspect", record.status) or ["model_patch_verify"])[0],
        "_timings": _timings,
    }
    if not load_result.get("ok", False):
        record_failure(record, "tool_error", "Failed to load model", load_result)
    elif reference_validation["has_warnings"]:
        record.status = "warning"
    ref_status = "ok" if not reference_validation["has_warnings"] else f"{len(reference_validation['mismatch_keys'])} mismatch(es)"
    record.summary.append(
        f"model_inspect: loaded={bool(load_result.get('ok'))}, ref={ref_status}, elapsed={_timings.get('total', '?')}s"
    )
    return finish(record, extra=extra)


def harness_model_patch_verify(
    *,
    scenario_id: str,
    run_id: str,
    edits: list[dict[str, Any]],
    run_update: bool = True,
    smoke_test_stop_time: float | None = None,
) -> dict[str, Any]:
    record = create_record(
        "model_patch_verify",
        scenario_id,
        run_id,
        {
            "edits": edits,
            "run_update": run_update,
            "smoke_test_stop_time": smoke_test_stop_time,
        },
    )
    run_dir = harness_reports.ensure_run_dir(scenario_id, run_id)
    transition_ok, transition_reason = check_transition(run_dir, "model_patch_verify")
    if not transition_ok:
        record.summary.append(f"transition_advisory: {transition_reason}")

    try:
        spec = resolve_scenario(scenario_id)
        _ensure_loaded(spec)
        patch = simulink_patch_and_verify(
            spec.model_name,
            edits=edits,
            run_update=run_update,
            smoke_test_stop_time=smoke_test_stop_time,
            timeout_sec=60,
        )
    except Exception as exc:
        exc_str = str(exc)
        if "set_param" in exc_str or "get_param" in exc_str:
            patch_hint = "Parameter set/get failed. Check block paths in edits[] match actual model block paths (use model_inspect with focus_paths)."
        elif "update_diagram" in exc_str or "sim(" in exc_str.lower():
            patch_hint = "Model update or smoke sim failed. Run model_diagnose to get compile/step errors, then fix before retrying."
        elif "load_system" in exc_str or "bdIsLoaded" in exc_str:
            patch_hint = "Model not loaded. Run model_inspect first."
        else:
            patch_hint = "Run model_inspect to confirm model is loaded, then model_diagnose to identify root cause before retrying edits."
        record_failure(record, "tool_error", "Patch and verify call failed", {"error": exc_str, "hint": patch_hint})
        extra = {
            "applied_edits": [],
            "readback": [],
            "update_ok": False,
            "smoke_test_ok": False,
            "smoke_test_summary": {},
            "recommended_next_task": (recommended_next_tasks_for("model_patch_verify", "failed") or ["model_diagnose"])[0],
        }
        record.summary.append(f"patch_verify FAILED: {patch_hint}")
        return finish(record, extra=extra)

    update_ok = bool(patch.get("update_ok", False))
    smoke_test_ok = patch.get("smoke_test_ok")
    has_errors = bool(patch.get("errors")) or any(item.get("error") for item in patch.get("readback", []))
    ok = bool(patch.get("ok", False)) and update_ok and not has_errors and (smoke_test_ok is not False)
    patch_status = "ok" if ok else "failed"
    next_from_table = recommended_next_tasks_for("model_patch_verify", patch_status)
    recommended = next_from_table[0] if next_from_table else ("model_report" if ok else "model_diagnose")
    extra = {
        "applied_edits": patch.get("applied_edits", []),
        "readback": patch.get("readback", []),
        "update_ok": update_ok,
        "smoke_test_ok": smoke_test_ok,
        "smoke_test_summary": patch.get("smoke_test_summary", {}),
        "recommended_next_task": recommended,
    }
    if not ok:
        record_failure(record, "model_error", "Patch verification did not complete cleanly", patch)
    record.summary.append(
        f"patch_verify: {len(edits)} edit(s), update_ok={update_ok}, smoke_ok={smoke_test_ok}, next={recommended}"
    )
    return finish(record, extra=extra)


def harness_model_diagnose(
    *,
    scenario_id: str,
    run_id: str,
    diagnostic_window: dict[str, float],
    signals: list[Any] | None = None,
    capture_warnings: bool = True,
) -> dict[str, Any]:
    """Run compile + step diagnostics on the model.

    Reads solver_audit and param_suspects from the prior model_inspect
    record as *evidence context* (not live state).  Only compile_diagnostics
    and step_diagnostics hit MATLAB — two IPC calls, fits in 30s.

    diagnostic_window keys:
      - start_time (float): simulation start time in seconds
      - stop_time  (float): simulation stop time in seconds
      - dt         (float, optional): step size override
    """
    # Accept shorthand keys for convenience.
    if "start" in diagnostic_window and "start_time" not in diagnostic_window:
        diagnostic_window["start_time"] = diagnostic_window.pop("start")
    if "stop" in diagnostic_window and "stop_time" not in diagnostic_window:
        diagnostic_window["stop_time"] = diagnostic_window.pop("stop")

    signals = signals or []
    record = create_record(
        "model_diagnose",
        scenario_id,
        run_id,
        {
            "diagnostic_window": diagnostic_window,
            "signals": signals,
            "capture_warnings": capture_warnings,
        },
    )
    run_dir_diag = harness_reports.ensure_run_dir(scenario_id, run_id)
    transition_ok, transition_reason = check_transition(run_dir_diag, "model_diagnose")
    if not transition_ok:
        record.summary.append(f"transition_advisory: {transition_reason}")

    try:
        spec = resolve_scenario(scenario_id)
        _ensure_loaded(spec)

        # --- IPC 1: compile diagnostics ---
        compile_info = simulink_compile_diagnostics(spec.model_name, mode="update")

        # --- IPC 2: step diagnostics ---
        step_info = simulink_step_diagnostics(
            spec.model_name,
            diagnostic_window["start_time"],
            diagnostic_window["stop_time"],
            capture_warnings=capture_warnings,
        )

        # --- Prior evidence (no IPC, read from run_dir) ---
        run_dir = harness_reports.ensure_run_dir(scenario_id, run_id)
        prior_solver_audit = _read_prior_evidence(run_dir, "model_inspect", "solver_audit") or {}
        prior_param_suspects = _read_prior_evidence(run_dir, "model_inspect", "param_suspects") or []

    except Exception as exc:
        exc_str = str(exc)
        if "load_system" in exc_str or "bdIsLoaded" in exc_str or "model" in exc_str.lower() and "not" in exc_str.lower():
            diag_failure_class = "load_error"
            diag_hint = "Model not loaded. Run model_inspect first to ensure the model is open in MATLAB."
        elif "compile_diagnostics" in exc_str or "update_diagram" in exc_str.lower():
            diag_failure_class = "compile_error"
            diag_hint = "Compile diagnostics failed. The model may be in an invalid state. Run model_inspect with focus_paths set to examine blocks."
        elif "step_diagnostics" in exc_str or "sim(" in exc_str.lower():
            diag_failure_class = "simulation_error"
            diag_hint = "Step diagnostics failed. Check diagnostic_window values are valid for this model."
        else:
            diag_failure_class = "tool_error"
            diag_hint = "Check that MATLAB engine is running and model is loaded (simulink_loaded_models)."
        record_failure(record, diag_failure_class, "Diagnostics failed", {"error": exc_str, "hint": diag_hint})
        extra = {
            "compile_ok": False,
            "compile_errors": [],
            "step_status": "tool_error",
            "warning_groups": [],
            "signal_snapshot": {},
            "suspected_root_causes": [],
            "repair_hints": [],
            "recommended_next_task": (recommended_next_tasks_for("model_diagnose", "failed") or ["model_patch_verify"])[0],
        }
        record.summary.append(f"diagnose FAILED ({diag_failure_class}): {diag_hint}")
        return finish(record, extra=extra)

    suspected_root_causes = [entry.get("message", "") for entry in compile_info.get("errors", []) if entry.get("message")]
    suspected_root_causes.extend(item.get("example", "") for item in step_info.get("top_errors", []) if item.get("example"))
    repair_hints = generate_repair_hints(suspected_root_causes)
    extra = {
        "compile_ok": bool(compile_info.get("ok", False)),
        "compile_errors": compile_info.get("errors", []),
        "step_status": step_info.get("status", ""),
        "warning_groups": step_info.get("top_warnings", []),
        "signal_snapshot": {},
        "prior_solver_audit": prior_solver_audit,
        "prior_param_suspects": prior_param_suspects,
        "suspected_root_causes": suspected_root_causes,
        "repair_hints": repair_hints,
        "recommended_next_task": (recommended_next_tasks_for("model_diagnose", record.status) or ["model_patch_verify"])[0],
    }
    if (not compile_info.get("ok", False)) or step_info.get("status") not in {"success", "ok"}:
        record_failure(record, "model_error", "Diagnostics found compile or simulation issues")
    record.summary.append(
        f"diagnose: compile_ok={compile_info.get('ok', False)}, step={step_info.get('status', '')}, "
        f"causes={len(suspected_root_causes)}, hints={len(repair_hints)}"
    )
    return finish(record, extra=extra)


def harness_model_report(
    *,
    scenario_id: str,
    run_id: str,
    include_summary_md: bool = True,
) -> dict[str, Any]:
    record = create_record(
        "model_report",
        scenario_id,
        run_id,
        {"include_summary_md": include_summary_md},
    )
    run_dir = harness_reports.ensure_run_dir(scenario_id, run_id)
    prior_records = list_existing_task_records(run_dir)
    completed_tasks = [item.get("task", Path(item.get("task", "")).stem) for item in prior_records if item.get("task")]
    failed_tasks = [item.get("task", "") for item in prior_records if item.get("status") == "failed"]
    warning_tasks = [item.get("task", "") for item in prior_records if item.get("status") == "warning"]
    run_status = "failed" if failed_tasks else "warning" if warning_tasks else "ok"
    key_findings = _collect_findings(prior_records)
    # recommended_followups: optional suggestions for the caller — not facts,
    # not used as preconditions by any harness task (preconditions read run_status
    # and failed_tasks only).
    recommended_followups = (
        ["Run train_smoke"]
        if run_status in {"ok", "warning"}
        else ["Fix failed modeling tasks before train_smoke"]
    )
    memory_hints = _build_memory_hints(prior_records)
    extra = {
        "run_status": run_status,
        "completed_tasks": completed_tasks,
        "failed_tasks": failed_tasks,
        "precondition_failed": run_status == "failed",
        "key_findings": key_findings,
        "recommended_followups": recommended_followups,
        "memory_hints": memory_hints,
    }
    if include_summary_md:
        summary_path = _write_summary(run_dir, run_status, completed_tasks, key_findings, recommended_followups, memory_hints)
        record.artifacts.append(str(summary_path))
    record.summary.append(
        f"run_report: status={run_status}, tasks={len(completed_tasks)}, "
        f"blocked={len(failed_tasks)}, findings={len(key_findings)}"
    )
    return finish(record, extra=extra)
