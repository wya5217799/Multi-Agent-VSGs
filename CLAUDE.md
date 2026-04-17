# Multi-Agent VSGs — 代码导航指南
> 路径字典。决策顺序: `AGENTS.md` → `docs/paper/yang2023-fact-base.md` → `engine/harness_reference.py` → 本文件。与 AGENTS.md 冲突以 AGENTS.md 为准。

## 项目概述
Yang et al. TPWRS 2023 论文复现。多智能体 SAC 控制 VSG 的虚拟惯量 H 和阻尼 D。
**活跃路径 = Simulink × {Kundur, NE39}**。ANDES/ODE 4 行为历史遗留，仅作路径字典，不主动投入工作。

## 后端 × 拓扑 → 关键文件

| 场景 | 环境类 | 训练脚本 | 配置 |
|------|--------|----------|------|
| ANDES Kundur | `env/andes/andes_vsg_env.py::AndesMultiVSGEnv` | `scenarios/kundur/train_andes.py` | `config.py` |
| ANDES NE39 | `env/andes/andes_ne_env.py::AndesNEEnv` | `scenarios/new_england/train_andes.py` | `config.py` |
| ODE Kundur | `env/ode/multi_vsg_env.py::MultiVSGEnv` | `scenarios/kundur/train_ode.py` | `config.py` |
| ODE NE39 | `env/ode/multi_vsg_env.py::MultiVSGEnv` | `scenarios/new_england/train_ode.py` | `config.py` |
| Simulink Kundur | `env/simulink/kundur_simulink_env.py` | `scenarios/kundur/train_simulink.py` | `scenarios/kundur/config_simulink.py` |
| Simulink NE39 | `env/simulink/ne39_simulink_env.py` | `scenarios/new_england/train_simulink.py` | `scenarios/new_england/config_simulink.py` |

> **Scenario ID（harness + training 通用）**：`kundur` 和 `ne39`。
> 注意：`kundur_simulink`、`kundur_simulink_env` 等均无效，registry 只认上述两个 ID。

## 核心模块入口

**Paper Track**
- **SAC Agent**: `agents/sac.py` — Actor/Critic/自动熵调节
- **多智能体管理**: `agents/ma_manager.py` — N 个 SAC 的协调训练
- **共享网络结构**: `agents/networks.py` — GaussianActor, DoubleQCritic
- **ANDES 环境基类**: `env/andes/base_env.py` — step/reset/obs/reward 共享逻辑
- **系统参数**: `config.py` — H/D 基值、扰动范围、训练超参数

**AI Collaboration Track** — 三层控制线（术语定义见 `docs/decisions/2026-04-17-control-surface-convention.md`）：
- **Model Harness**（建模质量门）/ **Smoke Bridge**（入口验证桥）/ **Training Control Surface**（训练观察面）
- **训练监控**: `utils/monitor.py::TrainingMonitor`
- **Training Control Surface**: `engine/training_launch.py::get_training_launch_status` — 单次返回所有启动事实（解释器路径、脚本、最近 run 状态、是否有活跃进程）

**辅助脚本目录**：
- `scripts/` — 通用仓库辅助脚本（启动、lint、profiling、workspace hygiene 等）
- `probes/` — 场景专用可复用回归探针（绑定模型语义，如 `probes/ne39/probe_phang_sensitivity.m`）；一次性排查脚本不属于此处

## MATLAB Engine 三层接口（`engine/` + `slx_helpers/`）

调用链：`SimulinkEnv → SimulinkBridge.step() → MatlabSession.call() → slx_step_and_read.m`（1 次 IPC/step）

| 层 | 关键文件 | 职责 |
|----|----------|------|
| L1 引擎 | `engine/matlab_session.py` | 单例、懒加载、被动重连 |
| L2 MATLAB | `slx_helpers/slx_step_and_read.m` | 批量 set_param + sim + 读状态 |
| L2 MATLAB | `slx_helpers/slx_inspect_model.m` 等 | 模型检查/校验/追踪 |
| L2 MATLAB | `slx_helpers/slx_run_quiet.m` | 静默执行，吞噪声只返回关键行 |
| L2 MATLAB | `slx_helpers/slx_check_params.m` | 参数物理范围校验，防静默单位错误 |
| L3 Python | `engine/simulink_bridge.py` | RL 训练接口（step/reset/close） |
| L3 Python | `engine/mcp_simulink_tools.py` | Claude MCP 工具 |

Simulink 建模规则见 `docs/knowledge/simulink_rules.md`。

## 常见修改点定位

| 修改目标 | 去哪里找 |
|----------|----------|
| 奖励函数（Simulink 主线） | `env/simulink/{kundur,ne39}_simulink_env.py::_compute_reward()`；历史 ANDES: `env/andes/base_env.py::_compute_rewards()` |
| 观测向量（Simulink 主线） | `env/simulink/{kundur,ne39}_simulink_env.py::_build_obs()`；历史 ANDES: `env/andes/base_env.py::_build_obs()` |
| 动作空间/映射（Simulink 主线） | `env/simulink/{kundur,ne39}_simulink_env.py::step()`；历史 ANDES: `env/andes/base_env.py::step()` 顶部 |
| VSG 参数范围 | `config.py` — `H_MIN/H_MAX/D_MIN/D_MAX` |
| 训练超参数 | `config.py` — `LR/BATCH_SIZE/BUFFER_SIZE` 等 |
| 训练循环逻辑 | 各 `scenarios/*/train_*.py` — 每个场景独立实现 |
| 启动 Simulink 训练（用户） | `scripts/launch_training.ps1 [kundur\|ne39\|both]` |
| 启动 Simulink 训练（agent） | `engine/training_launch.py::get_training_launch_status(scenario_id)` → 取 `launch` 字段执行 |
| Simulink 奖励 | `env/simulink/kundur_simulink_env.py` 或 `env/simulink/ne39_simulink_env.py` |
| Simulink step 批量逻辑 | `slx_helpers/slx_step_and_read.m` |
| Simulink 模型构建 | `scenarios/kundur/simulink_models/build_powerlib_kundur.m` |
| 单模型诊断探针 | `probes/ne39/` — 叶子节点，不被工具链调用 |
| MATLAB 引擎配置 | `engine/matlab_session.py` (重连、路径) |
| Simulink 桥接配置 | `scenarios/kundur/config_simulink.py::KUNDUR_BRIDGE_CONFIG` |
| 绘图样式 | `plotting/paper_style.py` |

## 重要注意事项

- **Token 熔断器**：消耗 ~5000 token 但无实质进展（无 passing test/成功工具调用/确认修改）→ 立即停手，分析是哪个工具/流程失效，修复后再继续
- NE 39节点系统频率为 **60Hz**，Kundur 为 50Hz，切勿混淆
- ANDES TDS 分段运行前必须清除 `tds.busted`，见 `env/andes/base_env.py`
- `action=[0,0]` 在非对称动作空间中不等于"不控制"
- `results/` 训练结果文件已于 2026-04-06 全部清理（.pt 模型、figures、logs），只剩 `results/harness/` 存放 harness 运行记录
