# Paper Eval — Metrics 模块抽离

**Status:** EXECUTED 2026-05-03 (verified by code-reviewer)
**Date:** 2026-05-03
**Supersedes:** 部分覆盖 `2026-05-03_paper_eval_optimization.md` 的 #1 + #2 项（其余 9 项各自独立 ticket，本计划不涉及）

**Retro corrections (post-execution review)**:
- I1: 计划写"LOCK 文本搬自 paper_eval.py:1-4"。FACT 核对 (`git show HEAD:evaluation/paper_eval.py | head -10`)：HEAD 上 paper_eval.py 第 1-10 行是 `"""Phase 5.1..."""` docstring，**没有 LOCK 头**。working tree 里那 4 行 LOCK 是上一会话未 commit 的添加。本次执行实际是**新增**了 LOCK 头到 metrics.py（同时保留了 working tree 的 paper_eval.py LOCK 头）。
- M1: 计划写测试路径 `tests/evaluation/test_metrics.py`。实际放 `tests/test_metrics.py`（扁平结构与项目现有 tests/ 约定一致）。验证命令应为 `pytest tests/test_metrics.py -v`。
- I4: 计划 case #11 (ring topology) 实际只覆盖 synchronous 退化情况（all zeros）。Post-review 补 `test_r_f_local_per_agent_eta1_ring_topology_asymmetric` 锁定非退化路径。

## Goal

把 `evaluation/paper_eval.py:48-330` 的 8 个 `_compute_*` helper + 2 个 dataclass + scenario generator 抽到独立模块 `evaluation/metrics.py`，使其可单测、可被多 caller 复用。`paper_eval.py` 退化为 thin runner。

## Out-of-scope（明确不做）

- 不动 paper formula 实现（受 paper_eval.py:19-23 hard boundary）
- 不动 `KUNDUR_CVS_V3_OMEGA_SOURCES` / `KUNDUR_CVS_V3_COMM_ADJ` 两个 dict（保留 runner，避免 metrics.py Kundur-specific）
- 不解锁 `paper_comparison_enabled = False`（受 PAPER-ANCHOR LOCK）
- 不动 `result_to_dict` schema、CLI 接口、env 构造、main() 控制流
- 不做 11 项 roadmap 其余 9 项（PHI metadata / batch CLI / bootstrap CI 等独立 ticket）

## Files

| 操作 | 路径 | 行数估计 |
|---|---|---|
| 新建 | `evaluation/metrics.py` | ~250 |
| 编辑 | `evaluation/paper_eval.py` | -150 (移走) +12 (re-export) |
| 新建 | `tests/evaluation/__init__.py` | 0 |
| 新建 | `tests/evaluation/test_metrics.py` | ~180 |

## Implementation Steps（顺序执行）

### Step 1: 写 characterization 测试（在抽离前）
新建 `tests/evaluation/test_metrics.py`，**当前 import 路径** `from evaluation.paper_eval import _compute_global_rf_unnorm, ...`。11 个 case：

1. `test_global_rf_zero_when_synchronous` — 4 agent 同步 omega → r_f_global == 0
2. `test_global_rf_per_agent_sums_to_global` — sum(per_agent) == global（数值容差 1e-12）
3. `test_max_abs_df_per_agent_distinct_for_distinct_traces`
4. `test_per_agent_nadir_peak_sign_asymmetric` — +0.5/-0.5 magnitude → opposite signs
5. `test_omega_summary_sha256_distinct_for_distinct_traces`
6. `test_omega_summary_sha256_equal_for_aliased_traces`（collapse detection 反向 case）
7. `test_settling_time_returns_when_settled`
8. `test_settling_time_returns_none_when_oscillating`
9. `test_rocof_zero_for_constant_trace`
10. `test_rocof_max_for_known_step_trace`
11. `test_r_f_local_per_agent_eta1_ring_topology` — 合成 omega + ring adj → 已知值

跑 `pytest tests/evaluation/ -v`，**全 pass = 锁定当前行为**。

### Step 2: 创建 `evaluation/metrics.py`

文件头（**必须复制原文，不 import**）：
```python
# FACT: 这是合约本身（搬自 paper_eval.py:1-4）。本模块所有 helper
# 输出在 PAPER-ANCHOR LOCK 解锁前 INVALID per LOCK，不得作为 paper
# claim 引用。详见 paper_eval.py:1-4 + docs/paper/archive/yang2023-fact-base.md §10.
"""Paper §IV-C metric helpers — pure-numpy, env-free.

Extracted from paper_eval.py 2026-05-03; behavior byte-equivalent. Helpers
operate on (omega_trace, f_nom, ...) pure inputs and return float / list /
dict — no env, no torch, no MATLAB. Safe for unit testing.
"""
```

复制内容（**逐函数 cut，不改行为**）：
- `_compute_global_rf_unnorm` (paper_eval.py:165-175)
- `_compute_global_rf_per_agent` (178-198)
- `_compute_per_agent_max_abs_df` (201-213)
- `_compute_per_agent_nadir_peak` (216-231)
- `_compute_per_agent_omega_summary` (234-261)
- `_compute_r_f_local_per_agent_eta1` (264-295)
- `_rocof_max` (298-304)
- `_settling_time_s` (307-328)
- `_is_finite_arr` (331-332)
- `PerEpisodeMetrics` dataclass (84-109)
- `EvalResult` dataclass (112-124)
- `generate_scenarios` (132-157)

**留在 paper_eval.py**：
- `KUNDUR_CVS_V3_OMEGA_SOURCES` 字典（60-73）
- `KUNDUR_CVS_V3_COMM_ADJ` 字典（74-76）
- `PAPER_DDIC_UNNORMALIZED` / `PAPER_NO_CONTROL_UNNORMALIZED` 常量（48-49）
- `SETTLE_TOL_HZ` / `SETTLE_WINDOW_S`（52-53）
  - **保留位置**：runner 调 `_settling_time_s(..., tol_hz=SETTLE_TOL_HZ, window_s=SETTLE_WINDOW_S)`
  - 这两个常量是 runner-level config，不是 metric primitive

### Step 3: paper_eval.py 改为 import + re-export

替换 paper_eval.py:48-330 整段为：

```python
# Re-exports for backward compatibility — historical callers do
# `from evaluation.paper_eval import _compute_global_rf_unnorm`. Keep
# until callers migrate to evaluation.metrics directly.
from evaluation.metrics import (  # noqa: F401  (re-export)
    PerEpisodeMetrics,
    EvalResult,
    generate_scenarios,
    _compute_global_rf_unnorm,
    _compute_global_rf_per_agent,
    _compute_per_agent_max_abs_df,
    _compute_per_agent_nadir_peak,
    _compute_per_agent_omega_summary,
    _compute_r_f_local_per_agent_eta1,
    _rocof_max,
    _settling_time_s,
    _is_finite_arr,
)

# Paper baselines (kept here — runner-level, NOT generic metrics).
PAPER_DDIC_UNNORMALIZED = -8.04
PAPER_NO_CONTROL_UNNORMALIZED = -15.20

# Settling tolerance (runner-level config; passed into _settling_time_s).
SETTLE_TOL_HZ = 0.005
SETTLE_WINDOW_S = 1.0

# Kundur cvs_v3 model metadata (NOT generic metrics — stays here).
KUNDUR_CVS_V3_OMEGA_SOURCES: list[dict] = [...]  # 原内容不变
KUNDUR_CVS_V3_COMM_ADJ: dict[int, list[int]] = {...}  # 原内容不变
```

### Step 4: 跑 Step 1 的测试（验证抽离未破坏）

```bash
cd "C:\Users\27443\Desktop\Multi-Agent  VSGs"
andes_env\python.exe -m pytest tests/evaluation/ -v
```

**11/11 pass = 抽离正确**。

### Step 5: Coverage 检查

```bash
andes_env\python.exe -m pytest tests/evaluation/ --cov=evaluation.metrics --cov-report=term-missing
```

**目标**：`evaluation/metrics.py` 行覆盖 ≥ 95%（dataclass + scenario gen 的少数 edge case 可豁免）。
未达则补 case，不放过 helper 主路径。

### Step 6: Regression（端到端 byte-equal）

复用最近的 paper_eval JSON（如 `results/eval/loadstep_ptdf_round_*.json`）：
1. 记录该 run 的 CLI 命令（从文件名 + 项目惯例反推）
2. 当前 HEAD 重跑同命令 → 新 JSON
3. `diff old.json new.json` → 必须 byte-equal（schema_version 不变；helper 行为不变）

如果 byte-不等：
- 检查是否动了 helper 内部数学
- 检查 dataclass field 顺序（影响 dict 序列化顺序）
- 不放过任何 diff

### Step 7: 不改 schema_version

`schema_version=1` 保持。本次是内部重构，外部契约 0 改动。

## Verification Checklist

执行完成判定标准（每项必过）：

- [ ] `pytest tests/evaluation/ -v` → 11 pass
- [ ] `pytest --cov=evaluation.metrics` → ≥ 95% line coverage
- [ ] `python -c "from evaluation.paper_eval import _compute_global_rf_unnorm; print(ok)"` → ok（向后兼容）
- [ ] `python -c "from evaluation.metrics import _compute_global_rf_unnorm; print(ok)"` → ok（新路径）
- [ ] paper_eval.py 行数 ≈ 947 - 250 + 12 ≈ 710（误差 ±20）
- [ ] Regression: 历史 JSON 重跑 byte-equal
- [ ] `ruff check evaluation/ tests/evaluation/` clean
- [ ] grep `_compute_` in `probes/` → 记录现有 caller，不破坏其 import（向后兼容已保证）

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| Step 6 regression byte-不等 | 不合并，diff 定位、回退 metrics.py 对应函数到 byte-精确，再次运行 |
| Probes 中有 `from evaluation.paper_eval import _compute_*` | re-export 已覆盖，向后兼容；新代码鼓励用 evaluation.metrics 直接路径 |
| 漏抽某 helper 导致 paper_eval.py 内部调用断 | Step 4 测试覆盖 + Step 6 端到端规避 |
| LOCK 文本与 paper_eval.py:1-4 漂移 | 文件头标 "搬自 paper_eval.py:1-4"，发现漂移以 paper_eval.py 为准 |

## 不做的事（再次明确）

- 不抽 PHI 权重输出 metadata（独立 ticket）
- 不抽 batch CLI（独立 ticket）
- 不动 `_compute_global_rf_unnorm` 公式（hard boundary）
- 不删 `pm_step_proxy_*` / 不解 PAPER-ANCHOR LOCK
- 不创建 `evaluation/result_schema.py` / `scenario_provenance.py` / `runner.py`（dataclass + scenario gen 同住 metrics.py，不过度拆分）

## Effort

约 3h:
- Step 1 测试: 1.5h
- Step 2-3 抽离 + re-export: 30 min
- Step 4-5 验证 + coverage: 30 min
- Step 6 regression: 30 min

---

**待批准事项**: 同意执行？或需进一步调整步骤？
