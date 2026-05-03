# A1: Vbase 量纲 Forensic

**审计时间**: 2026-05-04
**审计范围**: `LoadStep_trip_amp_busN -> CCS 注入 active power` 换算链
**结论摘要**: 当前实现存在 sqrt(3/2) ≈ 1.2247 倍高估因子（量纲错），外加相位失配导致 cos(Δφ) 衰减。**但两个因子叠加仍不能解释 amp=248e6 信号低于 IC residual 的反常现象——最可能根因是 CCS RConn1 电气接线未完成（悬空）。量纲修正是必要条件但不是充分条件；必须先排查接线。**

---

## 1. 当前公式实际行为

### 1.1 代码链溯源

**Vbase 定义** (build_kundur_cvs_v3_discrete.m line 137):
```
Vbase = double(230e3);   % 单位: V (线-线 RMS, V_LL_RMS)
```

**Vbase_const workspace export** (line 266):
```
assignin('base', 'Vbase_const', double(Vbase));   % 230000 V_LL_RMS
```

**CCS Amplitude Constant block** (lines 552-554):
```
add_block('simulink/Sources/Constant', [mdl '/LStripAmp_bus14'], ...
    'Value', 'LoadStep_trip_amp_bus14 / Vbase_const');
```

**Sine Wave blocks** (lines 572-580): Amplitude='1', Frequency='wn_const', Phase=phi_ph
- Phase offsets (line 562): {0, -2*pi/3, +2*pi/3}（绝对时间参考）

**Product block** (lines 582-601): amp_signal * sin_signal -> I_instantaneous_A

**CCS mode** (lines 591-595): Source_Type='DC'
- F4 验证 (test_ccs_dynamic_disc.m lines 20-28): DC+Step 5A -> 50V/10Ω. 确认 Inport1 = instantaneous amperes.

### 1.2 当前公式产生的实际峰值电流

```
LoadStep_trip_amp_bus14 = P_nominal = 248e6 W
Vbase_const             = 230e3 V_LL_RMS

I_pk_actual = P_nominal / Vbase_const
            = 248,000,000 / 230,000
            = 1078.3  A peak per phase
```

### 1.3 这个电流实际注入多少 3-phase 有功功率

在纯有功（cos φ = 1，注入 sin 与 bus voltage 完全同相）前提下：

```
V_phase_pk = V_LL_RMS * sqrt(2/3)
           = 230,000 * 0.81650
           = 187,793  V  (相-地峰值)

P_3ph_actual = (3/2) * V_phase_pk * I_pk_actual
             = 1.5 * 187,793 * 1,078.3
             = 303,853,200  W
             ≈ 303.9  MW
```

**结论**: 当前公式在 amp_W = 248e6 时（假设完全相位对齐），实际注入 P_active ≈ **303.9 MW**，**高于标称 248 MW 约 +22.47%**。

---

## 2. 正确公式推导

### 2.1 3-phase 有功功率基本关系

```
V_LL_RMS   = 230 kV           (线-线 RMS，Vbase)
V_ph_RMS   = V_LL / sqrt(3)   (相-地 RMS)
V_ph_pk    = V_ph_RMS * sqrt(2)
           = V_LL * sqrt(2) / sqrt(3)
           = V_LL * sqrt(2/3)
           = 230,000 * 0.81650
           = 187,793 V

# SMIB oracle (build_minimal_smib_discrete.m line 44) 使用同一公式:
# Vpk_ph = Vbase * sqrt(2/3)
```

### 2.2 从目标 P_total 反推 I_phase_pk

```
P_total = 3 * V_ph_RMS * I_ph_RMS * cos(phi)      [cos(phi)=1 for pure active]
        = 3 * (V_ph_pk/sqrt(2)) * (I_ph_pk/sqrt(2))
        = (3/2) * V_ph_pk * I_ph_pk

因此:
  I_ph_pk = 2 * P_total / (3 * V_ph_pk)
           = P_total * 2 / (3 * V_LL * sqrt(2/3))
           = P_total * sqrt(2/3) / V_LL
           = P_total * sqrt(2/3) / Vbase_const
```

数值：
```
I_ph_pk_correct = 248e6 * sqrt(2/3) / 230e3
                = 248,000,000 * 0.81650 / 230,000
                = 880.5  A peak per phase
```

### 2.3 正确公式（Constant block Value 应填写的表达式）

```
I_ph_pk = LoadStep_trip_amp_busN * sqrt(2/3) / Vbase_const
```

等价写法：`I_ph_pk = P_W / V_phase_peak = P_W / (V_LL_RMS * sqrt(3/2))`

### 2.4 反向验证

```
P_verify = (3/2) * V_ph_pk * I_ph_pk_correct
         = 1.5 * 187,793 * 880.5
         = 248,165,550 W ≈ 248 MW  [CORRECT ✓]
```

---

## 3. K Factor（实际注入 / 标称 amp_W）

### 3.1 精确代数推导

```
I_pk_actual  = P_nominal / Vbase_const                          [当前公式]
I_pk_correct = P_nominal * sqrt(2/3) / Vbase_const             [正确公式]

电流超额比: I_pk_actual / I_pk_correct = 1 / sqrt(2/3) = sqrt(3/2)

实际注入功率:
  P_actual = (3/2) * V_ph_pk * I_pk_actual
           = (3/2) * (V_LL * sqrt(2/3)) * (P_nominal / V_LL)
           = (3/2) * sqrt(2/3) * P_nominal

恒等式: (3/2) * sqrt(2/3) = sqrt((3/2)^2 * (2/3)) = sqrt(9/4 * 2/3) = sqrt(3/2)

因此: P_actual = sqrt(3/2) * P_nominal = K * P_nominal
```

### 3.2 K Factor 数值

```
K = sqrt(3/2) = sqrt(6)/2 ≈ 1.22474

P_actual = 1.22474 * 248e6 = 303.9 MW  (相位对齐时)

高估量: (K - 1) * 100% = 22.47%
```

**意义**: 每次传入 `LoadStep_trip_amp_busN = P_W`，实际注入的 3-phase 有功功率为 `P_W * sqrt(3/2)`，而非 `P_W`。

### 3.3 与旧 Phasor 公式对比（`if false` 段，lines 648-661）

旧 Phasor 注释（line 626-630）称: "real(V·conj(I)) ≈ Vbase · I_real ≈ amp_W"。这等价于用 `V_LL_RMS * I_ph_pk = P`（单相复功率分析），与正确 3-phase 公式差因子 3/2。Phasor 模式与 Discrete 模式的量纲逻辑不同，两种模式下旧公式各有不同的错误方向。当前分析仅针对 Discrete sin-CCS 实现。

---

## 4. 信号方向角度损耗

### 4.1 问题陈述

当前 Sine Wave Phase 参数（line 562）: `{0, -2*pi/3, +2*pi/3}`（绝对仿真时间参考）。

Kundur NR 潮流参考（compute_kundur_cvs_v3_powerflow.m line 58）: `BUS1_ABS_DEG = 20.0 deg`（Bus 1 松弛节点相位 = 20°）。

Bus 14 的电压相角约为 20 deg + 网络角差（route audit W4 引用 "delta_ts_3 ~14.4 deg per ES3 IC"，总量约 20-34 deg 范围）。

角度失配 Δφ = |注入 sin 参考相位 0° - Bus 14 电压相位|。

### 4.2 影响量化

```
P_active_injected = P_apparent * cos(Δφ)

Δφ = 0°:   cos = 1.000   P = 303.9 MW (量纲错无相位失配)
Δφ = 14°:  cos = 0.970   P = 294.8 MW (+19% vs 248 MW)
Δφ = 30°:  cos = 0.866   P = 263.3 MW (+6%  vs 248 MW)
Δφ = 60°:  cos = 0.500   P = 151.9 MW (-39% vs 248 MW)
Δφ = 80°:  cos = 0.174   P =  52.9 MW (-79% vs 248 MW)
```

（注：以上均假设量纲未修复，即 K = sqrt(3/2)）

### 4.3 两因子叠加无法解释反常现象

即使 Δφ = 80°，注入功率仍有 52.9 MW，远超 IC residual 水平（相当于 248 MW 的 21%）。**任何合理的相位失配值（0-90°）结合量纲高估（K=1.22），都预测 P_injected >> baseline，不可能产生 max|Δf| < IC residual 的结果。**

**结论**: 相位失配与量纲错是次要精度问题，不是 sanity 数据反常的根本原因。根本原因在 §7.1。

---

## 5. Y-connection neutral 检查

### 5.1 当前接线（build script lines 556-558, 603-605）

```
add_block('powerlib/Elements/Ground', [mdl '/LStripGNDneutral_bus14'], ...)

% 三相 CCS 全部共用此 GND (Y-grounded neutral)
add_line(mdl, 'LStripCCSA_bus14/LConn1', 'LStripGNDneutral_bus14/LConn1', ...)
add_line(mdl, 'LStripCCSB_bus14/LConn1', 'LStripGNDneutral_bus14/LConn1', ...)
add_line(mdl, 'LStripCCSC_bus14/LConn1', 'LStripGNDneutral_bus14/LConn1', ...)
```

### 5.2 正确性判断

**结论: Y-grounded neutral 接线本身正确。** 与 Kundur 模型所有 Three-Phase RLC Load（`Configuration='Y (grounded)'`，line ~377）一致。与 SMIB oracle CVS 的 Y-grounded neutral（build_minimal_smib_discrete.m lines 177-183）对称。

对平衡 3-phase 注入，中性线电流 = 0，共用 Ground block 无影响。Y-connection 接线不是 sanity 数据异常的原因。

### 5.3 悬挂问题：RConn1（电气出口端）

CCS 的 **LConn1**（负极）已确认接地。但 **RConn1**（正极，连接 bus 侧）的接线状态不确定：

build script line 607 注释:
```
% Note: CCS RConn1 (bus side) wiring is done in "Connect electrical bus net"
% section via local_register_at_bus — same as all other 3-phase blocks.
```

若 `local_register_at_bus` 的后续循环未将新增的 `LStripCCS{A,B,C}_bus14` 的 RConn1 正确注册，则 RConn1 悬空（开路）。**开路 CCS = 电气上不存在**，对网络频率无任何影响。这是 sanity 数据反常的首要怀疑对象（H1，见 §7）。

---

## 6. 修复建议（只描述等式，不写 patch）

### 选项 A: 最小改动（推荐: 排除 H1 接线问题后执行）

Constant block Value 从：
```
LoadStep_trip_amp_bus14 / Vbase_const
```
改为：
```
LoadStep_trip_amp_bus14 * sqrt(2/3) / Vbase_const
```

数学效果: I_ph_pk = P_W * sqrt(2/3) / V_LL_RMS = P_W / V_phase_peak

### 选项 B: 明确中间变量（可读性更高）

在 workspace assignin 段（near line 266）新增：
```
Vph_pk_const = Vbase_const * sqrt(2/3)   % [V] phase-to-ground peak
```

Constant block Value 改为：
```
LoadStep_trip_amp_bus14 / Vph_pk_const
```

语义：直接以相峰值电压为分母，与 SMIB oracle `Vpk_ph = Vbase * sqrt(2/3)` 命名对应。

### 选项 C: 量纲修正 + 相位对齐（完整方案，与 Phase 1.5 plan §2.5 + §2.3 一致）

1. **量纲**: Constant block Value = `LoadStep_trip_amp_bus14 * sqrt(2/3) / Vbase_const`

2. **相位**: 三相 Sine Wave Phase 参数分别为：
   - Phase A: `CCS_phi_bus14`
   - Phase B: `CCS_phi_bus14 - 2*pi/3`
   - Phase C: `CCS_phi_bus14 + 2*pi/3`

   其中 `CCS_phi_bus14` = bus 14 电压角（从 kundur_ic_cvs_v3.json `bus_voltage_angle_rad` 字段读取，单位 rad）。

注: Phase 1.5 plan §2.5 已注册 CHOICE: `I_pk = amp_W * sqrt(2/3) / Vbase_const`。
注: Phase 1.5 plan §2.3 已注册 CHOICE: `phi_<bus>` from NR IC。
P0-1c attempt 1 两个 CHOICE 均未实现，仍沿用旧 Phasor 公式 amp_W/Vbase_const。

---

## 7. 影响 audit Branch 决策

### 7.1 sanity 数据反常的正确解读

数据（route audit §2 W3）：
```
amp=0:      max|Δf| = 0.04-0.06 Hz (IC residual)
amp=248e6:  max|Δf| = 0.018-0.037 Hz (低于 IC residual — 反常)
amp=2480e6: max|Δf| = 0.05-0.34 Hz  (超 IC residual — 可见)
```

量纲分析结果: amp=248e6 实际注入 P ≈ 303.9 MW（量纲错高估），远大于 248 MW。若 CCS 电气连通，应产生 max|Δf| 远大于 IC residual，而非低于。

**反常现象唯一合理解释**: CCS 对网络的电气影响为零（悬空）或极小（高阻抗隔离）。

最可能假设排序：

**H1 (最高优先级): CCS RConn1 未完成 bus anchor 注册**
- 证据: line 607 注释明确 "wiring is done in ... local_register_at_bus"，但 P0-1c 新增的 block name 格式是 `LStripCCS{ph}_bus14`，而非旧格式——若 local_register_at_bus 的 block list 未包含新名称，则漏注册。
- 效果: RConn1 开路，CCS 对网络零影响，P=0 注入，观测到 IC residual（amp=0 的 IC residual 甚至略大于 amp=248e6 的观测值，符合）。
- 验证: `get_param([mdl '/LStripCCSA_bus14'], 'PortConnectivity')` 检查 RConn1 连接目标。

**H2 (中等优先级): CCS Source_Type='DC' 对 sin 信号行为异常**
- 证据: F4 只测 DC Step，未测 sin×constant 乘积。DC mode CCS 在 powerlib 可能对 AC 信号有截断。
- 效果: 注入 P << 期望，部分或全部 sin 被截断。
- 验证: mini-model CCS(DC) + sin*const input + R_load，测 V_load 波形。

**H3 (低优先级): IC 初始条件与 CCS 冲突导致数值不稳定**
- 效果: 功率注入存在但被 IC 迟回震荡掩盖。仅 amp=0 时看不到，amp=248e6 时也看不到——但 amp=2480e6 时可见（更强信号穿透噪声）。
- 这能解释 10× 可见但 1× 不可见的模式。与 H1 并行可能都有贡献。

### 7.2 K Factor 对实验数据修正系数

```
若 H1 排除（接线确认正确）且量纲已修复:
  amp=248e6 真实注入 = 248 MW (by design)
  期望 max|Δf| ≈ 4.9 Hz / 17 ≈ 0.29 Hz (SMIB oracle scaled by inertia ratio)
  G1.5-B 门限: ≥ 0.3 Hz — 边界情形，约 3% margin

若 H1 成立（接线悬空）:
  量纲修复无任何效果
  先修接线，再修量纲，再 E2E
```

### 7.3 正确的根因排查顺序

```
STEP 1: 验证 CCS 电气接线 (H1) — 最先做，代价最低
  工具: simulink_explore_block 或 simulink_trace_port_connections 查 LStripCCSA_bus14
  期望: RConn1 -> bus 14 phase A anchor (与其他 3-phase blocks 相同)
  若悬空 -> 修接线 -> rebuild -> E2E -> 检验信号通路 (跳过量纲修改先验证)

STEP 2: 若接线正确, 验证 CCS(DC) + sin 信号兼容性 (H2)
  工具: 单独 mini-model (不需要 Kundur 全模型)
  若截断 -> 考虑 Source_Type='AC' 或 CVS 替代

STEP 3: 接线+模式验证通过后, 修复量纲 (选项 A 或 B)
  预期: amp=248e6 产生 max|Δf| ≈ 0.25-0.35 Hz (≥0.3 Hz gate)

STEP 4 (可选): 若 STEP 3 后仍 < 0.3 Hz, 增加相位对齐 (选项 C)
  改善幅度: 约 +3-17% (cos(14°) ≈ 0.97 到 cos(34°) ≈ 0.83)
```

### 7.4 Branch 去向建议

若 H1 成立（接线悬空）: 量纲错 K=1.22 是已知 technical debt，但不是 blocker。接线修复 + 量纲修复 + 相位对齐 = 三件事可在同一 patch 中完成，不必分步。Phase 1.5 plan §2.5 已预注册了正确的量纲公式，只需在 P0-1c attempt 2 中落实。

若 H1 不成立（接线正确）: 量纲错 K=1.22 使实际注入 303.9 MW >> 248 MW，但信号仍不可见，说明存在更深层问题（H2 或 H3）。需先修 H2/H3 再评估量纲贡献。

---

*报告结束。不含任何代码 patch；所有行号引用自 build_kundur_cvs_v3_discrete.m P0-1c attempt 1 uncommitted state（git diff HEAD 可见）。*