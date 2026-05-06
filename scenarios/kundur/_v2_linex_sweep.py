"""V2 env NEW_LINE_X sweep — 验证拉长 ESS 接入线对 max_df 的影响.

Verdict (2026-05-06): 0.20 sweet spot. 0.30 cum_rf 超调, 0.40 max_df 反升, 0.60 power flow 发散.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ["EVAL_PAPER_SPEC_ENV"] = "v2"
os.environ["ANDES_V2_D0"] = "20,16,4,8"

CONFIGS = [0.10, 0.20, 0.30, 0.40, 0.60]


def reload_env_module():
    for mod in [
        "env.andes.andes_vsg_env_v2",
        "scenarios.kundur._eval_paper_specific",
    ]:
        if mod in sys.modules:
            del sys.modules[mod]


def main() -> None:
    rows = []
    for line_x in CONFIGS:
        os.environ["ANDES_V2_LINE_X"] = str(line_x)
        os.environ["EVAL_PAPER_SPEC_OUT_DIR"] = str(
            ROOT / "results" / f"andes_eval_specific_v2_linex_{line_x:.2f}"
        )
        reload_env_module()

        from scenarios.kundur._eval_paper_specific import (
            eval_scenario,
            controller_nocontrol,
            SAVE_DIR,
        )
        from env.andes.andes_vsg_env_v2 import AndesMultiVSGEnvV2

        os.makedirs(SAVE_DIR, exist_ok=True)
        print(f"\n=== NEW_LINE_X = {AndesMultiVSGEnvV2.NEW_LINE_X} ===")

        for scen in ["load_step_1", "load_step_2"]:
            try:
                r = eval_scenario(controller_nocontrol, scen, "no_control")
                with open(os.path.join(SAVE_DIR, f"no_control_{scen}.json"), "w") as f:
                    json.dump(r, f, indent=2)
                cum, mdf = r["cum_rf_total"], r["max_df"]
                rows.append({"line_x": line_x, "scen": scen,
                             "cum_rf": cum, "max_df": mdf})
                print(f"  no_control  {scen}  cum_rf={cum:+.4f}  max_df={mdf:.4f}")
            except Exception as e:
                print(f"  [DIVERGE] line_x={line_x} {scen}: {e}")
                rows.append({"line_x": line_x, "scen": scen, "diverge": str(e)})

    print("\n========= SUMMARY (V2 NEW_LINE_X sweep, D0=[20,16,4,8]) =========")
    for r in rows:
        if "diverge" in r:
            print(f"{r['line_x']:>8.2f}  {r['scen']:14s}  DIVERGE")
        else:
            print(f"{r['line_x']:>8.2f}  {r['scen']:14s}  "
                  f"cum_rf={r['cum_rf']:+.4f}  max_df={r['max_df']:.4f}")

    out_json = ROOT / "results" / "andes_v2_linex_sweep_summary.json"
    with open(out_json, "w") as f:
        json.dump({"d0": "20,16,4,8", "configs": CONFIGS, "rows": rows}, f, indent=2)
    print(f"\nSaved: {out_json}")


if __name__ == "__main__":
    main()
