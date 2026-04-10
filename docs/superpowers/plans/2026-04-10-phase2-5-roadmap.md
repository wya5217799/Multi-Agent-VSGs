# Phase 2–5 Roadmap: Training Monitoring & Auto-Tuning

**Date:** 2026-04-10  
**Builds on:** Phase 1 Artifact Contract (`819e593`) — `metrics.jsonl`, `events.jsonl`, `latest_state.json`, `evaluate_run.py`  
**Governing constraints:**
- Simulink = 主力训练平台；不降模型真实性
- Harness ↔ Training 零耦合（只通过 filesystem + subprocess）
- 32 GB RAM（2026-04-10 升级）支持双 MATLAB 实例并行
- 不引入重量级平台（无 WandB、无 TensorBoard server）

---

## 现状（Phase 1 交付物）

| 文件 | 作用 |
|------|------|
| `utils/artifact_writer.py` | 训练时 append-mode 写 metrics/events，原子写 state |
| `utils/evaluate_run.py` | 读 metrics.jsonl + contract → PASS/MARGINAL/FAIL 判决 |
| `scenarios/contracts/*.json` | 每个场景的 quality thresholds |
| 两个训练脚本集成 | Kundur + NE39 均已集成 ArtifactWriter |

**Gap（Phase 1 未覆盖）：**
- 训练进行中无法实时看到 reward 趋势，必须等训练结束
- 多轮训练结果无横向对比
- 超参调整仍靠人工经验
- 双场景并行训练未验证

---

## Phase 2 — 实时 Sidecar 观测 + Windows 通知

**目标：** 训练时不需要盯着终端，关键事件主动推送到桌面。

### 原理

`metrics.jsonl` 每集 append 一行 → sidecar 进程 tail-poll → 触发通知。
训练脚本零改动；sidecar 是纯读方，符合 harness 边界规则。

### 文件计划

| 文件 | 作用 |
|------|------|
| `utils/sidecar.py` | Sidecar 主进程：tail metrics.jsonl + events.jsonl，计算移动统计 |
| `utils/notifier.py` | Windows toast 封装（`win10toast` 或 `plyer`，无 GUI 依赖） |
| `utils/sidecar_rules.py` | 触发规则：reward 连续下降 N 集、eval 改善、monitor_alert 出现 |

### 触发规则（初版）

| 事件 | 条件 | 通知内容 |
|------|------|----------|
| 训练开始 | `training_start` event | "场景 X 开始训练" |
| Eval 改善 | eval_reward 较上次 >5% | "EP{n}: eval {old}→{new}" |
| Reward 持续下降 | 连续 30 集 reward 斜率 < -5 | "⚠ 奖励持续下降，建议检查" |
| Monitor 报警 | `monitor_alert` event | alert 规则名 + episode |
| Checkpoint 保存 | `checkpoint` event | "EP{n} checkpoint 已保存" |
| 训练结束 | `training_end` event + verdict | "PASS/MARGINAL/FAIL + 用时 X 分钟" |

### 启动方式

```bash
# 训练开始后另开终端：
python utils/sidecar.py --log-dir results/sim_kundur/logs/standalone --contract scenarios/contracts/sim_kundur.json
```

或在训练脚本末尾自动 fork（Optional，Phase 2 后期再决定）。

### 任务分解

- [ ] Task 1: `notifier.py` — Windows toast 封装，测试弹窗
- [ ] Task 2: `sidecar.py` — tail-poll metrics.jsonl + events.jsonl，移动窗口统计
- [ ] Task 3: `sidecar_rules.py` — 触发规则引擎，5 条规则
- [ ] Task 4: 集成测试：用 3 集假数据验证全链路
- [ ] Task 5: 文档：README 使用说明

**前置条件：** 无（只依赖 Phase 1 的 metrics.jsonl）  
**预计工作量：** 中等（约 4–6 个子代理任务）

---

## Phase 3 — 多轮对比 + 启发式建议

**目标：** 跑完几轮训练后，一条命令输出"这轮比上轮好/差在哪，建议怎么改"。

### 原理

每轮训练生成的 `metrics.jsonl` + `verdict.json` 存在各自 run dir → `compare_runs.py` 横向读取 → 输出对比报告 + 规则建议。

### 文件计划

| 文件 | 作用 |
|------|------|
| `utils/compare_runs.py` | 读多个 run dir → 对比表 + 曲线图（matplotlib） |
| `utils/suggest_hparams.py` | 规则引擎：基于 verdict 字段推理超参建议 |

### 对比维度

| 维度 | 数据来源 |
|------|----------|
| Reward 曲线（移动平均） | metrics.jsonl → `reward` |
| Alpha 衰减轨迹 | metrics.jsonl → `alpha` |
| 频率偏差收敛 | metrics.jsonl → `physics.mean_freq_dev_hz` |
| Settled rate 趋势 | metrics.jsonl → `physics.settled` |
| 最终 verdict | verdict.json |
| 超参（lr, buffer_size 等） | run_meta.json |

### 启发式建议规则（初版）

| 观察 | 建议 |
|------|------|
| alpha 在前 100 集已 < 0.01 | "熵塌陷 — 降低 alpha_init 或提高 target_entropy" |
| critic_loss 在中期爆炸（>1e4） | "critic 不稳定 — 降低 lr_critic 或加 grad_clip" |
| settled_rate 持续 < 0.1 | "从未定频 — 检查 episode 时长或扰动幅度" |
| reward 震荡不收敛（OLS R² < 0.1） | "无收敛趋势 — 增大 update_repeat 或 batch_size" |
| PASS 但 eval_reward 勉强过 threshold | "建议再跑 500 集确认稳定性" |

### 任务分解

- [ ] Task 1: `compare_runs.py` — 读 N 个 run dir，生成 4-panel 对比图
- [ ] Task 2: `suggest_hparams.py` — 规则引擎，6 条规则，输出 Markdown 建议
- [ ] Task 3: CLI 集成：`python utils/compare_runs.py results/sim_kundur/logs/run{1,2,3}`
- [ ] Task 4: 测试：用合成数据验证对比图 + 建议准确性

**前置条件：** Phase 1 + 至少 2 轮完整训练数据  
**预计工作量：** 中等（约 4 个子代理任务）

---

## Phase 4 — 双场景并行训练

**目标：** Kundur + NE39 同时训练，32 GB RAM 支撑两个 MATLAB 实例，互不干扰。

### 约束分析

| 资源 | Kundur 单训练 | NE39 单训练 | 双并行估计 |
|------|--------------|------------|-----------|
| RAM | ~6–8 GB | ~10–12 GB | ~18–20 GB ✅ |
| MATLAB 实例 | 1 | 1 | 2（独立） |
| GPU | 无 | 无 | 无 |
| artifact dir | `results/sim_kundur/` | `results/sim_ne39/` | 独立 ✅ |

### 实现策略

两个独立进程，各自持有一个 MatlabSession 单例，通过不同 artifact dir 隔离结果：

```bash
# Terminal 1
python scenarios/kundur/train_simulink.py --mode standalone --episodes 500

# Terminal 2  
python scenarios/new_england/train_simulink.py --mode standalone --episodes 500

# Terminal 3（可选 — 双 sidecar）
python utils/sidecar.py --log-dir results/sim_kundur/logs/standalone &
python utils/sidecar.py --log-dir results/sim_ne39/logs/standalone &
```

### 需要验证的问题

1. 两个 `matlab.engine.start_matlab()` 实例是否互不干扰 — 需要 smoke test
2. 共享 GPU（无）/ 共享磁盘 IO（低风险）
3. `MatlabSession` 单例是否进程级隔离（应该是，Python subprocess 有独立内存空间）

### 任务分解

- [ ] Task 1: smoke test — 启动两个并行 3-集训练，验证无冲突，无 artifact 串扰
- [ ] Task 2: 内存基准测试 — 记录双实例峰值 RAM
- [ ] Task 3: 文档：双并行启动 SOP

**前置条件：** Phase 1（artifact 目录隔离已实现）  
**预计工作量：** 小（约 2 个子代理任务 + 1 次人工验证）

---

## Phase 5 — 半自动 Optuna 调参

**目标：** 给定超参搜索空间，自动运行 N 轮训练，基于 verdict 选出最优超参。

### 架构

```
Optuna Study
  └─ Trial i → 采样超参 (lr, alpha_init, update_repeat, ...)
       └─ 子进程: train_simulink.py --hparam-override {...}
            └─ 写 metrics.jsonl + verdict.json
       └─ 读 verdict.json → 返回 Optuna objective score
  └─ 最优 trial → 建议超参 + 对比报告
```

**Objective 函数：** 将 Phase 1 verdict 映射为数值分数：

| Verdict | 分数 |
|---------|------|
| PASS | eval_reward（越高越好）|
| MARGINAL | eval_reward × 0.5 的惩罚 |
| FAIL（不足数据） | -1e9（无效 trial，pruned）|
| FAIL（reward 发散） | eval_reward（保留负值信号）|

### 搜索空间（初版）

| 超参 | 范围 | 类型 |
|------|------|------|
| `LR` | [1e-4, 5e-4] | log uniform |
| `ALPHA_INIT` | [0.05, 0.5] | uniform |
| `UPDATE_REPEAT` | [2, 10] | int |
| `BATCH_SIZE` | [128, 512] | categorical |
| `REWARD_PHI_F` | [50, 300] | int（Kundur=100/NE39=200 为基准）|

### StepInfo 数据合约（接 2026-03-30 设计）

需要先实现，作为 Optuna 回调和 DiagnosticsEngine 的输入：

```python
@dataclass
class GridState:
    freq_deviation: list[float]   # per-agent Hz
    power_output: list[float]
    rocof: list[float]            # Hz/s

@dataclass
class RewardBreakdown:
    total: float
    per_agent: list[float]
    r_f: list[float]
    r_h: float
    r_d: float

@dataclass
class StepInfo:
    grid: GridState
    reward: RewardBreakdown
    H: list[float]
    D: list[float]
    actions: list[float]
    episode: int
    step: int
```

适配器在训练循环中将 `env.step()` 返回的 `info` dict 映射到 StepInfo，**不改环境代码**。

### 任务分解

- [ ] Task 1: StepInfo 数据合约实现 + Simulink 适配器（Kundur）
- [ ] Task 2: NE39 适配器
- [ ] Task 3: `train_simulink.py` 支持 `--hparam-override JSON` CLI 参数
- [ ] Task 4: `utils/optuna_study.py` — Study 主循环，objective 函数，pruning 逻辑
- [ ] Task 5: DiagnosticsEngine v1 — critic stability + entropy health 指标（可作为 Optuna early stopping 信号）
- [ ] Task 6: 集成测试：5-trial smoke study，验证 objective 函数正确读取 verdict
- [ ] Task 7: 报告：最优 trial 的超参 + 对比图（复用 Phase 3 compare_runs.py）

**前置条件：** Phase 1 + Phase 3（verdict 读取 + 对比图）  
**预计工作量：** 大（约 7–9 个子代理任务）

---

## 优先级与执行顺序

```
Phase 1 ✅  →  Phase 4（验证并行，成本低，收益高）
                  ↓
             Phase 2（sidecar 通知，减少人工盯训练）
                  ↓
             Phase 3（多轮对比 + 建议）
                  ↓
             Phase 5（Optuna 自动调参，依赖 Phase 3 基础设施）
```

**为什么先做 Phase 4：** 32 GB RAM 升级已到位，验证双并行只需 2 个任务，直接翻倍训练效率。  
**为什么 Phase 5 最后：** Optuna 依赖 verdict 质量（Phase 1）+ 建议可解释性（Phase 3）+ 稳定的并行基础设施（Phase 4）。提前做会跑在不稳定基础上。

---

## 不做的事（明确排除）

| 功能 | 排除理由 |
|------|---------|
| WandB / TensorBoard server | 重量级平台依赖，违反"轻量"原则 |
| Phasor 简化模式 | 降低模型真实性，用户明确拒绝 |
| ODE 后端优化 | ODE 是冗余中间层，精力应在 Simulink |
| 共享 Python 模块 harness↔训练 | 违反 harness 边界规则（decision 2026-04-09）|
| 自动 git push 训练结果 | 模型文件太大，手动控制 |
