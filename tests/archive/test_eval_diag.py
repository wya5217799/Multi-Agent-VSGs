"""Quick eval diagnostic: check episode length and trajectory."""
import numpy as np
from env.andes.andes_vsg_env import AndesMultiVSGEnv
from agents.sac import SACAgent

N = 4
a0 = (0 - AndesMultiVSGEnv.DM_MIN) / (AndesMultiVSGEnv.DM_MAX - AndesMultiVSGEnv.DM_MIN) * 2 - 1
a1 = (0 - AndesMultiVSGEnv.DD_MIN) / (AndesMultiVSGEnv.DD_MAX - AndesMultiVSGEnv.DD_MIN) * 2 - 1
FIXED = np.array([a0, a1], dtype=np.float32)

# No control, LS1
print("=== No control, 2.0 p.u. LS ===")
env = AndesMultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
env.reset(delta_u={"PQ_0": -2.0})

for step in range(AndesMultiVSGEnv.STEPS_PER_EPISODE):
    act = {i: FIXED.copy() for i in range(N)}
    obs, rew, done, info = env.step(act)
    if step < 5 or step % 10 == 0 or done:
        freq = info["freq_hz"]
        df = np.max(np.abs(freq - 50.0))
        print(f"  Step {step:3d}: t={info['time']:.3f}, Δf_max={df:.4f} Hz, fail={info['tds_failed']}")
    if done:
        print(f"  Episode ended at step {step}")
        break

print(f"\nTotal steps: {step+1}, final time: {info['time']:.3f}")
