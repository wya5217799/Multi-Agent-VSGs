# R01 Verdict

**Date**: 2026-05-07
**Status**: DONE (9/9 exit 0)
**Wall**: 15:20-15:36 UTC (~16 min total, 7-way parallel)
**Trigger**: handoff 2026-05-07_andes_6axis_recovery_handoff.md

## 一句话
50 ep × 5 seed × LAMBDA_SMOOTH=0.01 训跑完, 但 **action_std 全 collapse 到 ≈0.18 (物理 ~7)** 无法
分辨 λ 三档 (0.001/0.01/0.1 final reward 差 <1%). GPU stress 证明 batch=2048+hidden=1024 跑得动且
wall 反快 10%. BC probe Phase B (governor add) PASS, Phase C-pre 因 probe bug 全 fail (incident 已写).

## 实测 (8 ckpt × 1 probe)

| arm | λ | seed | final_R (ep50) | best_R | std_e49 | TDS_fail% | freq_peak | wall(s) | ckpts |
|---|---|---|---|---|---|---|---|---|---|
| lam0p001_s42 | 0.001 | 42 | -1747.2 | -200 | 0.185 | 8.0 | 0.98 | 720 | 8 |
| lam0p01_s42 | 0.01 | 42 | -1741.6 | -200 | 0.182 | 8.0 | 0.98 | 708 | 8 |
| lam0p01_s43 | 0.01 | 43 | -2473.0 | -200 | 0.195 | 10.0 | 0.98 | 695 | 8 |
| lam0p01_s44 | 0.01 | 44 | -2346.2 | -200 | 0.185 | 8.0 | 0.93 | 716 | 8 |
| lam0p01_s45 | 0.01 | 45 | -3121.7 | -200 | 0.185 | 10.0 | 0.95 | 704 | 8 |
| lam0p01_s46 | 0.01 | 46 | -3507.4 | -200 | 0.182 | 10.0 | 0.92 | 700 | 8 |
| lam0p1_s42 | 0.1 | 42 | -1753.6 | -200 | 0.180 | 8.0 | 0.98 | 697 | 8 |
| stress_b2048_h1024 | 0.01 | 42 | -4529.8 | -200 | 0.208 | 8.0 | 0.78 | **652** | 8 |
| BC_probe | — | — | (sanity) | — | — | — | — | ~10 | — |

## 强制双 metric (per OPT-3)
```
exp lam0p01 (5 seed):
  train_reward (final ep50, 5 seed mean±std): -2638 ± 651
  paper_grade  (cum_rf @50 fixed test seeds): NOT MEASURED (50ep 太短不稳)
  6axis_overall: NOT MEASURED (smoothness axis = action std 0.18 物理 ~7 = paper ~0 的 3-4× gap)
```
spec 要求双 metric. 50ep smoke **不下 H1 验证结论**. R02 200ep 跑后才出 paper_grade.

## 假设验证

H1 (LAMBDA_SMOOTH 改善 smoothness): **不可判定 @ 50ep**.
- 三档 λ final reward 差 <1%, action std 全 0.18-0.20.
- root: SAC alpha 自动调小 → policy 在 50ep 内 deterministic collapse, smoothing penalty 信号被淹没.
- R02 200ep + 5seed mean±std 才能验.

H2 (λ ∈ {0.001, 0.01, 0.1} 有 sweet spot): **暂无证据**, 50ep 区分不出.
- 决策: R02 选 lam=0.01 (recovery plan §A.1 default, 5seed 已跑作 baseline). 不再 sweep 细分.

H3 (Phase B/C 可启): **半 PASS**.
- Phase B (IEEEG1+EXST1 add API + pflow): ✅ 全 ok, R02 可启
- Phase C-pre (H₀ sweep): ❌ 全 fail, root = probe disturbance dict schema 错 (`{"bus":7,...}` 不是合法 pq_idx). 见 [incident](incidents/r01_h0_probe_disturbance_bug.md). R02 改用 `delta_u=None` 重做.

## 对比

vs 上轮: 无 (R0).
vs V2 5seed baseline (老 results/andes_v2_balanced_seed42-46): 没有直接 same-context 对比,
但量级相似 (V2 5seed final ~-2000~-3500 范围). LAMBDA_SMOOTH 任档 50ep 没显著推动 reward.

vs 论文 (Fig.7/9 视觉): action std 物理 7 vs 论文 ~0 (gap 3-7×).
50ep + LAMBDA_SMOOTH 单 lever 不够.

## GPU stress 实测 (副产品)

| 配置 | wall (s) | final_R | TDS% | std_e49 |
|---|---|---|---|---|
| 论文 net [128⁴] + batch 256 (论文 baseline) | 695-720 | -1741~-3507 | 8-10 | 0.18 |
| stress [1024⁴] + batch 2048 (off-paper) | **652** | -4530 | 8 | 0.21 |

- batch 2048 + hidden 1024: wall **快 10%** (GPU 真起作用, 分摊 CPU 瓶颈)
- 但 50ep 大模型不收敛 (final 比 baseline 差 ~2×)
- VRAM: 启动 ~1.5 GB → 训练中估 3-5 GB (单 stress arm)
- **R02 不上大网络** — 偏离论文 Table I, 短 train 不收敛, ROI 弱

## Audit 标记

- **Best reward callback = -200** 全 8 arms 一致, 是 monitor 阈值/hardcode 痕迹, 非真 best.
  待 R02 检查 `utils/monitor.py::on_best_reward` 实现.
- 训练 log 默认 stdout 块缓冲, 实测 0 字节 → 误判 hang. R02 加 `python -u` (env var `PYTHONUNBUFFERED=1`).

## 接下轮 → R02

主 thrust: 200ep × 5seed lam=0.01 出 paper_grade @ daemon 自动 6-axis (真 H1 验证).

R02 candidates (K=7, 全占 8 vCPU 槽):
1. **r02_C_pre_h0_sweep_v2** (priority 10, cpu, ~5 min) — 修 probe disturbance schema bug 重跑 H₀∈{20,30,50,80}
2. **r02_A_lam0p01_200ep_s{42-46}** (priority 9-8, gpu × 5, ~30 min wall 5-way) — paper_grade 真信号
3. **r02_B_governor_smoke_s42** (priority 7, gpu, ~10 min) — V2 env + IEEEG1+EXST1 启用, 1seed×30ep 看 max_df

R02 G5 期望: 200ep 末 action std 物理 ≤ 4.0 (从 50ep 的 7 降一半).
R02 G2/G3 期望: governor 启用后 no-ctrl baseline max_df 0.6 → ≤ 0.30.

## 不行咋办
- R02 200ep 全 std 还是 7+ → smoothing 路径失效, pivot R03: action obs 加 last action (现 spec 仍待加, INCLUDE_OWN_ACTION_OBS env var 未实施)
- governor 启用 max_df 不降 → root cause 不在 D=0 GENROU, pivot R03: 改 V3 env 加 turbine governor
- H₀ probe v2 仍 fail → 看 V2 env 物理本身

## Cross-ref
- [round_01_plan.md](round_01_plan.md) — R01 plan
- [incidents/r01_h0_probe_disturbance_bug.md](incidents/r01_h0_probe_disturbance_bug.md) — H₀ probe bug
- [recovery plan](../plans/2026-05-07_andes_6axis_recovery.md) §A/B/C — context
- 8 arms ckpt: `results/research_loop/r01_A_*/`
