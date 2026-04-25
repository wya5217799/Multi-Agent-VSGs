"""Stage 2 Day 2 — Newton-Raphson IC validation for the 7-bus CVS model.

Connects to the MCP shared MATLAB session, (re)builds ``kundur_cvs.slx``
with the NR IC fed in via ``kundur_ic_cvs.json``, runs a 0.5 s zero-action
sim, and validates the 4 IC indicators from Stage 2 plan §1 D2 / §3:

    Pe ≈ Pm0          : per-agent |Pe_tail - Pm0| / Pm0 < 5 %
    ω ≈ 1             : per-agent |ω_tail_mean - 1| < 1e-3
    IntD margin       : per-agent |delta|_max < π/2 - 0.05 (≈ 1.521 rad)
    inter-agent sync  : (max ω - min ω over agents) < 1e-3

Tail window = last 0.2 s of a 0.5 s sim (per plan §3 footnote).

Pre-conditions:
    - MCP MATLAB shared session running (`matlab.engine.shareEngine('mcp_shared')`)
    - `compute_kundur_cvs_powerflow()` already produced `kundur_ic_cvs.json`
    - `build_kundur_cvs.m` reads the JSON

NOT in scope (deferred):
    - 30 s zero-action stability gate (D3 / Gate 1)
    - Disturbance sweep (D4 / Gate 2)
    - SAC / RL training (Gate 3)
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import matlab.engine

WORKTREE = Path(
    r"C:\Users\27443\Desktop\Multi-Agent  VSGs\.worktrees\kundur-cvs-phasor-vsg"
)
BUILD_DIR = WORKTREE / "scenarios" / "kundur" / "simulink_models"
NR_DIR    = WORKTREE / "scenarios" / "kundur" / "matlab_scripts"
IC_PATH   = WORKTREE / "scenarios" / "kundur" / "kundur_ic_cvs.json"

MODEL  = "kundur_cvs"
SHARED = "mcp_shared"

N_AGENTS    = 4
STOP_S      = 0.5
TAIL_S      = 0.2

PE_PM_RTOL    = 0.05
OMEGA_TOL     = 1e-3
INTD_MARGIN   = math.pi / 2 - 0.05   # ≈ 1.521 rad
SYNC_TOL      = 1e-3


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class D2Verdict:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def overall_pass(self) -> bool:
        return all(c.passed for c in self.checks)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(CheckResult(name=name, passed=ok, detail=detail))


def _connect_engine() -> matlab.engine.MatlabEngine:
    try:
        return matlab.engine.connect_matlab(SHARED)
    except matlab.engine.EngineError as exc:
        raise RuntimeError(
            f"Cannot connect to shared MATLAB session '{SHARED}'. "
            f"Run matlab.engine.shareEngine('{SHARED}') in MATLAB first."
        ) from exc


def _load_ic() -> dict:
    return json.loads(IC_PATH.read_text(encoding="utf-8"))


def _rebuild_with_nr(eng: matlab.engine.MatlabEngine) -> None:
    eng.eval(f"addpath('{NR_DIR.as_posix()}');", nargout=0)
    eng.eval(f"addpath('{BUILD_DIR.as_posix()}');", nargout=0)
    eng.eval("compute_kundur_cvs_powerflow();", nargout=0)
    eng.eval("build_kundur_cvs();", nargout=0)


def _run_zero_action_sim(eng: matlab.engine.MatlabEngine) -> None:
    eng.eval(f"set_param('{MODEL}', 'FastRestart', 'off');", nargout=0)
    eng.eval(
        f"so_d2 = sim('{MODEL}', 'StopTime', '{STOP_S}', "
        f"'ReturnWorkspaceOutputs', 'on');",
        nargout=0,
    )


def _per_agent_metrics(
    eng: matlab.engine.MatlabEngine,
) -> dict[int, dict[str, float]]:
    metrics: dict[int, dict[str, float]] = {}
    for i in range(1, N_AGENTS + 1):
        eng.eval(
            f"o_{i} = so_d2.get('omega_ts_{i}'); "
            f"d_{i} = so_d2.get('delta_ts_{i}'); "
            f"p_{i} = so_d2.get('Pe_ts_{i}'); "
            f"od_{i} = double(o_{i}.Data); ot_{i} = double(o_{i}.Time); "
            f"dd_{i} = double(d_{i}.Data); pd_{i} = double(p_{i}.Data); "
            f"mask_{i} = ot_{i} >= ot_{i}(end) - {TAIL_S}; "
            f"otm_{i} = mean(od_{i}(mask_{i})); "
            f"dmax_{i} = max(abs(dd_{i})); "
            f"ptm_{i} = mean(pd_{i}(mask_{i}));",
            nargout=0,
        )
        metrics[i] = {
            "omega_tail_mean": float(eng.workspace[f"otm_{i}"]),
            "delta_abs_max":   float(eng.workspace[f"dmax_{i}"]),
            "Pe_tail_mean":    float(eng.workspace[f"ptm_{i}"]),
        }
    return metrics


def main() -> int:
    print(f"[d2] connecting to '{SHARED}'")
    eng = _connect_engine()

    print("[d2] running NR + rebuild")
    _rebuild_with_nr(eng)

    ic = _load_ic()
    Pm0 = ic["vsg_pm0_pu"]
    delta0 = ic["vsg_internal_emf_angle_rad"]
    print(f"[d2] NR converged={ic['powerflow']['converged']} "
          f"iter={ic['powerflow']['iterations']} "
          f"max_mismatch_pu={ic['powerflow']['max_mismatch_pu']:.3e}")
    print(f"[d2] NR delta0 (rad) = {delta0}")
    print(f"[d2] NR Pm0    (pu)  = {Pm0}")

    print(f"[d2] zero-action sim 0 → {STOP_S}s")
    _run_zero_action_sim(eng)

    metrics = _per_agent_metrics(eng)

    verdict = D2Verdict()

    # Indicator 1 — Pe ≈ Pm0 per agent
    pe_pm_ok = True
    pe_pm_details: list[str] = []
    for i in range(1, N_AGENTS + 1):
        pm_i = float(Pm0[i - 1])
        pe_i = metrics[i]["Pe_tail_mean"]
        rel  = abs(pe_i - pm_i) / pm_i if pm_i != 0 else float("inf")
        ok   = rel < PE_PM_RTOL
        pe_pm_ok &= ok
        pe_pm_details.append(f"VSG{i}: Pe={pe_i:+.4f} Pm={pm_i:+.4f} rel={rel:.2%}")
    verdict.add("pe_approx_pm",
                pe_pm_ok,
                "; ".join(pe_pm_details))

    # Indicator 2 — ω ≈ 1 per agent
    omega_ok = True
    omega_details: list[str] = []
    for i in range(1, N_AGENTS + 1):
        otm = metrics[i]["omega_tail_mean"]
        ok  = abs(otm - 1.0) < OMEGA_TOL
        omega_ok &= ok
        omega_details.append(f"VSG{i}: ω_tail={otm:.6f} dev={otm - 1.0:+.2e}")
    verdict.add("omega_approx_1", omega_ok, "; ".join(omega_details))

    # Indicator 3 — IntD margin
    intd_ok = True
    intd_details: list[str] = []
    for i in range(1, N_AGENTS + 1):
        dmax = metrics[i]["delta_abs_max"]
        ok   = dmax < INTD_MARGIN
        intd_ok &= ok
        intd_details.append(f"VSG{i}: |δ|max={dmax:.4f} rad")
    verdict.add(
        "intd_margin",
        intd_ok,
        f"limit={INTD_MARGIN:.4f} rad; " + "; ".join(intd_details),
    )

    # Indicator 4 — inter-agent sync
    omegas = [metrics[i]["omega_tail_mean"] for i in range(1, N_AGENTS + 1)]
    spread = max(omegas) - min(omegas)
    sync_ok = spread < SYNC_TOL
    verdict.add(
        "inter_agent_sync",
        sync_ok,
        f"spread={spread:.3e} (limit {SYNC_TOL:.0e})",
    )

    print("\n=== Stage 2 Day 2 VERDICT ===")
    for c in verdict.checks:
        flag = "PASS" if c.passed else "FAIL"
        print(f"  [{flag}] {c.name}: {c.detail}")
    overall = "PASS" if verdict.overall_pass else "FAIL"
    print(f"\n  OVERALL: {overall}")

    print("\n--- per-agent metric dump ---")
    for i in range(1, N_AGENTS + 1):
        m = metrics[i]
        print(
            f"  VSG{i}: ω_tail={m['omega_tail_mean']:.6f}  "
            f"|δ|max={m['delta_abs_max']:.4f}  "
            f"Pe_tail={m['Pe_tail_mean']:+.4f}"
        )

    return 0 if verdict.overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
