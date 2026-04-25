"""Stage 2 Day 3 — Gate 1: 30 s zero-action stability for Kundur CVS.

Plan §1 D3 + §4 Gate 1 strict criteria:
  1. ω in [0.999, 1.001] pu over the FULL 30 s (per agent)
  2. |δ| < π/2 - 0.05 over the FULL 30 s (no IntD clip)
  3. Pe within ±5 % of IC nominal Pm0 over the FULL 30 s (per agent)
  4. ω never touches the [0.7, 1.3] hard clip
  5. Inter-agent sync (max ω - min ω over agents) < 1e-3 in tail 5 s window

Inputs (committed at HEAD `feat(cvs-d2)`):
  - kundur_ic_cvs.json  (NR IC, plan §3 schema)
  - kundur_cvs.slx      (D2 swing-eq closure)

Outputs:
  - results/cvs_gate1/<ISO_timestamp>/omega_ts_<i>.npz
  - results/cvs_gate1/<ISO_timestamp>/delta_ts_<i>.npz
  - results/cvs_gate1/<ISO_timestamp>/Pe_ts_<i>.npz
  - results/cvs_gate1/<ISO_timestamp>/summary.json

NOT in scope (per plan §4 strict ban):
  - SAC / RL agent
  - Disturbance injection (D4 / Gate 2)
  - bridge.py modification
  - NE39 / legacy / contract.py changes
  - Threshold relaxation on FAIL (must diagnose, not loosen)
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import matlab.engine
import numpy as np

WORKTREE = Path(
    r"C:\Users\27443\Desktop\Multi-Agent  VSGs\.worktrees\kundur-cvs-phasor-vsg"
)
BUILD_DIR = WORKTREE / "scenarios" / "kundur" / "simulink_models"
NR_DIR    = WORKTREE / "scenarios" / "kundur" / "matlab_scripts"
IC_PATH   = WORKTREE / "scenarios" / "kundur" / "kundur_ic_cvs.json"
RESULTS   = WORKTREE / "results" / "cvs_gate1"

MODEL  = "kundur_cvs"
SHARED = "mcp_shared"

N_AGENTS  = 4
STOP_S    = 30.0
TAIL_S    = 5.0

OMEGA_BAND_LO = 0.999
OMEGA_BAND_HI = 1.001
INTD_LIMIT    = math.pi / 2 - 0.05    # ≈ 1.521 rad
OMEGA_CLIP_LO = 0.7
OMEGA_CLIP_HI = 1.3
PE_RTOL       = 0.05
SYNC_TOL      = 1e-3


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class GateVerdict:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def overall_pass(self) -> bool:
        return all(c.passed for c in self.checks)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(CheckResult(name, ok, detail))


def _connect_engine() -> matlab.engine.MatlabEngine:
    try:
        return matlab.engine.connect_matlab(SHARED)
    except matlab.engine.EngineError as exc:
        raise RuntimeError(
            f"Cannot connect to shared MATLAB session '{SHARED}'. "
            f"Run matlab.engine.shareEngine('{SHARED}') in MATLAB first."
        ) from exc


def _rebuild_with_nr(eng: matlab.engine.MatlabEngine) -> None:
    eng.eval(f"addpath('{NR_DIR.as_posix()}');", nargout=0)
    eng.eval(f"addpath('{BUILD_DIR.as_posix()}');", nargout=0)
    eng.eval("compute_kundur_cvs_powerflow();", nargout=0)
    eng.eval("build_kundur_cvs();", nargout=0)


def _run_30s_sim(eng: matlab.engine.MatlabEngine) -> float:
    eng.eval(f"set_param('{MODEL}', 'FastRestart', 'off');", nargout=0)
    t0 = time.time()
    eng.eval(
        f"so_d3 = sim('{MODEL}', 'StopTime', '{STOP_S}', "
        f"'ReturnWorkspaceOutputs', 'on');",
        nargout=0,
    )
    return time.time() - t0


def _fetch_timeseries(
    eng: matlab.engine.MatlabEngine,
) -> dict[int, dict[str, np.ndarray]]:
    out: dict[int, dict[str, np.ndarray]] = {}
    for i in range(1, N_AGENTS + 1):
        eng.eval(
            f"o_{i} = so_d3.get('omega_ts_{i}'); "
            f"d_{i} = so_d3.get('delta_ts_{i}'); "
            f"p_{i} = so_d3.get('Pe_ts_{i}'); "
            f"ot_{i} = double(o_{i}.Time); od_{i} = double(o_{i}.Data); "
            f"dt_{i} = double(d_{i}.Time); dd_{i} = double(d_{i}.Data); "
            f"pt_{i} = double(p_{i}.Time); pd_{i} = double(p_{i}.Data);",
            nargout=0,
        )
        out[i] = {
            "omega_t": np.asarray(eng.workspace[f"ot_{i}"]).flatten(),
            "omega":   np.asarray(eng.workspace[f"od_{i}"]).flatten(),
            "delta_t": np.asarray(eng.workspace[f"dt_{i}"]).flatten(),
            "delta":   np.asarray(eng.workspace[f"dd_{i}"]).flatten(),
            "Pe_t":    np.asarray(eng.workspace[f"pt_{i}"]).flatten(),
            "Pe":      np.asarray(eng.workspace[f"pd_{i}"]).flatten(),
        }
    return out


def _save(out_dir: Path, ts: dict[int, dict[str, np.ndarray]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, d in ts.items():
        np.savez(out_dir / f"omega_ts_{i}.npz", t=d["omega_t"], y=d["omega"])
        np.savez(out_dir / f"delta_ts_{i}.npz", t=d["delta_t"], y=d["delta"])
        np.savez(out_dir / f"Pe_ts_{i}.npz",    t=d["Pe_t"],    y=d["Pe"])


def main() -> int:
    print(f"[d3] connecting to '{SHARED}'")
    eng = _connect_engine()

    print("[d3] running NR + rebuild")
    _rebuild_with_nr(eng)

    ic = json.loads(IC_PATH.read_text(encoding="utf-8"))
    Pm0 = ic["vsg_pm0_pu"]

    print(f"[d3] starting {STOP_S}s zero-action sim")
    elapsed = _run_30s_sim(eng)
    print(f"[d3] sim wall-clock = {elapsed:.2f} s")

    ts = _fetch_timeseries(eng)

    stamp = time.strftime("%Y%m%dT%H%M%S", time.localtime())
    out_dir = RESULTS / stamp
    _save(out_dir, ts)
    print(f"[d3] timeseries saved to {out_dir}")

    verdict = GateVerdict()

    # 1. omega band per-agent (full 30 s)
    omega_ok = True
    omega_det: list[str] = []
    for i in range(1, N_AGENTS + 1):
        w = ts[i]["omega"]
        wmin = float(w.min())
        wmax = float(w.max())
        ok = (wmin >= OMEGA_BAND_LO) and (wmax <= OMEGA_BAND_HI)
        omega_ok &= ok
        omega_det.append(f"VSG{i}: ω∈[{wmin:.6f},{wmax:.6f}]")
    verdict.add("omega_in_band_full_30s", omega_ok, "; ".join(omega_det))

    # 2. IntD margin per-agent (full 30 s)
    intd_ok = True
    intd_det: list[str] = []
    for i in range(1, N_AGENTS + 1):
        dmax = float(np.abs(ts[i]["delta"]).max())
        ok = dmax < INTD_LIMIT
        intd_ok &= ok
        intd_det.append(f"VSG{i}: |δ|max={dmax:.4f} rad")
    verdict.add(
        "intd_margin_full_30s",
        intd_ok,
        f"limit {INTD_LIMIT:.4f} rad; " + "; ".join(intd_det),
    )

    # 3. Pe within ±5 % of Pm0 per-agent (full 30 s)
    pe_ok = True
    pe_det: list[str] = []
    for i in range(1, N_AGENTS + 1):
        pm_i = float(Pm0[i - 1])
        pe = ts[i]["Pe"]
        pemin = float(pe.min())
        pemax = float(pe.max())
        rel_lo = abs(pemin - pm_i) / pm_i if pm_i else float("inf")
        rel_hi = abs(pemax - pm_i) / pm_i if pm_i else float("inf")
        ok = (rel_lo < PE_RTOL) and (rel_hi < PE_RTOL)
        pe_ok &= ok
        pe_det.append(
            f"VSG{i}: Pe∈[{pemin:.4f},{pemax:.4f}] (Pm={pm_i:.4f}, max_rel={max(rel_lo,rel_hi):.2%})"
        )
    verdict.add("pe_within_5pct_full_30s", pe_ok, "; ".join(pe_det))

    # 4. omega never touches hard clip [0.7, 1.3]
    clip_ok = True
    clip_det: list[str] = []
    for i in range(1, N_AGENTS + 1):
        w = ts[i]["omega"]
        clipped = bool((w <= OMEGA_CLIP_LO).any() or (w >= OMEGA_CLIP_HI).any())
        ok = not clipped
        clip_ok &= ok
        clip_det.append(f"VSG{i}: clip_touch={clipped}")
    verdict.add(
        "omega_no_hard_clip",
        clip_ok,
        f"clip=[{OMEGA_CLIP_LO},{OMEGA_CLIP_HI}]; " + "; ".join(clip_det),
    )

    # 5. inter-agent sync in tail 5 s
    tail_means: list[float] = []
    for i in range(1, N_AGENTS + 1):
        t = ts[i]["omega_t"]
        w = ts[i]["omega"]
        mask = t >= (t[-1] - TAIL_S)
        tail_means.append(float(w[mask].mean()))
    spread = max(tail_means) - min(tail_means)
    sync_ok = spread < SYNC_TOL
    verdict.add(
        "inter_agent_sync_tail5s",
        sync_ok,
        f"tail_means={['%.6f' % v for v in tail_means]} spread={spread:.3e}",
    )

    print("\n=== Stage 2 Day 3 / Gate 1 VERDICT ===")
    for c in verdict.checks:
        flag = "PASS" if c.passed else "FAIL"
        print(f"  [{flag}] {c.name}: {c.detail}")
    overall = "PASS" if verdict.overall_pass else "FAIL"
    print(f"\n  OVERALL: {overall}")

    summary = {
        "verdict": overall,
        "stop_s": STOP_S,
        "tail_s": TAIL_S,
        "wall_clock_s": elapsed,
        "thresholds": {
            "omega_band":   [OMEGA_BAND_LO, OMEGA_BAND_HI],
            "intd_limit":   INTD_LIMIT,
            "omega_clip":   [OMEGA_CLIP_LO, OMEGA_CLIP_HI],
            "pe_rtol":      PE_RTOL,
            "sync_tol":     SYNC_TOL,
        },
        "checks": [
            {"name": c.name, "passed": c.passed, "detail": c.detail}
            for c in verdict.checks
        ],
        "per_agent": {
            f"VSG{i}": {
                "omega_min":   float(ts[i]["omega"].min()),
                "omega_max":   float(ts[i]["omega"].max()),
                "delta_abs_max": float(np.abs(ts[i]["delta"]).max()),
                "Pe_min":      float(ts[i]["Pe"].min()),
                "Pe_max":      float(ts[i]["Pe"].max()),
                "Pm0":         float(Pm0[i - 1]),
            }
            for i in range(1, N_AGENTS + 1)
        },
        "tail_means_omega": tail_means,
        "tail_spread":      spread,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(f"[d3] summary saved to {out_dir / 'summary.json'}")

    return 0 if verdict.overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
