# Kundur CVS Phasor 路线 — Pre-Flight Verdict

**Date:** 2026-04-25
**Type:** Pre-Flight gate（不是 spike 扩展）
**Predecessor:** [`2026-04-25_cvs_phasor_feasibility.md`](2026-04-25_cvs_phasor_feasibility.md) → SPIKE-LEVEL GO
**Scope:** 只回答 3 问，不重做 G3.x，不做 4-VSG 完整 Kundur，不写 bridge.py

---

## Verdict

**PASS — 允许进入 5 天 Kundur CVS 改造**

Q1 / Q2 / Q3 全 PASS。RL episode 语义、FastRestart 缓存、模型持久化均无阻塞性问题。剩余工作属于约束文档定义的 5 天改造范围。

---

## Q1 — 多 driven CVS 在 Phasor 下能否共存

| 测试 | 模型 | 编译 | 0.5s sim | Verdict |
|---|---|---|---|---|
| 2 driven CVS（电压源 + L + 第二电压源 + GND）| `mcp_q1_2cvs` | ✅ | ✅ 0 errors / 0 warnings | PASS |
| 4 driven CVS（星型公共母线，phase/mag 微差） | `mcp_q1_4cvs` | ✅ | ✅ 0 errors / 0 warnings | PASS |

**关键工程发现（写入未来 cvs_design.md）：**
- ✅ N 个 driven CVS 可共存（已验证 N=2, N=4），**前提**：所有 CVS 输入信号类型必须一致（统一走 Real-Imag-to-Complex → CVS）
- ❌ 反例：spike v1 阶段 1 driven CVS（complex 输入）+ 1 fixed-bus CVS（real 输入）触发 powergui 内部 Mux 类型一致性约束 — 不要混用
- 替代方案（已验证）：fixed inf-bus 用 powerlib **AC Voltage Source**（无 inport）；或者所有 CVS 都用 RI2C complex 路径

**4-VSG Kundur 的拓扑含义**：所有 4 个 VSG 端口都是 driven CVS（统一类型），不存在 fixed-source 端口冲突。Q1 PASS 直接覆盖 4-VSG 拓扑的 Mux 兼容性。

---

## Q2 — RL episode 循环 + FastRestart + M0/D0 修改

**Probe**: `probes/kundur/spike/preflight_q2_episode.py`（matlab.engine.connect_matlab 连共享 MCP MATLAB session，最小 50 行直接 assignin + sim + read）

| 子测试 | 内容 | 结果 |
|---|---|---|
| **Q2A** 5 ep × FR=off bit-exact 复现 | 重置 ws → sim 0.5s → 读 omega_final ×5 | spread=**0.00e+00**（5 ep 全 0.99976624）✅ |
| **Q2B** 5 ep × FR=on bit-exact 复现 | 同上但 FastRestart=on | spread=**0.00e+00** ✅ |
| **Q2C** M0 12→24 with FR=on 是否生效 | 改 ws M0 → sim FR=on → 与 FR=off 对比 | omega 12→0.99977 vs 24→1.00164，**changed=True**, **FR_consistent=True** (FR-on 与 FR-off 数值精确相等)，lastwarn=空（无 nontunable warning）✅ |
| **Q2D** D0 3→8 with FR=on 是否生效 | 改 ws D0 → sim FR=on | omega 3→0.99977 vs 8→0.99979, **changed=True**, lastwarn=空 ✅ |
| FR 性能 | 5 ep elapsed | FR=off 0.8s, FR=on 0.6s（25% 提速；首次 compile 已 prime）|

**关键发现：**
- ✅ episode 边界（重置 ws + sim）数值确定，无 cross-episode state pollution
- ✅ FastRestart=on 不破坏 reproducibility
- ✅ **M0/D0 是 FR-tunable**（通过 base ws Constant block 路径），改值立即生效，**无 silent ignore**（约束文档 R2 风险在此配置下不触发）
- ✅ FR speedup 25%（预热后）— 5 天改造 RL 训练阶段 FR=on 安全

**约束文档 R2 状态**：本配置下不构成阻塞。原 R2 风险针对 TripLoad/breaker（Three-Phase Dynamic Load `ActivePower` 等 FR-nontunable 字段）。CVS 路线改用 base ws Constant 块 + driven CVS，M/D 路径完全规避。

---

## Q3 — save → close → reopen 后 reset+step 一致性

| 阶段 | omega_final |
|---|---|
| save 前 sim | 0.9997662368 |
| save → close_system → load_system → sim | 0.9997662368 |
| **abs_diff** | **0.000e+00** ✅ |

**Q3 PASS** — bit-exact 一致。模型 baked state 可移植。

---

## 工件清单

新增于 `probes/kundur/spike/`（叶子，不进主线）：
- `preflight_q2_episode.py` — Q2 最小 Python 探针（matlab.engine + assignin + sim + read，~150 行）
- `mcp_smib_swing.slx` — Q3 验证用同一 SMIB 模型（spike 阶段已存在）

主线 / NE39 / bridge.py / reward / obs / action / IC：**未触动**。

---

## 进入 5 天改造的解锁条件（已全部满足）

| 条件 | 状态 | 证据 |
|---|---|---|
| Q1 多 CVS 共存 | ✅ PASS | mcp_q1_2cvs / mcp_q1_4cvs 编译+sim |
| Q2 episode 循环可重复 + FR | ✅ PASS | preflight_q2_episode.py 全 PASS |
| Q3 模型持久化一致 | ✅ PASS | save→close→reopen abs_diff=0 |
| DR-1 阻抗谜团 | ✅ CLOSED | z_mismatch_audit.json verdict_final |
| Spike 主验证（G3.1/3.2/3.3）| ✅ PASS | 2026-04-25_cvs_phasor_feasibility.md |

---

## 启动 5 天改造前剩余事项（属约束文档 §5 Pre-Flight）

- [ ] 工作量预算 ≥ 5 工作日已和决策方确认
- [ ] NE39 baseline reward / freq_dev 数值已快照（用于约束文档 R1 NE39 污染检测）
- [ ] 在新 git branch（`feat/kundur-cvs-rewrite` 或类似）
- [ ] cvs_design.md 已写明（Source_Type=DC + Initialize=off + RI2C complex 路径 + 所有 driven CVS 一致性 + base ws double + AC Voltage Source 作 fixed inf-bus）

技术风险已 unlock，剩余只是组织决策。

---

## 失败信号 trigger（如未来重测出现，应停手）

如果在 5 天改造过程中遇到以下任一，应回到本 Pre-Flight 重新验证：

- 多 CVS 编译触发 "复信号不匹配 / Mux 类型不一致" — 检查所有 CVS 输入信号类型是否统一
- M0/D0 改值不生效（FR=on）— 检查 lastwarn 是否含 `nontunable` / `不可调` / `will not be used` / `新值不会使用`
- save → reopen 后行为漂移 — 检查 base ws 数值是否被重置为 int64

---

## 推荐立即下一步（不在本 Pre-Flight 范围）

P3（5 天改造）现已 unlocked，但 P1 / P2 仍优先：

1. 🥇 **P1 ANDES paper profile 100+ ep dry-run**（1-2 天）— 投资最低
2. 🥈 **P2 ee_lib + Continuous + CVS 工程修补**（DIST_MAX curriculum，< 1 天）— 修当前主线
3. 🥉 **P3 启动 5 天 CVS Phasor Kundur 改造** — Pre-Flight unlock 后的可选路径
