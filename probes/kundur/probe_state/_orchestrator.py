"""Module γ — subprocess pool orchestrator helpers (pure logic).

Spawned worker subprocess invokes::

    python -m probes.kundur.probe_state --phase <p> --workers 1
        --dispatch-subset <slice> --output-dir <wd>

inheriting other CLI args (--fast-restart, --t-warmup-s, --sim-duration,
--dispatch-mag, --output-dir replacement). Each worker owns a private
matlab.engine. The orchestrator collects exit codes; merge module δ
combines per-worker snapshots.

Pure stdlib + logging; no MATLAB import. Importable for unit testing.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)


def slice_targets(
    targets: Sequence[str],
    n_workers: int,
    strategy: str = "round_robin",
) -> list[list[str]]:
    """Split *targets* across *n_workers* slices (per spec §2.3 Decision 4.1).

    Round-robin (S5): worker k receives targets[k::n_workers]. Yields
    near-balanced load when targets have roughly equal cost.

    For N > len(targets), some slices are empty. Caller MAY skip empty
    slices in spawn (no point spawning a worker with nothing to do).

    Parameters
    ----------
    targets:
        Ordered sequence of dispatch name strings.
    n_workers:
        Number of worker slices to produce. Must be >= 1.
    strategy:
        Slicing strategy. Only ``"round_robin"`` is supported.

    Returns
    -------
    list[list[str]]
        Length-n_workers list of sublists; some may be empty.

    Raises
    ------
    ValueError
        If n_workers < 1.
    NotImplementedError
        If strategy is not ``"round_robin"``.
    """
    if n_workers < 1:
        raise ValueError(f"n_workers must be >= 1, got {n_workers}")
    if strategy != "round_robin":
        raise NotImplementedError(f"unsupported slicing strategy: {strategy!r}")
    n_workers = int(n_workers)
    return [list(targets[k::n_workers]) for k in range(n_workers)]


def spawn_worker(
    worker_idx: int,
    subset: list[str],
    worker_dir: Path,
    base_args: dict[str, Any],
    log_path: Path,
) -> tuple[subprocess.Popen, "object"]:
    """Spawn one worker subprocess.

    Worker invocation: ``python -m probes.kundur.probe_state``.

    - Worker 0 also computes phases 2 and 3 (per Decision 4.3 trust-worker-0):
      its ``--phase`` is ``"2,3,4"``. Workers 1..N-1 receive ``--phase "4"``.
    - ``--workers=1`` always (workers do NOT recursively parallelise).

    Parameters
    ----------
    worker_idx:
        Zero-based worker index. Determines which phases are requested.
    subset:
        Non-empty list of dispatch names assigned to this worker.
    worker_dir:
        Per-worker output directory. Must exist before calling.
    base_args:
        Dict with optional keys ``sim_duration``, ``dispatch_mag``,
        ``t_warmup_s``, ``fast_restart`` (all passed through to worker CLI).
    log_path:
        Path where worker stdout+stderr is captured.

    Returns
    -------
    (Popen, log_handle)
        ``log_handle`` must be closed after the process exits so all output
        is flushed to disk.

    Raises
    ------
    ValueError
        If subset is empty (caller's responsibility to skip empty slices).
    """
    if not subset:
        raise ValueError(f"worker {worker_idx} got empty subset; skip earlier")

    # Phase wiring per Decision 4.3 (trust-worker-0): worker 0 runs 1+2+3+4
    # so the merged snapshot picks up phases 2/3 from worker 0's output.
    # Other workers run 1+4 — Phase 1 is REQUIRED even for workers that only
    # do Phase 4, because _dynamics.run_per_dispatch reads
    # probe.snapshot["phase1_topology"]["dispatch_effective"] to resolve the
    # `targets` list against which _parse_subset_spec validates the subset
    # string. Without Phase 1 in-worker, valid_targets=[] and every name in
    # --dispatch-subset gets rejected as unknown (SystemExit).
    # Phase 1 is cheap (~15s, MATLAB cold start dominated) and parallelises
    # across workers, so adds ~15s wall not 60s. E2E 2026-05-03 root-cause fix.
    phases_arg = "1,2,3,4" if worker_idx == 0 else "1,4"

    argv = [
        sys.executable, "-m", "probes.kundur.probe_state",
        "--phase", phases_arg,
        "--workers", "1",
        "--dispatch-subset", ",".join(subset),
        "--output-dir", str(worker_dir),
    ]

    # Pass through user-controllable args from base_args dict (set by caller).
    for k in ("sim_duration", "dispatch_mag", "t_warmup_s", "fast_restart"):
        v = base_args.get(k)
        if v is None:
            continue
        if k == "fast_restart":
            argv.append("--fast-restart" if v else "--no-fast-restart")
        else:
            argv.extend([f"--{k.replace('_', '-')}", str(v)])

    log_handle = log_path.open("w", encoding="utf-8")
    logger.info(
        "worker_%d: spawning; subset=%s log=%s",
        worker_idx, subset, log_path,
    )
    proc = subprocess.Popen(
        argv,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),  # inherit KUNDUR_MODEL_PROFILE etc.
    )
    logger.info("worker_%d: started pid=%d", worker_idx, proc.pid)
    return proc, log_handle


def wait_for_all(
    workers: list[tuple[int, subprocess.Popen, Any]],
    timeout_s: float | None = None,
) -> list[tuple[int, int, float]]:
    """Wait for all workers to exit; return [(idx, exit_code, wall_s), ...].

    On timeout: SIGTERM survivors, then SIGKILL after 30 s; record
    exit_code=-15 (SIGTERM) or -9 (SIGKILL). Caller decides whether to
    abort merge.

    Parameters
    ----------
    workers:
        List of (worker_idx, Popen, log_handle) tuples from ``spawn_worker``.
    timeout_s:
        Optional cumulative timeout across all workers. When elapsed,
        surviving workers are terminated.

    Returns
    -------
    list[(idx, exit_code, wall_s)]
        One entry per input worker. ``wall_s`` is seconds since the call began.
    """
    t0 = time.perf_counter()
    deadline = (t0 + timeout_s) if timeout_s is not None else None
    results: list[tuple[int, int, float]] = []

    for idx, proc, _log_handle in workers:
        remaining = (deadline - time.perf_counter()) if deadline else None
        try:
            ec = proc.wait(timeout=remaining)
            wall = time.perf_counter() - t0
            results.append((idx, ec, wall))
            logger.info(
                "worker_%d: exit_code=%d wall=%.1fs", idx, ec, wall
            )
        except subprocess.TimeoutExpired:
            logger.warning("worker_%d: TIMEOUT, sending SIGTERM", idx)
            proc.terminate()
            try:
                ec = proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                logger.error(
                    "worker_%d: SIGTERM ignored, sending SIGKILL", idx
                )
                proc.kill()
                ec = proc.wait()
            wall = time.perf_counter() - t0
            results.append((idx, ec, wall))

    # Close log handles AFTER wait so they capture all output.
    for _idx, _proc, log_handle in workers:
        try:
            log_handle.close()
        except Exception:  # noqa: BLE001
            pass

    return results
