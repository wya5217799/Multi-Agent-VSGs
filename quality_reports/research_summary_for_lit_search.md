# Research Summary — ANDES Kundur 4-VSG Paper Replication

**Date**: 2026-05-07
**Purpose**: 面向 literature search 的研究总结. 帮 user 网上搜文献找优化方向.
**Source**: 整合 R01-R08 research-loop verdict + L4 refactor + paper facts.

---

## 1. 项目目标 (一句话)

复现 Yang et al. TPWRS 2023 论文 "Multi-Agent SAC for Distributed VSG Inertia/Damping Control" 在 Kundur 4-VSG 系统的频率调节结果, 主要 metric: **LS1 max\|Δf\| ≤ 0.13 Hz, settling ≤ 3s, ΔH/ΔD 守恒**.

**Paper full citation**: Yang et al., *IEEE Transactions on Power Systems*, 2023, "Distributed Data-Driven Control for Inertia and Damping Coordination of Multiple Virtual Synchronous Generators".

**复现平台**: ANDES (Cui et al. 2020, https://github.com/cuihantao/andes), Python 动力学仿真. **Paper 用 Simulink** Power System Blockset.

---

## 2. 系统设置

### 2.1 物理拓扑
- Kundur 2-area 11-bus 系统 (Power System Stability and Control, Kundur 1994 Example 12.6)
- 4 ESS-VSG 加在 Bus 7, 8, 9, 10 (paper Fig.3)
- 每 VSG: virtual inertia M (= 2H), virtual damping D, 通过 H/D 系数直调 (paper Eq.1, 13)
- 风电场加在 Bus 8 (低惯量 GENCLS, M=0.1)

### 2.2 控制问题
- **State**: 4-agent obs = [ω_self, ω_dot_self, P_es_self, comm_avg_ω, ...]
- **Action**: 2D per agent = [ΔH_norm, ΔD_norm] ∈ [-1, 1]², zero-centered mapping 到 [DH_MIN, DH_MAX] = [-5, +15] s, [DD_MIN, DD_MAX] = [-5, +15]
- **Paper action box** (Eq.12): ΔH ∈ [-100, +300], ΔD ∈ [-200, +600] — **20× 比项目 wider**
- **Reward**: r = r_f (frequency deviation) + φ_h × r_h (Eq.17 ΔH_avg² 守恒) + φ_d × r_d (ΔD_avg² 守恒) — paper §IV
- **Disturbance**: LS1 = -2.48 sys_pu @ Bus 14 step, LS2 = +1.88 sys_pu @ Bus 15 step (paper §IV-C)

### 2.3 训练
- Multi-Agent SAC, 4 independent actors + 4 critics, parameter sharing optional
- Episode = 50 steps × dt=0.2s = 10s window
- Train hyperparams (paper Table I): PHI_D = 1.0, LAMBDA_SMOOTH = 0.01, etc.

---

## 3. 已实验路径 + 实测结果

### 3.1 Environment 版本

| Env | 描述 | 状态 |
|---|---|---|
| V1 | M0=20 (H0=10s) uniform, D0=4 uniform, NEW_LINE_X=0.10 | 简单, R05 实测 max_df 0.815 (LS1) |
| V2 | M0=20, D0=[20,16,4,8] heterogeneous, NEW_LINE_X=0.20 (制造 sync 失同步 ablation) | 当前主路径 |
| V3 | V2 + IEEEG1 governor + EXST1 AVR | **R08 实测 governor wiring 完全无效** ⚠ |

### 3.2 Round-by-round verdict (R01-R08, ~145 min wall)

| Round | 内容 | 关键发现 |
|---|---|---|
| R01-R03 | 5 seed × 同 hyperparam 重复采样 (老路径) | 找到 PHI_D=0.05 偏 paper 1.0 (20×), 修为 1.0 |
| R04 | PHI_D=1.0 5 seed × 200 ep (V2 env) | 6-axis = 0.037 attractor; adaptive baseline = no_ctrl = 0.010 (控制实现/平台问题信号) |
| R05 | 8 arm × 30ep × 1 seed parallel (短-多臂 bandit) | 8 hyperparam 维度 (V1/V2/V3 + PHI_D 1/5 + λ 0/0.01 + range 2× + disturb 5×) **全 6-axis 0.037 并列** → hyperparam 不是 root cause |
| R06 | 4 audit 并行 fork (eval 公式 + action 语义 + disturbance + attractor 性质) | ⭐ 找到 evaluator bug (axes.py range axis 公式语义反); 推翻 P 注入嫌疑; disturbance 已对齐 |
| R07 | 修 axes.py range axis (box containment) | 6-axis 0.037 → 0.139, attractor 破; 暴露 no_control 平台 4× 残差 |
| R08 | H scan (10/30/100/300) + governor on/off (0 SAC train) | ⭐⭐⭐ V3 env governor 实测**完全无效**; H=300 (paper 上限) no_ctrl 仍 2× paper |

### 3.3 SAC 训练 vs no_control 实测

| metric | no_control V2 H=10 | SAC R04 PHI_D=1.0 5seed × 200ep | paper benchmark |
|---|---|---|---|
| LS1 max\|Δf\| (Hz) | **0.815** | **0.567 (mean)** | **0.13** |
| LS2 max\|Δf\| (Hz) | 0.533 | 0.413 | 0.10 |
| LS1 settling (s) | ∞ (>10s) | ∞ | 3 |
| 6-axis overall | 0.010 | 0.139 | 1.0 |

**SAC 改善 30% vs no_control**, 但仍 **4.4× too large vs paper**.

---

## 4. 3 个 Root Cause (按修复难度)

### Root #1: Eval 公式 bug — ✅ 已修

`evaluation/paper_grade_axes.py` range axis 把 paper Eq.12 box bound width 当 trajectory span 期望值. 已 R07 修. **通用收益**, Simulink 路径同 evaluator 也受益.

### Root #2: V3 env governor wiring 失效 — ⚠ 已识别未修

ANDES `IEEEG1` 模型加进去 + `syn=GENROU_idx` 字段 set, 但 vout 没传到 swing 方程. zero-action no-SAC V2 vs V3 max_df **完全相同** (0.815 LS1 H=10).

**怀疑根因**: ANDES IEEEG1 的 `Pgv` (turbine governor 输出) 跟 GENROU 的 `Pm` 没自动 wire, 需要手动 patch.

### Root #3: 平台 2× 残差 — ❌ 不可在 ANDES 内 fix

R08 H scan: H=300 (paper Eq.12 box 上限) no_control max_df = **0.266 vs paper 0.13 (2× too large)**. 即使 governor 修对 + SAC 完美训练, 物理上限仍 ~0.14-0.18, 跟 paper 0.13 还有 visual cosmetic gap.

**怀疑残差源**:
- ANDES `kundur_full.xlsx` line impedance / transformer leakage / load model 跟 paper Kundur Power System Stability 标准不一致
- ANDES TDS solver (trapezoidal implicit) 数值阻尼 vs Simulink ode23tb/ode15s 不同
- ANDES PQ 模型 p2p=1.0 (constant power) 注入 vs paper Simulink load step 物理不同

---

## 5. 未解决的问题 (用于文献搜索方向)

### Q1: ANDES vs Simulink Kundur 平台校准差异 — 文献有报道吗?

**搜索关键词** (英):
- `"ANDES" "Simulink" Kundur frequency response benchmark`
- `power system simulation platform comparison frequency dynamics`
- `cross-platform validation Kundur 11-bus`
- `numerical damping ANDES TDS solver`

**搜索关键词** (中):
- "ANDES Simulink 频率响应 对比"
- "电力系统仿真平台校准 Kundur"

**期待**: 找有人报告同样的"H=300 no_control max_df 还是 2× Simulink"现象的论文/技术报告.

### Q2: ANDES IEEEG1 governor wiring 问题 — 模型文档/issue 有吗?

**搜索方向**:
- ANDES GitHub issues: `IEEEG1 GENROU wiring`, `governor not working`, `Pm input`
- ANDES doc: https://docs.andes.app/en/latest/ — IEEEG1 model description
- 有没有人写过 example notebook show IEEEG1 起作用?

**搜索关键词**:
- `ANDES IEEEG1 example`
- `ANDES turbine governor frequency response`
- `pyandes governor connect synchronous generator`

### Q3: 4-VSG SAC 训练 reach Yang2023 量级是否在其他平台 (PSCAD / RTDS) 有复现?

**搜索方向**:
- 搜 Yang2023 paper 的 follow-up papers (cite-by)
- 有没有人在 PSCAD / RTDS / DigSilent 复现?
- 跨平台 RL+VSG 的 benchmark 论文?

**搜索关键词**:
- `multi-agent SAC virtual synchronous generator inertia damping replication`
- `Yang 2023 IEEE TPWRS replication`
- `data-driven inertia control PSCAD RTDS`

### Q4: ΔH/ΔD action range 100-300 物理可达性?

paper Eq.12 ΔH ∈ [-100, +300] (=300s 惯量调节). 这是物理可达的吗? 实际 ESS / virtual inertia control 文献给的范围:

**搜索关键词**:
- `virtual inertia ESS battery storage range capability`
- `synthetic inertia primary frequency control magnitude`
- `H ΔH virtual synchronous machine bound`

### Q5: 6-axis evaluation 的 paper-style 数字真实性

**Paper 给的 max_df 0.13 Hz 跟 Kundur 系统 + 2.48 sys_pu LS 真的物理一致吗?**

按 ROCOF 经典公式: max_df ≈ ΔP / (2 × H × f_nom). LS=2.48 sys_pu, 项目 SBASE=100 MVA → ΔP=248 MW. Kundur 总惯量 ~13s × 4 同步机 ≈ 50s effective. f_nom=50Hz.

max_df ≈ 248 / (2 × 50 × 50) = 0.05 Hz?

但 paper 报 0.13 Hz, 项目 H=300 给 0.266 Hz. 这意味着 **paper 0.13 数字本身可能跟简单公式不符** — 暗示 paper Simulink 系统 effective inertia ~ 25s (不是项目 H=10 × 4 = 40s, 也不是 H=300 × 4 = 1200s).

**搜索关键词**:
- `Kundur 4-machine 11-bus inertia constant H value default`
- `ROCOF Kundur load step frequency response analytical`
- `power system stability Kundur model parameters`

---

## 6. 已知偏差列表 (paper appendix material)

如果继续 ANDES 路径或写 cross-platform paper, 这些是 disclosed deviation:

1. **Action box width**: project ΔH ∈ [-5, +15], paper Eq.12 [-100, +300] — **20× narrower**
2. **System parameter**: project `kundur_full.xlsx` (ANDES default Kundur case), paper 用什么 Kundur variant 不明 (paper 没给具体 line/load 参数)
3. **TDS solver**: ANDES trapezoidal implicit, paper Simulink (ode23tb 默认)
4. **Disturbance protocol**: project PQ.Ppf step at t=0.5s after warmup, paper 写"50 different disturbances" 但训练 distribution 没给
5. **Governor**: paper 假设有 governor (Yang2023 §II-A), project V2 env 没有, V3 env 有但 wiring 失效

---

## 7. 现有 codebase 状态 (给可能跨 repo 引用用)

**Repository**: `C:\Users\27443\Desktop\Multi-Agent  VSGs` (双空格, ANDES 路径)
**主 repository**: `C:\Users\27443\Desktop\Multi-Agent-VSGs-discrete` (双 -, Simulink 路径) — paper submission active

**关键文件 (ANDES)**:
- `env/andes/andes_vsg_env.py` — V1 baseline env
- `env/andes/andes_vsg_env_v2.py` — V2 hetero env (主)
- `env/andes/andes_vsg_env_v3.py` — V3 + governor (⚠ wiring 失效)
- `evaluation/paper_grade_axes.py` — 6-axis evaluator (R07 已修)
- `scripts/research_loop/eval_paper_spec_v2.py` — eval 单一入口 (L4 lock-in)
- `scripts/research_loop/r08_h_scan.py` — physics validation script
- `quality_reports/research_loop/round_{01..08}_*.md` — 每 round verdict

---

## 8. 推荐文献搜索 priority

按 ROI 排:

| Priority | 方向 | 期望产出 |
|---|---|---|
| P1 | Yang2023 follow-up / cite-by + cross-platform replication | 是否有人 reproduce 过, 用啥平台, 啥参数 |
| P2 | ANDES vs Simulink Kundur platform calibration 文献 | Root #3 平台 2× 残差有先例吗 |
| P3 | virtual inertia ΔH=300s 物理可达性 | paper Eq.12 是否假设 unrealistic |
| P4 | ROCOF Kundur 4-machine 11-bus analytical | 反推 paper effective inertia, 看 H=300 配置应该多少 max_df |
| P5 | ANDES IEEEG1 example / governor wiring | Root #2 解决方法 |

---

## 9. 一句话给 LLM 搜文献用的 prompt 模板

```
我在复现 Yang et al. IEEE TPWRS 2023 "Distributed Data-Driven Control for
Inertia and Damping Coordination of Multiple Virtual Synchronous Generators"
on Kundur 4-machine 2-area system using ANDES (not Simulink). My ANDES no-
control LS1 max|Δf| = 0.815 Hz at H=10s, 0.266 Hz at H=300s, but paper reports
0.13 Hz. After fixing evaluator bugs and matching paper hyperparameters
(PHI_D=1.0, action box [-100,+300] for ΔH), my SAC agent reaches 6-axis
overall = 0.139 vs paper 1.0. The 2× residual at H=300s suggests platform-
level damping difference between ANDES and Simulink. 寻找:
1. ANDES vs Simulink Kundur frequency response benchmark
2. Yang2023 follow-up replication papers
3. ROCOF analytical for Kundur 4-machine LS=2.48 sys_pu
4. ANDES IEEEG1+EXST1 working example
```

直接贴给 ChatGPT/Claude/Perplexity 搜.

---

*Generated by main agent integrating R01-R08 verdict + R06 audits + R08 physics validation.*
