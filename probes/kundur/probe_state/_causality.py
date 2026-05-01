# FACT: this module's runtime output (snapshot.phase6_causality) is the
# contract; comments / README about Phase C fields are CLAIM until verified
# against what the module actually emits.
"""Phase 6 — causality short-train (R1 only).

Plan: ``quality_reports/plans/2026-05-01_probe_state_phase_C.md``.
Prerequisites: ``quality_reports/phase_C_prerequisites.md`` (Step 0 verdict).

R1 hypothesis (plan §3):
- baseline (production φ_f=100 ckpt) and no_rf (φ_f=0 short-train ckpt)
  evaluated under the same paper_eval pipeline.
- ``r_f`` is paper-§IV-C frequency-coordination cost (PHI-unweighted in eval).
- R1 PASS ⇔ ``r_f(no_rf) - r_f(baseline) < -IMPROVE_TOL_R1``
  (no_rf significantly worse ⇒ φ_f penalty is the driver).

Architecture:
- ``_short_train_run_id``: builds ``probe_phase_c_<config>_<TS>`` per plan §5.
- ``_run_short_train``: subprocess wrapper over ``train_simulink.py``;
  KUNDUR_PHI_F (and phi_h / phi_d) ENV-injected.
- ``_eval_ckpt``: reuses Phase B ``_run_paper_eval`` + ``_extract_metrics``.
- ``_compute_r1_verdict``: PASS / REJECT / PENDING from ablation diff.
- ``run_causality_short_train``: orchestrator entry point.

Design rules (plan §2):
- Train script is consumed as black-box CLI (no internal imports).
- Production code untouched (CLI flag was the only train_simulink change).
- PHI control via ENV var only (config_simulink.py:91/114/115 already wired).
- schema_version = 1 stays (additive ``phase6_causality`` field only).
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from probes.kundur.probe_state.probe_state import ModelStateProbe

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]

# R1 / train thresholds — sourced from probe_config (F1 2026-05-01).
# Module-level aliases preserve grep-ability. **Do NOT override locally**
# — edit ``probe_config.ProbeThresholds`` instead (m1 review fix).
from probes.kundur.probe_state.probe_config import THRESHOLDS

IMPROVE_TOL_R1_SYS_PU_SQ = THRESHOLDS.r1_improve_tol_sys_pu_sq
TRAIN_TIMEOUT_S = THRESHOLDS.train_timeout_s
EPISODES_SMOKE = THRESHOLDS.episodes_smoke
EPISODES_FULL = THRESHOLDS.episodes_full

# Default PHI baselines from config_simulink.py (used unless overridden by mode).
PHI_F_BASELINE = 100.0
PHI_H_BASELINE = 5e-4
PHI_D_BASELINE = 5e-4


# ---------------------------------------------------------------------------
# Run-id helpers
# ---------------------------------------------------------------------------


def _short_train_run_id(config_label: str) -> str:
    """``probe_phase_c_<label>_<UTC TS>`` per plan §5."""
    ts = time.strftime("%Y%m%dT%H%M%S")
    return f"probe_phase_c_{config_label}_{ts}"


def _run_dir_for(run_id: str) -> Path:
    return REPO_ROOT / "results" / "sim_kundur" / "runs" / run_id


# ---------------------------------------------------------------------------
# Step 2 — short-train subprocess wrapper
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _TrainSpec:
    config_label: str
    phi_f: float
    phi_h: float
    phi_d: float
    episodes: int
    seed: int = 42


def _run_short_train(
    spec: _TrainSpec,
    timeout_s: int = TRAIN_TIMEOUT_S,
) -> dict[str, Any]:
    """Launch one short-train via subprocess.

    Returns
    -------
    dict with keys:
        ``run_id``: str — run-id used (also written to phase6 snapshot)
        ``run_dir``: str | None — actual run dir if it was created
        ``ckpt``: Path | None — best.pt if found
        ``wall_s``: float
        ``error``: str (only on failure)
    """
    run_id = _short_train_run_id(spec.config_label)
    run_dir = _run_dir_for(run_id)
    py = sys.executable
    cmd = [
        py, "scenarios/kundur/train_simulink.py",
        "--mode", "simulink",
        "--episodes", str(spec.episodes),
        "--run-id", run_id,
        "--seed", str(spec.seed),
        "--resume", "none",
    ]
    # Subprocess-scoped env: dict overwrite wins over inherited os.environ,
    # so any pre-set KUNDUR_PHI_F/H/D in the operator shell is replaced
    # by the spec values for this short-train (no global mutation).
    env = {
        **os.environ,
        "KUNDUR_PHI_F": str(spec.phi_f),
        "KUNDUR_PHI_H": str(spec.phi_h),
        "KUNDUR_PHI_D": str(spec.phi_d),
    }
    t0 = time.perf_counter()
    logger.info(
        "short_train %s | episodes=%d phi_f=%.4g phi_h=%.4g phi_d=%.4g | run_id=%s",
        spec.config_label, spec.episodes, spec.phi_f, spec.phi_h, spec.phi_d, run_id,
    )
    try:
        result = subprocess.run(
            cmd, cwd=REPO_ROOT, env=env,
            capture_output=True, text=True,
            timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "run_id": run_id,
            "run_dir": str(run_dir) if run_dir.exists() else None,
            "ckpt": None,
            "wall_s": float(timeout_s),
            "error": f"timeout after {timeout_s}s",
        }
    wall = time.perf_counter() - t0

    if result.returncode != 0:
        stderr_tail = "\n".join(result.stderr.splitlines()[-15:])
        return {
            "run_id": run_id,
            "run_dir": str(run_dir) if run_dir.exists() else None,
            "ckpt": None,
            "wall_s": wall,
            "error": f"non-zero exit {result.returncode}",
            "stderr_tail": stderr_tail,
        }
    best = run_dir / "checkpoints" / "best.pt"
    if not best.exists():
        return {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "ckpt": None,
            "wall_s": wall,
            "error": "best.pt not produced (training did not converge to a checkpoint)",
        }
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "ckpt": str(best),
        "wall_s": wall,
    }


# ---------------------------------------------------------------------------
# Step 3 — eval + R1 verdict
# ---------------------------------------------------------------------------


def _eval_ckpt(
    ckpt_path: Path,
    *,
    label: str,
    n_scenarios: int,
    timeout_s: int = 900,
) -> dict[str, Any]:
    """Evaluate one checkpoint via paper_eval (reuse Phase B wrapper)."""
    from probes.kundur.probe_state._trained_policy import (
        _RunSpec,
        _extract_metrics,
        _run_paper_eval,
    )

    spec = _RunSpec(label=label, zero_agent_idx=None, use_checkpoint=True)
    with tempfile.TemporaryDirectory(prefix="probe_phase_c_eval_") as tmp:
        out_json = Path(tmp) / f"{label}.json"
        eval_dict = _run_paper_eval(
            spec=spec,
            checkpoint=ckpt_path,
            scenario_set="none",
            n_scenarios=n_scenarios,
            out_json=out_json,
            timeout=timeout_s,
        )
        return _extract_metrics(eval_dict)


def _resolve_baseline_eval(probe: "ModelStateProbe") -> dict[str, Any] | None:
    """Reuse Phase B baseline if present; else return None (caller may run fresh)."""
    p5 = probe.snapshot.get("phase5_trained_policy") or {}
    if not isinstance(p5, dict) or "error" in p5:
        return None
    runs = p5.get("runs") or {}
    base = runs.get("baseline")
    if not isinstance(base, dict) or "error" in base or "r_f_global" not in base:
        return None
    out = dict(base)
    out["_source"] = "phase5"
    return out


def _compute_r1_verdict(
    baseline_eval: dict[str, Any] | None,
    no_rf_eval: dict[str, Any] | None,
) -> dict[str, Any]:
    """R1: r_f(no_rf) - r_f(baseline) < -IMPROVE_TOL ⇒ PASS.

    PENDING when either eval errored / missing / not present.

    Spurious vs healthy R1 PASS — known V1 ambiguity (deferred to V1.1):
    - **Healthy** R1 PASS: ``no_rf.r_f`` lies between ``baseline.r_f`` and
      ``zero_all.r_f`` ⇒ no_rf training did learn weak r_h/r_d control but
      lost the φ_f signal ⇒ φ_f IS a causal driver.
    - **Spurious** R1 PASS: ``no_rf.r_f ≈ zero_all.r_f`` ⇒ no_rf training
      did NOT learn anything (e.g. 200 ep too few; reward magnitude
      collapsed; SAC stuck) ⇒ R1 PASS reflects "no training vs trained"
      rather than the φ_f penalty being causal.

    V1 does NOT distinguish these cases automatically. Downstream consumers
    of ``r1_verdict`` must check ``zero_all`` from
    ``snap.phase5_trained_policy.runs.zero_all.r_f_global`` and compare
    against ``no_rf_r_f_global`` before treating R1 PASS as causal evidence.
    A future V1.1 enhancement will add a ``subverdict`` field
    (healthy / spurious) automatically.
    """
    if baseline_eval is None or no_rf_eval is None:
        return {
            "verdict": "PENDING",
            "evidence": "baseline or no_rf eval missing",
        }
    if "error" in baseline_eval or "error" in no_rf_eval:
        return {
            "verdict": "PENDING",
            "evidence": (
                f"baseline.error={baseline_eval.get('error')}, "
                f"no_rf.error={no_rf_eval.get('error')}"
            ),
        }
    if "r_f_global" not in baseline_eval or "r_f_global" not in no_rf_eval:
        return {"verdict": "PENDING", "evidence": "r_f_global missing in eval"}

    base_rf = float(baseline_eval["r_f_global"])
    no_rf_rf = float(no_rf_eval["r_f_global"])
    diff = no_rf_rf - base_rf  # >0 ⇒ no_rf better; <0 ⇒ baseline better
    pass_cond = diff < -IMPROVE_TOL_R1_SYS_PU_SQ
    return {
        "verdict": "PASS" if pass_cond else "REJECT",
        "evidence": (
            f"baseline.r_f={base_rf:+.3f} vs no_rf.r_f={no_rf_rf:+.3f} "
            f"(diff={diff:+.3f}; IMPROVE_TOL={IMPROVE_TOL_R1_SYS_PU_SQ})"
        ),
        "improvement_baseline_minus_no_rf": -diff,
        "baseline_r_f_global": base_rf,
        "no_rf_r_f_global": no_rf_rf,
    }


# ---------------------------------------------------------------------------
# Orchestrator entry point
# ---------------------------------------------------------------------------


def run_causality_short_train(probe: "ModelStateProbe") -> dict[str, Any]:
    """Phase 6 entry — called by ``ModelStateProbe.run`` after phase 5.

    Reads ``probe.phase_c_*`` config attrs:
    - ``phase_c_mode``: 'smoke' | 'full'
    - ``phase_c_train_timeout_s``: per-train wall ceiling (default 24 hr)
    - ``phase_c_eval_n_scenarios``: paper_eval scenario count (default 5)
    """
    mode = getattr(probe, "phase_c_mode", "smoke")
    eval_n = int(getattr(probe, "phase_c_eval_n_scenarios", 5))
    train_timeout = int(getattr(probe, "phase_c_train_timeout_s", TRAIN_TIMEOUT_S))

    if mode not in ("smoke", "full"):
        return {
            "error": f"invalid phase_c_mode {mode!r}; expected 'smoke' or 'full'",
            "mode": mode,
        }
    episodes = EPISODES_SMOKE if mode == "smoke" else EPISODES_FULL

    base_record: dict[str, Any] = {
        "mode": mode,
        "ablation_config": "no_rf",
        "phi_f_used": 0.0,
        "phi_h_used": PHI_H_BASELINE,
        "phi_d_used": PHI_D_BASELINE,
        "episodes_planned": episodes,
        "improve_tol_r1_sys_pu_sq": IMPROVE_TOL_R1_SYS_PU_SQ,
        "errors": [],
    }

    # 1. Resolve baseline eval (Phase B reuse).
    baseline_eval = _resolve_baseline_eval(probe)
    if baseline_eval is None:
        # Plan §3 says we may run a fresh baseline; for v1 we mark PENDING
        # rather than re-eval (avoids extra MATLAB cold start when Phase B
        # snapshot is the standard chain). Caller can run --phase 5,6 to
        # populate baseline first.
        base_record["baseline_source"] = "missing"
        base_record["baseline_eval"] = None
        base_record["error"] = (
            "no Phase B baseline run available; run --phase 5,6 in one invocation "
            "(or pre-populate phase5_trained_policy.runs.baseline)"
        )
        base_record["r1_verdict"] = {
            "verdict": "PENDING",
            "evidence": "baseline_eval missing",
        }
        return base_record

    base_record["baseline_source"] = baseline_eval.get("_source", "unknown")
    base_record["baseline_eval"] = {
        k: v for k, v in baseline_eval.items() if not k.startswith("_")
    }

    # 2. Short-train no_rf.
    train_spec = _TrainSpec(
        config_label="no_rf",
        phi_f=0.0,
        phi_h=PHI_H_BASELINE,
        phi_d=PHI_D_BASELINE,
        episodes=episodes,
    )
    train_t0 = time.perf_counter()
    train_result = _run_short_train(train_spec, timeout_s=train_timeout)
    base_record["wall_train_s"] = float(train_result.get("wall_s", time.perf_counter() - train_t0))
    base_record["run_id"] = train_result.get("run_id")
    base_record["run_dir"] = train_result.get("run_dir")
    base_record["no_rf_checkpoint"] = train_result.get("ckpt")
    base_record["episodes_completed"] = (
        episodes if "error" not in train_result else None
    )

    if "error" in train_result:
        base_record["errors"].append(
            {"phase": "train", "error": train_result["error"]}
        )
        if "stderr_tail" in train_result:
            base_record["errors"][-1]["stderr_tail"] = train_result["stderr_tail"]
        base_record["no_rf_eval"] = None
        base_record["r1_verdict"] = {
            "verdict": "PENDING",
            "evidence": f"short-train failed: {train_result['error']}",
        }
        return base_record

    # 3. Eval no_rf checkpoint.
    eval_t0 = time.perf_counter()
    try:
        no_rf_eval = _eval_ckpt(
            Path(train_result["ckpt"]),
            label="phase_c_no_rf",
            n_scenarios=eval_n,
        )
    except Exception as exc:  # noqa: BLE001 — fail-soft
        base_record["wall_eval_s"] = time.perf_counter() - eval_t0
        base_record["errors"].append(
            {"phase": "eval", "error": f"{type(exc).__name__}: {exc}"}
        )
        base_record["no_rf_eval"] = None
        base_record["r1_verdict"] = {
            "verdict": "PENDING",
            "evidence": f"no_rf eval crashed: {exc}",
        }
        return base_record
    base_record["wall_eval_s"] = time.perf_counter() - eval_t0

    if "error" in no_rf_eval:
        base_record["errors"].append({"phase": "eval", "error": no_rf_eval["error"]})
    base_record["no_rf_eval"] = no_rf_eval

    # 4. R1 verdict.
    base_record["r1_verdict"] = _compute_r1_verdict(baseline_eval, no_rf_eval)
    return base_record
