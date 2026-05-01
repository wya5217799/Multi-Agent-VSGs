# FACT: this module's runtime output is the contract; comments in
# README/design about Phase B fields are CLAIM until verified against
# what this module actually emits.
"""Phase 5 — trained policy ablation.

Plan: ``quality_reports/plans/2026-05-01_probe_state_phase_B.md``.
Prerequisites: ``quality_reports/phase_B_prerequisites.md``.

Architecture:
- ``_discover_checkpoint``: search rule (CLI / ENV / auto-search).
- ``_run_paper_eval``: subprocess wrapper with timeout + fail-soft.
- ``_extract_metrics``: pull r_f / r_h / r_d from paper_eval JSON.
- ``_compute_ablation_diffs``: per-agent attribution.
- ``run_trained_policy_ablation``: orchestrator entry point.

Design rules (Plan §1):
- N_ESS comes from phase1.n_ess (not hardcoded).
- Checkpoint path is NEVER hardcoded — rule-based discovery only.
- paper_eval is consumed via subprocess + JSON; no internal imports.
- All runs are subprocess-isolated (MATLAB engine independence).
- schema_version stays = 1 (additive fields only).
"""
from __future__ import annotations

import json
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

# G6 / paper_eval thresholds — sourced from probe_config (F1 2026-05-01).
# Module-level aliases kept for back-compat / grep-ability. **Do NOT
# override locally** — edit ``probe_config.ProbeThresholds`` and bump
# ``IMPLEMENTATION_VERSION``; otherwise this module silently drifts from
# the rest (m1 review fix 2026-05-01).
from probes.kundur.probe_state.probe_config import THRESHOLDS

G6_K_REQUIRED_CONTRIBUTORS = THRESHOLDS.g6_k_required_contributors
G6_NOISE_THRESHOLD_SYS_PU_SQ = THRESHOLDS.g6_noise_threshold_sys_pu_sq
G6_IMPROVE_TOL_SYS_PU_SQ = THRESHOLDS.g6_improve_tol_sys_pu_sq
PAPER_EVAL_TIMEOUT_S = THRESHOLDS.paper_eval_timeout_s


@dataclass(frozen=True)
class _RunSpec:
    """One ablation run configuration."""

    label: str
    zero_agent_idx: int | None  # None = no zero (baseline or zero_all)
    use_checkpoint: bool        # False = zero_all (paper_eval no-ckpt mode)


def _build_run_matrix(n_agents: int) -> list[_RunSpec]:
    """Plan §3 Step 3 — N+2 runs total."""
    matrix: list[_RunSpec] = [
        _RunSpec(label="baseline", zero_agent_idx=None, use_checkpoint=True),
    ]
    for i in range(n_agents):
        matrix.append(
            _RunSpec(
                label=f"zero_agent_{i}",
                zero_agent_idx=i,
                use_checkpoint=True,
            )
        )
    matrix.append(
        _RunSpec(label="zero_all", zero_agent_idx=None, use_checkpoint=False)
    )
    return matrix


# ---------------------------------------------------------------------------
# Step 2: checkpoint discovery
# ---------------------------------------------------------------------------


def _discover_checkpoint(
    cli_override: str | None = None,
) -> tuple[Path | None, str]:
    """Find a checkpoint per the priority chain in Plan §5 Step 2.

    Returns
    -------
    (path, strategy) tuple. Path is None when no checkpoint matches.
    Strategy is a short string for the snapshot
    (``cli_override`` / ``env_override`` / ``auto_search`` / ``none_found``).
    """
    if cli_override:
        p = Path(cli_override).expanduser().resolve()
        if not p.exists():
            logger.warning(
                "CLI --checkpoint %s does not exist; falling through", p
            )
        else:
            return p, "cli_override"

    env_path = os.environ.get("KUNDUR_PROBE_CHECKPOINT")
    if env_path:
        p = Path(env_path).expanduser().resolve()
        if p.exists():
            return p, "env_override"
        logger.warning(
            "KUNDUR_PROBE_CHECKPOINT=%s does not exist; falling through",
            env_path,
        )

    # Auto-search ordered roots.
    search_roots = [
        REPO_ROOT / "results" / "harness" / "kundur",
        REPO_ROOT / "results" / "sim_kundur" / "runs",
        REPO_ROOT / "results" / "sim_kundur" / "archive",
    ]
    candidates: list[Path] = []
    for root in search_roots:
        if not root.exists():
            continue
        candidates.extend(root.rglob("best.pt"))

    # Filter: path must mention an active-profile-compatible token.
    # Heuristic — Phase A discovery already proves the active profile is
    # kundur_cvs_v3 (KUNDUR_MODEL_PROFILE points there); ckpt paths
    # under v3 training runs typically contain "kundur_simulink" or
    # "cvs_v3". We accept either; an obs_dim mismatch at load time is
    # caught by paper_eval and surfaces as a per-run error.
    def _is_v3_compatible(p: Path) -> bool:
        s = str(p).lower()
        return "kundur_simulink" in s or "cvs_v3" in s or "kundur_cvs" in s

    candidates = [p for p in candidates if _is_v3_compatible(p)]
    if not candidates:
        return None, "none_found"

    # Newest first.
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0], "auto_search"


# ---------------------------------------------------------------------------
# Step 3: subprocess wrapper
# ---------------------------------------------------------------------------


def _run_paper_eval(
    *,
    spec: _RunSpec,
    checkpoint: Path | None,
    scenario_set: str,
    n_scenarios: int,
    out_json: Path,
    timeout: int = PAPER_EVAL_TIMEOUT_S,
) -> dict[str, Any]:
    """Invoke ``python -m evaluation.paper_eval`` once.

    Returns the loaded JSON dict on success, or ``{"error": ...}`` on
    timeout / non-zero exit / JSON missing.
    """
    py = sys.executable
    cmd = [
        py, "-m", "evaluation.paper_eval",
        "--scenario-set", scenario_set,
        "--n-scenarios", str(n_scenarios),
        "--disturbance-mode", "gen",  # plan §3
        "--seed-base", "42",
        "--policy-label", spec.label,
        "--output-json", str(out_json),
    ]
    if spec.use_checkpoint and checkpoint is not None:
        cmd += ["--checkpoint", str(checkpoint)]
    if spec.zero_agent_idx is not None:
        cmd += ["--zero-agent-idx", str(spec.zero_agent_idx)]

    t0 = time.perf_counter()
    logger.info("paper_eval %s | %s", spec.label, " ".join(cmd[2:]))
    try:
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "error": f"timeout after {timeout}s",
            "wall_s": timeout,
        }
    wall = time.perf_counter() - t0

    if result.returncode != 0:
        # Surface last few stderr lines for debugging.
        stderr_tail = "\n".join(result.stderr.splitlines()[-10:])
        return {
            "error": f"non-zero exit {result.returncode}",
            "stderr_tail": stderr_tail,
            "wall_s": wall,
        }
    if not out_json.exists():
        return {
            "error": "output JSON missing after success exit",
            "wall_s": wall,
        }
    try:
        eval_dict = json.loads(out_json.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"JSON parse: {exc}", "wall_s": wall}

    eval_dict["_wall_s"] = wall
    return eval_dict


# ---------------------------------------------------------------------------
# Step 4: metric extraction + ablation diffs
# ---------------------------------------------------------------------------


def _extract_metrics(eval_dict: dict[str, Any]) -> dict[str, Any]:
    """Pull r_f / r_h / r_d / share inputs out of a paper_eval JSON.

    Field map (verified against ``evaluation/paper_eval.py:670-707`` and
    the cumulative dict shape at line 530-545):
    - ``cumulative_reward_global_rf`` is a **dict** with keys
      {``unnormalized``, ``per_M``, ``per_M_per_N``, ...}. We pick
      ``unnormalized`` as ``r_f_global`` (matches paper Sec.IV-C cum_unnorm).
      Float fallback kept for forward-compat.
    - sum(``per_episode_metrics[*].r_h_total``) → ``r_h_global``.
    - sum(``per_episode_metrics[*].r_d_total``) → ``r_d_global``.
    """
    if "error" in eval_dict:
        return dict(eval_dict)  # propagate error verbatim

    raw = eval_dict.get("cumulative_reward_global_rf", 0.0)
    if isinstance(raw, dict):
        r_f_global = float(raw.get("unnormalized", 0.0))
    else:
        r_f_global = float(raw)

    eps = eval_dict.get("per_episode_metrics", []) or []
    # Schema-drift watchdog (M4 fix 2026-05-01): paper_eval may rename
    # r_h_total / r_d_total; if so, sums silently become 0.0 — log a
    # warning so the snapshot diff against history makes the rename visible.
    if eps:
        first = eps[0] or {}
        for required in ("r_h_total", "r_d_total"):
            if required not in first:
                logger.warning(
                    "paper_eval per_episode_metrics[0] missing %r — "
                    "schema drift? r_%s_global will be 0",
                    required, required.split("_")[1],
                )
    r_h_global = float(sum(e.get("r_h_total", 0.0) for e in eps))
    r_d_global = float(sum(e.get("r_d_total", 0.0) for e in eps))

    # Per-agent r_f average across episodes (used by baseline rf_rh_rd_share
    # if needed; not consumed by G6 directly).
    per_agent_sums: list[float] = []
    if eps and "r_f_global_per_agent" in eps[0]:
        n_agents = len(eps[0]["r_f_global_per_agent"])
        per_agent_sums = [0.0] * n_agents
        for e in eps:
            row = e.get("r_f_global_per_agent", []) or []
            for i, v in enumerate(row[:n_agents]):
                per_agent_sums[i] += float(v)

    return {
        "r_f_global": r_f_global,
        "r_h_global": r_h_global,
        "r_d_global": r_d_global,
        "r_f_per_agent_total": per_agent_sums,
        "n_episodes": len(eps),
        "wall_s": float(eval_dict.get("_wall_s", 0.0)),
        "action_mean": None,  # paper_eval does not currently dump actions
    }


def _compute_ablation_diffs(
    runs: dict[str, dict[str, Any]],
    n_agents: int,
) -> tuple[list[float | None], list[bool | None]]:
    """Plan §4 — diff[i] = r_f_global(zero_agent_i) - r_f_global(baseline).

    Returns (ablation_diffs, agent_contributes). Both lists have length
    n_agents. None entries mean the corresponding zero_agent_i run errored.
    """
    base = runs.get("baseline", {}) or {}
    base_r_f = base.get("r_f_global")
    diffs: list[float | None] = []
    contribs: list[bool | None] = []
    for i in range(n_agents):
        z = runs.get(f"zero_agent_{i}", {}) or {}
        z_r_f = z.get("r_f_global")
        if base_r_f is None or z_r_f is None or "error" in z or "error" in base:
            diffs.append(None)
            contribs.append(None)
            continue
        diff = float(z_r_f) - float(base_r_f)
        diffs.append(diff)
        # i contributes when zeroing it makes r_f noticeably worse:
        # since r_f ≤ 0, "worse" = more negative = diff < 0 by NOISE.
        contribs.append(diff < -G6_NOISE_THRESHOLD_SYS_PU_SQ)
    return diffs, contribs


def _compute_rf_rh_rd_share(baseline: dict[str, Any]) -> dict[str, float] | None:
    """Plan §4 — fraction of |r_f|/|r_h|/|r_d| in total |reward|."""
    if not baseline or "error" in baseline:
        return None
    rf = abs(float(baseline.get("r_f_global", 0.0)))
    rh = abs(float(baseline.get("r_h_global", 0.0)))
    rd = abs(float(baseline.get("r_d_global", 0.0)))
    total = rf + rh + rd
    if total <= 0:
        return {"rf": 0.0, "rh": 0.0, "rd": 0.0}
    return {"rf": rf / total, "rh": rh / total, "rd": rd / total}


# ---------------------------------------------------------------------------
# Orchestrator entry point
# ---------------------------------------------------------------------------


def run_trained_policy_ablation(probe: "ModelStateProbe") -> dict[str, Any]:
    """Phase 5 entry — called by ``ModelStateProbe.run`` after phase 4.

    Reads ``probe.phase_b_*`` config attrs:
    - ``probe.phase_b_mode``: 'smoke' | 'full'
    - ``probe.phase_b_checkpoint``: CLI override (str or None)
    - ``probe.phase_b_n_scenarios``: smoke override (int)
    """
    mode = getattr(probe, "phase_b_mode", "smoke")
    cli_ckpt = getattr(probe, "phase_b_checkpoint", None)
    n_scenarios_override = getattr(probe, "phase_b_n_scenarios", 5)

    # Choose scenario_set + n_scenarios from mode.
    if mode == "full":
        scenario_set = "test"
        n_scenarios = 50  # paper_eval will override w/ manifest length
    else:
        scenario_set = "none"
        n_scenarios = int(n_scenarios_override)

    # Pull n_agents from phase 1; fall back to config_simulink default.
    phase1 = probe.snapshot.get("phase1_topology") or {}
    n_agents = phase1.get("n_ess")
    if not n_agents:
        try:
            from scenarios.contract import KUNDUR as _CONTRACT
            n_agents = int(_CONTRACT.n_agents)
        except Exception:  # noqa: BLE001
            return {
                "error": "cannot determine n_agents (phase1 absent + import failed)",
                "mode": mode,
            }

    # Discover checkpoint.
    ckpt_path, ckpt_strategy = _discover_checkpoint(cli_override=cli_ckpt)
    if ckpt_path is None and ckpt_strategy == "none_found":
        return {
            "error": "no_matching_checkpoint",
            "mode": mode,
            "scenario_set": scenario_set,
            "n_scenarios": n_scenarios,
            "n_agents": n_agents,
            "checkpoint_match_strategy": ckpt_strategy,
            "runs": {},
        }

    ckpt_mtime = (
        time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ckpt_path.stat().st_mtime))
        if ckpt_path
        else None
    )

    # Run matrix.
    matrix = _build_run_matrix(n_agents)
    runs: dict[str, dict[str, Any]] = {}
    per_run_errors: list[dict[str, str]] = []

    with tempfile.TemporaryDirectory(prefix="probe_state_phase_b_") as tmp_dir:
        tmp_out = Path(tmp_dir)
        for spec in matrix:
            out_json = tmp_out / f"{spec.label}.json"
            try:
                eval_dict = _run_paper_eval(
                    spec=spec,
                    checkpoint=ckpt_path if spec.use_checkpoint else None,
                    scenario_set=scenario_set,
                    n_scenarios=n_scenarios,
                    out_json=out_json,
                )
                metrics = _extract_metrics(eval_dict)
                metrics["label"] = spec.label
                runs[spec.label] = metrics
                if "error" in metrics:
                    per_run_errors.append(
                        {"label": spec.label, "error": str(metrics["error"])}
                    )
            except Exception as exc:  # noqa: BLE001 — fail-soft per run
                logger.warning("ablation %s FAILED: %s", spec.label, exc)
                runs[spec.label] = {
                    "error": f"{type(exc).__name__}: {exc}",
                    "label": spec.label,
                }
                per_run_errors.append(
                    {"label": spec.label, "error": str(exc)}
                )

    # Aggregate.
    diffs, contribs = _compute_ablation_diffs(runs, n_agents)
    share = _compute_rf_rh_rd_share(runs.get("baseline", {}))

    return {
        "checkpoint_path": str(ckpt_path) if ckpt_path else None,
        "checkpoint_mtime": ckpt_mtime,
        "checkpoint_match_strategy": ckpt_strategy,
        "mode": mode,
        "scenario_set": scenario_set,
        "n_scenarios": n_scenarios,
        "disturbance_mode": "gen",
        "n_agents": int(n_agents),
        "noise_threshold_sys_pu_sq": G6_NOISE_THRESHOLD_SYS_PU_SQ,
        "improve_tol_sys_pu_sq": G6_IMPROVE_TOL_SYS_PU_SQ,
        "k_required_contributors": G6_K_REQUIRED_CONTRIBUTORS,
        "runs": runs,
        "ablation_diffs": diffs,
        "agent_contributes": contribs,
        "rf_rh_rd_share": share,
        "errors": per_run_errors,
    }
