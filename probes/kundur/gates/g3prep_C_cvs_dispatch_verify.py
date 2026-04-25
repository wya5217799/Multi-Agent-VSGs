"""G3-prep C verification — CVS dispatch end-to-end through SimulinkBridge.

Builds a CVS-flavoured BridgeConfig with step_strategy='cvs_signal', drives
SimulinkBridge.warmup(t_warmup=30.0), and checks the 5 D3 PASS criteria
against the resulting omega/delta/Pe Timeseries.

This is NOT Gate 3 / SAC / RL: no agent, no replay buffer, no reward, no
disturbance. Pure plumbing verification that bridge.warmup() routes to
slx_episode_warmup_cvs.m and the new .m files read CVS Timeseries correctly.

Hard criteria (D3 / Gate 1, plan §1 D3):
  1. ω in [0.999, 1.001] full 30 s, per VSG
  2. |δ| < π/2 - 0.05 (≈ 1.521 rad) full 30 s, per VSG
  3. Pe within ±5 % of Pm₀ (=0.5 pu) full 30 s, per VSG
  4. ω never touches [0.7, 1.3] hard clip
  5. inter-VSG sync (max ω - min ω over agents) < 1e-3 in tail 5 s

Pre-condition: MCP MATLAB shared session running with
matlab.engine.shareEngine('mcp_shared'); compute_kundur_cvs_powerflow.m has
already produced kundur_ic_cvs.json (D2 commit 5b269d1+); kundur_cvs.slx
exists and contains the CVS swing-eq closure (D2/D3 commits).
"""
from __future__ import annotations

import io
import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

if isinstance(sys.stdout, io.TextIOWrapper):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

WORKTREE = Path(
    r"C:\Users\27443\Desktop\Multi-Agent  VSGs\.worktrees\kundur-cvs-phasor-vsg"
)
sys.path.insert(0, str(WORKTREE))

BUILD_DIR = WORKTREE / "scenarios" / "kundur" / "simulink_models"
NR_DIR    = WORKTREE / "scenarios" / "kundur" / "matlab_scripts"
RESULTS   = WORKTREE / "results" / "cvs_g3prep_c"

MODEL = "kundur_cvs"
SHARED = "mcp_shared"

N_AGENTS = 4
WARMUP_S = 30.0
TAIL_S   = 5.0

OMEGA_BAND_LO = 0.999
OMEGA_BAND_HI = 1.001
INTD_LIMIT    = math.pi / 2 - 0.05
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


def _build_cvs_bridge_config():
    """Construct a CVS-mode BridgeConfig in pure Python — does not use
    scenarios.kundur.config_simulink (which depends on KUNDUR_MODEL_PROFILE
    env var). All required fields populated; step_strategy='cvs_signal'."""
    from engine.simulink_bridge import BridgeConfig

    # NOTE: BridgeConfig.__post_init__ enforces "pe_measurement='vi' requires
    # both vabc_signal and iabc_signal set" — a constraint authored for the
    # NE39/legacy phang_feedback path. CVS .m files IGNORE these signals
    # (Pe is read directly from Pe_ts_<i>). To pass the existing validation
    # without extending BridgeConfig (per G3-prep-C scope), we set placeholder
    # template strings here. The CVS .m never reads them.
    return BridgeConfig(
        model_name="kundur_cvs",
        model_dir=str(BUILD_DIR),
        n_agents=N_AGENTS,
        dt_control=0.2,
        sbase_va=1.0e8,
        m_path_template="{model}/M_{idx}",   # informational; CVS does not set_param
        d_path_template="{model}/D_{idx}",
        omega_signal="omega_ts_{idx}",
        # Placeholders to satisfy NE39/legacy-oriented validation; CVS .m does
        # not read these signals.
        vabc_signal="Vabc_unused_{idx}",
        iabc_signal="Iabc_unused_{idx}",
        pe_measurement="vi",
        m_var_template="M_{idx}",
        d_var_template="D_{idx}",
        m0_default=24.0,
        d0_default=18.0,
        pe0_default_vsg=0.5,
        phase_command_mode="passthrough",
        step_strategy="cvs_signal",  # G3-prep-B / C dispatch trigger
    )


def main() -> int:
    import matlab.engine
    from engine.matlab_session import MatlabSession
    from engine.simulink_bridge import SimulinkBridge

    print(f"[c] connecting to '{SHARED}'")
    eng = matlab.engine.connect_matlab(SHARED)

    # Inject the live mcp_shared engine into MatlabSession's session cache so
    # SimulinkBridge.session = MatlabSession.get(SHARED) reuses it instead of
    # spawning a new MATLAB process.
    sess = MatlabSession.get(SHARED)
    sess._eng = eng
    sess._session_id = SHARED

    # Ensure NR + slx are fresh on disk (D2/D3 already committed; this just
    # re-runs the build for reproducibility — does not modify build script).
    print("[c] running NR + rebuild (CVS path)")
    eng.eval(f"addpath('{NR_DIR.as_posix()}');", nargout=0)
    eng.eval(f"addpath('{BUILD_DIR.as_posix()}');", nargout=0)
    eng.eval("compute_kundur_cvs_powerflow();", nargout=0)
    eng.eval("build_kundur_cvs();", nargout=0)

    cfg = _build_cvs_bridge_config()
    print(f"[c] BridgeConfig: model={cfg.model_name!r} step_strategy={cfg.step_strategy!r}")
    print(f"[c]   m_var={cfg.m_var_template!r} d_var={cfg.d_var_template!r}")

    bridge = SimulinkBridge(cfg, session_id=SHARED)
    print("[c] loading model via bridge.load_model()")
    bridge.load_model()

    print(f"[c] running bridge.warmup(duration={WARMUP_S}s) — CVS dispatch")
    t0 = time.time()
    bridge.warmup(duration=WARMUP_S)
    elapsed = time.time() - t0
    print(f"[c] warmup wall-clock = {elapsed:.2f} s")

    # Pull the per-agent Timeseries from MATLAB workspace (the warmup function
    # leaves them in the simOut local — re-run a brief sim to capture them
    # OR query the global workspace where the .slx logs them).
    # NOTE: simOut is local to slx_episode_warmup_cvs and not retained.
    # Re-run a fresh sim() at duration WARMUP_S, reading IC from base ws
    # which slx_episode_warmup_cvs already populated.
    eng.eval(
        f"set_param('{MODEL}', 'StopTime', '{WARMUP_S}'); "
        f"so_c = sim('{MODEL}', 'StopTime', '{WARMUP_S}', "
        f"'ReturnWorkspaceOutputs', 'on');",
        nargout=0,
    )

    ts: dict[int, dict[str, np.ndarray]] = {}
    for i in range(1, N_AGENTS + 1):
        eng.eval(
            f"o_{i} = so_c.get('omega_ts_{i}'); "
            f"d_{i} = so_c.get('delta_ts_{i}'); "
            f"p_{i} = so_c.get('Pe_ts_{i}'); "
            f"ot_{i} = double(o_{i}.Time); od_{i} = double(o_{i}.Data); "
            f"dt_{i} = double(d_{i}.Time); dd_{i} = double(d_{i}.Data); "
            f"pt_{i} = double(p_{i}.Time); pd_{i} = double(p_{i}.Data);",
            nargout=0,
        )
        ts[i] = {
            "omega_t": np.asarray(eng.workspace[f"ot_{i}"]).flatten(),
            "omega":   np.asarray(eng.workspace[f"od_{i}"]).flatten(),
            "delta_t": np.asarray(eng.workspace[f"dt_{i}"]).flatten(),
            "delta":   np.asarray(eng.workspace[f"dd_{i}"]).flatten(),
            "Pe_t":    np.asarray(eng.workspace[f"pt_{i}"]).flatten(),
            "Pe":      np.asarray(eng.workspace[f"pd_{i}"]).flatten(),
        }

    ic = json.loads(
        (WORKTREE / "scenarios" / "kundur" / "kundur_ic_cvs.json").read_text(encoding="utf-8")
    )
    Pm0 = ic["vsg_pm0_pu"]

    # 5 D3 hard criteria
    verdict = GateVerdict()

    omega_ok = True
    omega_det = []
    for i in range(1, N_AGENTS + 1):
        w = ts[i]["omega"]
        wmin = float(w.min()); wmax = float(w.max())
        ok = (wmin >= OMEGA_BAND_LO) and (wmax <= OMEGA_BAND_HI)
        omega_ok &= ok
        omega_det.append(f"VSG{i}: ω∈[{wmin:.6f},{wmax:.6f}]")
    verdict.add("omega_in_band_full_30s", omega_ok, "; ".join(omega_det))

    intd_ok = True
    intd_det = []
    for i in range(1, N_AGENTS + 1):
        dmax = float(np.abs(ts[i]["delta"]).max())
        ok = dmax < INTD_LIMIT
        intd_ok &= ok
        intd_det.append(f"VSG{i}: |δ|max={dmax:.4f}")
    verdict.add("intd_margin_full_30s", intd_ok, f"limit {INTD_LIMIT:.4f}; " + "; ".join(intd_det))

    pe_ok = True
    pe_det = []
    for i in range(1, N_AGENTS + 1):
        pm_i = float(Pm0[i - 1])
        pe = ts[i]["Pe"]
        pemin, pemax = float(pe.min()), float(pe.max())
        rel = max(abs(pemin - pm_i), abs(pemax - pm_i)) / pm_i if pm_i else float("inf")
        ok = rel < PE_RTOL
        pe_ok &= ok
        pe_det.append(f"VSG{i}: Pe∈[{pemin:.4f},{pemax:.4f}] rel={rel:.2%}")
    verdict.add("pe_within_5pct_full_30s", pe_ok, "; ".join(pe_det))

    clip_ok = True
    clip_det = []
    for i in range(1, N_AGENTS + 1):
        w = ts[i]["omega"]
        clipped = bool((w <= OMEGA_CLIP_LO).any() or (w >= OMEGA_CLIP_HI).any())
        clip_ok &= not clipped
        clip_det.append(f"VSG{i}: clip_touch={clipped}")
    verdict.add("omega_no_hard_clip", clip_ok, "; ".join(clip_det))

    tail_means = []
    for i in range(1, N_AGENTS + 1):
        t = ts[i]["omega_t"]; w = ts[i]["omega"]
        mask = t >= (t[-1] - TAIL_S)
        tail_means.append(float(w[mask].mean()))
    spread = max(tail_means) - min(tail_means)
    verdict.add(
        "inter_agent_sync_tail5s",
        spread < SYNC_TOL,
        f"tail_means={['%.6f' % v for v in tail_means]} spread={spread:.3e}",
    )

    print("\n=== G3-prep C — CVS dispatch verification VERDICT ===")
    for c in verdict.checks:
        flag = "PASS" if c.passed else "FAIL"
        print(f"  [{flag}] {c.name}: {c.detail}")
    overall = "PASS" if verdict.overall_pass else "FAIL"
    print(f"\n  OVERALL: {overall}")

    stamp = time.strftime("%Y%m%dT%H%M%S", time.localtime())
    out_dir = RESULTS / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "verdict": overall,
        "warmup_s": WARMUP_S,
        "wall_clock_s": elapsed,
        "checks": [
            {"name": c.name, "passed": c.passed, "detail": c.detail}
            for c in verdict.checks
        ],
        "per_agent": {
            f"VSG{i}": {
                "omega_min": float(ts[i]["omega"].min()),
                "omega_max": float(ts[i]["omega"].max()),
                "delta_abs_max": float(np.abs(ts[i]["delta"]).max()),
                "Pe_min": float(ts[i]["Pe"].min()),
                "Pe_max": float(ts[i]["Pe"].max()),
                "Pm0": float(Pm0[i - 1]),
            } for i in range(1, N_AGENTS + 1)
        },
        "tail_means_omega": tail_means,
        "tail_spread": spread,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[c] summary saved to {out_dir / 'summary.json'}")
    return 0 if verdict.overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
