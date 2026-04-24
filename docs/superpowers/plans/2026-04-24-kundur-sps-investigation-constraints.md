# Kundur SPS Task 9 — Investigation Constraints

> 跨批次约束文档，记录本次 investigation 期间不变的规则。  
> **不**记录当前批次授权（查当前短计划）、当前状态（查 NOTES.md 和 summary.md）。  
> **搭配方式**：本文档（稳定边界）+ 短计划（单批次授权）。长计划仅供历史参考，不参与执行链。

---

## 文件职责分工

| 文件 | 职责 | 更新时机 |
|---|---|---|
| 本文件 | Hard gates、禁止项、STOP 条件 | investigation 期间基本不变 |
| 当前短计划 | 当前授权批次 + 本批次允许/禁止的具体操作 | 每批次开始前由人工写出 |
| `NOTES.md` "现在在修" | 场景 blocked 状态（3 行以内）+ 指针 | 每批次 STOP 后 |
| `summary.md` 当前状态节 | 最新 verdict + 已排除假设 | 每批次 STOP 后覆写 |
| `summary.md` 证据记录节 | 各批次数据 | 每批次 STOP 后追加 |
| `attachments/` | Artifact ground truth | 只增不改 |

---

## 执行前必读顺序

1. 本文件（约束规则，权威）
2. 当前短计划 → 确认本批次授权操作和终止 artifact
3. `scenarios/kundur/NOTES.md` "现在在修" → 确认场景 blocked 状态
4. `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/summary.md` → 确认最新 verdict

---

## 最终目标

使 Kundur SPS/Phasor 候选模型的静态工作点与 NR 潮流参考值对齐，令所有静态 hard gates 通过，从而重新开放 Smoke Bridge → 训练路径。

---

## Hard Gates

模型重新进入 Smoke Bridge 的必要条件，不得绕过：

- `abs(sps_ess_bus_angle_deg − nr_ess_bus_angle_deg) ≤ 1.0 deg`（ESS 专属母线 Bus 12/16/14/15，全部四个 ESS）
- `abs(Pe_sys_pu − expected_Pe_sys_pu) ≤ 0.05 pu`（全部四个 ESS，期望值 0.2 pu）
- `manual_vi_diff_abs ≤ 1e-6 pu`
- 无任何 ESS Pe 符号错误
- 无任何 ESS Pe 多倍标幺值（`abs(Pe_sys_pu) > 1.0 pu` 为硬性失败）
- `validate_phase3_zero_action.py` 判定 `VERDICT: ALL PASS`（C0/C1/C3/C4/C5）
- 所有角度比较使用 `wrap_to_180` 归一化和 `angle_diff_deg`，不得裸减
- 探针运行后模型不得为 dirty（若 dirty：不保存，close without saving，从磁盘重载）

> NR 角度比较基准已更新为 ESS 专属母线（Bus 12/16/14/15）。  
> `measurement_point_mapping.json` 已确认 SPS 实际测量节点为 ESS bus；主线 bus（7/8/10/9）在当前 SPS 模型中无直接测量块。

---

## 禁止项

以下操作在根因确认并获得 Task 5 显式授权前，严格禁止：

**生产文件禁止编辑：**
- `scenarios/kundur/simulink_models/build_kundur_sps.m`
- `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m`
- `scenarios/kundur/simulink_models/build_powerlib_kundur.m`
- `scenarios/kundur/kundur_ic.json`
- `scenarios/kundur/simulink_models/kundur_vsg_sps.slx`
- `scenarios/kundur/config_simulink.py`
- `slx_helpers/vsg_bridge/slx_extract_state.m`
- `docs/paper/experiment-index.md`
- 任何训练脚本

**行为禁止：**
- 禁止保存 Simulink 模型（`simulink_save_model`）
- 禁止任何可能导致模型 dirty 的临时参数修改（`set_param`、`simulink_patch_and_verify` 等）
- 禁止运行 Smoke Bridge、训练脚本、cutover
- 禁止将探针结论直接升级为模型修改（evidence ≠ action）
- 禁止 agent 仅凭 artifact 内容推断下一分支并执行（必须人工授权后才能行动）
- 禁止同时测试多个诊断分支
- 禁止把诊断任务升级为重构或架构修改

---

## STOP 条件

以下任一满足，立即停止并汇报：

1. 当前授权批次的 artifact 已写出（批次完成）
2. 任意 ESS Pe 出现多倍标幺值（`abs(Pe_sys_pu) > 1.0 pu`）
3. 探针运行后模型处于 dirty 状态
4. 探针输出与当前工作假设矛盾
5. 即将修改任意被禁止的生产文件，或即将运行超出当前批次授权范围的操作
6. 约 5000 token 后仍无有效证据、无确认工具调用、无写出 artifact（token 熔断器）
7. 所需信息无法通过只读操作获取
8. 下一步动作属于未授权批次

**STOP 后必做：** 更新 `summary.md` 当前状态节 → 更新 `NOTES.md` "现在在修" → 再汇报。

---

## STOP 汇报格式

```
- 当前授权批次 artifact 是否写出：[是 / 否]
- artifact 路径：[路径]
- 是否有 blocker：[是（描述）/ 否]
- 是否发生 dirty 状态：[是（描述）/ 否]
- 下一步：需要人工授权，不得自行执行
```
