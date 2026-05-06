# Per-Model Figure Variants Index (2026-05-06 重建)

> 4 个 model variants, 每个独立子目录, 含 fig6/7/8/9 (LS1/LS2 时序).
> fig4 (training curves) + fig5 (50-ep cum reward) 在 `paper/figures/` 顶层共享.

## Variants 排序 (按 max(LS1 diff, LS2 diff) 升序)

| Subdir | DDIC ckpt | LS1 cum_rf | LS1 diff | LS2 cum_rf | LS2 diff | 最差 |
|---|---|---|---|---|---|---|
| **`v2env_phase3v2_seed44/`** | `ddic_phase3v2_seed44` (V1 trained, PHI_ABS=50) | -0.722 | **-6.2%** | -0.471 | **+9.4%** | **9.4%** ✓ paper-grade |
| `v2env_postfix_dt02_seed43_best/` | `ddic_postfix_dt02_seed43_best` (V1, default hyper) | -0.562 | +17.3% | -0.422 | +18.8% | 18.8% |
| `v2env_v2trained_seed42_best/` | `ddic_v2_balanced_seed42_best` (V2-trained, PHI_D=0.05) | -0.830 | -22.0% | -0.423 | +18.7% | 22.0% |
| `v2env_balanced_seed46_final/` | `ddic_balanced_seed46_final` (V1, PHI_D=0.05) | -0.669 | **+1.6%** byte-near | -0.354 | +31.9% | 31.9% (LS1 单独最佳) |

**论文参考**: LS1 DDIC = -0.68, LS2 DDIC = -0.52 (`kd_4agent_paper_facts.md` §8.4).

**fig6/8** (no-control) 共享数据: `results/andes_eval_paper_specific_v2_envV2_hetero/no_control_load_step_{1,2}.json`
- LS1 no-ctrl: -1.66 (-2.9% vs paper -1.61)
- LS2 no-ctrl: -0.72 (+9.9% vs paper -0.80)

**fig7/9** (DDIC) 来自: `results/andes_eval_paper_specific_v2_envV2_hetero/{DDIC_LABEL}_load_step_{1,2}.json`

## 共享文件 (顶层 `paper/figures/`)

| 文件 | 内容 |
|---|---|
| `fig4_training_curves.png` | Fig.4 训练性能 (默认 V1 phase4_noPHIabs_seed42) |
| `fig5_cum_reward_50ep.png` | Fig.5 50-test-ep cum reward |
| `fig6_nocontrol_ls1.png` 等 | 默认 = phase3v2_seed44 |

## 重新生成命令

```bash
cd paper/figure_scripts

# 默认顶层
python fig4_training_curves.py
python fig5_cum_reward.py
python figs6_9_ls_traces.py

# 4 variants 一键全跑
for v in "v2env_phase3v2_seed44:ddic_phase3v2_seed44" \
         "v2env_postfix_dt02_seed43_best:ddic_postfix_dt02_seed43_best" \
         "v2env_v2trained_seed42_best:ddic_v2_balanced_seed42_best" \
         "v2env_balanced_seed46_final:ddic_balanced_seed46_final"; do
    PAPER_FIG_VARIANT="${v%%:*}" PAPER_FIG_DDIC_LABEL="${v##*:}" \
        python figs6_9_ls_traces.py
done
```

## 环境变量

| 变量 | 用途 | 默认 |
|---|---|---|
| `PAPER_FIG_VARIANT` | 输出子目录名 | (空, = 顶层) |
| `PAPER_FIG_DDIC_LABEL` | DDIC ckpt 标签 (figs6_9 用) | `ddic_phase3v2_seed44` |
| `PAPER_FIG_SPEC_DIR` | LS1/LS2 eval 数据目录 | `andes_eval_paper_specific_v2_envV2_hetero` |
| `PAPER_FIG_TRAIN_RUN` | training_log.json run dir (fig4 用) | `andes_phase4_noPHIabs_seed42` |
| `PAPER_FIG_FIG5_DDIC` | Fig.5 DDIC json filename | `ddic_seed44.json` |

## 决策

- **写论文用**: `v2env_phase3v2_seed44/` (verdict 锁定, 双 <10% diff)
- **PHI_D=0.05 验证用**: `v2env_balanced_seed46_final/` (LS1 byte-near, LS2 退化)
- **V2-trained ablation**: `v2env_v2trained_seed42_best/` (V2 训练数值不稳)
- **default-hyper baseline**: `v2env_postfix_dt02_seed43_best/`

详见 `quality_reports/verdicts/2026-05-06_andes_paper_figs_v1_v2_verdict.md`.

## 历史教训 (2026-05-06)

旧的工作产物（含本目录的 fig4-9 + 4 variants subdir + MODELS_INDEX/ENV_COMPARISON.md）
**未 git tracked** → 切分支 stash 时被擦. 本次重建后:
1. 立刻 `git add paper/figure_scripts/ paper/figures/` 防丢
2. 每个 variant subdir 跑完 → 立刻 commit
