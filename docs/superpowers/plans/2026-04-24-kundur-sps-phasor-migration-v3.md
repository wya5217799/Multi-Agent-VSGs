# Kundur SPS Phasor Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前基于 `ee_lib` / Simscape 的 `kundur_vsg` 训练主线迁移为基于 `powergui + SPS + Phasor` 的可训练场景，消除 `warmup`、`delta0/Pe_prev` 初值拼补、`P_ref` 斜坡冲击、以及 `delta=-90°` 这类假阳性稳定判据。

**Architecture:** 采用“影子模型先行，再切主线”的迁移方式。先在 `scenarios/kundur/simulink_models/` 下构建 `kundur_vsg_sps.slx`，保留现有 Kundur 训练入口、Python bridge 和 harness 路径不变，只给它们增加一个临时的候选模型开关；等 `zero-action`、`train_smoke`、短训练三道 gate 都通过后，再把 `kundur_vsg_sps` 扶正为新的 `kundur_vsg` 主线。

**Tech Stack:** MATLAB/Simulink R2025b, `powerlib`, `powergui` Phasor mode, Python `engine/simulink_bridge.py`, repo MCP Simulink tools, harness outputs under `results/harness/`.

---

## Approach Choice

### Option A: In-place rewrite `kundur_vsg.slx`

优点：文件少，切换快。

缺点：会立刻破坏当前 `ScenarioContract -> harness_reference -> train_entry` 的稳定链路；任何中途失败都让训练、探针、harness 同时失效。

### Option B: Shadow model then cut over

优点：可以并行保留当前 `ee_lib` 主线，逐步验证 `SPS/Phasor` 版本；可以把失败定位到“模型层”而不是“训练层”；最符合当前仓库的 harness-first 和 paper-track guardrail。

缺点：短期内会维护两套模型文件和一小段桥接分支。

### Option C: 直接按 NE39 模式重搭 Kundur

优点：最统一，理论上复用最多。

缺点：Kundur 还有 `TripLoad`、三常规机、两风场、四 VSG 的特定拓扑，直接照搬 NE39 容易跳过 Kundur 现有语义。

**Recommendation:** 选择 Option B。先用 `kundur_vsg_sps.slx` 吃下结构性问题，再在 cutover 时把 contract 和默认桥接目标切过去。

---

## Current Evidence

- `scenarios/kundur/config_simulink.py` 当前仍显式依赖 `T_WARMUP = 3.0`、`delta0_deg`、`TripLoad*_P`、`pe_measurement='feedback'`。
- `env/simulink/kundur_simulink_env.py` 的 `_reset_backend()` 仍然执行 `load_model -> reset -> set_disturbance_load -> warmup(T_WARMUP)`。
- `engine/simulink_bridge.py` 的 `warmup()` 会显式种入 `_Pe_prev`、`_delta_prev_deg`、`tripload_state`、FastRestart 状态。
- `scenarios/kundur/simulink_models/build_powerlib_kundur.m` 虽名为 `powerlib`，但实际上仍是 `ee_lib`/`SolverConfig` 路线，并用 `PrefRamp_*` 和 `TripLoad` 工作区变量规避冷启动。
- `scenarios/kundur/NOTES.md` 已经确认：`ee_lib` 路线下的 `P_ref` ramp、`T_WARMUP` 覆盖、`IL_specify`、`delta0` 回写都只是补症状，不是解根因。
- `probes/kundur/probe_sps_minimal.m` 已经给出正确的最小验证方向：`powergui(Phasor)` + `Three-Phase Source(PhaseAngle=workspace)` + `V-I Measurement`，目标是在 `t=0` 直接得到接近额定的 `Pe`。
- `scenarios/new_england/config_simulink.py` 已经使用 `phase_command_mode='absolute_with_loadflow'`，这是 Kundur 迁移后应对齐的 bridge 语义模板。

---

## Non-Goals

- 不改 ODE 和 ANDES 主线。
- 不在迁移初期修改 `scenarios/contract.py` 的 `model_name='kundur_vsg'`。
- 不把 harness 报告混写进 `results/sim_kundur/`。
- 不新增“再一层 warmup 补丁”来维持 `ee_lib` 路线。

---

## MCP-First Tool Policy

### Discovery

Step 1: 建立当前模型基线  
  Tool: `simulink_loaded_models`, `simulink_load_model`, `simulink_get_block_tree`, `simulink_solver_audit`  
  Combine: `results/harness/<scenario>/<run_id>/model_inspect.json` 记录快照  
  Verify: `simulink_get_block_tree` 能看到 `SolverConfig`, `PrefRamp_*`, `DynLoad_Trip*`

Step 2: 查询目标库块和参数  
  Tool: `simulink_library_lookup`, `simulink_query_params`, `simulink_describe_block_ports`  
  Combine: 若工具抛 `Unknown exception`，立即退到 `simulink_run_script` 调 `get_param` / `find_system` 做一次性探针  
  Verify: 把确认过的库块路径和关键参数写回 build script 顶部常量

### Editing

Step 3: 模型增删改连线  
  Tool: `simulink_add_block`, `simulink_add_subsystem`, `simulink_connect_ports`, `simulink_set_block_params`, `simulink_delete_block`  
  Combine: 每做完一批结构修改就 `simulink_compile_diagnostics`  
  Verify: `simulink_get_block_tree` 与 `simulink_query_params` 回读

### Diagnosis

Step 4: 编译和短窗诊断  
  Tool: `simulink_compile_diagnostics`, `harness_model_diagnose`, `simulink_bridge_status`  
  Combine: `probes/kundur/*.m` 和 `validate_phase3_zero_action.py`  
  Verify: 模型编译通过，`zero-action` 不再需要物理 warmup 才稳定

### Fallback Rule

如果 `simulink_explore_block` / `simulink_query_params` / `simulink_library_lookup` 继续出现 `Unknown exception`：

- 不要盲猜 block path 和参数名。
- 用 `simulink_run_script` 执行 repo 内现成 probe 或小段 `get_param` 探针。
- 把失败本身写入 harness evidence，作为工具层风险，而不是沉默绕过。

---

## Acceptance Gates

### Gate G0: SPS feasibility

- `probe_sps_minimal.m` 证明 `powergui(Phasor)` 下，`PhaseAngle=workspace` 可以在 `t=0` 直接建立接近额定的 `Pe`。
- 通过标准：`t <= 1 ms` 时 `Pe / P_nominal` 进入 `[0.95, 1.05]`。

### Gate G1: Zero-action physical gate

- 运行 `probes/kundur/validate_phase3_zero_action.py` 或等价 probe。
- 通过标准：
  - 不再依赖“长 warmup 才稳定”。
  - `C1`/`C3`/`C4` 全 PASS。
  - 不接受“delta 贴着 -90° 但 drift 很小”的假稳定。

### Gate G2: Smoke bridge gate

- Model Harness 全绿后，执行 `train_smoke_*`。
- 通过标准：`train_smoke_start` / `train_smoke_poll` 给出 pass verdict，且桥接层没有额外 `Pe_prev`/`delta_prev_deg` 拼补逻辑。

### Gate G3: Short training gate

- `scenarios/kundur/train_simulink.py` 跑短训练。
- 通过标准：
  - episode 1 就能进入训练循环；
  - 不需要把 `T_WARMUP` 当作物理稳定手段；
  - 没有系统性 `omega_saturated`、`Pe=0` 连续失败、或 FastRestart reset 污染。

只有 G0-G3 全过，才能切主线。

---

## Task 1: Freeze Baseline And Evidence

**Files:**
- Read: `scenarios/kundur/config_simulink.py`
- Read: `env/simulink/kundur_simulink_env.py`
- Read: `engine/simulink_bridge.py`
- Read: `scenarios/kundur/simulink_models/build_powerlib_kundur.m`
- Write: `results/harness/kundur/<run_id>/manifest.json`
- Write: `results/harness/kundur/<run_id>/model_inspect.json`

- [ ] **Step 1: Create a migration run id**

Use: `20260424-<time>-kundur-sps-phasor-migration-baseline`

Expected: `results/harness/kundur/<run_id>/` exists with a manifest.

- [ ] **Step 2: Capture current model tree and solver state**

Tool: `simulink_load_model`, `simulink_get_block_tree`, `simulink_solver_audit`

Expected:
- root contains `SolverConfig`
- root contains `PrefRamp_*`
- root contains `DynLoad_Trip*`
- solver audit shows Simscape local solver path, not `powergui`

- [ ] **Step 3: Record structural pain points as explicit baseline findings**

Write into `summary.md`:
- `T_WARMUP` is compensating startup, not just resetting runtime state
- `delta0_deg` is required to seed integrator IC
- `TripLoad*_P` is part of startup/reset choreography
- `pe_measurement='feedback'` keeps Kundur on a separate bridge semantics path from NE39

- [ ] **Step 4: Do not change contract yet**

Verify that `scenarios/contract.py` remains unchanged and still points to `kundur_vsg`.

---

## Task 2: Prove The SPS/Phasor Direction On A Minimal Probe

**Files:**
- Read: `probes/kundur/probe_sps_minimal.m`
- Modify: `probes/kundur/probe_sps_minimal.m` if block paths or measurements need correction
- Write: `results/harness/kundur/<run_id>/attachments/probe_sps_minimal.txt`

- [ ] **Step 1: Validate `probe_sps_minimal.m` against installed SPS library**

Tool: `simulink_library_lookup` first, fallback `simulink_run_script`

Verify these blocks and parameter names:
- `powerlib/powergui`
- `powerlib/Electrical Sources/Three-Phase Source`
- `powerlib/Measurements/Three-Phase V-I Measurement`
- `powerlib/Elements/Three-Phase Parallel RLC Load`

- [ ] **Step 2: Run the probe with explicit MATLAB path setup**

Tool: `simulink_run_script`

Expected output:
- `RESULT: probe_sps_minimal PASS`
- or a concrete library/parameter mismatch that must be fixed before continuing

- [ ] **Step 3: Freeze the winning source pattern**

Document the exact source-side recipe to reuse:
- `powergui` in `Phasor`
- `Three-Phase Source`
- `PhaseAngle = workspace variable`
- source impedance set inside the source block
- `V-I Measurement` used for `Pe = V x I`

- [ ] **Step 4: Abort the migration if G0 fails**

If the minimal probe cannot reach correct `Pe` at `t=0`, stop. Do not start mass model surgery.

---

## Task 3: Build A Shadow SPS Model Skeleton

**Files:**
- Create: `scenarios/kundur/simulink_models/kundur_vsg_sps.slx`
- Modify: `scenarios/kundur/simulink_models/build_powerlib_kundur.m`
- Optional create: `scenarios/kundur/simulink_models/build_kundur_sps.m`

- [ ] **Step 1: Choose the builder shape**

Recommended:
- keep the old `build_powerlib_kundur.m` as historical ee_lib builder
- create a new `build_kundur_sps.m` that emits `kundur_vsg_sps.slx`

Reason: in-place rewrite destroys the fallback path too early.

- [ ] **Step 2: Create an empty SPS shadow model**

Tool: `simulink_run_script` or `simulink_add_block` sequence

Expected skeleton:
- model root exists
- `powergui` exists
- no `SolverConfig`
- no `ee_lib` block references

- [ ] **Step 3: Wire only the global solver layer**

Tool: `simulink_add_block`, `simulink_set_block_params`, `simulink_compile_diagnostics`

Verify:
- `powergui` is `Phasor`
- frequency is `50`
- model compile reaches “missing block / unconnected network” stage, not library-missing stage

- [ ] **Step 4: Save the shadow model without touching the contract**

Expected: `kundur_vsg_sps.slx` lives beside `kundur_vsg.slx`, while all runtime defaults still point to the old model.

---

## Task 4: Port The Electrical Layer From `ee_lib` To SPS

**Files:**
- Modify: `scenarios/kundur/simulink_models/build_kundur_sps.m`
- Read: `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m`
- Read: `scenarios/new_england/simulink_models/patch_ne39_faststart.m`

- [ ] **Step 1: Port source blocks first**

Port these families in order:
- `CVS_G*` / `CVS_ES*` -> `Three-Phase Source`
- wind farm source blocks -> SPS source equivalent

Tool: `simulink_add_block`, `simulink_set_block_params`, `simulink_connect_ports`

Verify: every source has explicit phase angle and internal impedance, not external RLC crutches for initialization.

- [ ] **Step 2: Port measurement blocks**

Target:
- `PeGain_*` feedback path becomes `V-I Measurement` + bridge-side `vi` computation for VSG
- keep `ToWorkspace` signals needed by Python until the bridge is fully switched

Tool: `simulink_add_block`, `simulink_connect_ports`, `simulink_query_params`

Verify: VSG electrical power can be reconstructed from V/I without `PeFb_*`.

- [ ] **Step 3: Port transmission lines and loads**

Target:
- line, load, disturbance bank all use SPS equivalents
- disturbance should remain amplitude-controlled, but no longer depend on Simscape warm-start behavior

Tool: `simulink_add_block`, `simulink_delete_block`, `simulink_connect_ports`

Verify: the root tree no longer contains `SimscapeBlock` network elements.

- [ ] **Step 4: Remove `PrefRamp_*`, `PrefSat_*`, and any startup-only crutches**

Reason: under phasor steady-state initialization, these are no longer allowed as stability compensation.

Verify:
- no `PrefRamp_*` blocks
- no “`P_ref` starts at 0 and ramps to nominal” comments remain in the new builder

- [ ] **Step 5: Compile after every structural batch**

Tool: `simulink_compile_diagnostics`

Expected: fix compile errors immediately; do not queue large unverified edits.

---

## Task 5: Rewire Kundur Bridge Semantics To Match The SPS Model

**Files:**
- Modify: `scenarios/kundur/config_simulink.py`
- Modify: `env/simulink/kundur_simulink_env.py`
- Optional modify: `engine/simulink_bridge.py` only if Kundur truly needs a missing generic capability

- [ ] **Step 1: Add a temporary shadow-model config path**

Recommendation:
- add `SIMULINK_MODEL_CANDIDATE = 'kundur_vsg_sps'`
- allow `KundurSimulinkEnv` to opt into the shadow model via arg or env var

This keeps harness/mainline untouched until cutover.

- [ ] **Step 2: Switch Kundur from `feedback` to `vi`**

In `KUNDUR_BRIDGE_CONFIG`:
- `pe_measurement='vi'`
- `phase_command_mode='absolute_with_loadflow'`
- `init_phang` fed by power-flow output

Expected: Kundur now uses the same bridge semantic family as NE39.

- [ ] **Step 3: Demote warmup from physics compensation to runtime reset**

Target state:
- `T_WARMUP` is at most a short technical reset window
- no logic depends on “wait for `P_ref` ramp to finish”

Verify:
- comments in `config_simulink.py` no longer justify warmup with ramp completion
- `_reset_backend()` no longer treats warmup as a physical settling stage

- [ ] **Step 4: Stop relying on integrator IC patching for stability**

Target state:
- `delta0_deg` is only a load-flow phase seed if still needed by the source block
- VSG `IntD` IC is no longer the place where the equilibrium is faked

Verify with probe or direct parameter readback.

---

## Task 6: Add Regression Gates For The New Structure

**Files:**
- Modify: `probes/kundur/validate_phase3_zero_action.py`
- Create: `probes/kundur/probe_warmup_trajectory.m`
- Modify: `tests/test_simulink_bridge.py`
- Modify: `scenarios/kundur/NOTES.md`

- [ ] **Step 1: Rewrite the zero-action probe around the new invariants**

Old invariant:
- “warmup long enough and drift small”

New invariant:
- “no structural warmup compensation is needed”
- “`Pe` is near nominal immediately”
- “no hidden clamp masquerades as stability”

- [ ] **Step 2: Add a dedicated warmup/reset probe**

`probe_warmup_trajectory.m` should answer:
- does episode 2 reset to the same post-reset state as episode 1
- is reset time now technical, not physical
- are `omega`, `Pe`, and source phase consistent without long settling

- [ ] **Step 3: Update bridge tests to reflect the new Kundur contract**

Must assert:
- Kundur uses `vi`
- Kundur no longer depends on `feedback`-only blocks
- build script uses `powergui`, not `SolverConfig`

- [ ] **Step 4: Record the migration rule in `scenarios/kundur/NOTES.md`**

Document:
- `ee_lib` route is historical only
- `SPS/Phasor` is the active path
- any future reintroduction of `PrefRamp` or long warmup is regression, not optimization

---

## Task 7: Run The Model Harness And Smoke Bridge On The Shadow Model

**Files:**
- Write: `results/harness/kundur/<run_id>/scenario_status.json`
- Write: `results/harness/kundur/<run_id>/model_inspect.json`
- Write: `results/harness/kundur/<run_id>/model_diagnose.json`
- Write: `results/harness/kundur/<run_id>/train_smoke.json`

- [ ] **Step 1: Run `scenario_status` and `model_inspect` for the candidate**

Use the shadow-model override path, but keep `scenario_id='kundur'`.

- [ ] **Step 2: Diagnose compile/runtime issues before any training**

Tool: `harness_model_diagnose`

Expected:
- no compile failure
- no first-step instability that disappears only after long warmup

- [ ] **Step 3: Only after harness is green, run `train_smoke_*`**

Expected:
- pass verdict
- no repeated FastRestart corruption
- no `Pe=0` tolerance trips caused by missing measurement chain

---

## Task 8: Short Training, Compare, Then Cut Over

**Files:**
- Modify: `scenarios/contract.py`
- Modify: `scenarios/kundur/harness_reference.json`
- Modify: `scenarios/kundur/config_simulink.py`
- Update: `docs/paper/experiment-index.md`

- [ ] **Step 1: Run a short training on the shadow model**

Command shape:

```bash
python scenarios/kundur/train_simulink.py --mode simulink --episodes 20
```

Expected:
- backend boot succeeds on episode 1
- no structural warmup failures
- episode loop progresses with the shadow model

- [ ] **Step 2: Compare the new run against the old failure modes**

Must explicitly answer:
- was `T_WARMUP` still needed for physics
- was `P_ref` ramp still present
- did any `delta=-90°` false stability reappear
- did `omega_saturated` become rare or disappear under zero action

- [ ] **Step 3: Perform cutover only after G0-G3 all pass**

Cutover sequence:
1. make `kundur_vsg_sps.slx` the default build artifact
2. rename/archive old `kundur_vsg.slx`
3. update `scenarios/contract.py` and `harness_reference.json`
4. refresh notes and paper experiment index

- [ ] **Step 4: Archive, do not delete, the old `ee_lib` builder**

Reason: it is evidence of the failed structural route and still useful for regression archaeology.

---

## Definition Of Done

- Kundur active training path is `powergui + SPS + Phasor`, not `ee_lib + SolverConfig`.
- `T_WARMUP` is no longer a physics crutch.
- `PrefRamp_*` and equivalent startup shock suppressors are gone from the active model.
- Kundur bridge semantics align with NE39 on `vi` and `absolute_with_loadflow`.
- `zero-action`, `train_smoke`, and short training all pass on the SPS model.
- `scenarios/contract.py` is updated only after the shadow model proves itself.

---

## Risks To Watch

- Tooling risk: in this session `simulink_get_block_tree` works, but some deeper discovery tools can return `Unknown exception`; the implementation must treat `simulink_run_script` as an explicit fallback, not a last-minute hack.
- Semantics risk: if only VSG sources move to SPS but conventional generators keep the old initialization semantics, startup shock may survive in a new form.
- Cutover risk: switching `model_name` too early will break harness and make regression isolation harder.

