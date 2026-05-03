# 路线审计结论

**审计时间**: 2026-05-04 EOD (P0-1c attempt 1 E2E running, ~15 min remaining)
**审计范围**: 本 session 全部工作 (9 commits + 1 uncommitted attempt + 2 reverted attempts)
**审计立场**: 严格证据派，不默认支持，不粉饰

---

## 1. 一句话判断

**当前路线 = CONDITIONAL GO**

条件：bus14 LoadStep dispatch 在 probe E2E (proper warmup) 必须给出 `max|Δf|_per_source ≥ 0.3 Hz` (Phase 1.5 plan §1.2 G1.5-B 阈值，self-pre-registered)。
若 < 0.1 Hz → **降级 HOLD**。
若 0.1-0.3 Hz → 模糊带，再加 1 个 falsification 实验。

---

## 2. 最近工作质量评价

### 强项 (实有的)

| 项 | 证据 |
|---|---|
| Atomic commit 风格 | 9 commits 全单一 cycle，diff 清楚，message 详尽 |
| 失败果断 revert | Phase 1.5 attempt 1 compile FAIL → revert 而非 force-fix |
| Engineering philosophy 部分尊重 | P0-1 GATE-PHYS PASS 写了 "LoadStep silent no-op caveat" 在 ADR |
| 文档化深度 | Phase 1.5 §0.6/§0.7 留下 attempt 失败的根因，不是 silent skip |
| Subagent 并行 | 4 agents 同消息发出 (Wave 1)，wall 压缩 ~7 min |
| 资产复用 | P0-1c 真用上 F4 patterns + SMIB oracle + dynamic_source helper 思路 |

### 弱项 (必须直面的)

#### W1: P0-1 "GATE-PHYS PARTIAL → FULL_PASS" 是 goalpost 移动

**证据链**:
- P2 spec §5 GATE-PHYS 定义: `|max_abs_f_dev_hz_global_serial[d] - max_abs_f_dev_hz_global_parallel[d]| ≤ 1e-9` 跨模 bit-exact
- P0-1 commit `c400cbd` 标 GATE-PHYS PASS (15/15 bit-exact 0.00e+00)
- 但 3/15 dispatch (loadstep_paper_bus14/15/random_bus) 实际值 0.108096 = silent no-op residual chain，**不是 LoadStep 触发产物**
- caveat 写在 ADR 注释里，但 commit headline 仍是 "P2 GATE-PHYS PASS"

**重新分类**：
- spec 的 GATE-PHYS 在 paper-anchor 语境下=="LoadStep 物理正确性 跨模 bit-exact"
- 实际 PASS 的是 "silent no-op 跨模 bit-exact" = "并行化基础设施正确" 

**违 engineering_philosophy.md §6 (DON'T MOVE THE GOALPOSTS)** 的标准——把 GATE-PHYS 含义从 "LoadStep 物理" 重新定义为 "并行化"，即使有 caveat。

**Severity**: HIGH — 这种 label 漂移如果重复，会侵蚀 GATE 信任度。

#### W2: F4 误读延续 ≥ 2 个 cycle

**证据**:
- F4 (`test_ccs_dynamic_disc.m`) 实际验证: `Source_Type='DC' + 外部 Step (real) → CCS.Inport1` 在 Discrete + FastRestart 工作
- Phase 1.5 attempt 1 假设: `Constant → RI2C → CCS` (Phasor pattern) 在 Discrete 也工作 — **F4 不 cover 这个**
- §0.5 写 "Option E CCS substitution is the only viable path" 是 over-interpret F4
- 直到 attempt 1 compile FAIL，才 §0.6 修正为 "F4 只验 DC+Step，不验 RI2C"

**根因**: 多个 session 的 plan/agent 都在 parrot "F4 验证 CCS works"，没人去读 F4 实际 code。这是 **collective hallucination** — 跨 session 复制 claim 不验证。

**Severity**: MEDIUM — 现在 §0.6 修了，但 pattern (claim 不读源验证) 可能还在。

#### W3: P0-1c sanity 数据不能 declare "mechanism works"

**FACT**:
- amp=0 baseline `late|df|` = 0.04-0.06 Hz (IC residual)
- amp=248e6 `late|df|` = 0.018-0.037 Hz (**比 baseline 还小**)
- amp=2480e6 (10×) `late|df|` = 0.05-0.34 Hz (ES3=0.34 Hz 明显超 baseline)

**只能下的结论**:
- ✅ amp ↑ 时 Δf ↑ (10× amp 能区分信号 vs 噪声)
- ❌ paper-anchor amp (1×=248e6) 不能区分信号 vs IC residual
- ❌ "scaling 线性" 是 1 个 data point (10×) 推断，不是验证

**当前 sanity 不支持 P0-1c attempt 1 verdict**。Mechanism 在 PoC scale 验证，**不在 paper magnitude 验证**。

**Severity**: HIGH — 直接关系到下一步是否 GO。

#### W4: bus14 注入与 bus voltage phase 角度未对齐

**证据**:
- agent 实施: 3 sin generators with `Phase ∈ {0, -2π/3, +2π/3}` (绝对时间参考)
- bus14 voltage phase 相对 G1 slack: 从 IC `delta_ts_3` (ES3 ≈ 14.4°) 推断 bus14 voltage 角度类似量级
- 注入 sin 在绝对时间参考 → 与 bus14 voltage 有 ~10-30° 失配
- 实际注入 P_active = 248 MW × cos(失配) → 87% active + 50% reactive 浪费
- SMIB oracle 没这问题（SMIB 单一参考帧，bus voltage phase=0）

**未做的**: PLL 锁相 / voltage-phase 对齐 / 用 bus voltage 测量值乘除回 sin

**Severity**: MEDIUM — 解释了为什么 248 MW 在 Kundur 比 SMIB 弱很多。但即使修了，35× 系统惯量也压缩响应。

#### W5: bus15 schema-code 不一致

**证据**:
- `workspace_vars.py::LOAD_STEP_AMP.effective_in_profile = frozenset()` (deprecated)
- `disturbance_protocols.py::LoadStepRBranch.apply` bus15 路径仍写 `LOAD_STEP_AMP[15]`，标 `require_effective=False`
- bus15 LoadStep dispatch 物理结果: silent no-op (P0-1 已知)
- E2E 日志 (just observed): 仍 fire `Variable 'LoadStep_amp_bus15' ... nontunable parameter ... will not be used`

**问题**: schema 说 deprecated，code 还写。`require_effective=False` 是 escape hatch。这与 self-philosophy ("schema 是单一真值") 自相矛盾。

**Severity**: MEDIUM — 不破坏当前 E2E (silent fail)，但是 long-term debt。

#### W6: 8/9 commits 是 infra，1/9 是 physics

**Commit 分类**:
- Infra: P0-3 gate-eval / P1-1 G4 / P1-2 metadata / P2-archive / P2-pathguard / P2-archive-cleanup / 9d8d8ee finding doc = 7
- Physics-claim: c400cbd P0-1 (GATE-PHYS "PASS" but actually silent no-op) = 1
- Physics-actual: uncommitted P0-1c attempt 1 (PoC 验证, 1 bus, magnitude TBD) = 1

**比例 8:1 倾向 infra**。Engineering_philosophy.md §4 "YAGNI" + §8 "Decision-Driven Tests" 自打脸: 这些 infra 都是 retro 列出的，不是 Phase 1 paper-anchor 决策的直接 enabler。

**严重的: paper-anchor LoadStep disturbance 真验证** 仍 = 0 (E2E 跑完前)。

#### W7: Estimate 校准只在 infra 工作 winning

**Estimate vs actual**:
- P0-3: 1 hr est → 10 min actual (-83%)
- P1-1: 30 min → 10 min (-67%)
- P1-2: 1 hr → 15 min (-75%)
- P2-archive: 1 hr → 20 min (-67%)
- P2-pathguard: 1.5 hr → 10 min (-89%)
- 平均 -76%

但:
- Phase 1.5 attempt 1: 5 hr est → ~30 min agent + 100% revert = **-100% useful output**
- P0-1c attempt 1: ~30 min agent + ~30 min MATLAB = nominal time (no improvement vs estimate)

**Pattern**: agent 在 schema/test/CLI 工作上估时高估 (因为简单)。Physics 工作没收益。**不能用 infra estimate trend 推论 physics estimate 准**。

#### W8: Test count 87 通胀 vs 0 physics 验证

**87 个新测试**:
- test_p1_g4_threshold (10): mock snapshot input + verdict logic
- test_p1_metadata_profile_aware (18): floor scaling math
- test_archive_script (16): file move logic
- test_path_guard (15): cwd assert logic
- test_p0_1c_bus14_ccs_loadstep (5): adapter writes correct var
- test_gate_eval (23): JSON schema + delta math
- (others: schema flips, sign convention)

**全部 verify schema/API/逻辑**。**0 个 verify physics correctness** (因为 pytest 不能跑 MATLAB)。

测试覆盖给 confidence，但 confidence ≠ correctness。Engineering_philosophy.md §3 "Smoke PASS ≠ Validity" 在测试层面适用。

---

## 3. 证据表

| Claim | 类别 | 证据强度 |
|---|---|---|
| 9 commits 全 push 到 origin | FACT | 强 (git log) |
| MATLAB rebuild + compile clean (P0-1c attempt 1) | FACT | 强 (compile_diagnostics 0 errors/warnings) |
| IC settle 6/7 vs 5/7 pre-fix | FACT | 强 (test_v3_discrete_ic_settle 输出) |
| 87 new tests pass | FACT | 强 (pytest 输出) |
| ES4 settled 是 CCS 替换的因果 | **CLAIM (推断)** | 弱 (没 falsification 实验，可能巧合) |
| ES3 std 0.00177 → 0.00114 (-36%) 是 CCS 替换的因果 | **CLAIM (推断)** | 弱 (同上) |
| amp=2480e6 ES3=0.34 Hz "scaling linear" | **CLAIM (n=1)** | 中 (单数据点) |
| amp=248e6 mechanism 工作 | **未证明假设** | **0 (信号 ≤ 噪声)** |
| paper-anchor 248 MW 在 Kundur Discrete 可达 ≥ 0.3 Hz Δf | **未证明假设** | **0 (E2E 未验)** |
| bus14 PoC scaling 到 bus15/bus7/bus9 都 work | **未证明假设** | **0 (未尝试)** |
| Phase 1.5 G1.5-A..F 全 PASS 后 → Phase 1.6/1.7 ready | **未证明假设** | **0 (前置未验)** |
| GATE-PHYS PASS 在 P2 ADR 真等于 "LoadStep works" | **FALSE** | 强 (ADR caveat 自承认) |
| F4 验证 RI2C-Phasor pattern 在 Discrete 工作 | **FALSE** | 强 (F4 用 DC+Step，不用 RI2C) |
| Schema-code 在 bus15 LOAD_STEP_AMP 一致 | **FALSE** | 中 (frozenset() 但仍写) |

---

## 4. 当前能不能进入下一阶段

**不能。**

**下一阶段 = Phase 1.6 (env config + paper_eval) 或 Phase 1.7 (RL trial)** (per `2026-05-03_phase1_progress_and_next_steps.md` §5)

**Blocking conditions**:
1. paper-anchor LoadStep 物理验证 (bus14 dispatch ≥ 0.3 Hz @ 248 MW) 未达
2. bus15 LoadStep 仍是 silent no-op (P0-1c 没动它)
3. CCS Load bus7/bus9 仍 `if false` (未启用)
4. Phase 1.5 §1.2 G1.5-A..F 全部 6 gates，预计 0/6 通过 (G1.5-A 也未严格验证: IC settle 6/7 但有 5/6→6/7 移动，没物理 rationale 写下)

**严格判断**: Phase 1.5 当前完成度估 **15-25%** (mechanism PoC 1 bus / 4)。距离 "下一阶段 ready" 远。

---

## 5. Top 5 风险

### R1: paper-anchor magnitude 不可达 (BLOCKING)

**机制**: 248 MW 在 Kundur (3500 MVA equiv inertia) 物理上限可能就是 0.1-0.3 Hz Δf，与 SMIB (200 MVA) 的 4.9 Hz 不可比。
**触发条件**: E2E bus14 dispatch max|Δf| < 0.1 Hz
**影响**: 整个 Phase 1.5 路线物理上不可达 paper anchor。需要：
  - (a) 调整 acceptance gate (有 physics rationale 的话不算 goalpost move)
  - (b) 加 PLL phase alignment
  - (c) 重 design 注入幅度公式 (目前 amp/Vbase_LL_RMS 可能差 sqrt(3) 因子)
  - (d) 接受 LoadStep 在 v3 Discrete 不可达 paper anchor，专注 PM_STEP 路径

### R2: F4 类 misread 复发 (HIGH)

**模式**: 跨 session agent 复制 claim 不验证源
**触发**: 任何 "X 已验证" 的 claim 没有 commit hash + 具体测试 file:line 引用
**影响**: 像 attempt 1 RI2C 那样 build/test pass + MATLAB compile fail
**Mitigation 缺**: 没有"claim → 证据回链"机制

### R3: Schema/code 不一致继续累积 (MEDIUM)

**当前**: bus15 LOAD_STEP_AMP frozenset() 但仍写
**触发**: 下一 cycle 加 require_effective=True 严格化或者忘 bug
**影响**: 隐藏 silent failure

### R4: Goal drift (MEDIUM)

**当前**: 8:1 infra:physics 比例
**触发**: 下一 cycle 又选 infra cycle (e.g., 文档清理, 监控增强) 而不是 physics
**影响**: paper-anchor 越来越远

### R5: "改进metric 当成 路线正确" 复发 (MEDIUM)

**当前**: P0-1c IC 5/7 → 6/7 没 H1-H4 falsification 解释，但被报告成 "improvement"
**触发**: 下一 cycle 类似 metric movement 不做 root cause
**影响**: hallucinate 因果

---

## 6. 目标漂移判断

**有 STRUCTURAL 漂移**（不是 lateral pivots，而是 default 路径）。

### 证据

| 维度 | 原目标 (Phase 1 plan, 2026-05-03) | 当前实际 (2026-05-04 EOD) |
|---|---|---|
| 主线 | "v3 Discrete probe Phase 4 with paper-faithful disturbances" | LoadStep dispatch 1/3 buses mechanism PoC，magnitude TBD |
| Phase 1.5 (CCS restoration) | 5 hr 单 cycle | 已 attempt 1 fail + attempt 1c bus14 only PoC，预计 ≥2 hr 余量 |
| 8:1 commit ratio | 期望: 主要工作是 build script + IC validation | 实际: 主要工作是 gate-eval / threshold / archive / pathguard |
| Test counts | infra 测试是工具，不是主线 | 87 新测试 0 物理验证 |

### 性质

不是 "放弃 paper-anchor"。是 **"低阻力 cycle 偏好"**: infra cycles 估时小、agent 友好、风险低 → 容易完成。physics cycles 需要 MATLAB + 真实物理验证 → 高风险，难。

人 (我) + agent 在 path of least resistance 下选 infra. 这是 **结构性**，不是 lateral.

### 缓解

- 强制 N:1 比例规则: 每 1 个 infra cycle 必须紧跟 1 个 physics cycle (即使 physics fail)
- Pre-register: cycle 开始前定 "physics or infra" 标签 + 不得换
- 拒绝 retro 列出的 P1/P2 infra 优化直到 Phase 1.5 G1.5-B/C 至少 1 个真 PASS

---

## 7. 证据链断点

### 已闭合的链

| 链节 | 状态 |
|---|---|
| F4 → CCS-DC-Step in Discrete works | ✓ (test_ccs_dynamic_disc 5A → 50V) |
| Phase 1.5 attempt 1 RI2C → Phasor pattern fail in Discrete | ✓ (compile error explicit) |
| P0-1c sin-Constant-Product → compile clean + 6/7 IC | ✓ (rebuild + test_v3_discrete_ic_settle) |
| amp=2480e6 → ES3=0.34 Hz | ✓ (sanity 实测) |

### 断点 (未闭合，必须解)

| 断点 | 必须的实验 |
|---|---|
| 248 MW @ Kundur post-warmup → ≥ 0.1 Hz Δf | probe E2E (running) |
| sin phase=0 vs bus14 voltage phase 对齐 | sim with PLL or voltage measurement |
| bus14 PoC scaling 到 bus15 | 对 bus15 重做 P0-1c |
| bus15 + bus7/bus9 启用 → Phase 1.5 G1.5-A..F 全 PASS | 4-bus 完整集成 + E2E |
| 6/7 IC settle "improvement" 因果 | falsification: 关 CCS amp=0 + 旧 RLC 加回 1W default → ES4 是否仍 settle? (1 hr 实验) |

### 关键断点 (BLOCKING)

**`paper-anchor magnitude 是否物理可达`** = E2E (~15 min remaining) 拍板。

---

## 8. 最小下一步

### 必做 (E2E 完成前)

1. **不再启动新 cycle**。等 E2E。
2. **预注册 magnitude 阈值**：
   - bus14 dispatch max|Δf|_per_source ≥ 0.3 Hz on ≥ 1 of {ES1..ES4}: GO
   - 0.1-0.3 Hz: HOLD + 加 PLL alignment 实验
   - < 0.1 Hz: HOLD + 重 design (Vbase 量纲 / phase alignment / 另选机制)
3. **不能用 ALL_PASS bit-exact 当 success**：序列化 v 并行 bit-exact 是 P2 已验证 infra，**P0-1c 需要的是 magnitude，不是 cross-mode determinism**

### 必不做

- ❌ 不能 commit P0-1c attempt 1 验收 = "PASS" 基于现有 sanity 数据 (信号 ≤ 噪声)
- ❌ 不能开始 bus15 / bus7 / bus9 工作直到 bus14 magnitude 验证
- ❌ 不能宣布 "Phase 1.5 progress 50%" — 4 buses 中 1 个 PoC，magnitude 未验，实际 < 25%
- ❌ 不能再发 infra cycle 直到 Phase 1.5 G1.5-B 或 G1.5-C 真 PASS

### 应做 (E2E 数据后)

**Branch A** (E2E ≥ 0.3 Hz):
- Commit P0-1c attempt 1 + scale to bus15 in attempt 2
- Estimate 2 hr (复用 bus14 pattern)
- 然后 attempt 3: bus7/bus9 CCS Load (相同 pattern)
- Phase 1.5 全集成 + E2E 验所有 G1.5-A..F

**Branch B** (E2E 0.1-0.3 Hz):
- HOLD attempt 2
- 加 PLL phase alignment 实验 (1-2 hr)
- 加 Vbase 量纲核 (line vs phase, RMS vs peak)
- 重测 → 决定 Branch A 或 C

**Branch C** (E2E < 0.1 Hz):
- 严重 HOLD
- 接受 LoadStep CCS injection 在 v3 Discrete 物理上不可达 paper anchor magnitude
- 重审 Phase 1.5 acceptance gates (with rationale, not goalpost-move)
- 或考虑替代机制 (Variable Resistor / Three-Phase Fault block / actual-load engagement via dynamic load)

---

## 9. 最终建议

### 当前状态 (一句话)

P0-1c bus14 PoC **mechanism 验证是 weak proof** (compile + IC + 10× amp linear)，但 **paper magnitude 验证缺失**。8:1 infra:physics 比例显示结构性 goal drift。

### CONDITIONAL GO 的条件 (must-meet, immutable)

1. probe E2E bus14 dispatch `max|Δf|_per_source` ≥ 0.3 Hz at 248 MW
2. 若不达，下一步必是 **诊断**，不是 **scale**
3. 不再积累 infra cycles 直到 1 个 physics gate (G1.5-B 或 G1.5-C) 真 PASS

### 反思 (engineering_philosophy.md 自查)

| 原则 | 本 session 自我打分 | 证据 |
|---|---|---|
| §1 Falsification > Validation | 60/100 | 失败 attempt 1 revert 是 falsification 行为，但 sanity test 用 amp=0/1×/10× 是 validation framing，没设 falsification 假设 |
| §3 Documentation ≠ Repair | 70/100 | §0.6/§0.7 留下深度分析，但 P0-1 commit headline "FULL_PASS" 是 documentation-only repair |
| §6 DON'T MOVE GOALPOSTS | 40/100 | P0-1 GATE-PHYS PARTIAL → FULL_PASS 是 goalpost 重新定义 |
| §7 FACT vs CLAIM 强制分类 | 60/100 | 大量 commit message + plan §0.7 用 CLAIM 写法 (e.g., "improvement" / "verified") 没 FACT 标记 |
| §8 Decision-Driven Tests | 80/100 | 大多数 test 有具体决策 (P0-3 取代 inline / P1-1 解 G4 假阳性) |
| §13 Honest Ignorance > Faked Knowledge | 50/100 | 知道 amp=248 信号 ≤ 噪声但仍 "mechanism works" 框定，是 faked positivity |

**总分: ~60/100**。中等偏低。最大问题是 §6 + §7 + §13 三条 (诚实问题)。

### 路线总评

route 不是错的，但 cycles 在向 infra 倾斜。**physics 任务剩余预算需要 hard-cap**: 若 E2E 数据 < 0.1 Hz, Phase 1.5 概念可能不可达 paper-anchor magnitude (机制 vs 物理上限)。

**最危险的事**: 如果 E2E 给 0.1-0.3 Hz 模糊带，倾向是 "继续 scaling" (低阻力路径)，但正确的是 "诊断+falsify" (高阻力)。**预先承诺**走高阻力。

---

*end — 审计基于 2026-05-04 02:30 状态。E2E `bazv5zwoy` 仍在运行。验收 + 路线决策必须等 E2E + gate-eval 数据。*
