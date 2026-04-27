"""Z1 — SG-side Pm-step proxy sweep with paper-style global-r_f gate.

Per phase5_r2_phi_sweep_verdict.md root cause: ESS-side Pm-step disturbance
gives ESS H/D no leverage. Z1 routes the disturbance through SG sources
(G1/G2/G3) instead, simulating paper's "external perturbation propagates to
ESS via the network" topology. ESS H/D adjustments now have system-level
leverage on freq response.

Sequence:
  1. Establish new no-control baseline under SG-side disturbance (50 scenarios,
     seed=42, KUNDUR_DISTURBANCE_TYPE=pm_step_proxy_random_gen).
  2. Train + paper_eval candidates: phi_b1 (1e-4/1e-4/100, control), phi_h_d_lower
     (1e-5/1e-5/100, R2 best). Compare against the new no-control baseline.
  3. STOP at first PASS (DDIC cum_unnorm > no_control cum_unnorm).

Wall projection:
  - SG-side no-control eval ~8 min
  - per candidate: 50-ep train ~10 min + eval ~8 min ≈ 18 min
  - 2 candidates ≈ 36 min + 8 min baseline = ~45 min total

Hard boundaries: only env dispatch + config edits. No build / .slx / IC /
runtime.mat / bridge / helper / reward / LoadStep / NE39 / 2000-ep training.
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

EPISODES_PER_RUN = 50
SEED = 42

CANDIDATES: list[tuple[str, str, str, str, str]] = [
    # (tag, PHI_H, PHI_D, PHI_F, rationale)
    (
        "z1_phi_b1",
        "0.0001", "0.0001", "100.0",
        "control: same PHI as P4.2 winner but SG-side disturbance",
    ),
    (
        "z1_phi_h_d_lower",
        "0.00001", "0.00001", "100.0",
        "R2 best PHI (least r_h dominance) under SG-side disturbance",
    ),
]


def _run_subproc(label: str, cmd: list[str], extra_env: dict[str, str]) -> tuple[int, float]:
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


def _eval_no_control_sg() -> dict:
    out_metrics = HARNESS_DIR / "z1_no_control_sg_metrics.json"
    cmd = [
        PYTHON_EXE, "-m", "evaluation.paper_eval",
        "--n-scenarios", "50",
        "--seed-base", str(SEED),
        "--policy-label", "z1_no_control_sg",
        "--output-json", str(out_metrics),
        "--disturbance-mode", "gen",
    ]
    extra = {
        "KUNDUR_MODEL_PROFILE": str(
            REPO_ROOT / "scenarios" / "kundur" / "model_profiles" / "kundur_cvs_v3.json"
        ),
        "KUNDUR_DISTURBANCE_TYPE": "pm_step_proxy_random_gen",
    }
    print("\n=== Z1 BASELINE: no_control under SG-side disturbance ===")
    rc, wall = _run_subproc("z1_no_control_sg", cmd, extra)
    print(f"  exit={rc} wall={wall:.0f}s")
    if not out_metrics.exists():
        return {"error": "no metrics", "exit": rc, "wall_s": wall}
    with out_metrics.open("r", encoding="utf-8") as f:
        m = json.load(f)
    cum = m["cumulative_reward_global_rf"]["unnormalized"]
    print(f"  no_control_sg cum_unnorm = {cum:+.4f}")
    return {"metrics": m, "cum_unnorm": cum, "exit": rc, "wall_s": wall}


def _train_candidate(tag: str, phi_h: str, phi_d: str, phi_f: str) -> dict:
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
    extra = {
        "KUNDUR_MODEL_PROFILE": str(
            REPO_ROOT / "scenarios" / "kundur" / "model_profiles" / "kundur_cvs_v3.json"
        ),
        "KUNDUR_DISTURBANCE_TYPE": "pm_step_proxy_random_gen",
        "KUNDUR_PHI_H": phi_h,
        "KUNDUR_PHI_D": phi_d,
        "KUNDUR_PHI_F": phi_f,
    }
    print(f"\n=== Z1 TRAIN: {tag} ===")
    print(f"  PHI_H={phi_h} PHI_D={phi_d} PHI_F={phi_f}")
    t0 = time.time()
    rc, wall = _run_subproc(f"{tag}_train", cmd, extra)
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


def _eval_candidate(tag: str, best_pt: Path) -> dict:
    out_metrics = HARNESS_DIR / f"{tag}_eval_metrics.json"
    cmd = [
        PYTHON_EXE, "-m", "evaluation.paper_eval",
        "--checkpoint", str(best_pt),
        "--n-scenarios", "50",
        "--seed-base", str(SEED),
        "--policy-label", f"{tag}_best",
        "--output-json", str(out_metrics),
        "--disturbance-mode", "gen",
    ]
    extra = {
        "KUNDUR_MODEL_PROFILE": str(
            REPO_ROOT / "scenarios" / "kundur" / "model_profiles" / "kundur_cvs_v3.json"
        ),
        "KUNDUR_DISTURBANCE_TYPE": "pm_step_proxy_random_gen",
    }
    print(f"  --- Z1 EVAL: {tag} ---")
    rc, wall = _run_subproc(f"{tag}_eval", cmd, extra)
    print(f"  eval exit={rc} wall={wall:.0f}s")
    if not out_metrics.exists():
        return {"error": "no metrics", "exit": rc, "wall_s": wall}
    with out_metrics.open("r", encoding="utf-8") as f:
        m = json.load(f)
    cum = m["cumulative_reward_global_rf"]["unnormalized"]
    print(f"  eval cum_unnorm = {cum:+.4f}")
    return {"metrics": m, "cum_unnorm": cum, "exit": rc, "wall_s": wall}


def main() -> int:
    print("Z1 SG-side Pm-step proxy sweep")
    baseline = _eval_no_control_sg()
    if baseline.get("error"):
        print(f"BASELINE EVAL FAILED: {baseline['error']}")
        return 1
    no_ctrl_sg = baseline["cum_unnorm"]
    print(f"BASELINE: no_control_sg cum_unnorm = {no_ctrl_sg:+.4f}")

    results = []
    pass_idx = -1
    for i, (tag, ph, pd, pf, rat) in enumerate(CANDIDATES):
        train_rec = _train_candidate(tag, ph, pd, pf)
        run_dir = _latest_run_dir(train_rec["t0"])
        if run_dir is None:
            print(f"  [{tag}] no run_dir found")
            results.append({"tag": tag, "phi_h": ph, "phi_d": pd, "phi_f": pf,
                            "train": train_rec, "eval": None,
                            "pass": False, "fail_reason": "no_run_dir"})
            continue
        ckpt = run_dir / "checkpoints" / "best.pt"
        if not ckpt.exists():
            for fb in ("final.pt", "ep50.pt"):
                p = run_dir / "checkpoints" / fb
                if p.exists():
                    ckpt = p
                    break
        if not ckpt.exists():
            print(f"  [{tag}] no checkpoint found")
            results.append({"tag": tag, "phi_h": ph, "phi_d": pd, "phi_f": pf,
                            "train": train_rec, "eval": None,
                            "pass": False, "fail_reason": "no_checkpoint"})
            continue
        eval_rec = _eval_candidate(tag, ckpt)
        if eval_rec.get("error"):
            results.append({"tag": tag, "phi_h": ph, "phi_d": pd, "phi_f": pf,
                            "train": train_rec, "eval": eval_rec,
                            "pass": False, "fail_reason": "eval_error"})
            continue
        ddic_cum = eval_rec["cum_unnorm"]
        passed = ddic_cum > no_ctrl_sg
        delta_pct = (ddic_cum - no_ctrl_sg) / abs(no_ctrl_sg) * 100.0
        sign_str = "BETTER" if passed else "WORSE"
        print(f"  GATE: {tag} DDIC={ddic_cum:+.4f} vs no_ctrl_sg={no_ctrl_sg:+.4f} "
              f"= {delta_pct:+.1f}% ({sign_str}) PASS={passed}")
        rec = {
            "tag": tag, "phi_h": ph, "phi_d": pd, "phi_f": pf, "rationale": rat,
            "checkpoint": str(ckpt), "run_dir": str(run_dir),
            "train": train_rec, "eval": eval_rec,
            "ddic_cum_unnorm": ddic_cum, "no_ctrl_sg_cum_unnorm": no_ctrl_sg,
            "delta_pct_vs_no_ctrl_sg": delta_pct,
            "pass": passed,
        }
        results.append(rec)
        if passed:
            pass_idx = i
            print(f"\nZ1 STOP: {tag} PASSED — no further candidates needed.")
            break

    aggregate = {
        "schema_version": 1,
        "disturbance_mode": "gen",
        "no_control_sg_cum_unnorm": no_ctrl_sg,
        "n_candidates_run": len(results),
        "pass_index": pass_idx,
        "winning_tag": results[pass_idx]["tag"] if pass_idx >= 0 else None,
        "candidates": results,
        "baseline_metrics": baseline.get("metrics"),
    }
    agg_path = HARNESS_DIR / "z1_aggregate_metrics.json"
    with agg_path.open("w", encoding="utf-8") as f:
        json.dump(aggregate, f, indent=2, default=str)
    print(f"\nZ1 aggregate -> {agg_path}")
    print(f"Z1 complete: pass_index={pass_idx} winning_tag={aggregate['winning_tag']}")
    return 0 if pass_idx >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
