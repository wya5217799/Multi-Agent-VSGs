"""P4.1 diagnostic — capture raw MATLAB error bytes from slx_episode_warmup_cvs.

Cold-starts a MATLAB engine, manually invokes the warmup chain that the
KundurSimulinkEnv would run, and prints the native MATLAB error message
in multiple decodings (GB18030 / UTF-8 / latin1) so the Chinese-locale
stderr is recoverable. Read-only on disk; no edits.

Per Phase 4.1 user GO message: "If smoke fails, stop with diagnosis only;
do not widen scope." This script is diagnosis ONLY.
"""

from __future__ import annotations

import io
import os
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    import matlab.engine as me

    print("DIAG: starting matlab engine ...")
    eng = me.start_matlab()
    print("DIAG: engine started")

    eng.addpath(str(REPO_ROOT / "slx_helpers"), nargout=0)
    eng.addpath(str(REPO_ROOT / "slx_helpers" / "vsg_bridge"), nargout=0)
    eng.cd(str(REPO_ROOT / "scenarios" / "kundur" / "simulink_models"), nargout=0)

    # Build matlab_cfg + kundur_cvs_ip in MATLAB workspace via eval (same as bridge).
    import json as _json
    ic_path = REPO_ROOT / "scenarios" / "kundur" / "kundur_ic_cvs_v3.json"
    ic = _json.loads(ic_path.read_text(encoding="utf-8"))
    delta_str = ", ".join(f"{v:.10f}" for v in ic["vsg_internal_emf_angle_rad"])
    pm_str = ", ".join(f"{v:.10f}" for v in ic["vsg_pm0_pu"])
    eng.eval(
        f"kundur_cvs_ip.M0          = 24.0; "
        f"kundur_cvs_ip.D0          = 4.5; "
        f"kundur_cvs_ip.Pm0_pu      = [{pm_str}]; "
        f"kundur_cvs_ip.delta0_rad  = [{delta_str}]; "
        f"kundur_cvs_ip.Pm_step_t   = 5.0; "
        f"kundur_cvs_ip.Pm_step_amp = 0.0; "
        f"kundur_cvs_ip.t_warmup    = 10.0;",
        nargout=0,
    )
    eng.eval(
        "matlab_cfg.m_var_template='M_{idx}'; "
        "matlab_cfg.d_var_template='D_{idx}'; "
        "matlab_cfg.n_agents=4; "
        "matlab_cfg.sbase_va=100e6;",
        nargout=0,
    )

    # Call the warmup, capture stdout / stderr in StringIO (mirrors bridge),
    # then ALSO read the returned status struct's error directly.
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    print("DIAG: invoking slx_episode_warmup_cvs(do_recompile=true) ...")
    try:
        state, status = eng.slx_episode_warmup_cvs(
            "kundur_cvs_v3",
            eng.eval("double([1 2 3 4])", nargout=1),
            100e6,
            eng.eval("matlab_cfg", nargout=1),
            eng.eval("kundur_cvs_ip", nargout=1),
            True,
            nargout=2,
            stdout=out_buf,
            stderr=err_buf,
        )
        print("DIAG: status.success =", status.get("success"))
        err_native = status.get("error", "")
        print("DIAG: status.error =", repr(err_native))
        # Try to decode mojibake -> GB18030
        if isinstance(err_native, str) and err_native:
            try:
                gb_attempt = err_native.encode("latin1", errors="replace").decode(
                    "gb18030", errors="replace"
                )
                print("DIAG: status.error decoded (latin1->gb18030) =", repr(gb_attempt))
            except Exception as exc:
                print("DIAG: gb18030 decode failed:", exc)
            try:
                cp_attempt = err_native.encode("cp1252", errors="replace").decode(
                    "gb18030", errors="replace"
                )
                print("DIAG: status.error decoded (cp1252->gb18030) =", repr(cp_attempt))
            except Exception:
                pass
        # Pull the status struct's full content so we don't miss any attribute.
        print("DIAG: status keys =", list(status.keys()) if hasattr(status, "keys") else status)
    except Exception as exc:
        print("DIAG: matlab.engine raised:", type(exc).__name__, exc)
        traceback.print_exc()

    print("DIAG: ----- captured matlab stdout (head) -----")
    txt = out_buf.getvalue()
    print(txt[:2000])
    print("DIAG: ----- captured matlab stderr (head) -----")
    err_txt = err_buf.getvalue()
    print(err_txt[:2000])
    # Try to decode the captured stderr buffer
    if err_txt:
        try:
            gb = err_txt.encode("latin1", errors="replace").decode(
                "gb18030", errors="replace"
            )
            print("DIAG: stderr decoded (latin1->gb18030):")
            print(gb[:2000])
        except Exception as exc:
            print("DIAG: stderr gb18030 decode failed:", exc)

    # Probe MATLAB locale
    try:
        info = eng.eval("[char(getenv('LANG')) '|' char(version('-release'))]", nargout=1)
        print("DIAG: LANG|MATLAB release =", info)
    except Exception:
        pass
    try:
        feat = eng.eval(
            "[char(feature('locale')) '|' char(feature('DefaultCharacterSet'))]",
            nargout=1,
        )
        print("DIAG: locale features =", feat)
    except Exception:
        pass

    # Also probe whether the model loaded; if it loaded, what's its dirty/compile state.
    try:
        present = eng.eval("bdIsLoaded('kundur_cvs_v3')", nargout=1)
        print("DIAG: bdIsLoaded(kundur_cvs_v3) =", present)
    except Exception as exc:
        print("DIAG: bdIsLoaded probe failed:", exc)

    eng.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
