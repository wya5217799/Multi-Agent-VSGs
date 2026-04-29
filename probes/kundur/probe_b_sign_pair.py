"""Probe B sign-pair experiment driver.

Runs paper_eval twice — same bus, magnitude +0.5 sys-pu and -0.5 sys-pu —
under a LIVE disturbance protocol (NOT dead LoadStep). Designed to falsify:

  H1: 4 ESS omega measurements are not aliased (sha256 differ per agent
      AND across +0.5 / -0.5 runs)
  H2: Per-agent nadir/peak flip sign between +0.5 and -0.5 runs
      (or differ in magnitude in a sign-correlated way)
  H3: Per-agent r_f_local_eta1 is not byte-identical across agents

If H1/H2/H3 fail, the per-agent measurement layer is broken
independent of the disturbance protocol fix already done.

Usage:
    python probes/kundur/probe_b_sign_pair.py [--protocol gen|bus]
                                              [--bus N]
                                              [--mag M]

    --protocol  gen (default) -> SG-side pm_step_proxy_random_gen,
                                  bus must be 1/2/3
                bus -> ESS-side pm_step_proxy_random_bus, bus must be 7/9
    --bus       single bus to test on both runs (default: 2 for gen, 7 for bus)
    --mag       absolute magnitude (default 0.5)

Output:
    Two JSON files in results/harness/kundur/cvs_v3_probe_b/:
      probe_b_pos.json (mag=+M)
      probe_b_neg.json (mag=-M)
    Plus a probe_b_verdict.md summarizing H1/H2/H3 falsification status.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PY = "C:/Users/27443/miniconda3/envs/andes_env/python.exe"
OUT_DIR = REPO_ROOT / "results/harness/kundur/cvs_v3_probe_b"


def write_manifest(path: Path, bus: int, magnitude: float, kind: str,
                   protocol_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "name": f"probe_b_{kind}_mag{magnitude:+.2f}",
        "n_scenarios": 1,
        "seed_base": 42,
        "disturbance_mode": kind,
        "dist_min_sys_pu": abs(magnitude),
        "dist_max_sys_pu": abs(magnitude),
        "bus_choices": [bus],
        "scenarios": [{
            "scenario_idx": 0,
            "disturbance_kind": kind,
            "target": bus,
            "magnitude_sys_pu": magnitude,
            "comm_failed_links": [],
        }],
    }
    with path.open("w") as f:
        json.dump(manifest, f, indent=2)


def run_eval(manifest_path: Path, output_json: Path, label: str,
             disturbance_mode: str, env_disturbance_type: str) -> int:
    env = os.environ.copy()
    env["KUNDUR_DISTURBANCE_TYPE"] = env_disturbance_type
    env.pop("KUNDUR_DIST_MAX", None)
    env.pop("KUNDUR_PHI_H", None)
    env.pop("KUNDUR_PHI_D", None)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [
        PY, "-m", "evaluation.paper_eval",
        "--disturbance-mode", disturbance_mode,
        "--scenario-set", "test",
        "--scenario-set-path", str(manifest_path),
        "--policy-label", label,
        "--output-json", str(output_json),
    ]
    log_dir = output_json.parent
    out = (log_dir / f"{label}_stdout.log").open("w")
    err = (log_dir / f"{label}_stderr.log").open("w")
    print(f"[probe_b] launching {label}: {' '.join(cmd)}")
    rc = subprocess.call(cmd, cwd=str(REPO_ROOT), env=env, stdout=out, stderr=err)
    out.close(); err.close()
    print(f"[probe_b] {label} exit={rc}")
    return rc


def diff_runs(pos_json: Path, neg_json: Path, verdict_md: Path) -> int:
    p = json.load(pos_json.open())
    n = json.load(neg_json.open())
    p_e = p["per_episode_metrics"][0]
    n_e = n["per_episode_metrics"][0]

    h1_collapse_within_pos = h1_collapse_within_neg = False
    h1_alias_across = False
    h2_sign_flip_ok = True
    h3_local_distinct = False
    notes = []

    pos_summary = p_e.get("omega_trace_summary_per_agent", [])
    neg_summary = n_e.get("omega_trace_summary_per_agent", [])
    if not pos_summary or not neg_summary:
        notes.append("WARN: omega_trace_summary_per_agent missing — re-run paper_eval with current code")
        h1_collapse_within_pos = True
    else:
        pos_hashes = [s["sha256_16"] for s in pos_summary]
        neg_hashes = [s["sha256_16"] for s in neg_summary]
        h1_collapse_within_pos = len(set(pos_hashes)) < len(pos_hashes)
        h1_collapse_within_neg = len(set(neg_hashes)) < len(neg_hashes)
        h1_alias_across = bool(set(pos_hashes) & set(neg_hashes))
        notes.append(f"pos_hashes = {pos_hashes}")
        notes.append(f"neg_hashes = {neg_hashes}")

    pos_nadir = p_e.get("nadir_hz_per_agent", [])
    neg_nadir = n_e.get("nadir_hz_per_agent", [])
    pos_peak = p_e.get("peak_hz_per_agent", [])
    neg_peak = n_e.get("peak_hz_per_agent", [])
    h2_at_least_one_responds = False
    h4_multi_agent_responds = False
    diffs = []
    if pos_nadir and neg_nadir:
        # H2 (revised 2026-04-30): single-bus disturbance physically can
        # only excite electrically-near agents; expecting all 4 agents to
        # respond is wrong. New H2: at least 1 agent must show
        # |nadir_diff|+|peak_diff| > 1e-3 Hz (i.e. dispatch IS firing).
        # New H4: more than 1 agent should respond (else gradient is
        # degenerate — only 1/4 agents has learning signal).
        diffs = [abs(pos_nadir[i] - neg_nadir[i]) + abs(pos_peak[i] - neg_peak[i])
                 for i in range(min(len(pos_nadir), len(neg_nadir)))]
        h2_at_least_one_responds = any(d > 1e-3 for d in diffs)
        h4_multi_agent_responds = sum(1 for d in diffs if d > 1e-3) > 1
        h2_sign_flip_ok = h2_at_least_one_responds
        notes.append(f"pos_nadir = {pos_nadir}  pos_peak = {pos_peak}")
        notes.append(f"neg_nadir = {neg_nadir}  neg_peak = {neg_peak}")
        notes.append(f"per-agent (|nadir_diff|+|peak_diff|) = {diffs}")
        n_responding = sum(1 for d in diffs if d > 1e-3)
        notes.append(f"agents_responding (|diff| > 1e-3 Hz) = {n_responding}/4")

    pos_rf_local = p_e.get("r_f_local_per_agent_eta1", [])
    neg_rf_local = n_e.get("r_f_local_per_agent_eta1", [])
    if pos_rf_local:
        h3_local_distinct = (max(pos_rf_local) - min(pos_rf_local)) > 1e-9
        notes.append(f"pos_r_f_local_eta1 = {pos_rf_local}")
        notes.append(f"neg_r_f_local_eta1 = {neg_rf_local}")

    verdict_lines = [
        "# Probe B sign-pair experiment verdict",
        "",
        f"**Generated:** {pos_json.name} vs {neg_json.name}",
        "",
        "## Falsification matrix",
        "",
        "| Hypothesis | Status | Evidence |",
        "|---|---|---|",
        f"| **H1** within-run distinct sha256 (4 agents) | "
        f"{'FAIL (collapsed)' if h1_collapse_within_pos or h1_collapse_within_neg else 'PASS (4 distinct)'} | "
        f"see hash list below |",
        f"| **H1b** cross-run no aliased hash | "
        f"{'FAIL (some agent identical between +mag/-mag)' if h1_alias_across else 'PASS (no shared hash)'} | "
        f"see hash list |",
        f"| **H2** at least 1 agent responds to mag sign (>1e-3 Hz) | "
        f"{'PASS (dispatch firing)' if h2_at_least_one_responds else 'FAIL (zero response — dispatch may be dead)'} | "
        f"see (|nadir_diff|+|peak_diff|) below |",
        f"| **H3** r_f_local distinct across agents within run | "
        f"{'PASS' if h3_local_distinct else 'FAIL (4 agents collapsed)'} | "
        f"see r_f_local_eta1 below |",
        f"| **H4** more than 1 agent responds (gradient non-degenerate) | "
        f"{'PASS (multiple agents excited)' if h4_multi_agent_responds else 'FAIL (single-agent gradient — DEGENERATE)'} | "
        f"see agents_responding count below |",
        "",
        "## Raw evidence",
        "",
        "```",
        *notes,
        "```",
        "",
        "## Verdict",
        "",
    ]
    measurement_ok = (
        not h1_collapse_within_pos
        and not h1_collapse_within_neg
        and not h1_alias_across
        and h3_local_distinct
        and h2_at_least_one_responds
    )
    if measurement_ok and h4_multi_agent_responds:
        verdict_lines += [
            "**STOP-VERDICT: PASS** — measurement layer separated AND multiple ",
            "agents respond. Network coupling distributes the disturbance ",
            "across the 4 ESS as expected.",
        ]
        rc = 0
    elif measurement_ok and not h4_multi_agent_responds:
        verdict_lines += [
            "**STOP-VERDICT: MEASUREMENT_OK_GRADIENT_DEGENERATE** — measurement ",
            "layer is sound (4 distinct sha256 traces, sign-asymmetric per-agent ",
            "response, distinct r_f_local). However, only 1 agent shows non-",
            "trivial response (>1e-3 Hz) to the disturbance; the other 3 see ",
            "noise-floor signal. This confirms the audit R5 hypothesis: r_f ",
            "gradient is concentrated in 1/4 agents per scenario. 3/4 agents ",
            "have effectively zero learning signal under single-point ",
            "disturbance protocol.",
            "",
            "Implications:",
            "- The earlier loadstep_metrics.json bit-identicality WAS a ",
            "  disturbance-protocol artifact (frozen R-block), not measurement ",
            "  collapse. Measurement layer is exonerated.",
            "- But the 3-of-4 agents see no signal even under live SG-side ",
            "  disturbance. RL improvement claim under this protocol is ",
            "  bounded by the 1 agent that DOES see signal (typically the ",
            "  electrically-nearest ESS to the perturbed gen).",
            "- Multi-point disturbance (Option F = SG-side + multi-point ESS ",
            "  Pm-step) or true network LoadStep (Option E = CCS at Bus 7/9) ",
            "  remain the only known protocols that would excite >1 agent.",
        ]
        rc = 0  # measurement OK = main probe goal achieved
    else:
        verdict_lines += [
            "**STOP-VERDICT: FAIL** — measurement layer shows collapse, alias, ",
            "or zero response. Manual review required of:",
            "  - omega_ts_<i> ToWorkspace block wiring in build_kundur_cvs_v3.m",
            "  - bridge step extraction (slx_helpers/vsg_bridge/slx_step_and_read_cvs.m)",
            "  - whether IntW integrators per ESS are truly independent or share a node",
            "  - whether dispatch path is actually writing to the live workspace var",
        ]
        rc = 1

    verdict_md.write_text("\n".join(verdict_lines), encoding="utf-8")
    print(f"[probe_b] verdict written: {verdict_md}")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", choices=["gen", "bus"], default="gen")
    ap.add_argument("--bus", type=int, default=None)
    ap.add_argument("--mag", type=float, default=0.5)
    args = ap.parse_args()

    if args.protocol == "gen":
        bus = args.bus if args.bus is not None else 2
        if bus not in (1, 2, 3):
            print("ERROR: --protocol gen requires --bus 1/2/3")
            return 2
        kind = "gen"
        env_dt = "pm_step_proxy_random_gen"
    else:
        bus = args.bus if args.bus is not None else 7
        if bus not in (7, 9):
            print("ERROR: --protocol bus requires --bus 7/9")
            return 2
        kind = "bus"
        env_dt = "pm_step_proxy_random_bus"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pos_man = OUT_DIR / f"manifest_pos_{args.protocol}_b{bus}.json"
    neg_man = OUT_DIR / f"manifest_neg_{args.protocol}_b{bus}.json"
    write_manifest(pos_man, bus, +args.mag, kind, env_dt)
    write_manifest(neg_man, bus, -args.mag, kind, env_dt)

    pos_out = OUT_DIR / f"probe_b_pos_{args.protocol}_b{bus}.json"
    neg_out = OUT_DIR / f"probe_b_neg_{args.protocol}_b{bus}.json"
    label_pos = f"probe_b_pos_{args.protocol}_b{bus}"
    label_neg = f"probe_b_neg_{args.protocol}_b{bus}"

    rc = run_eval(pos_man, pos_out, label_pos, args.protocol, env_dt)
    if rc != 0:
        print("ERROR: probe_b_pos failed; aborting")
        return rc
    rc = run_eval(neg_man, neg_out, label_neg, args.protocol, env_dt)
    if rc != 0:
        print("ERROR: probe_b_neg failed; aborting")
        return rc

    verdict_path = OUT_DIR / f"probe_b_verdict_{args.protocol}_b{bus}.md"
    return diff_runs(pos_out, neg_out, verdict_path)


if __name__ == "__main__":
    sys.exit(main())
