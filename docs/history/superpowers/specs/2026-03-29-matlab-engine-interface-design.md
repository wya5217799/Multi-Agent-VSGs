# MATLAB Engine Python Interface — Three-Layer Architecture Design

**Date:** 2026-03-29
**Scope:** sim_kundur + sim_ne39 (Simulink backends)
**Goal:** Unified MATLAB Engine interface for RL training co-simulation AND Claude AI perception of Simulink models

---

## Problem Statement

The current Simulink integration has five critical gaps:

1. **Segmented simulation not implemented** — `simulink_vsg_env.py:267` has a TODO; parameters set mid-episode have no effect
2. **Excessive cross-process overhead** — 16+ `eng.eval()` calls per control step (Kundur 4-agent); each is 10-50ms
3. **No model perception for Claude** — AI assistant cannot inspect block structure, trace signals, or validate models
4. **Fragile connection management** — each environment class manages its own MATLAB Engine lifecycle independently
5. **String-based API calls** — `eng.eval(f"set_param('{mdl}/VSG_ES{i}/M0', 'Value', '{val}')")` — no type safety, errors buried

**Ultimate objective:** Fully automated RL training loop where Claude can build, inspect, validate, and train on Simulink models end-to-end.

---

## Architecture: Three Layers

```
┌──────────────────────────────────────────────────────────┐
│  Layer 3: Consumers                                       │
│  ┌───────────────────┐  ┌─────────────────────────────┐  │
│  │ SimulinkBridge     │  │ MCP Simulink Tools          │  │
│  │ (RL env.step())    │  │ (Claude perception)         │  │
│  └────────┬──────────┘  └──────────────┬──────────────┘  │
├───────────┼─────────────────────────────┼────────────────┤
│  Layer 2: MATLAB-side Helpers (vsg_helpers/*.m)           │
│  ┌────────┴─────────────────────────────┴─────────────┐  │
│  │ vsg_step_and_read.m   (set params + sim + read)    │  │
│  │ vsg_inspect_model.m   (block tree + signals)       │  │
│  │ vsg_validate_model.m  (integrity check)            │  │
│  │ vsg_trace_signal.m    (source→sink path)           │  │
│  │ vsg_get_block_tree.m  (hierarchical structure)     │  │
│  └────────┬──────────────────────────────────────────┘  │
├───────────┼──────────────────────────────────────────────┤
│  Layer 1: MatlabSession (engine/matlab_session.py)        │
│  ┌────────┴──────────────────────────────────────────┐  │
│  │ - Lazy init + passive reconnect (no active ping)   │  │
│  │ - call(func, *args) preferred over eval(string)    │  │
│  │ - Auto addpath for vsg_helpers/                    │  │
│  │ - Structured error chain (MATLAB → Python)         │  │
│  │ - session_id for future multi-instance             │  │
│  └───────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

---

## Layer 1: MatlabSession

**File:** `engine/matlab_session.py`

### Responsibilities

- MATLAB Engine lifecycle management (start, reconnect, close)
- Unified `call(func_name, *args)` entry point
- Automatic `addpath` for `vsg_helpers/` on first connect
- Structured error handling: `MatlabExecutionError` → `MatlabCallError` with function name, args, original message
- Logging: every `call()` logs function name + elapsed time at DEBUG level

### Key Design Decisions

**Passive reconnect, not active health check.**
`ensure_connected()` does NOT call `eval("1;")` to test liveness. Instead, `call()` catches communication exceptions and triggers reconnect only on failure. This eliminates one IPC round-trip per step on the normal path.

```python
def call(self, func_name, *args, nargout=1):
    eng = self._get_engine()  # returns cached engine, no health check
    try:
        return getattr(eng, func_name)(*args, nargout=nargout)
    except (matlab.engine.EngineError, matlab.engine.MatlabExecutionError) as e:
        if self._is_communication_error(e):
            self._eng = None  # force reconnect on next call
            eng = self._get_engine()
            return getattr(eng, func_name)(*args, nargout=nargout)
        raise MatlabCallError(func_name, args, str(e))
```

**Session ID for future multi-instance.**
Default behavior is singleton (`session_id="default"`). API accepts arbitrary session IDs for future parallel environments. No multi-instance logic implemented now — just a dict of sessions keyed by ID.

```python
_instances: dict[str, 'MatlabSession'] = {}

@classmethod
def get(cls, session_id: str = "default") -> 'MatlabSession':
    if session_id not in cls._instances:
        cls._instances[session_id] = cls()
    return cls._instances[session_id]
```

**Auto addpath.**
On first successful connection, adds `<project_root>/vsg_helpers/` to MATLAB path. This is idempotent — calling `addpath` on an already-added path is a no-op in MATLAB.

### Public API

| Method | Description |
|--------|-------------|
| `get(session_id="default")` | Get or create session instance |
| `call(func, *args, nargout=1)` | Call MATLAB function (preferred) |
| `eval(code, nargout=0)` | Execute MATLAB string (escape hatch) |
| `close()` | Quit MATLAB engine, remove from instances |
| `engine` (property) | Direct engine access (for interop with existing MCP tools) |

---

## Layer 2: MATLAB-side Helpers

**Directory:** `vsg_helpers/` (project root)

### Core Principle

Each `.m` function does a **batch of related operations** inside a single MATLAB process call, eliminating per-agent cross-process overhead. All functions return MATLAB structs that serialize efficiently across the Engine API.

### 2.1 `vsg_step_and_read.m` — The Main Training Workhorse

**Purpose:** One call per control step — set parameters, run simulation segment, read state, return compact result.

```matlab
function [state, xFinal, status] = vsg_step_and_read( ...
    model_name, agent_ids, M_values, D_values, ...
    t_start, t_stop, xPrev, sbase_va, cfg)
%VSG_STEP_AND_READ  Set params + simulate + read state in one call.
%
%   cfg struct fields:
%     cfg.m_path_template  - e.g. '{model}/VSG_ES{idx}/M0'
%     cfg.d_path_template  - e.g. '{model}/VSG_ES{idx}/D0'
%     cfg.omega_signal     - e.g. 'omega_ES{idx}'
%     cfg.vabc_signal      - e.g. 'Vabc_ES{idx}'
%     cfg.iabc_signal      - e.g. 'Iabc_ES{idx}'
%
%   Returns:
%     state.omega(N)  - per-agent frequency (p.u.)
%     state.Pe(N)     - per-agent electrical power (p.u.)
%     state.rocof(N)  - per-agent ROCOF
%     xFinal          - simulation final state for next step
%     status.success  - boolean
%     status.error    - error message (empty if success)
%     status.elapsed_ms - wall-clock time

    status.success = true;
    status.error = '';
    tic;
    N = length(agent_ids);

    % --- Phase 1: Batch set parameters ---
    for i = 1:N
        idx = agent_ids(i);
        m_path = strrep(strrep(cfg.m_path_template, '{model}', model_name), '{idx}', num2str(idx));
        d_path = strrep(strrep(cfg.d_path_template, '{model}', model_name), '{idx}', num2str(idx));
        set_param(m_path, 'Value', num2str(M_values(i), '%.6f'));
        set_param(d_path, 'Value', num2str(D_values(i), '%.6f'));
    end

    % --- Phase 2: Segmented simulation ---
    set_param(model_name, 'StartTime', num2str(t_start, '%.6f'));
    set_param(model_name, 'StopTime',  num2str(t_stop,  '%.6f'));

    if ~isempty(xPrev)
        set_param(model_name, 'LoadInitialState', 'on');
        set_param(model_name, 'InitialState', 'xPrev');
        assignin('base', 'xPrev', xPrev);
    else
        set_param(model_name, 'LoadInitialState', 'off');
    end

    set_param(model_name, 'SaveFinalState', 'on');
    set_param(model_name, 'FinalStateName', 'xFinal');
    set_param(model_name, 'SaveCompleteSim', 'on');

    try
        simOut = sim(model_name);
    catch ME
        status.success = false;
        status.error = ME.message;
        state = struct('omega', zeros(1,N), 'Pe', zeros(1,N), 'rocof', zeros(1,N));
        xFinal = xPrev;
        status.elapsed_ms = toc * 1000;
        return;
    end

    xFinal = simOut.get('xFinal');

    % --- Phase 3: Extract compact state (stays in MATLAB, no cross-process) ---
    state.omega = zeros(1, N);
    state.Pe    = zeros(1, N);
    state.rocof = zeros(1, N);

    for i = 1:N
        idx = agent_ids(i);
        omega_name = strrep(cfg.omega_signal, '{idx}', num2str(idx));
        vabc_name  = strrep(cfg.vabc_signal,  '{idx}', num2str(idx));
        iabc_name  = strrep(cfg.iabc_signal,  '{idx}', num2str(idx));

        omega_ts = simOut.get(omega_name);
        state.omega(i) = omega_ts.Data(end);

        Vabc = simOut.get(vabc_name);
        Iabc = simOut.get(iabc_name);
        state.Pe(i) = real(sum(Vabc.Data(end,:) .* conj(Iabc.Data(end,:)))) / sbase_va;

        if length(omega_ts.Data) >= 2
            dt = omega_ts.Time(end) - omega_ts.Time(end-1);
            state.rocof(i) = (omega_ts.Data(end) - omega_ts.Data(end-1)) / dt;
        end
    end

    status.elapsed_ms = toc * 1000;
end
```

**Performance impact:** Kundur 4-agent goes from 16+ IPC calls/step to **1**. NE39 8-agent goes from 24+ to **1**.

### 2.2 `vsg_inspect_model.m` — Model Structure for Claude

```matlab
function info = vsg_inspect_model(model_name, depth)
%VSG_INSPECT_MODEL  Return complete model structure as a serializable struct.
%   info.block_count  - total blocks found
%   info.blocks{}     - cell array of {path, type, name, key_params}
%   info.signal_count - total signal lines
%   info.subsystems{} - subsystem hierarchy

    if nargin < 2, depth = 3; end
    load_system(model_name);

    blocks = find_system(model_name, 'SearchDepth', depth);
    info.block_count = length(blocks);
    info.blocks = cell(length(blocks), 1);

    for i = 1:length(blocks)
        b.path = blocks{i};
        b.type = get_param(blocks{i}, 'BlockType');
        b.name = get_param(blocks{i}, 'Name');
        try
            dp = get_param(blocks{i}, 'DialogParameters');
            fn = fieldnames(dp);
            b.key_params = struct();
            for j = 1:min(length(fn), 10)  % cap at 10 params to limit size
                b.key_params.(fn{j}) = get_param(blocks{i}, fn{j});
            end
        catch
            b.key_params = struct();
        end
        info.blocks{i} = b;
    end

    % Subsystem list
    subs = find_system(model_name, 'SearchDepth', depth, 'BlockType', 'SubSystem');
    info.subsystems = subs;

    % Signal lines (handles → struct)
    lines = find_system(model_name, 'FindAll', 'on', 'Type', 'line', 'SearchDepth', depth);
    info.signal_count = length(lines);
end
```

### 2.3 `vsg_validate_model.m` — Integrity Check

```matlab
function report = vsg_validate_model(model_name, expected_cfg)
%VSG_VALIDATE_MODEL  Check model against expected configuration.
%   expected_cfg.n_agents       - expected number of VSG subsystems
%   expected_cfg.subsys_pattern - e.g. 'VSG_ES' or 'VSG_W'
%   expected_cfg.required_blocks - cell array of block types that must exist
%
%   report.passed    - boolean
%   report.errors{}  - cell array of error descriptions
%   report.warnings{} - cell array of warnings

    load_system(model_name);
    report.passed = true;
    report.errors = {};
    report.warnings = {};

    % Check VSG subsystem count
    pattern = [model_name '/' expected_cfg.subsys_pattern '*'];
    vsg_subs = find_system(model_name, 'SearchDepth', 1, 'Name', [expected_cfg.subsys_pattern '*']);
    actual_count = length(vsg_subs);
    if actual_count ~= expected_cfg.n_agents
        report.passed = false;
        report.errors{end+1} = sprintf('Expected %d VSG subsystems, found %d', ...
            expected_cfg.n_agents, actual_count);
    end

    % Check required blocks exist
    for i = 1:length(expected_cfg.required_blocks)
        found = find_system(model_name, 'BlockType', expected_cfg.required_blocks{i});
        if isempty(found)
            report.passed = false;
            report.errors{end+1} = sprintf('Missing required block type: %s', ...
                expected_cfg.required_blocks{i});
        end
    end

    % Check solver settings
    solver = get_param(model_name, 'Solver');
    if ~strcmp(solver, 'ode23t') && ~strcmp(solver, 'ode15s')
        report.warnings{end+1} = sprintf('Solver is %s, expected ode23t or ode15s', solver);
    end
end
```

### 2.4 `vsg_trace_signal.m` — Signal Path Tracing

```matlab
function path = vsg_trace_signal(model_name, signal_name)
%VSG_TRACE_SIGNAL  Trace a signal from source to all sinks.
%   Returns a struct array with source block, intermediate blocks, and sink blocks.

    load_system(model_name);
    ph = find_system(model_name, 'FindAll', 'on', 'Type', 'port', 'Name', signal_name);
    path = struct('source', '', 'sinks', {{}}, 'through', {{}});

    if isempty(ph)
        path.source = 'NOT_FOUND';
        return;
    end

    % Get source
    line_h = get_param(ph(1), 'Line');
    if line_h > 0
        src_h = get_param(line_h, 'SrcBlockHandle');
        path.source = getfullname(src_h);

        dst_h = get_param(line_h, 'DstBlockHandle');
        for i = 1:length(dst_h)
            path.sinks{end+1} = getfullname(dst_h(i));
        end
    end
end
```

### 2.5 `vsg_get_block_tree.m` — Hierarchical View

```matlab
function tree = vsg_get_block_tree(model_name, root_path, max_depth)
%VSG_GET_BLOCK_TREE  Return hierarchical block structure as nested struct.
%   tree.name, tree.type, tree.children[]

    if nargin < 2, root_path = model_name; end
    if nargin < 3, max_depth = 3; end

    load_system(model_name);
    tree = build_tree(root_path, 0, max_depth);
end

function node = build_tree(path, current_depth, max_depth)
    node.name = get_param(path, 'Name');
    node.type = get_param(path, 'BlockType');
    node.path = path;
    node.children = {};

    if current_depth >= max_depth
        return;
    end

    if strcmp(node.type, 'SubSystem')
        children = find_system(path, 'SearchDepth', 1);
        children = children(2:end);  % exclude self
        for i = 1:length(children)
            node.children{end+1} = build_tree(children{i}, current_depth + 1, max_depth);
        end
    end
end
```

---

## Layer 3a: SimulinkBridge (Training Interface)

**File:** `engine/simulink_bridge.py`

### Design Rationale: Why Not simulink_gym?

[simulink_gym](https://github.com/johbrust/simulink_gym) (v0.6.1, Feb 2025) is the closest existing open-source solution — it wraps Simulink as a Gymnasium environment. We do not use it for three reasons:

1. **Communication overhead:** simulink_gym uses TCP/IP sockets between Python and MATLAB. Our `matlab.engine`-based approach is in-process, with no serialization or network layer.
2. **No batch operations:** simulink_gym has no mechanism for batching multi-agent parameter sets into a single call. Our `vsg_step_and_read.m` compresses N-agent ops to 1 IPC call.
3. **Extra dependency:** simulink_gym requires the Instrument Control Toolbox. `matlab.engine` is included with standard MATLAB.

### Responsibilities

- Wraps `vsg_step_and_read.m` into a clean `step()` API
- Manages simulation time and final state across steps
- Provides `reset()` / `step()` / `close()` lifecycle
- Handles numpy ↔ matlab.double conversion

### Configuration

Each scenario provides a `BridgeConfig` that parameterizes block paths:

```python
@dataclass
class BridgeConfig:
    model_name: str              # 'kundur_two_area' or 'NE39bus_v2'
    model_dir: str               # path to directory containing .slx
    n_agents: int                # 4 or 8
    dt_control: float            # 0.2s
    sbase_va: float              # 200e6
    m_path_template: str         # '{model}/VSG_ES{idx}/M0'
    d_path_template: str         # '{model}/VSG_ES{idx}/D0'
    omega_signal: str            # 'omega_ES{idx}'
    vabc_signal: str             # 'Vabc_ES{idx}'
    iabc_signal: str             # 'Iabc_ES{idx}'
```

Kundur and NE39 each define their own config in `scenarios/*/config_simulink.py`.

### Public API

```python
class SimulinkBridge:
    def __init__(self, config: BridgeConfig, session_id: str = "default"):
        self.session = MatlabSession.get(session_id)
        self.cfg = config
        self.t_current = 0.0
        self._xFinal = None
        self._matlab_cfg = None  # MATLAB struct built from BridgeConfig

    def load_model(self):
        """Load .slx model and build MATLAB-side config struct."""
        self.session.call('cd', self.cfg.model_dir, nargout=0)
        self.session.call('load_system', self.cfg.model_name, nargout=0)
        self._matlab_cfg = self._build_matlab_cfg()

    def step(self, M: np.ndarray, D: np.ndarray) -> dict:
        """One control step: set params → simulate → read state.

        Args:
            M: shape (n_agents,) — target inertia values
            D: shape (n_agents,) — target damping values

        Returns:
            {'omega': np.ndarray, 'Pe': np.ndarray, 'rocof': np.ndarray}

        Raises:
            SimulinkError if simulation diverges or fails.
        """
        t_start = self.t_current
        t_stop = self.t_current + self.cfg.dt_control
        agent_ids = matlab.double(list(range(1, self.cfg.n_agents + 1)))

        state, xFinal, status = self.session.call(
            'vsg_step_and_read',
            self.cfg.model_name, agent_ids,
            matlab.double(M.tolist()), matlab.double(D.tolist()),
            float(t_start), float(t_stop),
            self._xFinal if self._xFinal is not None else matlab.double([]),
            float(self.cfg.sbase_va),
            self._matlab_cfg,
            nargout=3
        )

        if not status['success']:
            raise SimulinkError(
                f"Simulation failed at t={t_start:.3f}: {status['error']}")

        self._xFinal = xFinal
        self.t_current = t_stop

        return {
            'omega': np.array(state['omega']).flatten(),
            'Pe':    np.array(state['Pe']).flatten(),
            'rocof': np.array(state['rocof']).flatten(),
        }

    def reset(self):
        """Reset simulation to t=0."""
        self.t_current = 0.0
        self._xFinal = None

    def close(self):
        """Close the Simulink model (keep MATLAB engine alive)."""
        try:
            self.session.call('close_system', self.cfg.model_name, nargout=0)
        except MatlabCallError:
            pass  # model may already be closed
```

### Integration with Existing Environments

`KundurSimulinkEnv._step_backend()` and `NE39BusSimulinkEnv._step_backend()` currently contain inline `eng.eval()` calls. After this refactor, they delegate to `SimulinkBridge.step()`:

```python
# env/simulink/kundur_simulink_env.py (modified)
class KundurSimulinkEnv(_KundurBaseEnv):
    def __init__(self, ...):
        self.bridge = SimulinkBridge(KUNDUR_BRIDGE_CONFIG)

    def _step_backend(self, M_target, D_target):
        state = self.bridge.step(M_target, D_target)
        return state['omega'], state['Pe'], state['rocof']
```

---

## Layer 3b: MCP Simulink Tools (Claude Perception)

**File:** `engine/mcp_simulink_tools.py`

These tools are registered as MCP endpoints, giving Claude direct Simulink model access during conversations.

### Tool Catalog

| Tool Name | Purpose | MATLAB Helper | Returns |
|-----------|---------|---------------|---------|
| `simulink_inspect_model` | Browse model structure (blocks, types, params) | `vsg_inspect_model.m` | Block tree with key parameters |
| `simulink_get_block_params` | Query all params of a specific block | Direct `get_param` via session | Parameter dict |
| `simulink_trace_signal` | Trace signal source → sinks | `vsg_trace_signal.m` | Path with block names |
| `simulink_validate_model` | Check model integrity against expected config | `vsg_validate_model.m` | Pass/fail report with errors |
| `simulink_get_block_tree` | Hierarchical view of subsystems | `vsg_get_block_tree.m` | Nested tree structure |
| `simulink_list_models` | List available .slx files in scenarios/ | `dir` via session | File list with paths |
| `simulink_read_state` | Read current simulation state (debug) | Direct `simOut` workspace read via session | omega/Pe/rocof arrays (requires active sim) |

### Shared Engine Connection

All MCP tools access MATLAB through `MatlabSession.get()`, sharing the same engine as active training:

```python
# engine/mcp_simulink_tools.py

def simulink_inspect_model(model_name: str, depth: int = 3) -> dict:
    """MCP tool: inspect Simulink model structure."""
    session = MatlabSession.get()
    info = session.call('vsg_inspect_model', model_name, float(depth))
    return {
        'block_count': int(info['block_count']),
        'blocks': _convert_blocks(info['blocks']),
        'signal_count': int(info['signal_count']),
        'subsystems': list(info['subsystems']),
    }

def simulink_validate_model(model_name: str, scenario: str) -> dict:
    """MCP tool: validate model against scenario config."""
    cfg = _load_expected_config(scenario)  # from config_simulink.py
    session = MatlabSession.get()
    report = session.call('vsg_validate_model', model_name, cfg)
    return {
        'passed': bool(report['passed']),
        'errors': list(report['errors']),
        'warnings': list(report['warnings']),
    }
```

### Relationship to Existing MATLAB MCP Tools

- `mcp__matlab__evaluate_matlab_code` — **kept as-is**, for ad-hoc MATLAB commands
- `mcp__matlab__run_matlab_file` — **kept as-is**, for running build scripts
- New `simulink_*` tools — **additive**, Simulink-specific high-level operations
- All share the same MATLAB engine via `MatlabSession.get().engine` property

---

## File Structure (New Files)

```
engine/                              # NEW directory
  __init__.py
  matlab_session.py                  # Layer 1: connection management
  simulink_bridge.py                 # Layer 3a: training co-sim interface
  mcp_simulink_tools.py              # Layer 3b: MCP tool implementations
  exceptions.py                      # MatlabCallError, SimulinkError

vsg_helpers/                         # NEW directory (MATLAB .m files)
  vsg_step_and_read.m                # Batch: set params + sim + read state
  vsg_inspect_model.m                # Model structure inspection
  vsg_validate_model.m               # Model integrity check
  vsg_trace_signal.m                 # Signal path tracing
  vsg_get_block_tree.m               # Hierarchical block view
```

## Modified Files

| File | Change |
|------|--------|
| `env/simulink/kundur_simulink_env.py` | `KundurSimulinkEnv` uses `SimulinkBridge` instead of inline `eng.eval()` |
| `env/simulink/ne39_simulink_env.py` | `NE39BusSimulinkEnv` uses `SimulinkBridge` instead of inline `eng.eval()` |
| `scenarios/kundur/config_simulink.py` | Add `KUNDUR_BRIDGE_CONFIG` with block path templates |
| `scenarios/new_england/config_simulink.py` | Add `NE39_BRIDGE_CONFIG` with block path templates |

## Deprecated Files

| File | Reason |
|------|--------|
| `env/simulink/simulink_vsg_env.py` | Replaced by `SimulinkBridge`; was already incomplete (TODO on line 267) |

---

## Performance Summary

| Metric | Before | After |
|--------|--------|-------|
| IPC calls per control step | 16+ (Kundur) / 24+ (NE39) | **1** |
| Segmented simulation | Not implemented | **Fully implemented** (SaveFinalState/LoadInitialState) |
| Claude model perception | None | **7 MCP tools** |
| Error handling | String-based, exceptions lost | **Structured exception chain** |
| Engine lifecycle | Per-environment, independent | **Singleton, shared, auto-reconnect** |
| Block path coupling | Hardcoded per model | **Template-based, config-driven** |

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| `SaveFinalState`/`LoadInitialState` may not work for all Simscape blocks | Test with both models early; fall back to `SimState` object if needed |
| MATLAB struct → Python dict conversion may lose type info | Explicit conversion functions in SimulinkBridge; unit tests for round-trip |
| MCP tools called during active training could interfere | Read-only MCP tools (`inspect`, `validate`, `trace`) are safe; `set_params` tool has explicit warning |
| Single MATLAB engine shared between training and MCP | Training holds priority; MCP tools queue behind training calls (future: separate session_id) |

---

## Out of Scope

- Multi-MATLAB-instance parallel training (API ready via session_id, implementation deferred)
- Automatic Simulink model building from Python (keep using existing `.m` build scripts)
- Real-time visualization of simulation state (use existing MATLAB scopes)
- Changes to ODE or ANDES backends (unaffected by this design)
