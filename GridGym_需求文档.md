# GridGym 项目需求文档

> 本文档是 Claude Code 的项目指导文件，定义了 GridGym 的定位、当前代码状态、重构目标和边界约束。

---

## 一、项目定位

GridGym 是电力系统动态仿真与强化学习之间的桥梁层。它不是仿真器（ANDES 已经做了），不是通用 RL 算法库（Stable-Baselines3 已经做了），而是把仿真能力封装成 Gymnasium 标准接口，让研究者专注于 RL 算法创新。

类比关系：
- ANDES 之于 GridGym ≈ PandaPower 之于 Grid2Op（底层仿真器 vs 上层 RL 接口）
- GridGym 之于电力系统控制 ≈ OpenAI Gym 之于 Atari 游戏（标准化训练环境）

当前切入点：VSG（虚拟同步发电机）自适应参数控制，支持单机和多机 MARL。未来可扩展至 LFC、微电网调度、电压调节等场景。

核心依赖：ANDES（仿真后端）、Gymnasium（接口标准）、PyTorch（神经网络）。

GridGym 本身负责：
- 状态观测封装（频率偏差、角加速度、有功出力、邻居频率信息）
- 动作空间定义（ΔM、ΔD 连续调节）
- 奖励函数设计（可插拔架构）
- Episode 管理（reset/step 循环、扰动注入）
- 多智能体通信拓扑管理（环形/全连接/自定义，含故障和延迟模拟）

GridGym 本身还负责：
- **训练诊断与监控**（领域级健康检测，详见第六章）

GridGym 不实现：
- 电力系统仿真求解（由 ANDES 负责）
- RL 算法本身（内置 SAC 仅作为 baseline 参考，用户可用任意框架）
- 通用 RL 训练监控（loss/entropy/gradient 等算法层面指标由 SB3/RLlib/WandB 负责）

### 生态位定位

GridGym 是电力系统仿真与 RL 框架之间的**中间层**：

```
用户的算法（SB3 / RLlib / TorchRL / 自定义）
        ↕  PettingZoo ParallelEnv API
    GridGym（环境 + 领域诊断）       ← 本项目
        ↕  内部接口
    ANDES（仿真后端）
```

- **下层（ANDES）**：只负责仿真求解，不懂 RL 训练循环
- **上层（SB3/RLlib 等）**：提供通用 RL 训练监控（loss、entropy），但不懂电力系统物理量
- **GridGym 的独特价值**：桥接两者，提供只有领域中间层才能做的**电力系统 RL 训练诊断**

上层 RL 框架选型建议：
- **当前项目（论文复现）**：保持自定义 SAC（~170 行，精确对标论文 Algorithm 1）
- **GridGym 库**：环境层实现 PettingZoo `ParallelEnv` API，让任意 MARL 框架均可接入
- **参考框架**：SB3（可靠工具箱，适合快速实验）、RLlib（工业级，适合大规模并行）、EPyMARL/TorchRL（多智能体专用）

---

## 二、当前代码状态

### 2.1 项目根目录

`C:\Users\27443\Desktop\Multi-Agent  VSGs\`

### 2.2 已有模块及成熟度

| 模块 | 文件 | 行数 | 成熟度 | 说明 |
|------|------|------|--------|------|
| 环境基类 | `env/andes/base_env.py` | 413 | ★★★★ | 抽象设计好，reset/step/reward 模板方法清晰 |
| Kundur 环境 | `env/andes/andes_vsg_env.py` | 155 | ★★★★ | 4 台 VSG，Kundur 两区域系统，完整可用 |
| NE 39-bus 环境 | `env/andes/andes_ne_env.py` | 154 | ★★★★ | 8 台 VSG，IEEE 39-bus，含发电机跳闸 |
| REGCA1 环境 | `env/andes/andes_ne_regca1_env.py` | 存在 | ★★★ | 新能源替代场景 |
| 全局配置 | `config.py` | 142 | ★★★ | 参数集中管理，但硬编码 Kundur 4-agent |
| SAC 智能体 | `agents/sac.py` | 存在 | ★★★★ | 标准 SAC + 自动熵调节 |
| 神经网络 | `agents/networks.py` | 存在 | ★★★★ | GaussianActor + DoubleQCritic |
| 多智能体管理 | `agents/ma_manager.py` | 75 | ★★★ | 协调 N 个独立 SAC，接口清晰 |
| Replay Buffer | `agents/replay_buffer.py` | 存在 | ★★★★ | 标准实现 |
| ODE 简化环境 | `env/ode/` | 存在 | ★★★★ | Kron 缩减摇摆方程，用于快速验证 |
| 绘图工具 | `plotting/` | 多个文件 | ★★★ | 论文级图表生成 |

### 2.3 已有训练结果

- `results/andes_models/` ~ `andes_models_v4/`：Kundur 环境多轮训练，每轮 2000 episodes，4 个 agent 权重完整保存
- `results/andes_ne_models/`：NE 39-bus 环境训练，8 个 agent（含 agent_4 ~ agent_7）
- `results/figures/` 和 `results/figures_paper_style/`：Fig 4-21 全部复现
- `results/scalability/`：分布式 vs 集中式对比实验
- 论文复现结果完整：分布式 MADRL、通信故障鲁棒性、通信延迟鲁棒性均已验证

### 2.4 当前代码的核心问题

1. **没有 Gym 标准接口**：外部用户无法 `gym.make("...")` 直接使用
2. **配置硬编码**：`config.py` 写死了 N_AGENTS=4、Kundur 参数，切换场景要改源码
3. **不可 pip install**：缺少 `pyproject.toml`，无法作为包分发
4. **导入路径脆弱**：`base_env.py` 直接 `import config as cfg`，重构后会断
5. **缺少文档和示例**：没有 quickstart，新用户无法上手
6. **名字未统一**：代码中仍使用 MAVSG-Gym 旧名

---

## 三、重构目标（Phase 1：MVP）

### 3.1 最终用户体验

```python
import gridgym

# 一行创建环境
env = gridgym.make("Kundur-4VSG-v0")

# 标准 Gymnasium 循环
obs, info = env.reset(seed=42)
for step in range(50):
    actions = {i: env.action_space[i].sample() for i in range(env.n_agents)}
    obs, rewards, terminated, truncated, info = env.step(actions)
    if terminated or truncated:
        break
```

### 3.2 目标目录结构

```
gridgym/                        # ← 从 Multi-Agent VSGs 重构而来
├── pyproject.toml
├── README.md
├── LICENSE                     # MIT
│
├── gridgym/                    # 核心包
│   ├── __init__.py             # make() + 版本号 + 环境注册
│   ├── registry.py             # 环境注册表
│   │
│   ├── envs/
│   │   ├── __init__.py
│   │   ├── base_env.py         # ← 从 env/andes/base_env.py 重构
│   │   ├── gym_wrapper.py      # Gymnasium API 适配器（新增）
│   │   ├── kundur.py           # ← 从 env/andes/andes_vsg_env.py 重构
│   │   ├── new_england.py      # ← 从 env/andes/andes_ne_env.py 重构
│   │   └── rewards.py          # 可插拔奖励函数（从 base_env 提取）
│   │
│   ├── agents/                 # 内置 baseline（非核心，仅参考）
│   │   ├── __init__.py
│   │   ├── sac.py
│   │   ├── networks.py
│   │   ├── replay_buffer.py
│   │   └── ma_manager.py
│   │
│   ├── configs/                # YAML 配置（新增）
│   │   ├── kundur_4vsg.yaml
│   │   ├── ne39_8vsg.yaml
│   │   └── default_sac.yaml
│   │
│   ├── monitor.py              # 训练诊断模块（P0.5，详见第六章）
│   │
│   └── utils/
│       ├── __init__.py
│       ├── plotting.py
│       └── logger.py
│
├── examples/
│   ├── quickstart.py           # 10 行跑通
│   ├── train_kundur.py         # 完整训练示例
│   └── custom_reward.py        # 自定义奖励
│
├── benchmarks/                 # 预训练权重 + 收敛曲线
│   ├── kundur_sac/
│   └── ne39_sac/
│
└── tests/
    ├── test_env.py
    └── test_integration.py
```

### 3.3 具体改造任务

**P0（必须做，MVP 发布前）：**

1. **包结构创建**：建立 `gridgym/` 目录，按上述结构组织代码
2. **配置系统重构**：用 YAML + dataclass 替代硬编码的 `config.py`，每个场景一个 YAML 文件。`base_env.py` 不再 `import config`，而是接收配置对象
3. **Gymnasium 接口适配**：在 `base_env.py` 外包一层 `gym_wrapper.py`，兼容 Gymnasium 的 `reset()` 返回 `(obs, info)` 和 `step()` 返回 `(obs, reward, terminated, truncated, info)`
4. **环境注册表**：实现 `gridgym.make("Kundur-4VSG-v0")` 工厂函数
5. **pyproject.toml**：让项目可 `pip install -e .`
6. **quickstart 示例**：`examples/quickstart.py`，验证环境能跑通

**P0.5（训练基础设施，优先于 MVP 重构）：**

> 当前最紧急的需求：让训练过程可观测、可诊断，避免"跑 2000 轮才发现没训练上"。

7. **训练诊断模块 `TrainingMonitor`**：独立模块（详见第六章），提供领域级健康检测
8. **TDS 失败检测**：已实现 — step() 中检测仿真时间未推进则终止 episode 并给 -50 惩罚
9. **奖励缩放修复**：r_h/r_d 必须使用归一化动作 [-1,1]，不是物理 ΔH/ΔD（当前 bug 导致 r_h/r_d 比 r_f 大 360 万倍）

**P1（重要但可稍后）：**

10. **奖励函数可插拔**：从 `base_env._compute_rewards()` 提取为独立的 `rewards.py`，支持用户自定义
11. **PettingZoo 适配**：实现 `ParallelEnv` 接口，让 GridGym 环境可被任意 MARL 框架使用（从 P2 提升）
12. **README 中英文**：项目介绍 + 安装 + quickstart + 环境列表
13. **单元测试**：至少覆盖 env.reset()、env.step()、配置加载
14. **benchmark 数据**：从 `results/` 整理预训练权重和收敛曲线

**P2（未来做）：**

15. Docker 镜像
16. 更多电网场景（IEEE 118-bus 等）
17. TensorBoard/WandB 后端集成（TrainingMonitor 的可视化扩展）
18. PyPI 发布

---

## 四、关键设计约束

### 4.1 不要改的东西

- **base_env.py 的核心逻辑**（step/reset 流程、观测构建、奖励计算的数学公式）已经过多轮训练验证，不要改动算法逻辑，只做接口重构
- **agents/ 下的 SAC 实现**：作为 baseline 原样保留，不需要优化
- **ANDES 交互方式**：TDS 暂停-修改-恢复的控制循环是核心创新，不要改
- **已有训练结果**（results/ 目录）：作为 benchmark 数据保留

### 4.2 必须保持的兼容性

- ANDES ≥ 2.0（仿真后端）
- Gymnasium ≥ 0.29（接口标准）
- PyTorch ≥ 2.0（内置 agents 依赖）
- Python ≥ 3.9
- 运行环境：WSL2（ANDES 在 Windows 上需要 WSL）

### 4.3 命名规范

- 包名：`gridgym`（全小写）
- 环境 ID：`{电网名}-{N}VSG-v{版本}`，如 `Kundur-4VSG-v0`、`NE39-8VSG-v0`
- GitHub 仓库名：`gridgym`
- 文档中的正式名称：GridGym

---

## 五、学术背景参考

本项目复现并扩展的核心论文：

- **Yang et al., IEEE TPWRS 2023**："A Distributed Dynamic Inertia-Droop Control Strategy Based on Multi-Agent Deep Reinforcement Learning for Multiple Paralleled VSGs"
  - 分布式 MADRL 框架（CTDE：集中训练分散执行）
  - 每台 VSG 一个独立 SAC 智能体
  - 环形通信拓扑 + 通信故障/延迟鲁棒性
  - 奖励函数：频率同步项 + 参数正则项（权重 100:1:1）

代码中的 `config.py` 注释详细标注了每个参数在论文中的出处（Section/Table/Equation），重构时需保留这些追溯信息。

---

## 六、训练诊断系统（TrainingMonitor）

### 6.1 设计动机

当前训练过程是"黑箱跑 2000 轮"：
- 日志仅每 50 episode 打印一次奖励摘要，最后存一个 `.npz` 文件
- 没有收敛检测、没有早停、没有异常报警
- SAC 的 Q-loss/policy-loss/entropy 计算了但从未记录
- ANDES TDS 仿真失败被静默吞掉（已修复：加入 TDS 失败检测）
- 历史教训：奖励缩放 bug 导致 agent 学会"什么都不做"，跑完 2000 轮才发现

### 6.2 定位：领域级诊断，非通用 RL 监控

GridGym 的诊断系统**不替代**上层 RL 框架的监控（SB3 的 callback、WandB 的 loss 曲线），而是专注于**只有电力系统中间层才能做**的检测：

| 检测维度 | GridGym TrainingMonitor（领域级） | SB3/WandB（算法级） |
|---------|-------------------------------|-------------------|
| 奖励量级 | 检测是否匹配物理预期（如初始 ≈ -1500） | 只看趋势，不懂物理含义 |
| 奖励分量比例 | r_f 应主导（≥90%），r_h/r_d 是正则项 | 无法拆分领域奖励 |
| 动作分布 | 检测动作是否趋近零（="不控制"） | 只看 entropy，不懂动作物理含义 |
| 频率偏差 | 检测是否在合理物理范围内 | 不懂电力系统 |
| TDS 仿真健康度 | 仿真失败率、数值发散检测 | 不可见 |
| VSG 参数越界 | H/D 是否超出物理合理范围 | 不可见 |

### 6.3 核心功能

**A. 指标收集（每 episode）**

```python
monitor.log_episode(
    episode=ep,
    rewards=rewards_dict,          # 各 agent 总奖励
    reward_components={"r_f": ..., "r_h": ..., "r_d": ...},  # 奖励分量
    actions=actions_history,       # 本 episode 所有动作
    info=episode_info,             # 频率、功率、VSG 参数等
)
```

**B. 诊断检测规则（可配置 warn/stop/ignore）**

| 检测项 | 默认阈值 | 默认动作 | 说明 |
|-------|---------|---------|------|
| `reward_magnitude` | 初始奖励偏离预期 >100x | `stop` | 检测奖励缩放错误 |
| `reward_component_ratio` | r_f 占比 <50% | `warn` | r_h/r_d 不应主导奖励 |
| `action_collapse` | 动作标准差 <0.05 持续 50 ep | `warn` | agent 趋近于"不控制" |
| `action_saturation` | >80% 动作在边界 ±1.0 | `warn` | 动作空间可能过小 |
| `reward_plateau` | 100 ep 内改善 <1% | `warn` | 可能陷入局部最优 |
| `reward_divergence` | 奖励持续恶化 50 ep | `stop` | 训练发散 |
| `tds_failure_rate` | 仿真失败率 >20% | `warn` | ANDES 数值不稳定 |
| `freq_out_of_range` | 频率偏差 >±2 Hz | `warn` | 物理量超出合理范围 |

**C. 配置方式**

```python
monitor = TrainingMonitor(
    checks={
        "reward_magnitude": {"expected_range": (-2000, -500), "action": "stop"},
        "action_collapse":  {"std_threshold": 0.05, "window": 50, "action": "warn"},
        "reward_divergence": {"window": 50, "action": "stop"},
    },
    log_interval=10,          # 每 N episode 输出摘要
    check_after=20,           # 前 N episode 为热身期，不触发检测
)
```

用户可通过配置选择每个检测项的响应方式：
- `ignore`：不检测
- `warn`：终端打印醒目警告，训练继续
- `stop`：终端打印诊断报告，自动终止训练

**D. 输出格式**

正常运行时（每 `log_interval` episode）：
```
[Monitor] Episode 50 | Reward: -1423.5 (r_f: 98.2%, r_h: 0.9%, r_d: 0.9%)
          Actions μ: [0.12, -0.08, 0.23, 0.05]  σ: [0.45, 0.38, 0.51, 0.42]
          TDS fails: 4/50 (8.0%) | Freq max dev: 0.32 Hz
```

触发警告时：
```
⚠ [Monitor] WARNING: action_collapse detected!
  Agent 2 action std dropped to 0.03 (threshold: 0.05) over last 50 episodes.
  This may indicate the agent is learning a near-zero policy ("do nothing").
  Suggestion: Check reward scaling — r_h/r_d should be small relative to r_f.
```

触发停止时：
```
🛑 [Monitor] STOPPED: reward_magnitude check failed!
  Expected initial reward in range (-2000, -500), got -10,847,293.
  This is 7233x larger than expected.
  Likely cause: Reward components are using unscaled physical values.
  Diagnostic: r_f=-1423, r_h=-5,412,935, r_d=-5,433,935
              r_h+r_d is 7612x larger than r_f (expected: <10x)
  Training terminated at episode 20. No model saved.
```

### 6.4 实现约束

- **独立模块**：`gridgym/monitor.py`（或当前阶段暂放 `utils/monitor.py`），不侵入 env 或 agent 代码
- **零额外依赖**：仅用 Python 标准库 + NumPy，不强制要求 TensorBoard/WandB
- **可选后端**：未来可扩展 TensorBoard/WandB 日志后端（P2）
- **模型无关**：检测规则基于环境层指标（reward/action/state），不依赖具体 RL 算法
- **向后兼容**：训练脚本加 3-5 行代码即可接入，不改变现有训练循环结构

### 6.5 接入示例

```python
from gridgym.monitor import TrainingMonitor  # 或 from utils.monitor import ...

monitor = TrainingMonitor()  # 使用默认配置

for episode in range(N_EPISODES):
    obs = env.reset(scenario)
    ep_rewards, ep_actions = [], []

    for step in range(STEPS):
        actions = manager.select_actions(obs)
        obs, rewards, done, info = env.step(actions)
        ep_rewards.append(rewards)
        ep_actions.append(actions)

    # 一行接入
    should_stop = monitor.log_and_check(
        episode=episode,
        rewards=ep_rewards,
        actions=ep_actions,
        info=info,
    )
    if should_stop:
        break

monitor.summary()  # 训练结束时输出总结报告
```

### 6.6 已知问题清单（训练经验沉淀）

以下是在开发过程中发现的训练问题，作为诊断规则设计的参考：

| 问题 | 根因 | 症状 | 对应检测项 |
|------|------|------|-----------|
| 奖励缩放 bug | r_h/r_d 用物理值而非归一化动作 | 初始奖励 -10M（应为 -1500） | `reward_magnitude` |
| Agent 学会"不控制" | 上述 bug 导致 r_h/r_d 惩罚过大 | 动作收敛到 ≈0 | `action_collapse` |
| TDS 静默失败 | ANDES 求解器发散但未检测 | 50 步全用 stale 状态 | `tds_failure_rate` |
| TDS.busted 持久化 | 首次 TDS.run() 后 busted=True 未清除 | 后续所有 episode TDS 失败 | `tds_failure_rate` |
| PQ 负荷模式错误 | 默认 constant-impedance，Ppf 修改无效 | 扰动注入后系统无响应 | `freq_out_of_range`（无偏差） |
| REGCA1 分段 TDS 不兼容 | Toggler 事件后 solver 状态损坏 | 100% TDS 失败 | `tds_failure_rate` |
