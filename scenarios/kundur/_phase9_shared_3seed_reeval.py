"""Phase 9 — Re-eval 3-seed × 500ep shared-param SAC under paper-faithful conditions.

Bug context
-----------
_phase9_shared_param_sac_full.py:145 originally set comm_fail_prob=0.0 in
evaluate_paper_grade(), mismatching the training condition (comm_fail_prob=0.1
at _phase9_shared_param_sac.py:81). This produced eval_paper_grade.json files
that reflect a counterfactual evaluation condition. Fixed in script on 2026-05-04;
see audit 2026-05-04_andes_ddic_eval_discrepancy_verdict.md §8.

This script:
  - Loads agent_shared_final.pt for seeds 42, 43, 44
  - Runs 50 fixed test episodes (seeds 20000..20049) with
    AndesMultiVSGEnv(random_disturbance=True)  — default comm_fail_prob=0.1
  - Computes per-ep cum_rf, mean, std, max_df, osc
  - Saves eval_paper_grade_v2.json (does NOT overwrite eval_paper_grade.json)
  - Reports 3-seed aggregate with bootstrap CI (n_resample=1000, seed=7919)

Run
---
  wsl bash -c 'cd /mnt/c/Users/27443/Desktop/Multi-Agent  VSGs && \
    source ~/andes_venv/bin/activate && \
    python3 scenarios/kundur/_phase9_shared_3seed_reeval.py'
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np
import torch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from env.andes.andes_vsg_env import AndesMultiVSGEnv
from agents.sac import SACAgent
from evaluation.metrics import _bootstrap_ci
import config as cfg


SEEDS = [42, 43, 44]
FIXED_TEST_SEEDS = [20000 + i for i in range(50)]
BOOTSTRAP_SEED = 7919   # matches paper-grade convention
N_RESAMPLE = 1000

# DDIC and adaptive references (CLAIM — from stored eval JSONs, paper-grade)
DDIC_3SEED_MEAN_TOTAL = -1.156   # results/andes_eval_paper_grade/per_seed_summary.json
DDIC_3SEED_PER_EP = -0.02313     # 3-seed 150-ep pooled mean
DDIC_CI_LO = -0.02591
DDIC_CI_HI = -0.02064
ADAPTIVE_PER_EP = -0.02120       # K=10/400
ADAPTIVE_CI_LO = -0.02640
ADAPTIVE_CI_HI = -0.01632


def rollout_one(env: AndesMultiVSGEnv, get_action) -> dict:
    """Run 1 episode. Returns cum_rf_global, max_df, osc."""
    obs = env.reset()
    N = AndesMultiVSGEnv.N_AGENTS
    cum_rf = 0.0
    max_df = 0.0
    osc = 0.0
    for _step in range(AndesMultiVSGEnv.STEPS_PER_EPISODE):
        actions = get_action(obs)
        obs, _, done, info = env.step(actions)
        f = info["freq_hz"]
        f_bar = float(np.mean(f))
        cum_rf -= float(np.sum((f - f_bar) ** 2))
        max_df = max(max_df, info["max_freq_deviation_hz"])
        raw = info.get("raw_signals", {})
        osc = max(osc, raw.get("d_omega_global_spread", 0.0))
        if done:
            break
    return {"cum_rf_global": cum_rf, "max_df": max_df, "osc": osc}


def eval_one_seed(train_seed: int) -> dict:
    save_dir = os.path.join(
        ROOT, "results", "andes_phase9_shared_seed%d_500ep" % train_seed
    )
    final_path = os.path.join(save_dir, "agent_shared_final.pt")
    if not os.path.exists(final_path):
        raise FileNotFoundError("Checkpoint not found: %s" % final_path)

    shared_agent = SACAgent(
        obs_dim=AndesMultiVSGEnv.OBS_DIM,
        action_dim=2,
        hidden_sizes=cfg.HIDDEN_SIZES,
        lr=cfg.LR,
        gamma=cfg.GAMMA,
        tau=cfg.TAU_SOFT,
        buffer_size=cfg.BUFFER_SIZE,
        batch_size=cfg.BATCH_SIZE,
    )
    shared_agent.load(final_path)
    N = AndesMultiVSGEnv.N_AGENTS

    def get_action(obs: dict) -> dict:
        return {
            i: shared_agent.select_action(obs[i], deterministic=True)
            for i in range(N)
        }

    print("--- seed%d paper-grade eval (comm_fail_prob=0.1, %d eps) ---" % (train_seed, len(FIXED_TEST_SEEDS)))
    episodes: list[dict] = []
    t0 = time.time()

    for ts in FIXED_TEST_SEEDS:
        # Use env default comm_fail_prob=0.1 to match training; see audit 2026-05-04
        env = AndesMultiVSGEnv(random_disturbance=True)
        env.seed(ts)
        try:
            r = rollout_one(env, get_action)
        except Exception as exc:
            print("  test_seed %d FAILED: %s" % (ts, exc))
            continue
        episodes.append({"seed": ts, **r})

    if not episodes:
        raise RuntimeError("All paper-grade eval episodes failed for seed%d" % train_seed)

    cum_rfs = [e["cum_rf_global"] for e in episodes]
    mdfs = [e["max_df"] for e in episodes]
    oscs = [e["osc"] for e in episodes]

    cum_rf_mean = float(np.mean(cum_rfs))
    cum_rf_std = float(np.std(cum_rfs, ddof=1))
    max_df_mean = float(np.mean(mdfs))
    osc_mean = float(np.mean(oscs))
    fail_rate = float(sum(1 for x in mdfs if x > 0.5) / max(len(mdfs), 1))
    wall_s = time.time() - t0

    ci = _bootstrap_ci(cum_rfs, n_resample=N_RESAMPLE, seed=BOOTSTRAP_SEED)

    print(
        "  cum_rf_mean/ep=%.4f  std=%.4f  CI=[%.4f,%.4f]  max_df=%.4f  osc=%.4f  fail%%=%.1f  wall=%.0fs"
        % (cum_rf_mean, cum_rf_std, ci["ci_lo"], ci["ci_hi"], max_df_mean, osc_mean, fail_rate * 100, wall_s)
    )

    result = {
        "controller": "shared_param_sac_seed%d_500ep_v2" % train_seed,
        "eval_version": "v2",
        "eval_comm_fail_prob": "0.1 (env default, matches training)",
        "bug_note": (
            "v1 eval_paper_grade.json used comm_fail_prob=0.0 (mismatching training). "
            "This v2 uses env default (0.1). See audit 2026-05-04_andes_ddic_eval_discrepancy_verdict.md §8."
        ),
        "train_seed": train_seed,
        "n_test_eps": len(episodes),
        "cum_rf_mean": cum_rf_mean,
        "cum_rf_std": cum_rf_std,
        "cum_rfs": cum_rfs,
        "bootstrap_ci": ci,
        "max_df_mean": max_df_mean,
        "osc_mean": osc_mean,
        "fail_rate_max_df_gt_05": fail_rate,
        "wall_s": wall_s,
        "episodes": episodes,
    }
    out_path = os.path.join(save_dir, "eval_paper_grade_v2.json")
    with open(out_path, "w") as fout:
        json.dump(result, fout, indent=2)
    print("  Saved: %s" % out_path)
    return result


def main() -> None:
    print("=" * 70)
    print(" Phase 9 Shared-Param SAC — 3-seed re-eval (comm_fail_prob=0.1)")
    print("=" * 70)

    all_results: list[dict] = []
    for s in SEEDS:
        res = eval_one_seed(s)
        all_results.append(res)
        print()

    # Aggregate
    per_ep_means = [r["cum_rf_mean"] for r in all_results]
    totals = [r["cum_rf_mean"] * r["n_test_eps"] for r in all_results]
    three_seed_mean_total = float(np.mean(totals))
    three_seed_total_std = float(np.std(totals, ddof=1))
    three_seed_per_ep_mean = float(np.mean(per_ep_means))

    # Pool all 150 per-ep cum_rf values for bootstrap CI
    all_cum_rfs: list[float] = []
    for r in all_results:
        all_cum_rfs.extend(r["cum_rfs"])
    pooled_ci = _bootstrap_ci(all_cum_rfs, n_resample=N_RESAMPLE, seed=BOOTSTRAP_SEED)

    # vs DDIC 3-seed mean total (-1.156) — [CLAIM: from paper-grade eval]
    delta_vs_ddic = three_seed_mean_total - DDIC_3SEED_MEAN_TOTAL
    pct_vs_ddic = delta_vs_ddic / abs(DDIC_3SEED_MEAN_TOTAL) * 100.0

    # vs Adaptive K=10/400 per-ep mean (-0.02120) — [CLAIM]
    delta_vs_adap_per_ep = three_seed_per_ep_mean - ADAPTIVE_PER_EP
    pct_vs_adap_per_ep = delta_vs_adap_per_ep / abs(ADAPTIVE_PER_EP) * 100.0

    # Bootstrap CI overlap test vs DDIC and adaptive
    # DDIC 150-ep pooled CI: [-0.02591, -0.02064]
    # Adaptive 50-ep CI:     [-0.02640, -0.01632]
    shared_lo = pooled_ci["ci_lo"]
    shared_hi = pooled_ci["ci_hi"]

    ddic_overlap = (shared_lo <= DDIC_CI_HI) and (DDIC_CI_LO <= shared_hi)
    adap_overlap = (shared_lo <= ADAPTIVE_CI_HI) and (ADAPTIVE_CI_LO <= shared_hi)

    # Verdict logic
    if abs(pct_vs_ddic) <= 10.0 and ddic_overlap:
        verdict = "DECORATIVE_CONFIRMED"
    elif pct_vs_ddic < -10.0 and not ddic_overlap:
        verdict = "SHARED_WORSE"
    elif pct_vs_ddic > 10.0:
        verdict = "SHARED_BETTER"
    else:
        verdict = "TIED"

    summary = {
        "n_seeds": len(SEEDS),
        "n_eps_per_seed": 50,
        "n_eps_total": len(all_cum_rfs),
        "eval_comm_fail_prob": "0.1 (env default, matches training)",
        "per_seed": [
            {
                "seed": all_results[i]["train_seed"],
                "cum_rf_mean_per_ep": all_results[i]["cum_rf_mean"],
                "cum_rf_std": all_results[i]["cum_rf_std"],
                "ci": all_results[i]["bootstrap_ci"],
            }
            for i in range(len(all_results))
        ],
        "three_seed_mean_total": three_seed_mean_total,
        "three_seed_total_std_n1": three_seed_total_std,
        "three_seed_per_ep_mean": three_seed_per_ep_mean,
        "pooled_150ep_bootstrap_ci": pooled_ci,
        "vs_ddic_3seed_mean_total": {
            "ddic_value": DDIC_3SEED_MEAN_TOTAL,
            "delta": delta_vs_ddic,
            "pct": pct_vs_ddic,
            "ci_overlap": ddic_overlap,
            "ddic_ci": [DDIC_CI_LO, DDIC_CI_HI],
        },
        "vs_adaptive_per_ep": {
            "adaptive_value": ADAPTIVE_PER_EP,
            "delta_per_ep": delta_vs_adap_per_ep,
            "pct": pct_vs_adap_per_ep,
            "ci_overlap": adap_overlap,
            "adaptive_ci": [ADAPTIVE_CI_LO, ADAPTIVE_CI_HI],
        },
        "verdict": verdict,
        "fact_note": (
            "DDIC/adaptive reference values are CLAIM from stored eval JSONs. "
            "See quality_reports/audits/2026-05-04_andes_ddic_eval_discrepancy_verdict.md."
        ),
    }

    out_path = os.path.join(ROOT, "results", "phase9_shared_3seed_reeval_summary.json")
    with open(out_path, "w") as fout:
        json.dump(summary, fout, indent=2)

    print("=" * 70)
    print(" 3-SEED AGGREGATE SUMMARY (comm_fail_prob=0.1)")
    print("=" * 70)
    for r in all_results:
        ci = r["bootstrap_ci"]
        print(
            "  seed%d: cum_rf/ep=%.4f  50-ep CI=[%.4f,%.4f]"
            % (r["train_seed"], r["cum_rf_mean"], ci["ci_lo"], ci["ci_hi"])
        )
    print("")
    print("  3-seed mean total    : %.4f" % three_seed_mean_total)
    print("  3-seed total std(n-1): %.4f" % three_seed_total_std)
    print("  3-seed per-ep mean   : %.4f" % three_seed_per_ep_mean)
    print("  150-ep bootstrap CI  : [%.4f, %.4f]" % (shared_lo, shared_hi))
    print("")
    print("  vs DDIC 3-seed mean total (%.4f): %+.1f%%  CI overlap=%s" % (DDIC_3SEED_MEAN_TOTAL, pct_vs_ddic, ddic_overlap))
    print("  vs Adaptive per-ep (%.4f):        %+.1f%%  CI overlap=%s" % (ADAPTIVE_PER_EP, pct_vs_adap_per_ep, adap_overlap))
    print("")
    print("  VERDICT: %s" % verdict)
    print("=" * 70)
    print("  Saved: %s" % out_path)


if __name__ == "__main__":
    main()
