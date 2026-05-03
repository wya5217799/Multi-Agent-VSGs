# 长周期开发后的高复用建设项与工具优化复盘

**日期**: 2026-05-04
**Branch**: `discrete-rebuild` @ `da252fc`
**审计范围**: git log (35 commits since Apr 5), `quality_reports/` (27 plans / 26 gates / 5 verdicts / 2 specs), `probes/` (probe_state 5059 LOC, spike 25 files), `docs/decisions/` (16 ADRs)
**约束**: 仅工程复盘，不推进训练路线

---

## 1. 高复用工具/流程/抽象（已经被反复证明值得用的）

| 项 | 证据 | 复用价值 |
|---|---|---|
| **probe_state 6-phase falsification 框架** (5059 LOC) | CLAUDE.md `PAPER-ANCHOR HARD RULE` 直接挂钩 G1-G6；本 session E2E 直接用它当 P2 验证骨架 | 任何 paper claim 都要走它，不可绕过；新 dispatch / 新 profile 加进去后 G1-G5 自动产出 |
| **`workspace_vars.py` schema (PROFILES_CVS_V3 + effective_in_profile)** | Z route 一次干掉 3 处 hardcoded 模型名 tuple；schema 自动 raise dangling-write | 物理上"name-valid 但 not effective"是这套 codebase 反复出现的现象（F2/F3/Option E ABORT/LoadStep bus15），schema 是唯一干净表达 |
| **`model_profile.py` + JSON profile 契约** | Z route 加 v3 Discrete 只动 1 个 JSON + 2 个 enum 值 | 加新 backend (v4 / EMT detail) 是配置任务不是 refactor |
| **Plan/Spec 模板结构** (§MUST/SHOULD/MAY + Clarity status + Pre-registered acceptance gates) | 5 月 11 个 plan / 2 个 spec 都是这个骨架；本 session P2 spec 8 个 BLOCKED 项被严格追踪解锁 | engineering_philosophy.md §6 anti-goalpost 落地的载体——MUST/gates 提前 freeze 防止后期改阈值 |
| **subagent dispatch 并行模式** | 本 session 8 个 agent 并行（cross-grep / E1 LoadStep / pytest 修 / D1+D2+D3 诊断 / γ + δ + writer + debugger + executor） | 主 context 不污染；agent 失败可独立追踪不破坏主线 |
| **ADR `YYYY-MM-DD-topic.md` 命名 + git history** | 16 个 ADR，时间序列清晰，无重命名/移动 | 跨 session 路由表，新 agent 能 `ls docs/decisions/` 直接看演进 |
| **`engineering_philosophy.md`** (157 LOC, 13 原则 + 8-item stop checklist) | §0.6.6 显式引用；本 session 拒绝放宽 GATE-PHYS 1e-9 阈值就是这条规则 | 防 AI hallucination 的成本最低工具，比 prompt 修复有效 |
| **`dispatch_metadata.py` (22 dispatch + floor/ceiling fail-soft)** | Phase 4 27 dispatch 误判被自动标记 `expected_floor_unknown` 而不是崩 | 新 profile 进来，metadata 缺数据时不 block，只 warn |

---

## 2. 当前最痛的开发拖慢/误判源

| # | 痛点 | 证据 | 影响 |
|---|---|---|---|
| **A** | **Simulink 编译冻结的 workspace var 没有显式注册表** | F2 (Series RLC R) → LoadStep_t (Three-Phase Breaker SwitchTimes) → SimscapeIC compile state 反复重新发现 | 每个新 feature 撞墙 1-3 hr (LoadStep 这次 ~5 hr 含 debug) |
| **B** | **MATLAB engine 单进程瓶颈+并发未常态化** | Phase 4 serial 47.9 min，4 worker 并行 16.4 min；E2E v1 全失败因为 worker 跳了 Phase 1 | 每次 oracle 迭代 30+ min wall，迭代次数被压缩 |
| **C** | **跨 worktree shadowing** (`Multi-Agent  VSGs/` 双空格 vs `Multi-Agent-VSGs-discrete/`) | CLAUDE.md §0.6.1/0.6.2 警告；本 session β agent 报 stop-hook 反复回滚（其实没发生但触发了警觉） | 静默用错版本是潜在 BAD_AGENT 头号源 |
| **D** | **Plan 累积无归档**（5 周 27 plan，许多 supersedes 但还在 plans/） | `2026-04-26` 一天 5 个 plan；`2026-04-28-task-1/2/3` 各一份 | 新 agent 读 plans/ 不知该读哪份；§0.5 read order 必须显式列 |
| **E** | **G4_position_hz 阈值现有字段但 _verdict 没用** | 本 session 加了字段（probe_config.py:0.6.0），D1 标了"not yet wired" | G4 在 v3 Discrete 持续 REJECT spurious，每次 probe 跑都得手动忽略 |
| **F** | **dispatch_metadata 的 floor/ceiling 不 profile-aware** | `pm_step_hybrid_sg_es` floor=0.30 Hz 是历史 mag=1.55 sweep 平均，probe 用 mag=0.5 实测 0.18-0.21（已 below_floor warning 多次） | 每次跑 Phase 4 都假阳性 warning，疲劳 |
| **G** | **v3 Phasor / v3 Discrete dual-track 共存的认知负担** | Z route 之后 PROFILES_CVS_V3 集合显式挂钩；但 `kundur_cvs_v3.slx` + `kundur_cvs_v3_discrete.slx` 都活，编译有差，build 路径要选 | 跨 worktree shadowing (痛点 C) 的子症状 |
| **H** | **`kundur_cvs` (v2) 死代码** | `compute_kundur_cvs_powerflow_v1_legacy.m` + `kundur_ic_cvs_v1_legacy.json` + 2 处 model_name == 'kundur_cvs' 分支 | 维护成本，mock 测试还引用它 |

---

## 3. 建设项排序（P0/P1/P2）

### P0-1 LoadStep bus15 + Hybrid RNG fix（plan 已写）

- **痛点**: 痛点 A 直接体现；P2 GATE-PHYS 12/15 PASS + 3 dispatches FAIL 被它阻塞
- **复用价值**: 修完后形成 "compile-frozen var → 物理替代机制" 的范式（bus14 InitialState=closed + amp 写法已验证），后续 CCS 恢复直接套
- **建设内容**: 执行 `quality_reports/plans/2026-05-04_loadstep_bus15_hybrid_dispatch_fix.md` Module L1+L2+H1（bus15 InitialState=open→closed + 移 LOAD_STEP_T 无效写 + hybrid target_g_override）
- **不建设后果**: P2 永远停在 GATE-PHYS PARTIAL；后续 Phase 1.4 paper-anchor oracle 也撞同样墙
- **验收**: 重跑 E2E (serial+parallel) → 15/15 dispatches GATE-PHYS bit-exact 1e-9
- **估时**: 3-4 hr

### P0-2 编译冻结变量注册表（compile-frozen var registry）

- **痛点**: 痛点 A 系统化解决
- **复用价值**: F2/F3/F9/LoadStep 痛过 4 次了，下一次 CCS 恢复（Phase 1.5）会再撞；Phase 1.6 env 切换会再撞
- **建设内容**: 在 `scenarios/kundur/NOTES.md` 或新 `docs/knowledge/simulink_compile_frozen_vars.md` 写一份: 块类型 × 参数名 × 是否 runtime-tunable × 证据 commit hash 的表；workspace_vars.py.effective_in_profile 的 inactive_reason 也指向这表
- **不建设后果**: 每个新 feature 再损 2-5 hr 重新发现
- **验收**: 表能解释当前所有 `effective_in_profile=frozenset()` 条目的 mechanism；新加 spec 时可直接查
- **估时**: 1.5 hr (聚合已有知识)

### P1-1 G4_position_hz 接入 _verdict (D1 follow-up)

- **痛点**: E
- **复用价值**: 每次 Phase 4 跑都受益；G4 REJECT 假阳性消失
- **建设内容**: `probes/kundur/probe_state/_verdict.py::compute_gates` 在 G4_position 计算 responder signature 时改用 `THRESHOLDS.g4_position_hz` (0.10 Hz) 替代 `g1_respond_hz` (1mHz)；加单测
- **不建设后果**: G4 在 v3 Discrete 永久 REJECT，每次 probe 报告都得手动批注"已知误报"
- **验收**: 用本 session E2E parallel snapshot 重跑 verdict → G4 PASS（≥2 distinct responder signatures across 12 dispatches）
- **估时**: 30 min

### P1-2 dispatch_metadata floor profile-aware 重校准 (D2 follow-up)

- **痛点**: F
- **复用价值**: 减少 Phase 4 假阳性 warning；每次 LoadStep oracle 不被噪声淹没
- **建设内容**: `dispatch_metadata.py` 加 `expected_min_df_hz_per_profile: dict[profile_name, float]` OR 改成 `expected_min_df_hz_per_mw: float`（线性校准）；至少 `pm_step_hybrid_sg_es` 重校准
- **不建设后果**: Phase 4 报告每次都有假阳性 warning，疲劳
- **验收**: pm_step_hybrid_sg_es 在 v3 Discrete + mag=0.5 不再 below_floor
- **估时**: 1 hr

### P1-3 Phase 1.5 CCS 恢复 (plan 已写, 5 hr)

- **痛点**: 当前 v3 Discrete CCS 块 `if false` 包裹，trip-direction LoadStep + Bus 7/9 load-center CCS 全部不可用
- **复用价值**: 解锁 paper Fig.3 LS1 trip 方向；让 LOAD_STEP_TRIP_AMP / CCS_LOAD_AMP schema 能 promote effective
- **建设内容**: 执行 `quality_reports/plans/2026-05-03_phase1_5_ccs_restoration.md` 6 acceptance gates
- **不建设后果**: paper-faithful 一半 oracle 不存在；训练 dispatch 多样性受限
- **验收**: G1.5-A~F 全过；workspace_vars.py LOAD_STEP_TRIP_AMP / CCS_LOAD_AMP 在 v3 Discrete 标 effective
- **估时**: 5 hr (含 1 surprise budget)

### P2-1 Plan 归档脚本 + plans/_archive/

- **痛点**: D
- **复用价值**: 跨 session AI 上下文清理
- **建设内容**: 一个 `scripts/archive_superseded_plans.py`：扫描 plans/*.md 找 `Supersedes:` 或 `Status: SUPERSEDED` header → mv 到 `_archive/`；保留最近 30 天活跃
- **不建设后果**: plans/ 继续累积；新 agent 读 §0.5 read order 还是要靠手工列
- **验收**: 跑一次后 plans/ 只剩 < 10 个活跃 plan
- **估时**: 1 hr

### P2-2 v2 (kundur_cvs) 路径归档

- **痛点**: H
- **复用价值**: 减 if-branch；新 agent 不被分散
- **建设内容**: 把 `compute_kundur_cvs_powerflow_v1_legacy.m`、`kundur_ic_cvs_v1_legacy.json`、`config_simulink.py` v2 分支移到 `_archive/legacy_v2/`；移除 `model_profiles/kundur_cvs.json` 或标 deprecated
- **不建设后果**: 维护负担微小但会越积越多
- **验收**: `grep -rn "kundur_cvs[^_v]" --include="*.py"` 在 prod 路径返回 0；测试可保留 fixture
- **估时**: 1 hr

### P2-3 Cross-worktree shadow guard

- **痛点**: C
- **复用价值**: 防 BAD_AGENT 静默用错版本
- **建设内容**: 一个 `engine/path_guard.py::assert_active_worktree(expected="discrete-rebuild")`，build script + probe entrypoint 调；`addpath` 显式 `prepend` 而非默认
- **不建设后果**: 偶发但严重的"用错版本"风险；本 session 已有 1 次警觉
- **验收**: build script 在错的 worktree 跑直接 raise；probe entrypoint 同
- **估时**: 1.5 hr

## §3.5 重排建议 (post-retro critique 2026-05-04)

retro 写完后，P0-1 执行过程中识别的若干漏项 / 顺序错。本节是增量补丁，不否定 §3 主结构。

### §3.5.1 P0-2 与 P0-1 关系修正

P0-2 (compile-frozen 注册表) 应 demote 为 **P0-1 期间附带沉淀**，不是独立排期。
理由：bus15 fix 时必产出"Three-Phase Breaker SwitchTimes / InitialState compile-frozen → InitialState=closed + amp 写法替代"范式，这就是注册表第一条。注册表 = P0-1 的副产物文档，零增量时间。

### §3.5.2 漏排 P0-3: gate eval 自动化

`probes/kundur/probe_state/_diff.py` 出 stdout 不出结构化 verdict。重跑 E2E、Phase 1.4 oracle、P0-1 验收都得手写 Python 比 snapshot。

**建设**: `probes/kundur/probe_state/_gate_eval.py`
- 输入: 2 个 snapshot 路径 + 阈值 (默认 GATE-PHYS=1e-9)
- 输出: JSON `{GATE_PHYS: PASS/FAIL, max_dispatch_delta: float, per_dispatch_delta: dict, gate_g15: PASS/FAIL, verdict_drift: list}`
- CLI: `python -m probes.kundur.probe_state --gate-eval prev curr`

**复用次数**: P0-1 验收 1×、Phase 1.4 oracle 1×、Phase 1.5 CCS gate 6×、未来每次 paper-anchor probe 1×。≥ 8 次复用 / 1 hr 建设。

**估时**: 1 hr (P0-1 验收时机建)

### §3.5.3 痛点 C 升级 P0

retro §2 痛点 C 写"偶发但严重"。本 session build + IC test 都 trigger 了 `Multi-Agent  VSGs/slx_helpers/` (主 worktree 双空格) shadow warning。当前 mitigation 全靠 `addpath('-begin')` 手动写。两个 worktree 同名 helper 行为分歧 = 静默 silent corruption，root cause 极难追。

**升级理由**: 触发频率 ≥ 1 / session，潜在影响是 model build 静默用错版本，retro 估的"偶发"低估实际。

**最小行动 (P0-shadow, 5 min, P0-1 期间附带)**: build script 顶部加：
```matlab
expected_root = 'C:/Users/27443/Desktop/Multi-Agent-VSGs-discrete';
if ~startsWith(strrep(pwd, '\', '/'), expected_root)
    error('build_kundur_cvs_v3_discrete: wrong worktree pwd=%s', pwd);
end
```
完整 path_guard.py 留在 P2 cleanup。

### §3.5.4 §2 痛点 A 应展开 root cause 列表

retro 写"反复重新发现"过于模糊。具体 instances 应在 §2 列出（也是 P0-2 registry 种子）：

| Instance | Block | 参数 | 状态 |
|---|---|---|---|
| F2 | Series RLC Branch | `Resistance` | compile-frozen, 已知 |
| F9 | Continuous Integrator + FixedStepDiscrete | (兼容性) | 已知 |
| LoadStep T | Three-Phase Breaker | `SwitchTimes` | compile-frozen, 已知 |
| LoadStep S | Three-Phase Breaker | `InitialState` | compile-frozen, **本 P0-1 触发** |
| CCS | (待定) | (待定) | pending Phase 1.5 |

写进 §2 替代痛点 A 的"反复重新发现"模糊表达。

### §3.5.5 §4 归档列表过保守

漏列：
- `quality_reports/plans/2026-04-26_*.md` (5 份) — 被 §1.0 registry 取代
- `quality_reports/plans/2026-04-28-task-{1,2,3}.md` (3 份) — 同
- `quality_reports/plans/phase_b_findings_cvs_discrete_unlock.md` 等 F-series 笔记 — 被 §1.0 完全取代

合并到 P2-1 plan 归档脚本（处理时纳入扫描）。

### §3.5.6 §5 估时模型校准

retro 给 P0-1 估 3-4 hr。实际 (in-progress 2026-05-04 cycle):
- code edits + pytest: ~30 min
- rebuild + IC re-verify: ~15 min
- E2E serial: 进行中 (~48 min 期望)
- E2E parallel + gate eval + ADR + commit: ~30 min 期望
- **预计 actual ~2 hr**, vs 估 3-4 hr → **-33% 到 -50%**

原因: subagent 并行（cross-grep + executor + writer 同时跑）压缩 wall。retro 估时用单线程模型。

**机制**: 每个 cycle 在 retro §6 加一行 actual datapoint，N=5 后回归调估时模型。本 cycle 起开始收。

### §3.5.7 P2-1/2/3 合并建议

retro §3 P2-1 (plan 归档) / P2-2 (v2 归档) / P2-3 (shadow guard) 各 1-1.5 hr 分 3 次。主线无收益的清理活动一次性做完更高效：合并为 **P2-cleanup (3 hr)** 单 plan：
- (a) plan/gate 归档脚本 + 跑一次（含 §3.5.5 漏列）
- (b) v2 (`kundur_cvs`) 路径归档
- (c) shadow guard 完整版 `engine/path_guard.py` (P0-shadow 已部分提前到 P0-1 期间)

避免 3 次 context-switch 成本；一个 plan 收 3 件事。

---

## 4. 应停止投入或归档

| 项 | 路径 | 状态 | 处置 |
|---|---|---|---|
| Phasor v3 dryrun probes | `probes/kundur/v3_dryrun/` (27 files) | DEFERRED in registry | 移 `_archive/`；保留 README 解释为何不删 |
| Phase 3 g3prep 系列 verdict | `quality_reports/gates/2026-04-26_kundur_cvs_g3prep_*` (16 files) | 被 Phase 4 oracle 替代 | 移 `gates/_archive/2026-04_g3prep/` |
| 4-26 task plans | `quality_reports/plans/2026-04-26_*` (5 files) + `2026-04-28-task-1/2/3*.md` | 被 phase1_progress §1.0 registry 取代 | 移 `plans/_archive/` |
| `optimization_log/` | MEMORY.md 标 "2026-04-16 停用，待确认后删除" | 确认中 | 确认后删 |
| v2 (`kundur_cvs`) profile + IC JSON | scenarios/kundur/, model_profiles/, matlab_scripts/ | 被 v3 Phasor + v3 Discrete 取代 | P2-2 |
| FastRestart `_apply_fast_restart` 方法 | `engine/simulink_bridge.py` | call site 已 revert，dead code | **保留** for Option C refactor (LoadStep+Hybrid fix 同步做才能正确测) |
| `optimization_log` (停 2026-04-16) | 不在仓 | 已死 | 确认是否真删（MEMORY.md 行 5） |

---

## 5. 如果只能先做一件事

**P0-1: LoadStep bus15 + Hybrid RNG fix (~3-4 hr)**

理由：
1. **唯一能让 P2 GATE-PHYS 从 PARTIAL 走到 ALL_PASS 的事**——P2 的全部基础设施 (4 module + Y4 + 145 unit tests + 2.92× speedup measured) 已经在仓里，差的是物理层 3 个 dispatch 不真触发。修完 P2 落档完整 ALL_PASS。
2. **触发 P0-2 (compile-frozen 注册表) 的天然时机**——修 bus15 时必然要写出"breaker SwitchTimes 编译冻结 → InitialState=closed + amp 写法替代"的范式，这就是注册表第一条。
3. **是 Phase 1.5 CCS 恢复的前置认知**——CCS 块同样会撞编译冻结问题，bus15 fix 提供模板。
4. **不修就一直绕**：每次想跑 LoadStep oracle 都要手动忽略 3 个 dispatch，G4 REJECT 永远在，paper-faithful trip 方向永远不存在。

修完后立刻获得：
- P2 ALL_GATES_PASS（5/5）
- Phase 1.4 LoadStep oracle 16 min wall（vs alpha 47 min）
- Phase 1.5 CCS plan 复用 bus15 修法范式

不修则 P2 整套基础设施处于 "技术上 90% 就位但实际不能闭环验证" 的卡死状态。

---

*end — 审计基于 2026-05-04 上午 commit `da252fc` 状态。*
