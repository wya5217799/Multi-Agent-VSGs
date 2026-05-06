# R02 Plan

**Status**: DRAFT
**Date**: 2026-05-07
**Trigger**: R01 verdict — λ 三档 50ep 区分不出, 必须 200ep 出 paper_grade; H₀ probe schema bug 重做

## 上轮
8/9 SAC arms exit 0, 1 BC probe 半 PASS.
final_R (lam=0.01 5seed mean±std): -2638 ± 651
action std (mean of 4 agents @ ep 49): 0.18-0.20 三档全收敛, 物理 ~7 vs paper ~0 gap 3-7×
G1-G6: 全 NOT MEASURED (50ep 太短, 不跑 paper_grade)

## 假设
H1 (R02 主验): LAMBDA_SMOOTH=0.01 + 200ep × 5seed → paper_grade @50 fixed seeds 显著改善 (smoothness axis ≥ 0.85, ΔH/ΔD std ≤ 4 物理)
   理由: R01 50ep 末 std 已经在收敛趋势 (0.6→0.2), 加 150 ep 应再降一半. 5seed 给 mean±std.
H2 (R02 辅): H₀ ∈ {20,30,50,80} 至少 1 个 pflow 收敛 + 5step TDS smoke 不发散
   理由: R01 probe schema bug 修后, 物理可行性是真实数据.

## 跑啥 (K=6, 全占 vCPU 6/8)

```
exp1: r02_C_pre_h0_sweep_v2  cpu probe ~5 min priority=10
      cmd: /home/wya/andes_venv/bin/python scripts/research_loop/r02_h0_sweep_v2.py
      out: results/research_loop/r02_C_pre_h0_sweep_v2.json
      rationale: 修 R01 probe disturbance schema bug, gates Phase C 决策

exp2-6: r02_A_lam0p01_200ep_resume_s{42-46}  gpu × 5  ~22 min wall (5-way) priority=9-8
      cmd: DEVICE=cuda LAMBDA_SMOOTH=0.01 PYTHONUNBUFFERED=1 python scenarios/kundur/train_andes_v2.py
           --episodes 150 --seed {S} --phi-d 0.05
           --resume results/research_loop/r01_A_lam0p01_s{S}
           --save-dir results/research_loop/r02_A_lam0p01_200ep_s{S}
      effective: 50ep (R01) + 150ep (R02) = 200ep total
      rationale: 复用 R01 ckpt 节省 50ep wall (per memory feedback_training_resume.md);
                 200ep 出 paper_grade signal; PYTHONUNBUFFERED 防 stdout buffer 误判
```

## 期 (跟 G1-G6)
- G5 (smoothness): action std @ ep 200 ≤ 0.10 (从 R01 0.18 降一半)
- 6axis_overall (5seed mean): ≥ 0.10 (从 R0 baseline 0.036 提 3×)
- exp1 H₀ sweep: 至少 H₀=30 收敛 + TDS 不发散

## 双 metric (R02 强制实测)
```
exp lam=0.01 200ep (5 seed):
  train_reward (R_avg10 ep190-200, 5 seed mean±std): TBD
  paper_grade  (cum_rf @50 fixed test seeds, daemon 自动 6-axis): TBD
  6axis_overall: TBD  G=ABCDEF
```

## 不行咋办
- 200ep std 仍 ≥ 0.15 → smoothing 路径失效, R03 pivot:
  - 加 INCLUDE_OWN_ACTION_OBS (R02 不上, 改 obs dim 风险高, 放 R03)
  - 改 reward 公式: 直接 penalty action change 而非 delta change
- exp1 H₀=20 仍 fail → 收紧 ΔH range axis 上限到 H₀∈[30,80]
- 5seed std 仍 >>500 → 训练随机性大, R03 加 lr scheduler / target_entropy adjust

## 不上的
- ❌ Phase B governor 启用 (推 R03 — 改 V2/V3 env 加 IEEEG1+EXST1 wiring 是大动, 不在 R02 K=6 内)
- ❌ GPU stress 大网络 (R01 已证明跑得动, ROI 弱不进 baseline)
- ❌ λ sweep 细分 (R01 50ep 三档无差, 200ep 大概率仍无差)
- ❌ Phase A 全新训练 (用 resume 节约时间)

## §note
- 总 wall ≈ 22-30 min (K=6)
- VRAM: 5 GPU × ~0.4 GB ≈ 2 GB / 8 GB (论文 net 物理上限)
- CPU 6/8 占用, 留 2 槽 buffer

---

# §Done (post-execution append)
(待 R02 6 路完成后填)
