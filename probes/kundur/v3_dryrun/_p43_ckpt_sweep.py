"""P4.3 + G5 — checkpoint sweep on test manifest.

Run paper_eval on each saved checkpoint of the P4.3+G5 200-ep training run.
Compare DDIC cum_unnorm trajectory across (ep50, ep100, ep150, ep200, best,
final) on the v3_paper_test_50.json manifest. Identifies whether the
regression is over-training (early ckpts beat late ones) or floor-level
across all checkpoints (BUFFER=10000 root cause).

No re-training. ~5 × 8 min = ~40 min.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_EXE = r"C:\Users\27443\miniconda3\envs\andes_env\python.exe"
HARNESS_DIR = REPO_ROOT / "results" / "harness" / "kundur" / "cvs_v3_phase4"

CKPT_DIR = (
    REPO_ROOT
    / "results" / "sim_kundur" / "runs"
    / "kundur_simulink_20260427_133927" / "checkpoints"
)
SEED = 42
NO_CTRL_TEST = -4.197763008978613  # from p43_no_control_test_metrics.json

# Order matters: ep50, ep100, ep150, ep200, then best/final for context
CHECKPOINTS = [
    ("ep50",   "ep50.pt"),
    ("ep100",  "ep100.pt"),
    ("ep150",  "ep150.pt"),
    ("ep200",  "ep200.pt"),
    # best/final already evaluated as p43_ddic_test_metrics.json (-4.62);
    # re-eval not strictly needed but include for completeness via 'final'.
    ("final",  "final.pt"),
]


def _run(label: str, cmd: list[str], extra_env: dict[str, str]) -> tuple[int, float]:
    out_log = HARNESS_DIR / f"{label}_stdout.txt"
    out_err = HARNESS_DIR / f"{label}_stderr.txt"
    env = os.environ.copy()
    env.update(extra_env)
    env["PYTHONUNBUFFERED"] = "1"
    print(f"  cmd: {' '.join(cmd)}")
    t0 = time.time()
    with out_log.open("w", encoding="utf-8") as fout, out_err.open("w", encoding="utf-8") as ferr:
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, stdout=fout, stderr=ferr)
    return proc.returncode, time.time() - t0


def _eval(ckpt_label: str, ckpt_name: str) -> dict:
    ckpt_path = CKPT_DIR / ckpt_name
    out_metrics = HARNESS_DIR / f"p43_ckpt_{ckpt_label}_test_metrics.json"
    cmd = [
        PYTHON_EXE, "-m", "evaluation.paper_eval",
        "--checkpoint", str(ckpt_path),
        "--seed-base", str(SEED),
        "--policy-label", f"p43_ddic_{ckpt_label}_test",
        "--output-json", str(out_metrics),
        "--disturbance-mode", "gen",
        "--scenario-set", "test",
    ]
    extra = {
        "KUNDUR_MODEL_PROFILE": str(
            REPO_ROOT / "scenarios" / "kundur" / "model_profiles" / "kundur_cvs_v3.json"
        ),
        "KUNDUR_DISTURBANCE_TYPE": "pm_step_proxy_random_gen",
    }
    print(f"\n=== EVAL {ckpt_label} ({ckpt_name}) ===")
    rc, wall = _run(f"p43_ckpt_{ckpt_label}_test", cmd, extra)
    print(f"  exit={rc} wall={wall:.0f}s")
    if not out_metrics.exists():
        return {"label": ckpt_label, "error": "no metrics", "exit": rc, "wall_s": wall}
    with out_metrics.open("r", encoding="utf-8") as f:
        m = json.load(f)
    cum = m["cumulative_reward_global_rf"]["unnormalized"]
    summary = m["summary"]
    delta_pct = (cum - NO_CTRL_TEST) / abs(NO_CTRL_TEST) * 100.0
    sign_str = "BETTER" if cum > NO_CTRL_TEST else "WORSE"
    print(f"  cum_unnorm = {cum:+.4f}  vs no_ctrl_test={NO_CTRL_TEST:+.4f}  delta={delta_pct:+.2f}% ({sign_str})")
    print(f"  max|df| mean={summary['max_freq_dev_hz_mean']:.4f}  ROCOF mean={summary['rocof_hz_per_s_mean']:.3f}")
    return {
        "label": ckpt_label, "ckpt_name": ckpt_name,
        "cum_unnorm": cum,
        "max_freq_dev_hz_mean": summary["max_freq_dev_hz_mean"],
        "rocof_hz_per_s_mean": summary["rocof_hz_per_s_mean"],
        "settled_pct": summary["settled_pct"],
        "delta_pct_vs_no_ctrl": delta_pct,
        "exit": rc, "wall_s": wall,
    }


def main() -> int:
    print("P4.3+G5 checkpoint sweep on test manifest")
    print(f"  ckpt dir: {CKPT_DIR}")
    print(f"  no_ctrl_test baseline = {NO_CTRL_TEST:+.4f}")
    results = []
    for label, name in CHECKPOINTS:
        if not (CKPT_DIR / name).exists():
            print(f"  [{label}] missing {name}, skipping")
            continue
        r = _eval(label, name)
        results.append(r)

    aggregate = {
        "schema_version": 1,
        "no_ctrl_test_cum_unnorm": NO_CTRL_TEST,
        "ckpt_dir": str(CKPT_DIR),
        "checkpoints": results,
        "trajectory": [
            {"label": r["label"], "cum_unnorm": r.get("cum_unnorm"), "delta_pct": r.get("delta_pct_vs_no_ctrl")}
            for r in results
        ],
    }
    out_path = HARNESS_DIR / "p43_ckpt_sweep_summary.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(aggregate, f, indent=2, default=str)
    print(f"\nSweep summary -> {out_path}")
    print(f"\n{'ckpt':10s} {'cum_unnorm':>12s} {'delta_pct':>10s}  status")
    print("-" * 55)
    for r in results:
        status = ""
        if r.get("error"):
            status = f"ERROR: {r['error']}"
        elif r.get("cum_unnorm", 0) > NO_CTRL_TEST:
            status = "BETTER"
        else:
            status = "WORSE"
        print(f"{r['label']:10s} {r.get('cum_unnorm', 0):>12.4f} {r.get('delta_pct_vs_no_ctrl', 0):>+9.2f}%  {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
