# Training Diagnostics & Monitoring System — Design Spec

**Date:** 2026-03-30
**Status:** Draft
**Scope:** B 阶段 (wandb + 物理诊断)，预留 C 阶段 (auto-tuning) 接口

## 1. Problem Statement

### 1.1 现状

ANDES Kundur v9 训练 2000 episodes（5.4 小时），数据分析揭示：
- critic_loss 从 1.3 爆炸到 45.8（35x），从 ep 463 开始，loss_explosion 警告触发 1446 次
- 最佳 reward -18 出现在 ep 1675，但训练结束时退化到 -277（比开头 -170 还差）
- r_f（频率控制）几乎没改善：-145 → -120，是 reward 的主要瓶颈
- 每次训练 4 小时，训练完再人工分析效率极低

### 1.2 根本原因

1. **物理数据丢失**：env.step() 每步产出 freq/power/H/D/ROCOF，但 TrainingMonitor 聚合时只保留标量（max_freq_dev），完整轨迹丢弃
2. **无实时可视化**：只有 CSV/JSON，训练中看不到曲线
3. **无实验对比**：v1-v9 没法并排对比不同超参数的效果
4. **无自动诊断**：critic loss 爆炸在 ep 463 就开始了，但训练跑完 2000 ep 才发现

### 1.3 目标

- 训练中实时看到 reward 曲线、物理轨迹、agent 行为
- 自动检测训练异常（critic loss 爆炸、策略退化、频率控制停滞）
- 跨后端统一（ANDES/ODE/Simulink 共用同一套监控）
- 预留 auto-tuning 接口，B 阶段数据格式天然兼容 C 阶段

## 2. Architecture Overview

```
env.step() → raw info dict (backend-specific)
    │
    ▼
StepInfoAdapter (per-backend)
    │
    ▼
StepInfo (unified dataclass)
    │
    ▼
EpisodeBuffer
    ├── ring buffer (内存, 最近 K ep 完整轨迹)
    ├── periodic save (每 N ep → npz + wandb artifact)
    ├── alert snapshot (诊断触发 → 自动存当前 + 前 4 个 ep)
    └── EpisodeMetrics (per-ep 聚合标量)
            │
            ├──→ WandbTracker.log_episode()     标量指标
            │
            ▼
      DiagnosticsEngine
        ├── 7 rules with check_interval + window_size
        └── DiagnosticReport
                ├──→ WandbTracker.log_diagnostics()
                ├──→ EpisodeBuffer.snapshot()    告警自动快照
                └──→ [预留] TunerInterface.suggest()
```

**数据流单向**：env → StepInfo → Buffer → Diagnostics → wandb。无循环依赖。

## 3. Module 1: StepInfo 数据契约

### 3.1 数据结构

```python
from dataclasses import dataclass
import numpy as np

@dataclass
class GridState:
    freq_hz: np.ndarray           # shape (n_agents,) 各发电机频率
    freq_dev_hz: np.ndarray       # shape (n_agents,) 频率偏差
    max_freq_dev_hz: float        # 标量，本步最大频率偏差
    freq_coi_hz: float            # COI 频率 = Σ(H_i·f_i)/Σ(H_i)
    rocof: np.ndarray | None      # shape (n_agents,) dω/dt, Simulink 暂无
    power: np.ndarray             # shape (n_agents,) P_es 有功出力

@dataclass
class AgentState:
    agent_id: int
    H: float                      # 当前虚拟惯量
    D: float                      # 当前虚拟阻尼
    delta_H: float                # 本步 ΔH
    delta_D: float                # 本步 ΔD
    action_raw: np.ndarray        # shape (2,) 网络输出 [-1, 1]
    action_mapped: np.ndarray     # shape (2,) 映射后的 [ΔH, ΔD]

@dataclass
class RewardBreakdown:
    total: float                  # 所有 agent 总 reward
    per_agent: dict[int, float]   # 各 agent reward
    components: dict[str, float]  # 灵活 key: {"r_freq": ..., "r_rocof": ..., "r_action_h": ..., "r_action_d": ...}

@dataclass
class SolverState:
    converged: bool               # ANDES: not tds_failed, Simulink: sim_ok
    sim_time: float               # 仿真器内部时间
    backend: str                  # "andes" | "ode" | "simulink"
    dt_actual: float | None       # ANDES 实际步长，ODE/Simulink 可为 None

@dataclass
class StepInfo:
    step: int
    episode: int
    wall_time: float              # time.time()
    done: bool                    # episode 是否结束
    done_reason: str | None       # "complete" | "solver_fail" | "max_steps"
    grid: GridState
    agents: list[AgentState]
    reward: RewardBreakdown
    solver: SolverState
```

### 3.2 后端适配

每个后端一个 adapter 函数，在 train_loop 内调用。env 代码不需要修改。

| 后端 | 适配映射 |
|------|---------|
| ANDES | `time` → sim_time, `M_es` → H, `D_es` → D, `delta_M` → delta_H, `tds_failed` → not converged |
| ODE | `H_es` → H, `D_es` → D, `delta_H` → delta_H, converged 永远 True |
| Simulink | `sim_time` → sim_time, `M` → H, `D` → D, `sim_ok` → converged, `max_freq_dev_hz` → max_freq_dev_hz |

COI 频率在 adapter 内计算：`freq_coi = sum(H_i * freq_i) / sum(H_i)`。

### 3.3 版本控制

config 中记录 `"step_info_version": "1.0"`，回看旧实验时可识别数据结构版本。

## 4. Module 2: EpisodeBuffer

### 4.1 EpisodeMetrics

```python
@dataclass
class EpisodeMetrics:
    episode: int
    total_reward: float
    reward_components: dict[str, float]   # 各分量 episode 累计
    per_agent_rewards: dict[int, float]
    mean_freq_dev_hz: float
    max_freq_dev_hz: float
    freq_coi_std: float                   # COI 频率的 episode 内标准差
    action_mean: dict[int, np.ndarray]    # 各 agent 平均动作
    action_std: dict[int, np.ndarray]     # 各 agent 动作标准差
    h_range_used: dict[int, tuple[float, float]]  # 各 agent H 的 (min, max)
    d_range_used: dict[int, tuple[float, float]]  # 各 agent D 的 (min, max)
    solver_fail_steps: int                # 本 episode solver 失败步数
    done_reason: str
    wall_time_seconds: float              # 本 episode 墙钟耗时
    training_stats: dict[str, float] | None  # {"critic_loss": ..., "actor_loss": ..., "entropy": ...}

    def to_wandb_dict(self) -> dict[str, Any]:
        """序列化为 wandb.log() 格式，按 grid/reward/agent/train 分组。"""
        ...
```

### 4.2 EpisodeBuffer 类

```python
@dataclass
class SnapshotRecord:
    path: Path
    episode: int
    reason: str
    timestamp: float

class EpisodeBuffer:
    def __init__(self, capacity: int = 20,
                 periodic_save_interval: int = 50,
                 metrics_maxlen: int = 5000):
        self._ring: deque[list[StepInfo]] = deque(maxlen=capacity)
        self._current_episode: list[StepInfo] = []
        self._metrics_history: deque[EpisodeMetrics] = deque(maxlen=metrics_maxlen)
        self._periodic_interval = periodic_save_interval
        self._snapshots: list[SnapshotRecord] = []
        self._episode_offset: int = 0  # resume 时设置

    def add_step(self, info: StepInfo):
        self._current_episode.append(info)
        if info.done:
            self._ring.append(self._current_episode)
            metrics = self._aggregate(self._current_episode)
            self._metrics_history.append(metrics)
            self._current_episode = []

    def patch_training_stats(self, episode: int, stats: dict[str, float] | None):
        """update 完成后注入 SAC loss 等训练统计。"""
        if self._metrics_history and self._metrics_history[-1].episode == episode:
            self._metrics_history[-1].training_stats = stats

    def snapshot(self, reason: str) -> SnapshotRecord:
        """告警触发时，存当前 episode + 前 4 个 episode 的完整轨迹。"""
        ...

    def get_recent_metrics(self, n: int) -> list[EpisodeMetrics]:
        return list(self._metrics_history)[-n:]

    def get_trajectory(self, episode: int) -> list[StepInfo] | None:
        for ep_steps in self._ring:
            if ep_steps and ep_steps[0].episode == episode:
                return ep_steps
        return None

    def latest_metrics(self) -> EpisodeMetrics | None:
        return self._metrics_history[-1] if self._metrics_history else None

    def set_episode_offset(self, offset: int):
        self._episode_offset = offset
```

### 4.3 存储策略

| 层级 | 内容 | 保留量 | 触发条件 |
|------|------|--------|---------|
| 内存 ring | 完整 StepInfo 序列 | 最近 20 ep | 每 ep 自动 |
| 内存 metrics | EpisodeMetrics 标量 | 最近 5000 ep | 每 ep 自动 |
| 磁盘 npz + wandb | 完整物理轨迹 | 无限（按需） | 每 50 ep + 告警时 |

内存占用：4 agent × 50 步 × ~200B/StepInfo × 20 ep ≈ 800KB，忽略不计。

## 5. Module 3: DiagnosticsEngine

### 5.1 规则基类

```python
class Severity(Enum):
    INFO = "info"
    WARN = "warn"
    STOP = "stop"

@dataclass
class DiagnosticResult:
    rule_name: str
    severity: Severity
    message: str
    evidence: dict[str, Any]
    suggestion: str | None

class DiagnosticRule(ABC):
    name: str
    check_interval: int     # 每 N 个 episode 检查一次
    min_episodes: int        # 至少积累多少 episode 才开始
    window_size: int         # 需要多少个 episode 的历史数据
    severity: Severity       # 默认严重级别

    @abstractmethod
    def check(self, metrics: list[EpisodeMetrics]) -> DiagnosticResult | None:
        """返回 None 表示正常。"""
```

### 5.2 规则清单（7 条）

| # | 规则名 | interval | window | min_ep | 检测逻辑 | 来源 |
|---|--------|----------|--------|--------|---------|------|
| 1 | `CriticLossTrend` | 50 | 200 | 100 | training_stats.critic_loss 线性回归斜率 > 阈值 | 新增，v9 主要问题 |
| 2 | `ImprovementStall` | 100 | 200 | 200 | total_reward 和 r_freq 的 200ep 滑动均值斜率 ≤ 0 | 新增，合并 freq_stall + reward_plateau |
| 3 | `HDRangeUtilization` | 100 | 100 | 100 | 各 agent H/D 使用范围 < 总范围的 20% | 新增 |
| 4 | `InterAgentCoordination` | 100 | 50 | 100 | 最近 50ep 各 agent action_mean 序列，两两 Pearson > 0.9 全部 pair | 新增 |
| 5 | `RewardComponentDominance` | 50 | 50 | 50 | 某 component 占比 > 80% 持续 50 ep | 新增 |
| 6 | `ActionCollapse` | 50 | 50 | 50 | 任一 agent action_std < 0.05 持续 50 ep | 现有升级 |
| 7 | `SolverFailureRate` | 20 | 20 | 20 | 最近 20ep 的 solver_fail 比例 > 20% | 现有升级 |

### 5.3 DiagnosticReport

```python
@dataclass
class DiagnosticReport:
    episode: int
    timestamp: float
    results: list[DiagnosticResult]
    health_score: float               # 归一化 [0, 1]
    n_active_rules: int

    def has_alerts(self) -> bool: ...
    def worst_severity(self) -> Severity: ...
    def to_wandb_dict(self) -> dict[str, Any]:
        """唯一的序列化出口。包含 health_score + 各规则触发详情。"""
        ...
```

### 5.4 health_score 计算

```python
def _compute_health(self, results: list[DiagnosticResult],
                     n_active_rules: int) -> float:
    penalty = sum(
        0.3 if r.severity == Severity.STOP else 0.1
        for r in results
    )
    return max(0.0, 1.0 - penalty / max(n_active_rules * 0.1, 1.0))
```

归一化到 [0, 1]，不受规则数量变化影响。

### 5.5 Engine 主体

```python
class DiagnosticsEngine:
    def __init__(self, rules: list[DiagnosticRule] | None = None):
        self.rules = rules or self._default_rules()
        self._reports: list[DiagnosticReport] = []

    def on_episode_end(self, buffer: EpisodeBuffer) -> DiagnosticReport | None:
        latest = buffer.latest_metrics()
        if latest is None:
            return None

        ep = latest.episode

        # 防御性检查：training_stats 是否已注入
        if latest.training_stats is None:
            logger.warning("training_stats not patched before diagnostics run")

        active_rules = [r for r in self.rules
                        if ep >= r.min_episodes and ep % r.check_interval == 0]
        if not active_rules:
            return None

        metrics_needed = max(r.window_size for r in active_rules)
        metrics = buffer.get_recent_metrics(metrics_needed)

        results = []
        for rule in active_rules:
            result = rule.check(metrics)
            if result:
                results.append(result)

        if not results:
            return None

        report = DiagnosticReport(
            episode=ep, timestamp=time.time(),
            results=results,
            health_score=self._compute_health(results, len(active_rules)),
            n_active_rules=len(active_rules))

        if report.worst_severity() in (Severity.WARN, Severity.STOP):
            buffer.snapshot(reason=f"diag_{report.worst_severity().value}_ep{ep}")

        self._reports.append(report)
        return report

    def latest_health_score(self) -> float | None:
        return self._reports[-1].health_score if self._reports else None
```

## 6. Module 4: WandbTracker

### 6.1 类设计

```python
class WandbTracker:
    def __init__(self, project: str, scenario: str, config: dict,
                 enabled: bool = True,
                 trajectory_interval: int = 50):
        self._enabled = enabled
        self.trajectory_interval = trajectory_interval
        self._last_traj_ep = -100  # 防抖
        if enabled:
            import wandb
            self._run = wandb.init(
                project=project,
                name=f"{scenario}_{datetime.now():%m%d_%H%M}",
                config=config,
                tags=[scenario, config.get("backend", "unknown")],
            )

    def log_episode(self, metrics: EpisodeMetrics):
        """每 episode，标量指标。key 按 grid/reward/agent/train 分组。"""
        # grid/ 前缀：物理量
        # reward/ 前缀：reward 分量
        # agent_N/ 前缀：per-agent 指标
        # train/ 前缀：SAC loss 等
        # episode/ 前缀：done_reason, wall_time
        d = metrics.to_wandb_dict()
        wandb.log(d, step=metrics.episode)

    def log_diagnostics(self, report: DiagnosticReport):
        """诊断报告。序列化逻辑全部在 to_wandb_dict() 内。"""
        d = report.to_wandb_dict()
        wandb.log(d, step=report.episode)
        if report.worst_severity() == Severity.STOP:
            wandb.alert(
                title=f"Training STOP @ ep {report.episode}",
                text="\n".join(r.message for r in report.results),
                level=wandb.AlertLevel.ERROR)

    def log_trajectory(self, episode: int, steps: list[StepInfo]):
        """周期性 + 告警时，物理轨迹图。带防抖。"""
        if episode - self._last_traj_ep < 10:
            return
        self._last_traj_ep = episode
        # matplotlib 4-subplot: freq, power, H, D
        # wandb.Image(fig) 上传
        ...

    def finish(self, result: dict):
        """训练结束，写 summary 供实验对比表格使用。"""
        if self._enabled:
            for k, v in result.items():
                if v is not None:
                    wandb.summary[k] = v
            wandb.finish()
```

### 6.2 wandb key 命名规范

| 前缀 | 内容 |
|------|------|
| `grid/` | mean_freq_dev_hz, max_freq_dev_hz, freq_coi_std |
| `reward/` | total, r_freq, r_rocof, r_action_h, r_action_d (动态 key) |
| `agent_N/` | reward, action_std, H_range, D_range |
| `train/` | critic_loss, actor_loss, entropy |
| `episode/` | done_reason, wall_time_s |
| `diagnostics/` | health_score, 各规则名称 + severity |

### 6.3 离线模式

WSL 无网络时设 `WANDB_MODE=offline`，训练完 `wandb sync` 上传。`enabled=False` 时所有方法 no-op。

## 7. Module 5: TunerInterface（C 阶段预留）

### 7.1 接口定义

```python
@dataclass
class HyperparamSuggestion:
    changes: dict[str, Any]       # {"lr": 1e-4, "gradient_clip": 1.0}
    reason: str                    # "critic_loss 持续上升，建议降低 LR"
    confidence: float              # 0-1

class TunerInterface(ABC):
    @abstractmethod
    def suggest(self, report: DiagnosticReport,
                recent_metrics: list[EpisodeMetrics]) -> HyperparamSuggestion | None:
        """根据诊断结论建议超参调整。None 表示不建议调整。"""

    @abstractmethod
    def objective(self, metrics: list[EpisodeMetrics],
                  final_report: DiagnosticReport) -> float:
        """Optuna trial 的优化目标。
        示例: 0.7 * normalized_best_reward + 0.3 * mean_health_score"""

    @abstractmethod
    def should_prune(self, metrics: list[EpisodeMetrics],
                     report: DiagnosticReport | None) -> bool:
        """中途砍掉 trial。
        health_score 连续 3 次 < 0.3 → prune
        CriticLossTrend 触发 STOP → prune"""

    @abstractmethod
    def search_space(self) -> dict[str, Any]:
        """超参搜索空间，兼容 Optuna 格式。"""
```

### 7.2 B 阶段保证

B 阶段实现确保以下数据可用于 C 阶段：
- `DiagnosticReport` 包含 health_score + evidence dict → 支撑 `suggest()`
- `EpisodeMetrics` 包含 reward + freq + training_stats → 支撑 `objective()`
- `EpisodeBuffer.metrics_history` 可序列化 → 回溯分析旧 trial

## 8. Module 6: train_loop.py 集成

### 8.1 接口变更

```python
def run_training(
    # ... 现有参数全部不变 ...

    # 新增，全部可选
    wandb_tracker: WandbTracker | None = None,
    diagnostics_engine: DiagnosticsEngine | None = None,
    episode_buffer: EpisodeBuffer | None = None,
    step_info_adapter: Callable | None = None,
):
```

零破坏：不传新参数时行为完全不变。

### 8.2 集成点（伪代码）

```python
for ep in range(args.episodes):
    for step in range(steps_per_episode):
        # ... 现有逻辑 ...

        # [新增] StepInfo → Buffer
        if episode_buffer and step_info_adapter:
            step_info = step_info_adapter(
                step=step, episode=ep, raw_info=info,
                actions=actions, rewards=rewards, done=done)
            episode_buffer.add_step(step_info)

    # ... 现有 update 逻辑 ...

    # [新增] 注入 training_stats（必须在 diagnostics 之前）
    if episode_buffer:
        episode_buffer.patch_training_stats(ep, sac_losses_dict)

    # [新增] 诊断
    if diagnostics_engine and episode_buffer:
        report = diagnostics_engine.on_episode_end(episode_buffer)
        if report:
            if wandb_tracker:
                wandb_tracker.log_diagnostics(report)
            if report.worst_severity() == Severity.STOP:
                logger.error("Diagnostics STOP: %s",
                             [r.message for r in report.results])
                break

    # [新增] wandb 标量
    if wandb_tracker and episode_buffer:
        wandb_tracker.log_episode(episode_buffer.latest_metrics())

    # [新增] wandb 轨迹（周期性）
    if wandb_tracker and episode_buffer:
        if (ep + 1) % wandb_tracker.trajectory_interval == 0:
            traj = episode_buffer.get_trajectory(ep)
            if traj:
                wandb_tracker.log_trajectory(ep, traj)

# [新增] 结束
if wandb_tracker:
    wandb_tracker.finish({
        "best_reward": max(total_rewards) if total_rewards else None,
        "episodes_completed": last_ep + 1,
        "final_health_score": (
            diagnostics_engine.latest_health_score()
            if diagnostics_engine else None),
        "stop_reason": stop_reason,  # "diagnostics_stop" | "max_episodes" | "manual"
    })
```

### 8.3 调用顺序约束

```
patch_training_stats() → on_episode_end() → log_episode() → log_trajectory()
```

`patch_training_stats` 必须在 `on_episode_end` 之前，否则 CriticLossTrend 拿到 None。
`on_episode_end` 可能触发 snapshot，需要 buffer 中有完整轨迹。

## 9. File Layout

```
utils/
  diagnostics/
    __init__.py
    step_info.py          # StepInfo, GridState, AgentState, RewardBreakdown, SolverState
    adapters.py           # andes_adapter, ode_adapter, simulink_adapter
    episode_buffer.py     # EpisodeBuffer, EpisodeMetrics, SnapshotRecord
    engine.py             # DiagnosticsEngine, DiagnosticRule, DiagnosticReport, Severity
    rules/
      __init__.py
      critic_loss.py      # CriticLossTrend
      improvement.py      # ImprovementStall
      hd_range.py         # HDRangeUtilization
      coordination.py     # InterAgentCoordination
      dominance.py        # RewardComponentDominance
      action_collapse.py  # ActionCollapse
      solver_failure.py   # SolverFailureRate
    wandb_tracker.py      # WandbTracker
    tuner_interface.py    # TunerInterface, HyperparamSuggestion (ABC only)
```

## 10. Migration from TrainingMonitor

现有 `utils/monitor.py` (`TrainingMonitor`) 不删除，但标记 deprecated。迁移策略：

| 旧功能 | 新归属 |
|--------|--------|
| reward_magnitude 检测 | 移除，wandb alert 替代 |
| reward_component_ratio | → RewardComponentDominance（增强版） |
| action_collapse / saturation | → ActionCollapse |
| reward_plateau | → ImprovementStall（合并） |
| reward_divergence | → CriticLossTrend + ImprovementStall |
| tds_failure_rate | → SolverFailureRate |
| freq_out_of_range | → ImprovementStall 的 freq 分支 |
| agent_reward_disparity | → InterAgentCoordination 扩展 |
| loss_explosion | → CriticLossTrend |
| early_stopping | → ImprovementStall patience |
| CSV export | → wandb 替代 |
| best_reward_callback | → 保留在 train_loop 中 |

## 11. Dependencies

| 依赖 | 版本 | 用途 |
|------|------|------|
| wandb | >=0.16 | 实验跟踪 |
| numpy | 已有 | 数据处理 |
| matplotlib | 已有 | 轨迹图渲染 |
| scipy | 已有 | Pearson 相关（InterAgentCoordination） |

wandb 是唯一新增外部依赖。`pip install wandb`。

## 12. Success Criteria

1. ANDES Kundur 训练时，wandb dashboard 实时显示 reward/freq/H/D 曲线
2. critic_loss 爆炸在 ep 500 内自动检测并报告（v9 数据验证）
3. Simulink 训练接入零代码改动（只需在 wrapper 中初始化 3 个组件）
4. C 阶段 Optuna 接入只需实现 TunerInterface，不改 B 阶段代码
