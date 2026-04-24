# Pattern: Training Smoke & Debug（训练启动 + 烟雾测试排查）

> **Repository overlay** — This file belongs to the Yang/VSG project. It must
> not be placed in the shared installed `simulink-toolbox` skill.

## 适用场景

RL 训练启动前验证、训练失败后溯源、异步 smoke 监控、训练完成后质量评估。
Simulink 建模问题请转 `debug-existing-model.md`；本 pattern 聚焦"能不能跑起来"和"跑完好不好"。

---

## 场景 A：训练前冒烟验证（快速路径）

目标：最短时间确认 Simulink 环境可工作，再启动完整训练。

```
1. harness_scenario_status          确认场景配置与模型文件完整
2. harness_train_smoke_minimal      单步同步 smoke 测试（最快）
3. 结果判断 → 通过则启动完整训练
             → 失败则进入场景 B
```

### 步骤详解

**Step 1 — harness_scenario_status**

```json
{ "scenario_id": "kundur" }   // 或 "ne39"
```

关注字段：
- `model_exists` — `false` 说明 .slx 文件缺失，先修模型
- `config_valid` — `false` 说明配置项缺失或格式错误
- `bridge_ready` — `false` 说明 MATLAB Engine 未就绪，需先启动

若以上三项均为 `true`，继续 Step 2。

**Step 2 — harness_train_smoke_minimal**

```json
{ "scenario_id": "kundur" }
```

关注字段：
- `passed` — `true` 表示单步仿真成功
- `error` — 失败时包含原始错误信息
- `obs_shape` / `reward` — 核对观测维度和奖励值是否合理（非 NaN/Inf）

**Step 3 — 结果判断**

| passed | 下一步 |
|--------|--------|
| `true` | 启动完整训练 |
| `false`，error 含 "model" | 进入场景 B，先跑 harness_model_diagnose |
| `false`，error 含 "MATLAB" / "engine" | 检查 MATLAB Engine，重启后重试 |
| `false`，obs 含 NaN/Inf | 查配置 IC 文件，参考 `scenarios/<topo>/kundur_ic.json` |

---

## 场景 B：训练启动失败排查

目标：完整训练启动后失败，系统定位根因并修复。

```
1. training_status                  查询当前训练状态与错误摘要
2. training_diagnose                深入诊断失败原因
3. （如有模型问题）harness_model_diagnose   定位 Simulink 模型缺陷
4.              harness_model_patch_verify  应用修复并验证
5. harness_train_smoke_minimal      修复后重新验证
6. 重启训练
```

### 步骤详解

**Step 1 — training_status**

```json
{ "scenario_id": "kundur" }
```

关注字段：
- `status` — `"running"` / `"failed"` / `"idle"`
- `last_error` — 上一次错误的摘要
- `pid` — 若非空说明进程仍存活，需先 kill 再重试

**Step 2 — training_diagnose**

```json
{ "scenario_id": "kundur" }
```

关注字段：
- `root_cause` — 根因分类（`"model_error"` / `"config_error"` / `"engine_error"` / `"rl_error"`）
- `suggested_action` — 工具建议的下一步操作
- `traceback` — Python 端完整调用栈（定位 Python 侧问题）

**Step 3 — harness_model_diagnose**（仅当 root_cause 含 "model"）

```json
{ "scenario_id": "kundur" }
```

关注字段：
- `issues` — 问题列表，每项含 `severity`（`critical` / `warning`）和 `description`
- `fix_candidates` — 可由 patch_verify 自动修复的问题列表

**Step 4 — harness_model_patch_verify**

```json
{
  "scenario_id": "kundur",
  "fix_ids": ["<fix_id_from_diagnose>"]
}
```

关注字段：
- `applied` — 实际应用的修复列表
- `verify_passed` — `true` 表示修复后编译通过
- `remaining_issues` — 未能自动修复的问题（需手动处理）

**Step 5 — 回到场景 A Step 2**，重新跑 smoke_minimal 确认。

---

## 场景 C：Smoke 测试异步流程

目标：复杂场景需要完整异步 smoke（多步仿真），不阻塞主线程。

```
1. harness_scenario_status          前置检查（同场景 A Step 1）
2. harness_train_smoke_start        启动异步 smoke 任务
3. harness_train_smoke_poll         轮询直到完成
4. 结果判断
```

### 步骤详解

**Step 2 — harness_train_smoke_start**

```json
{ "scenario_id": "ne39" }
```

关注字段：
- `task_id` — 后续 poll 使用，必须记录
- `status` — 应为 `"started"`；若为 `"error"` 则不必 poll，直接看 `error` 字段

**Step 3 — harness_train_smoke_poll（循环）**

```json
{ "task_id": "<task_id_from_start>" }
```

关注字段：
- `status` — `"running"` 继续 poll；`"done"` 退出循环；`"failed"` 退出并排查
- `progress` — 当前已完成步数 / 总步数（用于判断是否卡住）
- `elapsed_s` — 超过预期时间（如 120s）仍 `"running"` 可能卡死

**轮询策略**：

| 场景 | 建议间隔 |
|------|---------|
| Kundur（小模型） | 10–15s |
| NE39（大模型，cold start 后） | 20–30s |
| 超时阈值 | 300s（Kundur）/ 600s（NE39） |

**Step 4 — 结果判断**

| status | passed | 下一步 |
|--------|--------|--------|
| `"done"` | `true` | 可启动完整训练 |
| `"done"` | `false` | 进入场景 B |
| `"failed"` | — | 查 `error` 字段，进入场景 B |
| 超时仍 `"running"` | — | 检查 MATLAB Engine 是否卡死，重启后重试 |

---

## 场景 D：训练质量评估

目标：训练完成后评估收敛效果，决策是否需要重训或调参。

```
1. training_status                  确认训练已完成
2. training_evaluate_run            评估指定 run 的质量指标
3. （可选）training_compare_runs    横向对比多个 run
```

### 步骤详解

**Step 1 — training_status**

```json
{ "scenario_id": "kundur" }
```

确认 `status` 为 `"done"` 或 `"completed"`，记录 `run_id`。

**Step 2 — training_evaluate_run**

```json
{
  "scenario_id": "kundur",
  "run_id": "<run_id>"
}
```

关注字段：
- `converged` — 布尔值，是否判定收敛
- `mean_reward_last_10pct` — 最后 10% episode 的平均奖励（核心指标）
- `freq_nadir_improvement` — 频率最低点改善幅度（物理意义最强）
- `issues` — 训练过程中的异常（如奖励发散、动作饱和）

**Step 3 — training_compare_runs（可选）**

```json
{
  "scenario_id": "kundur",
  "run_ids": ["<run_a>", "<run_b>"]
}
```

关注字段：
- `winner` — 综合评分更优的 run_id
- `metric_table` — 各指标对比表格

---

## 常见坑

### Cold Start 延迟

MATLAB Engine 首次启动需要 30–90s（R2025b 典型值）。
smoke_minimal / smoke_start 第一次调用可能超时，**不要立即判定失败**。
建议：首次调用前先用 `harness_scenario_status` 的 `bridge_ready` 字段确认引擎已就绪。

### scenario_id 合法值只有两个

```
"kundur"   ✓
"ne39"     ✓

"kundur_simulink"     ✗  （注册表不认）
"new_england"         ✗
"ne_39"               ✗
```

传错 scenario_id 会返回 `"scenario not found"` 错误，不会 fallback。

### smoke_minimal ≠ 完整 smoke

`harness_train_smoke_minimal` 只跑 **1 步**仿真，验证环境可初始化、动作/观测接口正常。
它不能发现以下问题：
- 多步后状态发散（积分不稳定）
- episode reset 逻辑错误
- 长时间仿真的内存泄漏

需要验证上述问题时，使用场景 C 的异步 smoke（多步）。

### 不要并发多个 smoke 任务

同一 scenario_id 同时跑多个 smoke_start 会共享 MATLAB Engine 状态，导致结果不可信。
确认上一个 task_id 的 status 为 `"done"` 或 `"failed"` 后再启动新任务。

### NE39 cold start 特别慢

NE39 模型（39 节点）首次加载约需 60–120s。
首次 smoke 超时不代表模型有问题，等引擎加载完成后重试。
参见 `scenarios/new_england/NOTES.md` 中的 cold-start 记录。

---

## 快速决策树

```
想跑训练?
├── 先跑 harness_scenario_status
│   ├── config/model 不完整 → 修配置/模型
│   └── 全部 OK
│       └── harness_train_smoke_minimal
│           ├── passed=true → 启动完整训练 ✓
│           └── passed=false
│               ├── model error → harness_model_diagnose → patch_verify → 重试
│               ├── engine error → 重启 MATLAB Engine → 重试
│               └── NaN/Inf → 检查 IC 文件 / 配置参数
```
