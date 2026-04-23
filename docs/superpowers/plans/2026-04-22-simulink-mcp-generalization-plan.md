# Simulink MCP Generalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the Simulink MCP layer into a reusable general tool surface while preserving the current Kundur/NE39 VSG training bridge.

**Architecture:** Add general MATLAB primitives under `slx_helpers/`, expose stable primitives as `simulink_*` MCP tools, and keep VSG/RL semantics in project adapters. Existing VSG helpers remain compatibility wrappers until Kundur and NE39 bridge checks pass.

**Tech Stack:** Python, FastMCP, MATLAB Engine for Python, Simulink R2025b, MATLAB `.m` helpers, pytest, `simulink-toolbox` skill files.

---

## Source Documents

- Boundary decision: `docs/decisions/2026-04-22-simulink-mcp-generalization-boundary.md`
- MCP server: `engine/mcp_server.py`
- MCP wrappers: `engine/mcp_simulink_tools.py`
- MATLAB helper directory: `slx_helpers/`
- VSG bridge: `engine/simulink_bridge.py`
- Codex skill routing: `C:\Users\27443\.codex\skills\simulink-toolbox`
- Claude skill routing: `C:\Users\27443\.claude\skills\simulink-toolbox`
- Skill index generator: `scripts/regen_skill_index.py`

## File Responsibility Map

| File | Responsibility in this plan |
| --- | --- |
| `slx_helpers/README.md` | State helper boundary and classify legacy VSG helpers |
| `slx_helpers/slx_model_status.m` | Return loaded, dirty, file, FastRestart, solver, and StopTime state |
| `slx_helpers/slx_save_model.m` | Save a model or save to a target path with structured result |
| `slx_helpers/slx_workspace_set.m` | Set base-workspace variables from a struct in one MATLAB call |
| `slx_helpers/slx_run_window.m` | Run a model from StartTime to StopTime using `Simulink.SimulationInput` |
| `slx_helpers/slx_runtime_reset.m` | General FastRestart reset and runtime data cleanup primitive |
| `slx_helpers/slx_signal_snapshot.m` | Existing signal snapshot primitive; expose through MCP after smoke tests |
| `engine/mcp_simulink_tools.py` | Public Python wrappers and MATLAB return conversion |
| `engine/mcp_server.py` | Public MCP registration order and instructions |
| `scripts/regen_skill_index.py` | Tool metadata and multi-skill-dir generation for `.codex` and `.claude` |
| `C:\Users\27443\.codex\skills\simulink-toolbox\index.json` | Generated Codex tool inventory |
| `C:\Users\27443\.claude\skills\simulink-toolbox\index.json` | Generated Claude tool inventory |
| `C:\Users\27443\.codex\skills\simulink-toolbox\map.md` | Codex AI routing for runtime, signal, workspace, save/status tools |
| `C:\Users\27443\.claude\skills\simulink-toolbox\map.md` | Claude AI routing for runtime, signal, workspace, save/status tools |
| `C:\Users\27443\.codex\skills\simulink-toolbox\SKILL.md` | Codex skill entrypoint; preserve Codex hook wording |
| `C:\Users\27443\.claude\skills\simulink-toolbox\SKILL.md` | Claude skill entrypoint; preserve Claude hook wording |
| `tests/test_mcp_tool_helper_coverage.py` | Static coverage from public MCP tools to helper files |
| `tests/test_mcp_simulink_tools.py` | Python wrapper tests with mocked MATLAB session |
| `tests/test_slx_helper_boundary.py` | Static boundary test preventing new domain-specific helpers in the general layer |
| `tests/test_simulink_general_runtime.py` | MATLAB-marked smoke tests for new runtime primitives |
| `engine/simulink_bridge.py` | Later adapter migration after primitives are stable |
| `tests/test_simulink_bridge.py` | VSG bridge regression coverage |

## Invariants

- Public `simulink_*` tools use general Simulink vocabulary.
- No new public `simulink_*` tool may require VSG terms such as agent, reward,
  `M_values`, `D_values`, `Pe`, `omega`, `rocof`, or `delta`.
- `harness_*` and `training_*` stay project-specific.
- `slx_warmup`, `slx_step_and_read`, `slx_extract_state`, and
  `slx_build_bridge_config` remain available until all direct callers migrate.
- Every public wrapper that calls `session.call("slx_*", ...)` must have a
  matching helper file in `slx_helpers/`.
- Skill `index.json` is generated from `engine.mcp_server.PUBLIC_TOOLS`; routing
  prose lives in `map.md`.

---

## Task 1: Add Boundary Documentation and Static Guard

**Files:**
- Modify: `slx_helpers/README.md`
- Modify: `slx_helpers/slx_batch_query.m`
- Modify: `slx_helpers/slx_screenshot.m`
- Create: `tests/test_slx_helper_boundary.py`

- [ ] **Step 1: Remove project-specific examples from general helper comments**

In `slx_helpers/slx_batch_query.m`, replace the Kundur example paths with
generic names:

```matlab
%   Example - read all params:
%     r = slx_batch_query('demo_model', {
%         'demo_model/Gain1',
%         'demo_model/Gain2'
%     });
%     r(1).params.Gain   % -> '2'
%
%   Example - read selected params only:
%     r = slx_batch_query('demo_model', {'demo_model/Gain1'}, {'Gain'});
%     r(1).missing_params  % -> {} or {'Gain'} if Gain does not exist
```

In `slx_helpers/slx_screenshot.m`, replace project-specific examples with:

```matlab
%   system_path  - Model name ('demo_model') or subsystem path
%                  ('demo_model/Controller'). The model must be loaded.
```

- [ ] **Step 2: Update `slx_helpers/README.md` with a boundary table**

Add sections named exactly:

```markdown
## Boundary

General helpers may use Simulink concepts: model, block, line, port, parameter,
workspace variable, SimulationInput, SimulationOutput, timeseries, solver,
FastRestart, diagnostics, screenshot, and figure.

General helpers must not introduce new APIs whose primary contract is expressed
in VSG/RL terms: agent, episode, reward, M/D action, Pe, omega, rocof, delta,
Kundur, or NE39.

## Legacy Project Adapters

The following helpers are retained for the active Yang 2023 reproduction path
and are not general Simulink primitives:

- `slx_warmup.m`
- `slx_step_and_read.m`
- `slx_extract_state.m`
- `slx_build_bridge_config.m`
- `slx_validate_model.m`
```

- [ ] **Step 3: Write the static boundary test**

Create `tests/test_slx_helper_boundary.py`:

```python
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SLX_HELPERS = REPO_ROOT / "slx_helpers"

LEGACY_PROJECT_ADAPTERS = {
    "slx_warmup.m",
    "slx_step_and_read.m",
    "slx_extract_state.m",
    "slx_build_bridge_config.m",
    "slx_validate_model.m",
}

FORBIDDEN_GENERAL_TOKENS = {
    "agent_ids",
    "m_values",
    "d_values",
    "reward",
    "episode",
    "kundur",
    "ne39",
    "vsg",
    "vsg-base",
    "system-base",
}


def test_general_slx_helpers_do_not_add_project_terms():
    offenders = {}
    for path in sorted(SLX_HELPERS.glob("slx_*.m")):
        if path.name in LEGACY_PROJECT_ADAPTERS:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        hits = sorted(token for token in FORBIDDEN_GENERAL_TOKENS if token in text)
        if hits:
            offenders[path.name] = hits
    assert not offenders, offenders
```

- [ ] **Step 4: Run the static boundary test**

Run:

```powershell
python -m pytest tests/test_slx_helper_boundary.py -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```powershell
git add slx_helpers/README.md slx_helpers/slx_batch_query.m slx_helpers/slx_screenshot.m tests/test_slx_helper_boundary.py
git commit -m "docs: define slx helper generalization boundary"
```

---

## Task 2: Add General MATLAB Runtime Primitives

**Files:**
- Create: `slx_helpers/slx_model_status.m`
- Create: `slx_helpers/slx_save_model.m`
- Create: `slx_helpers/slx_workspace_set.m`
- Create: `slx_helpers/slx_run_window.m`
- Create: `slx_helpers/slx_runtime_reset.m`
- Test: `tests/test_mcp_tool_helper_coverage.py`

- [ ] **Step 1: Add `slx_model_status.m`**

Create a MATLAB helper with this contract:

```matlab
function result = slx_model_status(model_name)
%SLX_MODEL_STATUS Return general loaded/dirty/runtime state for one model.

    model_name = char(model_name);
    result = struct( ...
        'model_name', model_name, ...
        'loaded', false, ...
        'dirty', '', ...
        'file_name', '', ...
        'fast_restart', '', ...
        'solver', '', ...
        'start_time', '', ...
        'stop_time', '', ...
        'ok', true, ...
        'error_message', '');

    try
        result.loaded = bdIsLoaded(model_name);
        if ~result.loaded
            return;
        end
        result.dirty = char(get_param(model_name, 'Dirty'));
        result.file_name = char(get_param(model_name, 'FileName'));
        result.fast_restart = char(get_param(model_name, 'FastRestart'));
        result.solver = char(get_param(model_name, 'Solver'));
        result.start_time = char(get_param(model_name, 'StartTime'));
        result.stop_time = char(get_param(model_name, 'StopTime'));
    catch ME
        result.ok = false;
        result.error_message = char(ME.message);
    end
end
```

- [ ] **Step 2: Add `slx_save_model.m`**

Create a helper with this contract:

```matlab
function result = slx_save_model(model_name, target_path)
%SLX_SAVE_MODEL Save a loaded model, optionally to a target path.

    if nargin < 2
        target_path = '';
    end

    model_name = char(model_name);
    target_path = char(target_path);
    result = struct( ...
        'model_name', model_name, ...
        'target_path', target_path, ...
        'saved', false, ...
        'dirty_after', '', ...
        'file_name', '', ...
        'ok', true, ...
        'error_message', '');

    try
        if ~bdIsLoaded(model_name)
            load_system(model_name);
        end
        if isempty(target_path)
            save_system(model_name);
        else
            save_system(model_name, target_path);
        end
        result.saved = true;
        result.dirty_after = char(get_param(model_name, 'Dirty'));
        result.file_name = char(get_param(model_name, 'FileName'));
    catch ME
        result.ok = false;
        result.error_message = char(ME.message);
    end
end
```

- [ ] **Step 3: Add `slx_workspace_set.m`**

Create a helper with this contract:

```matlab
function result = slx_workspace_set(vars)
%SLX_WORKSPACE_SET Set MATLAB base-workspace variables from a scalar struct.

    result = struct( ...
        'ok', true, ...
        'vars_written', {{}}, ...
        'errors', {{}}, ...
        'error_message', '');

    try
        fields = fieldnames(vars);
        for i = 1:numel(fields)
            name = fields{i};
            assignin('base', name, vars.(name));
            result.vars_written{end + 1, 1} = name; %#ok<AGROW>
        end
    catch ME
        result.ok = false;
        result.error_message = char(ME.message);
        result.errors{end + 1, 1} = char(ME.message);
    end
end
```

- [ ] **Step 4: Add `slx_run_window.m`**

Create a helper with this contract:

```matlab
function result = slx_run_window(model_name, start_time, stop_time, capture_errors)
%SLX_RUN_WINDOW Run one model over a controlled simulation window.

    if nargin < 4 || isempty(capture_errors)
        capture_errors = true;
    end

    model_name = char(model_name);
    result = struct( ...
        'model_name', model_name, ...
        'start_time', double(start_time), ...
        'stop_time', double(stop_time), ...
        'sim_time_reached', [], ...
        'ok', true, ...
        'error_message', '');

    try
        load_system(model_name);
        sim_in = Simulink.SimulationInput(model_name);
        if logical(capture_errors)
            capture_value = 'on';
        else
            capture_value = 'off';
        end
        sim_in = sim_in.setModelParameter( ...
            'StartTime', num2str(double(start_time), '%.9g'), ...
            'StopTime', num2str(double(stop_time), '%.9g'), ...
            'CaptureErrors', capture_value);
        sim_out = sim(sim_in); %#ok<NASGU>
        result.sim_time_reached = double(stop_time);
    catch ME
        result.ok = false;
        result.error_message = char(ME.message);
    end
end
```

- [ ] **Step 5: Add `slx_runtime_reset.m`**

Create a helper with this contract:

```matlab
function result = slx_runtime_reset(model_name, fast_restart, clear_sdi, clear_workspace_pattern)
%SLX_RUNTIME_RESET Reset general Simulink runtime state.

    if nargin < 2 || isempty(fast_restart)
        fast_restart = '';
    end
    if nargin < 3 || isempty(clear_sdi)
        clear_sdi = false;
    end
    if nargin < 4
        clear_workspace_pattern = '';
    end

    model_name = char(model_name);
    fast_restart = char(fast_restart);
    clear_workspace_pattern = char(clear_workspace_pattern);

    result = struct( ...
        'ok', true, ...
        'model_name', model_name, ...
        'fast_restart', fast_restart, ...
        'cleared_sdi', false, ...
        'cleared_workspace_pattern', clear_workspace_pattern, ...
        'error_message', '');

    try
        load_system(model_name);
        if logical(clear_sdi)
            try
                Simulink.sdi.clear;
                result.cleared_sdi = true;
            catch
            end
        end
        if ~isempty(clear_workspace_pattern)
            evalin('base', sprintf('clearvars -regexp ''%s''', clear_workspace_pattern));
        end
        if ~isempty(fast_restart)
            set_param(model_name, 'FastRestart', fast_restart);
        end
    catch ME
        result.ok = false;
        result.error_message = char(ME.message);
    end
end
```

- [ ] **Step 6: Run static helper coverage**

Run:

```powershell
python -m pytest tests/test_mcp_tool_helper_coverage.py::test_all_slx_helpers_exist -q
```

Expected before MCP wrappers are added: `1 passed`, because no public wrapper
references these helpers yet.

- [ ] **Step 7: Commit**

```powershell
git add slx_helpers/slx_model_status.m slx_helpers/slx_save_model.m slx_helpers/slx_workspace_set.m slx_helpers/slx_run_window.m slx_helpers/slx_runtime_reset.m
git commit -m "feat: add general Simulink runtime primitives"
```

---

## Task 3: Expose General Runtime Primitives as MCP Tools

**Files:**
- Modify: `engine/mcp_simulink_tools.py`
- Modify: `engine/mcp_server.py`
- Modify: `tests/test_mcp_simulink_tools.py`
- Test: `tests/test_mcp_tool_helper_coverage.py`

- [ ] **Step 1: Add public wrappers to `engine/mcp_simulink_tools.py`**

Add wrappers with these signatures and behavior:

```python
def simulink_model_status(model_name: str) -> dict:
    """Return loaded/dirty/runtime status for one Simulink model."""
    session = MatlabSession.get()
    raw = session.call("slx_model_status", model_name, nargout=1)
    return _convert_element(raw)


def simulink_save_model(model_name: str, target_path: str = "") -> dict:
    """Save a Simulink model, optionally to a new target path."""
    session = MatlabSession.get()
    raw = session.call("slx_save_model", model_name, target_path, nargout=1)
    return _convert_element(raw)


def simulink_workspace_set(vars: dict[str, Any]) -> dict:
    """Set MATLAB base-workspace variables from a dict in one call."""
    session = MatlabSession.get()
    raw = session.call("slx_workspace_set", vars, nargout=1)
    return _convert_element(raw)


def simulink_run_window(
    model_name: str,
    start_time: float = 0.0,
    stop_time: float = 0.1,
    capture_errors: _BoolArg = True,
) -> dict:
    """Run a model over a controlled simulation window."""
    session = MatlabSession.get()
    raw = session.call(
        "slx_run_window",
        model_name,
        float(start_time),
        float(stop_time),
        bool(capture_errors),
        nargout=1,
    )
    return _convert_element(raw)


def simulink_runtime_reset(
    model_name: str,
    fast_restart: str = "",
    clear_sdi: _BoolArg = False,
    clear_workspace_pattern: str = "",
) -> dict:
    """Reset general Simulink runtime state without VSG semantics."""
    session = MatlabSession.get()
    raw = session.call(
        "slx_runtime_reset",
        model_name,
        fast_restart,
        bool(clear_sdi),
        clear_workspace_pattern,
        nargout=1,
    )
    return _convert_element(raw)


def simulink_signal_snapshot(
    model_name: str,
    time_s: float,
    signals: list[Any],
    allow_partial: _BoolArg = False,
) -> dict:
    """Read logged, ToWorkspace, or temporary block-probe values at one time."""
    session = MatlabSession.get()
    raw = session.call(
        "slx_signal_snapshot",
        model_name,
        float(time_s),
        signals,
        bool(allow_partial),
        nargout=1,
    )
    return _convert_element(raw)
```

Use the existing `_BoolArg`, `Any`, `MatlabSession`, and `_convert_element`
patterns already present in `engine/mcp_simulink_tools.py`.

- [ ] **Step 2: Register tools in `engine/mcp_server.py`**

Import and add the new tools in the public Simulink section:

```python
simulink_model_status,
simulink_save_model,
simulink_workspace_set,
simulink_run_window,
simulink_runtime_reset,
simulink_signal_snapshot,
```

Place them near related groups:

- `simulink_model_status` near lifecycle/discover tools
- `simulink_save_model` near lifecycle tools
- `simulink_workspace_set`, `simulink_run_window`, `simulink_runtime_reset`,
  and `simulink_signal_snapshot` near diagnostics/runtime tools

Update the server instruction string to mention:

```text
Use simulink_model_status before saving or closing a model when dirty state matters.
Use simulink_signal_snapshot for logged/ToWorkspace/block-output values at one time point.
Use simulink_workspace_set and simulink_run_window for general runtime control.
```

- [ ] **Step 3: Add mocked Python wrapper tests**

In `tests/test_mcp_simulink_tools.py`, add tests that patch
`MatlabSession.get()` and assert the wrappers call the correct helper names:

```python
def test_simulink_model_status_calls_helper(monkeypatch):
    mock_session = MagicMock()
    mock_session.call.return_value = {"ok": True, "loaded": True}
    monkeypatch.setattr(mcp_tools.MatlabSession, "get", lambda: mock_session)

    result = mcp_tools.simulink_model_status("demo")

    mock_session.call.assert_called_once_with("slx_model_status", "demo", nargout=1)
    assert result["ok"] is True
    assert result["loaded"] is True
```

Repeat the same pattern for:

- `simulink_save_model`
- `simulink_workspace_set`
- `simulink_run_window`
- `simulink_runtime_reset`
- `simulink_signal_snapshot`

- [ ] **Step 4: Run wrapper and static coverage tests**

Run:

```powershell
python -m pytest tests/test_mcp_simulink_tools.py tests/test_mcp_tool_helper_coverage.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```powershell
git add engine/mcp_simulink_tools.py engine/mcp_server.py tests/test_mcp_simulink_tools.py
git commit -m "feat: expose general Simulink runtime MCP tools"
```

---

## Task 4: Add MATLAB Smoke Tests for General Runtime Tools

**Files:**
- Create: `tests/test_simulink_general_runtime.py`

- [ ] **Step 1: Create a MATLAB-marked smoke test file**

Create `tests/test_simulink_general_runtime.py`:

```python
from pathlib import Path

import pytest


pytestmark = pytest.mark.matlab


def _session():
    from engine.matlab_session import MatlabSession

    return MatlabSession.get()


def test_model_status_reports_unloaded_model():
    session = _session()
    result = session.call("slx_model_status", "model_that_does_not_exist_123", nargout=1)
    assert isinstance(result, dict)
    assert "ok" in result
    assert "loaded" in result


def test_workspace_set_returns_written_names():
    session = _session()
    result = session.call("slx_workspace_set", {"slx_test_var": 42.0}, nargout=1)
    assert bool(result["ok"])
    assert "slx_test_var" in list(result["vars_written"])


def test_runtime_helpers_on_new_minimal_model(tmp_path):
    session = _session()
    model_name = "slx_general_runtime_smoke"
    target_path = tmp_path / f"{model_name}.slx"
    session.call("slx_create_model", model_name, False, nargout=1)
    try:
        status = session.call("slx_model_status", model_name, nargout=1)
        assert bool(status["ok"])
        assert bool(status["loaded"])

        reset = session.call("slx_runtime_reset", model_name, "off", True, "", nargout=1)
        assert bool(reset["ok"])

        run = session.call("slx_run_window", model_name, 0.0, 0.01, True, nargout=1)
        assert "ok" in run

        saved = session.call("slx_save_model", model_name, str(target_path), nargout=1)
        assert "ok" in saved
        assert Path(target_path).exists()
    finally:
        session.call("slx_close_model", model_name, False, nargout=0)
```

- [ ] **Step 2: Run the non-MATLAB tests first**

Run:

```powershell
python -m pytest tests/test_slx_helper_boundary.py tests/test_mcp_tool_helper_coverage.py tests/test_mcp_simulink_tools.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run MATLAB smoke when MATLAB is available**

Run:

```powershell
python -m pytest tests/test_simulink_general_runtime.py -q -m matlab
```

Expected: all selected MATLAB smoke tests pass.

- [ ] **Step 4: Commit**

```powershell
git add tests/test_simulink_general_runtime.py
git commit -m "test: cover general Simulink runtime helpers"
```

---

## Task 5: Update Skill Inventory and Routing

**Files:**
- Modify: `scripts/regen_skill_index.py`
- Modify: `C:\Users\27443\.codex\skills\simulink-toolbox\index.json`
- Modify: `C:\Users\27443\.claude\skills\simulink-toolbox\index.json`
- Modify: `C:\Users\27443\.codex\skills\simulink-toolbox\map.md`
- Modify: `C:\Users\27443\.claude\skills\simulink-toolbox\map.md`
- Modify: `C:\Users\27443\.codex\skills\simulink-toolbox\SKILL.md`
- Modify: `C:\Users\27443\.claude\skills\simulink-toolbox\SKILL.md`

- [ ] **Step 1: Update skill index metadata**

In `scripts/regen_skill_index.py`, add metadata entries:

```python
"simulink_model_status": {
    "group": "discover",
    "description": "Return loaded/dirty/runtime status for one model",
},
"simulink_save_model": {
    "group": "construct",
    "description": "Save a model, optionally to a target path",
},
"simulink_workspace_set": {
    "group": "workspace",
    "description": "Set MATLAB base-workspace variables in one call",
},
"simulink_run_window": {
    "group": "runtime",
    "description": "Run a model over a controlled simulation window",
},
"simulink_runtime_reset": {
    "group": "runtime",
    "description": "Reset FastRestart/runtime state without project semantics",
},
"simulink_signal_snapshot": {
    "group": "signals",
    "description": "Read logged/ToWorkspace/block-output values at one time point",
},
```

Replace `_get_skill_dir()` with multi-target skill directory resolution:

```python
def _get_skill_dirs() -> list[Path]:
    """Return target skill directories for both Codex and Claude installs."""
    env_multi = os.environ.get("SKILL_DIRS")
    if env_multi:
        return [
            Path(item).expanduser().resolve()
            for item in env_multi.split(os.pathsep)
            if item.strip()
        ]

    env_single = os.environ.get("SKILL_DIR")
    if env_single:
        return [Path(env_single).expanduser().resolve()]

    return [
        Path("~/.codex/skills/simulink-toolbox").expanduser().resolve(),
        Path("~/.claude/skills/simulink-toolbox").expanduser().resolve(),
    ]
```

Update `main()` so normal generation writes `index.json` to every directory
returned by `_get_skill_dirs()`, and `--check` verifies every returned directory.
The command must exit nonzero if any target skill index is missing or out of
sync.

- [ ] **Step 2: Regenerate the skill index**

Run:

```powershell
python scripts/regen_skill_index.py
```

Expected: output points to `C:\Users\27443\.codex\skills\simulink-toolbox\index.json`
and `C:\Users\27443\.claude\skills\simulink-toolbox\index.json`, and reports
the updated tool count for both.

- [ ] **Step 3: Check the skill index**

Run:

```powershell
python scripts/regen_skill_index.py --check
```

Expected: both installed `index.json` files are consistent with `PUBLIC_TOOLS`.

- [ ] **Step 4: Update both `map.md` routing files**

Apply the same routing additions to:

- `C:\Users\27443\.codex\skills\simulink-toolbox\map.md`
- `C:\Users\27443\.claude\skills\simulink-toolbox\map.md`

Add sections named:

```markdown
## workspace - base workspace variables

- `simulink_workspace_set` - set base-workspace variables in one structured call.
  NOT: do not use this for block mask parameters; use `simulink_set_block_params`.

## runtime - controlled simulation execution

- `simulink_runtime_reset` - reset FastRestart/runtime state without project semantics.
- `simulink_run_window` - run a model over a StartTime/StopTime window.
  NOT: do not use these for VSG episode semantics; use project bridge entry points.

## signals - signal reads and snapshots

- `simulink_signal_snapshot` - read logged, ToWorkspace, or temporary block-output
  values at one time point.
  NOT: do not interpret VSG Pe/omega/delta here; interpretation belongs to adapters.

## save/status - model persistence

- `simulink_model_status` - inspect loaded, dirty, solver, StopTime, and FastRestart state.
- `simulink_save_model` - save the current model or save to a target path.
```

- [ ] **Step 5: Update both `SKILL.md` boundary notes**

Apply the boundary note to both entrypoint files:

- `C:\Users\27443\.codex\skills\simulink-toolbox\SKILL.md`
- `C:\Users\27443\.claude\skills\simulink-toolbox\SKILL.md`

Preserve their environment-specific hook paragraphs. Do not overwrite the
Claude file with the Codex file or the Codex file with the Claude file.

Add this boundary note:

```markdown
General Simulink tasks use `simulink_*` tools only. `harness_*`, `training_*`,
and VSG bridge helpers are project-specific. Do not route generic modeling,
signal, workspace, or runtime tasks through VSG bridge helpers.
```

- [ ] **Step 6: Commit repo generator changes**

The skill files under `C:\Users\27443\.codex\skills\simulink-toolbox` and
`C:\Users\27443\.claude\skills\simulink-toolbox` are local configuration files
outside this Git repository. Do not include them in the repo commit command.
Commit only the repo-owned generator change and mention the local skill file
updates in the commit body or handoff note.

```powershell
git add scripts/regen_skill_index.py
git commit -m "docs: route general Simulink runtime tools in skill"
```

---

## Task 6: Refactor VSG Bridge Helpers to Use General Primitives

**Files:**
- Modify: `slx_helpers/slx_warmup.m`
- Modify: `slx_helpers/slx_step_and_read.m`
- Modify: `engine/simulink_bridge.py`
- Test: `tests/test_simulink_bridge.py`
- Test: `tests/test_perf_warmup_fr.py`

- [ ] **Step 1: Preserve public helper signatures**

Keep these existing signatures unchanged:

```matlab
function [state, status] = slx_warmup(model_name, agent_ids_or_duration, sbase_va, cfg, init_params, do_recompile)
function [state, status] = slx_step_and_read(model_name, agent_ids, M_values, D_values, t_stop, sbase_va, cfg, Pe_prev, delta_prev_deg)
```

No Python caller should need to change in this task.

- [ ] **Step 2: Replace duplicated runtime reset logic in `slx_warmup.m`**

In the paths that currently call `set_param(model_name, 'FastRestart', ...)`,
`Simulink.sdi.clear`, and `clearvars -regexp`, call `slx_runtime_reset` instead.

Use these calls:

```matlab
slx_runtime_reset(model_name, 'off', true, '^(omega|delta|Vabc|Iabc)_ES\d+$');
slx_runtime_reset(model_name, 'on', false, '');
slx_runtime_reset(model_name, '', true, '^(omega|delta|Vabc|Iabc)_ES\d+$');
```

Preserve the existing `do_recompile` behavior:

- `do_recompile=true`: FastRestart off then on
- `do_recompile=false`: keep FastRestart on and clear accumulated runtime data

- [ ] **Step 3: Replace warmup workspace assignment with `slx_workspace_set`**

Build a scalar struct named `vars` and call:

```matlab
slx_workspace_set(vars);
```

The struct must contain the same variable names currently assigned manually:

- `M0_val_ES{idx}`
- `D0_val_ES{idx}`
- `phAng_ES{idx}`
- `Pe_ES{idx}`
- `wref_{idx}`

- [ ] **Step 4: Replace simple sim windows with `slx_run_window`**

Where `slx_warmup.m` runs a simple warmup using `set_param(..., 'StopTime', ...)`
followed by `sim(model_name)`, call:

```matlab
run_result = slx_run_window(model_name, 0.0, init_params.t_warmup, true);
```

For the 2-arg and 3-arg legacy paths, use:

```matlab
run_result = slx_run_window(model_name, 0.0, duration, true);
```

If `run_result.ok` is false, preserve the existing error behavior for that path.

- [ ] **Step 5: Refactor only the runtime parts of `slx_step_and_read.m`**

Keep VSG state interpretation in `slx_step_and_read.m`. Replace only:

- base-workspace assignment loop with `slx_workspace_set(vars)`
- `set_param(model_name, 'StopTime', ...)` plus `sim(model_name)` with
  `slx_run_window(model_name, 0.0, t_stop, true)`

Do not change:

- `step_phase_command_deg`
- `step_wrap_to_180`
- calls to `slx_extract_state`
- Pe scaling semantics
- `state.phAng_cmd_deg`
- `status.measurement_failures`

- [ ] **Step 6: Run bridge unit tests**

Run:

```powershell
python -m pytest tests/test_simulink_bridge.py tests/test_perf_warmup_fr.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Run MCP wrapper tests**

Run:

```powershell
python -m pytest tests/test_mcp_simulink_tools.py tests/test_mcp_tool_helper_coverage.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit**

```powershell
git add slx_helpers/slx_warmup.m slx_helpers/slx_step_and_read.m engine/simulink_bridge.py tests/test_simulink_bridge.py tests/test_perf_warmup_fr.py
git commit -m "refactor: route VSG bridge through general Simulink primitives"
```

---

## Task 7: Run Project-Specific Regression Gates

**Files:**
- Run only; no file edits expected

- [ ] **Step 1: Run non-MATLAB static/unit tests**

Run:

```powershell
python -m pytest tests/test_slx_helper_boundary.py tests/test_mcp_tool_helper_coverage.py tests/test_mcp_simulink_tools.py tests/test_simulink_bridge.py tests/test_perf_warmup_fr.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run MATLAB general smoke tests**

Run:

```powershell
python -m pytest tests/test_simulink_general_runtime.py -q -m matlab
```

Expected: all selected MATLAB smoke tests pass.

- [ ] **Step 3: Run the active Simulink bridge smoke path**

Use the existing project MCP or harness route for active scenarios:

```text
1. harness_scenario_status(scenario_id="kundur")
2. harness_model_inspect(scenario_id="kundur")
3. harness_train_smoke_minimal(scenario_id="kundur")
4. harness_scenario_status(scenario_id="ne39")
5. harness_model_inspect(scenario_id="ne39")
6. harness_train_smoke_minimal(scenario_id="ne39")
```

Expected:

- scenario resolution succeeds for `kundur`
- scenario resolution succeeds for `ne39`
- model inspection returns no new helper-contract failure
- minimal smoke does not fail due to missing helper, wrong helper signature,
  or changed VSG state shape

- [ ] **Step 4: If smoke identifies a model-side physical fault**

Route back to Model Harness order:

```text
scenario_status -> model_inspect -> model_patch_verify -> model_diagnose -> model_report
```

Do not treat a physical/model semantic failure as a general MCP tooling failure
until the helper call signatures and return shapes are ruled out.

- [ ] **Step 5: Record the final regression evidence**

Create or update the relevant harness run record under:

```text
results/harness/<scenario_id>/<run_id>/
```

Use the existing harness artifact policy. Do not put harness output in
`results/sim_*`.

- [ ] **Step 6: Commit regression notes only if new durable evidence was created**

```powershell
git add results/harness docs/devlog
git commit -m "docs: record Simulink MCP generalization regression evidence"
```

Skip this commit when no durable harness/devlog artifact was created.

---

## Task 8: Remove or Reclassify Legacy Public Ambiguity

**Files:**
- Modify: `slx_helpers/README.md`
- Modify: `C:\Users\27443\.codex\skills\simulink-toolbox\map.md`
- Modify: `C:\Users\27443\.claude\skills\simulink-toolbox\map.md`
- Modify: `docs/decisions/2026-04-22-simulink-mcp-generalization-boundary.md`

- [ ] **Step 1: Confirm no general MCP route points to VSG helpers**

Run:

```powershell
Select-String -Path "engine\mcp_server.py","engine\mcp_simulink_tools.py","C:\Users\27443\.codex\skills\simulink-toolbox\map.md","C:\Users\27443\.claude\skills\simulink-toolbox\map.md" -Pattern "slx_warmup|slx_step_and_read|slx_extract_state|slx_build_bridge_config"
```

Expected:

- `engine/simulink_bridge.py` may still use these helpers.
- General `simulink_*` tool descriptions and skill generic routing do not route
  users to these helpers.

- [ ] **Step 2: Update helper README status**

In `slx_helpers/README.md`, mark the legacy adapters as:

```markdown
Status: retained for VSG bridge compatibility. New generic MCP tools must not
call these helpers directly.
```

- [ ] **Step 3: Update the boundary decision with final status**

After regression gates pass, change the decision status from:

```markdown
Accepted for planning. Implementation is pending.
```

to:

```markdown
Adopted. General MCP primitives are implemented; VSG helpers remain as project
adapter compatibility wrappers.
```

- [ ] **Step 4: Run final static checks**

Run:

```powershell
python -m pytest tests/test_slx_helper_boundary.py tests/test_mcp_tool_helper_coverage.py -q
python scripts/regen_skill_index.py --check
```

Expected: both commands pass.

- [ ] **Step 5: Commit repo docs**

The skill `map.md` files are outside this Git repository. Do not add their
absolute paths to the repo commit. Commit only repo-owned files and record the
local skill file changes in the handoff note.

```powershell
git add slx_helpers/README.md docs/decisions/2026-04-22-simulink-mcp-generalization-boundary.md
git commit -m "docs: finalize Simulink MCP generalization boundary"
```

---

## Verification Matrix

| Check | Command | Required before |
| --- | --- | --- |
| Static helper boundary | `python -m pytest tests/test_slx_helper_boundary.py -q` | Adding or changing any `slx_helpers/slx_*.m` file |
| Public helper coverage | `python -m pytest tests/test_mcp_tool_helper_coverage.py -q` | Registering public MCP tools |
| Python wrapper tests | `python -m pytest tests/test_mcp_simulink_tools.py -q` | Changing `engine/mcp_simulink_tools.py` |
| Bridge regression | `python -m pytest tests/test_simulink_bridge.py tests/test_perf_warmup_fr.py -q` | Refactoring VSG wrappers |
| MATLAB general smoke | `python -m pytest tests/test_simulink_general_runtime.py -q -m matlab` | Claiming runtime primitives work in MATLAB |
| Skill index consistency | `python scripts/regen_skill_index.py --check` | Changing `engine/mcp_server.py` or skill inventory |

## Rollback Plan

If the general primitives work but VSG bridge smoke fails:

1. Keep new primitives and public MCP tools.
2. Revert only the Task 6 changes to `slx_warmup.m`, `slx_step_and_read.m`, and
   bridge callers.
3. Keep `slx_helpers/README.md` classification in place.
4. Record the bridge failure under `docs/devlog/` with the exact failing command
   and helper call signature.

If a new public MCP tool contract is wrong:

1. Remove the tool from `PUBLIC_TOOLS`.
2. Regenerate `index.json`.
3. Keep the MATLAB helper private until its contract smoke passes.

## Acceptance Criteria

- New general public tools do not require VSG/RL vocabulary.
- Existing Kundur and NE39 bridge paths still call compatible helper signatures.
- `simulink-toolbox` routes general runtime, signal, workspace, and save/status
  tasks to public `simulink_*` tools.
- Static tests prevent accidental addition of new VSG-specific general helpers.
- MATLAB smoke proves the new general primitives can run on a minimal model.
- Project-specific smoke confirms no helper signature or state-shape regression
  in the active reproduction path.
