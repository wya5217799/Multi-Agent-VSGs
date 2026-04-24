"""对比分析 v1 (收敛) vs v4 (不收敛) 训练数据"""
import json
import numpy as np

# v4 训练日志
with open("results/andes_kundur_models_v4/training_log.json") as f:
    v4 = json.load(f)

r4 = v4["total_rewards"]

print("=" * 60)
print("V4 Training Analysis (500 ep)")
print("=" * 60)

# 分段统计
for start in range(0, 500, 50):
    end = min(start + 50, len(r4))
    seg = r4[start:end]
    print(f"  Ep {start:3d}-{end:3d}: mean={np.mean(seg):7.1f}  std={np.std(seg):6.1f}  "
          f"min={min(seg):7.1f}  max={max(seg):7.1f}")

# 趋势: 前100 vs 后100
early = np.mean(r4[:100])
late = np.mean(r4[-100:])
print(f"\nFirst 100 ep avg: {early:.1f}")
print(f"Last  100 ep avg: {late:.1f}")
print(f"Improvement: {late - early:+.1f} ({(late-early)/abs(early)*100:+.1f}%)")

# Per-agent 分析
print("\nPer-agent reward trajectory:")
for i in range(4):
    r = v4["episode_rewards"][str(i)]
    e100 = np.mean(r[:100])
    l100 = np.mean(r[-100:])
    print(f"  Agent {i}: first100={e100:.1f} -> last100={l100:.1f} (delta={l100-e100:+.1f})")

# 检查 reward 方差 (高方差 = 策略不稳定)
print(f"\nReward std (全局): {np.std(r4):.1f}")
print(f"Reward std (last 100): {np.std(r4[-100:]):.1f}")

# 检查是否有大量极端值
bad_eps = sum(1 for r in r4 if r < -150)
print(f"\nExtreme bad episodes (< -150): {bad_eps}/{len(r4)} ({bad_eps/len(r4)*100:.1f}%)")
