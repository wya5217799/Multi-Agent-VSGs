# Simulink Debug 知识库

> **遇到 Simulink bug 时先查这里** — 有 error message 的已知问题，按现象检索

## 使用说明

1. 用**错误信息关键词**在本文件搜索（条目索引见下）
2. 命中 → 照解法处理
3. 未命中 → 走 CLAUDE.md Bug 处理流程（WebSearch 最多 3 轮）
4. 新解法确认后存入本文件，**存完展示给用户确认**
5. 每条记录标注"首次观察版本"（如 `[R2025b]`），含义是"在此版本上确认存在"，不代表"仅限此版本"。升级 MATLAB 时重新验证版本相关条目

## 条目索引（按关键词速查）

| 关键词 | 条目 |
|---|---|
| `set_param` Breaker 参数名不存在 / TransitionTimes | D1 |
| 初始条件未收敛 / IC crash / Vmag0 / 励磁子域悬浮 / Vfd.p.v 与确定值绑定 / 域参考模块 | D2 |
| SM stator composite 无法连线 / add_line domain mismatch / addConnection Cannot add connection | D3 |
| `SynchronousMachineInit.p` crash / 加密文件内部错误 | D4 |
| `MatlabCallError` / eval失败 / 引擎断连 | D5 |

---

## D1. R2025b Breaker 参数名变更 [R2025b]

**现象**：`set_param` Breaker 失败，提示参数名不存在
**原因**：R2025b breaking change，参数名已改
**解法**：
```matlab
SwitchTimes       % 旧名 TransitionTimes（已废弃）
InitialState      % 'open' 或 'closed'（不是 '[1 1 1]'）
BreakerResistance = '0.01'
SnubberResistance = '1e6'   % 不是 'inf'
SnubberCapacitance = 'inf'  % 不是 '0'
```

---

## D2. SM 初始条件不收敛 [R2025b+]

**现象**：仿真报 "初始条件求解未能收敛" 或 IC crash，或错误 `"将变量 'Vfd_Gx.p.v' (电压) 与确定值绑定，例如通过连接适当的域参考模块"`
**原因**（四个已知原因，均不是软件 bug）：
1. `Vmag0 = 0`（未设置或默认算出 0）
2. 阻尼绕组电阻 = Inf（改用大值如 `1e6`）
3. 单机无负载，网络欠定（必须接一个真实负载，哪怕 1 MW 电阻）
4. **励磁回路没有接地参考（最常见于程序化建模）**：`Vfd/p—SM/fd_p—SM/fd_n—Vfd/n` 形成孤立子域，IC 求解器无法锚定绝对电压。错误特征：`"将变量 'Vfd_Gx.p.v' (电压) 与确定值绑定"`

**原因4解法**：对 `Vfd/n` 和 `SM/fd_n` 分别接独立 Electrical Reference（两个 GND 均在同一电气域，物理等价于连接后单点接地）：
```matlab
simscape.addConnection([mdl '/' vfd_name], 'n', [mdl '/' gnd_fd_n_vfd], 'V');
simscape.addConnection([mdl '/' sm_name], 'fd_n', [mdl '/' gnd_fd_n_sm], 'V');
% 注意：不要直接连 Vfd/n → SM/fd_n（两端口均悬浮），必须接 GND
```

**调试工具**：右键 SM → Electrical → Display Associated Initial Conditions

---

## D3. SM 定子 composite port 无法连线（add_line 和 addConnection 均失败）[所有版本]

**现象**：`add_line` → "点输入域不匹配"；`simscape.addConnection(sm,'N',rlc,'N1')` → "Cannot add connection"（即使两端 ConnectionType 均为 `foundation.electrical.three_phase`）
**原因**：SM stator composite port 是 machine class 特殊端口，与 TL/RLC/PSensor 的普通网络 composite port 不兼容，任何程序化连线 API 均拒绝。注意："Three-Phase Assembly/Disassembly" block 不存在，不要搜索。
**解法（已验证流程）**：
```matlab
% 1. 展开 SM
set_param([mdl '/SM1'], 'port_option', 'ee.enum.threePhasePort.expanded');
% 2. 加 Phase Splitter 做 expanded↔composite 桥接
add_block(spl_lib, [mdl '/Spl1'], ...);
% 3. 查 Phase Splitter individual 端口名（运行时）
spl_props = simscape.connectionPortProperties([mdl '/Spl1']);
spl_indiv = {spl_props(~contains({spl_props.Type},'three_phase')).Name};  % 字段是 Type，不是 ConnectionType
% 4. SM a/b/c → Phase Splitter individual
simscape.addConnection([mdl '/SM1'],'a',[mdl '/Spl1'],spl_indiv{1});
simscape.addConnection([mdl '/SM1'],'b',[mdl '/Spl1'],spl_indiv{2});
simscape.addConnection([mdl '/SM1'],'c',[mdl '/Spl1'],spl_indiv{3});
% 5. Phase Splitter composite → RLC（add_line，与其他网络块相同）
add_line(mdl, 'Spl1/LConn1', 'Zgen/LConn1', 'autorouting','smart');
```
→ RLC 下游（PSensor、bus）保持 composite/add_line 不变
→ Phase Splitter lib path：`ee_lib/Connectors & References/Phase Splitter`（find_system 也可查）
→ Phase Splitter 端口布局（R2025b 已验证）：LConn1=composite(~)，RConn1/2/3=individual(a/b/c)
→ 注意：`port_option` 要在 add_block **之后、任何连线之前** 调用，否则端口名仍是 composite 的 'N'

---

## D4. SynchronousMachineInit.p 内部 crash [R2025b]

**现象**：SM 初始化时报加密文件内部错误，stack trace 指向 `.p` 文件
**原因**：机械域端口悬空（`SM/R` 未连），不是 R2025b 软件 bug
**解法**：确保 `SM/R` 接 TorqueSource，`SM/C` 接 MechRef
→ **正确接法详见 simulink_base.md §4**（D4 不重复描述，以 §4 为准）

---

## 接口层错误（matlab_session / simulink_bridge / vsg_helpers）

> 这类错误是 MATLAB/Simulink 抛出后通过 Python 接口冒泡，本质仍是 Simulink 问题。

## D6. SM steadystate 模式 IC 未收敛（多机系统）[R2025b]

**现象**：
```
警告: First solve for initial conditions failed to converge. Trying again with all high priorities relaxed to low.
警告: 对初始条件的第二次求解未能收敛。请在忽略所有变量目标的情况下重试。
警告: 无法满足所有初始条件。
```
方程来源：`round_rotor/base.sscp`，影响所有 G1/G2/G3 同时报错

**原因**：SM steadystate IC 求解器按 block 独立求解。要唯一确定 SM 内态（δ、ψ_d、ψ_q、Vf0），需要 Vmag0 + Pt0 + **Vang0（或 Qt0）**。只提供 Vmag0+Pt0 时，电角度参考不确定 → 求解器两次失败后放弃，采用近似 IC。

**是否有害**：**否。Simulink fallback IC 仍可运行**，仿真动态自行收敛至正确工作点（omega≈1.0）。

**重要**：即使 IC 未收敛，steadystate 模式仍然有效消除了 Zgen.IL 警告（因为 `d/dt=0` 约束仍对电感电流方程生效）。

**解法（优先考虑）**：接受此警告，仿真结果有效。如需完全消除，可尝试在 steadystate `set_param` 中加入 `'Vang0', num2str(V_init_ang)`（但不确定 SM 的 steadystate 模式是否接受该参数；如报 set_param 错误则放弃）。

**验证场景**：Kundur 16-bus，G1（Swing）+ G2/G3（PV），MATPOWER 提供 Vmag0+Pt0，omega_ES1=0.9998 ✅，无 IL 警告 ✅，1s 仿真通过 ✅（2026-04-01）

---

## D5. MatlabCallError / eval() 失败后引擎断连 [所有版本]

**现象**：Python 侧抛 `MatlabCallError`，后续调用全部失败，引擎无响应
**原因**：MATLAB eval() 内部报错导致引擎状态异常
**解法**：`matlab_session.py` 已封装重连逻辑；重连后仍失败则检查 MATLAB 错误原文，按错误信息再查本库其他条目
