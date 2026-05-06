"""V2 env D₀ sweep — 找 max_df 减半且保持 sync 量级的最优 baseline.

Verdict (2026-05-06): D₀=[20,16,4,8] 是 sync 量级最优 (LS1 cum_rf=-1.66 vs paper -1.61).

Usage:
    EVAL_PAPER_SPEC_ENV=v2 \\
    /home/wya/andes_venv/bin/python scenarios/kundur/_v2_d0_sweep.py
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ["EVAL_PAPER_SPEC_ENV"] = "v2"

CONFIGS = [
    [10, 8, 2, 4],
    [20, 16, 4, 8],
    [30, 24, 6, 12],
    [40, 32, 8, 16],
]


def reload_env_module():
    for mod in [
        "env.andes.andes_vsg_env_v2",
        "scenarios.kundur._eval_paper_specific",
    ]:
        if mod in sys.modules:
            del sys.modules[mod]


def main() -> None:
    rows = []
    for d0 in CONFIGS:
        os.environ["ANDES_V2_D0"] = ",".join(str(x) for x in d0)
        tag = "_".join(str(x) for x in d0)
        os.environ["EVAL_PAPER_SPEC_OUT_DIR"] = str(
            ROOT / "results" / f"andes_eval_specific_v2_d0_{tag}"
        )
        reload_env_module()

        from scenarios.kundur._eval_paper_specific import (
            eval_scenario,
            controller_nocontrol,
            _make_adaptive_controller,
            SAVE_DIR,
        )
        from env.andes.andes_vsg_env_v2 import AndesMultiVSGEnvV2

        os.makedirs(SAVE_DIR, exist_ok=True)
        print(f"\n=== D0 = {AndesMultiVSGEnvV2.D0_HETEROGENEOUS.tolist()} ===")

        adaptive = _make_adaptive_controller(K_H=10.0, K_D=400.0)
        for ctrl_name, ctrl in [
            ("no_control", controller_nocontrol),
            ("adaptive_K10_K400", adaptive),
        ]:
            for scen in ["load_step_1", "load_step_2"]:
                r = eval_scenario(ctrl, scen, ctrl_name)
                out_p = os.path.join(SAVE_DIR, f"{ctrl_name}_{scen}.json")
                with open(out_p, "w") as f:
                    json.dump(r, f, indent=2)
                cum, mdf = r["cum_rf_total"], r["max_df"]
                rows.append({"d0": d0, "ctrl": ctrl_name, "scen": scen,
                             "cum_rf": cum, "max_df": mdf})
                print(f"  {ctrl_name:22s} {scen}  cum_rf={cum:+.4f}  max_df={mdf:.4f}")

    print("\n========= SUMMARY (V2 D0 sweep) =========")
    for r in rows:
        print(f"{str(r['d0']):24s} {r['ctrl']:22s} {r['scen']:14s} "
              f"cum={r['cum_rf']:+.4f} max_df={r['max_df']:.4f}")

    out_json = ROOT / "results" / "andes_v2_d0_sweep_summary.json"
    with open(out_json, "w") as f:
        json.dump({"configs": CONFIGS, "rows": rows}, f, indent=2)
    print(f"\nSaved: {out_json}")


if __name__ == "__main__":
    main()
