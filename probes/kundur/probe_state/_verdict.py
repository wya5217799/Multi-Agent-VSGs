# FACT: gate logic = code below; verdicts assigned by this code are FACT
# given the input snapshot. Any narrative about "what gate X means" is
# CLAIM until cross-checked with the gate's own evidence string.
"""Falsification gates G1-G6 — Evidence-Pack boundary (v0.5.0).

Each gate consumes its phase data and emits one of four verdicts plus a
list of reason codes:

- ``PASS`` — observed evidence rules out the falsification hypothesis
- ``REJECT`` — evidence is decisive AND data confirms the hypothesis
- ``PENDING`` — data insufficient (re-run the missing phase to resolve)
- ``ERROR`` — pipeline broke (a phase threw / subprocess failed; re-run
  alone will not self-heal — fix the upstream code or environment first)

ERROR vs PENDING is the key distinction this module enforces: PENDING is
recoverable by running more phases; ERROR is a pipeline-level failure
that must be diagnosed before any verdict is meaningful.

reason_codes are drawn from ``probe_config.REASON_CODES`` (frozen
vocabulary). Every verdict dict carries a non-empty ``reason_codes``
list — empty lists are a contract violation and raise at write time.

Gate definitions:

| Gate | Falsification hypothesis | PASS condition |
|------|--------------------------|----------------|
| G1 — signal      | "no dispatch can excite ≥ 2 agents" | ≥ 1 dispatch with ≥ 2 agents responding > THRESHOLDS.g1_respond_hz |
| G2 — measurement | "all omega traces are aliased"    | open-loop sha256 distinct across agents |
| G3 — gradient    | "per-agent reward share is degenerate" | max-min r_f share > THRESHOLDS.g3_share_diff_rel × mean (some dispatch) |
| G4 — position    | "dispatch site doesn't change mode shape" | ≥ 2 distinct responder signatures across dispatches |
| G5 — trace       | "agent omega-std collapses to one number" | std diff across agents > THRESHOLDS.g5_noise_floor_pu |
| G6 — trained-policy | "policy is degenerate AND/OR φ_f is not a causal driver" | G6_partial PASS (Phase B) AND R1 PASS (Phase C) |
"""
from __future__ import annotations

from typing import Any

from probes.kundur.probe_state import probe_config
from probes.kundur.probe_state.probe_config import REASON_CODES

VERDICT_PASS = "PASS"
VERDICT_REJECT = "REJECT"
VERDICT_PENDING = "PENDING"
VERDICT_ERROR = "ERROR"

_VALID_VERDICTS = frozenset(
    {VERDICT_PASS, VERDICT_REJECT, VERDICT_PENDING, VERDICT_ERROR}
)


def compute_gates(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "G1_signal": _g1_signal(snapshot),
        "G2_measurement": _g2_measurement(snapshot),
        "G3_gradient": _g3_gradient(snapshot),
        "G4_position": _g4_position(snapshot),
        "G5_trace": _g5_trace(snapshot),
        "G6_trained_policy": _g6_trained_policy(snapshot),
    }


# ---------------------------------------------------------------------------
# Phase status helpers (tristate: present | missing | errored)
# ---------------------------------------------------------------------------

_STATUS_PRESENT = "present"
_STATUS_MISSING = "missing"
_STATUS_ERRORED = "errored"


def _phase_status(
    snap: dict[str, Any],
    key: str,
) -> tuple[dict[str, Any] | None, str]:
    """Inspect a top-level phase entry without absorbing ERROR into PENDING.

    Returns
    -------
    (payload, status). status ∈ {"present","missing","errored"}.
        - "missing": key absent / None / non-dict
        - "errored": dict with an ``error`` field
        - "present": dict with no error field; payload is the dict
    """
    p = snap.get(key)
    if p is None or not isinstance(p, dict):
        return None, _STATUS_MISSING
    if "error" in p:
        return None, _STATUS_ERRORED
    return p, _STATUS_PRESENT


def _phase4_data_dispatches(snap: dict[str, Any]) -> dict[str, Any]:
    """Return only dispatches that have data (filter out per-dispatch errors).

    Caller must check phase4 status separately via ``_phase_status`` to
    distinguish "phase4 missing" / "phase4 errored" / "phase4 present
    but every dispatch errored or empty".
    """
    p4, status = _phase_status(snap, "phase4_per_dispatch")
    if status != _STATUS_PRESENT or p4 is None:
        return {}
    return {
        k: v
        for k, v in (p4.get("dispatches", {}) or {}).items()
        if isinstance(v, dict) and "error" not in v
    }


# ---------------------------------------------------------------------------
# Verdict factory — strict contract on reason_codes
# ---------------------------------------------------------------------------


def _verdict(
    verdict: str,
    evidence: str,
    *,
    reason_codes: list[str],
    **extras: Any,
) -> dict[str, Any]:
    """Build a verdict dict with strict reason_codes contract.

    Raises
    ------
    ValueError
        If ``verdict`` is not in ``_VALID_VERDICTS``, or if
        ``reason_codes`` is empty, or if any code is not in
        ``REASON_CODES``.
    """
    if verdict not in _VALID_VERDICTS:
        raise ValueError(
            f"unknown verdict {verdict!r}; expected one of "
            f"{sorted(_VALID_VERDICTS)}"
        )
    if not reason_codes:
        raise ValueError(
            f"reason_codes must be non-empty (verdict={verdict!r}, "
            f"evidence={evidence!r})"
        )
    unknown = [c for c in reason_codes if c not in REASON_CODES]
    if unknown:
        raise ValueError(
            f"unknown reason_codes {unknown!r}; allowed = "
            f"{sorted(REASON_CODES)}"
        )
    out: dict[str, Any] = {
        "verdict": verdict,
        "evidence": evidence,
        "reason_codes": list(reason_codes),
    }
    out.update(extras)
    return out


# ---------------------------------------------------------------------------
# Phase-level early-return helpers
# ---------------------------------------------------------------------------


def _early_phase_check(
    snap: dict[str, Any],
    *,
    key: str,
    pretty: str,
) -> dict[str, Any] | None:
    """Return PENDING/ERROR verdict if phase is missing/errored, else None.

    Caller continues with normal data-driven checks when this returns None.
    """
    payload, status = _phase_status(snap, key)
    if status == _STATUS_MISSING:
        return _verdict(
            VERDICT_PENDING,
            f"{pretty} missing",
            reason_codes=["MISSING_PHASE"],
        )
    if status == _STATUS_ERRORED:
        err_msg = (snap.get(key) or {}).get("error", "<unknown>")
        return _verdict(
            VERDICT_ERROR,
            f"{pretty} errored: {err_msg}",
            reason_codes=["PHASE_ERRORED"],
        )
    return None


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


def _g1_signal(snap: dict[str, Any]) -> dict[str, Any]:
    early = _early_phase_check(snap, key="phase4_per_dispatch", pretty="phase4_per_dispatch")
    if early is not None:
        return early

    dispatches = _phase4_data_dispatches(snap)
    if not dispatches:
        return _verdict(
            VERDICT_PENDING,
            "phase4_per_dispatch present but no data-bearing dispatches",
            reason_codes=["EMPTY_DATA"],
        )

    # Distinguish "field missing" from "field present but zero".
    missing_field = [
        d_type
        for d_type, d in dispatches.items()
        if "agents_responding_above_1mHz" not in d
    ]
    if missing_field:
        return _verdict(
            VERDICT_PENDING,
            (
                f"agents_responding_above_1mHz missing in "
                f"{len(missing_field)} dispatch(es): "
                f"{missing_field[:3]}{'...' if len(missing_field) > 3 else ''}"
            ),
            reason_codes=["MISSING_FIELD"],
        )

    best_d = None
    best_count = -1
    for d_type, d in dispatches.items():
        c = int(d.get("agents_responding_above_1mHz", 0))
        if c > best_count:
            best_count = c
            best_d = d_type
    evidence = f"best dispatch {best_d!r} excites {best_count} agents > 1 mHz"
    if best_count >= 2:
        return _verdict(
            VERDICT_PASS,
            evidence,
            reason_codes=["EVIDENCE_OK"],
            best_dispatch=best_d,
            max_agents_responding=best_count,
        )
    return _verdict(
        VERDICT_REJECT,
        evidence,
        reason_codes=["THRESHOLD_NOT_MET"],
        best_dispatch=best_d,
        max_agents_responding=best_count,
    )


def _g2_measurement(snap: dict[str, Any]) -> dict[str, Any]:
    early = _early_phase_check(snap, key="phase3_open_loop", pretty="phase3_open_loop")
    if early is not None:
        return early

    p3 = snap.get("phase3_open_loop") or {}
    # Required fields for verdict computation.
    required = ("n_distinct_sha256", "n_agents", "all_sha256_distinct")
    missing = [f for f in required if f not in p3]
    if missing:
        return _verdict(
            VERDICT_PENDING,
            f"phase3_open_loop missing required fields: {missing}",
            reason_codes=["MISSING_FIELD"],
        )

    n_distinct = int(p3["n_distinct_sha256"])
    n_agents = int(p3["n_agents"])
    distinct = bool(p3["all_sha256_distinct"])
    evidence = f"open-loop omega sha256: {n_distinct}/{n_agents} distinct"
    if distinct and n_agents > 1:
        return _verdict(
            VERDICT_PASS,
            evidence,
            reason_codes=["EVIDENCE_OK"],
            n_distinct=n_distinct,
            n_agents=n_agents,
        )
    return _verdict(
        VERDICT_REJECT,
        evidence,
        reason_codes=["THRESHOLD_NOT_MET"],
        n_distinct=n_distinct,
        n_agents=n_agents,
    )


def _g3_gradient(snap: dict[str, Any]) -> dict[str, Any]:
    early = _early_phase_check(snap, key="phase4_per_dispatch", pretty="phase4_per_dispatch")
    if early is not None:
        return early

    dispatches = _phase4_data_dispatches(snap)
    if not dispatches:
        return _verdict(
            VERDICT_PENDING,
            "phase4_per_dispatch present but no data-bearing dispatches",
            reason_codes=["EMPTY_DATA"],
        )

    # Distinguish "field missing" from "field present but empty list".
    missing_field = [d_type for d_type, d in dispatches.items() if "r_f_local_share" not in d]
    if missing_field:
        return _verdict(
            VERDICT_PENDING,
            (
                f"r_f_local_share missing in {len(missing_field)} dispatch(es): "
                f"{missing_field[:3]}{'...' if len(missing_field) > 3 else ''}"
            ),
            reason_codes=["MISSING_FIELD"],
        )

    results = []
    any_pass = False
    n_with_data = 0
    for d_type, d in dispatches.items():
        share = list(d.get("r_f_local_share", []) or [])
        if not share:
            results.append({"dispatch": d_type, "skipped": "no share data"})
            continue
        n_with_data += 1
        mean_share = sum(share) / len(share)
        diff = max(share) - min(share)
        threshold = (
            probe_config.THRESHOLDS.g3_share_diff_rel * abs(mean_share)
            if mean_share != 0
            else 0.0
        )
        passes = (diff > threshold) and (diff > 0)
        results.append(
            {
                "dispatch": d_type,
                "mean_share": mean_share,
                "max_min_diff": diff,
                "threshold": threshold,
                "passes": passes,
            }
        )
        any_pass = any_pass or passes

    if n_with_data == 0:
        # All dispatches had empty share lists — distinct from REJECT.
        return _verdict(
            VERDICT_PENDING,
            f"all {len(dispatches)} dispatches have empty r_f_local_share",
            reason_codes=["EMPTY_DATA"],
            per_dispatch=results,
        )

    evidence = (
        f"{sum(1 for r in results if r.get('passes'))} of "
        f"{n_with_data} dispatches show non-degenerate per-agent share gradient"
    )
    if any_pass:
        return _verdict(
            VERDICT_PASS,
            evidence,
            reason_codes=["EVIDENCE_OK"],
            per_dispatch=results,
        )
    return _verdict(
        VERDICT_REJECT,
        evidence,
        reason_codes=["THRESHOLD_NOT_MET"],
        per_dispatch=results,
    )


def _g4_position(snap: dict[str, Any]) -> dict[str, Any]:
    """Different dispatch sites should produce different mode-shape signatures.

    Phase A simplification: signature = sorted set of agent indices whose
    max|Δf| exceeds the response threshold. PASS if ≥ 2 distinct
    signatures observed across dispatches.
    """
    early = _early_phase_check(snap, key="phase4_per_dispatch", pretty="phase4_per_dispatch")
    if early is not None:
        return early

    dispatches = _phase4_data_dispatches(snap)
    if not dispatches:
        return _verdict(
            VERDICT_PENDING,
            "phase4_per_dispatch present but no data-bearing dispatches",
            reason_codes=["EMPTY_DATA"],
        )
    if len(dispatches) < 2:
        return _verdict(
            VERDICT_PENDING,
            f"need ≥ 2 dispatches with data, got {len(dispatches)}",
            reason_codes=["INSUFFICIENT_DISPATCHES"],
        )

    # Distinguish "field missing" from "field present but empty list".
    missing_field = [
        d_type
        for d_type, d in dispatches.items()
        if "max_abs_f_dev_hz_per_agent" not in d
    ]
    if missing_field:
        return _verdict(
            VERDICT_PENDING,
            (
                f"max_abs_f_dev_hz_per_agent missing in "
                f"{len(missing_field)} dispatch(es): "
                f"{missing_field[:3]}{'...' if len(missing_field) > 3 else ''}"
            ),
            reason_codes=["MISSING_FIELD"],
        )

    # G4 uses g4_position_hz (0.10 Hz default) NOT g1_respond_hz (1mHz).
    # At 1mHz in v3 Discrete EMT, all agents always respond → signature collapse →
    # spurious G4 REJECT. 0.10 Hz buckets agents by physical proximity to disturbance.
    # Wired 2026-05-04 (P1-1 follow-up to P2 D1).
    floor = probe_config.THRESHOLDS.g4_position_hz

    signatures: dict[str, tuple[int, ...]] = {}
    for d_type, d in dispatches.items():
        per_agent_max = list(d.get("max_abs_f_dev_hz_per_agent", []) or [])
        responding = tuple(i for i, v in enumerate(per_agent_max) if v > floor)
        signatures[d_type] = responding

    distinct = set(signatures.values())
    evidence = (
        f"{len(distinct)} distinct responder signatures across "
        f"{len(signatures)} dispatches"
    )
    if len(distinct) >= 2:
        return _verdict(
            VERDICT_PASS,
            evidence,
            reason_codes=["EVIDENCE_OK"],
            signatures={k: list(v) for k, v in signatures.items()},
        )
    return _verdict(
        VERDICT_REJECT,
        evidence,
        reason_codes=["THRESHOLD_NOT_MET"],
        signatures={k: list(v) for k, v in signatures.items()},
    )


def _g5_trace(snap: dict[str, Any]) -> dict[str, Any]:
    """Per-agent omega-std should differ across agents in some dispatch.

    PASS if any phase 3 or phase 4 std-diff exceeds the noise floor
    (sourced from ``probe_config.THRESHOLDS``).
    """
    noise_floor = probe_config.THRESHOLDS.g5_noise_floor_pu
    candidates: list[tuple[str, float]] = []

    p3, p3_status = _phase_status(snap, "phase3_open_loop")
    if p3_status == _STATUS_PRESENT and p3 is not None:
        if "std_diff_max_min_pu" in p3:
            candidates.append(
                ("phase3_open_loop", float(p3["std_diff_max_min_pu"]))
            )

    p4_payload, p4_status = _phase_status(snap, "phase4_per_dispatch")
    for d_type, d in _phase4_data_dispatches(snap).items():
        per_agent = d.get("per_agent", []) or []
        stds = [float(a.get("std_omega_pu_post_settle", 0.0)) for a in per_agent]
        if stds:
            candidates.append((d_type, max(stds) - min(stds)))

    # If both upstream phases errored, surface ERROR (not PENDING).
    if p3_status == _STATUS_ERRORED and p4_status == _STATUS_ERRORED:
        return _verdict(
            VERDICT_ERROR,
            "both phase3 and phase4 errored",
            reason_codes=["PHASE_ERRORED"],
        )

    if not candidates:
        # No std data at all. If a phase was errored, prefer ERROR; else PENDING.
        if p3_status == _STATUS_ERRORED or p4_status == _STATUS_ERRORED:
            return _verdict(
                VERDICT_ERROR,
                "no phase data with std (an upstream phase errored)",
                reason_codes=["PHASE_ERRORED"],
            )
        return _verdict(
            VERDICT_PENDING,
            "no phase data with std",
            reason_codes=["MISSING_PHASE"],
        )

    best_label, best_diff = max(candidates, key=lambda kv: kv[1])
    evidence = f"largest std-diff = {best_diff:.3e} pu in {best_label!r}"
    if best_diff > noise_floor:
        return _verdict(
            VERDICT_PASS,
            evidence,
            reason_codes=["EVIDENCE_OK"],
            best_diff_pu=best_diff,
            best_source=best_label,
            noise_floor=noise_floor,
        )
    return _verdict(
        VERDICT_REJECT,
        evidence,
        reason_codes=["THRESHOLD_NOT_MET"],
        best_diff_pu=best_diff,
        best_source=best_label,
        noise_floor=noise_floor,
    )


# ---------------------------------------------------------------------------
# G6 — composite (Phase B partial + Phase C R1)
# ---------------------------------------------------------------------------


def _g6_partial(snap: dict[str, Any]) -> dict[str, Any]:
    """Phase B G6 partial — trained policy must use ≥ K agents AND beat zero_all.

    Reads phase5_trained_policy. Errored phase ⇒ ERROR; missing fields ⇒
    PENDING; everything-present-but-threshold-not-met ⇒ REJECT.
    """
    early = _early_phase_check(snap, key="phase5_trained_policy", pretty="phase5_trained_policy")
    if early is not None:
        return early

    p5 = snap.get("phase5_trained_policy") or {}
    runs = p5.get("runs", {}) or {}
    baseline = runs.get("baseline") or {}
    zero_all = runs.get("zero_all") or {}
    diffs = p5.get("ablation_diffs") or []
    contribs = p5.get("agent_contributes") or []
    K = int(p5.get("k_required_contributors", 2))
    improve_tol = float(p5.get("improve_tol_sys_pu_sq", 0.5))

    # Errored sub-runs ⇒ surface as ERROR (subprocess pipeline failure).
    if "error" in baseline or "error" in zero_all:
        return _verdict(
            VERDICT_ERROR,
            (
                f"baseline.error={'error' in baseline}, "
                f"zero_all.error={'error' in zero_all}"
            ),
            reason_codes=["EVAL_FAILED"],
        )
    if "r_f_global" not in baseline or "r_f_global" not in zero_all:
        return _verdict(
            VERDICT_PENDING,
            "baseline / zero_all missing r_f_global",
            reason_codes=["MISSING_FIELD"],
        )

    contributors = sum(1 for c in contribs if c is True)
    base_rf = float(baseline["r_f_global"])
    zero_all_rf = float(zero_all["r_f_global"])
    improvement = base_rf - zero_all_rf  # >0 means baseline better
    beats_zero_all = improvement > improve_tol

    pass_cond = (contributors >= K) and beats_zero_all
    evidence = (
        f"contributors={contributors}/{K} K-required; "
        f"baseline.r_f_global={base_rf:+.3f} vs "
        f"zero_all.r_f_global={zero_all_rf:+.3f} "
        f"(Δ={improvement:+.3f} vs IMPROVE_TOL={improve_tol})"
    )
    extras = {
        "contributors": contributors,
        "K_required": K,
        "baseline_r_f_global": base_rf,
        "zero_all_r_f_global": zero_all_rf,
        "improvement_sys_pu_sq": improvement,
        "ablation_diffs": diffs,
    }
    if pass_cond:
        return _verdict(
            VERDICT_PASS, evidence, reason_codes=["EVIDENCE_OK"], **extras
        )
    return _verdict(
        VERDICT_REJECT, evidence, reason_codes=["THRESHOLD_NOT_MET"], **extras
    )


def _g6_trained_policy(snap: dict[str, Any]) -> dict[str, Any]:
    """G6 — composite verdict (Phase B partial + Phase C R1 if available).

    Composition rules:
    - phase6 missing ⇒ G6 = G6_partial (Phase B-only scope).
    - phase6 errored ⇒ G6 = ERROR + PHASE_ERRORED (R1 layer broke;
      partial verdict preserved in extras for inspection).
    - phase6 present + R1 absent ⇒ G6 = G6_partial.
    - any sub-verdict ERROR ⇒ G6 = ERROR.
    - any sub-verdict PENDING (and no ERROR) ⇒ G6 = PENDING.
    - any sub-verdict REJECT (and no ERROR/PENDING) ⇒ G6 = REJECT.
    - both PASS ⇒ G6 = PASS.
    """
    partial = _g6_partial(snap)

    p6, p6_status = _phase_status(snap, "phase6_causality")
    if p6_status == _STATUS_ERRORED:
        err_msg = (snap.get("phase6_causality") or {}).get("error", "<unknown>")
        out = _verdict(
            VERDICT_ERROR,
            f"phase6_causality errored: {err_msg}",
            reason_codes=["PHASE_ERRORED"],
            scope="g6_complete",
            g6_partial=partial,
            r1=None,
        )
        return out
    if p6_status == _STATUS_MISSING:
        # Phase B-only scope; preserve full partial verdict + tag scope.
        out = dict(partial)
        out["scope"] = "g6_partial_only"
        out["g6_partial"] = partial
        out["r1"] = None
        return out

    # phase6 present — look for R1 sub-verdict.
    r1 = (p6 or {}).get("r1_verdict")
    if not isinstance(r1, dict):
        # No R1 layer despite phase6 present — treat like Phase B-only scope.
        out = dict(partial)
        out["scope"] = "g6_partial_only"
        out["g6_partial"] = partial
        out["r1"] = None
        return out

    r1_verdict = r1.get("verdict", VERDICT_PENDING)
    partial_verdict = partial.get("verdict", VERDICT_PENDING)
    r1_codes = list(r1.get("reason_codes", []) or [])
    partial_codes = list(partial.get("reason_codes", []) or [])

    # Composition precedence: ERROR > PENDING > REJECT > PASS.
    if r1_verdict == VERDICT_ERROR or partial_verdict == VERDICT_ERROR:
        out_v = VERDICT_ERROR
    elif r1_verdict == VERDICT_PENDING or partial_verdict == VERDICT_PENDING:
        out_v = VERDICT_PENDING
    elif r1_verdict == VERDICT_REJECT or partial_verdict == VERDICT_REJECT:
        out_v = VERDICT_REJECT
    else:
        out_v = VERDICT_PASS

    # Composite reason_codes = union of contributing codes; default to a
    # single class-appropriate code if both sides somehow lack codes
    # (legacy defensive — inputs from this module always carry codes).
    composite_codes = sorted(set(r1_codes) | set(partial_codes))
    if not composite_codes:
        if out_v == VERDICT_PASS:
            composite_codes = ["EVIDENCE_OK"]
        elif out_v == VERDICT_REJECT:
            composite_codes = ["THRESHOLD_NOT_MET"]
        elif out_v == VERDICT_PENDING:
            composite_codes = ["MISSING_PHASE"]
        else:
            composite_codes = ["PHASE_ERRORED"]

    evidence = (
        f"G6_partial={partial_verdict}, R1={r1_verdict}; "
        f"partial: {partial.get('evidence')}; r1: {r1.get('evidence')}"
    )
    return _verdict(
        out_v,
        evidence,
        reason_codes=composite_codes,
        scope="g6_complete",
        g6_partial=partial,
        r1=r1,
    )
