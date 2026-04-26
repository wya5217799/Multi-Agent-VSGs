# simulink-tools MCP — 优化计划 (Optimization Plan)

> **Status:** PLAN v4 ONLY — 无代码 / 无工具 / 无模型修改。等待用户 GO 后再分阶段执行。
> **Date:** 2026-04-27 (4 轮审查收敛后 consolidated — 决策日志见 §10)
> **Predecessor:** [`quality_reports/reviews/2026-04-27_simulink_tools_mcp_review.md`](../reviews/2026-04-27_simulink_tools_mcp_review.md) — Phase 1→3 使用评估，识别 5 个限制 + 3 个新工具诉求 + Top-5 ROI 排序。
> **Companion docs:**
> - [`quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_phase5_roadmap.md`](2026-04-26_kundur_cvs_v3_phase4_phase5_roadmap.md) — v3 路线图（被本计划支撑）
> - `engine/mcp_simulink_tools.py` — 现行 MCP 工具入口装饰器（项目层，允许项目术语）
> - `engine/modeling_tasks.py` + `engine/smoke_tasks.py` — harness 真实业务逻辑（项目层）
> - `engine/matlab_session.py` — engine 单例（项目层）
> - `slx_helpers/*.m` — MATLAB 端 helper（**严格项目无关** — 实测 30 个 .m 文件 0 处提 kundur/ne39/cvs_v3/VSG/paper）
> - `~/.claude/skills/simulink-toolbox/{SKILL,map,INVARIANTS,OPTIMIZATION_PLAN}.md` + `hooks/` — 全局 skill（受 INVARIANTS R3/R4 + OPTIMIZATION_PLAN Rule 1 约束：禁项目特定术语）

---

## 0. Scope & hard non-goals

### Scope (本计划只覆盖)

- **项目层 (`engine/`)**：`mcp_simulink_tools.py` 工具入口、`modeling_tasks.py` + `smoke_tasks.py` harness 业务逻辑、`matlab_session.py` engine 单例、`simulink_bridge.py`（如需）— 允许项目术语（kundur / ne39 / cvs_v3）
- **MATLAB 通用层 (`slx_helpers/`)**：新增或修改 .m helper — **必须项目无关**，禁出现 kundur / ne39 / cvs_v3 / VSG / paper / Bus 7 anchor 等术语；docstring + 自带测试只用 mini model 或 MATLAB 自带 demo 模型
- **全局 skill (`~/.claude/skills/simulink-toolbox/`)**：仅修通用文案（路由建议、hook 注入），**禁加项目特定术语**（如 NR / VSG / kundur）；与既有 [`OPTIMIZATION_PLAN.md`](C:\Users\27443\.claude\skills\simulink-toolbox\OPTIMIZATION_PLAN.md) 任务范围正交（路由 vs 参数名修正），文件级 conflict 须协调
- **项目侧测试与模板**：`tests/fixtures/`（v2/v3 ground truth）、`probes/kundur/v3_dryrun/`（v3 anchor 测试）、`docs/knowledge/simulink_plan_template.md`（Simulink 计划模板）— 项目术语集中在此

### Hard non-goals (锁住)

- ❌ **不修任何 v3 模型文件**（`kundur_cvs_v3.slx`、`build_kundur_cvs_v3.m`、`_runtime.mat`、IC、`compute_kundur_cvs_v3_powerflow.m` — 已在 `cbc5dda` + `a5bc173` 锁住）
- ❌ **不修 v2 / SPS / NE39** 任何模型 / 配置 / 训练
- ❌ **不修 ANDES / ODE 路径**
- ❌ **不修 RL agent**（`agents/`）、env reward / obs / action 逻辑、scenario contract
- ❌ **不打断当前运行的 NE39 500-ep 训练**（PID 75660 + MATLAB engine 70996）
- ❌ **不破坏 v2 / NE39 现有 probe / harness 调用契约**（向后兼容是硬约束 — 见各阶段 pass criteria）
- ❌ **不引入新的依赖包**（坚持现有 `matlab.engine` + stdlib 路径）

任何偏离 = STOP + 用户授权。

---

## 1. 改进项总览（按 ROI 排序，对应 review §7）

| # | 改进项 | ROI | 阶段 | 修改面 | 估时 |
|---|---|---|---|---|---|
| 1 | 新增 `simulink_block_workspace_dependency` | ⭐⭐⭐⭐⭐ | B | MATLAB helper + Python 入口 + 项目侧 fixture | 4-6 h |
| 2 | `simulink_poll_script` 增量 stdout (diary→file tail，**已重设计**) | ⭐⭐⭐⭐ | C | MATLAB (`slx_run_quiet.m`) + Python | 5-7 h ⬆ |
| 3 | `simulink_trace_port_connections` 加 `max_depth` + cycle 检测 | ⭐⭐⭐⭐ | C | MATLAB helper | 2-3 h |
| 4 | `harness_*` profile-aware fail-fast | ⭐⭐⭐ | E | `engine/modeling_tasks.py` + `engine/smoke_tasks.py`（**修正：非 mcp_simulink_tools.py**） | 2-3 h ⬇ |
| 5 | stdout UTF-8 强制 + Windows PID 暴露 | ⭐⭐ | A | Python (engine + matlab_session) | 1-2 h |
| 6 | `simulink_run_script` (sync) 默认 timeout 600 s | ⭐ ⬇ | A | Python | 0.5 h |
| 7 | `compile_diagnostics(mode='compile')` schema 限定 | ⭐⭐ | A | Python | 0.5 h |
| 8 | 新增 `simulink_powerlib_net_query` | ⭐⭐⭐ | D | MATLAB helper + Python 入口 + 项目侧 anchor 测试 | 5-7 h |
| 9 | `simulink_explore_block` 对 powerlib 端口返回 `not_supported` 标记 | ⭐ | D | MATLAB helper + Python | 1 h |
| 10 | skill hook 注入 ≤ 2 行通用路由建议（**禁项目术语**） | ⭐ | A | skill SKILL.md / hooks/ | 0.5 h |
| 11 | Simulink 计划模板（**搬到项目内**：`docs/knowledge/simulink_plan_template.md`，不污染 superpowers writing-plans skill） | ⭐ | E | 项目内文档 | 1 h |

**总估时：** ~24-32 h（含 §3.C.1 重设计上调 + §3.E.1 改对位置后下调；不含审查 / 回归测试 wall）

**ROI 注释：**
- #2 工时含 MATLAB-side diary→file + Python tail（matlab.engine 同步 RPC 无 subprocess stdout）
- #4 工时含 `_harness_profile_gate.py` 共用 helper + `modeling_tasks.py`/`smoke_tasks.py` 9 函数 fail-fast 注入
- #6 保留是为了文档清晰性（async 默认已 300 s，sync 实际很少触发）

---

## 2. 阶段划分（建议执行顺序）

### Phase A — Quick wins（低风险 ergonomics，并行执行）

**目标：** 一晚搞定 5 项小修；任何一项独立可 ship；不阻塞下游。

涵盖项：#5（UTF-8 + PID）、#6（sync timeout）、#7（compile mode）、#10（hook 路由建议）、#11（plan-writing 模板）

详细见 §3.A。

### Phase B — Block workspace dependency（最高 ROI 单项）

**目标：** 新增 `simulink_block_workspace_dependency` 工具，能直接消除一类 critic 修订（如 R2-Blocker1 死代码 workspace var）。

涵盖项：#1

详细见 §3.B。

### Phase C — Streaming + safety bounds

**目标：** 让 long-running build / sim 中间不再黑盒；让密集 net trace 不 OOM。

涵盖项：#2（partial_stdout）、#3（max_depth）

详细见 §3.C。

### Phase D — Powerlib introspection

**目标：** 物理网拓扑可内省，不再靠"短路 + 看 ω 飞不飞"反推。

涵盖项：#8（net_query）、#9（explore_block 标记）

详细见 §3.D。

### Phase E — Harness profile-aware

**目标：** harness 工具在 v3 这类新 profile 上不静默错路由，要么前置 fail-fast，要么 profile-driven dispatch。

涵盖项：#4

详细见 §3.E。

---

## 3. 各阶段细化

### 3.A — Phase A：Quick wins

#### 3.A.1 stdout UTF-8 强制 + Windows PID 暴露（项 #5）

**Target:** MCP `simulink_poll_script` / `simulink_run_script` 返回的 stdout 不再 GBK 乱码；PID 字段同时给 Windows-side。

**Modification surface:**
- `engine/mcp_simulink_tools.py` —
  - poll / run 在读取子进程 stdout 时 `decode('utf-8', errors='replace')`，不依赖 OS locale
  - 在 MATLAB 侧脚本启动前注入 `feature('DefaultCharacterSet','UTF-8')`（一次性 helper script）
  - 在 poll / status 返回 dict 加 `windows_pid` 字段（用 `psutil.Process(os.getpid()).pid` 在 Windows 下与 Cygwin PID 区分；Cygwin 路径调用走 `cygpath` 反查或直接附 `wmic process where ...` 反查）
- `engine/matlab_session.py` — engine 启动后立即跑 `feature('DefaultCharacterSet','UTF-8')`

**Risk:**
- R-A1-1: 已有调用方依赖现有乱码字符串做匹配（不太可能，但 grep 一次 `engine/` + `probes/` 验证）
- R-A1-2: PID 字段名变更破坏现有调用方 — **缓解：** 新增字段，不改老字段（`pid` 保持 Cygwin 视角，新增 `windows_pid`）

**Validation:**
- 单元：故意 print 中文字符串到 MATLAB stdout，poll 返回应能直接显示，无 `\xc1\xfa` 之类
- 单元：poll 返回 dict 必含 `pid` 且新增 `windows_pid`；Windows 下两者相等或可在 `tasklist` 中查到

**Pass criteria:**
- ✅ v3 probe 回归 PASS — 通过 `simulink_run_script_async("slx_run_quiet('probes/kundur/v3_dryrun/probe_5ep_smoke_mcp')")` 触发（**实际文件是 .m，非 .py**；v3_dryrun 下 probe_*.m 全部走 helper string 路径）
- ✅ 现有任意 probe 字符串消费方无 `UnicodeDecodeError`（编码改不会引发 KeyError，原表述笔误）
- ✅ poll 返回 dict 仍含老 `pid` 字段（向后兼容），新增 `windows_pid`

---

#### 3.A.2 sync timeout 默认 600 s（项 #6）

**Target:** `simulink_run_script` 同步模式默认 timeout 从 120 s 升到 600 s（async 默认已是 300 s，不变）。

**Modification surface:**
- `engine/mcp_simulink_tools.py` — `simulink_run_script(...)` 默认 `timeout_sec=600`
- docstring 说明：长 build / 长 sim 类工作建议显式传 `timeout_sec` 或走 async

**Risk:** 无 — 老调用如显式传 `timeout_sec` 不变；不传的老调用从 120 s 容忍到 600 s 是放宽，不破坏。

**Validation:** 单元测试 — 不传 timeout 跑一个 30 s sleep MATLAB 脚本，应能正常完成（旧默认 120 s 也能跑 30 s，但用 130 s sleep 能区分新旧）。

**Pass criteria:**
- ✅ 130 s MATLAB 脚本在新默认下完成，旧默认下 timeout

---

#### 3.A.3 `compile_diagnostics(mode='compile')` schema / fallback（项 #7）

**Target:** mode='compile' 不再报 `Simulink.BlockDiagram.compile` 不存在；要么显式 raise schema 错误，要么 fallback 到 `update`。

**Modification surface:**
- `engine/mcp_simulink_tools.py` — `simulink_compile_diagnostics(model_name, mode)` 加 `mode in {'update', 'rebuild'}` 校验，不允许传 `compile`
- 文档解释 `update` 和 `rebuild`（如已实现 rebuild）的区别

**Risk:** 现有调用方传 `compile`（review §3.5 唯一一次）会从 silent failure 变 schema error。**这是修复**，非 regression。

**Validation:**
- mode='compile' 应 raise `ValueError`（or MCP error）而非 MATLAB 异常
- mode='update' 调用回归 PASS — 一次 v2 模型 + 一次 v3 模型（防止 schema 校验 typo 同时破坏 update 路径）

**Pass criteria:**
- ✅ schema 校验 + 错误信息清晰指示合法 mode 集合
- ✅ mode='update' v2 + v3 各跑一次，无 regression

---

#### 3.A.4 skill hook 路由建议（项 #10）

**Target:** `~/.claude/skills/simulink-toolbox/` 的 hook 注入文本加 ≤ 2 行通用路由建议（**严格通用，禁项目术语**）：

```
Long-running script (build/sim > 60 s) → simulink_run_script_async + simulink_poll_script
Param discovery before placing → simulink_library_lookup (cheap, 1 call replaces N retries)
```

（删去原草稿中 "NR"（Newton-Raphson 潮流，paper-track 项目术语）和 "Pre-sim sanity"（与既有 OPTIMIZATION_PLAN.md 修复 preflight 误用任务有重叠，待该计划完成后再评估）。）

**Modification surface:**
- `~/.claude/skills/simulink-toolbox/SKILL.md` 或 `hooks/claude/`、`hooks/codex/` 中的注入文本（取较稳的位置；先读现状再决定）

**边界硬约束：**
- INVARIANTS R4（无摩擦增长）：注入文本总长度增加 ≤ 2 行；如使总注入 > 5 行，按重要性挤掉旧行
- INVARIANTS 全文：禁加项目特定术语
- 与既有 [`~/.claude/skills/simulink-toolbox/OPTIMIZATION_PLAN.md`](C:\Users\27443\.claude\skills\simulink-toolbox\OPTIMIZATION_PLAN.md) 任务范围正交（路由 vs 参数名/preflight 修正）

**实施顺序决策（2026-04-27 实测：该 OPT_PLAN.md 6 Task / 18 Step 全 `[ ]` 未启动）：**
- Phase A 启动时再核查该 OPT_PLAN.md 进度
  - **0 进度** → 直接做 ≤ 2 行注入；PR 描述附 cross-link 到该 OPT_PLAN.md，标记"orthogonal task; merge order doesn't matter"
  - **进行中** → 串行等其完成（但等待时长 > 7 天 → 走 PR 合并）
  - **已完成** → 在新基础上加注入

**Risk:**
- R-A4-1: 与既有 OPTIMIZATION_PLAN.md hook 改动 merge conflict — **缓解：** 先读后改，且按上面"实施顺序"

**Validation:** 下次 session 启动时确认 hook 注入文本包含两行通用路由；不含 "NR" / "VSG" / "kundur" / "ne39" 等术语。

**Pass criteria:**
- ✅ 通用文本可见、新增 ≤ 2 行
- ✅ INVARIANTS 全部 R 项不违反
- ✅ 与既有 OPTIMIZATION_PLAN.md 协调记录在本计划 §10 修订摘要

---

#### 3.A.5 Simulink 计划模板（项 #11，**已搬到项目内**）

**Target:** 在本仓库内新增 `docs/knowledge/simulink_plan_template.md`，对 Simulink-涉及步骤给出标准 MCP 工具序列模板，供项目侧 plan 作者引用。

**为什么不放到 superpowers writing-plans skill：** 该 skill 是全局通用，加 Simulink 特定模板违反 superpowers skill 项目无关原则；放项目内可任意写 v3 / NR / VSG 等术语。

模板示例：

```
For each Simulink touch step:
1. simulink_library_lookup(...)           # discover params before placing
2. simulink_run_script_async(build_*.m)   # build
3. simulink_compile_diagnostics(update)   # sanity
4. simulink_run_script_async(sim_*.m)     # actual sim
5. simulink_poll_script(...)              # poll
```

**Modification surface:** 仅 `docs/knowledge/simulink_plan_template.md`（新增）；CLAUDE.md "常见修改点定位" 表加一行指引。

**Risk:** 无。

**Pass criteria:**
- ✅ 模板文件创建，CLAUDE.md 有引用入口
- ✅ 下次本项目 plan 实际抄用一次（计入下个 plan 末尾的 deliverable list 验证）

---

### 3.B — Phase B：`simulink_block_workspace_dependency`

#### 3.B.1 设计

**Why critical:** 见 review §4.1 + §5.3。critic R2-Blocker1（LoadStep workspace 死代码）的发现成本是"读 670 行 build script"，本工具一次调用即可。

**Schema:**

```jsonc
simulink_block_workspace_dependency(
  model_name: str,                   // required
  workspace_vars: list[str] | None,  // optional; if None, return all referenced vars
  scope: "model" | "subsystem"       // default "model"; subsystem path passed in workspace_vars[0]?? simpler: just model
) → {
  "model": "kundur_cvs_v3",
  "vars": {
    "G_perturb_1_S": {
      "consumed_by_blocks": [],
      "consumer_count": 0,
      "verdict": "DEAD"
    },
    "Pm_step_amp_1": {
      "consumed_by_blocks": [
        {"path": "kundur_cvs_v3/Pm_step_amp_c_ES1", "param": "Value", "expression": "Pm_step_amp_1"}
      ],
      "consumer_count": 1,
      "verdict": "LIVE"
    }
  },
  "scan_summary": {
    "blocks_scanned": 412,
    "params_scanned": 1840,
    "elapsed_sec": 1.2
  }
}
```

#### 3.B.2 MATLAB 端实现（`slx_helpers/slx_block_workspace_deps.m`）

**边界硬约束（slx_helpers 严格项目无关）：**
- helper 函数签名、docstring、自带测试 **禁出现** kundur / ne39 / cvs_v3 / VSG / paper / Pm_step / G_perturb / Bus 7 等项目术语
- helper 自测只用 `slx_create_model` 临时 mini model（造一个 1 Constant + 1 Gain 的玩具模型即可）
- 所有 v3 / v2 ground truth fixture 放 **项目侧** `tests/fixtures/`（见 §3.B.5）


```matlab
function result = slx_block_workspace_deps(model_name, workspace_vars)
% 1. load_system if not loaded
% 2. blocks = find_system(model_name, 'LookUnderMasks', 'all', 'Type', 'block');
% 3. for each block:
%      DialogParameters = get_param(b, 'DialogParameters');
%      for each param p in DialogParameters:
%        v = get_param(b, p);                 % string value
%        if ischar(v) || isstring(v):
%          for each var in workspace_vars:
%            if regexp(v, ['\<' var '\>'], 'once'):  % word boundary
%              record (block, param, expression)
% 4. emit RESULT: {...} JSON line for MCP harvest
end
```

实现 hint：
- 用 `regexp` word-boundary `\<var\>` 避免 `Pm_step_amp_1` 误匹 `Pm_step_amp_10`
- 跳过 mask block 内部黑盒不必要的下钻（`LookUnderMasks='all'` 已展开）
- `DialogParameters` 不是所有 block 都有（如 SimscapeBlock）— `try/catch` 跳过
- 性能：v3 ~ 400 块、平均 5 表达式参数，~ 2000 字符串扫描；regexp 单次 < 1 ms → < 2 s 总

#### 3.B.3 Python 端实现（`engine/mcp_simulink_tools.py`）

新增 tool decorator + schema；调用 MATLAB-side helper；解析 RESULT JSON。

#### 3.B.4 Risk

- R-B-1: `find_system` 在 mask 内不一定能找到所有引用 — **缓解：** v3 build 中无 mask 引用 workspace var（已 verified by reading build script），但需在 docstring 标注此限制
- R-B-2: workspace var 通过 `evalin('base', ...)` 间接访问的代码无法静态检测（如 callback 里读 base var）— **缓解：** docstring 标注，并加可选 `--include-callbacks` 旗标做 callback 文本扫描
- R-B-3: 大模型（NE39 500+ 块）扫描时间超过 sync 默认 timeout — **缓解：** 走 async 模式

#### 3.B.5 Validation（**ground truth 已搬到项目侧**）

**helper 自测（在 `slx_helpers/` 内，必须项目无关）：**
- 单元 H1：`slx_create_model` 造 mini model（1 Constant block Value=`myvar` + 1 Gain Gain=`unusedvar` 不接入任何东西，或反之 Gain 无引用）→ 工具应返回 myvar=LIVE / unusedvar=DEAD

**项目侧测试（在 `tests/fixtures/kundur_workspace_vars.json` + `tests/test_workspace_deps_kundur.py`）：**

Fixture 来源：grep 全部 `assignin('base', X, ...)` 候选 var → 人工对每 X 标注期望 `verdict: DEAD | LIVE`。**不用 `kundur_cvs_runtime.mat` 当 ground truth** — 该 mat 是仿真初值快照而非 var-consumer 清单。

- 单元 P1：v3 fixture — `G_perturb_1_S` / `LoadStep_t_1` / `LoadStep_amp_1` 期望 DEAD（review §4.1 已 verified）
- 单元 P2：v3 fixture — `Pm_step_amp_1..4` / `Pm_step_t_1..4` 期望 LIVE
- 单元 P3：v2 fixture — 读 `build_kundur_cvs.m` 同样标注；现有所有 LIVE 仍 LIVE（向后兼容）
- 单元 P4 (NE39 性能上限)：在 NE39 模型上跑（如有）→ < 30 s wall（§3.B.4 R-B-3 缓解证据）

**fixture 生成辅助流程（防漏）：**
```bash
# Step 1: grep 全部 assignin 调用，得到候选 var list
grep -nE "assignin\(['\"]base['\"]," scenarios/kundur/simulink_models/build_kundur_cvs_v3.m \
  | sed -E "s/.*assignin\(['\"]base['\"], *['\"]([^'\"]+)['\"].*/\1/" \
  | sort -u > /tmp/v3_candidate_vars.txt
# Step 2: 人工对每个 var 标 verdict（DEAD/LIVE）+ expected consumer block
# Step 3: 保存到 tests/fixtures/kundur_workspace_vars.json
```
list 由 grep 兜底完整性，verdict 仍人工但有完整候选池。
- 单元 P4 (NE39 性能上限)：在 NE39 模型上跑（如有）→ < 30 s wall（§3.B.4 R-B-3 缓解证据）

#### 3.B.6 Pass criteria

- ✅ helper 单元 H1 PASS（不含项目术语）
- ✅ 项目侧 P1-P3 全 PASS
- ✅ P4 NE39 性能上限达成（如不可达 → 走 async 路径并记录限制）
- ✅ 工具调用 < 5 s wall on `kundur_cvs_v3`
- ✅ helper docstring 标注 mask / callback / `evalin('base',...)` 间接访问的检测限制

---

### 3.C — Phase C：Streaming + safety bounds

#### 3.C.1 `simulink_poll_script` 增量 stdout（项 #2）

**设计：MATLAB diary → 文件 → Python tail**（rationale 见 §10 D1）

```
Async job 启动时:
  Python: 给 job 分配 job_id；预生成 log_path = <tempdir>/slx_job_<job_id>.log
  Python → MATLAB: 调 slx_run_quiet 时传 log_path 参数
  MATLAB (slx_run_quiet.m): diary(log_path); diary on; <现有逻辑>; diary off
                            (diary 是非缓冲的，行级 flush)

Poll 时:
  Python: 读 log_path 当前文件大小 + 末尾 N KB 内容
  MATLAB engine 仍在跑：log_path 持续追加，Python tail 拿增量
  done 时：仍按现有路径返回 important_lines，并附 stdout_full 路径
```

**Schema:**

```jsonc
simulink_poll_script(job_id, tail_kb=50) → {
  "status": "running" | "done" | "error",
  ...,
  "stdout_tail": "...末尾 tail_kb KB 文本...",
  "stdout_total_bytes": 13800,
  "stdout_path": "<tempdir>/slx_job_<jid>.log",   // running 也返回，便于外部 tail
  "stdout_truncated": true | false                 // tail_kb 是否截断了
}
```

**Modification surface:**
- `slx_helpers/slx_run_quiet.m` — 改签名 `function summary = slx_run_quiet(code_or_file, log_path)`；`if nargin < 2 || isempty(log_path)` 时跳过 diary（**1-arg 调用必须行为不变**）；2-arg 时 `cleanupObj = onCleanup(@() diary('off')); diary(log_path); diary on;`
- `engine/mcp_simulink_tools.py` —
  - `simulink_run_script_async` 分配 `log_path`（到 `tempfile.gettempdir()`），传给 `slx_run_quiet`
  - `simulink_poll_script` running 状态读文件末尾 `tail_kb`；done 状态保留现有 `important_lines` 不变
  - 现有 sync `simulink_run_script` 不需改 — 仍 1-arg 调用
- `tests/test_vsg_run_quiet.m` — 新增 2-arg case（diary 写文件成功）；现有 1-arg case **保持不动**（zero-modification 硬约束）
- `tests/test_mcp_simulink_tools.py:374` — `mock_eng.slx_run_quiet` mock 必须接受新可选参数（用 `MagicMock(side_effect=lambda *a, **kw: {...})` 而非固定 1-arg）

**边界硬约束：**
- `slx_run_quiet.m` 是项目无关 helper；`log_path` 参数命名通用，禁出现项目术语
- **向后兼容硬约束：** `slx_run_quiet('script_name')` 单参数调用必须行为完全不变；`probes/README.md:20` 文档化的调用模式不能 break

**Risk:**
- R-C1-1: stdout 大 → MCP payload 膨胀 — **缓解：** `tail_kb` 默认 50；调用方需要更多可显式传更大值
- R-C1-2: log 文件不清理累积 — **缓解：** done 时 evict job 同时 `os.unlink(log_path)`；启动时清理 `slx_job_*.log` 24 h 以上的残留
- R-C1-3: diary 在 MATLAB 错误抛出时不会自动关闭 — **缓解：** `slx_run_quiet.m` 用 `cleanupObj = onCleanup(@() diary('off'));`
- R-C1-4: 多 async 并发不允许（已有 `_SCRIPT_JOB_LOCK` 串行化），所以 log_path 不会冲突

**Validation:**
- 单元 H2（helper 项目无关）：跑一个 `for k=1:30; fprintf('line %d\n',k); pause(1); end` 的 mini 测试脚本；中间 poll 3 次拿到约 10/20/30 行
- 项目侧 P5：`build_kundur_cvs_v3.m` 中间 poll 看到 "Adding bus..." / "Adding ESS..." / "Saving model..." 逐步进展

**Pass criteria:**
- ✅ poll running 状态返回 `stdout_tail` 非空 + `stdout_total_bytes` 单调增
- ✅ done 时 `important_lines` 与原行为一致（向后兼容硬约束）
- ✅ 错误抛出时 diary 仍正确关闭（`onCleanup` 验证）
- ✅ helper 单测不含项目术语
- ✅ **关键回归**（4 个文件，必须全 PASS，不删任何现有 case）：
  - `tests/test_vsg_run_quiet.m` — 1-arg case 全部 PASS（zero-modification）
  - `tests/test_async_run_script.py` — async 路径 PASS（间接验证 log_path 不破坏 async 现状）
  - `tests/test_mcp_simulink_tools.py` — 含 `mock_eng.slx_run_quiet` 的 case PASS（mock 签名扩展但旧 assertion 仍通过）
  - `probes/README.md:20` 文档化的 `slx_run_quiet('probes/...')` 调用模式手动 smoke 一次

---

#### 3.C.2 `simulink_trace_port_connections` 加 `max_depth` + cycle 检测（项 #3）

**Target:** 密集物理网（v3 Bus 7：~11 端口共线）trace 不 OOM；显式截断 + 报告。

**Schema:**

```jsonc
simulink_trace_port_connections(
  block_path: str,
  port: str,
  max_depth: int = 10,        // NEW; was unbounded
  max_visits: int = 200       // NEW; total visited port count cap
) → {
  ...,
  "truncated": true | false,
  "truncated_at_depth": 10,
  "truncated_at_visits": 200
}
```

**Modification surface:** `slx_helpers/slx_trace_port_connections.m` — 加深度计数 + visited set；Python schema 同步（仅加新字段）。

**边界硬约束：** helper 内部和 docstring 禁提 v3 / Bus 7 / Load7 等项目术语。所有 v3 anchor 性能验证移到项目侧。

**Risk:**
- R-C2-1: 现有调用如依赖"完整树"会因截断变 partial — **缓解：** 默认 max_depth=10 应覆盖 99 % 实际场景；返回 `truncated` 显式标记，调用方可显式传更大值

**Validation:**
- 单元 H3（helper 项目无关）：用 `slx_create_model` 造一个 4 端口共线 mini net；max_depth=2 应截断、max_depth=10 应完整
- 项目侧 P6：在 `kundur_cvs_v3/Load7/LConn1` 上跑（放 `probes/kundur/v3_dryrun/`）→ 不 OOM，返回 `truncated: false` 或合理截断
- 项目侧 P7（regression）：现有 v2 + NE39 trace 调用 PASS

**Pass criteria:**
- ✅ helper 单元 H3 PASS（不含项目术语）
- ✅ P6: `Load7/LConn1` trace 完成 < 5 s，无 OOM
- ✅ P7: v2 / NE39 trace regression PASS

---

### 3.D — Phase D：Powerlib introspection

#### 3.D.1 `simulink_powerlib_net_query`（项 #8）

**Target:** 给定一个 powerlib block 的物理端口，返回该 electrical net 上所有成员。

**Schema:** 见 review §4.2。

**MATLAB 端实现 hint:**
- powerlib 物理网在 `power_analyze` / `getLinkData` 中有暴露；或者通过 simscape language 的 `simscape.netlist.Netlist` API
- 备选：解析 `power_analyze(model, 'sort')` 输出的 netlist 结构

**边界硬约束：** `slx_powerlib_net_query.m` 的 docstring + 自测必须项目无关。所有 v3 / v2 / SPS 拓扑验证放项目侧。

**Risk:**
- R-D1-1: powerlib API 不同版本签名不同 — **缓解：** 在 R2025b 下 verified；老版本走 fallback 返回 `not_supported`
- R-D1-2: 实现成本高（5-7 h）、依赖 powerlib 内部 API — **缓解：** 如果 §3.D.2 的 `not_supported` 标记 + 既有 build script 文档已能解决 critic 工作流，本项可降级到 P2/P3

**Validation:**
- 单元 H4（helper 项目无关）：用 powerlib 自带 demo（如 `power_2quadrant`）或 `slx_create_model` 造 mini powerlib net 测，验证 net 成员枚举正确
- 项目侧 P8：在 v3 anchor 上跑（测试代码放 `probes/kundur/v3_dryrun/probe_powerlib_net_query.py`）→ 返回应含 Bus 7 net 上所有 11 个端口
- 项目侧 P9（regression）：v2 + SPS 拓扑正确识别

**Pass criteria:**
- ✅ 单元 H4 PASS（不含项目术语）
- ✅ P8: v3 Bus 7 anchor 返回所有已知端口（不漏 / 不重）
- ✅ P9: v2 / SPS regression PASS

---

#### 3.D.2 `simulink_explore_block` powerlib 标记（项 #9）

**Target:** 当 block 是 powerlib LConn / RConn 时，明确返回 `"power_port_introspection": "not_supported"`，不再让调用方误以为"端口存在但无连接 = 该 net 没有其他成员"。

**Modification surface:** `slx_helpers/slx_describe_block_ports.m`（实测当前实现位置）+ Python schema 注释。

**边界判定：** 仅新增字段 + 旧字段（`is_connected`、`source_blocks`、`sink_blocks`、`connections`）行为不变；既有 skill `~/.claude/skills/simulink-toolbox/patterns/{build-and-verify,debug-existing-model,trace-connectivity}.md` 引用 `simulink_describe_block_ports` 的 4 处不需任何修改 — patterns/*.md 文档无需 PR。

**Risk:** 无（向后兼容，仅加字段）。

**Pass criteria:**
- ✅ 在 powerlib block 上调用时返回 `power_port_introspection` 字段
- ✅ Simulink 信号端口 block 不返回该字段（避免冗余）
- ✅ 既有 v2/v3/NE39 trace_port_connections 链式调用 regression PASS

---

### 3.E — Phase E：Harness profile-aware

#### 3.E.1 `harness_*` profile-aware dispatch（项 #4）

**Target:** harness 工具读 `KUNDUR_MODEL_PROFILE` 或类似 env，自动 dispatch 到对应路径，或前置 fail-fast。

**两种执行路径：**

| Path | 描述 | 工作量 | 推荐 |
|---|---|---|---|
| **(A) Fail-fast** | 在 v3 / 不支持的 profile 下 raise `harness_profile_mismatch` 错误，告诉用户去用哪个 v3-aware 替代 | 1-2 h | ✅ Phase E 默认 |
| (B) 完全 profile-driven | harness 工具内部 dispatch 到不同 helper（v2 / v3 / NE39） | 4-5 h | 待 (A) ship 后视需求决定 |

**Path A 设计：**

**关键事实（2026-04-27 verified）：**
- `engine/harness_tasks.py` 是 52 行的 re-export 兼容 shim（注释明写"real implementations live in modeling_tasks / smoke_tasks"），**不是修改面**
- `engine/modeling_tasks.py:323` 已 import `KUNDUR_MODEL_PROFILE` —— 不需新加 env 检测
- `engine/smoke_tasks.py` 419 行，无 profile import；需新加

**步骤：**

**关键事实（实测）：**
- Kundur 有动态 profile 加载器：`KUNDUR_MODEL_PROFILE = load_runtime_kundur_profile()`，`.model_name` 可为 `kundur_cvs` / `kundur_cvs_v3` / `kundur_vsg` 等（受 env var 控制）
- NE39 **无动态 profile**：`NE39_BRIDGE_CONFIG.model_name = 'NE39bus_v2'` 静态 hardcode 在 BridgeConfig 里
- `engine/harness_registry.py:23` 已有 `resolve_scenario(scenario_id) → ScenarioSpec` 返回 contract base name（`kundur_vsg` / `NE39bus_v2`）— 复用此 API 避免重造轮子

1. **`engine/_harness_profile_gate.py`** （NEW，~ 30 行）— 双 scenario profile 检测：

   ```python
   # engine/_harness_profile_gate.py
   from typing import Any

   _UNSUPPORTED_PROFILES: dict[str, set[str]] = {
       "kundur": {"kundur_cvs_v3"},   # v3 uses cvs_signal step_strategy + integer-suffix loggers
       "ne39":   set(),                # NE39 has no dynamic profile; extend only if base changes
   }

   def _runtime_profile_name(scenario_id: str) -> str | None:
       """Resolve runtime profile name. Kundur reads dynamic profile; NE39 has none — fallback to contract base."""
       try:
           if scenario_id == "kundur":
               from scenarios.kundur.config_simulink import KUNDUR_MODEL_PROFILE as _p
               return _p.model_name  # dataclass attribute, NOT .get()
           if scenario_id == "ne39":
               from engine.harness_registry import resolve_scenario
               return resolve_scenario("ne39").model_name  # 'NE39bus_v2', static
       except (ImportError, AttributeError, ValueError):
           return None
       return None

   def check_harness_profile(scenario_id: str) -> dict[str, Any] | None:
       """Return None if supported; return error dict if profile mismatch."""
       runtime_name = _runtime_profile_name(scenario_id)
       if runtime_name is None:
           return None  # profile resolution failed — let downstream surface the real error
       if runtime_name in _UNSUPPORTED_PROFILES.get(scenario_id, set()):
           return {
               "ok": False,
               "error": "harness_profile_mismatch",
               "scenario_id": scenario_id,
               "profile_name": runtime_name,
               "message": (
                   f"harness path does not support profile '{runtime_name}' for scenario "
                   f"'{scenario_id}'. See docs/knowledge/training_management.md and "
                   f"scenarios/{scenario_id}/NOTES.md for the supported alternative."
               ),
           }
       return None
   ```

2. `engine/modeling_tasks.py` 中 `harness_model_diagnose/inspect/patch_verify/report` 顶部加 fail-fast。**位置约束：** 在 `resolve_scenario(scenario_id)` 之后、任何 scenario-specific 业务逻辑（含 `_val_align` 在 Kundur 路径上）之前。

   ```python
   from engine._harness_profile_gate import check_harness_profile
   spec = resolve_scenario(scenario_id)        # 现有代码
   _gate = check_harness_profile(scenario_id)
   if _gate is not None:
       return _gate
   # ... 后续 scenario-specific 业务（_val_align 等）
   ```

3. `engine/smoke_tasks.py` 中 `harness_train_smoke_*` 5 函数同样加。

（设计依据见 §10 D2 + D3。）

**Modification surface:**
- `engine/_harness_profile_gate.py`（NEW，~ 25 行 — 共用 profile gate）
- `engine/modeling_tasks.py`（4 函数顶部加 import + 3 行 gate 调用）
- `engine/smoke_tasks.py`（5 函数顶部加 import + 3 行 gate 调用）
- **不改** `engine/mcp_simulink_tools.py`（仅装饰器入口）
- **不改** `engine/harness_tasks.py`（兼容 shim）

**Phase E 启动前 verify：** 无（OQ #8 已结案 — NE39 无动态 profile；gate 设计已用 `resolve_scenario('ne39').model_name` 替代不存在的 `NE_MODEL_PROFILE` import）

**边界判定：** 修改在 `engine/`（项目层），允许项目术语，OK。

**Risk:**
- R-E1-1: 如果有人通过 harness 测过 v3 部分功能（哪怕没记录），fail-fast 会让现有手工流程 break — **缓解：** review §3.7 已确认 v3 phase 1-3 harness 调用计数为 0
- R-E1-2: `_UNSUPPORTED_PROFILES` 集合维护 — **缓解：** 加注释要求新 profile 必须在 PR 中显式加入或主动测试

**Validation:**
- 单元：在 v3 profile 下调用 `harness_model_diagnose` / `harness_train_smoke_minimal` → 返回 `error: harness_profile_mismatch`
- 单元：在 v2 (`kundur_cvs`) profile 下调用 → 现有行为不变（regression）
- 单元：在 NE39 profile 下调用 → 现有行为不变（regression，因 `_UNSUPPORTED_PROFILES['ne39']` 是空集）
- 单元（gate 模块自测）：monkeypatch `_UNSUPPORTED_PROFILES['kundur'] = {'kundur_cvs'}` 验证 v2 fail-fast 消息格式正确
- 单元（gate 容错）：monkeypatch `import` 失败 → `check_harness_profile` 返回 `None`（不让 gate 自身崩溃 propagate 到 harness 工具）

**Pass criteria:**
- ✅ v3 profile 调用 harness_* 全部给出 `harness_profile_mismatch` 错误
- ✅ v2 + NE39 现有调用 regression PASS（双 scenario 都覆盖）
- ✅ 修改在 `_harness_profile_gate.py` + `modeling_tasks.py` + `smoke_tasks.py`，不改 mcp_simulink_tools.py / harness_tasks.py
- ✅ NE39 profile import 实测确认（Open Question #8 已 close）

---

## 4. 跨阶段风险

### R-X1：v2 / NE39 现有调用契约不能破坏

任何修改在 ship 前必须在 v2 + NE39 至少一个 representative probe 上回归 PASS：
- v2: `probes/kundur/probe_*` 的某一个最小 smoke
- NE39: NE39 现有 probe（如 `probes/ne39/...`，按 CLAUDE.md 路径）

不要等 phase 末才回归；每个阶段 ship 前都要跑。

### R-X2：NE39 训练活跃状态检测（条件性约束，rationale 见 §10 D7）

执行任意 phase **前**做条件检测：

```bash
# Step 1: 是否有 NE39 训练活跃
tasklist | findstr /I "MATLAB python"
ls -lt results/sim_kundur/runs/*/training_status.json 2>/dev/null | head -3
# 看最近 status.json 是否在 last 5 min 内更新
```

**判定与缓解：**
- 训练活跃 → 所有 MATLAB-side 修改**只能新增 .m 文件**，**禁止**修改既有 `slx_step_and_read_cvs.m` / `slx_episode_warmup_cvs.m` / `slx_run_quiet.m` 等共享 helper 内部逻辑（§3.C.1 必须等训练结束）
- 训练空闲 → 共享 helper 修改可放心做，但仍按"phase 边界 ship + restart MCP server + 跑回归"流程
- **MCP server 重启 ≠ 训练进程重启**：训练有独立 matlab.engine 进程，MCP 重启不影响它；但反过来，修共享 helper 后训练用的 MATLAB engine 不会自动重载 → 训练期内禁改

### R-X3：MCP 工具 schema 变更影响其他项目

simulink-tools 是项目内的 MCP server。schema 加字段（向后兼容）OK；删字段 / 改字段类型 = 破坏。本计划所有改动设计为新增字段或新增工具，不删不改老字段。

### R-X4：Token 熔断器（CLAUDE.md 规则）

任何阶段实现中如果 ~5000 token 没实质进展（无 passing test / 成功调用 / 确认修改），STOP + 分析瓶颈再继续。

---

## 5. 验证 / 回归矩阵

| 阶段 | v3 probe 回归 | v2 probe 回归 | NE39 不打断 | 新工具单元 |
|---|---|---|---|---|
| A | smoke MCP ✅ | smoke ✅ | ✅ | UTF-8 / PID / timeout / mode 各 1 |
| B | smoke MCP ✅ | smoke ✅ | ✅ | dead/live var 各 ≥ 2 |
| C | smoke MCP ✅ | smoke ✅ | ✅ | poll streaming + trace max_depth |
| D | smoke MCP ✅ | smoke ✅ | ✅ | net_query Bus 7 + explore powerlib |
| E | smoke MCP ✅ | smoke ✅ + harness regression | ✅ | v3 fail-fast 消息单元 |

---

## 6. 推荐执行顺序 & decision points

```
[每个 phase ship 步骤]：
  1. v2 + v3 + NE39 regression PASS（NE39 视训练状态，活跃则跳过现场跑）
  2. 删 .pyc 缓存：`rm engine/__pycache__/mcp_simulink_tools.cpython-*.pyc engine/__pycache__/_harness_profile_gate.cpython-*.pyc`
  3. 重启 MCP server（Claude session 重启或 MCP server 命令重启）
  4. 在新 session 跑一次 representative probe 验证新工具生效
  5. user GO → 进下一 phase

[每个 phase 启动前]：先做 §4 R-X2 NE39 训练活跃检测

Day 1 (~3-4 h):
  Phase A — quick wins (#5/#6/#7/#10/#11)
  GATE A: ship + restart MCP + regress v2 smoke + (NE39 smoke if 训练空闲)
  ↓ 用户 GO?

Day 2 (~6-8 h):
  Phase B — block_workspace_dependency (#1)
  GATE B: helper H1 + 项目侧 P1-P3 PASS + (P4 NE39 性能 if 模型可达)
  ↓ 用户 GO? (可选：在此 plan 一次 critic 修订；如能直接消除某个之前 BLOCKER 视为本项工具自证)

Day 3 (~6-8 h, 上调):
  Phase C — streaming (#2 重设计 5-7 h) + max_depth (#3 2-3 h)
  GATE C: helper H2/H3 + 项目侧 P5/P6/P7 PASS
  ↓ 用户 GO?

Day 4 (~6-8 h):
  Phase D.2 first (#9, ~ 1 h) — explore powerlib 标记
  GATE D.2: 标记返回 + v2 regression
  ↓
  Phase D.1 (#8, ~ 5-7 h) — net_query
  GATE D.1: helper H4 + 项目侧 P8/P9 PASS

Day 5 (~2-3 h):
  Phase E — harness profile-aware (#4) — 修对位置 modeling_tasks.py + smoke_tasks.py
  GATE E: v3 fail-fast 消息 + v2/NE39 regression

Total work: ~ 24-32 h
Wall (每日有 user gate + 训练活跃检测 + MCP restart 间隔): 1-2 周（5 个有效工作日，非连续）
```

**Decision points:**
- 每个 GATE：用户审 verdict 决定是否进下一阶段
- Phase B 完成后：评估是否真消除了一类 critic 修订；如否，重审本计划 ROI 排序
- Phase D.1 实现成本高，如 D.2 + 文档已能解决，D.1 可降级延后

---

## 7. 不在本计划范围内的事

- 不重写 `simulink_run_script` 同步路径（async 已足够）
- 不实现 `simulink_compile_diagnostics(mode='compile')` 真功能（schema 限定即可，节流）
- 不在本计划阶段做 NE39 / ANDES / ODE 路径专属工具（review §8 风险声明：本评估仅 v3 样本）
- 不改 RL training 代码 / scenario contract / agent 实现
- 不改 paper / fact-base / 模型本身

---

## 8. 文件清单（计划完成后预期 deliverables）

**项目层（`engine/`，允许项目术语）：**
```
engine/mcp_simulink_tools.py                  (modified — UTF-8/PID/timeout/mode/poll tail/B 工具入口/D 工具入口)
engine/matlab_session.py                      (modified — UTF-8 init)
engine/modeling_tasks.py                      (modified — Phase E harness fail-fast 4 函数)
engine/smoke_tasks.py                         (modified — Phase E harness fail-fast 5 函数)
engine/_harness_profile_gate.py               (NEW, Phase E — 共用 profile gate)
```

**MATLAB 通用层（`slx_helpers/`，严格项目无关）：**
```
slx_helpers/slx_run_quiet.m                   (modified — 签名加 log_path 可选；nargin<2 行为不变；onCleanup 兜底)
slx_helpers/slx_trace_port_connections.m      (modified — max_depth + visited set)
slx_helpers/slx_describe_block_ports.m        (modified — powerlib not_supported 标记，§3.D.2)
slx_helpers/slx_block_workspace_deps.m        (NEW, Phase B — 项目无关)
slx_helpers/slx_powerlib_net_query.m          (NEW, Phase D.1 — 项目无关)
```

**项目侧测试与模板：**
```
tests/fixtures/                               (NEW dir — mkdir before Phase B)
tests/fixtures/kundur_workspace_vars.json     (NEW, Phase B — v3+v2 ground truth via grep+人工)
tests/test_workspace_deps_kundur.py           (NEW, Phase B)
tests/test_vsg_run_quiet.m                    (modified — 加 2-arg case；现有 1-arg case zero-modification)
tests/test_mcp_simulink_tools.py              (modified — slx_run_quiet mock 接受新可选 arg)
probes/kundur/v3_dryrun/probe_powerlib_net_query.py  (NEW, Phase D.1 — v3 anchor 测试)
docs/knowledge/simulink_plan_template.md      (NEW, Phase A.5 — 计划模板)
CLAUDE.md                                     (modified — "常见修改点定位"加模板入口)
```

**全局 skill（`~/.claude/skills/simulink-toolbox/`，受 INVARIANTS 约束）：**
```
~/.claude/skills/simulink-toolbox/SKILL.md    或 hooks/<flavor>/  (modified, ≤ 2 行通用路由)
                  — 协调 OPTIMIZATION_PLAN.md 任务后再 ship
```

**外部输入（不修）：**
```
quality_reports/reviews/2026-04-27_simulink_tools_mcp_review.md         (predecessor)
~/.claude/skills/simulink-toolbox/INVARIANTS.md                          (硬约束)
~/.claude/skills/simulink-toolbox/OPTIMIZATION_PLAN.md                   (正交任务，需协调)
```

**Commit 节奏：** 每个阶段独立 commit；每个 commit 含 v2 + v3 regression 证据 + helper 项目无关性 grep 证据。

---

## 9. 已识别的开放问题（实施前需澄清）

| # | 问题 | 状态 | 备注 |
|---|---|---|---|
| 1 | simulink-tools MCP server 源代码是否在本仓库 | ✅ 已结案 | `engine/mcp_simulink_tools.py` 2002 行确认（2026-04-27 verified） |
| 2 | skill hook 注入路径 | ✅ 已结案 | `~/.claude/skills/simulink-toolbox/{SKILL.md, hooks/claude/, hooks/codex/}` |
| 3 | harness 工具 profile 检测逻辑 | ✅ 已结案 | 仅 `modeling_tasks.py:323` 有 `KUNDUR_MODEL_PROFILE` import；`smoke_tasks.py` 无；`harness_tasks.py` 是 shim 不动 |
| 4 | 是否存在 `simulink_profile_aware_harness` 占位工具 | ✅ 已结案 | 不存在 |
| 5 | Phase B 工具命名最终版 | 🟡 ship 前定 | 候选：`simulink_block_workspace_dependency` / `simulink_workspace_var_consumers` / `simulink_var_xref` |
| 6 | 既有 skill `OPTIMIZATION_PLAN.md` 任务的执行状态 | ✅ 已结案（2026-04-27） | 6 Task / 18 Step 全 `[ ]` 未启动；§3.A.4 决策见时限规则 |
| 7 | NE39 训练当前活跃状态 | 🟡 每个 phase 启动前 verify | 见 §4 R-X2 检测脚本 |
| 8 | NE39 profile import 路径与属性名 | ✅ 已结案（2026-04-27 r4） | NE39 无动态 profile；用 `resolve_scenario('ne39').model_name` 拿 'NE39bus_v2' 即可 |

---

## 10. 决策日志（4 轮审查收敛）

每条记录：决策结论 + 一句 rationale。不重述错误版草稿。

### 设计决策（D）

- **D1 (§3.C.1) MATLAB diary→file tail，不走 subprocess.PIPE**
  Rationale: matlab.engine 同步 RPC 无 subprocess stdout 流可读；diary 是 MATLAB 内置非缓冲日志机制，`slx_run_quiet` 加可选 `log_path` 参数即可，1-arg 调用行为不变。

- **D2 (§3.E.1) Profile gate 走 `engine/_harness_profile_gate.py` + 复用 `resolve_scenario`**
  Rationale: Kundur 有动态 profile（`KUNDUR_MODEL_PROFILE.model_name` 受 env 控制），NE39 无（model_name 静态 hardcode 在 BridgeConfig）。复用 `engine/harness_registry.py:23` 的 `resolve_scenario('ne39').model_name` 比 import 不存在的 `NE_MODEL_PROFILE` 干净。Profile 是 dataclass 属性 `.model_name`，**不是 dict `.get(...)`**。

- **D3 (§3.E.1) Gate 注入位置：`resolve_scenario(scenario_id)` 之后、所有 scenario-specific 业务逻辑之前**
  Rationale: profile mismatch 比 manifest drift / val_align 更基本；约束在 NE39 路径（无 val_align）也无歧义。

- **D4 (§3.B.5) Workspace var fixture 走 `grep assignin` 候选 + 人工 verdict**
  Rationale: `kundur_cvs_runtime.mat` 是仿真初值快照而非 var-consumer 清单；用 mat 当 ground truth 会让数值常量被误判 DEAD。grep 兜底 list 完整性，verdict 仍人工保证准确。

- **D5 (§3.A.4) skill OPT_PLAN.md 协调走"实测 0 进度 → 直接做 + cross-link"**
  Rationale: 实测该 OPT_PLAN.md 6 Task / 18 Step 全 `[ ]` 未启动；任务范围正交（路由 vs 参数名修正）；等待无收益。

- **D6 (§3.A.5) Simulink 计划模板放项目内 `docs/knowledge/`，不污染 superpowers writing-plans skill**
  Rationale: superpowers skill 项目无关；项目内可任意写 v3 / VSG 等术语而不破坏全局规则。

- **D7 (§4 R-X2) NE39 训练活跃状态走条件检测，不写死 PID**
  Rationale: PID 失效快；条件检测（tasklist + status.json mtime）可移植。

### 边界规则（B）

- **B1** `engine/` 项目层 — 允许 kundur/ne39/cvs_v3/VSG 术语
- **B2** `slx_helpers/` 严格项目无关 — 实测 30 个 .m 文件 0 处项目术语，新增/修改 helper 必须保持；项目特定测试搬 `tests/fixtures/` + `probes/<scenario>/`
- **B3** `~/.claude/skills/simulink-toolbox/` 全局通用 — 受 INVARIANTS R3/R4 + OPT_PLAN Rule 1 约束，禁项目术语；hook 注入新增 ≤ 2 行，总长 > 5 行须挤旧

### 结案开放问题（OQ closed）

| OQ | 结论 |
|---|---|
| #1 MCP 源在仓库 | ✅ `engine/mcp_simulink_tools.py` 2002 行 |
| #2 hook 注入路径 | ✅ `~/.claude/skills/simulink-toolbox/{SKILL.md,hooks/}` |
| #3 harness profile 检测现状 | ✅ 仅 `modeling_tasks.py:323` 有 import；smoke_tasks 无 |
| #4 `simulink_profile_aware_harness` 占位工具 | ✅ 不存在 |
| #6 既有 OPT_PLAN.md 状态 | ✅ 实测 0 进度（D5 决策） |
| #8 NE39 profile API | ✅ 无动态 profile，走 `resolve_scenario('ne39').model_name`（D2 决策） |

剩余开放：**#5 Phase B 工具命名**、**#7 NE39 训练活跃状态（每 phase 启动前现场 verify）**

---

**End of plan v4. Awaiting user GO before any execution.**

**第一步**（如收到 GO）：
1. §4 R-X2 NE39 训练活跃状态检测
2. 启动 Phase A（quick wins，5 项小修，~ 3-4 h），完成后 §6 phase ship 5 步
