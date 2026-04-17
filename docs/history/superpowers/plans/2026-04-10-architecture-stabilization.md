# Architecture Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把项目从"接口合约漂移、训练 run 身份不统一、双 SAC 实现"的早期可维护状态，推进到合约稳定、主线训练可追溯的成熟研究系统。

**Architecture:** P0 修复现有合约测试与实现的漂移（不新增功能，只对齐真相）；P1 建立 per-run 训练目录协议，为 sidecar/Optuna 提供基础设施；P1b 加 SAC 一致性测试防回归；P2 统一 Simulink 主线配置的重复常量。

**Tech Stack:** Python 3.10+, pytest, torch, numpy, FastMCP。测试不依赖 MATLAB（全部可在 andes_env 离线运行）。

**Run tests with:** `C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest <test_file> -v`

---

## Scope Note

这是一个 4 阶段独立任务集合。P0 是阻塞项（必须先做），P1 / P1b / P2 可并行进行。如需拆分：每个 Phase 均可作为独立子计划执行。

---

## Files Overview

| 操作 | 文件 | 说明 |
|------|------|------|
| Modify | `tests/test_simulink_bridge.py` | 修复 mock 3→2 返回值，补 `delta_deg` |
| Modify | `tests/test_mcp_server.py` | 对齐 PUBLIC_TOOLS 实际清单（30 个） |
| Modify | `tests/test_ne39_phang_probe.py` | 同步 RESULT: 字段列表 |
| Modify | `scenarios/kundur/train_simulink.py` | 把 `check_python_env()` 移出顶层 import |
| Modify | `scenarios/new_england/train_simulink.py` | 同上 |
| Create | `utils/run_protocol.py` | run_id 生成 + per-run 目录路径 + training_status 原子写 |
| Create | `tests/test_run_protocol.py` | run_protocol 单元测试 |
| Modify | `scenarios/kundur/train_simulink.py` | 集成 run_protocol |
| Modify | `scenarios/new_england/train_simulink.py` | 集成 run_protocol |
| Create | `tests/test_sac_consistency.py` | alpha clip / buffer / save 格式一致性测试 |
| Create | `scenarios/config_simulink_base.py` | Simulink 主线共享 SAC 超参基类 |
| Modify | `scenarios/kundur/config_simulink.py` | 从 base 继承，文档化差异原因 |
| Modify | `scenarios/new_england/config_simulink.py` | 从 base 继承，文档化差异原因 |

---

## Phase 0: Interface Contract Tests Green
> **前置条件：** 无。P1/P1b/P2 必须等 P0 全绿后再开始。

---

### Task 1: Fix SimulinkBridge mock — 3-return → 2-return + add `delta_deg`

**Problem:** `engine/simulink_bridge.py:190` 调用 `nargout=2`，返回 `(state, status)`。
但 `tests/test_simulink_bridge.py:62` 的 mock 还是 3 返回值 `(state, xfinal, status)`，
且 mock_state 缺少 `delta_deg` 键（bridge.py:217 会访问它）。

**Files:**
- Modify: `tests/test_simulink_bridge.py`

- [ ] **Step 1: Run test to confirm failure**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_simulink_bridge.py::TestSimulinkBridge::test_step_returns_dict_with_omega_pe_rocof -v
```

Expected: FAIL — `ValueError: too many values to unpack (expected 2)` 或 `KeyError: 'delta_deg'`

- [ ] **Step 2: Fix mock in `test_step_returns_dict_with_omega_pe_rocof`**

在 `tests/test_simulink_bridge.py` 找到 `TestSimulinkBridge.test_step_returns_dict_with_omega_pe_rocof`，做两处改动：

1. mock_state 补 `delta_deg` 键
2. 删除 `mock_xfinal`，改为 2-tuple 返回值

旧代码（lines 55-63）：
```python
mock_state = {"omega": [[1.0, 1.0, 1.0, 1.0]],
              "Pe": [[0.5, 0.5, 0.5, 0.5]],
              "rocof": [[0.0, 0.0, 0.0, 0.0]],
              "delta": [[0.0, 0.0, 0.0, 0.0]]}
mock_xfinal = MagicMock()
mock_status = {"success": True, "error": "", "elapsed_ms": 10.0}
mock_eng.vsg_step_and_read = MagicMock(
    return_value=(mock_state, mock_xfinal, mock_status)
)
```

新代码：
```python
mock_state = {"omega": [[1.0, 1.0, 1.0, 1.0]],
              "Pe": [[0.5, 0.5, 0.5, 0.5]],
              "rocof": [[0.0, 0.0, 0.0, 0.0]],
              "delta": [[0.0, 0.0, 0.0, 0.0]],
              "delta_deg": [[0.0, 0.0, 0.0, 0.0]]}
mock_status = {"success": True, "error": "", "elapsed_ms": 10.0}
mock_eng.vsg_step_and_read = MagicMock(
    return_value=(mock_state, mock_status)
)
```

- [ ] **Step 3: Apply same fix to `test_step_advances_time` and `test_step_raises_on_sim_failure`**

`test_step_advances_time` (lines 80-99): 同样的 mock_state 缺 `delta_deg`，同样是 3-tuple。
改法：同 Step 2（加 `"delta_deg": [[0.0]*4]`，去 `mock_xfinal`，改为 2-tuple）。

`test_step_raises_on_sim_failure` (lines 101-121): mock_state 缺 `delta_deg`（虽然 sim 失败会在读取前 raise，但保持一致）。
改法：加 `"delta_deg": [[0.0]*4]`，去 `mock_xfinal`，改为 2-tuple。

- [ ] **Step 4: Run all bridge tests**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_simulink_bridge.py -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_simulink_bridge.py
git commit -m "fix(tests): align SimulinkBridge mock with nargout=2 signature"
```

---

### Task 2: Align MCP PUBLIC_TOOLS contract test

**Problem:** `tests/test_mcp_server.py` 期望 29 个工具，包含已删除的 `harness_train_smoke`，
且缺少已添加的 `simulink_bridge_status` 和 `simulink_explore_block`。
实际 `engine/mcp_server.py` PUBLIC_TOOLS 有 30 个函数。

**Files:**
- Modify: `tests/test_mcp_server.py`

实际 PUBLIC_TOOLS 顺序（从 mcp_server.py:88-119 读取）：
```
harness_scenario_status, harness_model_inspect, harness_model_patch_verify,
harness_model_diagnose, harness_model_report,
harness_train_smoke_start, harness_train_smoke_poll,
simulink_load_model, simulink_create_model, simulink_close_model, simulink_loaded_models,
simulink_bridge_status,
simulink_get_block_tree, simulink_describe_block_ports, simulink_trace_port_connections,
simulink_explore_block,
simulink_query_params, simulink_set_block_params, simulink_check_params, simulink_preflight,
simulink_add_block, simulink_add_subsystem, simulink_connect_ports, simulink_delete_block,
simulink_build_chain,
simulink_compile_diagnostics, simulink_step_diagnostics, simulink_solver_audit,
simulink_patch_and_verify, simulink_run_script,
```
总计：30 个

- [ ] **Step 1: Run test to confirm failure**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_mcp_server.py::test_public_tools_list_matches_expected_contract tests/test_mcp_server.py::test_public_tools_contract_has_stable_size -v
```

Expected: FAIL on both

- [ ] **Step 2: Update expected list and count in `tests/test_mcp_server.py`**

找到 `test_public_tools_list_matches_expected_contract` 函数，把 `expected_names` 替换为：

```python
expected_names = [
    "harness_scenario_status",
    "harness_model_inspect",
    "harness_model_patch_verify",
    "harness_model_diagnose",
    "harness_model_report",
    "harness_train_smoke_start",
    "harness_train_smoke_poll",
    "simulink_load_model",
    "simulink_create_model",
    "simulink_close_model",
    "simulink_loaded_models",
    "simulink_bridge_status",
    "simulink_get_block_tree",
    "simulink_describe_block_ports",
    "simulink_trace_port_connections",
    "simulink_explore_block",
    "simulink_query_params",
    "simulink_set_block_params",
    "simulink_check_params",
    "simulink_preflight",
    "simulink_add_block",
    "simulink_add_subsystem",
    "simulink_connect_ports",
    "simulink_delete_block",
    "simulink_build_chain",
    "simulink_compile_diagnostics",
    "simulink_step_diagnostics",
    "simulink_solver_audit",
    "simulink_patch_and_verify",
    "simulink_run_script",
]
```

找到 `test_public_tools_contract_has_stable_size`，把 `assert len(...) == 29` 改为 `assert len(...) == 30`。

- [ ] **Step 3: Run to verify**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_mcp_server.py -v
```

Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_mcp_server.py
git commit -m "fix(tests): align MCP PUBLIC_TOOLS contract — 29→30, add bridge_status+explore_block, remove train_smoke"
```

---

### Task 3: Sync phAng probe RESULT field list

**Problem:** `tests/test_ne39_phang_probe.py` 期望 10 个 RESULT: 字段，
但 `.m` 脚本已演化（字段名增加了 `/phAngCmd`，新增了 `closed-loop two-step bounded`）。

**Files:**
- Modify: `tests/test_ne39_phang_probe.py`

实际 `.m` 文件 RESULT: 前缀（从 `vsg_helpers/vsg_probe_ne39_phang_sensitivity.m` grep 得到）：
```
RESULT: phAng param exists
RESULT: baseline Pe/omega/phAngCmd
RESULT: phAng step +30deg Pe/omega
RESULT: M/D low omega/delta/phAngCmd/Pe
RESULT: M/D base omega/delta/phAngCmd/Pe
RESULT: M/D high omega/delta/phAngCmd/Pe
RESULT: open-loop no-delta Pe drift
RESULT: closed-loop two-step bounded
RESULT: delta range
RESULT: warmup init phAng preserved
RESULT: classification
```
共 11 个（`classification` 出现 2 次，test 只需检查字符串存在性）

- [ ] **Step 1: Run test to confirm failures**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_ne39_phang_probe.py::test_ne39_phang_probe_script_has_stable_result_fields -v
```

Expected: FAIL — 多个字段 assertion 失败

- [ ] **Step 2: Update `expected_fields` in `tests/test_ne39_phang_probe.py`**

找到 `test_ne39_phang_probe_script_has_stable_result_fields`，把 `expected_fields` 替换为：

```python
expected_fields = [
    "RESULT: phAng param exists",
    "RESULT: baseline Pe/omega/phAngCmd",
    "RESULT: phAng step +30deg Pe/omega",
    "RESULT: M/D low omega/delta/phAngCmd/Pe",
    "RESULT: M/D base omega/delta/phAngCmd/Pe",
    "RESULT: M/D high omega/delta/phAngCmd/Pe",
    "RESULT: open-loop no-delta Pe drift",
    "RESULT: closed-loop two-step bounded",
    "RESULT: delta range",
    "RESULT: warmup init phAng preserved",
    "RESULT: classification",
]
```

- [ ] **Step 3: Run to verify**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_ne39_phang_probe.py -v
```

Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_ne39_phang_probe.py
git commit -m "fix(tests): sync phAng probe RESULT field list with evolved .m script"
```

---

### Task 4: Isolate `check_python_env()` from import time

**Problem:** 两个训练脚本在顶层（module import 时）立即调用 `check_python_env()`，
该函数在 wrong-interpreter 时调用 `sys.exit()`。这导致 `pytest --collect-only` 在标准 Python 下失败。

**Files:**
- Modify: `scenarios/kundur/train_simulink.py`
- Modify: `scenarios/new_england/train_simulink.py`

- [ ] **Step 1: Run collection to confirm problem**

```bash
python -m pytest tests/ --collect-only -q 2>&1 | head -20
```

Expected: errors about `SystemExit` or collection failure when importing train_simulink

- [ ] **Step 2: Fix `scenarios/kundur/train_simulink.py`**

旧代码（lines 25-27）：
```python
from utils.python_env_check import check_python_env
check_python_env(r"C:\Users\27443\miniconda3\envs\andes_env\python.exe")
from collections import deque
```

新代码：
```python
from collections import deque
```

然后在 `parse_args()` 函数末尾（return 之前）或在 `main()` 最顶部加：
```python
def main():
    from utils.python_env_check import check_python_env
    check_python_env(r"C:\Users\27443\miniconda3\envs\andes_env\python.exe")
    args = parse_args()
    # ... 其余 main 代码
```

如果 `main()` 不存在而是直接 `if __name__ == "__main__":` 块，把调用移到块内最开头：
```python
if __name__ == "__main__":
    from utils.python_env_check import check_python_env
    check_python_env(r"C:\Users\27443\miniconda3\envs\andes_env\python.exe")
    # ... 其余代码
```

- [ ] **Step 3: Apply same fix to `scenarios/new_england/train_simulink.py`**

同上，把 `check_python_env()` 调用和 import 从顶层移到 `if __name__ == "__main__":` 块内。

- [ ] **Step 4: Verify collection is clean**

```bash
python -m pytest tests/ --collect-only -q 2>&1 | grep -E "error|ERROR|collected" | head -10
```

Expected: `N items / 0 errors` — 不应出现 SystemExit 相关 error

- [ ] **Step 5: Verify train scripts still work as entry points (dry-run)**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe scenarios/kundur/train_simulink.py --help
```

Expected: 输出 usage/help，无 error

- [ ] **Step 6: Run full P0 test suite**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_simulink_bridge.py tests/test_mcp_server.py tests/test_ne39_phang_probe.py tests/test_python_env_check.py -v
```

Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add scenarios/kundur/train_simulink.py scenarios/new_england/train_simulink.py
git commit -m "fix: defer check_python_env() to runtime — prevent pytest collection failure"
```

---

## Phase 1a: Per-Run Training Protocol

> **前置条件：** P0 全绿。
> **目标：** 训练产物写入 `results/sim_{scenario}/runs/{run_id}/`，提供 `training_status.json` 供 sidecar/Optuna 轮询。不改 `results/harness/`（那是 fact layer，不存训练产物）。

---

### Task 5: Create `utils/run_protocol.py`

**Files:**
- Create: `utils/run_protocol.py`
- Create: `tests/test_run_protocol.py`

- [ ] **Step 1: Write failing tests first**

创建 `tests/test_run_protocol.py`：

```python
"""Tests for utils.run_protocol — per-run directory and status protocol."""
import json
import time
from pathlib import Path

import pytest


def test_generate_run_id_format():
    from utils.run_protocol import generate_run_id
    run_id = generate_run_id("kundur")
    assert run_id.startswith("kundur_")
    parts = run_id.split("_")
    assert len(parts) == 3          # kundur_YYYYMMDD_HHMMSS
    assert len(parts[1]) == 8       # date part
    assert len(parts[2]) == 6       # time part


def test_generate_run_id_is_unique():
    from utils.run_protocol import generate_run_id
    ids = [generate_run_id("kundur") for _ in range(3)]
    # All unique (sleep not needed if clock resolution is fine; if test is flaky add time.sleep(1))
    assert len(set(ids)) == len(ids)


def test_get_run_dir_path(tmp_path, monkeypatch):
    from utils import run_protocol
    monkeypatch.setattr(run_protocol, "_PROJECT_ROOT", tmp_path)
    run_dir = run_protocol.get_run_dir("kundur", "kundur_20260410_120000")
    assert run_dir == tmp_path / "results" / "sim_kundur" / "runs" / "kundur_20260410_120000"


def test_write_and_read_training_status(tmp_path):
    from utils.run_protocol import write_training_status, read_training_status
    run_dir = tmp_path / "run1"
    run_dir.mkdir()

    status = {"status": "running", "episodes_done": 5, "last_reward": -120.0}
    write_training_status(run_dir, status)

    loaded = read_training_status(run_dir)
    assert loaded["status"] == "running"
    assert loaded["episodes_done"] == 5
    assert loaded["last_reward"] == pytest.approx(-120.0)


def test_write_training_status_is_atomic(tmp_path):
    """Write should use tempfile+replace so partial writes don't corrupt."""
    from utils.run_protocol import write_training_status
    run_dir = tmp_path / "run1"
    run_dir.mkdir()

    write_training_status(run_dir, {"status": "running"})
    write_training_status(run_dir, {"status": "completed", "episodes_done": 100})

    status_file = run_dir / "training_status.json"
    data = json.loads(status_file.read_text())
    assert data["status"] == "completed"


def test_read_training_status_returns_none_if_missing(tmp_path):
    from utils.run_protocol import read_training_status
    result = read_training_status(tmp_path / "nonexistent_run")
    assert result is None


def test_ensure_run_dir_creates_directory(tmp_path, monkeypatch):
    from utils import run_protocol
    monkeypatch.setattr(run_protocol, "_PROJECT_ROOT", tmp_path)
    run_dir = run_protocol.ensure_run_dir("ne39", "ne39_20260410_120000")
    assert run_dir.exists()
    assert (run_dir.parent.name == "runs")
```

- [ ] **Step 2: Run to confirm all fail**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_run_protocol.py -v
```

Expected: ALL FAIL — `ModuleNotFoundError: No module named 'utils.run_protocol'`

- [ ] **Step 3: Implement `utils/run_protocol.py`**

创建 `utils/run_protocol.py`：

```python
"""utils/run_protocol.py — Per-run training directory and status protocol.

Defines:
  - generate_run_id(scenario)  → "kundur_20260410_120305"
  - get_run_dir(scenario, run_id) → Path to run output directory
  - ensure_run_dir(scenario, run_id) → creates and returns run_dir
  - write_training_status(run_dir, status) → atomic JSON write
  - read_training_status(run_dir) → dict | None

Output layout:
    results/sim_{scenario}/runs/{run_id}/
        training_status.json   ← atomic-written; polled by sidecar
        run_meta.json          ← written once at training start
        metrics.jsonl          ← appended per episode
        events.jsonl           ← appended per event
        verdict.json           ← written at training end
        checkpoints/           ← model files

This layout intentionally separates native training outputs from
results/harness/ (the modeling quality-gate fact layer).
See docs/decisions/2026-04-09-harness-boundary-convention.md.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def generate_run_id(scenario: str) -> str:
    """Return a unique run identifier: '{scenario}_{YYYYMMDD}_{HHMMSS}'.

    Example: 'kundur_20260410_143022'
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{scenario}_{ts}"


def get_run_dir(scenario: str, run_id: str) -> Path:
    """Return the run output directory path (does NOT create it)."""
    return _PROJECT_ROOT / "results" / f"sim_{scenario}" / "runs" / run_id


def ensure_run_dir(scenario: str, run_id: str) -> Path:
    """Create run directory (and subdirs) and return the path."""
    run_dir = get_run_dir(scenario, run_id)
    (run_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    return run_dir


def write_training_status(run_dir: Path, status: dict[str, Any]) -> None:
    """Atomically write training_status.json to run_dir.

    Uses tempfile + os.replace so readers never see a partial write.
    """
    target = run_dir / "training_status.json"
    fd, tmp_path = tempfile.mkstemp(dir=run_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(status, f)
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_training_status(run_dir: Path) -> dict[str, Any] | None:
    """Read training_status.json, returning None if file does not exist."""
    path = run_dir / "training_status.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run tests**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_run_protocol.py -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add utils/run_protocol.py tests/test_run_protocol.py
git commit -m "feat(protocol): add per-run training directory protocol (run_protocol.py)"
```

---

### Task 6: Integrate `run_protocol` into `scenarios/kundur/train_simulink.py`

**Files:**
- Modify: `scenarios/kundur/train_simulink.py`

- [ ] **Step 1: Add import at top of file (after existing imports)**

在 `scenarios/kundur/train_simulink.py` 的 imports 区域添加：
```python
from utils.run_protocol import generate_run_id, ensure_run_dir, write_training_status
```

- [ ] **Step 2: Generate run_id at training start**

在 `main()` 函数（或 `if __name__ == "__main__":` 块）中，紧接 `args = parse_args()` 之后添加：

```python
# Per-run output directory (results/sim_kundur/runs/{run_id}/)
run_id = generate_run_id("kundur")
run_dir = ensure_run_dir("kundur", run_id)
print(f"[train] run_id={run_id}, output={run_dir}")

write_training_status(run_dir, {
    "status": "running",
    "run_id": run_id,
    "scenario": "kundur",
    "mode": args.mode,
    "episodes_total": args.episodes,
    "episodes_done": 0,
    "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "last_reward": None,
    "last_max_freq_dev_hz": None,
})
```

- [ ] **Step 3: Update status each episode**

在训练循环内部，每个 episode 结束后（写 metrics.jsonl 的同一处），添加：

```python
write_training_status(run_dir, {
    "status": "running",
    "run_id": run_id,
    "scenario": "kundur",
    "mode": args.mode,
    "episodes_total": args.episodes,
    "episodes_done": ep + 1,
    "last_reward": float(ep_reward),
    "last_max_freq_dev_hz": float(max_freq_dev) if max_freq_dev is not None else None,
})
```

（`ep_reward` 和 `max_freq_dev` 是训练循环里已有的变量，名字以实际代码为准）

- [ ] **Step 4: Write final status at training end**

在训练循环结束后（`finally` 块或正常退出处）添加：

```python
write_training_status(run_dir, {
    "status": "completed",
    "run_id": run_id,
    "scenario": "kundur",
    "mode": args.mode,
    "episodes_total": args.episodes,
    "episodes_done": total_episodes_done,
    "last_reward": last_known_reward,
    "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
})
```

如有异常捕获块，在 `except` 中写 `"status": "failed"` 版本。

- [ ] **Step 5: Smoke-test import**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -c "import scenarios.kundur.train_simulink; print('import ok')"
```

Expected: `import ok`（不应 SystemExit 或 ImportError）

- [ ] **Step 6: Commit**

```bash
git add scenarios/kundur/train_simulink.py
git commit -m "feat(protocol): integrate run_protocol into kundur training — run_id + training_status"
```

---

### Task 7: Integrate `run_protocol` into `scenarios/new_england/train_simulink.py`

**Files:**
- Modify: `scenarios/new_england/train_simulink.py`

与 Task 6 完全相同，只需把 `"kundur"` 替换为 `"ne39"`。

- [ ] **Step 1: Add import**

```python
from utils.run_protocol import generate_run_id, ensure_run_dir, write_training_status
```

- [ ] **Step 2: Generate run_id and write initial status**

在 `args = parse_args()` 之后：
```python
run_id = generate_run_id("ne39")
run_dir = ensure_run_dir("ne39", run_id)
print(f"[train] run_id={run_id}, output={run_dir}")

write_training_status(run_dir, {
    "status": "running",
    "run_id": run_id,
    "scenario": "ne39",
    "mode": args.mode,
    "episodes_total": args.episodes,
    "episodes_done": 0,
    "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "last_reward": None,
    "last_max_freq_dev_hz": None,
})
```

- [ ] **Step 3: Per-episode update and final status** — same pattern as Task 6.

- [ ] **Step 4: Smoke-test import**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -c "import scenarios.new_england.train_simulink; print('import ok')"
```

- [ ] **Step 5: Commit**

```bash
git add scenarios/new_england/train_simulink.py
git commit -m "feat(protocol): integrate run_protocol into ne39 training"
```

---

## Phase 1b: SAC Consistency Tests

> **前置条件：** P0 全绿（否则 pytest 收集不稳定）。
> **目标：** 为已知 bug 回归点加防护，不重构实现（合并 SAC 留到后续）。

---

### Task 8: Add `tests/test_sac_consistency.py`

**Files:**
- Create: `tests/test_sac_consistency.py`

- [ ] **Step 1: Write the tests**

创建 `tests/test_sac_consistency.py`：

```python
"""Regression tests for known SAC consistency bugs.

These tests guard against re-introducing bugs that were fixed but had
no tests: alpha gradient clip sync, buffer size, save key set.
Both SAC implementations must pass all checks.
"""
import math
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAC_MAIN = PROJECT_ROOT / "agents" / "sac.py"
SAC_STANDALONE = PROJECT_ROOT / "env" / "simulink" / "sac_agent_standalone.py"


# ---------- Alpha gradient clip ----------

def _has_alpha_clip(path: Path) -> bool:
    """Return True if file applies clip_grad_norm_ to the alpha/log_alpha param."""
    text = path.read_text(encoding="utf-8")
    # Matches: clip_grad_norm_([self.log_alpha], ...) or similar
    return bool(re.search(r"clip_grad_norm_.*log_alpha", text))


def test_sac_main_has_alpha_clip():
    assert _has_alpha_clip(SAC_MAIN), (
        "agents/sac.py must apply clip_grad_norm_ to log_alpha. "
        "This was a known bug — see feedback_training_structural_fixes.md"
    )


def test_sac_standalone_has_alpha_clip():
    assert _has_alpha_clip(SAC_STANDALONE), (
        "env/simulink/sac_agent_standalone.py must apply clip_grad_norm_ to log_alpha. "
        "Both SAC files must be kept in sync."
    )


# ---------- Save key set ----------

def _get_save_keys(path: Path) -> set[str]:
    """Extract keys passed to torch.save({...}) in the save() method."""
    text = path.read_text(encoding="utf-8")
    # Find the dict literal inside torch.save({...}, path)
    match = re.search(r"torch\.save\(\{([^}]+)\}", text, re.DOTALL)
    if not match:
        return set()
    block = match.group(1)
    return set(re.findall(r"'(\w+)'", block))


def test_sac_main_save_has_required_keys():
    keys = _get_save_keys(SAC_MAIN)
    required = {"actor", "critic", "critic_target", "log_alpha",
                "actor_opt", "critic_opt", "alpha_opt"}
    missing = required - keys
    assert not missing, f"agents/sac.py save() missing keys: {missing}"


def test_sac_standalone_save_has_required_keys():
    keys = _get_save_keys(SAC_STANDALONE)
    required = {"actor", "critic", "log_alpha"}  # standalone minimum
    missing = required - keys
    assert not missing, f"sac_agent_standalone.py save() missing keys: {missing}"


# ---------- Buffer size not undersized ----------

def test_kundur_buffer_not_undersized():
    """Kundur config BUFFER_SIZE must be >= 10000 for 4-agent training."""
    from scenarios.kundur.config_simulink import BUFFER_SIZE
    assert BUFFER_SIZE >= 10000, (
        f"BUFFER_SIZE={BUFFER_SIZE} is too small for 4-agent Kundur training. "
        "4 agents × 25 steps/ep × 10 eps = 1000 samples/10ep; buffer should hold ≥100 episodes."
    )


def test_ne39_buffer_not_undersized():
    """NE39 config BUFFER_SIZE must be >= 50000 for 8-agent training."""
    from scenarios.new_england.config_simulink import BUFFER_SIZE
    assert BUFFER_SIZE >= 50000, (
        f"BUFFER_SIZE={BUFFER_SIZE} is too small for 8-agent NE39 training. "
        "8 agents × 50 steps/ep fills buffer ~2x faster than Kundur."
    )


# ---------- Reward formula: mean(a²) not (mean(a))² ----------

def _uses_correct_reward_formula(path: Path) -> bool:
    """Check that action penalty uses np.mean(a**2) or similar, not np.mean(a)**2."""
    text = path.read_text(encoding="utf-8")
    # Bad pattern: mean(actions)**2 or mean(action)**2
    bad = re.search(r"np\.mean\(.*action.*\)\s*\*\*\s*2", text)
    return bad is None


def test_kundur_env_reward_formula():
    env_file = PROJECT_ROOT / "env" / "simulink" / "kundur_simulink_env.py"
    assert _uses_correct_reward_formula(env_file), (
        "kundur_simulink_env.py contains (mean(action))**2 penalty — should be mean(action**2). "
        "This silently cancels symmetric actions."
    )


def test_ne39_env_reward_formula():
    env_file = PROJECT_ROOT / "env" / "simulink" / "ne39_simulink_env.py"
    if env_file.exists():
        assert _uses_correct_reward_formula(env_file), (
            "ne39_simulink_env.py contains (mean(action))**2 penalty — should be mean(action**2)."
        )
```

- [ ] **Step 2: Run to check current state**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_sac_consistency.py -v
```

Expected: most PASS (bugs were fixed); any FAIL = 真实回归，需立即修复再继续。

- [ ] **Step 3: If any FAIL — fix the underlying implementation first, then rerun**

如果 `test_sac_standalone_has_alpha_clip` 失败：在 `env/simulink/sac_agent_standalone.py` 找到 alpha 更新块，在 `alpha_optimizer.step()` 之前加：
```python
torch.nn.utils.clip_grad_norm_([self.log_alpha], self.max_grad_norm)
```

- [ ] **Step 4: All green, commit**

```bash
git add tests/test_sac_consistency.py
git commit -m "test(sac): add regression guards — alpha clip, buffer size, reward formula, save keys"
```

---

## Phase 2: Simulink Config Convergence

> **前置条件：** P0 全绿。可与 P1b 并行。
> **目标：** 消除 Kundur / NE39 配置文件的重复 SAC 超参，文档化差异原因。

---

### Task 9: Create `scenarios/config_simulink_base.py`

**Files:**
- Create: `scenarios/config_simulink_base.py`

- [ ] **Step 1: Identify shared constants**

Kundur 和 NE39 配置完全相同的 SAC/训练常量（从两个文件对比得到）：
- `LR = 3e-4`
- `GAMMA = 0.99`
- `TAU_SOFT = 0.005`
- `HIDDEN_SIZES = (128, 128, 128, 128)`
- `ADAPTIVE_KH = 0.1`，`ADAPTIVE_KD = 2.0`
- `CHECKPOINT_INTERVAL = 100`
- `EVAL_INTERVAL = 50`
- `CLEAR_BUFFER_PER_EPISODE = False`
- `DT = 0.2`，`N_SUBSTEPS = 5`，`T_WARMUP = 0.5`
- `DM_MIN, DM_MAX = -6.0, 18.0`
- `DD_MIN, DD_MAX = -1.5, 4.5`
- `DIST_MIN = 1.0`，`DIST_MAX = 3.0`
- `VSG_M0 = 12.0`，`VSG_D0 = 3.0`，`VSG_SN = 200.0`

- [ ] **Step 2: Create the base config**

创建 `scenarios/config_simulink_base.py`：

```python
"""scenarios/config_simulink_base.py — Shared Simulink SAC hyperparameters.

Scenario-specific configs (kundur/config_simulink.py, new_england/config_simulink.py)
should import * from here and override only what differs.

DO NOT add system-specific parameters here (N_AGENTS, FN, T_EPISODE, PHI_F, BATCH_SIZE).
Those belong in the scenario config with a comment explaining WHY they differ.
"""

# ========== SAC Hyperparameters (scenario-invariant) ==========
LR = 3e-4
GAMMA = 0.99
TAU_SOFT = 0.005
HIDDEN_SIZES = (128, 128, 128, 128)

# ========== Training Control ==========
CHECKPOINT_INTERVAL = 100
EVAL_INTERVAL = 50
CLEAR_BUFFER_PER_EPISODE = False

# ========== Adaptive Baseline (Fu et al. 2022) ==========
ADAPTIVE_KH = 0.1
ADAPTIVE_KD = 2.0

# ========== Simulation Timing ==========
DT = 0.2             # control step (s)
N_SUBSTEPS = 5       # parameter interpolation substeps
T_WARMUP = 0.5       # warmup before disturbance (s)

# ========== Action Space (both scenarios use same M/D range) ==========
DM_MIN, DM_MAX = -6.0, 18.0    # M range: [M0+DM_MIN, M0+DM_MAX]
DD_MIN, DD_MAX = -1.5, 4.5     # D range: [D0+DD_MIN, D0+DD_MAX]

# ========== Disturbance Magnitude ==========
DIST_MIN = 1.0    # p.u.
DIST_MAX = 3.0

# ========== VSG Base Parameters ==========
VSG_M0 = 12.0    # M = 2H (s), H0 = 6.0 s
VSG_D0 = 3.0     # p.u.
VSG_SN = 200.0   # MVA per unit

# ========== Observation Normalization ==========
NORM_P = 2.0
NORM_FREQ = 3.0
NORM_ROCOF = 5.0

# ========== Reward (PHI_H, PHI_D are scenario-invariant; PHI_F is not) ==========
PHI_H = 1.0    # inertia control cost
PHI_D = 1.0    # damping control cost
TDS_FAIL_PENALTY = -50.0
```

- [ ] **Step 3: Verify the base imports cleanly**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -c "from scenarios.config_simulink_base import *; print('LR=', LR)"
```

Expected: `LR= 0.0003`

- [ ] **Step 4: Commit base config**

```bash
git add scenarios/config_simulink_base.py
git commit -m "feat(config): add config_simulink_base.py — shared SAC hyperparams for Simulink scenarios"
```

---

### Task 10: Update `scenarios/kundur/config_simulink.py` to use base

**Files:**
- Modify: `scenarios/kundur/config_simulink.py`

- [ ] **Step 1: Write a regression test first**

在 `tests/test_sac_consistency.py` 的末尾追加：

```python
def test_kundur_config_uses_base_lr():
    from scenarios.kundur.config_simulink import LR
    from scenarios.config_simulink_base import LR as BASE_LR
    assert LR == BASE_LR, "Kundur LR diverged from base — edit config_simulink_base.py to change it"


def test_ne39_config_uses_base_lr():
    from scenarios.new_england.config_simulink import LR
    from scenarios.config_simulink_base import LR as BASE_LR
    assert LR == BASE_LR, "NE39 LR diverged from base — edit config_simulink_base.py to change it"
```

- [ ] **Step 2: Run — should PASS already (LR is the same value)**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_sac_consistency.py::test_kundur_config_uses_base_lr tests/test_sac_consistency.py::test_ne39_config_uses_base_lr -v
```

Expected: PASS (values are identical; this establishes a baseline before refactor)

- [ ] **Step 3: Add base import to `scenarios/kundur/config_simulink.py`**

在文件顶部的 `import numpy as np` 之后插入：
```python
from scenarios.config_simulink_base import (
    LR, GAMMA, TAU_SOFT, HIDDEN_SIZES,
    CHECKPOINT_INTERVAL, EVAL_INTERVAL, CLEAR_BUFFER_PER_EPISODE,
    ADAPTIVE_KH, ADAPTIVE_KD,
    DT, N_SUBSTEPS, T_WARMUP,
    DM_MIN, DM_MAX, DD_MIN, DD_MAX,
    DIST_MIN, DIST_MAX,
    VSG_M0, VSG_D0, VSG_SN,
    NORM_P, NORM_FREQ, NORM_ROCOF,
    PHI_H, PHI_D, TDS_FAIL_PENALTY,
)
```

然后删除 Kundur 文件中这些常量的重复定义。

在保留的 Kundur-specific 常量（`PHI_F`, `BATCH_SIZE`, `BUFFER_SIZE`, `WARMUP_STEPS`, `N_AGENTS`, etc.）处各加一行注释说明为什么和 NE39 不同，例如：

```python
# ========== SAC Hyperparameters (Kundur-specific overrides) ==========
# PHI_F: Kundur 4-gen system has lower frequency sensitivity than 8-gen NE39
# Paper Table I uses PHI_F=100 for this topology. NE39 uses PHI_F=200.
PHI_F = 100.0

# BATCH_SIZE: Kundur fills buffer slower (4 agents × 25 steps/ep vs NE39 8×50).
# 256 gives good sample utilization at warmup completion.
BATCH_SIZE = 256

BUFFER_SIZE = 100000
WARMUP_STEPS = 2000
```

- [ ] **Step 4: Verify Kundur config still imports cleanly**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -c "from scenarios.kundur.config_simulink import *; print('N_AGENTS=', N_AGENTS, 'LR=', LR, 'PHI_F=', PHI_F)"
```

Expected: `N_AGENTS= 4 LR= 0.0003 PHI_F= 100.0`

- [ ] **Step 5: Run full test suite to confirm no regression**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_sac_consistency.py tests/test_simulink_bridge.py -v
```

Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add scenarios/kundur/config_simulink.py tests/test_sac_consistency.py
git commit -m "refactor(config): kundur config inherits from config_simulink_base, documents PHI_F/BATCH_SIZE rationale"
```

---

### Task 11: Update `scenarios/new_england/config_simulink.py` to use base

**Files:**
- Modify: `scenarios/new_england/config_simulink.py`

- [ ] **Step 1: Add base import (same pattern as Task 10)**

在 `import numpy as np` 之后：
```python
from scenarios.config_simulink_base import (
    LR, GAMMA, TAU_SOFT, HIDDEN_SIZES,
    CHECKPOINT_INTERVAL, EVAL_INTERVAL, CLEAR_BUFFER_PER_EPISODE,
    ADAPTIVE_KH, ADAPTIVE_KD,
    DT, N_SUBSTEPS, T_WARMUP,
    DM_MIN, DM_MAX, DD_MIN, DD_MAX,
    DIST_MIN, DIST_MAX,
    VSG_M0, VSG_D0, VSG_SN,
    NORM_P, NORM_FREQ, NORM_ROCOF,
    PHI_H, PHI_D, TDS_FAIL_PENALTY,
)
```

删除重复定义。保留并注释 NE39-specific 差异：

```python
# ========== SAC Hyperparameters (NE39-specific overrides) ==========
# PHI_F: NE39 8-gen system has higher frequency coupling — 2× penalty matches
# the larger normalized frequency deviations observed in NE39 simulations.
PHI_F = 200.0

# BATCH_SIZE: 8 agents fill buffer ~2× faster; small batch (32) avoids
# overfitting to early narrow distribution before buffer is well-populated.
BATCH_SIZE = 32

BUFFER_SIZE = 100000
# WARMUP_STEPS: NE39 converges faster to meaningful gradients, 500 is sufficient.
WARMUP_STEPS = 500
```

- [ ] **Step 2: Verify NE39 config imports cleanly**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -c "from scenarios.new_england.config_simulink import *; print('N_AGENTS=', N_AGENTS, 'LR=', LR, 'PHI_F=', PHI_F)"
```

Expected: `N_AGENTS= 8 LR= 0.0003 PHI_F= 200.0`

- [ ] **Step 3: Run full regression**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_sac_consistency.py tests/test_simulink_bridge.py tests/test_mcp_server.py -v
```

Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add scenarios/new_england/config_simulink.py
git commit -m "refactor(config): ne39 config inherits from config_simulink_base, documents PHI_F/BATCH_SIZE rationale"
```

---

## Final Verification

- [ ] **Run the full non-MATLAB test suite**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/ -v --ignore=tests/test_andes_kundur_smoke.py --ignore=tests/test_matlab_session.py -x
```

Expected: 所有合约/单元/一致性测试通过。MATLAB-dependent 测试跳过是正常的。

- [ ] **Verify training scripts still import cleanly**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -c "import scenarios.kundur.train_simulink; print('kundur ok')"
C:\Users\27443\miniconda3\envs\andes_env\python.exe -c "import scenarios.new_england.train_simulink; print('ne39 ok')"
```

Expected: both `ok`

---

## Summary

| Phase | Tasks | Files changed | 预计工时 | 阻塞关系 |
|-------|-------|---------------|----------|----------|
| P0 合约测试 | 1-4 | 4 test files + 2 train scripts | 2-3h | 必须先做 |
| P1a per-run 协议 | 5-7 | run_protocol.py + 2 train scripts | 3-4h | P0 后 |
| P1b SAC 一致性 | 8 | test_sac_consistency.py | 1-2h | P0 后，可并行 P1a |
| P2 Config 统一 | 9-11 | base config + 2 scenario configs | 2-3h | P0 后，可并行 |

所有阶段完成后，接口合约稳定（测试能拦截回归）、训练产物有唯一地址（支撑 sidecar/Optuna）、双配置重复消除（实验可解释）。
