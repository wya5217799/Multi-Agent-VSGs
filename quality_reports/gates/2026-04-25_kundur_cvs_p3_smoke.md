# Gate P3 — Kundur CVS zero-action smoke (4-VSG, 10s)

**Date:** 2026-04-25
**Branch:** `feature/kundur-cvs-phasor-vsg`
**Predecessor:** [Gate P2 PASS](2026-04-25_kundur_cvs_p2_episode.md)
**Scope:** 4-VSG zero-action 10s sim 物理稳态 + 同步 + IntD + Pe 一致性

---

## Verdict

**PASS — OVERALL: PASS**

| Check | Threshold | Result | Verdict |
|---|---|---|---|
| ω tail_mean ∈ [0.999, 1.001] | per-agent | VSG1/2=0.99996, VSG3/4=0.99978 | ✅ PASS |
| inter-agent sync (max-min) | < 0.01 pu | spread = 1.77e-4 | ✅ PASS (50× 余量) |
| IntD not near ±π/2 | < π/2 - 0.01 | max\|delta\|=1.211 vs 1.571 | ✅ PASS (23% 余量) |
| Pe ≈ Pm0 (±5%) | per-agent | VSG1/2 Pe=0.497, VSG3/4 Pe=0.504 (Pm0=0.5) | ✅ PASS |

无 NaN / Inf / early termination。无 nontunable warning。

---

## 实测数据

10s sim, tail = last 2s window:

| Agent | tail_mean ω | tail_std ω | max\|delta\| (rad) | Pe_tail_mean |
|---|---|---|---|---|
| VSG1 | 0.999959 | 4.18e-4 | 0.149 | 0.497 |
| VSG2 | 0.999959 | 4.18e-4 | 0.149 | 0.497 |
| VSG3 | 0.999782 | 1.22e-3 | 1.211 | 0.504 |
| VSG4 | 0.999782 | 1.22e-3 | 1.211 | 0.504 |

VSG1/2 与 VSG3/4 略不同步（0.999959 vs 0.999782，差 1.77e-4）但都在带内。VSG3/4 通过 L_tie 接 BUS_left，IntD 稳态值更大（1.21 vs 0.15）反映 NR 估算的稳态相位 0.355 rad，并叠加慢速 swing oscillation（period ~ 4-5s）。

---

## IC（per-agent）

按手算 NR 解（cvs_design.md §3 待 NR 升级）：
- AC_INF anchors BUS_left at 0 rad
- L_tie 稳态承载 1.0 pu (R→L)
- θ_BUS_right = asin(1.0 × 0.30) = 0.30537 rad
- δ_VSG_local = asin(0.5 × 0.10) = 0.05016 rad

| VSG | delta0 (rad) |
|---|---|
| VSG1, VSG2 (BUS_left) | 0.05016 |
| VSG3, VSG4 (BUS_right) | 0.30537 + 0.05016 = 0.35553 |

---

## P3 失败 → PASS 修复路径（已记入 cvs_design.md §3 待办）

| 阶段 | omega_band | sync | IntD | Pe ±5% |
|---|---|---|---|---|
| Initial 5s, IC delta0 = 0.05 全相同 | FAIL (VSG3/4 1.0016) | PASS | FAIL (max=1.64) | FAIL (Pe=0.60) |
| Per-agent IC: VSG3/4 = asin(0.5*0.40)=0.20 (失败的简化) | PASS | PASS | PASS | FAIL (Pe=0.60) |
| Per-agent IC: hand-NR (delta0_right=0.36) | PASS | PASS | PASS (max=1.21) | FAIL (Pe=0.57, transient 残留) |
| **同上 + 10s 仿真** | **PASS** | **PASS** | **PASS** | **PASS** (Pe=0.50) |

经验：5s 不够 settle 4-VSG 摆动模式（period ~4-5s，需要 2-3 周期阻尼）。10s + tail 2s window 足够。

---

## 工件

- [`probes/kundur/gates/smoke_kundur_cvs_p3.py`](../../probes/kundur/gates/smoke_kundur_cvs_p3.py) — zero-action smoke 探针（matlab.engine + assignin + sim + read，~120 行）
- 复用 [`probes/kundur/gates/kundur_cvs_p2.slx`](../../probes/kundur/gates/kundur_cvs_p2.slx) 模型（P2/P3 共用）

---

## P1+P2+P3 全 PASS — 5 天主线改造允许启动

按 cvs_design.md §0 Gate 推进顺序：

```
Gate P1: 4-CVS 模型结构      ✅ PASS
Gate P2: reset/warmup/step/read ✅ PASS
Gate P3: zero-action smoke   ✅ PASS
                                 ↓
                           ⛔ 不允许直接进入 RL 训练
                                 ↓
                  [启动 5 天 Kundur CVS 主线改造]
```

**剩余非技术决策**（cvs_design.md §0 边界）：
- [ ] 5 工作日预算与决策方确认
- [ ] NE39 baseline 数值快照（约束文档 R1 NE39 污染检测 baseline）
- [ ] 替换手算 NR 为正式 Newton-Raphson 潮流（compute_kundur_powerflow.m 已存在，可适配 CVS 模型 — cvs_design.md §3）
- [ ] 写完整 4-VSG inter-area Kundur 拓扑（当前 P1/P2 拓扑是 BUS_left-tie-BUS_right 简化，未对应 paper Sec.IV-A 7-bus inter-area；属 5 天主线改造范围）

技术 unlock 已完成，进入主线改造前 P1/P2/P3 工件可作为模板复用。
