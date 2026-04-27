"""P4.1 deepest diagnostic — getReport(ME,'extended') on sim() failure.

The previous diagnostic showed `MATLAB:MException:MultipleErrors` with the
same placeholder message at all 3 cause levels. `getReport(ME,'extended')`
unwraps the full Simulink diagnostic chain into a single text block.

Read-only on disk; no helper / model edits.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    import matlab.engine as me

    out_path = (
        REPO_ROOT
        / "results"
        / "harness"
        / "kundur"
        / "cvs_v3_phase4"
        / "p41_native_err_extended.txt"
    )
    if out_path.exists():
        out_path.unlink()

    print("DIAG3: starting matlab engine ...")
    eng = me.start_matlab()
    eng.addpath(str(REPO_ROOT / "slx_helpers"), nargout=0)
    eng.addpath(str(REPO_ROOT / "slx_helpers" / "vsg_bridge"), nargout=0)
    eng.cd(str(REPO_ROOT / "scenarios" / "kundur" / "simulink_models"), nargout=0)
    print("DIAG3: engine ready")

    ic = json.loads(
        (REPO_ROOT / "scenarios" / "kundur" / "kundur_ic_cvs_v3.json").read_text(
            encoding="utf-8"
        )
    )
    delta_str = ", ".join(f"{v:.10f}" for v in ic["vsg_internal_emf_angle_rad"])
    pm_str = ", ".join(f"{v:.10f}" for v in ic["vsg_pm0_pu"])

    eng.eval(
        f"M0_default = 24.0; D0_default = 4.5; "
        f"Pm0_pu = [{pm_str}]; "
        f"delta0_rad = [{delta_str}]; "
        f"for i = 1:4, "
        f"  assignin('base', sprintf('M_%d', i), double(M0_default)); "
        f"  assignin('base', sprintf('D_%d', i), double(D0_default)); "
        f"  assignin('base', sprintf('Pm_%d', i), double(Pm0_pu(i))); "
        f"  assignin('base', sprintf('delta0_%d', i), double(delta0_rad(i))); "
        f"  assignin('base', sprintf('Pm_step_t_%d', i), double(5.0)); "
        f"  assignin('base', sprintf('Pm_step_amp_%d', i), double(0.0)); "
        f"end",
        nargout=0,
    )
    eng.eval(
        "if ~bdIsLoaded('kundur_cvs_v3'), load_system('kundur_cvs_v3'); end; "
        "set_param('kundur_cvs_v3', 'FastRestart', 'on'); "
        "set_param('kundur_cvs_v3', 'StopTime', '10.0');",
        nargout=0,
    )

    out_str = str(out_path).replace("\\", "/")
    eng.eval(
        "fid = fopen('" + out_str + "', 'w'); "
        "try; "
        "  simOut = sim('kundur_cvs_v3'); "
        "  fwrite(fid, unicode2native('SUCCESS', 'UTF-8')); "
        "catch ME; "
        "  rep = getReport(ME, 'extended', 'hyperlinks', 'off'); "
        "  fwrite(fid, unicode2native(rep, 'UTF-8')); "
        "end; "
        "fclose(fid);",
        nargout=0,
    )
    print(f"DIAG3: extended report written: {out_path}")

    text = out_path.read_text(encoding="utf-8", errors="replace")
    print("DIAG3: ----- extended report -----")
    print(text)
    print("DIAG3: ----- end extended report -----")

    eng.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
