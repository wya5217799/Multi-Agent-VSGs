"""ODE Gate 4 — RL plumbing sanity (boundary doc §18 G4).

Plan: quality_reports/plans/2026-05-02_ode_paper_alignment.md (Stage 5)

Verifies that after the Stage 1-4 refactor the SAC-driven training loop
exchanges signals correctly with the env. Does NOT verify learning quality
(that is Gate 5 territory).

  G4.a  50-episode short training completes without crash.
  G4.b  Replay buffer accumulates >= warmup-step transitions.
  G4.c  Action distribution is non-constant across steps (std > 0.05).
  G4.d  Reward components (info['reward_components']) are populated each
        step; per-agent r_f is non-zero on at least one agent on at
        least one step (i.e. signal reaches the loss).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from env.multi_vsg_env import MultiVSGEnv  # noqa: E402
from env.ode.ode_scenario import (          # noqa: E402
    SEED_TRAIN_DEFAULT,
    generate_scenarios as _generate_ode_scenarios,
)
from agents.ma_manager import MultiAgentManager  # noqa: E402
import config as cfg                              # noqa: E402


def gate_4_short_training(n_episodes: int = 30, seed: int = 42) -> dict:
    print(f"\n=== G4 · Short SAC training: {n_episodes} episodes, seed={seed} ===")

    # Reproducibility
    torch.manual_seed(seed)
    np.random.seed(seed)
    rng = np.random.default_rng(seed)

    train_set = _generate_ode_scenarios(
        cfg.N_TRAIN_SCENARIOS, seed_base=seed, name="g4_smoke"
    )
    scenarios = list(train_set.scenarios)

    env = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
    manager = MultiAgentManager(
        n_agents=cfg.N_AGENTS,
        obs_dim=cfg.OBS_DIM,
        action_dim=cfg.ACTION_DIM,
        hidden_sizes=cfg.HIDDEN_SIZES,
        lr=cfg.LR,
        gamma=cfg.GAMMA,
        tau=cfg.TAU_SOFT,
        buffer_size=cfg.BUFFER_SIZE,
        batch_size=cfg.BATCH_SIZE,
        device='cpu',
    )

    actions_record: list[np.ndarray] = []
    info_seen = 0
    info_with_components = 0
    nonzero_r_f_seen = False
    total_steps = 0
    warmup_steps = min(200, cfg.WARMUP_STEPS)   # short for Gate 4

    for ep in range(n_episodes):
        obs = env.reset(scenario=scenarios[ep % len(scenarios)])
        for _ in range(cfg.STEPS_PER_EPISODE):
            if total_steps < warmup_steps:
                actions = {i: rng.uniform(-1, 1, size=cfg.ACTION_DIM) for i in range(cfg.N_AGENTS)}
            else:
                actions = manager.select_actions(obs)
            next_obs, rewards, done, info = env.step(actions)
            manager.store_transitions(obs, actions, rewards, next_obs, done)
            if total_steps >= warmup_steps:
                manager.update()

            actions_record.append(np.array([actions[i] for i in range(cfg.N_AGENTS)]))
            info_seen += 1
            rc = info.get('reward_components')
            if rc is not None:
                info_with_components += 1
                if any(abs(x) > 1e-12 for x in rc.get('r_f_per_agent', [])):
                    nonzero_r_f_seen = True
            obs = next_obs
            total_steps += 1

    # FIX 2026-05-02: ma_manager exposes agents at `manager.agents[i].buffer`,
    # NOT `manager.buffers[i]`. Earlier probe revision used the wrong attr and
    # silently fell through to None, making this gate vacuously PASS. See
    # quality_reports/verdicts/2026-05-02_ode_gate_1to5.md M2.
    n_transitions_each = [len(manager.agents[i].buffer) for i in range(cfg.N_AGENTS)]

    actions_arr = np.array(actions_record)  # (T, N, 2)
    action_std = float(actions_arr.std())
    return {
        "n_episodes": n_episodes,
        "total_steps": total_steps,
        "warmup_steps": warmup_steps,
        "info_seen": info_seen,
        "info_with_components": info_with_components,
        "nonzero_r_f_seen": nonzero_r_f_seen,
        "action_std": action_std,
        "n_transitions_each": n_transitions_each,
    }


def main() -> int:
    print("=" * 65)
    print("  ODE Gate 4 · RL plumbing sanity")
    print("=" * 65)
    res = gate_4_short_training(n_episodes=30)
    print("\n--- Summary ---")
    for k, v in res.items():
        print(f"  {k}: {v}")

    passes = {
        "4a_completed_no_crash": True,  # if we got here, no crash
        # FIX 2026-05-02: previously short-circuited on `is None`, masking
        # the wrong-attr bug. Now require an actual list AND threshold.
        "4b_buffer_accumulated": (res["n_transitions_each"] is not None
                                  and all(n >= res["warmup_steps"] for n in res["n_transitions_each"])),
        "4c_action_nonconstant": res["action_std"] > 0.05,
        "4d_reward_components_populated": (res["info_with_components"] == res["info_seen"]
                                            and res["nonzero_r_f_seen"]),
    }
    print("\n--- Verdict ---")
    for k, v in passes.items():
        print(f"  {'PASS' if v else 'FAIL':6s}  G{k}")
    return 0 if all(passes.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
