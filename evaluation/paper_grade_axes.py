"""6-axis paper-alignment evaluator for ANDES Kundur 4-VSG traces.

替代旧 cum_rf 单维评判. 量化结合 Yang2023 Fig.6/7/8/9 实测特征.

Axes (论文 benchmark = 1.0, 项目实测越接近越高):
  1. max_|Δf|       : 峰值 |Δf| (Hz) — 论文 LS1=0.13 / LS2=0.10
  2. final_|Δf|@6s  : t=6s 残值 — 论文 LS1=0.08 / LS2=0.05
  3. settling_s     : |Δf|进入 ±0.02 Hz of residual 的时刻 — 论文 LS1=3s / LS2=2.5s
  4. ΔH_smooth      : ΔH avg 高频抖动 std (越平滑越好) — 论文 ~0
  5. ΔD_smooth      : ΔD avg 高频抖动 std — 论文 ~0
  6. action_range   : agent 实际用的 ΔH/ΔD 范围与论文比 — DDIC 期望 [-100,+250] H, [-200,+500] D

每 axis score = clip(1 - |actual - paper|/tolerance, 0, 1)
6-axis 总分 = 几何平均 (任何一项 0 → 总分 0, 强制 holistic 通过)

Usage:
    python evaluation/paper_grade_axes.py [eval_dir]

Default eval_dir = results/andes_eval_paper_specific_v2_envV2_hetero/
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


# ─── Paper benchmarks (from Fig.6/7/8/9 visual extraction, 2026-05-06) ───

@dataclass(frozen=True)
class PaperBenchmark:
    scenario: str
    max_abs_df_Hz: float
    final_abs_df_Hz: float
    settling_to_residual_s: float
    dH_avg_smooth_std: float
    dD_avg_smooth_std: float
    dH_range: tuple[float, float]
    dD_range: tuple[float, float]
    note: str = ""


PAPER = {
    "load_step_1": PaperBenchmark(
        scenario="load_step_1",
        max_abs_df_Hz=0.13, final_abs_df_Hz=0.08, settling_to_residual_s=3.0,
        dH_avg_smooth_std=0.0, dD_avg_smooth_std=0.0,
        dH_range=(-100.0, 250.0), dD_range=(-200.0, 500.0),
        note="Fig.6 no-ctrl + Fig.7 DDIC, 6s window",
    ),
    "load_step_2": PaperBenchmark(
        scenario="load_step_2",
        max_abs_df_Hz=0.10, final_abs_df_Hz=0.05, settling_to_residual_s=2.5,
        dH_avg_smooth_std=0.0, dD_avg_smooth_std=0.0,
        dH_range=(-100.0, 200.0), dD_range=(-200.0, 300.0),
        note="Fig.8 no-ctrl + Fig.9 DDIC, 6s window",
    ),
}


TOL = dict(
    max_df=0.10,
    final_df=0.06,
    settling=4.0,
    dH_smooth=10.0,
    dD_smooth=30.0,
    range_factor=0.5,
)


@dataclass
class AxisScore:
    name: str
    project_value: float
    paper_value: float
    score: float
    note: str = ""


@dataclass
class TraceScore:
    label: str
    scenario: str
    is_ddic: bool
    axes: list[AxisScore] = field(default_factory=list)
    overall: float = 0.0

    def summary(self) -> str:
        lines = [f"\n=== {self.label} / {self.scenario} (DDIC={self.is_ddic}) ==="]
        for a in self.axes:
            bar = int(a.score * 20) * "#" + int((1 - a.score) * 20) * "."
            lines.append(
                f"  {a.name:18s} project={a.project_value:8.3f}  paper={a.paper_value:8.3f}  "
                f"score={a.score:.2f}  [{bar}]"
            )
        lines.append(f"  {'OVERALL (geo mean)':18s} {'':>8s}  {'':>8s}  score={self.overall:.2f}")
        return "\n".join(lines)


def _tol_score(project: float, paper: float, tol: float) -> float:
    return float(max(0.0, 1.0 - abs(project - paper) / tol))


def _settling_time(t: np.ndarray, df: np.ndarray, residual_band_Hz: float = 0.02,
                   final_df_Hz: float = 0.0, dt_window: float = 0.5) -> float:
    """Time after which max|Δf - final_df| stays < residual_band_Hz over dt_window window."""
    max_per_t = np.max(np.abs(df), axis=1)
    deviation_from_residual = np.abs(max_per_t - final_df_Hz)
    n_window = max(1, int(dt_window / max(t[1] - t[0], 1e-6)))
    for i in range(len(t) - n_window):
        if np.all(deviation_from_residual[i : i + n_window] < residual_band_Hz):
            return float(t[i])
    return float("inf")


def _hf_std(arr: np.ndarray) -> float:
    """High-freq oscillation: step-to-step diff std (avg curve over agents)."""
    avg = arr.mean(axis=1)
    return float(np.std(np.diff(avg)))


def _action_range(arr: np.ndarray) -> tuple[float, float]:
    """Min/max of avg curve over time."""
    avg = arr.mean(axis=1)
    return float(avg.min()), float(avg.max())


def evaluate_trace(trace_json_path: Path, paper: PaperBenchmark, is_ddic: bool,
                   label: str) -> TraceScore:
    """Compute 6-axis score for one trace JSON."""
    j = json.load(open(trace_json_path))
    tr = j["traces"]
    t = np.array([s["t"] for s in tr])
    df_full = np.array([s["delta_f_es"] for s in tr])
    H_full = np.array([s["M_es"] for s in tr]) / 2.0  # M=2H convention
    D_full = np.array([s["D_es"] for s in tr])

    # Truncate to 6s window for paper-direct comparison
    mask_6s = t <= t[0] + 6.0
    df = df_full[mask_6s]
    H = H_full[mask_6s]
    D = D_full[mask_6s]
    t6 = t[mask_6s]

    dH = H - H[0:1]
    dD = D - D[0:1]

    proj_max_df = float(np.max(np.abs(df)))
    proj_final_df = float(np.abs(df[-1]).max())
    proj_settling = _settling_time(t6, df, residual_band_Hz=0.02,
                                    final_df_Hz=paper.final_abs_df_Hz)
    proj_dH_std = _hf_std(dH) if is_ddic else 0.0
    proj_dD_std = _hf_std(dD) if is_ddic else 0.0
    proj_dH_min, proj_dH_max = _action_range(dH)
    proj_dD_min, proj_dD_max = _action_range(dD)

    axes = [
        AxisScore("max_|df|_Hz", proj_max_df, paper.max_abs_df_Hz,
                  _tol_score(proj_max_df, paper.max_abs_df_Hz, TOL["max_df"])),
        AxisScore("final_|df|@6s", proj_final_df, paper.final_abs_df_Hz,
                  _tol_score(proj_final_df, paper.final_abs_df_Hz, TOL["final_df"])),
        AxisScore("settling_s", proj_settling if proj_settling != float("inf") else 99.0,
                  paper.settling_to_residual_s,
                  _tol_score(proj_settling if proj_settling != float("inf") else 99.0,
                             paper.settling_to_residual_s, TOL["settling"])),
    ]
    if is_ddic:
        axes.append(AxisScore("dH_avg_smoothness", proj_dH_std, 0.0,
                              max(0.0, 1.0 - proj_dH_std / TOL["dH_smooth"])))
        axes.append(AxisScore("dD_avg_smoothness", proj_dD_std, 0.0,
                              max(0.0, 1.0 - proj_dD_std / TOL["dD_smooth"])))
        proj_dH_span = proj_dH_max - proj_dH_min
        paper_dH_span = paper.dH_range[1] - paper.dH_range[0]
        proj_dD_span = proj_dD_max - proj_dD_min
        paper_dD_span = paper.dD_range[1] - paper.dD_range[0]
        dH_ratio = proj_dH_span / paper_dH_span if paper_dH_span > 0 else 0.0
        dD_ratio = proj_dD_span / paper_dD_span if paper_dD_span > 0 else 0.0
        axes.append(AxisScore("dH_range_match", proj_dH_span, paper_dH_span,
                              max(0.0, 1.0 - abs(1 - dH_ratio) / TOL["range_factor"]),
                              note=f"ratio={dH_ratio:.2f}"))
        axes.append(AxisScore("dD_range_match", proj_dD_span, paper_dD_span,
                              max(0.0, 1.0 - abs(1 - dD_ratio) / TOL["range_factor"]),
                              note=f"ratio={dD_ratio:.2f}"))

    scores = [a.score for a in axes]
    overall = math.exp(sum(math.log(max(s, 0.01)) for s in scores) / len(scores))
    return TraceScore(label=label, scenario=paper.scenario, is_ddic=is_ddic,
                      axes=axes, overall=overall)


def rank_models(eval_dir: Path, ckpt_labels: list[str]) -> list[tuple[str, float]]:
    rankings = []
    for lbl in ckpt_labels:
        scores = []
        for scen in ["load_step_1", "load_step_2"]:
            p = eval_dir / f"{lbl}_{scen}.json"
            if not p.exists():
                continue
            ts = evaluate_trace(p, PAPER[scen], is_ddic=("ddic" in lbl), label=lbl)
            scores.append(ts.overall)
        if scores:
            rankings.append((lbl, float(np.mean(scores))))
    rankings.sort(key=lambda x: -x[1])
    return rankings


if __name__ == "__main__":
    import sys
    import os
    ROOT = Path(__file__).resolve().parents[1]
    eval_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        ROOT / "results" / "andes_eval_paper_specific_v2_envV2_hetero"

    files = os.listdir(eval_dir)
    labels = sorted(set(
        f.replace("_load_step_1.json", "").replace("_load_step_2.json", "")
        for f in files if f.endswith(".json")
    ))

    print(f"Eval dir: {eval_dir}")
    print(f"Found {len(labels)} ckpt labels\n")

    all_scores = []
    for lbl in labels:
        for scen in ["load_step_1", "load_step_2"]:
            p = eval_dir / f"{lbl}_{scen}.json"
            if not p.exists():
                continue
            ts = evaluate_trace(p, PAPER[scen], is_ddic=("ddic" in lbl), label=lbl)
            all_scores.append(ts)

    all_scores.sort(key=lambda x: -x.overall)

    print("=" * 80)
    print("TOP 6 (full breakdown)")
    print("=" * 80)
    for ts in all_scores[:6]:
        print(ts.summary())

    print("\n" + "=" * 80)
    print("RANKING by mean(LS1, LS2) overall score")
    print("=" * 80)
    by_lbl: dict[str, list[float]] = {}
    for ts in all_scores:
        by_lbl.setdefault(ts.label, []).append(ts.overall)
    combined = sorted(
        [(l, float(np.mean(s))) for l, s in by_lbl.items() if len(s) == 2],
        key=lambda x: -x[1],
    )
    print(f"{'rank':>4s}  {'label':50s}  {'mean overall':>12s}")
    for i, (l, s) in enumerate(combined, 1):
        marker = " <- BEST" if i == 1 else ""
        print(f"{i:4d}  {l:50s}  {s:12.3f}{marker}")
