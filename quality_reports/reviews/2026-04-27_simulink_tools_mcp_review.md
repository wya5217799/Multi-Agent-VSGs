# simulink-tools MCP — Phase 1 → Phase 3 使用评估报告

> **Generated:** 2026-04-27
> **Scope:** Kundur CVS v3 Phase 1 (NR + build) → Phase 3.4 (5-ep smoke PASS at commit `a5bc173`) 期间所有 simulink-tools MCP 工具实际使用情况的回顾性评估。
> **Author perspective:** 主控 agent，通过 MCP 调用 simulink-tools；视角是"做事的人"，不是工具开发者。
> **Companion docs:** 路线图位于 [`quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_phase5_roadmap.md`](../plans/2026-04-26_kundur_cvs_v3_phase4_phase5_roadmap.md)；Phase 0 audit 位于 `results/harness/kundur/cvs_v3_phase3/phase3_p30_audit_verdict.md`。

---

## 0. Executive summary

simulink-tools MCP **是这次 v3 Phase 1–3 能完成的关键基础设施**。最重要的单点价值是 long-lived 预热 MATLAB engine — P3.4 从 Python `matlab.engine` 冷启动 24 min HANG 转向 MCP 路径 71 s PASS，本质就是绕过冷启动 + 资源争用。

但有 5 个**影响开发节奏**的限制：(1) stdout 不能实时流式回传 (2) power port 不可内省 (3) connection trace 在密集 net 上 OOM (4) harness 工具与 v3 profile 契约不匹配 (5) 缺少 workspace-var 反向追踪工具 — 后两者直接是 critic 三轮中最难诊断的两个 BLOCKER (R2-Blocker1 LoadStep workspace 死代码、Pm-step proxy 路径选择) 的根因。

最高优先级建议：实现一个 `simulink_block_workspace_dependency` 工具，能列出 .slx 中所有块的 `Value` / `Resistance` / `Inductance` 等表达式实际引用的工作空间变量。

---

## 1. 工具使用频次 + 满意度

| 工具 | 调用次数 | 评级 | 主要用途 |
|---|---|---|---|
| `simulink_run_script_async` + `simulink_poll_script` | ≈ 15+ 对 | ⭐⭐⭐⭐⭐ | 主力执行通道：build、NR、smoke |
| `simulink_compile_diagnostics(mode='update')` | 3 | ⭐⭐⭐⭐ | build-edit 后第一道闸 |
| `simulink_library_lookup` | 1 | ⭐⭐⭐⭐⭐ | P3.0b 关键救场 |
| `simulink_step_diagnostics` | 1 | ⭐⭐⭐⭐ | Phase 1.3 0.5 s smoke |
| `simulink_explore_block` | 1 | ⭐⭐ | Power port 信息空 |
| `simulink_trace_port_connections` | 1 | ⭐ | OOM / 无限递归 |
| `harness_train_smoke_minimal/start/poll` | 0 | n/a | 契约不匹配 v3 |
| `harness_model_diagnose/inspect/patch_verify/report` | 0 | n/a | 同上 |
| `simulink_run_script` (sync) | 0 | n/a | 用 async 替代 |
| `simulink_bridge_status` | 0 | n/a | 没用上 |

---

## 2. 做对的事 — 高价值确认

### 2.1 Long-lived 预热 engine（**核心价值**）

P3.4 第一次跑 `probes/kundur/v3_dryrun/probe_5ep_smoke.py`（Python 冷启动 `matlab.engine.start_matlab()`）：

- ep0 reset/warmup 卡住 24 min
- Python CPU 0 %、MATLAB CPU < 0.7 %
- 输出文件 0 字节（`tail -80` pipe 缓冲）
- 根因：与并行 NE39 500-ep 训练（PID 75660 + MATLAB engine 70996，已运行 57 min）争用 MATLAB license server / shared cache / OS lock

切到 `simulink_run_script_async` MCP 路径（PID 65256，long-lived 预热 engine，独立进程）：

- 同模型 71 s 完成 5 个 ep × 50 step = 250 步 round-trip
- ALL 8 gates PASS

**结论：长生命周期、预热好、独立进程的 MCP engine 是这一阶段的关键基础设施**。任何团队成员只要在 MATLAB 上做需要快速迭代的脚本/sim 工作，应优先用 MCP 路径而不是直接 Python `matlab.engine` 冷启。

### 2.2 `simulink_library_lookup` 救场版本漂移

P3.0b 第一次 build 失败：`ToWorkspace block 没有名为 'LimitDataPoints' 的参数`。如果硬猜会反复试错；用 `simulink_library_lookup('simulink', 'To Workspace')` 一次得到当前版本所有 `params_main`：发现这个版本只有 `MaxDataPoints`、不再有 `LimitDataPoints`。**单次调用省了 N 次 build 重试**。

### 2.3 `compile_diagnostics(mode='update')` 作为 build-edit gate

每次 build 后做 sim 之前先 `update`：< 5 s 拿到 0 errors / 0 warnings 确认。比直接跑 `step_diagnostics` 至少便宜 10×。

### 2.4 `step_diagnostics` 的 schema 设计正确

Phase 1.3 0.5 s smoke 一次给出：`status='success'`、`elapsed_sec`、`sim_time_reached`、`warning_count`、`error_count`、`simscape_constraint_violation` — 一次就拿到所有要写进 verdict 的字段。这种 wrapped-MATLAB-result 的 schema 比让 agent 解析裸 stdout 强得多。

---

## 3. 用得不顺的事 — 影响开发节奏的限制

### 3.1 `simulink_run_script_async` 的 stdout 不能 streaming

**症状：**
- async 启动后 `simulink_poll_script` 在 status='running' 时不返回任何已经累积的 stdout
- 60+ s 的 build 中间发生什么完全黑盒
- 只有 status='done' 时一次性返回 `important_lines`（且只截取带 `RESULT:` 前缀的行 + 部分错误行）

**实际影响：**
- P3.0b 第一次 build 失败时只能从最后一行错误反推；如果错误发生在 build 后期、前面已经 print 了一堆诊断，全丢
- Phase 1.1 NR 第一次外层迭代 30 轮发散，正常应每轮看一行；只能等结束看完整 history

**改进意见：**
- `simulink_poll_script` 在 running 状态时返回 `partial_stdout` (从启动到现在累积的 stdout)
- 或者引入 `simulink_tail_script` 工具显式查询当前缓冲

### 3.2 `simulink_run_script` (sync) 默认 120 s timeout 太短

build_kundur_cvs_v3 一次 build ~ 19 s 没问题，但 P3.0b 第一次（含初次 powerlib load）跑了 25+ s 仍在范围内。如果哪天 build 跑 130 s 会被 silently 杀掉。`max=600 s` 的支持有，但默认值偏低。**建议**：默认 600 s，同时 schema 文档提示 build / NR 类工作宜传 `timeout_sec`。

### 3.3 `simulink_trace_port_connections` 在密集 net 上 OOM

在 v3 build 上探 `Load7/LConn1`：

```
"error_message": "内存不足。可能的原因是程序内存在无限递归。"
```

v3 Bus 7 这种 net 上挂着：1 条 Load7 + 1 条 Shunt7 + 1 条 LoadStep7 + 4 条线路端点 + 4 条线路 shunt-C/2 共 ~11 个端口共线。trace 应该是有限深度的图遍历，不该 OOM。

**改进意见：**
- 加 `max_depth` 参数（默认 10 或类似）
- 显式检测 cycle / large-fanout net，截断时返回 `"truncated_at": <port_count>`
- 不要靠 catch OutOfMemory 兜底

### 3.4 `simulink_explore_block` 对 powerlib power port 信息空

```
{
  "ports": [
    {"kind":"LConn","index":1,"is_connected":true,
     "source_blocks":[],"sink_blocks":[],"connections":[]}
  ]
}
```

`is_connected: true` 但所有连接列表都是空。原因：powerlib `LConn` / `RConn` 是 Simscape 物理域端口，不是 Simulink 信号线 — 工具的内省机制看不见物理网。

**实际影响：** P3.4 诊断 LoadStep7 是否真在网里浪费了几次 sim：
1. 短路 R=1e-3 测试（看 ω 是否飞）
2. 修改 Load7 R 反测（发现无影响 → 误判 Load7 没接通）
3. 最终通过算 Pe 总和反向验证拓扑正确

**改进意见：**
- 要么明确返回 `"power_port_introspection": "not_supported_for_this_block_type"`
- 要么实现 `simulink_powerlib_net_query(model, bus_id_or_anchor)` 返回该 electrical net 上所有块 + 端口

### 3.5 `compile_diagnostics(mode='compile')` 报 "类 Simulink.BlockDiagram 没有名为 'compile' 的常量属性或静态方法"

第一次试 `mode='compile'` 期望深度编译诊断，结果直接报错。`mode='update'` 才工作。

**改进意见：**
- schema 限定 `mode` 枚举
- 或者 `compile` 不可用时 fallback 到 `update` + warning

### 3.6 stdout 编码 GBK→UTF-8 乱码

MATLAB 报错 `Warmup sim failed: 由原因导致` 之类的，本来是中文（"由原因导致" 应该是 "Caused by..."），但走 MCP stdout 时乱码 → critic 一轮和我都得脑补。

**改进意见：**
- MCP 在采集 stdout 时强制 UTF-8 解码、或附原始字节
- MATLAB 端可统一 `feature('DefaultCharacterSet','UTF-8')`

### 3.7 `harness_*` 系列工具一次没用上

整个 Phase 1-3 自己手写了 5 个 probe（`probe_30s_zero_action`, `probe_pm_step_reach`, `probe_loadstep_reach`, `probe_wind_trip_reach`, `probe_hd_sensitivity`, `probe_d_*_decay`, `probe_logger_readout_sanity`, `probe_5ep_smoke_mcp`），但 `harness_train_smoke_minimal` / `harness_model_diagnose` / `harness_model_inspect` 这一套 harness 工具一次没用上。

**根因猜测：**
- harness 工具默认绑 v2 / NE39 路径的契约（`omega_ES{idx}` 信号、`phang_feedback` step strategy、`kundur_cvs_runtime.mat` 硬编码 sidecar）
- v3 用 `cvs_signal` step strategy + 整数后缀 logger + v3 sidecar — harness 假设全错位

**实际影响：**
- 每个新场景重写 probe 的 boilerplate 浪费 ~30 % 时间
- harness 系列在一个仓库里成了"看起来很全但实际没人用"的死路径

**改进意见：**
- harness 工具检测 `KUNDUR_MODEL_PROFILE` 当前指向的 profile，如果 `solver_family != harness 假设的 simscape_ee` 或 `step_strategy != phang_feedback`，**前置 fail-fast 警告**，告诉用户用哪个 v3-aware 替代
- 或者 harness 工具完全 profile-driven，不假设契约

### 3.8 Cygwin PID vs Windows PID 不一致

不是 simulink-tools 直接问题，但跨工具协作时是个坑：

- `ps -ef` (Cygwin) 给 PID 153023
- `tasklist | grep 153023` 找不到（Windows-side PID 是 45200）
- PowerShell `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'probe_5ep_smoke' }` 才找到

**改进意见：**
- `simulink_bridge_status` 或 `simulink_poll_script` 返回里同时给 Windows-side PID
- 文档明确"如果你在 Cygwin/MSYS bash 里跑 PowerShell tools，PID 之间不互通"

---

## 4. 缺失的工具 — 最想要的新增

### 4.1 `simulink_block_workspace_dependency` (HIGHEST PRIORITY)

**Why critical:**

critic 二轮 R2-Blocker1 是这一轮整个 Phase 4 plan 修订的最大根因 — `build_kundur_cvs_v3.m:200-205` 创建了 `G_perturb_<k>_S` / `LoadStep_t_<k>` / `LoadStep_amp_<k>` 工作空间变量，但 `LoadStep7/9` 块的 `Resistance` 是硬编码 `'1e9'`，**这些 workspace var 实际上从未被任何 Simulink 块读取**。这种"workspace var 创建但未被消费"的死代码只能靠人肉 grep build script 才能发现。

**Proposed schema:**

```jsonc
simulink_block_workspace_dependency(
  model_name="kundur_cvs_v3",
  workspace_vars=["G_perturb_1_S", "LoadStep_t_1"]
) → {
  "G_perturb_1_S": {
    "consumed_by_blocks": [],     // empty = dead
    "consumer_count": 0
  },
  "LoadStep_t_1": {
    "consumed_by_blocks": [],
    "consumer_count": 0
  },
  "Pm_step_amp_1": {              // example of live var
    "consumed_by_blocks": [
      {"path": "kundur_cvs_v3/Pm_step_amp_c_ES1", "param": "Value"}
    ],
    "consumer_count": 1
  }
}
```

**Implementation hint:** MATLAB-side 遍历 `find_system(model, 'Type', 'block')`，对每个块的 `DialogParameters` 字段做正则搜匹 var name。

**Impact:** 立刻让 P4.0 audit 不需要人肉读 build；可能避免一整轮 critic 修订。

### 4.2 `simulink_powerlib_net_query`

**Why:** 见 §3.3 / §3.4。powerlib 物理网拓扑现在不可内省。

**Proposed schema:**

```jsonc
simulink_powerlib_net_query(
  model_name="kundur_cvs_v3",
  start_block="kundur_cvs_v3/L_6_7a",
  start_port="RConn1"
) → {
  "net_id": "Bus_7_anchor",
  "members": [
    {"block":"kundur_cvs_v3/L_6_7a","port":"RConn1"},
    {"block":"kundur_cvs_v3/L_6_7b","port":"RConn1"},
    {"block":"kundur_cvs_v3/Load7","port":"LConn1"},
    {"block":"kundur_cvs_v3/Shunt7","port":"LConn1"},
    {"block":"kundur_cvs_v3/LoadStep7","port":"LConn1"},
    {"block":"kundur_cvs_v3/L_7_12","port":"LConn1"},
    {"block":"kundur_cvs_v3/L_7_8a","port":"LConn1"},
    ...
  ],
  "anchor_chosen_by_build": "L_6_7a/RConn1"
}
```

### 4.3 `simulink_run_script_async` 的增量 stdout 模式

见 §3.1。

```jsonc
simulink_poll_script(job_id="...", since_byte=12345) → {
  "status": "running",
  "elapsed_sec": 18.3,
  "stdout_chunk": "...",       // bytes 12345 onward
  "stdout_total_bytes": 13800
}
```

### 4.4 `simulink_profile_aware_harness` (替代当前 harness_*)

让 harness 工具读 `KUNDUR_MODEL_PROFILE` env var，自动 dispatch 到 v2 / v3 / SPS / NE39 路径，不要硬编码契约。

---

## 5. 与开发流程的契合度

### 5.1 与 Skills 契约的契合

`C:/Users/27443/.claude/skills/simulink-toolbox/SKILL.md` map.md 每次都被 hook 注入提示 "Use named MCP tools. Avoid shell matlab/.m/find_system bypasses." 这一点起到了正向约束 — Phase 0 audit 之后我自觉不再考虑 `Bash python` 调 `matlab.engine` 的路径，直接走 MCP。

但 hook 的注入文本对**具体路由建议**只指向 map.md 而不内联。**改进意见：** hook 注入时直接附 1-2 行最高频路由建议 ("use simulink_run_script_async for any > 60 s task")，对话开销小、效果直接。

### 5.2 与 Plan-First Workflow 契合

不一致：plan markdown 里我写"使用 `simulink_run_script_async`"是 plan 时的指令，但实际执行时往往同一段 plan 步骤要交替用 3-4 个 MCP 工具（async + poll + library_lookup + compile_diagnostics）。**改进意见：** 在 plan-writing skill 里加一节"对 Simulink-涉及步骤的标准 MCP 工具序列"模板。

### 5.3 与 critic 审查契合

critic agent 三轮审查里 R2-Blocker1（LoadStep workspace 死代码）是 critic 直接读 `build_kundur_cvs_v3.m:200-205` 才发现的。如果有 `simulink_block_workspace_dependency`，critic 一次工具调用就能确认死代码事实，不需要读 670 行 build script。**这条工具直接受益于 critic 工作流。**

---

## 6. 量化：本次 v3 工作中的 MCP 时间分布（粗估）

| 阶段 | MCP MATLAB 调用数 | 估计 wall time | 备注 |
|---|---|---|---|
| Phase 1.1 NR | 3 (1 失败 + 1 重试 + 1 spot-check) | ~ 1 min | 收敛 5 s × 多次 |
| Phase 1.3 build + smoke | 4 (build + library_lookup + 2 sim) | ~ 1.5 min | 1 次 LimitDataPoints fail |
| Phase 2 五个 probe | 8 个 sim | ~ 5 min | 30 s zero-action + ...等 |
| P3.0b/c rebuild + sanity | 3 | ~ 2 min | |
| P3.4 smoke (Python hung version) | n/a | **24 min hung** | NOT MCP path |
| P3.4 smoke (MCP MATLAB-side) | 3 (1 cell-array fix retry + 1 base_ws seed retry + 1 PASS) | ~ 1.5 min wall (含两轮 fix) | |
| **MCP 总 wall**（不含 hung Python） | ~ 25 calls | **~ 12 min** | 平均 ~ 30 s/call |
| **若全用 Python `matlab.engine` 冷启** | 25 calls × 估 ~ 3-5 min/cold-start (含可能 hang) | **75-125 min, 高方差** | 不可接受 |

**净效率提升估计 ≥ 6× — 主要来自不重新付冷启 cost。**

---

## 7. Top-5 给工具开发者的建议（按 ROI 排序）

1. **新增 `simulink_block_workspace_dependency`** — 单工具、MATLAB-side 实现轻量、能直接消除一类整轮的 critic 修订（R2-Blocker1 那一类）。
2. **`simulink_poll_script` 支持 partial_stdout** — long-running build/sim 中间不再黑盒；估计能省 30 % 调试 wall。
3. **`simulink_trace_port_connections` 加 `max_depth` 默认值** — 不让密集 net OOM 把整个工具变成"看起来支持但不能用"。
4. **harness_* 工具加 profile-aware dispatch** 或者**前置 fail-fast 警告** — 让它在 v3 这类新 profile 上不静默错路由。
5. **stdout UTF-8 强制 + Windows-side PID 暴露** — 边边角角的 ergonomics 修一遍。

---

## 8. 风险声明

本报告基于一次（v3 Phase 1-3）的使用样本。某些限制（如 stdout streaming 缺失）在小型 / 短任务下不显眼，是中型 build (60+ s) 才暴露。其他路径（NE39 训练长跑、ANDES、ODE）的 simulink-tools 使用情况未覆盖，建议交叉对照。

不修任何工具或代码 — 这是评估报告，不是改进 PR。`harness_*` 工具在 v3 路径上未试用 ≠ 它们整体不工作；只能说 v3 当前契约下没匹配上。

---

## 9. 文件列表

```
quality_reports/reviews/2026-04-27_simulink_tools_mcp_review.md   (this file)
```

仅一份 markdown。无代码 / 模型 / 训练 / 工具修改。
