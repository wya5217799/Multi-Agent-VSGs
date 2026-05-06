"""Re-evaluate Phase 9 shared-param SAC pilot under paper-faithful comm_fail_prob=0.1.

The original eval_summary.json used comm_fail_prob=0.0 (legacy path in evaluate()).
Training used comm_fail_prob=0.1 (line 81 of _phase9_shared_param_sac.py).
This script corrects the apples-to-oranges comparison in predraft §2.6.

Output: results/andes_phase9_shared_seed42/eval_paper_grade_pilot.json
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
import config as cfg

SAVE_DIR = os.path.join(ROOT, "results", "andes_phase9_shared_seed42")
CKPT = os.path.join(SAVE_DIR, "agent_shared_final.pt")
OUT = os.path.join(SAVE_DIR, "eval_paper_grade_pilot.json")

FIXED_TEST_SEEDS = [20000 + i for i in range(50)]

# Reference (CLAIM — from stored eval JSONs, paper-grade re-eval 2026-05-04)
DDIC_SEED42_FINAL_PG = -1.1570142304511677   # paper-grade, comm_fail_prob=0.1


def _rollout(env: AndesMultiVSGEnv, agent: SACAgent, n_agents: int) -> dict:
    obs = env.reset()
    cum_rf = 0.0
    max_df = 0.0
    osc = 0.0
    for _step in range(AndesMultiVSGEnv.STEPS_PER_EPISODE):
        actions = {i: agent.select_action(obs[i], deterministic=True) for i in range(n_agents)}
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


def main() -> None:
    if not os.path.exists(CKPT):
        raise FileNotFoundError(f"Checkpoint not found: {CKPT}")

    shared_agent = SACAgent(
        obs_dim=AndesMultiVSGEnv.OBS_DIM, action_dim=2,
        hidden_sizes=cfg.HIDDEN_SIZES,
        lr=cfg.LR, gamma=cfg.GAMMA, tau=cfg.TAU_SOFT,
        buffer_size=cfg.BUFFER_SIZE, batch_size=cfg.BATCH_SIZE,
    )
    shared_agent.load(CKPT)
    N = AndesMultiVSGEnv.N_AGENTS  # 4

    print(f"Re-evaluating {CKPT} under comm_fail_prob=0.1 (paper-faithful) ...")
    t0 = time.time()
    eps = []
    for seed in FIXED_TEST_SEEDS:
        # Do NOT pass comm_fail_prob — default is 0.1, matching training
        env = AndesMultiVSGEnv(random_disturbance=True)
        env.seed(seed)
        try:
            r = _rollout(env, shared_agent, N)
        except Exception as e:
            print(f"  seed {seed} FAILED: {e}")
            continue
        eps.append({"seed": seed, **r})

    if not eps:
        raise RuntimeError("All eval episodes failed")

    cum_rfs = [e["cum_rf_global"] for e in eps]
    mdfs = [e["max_df"] for e in eps]
    oscs = [e["osc"] for e in eps]

    cum_rf_total = float(sum(cum_rfs))
    max_df_mean = float(np.mean(mdfs))
    osc_mean = float(np.mean(oscs))
    fail_rate = sum(1 for x in mdfs if x > 0.5) / max(len(mdfs), 1)
    wall_s = time.time() - t0

    delta_vs_ddic42 = cum_rf_total - DDIC_SEED42_FINAL_PG
    pct_vs_ddic42 = (delta_vs_ddic42 / abs(DDIC_SEED42_FINAL_PG)) * 100.0

    result = {
        "controller": "shared_param_sac_seed42_100ep_reeval_comm01",
        "eval_condition": "comm_fail_prob=0.1 (matches training, paper-faithful)",
        "eval_date": "2026-05-04",
        "n_test_eps": len(eps),
        "cum_rf_total": cum_rf_total,
        "max_df_mean": max_df_mean,
        "osc_mean": osc_mean,
        "fail_rate_max_df_gt_05": fail_rate,
        "wall_s": wall_s,
        "comparison": {
            "vs_ddic_seed42_paper_grade": {
                "ddic_seed42_cum_rf": DDIC_SEED42_FINAL_PG,
                "shared_cum_rf": cum_rf_total,
                "cum_rf_delta": delta_vs_ddic42,
                "pct_relative": pct_vs_ddic42,
            }
        },
        "note": (
            "Re-evaluated 2026-05-04 under comm_fail_prob=0.1 (paper-faithful). "
            "Replaces stale -1.200 from eval_summary.json (comm_fail_prob=0.0). "
            "See quality_reports/audits/2026-05-04_andes_ddic_eval_discrepancy_verdict.md"
        ),
        "episodes": eps,
    }

    json.dump(result, open(OUT, "w"), indent=2)
    print(f"\n--- Results ---")
    print(f"  cum_rf_total = {cum_rf_total:.4f}  (old stale: -1.2000)")
    print(f"  vs DDIC seed42 ({DDIC_SEED42_FINAL_PG:.4f}): {pct_vs_ddic42:+.1f}%")
    print(f"  max_df_mean={max_df_mean:.4f}  osc_mean={osc_mean:.4f}  fail%={fail_rate*100:.1f}")
    print(f"  wall={wall_s:.0f}s  n_eps={len(eps)}")
    print(f"\nSaved: {OUT}")


if __name__ == "__main__":
    main()
