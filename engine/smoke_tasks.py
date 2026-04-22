from __future__ import annotations

"""Zone B — Training smoke process management.

train_smoke_start / train_smoke_poll: thin subprocess launcher only.
Interface to training layer is filesystem + subprocess ONLY; no training imports.
Record primitives live in engine.task_primitives.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from engine import harness_reports
from engine.task_primitives import (
    create_record,
    finish,
    load_task_record,
    record_failure,
)
from engine.harness_registry import resolve_scenario
from engine.task_state import check_transition

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

from engine.harness_models import MODELING_TASKS as _MODELING_TASKS
_NATIVE_RESULTS_ROOTS = {
    "kundur": Path("results/sim_kundur"),
    "ne39": Path("results/sim_ne39"),
}

# Module-level registry of running smoke processes keyed by (scenario_id, run_id).
_SMOKE_PROCESSES: dict[tuple[str, str], subprocess.Popen] = {}
_SMOKE_LOG_HANDLES: dict[tuple[str, str], tuple[Any, Any]] = {}


def _train_smoke_paths(scenario_id: str, run_id: str) -> tuple[Path, Path]:
    native_root = _PROJECT_ROOT / _NATIVE_RESULTS_ROOTS[scenario_id] / "harness_smoke" / run_id
    checkpoint_dir = native_root / "checkpoints"
    log_file = native_root / "logs" / "training_log.json"
    return checkpoint_dir, log_file


def _train_smoke_preconditions(run_dir: Path) -> tuple[bool, list[str]]:
    failures: list[str] = []

    # Advisory: check transition table
    transition_ok, transition_reason = check_transition(run_dir, "train_smoke_start")
    if not transition_ok:
        failures.append(f"transition_advisory: {transition_reason}")

    # Hard gates (existing logic preserved exactly):
    scenario_status = load_task_record(run_dir, "scenario_status")
    if not scenario_status or scenario_status.get("status") != "ok":
        failures.append("scenario_status must exist with status ok")

    model_report = load_task_record(run_dir, "model_report")
    report_run_status = None if model_report is None else model_report.get("run_status")
    if report_run_status not in {"ok", "warning"}:
        failures.append("model_report must exist with run_status ok or warning")

    for task_name in _MODELING_TASKS:
        record = load_task_record(run_dir, task_name)
        if record and record.get("status") == "failed":
            failures.append(f"{task_name} is failed")

    # Only hard failures block; transition advisory is informational
    hard_failures = [item for item in failures if not item.startswith("transition_advisory:")]
    return (not hard_failures), failures


def _recover_pid_from_disk(scenario_id: str, run_id: str) -> int | None:
    """Try to recover a PID from a prior train_smoke_start record on disk."""
    run_dir = harness_reports.ensure_run_dir(scenario_id, run_id)
    record = load_task_record(run_dir, "train_smoke_start")
    if record and record.get("status") == "running" and record.get("pid"):
        return record["pid"]
    return None


def _is_pid_alive(pid: int) -> bool:
    """Check whether a process with the given PID is still running."""
    try:
        import os as _os
        # On Windows, os.kill with signal 0 checks existence.
        _os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _parse_training_summary(log_file: Path) -> dict[str, Any] | None:
    """Parse training_log.json and return a summary dict, or None on any failure.

    Returns None if the file does not exist, is not valid JSON, or raises any
    exception during parsing.  Never raises — callers rely on silent fallback.
    """
    if not log_file.exists():
        return None
    try:
        log_data = json.loads(log_file.read_text(encoding="utf-8"))
        ep_rewards: list = log_data.get("episode_rewards") or []
        eval_rewards: list = log_data.get("eval_rewards") or []
        physics: list = log_data.get("physics_summary") or []
        alphas: list = log_data.get("alphas") or []

        last_10 = ep_rewards[-10:]
        last_10_mean = round(sum(last_10) / len(last_10), 4) if last_10 else None

        eval_values = [e["reward"] for e in eval_rewards if isinstance(e, dict) and "reward" in e]
        best_eval = round(max(eval_values), 4) if eval_values else None
        last_eval = round(eval_values[-1], 4) if eval_values else None

        last_alpha = round(float(alphas[-1]), 6) if alphas else None

        last_10_physics = physics[-10:]
        settled_rate = (
            round(sum(1 for p in last_10_physics if p.get("settled")) / len(last_10_physics), 2)
            if last_10_physics else None
        )
        last_freq_dev_raw = physics[-1].get("max_freq_dev_hz") if physics else None
        last_freq_dev = round(float(last_freq_dev_raw), 4) if last_freq_dev_raw is not None else None

        return {
            "episodes_completed": len(ep_rewards),
            "last_10_reward_mean": last_10_mean,
            "best_eval_reward": best_eval,
            "last_eval_reward": last_eval,
            "last_alpha": last_alpha,
            "physics_settled_rate_last10": settled_rate,
            "last_max_freq_dev_hz": last_freq_dev,
        }
    except Exception:
        return None


def _collect_finished(
    record: Any,
    run_dir: Path,
    scenario_id: str,
    run_id: str,
    pid: int,
    returncode: int | None,
    key: tuple[str, str],
) -> dict[str, Any]:
    """Shared result collection for poll (in-memory and recovered paths)."""
    stdout_path = run_dir / "train_smoke_stdout.log"
    stderr_path = run_dir / "train_smoke_stderr.log"
    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""

    checkpoint_dir, log_file = _train_smoke_paths(scenario_id, run_id)
    native_log_paths = [str(log_file)] if log_file.exists() else []
    native_checkpoint_paths = sorted(
        str(path) for path in checkpoint_dir.rglob("*") if path.is_file()
    ) if checkpoint_dir.exists() else []

    # If we lost the process handle (MCP restart), infer success from artifacts.
    if returncode is None:
        smoke_passed = len(native_checkpoint_paths) > 0 and len(stderr_text.strip()) == 0
    else:
        smoke_passed = returncode == 0

    extra = {
        "process_status": "finished",
        "pid": pid,
        "exit_code": returncode,
        "native_log_paths": native_log_paths,
        "native_checkpoint_paths": native_checkpoint_paths,
        "smoke_passed": smoke_passed,
        "training_summary": _parse_training_summary(log_file),
    }

    if not smoke_passed:
        record_failure(
            record,
            "smoke_failed",
            "Training smoke command failed" + (" (exit code unknown — recovered after MCP restart)" if returncode is None else ""),
            {"stdout_tail": stdout_text[-2000:], "stderr_tail": stderr_text[-2000:]},
        )

    _SMOKE_PROCESSES.pop(key, None)
    exit_str = str(returncode) if returncode is not None else "unknown"
    record.summary.append(f"smoke_poll: finished, passed={smoke_passed}, exit_code={exit_str}")
    return finish(record, extra=extra)


# ---------------------------------------------------------------------------
# Zone B public task functions
# ---------------------------------------------------------------------------


def harness_train_smoke(
    *,
    scenario_id: str,
    run_id: str,
    episodes: int = 1,
    mode: str = "simulink",
) -> dict[str, Any]:
    """Synchronous train_smoke — deprecated in favour of the async start/poll pair.

    This function blocks the MCP server for the full training duration and will
    time out.  Use ``harness_train_smoke_start`` + ``harness_train_smoke_poll``
    instead.
    """
    record = create_record(
        "train_smoke",
        scenario_id,
        run_id,
        {"episodes": episodes, "mode": mode},
    )
    run_dir = harness_reports.ensure_run_dir(scenario_id, run_id)
    record_failure(
        record,
        "contract_error",
        "harness_train_smoke is deprecated: use harness_train_smoke_start + harness_train_smoke_poll. "
        "Calling this tool directly blocks the MCP server and will time out.",
        {"migration": "call harness_train_smoke_start, then poll with harness_train_smoke_poll"},
    )
    extra = {
        "command": "",
        "exit_code": None,
        "native_log_paths": [],
        "native_checkpoint_paths": [],
        "smoke_passed": False,
    }
    return finish(record, extra=extra)


def harness_train_smoke_start(
    *,
    scenario_id: str,
    run_id: str,
    episodes: int = 1,
    mode: str = "simulink",
) -> dict[str, Any]:
    """Launch train_smoke as a background process; returns immediately."""
    record = create_record(
        "train_smoke_start",
        scenario_id,
        run_id,
        {"episodes": episodes, "mode": mode},
    )
    run_dir = harness_reports.ensure_run_dir(scenario_id, run_id)
    preconditions_ok, failures = _train_smoke_preconditions(run_dir)
    if not preconditions_ok:
        record_failure(
            record,
            "precondition_failed",
            "train_smoke requires scenario_status ok, no failed modeling tasks, and model_report run_status ok/warning",
            {"reasons": failures},
        )
        return finish(record, extra={"command": "", "pid": None, "smoke_started": False})

    try:
        spec = resolve_scenario(scenario_id)
    except ValueError as exc:
        record_failure(record, "contract_error", str(exc))
        return finish(record, extra={"command": "", "pid": None, "smoke_started": False})

    key = (scenario_id, run_id)
    if key in _SMOKE_PROCESSES and _SMOKE_PROCESSES[key].poll() is None:
        record_failure(
            record,
            "contract_error",
            f"train_smoke already running for {scenario_id}/{run_id} (pid {_SMOKE_PROCESSES[key].pid})",
        )
        return finish(record, extra={"command": "", "pid": _SMOKE_PROCESSES[key].pid, "smoke_started": False})

    checkpoint_dir, log_file = _train_smoke_paths(scenario_id, run_id)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    # Use the andes_env interpreter (has matlab.engine) instead of sys.executable
    # which may point to the MCP server's Python (no matlab.engine → silent failure).
    from engine.training_launch import _PYTHON_EXE as _andes_python
    command = [
        str(_andes_python),
        str(_PROJECT_ROOT / spec.train_entry),
        "--mode",
        mode,
        "--episodes",
        str(episodes),
        "--checkpoint-dir",
        str(checkpoint_dir),
        "--log-file",
        str(log_file),
    ]

    stdout_path = run_dir / "train_smoke_stdout.log"
    stderr_path = run_dir / "train_smoke_stderr.log"
    stdout_fh = open(stdout_path, "w", encoding="utf-8")
    stderr_fh = open(stderr_path, "w", encoding="utf-8")

    proc = subprocess.Popen(
        command,
        cwd=str(_PROJECT_ROOT),
        stdout=stdout_fh,
        stderr=stderr_fh,
    )
    _SMOKE_PROCESSES[key] = proc
    _SMOKE_LOG_HANDLES[key] = (stdout_fh, stderr_fh)

    extra = {
        "command": subprocess.list2cmdline(command),
        "pid": proc.pid,
        "smoke_started": True,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }
    record.status = "running"
    record.summary.append(f"smoke_start: pid={proc.pid}, episodes={episodes}, mode={mode} — poll to check completion")
    return finish(record, extra=extra)


def harness_train_smoke_poll(
    *,
    scenario_id: str,
    run_id: str,
) -> dict[str, Any]:
    """Check whether a previously started train_smoke has finished.

    Survives MCP server restarts: if the in-memory process dict is empty,
    recovers PID from the persisted train_smoke_start.json record and
    checks whether the OS process is still alive.
    """
    record = create_record("train_smoke_poll", scenario_id, run_id, {})
    key = (scenario_id, run_id)
    run_dir = harness_reports.ensure_run_dir(scenario_id, run_id)

    proc = _SMOKE_PROCESSES.get(key)

    # --- Fast path: in-memory process handle available ---
    if proc is not None:
        returncode = proc.poll()
        if returncode is None:
            record.status = "running"
            record.summary.append(f"smoke_poll: still running, pid={proc.pid} — poll again later")
            return finish(record, extra={"process_status": "running", "pid": proc.pid, "smoke_passed": False})
        # Done — close log file handles.
        for fh in _SMOKE_LOG_HANDLES.pop(key, ()):
            if fh and not fh.closed:
                fh.close()
        return _collect_finished(record, run_dir, scenario_id, run_id, proc.pid, returncode, key)

    # --- Slow path: MCP restarted, recover PID from disk ---
    recovered_pid = _recover_pid_from_disk(scenario_id, run_id)
    if recovered_pid is None:
        record_failure(
            record,
            "contract_error",
            f"No running train_smoke for {scenario_id}/{run_id}. Call train_smoke_start first.",
        )
        return finish(record, extra={"process_status": "not_found", "smoke_passed": False})

    if _is_pid_alive(recovered_pid):
        record.status = "running"
        record.summary.append(f"smoke_poll: still running (recovered), pid={recovered_pid} — poll again later")
        return finish(record, extra={
            "process_status": "running", "pid": recovered_pid,
            "smoke_passed": False, "recovered_from_disk": True,
        })

    # Process finished but we lost the handle — exit code unknown.
    return _collect_finished(record, run_dir, scenario_id, run_id, recovered_pid, None, key)


def harness_train_smoke_minimal(
    *,
    scenario_id: str,
    run_id: str,
    goal: str = "smoke_test",
    episodes: int = 1,
    mode: str = "simulink",
) -> dict[str, Any]:
    """Run scenario_status → model_report → train_smoke_start in one call.

    Convenience wrapper that eliminates manual prerequisite chaining.
    Returns the train_smoke_start result on success, or the first failure
    with a ``smoke_full_step`` field identifying which step failed.
    """
    from engine.modeling_tasks import harness_scenario_status, harness_model_report

    # Step 1: scenario_status (writes record to disk — required by smoke preconditions)
    status_result = harness_scenario_status(
        scenario_id=scenario_id,
        run_id=run_id,
        goal=goal,
    )
    if status_result.get("status") != "ok":
        status_result["smoke_full_step"] = "scenario_status"
        status_result["smoke_started"] = False
        return status_result

    # Step 2: model_report (writes record to disk — required by smoke preconditions)
    report_result = harness_model_report(
        scenario_id=scenario_id,
        run_id=run_id,
    )
    run_status = report_result.get("run_status")
    if run_status not in {"ok", "warning"}:
        report_result["smoke_full_step"] = "model_report"
        report_result["smoke_started"] = False
        return report_result

    # Step 3: train_smoke_start (preconditions satisfied by disk records above)
    smoke_result = harness_train_smoke_start(
        scenario_id=scenario_id,
        run_id=run_id,
        episodes=episodes,
        mode=mode,
    )
    smoke_result["smoke_full_step"] = "train_smoke_start"
    smoke_result["model_report_run_status"] = run_status
    return smoke_result


harness_train_smoke_full = harness_train_smoke_minimal  # deprecated alias
