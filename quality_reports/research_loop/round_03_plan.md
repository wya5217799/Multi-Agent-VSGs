# R03 Plan

**Status**: DRAFT
**Date**: 2026-05-07
**Trigger**: R02 verdict — std 改善但未达 G5; H₀ 通; 需架构改动 + 长 train

## 上轮
R02: 5seed × 200ep lam=0.01 (resume R01) final_R -1059±135, action std 0.122±0.019.
H₀ probe v2: 4/4 PASS. G1-G6 仍 NOT MEASURED (eval driver 待建).

## 假设
H1 (R03 主验): 500ep + 三路架构 smoke 中至少 1 路 PASS, R04 整合训练 std →物理 ≤ 1.0
H2 (smokes): INCLUDE_OWN_ACTION_OBS dim 7→9 训练不爆; governor wiring build pass
H3: paper_grade eval driver 缺失需 R04 优先重建 (recovery §E)

## 跑啥 (K=7, fit count = min(8 cpu, 13 ram) - 1=7 (probe takes 1 thread 但 ANDES 多线程))

```
exp1: r03_governor_wire_probe   cpu, ~5 min, priority=10
      cmd: python scripts/research_loop/r03_governor_wire_probe.py
      gates Phase B physical impl (R04 wire into V3 env)

exp2: r03_INCLUDE_OWN_ACTION_OBS_smoke  gpu, ~10 min, priority=8
      cmd: DEVICE=cuda LAMBDA_SMOOTH=0.01 INCLUDE_OWN_ACTION_OBS=1 \
           python train_andes_v2.py --episodes 30 --seed 42 --phi-d 0.05 \
           --save-dir results/research_loop/r03_obs9_smoke_s42
      OBS_DIM 7→9 (加 last_action), 不能 resume R02 (ckpt actor 输入维度不匹配), fresh 训
      期望: 训练不爆, ep30 末 reward 与 R01 ep30 同量级 (~-3000~-5000)

exp3-7: r03_A_lam0p01_500ep_resume_s{42-46}  gpu × 5, ~60 min wall (5-way), priority=9
      cmd: DEVICE=cuda LAMBDA_SMOOTH=0.01 PYTHONUNBUFFERED=1 \
           python train_andes_v2.py --episodes 300 --seed {S} --phi-d 0.05 \
           --resume results/research_loop/r02_A_lam0p01_200ep_s{S} \
           --save-dir results/research_loop/r03_A_lam0p01_500ep_s{S}
      effective: R02 200ep + R03 300ep = 500ep total
      期望: action std @ ep500 ≤ 0.08 (从 R02 0.122 再降 35%); final_R 改善 30%
```

## 期 (G1-G6)
- G5 (smoothness 物理 std): R03 train 末 std ≤ 0.10 (normalized) → 物理 ≤ 4.0 (R02 4.88)
- exp1: governor add 不抛 ImportError, ss.IEEEG1.n=4, ss.EXST1.n=4
- exp2: critic_loss 不爆 + ep30 reward 不偏离 R01 ep30 baseline > 50%

## 双 metric (R03 强制)
```
exp r03_A 500ep (5 seed):
  train_reward (final ep500, mean±std): TBD
  paper_grade  (cum_rf @50 fixed seeds): NOT MEASURED YET (R04 build eval driver)
  6axis_overall: NOT MEASURED YET
```

## 不行咋办
- exp1 (governor) build error → 写 incident, R04 改用 V3 case 文件级注入 (修 .xlsx)
- exp2 (obs+last_action) 训练发散 → audit, 改 obs encode 用 [-1,1] clip 不直接 raw action
- exp3-7 reward 不再升 (vs R02) → SAC plateau, R04 加 lr scheduler / target_entropy 调整

## 不上的
- ❌ 6-axis paper_grade eval (依赖缺失 _eval_paper_specific.py, R04 重建; .pyc compile cache 存在但 source 丢)
- ❌ PHI_F sweep (留 R04, 先验 obs/governor 哪个有效)
- ❌ V3 env 重写 (未来 R05+)

## §note
- 总 wall ≈ 60 min (K=7, 5seed 500ep resume 主导)
- VRAM: 6 GPU × ~0.4 GB ≈ 2.4 GB / 8 GB
- exp2 (obs9) fresh 训不能 resume — 从 0ep 起跑, 30ep smoke 仅验 build
- recovery §E (eval driver 重建) 入 R04 priority

## R04 预告 (R03 verdict 时定)
- 主: 重建 V2-compatible eval driver (paper_grade @50 fixed seeds 6-axis), 跑 R03 5 ckpt
- 辅: PHI_F sweep / governor wire 真整合 / obs9 5seed × 200ep

---

# §Done (post-execution append)
(待 R03 7 路完成后填)
