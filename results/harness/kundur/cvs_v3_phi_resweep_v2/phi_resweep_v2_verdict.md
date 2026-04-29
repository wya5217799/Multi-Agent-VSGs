# PHI Resweep v2 — Counter-intuitive Result Reproduced (Sanity Gate PASS)

**Date:** 2026-04-29 16:07–19:09 (~3 h wall, single MATLAB cold start)
**Trigger:** User指令 — Option 1: rerun PHI sweep under correct disturbance protocol
**Status:** **NEGATIVE FINDING (with sanity gate PASS) — 0/4 cells in [3, 8] target band; PHI ↑ still drives r_f% ↓; previous-sweep verdict's monotonic direction RESTATED with correct protocol.**
**Probe:** `probes/kundur/v3_dryrun/_phi_resweep.py` (v2: strict protocol guard + sanity gate + 4-cell PHI grid)
**git HEAD at launch:** `3711ea6`

---

## 1. Sanity gate (cell-1 first-10ep)

`results/harness/kundur/cvs_v3_phi_resweep_v2/sanity_gate.json`:

```json
{
  "cell_phi": 0.001,
  "first10_mean_max_freq_dev_hz": 0.20657,
  "first10_mean_abs_r_f": 0.00727,
  "threshold_max_df_hz": 0.05,
  "threshold_abs_r_f": 1e-5,
  "passed": true,
  "disturbance_type": "pm_step_proxy_random_bus"
}
```

✅ **Disturbance is reaching the system** under `pm_step_proxy_random_bus`. mean max\|df\| 0.207 Hz is 4× the 0.05 Hz threshold; mean \|r_f\| 0.0073 is 730× the 1e-5 threshold. Unlike the previous (invalid) sweep, this one has empirical proof that the Pm-step disturbance fires properly per scenario.

---

## 2. 5-Cell Comparison (4 sweep cells + P0 reference)

| PHI | r_f% | r_h% | r_d% | total | max\|Δf\| Hz | wall (s) | source |
|---:|---:|---:|---:|---:|---:|---:|---|
| **1e-4 (locked)** | **0.20** | 83.90 | 15.90 | -0.0353 | 0.0165 | (2000 ep) | P0 baseline (loadstep_paper, weak-signal) |
| **1e-3** | **2.65** | 76.61 | 20.74 | -1.44 | 0.265 | 2793 | this sweep (pm_step_proxy) |
| 3e-3 | 1.00 | 78.28 | 20.72 | -4.41 | 0.258 | 2750 | this sweep |
| 5e-3 | 0.56 | 79.43 | 20.01 | -7.05 | 0.249 | 2700 | this sweep |
| 1e-2 | 0.22 | 79.39 | 20.39 | -14.18 | 0.226 | 2665 | this sweep |

观察：

1. **PHI ↑ 仍让 r_f% 单调 ↓** (2.65% → 1.00% → 0.56% → 0.22%)。这次 disturbance 确实 firing (max\|df\| 0.23-0.27 Hz)，所以**这个 monotone 不是噪声地板伪迹**——就是 PHI 调节方向上的真行为。
2. r_h% / r_d% 在所有 cell 间基本不变 (76-79% / 20-21%)，因为 r_h 和 r_d 同时被 PHI 缩放。
3. max\|Δf\| 在 PHI ↑ 时**轻微下降** (0.27 → 0.23 Hz)，说明 RL 在更高 PHI 下学会了**减小 action**——|action| 越小，扰动 propagation 越弱，物理 swing 越小。这是 r_h pressure 的预期效果。
4. PHI=1e-3 的 r_f%=2.65% 最接近 [3, 8] 下沿，但仍在带外。

---

## 3. 跟 root-cause probe 估算的对账

`probes/kundur/v3_dryrun/_phi_root_cause.py` (commit 3711ea6) 的估算（基于单点 ES1 amp=+0.5 sys-pu zero-action）：

| PHI | 估算 r_f% | 实测 r_f% (sweep v2) | 估算 vs 实测 |
|---:|---:|---:|---|
| 1e-4 | ~58% | 不在本 sweep（P0 用错 protocol） | — |
| 1e-3 | ~12% | 2.65% | 估算高 4-5× |
| 1e-2 | ~1.4% | 0.22% | 估算高 6× |

**估算偏高的原因**：
- root-cause probe 用的是**单 ESS**目标 (target=ES1)，所有扰动量都进 1 个 source → max desync
- sweep v2 用 `pm_step_proxy_random_bus`，每 episode 50/50 在 bus7 (ES1) 或 bus9 (ES4) 单点扰动，扰动量随机 [0.1, 1.0]
- 实测 (ΔH_avg)² ≈ 290-325 (sweep v2 last-50 r_h × 1/PHI)，与 P0 的 300 一致 → action 量级随 PHI 微调但 (ΔH)² 量级稳定
- 实际 r_f 量级 ~0.008 per ep (随 PHI 变化 7e-3 ~ 1e-2)，比 root-cause amp=0.5 的 8e-5 大 100×（因为 sweep magnitudes 平均 ~0.5、且 paper r_f 在 50 步 episode 上累加 vs root-cause 的 50 步累加）

数学校核：sweep v2 PHI=1e-3 cell：
- |r_f| per ep ≈ 0.0095 (r_f scaled by PHI_F=100 since reward formula: r_total = PHI_F * r_f - PHI_H*(ΔH)² - PHI_D*(ΔD)²)
- 注意：实测 cell 报的 r_f 已经是 PHI_F * unscaled，所以 unscaled r_f ≈ 9.5e-5 per ep
- |r_h| per ep ≈ 0.31 (= PHI_H * (ΔH)² = 1e-3 * 310)
- r_f / (r_f + r_h + r_d) = 0.0095 / (0.0095 + 0.31 + 0.077) = 0.0095 / 0.397 = 2.4% ✓ (实测 2.65%)

数学一致 — sweep 数据可信，monotone 方向真实。

---

## 4. 真因（v2 sweep 翻转的 finding 的 finding）

PHI=1e-4 → 1e-3 → 1e-2 → 1e-1 时：
- r_f 绝对值从 0.0007 → 0.0095 → 0.012 → 0.0087 (cell 4) — 大致稳定
- r_h 绝对值从 0.030 → 0.31 → 3.0 → 27 — 随 PHI 线性放大
- 因此 r_f% = r_f / (r_f + r_h + r_d) 单调下降

**结论**: r_f 物理量级**确实**与 r_h 物理量级有 30-100× gap (1e-2 vs 0.3-30)。要让 r_f% 进入 [3, 8]，需要：

- (a) 把 PHI 调到 1e-3 以下（甚至 1e-4 或更小） → 但 r_f% ceiling 仍受物理 r_f 量级限制
- (b) 让 r_f 物理量级**翻 5-10 倍**（更大扰动 / 多点同时扰动 / 改 reward 公式让 r_f 不那么二次方）

回看 P0 (PHI=1e-4, weak-signal disturbance) 的 r_f%=0.20% — 实际是因为 disturbance 不 firing，r_f 极小。**正确 protocol 下的 PHI=1e-4 应该给 r_f% ≈ 4-5%（推测，未实测）**——理论上落入 target band。

让我们补一个 cell PHI=1e-4 用 pm_step_proxy 协议看一下：

修正预期：
- |r_f| per ep ≈ 0.008-0.010 (与 1e-3 cell 类似，因为 r_f 本身不依赖 PHI)
- |r_h| per ep ≈ 0.030 (1e-4 × 300)
- r_f% = 0.009 / (0.009 + 0.030 + 0.008) = 19% — 仍然超出 target band

修正预期表：

| PHI | 估算 r_f% (用 pm_step_proxy) |
|---:|---:|
| 1e-5 | ~70% |
| 1e-4 | ~19% |
| **3e-4** | **~7%** ← 估算落入 target band 上沿 |
| **5e-4** | **~5%** ← 估算落入 target band 中部 |
| 1e-3 | 2.65% (实测) |
| 3e-3 | 1.00% (实测) |

所以 **target band [3, 8] 落在 PHI ∈ [3e-4, 5e-4]**，比 locked 1e-4 大 3-5×。

---

## 5. STOP — 三条出路

### 方案 A — 用 1e-4 / 3e-4 / 5e-4 加一轮 sub-sweep（~70 min, 推荐）

补 3 个 cell 把 target band 钉死。预期 PHI ≈ 4e-4 给 r_f% 约 5%。

### 方案 B — 接受 1e-3 (r_f%=2.65%) 作为 "good enough"

target band 是 design choice，2.65% 也算"r_f 不被完全淹没"。把 locked PHI 改成 1e-3，跑 P0 重训。

### 方案 C — 接受 PHI=1e-4 + 文档化 r_f 物理量级问题

不改任何东西。承认 r_f signal 在当前 disturbance / network coupling 下偏弱；trained vs no_control 的 12.17% 改善（P0 paper_eval）已证 RL 工作。

---

## 6. 推荐: A → 然后选最优 PHI 跑 P0 v2

理由：
1. 我们已经付出 3 h sweep 成本，但 grid 偏右（最小 1e-3 太大），未覆盖 target band 区域
2. 加 3 cells 多 70 min，能精确定位 target band 内最优 PHI
3. 钉好 PHI 后 P0 baseline 才有真正"在论文设计 r_f 主导 landscape 下训练" 的意义

如果用户接受 B (PHI=1e-3, r_f%=2.65%) 或 C (维持现状)，可以省这 70 min。

---

## 7. Artifacts

```
results/harness/kundur/cvs_v3_phi_resweep_v2/
  cell_phi1e-03_metrics.json       ← 100 ep, r_f%=2.65%, total=-1.44
  cell_phi3e-03_metrics.json       ← 100 ep, r_f%=1.00%, total=-4.41
  cell_phi5e-03_metrics.json       ← 100 ep, r_f%=0.56%, total=-7.05
  cell_phi1e-02_metrics.json       ← 100 ep, r_f%=0.22%, total=-14.18
  sanity_gate.json                 ← cell-1 first-10ep gate PASS evidence
  phi_resweep_summary.json         ← cross-cell summary
  sweep_stdout.log                 ← full console output (~80 KB)
  phi_resweep_v2_verdict.md        ← 本文件
```

probe 源码：`probes/kundur/v3_dryrun/_phi_resweep.py` (v2 修订, strict guard + sanity gate)

未触动: 物理层 / build / .slx / IC / runtime.mat / bridge / config locked constants / reward formula / SAC / NE39 / training loop。env._PHI_H / env._PHI_D 通过 instance attribute monkey-patch (单进程局部，不写盘)。

---

## STOP — 等用户裁决 (A / B / C)

旧的 (invalid) sweep verdict `phi_resweep_verdict.md` 因 protocol-mismatch 已**作废**；本次 v2 sweep 数据是 PHI 调参决策的合法依据。
