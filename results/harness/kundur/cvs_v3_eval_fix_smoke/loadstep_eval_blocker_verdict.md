# LoadStep paper-faithful eval — Architectural Blocker Verdict

**Date:** 2026-04-29
**Trigger:** User指令 "做 1 和 2" — fix env._reset_backend LoadStep IC restoration + rerun 4-policy paper_eval under loadstep_paper_random_bus.
**Status:** **STEP 1 COMPLETED, STEP 2 BLOCKED — architectural limitation surfaced; rerun would produce null comparisons.**

---

## Step 1 — completed

**Commit:** `4902caf fix(kundur-env): restore LoadStep IC workspace vars on every v3 reset`

`env/simulink/kundur_simulink_env.py` 的 `_reset_backend` 在 `cfg.model_name == 'kundur_cvs_v3'` 路径下显式写：
- `LoadStep_amp_bus14 = 248e6`
- `LoadStep_amp_bus15 = 0`
- `LoadStep_trip_amp_bus14 = 0`
- `LoadStep_trip_amp_bus15 = 0`

每个 reset 时恢复，让 FastRestart 下不再粘连上一 episode 的 disturbance state。这是**正确的 IC 恢复行为**。

**但**：smoke 验证显示这个 fix **不能解锁 LoadStep 通路的 paper_eval 信号**（见下一节）。

---

## Step 2 — blocked，未执行

### 4 个 5-scenario smoke 数据

| Smoke | 协议 | LoadStep IC reset fix | max\|Δf\| (mean over 5) | cum_unnorm | 状态 |
|---|---|---|---:|---:|---|
| A | loadstep_paper_random_bus | 无 (pre-fix) | 0.0091 Hz × 5 (bit-identical) | -0.0038 | weak signal |
| B | (default Pm-step proxy) | 无 (pre-fix) | 0.0795 - 0.4135 Hz (varied) | -2.6667 | ✅ working |
| C | loadstep_paper_random_bus | ✅ post-fix | 0.0091 Hz × 5 (bit-identical) | -0.0038 | **same as A** |
| D | loadstep_paper_trip_random_bus (CCS) | ✅ post-fix | 0.0093 - 0.0098 Hz | -0.0041 | weak signal w/ tiny variation |

### 根本原因（LoadStep R-mode）

`scenarios/kundur/simulink_models/build_kundur_cvs_v3.m` line 354-355:

```matlab
set_param([mdl '/' name], 'BranchType', 'R', ...
    'Resistance', sprintf('Vbase_const^2 / max(LoadStep_amp_%s, 1e-3)', bus_label));
```

LoadStep 用的是 `powerlib/Elements/Series RLC Branch`（`BranchType='R'`）的 `Resistance` **字符串表达式**。问题：

- **Series RLC 块的参数在 .slx 编译时被求值并冻结**
- FastRestart 下 sim() chunks 共享同一份 compiled model
- 运行时 `apply_workspace_var('LoadStep_amp_bus14', 0)` 只更新 base workspace
- Constant 块会每 sim chunk re-eval；Series RLC 块不会
- 所以 `LoadStep_amp_bus14 = 248e6 → 213 Ω` 在编译时定下，永远不变

build script 自己的注释 "Tunability: Constant.Value re-evaluates per sim() chunk" 实际上**误标了** —— LoadStep 用的是 Series RLC R，不是 Constant。

### CCS path (Smoke D)

`loadstep_paper_trip_random_bus` 用 Constant → CCS 链：

```matlab
add_block('simulink/Sources/Constant', [mdl '/' re_name], ...
    'Value', sprintf('LoadStep_trip_amp_%s / Vbase_const', bus_label));
add_block('powerlib/Electrical Sources/Controlled Current Source', ...);
```

Constant 块**应该**每 sim chunk re-eval（这是标准 Simulink 行为）。Smoke D 显示 max\|Δf\| 在 0.0093-0.0098 之间略有变化（不再 bit-identical），证明 CCS amp 确实在响应 magnitude。但量级仍然只有 0.01 Hz，与 Pm-step proxy 在同 magnitude 下的 0.4 Hz 差 40 倍。

可能原因：
- CCS 块的 `Initialize='off'` 配置可能让首个 sim chunk 完全忽略外部输入
- Bus 14/15 是 ESS 短 1-km Pi 线连接，电气距离离 Bus 7/9 load center 远，injection 在那里不能有效激发系统模式
- powerlib CCS 在 Phasor 模式下的 tunability 文档 unclear

### 为什么 step 2 跑了也无意义

如果在 `loadstep_paper_random_bus` 协议下重跑 no_control + ep50 + best + final 4 policies：

- 每次 cum_unnorm ≈ -0.004（完全由 IC kickoff 残留主导）
- policy 之间差异在 1e-4 Hz 量级（噪声地板内）
- **无法区分 trained vs no_control**

跑出来的 verdict 只能写"4 policies 不可区分，因为 disturbance 没有真正应用"。这不是评估 trained policy 的有效结果，而是评估 architecture 的 dead-end。**跑这一轮浪费 27 分钟 MATLAB engine 时间换无信息量结论**，所以跳过。

---

## 真正能解锁 LoadStep paper-faithful eval 的路径（不在本次 scope）

### 方案 A — build script 改 LoadStep 块类型（**触及物理层**）
将 `powerlib/Elements/Series RLC Branch` 替换为：
- `powerlib/Elements/Variable Resistor`（动态 R 输入端口）—— **要求 Discrete solver**，与现 Phasor solver 不兼容
- `powerlib/Elements/Three-Phase Programmable Voltage Source`（驱动可变 R）
- 或 Switch-controlled Branch network with PS Logic

每条都需 build script 重写 + 重生成 .slx + 重生成 IC + 重 smoke。**物理层动作 = 不在 credibility-close 锁定后允许的范围**。

### 方案 B — 接受 Pm-step proxy 作为 de facto eval 协议（**最低成本**）
明确文档化：

> "Under v3 architecture with FastRestart + Phasor solver, paper-faithful network-side LoadStep disturbance is NOT runtime-tunable in paper_eval. The Pm-step proxy at ESS-side (`pm_step_proxy_random_bus`) is the de facto working evaluation protocol. Comparisons against paper DDIC -8.04 / paper no_ctrl -15.20 are protocol-mismatched and should be interpreted accordingly."

这是诚实的 documented deviation，与 `docs/paper/action-range-mapping-deviation.md`（Q7）同类。

### 方案 C — per-episode 强制重 compile（**性能不可行**）
关闭 FastRestart 让 Series RLC R 每 episode 重新评估。每 episode +30s 编译 → 50 scenario × 30s × N policies = 工时翻 5+ 倍。

---

## 当前 commit 状态

```
4902caf fix(kundur-env): restore LoadStep IC workspace vars on every v3 reset    ← 本次
32c7511 fix(paper-eval): gate per-episode disturbance_type override on env-var
88abd64 feat(kundur-train): P1 runtime pre-flight banner + IC sha256 in run_meta
ec07e1d feat(kundur-sac): add per-agent buffer and warmup knobs
a9ad2ea chore(kundur-cvs-v3): lock credibility-close training interface defaults
```

tracked-M = 0。无 .slx / IC / runtime.mat / build / bridge / config / SAC / reward / NE39 改动。

---

## STOP — 等用户裁决

不进入步骤 2 的"无效 4-policy 重跑"。请选：

1. **接受方案 B**（推荐）：明确 Pm-step proxy 是 de facto eval 协议；当前 P0 paper_eval verdict 直接成立；进入 PHI 重审 sweep（A 优先）或 P2 update_repeat sweep
2. **走方案 A**：物理层重做 LoadStep 块（破坏 credibility close 锁定）
3. **走方案 C**：关 FastRestart 重跑 step 2（27 min × ~5 = 2+ h，且未来所有 eval 都慢）

完整 verdict + smoke 数据 + 架构分析见 `results/harness/kundur/cvs_v3_eval_fix_smoke/loadstep_eval_blocker_verdict.md`。
