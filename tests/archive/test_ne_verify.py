"""Phase 4: Verify the TDS.busted fix works"""
import sys, os
import numpy as np
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.getcwd())

from env.andes.andes_ne_env import AndesNEEnv

print("=" * 60)
print("VERIFY 1: NE env reset + 50 steps with zero action")
print("=" * 60)

env = AndesNEEnv(random_disturbance=True)
env.seed(42)
obs = env.reset()
print(f"[OK] Reset: t={env.ss.dae.t:.2f}, busted={env.ss.TDS.busted}")

actions = {i: np.array([0.0, 0.0]) for i in range(8)}
total_reward = 0
for step in range(50):
    obs, rewards, done, info = env.step(actions)
    r = sum(rewards.values())
    total_reward += r
    if info["tds_failed"]:
        print(f"  Step {step}: TDS FAILED at t={info['time']:.2f}")
        break
    if step % 10 == 0:
        freq = info["freq_hz"]
        print(f"  Step {step}: t={info['time']:.2f}, r={r:.2f}, "
              f"freq=[{freq.min():.4f}, {freq.max():.4f}] Hz")
    if done:
        print(f"  Episode done at step {step}")
        break

print(f"\nTotal reward: {total_reward:.2f}")

print("\n" + "=" * 60)
print("VERIFY 2: 5 episodes with random actions (like training)")
print("=" * 60)

for ep in range(5):
    env_ep = AndesNEEnv(random_disturbance=True, comm_fail_prob=0.1)
    env_ep.seed(42 + ep)
    obs = env_ep.reset()

    ep_reward = 0
    tds_failed = False
    steps_done = 0

    for step in range(50):
        act = {i: np.random.uniform(-1, 1, size=2) for i in range(8)}
        obs, rewards, done, info = env_ep.step(act)
        ep_reward += sum(rewards.values())
        steps_done += 1

        if info["tds_failed"]:
            tds_failed = True
            print(f"  Ep {ep}: TDS FAILED step {step}, t={info['time']:.2f}, "
                  f"M={np.round(info['M_es'], 1)}")
            break
        if done:
            break

    if not tds_failed:
        print(f"  Ep {ep}: OK, {steps_done} steps, reward={ep_reward:.2f}, "
              f"max_freq_dev={info['max_freq_deviation_hz']:.4f} Hz")

print("\nDone.")
