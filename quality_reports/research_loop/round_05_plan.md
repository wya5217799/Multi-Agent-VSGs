# R05 Plan — 短-多臂 Bandit (REVISED 2026-05-07 per user methodology critique)

> ⚠ **REVISED 但未执行**. 这份 50ep + paranoid wall + axis-trend 评判规则的修订版
> 是 user 批评后我 (主上下文 AI) 改的. 但 ScheduleWakeup 在我提交修订前
> 已用更早 30ep 版本启动 daemon, **R05 实际跑的是 30ep 老版** (`round_05_verdict.md`).
>
> 关键发现: 30ep 在 R05 attractor 现象下**已经够 falsify** (8 arms 全 6-axis=0.037
> 完全并列). 我担心的"30ep 看不到 cum_rf 信号"在 hyperparam 全部失效的场景下
> 不成立 — 信号强到 30ep 就能看清"hyperparam 不是 root cause".
>
> 这份修订版保留是为了:
> 1. 方法论参考 (`SKILL.md` Explore→Exploit 段引用本文件)
> 2. 万一 R06 audits 找到 mismatch 后需要重跑某些 arm, 用 50ep 更稳

**Status**: REVISED 但未执行 (历史). 实际执行版见 git `e40ff06^` 或 `round_05_verdict.md`.
**Date**: 2026-05-07
**Trigger**:
- R04 verdict — adaptive 6-axis 0.010 = no_ctrl, 平台问题不是算法
- User .txt 批评 (2026-05-07): R01-R04 都是 "1 hyperparam × 5 seed", explore 阶段应该 "1 seed × N hyperparam"
- L4 完结 (commit `e40ff06`), eval 单一入口已锁

---

## 0. 关键修订 (vs 老 R05 plan)

| 维度 | 老 plan | 新 plan | 理由 |
|---|---|---|---|
| episode | 30 | **50** | ANDES SAC 历史 ~100 ep 才出 cum_rf 信号; 30 ep 看不到, 50 ep 安全下限 |
| wall 估计 | 10 min (8-way GPU parallel) | **30-40 min** (CPU 争用 paranoid) | ANDES TDS CPU-bound, 8 路 fight CPU; 实测优先于乐观估计 |
| Verdict 评判 | 比 cum_rf 绝对值 | **看 axis trend** (max_df ↓ / smoothness ↑) | 1-seed cum_rf 有 RNG drift (G6 surprise: 单 seed ×8.6 实是 RNG 非真改进) |
| arm 7 disturb_5x | 怀疑 paper magnitude 8× gap | **保留 (falsification probe)** | 跑出来 negative 也 falsify H2, 是有用 science (我之前误判这条要删) |

---

## 1. 上轮事实

R04 5seed PHI_D=1.0 (200ep × 5 seed):
- 6-axis overall **0.037 ± 0** (5 seed 完全并列)
- cum_rf LS1 项目 -0.150±0.020 vs paper -0.68 → **1/4 太小**
- max_df 项目 0.567 Hz vs paper 0.13 Hz → **4× 太大**
- adaptive baseline 0.010 = no_control → **控制实现/平台问题**, 不是算法
- smoothness axis 0.99 (PHI_D=1.0 修对了)
- range axis 仍 0 (ΔH/ΔD 没用足)

---

## 2. 已有 R05A 部分数据 (不丢)

state.json 显示 5 个 R05 候选 train log 存在 (daemon 死前部分跑了):

| candidate | 状态 | 数据 |
|---|---|---|
| r05_disturb_5x_s42 | done, exit_0, axes={} | 30ep 训练 final, **缺 eval** |
| r05_combo_v1_disturb5x_s42 | done, exit_0, axes={} | 同上 |
| r05_baseline_paper_s42 | killed (cancelled), partial dir | 训练未完, **不可用** |
| r05_lam_zero_s42 | killed, partial dir | 同 |
| r05_action_range_2x_s42 | killed, partial dir | 同 |

→ R05B 三种动作:
- **A 类 (eval-only, 2 candidate)**: 跑 `eval_paper_spec_v2.py --ckpt-dir` 给 disturb_5x / combo_v1_disturb5x 出 axes (~5 min total)
- **B 类 (full re-train + eval, 6 candidate)**: 50 ep × 1 seed 跑剩 6 arm (含 3 partial 重跑)
- **C 类 (eval-driver patch, 1 工作)**: target_entropy 需 sac.py patch (5 min)

---

## 3. 假设 (revised)

H1 (R05 主验): 8 单变量 sweep, 至少 1 arm 6-axis overall ≥ 0.10 (R04 0.037 的 ~3×)

H2 (磁度假设, falsification 候选):
- 老 H2: paper cum_rf 8× gap = disturbance magnitude 1/8
- **修正**: 项目 mean ~1.25 sys_pu vs paper ~1.61 sys_pu 量级一致 (`ENV_COMPARISON_V1_V2.md:70`), 不是 1/8
- 新 H2: r05_disturb_5x cum_rf 量级如果还是 1/4 → **falsify magnitude 假设**, root cause 在 reward shape / observation / 动作空间
- 新 H2 弱化: r05_disturb_5x cum_rf 量级跳到 paper 半 → confirm magnitude 不能完全解释 但是 partial driver

H3: r05_v1_env_back 6-axis ≥ R04 → V2 设计偏离 paper, 应回 V1

H4: r05_lam_zero range axis ≥ 0.30 → smoothing penalty 杀 range

H5 (新): r05_action_range_2x range axis ≥ 0.30 → ΔH/ΔD 限制是 range 杀手

---

## 4. 跑啥 (K=8 arm × 1 seed × 50 ep × CPU/GPU)

```
A 类 (eval-only, 立刻可跑, ~5 min):
  exp1.eval: r05_disturb_5x         eval_paper_spec_v2.py --ckpt-dir results/research_loop/r05_disturb_5x_s42 --suffix final --label r05_disturb_5x_s42 --out-dir results/andes_eval_paper_specific_v2_envV2_hetero/
  exp2.eval: r05_combo_v1_disturb5x 同上, ckpt-dir = r05_combo_v1_disturb5x_s42

B 类 (full train+eval, 50 ep × 1 seed, parallel ≤ 2 路 CPU 争用 paranoid):
  exp3: r05_baseline_paper           V2, PHI_D=1.0, λ=0.01, 50 ep, fresh         priority=10
        cmd: DEVICE=cpu LAMBDA_SMOOTH=0.01 python scenarios/kundur/train_andes_v2.py --episodes 50 --seed 42 --phi-d 1.0 --save-interval 25 --out-dir results/research_loop/r05b_baseline_paper_s42
  exp4: r05_phid_5x                  PHI_D=5.0                                    priority=8
        cmd: 同 + --phi-d 5.0
  exp5: r05_lam_zero                 LAMBDA_SMOOTH=0                              priority=9
        cmd: LAMBDA_SMOOTH=0 ...
  exp6: r05_v1_env_back              V1 env (M0=20, D0=4 uniform, NEW_LINE_X=0.10)  priority=10
        cmd: python scenarios/kundur/train_andes.py --episodes 50 --seed 42 --phi-d 1.0
  exp7: r05_action_range_2x          DM/DD × 2 ([-24,80] / [-30,90])               priority=8
        cmd: --dm-min -24 --dm-max 80 --dd-min -30 --dd-max 90 --phi-d 1.0
  exp8: r05_v3_governor              V3 env (V2 + IEEEG1 + EXST1)                  priority=7
        cmd: python scenarios/kundur/train_andes_v3.py --episodes 50 --seed 42 --phi-d 1.0

C 类 (patch + train+eval, 5 min build + 50 ep train):
  exp9: r05_target_entropy_low       target_entropy=-2 (强 deterministic)          priority=6
        prereq: patch agents/sac.py 加 --target-entropy flag (5 min)
        cmd: python train_andes_v2.py --episodes 50 --seed 42 --phi-d 1.0 --target-entropy -2
```

8 arms total (2 eval-only + 6 train-then-eval).

---

## 5. 期 (G1-G6, revised verdict rule)

**Verdict 评判规则 (新)**:
- 不看 cum_rf 绝对值 (1-seed RNG drift)
- 看 6-axis trend: 哪个 arm 让 max_df ↓ / smoothness ↑ / range ↑ / final_df ↓
- 信号阈值: axis 提升 ≥ 0.10 absolute 才算"有信号"
- 至少 1 arm overall ≥ 0.10 (R04 0.037 的 ~3×) 才算 R05 不白跑

---

## 6. 执行 wall 估计 (revised, paranoid)

| 阶段 | 工作 | wall |
|---|---|---|
| 0 | sac.py target_entropy patch (exp9 prereq) | 5 min |
| 1 | A 类 eval-only ×2 (serial 因 same eval dir) | 5 min |
| 2 | B 类 6 train, 2-way parallel (CPU paranoid) | 30-40 min |
| 3 | B+C 类 eval ×7 (serial on train finish) | 10 min |
| 4 | 6-axis JSON regen + ranking | 5 min |
| **total** | | **55-65 min** |

vs 老 plan 估的 10 min: **5-6×**, 但合理. 老 plan 假设 GPU 8-way 但 ANDES TDS 不主吃 GPU (env step 是 CPU).

---

## 7. R06 衔接 (exploit phase)

R05 完后看 6-axis ranking:
- top-2 arms (overall 最高 2 个) → R06 5 seed × 200 ep × 长训
- 若 top-2 都 < 0.10 → R06 是**多变量组合 sweep** (e.g. exp4+exp6 = V1 env + disturb_5x), 不是再单变量
- 若 top-1 显著 (overall ≥ 0.15) → R06 直接整合 + paper-spec eval + visual fig 对比

---

## 8. 双 metric (per OPT-3 rule)

R05 是 explore, 1 seed × 50 ep. 评判强制写两个 metric:

```
exp r05_baseline_paper:
  train_reward (final ep R, 1 seed): TBD
  paper_grade (cum_rf @ deterministic 1 seed): TBD     ← 注: 1 seed 仅作 trend 参考, 防 RNG drift
  6axis_overall: TBD
  axis trend: max_df __ → __ / smoothness __ → __ / range __ → __ (vs R04)
```

R06 才出 paper-style 5seed mean±std.

---

## 9. 不行咋办

- 8 arm 全 < 0.05 → R06 pivot **物理诊断不是参数搜**: eval 用 paper-spec disturbance protocol 精确复现, 看 cum_rf 是否量级跳 → root cause 是 disturbance protocol 不一致, 不是 SAC
- exp1.eval r05_disturb_5x cum_rf 仍 1/4 → **falsify H2 magnitude 假设**, 写 `audits/2026-05-07_disturb_magnitude_falsified.md`
- exp6 V1 env > V2 → R06 全弃 V2, 写 `audits/2026-05-07_v2_design_failure.md`

---

## 10. 状态 / Done append (post-execution)

R05A partial:
- r05_disturb_5x_s42 / r05_combo_v1_disturb5x_s42 done train (axes 待 eval-only)
- r05_baseline_paper_s42 / r05_lam_zero_s42 / r05_action_range_2x_s42 partial dir, **重跑 50 ep**

R05B execution log: 待填.
