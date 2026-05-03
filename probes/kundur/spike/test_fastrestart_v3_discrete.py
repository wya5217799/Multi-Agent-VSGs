"""FastRestart compatibility + physics-sanity microtest for v3 Discrete.

Design (γγ 2026-05-03):
  Wall-time sequence with the same loaded model, sim StopTime=1.0:
    a) FastRestart='off', sim() once       -> wall_off_1, omega_off_1
    b) FastRestart='off', sim() again      -> wall_off_2 (cold-cold baseline)
    c) FastRestart='on',  sim() once       -> wall_on_first (FR snapshot save)
    d) FastRestart='on',  sim() again      -> wall_on_repeat (THE FR speedup)
    e) FastRestart='on',  reassignin M_1, sim() -> wall_on_param_change
    f) Physics gate: max abs (omega_off_1 - omega_on_repeat) / max(abs(omega_off_1))
       must be < 1e-5 (paper-anchor signal preserved within numerical noise).

Verdict map:
  - sim() under FR='on' raises -> FR_INCOMPAT (do NOT integrate)
  - omega match fails (rel err >= 1e-5) -> FR_PHYSICS_REGRESSION (do NOT integrate)
  - wall_on_repeat > 0.7 * wall_off_1 -> FR_NEGLIGIBLE_GAIN (impl cost not justified)
  - else -> FR_VIABLE (integrate via opt-in BridgeConfig flag, default off, per
    feedback_optimization_no_perf_regression rule)

Runs in its own Python subprocess so it does not collide with the alpha
probe_state run in another process.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(r"C:/Users/27443/Desktop/Multi-Agent-VSGs-discrete")
MDL_DIR = ROOT / "scenarios/kundur/simulink_models"
MDL = "kundur_cvs_v3_discrete"


def _setup_workspace(eng) -> None:
    eng.eval(
        "load(fullfile('"
        + str(MDL_DIR).replace("\\", "/")
        + "', '"
        + MDL
        + "_runtime.mat'));",
        nargout=0,
    )
    # M_<i> / D_<i> are RL-controlled — set per-step in production via
    # bridge.step(), not persisted to runtime.mat. For this microtest we
    # seed them to ESS_M0_default / ESS_D0_default (matches bridge cfg
    # m0_default / d0_default for v3 Discrete CVS profile).
    for i in range(1, 5):
        eng.eval(f"M_{i} = 24.0;", nargout=0)
        eng.eval(f"D_{i} = 4.5;", nargout=0)
    # push disturbances out
    for k in range(1, 5):
        eng.eval(f"Pm_step_t_{k} = 100.0;", nargout=0)
        eng.eval(f"Pm_step_amp_{k} = 0.0;", nargout=0)
    for g in range(1, 4):
        eng.eval(f"PmgStep_t_{g} = 100.0;", nargout=0)
        eng.eval(f"PmgStep_amp_{g} = 0.0;", nargout=0)
    eng.eval("LoadStep_t_bus14 = 100.0;", nargout=0)
    eng.eval("LoadStep_t_bus15 = 100.0;", nargout=0)


def _capture_omega_3(eng, mdl: str):
    """Pull omega_ts_3 (ES3) trajectory from base ws after sim() as ndarray."""
    import numpy as np
    return np.asarray(eng.eval("omega_ts_3.Data(:)", nargout=1)).ravel()


def _set_loggers_inf(eng, mdl: str) -> None:
    for sname in ("G1", "G2", "G3", "ES1", "ES2", "ES3", "ES4"):
        try:
            eng.set_param(
                f"{mdl}/W_omega_{sname}", "MaxDataPoints", "inf", nargout=0
            )
        except Exception:
            pass


def _timed_sim(eng, mdl: str, label: str):
    import numpy as np
    t0 = time.perf_counter()
    eng.eval(f"out = sim('{mdl}');", nargout=0)
    wall = time.perf_counter() - t0
    omega = np.asarray(
        eng.eval("out.get('omega_ts_3').Data(:)", nargout=1)
    ).ravel()
    print(f"  [{label}] wall={wall:.2f}s n_samples={len(omega)}")
    return wall, omega


def _max_rel_err(a, b) -> float:
    import numpy as np
    a = np.asarray(a).ravel()
    b = np.asarray(b).ravel()
    n = min(len(a), len(b))
    if n == 0:
        return float("inf")
    a_max = float(np.max(np.abs(a[:n]))) or 1.0
    return float(np.max(np.abs(a[:n] - b[:n]))) / a_max


def main() -> int:
    print("[FR microtest] starting independent MATLAB engine...")
    t_cold = time.perf_counter()
    import matlab.engine
    eng = matlab.engine.start_matlab()
    print(f"[FR microtest] engine cold start {time.perf_counter()-t_cold:.1f}s")

    eng.addpath(str(MDL_DIR).replace("\\", "/"), nargout=0)
    eng.eval(f"load_system(fullfile('{str(MDL_DIR).replace(chr(92), '/')}','{MDL}.slx'));", nargout=0)

    _setup_workspace(eng)
    _set_loggers_inf(eng, MDL)
    eng.set_param(MDL, "StopTime", "1.0", nargout=0)

    print("\n[FR microtest] (a) FastRestart=off, sim 1 ...")
    eng.set_param(MDL, "FastRestart", "off", nargout=0)
    t_off_1, om_off_1 = _timed_sim(eng, MDL, "off-1")

    print("\n[FR microtest] (b) FastRestart=off, sim 2 (cold-cold baseline) ...")
    t_off_2, om_off_2 = _timed_sim(eng, MDL, "off-2")

    print("\n[FR microtest] (c) FastRestart=on, sim 1 (snapshot save) ...")
    try:
        eng.set_param(MDL, "FastRestart", "on", nargout=0)
        t_on_first, om_on_first = _timed_sim(eng, MDL, "on-first")
    except Exception as e:
        print(f"[FR microtest] FR_INCOMPAT — sim under FR='on' raised: {type(e).__name__}: {e}")
        eng.exit()
        return 2

    print("\n[FR microtest] (d) FastRestart=on, sim 2 (REAL FR speedup) ...")
    t_on_repeat, om_on_repeat = _timed_sim(eng, MDL, "on-repeat")

    print("\n[FR microtest] (e) FastRestart=on, modify M_1=23.5, sim ...")
    eng.eval("M_1 = 23.5;", nargout=0)
    t_on_param, om_on_param = _timed_sim(eng, MDL, "on-param-tune")

    # restore M_1
    eng.eval("M_1 = 24.0;", nargout=0)
    eng.set_param(MDL, "FastRestart", "off", nargout=0)
    eng.exit()

    rel_off_to_on = _max_rel_err(om_off_1, om_on_repeat)
    rel_off_to_off = _max_rel_err(om_off_1, om_off_2)
    rel_on_to_param = _max_rel_err(om_on_repeat, om_on_param)

    print("\n=== Wall-time summary ===")
    print(f"  off-1            : {t_off_1:.2f}s")
    print(f"  off-2            : {t_off_2:.2f}s")
    print(f"  on-first (save)  : {t_on_first:.2f}s")
    print(f"  on-repeat (FR)   : {t_on_repeat:.2f}s   <-- THIS is the FR speedup")
    print(f"  on-param-tune    : {t_on_param:.2f}s")
    print(f"  speedup factor   : {t_off_1 / max(t_on_repeat, 0.01):.2f}x")

    print("\n=== Physics sanity (max rel err vs off-1) ===")
    print(f"  off-1 vs off-2     : {rel_off_to_off:.3e}  (numerical noise floor)")
    print(f"  off-1 vs on-repeat : {rel_off_to_on:.3e}  (FR vs no-FR; THIS must be < 1e-5)")
    print(f"  on-repeat vs param : {rel_on_to_param:.3e}  (param tune effect; expect non-zero, sanity = solver ran)")

    physics_ok = rel_off_to_on < 1e-5
    speed_ok = t_on_repeat < 0.7 * t_off_1
    print("\n=== VERDICT ===")
    if not physics_ok:
        print(f"  FR_PHYSICS_REGRESSION: rel err {rel_off_to_on:.3e} >= 1e-5 threshold")
        return 3
    if not speed_ok:
        print(f"  FR_NEGLIGIBLE_GAIN: on-repeat {t_on_repeat:.2f}s vs off-1 {t_off_1:.2f}s — speedup < 1.43x")
        return 4
    print(f"  FR_VIABLE: physics OK ({rel_off_to_on:.2e} < 1e-5), speedup {t_off_1/t_on_repeat:.1f}x")
    print(f"  recommend: opt-in via BridgeConfig.fast_restart flag, default off")
    return 0


if __name__ == "__main__":
    sys.exit(main())
