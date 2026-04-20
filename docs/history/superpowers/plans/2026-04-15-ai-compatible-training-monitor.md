# AI-Compatible Training Monitor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two MCP tools (`training_status`, `training_diagnose`) and a `find_latest_run` helper that let AI read live and post-mortem training state without modifying any training-side code except schema enrichment.

**Architecture:** `find_latest_run` resolves the active run by reading `training_status.json` status fields (never raw mtime). `training_status` merges heartbeat + metrics snapshot into one AI-ready dict. `training_diagnose` parses `events.jsonl` for structured anomaly reports. Training scripts gain four new fields (`started_at` refactored to variable, `logs_dir`, `last_eval_reward`, `stop_reason`) carried through every status write.

**Tech Stack:** Python 3.11+, `pathlib.Path`, `json`, `fastmcp`, `pytest` with `tmp_path` fixtures.

---

## File Map

| Status | File | Change |
|--------|------|--------|
| Modify | `utils/run_protocol.py` | Add `find_latest_run(scenario_id)` |
| Modify | `engine/training_tasks.py` | Add `training_status()` + `training_diagnose()` |
| Modify | `engine/mcp_server.py` | Import + register 2 new tools; update docstring + count |
| Modify | `scenarios/kundur/train_simulink.py` | 4 status-write enrichments |
| Modify | `scenarios/new_england/train_simulink.py` | Same 4 enrichments |
| Modify | `tests/test_run_protocol.py` | 4 new tests for `find_latest_run` |
| Modify | `tests/test_mcp_server.py` | 2 new tests + update 2 existing count tests |
| Create | `tests/test_training_tasks.py` | 8 new tests |

---

## Task 1: `find_latest_run()` in `run_protocol.py`

**Files:**
- Modify: `utils/run_protocol.py`
- Test: `tests/test_run_protocol.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_run_protocol.py`:

```python
# ── find_latest_run ────────────────────────────────────────────────────────────

def _write_status(run_dir: Path, status: dict) -> None:
    """Helper: create run_dir and write training_status.json."""
    run_dir.mkdir(parents=True, exist_ok=True)
    from utils.run_protocol import write_training_status
    write_training_status(run_dir, status)


def test_find_latest_run_returns_none_when_no_runs(tmp_path, monkeypatch):
    from utils import run_protocol
    monkeypatch.setattr(run_protocol, "_PROJECT_ROOT", tmp_path)
    result = run_protocol.find_latest_run("kundur")
    assert result is None


def test_find_latest_run_returns_single_running_run(tmp_path, monkeypatch):
    from utils import run_protocol
    monkeypatch.setattr(run_protocol, "_PROJECT_ROOT", tmp_path)
    run_dir = tmp_path / "results" / "sim_kundur" / "runs" / "run1"
    _write_status(run_dir, {"status": "running", "last_updated": "2026-04-15T10:00:00Z"})
    result = run_protocol.find_latest_run("kundur")
    assert result == run_dir


def test_find_latest_run_multiple_running_returns_most_recent_by_last_updated(tmp_path, monkeypatch):
    from utils import run_protocol
    monkeypatch.setattr(run_protocol, "_PROJECT_ROOT", tmp_path)
    older = tmp_path / "results" / "sim_kundur" / "runs" / "run_old"
    newer = tmp_path / "results" / "sim_kundur" / "runs" / "run_new"
    _write_status(older, {"status": "running", "last_updated": "2026-04-15T09:00:00Z"})
    _write_status(newer, {"status": "running", "last_updated": "2026-04-15T10:00:00Z"})
    result = run_protocol.find_latest_run("kundur")
    assert result == newer


def test_find_latest_run_no_running_returns_most_recent_finished(tmp_path, monkeypatch):
    from utils import run_protocol
    monkeypatch.setattr(run_protocol, "_PROJECT_ROOT", tmp_path)
    older = tmp_path / "results" / "sim_kundur" / "runs" / "run_old"
    newer = tmp_path / "results" / "sim_kundur" / "runs" / "run_new"
    _write_status(older, {"status": "completed", "finished_at": "2026-04-14T12:00:00Z"})
    _write_status(newer, {"status": "completed", "finished_at": "2026-04-15T08:00:00Z"})
    result = run_protocol.find_latest_run("kundur")
    assert result == newer
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "C:\Users\27443\Desktop\Multi-Agent  VSGs"
python -m pytest tests/test_run_protocol.py -k "find_latest_run" -v
```

Expected: FAIL with `AttributeError: module 'utils.run_protocol' has no attribute 'find_latest_run'`

- [ ] **Step 3: Implement `find_latest_run` in `utils/run_protocol.py`**

Add after `read_training_status` (at the end of the file):

```python
def find_latest_run(scenario_id: str) -> Path | None:
    """Return the active or most-recently-updated run_dir, or None.

    Resolution priority (do NOT use raw mtime):
    1. Exactly one run with status "running" → return it.
    2. Multiple "running" runs → return the one with the most recent last_updated.
    3. No running runs → return the run with the most recent finished_at / failed_at.
    4. No runs at all → return None.
    """
    runs_dir = _PROJECT_ROOT / "results" / f"sim_{scenario_id}" / "runs"
    if not runs_dir.exists():
        return None

    candidates: list[tuple[Path, dict]] = []
    for entry in runs_dir.iterdir():
        if not entry.is_dir():
            continue
        status = read_training_status(entry)
        if status is not None:
            candidates.append((entry, status))

    if not candidates:
        return None

    running = [(d, s) for d, s in candidates if s.get("status") == "running"]
    if len(running) == 1:
        return running[0][0]
    if len(running) > 1:
        return max(running, key=lambda item: item[1].get("last_updated") or "")[0]

    # No running runs: use finished_at or failed_at timestamp from file content.
    def _terminal_ts(item: tuple[Path, dict]) -> str:
        s = item[1]
        return s.get("finished_at") or s.get("failed_at") or ""

    return max(candidates, key=_terminal_ts)[0]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_run_protocol.py -k "find_latest_run" -v
```

Expected: PASS (4 tests)

- [ ] **Step 5: Run the full test_run_protocol suite to check for regressions**

```bash
python -m pytest tests/test_run_protocol.py -v
```

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
rtk git add utils/run_protocol.py tests/test_run_protocol.py
rtk git commit -m "feat(monitor): add find_latest_run to run_protocol with status-aware resolution"
```

---

## Task 2: `training_status()` + `training_diagnose()` in `training_tasks.py`

**Files:**
- Modify: `engine/training_tasks.py`
- Create: `tests/test_training_tasks.py`

- [ ] **Step 1: Write the failing tests (create `tests/test_training_tasks.py`)**

```python
"""Tests for engine.training_tasks monitoring tools."""
import json
from pathlib import Path

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_run(tmp_path: Path, scenario: str, run_id: str, status: dict) -> Path:
    """Create a minimal run directory with training_status.json."""
    run_dir = tmp_path / "results" / f"sim_{scenario}" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "training_status.json").write_text(
        json.dumps(status), encoding="utf-8"
    )
    return run_dir


def _make_logs(run_dir: Path) -> Path:
    """Create logs subdirectory and return its path."""
    logs = run_dir / "logs"
    logs.mkdir(exist_ok=True)
    return logs


# ── training_status ────────────────────────────────────────────────────────────

def test_training_status_no_run(tmp_path, monkeypatch):
    import utils.run_protocol as rp
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)
    from engine.training_tasks import training_status
    result = training_status("kundur")
    assert result["status"] == "no_run"
    assert result["scenario_id"] == "kundur"


def test_training_status_running(tmp_path, monkeypatch):
    import utils.run_protocol as rp
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)
    # Build run_dir path first so logs_dir can reference it without a NameError.
    run_dir = tmp_path / "results" / "sim_kundur" / "runs" / "run1"
    run_dir.mkdir(parents=True, exist_ok=True)
    from utils.run_protocol import write_training_status
    write_training_status(run_dir, {
        "status": "running",
        "run_id": "run1",
        "scenario": "kundur",
        "episodes_total": 500,
        "episodes_done": 120,
        "last_reward": -45.3,
        "last_updated": "2026-04-15T10:00:00Z",
        "started_at": "2026-04-15T09:00:00Z",
        "logs_dir": str(run_dir / "logs"),
        "last_eval_reward": -38.1,
    })
    from engine.training_tasks import training_status
    result = training_status("kundur")
    assert result["status"] == "running"
    assert result["run_id"] == "run1"
    assert result["episodes_done"] == 120
    assert result["episodes_total"] == 500
    assert result["progress_pct"] == pytest.approx(24.0)
    assert result["last_reward"] == pytest.approx(-45.3)
    assert result["last_eval_reward"] == pytest.approx(-38.1)
    assert result["started_at"] == "2026-04-15T09:00:00Z"
    assert result["latest_snapshot"] is None  # no latest_state.json yet


def test_training_status_with_latest_state(tmp_path, monkeypatch):
    import utils.run_protocol as rp
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)
    run_dir = _make_run(tmp_path, "kundur", "run1", {
        "status": "running",
        "run_id": "run1",
        "episodes_total": 500,
        "episodes_done": 200,
        "last_reward": -30.0,
        "last_updated": "2026-04-15T11:00:00Z",
    })
    logs = _make_logs(run_dir)
    (logs / "latest_state.json").write_text(json.dumps({
        "episode": 150,
        "reward_mean_50": -55.2,
        "alpha": 0.12,
        "settled_rate_50": 0.72,
        "buffer_size": 8000,
    }), encoding="utf-8")
    from engine.training_tasks import training_status
    result = training_status("kundur")
    snap = result["latest_snapshot"]
    assert snap is not None
    assert snap["episode"] == 150
    assert snap["reward_mean_50"] == pytest.approx(-55.2)
    assert snap["snapshot_age_episodes"] == 50  # 200 - 150
    assert snap["snapshot_freshness"] == "~50-episode intervals"


def test_training_status_without_latest_state(tmp_path, monkeypatch):
    import utils.run_protocol as rp
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)
    _make_run(tmp_path, "kundur", "run1", {
        "status": "completed",
        "run_id": "run1",
        "episodes_total": 500,
        "episodes_done": 500,
        "finished_at": "2026-04-15T12:00:00Z",
    })
    from engine.training_tasks import training_status
    result = training_status("kundur")
    assert result["status"] == "completed"
    assert result["latest_snapshot"] is None


# ── training_diagnose ──────────────────────────────────────────────────────────

def test_training_diagnose_empty_events(tmp_path, monkeypatch):
    import utils.run_protocol as rp
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)
    run_dir = _make_run(tmp_path, "kundur", "run1", {
        "status": "running", "run_id": "run1",
        "episodes_total": 500, "episodes_done": 10,
    })
    logs = _make_logs(run_dir)
    (logs / "events.jsonl").write_text("", encoding="utf-8")
    from engine.training_tasks import training_diagnose
    result = training_diagnose("kundur")
    assert result["event_count"] == 0
    assert result["alerts"] == []
    assert result["monitor_stop"] is None
    assert result["eval_rewards"] == []
    assert result["training_start"] is None
    assert result["training_end"] is None


def test_training_diagnose_parses_events(tmp_path, monkeypatch):
    import utils.run_protocol as rp
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)
    run_dir = _make_run(tmp_path, "kundur", "run1", {
        "status": "monitor_stopped", "run_id": "run1",
        "episodes_total": 500, "episodes_done": 87,
    })
    logs = _make_logs(run_dir)
    events = [
        {"episode": 0, "ts": "2026-04-15T09:00:00Z", "type": "training_start",
         "mode": "simulink", "start_episode": 0, "end_episode": 500},
        {"episode": 50, "ts": "2026-04-15T09:30:00Z", "type": "eval",
         "eval_reward": -42.5},
        {"episode": 85, "ts": "2026-04-15T09:55:00Z", "type": "monitor_alert",
         "rule": "reward_divergence"},
        {"episode": 87, "ts": "2026-04-15T09:57:00Z", "type": "monitor_stop",
         "triggered_by": "monitor"},
        {"episode": 100, "ts": "2026-04-15T10:10:00Z", "type": "checkpoint",
         "file": "ep100.pt"},
    ]
    (logs / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events), encoding="utf-8"
    )
    from engine.training_tasks import training_diagnose
    result = training_diagnose("kundur")
    assert result["event_count"] == 5
    assert result["training_start"] == {"episode": 0, "mode": "simulink"}
    assert result["eval_rewards"] == [{"episode": 50, "eval_reward": -42.5}]
    assert result["alerts"] == [{"episode": 85, "rule": "reward_divergence"}]
    assert result["monitor_stop"] == {"episode": 87}
    assert result["checkpoints"] == [{"episode": 100, "file": "ep100.pt"}]
    assert result["training_end"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_training_tasks.py -v
```

Expected: FAIL with `ImportError` or `AttributeError` — `training_status` and `training_diagnose` don't exist yet.

- [ ] **Step 3: Implement the two functions in `engine/training_tasks.py`**

Add these imports at the top of the existing imports section (after `from pathlib import Path`):

```python
from utils.run_protocol import find_latest_run, get_run_dir, read_training_status
```

Then append the two new functions at the end of the file:

```python
def training_status(scenario_id: str, run_id: str | None = None) -> dict[str, Any]:
    """Return a merged AI summary of the active (or most recent) training run.

    Tier 1 polling tool.  Merges training_status.json (per-episode heartbeat)
    with logs/latest_state.json (~50-episode snapshot).

    Args:
        scenario_id: "kundur" or "ne39"
        run_id: specific run to inspect; if None, uses find_latest_run.

    Returns dict with lifecycle fields, heartbeat metrics, and latest_snapshot.
    """
    if run_id is not None:
        run_dir: Path | None = get_run_dir(scenario_id, run_id)
    else:
        run_dir = find_latest_run(scenario_id)
    if run_dir is None:
        return {
            "scenario_id": scenario_id,
            "status": "no_run",
            "run_id": None,
            "episodes_done": 0,
            "episodes_total": 0,
            "progress_pct": 0.0,
            "last_reward": None,
            "last_updated": None,
            "started_at": None,
            "finished_at": None,
            "error": None,
            "stop_reason": None,
            "last_eval_reward": None,
            "logs_dir": None,
            "run_dir": None,
            "latest_snapshot": None,
        }

    status = read_training_status(run_dir) or {}
    episodes_done = status.get("episodes_done", 0)
    episodes_total = status.get("episodes_total", 0)
    progress_pct = (episodes_done / episodes_total * 100) if episodes_total > 0 else 0.0

    # Determine logs dir: prefer value from status (written by training script),
    # fall back to conventional run_dir/logs for runs started before this feature.
    logs_dir_str = status.get("logs_dir")
    logs_dir_path = Path(logs_dir_str) if logs_dir_str else (run_dir / "logs")

    latest_snapshot = None
    latest_state_path = logs_dir_path / "latest_state.json"
    if latest_state_path.exists():
        try:
            state = json.loads(latest_state_path.read_text(encoding="utf-8"))
            snapshot_episode = state.get("episode", 0)
            latest_snapshot = {
                "episode": snapshot_episode,
                "reward_mean_50": state.get("reward_mean_50"),
                "alpha": state.get("alpha"),
                "settled_rate_50": state.get("settled_rate_50"),
                "buffer_size": state.get("buffer_size"),
                "snapshot_age_episodes": episodes_done - snapshot_episode,
                "snapshot_freshness": "~50-episode intervals",
            }
        except Exception:
            pass  # missing or malformed snapshot is non-fatal

    return {
        "scenario_id": scenario_id,
        "run_id": status.get("run_id"),
        "status": status.get("status"),
        "episodes_done": episodes_done,
        "episodes_total": episodes_total,
        "progress_pct": round(progress_pct, 2),
        "last_reward": status.get("last_reward"),
        "last_updated": status.get("last_updated"),
        "started_at": status.get("started_at"),
        "finished_at": status.get("finished_at"),
        "error": status.get("error"),
        "stop_reason": status.get("stop_reason"),
        "last_eval_reward": status.get("last_eval_reward"),
        "logs_dir": logs_dir_str,
        "run_dir": str(run_dir),
        "latest_snapshot": latest_snapshot,
    }


def training_diagnose(
    scenario_id: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Parse events.jsonl for structured anomaly diagnosis.

    Tier 2 tool — invoke only when training_status reveals an anomaly.

    Args:
        scenario_id: "kundur" or "ne39"
        run_id: specific run to diagnose; if None, uses find_latest_run.

    Returns structured report with alerts, eval trajectory, monitor_stop info.
    """
    if run_id is None:
        run_dir = find_latest_run(scenario_id)
    else:
        run_dir = get_run_dir(scenario_id, run_id)

    _empty: dict[str, Any] = {
        "scenario_id": scenario_id,
        "run_id": run_id or "unknown",
        "event_count": 0,
        "alerts": [],
        "monitor_stop": None,
        "eval_rewards": [],
        "checkpoints": [],
        "training_start": None,
        "training_end": None,
    }

    if run_dir is None:
        return _empty

    status = read_training_status(run_dir) or {}
    logs_dir_str = status.get("logs_dir")
    logs_dir_path = Path(logs_dir_str) if logs_dir_str else (run_dir / "logs")

    events_path = logs_dir_path / "events.jsonl"
    events: list[dict[str, Any]] = []
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    actual_run_id = status.get("run_id") or run_dir.name

    training_start_events = [e for e in events if e.get("type") == "training_start"]
    training_end_events = [e for e in events if e.get("type") == "training_end"]
    monitor_stop_events = [e for e in events if e.get("type") == "monitor_stop"]

    return {
        "scenario_id": scenario_id,
        "run_id": actual_run_id,
        "event_count": len(events),
        "alerts": [
            {"episode": e.get("episode"), "rule": e.get("rule")}
            for e in events if e.get("type") == "monitor_alert"
        ],
        "monitor_stop": (
            {"episode": monitor_stop_events[0].get("episode")}
            if monitor_stop_events else None
        ),
        "eval_rewards": [
            {"episode": e.get("episode"), "eval_reward": e.get("eval_reward")}
            for e in events if e.get("type") == "eval"
        ],
        "checkpoints": [
            {"episode": e.get("episode"), "file": e.get("file")}
            for e in events if e.get("type") == "checkpoint"
        ],
        "training_start": (
            {
                "episode": training_start_events[0].get("episode"),
                "mode": training_start_events[0].get("mode"),
            }
            if training_start_events else None
        ),
        "training_end": (
            {"episode": training_end_events[0].get("episode")}
            if training_end_events else None
        ),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_training_tasks.py -v
```

Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
rtk git add engine/training_tasks.py tests/test_training_tasks.py
rtk git commit -m "feat(monitor): add training_status and training_diagnose MCP tool functions"
```

---

## Task 3: Register new tools in `engine/mcp_server.py`

**Files:**
- Modify: `engine/mcp_server.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mcp_server.py`:

```python
def test_mcp_registers_training_status():
    from engine import mcp_server
    names = [tool.__name__ for tool in mcp_server.PUBLIC_TOOLS]
    assert "training_status" in names


def test_mcp_registers_training_diagnose():
    from engine import mcp_server
    names = [tool.__name__ for tool in mcp_server.PUBLIC_TOOLS]
    assert "training_diagnose" in names
```

Also update the two existing tests that will break (count 36 → 38, and the expected_names list):

Replace the body of `test_public_tools_list_matches_expected_contract` — add `"training_status"` and `"training_diagnose"` as the first two entries (before `"training_evaluate_run"`):

```python
def test_public_tools_list_matches_expected_contract():
    from engine import mcp_server

    expected_names = [
        "training_status",
        "training_diagnose",
        "training_evaluate_run",
        "training_compare_runs",
        "harness_scenario_status",
        "harness_model_inspect",
        "harness_model_patch_verify",
        "harness_model_diagnose",
        "harness_model_report",
        "harness_train_smoke_start",
        "harness_train_smoke_poll",
        "simulink_load_model",
        "simulink_create_model",
        "simulink_close_model",
        "simulink_loaded_models",
        "simulink_bridge_status",
        "simulink_get_block_tree",
        "simulink_describe_block_ports",
        "simulink_trace_port_connections",
        "simulink_explore_block",
        "simulink_query_params",
        "simulink_set_block_params",
        "simulink_check_params",
        "simulink_preflight",
        "simulink_add_block",
        "simulink_add_subsystem",
        "simulink_connect_ports",
        "simulink_delete_block",
        "simulink_build_chain",
        "simulink_compile_diagnostics",
        "simulink_step_diagnostics",
        "simulink_solver_audit",
        "simulink_patch_and_verify",
        "simulink_run_script",
        "simulink_run_script_async",
        "simulink_poll_script",
        "simulink_screenshot",
        "simulink_capture_figure",
    ]

    assert [tool.__name__ for tool in mcp_server.PUBLIC_TOOLS] == expected_names


def test_public_tools_contract_has_stable_size():
    from engine import mcp_server

    assert len(mcp_server.PUBLIC_TOOLS) == 38
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_mcp_server.py -v
```

Expected: 4 failures (`training_status`/`training_diagnose` not in list, count still 36, name list mismatch).

- [ ] **Step 3: Update `engine/mcp_server.py`**

**3a.** Update the module docstring — change `"2  training_* tools  (Training Control: evaluate_run + compare_runs)"` to:

```python
"""engine/mcp_server.py - Python MCP server for structured Simulink and training access.

Registers a curated set of ~39 workflow-level tools for Claude:
  - 4  training_* tools  (Training Monitor: status + diagnose; Training Control: evaluate_run + compare_runs)
  - 8  harness_*  tools  (Model Control: scenario/inspect/patch/diagnose/report/smoke/smoke_full)
  - 27 simulink_* tools  (model building, parameter ops, diagnostics, visual capture)
```

**3b.** Update the import from `engine.training_tasks`:

```python
from engine.training_tasks import (
    training_status,
    training_diagnose,
    training_evaluate_run,
    training_compare_runs,
)
```

**3c.** Update `PUBLIC_TOOLS` — add the two new tools at the top of the Training Control section:

```python
PUBLIC_TOOLS = [
    # --- Training Monitor (2) ---
    training_status,
    training_diagnose,
    # --- Training Control (2) ---
    training_evaluate_run,
    training_compare_runs,
    # ... rest unchanged ...
```

**3d.** Update the MCP `instructions` string — add a sentence about the new tools:

```python
mcp = FastMCP(
    "simulink-tools",
    instructions=(
        "Structured Simulink and training control tools (~38 total). "
        "Use training_status to poll live training progress (Tier 1). "
        "Use training_diagnose only when training_status shows anomaly/failure (Tier 2). "
        "Use training_evaluate_run / training_compare_runs for post-run Training Control workflows. "
        ...
    ),
)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_mcp_server.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
python -m pytest tests/test_run_protocol.py tests/test_training_tasks.py tests/test_mcp_server.py -v --tb=short
```

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
rtk git add engine/mcp_server.py tests/test_mcp_server.py
rtk git commit -m "feat(monitor): register training_status and training_diagnose in MCP server"
```

---

## Task 4: Training script schema enrichment — Kundur

**Files:**
- Modify: `scenarios/kundur/train_simulink.py`

The goal is to carry four new fields through all `write_training_status` calls:
`logs_dir` (always), `started_at` (always), `last_eval_reward` (always), `stop_reason` (only on `monitor_stopped`). Also carry `last_reward` through to final writes.

> **Note:** No unit tests are written for training script changes — these require a live MATLAB/Simulink environment. Correctness is verified by inspecting `training_status.json` on the next live training run.

- [ ] **Step 1: Extract `_started_at` and `_logs_dir` as local variables**

Locate the initial `write_training_status` call (around line 299). Currently `started_at` is computed inline. Replace the inline expression with a local variable, and add `_logs_dir`:

**Before** (lines ~299–307):
```python
write_training_status(run_dir, {
    "status": "running",
    "run_id": run_id,
    "scenario": "kundur",
    "episodes_total": args.episodes,
    "episodes_done": 0,
    "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "last_reward": None,
})
```

**After:**
```python
_started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
write_training_status(run_dir, {
    "status": "running",
    "run_id": run_id,
    "scenario": "kundur",
    "episodes_total": args.episodes,
    "episodes_done": 0,
    "started_at": _started_at,
    "logs_dir": str(Path(args.log_file).parent),
    "last_reward": None,
    "last_eval_reward": None,
})
```

> `_log_dir` already exists (line ~311) but as `os.path.dirname(args.log_file)`.
> Use `str(Path(args.log_file).parent)` in the write for consistency with the spec.
> Add `_logs_dir = str(Path(args.log_file).parent)` immediately after `_started_at`
> so the same value can be reused below without re-computing.

Full replacement after extracting variables:

```python
_started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
_logs_dir = str(Path(args.log_file).parent)
write_training_status(run_dir, {
    "status": "running",
    "run_id": run_id,
    "scenario": "kundur",
    "episodes_total": args.episodes,
    "episodes_done": 0,
    "started_at": _started_at,
    "logs_dir": _logs_dir,
    "last_reward": None,
    "last_eval_reward": None,
})
```

- [ ] **Step 2: Add `_stop_reason` variable before the training loop**

Just after `_last_eval_reward: float | None = None` (line ~320), add:

```python
_stop_reason: str | None = None
```

- [ ] **Step 3: Update the per-episode heartbeat write (~line 417)**

**Before:**
```python
write_training_status(run_dir, {
    "status": "running",
    "run_id": run_id,
    "scenario": "kundur",
    "episodes_total": args.episodes,
    "episodes_done": ep - start_episode + 1,
    "last_reward": float(mean_reward),
    "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
})
```

**After:**
```python
write_training_status(run_dir, {
    "status": "running",
    "run_id": run_id,
    "scenario": "kundur",
    "episodes_total": args.episodes,
    "episodes_done": ep - start_episode + 1,
    "last_reward": float(mean_reward),
    "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "started_at": _started_at,
    "logs_dir": _logs_dir,
    "last_eval_reward": _last_eval_reward,
})
```

- [ ] **Step 4: Capture `_stop_reason` when monitor stops**

In the `if stop_triggered:` block (after the `_new_triggers` loop, before `break`):

```python
if stop_triggered:
    _stop_reason = _new_triggers[-1] if _new_triggers else None
    writer.log_event(ep, "monitor_stop", {"triggered_by": "monitor"})
    ...
```

- [ ] **Step 5: Enrich the final `completed`/`monitor_stopped` write (~line 590)**

**Before:**
```python
final_status = "monitor_stopped" if monitor_stopped else "completed"
write_training_status(run_dir, {
    "status": final_status,
    "run_id": run_id,
    "scenario": "kundur",
    "episodes_total": args.episodes,
    "episodes_done": len(log["episode_rewards"]),
    "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
})
```

**After:**
```python
final_status = "monitor_stopped" if monitor_stopped else "completed"
_final_status_dict: dict = {
    "status": final_status,
    "run_id": run_id,
    "scenario": "kundur",
    "episodes_total": args.episodes,
    "episodes_done": len(log["episode_rewards"]),
    "last_reward": float(log["episode_rewards"][-1]) if log["episode_rewards"] else None,
    "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "started_at": _started_at,
    "logs_dir": _logs_dir,
    "last_eval_reward": _last_eval_reward,
}
if final_status == "monitor_stopped":
    _final_status_dict["stop_reason"] = _stop_reason
write_training_status(run_dir, _final_status_dict)
```

- [ ] **Step 6: Enrich the `failed` write (~line 600)**

**Before:**
```python
write_training_status(run_dir, {
    "status": "failed",
    "run_id": run_id,
    "scenario": "kundur",
    "episodes_total": args.episodes,
    "episodes_done": len(log["episode_rewards"]),
    "failed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "error": str(_train_exc),
})
```

**After:**
```python
write_training_status(run_dir, {
    "status": "failed",
    "run_id": run_id,
    "scenario": "kundur",
    "episodes_total": args.episodes,
    "episodes_done": len(log["episode_rewards"]),
    "last_reward": float(log["episode_rewards"][-1]) if log["episode_rewards"] else None,
    "failed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "started_at": _started_at,
    "logs_dir": _logs_dir,
    "last_eval_reward": _last_eval_reward,
    "error": str(_train_exc),
})
```

- [ ] **Step 7: Run the full test suite to verify no regressions**

```bash
python -m pytest tests/test_run_protocol.py tests/test_training_tasks.py tests/test_mcp_server.py -v --tb=short
```

Expected: All tests PASS (no live MATLAB needed — only the schema changes, not the training loop)

- [ ] **Step 8: Commit**

```bash
rtk git add scenarios/kundur/train_simulink.py
rtk git commit -m "feat(monitor): enrich kundur training_status.json with logs_dir, last_eval_reward, stop_reason"
```

---

## Task 5: Training script schema enrichment — NE39

**Files:**
- Modify: `scenarios/new_england/train_simulink.py`

Same four enrichments as Task 4. The ne39 script is structurally identical. Line numbers are approximately the same (~291, ~416, ~584, ~593).

- [ ] **Step 1: Extract `_started_at` and `_logs_dir` in initial write (~line 291)**

Locate the `write_training_status` call with `"scenario": "ne39"`. Apply the same extraction as Task 4 Step 1, with `"scenario": "ne39"`:

```python
_started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
_logs_dir = str(Path(args.log_file).parent)
write_training_status(run_dir, {
    "status": "running",
    "run_id": run_id,
    "scenario": "ne39",
    "episodes_total": args.episodes,
    "episodes_done": 0,
    "started_at": _started_at,
    "logs_dir": _logs_dir,
    "last_reward": None,
    "last_eval_reward": None,
})
```

- [ ] **Step 2: Add `_stop_reason` before the training loop**

After `_last_eval_reward: float | None = None` (line ~316), add:

```python
_stop_reason: str | None = None
```

- [ ] **Step 3: Update per-episode write (~line 416)**

**Before:**
```python
write_training_status(run_dir, {
    "status": "running",
    "run_id": run_id,
    "scenario": "ne39",
    "episodes_total": args.episodes,
    "episodes_done": ep - start_episode + 1,
    "last_reward": float(mean_reward),
    "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
})
```

**After:**
```python
write_training_status(run_dir, {
    "status": "running",
    "run_id": run_id,
    "scenario": "ne39",
    "episodes_total": args.episodes,
    "episodes_done": ep - start_episode + 1,
    "last_reward": float(mean_reward),
    "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "started_at": _started_at,
    "logs_dir": _logs_dir,
    "last_eval_reward": _last_eval_reward,
})
```

- [ ] **Step 4: Capture `_stop_reason` when monitor stops**

In the `if stop_triggered:` block:

```python
if stop_triggered:
    _stop_reason = _new_triggers[-1] if _new_triggers else None
    writer.log_event(ep, "monitor_stop", {"triggered_by": "monitor"})
    ...
```

- [ ] **Step 5: Enrich final `completed`/`monitor_stopped` write (~line 584)**

```python
final_status = "monitor_stopped" if monitor_stopped else "completed"
_final_status_dict: dict = {
    "status": final_status,
    "run_id": run_id,
    "scenario": "ne39",
    "episodes_total": args.episodes,
    "episodes_done": len(log["episode_rewards"]),
    "last_reward": float(log["episode_rewards"][-1]) if log["episode_rewards"] else None,
    "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "started_at": _started_at,
    "logs_dir": _logs_dir,
    "last_eval_reward": _last_eval_reward,
}
if final_status == "monitor_stopped":
    _final_status_dict["stop_reason"] = _stop_reason
write_training_status(run_dir, _final_status_dict)
```

- [ ] **Step 6: Enrich `failed` write (~line 593)**

```python
write_training_status(run_dir, {
    "status": "failed",
    "run_id": run_id,
    "scenario": "ne39",
    "episodes_total": args.episodes,
    "episodes_done": len(log["episode_rewards"]),
    "last_reward": float(log["episode_rewards"][-1]) if log["episode_rewards"] else None,
    "failed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "started_at": _started_at,
    "logs_dir": _logs_dir,
    "last_eval_reward": _last_eval_reward,
    "error": str(_train_exc),
})
```

- [ ] **Step 7: Run full test suite**

```bash
python -m pytest tests/test_run_protocol.py tests/test_training_tasks.py tests/test_mcp_server.py -v --tb=short
```

Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
rtk git add scenarios/new_england/train_simulink.py
rtk git commit -m "feat(monitor): enrich ne39 training_status.json with logs_dir, last_eval_reward, stop_reason"
```

---

## Self-Review: Spec Coverage Check

| Spec requirement | Task |
|---|---|
| `find_latest_run` with 4-priority resolution | Task 1 |
| `training_status` MCP tool — merges heartbeat + snapshot | Task 2 |
| `training_diagnose` MCP tool — parses events.jsonl | Task 2 |
| `training_status` registered in mcp_server | Task 3 |
| `training_diagnose` registered in mcp_server | Task 3 |
| Kundur: `logs_dir` in all writes | Task 4 |
| Kundur: `started_at` carried through all writes | Task 4 |
| Kundur: `last_eval_reward` in heartbeat + final writes | Task 4 |
| Kundur: `stop_reason` on `monitor_stopped` write | Task 4 |
| Kundur: `last_reward` carried to final writes | Task 4 |
| NE39: same 5 changes | Task 5 |
| `test_find_latest_run_returns_most_recent` | Task 1 |
| `test_find_latest_run_returns_none_when_no_runs` | Task 1 |
| `test_training_status_running` | Task 2 |
| `test_training_status_no_run` | Task 2 |
| `test_training_status_with_latest_state` | Task 2 |
| `test_training_status_without_latest_state` | Task 2 |
| `test_training_diagnose_parses_events` | Task 2 |
| `test_training_diagnose_empty_events` | Task 2 |
| `test_mcp_registers_training_status` | Task 3 |
| `test_mcp_registers_training_diagnose` | Task 3 |
| smoke harness untouched | Not in any task ✓ |
| `training_evaluate_run`/`training_compare_runs` untouched | Not in any task ✓ |

All spec requirements covered. No placeholders. Type names consistent across tasks (`find_latest_run` returns `Path | None`, consumed as `run_dir` in Tasks 2–3).
