"""R08 H scan + governor on/off — physics validation, no SAC.

Per quality_reports/plans/2026-05-07_physics_validation_plan.md (V1+V2+V3).
Tests: does ANDES Kundur respond to H change? Is governor necessary?

Output: results/research_loop/r08_h_scan.json + console summary.

Run via WSL ANDES venv:
    /home/wya/andes_venv/bin/python scripts/research_loop/r08_h_scan.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from env.andes.andes_vsg_env_v2 import AndesMultiVSGEnvV2  # noqa: E402
from env.andes.andes_vsg_env_v3 import AndesMultiVSGEnvV3  # noqa: E402

SCENARIOS = {
    "load_step_1": {"PQ_Bus14": -2.48},
    "load_step_2": {"PQ_Bus15": 1.88},
}


def run_one(env_cls, h_val: float, scen: str, delta_u: dict, label: str) -> dict:
    """Run 1 episode (50 step) with H_all=h_val forced, zero SAC action.

    Returns: {label, scen, h, max_df, final_df, settling, tds_failed}
    """
    env = env_cls(random_disturbance=False, comm_fail_prob=0.0)
    env.seed(42)
    # Force H_all = h_val (M = 2H), instance-level, before reset
    m_target = 2.0 * h_val
    env.M0 = np.full(env.N_AGENTS, m_target)

    try:
        obs = env.reset(delta_u=delta_u)
    except Exception as e:
        env.close() if hasattr(env, "close") else None
        return {
            "label": label, "scen": scen, "h": h_val,
            "max_df": None, "final_df": None, "settling": None,
            "tds_failed": True, "error": str(e)[:100],
        }

    F_NOM = env.FN
    df_history = []
    max_df = 0.0
    tds_failed = False

    for step in range(env.STEPS_PER_EPISODE):
        actions = {i: np.zeros(2, dtype=np.float32) for i in range(env.N_AGENTS)}
        try:
            obs, rewards, done, info = env.step(actions)
        except Exception as e:
            tds_failed = True
            print(f"  [step {step} err] {label} {scen}: {str(e)[:80]}")
            break

        if info.get("tds_failed", False):
            tds_failed = True
            break

        delta_f_max = float(np.max(np.abs(info["freq_hz"] - F_NOM)))
        df_history.append(delta_f_max)
        max_df = max(max_df, delta_f_max)

        if done:
            break

    final_df = df_history[-1] if df_history else None
    # Settling: time when |delta_f| stays < 0.02 + final_df for ≥ 0.5s window
    settling = None
    if df_history and final_df is not None:
        band = 0.02 + final_df
        for i in range(len(df_history) - 3):
            if all(d < band for d in df_history[i:i + 3]):  # 3-step ≈ 0.6s window
                settling = i * 0.2  # DT = 0.2s
                break
        if settling is None:
            settling = float("inf")

    try:
        env.close()
    except Exception:
        pass

    return {
        "label": label, "scen": scen, "h": h_val,
        "max_df": max_df if max_df > 0 else None,
        "final_df": final_df,
        "settling": settling,
        "tds_failed": tds_failed,
    }


def main():
    results = []

    print("=" * 70)
    print("V1: H scan on V2 env (no governor), zero SAC action")
    print("=" * 70)
    for h in [10, 30, 100, 300]:  # V1-a/b/c/d
        for scen, du in SCENARIOS.items():
            r = run_one(AndesMultiVSGEnvV2, h, scen, du, f"V1_H{h}_noGov")
            mdf = f"{r['max_df']:.3f}" if r["max_df"] else "FAIL"
            tds = " (TDS_FAIL)" if r["tds_failed"] else ""
            print(f"  V1 H={h:>3} {scen}: max_df={mdf}{tds}")
            results.append(r)

    print("\n" + "=" * 70)
    print("V2: governor on/off at H=10")
    print("=" * 70)
    for env_cls, label in [(AndesMultiVSGEnvV2, "V2a_H10_noGov"),
                            (AndesMultiVSGEnvV3, "V2b_H10_gov")]:
        for scen, du in SCENARIOS.items():
            r = run_one(env_cls, 10.0, scen, du, f"{label}_{scen}")
            mdf = f"{r['max_df']:.3f}" if r["max_df"] else "FAIL"
            tds = " (TDS_FAIL)" if r["tds_failed"] else ""
            print(f"  {label} {scen}: max_df={mdf}{tds}")
            results.append(r)

    print("\n" + "=" * 70)
    print("V3: H=300 + governor on (final showstopper)")
    print("=" * 70)
    for scen, du in SCENARIOS.items():
        r = run_one(AndesMultiVSGEnvV3, 300.0, scen, du, f"V3_H300_gov_{scen}")
        mdf = f"{r['max_df']:.3f}" if r["max_df"] else "FAIL"
        tds = " (TDS_FAIL)" if r["tds_failed"] else ""
        print(f"  V3 H=300 gov {scen}: max_df={mdf}{tds}")
        results.append(r)

    out = ROOT / "results" / "research_loop" / "r08_h_scan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nWritten {out}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY (max_df by config × LS)")
    print("=" * 70)
    print(f"{'config':<25} {'LS1 max_df':>12} {'LS2 max_df':>12}")
    print("-" * 50)
    by_label = {}
    for r in results:
        # Group by label without _scen suffix
        base = r["label"].replace("_load_step_1", "").replace("_load_step_2", "")
        by_label.setdefault(base, {})[r["scen"]] = r["max_df"]
    for lbl, scns in by_label.items():
        ls1 = scns.get("load_step_1")
        ls2 = scns.get("load_step_2")
        ls1s = f"{ls1:.3f}" if ls1 else "FAIL"
        ls2s = f"{ls2:.3f}" if ls2 else "FAIL"
        print(f"{lbl:<25} {ls1s:>12} {ls2s:>12}")

    print(f"\npaper benchmark: LS1=0.13 LS2=0.10")


if __name__ == "__main__":
    main()
