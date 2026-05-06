"""Training curve smoke: cum_rf vs training episode.

Hypothesis: §3.7 5-seed × 500ep mean cum_rf -0.1193 ≈ §3.3 5-seed × 100ep
mean -0.1314 (Welch t = 0.45, p = 0.66, n.s.). This suggests training may
plateau at ep 100. Test by saving intermediate checkpoints during a single
500ep training run and evaluating each on the fixed test seeds.

If cum_rf curve is flat from ep 100 → can reduce training to 100ep (5× compute
savings). If monotonically improves → 500ep is needed. If non-monotonic
(e.g. peak at ep 200, degrades by 500) → indicates over-training.

Usage:
    python3 -u scenarios/kundur/_phase9_curve_smoke.py --seed 50

Output:
    results/andes_phase9_curve_seed{N}/
        agent_shared_ep{100,200,300,400,500}.pt
        eval_paper_grade_ep{100,200,300,400,500}.json
        curve_summary.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import torch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from env.andes.andes_vsg_env import AndesMultiVSGEnv  # noqa: E402
from agents.sac import SACAgent  # noqa: E402
from utils.monitor import TrainingMonitor  # noqa: E402
import config as cfg  # noqa: E402


FIXED_TEST_SEEDS = [20000 + i for i in range(50)]
SAVE_EPS = (100, 200, 300, 400, 500)


def train_with_checkpoints(save_dir: str, seed: int, episodes: int) -> dict:
    os.makedirs(save_dir, exist_ok=True)
    np.random.seed(seed)
    torch.manual_seed(seed)

    N = AndesMultiVSGEnv.N_AGENTS
    OBS_DIM = AndesMultiVSGEnv.OBS_DIM
    N_EPOCH = 10
    WARMUP = cfg.WARMUP_STEPS

    shared_agent = SACAgent(
        obs_dim=OBS_DIM, action_dim=2,
        hidden_sizes=cfg.HIDDEN_SIZES,
        lr=cfg.LR, gamma=cfg.GAMMA, tau=cfg.TAU_SOFT,
        buffer_size=cfg.BUFFER_SIZE, batch_size=cfg.BATCH_SIZE,
    )

    monitor = TrainingMonitor()
    total_steps = 0
    total_rewards = []
    saved_eps: list[int] = []
    t_start = time.time()

    for ep in range(episodes):
        env = AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=0.1)
        env.seed(seed + ep)
        try:
            obs = env.reset()
        except Exception as e:
            print(f"  ep {ep} reset failed: {e}")
            continue

        ep_reward_sum = 0.0
        ep_actions = []
        ep_r_f = ep_r_h = ep_r_d = 0.0
        ep_max_freq = 0.0
        ep_tds_failed = False

        for step in range(AndesMultiVSGEnv.STEPS_PER_EPISODE):
            actions = {}
            for i in range(N):
                if total_steps < WARMUP:
                    actions[i] = np.random.uniform(-1, 1, size=2)
                else:
                    actions[i] = shared_agent.select_action(obs[i])

            try:
                next_obs, rewards, done, info = env.step(actions)
            except Exception as e:
                print(f"  ep {ep} step {step} failed: {e}")
                break

            ep_actions.append(np.array([actions[i] for i in range(N)]))
            ep_r_f += info.get("r_f", 0.0)
            ep_r_h += info.get("r_h", 0.0)
            ep_r_d += info.get("r_d", 0.0)
            ep_max_freq = max(ep_max_freq, info.get("max_freq_deviation_hz", 0.0))
            ep_tds_failed = ep_tds_failed or info.get("tds_failed", False)

            for i in range(N):
                shared_agent.buffer.add(obs[i], actions[i], rewards[i], next_obs[i], float(done))
                ep_reward_sum += rewards[i]

            obs = next_obs
            total_steps += 1
            if done:
                break

        if total_steps >= WARMUP:
            n_updates = N_EPOCH * N
            for _ in range(n_updates):
                if len(shared_agent.buffer) >= cfg.BATCH_SIZE:
                    shared_agent.update()

        total_rewards.append(ep_reward_sum)
        if ep_actions:
            monitor.log_and_check(
                episode=ep, rewards=ep_reward_sum,
                reward_components={"r_f": ep_r_f, "r_h": ep_r_h, "r_d": ep_r_d},
                actions=np.array(ep_actions),
                info={"tds_failed": ep_tds_failed, "max_freq_deviation_hz": ep_max_freq},
                per_agent_rewards={i: ep_reward_sum / N for i in range(N)},
            )

        if (ep + 1) % 10 == 0:
            r_avg10 = float(np.mean(total_rewards[-10:]))
            print(f"  ep {ep+1:>3}/{episodes}  R_avg10={r_avg10:>10.1f}  "
                  f"steps={total_steps}  t={time.time()-t_start:.0f}s")

        # Save intermediate checkpoint
        if (ep + 1) in SAVE_EPS:
            ckpt_path = os.path.join(save_dir, f"agent_shared_ep{ep+1}.pt")
            shared_agent.save(ckpt_path)
            saved_eps.append(ep + 1)
            print(f"  [ckpt] saved ep{ep+1} → {os.path.basename(ckpt_path)}")

    wall_s = time.time() - t_start
    train_log = {
        "total_rewards": total_rewards,
        "total_steps": total_steps,
        "episodes_completed": len(total_rewards),
        "seed": seed,
        "obs_dim": OBS_DIM,
        "wall_s": wall_s,
        "saved_eps": saved_eps,
        "r_avg10_curve": [
            float(np.mean(total_rewards[max(0, e - 10):e]))
            for e in saved_eps
        ],
    }
    json.dump(train_log, open(os.path.join(save_dir, "training_log.json"), "w"), indent=2)
    print(f"\nTraining done. wall={wall_s:.0f}s  saved_eps={saved_eps}")
    return train_log


def rollout_one(env, get_action) -> dict:
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


def evaluate_ckpt(save_dir: str, ep: int, seed_label: int) -> dict:
    ckpt_path = os.path.join(save_dir, f"agent_shared_ep{ep}.pt")
    if not os.path.exists(ckpt_path):
        raise FileNotFoundError(ckpt_path)

    shared_agent = SACAgent(
        obs_dim=AndesMultiVSGEnv.OBS_DIM, action_dim=2,
        hidden_sizes=cfg.HIDDEN_SIZES,
        lr=cfg.LR, gamma=cfg.GAMMA, tau=cfg.TAU_SOFT,
        buffer_size=cfg.BUFFER_SIZE, batch_size=cfg.BATCH_SIZE,
    )
    shared_agent.load(ckpt_path)
    N = AndesMultiVSGEnv.N_AGENTS

    def get_action(obs):
        return {i: shared_agent.select_action(obs[i], deterministic=True)
                for i in range(N)}

    print(f"  [eval ep{ep}] running {len(FIXED_TEST_SEEDS)} test seeds...")
    episodes = []
    t0 = time.time()
    for ts in FIXED_TEST_SEEDS:
        env = AndesMultiVSGEnv(random_disturbance=True)
        env.seed(ts)
        try:
            r = rollout_one(env, get_action)
        except Exception as exc:
            print(f"    test_seed {ts} FAILED: {exc}")
            continue
        episodes.append({"seed": ts, **r})

    cum_rfs = [e["cum_rf_global"] for e in episodes]
    mdfs = [e["max_df"] for e in episodes]
    cum_rf_mean = float(np.mean(cum_rfs))
    cum_rf_std = float(np.std(cum_rfs))
    max_df_mean = float(np.mean(mdfs))
    fail_rate = float(sum(1 for x in mdfs if x > 0.5) / max(len(mdfs), 1))
    wall_s = time.time() - t0

    print(f"  [eval ep{ep}] cum_rf={cum_rf_mean:.4f} ± {cum_rf_std:.4f}  "
          f"max_df={max_df_mean:.4f}  fail%={fail_rate*100:.1f}  wall={wall_s:.0f}s")

    result = {
        "ep": ep,
        "train_seed": seed_label,
        "n_test_eps": len(episodes),
        "cum_rf_mean": cum_rf_mean,
        "cum_rf_std": cum_rf_std,
        "cum_rfs": cum_rfs,
        "max_df_mean": max_df_mean,
        "fail_rate_max_df_gt_05": fail_rate,
        "wall_s": wall_s,
    }
    out_path = os.path.join(save_dir, f"eval_paper_grade_ep{ep}.json")
    json.dump(result, open(out_path, "w"), indent=2)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=50)
    parser.add_argument("--episodes", type=int, default=500)
    args = parser.parse_args()

    SEED = args.seed
    SAVE_DIR = os.path.join(ROOT, f"results/andes_phase9_curve_seed{SEED}")

    print("=" * 70)
    print(f" Training curve smoke — seed={SEED} episodes={args.episodes}")
    print(f" save_dir={SAVE_DIR}")
    print(f" checkpoint episodes: {SAVE_EPS}")
    print("=" * 70)

    train_log = train_with_checkpoints(SAVE_DIR, seed=SEED, episodes=args.episodes)

    print()
    print("─" * 70)
    print(" Evaluating all checkpoints (50 fixed test seeds each)")
    print("─" * 70)

    eval_results = []
    for ep in train_log["saved_eps"]:
        result = evaluate_ckpt(SAVE_DIR, ep, seed_label=SEED)
        eval_results.append(result)

    # Summary
    summary = {
        "seed": SEED,
        "training_eps_total": args.episodes,
        "train_wall_s": train_log["wall_s"],
        "saved_eps": train_log["saved_eps"],
        "r_avg10_curve": train_log["r_avg10_curve"],
        "cum_rf_curve": [r["cum_rf_mean"] for r in eval_results],
        "cum_rf_std_curve": [r["cum_rf_std"] for r in eval_results],
        "max_df_curve": [r["max_df_mean"] for r in eval_results],
        "fail_rate_curve": [r["fail_rate_max_df_gt_05"] for r in eval_results],
    }
    json.dump(summary, open(os.path.join(SAVE_DIR, "curve_summary.json"), "w"), indent=2)

    print()
    print("=" * 70)
    print(" SUMMARY — cum_rf curve vs training episode")
    print("=" * 70)
    print(f"{'ep':>5}  {'r_avg10_train':>15}  {'cum_rf_eval':>15}  {'max_df':>10}  {'fail%':>7}")
    for ep, r_avg10, cum_rf, std, mdf, fr in zip(
        summary["saved_eps"],
        summary["r_avg10_curve"],
        summary["cum_rf_curve"],
        summary["cum_rf_std_curve"],
        summary["max_df_curve"],
        summary["fail_rate_curve"],
    ):
        print(f"{ep:>5}  {r_avg10:>15.1f}  {cum_rf:>9.4f}±{std:.3f}  {mdf:>10.4f}  {fr*100:>6.1f}")
    print("=" * 70)


if __name__ == "__main__":
    main()
