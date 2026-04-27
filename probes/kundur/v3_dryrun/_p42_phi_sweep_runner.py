"""P4.2 — PHI sweep on kundur_cvs_v3 (Phase 4.2 of roadmap).

Sequentially launches 50-episode train_simulink.py runs with different PHI_H /
PHI_D candidates under KUNDUR_DISTURBANCE_TYPE=pm_step_proxy_random_bus.
Computes the 8 Phase 4 gate criteria per run and decides whether to continue.

Stopping rule (per plan §Gap 2 + user GO message):
  First run with r_f% in [3 %, 30 %] AND completion + numerical health + freq
  reach + SAC sanity all green = v3 default candidate. Within that band, prefer
  closest to 5 % target. If first 3 fail, extend to phi_asym_b. If 4 fail,
  optionally phi_paper.

Run output:
  results/sim_kundur/runs/kundur_simulink_<TIMESTAMP>/   (auto run_id per launch)
    ├── checkpoints/
    ├── logs/training_log.json
    ├── run_status.json
    └── events.jsonl

Aggregate output:
  results/harness/kundur/cvs_v3_phase4/p42_<run_tag>_metrics.json
  results/harness/kundur/cvs_v3_phase4/p42_<run_tag>_stdout.txt
  results/harness/kundur/cvs_v3_phase4/p42_aggregate_metrics.json
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))


PYTHON_EXE = r"C:\Users\27443\miniconda3\envs\andes_env\python.exe"
RUNS_ROOT = REPO_ROOT / "results" / "sim_kundur" / "runs"
HARNESS_DIR = REPO_ROOT / "results" / "harness" / "kundur" / "cvs_v3_phase4"

# Sweep candidates per roadmap §Gap 2.
# Order: regression baseline -> mild -> aggressive. Stop on first PASS.
SWEEP_CANDIDATES = [
    # (tag,                 PHI_H,    PHI_D,    rationale)
    ("phi_b1",              "0.0001", "0.0001", "regression check vs current Kundur v3 baseline"),
    ("phi_asym_a",          "0.001",  "0.0001", "P2.5c-recommended asymmetric (H lever 10x weighted)"),
    ("phi_paper_scaled",    "0.01",   "0.01",   "symmetric, factor-100 above B1 baseline"),
    # Conditional extensions (only if all 3 above fail):
    ("phi_asym_b",          "0.01",   "0.001",  "same H:D ratio, larger absolute"),
    ("phi_paper",           "1.0",    "1.0",    "paper literal weights"),
]

# Phase 4 gate criteria thresholds (per roadmap §3 table)
GATE_RFP_LO = 0.03
GATE_RFP_HI = 0.30
GATE_RFP_TARGET = 0.05
GATE_FREQ_LO_HZ = 0.05
GATE_FREQ_HI_HZ = 1.5
GATE_FREQ_PCT_REQ = 0.80
GATE_WALL_S = 60 * 60.0  # 60 min cap


def latest_run_dir(scenario_root: Path, after_ts: float) -> Path | None:
    """Find the run dir created after `after_ts`."""
    cands = []
    for child in scenario_root.iterdir():
        if not child.is_dir():
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


def parse_disturbance_log(stdout_path: Path) -> dict:
    """Count occurrences of (proxy_bus7) / (proxy_bus9) tags in disturbance lines."""
    counts = {"bus7": 0, "bus9": 0, "single_vsg": 0, "other": 0, "total": 0}
    if not stdout_path.exists():
        return counts
    try:
        with stdout_path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if "Pm step" not in line:
                    continue
                if "[Kundur-Simulink-CVS]" not in line:
                    continue
                counts["total"] += 1
                if "(proxy_bus7)" in line:
                    counts["bus7"] += 1
                elif "(proxy_bus9)" in line:
                    counts["bus9"] += 1
                elif "(pm_step_single_vsg)" in line:
                    counts["single_vsg"] += 1
                else:
                    counts["other"] += 1
    except Exception:
        pass
    return counts


def is_finite(x):
    import math
    try:
        return math.isfinite(float(x))
    except Exception:
        return False


def compute_gates(
    run_dir: Path,
    wall_s: float,
    bus_counts: dict,
    expected_episodes: int = 50,
) -> dict:
    """Compute Phase 4 gate metrics from a finished run dir."""
    log_path = run_dir / "logs" / "training_log.json"
    if not log_path.exists():
        return {"error": f"training_log.json not found at {log_path}"}
    try:
        with log_path.open("r", encoding="utf-8") as f:
            log = json.load(f)
    except Exception as exc:
        return {"error": f"failed to parse log: {exc}"}

    rewards = log.get("episode_rewards", [])
    physics = log.get("physics_summary", [])
    critic_losses = log.get("critic_losses", [])
    policy_losses = log.get("policy_losses", [])
    alphas = log.get("alphas", [])

    n_done = len(rewards)
    completion_ok = (n_done == expected_episodes)

    # Numerical health
    nan_inf_seen = False
    for r in rewards:
        if not is_finite(r):
            nan_inf_seen = True
            break
    if not nan_inf_seen:
        for p in physics:
            for k in ("max_freq_dev_hz", "mean_freq_dev_hz", "r_f", "r_h", "r_d"):
                if k in p and not is_finite(p[k]):
                    nan_inf_seen = True
                    break
            if nan_inf_seen:
                break

    # r_f% (last 25 ep)
    if physics:
        last25 = physics[-25:] if len(physics) >= 25 else physics
        sum_abs_rf = sum(abs(p.get("r_f", 0.0)) for p in last25)
        sum_abs_rh = sum(abs(p.get("r_h", 0.0)) for p in last25)
        sum_abs_rd = sum(abs(p.get("r_d", 0.0)) for p in last25)
        denom = sum_abs_rf + sum_abs_rh + sum_abs_rd
        rfp = (sum_abs_rf / denom) if denom > 0 else 0.0
        mean_abs_rf = sum_abs_rf / max(len(last25), 1)
        mean_abs_rh = sum_abs_rh / max(len(last25), 1)
        mean_abs_rd = sum_abs_rd / max(len(last25), 1)
    else:
        rfp = 0.0
        mean_abs_rf = mean_abs_rh = mean_abs_rd = 0.0

    rfp_in_band = (GATE_RFP_LO <= rfp <= GATE_RFP_HI)

    # Freq reach
    freq_pass_ct = 0
    freq_devs = []
    for p in physics:
        d = p.get("max_freq_dev_hz", 0.0)
        if not is_finite(d):
            continue
        freq_devs.append(d)
        if GATE_FREQ_LO_HZ <= d <= GATE_FREQ_HI_HZ:
            freq_pass_ct += 1
    freq_pct = freq_pass_ct / max(len(physics), 1)
    freq_pass = (freq_pct >= GATE_FREQ_PCT_REQ)
    freq_min = min(freq_devs) if freq_devs else 0.0
    freq_max = max(freq_devs) if freq_devs else 0.0
    freq_mean = (sum(freq_devs) / len(freq_devs)) if freq_devs else 0.0

    # SAC sanity (losses finite)
    sac_ok = (
        all(is_finite(x) for x in critic_losses)
        and all(is_finite(x) for x in policy_losses)
        and all(is_finite(x) for x in alphas)
    )

    # Wall time
    wall_ok = (wall_s <= GATE_WALL_S)

    # Learning trend
    if len(rewards) >= 50:
        first25 = rewards[:25]
        last25_r = rewards[-25:]
        first_mean = sum(first25) / 25
        last_mean = sum(last25_r) / 25
        improve = last_mean - first_mean
    else:
        first_mean = last_mean = improve = float("nan")

    # tds_failed count via run_status (may not be present in log per se)
    # We rely on completion + nan_inf_seen as a sufficient proxy here.

    # Disturbance bus distribution (from stdout parse)
    bus7 = bus_counts.get("bus7", 0)
    bus9 = bus_counts.get("bus9", 0)
    bus_total = bus7 + bus9
    bus7_frac = (bus7 / bus_total) if bus_total else 0.0
    # For 50 random_bus draws, expect ~0.5 ± 0.07 (binomial 50,0.5).

    return {
        "completion_ok": completion_ok,
        "n_episodes_done": n_done,
        "n_episodes_expected": expected_episodes,
        "nan_inf_seen": nan_inf_seen,
        "rfp_pct": rfp * 100.0,  # percentage
        "rfp_target_pct": GATE_RFP_TARGET * 100.0,
        "rfp_band_pct": [GATE_RFP_LO * 100.0, GATE_RFP_HI * 100.0],
        "rfp_in_band": rfp_in_band,
        "mean_abs_rf": mean_abs_rf,
        "mean_abs_rh": mean_abs_rh,
        "mean_abs_rd": mean_abs_rd,
        "freq_pct_in_band": freq_pct,
        "freq_pass": freq_pass,
        "freq_dev_min_hz": freq_min,
        "freq_dev_max_hz": freq_max,
        "freq_dev_mean_hz": freq_mean,
        "sac_losses_finite": sac_ok,
        "n_critic_loss_records": len(critic_losses),
        "n_alpha_records": len(alphas),
        "wall_time_s": wall_s,
        "wall_ok": wall_ok,
        "first25_mean_reward": first_mean,
        "last25_mean_reward": last_mean,
        "improve_last25_minus_first25": improve,
        "bus_distribution": {
            "bus7_count": bus7,
            "bus9_count": bus9,
            "single_vsg_count": bus_counts.get("single_vsg", 0),
            "total": bus_counts.get("total", 0),
            "bus7_fraction_of_proxies": bus7_frac,
        },
    }


def overall_gate_pass(g: dict) -> tuple[bool, list[str]]:
    """Return (pass, fail_reasons). Decision criteria per plan §3 + user GO."""
    fails = []
    if "error" in g:
        return False, [f"metrics_error:{g['error']}"]
    if not g.get("completion_ok"):
        fails.append(
            f"completion {g.get('n_episodes_done')}/{g.get('n_episodes_expected')}"
        )
    if g.get("nan_inf_seen"):
        fails.append("nan_inf_in_metrics")
    if not g.get("rfp_in_band"):
        fails.append(f"rfp_pct={g.get('rfp_pct'):.2f}% out of [{g['rfp_band_pct'][0]:.0f}%,{g['rfp_band_pct'][1]:.0f}%]")
    if not g.get("freq_pass"):
        fails.append(
            f"freq_reach {g.get('freq_pct_in_band', 0)*100:.0f}% < 80% in "
            f"[{GATE_FREQ_LO_HZ},{GATE_FREQ_HI_HZ}] Hz"
        )
    if not g.get("sac_losses_finite"):
        fails.append("sac_losses_not_finite")
    if not g.get("wall_ok"):
        fails.append(f"wall_time={g.get('wall_time_s', 0):.0f}s > {GATE_WALL_S:.0f}s")
    return (len(fails) == 0), fails


def run_one(
    tag: str,
    phi_h: str,
    phi_d: str,
    rationale: str,
    seed: int = 42,
    episodes: int = 50,
) -> dict:
    print(f"\n=== P4.2 RUN: {tag} ===")
    print(f"  PHI_H={phi_h} PHI_D={phi_d}  ({rationale})")
    print(f"  KUNDUR_DISTURBANCE_TYPE=pm_step_proxy_random_bus")

    HARNESS_DIR.mkdir(parents=True, exist_ok=True)
    stdout_path = HARNESS_DIR / f"p42_{tag}_stdout.txt"
    stderr_path = HARNESS_DIR / f"p42_{tag}_stderr.txt"
    metrics_path = HARNESS_DIR / f"p42_{tag}_metrics.json"

    env = os.environ.copy()
    env["KUNDUR_MODEL_PROFILE"] = str(
        REPO_ROOT / "scenarios" / "kundur" / "model_profiles" / "kundur_cvs_v3.json"
    )
    env["KUNDUR_DISTURBANCE_TYPE"] = "pm_step_proxy_random_bus"
    env["KUNDUR_PHI_H"] = phi_h
    env["KUNDUR_PHI_D"] = phi_d
    # Force unbuffered Python so disturbance logs land in stdout file in real time.
    env["PYTHONUNBUFFERED"] = "1"

    cmd = [
        PYTHON_EXE,
        str(REPO_ROOT / "scenarios" / "kundur" / "train_simulink.py"),
        "--mode", "simulink",
        "--episodes", str(episodes),
        "--resume", "none",   # force fresh start; no auto-resume
        "--seed", str(seed),
        "--save-interval", "50",
        "--eval-interval", "50",   # we don't care about eval inside the gate run
    ]
    print(f"  cmd: {' '.join(cmd)}")
    print(f"  stdout -> {stdout_path}")

    t0 = time.time()
    with stdout_path.open("w", encoding="utf-8") as fout, stderr_path.open(
        "w", encoding="utf-8"
    ) as ferr:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            stdout=fout,
            stderr=ferr,
            shell=False,
        )
    wall_s = time.time() - t0
    print(f"  exit_code={proc.returncode} wall={wall_s:.0f}s ({wall_s/60:.1f} min)")

    # Find the run dir created during this subprocess.
    run_dir = latest_run_dir(RUNS_ROOT, t0)
    print(f"  run_dir={run_dir}")

    bus_counts = parse_disturbance_log(stdout_path)
    print(f"  disturbance_bus_counts={bus_counts}")

    gates = {"tag": tag, "phi_h": phi_h, "phi_d": phi_d, "rationale": rationale}
    gates["exit_code"] = proc.returncode
    gates["run_dir"] = str(run_dir) if run_dir else None
    gates["bus_counts"] = bus_counts

    if run_dir is not None:
        try:
            metrics = compute_gates(run_dir, wall_s, bus_counts, expected_episodes=episodes)
        except Exception as exc:
            metrics = {"error": f"compute_gates raised: {exc}"}
    else:
        metrics = {"error": "no run_dir found"}

    gates["metrics"] = metrics
    passed, fails = overall_gate_pass(metrics)
    gates["pass"] = passed
    gates["fail_reasons"] = fails

    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(gates, f, indent=2, default=str)
    print(f"  metrics -> {metrics_path}")
    print(f"  PASS={passed} fails={fails}")
    return gates


def main() -> int:
    print("P4.2 PHI sweep starting")
    print(f"  REPO_ROOT={REPO_ROOT}")
    print(f"  PYTHON_EXE={PYTHON_EXE}")
    print(f"  RUNS_ROOT={RUNS_ROOT}")
    print(f"  HARNESS_DIR={HARNESS_DIR}")

    HARNESS_DIR.mkdir(parents=True, exist_ok=True)

    # Run baseline 3 sequentially. After 3, evaluate; extend to 4 / 5 only if no PASS.
    runs = []
    pass_idx = -1
    initial = SWEEP_CANDIDATES[:3]
    for i, (tag, ph, pd, rat) in enumerate(initial):
        gates = run_one(tag, ph, pd, rat)
        runs.append(gates)
        if gates.get("pass"):
            pass_idx = i
            print(f"\nP4.2 STOP: {tag} PASSED — no further runs needed.")
            break

    if pass_idx < 0:
        # Extend to phi_asym_b
        tag, ph, pd, rat = SWEEP_CANDIDATES[3]
        print(f"\nP4.2 EXTEND: 3 baselines failed; running {tag}")
        gates = run_one(tag, ph, pd, rat)
        runs.append(gates)
        if gates.get("pass"):
            pass_idx = len(runs) - 1
        else:
            tag, ph, pd, rat = SWEEP_CANDIDATES[4]
            print(f"\nP4.2 EXTEND: 4 candidates failed; running {tag}")
            gates = run_one(tag, ph, pd, rat)
            runs.append(gates)
            if gates.get("pass"):
                pass_idx = len(runs) - 1

    # Write aggregate summary
    aggregate = {
        "schema_version": 1,
        "n_runs": len(runs),
        "pass_index": pass_idx,
        "winning_tag": runs[pass_idx]["tag"] if pass_idx >= 0 else None,
        "kundur_disturbance_type": "pm_step_proxy_random_bus",
        "gate_thresholds": {
            "rfp_band_pct": [GATE_RFP_LO * 100.0, GATE_RFP_HI * 100.0],
            "rfp_target_pct": GATE_RFP_TARGET * 100.0,
            "freq_band_hz": [GATE_FREQ_LO_HZ, GATE_FREQ_HI_HZ],
            "freq_pct_required": GATE_FREQ_PCT_REQ,
            "wall_cap_s": GATE_WALL_S,
        },
        "runs": runs,
    }
    agg_path = HARNESS_DIR / "p42_aggregate_metrics.json"
    with agg_path.open("w", encoding="utf-8") as f:
        json.dump(aggregate, f, indent=2, default=str)
    print(f"\nAggregate -> {agg_path}")
    print(f"P4.2 complete: pass_index={pass_idx} winning_tag={aggregate['winning_tag']}")
    return 0 if pass_idx >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
