"""一键生成所有 model variant 的 fig6/7/8/9 (LS1/LS2 时序).

Auto-discover DDIC ckpt labels from results/andes_eval_paper_specific_v2_envV2_hetero/,
然后为每个 ckpt 自动建子目录 + 跑 figs6_9_ls_traces.py.

子目录命名: paper/figures/v2env_<ckpt_label>/

Usage:
    python paper/figure_scripts/run_all_variants.py
    python paper/figure_scripts/run_all_variants.py --top 4   # 只跑 top 4 by 6-axis
    python paper/figure_scripts/run_all_variants.py --label ddic_balanced_seed46_best  # 单跑
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).parent
EVAL_DIR = ROOT / "results" / "andes_eval_paper_specific_v2_envV2_hetero"
RANKING_JSON = ROOT / "results" / "andes_paper_alignment_6axis_2026-05-07.json"


def discover_labels() -> list[str]:
    """Auto-discover all DDIC ckpt labels from eval dir."""
    if not EVAL_DIR.exists():
        return []
    files = os.listdir(EVAL_DIR)
    labels = sorted(set(
        f.replace("_load_step_1.json", "").replace("_load_step_2.json", "")
        for f in files if f.endswith(".json") and f.startswith("ddic_")
    ))
    return labels


def top_by_6axis(n: int) -> list[str]:
    """Top N DDIC labels ranked by 6-axis mean overall score."""
    if not RANKING_JSON.exists():
        print(f"[WARN] {RANKING_JSON.name} missing, falling back to alphabetical.")
        return discover_labels()[:n]
    d = json.load(open(RANKING_JSON))
    rankings = d.get("rankings", [])
    return [lbl for lbl, _info in rankings[:n] if "ddic" in lbl]


def render_variant(label: str) -> bool:
    """Run figs6_9_ls_traces.py for one DDIC label."""
    env = os.environ.copy()
    env["PAPER_FIG_DDIC_LABEL"] = label
    env.pop("PAPER_FIG_VARIANT", None)  # let _common auto-derive
    print(f"\n=== Rendering variant: {label} ===")
    r = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "figs6_9_ls_traces.py")],
        env=env, cwd=str(SCRIPT_DIR),
    )
    return r.returncode == 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=0,
                    help="Only run top N by 6-axis (default: all)")
    ap.add_argument("--label", type=str, default="",
                    help="Run a single DDIC label only")
    ap.add_argument("--list", action="store_true",
                    help="List discovered labels and exit")
    args = ap.parse_args()

    if args.label:
        labels = [args.label]
    elif args.top > 0:
        labels = top_by_6axis(args.top)
    else:
        labels = [l for l in discover_labels() if "ddic" in l]

    if args.list:
        print(f"Found {len(labels)} DDIC labels:")
        for l in labels:
            print(f"  {l}")
        return

    if not labels:
        print("[ERROR] No DDIC labels discovered."); sys.exit(1)

    print(f"Will render {len(labels)} variants:")
    for l in labels:
        print(f"  - paper/figures/v2env_{l[5:] if l.startswith('ddic_') else l}/")
    print()

    failed = []
    for lbl in labels:
        if not render_variant(lbl):
            failed.append(lbl)

    print(f"\n=== Done: {len(labels) - len(failed)}/{len(labels)} succeeded ===")
    if failed:
        print(f"Failed: {failed}"); sys.exit(1)


if __name__ == "__main__":
    main()
