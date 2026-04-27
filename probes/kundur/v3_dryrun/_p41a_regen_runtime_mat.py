"""P4.1a — regenerate kundur_cvs_v3_runtime.mat with the WindAmp_<w> fix.

Calls build_kundur_cvs_v3() in a cold-start matlab.engine so the runtime.mat
sidecar gets re-emitted with the new runtime_consts wind block (WindAmp_<w>
included). The build is deterministic given the same IC / parameters, so the
re-emitted .slx is topologically identical to the prior commit (same blocks,
same positions, same parameters) — only the .mat sidecar gains 2 fields.

Verification:
  - print runtime.mat field count + WindAmp_<w> presence
  - print SHA256 of .slx before / after to document binary change scope
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


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

    print(f"P41A: pre-regen slx_sha256  = {_sha(slx_path)}")
    print(f"P41A: pre-regen mat_sha256  = {_sha(mat_path)}")

    print("P41A: starting matlab engine ...")
    eng = me.start_matlab()
    eng.addpath(str(REPO_ROOT / "slx_helpers"), nargout=0)
    eng.addpath(str(REPO_ROOT / "slx_helpers" / "vsg_bridge"), nargout=0)
    eng.cd(str(out_dir), nargout=0)
    print("P41A: engine ready, invoking build_kundur_cvs_v3() ...")

    # Build prints RESULT lines via fprintf -> capture into StringIO so the
    # log lands in stderr/stdout files of this Python process.
    import io
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    eng.eval("build_kundur_cvs_v3();", nargout=0, stdout=out_buf, stderr=err_buf)
    print("P41A: ----- build stdout -----")
    print(out_buf.getvalue())
    print("P41A: ----- build stderr -----")
    print(err_buf.getvalue())

    # Verify mat
    print("P41A: verifying runtime.mat contents ...")
    fields = eng.eval(f"fieldnames(load('{str(mat_path).replace(chr(92), '/')}'))", nargout=1)
    field_list = [str(f) for f in fields]
    print(f"P41A: runtime.mat field count = {len(field_list)}")
    has_w1 = "WindAmp_1" in field_list
    has_w2 = "WindAmp_2" in field_list
    print(f"P41A: WindAmp_1 in mat = {has_w1}")
    print(f"P41A: WindAmp_2 in mat = {has_w2}")
    val_w1 = eng.eval(
        f"getfield(load('{str(mat_path).replace(chr(92), '/')}'), 'WindAmp_1')",
        nargout=1,
    )
    val_w2 = eng.eval(
        f"getfield(load('{str(mat_path).replace(chr(92), '/')}'), 'WindAmp_2')",
        nargout=1,
    )
    print(f"P41A: WindAmp_1 value = {val_w1}")
    print(f"P41A: WindAmp_2 value = {val_w2}")

    eng.quit()

    print(f"P41A: post-regen slx_sha256 = {_sha(slx_path)}")
    print(f"P41A: post-regen mat_sha256 = {_sha(mat_path)}")

    if has_w1 and has_w2 and float(val_w1) == 1.0 and float(val_w2) == 1.0:
        print("P41A: regen OK")
        return 0
    print("P41A: regen FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
