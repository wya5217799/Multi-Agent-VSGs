"""
Verify convergence criteria for a new ANDES training seed per spec §5.

Usage:
    python3 scripts/verify_seed_convergence.py --seed 45

Checks:
1. total_rewards[-10:] mean / total_rewards[:10] mean ratio (convergence)
2. interrupted=false
3. TDS failures = 0 (requires training_log to have tds_failures field)
4. Action stability: not checked from log alone; requires checkpoint probe

Outputs pass/fail per criterion and overall verdict.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def check_seed(seed: int) -> dict:
    log_dir = ROOT / f"results/andes_phase4_noPHIabs_seed{seed}"
    log_path = log_dir / "training_log.json"

    result = {"seed": seed, "criteria": {}, "verdict": "UNKNOWN"}

    if not log_path.exists():
        result["verdict"] = "MISSING_LOG"
        result["error"] = str(log_path)
        return result

    with open(log_path) as f:
        d = json.load(f)

    rewards = d.get("total_rewards", [])
    interrupted = d.get("interrupted", True)
    ep_completed = d.get("episodes_completed", 0)
    total_steps = d.get("total_steps", 0)

    # Criterion 1: Reward improvement ratio
    if len(rewards) >= 20:
        first10_mean = float(np.mean(rewards[:10]))
        last10_mean = float(np.mean(rewards[-10:]))
        # ratio = |last10_mean| / |first10_mean| should be < 0.2
        if abs(first10_mean) < 1e-6:
            ratio = float("nan")
            c1_pass = False
            c1_note = "first10_mean near zero"
        else:
            ratio = abs(last10_mean) / abs(first10_mean)
            # spec says > 5x improvement = ratio < 0.2
            c1_pass = ratio < 0.2
            c1_note = f"ratio={ratio:.3f} (pass if <0.2)"
    else:
        ratio = float("nan")
        c1_pass = False
        c1_note = f"only {len(rewards)} episodes completed"

    result["criteria"]["c1_reward_improvement"] = {
        "pass": c1_pass,
        "note": c1_note,
        "first10_mean": float(np.mean(rewards[:10])) if len(rewards) >= 10 else None,
        "last10_mean": float(np.mean(rewards[-10:])) if len(rewards) >= 10 else None,
        "ratio": ratio,
    }

    # Criterion 2: Not interrupted
    c2_pass = not interrupted
    result["criteria"]["c2_not_interrupted"] = {
        "pass": c2_pass,
        "interrupted": interrupted,
        "ep_completed": ep_completed,
        "ep_planned": d.get("episodes_planned", 500),
    }

    # Criterion 3: TDS failures (if recorded in log)
    # training_log.json may not have tds_failures field; check if episode_rewards has consistent shape
    tds_failures = d.get("tds_failures", None)
    if tds_failures is None:
        c3_pass = None  # cannot verify from log alone
        c3_note = "tds_failures not in log; verify via agent_state probe"
    else:
        c3_pass = tds_failures == 0
        c3_note = f"tds_failures={tds_failures}"
    result["criteria"]["c3_tds_failures"] = {
        "pass": c3_pass,
        "note": c3_note,
    }

    # Criterion 4: Action stability (needs checkpoint probe; mark as DEFERRED)
    result["criteria"]["c4_action_stability"] = {
        "pass": None,
        "note": "DEFERRED — requires agent_state probe phase A1 (specialization)",
    }

    # Summary
    definite_failures = [
        k for k, v in result["criteria"].items()
        if v["pass"] is False
    ]
    if definite_failures:
        result["verdict"] = "FAIL"
        result["failed_criteria"] = definite_failures
    elif all(v["pass"] is True for k, v in result["criteria"].items() if v["pass"] is not None):
        result["verdict"] = "PASS_DEFERRED"  # some criteria deferred to probe
        result["note"] = "C3/C4 require probe verification"
    else:
        result["verdict"] = "PARTIAL"

    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, required=True)
    args = p.parse_args()

    result = check_seed(args.seed)
    print(json.dumps(result, indent=2))

    if result["verdict"] == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
