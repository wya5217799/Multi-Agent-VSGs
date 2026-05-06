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

R01-R03 因 `_eval_paper_specific.py` (eval driver) 2026-05-07 stash 事故丢, 写了 "6-axis NOT
MEASURED YET" — R04 第一任务必 rebuild driver + 跑 R03 ckpt 闭环.

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
