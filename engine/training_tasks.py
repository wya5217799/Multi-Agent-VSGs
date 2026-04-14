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

from utils.run_protocol import find_latest_run, get_run_dir, read_training_status

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


def training_status(scenario_id: str, run_id: str | None = None) -> dict[str, Any]:
    """Return a merged AI summary of the active (or most recent) training run.

    Tier 1 polling tool. Merges training_status.json (per-episode heartbeat)
    with logs/latest_state.json (~50-episode snapshot).

    Args:
        scenario_id: "kundur" or "ne39"
        run_id: specific run to inspect; if None, uses find_latest_run.

    Returns dict with lifecycle fields, heartbeat metrics, and latest_snapshot.
    """
    if run_id is not None:
        run_dir: Path | None = get_run_dir(scenario_id, run_id)
    else:
        run_dir = find_latest_run(scenario_id)
    if run_dir is None:
        return {
            "scenario_id": scenario_id,
            "status": "no_run",
            "run_id": None,
            "episodes_done": 0,
            "episodes_total": 0,
            "progress_pct": 0.0,
            "last_reward": None,
            "last_updated": None,
            "started_at": None,
            "finished_at": None,
            "error": None,
            "stop_reason": None,
            "last_eval_reward": None,
            "logs_dir": None,
            "run_dir": None,
            "latest_snapshot": None,
        }

    status = read_training_status(run_dir) or {}
    episodes_done = status.get("episodes_done", 0)
    episodes_total = status.get("episodes_total", 0)
    progress_pct = (episodes_done / episodes_total * 100) if episodes_total > 0 else 0.0

    # Prefer logs_dir from status (written by training script); fall back to
    # conventional run_dir/logs for runs started before this field was added.
    logs_dir_str = status.get("logs_dir")
    logs_dir_path = Path(logs_dir_str) if logs_dir_str else (run_dir / "logs")

    latest_snapshot = None
    latest_state_path = logs_dir_path / "latest_state.json"
    if latest_state_path.exists():
        try:
            state = json.loads(latest_state_path.read_text(encoding="utf-8"))
            snapshot_episode = state.get("episode", 0)
            latest_snapshot = {
                "episode": snapshot_episode,
                "reward_mean_50": state.get("reward_mean_50"),
                "alpha": state.get("alpha"),
                "settled_rate_50": state.get("settled_rate_50"),
                "buffer_size": state.get("buffer_size"),
                "snapshot_age_episodes": episodes_done - snapshot_episode,
                "snapshot_freshness": "~50-episode intervals",
            }
        except Exception:
            pass  # missing or malformed snapshot is non-fatal

    return {
        "scenario_id": scenario_id,
        "run_id": status.get("run_id"),
        "status": status.get("status"),
        "episodes_done": episodes_done,
        "episodes_total": episodes_total,
        "progress_pct": round(progress_pct, 2),
        "last_reward": status.get("last_reward"),
        "last_updated": status.get("last_updated"),
        "started_at": status.get("started_at"),
        "finished_at": status.get("finished_at"),
        "error": status.get("error"),
        "stop_reason": status.get("stop_reason"),
        "last_eval_reward": status.get("last_eval_reward"),
        "logs_dir": logs_dir_str,
        "run_dir": str(run_dir),
        "latest_snapshot": latest_snapshot,
    }


def training_diagnose(
    scenario_id: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Parse events.jsonl for structured anomaly diagnosis.

    Tier 2 tool — invoke only when training_status reveals an anomaly.

    Args:
        scenario_id: "kundur" or "ne39"
        run_id: specific run to diagnose; if None, uses find_latest_run.

    Returns structured report with alerts, eval trajectory, monitor_stop info.
    """
    if run_id is None:
        run_dir = find_latest_run(scenario_id)
    else:
        run_dir = get_run_dir(scenario_id, run_id)

    _empty: dict[str, Any] = {
        "scenario_id": scenario_id,
        "run_id": run_id or "unknown",
        "event_count": 0,
        "alerts": [],
        "monitor_stop": None,
        "eval_rewards": [],
        "checkpoints": [],
        "training_start": None,
        "training_end": None,
    }

    if run_dir is None:
        return _empty

    status = read_training_status(run_dir) or {}
    logs_dir_str = status.get("logs_dir")
    logs_dir_path = Path(logs_dir_str) if logs_dir_str else (run_dir / "logs")

    events_path = logs_dir_path / "events.jsonl"
    events: list[dict[str, Any]] = []
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    actual_run_id = status.get("run_id") or run_dir.name

    training_start_events = [e for e in events if e.get("type") == "training_start"]
    training_end_events = [e for e in events if e.get("type") == "training_end"]
    monitor_stop_events = [e for e in events if e.get("type") == "monitor_stop"]

    return {
        "scenario_id": scenario_id,
        "run_id": actual_run_id,
        "event_count": len(events),
        "alerts": [
            {"episode": e.get("episode"), "rule": e.get("rule")}
            for e in events if e.get("type") == "monitor_alert"
        ],
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
    }
