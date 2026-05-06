# Multi-Agent VSGs — 代码导航指南
> 路径字典。决策顺序: `AGENTS.md` → `docs/paper/kd_4agent_paper_facts.md` (KD 4-agent 唯一规范) → `engine/harness_reference.py` → 本文件。

## 🚨 当前活跃路径 = ANDES Kundur (2026-05-06 切换, 2026-05-07 真相修正)

**论文复现主线在 ANDES**, 不在 Simulink. 新对话进来**首先读** `quality_reports/handoff/2026-05-07_andes_6axis_recovery_handoff.md` (5 分钟接续), 然后按需读:
1. `docs/paper/andes_replication_status_2026-05-07_6axis.md` — 真实状态 (6-axis 评估)
2. `quality_reports/audits/2026-05-07_andes_6axis_failure_analysis.md` — 失败分析
3. `quality_reports/plans/2026-05-07_andes_6axis_recovery.md` — 恢复 plan
4. `evaluation/paper_grade_axes.py` — 6-axis 量化函数
5. `scenarios/kundur/NOTES_ANDES.md` — 修代码必读

**复现进展速查 (2026-05-07 修正, 6-axis 真实)**:
- ⚠ 旧 "cum_rf paper-level" 声明已被 6-axis 推翻
- 真实状态: 所有 21 ckpt overall score **0.033-0.036 / 1.0**
- 5/6 axis 全 fail: max_df 3-4×偏大 / final_df 2-4× / settling ∞ / ΔH range 70× 偏小 / ΔD range 45× 偏小
- 仅 smoothness 偶尔 0.7-0.9
- 量化函数: `evaluation/paper_grade_axes.py`
- 完整 ranking: `results/andes_paper_alignment_6axis_2026-05-07.json`

**Simulink 路径 (kundur_cvs_v3 / ne39)**: 历史活跃, 现在维护性. PAPER-ANCHOR LOCK 仍 active.

## 代码搜索规则
- **已知确切符号/字符串** → 用 Grep/Glob（快，精确）
- **语义查询**（"奖励函数在哪"、"MATLAB 怎么调用"、"step 逻辑"）→ 优先用 `search_code` MCP 工具
- 探索陌生模块或跨文件追踪逻辑时，先用 `search_code` 再用 Read 深入

## ⚠️ 修模型前必读 NOTES

| 改什么 | 读哪份 NOTES |
|---|---|
| **`env/andes/*`、`scenarios/kundur/train_andes*.py`、`scripts/research_loop/eval_paper_spec_v2.py`** | **`scenarios/kundur/NOTES_ANDES.md`** (2026-05-07 6-axis 修正 + L4 重构, **必读**) |
| 论文复现量级对账 (6-axis 真实) | `docs/paper/andes_replication_status_2026-05-07_6axis.md` ← **当前权威** |
| `scenarios/kundur/*`、`env/simulink/kundur_simulink_env.py` | `scenarios/kundur/NOTES.md` |
| `scenarios/new_england/*`、`env/simulink/ne39_simulink_env.py` | `scenarios/new_england/NOTES.md` |
| `env/simulink/_base.py`、`plotting/evaluate.py`、`utils/training_viz.py`、`engine/simulink_bridge.py` | `env/simulink/COMMON_NOTES.md` + 两份场景 NOTES |
| `env/ode/*`、`scenarios/*/train_ode.py` | `env/ode/NOTES.md` |

改完顺手更新对应 NOTES：新发现加到"已知事实"，失效的直接删，证伪的尝试加到"试过没用的"。

## 项目概述
Yang et al. TPWRS 2023 论文复现。多智能体 SAC 控制 VSG 的虚拟惯量 H 和阻尼 D。

**活跃路径 (2026-05-06 切换): ANDES Kundur** — 6-axis 真实评估暴露 0% paper-aligned, 已写 4 phase recovery plan.
**Simulink × {Kundur, NE39}**: 历史活跃, 维护性, PAPER-ANCHOR LOCK 仍 active.
**ODE**: 路径字典, 不主动投入.

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

**Training Management 4 角色**（详见 `docs/knowledge/training_management.md`）：
- **Launcher** = `scripts/launch_training.ps1`（用户入口）+ `engine/training_launch.py`（agent 入口）
- **Monitor** = `utils/monitor.py::TrainingMonitor`（进程内写） + `utils/run_protocol.py`（文件 I/O 协议）
- **Observer** = `engine/training_tasks.py::training_status` / `training_diagnose`（MCP 进程外读）
- **Evaluator** = `engine/training_tasks.py::training_evaluate_run` / `training_compare_runs`（MCP 进程外评估）
- **共享 schema**: `engine/run_schema.py::RunStatus` — `training_status.json` 类型化视图，所有进程外读取统一走 `read_run_status(run_dir)`

**辅助脚本目录**：
- `scripts/` — 通用仓库辅助脚本（启动、lint、profiling、workspace hygiene 等）
- `probes/` — 场景专用可复用回归探针（绑定模型语义）；`probes/<scenario>/gates/` 存放当前开发阶段的流水线门控脚本；一次性排查脚本用完即弃，不落 `probes/`

## MATLAB Engine 三层接口（`engine/` + `slx_helpers/`）

调用链：`SimulinkEnv → SimulinkBridge.step() → MatlabSession.call() → slx_step_and_read.m`（1 次 IPC/step）

| 层 | 关键文件 | 职责 |
|----|----------|------|
| L1 引擎 | `engine/matlab_session.py` | 单例、懒加载、被动重连 |
| L2 MATLAB | `slx_helpers/slx_step_and_read.m` | 批量 set_param + sim + 读状态 |
| L2 MATLAB | `slx_helpers/slx_inspect_model.m` 等 | 模型检查/校验/追踪 |
| L2 MATLAB | `slx_helpers/slx_run_quiet.m` | 静默执行，吞噪声只返回关键行 |
| L3 Python | `engine/simulink_bridge.py` | RL 训练接口（step/reset/close） |
| L3 Python | `engine/mcp_simulink_tools.py` | Claude MCP 工具 |

Simulink 建模规则见 `docs/knowledge/simulink_rules.md`。
写计划涉及 Simulink 步骤：参考 `docs/knowledge/simulink_plan_template.md` 标准 MCP 工具序列模板。

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
| 训练 run 数据 schema | `engine/run_schema.py::RunStatus` + `read_run_status(run_dir)` — 所有进程外读取统一入口 |
| Training management 总览 | `docs/knowledge/training_management.md` — 4 角色（Launcher/Monitor/Observer/Evaluator）+ status 字段契约 |
| Simulink 奖励 | `env/simulink/kundur_simulink_env.py` 或 `env/simulink/ne39_simulink_env.py` |
| Simulink step 批量逻辑 | `slx_helpers/slx_step_and_read.m` |
| Simulink 模型构建 | `scenarios/kundur/simulink_models/build_powerlib_kundur.m` |
| Kundur CVS 扰动 dispatch | `scenarios/kundur/disturbance_protocols.py`（4 adapter，C1 2026-04-29）；env 中 `_apply_disturbance_backend` CVS 分支只剩 `resolve_disturbance(...)` + `protocol.apply(...)` |
| Kundur 扰动 workspace var schema | `scenarios/kundur/workspace_vars.py::resolve(...)`（C3）；name-valid vs `require_effective` 二层校验，effective 集合靠物理修复推进 |
| Kundur Scenario VO 入口 | `scenarios/kundur/scenario_loader.py::Scenario` + `env.reset(scenario=Scenario(...))`（C4 2026-04-29）；`options['trigger_at_step']` 控触发时机；§1.5b：`info['resolved_disturbance_type']` 是 audit 单一真值 |
| 单模型诊断探针 | `probes/kundur/`（5 个回归门）+ `probes/ne39/`；`probes/kundur/gates/` 为 CVS 开发流水线门控 |
| MATLAB 引擎配置 | `engine/matlab_session.py` (重连、路径) |
| Simulink 桥接配置 | `scenarios/kundur/config_simulink.py::KUNDUR_BRIDGE_CONFIG` |
| 绘图样式 | `plotting/paper_style.py` |
| **ANDES eval 单一入口 (L4 lock-in 2026-05-07)** | `scripts/research_loop/eval_paper_spec_v2.py` — 老入口 (`_eval_paper_grade_andes*`, `_phase{3,4,9}*_eval`, `_re_eval_best_ckpts`) 已归档 `scenarios/kundur/_legacy_2026-04/` |
| 6-axis paper-spec 量化 | `evaluation/paper_grade_axes.py` |
| Fig 6/7/8/9 (LS1/LS2 traces) 生成 | `paper/figure_scripts/figs6_9_ls_traces.py` |

## 重要注意事项

- **Token 熔断器**：消耗 ~5000 token 但无实质进展（无 passing test/成功工具调用/确认修改）→ 立即停手，分析是哪个工具/流程失效，修复后再继续
- NE 39节点系统频率为 **60Hz**，Kundur 为 50Hz，切勿混淆
- ANDES TDS 分段运行前必须清除 `tds.busted`，见 `env/andes/base_env.py`
- `action=[0,0]` 在非对称动作空间中不等于"不控制"
- `results/` 训练结果文件已于 2026-04-06 全部清理（.pt 模型、figures、logs），只剩 `results/harness/` 存放 harness 运行记录
