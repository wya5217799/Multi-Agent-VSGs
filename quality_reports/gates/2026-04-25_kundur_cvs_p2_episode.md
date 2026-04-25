# Gate P2 — Kundur CVS reset/warmup/step/read RL Episode Loop

**Date:** 2026-04-25
**Branch:** `feature/kundur-cvs-phasor-vsg`
**Predecessor:** [Gate P1 PASS](2026-04-25_kundur_cvs_p1_structure.md)
**Scope:** 4-VSG swing-eq 闭环 + 5 ep × FR off/on bit-exact + 每 agent M_i/D_i 改值生效

---

## Verdict

**PASS** — `OVERALL: PASS`，所有 4 子测试 PASS。

| Sub | Test | Result |
|---|---|---|
| **P2A** | 5 ep × FR=off bit-exact | ✅ max spread per-agent = 0.00e+00 |
| **P2B** | 5 ep × FR=on bit-exact (after first compile prime) | ✅ max spread per-agent = 0.00e+00 |
| **P2C** | per-agent M_i 12 → 24 (FR=on) | ✅ 4/4 changed, no nontunable warn |
| **P2D** | per-agent D_i 3 → 8 (FR=on) | ✅ 4/4 changed, no nontunable warn |

FR speedup: 1.4s (off) → 0.8s (on)，43% 提速（4-VSG 模型）。

---

## 实测数值

### P2A / P2B 5-ep 重复 omega_final（per agent，FR=off 与 FR=on 完全一致）

| Agent | omega_final 5 ep | spread |
|---|---|---|
| VSG1 | 0.99906089 ×5 | 0.00e+00 |
| VSG2 | 0.99906089 ×5 | 0.00e+00 |
| VSG3 | 1.00796318 ×5 | 0.00e+00 |
| VSG4 | 1.00796318 ×5 | 0.00e+00 |

VSG1/2 vs VSG3/4 分两组（差 ~0.009 pu = 0.45 Hz）— BUS_left 与 BUS_right 通过 L_tie 连接，两组 VSG 接 BUS 不同位置造成端电压相量初值不同。**这是 P1 拓扑的合理输出**：4 VSG 0.5s 内尚未通过 L_tie 完全同步。Gate P3 zero-action 5s 是否完全同步收敛是下一步关注点。

### P2C M_i 改值（FR=on，所有 4 agent 改值都生效）

| Agent | omega(M=12) | omega(M=24) | Δ | nontunable warn |
|---|---|---|---|---|
| VSG1 | 0.999061 | 0.999029 | -3.2e-5 | False |
| VSG2 | 0.999061 | 0.999029 | -3.2e-5 | False |
| VSG3 | 1.007963 | 1.007947 | -1.6e-5 | False |
| VSG4 | 1.007963 | 1.007947 | -1.6e-5 | False |

### P2D D_i 改值（FR=on）

| Agent | omega(D=3) | omega(D=8) | Δ | nontunable warn |
|---|---|---|---|---|
| VSG1 | 0.999061 | 0.999151 | +9.0e-5 | False |
| VSG2 | 0.999061 | 0.999151 | +9.0e-5 | False |
| VSG3 | 1.007963 | 1.007616 | -3.5e-4 | False |
| VSG4 | 1.007963 | 1.007616 | -3.5e-4 | False |

---

## 关键工程结论

- ✅ 4-VSG swing-eq 闭环编译 + sim 通过，无新 Mux / int64 / nontunable 错误
- ✅ Episode 边界（reset_workspace 重写所有 base ws + sim 0.5s + 读 omega）数值确定，跨 episode 无状态污染
- ✅ FastRestart=on 不破坏 reproducibility
- ✅ 所有 8 个 base ws 数值（M_1..4, D_1..4）改值都立即生效，**无 silent ignore**
- ⚠️ VSG1/2 vs VSG3/4 omega 不同组 — L_tie 跨 BUS 同步在 0.5s 内未完成，需 Gate P3 验证 5s 同步收敛

---

## 工件

- [`probes/kundur/gates/build_kundur_cvs_p2.m`](../../probes/kundur/gates/build_kundur_cvs_p2.m) — 4-VSG 模型构造脚本（~120 行）
- [`probes/kundur/gates/kundur_cvs_p2.slx`](../../probes/kundur/gates/kundur_cvs_p2.slx) — 模型（70+ 块）
- [`probes/kundur/gates/preflight_kundur_cvs_p2.py`](../../probes/kundur/gates/preflight_kundur_cvs_p2.py) — episode probe（matlab.engine + assignin + sim + read，~150 行）

---

## 下一步

进入 **Gate P3** — zero-action 5s smoke：在 P2 模型上跑 5s sim，验证：
- 4 VSG 全部 ω_tail_mean ∈ [0.999, 1.001]
- 4 VSG 间 max-min < 0.01 pu（同步）
- IntD 全程不触 ±90° 钳位
- Pe 与 Pm 一致（±5%）
