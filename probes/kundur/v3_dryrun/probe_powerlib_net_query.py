"""probe_powerlib_net_query — live integration test for Phase D.1 tool.

Loads kundur_cvs_v3.slx, queries the Bus 7 anchor, asserts that all
expected members of the Bus 7 electrical net appear (Load7, Shunt7,
LoadStep7, line endpoints, line shunts).

Run via:
  simulink_run_script_async("...this script's content as MATLAB-compatible..."),
or invoke from a controller agent that has live MCP MATLAB engine access:
  python probes/kundur/v3_dryrun/probe_powerlib_net_query.py

Skips automatically if the MATLAB engine is unreachable (e.g. training
holding all licenses).

Plan §3.D.1 P8/P9.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root on sys.path
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# Expected members of the Bus 7 net per build_kundur_cvs_v3.m + topology spec.
# All blocks should appear (the order may differ; only set membership matters).
EXPECTED_BUS7_MEMBERS = {
    "Load7", "Shunt7", "LoadStep7",
    "L_6_7a", "L_6_7b",        # lines into bus 7 from bus 6
    "L_7_8a", "L_7_8b",        # lines out of bus 7 to bus 8
    "L_7_12",                   # branch to bus 12 (ESS connection)
}


def main() -> int:
    try:
        from engine.mcp_simulink_tools import (
            simulink_load_model,
            simulink_powerlib_net_query,
        )
    except ImportError as exc:
        print(f"SKIP: import failed: {exc}")
        return 0

    model_path = _ROOT / "scenarios" / "kundur" / "simulink_models" / "kundur_cvs_v3.slx"
    if not model_path.exists():
        print(f"SKIP: model file not found: {model_path}")
        return 0

    print(f"Loading {model_path.name} ...")
    try:
        simulink_load_model(str(model_path))
    except Exception as exc:  # noqa: BLE001
        print(f"SKIP: load_model failed (likely MATLAB engine busy): {exc}")
        return 0

    # Query Bus 7 anchor — line L_6_7a's RConn1 is one canonical entry point
    print("Querying Bus 7 anchor: kundur_cvs_v3/L_6_7a/RConn1 ...")
    try:
        result = simulink_powerlib_net_query(
            "kundur_cvs_v3",
            "kundur_cvs_v3/L_6_7a",
            "RConn1",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: net_query call raised: {exc}")
        return 2

    print(f"  supported: {result['supported']}")
    print(f"  reason:    {result.get('reason', '')!r}")
    print(f"  net_id:    {result['net_id']}")
    print(f"  members ({len(result['members'])}):")
    for m in result["members"]:
        print(f"    - {m['block']} :: {m['port']}")

    if not result["supported"]:
        print(f"FAIL: helper reported unsupported (reason: {result['reason']})")
        return 2

    # Extract block leaf names (last path component)
    member_leaves = {Path(m["block"]).name for m in result["members"]}

    missing = EXPECTED_BUS7_MEMBERS - member_leaves
    extra = member_leaves - EXPECTED_BUS7_MEMBERS - {"L_6_7a"}  # anchor itself OK
    if missing:
        print(f"FAIL: missing expected members: {sorted(missing)}")
        return 2
    if extra:
        # Extra is informational, not a failure — bus may have ESS or wind plant
        print(f"  (info) additional members beyond expected set: {sorted(extra)}")

    print("PASS: Bus 7 anchor returns all expected members.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
