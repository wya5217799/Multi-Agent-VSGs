"""Agent state probe orchestrator.

Loads a trained DDIC policy (ckpt_dir, ckpt_kind), runs phases A1/A2/A3 with
fail-soft, accumulates snapshot dict, computes A1-A3 verdicts, writes JSON +
Markdown report.

Usage:
    from probes.kundur.agent_state.agent_state import AgentStateProbe
    probe = AgentStateProbe(ckpt_dir="results/andes_phase4_noPHIabs_seed42")
    snapshot = probe.run()  # all phases
    # or: probe.run(phases=("A1", "A2"))
"""
from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from probes.kundur.agent_state import _ablation, _failure, _report, _specialization, _verdict
from probes.kundur.agent_state._loader import load
from probes.kundur.agent_state.probe_config import (
    IMPLEMENTATION_VERSION,
    SCHEMA_VERSION,
    ProbeThresholds,
)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "results" / "harness" / "kundur" / "agent_state"

ALL_PHASES = ("A1", "A2", "A3")


@dataclass
class AgentStateProbe:
    ckpt_dir: str = ""
    ckpt_kind: str = "final"      # 'best' | 'final'
    backend: str = "andes"        # 'andes' | 'simulink'
    output_dir: Path | None = None
    thresholds: ProbeThresholds = field(default_factory=ProbeThresholds)
    snapshot: dict[str, Any] = field(default_factory=dict)
    comm_fail_prob: float | None = None  # None = env default (0.1, matching training)

    def __post_init__(self) -> None:
        if self.output_dir is None:
            self.output_dir = DEFAULT_OUTPUT_DIR
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot.update({
            "schema_version": SCHEMA_VERSION,
            "implementation_version": IMPLEMENTATION_VERSION,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "ckpt_dir": str(self.ckpt_dir),
            "ckpt_kind": str(self.ckpt_kind),
            "backend": str(self.backend),
            "comm_fail_prob": self.comm_fail_prob,
            "errors": [],
        })

    def run(self, phases: tuple[str, ...] | None = None) -> dict:
        phases = phases or ALL_PHASES
        wall_t0 = time.perf_counter()
        logger.info("AgentStateProbe starting; phases=%s backend=%s", phases, self.backend)

        # Load policy once
        try:
            policy = load(self.ckpt_dir, ckpt_kind=self.ckpt_kind, backend=self.backend)
            self.snapshot["n_agents"] = policy.n_agents
            self.snapshot["obs_dim"] = policy.obs_dim
        except Exception as e:
            self.snapshot["errors"].append(f"loader: {e}")
            self.snapshot["falsification_gates"] = _verdict.compute_gates(self.snapshot, self.thresholds)
            return self.snapshot

        # Run phases (fail-soft)
        cfp = self.comm_fail_prob  # capture for lambda closure
        if "A1" in phases:
            self._run_phase("phase_a1_specialization", lambda: _specialization.run(policy, self.thresholds))
        if "A2" in phases:
            self._run_phase("phase_a2_ablation", lambda: _ablation.run(policy, self.thresholds, comm_fail_prob=cfp))
        if "A3" in phases:
            self._run_phase("phase_a3_failure", lambda: _failure.run(policy, self.thresholds, comm_fail_prob=cfp))

        # Verdicts
        self.snapshot["falsification_gates"] = _verdict.compute_gates(self.snapshot, self.thresholds)
        self.snapshot["wall_time_s"] = time.perf_counter() - wall_t0

        return self.snapshot

    def _run_phase(self, key: str, fn) -> None:
        t0 = time.perf_counter()
        try:
            section = fn()
            section["wall_s"] = time.perf_counter() - t0
            self.snapshot[key] = section
            logger.info("Phase %s done in %.1fs", key, time.perf_counter() - t0)
        except Exception as e:
            tb = traceback.format_exc()
            self.snapshot[key] = {"error": str(e), "trace": tb, "wall_s": time.perf_counter() - t0}
            self.snapshot["errors"].append(f"{key}: {e}")
            logger.error("Phase %s FAILED: %s", key, e)

    def write(self, run_id: str | None = None) -> tuple[str, str]:
        return _report.write_snapshot(self.snapshot, str(self.output_dir), run_id)
