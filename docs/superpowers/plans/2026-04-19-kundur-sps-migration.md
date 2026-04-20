# Kundur Simulink 从 ee_lib 迁移到 SPS (powerlib) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Kundur Simulink 模型的网络层从 Simscape Electrical (`ee_lib`) 改造为 Specialized Power Systems (`powerlib` + `powergui`)，根治 ee_lib Simscape 求解器无法接受 AC 相量初值导致的 warmup 发散链（T_ramp、IL_specify、vlf_ess、phAng 回写、T_WARMUP 延长 6 次治症状都失败）。保留所有信号域子系统、Python bridge、validate/train 链路。

**Architecture:** ~~Route A（首选）—— Continuous EMT~~  **→ Route B（已确认）—— `powergui` Phasor 模式**（Phase 0 勘察证实 NE39 实际用 Phasor，见下方勘察结论）。核心范式：`Three-Phase Source`（`PhaseAngle = phAng_ES{i}` workspace 变量）+ 内嵌阻抗；Phasor 求解器在 t=0 自动算稳态，**无需手动注入 IC**；Pe 通过 workspace 变量 `Pe_ES{i}` 在步间注入，与 NE39bus_v2 生产模型完全一致。

**Tech Stack:** MATLAB/Simulink R2025b `powerlib` + `powergui`；Python 3（validate probe + RL env 不动）；MCP simulink-tools。

## Supersedes

- [`C:\Users\27443\.claude\plans\federated-cuddling-pumpkin.md`](C:/Users/27443/.claude/plans/federated-cuddling-pumpkin.md) —— T_ramp A/B 修复方向放弃
- [`docs/superpowers/plans/2026-04-18-kundur-pe-contract-fix.md`](../2026-04-18-kundur-pe-contract-fix.md) Phase 5b B6 开始的分支

---

## 决策依据

### 为什么放弃当前 ee_lib 路线
6 轮"根因"6 轮证伪：`T_WARMUP→IntD 饱和→IL_specify→vlf_ess 过期→phAng 回写→T_ramp/τ 失配`。这些不是独立 bug，而是同一个结构性缺陷的不同投影：**ee_lib 的 Simscape 求解器是 DC 求解器，对 AC 电路只能冷启动（IL=0，VC=0），不接受相量初值**。每个 patch 推平一个突起，下一个在等。

### 为什么 SPS (powerlib) 可行
| 证据 | 位置 |
|---|---|
| NE39 现生产使用 powerlib | `scenarios/new_england/simulink_models/NE39bus_v2.slx` 的 `system_root.xml` 含 `powergui`、`powerlib_extras/Phasor` |
| NE39 build 脚本模板成熟 | `scenarios/new_england/matlab_scripts/connect_vsg_to_grid.m:69-127` |
| SPS Series RLC Branch 的 `InitialCurrents` 接受 AC 相量 | MathWorks 文档（Phasor/Discrete/Continuous 模式下支持） |

> **澄清**：仓库中 `kundur_two_area.slx.original`（3/25）和 `kundur_two_area.slx`（3/26）也是 **ee_lib**（各 36/38 处 `ee_lib` 引用，0 处 `powerlib`），不是老 SPS 版本。Kundur 从未有过 SPS 实现——这是**首次迁移**，不是"迁回"。脚本名 `build_powerlib_kundur.m` 中的 "powerlib" 只是命名遗留（原 plan [`docs/history/superpowers/plans/2026-03-30-kundur-vsg-topology-upgrade.md:53-54`](../history/superpowers/plans/2026-03-30-kundur-vsg-topology-upgrade.md) 声明要用 powerlib，但实施时偏离到 ee_lib）。

### ~~为什么选 Route A（EMT）~~ → 已作废：NE39 实际用 Phasor

Phase 0 勘察证伪了 Route A 的全部假设。见下方勘察结论。

---

## Phase 0 勘察结论（2026-04-19 MCP 实测）

> 以下结论均通过 `mcp__simulink-tools__simulink_run_script` + `simulink_explore_block` + `simulink_query_params` 实测 `NE39bus_v2.slx` 和 powerlib 获得。

### 0.1 NE39 powergui 参数（实测）

| 参数 | 值 | 含义 |
|---|---|---|
| `MaskType` | `PSB option menu block` | SPS 标准 powergui mask |
| **`SimulationMode`** | **`Phasor`** | ⚠ 不是 Continuous EMT，是 Phasor！|
| `frequency` | `60` | NE39 频率（Kundur 改 `50`）|
| `SolverType` | `Tustin` | Phasor 离散求解器 |
| `Pbase` | `100e6` | 功率基值 |

> **结论**：`add_block('powerlib/powergui',...)` 后应 `set_param([mdl '/powergui'],'SimulationMode','Phasor')` + `'frequency','50'`。注意参数名是 `SimulationMode`，**不是** `SimulationType`（后者不存在）。

### 0.2 Three-Phase Series RLC Branch mask params（实测）

实际 mask params：`BranchType, Resistance, Inductance, Capacitance, Measurements`

> **结论**：**没有 `SpecifyIC` / `IC` 参数**。计划原 Phase 5 的"向 RLC 支路注入 AC 相量 InitialCurrents"方案在 R2025b 下不存在。**Phase 5 完全作废**。Phasor 求解器在 t=0 自动从源相量算稳态，不需要手动 IC。

### 0.3 Three-Phase Programmable Voltage Source（实测）

- **`Inport count = 0`**：没有任何信号输入端口
- 参数中无 `Amplification` 字段
- `VariationEntity=None`（预定义变化，不是信号驱动）

> **结论**：Programmable VS **无法**被信号驱动相位。原计划 Phase 2/3 "delta → Amplification='Time-dependent' → Phase 输入" 方案失效。

### 0.4 NE39 实际 VSG 源架构（实测）

NE39bus_v2 中：
- **`VSrc_ES{i}`** = 链接自 `spsThreePhaseSourceLib/Three-Phase Source`（不是 Programmable VS）
  - `PhaseAngle = phAng_ES{i}`（**workspace 变量**，每步由 Python bridge 写入）
  - `SpecifyImpedance = on`，`Resistance = R_vsg`，`Inductance = L_vsg`（内嵌阻抗，**无需独立 RLC 支路**）
  - 物理端口：3 个 RConn（A/B/C 分离，每相一个端口）→ `Meas_ES{i}`
- **`Pe_{i}`** = Constant 块，值 = `Pe_ES{i}`（**workspace 变量**，每步由 Python bridge 写入）→ VSG_ES{i} Port 5
- **`Meas_ES{i}`** = V-I Measurement，仅用于记录 Vabc/Iabc，不向模型内回注 Pe
- **`VSG_ES{i}`** IntD `InitialCondition = 0`（每步从 0 积分，增量 delta 写到 Log_delta_ES{i}）

### 0.5 关键假设验证结论

| 假设 | 原计划 | 实测结果 |
|---|---|---|
| Route A Continuous EMT | 首选 | ❌ NE39 用 Phasor，Route B 是正确路线 |
| RLC Branch SpecifyIC AC 相量 | Phase 5 核心 | ❌ 参数不存在，Phase 5 作废 |
| Programmable VS 信号相位输入 | Phase 2/3 核心 | ❌ Inport=0，无信号输入 |
| Three-Phase Source PhaseAngle workspace | 原备选 | ✅ NE39 正是这样做的 |
| Phasor 自动 IC（无需手动注入） | 原未考虑 | ✅ Phasor 求解器自动从 phAng 算稳态 |
| Pe workspace 变量注入 | 原未考虑 | ✅ NE39 用 Pe_ES{i} workspace Constant |
| IntD IC = 0（增量步进） | 原以为 = delta0_rad | ✅ NE39 IntD IC = 0 |

### 0.6 修订后架构（取代原 Phase 2-5 设计）

**每个 Gen/VSG 源的新模式：**
```
Three-Phase Source
  PhaseAngle   = phAng_ES{i}   ← workspace var，Python bridge 每步更新
  SpecifyImpedance = on
  Resistance   = R_gen/R_vsg   ← 内嵌阻抗，无需独立 Zgen/Zess RLC 块
  Inductance   = L_gen/L_vsg
  RConn1/2/3   → Meas_ES{i} LConn1/2/3  ← 3 相独立端口，非 composite

Pe_{i} = Constant(Pe_ES{i})    ← workspace var，Python bridge 每步更新
VSG_ES{i} IntD IC = 0          ← 每步从 0 积分，Python 步间累加 phAng
```

**Python bridge 步进协议（补充）：**
```
# 每步开始前（Python side）
matlab.assignin('base', f'phAng_ES{i}', phAng_current[i])  # degrees
matlab.assignin('base', f'Pe_ES{i}', Pe_current[i])        # VSG-base pu

# 每步结束后
delta_inc = matlab.eval(f'delta_ES{i}.Data(end)')  # radians (IntD output)
phAng_current[i] += delta_inc * 180/pi              # 累加到绝对相角
Pe_current[i] = compute_pe(Vabc_log, Iabc_log, VSG_SN)  # from Meas log
```

**已有代码契合度：**
- `slx_warmup.m` 6-arg 版本已经有 `assignin('base','phAng_ES{i}', delta0_deg)` ✅
- `slx_step_and_read.m` 需新增 phAng 步进逻辑和 Pe 更新逻辑

### 0.7 新增必须解决的缺口（补充审核）

| 缺口 | 影响阶段 | 说明 |
|---|---|---|
| `do_wire_ee` → `do_wire_sps` | Phase 4 | ee_lib composite port（1线）→ SPS 3 分离端口（3线/连接） |
| Dynamic Load S2PS 层去除 | Phase 4 | SPS Dynamic Load 直接接 Simulink 信号，不需要 S2PS |
| `Three-Phase Parallel RLC Load` 参数名 | Phase 4 | 实测：`InductivePower`/`CapacitivePower`（非 `InductiveReactivePower`） |
| `Meas` 端口数 | Phase 2-3 | V-I Measurement：LConn 3个（A/B/C in），RConn 3个（A/B/C out），Outport 2个（Vabc信号,Iabc信号） |
| `Three-Phase Source` 端口 | Phase 2-3 | RConn 3个独立端口（非 composite），每相单独接线 |
| Pe workspace 步进逻辑 | bridge | 需修改 `slx_step_and_read.m` + kundur_simulink_env.py |

---

## 资产保留清单（迁移不触及）

| 资产 | 路径 |
|---|---|
| VSG/ConvGen swing-equation 子系统（Simulink 信号域） | `build_powerlib_kundur.m:366-478`（ConvGen）, `:678-990`（VSG） |
| ToWorkspace logger 接口 | `PeFb_ES{i}`, `omega_ES{i}`, `delta_ES{i}`, `P_out_ES{i}` |
| Python bridge + RL env + config | `engine/simulink_bridge.py`, `env/simulink/kundur_simulink_env.py`, `scenarios/kundur/config_simulink.py` |
| Warmup/step helpers | `slx_helpers/slx_warmup.m`, `slx_step_and_read.m` |
| 潮流计算 + IC JSON | `slx_helpers/compute_kundur_powerflow.m`, `scenarios/kundur/kundur_ic.json` |
| Phase 3 probe | `probes/kundur/validate_phase3_zero_action.py` |
| 测试套件 | `tests/test_simulink_bridge.py` 等 |

---

## 文件地图

| 文件 | 操作 | 阶段 |
|---|---|---|
| `probes/kundur/probe_sps_minimal.m` | **新建**（Phase 0 可行性） | 0 |
| `scenarios/kundur/simulink_models/build_powerlib_kundur.m` | **重写网络层**（保留子系统/参数） | 1-5 |
| `slx_helpers/compute_kundur_powerflow.m` | **可能扩展**（输出 AC 相量初流） | 4 |
| `scenarios/kundur/kundur_ic.json` | `calibration_status=pending_rebuild` | 1 |
| `scenarios/kundur/simulink_models/kundur_vsg.slx` | **重建产物**（build 脚本生成） | 5 |
| `probes/kundur/probe_warmup_trajectory.m` | **新建**（迁移后 warmup 轨迹对比） | 6 |
| `scenarios/kundur/NOTES.md` | **更新**（根因定稿 + SPS 注意事项） | 7 |
| `docs/superpowers/plans/2026-04-18-kundur-pe-contract-fix.md` | **更新**（标记 B6 路线终结） | 7 |

---

## Phase 0: 可行性勘察（0.5 天）

**目标**：用最小模型验证 3 条关键假设。任一失败 → 停止 Phase 1，回到架构讨论。

### Task 0.1: 解压并确认 NE39 SPS 配置

- [ ] **Step 1**：从 `scenarios/new_england/simulink_models/NE39bus_v2.slx` 读出 `powergui` 的 `SimulationType`（需要 MATLAB 开模型读）

```matlab
% 用 MCP simulink_run_script：
load_system('scenarios/new_england/simulink_models/NE39bus_v2');
pg = find_system('NE39bus_v2', 'BlockType', 'PowerGraphicalUserInterface');
sim_type = get_param(pg{1}, 'SimulationType');
fprintf('NE39 powergui SimulationType: %s\n', sim_type);
close_system('NE39bus_v2', 0);
```

- [ ] **Step 2**：记录结果（预期 `Continuous` 或 `Discrete`；若是 `Phasor` 则 NE39 其实用的是 Phasor，计划调整）

### Task 0.2: SPS 最小可行性探针

**Files:**
- Create: `probes/kundur/probe_sps_minimal.m`

**目的**：1 个 VSG + 1 个 SPS 源 + 1 个 RLC 支路 + 1 个负荷，验证：
- (A) `InitialCurrents` 能否接受 AC 相量使 t=0 Pe = Pe_nominal
- (B) 信号域 delta 通过 workspace 变量驱动 Programmable VS `PositiveSequence` 的 phase 字段

- [ ] **Step 1**：写探针脚本

```matlab
% probes/kundur/probe_sps_minimal.m
% 最小 SPS 可行性测试：
%   Programmable VS → Series RLC Branch (InitialCurrents=相量) → Three-Phase Parallel RLC Load
% 目标：t=0 Pe ≈ Pe_nominal，无 warmup 瞬态

mdl = 'probe_sps_minimal';
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
load_system('powerlib');

% --- powergui (Continuous EMT) ---
add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 80 60]);
set_param([mdl '/powergui'], 'SimulationType', 'Continuous');

% --- Parameters (single VSG, 100 MVA base, 230 kV, 50 Hz) ---
Vbase   = 230e3;   Sbase = 100e6;  fn = 50;
R_ohm   = 0.003 * Vbase^2/Sbase;                % 3.9744 Ω
L_H     = 0.15   * Vbase^2/Sbase / (2*pi*fn);   % 0.632 H (X/R=50)
Pload   = 200e6;   % 200 MW

% --- AC phasor initial current (complex) for Pe=200 MW at V=230 kV ---
% Assume Pe=Pe0, V=Vnom, unity PF. Per-phase current magnitude:
Iph_rms = Pload / (sqrt(3) * Vbase);     % phase-A RMS
delta0  = 0;   % degrees (reference)
Ia_phasor = Iph_rms * exp(1j * deg2rad(delta0));
Ib_phasor = Iph_rms * exp(1j * deg2rad(delta0 - 120));
Ic_phasor = Iph_rms * exp(1j * deg2rad(delta0 + 120));

% --- Source ---
add_block('powerlib/Electrical Sources/Three-Phase Programmable Voltage Source', ...
    [mdl '/Src'], 'Position', [150 100 210 180]);
set_param([mdl '/Src'], 'PositiveSequence', sprintf('[%g 0 %g]', Vbase, fn));
set_param([mdl '/Src'], 'InternalConnection', 'Yg');

% --- Series RLC Branch (transmission) with AC phasor InitialCurrents ---
add_block('powerlib/Elements/Three-Phase Series RLC Branch', ...
    [mdl '/Zline'], 'Position', [270 100 330 180]);
set_param([mdl '/Zline'], 'BranchType', 'RL');
set_param([mdl '/Zline'], 'Resistance', num2str(R_ohm));
set_param([mdl '/Zline'], 'Inductance', num2str(L_H));
set_param([mdl '/Zline'], 'SpecifyIC', 'on');   % key: accept AC phasor IC
set_param([mdl '/Zline'], 'IC', sprintf('[%g %g %g; %g %g %g]', ...
    real(Ia_phasor), real(Ib_phasor), real(Ic_phasor), ...
    imag(Ia_phasor), imag(Ib_phasor), imag(Ic_phasor)));

% --- Load ---
add_block('powerlib/Elements/Three-Phase Parallel RLC Load', ...
    [mdl '/Load'], 'Position', [390 100 450 180]);
set_param([mdl '/Load'], 'NominalVoltage', num2str(Vbase));
set_param([mdl '/Load'], 'NominalFrequency', num2str(fn));
set_param([mdl '/Load'], 'ActivePower', num2str(Pload));
set_param([mdl '/Load'], 'InductiveReactivePower', '0');
set_param([mdl '/Load'], 'CapacitiveReactivePower', '0');

% --- P/Q Measurement ---
add_block('powerlib/Measurements/Three-Phase Instantaneous Active & Reactive Power', ...
    [mdl '/PQ'], 'Position', [270 220 370 260]);

% --- V-I Measurement (for PQ input) ---
add_block('powerlib/Measurements/Three-Phase V-I Measurement', ...
    [mdl '/VI'], 'Position', [180 220 240 280]);
set_param([mdl '/VI'], 'VoltageMeasurement', 'phase-to-ground');
set_param([mdl '/VI'], 'CurrentMeasurement', 'yes');

% --- Connect electrical ports ---
add_line(mdl, 'Src/LConn1', 'Zline/LConn1', 'autorouting', 'smart');
add_line(mdl, 'Src/LConn2', 'Zline/LConn2', 'autorouting', 'smart');
add_line(mdl, 'Src/LConn3', 'Zline/LConn3', 'autorouting', 'smart');
add_line(mdl, 'Zline/RConn1', 'VI/LConn1', 'autorouting', 'smart');
add_line(mdl, 'Zline/RConn2', 'VI/LConn2', 'autorouting', 'smart');
add_line(mdl, 'Zline/RConn3', 'VI/LConn3', 'autorouting', 'smart');
add_line(mdl, 'VI/RConn1', 'Load/LConn1', 'autorouting', 'smart');
add_line(mdl, 'VI/RConn2', 'Load/LConn2', 'autorouting', 'smart');
add_line(mdl, 'VI/RConn3', 'Load/LConn3', 'autorouting', 'smart');
add_line(mdl, 'VI/1', 'PQ/1', 'autorouting', 'smart');   % Vabc
add_line(mdl, 'VI/2', 'PQ/2', 'autorouting', 'smart');   % Iabc

% --- Log PQ ---
add_block('simulink/Sinks/To Workspace', [mdl '/Log_P'], 'Position', [400 220 450 260]);
set_param([mdl '/Log_P'], 'VariableName', 'P_probe', 'SaveFormat', 'Timeseries');
add_line(mdl, 'PQ/1', 'Log_P/1', 'autorouting', 'smart');

% --- Run 0.1s sim ---
set_param(mdl, 'StopTime', '0.1');
fprintf('\nRunning SPS minimal probe (100 ms, Continuous EMT)...\n');
simOut = sim(mdl);
P_ts = simOut.get('P_probe');

% Snapshot Pe at t=1ms, 10ms, 50ms, 100ms
snap = [1e-3, 10e-3, 50e-3, 100e-3];
fprintf('\n=== Pe(t) vs Pe_nominal=200 MW ===\n');
for t = snap
    [~, k] = min(abs(P_ts.Time - t));
    fprintf('  t=%.3fs  Pe=%.3f MW  (ratio=%.3f)\n', ...
        P_ts.Time(k), P_ts.Data(k)/1e6, P_ts.Data(k)/Pload);
end

% Pass criterion: |Pe(t=10ms) - Pnominal| / Pnominal < 5%
ratio_10ms = P_ts.Data(find(P_ts.Time >= 10e-3, 1)) / Pload;
if abs(ratio_10ms - 1) < 0.05
    fprintf('\nRESULT: SPS InitialCurrents WORKS — Pe=%.1f%% of nominal at t=10ms\n', ...
        ratio_10ms*100);
    fprintf('RESULT: probe_sps_minimal PASS\n');
else
    fprintf('\nRESULT: SPS InitialCurrents FAILED — Pe=%.1f%% of nominal at t=10ms\n', ...
        ratio_10ms*100);
    fprintf('RESULT: probe_sps_minimal FAIL — 重新评估 Route B (Phasor)\n');
end

close_system(mdl, 0);
```

- [ ] **Step 2**：通过 MCP `simulink_run_script` 运行，读 `RESULT:` 行判断 PASS/FAIL

### Task 0.3: 决策门

- [ ] 若 0.1 显示 NE39 的 powergui 是 Continuous 且 0.2 PASS → **继续 Phase 1**
- [ ] 若 0.2 FAIL → 切换到 Route B（Phasor），重写 Phase 1 设计；暂停本计划提醒
- [ ] 若 0.1 显示 NE39 是 Phasor → Route A 其实是 Phasor 路线，调整 `SimulationType` 设置

---

## Phase 1: 参数层 & powergui 设置（0.5 天）

> ✅ **Phase 0 已完成**（2026-04-19 MCP 实测）：NE39 = Phasor，Route B 确认，架构方案已定。Phase 0 的两个 Task 改为"已勘察"状态，probe_sps_minimal.m 已创建但执行留待确认。

**目标**：在 `build_powerlib_kundur.m` 开头把 ee_lib 路径发现逻辑替换为 powerlib 加载；参数保持不变。

**Files:**
- Modify: `scenarios/kundur/simulink_models/build_powerlib_kundur.m:1-320`
- Modify: `scenarios/kundur/kundur_ic.json`

### Task 1.1: 头部注释 + 参数保留

- [ ] **Step 1**：改头注释（移除 "Uses powerlib blocks exclusively (not ee_lib)" 矛盾声明，改为 "Uses SPS powerlib blocks with powergui Continuous EMT; migrated from ee_lib 2026-04-19"）
- [ ] **Step 2**：**保留** line 86-277 的所有参数（gen_cfg, wind_cfg, line_defs, load_defs, shunt_defs, trip_defs, VSG_M0/D0/SN）——不动一个字
- [ ] **Step 3**：**保留** line 79-81 的 T_ramp——**改为 0**（SPS 下 AC 相量 IC 正确注入后，P_ref 可以 t=0 即为 Pe_nominal，不需要斜坡）

```matlab
T_ramp = 0.05;   % seconds — SPS migration: near-zero ramp, IC handles steady-state
% ee_lib 时代 T_ramp=2.0s 是为了补偿 DC 求解器下 IL=0 的冷启动瞬态；
% SPS InitialCurrents 接受 AC 相量 IC 后此补偿无意义
```

### Task 1.2: 替换 Solver Configuration 为 powergui

- [ ] **Step 1**：删除 line 309-323 的 Solver Configuration + Electrical Reference 块添加代码
- [ ] **Step 2**：插入 powergui 块（**Phasor 模式，50 Hz**）

```matlab
%% Step 1: powergui (SPS Phasor mode — confirmed from NE39bus_v2 inspection)
add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 120 80]);
% 注意参数名是 SimulationMode（非 SimulationType），从 NE39 实测确认
set_param([mdl '/powergui'], 'SimulationMode', 'Phasor');
set_param([mdl '/powergui'], 'frequency',      '50');   % Kundur = 50 Hz（NE39 是 60 Hz）
set_param([mdl '/powergui'], 'Pbase',          num2str(Sbase));
```

> **原计划错误更正**：原写 `SimulationType='Continuous'`，实测 NE39 参数名为 `SimulationMode`，值为 `'Phasor'`。

### Task 1.3: 替换 ee_lib 加载为 powerlib

- [ ] **Step 1**：删除 `discover_ee_lib_paths.m` 调用（若在 build 脚本中）
- [ ] **Step 2**：在 build 脚本顶部（`clear; clc` 之后）添加：

```matlab
%% Load SPS powerlib
load_system('powerlib');
fprintf('powerlib loaded.\n');
```

### Task 1.4: 更新 IC 状态

- [ ] **Step 1**：`scenarios/kundur/kundur_ic.json` 的 `calibration_status` 改为 `"pending_rebuild"`

---

## Phase 2: 源替换（G1-G3 + W1/W2）（1 天）

> **架构大改（基于 Phase 0 勘察结论 0.3/0.4）**：
> - ❌ ~~Programmable VS + signal-driven phase~~ — Programmable VS Inport=0，无法信号驱动
> - ❌ ~~S2PS → CVS~~ — ee_lib 特有，SPS 无对应
> - ❌ ~~独立 Zgen/Zw RLC Branch~~ — 阻抗内嵌到 Three-Phase Source
> - ✅ **`Three-Phase Source` + `PhaseAngle=phAng_G{i}` workspace var + `SpecifyImpedance=on`**（NE39 实测范式）
> - ✅ **`Pe_G{i}` workspace Constant** 替代 Power Sensor 闭环

**Files:**
- Modify: `scenarios/kundur/simulink_models/build_powerlib_kundur.m:334-676`

### Task 2.1: G1-G3（Synchronous Gens — Three-Phase Source workspace 范式）

**ee_lib 旧做法**（line 479-616）：Clock → Theta → Vabc → S2PS → CVS + 独立 Zgen RLC + Power Sensor → PS2S → PeGain

**SPS 新做法**（NE39bus_v2 实测范式）：Three-Phase Source（内嵌阻抗，PhaseAngle = workspace）+ V-I Measurement（日志用）+ Constant(Pe_G{i}) → ConvGen P_e input

- [ ] **Step 1**：删除每个 G{i} 的 Clock/wnt/Theta/Vabc/S2PS/CVS/Zgen/PSens/PS2S/PeGain 共 11 类块

- [ ] **Step 2**：用 `Three-Phase Source` 替代，内嵌阻抗，PhaseAngle = workspace 变量：

```matlab
gen_name = sprintf('G%d', gi);
src_path  = [mdl '/' gen_name];
pang_var  = sprintf('phAng_%s', gen_name);  % 'phAng_G1', 'phAng_G2', 'phAng_G3'
assignin('base', pang_var, vlf_gen(gi, 2));  % 初始化 workspace 为 PF 角

add_block('powerlib/Electrical Sources/Three-Phase Source', src_path, 'Position', pos_gen{gi});
set_param(src_path, 'Voltage',          num2str(Vbase * vlf_gen(gi,1)));  % V RMS line-line
set_param(src_path, 'PhaseAngle',       pang_var);     % workspace 变量名（字符串）
set_param(src_path, 'Frequency',        num2str(fn));
set_param(src_path, 'InternalConnection','Yg');
set_param(src_path, 'NonIdealSource',   'on');
set_param(src_path, 'SpecifyImpedance', 'on');
set_param(src_path, 'Resistance',       num2str(R_gen));
set_param(src_path, 'Inductance',       num2str(L_gen));
% 3 个 RConn 分离端口 → 接 Meas_G{gi} LConn1/2/3（用 do_wire_sps）
```

- [ ] **Step 3**：每个 G{i} 加 V-I Measurement（仅日志，RConn 接 bus）：

```matlab
meas_path = [mdl '/Meas_' gen_name];
add_block('powerlib/Measurements/Three-Phase V-I Measurement', meas_path, 'Position', pos_meas_gen{gi});
set_param(meas_path, 'VoltageMeasurement', 'phase-to-ground');
set_param(meas_path, 'CurrentMeasurement', 'yes');
% LConn1/2/3 ← Source RConn1/2/3；RConn1/2/3 → bus
```

- [ ] **Step 4**：`Pe_G{i}` Constant 块 + workspace 变量（替代 Power Sensor 闭环）：

```matlab
pe_var  = sprintf('Pe_G%d', gi);
pe_path = [mdl '/Pe_' gen_name];
assignin('base', pe_var, P0_pu);  % 初始化为 P0（ConvGen base pu）
add_block('built-in/Constant', pe_path, 'Position', pos_pe_gen{gi}, 'Value', pe_var);
add_line(mdl, [pe_path '/1'], sprintf('ConvGen_%s/1', gen_name), 'autorouting','smart');
```

- [ ] **Step 5**：删除 `do_wire_ee` 相关调用，改用 `do_wire_sps`（见 Phase 4 新增辅助函数）将 Meas RConn 注册为 bus node

### Task 2.2: W1/W2（Wind farms — 同 G1-G3 范式，无 ConvGen/Pe）

- [ ] **Step 1**：W1/W2 同样用 `Three-Phase Source` + `SpecifyImpedance=on`（内嵌 Zw），`PhaseAngle = phAng_W{k}` workspace 变量：

```matlab
wind_name = sprintf('W%d', wi);
pang_var  = sprintf('phAng_%s', wind_name);
assignin('base', pang_var, vlf_wind(wi, 2));

add_block('powerlib/Electrical Sources/Three-Phase Source', [mdl '/' wind_name], 'Position', pos_w{wi});
set_param([mdl '/' wind_name], 'Voltage',          num2str(Vbase * vlf_wind(wi,1)));
set_param([mdl '/' wind_name], 'PhaseAngle',       pang_var);
set_param([mdl '/' wind_name], 'Frequency',        num2str(fn));
set_param([mdl '/' wind_name], 'InternalConnection','Yg');
set_param([mdl '/' wind_name], 'NonIdealSource',   'on');
set_param([mdl '/' wind_name], 'SpecifyImpedance', 'on');
set_param([mdl '/' wind_name], 'Resistance',       num2str(R_gen));
set_param([mdl '/' wind_name], 'Inductance',       num2str(L_gen));
```

- [ ] **Step 2**：加 Meas_W{k}（V-I Measurement，仅日志），Meas RConn 注册为 bus node

---

## Phase 3: VSG 接入（ES1-ES4）（1 天）

> **架构大改（基于 Phase 0 勘察结论 0.4）**：完全复刻 NE39bus_v2 实测架构：
> - ❌ ~~Programmable VS + signal-driven phase~~ — 已证伪
> - ❌ ~~独立 Zess RLC Branch~~ — 阻抗内嵌到 Three-Phase Source
> - ❌ ~~Power Sensor → PS2S 闭环~~ — 改为 Pe workspace Constant
> - ✅ `VSrc_ES{i}` = `Three-Phase Source`（PhaseAngle = `phAng_ES{i}`，SpecifyImpedance）
> - ✅ `Pe_{i}` = Constant(`Pe_ES{i}`) → VSG_ES{i} port 5
> - ✅ VSG_ES{i} IntD IC = **0**（增量步进，每步从 0 积分）

**Files:**
- Modify: `scenarios/kundur/simulink_models/build_powerlib_kundur.m:678-990`

### Task 3.1: 保留 VSG 子系统内部，调整 IntD IC

- [ ] **Step 1**：line 703-809 的 VSG 子系统（5 输入 3 输出的信号域 swing eq）**不动**
- [ ] **Step 2**：line 844-920 的 Clock + Theta + 3-相 sin 生成子系统（Vabc 信号）**全部删除**
- [ ] **Step 3**：VSG_ES{i} 内的 IntD `InitialCondition` 改为 `'0'`（NE39 实测确认）：
  ```matlab
  set_param([vsg_path '/IntD'], 'InitialCondition', '0');
  ```

### Task 3.2: VSG 电气接入（NE39bus_v2 实测范式）

对每个 ES{i} (i=1..4)：

- [ ] **Step 1**：`VSrc_ES{i}` = Three-Phase Source（PhaseAngle = workspace var，内嵌阻抗）：

```matlab
vsrc_name = sprintf('VSrc_ES%d', i);
vsrc_path = [mdl '/' vsrc_name];
pang_var  = sprintf('phAng_ES%d', i);
assignin('base', pang_var, ess_delta0_deg(i));  % 初始化为 PF delta0

add_block('powerlib/Electrical Sources/Three-Phase Source', vsrc_path, 'Position', pos_ess_src{i});
set_param(vsrc_path, 'Voltage',          num2str(Vbase * vlf_ess(i,1)));
set_param(vsrc_path, 'PhaseAngle',       pang_var);    % workspace 变量名字符串
set_param(vsrc_path, 'Frequency',        num2str(fn));
set_param(vsrc_path, 'InternalConnection','Yg');
set_param(vsrc_path, 'NonIdealSource',   'on');
set_param(vsrc_path, 'SpecifyImpedance', 'on');
set_param(vsrc_path, 'Resistance',       num2str(R_vsg));
set_param(vsrc_path, 'Inductance',       num2str(L_vsg));
% RConn1/2/3 → Meas_ES{i} LConn1/2/3（3 分离端口，见 do_wire_sps）
```

- [ ] **Step 2**：`Meas_ES{i}` = V-I Measurement（日志用，接 bus）：

```matlab
meas_path = [mdl '/Meas_ES' num2str(i)];
add_block('powerlib/Measurements/Three-Phase V-I Measurement', meas_path, 'Position', pos_meas_ess{i});
set_param(meas_path, 'VoltageMeasurement','phase-to-ground');
set_param(meas_path, 'CurrentMeasurement','yes');
% LConn1/2/3 ← VSrc RConn1/2/3；RConn1/2/3 → ess_bus node（用 do_wire_sps）
% Outport 1（Vabc）→ Log_Vabc_ES{i}；Outport 2（Iabc）→ Log_Iabc_ES{i}
```

- [ ] **Step 3**：`Pe_{i}` = Constant(workspace `Pe_ES{i}`) → VSG Port 5（替代旧 PSensor 闭环）：

```matlab
pe_var  = sprintf('Pe_ES%d', i);
pe_path = [mdl '/Pe_' num2str(i)];
assignin('base', pe_var, VSG_P0(i));  % 初始化为 P0（VSG-base pu）
add_block('built-in/Constant', pe_path, 'Position', pos_pe_ess{i}, 'Value', pe_var);
add_line(mdl, [pe_path '/1'], sprintf('%s/5', vsg_name), 'autorouting','smart');
```

### Task 3.3: 保留 ToWorkspace loggers

- [ ] **Step 1**：`PeFb_ES{i}` ToWorkspace 改为从 `Pe_{i}` Constant 输出分支（等价于旧 PeGain，保持 Python bridge 读取接口不变）
- [ ] **Step 2**：`omega_ES{i}`, `delta_ES{i}`, `P_out_ES{i}` 同旧，从 VSG 子系统 Outport 1/2/3 读取
- [ ] **Step 3**：**新增** `Vabc_ES{i}`, `Iabc_ES{i}` ToWorkspace 块，从 Meas_ES{i} Outport 1/2 读取（Python bridge 步间计算 Pe 用）

### Task 3.4: P_ref ramp 设置

- [ ] **Step 1**：Phasor 模式下 t=0 Pe = Pe_nominal（phAng 已设为 PF 角，无冷启动），T_ramp 可设为 0：
  ```matlab
  T_ramp = 0;   % Phasor IC 正确时无需斜坡
  % PrefRamp slope = VSG_P0(i) / max(T_ramp, 1e-6)（避免除零，用 1e-3 即可）
  ```

---

## Phase 4: 网络层（线+负荷+断路器+shunt）（0.5 天）

**Files:**
- Modify: `scenarios/kundur/simulink_models/build_powerlib_kundur.m:1030-1237`

### Task 4.0: 新增 `do_wire_sps` 辅助函数（Phase 4 之前必须完成）

> **关键缺口**（审核结论）：ee_lib 用 composite 3相端口（1条线），SPS 用 3 个分离端口（LConn1/RConn1，LConn2/RConn2，LConn3/RConn3 分别对应 A/B/C 相）。必须重写母线连接辅助函数。

- [ ] **Step 1**：在 `build_powerlib_kundur.m` 末尾（替换原 `do_wire_ee`）加入：

```matlab
function bus_nodes = do_wire_sps(mdl, bus_nodes, bus_id, blk_name, side)
%DO_WIRE_SPS Connect a block to a bus node via SPS 3-phase separate ports.
%   side: 'LConn' (input side, e.g. load/line from-end)
%         'RConn' (output side, e.g. source out / line to-end)
%   SPS blocks use LConn1/2/3 and RConn1/2/3 for phases A/B/C.
    conn_fmt = [side '%d'];
    if isempty(bus_nodes{bus_id})
        bus_nodes{bus_id} = {blk_name, conn_fmt};
    else
        ref = bus_nodes{bus_id};
        for ph = 1:3
            add_line(mdl, ...
                sprintf('%s/' , ref{1}) + sprintf(ref{2}, ph), ...
                sprintf('%s/', blk_name) + sprintf(conn_fmt, ph), ...
                'autorouting', 'smart');
        end
    end
end
```

### Task 4.1: 传输线（18 条）

> **参数名待 MCP 验证**：Three-Phase PI Section Line 实际参数名需通过 `simulink_query_params` 确认（原计划写的 `Resistances/Inductances/Capacitances` 可能不正确）。

- [ ] **Step 1**：确认 PI Line 参数名（执行前先 MCP 查询）：
  ```matlab
  % MCP simulink_query_params 查 powerlib/Elements/Three-Phase PI Section Line
  ```
- [ ] **Step 2**：ee_lib Transmission Line → `Three-Phase PI Section Line`（完整 R/L/C pi 段），用 `do_wire_sps` 接 from/to bus，**不再需要 LConn2/RConn2 接地（SPS PI Line 内部接地）**

### Task 4.2: 负荷 + Shunts

> **参数名已确认（Phase 0 实测）**：`NominalVoltage`, `NominalFrequency`, `ActivePower`, `InductivePower`, `CapacitivePower`（**注意**：不是 `InductiveReactivePower`）

- [ ] **Step 1**：ee_lib Wye-Load → `powerlib/Elements/Three-Phase Parallel RLC Load`：
  ```matlab
  set_param(load_path, 'NominalVoltage',   num2str(Vbase));
  set_param(load_path, 'NominalFrequency', num2str(fn));
  set_param(load_path, 'ActivePower',      num2str(P_MW * 1e6));
  set_param(load_path, 'InductivePower',   num2str(Q_Mvar * 1e6));  % 确认参数名
  set_param(load_path, 'CapacitivePower',  '0');
  ```
- [ ] **Step 2**：Shunt capacitors → 同上，`ActivePower='0'`, `InductivePower='0'`, `CapacitivePower=num2str(Q_Mvar*1e6)`
- [ ] **Step 3**：用 `do_wire_sps` 接 bus（LConn1/2/3）

### Task 4.3: 扰动负荷（TripLoad1/2）

> **S2PS 层可以去除**：SPS `Three-Phase Dynamic Load` 的 P/Q 端口直接接 Simulink 信号（非物理 PS 端口），无需 S2PS 转换。

- [ ] **Step 1**：`powerlib/Elements/Three-Phase Dynamic Load` 的 P 端口直接接 `Constant(TripLoad1_P)` 信号（删除原来的 S2PS_P_Trip{i}）：
  ```matlab
  add_block('powerlib/Elements/Three-Phase Dynamic Load', [mdl '/' dl3ph_name], ...);
  % P port (Inport) 直接接 Constant 信号，无需 S2PS
  add_block('built-in/Constant', [mdl '/' cp_name], ..., 'Value', var_name);
  add_line(mdl, [cp_name '/1'], [dl3ph_name '/P_port'], 'autorouting','smart');
  % Q port 同理
  ```
- [ ] **Step 2**：用 `do_wire_sps` 接 bus（Dynamic Load composite 端口需确认是否仍是 LConn1）

---

## Phase 5: Bridge 步进逻辑 + workspace 初始化（0.5 天）

> **Phase 5 完全重写**（Phase 0 勘察证伪原 IC 注入方案）：
> - ❌ ~~SpecifyIC / IC 注入~~ — Three-Phase Series RLC Branch 无此参数，Phase 5 原设计作废
> - ❌ ~~PositiveSequence 相位注入~~ — Programmable VS 无信号输入
> - ✅ **Phasor 求解器自动从 phAng_ES{i} 算 t=0 稳态**，无需手动 IC
> - ✅ **新增任务**：更新 `slx_step_and_read.m` + `kundur_simulink_env.py` 支持 phAng/Pe workspace 步进

**Files:**
- Modify: `slx_helpers/slx_step_and_read.m`（新增 phAng 步进逻辑）
- Modify: `slx_helpers/slx_warmup.m`（简化：phAng 直接 assignin，不再需要 6-arg 复杂逻辑）
- Modify: `env/simulink/kundur_simulink_env.py`（步间 phAng/Pe 更新）
- Modify: `scenarios/kundur/simulink_models/build_powerlib_kundur.m`（删除 Step 5b IC 代码 line 993-1027）

### Task 5.1: 删除 Step 5b（IL_specify）代码

- [ ] **Step 1**：删除 `build_powerlib_kundur.m` line 993-1027（整个 Step 5b "Setting AC phasor IL" 段）——这是 ee_lib 特有代码，SPS 无此机制

### Task 5.2: workspace 变量初始化（build 阶段）

- [ ] **Step 1**：在 build 脚本 Step 12（workspace init，line 1284-1291）补充：
  ```matlab
  % 初始化 phAng / Pe workspace 变量（Phasor Three-Phase Source 读取）
  for i = 1:n_vsg
      assignin('base', sprintf('phAng_ES%d', i), ess_delta0_deg(i));  % PF delta0
      assignin('base', sprintf('Pe_ES%d',   i), VSG_P0(i));           % VSG-base pu
  end
  for gi = 1:3
      assignin('base', sprintf('phAng_G%d', gi), vlf_gen(gi,2));      % gen EMF angle
      assignin('base', sprintf('Pe_G%d',    gi), P0_pu_gen(gi));      % gen P0 pu
  end
  for wi = 1:2
      assignin('base', sprintf('phAng_W%d', wi), vlf_wind(wi,2));
  end
  ```

### Task 5.3: 更新 `slx_step_and_read.m` — phAng 步进

- [ ] **Step 1**：在每步仿真后，把 VSG_ES{i} 的 delta increment 累加到 phAng_ES{i}：
  ```matlab
  % 读 delta 增量（IntD 从 IC=0 积分，输出为本步内的相角变化量，rad）
  for i = 1:n_vsg
      delta_inc_rad = delta_ES{i}.Data(end);  % ToWorkspace 末尾值
      phAng_old = evalin('base', sprintf('phAng_ES%d', i));
      assignin('base', sprintf('phAng_ES%d', i), phAng_old + delta_inc_rad * 180/pi);
  end
  ```
- [ ] **Step 2**：同步更新 Pe_ES{i}（从 Meas log 计算 Pe，或用 PeFb_ES{i} pu 值）

### Task 5.4: 更新 `slx_warmup.m` — Phasor 简化

- [ ] **Step 1**：6-arg 分支（`phAng_ES{i}` 注入）已在 ee_lib 时代失效。Phasor 模式下，warmup 只需：
  ```matlab
  % 初始化 workspace → sim → 直接到达稳态（无暖机需要）
  for i = 1:n_vsg
      assignin('base', sprintf('phAng_ES%d', i), delta0_deg(i));
      assignin('base', sprintf('Pe_ES%d', i), pe0_pu(i));
  end
  simOut = sim(mdl, 'StopTime', '0.1');  % 0.1s 足够（Phasor 无冷启动瞬态）
  ```
- [ ] **Step 2**：删除旧的 T_WARMUP / P_ref ramp 等候逻辑（Phasor 模式不需要）

### Task 5.5: 运行 build + rebuild

- [ ] **Step 1**：通过 MCP `simulink_run_script_async` 运行 `build_powerlib_kundur.m`
- [ ] **Step 2**：轮询直到 `RESULT: [12/12] build complete` 或报错
- [ ] **Step 3**：常见失败场景：
  - `powerlib` 未加载 → 顶部已有 `load_system('powerlib')` ✓
  - `PhaseAngle` 参数名错 → 参数名 `PhaseAngle`（实测 NE39 确认）✓
  - `do_wire_sps` 缺少 → 确认函数在 build 脚本末尾 ✓

---

## Phase 6: 验证（0.5 天）

### Task 6.1: Warmup 轨迹探针（新版）

- [ ] **Step 1**：新建 `probes/kundur/probe_warmup_trajectory.m`，测 0-0.5s 的 `Pe_elec`, `omega`, `delta`（用 PQ Measurement 读实际 Pe，不再用 hardcoded `_Pe_prev`）

> 探针结构与之前 T_ramp 修复计划相同（见 [federated-cuddling-pumpkin.md](C:/Users/27443/.claude/plans/federated-cuddling-pumpkin.md) Task A1），只是读 SPS 的 PQ Measurement 输出而非 PeFb_ES 信号。

- [ ] **Step 2**：运行，预期输出：
  - t=10ms: `Pe ≈ Pe_nominal` (5% 容差)
  - t=100ms: `omega ≈ 1.0` (0.002 pu 容差)
  - t=500ms: `delta ≈ delta0` (30° 容差)

### Task 6.2: Phase 3 validate

- [ ] **Step 1**：运行 `probes/kundur/validate_phase3_zero_action.py`（完整 Python 路径，见 `feedback_launch_env.md`）
- [ ] **Step 2**：期望 `VERDICT: PASS` (C1/C3 均 PASS，C4 PASS 但不再是假阳性因为 SPS 下 delta 无需 clip)
- [ ] **Step 3**：若 FAIL：
  - 读 `POST-WARMUP _delta_prev_deg` 与 `[12.62, 4.68, 6.23, 3.32]` 差距
  - 若差距 > 30° → Task 5.3/5.4 的 phase 注入逻辑有误，回 Phase 5
  - 若 delta 稳但 Pe 偏差大 → Task 5.2 的 InitialCurrents 注入有误

### Task 6.3: 单步训练 smoke

- [ ] **Step 1**：运行 `scripts/launch_training.ps1 kundur` 的 1 个 episode 变体（或 MCP `harness_train_smoke_start`，episodes=1）
- [ ] **Step 2**：检查 `omega` 不崩溃，`reward` 不 NaN

### Task 6.4: 现有测试套件

- [ ] **Step 1**：`pytest tests/test_simulink_bridge.py tests/test_env.py -k kundur -v`
- [ ] **Step 2**：绿通过 → Phase 7；任一失败 → 修 Python 端（应该不需要，但检查 `PeFb_ES{i}` 单位匹配）

---

## Phase 7: NOTES + commit（0.5 小时）

### Task 7.1: 更新 `scenarios/kundur/NOTES.md`

- [ ] **Step 1**：删除 Phase 5b 第二轮小节里的三处错误结论（见 [federated-cuddling-pumpkin.md](C:/Users/27443/.claude/plans/federated-cuddling-pumpkin.md) Task C1 Step 1 三条修改）
- [ ] **Step 2**：在"已知事实"节追加：

```markdown
- **ee_lib → SPS 迁移（2026-04-19）**：Kundur 从 Simscape Electrical (`ee_lib`) 迁移至 Specialized Power Systems (`powerlib` + `powergui` Continuous EMT)。根因：ee_lib Simscape 求解器是 DC 求解器，不接受 AC 相量 IL 初值，导致所有 warmup patch 都在治症状。SPS 的 Three-Phase Series RLC Branch 的 `SpecifyIC` + `IC` 字段接受复相量，t=0 Pe ≈ Pe_nominal。NE39 (`scenarios/new_england/`) 一直用 SPS，此次 Kundur 回归同路线。
- **Programmable VS phase 注入**：VSG `delta` 信号通过 Time-dependent amplification 的 Phase 输入端接入 Programmable VS；IntD 初值改为 0（相位基准由 `PositiveSequence.phase0` 承载）。
```

- [ ] **Step 3**：在"试过没用的"节追加：
```markdown
- ee_lib `IL_specify` 方案（2026-04-17）：在 Simscape DC 求解器下 AC 相量被当 DC 瞬时值处理，下一步电压相位变化后电流需重建，无效。
- T_ramp A/B（2026-04-19 前）：2.0s→0.5s→0.3s 均无法消除根本的 AC 冷启动瞬态；问题不在 ramp 时长，在求解器不认 AC 相量 IC。
```

### Task 7.2: 更新 `docs/superpowers/plans/2026-04-18-kundur-pe-contract-fix.md`

- [ ] **Step 1**：顶部状态行标记 `B6 → 归档（SPS 迁移接管）`
- [ ] **Step 2**：7.7 节 B6 段落追加：
```markdown
### B6 归档（2026-04-19）：路线转向 SPS 迁移
ee_lib 路径多轮治症状失败，根因锁定为 DC 求解器无法接受 AC 相量 IC。接任计划：`docs/superpowers/plans/2026-04-19-kundur-sps-migration.md`。
```

### Task 7.3: Commit

- [ ] **Step 1**：`rtk git add` 所有修改文件（`build_powerlib_kundur.m`, `kundur_ic.json`, `probes/kundur/probe_sps_minimal.m`, `probes/kundur/probe_warmup_trajectory.m`, `scenarios/kundur/NOTES.md`, `docs/superpowers/plans/2026-04-18-kundur-pe-contract-fix.md`, `docs/superpowers/plans/2026-04-19-kundur-sps-migration.md`）
- [ ] **Step 2**：提交（HEREDOC 格式）：
```bash
rtk git commit -m "$(cat <<'EOF'
refactor(kundur): migrate Simulink network from ee_lib to SPS powerlib

Root cause of recurring warmup divergence: ee_lib uses Simscape DC
solver which cannot accept AC phasor IL initial conditions. Six
patches (T_WARMUP, IL_specify, vlf_ess, phAng feedback, T_ramp,
IntD init) all treated symptoms of the same structural mismatch.

Migration:
- Network layer: ee_lib → powerlib (Three-Phase Programmable VS,
  Series RLC Branch, PI Section Line, Parallel RLC Load, Breaker)
- Solver: Solver Configuration → powergui Continuous EMT
- IC: IL_specify → SpecifyIC with complex AC phasor (accepted by
  SPS native)
- T_ramp 2.0s → 0.05s (no longer needed)

Preserved: VSG/ConvGen signal-domain swing eq subsystems, Python
bridge, RL env, validate/train pipelines, test suite.

Reference: NE39 SPS implementation (scenarios/new_england/) —
already proven in production.

Phase 3 validate: C1/C3/C4 all PASS.
EOF
)"
```

---

## 回滚方案

若 Phase 2-5 中途卡住无法完成，回滚到 ee_lib：
1. `rtk git checkout HEAD -- scenarios/kundur/simulink_models/build_powerlib_kundur.m`
2. `scenarios/kundur/kundur_ic.json` 的 `calibration_status` 改回 `powerflow_parametric`
3. 重跑 build（恢复 ee_lib `kundur_vsg.slx`）
4. 在 NOTES.md 记录迁移失败原因

若 Route A 全部做完但 Phase 3 validate 仍 FAIL：
1. **不回滚**：保留 SPS 网络层；只改 `powergui/SimulationType` 为 `Phasor`（Route B）
2. 加 `powergui/PhasorFrequency = 50`
3. 重建 IC（Phasor 模式下 IL 自动从 LF 算，可能需移除 `SpecifyIC`）
4. 重跑 Phase 6 验证

---

## 预估时间表

| Phase | 工作量 | 累计 |
|---|---|---|
| 0 可行性勘察 | 0.5 天 | 0.5 |
| 1 参数层 + powergui | 0.5 天 | 1.0 |
| 2 源替换 | 1.0 天 | 2.0 |
| 3 VSG 接入 | 1.0 天 | 3.0 |
| 4 网络层 | 0.5 天 | 3.5 |
| 5 IC 注入 + 潮流 | 0.5 天 | 4.0 |
| 6 验证 | 0.5 天 | 4.5 |
| 7 NOTES + commit | 0.5 h | 4.6 |

**总工期**：约 4-5 个工作日（假设 Phase 0 PASS，无重大回退）。

---

## 风险矩阵

| 风险 | 概率 | 严重度 | 缓解 |
|---|---|---|---|
| SPS `SpecifyIC` 不接受 AC 相量 | 中 | 高 | Phase 0 Task 0.2 先验证；若 FAIL → Route B |
| Programmable VS Time-dependent phase 输入不支持 signal | 中 | 中 | 退回 CVS+Vabc 生成（ee_lib 模式移植到 SPS，VC 仍可设 IC） |
| 16-bus 多机 SPS Continuous EMT 不收敛 | 低 | 高 | local step 从 20ms 降到 10ms；或切 Phasor |
| VSG signal→ 相位耦合 phase0 双计入 | 中 | 低 | Task 5.4 显式置 IntD IC=0；探针验证 |
| Python bridge 对 Pe 单位变更敏感 | 低 | 低 | Task 6.4 测试套件覆盖 |
| `compute_kundur_powerflow.m` 输出不是 AC 相量 | 低 | 中 | Phase 5 Task 5.1 预先确认，必要时扩展 |

---

## 快速参考

### 关键块映射（Phase 0 勘察后修订）

| ee_lib 旧块 | powerlib (SPS) 新块 | 备注 |
|---|---|---|
| CVS + S2PS + Clock/Theta/Vabc | **`Three-Phase Source`**（PhaseAngle=phAng_{} workspace） | 最大架构变化；内嵌阻抗 |
| PVS（Wind，固定相位） | `Three-Phase Source`（PhaseAngle=phAng_W{} workspace） | 同一范式 |
| `ee_lib/Passive/RLC` (Zgen/Zess) | **内嵌到 Three-Phase Source**（SpecifyImpedance=on） | 无独立 RLC Branch |
| `Power Sensor` + PS2S + PeGain | **`Constant(Pe_{} workspace)`** → VSG Port 5 | 步间 workspace 注入，非闭环 |
| `ee_lib/Passive/Lines/TL` | `powerlib/Elements/Three-Phase PI Section Line` | 参数名待 Phase 4 确认 |
| Wye-Connected Load | `powerlib/Elements/Three-Phase Parallel RLC Load` | 参数：ActivePower, InductivePower, CapacitivePower |
| Dynamic Load + S2PS | `Three-Phase Dynamic Load`（直接 Simulink 信号，无 S2PS） | S2PS 层去除 |
| `Solver Configuration` + `Electrical Reference` | `powerlib/powergui`（SimulationMode='Phasor', frequency='50'） | 参数名 SimulationMode（非 SimulationType）|
| `do_wire_ee`（composite 1口） | **`do_wire_sps`**（3 分离端口，每相 1 线）| 新增辅助函数 |

### 关键 workspace 变量（Python bridge ↔ MATLAB）

| 变量 | 方向 | 含义 | 更新时机 |
|---|---|---|---|
| `phAng_ES{i}` | Python→MATLAB | VSrc_ES{i} 绝对相角（度） | 每步开始前 assignin |
| `Pe_ES{i}` | Python→MATLAB | VSG Pe（VSG-base pu） | 每步开始前 assignin（从上步 Meas log 算） |
| `M0_val_ES{i}` | Python→MATLAB | VSG M0（RL action） | 每步开始前 assignin |
| `D0_val_ES{i}` | Python→MATLAB | VSG D0（RL action） | 每步开始前 assignin |
| `delta_ES{i}` | MATLAB→Python | IntD 末值（rad，增量） | 每步结束后 ToWorkspace 读取，累加到 phAng |
| `omega_ES{i}` | MATLAB→Python | IntW 末值（pu） | 每步结束后 ToWorkspace 读取 |
| `Vabc_ES{i}` | MATLAB→Python | V-I Meas 电压信号 | 每步结束后读取，用于计算 Pe |
| `Iabc_ES{i}` | MATLAB→Python | V-I Meas 电流信号 | 每步结束后读取，用于计算 Pe |

### 参数物理量

| 量 | 单位 | 计算 |
|---|---|---|
| Z 从 pu 到 ohm | Ω | `Z_ohm = Z_pu * Vbase^2 / Sbase` |
| L 从 X_pu 到 H | H | `L_H = X_pu * Vbase^2 / Sbase / (2*pi*fn)` |
| Iph RMS 从 P, V | A | `Iph = P / (sqrt(3) * Vbase * pf)` |
| 相量 IC | 复数 | `Iph * exp(j * phase_deg * pi/180)` |

### MCP 调用模板

```yaml
# 运行 build
simulink_run_script_async:
  script_path: scenarios/kundur/simulink_models/build_powerlib_kundur.m

# Phase 3 validate
simulink_run_script_async:
  script_path: C:/Users/27443/AppData/Local/anaconda3/envs/andes_env/python.exe probes/kundur/validate_phase3_zero_action.py

# Minimal probe
simulink_run_script:
  script_path: probes/kundur/probe_sps_minimal.m
```
