"""
Parallel ANDES paper-grade evaluator — orchestrator.

Spawns 5 worker subprocesses (one per controller) via WSL, waits for all,
then aggregates results into summary.json + summary.md identical in schema
to the serial _eval_paper_grade_andes.py output.

Usage (full 50-ep run):
    wsl bash -c 'source ~/andes_venv/bin/activate && \\
        cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs" && \\
        python3 scenarios/kundur/_eval_paper_grade_andes_parallel.py'

Smoke test (2 eps per controller, fast check):
    wsl bash -c 'source ~/andes_venv/bin/activate && \\
        cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs" && \\
        python3 scenarios/kundur/_eval_paper_grade_andes_parallel.py --n-eps 2'

CPU/memory note:
    5 ANDES TDS sims run simultaneously. Each TDS uses ~1 CPU core + ~300 MB
    RAM.  On a 4-core machine this saturates the CPU → realistic speedup is
    2-3× rather than 5×.  On 8+ cores expect 4-5× speedup.  If memory is
    below ~2 GB free, prefer the serial version.

DO NOT modify _eval_paper_grade_andes.py — it may be mid-run.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# ── project root ──────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent.parent
_WORKER_SCRIPT = "scenarios/kundur/_eval_paper_grade_andes_one.py"

# WSL project root (convert Windows path to WSL mount path)
_WSL_ROOT = "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"

OUTPUT_DIR = _ROOT / "results" / "andes_eval_paper_grade_parallel"

# Controllers in the same order as the serial version
_CONTROLLERS = [
    "no_control",
    "adaptive",
    "ddic_seed42",
    "ddic_seed43",
    "ddic_seed44",
]

# Map worker --controller names → canonical serial labels (for summary compat)
_LABEL_MAP = {
    "no_control":  "no_control",
    "adaptive":    "adaptive_K10_K400",
    "ddic_seed42": "ddic_phase4_seed42_final",
    "ddic_seed43": "ddic_phase4_seed43_final",
    "ddic_seed44": "ddic_phase4_seed44_final",
}

BOOTSTRAP_N = 1000
BOOTSTRAP_ALPHA = 0.05
BOOTSTRAP_SEED = 7919
F_NOM = 50.0
DT_S = 0.2
N_STEPS = 50
TOL_HZ = 0.005
WINDOW_S = 1.0
K_H = 10.0
K_D = 400.0
SEED_BASE = 20000


# ── subprocess helpers ────────────────────────────────────────────────────────

def _wsl_json_path(target_path: Path) -> str:
    """Return WSL-compatible path string.

    Inside WSL: Path.__str__() is already POSIX (starts with '/') — no conversion needed.
    On Windows: convert drive letter to /mnt/<drive>/... notation.
    """
    p = str(target_path)
    if _in_wsl():
        # Already POSIX; forward slashes guaranteed by Path.__str__ on Linux
        return p.replace("\\", "/")
    # Windows → WSL mount path
    p = p.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        p = f"/mnt/{drive}{p[2:]}"
    return p


def _in_wsl() -> bool:
    """Return True if the current process is running inside WSL."""
    try:
        with open("/proc/version") as fh:
            return "microsoft" in fh.read().lower()
    except OSError:
        return False


def _launch_worker(
    ctrl: str,
    out_json: Path,
    n_eps: int,
    log_fh,
) -> subprocess.Popen:
    """Spawn one worker subprocess.

    If already inside WSL: use 'bash -c' directly (no nested wsl call).
    If on Windows: wrap with 'wsl bash -c' to enter WSL first.
    """
    wsl_out = _wsl_json_path(out_json)
    # Resolve the WSL-side project root: if already in WSL use the actual path,
    # otherwise use the static _WSL_ROOT mount path.
    if _in_wsl():
        project_root = str(_ROOT)
    else:
        project_root = _WSL_ROOT

    cmd_inner = (
        f"source ~/andes_venv/bin/activate && "
        f"cd \"{project_root}\" && "
        f"python3 {_WORKER_SCRIPT} "
        f"--controller {ctrl} "
        f"--out-json \"{wsl_out}\" "
        f"--n-eps {n_eps}"
    )

    if _in_wsl():
        argv = ["bash", "-c", cmd_inner]
    else:
        argv = ["wsl", "bash", "-c", cmd_inner]

    proc = subprocess.Popen(
        argv,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc


# ── aggregation (mirrors serial version) ─────────────────────────────────────

def _bootstrap_ci_simple(values: list[float]) -> dict:
    """Local fallback bootstrap CI — used only if evaluation.metrics unavailable."""
    import numpy as np
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    arr = np.array(values, dtype=np.float64)
    means = np.array([rng.choice(arr, size=len(arr), replace=True).mean()
                      for _ in range(BOOTSTRAP_N)])
    return {
        "mean": float(arr.mean()),
        "ci_lo": float(np.percentile(means, 2.5)),
        "ci_hi": float(np.percentile(means, 97.5)),
    }


def _load_bootstrap_ci():
    """Import _bootstrap_ci from evaluation.metrics if available; else local fallback."""
    try:
        sys.path.insert(0, str(_ROOT))
        from evaluation.metrics import _bootstrap_ci  # type: ignore
        return _bootstrap_ci
    except ImportError:
        return _bootstrap_ci_simple


def _aggregate_per_controller(records: list[dict], label: str) -> dict:
    _bootstrap_ci = _load_bootstrap_ci()
    n = len(records)
    cum_rf_vals = [r["cum_rf"] for r in records]
    max_df_vals = [r["max_df_hz"] for r in records]
    rocof_vals = [r["rocof_max"] for r in records]
    settling_vals = [r["settling_s"] for r in records if r["settling_s"] is not None]
    n_settled = len(settling_vals)
    n_unsettled = n - n_settled
    cum_rf_total = float(sum(cum_rf_vals))
    settling_for_ci = settling_vals if settling_vals else [0.0]

    return {
        "label": label,
        "n_scenarios": n,
        "cum_rf_total": cum_rf_total,
        "cum_rf_ci": _bootstrap_ci(cum_rf_vals, n_resample=BOOTSTRAP_N,
                                   alpha=BOOTSTRAP_ALPHA, seed=BOOTSTRAP_SEED),
        "max_df_hz": _bootstrap_ci(max_df_vals, n_resample=BOOTSTRAP_N,
                                   alpha=BOOTSTRAP_ALPHA, seed=BOOTSTRAP_SEED),
        "rocof_max": _bootstrap_ci(rocof_vals, n_resample=BOOTSTRAP_N,
                                   alpha=BOOTSTRAP_ALPHA, seed=BOOTSTRAP_SEED),
        "settling_time_s": {
            **_bootstrap_ci(settling_for_ci, n_resample=BOOTSTRAP_N,
                            alpha=BOOTSTRAP_ALPHA, seed=BOOTSTRAP_SEED),
            "n_settled": n_settled,
            "n_unsettled": n_unsettled,
        },
    }


def _ci_overlap(ci_a: dict, ci_b: dict) -> bool:
    lo_a, hi_a = ci_a["ci_lo"], ci_a["ci_hi"]
    lo_b, hi_b = ci_b["ci_lo"], ci_b["ci_hi"]
    return not (hi_a < lo_b or hi_b < lo_a)


def _write_markdown(summaries: dict, out_path: Path, n_test_eps: int) -> None:
    ctrl_keys = list(summaries["controllers"].keys())
    ctrls = summaries["controllers"]

    lines = [
        "# ANDES Kundur Paper §IV-C Grade Evaluation (Parallel Run)",
        "",
        "**Metric helpers provenance**: `evaluation/metrics.py`  ",
        f"**N test episodes per controller**: {n_test_eps} (seeds {SEED_BASE}–{SEED_BASE+n_test_eps-1})  ",
        f"**Settling tolerance**: {TOL_HZ} Hz, window {WINDOW_S}s  ",
        f"**Bootstrap**: n_resample={BOOTSTRAP_N}, alpha={BOOTSTRAP_ALPHA}, seed={BOOTSTRAP_SEED}",
        "",
        "---",
        "",
        "## Table 1 — Cumulative r_f with Bootstrap CI",
        "",
        "| Controller | cum_rf total | mean/ep | ci_lo | ci_hi |",
        "|---|---:|---:|---:|---:|",
    ]
    for k in ctrl_keys:
        c = ctrls[k]
        ci = c["cum_rf_ci"]
        lines.append(
            f"| {k} | {c['cum_rf_total']:.4f} | {ci['mean']:.4f} | "
            f"{ci['ci_lo']:.4f} | {ci['ci_hi']:.4f} |"
        )

    lines += [
        "",
        "## Table 2 — max |Δf|, ROCoF, Settling Time with Bootstrap CI",
        "",
        "| Controller | max_df mean (Hz) | ci_lo | ci_hi |"
        " ROCoF mean (Hz/s) | ci_lo | ci_hi |"
        " settling mean (s) | ci_lo | ci_hi | n_settled |",
        f"|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for k in ctrl_keys:
        c = ctrls[k]
        df = c["max_df_hz"]
        ro = c["rocof_max"]
        st = c["settling_time_s"]
        lines.append(
            f"| {k} | {df['mean']:.4f} | {df['ci_lo']:.4f} | {df['ci_hi']:.4f} |"
            f" {ro['mean']:.4f} | {ro['ci_lo']:.4f} | {ro['ci_hi']:.4f} |"
            f" {st['mean']:.3f} | {st['ci_lo']:.3f} | {st['ci_hi']:.3f} |"
            f" {st['n_settled']}/{n_test_eps} |"
        )

    ddic_key = "ddic_phase4_3seed_mean"
    adaptive_key = "adaptive_K10_K400"
    no_ctrl_key = "no_control"

    lines += [
        "",
        "## Table 3 — Comparison Statements",
        "",
        "| Comparison | Metric | DDIC mean | Adaptive mean | CI overlap | Interpretation |",
        "|---|---|---:|---:|---|---|",
    ]

    if ddic_key in ctrls and adaptive_key in ctrls:
        def _ov(b: bool) -> str:
            return "OVERLAP → not statistically significant" if b else "NO OVERLAP → significant"

        d_rf = ctrls[ddic_key]["cum_rf_ci"]
        a_rf = ctrls[adaptive_key]["cum_rf_ci"]
        d_df = ctrls[ddic_key]["max_df_hz"]
        a_df = ctrls[adaptive_key]["max_df_hz"]
        d_ro = ctrls[ddic_key]["rocof_max"]
        a_ro = ctrls[adaptive_key]["rocof_max"]
        d_st = ctrls[ddic_key]["settling_time_s"]
        a_st = ctrls[adaptive_key]["settling_time_s"]

        for metric, dm, am in [
            ("cum_rf/ep", d_rf, a_rf),
            ("max_df (Hz)", d_df, a_df),
            ("ROCoF (Hz/s)", d_ro, a_ro),
            ("settling (s)", d_st, a_st),
        ]:
            ov = _ci_overlap(dm, am)
            lines.append(
                f"| DDIC vs adaptive | {metric} |"
                f" {dm['mean']:.4f} | {am['mean']:.4f} |"
                f" CI overlap = {'YES' if ov else 'NO'} | {_ov(ov)} |"
            )

    if no_ctrl_key in ctrls and ddic_key in ctrls:
        nc_rf = ctrls[no_ctrl_key]["cum_rf_ci"]
        d_rf2 = ctrls[ddic_key]["cum_rf_ci"]
        improvement_rf = (nc_rf["mean"] - d_rf2["mean"]) / (abs(nc_rf["mean"]) + 1e-12) * 100
        lines.append(
            f"| DDIC vs no-control | cum_rf/ep |"
            f" {d_rf2['mean']:.4f} | {nc_rf['mean']:.4f} |"
            f" — | DDIC improvement: {improvement_rf:+.1f}% |"
        )

    lines += [
        "",
        "---",
        "",
        f"*Generated by `scenarios/kundur/_eval_paper_grade_andes_parallel.py`*",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[agg] markdown → {out_path}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parallel ANDES paper-grade evaluator orchestrator"
    )
    parser.add_argument(
        "--n-eps",
        type=int,
        default=int(os.environ.get("N_EPS_OVERRIDE", "50")),
        help="Episodes per controller (default 50; set 2 for smoke test)",
    )
    args = parser.parse_args()
    n_eps: int = args.n_eps

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log_dir = OUTPUT_DIR / "worker_logs"
    log_dir.mkdir(exist_ok=True)

    print(f"[parallel] Launching {len(_CONTROLLERS)} worker processes "
          f"({n_eps} eps each)...")
    print(f"[parallel] Output dir: {OUTPUT_DIR}")

    wall_start = time.time()

    # ── launch all 5 subprocesses ─────────────────────────────────────────────
    procs: dict[str, dict] = {}
    for ctrl in _CONTROLLERS:
        out_json = OUTPUT_DIR / f"{ctrl}.json"
        log_path = log_dir / f"{ctrl}.log"
        log_fh = open(log_path, "w", encoding="utf-8")  # noqa: WPS515
        proc = _launch_worker(ctrl, out_json, n_eps, log_fh)
        procs[ctrl] = {
            "proc": proc,
            "log_fh": log_fh,
            "log_path": log_path,
            "out_json": out_json,
            "start": time.time(),
        }
        print(f"  [parallel] launched {ctrl} → pid={proc.pid}")

    # ── wait for all, collect return codes ───────────────────────────────────
    print(f"\n[parallel] Waiting for all workers to finish...")
    failed: list[str] = []
    for ctrl, info in procs.items():
        proc: subprocess.Popen = info["proc"]
        try:
            rc = proc.wait(timeout=3600)  # 60 min hard cap per worker
        except subprocess.TimeoutExpired:
            proc.kill()
            rc = -999
            print(f"  [parallel] TIMEOUT: {ctrl} — killed")

        info["log_fh"].close()
        elapsed = time.time() - info["start"]
        status = "OK" if rc == 0 else f"FAIL(rc={rc})"
        print(f"  [parallel] {ctrl}: {status}  wall={elapsed:.1f}s  "
              f"log={info['log_path']}")
        if rc != 0:
            failed.append(ctrl)

    total_wall = time.time() - wall_start
    print(f"\n[parallel] All workers done.  total wall={total_wall:.1f}s")

    if failed:
        print(f"[parallel] WARNING: {len(failed)} worker(s) FAILED: {failed}")
        print("[parallel] Aggregating from available JSON files only.")

    # ── aggregate ──────────────────────────────────────────────────────────────
    print("\n[parallel] Aggregating results...")

    all_records: dict[str, list[dict]] = {}
    missing: list[str] = []

    for ctrl in _CONTROLLERS:
        out_json: Path = procs[ctrl]["out_json"]
        if not out_json.exists():
            print(f"  [agg] MISSING: {out_json}")
            missing.append(ctrl)
            continue
        try:
            with open(out_json, encoding="utf-8") as fh:
                worker_out = json.load(fh)
            records = worker_out["episode_records"]
            label = worker_out["label"]
            all_records[label] = records
            print(f"  [agg] loaded {ctrl}: {len(records)} eps, label={label}")
        except Exception as exc:
            print(f"  [agg] ERROR reading {out_json}: {exc}")
            missing.append(ctrl)

    if missing:
        print(f"[agg] WARNING: {len(missing)} controller(s) missing from results: {missing}")

    # Build 3-seed mean aggregate (mirrors serial version)
    three_seed_records: list[dict] = []
    for s in [42, 43, 44]:
        lbl = f"ddic_phase4_seed{s}_final"
        if lbl in all_records:
            three_seed_records.extend(all_records[lbl])

    controllers_summary: dict[str, dict] = {}
    for label, records in all_records.items():
        controllers_summary[label] = _aggregate_per_controller(records, label)

    if three_seed_records:
        controllers_summary["ddic_phase4_3seed_mean"] = _aggregate_per_controller(
            three_seed_records, "ddic_phase4_3seed_mean"
        )

    # Count n_test_eps from available records (may differ from args.n_eps if partial)
    actual_n_eps_per_ctrl = {
        lbl: len(recs) for lbl, recs in all_records.items()
    }

    output = {
        "metric_helpers_provenance": "evaluation/metrics.py",
        "parallel_run": True,
        "n_workers": len(_CONTROLLERS),
        "n_failed_workers": len(failed),
        "total_wall_s": round(total_wall, 2),
        "eval_config": {
            "n_test_eps": n_eps,
            "seed_range": f"{SEED_BASE}..{SEED_BASE + n_eps - 1}",
            "f_nom_hz": F_NOM,
            "dt_s": DT_S,
            "n_steps": N_STEPS,
            "tol_hz": TOL_HZ,
            "window_s": WINDOW_S,
            "bootstrap": {
                "n_resample": BOOTSTRAP_N,
                "alpha": BOOTSTRAP_ALPHA,
                "seed": BOOTSTRAP_SEED,
            },
            "adaptive_gains": {"K_H": K_H, "K_D": K_D},
        },
        "controllers": controllers_summary,
        "n_eps_per_controller": actual_n_eps_per_ctrl,
    }

    json_path = OUTPUT_DIR / "per_seed_summary.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, default=str)
    print(f"\n[agg] JSON → {json_path}")

    md_path = OUTPUT_DIR / "summary.md"
    _write_markdown(output, md_path, n_eps)

    print(f"\n[parallel] Done.")
    print(f"  JSON:       {json_path}")
    print(f"  Markdown:   {md_path}")
    print(f"  Worker logs: {log_dir}/")
    print(f"  Total wall:  {total_wall:.1f}s  "
          f"({'smoke' if n_eps <= 5 else 'full'} run, {n_eps} eps/ctrl)")

    if failed:
        print(f"\n  CAUTION: {len(failed)} worker(s) failed — summary is partial.")
        sys.exit(1)


if __name__ == "__main__":
    main()
