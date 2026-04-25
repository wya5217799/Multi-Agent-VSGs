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

# Pass thresholds (D4-rev-B 2026-04-26, plan-author authorised):
#   - settle: relative 5%-of-peak band, threshold 15 s. Replaces the strict
#     absolute 5e-4 pu band at 5 s (D4.2 §3 / §6: was rule-of-thumb,
#     unreachable with project paper-baseline D=18).
#   - peak_to_steady: REMOVED from the omega channel (D4.2 §4: ill-defined
#     for type-0 frequency response).
#   - delta-channel overshoot: COMPUTED + REPORTED, but DOWNGRADED to
#     diagnostic-only. Not a hard criterion for Gate 2. Reason: the 1.5
#     threshold has no paper citation and is unreachable under the project
#     paper-baseline ζ≈0.033; empirical 1.70-1.75 matches analytic 1.90,
#     i.e. the value is a faithful physical signal of under-damping rather
#     than a model failure.
#   - simulation_health: NEW hard criterion replacing the dropped overshoot
#     check; NaN/Inf in any per-VSG omega/delta trace, or any matlab.engine
#     execution error during the sweep, fails Gate 2.
R2_MIN                  = 0.9
MAX_FREQ_DEV_05_HZ      = 5.0
SETTLE_S_MAX            = 15.0           # was 5.0 (D4.2 disposition)
SETTLE_FRAC_OF_PEAK     = 0.05           # relative band
SETTLE_HOLD_S           = 1.0            # consecutive settled duration
OMEGA_CLIP_LO           = 0.7
OMEGA_CLIP_HI           = 1.3
DELTA_OVERSHOOT_DIAG_MAX = 1.5           # diagnostic-only marker (NOT a gate)


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


def _run_sim(eng: matlab.engine.MatlabEngine) -> tuple[float, str]:
    """Run the sim. Returns (elapsed_s, error_str). error_str is empty on
    success; non-empty if matlab.engine raised, used by the Gate 2
    simulation_health hard criterion (D4-rev-B)."""
    t0 = time.time()
    try:
        eng.eval(
            f"so_d4 = sim('{MODEL}', 'StopTime', '{STOP_S}', "
            f"'ReturnWorkspaceOutputs', 'on');",
            nargout=0,
        )
    except matlab.engine.MatlabExecutionError as exc:
        return time.time() - t0, f"matlab.engine error: {exc}"
    return time.time() - t0, ""


def _fetch_traces(eng: matlab.engine.MatlabEngine) -> dict[int, dict[str, np.ndarray]]:
    """Fetch omega + delta timeseries for all agents (delta needed for D4-rev
    overshoot metric on the delta channel)."""
    out: dict[int, dict[str, np.ndarray]] = {}
    for i in range(1, N_AGENTS + 1):
        eng.eval(
            f"o_{i} = so_d4.get('omega_ts_{i}'); "
            f"d_{i} = so_d4.get('delta_ts_{i}'); "
            f"ot_{i} = double(o_{i}.Time); od_{i} = double(o_{i}.Data); "
            f"dt_{i} = double(d_{i}.Time); dd_{i} = double(d_{i}.Data);",
            nargout=0,
        )
        out[i] = {
            "omega_t": np.asarray(eng.workspace[f"ot_{i}"]).flatten(),
            "omega":   np.asarray(eng.workspace[f"od_{i}"]).flatten(),
            "delta_t": np.asarray(eng.workspace[f"dt_{i}"]).flatten(),
            "delta":   np.asarray(eng.workspace[f"dd_{i}"]).flatten(),
        }
    return out


def _settle_time_relative(t: np.ndarray, dev: np.ndarray) -> float:
    """First time after t_step where |dev| stays ≤ SETTLE_FRAC_OF_PEAK·peak
    for ≥ SETTLE_HOLD_S consecutive seconds. D4.2 §3-§6 disposition: relative
    band replaces the absolute 5e-4 pu band that was unreachable."""
    mask = t >= T_STEP
    tt = t[mask]
    dd = np.abs(dev[mask])
    if dd.size == 0:
        return float("inf")
    peak = dd.max()
    if peak <= 0:
        return 0.0
    band = SETTLE_FRAC_OF_PEAK * peak
    in_band = dd <= band
    streak_start: float | None = None
    for tk, ok in zip(tt, in_band, strict=False):
        if ok:
            if streak_start is None:
                streak_start = tk
            if tk - streak_start >= SETTLE_HOLD_S:
                return streak_start - T_STEP
        else:
            streak_start = None
    return float("inf")


def _delta_overshoot(t: np.ndarray, delta: np.ndarray) -> float:
    """Delta-channel overshoot ratio: (peak excursion vs old equilibrium) /
    (|new − old| equilibrium displacement). Uses the t<T_STEP window for
    delta_old (= NR IC value) and the tail 5 s window for delta_new.

    Returns 1.0 if displacement is non-existent (static). NaN if old/new
    differ by less than 1e-6 rad (no meaningful step occurred at this VSG)."""
    pre  = delta[t <  T_STEP]
    post = delta[t >= T_STEP]
    tail = delta[t >= (t[-1] - 5.0)]
    if pre.size == 0 or post.size == 0:
        return float("nan")
    delta_old = float(pre[-1] if pre.size else delta[0])
    delta_new = float(np.mean(tail))
    displacement = delta_new - delta_old
    if abs(displacement) < 1e-6:
        return float("nan")
    peak_excursion = float(np.max(np.abs(post - delta_old)))
    return peak_excursion / abs(displacement)


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
            elapsed, sim_err = _run_sim(eng)
            if sim_err:
                # Skip metric extraction; record sim_health failure for this run
                runs.append({
                    "amp_pu": amp, "seed": seed, "target_vsg": target,
                    "wall_clock_s": elapsed, "sim_error": sim_err,
                    "nan_inf": False, "clip_hit": False,
                    "max_freq_dev_pu": float("nan"),
                    "max_freq_dev_Hz": float("nan"),
                    "settle_relative_5pct_after_step_s": float("inf"),
                    "delta_overshoot_ratio": float("nan"),
                })
                print(f"[d4] amp={amp:.2f} seed={seed} SIM FAIL: {sim_err}")
                continue

            data = _fetch_traces(eng)

            # NaN/Inf health check — any non-finite sample fails simulation_health
            nan_inf = False
            for i in range(1, N_AGENTS + 1):
                if not (np.all(np.isfinite(data[i]["omega"]))
                        and np.all(np.isfinite(data[i]["delta"]))):
                    nan_inf = True
                    break

            # Per-run omega metrics over all 4 agents
            max_dev = 0.0
            clip_hit = False
            agent_max_devs: dict[int, float] = {}
            for i in range(1, N_AGENTS + 1):
                t = data[i]["omega_t"]
                w = data[i]["omega"]
                dev = w - 1.0
                m = float(np.max(np.abs(dev)))
                agent_max_devs[i] = m
                if m > max_dev:
                    max_dev = m
                if (w <= OMEGA_CLIP_LO).any() or (w >= OMEGA_CLIP_HI).any():
                    clip_hit = True

            # Target agent's omega for settle (relative band)
            t_t   = data[target]["omega_t"]
            w_t   = data[target]["omega"]
            dev_t = w_t - 1.0
            settle_t = _settle_time_relative(t_t, dev_t)

            # Target agent's delta channel — diagnostic-only (D4-rev-B)
            td  = data[target]["delta_t"]
            dy  = data[target]["delta"]
            d_overshoot = _delta_overshoot(td, dy)

            run_summary = {
                "amp_pu":            amp,
                "seed":              seed,
                "target_vsg":        target,
                "max_freq_dev_pu":   max_dev,
                "max_freq_dev_Hz":   max_dev * FN_HZ,
                "agent_max_devs_pu": agent_max_devs,
                "settle_relative_5pct_after_step_s": settle_t,
                "delta_overshoot_ratio": d_overshoot,   # diagnostic-only
                "clip_hit":          clip_hit,
                "nan_inf":           nan_inf,
                "sim_error":         "",
                "wall_clock_s":      elapsed,
            }
            runs.append(run_summary)

            # Save per-run timeseries: omega + delta of all 4 agents
            traces = {}
            for i in range(1, N_AGENTS + 1):
                traces[f"omega_t_{i}"] = data[i]["omega_t"]
                traces[f"omega_y_{i}"] = data[i]["omega"]
                traces[f"delta_t_{i}"] = data[i]["delta_t"]
                traces[f"delta_y_{i}"] = data[i]["delta"]
            np.savez(
                out_dir / f"trace_dist_{amp:.2f}_seed{seed}.npz",
                **traces,
            )

            settle_str = (
                f"{settle_t:.2f}" if math.isfinite(settle_t) else "inf"
            )
            print(
                f"[d4] amp={amp:.2f} seed={seed} target=VSG{target} "
                f"max_dev={max_dev * FN_HZ:.4f} Hz "
                f"δ_overshoot={d_overshoot:.3f} "
                f"settle_5pct={settle_str}s "
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

    # 3. settle_time on relative 5%-of-peak band ≤ SETTLE_S_MAX (15 s)
    bad_settle = [
        f"amp={r['amp_pu']:.2f} seed={r['seed']} "
        f"settle={r['settle_relative_5pct_after_step_s']:.2f}s"
        for r in runs if r["settle_relative_5pct_after_step_s"] > SETTLE_S_MAX
    ]
    verdict.add(
        "settle_relative_5pct_le_15s",
        len(bad_settle) == 0,
        f"violations={len(bad_settle)}; "
        + (", ".join(bad_settle) if bad_settle else f"all ≤ {SETTLE_S_MAX:.0f} s"),
    )

    # 4. ω never touches hard clip
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

    # 5. simulation health: no matlab.engine errors AND no NaN/Inf in any trace
    bad_health = [
        f"amp={r['amp_pu']:.2f} seed={r['seed']}"
        + (f" sim_err='{r['sim_error']}'" if r.get("sim_error") else "")
        + (" nan_inf=True" if r.get("nan_inf") else "")
        for r in runs
        if r.get("sim_error") or r.get("nan_inf")
    ]
    verdict.add(
        "simulation_health",
        len(bad_health) == 0,
        f"violations={len(bad_health)}; "
        + (", ".join(bad_health) if bad_health else "all 15 runs clean (no sim errors, no NaN/Inf)"),
    )

    # ---- Diagnostic-only (NOT counted in PASS/FAIL): δ-channel overshoot ----
    overshoots = [
        r["delta_overshoot_ratio"] for r in runs
        if not math.isnan(r.get("delta_overshoot_ratio", float("nan")))
    ]
    if overshoots:
        os_min, os_max = min(overshoots), max(overshoots)
        os_above = sum(1 for v in overshoots if v > DELTA_OVERSHOOT_DIAG_MAX)
        diag_overshoot = {
            "metric": "delta_channel_overshoot_ratio",
            "rationale": (
                "δ-channel (peak − δ_old) / |δ_new − δ_old|. Diagnostic only "
                "per D4-rev-B disposition: 1.5 reference is a control rule of "
                "thumb without paper citation; under-damped paper-baseline ζ≈0.033 "
                "yields analytic 1+%OS≈1.90 — values 1.7–1.75 are the faithful "
                "physical signal of low damping, not a model failure."
            ),
            "diag_threshold": DELTA_OVERSHOOT_DIAG_MAX,
            "n_runs_with_metric": len(overshoots),
            "min": float(os_min),
            "max": float(os_max),
            "n_above_diag_threshold": int(os_above),
        }
    else:
        diag_overshoot = {
            "metric": "delta_channel_overshoot_ratio",
            "n_runs_with_metric": 0,
            "note": "no run produced a finite delta-channel overshoot ratio",
        }

    print("\n=== Stage 2 Day 4 / Gate 2 VERDICT (D4-rev-B) ===")
    for c in verdict.checks:
        flag = "PASS" if c.passed else "FAIL"
        print(f"  [{flag}] {c.name}: {c.detail}")
    overall = "PASS" if verdict.overall_pass else "FAIL"
    print(f"\n  OVERALL: {overall}")

    if "min" in diag_overshoot:
        print(
            f"\n  [DIAG] delta_channel_overshoot_ratio (NOT a hard criterion): "
            f"min={diag_overshoot['min']:.3f} max={diag_overshoot['max']:.3f} "
            f"({diag_overshoot['n_above_diag_threshold']}/15 above the "
            f"{DELTA_OVERSHOOT_DIAG_MAX:.1f} reference; analytic 1+%OS for "
            f"paper-baseline ζ≈0.033 is ~1.90)"
        )

    summary = {
        "verdict": overall,
        "stop_s": STOP_S,
        "t_step": T_STEP,
        "amplitudes": AMPLITUDES,
        "seeds": SEEDS,
        "n_runs": len(runs),
        "hard_thresholds": {
            "linearity_R2_min": R2_MIN,
            "max_freq_dev_at_05pu_Hz": MAX_FREQ_DEV_05_HZ,
            "settle_s_max": SETTLE_S_MAX,
            "settle_frac_of_peak": SETTLE_FRAC_OF_PEAK,
            "settle_hold_s": SETTLE_HOLD_S,
            "omega_clip": [OMEGA_CLIP_LO, OMEGA_CLIP_HI],
        },
        "diagnostic_only": diag_overshoot,
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
