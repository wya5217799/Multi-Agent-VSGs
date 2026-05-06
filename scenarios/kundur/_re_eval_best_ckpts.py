"""W1.1: 用 best.pt 重 eval 老 model — 看是否被低估.

旧脚本 _eval_paper_specific.py 默认用 final.pt 评估老 phase 系列, 但 balanced
分支揭示 final 后期可能退化 25%. 本脚本扫所有 phase4/phase9/warmstart 系列
用 best.pt + final.pt 双跑 LS1/LS2 对比.

输出: results/andes_eval_bestckpt_re_eval_2026-05-06/

⚠ 2026-05-07 修正: 即使用 best.pt, 老 model 仅 cum_rf 单维"接近论文"
   (warmstart_seed42 final LS1 4.5%/LS2 1.8% 是 cum_rf cherry-pick).
   6-axis 评估 (max_df / final_df / settling / range / smoothness)
   仍全部 fail. 见 docs/paper/andes_replication_status_2026-05-07_6axis.md.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "results" / "andes_eval_bestckpt_re_eval_2026-05-06"
os.environ["EVAL_PAPER_SPEC_OUT_DIR"] = str(OUT)

from scenarios.kundur._eval_paper_specific import (  # noqa: E402
    eval_scenario,
    _load_sac_actors,
    _make_ddic_controller,
)

OUT.mkdir(parents=True, exist_ok=True)

CANDIDATES = [
    "andes_phase4_noPHIabs_seed42",
    "andes_phase4_noPHIabs_seed43",
    "andes_phase4_noPHIabs_seed44",
    "andes_phase4_noPHIabs_seed45",
    "andes_phase4_noPHIabs_seed46",
    "andes_warmstart_seed42",
    "andes_warmstart_seed43",
    "andes_warmstart_seed44",
    "andes_phase3_seed42",
    "andes_phase3_seed43",
    "andes_phase3_seed44",
    "andes_phase9_shared_seed42_500ep",
    "andes_phase9_shared_seed43_500ep",
    "andes_phase9_shared_seed44_500ep",
    "andes_phase9_shared_seed45_500ep",
    "andes_phase9_shared_seed46_500ep",
]

PAPER_REF = {
    "load_step_1": {"no_control": -1.61, "ddic": -0.68},
    "load_step_2": {"no_control": -0.80, "ddic": -0.52},
}


def _diff_pct(actual: float, ref: float) -> str:
    if abs(ref) < 1e-9:
        return "n/a"
    return f"{abs(actual - ref) / abs(ref) * 100:.1f}%"


def main() -> None:
    rows = []
    for run in CANDIDATES:
        ckpt_dir = ROOT / "results" / run
        if not ckpt_dir.exists():
            print(f"[SKIP] {run}: dir missing")
            continue
        for suffix in ["best", "final"]:
            ckpt_files = list(ckpt_dir.glob(f"agent_*_{suffix}.pt"))
            if len(ckpt_files) < 4:
                continue
            actors = _load_sac_actors(str(ckpt_dir), suffix=suffix)
            if actors is None:
                continue
            ctrl = _make_ddic_controller(actors)
            label = f"{run.replace('andes_', '')}_{suffix}"

            for scen in ["load_step_1", "load_step_2"]:
                try:
                    r = eval_scenario(ctrl, scen, label)
                    out = OUT / f"{label}_{scen}.json"
                    with open(out, "w") as f:
                        json.dump(r, f, indent=2)
                    cum = r["cum_rf_total"]
                    mdf = r["max_df"]
                    paper_ddic = PAPER_REF[scen]["ddic"]
                    diff = _diff_pct(cum, paper_ddic)
                    rows.append({
                        "run": run, "suffix": suffix, "scen": scen,
                        "cum_rf": cum, "max_df": mdf, "diff_vs_paper": diff,
                    })
                    print(f"  {label:55s} {scen}  cum_rf={cum:+.4f}  "
                          f"max_df={mdf:.4f}  diff={diff}")
                except Exception as e:
                    print(f"  [ERR] {label} {scen}: {e}")

    print("\n========= BEST vs FINAL diff (vs paper DDIC ref) =========")
    by_run = {}
    for r in rows:
        key = (r["run"], r["scen"])
        by_run.setdefault(key, {})[r["suffix"]] = r

    for (run, scen), d in by_run.items():
        b = d.get("best")
        f = d.get("final")
        if not (b and f):
            continue
        print(f"{run:50s} {scen:14s} best={b['cum_rf']:+.4f} ({b['diff_vs_paper']}) "
              f"final={f['cum_rf']:+.4f} ({f['diff_vs_paper']})")

    summary = OUT / "best_vs_final_summary.json"
    with open(summary, "w") as fh:
        json.dump(rows, fh, indent=2)
    print(f"\nSaved: {summary}")


if __name__ == "__main__":
    main()
