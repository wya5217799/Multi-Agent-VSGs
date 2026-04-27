"""P4.1 deeper diagnostic — capture native MATLAB sim() error in UTF-8.

Replicates the slx_episode_warmup_cvs setup steps, then runs
sim('kundur_cvs_v3') under a custom MATLAB try/catch that writes
ME.message + ME.identifier + cause chain to a UTF-8 file using
unicode2native, bypassing the matlab.engine str round-trip that
loses Chinese-locale bytes.

Read-only on disk; no helper / model edits. Diagnosis only.
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

    err_file = (
        REPO_ROOT
        / "results"
        / "harness"
        / "kundur"
        / "cvs_v3_phase4"
        / "p41_native_err_utf8.txt"
    )
    err_file.parent.mkdir(parents=True, exist_ok=True)
    if err_file.exists():
        err_file.unlink()

    print("DIAG2: starting matlab engine ...")
    eng = me.start_matlab()
    print("DIAG2: engine started")

    eng.addpath(str(REPO_ROOT / "slx_helpers"), nargout=0)
    eng.addpath(str(REPO_ROOT / "slx_helpers" / "vsg_bridge"), nargout=0)
    model_dir = REPO_ROOT / "scenarios" / "kundur" / "simulink_models"
    eng.cd(str(model_dir), nargout=0)
    print(f"DIAG2: cwd={model_dir}")

    ic_path = REPO_ROOT / "scenarios" / "kundur" / "kundur_ic_cvs_v3.json"
    ic = json.loads(ic_path.read_text(encoding="utf-8"))
    print(f"DIAG2: IC schema={ic.get('schema_version')} converged={ic['powerflow']['converged']}")

    # Mirror slx_episode_warmup_cvs Phase 1a/1b: write M_i, D_i, Pm_i,
    # delta0_i, Pm_step_t_i, Pm_step_amp_i for i=1..4.
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
    print("DIAG2: workspace vars seeded for ESS 1..4")

    # Load the model and enable FastRestart (mirrors slx_runtime_reset on=true,
    # but we use set_param directly so we don't depend on helper return values).
    eng.eval(
        "if ~bdIsLoaded('kundur_cvs_v3'), load_system('kundur_cvs_v3'); end; "
        "set_param('kundur_cvs_v3', 'FastRestart', 'on'); "
        "set_param('kundur_cvs_v3', 'StopTime', '10.0');",
        nargout=0,
    )
    print("DIAG2: FastRestart enabled, StopTime=10.0")

    # Custom try/catch that writes the FULL native error chain to UTF-8.
    err_path_str = str(err_file).replace("\\", "/")
    eng.eval(
        "fid = fopen('"
        + err_path_str
        + "', 'w'); "
        "try; "
        "  simOut = sim('kundur_cvs_v3'); "
        "  fwrite(fid, unicode2native('SUCCESS', 'UTF-8')); "
        "catch ME; "
        "  msg = sprintf('IDENT: %s\\nMESSAGE:\\n%s\\n', ME.identifier, ME.message); "
        "  if isprop(ME, 'cause') && ~isempty(ME.cause); "
        "    for k = 1:length(ME.cause); "
        "      msg = sprintf('%s\\nCAUSE[%d] IDENT: %s\\nCAUSE[%d] MESSAGE:\\n%s\\n', "
        "        msg, k, ME.cause{k}.identifier, k, ME.cause{k}.message); "
        "    end; "
        "  end; "
        "  if isprop(ME, 'stack') && ~isempty(ME.stack); "
        "    msg = sprintf('%s\\nSTACK:\\n', msg); "
        "    for k = 1:length(ME.stack); "
        "      msg = sprintf('%s  [%d] %s line %d\\n', msg, k, ME.stack(k).name, ME.stack(k).line); "
        "    end; "
        "  end; "
        "  fwrite(fid, unicode2native(msg, 'UTF-8')); "
        "end; "
        "fclose(fid);",
        nargout=0,
    )
    print(f"DIAG2: native error file written: {err_file}")

    # Read the file as raw bytes -> decode as UTF-8 in Python.
    with err_file.open("rb") as f:
        data = f.read()
    text = data.decode("utf-8", errors="replace")
    print("DIAG2: ----- native UTF-8 error -----")
    print(text)
    print("DIAG2: ----- end native error -----")

    eng.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
