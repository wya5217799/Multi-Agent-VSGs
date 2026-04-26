"""Pre-Flight Q2: episode loop + FastRestart + M0/D0 修改 — minimal probe.

Direct matlab.engine + assignin + sim + read. No bridge.py, no env wrapping.

Tests:
  Q2A: 5 ep × 0.5 s zero-action with FR=off — read omega_final per ep
       (verify identical reset → identical output across episodes)
  Q2B: same loop with FR=on after first compile — read omega_final
       (verify FR cache lets sim() re-run without recompile)
  Q2C: middle-episode change M0 12 → 24 with FR=on, verify output changes
       (detect FR-nontunable silent-ignore — known R2 risk)
  Q2D: middle-episode change D0 3 → 8 with FR=on, verify output changes

Usage:
  python preflight_q2_episode.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import matlab.engine  # noqa: E402

SLX_PATH = Path(__file__).parent / "mcp_smib_swing.slx"
MODEL = "mcp_smib_swing"
SHARED_ENGINE_NAME = "mcp_shared"


def _double(x: float) -> float:
    return float(x)


def reset_workspace(eng) -> None:
    """Set base workspace defaults — all double."""
    defaults = dict(
        M0=12.0, D0=3.0, Pm0=0.5, Pm_step_t=999.0, Pm_step_amp=0.0,
        delta0=0.15057, wn_const=314.1592653589793,
        Vbase_const=230000.0, Sbase_const=100000000.0,
        Pe_scale=5e-9, L_H_const=0.5051969,
    )
    for name, val in defaults.items():
        eng.assignin("base", name, _double(val), nargout=0)


def sim_and_read(eng, stop_time: float = 0.5) -> float:
    """sim() with ReturnWorkspaceOutputs and pull last omega from SimOutput."""
    eng.eval(
        f"so_tmp = sim('{MODEL}', 'StopTime', '{stop_time}', "
        f"'ReturnWorkspaceOutputs', 'on'); "
        f"v_tmp = double(so_tmp.get('omega_ts').Data(end));",
        nargout=0,
    )
    return float(eng.workspace["v_tmp"])


def run_episode(eng, stop_time: float = 0.5, fast_restart: str = "off") -> float:
    eng.eval(f"set_param('{MODEL}', 'FastRestart', '{fast_restart}');", nargout=0)
    return sim_and_read(eng, stop_time)


def read_omega_final(eng) -> float:
    return float(eng.workspace["v_tmp"])


def main() -> None:
    print(f"[init] connect_matlab('{SHARED_ENGINE_NAME}')")
    eng = matlab.engine.connect_matlab(SHARED_ENGINE_NAME)
    print(f"[init] connected; loading {SLX_PATH}")
    eng.eval(f"load_system('{SLX_PATH}');", nargout=0)

    # === Q2A: 5 episodes, FR=off, identical IC each time ===
    print("\n=== Q2A: 5 ep × FR=off, identical IC ===")
    omegas_off = []
    t0 = time.time()
    for ep in range(5):
        reset_workspace(eng)
        omega = run_episode(eng, stop_time=0.5, fast_restart="off")
        omegas_off.append(omega)
        print(f"  ep{ep}: omega_final={omega:.8f}")
    elapsed_a = time.time() - t0
    spread_off = max(omegas_off) - min(omegas_off)
    print(f"  spread_off={spread_off:.2e}  elapsed={elapsed_a:.1f}s")

    # === Q2B: 5 episodes FR=on after first compile ===
    print("\n=== Q2B: 5 ep × FR=on, identical IC ===")
    omegas_on = []
    reset_workspace(eng)
    # Prime FR with a first sim
    eng.eval(f"set_param('{MODEL}', 'FastRestart', 'off');", nargout=0)
    sim_and_read(eng, stop_time=0.5)
    eng.eval(f"set_param('{MODEL}', 'FastRestart', 'on');", nargout=0)
    t0 = time.time()
    for ep in range(5):
        reset_workspace(eng)
        sim_and_read(eng, stop_time=0.5)
        omega = read_omega_final(eng)
        omegas_on.append(omega)
        print(f"  ep{ep}: omega_final={omega:.8f}")
    elapsed_b = time.time() - t0
    spread_on = max(omegas_on) - min(omegas_on)
    print(f"  spread_on={spread_on:.2e}  elapsed={elapsed_b:.1f}s")

    # === Q2C: change M0 mid-loop with FR=on, verify output changes ===
    print("\n=== Q2C: FR=on + M0 12→24 (FR-nontunable detection) ===")
    reset_workspace(eng)
    sim_and_read(eng, stop_time=0.5)
    omega_M12 = read_omega_final(eng)
    # Change M0 with FR still on
    eng.assignin("base", "M0", _double(24.0), nargout=0)
    # Capture lastwarn before/after to detect "nontunable" warning
    eng.eval("lastwarn('');", nargout=0)
    sim_and_read(eng, stop_time=0.5)
    warn_msg = str(eng.eval("lastwarn", nargout=1))
    omega_M24_FRon = read_omega_final(eng)
    M0_changed_FRon = abs(omega_M12 - omega_M24_FRon) > 1e-6
    print(f"  omega(M0=12)={omega_M12:.8f}")
    print(f"  omega(M0=24, FR=on)={omega_M24_FRon:.8f}")
    print(f"  changed={M0_changed_FRon}  lastwarn={warn_msg!r}")

    # Compare against FR=off ground truth for M0=24
    eng.eval(f"set_param('{MODEL}', 'FastRestart', 'off');", nargout=0)
    reset_workspace(eng)
    eng.assignin("base", "M0", _double(24.0), nargout=0)
    sim_and_read(eng, stop_time=0.5)
    omega_M24_FRoff = read_omega_final(eng)
    fr_consistent_M = abs(omega_M24_FRon - omega_M24_FRoff) < 1e-6
    print(f"  omega(M0=24, FR=off)={omega_M24_FRoff:.8f}  FR_consistent={fr_consistent_M}")

    # === Q2D: change D0 with FR=on, verify ===
    print("\n=== Q2D: FR=on + D0 3→8 ===")
    eng.eval(f"set_param('{MODEL}', 'FastRestart', 'on');", nargout=0)
    reset_workspace(eng)
    sim_and_read(eng, stop_time=0.5)
    omega_D3 = read_omega_final(eng)
    eng.assignin("base", "D0", _double(8.0), nargout=0)
    eng.eval("lastwarn('');", nargout=0)
    sim_and_read(eng, stop_time=0.5)
    warn_msg_d = str(eng.eval("lastwarn", nargout=1))
    omega_D8_FRon = read_omega_final(eng)
    D0_changed_FRon = abs(omega_D3 - omega_D8_FRon) > 1e-6
    print(f"  omega(D0=3)={omega_D3:.8f}")
    print(f"  omega(D0=8, FR=on)={omega_D8_FRon:.8f}")
    print(f"  changed={D0_changed_FRon}  lastwarn={warn_msg_d!r}")

    # Verdict
    print("\n=== Q2 VERDICT ===")
    print(f"  Q2A repeatable_FR_off: spread={spread_off:.2e} (PASS if < 1e-9)")
    print(f"  Q2B repeatable_FR_on:  spread={spread_on:.2e}  (PASS if < 1e-9)")
    print(f"  Q2C M0 mutable FR=on: changed={M0_changed_FRon}, FR_consistent={fr_consistent_M}")
    print(f"  Q2D D0 mutable FR=on: changed={D0_changed_FRon}")
    print(f"  FR speedup: off={elapsed_a:.1f}s vs on={elapsed_b:.1f}s")

    # Reset model to FR=off and original params for cleanup
    eng.eval(f"set_param('{MODEL}', 'FastRestart', 'off');", nargout=0)
    reset_workspace(eng)


if __name__ == "__main__":
    main()
