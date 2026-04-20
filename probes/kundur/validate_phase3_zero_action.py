"""Phase 3 validation: zero-action Python bridge episode.

Runs 50 steps with action=zeros through KundurSimulinkEnv (Simulink bridge).
Evaluates Section 5.2 criteria from:
  docs/superpowers/plans/2026-04-18-kundur-pe-contract-fix.md

Run from repo root:
    python probes/kundur/validate_phase3_zero_action.py

IntW note: omega_ES{i} IS the IntW output (IntW integrates to omega, then clipped
to [0.7, 1.3]). No separate IntW_ES{i} ToWorkspace needed; saturation tracked via
info["omega_saturated"].
"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import numpy as np

from env.simulink.kundur_simulink_env import KundurSimulinkEnv
from scenarios.kundur.config_simulink import VSG_P0_SBASE

# ---------------------------------------------------------------------------
# Validation parameters
# ---------------------------------------------------------------------------
N_STEPS = 50
STEADY_START = 40   # 0-indexed; steps [40, 50) = paper indices 41-50
STEADY_END = 50

# Section 5.2 thresholds
PE_REL_TOL = 0.05       # 5% max relative Pe deviation
OMEGA_DEV_TOL = 0.002   # 0.002 pu = ±0.1 Hz at 50 Hz
DELTA_DRIFT_TOL = 1.0   # 1 deg/step max consecutive-step drift


def _fmt_arr(arr: np.ndarray, fmt: str = ".4f") -> str:
    return "[" + ", ".join(format(v, fmt) for v in arr) + "]"


def run_validation() -> bool:
    print("=" * 72)
    print("Phase 3: Zero-Action Physical Validation (Python Bridge)")
    print("=" * 72)
    print(f"VSG_P0_SBASE (reference, system-base pu): {_fmt_arr(VSG_P0_SBASE)}")
    print(f"Steps: {N_STEPS}, steady-state window: {STEADY_START+1}-{STEADY_END}")
    print()

    # training=False disables random comm_mask so validation is deterministic
    env = KundurSimulinkEnv(training=False)

    omegas: list[np.ndarray] = []
    pes: list[np.ndarray] = []
    deltas_deg: list[np.ndarray] = []
    omega_saturated_any = False
    n_steps_done = 0

    try:
        print("Resetting (warmup ~0.5 s)...")
        _obs, _info = env.reset()
        print(f"POST-WARMUP _delta_prev_deg: {env.bridge._delta_prev_deg}")
        print(f"POST-WARMUP _Pe_prev:        {env.bridge._Pe_prev}")
        print("Reset OK. Running zero-action episode...\n")

        action = np.zeros(env.action_space.shape, dtype=np.float32)

        for step in range(N_STEPS):
            obs, reward, terminated, truncated, info = env.step(action)

            omega = info["omega"].copy()
            pe = info["P_es"].copy()
            delta = env.bridge._delta_prev_deg.copy()

            omegas.append(omega)
            pes.append(pe)
            deltas_deg.append(delta)
            n_steps_done += 1

            if info["omega_saturated"]:
                omega_saturated_any = True

            if step < 3 or step % 10 == 9:
                print(
                    f"  step {step+1:3d}  t={info['sim_time']:.1f}s"
                    f"  ω={_fmt_arr(omega, '.4f')}"
                    f"  Pe={_fmt_arr(pe, '.4f')}"
                    f"  sat={'Y' if info['omega_saturated'] else 'n'}"
                )

            if terminated:
                print(f"\n  !! sim terminated at step {step+1}")
                break
    finally:
        env.close()

    if n_steps_done == 0:
        print("ERROR: no steps completed — validation aborted")
        return False

    arr_omega = np.array(omegas)      # (steps, 4)
    arr_pe = np.array(pes)            # (steps, 4)
    arr_delta = np.array(deltas_deg)  # (steps, 4)

    sw_end = min(STEADY_END, n_steps_done)
    sw_start = min(STEADY_START, sw_end)
    sw_omega = arr_omega[sw_start:sw_end]
    sw_pe = arr_pe[sw_start:sw_end]
    sw_delta = arr_delta[sw_start:sw_end]
    sw_len = sw_omega.shape[0]

    print()
    print(f"Steady-state window: steps {sw_start+1}–{sw_end} ({sw_len} steps)")
    print("-" * 72)

    # ------------------------------------------------------------------
    # Criterion 1: Pe deviation < 5% in steady-state window
    # ------------------------------------------------------------------
    pe_ref = VSG_P0_SBASE  # shape (4,)
    pe_rel = np.abs(sw_pe - pe_ref) / np.abs(pe_ref)
    max_pe_rel = pe_rel.max(axis=0)
    c1_pass = bool(np.all(max_pe_rel < PE_REL_TOL))

    print(f"\n[C1] Pe deviation < {PE_REL_TOL*100:.0f}% (system-base pu):")
    for i in range(4):
        tag = "PASS" if max_pe_rel[i] < PE_REL_TOL else "FAIL"
        print(
            f"  ES{i+1}: max_rel={max_pe_rel[i]*100:.2f}%"
            f"  mean_Pe={sw_pe[:, i].mean():.4f}"
            f"  ref={pe_ref[i]:.4f}"
            f"  [{tag}]"
        )
    print(f"  → C1: {'PASS' if c1_pass else 'FAIL'}")

    # ------------------------------------------------------------------
    # Criterion 2: IntW (omega) never saturated [0.7, 1.3] pu (full run)
    # Note: per Section 5.4 this does NOT hard-block Phase 4; it's a warning.
    # ------------------------------------------------------------------
    c2_pass = not omega_saturated_any

    print(f"\n[C2] IntW (omega) never saturated [0.7, 1.3] pu (full run):")
    print(f"  Saturation triggered: {omega_saturated_any}")
    print(f"  (omega IS IntW output — dedicated IntW_ES ToWorkspace not needed)")
    print(f"  → C2: {'PASS' if c2_pass else 'WARN (soft, non-blocking per Section 5.4)'}")

    # ------------------------------------------------------------------
    # Criterion 3: omega deviation < 0.002 pu in steady-state window
    # ------------------------------------------------------------------
    omega_dev = np.abs(sw_omega - 1.0)
    max_omega_dev = omega_dev.max(axis=0)
    c3_pass = bool(np.all(max_omega_dev < OMEGA_DEV_TOL))

    print(f"\n[C3] omega deviation < {OMEGA_DEV_TOL} pu (= ±{OMEGA_DEV_TOL*50:.2f} Hz):")
    for i in range(4):
        tag = "PASS" if max_omega_dev[i] < OMEGA_DEV_TOL else "FAIL"
        print(f"  ES{i+1}: max|omega-1|={max_omega_dev[i]:.5f} pu  [{tag}]")
    print(f"  → C3: {'PASS' if c3_pass else 'FAIL'}")

    # ------------------------------------------------------------------
    # Criterion 4: delta drift < 1 deg/step in steady-state window
    # ------------------------------------------------------------------
    if sw_len >= 2:
        drift = np.abs(np.diff(sw_delta, axis=0))   # (sw_len-1, 4)
        max_drift = drift.max(axis=0)
        c4_pass = bool(np.all(max_drift < DELTA_DRIFT_TOL))
    else:
        max_drift = np.full(4, np.nan)
        c4_pass = False

    print(f"\n[C4] delta drift < {DELTA_DRIFT_TOL:.0f} deg/step:")
    for i in range(4):
        tag = "PASS" if max_drift[i] < DELTA_DRIFT_TOL else "FAIL"
        print(f"  ES{i+1}: max_drift={max_drift[i]:.3f} deg/step  [{tag}]")
    print(f"  → C4: {'PASS' if c4_pass else 'FAIL'}")

    # ------------------------------------------------------------------
    # Verdict (C2 is soft; hard gate = C1, C3, C4)
    # ------------------------------------------------------------------
    hard_pass = c1_pass and c3_pass and c4_pass

    print()
    print("=" * 72)
    if hard_pass:
        print("VERDICT: ALL PASS  →  proceed to Phase 4 (smoke + short training)")
    else:
        failed = [f"C{i}" for i, p in enumerate([c1_pass, None, c3_pass, c4_pass], 1)
                  if p is not None and not p]
        print(f"VERDICT: FAIL ({', '.join(failed)})  →  trigger Phase 5 (IC calibration)")
    print("=" * 72)

    return hard_pass


if __name__ == "__main__":
    ok = run_validation()
    sys.exit(0 if ok else 1)
