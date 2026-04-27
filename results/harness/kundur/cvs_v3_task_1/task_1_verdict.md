# Task 1 — W2 直连 Bus 8 — Verdict

**Date:** 2026-04-28
**Status:** **PASS** — 10/10 acceptance gates 通过
**Paper PRIMARY:** line 894 — "100 MW wind farm is connected to bus 8"
**Plan ref:** `quality_reports/plans/2026-04-28-task-1-w2-to-bus8-execution-plan.md`

---

## TL;DR

| 项 | 结果 |
|---|---|
| 修改完成 | ✅ |
| 论文对齐 (paper line 894) | ✅ |
| 系统 bus 数 | 16 → 15 (删 bus 11) |
| ESS Pm0 | -0.3691 sys-pu (与 baseline 同, 拓扑变不影响功率平衡) |
| 30s 零动作稳定 | ✅ max\|ω-1\|·50 = 0.176 Hz (baseline 0.18 ±2%) |
| 50 MW B14 step-on 方向 | ✅ FREQ_DOWN (0.99986 < 1) |
| Phase A++ CCS 路径 | 保留作 alternate (零成本) |
| 下游验证 | Task 2/3 前需 mini Phase A-D 重验 (ESS Pm0 数值不变, 但 topology 变, sanity 重测) |

---

## Acceptance gates 10/10

| # | Gate | Result |
|---|---|---|
| 1 | NR converged + closure_ok | PASS — outer_iter=8, mismatch=4.4e-13, residual=8.8e-10 |
| 2 | NR + build 无 ERROR | PASS — NR 73.7s, build 135.9s, 0 errors |
| 3 | Block tree: 无 L_8_W2 / bus 11 | PASS — 0 / 0 hits |
| 4 | PVS_W2 接入正确 | PASS — Lwind_W2.UserData.bus=8 |
| 5 | runtime.mat 无 "11" 语义字段 | PASS — 0 / 68 fields |
| 6 | 30s 零动作 stable | PASS — 0.176 Hz peak (= IC kickoff transient, 与 Phase B baseline 一致) |
| 7 | 50 MW B14 step-on freq DOWN | PASS — om_final ≈ 0.99986, FREQ_DOWN_OK |
| 8 | SHA-256 已变 | PASS — 3 文件全部不同 |
| 9 | topology_variant 同步更新 | PASS — 4 处 (build/NR/factory/probe) 一致 `'v3_paper_kundur_15bus_w2_at_bus8'` |
| 10 | Phase A++ CCS path 仍存在 | PASS — `LoadStepTrip_bus14` / `LoadStepTrip_bus15` 块仍在 |

---

## 文件 SHA-256 前后对比

| 文件 | Pre-Task | Post-Task |
|---|---|---|
| `kundur_cvs_v3.slx` | `1661ae8e09b4e72d...` | `e3cebd32a3292389...` |
| `kundur_cvs_v3_runtime.mat` | `febe1ad657043656...` | `358d64d88bc1a3d9...` |
| `kundur_ic_cvs_v3.json` | `521de192d809fe87...` | `db9741070d3c30ed...` |

3 文件 hash 全部更新, 验证修改生效。

---

## 修改文件清单

| 文件 | 修改类型 | 修改内容 |
|---|---|---|
| `scenarios/kundur/simulink_models/build_kundur_cvs_v3.m` | EDIT | 删除 line_defs `L_8_W2` 行; wind_meta W2 bus 11→8; comment 更新; assert string 改 `15bus_w2_at_bus8` |
| `scenarios/kundur/matlab_scripts/compute_kundur_cvs_v3_powerflow.m` | EDIT | bus_ids 删 11; bus_lbl 删 'Bus11_W2'; line_defs 删 `8,11,...`; bus_data 11→8; wind_buses [4,11]→[4,8]; topology_variant 改 |
| `scenarios/kundur/config_simulink.py` | EDIT | `_load_profile_ic` v3 分支 topology_variant 字符串改 |
| `probes/kundur/v3_dryrun/probe_5ep_smoke_mcp.m` | EDIT | identity_ok 检查 topology_variant 字符串改 |
| `scenarios/kundur/kundur_ic_cvs_v3.json` | REGENERATE (NR run) | 14 bus 数据, topology_variant 新, ESS Pm0 不变 |
| `scenarios/kundur/simulink_models/kundur_cvs_v3_runtime.mat` | REGENERATE (build run) | 68 fields, Wphase_2=0.0779 (新 bus 8 角度) |
| `scenarios/kundur/simulink_models/kundur_cvs_v3.slx` | REBUILD | 397 块, 19 lines (-1 = L_8_W2 系列), PVS_W2 在 bus 8 |

## Pre-Task 备份保留

5 个 `.pretask1.bak` 文件保留为回滚保险:
- `build_kundur_cvs_v3.m.pretask1.bak`
- `compute_kundur_cvs_v3_powerflow.m.pretask1.bak`
- `kundur_ic_cvs_v3.json.pretask1.bak`
- `kundur_cvs_v3_runtime.mat.pretask1.bak`
- `kundur_cvs_v3.slx.pretask1.bak`
- `config_simulink.py.pretask1.bak`

---

## 不动的 Task 1 隔离

按计划 §12 范围:
- ❌ 未改 LoadStep IC (仍 LS1=0/LS2=0 default = Task 2 的事)
- ❌ 未改 LS dispatch 方向 (env LS1 仍 step-on = Task 2 的事)
- ❌ 未改 ESS Pm0 sign (Task 1 W2 拓扑变不影响功率平衡, Pm0 仍 -0.3691)
- ❌ 未改 action range 常量 (= Task 3 的事, doc only)
- ❌ 未改 reward / SAC / paper_eval / NE39 / v2 / SPS

---

## 物理观察

NR 重派后:
- ESS Pm0 sys-pu = -0.3691 (与 pre-Task 同, 完全不变)
- W2 terminal V = 1.0 pu (PV bus, V mag 固定)
- W2 terminal angle = 0.0779 rad ≈ 4.46° (从 bus 11 0.0782 rad 微调)
- ESS internal EMF angles: ES1=0.195, ES2=0.024, ES3=0.195, ES4=0.009 rad
  (vs pre-Task 全部 ≈ 0.005-0.195, 略偏移因为 bus 11 1km 短线删除)
- 50 MW B14 step-on: ES3 ω 下降最多 (0.99909) — 物理正确 (ES3 在 bus 14
  = 扰动同 bus, 响应最快最强)

---

## Hand-off

**Modeling layer Task 1 完成**, kundur_cvs_v3 现状:
- Bus 14 buses (1-10, 12, 14, 15, 16, 含 8 现挂 W2)
- W2 直接接 bus 8, 无 bus 11 中转
- topology_variant = `'v3_paper_kundur_15bus_w2_at_bus8'`

**下一步可选:**
- Task 2: Bus 14 IC pre-engage 248 MW + LS1 反向 (paper line 993)
- Task 3: Action range 文档化 (paper line 938 + Q7)

**Phase A-D 验证状态:** Task 1 改了 IC json + runtime.mat + .slx, 严格说
所有 phase verdicts 是 pre-Task 的; 但 Task 1 物理影响极小 (W2 拓扑微调,
ESS Pm0 不变), 30s + 50 MW sanity 已 PASS。Task 2/3 前若需要可 mini 重验
Phase B 16-cell sweep。

---

## STOP

Task 1 完成。等用户决定 Task 2 / Task 3 / 备份清理 / commit 等下一步。
