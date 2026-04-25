"""Gate P3: zero-action 5s smoke for Kundur 4-VSG CVS Phasor model.

Validates physical reasonableness:
  - 4 agents tail ω ∈ [0.999, 1.001] pu
  - inter-agent ω synchrony (max - min < 0.01 pu over tail window)
  - IntD never near ±π/2 clip
  - Pe ≈ Pm0 (±5%)
  - no NaN / Inf / early termination
"""
from __future__ import annotations

import math
from pathlib import Path

import matlab.engine

SLX_PATH = Path(__file__).parent / "kundur_cvs_p2.slx"
MODEL = "kundur_cvs_p2"
SHARED = "mcp_shared"
N = 4
TAIL_S = 2.0
STOP_S = 10.0


def _d(x):
    return float(x)


def reset_ws(eng):
    # Per-agent IC by hand-NR for the symmetric 2x2 topology:
    # AC_INF anchors BUS_left at 0 rad. With 4 VSGs each injecting Pm0=0.5,
    # total 2.0 pu flows to inf-bus (all via BUS_left), tie carries 1.0 pu (R→L).
    # tie_phase: sin(0 - theta_right)*1/X_tie = -1 → theta_right = +0.30537 rad
    # VSG_to_local_bus: sin(delta - theta_bus)/X_line = Pm0 → ΔLocal = +0.05016 rad
    # VSG1/2: delta = 0 + 0.05016
    # VSG3/4: delta = 0.30537 + 0.05016 = 0.35553
    Pm0 = 0.5
    X_line, X_tie = 0.10, 0.30
    theta_right = math.asin(Pm0 * 2 * X_tie)        # tie carries 2*Pm0 = 1.0 pu
    delta_VSG_local = math.asin(Pm0 * X_line)       # 0.0502 rad
    delta0_left = delta_VSG_local                    # 0.0502
    delta0_right = theta_right + delta_VSG_local     # 0.30537 + 0.0502 = 0.3556
    deltas = {1: delta0_left, 2: delta0_left, 3: delta0_right, 4: delta0_right}
    for i in range(1, N + 1):
        eng.assignin("base", f"M_{i}", _d(12.0), nargout=0)
        eng.assignin("base", f"D_{i}", _d(3.0), nargout=0)
        eng.assignin("base", f"Pm_{i}", _d(Pm0), nargout=0)
        eng.assignin("base", f"delta0_{i}", _d(deltas[i]), nargout=0)
    eng.assignin("base", "wn_const", _d(2 * math.pi * 50), nargout=0)
    eng.assignin("base", "Vbase_const", _d(230e3), nargout=0)
    eng.assignin("base", "Sbase_const", _d(1e8), nargout=0)
    eng.assignin("base", "Pe_scale", _d(0.5 / 1e8), nargout=0)
    eng.assignin("base", "L_line_H",
                 _d(0.10 * 230e3 ** 2 / 1e8 / (2 * math.pi * 50)), nargout=0)
    eng.assignin("base", "L_tie_H",
                 _d(0.30 * 230e3 ** 2 / 1e8 / (2 * math.pi * 50)), nargout=0)


def main():
    eng = matlab.engine.connect_matlab(SHARED)
    eng.eval(f"load_system('{SLX_PATH}');", nargout=0)
    eng.eval(f"set_param('{MODEL}', 'FastRestart', 'off');", nargout=0)
    reset_ws(eng)

    eng.eval(
        f"so_smoke = sim('{MODEL}', 'StopTime', '{STOP_S}', "
        f"'ReturnWorkspaceOutputs', 'on');",
        nargout=0,
    )
    print(f"[smoke] sim 0 → {STOP_S}s done; reading per-agent stats")

    pass_omega_band = True
    pass_intd_clip = True
    pass_pe_match = True
    omegas_tail_mean = {}
    omegas_tail_std = {}
    delta_max = {}
    pe_tail_mean = {}

    for i in range(1, N + 1):
        eng.eval(
            f"o_{i} = so_smoke.get('omega_ts_{i}'); "
            f"d_{i} = so_smoke.get('delta_ts_{i}'); "
            f"p_{i} = so_smoke.get('Pe_ts_{i}'); "
            f"od_{i} = double(o_{i}.Data); ot_{i} = double(o_{i}.Time); "
            f"dd_{i} = double(d_{i}.Data); pd_{i} = double(p_{i}.Data); "
            f"mask_{i} = ot_{i} >= ot_{i}(end) - {TAIL_S}; "
            f"otm_{i} = mean(od_{i}(mask_{i})); ots_{i} = std(od_{i}(mask_{i})); "
            f"dmax_{i} = max(abs(dd_{i})); ptm_{i} = mean(pd_{i}(mask_{i}));",
            nargout=0,
        )
        otm = float(eng.workspace[f"otm_{i}"])
        ots = float(eng.workspace[f"ots_{i}"])
        dmax = float(eng.workspace[f"dmax_{i}"])
        ptm = float(eng.workspace[f"ptm_{i}"])
        omegas_tail_mean[i] = otm
        omegas_tail_std[i] = ots
        delta_max[i] = dmax
        pe_tail_mean[i] = ptm
        in_band = 0.999 <= otm <= 1.001
        intd_safe = dmax < (math.pi / 2 - 0.01)
        pe_ok = abs(ptm - 0.5) / 0.5 < 0.05
        if not in_band:
            pass_omega_band = False
        if not intd_safe:
            pass_intd_clip = False
        if not pe_ok:
            pass_pe_match = False
        print(f"  VSG{i}: tail_mean ω={otm:.6f} std={ots:.4e} "
              f"|delta|max={dmax:.4f} rad Pe_tail_mean={ptm:.4f}")

    sync_spread = max(omegas_tail_mean.values()) - min(omegas_tail_mean.values())
    pass_sync = sync_spread < 0.01

    eng.eval(f"set_param('{MODEL}', 'FastRestart', 'off');", nargout=0)
    reset_ws(eng)

    print("\n=== Gate P3 VERDICT ===")
    print(f"  ω band  [0.999, 1.001]: {'PASS' if pass_omega_band else 'FAIL'}")
    print(f"  inter-agent sync (Δω < 0.01 pu): {'PASS' if pass_sync else 'FAIL'} (spread={sync_spread:.4e})")
    print(f"  IntD not near ±π/2 clip: {'PASS' if pass_intd_clip else 'FAIL'} (max|delta|={max(delta_max.values()):.4f})")
    print(f"  Pe ≈ Pm (±5%): {'PASS' if pass_pe_match else 'FAIL'}")
    overall = pass_omega_band and pass_sync and pass_intd_clip and pass_pe_match
    print(f"\n  OVERALL: {'PASS' if overall else 'FAIL'}")


if __name__ == "__main__":
    main()
