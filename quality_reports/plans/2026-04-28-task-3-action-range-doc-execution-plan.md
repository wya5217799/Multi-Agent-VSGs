# Task 3 — Action Range Q7 Ambiguity 文档化 — 落实执行计划

**Date:** 2026-04-28
**Goal:** 显式声明 v3 ΔM/ΔD 范围与 paper line 938-939 字面值的关系, 把
当前 deviation 从"隐式"升级为"documented", 在 Q7 H 单位歧义解决前不强
行机械采纳 paper 数字。
**Paper PRIMARY:** line 938-939 — "ΔH ∈ [-100, 300], ΔD ∈ [-200, 600]"
**Pre-req:** Task 1 + Task 2 PASS (modeling layer 已完整 paper-aligned)
**Constraint:** **doc only**, 不动任何代码 / .slx / runtime.mat / IC
/ env / build / NR / config 数值常量。
**Tool:** 无需 simulink-tools — 纯 markdown 编辑。`Read` / `Edit` /
`Write` 即可。

---

## 0. 背景回顾

### 0.1 Paper 原文 (line 938-939)
> "The parameter range of inertia and droop for each energy storage is
> from −100 to 300 and from −200 to 600, respectively."

数字明文。ΔH ∈ [-100, 300], ΔD ∈ [-200, 600]。

### 0.2 Paper Eq.1 (line 250)
$$H_{esi}\Delta\dot{\omega}_i + D_{esi}\Delta\omega_i = \Delta u_i - \Delta P_{esi}$$

- 无 `2` 系数
- 无 `ω_s` 系数
- H 单位 paper **未明示**

### 0.3 Q7 状态 (`docs/paper/yang2023-fact-base.md` §8)
- H_es,i 的量纲 (秒? p.u.? 无量纲?) **未解**
- H_es,0 baseline 数值 **paper 未给**
- 项目工作假设 H_paper = 2·H_code (M=2H 经典电机) 是**项目推断**, 非
  论文事实

### 0.4 v3 现状 (PRIMARY 验证)
- `scenarios/config_simulink_base.py`: `DM_MIN=-3, DM_MAX=+9, DD_MIN=-1.5,
  DD_MAX=+4.5`
- ESS_M0=24 (= H_code=12), ESS_D0=4.5 (vsg-pu)
- Phase C 实证: ΔM > +30 / ΔD > +15 已撞物理 floor (M_FLOOR=1, D_FLOOR=0.5)
- L0 (= 当前) 是唯一 Phase C 验证物理可行的 ladder

### 0.5 Paper 立场推断
若 paper-literal 采纳 ΔM=[-100,300], 则:
- M_min = ESS_M0 + ΔM_min = 24 - 100 = -76 → 必撞 floor (clip 到 1)
- 87% action space 无效 (Phase C C-BLOCKER-1 已实证)
- SAC actor 输出大部分动作被 clip → 训练崩溃

机械采纳 = 反物理。documenting deviation 是最负责任的对齐方式。

---

## 1. 影响文件清单

| 文件 | 当前状态 | 修改类型 |
|---|---|---|
| `docs/paper/action-range-mapping-deviation.md` | 不存在 | NEW (主输出) |
| `docs/paper/yang2023-fact-base.md` | Q7 段不指向新文档 | EDIT (在 Q7 段加交叉引用) |
| `scenarios/config_simulink_base.py` | DM/DD 常量无注释指向 paper deviation | EDIT (添 docstring 顶部注释指向新文档) |

> **REVIEW NOTE (1):** 三处足够 — 新主文档 + fact-base 交叉引用 + 代码
> 注释指针。**不**改 DM/DD 数值常量本身。

---

## 2. Pre-flight

### 2.1 文档目录确认
`Bash` 确认 `docs/paper/` 目录存在 (从已读的 `yang2023-fact-base.md`
可知存在)。无需新建目录。

### 2.2 现状 PRIMARY 验证
| Step | Tool | 目的 |
|---|---|---|
| 2.2.a | `Read` `scenarios/config_simulink_base.py` | 找 DM_MIN/DM_MAX/DD_MIN/DD_MAX 常量定义行号 + 现有 docstring (如有) |
| 2.2.b | `Grep` `DM_MIN\|DM_MAX\|DD_MIN\|DD_MAX` | 找所有引用点 (确认改注释不影响代码) |
| 2.2.c | `Read` `docs/paper/yang2023-fact-base.md` Q7 段 | 找 §8 Q7 对应行号 + §10 deviation 表对应行号 (用于交叉引用插入位置) |

> **REVIEW NOTE (2.2):** 这三步 PRIMARY, 防止盲改 fact-base 里语义不
> 清的字段。

---

## 3. 主文档 `action-range-mapping-deviation.md` 结构

### 3.1 章节大纲

```
# Action Range Mapping Deviation — Yang 2023 Paper vs v3 Implementation

## 1. Paper PRIMARY (直接引文)
   1.1 Action range (line 938-939 原文 + 链接)
   1.2 Eq.1 (line 250 公式 + H/D 单位描述缺失)

## 2. v3 Implementation State (PRIMARY 源码引用)
   2.1 DM/DD constants (file:line)
   2.2 Initial baselines (M0=24, D0=4.5)
   2.3 Floor constants (M_FLOOR=1, D_FLOOR=0.5)

## 3. The Deviation
   3.1 数值差距 (literal 33-133× narrower)
   3.2 单位歧义 (Q7 — H_es,i 是 s? pu? 无量纲?)
   3.3 H_es,0 baseline (paper 未给, 项目选 12 vsg-base)

## 4. Why Not Adopt Paper-Literal Range
   4.1 Phase C 实证 floor clip (link to verdict)
   4.2 ΔM=-100 → M=-76 → clip 到 floor=1
   4.3 87% action space 无效 → SAC 不可训练
   4.4 反推: 若 ESS_M0=150 让 paper-literal 范围有效, 偏离 [49] 经验值

## 5. The Working Assumption (项目推断, 非论文事实)
   5.1 H_paper = 2·H_code (M=2H 经典电机形式)
   5.2 → 项目 ΔM=[-3,9] ≈ paper-equivalent ΔH=[-1.5, 4.5]
   5.3 仍 33× narrower than paper-literal [-100, 300]
   5.4 Disclaimer: 这是推断, 不是 paper 事实

## 6. Decision: Document Don't Adopt
   6.1 三条路径 (E-doc / E-paper-literal / E-paper-equivalent)
   6.2 选 E-doc 理由 (Q7 未解 + Phase C 实证)
   6.3 透明度高于盲目对齐

## 7. Resolution Path (Q7 解决后再考虑)
   7.1 何时可重审: paper 作者邮件 / 同领域文献交叉印证 / TPWRS 习惯调研
   7.2 重审决策树
   7.3 如果 H_paper 单位真是某 pu, 项目可能要重新 calibrate ESS_M0/D0

## 8. References (PRIMARY 引证)
   8.1 Paper line 938-939, 250
   8.2 Phase C verdict (results/harness/kundur/cvs_v3_phase_c/...)
   8.3 fact-base Q7 §8
   8.4 env/ode/NOTES.md M1 段
   8.5 scenarios/config_simulink_base.py:DM_MIN..

## 9. Status
   9.1 当前 v3 状态: documented deviation
   9.2 状态变更条件: Q7 解决 + 项目决议重 calibrate
   9.3 维护责任: 项目主线
```

### 3.2 关键内容要求

每节必须:
- 含 paper PRIMARY 行号 (line 250 / 938-939)
- 含 v3 PRIMARY 文件:行号 (config_simulink_base.py:DM_MIN..)
- 含 Phase C verdict 引用 (实证依据)
- 区分 "paper 事实" vs "项目推断"
- 区分 "deviation" vs "alignment"

> **REVIEW NOTE (3.2):** 避免文档自身 hallucinate paper 字段。所有
> "paper 这样说" 必须有 line 号; 所有 "项目这样推断" 必须明确标注。

---

## 4. fact-base 交叉引用 EDIT

### 4.1 §8 Q7 段
找当前 Q7 行 (含"H_es,i 的量纲"内容), 在描述末尾加:
```markdown
> **2026-04-28 update:** Q7 处理决策 documented in
> `docs/paper/action-range-mapping-deviation.md` (Task 3). 当前 v3
> 保持 ΔM=[-3,9]/ΔD=[-1.5,4.5] 作 documented deviation, 在 Q7 解决前
> 不机械采纳 paper-literal [-100,300]/[-200,600]。
```

### 4.2 §10 偏差备案
找"动作范围"行, 加 reference 链接到新文档:
```markdown
| 动作范围 | $\Delta H \in [-100,300]$, $\Delta D \in [-200,600]$
         | $\Delta M \in [-3,9]$ (M=2H), $\Delta D \in [-1.5,4.5]$
         | 不同的基值 (H₀/D₀ scale 不同); **详见 `docs/paper/action-range-mapping-deviation.md`** |
```

> **REVIEW NOTE (4):** 不改 fact-base 已有的事实陈述, 只加交叉引用。

---

## 5. (可选) `config_simulink_base.py` 注释 EDIT

如果 DM/DD 常量定义处无 paper deviation 注释, 加 docstring:
```python
# Action range deviation from Yang 2023 paper line 938-939
# (ΔH=[-100,300], ΔD=[-200,600]) — current v3 uses 33× narrower range.
# Rationale: paper Eq.1 H unit ambiguous (Q7 unresolved); Phase C
# empirically shows wider ladders hit physical floor.
# Full deviation analysis: docs/paper/action-range-mapping-deviation.md
DM_MIN = -3
DM_MAX = 9
DD_MIN = -1.5
DD_MAX = 4.5
```

> **REVIEW NOTE (5):** 可选 — 看现有注释覆盖度。如果已有充分注释, 仅
> 加文件链接即可。这一步是 "code → doc 链接闭环"。

---

## 6. Acceptance gate (5 项)

| # | Gate | 通过判据 |
|---|---|---|
| 1 | `docs/paper/action-range-mapping-deviation.md` 存在 + 9 节齐全 | 文件存在 + grep 9 个 H1/H2 标题 |
| 2 | Paper PRIMARY 行号 (line 938-939, line 250) 引用至少各 1 次 | grep |
| 3 | v3 PRIMARY (`config_simulink_base.py` 文件名 + 常量名) 引用 | grep |
| 4 | Phase C verdict 路径引用 | grep `cvs_v3_phase_c` |
| 5 | fact-base §8 Q7 + §10 deviation 表已加交叉引用 | grep `action-range-mapping-deviation` in fact-base |

**全 5 PASS = Task 3 完成。**

---

## 7. Risk register (4 项, 全 LOW)

| ID | Risk | Mitigation |
|---|---|---|
| R3-1 | 文档误引 paper 行号 (typo) | §3.2 要求每个引用必带 line 号; 写完用 `Read` 在 paper transcription 复核 |
| R3-2 | fact-base 误改 (改了已有事实而非添加 update) | §4 EDIT 用 append 模式, 不删除已有内容 |
| R3-3 | config_simulink_base.py 添注释意外改 DM/DD 数值 | §5 仅加 docstring, **不**改常量赋值; 写完用 `Bash python -c "from scenarios.config_simulink_base import DM_MIN, ...; print(...)"` 验证常量数值未变 |
| R3-4 | "项目推断" 与 "paper 事实" 混淆 | §3.2 显式 disclaimer + §5.4 重申; reviewer 通读时关注此一致性 |

---

## 8. Stop conditions

- Paper line 938-939 / 250 引证错误 (引到错段) → 重核
- fact-base §8 / §10 找不到 (结构变了) → 看 fact-base 当前 schema 决定
  插入位置
- DM/DD 常量数值意外改动 → 立即 revert

---

## 9. 执行步骤 (~30 min)

```text
A. Pre-flight (5 min)
   A1. Read scenarios/config_simulink_base.py — 找 DM_MIN..DD_MAX 常量
       行号 + 当前注释覆盖度
   A2. Read docs/paper/yang2023-fact-base.md §8 Q7 + §10 deviation 表
   A3. (可选) Re-read paper line 250 + 938-939 确认引文准确

B. 主文档写作 (15 min)
   B1. Write docs/paper/action-range-mapping-deviation.md (9 节)
   B2. 用 §3.1 大纲 fill in content, 每节带 PRIMARY 引证

C. fact-base 交叉引用 (5 min)
   C1. Edit §8 Q7 段加 update note + 文档链接
   C2. Edit §10 deviation 表加 doc 链接

D. (可选) 代码注释 (3 min)
   D1. Read config_simulink_base.py DM/DD 段
   D2. Edit 加 docstring 指向新文档
   D3. Bash python -c verify 常量数值未变

E. Acceptance verify (2 min)
   E1. grep 5 个 gate 全过

F. Verdict (5 min)
   F1. Write results/harness/kundur/cvs_v3_task_3/task_3_verdict.md
   F2. (可选) Git commit
```

---

## 10. 不在 Task 3 scope

- ❌ **不改** DM/DD/M_FLOOR/D_FLOOR 数值常量
- ❌ **不改** ESS_M0/ESS_D0 baselines
- ❌ **不改** build / NR / IC / runtime.mat / .slx / env disturbance
       dispatch / SAC / reward / paper_eval / NE39 / v2 / SPS
- ❌ **不动** Task 1 + Task 2 已完成 modeling layer 状态
- ❌ **不重新** discuss Q7 解决 (留给未来 paper 作者邮件 / 同领域文献
      调研)

---

## 11. 输出

| 路径 | 内容 |
|---|---|
| `docs/paper/action-range-mapping-deviation.md` | NEW — 主 deviation 文档 (9 节) |
| `docs/paper/yang2023-fact-base.md` | EDIT — §8 Q7 + §10 deviation 表加交叉引用 |
| `scenarios/config_simulink_base.py` | (可选) EDIT — DM/DD 常量上加 docstring 链接 |
| `results/harness/kundur/cvs_v3_task_3/task_3_verdict.md` | NEW — 5 acceptance gates 结果 |
| Git commit | `docs(kundur-cvs-v3): Task 3 — Action range Q7 deviation documentation (paper line 938)` |

---

## 12. Self-review (写完整体审)

| 检查项 | 状态 |
|---|---|
| Task 目标清晰 (paper line 938 + Q7 ambiguity → documented deviation) | ✓ |
| 不改任何代码常量, 仅文档 | ✓ |
| Tool policy: 无需 simulink-tools (纯 doc) | ✓ |
| 主文档大纲 9 节齐全 (paper / v3 / deviation / why not / assumption / decision / future / refs / status) | ✓ |
| Fact-base 交叉引用 (§8 + §10) | ✓ |
| 区分 "paper 事实" vs "项目推断" 显式 | ✓ |
| Acceptance gate 5 项 (文件 / paper / v3 / Phase C / 交叉引用) | ✓ |
| Risk 4 项全 LOW (typo / mis-edit / 误改常量 / 概念混淆) | ✓ |
| 估时合理 (~30 min) | ✓ |
| Scope 隔离 (Task 3 不动 Task 1/2 已完成) | ✓ |
| Rollback: 文档 only, git revert 即可 | (隐式) ✓ |

> **FINAL REVIEW** 关键发现:
> 1. **§5 可选代码注释**: code → doc 链接是闭环, 但风险 (R3-3 误改常量)
>    可控, 推荐做。
> 2. **§4 fact-base 交叉引用 append-only**: 防止 R3-2 误改已有事实, 用
>    "update" note 形式而非重写。
> 3. **§3.2 PRIMARY citation 强制**: 每节带行号 + 文件名, 防止 R3-4
>    paper 事实 vs 项目推断混淆。
> 4. **不需要 simulink-tools**: Task 3 是纯 doc, 没有 build / NR / sim
>    runs。这是 Task 3 与 Task 1/2 最大差异 — execution surface 极小,
>    risk 极低, 估时短。
>
> 计划已具备执行级细节。无 hidden risk。
