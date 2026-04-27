"""R2 — PHI re-sweep with paper-style global-r_f gate.

Per P5.1 verdict + R1 audit: P4.2's `phi_b1` winner is actually WORSE than
zero-action no-control by 19 % under paper-style global r_f formula. Reward
formula is correct (R1); fault is PHI weighting. R2 sweeps 3 candidates
designed to push r_h share away from 70 %.

For each candidate:
  1. 50-ep train (KUNDUR_DISTURBANCE_TYPE=pm_step_proxy_random_bus,
     KUNDUR_PHI_H/D/F overridden via env vars).
  2. paper_eval on best.pt (50 deterministic scenarios, seed=42).
  3. Compare cum_unnorm vs fixed no-control baseline = -7.4838 (from P5.1).
  4. PASS if cum_unnorm > -7.4838 (less freq deviation = closer to 0 = better).

Stopping rule: first PASS = R2 winner. If 3 fail, halt + diagnostic.

Wall projection: 50-ep train ~10-12 min + eval ~16 min = ~28 min/candidate;
3 candidates ~1.4 hr. Sequential.

Hard boundaries: only PHI env var changes. No build / .slx / IC / runtime.mat /
bridge / helper / env-dispatch / reward / LoadStep / NE39 / SAC arch edits.
No 200-ep / 2000-ep training launches.
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

# Fixed no-control baseline from P5.1 (50 scenarios, seed=42).
NO_CONTROL_CUM_UNNORM = -7.483751385085248
GATE_DEFAULT_THRESHOLD = NO_CONTROL_CUM_UNNORM  # DDIC must be > this (less negative)

# Candidates to sweep — skip phi_b1 (already known: -8.90 = WORSE).
CANDIDATES: list[tuple[str, str, str, str, str]] = [
    # (tag, PHI_H, PHI_D, PHI_F, rationale)
    (
        "phi_h_d_lower",
        "0.00001", "0.00001", "100.0",
        "10x lower PHI_H/PHI_D vs phi_b1 — frees policy from r_h dominance",
    ),
    (
        "phi_f_500",
        "0.0001", "0.0001", "500.0",
        "5x higher PHI_F vs phi_b1 — boosts r_f weight relative to r_h",
    ),
    (
        "phi_paper_scaled",
        "0.01", "0.01", "100.0",
        "100x higher PHI_H/D vs phi_b1 — paper-style symmetric weighting",
    ),
]

EPISODES_PER_RUN = 50
SEED = 42


def _run_train(tag: str, phi_h: str, phi_d: str, phi_f: str, rationale: str) -> dict:
    out_log = HARNESS_DIR / f"r2_{tag}_train_stdout.txt"
    out_err = HARNESS_DIR / f"r2_{tag}_train_stderr.txt"

    cmd = [
        PYTHON_EXE,
        str(REPO_ROOT / "scenarios" / "kundur" / "train_simulink.py"),
        "--mode", "simulink",
        "--episodes", str(EPISODES_PER_RUN),
        "--resume", "none",
        "--seed", str(SEED),
        "--save-interval", "50",
        "--eval-interval", "50",
    ]
    env = os.environ.copy()
    env["KUNDUR_MODEL_PROFILE"] = str(
        REPO_ROOT / "scenarios" / "kundur" / "model_profiles" / "kundur_cvs_v3.json"
    )
    env["KUNDUR_DISTURBANCE_TYPE"] = "pm_step_proxy_random_bus"
    env["KUNDUR_PHI_H"] = phi_h
    env["KUNDUR_PHI_D"] = phi_d
    env["KUNDUR_PHI_F"] = phi_f
    env["PYTHONUNBUFFERED"] = "1"

    print(f"\n=== R2 TRAIN: {tag} ===")
    print(f"  PHI_H={phi_h} PHI_D={phi_d} PHI_F={phi_f}")
    print(f"  rationale: {rationale}")
    t0 = time.time()
    with out_log.open("w", encoding="utf-8") as fout, out_err.open("w", encoding="utf-8") as ferr:
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, stdout=fout, stderr=ferr)
    wall = time.time() - t0
    print(f"  train exit={proc.returncode} wall={wall:.0f}s ({wall/60:.1f} min)")
    return {"tag": tag, "exit_code": proc.returncode, "wall_s": wall, "stdout": str(out_log), "stderr": str(out_err)}


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


def _run_paper_eval(tag: str, best_pt: Path) -> dict:
    out_metrics = HARNESS_DIR / f"r2_{tag}_eval_metrics.json"
    out_log = HARNESS_DIR / f"r2_{tag}_eval_stdout.txt"
    out_err = HARNESS_DIR / f"r2_{tag}_eval_stderr.txt"

    cmd = [
        PYTHON_EXE, "-m", "evaluation.paper_eval",
        "--checkpoint", str(best_pt),
        "--n-scenarios", "50",
        "--seed-base", str(SEED),
        "--policy-label", f"r2_{tag}_best",
        "--output-json", str(out_metrics),
    ]
    env = os.environ.copy()
    env["KUNDUR_MODEL_PROFILE"] = str(
        REPO_ROOT / "scenarios" / "kundur" / "model_profiles" / "kundur_cvs_v3.json"
    )
    # Paper eval probes set per-scenario disturbance_type so this default is safe.
    env["KUNDUR_DISTURBANCE_TYPE"] = "pm_step_proxy_random_bus"
    env["PYTHONUNBUFFERED"] = "1"

    print(f"  --- R2 EVAL: {tag} ---")
    t0 = time.time()
    with out_log.open("w", encoding="utf-8") as fout, out_err.open("w", encoding="utf-8") as ferr:
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, stdout=fout, stderr=ferr)
    wall = time.time() - t0
    print(f"  eval exit={proc.returncode} wall={wall:.0f}s ({wall/60:.1f} min)")
    if not out_metrics.exists():
        return {"tag": tag, "error": "no eval metrics emitted", "exit_code": proc.returncode, "wall_s": wall}
    with out_metrics.open("r", encoding="utf-8") as f:
        m = json.load(f)
    cum = m["cumulative_reward_global_rf"]["unnormalized"]
    print(f"  cum_unnorm = {cum:+.4f}  (no_control = {NO_CONTROL_CUM_UNNORM:+.4f})")
    return {"tag": tag, "exit_code": proc.returncode, "wall_s": wall, "metrics": m}


def _gate_pass(eval_result: dict) -> tuple[bool, str]:
    if eval_result.get("error"):
        return False, f"eval_error:{eval_result['error']}"
    cum = eval_result["metrics"]["cumulative_reward_global_rf"]["unnormalized"]
    if cum > NO_CONTROL_CUM_UNNORM:
        return True, f"DDIC cum_unnorm={cum:+.4f} > no_control {NO_CONTROL_CUM_UNNORM:+.4f}"
    return False, f"DDIC cum_unnorm={cum:+.4f} ≤ no_control {NO_CONTROL_CUM_UNNORM:+.4f} (worse)"


def main() -> int:
    print("R2 PHI sweep with paper-style gate")
    print(f"  no_control baseline cum_unnorm = {NO_CONTROL_CUM_UNNORM:+.6f}")
    print(f"  gate: DDIC cum_unnorm > {NO_CONTROL_CUM_UNNORM:+.4f}  (less negative = less freq dev)")
    print(f"  candidates: {[c[0] for c in CANDIDATES]}")

    results: list[dict] = []
    pass_idx = -1
    for i, (tag, ph, pd, pf, rat) in enumerate(CANDIDATES):
        train_t0 = time.time()
        train_rec = _run_train(tag, ph, pd, pf, rat)
        run_dir = _latest_run_dir(train_t0)
        train_rec["run_dir"] = str(run_dir) if run_dir else None
        if run_dir is None:
            print(f"  [{tag}] ERROR: train run_dir not found, aborting candidate")
            results.append({"tag": tag, "phi_h": ph, "phi_d": pd, "phi_f": pf, "train": train_rec, "eval": None, "pass": False, "fail_reason": "no_run_dir"})
            continue
        best_pt = run_dir / "checkpoints" / "best.pt"
        if not best_pt.exists():
            # Fallback: final.pt or ep50.pt
            for cand in ("final.pt", "ep50.pt"):
                p = run_dir / "checkpoints" / cand
                if p.exists():
                    best_pt = p
                    break
        if not best_pt.exists():
            print(f"  [{tag}] ERROR: no checkpoint found in {run_dir}/checkpoints/")
            results.append({"tag": tag, "phi_h": ph, "phi_d": pd, "phi_f": pf, "train": train_rec, "eval": None, "pass": False, "fail_reason": "no_checkpoint"})
            continue
        print(f"  best/fallback ckpt: {best_pt.name}")

        eval_rec = _run_paper_eval(tag, best_pt)
        eval_rec["checkpoint_used"] = str(best_pt)

        passed, reason = _gate_pass(eval_rec)
        print(f"  GATE: PASS={passed}  ({reason})")
        rec = {
            "tag": tag, "phi_h": ph, "phi_d": pd, "phi_f": pf, "rationale": rat,
            "train": train_rec, "eval": eval_rec,
            "pass": passed, "gate_reason": reason,
        }
        results.append(rec)
        if passed:
            pass_idx = i
            print(f"\nR2 STOP: {tag} PASSED — no further candidates needed.")
            break

    # Aggregate
    aggregate = {
        "schema_version": 1,
        "no_control_baseline_cum_unnorm": NO_CONTROL_CUM_UNNORM,
        "gate_threshold": GATE_DEFAULT_THRESHOLD,
        "n_candidates_run": len(results),
        "pass_index": pass_idx,
        "winning_tag": results[pass_idx]["tag"] if pass_idx >= 0 else None,
        "candidates": results,
    }
    agg_path = HARNESS_DIR / "r2_aggregate_metrics.json"
    with agg_path.open("w", encoding="utf-8") as f:
        json.dump(aggregate, f, indent=2, default=str)
    print(f"\nR2 aggregate -> {agg_path}")
    print(f"R2 complete: pass_index={pass_idx} winning_tag={aggregate['winning_tag']}")
    return 0 if pass_idx >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
