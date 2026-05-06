"""Shared helpers for paper/figure_scripts/* (Simulink discrete edition).

Plan: quality_reports/plans/2026-05-05_paper_figure_toolkit.md

Conventions
-----------
- Output dir = paper/figures/  (PNG + PDF)
- Run dir paths point to results/sim_kundur/runs/<run_id>/
- All consumers tolerate missing files / fields (graceful skip / fallback).
- Banner per script: prints PAPER-ANCHOR LOCK reminder before plotting.

Adding a new run
----------------
1. Add a constant to RUN_DIRS below.
2. _common.load_metrics_jsonl(RUN_DIRS["my_run"]) → list[dict]

PAPER-ANCHOR LOCK (from MEMORY feedback_signal_first_falsification.md):
Numerical values plotted here are project-run results, NOT benchmarked
against paper -8.04/-12.93/-15.20 until G1-G6 falsification gates clear.
Show the curves; do not claim parity until verdicts upgrade.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np

# ── Paths ──────────────────────────────────────────────────────────────────

import os as _os

REPO = Path(__file__).resolve().parents[2]
RUNS_ROOT = REPO / "results" / "sim_kundur" / "runs"  # Simulink legacy

# Per-model output subdir via PAPER_FIG_VARIANT env var:
#   PAPER_FIG_VARIANT=v2env_phase3v2_seed44 → paper/figures/v2env_phase3v2_seed44/
#   未设 → paper/figures/  (default)
OUT_DIR_BASE = REPO / "paper" / "figures"
_VARIANT = _os.environ.get("PAPER_FIG_VARIANT", "")
OUT_DIR = OUT_DIR_BASE / _VARIANT if _VARIANT else OUT_DIR_BASE

# ANDES paths (current active path, 2026-05-06)
ANDES_RESULTS = REPO / "results"
_RUN_EVAL_PAPER_GRADE = ANDES_RESULTS / "andes_eval_paper_grade"
_RUN_EVAL_PAPER_GRADE_PARALLEL = ANDES_RESULTS / "andes_eval_paper_grade_parallel"
_RUN_EVAL_PAPER_SPEC_ENVV2 = ANDES_RESULTS / "andes_eval_paper_specific_v2_envV2_hetero"
_RUN_EVAL_PAPER_SPEC_V2 = ANDES_RESULTS / "andes_eval_paper_specific_v2"
_RUN_EVAL_PAPER_SPEC_LEGACY = ANDES_RESULTS / "andes_eval_paper_specific"
_RUN_TRAIN_PER_AGENT = ANDES_RESULTS / "andes_phase4_noPHIabs_seed42"

# Plan §2 main runs (paper plan v2.1c) — Simulink legacy, kept for compat
RUN_DIRS = {
    # Trial 3 main: PHI=5e-4, seed=100, 500 ep
    "trial3":             RUNS_ROOT / "phase1_7_trial_3",
    # PHI sweep neighborhood
    "trial3_phi1e3":      RUNS_ROOT / "phase1_7_trial_3_phi1e3",   # PHI=1e-3
    "trial2A_baseline":   RUNS_ROOT / "phase1_7_trial_2A_baseline", # PHI=0.1
    "trial2A":            RUNS_ROOT / "phase1_7_trial_2A",
    # Seed-consistency runs (plan §5.2)
    "trial3_seed200":     RUNS_ROOT / "phase1_7_trial_3_seed200",
    "trial3_seed300":     RUNS_ROOT / "phase1_7_trial_3_seed300",
    # Buffer ablation (plan §5.5)
    "trial3_buffer10k":   RUNS_ROOT / "phase1_7_trial_3_buffer10k",
}

# Honest peak window (plan §5.3)
PEAK_EP_RANGE = (200, 220)
PHI_SWEEP_BLOCK = (38, 48)  # plan §5.1 block window for r_f sweep

# Paper §IV-A grade requirements
PAPER_DT_S = 0.2
PAPER_N_STEPS = 50
PAPER_T_EPISODE = 10.0

# ── Loaders ────────────────────────────────────────────────────────────────


def metrics_path(run_dir: Path) -> Path:
    return run_dir / "logs" / "metrics.jsonl"


def training_log_path(run_dir: Path) -> Path:
    return run_dir / "logs" / "training_log.json"


def load_metrics_jsonl(run_dir: Path) -> list[dict]:
    """Load metrics.jsonl as list of dicts. Returns [] if missing."""
    p = metrics_path(run_dir)
    if not p.exists():
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_training_log(run_dir: Path) -> dict:
    """Load training_log.json. Returns {} if missing."""
    p = training_log_path(run_dir)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_eval_traces(traces_dir: Path, label: str) -> dict | None:
    """Load a single trace JSON dumped by evaluate_simulink --dump-eval-json.

    label e.g. "ddic_load_step_1" → traces_dir/ddic_load_step_1.json
    """
    p = traces_dir / f"{label}.json"
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_eval_test_set(traces_dir: Path, label: str) -> list[float] | None:
    """Load 50-test cum-reward JSON (paper Fig.5 source).

    label e.g. "fig5_rl" → traces_dir/fig5_rl_test_set.json
    Returns list of per-episode cum_rf, or None if missing.
    """
    p = traces_dir / f"{label}_test_set.json"
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    return [r["cum_rf"] for r in d.get("episode_records", [])]


# ── Extractors (metrics.jsonl → np arrays) ────────────────────────────────


def get_episode_rewards(metrics: list[dict]) -> np.ndarray:
    """Per-episode mean reward (4-agent averaged), shape (n_ep,)."""
    return np.asarray([m.get("reward", np.nan) for m in metrics], dtype=float)


def get_reward_components(metrics: list[dict]) -> dict[str, np.ndarray]:
    """Returns {'r_f': arr, 'r_h': arr, 'r_d': arr}, each shape (n_ep,)."""
    out = {"r_f": [], "r_h": [], "r_d": []}
    for m in metrics:
        rc = m.get("reward_components", {})
        for k in out:
            out[k].append(rc.get(k, np.nan))
    return {k: np.asarray(v, dtype=float) for k, v in out.items()}


def get_per_agent_rewards(metrics: list[dict]) -> np.ndarray | None:
    """Per-agent reward time series, shape (n_agents, n_ep). None if missing."""
    rows = [m.get("reward_per_agent") for m in metrics]
    if not rows or rows[0] is None:
        return None
    arr = np.asarray(rows, dtype=float)  # (n_ep, n_agents)
    return arr.T  # (n_agents, n_ep)


def get_per_agent_r_f(metrics: list[dict]) -> np.ndarray | None:
    """Per-agent r_f time series, shape (n_agents, n_ep). None if missing."""
    rows = [m.get("r_f_per_agent") for m in metrics]
    if not rows or rows[0] is None:
        return None
    arr = np.asarray(rows, dtype=float)
    return arr.T


def block_mean(arr: np.ndarray, lo: int, hi: int) -> float:
    """Mean over arr[lo:hi]; tolerant to short arrays."""
    s = arr[lo:hi]
    s = s[~np.isnan(s)]
    return float(s.mean()) if s.size else float("nan")


# ── Banner ─────────────────────────────────────────────────────────────────


def banner_no_anchor(fig_name: str) -> str:
    return (
        f"[{fig_name}] PAPER-ANCHOR LOCK: figure shows project-run data. "
        "Values not benchmarked against paper -8.04/-12.93/-15.20 "
        "until G1-G6 falsification gates clear (per MEMORY)."
    )


def load_json(path: Path) -> dict:
    """Old-repo compat alias for load_json (Simulink-side equivalent)."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── ANDES path aliases (active 2026-05-06) ───────────────────────────────
# 旧 alias 指 Simulink, 改指 ANDES. 老脚本若引用 EVAL_PG_DIR/EVAL_SPEC_DIR
# 自动获得 ANDES 数据.
EVAL_PG_DIR = _RUN_EVAL_PAPER_GRADE
EVAL_PG_PARALLEL_DIR = _RUN_EVAL_PAPER_GRADE_PARALLEL
EVAL_SPEC_V2_DIR = _RUN_EVAL_PAPER_SPEC_V2
EVAL_SPEC_DIR = _RUN_EVAL_PAPER_SPEC_ENVV2  # default = V2 hetero env (verdict locked)
TRAIN_LOG = _RUN_TRAIN_PER_AGENT / "training_log.json"


def resolve_spec_dir() -> Path:
    """Resolve ANDES eval spec dir (V2 hetero default).

    Override via PAPER_FIG_SPEC_DIR env var (abs path or rel-to-results name).
    """
    override = _os.environ.get("PAPER_FIG_SPEC_DIR", "")
    if override:
        p = Path(override)
        if not p.is_absolute():
            p = ANDES_RESULTS / override
        if (p / "no_control_load_step_1.json").exists():
            return p
        raise ValueError(
            f"PAPER_FIG_SPEC_DIR={override} missing no_control_load_step_1.json"
        )
    if (_RUN_EVAL_PAPER_SPEC_ENVV2 / "no_control_load_step_1.json").exists():
        return _RUN_EVAL_PAPER_SPEC_ENVV2
    if (_RUN_EVAL_PAPER_SPEC_V2 / "no_control_load_step_1.json").exists():
        return _RUN_EVAL_PAPER_SPEC_V2
    return _RUN_EVAL_PAPER_SPEC_LEGACY


def warn_missing(field: str, run_dir: Path, fallback: str) -> None:
    print(f"  [WARN] {run_dir.name}: '{field}' missing → {fallback}")


# ── Guards (borrowed from old-repo paper/figure_scripts/_common.py) ───────


def assert_dt_paper_grade(eval_config: dict, src: str) -> None:
    """Refuse to plot non-paper-grade data (dt != 0.2 or n_steps != 50).

    Raises ValueError. Call this in fig5 / figs6_7 BEFORE plotting any
    eval JSON loaded from disk, to fail-fast on accidental Tier-2 200µs
    or other off-spec data.

    eval_config dict shape (matches evaluate_simulink._dump_*_json output):
        {"dt_s": float, "n_steps": int, ...}  OR  any superset
    """
    dt = eval_config.get("dt_s")
    n = eval_config.get("n_steps")
    if dt is None or n is None:
        # eval_config field absent — skip (graceful for older dumps)
        return
    if abs(float(dt) - PAPER_DT_S) > 1e-6 or int(n) != PAPER_N_STEPS:
        raise ValueError(
            f"[{src}] dt={dt}s / n_steps={n} is NOT paper-grade "
            f"(expected dt={PAPER_DT_S} / n_steps={PAPER_N_STEPS}). "
            "Refusing to generate paper figure."
        )


def assert_traces_paper_grade(traces: list, src: str) -> None:
    """Refuse to plot traces whose actual dt deviates from paper.

    Used by figs6_7_ls_traces.py before plotting time series.
    Compares t[1]-t[0] (assumed uniform sampling) against PAPER_DT_S.
    """
    if len(traces) < 2:
        raise ValueError(f"[{src}] traces too short ({len(traces)} steps)")
    dt_actual = float(traces[1]["t"] - traces[0]["t"])
    if abs(dt_actual - PAPER_DT_S) > 1e-3:
        raise ValueError(
            f"[{src}] trace dt={dt_actual:.4f}s "
            f"is NOT paper-grade (expected {PAPER_DT_S}s)."
        )


__all__ = [
    "REPO", "RUNS_ROOT", "OUT_DIR", "RUN_DIRS",
    "PEAK_EP_RANGE", "PHI_SWEEP_BLOCK",
    "PAPER_DT_S", "PAPER_N_STEPS", "PAPER_T_EPISODE",
    "metrics_path", "training_log_path",
    "load_metrics_jsonl", "load_training_log",
    "load_eval_traces", "load_eval_test_set",
    "get_episode_rewards", "get_reward_components",
    "get_per_agent_rewards", "get_per_agent_r_f",
    "block_mean",
    "banner_no_anchor", "warn_missing",
    "assert_dt_paper_grade", "assert_traces_paper_grade",
]
