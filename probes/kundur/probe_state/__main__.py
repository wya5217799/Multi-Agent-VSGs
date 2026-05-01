# FACT: CLI behaviour is what this script does at runtime; --help is the
# only normative description. CLAIM = anything in README.md describing it.
"""CLI entry-point for ``python -m probes.kundur.probe_state``.

Usage examples::

    PY=".../andes_env/python.exe"
    $PY -m probes.kundur.probe_state                  # all phases
    $PY -m probes.kundur.probe_state --phase 1        # static only
    $PY -m probes.kundur.probe_state --phase 2,7      # NR/IC + report only
    $PY -m probes.kundur.probe_state --no-mcp         # phases 1-4 skipped

Phase indices map to plan §5 step list (Phase 1 = static discovery, ...).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from probes.kundur.probe_state.probe_state import ModelStateProbe


def _parse_phases(arg: str) -> tuple[int, ...]:
    """Parse a phase spec like ``"1,2,4"`` or ``"all"``."""
    if arg.strip().lower() in ("all", ""):
        return ModelStateProbe.ALL_PHASES
    raw = [p.strip() for p in arg.split(",") if p.strip()]
    try:
        phases = tuple(int(p) for p in raw)
    except ValueError as exc:
        raise SystemExit(f"--phase expects integers or 'all', got {arg!r}") from exc
    bad = [p for p in phases if p not in ModelStateProbe.ALL_PHASES]
    if bad:
        raise SystemExit(
            f"--phase contains invalid indices {bad}; "
            f"valid: {ModelStateProbe.ALL_PHASES}"
        )
    return phases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="probes.kundur.probe_state",
        description=(
            "Dump kundur_cvs runtime state (topology + NR/IC + open-loop "
            "+ per-dispatch + G1-G5 verdict) to JSON + Markdown."
        ),
    )
    parser.add_argument(
        "--phase",
        default="all",
        help="comma-separated data phases (1-6) or 'all'. "
             "1=static, 2=NR/IC, 3=open-loop, 4=per-dispatch, "
             "5=trained-policy ablation (Phase B), "
             "6=causality short-train (Phase C). "
             "Verdict (G1-G6) and report (JSON+MD) always run after data phases.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="override default output dir (results/harness/kundur/probe_state/)",
    )
    parser.add_argument(
        "--no-mcp",
        action="store_true",
        help="skip phases that need MATLAB engine (1, 3, 4, 5, 6); keeps 2 + verdict + report",
    )
    parser.add_argument(
        "--phase-b-mode",
        choices=["smoke", "full"],
        default="smoke",
        help="Phase 5 scope: smoke = 5 inline scenarios (~20min); "
             "full = 50 manifest scenarios (~3hr).",
    )
    parser.add_argument(
        "--checkpoint",
        default=None,
        help="Phase 5 SAC ckpt override (CLI > KUNDUR_PROBE_CHECKPOINT > auto-search).",
    )
    parser.add_argument(
        "--phase-b-n-scenarios",
        type=int,
        default=5,
        help="Phase 5 smoke-mode scenario count (full mode uses manifest length).",
    )
    parser.add_argument(
        "--phase-c-mode",
        choices=["smoke", "full"],
        default="smoke",
        help="Phase 6 scope: smoke = 10 ep short-train (~30-60min wall, "
             "plumbing test only); full = 200 ep (~10-50hr wall, real R1 signal).",
    )
    parser.add_argument(
        "--phase-c-eval-n-scenarios",
        type=int,
        default=5,
        help="Phase 6 paper_eval scenario count for the no_rf checkpoint.",
    )
    parser.add_argument(
        "--phase-c-train-timeout-s",
        type=int,
        default=86400,
        help="Phase 6 per short-train wall ceiling (default 24 hr).",
    )
    parser.add_argument(
        "--dispatch-mag",
        type=float,
        default=0.5,
        help="absolute disturbance magnitude (sys-pu) for Phase 4 scan",
    )
    parser.add_argument(
        "--sim-duration",
        type=float,
        default=5.0,
        help="seconds of post-warmup sim per Phase 3/4 run",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="DEBUG-level logging",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    phases = _parse_phases(args.phase)
    if args.no_mcp:
        # Drop MATLAB-bound phases. Phases 5 and 6 launch paper_eval / train
        # subprocesses that themselves need MATLAB, so they're dropped too.
        phases = tuple(p for p in phases if p not in (1, 3, 4, 5, 6))

    probe = ModelStateProbe(
        output_dir=Path(args.output_dir) if args.output_dir else None,
        dispatch_magnitude=args.dispatch_mag,
        sim_duration=args.sim_duration,
        phase_b_mode=args.phase_b_mode,
        phase_b_checkpoint=args.checkpoint,
        phase_b_n_scenarios=args.phase_b_n_scenarios,
        phase_c_mode=args.phase_c_mode,
        phase_c_eval_n_scenarios=args.phase_c_eval_n_scenarios,
        phase_c_train_timeout_s=args.phase_c_train_timeout_s,
    )
    probe.run(phases=phases)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
