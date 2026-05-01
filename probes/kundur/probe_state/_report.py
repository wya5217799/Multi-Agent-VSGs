# FACT: report writers serialise the snapshot dict; output content is
# whatever the snapshot contains. CLAIM = anything narrative this module
# adds (header text, table descriptions).
"""Phase 6 — JSON snapshot + Markdown human-readable report."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

VERDICT_GLYPH = {
    "PASS": "✅",
    "REJECT": "❌",
    "PENDING": "⏳",
}


def write(snapshot: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%S")
    json_path = output_dir / f"state_snapshot_{ts}.json"
    md_path = output_dir / f"STATE_REPORT_{ts}.md"

    json_path.write_text(
        json.dumps(snapshot, indent=2, default=_json_default, ensure_ascii=False),
        encoding="utf-8",
    )
    md_path.write_text(_render_md(snapshot, ts), encoding="utf-8")

    # Also write a stable "latest" alias for tests + downstream consumers.
    latest_json = output_dir / "state_snapshot_latest.json"
    latest_md = output_dir / "STATE_REPORT_latest.md"
    latest_json.write_text(
        json.dumps(snapshot, indent=2, default=_json_default, ensure_ascii=False),
        encoding="utf-8",
    )
    latest_md.write_text(_render_md(snapshot, ts), encoding="utf-8")

    return {
        "json": json_path,
        "md": md_path,
        "latest_json": latest_json,
        "latest_md": latest_md,
    }


def _json_default(obj: Any) -> Any:
    """Coerce non-serialisable values (numpy / pathlib / etc.) for JSON dump."""
    try:
        import numpy as np

        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.generic):
            return obj.item()
    except ImportError:
        pass
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"non-serialisable {type(obj).__name__}: {obj!r}")


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _render_md(snap: dict[str, Any], ts: str) -> str:
    lines: list[str] = []
    lines.append(f"# Kundur CVS Model State Report — {ts}")
    lines.append("")
    lines.append(
        "> CLAIM: this is a derived view of `state_snapshot_{ts}.json`. "
        "FACT = the JSON. Cite the JSON path + this timestamp when "
        "referencing values from this report."
    )
    lines.append("")
    lines.append(f"- schema_version: `{snap.get('schema_version')}`")
    lines.append(f"- git_head: `{snap.get('git_head')}`")
    lines.append(f"- timestamp: `{snap.get('timestamp')}`")

    cfg = snap.get("config", {}) or {}
    if cfg:
        lines.append(
            f"- probe config: dispatch_mag={cfg.get('dispatch_magnitude_sys_pu')}, "
            f"sim_duration={cfg.get('sim_duration_s')} s"
        )

    lines.append("")
    lines.append("## Falsification Gates (Phase A: G1-G5; Phase B: G6)")
    lines.append("")
    lines.append("| Gate | Verdict | Evidence |")
    lines.append("|------|---------|----------|")
    gates = snap.get("falsification_gates", {}) or {}
    # Sorted iteration so future gates (G7, G8, ...) appear automatically
    # in alphabetical order. Gn names sort lexicographically ⇒ same order
    # as numeric.
    for gname in sorted(gates.keys()):
        g = gates.get(gname, {}) or {}
        verdict = g.get("verdict", "PENDING")
        glyph = VERDICT_GLYPH.get(verdict, "?")
        evidence = g.get("evidence", "—")
        lines.append(f"| {gname} | {glyph} `{verdict}` | {evidence} |")

    lines.append("")
    lines.append("## Phase 1 — Static Topology")
    p1 = snap.get("phase1_topology", {}) or {}
    if "error" in p1:
        lines.append(f"- ❌ Phase 1 errored: `{p1['error']}`")
    elif not p1:
        lines.append("- ⏳ Phase 1 not run")
    else:
        lines.append(f"- model: `{p1.get('model_name')}` "
                     f"(profile path: `{p1.get('model_profile_path')}`)")
        lines.append(
            f"- topology variant: `{p1.get('topology_variant')}`"
        )
        lines.append(
            f"- counts: ESS={p1.get('n_ess')}, SG={p1.get('n_sg')}, "
            f"wind={p1.get('n_wind')}"
        )
        lines.append(f"- ESS bus map: `{p1.get('ess_bus_map')}`")
        lines.append(
            f"- dispatch total = {p1.get('dispatch_total')}, "
            f"effective = {len(p1.get('dispatch_effective', []))}"
        )
        if p1.get("dispatch_effective"):
            lines.append(
                "- effective dispatches: "
                + ", ".join(f"`{d}`" for d in p1["dispatch_effective"])
            )
        if p1.get("dispatch_name_valid_only"):
            lines.append(
                "- name-valid only (NOT effective): "
                + ", ".join(f"`{d}`" for d in p1["dispatch_name_valid_only"])
            )
        matlab = p1.get("matlab", {}) or {}
        if matlab.get("matlab_unavailable"):
            lines.append(
                f"- ⚠️ MATLAB unavailable for dynamic discovery: "
                f"`{matlab.get('reason')}`"
            )
        else:
            lines.append(
                f"- powergui mode: `{matlab.get('powergui_mode')}`"
            )
            lines.append(
                f"- W_omega_ blocks (build-script naming): "
                f"ESS={matlab.get('omega_tw_count_ess')}, "
                f"SG={matlab.get('omega_tw_count_sg')}, "
                f"Wind={matlab.get('omega_tw_count_wind')}"
            )
            solver = matlab.get("solver", {}) or {}
            if solver:
                lines.append("- solver/sim:")
                for k, v in solver.items():
                    lines.append(f"  - {k}: `{v}`")
        for warn in p1.get("consistency_warnings", []) or []:
            lines.append(f"- ⚠️ {warn}")
        cfg = p1.get("config", {}) or {}
        if cfg:
            lines.append(
                f"- φ: PHI_F={cfg.get('phi_f')}, PHI_H={cfg.get('phi_h')}, "
                f"PHI_D={cfg.get('phi_d')} | DIST=[{cfg.get('dist_min_sys_pu')}, "
                f"{cfg.get('dist_max_sys_pu')}] sys-pu"
            )
            lines.append(
                f"- M0={cfg.get('vsg_m0')}, D0={cfg.get('vsg_d0')}, "
                f"DM=[{cfg.get('dm_min')}, {cfg.get('dm_max')}], "
                f"DD=[{cfg.get('dd_min')}, {cfg.get('dd_max')}]"
            )

    lines.append("")
    lines.append("## Phase 2 — NR / Initial Conditions")
    p2 = snap.get("phase2_nr_ic", {}) or {}
    if "error" in p2:
        lines.append(f"- ❌ Phase 2 errored: `{p2['error']}`")
    elif not p2:
        lines.append("- ⏳ Phase 2 not run")
    else:
        lines.append(
            f"- ic file: `{p2.get('ic_path')}` "
            f"(schema_version={p2.get('schema_version')}, "
            f"hash={p2.get('source_hash')})"
        )
        lines.append(f"- topology variant: `{p2.get('topology_variant')}`")
        lines.append(
            f"- vsg_pm0_pu: {_short_list(p2.get('vsg_pm0_pu', []))}"
        )
        lines.append(
            f"- sg_pm0_sys_pu: {_short_list(p2.get('sg_pm0_sys_pu', []))}"
        )
        lines.append(
            f"- no_hidden_slack: `{p2.get('no_hidden_slack')}` "
            f"(invariants checked: {p2.get('physical_invariants_checked')})"
        )
        lines.append(
            f"- balance dump: load={float(p2.get('p_load_total_sys_pu', 0.0)):.4f}, "
            f"gen={float(p2.get('p_gen_paper_sys_pu', 0.0)):.4f}, "
            f"wind={float(p2.get('p_wind_paper_sys_pu', 0.0)):.4f}, "
            f"ess={float(p2.get('p_ess_total_sys_pu', 0.0)):.4f}, "
            f"loss={float(p2.get('p_loss_sys_pu', 0.0)):.4f}, "
            f"sum={float(p2.get('global_balance_sum_sys_pu', 0.0)):.4f}"
        )

    lines.append("")
    lines.append("## Phase 3 — Open-Loop (no disturbance)")
    p3 = snap.get("phase3_open_loop", {}) or {}
    if "error" in p3:
        lines.append(f"- ❌ Phase 3 errored: `{p3['error']}`")
    elif not p3:
        lines.append("- ⏳ Phase 3 not run")
    else:
        lines.append(
            f"- ran {p3.get('n_steps')} steps × DT={p3.get('dt_control_s')}s "
            f"× n_agents={p3.get('n_agents')} (mag = {p3.get('magnitude_sys_pu')})"
        )
        lines.append(
            f"- all_sha256_distinct: `{p3.get('all_sha256_distinct')}` "
            f"({p3.get('n_distinct_sha256')}/{p3.get('n_agents')})"
        )
        lines.append(
            f"- std diff (max-min) post-settle: "
            f"{float(p3.get('std_diff_max_min_pu', 0.0)):.3e} pu"
        )
        lines.append("")
        lines.append("| agent | mean ω (pu) | std post-2s (pu) | max\\|Δf\\| (Hz) | sha256(omega) |")
        lines.append("|-------|-------------|------------------|------------------|----------------|")
        for a in p3.get("per_agent", []):
            lines.append(
                f"| {a['idx']} | {a['mean_omega_pu']:.6f} "
                f"| {a['std_omega_pu_post_settle']:.3e} "
                f"| {a['max_abs_f_dev_hz']:.4f} "
                f"| `{a['sha256_omega'][:16]}…` |"
            )

    lines.append("")
    p4 = snap.get("phase4_per_dispatch", {}) or {}
    p4_default_mag = p4.get("probe_default_magnitude_sys_pu")
    lines.append(
        f"## Phase 4 — Per-Dispatch "
        f"(probe-default mag = {p4_default_mag}, per-dispatch may override)"
    )
    if "error" in p4:
        lines.append(f"- ❌ Phase 4 errored: `{p4['error']}`")
    elif not p4:
        lines.append("- ⏳ Phase 4 not run")
    else:
        if p4.get("warning"):
            lines.append(f"- ⚠️ {p4['warning']}")
        if p4.get("skipped_unrecognised"):
            lines.append(
                f"- skipped (not in env valid set): "
                f"{p4['skipped_unrecognised']}"
            )
        if p4.get("metadata_missing_dispatches"):
            lines.append(
                f"- ⚠️ metadata missing for: "
                f"{p4['metadata_missing_dispatches']}"
            )
        dispatches = p4.get("dispatches", {}) or {}
        if dispatches:
            lines.append("")
            lines.append(
                "| dispatch | family | mag | agents>1mHz | max\\|Δf\\| Hz | "
                "expected≥ Hz | floor | r_f Δ |"
            )
            lines.append(
                "|----------|--------|-----|-------------|----------------|"
                "----------------|-------|--------|"
            )
            n_below_floor = 0
            for d_type, d in dispatches.items():
                md = d.get("metadata", {}) or {}
                family = md.get("family", "—")
                mag = d.get("applied_magnitude_sys_pu", "—")
                if "error" in d and "agents_responding_above_1mHz" not in d:
                    lines.append(
                        f"| `{d_type}` | {family} | {mag} "
                        f"| ❌ {d['error']} | — | — | — | — |"
                    )
                    continue
                exp = d.get("expected_min_df_hz")
                exp_str = f"{exp:.4f}" if exp is not None else "—"
                fs = d.get("floor_status", "—")
                fs_glyph = {
                    "ok": "✅",
                    "below_expected_floor": "⚠️ below",
                    "above_expected_ceiling": "⚠️ above",
                    "expected_floor_unknown": "❓ unknown",
                }.get(fs, fs)
                if fs in ("below_expected_floor", "above_expected_ceiling"):
                    n_below_floor += 1
                lines.append(
                    f"| `{d_type}` | {family} | {mag} "
                    f"| {d.get('agents_responding_above_1mHz')} "
                    f"| {d.get('max_abs_f_dev_hz_global', 0):.4f} "
                    f"| {exp_str} | {fs_glyph} "
                    f"| {d.get('r_f_share_max_min_diff', 0):.3e} |"
                )
            if n_below_floor:
                lines.append("")
                lines.append(
                    f"⚠️ {n_below_floor} dispatch(es) outside expected band "
                    "(below floor or above ceiling) — possible model "
                    "degradation, runaway divergence, or build drift; see "
                    "`historical_source` per-dispatch for the verdict that "
                    "set the bounds."
                )

    # Phase 5 — trained policy ablation (Phase B)
    lines.append("")
    p5 = snap.get("phase5_trained_policy", {}) or {}
    p5_mode = p5.get("mode")
    lines.append(f"## Phase 5 — Trained Policy Ablation (mode={p5_mode})")
    if "error" in p5:
        lines.append(f"- ❌ Phase 5 errored: `{p5['error']}`")
    elif not p5:
        lines.append("- ⏳ Phase 5 not run")
    else:
        lines.append(
            f"- checkpoint: `{p5.get('checkpoint_path')}` "
            f"(strategy={p5.get('checkpoint_match_strategy')}, "
            f"mtime={p5.get('checkpoint_mtime')})"
        )
        lines.append(
            f"- scenario_set={p5.get('scenario_set')}, "
            f"n_scenarios={p5.get('n_scenarios')}, "
            f"disturbance_mode={p5.get('disturbance_mode')}, "
            f"n_agents={p5.get('n_agents')}"
        )
        lines.append(
            f"- thresholds: K={p5.get('k_required_contributors')}, "
            f"NOISE={p5.get('noise_threshold_sys_pu_sq')}, "
            f"IMPROVE_TOL={p5.get('improve_tol_sys_pu_sq')}"
        )
        runs = p5.get("runs", {}) or {}
        if runs:
            lines.append("")
            lines.append("| run | r_f_global | r_h_global | r_d_global | n_ep | wall (s) | error |")
            lines.append("|-----|------------|------------|------------|------|----------|-------|")
            for label, r in runs.items():
                if "error" in r:
                    lines.append(
                        f"| `{label}` | — | — | — | — | — | ❌ {r['error']} |"
                    )
                    continue
                lines.append(
                    f"| `{label}` | "
                    f"{float(r.get('r_f_global', 0.0)):+.3f} | "
                    f"{float(r.get('r_h_global', 0.0)):+.3f} | "
                    f"{float(r.get('r_d_global', 0.0)):+.3f} | "
                    f"{r.get('n_episodes', '—')} | "
                    f"{float(r.get('wall_s', 0.0)):.1f} | — |"
                )
        diffs = p5.get("ablation_diffs") or []
        contribs = p5.get("agent_contributes") or []
        if diffs:
            lines.append("")
            lines.append("**Ablation diffs** (zero_agent_i.r_f - baseline.r_f; <0 ⇒ i contributes):")
            lines.append("")
            lines.append("| agent | diff | contributes |")
            lines.append("|-------|------|-------------|")
            for i, (d, c) in enumerate(zip(diffs, contribs)):
                d_s = "—" if d is None else f"{d:+.3f}"
                c_s = "—" if c is None else ("✅" if c else "—")
                lines.append(f"| {i} | {d_s} | {c_s} |")
        share = p5.get("rf_rh_rd_share")
        if share:
            lines.append("")
            lines.append(
                f"**Reward share** (baseline): rf={share.get('rf', 0):.3f}, "
                f"rh={share.get('rh', 0):.3f}, rd={share.get('rd', 0):.3f}"
            )

    # Phase 6 — causality short-train (Phase C)
    lines.append("")
    p6 = snap.get("phase6_causality", {}) or {}
    lines.append(
        f"## Phase 6 — Causality Short-Train (mode={p6.get('mode')}, "
        f"R1 ablation={p6.get('ablation_config')})"
    )
    if "error" in p6:
        lines.append(f"- ❌ Phase 6 errored: `{p6['error']}`")
    elif not p6:
        lines.append("- ⏳ Phase 6 not run")
    else:
        lines.append(
            f"- run_id: `{p6.get('run_id')}` (run_dir: `{p6.get('run_dir')}`)"
        )
        lines.append(
            f"- phi_used: f={p6.get('phi_f_used')}, h={p6.get('phi_h_used')}, "
            f"d={p6.get('phi_d_used')} | episodes_planned={p6.get('episodes_planned')} "
            f"completed={p6.get('episodes_completed')}"
        )
        lines.append(
            f"- baseline_source: `{p6.get('baseline_source')}`; "
            f"IMPROVE_TOL_R1={p6.get('improve_tol_r1_sys_pu_sq')}"
        )
        lines.append(
            f"- wall: train={float(p6.get('wall_train_s', 0.0)):.1f}s, "
            f"eval={float(p6.get('wall_eval_s', 0.0)):.1f}s"
        )
        baseline_eval = p6.get("baseline_eval") or {}
        no_rf_eval = p6.get("no_rf_eval") or {}
        lines.append("")
        lines.append("| run | r_f_global | r_h_global | r_d_global | error |")
        lines.append("|-----|------------|------------|------------|-------|")
        for label, run in (("baseline", baseline_eval), ("no_rf", no_rf_eval)):
            if not run:
                lines.append(f"| `{label}` | — | — | — | not available |")
                continue
            if "error" in run:
                lines.append(f"| `{label}` | — | — | — | ❌ {run['error']} |")
                continue
            lines.append(
                f"| `{label}` | "
                f"{float(run.get('r_f_global', 0.0)):+.3f} | "
                f"{float(run.get('r_h_global', 0.0)):+.3f} | "
                f"{float(run.get('r_d_global', 0.0)):+.3f} | — |"
            )
        r1 = p6.get("r1_verdict") or {}
        if r1:
            glyph = VERDICT_GLYPH.get(r1.get("verdict", "PENDING"), "?")
            lines.append("")
            lines.append(
                f"**R1 verdict**: {glyph} `{r1.get('verdict')}` — {r1.get('evidence')}"
            )
        per_run_errors = p6.get("errors") or []
        if per_run_errors:
            lines.append("")
            lines.append("**Phase 6 sub-errors**:")
            for e in per_run_errors:
                lines.append(f"- `{e.get('phase')}`: {e.get('error')}")

    errors = snap.get("errors", []) or []
    if errors:
        lines.append("")
        lines.append("## Errors")
        for e in errors:
            lines.append(f"- `{e.get('phase')}`: {e.get('error')}")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "Plans: `quality_reports/plans/2026-04-30_probe_state_kundur_cvs.md` "
        "(Phase A) + `quality_reports/plans/2026-05-01_probe_state_phase_B.md` "
        "(Phase B). Phases C/D deferred."
    )
    return "\n".join(lines) + "\n"


def _short_list(values: list, n: int = 6) -> str:
    if not values:
        return "[]"
    if len(values) <= n:
        return "[" + ", ".join(f"{v:.4f}" for v in values) + "]"
    head = ", ".join(f"{v:.4f}" for v in values[:n])
    return f"[{head}, … (+{len(values) - n} more)]"
