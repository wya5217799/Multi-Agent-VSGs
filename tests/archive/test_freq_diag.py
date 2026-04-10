"""Quick diagnostic: check nominal frequency and disturbance response."""
import numpy as np
from env.andes.andes_vsg_env import AndesMultiVSGEnv

# Test 1: No disturbance
print("=== No disturbance ===")
env = AndesMultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
obs = env.reset()
omega = env._get_vsg_omega()
print("Nominal omega (p.u.):", omega)
print("freq_hz = omega*50:", omega * 50.0)

a0 = (0 - env.DM_MIN) / (env.DM_MAX - env.DM_MIN) * 2 - 1
a1 = (0 - env.DD_MIN) / (env.DD_MAX - env.DD_MIN) * 2 - 1
act = {i: np.array([a0, a1], dtype=np.float32) for i in range(4)}

for step in range(3):
    obs, rew, done, info = env.step(act)
    print(f"  Step {step}: t={info['time']:.3f}, freq_hz={info['freq_hz']}, fail={info['tds_failed']}")

# Test 2: Small disturbance
print("\n=== 0.3 p.u. disturbance ===")
env2 = AndesMultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
env2.reset(delta_u={"PQ_0": -0.3})
for step in range(10):
    obs, rew, done, info = env2.step(act)
    print(f"  Step {step}: t={info['time']:.3f}, freq_hz={info['freq_hz']}, fail={info['tds_failed']}")
    if done:
        break

# Test 3: 1.0 p.u. disturbance
print("\n=== 1.0 p.u. disturbance ===")
env3 = AndesMultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
env3.reset(delta_u={"PQ_0": -1.0})
for step in range(10):
    obs, rew, done, info = env3.step(act)
    print(f"  Step {step}: t={info['time']:.3f}, freq_hz={info['freq_hz']}, fail={info['tds_failed']}")
    if done:
        break
