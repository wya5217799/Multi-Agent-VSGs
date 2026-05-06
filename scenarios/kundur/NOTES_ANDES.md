# scenarios/kundur — ANDES 路径修代码必读 NOTES

> **2026-05-07 修正**: 旧 "paper-level 复现" 声明 (基于 cum_rf 单维) **被 6-axis 推翻**.
> 真实状态: 所有 ckpt overall score < 0.04 / 1.0. 5/6 axis 全 fail (max_df, final_df,
> settling, ΔH range, ΔD range), 仅 smoothness 偶尔 0.7-0.9.
>
> 详见 `docs/paper/andes_replication_status_2026-05-07_6axis.md`.
>
> 修 ANDES env / train / eval 前必读本文件 + `docs/paper/kd_4agent_paper_facts.md`.
> 最后更新: 2026-05-07.

---

## 1. 论文复现现状速查 (2026-05-07, 6-axis 真实评估)

**所有 21 个 ckpt overall score 0.033-0.036 / 1.0** (论文 = 1.0). cum_rf 单维"paper-grade"
判断已被推翻——cum_rf 是 sync 积分量, 对 step-jitter 不敏感, 不能反映物理动态.

**Top 1 by 6-axis (V2 env)**: `ddic_balanced_seed46_best` overall 0.036, 强项仅 smoothness.
**旧 #1 (cum_rf)**: `phase3v2_seed44` 6-axis ranking #18, ΔD smoothness std=22 严重锯齿.

### 6-axis 评估 (论文 vs 项目最佳)

| Axis | LS1 论文 | LS1 项目 best | LS2 论文 | LS2 项目 best |
|---|---|---|---|---|
| max \|Δf\| | 0.13 Hz | 0.41 Hz (3.2×) | 0.10 Hz | 0.35 Hz (3.5×) |
| final \|Δf\|@6s | 0.08 Hz | 0.18 Hz (2.3×) | 0.05 Hz | 0.22 Hz (4.4×) |
| settling_s | 3 s | ∞ (10s 不收敛) | 2.5 s | ∞ |
| ΔH range (DDIC) | 350 | 5 (1.4%) | 300 | 7 (2.3%) |
| ΔD range (DDIC) | 700 | 15 (2.1%) | 500 | 22 (4.4%) |
| ΔH/ΔD smoothness | std~0 | std 2-22 | 同 | 同 |
| cum_rf (sync 积分) | -0.68 / -0.52 | -0.45 / -0.49 (~10% diff) | — | — |

### 历史认知 (已被证伪)

| 日期 | 旧声明 | 现状 |
|---|---|---|
| 2026-05-06 verdict PASS | "phase3v2_seed44 paper-level (LS1 -6.2% / LS2 +9.4% cum_rf)" | SUPERSEDED, 6-axis = 0.033 |
| warmstart_seed42 综合最佳 | "LS1 4.5% / LS2 1.8% cum_rf" | 同上, 物理 5/6 axis 仍 0 分 |

## 2. ANDES env 版本

### V1 (默认, 老线): `env/andes/andes_vsg_env.py::AndesMultiVSGEnv`
- 拓扑: ANDES `kundur_full.xlsx` + 4 ESS GENCLS @ Bus 12/14/15/16 + W2 风电场 @ Bus 8 + G4→W1
- baseline: M₀=20 (H₀=10s), D₀=4 (uniform)
- 动作: ΔM=[-10, 30] / ΔD=[-10, 30]
- 训过 SAC: phase3 / phase4 / phase9 / warmstart / postfix / balanced 系列

### V2 (新, 2026-05-06): `env/andes/andes_vsg_env_v2.py::AndesMultiVSGEnvV2`
- 拓扑: 与 V1 相同
- baseline: M₀=30 (H₀=15s), **D₀=[20, 16, 4, 8] 异质**
- 动作: ΔM=[-12, 40] / ΔD=[-15, 45]
- NEW_LINE_X: 0.20 (V1=0.10, sweep verdict)
- 训过 SAC: 5-seed × 500ep (`andes_v2_balanced_seed{42-46}/`)
- 切换: `EVAL_PAPER_SPEC_ENV=v2 python ...`
- D₀ override: `ANDES_V2_D0="20,16,4,8" ...`
- LINE_X override: `ANDES_V2_LINE_X=0.20 ...`

### V2 设计动机
V1 4 ESS 同质 D₀ → 4 节点频率响应过同步 → cum_rf 量级偏小. V2 异质 D₀ 制造 sync
失同步 → no-ctrl LS1 cum_rf=-1.66 完美匹配论文 -1.61 (但 6-axis 仍 fail).

## 3. Reward 调权 verdicts

`base_env.py::PHI_F/PHI_H/PHI_D`:
- PHI_F = 10000 (Phase 2α: 原 100 → r_f_raw ~1e-5 时 r_f 信号 100× 弱于 r_d)
- PHI_H = 1.0 (默认)
- PHI_D = **0.05** (2026-05-06 balanced verdict)

### PHI_D sweep 结果 (2026-05-06)
| PHI_D | seed42 LS1 | LS2 | 多 seed 验证? | 备注 |
|---|---|---|---|---|
| 0.02 (default) | 33% (best) | 38% (best) | phase4_seed42 baseline | |
| 0.02 (default) | n/a | **0.8% (best)** | phase4_seed46 best | LS2 default 也能 paper-level |
| **0.05 (balanced)** | 36% (best) | **5.4% (best)** | s42 only | s43=29% / s44=72.5% **不稳定** |

**verdict**: PHI_D=0.05 不是 LS2 突破的根因. seed luck + best ckpt 才是 cum_rf 单维偶然匹配.

## 4. dt 一致性 (2026-05-05 fix)

旧 `_dt_runtime` 在 `step()` sub-step 推进时 over-shoot, 实际 dt=0.6s 而非 0.2s.
`base_env.py:328-361` 已 fix: 用累积绝对时间 + 最后段精确 stop.
**训练 + eval 现在都是 dt=0.2s/10s, M=50 步**, 与论文 §IV-A 一致.

## 5. Best vs Final ckpt verdict (2026-05-06)

500 ep 训练里多 model 出现 **final 后期退化** (critic loss 上升, episode reward 震荡).
应**用 best.pt 而非 final.pt** eval.

工具: 历史用 `_re_eval_best_ckpts.py` 一次扫. **L4 重构后 (2026-05-07) 该脚本已归档到
`scenarios/kundur/_legacy_2026-04/`**, 现统一通过 `scripts/research_loop/eval_paper_spec_v2.py`
跑 `--suffix best` 和 `--suffix final` 两遍后人工对比 cum_rf / 6-axis.

## 6. 关键 results/ 目录定位

### Train artifacts
- `andes_phase3_seed{42,43,44}` — phase3 (PHI_ABS=50)
- `andes_phase4_noPHIabs_seed{42-46}` — phase4 (no PHI_ABS)
- `andes_phase9_shared_seed{42-46}_500ep` — shared policy
- `andes_warmstart_seed{42-44}` — warmstart from earlier ckpt
- `andes_postfix_dt02_seed{42,43}` — post-dt-fix retrain
- `andes_postfix_balanced_seed{42-46}` — **PHI_D=0.05** retrain (V1 env)
- `andes_v2_balanced_seed{42-46}` — **V2 env + PHI_D=0.05** retrain (5 seed × 500ep)

### Eval artifacts
- `andes_eval_paper_grade/` — 50-test-ep cum_rf summary (n=3 seed)
- `andes_eval_paper_grade_parallel/` — n_test_eps=2 smoke (**不可用!**)
- `andes_eval_paper_specific/` — V1 legacy LS1/LS2 traces (dt=0.6/30s)
- `andes_eval_paper_specific_v2/` — V1 paper-aligned LS1/LS2 traces (dt=0.2/10s)
- `andes_eval_paper_specific_v2_envV2_hetero/` — **V2 hetero env eval (主要数据源)**
- `andes_eval_specific_v2_d0_*` — V2 D₀ sweep (4 配置)
- `andes_eval_specific_v2_linex_*` — V2 NEW_LINE_X sweep (5 配置)
- `andes_eval_bestckpt_re_eval_2026-05-06/` — best vs final 全扫
- `andes_paper_alignment_6axis_2026-05-07.json` — **6-axis 完整 ranking JSON**

## 7. 已知失败 / 试过没用的

- **V2 D₀ uniform=30**: max_df 减 28% 但 cum_rf 退到 16%. **错方向**. 改用异质 D₀.
- **V2 NEW_LINE_X=0.30**: cum_rf 超调 175% (论文 -1.61 跑成 -2.82). 0.20 sweet spot.
- **V2 NEW_LINE_X=0.60**: power flow 不收敛 (DIVERGE).
- **paper-literal ΔH=[-100, 300]**: Phase C 验证 87% floor-clip → SAC 不能学. 物理 floor 限制.
- **paper_grade_parallel 数据**: n_test_eps=2 smoke, **不可用做 50-ep cum reward 图**.
- **PHI_D=0.05 假设证伪**: 3-seed 验证 (s42=5.4%, s43=29%, s44=72%) 不稳定.
- **cum_rf 单维评判**: 被 6-axis 推翻, 是 sync 积分 cherry-pick.

## 8. 6-axis 量化函数 (2026-05-07)

`evaluation/paper_grade_axes.py` — 6 axis 几何均值评判. 用法:

```bash
# Default eval dir = andes_eval_paper_specific_v2_envV2_hetero/
python evaluation/paper_grade_axes.py

# 指定 dir
python evaluation/paper_grade_axes.py results/andes_eval_xxx/
```

输出每 ckpt × 7 axis × 2 scenario 评分 + 综合 ranking.

## 9. 6-axis 论文 max_df 残差不可消

实测: V1, V2, V2 D₀ sweep, V2 LINE_X sweep, balanced PHI_D=0.05 → max_df **全部 0.5+ Hz**
(论文 0.12 Hz).

根因 (按贡献):
1. 动作范围 6×/14× 缩 (Phase C floor 物理限制)
2. 4 G GENROU 在 ANDES Kundur full 中 D=0 (无 governor) — 论文系统可能含 governor
3. 扰动相对幅值: LS1=248 MW vs 4 ESS 总 800 MVA = 31%

GENROU H 已验证 (M=117 在 Sn=900 base, 折 Sbase=100 后 H=6.5, 与 Kundur [49] 一致).
**不是 H 问题, 是 D=0 + 无 governor**.

## 9.5. L4 eval 单一入口 lock-in (2026-05-07)

**唯一 paper-spec eval 脚本**: `scripts/research_loop/eval_paper_spec_v2.py`.

R03 verdict 暴露 5+ 并存 eval 入口混乱, R04 完成闭环验证. 13 个 R0 期 (2026-04~05) eval/sweep
脚本 (`_eval_paper_grade_andes*` / `_phase{3,4,9}*_eval` / `_re_eval_best_ckpts` / `_v2_*_sweep`
/ `_run_v2_5seed.sh`) 已归档到 `scenarios/kundur/_legacy_2026-04/`. **不要从 _legacy/ import**.

历史 `_eval_paper_specific.py` 在 2026-05-07 stash 事故中丢失, 已被 `eval_paper_spec_v2.py`
取代; 依赖它的 `_phase9_*_reeval` 等脚本归档时已 broken.

老 pipeline `scripts/run_tier_a_post_training.sh` 因依赖归档脚本现已 dead, 不要重启.

详见 `_legacy_2026-04/README.md` 文件清单.

## 10. 修代码契约

修 V1 env / V2 env / train / eval 时:
1. 改任何 baseline (M₀/D₀/动作范围) → 必须**新建 V3 子类**, 不覆盖 V1/V2
2. 改 reward 公式 → 改 base_env, 同步更新本 NOTES §3 表
3. 改 dt → 必须同时跑 sanity test 验证 traces[1].t - traces[0].t = new_dt
4. 跑新 eval → 用环境变量 `EVAL_PAPER_SPEC_OUT_DIR=...` 落到独立 dir, 不覆盖老 results
5. 新 eval 完成 → 跑 `python evaluation/paper_grade_axes.py <new_dir>` 评 6-axis
6. 论文复现量级对账更新 → 同步本 NOTES §1 + `docs/paper/andes_replication_status_2026-05-07_6axis.md`

## 11. 下一步路径 (2026-05-07 6-axis recovery)

详见 `quality_reports/plans/2026-05-07_andes_6axis_recovery.md`.

| Phase | 内容 | 期望 axis 改善 | 论文 scope 内 |
|---|---|---|---|
| **A** | actor smoothing reward + INCLUDE_OWN_ACTION_OBS | smoothness 0.7→1.0 | ✅ 标准 RL |
| **B** | 启 IEEEG1 governor + EXST1 AVR | max/final/settling 同时 0→0.4 | ⚠️ 离开 §II-A scope |
| **C** | H₀=50 baseline + ΔH=[-50,150] | range 0→0.5 | ⚠️ 偏离 Kundur [49] |
| **D** | V3 env 子类 + 5 seed × 500 ep 重训 + 6-axis 重评 | overall ≥ 0.5 | — |
| **E** | verdict + 文档更新 + V3 fig 重画 | — | — |
