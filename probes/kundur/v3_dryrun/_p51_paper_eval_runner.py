"""P5.1 — paper-style evaluator runner.

Evaluates 2 policies on 50 deterministic scenarios:
  1. zero-action no-control baseline (policy=None, action=0)
  2. best.pt from kundur_simulink_20260427_013758 (the phi_b1 overnight)

Emits per-policy metrics JSON + an aggregate verdict-input JSON that compares
both against paper baselines (DDIC -8.04, no-control -15.20) under all 3
normalization variants (unnormalized / per-M / per-M·N).

Each eval ~9 min wall (cold-start + 50 scenarios × ~10 s); total ~18 min.
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
HARNESS_DIR.mkdir(parents=True, exist_ok=True)

BEST_CKPT = (
    REPO_ROOT
    / "results"
    / "sim_kundur"
    / "runs"
    / "kundur_simulink_20260427_013758"
    / "checkpoints"
    / "best.pt"
)


def _run_eval(label: str, checkpoint: str | None, n_scenarios: int = 50, seed: int = 42) -> dict:
    out_json = HARNESS_DIR / f"p51_{label}_metrics.json"
    out_log = HARNESS_DIR / f"p51_{label}_stdout.txt"
    out_err = HARNESS_DIR / f"p51_{label}_stderr.txt"

    cmd = [
        PYTHON_EXE, "-m", "evaluation.paper_eval",
        "--n-scenarios", str(n_scenarios),
        "--seed-base", str(seed),
        "--policy-label", label,
        "--output-json", str(out_json),
    ]
    if checkpoint:
        cmd += ["--checkpoint", str(checkpoint)]

    env = os.environ.copy()
    env["KUNDUR_MODEL_PROFILE"] = str(
        REPO_ROOT / "scenarios" / "kundur" / "model_profiles" / "kundur_cvs_v3.json"
    )
    env["KUNDUR_DISTURBANCE_TYPE"] = "pm_step_proxy_random_bus"
    env["PYTHONUNBUFFERED"] = "1"

    print(f"\n=== P5.1 EVAL: {label} ===")
    print(f"  cmd: {' '.join(cmd)}")
    t0 = time.time()
    with out_log.open("w", encoding="utf-8") as fout, out_err.open("w", encoding="utf-8") as ferr:
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, stdout=fout, stderr=ferr)
    wall = time.time() - t0
    print(f"  exit_code={proc.returncode} wall={wall:.0f}s ({wall/60:.1f} min)")
    if not out_json.exists():
        return {"label": label, "error": "no metrics emitted", "exit_code": proc.returncode, "wall_s": wall}
    with out_json.open("r", encoding="utf-8") as f:
        m = json.load(f)
    print(f"  cumulative_unnorm = {m['cumulative_reward_global_rf']['unnormalized']:+.4f}")
    print(f"  paper_DDIC        = {m['cumulative_reward_global_rf']['paper_target_unnormalized']:+.4f}")
    print(f"  paper_no_control  = {m['cumulative_reward_global_rf']['paper_no_control_unnormalized']:+.4f}")
    return m


def main() -> int:
    if not BEST_CKPT.exists():
        print(f"ERROR: best.pt not found at {BEST_CKPT}")
        return 1

    results: dict = {}

    # 1) zero-action baseline (paper "no-control" equivalent)
    no_ctrl = _run_eval("no_control", checkpoint=None)
    results["no_control"] = no_ctrl

    # 2) DDIC v3 = trained policy (best.pt at ep 549 of phi_b1 overnight)
    ddic = _run_eval("ddic_phi_b1_best", checkpoint=str(BEST_CKPT))
    results["ddic_phi_b1_best"] = ddic

    # Aggregate comparison
    cum_no = (no_ctrl.get("cumulative_reward_global_rf") or {}).get("unnormalized")
    cum_dd = (ddic.get("cumulative_reward_global_rf") or {}).get("unnormalized")
    paper_ddic = -8.04
    paper_no = -15.20

    summary = {
        "schema_version": 1,
        "n_scenarios": 50,
        "seed_base": 42,
        "policies": list(results.keys()),
        "cumulative_unnorm": {
            "v3_no_control": cum_no,
            "v3_ddic_phi_b1_best": cum_dd,
            "paper_no_control": paper_no,
            "paper_ddic": paper_ddic,
        },
        "ratios": {
            "v3_no_control_vs_paper_no_control": (cum_no / paper_no) if (cum_no is not None and paper_no) else None,
            "v3_ddic_vs_paper_ddic": (cum_dd / paper_ddic) if (cum_dd is not None and paper_ddic) else None,
            "v3_ddic_vs_v3_no_control": (cum_dd / cum_no) if (cum_dd and cum_no) else None,
            "paper_ddic_vs_paper_no_control": paper_ddic / paper_no,
        },
        "improvement_v3_ddic_over_v3_no_control_pct": (
            ((cum_no - cum_dd) / abs(cum_no)) * 100.0 if (cum_no and cum_dd is not None) else None
        ),
        "improvement_paper_ddic_over_paper_no_control_pct": ((paper_no - paper_ddic) / abs(paper_no)) * 100.0,
        "results": results,
    }
    summary_path = HARNESS_DIR / "p51_aggregate_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nP5.1 aggregate -> {summary_path}")
    print(f"v3 no_control unnorm = {cum_no!r}")
    print(f"v3 ddic       unnorm = {cum_dd!r}")
    print(f"paper DDIC           = {paper_ddic}")
    print(f"paper no-control     = {paper_no}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
