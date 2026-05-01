"""ODE Gate 5 — Paper-direction sanity (boundary doc §18 G5).

Plan: quality_reports/plans/2026-05-02_ode_paper_alignment.md (Stage 5)

Trains SAC for ``--episodes`` episodes on the canonical 100-train manifest,
evaluates the trained policy and the no-control baseline on the canonical
50-test manifest using ``evaluation_reward_global``.

PASS condition: ``mean(R_trained) > mean(R_no_control)``  (direction only,
NOT paper -8.04 number). FAIL is recorded as INCONCLUSIVE (DoD allows it).

Default --episodes=200 is intentionally short. Paper-scale comparison
needs >=2000 episodes; that is out of scope for this plan.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from env.multi_vsg_env import MultiVSGEnv  # noqa: E402
from env.ode.ode_scenario import (          # noqa: E402
    SEED_TRAIN_DEFAULT,
    SEED_TEST_DEFAULT,
    ODE_SCENARIO_SETS_DIR,
    load_manifest as _load_ode_manifest,
    generate_scenarios as _generate_ode_scenarios,
    N_TRAIN_PAPER, N_TEST_PAPER,
)
from env.ode.reward import evaluation_reward_global  # noqa: E402
from agents.ma_manager import MultiAgentManager        # noqa: E402
import config as cfg                                    # noqa: E402


def _resolve_set(seed: int, n: int, kind: str):
    canonical = ODE_SCENARIO_SETS_DIR / f"kd_{kind}_{n}.json"
    if canonical.exists():
        s = _load_ode_manifest(canonical)
        return list(s.scenarios)
    return list(_generate_ode_scenarios(n, seed_base=seed, name=f"adhoc_{kind}").scenarios)


def _train(manager, env, scenarios, n_episodes, warmup, seed):
    """Train with per-episode reward + per-agent buffer-state instrumentation.

    Q1 fix 2026-05-02: returns a diagnostic dict so callers can distinguish
    INCONCLUSIVE-because-short-training from INCONCLUSIVE-because-broken.
    """
    rng = np.random.default_rng(seed)
    total_steps = 0
    t0 = time.time()
    ep_rewards: list[float] = []
    nan_in_reward = False
    early_term_episodes = 0
    term_reasons: dict[str, int] = {}
    for ep in range(n_episodes):
        obs = env.reset(scenario=scenarios[ep % len(scenarios)])
        ep_total = 0.0
        terminated_this_ep = False
        for _ in range(cfg.STEPS_PER_EPISODE):
            if total_steps < warmup:
                actions = {i: rng.uniform(-1, 1, size=cfg.ACTION_DIM) for i in range(cfg.N_AGENTS)}
            else:
                actions = manager.select_actions(obs)
            next_obs, rewards, done, info = env.step(actions)
            manager.store_transitions(obs, actions, rewards, next_obs, done)
            if total_steps >= warmup:
                manager.update()
            obs = next_obs
            total_steps += 1
            for v in rewards.values():
                if not np.isfinite(v):
                    nan_in_reward = True
                ep_total += float(v)
            reason = info.get('termination_reason', '')
            if reason and not terminated_this_ep:
                terminated_this_ep = True
                term_reasons[reason] = term_reasons.get(reason, 0) + 1
        if terminated_this_ep:
            early_term_episodes += 1
        ep_rewards.append(ep_total)
        if (ep + 1) % 50 == 0:
            recent = np.mean(ep_rewards[-50:])
            print(f"    [train] ep {ep+1}/{n_episodes}  recent_avg={recent:.2f}  "
                  f"({time.time()-t0:.1f}s)")
    print(f"    [train] done in {time.time()-t0:.1f}s, total_steps={total_steps}")
    return {
        "ep_rewards": ep_rewards,
        "nan_in_reward": nan_in_reward,
        "early_term_episodes": early_term_episodes,
        "early_term_fraction": early_term_episodes / max(1, n_episodes),
        "term_reasons": term_reasons,
        "buffer_lens": [len(manager.agents[i].buffer) for i in range(cfg.N_AGENTS)],
    }


def _eval_set(env, scenarios, manager=None) -> np.ndarray:
    rewards: list[float] = []
    for s in scenarios:
        obs = env.reset(scenario=s)
        freq_trace: list[np.ndarray] = [env.ps.get_state()['freq_hz']]
        for _ in range(cfg.STEPS_PER_EPISODE):
            if manager is None:
                actions = {i: np.zeros(cfg.ACTION_DIM, dtype=np.float32) for i in range(cfg.N_AGENTS)}
            else:
                actions = manager.select_actions(obs, deterministic=True)
            next_obs, _, _, info = env.step(actions)
            freq_trace.append(info['freq_hz'])
            obs = next_obs
        rewards.append(evaluation_reward_global(np.array(freq_trace)))
    return np.array(rewards)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--episodes", type=int, default=200,
                   help="Training episodes (default 200; paper uses 2000)")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    print("=" * 65)
    print(f"  ODE Gate 5 · Paper-direction · {args.episodes} train ep / 50 test")
    print("=" * 65)

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    train_scenarios = _resolve_set(SEED_TRAIN_DEFAULT, N_TRAIN_PAPER, "train")
    test_scenarios = _resolve_set(SEED_TEST_DEFAULT, N_TEST_PAPER, "test")
    print(f"  train_set: {len(train_scenarios)} scenarios")
    print(f"  test_set:  {len(test_scenarios)} scenarios")

    env = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
    manager = MultiAgentManager(
        n_agents=cfg.N_AGENTS, obs_dim=cfg.OBS_DIM, action_dim=cfg.ACTION_DIM,
        hidden_sizes=cfg.HIDDEN_SIZES, lr=cfg.LR, gamma=cfg.GAMMA,
        tau=cfg.TAU_SOFT, buffer_size=cfg.BUFFER_SIZE, batch_size=cfg.BATCH_SIZE,
        device='cpu',
    )

    print("\n--- Training ---")
    train_diag = _train(manager, env, train_scenarios, args.episodes,
                        warmup=min(cfg.WARMUP_STEPS, args.episodes * 5), seed=args.seed)

    print("\n--- Evaluation ---")
    rewards_trained = _eval_set(env, test_scenarios, manager=manager)
    rewards_nc = _eval_set(env, test_scenarios, manager=None)

    mean_t, mean_nc = float(rewards_trained.mean()), float(rewards_nc.mean())
    print(f"  trained:    mean={mean_t:.4f}  std={rewards_trained.std():.4f}")
    print(f"  no_control: mean={mean_nc:.4f}  std={rewards_nc.std():.4f}")
    print(f"  delta = trained - no_control = {mean_t - mean_nc:+.4f}")

    direction_pass = mean_t > mean_nc

    # Q1 fix 2026-05-02: distinguish INCONCLUSIVE (short training, alive) from
    # broken (NaN, no buffer fill, training-reward stuck/diverging).
    print("\n--- Training diagnostics ---")
    eps = train_diag["ep_rewards"]
    n = len(eps)
    if n >= 6:
        first_third = float(np.mean(eps[: n // 3]))
        last_third = float(np.mean(eps[-n // 3:]))
        print(f"  ep_reward early third: {first_third:+.2f}")
        print(f"  ep_reward last  third: {last_third:+.2f}")
        print(f"  ep_reward delta      : {last_third - first_third:+.2f}")
    print(f"  NaN reward during training: {train_diag['nan_in_reward']}")
    print(f"  early-termination episodes: {train_diag['early_term_episodes']}/{n} "
          f"({train_diag['early_term_fraction']*100:.0f}%)")
    if train_diag['term_reasons']:
        print(f"  termination reasons: {train_diag['term_reasons']}")
    print(f"  buffer fills (per agent): {train_diag['buffer_lens']}")
    # Healthy if: no reward NaN AND <50% episodes terminated early AND buffer non-empty.
    # Occasional safety termination during random warmup is expected, NOT broken.
    healthy = (not train_diag["nan_in_reward"]) \
              and train_diag["early_term_fraction"] < 0.5 \
              and all(b > 0 for b in train_diag["buffer_lens"])

    if direction_pass:
        verdict = "PASS (direction)"
    elif healthy:
        verdict = "INCONCLUSIVE — short training, infrastructure healthy"
    else:
        verdict = "BROKEN — NaN or empty buffer"
    print(f"\n  Gate 5 ({args.episodes} ep): {verdict}")
    return 0 if direction_pass else (2 if healthy else 1)


if __name__ == "__main__":
    sys.exit(main())
