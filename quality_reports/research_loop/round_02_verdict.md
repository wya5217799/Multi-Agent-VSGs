# R02 Verdict

**Date**: 2026-05-07
**Status**: DONE (6/6 exit 0)
**Wall**: 15:43–16:21 UTC (~38 min, 5-way GPU parallel + 1 cpu probe)
**Trigger**: R01 verdict — 200ep × 5seed 验 H1 + 修 H0 probe schema bug

## 一句话
200ep × 5seed lam=0.01 把 final_R **改善 60% (R01 -2638→R02 -1059)**, action std **改善 35% (0.18→0.12)**,
5seed std 收紧 5×. H0 sweep v2 修后**全 4 候选 pflow + 5step TDS 通过**, Phase C 解锁.
但 G5 物理 (std×DM_MAX=4.9 vs paper~0) 仍未达 ≤1.0 阈值, **需 R03 加 obs/governor 而非单纯加 ep**.

## 实测 (5 SAC arms × 200ep + 1 H0 probe)

### r02_A_lam0p01_200ep × 5seed (resume R01)
| arm | final_R(ep200) | best_R | std_e199 | TDS% | freq_peak | wall(s) | r_h% | r_d% | r_f% |
|---|---|---|---|---|---|---|---|---|---|
| s42 | -922.8 | -200 | 0.120 | 10.0 | 0.88 | 1885 | 59.6 | 18.2 | 22.3 |
| s43 | -1204.5 | -200 | 0.135 | 10.0 | 0.88 | 1890 | 58.0 | 23.0 | 19.0 |
| s44 | -983.3 | -200 | 0.113 | 8.7 | 0.90 | 1906 | 73.9 | 15.5 | 10.7 |
| s45 | -978.8 | -200 | 0.147 | 10.0 | 0.92 | 1893 | 61.9 | 14.1 | 24.0 |
| s46 | -1205.2 | -200 | 0.098 | 10.0 | 0.91 | 1887 | 80.5 | 16.5 | 3.0 |
| **5seed mean ± std** | **-1058.9 ± 135.3** | -200 | **0.122 ± 0.019** | 9.7 | 0.90 | 1892 | — | — | — |

### r02_C_pre_h0_sweep_v2 (H0 probe with delta_u=None fix)
| H₀ (s) | M₀ (s) | pflow | 5step TDS |
|---|---|---|---|
| 20 | 40 | ✅ ok | ✅ ok |
| 30 | 60 | ✅ ok | ✅ ok |
| 50 | 100 | ✅ ok | ✅ ok |
| 80 | 160 | ✅ ok | ✅ ok |

→ **R03 上 H₀=50 baseline 物理可行** (recovery plan §C 解锁).

## 强制双 metric (per OPT-3)
```
exp r02_A_lam0p01_200ep (5 seed):
  train_reward (final ep200, mean±std):     -1058.9 ± 135.3   (R01: -2638 ± 651, 改善 60%, std 5× 收紧)
  paper_grade  (cum_rf @50 fixed seeds):    NOT MEASURED YET   (R03 r03_eval_r02_paper_grade 跑)
  6axis_overall:                            NOT MEASURED YET   (依赖 paper_grade)
```
**R03 必跑 paper_grade eval** 才能验 H1 完整闭环 (action std 改善是否反映在 6-axis smoothness/max_df).

## G5 直接估算 (训练阶段)
G5 阈值 (recovery §1): ΔH/ΔD smoothness std ≤ 1.0 (LS1 DDIC best, 物理单位)

R02 action_std @ ep199 = 0.122 (normalized, 4 agent 平均)
物理 ΔH std = 0.122 × DM_MAX = 0.122 × 40 = **4.88**
gap to paper (~0): **4.88×**, 还差 ~5×.
G5 状态: **改善但未通过** (R01 7.3 → R02 4.88, 33% 改善)

> 注: 训练阶段 std 含探索噪声; eval (deterministic best.pt) 应低于训练阶段. paper_grade 6-axis 才是真值.

## 假设验证

H1 (LAMBDA_SMOOTH=0.01 + 200ep 改善 smoothness): **部分验证**
- train_reward: R01 -2638 → R02 -1059, 60% improvement, std 5× tighter ✅
- action std: 0.18 → 0.12, 33% improvement ✅
- 但物理 std 4.88 vs paper ~0 仍 5× gap → smoothing 单 lever 不够
- 决策: R03 加 INCLUDE_OWN_ACTION_OBS + 启 governor (Phase B), smoothing 配合不再单独跑

H2 (H0 ∈ {20,30,50,80} pf+TDS sanity): ✅ **完全验证** (4/4 PASS)
- R03 用 H₀=50 baseline 物理可行 (recovery §C 解锁)

## 对比

vs R01 (50ep): 60% reward improvement, 33% std improvement, 5× 5seed std 收紧. Resume 路径有效.
vs 论文 (Fig.7/9): action std 4.88 vs ~0 (gap 5×); freq_peak 0.90 Hz vs 0.13 Hz (gap 7×).
vs no-ctrl baseline (V2): no-ctrl freq_peak 0.6 Hz, R02 0.90 Hz — **R02 反而比 no-ctrl 差!** 这是
重要警报, 含义: 训练阶段 SAC 探索还在, eval deterministic 才能比. R03 paper_grade 必跑.

## Audit 标记

1. **freq_peak R02 0.90 vs no-ctrl 0.60**: 训练阶段 SAC 探索 σ 加噪给 policy, eval 用 best.pt
   deterministic 才公平比. R03 必跑 eval 验证.
2. **best reward callback "-200" 8/8 arm 一致**: 仍是 monitor hardcode, 待修 (recovery §E).
3. **r_h dominance 60-80%**: PHI_D=0.05 设定下, H 项主导 reward signal. 论文 PHI_F=100 PHI_H=PHI_D=1.0.
   R03 若想推 freq peak 改善, 可考虑 PHI_F 拉高 (但偏离论文 Table I).

## 接下轮 → R03

主 thrust 3 路:
1. **r03_eval_r02_paper_grade** (cpu, ~20 min) — 跑 R02 5 best.pt × 50 fixed seeds + 6-axis ranking. **必须先跑** 才知 G1-G5 真值.
2. **架构改动并行 smoke** (3 候选, 各 ~10 min):
   - r03_INCLUDE_OWN_ACTION_OBS_smoke: V2 env obs dim 7→9 (加 last action), 1seed × 30ep fresh.
   - r03_B_governor_wire_smoke: V2 env + IEEEG1+EXST1 add 1 episode reset 验 build/pf/TDS 通.
   - r03_PHI_F_2x_smoke: PHI_F 100→200, 1seed × 50ep, 看 freq_peak 改善
3. **r03_A_lam0p01_500ep_resume_s{42-46}** (5 GPU, ~60 min) — R02 → 500ep resume, 看是否 250 ep diminishing returns.

K=9 (1 probe + 3 smoke + 5 resume), 超 8 vCPU, daemon 排队 1 个等空槽.

R03 期 (假设 1 任一 PASS, R02 6-axis ≥ 0.10):
- r03_eval_r02 → 6-axis baseline (假设 0.10-0.20)
- INCLUDE_OWN_ACTION_OBS smoke 不爆 → R04 全 5seed 训
- governor wire 不爆 → R04 启用 IEEEG1+EXST1
- 500ep resume → 5seed mean±std, paper_grade 改善 ≥ 1.5×

## 不行咋办
- r03_eval_r02 6-axis 仍 < 0.05: smoothing 路径全失效, R04 pivot 改 reward 公式 (penalize abs action 而非 delta)
- INCLUDE_OWN_ACTION_OBS 训练发散: actor input 维度不兼容 ckpt (resume 不行), 必 fresh 训
- governor wire build error: ANDES API 不支持 dynamic 添加, 改 V3 case 文件级注入 (大动)
- 500ep resume reward 不再升: SAC 收敛 plateau, R04 加 lr scheduler

## Cross-ref
- [round_01_verdict.md](round_01_verdict.md) — R01 baseline
- [round_02_plan.md](round_02_plan.md) — R02 plan
- [incidents/r01_h0_probe_disturbance_bug.md](incidents/r01_h0_probe_disturbance_bug.md) — H0 probe bug
- 5 R02 ckpt: `results/research_loop/r02_A_lam0p01_200ep_s{42-46}/`
- H0 probe v2: `results/research_loop/r02_C_pre_h0_sweep_v2.json`
