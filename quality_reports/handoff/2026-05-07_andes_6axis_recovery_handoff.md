# Session Handoff — 2026-05-07 ANDES 6-Axis 真实评估 + Recovery 计划

> **新对话第一步**: 读完本文 → 读 §"必读 5 文件序列" → 接上当前任务.

---

## 0. 一句话状态

**ANDES 论文复现实际 0% paper-aligned (6-axis overall 0.036/1.0)**, 旧 cum_rf "paper-grade"
verdict 被新 6-axis 评估推翻. 已写 4 phase recovery plan (Phase A-E).

**⚠ 2026-05-07 跨分支 stash 事故**: 多文档丢失后已恢复. 新对话进来若发现关键文件缺失, 见
§9 "已知 Bug / Gotcha".

---

## 1. 必读 5 文件序列 (新对话进入)

| 顺序 | 文件 | 内容 |
|---|---|---|
| 1 | `docs/paper/andes_replication_status_2026-05-07_6axis.md` | **真实状态总表** + Top 3 ckpt 6-axis 明细 + 完整 ranking + 失败根因 |
| 2 | `quality_reports/audits/2026-05-07_andes_6axis_failure_analysis.md` | **失败分析 7 节**: 6 个 axis 失败原因 + root cause 树 |
| 3 | `quality_reports/plans/2026-05-07_andes_6axis_recovery.md` | **4 Phase recovery plan** + G1-G6 gates |
| 4 | `evaluation/paper_grade_axes.py` | **6-axis 量化函数** + 论文 benchmark + 批量 ranking |
| 5 | `scenarios/kundur/NOTES_ANDES.md` §1 | 修代码必读, V1/V2 env / results/ 目录定位 |

辅助:
- `paper/figures/MODELS_INDEX.md` — 4 个 variant fig dir (按 6-axis 排序)
- `quality_reports/verdicts/2026-05-06_andes_paper_figs_v1_v2_verdict.md` — SUPERSEDED (历史)
- `results/andes_paper_alignment_6axis_2026-05-07.json` — 21 ckpt × 7 axis × 2 scen 完整数据
- `CLAUDE.md` 顶部 banner — ANDES first-class + 6-axis 速查

---

## 2. 6-axis 评估方法 (核心修正)

### 论文 benchmark (Fig.6/7/8/9 视觉提取)

| Axis | LS1 论文 | LS2 论文 | Tolerance |
|---|---|---|---|
| max \|Δf\| | 0.13 Hz | 0.10 Hz | ±0.10 Hz |
| final \|Δf\|@6s | 0.08 Hz | 0.05 Hz | ±0.06 Hz |
| settling_s | 3 s | 2.5 s | ±4 s |
| ΔH range (DDIC) | [-100, +250] | [-100, +200] | ±50% ratio |
| ΔD range (DDIC) | [-200, +500] | [-200, +300] | ±50% ratio |
| smoothness | std~0 | 同 | std ≤ 10/30 |

### 评分公式
- 单 axis score = clip(1 - \|project - paper\|/tolerance, 0, 1)
- overall = 6 axis 几何均值 (任一 0 → 总分 0, 强制 holistic)

### 项目最佳 vs 论文

| Rank | Ckpt | overall | 强项 | 弱项 |
|---|---|---|---|---|
| 1 | balanced_seed46_best | **0.036** | smoothness 0.83 | max/final/settling/range 全 0 |
| 18 | **phase3v2_seed44** (旧 verdict 锁定) | 0.033 | (无) | ΔD smoothness std=22 锯齿 |
| 20 | adaptive_K10_K400 | 0.010 | smoothness | range 全 0 |
| 21 | no_control | 0.010 | smoothness 1.0 | range 0 |

---

## 3. 失败 root cause 树

```
6-axis 全 fail (overall 0.036)
├── F1. ΔH/ΔD range 70×/47× 偏小 (root: H₀=10 选择, paper-literal 物理不可行)
├── F2/F3/F4. max_df / final_df / settling 全失败 (root: GENROU D=0 + GENCLS-only 缺 governor)
├── F5. ΔH/ΔD smoothness (root: SAC stochastic actor + 无 smoothing penalty)
└── F6. cum_rf 假阳性 (root: sync 积分量, 对 step-jitter 不敏感)

二级:
├── M1. 评判 metric 单维 cherry-pick → 修: 6-axis 几何均值
├── M2. 论文 benchmark 之前用估值 → 修: 视觉提取真实数值
└── M3. 训练完没看时序图, 只看积分量 → 修: 必须 fig7/9 review
```

---

## 4. 4 Phase Recovery Plan (DRAFT)

| Phase | 内容 | 期望 axis 改善 | 论文 scope | 成本 |
|---|---|---|---|---|
| **A** | actor smoothing reward + INCLUDE_OWN_ACTION_OBS | smoothness 0.7→1.0 | ✅ 标准 RL | 0 风险, 1 day |
| **B** | 启 ANDES IEEEG1 governor + EXST1 AVR | max/final/settling 同时 0→0.4 | ⚠️ 需 deviation 文档 | 1-2 day |
| **C** | H₀=50 baseline + ΔH=[-50,150] | range 0→0.5 | ⚠️ 偏离 Kundur [49] | 1 day |
| **D** | V3 env 子类 + 5 seed × 500 ep 重训 + 6-axis 重评 | overall ≥ 0.5 | — | 6-8 hr WSL |
| **E** | verdict + 文档更新 + V3 fig 重画 | — | — | 0.5 day |

### G1-G6 Acceptance Gates (PRE-REGISTERED)
- G1: overall ≥ 0.5
- G2: max\|Δf\| ≤ 0.20 Hz
- G3: settling_s ≤ 6 s
- G4: ΔH range ≥ 100
- G5: smoothness std ≤ 1.0
- G6: DDIC > Adaptive > NoCtrl ranking 保持

详见 `quality_reports/plans/2026-05-07_andes_6axis_recovery.md`.

---

## 5. 关键认知修正 (写论文必须 reflect)

| 旧认知 | 新认知 |
|---|---|
| "ANDES 复现已多处达 paper-level (cum_rf 5-10%)" | 仅 cum_rf 单维匹配, 物理动态 5/6 axis 全 fail |
| "phase3v2_seed44 paper-level DDIC" | 6-axis ranking #18, ΔD smoothness std=22 锯齿 |
| "V2 env LS1 no-ctrl 103%" | 仅 sync 积分量级匹配, max_df 5×偏大, settling ∞ |
| "max_df 5× 是不可消架构 floor, 接受现状" | F1+F2 联合 (governor + H₀重选) **可改善**, 但需 deviation |
| "复现成功" | 机制对齐, 物理量级 documented deviation, 写论文要诚实 |

---

## 6. 下一步选项 (用户决策)

| 选项 | 说明 | 时长 | 风险 |
|---|---|---|---|
| **a. 启动 Phase A** | reward smoothing + INCLUDE_OWN_ACTION_OBS, 1 seed × 30ep smoke | 1 hr | 低 |
| **b. 启动 Phase A-B** | A + B (governor) 合并测试 1 seed | 2-3 hr | 中 |
| **c. 全 Phase A-D** | A+B+C+D 一次性 5 seed × 500 ep 重训 | 6-8 hr | 高 |
| **d. 暂停项目** | 接受当前 6-axis = 0.036, 写论文 contribution = 机制对齐 + documented deviation | 0 | 0 |
| **e. 写 paper revision** | 改"复现"声明为"机制对齐 + 量化偏差登记" | 1-2 day | 0 |

---

## 7. 后台任务状态

**无活跃训练**. V2 5-seed train 已完成:
- `andes_v2_balanced_seed{42-46}` 全部 500ep 完成
- 实测在 V2 env 下 zero-shot 表现见 `results/andes_eval_paper_specific_v2_envV2_hetero/`

**老 V1 训练** 全部完整保留, 不删.

---

## 8. WSL 环境

- ANDES Python: `/home/wya/andes_venv/bin/python`
- Repo path (双空格): `/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs`
- 评估 dir: `/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs/results/andes_eval_paper_specific_v2_envV2_hetero/`

---

## 9. 已知 Bug / Gotcha (新对话需避免)

- `bash -c "for x in ..."` 多层 escape 把 `$x` 吞掉 → 写 .sh 脚本扔 WSL
- `paper_grade_parallel/` 是 2-ep smoke 不可用做 50-ep cum reward 图
- `_eval_paper_specific.py` 默认用 final.pt eval, 老 model 应改用 best.pt
- ANDES TDS 某些 baseline 配置 (V2 D=30 uniform, NEW_LINE_X=0.60) 会 power flow 不收敛
- 训练 5-seed 顺序跑 (避免 ANDES 单进程 SLX 冲突), 6-8 hr 串行
- WSL repo path 双空格 → 命令必须用单引号包裹 `'/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs'`
- **2026-05-07 stash 事故**: 切分支不 commit → 多文档被擦. **修代码完后立刻 git add + commit
  scoped 文件**, 防丢
- 关键非 git tracked 文件: `evaluation/paper_grade_axes.py`, `env/andes/andes_vsg_env_v2.py`,
  `scenarios/kundur/NOTES_ANDES.md`, `docs/paper/andes_replication_status_2026-05-07_6axis.md`,
  `paper/figures/MODELS_INDEX.md`. 这些每次改完都要 commit.

---

## 10. 一行接续

新对话进来说:
- "继续 Phase A" → 启动 reward smoothing + smoke test
- "整体启动 A-D" → 完整 recovery plan 6-8 hr
- "回到论文写作" → 不再追 6-axis, 改 contribution 声明
- "重看 6-axis 数据" → 读 `docs/paper/andes_replication_status_2026-05-07_6axis.md`

---

*Session: 2026-05-07*
*Trigger: cum_rf 评判被推翻 → 6-axis 评估流程重写 → recovery plan*
*Recovery: 跨分支 stash 事故后多文件重建, 6-axis JSON 数据完整保留*
