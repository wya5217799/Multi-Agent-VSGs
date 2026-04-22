"""engine/training_launch.py — Lightweight training launch control plane.

Provides get_training_launch_status(scenario_id) as the single query
entry point before launching training.  Reads from existing harness
JSON (no new fact sources).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from engine.harness_reference import load_scenario_reference
from scenarios.contract import get_contract

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Training scripts guard their entry point with a [WRONG PYTHON] check that
# requires the andes_env interpreter (which has matlab.engine installed).
# Using sys.executable only works when this module is imported from andes_env;
# when called from Claude Code or any other Python, it would resolve to the
# wrong interpreter and silently fail at launch time.
#
# Resolution order:
#  1. CONDA_PREFIX env var points to active conda env → use its python.exe
#  2. Search well-known miniconda/conda paths for andes_env
#  3. Fall back to sys.executable (works when already in andes_env)
def _resolve_python_exe() -> Path:
    # Check if currently inside andes_env
    conda_prefix = os.environ.get("CONDA_PREFIX", "")
    if conda_prefix and "andes_env" in conda_prefix:
        candidate = Path(conda_prefix) / "python.exe"
        if candidate.exists():
            return candidate

    # Search common miniconda/anaconda locations on Windows
    search_roots = [
        Path.home() / "miniconda3" / "envs" / "andes_env",
        Path.home() / "anaconda3" / "envs" / "andes_env",
        Path("C:/ProgramData/miniconda3/envs/andes_env"),
        Path("C:/ProgramData/anaconda3/envs/andes_env"),
    ]
    for root in search_roots:
        candidate = root / "python.exe"
        if candidate.exists():
            return candidate

    # Fall back to current interpreter (works when already in andes_env)
    return Path(sys.executable)


_PYTHON_EXE = _resolve_python_exe()

def _scenario_launch_facts(scenario_id: str) -> tuple[str, str, Path]:
    """Return contract-derived train entry, model name, and model file path."""
    contract = get_contract(scenario_id)
    train_entry = contract.train_entry.as_posix()
    model_name = contract.model_name
    model_file = contract.model_dir / f"{contract.model_name}.slx"
    return train_entry, model_name, model_file


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

    try:
        contract_train_entry, contract_model_name, contract_model_file = (
            _scenario_launch_facts(scenario_id)
        )
    except ValueError:
        return {
            "supported": False,
            "scenario_id": scenario_id,
            "error": "unknown scenario_id",
        }

    facts = {item["key"]: item["value"] for item in ref.get("reference_items", [])}

    train_entry = facts.get("training_entry", contract_train_entry)
    model_name = facts.get("model_name", contract_model_name)

    slx_abs = _PROJECT_ROOT / contract_model_file
    model_exists = slx_abs.exists()

    # --- inspect the latest run (status-aware, ghost-proof via find_latest_run) ---
    from utils.run_protocol import find_latest_run as _find_latest, \
        read_training_status as _read_status
    _latest_dir = _find_latest(scenario_id)
    if _latest_dir is None:
        latest_run_id = latest_run_status = resume_candidate = None
        ckpt_count = 0
    else:
        latest_run_id = _latest_dir.name
        latest_run_status = (_read_status(_latest_dir) or {}).get("status")
        _ckpt_dir = _latest_dir / "checkpoints"
        _ep_ckpts = sorted(
            [f for f in (_ckpt_dir.iterdir() if _ckpt_dir.is_dir() else [])
             if f.name.startswith("ep") and f.name.endswith(".pt")],
            key=lambda f: int(f.stem[2:]),
        )
        ckpt_count = len(_ep_ckpts)
        resume_candidate = str(_ep_ckpts[-1]) if _ep_ckpts else (
            str(_ckpt_dir / "final.pt") if (_ckpt_dir / "final.pt").exists() else None
        )

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
    """Find the most-recently-modified run dir and summarise its state.

    NOTE: this helper is used only by tests; get_training_launch_status() calls
    find_latest_run() directly for ghost-proof, status-aware selection.
    """
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
