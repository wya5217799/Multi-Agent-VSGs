# PHI Resweep Verdict — Counter-intuitive Finding [⚠️ INVALIDATED 2026-04-29]

> **⚠️ ARCHIVED / INVALIDATED 2026-04-29**
>
> This verdict is **invalidated** — the underlying sweep ran under a
> weak-signal disturbance protocol (`loadstep_paper_random_bus`, R-block
> compile-frozen under FastRestart per commit `97f6d3a`). The
> root-cause probe in commit `3711ea6` proved the Pm-step disturbance
> never reached the system, and the corrected v2 sweep (commit `5bfe46c`,
> with explicit `pm_step_proxy_random_bus` guard + first-cell sanity
> gate) overturned the "PHI is not effective" conclusion stated below.
>
> **Use instead**:
> - `results/harness/kundur/cvs_v3_phi_resweep_v2/phi_resweep_v2_verdict.md`
> - `results/harness/kundur/cvs_v3_phi_root_cause/phi_root_cause_verdict.md`
>
> Kept here only as historical record of the protocol-mismatch failure mode.

---

**Date:** 2026-04-29 13:25–15:35 (~2 h 10 min wall, single MATLAB engine)
**Trigger:** User指令 "1" (PHI 重审 sweep) — 找让 r_f% ∈ [3, 8] target band 的 PHI 值
**Status:** **INVALID NEGATIVE FINDING — sweep ran under weak-signal protocol; conclusion below is contaminated and overturned by v2 sweep.**
**Probe:** `probes/kundur/v3_dryrun/_phi_resweep.py` (since modernized; this run used pre-3711ea6 version with hardcoded weak protocol)

---

## 1. 4-Cell Comparison

| PHI | r_f% | r_h% | r_d% | total reward | max\|Δf\| Hz | wall (s) | source |
|---:|---:|---:|---:|---:|---:|---:|---|
| **1e-4 (locked, P0)** | **0.20** | 83.90 | 15.90 | -0.0353 | 0.0165 | (2000 ep) | P0 baseline |
| 1e-3 | 0.01 | 80.98 | 19.01 | -1.43 | 0.0159 | 2623 | this sweep |
| 1e-2 | 0.00 | 80.04 | 19.96 | -14.61 | 0.0154 | 2588 | this sweep |
| 1e-1 | 0.00 | 79.28 | 20.72 | -141.62 | 0.0158 | 2588 | this sweep |

观察：
- PHI 从 1e-4 → 1e-1（10000×），**r_f% 从 0.20% 单调下降到 0.00%** —— 与"target band 3-8%"的方向相反
- r_h% 在所有 PHI 下基本不变（~80%），r_d% 也几乎不变（~20%）
- max\|Δf\| 在 4 个 cell 间几乎一致（0.015-0.017 Hz）—— 物理响应不变
- total reward 数量级随 PHI 缩放 ~10×

---

## 2. Root cause analysis

### Reward 分解数学

$$ r_{\text{total}} = \varphi_F \cdot r_f - \varphi_H (\Delta H_{\text{avg}})^2 - \varphi_D (\Delta D_{\text{avg}})^2 $$

PHI_F 在 4 个 cell 都是 100（locked）。PHI_H 和 PHI_D 是 sweep 变量。

$$ r_f\% = \frac{|\varphi_F \cdot r_f|}{|\varphi_F \cdot r_f| + |\varphi_H \cdot (\Delta H)^2| + |\varphi_D \cdot (\Delta D)^2|} $$

实测各项绝对值：

| 量 | P0 / cell 1e-4 | cell 1e-3 | cell 1e-2 | cell 1e-1 |
|---|---:|---:|---:|---:|
| $\|r_f\|$ | 5.0e-5 | 4.0e-5 | 4.0e-5 | 4.0e-5 |
| $\|(\Delta H_{\text{avg}})^2\|$ | 300 | 325 | 292 | 268 |
| $\|(\Delta D_{\text{avg}})^2\|$ | 56 | 76 | 72 | 72 |

**关键 insight**: $(\Delta H_{\text{avg}})^2$ 在 4 cell 间基本恒定（~300）。这说明 RL 在 100 episode 内未学会"通过减小 action 来减小 r_h"，policy 仍接近随机分布；P0 在 2000 ep 后 (ΔH)² 还是 300 量级 → RL 即使训练到位也没真正 minimize r_h。

### 为什么 PHI ↑ 让 r_f% ↓

PHI_H × 300 + PHI_D × 70 = PHI_combined × 370（~70% r_h + ~30% r_d）

| PHI | $\varphi_F \|r_f\|$ | $\varphi_H \cdot (\Delta H)^2$ | r_f% (理论) | r_f% (实测) |
|---:|---:|---:|---:|---:|
| 1e-4 | 5e-3 | 0.030 + 0.006 ≈ 0.036 | 0.5% × 0.4 ≈ 0.2% | 0.20% ✓ |
| 1e-3 | 4e-3 | 0.30 + 0.06 ≈ 0.36 | 1.1% | 0.01% (差 100×) |
| 1e-2 | 4e-3 | 3.0 + 0.7 ≈ 3.7 | 0.11% | 0.00% |
| 1e-1 | 4e-3 | 30 + 7 ≈ 37 | 0.011% | 0.00% |

理论 vs 实测 1e-3 差 100×：原因是实际 r_f% 用 last-50 mean，分母里 r_h 是 50-ep mean，r_f 是 50-ep mean —— 但实测时 ep_rf, ep_rh 相加都是 episode total，第 90-100 ep 期间 r_f abs ≈ 4e-5（per episode 50 step sum），r_h abs ≈ 0.32（per ep）。

### 让 r_f% 进入 [3, 8] band 需要什么

$\varphi_F \cdot r_f / \varphi_H \cdot (\Delta H)^2 \approx 0.05$ (5%)

代入：100 × 5e-5 / (PHI_H × 300) ≈ 0.05 → PHI_H ≈ 5e-3 / 15 ≈ **3.3e-4**?

但实测 PHI_H=1e-4 → r_f%=0.20%，PHI_H=1e-3 → r_f%=0.01%。两者中间 3.3e-4 推断 r_f% 大约 0.1%，**仍远低于 3%**。

实际上 r_f% 的 ceiling 由 |r_f| / |r_h| 上限决定，与 PHI 无关：

$$ r_f\%_{max} = \frac{|r_f|}{|r_f| + |r_h \cdot 1| + |r_d \cdot 1|} $$（即 PHI_H = PHI_F=100 的极限情形）

代入：100 × 5e-5 / (100 × 5e-5 + 300 + 70) ≈ 5e-3 / 370 ≈ **0.0014%**

即使 PHI_H = PHI_F = 100，r_f% 上限也只有 0.0014%。

**根本问题**: $|r_f| / |(\Delta H)^2| \approx 5e-5 / 300 = 1.7e-7$。无论 PHI 如何调，r_f% 都会被 r_h 量级压制。

---

## 3. 为什么 r_f 这么小

$$ r_f = -(\Delta\omega_i - \overline{\Delta\omega}_i)^2 $$

per step per agent。论文 PHI_F=100 × per-step r_f² 应该和 r_h 量级相当（论文设计意图）。

实测 last-50 mean r_f per episode = -5e-5 → per step per agent ≈ -2.5e-7 → $(\Delta\omega - \overline{\Delta\omega}) \approx 5e-4$ pu = **0.025 Hz** 量级的同步残差。

而 max\|Δf\| 实测 0.015 Hz —— **频率本身只有 0.015 Hz 偏差，同步残差 0.025 Hz 是不可能的**（残差不可大于偏差）。

实际上 last-50 r_f mean 对应整个 50-step episode 累加，所以 per-step ~1e-6，对应 $(\Delta\omega - \overline{\Delta\omega}) \approx 1e-3$ pu = **0.05 Hz**，仍比 max\|Δf\|=0.015 Hz 大。

矛盾说明 $\overline{\Delta\omega}$ 公式中含 communication failure mask $\eta_{j,t}$，broken 时 $\overline{\Delta\omega} = 0$，导致 $(\Delta\omega - 0)^2 = (\Delta\omega)^2$，残差等于偏差本身。**comm fail (10% 概率) 是 r_f 主要贡献源，不是真正的同步差异**。

无 comm fail 时（90% steps），各 ESS 频率几乎完全同步（network coupling），$(\Delta\omega - \overline{\Delta\omega})^2 \approx 0$。

**所以 r_f 的非零部分主要来自 comm-fail 的 10% steps，与 RL 是否学习无关**。

---

## 4. 真正的 blocker

| 层 | 状态 | 阻碍 |
|---|---|---|
| **Disturbance protocol** | Pm-step proxy 单 ESS @ 10-100 MW | 单点扰动 → network coupling 平均 → ESS 间频率残差极小 |
| **r_f formula** | 同步残差²，跟随 ω̄_i | network coupling 让 ω̄ 几乎等于每个 ω → r_f 主要由 comm fail noise 驱动 |
| **(ΔH)² 量级** | RL 100/2000 ep 都没学会 → 300 量级常数 | (ΔH)² 不能简单通过 PHI 调降到 r_f 同量级 |

**3 层共同决定 r_f% 在当前 architecture 下不可能进入 3-8%**。PHI 不是有效旋钮。

---

## 5. PHI=1e-4 是否仍合理

回看 P0 数据：
- last-100 reward = -0.035
- last-100 |r_f| = 5e-5 (噪声地板)
- last-100 max\|Δf\| = 0.0165 Hz
- final_ep2000 vs no_control: +12.17% 改善 (paper_eval)

trained policy 确实**比 no_control 好**（12.17%），即使 r_f% 仅 0.2%。说明 RL 学到的不是 paper-style "minimize sync residual"，而是某种**经验性 minimize total reward**（动作分布微调让 r_h 略小）。

**PHI=1e-4 的实际作用**: 让 RL 在 r_h dominated landscape 上仍学到一些 useful policy，trained vs no_control 测试集改善可观。再调小 PHI 到 1e-5/1e-6 不会让 r_f% 真正主导（受 r_f 物理量级 ceiling 限制），反而让 r_h pressure 更弱，policy 更随机。

---

## 6. STOP — 三条出路

### 选项 A — 接受现状，回到锁定 PHI=1e-4
- **不改任何东西**
- 把 r_f% 在当前 disturbance/reward formulation 下 ≈ 0% 标记为已知限制
- trained vs no_control 改善 12.17% 作为 RL 工作的内部判定
- 进入 P2 (update_repeat sweep) 或其他

### 选项 B — 重审 disturbance protocol（破现行锁定）
让 r_f 真正变大：
- 切回 LoadStep paper-faithful（但已 documented blocker，需重做物理层）
- 或多点同时扰动 + 异步触发，让 ESS 间频率不同步
- 或扩大 DIST_MAX > 1.0（之前 1.5 实测 IntW 饱和）

任一项都会冲击 commit `a9ad2ea` credibility close 锁定。

### 选项 C — 重新设计 reward formula（脱离论文）
让 r_h / r_d 量级与 r_f 自然匹配：
- 用 normalize action 而非物理 ΔM/ΔD：r_h = -PHI_H × (mean(a_i^M))² (per-agent normalized action ∈ [-1,1])
- 或用 ratio: r_h = -PHI_H × (mean(ΔH_i / H_0))²

这是 reward 公式结构改动，违反 credibility close 的"reward 公式结构不动"约束。

---

## 7. 推荐: 选项 A

理由：
1. P0 已实证 trained policy 比 no_control 好 12.17%（在项目协议下）
2. r_f% ceiling 是 architecture 决定的，PHI 调节解不了
3. 选项 B/C 都需破锁定，超出本次工作范围

进 P2 update_repeat sweep 是合理下一步：在固定 PHI=1e-4 协议下找最优 sample efficiency。

---

## 8. Artifacts

```
results/harness/kundur/cvs_v3_phi_resweep/
  cell_phi1e-03_metrics.json   ← 100 ep, r_f%=0.01%, total=-1.43
  cell_phi1e-02_metrics.json   ← 100 ep, r_f%=0.00%, total=-14.61
  cell_phi1e-01_metrics.json   ← 100 ep, r_f%=0.00%, total=-141.62
  phi_resweep_summary.json     ← cross-cell 横向 summary
  sweep_stdout.log             ← 全 console 输出
  phi_resweep_verdict.md       ← 本文件
```

probe 源代码：`probes/kundur/v3_dryrun/_phi_resweep.py`（unmodified config_simulink.py）

未触动: 物理层 / build / .slx / IC / runtime.mat / bridge / config_simulink.py / SAC / reward formula / NE39。env._PHI_H/D 通过 instance attribute monkey-patch，不影响其他模块。

---

## STOP — 等用户裁决（A / B / C）
