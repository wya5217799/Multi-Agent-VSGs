# R08 Verdict — H scan + governor 物理验证 (V3 env governor 实测无效)

**Phase**: Audit + Empirical Sweep (0 SAC train)
**Status**: DONE
**Wall**: ~5 min (script run via WSL ANDES) + 10 min verdict
**Trigger**: R07 verdict §5 提的 R08 audit 路径 + user 提供 `quality_reports/plans/2026-05-07_physics_validation_plan.md` (V1+V2+V3)
**Script**: `scripts/research_loop/r08_h_scan.py` (8 H × 2 LS + 2 governor on/off + V3, 14 eval)
**Output**: `results/research_loop/r08_h_scan.json`

---

## §1 实测 (14 eval, no SAC, zero action)

### V1: H scan on V2 env (no governor)
| H (s) | LS1 max_df | LS2 max_df | vs H=10 LS1 |
|---|---|---|---|
| **10** (baseline) | **0.815** | **0.533** | — |
| 30 | 0.539 | 0.394 | -34% |
| 100 | 0.328 | 0.318 | -60% |
| **300** (paper Eq.12 upper) | **0.266** | **0.242** | **-67%** |
| **paper benchmark** | **0.13** | **0.10** | — |

### V2: governor on/off at H=10
| config | LS1 max_df | LS2 max_df |
|---|---|---|
| V2a (V2 env, no gov) | 0.815 | 0.533 |
| V2b (V3 env, gov on) | **0.815** | **0.533** |
| **diff** | **0.000** | **0.000** |

### V3: H=300 + governor on (final showstopper)
| config | LS1 max_df | LS2 max_df |
|---|---|---|
| V3 (V3 env, H=300) | 0.266 | 0.242 |
| V1_H300_noGov | 0.266 | 0.242 |
| **diff** | **0.000** | **0.000** |

---

## §2 关键发现

### ⭐ Finding 1: ANDES 对 H 调节响应正常 (V1 通过)

H 翻 30× (10→300) → max_df 降 67% (LS1) / 55% (LS2). 单调降, R05 SAC 没学到大 H 是 partial 原因 (但见 Finding 3).

**结论**: ANDES GENCLS swing 方程对 M (=2H) 参数响应物理正确. 不是"agents 不动"问题, 是 SAC 学不到大 ΔH.

但 R05 action_range_2x (DM_MAX=60, ΔH up to ~30) 也卡 0.037 attractor → 在 SAC 学到 ΔH=30 时 max_df 仍 0.5, 跟 V1 H=30 实测一致 (max_df 0.539). **action bound 扩到 paper-scale (DM_MAX=600 → ΔH 300)** 才是 V1-d (0.266) 的 SAC 等价.

### ⭐⭐ Finding 2: V1-d max_df 0.266 仍 **2× 太大** vs paper 0.13

即使 H=300 (paper Eq.12 box upper, 物理可达极限), ANDES no_control:
- LS1: 0.266 vs paper 0.13 → **2.0× too large**
- LS2: 0.242 vs paper 0.10 → **2.4× too large**

**SAC 极限**: 即使 SAC 完美学到 H=300 配置, ANDES 物理上还是 2× paper. **paper Fig.7 视觉对比仍达不到**.

→ R09 候选: 找 paper Simulink Kundur 跟项目 ANDES Kundur 的**剩 2× 残差源** (after H 量级对齐):
- 系统其他参数差异 (line / load model / SBASE)
- TDS solver 数值阻尼
- disturbance 注入方式

### ⭐⭐⭐ Finding 3: **V3 env governor 完全无效** (致命)

V2b (V3 env governor on) max_df **完全等于** V2a (V2 env no gov):
- LS1: 0.815 = 0.815 ✓
- LS2: 0.533 = 0.533 ✓
- V3 (H=300 + gov) = V1_H300_noGov 也完全相同

**root cause**: V3 env (`env/andes/andes_vsg_env_v3.py`) 加了 IEEEG1 + EXST1 但**没接进 swing 方程**:
- `r03_governor_wire_probe.json` 报 "pflow + 5step TDS PASS" 是**没 crash**, 不代表 governor 真起作用
- 可能 governor 输出 (Pgv) 没传到 GENROU/GENCLS 的 Pm, 或 EXST1 输出没传到 vf
- R04 V3_smoke 报 fpeak 0.42 (vs V2 0.55, 改善 24%) 是 **SAC 训练效果**, 不是 governor 物理效果

**这意味着 R03/R04 governor 实验全部 invalid** — 我们以为 V3 加了 governor, 实际 governor 装上但没工作.

---

## §3 R09 路径 — 双轨平台校准

**Phase Audit + Code Fix (混合)**, ~80 min wall:

### 主线 (priority=11): 修 V3 env governor wiring

**问题**: IEEEG1 + EXST1 加进 ANDES 但 vout 没接 swing 方程.

**任务**:
1. 读 ANDES doc: IEEEG1 / EXST1 模型 vout 字段 (Pgv 输出 / vf 输出)
2. 读 ANDES GENROU 模型 input 字段 (Pm input / vf input)
3. 验 ANDES 自动连接 syn= 字段是否真的 wire vout → input (R03 probe 没验这个)
4. 若没 wire, 手动设 GENROU 的 Pm/vf 链接到 IEEEG1/EXST1 输出
5. 再跑 V2/V3 对比, 期 V3 max_df 降 ≥ 30%

**out**: `audits/2026-05-08_governor_wiring_fix.md` + 修代码

### 副线 (priority=8): 平台 2× 残差源 audit

**问题**: H=300 物理可达极限, max_df 仍 2× paper.

**任务**:
1. paper §III: Kundur 系统 SBASE / line impedance / transformer / load model
2. ANDES `kundur_full.xlsx` case 实际值
3. 找参数 mismatch (尤其 line damping / load p2p 模式)
4. 反推: paper Fig.6 LS1 no-control max_df=0.13 + LS=2.48 sys_pu 反推 paper Kundur effective 平均 H/D
5. 跟 ANDES H=300 对比, 看是否 system damping D 是关键差异

**out**: `audits/2026-05-08_platform_2x_residual.md`

### 兜底

若 R09 主线修了 governor 后 max_df 仍 ≥ 0.4 → 平台残差 (副线) 是 root, R10 改 paper narrative ("ANDES Kundur partial replication, 2× residual on max_df due to platform damping difference").

---

## §4 SKILL.md 候选 lessons

1. **probe PASS ≠ 物理生效**: r03_governor_wire_probe.json "pflow + 5step TDS PASS" 让 R04 假设 governor 起作用, 实际 R08 V2 直接对比证伪. **新规则: 物理修改 (governor / damper / new model) 后必须做 "before vs after 物理量对比" probe, 不是 "TDS PASS" probe**.
2. **R04 V3_smoke 改善是 SAC 效果不是 governor 效果**: 混淆训练效果 vs 物理效果是常见错误. **新规则: governor on/off 对比必须 zero-action no-SAC, 隔离物理效果**.
3. **plan-driven empirical sweep ROI 极高**: V1+V2+V3 plan ~5 min wall, 14 eval, 3 个高密度信号. 比纯 code audit (R06 ~30 min) 信号密度更高. **新规则: physics validation 要 empirical sweep first, 然后 audit code**.
4. **Plan 来源不是只 AI** — user 提供的 physics_validation_plan.md 比我 R07 提的 R08 audit plan (4 个 audit) 更直接. **新规则: 用户写的 plan 优先, AI 整合不机械替换**.

---

## §5 信号 / wall ratio

| Round | wall | 信号 | ratio |
|---|---|---|---|
| R01-R04 | 120 min | 1 | 1/120 极低 |
| R05 | 20 min | 8 | 8/20 高 |
| R06 | 30 min | 3 | 3/30 中高 |
| R07 | 20 min | 2 | 2/20 中高 |
| **R08** | **15 min** | **3 高密度** (H 响应正常 + 2× 残差 + governor 无效) | **3/15 = 高** |

R05-R08 共 ~85 min wall, 锁定 root cause:
1. eval 公式 bug (R06+R07 修)
2. governor wiring 失效 (R08 找到)
3. 平台 2× 残差 (R08 量化)

vs R01-R04 同期 120 min 0 root cause. **新工作流 (Explore→Audit) ROI ~10× 老工作流**.

---

## §6 R09 衔接立刻可干

最高 ROI: 修 V3 env governor wiring. 估 30 min:
- 读 ANDES IEEEG1/EXST1 doc (5 min)
- 验证 GENROU 是否自动连接 (10 min, 1 个 ANDES eval)
- 若没连, 手动 wire (10 min code)
- 重跑 V2 对比验 fix (5 min eval)

后跑通了再做副线平台 audit.

---

*Generated by main agent, 2026-05-07. Script: scripts/research_loop/r08_h_scan.py.*
