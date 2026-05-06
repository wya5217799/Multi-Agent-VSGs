"""Phase 9 — Re-eval 5-seed × 500ep shared-param SAC under paper-faithful conditions.

Extends `_phase9_shared_3seed_reeval.py` to n=5 (seeds 42..46) per Tier-1
revision T1.1 (Phase 9 sample-size match with Phase 4 DDIC at n=5).

This script:
  - Loads agent_shared_final.pt for seeds 42, 43, 44, 45, 46
  - Runs 50 fixed test episodes (seeds 20000..20049) with
    AndesMultiVSGEnv(random_disturbance=True)  -- default comm_fail_prob=0.1
  - Computes per-ep cum_rf, mean, std, max_df, osc
  - Saves eval_paper_grade_v2.json (overwrites if exists)
  - Reports 5-seed aggregate with bootstrap CI (n_resample=1000, seed=7919)

Run
---
  wsl bash -c 'cd /mnt/c/Users/27443/Desktop/Multi-Agent  VSGs && \\
    source ~/andes_venv/bin/activate && \\
    python3 -u scenarios/kundur/_phase9_shared_5seed_reeval.py'
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np
import torch  # noqa: F401  (imported for SAC backend)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from env.andes.andes_vsg_env import AndesMultiVSGEnv
from agents.sac import SACAgent
from evaluation.metrics import _bootstrap_ci
import config as cfg


SEEDS = [42, 43, 44, 45, 46]
FIXED_TEST_SEEDS = [20000 + i for i in range(50)]
BOOTSTRAP_SEED = 7919   # matches paper-grade convention
N_RESAMPLE = 1000

# DDIC n=5 baseline references (from results/andes_eval_paper_grade/n5_aggregate.json)
DDIC_5SEED_MEAN_TOTAL = -1.1863
DDIC_5SEED_STD = 0.2649
DDIC_5SEED_CI_LO = -1.3932
DDIC_5SEED_CI_HI = -0.9841

# Adaptive K=10/400 per-ep reference
ADAPTIVE_PER_EP = -0.02120
ADAPTIVE_CI_LO = -0.02640
ADAPTIVE_CI_HI = -0.01632


def rollout_one(env: AndesMultiVSGEnv, get_action) -> dict:
    """Run 1 episode. Returns cum_rf_global, max_df, osc."""
    _ = env.reset()
    obs = env.reset()
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

    print("--- seed%d paper-grade eval (comm_fail_prob=0.1, %d eps) ---" % (
        train_seed, len(FIXED_TEST_SEEDS)))
    episodes: list[dict] = []
    t0 = time.time()

    for ts in FIXED_TEST_SEEDS:
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
    cum_rf_total = float(np.sum(cum_rfs))   # 50-ep total = comparable to DDIC per-seed totals
    max_df_mean = float(np.mean(mdfs))
    osc_mean = float(np.mean(oscs))
    fail_rate = float(sum(1 for x in mdfs if x > 0.5) / max(len(mdfs), 1))
    wall_s = time.time() - t0

    ci = _bootstrap_ci(cum_rfs, n_resample=N_RESAMPLE, seed=BOOTSTRAP_SEED)

    print(
        "  cum_rf_mean/ep=%.4f  std=%.4f  CI=[%.4f,%.4f]  "
        "cum_rf_total_50=%.4f  max_df=%.4f  osc=%.4f  fail%%=%.1f  wall=%.0fs"
        % (cum_rf_mean, cum_rf_std, ci["ci_lo"], ci["ci_hi"],
           cum_rf_total, max_df_mean, osc_mean, fail_rate * 100, wall_s)
    )

    result = {
        "controller": "shared_param_sac_seed%d_500ep_v2" % train_seed,
        "eval_version": "v2",
        "eval_comm_fail_prob": "0.1 (env default, matches training)",
        "train_seed": train_seed,
        "n_test_eps": len(episodes),
        "cum_rf_mean": cum_rf_mean,
        "cum_rf_std": cum_rf_std,
        "cum_rf_total_50ep": cum_rf_total,
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
    print(" Phase 9 Shared-Param SAC -- 5-seed re-eval (comm_fail_prob=0.1)")
    print(" Tier-1 revision T1.1: matches Phase 4 DDIC n=5 sample size")
    print("=" * 70)

    all_results: list[dict] = []
    for s in SEEDS:
        res = eval_one_seed(s)
        all_results.append(res)
        print()

    # Per-seed 50-ep totals (directly comparable to DDIC per-seed totals)
    per_seed_totals = [r["cum_rf_total_50ep"] for r in all_results]
    five_seed_mean_total = float(np.mean(per_seed_totals))
    five_seed_total_std = float(np.std(per_seed_totals, ddof=1))

    # Bootstrap CI on the 5 per-seed totals (matches phase4 baseline aggregator method)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    arr = np.array(per_seed_totals)
    boot_means = [float(np.mean(rng.choice(arr, size=len(arr), replace=True)))
                  for _ in range(N_RESAMPLE)]
    seed_total_ci_lo = float(np.percentile(boot_means, 2.5))
    seed_total_ci_hi = float(np.percentile(boot_means, 97.5))

    # Pooled per-ep CI (250 episodes)
    all_cum_rfs: list[float] = []
    for r in all_results:
        all_cum_rfs.extend(r["cum_rfs"])
    pooled_ci = _bootstrap_ci(all_cum_rfs, n_resample=N_RESAMPLE, seed=BOOTSTRAP_SEED)

    # Comparison vs DDIC n=5 (matched n)
    delta_vs_ddic_total = five_seed_mean_total - DDIC_5SEED_MEAN_TOTAL
    pct_vs_ddic_total = delta_vs_ddic_total / abs(DDIC_5SEED_MEAN_TOTAL) * 100.0

    # CI-overlap test on the seed-total bootstrap CI vs DDIC's seed-total CI
    ddic_total_ci = (DDIC_5SEED_CI_LO, DDIC_5SEED_CI_HI)
    shared_total_ci = (seed_total_ci_lo, seed_total_ci_hi)
    ddic_total_overlap = (shared_total_ci[0] <= ddic_total_ci[1]) and \
                         (ddic_total_ci[0] <= shared_total_ci[1])

    # Verdict
    if abs(pct_vs_ddic_total) <= 10.0 and ddic_total_overlap:
        verdict = "DECORATIVE_CONFIRMED_AT_N5"
    elif pct_vs_ddic_total < -10.0 and not ddic_total_overlap:
        verdict = "SHARED_WORSE_AT_N5"
    elif pct_vs_ddic_total > 10.0 and not ddic_total_overlap:
        verdict = "SHARED_BETTER_AT_N5"
    else:
        verdict = "TIED_AT_N5"

    summary = {
        "n_seeds": len(SEEDS),
        "n_eps_per_seed": 50,
        "n_eps_total": len(all_cum_rfs),
        "eval_comm_fail_prob": "0.1 (env default, matches training)",
        "per_seed": [
            {
                "seed": all_results[i]["train_seed"],
                "cum_rf_total_50ep": all_results[i]["cum_rf_total_50ep"],
                "cum_rf_mean_per_ep": all_results[i]["cum_rf_mean"],
                "cum_rf_std": all_results[i]["cum_rf_std"],
                "ci": all_results[i]["bootstrap_ci"],
            }
            for i in range(len(all_results))
        ],
        "five_seed_total_mean": five_seed_mean_total,
        "five_seed_total_std_n1": five_seed_total_std,
        "five_seed_total_bootstrap_ci": {
            "ci_lo": seed_total_ci_lo,
            "ci_hi": seed_total_ci_hi,
            "n_resample": N_RESAMPLE,
            "seed": BOOTSTRAP_SEED,
        },
        "pooled_250ep_bootstrap_ci": pooled_ci,
        "vs_ddic_5seed_total": {
            "ddic_n5_mean": DDIC_5SEED_MEAN_TOTAL,
            "ddic_n5_std": DDIC_5SEED_STD,
            "ddic_n5_ci": [DDIC_5SEED_CI_LO, DDIC_5SEED_CI_HI],
            "delta": delta_vs_ddic_total,
            "pct": pct_vs_ddic_total,
            "ci_overlap": ddic_total_overlap,
        },
        "verdict": verdict,
    }

    out = os.path.join(ROOT, "results", "phase9_shared_5seed_reeval_summary.json")
    with open(out, "w") as fout:
        json.dump(summary, fout, indent=2)

    print("=" * 70)
    print(" 5-seed aggregate")
    print("=" * 70)
    print("  Per-seed totals (50ep each):")
    for s, t in zip(SEEDS, per_seed_totals):
        print("    seed%d: %.4f" % (s, t))
    print("  mean   = %+.4f" % five_seed_mean_total)
    print("  std    =  %.4f" % five_seed_total_std)
    print("  CI     = [%.4f, %.4f]" % (seed_total_ci_lo, seed_total_ci_hi))
    print()
    print("  Baseline DDIC n=5:")
    print("    mean = %+.4f" % DDIC_5SEED_MEAN_TOTAL)
    print("    std  =  %.4f" % DDIC_5SEED_STD)
    print("    CI   = [%.4f, %.4f]" % (DDIC_5SEED_CI_LO, DDIC_5SEED_CI_HI))
    print()
    print("  delta_vs_DDIC = %+.4f  (%+.1f%%)" % (delta_vs_ddic_total, pct_vs_ddic_total))
    print("  CI overlap    = %s" % ddic_total_overlap)
    print("  VERDICT       = %s" % verdict)
    print()
    print("  Saved: %s" % out)


if __name__ == "__main__":
    main()
