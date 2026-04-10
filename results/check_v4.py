import json, numpy as np

with open("results/andes_kundur_models_v4/training_log.json") as f:
    log = json.load(f)

rewards = log["total_rewards"]
ec = log["episodes_completed"]
ts = log["total_steps"]
ir = log["interrupted"]

print(f"Episodes completed: {ec}")
print(f"Total steps: {ts}")
print(f"Interrupted: {ir}")
print(f"First 10 ep avg:  {np.mean(rewards[:10]):.2f}")
print(f"Last 10 ep avg:   {np.mean(rewards[-10:]):.2f}")
print(f"Last 50 ep avg:   {np.mean(rewards[-50:]):.2f}")
print(f"Best reward:  {max(rewards):.2f} @ ep {np.argmax(rewards)}")
print(f"Worst reward: {min(rewards):.2f}")
print("--- Per-agent last 50 ep avg ---")
for i in range(4):
    r = log["episode_rewards"][str(i)]
    print(f"  Agent {i}: {np.mean(r[-50:]):.2f}")
