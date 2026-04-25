"""Stage 2 Day 1 — Kundur CVS 7-bus topology structural verification.

Connects to the MCP shared MATLAB session, (re)builds ``kundur_cvs.slx``,
and exercises the 4 D1 pass criteria:

  1. ``simulink_compile_diagnostics(mode='update')`` -> 0 errors / 0 warnings
  2. 0.5 s static sim -> ``status='success'``, 0 errors, 0 warnings
  3. All 4 driven CVS configured ``Source_Type=DC, Initialize=off,
     Measurements=None``; each CVS Inport sourced from the matching ``RI2C_i``
     (uniform RI2C complex path).
  4. 7 buses present per the build script intent (4 driven CVS terminals,
     Bus_A, Bus_B, Bus_INF), with the implicit Simscape physical-domain
     branching realising the 3 multi-port nodes Bus_A / Bus_B / Bus_INF.

NOT in scope (deferred to D2/D3+):
  - Newton-Raphson IC validation (D2)
  - 30 s zero-action stability (D3 / Gate 1)
  - Disturbance sweep (D4 / Gate 2)
  - Swing-equation closure / RL agent

Engine pre-condition: MATLAB MCP shared session must already have run
``matlab.engine.shareEngine('mcp_shared')`` (this is the standard MCP
launch). If absent, this script raises a clear error.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import matlab.engine

WORKTREE = Path(
    r"C:\Users\27443\Desktop\Multi-Agent  VSGs\.worktrees\kundur-cvs-phasor-vsg"
)
BUILD_DIR = WORKTREE / "scenarios" / "kundur" / "simulink_models"
GATES_DIR = WORKTREE / "probes" / "kundur" / "gates"
SLX_PATH = BUILD_DIR / "kundur_cvs.slx"
MODEL = "kundur_cvs"
SHARED = "mcp_shared"

EXPECTED_COUNTS: dict[str, int] = {
    "CVS_VSG": 4,
    "AC_INF": 1,
    "L_v": 4,
    "L_tie": 1,
    "L_inf": 1,
    "Load_A": 1,
    "Load_B": 1,
    "RI2C": 4,
    "Vr": 4,
    "Vi": 4,
    "GND_VSG": 4,
    "GND_LA": 1,
    "GND_LB": 1,
    "GND_INF": 1,
    "powergui": 1,
}


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class D1Verdict:
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


def _rebuild_model(eng: matlab.engine.MatlabEngine) -> None:
    eng.eval(f"addpath('{BUILD_DIR.as_posix()}');", nargout=0)
    eng.eval("build_kundur_cvs();", nargout=0)


def _compile_update(eng: matlab.engine.MatlabEngine) -> tuple[int, int]:
    eng.eval(
        f"lastwarn(''); err_count = 0; "
        f"try; set_param('{MODEL}', 'SimulationCommand', 'update'); "
        f"catch e; err_count = 1; end",
        nargout=0,
    )
    err_count = int(eng.workspace["err_count"])
    last_warn = str(eng.eval("lastwarn", nargout=1))
    warn_count = 0 if last_warn.strip() == "" else 1
    return err_count, warn_count


def _run_05s_sim(eng: matlab.engine.MatlabEngine) -> tuple[bool, str]:
    eng.eval(f"lastwarn(''); set_param('{MODEL}', 'StopTime', '0.5');", nargout=0)
    err = ""
    try:
        eng.eval(
            f"so_d1 = sim('{MODEL}', 'StopTime', '0.5', "
            f"'ReturnWorkspaceOutputs', 'on');",
            nargout=0,
        )
    except matlab.engine.MatlabExecutionError as exc:
        return False, str(exc)
    last_warn = str(eng.eval("lastwarn", nargout=1))
    if last_warn.strip():
        err = f"warning: {last_warn}"
    return True, err


def _check_cvs_config(eng: matlab.engine.MatlabEngine) -> list[tuple[int, str, str, str]]:
    out: list[tuple[int, str, str, str]] = []
    for i in range(1, 5):
        st = str(eng.eval(f"get_param('{MODEL}/CVS_VSG{i}','Source_Type')", nargout=1))
        ini = str(eng.eval(f"get_param('{MODEL}/CVS_VSG{i}','Initialize')", nargout=1))
        meas = str(eng.eval(f"get_param('{MODEL}/CVS_VSG{i}','Measurements')", nargout=1))
        out.append((i, st, ini, meas))
    return out


def _check_cvs_input_source(eng: matlab.engine.MatlabEngine) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for i in range(1, 5):
        eng.eval(
            f"ph_d1_{i} = get_param('{MODEL}/CVS_VSG{i}','PortHandles'); "
            f"ln_d1_{i} = get_param(ph_d1_{i}.Inport(1),'Line'); "
            f"if ln_d1_{i} ~= -1; "
            f"  sp_d1_{i} = get_param(ln_d1_{i},'SrcPortHandle'); "
            f"  if sp_d1_{i} ~= -1; "
            f"    src_d1_{i} = get_param(get_param(sp_d1_{i},'Parent'),'Name'); "
            f"  else; src_d1_{i} = ''; end; "
            f"else; src_d1_{i} = ''; end",
            nargout=0,
        )
        src = str(eng.workspace[f"src_d1_{i}"])
        out.append((i, src))
    return out


def _check_block_counts(eng: matlab.engine.MatlabEngine) -> dict[str, int]:
    eng.eval(f"addpath('{GATES_DIR.as_posix()}'); verify_kundur_cvs_topology();",
             nargout=0)
    counts: dict[str, int] = {}
    name_regex = {
        "CVS_VSG": r"^CVS_VSG\d$",
        "L_v": r"^L_v_\d$",
        "RI2C": r"^RI2C_\d$",
        "Vr": r"^Vr_\d$",
        "Vi": r"^Vi_\d$",
        "GND_VSG": r"^GND_VSG\d$",
    }
    plain = ["AC_INF", "L_tie", "L_inf", "Load_A", "Load_B", "GND_LA", "GND_LB",
             "GND_INF", "powergui"]
    for key, rx in name_regex.items():
        n = int(eng.eval(
            f"numel(find_system('{MODEL}','Regexp','on','Name','{rx}'))", nargout=1))
        counts[key] = n
    for nm in plain:
        n = int(eng.eval(
            f"numel(find_system('{MODEL}','Name','{nm}'))", nargout=1))
        counts[nm] = n
    return counts


def _check_powergui(eng: matlab.engine.MatlabEngine) -> tuple[str, str]:
    mode = str(eng.eval(f"get_param('{MODEL}/powergui','SimulationMode')", nargout=1))
    freq = str(eng.eval(f"get_param('{MODEL}/powergui','frequency')", nargout=1))
    return mode, freq


def main() -> int:
    print(f"[d1] connecting to shared MATLAB session '{SHARED}'")
    eng = _connect_engine()

    print(f"[d1] rebuilding {MODEL}.slx via build_kundur_cvs()")
    _rebuild_model(eng)

    verdict = D1Verdict()

    err, warn = _compile_update(eng)
    verdict.add(
        "compile_update_clean",
        err == 0 and warn == 0,
        f"errors={err} warnings={warn}",
    )
    print(f"[d1] compile_update errors={err} warnings={warn}")

    sim_ok, sim_detail = _run_05s_sim(eng)
    verdict.add("sim_05s_success", sim_ok and not sim_detail, sim_detail or "0/0")
    print(f"[d1] 0.5s sim ok={sim_ok} detail='{sim_detail}'")

    cvs_cfg = _check_cvs_config(eng)
    cfg_ok = all(
        st == "DC" and ini == "off" and meas == "None"
        for _, st, ini, meas in cvs_cfg
    )
    verdict.add(
        "cvs_dc_initoff_measnone",
        cfg_ok,
        "; ".join(f"VSG{i}:{st}/{ini}/{meas}" for i, st, ini, meas in cvs_cfg),
    )
    print(f"[d1] CVS config uniform DC+Init=off+Meas=None: {cfg_ok}")

    cvs_src = _check_cvs_input_source(eng)
    src_ok = all(src == f"RI2C_{i}" for i, src in cvs_src)
    verdict.add(
        "cvs_input_uniform_RI2C",
        src_ok,
        "; ".join(f"VSG{i}<-{s}" for i, s in cvs_src),
    )
    print(f"[d1] CVS Inport <- RI2C_i uniform: {src_ok}")

    counts = _check_block_counts(eng)
    counts_ok = all(counts.get(k, -1) == v for k, v in EXPECTED_COUNTS.items())
    verdict.add(
        "block_counts_match_intent",
        counts_ok,
        ", ".join(f"{k}={counts.get(k, '?')}/{v}" for k, v in EXPECTED_COUNTS.items()),
    )
    print(f"[d1] block counts match: {counts_ok}")

    mode, freq = _check_powergui(eng)
    pg_ok = mode == "Phasor" and freq == "50"
    verdict.add("powergui_phasor_50hz", pg_ok, f"mode={mode} freq={freq}")
    print(f"[d1] powergui Phasor 50Hz: {pg_ok}")

    print("\n=== Stage 2 Day 1 VERDICT ===")
    for c in verdict.checks:
        flag = "PASS" if c.passed else "FAIL"
        print(f"  [{flag}] {c.name}: {c.detail}")
    overall = "PASS" if verdict.overall_pass else "FAIL"
    print(f"\n  OVERALL: {overall}")
    return 0 if verdict.overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
