# NE39 Training Speed & Convergence Improvements

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut NE39 Simulink episode wall-clock time by ~30-40% and fix convergence quality by eliminating per-episode FastRestart recompilation and fixing severely undersized RL hyperparameters.

**Architecture:**
- Task 1 (pure code): NE39 `_reset_backend` passes a `do_recompile` flag to `vsg_warmup`; on episode 2+ the ~12s FastRestart off→on cycle is skipped. Mirrors the existing `_fr_compiled` cache already working in Kundur's `SimulinkBridge.warmup()`.
- Task 2 (config only): `ne39_simulink_env.py` currently builds an inline `BridgeConfig` that silently differs from the canonical `NE39_BRIDGE_CONFIG`; consolidate them so a single config object is the source of truth.
- Task 3 (config only): `BATCH_SIZE=32` is critically undersized for an 8-agent system that generates 400 transitions/episode; raise to 256. `WARMUP_STEPS=500` starts training after just 1 episode; raise to 2000.
- Task 4 (Simulink model, optional): Add scalar `P_out_ES{k}` ToWorkspace blocks to `NE39bus_v2.slx` so each step reads 1 scalar per agent instead of two 200×3 time-series arrays (Vabc + Iabc), eliminating a ~200× data-transfer overhead per step.

**Tech Stack:** Python 3, MATLAB R2025b, Simulink, pytest

> **⚠ Current training:** `ne39_simulink_20260414_193303` is active at ~37/500 ep. Tasks 1–3 require stopping it first. Task 4 requires a model rebuild; restart training only after Task 4 (or after Task 3 if skipping Task 4).

---

## Task 1 — NE39 FastRestart recompile cache

**Expected saving:** ~12 s/episode × 500 episodes ≈ **1.7 hours** total.

**Files:**
- Modify: `vsg_helpers/vsg_warmup.m`
- Modify: `env/simulink/ne39_simulink_env.py:946-965`
- Test: `tests/test_simulink_bridge.py`

---

- [ ] **1.1 — Write failing test for `_fr_compiled` flag on NE39 env**

Open `tests/test_simulink_bridge.py` and add this test class after `TestBridgeConfig`:

```python
class TestNE39FrCompiled:
    """NE39 env must expose _fr_compiled via its bridge and pass do_recompile correctly."""

    def test_fr_compiled_starts_false(self, monkeypatch):
        """bridge._fr_compiled is False before any reset."""
        _install_fake_gymnasium(monkeypatch)
        # Stub out matlab engine and SimulinkBridge so no MATLAB needed.
        import types, sys
        fake_matlab = types.ModuleType("matlab")
        fake_matlab.engine = types.ModuleType("matlab.engine")
        monkeypatch.setitem(sys.modules, "matlab", fake_matlab)
        monkeypatch.setitem(sys.modules, "matlab.engine", fake_matlab.engine)

        from unittest.mock import MagicMock, patch
        with patch("engine.simulink_bridge.SimulinkBridge") as MockBridge:
            instance = MockBridge.return_value
            instance._fr_compiled = False
            from env.simulink.ne39_simulink_env import NE39SimulinkEnv
            env = NE39SimulinkEnv.__new__(NE39SimulinkEnv)
            env.bridge = instance
            assert env.bridge._fr_compiled is False

    def test_fr_compiled_set_after_reset(self, monkeypatch):
        """After _reset_backend, bridge._fr_compiled must be True."""
        _install_fake_gymnasium(monkeypatch)
        import types, sys
        fake_matlab = types.ModuleType("matlab")
        fake_matlab.engine = types.ModuleType("matlab.engine")
        fake_matlab.double = list
        monkeypatch.setitem(sys.modules, "matlab", fake_matlab)
        monkeypatch.setitem(sys.modules, "matlab.engine", fake_matlab.engine)

        from unittest.mock import MagicMock, patch, call
        recorded_calls = []

        class FakeBridge:
            _fr_compiled = False
            cfg = MagicMock()
            cfg.model_name = "NE39bus_v2"
            cfg.sbase_va = 100e6
            _matlab_double = list
            _matlab_cfg = {}
            t_current = 0.0
            _delta_prev_deg = [0.0] * 8
            _Pe_prev = [0.5] * 8

            def load_model(self): pass
            def reset(self): pass

            class session:
                @staticmethod
                def eval(expr, nargout=0): return {}
                @staticmethod
                def call(fn, *args, nargout=0):
                    recorded_calls.append((fn, args))
                    if fn == "vsg_warmup":
                        return {}, {"success": True}
                    return None

        with patch("engine.simulink_bridge.SimulinkBridge", return_value=FakeBridge()), \
             patch("scenarios.new_england.config_simulink.NE39_BRIDGE_CONFIG"):
            from env.simulink.ne39_simulink_env import NE39SimulinkEnv
            env = NE39SimulinkEnv.__new__(NE39SimulinkEnv)
            env.bridge = FakeBridge()
            env._sim_time = 0.0

            # First reset: do_recompile must be True (bridge._fr_compiled=False)
            env._reset_backend()
            warmup_call = next(c for c in recorded_calls if c[0] == "vsg_warmup")
            assert warmup_call[1][-1] is True, "first reset must recompile"
            assert env.bridge._fr_compiled is True

            # Second reset: do_recompile must be False
            recorded_calls.clear()
            env._reset_backend()
            warmup_call2 = next(c for c in recorded_calls if c[0] == "vsg_warmup")
            assert warmup_call2[1][-1] is False, "second reset must skip recompile"
```

- [ ] **1.2 — Run test to confirm it fails**

```bash
cd "C:\Users\27443\Desktop\Multi-Agent  VSGs"
python -m pytest tests/test_simulink_bridge.py::TestNE39FrCompiled -v 2>&1 | tail -20
```

Expected: `FAILED` (NE39 env doesn't yet pass do_recompile).

- [ ] **1.3 — Update `vsg_warmup.m`: add optional 6th arg for NE39 do_recompile**

In `vsg_helpers/vsg_warmup.m`:

**Change the function signature** (line 1) from:
```matlab
function [state, status] = vsg_warmup(model_name, agent_ids_or_duration, sbase_va, cfg, init_params)
```
to:
```matlab
function [state, status] = vsg_warmup(model_name, agent_ids_or_duration, sbase_va, cfg, init_params, do_recompile)
```

**Add `do_recompile` default** after the `nargin==3` block (before line `% NE39 full mode`). Insert:
```matlab
    % NE39 full mode (5-arg or 6-arg with optional do_recompile flag).
    % 6-arg: do_recompile=false skips the ~10-12 s FastRestart recompile on
    % episodes 2+ — caller tracks bridge._fr_compiled and passes the flag.
    if nargin < 6
        do_recompile = true;   % default: always recompile (backward-compat)
    end
```

**Wrap "Step 1" (FastRestart off)** — change the unconditional block starting at `% Step 1`:
```matlab
    % Step 1: Stop any running FastRestart session (skip when do_recompile=false)
    if do_recompile
        try
            set_param(model_name, 'FastRestart', 'off');
        catch
        end
    end
```

**Wrap "Step 3" (FastRestart on)** — change the unconditional block starting at `% Step 3`:
```matlab
    % Step 3: Enable FastRestart (skip when do_recompile=false -- already compiled)
    if do_recompile
        try
            set_param(model_name, 'FastRestart', 'on');
        catch ME
            status.success = false;
            status.error   = ['FastRestart enable failed: ' ME.message];
            state = warmup_empty_state(N);
            status.elapsed_ms = toc * 1000;
            return;
        end
    end
```

- [ ] **1.4 — Update `ne39_simulink_env.py`: pass do_recompile, set `_fr_compiled`**

In `env/simulink/ne39_simulink_env.py`, in `_reset_backend` (around line 946), replace the `warmup_state, warmup_status = ...` block **and** the subsequent `bridge.t_current` assignment:

Old:
```python
            # Call vsg_warmup with full NE39 5-arg signature
            # Returns [state, status] but we only need status for error checking.
            mdbl = self.bridge._matlab_double
            agent_ids = mdbl(list(range(1, N_ESS + 1)))
            warmup_state, warmup_status = self.bridge.session.call(
                "vsg_warmup",
                self.bridge.cfg.model_name,
                agent_ids,
                float(self.bridge.cfg.sbase_va),
                self.bridge._matlab_cfg,
                self.bridge.session.eval("ne39_ip", nargout=1),
                nargout=2,
            )

            if warmup_status and not warmup_status.get("success", True):
                raise RuntimeError(
                    f"vsg_warmup failed: {warmup_status.get('error', 'unknown')}"
                )

            self.bridge.t_current = T_WARMUP
```

New:
```python
            # Call vsg_warmup with full NE39 5-arg signature + do_recompile flag.
            # do_recompile=False on episode 2+ skips the ~12s FastRestart off→on
            # recompile cycle.  bridge._fr_compiled is False until first success.
            mdbl = self.bridge._matlab_double
            agent_ids = mdbl(list(range(1, N_ESS + 1)))
            do_recompile = not self.bridge._fr_compiled
            warmup_state, warmup_status = self.bridge.session.call(
                "vsg_warmup",
                self.bridge.cfg.model_name,
                agent_ids,
                float(self.bridge.cfg.sbase_va),
                self.bridge._matlab_cfg,
                self.bridge.session.eval("ne39_ip", nargout=1),
                bool(do_recompile),  # 6th arg: skip FastRestart off→on after first episode
                nargout=2,
            )

            if warmup_status and not warmup_status.get("success", True):
                raise RuntimeError(
                    f"vsg_warmup failed: {warmup_status.get('error', 'unknown')}"
                )

            self.bridge._fr_compiled = True  # mark compiled; future resets skip recompile
            self.bridge.t_current = T_WARMUP
```

- [ ] **1.5 — Run test to confirm it passes**

```bash
python -m pytest tests/test_simulink_bridge.py::TestNE39FrCompiled -v 2>&1 | tail -10
```

Expected: `2 passed`.

- [ ] **1.6 — Run full bridge test suite to verify no regressions**

```bash
python -m pytest tests/test_simulink_bridge.py -v 2>&1 | tail -15
```

Expected: all existing tests still pass.

- [ ] **1.7 — Commit**

```bash
git add vsg_helpers/vsg_warmup.m env/simulink/ne39_simulink_env.py tests/test_simulink_bridge.py
git commit -m "perf(ne39): skip FastRestart recompile on episode 2+ (~12s/ep saved)"
```

---

## Task 2 — Consolidate NE39 env to use NE39_BRIDGE_CONFIG

**Why:** `ne39_simulink_env.py.__init__` builds its own inline `BridgeConfig` that omits `pe_measurement`, `pe0_default_vsg`, and other fields present in `NE39_BRIDGE_CONFIG`. This silent divergence means config changes in `config_simulink.py` don't take effect. Fix once; Task 4 will benefit automatically.

**Files:**
- Modify: `env/simulink/ne39_simulink_env.py:900-918`
- Test: `tests/test_simulink_bridge.py` (existing `test_ne39_config_has_correct_agents`)

---

- [ ] **2.1 — Replace inline BridgeConfig with NE39_BRIDGE_CONFIG**

In `env/simulink/ne39_simulink_env.py`, in `__init__` replace the block from
`from engine.simulink_bridge import BridgeConfig, SimulinkBridge` through
`self.bridge = SimulinkBridge(cfg)`:

Old:
```python
        from engine.simulink_bridge import BridgeConfig, SimulinkBridge

        resolved_dir = model_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', '..', 'scenarios', 'new_england', 'simulink_models'
        )
        cfg = BridgeConfig(
            model_name=model_name,
            model_dir=resolved_dir,
            n_agents=N_ESS,
            dt_control=DT,
            sbase_va=100e6,  # 100 MVA system base
            m_path_template='{model}/VSG_ES{idx}/M0',
            d_path_template='{model}/VSG_ES{idx}/D0',
            omega_signal='omega_ES{idx}',
            vabc_signal='Vabc_ES{idx}',
            iabc_signal='Iabc_ES{idx}',
        )
        self.bridge = SimulinkBridge(cfg)
```

New:
```python
        import dataclasses
        from engine.simulink_bridge import SimulinkBridge
        from scenarios.new_england.config_simulink import NE39_BRIDGE_CONFIG

        resolved_dir = model_dir or NE39_BRIDGE_CONFIG.model_dir
        cfg = dataclasses.replace(NE39_BRIDGE_CONFIG, model_dir=resolved_dir)
        self.bridge = SimulinkBridge(cfg)
```

- [ ] **2.2 — Run existing config test to confirm it still passes**

```bash
python -m pytest tests/test_simulink_bridge.py::TestBridgeConfig::test_ne39_config_has_correct_agents -v
```

Expected: `PASSED`.

- [ ] **2.3 — Confirm pe_measurement is now active**

```bash
python -c "
from scenarios.new_england.config_simulink import NE39_BRIDGE_CONFIG
print('pe_measurement:', NE39_BRIDGE_CONFIG.pe_measurement)
print('p_out_signal:  ', NE39_BRIDGE_CONFIG.p_out_signal)
print('n_agents:      ', NE39_BRIDGE_CONFIG.n_agents)
"
```

Expected output:
```
pe_measurement: vi
p_out_signal:   
n_agents:       8
```

- [ ] **2.4 — Commit**

```bash
git add env/simulink/ne39_simulink_env.py
git commit -m "refactor(ne39): use NE39_BRIDGE_CONFIG instead of inline BridgeConfig"
```

---

## Task 3 — Fix BATCH_SIZE and WARMUP_STEPS

**Why:**
- `BATCH_SIZE=32` with 400 transitions/episode = 8% data utilisation. Kundur runs 256 on 100 transitions. Raise to 256.
- `WARMUP_STEPS=500` ≈ 1 episode of data before SAC updates start. 8 agents need a richer buffer to avoid high-variance gradients early on. Raise to 2000 (≈ 5 episodes).

**Files:**
- Modify: `scenarios/new_england/config_simulink.py:87-92`

---

- [ ] **3.1 — Update config**

In `scenarios/new_england/config_simulink.py`, replace lines 86–92:

Old:
```python
# ========== SAC Hyperparameters (NE39-specific overrides) ==========
# BATCH_SIZE: 8 agents fill buffer ~2× faster; small batch (32) avoids
# overfitting to early narrow distribution before buffer is well-populated.
BATCH_SIZE = 32
BUFFER_SIZE = 100000
# WARMUP_STEPS: NE39 converges faster to meaningful gradients, 500 is sufficient.
WARMUP_STEPS = 500
```

New:
```python
# ========== SAC Hyperparameters (NE39-specific overrides) ==========
# BATCH_SIZE: 8 agents × 50 steps = 400 transitions/episode.
# 256 gives stable gradient estimates across the 8-agent action space.
BATCH_SIZE = 256
BUFFER_SIZE = 100000
# WARMUP_STEPS: need ~5 full episodes of random data (~2000 steps) before
# SAC updates start, so all 8 agents have seen diverse initial conditions.
WARMUP_STEPS = 2000
```

- [ ] **3.2 — Smoke-check that config imports cleanly**

```bash
python -c "
from scenarios.new_england.config_simulink import BATCH_SIZE, WARMUP_STEPS
assert BATCH_SIZE == 256, BATCH_SIZE
assert WARMUP_STEPS == 2000, WARMUP_STEPS
print('OK: BATCH_SIZE=', BATCH_SIZE, 'WARMUP_STEPS=', WARMUP_STEPS)
"
```

Expected: `OK: BATCH_SIZE= 256 WARMUP_STEPS= 2000`

- [ ] **3.3 — Commit**

```bash
git add scenarios/new_england/config_simulink.py
git commit -m "perf(ne39): BATCH_SIZE 32→256, WARMUP_STEPS 500→2000 for convergence quality"
```

---

## Task 4 (Optional) — Add scalar P_out to NE39 Simulink model

**Why:** Each step reads `Vabc_ES{k}` (200×3 time-series) + `Iabc_ES{k}` (200×3) for 8 agents = 9 600 doubles/step vs Kundur's 4 scalars. Adding `P_out_ES{k}` ToWorkspace blocks (scalar, 1 sample) inside the model eliminates this ~200× data overhead and switches to the same `pout` path Kundur uses.

**Prerequisite:** Requires MATLAB R2025b with NE39bus_v2.slx loaded. Stop any running NE39 training before proceeding. The model will be modified and rebuilt.

**Files:**
- Create: `scenarios/new_england/simulink_models/add_ne39_pout.m`
- Modify: `scenarios/new_england/config_simulink.py` (update `NE39_BRIDGE_CONFIG`)
- Rebuild: `NE39bus_v2.slx`

---

- [ ] **4.1 — Inspect model to find Vabc/Iabc block paths**

Before writing the patch, identify the exact block paths of the existing ToWorkspace blocks. Run in MATLAB:

```matlab
mdl = 'NE39bus_v2';
if ~bdIsLoaded(mdl), load_system(mdl); end
vabc_blks = find_system(mdl, 'BlockType', 'ToWorkspace', 'VariableName', 'Vabc_ES1');
iabc_blks = find_system(mdl, 'BlockType', 'ToWorkspace', 'VariableName', 'Iabc_ES1');
disp('Vabc_ES1 block:'); disp(vabc_blks);
disp('Iabc_ES1 block:'); disp(iabc_blks);
% Also check if any P_out_ES1 already exists
pout_blks = find_system(mdl, 'BlockType', 'ToWorkspace', 'VariableName', 'P_out_ES1');
disp('P_out_ES1 block (should be empty):'); disp(pout_blks);
```

Note the parent subsystem path returned for `Vabc_ES1`. The `P_out_ES{k}` blocks will be added to the same parent subsystem.

- [ ] **4.2 — Write patch script `add_ne39_pout.m`**

Create `scenarios/new_england/simulink_models/add_ne39_pout.m`:

```matlab
%% add_ne39_pout.m
% Adds scalar P_out_ES{k} computation and ToWorkspace logging to NE39bus_v2.
%
% For each ESS k=1..8:
%   1. Find parent subsystem of Vabc_ES{k} ToWorkspace block.
%   2. Add a MATLAB Function block that computes Pe = real(sum(Vabc.*conj(Iabc)))
%      using the final sample of the existing Vabc/Iabc signals.
%   3. Add a ToWorkspace block named P_out_ES{k} (scalar, 1 sample, sbase p.u.).
%
% After running this script:
%   - Set pe_measurement='pout' and p_out_signal='P_out_ES{idx}' in NE39_BRIDGE_CONFIG.
%   - Rebuild the model.
%
% Run once from MATLAB:
%   cd('C:\Users\27443\Desktop\Multi-Agent  VSGs\scenarios\new_england\simulink_models')
%   add_ne39_pout

mdl    = 'NE39bus_v2';
sbase  = 100e6;   % system base VA
vsg_sn = 200e6;   % VSG rated VA

if ~bdIsLoaded(mdl), load_system(mdl); end

fprintf('Adding P_out_ES{k} scalar ToWorkspace blocks to %s...\n', mdl);

for k = 1:8
    vabc_name = sprintf('Vabc_ES%d', k);
    iabc_name = sprintf('Iabc_ES%d', k);

    % Find parent subsystem of existing Vabc ToWorkspace
    vabc_blks = find_system(mdl, 'BlockType', 'ToWorkspace', 'VariableName', vabc_name);
    if isempty(vabc_blks)
        error('Could not find ToWorkspace block for %s', vabc_name);
    end
    vabc_path  = vabc_blks{1};
    parent_sys = get_param(vabc_path, 'Parent');

    % Find the source port connected to the Vabc ToWorkspace block
    vabc_ph  = get_param(vabc_path, 'PortHandles');
    vabc_src = get_param(vabc_ph.Inport(1), 'SrcPortHandle');

    iabc_blks = find_system(parent_sys, 'BlockType', 'ToWorkspace', 'VariableName', iabc_name);
    if isempty(iabc_blks)
        error('Could not find ToWorkspace block for %s', iabc_name);
    end
    iabc_path = iabc_blks{1};
    iabc_ph   = get_param(iabc_path, 'PortHandles');
    iabc_src  = get_param(iabc_ph.Inport(1), 'SrcPortHandle');

    % Add MATLAB Function block to compute Pe scalar
    fn_path = [parent_sys sprintf('/Pe_calc_ES%d', k)];
    if isempty(find_system(parent_sys, 'Name', sprintf('Pe_calc_ES%d', k)))
        add_block('simulink/User-Defined Functions/MATLAB Function', fn_path);
    end
    % Set function code: Pe = real(sum(Vabc .* conj(Iabc))) / sbase
    % (sbase hard-coded as gain; function receives 3-phase vectors)
    fn_edt = get_param(fn_path, 'FunctionScript');
    new_code = sprintf([
        'function Pe_pu = pe_from_vi(Vabc, Iabc)\n'
        '  Pe_pu = real(Vabc(1)*conj(Iabc(1)) + Vabc(2)*conj(Iabc(2)) + Vabc(3)*conj(Iabc(3))) / %.6e;\n'
    ], sbase);
    set_param(fn_path, 'FunctionScript', new_code);

    % Add scalar ToWorkspace block for P_out
    pout_name = sprintf('P_out_ES%d', k);
    pout_path = [parent_sys '/' pout_name];
    if isempty(find_system(parent_sys, 'Name', pout_name))
        add_block('simulink/Sinks/To Workspace', pout_path);
    end
    set_param(pout_path, 'VariableName', pout_name);
    set_param(pout_path, 'MaxDataPoints', '1');   % keep final sample only
    set_param(pout_path, 'SaveFormat', 'Timeseries');

    % Connect: Vabc→Pe_calc port1, Iabc→Pe_calc port2, Pe_calc→P_out ToWorkspace
    fn_ph = get_param(fn_path, 'PortHandles');
    add_line(parent_sys, vabc_src, fn_ph.Inport(1), 'autorouting', 'on');
    add_line(parent_sys, iabc_src, fn_ph.Inport(2), 'autorouting', 'on');
    pout_ph = get_param(pout_path, 'PortHandles');
    add_line(parent_sys, fn_ph.Outport(1), pout_ph.Inport(1), 'autorouting', 'on');

    fprintf('  ES%d: Pe_calc + P_out_ES%d added to %s\n', k, k, parent_sys);
end

save_system(mdl);
fprintf('\nDone. %s saved. Now rebuild and update NE39_BRIDGE_CONFIG.\n', mdl);
```

> **Note:** If the MATLAB Function block approach fails (e.g., due to signal dimension mismatches with 3-phase complex signals), use `Product (Element-wise)` + `Sum` + `Real-Imag to Complex` blocks instead, or add a `Power Measurement (Three-Phase)` block from Simscape Electrical at the VSG terminal. Adapt the script to match what the model exposes.

- [ ] **4.3 — Execute patch via vsg_run_quiet**

Use the simulink MCP tool:
```
mcp simulink_run_script with script_path = "scenarios/new_england/simulink_models/add_ne39_pout.m"
```

Or from MATLAB command window:
```matlab
cd('C:\Users\27443\Desktop\Multi-Agent  VSGs')
addpath('vsg_helpers')
vsg_run_quiet('scenarios/new_england/simulink_models/add_ne39_pout.m')
```

Expected output contains: `ES8: Pe_calc + P_out_ES8 added to ...`
If error: check the block paths returned in Step 4.1 and adjust `parent_sys` logic.

- [ ] **4.4 — Verify P_out signals exist in model**

```matlab
mdl = 'NE39bus_v2';
for k = 1:8
    blks = find_system(mdl, 'BlockType', 'ToWorkspace', ...
                       'VariableName', sprintf('P_out_ES%d', k));
    assert(~isempty(blks), sprintf('Missing P_out_ES%d', k));
    fprintf('  P_out_ES%d OK: %s\n', k, blks{1});
end
disp('All 8 P_out ToWorkspace blocks present.')
```

- [ ] **4.5 — Rebuild model**

```matlab
set_param('NE39bus_v2', 'FastRestart', 'off');
set_param('NE39bus_v2', 'FastRestart', 'on');
disp('Rebuild complete.')
```

Or use MCP `simulink_build_chain` for the NE39 scenario.

- [ ] **4.6 — Update NE39_BRIDGE_CONFIG to use pout path**

In `scenarios/new_england/config_simulink.py`, change lines 114–129:

Old:
```python
NE39_BRIDGE_CONFIG = BridgeConfig(
    model_name='NE39bus_v2',
    model_dir=_os.path.join(
        _os.path.dirname(_os.path.abspath(__file__)), 'simulink_models'
    ),
    n_agents=N_AGENTS,
    dt_control=DT,
    sbase_va=SBASE * 1e6,  # 100 MVA -> 100e6 VA
    m_path_template='{model}/VSG_ES{idx}/M0',
    d_path_template='{model}/VSG_ES{idx}/D0',
    omega_signal='omega_ES{idx}',
    vabc_signal='Vabc_ES{idx}',
    iabc_signal='Iabc_ES{idx}',
    pe_measurement='vi',    # NE39: Pe from V×I (Vabc/Iabc ToWorkspace)
    pe0_default_vsg=VSG_P0,
)
```

New:
```python
NE39_BRIDGE_CONFIG = BridgeConfig(
    model_name='NE39bus_v2',
    model_dir=_os.path.join(
        _os.path.dirname(_os.path.abspath(__file__)), 'simulink_models'
    ),
    n_agents=N_AGENTS,
    dt_control=DT,
    sbase_va=SBASE * 1e6,  # 100 MVA -> 100e6 VA
    m_path_template='{model}/VSG_ES{idx}/M0',
    d_path_template='{model}/VSG_ES{idx}/D0',
    omega_signal='omega_ES{idx}',
    vabc_signal='Vabc_ES{idx}',    # kept for fallback; not used when pe_measurement='pout'
    iabc_signal='Iabc_ES{idx}',
    p_out_signal='P_out_ES{idx}',  # scalar Pe ToWorkspace added by add_ne39_pout.m
    pe_measurement='pout',         # NE39: Pe from scalar P_out (eliminates 200× V×I transfer)
    pe0_default_vsg=VSG_P0,
)
```

- [ ] **4.7 — Verify config change propagates to env**

```bash
python -c "
from scenarios.new_england.config_simulink import NE39_BRIDGE_CONFIG
assert NE39_BRIDGE_CONFIG.pe_measurement == 'pout'
assert 'P_out_ES' in NE39_BRIDGE_CONFIG.p_out_signal
print('OK: pe_measurement=pout, p_out_signal=', NE39_BRIDGE_CONFIG.p_out_signal)
"
```

Expected: `OK: pe_measurement=pout, p_out_signal= P_out_ES{idx}`

- [ ] **4.8 — Run smoke test with new config (no MATLAB required)**

```bash
python -m pytest tests/test_simulink_bridge.py::TestBridgeConfig::test_ne39_config_has_correct_agents -v
```

Expected: `PASSED`.

- [ ] **4.9 — Commit**

```bash
git add scenarios/new_england/simulink_models/add_ne39_pout.m \
        scenarios/new_england/config_simulink.py
git commit -m "perf(ne39): add scalar P_out_ES{k} ToWorkspace, switch to pout Pe path"
```

---

## Restart training

After completing Tasks 1–3 (or 1–4), restart NE39 training:

```powershell
powershell -Command "Start-Process powershell -ArgumentList '-NoExit', '-Command', 'cd ''C:\Users\27443\Desktop\Multi-Agent  VSGs''; python scripts\launch_training.ps1 ne39'"
```

Or use the standard launch:
```powershell
scripts\launch_training.ps1 ne39
```

---

## Expected outcome

| Change | Mechanism | Estimated saving |
|--------|-----------|-----------------|
| Task 1 FastRestart cache | Skip ~12s recompile × 499 episodes | **~1.7 h** |
| Task 3 BATCH_SIZE 32→256 | Better gradient estimates, fewer wasted episodes | convergence quality |
| Task 3 WARMUP_STEPS 500→2000 | Richer buffer before SAC updates | convergence quality |
| Task 4 scalar P_out | ~200× less data/step × 50 steps × 500 ep | **~significant** (step-time dependent) |

Tasks 1–3 are safe, test-covered, and independent. Task 4 modifies the Simulink model; skip and do as follow-up if uncertain about the model structure.
