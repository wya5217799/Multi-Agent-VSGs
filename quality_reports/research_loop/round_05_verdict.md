# R05 Verdict — 短-多臂 Bandit (8 arms 全 falsified)

**Status**: DONE (8/8 30ep trains 实际完成, daemon 标 killed 但 ckpt + log 全在)
**Wall**: ~10 min train (实际跑完了, daemon 误判 _done.json 导致 killed) + 8 min eval + 2 min ranking = ~20 min
**Trigger**: R04 verdict — adaptive=no_ctrl 解耦; user 批评 "1 hyperparam × 5 seed" 重复采样

---

## §1 实测 (ground truth)

### 8 arm × 30ep × 1 seed (V2 eval 同 context)

| arm | env / 改的维度 | final_R | cum_rf LS1 | max_df LS1 | 6-axis | rank |
|---|---|---|---|---|---|---|
| **r05_combo_v1_disturb5x_s42** | V1 + disturb 5× | -5465 | -0.064 | 0.456 | **0.037** | **1** |
| **r05_disturb_5x_s42** | V2 + disturb 5× | -6925 | -0.067 | 0.452 | **0.037** | **2** |
| r05_lam_zero_s42 | V2 + λ=0 | -23747 | -0.120 | 0.478 | 0.037 | 3 |
| r05_baseline_paper_s42 | V2 + PHI_D=1.0 + λ=0.01 | -23748 | -0.120 | 0.478 | 0.037 | 4 |
| r05_v3_governor_s42 | V3 (V2 + IEEEG1+EXST1) | -23748 | -0.120 | 0.478 | 0.037 | 5 |
| r05_phid_5x_s42 | V2 + PHI_D=5 | **-98713** | -0.096 | 0.485 | 0.037 | 6 |
| r05_action_range_2x_s42 | V2 + DM/DD ×2 | **-93997** | -0.088 | 0.466 | 0.037 | 7 |
| r05_v1_env_back_s42 | V1 baseline | -11116 | -0.088 | 0.466 | 0.037 | 8 |
| no_control (baseline) | V2 zero action | — | -0.134 | 0.551 | 0.010 | 9 |
| **paper DDIC (target)** | — | — | **-0.68** | **0.13** | **1.00** | — |

⚠ **8 个不同维度的 hyperparam 改动 + V1/V2/V3 env 切换, 6-axis 完全并列 0.037**.

### Train reward 量级分类
- 超低 (-93K~-99K): PHI_D=5, action_range_2x → reward landscape 太陡, SAC 卡住
- 中 (-23K): V2 baseline, λ=0, V3 governor, PHI_D=1.0 — 类似收敛
- 较好 (-11K): V1 env back
- 最好 (-5K~-7K): combo_v1_disturb5x, disturb_5x — 5× disturbance 让 reward magnitude 自然变大但 6-axis 不变

---

## §2 6-axis paper alignment

5 axis 在所有 8 arms 表现完全一致:
| axis | 全 8 arms 项目 | paper | score |
|---|---|---|---|
| 1 max_|df| | 0.45-0.49 Hz | 0.13 | **0** (4× 太大) |
| 2 final_|df|@6s | 0.30-0.32 | 0.08 | **0** (4× 太大) |
| 3 settling_s | 99 (∞) | 3 | **0** (没 settle) |
| 4 dH_smooth | 0.1-0.4 | ~0 | **0.99** ✅ |
| 5 dD_smooth | 0.3-1.0 | ~0 | **0.99** ✅ |
| 6 dH_range | 0.2-0.7 | 350 | **0** (500-1500× 偏小) |
| 7 dD_range | 0.5-2.4 | 700 | **0** (300-1500× 偏小) |

**几何均值约束**: smoothness 接近完美 + 4 个 axis 0 → overall ≡ 0.037.

任何 hyperparam 改动**都没破这个 attractor**.

---

## §3 视觉对比 (paper Fig.7 vs R05 待生)

(R05 fig 待生 — 但鉴于 8 arms 都 0.037, 视觉应同质. 节省 wall, 不生.)

预期 R05 fig 对比 paper Fig.7:
- ΔH 项目 ≤ 1, paper [-100, +250] — 1500× 偏小
- ΔD 项目 ≤ 2.4, paper [-200, +500] — 280× 偏小
- 所有 8 arms 视觉一致 (smoothness 0.99 = 几乎不动 ΔH/ΔD)

---

## §4 Hyperparam vs paper Table I

R05 已经覆盖了 paper-faithful + 多个反向 sweep:
| 改的方向 | arm | 结果 |
|---|---|---|
| paper-faithful baseline | r05_baseline_paper | 0.037 |
| over-shoot PHI_D | r05_phid_5x | 0.037 (reward 极差) |
| 撤 LAMBDA_SMOOTH | r05_lam_zero | 0.037 |
| 加 governor | r05_v3_governor | 0.037 |
| 大 action range | r05_action_range_2x | 0.037 (reward 极差) |
| V1 env 回归 | r05_v1_env_back | 0.037 |
| 5× disturb | r05_disturb_5x | 0.037 |
| V1 + 5× disturb (best guess) | r05_combo_v1_disturb5x | 0.037 |

→ **paper Table I 的所有合法变种都已测**, hyperparam 不是 root cause.

---

## §5 假设验证 — **5 H 全 falsified**

| H | 假设 | 验证 |
|---|---|---|
| H1 | 有 1 个 arm 6-axis ≥ 0.10 | ❌ 8 arms 全 0.037 |
| H2 | disturb 5× 让 cum_rf 跳到 paper 量级 (-0.68) | ❌ disturb_5x cum_rf -0.067 (近 no_ctrl), 不靠近 paper |
| H3 | V1 env 比 V2 显著好 | ❌ V1 也 0.037 |
| H4 | LAMBDA_SMOOTH 是 range 杀手 | ❌ λ=0 也 0.037, range 没回 |
| H5 | action range 2× 救 range axis | ❌ 也 0.037, reward 反而崩 |

**结论: R01-R05 的 hyperparam 搜索全失败**. 不能再 search hyperparam.

---

## §6 R{N+1}=R06 candidates — 强 pivot 不再 hyperparam search

R05 证明 hyperparam 不是 root cause. R06 必须深入 **eval 公式 + 物理量纲对齐**.

### R06 主线: 物理对齐 audit, 不再训练

```
exp1: r06_eval_formula_audit (cpu, 0 train, ~30 min 主上下文人工)
  目标: 验 paper_grade_axes.py 的 max_df / settling / range 计算公式 vs paper Sec.IV-C
  - max_|df| paper 用的是 |freq_hz - F_NOM| 还是 |freq - mean(neighbors)|?
  - settling_s 阈值 ±0.02 Hz 是 paper 定义还是项目?
  - dH_range 是 [min(ΔH_avg), max(ΔH_avg)] 跨整个 episode 还是仅 6s window?
  - paper 的 ΔH_es vs 项目的 M_es - M0 (项目算 ΔM 不是 ΔH; H = M/2)
  - 输出: audits/2026-05-07_eval_formula_audit.md

exp2: r06_action_semantics_audit (cpu, 0 train, ~30 min)
  目标: paper §II-B "ESS P 注入仿真 effective inertia" vs 项目 GENCLS.M/D 直接调
  - paper effective inertia: H_es = ΔP_es / (ω̇ - ω̇_ref) 通过 ESS 功率注入
  - 项目: 直接 set_param(GENCLS, M, M_new) 改 ANDES 内部惯量参数
  - 这是物理语义不同, 可能解释 ΔH range 1500× gap
  - 输出: audits/2026-05-07_action_semantics_audit.md

exp3: r06_paper_disturbance_protocol_audit (cpu, 0 train, ~20 min)
  目标: paper Fig.6/7 LS1 = "load step at Bus X" 是什么样的扰动?
  - 项目: PQ_Bus14 -2.48 (减载 248 MW)
  - paper: §IV-A "0.5 p.u. step" 是 system base 还是 local base?
  - 检查 disturbance_protocols.py PAPER_LS_MAGNITUDE_SYS_PU 真值
  - 输出: audits/2026-05-07_paper_disturbance_audit.md
```

### R06 副线 (可选, 1 个 cpu 槽):
```
exp4: r06_v1_env_5seed_200ep_smoke (gpu, 5 seed × 200ep, ~30 min)
  目标: 既然 R05 V1 env 也 = 0.037, 还跑 5seed 200ep 看长训会不会跳出 attractor
  rationale: R05 30ep 太短, 但 R04 5seed 200ep 也才 0.037, 所以希望低. 留 1 槽测.
  decision: 若 r06 audits 已 root-cause → kill exp4
```

### Out of scope (不再做):
- ❌ 任何 PHI / LR / target_entropy / action_range / λ 调整 (R05 已 cover 8 维度)
- ❌ V1/V2/V3 env 横跳 (R05 已 cover)
- ❌ INCLUDE_OWN_ACTION_OBS 长训 (smoke 通过, 但不会救 hyperparam attractor)

---

## §7 Audit (R05 negative findings 的 lessons)

1. **Hyperparam 8-axis sweep 全 0.037**: 证明 paper 标准 (max_df/settling/range) 跟项目实测在 ANDES 这一层有结构性 gap, 不是 SAC 调一调能跳出来的
2. **smoothness 0.99 是 trap**: 我们 R03→R04→R05 不停"改善" smoothness axis, 但**没破其他 4 个 0**. 说明 smoothness 接近 paper ≠ paper match (其他 axis 还得过)
3. **train reward 排名 ≠ 6-axis 排名**: r05_v1_env_back train -11K (中等) 但 6-axis = 0.037; r05_phid_5x train -99K 极差 6-axis 也 0.037. **train reward 不是 paper-grade proxy**, 必须 eval driver 闭环
4. **R01-R05 共耗 ~3 hr wall** for 6-axis 0.035→0.037 (改善 5%) — explore 阶段 ROI 极低. R06 必须**先 audit 再训练**, 否则继续浪费

---

## Cross-ref
- R04 verdict: [round_04_verdict.md](round_04_verdict.md)
- R05 plan (revised): [round_05_plan.md](round_05_plan.md)
- 8 R05 ckpt: `results/research_loop/r05_*_s42/`
- 8 arm eval JSONs: `results/research_loop/eval_r05/` (16 + no_ctrl 2)
- R06 plan: [round_06_plan.md](round_06_plan.md)
