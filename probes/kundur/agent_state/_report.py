"""Render snapshot → JSON file + Markdown report."""
from __future__ import annotations

import json
import os
import time


def write_snapshot(snapshot: dict, out_dir: str, run_id: str | None = None) -> tuple[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    if run_id is None:
        run_id = time.strftime("%Y%m%dT%H%M%S")
    json_path = os.path.join(out_dir, f"agent_state_{run_id}.json")
    md_path = os.path.join(out_dir, f"AGENT_STATE_REPORT_{run_id}.md")
    with open(json_path, "w") as f:
        json.dump(snapshot, f, indent=2, default=str)
    with open(md_path, "w") as f:
        f.write(_render_md(snapshot))
    return json_path, md_path


def _render_md(s: dict) -> str:
    out = []
    out.append("# Agent State Probe Report\n")
    out.append(f"- timestamp: {s.get('timestamp', 'n/a')}")
    out.append(f"- schema_version: {s.get('schema_version')}")
    out.append(f"- implementation_version: {s.get('implementation_version')}")
    out.append(f"- ckpt_dir: `{s.get('ckpt_dir', 'n/a')}`")
    out.append(f"- ckpt_kind: {s.get('ckpt_kind', 'n/a')}\n")

    out.append("## Verdicts (A1-A3)\n")
    out.append("| Gate | Verdict | Reason codes |")
    out.append("|---|---|---|")
    gates = s.get("falsification_gates", {})
    for gid in ("A1", "A2", "A3"):
        g = gates.get(gid, {})
        codes = ", ".join(g.get("reason_codes", []))
        out.append(f"| {gid} | {g.get('verdict', '?')} | {codes} |")
    out.append("")

    # Phase A1
    p1 = s.get("phase_a1_specialization")
    if p1 and "error" not in p1:
        out.append("## A1 — Specialization\n")
        out.append(f"- offdiag cosine mean: **{p1['offdiag_cos_mean']:.4f}** (max {p1['offdiag_cos_max']:.4f}, min {p1['offdiag_cos_min']:.4f})")
        out.append(f"- n_obs samples: {p1['n_obs_samples']}\n")
        out.append("Pairwise cosine matrix:\n```")
        for row in p1["pairwise_cos_matrix"]:
            out.append("  " + "  ".join(f"{v:>+.3f}" for v in row))
        out.append("```\n")
        out.append("Per-agent action stats (synthetic obs):")
        out.append("| agent | a0 (ΔM) μ | a0 σ | a1 (ΔD) μ | a1 σ |")
        out.append("|---|---|---|---|---|")
        for r in p1["per_agent_action_stats"]:
            out.append(f"| {r['agent']} | {r['a0_mean']:>+.3f} | {r['a0_std']:.3f} | {r['a1_mean']:>+.3f} | {r['a1_std']:.3f} |")
        out.append("")

    # Phase A2
    p2 = s.get("phase_a2_ablation")
    if p2 and "error" not in p2:
        out.append("## A2 — Ablation\n")
        out.append(f"- baseline cum_rf: **{p2['baseline_cum_rf']:.4f}** ({p2['n_eval_eps']} eps)\n")
        out.append("| agent | ablated cum_rf | Δ cum_rf | share |")
        out.append("|---|---|---|---|")
        for r in p2["per_agent_ablation"]:
            out.append(f"| {r['agent']} | {r['ablated_cum_rf']:>9.4f} | {r['delta_cum_rf']:>+8.4f} | {r['share']*100:>5.1f}% |")
        out.append("\n_Δ > 0 = agent contributes; share is normalized contribution._\n")

    # Phase A3
    p3 = s.get("phase_a3_failure")
    if p3 and "error" not in p3:
        out.append("## A3 — Failure Forensics\n")
        out.append(f"- n_episodes: {p3['n_episodes']} (errors: {p3['n_errors']})")
        out.append(f"- max_df overall p50/p95/max: {p3['max_df_overall_p50']:.4f} / {p3['max_df_overall_p95']:.4f} / {p3['max_df_overall_max']:.4f}")
        out.append(f"- n over {p3['threshold_hz']} Hz threshold: {p3['n_over_threshold']}")
        out.append(f"- worst-K most-common bus: **{p3['worstk_most_common_bus']}** ({p3['worstk_most_common_bus_count']} of {len(p3['worst_k'])})")
        out.append(f"- worstk magnitude median (pu): {p3['worstk_magnitude_median_pu']:.3f}  (overall: {p3['overall_magnitude_median_pu']:.3f})")
        out.append(f"- clustered_by_bus: {p3['clustered_by_bus']}, clustered_by_sign: {p3['clustered_by_sign']}\n")
        out.append("Worst K episodes:")
        out.append("| seed | max_df | dist_bus | dist_mag (pu) | sign | spread peak step | action L1 mean |")
        out.append("|---|---|---|---|---|---|---|")
        for r in p3["worst_k"]:
            out.append(f"| {r['seed']} | {r['max_df_hz']:.4f} | {r['dist_bus']} | {r['dist_magnitude_pu']:>+.3f} | {r['dist_sign']:>+d} | {r['spread_peak_step']} | {r['action_l1_mean']:.3f} |")
        out.append("")

    # Errors collected
    if s.get("errors"):
        out.append("## Errors\n")
        for e in s["errors"]:
            out.append(f"- {e}")

    return "\n".join(out) + "\n"
