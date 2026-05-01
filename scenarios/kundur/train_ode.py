"""
训练脚本 — 多智能体 SAC 分布式惯量-阻尼控制

论文: Yang et al., IEEE TPWRS 2023

关键实现细节 (与论文对齐):
  - 每 episode 结束后清空 buffer (Algorithm 1 line 16)
  - r_h/r_d 使用全局平均 ΔH^avg / ΔD^avg (Eq.17-18)
  - ΔH ∈ [-100, 300], ΔD ∈ [-200, 600] (Fig.7(c)(d))
  - 固定训练场景集 100 scenarios (Sec IV-A)

用法:
    python train.py                     # 默认 2000 episodes
    python train.py --episodes 500      # 快速测试
"""

import argparse
import os
import sys
import time
import numpy as np
import torch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config as cfg
from env.multi_vsg_env import MultiVSGEnv
from env.ode.ode_scenario import (
    ODEScenario,
    ODE_SCENARIO_SETS_DIR,
    SEED_TRAIN_DEFAULT,
    generate_scenarios as _generate_ode_scenarios,
    load_manifest as _load_ode_manifest,
    save_manifest as _save_ode_manifest,
    N_TRAIN_PAPER,
)
from agents.ma_manager import MultiAgentManager
from utils.monitor import TrainingMonitor


# DEPRECATED 2026-05-02 — kept temporarily for any external caller. Use
# ``env.ode.ode_scenario.generate_scenarios`` + on-disk manifest instead.
def generate_scenario_set(n_scenarios, seed=0):
    """[DEPRECATED] Use env.ode.ode_scenario.generate_scenarios + manifest.

    Returns the legacy (delta_u, failed_links) tuple list shape, kept as a
    thin shim around the new ODEScenario generator so we cannot drift.
    """
    s = _generate_ode_scenarios(n_scenarios, seed_base=seed, name="legacy_shim")
    return [scenario.to_legacy_tuple() for scenario in s.scenarios]


def _load_or_generate_train_set(seed: int) -> tuple[list[ODEScenario], str | None]:
    """Resolve the canonical ODE training set.

    Strategy:
      - If seed matches the canonical SEED_TRAIN_DEFAULT and the on-disk
        manifest exists, load it. (paper-aligned reproducibility, §16)
      - Otherwise regenerate in-memory from the requested seed (no disk
        write — caller's choice of an experimental seed should not clobber
        the canonical manifest).

    Returns (scenarios, manifest_path_or_None).
    """
    canonical_path = ODE_SCENARIO_SETS_DIR / "kd_train_100.json"
    if seed == SEED_TRAIN_DEFAULT and canonical_path.exists():
        s = _load_ode_manifest(canonical_path)
        return list(s.scenarios), str(canonical_path)
    s = _generate_ode_scenarios(cfg.N_TRAIN_SCENARIOS, seed_base=seed, name=f"adhoc_seed{seed}")
    return list(s.scenarios), None


def train(args):
    device = 'cuda' if torch.cuda.is_available() and not args.cpu else 'cpu'

    # ── P1: 完整 seed 协议，必须在 manager/网络构造前完成 ──
    from utils.seed_utils import seed_everything
    seed_info = seed_everything(args.seed)
    warmup_rng = np.random.default_rng(args.seed)

    # ── 加载/生成固定训练场景集 (Stage 4 2026-05-02: 从 ODEScenario manifest) ──
    train_scenarios, train_manifest_path = _load_or_generate_train_set(args.seed)
    if train_manifest_path is not None:
        print(f"  [scenario set] loaded canonical manifest: {train_manifest_path}")
    else:
        print(f"  [scenario set] adhoc seed={args.seed} (in-memory; not persisted)")

    # ── 环境 (不使用内部随机扰动, 由外部指定) ──
    env = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)

    # ── 多智能体 (seed 已在上方统一设置) ──
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
        device=device,
    )

    # ── 日志 ──
    save_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'results')
    os.makedirs(os.path.join(save_dir, 'models'), exist_ok=True)

    episode_rewards = {i: [] for i in range(cfg.N_AGENTS)}
    episode_total_rewards = []
    episode_freq_rewards = []    # PHI_F * sum(r_f)
    episode_inertia_rewards = [] # PHI_H * sum(r_h)
    episode_droop_rewards = []   # PHI_D * sum(r_d)

    print("=" * 65)
    print("  MADRL-SAC Training — Multi-VSG Distributed Inertia-Droop")
    print("=" * 65)
    print(f"  Device        = {device}")
    print(f"  N agents      = {cfg.N_AGENTS}")
    print(f"  Episodes      = {args.episodes}")
    print(f"  Steps/episode = {cfg.STEPS_PER_EPISODE}")
    print(f"  DT            = {cfg.DT}s, Episode = {cfg.T_EPISODE}s")
    print(f"  H_ES0         = {cfg.H_ES0[0]}, D_ES0 = {cfg.D_ES0[0]}")
    print(f"  dH in [{cfg.DH_MIN}, {cfg.DH_MAX}], dD in [{cfg.DD_MIN}, {cfg.DD_MAX}]")
    print(f"  Network       = {cfg.HIDDEN_SIZES}")
    print(f"  Disturbance   = [{cfg.DISTURBANCE_MIN}, {cfg.DISTURBANCE_MAX}] p.u.")
    print(f"  Train scenes  = {len(train_scenarios)}")
    print(f"  Buffer        = {'clear per ep (Alg.1)' if cfg.CLEAR_BUFFER_PER_EPISODE else 'accumulate across eps (Table I)'}")
    print(f"  Warmup steps  = {cfg.WARMUP_STEPS}")
    print(f"  Seed          = {args.seed}")
    print("=" * 65)

    monitor = TrainingMonitor()

    total_steps = 0
    t_start = time.time()

    for episode in range(args.episodes):
        # 从固定场景集中循环选取 (D2 2026-05-02: ODEScenario VO via reset(scenario=))
        scenario_idx = episode % len(train_scenarios)
        scenario = train_scenarios[scenario_idx]
        obs = env.reset(scenario=scenario)

        ep_rewards = {i: 0.0 for i in range(cfg.N_AGENTS)}
        ep_r_f, ep_r_h, ep_r_d = 0.0, 0.0, 0.0
        ep_actions_list = []
        ep_max_freq = 0.0

        for step in range(cfg.STEPS_PER_EPISODE):
            # 选择动作
            if total_steps < cfg.WARMUP_STEPS:
                # P1: 本地 RNG 替代全局 np.random 保证可复现
                actions = {i: warmup_rng.uniform(-1, 1, size=cfg.ACTION_DIM)
                           for i in range(cfg.N_AGENTS)}
            else:
                actions = manager.select_actions(obs)

            # 环境步进
            next_obs, rewards, done, info = env.step(actions)

            # 存储经验
            manager.store_transitions(obs, actions, rewards, next_obs, done)

            # 更新网络
            if total_steps >= cfg.WARMUP_STEPS:
                manager.update()

            for i in range(cfg.N_AGENTS):
                ep_rewards[i] += rewards[i]

            # 累计分项奖励
            ep_r_f += info['r_f']
            ep_r_h += info['r_h']
            ep_r_d += info['r_d']

            # Monitor: collect actions and freq deviation
            ep_actions_list.append(np.array([actions[i] for i in range(cfg.N_AGENTS)]))
            ep_max_freq = max(ep_max_freq, info.get('max_freq_deviation_hz', 0.0))

            obs = next_obs
            total_steps += 1

        # 论文 Algorithm 1 line 16: 每 episode 结束后清空 buffer
        # 可通过 config.CLEAR_BUFFER_PER_EPISODE 切换 (对比实验)
        if cfg.CLEAR_BUFFER_PER_EPISODE:
            manager.clear_buffers()

        # Monitor: check for training issues
        should_stop = monitor.log_and_check(
            episode=episode,
            rewards=sum(ep_rewards[i] for i in range(cfg.N_AGENTS)),
            reward_components={"r_f": ep_r_f, "r_h": ep_r_h, "r_d": ep_r_d},
            actions=np.array(ep_actions_list),
            info={"tds_failed": False, "max_freq_deviation_hz": ep_max_freq},
        )
        if should_stop:
            break

        # 记录奖励
        total_r = 0.0
        for i in range(cfg.N_AGENTS):
            episode_rewards[i].append(ep_rewards[i])
            total_r += ep_rewards[i]
        episode_total_rewards.append(total_r)
        episode_freq_rewards.append(ep_r_f)
        episode_inertia_rewards.append(ep_r_h)
        episode_droop_rewards.append(ep_r_d)

        # 打印进度
        if (episode + 1) % 50 == 0 or episode == 0:
            avg_total = np.mean(episode_total_rewards[-50:])
            elapsed = time.time() - t_start
            per_agent = [np.mean(episode_rewards[i][-50:]) for i in range(cfg.N_AGENTS)]
            print(f"  Ep {episode+1:5d}/{args.episodes} | "
                  f"Total R = {total_r:10.2f} | "
                  f"Avg50 = {avg_total:10.2f} | "
                  f"Per-agent = [{', '.join(f'{r:.1f}' for r in per_agent)}] | "
                  f"{elapsed:.0f}s")

        # 定期保存
        if (episode + 1) % 500 == 0:
            model_dir = os.path.join(save_dir, 'models', f'ep_{episode+1}')
            manager.save(model_dir)

    monitor.summary()

    # ── 最终保存 ──
    final_dir = os.path.join(save_dir, 'models', 'final')
    manager.save(final_dir)

    log_path = os.path.join(save_dir, 'training_log.npz')
    log_data = {
        'episode_total_rewards': np.array(episode_total_rewards),
        'episode_freq_rewards': np.array(episode_freq_rewards),
        'episode_inertia_rewards': np.array(episode_inertia_rewards),
        'episode_droop_rewards': np.array(episode_droop_rewards),
    }
    for i in range(cfg.N_AGENTS):
        log_data[f'episode_rewards_agent_{i}'] = np.array(episode_rewards[i])
    np.savez(log_path, **log_data)

    # P0 + P1: run metadata sidecar (完整 seed 协议 + 固定训练集标识)
    import json as _json
    meta = {
        "scenario": "kundur_ode",
        "train_seed": int(args.seed),
        "seed_protocol": seed_info,
        "n_episodes": int(args.episodes),
        "train_set": {
            "n_train": int(cfg.N_TRAIN_SCENARIOS),
            "seed": int(args.seed),
            "generator": "env.ode.ode_scenario.generate_scenarios",
            "manifest_path": train_manifest_path,
        },
        "note": "Stage 4 2026-05-02: ODEScenario VO + manifest (env/ode/ode_scenario.py)",
    }
    meta_path = os.path.join(save_dir, 'run_meta.json')
    with open(meta_path, 'w') as f:
        _json.dump(meta, f, indent=2)
    print(f"  [P0/P1 metadata] {meta_path}")

    elapsed = time.time() - t_start
    print(f"\n{'=' * 65}")
    print(f"  Training complete!")
    print(f"  Episodes: {args.episodes}, Time: {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  Final 50ep avg reward: {np.mean(episode_total_rewards[-50:]):.2f}")
    print(f"  Model: {final_dir}")
    print(f"{'=' * 65}")


def main():
    parser = argparse.ArgumentParser(description="MADRL-SAC Training")
    parser.add_argument('--episodes', type=int, default=cfg.N_EPISODES)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--cpu', action='store_true')
    args = parser.parse_args()
    train(args)


if __name__ == '__main__':
    main()
