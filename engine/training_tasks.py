"""Training Control thin MCP surface.

This module wraps existing training artifact utilities for structured agent
access.  It must NOT import model repair code or mutate Simulink models.

MCP tools exposed here:
  training_evaluate_run   — compute PASS/MARGINAL/FAIL verdict for one run
  training_compare_runs   — compare verdicts and metrics across multiple runs
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Repo root: two levels up from engine/
_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONTRACTS_DIR = _REPO_ROOT / "scenarios" / "contracts"


def _contract_path(scenario_id: str) -> Path:
    return _CONTRACTS_DIR / f"{scenario_id}.json"


def _log_dir(scenario_id: str, run_id: str) -> Path:
    """Convention: results/<scenario_id>/runs/<run_id>/logs/simulink/"""
    return _REPO_ROOT / "results" / scenario_id / "runs" / run_id / "logs" / "simulink"


def training_evaluate_run(scenario_id: str, run_id: str) -> dict[str, Any]:
    """Evaluate a completed training run and emit a structured verdict.

    Args:
        scenario_id: e.g. "sim_kundur" or "sim_ne39"
        run_id: directory name under results/<scenario_id>/runs/

    Returns dict with keys: scenario_id, run_id, verdict, reasons, metrics,
    episode_count.  verdict is PASS | MARGINAL | FAIL.
    """
    from utils.evaluate_run import load_metrics, load_contract, compute_verdict

    contract_file = _contract_path(scenario_id)
    if not contract_file.exists():
        return {
            "scenario_id": scenario_id,
            "run_id": run_id,
            "verdict": "ERROR",
            "reasons": [f"Contract not found: {contract_file}"],
            "metrics": {},
            "episode_count": 0,
        }

    log_dir = _log_dir(scenario_id, run_id)
    contract = load_contract(contract_file)
    rows = load_metrics(log_dir)
    result = compute_verdict(rows, contract["quality_thresholds"])

    return {
        "scenario_id": scenario_id,
        "run_id": run_id,
        "log_dir": str(log_dir),
        "verdict": result.verdict.value,
        "reasons": result.reasons,
        "metrics": result.metrics,
        "episode_count": result.episode_count,
    }


def training_compare_runs(scenario_id: str, run_ids: list[str]) -> dict[str, Any]:
    """Compare verdicts and key metrics across multiple runs of the same scenario.

    Args:
        scenario_id: e.g. "sim_kundur"
        run_ids: list of run directory names to compare

    Returns dict with keys: scenario_id, comparisons (list of per-run summaries),
    best_run (run_id with highest verdict + episode_count).
    """
    _VERDICT_RANK = {"PASS": 2, "MARGINAL": 1, "FAIL": 0, "ERROR": -1}

    comparisons = []
    for run_id in run_ids:
        r = training_evaluate_run(scenario_id, run_id)
        comparisons.append({
            "run_id": run_id,
            "verdict": r["verdict"],
            "episode_count": r.get("episode_count", 0),
            "reward_mean_recent": r.get("metrics", {}).get("reward_mean_recent"),
            "settled_rate_recent": r.get("metrics", {}).get("settled_rate_recent"),
            "mean_freq_dev_hz_recent": r.get("metrics", {}).get("mean_freq_dev_hz_recent"),
            "reasons": r.get("reasons", []),
        })

    best = max(
        comparisons,
        key=lambda c: (
            _VERDICT_RANK.get(c["verdict"], -1),
            c["episode_count"],
        ),
    ) if comparisons else None

    return {
        "scenario_id": scenario_id,
        "comparisons": comparisons,
        "best_run": best["run_id"] if best else None,
    }
