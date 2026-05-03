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

from engine.path_guard import assert_active_worktree
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
        "--t-warmup-s",
        type=float,
        default=None,
        help="override env warmup duration (s) for probe contexts. "
             "None = use scenarios.kundur.config_simulink.T_WARMUP "
             "(production default, locked at 10 s for r_f reward "
             "settle). Probe / smoke runs may use shorter (e.g. 5 s) "
             "since they don't consume r_f; Phase 3 G5 verdict acts as "
             "the post-warmup std sanity check.",
    )
    parser.add_argument(
        "--fast-restart",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable Simulink FastRestart for probe context (opt-in; "
             "default = use BridgeConfig default = False). Validated only "
             "for v3 Discrete (probe microtest 2026-05-03, physics rel err "
             "2.46e-08). Not safe for v3 Phasor or production training "
             "without separate validation. Use --no-fast-restart to force off.",
    )
    # Module α — P2 parallelization flags.
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="Number of parallel worker processes for Phase 4 dispatch sweep "
             "(default=1, serial). N>=2 is Module γ (not yet implemented); "
             "with this module α, N>=2 is parsed and validated but does not "
             "yet spawn subprocesses.  Rejected for --phase 5/6 (out of P2 "
             "scope).",
    )
    parser.add_argument(
        "--dispatch-subset",
        default=None,
        metavar="SPEC",
        help="Comma-separated subset of Phase 4 dispatches to run.  Each "
             "token is either an integer index into the effective-dispatch "
             "list (0-based) or a dispatch name.  Mixed allowed, e.g. "
             "'0,3,pm_step_proxy_random_gen'.  None (default) = run all.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="DEBUG-level logging",
    )
    parser.add_argument(
        "--diff",
        nargs=2,
        metavar=("PREV", "CURR"),
        default=None,
        help="Field-level diff between two state_snapshot_*.json files. "
             "Short-circuits all phases; exits 0 if identical, 1 otherwise. "
             "Aliases (G3): 'baseline' → baseline.json; 'latest' → "
             "state_snapshot_latest.json. Design §5.6 (F2).",
    )
    parser.add_argument(
        "--gate-eval",
        nargs=2,
        metavar=("PREV", "CURR"),
        default=None,
        help="Structured gate evaluation between two state_snapshot_*.json files. "
             "Computes GATE-PHYS, GATE-G15, GATE-WALL verdicts and writes JSON to "
             "stdout. Exit code: 0 if overall_verdict==PASS, 1 if FAIL. "
             "Short-circuits all phases. P0-3 (2026-05-04).",
    )
    parser.add_argument(
        "--gate-eval-tol",
        type=float,
        default=1e-9,
        metavar="FLOAT",
        help="GATE-PHYS absolute tolerance (default 1e-9, immutable P2 contract). "
             "Override only in exploratory / diagnostic contexts.",
    )
    parser.add_argument(
        "--promote-baseline",
        default=None,
        metavar="SNAPSHOT",
        help="Copy SNAPSHOT to baseline.json under --output-dir (G3). "
             "Use after a green run to rebase the diff baseline. "
             "Short-circuits all phases.",
    )
    args = parser.parse_args(argv)

    # Fail-fast if launched from the wrong worktree (Python-side analog of the
    # MATLAB assert in build_kundur_cvs_v3_discrete.m:61-79).  Placed after
    # parse_args so --help still works without triggering the guard.
    assert_active_worktree()

    # Resolve snapshot dir once (used by both --diff aliases and --promote-baseline).
    from probes.kundur.probe_state.probe_state import DEFAULT_OUTPUT_DIR
    snapshot_dir = (
        Path(args.output_dir).resolve() if args.output_dir
        else DEFAULT_OUTPUT_DIR
    )

    # G3 short-circuit: --promote-baseline <path>
    if args.promote_baseline:
        from probes.kundur.probe_state._diff import promote_baseline
        result = promote_baseline(Path(args.promote_baseline), snapshot_dir)
        print(f"src:    {result['src']}")
        print(f"dst:    {result['dst']}")
        if result["backup"]:
            print(f"backup: {result['backup']}  (previous baseline preserved)")
        print(f"new baseline verdicts: {result['verdict_summary']}")
        return 0

    # F2/G3 short-circuit: --diff PREV CURR (with alias support).
    if args.diff:
        from probes.kundur.probe_state._diff import diff_snapshots, resolve_alias
        prev = resolve_alias(args.diff[0], snapshot_dir)
        curr = resolve_alias(args.diff[1], snapshot_dir)
        return diff_snapshots(prev, curr)

    # P0-3 short-circuit: --gate-eval PREV CURR
    if args.gate_eval:
        import json as _json
        from probes.kundur.probe_state._gate_eval import evaluate_gates
        from probes.kundur.probe_state._diff import resolve_alias
        prev = resolve_alias(args.gate_eval[0], snapshot_dir)
        curr = resolve_alias(args.gate_eval[1], snapshot_dir)
        result = evaluate_gates(prev, curr, phys_tol=args.gate_eval_tol)
        print(_json.dumps(result, indent=2))
        return 0 if result["overall_verdict"] == "PASS" else 1

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

    # Module α: validate --workers.
    if args.workers < 1:
        raise SystemExit("--workers must be >= 1")
    if args.workers > 1 and any(p in (5, 6) for p in phases):
        raise SystemExit(
            "--workers > 1 is incompatible with --phase 5/6 (out of P2 scope)"
        )

    # Module α: parse --dispatch-subset.  Deferred to probe.run() time when
    # the effective dispatch list is known; store raw spec here.  The actual
    # _parse_subset_spec call happens once Phase 1 targets are available.
    # For CLI-level validation we do a best-effort check if SPEC tokens look
    # purely numeric — full name-validation requires Phase 1 data.
    dispatch_subset_parsed: tuple[str, ...] | None = None
    if args.dispatch_subset is not None:
        # We cannot resolve names yet (need Phase 1 dispatch_effective list),
        # so store as a sentinel string that _dynamics will parse at runtime.
        # The _apply_dispatch_subset helper in _dynamics calls _parse_subset_spec
        # with the live targets list.  Pass through as a string sentinel here.
        dispatch_subset_parsed = args.dispatch_subset  # type: ignore[assignment]

    probe = ModelStateProbe(
        output_dir=Path(args.output_dir) if args.output_dir else None,
        dispatch_magnitude=args.dispatch_mag,
        sim_duration=args.sim_duration,
        t_warmup_s=args.t_warmup_s,
        fast_restart=args.fast_restart,
        phase_b_mode=args.phase_b_mode,
        phase_b_checkpoint=args.checkpoint,
        phase_b_n_scenarios=args.phase_b_n_scenarios,
        phase_c_mode=args.phase_c_mode,
        phase_c_eval_n_scenarios=args.phase_c_eval_n_scenarios,
        phase_c_train_timeout_s=args.phase_c_train_timeout_s,
        workers=args.workers,
        dispatch_subset=dispatch_subset_parsed,
    )
    probe.run(phases=phases)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
