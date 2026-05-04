"""Agent state probe — verdict logic.

A1 specialization, A2 ablation, A3 failure.
Returns: dict mapping gate_id → {"verdict", "reason_codes", "evidence"}.
"""
from __future__ import annotations

from probes.kundur.agent_state.probe_config import ProbeThresholds


def compute_gates(snapshot: dict, thresholds: ProbeThresholds) -> dict:
    gates = {}

    # ── A1: specialization ──
    p1 = snapshot.get("phase_a1_specialization")
    if p1 and "error" not in p1:
        cos = p1.get("offdiag_cos_mean", 1.0)
        if cos < thresholds.a1_specialized_max_cos:
            verdict = "PASS"
            codes = ["A1_SPECIALIZED"]
        elif cos > thresholds.a1_homogeneous_min_cos:
            verdict = "REJECT"
            codes = ["A1_HOMOGENEOUS"]
        else:
            verdict = "PENDING"
            codes = ["A1_INTERMEDIATE"]
        gates["A1"] = {
            "verdict": verdict,
            "reason_codes": codes,
            "evidence": {
                "offdiag_cos_mean": cos,
                "thresholds": {
                    "specialized_max": thresholds.a1_specialized_max_cos,
                    "homogeneous_min": thresholds.a1_homogeneous_min_cos,
                },
            },
        }
    else:
        gates["A1"] = {"verdict": "ERROR", "reason_codes": ["A1_PHASE_NOT_RUN"], "evidence": {}}

    # ── A2: ablation ──
    p2 = snapshot.get("phase_a2_ablation")
    if p2 and "error" not in p2:
        per_agent = p2.get("per_agent_ablation", [])
        shares = [r["share"] for r in per_agent]
        if shares:
            min_share = min(shares)
            max_share = max(shares)
            if min_share < thresholds.a2_freerider_max_share:
                verdict = "REJECT"
                codes = ["A2_FREERIDER_DETECTED"]
            elif max_share / max(min_share, 1e-12) > 4.0:
                verdict = "PENDING"
                codes = ["A2_IMBALANCED_CONTRIBUTION"]
            else:
                verdict = "PASS"
                codes = ["A2_BALANCED_CONTRIBUTION"]
            gates["A2"] = {
                "verdict": verdict,
                "reason_codes": codes,
                "evidence": {
                    "min_share": min_share,
                    "max_share": max_share,
                    "shares": shares,
                    "freerider_threshold": thresholds.a2_freerider_max_share,
                },
            }
        else:
            gates["A2"] = {"verdict": "ERROR", "reason_codes": ["A2_NO_DATA"], "evidence": {}}
    else:
        gates["A2"] = {"verdict": "ERROR", "reason_codes": ["A2_PHASE_NOT_RUN"], "evidence": {}}

    # ── A3: failure pattern ──
    p3 = snapshot.get("phase_a3_failure")
    if p3 and "error" not in p3:
        codes = []
        if p3.get("clustered_by_bus"):
            codes.append("A3_CLUSTERED_BUS")
        if p3.get("clustered_by_sign"):
            codes.append("A3_CLUSTERED_SIGN")
        worstk_mag = p3.get("worstk_magnitude_median_pu", 0)
        overall_mag = p3.get("overall_magnitude_median_pu", 1)
        if worstk_mag > 1.5 * overall_mag:
            codes.append("A3_HIGH_MAGNITUDE_FAILURES")
        # If no pattern detected, the failures are scattered
        if not codes:
            codes.append("A3_SCATTERED_FAILURES")
            verdict = "PASS"  # PASS = no actionable cluster
        else:
            verdict = "REJECT"  # REJECT = pattern detected, actionable
        gates["A3"] = {
            "verdict": verdict,
            "reason_codes": codes,
            "evidence": {
                "worstk_most_common_bus": p3.get("worstk_most_common_bus"),
                "worstk_most_common_bus_count": p3.get("worstk_most_common_bus_count"),
                "worstk_magnitude_median_pu": worstk_mag,
                "overall_magnitude_median_pu": overall_mag,
                "n_over_threshold": p3.get("n_over_threshold"),
            },
        }
    else:
        gates["A3"] = {"verdict": "ERROR", "reason_codes": ["A3_PHASE_NOT_RUN"], "evidence": {}}

    return gates
