# Kundur CVS Phasor VSG — 工程约束设计文档

**Branch:** `feature/kundur-cvs-phasor-vsg`
**Predecessors:**
- [`quality_reports/audits/2026-04-25_cvs_phasor_feasibility.md`](../../quality_reports/audits/2026-04-25_cvs_phasor_feasibility.md) — SPIKE-LEVEL GO（G3.1/3.2/3.3 PASS）
- [`quality_reports/audits/2026-04-25_cvs_phasor_preflight.md`](../../quality_reports/audits/2026-04-25_cvs_phasor_preflight.md) — Pre-Flight PASS（Q1 多 CVS / Q2 episode + FR / Q3 持久化）
- [`docs/superpowers/plans/2026-04-25-kundur-cvs-rewrite-constraints.md`](../superpowers/plans/2026-04-25-kundur-cvs-rewrite-constraints.md) — 5 天改造约束（main worktree）

**Status:** ACTIVE — 改造期间持续维护，每个 gate 完成后回填证据

**Audience:** 任何在本分支工作的代理 / 工程师

> **TL;DR:** 这份文档把 spike + Pre-Flight 已锁的物理/工程约束固化下来。**违反这些约束会复现已踩过的坑**。改代码前先读完。

---

## 0. 改造范围与边界（不可越界）

### 第一阶段（本分支）只改 Kundur

- ✅ **可改**：新增 `scenarios/kundur/simulink_models/build_kundur_cvs.m` + 新 `kundur_vsg_cvs.slx`、新 `scenarios/kundur/model_profiles/kundur_cvs.json`、新 IC（如需重写）、新 step/warmup .m（profile-dispatched）、bridge.py 加 step_strategy 字段（不改原字段）、新 gate 套件
- ❌ **不可改**：NE39 任何文件、ANDES 路径、reward / observation / action 公式、agent / SAC 网络结构 / 训练超参、`scenarios/contract.py::KUNDUR`、`slx_helpers/vsg_bridge/` 共享层（约束 H3）、Yang fact-base §1-§9

### Gate 推进顺序

```
Gate P1: 4-CVS 模型结构  →  Gate P2: reset/warmup/step/read  →  Gate P3: zero-action smoke
                                                                        ↓
                                                                   ⛔ 不允许直接进入 RL 训练
                                                                   除非 P1+P2+P3 全 PASS
```

每个 Gate 必须有：
- 可复现脚本（`probes/kundur/gates/` 下）
- 简短 verdict 报告（`quality_reports/gates/<date>_<gate_id>.md`）
- 主线代码（仅 Kundur）只在 verdict PASS 后才允许 commit

---

## 1. SPS Phasor + CVS 物理建模契约（HARD）

### H1. CVS 块配置（违反必触发"复信号不匹配"或"FR-nontunable"）

| 参数 | 必须值 | 理由 |
|---|---|---|
| 块路径 | `powerlib/Electrical Sources/Controlled Voltage Source` | SPS native，与 powergui Phasor 共享 SPS-domain（不要用 ee_lib CVS） |
| `Source_Type` | **`DC`** | AC 模式 1-inport 期望 real（块自生相位），动态 complex 信号触发 Mux 不匹配 |
| `Initialize` | **`off`** | 让 inport 完全控制电压相量；on 会让块参 Phase/Frequency 参与初始化，与动态信号路径冲突 |
| `Amplitude` | `Vbase`（230e3 默认） | 仅作为编辑器显示，运行时被 inport 信号覆盖 |
| `Phase` | `0` | 同上 |
| `Frequency` | `0` | DC 模式必须为 0 |
| `Measurements` | `None` | 用独立 Voltage / Current Measurement 块取相量；不要让 CVS 自带测量 goto |

### H2. CVS 输入信号路径（统一性约束）

**所有 driven CVS 的输入端口必须是 complex 信号**，由 `Real-Imag to Complex` 块产生。

```
[swing-eq IntD] -> cos/sin -> Vr_gain * cos / Vi_gain * sin
                    -> [Real-Imag to Complex] -> [SPS CVS inport]
```

**不要混用**：
- ❌ 1 个 CVS 接 complex 信号 + 另 1 个 CVS 接 real Constant → powergui 内部 Mux 类型一致性约束触发
- ✅ N 个 CVS 全部接 RI2C 出来的 complex（已验证 N=2, N=4）

### H3. Infinite bus / fixed-pattern source

- ✅ **优先**用 powerlib **`AC Voltage Source`**（无 inport，纯 fixed-pattern）— 已 G3 验证
- ❌ **不要**用 `Three-Phase Source`（PhaseAngle workspace var 路径，已知 6 次 fix 失败链 — 约束文档 H1 硬禁）
- ❌ **不要**用第二个 driven `Controlled Voltage Source` 接 complex Constant 当 inf-bus（spike 阶段已踩坑：与第一个 CVS 触发 Mux 类型冲突）

### H4. 求解器配置

| 参数 | 必须值 |
|---|---|
| `powergui/SimulationMode` | `Phasor` |
| `powergui/frequency` | `50`（Kundur）|
| `Solver` | `ode23t` |
| `SolverType` | `Variable-step` |
| `MaxStep` | `0.005` 起；后续若发现数值噪声可调 |

### H5. base workspace 数值类型（已踩坑）

**所有从 Python / Bridge 写入 base workspace 的数值必须显式 `double`。**

```python
eng.assignin("base", "M0", float(12.0), nargout=0)  # ✅
eng.assignin("base", "M0", 12, nargout=0)           # ❌ 可能存为 int64
```

或在 MATLAB 端：

```matlab
assignin('base', 'M0', double(12));  % ✅
```

**理由**：powergui 内部 EquivalentModel Mux 在 int64 vs double 间触发 "数据类型不匹配，应接受 int64，但由 double 驱动"（已踩坑，Pre-Flight Q2 修复）。

### H6. Phasor 求解器内部 Mux（不可见但有约束）

powergui Phasor 模式下，求解器把所有 SPS sources 内部聚合到一个隐藏 EquivalentModel/Sources/Mux。这个 Mux 对所有 inport 类型有一致性要求。**符合 H1+H2+H5 即可绕开**，否则错误信息形如：

- `复信号不匹配 / Mux 输入端口 N 应接受 real（complex）的信号`
- `数据类型不匹配 / int64 vs double`

---

## 2. RL Episode 语义契约（已 Pre-Flight Q2 验证）

### E1. Episode 结构

```
for ep in episodes:
    reset_workspace(eng)           # assignin M0/D0/Pm0/delta0 等 base ws 默认
    sim('mdl', 'StopTime', '0.5')  # warmup + step（同一 sim 调用可分段，详见 E3）
    omega_final = read(omega_ts)
    pe_final = read(Pe_ts)
    delta_final = read(delta_ts)
```

### E2. FastRestart 使用规则

| 状态 | 何时 | 代价 |
|---|---|---|
| 首次 sim | `FastRestart='off'`（compile 一次） | ~0.8s（含 compile） |
| 后续 sim | `FastRestart='on'`（复用 compile cache） | ~0.6s（25% 提速）|
| 每次 reset_workspace | 仅改 base ws 数值，**不**翻 FR off | M0/D0 是 base ws Constant 路径，FR-tunable，无 silent ignore |

**FR-nontunable 风险监控**：
- 每次 sim 后检查 `lastwarn` 是否含 `nontunable` / `不可调` / `will not be used` / `新值不会使用`
- 命中任一 → raise 异常或打 hard fail（不要 silent pass）

### E3. Step 内 substep 处理

如需在一个 RL step (DT=0.2s) 内做多个内部 substep：
- ✅ 用同一 `sim('mdl', 'StopTime', '0.2')` 跑完，由 ode23t 自适应步长
- ❌ **不要**多次 `sim` 累加，每次 sim() 重新 compile 或重置 IC，episode 状态会污染

### E4. 跨 Episode 状态隔离

`reset_workspace(eng)` 必须重写**所有**会被 swing eq / CVS 信号链 / FR cache 看到的 base ws 变量：M0, D0, Pm0, Pm_step_t, Pm_step_amp, delta0（IntD InitialCondition 引用）, wn_const, Vbase_const, Sbase_const, Pe_scale, L_H_const。

任何遗漏 = 跨 episode 状态污染（约束文档 R4 风险）。

### E5. Disturbance 注入路径

第一阶段 zero-action smoke 不做 disturbance。后续若加：
- 通过 base ws 数值（如 `Pm_step_t` / `Pm_step_amp` / `dist_amp`）→ Constant block → 信号链
- **不要**用 TripLoad / breaker（FR-nontunable，silent ignore；约束文档 R2/DR-2）

---

## 3. IC 与工作点（待 Gate P1 确认后填）

### 3.1 待解决项

- [ ] 4 VSG 各自的 `delta0_i`：从 NR 潮流求解 — 但 spike 用 SMIB 单 VSG `delta0 = asin(Pm0 * X)` 0.1506 rad；4 VSG 拓扑下需要重做 NR
- [ ] 各 VSG 的 `Pm0_i`：约束文档 D-CVS-6 锁定"4 VSG 同质"（M0=12, D0=3）；Pm0 同样应同质 → 0.5 pu 起点
- [ ] X_line（VSG → 母线 / 母线间）：基于约束文档 §0 DR-1 已 CLOSED，X_vsg_sys = 0.0117 pu（SCL 公式）；线路 X 取 NR refernce
- [ ] R5 Pe 测量路径：固定 `vi`（V×I real-imag → real(V·conj(I)) * 0.5 / Sbase pu）— 已 G3 验证

### 3.2 IC 来源

新建 `scenarios/kundur/kundur_ic_cvs.json`（**不**覆写 `kundur_ic.json`，保留旧 IC 给现有 ANDES / legacy ee 路径）。

### 3.3 warmup 期间 IntD 处理

约束文档 R4：warmup 期间 IntD 漂移会变成 CVS 角度漂移。

第一阶段策略：
- IntD InitialCondition = `delta0_i`（NR 解）
- warmup 期间不冻结积分器，但 warmup 时长设为 **0.2s**（短）+ Pm0 与 IC delta 已平衡 → IntD 漂移应 < 0.01°
- 若 Gate P3 zero-action smoke 显示 IntD 漂移 > 0.5°，再升级为冻结策略（IntD 输入接 0 直到 warmup 结束）

---

## 4. Bridge 集成契约（Gate P2 后再修，不在第一阶段范围）

第一阶段 Gate P1/P2/P3 **不修 bridge.py**。所有 reset/warmup/step/read 通过最小 Python 探针直接 `matlab.engine + assignin + sim + read`（同 `preflight_q2_episode.py` 风格）。

第二阶段（Gate P3 PASS 后）才考虑：
- BridgeConfig 加字段 `step_strategy: 'cvs_signal'`（约束文档 S1）
- 新 step/warmup .m: `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m`、`slx_helpers/vsg_bridge/slx_episode_warmup_cvs.m`（独立文件，**不改**现有 `slx_step_and_read.m` / `slx_episode_warmup.m` —— H3 NE39 隔离）
- `engine/simulink_bridge.py` 根据 `step_strategy` 路由（仅加分支，不删旧路径）

---

## 5. Gate 推进锚点

### Gate P1: 4-CVS 模型结构

**目标**：构造 4 driven CVS + 公共母线（含线路 jX）+ 4 GND + AC inf-bus（如有）+ powergui Phasor，验证编译通过 + 0.5s static sim 通过。

**脚本**：`probes/kundur/gates/build_kundur_cvs_p1.m` 用 MCP 命名工具或 add_block 构建（不带 swing-eq，纯结构验证）

**Verdict 标准**：
- 编译 0 errors / 0 warnings
- 0.5s sim 0 errors / 0 warnings
- 所有 4 CVS 输入信号统一 RI2C complex 路径（无 mixed real/complex）
- 写 `quality_reports/gates/2026-04-25_kundur_cvs_p1_structure.md`

### Gate P2: reset/warmup/step/read

**目标**：在 P1 模型基础上加 swing-eq 信号链（4 套 IntW/IntD/cosD/sinD/RI2C 与 Pe 反馈），验证 Pre-Flight Q2 等价循环（5 ep × FR=on/off + M0/D0 改值生效 + bit-exact 复现）。

**脚本**：`probes/kundur/gates/preflight_kundur_cvs_p2.py`（基于 `preflight_q2_episode.py` 改）

**Verdict 标准**：
- 5 ep 重复 omega/delta/Pe spread = 0
- M0/D0 per-agent 改值生效（FR=on）
- lastwarn 不含 nontunable
- 写 `quality_reports/gates/2026-04-25_kundur_cvs_p2_episode.md`

### Gate P3: zero-action smoke

**目标**：4-VSG zero-action 5 s sim，验证 ω 稳态、IntD 不漂、Pe 与 Pm 一致。

**Verdict 标准**：
- 4 VSG 全部 ω_tail_mean ∈ [0.999, 1.001]（约束文档 Gate 1 子集，缩短到 5 s）
- IntD 全程不触 ±90° 钳位
- 4 VSG 间 ω 同步（max - min < 0.01 pu）
- Pe ≈ Pm0（±5%）
- 写 `quality_reports/gates/2026-04-25_kundur_cvs_p3_smoke.md`

### Gate P4+（暂缓，本分支不做）

P4 Gate 1 全量 30s + dist sweep / P5 Gate 2 训练基线 — 留给约束文档 5 天改造的后续分支或本分支 Phase 2，本设计文档不展开。

---

## 6. 失败信号与回退条件

如果 Gate 推进过程中遇到以下任一，**停手 + 诊断根因**：

| 错误信号 | 根因检查清单 |
|---|---|
| `复信号不匹配 / Mux 输入端口 N 应接受 real` | (1) 是否有任一 CVS 输入接 real Constant？应统一 RI2C complex；(2) Vin_INF 是否误用 `Vbase + 0i`？应改 `Vbase` 实数 |
| `数据类型不匹配 / int64 vs double` | base ws 数值变量是否 `double()` 显式转换 |
| `Mux 端口 K 应接受 int64`（compile 阶段） | 同上 |
| sim() 后 `lastwarn` 含 `nontunable` / `不可调` / `will not be used` / `新值不会使用` | 改值的 ws 变量对应的 block 是否 FR-nontunable；改用 FR-tunable 路径 |
| save → reopen 后行为漂移 | base ws 类型是否被重置；powergui 是否被 .slx baked state 改写 |
| IntD 触 ±90° 钳位 | warmup 期间漂移过大；考虑冻结 IntD 直到 warmup 结束（约束文档 R4） |

如果连续 2 个 Gate 推进失败：abort，回到约束文档 §0 决策门重新评估方向。

---

## 7. 已锁定的设计决策汇总（来自约束文档 §8 + spike + Pre-Flight）

| ID | 决策 |
|---|---|
| D-CVS-1 | CVS 输入 = 复相量（实部+虚部）via Real-Imag-to-Complex |
| D-CVS-2 | IntW/IntD = 内置 Integrator |
| D-CVS-3 | warmup 期间 IntD 不冻结（短 warmup + IC 已平衡），如 P3 漂移大再升级 |
| D-CVS-4 | Pe 测量 = `vi`（V×I real(V*conj(I)) * 0.5 / Sbase pu） |
| D-CVS-5 | T_WARMUP = 0.2s（CVS 不需要 P_ref 斜坡） |
| D-CVS-6 | 4 VSG 同质（M0=12, D0=3, Pm0=0.5）|
| D-CVS-7 | X_vsg_sys = 0.0117 pu（DR-1 已 CLOSED）|
| D-CVS-8 | NE39 不跟进 CVS 改造（H3 强制）|
| D-CVS-9（新增）| Source_Type=DC + Initialize=off 是 driven CVS 唯一合法配置 |
| D-CVS-10（新增）| inf-bus 用 `AC Voltage Source`，不用第二 driven CVS |
| D-CVS-11（新增）| 所有 base ws 数值显式 `double` |

---

## 8. 维护

完成 Gate P1/P2/P3 后回填本文档：
- 各 Gate 的实测数值
- 任何新发现的工程约束
- 任何决策变更（如 D-CVS-3 是否需升级冻结策略）
