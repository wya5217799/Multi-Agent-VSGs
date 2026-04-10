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
    train_rows = [r for r in rows if r.get("type", "train") != "eval"]
    n = len(train_rows)
    computed["episode_count"] = n

    # ── Guard: insufficient data ──────────────────────────────────────────────
    if n < 50:
        return EvaluationResult(
            verdict=Verdict.FAIL,
            reasons=[f"Insufficient data: only {n} episodes (need >= 50)"],
            metrics=computed,
            episode_count=n,
        )

    window = min(thresholds.get("reward_trend_window", 100), n)
    recent = train_rows[-window:]

    # ── Extract reward series ─────────────────────────────────────────────────
    rewards = [r["reward"] for r in recent if "reward" in r]
    computed["reward_mean_recent"] = float(np.mean(rewards)) if rewards else None
    computed["reward_trend_slope"] = _linear_trend(rewards) if len(rewards) >= 2 else 0.0

    if not rewards:
        return EvaluationResult(
            verdict=Verdict.FAIL,
            reasons=["reward field missing from all recent records; metrics.jsonl may be malformed"],
            metrics=computed,
            episode_count=n,
        )

    # ── Extract eval rewards (optional) ──────────────────────────────────────
    eval_rewards = [r["eval_reward"] for r in rows
                    if r.get("eval_reward") is not None]
    last_eval = float(eval_rewards[-1]) if eval_rewards else None
    computed["last_eval_reward"] = last_eval
    if last_eval is None and (
        "eval_reward_pass" in thresholds or "eval_reward_marginal" in thresholds
    ):
        scores_missing_eval = True
    else:
        scores_missing_eval = False

    # ── Extract alpha series ──────────────────────────────────────────────────
    alphas = [r["alpha"] for r in recent if r.get("alpha") is not None]
    mean_alpha = float(np.mean(alphas)) if alphas else None
    computed["mean_alpha_recent"] = mean_alpha
    if mean_alpha is None and ("alpha_min" in thresholds or "alpha_max" in thresholds):
        scores_missing_alpha = True
    else:
        scores_missing_alpha = False

    # ── Extract physics ───────────────────────────────────────────────────────
    physics_rows = [r["physics"] for r in recent if "physics" in r]
    settled_flags = [p["settled"] for p in physics_rows if "settled" in p]
    freq_devs = [p.get("mean_freq_dev_hz", p.get("max_freq_dev_hz", 0.0))
                 for p in physics_rows]
    if not settled_flags:
        criteria_settled: str | None = "marginal"
        reasons.append("No physics/settled data found; settled_rate cannot be assessed")
        settled_rate = None
    else:
        criteria_settled = None
        settled_rate = float(np.mean(settled_flags))
    mean_freq_dev = float(np.mean(freq_devs)) if freq_devs else None
    computed["settled_rate_recent"] = settled_rate
    computed["mean_freq_dev_hz_recent"] = mean_freq_dev

    # ── Score each criterion ──────────────────────────────────────────────────
    scores: list[str] = []

    # 1. Reward trend
    slope = computed["reward_trend_slope"]
    thr_trend_marg = thresholds.get("reward_trend_slope_marginal", 0)
    thr_trend_fail = thresholds.get("reward_trend_slope_fail", -5)
    if slope > thr_trend_marg:
        scores.append("pass")
    elif slope > thr_trend_fail:
        scores.append("marginal")
        reasons.append(f"Reward trend flat or slightly negative (slope={slope:.2f}/ep)")
    else:
        scores.append("fail")
        reasons.append(f"Reward diverging (slope={slope:.2f}/ep)")

    # 2. Eval reward (if available)
    if scores_missing_eval:
        scores.append("fail")
        reasons.append("eval_reward missing despite configured eval reward thresholds")
    elif last_eval is not None:
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
    if criteria_settled is not None:
        # No data — already recorded as marginal in reasons above
        scores.append(criteria_settled)
    else:
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
            reasons.append(f"Freq dev marginal ({mean_freq_dev:.2f} Hz, pass <= {thr_fd_pass:.2f})")
        else:
            scores.append("fail")
            reasons.append(f"Freq dev above marginal ({mean_freq_dev:.2f} Hz > {thr_fd_marg:.2f})")

    # 5. Alpha health
    if scores_missing_alpha:
        scores.append("fail")
        reasons.append("alpha missing despite configured alpha thresholds")
    elif mean_alpha is not None:
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
    out_path.write_text(json.dumps(out_data, indent=2), encoding="utf-8")

    print(f"\n{'='*50}")
    print(f"  Verdict: {result.verdict.value}")
    print(f"  Episodes evaluated: {result.episode_count}")
    for r in result.reasons:
        print(f"  - {r}")
    print(f"{'='*50}")
    print(f"  Saved to: {out_path}")


if __name__ == "__main__":
    main()
