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
| `training_status.json` | training script | **every episode** (heartbeat) + final/exception | Tier 1: primary state source |
| `logs/latest_state.json` | `ArtifactWriter.update_state()` | ~every 50 episodes + training end | Tier 1: supplemental metrics snapshot |
| `logs/events.jsonl` | `ArtifactWriter.log_event()` | per event (append) | Tier 2: diagnostic evidence |
| `logs/monitor_state.json` | `TrainingMonitor.save_checkpoint()` | training end only | Not used in Tier 2 for now |

**`training_status.json` is a per-episode heartbeat.** The training loop writes
it every episode with `last_reward` and `last_updated`. This makes it the
primary freshness source for Tier 1. Do not regress this to start/end-only
writes — that would break stall detection.

Current per-episode fields (already present, must be preserved):
`status`, `run_id`, `scenario`, `episodes_total`, `episodes_done`,
`last_reward`, `last_updated`.

`latest_state.json` is supplemental: written every ~50 episodes, provides
additional metrics (`reward_mean_50`, `alpha`, `settled_rate_50`, `buffer_size`)
not present in the heartbeat. MCP tool must surface that it is low-frequency.

`events.jsonl` contains the full event stream — not just anomalies:
`training_start`, `eval`, `checkpoint`, `monitor_alert`, `monitor_stop`,
`training_end`. It is the canonical training timeline.

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
| `started_at` | initial `running` write + all subsequent writes | ISO timestamp captured once at training start |
| `logs_dir` | all status writes | **derived from `args.log_file` at runtime**, e.g. `str(Path(args.log_file).parent)` |
| `last_eval_reward` | per-episode write when eval ran + final write | most recent evaluation reward; `null` until first eval |
| `stop_reason` | final `monitor_stopped` write | e.g. `"reward_divergence"`, `"physics_frozen"` — taken from the triggering monitor rule |

**`started_at`**: currently absent from `training_status.json`; exists only in
`run_meta.json`. Adding it avoids a two-file read for "how long has it been
running?". Store as a local variable at training start; carry through every
subsequent write.

**`logs_dir`**: must NOT be hardcoded as `"logs"`. Training scripts support
custom `--log-file` paths. Derive at runtime:
```python
_logs_dir = str(Path(args.log_file).parent)
```
Store as a local variable at training start; carry through every subsequent
write.

**`last_eval_reward`**: already implicit from `events.jsonl` eval events, but
having it in the heartbeat lets Tier 1 answer "what is the latest eval signal?"
without escalating to Tier 2. Initialize to `None`; update whenever an eval
episode runs.

**`stop_reason`**: only written on `monitor_stopped` status. Comes from the
monitor trigger rule name (e.g. `"reward_divergence"`). Lets Tier 1 answer
"why did it stop?" without reading `events.jsonl`.

**`last_reward`** (existing field): must be carried through to the final
`completed` / `monitor_stopped` / `failed` writes. Currently it is dropped on
the final write — fix this.

### No renames

`monitor_stopped` stays as-is (not renamed to `interrupted`). Changing it
would break existing tooling and tests with no benefit right now.

---

## New Helper: `find_latest_run(scenario_id)` in `run_protocol.py`

MCP tools need to locate the active or most recent run without requiring an
explicit `run_id`. Add:

```python
def find_latest_run(scenario_id: str) -> Path | None:
    """Return the active or most-recently-updated run_dir, or None."""
```

**Resolution rule (priority order — do NOT use raw mtime):**

1. **Prefer `status: "running"`** — if exactly one run has `status: "running"`,
   return it. This is the active run.
2. **Multiple running** (abnormal) — return the one with the most recent
   `last_updated` timestamp from `training_status.json`.
3. **No running runs** — return the run with the most recent `finished_at` or
   `failed_at` timestamp across completed/monitor_stopped/failed runs.
4. **No runs at all** — return `None`.

Using `last_updated` / `finished_at` from the status file is more reliable
than filesystem mtime, which can change for unrelated reasons (e.g. file
system operations on a just-completed older run).

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
    # From training_status.json (heartbeat — per-episode freshness)
    "scenario_id": str,
    "run_id": str,
    "status": "running" | "completed" | "monitor_stopped" | "failed" | "no_run",
    "episodes_done": int,
    "episodes_total": int,
    "progress_pct": float,          # episodes_done / episodes_total * 100
    "last_reward": float | None,    # most recent episode reward (already in heartbeat)
    "last_updated": str | None,     # ISO timestamp of last heartbeat write
    "started_at": str | None,       # NEW: when training started
    "finished_at": str | None,      # None if still running
    "error": str | None,            # populated only on status=failed
    "stop_reason": str | None,      # NEW: populated only on status=monitor_stopped
    "last_eval_reward": float | None, # NEW: most recent eval reward, None until first eval
    "logs_dir": str | None,         # NEW: absolute path to logs dir (derived, not hardcoded)
    "run_dir": str,                 # absolute path as string

    # From logs/latest_state.json (~50-episode freshness, supplemental)
    "latest_snapshot": {
        "episode": int,
        "reward_mean_50": float,
        "alpha": float,
        "settled_rate_50": float,
        "buffer_size": int,
        "snapshot_age_episodes": int,  # episodes_done - snapshot.episode
        "snapshot_freshness": "~50-episode intervals"  # static caveat
    } | None,
}
```

`snapshot_age_episodes` = `episodes_done - latest_snapshot.episode` lets AI
judge how stale the snapshot is without computing it itself.

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

## Training Script Changes

**Files:** `scenarios/kundur/train_simulink.py`,
           `scenarios/new_england/train_simulink.py`

All changes follow the same pattern in both files.

### Change 1: Capture `_started_at` and `_logs_dir` as local variables at training start

Before the first `write_training_status` call (around line 299):

```python
_started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
_logs_dir = str(Path(args.log_file).parent)   # derive from actual path, never hardcode
```

### Change 2: Add new fields to the initial `running` write

```python
write_training_status(run_dir, {
    "status": "running",
    "run_id": run_id,
    "scenario": SCENARIO_ID,
    "episodes_total": args.episodes,
    "episodes_done": start_episode,
    "started_at": _started_at,    # ADD
    "logs_dir": _logs_dir,        # ADD
})
```

### Change 3: Add new fields to the per-episode heartbeat write (line ~417)

Also add `last_eval_reward` tracking. Initialize before training loop:

```python
_last_eval_reward: float | None = None
```

Update when eval runs (after eval block). In the per-episode write:

```python
write_training_status(run_dir, {
    "status": "running",
    "run_id": run_id,
    "scenario": SCENARIO_ID,
    "episodes_total": args.episodes,
    "episodes_done": ep - start_episode + 1,
    "last_reward": float(mean_reward),
    "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "started_at": _started_at,        # ADD — carry through
    "logs_dir": _logs_dir,            # ADD — carry through
    "last_eval_reward": _last_eval_reward,  # ADD — None until first eval
})
```

### Change 4: Carry all fields through final status writes

**Completed / monitor_stopped write** (line ~590): add `last_reward`,
`started_at`, `logs_dir`, `last_eval_reward`, and `stop_reason` (only on
`monitor_stopped`; derive from the triggering monitor rule name).

**Failed write** (line ~600): add `started_at`, `logs_dir`,
`last_eval_reward`, `last_reward`.

### `latest_state.json` write frequency unchanged

Every ~50 episodes. The MCP tool accounts for this via `snapshot_age_episodes`.

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
