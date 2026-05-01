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
    # Phase B (trained-policy ablation) config; ignored unless phase 5 runs.
    phase_b_mode: str = "smoke"  # 'smoke' | 'full'
    phase_b_checkpoint: str | None = None  # CLI override; None → auto-search
    phase_b_n_scenarios: int = 5  # smoke-mode scenario count
    # Phase C (causality short-train) config; ignored unless phase 6 runs.
    phase_c_mode: str = "smoke"  # 'smoke' (10 ep) | 'full' (200 ep)
    phase_c_eval_n_scenarios: int = 5
    phase_c_train_timeout_s: int = 86400  # 24 hr per short-train ceiling
    snapshot: dict[str, Any] = field(default_factory=dict)

    ALL_PHASES = (1, 2, 3, 4, 5, 6)

    def __post_init__(self) -> None:
        if self.output_dir is None:
            self.output_dir = DEFAULT_OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot.update(
            {
                "schema_version": SCHEMA_VERSION,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S"),
                "git_head": _git_head(),
                "config": {
                    "dispatch_magnitude_sys_pu": float(self.dispatch_magnitude),
                    "sim_duration_s": float(self.sim_duration),
                },
                "errors": [],
            }
        )

    def run(self, phases: tuple[int, ...] | None = None) -> dict[str, Any]:
        phases = phases if phases is not None else self.ALL_PHASES
        wall_t0 = time.perf_counter()
        logger.info("Probe starting; phases=%s", phases)

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
