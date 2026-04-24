# Kundur ee_lib → SPS Phasor 迁移计划（v2 重写）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Kundur 模型从 ee_lib（Simscape Electrical）迁移到 SPS powerlib Phasor 模式，消除 6 轮 warmup 治症状循环，使 Kundur 走与 NE39 完全一致的共享层路径。

**Architecture:** 用 `powergui`（Phasor 50 Hz）替代 `SolverConfig + Electrical Reference`；每个源改为 `Three-Phase Source`（`PhaseAngle` 绑 workspace 变量 + `SpecifyImpedance`）+ `V-I Measurement`；`pe_measurement` 切到 `'vi'`（Python 端算 V×I），`phase_command_mode` 切到 `'absolute_with_loadflow'`，VSG IntD IC 改为 0（delta 是增量）。共享层 bridge/step/warmup 不动。

**Tech Stack:** MATLAB R2025b · SPS powerlib · Python 3.x (andes_env) · MCP simulink-tools · pytest

---

## 背景与已证伪路径

原计划 `2026-04-19-kundur-sps-migration.md` Phase 0 实测证伪 Route A（Continuous EMT），并发现 4 处 P0/P1 缺陷。本版本从零重写，作废的路径不再出现在任何 actionable 步骤中。

**固定不动的资产（不要修改）**

| 文件 | 原因 |
|---|---|
| `engine/simulink_bridge.py` | 6-arg warmup + Pe/delta 回写已就绪 |
| `slx_helpers/slx_step_and_read.m` | vi/pout/feedback + passthrough/absolute_with_loadflow 全实现 |
| `slx_helpers/slx_warmup.m` | 3/5/6-arg dispatch 已就绪 |
| `engine/mcp_simulink_tools.py` | 不改 |
| `env/simulink/kundur_simulink_env.py` | 只调 bridge 公共接口 |
| `scenarios/kundur/kundur_ic.py` + `kundur_ic.json` | 提供 `vsg_delta0_deg` + `vsg_p0_vsg_base_pu` |

**必须修改的资产**

| 文件 | 操作 |
|---|---|
| `scenarios/kundur/config_simulink.py` | `pe_measurement→vi` / `phase_command_mode→absolute_with_loadflow` / `init_phang` / `T_WARMUP→0.5` |
| `scenarios/kundur/simulink_models/build_powerlib_kundur.m` | 重写网络层（源/网络/负荷/powergui），保留 VSG swing eq 子系统 |
| `tests/test_simulink_bridge.py` | 改 3 个 kundur 测试（feedback→vi / LocalSolver→powergui / dynload 块名） |

**必须新建的资产**

| 文件 | 用途 |
|---|---|
| `probes/kundur/probe_warmup_trajectory.m` | 迁移后 warmup 轨迹验证探针 |

---

## MCP-First 原则（必读）

Phase 3-5 所有建模操作：先用 MCP 在打开的模型上单块验证，再把验证过的命令写入 `build_powerlib_kundur.m`。

**禁止**：猜参数名 → 改整个脚本 → 跑 5 分钟 build → 读报错 → 再改。
**要求**：`simulink_explore_block` → `simulink_query_params` → `simulink_add_block` → `simulink_check_params` → 回写脚本 → `simulink_compile_diagnostics`。

---

## Phase 1: Config + Test 解锁（0.5 天）

目的：先改 config 和测试，让 pytest 在 Phase 2-5 期间指示正确方向。

### Task 1.1：改 `scenarios/kundur/config_simulink.py`

**Files:** Modify `scenarios/kundur/config_simulink.py`

- [ ] **Step 1: 改 `T_WARMUP`**

  打开文件，找到 `T_WARMUP = 3.0`，改为：

  ```python
  T_WARMUP = 0.5  # Phasor 无 ee_lib T_ramp 冷启动瞬态，继承 base 默认值
  ```

- [ ] **Step 2: 改 `KUNDUR_BRIDGE_CONFIG`**

  找到 `KUNDUR_BRIDGE_CONFIG = BridgeConfig(...)` 块，整体替换为：

  ```python
  KUNDUR_BRIDGE_CONFIG = BridgeConfig(
      model_name='kundur_vsg',
      model_dir=SIMULINK_MODEL_DIR or _os.path.join(
          _os.path.dirname(_os.path.abspath(__file__)), 'simulink_models'
      ),
      n_agents=N_AGENTS,
      dt_control=DT,
      sbase_va=SBASE * 1e6,
      m_path_template='{model}/VSG_ES{idx}/M0',
      d_path_template='{model}/VSG_ES{idx}/D0',
      omega_signal='omega_ES{idx}',
      vabc_signal='Vabc_ES{idx}',
      iabc_signal='Iabc_ES{idx}',
      pe_path_template='{model}/Pe_{idx}',
      src_path_template='{model}/VSrc_ES{idx}',
      pe_measurement='vi',                          # was 'feedback'
      phase_command_mode='absolute_with_loadflow',  # was default 'passthrough'
      init_phang=tuple(_ic.vsg_delta0_deg),         # [12.62, 4.68, 6.23, 3.32]
      phase_feedback_gain=1.0,
      tripload1_p_default=248e6 / 3,
      tripload2_p_default=0.0,
      pe0_default_vsg=tuple(VSG_P0_VSG_BASE.tolist()),
      delta0_deg=tuple(_ic.vsg_delta0_deg),
      breaker_step_block_template='',
      breaker_count=0,
  )
  ```

- [ ] **Step 3: 改底部 validation**

  找到 `pe_measurement` 相关的 `if` 断言，改为：

  ```python
  if KUNDUR_BRIDGE_CONFIG.pe_measurement not in ('vi', 'feedback'):
      raise ValueError(
          "Kundur main training path must use a real-measurement mode "
          "('vi' or 'feedback'); 'pout' is debug only."
      )
  ```

### Task 1.2：改测试契约（`tests/test_simulink_bridge.py`）

**Files:** Modify `tests/test_simulink_bridge.py`

- [ ] **Step 1: 把 `test_kundur_config_declares_feedback` 改为 `test_kundur_config_declares_vi`**

  找到该测试（约 :794），整体替换：

  ```python
  def test_kundur_config_declares_vi(self):
      """Kundur main path uses pe_measurement='vi' (mirrors NE39, SPS phasor migration)."""
      from scenarios.kundur.config_simulink import KUNDUR_BRIDGE_CONFIG
      assert KUNDUR_BRIDGE_CONFIG.pe_measurement == "vi"
      assert KUNDUR_BRIDGE_CONFIG.phase_command_mode == "absolute_with_loadflow"
      assert KUNDUR_BRIDGE_CONFIG.init_phang, "init_phang must carry load-flow angles"
  ```

- [ ] **Step 2: 把 `test_kundur_build_script_uses_local_solver` 改为 `test_kundur_build_script_uses_powergui_phasor`**

  找到该测试（约 :533），整体替换：

  ```python
  def test_kundur_build_script_uses_powergui_phasor():
      """Build script uses powerlib/powergui in Phasor mode (SPS migration)."""
      script = (
          Path(__file__).resolve().parents[1]
          / "scenarios" / "kundur" / "simulink_models" / "build_powerlib_kundur.m"
      )
      text = script.read_text(encoding="utf-8")
      assert "powerlib/powergui" in text, "Missing powergui block"
      assert "'SimulationMode', 'Phasor'" in text or '"SimulationMode", "Phasor"' in text, \
          "powergui must run in Phasor mode"
      assert "'frequency', '50'" in text, "Kundur is 50 Hz"
      assert "UseLocalSolver" not in text, "SolverConfig removed in phasor migration"
      assert "ee_lib_paths" not in text, "ee_lib loader removed"
  ```

- [ ] **Step 3: 改 dynload 块名断言**

  找到 `test_kundur_build_script_uses_dynamic_load_not_breakers`（约 :494），把 `dynload_lib` / `DynamicLoad3ph` 等 ee_lib 名字断言替换为：

  ```python
      assert "Three-Phase Dynamic Load" in text, (
          "Disturbance subsystem must use powerlib Three-Phase Dynamic Load"
      )
  ```

- [ ] **Step 4: 跑测试，确认 RED**

  ```bash
  C:/Users/27443/AppData/Local/anaconda3/envs/andes_env/python.exe \
    -m pytest tests/test_simulink_bridge.py -k "kundur and (config or build_script)" -v
  ```

  **期望**：`test_kundur_config_declares_vi` → PASS；`test_kundur_build_script_uses_powergui_phasor` 和 `test_kundur_build_script_uses_dynamic_load_not_breakers` → FAIL（build 脚本还未改，Phase 2-5 解决）。

- [ ] **Step 5: Commit**

  ```bash
  rtk git add scenarios/kundur/config_simulink.py tests/test_simulink_bridge.py
  rtk git commit -m "refactor(kundur): switch bridge config to phasor vi mode (RED for phase 2-5)"
  ```

---

## Phase 2: Build 脚本 — 全局结构重写（1 天）

**Files:** Modify `scenarios/kundur/simulink_models/build_powerlib_kundur.m`

### Task 2.1：头部注释 + 保留参数层

- [ ] **Step 1: 改 header 注释（第 1-48 行附近）**

  把 `"Uses ee_lib (Simscape Electrical) blocks exclusively"` 改为：

  ```matlab
  % Uses SPS powerlib in Phasor mode (50 Hz); migrated from ee_lib 2026-04-19.
  % Port mapping (SPS Three-Phase Source):
  %   RConn1/2/3 = 3 separate phase output ports (A/B/C)
  %   LConn1/2/3 = 3 separate phase input ports (for V-I Measurement)
  ```

- [ ] **Step 2: 删除 `T_ramp = 2.0`（第 81 行附近），替换为注释**

  ```matlab
  % T_ramp: removed in SPS phasor migration.
  % Phasor solver computes algebraic steady-state at t=0 with phAng seeded to
  % delta0 and Pe_ES{i} seeded to VSG_P0; swing eq is balanced from step 1, no
  % ramp compensation needed. Legacy ee_lib value was T_ramp=2.0s.
  ```

- [ ] **Step 3: 保留参数计算段（第 62-277 行）不改**

  保留 `fn / Sbase / Vbase / gen_cfg / wind_cfg / line_defs / load_defs / shunt_defs / trip_defs / VSG_M0 / VSG_D0 / VSG_SN / R_gen / L_gen / R_vsg / L_vsg / pf.* / vlf_gen / vlf_ess`。

### Task 2.2：替换库加载 + 插入 powergui + 定义路径常量

- [ ] **Step 1: 替换 `load_system('ee_lib')` 段（第 282-307 行）**

  删除 `load_system('ee_lib')` / `load_system('nesl_utility')` / `paths = ee_lib_paths()` 及相关变量声明，替换为：

  ```matlab
  %% Load SPS powerlib
  load_system('powerlib');
  fprintf('powerlib loaded.\n');

  % SPS block paths — confirmed via simulink_explore_block + simulink_query_params
  % (update these constants if MCP returns different paths in your R2025b installation)
  SRC_TPS_PATH  = 'powerlib/Electrical Sources/Three-Phase Source';
  MEAS_VI_PATH  = 'powerlib/Measurements/Three-Phase V-I Measurement';
  LINE_PI_PATH  = 'powerlib/Elements/Three-Phase PI Section Line';
  LOAD_RLC_PATH = 'powerlib/Elements/Three-Phase Parallel RLC Load';
  DYNLOAD_PATH  = 'powerlib/Elements/Three-Phase Dynamic Load';
  TWS_PATH      = 'built-in/ToWorkspace';
  ```

  > **注意**：上方路径是典型值，Phase 3 Task 3.0 Step 1 会用 MCP 确认实际路径；如果不同请在脚本顶部更新这 5 个常量。

- [ ] **Step 2: 删除 `SolverConfig + Electrical Reference` 段（第 309-323 行）**

  整段删除，替换为：

  ```matlab
  %% Step 1: powergui (SPS Phasor mode, 50 Hz)
  add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 120 80]);
  set_param([mdl '/powergui'], 'SimulationMode', 'Phasor');
  set_param([mdl '/powergui'], 'frequency',      '50');
  set_param([mdl '/powergui'], 'Pbase',          num2str(Sbase));
  fprintf('  powergui (Phasor 50 Hz) added.\n');
  ```

  > `SimulationMode`（不是 `SimulationType`）；`frequency`（小写）。

### Task 2.3：`do_wire_sps` 辅助函数

- [ ] **Step 1: 在脚本末尾添加（替换 `do_wire_ee`）**

  ```matlab
  function bus_nodes = do_wire_sps(mdl, bus_nodes, bus_id, blk_name, side)
  %DO_WIRE_SPS Connect a block to a shared bus via SPS 3-phase separate ports.
  %   side: 'LConn' | 'RConn'
  %   bus_nodes{bus_id}: empty → this block becomes anchor; else → draw 3 lines.
      conn_fmt = [side '%d'];
      if isempty(bus_nodes{bus_id})
          bus_nodes{bus_id} = {blk_name, conn_fmt};
          return;
      end
      ref     = bus_nodes{bus_id};
      ref_blk = ref{1};
      ref_fmt = ref{2};
      for ph = 1:3
          src_port = sprintf('%s/%s', ref_blk, sprintf(ref_fmt, ph));
          dst_port = sprintf('%s/%s', blk_name, sprintf(conn_fmt, ph));
          add_line(mdl, src_port, dst_port, 'autorouting', 'smart');
      end
  end
  ```

  > **MATLAB 陷阱**：端口路径拼接只能用 `sprintf('%s/%s', a, b)`，绝不用 `sprintf(a) + sprintf(b)`（char array `+` 是数值加法）。

- [ ] **Step 2: 删除旧的 `do_wire_ee` 函数**

  找到脚本末尾 `function bus_nodes = do_wire_ee(...)` 整个函数体，删除。

### Task 2.4：MCP Smoke check + Commit

- [ ] **Step 1: MCP 跑 build 脚本**

  ```
  simulink_run_script  script_path=scenarios/kundur/simulink_models/build_powerlib_kundur.m
  ```

  **期望**：脚本输出含 `"powerlib loaded"` + `"powergui (Phasor 50 Hz) added"`；若有 `ee_lib` 路径错误，说明 `load_system('ee_lib')` 残余未删净。

- [ ] **Step 2: 验证 powergui 块参数**

  ```
  simulink_load_model   model_name=kundur_vsg
  simulink_query_params model_name=kundur_vsg  block_path=powergui
  ```

  **期望**：`SimulationMode = Phasor`，`frequency = 50`。

- [ ] **Step 3: 编译诊断（此时必然报错，但类型要对）**

  ```
  simulink_compile_diagnostics  model=kundur_vsg
  ```

  **期望**：错误应是 "Unknown block type" 或 "Missing connection"（源/网络尚未迁移）；**不应有** `UseLocalSolver` / `ee_lib` / `CVS` / `S2PS` 类型的残余块报错。

- [ ] **Step 4: Commit**

  ```bash
  rtk git add scenarios/kundur/simulink_models/build_powerlib_kundur.m
  rtk git commit -m "refactor(kundur build): replace ee_lib loader with powerlib + powergui phasor"
  ```

---

## Phase 3: 源替换（G1-G3 + W1/W2）（1 天）

### Task 3.0：MCP 一次性探查（全 Phase 复用）

- [ ] **Step 1: 确认 Three-Phase Source 路径和参数名**

  ```
  simulink_explore_block  library=powerlib  pattern=Three-Phase Source
  ```

  **期望**：返回完整路径（如 `powerlib/Electrical Sources/Three-Phase Source`）。若与脚本常量 `SRC_TPS_PATH` 不同，立即更新脚本顶部常量。

  ```
  simulink_query_params  model_name=powerlib  block_path=<上一步返回路径>
  ```

  **期望**：记录以下参数名（实际名称以 MCP 返回为准，不要用猜测值）：
  - 电压幅值参数：通常 `Voltage`
  - 相角参数：通常 `PhaseAngle`（绑 workspace 变量名字符串）
  - 频率参数：通常 `Frequency`
  - 阻抗开关：通常 `SpecifyImpedance`（`'on'`/`'off'`）
  - 接地类型：通常 `InternalConnection`（`'Yg'`）

- [ ] **Step 2: 确认 V-I Measurement 路径、参数和端口**

  ```
  simulink_explore_block        library=powerlib  pattern=V-I Measurement
  simulink_query_params         model_name=powerlib  block_path=<返回路径>
  simulink_describe_block_ports model_name=powerlib  block_path=<返回路径>
  ```

  **期望**：LConn1/2/3 = 3 相输入；RConn1/2/3 = 3 相通过；输出 port 1 = Vabc，port 2 = Iabc。记录具体端口名。

### Task 3.1：G1-G3 — MCP 验证模板 → 回写脚本

- [ ] **Step 1: 加 G1 模板块（MCP 验证用，最后删）**

  ```
  simulink_load_model       model_name=kundur_vsg
  simulink_add_block        target=kundur_vsg/G1_tpl   source=<SRC_TPS_PATH>
  simulink_set_block_params target=kundur_vsg/G1_tpl   params={"PhaseAngle":"phAng_G1","SpecifyImpedance":"on","InternalConnection":"Yg","Frequency":"50"}
  simulink_check_params     target=kundur_vsg/G1_tpl
  simulink_describe_block_ports  target=kundur_vsg/G1_tpl
  ```

  **期望**：`simulink_check_params` 无 warning；`simulink_describe_block_ports` 确认 RConn1/2/3 存在。

- [ ] **Step 2: 加 Meas_G1_tpl + 接线（MCP 验证）**

  ```
  simulink_add_block       target=kundur_vsg/Meas_G1_tpl   source=<MEAS_VI_PATH>
  simulink_connect_ports   src=kundur_vsg/G1_tpl/RConn1    dst=kundur_vsg/Meas_G1_tpl/LConn1
  simulink_connect_ports   src=kundur_vsg/G1_tpl/RConn2    dst=kundur_vsg/Meas_G1_tpl/LConn2
  simulink_connect_ports   src=kundur_vsg/G1_tpl/RConn3    dst=kundur_vsg/Meas_G1_tpl/LConn3
  ```

  **期望**：3 条接线均无 "Port already connected" / "Invalid port" 报错。

- [ ] **Step 3: 删模板块**

  ```
  simulink_delete_block  target=kundur_vsg/G1_tpl
  simulink_delete_block  target=kundur_vsg/Meas_G1_tpl
  ```

- [ ] **Step 4: 删除旧 G1-G3 段（`Clock/wnt/Theta/Vabc/S2PS/CVS/RLC/PSens/PS2S/PeGain` 链）**

  在 `build_powerlib_kundur.m` 中找到 `Step 3: Conventional Generators G1-G3`（约第 336-621 行），删除整段，替换为：

  ```matlab
  %% Step 3: Conventional Generators G1–G3 (Three-Phase Source + V-I Measurement)
  fprintf('\n=== Building conventional generators G1-G3 ===\n');
  fprintf('RESULT: [3/12] building generators G1-G3\n');

  for gi = 1:length(gen_cfg)
      g      = gen_cfg(gi);
      gname  = g.name;
      bus_id = g.bus;
      pang_var = sprintf('phAng_%s', gname);
      assignin('base', pang_var, vlf_gen(gi, 2));  % degrees

      bx = 100 + (gi-1)*500;
      by = 100;

      % ---- ConvGen swing eq subsystem (PRESERVED, unchanged) ----
      sub_path = [mdl '/ConvGen_' gname];
      % [exact ConvGen subsystem build code preserved from original — do not regenerate]
      % The ConvGen_G{i} swing eq block must exist before Pe_G{i} constant is wired.

      % ---- Three-Phase Source ----
      src_path = [mdl '/' gname];
      V_gen    = Vbase * vlf_gen(gi, 1);
      add_block(SRC_TPS_PATH, src_path, 'Position', [bx by bx+80 by+60]);
      set_param(src_path, ...
          'Voltage',            num2str(V_gen), ...
          'PhaseAngle',         pang_var, ...
          'Frequency',          num2str(fn), ...
          'InternalConnection', 'Yg', ...
          'NonIdealSource',     'on', ...
          'SpecifyImpedance',   'on', ...
          'Resistance',         num2str(R_gen), ...
          'Inductance',         num2str(L_gen));

      % ---- V-I Measurement ----
      meas_path = [mdl '/Meas_' gname];
      add_block(MEAS_VI_PATH, meas_path, 'Position', [bx+100 by bx+180 by+60]);
      for ph = 1:3
          add_line(mdl, sprintf('%s/RConn%d', gname, ph), ...
                        sprintf('Meas_%s/LConn%d', gname, ph), 'autorouting', 'smart');
      end

      % ---- Vabc/Iabc ToWorkspace (vi Pe path) ----
      add_block(TWS_PATH, [mdl '/Log_Vabc_' gname], ...
          'Position', [bx+200 by bx+270 by+20], ...
          'VariableName', sprintf('Vabc_%s', gname), 'SaveFormat', 'Timeseries');
      add_block(TWS_PATH, [mdl '/Log_Iabc_' gname], ...
          'Position', [bx+200 by+30 bx+270 by+50], ...
          'VariableName', sprintf('Iabc_%s', gname), 'SaveFormat', 'Timeseries');
      add_line(mdl, sprintf('Meas_%s/1', gname), sprintf('Log_Vabc_%s/1', gname), 'autorouting', 'smart');
      add_line(mdl, sprintf('Meas_%s/2', gname), sprintf('Log_Iabc_%s/1', gname), 'autorouting', 'smart');

      % ---- Pe_G{i} Constant (workspace var, bridge overwrites each step) ----
      pe_var  = sprintf('Pe_%s', gname);  % workspace: Pe_G1 / Pe_G2 / Pe_G3
      pe_path = [mdl '/Pe_' gname];
      assignin('base', pe_var, g.P0_MW * 1e6 / Sbase);
      add_block('built-in/Constant', pe_path, ...
          'Position', [bx-120 by+80 bx-80 by+100], 'Value', pe_var);
      add_line(mdl, [pe_path '/1'], sprintf('ConvGen_%s/1', gname), 'autorouting', 'smart');

      % ---- Meas RConn1/2/3 → bus ----
      bus_nodes = do_wire_sps(mdl, bus_nodes, bus_id, ['Meas_' gname], 'RConn');

      fprintf('  %s at Bus%d: V=%.0fV, phAng_var=%s\n', gname, bus_id, V_gen, pang_var);
  end
  fprintf('RESULT: [3/12] generators done (%d)\n', length(gen_cfg));
  ```

  > **注意**：`ConvGen_G{i}` 子系统内部保留（swing eq + IntD + IntW）。外部的 Clock/wnt/Theta/Vabc/S2PS/CVS/RLC/PSens/PS2S/PeGain 链全部删除。Pe 现在由 workspace Constant 提供，每步由 bridge 的 vi 测量结果覆写。

### Task 3.2：W1/W2 — 复用 G 结构，但无 swing eq 连接

- [ ] **Step 1: 删除旧 `Step 4: Wind Farms` 段（约第 624-676 行），替换为：**

  ```matlab
  %% Step 4: Wind Farms W1, W2 (Three-Phase Source + V-I Measurement)
  fprintf('\n=== Building wind farms W1, W2 ===\n');
  fprintf('RESULT: [4/12] building wind farms W1-W2\n');

  for wi = 1:length(wind_cfg)
      w      = wind_cfg(wi);
      wname  = w.name;
      bus_id = w.bus;
      pang_var = sprintf('phAng_%s', wname);
      assignin('base', pang_var, vlf_wind(wi, 2));  % degrees

      bx = 100 + (wi-1)*500;
      by = 500;

      % ---- Three-Phase Source ----
      src_path = [mdl '/' wname];
      V_wind   = Vbase * vlf_wind(wi, 1);
      add_block(SRC_TPS_PATH, src_path, 'Position', [bx by bx+80 by+60]);
      set_param(src_path, ...
          'Voltage',            num2str(V_wind), ...
          'PhaseAngle',         pang_var, ...
          'Frequency',          num2str(fn), ...
          'InternalConnection', 'Yg', ...
          'NonIdealSource',     'on', ...
          'SpecifyImpedance',   'on', ...
          'Resistance',         num2str(R_gen), ...
          'Inductance',         num2str(L_gen));

      % ---- V-I Measurement ----
      meas_path = [mdl '/Meas_' wname];
      add_block(MEAS_VI_PATH, meas_path, 'Position', [bx+100 by bx+180 by+60]);
      for ph = 1:3
          add_line(mdl, sprintf('%s/RConn%d', wname, ph), ...
                        sprintf('Meas_%s/LConn%d', wname, ph), 'autorouting', 'smart');
      end

      % ---- Vabc/Iabc ToWorkspace ----
      add_block(TWS_PATH, [mdl '/Log_Vabc_' wname], ...
          'Position', [bx+200 by bx+270 by+20], ...
          'VariableName', sprintf('Vabc_%s', wname), 'SaveFormat', 'Timeseries');
      add_block(TWS_PATH, [mdl '/Log_Iabc_' wname], ...
          'Position', [bx+200 by+30 bx+270 by+50], ...
          'VariableName', sprintf('Iabc_%s', wname), 'SaveFormat', 'Timeseries');
      add_line(mdl, sprintf('Meas_%s/1', wname), sprintf('Log_Vabc_%s/1', wname), 'autorouting', 'smart');
      add_line(mdl, sprintf('Meas_%s/2', wname), sprintf('Log_Iabc_%s/1', wname), 'autorouting', 'smart');

      % Wind 无 swing eq → 无 Pe Constant，不接任何 ConvGen 端口

      % ---- Meas RConn → bus ----
      bus_nodes = do_wire_sps(mdl, bus_nodes, bus_id, ['Meas_' wname], 'RConn');

      fprintf('  %s at Bus%d: V=%.0fV, phAng_var=%s\n', wname, bus_id, V_wind, pang_var);
  end
  fprintf('RESULT: [4/12] wind farms done (%d)\n', length(wind_cfg));
  ```

### Task 3.3：MCP 验证 G/W + Commit

- [ ] **Step 1: MCP 追踪 G1 拓扑**

  ```
  simulink_trace_port_connections  model=kundur_vsg  block=G1  port=RConn1
  simulink_compile_diagnostics     model=kundur_vsg
  ```

  **期望**：RConn1 → Meas_G1 → bus 节点；编译错误仅来自 VSG/ES 和网络层尚未迁移，G/W 无报错。

- [ ] **Step 2: Commit**

  ```bash
  rtk git add scenarios/kundur/simulink_models/build_powerlib_kundur.m
  rtk git commit -m "refactor(kundur build): migrate G1-G3 + W1/W2 to Three-Phase Source (MCP-verified)"
  ```

---

## Phase 4: VSG（ES1-ES4）（1 天）

**Files:** Modify `scenarios/kundur/simulink_models/build_powerlib_kundur.m` VSG 段

### Task 4.1：保留 VSG swing eq，改 IntD IC

- [ ] **Step 1: 找到 VSG `IntD` 初始条件设置（约 :774-777），改为 IC=0**

  找到：`'InitialCondition', num2str(delta0_rad)`（在 `add_block('built-in/Integrator', [vsg_path '/IntD'], ...` 附近）

  改为：

  ```matlab
  add_block('built-in/Integrator', [vsg_path '/IntD'], ...
      'Position', [500 240 540 280], ...
      'InitialCondition', '0');
  % IC=0: Phasor mode integrates delta as increment from equilibrium.
  % phAng_ESi = init_phang[i] + delta is seeded to delta0 by absolute_with_loadflow.
  ```

- [ ] **Step 2: 删除 VSG 外部的电气链（Clock/wnt/Theta/Vabc/S2PS/CVS/RLC/PSens/PS2S/PeGain/PeFb）**

  在 VSG 建设循环的电气部分（约 :844-970），删除：
  - `Clk_ES{i}` / `wnt_ES{i}` / `Theta_ES{i}` / `Vabc_ES{i}` subsystem
  - `S2PS_ES{i}` / `CVS_ES{i}` / `GND_*` / `Zess_{i}`
  - `PSens_ES{i}` / `PS2S_ES{i}` / `PeGain_ES{i}` / `Log_PeFb_ES{i}`

  同时删除 `PrefRamp_{i}` / `PrefSat_{i}`（P_ref 斜坡，Phasor 不需要）。

### Task 4.2：VSrc_ES{i} + Meas_ES{i}

- [ ] **Step 1: MCP 验证 VSrc_ES1 模板**

  ```
  simulink_load_model       model_name=kundur_vsg
  simulink_add_block        target=kundur_vsg/VSrc_ES1_tpl  source=<SRC_TPS_PATH>
  simulink_set_block_params target=kundur_vsg/VSrc_ES1_tpl  params={"PhaseAngle":"phAng_ES1","SpecifyImpedance":"on","Frequency":"50"}
  simulink_check_params     target=kundur_vsg/VSrc_ES1_tpl
  simulink_delete_block     target=kundur_vsg/VSrc_ES1_tpl
  ```

  **期望**：`simulink_check_params` 无 warning。

- [ ] **Step 2: 在 build 脚本 VSG 循环末尾添加 VSrc/Meas/ToWorkspace 代码**

  在 swing eq 子系统建立后（`IntD IC=0` 之后），添加：

  ```matlab
      % ---- VSrc_ES{i}: Three-Phase Source (phAng bound to workspace var) ----
      vsrc_path = [mdl sprintf('/VSrc_ES%d', i)];
      pang_var  = sprintf('phAng_ES%d', i);
      V_ess     = Vbase * vlf_ess(i, 1);
      add_block(SRC_TPS_PATH, vsrc_path, 'Position', [bx+400 by bx+480 by+60]);
      set_param(vsrc_path, ...
          'Voltage',            num2str(V_ess), ...
          'PhaseAngle',         pang_var, ...
          'Frequency',          num2str(fn), ...
          'InternalConnection', 'Yg', ...
          'NonIdealSource',     'on', ...
          'SpecifyImpedance',   'on', ...
          'Resistance',         num2str(R_vsg), ...
          'Inductance',         num2str(L_vsg));

      % ---- Meas_ES{i}: V-I Measurement ----
      meas_path = [mdl sprintf('/Meas_ES%d', i)];
      add_block(MEAS_VI_PATH, meas_path, 'Position', [bx+500 by bx+580 by+60]);
      for ph = 1:3
          add_line(mdl, sprintf('VSrc_ES%d/RConn%d', i, ph), ...
                        sprintf('Meas_ES%d/LConn%d', i, ph), 'autorouting', 'smart');
      end

      % ---- Vabc/Iabc ToWorkspace (slx_step_and_read reads these for vi Pe) ----
      add_block(TWS_PATH, [mdl sprintf('/Log_Vabc_ES%d', i)], ...
          'Position', [bx+600 by bx+670 by+20], ...
          'VariableName', sprintf('Vabc_ES%d', i), 'SaveFormat', 'Timeseries');
      add_block(TWS_PATH, [mdl sprintf('/Log_Iabc_ES%d', i)], ...
          'Position', [bx+600 by+30 bx+670 by+50], ...
          'VariableName', sprintf('Iabc_ES%d', i), 'SaveFormat', 'Timeseries');
      add_line(mdl, sprintf('Meas_ES%d/1', i), sprintf('Log_Vabc_ES%d/1', i), 'autorouting', 'smart');
      add_line(mdl, sprintf('Meas_ES%d/2', i), sprintf('Log_Iabc_ES%d/1', i), 'autorouting', 'smart');

      % ---- Meas_ES{i} RConn → bus ----
      bus_nodes = do_wire_sps(mdl, bus_nodes, bus_id, sprintf('Meas_ES%d', i), 'RConn');
  ```

### Task 4.3：Pe_ES{i} workspace Constant → VSG Port 5

- [ ] **Step 1: 在 Task 4.2 代码之后接着加 Pe Constant 连线**

  ```matlab
      % ---- Pe_ESi Constant: bridge 每步用 vi 算出真实 Pe 写入此 workspace var ----
      pe_var  = sprintf('Pe_ES%d', i);   % workspace 变量名（slx_step_and_read 约定）
      pe_path = [mdl sprintf('/Pe_%d', i)];  % 块路径用数字避免歧义
      assignin('base', pe_var, VSG_P0(i));   % VSG-base pu 初值；bridge warmup 会覆写
      add_block('built-in/Constant', pe_path, ...
          'Position', [bx-120 by+80 bx-80 by+100], 'Value', pe_var);
      add_line(mdl, [pe_path '/1'], sprintf('%s/5', vsg_name), 'autorouting', 'smart');
  ```

  > `Pe_ES{i}` 是 workspace 变量名；`Pe_{i}` 是块路径名。`slx_step_and_read.m:67-70` 每步 `assignin('base', 'Pe_ESi', Pe_prev * pe_scale)`，其中 `Pe_prev` 来自上一步 V×I 真实电气测量，**不是命令回显**。

### Task 4.4：保留 omega/delta/P_out ToWorkspace，删 PeFb 相关

- [ ] **Step 1: 确认 VSG Outport 1/2/3 → Log_omega/delta/P_out_ES{i} 的连线保留**

  检查现有代码（约 :974-986）的 ToWorkspace 循环是否已保留（不要删除）：

  ```matlab
      out_log_names = {'omega', 'delta', 'P_out'};
      for out_idx = 1:3
          log_name = sprintf('Log_%s_ES%d', out_log_names{out_idx}, i);
          log_path = [mdl '/' log_name];
          lx = bx + 200;
          ly = by - 10 + (out_idx-1) * 30;
          add_block(TWS_PATH, log_path, ...
              'Position', [lx ly lx+60 ly+20], ...
              'VariableName', sprintf('%s_ES%d', out_log_names{out_idx}, i), ...
              'SaveFormat', 'Timeseries');
          add_line(mdl, sprintf('%s/%d', vsg_name, out_idx), ...
              [log_name '/1'], 'autorouting', 'smart');
      end
  ```

  如果该段已被删除，补回来。

- [ ] **Step 2: 确认 `Log_PeFb_ES{i}` 相关代码已删除**

  搜索 `PeFb_ES` / `PeGain_ES` / `Log_PeFb_ES`——这些代码应在 Task 4.1 Step 2 中已删除。如有残余，删除。

### Task 4.5：bus 连接验证 + Commit

- [ ] **Step 1: MCP 抽查 ESS 母线拓扑**

  ```
  simulink_trace_port_connections  model=kundur_vsg  block=VSrc_ES1  port=RConn1
  simulink_compile_diagnostics     model=kundur_vsg
  ```

  **期望**：RConn1 → Meas_ES1 → 母线节点；编译报错仅来自网络层尚未迁移。

- [ ] **Step 2: Commit**

  ```bash
  rtk git add scenarios/kundur/simulink_models/build_powerlib_kundur.m
  rtk git commit -m "refactor(kundur build): migrate VSG_ES1-4 to Three-Phase Source + vi Pe feedback"
  ```

---

## Phase 5: 网络层 + workspace 初始化（0.5 天）

**Files:** Modify `scenarios/kundur/simulink_models/build_powerlib_kundur.m`

### Task 5.1：传输线（Three-Phase PI Section Line）

- [ ] **Step 1: MCP 探查**

  ```
  simulink_explore_block  library=powerlib  pattern=PI Section Line
  simulink_query_params   model_name=powerlib  block_path=<返回路径>
  ```

  **期望**：记录参数名（典型：`R`、`L`、`Cl`（nF/km）、`length`、`freq`）。若与 `LINE_PI_PATH` 常量不同，更新常量。

- [ ] **Step 2: 删除旧 `Step 6: Transmission lines`（约 :1030-1080），替换为：**

  ```matlab
  %% Step 6: Transmission lines (Three-Phase PI Section Line)
  fprintf('\n=== Adding transmission lines ===\n');
  fprintf('RESULT: [6/12] adding %d transmission lines\n', size(line_defs, 1));

  n_lines = size(line_defs, 1);
  line_y_base = 800;

  for li = 1:n_lines
      lname    = line_defs{li, 1};
      from_bus = line_defs{li, 2};
      to_bus   = line_defs{li, 3};
      len_km   = line_defs{li, 4};
      R_km     = line_defs{li, 5};
      L_km     = line_defs{li, 6};
      C_km     = line_defs{li, 7};

      lx = 100 + mod(li-1, 5) * 300;
      ly = line_y_base + floor((li-1)/5) * 120;

      line_path = [mdl '/' lname];
      add_block(LINE_PI_PATH, line_path, 'Position', [lx ly lx+80 ly+50]);
      set_param(line_path, ...
          'R',      num2str(R_km), ...
          'L',      num2str(L_km * 1000), ...   % H/km → mH/km
          'Cl',     num2str(C_km * 1e9), ...    % F/km → nF/km
          'length', num2str(len_km), ...
          'freq',   num2str(fn));

      bus_nodes = do_wire_sps(mdl, bus_nodes, from_bus, lname, 'LConn');
      bus_nodes = do_wire_sps(mdl, bus_nodes, to_bus,   lname, 'RConn');

      fprintf('  %s: Bus%d -> Bus%d, %.0fkm\n', lname, from_bus, to_bus, len_km);
  end
  fprintf('RESULT: [6/12] transmission lines done (%d)\n', n_lines);
  ```

### Task 5.2：负荷 + Shunts（Three-Phase Parallel RLC Load）

- [ ] **Step 1: MCP 探查**

  ```
  simulink_explore_block  library=powerlib  pattern=Parallel RLC Load
  simulink_query_params   model_name=powerlib  block_path=<返回路径>
  ```

  **期望**：记录参数名（典型：`ActivePower`、`InductivePower`、`CapacitivePower`、`Vn`、`Fn`）。

- [ ] **Step 2: 删除旧 `Step 7: Loads` + `Step 8: Shunts`，替换为：**

  ```matlab
  %% Step 7: Loads (Three-Phase Parallel RLC Load)
  fprintf('\n=== Adding loads ===\n');
  for li = 1:length(load_defs)
      ld        = load_defs(li);
      load_path = [mdl '/' ld.name];
      lx = 100 + (li-1)*300; ly = 1400;
      add_block(LOAD_RLC_PATH, load_path, 'Position', [lx ly lx+60 ly+50]);
      set_param(load_path, ...
          'ActivePower',    num2str(ld.P_MW * 1e6), ...
          'InductivePower', num2str(ld.Q_Mvar * 1e6), ...
          'Vn',             num2str(Vbase), ...
          'Fn',             num2str(fn));
      bus_nodes = do_wire_sps(mdl, bus_nodes, ld.bus, ld.name, 'LConn');
      fprintf('  %s at Bus%d: P=%.0fMW, Q=%.0fMvar\n', ld.name, ld.bus, ld.P_MW, ld.Q_Mvar);
  end

  %% Step 8: Shunt capacitors (Three-Phase Parallel RLC Load, C-only)
  fprintf('\n=== Adding shunt capacitors ===\n');
  for si = 1:length(shunt_defs)
      sh         = shunt_defs(si);
      shunt_path = [mdl '/' sh.name];
      sx = 100 + (si-1)*300; sy = 1550;
      add_block(LOAD_RLC_PATH, shunt_path, 'Position', [sx sy sx+60 sy+50]);
      set_param(shunt_path, ...
          'ActivePower',      '0', ...
          'CapacitivePower',  num2str(sh.Q_Mvar * 1e6), ...
          'Vn',               num2str(Vbase), ...
          'Fn',               num2str(fn));
      bus_nodes = do_wire_sps(mdl, bus_nodes, sh.bus, sh.name, 'LConn');
      fprintf('  %s at Bus%d: %.0f Mvar capacitive\n', sh.name, sh.bus, sh.Q_Mvar);
  end
  ```

  > 参数名（`ActivePower` / `InductivePower` / `CapacitivePower` / `Vn` / `Fn`）以 Task 5.2 Step 1 MCP 返回为准，不要照抄上面默认值。

### Task 5.3：扰动负荷（Three-Phase Dynamic Load）

- [ ] **Step 1: MCP 探查**

  ```
  simulink_explore_block        library=powerlib  pattern=Dynamic Load
  simulink_query_params         model_name=powerlib  block_path=<返回路径>
  simulink_describe_block_ports model_name=powerlib  block_path=<返回路径>
  ```

  **期望**：确认 P 输入端口名（Phasor 版 Dynamic Load 通常是 Inport `1`（P）和 Inport `2`（Q）的信号连接，而不是 ee_lib 的 `LConn2/LConn3` 物理信号端口）。

- [ ] **Step 2: 删除旧 `Step 9: Disturbance loads`（约 :1152-1237），替换为：**

  ```matlab
  %% Step 9: Disturbance loads (Three-Phase Dynamic Load + workspace vars)
  fprintf('\n=== Adding Dynamic Load (Three-Phase) disturbance subsystems ===\n');
  fprintf('RESULT: [9/12] adding Dynamic Load (Three-Phase) disturbance subsystems\n');

  TripLoad1_P = 248e6 / 3;
  TripLoad2_P = 0.0;
  assignin('base', 'TripLoad1_P', TripLoad1_P);
  assignin('base', 'TripLoad2_P', TripLoad2_P);

  for ti = 1:size(trip_defs, 1)
      var_name  = trip_defs{ti, 1};
      bus_id    = trip_defs{ti, 2};
      default_W = trip_defs{ti, 3};
      label     = trip_defs{ti, 4};

      bx_t = 800 + (ti-1)*600;  by_t = 1400;

      dl_name = sprintf('DynLoad_Trip%d', ti);
      add_block(DYNLOAD_PATH, [mdl '/' dl_name], ...
          'Position', [bx_t by_t bx_t+80 by_t+60]);

      bus_nodes = do_wire_sps(mdl, bus_nodes, bus_id, dl_name, 'LConn');

      % P control: Constant(workspace var) → DynLoad P port
      cp_name = sprintf('C_P_Trip%d', ti);
      add_block('built-in/Constant', [mdl '/' cp_name], ...
          'Position', [bx_t+100 by_t+70 bx_t+150 by_t+90], 'Value', var_name);
      % NOTE: SPS Dynamic Load P/Q port wiring confirmed by simulink_describe_block_ports
      % in Task 5.3 Step 1. Replace '/1' below with actual port name if different.
      add_line(mdl, [cp_name '/1'], sprintf('%s/1', dl_name), 'autorouting', 'smart');

      % Q control: Constant(0) → DynLoad Q port
      cq_name = sprintf('C_Q_Trip%d', ti);
      add_block('built-in/Constant', [mdl '/' cq_name], ...
          'Position', [bx_t+100 by_t+100 bx_t+150 by_t+120], 'Value', '0');
      add_line(mdl, [cq_name '/1'], sprintf('%s/2', dl_name), 'autorouting', 'smart');

      fprintf('  Trip%d at Bus%d: var=%s, default=%.0fW — %s\n', ...
          ti, bus_id, var_name, default_W, label);
  end
  fprintf('RESULT: [9/12] Dynamic Load (Three-Phase) done\n');
  ```

  > SPS Dynamic Load 端口（`/1`=P，`/2`=Q）以 Task 5.3 Step 1 MCP 实测为准。如果是物理信号端口（LConn），改用 `add_line(mdl, [cp_name '/1'], [dl_name '/LConn2'], ...)` 格式。

### Task 5.4：Step 5b IL 代码 — 删除

- [ ] **Step 1: 找到并删除 `Step 5b: Set AC phasor IL`（约 :993-1027，整段约 35 行）**

  确认删除范围：从 `%% Step 5b: Set AC phasor IL` 到 `fprintf('RESULT: [5b/12] RL initial currents set (9 blocks)\n');`。

  Phasor 求解器自动算代数稳态，不需要手动 IC 注入。

### Task 5.5：删除 `Step 9b: SolverConfig 连线` + 添加 workspace init

- [ ] **Step 1: 删除旧 `Step 9b: Connect Solver Configuration`（约 :1240-1249）**

  整段删除（powergui 不需要连到网络节点）。

- [ ] **Step 2: 在 `Step 11: Solver configuration and save` 之前插入 workspace init 段**

  ```matlab
  %% Step 10b: Initialize phAng / Pe workspace variables
  % bridge.warmup() overwrites these with actual load-flow values each episode.
  for i = 1:n_vsg
      assignin('base', sprintf('phAng_ES%d', i), ess_delta0_deg(i));
      assignin('base', sprintf('Pe_ES%d',    i), VSG_P0(i));
  end
  for gi = 1:3
      assignin('base', sprintf('phAng_%s', gen_cfg(gi).name), vlf_gen(gi, 2));
  end
  for wi = 1:2
      assignin('base', sprintf('phAng_%s', wind_cfg(wi).name), vlf_wind(wi, 2));
  end
  fprintf('RESULT: [10b/12] workspace vars initialized\n');
  ```

- [ ] **Step 3: 改 `Step 11: Solver configuration`——改成 Phasor 求解器设置**

  ```matlab
  set_param(mdl, ...
      'StopTime',   '10.0', ...
      'SolverType', 'Variable-step', ...
      'Solver',     'ode23t', ...
      'MaxStep',    '0.001', ...
      'RelTol',     '1e-4');
  ```

  保留 `save_system(mdl, model_path)`。

### Task 5.6：重建 `.slx` + Commit

- [ ] **Step 1: 删旧 .slx，跑 build 脚本**

  ```bash
  rm "scenarios/kundur/simulink_models/kundur_vsg.slx"
  ```

  ```
  simulink_run_script  script_path=scenarios/kundur/simulink_models/build_powerlib_kundur.m
  ```

  **期望**：输出结尾 `RESULT: [DONE] build_powerlib_kundur complete` 且无 MATLAB 错误。若失败：
  - 未知 block path → 检查 `SRC_TPS_PATH` / `MEAS_VI_PATH` 等常量与 MCP 探查结果是否一致
  - 参数名错 → 用 `simulink_query_params` 复核对应块

- [ ] **Step 2: 编译诊断**

  ```
  simulink_compile_diagnostics  model=kundur_vsg
  ```

  **期望**：无 error（允许合理 warning）。

- [ ] **Step 3: Commit**

  ```bash
  rtk git add scenarios/kundur/simulink_models/build_powerlib_kundur.m
  rtk git commit -m "refactor(kundur build): migrate network layer + remove IL_specify + workspace init"
  ```

---

## Phase 6: Verification（0.5 天）

### Task 6.1：Warmup 轨迹探针

**Files:** Create `probes/kundur/probe_warmup_trajectory.m`

- [ ] **Step 1: 写探针文件**

  ```matlab
  % probes/kundur/probe_warmup_trajectory.m
  % Post-migration warmup trajectory probe: verifies Phasor algebraic steady-state.

  mdl = 'kundur_vsg';
  if bdIsLoaded(mdl), close_system(mdl, 0); end

  script_dir   = fileparts(mfilename('fullpath'));
  repo_root    = fileparts(fileparts(script_dir));
  load_system(fullfile(repo_root, 'scenarios', 'kundur', 'simulink_models', mdl));

  delta0_deg_vec = [12.62, 4.68, 6.23, 3.32];
  VSG_P0_vec     = [0.1, 0.1, 0.1, 0.1];
  for i = 1:4
      assignin('base', sprintf('phAng_ES%d', i), delta0_deg_vec(i));
      assignin('base', sprintf('Pe_ES%d',    i), VSG_P0_vec(i));
      assignin('base', sprintf('M0_val_ES%d', i), 12.0);
      assignin('base', sprintf('D0_val_ES%d', i), 3.0);
  end
  for gi = 1:3
      gen_names = {'G1','G2','G3'};
      vlf_g     = [23.5, 21.0, -4.5];
      assignin('base', sprintf('phAng_%s', gen_names{gi}), vlf_g(gi));
  end
  assignin('base', 'TripLoad1_P', 248e6/3);
  assignin('base', 'TripLoad2_P', 0.0);

  set_param(mdl, 'StopTime', '0.5');
  simOut = sim(mdl);

  fprintf('\n=== probe_warmup_trajectory results ===\n');
  all_pass = true;
  for i = 1:4
      omega_ts = simOut.get(sprintf('omega_ES%d', i));
      delta_ts = simOut.get(sprintf('delta_ES%d', i));
      Vabc_ts  = simOut.get(sprintf('Vabc_ES%d', i));
      Iabc_ts  = simOut.get(sprintf('Iabc_ES%d', i));

      for t_check = [0.01, 0.1, 0.5]
          [~, k] = min(abs(omega_ts.Time - t_check));
          Sva = sum(Vabc_ts.Data(k,:) .* conj(Iabc_ts.Data(k,:)));
          Pe_vi = real(Sva) / 100e6;
          omega_val = omega_ts.Data(k);
          delta_val = delta_ts.Data(k) * 180/pi;
          fprintf('ES%d t=%.2fs  omega=%.4fpu  delta=%.2fdeg  Pe_vi=%.4fpu\n', ...
              i, omega_ts.Time(k), omega_val, delta_val, Pe_vi);
          if t_check == 0.01
              if abs(omega_val - 1.0) > 1e-3
                  fprintf('  FAIL: omega not near 1.0 at t=10ms\n');
                  all_pass = false;
              end
              Pe_ref = VSG_P0_vec(i) * 200e6 / 100e6;
              if abs(Pe_vi - Pe_ref) / Pe_ref > 0.05
                  fprintf('  FAIL: Pe_vi=%.4f not near Pe_ref=%.4f (>5%%)\n', Pe_vi, Pe_ref);
                  all_pass = false;
              end
          end
      end
  end

  if all_pass
      fprintf('\nRESULT: probe_warmup_trajectory PASS\n');
  else
      fprintf('\nRESULT: probe_warmup_trajectory FAIL — see above\n');
  end
  close_system(mdl, 0);
  ```

- [ ] **Step 2: MCP 跑探针**

  ```
  simulink_run_script  script_path=probes/kundur/probe_warmup_trajectory.m
  ```

  **期望**：`t=10ms: omega ≈ 1.0 (|Δ| < 1e-3), Pe_vi ≈ 0.2 pu (VSG_P0=0.1 pu on VSG base = 0.2 pu on Sbase)`；`RESULT: probe_warmup_trajectory PASS`。

### Task 6.2：Phase 3 validate

- [ ] **Step 1: 跑 Phase 3 validate 探针**

  ```bash
  C:/Users/27443/AppData/Local/anaconda3/envs/andes_env/python.exe \
    probes/kundur/validate_phase3_zero_action.py
  ```

  **期望**：`VERDICT: PASS`（C1/C3/C4 均 PASS）。

- [ ] **Step 2: 若 FAIL，诊断**

  - `_delta_prev_deg ≈ 0`（IntD IC=0，warmup 短）→ `phAng = init_phang + 0 = delta0`，正确
  - 若 delta 漂 → 检查 `phase_command_mode='absolute_with_loadflow'` 且 `init_phang` 长度==4
  - 若 Pe=0 → 检查 `Vabc_ES{i}`/`Iabc_ES{i}` ToWorkspace 信号名和 Meas 连线

### Task 6.3：训练 Smoke test

- [ ] **Step 1: MCP 启动单 episode smoke**

  ```
  mcp__simulink-tools__harness_train_smoke_start  scenario=kundur  episodes=1
  ```

- [ ] **Step 2: Poll 完成**

  ```
  mcp__simulink-tools__harness_train_smoke_poll
  ```

  **期望**：`omega` 不崩（范围 0.7-1.3），`reward` 不 NaN，episode 正常结束。

### Task 6.4：pytest 套件

- [ ] **Step 1: 跑 Kundur 相关测试**

  ```bash
  C:/Users/27443/AppData/Local/anaconda3/envs/andes_env/python.exe \
    -m pytest tests/test_simulink_bridge.py tests/test_env.py -k "kundur" -v
  ```

  **期望**：全绿（Phase 1 改的 3 个测试 + 其余 kundur 测试）。若 FAIL：检查是否还有 `PeFb_ES` / `pe_feedback_signal` 断言残留。

- [ ] **Step 2: Commit verification 产物**

  ```bash
  rtk git add probes/kundur/probe_warmup_trajectory.m
  rtk git commit -m "test(kundur): add post-migration warmup trajectory probe"
  ```

---

## Phase 7: NOTES + 归档（30 分钟）

### Task 7.1：更新 `scenarios/kundur/NOTES.md`

**Files:** Modify `scenarios/kundur/NOTES.md`

- [ ] **Step 1: 在"已知事实"追加**

  ```markdown
  - **ee_lib → SPS Phasor 迁移（2026-04-19）**：Kundur 从 Simscape Electrical 迁至 SPS powerlib Phasor 50 Hz。根因：ee_lib Simscape 求解器是 DC 求解器，不接受 AC 相量 IC，6 轮 warmup patch 均治症状。NE39 一直用 SPS Phasor，此次 Kundur 镜像其架构。
  - **架构范式**：`Three-Phase Source(PhaseAngle=phAng_{NAME} workspace, SpecifyImpedance=on)` + `V-I Measurement` → `Vabc/Iabc ToWorkspace`。`pe_measurement='vi'`，bridge 每步用 V×I 算真实电气 Pe 写入 `Pe_ES{i}` workspace Constant，VSG Port 5 读取。
  - **phase_command 模式**：`absolute_with_loadflow`；IntD IC 改为 `0`（delta 是增量，t=0 时 phAng=init_phang=delta0）。
  ```

- [ ] **Step 2: 在"试过没用的"追加**

  ```markdown
  - ee_lib `IL_specify` AC 相量初流注入（2026-04-17）：DC 求解器把相量当 DC 处理，下一步相位变化后电流需重建，无效。
  - T_ramp 2.0→0.5→0.3s（2026-04-19 前）：无法消除 AC 冷启动瞬态，根因不在 ramp 时长。
  - Route A Continuous EMT（Phase 0 证伪）：Three-Phase Series RLC Branch 无 `SpecifyIC`；Programmable VS `Inport=0` 无法信号驱动相位。
  ```

### Task 7.2：归档原计划

**Files:** Modify `docs/superpowers/plans/2026-04-19-kundur-sps-migration.md`

- [ ] **Step 1: 在原计划顶部插入 SUPERSEDED 标记**

  ```markdown
  > **Status: SUPERSEDED** — 由重写版 `docs/superpowers/plans/2026-04-19-kundur-sps-migration-v2.md` 接管。
  > 本文件的 Phase 0 勘察结论有效，但 Phase 1-7 的 actionable 清单指向已作废的 Route A + PeFb 命令回显路径，不要按本清单执行。
  ```

- [ ] **Step 2: 更新 `docs/superpowers/plans/2026-04-18-kundur-pe-contract-fix.md` 状态行**

  找到状态行，改为：`B6 归档（SPS Phasor 迁移接管，2026-04-19）`

### Task 7.3：最终 Commit

- [ ] **Step 1:**

  ```bash
  rtk git add scenarios/kundur/NOTES.md \
              docs/superpowers/plans/2026-04-19-kundur-sps-migration.md \
              docs/superpowers/plans/2026-04-18-kundur-pe-contract-fix.md
  rtk git commit -m "docs(kundur): record SPS phasor migration completion + archive ee_lib plan"
  ```

---

## Verification 总览

七层全通过 = 迁移完成：

1. **Config 层**：`pytest -k "kundur_config" -v` 全绿（vi/absolute_with_loadflow/init_phang/delta0_deg）
2. **Build 层**：`simulink_run_script` 无错；`simulink_compile_diagnostics` 无 error
3. **参数层**：`simulink_query_params block_path=powergui` → `SimulationMode=Phasor, frequency=50`
4. **拓扑层**：`simulink_trace_port_connections` 3 条母线确认每相 source→load 闭环
5. **Warmup 层**：`probe_warmup_trajectory.m` → `PASS`（t=10ms omega≈1.0，Pe_vi≈Pe_ref）
6. **Bridge 层**：`validate_phase3_zero_action.py` → `VERDICT: PASS`
7. **Training 层**：`harness_train_smoke_start kundur 1ep` 完成无 NaN

---

## 回滚方案

**Phase 2-5 中途卡住**：`rtk git checkout HEAD -- scenarios/kundur/simulink_models/build_powerlib_kundur.m` 单独回滚 build 脚本；Phase 1 的 config/test 改动保留（对所有 phasor 路线都有效）。

**Phase 6 验证失败但架构大致正确**：按 Task 6.2 诊断路径逐项排查；只在无法定位时回滚到 Phase 5 末的 commit。

---

## 预估时间

| Phase | 工作量 | 累计 |
|---|---|---|
| 1 Config + Test | 0.5 天 | 0.5 |
| 2 Build 结构骨架 | 1.0 天 | 1.5 |
| 3 源替换 G/W | 1.0 天 | 2.5 |
| 4 VSG ES1-4 | 1.0 天 | 3.5 |
| 5 网络 + init | 0.5 天 | 4.0 |
| 6 Verification | 0.5 天 | 4.5 |
| 7 NOTES + 归档 | 0.5 h | 4.6 |
