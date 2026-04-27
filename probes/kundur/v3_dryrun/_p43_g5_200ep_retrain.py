"""Phase 4.3 (G3 wire-in) + G5 (BUFFER_SIZE=10000) — 200-ep retrain on
fixed v3_paper_train_100 manifest, evaluated on v3_paper_test_50 manifest.

Uses Z1 winner config:
  KUNDUR_DISTURBANCE_TYPE = pm_step_proxy_random_gen
  KUNDUR_PHI_H/D = 1e-5
  KUNDUR_PHI_F = 100
  seed = 42

Sequence:
  1. Eval no-control on test manifest (paper-faithful zero-action baseline).
  2. Train 200 ep on train manifest (cycles scenario k mod 100).
  3. Eval best.pt on test manifest.
  4. Report DDIC vs no-control on the SAME test manifest.

Wall projection:
  - no_ctrl test eval ~8 min
  - 200-ep train ~40-50 min (Z1 phase showed 12-14 s/ep at smaller buffer
    expect similar; BUFFER_SIZE=10000 vs 100000 should not slow things)
  - ddic test eval ~8 min
  - total ~1-1.2 hr
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

EPISODES = 200
SEED = 42
PHI_H = "0.00001"
PHI_D = "0.00001"
PHI_F = "100.0"


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


def _eval_no_ctrl_test() -> dict:
    out_metrics = HARNESS_DIR / "p43_no_control_test_metrics.json"
    cmd = [
        PYTHON_EXE, "-m", "evaluation.paper_eval",
        "--seed-base", str(SEED),
        "--policy-label", "p43_no_control_test",
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
    print("\n=== P4.3 BASELINE: no_control on test manifest ===")
    rc, wall = _run("p43_no_control_test", cmd, extra)
    print(f"  exit={rc} wall={wall:.0f}s")
    if not out_metrics.exists():
        return {"error": "no metrics", "exit": rc, "wall_s": wall}
    with out_metrics.open("r", encoding="utf-8") as f:
        m = json.load(f)
    cum = m["cumulative_reward_global_rf"]["unnormalized"]
    print(f"  no_control_test cum_unnorm = {cum:+.4f}")
    return {"metrics": m, "cum_unnorm": cum, "exit": rc, "wall_s": wall}


def _train_200ep() -> dict:
    cmd = [
        PYTHON_EXE,
        str(REPO_ROOT / "scenarios" / "kundur" / "train_simulink.py"),
        "--mode", "simulink",
        "--episodes", str(EPISODES),
        "--resume", "none",
        "--seed", str(SEED),
        "--save-interval", "50",
        "--eval-interval", "50",
        "--scenario-set", "train",
    ]
    extra = {
        "KUNDUR_MODEL_PROFILE": str(
            REPO_ROOT / "scenarios" / "kundur" / "model_profiles" / "kundur_cvs_v3.json"
        ),
        "KUNDUR_DISTURBANCE_TYPE": "pm_step_proxy_random_gen",
        "KUNDUR_PHI_H": PHI_H,
        "KUNDUR_PHI_D": PHI_D,
        "KUNDUR_PHI_F": PHI_F,
    }
    print(f"\n=== P4.3 TRAIN: 200 ep on train manifest ===")
    print(f"  PHI_H={PHI_H} PHI_D={PHI_D} PHI_F={PHI_F}")
    print(f"  scenario-set=train, BUFFER_SIZE=10000 (G5)")
    t0 = time.time()
    rc, wall = _run("p43_200ep_train", cmd, extra)
    print(f"  train exit={rc} wall={wall:.0f}s ({wall/60:.1f} min)")
    return {"exit": rc, "wall_s": wall, "t0": t0}


def _latest_run_dir(after_ts: float) -> Path | None:
    runs_root = REPO_ROOT / "results" / "sim_kundur" / "runs"
    cands = []
    for child in runs_root.iterdir():
        if not child.is_dir() or not child.name.startswith("kundur_simulink_"):
            continue
        try:
            mtime = child.stat().st_mtime
        except OSError:
            continue
        if mtime >= after_ts - 5.0:
            cands.append((mtime, child))
    if not cands:
        return None
    cands.sort()
    return cands[-1][1]


def _eval_ddic_test(best_pt: Path) -> dict:
    out_metrics = HARNESS_DIR / "p43_ddic_test_metrics.json"
    cmd = [
        PYTHON_EXE, "-m", "evaluation.paper_eval",
        "--checkpoint", str(best_pt),
        "--seed-base", str(SEED),
        "--policy-label", "p43_ddic_phi_h_d_lower_200ep_test",
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
    print(f"\n=== P4.3 EVAL: DDIC best.pt on test manifest ===")
    rc, wall = _run("p43_ddic_test", cmd, extra)
    print(f"  exit={rc} wall={wall:.0f}s")
    if not out_metrics.exists():
        return {"error": "no metrics", "exit": rc, "wall_s": wall}
    with out_metrics.open("r", encoding="utf-8") as f:
        m = json.load(f)
    cum = m["cumulative_reward_global_rf"]["unnormalized"]
    print(f"  ddic_test cum_unnorm = {cum:+.4f}")
    return {"metrics": m, "cum_unnorm": cum, "exit": rc, "wall_s": wall}


def main() -> int:
    print("Phase 4.3 + G5 — 200-ep retrain on fixed manifests")

    # Step 1: no-control baseline on test manifest
    nc = _eval_no_ctrl_test()
    if nc.get("error"):
        print(f"BASELINE FAILED: {nc['error']}")
        return 1
    nc_cum = nc["cum_unnorm"]

    # Step 2: 200-ep train on train manifest
    train_rec = _train_200ep()
    run_dir = _latest_run_dir(train_rec["t0"])
    if run_dir is None:
        print("ERROR: no train run_dir found")
        return 1
    best_pt = run_dir / "checkpoints" / "best.pt"
    if not best_pt.exists():
        for fb in ("ep200.pt", "ep150.pt", "ep100.pt", "ep50.pt", "final.pt"):
            p = run_dir / "checkpoints" / fb
            if p.exists():
                best_pt = p
                break
    if not best_pt.exists():
        print(f"ERROR: no checkpoint in {run_dir}/checkpoints/")
        return 1
    print(f"  using checkpoint: {best_pt.name}")

    # Step 3: DDIC eval on test manifest
    dd = _eval_ddic_test(best_pt)
    if dd.get("error"):
        print(f"EVAL FAILED: {dd['error']}")
        return 1
    dd_cum = dd["cum_unnorm"]

    # Step 4: report + write summary
    delta_pct = (dd_cum - nc_cum) / abs(nc_cum) * 100.0
    passed = dd_cum > nc_cum  # less negative = better
    sign_str = "BETTER" if passed else "WORSE"

    summary = {
        "schema_version": 1,
        "phase": "4.3+G5",
        "config": {
            "scenario_set_train": "v3_paper_train_100.json",
            "scenario_set_test": "v3_paper_test_50.json",
            "episodes": EPISODES,
            "seed": SEED,
            "PHI_H": PHI_H, "PHI_D": PHI_D, "PHI_F": PHI_F,
            "KUNDUR_DISTURBANCE_TYPE": "pm_step_proxy_random_gen",
            "BUFFER_SIZE": 10000,
        },
        "results": {
            "no_control_test_cum_unnorm": nc_cum,
            "ddic_test_cum_unnorm": dd_cum,
            "delta_pct_vs_no_control": delta_pct,
            "improvement_direction": sign_str,
            "passed": passed,
        },
        "checkpoint_used": str(best_pt),
        "run_dir": str(run_dir),
        "wall": {
            "no_ctrl_eval_s": nc["wall_s"],
            "train_s": train_rec["wall_s"],
            "ddic_eval_s": dd["wall_s"],
        },
        "raw": {
            "no_control_test": nc,
            "train": train_rec,
            "ddic_test": dd,
        },
    }
    out_path = HARNESS_DIR / "p43_g5_aggregate_summary.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nP4.3 + G5 aggregate -> {out_path}")
    print(f"no_control_test cum_unnorm = {nc_cum:+.4f}")
    print(f"ddic_test       cum_unnorm = {dd_cum:+.4f}")
    print(f"delta vs no_control        = {delta_pct:+.2f}% ({sign_str}) PASS={passed}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
