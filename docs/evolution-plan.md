# MCP / Simulink 系统演进计划

> **用途**: 跨会话演进追踪补充文档。通过 `AGENTS.md` 或 `navigation_manifest.toml` 导航到此处，不是独立入口。
> **维护**: 完成一项打勾+填日期；阻塞时写原因；每次改动更新 Last Updated。
> **上游计划**:
>   - `docs/superpowers/plans/2026-04-12-harness-type-contracts-and-decomposition.md` (Phase 1-3 done + Phase 4-7 directional)
>   - `docs/superpowers/plans/2026-04-12-agent-control-layer-restructure.md` (Task 1-4 全部未开始)

**Last Updated**: 2026-04-14
**Current Phase**: B/C/D 全部任务完成（含 D2）

---

## 当前工具表面（已验证 2026-04-14，D1 后）

`engine/mcp_server.py` PUBLIC_TOOLS: **34 个**（7 harness + 27 simulink）
`engine/mcp_simulink_tools.py` 定义: **56 个** simulink_* 函数（新增 run_script_async + poll_script）→ 29 个未暴露

B1a 审计分类（原 54）：expose=2 / merged=5 / deprecated=3 / scenario=1 / evaluate=20 / exposed=23

---

## 已完成的前置工作

| 日期 | 内容 | Commit |
|------|------|--------|
| 2026-04-12 | Phase 1: 类型化任务信封 (TaskRecord + payload dataclasses) | c570643 |
| 2026-04-12 | Phase 2: 模块分解 (modeling_tasks + smoke_tasks) | 1f80b00 |
| 2026-04-12 | Phase 3: 显式流状态 (TaskPhase + TRANSITIONS + advisory gates) | cf45b2b |
| 2026-04-12 | 清理: 去重 MODELING_TASKS + 删除未用参数 | 6381b46 |

---

## 状态说明

- `done` = 已提交
- `ready` = 无阻塞，可开始
- `blocked` = 有前置依赖
- `directional` = 方向已定，不在当前主线；前置满足后转为 `ready`

---

## Phase B: 工具审计 + 最小叙事修正

> 当前主线: Simulink 建模可靠性。B 阶段目标是摸清现状，不扩张 scope。
> B1a 是默认起点（D1 可独立推进）；B2 仅修正文档过时事实；B3-B6 是 B1 的条件性输出，不自动执行。

| ID | 任务 | 状态 | 依赖 | 预估 |
|----|------|------|------|------|
| B1a | MCP 工具全面审计: 分类全部 54 个 simulink_* 函数，产出分类报告 | `done` 2026-04-14 | 无 | 45 min |
| B1b | 执行 B1a 中"立即暴露"建议: 更新 mcp_server.py + test + pytest 全绿 | `done` 2026-04-14 | B1a | 15 min |
| B2 | AGENTS.md 最小修正: 更正 scope 内事实性陈述（工具数量/描述），不修改 scope 本身 | `done` 2026-04-14 (mcp_server.py 注释已更正；AGENTS.md 无需变更) | B1b | 20 min |
| B3 | 创建 `docs/agent_control_manifest.toml` | `directional` | B1 建议引入 manifest | 30 min |
| B4 | 创建 `tests/test_agent_control_manifest.py` | `directional` | B3 | 30 min |
| B5 | 扩展 `scripts/lint_nav.py` 支持 manifest 校验 | `directional` | B3 | 20 min |
| B6 | 矛盾检查: AGENTS.md / CLAUDE.md / MEMORY.md / manifest 无冲突 | `directional` | B2+B3 | 10 min |

**B1a 审计分类 taxonomy**（统一 6 类，覆盖所有 54 个函数）:

| 分类 | 含义 | 预期数量 | 示例 |
|------|------|----------|------|
| expose | 实现完整、零风险，建议立即暴露 | ~2 | screenshot, capture_figure |
| merged | 功能已合并入已暴露工具，不再单独暴露 | ~5 | connect_blocks → connect_ports |
| deprecated | 已有替代，应标记废弃或删除 | ~2 | get_block_params (用 query_params) |
| scenario | 场景/拓扑特化，不适合通用暴露 | ~2 | build_vsg_stub, clone_subsystem_n_times |
| evaluate | 功能明确但需进一步评估风险/依赖 | ~20 | inspect_model, trace_signal, list_models 等 |
| exposed | 已暴露的 simulink_* 子集（当前 23 个），仅确认归属 | 23 | — |

> B1a 的审计对象是全部 54 个 simulink_* 函数（不含 7 个 harness_* 工具）。每个函数必须且只能落入以上 6 类之一。

**B1b 执行范围**（仅处理 B1a 中 `expose` 类）:
- 更新 `engine/mcp_server.py` 暴露函数
- 更新 `tests/test_mcp_server.py` 工具数量断言
- `pytest tests/test_mcp_server.py -q` 全绿

**B2 约束**:
- 只更正 scope 内的事实性陈述（如工具数量、过时描述），不修改 scope 本身
- 不引入"双控制线"叙事，不扩展训练侧 scope
- 目标: AGENTS.md 描述的现状与 B1a 审计结论一致

**B3-B6 触发条件**: 出现多份控制叙事冲突、现有导航无法稳定表达控制边界、或 lint 无法覆盖一致性校验。不以工具数量为门槛。

**Done when**: B1a 报告完成；B1b pytest 全绿；B2 完成。

---

## Phase C: 废弃处置 + Training gap（审计驱动）

> C2 是 B1 的机械性后续。C1/C3 是 Training 侧扩展，当前 scope 外，标 `directional`。

| ID | 任务 | 状态 | 依赖 | 预估 |
|----|------|------|------|------|
| C2 | 执行废弃函数处置 (删除 / 标记 deprecated) | `done` 2026-04-14 (3 函数已有 DeprecationWarning + deprecated 标记；修正 inspect_model 过时交叉引用) | B1a | 30 min |
| C1 | Training 侧 gap 分析: 是否需要 `train_run_evaluate` / `train_run_compare` | `directional` | B1a+B2 | 20 min |
| C3 | 如果 C1 确认有 gap: 创建 `engine/training_tasks.py` (薄包装) | `directional` | C1 | 1-2 hr |

**C3 约束**: `training_tasks.py` 只可以读 artifact / 调用 evaluate_run.py / 跨 run 对比。不可以导入模型修复代码、修改 Simulink 模型、变成第二个编排框架。

**C1/C3 触发条件**: Training 侧成为主线（AGENTS.md scope 更新）后，将 C1 改为 `ready`。

**Done when**: C2 完成（废弃函数已处置）。C1/C3 完成条件在转为 `ready` 时补充。

---

## Phase D: 长任务可观测性

> `run_script` 异步化。模式已在 smoke_tasks 验证，复用骨架即可。独立于 B/C。

| ID | 任务 | 状态 | 依赖 | 预估 |
|----|------|------|------|------|
| D1 | `run_script` 异步化: start/poll 模式（复用 smoke_tasks 骨架） | `done` 2026-04-14 | 无硬依赖 | 2 hr |
| D2 | MATLAB 端 build 脚本加 stage-level progress 写入 | `done` 2026-04-14 (17 RESULT: markers in build_powerlib_kundur.m, steps 0-DONE) | D1 | 1 hr |

背景: Claude Code 不渲染 MCP progress notifications ([claude-code#4157](https://github.com/anthropics/claude-code/issues/4157))。当前可行方案: start/poll 两工具模式。

**Done when**: `simulink_run_script_async()` + `simulink_poll_script()` 通过测试。

---

## Phase E-H: 方向性规划（不可直接执行）

> 以下四个 phase 方向已定但具体设计待定。详细设计见上游计划文档，此处仅保留摘要。

### Phase E: 训练回调统一化

**问题**: 每个 train_*.py 各自重实现 monitoring/checkpointing/early-stop。
**方向**: 提取最小 callback ABC（参考 SB3 on_step → bool），TrainingMonitor 变为 callback 实现。
**未决**: hook 粒度、callback 排序、声明式 vs 命令式注册。
**详见**: harness plan Phase 4

### Phase F: Agent 层评估测试

**问题**: flow 合约（转移顺序、前置条件、故障传播）只在端到端手动运行时才被验证。
**方向**: 场景化集成测试 + 非法转移测试 + 故障注入测试 + 幂等性测试。
**前置**: B+C 完成后定范围。
**详见**: harness plan Phase 5

### Phase G: 分级故障恢复

**问题**: 所有失败统一处理，但 IPC 超时和模型文件缺失恢复方式完全不同。
**方向**: 三级分类 (transient/process/escalate)，参考 DLRover 模型。
**前置**: 需要运营经验积累确定分级边界。
**详见**: harness plan Phase 6

### Phase H: FastMCP 迁移

**问题**: 手工 tool 注册需要实现和 schema 同步修改，存在签名漂移风险。
**方向**: `@mcp.tool` 装饰器自动 schema + 分类组织 + stdout 隔离。
**前置**: B1a 确定最终工具表面后再迁移。FastMCP 已是现有依赖，不是新引入。
**详见**: harness plan Phase 7

---

## 可选项

| ID | 任务 | 状态 | 备注 |
|----|------|------|------|
| Z1 | Graph policy 文档 (`docs/agent_layer/graph-policy.md`) | `ready` | 10 min |
| Z2 | `vsg_helpers/` 前缀清理 (vsg_ → slx_) | `deferred` | 准备独立发布时再改 |

---

## 依赖图

```
B1a (审计报告) ──────────────────────── 默认起点
  │
  ├──→ B1b (执行 expose 建议) ──→ B2 (最小修正) ──→ B6 (条件)
  ├──→ C2 (废弃处置)
  └──→ [触发条件满足?] → B3 (manifest) → B4 → B5

C1 (directional) → C3 (directional)    ← Training 侧，当前 scope 外

D1 (run_script async) → D2              ← 独立于 B/C，可并行推进

E/F/G/H: directional，前置条件见各节
```

---

## 延后项（附重评条件）

| 项目 | 延后理由 | 重评条件 |
|------|----------|----------|
| Workspace snapshot | bootstrap 已覆盖冷启动恢复 | 出现"崩溃后丢失大量修改"痛点 |
| ScenarioAdapter 接口 | 只有 2 个场景，硬编码可接受 | 第 3 个场景到来 |
| TRANSITIONS 参数化 | 只有 1 种任务流 | 出现不同工作流 |
| 训练状态 bug line | 控制层计划明确 scope out | 训练进入评估/对比阶段 |

---

## 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| B1a 审计发现 ~19 个待评估函数中多数应暴露 | Phase H 工具数量假设失效 | 暴露前先分类到 evaluate，逐批评估后再决定 |
| D1 run_script async 改动影响现有 build 流程 | 回归风险 | 保留同步 run_script 不变，新增 async 版本 |
| Phase E callback 设计与训练脚本耦合 | 改动范围不可控 | 先只做 ABC 定义，不改训练脚本 |

---

## 上游计划冲突分析

两份上游计划无硬冲突，三处重叠已合并：

| 重叠点 | 合并决策 |
|--------|----------|
| FastMCP 迁移 | → Phase H（harness plan 更详细） |
| MCP 工具审计 | → Phase B1（agent-control plan 的显式步骤） |
| Agent 层评估 | 拆两步：B1 = 人工审计，Phase F = 自动化测试 |

---

## 外部对标摘要

| 领域 | 结论 |
|------|------|
| MCP 注册 | 显式 add_tool() 适合多文件；FastMCP mount() 是升级路径 |
| Streaming | Claude Code 不渲染 progress notifications；start/poll 当前可行方案 |
| Checkpoint | metadata-only 重建优于 full snapshot (PyTorch/RLlib 共识) |
| Harness 分层 | 高度对齐 Gymnasium/Terraform provider 模式 |
| 故障恢复 | DLRover 三级模型适用于单机 |

---

## 决策日志

| 日期 | 决策 | 理由 |
|------|------|------|
| 2026-04-13 | D1 不依赖 C | start/poll 模式已在 smoke_tasks 验证，复用骨架即可 |
| 2026-04-13 | Phase E-H 标记 directional | 上游计划明确标注"具体设计待定" |
| 2026-04-13 | harness Phase 7 + 原始 P1 合并为 Phase H | 两处引用同一件事 |
| 2026-04-14 | 删除独立 Phase A，截图暴露并入 B1b | audit-first 原则不设例外；审计结论驱动暴露决策 |
| 2026-04-14 | B2 降级为最小修正，scope 不变 | 当前主线是 Simulink 建模；B2 不应突破 AGENTS.md 边界 |
| 2026-04-14 | C1/C3 标 directional | Training 侧扩展不在当前主线；需主线切换后才触发 |
| 2026-04-14 | B3-B6 标 directional | manifest 仅在导航/authority drift 出现时才执行 |
| 2026-04-14 | B1 拆分为 B1a (审计报告) + B1b (执行建议) | 分离 read-only 结论与 write 操作，消除 Done when 歧义 |
| 2026-04-14 | B3-B6 触发条件改为问题驱动 | 工具数量不是 manifest 的决策依据；导航一致性才是 |

---

## 排序理由

```
Phase B  (~1.5 hr)   B1a 审计报告 → B1b 执行暴露 → B2 最小修正；B3-B6 条件触发
Phase C  (C2: 30min) 废弃处置跟随 B1a；C1/C3 training 侧待主线确认
Phase D  (~3 hr)     独立推进，填补可观测性 gap
Phase E-H (待定)     方向性规划，逐步从 directional 变为 ready
```

核心路径: **B1a → B1b → B2 + C2**。D 独立推进。B3-B6 条件触发。

---

## 使用方法

> **入口说明**: 新对话主入口是 `AGENTS.md`（或 `navigation_manifest.toml`）。此文件是**演进追踪补充文档**，不是独立入口；通过 AGENTS.md 导航到此文件后，再用下方规则定位当前任务。

**恢复进度**: 默认从 B1a 开始；D1 仅在明确并行推进时执行；Z1 属可选项，不阻塞主线。
**完成任务**: 改 `done`，填日期和 commit，检查下游是否解锁。
**directional → ready**: 前置满足 + 具体设计确定后，补充任务表和预估。
**新增任务**: 放入最合适的 Phase，标注依赖。
