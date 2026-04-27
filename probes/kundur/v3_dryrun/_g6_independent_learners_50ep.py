"""G6 isolated experiment — 4 independent SACAgents (paper Algorithm 1).

Single axis change vs P4.3+G5 setup: shared-weights SAC -> MultiAgentSACManager.
Everything else IDENTICAL:
  - PHI_H = PHI_D = 1e-5, PHI_F = 100 (Z1 winner)
  - KUNDUR_DISTURBANCE_TYPE = pm_step_proxy_random_gen
  - --scenario-set train (cycle k mod 100)
  - BUFFER_SIZE = 10000 (paper Table I)
  - 50 ep, seed=42

Sequence:
  1. 5-ep smoke (verify env step + multi-agent buffers + update + save/load)
  2. 50-ep G6 train on train manifest
  3. paper_eval best.pt on test manifest
  4. Compare vs:
       - no_control_test  (= -4.198)
       - P4.3+G5 ep50.pt  (shared-weights baseline at same 50-ep mark)

Boundaries: only --independent-learners flag; no Simulink/reward/PHI/dist/
manifest/paper_eval semantic edits.
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

# Baselines for comparison
NO_CTRL_TEST = -4.197763008978613
P43G5_EP50_TEST = None  # will fill from p43_ckpt_ep50_test_metrics.json if available

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


def _smoke_5ep() -> dict:
    cmd = [
        PYTHON_EXE,
        str(REPO_ROOT / "scenarios" / "kundur" / "train_simulink.py"),
        "--mode", "simulink",
        "--episodes", "5",
        "--resume", "none",
        "--seed", str(SEED),
        "--save-interval", "5",
        "--eval-interval", "100",  # skip eval inside 5-ep smoke
        "--scenario-set", "train",
        "--independent-learners",
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
    print("\n=== G6 SMOKE: 5-ep (multi-agent train) ===")
    t0 = time.time()
    rc, wall = _run("g6_smoke_5ep", cmd, extra)
    print(f"  smoke exit={rc} wall={wall:.0f}s")
    return {"exit": rc, "wall_s": wall, "t0": t0}


def _train_50ep() -> dict:
    cmd = [
        PYTHON_EXE,
        str(REPO_ROOT / "scenarios" / "kundur" / "train_simulink.py"),
        "--mode", "simulink",
        "--episodes", "50",
        "--resume", "none",
        "--seed", str(SEED),
        "--save-interval", "50",
        "--eval-interval", "50",
        "--scenario-set", "train",
        "--independent-learners",
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
    print("\n=== G6 TRAIN: 50-ep on train manifest (independent learners) ===")
    t0 = time.time()
    rc, wall = _run("g6_50ep_train", cmd, extra)
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


def _eval_test(best_pt: Path) -> dict:
    out_metrics = HARNESS_DIR / "g6_50ep_test_metrics.json"
    cmd = [
        PYTHON_EXE, "-m", "evaluation.paper_eval",
        "--checkpoint", str(best_pt),
        "--seed-base", str(SEED),
        "--policy-label", "g6_50ep_test",
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
    print("\n=== G6 EVAL: best.pt on test manifest ===")
    rc, wall = _run("g6_50ep_eval", cmd, extra)
    print(f"  eval exit={rc} wall={wall:.0f}s")
    if not out_metrics.exists():
        return {"error": "no metrics", "exit": rc, "wall_s": wall}
    with out_metrics.open("r", encoding="utf-8") as f:
        m = json.load(f)
    cum = m["cumulative_reward_global_rf"]["unnormalized"]
    summary = m["summary"]
    print(f"  G6 ddic_test cum_unnorm = {cum:+.4f}")
    return {"metrics": m, "cum_unnorm": cum, "summary": summary, "exit": rc, "wall_s": wall}


def _load_p43_ep50_baseline() -> float | None:
    p = HARNESS_DIR / "p43_ckpt_ep50_test_metrics.json"
    if not p.exists():
        return None
    try:
        with p.open("r", encoding="utf-8") as f:
            m = json.load(f)
        return float(m["cumulative_reward_global_rf"]["unnormalized"])
    except Exception:
        return None


def main() -> int:
    global P43G5_EP50_TEST
    P43G5_EP50_TEST = _load_p43_ep50_baseline()

    print("G6 isolated experiment — 4 independent SACAgents")
    print(f"  no_ctrl_test baseline = {NO_CTRL_TEST:+.4f}")
    print(f"  P4.3+G5 ep50 (shared) = {P43G5_EP50_TEST}")
    print(f"  PHI_H/D/F = {PHI_H} / {PHI_D} / {PHI_F}")
    print(f"  KUNDUR_DISTURBANCE_TYPE = pm_step_proxy_random_gen")
    print(f"  scenario-set = train, BUFFER_SIZE=10000, seed={SEED}")

    # Step 1: 5-ep smoke
    smoke = _smoke_5ep()
    if smoke["exit"] != 0:
        print(f"SMOKE FAILED exit={smoke['exit']} — aborting before 50-ep train")
        return 1
    smoke_run_dir = _latest_run_dir(smoke["t0"])
    smoke_ckpt = (smoke_run_dir / "checkpoints" / "ep5.pt") if smoke_run_dir else None
    if smoke_ckpt and smoke_ckpt.exists():
        print(f"  smoke ckpt: {smoke_ckpt}")
    else:
        print(f"  WARNING: no smoke ep5.pt found; smoke may have crashed silently")

    # Step 2: 50-ep G6 train
    train_rec = _train_50ep()
    if train_rec["exit"] != 0:
        print(f"TRAIN FAILED exit={train_rec['exit']}")
        return 1
    run_dir = _latest_run_dir(train_rec["t0"])
    if run_dir is None:
        print("ERROR: no train run_dir found")
        return 1
    best_pt = run_dir / "checkpoints" / "best.pt"
    if not best_pt.exists():
        for fb in ("ep50.pt", "final.pt"):
            p = run_dir / "checkpoints" / fb
            if p.exists():
                best_pt = p
                break
    if not best_pt.exists():
        print(f"ERROR: no checkpoint in {run_dir}/checkpoints/")
        return 1
    print(f"  using checkpoint: {best_pt.name}")

    # Step 3: paper_eval on test manifest
    eval_rec = _eval_test(best_pt)
    if eval_rec.get("error"):
        print(f"EVAL FAILED: {eval_rec['error']}")
        return 1
    g6_cum = eval_rec["cum_unnorm"]
    delta_vs_no_ctrl = (g6_cum - NO_CTRL_TEST) / abs(NO_CTRL_TEST) * 100.0
    delta_vs_p43 = (
        (g6_cum - P43G5_EP50_TEST) / abs(P43G5_EP50_TEST) * 100.0
        if P43G5_EP50_TEST is not None else None
    )

    summary = {
        "schema_version": 1,
        "phase": "G6",
        "config": {
            "scenario_set_train": "v3_paper_train_100.json",
            "scenario_set_test": "v3_paper_test_50.json",
            "episodes": 50,
            "seed": SEED,
            "PHI_H": PHI_H, "PHI_D": PHI_D, "PHI_F": PHI_F,
            "KUNDUR_DISTURBANCE_TYPE": "pm_step_proxy_random_gen",
            "BUFFER_SIZE_total": 10000,
            "agent": "MultiAgentSACManager (4 independent SACAgents)",
        },
        "results": {
            "g6_test_cum_unnorm": g6_cum,
            "no_control_test_cum_unnorm": NO_CTRL_TEST,
            "p43g5_ep50_test_cum_unnorm": P43G5_EP50_TEST,
            "delta_pct_vs_no_control": delta_vs_no_ctrl,
            "delta_pct_vs_p43g5_shared_ep50": delta_vs_p43,
            "passed_vs_no_control": g6_cum > NO_CTRL_TEST,
            "improved_vs_p43g5_shared_ep50": (
                (g6_cum > P43G5_EP50_TEST) if P43G5_EP50_TEST is not None else None
            ),
        },
        "checkpoint_used": str(best_pt),
        "run_dir": str(run_dir),
        "smoke_run_dir": str(smoke_run_dir) if smoke_run_dir else None,
        "wall": {
            "smoke_5ep_s": smoke["wall_s"],
            "train_50ep_s": train_rec["wall_s"],
            "eval_s": eval_rec["wall_s"],
        },
        "g6_eval_summary": eval_rec.get("summary"),
    }
    out_path = HARNESS_DIR / "g6_aggregate_summary.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nG6 aggregate -> {out_path}")
    print(f"\n{'config':30s} {'cum_unnorm':>12s} {'delta_pct':>10s}")
    print("-" * 60)
    print(f"{'no_control_test':30s} {NO_CTRL_TEST:>12.4f} {0.0:>+9.2f}%")
    if P43G5_EP50_TEST is not None:
        d = (P43G5_EP50_TEST - NO_CTRL_TEST) / abs(NO_CTRL_TEST) * 100.0
        print(f"{'P4.3+G5 ep50 (shared)':30s} {P43G5_EP50_TEST:>12.4f} {d:>+9.2f}%")
    print(f"{'G6 50-ep (independent)':30s} {g6_cum:>12.4f} {delta_vs_no_ctrl:>+9.2f}%")
    print()
    print(f"G6 vs no_control       : {delta_vs_no_ctrl:+.2f}% ({'BETTER' if g6_cum > NO_CTRL_TEST else 'WORSE'})")
    if delta_vs_p43 is not None:
        print(f"G6 vs P4.3+G5 (shared) : {delta_vs_p43:+.2f}% ({'BETTER' if g6_cum > P43G5_EP50_TEST else 'WORSE'})")
    return 0 if g6_cum > NO_CTRL_TEST else 1


if __name__ == "__main__":
    sys.exit(main())
