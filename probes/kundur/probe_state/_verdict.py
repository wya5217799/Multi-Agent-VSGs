# FACT: gate logic = code below; verdicts assigned by this code are FACT
# given the input snapshot. Any narrative about "what gate X means" is
# CLAIM until cross-checked with the gate's own evidence string.
"""Falsification gates G1-G5 for Phase A.

Each gate consumes phase3 + phase4 data and emits one of:
- ``PASS`` — observed evidence rules out the falsification hypothesis
- ``REJECT`` — observed evidence confirms the falsification hypothesis
  (i.e. the gate's claim is broken)
- ``PENDING`` — phase data missing or insufficient

Gate definitions (Phase A subset; G6 deferred to Phase C):

| Gate | Falsification hypothesis | PASS condition |
|------|--------------------------|----------------|
| G1 — signal      | "no dispatch can excite ≥ 2 agents" | ≥ 1 dispatch with ≥ 2 agents responding > 1 mHz |
| G2 — measurement | "all 4 omega traces are aliased"    | open-loop sha256 distinct across agents |
| G3 — gradient    | "per-agent reward share is degenerate" | max-min r_f share > 5% × mean (best dispatch) |
| G4 — position    | "dispatch site doesn't change mode shape" | ≥ 2 dispatches with different responding-agent sets |
| G5 — trace       | "agent omega-std collapses to one number" | std diff across agents > 1e-7 pu in some dispatch |
"""
from __future__ import annotations

from typing import Any

VERDICT_PASS = "PASS"
VERDICT_REJECT = "REJECT"
VERDICT_PENDING = "PENDING"


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
# Helpers
# ---------------------------------------------------------------------------


def _phase3(snap: dict[str, Any]) -> dict[str, Any] | None:
    p = snap.get("phase3_open_loop")
    if not isinstance(p, dict) or "error" in p:
        return None
    return p


def _phase4(snap: dict[str, Any]) -> dict[str, Any] | None:
    p = snap.get("phase4_per_dispatch")
    if not isinstance(p, dict) or "error" in p:
        return None
    return p


def _phase4_dispatches(snap: dict[str, Any]) -> dict[str, Any]:
    """Return only dispatches that have data (filter out per-dispatch errors)."""
    p4 = _phase4(snap)
    if p4 is None:
        return {}
    return {
        k: v
        for k, v in (p4.get("dispatches", {}) or {}).items()
        if isinstance(v, dict) and "error" not in v
    }


def _verdict(verdict: str, evidence: str, **extras: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"verdict": verdict, "evidence": evidence}
    out.update(extras)
    return out


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


def _g1_signal(snap: dict[str, Any]) -> dict[str, Any]:
    dispatches = _phase4_dispatches(snap)
    if not dispatches:
        return _verdict(
            VERDICT_PENDING,
            "phase4_per_dispatch missing or empty",
        )
    best_d = None
    best_count = -1
    for d_type, d in dispatches.items():
        c = int(d.get("agents_responding_above_1mHz", 0))
        if c > best_count:
            best_count = c
            best_d = d_type
    evidence = (
        f"best dispatch {best_d!r} excites {best_count} agents > 1 mHz"
    )
    return _verdict(
        VERDICT_PASS if best_count >= 2 else VERDICT_REJECT,
        evidence,
        best_dispatch=best_d,
        max_agents_responding=best_count,
    )


def _g2_measurement(snap: dict[str, Any]) -> dict[str, Any]:
    p3 = _phase3(snap)
    if p3 is None:
        return _verdict(
            VERDICT_PENDING, "phase3_open_loop missing or errored"
        )
    n_distinct = int(p3.get("n_distinct_sha256", 0))
    n_agents = int(p3.get("n_agents", 0))
    distinct = bool(p3.get("all_sha256_distinct", False))
    evidence = (
        f"open-loop omega sha256: {n_distinct}/{n_agents} distinct"
    )
    return _verdict(
        VERDICT_PASS if distinct and n_agents > 1 else VERDICT_REJECT,
        evidence,
        n_distinct=n_distinct,
        n_agents=n_agents,
    )


def _g3_gradient(snap: dict[str, Any]) -> dict[str, Any]:
    dispatches = _phase4_dispatches(snap)
    if not dispatches:
        return _verdict(
            VERDICT_PENDING,
            "phase4_per_dispatch missing or empty",
        )
    # For each dispatch compute (max-min) of r_f_local_share and check
    # whether it exceeds 5% of the mean share.
    results = []
    any_pass = False
    for d_type, d in dispatches.items():
        share = list(d.get("r_f_local_share", []) or [])
        if not share:
            results.append({"dispatch": d_type, "skipped": "no share data"})
            continue
        from probes.kundur.probe_state.probe_config import THRESHOLDS
        mean_share = sum(share) / len(share)
        diff = max(share) - min(share)
        threshold = THRESHOLDS.g3_share_diff_rel * abs(mean_share) if mean_share != 0 else 0.0
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
    return _verdict(
        VERDICT_PASS if any_pass else VERDICT_REJECT,
        f"{sum(1 for r in results if r.get('passes'))} of {len(results)} dispatches "
        "show non-degenerate per-agent share gradient",
        per_dispatch=results,
    )


def _g4_position(snap: dict[str, Any]) -> dict[str, Any]:
    """Different dispatch sites should produce different mode-shape signatures.

    Phase A simplification: signature = sorted set of agent indices whose
    max|Δf| exceeds the response threshold. PASS if ≥ 2 distinct
    signatures observed across dispatches.
    """
    dispatches = _phase4_dispatches(snap)
    if not dispatches:
        return _verdict(
            VERDICT_PENDING,
            "phase4_per_dispatch missing or empty",
        )
    if len(dispatches) < 2:
        return _verdict(
            VERDICT_PENDING,
            f"need ≥ 2 dispatches with data, got {len(dispatches)}",
        )

    signatures: dict[str, tuple[int, ...]] = {}
    for d_type, d in dispatches.items():
        per_agent_max = list(
            d.get("max_abs_f_dev_hz_per_agent", []) or []
        )
        responding = tuple(
            i for i, v in enumerate(per_agent_max)
            if v > 1e-3  # 1 mHz floor (same as G1)
        )
        signatures[d_type] = responding

    distinct = set(signatures.values())
    evidence = (
        f"{len(distinct)} distinct responder signatures across "
        f"{len(signatures)} dispatches"
    )
    return _verdict(
        VERDICT_PASS if len(distinct) >= 2 else VERDICT_REJECT,
        evidence,
        signatures={k: list(v) for k, v in signatures.items()},
    )


def _phase5(snap: dict[str, Any]) -> dict[str, Any] | None:
    p = snap.get("phase5_trained_policy")
    if not isinstance(p, dict) or "error" in p:
        return None
    return p


def _g6_partial(snap: dict[str, Any]) -> dict[str, Any]:
    """Phase B G6 (partial) — trained policy must use ≥ K agents AND beat zero_all.

    Plan §5 (Phase B). Thresholds K / NOISE / IMPROVE_TOL are sourced from
    the phase5 snapshot itself so they are self-describing in the JSON.
    """
    p5 = _phase5(snap)
    if p5 is None:
        return _verdict(
            VERDICT_PENDING, "phase5_trained_policy missing or errored"
        )
    runs = p5.get("runs", {}) or {}
    baseline = runs.get("baseline") or {}
    zero_all = runs.get("zero_all") or {}
    diffs = p5.get("ablation_diffs") or []
    contribs = p5.get("agent_contributes") or []
    K = int(p5.get("k_required_contributors", 2))
    improve_tol = float(p5.get("improve_tol_sys_pu_sq", 0.5))

    if "error" in baseline or "error" in zero_all:
        return _verdict(
            VERDICT_PENDING,
            f"baseline or zero_all errored "
            f"(baseline={'error' in baseline}, zero_all={'error' in zero_all})",
        )
    if "r_f_global" not in baseline or "r_f_global" not in zero_all:
        return _verdict(
            VERDICT_PENDING,
            "baseline / zero_all missing r_f_global",
        )

    contributors = sum(1 for c in contribs if c is True)
    base_rf = float(baseline["r_f_global"])
    zero_all_rf = float(zero_all["r_f_global"])
    improvement = base_rf - zero_all_rf  # >0 means baseline better (less negative)
    beats_zero_all = improvement > improve_tol

    pass_cond = (contributors >= K) and beats_zero_all
    evidence = (
        f"contributors={contributors}/{K} K-required; "
        f"baseline.r_f_global={base_rf:+.3f} vs "
        f"zero_all.r_f_global={zero_all_rf:+.3f} "
        f"(Δ={improvement:+.3f} vs IMPROVE_TOL={improve_tol})"
    )
    return _verdict(
        VERDICT_PASS if pass_cond else VERDICT_REJECT,
        evidence,
        contributors=contributors,
        K_required=K,
        baseline_r_f_global=base_rf,
        zero_all_r_f_global=zero_all_rf,
        improvement_sys_pu_sq=improvement,
        ablation_diffs=diffs,
    )


def _phase6(snap: dict[str, Any]) -> dict[str, Any] | None:
    p = snap.get("phase6_causality")
    if not isinstance(p, dict) or "error" in p:
        return None
    return p


def _g6_trained_policy(snap: dict[str, Any]) -> dict[str, Any]:
    """G6 — composite verdict (Phase B partial + Phase C R1 if available).

    Behaviour matrix:
    - phase6 absent / errored ⇒ G6 = G6_partial (full Phase B backward compat)
    - phase6 present + R1 PENDING ⇒ G6 PENDING (conservative — matches plan §5
      and CLAUDE.md PAPER-ANCHOR HARD RULE: G1-G6 not all PASS blocks paper
      anchor unlock. Phase B PASS evidence remains accessible via the
      ``g6_partial`` extras field; the composite verdict deliberately does
      NOT silently degrade-to-partial here.)
    - phase6 present + R1 PASS + G6_partial PASS ⇒ G6 完整 PASS
    - phase6 present + (R1 REJECT or G6_partial REJECT) ⇒ G6 REJECT

    R1 PASS — known V1 spurious-vs-healthy ambiguity (see
    ``_causality._compute_r1_verdict`` docstring for detail). G6 PASS
    inherits the same caveat: callers must inspect
    ``r1.improvement_baseline_minus_no_rf`` against
    ``phase5_trained_policy.runs.zero_all.r_f_global`` before treating
    G6 完整 PASS as causal evidence for paper-anchor unlock.
    """
    partial = _g6_partial(snap)
    p6 = _phase6(snap)
    r1 = (p6 or {}).get("r1_verdict")

    if not isinstance(r1, dict):
        # No R1 layer ⇒ keep Phase B G6 verdict (and tag scope so callers
        # know which combination produced this verdict).
        out = dict(partial)
        out["scope"] = "g6_partial_only"
        out["g6_partial"] = partial
        out["r1"] = None
        return out

    r1_verdict = r1.get("verdict", "PENDING")
    partial_verdict = partial.get("verdict", "PENDING")

    if r1_verdict == "PENDING" or partial_verdict == "PENDING":
        out_v = VERDICT_PENDING
    elif r1_verdict == "REJECT" or partial_verdict == "REJECT":
        out_v = VERDICT_REJECT
    else:
        out_v = VERDICT_PASS

    evidence = (
        f"G6_partial={partial_verdict}, R1={r1_verdict}; "
        f"partial: {partial.get('evidence')}; r1: {r1.get('evidence')}"
    )
    return _verdict(
        out_v,
        evidence,
        scope="g6_complete",
        g6_partial=partial,
        r1=r1,
    )


def _g5_trace(snap: dict[str, Any]) -> dict[str, Any]:
    """Per-agent omega-std should differ across agents in some dispatch.

    PASS if any phase 3 or phase 4 std-diff exceeds the noise floor
    (default 1e-7 pu, sourced from ``probe_config.THRESHOLDS``).
    """
    from probes.kundur.probe_state.probe_config import THRESHOLDS
    noise_floor = THRESHOLDS.g5_noise_floor_pu
    candidates: list[tuple[str, float]] = []

    p3 = _phase3(snap)
    if p3 is not None:
        candidates.append(
            ("phase3_open_loop", float(p3.get("std_diff_max_min_pu", 0.0)))
        )

    for d_type, d in _phase4_dispatches(snap).items():
        per_agent = d.get("per_agent", []) or []
        stds = [float(a.get("std_omega_pu_post_settle", 0.0)) for a in per_agent]
        if stds:
            candidates.append((d_type, max(stds) - min(stds)))

    if not candidates:
        return _verdict(VERDICT_PENDING, "no phase data with std")

    best_label, best_diff = max(candidates, key=lambda kv: kv[1])
    return _verdict(
        VERDICT_PASS if best_diff > noise_floor else VERDICT_REJECT,
        f"largest std-diff = {best_diff:.3e} pu in {best_label!r}",
        best_diff_pu=best_diff,
        best_source=best_label,
        noise_floor=noise_floor,
    )
