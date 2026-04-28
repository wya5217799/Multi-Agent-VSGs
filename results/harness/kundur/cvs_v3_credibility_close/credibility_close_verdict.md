# Credibility Close — HPO 前接口层锁定 + paper_eval 复测

**Date:** 2026-04-28 23:00 → 2026-04-29 00:40
**Trigger:** 用户指令 "按 5 项执行 credibility close，严格 STOP cadence；只改文件，不动物理层"
**Topology variant:** `v3_paper_kundur_15bus_w2_at_bus8_ls1_preengaged`
**Status:** **ACCEPTABLE-WIDE PASS** — 用户裁决路径 1：接受 -21.73 为项目协议下真实 no-control baseline，ACCEPTABLE 区间放宽到 [-8, -25]；commit 5 项接口层锁定。

---

## 1. 5 项裁决表（HPO 前接口层）

| # | 项 | 裁决 | 理由 |
|---|---|---|---|
| 1 | 动作范围 ΔM∈[-6,18]/ΔD∈[-1.5,4.5] | **保留** | Phase C 实证 paper-literal L3 范围 M=1 corner ROCOF=9.8 Hz/s 危险；当前 L0 已 Phase D 18× tau 杠杆验证。Q7 量纲未解前不机械采纳论文字面值。详见 `docs/paper/action-range-mapping-deviation.md` |
| 2 | 奖励权重 PHI_H/PHI_D | **锁定 0.0001 + 删 env-var override** | env-var 是 sweep 用的，HPO 必须搜固定 reward。0.0001 由 Q7 量纲映射推出（ΔM 比论文 ΔH 小 33×，ΔM² 小 ~1100×） |
| 3 | 训练扰动幅度 DIST_MAX | **0.5 → 1.0 sys-pu** | paper_eval no-control = -6.11 vs 论文 -15.20 高度相关于扰动量级；DIST_MAX=0.5 可能显著 under-excite system。**不声称已完全证明 2.5× 缺口只由 DIST_MAX 解释。** |
| 4 | Buffer 不清空 | **保留** | off-policy SAC 标准；已在 `paper-baseline-contract.md §Q3` 备案 |
| 5 | T_WARMUP=10s | **保留 + 注释升级 production locked** | post_task_mini 实证 t=10 s 残差 < 0.5 mHz |

---

## 2. 文件 diff 摘要

| 文件 | 修改 |
|---|---|
| `scenarios/kundur/config_simulink.py` | 5 处：DEFAULT_KUNDUR_MODEL_PROFILE → v3；PHI_H=PHI_D=0.0001 锁；DIST_MAX 0.5→1.0；KUNDUR_DISTURBANCE_TYPE 默认 `loadstep_paper_random_bus`；T_WARMUP 注释升级 |
| `docs/paper/yang2023-fact-base.md` | §10 表新增 5 行 credibility-close 条目，更新最后修改日期 |
| `docs/decisions/2026-04-10-paper-baseline-contract.md` | 末尾追加 "2026-04-28 Credibility Close" 段（裁决表 + 同步修改 + 未触动列表）|
| `scenarios/kundur/NOTES.md` | 顶部加 credibility-close 块 |
| `results/harness/kundur/cvs_v3_credibility_close/credibility_close_verdict.md` | 本文件 |

**未触动**: 物理层（拓扑/IC/.slx/runtime.mat/NR 脚本）、`engine/simulink_bridge.py`（pre-existing M, 不属本次范围）、bridge/helper、SAC 架构、reward 公式结构、NE39 任何文件。

---

## 3. 静态验证

env-vars 全部 unset 后 import config:

```
DEFAULT_KUNDUR_MODEL_PROFILE = .../kundur_cvs_v3.json    ✓ contains kundur_cvs_v3.json
PHI_H == 0.0001  ✓
PHI_D == 0.0001  ✓
DIST_MIN == 0.1  ✓
DIST_MAX == 1.0  ✓
KUNDUR_DISTURBANCE_TYPE == 'loadstep_paper_random_bus'  ✓
T_WARMUP == 10.0  ✓
```

`grep KUNDUR_PHI_H|KUNDUR_PHI_D scenarios/kundur/config_simulink.py` → No matches ✓

`git diff` 范围检查：本次修改的 5 个文件全部位于允许列表内；其余 `engine/simulink_bridge.py`、`agents/multi_agent_sac_manager.py`、`scenarios/kundur/train_simulink.py` 是 session 启动前已存在的 M 文件，不在本次 commit 范围。

---

## 4. paper_eval no-control 复测（锁定后）

**配置**:
- `KUNDUR_MODEL_PROFILE=scenarios/kundur/model_profiles/kundur_cvs_v3.json`
- `KUNDUR_DISTURBANCE_TYPE=loadstep_paper_random_bus`
- 50 deterministic scenarios, seed-base=42

**结果**:
| Metric | Pre-lock (10:54) | Post-lock (00:40) | Paper |
|---|---:|---:|---:|
| cum_unnorm | -6.1055 | **-21.7348** | -15.20 (no_ctrl) / -8.04 (DDIC) |
| per_M | -0.12211 | -0.43470 | — |
| per_M_per_N | -0.030527 | -0.108674 | — |
| max\|Δf\| mean Hz | 0.132 | 0.243 | — |
| max\|Δf\| peak Hz | 0.228 | **0.463** | ~0.5 (Fig.6 LS1 估计) |
| ROCOF mean Hz/s | 0.91 | 1.64 | — |
| ROCOF max Hz/s | 1.56 | 3.14 | — |
| tds_fail / nan | 0 / 50 | 0 / 50 | — |

**Verdict 区间映射** (用户原始指令):
- [-10, -15] → PASS
- [-8, -18] → ACCEPTABLE (记残差)
- > -3 或 < -30 → FAIL，STOP，不 commit

**用户裁决（2026-04-29）— 路径 1**: 接受 -21.73 为项目协议下真实 no-control baseline，ACCEPTABLE 区间放宽到 [-8, -25]。理由：物理上合理（max|Δf| 0.46 Hz ≈ 论文 Fig.6 LS1 ~0.5 Hz；0 tds_fail / NaN），paper-faithfulness 优先于严格数值对账。残差 +6.5 (-21.73 vs -15.20) 已记录。**ACCEPTABLE-WIDE PASS，commit 配置锁定。**

---

## 5. 解读

**物理上的合理性**:
- max|Δf| mean 0.24 Hz / peak 0.46 Hz 与论文 Fig.6 LS1 ~0.5 Hz 量级吻合
- 0 NaN, 0 tds_fail, 0 saturation → 物理仍稳定
- 扰动从小幅 Pm-step proxy（10-50 MW）切到 paper-faithful LoadStep（固定 248/188 MW）确实把 r_f 拉到论文同量级

**为何超过 [-8, -18] 上限**:
- 切到 `loadstep_paper_random_bus` 后扰动量级被 disturbance_type 直接固定（LS1=248 MW、LS2=188 MW），不受 DIST_MAX 调节。Pre-lock 的 -6.11 主要被 ESS-side 小幅 proxy 限制
- DIST_MAX 0.5→1.0 在 LoadStep 路径下实际不起作用（LS1 magnitude argument 被忽略，LS2 受 magnitude 缩放但 magnitude 仍由 LoadStep 路径直接生成）
- r_f 是同步残差的二次方求和；扰动量级↑ → 同步残差↑ → r_f 平方放大

**两条可选路径让数字回到 ACCEPTABLE**:

1. **路径 A — 减小 LoadStep 扰动幅度**: 把 build 默认的 248 MW (LS1) / 188 MW (LS2) 缩成 ~ 100-150 MW。需要改 build script + 重 NR + 重生成 .slx —— **触及物理层，与本次"不动物理层"原则冲突**
2. **路径 B — 保持 LoadStep 248/188 MW (paper-faithful)，承认 -21.73 是项目协议下的真实 no-control baseline**: 把 ACCEPTABLE 区间放宽到 [-8, -25] 或类似，记录这一事实

**两条路径的 trade-off**:
- A 牺牲 paper-faithfulness 换数值 alignment
- B 保留 paper-faithfulness 承认数值差异

---

## 6. ACCEPTABLE-WIDE PASS — Commit 配置锁定

用户裁决路径 1：放宽 ACCEPTABLE 到 [-8, -25]，承认 -21.73 是 paper-faithful disturbance 协议下的真实 no-control baseline。

**残差备案**: -21.73 vs paper -15.20，绝对差 +6.5。可能来源（按概率排序）:
- 项目同步残差比论文实测略大（M=24/D=4.5 vs paper 未给 baseline）
- LoadStep 是 R-engagement / R-trip 模型 vs paper breaker 真实切换（可能影响瞬态形状）
- 测试 scenario 集（50 个 deterministic 随机扰动）vs 论文 50 个原始 random 扰动分布的具体差异

**HPO 启动后**: 用 DDIC 训练 policy 重跑 paper_eval，看是否进入 -8 → -15 之间（即 |residual_DDIC - paper_DDIC -8.04| 是否 < 7）。如果 trained policy 跑 paper_eval 拿到 -10 ~ -8，说明项目协议下的 |delta_DDIC_vs_no_control| 与论文 |8.04 - 15.20| ≈ 7 接近，方法论 alignment OK。

**未触动**: 物理层、bridge/helper、SAC 架构、reward 公式结构、NE39。
