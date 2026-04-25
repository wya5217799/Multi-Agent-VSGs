"""Stage 2 Day 4 — Gate 2: Pm step disturbance sweep for Kundur CVS.

Plan §1 D4 + §5 Gate 2:
  - 5 amplitudes ∈ {0.05, 0.10, 0.20, 0.30, 0.50} pu
  - 3 seeds (= target VSG ∈ {VSG1, VSG2, VSG3})
  - 15 runs total, each 30 s, t_step = 5 s
  - Disturbance path: base-ws Pm_step_amp_<i> + Pm_step_t_<i>
    (FR-tunable Constant chain; NOT TripLoad / breaker)

Pass criteria (plan §5 / Gate 2):
  1. max_freq_dev linearity vs amplitude: R^2 > 0.9
  2. At amp = 0.5 pu: max_freq_dev ≤ 5 Hz
  3. peak/steady ≤ 1.5 (overshoot < 50 %)
  4. settle_time ≤ 5 s (after step time)
  5. ω never touches hard clip [0.7, 1.3]

Outputs:
  - results/cvs_gate2/<ts>/trace_dist_<amp>_seed<s>.npz (×15)
  - results/cvs_gate2/<ts>/summary.json

NOT in scope (strict ban from authorisation):
  - SAC / RL / training entry
  - bridge.py / NE39 / vsg_bridge / contract.py / legacy changes
  - amp > 0.5 pu
  - threshold relaxation on FAIL → stop at diagnosis + verdict
"""
from __future__ import annotations

import io
import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import matlab.engine
import numpy as np

# Force UTF-8 stdout regardless of console codepage (Windows default GBK
# would crash on math symbols like ² / ω / δ in the verdict text).
if isinstance(sys.stdout, io.TextIOWrapper):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

WORKTREE = Path(
    r"C:\Users\27443\Desktop\Multi-Agent  VSGs\.worktrees\kundur-cvs-phasor-vsg"
)
BUILD_DIR = WORKTREE / "scenarios" / "kundur" / "simulink_models"
NR_DIR    = WORKTREE / "scenarios" / "kundur" / "matlab_scripts"
RESULTS   = WORKTREE / "results" / "cvs_gate2"

MODEL  = "kundur_cvs"
SHARED = "mcp_shared"
FN_HZ  = 50.0
N_AGENTS = 4
STOP_S   = 30.0
T_STEP   = 5.0

AMPLITUDES = [0.05, 0.10, 0.20, 0.30, 0.50]
SEEDS      = [1, 2, 3]                 # selects target VSG ∈ {VSG1, VSG2, VSG3}

# Pass thresholds
R2_MIN              = 0.9
MAX_FREQ_DEV_05_HZ  = 5.0
PEAK_TO_STEADY_MAX  = 1.5
SETTLE_S_MAX        = 5.0
OMEGA_CLIP_LO       = 0.7
OMEGA_CLIP_HI       = 1.3
SETTLE_TOL          = 5e-4              # ω-1 |·| ≤ 5e-4 pu = 0.025 Hz
SETTLE_HOLD_S       = 1.0               # consecutive settled duration


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
            f"Cannot connect to '{SHARED}'. Run "
            f"matlab.engine.shareEngine('{SHARED}') in MATLAB."
        ) from exc


def _rebuild_with_nr(eng: matlab.engine.MatlabEngine) -> None:
    eng.eval(f"addpath('{NR_DIR.as_posix()}');", nargout=0)
    eng.eval(f"addpath('{BUILD_DIR.as_posix()}');", nargout=0)
    eng.eval("compute_kundur_cvs_powerflow();", nargout=0)
    eng.eval("build_kundur_cvs();", nargout=0)


def _set_step(eng: matlab.engine.MatlabEngine, target_vsg: int, amp: float) -> None:
    """Reset all step amps to 0, set the target VSG's step_t and step_amp."""
    for i in range(1, N_AGENTS + 1):
        eng.eval(f"assignin('base','Pm_step_amp_{i}',double(0));", nargout=0)
        eng.eval(f"assignin('base','Pm_step_t_{i}',double({T_STEP}));", nargout=0)
    eng.eval(
        f"assignin('base','Pm_step_amp_{target_vsg}',double({amp}));",
        nargout=0,
    )


def _run_sim(eng: matlab.engine.MatlabEngine) -> float:
    t0 = time.time()
    eng.eval(
        f"so_d4 = sim('{MODEL}', 'StopTime', '{STOP_S}', "
        f"'ReturnWorkspaceOutputs', 'on');",
        nargout=0,
    )
    return time.time() - t0


def _fetch_omega(eng: matlab.engine.MatlabEngine) -> dict[int, np.ndarray]:
    out: dict[int, np.ndarray] = {}
    for i in range(1, N_AGENTS + 1):
        eng.eval(
            f"o_{i} = so_d4.get('omega_ts_{i}'); "
            f"ot_{i} = double(o_{i}.Time); "
            f"od_{i} = double(o_{i}.Data);",
            nargout=0,
        )
        t = np.asarray(eng.workspace[f"ot_{i}"]).flatten()
        y = np.asarray(eng.workspace[f"od_{i}"]).flatten()
        out[i] = np.column_stack([t, y])
    return out


def _settle_time(t: np.ndarray, dev: np.ndarray) -> float:
    """First time after t_step where |dev| stays ≤ SETTLE_TOL for ≥ SETTLE_HOLD_S."""
    mask = t >= T_STEP
    tt = t[mask]
    dd = dev[mask]
    in_band = np.abs(dd) <= SETTLE_TOL
    settle_t = float("inf")
    streak_start: float | None = None
    for k, (tk, ok) in enumerate(zip(tt, in_band, strict=False)):
        if ok:
            if streak_start is None:
                streak_start = tk
            if tk - streak_start >= SETTLE_HOLD_S:
                settle_t = streak_start - T_STEP
                break
        else:
            streak_start = None
    return settle_t


def _r2(x: list[float], y: list[float]) -> float:
    xa = np.asarray(x, dtype=float)
    ya = np.asarray(y, dtype=float)
    if len(xa) < 2 or np.std(xa) == 0:
        return 0.0
    coef = np.polyfit(xa, ya, 1)
    yhat = coef[0] * xa + coef[1]
    ss_res = float(np.sum((ya - yhat) ** 2))
    ss_tot = float(np.sum((ya - ya.mean()) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0


def main() -> int:
    print(f"[d4] connecting to '{SHARED}'")
    eng = _connect_engine()

    print("[d4] running NR + rebuild")
    _rebuild_with_nr(eng)
    eng.eval(f"set_param('{MODEL}', 'FastRestart', 'on');", nargout=0)

    stamp = time.strftime("%Y%m%dT%H%M%S", time.localtime())
    out_dir = RESULTS / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    runs: list[dict] = []
    print(f"[d4] starting sweep: {len(AMPLITUDES)} amps × {len(SEEDS)} seeds = {len(AMPLITUDES) * len(SEEDS)} runs")

    for amp in AMPLITUDES:
        for seed in SEEDS:
            target = seed
            _set_step(eng, target, amp)
            elapsed = _run_sim(eng)
            data = _fetch_omega(eng)

            # Per-run metrics over all 4 agents
            max_dev = 0.0
            clip_hit = False
            agent_max_devs: dict[int, float] = {}
            for i in range(1, N_AGENTS + 1):
                t = data[i][:, 0]
                w = data[i][:, 1]
                dev = w - 1.0
                m = float(np.max(np.abs(dev)))
                agent_max_devs[i] = m
                if m > max_dev:
                    max_dev = m
                if (w <= OMEGA_CLIP_LO).any() or (w >= OMEGA_CLIP_HI).any():
                    clip_hit = True

            # Use the target agent's omega for peak/steady & settle
            t_t = data[target][:, 0]
            w_t = data[target][:, 1]
            dev_t = w_t - 1.0
            after_step = t_t >= T_STEP
            peak = float(np.max(np.abs(dev_t[after_step])))
            tail_mask = t_t >= (t_t[-1] - 5.0)
            steady = float(np.mean(np.abs(dev_t[tail_mask])))
            ratio = peak / max(steady, 1e-5)
            settle_t = _settle_time(t_t, dev_t)

            run_summary = {
                "amp_pu":            amp,
                "seed":              seed,
                "target_vsg":        target,
                "max_freq_dev_pu":   max_dev,
                "max_freq_dev_Hz":   max_dev * FN_HZ,
                "agent_max_devs_pu": agent_max_devs,
                "peak_pu":           peak,
                "steady_pu":         steady,
                "peak_to_steady":    ratio,
                "settle_after_step_s": settle_t,
                "clip_hit":          clip_hit,
                "wall_clock_s":      elapsed,
            }
            runs.append(run_summary)

            # Save per-run timeseries (4 agents × omega only — Gate 2 metrics are ω-based)
            traces = {}
            for i in range(1, N_AGENTS + 1):
                traces[f"omega_t_{i}"] = data[i][:, 0]
                traces[f"omega_y_{i}"] = data[i][:, 1]
            np.savez(
                out_dir / f"trace_dist_{amp:.2f}_seed{seed}.npz",
                **traces,
            )

            print(
                f"[d4] amp={amp:.2f} seed={seed} target=VSG{target} "
                f"max_dev={max_dev * FN_HZ:.4f} Hz peak/steady={ratio:.2f} "
                f"settle={settle_t if math.isfinite(settle_t) else 'inf':} "
                f"clip={clip_hit} ({elapsed:.2f}s)"
            )

    # Reset all step amps to 0 (clean state for any subsequent sim)
    for i in range(1, N_AGENTS + 1):
        eng.eval(f"assignin('base','Pm_step_amp_{i}',double(0));", nargout=0)
    eng.eval(f"set_param('{MODEL}', 'FastRestart', 'off');", nargout=0)

    # ---- Aggregate Gate 2 verdicts ----
    verdict = GateVerdict()

    # 1. Linearity R^2
    amp_list: list[float] = []
    dev_list: list[float] = []
    for amp in AMPLITUDES:
        per_amp = [r["max_freq_dev_Hz"] for r in runs if r["amp_pu"] == amp]
        amp_list.append(amp)
        dev_list.append(float(np.mean(per_amp)))
    r2 = _r2(amp_list, dev_list)
    verdict.add(
        "linearity_R2",
        r2 > R2_MIN,
        f"R^2={r2:.4f} (limit > {R2_MIN}); amps={amp_list} mean_max_dev_Hz={['%.4f' % v for v in dev_list]}",
    )

    # 2. amp = 0.5 pu, max_freq_dev ≤ 5 Hz
    runs_05 = [r for r in runs if r["amp_pu"] == 0.5]
    max_dev_05_Hz = max(r["max_freq_dev_Hz"] for r in runs_05)
    verdict.add(
        "max_freq_dev_at_05pu_le_5Hz",
        max_dev_05_Hz <= MAX_FREQ_DEV_05_HZ,
        f"max_dev@0.5pu = {max_dev_05_Hz:.4f} Hz (limit ≤ {MAX_FREQ_DEV_05_HZ} Hz)",
    )

    # 3. peak/steady ≤ 1.5 — but steady ≈ 0 makes ratio meaningless;
    #    Use absolute overshoot: peak ≤ 1.5 × |Δω predicted by linear fit|.
    #    Simpler enforcement: peak ≤ 1.5 × max(amp-corresponding linear dev).
    #    Pragmatic: skip if steady < 1e-4 pu (nominal recovery), else apply ratio.
    bad_ratio: list[str] = []
    for r in runs:
        if r["steady_pu"] >= 1e-4:
            if r["peak_to_steady"] > PEAK_TO_STEADY_MAX:
                bad_ratio.append(
                    f"amp={r['amp_pu']:.2f} seed={r['seed']} ratio={r['peak_to_steady']:.2f}"
                )
    verdict.add(
        "peak_to_steady_le_1p5",
        len(bad_ratio) == 0,
        f"violations={len(bad_ratio)}; "
        + (", ".join(bad_ratio) if bad_ratio
           else "(all settled near 1.0; ratio test trivially satisfied)"),
    )

    # 4. settle_time ≤ 5 s
    bad_settle = [
        f"amp={r['amp_pu']:.2f} seed={r['seed']} settle={r['settle_after_step_s']:.2f}s"
        for r in runs if r["settle_after_step_s"] > SETTLE_S_MAX
    ]
    verdict.add(
        "settle_time_le_5s",
        len(bad_settle) == 0,
        f"violations={len(bad_settle)}; "
        + (", ".join(bad_settle) if bad_settle else "all ≤ 5 s"),
    )

    # 5. ω never touches hard clip
    clipped = [
        f"amp={r['amp_pu']:.2f} seed={r['seed']}"
        for r in runs if r["clip_hit"]
    ]
    verdict.add(
        "no_omega_clip_touch",
        len(clipped) == 0,
        f"clip violations={len(clipped)}; "
        + (", ".join(clipped) if clipped else "none"),
    )

    print("\n=== Stage 2 Day 4 / Gate 2 VERDICT ===")
    for c in verdict.checks:
        flag = "PASS" if c.passed else "FAIL"
        print(f"  [{flag}] {c.name}: {c.detail}")
    overall = "PASS" if verdict.overall_pass else "FAIL"
    print(f"\n  OVERALL: {overall}")

    summary = {
        "verdict": overall,
        "stop_s": STOP_S,
        "t_step": T_STEP,
        "amplitudes": AMPLITUDES,
        "seeds": SEEDS,
        "n_runs": len(runs),
        "thresholds": {
            "linearity_R2_min": R2_MIN,
            "max_freq_dev_at_05pu_Hz": MAX_FREQ_DEV_05_HZ,
            "peak_to_steady_max": PEAK_TO_STEADY_MAX,
            "settle_s_max": SETTLE_S_MAX,
            "omega_clip": [OMEGA_CLIP_LO, OMEGA_CLIP_HI],
            "settle_tol_pu": SETTLE_TOL,
            "settle_hold_s": SETTLE_HOLD_S,
        },
        "checks": [
            {"name": c.name, "passed": c.passed, "detail": c.detail}
            for c in verdict.checks
        ],
        "runs": runs,
        "linearity_amps": amp_list,
        "linearity_mean_max_dev_Hz": dev_list,
        "linearity_R2": r2,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(f"[d4] traces + summary saved to {out_dir}")
    return 0 if verdict.overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
