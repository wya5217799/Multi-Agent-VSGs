---
name: research-loop
description: ANDES 6-axis recovery 自治研究循环. 用户说 "续 research-loop" 或新会话进来读 handoff 后. AI 读 state.json + 最新 verdict, 写 plan/verdict (caveman), 入队, 睡到下一轮.
---

# Research Loop AI Agent

> Spec: `quality_reports/specs/2026-05-07_research_loop_design.md`
> Plan: `quality_reports/plans/2026-05-07_research_loop_implementation.md`
> Auto-trigger: 用户说 "续 research-loop" / "进 research-loop" / "继续 research-loop"

## 进会话第一动作 (强制)

1. 读 `quality_reports/research_loop/state.json` (Schema 检查走 `python -m scripts.research_loop.check_state <path>`)
2. 读 `quality_reports/research_loop/handoffs/INDEX.md` 顶行 → 读对应 handoff
3. 读最新 `round_NN_verdict.md` (如有)
4. 进 §决策树

## 自由度宪章 (硬约束)

1. 默认走启发式. 例外要写理由 (一行也行)
2. 不预设的现象 → 允许新建 `audits/<topic>.md` ad-hoc 分析
3. 候选不限调参——允许提: 换 metric / 改 obs / 重写 reward / 加 ablation / 跑 sanity probe
4. 跑飞 (OOM/NaN/发散) → 自写 `incidents/<round>.md`, 不等用户
5. 觉得方向不对 → 写 `pivots/<round>.md` 提议, 入 state.pending 等下轮采纳
6. 用户在任何时插话 → 优先级最高, 立刻停手听
7. caveman 默认. "为啥这么干"段落允许说人话
8. 对话框只总结, 详写文档

## 决策树 (per wake)

```
看 state + done.last vs verdict 写没写:
├ done 末尾 verdict 未写 → 写 verdict + 提下轮 (主任务)
├ pending 满 + 无 done 新增 → ScheduleWakeup(estimated_remaining_min)
├ state.killed[] 新增 → 写 incident_<id>.md (RAM/OOM 复盘)
├ done.exit_code ≠ 0 → 写 incident_<id>.md (NaN/发散/cmd 错复盘)
├ stagnation.delta_pct < 5% 连 3 round → 写 pivot_<round>.md
├ ctx > 650k → 找自然断点 → handoff (软触发)
├ ctx > 700k → 强 handoff, 不再做新分析
├ G1-G6 全 PASS → 写 final_verdict, 等用户决终止
└ 无新事件 → 短 wait (5min) 再查
```

## Root-Cause 分析 (强制 fork)

主上下文不做长篇分析. 用 Agent fork:
- subagent_type=`domain-reviewer` 做物理 root-cause
- subagent_type=`tracer` 做证据-假设跟踪

主上下文只接 subagent 摘要 (≤50 字) + 关键数字. 每次 wake 主上下文目标 ≤ 10k token.

## /andes-compare 调用契约

verdict 阶段必调 `/andes-compare` 当:
- 本轮 K ≥ 2 (多候选互比)
- 本轮 best vs 上轮 best (跨轮强制 same-context alignment)
- 本轮 vs 论文 → 走 6-axis JSON, 不再单独调 compare

输出落 `quality_reports/research_loop/round_NN_compare.md`.

## ⚠ Verdict 6-段强制模板 (L1, 2026-05-07)

每 round_NN_verdict.md 必含 6 段, 缺任一段不算完整:

```markdown
# R{NN} Verdict
**Status / Wall / Trigger**

## §1 实测 (ground truth)
- train_reward: 5 seed mean ± std @ final ep
- paper-spec eval: cum_rf, max_df (项目 vs 论文)
- 表格列每 arm 的 final_R / std / TDS% / fpeak / wall

## §2 6-axis paper alignment
- 调 `evaluation/paper_grade_axes.py <eval_dir>` 出 6-axis JSON
- 表格: axis 1-6 score (0-1) + geometric mean + paper benchmark gap
- 若 eval driver 缺 → 标 "NOT MEASURED" 并入 R{N+1} 优先 #1

## §3 视觉对比 (paper vs project fig)
- 路径: paper/figures/<variant>/fig{6,7,8,9}_*.png vs ../一切/论文/Figure.paper/{6,7,8,9}.png
- 1-2 句具体 diff: "项目 Δf peak 0.X Hz vs paper 0.13 Hz, 锯齿/平滑, ΔH 方向正/负"

## §4 Hyperparam vs paper Table I
- 表格列 Class A/B/C deviation:
  - A: 必须靠近 (违规 → bug, 必修)
  - B: 可保留 deviation (写论文声明)
  - C: ANDES 平台局限 (不可消)
- 见 `feedback_research_boundaries.md`

## §5 假设验证 (H1-Hn)
- 上轮 H 验/部分/证伪, 一行 reason

## §6 R{N+1} candidates
- ≤4 候选, priority 排, rationale 一行
- K_max default 8 (CPU 物理上限), GPU=optional
```

L1 enforces: 写 verdict 时如发现 § 缺失, 不准跳过, 必补 (即使 "NOT MEASURED YET" 也要写明
为啥 + 入 R{N+1} 优先).

## ⚠ Verdict 必含 paper-fig 6-axis 闭环 (per 2026-05-07 user 强 input)

判训成功的 gold standard = `paper/figures/<variant>/fig{6,7,8,9}*.png` vs
`C:\Users\27443\Desktop\一切\论文\Figure.paper\{6,7,8,9}.png` 视觉对比 + 6-axis 量化.

每 round verdict 必走 ckpt → eval driver (V2-compat) → traces JSON →
`evaluation/paper_grade_axes.py` (6-axis JSON) → `paper/figure_scripts/figs6_9_ls_traces.py`
(fig regen) → verdict 写 6-axis score + 视觉对比 1 句.

train_reward / action_std / cum_rf 是代理量, 不能替代 6-axis. 见
`feedback_paper_fig_is_gold_standard.md`.

R01-R03 因老 driver `_eval_paper_specific.py` 2026-05-07 stash 事故丢, 写了 "6-axis NOT
MEASURED YET" — R03 已 rebuild 为 `scripts/research_loop/eval_paper_spec_v2.py`, R04 完成
闭环验证. 老入口 `scenarios/kundur/_eval_paper_grade_andes*` / `_phase{3,4,9}*_eval` 等 13 文件
已归档 `scenarios/kundur/_legacy_2026-04/` (L4 lock-in 2026-05-07), 不要 import.

## eval 单一入口 (L4 lock-in 2026-05-07)

ANDES paper-spec eval 唯一脚本: `scripts/research_loop/eval_paper_spec_v2.py`.
任何 round plan / verdict 中 eval 段 cmd 必为该脚本; 不要复活 _legacy_2026-04/ 下任何文件.

老入口归档清单见 `scenarios/kundur/_legacy_2026-04/README.md`.

## ⚠ Explore → Exploit 两阶段方法论 (per user 2026-05-07 + R05 验证)

R01-R04 走偏: 每 round 1 hyperparam × 5 seed × 200-500 ep, 是 paper-style report
不是 explore. 5-seed std 在 explore 阶段 = 噪声不是信号. 4 round 烧 ~120 min wall
还没找到 optimal region.

**R05 验证**: 8 arm × 30ep × 1 seed × parallel ~20 min wall, 立刻 falsify hyperparam
是 root cause 假设 (8 arm 全 6-axis = 0.037 attractor). 信息密度 8× 高于老路径.
见 `round_05_verdict.md` + 修订 plan 注 `round_05_plan.md`.

**正确流程: 每个研究 cycle 分 2 phase**.

### Phase E (explore, 找最优区间) — N seed=1 × K hyperparam × short

| 字段 | 默认 |
|---|---|
| K (arm 数) | 6-8 (单变量 sweep, 每 arm 改 1 个 hyperparam 维度) |
| seed/arm | **1** (不强求 std, paper-style report 留给 P 阶段) |
| episodes | 30-80 (ANDES SAC: 30ep 够 falsify hyperparam, 50-80ep 看 cum_rf 收敛) |
| parallel | 2-3 路 (CPU 争用 paranoid, 不是 8 路 GPU 神话) |
| wall | 20-60 min |
| 评判 | **6-axis trend** (axis 提升 ≥ 0.10 absolute), **不看 cum_rf 绝对值** |

### Phase P (exploit, 验证 winner) — N seed=5 × K' hyperparam × long

| 字段 | 默认 |
|---|---|
| K' (top-N) | 2-3 (E 阶段 axis-trend 排名前几) |
| seed/arm | 5 (出 mean±std) |
| episodes | 200-500 (paper-style 收敛) |
| parallel | 1-2 路 (long train compute heavy) |
| wall | 60-120 min |
| 评判 | 6-axis overall + paper-fig 视觉对比 (gold standard) |

### Phase A (audit, 物理对齐 — R05 attractor 触发) — 0 train, 主上下文人工

E 阶段 K arms 全部 falsified (e.g. 6-axis 完全并列, hyperparam 不是 root) → pivot
到 audit-first, 不再 train:
- eval 公式审计 (单位 / 窗口 / 归一化 vs paper)
- action 物理语义审计 (ESS P 注入 vs GENCLS.M/D 直接调)
- disturbance protocol 审计 (LS magnitude calibration)

A 阶段产出 = `audits/<topic>.md`, 决策 next round 是 train (修 mismatch 后) 还是
更深 audit. 见 R06 plan 模板.

### Round 决策契约

每写 round_NN_plan.md, 第一段必写:
```
**Phase**: Explore | Exploit | Audit | Mixed
**Reason**: <为啥这阶段>
```

不写 phase 等于 plan 不合规.

### 反模式 (don't)

- ❌ "5 seed × 同 hyperparam × 200 ep" 出现在 explore 阶段 (信号 ≠ 噪声)
- ❌ "1 seed × 30 ep" 出现在 exploit 阶段 (RNG drift, 单点不出 paper)
- ❌ R+1 抢 R 的 winner 之前没跑 P 阶段 (没验, 不准 anchor paper)
- ❌ E 阶段 K arms 全 falsified 还继续 train 调参 (R05 教训: pivot audit, 不是再 explore)
- ❌ 8-way GPU parallel 假设 (ANDES TDS CPU-bound, 8 路 fight CPU 实测 30-40 min wall)

### 单 cycle 总 wall

E + P ≈ 90-180 min (1-3 hours), 比单 round "5seed × 200ep × 1 hyperparam" (~45 min)
慢 2-4×, 但**信息密度 8-10×** (E 探 8 维度 vs 老法 1 维度 × 5 重复).

E + A 路径 (R05 attractor 触发): E 20 min + A 主上下文 60-90 min = ~110 min, 不烧训练.

老路径 vs 新路径 4 round 比较:
- 老 (R01-R04): 4 round × ~30 min × 5 seed-rep = 120 min, 4 个 hyperparam point, 0 winner found
- 新 (R05+R06): E phase 20 min + A phase pending → 已 falsify hyperparam 假设, 进物理 root-cause

## ⚠ Verdict 强制双 metric (per OPT-3, 2026-05-07)

verdict "实测" 节必须写 **两个** metric, 不准只引训练:

```
exp1:
  train_reward (R_avg10, 5 seed mean±std): <X>
  paper_grade  (cum_rf @50 fixed test seeds): <Y>
  6axis_overall: <Z>  G=<ABCDEF>
```

理由: 2026-05-06 throughput G6 surprise — 单 seed cum_rf 改 8.6× "改进"
实为 RNG drift, 非真改. paper_grade @50 fixed seeds 才是真信号.

## 文档产出 (caveman, 见 spec §7)

- `round_NN_plan.md`         (template: `templates/plan-caveman.md`)
- `round_NN_verdict.md`      (template: `templates/verdict-caveman.md`)
- `round_NN_compare.md`      (调 `/andes-compare` 自动产)
- `incidents/<id>.md`        (随写)
- `audits/<topic>.md`        (随写)
- `pivots/<round>.md`        (随写)
- `handoffs/<date>_R<NN>.md` (ctx 触发)

## 起步 (第一轮)

不动 `quality_reports/plans/2026-05-07_andes_6axis_recovery.md`.

读现 6-axis 真相 (`docs/paper/andes_replication_status_2026-05-07_6axis.md`) +
recovery plan (作 prior knowledge), AI 自决 2-4 个候选.

## Daemon 启停 (用户做)

```bash
cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"
nohup bash scripts/research_loop_daemon.sh > /tmp/rloop_daemon.log 2>&1 &
echo $! > /tmp/rloop_daemon.pid
```

终止: `kill $(cat /tmp/rloop_daemon.pid)`

## ANDES Throughput 默认 (per spec §11.5 + 2026-05-07 user override)

- WSL `~/.wslconfig`: `memory=24GB processors=32 swap=8GB`
- 单 ANDES run: ~800 MB RSS, 安全位 1.5 GB
- OMP_NUM_THREADS=4 / MKL_NUM_THREADS=4 必须 (BLAS oversub 防御)
- 5 路并行最甜 (1.12× 单进程)
- GPU SAC: **optional, 不 REJECT**. 2026-05-06 verdict 实测 256-256 网络 GPU 训练慢
  ~4% (ROI 弱), 但**不是兼容性问题**, 跑得动. 用户授权: 候选可指定 GPU
  (cmd 加 `DEVICE=cuda CUDA_VISIBLE_DEVICES=0`, backend=`sac_gpu`), 不再要求人工授权
  每次. 见 `feedback_gpu_policy_optional.md`.

## Handoff 流程 (ctx 满)

ctx > 650k 软触发:
1. 选下个自然断点 (写完 verdict 算)
2. write `handoffs/<date>_R<NN>.md` (template: spec §7.6)
3. update `handoffs/INDEX.md` 加一行 (调 `python -m scripts.research_loop.handoff_index`...或直写)
4. update `state.json.ai_session_log[]`
5. say 用户: "续: 开新对话粘 `续 research-loop, 读 <handoff>`"

ctx > 700k 强触发: 跳自然断点等待, 立即写.

## 失败模式 (见 spec §15)

参考 spec, 不复述.
