# ANDES 论文复现进度对账 — 6-Axis 真实评估 (2026-05-07)

> **真实状态: 0% paper-aligned**. 所有 21 个 ckpt overall score < 0.04 / 1.0.
>
> 论文事实查询走 `kd_4agent_paper_facts.md`; 量化函数在 `evaluation/paper_grade_axes.py`;
> 完整 ranking JSON 在 `results/andes_paper_alignment_6axis_2026-05-07.json`.

---

## 0. TL;DR

| 旧 verdict (2026-05-06, cum_rf 单维) | 新 verdict (2026-05-07, 6-axis) |
|---|---|
| "phase3v2_seed44 LS1 -6.2% / LS2 +9.4% paper-grade" | overall 0.033 / 1.0 (ranking #18 of 19 DDIC) |
| "V2 hetero env LS1 -2.9% paper-grade no-ctrl" | 仅 sync 积分匹配, max_df 5×偏大 / final_df 4× / settling ∞ |
| 评判结论 PASS | 评判结论 INCONCLUSIVE — 5/6 axis 全 fail, 仅 smoothness 0.7-0.9 |

**核心修正**: cum_rf = ∫(f-f̄)² 是 sync **积分**量, 对 step-jitter 不敏感. 论文 Fig.6/7/8/9 看的是
**动态过程** (峰值 / 衰减 / settling / action smoothness / range) 而非积分. 旧评判用单维 cherry-pick,
失去物理含义.

---

## 1. 论文 benchmark (从 Fig.6/7/8/9 视觉提取, 6s 窗口)

| 指标 | LS1 (Bus14 -248 MW) | LS2 (Bus15 +188 MW) |
|---|---|---|
| max \|Δf\| | 0.13 Hz | 0.10 Hz |
| final \|Δf\| @ t=6s | 0.08 Hz (residual) | 0.05 Hz |
| settling time (Δf 进入 ±0.02 Hz of residual) | ~3 s | ~2.5 s |
| ΔH range (DDIC) | [-100, +250] | [-100, +200] |
| ΔD range (DDIC) | [-200, +500] | [-200, +300] |
| ΔH/ΔD avg curve smoothness | 平滑包络收敛 (std ~0) | 同 |

源: `docs/paper/kd_4agent_paper_facts.md` §8.4 + Fig.6-9 视觉直读.

---

## 2. 项目实测 vs 论文 (Top 3 ckpt, V2 env)

### #1 ranking: `ddic_balanced_seed46_best` (overall 0.036 / 1.0)

| Axis | LS1 project | LS1 paper | LS1 score | LS2 project | LS2 paper | LS2 score |
|---|---|---|---|---|---|---|
| max \|Δf\| | 0.41 Hz | 0.13 | 0.0 | 0.35 Hz | 0.10 | 0.0 |
| final \|Δf\|@6s | 0.18 Hz | 0.08 | 0.0 | 0.22 Hz | 0.05 | 0.0 |
| settling_s | ∞ | 3.0 | 0.0 | ∞ | 2.5 | 0.0 |
| ΔH smoothness | std=2.34 | 0 | 0.77 | std=2.13 | 0 | 0.79 |
| ΔD smoothness | std=4.96 | 0 | 0.83 | std=3.51 | 0 | 0.88 |
| ΔH range | 4.6 | 350 | 0.0 (1.3% 论文范围) | 6.9 | 300 | 0.0 (2.3%) |
| ΔD range | 14.6 | 700 | 0.0 (2.1%) | 22.0 | 500 | 0.0 (4.4%) |

### #18 ranking: `ddic_phase3v2_seed44` (overall 0.033, 旧 verdict 锁定 model)

| Axis | LS1 score | LS2 score |
|---|---|---|
| max \|Δf\| | 0.0 (0.48 Hz vs 0.13) | 0.0 |
| final \|Δf\|@6s | 0.0 (0.18 vs 0.08) | 0.0 |
| settling_s | 0.0 (∞) | 0.0 |
| ΔH smoothness | **0.52** (std=4.84, 偏大) | **0.66** (std=3.41) |
| ΔD smoothness | **0.0** (std=22.28, 严重高频锯齿) | **0.0** (std=22.69) |
| ΔH range | 0.0 (25 vs 350) | 0.0 |
| ΔD range | 0.0 (60 vs 700) | 0.0 |

cum_rf "9.4% diff paper-grade" 的旧标签 = **以单维 cherry-pick 误导整体判断**.

---

## 3. 完整 ranking (Top 10 of 21)

| Rank | Label | Mean overall | LS1 | LS2 |
|---|---|---|---|---|
| 1 | ddic_balanced_seed46_best | 0.036 | 0.038 | 0.034 |
| 2 | ddic_balanced_seed44_best | 0.035 | 0.036 | 0.034 |
| 3 | ddic_balanced_seed44_final | 0.035 | 0.034 | 0.035 |
| 4 | ddic_balanced_seed43_final | 0.035 | 0.034 | 0.035 |
| 5 | ddic_balanced_seed45_best | 0.035 | 0.034 | 0.035 |
| 6 | ddic_v2_balanced_seed42_final | 0.035 | 0.035 | 0.034 |
| 7 | ddic_balanced_seed46_final | 0.035 | 0.038 | 0.031 |
| 8 | ddic_balanced_seed43_best | 0.034 | 0.034 | 0.034 |
| 9 | ddic_v2_balanced_seed43_best | 0.034 | 0.034 | 0.034 |
| 10 | ddic_balanced_seed42_final | 0.034 | 0.034 | 0.034 |
| ... | (10 more) | ~0.033 | | |
| 18 | **ddic_phase3v2_seed44** (旧 verdict 锁定) | 0.033 | 0.033 | 0.033 |
| 20 | adaptive_K10_K400 | 0.010 | | |
| 21 | no_control | 0.010 | | |

**所有 DDIC ckpt 在 0.033-0.036 之间** (差 ~10%). DDIC 仅在 smoothness 上**勉强**优于
adaptive/no-ctrl, 物理动态量级全部 fail.

---

## 4. 5/6 Axis 为何全 fail (按贡献度)

| Axis | 项目 | 论文 | 倍数差 | 修法 | 修法成本 |
|---|---|---|---|---|---|
| ΔH range | ~5 | 350 | **70× 偏小** | H₀ baseline 从 10s 拉到 100s + ΔH ∈ [-100,250] | 偏离 Kundur [49] + 重训 |
| ΔD range | ~15 | 700 | **45× 偏小** | 同上 D₀ | 同 |
| max \|Δf\| | ~0.5 Hz | 0.13 | **4× 偏大** | 启 IEEEG1 governor + AVR | 离开论文 §II-A scope |
| final \|Δf\|@6s | ~0.2 Hz | 0.08 | **2.5× 偏大** | 同 governor | 同 |
| settling_s | ∞ | 3 s | **质性失败** | 同 governor | 同 |
| smoothness | std 2-22 | ~0 | (按 axis 0.5-0.9) | actor 加 action-smoothing penalty | **项目内可改** |

**唯一可在论文 scope 内修的 axis = smoothness**.
其他 5 axis 都需要离开论文 §II-A 声明的 "ignore inner loop" scope.

---

## 5. 真实复现状态 (按 axis)

| 维度 | 状态 | 评估 |
|---|---|---|
| Reward 公式 (Eq.15-18) | ✅ 实现一致 | metrics.py 等价于论文 §8.2 公式 |
| MDP / SAC / Algorithm 1 | ✅ 实现 | 标准 SAC + Eq.11-23 + 训练循环 |
| 修改 Kundur 拓扑 | ✅ 实现 | ANDES `kundur_full.xlsx` + 项目自加 |
| dt=0.2s / M=50 / episode=10s | ✅ 一致 | 2026-05-05 dt fix 后正确 |
| DDIC > Adaptive > NoCtrl ranking | ✅ 一致 | n=5 seed 验证 |
| max \|Δf\| 量级 | ❌ 4× 偏大 | 系统欠阻尼 |
| Δf 收敛 | ❌ ∞ vs 3s | 不收敛 |
| ΔH/ΔD 范围 | ❌ 45-70× 偏小 | physical floor + H₀ 选择 |
| ΔH/ΔD 平滑度 | ❌ 高频锯齿 | actor 输出 stochastic, 无 smoothing |
| cum_rf 量级 (sync 积分) | ⚠️ 偶然匹配 | 此项 9.4% diff 是 cherry-pick |

**结论**: **机制正确**, **物理量级失配**. 论文 = 1.0, 项目 = 0.036.

---

## 6. 历史决策记录

- **2026-05-06 旧 verdict 标 PASS** — 基于 cum_rf 单维 (-2.9% / -6.2% / +9.4%). **失败**: 没看
  max_df / final_df / settling / range / smoothness, 没意识到 cum_rf 对 step-jitter 不敏感.
- **2026-05-07 6-axis 评估** — 用论文 Fig.6/7/8/9 视觉提取的 5 个动态指标 + smoothness +
  cum_rf, 几何平均强制 holistic. 结果暴露所有 model overall < 0.04.
- **教训**: 评判 metric 必须**多维 + 几何均值**, 任一项 0 → 总分 0. 不能用单维 cherry-pick.

---

## 7. 下一步路径 (按 ROI)

| 优先 | 动作 | 期望提升 | 论文 scope 内? |
|---|---|---|---|
| **P0** | 在 reward 加 \|Δa_t - Δa_{t-1}\|² 项, 重训 | smoothness axis 0.7→1.0, overall 0.04→0.06 | ✅ 标准 RL 技巧 |
| P1 | 启 ANDES IEEEG1 governor + AVR, 重 eval | max_df 4×→2×, final_df 2.5×→1.2×, settling ∞→6s | ⚠️ 论文 §II-A 未明示 |
| P2 | 重选 H₀=50, ΔH=[-50,150], 重训 | range axis 0→1, overall 大幅提升 | ⚠️ 偏离 Kundur [49] |
| ✗ | 继续追"cum_rf paper-grade" | 已被证伪是 cherry-pick | — |

详见 `quality_reports/plans/2026-05-07_andes_6axis_recovery.md` Phase A-E.

**写论文如何处理**: 不能再说"复现论文". 改 contribution 为:
- "ANDES Kundur full + 4 ESS GENCLS 实现机制 + 训练 SAC 收敛"
- "DDIC > Adaptive > NoCtrl ranking 一致, 但物理量级偏离 (5 类 documented deviation)"
- "5 axis (max_df / final_df / settling / range / smoothness) 实测项目分数 ~0.04, 揭示
  GENCLS-only + 论文 §II-A scope 内不可达"

---

## 8. 文件指针

| 文件 | 内容 |
|---|---|
| `evaluation/paper_grade_axes.py` | 6-axis 评估函数 + benchmark 数据 + 批量 ranking |
| `results/andes_paper_alignment_6axis_2026-05-07.json` | 21 ckpt × 7 axis × 2 scen 完整数据 |
| `paper/figures/MODELS_INDEX.md` | per-model 图目录 |
| `quality_reports/verdicts/2026-05-06_andes_paper_figs_v1_v2_verdict.md` | (SUPERSEDED, 历史) |
| `scenarios/kundur/NOTES_ANDES.md` §1 | 修代码必读 |

---

*Last computed: 2026-05-07 from `results/andes_eval_paper_specific_v2_envV2_hetero/`*
*Re-run command: `python evaluation/paper_grade_axes.py`*
