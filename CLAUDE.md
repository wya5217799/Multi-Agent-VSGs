> **⚠ HARNESS FIRST — 行动前必读**
> CLAUDE.md 不是 source of truth。所有决策必须基于 harness 当前状态。
> 有冲突时：**忽略 CLAUDE.md，遵循 harness**。
> 任何行动前，先定位并读取 harness（`engine/harness_reference.py`）。

# Multi-Agent VSGs — 代码导航指南

## 项目概述
Yang et al. TPWRS 2023 论文复现。多智能体 SAC 控制 VSG 的虚拟惯量 H 和阻尼 D。
6 个训练场景：3 个后端（ANDES/ODE/Simulink）× 2 个拓扑（Kundur 4机 / NE 39节点）。

## 后端 × 拓扑 → 关键文件

| 场景 | 环境类 | 训练脚本 | 配置 |
|------|--------|----------|------|
| ANDES Kundur | `env/andes/andes_vsg_env.py::AndesMultiVSGEnv` | `scenarios/kundur/train_andes.py` | `config.py` |
| ANDES NE39 | `env/andes/andes_ne_env.py::AndesNEEnv` | `scenarios/new_england/train_andes.py` | `config.py` |
| ODE Kundur | `env/ode/multi_vsg_env.py::MultiVSGEnv` | `scenarios/kundur/train_ode.py` | `config.py` |
| ODE NE39 | `env/ode/multi_vsg_env.py::MultiVSGEnv` | `scenarios/new_england/train_ode.py` | `config.py` |
| Simulink Kundur | `env/simulink/kundur_simulink_env.py` | `scenarios/kundur/train_simulink.py` | `scenarios/kundur/config_simulink.py` |
| Simulink NE39 | `env/simulink/ne39_simulink_env.py` | `scenarios/new_england/train_simulink.py` | `scenarios/new_england/config_simulink.py` |

## 核心模块入口

- **SAC Agent**: `agents/sac.py` — Actor/Critic/自动熵调节
- **多智能体管理**: `agents/ma_manager.py` — N 个 SAC 的协调训练
- **共享网络结构**: `agents/networks.py` — GaussianActor, DoubleQCritic
- **ANDES 环境基类**: `env/andes/base_env.py` — step/reset/obs/reward 共享逻辑
- **系统参数**: `config.py` — H/D 基值、扰动范围、训练超参数
- **训练监控**: `utils/monitor.py::TrainingMonitor`

## MATLAB Engine 三层接口（`engine/` + `vsg_helpers/`）

调用链：`SimulinkEnv → SimulinkBridge.step() → MatlabSession.call() → vsg_step_and_read.m`（1 次 IPC/step）

| 层 | 关键文件 | 职责 |
|----|----------|------|
| L1 引擎 | `engine/matlab_session.py` | 单例、懒加载、被动重连 |
| L2 MATLAB | `vsg_helpers/vsg_step_and_read.m` | 批量 set_param + sim + 读状态 |
| L2 MATLAB | `vsg_helpers/vsg_inspect_model.m` 等 | 模型检查/校验/追踪 |
| L2 MATLAB | `vsg_helpers/vsg_run_quiet.m` | 静默执行，吞噪声只返回关键行 |
| L2 MATLAB | `vsg_helpers/vsg_check_params.m` | 参数物理范围校验，防静默单位错误 |
| L3 Python | `engine/simulink_bridge.py` | RL 训练接口（step/reset/close） |
| L3 Python | `engine/mcp_simulink_tools.py` | Claude MCP 工具 |

**Simulink 建模规则（所有 Simulink 工作均适用）**

- **Bug 处理**：**严禁**诊断代码。本地明确错误（拼写/路径/参数值）直接修复；其他失败 → 先读错误输出：有错误信息则查 `simulink_debug.md` → 未命中再 WebSearch；无错误信息（超时/崩溃无输出）可分段定位后再查；**不得未查库/搜索直接换 API 重试**；WebSearch 最多 3 轮（1轮=1搜索+1修复），不确定或未解决则汇总给用户。（R2025b 环境，版本相关带版本号）
- **批判性审查**：用户反馈**或自己搜到的方案**有疑点/矛盾/版本不匹配 → 指出问题，不盲目采纳。
- **知识库**：改 `.slx`/build 脚本前读 `simulink_base.md`；任何 Simulink/MATLAB 报错（含 `matlab_session`/`simulink_bridge`/`vsg_helpers` 冒泡的错误）先查 `simulink_debug.md` → 命中则照做，未命中则走上述 Bug 处理流程 → 只存可复现的 Simulink 行为问题（非一次性拼写/路径错误），存回库后展示用户确认。
- **有界性检查（debug 分流门控）**：进入假设测试前先问：能否列出 ≤5 个具体原因？**能** → 正常 systematic-debug；**不能**（API 行为未知/无 error/首次遇到该 block）→ 这是无界问题，**禁止盲试**，改走发现流程：WebSearch 1轮定位 → 未解决则给用户具体关键词停手。
- **新 block 预飞行发现**：知识库未覆盖的 block 类型，建模前必须先查端口和参数名（`connectionPortProperties` + `isfield` 逐一查），将结果存入 `simulink_base.md` 再开始建模。一次发现成本 1-2k token，后续使用零探索成本。
- **建模后验证**：build 脚本写完后调用 `vsg_check_params(model)` 做参数物理范围审计，防止静默单位错误漏网。
- **基础设施约束**：遇到工具超时/MCP 限制等非 Simulink 问题，确认根因后立即停下，告知用户并列出可选方案，不得持续擅自尝试。Build 脚本超时默认方案：交付脚本，用户在 MATLAB 命令行手动运行。

- **建模操作模式（强制）**：所有 add_block/set_param/addConnection 必须先用 Write 工具写成 .m 脚本，再 `mcp__matlab__evaluate_matlab_code("vsg_run_quiet('脚本名')")` 一次执行。**禁止逐行 evaluate_matlab_code 做建模操作。**（单次 get_param 查询仍可直接调用，无需脚本化。）
- **批量查询（强制）**：查询多个 block 参数用 `vsg_batch_query`，不循环调用 get_param。
**建模辅助工具（`vsg_helpers/`）**：`vsg_run_quiet(code)` 吞输出噪声 · `vsg_check_params(model)` 参数范围审计 · `vsg_batch_query(model, blocks)` 批量参数查询

## 常见修改点定位

| 修改目标 | 去哪里找 |
|----------|----------|
| 奖励函数 | `env/andes/base_env.py::_compute_rewards()` |
| 观测向量 | `env/andes/base_env.py::_build_obs()` |
| 动作空间/映射 | `env/andes/base_env.py::step()` 顶部 |
| VSG 参数范围 | `config.py` — `H_MIN/H_MAX/D_MIN/D_MAX` |
| 训练超参数 | `config.py` — `LR/BATCH_SIZE/BUFFER_SIZE` 等 |
| 训练循环逻辑 | 各 `scenarios/*/train_*.py` — 每个场景独立实现 |
| Simulink 奖励 | `env/simulink/kundur_simulink_env.py` 或 `ne39_simulink_env.py` |
| Simulink step 批量逻辑 | `vsg_helpers/vsg_step_and_read.m` |
| Simulink 模型构建 | `scenarios/kundur/simulink_models/build_powerlib_kundur.m` |
| MATLAB 引擎配置 | `engine/matlab_session.py` (重连、路径) |
| Simulink 桥接配置 | `scenarios/kundur/config_simulink.py::KUNDUR_BRIDGE_CONFIG` |
| 绘图样式 | `plotting/paper_style.py` |

## 目录结构

```
agents/        SAC (sac, ma_manager, networks, replay_buffer)
engine/        MATLAB Engine 三层接口 (matlab_session, simulink_bridge, mcp_simulink_tools)
env/{andes,ode,simulink}/  三后端环境实现
vsg_helpers/   MATLAB .m 函数 (step_and_read, inspect, run_quiet, check_params 等)
scenarios/{kundur,new_england}/  训练/评估/建模脚本 × 3后端
utils/         monitor (TrainingMonitor)
plotting/      论文图表 | results/ 训练结果 | _archive/ 废弃代码(勿改)
```

## 重要注意事项

- **Token 熔断器**：消耗 ~5000 token 但无实质进展（无 passing test/成功工具调用/确认修改）→ 立即停手，分析是哪个工具/流程失效，修复后再继续，见 `feedback_token_circuit_breaker.md`
- NE 39节点系统频率为 **60Hz**，Kundur 为 50Hz，切勿混淆
- ANDES TDS 分段运行前必须清除 `tds.busted`，见 `env/andes/base_env.py`
- `action=[0,0]` 在非对称动作空间中不等于"不控制"，见 `feedback_action_mapping.md`
- `results/` 训练结果文件已于 2026-04-06 全部清理（.pt 模型、figures、logs），只剩 `results/harness/` 存放 harness 运行记录

## 记忆维护规则（每次对话必读）

**写入（自动，不需要用户提醒）：**
- 完成重大变更（重构、新功能、架构决策）→ 更新对应 status 文件 + MEMORY.md 索引
- 发现技术陷阱 → 写 `feedback_*.md`
- Simulink 相关 → `sim_kundur_status.md` 或 `sim_ne39_status.md`
- ANDES 相关 → `andes_kundur_status.md` 或 `andes_ne39_status.md`

**清理（半自动，需告知用户后执行）：**
- MEMORY.md 索引超过 50 条时，列出可合并项，等用户确认后合并
- Handoff 文件内容已被 status/decision 文件覆盖时，提议删除，等用户确认
- feedback 同类项超过 3 个时，提议合并为 1 个，等用户确认
- **禁止静默删除任何记忆文件**

**质量规则：**
- CLAUDE.md 保持 <120 行，超了就精简
- MEMORY.md 索引每条 <150 字符，内容只放"不读就会犯错"的导航和规则
