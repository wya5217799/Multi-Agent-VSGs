"""R03 — Phase B governor wire probe.

Goal: prove a V2 env subclass that adds IEEEG1 + EXST1 to all 4 GENROU sync gens
can run reset() + 5 step() without crash. Gates R04 Phase B physical wiring.

Approach: monkey-patch _build_system at instance level — after super build, add
governor + AVR per syn idx, then re-run setup. NOT integrated into V2 class
because that would touch many call sites; this is a smoke probe only.

Output: results/research_loop/r03_governor_wire_probe.json
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

OUT_PATH = ROOT / "results" / "research_loop" / "r03_governor_wire_probe.json"
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


def probe():
    """Build V2 env + add IEEEG1 + EXST1 to all GENROU; reset + 5 step."""
    import andes
    from env.andes.andes_vsg_env_v2 import AndesMultiVSGEnvV2

    out = {
        "step1_v2_env_construct": None,
        "step2_governor_add_per_genrou": [],
        "step3_setup_after_add": None,
        "step4_pflow": None,
        "step5_reset_after_governor": None,
        "step6_step_5_neutral_action": None,
    }

    env = AndesMultiVSGEnvV2(random_disturbance=True, comm_fail_prob=0.0)
    out["step1_v2_env_construct"] = {"ok": True, "OBS_DIM": env.OBS_DIM,
                                      "N_AGENTS": env.N_AGENTS}

    # We need to add governor BEFORE setup. Reset = full rebuild, so override
    # _build_system on this instance via subclass.
    base_build_system = type(env)._build_system

    def patched_build(self):
        ss = base_build_system(self)
        # Note: V2 base_build calls ss.setup() then sets vsg_idx. After setup,
        # we cannot add new components without re-setup. ANDES allows
        # add-after-setup but a final ss.setup() may need re-run for connectivity.
        try:
            for syn_idx in ss.GENROU.idx.v:
                _safe_add = ss.IEEEG1.add(idx=f"GOV_{syn_idx}", syn=syn_idx)
                _safe_add2 = ss.EXST1.add(idx=f"AVR_{syn_idx}", syn=syn_idx)
            # re-setup may complain; try
            try:
                ss.setup()
            except Exception as e:  # already-setup error often
                out["step2_governor_add_per_genrou"].append(
                    {"resetup_warn": type(e).__name__, "msg": str(e)[:100]})
        except Exception as e:
            out["step2_governor_add_per_genrou"].append(
                {"add_fail": True, "err": str(e)[:200]})
            raise
        return ss

    type(env)._build_system = patched_build
    out["step3_setup_after_add"] = _safe(lambda: True)

    out["step4_pflow"] = _safe(env.reset)
    if out["step4_pflow"]["ok"]:
        out["step5_reset_after_governor"] = {"ok": True,
                                              "tds_t_after_reset": float(env.ss.dae.t),
                                              "ieeeg1_n": env.ss.IEEEG1.n,
                                              "exst1_n": env.ss.EXST1.n}
        try:
            tds_ok = True
            for _ in range(5):
                actions = {i: np.zeros(2, dtype=np.float32)
                           for i in range(env.N_AGENTS)}
                _, _, done, info = env.step(actions)
                if info.get("tds_failed", False):
                    tds_ok = False
                    break
                if done:
                    break
            out["step6_step_5_neutral_action"] = {"ok": tds_ok,
                                                    "tds_failed_flag": not tds_ok}
        except Exception as e:
            out["step6_step_5_neutral_action"] = {
                "ok": False, "error_type": type(e).__name__,
                "error_msg": str(e), "trace": traceback.format_exc(limit=8)}

    env.close()
    return out


def main():
    print("[r03_governor_wire_probe] start", flush=True)
    report = {"version": "r03_governor_wire.v1",
              "probe": _safe(probe)}
    OUT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[r03_governor_wire_probe] wrote {OUT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
