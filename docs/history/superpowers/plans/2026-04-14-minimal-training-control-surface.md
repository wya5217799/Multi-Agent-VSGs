# Minimal Training Control Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal MCP-facing training control surface for formal long-running training: launch the run, poll and monitor its current state from existing artifacts, and keep AI outside the training loop.

**Architecture:** Keep formal training as an external OS process and reuse the outputs the training scripts already write: `training_status.json`, `training_log.json`, checkpoints, and latest-run directories under `results/sim_*`. Extend `engine/training_launch.py` from a read-only preflight helper into a thin launch/poll/monitor control plane, then expose that through `engine/training_tasks.py` and `engine/mcp_server.py`. `engine/smoke_tasks.py` stays in the repo only as a legacy bounded preflight utility from earlier model-stabilization phases; it is not part of the default long-training path. Do not redesign metrics, do not add training-loop callbacks for AI, and do not build post-training plotting in this plan.

**Tech Stack:** Python 3.11+, FastMCP, pytest, Windows subprocess process control, existing `scenarios/*/train_simulink.py` entrypoints, `utils/run_protocol.py` run layout.

---

## Scope

In scope:

- Full training `start` as a detached OS process.
- Full training `poll` / runtime monitoring based on existing run artifacts and process liveness.
- Reuse existing training outputs exactly as they are today.
- MCP tool exposure for the minimal training control path.
- Documentation updates for the new official launch path.

Out of scope:

- Training-after-run plotting or report generation.
- New training metrics, new reward diagnostics, or AI-defined judgments.
- AI participation inside the training loop.
- Automatic stop / resume / retune policies.
- Replacing `scripts/launch_training.ps1` as the user-facing manual launcher.
- Refactoring or extending `engine/smoke_tasks.py`.
- Making `smoke` part of the default formal-training workflow.

## File Structure

Files to modify:

- `engine/training_launch.py`
  Responsibility: training launch facts, detached process start, process polling, and run artifact discovery.
- `engine/training_tasks.py`
  Responsibility: thin MCP wrappers for training control tools.
- `engine/mcp_server.py`
  Responsibility: register the new public MCP tools.
- `tests/test_training_launch.py`
  Responsibility: unit coverage for interpreter resolution, detached launch, and poll/monitor state classification.
- `AGENTS.md`
  Responsibility: declare the official minimal training-control path for agents.
- `CLAUDE.md`
  Responsibility: mirror the operator-facing launch/poll guidance already used elsewhere in the repo.

Files intentionally left unchanged in this plan:

- `scenarios/kundur/train_simulink.py`
- `scenarios/new_england/train_simulink.py`
- `utils/run_protocol.py`
- `engine/smoke_tasks.py`
- `engine/training_tasks.py` post-run verdict functions `training_evaluate_run` / `training_compare_runs`

Reason: the current training scripts already emit the state and metrics this plan needs. The new layer should consume existing outputs instead of changing the training loop. `smoke` is retained only as a non-default legacy preflight tool, not the design center for current long-training control.

### Task 1: Extend `engine/training_launch.py` into a real start/poll/monitor control plane

**Files:**
- Modify: `engine/training_launch.py`
- Test: `tests/test_training_launch.py`

- [ ] **Step 1: Write the failing tests for interpreter resolution and detached launch**

```python
def test_status_uses_explicit_training_python_env(monkeypatch, tmp_path):
    import engine.training_launch as tl

    monkeypatch.setenv("SIMULINK_TRAINING_PYTHON", r"C:\custom\python.exe")
    monkeypatch.setattr(
        tl,
        "load_scenario_reference",
        lambda sid: _fake_ref(sid, "scenarios/kundur/train_simulink.py"),
    )
    monkeypatch.setattr(tl, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(tl, "_find_active_pid", lambda _: None)

    result = tl.get_training_launch_status("kundur")
    assert result["launch"]["python_executable"] == r"C:\custom\python.exe"


def test_start_training_process_returns_pid_and_launch_metadata(monkeypatch, tmp_path):
    import engine.training_launch as tl

    monkeypatch.delenv("SIMULINK_TRAINING_PYTHON", raising=False)
    monkeypatch.setattr(
        tl,
        "load_scenario_reference",
        lambda sid: _fake_ref(sid, "scenarios/new_england/train_simulink.py", "NE39bus_v2"),
    )
    monkeypatch.setattr(tl, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(tl, "_find_active_pid", lambda _: None)

    captured = {}

    class DummyProc:
        pid = 24680

    def fake_popen(cmd, cwd, creationflags):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["creationflags"] = creationflags
        return DummyProc()

    monkeypatch.setattr(tl.subprocess, "Popen", fake_popen)

    result = tl.start_training_process("ne39", episodes=500, mode="simulink")

    assert result["pid"] == 24680
    assert result["scenario_id"] == "ne39"
    assert result["mode"] == "simulink"
    assert result["episodes"] == 500
    assert captured["cmd"][1].endswith("scenarios/new_england/train_simulink.py")
    assert "--episodes" in captured["cmd"]
```

- [ ] **Step 2: Run the targeted tests and confirm they fail because the functions do not exist yet**

Run:

```bash
pytest tests/test_training_launch.py -k "explicit_training_python_env or start_training_process_returns_pid" -v
```

Expected:

```text
FAILED tests/test_training_launch.py::test_status_uses_explicit_training_python_env
FAILED tests/test_training_launch.py::test_start_training_process_returns_pid_and_launch_metadata
```

- [ ] **Step 3: Implement explicit interpreter resolution and detached start in `engine/training_launch.py`**

```python
import os
from datetime import datetime, timezone

_DEFAULT_TRAINING_PYTHON = Path(r"C:\Users\27443\miniconda3\envs\andes_env\python.exe")


def _resolve_training_python() -> Path:
    explicit = os.environ.get("SIMULINK_TRAINING_PYTHON", "").strip()
    if explicit:
        return Path(explicit)
    if _DEFAULT_TRAINING_PYTHON.exists():
        return _DEFAULT_TRAINING_PYTHON
    return Path(sys.executable)


def _detached_creationflags() -> int:
    flags = 0
    for name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP"):
        flags |= int(getattr(subprocess, name, 0))
    return flags


def start_training_process(
    scenario_id: str,
    *,
    episodes: int = 500,
    mode: str = "simulink",
) -> dict[str, Any]:
    status = get_training_launch_status(scenario_id)
    if not status.get("supported"):
        return {
            "supported": False,
            "scenario_id": scenario_id,
            "error": status.get("error", "unknown scenario_id"),
        }
    launch = status.get("launch")
    if not launch:
        return {
            "supported": False,
            "scenario_id": scenario_id,
            "error": "launch spec unavailable",
        }

    launched_at = datetime.now(timezone.utc).isoformat()
    command = [
        launch["python_executable"],
        str(_PROJECT_ROOT / launch["script"]),
        "--mode", mode,
        "--episodes", str(episodes),
    ]
    proc = subprocess.Popen(
        command,
        cwd=str(_PROJECT_ROOT),
        creationflags=_detached_creationflags(),
    )
    return {
        "supported": True,
        "scenario_id": scenario_id,
        "pid": proc.pid,
        "mode": mode,
        "episodes": episodes,
        "launched_at": launched_at,
        "command": subprocess.list2cmdline(command),
    }
```

- [ ] **Step 4: Re-run the targeted tests and confirm they pass**

Run:

```bash
pytest tests/test_training_launch.py -k "explicit_training_python_env or start_training_process_returns_pid" -v
```

Expected:

```text
PASSED tests/test_training_launch.py::test_status_uses_explicit_training_python_env
PASSED tests/test_training_launch.py::test_start_training_process_returns_pid_and_launch_metadata
```

- [ ] **Step 5: Commit the launch control-plane extension**

```bash
git add engine/training_launch.py tests/test_training_launch.py
git commit -m "feat: add detached full-training launch control"
```

### Task 2: Add poll/monitor state classification from existing training artifacts

**Files:**
- Modify: `engine/training_launch.py`
- Test: `tests/test_training_launch.py`

- [ ] **Step 1: Write the failing tests for `bootstrapping`, `running`, `stalled`, and `failed_before_status`**

```python
def test_poll_returns_bootstrapping_when_pid_alive_but_status_missing(monkeypatch, tmp_path):
    import engine.training_launch as tl

    monkeypatch.setattr(tl, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(tl, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(tl, "_find_latest_run_after", lambda scenario_id, launched_at: None)

    result = tl.poll_training_process("kundur", pid=111, launched_at="2026-04-14T10:00:00+00:00")

    assert result["process_status"] == "bootstrapping_backend"
    assert result["run_id"] is None
    assert result["training_status"] is None


def test_poll_returns_running_with_existing_training_status(monkeypatch, tmp_path):
    import engine.training_launch as tl

    run_dir = tmp_path / "results" / "sim_kundur" / "runs" / "kundur_simulink_20260414_180000"
    run_dir.mkdir(parents=True)
    (run_dir / "training_status.json").write_text(
        json.dumps({
            "status": "running",
            "run_id": "kundur_simulink_20260414_180000",
            "episodes_total": 500,
            "episodes_done": 12,
            "last_reward": 3.5,
        }),
        encoding="utf-8",
    )

    monkeypatch.setattr(tl, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(tl, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(
        tl,
        "_find_latest_run_after",
        lambda scenario_id, launched_at: ("kundur_simulink_20260414_180000", run_dir),
    )

    result = tl.poll_training_process("kundur", pid=111, launched_at="2026-04-14T10:00:00+00:00")

    assert result["process_status"] == "running"
    assert result["run_id"] == "kundur_simulink_20260414_180000"
    assert result["training_status"]["episodes_done"] == 12


def test_poll_returns_stalled_when_status_not_updated(monkeypatch, tmp_path):
    import engine.training_launch as tl

    run_dir = tmp_path / "results" / "sim_kundur" / "runs" / "kundur_simulink_20260414_180000"
    run_dir.mkdir(parents=True)
    (run_dir / "training_status.json").write_text(
        json.dumps({
            "status": "running",
            "run_id": "kundur_simulink_20260414_180000",
            "episodes_total": 500,
            "episodes_done": 12,
            "last_updated": "2026-04-14T10:00:00+00:00",
        }),
        encoding="utf-8",
    )

    monkeypatch.setattr(tl, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(tl, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(
        tl,
        "_find_latest_run_after",
        lambda scenario_id, launched_at: ("kundur_simulink_20260414_180000", run_dir),
    )

    result = tl.poll_training_process(
        "kundur",
        pid=111,
        launched_at="2026-04-14T09:00:00+00:00",
        stale_after_sec=300,
        now_utc="2026-04-14T10:10:00+00:00",
    )

    assert result["process_status"] == "stalled"
    assert result["training_status"]["episodes_done"] == 12


def test_poll_returns_failed_before_status_when_pid_dead_and_run_missing(monkeypatch, tmp_path):
    import engine.training_launch as tl

    monkeypatch.setattr(tl, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(tl, "_is_pid_alive", lambda pid: False)
    monkeypatch.setattr(tl, "_find_latest_run_after", lambda scenario_id, launched_at: None)

    result = tl.poll_training_process("ne39", pid=333, launched_at="2026-04-14T10:00:00+00:00")

    assert result["process_status"] == "failed_before_status"
    assert result["training_status"] is None
```

- [ ] **Step 2: Run the poll/monitor state tests and verify they fail before implementation**

Run:

```bash
pytest tests/test_training_launch.py -k "bootstrapping_when_pid_alive or running_with_existing_training_status or stalled_when_status_not_updated or failed_before_status_when_pid_dead" -v
```

Expected:

```text
FAILED tests/test_training_launch.py::test_poll_returns_bootstrapping_when_pid_alive_but_status_missing
FAILED tests/test_training_launch.py::test_poll_returns_running_with_existing_training_status
FAILED tests/test_training_launch.py::test_poll_returns_stalled_when_status_not_updated
FAILED tests/test_training_launch.py::test_poll_returns_failed_before_status_when_pid_dead_and_run_missing
```

- [ ] **Step 3: Implement artifact-driven polling and basic runtime monitoring in `engine/training_launch.py`**

```python
def _runs_root(scenario_id: str) -> Path:
    return _PROJECT_ROOT / "results" / f"sim_{scenario_id}" / "runs"


def _find_latest_run_after(scenario_id: str, launched_at: str) -> tuple[str, Path] | None:
    runs_root = _runs_root(scenario_id)
    if not runs_root.is_dir():
        return None
    cutoff = launched_at
    candidates: list[tuple[str, Path, str]] = []
    for run_dir in runs_root.iterdir():
        if not run_dir.is_dir():
            continue
        status_file = run_dir / "training_status.json"
        if not status_file.exists():
            continue
        try:
            payload = json.loads(status_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        started_at = str(payload.get("started_at") or payload.get("last_updated") or "")
        if started_at and started_at >= cutoff:
            candidates.append((run_dir.name, run_dir, started_at))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[2], reverse=True)
    run_id, run_dir, _ = candidates[0]
    return run_id, run_dir


def _read_training_status_file(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / "training_status.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _iso_to_epoch(value: str) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def poll_training_process(
    scenario_id: str,
    *,
    pid: int,
    launched_at: str,
    stale_after_sec: int = 600,
    now_utc: str | None = None,
) -> dict[str, Any]:
    latest = _find_latest_run_after(scenario_id, launched_at)
    pid_alive = _is_pid_alive(pid)

    if latest is None and pid_alive:
        return {
            "scenario_id": scenario_id,
            "pid": pid,
            "launched_at": launched_at,
            "process_status": "bootstrapping_backend",
            "run_id": None,
            "training_status": None,
        }
    if latest is None and not pid_alive:
        return {
            "scenario_id": scenario_id,
            "pid": pid,
            "launched_at": launched_at,
            "process_status": "failed_before_status",
            "run_id": None,
            "training_status": None,
        }

    run_id, run_dir = latest
    training_status = _read_training_status_file(run_dir)
    status_name = None if training_status is None else training_status.get("status")
    process_status = "running" if pid_alive else (status_name or "finished")
    if pid_alive and training_status:
        heartbeat = (
            str(training_status.get("last_updated") or "")
            or str(training_status.get("started_at") or "")
        )
        heartbeat_ts = _iso_to_epoch(heartbeat)
        now_ts = _iso_to_epoch(now_utc) if now_utc else time.time()
        if heartbeat_ts is not None and now_ts - heartbeat_ts > stale_after_sec:
            process_status = "stalled"
    return {
        "scenario_id": scenario_id,
        "pid": pid,
        "launched_at": launched_at,
        "process_status": process_status,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "training_status": training_status,
    }
```

- [ ] **Step 4: Run the full `training_launch` test file and make sure all covered launch/poll states pass**

Run:

```bash
pytest tests/test_training_launch.py -v
```

Expected:

```text
PASSED tests/test_training_launch.py::test_status_uses_explicit_training_python_env
PASSED tests/test_training_launch.py::test_start_training_process_returns_pid_and_launch_metadata
PASSED tests/test_training_launch.py::test_poll_returns_bootstrapping_when_pid_alive_but_status_missing
PASSED tests/test_training_launch.py::test_poll_returns_running_with_existing_training_status
PASSED tests/test_training_launch.py::test_poll_returns_stalled_when_status_not_updated
PASSED tests/test_training_launch.py::test_poll_returns_failed_before_status_when_pid_dead_and_run_missing
```

- [ ] **Step 5: Commit the poll/monitor implementation**

```bash
git add engine/training_launch.py tests/test_training_launch.py
git commit -m "feat: add artifact-driven full-training monitoring"
```

### Task 3: Expose the minimal long-training control tools through MCP

**Files:**
- Modify: `engine/training_tasks.py`
- Modify: `engine/mcp_server.py`
- Create: `tests/test_training_tasks.py`

- [ ] **Step 1: Write the failing wrapper tests for `training_start_run` and `training_poll_run`**

```python
from unittest.mock import patch


def test_training_start_run_delegates_to_training_launch():
    from engine import training_tasks

    with patch("engine.training_tasks.start_training_process") as mock_start:
        mock_start.return_value = {"scenario_id": "kundur", "pid": 123}
        result = training_tasks.training_start_run("kundur", episodes=50, mode="simulink")

    mock_start.assert_called_once_with("kundur", episodes=50, mode="simulink")
    assert result["pid"] == 123


def test_training_poll_run_delegates_to_training_launch():
    from engine import training_tasks

    with patch("engine.training_tasks.poll_training_process") as mock_poll:
        mock_poll.return_value = {"scenario_id": "kundur", "process_status": "stalled"}
        result = training_tasks.training_poll_run(
            "kundur",
            pid=123,
            launched_at="2026-04-14T10:00:00+00:00",
        )

    mock_poll.assert_called_once_with(
        "kundur",
        pid=123,
        launched_at="2026-04-14T10:00:00+00:00",
    )
    assert result["process_status"] == "stalled"
```

- [ ] **Step 2: Run the wrapper tests and confirm they fail because the wrappers are not defined yet**

Run:

```bash
pytest tests/test_training_tasks.py -v
```

Expected:

```text
FAILED tests/test_training_tasks.py::test_training_start_run_delegates_to_training_launch
FAILED tests/test_training_tasks.py::test_training_poll_run_delegates_to_training_launch
```

- [ ] **Step 3: Implement the wrappers and register them in `engine/mcp_server.py`**

```python
from engine.training_launch import (
    get_training_launch_status,
    poll_training_process,
    start_training_process,
)


def training_start_run(
    scenario_id: str,
    episodes: int = 500,
    mode: str = "simulink",
) -> dict[str, Any]:
    return start_training_process(scenario_id, episodes=episodes, mode=mode)


def training_poll_run(
    scenario_id: str,
    pid: int,
    launched_at: str,
) -> dict[str, Any]:
    return poll_training_process(scenario_id, pid=pid, launched_at=launched_at)
```

```python
from engine.training_tasks import (
    training_compare_runs,
    training_evaluate_run,
    training_poll_run,
    training_start_run,
)

PUBLIC_TOOLS = [
    training_start_run,
    training_poll_run,
    training_evaluate_run,
    training_compare_runs,
    # existing harness_* and simulink_* tools unchanged below
]
```

- [ ] **Step 4: Run the wrapper tests plus a compile sanity check**

Run:

```bash
pytest tests/test_training_tasks.py -v
python -m compileall engine
```

Expected:

```text
PASSED tests/test_training_tasks.py::test_training_start_run_delegates_to_training_launch
PASSED tests/test_training_tasks.py::test_training_poll_run_delegates_to_training_launch
Listing 'engine'...
```

- [ ] **Step 5: Commit the MCP exposure**

```bash
git add engine/training_tasks.py engine/mcp_server.py tests/test_training_tasks.py
git commit -m "feat: expose minimal training start and poll tools"
```

### Task 4: Update agent/operator docs to match the minimal design

**Files:**
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add the new official minimal training-control wording to `AGENTS.md`**

```md
## Training Control (minimal)

- Full training runs are external OS processes. They must not depend on the agent staying connected.
- Use `engine.training_launch.get_training_launch_status(scenario_id)` for read-only launch facts.
- Use MCP `training_start_run` to launch a full run.
- Use MCP `training_poll_run` to read current run state and detect basic runtime stalls from existing training artifacts.
- Do not add new training metrics or post-training plotting in this path.
- `engine/smoke_tasks.py` is retained only as a non-default legacy preflight tool.
```

- [ ] **Step 2: Mirror the same operator guidance in `CLAUDE.md`**

```md
### Full Training Control

- `training_start_run` — detached full-training launch using the existing scenario entrypoint
- `training_poll_run` — artifact-driven poll for bootstrapping / running / stalled / finished states
- `training_evaluate_run` / `training_compare_runs` remain post-run result readers only
- `smoke` remains available as a legacy bounded preflight utility, not the main long-training path
```

- [ ] **Step 3: Verify both docs mention the new tools and the scope boundary**

Run:

```bash
Select-String -Path AGENTS.md,CLAUDE.md -Pattern "training_start_run|training_poll_run|smoke|post-training plotting"
```

Expected:

```text
AGENTS.md:...
CLAUDE.md:...
```

- [ ] **Step 4: Commit the documentation alignment**

```bash
git add AGENTS.md CLAUDE.md
git commit -m "docs: define minimal training control launch and poll path"
```

## Final Verification

- [ ] Run the full targeted verification set before merging:

```bash
pytest tests/test_training_launch.py tests/test_training_tasks.py -v
python -m compileall engine
```

Expected:

```text
PASSED tests/test_training_launch.py::...
PASSED tests/test_training_tasks.py::...
Listing 'engine'...
```

- [ ] Manually sanity-check one detached launch on Windows after code review:

```bash
python -c "from engine.training_tasks import training_start_run; print(training_start_run('kundur', episodes=1, mode='standalone'))"
```

Expected:

```text
{'supported': True, 'scenario_id': 'kundur', 'pid': ..., 'mode': 'standalone', 'episodes': 1, 'launched_at': '...'}
```

This final manual check is only for launch mechanics. It does not validate training quality, does not exercise legacy `smoke`, and does not add any post-training analysis scope.
