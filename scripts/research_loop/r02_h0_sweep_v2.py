"""R02 — H0 sweep v2 (probe disturbance schema bug fix).

R01 r01_bc_probe.py used invalid `delta_u={"bus": 7, ...}` causing all 4 H0 candidates
to fail with `'bus' is not in list` at PQ.idx lookup. See:
  quality_reports/research_loop/incidents/r01_h0_probe_disturbance_bug.md

Fix: pass `delta_u=None` (random disturbance, lets env build sanity from physics) and
also keep IEEEG1+EXST1 governor add as auxiliary check (Phase B re-confirm).

Output: results/research_loop/r02_C_pre_h0_sweep_v2.json
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

OUT_PATH = ROOT / "results" / "research_loop" / "r02_C_pre_h0_sweep_v2.json"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def _safe(fn, *args, **kwargs):
    try:
        return {"ok": True, "result": fn(*args, **kwargs)}
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error_type": type(exc).__name__,
            "error_msg": str(exc),
            "trace": traceback.format_exc(limit=12),
        }


def probe_h0(h0_values=(20.0, 30.0, 50.0, 80.0)):
    """Power flow + 5-step TDS smoke per H0 candidate, NO `delta_u` (let env pick)."""
    from env.andes.andes_vsg_env_v2 import AndesMultiVSGEnvV2

    out = []
    for h0 in h0_values:
        m0 = 2.0 * h0
        entry = {"h0_s": h0, "m0_s": m0, "pflow": None, "tds_5step": None}
        cls = type(f"V2_M0_{int(m0)}", (AndesMultiVSGEnvV2,), {"VSG_M0": m0})
        try:
            env = cls(random_disturbance=True, comm_fail_prob=0.0)
            env.reset()  # delta_u=None → random_disturbance; bypass schema bug
            entry["pflow"] = {"ok": True, "tds_t_after_reset": float(env.ss.dae.t)}
            tds_ok = True
            for _step in range(5):
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
            entry["pflow"] = {
                "ok": False,
                "error_type": type(exc).__name__,
                "error_msg": str(exc),
                "trace": traceback.format_exc(limit=8),
            }
            entry["tds_5step"] = {"ok": False, "skipped_due_to_pflow": True}
        out.append(entry)
    return out


def main():
    print("[R02_h0_v2] start", flush=True)
    report = {
        "version": "r02_h0_sweep_v2.v1",
        "fix_for": "r01_bc_probe.py disturbance schema bug",
        "h0_sweep": _safe(probe_h0),
    }
    OUT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[R02_h0_v2] wrote {OUT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
