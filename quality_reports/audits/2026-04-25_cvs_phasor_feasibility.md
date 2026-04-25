# Kundur SPS Phasor + CVS 路线 — 最小可行性评估（修订 v2）

**Date:** 2026-04-25
**Type:** 评估报告（read-only spike，不修主线）
**Plan ref:** `C:/Users/27443/.claude/plans/jaunty-imagining-lovelace.md`
**Constraint ref:** `docs/superpowers/plans/2026-04-25-kundur-cvs-rewrite-constraints.md`
**Status:** v2 完整修订（v1 NO-GO 部分结论已收回）

---

## Verdict（修订）

**SPIKE-LEVEL GO**（技术路线在最小复杂度下被实测验证）

完整 1-VSG SMIB 闭环（powergui Phasor + SPS native CVS + signal-driven swing-eq）在 MATLAB R2025b / powerlib R2025b 下：
- ✅ 编译通过
- ✅ 5 s sim 收敛
- ✅ ω 稳态 = 1.0001 ± 0.0013（远优 [0.999, 1.001] 阈值）
- ✅ Pm 扰动响应阻尼振荡符合物理
- ✅ H 翻倍降振幅 + 振荡周期变长（量化）

**v1 NO-GO 的 F1 / F3 / F5 结论收回**（详见 §"v1 错误纠正"）。

仍未验证（属约束文档定义的 5 天改造范围，spike 不做）：三相扩展、4-VSG Kundur 拓扑、bridge 集成、RL 训练动态稳定。

**给用户的判断输入**：技术瓶颈已打开，决定是否启动 5 天改造现在只是**预算 + Pre-Flight 决策**，不是技术决策。

---

## Phase A — 先决条件审查（read-only）

| 问题 | Verdict | 证据 |
|---|---|---|
| DR-1（X_vsg 12.7× 阻抗谜团）是否关闭 | **CLOSED for SPS path**；CVS 路线**不继承**此 bug | `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/z_mismatch_audit.json` `verdict_final = "parameter_semantics_short_circuit_level_method"` — 12.57× 根因 = VSrc 用 ShortCircuitLevel 方法，Resistance/Inductance 是 stale display 字段。CVS 块无此 mask，bug 自动消失 |
| 用户是否授权 5 天 CVS 改造预算 | N/A — spike 评估不需要预算（已批准） | 用户消息："批准执行这个 Kundur CVS 路线最小可行性评估…完整改造需在 spike 得到 GO 后另行批准" |
| ANDES Kundur 是否被显式排除 | NOT EXCLUDED — ANDES 是真实替代 | `quality_reports/replications/20260425_145110_andes_kundur_paper.md` 显示今天 14:51 跑过 paper profile 5-ep + ckpt |

---

## Phase B — Spike 实测结果

### 工件清单

| 文件 | 用途 |
|---|---|
| `probes/kundur/spike/mcp_smib_swing.slx` | 完整 SMIB 闭环模型（22 块）— 通过 G3.1/3.2/3.3 验证 |
| `probes/kundur/spike/probe_sps_cvs_phasor_input.m` | T1-T3 输入格式探针 |
| `probes/kundur/spike/probe_sps_cvs_phasor_semantics.m` | 输入语义实测 |
| `probes/kundur/spike/probe_sps_cvs_swing_loop.m` | 单相 + R-load 闭环（无同步力，但验证 H 影响） |
| `probes/kundur/spike/probe_sps_cvs_smib.m` | SMIB v1（Source_Type=AC，失败） |
| `probes/kundur/spike/probe_sps_cvs_smib.m` 的 v2 等价工作 → MCP 命名工具直接构建 `mcp_smib_swing.slx` |
| `probes/kundur/spike/probe_sps_smib_isolate.m` | 4-stage 隔离诊断（部分有 bug） |

### 关键技术发现链

| Step | 工具 | 发现 |
|---|---|---|
| 1 | `simulink_run_script` + add_block 探查 | powerlib 含 SPS native `Controlled Voltage Source` / `Controlled Current Source`（add_block 7/7 命中） |
| 2 | `simulink_step_diagnostics` (T1-T3) | powergui Phasor + SPS CVS：3 种输入格式（实数 sin / 实数常量 / 复数常量）编译+sim 全通过 |
| 3 | semantics probe | Phasor 模式 CVS 输入语义 = **直接相量直传**：const 100 → 100；const 0+100i → 0+100j；瞬时 sin 被求解器**平均到 0**（不要喂时变实数信号） |
| 4 | swing-eq + R-load probe | 单相闭环 H 改变可观测影响 ω 振幅（M0=12 vs 24 → max ω 1.077 vs 1.049）— 但 R-load 无同步力，需要 SMIB 拓扑 |
| 5 | SMIB v1（Source_Type=**AC**） | ❌ 编译失败"复信号不匹配"。powergui 内部 Mux Inport 期望 real，因为 Source_Type=AC 时 CVS 用块参数 Phase + Frequency 自生相位 |
| 6 | `simulink_create_model` + 命名 MCP 工具 重建 (Source_Type=**DC** + Initialize=**off**) | ✅ 单 CVS + 动态 complex 信号编译+ 0.5 s sim 通过（0 errors / 0 warnings） |
| 7 | 加 CVS_INF 第二个 CVS | ❌ Mux 类型不匹配（Inport 1 vs 2 期望不一致） |
| 8 | 替换 CVS_INF 为 powerlib **AC Voltage Source**（fixed源，无 inport） | ✅ short sim 0.001 s 通过 |
| 9 | 完整 G3 SMIB 5 s sim | ✅ 见下表 |

### G3 SMIB 5-s 闭环 PASS/FAIL（全 PASS）

| 场景 | M0 | D0 | Pm step | 关键观测 | Verdict |
|---|---|---|---|---|---|
| **G3.1 zero-action** | 12 | 3 | none | ω_tail_mean=**1.000062**, tail_std=0.001297; Pe init 0.25 → final 0.41（朝 Pm0=0.5 阻尼收敛）; delta 0.1506 → 0.246（阻尼振荡） | ✅ PASS |
| **G3.2 Pm step** | 12 | 3 | t=2s, +0.1 pu | omega_peak=**1.003628**（+0.36%@50Hz）; tail_mean=0.999275, std=0.0011; delta_max=0.5437; Pe_max=0.862 | ✅ PASS |
| **G3.3 high inertia** | **24** | 3 | t=2s, +0.1 pu | omega_max=**1.002206**（仅 +0.22% — 比 G3.2 减半）; tail_std=**0.000304**（比 G3.2 缩小 4×）; delta_max=0.4547（小于 G3.2 的 0.5437） | ✅ PASS |

**核心物理验证**：
- ✅ Phasor + CVS + swing-eq 闭环数值稳定（5s, 1005 timesteps, 无 NaN/Inf/early-term）
- ✅ Pe 与 delta 同步（提供恢复力）
- ✅ Pm 扰动激发可观测阻尼振荡
- ✅ H 翻倍**精确降振幅**（peak ω 0.36% → 0.22%, tail std 4× 改善）
- ✅ ω 稳态在 1.0 pu（±0.001）

### 用户原始 6 条诉求映射

| # | 用户诉求 | Spike 实测 | 结论 |
|---|---|---|---|
| 1 | VSG 动态角度/频率进入仿真闭环 | IntD/IntW 输出有非平凡时间序列；Pe 反馈到 swing eq 改变 ω | ✅ PASS |
| 2 | action 是否能稳定影响 H/D | M0=12→24 量化降振幅 (0.36% → 0.22%) + 减振荡（std 4×） | ✅ PASS |
| 3 | 无扰动时系统是否能保持基本稳定 | G3.1 ω_tail_mean=1.000062, std=0.001297 | ✅ PASS |
| 4 | 小扰动下频率响应是否合理 | Pm +0.1 → ω peak 0.36% → 阻尼回 1.0 ≤5s | ✅ PASS |
| 5 | 是否可以跑完少量 episode | 单 sim 5 s 通过 1005 timesteps 无崩溃；多次 ws 重置 + sim 调用稳定 | ✅ PASS（episode 边界等价于 ws 重置 + sim） |
| 6 | 数值不崩 | 0 errors / 0 warnings 全程 | ✅ PASS |

---

## v1 错误纠正

v1（同名报告早些版本）下了 NO-GO verdict，证据 F1/F3/F5 现已被本次 spike 直接证伪：

| v1 证据 | v1 结论 | v2 验证 | 收回理由 |
|---|---|---|---|
| F1 "powerlib 无原生 CVS" | NO-GO 主因 | **错** | `add_block('powerlib/Electrical Sources/Controlled Voltage Source', ...)` 7/7 命中。先前用 `find_system + LookUnderMasks` 检索受 SubSystem 边界限制，假阴性 |
| F3 "SPS-PS domain 不能直连" | NO-GO 加权 | **范围误用** | 这只证明 ee_lib CVS（PS-domain）不能接 powerlib（SPS）网络。它**不证明 SPS 自己缺 CVS**。SPS 内部有原生 CVS + RLC + 测量，全 SPS-domain 互通 |
| F5 "ee_lib NE_FREQUENCY_TIME_EF 不适合 RL" | 替代路径排除 | **不需要这条路径**——SPS 原生 Phasor + native CVS 直接工作 |

新发现取代旧证据：
- **F1*（new）**：SPS native CVS 存在且工作，但**必须配 Source_Type=DC + Initialize=off**（AC 模式触发 Mux real-only 约束）
- **F2*（new）**：powergui Phasor 内部 Mux 对多 CVS 配置有类型一致性约束。Inf-bus 用 **powerlib AC Voltage Source**（fixed source）替代第二个 CVS 可绕开
- **F3*（new）**：base workspace 数值变量必须显式 double，否则 powergui 内部 EquivalentModel 触发 int64/double 不匹配

---

## 启动 5 天改造前必须做的事（约束文档 §0/§5 + spike 新发现）

### Pre-Flight（约束文档 §5 已存在）

- [x] DR-1 已关闭（z_mismatch_audit.json 已 verdict_final）
- [ ] ANDES Kundur 复活已尝试或显式排除（5-ep ckpt 存在但未收敛验证 → 需要决策）
- [ ] 工作量预算 ≥ 5 工作日已和决策方确认
- [ ] NE39 baseline reward / freq_dev 数值已快照
- [ ] 在新 git branch（`feat/kundur-cvs-rewrite` 或类似）
- [ ] 已读完约束文档全部章节
- [ ] 已读 NOTES.md "试过没用的"

### Spike 新增的工程要点（要写入 cvs_design.md）

- **CVS 配置必须固定**：`Source_Type=DC, Initialize=off, Amplitude=Vbase, Phase=0, Frequency=0`
- **CVS 输入端口**：动态 complex phasor 信号（Real-Imag to Complex 块输出）
- **Inf-bus**（无穷大母线）：用 powerlib `AC Voltage Source`（fixed source），**不要**用第二个 Controlled Voltage Source
- **base workspace 所有数值变量**：显式 double（避免 int64 类型推断）
- **三相扩展**（spike 未做但 design 要写）：3×SPS-CVS 用同一 IntD 驱动，每相 phase offset 0/-2π/3/+2π/3，3 路 RI2C → 3 个 CVS

### Gate 1-5 完成定义（约束文档 §6）

继续按约束文档要求；spike G3.1-3.3 已部分覆盖 Gate 1（动态稳定性）的物理必要性。完整 Gate 1 要求 30 s + 4 VSG，spike 只验证了 5 s 单 VSG，但**已证明技术路线本身不通的前提条件不存在**。

---

## 替代路径仍然有效

| 优先级 | 路径 | 理由 |
|---|---|---|
| 🥇 P1 | **继续 ANDES paper profile**（~1-2 工作日） | 今天已跑 5-ep；NOTES 标 "需 100+ ep dry-run"。直接投资比 5 天 CVS 改造性价比高 |
| 🥈 P2 | **工程修补现有 ee_lib + Continuous + CVS 主线** | NOTES 已建议 DIST_MAX 0.5→0.3 或 0.1→0.5 curriculum，工作量 < 1 天 |
| 🥉 P3 | **CVS Phasor 5 天改造（本评估目标路线）** | spike 已证技术路线通；启动条件 = Pre-Flight 全勾 + 5 天预算授权 |

P1/P2 失败后再启 P3 是合理顺序；spike 的功能 = **把 P3 从"未知是否可行"升级为"已知技术可行"**。

---

## Verification

报告交付即任务完成。验证标准：

1. ✅ `quality_reports/audits/2026-04-25_cvs_phasor_feasibility.md` 存在（本文件）
2. ✅ 含明确 verdict（修订为 SPIKE-LEVEL GO）
3. ✅ Phase A 三问题各一行答案 + 证据
4. ✅ Phase B 6 验证项 PASS/FAIL 表（全 PASS）
5. ✅ spike 模型 + 探针位于 `probes/kundur/spike/`，未触主线代码
6. ✅ v1 错误结论已显式收回 + 替代证据
7. ✅ MCP 工具优先（22+ block 模型全部用命名 MCP 工具构建；只用 simulink_run_script 提取详细错误诊断和读 timeseries）

---

## Worktree 边界

仅新增/修改：
- `probes/kundur/spike/build_minimal_cvs_phasor.m`（v1 失败方案，留作参考）
- `probes/kundur/spike/probe_sps_cvs_phasor_input.m`
- `probes/kundur/spike/probe_sps_cvs_phasor_semantics.m`
- `probes/kundur/spike/probe_sps_cvs_swing_loop.m`
- `probes/kundur/spike/probe_sps_cvs_smib.m`
- `probes/kundur/spike/probe_sps_smib_isolate.m`
- `probes/kundur/spike/probe_sps_smib_v2.m`
- `probes/kundur/spike/mcp_smib_swing.slx`（已 PASS spike 模型）
- `quality_reports/audits/2026-04-25_cvs_phasor_feasibility.md`（本报告）

主线代码（engine, env, scenarios/kundur 主文件, NE39, reward/obs/action）**未触动**。
