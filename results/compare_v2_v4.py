"""对比 v2 (收敛, 2000ep) vs kundur_v4 (不收敛, 500ep)"""
import json
import numpy as np

with open("results/andes_models_v2/training_log.json") as f:
    v2 = json.load(f)
with open("results/andes_kundur_models_v4/training_log.json") as f:
    v4 = json.load(f)

r2 = v2["total_rewards"]
r4 = v4["total_rewards"]

print("=" * 60)
print("V2 vs V4 (Kundur) — 50-episode windows")
print("=" * 60)
print(f"{'Window':>12s}  {'V2 mean':>10s}  {'V4 mean':>10s}  {'V2 std':>8s}  {'V4 std':>8s}")
for start in range(0, 500, 50):
    s2 = r2[start:start+50]
    s4 = r4[start:start+50]
    print(f"  Ep {start:3d}-{start+50:3d}  {np.mean(s2):10.1f}  {np.mean(s4):10.1f}  {np.std(s2):8.1f}  {np.std(s4):8.1f}")

print(f"\nV2 at ep 500:  avg={np.mean(r2[450:500]):.1f}")
print(f"V2 at ep 1000: avg={np.mean(r2[950:1000]):.1f}")
print(f"V2 at ep 1500: avg={np.mean(r2[1450:1500]):.1f}")
print(f"V2 at ep 2000: avg={np.mean(r2[1950:2000]):.1f}")

# Check step counts
s2 = v2["total_steps"]
s4 = v4["total_steps"]
e2 = v2.get("episodes_completed", len(r2))
e4 = v4.get("episodes_completed", len(r4))
print(f"\nV2: {e2} ep, {s2} steps -> {s2/e2:.1f} steps/ep")
print(f"V4: {e4} ep, {s4} steps -> {s4/e4:.1f} steps/ep")

# Per-agent comparison at ep 0-100 and ep 400-500
print("\nPer-agent: first 100 ep")
for i in range(4):
    r2a = np.mean(v2["episode_rewards"][str(i)][:100])
    r4a = np.mean(v4["episode_rewards"][str(i)][:100])
    print(f"  Agent {i}: V2={r2a:.1f}  V4={r4a:.1f}")

print("\nPer-agent: ep 400-500")
for i in range(4):
    r2a = np.mean(v2["episode_rewards"][str(i)][400:500])
    r4a = np.mean(v4["episode_rewards"][str(i)][400:500])
    print(f"  Agent {i}: V2={r2a:.1f}  V4={r4a:.1f}")
