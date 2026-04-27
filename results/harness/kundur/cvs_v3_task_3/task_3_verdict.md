# Task 3 — Action Range Q7 Ambiguity Documentation — Verdict

**Date:** 2026-04-28
**Status:** **PASS** — 5/5 acceptance gates 通过 + 0 模型修改
**Paper PRIMARY:** line 938-939 — "ΔH ∈ [−100, +300], ΔD ∈ [−200, +600]"
**Plan ref:** `quality_reports/plans/2026-04-28-task-3-action-range-doc-execution-plan.md`

---

## TL;DR

| 项 | 结果 |
|---|---|
| 主 deviation 文档创建 | ✅ `docs/paper/action-range-mapping-deviation.md` (9 节) |
| fact-base §8 Q7 交叉引用 | ✅ |
| fact-base §10 deviation 表交叉引用 | ✅ |
| `config_simulink_base.py` 代码注释 | ✅ DM/DD 常量上加文档链接 |
| **DM/DD/M_FLOOR/D_FLOOR 数值常量** | **✅ 未改 (R3-3 verified)** |
| build / NR / IC / runtime / .slx | ✅ 未触动 |
| env / SAC / reward / paper_eval | ✅ 未触动 |

---

## Acceptance gates 5/5

| # | Gate | 通过证据 |
|---|---|---|
| 1 | 主文档 9 节齐全 | grep `^## ` count = 9 ✓ |
| 2 | Paper PRIMARY (line 938-939, 250) 引证 | grep "line 938\|line 250" hits = 6 ✓ |
| 3 | v3 PRIMARY (config 文件 + 常量名) 引证 | grep `config_simulink_base\|DM_MIN\|DD_MIN` hits = 8 ✓ |
| 4 | Phase C verdict 路径引用 | grep `cvs_v3_phase_c\|Phase C` hits = 10 ✓ |
| 5 | fact-base 交叉引用 (§8 Q7 + §10 deviation) | grep `action-range-mapping-deviation` 在 fact-base 出现 2 次 ✓ |

R3-3 验证: `python -c "from scenarios.config_simulink_base import DM_MIN, DM_MAX, DD_MIN, DD_MAX"` →
`DM_MIN=-6.0 DM_MAX=18.0 DD_MIN=-1.5 DD_MAX=4.5` (与 pre-Task 3 完全一致, 仅加 docstring 注释)。

---

## 修改文件清单

| 文件 | 类型 | 内容 |
|---|---|---|
| `docs/paper/action-range-mapping-deviation.md` | NEW | 主 deviation 文档, 9 节 (Paper PRIMARY / v3 State / Deviation / Why Not Adopt / Working Assumption / Decision / Resolution Path / References / Status) |
| `docs/paper/yang2023-fact-base.md` | EDIT (append-only) | §8 Q7 加 2026-04-28 update note + doc link; §10 deviation 表加 doc link |
| `scenarios/config_simulink_base.py` | EDIT (注释 only) | DM/DD 常量上 7 行 docstring 指向 deviation 文档 |
| `results/harness/kundur/cvs_v3_task_3/task_3_verdict.md` | NEW | 本文件 |

**未修改的 (Task 3 隔离恪守):**
- DM/DD/M_FLOOR/D_FLOOR/ESS_M0/ESS_D0 数值常量
- build_kundur_cvs_v3.m / kundur_cvs_v3.slx / kundur_cvs_v3_runtime.mat /
  kundur_ic_cvs_v3.json / compute_kundur_cvs_v3_powerflow.m
- env/simulink/kundur_simulink_env.py / scenarios/kundur/config_simulink.py
- reward / SAC / replay buffer / checkpoint / paper_eval
- Task 1 + Task 2 已完成 modeling layer 状态

---

## 主文档 9 节结构

1. **Paper PRIMARY** — line 938-939 (action range) + line 250 (Eq.1 H 单位歧义)
2. **v3 Implementation State** — config_simulink_base.py:37-38 + ESS_M0=24, ESS_D0=4.5 + M_FLOOR/D_FLOOR
3. **The Deviation** — 33×/133× 数值差 + Q7 单位歧义 + H_es,0 baseline 缺失
4. **Why Not Adopt Paper-Literal Range** — Phase C L0-L3 floor clip 实证 (87% clip @ paper-equivalent L3); ΔM=-100 → M=-76 → clip; reverse calibration 偏离 [49]
5. **Working Assumption** — H_paper = 2·H_code 项目推断 (非 paper 事实) + 即使采纳此 mapping 仍 33× 窄
6. **Decision** — E-doc / E-paper-literal / E-paper-equivalent 三路径 → 选 E-doc
7. **Resolution Path** — Q7 解决条件 (paper 作者邮件 / cross-ref / 习惯调研) + 重审决策树
8. **References** — paper / Phase C / fact-base / NOTES / code 锚点
9. **Status** — documented deviation 当前态 + 状态变更条件 + 维护责任

---

## 关键 disclaimer 强调

文档显式区分:

| 类别 | 处理 |
|---|---|
| **Paper 事实** | 必带行号 (e.g., "line 938-939") |
| **项目推断** | 必带 disclaimer ("项目推断, 非 paper 事实") |
| **Phase C 实证** | 必带 verdict 路径引用 |

§5.4 Disclaimer (CRITICAL):
> "The H_paper = 2·H_code mapping is a project inference, not a paper-stated
> fact. Paper Eq.1 does not specify H unit; the 2× factor is derived from
> project code conventions, not paper text. Cite as project assumption,
> NEVER as paper fact."

---

## Risk register 状态

| ID | Risk | Status |
|---|---|---|
| R3-1 | Paper 行号 typo | NOT TRIGGERED — line 938-939 / 250 经 Read 复核 |
| R3-2 | fact-base 误改已有事实 | NOT TRIGGERED — 用 append "2026-04-28 update" 形式; 未删原文 |
| R3-3 | 意外改 DM/DD 数值常量 | NOT TRIGGERED — Python import 验证 -6.0/18.0/-1.5/4.5 与 pre-Task 完全一致 |
| R3-4 | "Paper 事实" vs "项目推断" 混淆 | NOT TRIGGERED — §5.4 + §1.2 显式 disclaimer; H_paper=2·H_code 永远标注 "项目推断, 非 paper 事实" |

---

## Hand-off

**Modeling layer Task 1 + Task 2 + Task 3 全部完成**:

- Task 1: W2 接入 bus 8 (paper line 894) ✓
- Task 2: Bus 14 IC pre-engage 248 MW + LS1 反向 (paper line 993) ✓
- Task 3: Action range Q7 deviation 文档化 (paper line 938) ✓

**v3 当前 paper-alignment 状态**:
- Modeling layer (拓扑 / IC / NR / runtime / .slx): **paper-aligned** post-Task 1+2
- Action range: **documented deviation** post-Task 3 (在 Q7 解决前不机械采纳)
- Paper 不要求的复杂度 (AVR / PSS / PLL / inner loops / turbine dynamics): **永久不加**

**论文有的 v3 全有, 论文不要的 v3 不加, 论文歧义的 v3 显式声明** — 三句话 Cover paper alignment 终态。

**下一步可选:**
- Phase A-D 重测 (post-Task 1+2 baseline establish, ESS Pm0 sign flip 后)
- RL training 启动 (modeling layer 已锁定, training surface 已 paper-aligned)
- Q7 解决工作 (paper 作者邮件 / cross-ref / 同领域文献调研)
- Git commit Task 1+2+3 完成态

---

## STOP

Task 3 完成。等用户下一步指令。
