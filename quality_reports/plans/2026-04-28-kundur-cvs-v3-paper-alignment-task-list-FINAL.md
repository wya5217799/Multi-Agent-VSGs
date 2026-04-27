# Kundur CVS v3 — 彻底 Paper-Alignment 任务清单 (FINAL)

**Date:** 2026-04-28
**Purpose:** 描述-only 任务清单 (无执行细节)。当前 v3 现状 + 目标状态
+ paper PRIMARY 依据。一次性付清, 之后 modeling layer 永久不动。
**适用范围:** Kundur 物理模型层, 不涉 RL training / reward / SAC /
buffer / paper_eval。
**Source PRIMARY:**
- `C:/Users/27443/Desktop/论文/high_accuracy_transcription_v2.md`
- v3 PRIMARY 源码 + MCP 查询 (本系列 session)

---

## 0. Paper 态度回顾 (本任务清单的依据)

| 立场 | 行号 | 原文 | 含义 |
|---|---|---|---|
| 简化原则 1 | line 261-263 | "this paper mainly studies the relatively slow dynamics of the electromechanical transient. Therefore, the dynamics of the inner loop can be neglected" | 内环全部忽略 |
| 简化原则 2 | line 277 | "Assuming that the voltage magnitudes are constant" | V 幅值假设恒定 |
| 简化原则 3 | line 265 | "considering the purely inductive lines" | analytical 假设纯感性 (sim 不强求) |
| SG 参数源 | line 891-892 | "parameters of the generators can be obtained from the classic Kundur two-area system [49]" | 仅 SG 数值参数从 [49], 非全套模型 |

**结论:** paper 要的是**极简化模型** — swing eq + 恒 V 源 + 网络 + 负
荷。任何 inner-loop / V 反馈 / turbine 动力学 / EMT 复杂度都**违背
paper 立场**。

---

## 1. 必须修改的 3 个任务

### Task 1 — W2 风电场接入位置

**Paper 要求 (PRIMARY 依据):**
- line 894: "100 MW wind farm is **connected to bus 8**"

**v3 现状 (PRIMARY 依据):**
- `build_kundur_cvs_v3.m` line 118 line_def: `'L_8_W2', 8, 11, 1, R_short, L_short, C_short`
- `build_kundur_cvs_v3.m` src_meta (line 425+): `'W2',  11, 'pvs', ...`
- PVS_W2 物理上在 Bus 11 节点, 经 1-km 短 Π-line 接 Bus 8
- `kundur_ic_cvs_v3.json`: 含 bus 11 voltage / angle 项 (16 bus 总数)
- `compute_kundur_cvs_v3_powerflow.m`: NR 含 bus 11

**目标状态:**
- W2 直接物理接 Bus 8
- 删除 bus 11 中转节点
- 删除 L_8_W2 短 Π-line
- 系统总 bus 数 16 → 15

**不影响:**
- 其他 wind / SG / ESS / load / shunt / line / solver
- env / config / agents / reward / SAC

---

### Task 2 — LoadStep 1 IC 与方向

**Paper 要求 (PRIMARY 依据):**
- line 993: "Load step 1 ... represents the **sudden load reduction
  of 248 MW at bus 14**"
- "reduction" 语义: pre-existing 248 MW load **突然断开** (= 跳闸)
- 等价 freq UP

**v3 现状 (PRIMARY 依据):**
- NR (`compute_kundur_cvs_v3_powerflow.m`): bus 14 load = **0 MW**
- `kundur_ic_cvs_v3.json`: `vsg_pm0_pu = [-0.369]·4` (ESS 处于 absorb
  模式, 因为系统少了 248 MW 负载, 多余功率被 ESS 吸收)
- `kundur_cvs_v3_runtime.mat`: `Pm_<i> = -0.369` sys-pu
- env LS1 dispatch 当前: 写 `LoadStep_amp_bus14 = 248e6` ⇒ R 接通
  ⇒ 248 MW **新接入** ⇒ freq DOWN (= 错方向)
- Phase A++ 加 CCS injection 路径 `LoadStep_trip_amp_bus14 = X` 反
  方向修补, 但**只是 negative-load 注入, IC 不一致**

**目标状态:**
- NR 时 bus 14 含 248 MW pre-engaged load
- 系统总负载 967 + 1767 + **248** + 0 = 2982 MW
- ESS Pm0 重派后约从 -0.369 翻号到 ~+0.144 sys-pu (ESS 由 absorb 转
  generate, 平衡新增 248 MW 负载)
- env LS1 dispatch 改为: 写 `LoadStep_amp_bus14 = 0` ⇒ R 跳到 1e9 ⇒
  248 MW **跳出** ⇒ freq UP (paper-faithful)
- LS2 (bus 15) **不变**: 当前 `LoadStep_amp_bus15: 0 → 188e6` 已是
  paper "sudden increase" 语义 ✓

**Phase A++ CCS 路径处置:**
- Task 2 后 LS1 主线机制改用 IC 预接 + 跳出, **不再依赖** CCS injection
- CCS 路径**保留**作 alternate test mode, 不删 (零成本)

**不影响:**
- build script (机制不变, 仅 IC 数值变 → runtime.mat 处理)
- .slx (不重 build)
- 其他 SG / ESS / wind / load / shunt / line
- LS2 任何环节

**强 PRIMARY 警示:**
- ESS Pm0 sign flip 是**重大下游影响**: Phase A++/B/C/D 全部 baseline
  须重测 (因为 swing eq 平衡点变)
- 这是 modeling-layer 完全 paper-aligned 的**一次性代价**, 之后永远不
  再翻

---

### Task 3 — Action range Q7 单位歧义文档化

**Paper 要求 (PRIMARY 依据):**
- line 938-939: "The parameter range of inertia and droop for each
  energy storage is from **−100 to 300** and from **−200 to 600**,
  respectively"
- line 250 Eq.1: `H·ω̇ + D·ω = u − P` — **无 `2` 系数, 无 `ω_s`,
  H 单位未明示** (Q7 in fact-base, 未解)

**v3 现状 (PRIMARY 依据):**
- `scenarios/config_simulink_base.py`: `DM_MIN = -3, DM_MAX = +9,
  DD_MIN = -1.5, DD_MAX = +4.5`
- 项目工作假设 (推断, 非论文事实): H_paper = 2·H_code (M=2H 经典电
  机形式)
- Phase C 实证: ΔM=-30 / ΔD=-15 已撞物理 floor (M_FLOOR=1, D_FLOOR=0.5)
- Phase C verdict: L0 (= 当前 ΔM=[-3,+9] / ΔD=[-1.5,+4.5]) 是唯一物
  理可行的 ladder

**目标状态:**
- 不改 `DM_MIN/DM_MAX/DD_MIN/DD_MAX` 数值常量
- 新增独立文档 (`docs/paper/action-range-mapping-deviation.md` 或类
  似) 显式声明:
  - paper line 938-939 字面值 ΔH=[-100,300]/ΔD=[-200,600]
  - paper Eq.1 H 单位未给 (Q7)
  - paper 未给 H_es,0 baseline 数值
  - 项目 M=2H 假设是工程推断 (非 paper 事实)
  - Phase C 实证更宽 ladder 撞物理 floor
  - 当前 v3 范围是 documented deviation, 在 Q7 解决前不强行采纳 paper
    字面值

**不影响:**
- 任何 build / .slx / NR / IC / runtime.mat
- 任何 env / config 数值
- 任何 RL / reward / SAC

---

## 2. 永久不修改清单 (paper 反对加这些)

按 paper 立场, **永远不加**这些复杂度。原 audit 的"deviation"标签
**全部撤销**, 这些项是**paper-aligned 的 feature, 不是 bug**。

### 同步发电机 (SG) 侧

| 不加项 | Paper 反对依据 |
|---|---|
| AVR / Exciter / V regulator | line 277 "V constant"; paper 全文未提 AVR |
| PSS (Power System Stabilizer) | paper 全文未提 PSS |
| Governor servomotor / 时间常数 / 阀位限位 | Eq.1 形式无 governor 动力学 |
| 次暂态 X'' / X_q / 阻尼绕组 | Eq.1 集总形式不含 |
| 励磁机详细模型 | line 277 V constant 与 line 263 内环忽略 |

### 储能 (ESS / VSG) 侧

| 不加项 | Paper 反对依据 |
|---|---|
| Inner V/I 控制环 | line 263 "inner loops neglected" 显式 |
| DC-link 动力学 | 同上 |
| PLL (Phase-Locked Loop) | 同上 |
| Virtual impedance | 同上 |
| 谐波 / PWM 开关动态 | Phasor solver + 慢机电暂态原则 |
| Outer P-Q 控制环 | swing eq Eq.1 已是 outer 控制, 无需再加 |

### 风电场 (Wind) 侧

| 不加项 | Paper 反对依据 |
|---|---|
| Type-3 DFIG 完整模型 | line 277 V constant + line 263 内环忽略 |
| Type-4 PMSG 完整模型 | 同上 |
| 转子单质量动力学 (rotor mass) | paper 不要求 wind 提供 inertia |
| GSC / RSC 控制环 | line 263 内环忽略 |
| MPPT (最大功率追踪) | paper 不提 wind 控制 |
| Pitch control (桨距控制) | 同上 |
| 风速输入 / 气动模型 | paper 用恒功率 / 恒电压简化 |

### 负荷 / 网络侧

| 不加项 | Paper 立场 |
|---|---|
| Const-PQ / ZIP / motor 复杂负荷 | Eq.3 平衡点 linearize 兼容 const-Z (当前) |
| 变压器 T 模型 | paper 完全不提 |
| Π-line 改纯感性 R=0 | line 265 仅 analytical, sim 不强求 |
| 三相不平衡 / 负序 / 零序 | Phasor solver 本身排除 |
| 频率自适应电感 / 容性 | 慢机电暂态原则排除 |

### 数值 / 仿真侧

| 不加项 | Paper 立场 |
|---|---|
| EMT (Electromagnetic Transient) solver | line 261 "slow dynamics" 排除 |
| Variable-frequency / 谐波模型 | Phasor 排除 |
| Continuous solver MaxStep < 0.001s | 慢机电暂态不需要 |

---

## 3. 当前已 paper-aligned 项确认 (无需修改)

这些 v3 PRIMARY 已 match paper PRIMARY, 永久保持。

### 拓扑

| 项 | v3 | Paper PRIMARY |
|---|---|---|
| Modified Kundur 2-area | ✓ kundur_cvs_v3 | line 871, 889 |
| 3 SGs (G1/G2/G3) | ✓ bus 1/2/3 | line 892-893 (G4 替换为 wind, 剩 3) |
| 4 ESS | ✓ ES1/2/3/4 @ bus 12/16/14/15 | line 894 |
| 2 wind farms | ✓ PVS_W1, PVS_W2 | line 890, 894 |
| W1 @ bus 4 | ✓ | line 892 (G4 位置) |

### SG 数值参数

| 项 | v3 | Paper PRIMARY |
|---|---|---|
| SG 容量 | ✓ SG_SN=900 MVA | classic [49] (paper line 891-892) |
| SG H values | ✓ Mg=[13, 13, 12.35] (H=[6.5, 6.5, 6.175]) | classic [49] |
| SG 内部 X | ✓ 0.30 gen-base | classic [49] |

### 模型结构

| 项 | v3 | Paper PRIMARY |
|---|---|---|
| Swing eq | ✓ M·ω̇ = Pm − Pe − D·(ω−1) (Phase D D1+D2 PRIMARY) | Eq.1 |
| SG = 恒 V CVS | ✓ DC Amplitude=VemfG_g constant | line 277 V constant |
| ESS = swing-eq + CVS | ✓ swing 闭合 + CVS, 无 inner loops | Eq.1 + line 263 |
| Wind = PVS 恒压源 | ✓ ACVoltageSource | line 277 V constant + line 263 |

### 负荷 / 网络

| 项 | v3 | Paper PRIMARY |
|---|---|---|
| Load Bus 7 | ✓ 967 MW + 100 Mvar | classic [49] |
| Load Bus 9 | ✓ 1767 MW + 100 Mvar | classic [49] |
| Shunt Bus 7 | ✓ 200 Mvar cap | classic [49] |
| Shunt Bus 9 | ✓ 350 Mvar cap | classic [49] |
| Load 模型 = const-Z | ✓ Series RLC R+L grounded | Eq.3 兼容 |
| Lines = lossy Π | ✓ 18 个 R+L+C lossy | classic [49], paper Eq.2 不强求 sim |

### 扰动

| 项 | v3 | Paper PRIMARY |
|---|---|---|
| LS block bus 14 | ✓ LoadStep_bus14 + LoadStepTrip_bus14 | line 993 "at bus 14" |
| LS block bus 15 | ✓ LoadStep_bus15 | line 994 "at bus 15" |
| LS1 magnitude 248 MW | ✓ Phase B 实证 stable | line 993 |
| LS2 magnitude 188 MW | ✓ Phase B 实证 stable | line 994 |

### 仿真参数

| 项 | v3 | Paper PRIMARY |
|---|---|---|
| Solver Phasor | ✓ powergui Phasor 50 Hz | classic [49] (paper 不指明 solver) |
| Time-domain Simulink + Python | ✓ SimulinkBridge + matlab.engine | line 911-912 |
| Control step 0.2 s | ✓ env DT=0.2 | line 913 |
| Episode time 10 s | ✓ T_EPISODE=10 | line 913 |
| M=50 step/episode | ✓ STEPS_PER_EPISODE=50 | line 884 |

---

## 4. Paper 不指明项 (项目自由度)

paper PRIMARY 没有约束的项, v3 选择合理且 self-consistent。**保持当前**。

| 项 | v3 当前 | Paper 立场 |
|---|---|---|
| Bus 总数 | 16 (Task 1 后 15) | paper Fig.3 implied, 不直接给 |
| ESS 具体 bus 编号 | 12/16/14/15 | "different areas, with loads" 不指明 |
| ESS 容量 | VSG_SN=200 MVA | 不指明 |
| ESS 内部 X | 0.30 vsg-base | 不指明 |
| ESS H_es,0 / D_es,0 | M0=24 (H=12) / D0=4.5 | 不指明 |
| SG D | 5.0 | classic [49]=0; paper 不指明 |
| SG governor R | 0.05 | 不指明 |
| 频率基 | 50 Hz | 不指明 |
| Sbase / Vbase | 100 MVA / 230 kV | 不指明 |
| 线路具体 R/L/C 数值 | classic [49] 标准值 | 引 [49] 但不全列 |
| 通信拓扑 | 2-neighbor ring | 仅 RL 层, 不在物理 |

---

## 5. 总结

### 必须改 (3 项)

| Task | 修改对象 | Paper 依据 | 触动 IC? | 触动 .slx? |
|---|---|---|---|---|
| 1. W2 to bus 8 | build + NR + IC + runtime + .slx | line 894 | YES | YES |
| 2. Bus 14 IC pre-engage 248 MW + LS1 反向 | NR + IC + runtime + env dispatch | line 993 | YES (sign flip) | NO |
| 3. Action range 文档化 | 新增 doc | line 938 + Q7 | NO | NO |

### 永远不改 (15 项)

按 paper 立场反对加复杂度, **永久排除**:

```
SG 侧:    AVR / PSS / Governor servomotor / 次暂态 X'' / 励磁机
ESS 侧:   Inner V/I 环 / DC-link / PLL / Virtual impedance / Outer P-Q 环
Wind 侧:  Type-3 DFIG / Type-4 PMSG / 转子动力学 / GSC/RSC / MPPT / Pitch
负荷侧:   Const-PQ / 变压器 T / 线路改纯感性 / 三相不平衡
数值侧:   EMT solver / 谐波模型
```

### 已对齐 (32 项)

拓扑 + SG 数值 + 模型结构 + 负荷网络 + 扰动机制 + 仿真参数 = 全部
match paper PRIMARY 或 paper-permitted。

### 自由度 (10 项)

paper 不指明, v3 选择合理 self-consistent, **保持当前**。

---

## 6. 一次性付清后的永久状态

执行 Task 1 + Task 2 + Task 3 后:

- Modeling layer (build / .slx / NR / IC / runtime.mat) **永久不动**
- 后续 RL training / reward 调整 / SAC 实验 / paper_eval / 任何 phase
  **不再碰**物理层
- 论文 PRIMARY 关于 Kundur 物理模型的所有要求 v3 完全满足
- 论文 PRIMARY **不要求**的复杂度 v3 永久不加

**"论文有的我们就都有了, 论文不要的我们也不加"** — 这是终态。
