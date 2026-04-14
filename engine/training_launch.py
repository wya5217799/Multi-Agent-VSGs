"""engine/training_launch.py — Lightweight training launch control plane.

Provides get_training_launch_status(scenario_id) as the single query
entry point before launching training.  Reads from existing harness
JSON (no new fact sources).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from engine.harness_reference import load_scenario_reference

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Resolved once at import time: the interpreter that is currently executing
# this module.  Callers (harness, agent, scripts) must run under the correct
# virtualenv; sys.executable propagates that choice rather than hard-coding a
# path that breaks on other machines.
_PYTHON_EXE = Path(sys.executable)

_TRAIN_ENTRIES = {
    "kundur": "scenarios/kundur/train_simulink.py",
    "ne39":   "scenarios/new_england/train_simulink.py",
}

_MODEL_PATHS = {
    "kundur": "scenarios/kundur/simulink_models/kundur_vsg.slx",
    "ne39":   "scenarios/new_england/simulink_models/NE39bus_v2.slx",
}


def get_training_launch_status(scenario_id: str) -> dict[str, Any]:
    """One-call answer to: can I launch training for this scenario?

    Returns a dict with all facts needed to decide and execute a launch.
    Does NOT start any process; does NOT write any files.
    """
    # --- is this a known scenario? ---
    try:
        ref = load_scenario_reference(scenario_id)
    except (ValueError, FileNotFoundError):
        return {"supported": False, "scenario_id": scenario_id,
                "error": "unknown scenario_id"}

    facts = {item["key"]: item["value"] for item in ref.get("reference_items", [])}

    train_entry = facts.get("training_entry",
                            _TRAIN_ENTRIES.get(scenario_id, ""))
    model_name  = facts.get("model_name", "")

    # --- does the model file exist? ---
    slx_rel      = _MODEL_PATHS.get(scenario_id, "")
    slx_abs      = _PROJECT_ROOT / slx_rel
    model_exists = slx_abs.exists() if slx_rel else None

    # --- inspect the latest run ---
    runs_root = _PROJECT_ROOT / "results" / f"sim_{scenario_id}" / "runs"
    latest_run_id, latest_run_status, ckpt_count, resume_candidate = \
        _inspect_latest_run(runs_root)

    # --- is there an active training process for this scenario? ---
    active_pid = _find_active_pid(train_entry)

    # --- structured launch spec (program-level guarantee on interpreter path) ---
    # Use structured fields so callers never need to parse a shell string.
    # `recommended_command` is kept as a human-readable hint only; agents and
    # scripts should consume `launch` instead.
    _default_args = ["--mode", "simulink", "--episodes", "500"]
    launch = {
        "python_executable": str(_PYTHON_EXE),
        "script":            train_entry,
        "args":              _default_args,
    } if train_entry else None

    # Human-readable hint built from the same structured fields (not the
    # primary interface — do not execute this string directly).
    recommended_command = (
        f'"{_PYTHON_EXE}" {train_entry} ' + " ".join(_default_args)
        if train_entry else ""
    )

    return {
        "supported":                   True,
        "scenario_id":                 scenario_id,
        "train_entry":                 train_entry,
        "model_name":                  model_name,
        "model_file_exists":           model_exists,
        "latest_run_id":               latest_run_id,
        "latest_run_status":           latest_run_status,
        "latest_run_checkpoint_count": ckpt_count,
        "active_pid":                  active_pid,
        "resume_candidate":            resume_candidate,
        "launch":                      launch,
        "recommended_command":         recommended_command,
    }


# ── helpers ───────────────────────────────────────────────────────────────────

def _inspect_latest_run(runs_root: Path):
    """Find the most-recently-modified run dir and summarise its state."""
    if not runs_root.is_dir():
        return None, None, 0, None

    run_dirs = sorted(
        [d for d in runs_root.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    if not run_dirs:
        return None, None, 0, None

    latest = run_dirs[0]
    status_file = latest / "training_status.json"
    status = None
    if status_file.exists():
        try:
            status = json.loads(
                status_file.read_text(encoding="utf-8")
            ).get("status")
        except Exception:
            pass

    ckpt_dir = latest / "checkpoints"
    ep_ckpts = sorted(
        [f for f in (ckpt_dir.iterdir() if ckpt_dir.is_dir() else [])
         if f.name.startswith("ep") and f.name.endswith(".pt")],
        key=lambda f: int(f.stem[2:]),
    )
    ckpt_count = len(ep_ckpts)
    resume_candidate = str(ep_ckpts[-1]) if ep_ckpts else (
        str(ckpt_dir / "final.pt") if (ckpt_dir / "final.pt").exists() else None
    )

    return latest.name, status, ckpt_count, resume_candidate


def _find_active_pid(train_entry: str) -> int | None:
    """Return PID of a running python process matching train_entry, or None."""
    if not train_entry:
        return None
    # Use last two path components to distinguish scripts that share a basename.
    # Both Kundur and NE39 are named "train_simulink.py"; include the parent
    # directory so patterns are unique. Process argv uses forward slashes, so
    # keep them (don't convert to backslashes):
    #   kundur → "kundur/train_simulink.py"
    #   ne39   → "new_england/train_simulink.py"
    parts = train_entry.replace("\\", "/").split("/")
    pattern = "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             f"Get-WmiObject Win32_Process -Filter \"name='python.exe'\" "
             f"| Where-Object {{ $_.CommandLine -like '*{pattern}*' }} "
             f"| Select-Object -First 1 -ExpandProperty ProcessId"],
            capture_output=True, text=True, timeout=10,
        )
        pid_str = result.stdout.strip()
        return int(pid_str) if pid_str.isdigit() else None
    except Exception:
        return None
