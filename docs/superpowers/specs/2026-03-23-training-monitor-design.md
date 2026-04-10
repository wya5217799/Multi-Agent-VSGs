# TrainingMonitor 设计文档

> GridGym 训练诊断模块：领域级健康检测，让训练问题在前 50 轮暴露而非 2000 轮后才发现。

## 1. 问题陈述

当前训练基础设施的核心缺陷：

- 日志仅每 50 episode 打印奖励摘要，训练结束存 `.npz` — 无实时诊断
- 无收敛检测、无早停、无异常报警
- 历史教训：奖励缩放 bug 导致 r_h/r_d 比 r_f 大 360 万倍，agent 学会"不控制"，跑完 2000 轮（~2h Kundur / ~24h NE）才发现
- ANDES TDS 仿真失败曾被静默吞掉（已修复，但缺少系统性监控）

## 2. 产品定位

### 2.1 GridGym 生态位中的角色

```
上层 RL 框架（SB3 / RLlib / TorchRL / 自定义）
  → 算法级监控：loss、entropy、gradient、learning rate
        ↕  PettingZoo API
    GridGym TrainingMonitor                    ← 本模块
  → 领域级监控：奖励物理合理性、动作语义、仿真健康度
        ↕
    ANDES（仿真后端）
  → 仿真级信息：收敛/发散、数值精度
```

TrainingMonitor 专注于**只有电力系统中间层才能做的诊断**：
- 上层框架不懂：奖励 -10M 是 bug 还是正常？r_f 应该占多大比例？
- 下层仿真不懂：agent 在学"不控制"还是在学"频率调节"？
- 只有 GridGym 同时理解 RL 训练循环和电力系统物理量

### 2.2 与 MATLAB RL Toolbox 的对标

MATLAB RL Toolbox 提供 `rlTrainingOptions` + Training Monitor（实时奖励曲线、`AverageReward`/`EpisodeReward` 停止条件、Custom 停止函数）。这些是**被验证过的需求**。

GridGym TrainingMonitor 在 Python 开源生态中提供对等甚至更强的能力：
- MATLAB 的停止条件是通用算法级的 → GridGym 也覆盖（reward_plateau、reward_divergence）
- MATLAB 没有的领域级检测 → GridGym 的核心差异化（奖励分量比例、动作语义、仿真健康度）

两者不在同一生态圈（MATLAB 付费闭源 vs Python 开源），不存在替代关系。

## 3. 模块架构

### 3.1 单类设计

```
TrainingMonitor
├── 数据存储层
│   ├── episode_rewards: list[float]           # 每 episode 总奖励
│   ├── reward_components: list[dict[str,float]]  # 任意命名的奖励分量
│   ├── action_stats: list[dict]               # 均值、标准差、饱和率
│   └── env_health: list[dict]                 # TDS 失败、频率偏差等
│
├── 校准引擎
│   └── _calibrate()                           # 前 N 轮自动建基线
│
├── 检测引擎（8 条规则）
│   ├── _check_reward_magnitude()
│   ├── _check_reward_component_ratio()
│   ├── _check_action_collapse()
│   ├── _check_action_saturation()
│   ├── _check_reward_plateau()
│   ├── _check_reward_divergence()
│   ├── _check_tds_failure_rate()
│   └── _check_freq_out_of_range()
│
├── 输出层
│   ├── _log_summary()                         # 定期摘要
│   ├── _emit_warning()                        # ⚠ 警告
│   └── _emit_stop()                           # 🛑 停止 + 诊断报告
│
└── 公共接口
    ├── log_and_check(episode, rewards, actions, info) → bool
    └── summary()                              # 训练结束总结
```

### 3.2 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 类结构 | 单类，无继承 | YAGNI，8 条规则不需要插件体系 |
| 检测规则 | 方法写在类中，配置控制开关 | 规则数量有限且稳定 |
| 数据存储 | list/dict + NumPy | 零额外依赖 |
| 日志后端 | 终端 print（默认） | 未来可扩展 TensorBoard/WandB（P2） |
| 奖励分量 | 任意命名 dict | 不硬编码 r_f/r_h/r_d，支持未来新分量 |

## 4. 阈值策略：路线 C（自动校准 + 手动 override）

### 4.1 三层阈值优先级

```
用户手动设置 > 场景预设 > 自动校准
```

1. **用户手动设置**：最高优先级，`TrainingMonitor(checks={...})` 中显式指定
2. **场景预设**：GridGym 内置各场景的推荐阈值（Kundur、NE 39-bus 等）
3. **自动校准**：前 `calibration_episodes` 轮收集基线，自动计算阈值

### 4.2 自动校准逻辑

在 `calibration_episodes`（默认 20）期间：
- 收集数据但**不触发任何检测**
- 校准完成后自动设置：
  - `reward_magnitude.expected_range` = `[μ - 3σ, μ + 3σ]`（基于前 20 轮奖励）
  - `tds_failure_rate.threshold` = `max(baseline_rate × 2, 0.3)`（允许波动但不允许恶化）
  - `action_collapse.std_threshold` = `baseline_std × 0.1`（标准差降到基线的 10% 视为坍缩）

### 4.3 手动 override 的必要性

自动校准有盲区：如果前 20 轮本身就有 bug（如奖励缩放错误），-10M 会被当作正常基线。此时需要用户根据领域知识手动设置 `expected_range=(-3000, -200)`。

因此 `reward_magnitude` 在没有手动设置时，降级为**相对检测**（"后续奖励相对基线恶化了 Nx"），而非绝对检测。

### 4.4 边界情况：训练提前结束

如果训练在 `calibration_episodes` 完成之前终止（手动停止或 episode 数少于校准期）：
- 所有依赖自动校准的检测项保持**禁用**状态
- 用户手动设置的检测项在 `check_after`（默认 = `calibration_episodes`）后正常生效
- `summary()` 输出会标注"校准未完成，部分检测未激活"

## 5. 检测规则详细设计

### 5.1 reward_magnitude — 奖励量级

- **输入**：前 `calibration_episodes` 的平均总奖励 or 用户设定的 `expected_range`
- **逻辑**：
  - 手动模式：`avg_reward ∉ expected_range` → 触发
  - 自动模式：后续奖励偏离基线 >100x → 触发
- **默认**：`action="stop"`
- **场景**：抓奖励缩放 bug（初始 -10M vs 预期 -1500）

### 5.2 reward_component_ratio — 分量比例

- **输入**：`reward_components` 字典（任意命名），`dominant` 指定主导分量名称
- **逻辑**：`|dominant| / sum(|all|) < dominance_threshold` → 触发
- **默认**：`dominance_threshold=0.5`，`action="warn"`
- **场景**：r_h/r_d 压过 r_f

### 5.3 action_collapse — 动作坍缩

- **输入**：最近 `window` 个 episode 的**每个 agent** 的动作标准差
- **逻辑**：**任意一个 agent** 的 `action_std < std_threshold` 持续 `window` episode → 触发（per-agent 检测，非聚合）
- **默认**：`std_threshold=0.05`（自动校准时为 `baseline_std × 0.1`），`window=50`，`action="warn"`
- **场景**：agent 学会"不控制"。Per-agent 检测确保单个 agent 坍缩不被其他 agent 的活跃动作掩盖
- **跨场景**：归一化动作 [-1,1]，与电网规模/拓扑无关

### 5.4 action_saturation — 动作饱和

- **输入**：所有动作中 `|a| > 0.95` 的比例
- **逻辑**：`saturation_ratio > threshold` → 触发
- **默认**：`threshold=0.8`，`action="warn"`
- **场景**：动作空间过小，agent 持续打满边界
- **跨场景**：归一化动作 [-1,1]，与物理动作范围无关

### 5.5 reward_plateau — 收敛停滞

- **输入**：最近 `window` 个 episode 的奖励改善率
- **逻辑**：`(max_recent - min_recent) / max(|min_recent|, 1e-8) < improvement_threshold` 持续 `window` episode → 触发。当 `|min_recent| < 1e-8` 时用绝对差 `max_recent - min_recent < 1e-6` 代替，避免除零
- **默认**：`window=100`，`improvement_threshold=0.01`，`action="warn"`
- **场景**：局部最优，100 轮零进步

### 5.6 reward_divergence — 训练发散

- **输入**：最近 `window` 个 episode 的奖励趋势
- **逻辑**：滑动窗口线性拟合斜率为负，且满足以下两个条件：(a) R² > 0.3（排除纯噪声），(b) 归一化斜率 `|slope × window / |mean_reward|| > 0.1`（窗口内总变化量超过均值的 10%）→ 触发。这避免了对微小负斜率的误报
- **默认**：`window=50`，`action="stop"`
- **场景**：Kundur 训练 ep280 后奖励从 -300K 恶化到 -1.5M

### 5.7 tds_failure_rate — 仿真失败率

- **输入**：最近 `window` 个 episode 中 TDS/ODE 仿真失败次数
- **逻辑**：`fail_count / window > threshold` → 触发
- **默认**：`threshold=0.2`（自动校准时为 `max(baseline × 2, 0.3)`），`window=50`，`action="warn"`
- **场景**：ANDES 数值不稳定、busted 未清除、模型兼容性问题
- **跨场景**：概念适用于任何时域仿真器（ANDES/PSS®E/PowerFactory）

### 5.8 freq_out_of_range — 频率越界

- **输入**：episode 中最大频率偏差（Hz）
- **逻辑**：最近 `window` 个 episode 中，超过 `min_episodes` 个 episode 的 `max_freq_deviation > threshold_hz` → 触发。单次尖峰（大扰动导致）不触发，持续越界才触发
- **默认**：`threshold_hz=2.0`，`window=10`，`min_episodes=3`，`action="warn"`
- **场景**：VSG 参数组合导致系统频率不稳定
- **跨场景**：大电网 ±2Hz 合理，微电网可能需要调整阈值

## 6. 接口设计

### 6.1 构造函数

```python
monitor = TrainingMonitor(
    # 校准
    calibration_episodes=20,       # 前 N 轮只收集不检测

    # 检测规则配置（可选，未设置的用自动校准或默认值）
    checks={
        "reward_magnitude":        {"expected_range": (-3000, -200), "action": "stop"},
        "reward_component_ratio":  {"dominant": "r_f", "dominance_threshold": 0.5, "action": "warn"},
        "action_collapse":         {"std_threshold": 0.05, "window": 50, "action": "warn"},
        "action_saturation":       {"threshold": 0.8, "action": "warn"},
        "reward_plateau":          {"window": 100, "improvement_threshold": 0.01, "action": "warn"},
        "reward_divergence":       {"window": 50, "action": "stop"},
        "tds_failure_rate":        {"threshold": 0.2, "window": 50, "action": "warn"},
        "freq_out_of_range":       {"threshold_hz": 2.0, "action": "warn"},
    },

    # 输出
    log_interval=10,               # 每 N episode 打印摘要
)
```

每个检测项的 `action` 可设为 `"warn"` / `"stop"` / `"ignore"`。

### 6.2 主入口

```python
should_stop = monitor.log_and_check(
    episode=ep,

    # 奖励：标量（所有 agent 总和）。聚合由调用方负责。
    # 所有检测规则（magnitude/plateau/divergence）均基于此标量。
    rewards: float,

    # 奖励分量：任意命名的 dict，每个值为标量（所有 agent 该分量之和）。
    # 用于 reward_component_ratio 检测。
    reward_components: dict[str, float],  # e.g. {"r_f": -1400, "r_h": -5, "r_d": -3}

    # 动作：shape (n_steps, n_agents, action_dim) 的 np.ndarray。
    # Monitor 内部计算每个 agent 的 std（沿 step 轴）用于 collapse/saturation 检测。
    # 调用方负责将 dict[int, np.ndarray] 转换为此格式。
    actions: np.ndarray,

    # 环境健康信息
    info: dict,  # 必须包含 "tds_failed": bool, "max_freq_deviation_hz": float
)
```

返回 `True` 表示检测触发了 `stop`，训练应终止。Monitor **不会**终止进程或抛异常，仅通过返回值通知调用方；调用方负责 `break`。

当多个检测同时触发时：所有触发的检测均输出日志，`stop` 优先于 `warn`（即只要有一个 `stop` 就返回 `True`）。

### 6.3 训练结束总结

```python
monitor.summary()
```

输出完整训练统计。示例输出：

```
[Monitor] ═══ Training Summary ═══
  Episodes: 2000 | Calibration: complete (20 ep)
  Reward:   -10,847,293 (ep 1) → -1,523 (ep 2000)
  Best:     -842 @ ep 1847 | Worst: -10,847,293 @ ep 1

  Checks triggered:
    reward_magnitude    🛑 STOP  @ ep 20   (1 time)
    action_collapse     ⚠ WARN  @ ep 350  (3 times, agents: [2])
    reward_divergence   ⚠ WARN  @ ep 1200 (1 time)

  TDS failures: 165/2000 (8.3%)
  Freq peak deviation: 1.87 Hz (ep 42)
```

### 6.4 训练脚本接入示例

现有训练脚本需要改动两处：(A) 环境的 `step()` / `_compute_rewards()` 需要在 `info` 中返回奖励分量；(B) 训练脚本加 ~8 行接入代码。

**A. 环境侧改动**（在 `base_env.step()` 或 `_compute_rewards()` 中）：

```python
# info dict 中需包含以下字段（当前部分已有，部分需补充）：
info = {
    "r_f": r_f,                          # 频率同步奖励分量（已有）
    "r_h": r_h,                          # 惯性惩罚分量（已有）
    "r_d": r_d,                          # 阻尼惩罚分量（已有）
    "tds_failed": tds_failed,            # 仿真是否失败（已有）
    "max_freq_deviation_hz": max_dev,    # 最大频率偏差 Hz（需补充）
}
```

**B. 训练脚本侧**：

```python
import numpy as np
from utils.monitor import TrainingMonitor                    # +1

monitor = TrainingMonitor()                                  # +2

for episode in range(N_EPISODES):
    obs = env.reset(scenario)
    ep_total_reward = 0.0
    ep_actions_list = []                                     # +3: 收集动作
    tds_failed = False
    last_info = {}

    for step in range(STEPS):
        actions = manager.select_actions(obs)
        obs, rewards, done, info = env.step(actions)
        ep_total_reward += sum(rewards.values())
        # 收集动作：将 dict[int, ndarray] 转为 (n_agents, action_dim)
        ep_actions_list.append(                              # +4
            np.array([actions[i] for i in range(env.n_agents)])
        )
        last_info = info
        if done:
            tds_failed = info.get("tds_failed", False)
            break

    should_stop = monitor.log_and_check(                     # +5,6,7
        episode=episode,
        rewards=ep_total_reward,
        reward_components={"r_f": last_info["r_f"],
                           "r_h": last_info["r_h"],
                           "r_d": last_info["r_d"]},
        actions=np.array(ep_actions_list),  # shape: (steps, agents, action_dim)
        info={"tds_failed": tds_failed,
              "max_freq_deviation_hz": last_info.get("max_freq_deviation_hz", 0)},
    )
    if should_stop:                                          # +8
        break

monitor.summary()
```

## 7. 输出格式

### 7.1 定期摘要（每 log_interval episode）

```
[Monitor] Ep 50 | Reward: -1423.5 (r_f: 98.2%, r_h: 0.9%, r_d: 0.9%)
          Actions μ: [0.12, -0.08, 0.23, 0.05]  σ: [0.45, 0.38, 0.51, 0.42]
          TDS fails: 4/50 (8.0%) | Freq peak: 0.32 Hz
```

### 7.2 校准完成

```
[Monitor] Calibration complete (20 episodes).
          Reward baseline: μ=-1487.3, σ=234.5 → magnitude range: [-2190, -784]
          Action std baseline: 0.48 → collapse threshold: 0.048
          TDS failure baseline: 8.0% → alert threshold: 16.0%
```

### 7.3 警告

```
⚠ [Monitor] action_collapse @ Ep 350
  Agent 2 action std = 0.03 (threshold: 0.048) over last 50 episodes.
  Interpretation: Agent may be learning a near-zero policy ("do nothing").
  Suggestion: Check reward scaling — ensure frequency reward (r_f) dominates.
```

### 7.4 停止 + 诊断报告

```
🛑 [Monitor] TRAINING STOPPED: reward_magnitude @ Ep 20
  Observed: avg reward = -10,847,293
  Expected: range (-3000, -200) [user-specified]
  Deviation: 7233x larger than expected upper bound

  Diagnostic breakdown:
    r_f  = -1,423      (0.01%)
    r_h  = -5,412,935  (49.9%)
    r_d  = -5,433,935  (50.1%)
  → r_h + r_d dominates reward (99.99%). Expected: r_f > 50%.

  Likely cause: Reward components using unscaled physical values instead of
  normalized actions [-1,1]. See: feedback_reward_scale.md

  Training terminated. No model saved.
```

## 8. 约束与边界

### 8.1 实现约束

- **独立模块**：当前阶段放 `utils/monitor.py`，未来 GridGym 重构时移至 `gridgym/monitor.py`
- **零额外依赖**：仅 Python 标准库 + NumPy
- **非侵入式**：不修改 env、agent、训练循环结构，训练脚本加 3-5 行接入
- **模型无关**：检测基于环境层指标（reward/action/state），不依赖 SAC/PPO/TD3 等具体算法
- **仿真器无关**：检测逻辑不绑定 ANDES API，`tds_failed` 和 `max_freq_deviation_hz` 通过 info dict 传入

### 8.2 不做的事

- 不记录/分析算法内部指标（loss、entropy、gradient）→ 留给上层框架
- 不做实验管理（run 命名、超参数对比、checkpoint resume）→ 未来 P2 或用 WandB
- 不做可视化 UI → 终端输出为主，TensorBoard/WandB 后端为 P2
- 不做自定义检测规则插件系统 → 8 条规则足够，未来需要再抽象

### 8.3 未来扩展点（不在本次实现范围）

- TensorBoard `SummaryWriter` 后端：每个指标写入 TB event 文件
- WandB `wandb.log()` 后端：实时云端看板
- 场景预设库：`TrainingMonitor.from_scenario("kundur-4vsg")` 加载推荐阈值
- 跨 run 对比：读取历史 monitor 日志，对比不同超参数的训练质量

## 9. 已知问题清单（检测规则设计依据）

| 历史问题 | 根因 | 症状 | 对应检测项 |
|---------|------|------|-----------|
| 奖励缩放 bug | r_h/r_d 用物理值而非归一化动作 | 初始奖励 -10M（应为 -1500） | reward_magnitude + reward_component_ratio |
| Agent 学会"不控制" | 上述 bug 导致 r_h/r_d 惩罚过大 | 动作收敛到 ≈0 | action_collapse |
| TDS 静默失败 | ANDES 求解器发散但未检测 | 50 步全用 stale 状态 | tds_failure_rate |
| TDS.busted 持久化 | 首次 TDS.run() 后 busted=True 未清除 | 后续所有 episode 失败 | tds_failure_rate |
| PQ 负荷模式错误 | 默认 constant-impedance，Ppf 修改无效 | 扰动注入后系统无响应 | freq_out_of_range（无偏差） |
| REGCA1 分段 TDS 不兼容 | Toggler 事件后 solver 状态损坏 | 100% TDS 失败 | tds_failure_rate |
| 训练后期恶化 | Kundur ep280 后奖励从 -300K 退化到 -1.5M | 奖励曲线先升后降 | reward_divergence |
