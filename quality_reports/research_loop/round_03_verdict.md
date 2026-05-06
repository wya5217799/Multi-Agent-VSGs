# R03 Verdict

**Status**: DONE (7/7 candidates, 1 killed=obs9 incident)
**Wall**: 16:50–17:50 UTC (~60 min, 5-way GPU + 1 cpu probe + 1 failed obs9)
**Trigger**: R02 verdict — 200ep 改善但 G5 仍 fail; 试 obs9 + governor + 500ep

---

## §1 实测 (ground truth)

### Train metrics (5 SAC arms × 500ep total = R02 200ep + R03 300ep resume)
| arm | final_R | best_R | std_e299 | TDS% | fpeak | wall(s) |
|---|---|---|---|---|---|---|
| s42 | -826.6 | -200 | 0.180 | 9.0 | 0.87 | 3896 |
| s43 | -1011.4 | -200 | 0.172 | 9.3 | 0.90 | 3888 |
| s44 | -787.7 | -200 | 0.113 | 9.3 | 0.90 | 3893 |
| s45 | -789.1 | -200 | 0.113 | 9.3 | 0.87 | 3890 |
| s46 | -1054.8 | -200 | 0.150 | 9.3 | 0.89 | 3884 |
| **5seed mean ± std** | **-893.9 ± 128.9** | -200 | **0.145 ± 0.032** | 9.3 | 0.886 | 3890 |

### Paper-spec eval (V2 eval driver L4 重建, 单 deterministic seed, 50-step)
| arm | LS1 cum_rf | LS1 max_df | LS2 cum_rf | LS2 max_df |
|---|---|---|---|---|
| s42 | -0.1359 | 0.531 | -0.0740 | 0.425 |
| s43 | -0.0711 | 0.522 | -0.0502 | 0.443 |
| s44 | -0.1005 | 0.511 | -0.0501 | 0.414 |
| s45 | -0.0827 | 0.545 | -0.0316 | 0.396 |
| s46 | -0.1167 | 0.611 | -0.0487 | 0.436 |
| no_control | -0.1343 | 0.551 | -0.0577 | 0.413 |
| **paper DDIC ref** | -0.68 | 0.13 | -0.52 | 0.10 |

⚠ R03 ckpt LS1 cum_rf [-0.07, -0.14] vs no_ctrl -0.13 — **几个 seed 跟 no-ctrl 几乎齐平**, 控制效果极弱.

---

## §2 6-axis paper alignment (`evaluation/paper_grade_axes.py`)

5seed mean overall (LS1+LS2 几何均值):
| rank | ckpt | overall |
|---|---|---|
| 1 | s45_best | 0.036 |
| 2 | s43_best | 0.035 |
| 3 | s46_best | 0.035 |
| 4 | s42_best | 0.035 |
| 5 | s44_best | 0.034 |
| 6 | no_control | 0.010 |

R03 vs no_ctrl: **3.5× 改善**. 但绝对 < 0.04 (G1=0.5 阈值).

axis 明细 (5seed mean, LS1):
| axis | project | paper | score |
|---|---|---|---|
| 1 max_df | 0.55 Hz | 0.13 Hz | **0.00** ← gap 4× |
| 2 final_df | 0.30 Hz | 0.08 Hz | **0.00** ← gap 4× |
| 3 settling | 99 s (∞) | 3 s | **0.00** ← 没 settle |
| 4 dH_smooth | 2.0~3.0 std | ~0 | **0.70-0.90** ← 唯一接近 |
| 5 dD_smooth | 3.0~7.0 std | ~0 | **0.75-0.90** ← 接近 |
| 6 dH_range | 2-4 | 350 | **0.00** ← gap 80× |
| 7 dD_range | 7-15 | 700 | **0.00** ← gap 50× |

几何均值约束: 任一 axis=0 → overall=0. R03 在 4/6 axis 全 0, 总分被拖死.

---

## §3 视觉对比 (paper Fig.7 vs project r03_lam0p01_s42_best/fig7)

`paper/figures/r03_lam0p01_s42_best/fig7_ddic_ls1.png` vs `Figure.paper/7.png`:
- Δf: paper peak 0.13 Hz settle 3s 平滑; 项目 peak 0.5 Hz 30s 内未 settle, 锯齿
- ΔH: paper 主要正向 [-100,+250] 平滑; **R03 现在双向 10-22, 比 R02 单向减小有改善但 magnitude 30× 偏小**
- ΔD: paper 正向 [-200,+500] 平滑; R03 双向 0-35, gap 20×
- ΔP_es: 项目 0-1.5 p.u. 锯齿; paper 平滑

R03 vs R02: H 学会双向变动 (R02 全负 collapse 已破); D 也开始双向 (但震幅更大). magnitude 仍 20-30× 不到论文.

---

## §4 Hyperparam vs paper Table I

| 参数 | R03 实际 | paper Table I | Class | 状态 |
|---|---|---|---|---|
| Actor/Critic LR | 3e-4 | 3e-4 | A | ✅ |
| GAMMA / TAU / BUFFER / BATCH / HIDDEN | paper 默认 | 同 | A | ✅ |
| **PHI_D (训练 cmd)** | **0.05** | **1.0** | **A** | ❌ **20× 偏离, R04 必修** |
| PHI_F | 100 | 100 | A | ✅ |
| PHI_ABS | 50 | 不存在 | B | ⚠ ANDES 紧耦合补丁, 声明 |
| LAMBDA_SMOOTH | 0.01 | 不存在 | B | ⚠ R01 实验性 |
| N_EPISODES | 500 (R03) | 2000 | A | ⚠ 部分 (成本压缩) |
| VSG_M0 / D0_HETEROGENEOUS / NEW_LINE_X | V2 调过 | 隐含 | B | ⚠ V2 sweep verdict |
| GENROU 无 governor | 默认 | Kundur [49] 经典含 governor | C | ❌ R04 加 (probe 已 PASS) |

---

## §5 假设验证 (R02 → R03)

H1 (LAMBDA_SMOOTH=0.01 改善 smoothness): **部分验证**
- 6-axis dH_smooth=0.7-0.9, dD_smooth=0.75-0.9 ✅ smoothness axis 接近 paper
- 但 std_e300=0.145 比 R02 std_e199=0.122 反而升 19% — late training SAC exploration 抵消 smoothing 效果

H_governor (Phase B): ✅ probe **PASS** (IEEEG1+EXST1 add+pflow+5step TDS)

H_obs9 (INCLUDE_OWN_ACTION_OBS): ❌ **FAILED** — train_andes 用 class attr OBS_DIM=7 不读 env var, replay buffer shape 错. 见 [incident](incidents/r03_obs9_shape_mismatch_bug.md). R04 5 行修.

H_500ep (resume + 300 more ep 改善 reward): ✅ **部分**
- final_R: R02 -1059 → R03 -894 (16% 改善, 但 R02 -2638→-1059 改善 60%, **diminishing returns**)
- 5seed std: R02 135 → R03 129 (≈持平)
- visual: H/D 双向变动出现 (R02 collapse 破除), 但 magnitude 仍 30× 偏小

---

## §6 R{N+1}=R04 candidates

主修 + 测 + 闭环, K=8:
1. **r04_train_andes_PHI_D_FIX** (code edit): 删 train_andes_v2 默认 `--phi-d 0.05`, 改 paper 默认 1.0
2. **r04_train_andes_obs_dim_FIX** (code edit): obs_dim 从 env var 读, 不读 class attr
3. **r04_eval_driver_consolidation_L4** (code reorg): archive `_eval_paper_grade*` × 4 + `_phase{3,4,9}*` × 6 + `_re_eval_best_ckpts.py` 进 `scenarios/kundur/_legacy_2026-04/`. 唯一入口 = `scripts/research_loop/eval_paper_spec_v2.py`
4. **r04_A_PHI_D_1p0_5seed_200ep** (5 GPU): paper PHI_D=1.0 5seed × 200ep fresh (不 resume R03, R03 ckpt 是 PHI_D=0.05 训的, 不兼容)
5. **r04_adaptive_baseline_eval** (1 cpu): adaptive K_H=10/K_D=400 controller (no SAC) 跑 eval driver → 出 6-axis. **解耦 算法 vs 实现 问题**: 若 adaptive 6-axis ≥ 0.5 = ANDES 平台 OK + SAC 还有空间; 若 adaptive 也烂 = 实现/平台问题
6. **r04_governor_V3_env_smoke** (1 GPU): 写 V3 env class (V2 + IEEEG1+EXST1 in `_build_system`), 1 seed × 30ep fresh smoke

K=4 train(PHI_D fix) + 1 cpu (adaptive) + 1 gpu (V3 smoke) + 2 buffer = 8 槽全占.

---

## §7 Audit

- **dt=0.6s 异常**: eval traces t[1]-t[0]=0.6 而非 paper 0.2; t-axis 拉 3×. R04 调查 base_env step DT 实际取值, 可能是 V2 env 修改了什么.
- **best reward "-200" hardcode**: 5 arm 全 -200, 是 monitor 阈值 ceiling 不是真 best. 待修.
- **action collapse 部分破除**: R02 全负 → R03 双向. 是 500ep + smoothing 渐变效果.
- **5seed cum_rf vs no_ctrl 差距小**: 控制效果弱, 印证 PHI_D 偏离 paper 的根因.

---

## Cross-ref
- R02 verdict: [round_02_verdict.md](round_02_verdict.md)
- obs9 incident: [incidents/r03_obs9_shape_mismatch_bug.md](incidents/r03_obs9_shape_mismatch_bug.md)
- governor probe: `results/research_loop/r03_governor_wire_probe.json`
- eval results: `results/research_loop/eval_r03_paper_spec/`
- figs (paper-spec): `paper/figures/r03_lam0p01_s42_best/fig{6,7,8,9}_*.png`
- archived R0 figs: `paper/figures/_archive_R0_2026-05-06/`
- nav 改动: SKILL.md L1 verdict 6-段模板
