# Phase 1: Artifact Contract & Run Verdict Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every training run a unified, machine-readable identity so the system can automatically output a PASS/MARGINAL/FAIL verdict when training ends.

**Architecture:** Each training run writes three files alongside the existing `training_log.json`: `metrics.jsonl` (one JSON line per episode, append-mode), `events.jsonl` (monitor alerts + checkpoints), and `latest_state.json` (overwritten every 50 episodes as a current snapshot). A new `evaluate_run.py` reads these files against scenario-specific quality thresholds defined in `scenarios/contracts/<scenario_id>.json` and emits a structured verdict JSON. The existing `training_log.json` is kept for backward compatibility with `training_viz.py`.

**Tech Stack:** Python 3.11 (andes_env), pytest, json, pathlib — no new dependencies.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `utils/artifact_writer.py` | Append-mode JSONL writing + atomic latest_state.json updates |
| Create | `utils/evaluate_run.py` | Load artifacts → compute verdict → emit JSON + one-page PNG |
| Create | `scenarios/contracts/sim_kundur.json` | Quality thresholds + artifact root for Kundur Simulink |
| Create | `scenarios/contracts/sim_ne39.json` | Quality thresholds + artifact root for NE39 Simulink |
| Create | `tests/test_artifact_writer.py` | Unit tests for ArtifactWriter |
| Create | `tests/test_evaluate_run.py` | Unit tests for verdict logic |
| Modify | `scenarios/kundur/train_simulink.py` | Add ArtifactWriter integration |
| Modify | `scenarios/new_england/train_simulink.py` | Add ArtifactWriter integration |

**Artifact layout per run (no changes to existing paths):**
```
results/sim_kundur/
  logs/simulink/
    training_log.json       ← existing (keep, backward compat)
    monitor_data.csv        ← existing
    monitor_state.json      ← existing
    metrics.jsonl           ← NEW: one line per episode
    events.jsonl            ← NEW: monitor alerts + checkpoint events
    latest_state.json       ← NEW: current snapshot (overwritten every 50 ep)
  checkpoints/simulink/
    run_meta.json           ← existing
```

---

## Task 1: Scenario Contract JSON Files

**Files:**
- Create: `scenarios/contracts/sim_kundur.json`
- Create: `scenarios/contracts/sim_ne39.json`

These are read-only data files. No test needed (validated by Task 3 tests via load path).

- [ ] **Step 1: Create contracts directory and sim_kundur.json**

```bash
mkdir -p "C:\Users\27443\Desktop\Multi-Agent  VSGs\scenarios\contracts"
```

Create `scenarios/contracts/sim_kundur.json`:

```json
{
  "scenario_id": "sim_kundur",
  "description": "Simulink × Kundur two-area, 4 VSG agents, 50 Hz",
  "n_agents": 4,
  "omega_hz": 50,
  "t_episode_s": 5.0,
  "artifact_root": "results/sim_kundur",
  "quality_thresholds": {
    "eval_reward_pass": -10000,
    "eval_reward_marginal": -50000,
    "settled_rate_100ep_pass": 0.30,
    "settled_rate_100ep_marginal": 0.10,
    "mean_freq_dev_hz_pass": 2.0,
    "mean_freq_dev_hz_marginal": 5.0,
    "alpha_min": 0.001,
    "alpha_max": 4.5,
    "reward_trend_window": 100
  }
}
```

- [ ] **Step 2: Create sim_ne39.json**

Create `scenarios/contracts/sim_ne39.json`:

```json
{
  "scenario_id": "sim_ne39",
  "description": "Simulink × NE 39-bus, 8 VSG agents, 60 Hz",
  "n_agents": 8,
  "omega_hz": 60,
  "t_episode_s": 10.0,
  "artifact_root": "results/sim_ne39",
  "quality_thresholds": {
    "eval_reward_pass": -80000,
    "eval_reward_marginal": -300000,
    "settled_rate_100ep_pass": 0.20,
    "settled_rate_100ep_marginal": 0.05,
    "mean_freq_dev_hz_pass": 3.0,
    "mean_freq_dev_hz_marginal": 8.0,
    "alpha_min": 0.001,
    "alpha_max": 4.5,
    "reward_trend_window": 100
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add scenarios/contracts/
git commit -m "feat(contracts): add scenario quality threshold contracts for sim_kundur and sim_ne39"
```

---

## Task 2: ArtifactWriter Utility

**Files:**
- Create: `utils/artifact_writer.py`
- Create: `tests/test_artifact_writer.py`

### Step 2a: Write the failing tests first

- [ ] **Step 1: Write tests/test_artifact_writer.py**

```python
"""Tests for ArtifactWriter — JSONL append + atomic latest_state."""
import json
import os
import tempfile
from pathlib import Path
import pytest

# Adjust sys.path so we can import from utils/ when running from any cwd.
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.artifact_writer import ArtifactWriter


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def test_metrics_jsonl_created(tmp_dir):
    w = ArtifactWriter(tmp_dir)
    w.log_metric(0, {"reward": -1000.0, "alpha": 0.5})
    path = Path(tmp_dir) / "metrics.jsonl"
    assert path.exists()
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["episode"] == 0
    assert record["reward"] == pytest.approx(-1000.0)
    assert record["alpha"] == pytest.approx(0.5)
    assert "ts" in record


def test_metrics_jsonl_appends(tmp_dir):
    w = ArtifactWriter(tmp_dir)
    w.log_metric(0, {"reward": -1000.0})
    w.log_metric(1, {"reward": -900.0})
    lines = (Path(tmp_dir) / "metrics.jsonl").read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[1])["episode"] == 1


def test_events_jsonl_created(tmp_dir):
    w = ArtifactWriter(tmp_dir)
    w.log_event(5, "alert", {"check": "freq_out_of_range", "message": "test"})
    path = Path(tmp_dir) / "events.jsonl"
    assert path.exists()
    record = json.loads(path.read_text().strip())
    assert record["episode"] == 5
    assert record["type"] == "alert"
    assert record["check"] == "freq_out_of_range"
    assert "ts" in record


def test_update_state_writes_json(tmp_dir):
    w = ArtifactWriter(tmp_dir)
    w.update_state({"episode": 50, "reward_mean": -5000.0, "alpha": 0.3})
    path = Path(tmp_dir) / "latest_state.json"
    assert path.exists()
    state = json.loads(path.read_text())
    assert state["episode"] == 50
    assert state["reward_mean"] == pytest.approx(-5000.0)
    assert "ts" in state


def test_update_state_is_atomic(tmp_dir):
    """latest_state.json should never contain partial writes."""
    w = ArtifactWriter(tmp_dir)
    w.update_state({"episode": 10})
    w.update_state({"episode": 20, "extra": "field"})
    path = Path(tmp_dir) / "latest_state.json"
    state = json.loads(path.read_text())
    assert state["episode"] == 20   # second write replaced first


def test_log_dir_created_if_missing(tmp_dir):
    nested = os.path.join(tmp_dir, "deep", "nested")
    w = ArtifactWriter(nested)
    w.log_metric(0, {"reward": 0.0})
    assert (Path(nested) / "metrics.jsonl").exists()
```

- [ ] **Step 2: Run tests to confirm they all FAIL**

```bash
cd "C:\Users\27443\Desktop\Multi-Agent  VSGs"
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_artifact_writer.py -v 2>&1 | head -40
```

Expected: `ModuleNotFoundError: No module named 'utils.artifact_writer'`

### Step 2b: Implement ArtifactWriter

- [ ] **Step 3: Create utils/artifact_writer.py**

```python
"""ArtifactWriter: lightweight structured output for training runs.

Writes three files to a log directory:
  metrics.jsonl     — one JSON line per episode (append)
  events.jsonl      — one JSON line per event: alerts, checkpoints (append)
  latest_state.json — current snapshot, overwritten atomically each update
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ArtifactWriter:
    """Writes structured training artifacts to a log directory."""

    def __init__(self, log_dir: str | Path) -> None:
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._metrics_path = self._dir / "metrics.jsonl"
        self._events_path = self._dir / "events.jsonl"
        self._state_path = self._dir / "latest_state.json"

    def log_metric(self, episode: int, data: dict[str, Any]) -> None:
        """Append one episode's metrics to metrics.jsonl."""
        record = {"episode": episode, "ts": _now_iso(), **data}
        self._append_jsonl(self._metrics_path, record)

    def log_event(self, episode: int, event_type: str, data: dict[str, Any]) -> None:
        """Append one event (alert, checkpoint, stop) to events.jsonl."""
        record = {"episode": episode, "ts": _now_iso(), "type": event_type, **data}
        self._append_jsonl(self._events_path, record)

    def update_state(self, data: dict[str, Any]) -> None:
        """Atomically overwrite latest_state.json with current snapshot."""
        record = {"ts": _now_iso(), **data}
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self._dir, prefix=".state_", suffix=".json"
        )
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(record, f, indent=2)
            os.replace(tmp_path, self._state_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @staticmethod
    def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Run tests — expect all PASS**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_artifact_writer.py -v
```

Expected output:
```
PASSED tests/test_artifact_writer.py::test_metrics_jsonl_created
PASSED tests/test_artifact_writer.py::test_metrics_jsonl_appends
PASSED tests/test_artifact_writer.py::test_events_jsonl_created
PASSED tests/test_artifact_writer.py::test_update_state_writes_json
PASSED tests/test_artifact_writer.py::test_update_state_is_atomic
PASSED tests/test_artifact_writer.py::test_log_dir_created_if_missing
6 passed
```

- [ ] **Step 5: Commit**

```bash
git add utils/artifact_writer.py tests/test_artifact_writer.py
git commit -m "feat(artifact): ArtifactWriter — append JSONL metrics/events + atomic state snapshot"
```

---

## Task 3: evaluate_run.py with Verdict Logic

**Files:**
- Create: `utils/evaluate_run.py`
- Create: `tests/test_evaluate_run.py`

### Step 3a: Write failing tests first

- [ ] **Step 1: Write tests/test_evaluate_run.py**

```python
"""Tests for evaluate_run verdict logic."""
import json
import os
import tempfile
from pathlib import Path
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.evaluate_run import (
    load_metrics,
    load_contract,
    compute_verdict,
    EvaluationResult,
    Verdict,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _write_metrics(path: Path, rows: list[dict]) -> None:
    """Write a metrics.jsonl file from a list of episode dicts."""
    with path.open("w") as f:
        for i, row in enumerate(rows):
            record = {"episode": i, "ts": "2026-01-01T00:00:00+00:00", **row}
            f.write(json.dumps(record) + "\n")


def _make_contract(tmp_dir: str) -> dict:
    contract = {
        "scenario_id": "sim_kundur",
        "n_agents": 4,
        "omega_hz": 50,
        "quality_thresholds": {
            "eval_reward_pass": -10000,
            "eval_reward_marginal": -50000,
            "settled_rate_100ep_pass": 0.30,
            "settled_rate_100ep_marginal": 0.10,
            "mean_freq_dev_hz_pass": 2.0,
            "mean_freq_dev_hz_marginal": 5.0,
            "alpha_min": 0.001,
            "alpha_max": 4.5,
            "reward_trend_window": 100,
        },
    }
    p = Path(tmp_dir) / "sim_kundur.json"
    p.write_text(json.dumps(contract))
    return contract


@pytest.fixture
def tmp_run_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


# ── load_metrics ─────────────────────────────────────────────────────────────

def test_load_metrics_parses_jsonl(tmp_run_dir):
    _write_metrics(tmp_run_dir / "metrics.jsonl", [
        {"reward": -1000.0, "alpha": 0.5, "physics": {"max_freq_dev_hz": 0.5, "settled": True}},
        {"reward": -900.0,  "alpha": 0.4, "physics": {"max_freq_dev_hz": 0.4, "settled": True}},
    ])
    rows = load_metrics(tmp_run_dir)
    assert len(rows) == 2
    assert rows[0]["reward"] == pytest.approx(-1000.0)


def test_load_metrics_missing_file_returns_empty(tmp_run_dir):
    rows = load_metrics(tmp_run_dir)
    assert rows == []


# ── compute_verdict: PASS ─────────────────────────────────────────────────────

def test_verdict_pass_all_criteria_met(tmp_run_dir):
    """100 episodes with good rewards, settled, low freq dev → PASS."""
    rows = [
        {
            "reward": -5000.0 + i * 30,   # improving trend
            "alpha": 0.1,
            "eval_reward": -4000.0,
            "physics": {"max_freq_dev_hz": 1.0, "mean_freq_dev_hz": 0.5, "settled": True},
        }
        for i in range(120)
    ]
    _write_metrics(tmp_run_dir / "metrics.jsonl", rows)
    with tempfile.TemporaryDirectory() as cd:
        contract = _make_contract(cd)
    result = compute_verdict(load_metrics(tmp_run_dir), contract["quality_thresholds"])
    assert result.verdict == Verdict.PASS


# ── compute_verdict: FAIL ─────────────────────────────────────────────────────

def test_verdict_fail_too_few_episodes(tmp_run_dir):
    """< 50 episodes → always FAIL (insufficient data)."""
    rows = [
        {"reward": -3000.0, "alpha": 0.1,
         "physics": {"max_freq_dev_hz": 0.5, "mean_freq_dev_hz": 0.3, "settled": True}}
        for _ in range(20)
    ]
    _write_metrics(tmp_run_dir / "metrics.jsonl", rows)
    with tempfile.TemporaryDirectory() as cd:
        contract = _make_contract(cd)
    result = compute_verdict(load_metrics(tmp_run_dir), contract["quality_thresholds"])
    assert result.verdict == Verdict.FAIL
    assert any("insufficient" in r.lower() for r in result.reasons)


def test_verdict_fail_diverging_reward(tmp_run_dir):
    """Reward worsening across last 100 episodes → FAIL."""
    rows = [
        {"reward": -1000.0 - i * 100,   # diverging
         "alpha": 0.1,
         "physics": {"max_freq_dev_hz": 1.0, "mean_freq_dev_hz": 0.5, "settled": False}}
        for i in range(120)
    ]
    _write_metrics(tmp_run_dir / "metrics.jsonl", rows)
    with tempfile.TemporaryDirectory() as cd:
        contract = _make_contract(cd)
    result = compute_verdict(load_metrics(tmp_run_dir), contract["quality_thresholds"])
    assert result.verdict == Verdict.FAIL


def test_verdict_fail_alpha_collapsed(tmp_run_dir):
    """Alpha near zero → FAIL (entropy collapsed)."""
    rows = [
        {"reward": -3000.0, "alpha": 0.00001,
         "physics": {"max_freq_dev_hz": 1.0, "mean_freq_dev_hz": 0.5, "settled": True}}
        for _ in range(120)
    ]
    _write_metrics(tmp_run_dir / "metrics.jsonl", rows)
    with tempfile.TemporaryDirectory() as cd:
        contract = _make_contract(cd)
    result = compute_verdict(load_metrics(tmp_run_dir), contract["quality_thresholds"])
    assert result.verdict == Verdict.FAIL
    assert any("alpha" in r.lower() for r in result.reasons)


# ── compute_verdict: MARGINAL ─────────────────────────────────────────────────

def test_verdict_marginal_settled_rate_low(tmp_run_dir):
    """Reward OK but settled_rate between marginal and pass thresholds → MARGINAL."""
    rows = [
        {"reward": -8000.0 + i * 20,   # improving, will reach pass eval_reward range
         "alpha": 0.15,
         "eval_reward": -8000.0,        # between marginal and pass thresholds
         "physics": {"max_freq_dev_hz": 1.5, "mean_freq_dev_hz": 0.8,
                     "settled": (i % 8 == 0)}}  # settled_rate = 0.125
        for i in range(120)
    ]
    _write_metrics(tmp_run_dir / "metrics.jsonl", rows)
    with tempfile.TemporaryDirectory() as cd:
        contract = _make_contract(cd)
    result = compute_verdict(load_metrics(tmp_run_dir), contract["quality_thresholds"])
    assert result.verdict in (Verdict.MARGINAL, Verdict.FAIL)


# ── load_contract ─────────────────────────────────────────────────────────────

def test_load_contract_reads_json(tmp_run_dir):
    contract_path = tmp_run_dir / "sim_kundur.json"
    data = {"scenario_id": "sim_kundur", "quality_thresholds": {}}
    contract_path.write_text(json.dumps(data))
    loaded = load_contract(contract_path)
    assert loaded["scenario_id"] == "sim_kundur"
```

- [ ] **Step 2: Run tests — confirm FAIL**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_evaluate_run.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'utils.evaluate_run'`

### Step 3b: Implement evaluate_run.py

- [ ] **Step 3: Create utils/evaluate_run.py**

```python
"""evaluate_run: load training artifacts and emit a structured run verdict.

Usage (CLI):
    python utils/evaluate_run.py --log-dir results/sim_kundur/logs/simulink \
                                 --contract scenarios/contracts/sim_kundur.json \
                                 [--out results/sim_kundur/verdict.json]

Verdict levels:
  PASS      — all key metrics within quality thresholds
  MARGINAL  — at least one metric between pass and marginal thresholds
  FAIL      — insufficient data, divergence, or below marginal threshold
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np


class Verdict(str, Enum):
    PASS = "PASS"
    MARGINAL = "MARGINAL"
    FAIL = "FAIL"


@dataclass
class EvaluationResult:
    verdict: Verdict
    reasons: list[str]
    metrics: dict[str, Any] = field(default_factory=dict)
    episode_count: int = 0


# ── I/O helpers ───────────────────────────────────────────────────────────────

def load_metrics(log_dir: Path | str) -> list[dict]:
    """Return list of episode records from metrics.jsonl (empty list if missing)."""
    path = Path(log_dir) / "metrics.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def load_contract(contract_path: Path | str) -> dict:
    """Load scenario contract JSON."""
    return json.loads(Path(contract_path).read_text(encoding="utf-8"))


# ── verdict computation ────────────────────────────────────────────────────────

def _linear_trend(values: list[float]) -> float:
    """Slope of OLS line fitted to values (positive = improving)."""
    n = len(values)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=float)
    x -= x.mean()
    y = np.array(values, dtype=float)
    y -= y.mean()
    denom = float((x * x).sum())
    return float((x * y).sum() / denom) if denom > 1e-12 else 0.0


def compute_verdict(rows: list[dict], thresholds: dict) -> EvaluationResult:
    """Compute a PASS/MARGINAL/FAIL verdict from episode metrics rows."""
    reasons: list[str] = []
    computed: dict[str, Any] = {}
    n = len(rows)
    computed["episode_count"] = n

    # ── Guard: insufficient data ──────────────────────────────────────────────
    if n < 50:
        return EvaluationResult(
            verdict=Verdict.FAIL,
            reasons=[f"Insufficient data: only {n} episodes (need ≥ 50)"],
            metrics=computed,
            episode_count=n,
        )

    window = min(thresholds.get("reward_trend_window", 100), n)
    recent = rows[-window:]

    # ── Extract reward series ─────────────────────────────────────────────────
    rewards = [r["reward"] for r in recent if "reward" in r]
    computed["reward_mean_recent"] = float(np.mean(rewards)) if rewards else None
    computed["reward_trend_slope"] = _linear_trend(rewards) if len(rewards) >= 2 else 0.0

    # ── Extract eval rewards (optional) ──────────────────────────────────────
    eval_rewards = [r["eval_reward"] for r in rows if "eval_reward" in r]
    last_eval = float(eval_rewards[-1]) if eval_rewards else None
    computed["last_eval_reward"] = last_eval

    # ── Extract alpha series ──────────────────────────────────────────────────
    alphas = [r["alpha"] for r in recent if "alpha" in r]
    mean_alpha = float(np.mean(alphas)) if alphas else None
    computed["mean_alpha_recent"] = mean_alpha

    # ── Extract physics ───────────────────────────────────────────────────────
    physics_rows = [r["physics"] for r in recent if "physics" in r]
    settled_flags = [p["settled"] for p in physics_rows if "settled" in p]
    freq_devs = [p.get("mean_freq_dev_hz", p.get("max_freq_dev_hz", 0.0))
                 for p in physics_rows]
    settled_rate = float(np.mean(settled_flags)) if settled_flags else 0.0
    mean_freq_dev = float(np.mean(freq_devs)) if freq_devs else None
    computed["settled_rate_recent"] = settled_rate
    computed["mean_freq_dev_hz_recent"] = mean_freq_dev

    # ── Score each criterion ──────────────────────────────────────────────────
    scores: list[str] = []   # "pass", "marginal", "fail"

    # 1. Reward trend
    slope = computed["reward_trend_slope"]
    if slope > 0:
        scores.append("pass")
    elif slope > -5:
        scores.append("marginal")
        reasons.append(f"Reward trend flat or slightly negative (slope={slope:.2f}/ep)")
    else:
        scores.append("fail")
        reasons.append(f"Reward diverging (slope={slope:.2f}/ep)")

    # 2. Eval reward (if available)
    if last_eval is not None:
        thr_pass = thresholds.get("eval_reward_pass", -1e9)
        thr_marg = thresholds.get("eval_reward_marginal", -1e9)
        if last_eval >= thr_pass:
            scores.append("pass")
        elif last_eval >= thr_marg:
            scores.append("marginal")
            reasons.append(f"Eval reward marginal ({last_eval:.0f}, pass threshold {thr_pass:.0f})")
        else:
            scores.append("fail")
            reasons.append(f"Eval reward below marginal ({last_eval:.0f} < {thr_marg:.0f})")

    # 3. Settled rate
    thr_sr_pass = thresholds.get("settled_rate_100ep_pass", 0.30)
    thr_sr_marg = thresholds.get("settled_rate_100ep_marginal", 0.10)
    if settled_rate >= thr_sr_pass:
        scores.append("pass")
    elif settled_rate >= thr_sr_marg:
        scores.append("marginal")
        reasons.append(f"Settled rate marginal ({settled_rate:.2f}, pass={thr_sr_pass:.2f})")
    else:
        scores.append("fail")
        reasons.append(f"Settled rate below marginal ({settled_rate:.2f} < {thr_sr_marg:.2f})")

    # 4. Mean frequency deviation
    if mean_freq_dev is not None:
        thr_fd_pass = thresholds.get("mean_freq_dev_hz_pass", 2.0)
        thr_fd_marg = thresholds.get("mean_freq_dev_hz_marginal", 5.0)
        if mean_freq_dev <= thr_fd_pass:
            scores.append("pass")
        elif mean_freq_dev <= thr_fd_marg:
            scores.append("marginal")
            reasons.append(f"Freq dev marginal ({mean_freq_dev:.2f} Hz, pass ≤ {thr_fd_pass:.2f})")
        else:
            scores.append("fail")
            reasons.append(f"Freq dev above marginal ({mean_freq_dev:.2f} Hz > {thr_fd_marg:.2f})")

    # 5. Alpha health
    if mean_alpha is not None:
        alpha_min = thresholds.get("alpha_min", 0.001)
        alpha_max = thresholds.get("alpha_max", 4.5)
        if alpha_min <= mean_alpha <= alpha_max:
            scores.append("pass")
        elif mean_alpha < alpha_min:
            scores.append("fail")
            reasons.append(f"Alpha collapsed ({mean_alpha:.5f} < {alpha_min})")
        else:
            scores.append("fail")
            reasons.append(f"Alpha saturated ({mean_alpha:.2f} > {alpha_max})")

    # ── Aggregate scores ──────────────────────────────────────────────────────
    if "fail" in scores:
        verdict = Verdict.FAIL
    elif "marginal" in scores:
        verdict = Verdict.MARGINAL
    else:
        verdict = Verdict.PASS

    if verdict == Verdict.PASS:
        reasons = ["All criteria met"]

    return EvaluationResult(
        verdict=verdict,
        reasons=reasons,
        metrics=computed,
        episode_count=n,
    )


# ── CLI entry point ────────────────────────────────────────────────────────────

def _parse_args():
    p = argparse.ArgumentParser(description="Evaluate a training run and emit a verdict.")
    p.add_argument("--log-dir", required=True, help="Path to logs/<mode>/ directory")
    p.add_argument("--contract", required=True, help="Path to scenario contract JSON")
    p.add_argument("--out", default=None, help="Output verdict JSON path (default: <log-dir>/verdict.json)")
    return p.parse_args()


def main():
    args = _parse_args()
    log_dir = Path(args.log_dir)
    contract = load_contract(args.contract)
    rows = load_metrics(log_dir)
    result = compute_verdict(rows, contract["quality_thresholds"])

    out_path = Path(args.out) if args.out else log_dir / "verdict.json"
    out_data = {
        "scenario_id": contract.get("scenario_id", "unknown"),
        "log_dir": str(log_dir),
        "verdict": result.verdict.value,
        "reasons": result.reasons,
        "metrics": result.metrics,
        "episode_count": result.episode_count,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_data, indent=2))

    print(f"\n{'='*50}")
    print(f"  Verdict: {result.verdict.value}")
    print(f"  Episodes evaluated: {result.episode_count}")
    for r in result.reasons:
        print(f"  • {r}")
    print(f"{'='*50}")
    print(f"  Saved to: {out_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests — expect all PASS**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_evaluate_run.py -v
```

Expected:
```
PASSED tests/test_evaluate_run.py::test_load_metrics_parses_jsonl
PASSED tests/test_evaluate_run.py::test_load_metrics_missing_file_returns_empty
PASSED tests/test_evaluate_run.py::test_verdict_pass_all_criteria_met
PASSED tests/test_evaluate_run.py::test_verdict_fail_too_few_episodes
PASSED tests/test_evaluate_run.py::test_verdict_fail_diverging_reward
PASSED tests/test_evaluate_run.py::test_verdict_fail_alpha_collapsed
PASSED tests/test_evaluate_run.py::test_verdict_marginal_settled_rate_low
PASSED tests/test_evaluate_run.py::test_load_contract_reads_json
8 passed
```

- [ ] **Step 5: Commit**

```bash
git add utils/evaluate_run.py tests/test_evaluate_run.py
git commit -m "feat(evaluate): run verdict system — PASS/MARGINAL/FAIL from metrics.jsonl + contract thresholds"
```

---

## Task 4: Integrate ArtifactWriter into Kundur Simulink Training

**Files:**
- Modify: `scenarios/kundur/train_simulink.py`

No new tests needed — existing training smoke tests cover the loop.
Integration is additive (new writes alongside existing `training_log.json`).

- [ ] **Step 1: Add import at top of scenarios/kundur/train_simulink.py**

After the existing imports block (line ~33), add:

```python
from utils.artifact_writer import ArtifactWriter
```

- [ ] **Step 2: Instantiate ArtifactWriter in train() after log_dir setup**

In `train()`, after `os.makedirs(os.path.dirname(args.log_file), exist_ok=True)` (currently ~line 211), add:

```python
    _log_dir = os.path.dirname(args.log_file)
    writer = ArtifactWriter(_log_dir)
    writer.log_event(start_episode, "training_start", {
        "mode": args.mode,
        "start_episode": start_episode,
        "end_episode": start_episode + args.episodes,
    })
```

- [ ] **Step 3: Log per-episode metrics after the existing log dict update**

After `log["physics_summary"].append({...})` block (currently ~line 316–321),
and after `log["alphas"].append(...)` block (currently ~line 329), add:

```python
        # --- artifact writer: append episode metrics ---
        writer.log_metric(ep, {
            "reward": float(mean_reward),
            "reward_components": ep_components,
            "alpha": float(np.mean(ep_losses["alpha"])) if ep_losses["alpha"] else None,
            "critic_loss": float(np.mean(ep_losses["critic"])) if ep_losses["critic"] else None,
            "policy_loss": float(np.mean(ep_losses["policy"])) if ep_losses["policy"] else None,
            "physics": {
                "max_freq_dev_hz": float(ep_max_freq_dev),
                "mean_freq_dev_hz": float(ep_mean_freq_dev),
                "settled": ep_settled,
                "max_power_swing": ep_power_swing,
            },
        })
```

- [ ] **Step 4: Route monitor alerts to events.jsonl**

After `stop_triggered = monitor.log_and_check(...)` call (currently ~line 339–350),
replace the existing `if stop_triggered:` block with:

```python
        # Route any new monitor triggers to events.jsonl
        _new_triggers = monitor._trigger_history[_prev_trigger_len:]
        for t in _new_triggers:
            writer.log_event(ep, "alert", t)
        _prev_trigger_len = len(monitor._trigger_history)

        if stop_triggered:
            writer.log_event(ep, "monitor_stop", {"episode": ep})
            print(f"[Monitor] Hard stop at episode {ep}. Saving checkpoint.")
            agent.save(
                os.path.join(args.checkpoint_dir, f"monitor_stop_ep{ep}.pt"),
                metadata={"start_episode": ep + 1},
            )
            break
```

Also initialize `_prev_trigger_len` before the episode loop (after `monitor = TrainingMonitor()`):

```python
    _prev_trigger_len = 0
```

- [ ] **Step 5: Log checkpoint events and update latest_state every 50 episodes**

After the `if (ep + 1) % args.eval_interval == 0:` block (eval section), add:

```python
        # Log eval result to events.jsonl
        if (ep + 1) % args.eval_interval == 0:
            writer.log_event(ep, "eval", {"eval_reward": float(eval_reward)})
            # also embed eval_reward in next metrics line for verdict scoring
            # (already written above — add eval_reward field if eval happened this ep)

        # Checkpoint event
        if (ep + 1) % args.save_interval == 0:
            writer.log_event(ep, "checkpoint", {
                "file": f"ep{ep+1}.pt",
                "episode": ep + 1,
            })

        # Update latest_state every 50 episodes
        if (ep + 1) % 50 == 0:
            _recent_rewards = log["episode_rewards"][-50:]
            _recent_physics = log["physics_summary"][-50:]
            _settled_recent = [p["settled"] for p in _recent_physics]
            writer.update_state({
                "episode": ep,
                "reward_mean_50": float(np.mean(_recent_rewards)),
                "alpha": float(agent.alpha),
                "settled_rate_50": float(np.mean(_settled_recent)) if _settled_recent else 0.0,
                "buffer_size": len(agent.buffer),
            })
```

Also add eval_reward to the metric record when eval happens this episode. Find the metrics write in Step 3 and add an optional field. The simplest approach: track eval result in a local variable and include it:

Before the episode loop, add:
```python
    _last_eval_reward: float | None = None
```

After `eval_reward = evaluate(env, agent)`, add:
```python
            _last_eval_reward = float(eval_reward)
```

In the `writer.log_metric(...)` call from Step 3, add:
```python
            "eval_reward": _last_eval_reward if (ep + 1) % args.eval_interval == 0 else None,
```

- [ ] **Step 6: Log training end event**

In the `try:` block at the end of `train()`, after `agent.save("final.pt")`:

```python
        writer.log_event(
            start_episode + args.episodes - 1,
            "training_end",
            {"total_episodes": start_episode + args.episodes},
        )
```

- [ ] **Step 7: Verify by running a 3-episode smoke test**

```bash
cd "C:\Users\27443\Desktop\Multi-Agent  VSGs"
C:\Users\27443\miniconda3\envs\andes_env\python.exe scenarios/kundur/train_simulink.py \
  --mode standalone --episodes 3 --resume none 2>&1 | tail -20
```

Then verify artifacts were created:

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -c "
from pathlib import Path
import json
log_dir = Path('results/sim_kundur/logs/standalone')
for fname in ['metrics.jsonl', 'events.jsonl', 'latest_state.json']:
    p = log_dir / fname
    print(fname, ':', 'EXISTS' if p.exists() else 'MISSING')
    if p.exists() and fname.endswith('.jsonl'):
        lines = p.read_text().strip().split('\n')
        print('  lines:', len(lines))
        print('  first:', json.loads(lines[0]))
"
```

Expected: all 3 files exist, metrics.jsonl has 3 lines.

- [ ] **Step 8: Commit**

```bash
git add scenarios/kundur/train_simulink.py
git commit -m "feat(kundur): integrate ArtifactWriter — metrics.jsonl + events.jsonl + latest_state.json"
```

---

## Task 5: Integrate ArtifactWriter into NE39 Simulink Training

**Files:**
- Modify: `scenarios/new_england/train_simulink.py`

> ⚠️ Apply this task only after the current NE39 run5 completes or is stopped.
> Do NOT apply to a running training process.

- [ ] **Step 1: Apply identical changes as Task 4 to scenarios/new_england/train_simulink.py**

The NE39 training script has the same structure. Apply Steps 1–6 from Task 4 verbatim, substituting:
- `N_AGENTS` is 8 (from NE39 config)
- `env.N_ESS` is 8
- The log dir will be `results/sim_ne39/logs/<mode>/`
- Import is from `scenarios.new_england.config_simulink` (already in the script)

The code changes are identical character-for-character; only the import path at the top differs.

- [ ] **Step 2: Verify with 3-episode standalone smoke test**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe scenarios/new_england/train_simulink.py \
  --mode standalone --episodes 3 --resume none 2>&1 | tail -20
```

Check:
```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -c "
from pathlib import Path; import json
log_dir = Path('results/sim_ne39/logs/standalone')
for f in ['metrics.jsonl','events.jsonl','latest_state.json']:
    p = log_dir / f
    print(f, ':', 'EXISTS' if p.exists() else 'MISSING')
"
```

- [ ] **Step 3: Commit**

```bash
git add scenarios/new_england/train_simulink.py
git commit -m "feat(ne39): integrate ArtifactWriter — mirrors Kundur artifact contract"
```

---

## Task 6: End-to-End Verdict Smoke Test

**Verify the full pipeline works on existing or freshly-generated data.**

- [ ] **Step 1: Run evaluate_run.py on Kundur standalone run (3-episode data)**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe utils/evaluate_run.py \
  --log-dir results/sim_kundur/logs/standalone \
  --contract scenarios/contracts/sim_kundur.json
```

Expected output (3 episodes = FAIL due to insufficient data):
```
==================================================
  Verdict: FAIL
  Episodes evaluated: 3
  • Insufficient data: only 3 episodes (need ≥ 50)
==================================================
  Saved to: results/sim_kundur/logs/standalone/verdict.json
```

- [ ] **Step 2: Run all tests together**

```bash
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest \
  tests/test_artifact_writer.py tests/test_evaluate_run.py -v
```

Expected: 14 tests pass, 0 fail.

- [ ] **Step 3: Final commit**

```bash
git add scenarios/contracts/
git commit -m "chore(phase1): wire up end-to-end smoke test for artifact contract pipeline"
```

---

## Self-Review

**Spec coverage check:**

| Requirement | Task |
|---|---|
| Unified run identity (single source of truth per run) | Task 2 (ArtifactWriter) + Task 4/5 (integration) |
| JSONL append-mode metrics (not single rewritten JSON) | Task 2 |
| Events log for alerts + checkpoints | Task 4 Step 4 |
| Atomic latest_state.json snapshot | Task 2 |
| Scenario contract with quality thresholds | Task 1 |
| Automatic PASS/MARGINAL/FAIL verdict | Task 3 |
| Backward compat: training_log.json still written | Not broken — training_log.json writes unchanged |
| NE39 support | Task 5 |

**Placeholder scan:** None found. All code blocks are complete and runnable.

**Type consistency:**
- `ArtifactWriter.log_metric(episode: int, data: dict)` — used consistently in Task 4/5
- `ArtifactWriter.log_event(episode: int, event_type: str, data: dict)` — used consistently
- `compute_verdict(rows: list[dict], thresholds: dict) -> EvaluationResult` — matches test calls
- `load_metrics(log_dir: Path | str) -> list[dict]` — matches test fixture usage
- `EvaluationResult.verdict: Verdict` (enum) — consistent in all tests

**Risk flag:** Task 4 Step 4 accesses `monitor._trigger_history` (private attribute).
This is safe since `TrainingMonitor` is internal code you own, but note it if you refactor the monitor class later.
