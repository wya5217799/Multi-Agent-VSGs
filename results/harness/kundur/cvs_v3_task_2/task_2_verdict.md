# Task 2 — Bus 14 IC 预接入 248 MW + LS1 反向 — Verdict

**Date:** 2026-04-28
**Status:** **PASS** — 12/12 acceptance gates 通过
**Paper PRIMARY:** line 993-994 — "sudden load **reduction** of 248 MW at
bus 14" / "sudden load **increase** of 188 MW at bus 15"
**Plan ref:** `quality_reports/plans/2026-04-28-task-2-bus14-preengage-execution-plan.md`

---

## TL;DR

| 项 | 结果 |
|---|---|
| Modeling layer 修改完成 | ✅ |
| Bus 14 IC 预接入 248 MW | ✅ |
| LS1 dispatch 反向 (env 写 0 → R disengage) | ✅ |
| LS2 dispatch 不变 (paper-aligned) | ✅ |
| ESS Pm0 sign flip | ✅ -0.3691 → +0.2502 sys-pu (absorb→generate) |
| LS1 触发方向 freq UP (paper LS1) | ✅ mean(ω_finals)=1.0000183 |
| LS2 触发方向 freq DOWN (paper LS2) | ✅ mean(ω_finals)=0.9999328 |
| 30s 零动作 stable (新 IC) | ✅ max\|ω-1\|·50=0.173 Hz |
| Phase A++ CCS path 保留 | ✅ alternate test mode |

---

## Acceptance gates 12/12

| # | Gate | Result |
|---|---|---|
| 1 | NR converged + closure_ok | PASS — outer_iter=9, inner mismatch=6.9e-13, aggregate residual=1.07e-10 |
| 2 | P_load_total ≈ -29.82 sys-pu | PASS — -29.8200 exact (= -27.34 + -2.48) |
| 3 | ESS Pm0 sign flipped (all 4 > 0) | PASS — vsg_pm0_pu=[+0.2502]·4 |
| 4 | G1 residual < 1e-6 | PASS — 1.07e-10 |
| 5 | Build OK + lines=19 / loadsteps=2 不变 | PASS — 块结构未变 |
| 6 | runtime.mat LoadStep_amp_bus14 默认=248e6 | PASS — 2.48e+08 |
| 7 | topology_variant 4 处一致 | PASS — `'v3_paper_kundur_15bus_w2_at_bus8_ls1_preengaged'` (build/NR/factory/probe) |
| 8 | SHA-256 三文件全变 | PASS |
| 9 | 30s 零动作 stable | PASS — max=0.173 Hz, no NaN/Inf |
| 10 | LS1 trigger freq UP | PASS — mean=1.0000183 |
| 11 | LS2 trigger freq DOWN | PASS — mean=0.9999328 |
| 12 | env import OK (Python AST) | PASS |

---

## 文件 SHA-256 前后对比

| 文件 | Pre-Task 2 (= Task 1 完成态) | Post-Task 2 |
|---|---|---|
| `kundur_cvs_v3.slx` | `e3cebd32a3292389…` | `44e45cd3ee4fcf06…` |
| `kundur_cvs_v3_runtime.mat` | `358d64d88bc1a3d9…` | `a77862736f40f6ce…` |
| `kundur_ic_cvs_v3.json` | `db9741070d3c30ed…` | `2b9101f926af7d33…` |

3 文件 hash 全部更新, 验证 modeling-layer 修改生效。

---

## 修改文件清单

| 文件 | 修改类型 | 修改内容 |
|---|---|---|
| `scenarios/kundur/matlab_scripts/compute_kundur_cvs_v3_powerflow.m` | EDIT | 加 `P_LS1_LOAD = 2.48`; bus 14 schedule 加 -P_LS1_LOAD offset; outer iter 同步; ess_load_offset 向量; closure 公式 P_load + P_ess_total 修正; V_emf 计算 undo 248 MW load offset; topology_variant 字符串 |
| `scenarios/kundur/simulink_models/build_kundur_cvs_v3.m` | EDIT | LoadStep_amp_bus14 默认 0 → 248e6 (assignin loop + runtime_consts loop); topology_variant assert |
| `scenarios/kundur/config_simulink.py` | EDIT | `_load_profile_ic` v3 分支 topology_variant check |
| `probes/kundur/v3_dryrun/probe_5ep_smoke_mcp.m` | EDIT | identity_ok topology_variant string |
| `env/simulink/kundur_simulink_env.py` | EDIT | `_apply_disturbance_backend` LS1 dispatch 改 `'trip'` action (写 0); LS2 改 `'engage'` action; magnitude 语义 LS1 ignored / LS2 normal; cc_inject (Phase A++) 保留 alternate |
| `scenarios/kundur/kundur_ic_cvs_v3.json` | REGENERATE (NR run) | vsg_pm0_pu 全 +0.2502 (sign flip); P_load=-29.82; topology_variant 新值 |
| `scenarios/kundur/simulink_models/kundur_cvs_v3_runtime.mat` | REGENERATE (build run) | LoadStep_amp_bus14=2.48e8; Pm_<i>=+0.250225 (×4) |
| `scenarios/kundur/simulink_models/kundur_cvs_v3.slx` | REBUILD | 块结构不变, IC 数值更新 |

## Pre-Task 2 备份保留

5 个 `.pretask2.bak` 文件作回滚保险:
- `compute_kundur_cvs_v3_powerflow.m.pretask2.bak`
- `build_kundur_cvs_v3.m.pretask2.bak`
- `config_simulink.py.pretask2.bak`
- `probe_5ep_smoke_mcp.m.pretask2.bak`
- `kundur_simulink_env.py.pretask2.bak`

---

## 关键 PRIMARY 物理观察

### NR 收敛指标
```
outer_converged=1   outer_iter=9    inner_iter_total=45
inner_max_mismatch_pu=6.906e-13     (tol=1e-10)   ✓
G1_residual_pu=1.072e-10            (G1 hit 700 MW exactly)
closure_ok=1   aggregate_residual=1.068e-10  (tol=1e-3)
```

### NR 物理量
```
P_gen_paper_sys_pu=21.1900   (G1+G2+G3 = 700+700+719 MW)
P_wind_paper=8.00            (W1+W2 = 700+100 MW, 不变)
P_load_total_sys_pu=-29.82   (= -27.34 Bus 7+9 + -2.48 Bus 14 LS1)
P_loss_sys_pu=0.3709         (1.24% of |load|)
P_ess_total_sys_pu=+1.0009   (= +0.2502 × 4, sign flipped from -1.4791 absorb)
P_ES_each_sys_pu=+0.2502     (= 25.02 MW per ESS, generate)
                              vsg-pu: +0.1251 (= +0.2502 × 100/200)
ESS_per_bus_dispatch_dev=4.05e-13  (Task 2 offset 校验通过)
```

### Sign flip
- pre-Task 2: ESS 群体 absorb 系统多余功率 (-0.369 sys-pu/ESS, -36.9 MW)
- post-Task 2: ESS 群体 generate 弥补 248 MW LS1 load 缺口 (+0.250 sys-pu/ESS, +25 MW)
- 物理意义: LS1 load 增 248 MW, 总 system 缺口 +63 MW + 损耗 ≈ +100 MW, 4 ESS 平摊 +25 MW each

### 30s 零动作 + IC 稳定性
- max\|ω-1\|·50 = 0.173 Hz (= IC kickoff transient, 与 Task 1 0.176 Hz 同 order)
- 无 NaN / Inf
- ESS Pm0 sign flip 后 swing eq 仍然稳定 (Phase D D1+D2 早 PRIMARY 验证 swing eq 形式对 Pm 符号无敏感性)

### LS1 / LS2 方向
- LS1 trigger (env 写 LoadStep_amp_bus14=0): mean(ω)=1.0000183 → freq UP ✓
- LS2 trigger (env 写 LoadStep_amp_bus15=188e6): mean(ω)=0.9999328 → freq DOWN ✓
- **paper line 993-994 完全 paper-faithful**

---

## env API 语义变化

新 dispatch 语义:

| Dispatch type | Action | Magnitude usage |
|---|---|---|
| `loadstep_paper_bus14` | LS1 trip (R disengage, 248 MW drops out) | **IGNORED** (always full 248 MW) |
| `loadstep_paper_bus15` | LS2 engage (R engage, 0→amp_w MW) | scales LS2 amplitude (e.g., 188e6 default) |
| `loadstep_paper_random_bus` | 50/50 LS1 trip / LS2 engage | LS1 ignores; LS2 uses |
| `loadstep_paper_trip_bus14/15` (Phase A++ alternate) | CCS injection (negative-load) | scales injection |
| `loadstep_paper_trip_random_bus` (Phase A++ alternate) | random CCS injection | scales |

**RL training 注意:** SAC actor 不再控制 LS1 magnitude。LS1 是 switch
action (开/关). LS2 仍是连续 magnitude action。Random_bus 50/50 选择保留
paper 实验语义。

---

## 不动的 Task 2 隔离

- ❌ 未改 action range 常量 (DM/DD) — Task 3 doc-only
- ❌ 未改 reward / PHI / SAC / replay buffer / checkpoint / paper_eval
- ❌ 未改 NE39 / v2 / SPS
- ❌ 未改 Task 1 的 W2 接入 (W2 仍在 bus 8 直接接)
- ❌ 未改 Phase A++ CCS 块结构 (保留 alternate)

---

## Risk register 状态

| ID | Risk | Status |
|---|---|---|
| R2-1 | NR 不收敛 | NOT TRIGGERED — 9 iter 收敛 |
| R2-2 | bus 14 outer iter 同步漏改 | NOT TRIGGERED — ess_load_offset 向量正确 |
| R2-3 | env LS1 magnitude 语义模糊 | DOC-MITIGATED — verdict 显式声明 |
| R2-4 | random_bus 失衡 | NOT TRIGGERED — LS1/LS2 仍对称 (freq UP/DOWN) |
| R2-5 | CCS path 退役不当 | NOT TRIGGERED — 保留作 alternate |
| R2-6 | Phase D D-axis verdict 失效 | TRIGGERED EXPECTED — Phase D 须重测 (Pm0 翻号), 不在 Task 2 内 |
| R2-7 | Pre-Task 2 baseline 偏差 | NOT TRIGGERED — SHA matches Task 1 verdict |
| R2-8 | engine 缓存 | NOT TRIGGERED |
| R2-9 | Phasor 数值 248 MW (213 Ω) 不稳 | NOT TRIGGERED — Phase B 已扫到 248 MW PASS |
| R2-10 | Pm0 sign flip 失败 (NR 解错) | NOT TRIGGERED — sign flipped 为 +0.2502 |

NR 第一次 closure_ok=0 (aggregate=2.48), 是 P_load + P_ess 双计 LS1 load
导致, 已在 closure 公式修正 (P_ess_total 改为 4·P_ES_each = 群 gen 而非
bus net), rerun PASS。**算 mid-flight 自我纠错, 不算 risk trigger。**

---

## Phase A-D 验证状态

Task 2 改了 IC json + runtime.mat + .slx, 三处 SHA 均变。post-Task 2 状
态下 Phase A++/B/C/D verdicts **形式上失效** (是 pre-Task 2 IC 跑的)。

但 Task 2 物理意义上的影响:
- ESS Pm0 sign flip: 改 swing eq 平衡点, 但 Phase D D1+D2 已 PRIMARY 验
  证 swing eq 对 Pm 符号无敏感性 (M1 fix 处理)
- Bus 14 IC 加 248 MW load: 改稳态 Y-bus 解, 但块拓扑未变
- 30s + LS1 + LS2 mini sanity 全 PASS, 物理稳定

**建议但不强制** post-Task 2 重测:
- Phase B 16-cell sweep (paper magnitudes scaling, 5 min sim)
- Phase D 5-cell D 扫 (canonical SG only, 1 min sim)

留给用户决定是否重测 (Task 2 scope 外)。

---

## Hand-off

**Modeling layer Task 1 + Task 2 完成**:
- W2 接入 bus 8 ✓ (paper line 894)
- Bus 14 IC 预接入 248 MW ✓ (paper line 993)
- LS1 dispatch reverse (R disengage = freq UP) ✓
- LS2 dispatch unchanged (= freq DOWN paper-aligned)
- topology_variant: `'v3_paper_kundur_15bus_w2_at_bus8_ls1_preengaged'`

**下一步可选:**
- Task 3: Action range 文档化 (Q7 ambiguity, 0 模型修改)
- Phase A-D 重测 (post-Task 2 baseline establish)
- RL training 启动

---

## STOP

Task 2 完成。等用户决定下一步 (Task 3 / Phase 重测 / commit / RL training)。
