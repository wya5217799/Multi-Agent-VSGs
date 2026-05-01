# FACT: dynamics phases delegate sim to KundurSimulinkEnv. Numbers in this
# module are derived from omega arrays returned by env.step(). Anything
# in NOTES/README about expected values is CLAIM.
"""Phase 3 + 4 — sim phases.

Phase 3 (``run_open_loop``): one 5s sim with magnitude=0 (all dispatch
amplitudes effectively zero). Records per-agent omega per control step.

Phase 4 (``run_per_dispatch``): one 5s sim per effective dispatch type,
magnitude=+0.5 sys-pu (override via ``probe.dispatch_magnitude``). Single
env instance reused; ``_disturbance_type`` mutated between runs to avoid
re-warmup overhead.

Caveats:
- omega returned by ``env.step()`` is the control-rate sample (one per
  DT=0.2s), not the solver-rate ``omega_ts_*`` Timeseries. sha256
  distinctness is therefore over N=25 samples, not 5000. Adequate for
  G2 distinct-source check, finer-grained checks would need direct
  ``omega_ts_*.Data`` reads.
- Some dispatch types are documented as "name-valid only" (LoadStep R,
  CCS Trip Bus 14/15) and produce ~0.01 Hz signal. Effective subset
  (from Phase 1) excludes these by design.
"""
from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from probes.kundur.probe_state.probe_state import ModelStateProbe

logger = logging.getLogger(__name__)

# 50 Hz nominal; project Kundur convention (config.py FN).
F_NOM_HZ = 50.0
DT_S = 0.2

# G1 trigger floor — sourced from probe_config (F1 2026-05-01).
from probes.kundur.probe_state.probe_config import THRESHOLDS
RESPOND_THRESHOLD_HZ = THRESHOLDS.g1_respond_hz


def _sha256_array(arr: np.ndarray) -> str:
    return hashlib.sha256(arr.astype(np.float64).tobytes()).hexdigest()


def _build_env(disturbance_type: str):
    """Lazy import + construct ``KundurSimulinkEnv`` with given dispatch.

    Hoisted into a helper so that import errors surface as Phase failures
    (caught by the orchestrator) rather than at module import time.
    """
    from env.simulink.kundur_simulink_env import KundurSimulinkEnv

    return KundurSimulinkEnv(disturbance_type=disturbance_type)


def _action_zero(env) -> np.ndarray:
    """Zero action: leave M/D at default IC, no parameter changes."""
    shape = env.action_space.shape
    return np.zeros(shape, dtype=np.float32)


def _collect_omega(env, n_steps: int) -> tuple[np.ndarray, dict[str, Any]]:
    """Run ``n_steps`` zero-action env.step calls; return omega trace.

    Returns
    -------
    omega : ndarray of shape (n_steps + 1, n_agents)
        Row 0 = post-warmup IC sample (env.reset's info['omega'] when
        present, else first step's omega). Subsequent rows are env.step
        outputs.
    metadata : dict with sim_ok counts, per-step terminate flags, etc.
    """
    zero = _action_zero(env)
    omega_rows: list[np.ndarray] = []
    sim_ok_count = 0
    terminated_at: int | None = None

    for step_idx in range(n_steps):
        obs, _reward, terminated, truncated, info = env.step(zero)
        omega_rows.append(np.asarray(info["omega"], dtype=np.float64).copy())
        if info.get("sim_ok", True):
            sim_ok_count += 1
        if terminated:
            terminated_at = step_idx
            break

    if not omega_rows:
        raise RuntimeError("No env.step calls succeeded; cannot extract omega")

    omega_arr = np.stack(omega_rows, axis=0)
    return omega_arr, {
        "n_steps_run": int(omega_arr.shape[0]),
        "sim_ok_count": sim_ok_count,
        "terminated_at": terminated_at,
    }


def _per_agent_stats(
    omega: np.ndarray,
    *,
    f_nom_hz: float,
    settle_window_steps: int,
) -> list[dict[str, Any]]:
    """Compute per-agent statistics over an (n_steps, n_agents) omega trace.

    omega is in pu (1.0 = nominal); converted to Hz deviation as
    ``f_dev = (omega - 1.0) * f_nom_hz``.
    """
    n_steps, n_agents = omega.shape
    f_dev_hz = (omega - 1.0) * f_nom_hz

    stats: list[dict[str, Any]] = []
    for i in range(n_agents):
        col = omega[:, i]
        f_col = f_dev_hz[:, i]
        post = col[settle_window_steps:] if n_steps > settle_window_steps else col
        stats.append(
            {
                "idx": i,
                "n_samples": int(n_steps),
                "mean_omega_pu": float(col.mean()),
                "std_omega_pu_post_settle": float(post.std()),
                "max_abs_f_dev_hz": float(np.max(np.abs(f_col))),
                "spread_max_min_pu": float(col.max() - col.min()),
                "sha256_omega": _sha256_array(col),
            }
        )
    return stats


def _r_f_local_share(omega: np.ndarray, f_nom_hz: float) -> list[float]:
    """Per-agent share of the global cumulative frequency-variance reward.

    Implements the paper §IV-C frequency reward decomposition::

        Δf_i,t  = (omega_i,t - 1) * f_nom
        z_i,t   = Δf_i,t - mean_j Δf_j,t
        share_i = sum_t z_i,t^2  /  sum_{i,t} z_i,t^2
    """
    f_dev = (omega - 1.0) * f_nom_hz  # (T, N)
    z = f_dev - f_dev.mean(axis=1, keepdims=True)  # (T, N)
    per_agent_sum = (z * z).sum(axis=0)  # (N,)
    total = per_agent_sum.sum()
    if total <= 0:
        return [0.0] * omega.shape[1]
    return (per_agent_sum / total).tolist()


# ---------------------------------------------------------------------------
# Phase 3 — open-loop
# ---------------------------------------------------------------------------


def run_open_loop(probe: "ModelStateProbe") -> dict[str, Any]:
    """5s sim, no disturbance. Captures the ambient/IC dynamics."""
    n_steps = max(1, int(round(probe.sim_duration / DT_S)))
    settle_steps = max(1, int(round(2.0 / DT_S)))  # 2 s post-IC settle

    # Pick any valid dispatch_type; magnitude=0 means it will not fire.
    env = _build_env(disturbance_type="pm_step_proxy_random_gen")
    try:
        _obs, _info = env.reset(options={"disturbance_magnitude": 0.0})
        omega, sim_meta = _collect_omega(env, n_steps)
    finally:
        try:
            env.close()
        except Exception:  # noqa: BLE001
            pass

    per_agent = _per_agent_stats(
        omega, f_nom_hz=F_NOM_HZ, settle_window_steps=settle_steps
    )
    sha_set = {a["sha256_omega"] for a in per_agent}
    stds = [a["std_omega_pu_post_settle"] for a in per_agent]
    return {
        "magnitude_sys_pu": 0.0,
        "n_steps": int(omega.shape[0]),
        "n_agents": int(omega.shape[1]),
        "dt_control_s": DT_S,
        "f_nom_hz": F_NOM_HZ,
        "per_agent": per_agent,
        "all_sha256_distinct": len(sha_set) == omega.shape[1],
        "n_distinct_sha256": len(sha_set),
        "std_diff_max_min_pu": (max(stds) - min(stds)) if stds else 0.0,
        "sim_meta": sim_meta,
    }


# ---------------------------------------------------------------------------
# Phase 4 — per-dispatch
# ---------------------------------------------------------------------------


def run_per_dispatch(probe: "ModelStateProbe") -> dict[str, Any]:
    """One sim per effective dispatch, using per-dispatch metadata.

    Plan §5/F3: each dispatch may have its own appropriate magnitude /
    sim duration; cross-dispatch metric comparison is biased otherwise.
    Per-dispatch metadata from ``dispatch_metadata.METADATA``; missing
    entries fall back to ``probe.dispatch_magnitude`` /
    ``probe.sim_duration`` and surface ``metadata_missing=True``.
    """
    from scenarios.kundur.config_simulink import (
        KUNDUR_DISTURBANCE_TYPES_VALID,
    )
    from probes.kundur.probe_state.dispatch_metadata import get_metadata

    phase1 = probe.snapshot.get("phase1_topology", {}) or {}
    effective_from_phase1 = phase1.get("dispatch_effective", []) or []
    targets = [d for d in effective_from_phase1 if d in KUNDUR_DISTURBANCE_TYPES_VALID]
    skipped = [d for d in effective_from_phase1 if d not in KUNDUR_DISTURBANCE_TYPES_VALID]

    if not targets:
        return {
            "probe_default_magnitude_sys_pu": float(probe.dispatch_magnitude),
            "probe_default_sim_duration_s": float(probe.sim_duration),
            "skipped_unrecognised": skipped,
            "dispatches": {},
            "warning": "no effective dispatches intersect KUNDUR_DISTURBANCE_TYPES_VALID",
        }

    settle_window_s = 2.0  # post-trigger settle window for std stats

    env = _build_env(disturbance_type=targets[0])
    results: dict[str, Any] = {}
    metadata_warnings: list[str] = []
    try:
        for d_type in targets:
            md = get_metadata(d_type)
            if md["metadata_missing"]:
                metadata_warnings.append(d_type)

            mag = (
                float(md["default_magnitude_sys_pu"])
                if md["default_magnitude_sys_pu"] is not None
                else float(probe.dispatch_magnitude)
            )
            sim_s = (
                float(md["default_sim_duration_s"])
                if md["default_sim_duration_s"] is not None
                else float(probe.sim_duration)
            )
            n_steps = max(1, int(round(sim_s / DT_S)))
            settle_steps = max(1, int(round(settle_window_s / DT_S)))

            try:
                env._disturbance_type = d_type
                _obs, info0 = env.reset(
                    options={"disturbance_magnitude": mag}
                )
                resolved = info0.get("resolved_disturbance_type", d_type)
                omega, sim_meta = _collect_omega(env, n_steps)

                per_agent = _per_agent_stats(
                    omega,
                    f_nom_hz=F_NOM_HZ,
                    settle_window_steps=settle_steps,
                )
                f_dev_hz = (omega - 1.0) * F_NOM_HZ
                max_abs_per_agent = np.max(np.abs(f_dev_hz), axis=0)
                agents_responding = int(
                    (max_abs_per_agent > RESPOND_THRESHOLD_HZ).sum()
                )
                share = _r_f_local_share(omega, F_NOM_HZ)
                # G4 reconciliation (2026-05-01, design §5.7):
                # compare observed max|Δf| against historical floor.
                expected_floor = md.get("expected_min_df_hz")
                observed_global = float(max_abs_per_agent.max())
                if expected_floor is None:
                    floor_status = "expected_floor_unknown"
                    below_floor = None
                elif observed_global < float(expected_floor):
                    floor_status = "below_expected_floor"
                    below_floor = True
                    logger.warning(
                        "Phase 4 dispatch %s observed max|Δf|=%.4f Hz < "
                        "expected floor %.4f Hz (source: %s) — possible "
                        "model degradation or build drift",
                        d_type, observed_global, float(expected_floor),
                        md.get("historical_source") or "—",
                    )
                else:
                    floor_status = "ok"
                    below_floor = False
                results[d_type] = {
                    "metadata": md,
                    "applied_magnitude_sys_pu": mag,
                    "applied_sim_duration_s": sim_s,
                    "resolved_disturbance_type": resolved,
                    "agents_responding_above_1mHz": agents_responding,
                    "max_abs_f_dev_hz_per_agent": max_abs_per_agent.tolist(),
                    "max_abs_f_dev_hz_global": observed_global,
                    "expected_min_df_hz": expected_floor,
                    "below_expected_floor": below_floor,
                    "floor_status": floor_status,
                    "r_f_local_share": share,
                    "r_f_share_max_min_diff": (
                        float(max(share) - min(share)) if share else 0.0
                    ),
                    "per_agent": per_agent,
                    "sim_meta": sim_meta,
                }
            except Exception as exc:  # noqa: BLE001 — fail-soft per dispatch
                logger.warning("Dispatch %s FAILED: %s", d_type, exc)
                results[d_type] = {
                    "error": f"{type(exc).__name__}: {exc}",
                    "metadata": md,
                    "applied_magnitude_sys_pu": mag,
                    "applied_sim_duration_s": sim_s,
                }
    finally:
        try:
            env.close()
        except Exception:  # noqa: BLE001
            pass

    return {
        "probe_default_magnitude_sys_pu": float(probe.dispatch_magnitude),
        "probe_default_sim_duration_s": float(probe.sim_duration),
        "skipped_unrecognised": skipped,
        "metadata_missing_dispatches": metadata_warnings,
        "dispatches": results,
    }
