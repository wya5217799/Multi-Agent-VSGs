# AI-Compatible Training Monitor — Design Spec

**Date:** 2026-04-15
**Status:** Approved for implementation
**Scope:** Simulink training scenarios (kundur, ne39)

---

## Design Philosophy

Training system is the primary actor. Scripts produce output independently.
AI is an external, on-demand entry point and interpretation layer only.

> Bottom line: training runs itself, writes state itself, AI reads existing outputs and makes high-level judgments. AI never manages the training process.

---

## What Is Out of Scope

- Checkpoint recovery / resume debugging (not the bottleneck)
- Smoke harness (`harness_train_smoke_*`) — preserved as-is, not modified
- Post-training plotting / systematic result organization (not yet built)
- `monitor_state.json` as a live source (only written at training end today)

---

## Architecture: Two-Tier Query Model

```
Tier 1 — Normal polling
  training_status(scenario_id)
    ├── training_status.json   → lifecycle state (always fresh)
    └── logs/latest_state.json → metrics snapshot (low-frequency, ~every 50 ep)
    → Returns merged structured AI summary

Tier 2 — Deep diagnosis (only when Tier 1 shows anomaly / stalled / failed)
  training_diagnose(scenario_id, run_id=None)
    └── logs/events.jsonl      → full event stream used as diagnostic evidence
    → Returns structured anomaly report
```

AI always starts with Tier 1. Tier 2 is invoked only when Tier 1 reveals a
problem worth investigating.

---

## File Roles (Corrected)

| File | Writer | Write Frequency | AI Role |
|---|---|---|---|
| `training_status.json` | training script | on start / end / exception | Tier 1: lifecycle state |
| `logs/latest_state.json` | `ArtifactWriter.update_state()` | ~every 50 episodes + training end | Tier 1: metrics snapshot (low-freq) |
| `logs/events.jsonl` | `ArtifactWriter.log_event()` | per event (append) | Tier 2: diagnostic evidence |
| `logs/monitor_state.json` | `TrainingMonitor.save_checkpoint()` | training end only | Not used in Tier 2 for now |

`latest_state.json` must be described as a **low-frequency snapshot**, not a
per-episode live feed. MCP tool must surface this caveat to AI consumers.

`events.jsonl` contains the full event stream:
`training_start`, `eval`, `checkpoint`, `monitor_alert`, `monitor_stop`,
`training_end`. Not just anomalies — it is the canonical training timeline.

---

## training_status.json — Schema Enrichment

### Current schema (all statuses)

```json
// on start (written by write_training_status at training start)
{"status": "running", "run_id": "...", "scenario": "kundur",
 "episodes_total": 500, "episodes_done": 0}

// normal completion
{"status": "completed", "run_id": "...", "scenario": "kundur",
 "episodes_total": 500, "episodes_done": 500,
 "finished_at": "2026-04-14T15:34:13Z"}

// monitor hard-stop
{"status": "monitor_stopped", "run_id": "...", "scenario": "kundur",
 "episodes_total": 500, "episodes_done": 247,
 "finished_at": "2026-04-14T12:11:05Z"}

// exception
{"status": "failed", "run_id": "...", "scenario": "kundur",
 "episodes_total": 500, "episodes_done": 83,
 "failed_at": "2026-04-14T10:22:31Z", "error": "..."}
```

### Fields to add (minimal additions)

| Field | Add to | Value |
|---|---|---|
| `started_at` | initial `running` write | ISO timestamp at training start |
| `logs_dir` | all status writes | relative path, e.g. `"logs"` |

`started_at` is currently absent from `training_status.json`; it exists only
in `run_meta.json`. Adding it here avoids requiring MCP tool to read two files
for a basic "how long has it been running?" query.

`logs_dir` is always `"logs"` by current convention, but making it explicit
means AI tools do not need to hard-code path assumptions.

### No renames

`monitor_stopped` stays as-is (not renamed to `interrupted`). Changing it
would break existing tooling and tests with no benefit right now.

---

## New Helper: `find_latest_run(scenario_id)` in `run_protocol.py`

MCP tools need to locate the most recent run directory without requiring an
explicit `run_id` from the caller. Add:

```python
def find_latest_run(scenario_id: str) -> Path | None:
    """Return the most-recently-modified run_dir for scenario_id, or None."""
```

Scans `results/sim_{scenario_id}/runs/`, returns the dir with the most recent
`training_status.json` mtime. Returns `None` if no runs exist.

---

## MCP Tool Interface

### `training_status(scenario_id: str) -> dict`

**Lives in:** `engine/training_tasks.py`
**Registered in:** `engine/mcp_server.py`

**Logic:**
1. Call `find_latest_run(scenario_id)` → `run_dir`
2. Read `training_status.json` → lifecycle fields
3. Read `logs/latest_state.json` if it exists → metrics fields (may be absent
   for very early runs)
4. Merge and return

**Return schema:**

```python
{
    # From training_status.json
    "scenario_id": str,
    "run_id": str,
    "status": "running" | "completed" | "monitor_stopped" | "failed" | "no_run",
    "episodes_done": int,
    "episodes_total": int,
    "progress_pct": float,          # episodes_done / episodes_total * 100
    "started_at": str | None,
    "finished_at": str | None,      # None if still running
    "error": str | None,            # populated only on status=failed
    "run_dir": str,                 # absolute path as string

    # From logs/latest_state.json (may be None if not yet written)
    "latest_snapshot": {
        "episode": int,
        "reward_mean_50": float,
        "alpha": float,
        "settled_rate_50": float,
        "buffer_size": int,
        "snapshot_freshness": "~50-episode intervals"  # static caveat
    } | None,
}
```

### `training_diagnose(scenario_id: str, run_id: str | None = None) -> dict`

**Lives in:** `engine/training_tasks.py`
**Registered in:** `engine/mcp_server.py`

**Logic:**
1. If `run_id` is None, call `find_latest_run(scenario_id)`
2. Read `logs/events.jsonl` — parse all records
3. Extract and classify: alerts, stops, eval trajectory, checkpoints
4. Return structured report

**Return schema:**

```python
{
    "scenario_id": str,
    "run_id": str,
    "event_count": int,
    "alerts": [{"episode": int, "rule": str, ...}],        # monitor_alert events
    "monitor_stop": {"episode": int} | None,               # first monitor_stop if any
    "eval_rewards": [{"episode": int, "eval_reward": float}],  # eval events
    "checkpoints": [{"episode": int, "file": str}],        # checkpoint events
    "training_start": {"episode": int, "mode": str} | None,
    "training_end": {"episode": int} | None,
}
```

---

## Training Script Changes (Minimal)

**Files:** `scenarios/kundur/train_simulink.py`,
           `scenarios/new_england/train_simulink.py`

### Change 1: Add `started_at` + `logs_dir` to the initial status write

Locate the `write_training_status(run_dir, {"status": "running", ...})` call
(currently around line 299 in both scripts). Add two fields:

```python
write_training_status(run_dir, {
    "status": "running",
    "run_id": run_id,
    "scenario": SCENARIO_ID,
    "episodes_total": args.episodes,
    "episodes_done": start_episode,
    "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),  # ADD
    "logs_dir": "logs",                                                        # ADD
})
```

### Change 2: Carry `started_at` + `logs_dir` through all subsequent status writes

All other `write_training_status` calls (completed, monitor_stopped, failed)
must also include `started_at` (read from the initial write or from
`run_meta.json`) and `logs_dir: "logs"`.

Simplest approach: read `started_at` once at training start, keep it in a
local variable, pass it to every subsequent status write.

### No other training script changes required.

`latest_state.json` write frequency (every 50 ep) stays as-is.
The MCP tool surfaces the caveat via `snapshot_freshness` field.

---

## `run_protocol.py` Changes

Add `find_latest_run(scenario_id)` function. No other changes.

---

## `engine/training_tasks.py` Changes

Add two new functions:
- `training_status(scenario_id: str) -> dict`
- `training_diagnose(scenario_id: str, run_id: str | None = None) -> dict`

The existing `training_evaluate_run` and `training_compare_runs` functions
remain unchanged (post-training analysis, not monitoring).

---

## `engine/mcp_server.py` Changes

Register the two new tools:
- `training_status`
- `training_diagnose`

No other MCP surface changes.

---

## Testing

| Test | Where |
|---|---|
| `test_find_latest_run_returns_most_recent` | `tests/test_run_protocol.py` |
| `test_find_latest_run_returns_none_when_no_runs` | `tests/test_run_protocol.py` |
| `test_training_status_running` | `tests/test_training_tasks.py` |
| `test_training_status_no_run` | `tests/test_training_tasks.py` |
| `test_training_status_with_latest_state` | `tests/test_training_tasks.py` |
| `test_training_status_without_latest_state` | `tests/test_training_tasks.py` |
| `test_training_diagnose_parses_events` | `tests/test_training_tasks.py` |
| `test_training_diagnose_empty_events` | `tests/test_training_tasks.py` |
| `test_mcp_registers_training_status` | `tests/test_mcp_server.py` |
| `test_mcp_registers_training_diagnose` | `tests/test_mcp_server.py` |

All tests use filesystem fixtures (tmp_path), no live training required.

---

## What Deliberately Stays Unchanged

- `harness_train_smoke_*` MCP tools — smoke harness untouched
- `training_evaluate_run`, `training_compare_runs` — post-run analysis untouched
- `utils/sidecar.py` — human notification tool, not part of AI monitoring path
- `latest_state.json` write frequency — 50-episode cadence is acceptable
- `monitor_state.json` — not used as a live source until made periodic
- `training_status.json` field names — no renames, only additions

---

## Deferred Decisions

| Item | Why Deferred |
|---|---|
| Make `monitor_state.json` periodic | Requires TrainingMonitor API change; not blocking |
| Per-episode `latest_state.json` | 50-ep is sufficient for AI polling; revisit if needed |
| Post-training plotting / result org | Tooling not yet built |
| `monitor_stopped` → `interrupted` rename | Breaking change, no benefit now |
