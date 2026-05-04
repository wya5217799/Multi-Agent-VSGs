"""Phase 3 v2 evaluator — fixed test set across all methods.

DEPRECATED 2026-05-04 — DO NOT USE for headline numbers.

This evaluator runs at `comm_fail_prob=0.0`, but training uses `comm_fail_prob=0.1`
(see `scenarios/kundur/train_andes.py:136`). The eval-vs-training mismatch inflates
cum_rf by ~5–8 %. Use `scenarios/kundur/_eval_paper_grade_andes.py` (or its
`_one.py` / `_parallel.py` variants) instead — these default to the env's class
default `comm_fail_prob=0.1`, matching training.

See: `quality_reports/audits/2026-05-04_andes_ddic_eval_discrepancy_verdict.md`

Kept here only for audit-trail reproducibility of pre-2026-05-04 numbers in
`results/andes_phase{3,4}_eval/`. Do not add new callers.

Fixes from v1:
- Same 50 env.seeds (FIXED_TEST_SEEDS) for DDIC, no-control, adaptive
- DDIC loads _best.pt (not _final.pt)
- All 3 methods report cum_rf_global per paper §8.2
- Adds: max_df max-of-max, osc max, failure rate (max_df > 0.5 Hz)

Output: results/andes_phase4_eval/{ddic_seedXX, nocontrol, adaptive}.json + summary.json
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Optional

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from env.andes.andes_vsg_env import AndesMultiVSGEnv

# Fixed test set: 50 env.seeds, identical across all evaluations
FIXED_TEST_SEEDS = [20000 + i for i in range(50)]

OUT_DIR = "results/andes_phase4_eval"


def make_env(seed: int) -> AndesMultiVSGEnv:
    env = AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=0.0)  # DEPRECATED: see module docstring
    env.seed(seed)
    return env


def rollout_one(env: AndesMultiVSGEnv, get_action) -> dict:
    """Run 1 episode. Returns per-step cum_rf_global + max_df + osc."""
    obs = env.reset()
    N = AndesMultiVSGEnv.N_AGENTS
    cum_rf = 0.0
    max_df = 0.0
    osc = 0.0
    for step in range(AndesMultiVSGEnv.STEPS_PER_EPISODE):
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


def eval_method(name: str, get_action_factory) -> dict:
    """Run rollout over FIXED_TEST_SEEDS. get_action_factory(env) → fn(obs) → actions."""
    print(f"--- {name} ---")
    eps = []
    t0 = time.time()
    for seed in FIXED_TEST_SEEDS:
        env = make_env(seed)
        get_action = get_action_factory(env)
        try:
            r = rollout_one(env, get_action)
        except Exception as e:
            print(f"  seed {seed} FAILED: {e}")
            continue
        eps.append({"seed": seed, **r})
    cum_rfs = [e["cum_rf_global"] for e in eps]
    mdfs = [e["max_df"] for e in eps]
    oscs = [e["osc"] for e in eps]
    fail_rate = sum(1 for x in mdfs if x > 0.5) / max(len(mdfs), 1)
    summary = {
        "method": name,
        "n_eps": len(eps),
        "cum_rf_global_total": sum(cum_rfs),
        "cum_rf_global_per_ep_mean": float(np.mean(cum_rfs)),
        "max_df_mean": float(np.mean(mdfs)),
        "max_df_max": float(np.max(mdfs)),
        "max_df_p95": float(np.percentile(mdfs, 95)),
        "osc_mean": float(np.mean(oscs)),
        "osc_max": float(np.max(oscs)),
        "fail_rate_max_df_gt_05": float(fail_rate),
        "wall_s": time.time() - t0,
        "episodes": eps,
    }
    print(f"  cum_rf_total={summary['cum_rf_global_total']:>10.4f}  max_df_mean={summary['max_df_mean']:.4f}  max_df_max={summary['max_df_max']:.4f}  osc_mean={summary['osc_mean']:.4f}  fail%={fail_rate*100:.1f}  wall={summary['wall_s']:.0f}s")
    return summary


# ─── controller factories ───

def factory_nocontrol(env):
    N = AndesMultiVSGEnv.N_AGENTS
    zero = np.zeros(2)
    def get_action(obs):
        return {i: zero for i in range(N)}
    return get_action


def factory_adaptive(K_H: float, K_D: float):
    def make(env):
        N = AndesMultiVSGEnv.N_AGENTS
        DM_MAX = AndesMultiVSGEnv.DM_MAX
        DD_MAX = AndesMultiVSGEnv.DD_MAX
        def get_action(obs):
            actions = {}
            for i in range(N):
                d_omega = obs[i][1] * 3.0
                d_omega_dot = obs[i][2] * 5.0
                dM = K_H * abs(d_omega_dot)
                dD = K_D * abs(d_omega)
                actions[i] = np.array([min(dM / DM_MAX, 1.0), min(dD / DD_MAX, 1.0)])
            return actions
        return get_action
    return make


def factory_ddic(seed: int, ckpt_kind: str = "best"):
    """ckpt_kind: 'best' or 'final'."""
    import torch
    from agents.sac import SACAgent
    import config as cfg
    ckpt_dir = f"results/andes_phase4_noPHIabs_seed{seed}"
    N = AndesMultiVSGEnv.N_AGENTS
    obs_dim = AndesMultiVSGEnv.OBS_DIM
    agents = []
    for i in range(N):
        agent = SACAgent(
            obs_dim=obs_dim, action_dim=2,
            hidden_sizes=cfg.HIDDEN_SIZES,
            lr=cfg.LR, gamma=cfg.GAMMA, tau=cfg.TAU_SOFT,
            buffer_size=cfg.BUFFER_SIZE, batch_size=cfg.BATCH_SIZE,
        )
        ckpt = os.path.join(ckpt_dir, f"agent_{i}_{ckpt_kind}.pt")
        if not os.path.exists(ckpt):
            raise FileNotFoundError(ckpt)
        agent.load(ckpt)
        agents.append(agent)
    def make(env):
        def get_action(obs):
            return {i: agents[i].select_action(obs[i], deterministic=True) for i in range(N)}
        return get_action
    return make


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    results = {}
    print(f"Test set: {len(FIXED_TEST_SEEDS)} fixed env.seeds [{FIXED_TEST_SEEDS[0]}..{FIXED_TEST_SEEDS[-1]}]")

    # No-control
    results["nocontrol"] = eval_method("no-control", factory_nocontrol)
    # Adaptive (project proxy)
    results["adaptive_KH50_KD100"] = eval_method("adaptive K_H=50 K_D=100",
                                                  factory_adaptive(50.0, 100.0))
    # DDIC seeds 42/43/44 — best.pt + final.pt
    for seed in [42, 43, 44]:
        for kind in ["best", "final"]:
            try:
                results[f"ddic_seed{seed}_{kind}"] = eval_method(
                    f"DDIC seed{seed} {kind}", factory_ddic(seed, kind))
            except FileNotFoundError as e:
                print(f"  Skip seed{seed} {kind}: {e}")

    # Save all
    for k, v in results.items():
        with open(os.path.join(OUT_DIR, f"{k}.json"), "w") as f:
            json.dump(v, f, indent=2)

    # Summary table
    print()
    print("=" * 100)
    print(f"{'method':<32} {'cum_rf':>12} {'max_df_mean':>12} {'max_df_max':>11} {'osc_mean':>10} {'fail%':>6}")
    print("-" * 100)
    for k, v in results.items():
        print(f"{k:<32} {v['cum_rf_global_total']:>12.4f} {v['max_df_mean']:>12.4f} {v['max_df_max']:>11.4f} {v['osc_mean']:>10.4f} {v['fail_rate_max_df_gt_05']*100:>5.1f}")

    # DDIC mean ± std (best, 3 seeds)
    ddic_best = [results[f"ddic_seed{s}_best"] for s in [42, 43, 44] if f"ddic_seed{s}_best" in results]
    if len(ddic_best) >= 2:
        cum_rfs = [r["cum_rf_global_total"] for r in ddic_best]
        oscs = [r["osc_mean"] for r in ddic_best]
        print()
        print(f"DDIC best 3-seed mean ± std: cum_rf = {np.mean(cum_rfs):.4f} ± {np.std(cum_rfs):.4f}, osc = {np.mean(oscs):.4f} ± {np.std(oscs):.4f}")
        if results.get("nocontrol"):
            ratio = np.mean(cum_rfs) / results["nocontrol"]["cum_rf_global_total"]
            print(f"DDIC / no-control ratio: {ratio:.3f}")
        if "adaptive_KH50_KD100" in results:
            ratio = np.mean(cum_rfs) / results["adaptive_KH50_KD100"]["cum_rf_global_total"]
            print(f"DDIC / adaptive ratio: {ratio:.3f}  (paper: 0.62)")

    summary_path = os.path.join(OUT_DIR, "summary.json")
    with open(summary_path, "w") as f:
        json.dump({"fixed_test_seeds": FIXED_TEST_SEEDS,
                   "results_by_method": {k: {kk: vv for kk, vv in v.items() if kk != "episodes"}
                                          for k, v in results.items()}}, f, indent=2)
    print(f"\nSaved: {summary_path}")


if __name__ == "__main__":
    main()
