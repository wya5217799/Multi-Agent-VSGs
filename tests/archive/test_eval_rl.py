"""Check RL episode trajectory data."""
import numpy as np
from env.andes.andes_vsg_env import AndesMultiVSGEnv
from agents.sac import SACAgent
import os

N = 4
agents = []
MODEL_DIR = "results/andes_models_fixed"
for i in range(N):
    agent = SACAgent(obs_dim=7, action_dim=2, hidden_sizes=[128,128,128,128],
                     buffer_size=10000, batch_size=256)
    agent.load(os.path.join(MODEL_DIR, f"agent_{i}_final.pt"))
    agents.append(agent)

a0 = (0 - AndesMultiVSGEnv.DM_MIN) / (AndesMultiVSGEnv.DM_MAX - AndesMultiVSGEnv.DM_MIN) * 2 - 1
a1 = (0 - AndesMultiVSGEnv.DD_MIN) / (AndesMultiVSGEnv.DD_MAX - AndesMultiVSGEnv.DD_MIN) * 2 - 1
FIXED = np.array([a0, a1], dtype=np.float32)

# RL control
print("=== RL control, 2.0 p.u. LS ===")
env = AndesMultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
obs = env.reset(delta_u={"PQ_0": -2.0})

times, freqs, Hvals = [], [], []
for step in range(AndesMultiVSGEnv.STEPS_PER_EPISODE):
    actions = {i: agents[i].select_action(obs[i], deterministic=True) for i in range(N)}
    obs, rew, done, info = env.step(actions)
    times.append(info["time"])
    freqs.append(info["freq_hz"].copy())
    Hvals.append(info["M_es"].copy() / 2.0)
    if step < 5 or step % 10 == 0 or done:
        df = np.max(np.abs(info["freq_hz"] - 50.0))
        H = info["M_es"] / 2.0
        print(f"  Step {step:3d}: t={info['time']:.3f}, Δf_max={df:.4f}, H={H}, fail={info['tds_failed']}")
    if done:
        print(f"  Episode ended at step {step}")
        break

times = np.array(times)
freqs = np.array(freqs)
Hvals = np.array(Hvals)
print(f"\nTime range: {times[0]:.3f} to {times[-1]:.3f}")
print(f"H range: {Hvals.min():.2f} to {Hvals.max():.2f}")
print(f"Freq range: {freqs.min():.4f} to {freqs.max():.4f}")
