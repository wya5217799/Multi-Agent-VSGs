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

from engine.run_schema import RunStatus, read_run_status
from utils.run_protocol import find_latest_run, get_run_dir

# Repo root: two levels up from engine/
_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONTRACTS_DIR = _REPO_ROOT / "scenarios" / "contracts"


def _contract_path(scenario_id: str) -> Path:
    # Contract files are named sim_<scenario_id>.json (e.g. sim_kundur.json).
    return _CONTRACTS_DIR / f"sim_{scenario_id}.json"


def _log_dir(scenario_id: str, run_id: str) -> Path:
    """Convention: results/sim_<scenario_id>/runs/<run_id>/logs/"""
    return _REPO_ROOT / "results" / f"sim_{scenario_id}" / "runs" / run_id / "logs"


def training_evaluate_run(scenario_id: str, run_id: str) -> dict[str, Any]:
    """Evaluate a completed training run and emit a structured verdict.

    Args:
        scenario_id: "kundur" or "ne39" (same convention as training_status)
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
        scenario_id: "kundur" or "ne39"
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

    status = read_run_status(run_dir) or RunStatus()
    episodes_done = status.episodes_done
    episodes_total = status.episodes_total
    progress_pct = status.progress_pct

    # Prefer logs_dir from status (written by training script); fall back to
    # conventional run_dir/logs for runs started before this field was added.
    logs_dir_path = status.logs_path(run_dir)

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
        except (json.JSONDecodeError, OSError, KeyError, ValueError):
            pass  # missing or malformed snapshot is non-fatal

    return {
        "scenario_id": scenario_id,
        "run_id": status.run_id,
        "status": status.status,
        "episodes_done": episodes_done,
        "episodes_total": episodes_total,
        "progress_pct": round(progress_pct, 2),
        "last_reward": status.last_reward,
        "last_updated": status.last_updated,
        "started_at": status.started_at,
        "finished_at": status.finished_at,
        "error": status.error,
        "stop_reason": status.stop_reason,
        "last_eval_reward": status.last_eval_reward,
        "logs_dir": str(logs_dir_path),
        "run_dir": str(run_dir),
        "latest_snapshot": latest_snapshot,
    }


def _diagnose_physics(
    run_dir: Path,
    status: RunStatus,
) -> dict[str, Any]:
    """Read metrics.jsonl and detect early-termination / stuck-at-cap patterns.

    Returns a dict with:
      - pattern: None | "early_termination" | "freq_capped" | "no_progress"
      - evidence: human-readable summary
      - recommendation: suggested fix
    """
    logs_dir = status.logs_path(run_dir)
    metrics_path = logs_dir / "metrics.jsonl"

    if not metrics_path.exists():
        return {"pattern": None, "evidence": "metrics.jsonl not found", "recommendation": None}

    rows: list[dict[str, Any]] = []
    for line in metrics_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    if not rows:
        return {"pattern": None, "evidence": "metrics.jsonl is empty", "recommendation": None}

    # metrics.jsonl rows written by train_simulink.py use a nested "physics" key:
    #   {"episode": N, "reward": ..., "physics": {"max_freq_dev_hz": ..., "settled": ...}}
    freq_devs = [
        r["physics"]["max_freq_dev_hz"] for r in rows
        if r.get("physics", {}).get("max_freq_dev_hz") is not None
    ]
    rewards = [r.get("reward") for r in rows if r.get("reward") is not None]
    settled = [
        r["physics"]["settled"] for r in rows
        if r.get("physics", {}).get("settled") is not None
    ]

    if not freq_devs:
        return {"pattern": None, "evidence": "no physics.max_freq_dev_hz in metrics", "recommendation": None}

    n = len(freq_devs)
    cap_threshold = 14.5  # Hz — within 0.5 Hz of the 15 Hz termination guard
    early_window = min(10, n)
    cap_early = sum(1 for f in freq_devs[:early_window] if f >= cap_threshold)
    cap_total = sum(1 for f in freq_devs if f >= cap_threshold)
    settled_total = sum(1 for s in settled if s)

    # Pattern 1: every episode hits the freq cap from ep0
    if cap_early == early_window and cap_total >= 0.9 * n:
        mean_reward = sum(rewards) / len(rewards) if rewards else float("nan")
        return {
            "pattern": "early_termination",
            "evidence": (
                f"{cap_total}/{n} episodes hit max_freq_dev >= {cap_threshold} Hz "
                f"(including all first {early_window}). Mean reward={mean_reward:.0f}. "
                f"Settled episodes: {settled_total}/{n}."
            ),
            "recommendation": (
                "Physics mismatch: disturbance is too large for D_min damping. "
                "Check DIST_MAX vs OMEGA_TERM_THRESHOLD (15 Hz). "
                "Also verify omega integrator saturation limits in the Simulink model "
                "(IntW block UpperSaturationLimit should match the Python guard)."
            ),
        }

    # Pattern 2: freq always capped but not from ep0 (model saturates after warmup)
    if cap_total >= 0.8 * n and cap_early < early_window:
        return {
            "pattern": "freq_capped",
            "evidence": (
                f"{cap_total}/{n} episodes hit max_freq_dev >= {cap_threshold} Hz, "
                f"but first {early_window} episodes varied. Possible policy collapse."
            ),
            "recommendation": (
                "Check alpha entropy coefficient — if alpha_min is too low, "
                "policy may collapse to deterministic action that saturates omega. "
                "Also check reward normalization."
            ),
        }

    # Pattern 3: no progress — reward flat and zero settled_rate
    if len(rewards) >= 20 and settled_total == 0:
        reward_range = max(rewards) - min(rewards) if rewards else 0.0
        if reward_range < max(abs(min(rewards, default=0)) * 0.05, 1.0):
            return {
                "pattern": "no_progress",
                "evidence": (
                    f"Reward range over {n} episodes: {reward_range:.0f} "
                    f"(< 5% of |min|). settled_rate=0 throughout."
                ),
                "recommendation": (
                    "RL not learning. Check buffer warmup (WARMUP_STEPS), "
                    "observation normalization (NORM_FREQ, NORM_P), "
                    "and that env.DIST_MAX matches config (not hardcoded)."
                ),
            }

    return {"pattern": None, "evidence": f"No anomalous pattern detected in {n} episodes.", "recommendation": None}


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
        "run_id": None,
        "event_count": 0,
        "alerts": [],
        "monitor_stop": None,
        "eval_rewards": [],
        "checkpoints": [],
        "training_start": None,
        "training_end": None,
        "physics_diagnosis": {"pattern": None, "evidence": "no run found", "recommendation": None},
    }

    if run_dir is None:
        return _empty

    status = read_run_status(run_dir) or RunStatus()
    logs_dir_path = status.logs_path(run_dir)

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

    actual_run_id = status.run_id or run_dir.name

    training_start_events = [e for e in events if e.get("type") == "training_start"]
    training_end_events = [e for e in events if e.get("type") == "training_end"]
    monitor_stop_events = [e for e in events if e.get("type") == "monitor_stop"]

    # Group alerts by check type to avoid O(N) blowup in the return payload.
    # Real runs can fire hundreds of identical "freq_out_of_range" warns — one
    # summary row per distinct (check, action) pair is all the caller needs.
    _alert_groups: dict[tuple[str, str | None], dict[str, Any]] = {}
    for _ae in events:
        if _ae.get("type") != "monitor_alert":
            continue
        _rule = _ae.get("rule")
        _check = _rule.get("check", str(_rule)) if isinstance(_rule, dict) else str(_rule)
        _action = _rule.get("action") if isinstance(_rule, dict) else None
        _ep = _ae.get("episode") or 0
        _key = (_check, _action)
        if _key not in _alert_groups:
            _alert_groups[_key] = {
                "check": _check,
                "action": _action,
                "count": 0,
                "first_episode": _ep,
                "last_episode": _ep,
            }
        _grp = _alert_groups[_key]
        _grp["count"] += 1
        _grp["first_episode"] = min(_grp["first_episode"], _ep)
        _grp["last_episode"] = max(_grp["last_episode"], _ep)

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
    }
