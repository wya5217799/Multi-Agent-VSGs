"""P4.2-overnight — detached continuation of phi_b1 from ep 50 → 2000.

Authorized by user GO message: "能继续这个 50 的，一直持续训练，直到我让停止为止"
(continue the phi_b1 50-ep config, keep training until I tell you to stop).

Resumes SAC state from `kundur_simulink_20260427_011559/checkpoints/ep50.pt`
to preserve the warm-up buffer + SAC weights from the P4.2 gate run; spawns
the trainer as a DETACHED Windows process so it survives this Claude session.
Same env contract as P4.2:
  KUNDUR_MODEL_PROFILE = kundur_cvs_v3.json
  KUNDUR_DISTURBANCE_TYPE = pm_step_proxy_random_bus
  KUNDUR_PHI_H = 0.0001  (phi_b1)
  KUNDUR_PHI_D = 0.0001
  seed = 42

Wall projection: 1950 remaining ep × ~13 s/ep ≈ 7.0 hr (well within overnight).
Checkpoint every 50 ep so a mid-run crash recovers from the latest ep.

To stop: locate the spawned train_simulink.py PID via `Get-Process python` or
the printed PID; `Stop-Process <pid>`. Or write a sentinel file as the monitor
.stop_signal — see `utils/monitor.py`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_EXE = r"C:\Users\27443\miniconda3\envs\andes_env\python.exe"

EP50_CKPT = (
    REPO_ROOT
    / "results"
    / "sim_kundur"
    / "runs"
    / "kundur_simulink_20260427_011559"
    / "checkpoints"
    / "ep50.pt"
)

# Total episodes to RUN past the resume point. ep50.pt has start_episode=50,
# so --episodes 1950 lands at ep 2000 total (matching paper Table I).
TARGET_REMAINING = 1950

LOG_DIR = REPO_ROOT / "results" / "harness" / "kundur" / "cvs_v3_phase4"
LOG_DIR.mkdir(parents=True, exist_ok=True)
DETACH_LOG_STDOUT = LOG_DIR / "p42_overnight_stdout.txt"
DETACH_LOG_STDERR = LOG_DIR / "p42_overnight_stderr.txt"
PID_FILE = LOG_DIR / "p42_overnight_pid.txt"


def main() -> int:
    if not EP50_CKPT.exists():
        print(f"ERROR: resume checkpoint not found: {EP50_CKPT}")
        return 1

    env = os.environ.copy()
    env["KUNDUR_MODEL_PROFILE"] = str(
        REPO_ROOT / "scenarios" / "kundur" / "model_profiles" / "kundur_cvs_v3.json"
    )
    env["KUNDUR_DISTURBANCE_TYPE"] = "pm_step_proxy_random_bus"
    env["KUNDUR_PHI_H"] = "0.0001"
    env["KUNDUR_PHI_D"] = "0.0001"
    env["PYTHONUNBUFFERED"] = "1"

    cmd = [
        PYTHON_EXE,
        str(REPO_ROOT / "scenarios" / "kundur" / "train_simulink.py"),
        "--mode", "simulink",
        "--episodes", str(TARGET_REMAINING),
        "--resume", str(EP50_CKPT),
        "--seed", "42",
        "--save-interval", "50",   # checkpoint every 50 ep so an interruption recovers cleanly
        "--eval-interval", "50",
    ]
    print("P42-OVERNIGHT: spawning detached training process")
    print(f"  cmd: {' '.join(cmd)}")
    print(f"  resume: {EP50_CKPT}")
    print(f"  target remaining episodes: {TARGET_REMAINING}")
    print(f"  detached_stdout: {DETACH_LOG_STDOUT}")
    print(f"  detached_stderr: {DETACH_LOG_STDERR}")

    # Windows: DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP severs the child
    # from the parent's console / job, so it survives this script + Claude
    # session exit.
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    fout = open(DETACH_LOG_STDOUT, "w", encoding="utf-8")
    ferr = open(DETACH_LOG_STDERR, "w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=fout,
        stderr=ferr,
        creationflags=flags,
        close_fds=True,
    )
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    print(f"P42-OVERNIGHT: spawned PID={proc.pid}")
    print(f"P42-OVERNIGHT: PID written to {PID_FILE}")
    print("P42-OVERNIGHT: parent script exiting; trainer is now detached and running.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
