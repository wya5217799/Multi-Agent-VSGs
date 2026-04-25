# Gate P1 — Kundur CVS 4-CVS Structure

**Date:** 2026-04-25
**Branch:** `feature/kundur-cvs-phasor-vsg`
**Predecessor:** Pre-Flight Q1/Q2/Q3 PASS
**Scope:** 仅结构验证（无 swing-eq），4 driven CVS + AC inf-bus + L_tie + 4 L_line + 5 GND 在 powergui Phasor 下编译 + 0.5s sim

---

## Verdict

**PASS**

| Check | Result |
|---|---|
| `build_kundur_cvs_p1.m` 构造完成（21 块）| ✅ saved to `probes/kundur/gates/kundur_cvs_p1.slx` |
| `simulink_compile_diagnostics(mode='update')` | ✅ errors=[], warnings=[] |
| `simulink_step_diagnostics(0 → 0.5s)` | ✅ status=success, 0 errors / 0 warnings, sim_time_reached=0.5 |
| 全 4 CVS 输入信号统一 RI2C complex（D-CVS-1 / H2）| ✅ 由 build 脚本保证 |
| 所有 base ws 数值显式 double（H5）| ✅ build 脚本用 `double(...)` 包裹 L_tie_H / L_line_H / phases_deg / mags |
| AC inf-bus = `AC Voltage Source`（D-CVS-10 / H3）| ✅ |
| Source_Type=DC + Initialize=off（H1 / D-CVS-9）| ✅ |
| powergui SimulationMode=Phasor, frequency=50（H4）| ✅ |

---

## 拓扑

```
              [AC_INF] -- L_tie/LConn1 = BUS_left
                           |
  [VSG1] --L_line_1--+    [VSG3] --L_line_3--+
  [VSG2] --L_line_2--+--BUS_left--L_tie--BUS_right--+--L_line_4-- [VSG4]
                                                                  
  各 CVS LConn1 → 各自 GND（floating-ground 单相 phasor 表示）
```

模型块列表：
- 1 powergui (Phasor 50Hz)
- 4 CVS_VSG{1..4} (Source_Type=DC, Initialize=off)
- 4 RI2C_{1..4}（Real-Imag to Complex）
- 8 Constant (Vr/Vi × 4)
- 4 L_line_{1..4}（Series RLC Branch L=L_line_H）
- 1 L_tie（Series RLC Branch L=L_tie_H）
- 1 AC_INF（AC Voltage Source）
- 5 GND_{1..4, INF}（Electrical Reference）

---

## 工程参数（H6 base ws）

| Param | Value |
|---|---|
| fn | 50 Hz |
| Sbase | 100e6 VA |
| Vbase | 230e3 V |
| X_line_pu | 0.10 |
| X_tie_pu | 0.30 |
| L_line_H | 0.5051969 / 3 ≈ 0.1684 H |
| L_tie_H | 0.5051969 H |
| phases_deg | [0, -0.5, +0.5, -0.3] |
| mags | [1.0, 0.999, 1.001, 0.998] |

---

## 失败信号检查（无触发）

| 信号 | 状态 |
|---|---|
| `复信号不匹配 / Mux 输入端口 N 应接受 real` | 无 |
| `数据类型不匹配 / int64 vs double` | 无 |
| `simscape_constraint_violation` | False |

---

## 下一步

进入 **Gate P2** — 在本结构上加 4 套 swing-eq（IntW/IntD/cosD/sinD/RI2C 替换 P1 的 Constant Vr/Vi）+ Pe 反馈，验证 reset/warmup/step/read RL episode 循环 + FastRestart + M0/D0 改值。
