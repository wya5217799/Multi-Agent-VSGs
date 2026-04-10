"""
快速测试: substep 渐变对 TDS 崩溃率的影响
===========================================
在 WSL 中运行:
    source ~/andes_venv/bin/activate
    cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"
    python3 tests/test_substep_tds.py

测试逻辑:
  - 用随机动作跑 N 个 episode (模拟 warmup 阶段最恶劣情况)
  - 统计 TDS 崩溃率和每 episode 完成的 step 数
  - 分别测试 Kundur (4 agent) 和 NE (8 agent)
"""

import os
import sys
import time
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def run_env(env_class, env_name, n_episodes=20, seed_base=100):
    """跑 n_episodes 个全随机动作 episode, 统计 TDS 崩溃率."""
    print(f"\n{'='*50}")
    print(f" {env_name}: M0={env_class.VSG_M0}, N_SUBSTEPS={env_class.N_SUBSTEPS}")
    print(f" scale_M={env_class._SCALE_M}, M range=[{env_class.VSG_M0 + env_class.DM_MIN:.1f}, {env_class.VSG_M0 + env_class.DM_MAX:.1f}]")
    print(f"{'='*50}")

    N = env_class.N_AGENTS
    tds_fail_count = 0
    total_steps = 0
    ep_steps_list = []
    t_start = time.time()

    for ep in range(n_episodes):
        env = env_class(random_disturbance=True, comm_fail_prob=0.0)
        env.seed(seed_base + ep)

        try:
            obs = env.reset()
        except Exception as e:
            print(f"  [ep {ep}] reset failed: {e}")
            tds_fail_count += 1
            ep_steps_list.append(0)
            continue

        ep_steps = 0
        ep_failed = False
        for step in range(env.STEPS_PER_EPISODE):
            # 全随机动作 (最恶劣情况)
            actions = {i: np.random.uniform(-1, 1, size=2) for i in range(N)}
            try:
                obs, rewards, done, info = env.step(actions)
            except Exception as e:
                print(f"  [ep {ep}, step {step}] exception: {e}")
                ep_failed = True
                break

            ep_steps += 1
            total_steps += 1

            if info.get('tds_failed', False):
                ep_failed = True
                break

            if done:
                break

        if ep_failed:
            tds_fail_count += 1
        ep_steps_list.append(ep_steps)

        elapsed = time.time() - t_start
        status = "FAIL" if ep_failed else f"OK ({ep_steps} steps)"
        print(f"  ep {ep:3d}: {status}  [{elapsed:.0f}s]")

    elapsed = time.time() - t_start
    fail_rate = tds_fail_count / n_episodes * 100
    avg_steps = np.mean(ep_steps_list)

    print(f"\n--- {env_name} Results ---")
    print(f"  Episodes: {n_episodes}")
    print(f"  TDS failures: {tds_fail_count}/{n_episodes} ({fail_rate:.1f}%)")
    print(f"  Avg steps/ep: {avg_steps:.1f} (max={env_class.STEPS_PER_EPISODE})")
    print(f"  Total time: {elapsed:.0f}s ({elapsed/n_episodes:.1f}s/ep)")
    return fail_rate


if __name__ == "__main__":
    n_ep = 20

    # Test Kundur
    from env.andes.andes_vsg_env import AndesMultiVSGEnv
    run_env(AndesMultiVSGEnv, "Kundur (4 VSG)", n_episodes=n_ep)

    # Test NE
    from env.andes.andes_ne_env import AndesNEEnv
    run_env(AndesNEEnv, "New England (8 VSG)", n_episodes=n_ep)
