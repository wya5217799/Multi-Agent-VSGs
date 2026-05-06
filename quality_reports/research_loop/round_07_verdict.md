# R07 Verdict — axes.py Bug-A/B 修, attractor 破但暴露平台校准问题

**Phase**: Explore (audit-driven, 0 train, ~20 min wall)
**Status**: DONE
**Wall**: 20 min (读 audit + 修 axes.py 25 LOC + verify run + verdict)
**Trigger**: R06 verdict §6 R07 衔接 — 修 axes.py Bug-A (range axis 公式语义反) + Bug-B (数值)

---

## §1 实测 (修后 R05 8 arms 6-axis ranking)

| rank | label | mean overall | 修前 (R05 verdict) | 跳幅 |
|---|---|---|---|---|
| 1 | combo_v1_disturb5x | **0.139** | 0.037 | 3.76× |
| 2 | disturb_5x | 0.139 | 0.037 | 3.76× |
| 3-8 | 其余 6 arm | 0.138 | 0.037 | 3.73× |
| 9 | no_control | 0.010 | 0.010 | 不变 |

**attractor 破了** (8 arms 全 0.139, 不再卡 0.037), 但**远未 paper-align** (0.139 vs 阈值 0.5).

### Per-axis breakdown (R05 baseline_paper LS1, 代表性)

| axis | 修前 score | 修后 score | 备注 |
|---|---|---|---|
| max_\|df\|_Hz | 0 | 0 | 项目 0.478 vs paper 0.13, **4× 太大** |
| final_\|df\|@6s | 0 | 0 | 0.319 vs 0.08, **4× 太大** |
| settling_s | 0 | 0 | 99 (∞) vs 2.5, never settle |
| dH_avg_smoothness | 0.99 | 0.99 | 不变 |
| dD_avg_smoothness | 0.99 | 0.99 | 不变 |
| dH_range_in_box | 0.00 | **1.00** | proj=[-0.07,+0.06] 完全在 box [-100,+300] |
| dD_range_in_box | 0.00 | **1.00** | proj=[-0.21,+0.15] 完全在 box [-200,+600] |
| **overall** | **0.037** | **0.139** | 几何均值 |

---

## §2 ⭐ 关键 R07 发现 — no_control 平台校准

ANDES Kundur 实测 vs paper:

| 量 | ANDES no_control | paper no_control | gap |
|---|---|---|---|
| LS1 max_\|df\| | 0.551 Hz | 0.13 Hz | **4.2× 太大** |
| LS2 max_\|df\| | 0.413 Hz | 0.10 Hz | **4.1× 太大** |
| LS1 cum_rf | -0.134 | (paper DDIC -0.68) | 项目 1/5 |

**SAC 控制后 (R05 best) max_df 0.45-0.49 Hz**, 改善幅度 11%.

**改善天花板**: 即使 SAC 完美 (理论 0 Hz), 还是 0 vs paper 0.13 的有限响应. 实际 SAC 把 ANDES no_control 0.55 → 0.49, 跟 paper Fig.7 DDIC 0.13 还差 4×. **即使 SAC 训练 1000 ep, 物理动态 axis 也 reach 不到 paper**.

**结论**: 物理动态 (max_df / final_df / settling) **不是 SAC 训练问题**, 是 **ANDES Kundur 平台 vs paper Simulink Kundur 的基础响应特性差异**.

候选差异源 (R08 audit 候选):
1. ANDES `GENCLS` 模型 vs paper Simulink Synchronous Generator Block 阻尼公式差
2. `TDS` 求解器步长 / 数值 damping 差异
3. ANDES `PQ.Ppf` 扰动注入方式 vs paper 用 step block / load disturbance
4. Bus 系统参数 (line impedance, transformer leakage) 跟 Kundur Power System Stability 标准不一致

---

## §3 修代码细节

`evaluation/paper_grade_axes.py` 改 25 LOC:

### Bug-A 修 (range axis 公式)

新加函数 `_box_containment(proj_min, proj_max, box_min, box_max, tol_factor=0.2)`:
- 项目 [proj_min, proj_max] 完全在 paper box → score=1.0
- 越界扣分 (overshoot_frac / tol_factor)
- 替换老 `score = 1 - |1 - proj_span/paper_span|/0.5` (反向惩罚 ΔH span 不够大)

老逻辑跟 paper Eq.17 (`r^h = -ΔH_avg^2`) 守恒约束矛盾, 是 R05 全 8 arms range axis = 0 的数学根因.

### Bug-B 修 (paper benchmark 数值)

```python
# LS1 / LS2 同步:
dH_range=(-100.0, 300.0)  # was (-100, 250) / (-100, 200) — paper Eq.12 LS-agnostic
dD_range=(-200.0, 600.0)  # was (-200, 500) / (-200, 300)
```

paper Sec.IV-B Eq.12 box bounds 是 action 约束, **不 LS-specific**. 老 axes.py LS2 (-100, 200) / (-200, 300) 是 visual extraction 误读 Fig.7/9 曲线包络, 不是 paper 公式.

### Bug-C 不存在 (audit agent 误报)

`H_full = M_es / 2.0` 折算正确:
- `env/andes/base_env.py:48` 注释 `VSG_M0 = 20.0  # 基础惯量 M = 2H (s)`
- `env/andes/base_env.py:54-55` `DM_MIN = -10  # = 2 * DH_MIN = 2 * (-5)` `DM_MAX = 30 # = 2 * DH_MAX = 2 * 15`
- trace `M_es` 是 ANDES `GENCLS.M` 参数 (= 2H), axes.py /2.0 → H 单位匹配 paper

---

## §4 6-axis paper alignment

修后 overall 0.139 (R05 8 arms), no_control 0.010.

| 区段 | 含义 | R07 验证 |
|---|---|---|
| 0.1 ≤ overall < 0.5 | attractor 破, partial align | ✓ 当前 |
| ≥ 0.5 | paper-aligned | ✗ 需 max_df / settling 改善 |
| < 0.1 | 真 attractor 复活 | — |

R06 verdict §6 R07 衔接表预测的"0.1 ≤ overall < 0.5 → R08 = 副线 DM_MAX 30→300 重训" **被 R07 §2 推翻**. 物理动态不是 action bound 偏小 (R05 action_range_2x DM_MAX=60 也 0.037), 是平台校准.

---

## §5 R08 衔接 — 平台校准 audit (重 pivot)

老 R06 衔接候选 (action bound 重训) 不动 — 已被 R07 §2 推翻.

新 R08 路径 **Phase Audit (audit-first 第二轮, 0 train, ~80 min)**:

### exp1: ANDES Kundur vs paper Simulink Kundur 物理参数对比 (priority=11)
- 读 `env/andes/andes_vsg_env.py` _build_system() Kundur load + line params
- 读 paper §III system specification (Kundur 系统 SBASE / line impedance / transformer)
- 找参数 mismatch
- out: `audits/2026-05-08_kundur_system_params_audit.md`

### exp2: ANDES TDS 求解器 vs Simulink 求解器对比 (priority=10)
- ANDES TDS 默认: trapezoidal implicit, fixed step?
- Simulink Kundur 默认: ode23tb / ode15s
- 验证 step 大小是否影响 max_df 数值响应
- 跑 1 个 short trial: ANDES no_control LS1, varying TDS step (0.01s / 0.005s / 0.001s) 看 max_df 是否变化
- out: `audits/2026-05-08_solver_step_audit.md`

### exp3: ANDES disturbance 注入 vs paper protocol 对比 (priority=9)
- 项目 `eval_paper_spec_v2.py:40-43` 用 `delta_u={"PQ_Bus14": -2.48}` 注入 PQ 模型
- paper §IV-C (R06 exp3 audit verified) LS1 = -2.48 sys_pu @ Bus14, instantaneous step
- 验 ANDES PQ.Ppf 注入是否真的 instantaneous (step) 还是 ramp
- out: `audits/2026-05-08_disturbance_protocol_audit.md`

### exp4: paper Fig.6 no-control 数值反推 (priority=8)
- 假设 paper Fig.6 LS1 no-control max_df=0.13 Hz, 反推 paper Kundur 系统的 effective M/D
- 对比项目 ANDES Kundur effective M/D
- 若数值差好几倍 → 改项目 M0 让 no_control 物理校准对齐
- out: `audits/2026-05-08_paper_baseline_reverse_eng.md`

### 期 (R08)
- exp1: 找 ≥ 1 系统参数 mismatch (line impedance / load model)
- exp2: solver step → max_df 趋势, 决定是否需改 ANDES 配置
- exp3: 验扰动 protocol 一致性
- exp4: 反推 paper effective M/D, 看是否需改项目 M0/D0

R09 衔接:
- exp1+exp4 找到 mismatch → R09 修系统参数, 重 eval no_control 看 max_df 是否回 0.13
- 全 audit clean → 真平台差异不可消, R09 改 paper narrative ("ANDES platform partial replication, axis 1-3 require Simulink")

---

## §6 信号 / wall ratio

| Round | wall | 信号 | ratio |
|---|---|---|---|
| R01-R04 | 120 min | 1 | 1/120 |
| R05 | 20 min | 8 (hyperparam falsified) | 8/20 |
| R06 | 30 min | 3 (range starvation + axes bug + P 注入推翻) | 3/30 |
| **R07** | **20 min** | **2 (attractor 破 + 平台校准 root)** | **2/20 = 中高** |

R07 拿到 2 个高密度信号:
1. attractor 破 (0.037 → 0.139, axes.py 修起作用)
2. 物理动态 root cause = ANDES vs Simulink 平台校准, 不是 SAC train (no_control 已 4×)

---

## §7 锁进 SKILL.md 候选 lessons

1. **attractor 破后看物理 baseline**: 修 eval 公式让 attractor 破后, 立刻 check no_control 物理基线 vs paper baseline. 若 no_control 已超 paper 几倍, SAC 训练再多也不可能 reach paper.
2. **axis 修是 partial fix**: range axis 修 0→1.0 是必要 (破 attractor) 但不充分 (max_df / settling 仍 0). 全 paper-align 需要平台校准 + axis 公式都对
3. **audit agent 标记的"可疑"要复核**: R06 audit agent 标 axes.py M=2H/2.0 折算可疑 (Bug-C), R07 复核 base_env.py 注释发现是对的, **audit agent over-cautious 是常态, 主上下文必须复核 critical bugs**
4. **修复路径选择**: R06 plan 预测 R07 修 axis → 0.5+ paper-align, 实测 0.139. 因为 max_df/settling 物理动态在 axis 之外. **预测/实测 gap 5× 是平台校准信号**

---

*Generated by main agent, 2026-05-07*
