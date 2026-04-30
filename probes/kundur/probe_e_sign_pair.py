"""Probe E sign-pair experiment driver — Option E CCS at Bus 7/9 load centers.

Runs paper_eval twice — same load-center bus, magnitude +mag and -mag — under
the LoadStepCcsLoadCenter dispatch (Option E). Designed to falsify whether
the network-side CCS at the paper-Fig.3 load centers produces a per-agent
frequency signal strong enough to support RL training.

Hypotheses (plan §5):

  H_E_strong : at least one agent shows (|nadir_diff| + |peak_diff|) > 0.05 Hz
               between +mag and -mag runs → Option E unblocks signal, proceed
               with retrain.

  H_E_marginal : at least one agent shows the diff in [0.01, 0.05) Hz → signal
                 is detectable but weak; document and stop unless DIST_MAX
                 sweep proves promising.

  H_E_abort : all 4 agents diff < 0.01 Hz → CCS at Bus 7/9 also weak,
              electrically distant or solver-attenuated → ABORT Option E.

Usage:
    python probes/kundur/probe_e_sign_pair.py [--bus 7|9] [--mag 0.5]

Output (under results/harness/kundur/cvs_v3_option_e_smoke/):
    manifest_pos_b{N}.json     manifest_neg_b{N}.json
    probe_e_pos_b{N}.json      probe_e_neg_b{N}.json
    *_stdout.log               *_stderr.log
    probe_e_verdict_b{N}.md    (PASS / MARGINAL / ABORT verdict)

Exit code:
    0 = PASS / MARGINAL (downstream proceeds; verdict text distinguishes)
    1 = ABORT (all agents under noise floor; downstream stops)
    2 = usage error
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
OUT_DIR = REPO_ROOT / "results/harness/kundur/cvs_v3_option_e_smoke"

# Option E plan §5 acceptance thresholds (Hz, per-agent
# |nadir_diff| + |peak_diff| between +mag and -mag runs).
PASS_HZ = 0.05      # at least 1 agent above this -> Option E PASS
ABORT_HZ = 0.01     # all agents below this -> Option E ABORT


def write_manifest(path: Path, bus: int, magnitude: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "name": f"probe_e_b{bus}_mag{magnitude:+.2f}",
        "n_scenarios": 1,
        "seed_base": 42,
        "disturbance_mode": "ccs_load",
        "dist_min_sys_pu": abs(magnitude),
        "dist_max_sys_pu": abs(magnitude),
        "bus_choices": [bus],
        "scenarios": [{
            "scenario_idx": 0,
            "disturbance_kind": "ccs_load",
            "target": bus,
            "magnitude_sys_pu": magnitude,
            "comm_failed_links": [],
        }],
    }
    with path.open("w") as f:
        json.dump(manifest, f, indent=2)


def run_eval(manifest_path: Path, output_json: Path, label: str,
             env_disturbance_type: str, dist_max: float) -> int:
    env = os.environ.copy()
    env["KUNDUR_DISTURBANCE_TYPE"] = env_disturbance_type
    # DIST_MAX must accommodate |mag| (absorbed into manifest dist_max_sys_pu
    # too, but env layer reads the env var as well).
    env["KUNDUR_DIST_MAX"] = f"{dist_max:.4f}"
    env.pop("KUNDUR_PHI_H", None)
    env.pop("KUNDUR_PHI_D", None)
    env.pop("KUNDUR_ALLOW_LEGACY_PROFILE", None)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [
        PY, "-m", "evaluation.paper_eval",
        "--disturbance-mode", "ccs_load",
        "--scenario-set", "test",
        "--scenario-set-path", str(manifest_path),
        "--policy-label", label,
        "--output-json", str(output_json),
    ]
    log_dir = output_json.parent
    out = (log_dir / f"{label}_stdout.log").open("w")
    err = (log_dir / f"{label}_stderr.log").open("w")
    print(f"[probe_e] launching {label}: {' '.join(cmd)}")
    rc = subprocess.call(cmd, cwd=str(REPO_ROOT), env=env, stdout=out, stderr=err)
    out.close()
    err.close()
    print(f"[probe_e] {label} exit={rc}")
    return rc


def diff_runs(pos_json: Path, neg_json: Path, verdict_md: Path,
              bus: int, mag: float) -> int:
    p = json.load(pos_json.open())
    n = json.load(neg_json.open())
    p_e = p["per_episode_metrics"][0]
    n_e = n["per_episode_metrics"][0]

    pos_nadir = p_e.get("nadir_hz_per_agent", [])
    neg_nadir = n_e.get("nadir_hz_per_agent", [])
    pos_peak = p_e.get("peak_hz_per_agent", [])
    neg_peak = n_e.get("peak_hz_per_agent", [])

    notes = [
        f"bus = {bus}, |mag| = {mag:.3f}",
        f"pos_nadir = {pos_nadir}",
        f"neg_nadir = {neg_nadir}",
        f"pos_peak = {pos_peak}",
        f"neg_peak = {neg_peak}",
    ]

    diffs: list[float] = []
    if pos_nadir and neg_nadir:
        for i in range(min(len(pos_nadir), len(neg_nadir))):
            d = abs(pos_nadir[i] - neg_nadir[i]) + abs(pos_peak[i] - neg_peak[i])
            diffs.append(d)
        notes.append(f"per-agent (|nadir_diff|+|peak_diff|) = "
                     f"{[f'{d:.4f}' for d in diffs]} Hz")
        n_pass = sum(1 for d in diffs if d >= PASS_HZ)
        n_marginal = sum(1 for d in diffs if ABORT_HZ <= d < PASS_HZ)
        n_abort = sum(1 for d in diffs if d < ABORT_HZ)
        notes.append(f"agents PASS (>= {PASS_HZ:.3f} Hz) = {n_pass}/4")
        notes.append(f"agents MARGINAL ([{ABORT_HZ:.3f}, {PASS_HZ:.3f}) Hz) = "
                     f"{n_marginal}/4")
        notes.append(f"agents under noise floor (< {ABORT_HZ:.3f} Hz) = "
                     f"{n_abort}/4")
    else:
        notes.append("WARN: per-agent nadir/peak missing — paper_eval may have "
                     "failed; check stderr logs")

    # Verdict logic
    max_diff = max(diffs) if diffs else 0.0
    if max_diff >= PASS_HZ:
        verdict = "PASS"
        body = (
            f"At least 1 agent shows (|nadir_diff|+|peak_diff|) >= "
            f"{PASS_HZ:.3f} Hz between +{mag:.2f} and -{mag:.2f} runs. "
            f"max per-agent diff = {max_diff:.4f} Hz. Option E unblocks the "
            f"per-agent frequency signal; proceed with retrain (plan Step 6)."
        )
        rc = 0
    elif max_diff >= ABORT_HZ:
        verdict = "MARGINAL"
        body = (
            f"All 4 agents have diff in [{ABORT_HZ:.3f}, {PASS_HZ:.3f}) Hz "
            f"(max = {max_diff:.4f}). Signal is detectable but weak. "
            f"Recommend either DIST_MAX increase to amplify, OR document "
            f"and stop. Do NOT spend 70 min on retrain without first "
            f"sweeping DIST_MAX."
        )
        rc = 0
    else:
        verdict = "ABORT"
        body = (
            f"All 4 agents have diff < {ABORT_HZ:.3f} Hz (max = "
            f"{max_diff:.4f}). CCS at Bus {bus} produces noise-floor signal "
            f"even at the paper-Fig.3 load center. Option E ABORT — "
            f"either electrical attenuation (admittance) or Phasor solver "
            f"phase mismatch is killing the disturbance. F4 v3 +18% "
            f"remains the project ceiling under current architecture."
        )
        rc = 1

    verdict_lines = [
        f"# Probe E sign-pair verdict — Option E CCS at Bus {bus}",
        "",
        f"**Generated:** {pos_json.name} vs {neg_json.name}",
        f"**Bus:** {bus}",
        f"**|mag|:** {mag:.3f} sys-pu",
        f"**Thresholds:** PASS >= {PASS_HZ:.3f} Hz, ABORT < {ABORT_HZ:.3f} Hz",
        "",
        "## Falsification matrix",
        "",
        "| Hypothesis | Status | Evidence |",
        "|---|---|---|",
        f"| H_E_strong (>= 1 agent diff >= {PASS_HZ:.3f} Hz) | "
        f"{'PASS' if max_diff >= PASS_HZ else 'FAIL'} | max diff = "
        f"{max_diff:.4f} Hz |",
        f"| H_E_marginal (>= 1 agent diff in [{ABORT_HZ:.3f}, {PASS_HZ:.3f})) | "
        f"{'PASS' if (ABORT_HZ <= max_diff < PASS_HZ) else 'N/A'} | see "
        f"per-agent diffs below |",
        f"| H_E_abort (all agents diff < {ABORT_HZ:.3f}) | "
        f"{'PASS (-> abort Option E)' if max_diff < ABORT_HZ else 'FAIL'} | "
        f"max diff = {max_diff:.4f} Hz |",
        "",
        "## Raw evidence",
        "",
        "```",
        *notes,
        "```",
        "",
        "## Verdict",
        "",
        f"**STOP-VERDICT: {verdict}** — {body}",
    ]
    verdict_md.write_text("\n".join(verdict_lines), encoding="utf-8")
    print(f"[probe_e] verdict written: {verdict_md}  status={verdict}")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bus", type=int, default=7, choices=[7, 9])
    ap.add_argument("--mag", type=float, default=0.5)
    args = ap.parse_args()

    bus = args.bus
    mag = float(args.mag)
    env_dt = f"loadstep_paper_ccs_bus{bus}"
    # Need DIST_MAX >= |mag| so env doesn't clip
    dist_max = max(3.0, abs(mag))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pos_man = OUT_DIR / f"manifest_pos_b{bus}.json"
    neg_man = OUT_DIR / f"manifest_neg_b{bus}.json"
    write_manifest(pos_man, bus, +mag)
    write_manifest(neg_man, bus, -mag)

    pos_out = OUT_DIR / f"probe_e_pos_b{bus}.json"
    neg_out = OUT_DIR / f"probe_e_neg_b{bus}.json"
    label_pos = f"probe_e_pos_b{bus}"
    label_neg = f"probe_e_neg_b{bus}"

    rc = run_eval(pos_man, pos_out, label_pos, env_dt, dist_max)
    if rc != 0:
        print("ERROR: probe_e_pos failed; aborting")
        return rc
    rc = run_eval(neg_man, neg_out, label_neg, env_dt, dist_max)
    if rc != 0:
        print("ERROR: probe_e_neg failed; aborting")
        return rc

    verdict_path = OUT_DIR / f"probe_e_verdict_b{bus}.md"
    return diff_runs(pos_out, neg_out, verdict_path, bus, mag)


if __name__ == "__main__":
    sys.exit(main())
