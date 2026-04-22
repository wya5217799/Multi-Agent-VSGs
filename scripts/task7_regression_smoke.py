"""Task 7 regression smoke: scenario_status + model_inspect + train_smoke for Kundur and NE39.

Calls harness functions directly (no MCP server needed).
Results are written to results/harness/<scenario_id>/<run_id>/.
"""

import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.modeling_tasks import harness_scenario_status, harness_model_inspect
from engine.smoke_tasks import harness_train_smoke_minimal, harness_train_smoke_poll

RUN_ID = f"task7-regression-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
SCENARIOS = ["kundur", "ne39"]
POLL_INTERVAL = 15   # seconds between polls
SMOKE_TIMEOUT = 480  # 8 minutes max per scenario

results = {}

for sid in SCENARIOS:
    print(f"\n{'='*60}")
    print(f"Scenario: {sid}  run_id: {RUN_ID}")

    # --- Step 1: scenario_status ---
    print("--- harness_scenario_status ---")
    status = harness_scenario_status(
        scenario_id=sid,
        run_id=RUN_ID,
        goal="task7-regression-gate",
    )
    print(f"  status={status.get('status')}  resolved={status.get('resolved_model_name', '?')}")
    if status.get("status") != "ok":
        print(f"  FAIL: {status.get('error', '')}")
        results[sid] = {"scenario_status": "FAIL", "model_inspect": "skipped", "train_smoke": "skipped"}
        continue

    # --- Step 2: model_inspect ---
    print("--- harness_model_inspect ---")
    inspect = harness_model_inspect(
        scenario_id=sid,
        run_id=RUN_ID,
        include_check_params=True,
    )
    inspect_status = inspect.get("run_status", inspect.get("status", "?"))
    print(f"  run_status={inspect_status}")
    if inspect_status not in {"ok", "warning"}:
        print(f"  FAIL details: {inspect.get('error', '')}")
        results[sid] = {
            "scenario_status": status.get("status"),
            "model_inspect": inspect_status,
            "train_smoke": "skipped",
        }
        continue

    # --- Step 3: train_smoke_minimal (1 episode) ---
    print("--- harness_train_smoke_minimal (1 episode) ---")
    smoke = harness_train_smoke_minimal(
        scenario_id=sid,
        run_id=RUN_ID,
        goal="task7-regression-gate",
        episodes=1,
        mode="simulink",
    )
    smoke_started = smoke.get("smoke_started", False)
    smoke_status = smoke.get("status", "?")
    print(f"  smoke_started={smoke_started}  status={smoke_status}  pid={smoke.get('pid')}")
    if not smoke_started:
        print(f"  FAIL to start: {smoke.get('error', smoke.get('failure_reason', ''))}")
        results[sid] = {
            "scenario_status": status.get("status"),
            "model_inspect": inspect_status,
            "train_smoke": "start_failed",
        }
        continue

    # --- Poll until done ---
    print(f"  Polling every {POLL_INTERVAL}s (timeout {SMOKE_TIMEOUT}s)...")
    deadline = time.monotonic() + SMOKE_TIMEOUT
    smoke_final = None
    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL)
        poll = harness_train_smoke_poll(scenario_id=sid, run_id=RUN_ID)
        proc_status = poll.get("process_status", poll.get("status", "?"))
        smoke_passed = poll.get("smoke_passed", False)
        print(f"  poll: process_status={proc_status}  smoke_passed={smoke_passed}")
        if proc_status != "running":
            smoke_final = poll
            break
    else:
        print(f"  TIMEOUT after {SMOKE_TIMEOUT}s")
        results[sid] = {
            "scenario_status": status.get("status"),
            "model_inspect": inspect_status,
            "train_smoke": "timeout",
        }
        continue

    train_result = "PASS" if smoke_final.get("smoke_passed") else "FAIL"
    results[sid] = {
        "scenario_status": status.get("status"),
        "model_inspect": inspect_status,
        "train_smoke": train_result,
        "exit_code": smoke_final.get("exit_code"),
    }

print(f"\n{'='*60}")
print("SUMMARY")
all_ok = True
for sid, r in results.items():
    ok = (
        r["scenario_status"] == "ok"
        and r["model_inspect"] in {"ok", "warning"}
        and r.get("train_smoke") == "PASS"
    )
    icon = "PASS" if ok else "FAIL"
    if not ok:
        all_ok = False
    print(f"  {sid}: {icon}  ({r})")

print(f"\nOverall: {'PASS' if all_ok else 'FAIL'}")
sys.exit(0 if all_ok else 1)
