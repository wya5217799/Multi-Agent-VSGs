"""Probe B-ESS — direct ESS Pm injection sign-pair, all 4 ES{i}.

Prerequisite for Option F design: verify whether ES2's swing-eq Pm input
channel is electrically responsive AT ALL. The 2026-04-30 Probe B
G1/G2/G3 found ES2 silent under any SG-side disturbance; this probe
isolates whether ES2 dead-ness is (a) network topology (no SG can reach
it) or (b) build-script bug (ES2 swing-eq Pm input not wired correctly).

For each ES{i} ∈ {1,2,3,4} runs 2 single-scenario evals:
  - mag = +0.5 sys-pu via pm_step_single_es{i}
  - mag = -0.5 sys-pu via pm_step_single_es{i}

Decision rule per agent:
  - If ES{i} responds to its own Pm step (|nadir_diff|+|peak_diff| > 1e-3 Hz)
    -> swing-eq Pm channel is LIVE for ES{i}
  - If ES{i} does NOT respond to its own Pm step
    -> build-script bug (Pm step not reaching IntW), needs .slx fix

For Option F design:
  - ES{i} that responds to direct injection -> Option F can target it via
    a multi-point dispatch (e.g. EssPmStepProxy(target_indices=(0,1,3))).
  - ES{i} that does NOT respond -> Option F cannot reach it without .slx fix.
    ES{i} stays as a structural dead agent until physical layer is repaired.

Usage:
    python probes/kundur/probe_b_ess_direct.py [--mag M]
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
OUT_DIR = REPO_ROOT / "results/harness/kundur/cvs_v3_probe_b_ess"


def write_manifest(path: Path, target_es: int, magnitude: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "name": f"probe_b_ess_es{target_es}_mag{magnitude:+.2f}",
        "n_scenarios": 1,
        "seed_base": 42,
        "disturbance_mode": "vsg",
        "dist_min_sys_pu": abs(magnitude),
        "dist_max_sys_pu": abs(magnitude),
        "bus_choices": [target_es],
        "scenarios": [{
            "scenario_idx": 0,
            "disturbance_kind": "vsg",
            "target": target_es,
            "magnitude_sys_pu": magnitude,
            "comm_failed_links": [],
        }],
    }
    with path.open("w") as f:
        json.dump(manifest, f, indent=2)


def run_eval(manifest: Path, output_json: Path, label: str) -> int:
    env = os.environ.copy()
    env["KUNDUR_DISTURBANCE_TYPE"] = "pm_step_single_es1"  # placeholder; mode=vsg overrides
    env.pop("KUNDUR_DIST_MAX", None)
    env.pop("KUNDUR_PHI_H", None)
    env.pop("KUNDUR_PHI_D", None)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [
        PY, "-m", "evaluation.paper_eval",
        "--disturbance-mode", "vsg",
        "--scenario-set", "test",
        "--scenario-set-path", str(manifest),
        "--policy-label", label,
        "--output-json", str(output_json),
    ]
    out = (output_json.parent / f"{label}_stdout.log").open("w")
    err = (output_json.parent / f"{label}_stderr.log").open("w")
    print(f"[probe_b_ess] {label} ...")
    rc = subprocess.call(cmd, cwd=str(REPO_ROOT), env=env, stdout=out, stderr=err)
    out.close(); err.close()
    print(f"[probe_b_ess] {label} exit={rc}")
    return rc


def analyze_es(es: int, mag: float) -> dict:
    pos_p = OUT_DIR / f"probe_b_ess_es{es}_pos.json"
    neg_p = OUT_DIR / f"probe_b_ess_es{es}_neg.json"
    p = json.load(pos_p.open())["per_episode_metrics"][0]
    n = json.load(neg_p.open())["per_episode_metrics"][0]
    pos_n = p["nadir_hz_per_agent"]
    pos_pk = p["peak_hz_per_agent"]
    neg_n = n["nadir_hz_per_agent"]
    neg_pk = n["peak_hz_per_agent"]
    diffs = [abs(pos_n[i] - neg_n[i]) + abs(pos_pk[i] - neg_pk[i]) for i in range(4)]
    own_diff = diffs[es - 1]  # 1-indexed -> 0-indexed
    own_responds = own_diff > 1e-3
    others_max = max(diffs[i] for i in range(4) if i != es - 1)
    return {
        "target_es": es,
        "magnitude": mag,
        "diffs_per_agent": diffs,
        "own_diff_hz": own_diff,
        "own_responds": own_responds,
        "others_max_diff_hz": others_max,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mag", type=float, default=0.5)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rcs = []
    for es in (1, 2, 3, 4):
        for sign, label_sign in ((+1, "pos"), (-1, "neg")):
            mag = sign * args.mag
            man = OUT_DIR / f"manifest_es{es}_{label_sign}.json"
            out = OUT_DIR / f"probe_b_ess_es{es}_{label_sign}.json"
            label = f"probe_b_ess_es{es}_{label_sign}"
            write_manifest(man, es, mag)
            rcs.append(run_eval(man, out, label))

    if any(rc != 0 for rc in rcs):
        print(f"[probe_b_ess] some evals failed: rcs={rcs}")
        return 1

    # Aggregate verdict
    verdict_lines = [
        "# Probe B-ESS verdict — single-ESS direct Pm injection",
        "",
        "**Goal:** verify whether each ES{i}'s swing-eq Pm input channel is",
        "electrically responsive when injected directly (bypassing network mode-shape).",
        "Specifically: is ES2's silence under SG-side a network artifact or build bug?",
        "",
        "## Per-agent direct-injection response",
        "",
        "| target | own_diff (Hz) | own_responds? | others_max (Hz) | verdict |",
        "|---:|---:|---|---:|---|",
    ]
    overall_es2_live = False
    for es in (1, 2, 3, 4):
        r = analyze_es(es, args.mag)
        if es == 2:
            overall_es2_live = r["own_responds"]
        if r["own_responds"]:
            verdict = f"ES{es} swing-eq LIVE"
        else:
            verdict = f"ES{es} swing-eq DEAD (build bug — Pm not reaching IntW)"
        verdict_lines.append(
            f"| ES{es} | {r['own_diff_hz']:.4f} | "
            f"{'YES' if r['own_responds'] else 'NO'} | "
            f"{r['others_max_diff_hz']:.4f} | {verdict} |"
        )
    verdict_lines += [
        "",
        "## Implication for Option F design",
        "",
    ]
    if overall_es2_live:
        verdict_lines += [
            "**ES2 swing-eq is LIVE** under direct injection. ES2 silence under",
            "SG-side (G1/G2/G3) is a NETWORK TOPOLOGY effect, not a build bug.",
            "",
            "Option F can include ES2 in multi-point dispatch via",
            "`EssPmStepProxy(target_indices=(0, 1, 2, 3))` etc. ES2 will receive a",
            "non-zero r_f signal in scenarios where target_indices includes 1.",
        ]
    else:
        verdict_lines += [
            "**ES2 swing-eq is DEAD** even under direct injection. This indicates",
            "a BUILD-SCRIPT BUG: the PM_STEP_AMP[2] workspace var is not actually",
            "wired to ES2's IntW Pm input (or wired with zero gain).",
            "",
            "Option F CANNOT include ES2 without first repairing the .slx wiring.",
            "Recommend: pause Option F design; spawn a build-script audit to find",
            "where ES2 swing-eq Pm injection should be but is not.",
        ]
    verdict_path = OUT_DIR / "PROBE_B_ESS_VERDICT.md"
    verdict_path.write_text("\n".join(verdict_lines), encoding="utf-8")
    print(f"[probe_b_ess] verdict: {verdict_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
