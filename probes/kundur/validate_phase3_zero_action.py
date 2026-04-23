"""SPS Zero-Action Physical Validation (Python bridge episode).

Runs 50 steps with action=zeros through KundurSimulinkEnv (Simulink bridge).
Evaluates SPS candidate path invariants:
  - No structural warmup compensation needed (technical_reset_only).
  - Pe is near nominal immediately (by step 3-5, not only after long warmup).
  - No hidden clamp masquerades as stability (delta must not be stuck at -90 deg).

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

# SPS candidate path thresholds
PE_REL_TOL = 0.05       # 5% max relative Pe deviation
OMEGA_DEV_TOL = 0.002   # 0.002 pu = ±0.1 Hz at 50 Hz
DELTA_DRIFT_TOL = 1.0   # 1 deg/step max consecutive-step drift

# C0 — early Pe convergence (SPS key invariant)
EARLY_WINDOW_END = 5    # check steps 0-4 (0-indexed) for Pe near nominal
PE_EARLY_REL_TOL = 0.10  # 10% tolerance in early window (looser than steady-state)

# C5 — delta false-stability guard
DELTA_FALSE_STABLE_LO = -95.0   # deg; range (-95, -85) indicates IntD clamped at -90
DELTA_FALSE_STABLE_HI = -85.0   # deg


def _fmt_arr(arr: np.ndarray, fmt: str = ".4f") -> str:
    return "[" + ", ".join(format(v, fmt) for v in arr) + "]"


def run_validation() -> bool:
    print("=" * 72)
    print("SPS Zero-Action Physical Validation (Python Bridge)")
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
    # Criterion 0: Early Pe convergence (SPS key invariant)
    # Pe deviation from nominal < 10% by step EARLY_WINDOW_END.
    # On the SPS path there is no physical warmup ramp, so Pe must be
    # near nominal immediately after reset — not only after long warmup.
    # ------------------------------------------------------------------
    early_end = min(EARLY_WINDOW_END, n_steps_done)
    early_pe = arr_pe[:early_end]
    pe_ref = VSG_P0_SBASE  # shape (4,)

    if early_end > 0:
        early_pe_rel = np.abs(early_pe - pe_ref) / np.abs(pe_ref)
        max_early_pe_rel = early_pe_rel.max(axis=0)
        c0_pass = bool(np.all(max_early_pe_rel < PE_EARLY_REL_TOL))
    else:
        max_early_pe_rel = np.full(4, np.nan)
        c0_pass = False

    print(f"\n[C0] Early Pe convergence < {PE_EARLY_REL_TOL*100:.0f}% by step {EARLY_WINDOW_END} (SPS: no warmup ramp):")
    for i in range(4):
        tag = "PASS" if max_early_pe_rel[i] < PE_EARLY_REL_TOL else "FAIL"
        print(
            f"  ES{i+1}: max_rel={max_early_pe_rel[i]*100:.2f}%"
            f"  ref={pe_ref[i]:.4f}"
            f"  [{tag}]"
        )
    print(f"  → C0: {'PASS' if c0_pass else 'FAIL'}")

    # ------------------------------------------------------------------
    # Criterion 1: Pe deviation < 5% in steady-state window
    # ------------------------------------------------------------------
    pe_rel = np.abs(sw_pe - pe_ref) / np.abs(pe_ref)
    max_pe_rel = pe_rel.max(axis=0)
    c1_pass = bool(np.all(max_pe_rel < PE_REL_TOL))

    print(f"\n[C1] Pe deviation < {PE_REL_TOL*100:.0f}% in steady-state window (system-base pu):")
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
    # Soft criterion — does not hard-block but indicates initialization issue.
    # ------------------------------------------------------------------
    c2_pass = not omega_saturated_any

    print(f"\n[C2] IntW (omega) never saturated [0.7, 1.3] pu (full run):")
    print(f"  Saturation triggered: {omega_saturated_any}")
    print(f"  (omega IS IntW output — dedicated IntW_ES ToWorkspace not needed)")
    print(f"  → C2: {'PASS' if c2_pass else 'WARN (soft, non-blocking)'}")

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
    # Criterion 5: delta false-stability guard (SPS anti-clamp check)
    # If ALL steps in the full run have delta in (-95, -85) deg for any
    # agent, IntD is clamped at -90 deg — false stability, not real.
    # ------------------------------------------------------------------
    c5_pass = True
    false_stable_agents = []
    if n_steps_done > 0:
        for i in range(4):
            agent_delta = arr_delta[:, i]
            stuck = bool(
                np.all(
                    (agent_delta > DELTA_FALSE_STABLE_LO)
                    & (agent_delta < DELTA_FALSE_STABLE_HI)
                )
            )
            if stuck:
                c5_pass = False
                false_stable_agents.append(f"ES{i+1}")

    print(f"\n[C5] delta false-stability guard (no agent stuck in ({DELTA_FALSE_STABLE_LO:.0f}, {DELTA_FALSE_STABLE_HI:.0f}) deg):")
    if false_stable_agents:
        print(f"  FAIL: agents with IntD likely clamped at -90°: {', '.join(false_stable_agents)}")
    else:
        print(f"  No agent stuck in false-stability band.")
    print(f"  → C5: {'PASS' if c5_pass else 'FAIL'}")

    # ------------------------------------------------------------------
    # Verdict (C2 is soft; hard gate = C0, C1, C3, C4, C5)
    # ------------------------------------------------------------------
    hard_pass = c0_pass and c1_pass and c3_pass and c4_pass and c5_pass

    print()
    print("=" * 72)
    if hard_pass:
        print("VERDICT: ALL PASS  →  SPS initialization confirmed")
    else:
        failed = []
        for label, passed in [("C0", c0_pass), ("C1", c1_pass), ("C3", c3_pass), ("C4", c4_pass), ("C5", c5_pass)]:
            if not passed:
                failed.append(label)
        print(f"VERDICT: FAIL ({', '.join(failed)})  →  investigate SPS initialization; check profile alignment")
    print("=" * 72)

    return hard_pass


if __name__ == "__main__":
    ok = run_validation()
    sys.exit(0 if ok else 1)
