#!/usr/bin/env python3
"""Daemon tick logic: monitor running processes, launch pending runs, update state.

Called by research_loop_daemon.sh each tick:
  python3 _tick.py <state_file> <free_gb> <tick_num> <repo_root>
"""
from __future__ import annotations
import datetime
import json
import os
import subprocess
import sys

STATE = sys.argv[1]
free_gb = int(sys.argv[2])
TICK = int(sys.argv[3])
REPO = sys.argv[4]

sys.path.insert(0, REPO)
from scripts.research_loop.state_io import read_state, write_state, with_state_lock

NOW = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> None:
    with with_state_lock(STATE):
        s = read_state(STATE)
        hard: float = s["ram"]["free_gb_min_hard"]
        per: float = s["ram"]["per_run_estimate_gb"]
        cpu_threads: int = s["ram"].get("cpu_threads_per_run", 4)
        wsl_cpu: int = s["ram"].get("wsl_total_cpu", 32)
        omp_env: dict = s["ram"].get(
            "omp_env_defaults",
            {"OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4"},
        )

        # 1. Monitor running processes -> done or killed
        still_running = []
        for r in s["running"]:
            pid = r["pid"]
            try:
                os.kill(pid, 0)
                still_running.append(r)
            except ProcessLookupError:
                done_json_path = os.path.join(r["out_dir"], "_done.json")
                if os.path.exists(done_json_path):
                    with open(done_json_path, encoding="utf-8") as _f:
                        d = json.load(_f)
                    s["done"].append({
                        "id": r["id"],
                        "exit_code": d["exit_code"],
                        "finished_at_utc": d["finished_at_utc"],
                        "verdict_path": None,
                        "overall_score_v2": None,
                        "axes": {},
                    })
                    print(f"tick={TICK} done id={r['id']} exit={d['exit_code']}")
                else:
                    s["killed"].append({
                        "id": r["id"],
                        "reason": "process gone, no _done.json",
                        "killed_at_utc": NOW,
                    })
                    print(f"tick={TICK} killed id={r['id']} (no _done.json)")
        s["running"] = still_running

        # 2. RAM tight warning (kill logic deferred to v2, MVP logs only)
        if free_gb < hard and s["running"]:
            print(f"tick={TICK} RAM_TIGHT free={free_gb} hard={hard} running={len(s['running'])}")

        # 3. Fit count: RAM AND CPU dual constraints (per spec section 11.5)
        usable_ram = max(0.0, float(free_gb) - float(hard))
        ram_fit = int(usable_ram / per) if per > 0 else 0
        cpu_fit = wsl_cpu // cpu_threads
        fit_count = min(ram_fit, cpu_fit) - len(s["running"])
        fit_count = max(0, fit_count)
        print(f"tick={TICK} ram_fit={ram_fit} cpu_fit={cpu_fit} fit={fit_count} ram={free_gb}GB")

        # 4. Launch pending runs by priority (descending)
        s["pending"].sort(key=lambda x: -x.get("priority", 0))
        started = 0
        new_pending = []
        for p in s["pending"]:
            if started >= fit_count:
                new_pending.append(p)
                continue
            backend = p.get("backend", "andes_cpu")
            launcher = os.path.join(REPO, "scripts", "backends", f"{backend}.sh")
            if not os.path.exists(launcher):
                new_pending.append(p)
                print(f"tick={TICK} skip id={p['id']} backend={backend} (no launcher)")
                continue

            # Inject OMP env defaults into subprocess environment
            launch_env = {**os.environ, **{k: str(v) for k, v in omp_env.items()}}
            result = subprocess.run(
                [launcher, "launch",
                 "--id", p["id"],
                 "--cmd", p["cmd"],
                 "--out-dir", p["out_dir"],
                 "--log", p["log"]],
                env=launch_env,
                capture_output=True,
                text=True,
            )
            pid = None
            for line in result.stdout.splitlines():
                if line.startswith("pid="):
                    try:
                        pid = int(line.split("=", 1)[1])
                    except (ValueError, IndexError):
                        pass
                    break
            if pid is None:
                print(f"tick={TICK} launch_fail id={p['id']} stderr={result.stderr[:200]}")
                new_pending.append(p)
                continue
            s["running"].append({
                "id": p["id"],
                "pid": pid,
                "started_at_utc": NOW,
                "log_tail_check_ok": True,
                "out_dir": p["out_dir"],
                "log": p["log"],
            })
            started += 1
            print(f"tick={TICK} started id={p['id']} pid={pid}")
        s["pending"] = new_pending

        write_state(STATE, s)
        print(
            f"tick={TICK} state_run={len(s['running'])} "
            f"pend={len(s['pending'])} done={len(s['done'])} killed={len(s['killed'])}"
        )


main()
