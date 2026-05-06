# R04 Verdict

**Status**: DONE (8/8 exit 0)
**Wall**: 18:30–19:15 UTC (~45 min, 5×PHI_D=1.0 trains 主导)
**Trigger**: R03 verdict — PHI_D=0.05 偏 paper Table I 1.0 20× bug; H2 解耦待验

---

## §1 实测 (ground truth)

### Train metrics (5 SAC arms × 200ep fresh PHI_D=1.0)
| arm | final_R | best_R | std_e199 | TDS% | fpeak | wall(s) | r_h% | r_d% | r_f% |
|---|---|---|---|---|---|---|---|---|---|
| s42 | -1930.5 | -200 | 0.045 | 9.5 | 0.86 | 2682 | 3.3 | **92.5** | 4.2 |
| s43 | -1952.2 | -200 | 0.090 | 10.0 | 0.90 | 2666 | 5.2 | 80.6 | 14.2 |
| s44 | -1952.5 | -200 | 0.090 | 9.5 | 0.80 | 2687 | 4.7 | 81.0 | 14.3 |
| s45 | -2114.7 | -200 | 0.053 | 10.0 | 0.89 | 2672 | 3.2 | 91.7 | 5.1 |
| s46 | -2271.8 | -200 | 0.070 | 10.0 | 0.87 | 2677 | 4.3 | 90.6 | 5.2 |
| **5seed mean ± std** | **-2044.3 ± 147.1** | -200 | **0.070 ± 0.021** | 9.8 | 0.864 | 2677 | 4.1 | **87.3** | 8.6 |

**vs R03 PHI_D=0.05 (500ep total)**: reward **退步 130%** (-894 → -2044, 因 r_d 强约束); std **改善 52%** (0.145 → 0.070); fpeak 微降 (0.886 → 0.864).

### Auxiliary smokes
- **adaptive_K10_K400** (no SAC): cum_rf LS1=-0.123 LS2=-0.037, max_df 0.566/0.408 Hz
- **V3_smoke (governor)**: 30ep, final -23748, fpeak 0.42 Hz, agent3 mu=+0.03 (首次正向!), critic_loss 113K stuck
- **obs9_smoke (修后)**: 30ep, final -23061, fpeak 0.42 Hz, ✅ 不报 shape error

### Paper-spec eval (5 R04 PHI_D=1.0 best.pt + adaptive + no_control)
| controller | LS1 cum_rf | LS1 max_df | LS2 cum_rf | LS2 max_df |
|---|---|---|---|---|
| r04_phid1p0 s42 | -0.150 | 0.586 | -0.245 | 0.496 |
| r04_phid1p0 s43 | -0.187 | 0.567 | -0.138 | 0.496 |
| r04_phid1p0 s44 | -0.137 | 0.570 | -0.084 | 0.450 |
| r04_phid1p0 s45 | -0.176 | 0.529 | -0.074 | 0.428 |
| r04_phid1p0 s46 | -0.150 | 0.585 | -0.151 | 0.455 |
| adaptive_K10_K400 | -0.123 | 0.566 | -0.037 | 0.408 |
| no_control | -0.134 | 0.551 | -0.058 | 0.413 |
| **paper DDIC** | -0.68 | 0.13 | -0.52 | 0.10 |

cum_rf 项目 / paper = 1/4 ~ 1/8 (12× 太小, 印证 disturbance magnitude 量级问题).

---

## §2 6-axis paper alignment

5seed × 2 LS mean ranking:
| rank | label | overall | 关键 |
|---|---|---|---|
| 1-5 | r04_phid1p0_s42-46 | **0.037** | 5 seed 完全并列 |
| 6 | adaptive_K10_K400 | 0.010 | = no_ctrl |
| 7 | no_control | 0.010 | base |

axis 明细 (s42 LS1, 代表):
| axis | R04 PHI_D=1.0 | R03 PHI_D=0.05 | paper | gap |
|---|---|---|---|---|
| 1 max_df | 0.586 Hz, score 0 | 0.531 Hz, score 0 | 0.13 | 4× |
| 2 final_df | 0.30 Hz, score 0 | 0.357 Hz, score 0 | 0.08 | 4× |
| 3 settling | ∞, score 0 | ∞, score 0 | 3 s | fail |
| 4 dH_smooth | 0.105, **score 0.99** | 2.99, score 0.70 | 0 | 接近 paper |
| 5 dD_smooth | 1.44, **score 0.95** | 2.86, score 0.90 | 0 | 接近 paper |
| 6 dH_range | 0.22, score 0 | 4.34, score 0 | 350 | 1500× 偏小 |
| 7 dD_range | 2.42, score 0 | 7.13, score 0 | 700 | 280× 偏小 |

**R04 修 PHI_D 后**: smoothness axis 4-5 飞涨 (0.7→0.99), **但 range axis 反而更偏小** (R03 4→R04 0.22), 因为强约束让 agent 干脆不动 ΔH/ΔD → smooth 但物理无效.

---

## §3 视觉对比 (paper Fig.7 vs R04 待生)

(R04 fig 待生 — 命令: `PAPER_FIG_SPEC_DIR=.../eval_r04_phid1p0 PAPER_FIG_VARIANT=r04_phid1p0_s42_best PAPER_FIG_DDIC_LABEL=ddic_r04_phid1p0_s42_best python paper/figure_scripts/figs6_9_ls_traces.py`)

预期对比:
- 项目 ΔH: R03 范围 10-22 → R04 0.22 物理几乎不动 (over-smooth)
- 项目 ΔD: R03 0-35 → R04 2.42 同
- paper Fig.7 ΔH/ΔD: 大幅正向 [-100,+250] / [-200,+500]

R04 → paper "smoothness 接近, magnitude 反向更远" — 需要看图确认.

---

## §4 Hyperparam vs paper Table I

| 参数 | R04 实际 | paper | Class | 状态 |
|---|---|---|---|---|
| LR / GAMMA / TAU / BUFFER / BATCH / HIDDEN | 同 | 同 | A | ✅ |
| **PHI_D** | **1.0** | **1.0** | **A** | ✅ **R03 bug 已修** |
| PHI_F | 100 | 100 | A | ✅ |
| PHI_ABS | 50 | 不存在 | B | ⚠ ANDES 紧耦合补丁 |
| LAMBDA_SMOOTH | 0.01 | 不存在 | B | ⚠ R01 加, 现 R04 看 smoothness 已 0.99, **可考虑撤掉** (range 太小可能因 smoothing + r_d 双重约束) |
| N_EPISODES (R04) | 200 | 2000 | A | ⚠ 部分 (cost) |
| V2 env (M0=30 / D0 hetero / NEW_LINE_X=0.20) | 偏离经典 | Kundur [49] 隐含 | B | ⚠ 项目 ablation, 不必要 |
| GENROU 无 governor | V2 默认 | Kundur 经典含 | C | ⚠ V3 smoke 已通, R05 上 |

---

## §5 假设验证

H1 (PHI_D=0.05→1.0 改善 max_df axis): **部分验证**
- ✅ smoothness axis 0.7-0.9 → 0.95-0.99 (paper 标称 ~0)
- ❌ max_df axis 仍 0 (0.586 Hz vs paper 0.13)
- ❌ range axis 反而恶化 (4 → 0.22)
- 结论: PHI_D 修对了一个 axis 但产生 over-smooth 副作用; 不是 root cause

H2 (adaptive 6-axis ≥ 0.5 解耦算法 vs 实现): **证伪**
- adaptive 6-axis = **0.010** (= no_control)
- SAC R04 = 0.037 (>**3.5×** adaptive)
- **结论: 不是算法问题, 是实现/平台问题**. 改 SAC 任何 hyperparam 都到不了 paper.
- root cause 候选: 1) disturbance magnitude calibration (cum_rf 8× 偏小); 2) GENCLS M/D 直接调 vs paper ESS P 注入语义; 3) 无 governor 物理底

H3 (V3 governor 训练通否): **验证 (smoke level)**
- ✅ build + reset + step + 30ep train 全通
- ⚠ critic_loss 113K stuck, agent 学不动 (30ep too short)
- ✅ 首次出现 agent3 mu=+0.03 正向 (V2 全负 collapse 在 V3 部分破)
- R05 长训验证

H4 (obs9 修后训练通否): ✅ **验证**, OBS_DIM 7→9 patch 正确; reward 量级与 R02 50ep 同 (smoke 短训不能下结论)

---

## §6 R{N+1}=R05 candidates — 短-多臂 bandit (per user 2026-05-07)

R01-R04 模式 = "1 hyperparam × 5 seed × 长训" = **重复采样**. 用户指出: 该 **多 hyperparam × 1 seed × 短训** 找最优区间.

R05 K=8, 每 arm 30ep × 1 seed × ~7 min, parallel ~10 min wall:

| arm | id | 改的维度 | 控制变量 | priority |
|---|---|---|---|---|
| 1 | r05_baseline_paper                | 全 paper-faithful (V2, PHI_D=1.0, λ=0.01)        | control                             | 8 |
| 2 | r05_phid_5x                       | PHI_D=5.0 (反向 sweep)                           | over-shoot 测                       | 8 |
| 3 | r05_lam_zero                      | LAMBDA_SMOOTH=0 (撤 smoothing)                   | 看是否 range 恢复                    | 8 |
| 4 | **r05_v1_env_back**               | **V1 env (M0=20, D0=4 uniform, NEW_LINE_X=0.10)** | 验 V2 设计是不是错              | 9 |
| 5 | r05_action_range_2x               | DM/DD × 2 ([-24,80] / [-30,90])                  | 给 agent 大空间                     | 7 |
| 6 | **r05_disturb_5x**                | **PQ_Bus14 -2.48 → -12.4**                       | 测 magnitude calibration (P0 root)  | 10 |
| 7 | r05_v3_governor_5seed_smoke       | V3 env 1 seed × 30ep 重测                        | 验 V3 collapse 是否破               | 7 |
| 8 | r05_target_entropy_low            | target_entropy=-2 (强 deterministic)             | 反 SAC explore collapse              | 7 |

**关键 priority=10**: r05_disturb_5x (cum_rf 量级 8× 偏小是 P0 root cause).

总 wall ~10 min. 完后跑 6-axis ranking, top-3 进 R06 长训.

---

## §7 Audit

- **R03 PHI_D=0.05 是 cum_rf cherry-pick optimum**: PHI_D 弱约束让 agent 自由调 D, 但物理上 ΔD 锯齿 std=22; PHI_D=1.0 修后 std 0.07 (反映物理 ΔD 几乎不动) — paper 期望的是中间状态 (smooth 的大幅 ΔD 调节), 可能需要重新设计 reward (per-agent 而非 mean-then-square).
- **5seed 完全并列 (0.037 ± 0)**: SAC 在 V2 env + PHI_D=1.0 上找到稳定但弱的局部最优 — 5 个 seed 都收敛到同一个 policy. 单一 hyperparam 不再是 explore.
- **R04 dH/dD range 反而更小**: 0.22 / 2.42 vs R03 4 / 7. 因为 r_d 强约束 + smoothing 双重压制. R05 r05_lam_zero 验证.
- **disturbance magnitude P0 嫌疑**: 项目 cum_rf vs paper 1/8 ratio 跨 R02-R04 一致. 可能 PQ_Bus14=-2.48 在 ANDES local p.u. 远小于 paper system p.u. 需 calibrate.

---

## Cross-ref
- R03 verdict: [round_03_verdict.md](round_03_verdict.md)
- adaptive eval: `results/research_loop/eval_r04_adaptive/`
- R04 5seed eval: `results/research_loop/eval_r04_phid1p0/`
- V3 smoke: `results/research_loop/r04_V3_smoke_s42/`
- obs9 smoke: `results/research_loop/r04_obs9_smoke_s42/`
- 5 R04 ckpt: `results/research_loop/r04_A_phid1p0_s{42-46}/`
- R05 plan: [round_05_plan.md](round_05_plan.md)
