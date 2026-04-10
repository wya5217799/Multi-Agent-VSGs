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
            "reward_trend_slope_marginal": 0,
            "reward_trend_slope_fail": -5,
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
            "reward": -5000.0 + i * 30,
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
        {"reward": -1000.0 - i * 100,
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
        {"reward": -8000.0 + i * 20,
         "alpha": 0.15,
         "eval_reward": -8000.0,
         "physics": {"max_freq_dev_hz": 1.5, "mean_freq_dev_hz": 0.8,
                     "settled": (i % 8 == 0)}}  # settled_rate = 0.125
        for i in range(120)
    ]
    _write_metrics(tmp_run_dir / "metrics.jsonl", rows)
    with tempfile.TemporaryDirectory() as cd:
        contract = _make_contract(cd)
    result = compute_verdict(load_metrics(tmp_run_dir), contract["quality_thresholds"])
    # Criterion breakdown for this data:
    # 1. Reward trend: -8000 + i*20 → positive slope → pass
    # 2. Eval reward: -8000 (>= -10000 pass threshold) → pass
    # 3. Settled rate: 1/8 = 0.125 (between 0.10 marginal and 0.30 pass) → marginal
    # 4. Freq dev: 0.8 Hz (< 2.0 pass threshold) → pass
    # 5. Alpha: 0.15 (in [0.001, 4.5]) → pass
    # Net: 1 marginal (settled_rate), 0 fails → MARGINAL
    assert result.verdict == Verdict.MARGINAL


# ── load_contract ─────────────────────────────────────────────────────────────

def test_load_contract_reads_json(tmp_run_dir):
    contract_path = tmp_run_dir / "sim_kundur.json"
    data = {"scenario_id": "sim_kundur", "quality_thresholds": {}}
    contract_path.write_text(json.dumps(data))
    loaded = load_contract(contract_path)
    assert loaded["scenario_id"] == "sim_kundur"


def test_verdict_pass_end_to_end_via_load_contract(tmp_run_dir):
    """Full pipeline: write contract file → load_contract → compute_verdict."""
    rows = [
        {
            "reward": -5000.0 + i * 30,
            "alpha": 0.1,
            "eval_reward": -4000.0,
            "physics": {"max_freq_dev_hz": 1.0, "mean_freq_dev_hz": 0.5, "settled": True},
        }
        for i in range(120)
    ]
    _write_metrics(tmp_run_dir / "metrics.jsonl", rows)
    # Write contract to disk and load through load_contract (not in-memory dict)
    contract_path = tmp_run_dir / "sim_kundur.json"
    contract_path.write_text(json.dumps({
        "scenario_id": "sim_kundur",
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
            "reward_trend_slope_marginal": 0,
            "reward_trend_slope_fail": -5,
        },
    }), encoding="utf-8")
    contract = load_contract(contract_path)
    result = compute_verdict(load_metrics(tmp_run_dir), contract["quality_thresholds"])
    assert result.verdict == Verdict.PASS


def test_verdict_handles_null_eval_reward_on_last_row(tmp_run_dir):
    """eval_reward=None on the last row must not raise (run stopped mid-interval)."""
    rows = []
    for i in range(101):
        row = {
            "reward": -5000.0 + i * 20,
            "alpha": 0.1,
            "physics": {"max_freq_dev_hz": 1.0, "mean_freq_dev_hz": 0.5, "settled": True},
        }
        # Set eval_reward every 50 episodes; last row (i=100) gets None
        if i % 50 == 0 and i < 100:
            row["eval_reward"] = -4000.0
        else:
            row["eval_reward"] = None
        rows.append(row)
    _write_metrics(tmp_run_dir / "metrics.jsonl", rows)
    with tempfile.TemporaryDirectory() as cd:
        contract = _make_contract(cd)
    # Must not raise despite eval_reward=None on last row
    result = compute_verdict(load_metrics(tmp_run_dir), contract["quality_thresholds"])
    assert result.verdict in {Verdict.PASS, Verdict.MARGINAL, Verdict.FAIL}


def test_verdict_fails_when_eval_and_alpha_missing(tmp_run_dir):
    """A run with missing contract-gated eval/alpha fields must not pass."""
    rows = [
        {
            "reward": -5000.0 + i * 30,
            "physics": {"max_freq_dev_hz": 1.0, "mean_freq_dev_hz": 0.5, "settled": True},
        }
        for i in range(120)
    ]
    _write_metrics(tmp_run_dir / "metrics.jsonl", rows)
    with tempfile.TemporaryDirectory() as cd:
        contract = _make_contract(cd)
    result = compute_verdict(load_metrics(tmp_run_dir), contract["quality_thresholds"])
    assert result.verdict == Verdict.FAIL
    assert any("eval_reward" in r for r in result.reasons)
    assert any("alpha" in r.lower() for r in result.reasons)


def test_verdict_uses_training_rows_and_eval_metric_rows(tmp_run_dir):
    """Rows marked type=eval must feed eval_reward without inflating episode count."""
    rows = []
    for i in range(120):
        rows.append({
            "type": "train",
            "reward": -5000.0 + i * 30,
            "alpha": 0.1,
            "physics": {
                "max_freq_dev_hz": 1.0,
                "mean_freq_dev_hz": 0.5,
                "settled": True,
            },
        })
    rows.append({
        "type": "eval",
        "eval_reward": -4000.0,
        "physics": {
            "max_freq_dev_hz": 0.8,
            "mean_freq_dev_hz": 0.4,
            "settled": True,
            "max_power_swing": 0.05,
        },
        "per_agent_rewards": {"0": -3900.0, "1": -4100.0},
        "disturbance": {"kind": "load_step", "magnitude": 2.0},
    })
    _write_metrics(tmp_run_dir / "metrics.jsonl", rows)
    with tempfile.TemporaryDirectory() as cd:
        contract = _make_contract(cd)

    result = compute_verdict(load_metrics(tmp_run_dir), contract["quality_thresholds"])

    assert result.verdict == Verdict.PASS
    assert result.episode_count == 120
    assert result.metrics["last_eval_reward"] == pytest.approx(-4000.0)
