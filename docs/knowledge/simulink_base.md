# Simulink 建模基础知识库

> **创建/修改 .slx 或 build 脚本前必读** — 静默失败类错误（Simulink不报错但结果不对）

## 分类规则
- **本文件（base）**：Simulink 静默接受错误值，不报错，只是结果不对 → 必须提前知道
- **simulink_debug.md**：有明确 error message 或 build 失败，可通过错误信息检索

---

## 0. 建模工作流原则（MathWorks 官方推荐）

**增量开发**：不要一次写完整个 build 脚本再跑。每加一个组件就验证一次，出错立刻定位。

**加块后自动整理布局**：
```matlab
Simulink.BlockDiagram.arrangeSystem('modelName')
```
每次 `add_block` 完一批 block 后调用，保持模型可读，便于调试。

**标准 Simscape 库路径**（`add_block` 第一参数前缀）：
| 库 | 路径前缀 | 内容 |
|---|---|---|
| 基础机械/电气 | `fl_lib` | Inertia、MechRef、Electrical Reference 等 |
| 传动系统 | `sdl_lib` | Gear、Clutch、Shaft 等 |
| 信号转换 | `nesl_utility` | Simulink-PS Converter、PS-Simulink Converter |

获取端口信息：`simscape.connectionPortProperties(block)` → 返回 Name/Label/ConnectionType

**连线前必须检查 ConnectionType 一致**：两端端口的 `ConnectionType` 不匹配 → `simscape.addConnection` 报错。连线前用 `connectionPortProperties` 查两端类型，确认一致再连。

**每个 Simscape 网络必须有 Solver Configuration block**：缺少则仿真失败。`Solver/port` 连接到网络中任意一个节点即可。

**LLM Simulink 建模失败分布**（SimuAgent, Warwick, 2026 — 1400 个任务统计）：

| 失败类型 | 占比 | 本知识库对应章节 |
|---|---|---|
| 拓扑/连接错误（端口名、域不匹配、方向错） | 33.9% | §0 ConnectionType + §1 add_line |
| Block 选错（相似名、库路径错、缺 Solver） | 28.5% | §0 库路径表 + §7 端口映射 |
| 参数遗漏/拼错/单位错 | 17.7% | §2 单位陷阱 + §6 参数名 |
| 过早终止 | 12.5% | CLAUDE.md 3 轮规则 |
| 上下文超限 | 7.3% | feedback_matlab_efficiency |

> 连接 + Block 选择 + 参数 = 80.1%，本知识库重点覆盖这三类。

---

## 1. ee_lib 带 `~` 端口 block — `add_line` 全部无效

带 `~` 的 block（SM、Transformer、Sensor 等）是 composite port，`add_line` 静默失败或报 domain mismatch。

**正确做法：**
```matlab
% 1. add_block 后立刻设 port_option（任何连线之前）
set_param([mdl '/SM1'], 'port_option', 'ee.enum.threePhasePort.expanded');

% 2. 查询实际端口 Name
props = simscape.connectionPortProperties([mdl '/SM1']);

% 3. 用 Name 字符串连线（物理域全部走这里）
simscape.addConnection([mdl '/SM1'], 'a', [mdl '/Bus'], 'a');

% 纯 Simulink 信号仍用 add_line
add_line(mdl, 'wRef/1', 'S2PS/1');
```

**替代方案**：GUI 建拓扑模板，代码只做 `set_param` 参数修改。物理结果完全相同，规避所有连线问题。

**已验证可全代码建模的 block**：CVS · TL · WyeLoad · RLC · PSensor · CB

---

## 2. 单位陷阱（静默失败，无任何警告）

| Block | 参数 | 正确单位 | 常见错误 | 后果 |
|-------|------|----------|----------|------|
| ee_lib RLC (Three-Phase) | L | **H（亨利）** | 误用 mH | 阻抗大 1000 倍，P_e ≈ 0 |
| ee_lib TL (Three-Phase) | L | mH/km | — | 与 RLC 不同，注意区分 |
| ee_lib SM Round Rotor | VRated | **line-line RMS (V)** | 用峰值相电压 | 电压错 √(2/3) 倍 |
| ee_lib Load Flow Source | VRated | **峰值线-地 (V)** | 与 SM 混淆 | 约定不同，不能套用 |

验证量级：`get_param(block, 'DialogParameters')` 查参数名；看 block 默认值确认单位。

---

## 3. CVS 架构 — 不支持 load flow（设计限制）

CVS 只有 `input_option` + `FRated`，Load Flow Solver 无法约束它。

**影响**：P_ref/P_e 初始不匹配 → 启动振荡，无法自动求稳态初始条件。

**解法**：MATPOWER 外部潮流 → 手动设置各机初始角度和 P/Q。

---

## 4. SM 机械域 — 转子悬空导致 IC 不收敛

```
SM/C → MechRef             （机壳接机械地）
SM/R → TorqueSource/R      （转子接扭矩源）
TorqueSource/C → MechRef   （扭矩源另一端也接机械地）
```

**错误接法（静默物理错误）**：
- `SM/C` 和 `SM/R` 接同一 MechRef → 转子被锁死，不能旋转，仿真跑完但物理错误

---

## 5. kundur_vsg.slx 仿真模式

必须：**Phasor + Fixed-step ode4**。不能改为连续求解器或可变步长。

---

## 6. 已验证参数名（直接用）

| Block | 参数名 | 单位 | 注意 |
|-------|--------|------|------|
| RLC (Three-Phase) | `R`, `L`, `component_structure` | Ω, **H** | L 不乘 1000 |
| TL (Three-Phase) | `R`, `L`, `Cl`, `length`, `freq` | Ω/km, **mH/km**, nF/km, km, Hz | — |
| Wye-Connected Load | `P`, `Qpos`, `VRated`, `FRated`, `parameterization`, `component_structure` | W, var, V, Hz | 不是 p/q |
| CVS (Three-Phase) | `input_option` | 数字 `'1'`/`'2'` | 字符串格式触发 warning |

不确定参数名：`get_param(block, 'DialogParameters')`

---

## 7. SM Round Rotor 端口映射（expanded 模式，9个端口）

| Name | 域 | 连接对象 |
|------|----|----------|
| `C` | mechanical.rotational | MechRef/W（机壳） |
| `R` | mechanical.rotational | TorqueSource（转子轴） |
| `a`, `b`, `c` | electrical | 母线 / TL |
| `fd_p`, `fd_n` | electrical | 励磁 DC 源 |
| `n` | electrical | GND（中性点） |
| `pu_output` | 物理信号输出 | PS2S（可选量测） |

---

## 8. SM 初始化方法选择

| 场景 | 方法 | 关键参数来源 |
|------|------|-------------|
| 全网络仿真 | `steadystate` + `source_type=Swing/PV` | MATPOWER 潮流结果（Vmag0, Vang0, Pt0, Qt0） |
| 单机调试 | `electrical` | 手动设 Vmag0, Vang0（必须 > 0），需接真实负载 |
| 快速验证 SM 能跑 | `electrical` + 小阻性负载（1 MW） | P=Q=0.001 pu，V=1 pu |

IC 不收敛三个已知原因（不是 bug）：Vmag0=0 · 阻尼绕组电阻=Inf（用 1e6） · 单机无负载

---

## 9. Kundur 四机系统 G1-G3 参数（Table 12.4）

| 参数 | G1/G2 | G3 | 单位 |
|------|-------|----|------|
| H | 6.5 | 6.175 | s |
| Sn | 900 | 900 | MVA |
| Vn | 20 | 20 | kV |
| fn | 50 | 50 | Hz |
| Xd / Xq | 1.8 / 1.7 | 同左 | pu |
| X'd / X'q | 0.3 / 0.55 | 同左 | pu |
| X''d = X''q | 0.25 | 同左 | pu |
| Td'0 / Tq'0 | 8.0 / 0.4 | 同左 | s |
| Ra / Xl | 0.0025 / 0.2 | 同左 | pu |

G1 = Swing bus，G2/G3 = PV bus

---

## 10. SM 惯量不在 SM block 内部

SM Round Rotor **没有 `H` 参数**。惯量通过外部 Inertia block 挂在转子轴上：

```
SM/R → Inertia/I → TorqueSource/R → MechRef
```

Inertia block 路径：`fl_lib/Mechanical/Rotational Elements/Inertia`
Mechanical Rotational Reference 路径：`fl_lib/Mechanical/Rotational Elements/Mechanical Rotational Reference`

**常见错误**：在 SM 参数里找 `H` 或 `Inertia` → 不存在 → 浪费探索轮次。正确做法是在外部 Inertia block 上设置 `inertia` 参数（单位 kg·m²，需要从 H(s) 换算：`J = 2 * H * Sn / (2*pi*fn)^2`）

## 12. 建模 Spec 文档（意图记录，建模前必须存在）

**为什么**：MCP 工具只能告诉 Claude"现在是什么"，无法告诉"应该是什么"。没有 spec，语义错误（端口未连、子系统缺 block）只有跑仿真才能发现。

**位置**：`scenarios/{topology}/simulink_models/{model}_spec.md`

**格式模板**：
```markdown
# {model}.slx Spec
系统：{Kundur/NE39}，Phasor，频率：{50/60}Hz

## 子系统 checklist
| 路径 | 必要 block 类型 | 关键参数约束 | 状态 |
|------|----------------|------------|------|
| model/VSG_ES1 | SwingEq, Constant(M0), Constant(D0), CVS | M0_val_ES1, D0_val_ES1 | ✅ |
| model/VSG_ES2 | 同上 | M0_val_ES2, D0_val_ES2 | ⬜ 未建 |

## ToWorkspace 信号（训练必须）
- omega_ES{1-N}, P_out_ES{1-N}, delta_ES{1-N}

## 已知限制
- CVS 不支持 load flow，初始角度需 MATPOWER 手动设置
```

**使用方式**：
- Phase 0 开始前：读 spec 了解现状；如果 spec 不存在，先创建再建模
- Phase 1 每段脚本后：对比 spec checklist，用 MCP inspect 验证刚建的部分是否打勾
- 遇到无法解决的错误：查 spec 判断已建部分是否仍正确，决定继续还是退出
- 完成一个子系统：更新 spec checklist（⬜ → ✅）

---

## 11. RL 分段仿真：FastRestart 是唯一可行方案（2026-04-04 验证）

**背景**：RL 训练中每个 control step 需要修改 M/D 参数并续接 Simscape 物理状态。

**SaveCompleteFinalSimState 方案为何不可用**：
- checksum 计算包含所有参数的**求值结果**（不只是模型结构）
- 任何参数值变化（包括 `setBlockParameter` 和 `setVariable` 修改 Constant 块）都会使 checksum 失配
- 错误：`无法加载完整工作点，因为该模型不同于生成工作点的模型`

**正确方案：FastRestart**：
- 状态保留在 MATLAB 内存，无 checksum 机制
- Constant 块 Value 改为 workspace 变量名（如 `'M0_val_ES1'`）
- 用 `SimulationInput.setVariable` 更新变量值（run-time tunable，不触发重编译）
- **关键约束**：FastRestart 激活后 `StartTime` 不可改，只能改 `StopTime`
- **Episode reset**：调 `set_param(mdl,'FastRestart','off')` 停止，再重启 warmup（StartTime=0）

```matlab
% 每步（step）：只改 StopTime
simIn = Simulink.SimulationInput(mdl);
simIn = simIn.setModelParameter('StopTime', num2str(t_stop,'%.6f'));
simIn = simIn.setModelParameter('FastRestart', 'on');
simIn = simIn.setVariable('M0_val_ES1', new_M);
sim(simIn);  % 自动从上次停止时刻续接

% Episode reset（warmup）：先 off 再 on
set_param(mdl, 'FastRestart', 'off');
simInW = Simulink.SimulationInput(mdl);
simInW = simInW.setModelParameter('StartTime','0','StopTime','0.01','FastRestart','on');
sim(simInW);
```


## 13. Dynamic Load — 两种方案（2026-04-09/14 验证）

### 方案 A（已实现）：单相 `Dynamic Load` × 3 + Phase Splitter
**库路径**: `ee_lib/Passive/Dynamic Load`（通过 `load_type` 切换 AC/DC）

**AC 模式端口**（`load_type = 'ee.enum.dc_ac.ac'`，LConn=3, RConn=1）：
| 端口 | 类型 | 含义 |
|------|------|------|
| LConn1 | 电气 + | 相线端（来自 Phase Splitter RConn1/2/3） |
| LConn2 | Physical Signal 输入 | 有功功率 P（W/phase） |
| LConn3 | Physical Signal 输入 | 无功功率 Q（var/phase） |
| RConn1 | 电气 - | 中性线端（接 GND） |

**三相挂载**：Phase Splitter（handle-only）+ 3 个单相 DynLoad（A/B/C）；每相独立 GND。
Phase Splitter LConn1 可用 `add_line` / `do_wire_ee`（标准复合端口，非 ~ 型）。

### 方案 B（推荐，待验证参数名）：三相 `Dynamic Load (Three-Phase)`
**库路径**: `ee_lib/Passive`（R2025b 已移至此路径）
**端口**：
| 端口 | 类型 | 含义 |
|------|------|------|
| `~` (LConn1) | 复合三相电气端口 | 直接连 bus（无需 Phase Splitter） |
| `P` | Physical Signal 输入 | 三相总有功功率（W） |
| `Q` | Physical Signal 输入 | 三相总无功功率（var） |

**启用外部 PQ 控制**：`set_param(block, '???', '???')` — 参数名待在 MATLAB 中查询：
```matlab
params = get_param([mdl '/DynLoad3ph'], 'DialogParameters');
disp(fieldnames(params));  % 找 'External control of PQ' 对应的参数名
```
**优势**：无 Phase Splitter，模型更简洁，直接 `do_wire_ee` 连 bus。

**关键参数**：
- `load_type = 'ee.enum.dc_ac.ac'`
- `f0 = '50'`, `f0_unit = 'Hz'`
- `Vrms_ini = num2str(Vbase/sqrt(3))`, `Vrms_ini_unit = 'V'`
- `tau = '0.05'`, `tau_unit = 's'`（50ms — **不要用 0.001s**，见下方性能陷阱）

**性能陷阱 — Dynamic Load 导致仿真极慢（2026-04-09）**：
tau=0.001s 使变步长求解器步长塌缩至 ~ps 级（femtosecond steps），0.5s warmup 需 4000 秒。
**修复**：① tau ≥ 0.05s；② SolverConfig 启用本地固定步长求解器（见 §14）。

**S2PS Converter InputFilterTimeConstant**：Dynamic Load 专用 S2PS 设为 0.02s（匹配 LocalSolverSampleTime），否则仍然引入 1ms 级刚性。

**Phase Splitter 只能 add_block by handle**（block 名含 '&'，字符串路径失效）：
```matlab
h = find_system('ee_lib', 'RegExp', 'on', 'SearchDepth', 8, 'Name', '.*Phase.*Split.*');
ph_splitter_h = get_param(h{1}, 'Handle');
add_block(ph_splitter_h, [mdl '/PhSplit_1'], ...);
```
Phase Splitter 端口：LConn1=composite 输入，RConn1/2/3=相 A/B/C 个体输出。

**Phase Splitter 连线方式（2026-04-14 验证）**：
- LConn1（composite 3ph 电气端口）：**可用 add_line / do_wire_ee** — 同类型为 CB/WyeLoad，不是 ~ 型端口，不需要 simscape.addConnection
- RConn1/2/3（单相电气端口）：可用 add_line 连到 DynLoad LConn1
- 禁止 add_line 的仅限 ~ 端口（SM、Transformer 等混合域端口）

**FastRestart 中途更换 P 值**：
```python
bridge.apply_disturbance_load('TripLoad1_P', 0.0)   # 下次 sim() 生效，无拓扑变化
```
Constant 块的 Value 字段是 Simulink 调优参数，不经 Simscape 编译→FastRestart 可变。

## 14. SolverConfig 本地固定步长求解器 — Dynamic Load 性能修复（2026-04-09）

**问题根因**：Dynamic Load (AC) + Phase Splitter 产生代数环，变步长 ode23t 步长塌缩至 femtosecond 级。即使 Dynamic Load 断电（P=0），速度仍然极慢 → 刚性来自网络约束方程，非功率非线性。

**解法：启用 Simscape 本地固定步长求解器**（与外层 ODE 解耦，彻底绕过刚性）：
```matlab
set_param([mdl '/SolverConfig'], 'DelaysMemoryBudget', '4096');  % 须 ≥ 1024，否则编译报内存不足
set_param([mdl '/SolverConfig'], 'UseLocalSolver',    'on');
set_param([mdl '/SolverConfig'], 'DoFixedCost',       'on');
set_param([mdl '/SolverConfig'], 'LocalSolverSampleTime', '0.02');  % 一个 50Hz 周期
set_param([mdl '/SolverConfig'], 'MaxNonlinIter',     '5');
set_param([mdl '/SolverConfig'], 'FilteringTimeConstant', '0.02');
```

**效果**（R2025b Kundur 四机系统）：
| 配置 | 0.5s warmup 实测 |
|------|-----------------|
| 变步长（默认）+ Dynamic Load | >4000 s（不可用） |
| 固定步长 T=0.02s | **~2.8 s** |

**注意**：LocalSolverSampleTime=0.02s（50Hz 基频周期）会通过 Backward Euler 重度衰减 50Hz 电气振荡，但机械频率动态（时间常数 >500ms）完整保留。VSG 训练场景下可接受。

---

## 15. 假设 API 四步验证（用前必查，不假设参数/路径存在）

任何不确定的 block 路径、端口名、参数名，**先用这 4 条命令查，再写建模脚本**：

```matlab
% 1. 确认 block 存在且类型正确
get_param([mdl '/BlockName'], 'BlockType')

% 2. 查 block 的信号端口（Simulink 信号域）
get_param([mdl '/BlockName'], 'PortConnectivity')

% 3. 查物理域端口名 + ConnectionType（Simscape 连线前必查）
simscape.connectionPortProperties([mdl '/BlockName'])

% 4. 查所有参数名（set_param 之前必查，R2025b 名称常与文档不符）
get_param([mdl '/BlockName'], 'DialogParameters')
```

**R2025b 已知路径变更对照（直接用，无需再探索）**：

| Block | 旧路径 / 旧参数名 | R2025b 正确值 |
|-------|------------------|--------------|
| Breaker | `TransitionTimes` | `SwitchTimes` |
| Breaker | `InitialState = '[1 1 1]'` | `'open'` 或 `'closed'` |
| Breaker | `SnubberResistance = 'inf'` | `'1e6'` |
| Breaker | `SnubberCapacitance = '0'` | `'inf'` |
| Phase Splitter | `add_block('ee_lib/...', ...)` 字符串路径 | **必须用 handle**（block 名含 '&'）→ 见 §13 |
| Dynamic Load (single-phase) | 库路径 | `ee_lib/Passive/Dynamic Load` |
| Dynamic Load (three-phase) | 库路径 | `ee_lib/Passive/Dynamic Load (Three-Phase)` |

**Dynamic Load（单相 AC 模式）端口名最终答案**（已验证，无需再探索）：

| 端口 | 类型 | 含义 |
|------|------|------|
| `LConn1` | 电气 + | 相线（来自 Phase Splitter RConn1/2/3） |
| `LConn2` | PS 输入 | 有功功率 P（W/phase） |
| `LConn3` | PS 输入 | 无功功率 Q（var/phase） |
| `RConn1` | 电气 - | 中性线（接 GND） |

---

## 16. 重命名不完整防护（grep 先查 + replace_all）

修改 block 名、变量名、信号名之前：

```bash
# Step 1: grep 找出所有引用点（.m 脚本 + Python 配置 + bridge）
grep -rn "旧名称" scenarios/ engine/ slx_helpers/

# Step 2: Edit 工具用 replace_all=true 一次性替换
# Edit(file, old_string="旧名称", new_string="新名称", replace_all=True)
```

**规则**：
- 不能只改 build 脚本忘记改 bridge/config（静默失败：build 成功但训练读不到信号）
- `vsg_step_and_read.m` 里的 `sprintf('M0_val_ES%d', idx)` 和 build 脚本里的 `sprintf('M0_val_ES%d', i)` 必须字符串模板一致
- 改完后用 `harness_model_diagnose` 验证信号路径，不要人工核对

---

## 17. Kundur workspace 初始化清单（test sim 前必须 assignin）

运行任何测试仿真前，必须确保 MATLAB base workspace 中存在以下变量：

```matlab
% Per-agent (i = 1..4)
for i = 1:4
    assignin('base', sprintf('M0_val_ES%d', i), 12.0);   % VSG_M0 (p.u.·s²)
    assignin('base', sprintf('D0_val_ES%d', i), 3.0);    % VSG_D0 (p.u.)
    assignin('base', sprintf('Pe_ES%d',    i), 1.87);    % 初始电功率 (p.u. on VSG base)
    assignin('base', sprintf('phAng_ES%d', i), 0.0);     % 初始相角命令 (deg)
    assignin('base', sprintf('wref_%d',    i), 1.0);     % 角频率参考 (p.u.)
end

% Global disturbance load
assignin('base', 'TripLoad1_P', 248e6 / 3);   % Bus14 额定负荷 W/phase（episode 开始时接入）
assignin('base', 'TripLoad2_P', 0.0);          % Bus15 初始断开（扰动时再接入）
```

**新增 workspace 变量时同步更新此清单**（否则他人/下次对话的 test sim 静默失败）。
> build 脚本结尾的 `% === Workspace init ===` 节已包含上述 assignin，直接跑完整 build 即可。

---

## 15. Build Script 编写防错规则（2026-04-14 总结）

### 错误分类

本次 Kundur build script 迁移（breaker → Dynamic Load）共出现 4 次 build 失败，归为两类：

| 类 | 错误示例 | 根因 |
|---|----------|------|
| **A：假设 API 未验证（3次）** | `built-in/Ramp` 不存在；`DynLoad_Trip1/P` 端口名错误 | 凭记忆/习惯写了 block 路径或端口名，未在 MATLAB 确认 |
| **B：重命名不完整（1次）** | `dynload_lib` 未识别（已改名为 `dynload3ph_lib`，fprintf 漏改） | 编辑时只改了定义处，未 grep 全部使用处 |

### A 类防范：写 API 调用前先验证

**规则：build script 里每一个新 block 路径 / 端口名 / 参数名，必须先在 MATLAB 确认存在，再写入脚本。**

```matlab
% ① 验证 block 路径是否存在
find_system('simulink', 'SearchDepth', 3, 'Name', 'Ramp')
% → 如果为空，说明路径错，需用 find_system 重新查

% ② 验证端口名（Simulink 信号域）
get_param('modelName/blockName', 'PortConnectivity')
% → 输出 struct array，每个 .Type 字段就是端口名（LConn1/LConn2/RConn1 等）

% ③ 验证 Simscape 物理域端口名
simscape.connectionPortProperties('modelName/blockName')
% → 输出 Name/ConnectionType，用于 simscape.addConnection

% ④ 验证参数名是否存在
fieldnames(get_param('modelName/blockName', 'DialogParameters'))
% → 输出该 block 所有可 set_param 的参数名
```

**已确认 R2025b 易错路径（不要凭记忆用，以 find_system 结果为准）：**

| 错误路径 | 正确路径 |
|----------|----------|
| `built-in/Ramp` | `simulink/Sources/Ramp` |
| `built-in/Step` | `simulink/Sources/Step` |
| `built-in/Constant` | `built-in/Constant` ✓（这个没变） |

**Dynamic Load (Three-Phase) R2025b 已验证端口名（无需再探索）：**
- `LConn1` = 三相复合电气端口（接 bus）
- `LConn2` = P 物理信号输入（W/phase）
- `LConn3` = Q 物理信号输入（var/phase）
- 无 "External control of PQ" 参数，P/Q 端口始终存在，无需 enable

### B 类防范：重命名必须 grep 全文

**规则：在 build script 里重命名任何变量前，先 grep 全部使用处，用 `replace_all=true` 或逐个确认。**

```bash
# 重命名前先确认所有出现位置
grep -n "dynload_lib" build_powerlib_kundur.m
```

Edit 工具用 `replace_all=true` 可一次性替换全文所有出现，避免漏改。

### 测试 sim 前的 workspace 初始化清单

build script 末尾的 test sim（Step 12）调用 `sim()` 前，必须 `assignin` 所有 workspace-backed Constant 的变量：

| 变量名 | 来源 block | 默认值 |
|--------|-----------|--------|
| `M0_val_ES1` … `M0_val_ES4` | `VSG_ESx/M0` Constant | `VSG_M0 = 12.0` |
| `D0_val_ES1` … `D0_val_ES4` | `VSG_ESx/D0` Constant | `VSG_D0 = 3.0` |
| `TripLoad1_P` | `C_P_Trip1` Constant | `248e6/3` W/phase |
| `TripLoad2_P` | `C_P_Trip2` Constant | `0.0` |

新增 workspace-backed Constant 时，同步更新此表。
