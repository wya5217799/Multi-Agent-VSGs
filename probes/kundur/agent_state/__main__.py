"""CLI entry: python -m probes.kundur.agent_state --ckpt-dir <dir> [--phases A1,A2,A3]"""
from __future__ import annotations

import argparse
import logging
import sys

from probes.kundur.agent_state.agent_state import AgentStateProbe, ALL_PHASES


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agent_state", description="Trained DDIC policy diagnostic probe")
    p.add_argument("--ckpt-dir", required=True,
                   help="Directory containing checkpoints (ANDES: agent_*_<kind>.pt; "
                        "Simulink: <kind>.pt bundle)")
    p.add_argument("--ckpt-kind", default="final", choices=["best", "final"])
    p.add_argument("--backend", default="andes", choices=["andes", "simulink"],
                   help="Policy backend: 'andes' (default) or 'simulink'")
    p.add_argument("--phases", default="A1,A2,A3", help="Comma list, e.g., A1 or A1,A3")
    p.add_argument("--output-dir", default=None)
    p.add_argument("--run-id", default=None, help="Tag for output filenames")
    p.add_argument("--comm-fail-prob", type=float, default=None,
                   help="Communication failure probability for ANDES backend A2/A3 rollouts. "
                        "Default: None = env default (COMM_FAIL_PROB=0.1, matching training). "
                        "Set to 0.0 to disable comm failures (legacy behaviour).")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    phases = tuple(p.strip().upper() for p in args.phases.split(",") if p.strip())
    invalid = [p for p in phases if p not in ALL_PHASES]
    if invalid:
        print(f"Invalid phases: {invalid}; choose from {ALL_PHASES}", file=sys.stderr)
        return 2

    probe = AgentStateProbe(
        ckpt_dir=args.ckpt_dir, ckpt_kind=args.ckpt_kind,
        backend=args.backend, output_dir=args.output_dir,
        comm_fail_prob=args.comm_fail_prob,
    )
    snapshot = probe.run(phases=phases)
    json_p, md_p = probe.write(run_id=args.run_id)

    print(f"Wrote: {md_p}")
    print(f"        {json_p}")
    print()
    print("Verdict summary:")
    for gid, g in snapshot.get("falsification_gates", {}).items():
        codes = ", ".join(g.get("reason_codes", []))
        print(f"  {gid}: {g.get('verdict', '?'):<8} [{codes}]")
    if snapshot.get("errors"):
        print()
        print("Errors during run:")
        for e in snapshot["errors"]:
            print(f"  - {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
