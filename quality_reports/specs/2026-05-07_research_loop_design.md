# Spec: Research Loop 自动研究工作流

**Date**: 2026-05-07
**Status**: DRAFT
**Owner**: 项目主线
**Type**: 架构 spec
**Brainstorm session**: 2026-05-07 (Q1-Q3 + 自由度调整)

> 风格: caveman 中文, 报告文档化, 对话框只总结. 整体"别太死, 空间大点"
> = 启发式 + AI override 权 + 仅 3 个硬约束.

---

## §1 目标

ANDES 6-axis recovery 自治化. AI 在循环里:

- 起训练 (RAM-fit 并行)
- 监训, 完跑出 verdict + 6-axis
- root-cause 分析
- 提下轮候选, 入队
- 重复直到: 目标 G1-G6 / RAM 危险 / 预算硬上限 / 停滞 / 用户停 / 会话上下文满

---

## §2 范围

**做**:
- ANDES 路径自治循环 (CPU/RAM bound)
- caveman 中文文档化 (plan/verdict/incident/audit/pivot/handoff)
- 跨会话续命 (state.json + handoff doc + INDEX.md)
- backend 抽象 (今日 RAM, 留 GPU/MATLAB stub)
- 复用现有 `quality_reports/{plans,verdicts,audits,handoff,specs}/` 风格

**不做**:
- 不改 `2026-05-07_andes_6axis_recovery.md` 既有 plan
- 不接 Codex MCP / SSH / WandB / Vast.ai (本地)
- 不写 Simulink 路径执行 (PAPER-ANCHOR LOCK 期, 仅 stub)
- 不引入 Docker/k8s/Airflow/Prefect 类调度框架
- 不做训练自动重试 (NaN/发散 默认 fail-stop, AI 看 incident)

---

## §3 架构 3 层

```
┌─ AI Agent (会话, 易逝) ────────────┐
│ 唤 → 读 state                       │
│ 思 (fork subagent 做 root-cause)   │ ⇄ state.json
│ 写 plan/verdict (caveman)          │ ⇄ round_NN_*.md
│ 入队 → ScheduleWakeup 睡           │
│ ctx 满 → handoff → 等用户开新会话  │
└─────────────────────────────────────┘
                  ↕ files only
┌─ State 层 (持久化, 跨会话) ─────────┐
│ quality_reports/research_loop/      │
│   state.json                         │
│   round_NN_plan.md     caveman      │
│   round_NN_verdict.md  caveman      │
│   incidents/  audits/  pivots/      │
│   handoffs/  + INDEX.md             │
└─────────────────────────────────────┘
                  ↕ daemon poll & write
┌─ Daemon (WSL nohup bash, 持久) ─────┐
│ 60s tick                             │
│ pending → free -g → fit K → nohup 起│
│ 监 running 进程 → done flag          │
│ 跑 6-axis → write done.json          │
│ RAM crisis → kill 低 priority       │
│ daemon.log 每 tick 一行              │
└──────────────────────────────────────┘
```

**核心不变量**:
- Daemon 是唯一持久层. 会话 AI 来去都行
- 全部跨层通信走文件. 无 socket/IPC/HTTP
- state.json schema 是契约, 改动需升 version + 双向兼容

---

## §4 state.json Schema (硬契约)

```json
{
  "version": "1.0",
  "round_idx": 0,
  "started_at_utc": "2026-05-07T...",
  "budget": {
    "rounds_used": 0,    "rounds_cap": 20,
    "wall_hr_used": 0.0, "wall_hr_cap": 72,
    "tokens_used": 0,    "tokens_cap": 800000
  },
  "ram": {
    "free_gb_min_hard": 4,
    "per_run_estimate_gb": 2.5
  },
  "gates": { "G1": null, "G2": null, "G3": null, "G4": null, "G5": null, "G6": null },
  "stagnation": { "last_3_overall": [], "delta_pct": null },
  "pending": [
    {
      "id": "r01_phaseA_smoothing_seed42",
      "backend": "andes_cpu",
      "cmd": "/home/wya/andes_venv/bin/python scenarios/kundur/train_andes_v2.py ...",
      "out_dir": "results/andes_v2_smooth_seed42",
      "log": "results/andes_v2_smooth_seed42.train.log",
      "expected_hr": 1.5,
      "ram_gb": 2.5,
      "priority": 5,
      "rationale": "first round Phase A smoothing test (AI override 子句)",
      "queued_by": "R01_plan.md"
    }
  ],
  "running": [
    { "id": "...", "pid": 12345, "started_at_utc": "...", "log_tail_check_ok": true }
  ],
  "done": [
    { "id": "...", "exit_code": 0, "verdict_path": "round_01_verdict.md",
      "overall_score_v2": 0.04, "axes": {...}, "finished_at_utc": "..." }
  ],
  "killed": [
    { "id": "...", "reason": "RAM crisis", "killed_at_utc": "..." }
  ],
  "ai_session_log": [
    { "wake_at_utc": "...", "context_used_tok": 350000,
      "wrote": ["round_01_verdict.md", "round_02_plan.md"],
      "session_id": "<conv_id_or_handoff_ref>" }
  ],
  "handoff_pointers": [
    { "round": 5, "path": "handoffs/2026-05-08_R05.md", "ctx_at_handoff": 695000 }
  ]
}
```

写检查脚本 `scripts/research_loop/check_state.py`. Daemon 每写 state 前调它. AI 每写前也调. fail → halt + log + 给用户.

---

## §5 Daemon (`scripts/research_loop_daemon.sh`)

行为 (60s 一 tick):

1. 加锁 `flock /tmp/research_loop.lock` (避免双开)
2. 读 + 校验 state.json
3. 算 `free_ram_gb = $(free -g | awk '/Mem:/ {print $7}')`
4. `fit_count = max(0, floor((free_ram_gb - free_gb_min_hard) / per_run_estimate_gb))`
5. 起 fit_count 个最高 priority pending → nohup 起 → 移 running
6. 监 running 进程:
   - exit 0 → 跑 `evaluation/paper_grade_axes.py` 出 6-axis JSON → 写 done
   - exit ≠ 0 → 写 done 标 fail (AI 下轮看)
   - log 5 min 无新行 → 标 stuck (不杀, AI 决)
7. RAM 紧:
   - free < 4 GB 持续 2 tick → kill 最低 priority running → 入 killed[]
8. 写 daemon.log 每 tick 一行 (`<utc> ram=X GB run=N pend=N done=N`)
9. 检 stagnation: done.last_3 overall 算 delta_pct, 写回 state
10. sleep 60, loop

启动:
```bash
nohup bash scripts/research_loop_daemon.sh > /tmp/rloop_daemon.log 2>&1 &
echo $! > /tmp/rloop_daemon.pid
```

终止: `kill $(cat /tmp/rloop_daemon.pid)`

---

## §6 AI Agent 行为

**进会话第一动作**:
1. 读 state.json (检 schema)
2. 读最新 handoff (如有, 通过 INDEX.md 找)
3. 读最新 round_NN_verdict.md (如有)
4. 决策树 (§6.1)

**§6.1 决策树**:

```
看 state + done.last vs verdict 写没写:
├ done 末尾 verdict 未写 → 写 verdict + 提下轮 (主任务)
├ pending 满 + 无 done 新增 → ScheduleWakeup(estimated_remaining_min)
├ state.killed[] 新增 项 → 写 incident_<id>.md (RAM/OOM 复盘)
├ done 项 exit_code ≠ 0 → 写 incident_<id>.md (NaN/发散/cmd 错复盘)
├ stagnation.delta_pct < 5% 连 3 round → 写 pivot_<round>.md
├ ctx > 650k → 找自然断点 → handoff (软触发)
├ ctx > 700k → 强 handoff, 不再做新分析
├ G1-G6 全 PASS → 写 final_verdict, 等用户决终止
└ 无新事件 → 短 wait (5min) 再查
```

**§6.2 root-cause 分析强制 fork**:

不在主上下文做长篇分析. 用 fork subagent:
- `domain-reviewer` (现 .claude/agents/) 做物理 root-cause
- `tracer` 做证据-假设跟踪
- 主上下文只接 subagent 摘要 (50 字内) + 关键数字

主上下文用量目标: 每 wake ≤ 10k token.

**§6.3 /andes-compare 调用契约**:

verdict 阶段必调 `/andes-compare` 当:
- 本轮 K ≥ 2 (多候选互比)
- 本轮 best vs 上轮 best (跨轮对比, 强制 same-context alignment)
- 本轮 vs 论文 benchmark 时, 仍走 6-axis JSON, 不再单独调 compare (因 6-axis 已含 paper benchmark)

K = 1 且无前轮时, 跳过 compare (无对比对象).

输出落 `quality_reports/research_loop/round_NN_compare.md`, AI verdict 引用.

**§6.4 候选实验设计自由度**:

不限"调参". AI 可以提:
- 换 metric (e.g., 加 phase coherence axis)
- 改 obs (e.g., 加 last action)
- 改 reward (e.g., smoothing penalty)
- 加 ablation (单变量隔离)
- 跑 sanity probe (短 ep 验证 power flow / NaN / RAM 估算)
- pivot 假设 (写 pivot_<round>.md 单独入队)

每条候选写 rationale (一行) 进 state.pending[].rationale.

---

## §7 caveman 文档规范

**对话框**: caveman 中文, 一段或一行总结. 详写文档.

**§7.1 round_NN_plan.md** (caveman, 200-500 字):

```
# R<NN> Plan
## 上轮
ckpt=<X>  6axis=<Y>  G=ABCDEF
## 假设
H1: 改 a → 期 Δb (理由 1 句)
H2: ...
## 跑啥 (K = 由 budget tier 算, 见 §9)
exp1: <cmd 简版> seed=<N> ep=<N> RAM≈<gb> hr≈<hr>
exp2: ...
## 期 (跟 G1-G6 对齐)
G<x> > <thr>
## 不行咋办
回 R<NN-1> baseline / pivot / 见 §<x>
```

**§7.2 round_NN_verdict.md** (caveman, 300-800 字):

```
# R<NN> Verdict
## 实测
exp1: 6axis=<X>  overall=<Y>  G=<ABCDEF>  log=<path>
exp2: ...
## 对比
vs 上轮: 升/降, 哪 axis
vs 论文: 哪 axis 还差几倍
## 假设验证
H1: 验 / 证伪 / 部分 (一行理由)
## 接下轮
继 H2 / pivot / done
## (可选) 数据表
| axis | LS1 | LS2 | paper | gap |
```

**§7.3 incident_<id>.md** (随写, AI 自由):

OOM / NaN / 训练发散 / daemon crash 实录. 不 enforce 模板. AI 写人话+caveman 混合.

**§7.4 pivot_<round>.md** (随写):

AI 觉得方向不对时, 提新假设. 允许长 (1000+ 字), 因为是说服性论证.

**§7.5 audit_<topic>.md** (随写):

跨 round 现象审计 (例: "5 round ΔH range 全 0"). caveman + 表格.

**§7.6 handoff_<date>_R<NN>.md**:

```
# Handoff R<NN>
session_id: <conv_id>
context_used: <tok>
state.json: quality_reports/research_loop/state.json
近 3 verdict 摘要:
- R<NN-2>: ...
- R<NN-1>: ...
- R<NN>:   ...
daemon: pid=<pid> alive=<y/n>
pending queue: <N> items, 见 state.pending
running: <N>, 见 state.running
新会话指令:
> 续 research-loop, 读 quality_reports/research_loop/handoffs/<self>
```

**§7.7 INDEX.md** (`research_loop/handoffs/INDEX.md`):

每 handoff 加一行. 头永远是最新.

---

## §8 软警报 + 硬熔断

| ID | 类型 | 默认阈值 | 行为 |
|---|---|---|---|
| RAM | **硬** | free < 4 GB 持续 2 tick | daemon 拒新 + 杀低优先级 |
| Round | 软 | rounds_used > rounds_cap | AI 写 budget_extension, 用户决 |
| WallHr | 软 | wall_hr_used > wall_hr_cap | 同上 |
| Token | 软 | tokens_used > tokens_cap | 同上 |
| Stagn | 软 | 3 round delta < 5% | AI 写 pivot 提案, 不强停 |
| Goal | 信号 | G1-G6 全 PASS | AI 写 final_verdict, 用户决终止 |
| Ctx650 | 软 handoff | session > 650k tok | AI 找自然断点切交接 |
| Ctx700 | 强 handoff | session > 700k tok | AI 强切, 不做新分析 |

**软**: AI 决 (写文档让用户拍板)
**硬**: daemon/AI 自动停 (无需用户)
**信号**: 不停, 但触发 final_verdict 流程

---

## §9 并行启发式

```
budget_pct = min(
  (rounds_cap - rounds_used) / rounds_cap,
  (wall_hr_cap - wall_hr_used) / wall_hr_cap,
  (tokens_cap - tokens_used) / tokens_cap
)

K_max default:
  pct > 0.40 → 4
  pct ∈ (0.20, 0.40] → 2
  pct ≤ 0.20 → 1

实并 = min(K_max, floor((free_ram_gb - 4) / per_run_estimate_gb))

AI override 允许 (写 rationale 进 pending[].rationale):
- 候选间复用 init/共享 ckpt → 多并几个
- 关键 ablation 风险高 → 少并 + sanity probe 先跑
- 已有方向陡降 → 少并 + 集中
- 候选时长悬殊 (30 ep smoke vs 500 ep full) → 短的填空隙
```

---

## §10 Handoff 流程

**软触发** (ctx > 650k):
1. AI 选下个自然断点 (写完 1 个 verdict 算完整断点)
2. write `handoffs/<date>_R<NN>.md`
3. update `handoffs/INDEX.md` 加一行
4. update `state.json.ai_session_log[]` 标本会话结束 + state.handoff_pointers[] 加条
5. say 用户 (caveman):
   > 续: 开新对话粘 `续 research-loop, 读 <handoff>`
6. 不再 ScheduleWakeup, 等用户

**强触发** (ctx > 700k):
- 跳过自然断点等待, 立即写 handoff
- 哪怕 verdict 没写完, 写到啥算啥, 用户读残 handoff + state.json 自行恢复

**新会话进**:
1. 读 handoff
2. 读 state.json
3. 读最新 verdict
4. 进 §6.1 决策树
5. ScheduleWakeup 续命

---

## §11 Backend 适配位

```
scripts/research_loop_daemon.sh           主守护 (backend-agnostic)
scripts/backends/andes_cpu.sh             今日: RAM + ANDES TDS launcher
scripts/backends/_resource_check.sh       共用 free / nvidia-smi 抽象
scripts/backends/sac_gpu.sh               未来 stub: VRAM 监控
scripts/backends/matlab_session.sh        未来 stub: MATLAB session 数
scripts/research_loop/check_state.py      schema 检查
scripts/research_loop/k_max_calc.sh       budget tier 算 K_max
```

state.json 每 pending 项有 `backend` 字段, daemon 路由到对应 .sh.

今天只实现:
- `research_loop_daemon.sh`
- `backends/andes_cpu.sh`
- `backends/_resource_check.sh`
- `research_loop/check_state.py`

GPU/MATLAB 留 stub (空文件 + comment).

---

## §12 复用既有 infra

| 既有 | 用途 |
|---|---|
| `quality_reports/{plans,verdicts,audits,handoff}/` | 加 `research_loop/` 子目录, 风格延续 |
| `templates/{plan,verdict}-minimal.md` | 不改; 加 caveman 版进 `templates/{plan,verdict}-caveman.md` |
| `evaluation/paper_grade_axes.py` | daemon 完跑后调它生 6-axis JSON |
| `/andes-compare` skill | AI 多 ckpt 对比时强制走它 (per CLAUDE.md trip-wire) |
| `scenarios/kundur/_run_v2_5seed.sh` | 单 run cmd 风格借鉴 |
| `engine/run_schema.py::RunStatus` | 训练 run dir status 类型, daemon 读 |
| `docs/paper/kd_4agent_paper_facts.md` | AI 写 plan/verdict 引论文事实必读 |
| `docs/paper/andes_replication_status_2026-05-07_6axis.md` | AI 第一轮起步 prior knowledge |
| `quality_reports/plans/2026-05-07_andes_6axis_recovery.md` | 同上, 不改, 仅参考 |

不复用:
- `scripts/launch_training.ps1` (Win-only, daemon 用 WSL nohup 直起)

---

## §13 第一轮起步

**不动** `quality_reports/plans/2026-05-07_andes_6axis_recovery.md`.

第一轮 AI:
1. 读现 6-axis 真相 (`docs/paper/andes_replication_status_2026-05-07_6axis.md`)
2. 读 recovery plan (作 prior knowledge, **不强制 Phase A→D 顺序**)
3. AI 自决 2-4 个候选 (可能含 Phase A, 可能新假设, AI 自由)
4. 写 R01_plan.md (caveman)
5. enqueue state.json
6. 用户启 daemon → ScheduleWakeup 续命

---

## §14 自由度宪章 (写进 SKILL.md 顶部)

```
1. 默认走启发式. 例外要写理由 (一行也行)
2. 不预设的现象 → 允许新建 audit_<topic>.md ad-hoc 分析
3. 候选不限调参——允许提: 换 metric / 改 obs / 重写 reward / 加 ablation / 跑 sanity probe
4. 跑飞 (OOM/NaN/发散) → AI 自写 incident_<round>.md, 不等用户
5. 觉得方向不对 → 允许写 pivot_<round>.md, 入 state.json pending 等下轮采纳
6. 用户在任何时插话 → AI 优先级最高, 立刻停手听
7. caveman 默认. "为啥这么干"段落允许说人话
8. 对话框只总结, 详写文档
```

---

## §15 失败模式 + 自处理边界

| 失败 | 谁处理 | 怎么处理 |
|---|---|---|
| OOM 1 进程 | daemon | kill, 入 killed[], AI 下轮看 incident |
| OOM daemon 自己 | 用户 | daemon.log 留尸, 用户 restart |
| ANDES NaN / power flow 不收敛 | daemon | exit ≠ 0, AI 写 incident, **默认不重试** |
| 训练发散 (critic loss 爆) | AI | 看 6-axis = 0 + log → 写 incident + pivot |
| 5 round 无升 | AI | 写 pivot 提案, 不强停 |
| state.json schema 漂 | check_state.py | fail → daemon halt + log + 用户介入 |
| daemon 卡死 (60s+ 无 tick) | 用户 | watchdog 不做 (YAGNI), 用户 ps 查 |
| handoff 写一半 ctx 满 | AI | 写到啥算啥, 用户读残 handoff + state.json 续 |
| AI 提的 cmd 路径错 | daemon | 训练 exit ≠ 0, AI 下轮看 log 自查 |
| AI 重复提相同候选 | check_state.py | 过 dedup 检 (id 唯一), reject + 提示 AI |
| daemon 写 state 中途崩 | 用户 | state.json 不能用, 从 git 上一 commit 恢复 |

---

## §16 测试策略

**M1 unit**:
- `check_state.py` 对一组 fixture state.json (合法/非法/老 version) 的判定
- `_resource_check.sh` 在不同 free 值下输出正确 fit_count
- caveman 模板渲染 (Python jinja-like 简实现)

**M2 integration**:
- daemon dry-run mode (不真起训练, mock 进程返回): 跑 5 tick 验证 state.json 正确流转
- AI agent skill dry-run (mock state.json 触发不同事件分支)

**M3 smoke (人在回路)**:
- 1 round × 1 candidate × 30 ep → 看 daemon 起训练 / 完跑 / 调 6-axis / 写 done.json / AI 醒着写 verdict 全链路
- 验证 `/andes-compare` 在 verdict 阶段被调

**M4 stress**:
- 模 ctx > 650k 触发 handoff
- 模 RAM 危机触发 daemon kill + AI incident
- 模 stagnation 触发 pivot

---

## §17 实现顺序 (后续 writing-plans skill 接手)

宏观依赖:

```
1. state.json schema + check_state.py        基础契约
2. caveman templates                          文档样板
3. backends/_resource_check.sh                共用 RAM 算
4. backends/andes_cpu.sh                      今日 launcher
5. research_loop_daemon.sh                    主守护
6. .claude/skills/research-loop/SKILL.md      AI 入口
7. handoffs/INDEX.md 工具                     交接索引
8. M1-M2 测试                                  自动化验证
9. M3 smoke (1 candidate × 30 ep)             人在回路验证
10. 全开 (≤ 4 candidate, daemon nohup 起)     正式启用
```

详细 atomic step 由 writing-plans skill 接手生成.

---

## §18 References

- `quality_reports/plans/2026-05-07_andes_6axis_recovery.md` (现 plan, 不改)
- `quality_reports/audits/2026-05-07_andes_6axis_failure_analysis.md` (失败分析)
- `evaluation/paper_grade_axes.py` (6-axis 量化, daemon 调)
- `docs/paper/andes_replication_status_2026-05-07_6axis.md` (现状)
- `docs/paper/kd_4agent_paper_facts.md` (论文事实)
- `quality_reports/aris-integration.md` (为何不接 ARIS 大部分 skill)
- `templates/plan-minimal.md` / `templates/verdict-minimal.md` (旧风格不改)
- `scenarios/kundur/_run_v2_5seed.sh` (单 run 风格借鉴)
- `quality_reports/handoff/2026-05-07_andes_6axis_recovery_handoff.md` (handoff 风格借鉴)

---

# §Done Summary (append-only, post-execution)

(待 writing-plans 出 plan + 实现完后填)
