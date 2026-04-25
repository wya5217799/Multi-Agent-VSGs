# Training Management — 组件分层与术语

> 单源真相文档：训练相关的"谁调谁、谁写谁读、谁是入口"。
> 与本仓 `CLAUDE.md` "AI Collaboration Track" 段落保持一致；冲突以本文为准。

## 1. 四角色术语（固化命名）

| 角色 | 工件 | 进程内/外 | 用户/Agent | 时机 |
|------|------|-----------|-----------|------|
| **Launcher** | `engine/training_launch.py` + `scripts/launch_training.ps1` | 进程外 | 二者并存 | 训练启动前 |
| **Monitor** | `utils/monitor.py::TrainingMonitor` + `utils/run_protocol.py` | **进程内**（训练循环里） | — | 训练运行中 |
| **Observer** | `engine/training_tasks.py::training_status` / `training_diagnose`（MCP） | 进程外 | Agent | 训练运行中（轮询） |
| **Evaluator** | `engine/training_tasks.py::training_evaluate_run` / `training_compare_runs`（MCP） | 进程外 | Agent | 训练完成后 |

四者**职责不重叠**，但都消费同一份 `training_status.json` 契约（见 §3）。

## 2. 入口分流

```
            ┌──────────────┐
            │  人 / 用户   │ ──► scripts/launch_training.ps1 ──┐
            └──────────────┘                                  │
                                                              ▼
            ┌──────────────┐                          scenarios/<topo>/
            │ LLM agent    │ ──► engine/training_     train_simulink.py
            │              │      launch.py::         (训练进程)
            │              │      get_training_       │
            │              │      launch_status()     │
            └──────────────┘            │             │ 进程内
                  ▲                     │             ▼
                  │                     │     utils/monitor.py
                  │                     │     TrainingMonitor
                  │                     │             │
                  │                     │             ▼
                  │                     │     utils/run_protocol.py
                  │                     │     write_training_status()
                  │                     │             │
                  │                     │             ▼
                  │                     │     results/sim_<topo>/runs/
                  │                     │       <run_id>/
                  │                     │         training_status.json   ◄─┐
                  │                     │         logs/metrics.jsonl       │
                  │                     │         logs/events.jsonl        │ 文件契约
                  │                     │         logs/latest_state.json   │
                  │                     │         checkpoints/             │
                  │                     │                                  │
                  │                     │ 进程外读取                        │
                  │                     ▼                                  │
                  │      engine/run_schema.py::read_run_status()  ────────┘
                  │                     │
                  │                     ▼
                  │      ┌─────────────────────────────┐
                  │      │ Launcher: 启动决策          │
                  │      │   training_launch.py        │
                  └──────┤ Observer: 实时监控          │
                         │   training_status / diagnose│
                         │ Evaluator: post-run 评估    │
                         │   training_evaluate_run     │
                         │   training_compare_runs     │
                         └─────────────────────────────┘
```

**用户**永远走 `launch_training.ps1`（交互式终端）。
**Agent**永远走 `engine/training_launch.py::get_training_launch_status()`（结构化事实）。
两条路径最终拉起同一个 `train_simulink.py`，无运行时差异。

## 3. 文件契约（`training_status.json`）

写入方：`utils/run_protocol.py::write_training_status`（仅训练进程内调用）。
读取方：所有进程外组件**只**通过 `engine/run_schema.py::read_run_status` 读取。

| 字段 | 类型 | 说明 |
|------|------|------|
| `run_id` | str | 形如 `kundur_20260410_143022` |
| `status` | "running" \| "finished" \| "failed" | 终态 |
| `episodes_done` | int | 已完成 episode |
| `episodes_total` | int | 计划 episode |
| `last_reward` | float \| None | 最近 episode reward |
| `last_eval_reward` | float \| None | 最近评估 reward |
| `last_updated` | ISO8601 str \| None | running 心跳时间 |
| `started_at` | ISO8601 str \| None | 启动时间 |
| `finished_at` | ISO8601 str \| None | 正常终止 |
| `failed_at` | ISO8601 str \| None | 异常终止 |
| `error` | str \| None | 错误摘要 |
| `stop_reason` | str \| None | 提前停止原因 |
| `logs_dir` | str \| None | 日志目录绝对路径 |

**变更约束**：新增字段 → 在 `RunStatus` 加可选字段、在本表加行；改名/删字段 → 跨 Launcher / Observer / Evaluator 同步，并更新本表。

## 4. 共享 schema 模块

`engine/run_schema.py`：
- `RunStatus` — `@dataclass(frozen=True)` 类型化视图
- `read_run_status(run_dir) -> RunStatus | None` — 单一类型化读取入口
- `list_episode_checkpoints(run_dir) -> list[Path]` — 统一 checkpoints 扫描

下游消费者：
- `engine/training_launch.py`（Launcher）
- `engine/training_tasks.py`（Observer + Evaluator）

下游**不**直接 `.get("status")` 字典，统一通过 dataclass 访问。

## 5. "不该混淆"清单

- ❌ `launch_training.ps1` 与 `engine/training_launch.py` **不**择一。前者是用户交互入口，后者是 agent 事实查询入口；都保留。
- ❌ Monitor（进程内写）与 Observer（进程外读）**不**合并。文件系统是天然解耦边界。
- ❌ MCP `training_status` 与 `training_evaluate_run` **不**合并。前者监控运行中，后者评估已完成。
- ❌ `engine/run_schema.py` 与 `utils/run_protocol.py` 职责不同：后者是文件 I/O 与 run 目录约定，前者是类型化 schema 视图。

## 6. 相关引用

- `CLAUDE.md` — "AI Collaboration Track" 段落（路径字典）
- `docs/decisions/2026-04-09-harness-boundary-convention.md` — `results/harness/` vs `results/sim_<topo>/runs/` 边界
- `docs/decisions/2026-04-17-control-surface-convention.md` — Model Harness / Smoke Bridge / Training Control Surface 三层定义
