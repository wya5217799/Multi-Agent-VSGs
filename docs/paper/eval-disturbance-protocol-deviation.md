# Eval Disturbance Protocol Deviation — Pm-step proxy as de facto

**Date:** 2026-04-29
**Scope:** `evaluation/paper_eval.py` 的 disturbance 协议选择，对论文 Sec.IV-C "load step 1/2 at Bus 14/15" 的偏离备案
**Status:** documented deviation, 类比 [Q7 action-range-mapping-deviation](action-range-mapping-deviation.md)

---

## 1. Paper PRIMARY (line 993-994)

> "Load step 1 and load step 2 represent the sudden load reduction of 248MW at bus 14 and the sudden load increase of 188MW at bus 15, respectively."

测试集累积奖励 (line 982-984)：
- DDIC trained: -8.04
- adaptive inertia: -12.93
- no control: -15.20

---

## 2. v3 Implementation State

### 2.1 LoadStep R-mode (loadstep_paper_random_bus / loadstep_paper_bus14 / loadstep_paper_bus15)

`build_kundur_cvs_v3.m` line 354-355:
```matlab
add_block('powerlib/Elements/Series RLC Branch', [mdl '/' name], ...);
set_param([mdl '/' name], 'BranchType', 'R', ...
    'Resistance', sprintf('Vbase_const^2 / max(LoadStep_amp_%s, 1e-3)', bus_label));
```

`Series RLC Branch` 的 Resistance 参数在 **.slx 编译时被求值并冻结**。FastRestart 下所有 sim() chunks 共享同一编译产物；运行时 `apply_workspace_var('LoadStep_amp_busXX', new_value)` 只更新 MATLAB base workspace，**不会触发** Series RLC 块的 Resistance 重新求值。

**实证 (Smoke A/C, 5 scenarios @ DIST=[0.1,1.0] sys-pu, M=24, D=4.5, zero-action)**:
- `max|Δf| = 0.0091 Hz` × 5 (bit-identical)
- `cum_unnorm = -0.0038`
- 完全是 IC kickoff 残留信号；扰动未真正应用

### 2.2 LoadStep CCS-mode (loadstep_paper_trip_random_bus / trip_bus14 / trip_bus15)

`build_kundur_cvs_v3.m` line 396-414:
```matlab
add_block('simulink/Sources/Constant', ...,
    'Value', sprintf('LoadStep_trip_amp_%s / Vbase_const', bus_label));
add_block('powerlib/Electrical Sources/Controlled Current Source', ...);
```

Constant 块每 sim() chunk 重 evaluate 表达式 → CCS 输入有部分 tunability。

**实证 (Smoke D, 同上配置)**:
- `max|Δf| ∈ [0.0093, 0.0098]` Hz (slight variation)
- `cum_unnorm = -0.0041`
- 信号仍仅 ~0.01 Hz 量级，比 Pm-step proxy 同 magnitude 下 (0.41 Hz) 弱 ~40×
- 可能原因：Bus 14/15 是 ESS 端短 1-km Pi 线，电气距离离 Bus 7/9 load center 远，injection 在那里激发系统模式效率低；或 CCS 在 Phasor mode 下的 Init/tunability 配置受限

### 2.3 Pm-step proxy (pm_step_proxy_random_bus / bus7 / bus9 / g1-3 / random_gen)

`build_kundur_cvs_v3.m` 给每个 source 接 Constant→Product 链，由 workspace var `Pm_step_amp_<i>` 驱动。Constant 真正可调。

**实证 (Smoke B, 同上配置)**:
- `max|Δf| ∈ [0.08, 0.41]` Hz (varies by magnitude)
- `cum_unnorm = -2.67` (5 scenarios) → -21.73 (50 scenarios, no_control_postlock)
- 信号正常应用

---

## 3. Decision

**接受 Pm-step proxy 为 v3 paper_eval 的 de facto 协议**。

具体实现：
- `evaluation/paper_eval.py` 默认 `KUNDUR_DISTURBANCE_TYPE = pm_step_proxy_random_bus`（已存）
- per-episode 按 scenario.bus ∈ {7, 9, 1, 2, 3} 路由到对应 ESS-side / SG-side proxy（已存，commit 32c7511 后受 env-var 控制）
- LoadStep R-mode / CCS-mode 路径**保留**给 unit testing / 物理回归用，**不**用于 paper_eval

### 偏差含义

- 项目 cum_unnorm 跟论文 -8.04 / -15.20 **不可直接对账**：协议不同
  - 论文：网络侧 248/188 MW 真负荷切换 + comm-link failures
  - 项目：ESS-side / SG-side Pm-step proxy 上 [10, 100] MW 范围随机扰动
- trained vs no_control 在**同一项目协议下**的对比仍然有效（这是 RL 是否工作的内部判定）

### 为何选 Pm-step proxy 而不修 LoadStep

- LoadStep R-mode 修复需替换 Series RLC R 为 Variable Resistor → 强制 Discrete solver → 与 Phasor solver 不兼容 → **重做物理层** + 重 build + 重 IC + 重 smoke
- LoadStep CCS-mode 信号弱可能源于 Bus 14/15 拓扑位置 → 重审拓扑也是 **重做物理层**
- 关 FastRestart 让 R 块每 episode 重编译 → 单 eval 时长翻 5×+，HPO 不可行

物理层在 commit `a9ad2ea` (credibility close) 已锁定，不在本次工作范围。

---

## 4. Resolution Path（解除偏差所需）

| 路径 | 动作 | 影响 |
|---|---|---|
| **A** | build_kundur_cvs_v3.m 改 LoadStep R 块为 PS-driven Resistance / Variable R + 选 solver-compatible 配置 | 物理层重做，破 credibility close 锁；需重 NR + 重 .slx + 重 smoke |
| **B** | 改 v3 拓扑把 LoadStep 测点从 Bus 14/15 ESS 母线移到 Bus 7/9 load center | 物理层重做；需重 NR + 重 .slx + 重 smoke |
| **C** | 关 FastRestart 让 R 块每 episode 重编译 | 性能不可行 (eval 时长 ×5+) |
| **D** (本次选) | 接受 Pm-step proxy 为 v3 协议；记录偏差；不改物理层 | 论文数值对账失效，但项目内部 trained vs no_control 比较仍有效 |

---

## 5. References

- 论文行号：line 993-994 (LoadStep 1/2 定义)，line 982-984 (DDIC -8.04 / no_ctrl -15.20)
- v3 build script：`scenarios/kundur/simulink_models/build_kundur_cvs_v3.m` line 354-414
- v3 env disturbance dispatch：`env/simulink/kundur_simulink_env.py::KundurSimulinkEnv._apply_disturbance_backend`
- LoadStep IC reset fix：commit `4902caf`
- paper_eval env-var gate fix：commit `32c7511`
- 4-smoke 实测数据：`results/harness/kundur/cvs_v3_eval_fix_smoke/{loadstep,default,loadstep_postfix,loadstep_trip}_metrics.json`
- 完整架构分析：`results/harness/kundur/cvs_v3_eval_fix_smoke/loadstep_eval_blocker_verdict.md`
- 同类 deviation：`docs/paper/action-range-mapping-deviation.md` (Q7)
- credibility close 锁定：`docs/decisions/2026-04-10-paper-baseline-contract.md` §2026-04-28

---

## 6. Status

| 项 | 状态 |
|---|---|
| Documented deviation | active, 2026-04-29 |
| 协议默认值 (`evaluation/paper_eval.py:488`) | `pm_step_proxy_random_bus` |
| Resolution required if | 论文数值精确对账 (cum_unnorm ↔ -8.04 / -15.20) 成为 binding 验收标准 |
| Owner | （待）|
