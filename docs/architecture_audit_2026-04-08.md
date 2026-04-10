# 现状架构审计 — Multi-Agent VSGs
**审计日期：2026-04-08**
**审计范围：仓库当前实际代码，不含未来计划**

---

## 1. 项目当前的整体目标是什么

**实际在做的事：**
复现 Yang et al. TPWRS 2023 论文中的多智能体深度强化学习方案，使用 Soft Actor-Critic (SAC) 控制电力系统中虚拟同步发电机 (VSG) 的虚拟惯量 H 和阻尼系数 D，目标是在扰动（负荷投切）后抑制频率偏差。

系统当前支持两个拓扑（Kundur 4 机 / NE39 39 节点）× 三个仿真后端（ANDES / ODE / Simulink），但**主要开发精力当前集中在 Simulink 后端**。已完成的内容：Simulink 模型联调、FastRestart 闭环控制、一套用于 Claude 远程操控的 MCP harness 工具链。训练本身（长 episodes 多轮收敛）尚未在 Simulink 后端完整跑出结果。

---

## 2. 当前系统的一级模块有哪些

| 模块/目录 | 职责 | 状态 |
|---|---|---|
| `agents/` | SAC 神经网络、多智能体管理器、经验回放 | **核心路径，但实际训练中未被 Simulink 脚本调用**（见§7） |
| `engine/` | MATLAB Engine 管理、Simulink Bridge、MCP Server、Harness 任务链 | **核心路径，已生效** |
| `env/simulink/` | Gymnasium 包装的 Simulink/ODE 环境 + 内嵌 SAC 实现 | **核心路径，已生效** |
| `env/andes/` | ANDES 仿真器环境（base + Kundur + NE39 + REGCA1） | 已完成，当前非主力后端 |
| `env/ode/` | 纯 Python swing equation 环境 | 辅助/快速原型 |
| `env/*.py`（根目录层） | 旧版环境文件（power_system, multi_vsg_env, andes_vsg_env 等） | **疑似历史残留，未被主要训练脚本导入** |
| `vsg_helpers/` | 24 个 MATLAB .m 函数（step/inspect/patch/query/run_quiet 等） | **核心路径，harness 所有 MATLAB IPC 都过这里** |
| `scenarios/kundur/` | Kundur 场景训练/评估脚本 + Simulink 模型 + config | 核心路径 |
| `scenarios/new_england/` | NE39 场景训练/评估脚本 + Simulink 模型 + config | 核心路径 |
| `utils/monitor.py` | TrainingMonitor（奖励/动作/损失异常检测） | **已实现，但 Simulink 训练脚本实际未调用**（见§7） |
| `plotting/` | 论文图表生成脚本 | 辅助工具，针对已完成的 ANDES 训练结果 |
| `results/harness/` | Harness 运行记录（JSON artifacts + summary） | **实际在写入，harness 运行后的历史记录** |
| `results/sim_kundur/`, `results/sim_ne39/` | Simulink 训练 checkpoint 和日志 | 训练结果存放点（当前只有 smoke test 结果） |
| `tests/` | Harness 模块单测（reference/registry/repair/reports/tasks） | 针对 harness 层的单测，已有 5 个文件 |
| `docs/` | ADR、harness 规范、devlog | 文档，部分已过时 |
| `C:\Users\27443\.claude\projects\...\memory\` | Claude 跨会话记忆文件 | 项目管理层，不属于代码路径 |

---

## 3. 真实的数据流 / 控制流

### 3a. Simulink 训练路径（当前主路径）

```
CLI 命令
  └─> scenarios/kundur/train_simulink.py  (入口)
        │  读取 scenarios/kundur/config_simulink.py（超参数）
        │  构造 KundurSimulinkEnv 或 KundurStandaloneEnv
        │  构造 SACAgent（来自 env/simulink/sac_agent_standalone.py，非 agents/）
        │
        └─> 训练循环
              │  env.reset() / env.step(actions)
              │    └─> KundurSimulinkEnv.step()
              │          └─> SimulinkBridge.step()   [engine/simulink_bridge.py]
              │                └─> MatlabSession.call("vsg_step_and_read", ...)  [engine/matlab_session.py]
              │                      └─> MATLAB Engine IPC
              │                            └─> vsg_helpers/vsg_step_and_read.m
              │                                  └─> set_param(FastRestart) + sim() + 读 omega/Pe
              │  agent.update() → SAC 损失更新
              │  checkpoint 写入 results/sim_kundur/
              └─> 结束
```

### 3b. Harness / MCP 工具链路径（Claude 远程控制）

```
Claude (MCP client)
  └─> mcp__simulink-tools__harness_*  / simulink_*  (MCP tool call)
        └─> engine/mcp_server.py  (FastMCP server)
              │  注册了 7 个 harness_* 工具 + 22 个 simulink_* 工具
              │
              ├─> harness_scenario_status / harness_model_report / ...
              │     └─> engine/harness_tasks.py
              │           │  读 scenarios/*/harness_reference.json（参考清单）
              │           │  via engine/harness_reference.py（resolve + validate）
              │           │  via engine/harness_registry.py（ScenarioSpec 查找）
              │           │  调用 mcp_simulink_tools.py 中的 simulink_* 函数执行 MATLAB
              │           │  via engine/harness_repair.py（D1-D6 错误 → 修复建议）
              │           └─> 写 results/harness/{scenario}/{run_id}/*.json
              │
              └─> simulink_load_model / simulink_query_params / ...
                    └─> engine/mcp_simulink_tools.py（直接 MATLAB IPC）
                          └─> engine/matlab_session.py（单例 MATLAB Engine）
                                └─> vsg_helpers/*.m
```

### 3c. 训练 smoke test 路径（harness 触发训练）

```
harness_train_smoke_start(scenario_id, run_id)
  └─> engine/harness_tasks.py
        │  检查前置条件：scenario_status.json + model_report.json 存在且 ok
        │  构造命令行：sys.executable + scenarios/*/train_simulink.py + --mode simulink
        └─> subprocess.Popen(cmd, ...)
              └─> 独立进程运行训练
              └─> stdout/stderr 写入 results/harness/{scenario}/{run_id}/train_smoke_stdout.log

harness_train_smoke_poll(scenario_id, run_id)
  └─> 读 Popen 进程状态 + log 文件行数 → 返回 JSON 状态
```

---

## 4. 当前系统的关键接口

### 显式接口（函数/文件/命令）

| 接口 | 类型 | 连接方 |
|---|---|---|
| `FastMCP` server (`engine/mcp_server.py`) | MCP 协议 | Claude ↔ Python engine |
| `harness_reference.json`（两个） | JSON 文件 | harness_tasks ↔ 场景配置真相 |
| `ScenarioSpec` / `harness_registry._REGISTRY` | Python dataclass + dict | harness_tasks ↔ 模型文件路径 |
| `SimulinkBridge.step(H_actions, D_actions)` | Python method | 环境类 ↔ MATLAB Bridge |
| `MatlabSession.call(func_name, *args)` | Python method | Bridge ↔ MATLAB Engine IPC |
| `vsg_step_and_read.m` | MATLAB 函数 | Python ↔ Simulink 模型状态 |
| `BridgeConfig`（frozen dataclass） | Python dataclass | SimulinkBridge ↔ Simulink 模型参数路径模板 |
| `scenarios/*/config_simulink.py` | Python module | 训练脚本 ↔ 所有超参数 |
| `train_simulink.py --mode simulink` | CLI 入口 | 手动训练 / harness smoke 调用 |
| `results/harness/{id}/{run_id}/*.json` | 文件系统 | harness_tasks 写入 / Claude 读取 / harness_train_smoke_poll |

### 隐式依赖（约定/命名/目录）

| 隐式约定 | 涉及方 | 风险 |
|---|---|---|
| `train_simulink.py` 的 `--checkpoint-dir` 默认指向 `results/sim_kundur/checkpoints` | harness smoke 的结果路径假设 | 路径不匹配则 poll 找不到 checkpoint |
| `results/harness/{scenario}/{run_id}/` 目录命名约定 | harness_tasks.py + harness_reports.py | run_id 重复时覆盖旧记录 |
| `vsg_helpers/` 必须在 MATLAB path 上 | `matlab_session.py` 的 `_connect()` 负责 addpath | MATLAB 重启后需重新 addpath |
| `NE39bus_v2.slx` 文件名写死在 `harness_registry.py` | registry ↔ 实际 .slx 文件 | 文件改名则 registry 失效 |
| Simulink 训练脚本中 `env.apply_disturbance()` 在 step 5 触发（hardcoded t=0.5s） | `train_simulink.py` | 非参数化，不读配置 |
| `SACAgent` 从 `env/simulink/sac_agent_standalone.py` 导入，而非 `agents/sac.py` | `scenarios/kundur/train_simulink.py` | 两套 SAC 实现并存，不共享代码 |

---

## 5. 当前项目的"单一事实来源"分别是什么

| 类别 | 文件 | 说明 |
|---|---|---|
| **Harness 规则** | `engine/harness_reference.py`（顶部注释明确：SOURCE OF TRUTH） | 优先级高于 CLAUDE.md |
| **场景契约** | `scenarios/kundur/harness_reference.json`、`scenarios/new_england/harness_reference.json` | 定义 model_name、n_agents、dt、obs_dim 等必须匹配的值 |
| **场景注册** | `engine/harness_registry.py` 的 `_REGISTRY` | 两个场景的模型文件路径和训练入口 |
| **训练超参数** | `scenarios/*/config_simulink.py` | 每场景独立，含 BridgeConfig |
| **全局系统参数** | `config.py`（根目录） | H/D 基值、ANDES 用的训练参数，**Simulink 训练脚本不导入这个文件** |
| **调试知识库** | `memory/simulink_debug.md`（D1-D6 规则） + `engine/harness_repair.py`（D1-D6 实现） | debug.md 是文字库，repair.py 是执行体 |
| **架构导航** | `CLAUDE.md` | 辅助导航，明确声明"有冲突时遵循 harness" |
| **跨会话记忆** | `C:\Users\27443\.claude\projects\...\memory\MEMORY.md` + 31 个 .md 文件 | Claude 专用，代码层不依赖 |

**冲突来源：**
- `config.py`（根目录）和 `scenarios/kundur/config_simulink.py` 都定义了 N_AGENTS=4、LR、BUFFER_SIZE 等参数，但 Simulink 训练脚本只导入 `config_simulink.py`，两者可能数值不同步。
- `agents/sac.py` 和 `env/simulink/sac_agent_standalone.py` 是两套独立实现，定义相同算法但参数接口不同，无共享。

---

## 6. 目前架构中最重要的结构性问题

### P1. 两套 SAC 实现并存，训练脚本走了非主线版本

`agents/sac.py` + `agents/ma_manager.py` + `agents/networks.py` + `agents/replay_buffer.py` 是一套完整的模块化实现。但 `scenarios/kundur/train_simulink.py` 实际导入的是 `env/simulink/sac_agent_standalone.py` 中自包含的 `SACAgent`，后者内嵌了 MLP、GaussianPolicy、ReplayBuffer 等所有组件。两套代码无共享、互相独立演化，`agents/` 目录实际对 Simulink 训练路径没有贡献。

### P2. TrainingMonitor 未被 Simulink 训练脚本调用

`utils/monitor.py` 的 `TrainingMonitor` 已实现 11 种检测（奖励量级/动作坍塌/loss 爆炸/早停等），但 `scenarios/kundur/train_simulink.py` 的训练循环中没有实例化或调用它。这个能力存在但在当前主路径上处于空置状态。

### P3. 根目录 `env/` 下存在旧版环境文件

`env/power_system.py`、`env/multi_vsg_env.py`、`env/andes_vsg_env.py`、`env/andes_ne_env.py`、`env/andes_ne_regca1_env.py`、`env/network_topology.py` 位于 `env/` 根目录，和子目录 `env/andes/`、`env/ode/` 中的同名类并列存在。这些根目录文件是否被任何当前脚本导入，无法从文件名确定，存在"幽灵模块"风险。

### P4. 两个 config 文件管理相同参数域

根目录 `config.py` 管理全局参数，`scenarios/*/config_simulink.py` 管理场景参数，两者的 N_AGENTS / LR / BUFFER_SIZE 等字段有重叠但无引用关系。Simulink 训练脚本只用后者，`config.py` 对当前主路径实际上不起作用。

### P5. Harness smoke 的前置条件是"已有完整 harness 运行记录"

`_train_smoke_preconditions()` 要求 `scenario_status.json` 和 `model_report.json` 都已存在且状态为 ok，才能启动训练。这意味着每次训练前需要先跑 4 个建模任务。对于快速迭代和 CI 来说是非常重的前置链。

### P6. 训练脚本的扰动触发是 hardcoded，不读 config

`train_simulink.py` 中 `if step == int(0.5 / env.DT)` 直接写死了扰动时间，而 `config_simulink.py` 中有 `SCENARIO1_TIME = 0.5` 这个常量，但训练脚本不导入这个值。两处维护同一个数字，迟早产生偏差。

---

## 7. 已经实现并生效 vs 计划中/未接通的内容

### 已实现且真正生效

- `engine/mcp_server.py` + `engine/harness_tasks.py`：Claude 通过 MCP 调用 7 个 harness 工具，会写 JSON 到 `results/harness/`，这条路已经跑过多次（从 results 目录有 kundur_v1-v6、ne39_run1-3 等记录可以确认）
- `engine/matlab_session.py` + `engine/simulink_bridge.py` + `vsg_helpers/vsg_step_and_read.m`：FastRestart 闭环 co-simulation 已验证（`sim_ne39_status.md` 记录 smoke PASSED）
- `engine/harness_repair.py` D1-D6 规则：有对应的 `tests/test_harness_repair.py`，且规则内容与 `memory/simulink_debug.md` 对应，是实际调试经验的编码
- `env/simulink/kundur_simulink_env.py` + `scenarios/kundur/train_simulink.py` + `env/simulink/sac_agent_standalone.py`：Kundur smoke test 曾成功启动训练进程（results/sim_kundur/harness_smoke/ 下有 checkpoint 目录）
- `scenarios/kundur/harness_reference.json` + `scenarios/new_england/harness_reference.json`：两个 JSON 已存在且被 harness_reference.py 读取验证
- `tests/test_harness_*.py`：5 个测试文件针对 harness 层，具体覆盖面不确定，但文件存在

### 实现了但未接入当前主路径

- `agents/sac.py` + `agents/ma_manager.py` + `agents/networks.py` + `agents/replay_buffer.py`：完整模块化实现，但 Simulink 训练脚本不导入这些，实际训练用的是 `sac_agent_standalone.py`
- `utils/monitor.py`（TrainingMonitor）：已实现，未被 Simulink 训练脚本调用
- `scenarios/scalability/`：存在但内容不明，不确定是否在任何主路径中

### 文档/记忆中提到但真实接通状态不确定

- `ma_manager.py` 中的 `clear_buffers()`（"Algorithm 1 line 16" 注释）：注释声称对应论文算法，但 Simulink 训练脚本用的是 `sac_agent_standalone.py` 内部自有 buffer，能否对应论文还需核查
- `agents/centralized_sac.py`：文件存在，但没有任何明显的训练脚本导入它
- NE39 的完整训练（非 smoke）：`ne39_run1-3` 等目录下有 train_smoke 记录，但长训练（1000+ episodes）尚未跑过 Simulink 后端（根据 `sim_ne39_status.md`）

---

## 8. 文字版架构图（当前真实结构）

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Claude (MCP client)                                                    │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │ MCP protocol (FastMCP)
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  engine/mcp_server.py     ← 7 harness_* + 22 simulink_* tools          │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  engine/harness_tasks.py   (harness 控制平面)                      │  │
│  │    ├─ engine/harness_reference.py  ← scenarios/*/harness_ref.json │  │
│  │    ├─ engine/harness_registry.py  ← ScenarioSpec (2 场景)         │  │
│  │    ├─ engine/harness_repair.py    ← D1-D6 repair hints            │  │
│  │    └─ engine/harness_reports.py   → results/harness/*/            │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                   │                                                      │
│  ┌────────────────▼──────────────────────────────────────────────────┐  │
│  │  engine/mcp_simulink_tools.py  (MATLAB 操作层, ~2000 lines)       │  │
│  └────────────────┬──────────────────────────────────────────────────┘  │
│                   │                                                      │
│  ┌────────────────▼──────────────────────────────────────────────────┐  │
│  │  engine/matlab_session.py  (singleton MATLAB Engine, lazy init)   │  │
│  └────────────────┬──────────────────────────────────────────────────┘  │
│                   │ MATLAB Engine IPC (~20s cold start)                 │
│  ┌────────────────▼──────────────────────────────────────────────────┐  │
│  │  vsg_helpers/*.m  (24个 MATLAB 辅助函数)                           │  │
│  │    vsg_step_and_read.m  ←──── 训练热路径                          │  │
│  └────────────────┬──────────────────────────────────────────────────┘  │
│                   │ sim() + set_param(FastRestart)                      │
│  ┌────────────────▼──────────────────────────────────────────────────┐  │
│  │  scenarios/kundur/simulink_models/kundur_vsg.slx  (708KB)        │  │
│  │  scenarios/new_england/simulink_models/NE39bus_v2.slx            │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  训练进程 (由 harness_train_smoke_start 以 subprocess 启动)              │
│                                                                         │
│  scenarios/kundur/train_simulink.py  或  scenarios/new_england/...     │
│      │  导入 config_simulink.py（超参数）                               │
│      │  导入 env/simulink/sac_agent_standalone.py（SAC，自包含）        │
│      │  构造 KundurSimulinkEnv / KundurStandaloneEnv                    │
│      │    └─> engine/simulink_bridge.py → matlab_session → MATLAB      │
│      └─> 训练循环 → 写 results/sim_kundur/checkpoints/*.pt             │
│                                                                         │
│  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ 已实现但未接入的模块 ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  │
│  agents/sac.py + ma_manager.py + networks.py + replay_buffer.py        │
│  utils/monitor.py (TrainingMonitor)                                    │
└─────────────────────────────────────────────────────────────────────────┘

配置/规则层（无代码依赖，只被以上模块读取）
  scenarios/*/config_simulink.py  ←── 场景超参数
  scenarios/*/harness_reference.json  ←── 场景契约（必须匹配值）
  config.py（根目录）  ←── 全局参数（Simulink 主路径实际未使用）
  memory/simulink_debug.md  ←── 调试知识库（人读 + D1-D6 规则来源）
```

---

## 9. 结论

**这个项目本质上是什么架构：**
一个以 **MCP 工具链为核心控制平面** 的 RL 训练框架。它的结构性创新不在于 RL 算法本身，而在于通过 MCP server 把 MATLAB/Simulink 的操作、模型验证、训练启动全部暴露给 Claude 作为自动化接口。这使得整个调试-修复-验证-训练循环可以被 LLM agent 驱动，而不需要人工登录 MATLAB 手动操作。

**它现在更像什么系统：**
与其说是一个 RL 训练框架，不如说是一个 **"仿真器集成 + agent 远程操控"** 的工程平台，RL 训练只是其中一个被编排的子流程。`engine/` 目录中的 harness 基础设施（6 个 harness_*.py 文件 + MCP server）在代码量和工程完成度上已经超过了训练逻辑本身。

**当前最影响后续开发效率的架构瓶颈：**

1. **两套 SAC 实现割裂**：`agents/` 目录积累了模块化设计，但 Simulink 训练脚本走的是 `sac_agent_standalone.py` 那套。下次要改 SAC 逻辑或加 TrainingMonitor 集成，需要先决定到底以哪套为准，否则改了一边另一边不会同步。

2. **TrainingMonitor 处于空置状态**：长训练最容易出的问题（critic loss 爆炸、entropy 衰减、奖励坍塌）已经有检测代码，但当前训练路径完全不调用它，等于裸跑训练没有任何自动报警。

3. **smoke test 前置链过重**：每次训练前需要先走完 scenario_status → model_inspect → model_report 这条链，才能触发训练。对于调试期的快速迭代（只改奖励函数或网络参数）来说，这个代价过高。
