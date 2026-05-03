# FACT: this is the orchestrator contract; runtime behaviour defines what
# the probe is. Anything in NOTES/README about it is CLAIM until verified
# against this file.
"""Probe orchestrator — runs phases and accumulates ``state_snapshot``.

Plan: ``quality_reports/plans/2026-04-30_probe_state_kundur_cvs.md``.
Phase A only — Phases B/C/D deferred (see plan §4).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from probes.kundur.probe_state import (
    _causality,
    _discover,
    _dynamics,
    _nr_ic,
    _report,
    _trained_policy,
    _verdict,
)
from probes.kundur.probe_state.probe_config import IMPLEMENTATION_VERSION

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "results/harness/kundur/probe_state"

SCHEMA_VERSION = 1


@dataclass
class ModelStateProbe:
    """Owns the state_snapshot dict and orchestrates phases."""

    output_dir: Path | None = None
    dispatch_magnitude: float = 0.5
    sim_duration: float = 5.0
    # Probe-context override for the env's bridge.warmup duration. None =
    # use scenarios.kundur.config_simulink.T_WARMUP (production default,
    # 10 s for r_f reward-shaping settle). Probe smoke / Phase 4 sweep do
    # not consume r_f, so a shorter warmup is acceptable as long as the
    # post-warmup omega std stays inside G5 threshold (verified by Phase 3
    # itself). Z 2026-05-03.
    t_warmup_s: float | None = None
    # FastRestart opt-in override. None = use BridgeConfig default (False).
    # Validated for v3 Discrete only (microtest 2026-05-03, physics rel err
    # 2.46e-08). Not safe for v3 Phasor or production training without
    # separate validation.
    fast_restart: bool | None = None
    # Phase B (trained-policy ablation) config; ignored unless phase 5 runs.
    phase_b_mode: str = "smoke"  # 'smoke' | 'full'
    phase_b_checkpoint: str | None = None  # CLI override; None → auto-search
    phase_b_n_scenarios: int = 5  # smoke-mode scenario count
    # Phase C (causality short-train) config; ignored unless phase 6 runs.
    phase_c_mode: str = "smoke"  # 'smoke' (10 ep) | 'full' (200 ep)
    phase_c_eval_n_scenarios: int = 5
    phase_c_train_timeout_s: int = 86400  # 24 hr per short-train ceiling
    # Module α — P2 parallelization (workers=1 default = serial, no-op).
    workers: int = 1
    # dispatch_subset: raw CLI spec string (parsed at Phase 4 time against live
    # targets list) OR pre-parsed canonical name tuple; None = run all.
    dispatch_subset: "str | tuple[str, ...] | None" = None
    snapshot: dict[str, Any] = field(default_factory=dict)

    ALL_PHASES = (1, 2, 3, 4, 5, 6)

    def __post_init__(self) -> None:
        if self.output_dir is None:
            self.output_dir = DEFAULT_OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot.update(
            {
                "schema_version": SCHEMA_VERSION,
                "implementation_version": IMPLEMENTATION_VERSION,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S"),
                "git_head": _git_head(),
                "config": {
                    "dispatch_magnitude_sys_pu": float(self.dispatch_magnitude),
                    "sim_duration_s": float(self.sim_duration),
                    "t_warmup_s_override": (
                        float(self.t_warmup_s)
                        if self.t_warmup_s is not None
                        else None
                    ),
                    "fast_restart_override": (
                        bool(self.fast_restart)
                        if self.fast_restart is not None
                        else None
                    ),
                    "workers": int(self.workers),
                    "dispatch_subset": (
                        list(self.dispatch_subset)
                        if isinstance(self.dispatch_subset, tuple)
                        else self.dispatch_subset  # str or None
                    ),
                },
                "errors": [],
            }
        )

    def run(self, phases: tuple[int, ...] | None = None) -> dict[str, Any]:
        phases = phases if phases is not None else self.ALL_PHASES
        wall_t0 = time.perf_counter()
        logger.info("Probe starting; phases=%s", phases)

        # Module α — S7: mode banner.
        if self.workers > 1:
            logger.info("running in parallel mode, N=%d", self.workers)
        else:
            logger.info("running in serial mode")

        # Module β — build idempotency: ensure .slx is up-to-date before
        # workers fork so they never race on rebuild.  Serial mode (workers=1)
        # is unchanged — _ensure_build_current is never called.
        if self.workers > 1:
            self._ensure_build_current()

        # Module γ — parallel branch when workers > 1.
        if self.workers > 1:
            if any(p in (5, 6) for p in phases):
                raise SystemExit(
                    "--workers > 1 incompatible with --phase 5/6 "
                    "(out of P2 scope; see spec §2.2)"
                )
            # Phase 1 runs in parent — cheap, deterministic, provides
            # dispatch_effective list needed for slicing.
            if 1 in phases:
                self._run_phase("phase1_topology", _discover.run, self)
            # Phases 2/3/4 delegated to workers (worker 0 handles 2+3+4;
            # others handle 4 only). Module δ merges snapshots centrally.
            return self._run_parallel(phases, wall_t0)

        # --- Serial path (M1: unchanged from pre-γ) ---
        if 1 in phases:
            self._run_phase("phase1_topology", _discover.run, self)
        if 2 in phases:
            self._run_phase("phase2_nr_ic", _nr_ic.run, self)
        if 3 in phases:
            self._run_phase("phase3_open_loop", _dynamics.run_open_loop, self)
        if 4 in phases:
            self._run_phase("phase4_per_dispatch", _dynamics.run_per_dispatch, self)
        if 5 in phases:
            self._run_phase(
                "phase5_trained_policy",
                _trained_policy.run_trained_policy_ablation,
                self,
            )
        if 6 in phases:
            self._run_phase(
                "phase6_causality",
                _causality.run_causality_short_train,
                self,
            )

        # Verdict + report always run; pure computation/IO.
        self._run_phase(
            "falsification_gates",
            lambda probe: _verdict.compute_gates(probe.snapshot),
            self,
        )

        out = _report.write(self.snapshot, self.output_dir)
        wall_elapsed = time.perf_counter() - wall_t0
        logger.info(
            "Probe done in %.1fs; JSON=%s; MD=%s",
            wall_elapsed,
            out["json"],
            out["md"],
        )
        return self.snapshot

    # ------------------------------------------------------------------
    def _run_phase(self, key: str, fn, *args, **kwargs) -> None:
        """Run a phase function and store its result under ``key``.

        Failures are caught; the phase result becomes ``{"error": str(exc)}``
        so other phases continue. Plan §3 fail-soft principle.
        """
        t0 = time.perf_counter()
        logger.info("Phase '%s' starting", key)
        try:
            result = fn(*args, **kwargs)
            self.snapshot[key] = result
            logger.info(
                "Phase '%s' done in %.1fs",
                key,
                time.perf_counter() - t0,
            )
        except Exception as exc:  # noqa: BLE001 — fail-soft per plan §3
            msg = f"{type(exc).__name__}: {exc}"
            logger.warning("Phase '%s' FAILED: %s", key, msg)
            self.snapshot[key] = {"error": msg}
            self.snapshot["errors"].append({"phase": key, "error": msg})


    # ------------------------------------------------------------------
    def _run_parallel(
        self,
        phases: tuple[int, ...],
        wall_t0: float,
    ) -> dict[str, Any]:
        """Module γ/δ — parallel dispatch: spawn N workers, wait, merge.

        Worker 0 receives ``--phase 2,3,4``; workers 1..N-1 receive
        ``--phase 4``. All workers receive ``--workers 1`` (no recursion)
        and ``--dispatch-subset <slice>``.

        Module δ (_merge.merge_snapshots) combines per-worker snapshots into
        the canonical merged snapshot; verdict is recomputed centrally after.

        Parameters
        ----------
        phases:
            Requested phases tuple (already validated: no 5/6; phase 1
            already ran in parent if present).
        wall_t0:
            ``time.perf_counter()`` timestamp from ``run()`` start.

        Returns
        -------
        dict
            Updated ``self.snapshot``.
        """
        from probes.kundur.probe_state._orchestrator import (  # noqa: PLC0415
            slice_targets,
            spawn_worker,
            wait_for_all,
        )
        from probes.kundur.probe_state._dynamics import (  # noqa: PLC0415
            _apply_dispatch_subset,
        )
        from scenarios.kundur.config_simulink import (  # noqa: PLC0415
            KUNDUR_DISTURBANCE_TYPES_VALID,
        )

        # --- Resolve targets from Phase 1 result (already in snapshot). ---
        phase1 = self.snapshot.get("phase1_topology", {}) or {}
        effective_from_phase1 = phase1.get("dispatch_effective", []) or []
        targets_all = [
            d for d in effective_from_phase1
            if d in KUNDUR_DISTURBANCE_TYPES_VALID
        ]

        # Apply dispatch_subset filter (same logic as serial _dynamics path).
        subset_spec = getattr(self, "dispatch_subset", None)
        targets, subset_applied = _apply_dispatch_subset(targets_all, subset_spec)

        if not targets:
            logger.warning(
                "parallel mode: no targets after subset filter — "
                "falling through to empty phase4_per_dispatch"
            )
            self.snapshot["phase4_per_dispatch"] = {
                "dispatches": {},
                "warning": "no effective dispatches after subset filter",
                "subset_applied": (
                    list(subset_applied) if subset_applied is not None else None
                ),
            }
            self._run_phase(
                "falsification_gates",
                lambda probe: _verdict.compute_gates(probe.snapshot),
                self,
            )
            out = _report.write(self.snapshot, self.output_dir)
            logger.info(
                "Probe done in %.1fs (parallel, empty targets); JSON=%s; MD=%s",
                time.perf_counter() - wall_t0, out["json"], out["md"],
            )
            return self.snapshot

        # --- Slice targets across workers (round-robin, S5). ---
        slices: list[list[str]] = slice_targets(targets, self.workers)

        # Collect non-empty slices; do NOT spawn workers with empty subset.
        non_empty_slices = [
            (idx, sl) for idx, sl in enumerate(slices) if sl
        ]
        n_active = len(non_empty_slices)
        logger.info(
            "parallel mode: %d targets → %d worker(s) active (of %d requested)",
            len(targets), n_active, self.workers,
        )

        # --- Build base_args dict from self. ---
        base_args: dict[str, Any] = {}
        if self.sim_duration is not None:
            base_args["sim_duration"] = self.sim_duration
        if self.dispatch_magnitude is not None:
            base_args["dispatch_mag"] = self.dispatch_magnitude
        if self.t_warmup_s is not None:
            base_args["t_warmup_s"] = self.t_warmup_s
        if self.fast_restart is not None:
            base_args["fast_restart"] = self.fast_restart

        # --- Spawn workers. ---
        spawned: list[tuple[int, subprocess.Popen, Any]] = []
        worker_dirs: list[Path] = []

        for idx, sl in non_empty_slices:
            worker_dir = self.output_dir / f"p2_worker_{idx}"
            # R_P6 mitigation: wipe stale dir before each run.
            shutil.rmtree(worker_dir, ignore_errors=True)
            worker_dir.mkdir(parents=True, exist_ok=True)
            worker_dirs.append(worker_dir)

            log_path = worker_dir / "probe.log"
            proc, log_handle = spawn_worker(
                worker_idx=idx,
                subset=sl,
                worker_dir=worker_dir,
                base_args=base_args,
                log_path=log_path,
            )
            spawned.append((idx, proc, log_handle))

        # --- Wait for all workers (4-hour defensive timeout). ---
        timeout_s = 4 * 3600.0
        exit_results = wait_for_all(spawned, timeout_s=timeout_s)

        # --- Harvest exit codes; surface failures. ---
        non_zero = [(i, ec, w) for i, ec, w in exit_results if ec != 0]
        if non_zero:
            for i, ec, w in non_zero:
                msg = f"worker_{i} exited with code {ec} (wall={w:.1f}s)"
                logger.error("parallel mode: %s", msg)
                self.snapshot["errors"].append(
                    {"phase": "phase4_per_dispatch_parallel", "error": msg}
                )

        # --- Log per-worker timings. ---
        total_wall = time.perf_counter() - wall_t0
        for i, ec, w in exit_results:
            logger.info(
                "worker_%d: wall=%.1fs exit_code=%d", i, w, ec
            )
        logger.info("parallel orchestration total wall=%.1fs", total_wall)

        # --- Module δ: merge worker snapshots into canonical snapshot. ---
        from probes.kundur.probe_state import _merge  # noqa: PLC0415

        # Build per-worker metadata list (in non_empty_slices order).
        exit_by_idx = {i: (ec, w) for i, ec, w in exit_results}
        worker_meta_list: list[dict] = []
        worker_snapshots: list[dict] = []

        for idx, sl in non_empty_slices:
            worker_dir = self.output_dir / f"p2_worker_{idx}"
            ec, wall = exit_by_idx.get(idx, (1, 0.0))
            meta_entry = {
                "idx": idx,
                "exit_code": ec,
                "wall_s": wall,
                "subset": sl,
                "worker_dir": str(worker_dir),
            }
            worker_meta_list.append(meta_entry)

            # Attempt to load snapshot; skip gracefully if missing (crash).
            try:
                ws = _merge.load_worker_snapshot(worker_dir)
                worker_snapshots.append(ws)
            except _merge.MergeError as exc:
                logger.error("Module δ: %s", exc)
                self.snapshot["errors"].append(
                    {"phase": "phase4_per_dispatch_merge", "error": str(exc)}
                )
                # Insert a minimal placeholder so indices align with meta list.
                worker_snapshots.append({
                    "phase4_per_dispatch": {"dispatches": {}},
                    "errors": [{"phase": "worker_load", "error": str(exc)}],
                })

        non_empty_slice_lists = [sl for _, sl in non_empty_slices]

        try:
            merged = _merge.merge_snapshots(
                self.snapshot,
                worker_snapshots,
                worker_meta_list,
                expected_dispatches_per_worker=non_empty_slice_lists,
            )
            self.snapshot = merged
        except _merge.MergeError as exc:
            logger.error("Module δ merge failed: %s", exc)
            self.snapshot["errors"].append(
                {"phase": "phase4_per_dispatch_merge", "error": str(exc)}
            )
            # Fallback: empty dispatches so verdict/report can still run.
            self.snapshot["phase4_per_dispatch"] = {
                "probe_default_magnitude_sys_pu": float(self.dispatch_magnitude),
                "probe_default_sim_duration_s": float(self.sim_duration),
                "dispatches": {},
                "merge_error": str(exc),
            }

        # Verdict + report on merged snapshot (M9: centrally recomputed).
        self._run_phase(
            "falsification_gates",
            lambda probe: _verdict.compute_gates(probe.snapshot),
            self,
        )
        out = _report.write(self.snapshot, self.output_dir)
        logger.info(
            "Probe done in %.1fs (parallel, merged); JSON=%s; MD=%s",
            total_wall, out["json"], out["md"],
        )
        return self.snapshot

    # ------------------------------------------------------------------
    def _ensure_build_current(self) -> None:
        """Rebuild kundur_cvs_v3_discrete.slx in the main process if stale.

        Called only when self.workers > 1, before worker processes are forked,
        so that parallel MATLAB engines never race on a rebuild.

        Raises on MATLAB build failure — better to halt than fork workers
        against a corrupt or stale model.
        """
        from probes.kundur.probe_state._build_check import (  # noqa: PLC0415
            discrete_build_dependencies,
            is_build_current,
        )

        repo_root = Path(__file__).resolve().parents[3]
        sim_models = repo_root / "scenarios" / "kundur" / "simulink_models"
        slx_path = sim_models / "kundur_cvs_v3_discrete.slx"
        deps = discrete_build_dependencies(repo_root)

        # Log mtimes for observability.
        slx_mtime = slx_path.stat().st_mtime if slx_path.exists() else None
        logger.info("build check: slx=%s mtime=%s", slx_path, slx_mtime)
        for d in deps:
            logger.info(
                "build check: dep=%s mtime=%s",
                d,
                d.stat().st_mtime if d.exists() else "MISSING",
            )

        if is_build_current(slx_path, deps):
            logger.info("build current, skipping rebuild")
            return

        logger.warning("build stale, rebuilding via main-process MATLAB session")
        from engine.matlab_session import MatlabSession  # noqa: PLC0415

        session = MatlabSession.get("default")
        session.eval(f"addpath('{sim_models}')", nargout=0)
        session.eval("build_kundur_cvs_v3_discrete()", nargout=0)

        # Confirm the .slx exists post-build.
        if not slx_path.exists():
            raise RuntimeError(
                f"build_kundur_cvs_v3_discrete() completed but {slx_path} "
                "still does not exist — aborting before worker fork."
            )
        logger.info("rebuild done: slx mtime=%s", slx_path.stat().st_mtime)


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"
