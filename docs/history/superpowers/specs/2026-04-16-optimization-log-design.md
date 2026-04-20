# Optimization Log Design

> AI 的优化经验记忆层：低成本记录"为什么改、改了什么、结果怎样、能不能迁移"，
> 工程化保证 AI 在诊断时看到历史，避免无意识重复、避免忽略已有证据。

## 总原则

历史记录是决策参考，不是硬约束。目的不是禁止 AI 再碰某些参数，而是：
- 避免无意识重复（同一参数、同一假设、已验证无效）
- 避免忽略已有证据（上次 harmful 的方向需要解释为什么这次不同）
- 促进跨场景迁移（Kundur 验证有效的方向优先在 NE39 尝试）

若 reward 结构、obs 空间、agent 配置、disturbance 策略等上下文发生明显变化，
旧结论自动降级为参考，而非强反证。

## 存储

```
scenarios/contracts/optimization_log_kundur.jsonl
scenarios/contracts/optimization_log_ne39.jsonl
```

每场景一个文件，append-only JSONL。与现有 contract JSON 同目录。
文件不存在时首次写入自动创建。

## 记录类型

两种类型通过 `opt_id` 关联。1:0..1 关系（optimization 可以没有 outcome）。

### optimization（决策记录）

AI 提出的优化建议被采纳执行后，立即追加。

**必需字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | `"optimization"` | 固定值 |
| `opt_id` | string | 自动生成，格式 `opt_{kd\|ne}_{YYYYMMDD}_{seq}`（seq=当天序号，从01起），调用者不需提供 |
| `ts` | ISO 8601 | 写入时间（自动填充） |
| `scenario` | `"kundur"` \| `"ne39"` | 目标场景 |
| `scope` | `"kundur_only"` \| `"ne39_only"` \| `"transferable"` | 意图适用范围，不随结果改变 |
| `status` | `"applied"` \| `"proposed"` \| `"rejected"` | 是否执行。第一版默认 `applied` |
| `problem` | string | 观察到的问题现象，1-2 句 |
| `hypothesis` | string | 为什么认为这个改动能解决问题 |
| `changes` | `[{"param": str, "from": any, "to": any}]` | 具体参数变动 |

**可选字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `source_run` | string | 触发此决策的 run_id |
| `expected_effect` | string | 预期量化效果 |
| `tags` | string[] | 自由标签，用于检索 |

**status 使用约定：** 第一版以 `applied` 为主。`proposed` / `rejected` 保留 schema
但不鼓励大量使用，避免日志噪声。仅在"这个未执行的想法值得留档以免未来重提"时用 `proposed`。

### outcome（结果记录）

训练结束或分析阶段，追加一条与原 `opt_id` 关联的结果。

**必需字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | `"outcome"` | 固定值 |
| `opt_id` | string | 关联的 optimization |
| `ts` | ISO 8601 | 写入时间（自动填充） |
| `verdict` | `"effective"` \| `"ineffective"` \| `"inconclusive"` \| `"harmful"` | 效果判断 |
| `summary` | string | 实际效果（写法要求见下方） |

**可选字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `result_run` | string | 验证此优化的 run_id |
| `transferable` | `"likely"` \| `"unlikely"` \| `"verified"` \| `"unknown"` | 基于结果的迁移性 |
| `transfer_notes` | string | 迁移注意事项 |
| `confidence` | `"high"` \| `"medium"` \| `"low"` | 结论可靠度 |

**summary 写法要求：** 必须包含关键指标的具体变化 + 最终判断。

```
BAD:  "效果较好"  "改善有限"
GOOD: "r_h 占比从 70% 降到 35%，settled_rate 从 0.05 升到 0.18，达到预期"
GOOD: "critic_loss 未改善(仍 >500)，但 reward 斜率从 -3 转正(+1.2)，部分有效"
```

### scope 与 transferable 的分离

- `scope` 写在 optimization 上 = 写入时的**意图**（"我认为这个优化适用于..."）
- `transferable` 写在 outcome 上 = 基于结果的**判断**（"根据效果看，这个能否迁移..."）
- 两者独立，互不污染

## 示例

```jsonl
{"type":"optimization","opt_id":"opt_kd_20260416_01","ts":"2026-04-16T11:30:00+08:00","scenario":"kundur","scope":"transferable","status":"applied","problem":"r_h 占总 reward 70%+，critic 被 r_h 梯度主导","hypothesis":"降低 PHI_H 可平衡 reward 分量，释放 critic 对 r_f 的学习能力","changes":[{"param":"PHI_H","from":1.0,"to":0.3}],"source_run":"kundur_simulink_20260415_090000","tags":["reward","phi_h"]}
{"type":"outcome","opt_id":"opt_kd_20260416_01","ts":"2026-04-16T20:00:00+08:00","verdict":"effective","summary":"r_h 占比从 70% 降到 35%，settled_rate 从 0.05 升到 0.18，达到预期","result_run":"kundur_simulink_20260416_113500","transferable":"likely","transfer_notes":"NE39 的 r_h 也偏高(~60%)，同方向可试但绝对值需标定","confidence":"high"}
```

## 读写接口

模块：`engine/optimization_log.py`

### P0 函数（第一版）

```python
def load_log(scenario: str) -> list[dict]:
    """读取指定场景的全部优化记录，按时间顺序。
    文件不存在返回空列表。跳过空行和解析失败行。"""

def append_optimization(scenario: str, record: dict) -> str:
    """追加 optimization 记录。自动填充 type/ts/opt_id。
    opt_id 由函数生成（扫描当天已有序号+1），调用者不需提供。
    校验必需字段存在性、scenario 合法性。
    以 'a' 模式追加。返回生成的 opt_id。"""

def append_outcome(scenario: str, opt_id: str, verdict: str, summary: str, **kwargs) -> None:
    """追加 outcome 记录。自动填充 type/ts。
    校验 opt_id 在已有记录中存在。
    kwargs: result_run, transferable, transfer_notes, confidence。"""
```

### P1 函数（稳定后加）

```python
def query_history(scenario: str) -> list[dict]:
    """合并视图：每条 optimization 合并其 outcome（如有）。
    用于 AI 回顾完整决策卡片。"""

def find_param_overlaps(scenario: str, params: list[str]) -> list[dict]:
    """给定参数名列表，返回历史中涉及这些参数的记录（含 outcome）。
    这是"参数重叠提示"，不是"重复检测"。
    参数重叠 != 重复优化。是否重复由 AI 结合 problem 和 hypothesis 判断。"""
```

## 诊断流程接入

### training_diagnose() 注入

历史记录作为 `training_diagnose()` 返回值的一部分，工程化保证可见性。
AI 调诊断就一定看到历史，不依赖 CLAUDE.md 提示词。

```python
# engine/training_tasks.py — training_diagnose() 修改

def training_diagnose(scenario_id, run_id=None):
    from engine.optimization_log import load_log

    opt_records = load_log(scenario_id)
    # ... 现有诊断逻辑不变 ...

    return {
        # 现有字段全部保留
        "alerts": ...,
        "eval_trajectory": ...,
        "physics_diagnosis": ...,
        # 新增
        "optimization_history": _build_opt_summary(opt_records)
    }

def _build_opt_summary(records: list[dict]) -> dict:
    optimizations = [r for r in records if r.get("type") == "optimization"]
    outcomes = {r["opt_id"]: r for r in records if r.get("type") == "outcome"}

    merged = []
    for opt in optimizations:
        entry = {**opt}
        if opt["opt_id"] in outcomes:
            entry["outcome"] = outcomes[opt["opt_id"]]
        merged.append(entry)

    verdict_counts = {}
    for o in outcomes.values():
        v = o.get("verdict", "unknown")
        verdict_counts[v] = verdict_counts.get(v, 0) + 1

    return {
        "total": len(optimizations),
        "with_outcome": len(outcomes),
        "by_verdict": verdict_counts,
        "records": merged
    }
```

## AI 行为规范

核心可见性已由 training_diagnose 工程化保证。以下规则约束 AI 如何**理解和使用**历史。

### 提出新优化建议前

1. **必读当前场景历史**：通过 `training_diagnose(scenario_id)` 的 `optimization_history` 获取
2. **NE39 额外读 Kundur 迁移记录**：读取 Kundur log 中 `scope=transferable` 且 outcome verdict 为 `effective` 的记录，作为迁移参考
3. **参数重叠时**：
   - 必须说明这是"延续已有方向的微调"还是"基于新 hypothesis 的重试"
   - 不能只因参数相同就判定为重复，也不能无视历史直接重提
   - 上次 `verdict=harmful`：必须解释为什么这次条件不同、为什么值得再试
4. **上下文变化降级**：若 reward/obs/agent/disturbance 等已发生明显变化，旧结论自动降级为参考

### 写入时机

- **optimization**：建议被采纳、代码已修改后，立即追加
- **outcome**：训练结束、AI 分析结果后追加。summary 必须带具体指标变化

## 实现优先级

### P0（能写、能读、AI 一定看到）

1. `engine/optimization_log.py` — `load_log` + `append_optimization` + `append_outcome`
2. `engine/training_tasks.py` — `training_diagnose()` 注入 `optimization_history`
3. CLAUDE.md — AI 行为规范 4 条
4. `tests/test_optimization_log.py` — load/append/summary 单元测试

### P1（稳定后）

5. `query_history()` 合并视图
6. `find_param_overlaps()` 参数重叠提示
7. 跨场景迁移：NE39 诊断时自动附带 Kundur transferable 记录

### P2（有需要再做）

8. MCP 工具暴露
9. 统计聚合面板
