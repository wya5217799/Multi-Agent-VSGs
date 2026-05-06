# R04 Plan

**Status**: DRAFT
**Date**: 2026-05-07
**Trigger**: R03 verdict — 6-axis 真闭环出 mean overall=0.035, 4/6 axis=0; PHI_D=0.05 偏 paper 20× 暴露; 需解耦算法 vs 实现.

## 上轮
R03 5seed 500ep mean overall=0.035; smoothness axis 0.7-0.9 接近 paper, max_df/final_df/settling/range 全 0; H/D collapse 部分破除 (双向变动出现).
G5 进度: 物理 std R02 4.88 → R03 5.8 (反升). 单纯加 ep 不再有效.

## 假设
H1 (R04 主验): **PHI_D=0.05→1.0** 修后, agent 学到正向 ΔD → max_df axis 改善 (0→0.3)
   理由: r_d 信号弱 20× 让 SAC 不在乎 D, 修后 reward 公式 paper-faithful
H2 (解耦 算法 vs 实现): adaptive controller (K_H=10/K_D=400, no SAC) 6-axis ≥ 0.5 → ANDES OK 是算法问题; < 0.05 → 实现/平台问题
H3 (governor 物理改善): V3 env (V2 + IEEEG1+EXST1) no-ctrl 状态下 max_df 从 0.6 Hz 降到 ≤ 0.3 Hz
H4 (obs9 修后跑通): obs_dim env-var 读 patch 后, INCLUDE_OWN_ACTION_OBS=1 训练不报 shape

## 跑啥 (K=8, 物理饱和 32 vCPU)

```
exp1: r04_adaptive_baseline_eval        cpu, ~5 min, priority=10
      cmd: python scripts/research_loop/r04_adaptive_baseline_eval.py
      out: results/research_loop/eval_r04_adaptive/
      gates 算法 vs 实现 解耦 (H2)

exp2: r04_governor_V3_smoke_s42         gpu, fresh 30ep, ~10 min, priority=9
      cmd: DEVICE=cuda LAMBDA_SMOOTH=0.01 PYTHONUNBUFFERED=1 \
           python scenarios/kundur/train_andes_v3.py --episodes 30 --seed 42 --phi-d 1.0 \
           --save-dir results/research_loop/r04_V3_smoke_s42
      gates V3 env training feasibility (H3, H4)

exp3-7: r04_A_PHI_D_1p0_5seed_200ep_s{42-46}  gpu × 5, fresh 200ep, ~30 min wall, priority=8
      cmd: DEVICE=cuda LAMBDA_SMOOTH=0.01 PYTHONUNBUFFERED=1 \
           python scenarios/kundur/train_andes_v2.py --episodes 200 --seed {S} --phi-d 1.0 \
           --save-dir results/research_loop/r04_A_phid1p0_s{S}
      ⚠ 不 resume R03 (R03 用 PHI_D=0.05 训, ckpt 不兼容 PHI_D=1.0 reward landscape)
      H1 主验 + 5seed mean±std

exp8: r04_obs9_smoke_v2_s42             gpu, fresh 30ep, ~10 min, priority=7
      cmd: DEVICE=cuda INCLUDE_OWN_ACTION_OBS=1 PYTHONUNBUFFERED=1 \
           python scenarios/kundur/train_andes_v2.py --episodes 30 --seed 42 --phi-d 1.0 \
           --save-dir results/research_loop/r04_obs9_smoke_s42
      H4: train_andes obs_dim 修后 SACAgent 启动不爆 shape error
```

总 wall ≈ 35 min (5-way 200ep dominates). RAM 6×1.5+0.5 ≈ 9.5 / 24 GB.

## 期 (G1-G6)
- exp1 (adaptive): 6-axis overall ≥ 0.05 (3× no_ctrl), 至少 max_df axis ≥ 0.2
- exp2 (V3): 训练不爆 + 末 ep no-ctrl-eval max_df 改善 ≥ 30%
- exp3-7 (PHI_D=1.0): 5seed mean overall ≥ 0.05, ΔD 锯齿 axis ≥ 0.7 保持, action mu **不再全负**
- exp8 (obs9): 训练不报 shape error, ep30 末 reward 与 R01 ep30 量级 (~-3000)

## 双 metric (R04 强制 - 用 L1 6 段模板)
```
exp r04_A_phid1p0 (5 seed):
  train_reward (final ep200, mean±std):    TBD
  paper_grade (5seed mean overall):        TBD (走 r04_eval_r04_PHI_D_fix 闭环)
  6axis_overall geometric mean:            TBD
  ranking vs r04_adaptive / r03_lam0p01:   TBD
```

## L4 副线 (与训练并行做)
- archive 老 eval scripts 进 `scenarios/kundur/_legacy_2026-04/`:
  - `_eval_paper_grade_andes{,_one,_parallel,_warmstart}.py` × 4
  - `_phase{3,4}_eval{,_v2}.py` × 2-3
  - `_phase9_shared_*_reeval.py` × 3
  - `_re_eval_best_ckpts.py`
  - `_v2_{d0,linex}_sweep.py` × 2
  - `_run_v2_5seed.sh`
- 唯一 eval 入口: `scripts/research_loop/eval_paper_spec_v2.py`
- 在 R04 verdict 时 mv (daemon 跑训练时 AI 主上下文做)

## 不行咋办
- exp1 adaptive 6-axis ≥ 0.5: ✅ 平台 OK, R05 全 thrust 改 SAC reward 公式 / 加 lr scheduler / target_entropy
- exp1 adaptive < 0.05: ⚠ 实现/平台问题, R05 必查 V2 env GENCLS M/D 直接调 vs paper ESS P 注入语义
- exp2 V3 governor 训练发散: 写 incident, R05 不上 governor, 改 V3 env 加 turbine droop coefficient 不全用 IEEEG1
- exp3-7 PHI_D=1.0 reward 反而差: 验证 0.05 是否其实是个 sweet spot? R05 sweep PHI_D∈{0.05, 0.2, 0.5, 1.0}
- exp8 obs9 仍报错: 检查 SACAgent / replay_buffer / network 三层 obs_dim 一致性

## 不上的
- ❌ 500ep PHI_D=1.0 (先 200ep 验, 通了 R05 上 500ep)
- ❌ PHI_D sweep 细分 (留 R05 if needed)
- ❌ V3 + obs9 + governor 全合并 (一次只测 1 变量, R05 整合)
- ❌ paper_grade_axes.py 改公式 (现公式 paper-faithful, 不动)

## §note
- AI 在 daemon 跑训练时同步做 L4 (archive 老 eval scripts) — 不阻塞 daemon
- R04 verdict 写完后会有 paper_grade 闭环 4 个比较点: no_ctrl / adaptive / R03_lam0p01 / R04_PHI_D_1p0 — same-context alignment

## R05 预告
依 R04 H2 结果定:
- 若 adaptive 通: R05 = SAC 算法改进 (target_entropy=-2 / lr scheduler / multi-task reward)
- 若 adaptive 不通: R05 = 实现深查 (V2 env 物理保真度 / paper ESS 语义对齐)

---

# §Done (post-execution append)
(待 R04 8 路完成后填)
