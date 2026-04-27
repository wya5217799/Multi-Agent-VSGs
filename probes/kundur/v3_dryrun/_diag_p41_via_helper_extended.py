"""P4.1 final diagnostic — call slx_episode_warmup_cvs (the actual helper used
by SimulinkBridge), then catch its failure and emit getReport(extended) of
the *underlying* sim() error so we know exactly which workspace vars
.runtime.mat does NOT seed.

Read-only on disk; no helper / model edits.
"""

from __future__ import annotations

import json
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
        / "p41_helper_native_err_extended.txt"
    )
    if out_path.exists():
        out_path.unlink()

    print("DIAG4: starting matlab engine ...")
    eng = me.start_matlab()
    eng.addpath(str(REPO_ROOT / "slx_helpers"), nargout=0)
    eng.addpath(str(REPO_ROOT / "slx_helpers" / "vsg_bridge"), nargout=0)
    eng.cd(str(REPO_ROOT / "scenarios" / "kundur" / "simulink_models"), nargout=0)
    print("DIAG4: engine ready")

    ic = json.loads(
        (REPO_ROOT / "scenarios" / "kundur" / "kundur_ic_cvs_v3.json").read_text(
            encoding="utf-8"
        )
    )
    delta_str = ", ".join(f"{v:.10f}" for v in ic["vsg_internal_emf_angle_rad"])
    pm_str = ", ".join(f"{v:.10f}" for v in ic["vsg_pm0_pu"])

    eng.eval(
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

    out_str = str(out_path).replace("\\", "/")
    eng.eval(
        "fid = fopen('" + out_str + "', 'w'); "
        # First, check what the runtime.mat contains, and what's in workspace
        # before/after the helper runs:
        "rmat = fullfile(fileparts(which('kundur_cvs_v3')), 'kundur_cvs_v3_runtime.mat'); "
        "mat_info = sprintf('runtime_mat=%s exists=%d', rmat, exist(rmat,'file')==2); "
        "fwrite(fid, unicode2native([mat_info char(10)], 'UTF-8')); "
        "if exist(rmat,'file')==2; "
        "  consts = load(rmat); cn = fieldnames(consts); "
        "  cn_str = sprintf('runtime_mat fields: %s', strjoin(cn, ', ')); "
        "  fwrite(fid, unicode2native([cn_str char(10) char(10)], 'UTF-8')); "
        "end; "
        "ws_before = evalin('base', 'who'); "
        "fwrite(fid, unicode2native(['ws_before_helper:' char(10)], 'UTF-8')); "
        "fwrite(fid, unicode2native([strjoin(ws_before, ', ') char(10) char(10)], 'UTF-8')); "
        # Now call the actual helper.
        "try; "
        "  agent_ids = double([1 2 3 4]); "
        "  [state, status] = slx_episode_warmup_cvs('kundur_cvs_v3', agent_ids, 100e6, matlab_cfg, kundur_cvs_ip, true); "
        "  fwrite(fid, unicode2native([sprintf('helper.success=%d', status.success) char(10)], 'UTF-8')); "
        "  ws_after = evalin('base', 'who'); "
        "  fwrite(fid, unicode2native(['ws_after_helper:' char(10) strjoin(ws_after, ', ') char(10) char(10)], 'UTF-8')); "
        "  if ~status.success; "
        "    fwrite(fid, unicode2native(['helper status.error native=' status.error char(10) char(10)], 'UTF-8')); "
        # The helper swallowed ME with [' ' ME.message] which lossy-converts.
        # Re-run sim() OURSELVES under the same workspace state to capture
        # getReport(extended) directly.
        "    fwrite(fid, unicode2native(['---- replaying sim() with same workspace ----' char(10)], 'UTF-8')); "
        "    try; "
        "      set_param('kundur_cvs_v3', 'StopTime', '10.0'); "
        "      simOut2 = sim('kundur_cvs_v3'); "
        "      fwrite(fid, unicode2native(['replay SUCCESS' char(10)], 'UTF-8')); "
        "    catch ME2; "
        "      rep = getReport(ME2, 'extended', 'hyperlinks', 'off'); "
        "      fwrite(fid, unicode2native(rep, 'UTF-8')); "
        "    end; "
        "  end; "
        "catch ME; "
        "  rep = getReport(ME, 'extended', 'hyperlinks', 'off'); "
        "  fwrite(fid, unicode2native(['---- helper itself raised ----' char(10) rep char(10)], 'UTF-8')); "
        "end; "
        "fclose(fid);",
        nargout=0,
    )
    print(f"DIAG4: report written: {out_path}")

    text = out_path.read_text(encoding="utf-8", errors="replace")
    # Avoid printing direct Chinese bullets via cp936 stdout — write a copy
    # to ASCII-safe stderr and flag if any present.
    print("DIAG4: report length:", len(text))
    eng.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
