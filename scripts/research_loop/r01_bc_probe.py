"""R01 exp4 — BC sanity probe.

Phase B prereq: confirm ANDES IEEEG1 + EXST1 add API works on Kundur full case.
Phase C-pre:    H0 sweep {20, 30, 50, 80}s, check power flow + 5-step TDS smoke.

Output: results/research_loop/r01_bc_probe.json (consumed by R01 verdict).

Usage (via daemon, env vars only):
    /home/wya/andes_venv/bin/python scripts/research_loop/r01_bc_probe.py

This is a sanity probe, not a training run. ~5-10 min wall.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

OUT_PATH = ROOT / "results" / "research_loop" / "r01_bc_probe.json"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def _safe_call(fn, *args, **kwargs):
    """Run fn, capture exception trace as JSON-friendly dict."""
    try:
        return {"ok": True, "result": fn(*args, **kwargs)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error_type": type(exc).__name__,
                "error_msg": str(exc),
                "trace": traceback.format_exc(limit=12)}


def probe_governor_add():
    """Probe B: ANDES IEEEG1 + EXST1 add API on Kundur full case.

    Strategy: load case, after setup() try add IEEEG1 then EXST1, then PFlow.
    Failure modes captured: model-not-found, missing fields, pflow not converging.
    """
    import andes
    case = andes.get_case("kundur/kundur_full.xlsx")
    if not Path(case).exists():
        return {"loaded": False, "reason": f"case missing: {case}"}

    ss = andes.load(case, setup=True, no_output=True, default_config=True)
    syn_idxs = list(ss.GENROU.idx.v) if ss.GENROU.n > 0 else []

    out = {
        "loaded": True,
        "case": case,
        "n_genrou": ss.GENROU.n,
        "n_gencls": ss.GENCLS.n if hasattr(ss, "GENCLS") else 0,
        "syn_idxs": syn_idxs,
        "ieeeg1_add": [],
        "exst1_add":  [],
        "pflow_after_add": None,
    }

    # Try add IEEEG1 to first GENROU only (cheapest probe)
    if syn_idxs:
        target_syn = syn_idxs[0]
        out["ieeeg1_add"].append(_safe_call(
            ss.IEEEG1.add,
            idx=f"PROBE_GOV_{target_syn}", syn=target_syn,
        ))
        out["exst1_add"].append(_safe_call(
            ss.EXST1.add,
            idx=f"PROBE_AVR_{target_syn}", syn=target_syn,
        ))

    out["pflow_after_add"] = _safe_call(lambda: ss.PFlow.run() and bool(ss.PFlow.converged))
    return out


def probe_h0_sweep(h0_values=(20.0, 30.0, 50.0, 80.0)):
    """Probe C-pre: power flow + 5-step TDS smoke for H0 candidates.

    Uses V2 env factory pattern: monkey-patch VSG_M0 then build full system.
    """
    from env.andes.andes_vsg_env_v2 import AndesMultiVSGEnvV2

    out = {"sweep": []}
    for h0 in h0_values:
        m0 = 2.0 * h0
        entry = {"h0_s": h0, "m0_s": m0, "pflow": None, "tds_5step": None}

        # Subclass override to avoid leaking M0 across runs
        cls_name = f"V2_M0_{int(m0)}"
        cls = type(cls_name, (AndesMultiVSGEnvV2,), {"VSG_M0": m0})

        try:
            env = cls(random_disturbance=False, comm_fail_prob=0.0)
            env.reset(delta_u={"bus": 7, "delta_p": 0.10})  # tiny LS for build sanity
            entry["pflow"] = {"ok": True, "tds_t_after_reset": float(env.ss.dae.t)}

            tds_ok = True
            for _step in range(5):
                # neutral action (a=0 → ΔM=0, ΔD=0); paper-faithful
                actions = {i: np.zeros(2, dtype=np.float32)
                           for i in range(env.N_AGENTS)}
                _, _, done, info = env.step(actions)
                if info.get("tds_failed", False):
                    tds_ok = False
                    break
                if done:
                    break
            entry["tds_5step"] = {"ok": tds_ok, "tds_failed_flag": not tds_ok}
            env.close()
        except Exception as exc:  # noqa: BLE001
            entry["pflow"] = {"ok": False, "error_type": type(exc).__name__,
                              "error_msg": str(exc),
                              "trace": traceback.format_exc(limit=8)}
            entry["tds_5step"] = {"ok": False, "skipped_due_to_pflow": True}

        out["sweep"].append(entry)
    return out


def main():
    print("[R01_BC_probe] start", flush=True)
    report = {
        "version": "r01_bc_probe.v1",
        "lambda_smooth_env": os.environ.get("LAMBDA_SMOOTH", "(unset)"),
        "phase_B_governor_add": _safe_call(probe_governor_add),
        "phase_C_h0_sweep":     _safe_call(probe_h0_sweep),
    }
    OUT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[R01_BC_probe] wrote {OUT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
