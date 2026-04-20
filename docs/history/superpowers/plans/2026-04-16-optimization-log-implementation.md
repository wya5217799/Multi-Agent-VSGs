# Optimization Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the P0 optimization memory layer — append-only JSONL log + training_diagnose injection + CLAUDE.md behavior rules.

**Architecture:** `engine/optimization_log.py` owns all read/write logic against `scenarios/contracts/optimization_log_{scenario}.jsonl`. `training_diagnose()` in `engine/training_tasks.py` calls `load_log()` and attaches a summary dict under `optimization_history`. CLAUDE.md gets 4 behavioral rules so the AI uses the log correctly.

**Tech Stack:** Python stdlib only (`json`, `pathlib`, `datetime`). pytest for tests.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `engine/optimization_log.py` | load_log / append_optimization / append_outcome / _build_opt_summary |
| Create | `tests/test_optimization_log.py` | Unit tests for all three public functions + summary builder |
| Modify | `engine/training_tasks.py` | Add `optimization_history` field to `training_diagnose()` return |
| Modify | `tests/test_training_tasks.py` | Test that `optimization_history` key is present in diagnose result |
| Modify | `CLAUDE.md` | Add 4-rule AI behavior section for optimization log |

---

## Task 1: `engine/optimization_log.py` — write failing tests

**Files:**
- Create: `tests/test_optimization_log.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_optimization_log.py
"""Tests for engine.optimization_log — append-only optimization memory layer."""
import json
from pathlib import Path

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _contracts_dir(tmp_path: Path) -> Path:
    d = tmp_path / "contracts"
    d.mkdir()
    return d


def _write_log(contracts_dir: Path, scenario: str, lines: list[dict]) -> Path:
    p = contracts_dir / f"optimization_log_{scenario}.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in lines), encoding="utf-8")
    return p


# ── load_log ──────────────────────────────────────────────────────────────────

def test_load_log_missing_file_returns_empty(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", _contracts_dir(tmp_path))
    from engine.optimization_log import load_log
    assert load_log("kundur") == []


def test_load_log_returns_records_in_order(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    cd = _contracts_dir(tmp_path)
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", cd)
    records = [
        {"type": "optimization", "opt_id": "opt_kd_20260416_01", "ts": "2026-04-16T10:00:00+08:00",
         "scenario": "kundur", "scope": "transferable", "status": "applied",
         "problem": "r_h too high", "hypothesis": "lower PHI_H", "changes": []},
        {"type": "outcome", "opt_id": "opt_kd_20260416_01", "ts": "2026-04-16T20:00:00+08:00",
         "verdict": "effective", "summary": "settled_rate 0.05→0.18"},
    ]
    _write_log(cd, "kundur", records)
    from engine.optimization_log import load_log
    result = load_log("kundur")
    assert len(result) == 2
    assert result[0]["type"] == "optimization"
    assert result[1]["type"] == "outcome"


def test_load_log_skips_empty_lines_and_malformed(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    cd = _contracts_dir(tmp_path)
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", cd)
    path = cd / "optimization_log_kundur.jsonl"
    path.write_text(
        '{"type":"optimization","opt_id":"opt_kd_20260416_01"}\n\n{broken\n',
        encoding="utf-8",
    )
    from engine.optimization_log import load_log
    result = load_log("kundur")
    assert len(result) == 1
    assert result[0]["opt_id"] == "opt_kd_20260416_01"


# ── append_optimization ───────────────────────────────────────────────────────

def test_append_optimization_returns_opt_id(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", _contracts_dir(tmp_path))
    from engine.optimization_log import append_optimization
    opt_id = append_optimization("kundur", {
        "scenario": "kundur",
        "scope": "transferable",
        "status": "applied",
        "problem": "r_h dominates",
        "hypothesis": "lower PHI_H balances reward",
        "changes": [{"param": "PHI_H", "from": 1.0, "to": 0.3}],
    })
    assert opt_id.startswith("opt_kd_")
    assert len(opt_id.split("_")) == 4  # opt_kd_YYYYMMDD_NN


def test_append_optimization_auto_fills_type_ts(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    cd = _contracts_dir(tmp_path)
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", cd)
    from engine.optimization_log import append_optimization, load_log
    append_optimization("kundur", {
        "scenario": "kundur",
        "scope": "kundur_only",
        "status": "applied",
        "problem": "p",
        "hypothesis": "h",
        "changes": [],
    })
    rows = load_log("kundur")
    assert rows[0]["type"] == "optimization"
    assert "ts" in rows[0]
    assert rows[0]["ts"]  # non-empty


def test_append_optimization_seq_increments_per_day(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    cd = _contracts_dir(tmp_path)
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", cd)
    from engine.optimization_log import append_optimization
    base = {"scenario": "kundur", "scope": "transferable", "status": "applied",
            "problem": "p", "hypothesis": "h", "changes": []}
    id1 = append_optimization("kundur", base.copy())
    id2 = append_optimization("kundur", base.copy())
    seq1 = id1.split("_")[-1]
    seq2 = id2.split("_")[-1]
    assert int(seq2) == int(seq1) + 1


def test_append_optimization_ne39_prefix(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", _contracts_dir(tmp_path))
    from engine.optimization_log import append_optimization
    opt_id = append_optimization("ne39", {
        "scenario": "ne39",
        "scope": "ne39_only",
        "status": "applied",
        "problem": "p",
        "hypothesis": "h",
        "changes": [],
    })
    assert opt_id.startswith("opt_ne_")


def test_append_optimization_missing_required_field_raises(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", _contracts_dir(tmp_path))
    from engine.optimization_log import append_optimization
    with pytest.raises(ValueError, match="Missing required"):
        append_optimization("kundur", {
            "scenario": "kundur",
            # missing scope, status, problem, hypothesis, changes
        })


def test_append_optimization_invalid_scenario_raises(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", _contracts_dir(tmp_path))
    from engine.optimization_log import append_optimization
    with pytest.raises(ValueError, match="scenario"):
        append_optimization("bad_scenario", {
            "scenario": "bad_scenario",
            "scope": "transferable",
            "status": "applied",
            "problem": "p",
            "hypothesis": "h",
            "changes": [],
        })


# ── append_outcome ────────────────────────────────────────────────────────────

def _seed_one_optimization(cd: Path, scenario: str, opt_id: str) -> None:
    """Write a minimal optimization record so append_outcome can validate opt_id."""
    rec = {
        "type": "optimization",
        "opt_id": opt_id,
        "ts": "2026-04-16T10:00:00+08:00",
        "scenario": scenario,
        "scope": "transferable",
        "status": "applied",
        "problem": "p",
        "hypothesis": "h",
        "changes": [],
    }
    p = cd / f"optimization_log_{scenario}.jsonl"
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def test_append_outcome_writes_record(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    cd = _contracts_dir(tmp_path)
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", cd)
    _seed_one_optimization(cd, "kundur", "opt_kd_20260416_01")
    from engine.optimization_log import append_outcome, load_log
    append_outcome(
        "kundur",
        "opt_kd_20260416_01",
        "effective",
        "settled_rate 0.05→0.18",
        confidence="high",
    )
    rows = load_log("kundur")
    outcome_rows = [r for r in rows if r.get("type") == "outcome"]
    assert len(outcome_rows) == 1
    o = outcome_rows[0]
    assert o["opt_id"] == "opt_kd_20260416_01"
    assert o["verdict"] == "effective"
    assert o["summary"] == "settled_rate 0.05→0.18"
    assert o["confidence"] == "high"
    assert o["type"] == "outcome"
    assert "ts" in o


def test_append_outcome_unknown_opt_id_raises(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", _contracts_dir(tmp_path))
    from engine.optimization_log import append_outcome
    with pytest.raises(ValueError, match="opt_id"):
        append_outcome("kundur", "opt_kd_99999999_01", "effective", "good")


def test_append_outcome_invalid_verdict_raises(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    cd = _contracts_dir(tmp_path)
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", cd)
    _seed_one_optimization(cd, "kundur", "opt_kd_20260416_01")
    from engine.optimization_log import append_outcome
    with pytest.raises(ValueError, match="verdict"):
        append_outcome("kundur", "opt_kd_20260416_01", "dunno", "summary")


# ── _build_opt_summary ────────────────────────────────────────────────────────

def test_build_opt_summary_empty():
    from engine.optimization_log import _build_opt_summary
    result = _build_opt_summary([])
    assert result == {"total": 0, "with_outcome": 0, "by_verdict": {}, "records": []}


def test_build_opt_summary_merges_outcome():
    from engine.optimization_log import _build_opt_summary
    records = [
        {"type": "optimization", "opt_id": "opt_kd_20260416_01",
         "scenario": "kundur", "scope": "transferable", "status": "applied",
         "problem": "p", "hypothesis": "h", "changes": []},
        {"type": "outcome", "opt_id": "opt_kd_20260416_01",
         "verdict": "effective", "summary": "good"},
    ]
    result = _build_opt_summary(records)
    assert result["total"] == 1
    assert result["with_outcome"] == 1
    assert result["by_verdict"] == {"effective": 1}
    merged = result["records"][0]
    assert merged["opt_id"] == "opt_kd_20260416_01"
    assert merged["outcome"]["verdict"] == "effective"


def test_build_opt_summary_no_outcome():
    from engine.optimization_log import _build_opt_summary
    records = [
        {"type": "optimization", "opt_id": "opt_kd_20260416_01",
         "scenario": "kundur", "scope": "transferable", "status": "applied",
         "problem": "p", "hypothesis": "h", "changes": []},
    ]
    result = _build_opt_summary(records)
    assert result["total"] == 1
    assert result["with_outcome"] == 0
    assert "outcome" not in result["records"][0]


def test_build_opt_summary_multiple_outcomes_last_wins():
    """Later outcome record overwrites earlier one for same opt_id."""
    from engine.optimization_log import _build_opt_summary
    records = [
        {"type": "optimization", "opt_id": "opt_kd_20260416_01",
         "scenario": "kundur", "scope": "transferable", "status": "applied",
         "problem": "p", "hypothesis": "h", "changes": []},
        {"type": "outcome", "opt_id": "opt_kd_20260416_01", "verdict": "inconclusive", "summary": "too early"},
        {"type": "outcome", "opt_id": "opt_kd_20260416_01", "verdict": "effective", "summary": "confirmed"},
    ]
    result = _build_opt_summary(records)
    assert result["records"][0]["outcome"]["verdict"] == "effective"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "C:\Users\27443\Desktop\Multi-Agent  VSGs"
python -m pytest tests/test_optimization_log.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'engine.optimization_log'` or similar import error.

- [ ] **Step 3: Commit the failing tests**

```bash
rtk git add tests/test_optimization_log.py
rtk git commit -m "test(opt-log): add failing tests for optimization_log module"
```

---

## Task 2: Implement `engine/optimization_log.py`

**Files:**
- Create: `engine/optimization_log.py`

- [ ] **Step 1: Create the module**

```python
# engine/optimization_log.py
"""Append-only optimization memory layer for RL training decisions.

Storage: scenarios/contracts/optimization_log_{scenario}.jsonl
One file per scenario (kundur | ne39), append-only JSONL.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONTRACTS_DIR = _REPO_ROOT / "scenarios" / "contracts"

_VALID_SCENARIOS = {"kundur", "ne39"}
_SCENARIO_PREFIX = {"kundur": "kd", "ne39": "ne"}
_VALID_SCOPES = {"kundur_only", "ne39_only", "transferable"}
_VALID_STATUSES = {"applied", "proposed", "rejected"}
_VALID_VERDICTS = {"effective", "ineffective", "inconclusive", "harmful"}
_OPT_REQUIRED = {"scenario", "scope", "status", "problem", "hypothesis", "changes"}


def _log_path(scenario: str) -> Path:
    return _CONTRACTS_DIR / f"optimization_log_{scenario}.jsonl"


def load_log(scenario: str) -> list[dict[str, Any]]:
    """Read all optimization records for a scenario in time order.

    Returns empty list if the file does not exist.
    Skips blank lines and JSON-decode failures silently.
    """
    path = _log_path(scenario)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return records


def _next_opt_id(scenario: str, today_str: str) -> str:
    """Generate next opt_id for today by scanning existing records."""
    prefix = _SCENARIO_PREFIX[scenario]
    existing = load_log(scenario)
    max_seq = 0
    for r in existing:
        oid = r.get("opt_id", "")
        # format: opt_{prefix}_{YYYYMMDD}_{seq}
        parts = oid.split("_")
        if len(parts) == 4 and parts[0] == "opt" and parts[1] == prefix and parts[2] == today_str:
            try:
                max_seq = max(max_seq, int(parts[3]))
            except ValueError:
                pass
    seq = max_seq + 1
    return f"opt_{prefix}_{today_str}_{seq:02d}"


def append_optimization(scenario: str, record: dict[str, Any]) -> str:
    """Append an optimization record. Returns the generated opt_id.

    Auto-fills: type, ts, opt_id.
    Validates: scenario is valid, all required fields are present.
    record must NOT include type/ts/opt_id — they are overwritten.
    """
    if scenario not in _VALID_SCENARIOS:
        raise ValueError(f"scenario must be one of {_VALID_SCENARIOS}, got {scenario!r}")
    missing = _OPT_REQUIRED - set(record.keys())
    if missing:
        raise ValueError(f"Missing required fields: {sorted(missing)}")

    today_str = datetime.now().strftime("%Y%m%d")
    opt_id = _next_opt_id(scenario, today_str)
    ts = datetime.now(tz=timezone.utc).astimezone().isoformat()

    row = {
        "type": "optimization",
        "opt_id": opt_id,
        "ts": ts,
        **{k: v for k, v in record.items() if k not in ("type", "ts", "opt_id")},
    }

    path = _log_path(scenario)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return opt_id


def append_outcome(
    scenario: str,
    opt_id: str,
    verdict: str,
    summary: str,
    **kwargs: Any,
) -> None:
    """Append an outcome record linked to opt_id.

    Auto-fills: type, ts.
    Validates: opt_id exists in log, verdict is valid.
    kwargs: result_run, transferable, transfer_notes, confidence.
    """
    if verdict not in _VALID_VERDICTS:
        raise ValueError(f"verdict must be one of {_VALID_VERDICTS}, got {verdict!r}")

    existing = load_log(scenario)
    known_ids = {r["opt_id"] for r in existing if r.get("type") == "optimization"}
    if opt_id not in known_ids:
        raise ValueError(f"opt_id {opt_id!r} not found in {scenario} log")

    ts = datetime.now(tz=timezone.utc).astimezone().isoformat()
    row: dict[str, Any] = {
        "type": "outcome",
        "opt_id": opt_id,
        "ts": ts,
        "verdict": verdict,
        "summary": summary,
    }
    allowed_kwargs = {"result_run", "transferable", "transfer_notes", "confidence"}
    for k, v in kwargs.items():
        if k in allowed_kwargs:
            row[k] = v

    path = _log_path(scenario)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _build_opt_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a merged summary dict for injection into training_diagnose output."""
    optimizations = [r for r in records if r.get("type") == "optimization"]
    outcomes: dict[str, dict[str, Any]] = {}
    for r in records:
        if r.get("type") == "outcome":
            outcomes[r["opt_id"]] = r  # later record overwrites earlier

    merged = []
    for opt in optimizations:
        entry = dict(opt)
        if opt["opt_id"] in outcomes:
            entry["outcome"] = outcomes[opt["opt_id"]]
        merged.append(entry)

    verdict_counts: dict[str, int] = {}
    for o in outcomes.values():
        v = o.get("verdict", "unknown")
        verdict_counts[v] = verdict_counts.get(v, 0) + 1

    return {
        "total": len(optimizations),
        "with_outcome": len(outcomes),
        "by_verdict": verdict_counts,
        "records": merged,
    }
```

- [ ] **Step 2: Run the tests**

```bash
python -m pytest tests/test_optimization_log.py -v
```

Expected: All tests PASS. Fix any failures before continuing.

- [ ] **Step 3: Commit**

```bash
rtk git add engine/optimization_log.py tests/test_optimization_log.py
rtk git commit -m "feat(opt-log): implement optimization_log module with load/append/summary"
```

---

## Task 3: Inject `optimization_history` into `training_diagnose()`

**Files:**
- Modify: `engine/training_tasks.py` (lines ~302-412, the `training_diagnose` function)
- Modify: `tests/test_training_tasks.py` (add one new test)

- [ ] **Step 1: Write the new failing test** — add to end of `tests/test_training_tasks.py`

```python
# Add to bottom of tests/test_training_tasks.py

def test_training_diagnose_includes_optimization_history(tmp_path, monkeypatch):
    """training_diagnose() must always include optimization_history key."""
    import utils.run_protocol as rp
    import engine.optimization_log as ol
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", tmp_path / "contracts")
    (tmp_path / "contracts").mkdir()

    run_dir = _make_run(tmp_path, "kundur", "run1", {
        "status": "running", "run_id": "run1",
        "episodes_total": 500, "episodes_done": 10,
    })
    _make_logs(run_dir)

    from engine.training_tasks import training_diagnose
    result = training_diagnose("kundur")
    assert "optimization_history" in result
    oh = result["optimization_history"]
    assert oh["total"] == 0
    assert oh["with_outcome"] == 0
    assert oh["by_verdict"] == {}
    assert oh["records"] == []


def test_training_diagnose_optimization_history_with_records(tmp_path, monkeypatch):
    """When opt log has records, training_diagnose merges them into optimization_history."""
    import json
    import utils.run_protocol as rp
    import engine.optimization_log as ol
    monkeypatch.setattr(rp, "_PROJECT_ROOT", tmp_path)
    cd = tmp_path / "contracts"
    cd.mkdir()
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", cd)

    # Seed one optimization + outcome in the log
    opt_rec = {
        "type": "optimization", "opt_id": "opt_kd_20260416_01",
        "ts": "2026-04-16T10:00:00+08:00", "scenario": "kundur",
        "scope": "transferable", "status": "applied",
        "problem": "r_h too high", "hypothesis": "lower PHI_H", "changes": [],
    }
    out_rec = {
        "type": "outcome", "opt_id": "opt_kd_20260416_01",
        "ts": "2026-04-16T20:00:00+08:00",
        "verdict": "effective", "summary": "settled_rate 0.05→0.18",
    }
    (cd / "optimization_log_kundur.jsonl").write_text(
        json.dumps(opt_rec) + "\n" + json.dumps(out_rec) + "\n",
        encoding="utf-8",
    )

    run_dir = _make_run(tmp_path, "kundur", "run1", {
        "status": "running", "run_id": "run1",
        "episodes_total": 500, "episodes_done": 50,
    })
    _make_logs(run_dir)

    from engine.training_tasks import training_diagnose
    result = training_diagnose("kundur")
    oh = result["optimization_history"]
    assert oh["total"] == 1
    assert oh["with_outcome"] == 1
    assert oh["by_verdict"] == {"effective": 1}
    assert oh["records"][0]["outcome"]["verdict"] == "effective"
```

- [ ] **Step 2: Run to verify these tests fail**

```bash
python -m pytest tests/test_training_tasks.py::test_training_diagnose_includes_optimization_history tests/test_training_tasks.py::test_training_diagnose_optimization_history_with_records -v
```

Expected: FAIL — `optimization_history` key not in result.

- [ ] **Step 3: Modify `engine/training_tasks.py`**

At the top of the file, add the import after the existing imports:

```python
# Add after existing imports (around line 15)
from engine.optimization_log import load_log as _load_opt_log, _build_opt_summary
```

In `training_diagnose()`, replace the final `return {...}` block (lines ~383-412):

```python
    # Load optimization history for this scenario
    opt_records = _load_opt_log(scenario_id)

    return {
        "scenario_id": scenario_id,
        "run_id": actual_run_id,
        "event_count": len(events),
        "alerts": list(_alert_groups.values()),
        "monitor_stop": (
            {"episode": monitor_stop_events[0].get("episode")}
            if monitor_stop_events else None
        ),
        "eval_rewards": [
            {"episode": e.get("episode"), "eval_reward": e.get("eval_reward")}
            for e in events if e.get("type") == "eval"
        ],
        "checkpoints": [
            {"episode": e.get("episode"), "file": e.get("file")}
            for e in events if e.get("type") == "checkpoint"
        ],
        "training_start": (
            {
                "episode": training_start_events[0].get("episode"),
                "mode": training_start_events[0].get("mode"),
            }
            if training_start_events else None
        ),
        "training_end": (
            {"episode": training_end_events[0].get("episode")}
            if training_end_events else None
        ),
        "physics_diagnosis": _diagnose_physics(run_dir, status),
        "optimization_history": _build_opt_summary(opt_records),
    }
```

Also fix the `_empty` dict (line ~321) to include the new key:

```python
    _empty: dict[str, Any] = {
        "scenario_id": scenario_id,
        "run_id": None,
        "event_count": 0,
        "alerts": [],
        "monitor_stop": None,
        "eval_rewards": [],
        "checkpoints": [],
        "training_start": None,
        "training_end": None,
        "physics_diagnosis": {"pattern": None, "evidence": "no run found", "recommendation": None},
        "optimization_history": {"total": 0, "with_outcome": 0, "by_verdict": {}, "records": []},
    }
```

- [ ] **Step 4: Run all training_tasks tests**

```bash
python -m pytest tests/test_training_tasks.py -v
```

Expected: All tests PASS (existing + new).

- [ ] **Step 5: Commit**

```bash
rtk git add engine/training_tasks.py tests/test_training_tasks.py
rtk git commit -m "feat(opt-log): inject optimization_history into training_diagnose output"
```

---

## Task 4: Add AI behavior rules to `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add the optimization log section**

Open `CLAUDE.md`. Find the section `## 重要注意事项` near the bottom. Insert the following block **before** that section:

```markdown
## Optimization Log — AI 行为规范

优化记录文件：`scenarios/contracts/optimization_log_{kundur|ne39}.jsonl`
读写接口：`engine/optimization_log.py`（`load_log` / `append_optimization` / `append_outcome`）

**提出新优化建议前（4条强制规则）：**

1. **必读历史**：通过 `training_diagnose(scenario_id)["optimization_history"]` 获取当前场景历史，
   不能在未看到 `optimization_history` 的情况下提出新优化建议。
2. **NE39 额外迁移检查**：操作 NE39 时，额外读取 Kundur log（`load_log("kundur")`）中
   `scope=transferable` 且 `verdict=effective` 的记录，作为迁移参考。
3. **参数重叠必须说明**：若改动涉及历史已有参数，必须说明是"延续已有方向的微调"还是
   "基于新 hypothesis 的重试"；上次 `verdict=harmful` 时必须解释为何这次条件不同。
4. **上下文变化降级**：若 reward/obs/agent/disturbance 等已发生明显变化，
   旧结论自动降级为参考，不能作为强反证。

**写入时机：**
- `append_optimization`：建议被采纳、代码已修改后，立即调用
- `append_outcome`：训练结束、分析完结果后调用；summary 必须含具体指标变化（数值）

```

- [ ] **Step 2: Verify CLAUDE.md stays under 120 lines**

```bash
wc -l CLAUDE.md
```

If over 120 lines, trim redundant content elsewhere to compensate.

- [ ] **Step 3: Commit**

```bash
rtk git add CLAUDE.md
rtk git commit -m "docs(opt-log): add AI behavior rules for optimization log to CLAUDE.md"
```

---

## Task 5: Full test suite verification

- [ ] **Step 1: Run all relevant tests**

```bash
python -m pytest tests/test_optimization_log.py tests/test_training_tasks.py -v
```

Expected: All green.

- [ ] **Step 2: Quick smoke check — existing tests still pass**

```bash
python -m pytest tests/ -x -q --ignore=tests/test_andes_kundur_smoke.py --ignore=tests/test_smoke_simulink.py 2>&1 | tail -20
```

Expected: No new failures introduced.

- [ ] **Step 3: Write a quick manual smoke to E:\讨论\opt_log_smoke.txt**

```bash
python -c "
import sys, json
sys.path.insert(0, '.')
import engine.optimization_log as ol
import tempfile, pathlib

# Use temp dir so we don't pollute real logs
with tempfile.TemporaryDirectory() as td:
    ol._CONTRACTS_DIR = pathlib.Path(td)
    opt_id = ol.append_optimization('kundur', {
        'scenario': 'kundur', 'scope': 'transferable', 'status': 'applied',
        'problem': 'r_h dominates critic', 'hypothesis': 'lower PHI_H',
        'changes': [{'param': 'PHI_H', 'from': 1.0, 'to': 0.3}],
    })
    print('opt_id:', opt_id)
    ol.append_outcome('kundur', opt_id, 'effective', 'settled_rate 0.05->0.18', confidence='high')
    rows = ol.load_log('kundur')
    summary = ol._build_opt_summary(rows)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
" > "E:\讨论\opt_log_smoke.txt" 2>&1
```

Check `E:\讨论\opt_log_smoke.txt` — should show opt_id and merged summary with `total: 1, with_outcome: 1`.

---

## Self-Review Against Spec

**Spec coverage check:**

| Requirement | Task |
|-------------|------|
| `engine/optimization_log.py` with `load_log/append_optimization/append_outcome` | Task 2 |
| `opt_id` auto-generation `opt_{kd\|ne}_{YYYYMMDD}_{seq}` | Task 2 (Step 1) |
| `ts` auto-filled, type auto-filled | Task 2 |
| `scenario` + required field validation | Task 2 |
| `verdict` validation | Task 2 |
| `opt_id` existence validation in append_outcome | Task 2 |
| Append-only JSONL, 'a' mode | Task 2 |
| Skip empty lines + malformed JSON | Task 2 |
| `_build_opt_summary` with total/with_outcome/by_verdict/records | Task 2 |
| `training_diagnose()` injection via `optimization_history` | Task 3 |
| `_empty` dict includes `optimization_history` | Task 3 (Step 3) |
| 4 AI behavior rules in CLAUDE.md | Task 4 |
| Unit tests | Task 1 (failing tests) + Task 2 (run passing) |

**Placeholder scan:** No TBD/TODO/placeholder text found.

**Type consistency:** `_build_opt_summary` is imported and used consistently. `load_log` return type `list[dict]` flows correctly into `_build_opt_summary`.

**P1 items** (`query_history`, `find_param_overlaps`) are deliberately excluded — YAGNI for this phase.
