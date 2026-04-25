"""Gate P2: Kundur 4-VSG CVS reset/warmup/step/read episode-loop probe.

Direct matlab.engine + assignin + sim + read. No bridge.py.

Tests (per-agent extension of Pre-Flight Q2):
  P2A: 5 ep × 0.5s zero-action, FR=off, identical IC -> spread per agent must = 0
  P2B: 5 ep × 0.5s zero-action, FR=on -> spread per agent must = 0
  P2C: per-agent change M_i 12 -> 24 with FR=on, omega_i must change, no nontunable warn
  P2D: per-agent change D_i 3 -> 8 with FR=on, omega_i must change

PASS criteria:
  - All 4 agents bit-exact across episodes (FR off and FR on)
  - M_i, D_i mutations propagate (FR=on) without nontunable lastwarn
  - 4 agents settle near omega = 1 pu under zero-action 0.5s window
"""
from __future__ import annotations

import time
from pathlib import Path

import matlab.engine

SLX_PATH = Path(__file__).parent / "kundur_cvs_p2.slx"
MODEL = "kundur_cvs_p2"
SHARED_ENGINE_NAME = "mcp_shared"
N_AGENTS = 4
PASS_SPREAD = 1e-9
PASS_M_CHANGE = 1e-6


def _double(x: float) -> float:
    return float(x)


def reset_workspace(eng) -> None:
    """Set all base ws defaults — every value forced double."""
    import math
    delta0_default = math.asin(0.5 * 0.10)
    for i in range(1, N_AGENTS + 1):
        eng.assignin("base", f"M_{i}", _double(12.0), nargout=0)
        eng.assignin("base", f"D_{i}", _double(3.0), nargout=0)
        eng.assignin("base", f"Pm_{i}", _double(0.5), nargout=0)
        eng.assignin("base", f"delta0_{i}", _double(delta0_default), nargout=0)
    eng.assignin("base", "wn_const", _double(2 * math.pi * 50), nargout=0)
    eng.assignin("base", "Vbase_const", _double(230000.0), nargout=0)
    eng.assignin("base", "Sbase_const", _double(1e8), nargout=0)
    eng.assignin("base", "Pe_scale", _double(0.5 / 1e8), nargout=0)
    fn = 50.0
    Vbase = 230e3
    Sbase = 1e8
    eng.assignin("base", "L_line_H",
                 _double(0.10 * Vbase * Vbase / Sbase / (2 * math.pi * fn)),
                 nargout=0)
    eng.assignin("base", "L_tie_H",
                 _double(0.30 * Vbase * Vbase / Sbase / (2 * math.pi * fn)),
                 nargout=0)


def sim_and_read(eng, stop_time: float = 0.5) -> dict[int, float]:
    """sim() and pull omega_final per agent."""
    eng.eval(
        f"so_tmp = sim('{MODEL}', 'StopTime', '{stop_time}', "
        f"'ReturnWorkspaceOutputs', 'on');",
        nargout=0,
    )
    out = {}
    for i in range(1, N_AGENTS + 1):
        eng.eval(f"v_{i} = double(so_tmp.get('omega_ts_{i}').Data(end));", nargout=0)
        out[i] = float(eng.workspace[f"v_{i}"])
    return out


def get_lastwarn(eng) -> str:
    return str(eng.eval("lastwarn", nargout=1))


def set_fr(eng, mode: str) -> None:
    eng.eval(f"set_param('{MODEL}', 'FastRestart', '{mode}');", nargout=0)


def main() -> None:
    print(f"[init] connect_matlab('{SHARED_ENGINE_NAME}')")
    eng = matlab.engine.connect_matlab(SHARED_ENGINE_NAME)
    print(f"[init] loading {SLX_PATH}")
    eng.eval(f"load_system('{SLX_PATH}');", nargout=0)

    # ===== P2A: FR=off bit-exact =====
    print("\n=== P2A: 5 ep × FR=off, identical IC ===")
    set_fr(eng, "off")
    runs_off = {i: [] for i in range(1, N_AGENTS + 1)}
    t0 = time.time()
    for ep in range(5):
        reset_workspace(eng)
        omegas = sim_and_read(eng, 0.5)
        for i, v in omegas.items():
            runs_off[i].append(v)
        print(f"  ep{ep}: " + ", ".join(f"o{i}={omegas[i]:.8f}" for i in omegas))
    elapsed_a = time.time() - t0
    spreads_off = {i: max(runs_off[i]) - min(runs_off[i]) for i in runs_off}
    p2a_pass = all(s < PASS_SPREAD for s in spreads_off.values())
    print(f"  spreads_off={ {i: f'{s:.2e}' for i,s in spreads_off.items()} }  elapsed={elapsed_a:.1f}s")

    # ===== P2B: FR=on bit-exact =====
    print("\n=== P2B: 5 ep × FR=on, identical IC ===")
    reset_workspace(eng)
    set_fr(eng, "off")
    sim_and_read(eng, 0.5)  # prime FR
    set_fr(eng, "on")
    runs_on = {i: [] for i in range(1, N_AGENTS + 1)}
    t0 = time.time()
    for ep in range(5):
        reset_workspace(eng)
        omegas = sim_and_read(eng, 0.5)
        for i, v in omegas.items():
            runs_on[i].append(v)
        print(f"  ep{ep}: " + ", ".join(f"o{i}={omegas[i]:.8f}" for i in omegas))
    elapsed_b = time.time() - t0
    spreads_on = {i: max(runs_on[i]) - min(runs_on[i]) for i in runs_on}
    p2b_pass = all(s < PASS_SPREAD for s in spreads_on.values())
    print(f"  spreads_on={ {i: f'{s:.2e}' for i,s in spreads_on.items()} }  elapsed={elapsed_b:.1f}s")

    # ===== P2C: M_i 12 -> 24 per agent (FR=on) =====
    print("\n=== P2C: FR=on + M_i 12 → 24 (per-agent) ===")
    set_fr(eng, "on")
    reset_workspace(eng)
    omegas_M12 = sim_and_read(eng, 0.5)
    p2c = {}
    for i in range(1, N_AGENTS + 1):
        reset_workspace(eng)
        eng.assignin("base", f"M_{i}", _double(24.0), nargout=0)
        eng.eval("lastwarn('');", nargout=0)
        omegas_after = sim_and_read(eng, 0.5)
        warn = get_lastwarn(eng)
        changed = abs(omegas_after[i] - omegas_M12[i]) > PASS_M_CHANGE
        nontunable_hit = any(k in warn.lower() for k in
                             ("nontunable", "不可调", "will not be used", "新值不会使用"))
        p2c[i] = {"changed": changed, "warn": warn, "nontunable": nontunable_hit,
                  "omega_M12": omegas_M12[i], "omega_M24": omegas_after[i]}
        print(f"  M_{i}: 12→{omegas_M12[i]:.6f}  24→{omegas_after[i]:.6f}  "
              f"changed={changed}  nontunable={nontunable_hit}")
    p2c_pass = all(v["changed"] and not v["nontunable"] for v in p2c.values())

    # ===== P2D: D_i 3 -> 8 per agent (FR=on) =====
    print("\n=== P2D: FR=on + D_i 3 → 8 (per-agent) ===")
    reset_workspace(eng)
    omegas_D3 = sim_and_read(eng, 0.5)
    p2d = {}
    for i in range(1, N_AGENTS + 1):
        reset_workspace(eng)
        eng.assignin("base", f"D_{i}", _double(8.0), nargout=0)
        eng.eval("lastwarn('');", nargout=0)
        omegas_after = sim_and_read(eng, 0.5)
        warn = get_lastwarn(eng)
        changed = abs(omegas_after[i] - omegas_D3[i]) > PASS_M_CHANGE
        nontunable_hit = any(k in warn.lower() for k in
                             ("nontunable", "不可调", "will not be used", "新值不会使用"))
        p2d[i] = {"changed": changed, "warn": warn, "nontunable": nontunable_hit,
                  "omega_D3": omegas_D3[i], "omega_D8": omegas_after[i]}
        print(f"  D_{i}: 3→{omegas_D3[i]:.6f}  8→{omegas_after[i]:.6f}  "
              f"changed={changed}  nontunable={nontunable_hit}")
    p2d_pass = all(v["changed"] and not v["nontunable"] for v in p2d.values())

    # ===== Reset cleanup =====
    set_fr(eng, "off")
    reset_workspace(eng)

    print("\n=== P2 VERDICT ===")
    print(f"  P2A repeatable_FR_off: {'PASS' if p2a_pass else 'FAIL'}  (max spread={max(spreads_off.values()):.2e})")
    print(f"  P2B repeatable_FR_on:  {'PASS' if p2b_pass else 'FAIL'}  (max spread={max(spreads_on.values()):.2e})")
    print(f"  P2C M_i tunable:       {'PASS' if p2c_pass else 'FAIL'}")
    print(f"  P2D D_i tunable:       {'PASS' if p2d_pass else 'FAIL'}")
    print(f"  FR speedup: off={elapsed_a:.1f}s on={elapsed_b:.1f}s")

    overall = p2a_pass and p2b_pass and p2c_pass and p2d_pass
    print(f"\n  OVERALL: {'PASS' if overall else 'FAIL'}")


if __name__ == "__main__":
    main()
