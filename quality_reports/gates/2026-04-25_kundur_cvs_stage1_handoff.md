# Kundur CVS Phasor — Stage 1 Handoff

**Date:** 2026-04-25
**Branch:** `feature/kundur-cvs-phasor-vsg`
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`（隔离，主 worktree 未触动）
**Stage 1 状态：完成，4 commits**

---

## 已 PASS

| Gate | Verdict | 报告 |
|---|---|---|
| Spike (G3.1/3.2/3.3 SMIB) | ✅ PASS | `quality_reports/audits/2026-04-25_cvs_phasor_feasibility.md` |
| Pre-Flight Q1 (多 driven CVS) | ✅ PASS | `quality_reports/audits/2026-04-25_cvs_phasor_preflight.md` |
| Pre-Flight Q2 (episode + FR + M0/D0) | ✅ PASS | 同上 |
| Pre-Flight Q3 (save/reopen) | ✅ PASS | 同上 |
| **Gate P1** 4-CVS 结构 | ✅ PASS | `quality_reports/gates/2026-04-25_kundur_cvs_p1_structure.md` |
| **Gate P2** reset/warmup/step/read | ✅ PASS (4-agent bit-exact + tunable) | `quality_reports/gates/2026-04-25_kundur_cvs_p2_episode.md` |
| **Gate P3** zero-action 10s smoke | ✅ PASS (ω band + sync + IntD + Pe) | `quality_reports/gates/2026-04-25_kundur_cvs_p3_smoke.md` |

---

## 当前边界（未越界）

| 边界 | 状态 |
|---|---|
| 主 worktree | ✅ 完全未动（governance-review-followups 改动保留） |
| NE39 文件 | ✅ 未触 |
| ANDES 路径 | ✅ 未触 |
| `slx_helpers/vsg_bridge/` 共享层 | ✅ 未触 |
| reward / observation / action 公式 | ✅ 未触 |
| agent / SAC / 训练超参 | ✅ 未触 |
| `scenarios/contract.py::KUNDUR` | ✅ 未触 |
| `engine/simulink_bridge.py` | ✅ 未触 |
| RL 训练入口 | ✅ 未触（按 P4+ 前置条件未满足，禁止进入） |

所有新增工件全部位于：
- `docs/design/cvs_design.md`
- `probes/kundur/spike/*`（spike + Pre-Flight 凭据）
- `probes/kundur/gates/*`（P1-P3 build 脚本 + .slx + Python 探针）
- `quality_reports/audits/2026-04-25_cvs_phasor_*.md`
- `quality_reports/gates/2026-04-25_kundur_cvs_p[1-3]_*.md`

---

## 4 Commits（按 design / spike-preflight evidence / P1-P3 gate artifacts / gate verdict reports 分层）

```
16208e1 docs(cvs-gates): P1/P2/P3 verdict reports — all PASS, RL training still gated
3daffb7 feat(cvs-gates): P1-P3 model + episode + smoke probes for 4-VSG CVS path
8a44bb9 chore(cvs-evidence): import spike + Pre-Flight artifacts as branch baseline
f90d1b4 docs(cvs-design): lock CVS Phasor + driven CVS engineering contract
```

合计 21 files changed, 2934 insertions, 0 deletions（基于 main 的 0d02bc0）。

---

## P4 前置条件（未满足）

进入 P4+（约束文档 §6 Gate 1: 30s + dist sweep / Gate 2: 训练 baseline）前必须先解决：

### 工程前置（Stage 2 范围，本分支可继续）

- [ ] **替换手算 NR 为正式 Newton-Raphson 潮流**：当前 P3 用 `θ_right = asin(2*Pm0*X_tie)` 手算，仅适用于 P1/P2 简化 2-bus 拓扑。完整 7-bus Kundur 需复用 `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m` 适配 CVS 模型 IC 输出。
- [ ] **完整 Kundur inter-area 拓扑**：当前 P1/P2 是 BUS_left—L_tie—BUS_right 简化（4 VSG 各通过 L_line 接其侧母线 + AC_INF 锚定 BUS_left）。实际 paper Sec.IV-A 是 7-bus inter-area + 2 area + load buses。Stage 2 build_kundur_cvs.m 需重建。
- [ ] **5s → 30s sim 数值稳定性验证**：P3 已证 10s window settle，但约束文档 Gate 1 要求 30s zero-action ω∈[0.999, 1.001] 全程。需要 30s × multiple seed 验证。
- [ ] **dist sweep 阶跃响应**：约束文档 Gate 2 要求 `{0.05, 0.1, 0.2, 0.3, 0.5} pu` 扰动下 max_freq_dev 与 dist 线性相关 (R² > 0.9)，0.5 pu 下 max_freq_dev ≤ 5 Hz。

### 组织前置（不在本分支技术工作范围）

- [ ] **5 工作日预算**与决策方确认（约束文档 §0/§5）
- [ ] **NE39 baseline reward / freq_dev 数值快照**（约束文档 R1 NE39 污染检测 baseline）— 跑 `python scenarios/new_england/train_simulink.py --mode simulink --episodes 3 --resume none` 取最近一次 100+ ep 的 reward 量级
- [ ] **决定是否优先 P1 ANDES paper profile / P2 ee_lib 工程修补**（cvs_design.md §0 替代路径仍在）

---

## Stage 1 关键工程发现（已固化到 cvs_design.md）

1. **D-CVS-9**：`Source_Type=DC + Initialize=off` 是 driven CVS 唯一合法配置（Source_Type=AC 触发 Mux real-only 约束）
2. **D-CVS-10**：fixed inf-bus 用 `powerlib/Electrical Sources/AC Voltage Source`（无 inport），不要用第二个 driven CVS（触发 Mux 类型一致性约束）
3. **D-CVS-11**：所有 base ws 数值显式 `double`（避免 powergui int64/double 不匹配）
4. **统一 RI2C 路径**：N driven CVS 共存的前提是所有输入信号类型一致；混 real Constant 与 complex RI2C 必失败
5. **4-VSG settle 时间**：inter-area mode period ~4-5s，5s sim 不够；至少 10s + tail 2s window 才能取到稳态
6. **per-agent IC 必须按 NR 解**：手算简化（统一 `asin(Pm0*X)`）会让 BUS_right 侧 VSG omega 飘 1‰，Pe 偏 +13~20%

---

## 下一步推荐

按指令"不要继续 P4，不要进 RL 训练"，本会话 Stage 1 完成。

后续启动 Stage 2 / P4 前推荐由人工确认上述前置清单是否满足；技术 unlock 状态保持，环境与凭据可直接复用。
