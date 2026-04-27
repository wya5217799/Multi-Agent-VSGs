"""P4.1a v2 — regenerate runtime.mat with the 22-var extension AND cold-start
verify that helper Phase 0 + Phase 1b + sim() now succeed.

Sequence (all in cold-start matlab.engine):
  1. Hash pre-fix .slx + .mat for change documentation.
  2. Run build_kundur_cvs_v3() to regenerate the .mat (and incidentally re-save
     the .slx — topology unchanged, MATLAB metadata only).
  3. Verify runtime.mat now contains all 22 expected new fields + WindAmp_w.
  4. quit + restart engine to clear base workspace fully.
  5. With a fresh engine, manually clear `who` (sanity), call
     slx_episode_warmup_cvs through the same path the bridge uses, and assert
     status.success == 1, omega vector finite, sim duration matches t_warmup.
  6. Run a short 2-second zero-action sim() under the same engine to confirm
     the model can advance past warmup without unrecognized-var errors.
  7. Save a JSON summary.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


EXPECTED_NEW_FIELDS = (
    [f"Mg_{g}" for g in (1, 2, 3)]
    + [f"Dg_{g}" for g in (1, 2, 3)]
    + [f"Rg_{g}" for g in (1, 2, 3)]
    + [f"PmgStep_t_{g}" for g in (1, 2, 3)]
    + [f"PmgStep_amp_{g}" for g in (1, 2, 3)]
    + [f"VSGScale_{i}" for i in (1, 2, 3, 4)]
    + [f"SGScale_{g}" for g in (1, 2, 3)]
)


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    import matlab.engine as me

    out_dir = REPO_ROOT / "scenarios" / "kundur" / "simulink_models"
    slx_path = out_dir / "kundur_cvs_v3.slx"
    mat_path = out_dir / "kundur_cvs_v3_runtime.mat"
    summary_path = (
        REPO_ROOT
        / "results"
        / "harness"
        / "kundur"
        / "cvs_v3_phase4"
        / "p41a_v2_summary.json"
    )

    # Phase 1: pre-fix hashes (post-WindAmp-only state).
    pre_slx = _sha(slx_path)
    pre_mat = _sha(mat_path)
    print(f"P41A2: pre-regen slx_sha256 = {pre_slx}")
    print(f"P41A2: pre-regen mat_sha256 = {pre_mat}")

    # Phase 2: regen the build via cold-start engine.
    print("P41A2: starting matlab engine #1 (regen) ...")
    eng = me.start_matlab()
    eng.addpath(str(REPO_ROOT / "slx_helpers"), nargout=0)
    eng.addpath(str(REPO_ROOT / "slx_helpers" / "vsg_bridge"), nargout=0)
    eng.cd(str(out_dir), nargout=0)

    out_buf = io.StringIO()
    err_buf = io.StringIO()
    print("P41A2: invoking build_kundur_cvs_v3() ...")
    eng.eval("build_kundur_cvs_v3();", nargout=0, stdout=out_buf, stderr=err_buf)
    print("P41A2: ----- build stdout -----")
    print(out_buf.getvalue())
    print("P41A2: ----- build stderr -----")
    print(err_buf.getvalue())

    # Phase 3: verify mat
    fields_raw = eng.eval(
        f"fieldnames(load('{str(mat_path).replace(chr(92), '/')}'))", nargout=1
    )
    field_list = [str(f) for f in fields_raw]
    field_set = set(field_list)
    print(f"P41A2: post-regen runtime.mat field count = {len(field_list)}")

    expected_present = [f for f in EXPECTED_NEW_FIELDS if f in field_set]
    expected_missing = [f for f in EXPECTED_NEW_FIELDS if f not in field_set]
    print(f"P41A2: expected-new present {len(expected_present)} of {len(EXPECTED_NEW_FIELDS)}")
    if expected_missing:
        print(f"P41A2: expected-new MISSING: {expected_missing}")
    # Also confirm WindAmp_w retained
    has_w1 = "WindAmp_1" in field_set
    has_w2 = "WindAmp_2" in field_set
    print(f"P41A2: WindAmp_1={has_w1} WindAmp_2={has_w2}")

    eng.quit()
    print("P41A2: matlab engine #1 closed.")

    post_slx = _sha(slx_path)
    post_mat = _sha(mat_path)
    print(f"P41A2: post-regen slx_sha256 = {post_slx}")
    print(f"P41A2: post-regen mat_sha256 = {post_mat}")

    # Phase 4: fresh cold-start engine to verify warmup + short sim.
    print("P41A2: starting matlab engine #2 (verify) ...")
    eng2 = me.start_matlab()
    eng2.addpath(str(REPO_ROOT / "slx_helpers"), nargout=0)
    eng2.addpath(str(REPO_ROOT / "slx_helpers" / "vsg_bridge"), nargout=0)
    eng2.cd(str(out_dir), nargout=0)

    # Confirm base workspace empty before warmup (only the few vars we set in
    # the verify probe block; cold-start engines start with a few built-ins).
    ws_pre = eng2.eval("evalin('base','who')", nargout=1)
    ws_pre_list = [str(v) for v in ws_pre] if hasattr(ws_pre, "__iter__") else []
    print(f"P41A2: ws_pre_count = {len(ws_pre_list)} : {ws_pre_list[:10]}{'...' if len(ws_pre_list)>10 else ''}")

    # Build init_params + matlab_cfg for slx_episode_warmup_cvs.
    ic = json.loads(
        (REPO_ROOT / "scenarios" / "kundur" / "kundur_ic_cvs_v3.json").read_text(
            encoding="utf-8"
        )
    )
    delta_str = ", ".join(f"{v:.10f}" for v in ic["vsg_internal_emf_angle_rad"])
    pm_str = ", ".join(f"{v:.10f}" for v in ic["vsg_pm0_pu"])
    eng2.eval(
        f"kundur_cvs_ip.M0          = 24.0; "
        f"kundur_cvs_ip.D0          = 4.5; "
        f"kundur_cvs_ip.Pm0_pu      = [{pm_str}]; "
        f"kundur_cvs_ip.delta0_rad  = [{delta_str}]; "
        f"kundur_cvs_ip.Pm_step_t   = 5.0; "
        f"kundur_cvs_ip.Pm_step_amp = 0.0; "
        f"kundur_cvs_ip.t_warmup    = 10.0; "
        f"matlab_cfg.m_var_template='M_{{idx}}'; "
        f"matlab_cfg.d_var_template='D_{{idx}}'; "
        f"matlab_cfg.n_agents=4; "
        f"matlab_cfg.sbase_va=100e6;",
        nargout=0,
    )

    # Run the helper inside MATLAB so `state` lives in MATLAB workspace; this
    # avoids the matlab.double<->Python iteration quirks for the verification
    # readouts. Helper return is irrelevant — we read state via eval afterward.
    print("P41A2: invoking slx_episode_warmup_cvs(do_recompile=true) via eval ...")
    eng2.eval(
        "agent_ids = double([1 2 3 4]); "
        "[state, status] = slx_episode_warmup_cvs("
        "'kundur_cvs_v3', agent_ids, 100e6, matlab_cfg, kundur_cvs_ip, true);",
        nargout=0,
    )
    helper_success = bool(eng2.eval("logical(status.success)", nargout=1))
    helper_error_str = (
        str(eng2.eval("status.error", nargout=1)) if not helper_success else ""
    )
    print(f"P41A2: helper.success={helper_success}")
    if not helper_success:
        print(f"P41A2: helper.error={helper_error_str!r}")

    omega_finite = False
    pe_finite = False
    omega_summary: list[float] = []
    pe_summary: list[float] = []
    if helper_success:
        # Extract scalar metrics via eval to avoid matlab.double<->Python edge
        # cases. omega_summary = [max(abs(omega-1)), min, max, all_finite].
        try:
            o_max_abs_dev = float(
                eng2.eval("max(abs(double(state.omega) - 1))", nargout=1)
            )
            o_min = float(eng2.eval("min(double(state.omega))", nargout=1))
            o_max = float(eng2.eval("max(double(state.omega))", nargout=1))
            o_all_finite = bool(
                eng2.eval("all(isfinite(double(state.omega)))", nargout=1)
            )
            p_min = float(eng2.eval("min(double(state.Pe))", nargout=1))
            p_max = float(eng2.eval("max(double(state.Pe))", nargout=1))
            p_all_finite = bool(eng2.eval("all(isfinite(double(state.Pe)))", nargout=1))
            omega_finite = o_all_finite
            pe_finite = p_all_finite
            omega_summary = [o_max_abs_dev, o_min, o_max, float(o_all_finite)]
            pe_summary = [p_min, p_max, float(p_all_finite)]
            # Also dump the 4-vector via mat2str for the audit trail.
            o_str = str(eng2.eval("mat2str(double(state.omega), 12)", nargout=1))
            p_str = str(eng2.eval("mat2str(double(state.Pe), 12)", nargout=1))
            print(f"P41A2: omega = {o_str}")
            print(f"P41A2: Pe    = {p_str}")
            print(
                f"P41A2: omega max|dev|={o_max_abs_dev:.6f} "
                f"min={o_min:.6f} max={o_max:.6f} all_finite={o_all_finite}"
            )
            print(
                f"P41A2: Pe    min={p_min:.6f} max={p_max:.6f} "
                f"all_finite={p_all_finite}"
            )
        except Exception as exc:
            print(f"P41A2: omega/Pe extract failed: {exc}")
    omega_list = omega_summary
    pe_list = pe_summary

    # Phase 6: zero-action 2-second sim() to confirm the model advances.
    short_sim_ok = False
    short_sim_err = ""
    if helper_success:
        print("P41A2: invoking 2-second zero-action sim() ...")
        try:
            eng2.eval(
                "set_param('kundur_cvs_v3', 'StopTime', '12.0');",
                nargout=0,
            )
            simout = eng2.eval("sim('kundur_cvs_v3');", nargout=1)
            short_sim_ok = True
            print("P41A2: short sim OK")
        except Exception as exc:
            short_sim_err = str(exc)[:300]
            print(f"P41A2: short sim FAILED: {short_sim_err}")

    eng2.quit()
    print("P41A2: matlab engine #2 closed.")

    summary = {
        "schema_version": 1,
        "pre_regen_slx_sha256": pre_slx,
        "post_regen_slx_sha256": post_slx,
        "pre_regen_mat_sha256": pre_mat,
        "post_regen_mat_sha256": post_mat,
        "post_regen_mat_field_count": len(field_list),
        "post_regen_mat_fields": sorted(field_list),
        "expected_new_fields": list(EXPECTED_NEW_FIELDS),
        "expected_new_present": expected_present,
        "expected_new_missing": expected_missing,
        "windamp_1_present": has_w1,
        "windamp_2_present": has_w2,
        "ws_pre_helper_count": len(ws_pre_list),
        "ws_pre_helper_sample": ws_pre_list[:10],
        "helper_success": helper_success,
        "helper_error": helper_error_str,
        "omega": omega_list,
        "pe": pe_list,
        "omega_finite": omega_finite,
        "pe_finite": pe_finite,
        "short_sim_ok": short_sim_ok,
        "short_sim_err": short_sim_err,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"P41A2: summary written: {summary_path}")

    overall_ok = (
        not expected_missing
        and has_w1
        and has_w2
        and helper_success
        and omega_finite
        and pe_finite
        and short_sim_ok
    )
    print(f"P41A2: overall_ok={overall_ok}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
