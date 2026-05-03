# Task 1 — W2 直连 Bus 8 — 落实执行计划

**Date:** 2026-04-28
**Goal:** v3 PVS_W2 物理上直接接 Bus 8, 删除 Bus 11 中转节点 + L_8_W2
短 Π-line。系统从 16-bus 降到 15-bus。
**Paper PRIMARY:** line 894 — "100 MW wind farm is **connected to bus 8**"
**Constraint:** 仅 modeling layer 修改; 不动 reward / SAC / PHI / paper_eval /
NE39 / v2 / SPS / Phase A++ CCS injection 路径。
**Tool policy:** simulink-tools MCP only; 长任务 (NR + build > 60s) 用
`simulink_run_script_async` + `simulink_poll_script`; 短验证用 sync。

---

## 0. 影响文件清单 (PRIMARY 引证)

| 文件 | 现状 | 需修改 |
|---|---|---|
| `scenarios/kundur/simulink_models/build_kundur_cvs_v3.m` | line 118 `L_8_W2`; src_meta W2 bus=11 | EDIT |
| `scenarios/kundur/simulink_models/compute_kundur_cvs_v3_powerflow.m` | bus 11 在 bus list, L_8_W2 在 line list, W2 注入在 bus 11 | EDIT |
| `scenarios/kundur/kundur_ic_cvs_v3.json` | 含 bus 11 V/angle 数据 | REGENERATE (NR 跑出) |
| `scenarios/kundur/simulink_models/kundur_cvs_v3_runtime.mat` | 含 bus 11 相关 workspace var (`Wphase_2` 是 bus 11 角度, 重派后变 bus 8 角度) | REGENERATE (build 跑出) |
| `scenarios/kundur/simulink_models/kundur_cvs_v3.slx` | PVS_W2 在 bus 11 节点, L_8_W2 块存在 | REBUILD |

> **REVIEW NOTE (0):** 文件清单完整。`runtime.mat` 是 build 副产物,
> `IC.json` 是 NR 副产物 — 修改顺序 `build script + NR script` →
> `NR run` → `build run` → `.slx + runtime.mat 自动生成`。

---

## 1. Pre-flight (执行前必做)

### 1.1 状态快照 + Git tag

**目的:** 任务失败时可一键回滚。

| Step | Tool | Action |
|---|---|---|
| 1.1.a | `Bash` | `git status` 确认无未提交脏改动 |
| 1.1.b | `Bash` | `git tag pre-task-1-w2-bus8-2026-04-28` |
| 1.1.c | `simulink_run_script` (sync, < 5s) | 计算并打印 `kundur_cvs_v3.slx` + `kundur_cvs_v3_runtime.mat` + `kundur_ic_cvs_v3.json` 三个文件 SHA-256 (= pre-Task baseline) |

**Acceptance:** 三个 SHA-256 记录到执行日志。Git tag 可用于回滚。

> **REVIEW NOTE (1.1):** 不做 Git tag 直接改 build 是危险的。Phase D
> 已建立 SHA-256 verification 模式, 复用。

### 1.2 当前模型 PRIMARY 验证 (确认起点)

| Step | Tool | Action |
|---|---|---|
| 1.2.a | `simulink_run_script` | 在 base workspace 读: `evalin('base', 'WindAmp_2')`, `WVmag_2`, `Wphase_2` 三个 W2 IC 值 → 记录 (回滚检查用) |
| 1.2.b | `simulink_get_block_tree` model='kundur_cvs_v3' | 确认存在 `PVS_W2` (路径 `kundur_cvs_v3/PVS_W2`) + `L_8_W2` (4 个相关块: 主 + Csh_F + Csh_T + GND) |

**Acceptance:** 起点状态符合 audit 描述 (W2 在 bus 11, L_8_W2 完整).

### 1.3 Phase D D6 SHA-256 一致性确认

`runtime.mat` SHA-256 应等于 Phase D 验证值 `febe1ad657...` (Phase D
verdict 记录的)。如果不等, 说明上次 session 后有未追踪改动, **STOP**
排查。

> **REVIEW NOTE (1.3):** 这一步发现历史漂移, 比执行 Task 1 后再发现
> 容易诊断。

---

## 2. 修改 build_kundur_cvs_v3.m

### 2.1 删除 L_8_W2 line_def

**Current (build line 118 附近):**
```matlab
line_defs = {
    ...
    'L_8_W2',   8, 11,    1, R_short, L_short, C_short;
    ...
};
```

**Target:** 删除该行 (整行)。`line_defs` 总行数从 20 → 19。

**Tool:** `Edit` (single old_string → empty new_string with proper context)

**Verify:** Read 改后文件 line 110-122 确认 L_8_W2 不再出现, 同时
`line_defs` 数组语法仍正确 (前后 `;` 和 `};` 完好)。

> **REVIEW NOTE (2.1):** 删行时**包括行末逗号 / 分号**。注意是数组
> 行, 删除整行后前一行的分号仍在。

### 2.2 修改 src_meta W2 bus 编号

**Current (build line 425+ 附近):**
```matlab
src_meta = {
    'G1',  1, ...;
    'G2',  2, ...;
    'G3',  3, ...;
    ...
    'W2', 11, 'pvs', ...;     ← 改 11 → 8
};
```

**Target:** `'W2', 11, 'pvs', ...` → `'W2', 8, 'pvs', ...` (只改 bus 编号字段)

**Tool:** `Edit` (精确匹配 W2 行, 把 11 改成 8)

**Verify:** Read 改后行确认 `'W2',  8, 'pvs'` 序列出现, **bus 11** 不再
在 W2 行 (但 bus 11 可能仍在 line_defs 早期行 — 应已被 2.1 删除)。

### 2.3 全脚本扫描 bus 11 / W2 残留

**Tool:** `Grep` pattern `bus.*11|11.*W2|W2.*11|bus_11`

**Expected:** 0 hit (除注释外)。如有 hit, 评估是否需要再删。

> **REVIEW NOTE (2.3):** 这是防御性检查, 防止 build 内有其他 bus 11
> 引用 (例如硬编码索引、注释中的 bus 11 → 应改为 bus 8)。

---

## 3. 修改 compute_kundur_cvs_v3_powerflow.m

### 3.1 读 NR 脚本

**Tool:** `Read` 全文 `compute_kundur_cvs_v3_powerflow.m`

**目的:** 找到:
- bus list 定义 (含 bus 11 = wind terminal)
- branch list (含 L_8_W2 = bus 8↔11 短线)
- generator/wind 注入定义 (W2 注入在 bus 11)

> **REVIEW NOTE (3.1):** 必须先 Read 才能精确 Edit, 不能盲改。NR
> 脚本结构本 session 未读, 必须看清。

### 3.2 修改 bus list / branch list / wind 注入

**Edits (具体行号待 3.1 Read 后确定):**
- Bus list: 删除 bus 11 行, 更新总数 (n_bus -= 1)
- Branch list: 删除 L_8_W2 entry
- Wind W2 注入: 把 `bus_idx_W2 = 11` 类似的索引改 `= 8`

**Tool:** `Edit` × 3 (每处一个 Edit)

**Verify:** Read 改后脚本相关段, 确认:
- Bus 编号 list 不含 11
- Branch list 不含 L_8_W2
- W2 注入指向 bus 8

### 3.3 全脚本 bus 11 / L_8_W2 残留扫描

**Tool:** `Grep` 同 2.3 模式

**Expected:** 0 hit (含注释也尽量改).

---

## 4. 运行 NR 重派 IC

### 4.1 启动 NR 异步任务

**Tool:** `simulink_run_script_async` (NR 通常 < 60s, 但保险起见 async)

**Code:** `addpath('scenarios/kundur/simulink_models'); compute_kundur_cvs_v3_powerflow();`

**Timeout:** 120 s

**Output:** `kundur_ic_cvs_v3.json` 重生成 (15-bus IC)

### 4.2 轮询完成

**Tool:** `simulink_poll_script` job_id=...

**等待:** done

### 4.3 检查 NR 收敛 + closure

NR 脚本应输出 `RESULT: powerflow.converged = true` 或类似。

**Tool:** poll 返回的 important_lines 中 grep `converged` / `closure_ok`

**Verify:**
- `converged = true`
- `closure_ok = true`
- 无 NaN / Inf 报错

**STOP IF:** NR 不收敛 → Task 1 失败, **回滚** (见 §8)。

> **REVIEW NOTE (4):** NR 是 Task 1 的最大风险点。Bus 8 已有 4 条线
> 连接 (L_7_8a/b/c, L_8_9a/b, L_8_16) + 现在加 W2 注入 = 5 条 + 1 注入
> = 度数 6, 仍合理。但 NR 数值可能因失去 1 km 隔离短线 (= 失去 X≈
> 0.157 Ω) 而对初值更敏感。如果 NR fail, 第一备选是检查 NR 初猜
> bus 8 V/angle, 第二备选是用 pre-Task 1 的 IC json 作 warmstart。

### 4.4 检查 IC json 内容

**Tool:** `Read` `kundur_ic_cvs_v3.json` 头部 + bus list section

**Verify:**
- `schema_version = 3` (不变)
- `topology_variant = 'v3_paper_kundur_16bus'` ← **可能需更新**

> **REVIEW NOTE (4.4):** topology_variant 字符串包含 "16bus", post-Task
> 是 15bus, **会与 build script 的 assert 冲突**。需要决定:
> - 选项 A: 改 build script + IC json 都用 `'v3_paper_kundur_15bus'`
> - 选项 B: 保持 `'v3_paper_kundur_16bus'` 字符串 (历史 ID, 不严格反
>   映 bus 数), 加注释说明 bus 11 已删
>
> **决策建议: 选项 A** — 字符串反映真实拓扑, 防止未来歧义。
> NR script 同步改 `topology_variant` 输出值 + build script 同步改
> assert。

### 4.5 修订 topology_variant 字符串

**Tool:** `Edit`
- `compute_kundur_cvs_v3_powerflow.m`: 写 IC json 时 `topology_variant`
  字段 `'v3_paper_kundur_16bus'` → `'v3_paper_kundur_15bus_w2_at_bus8'`
- `build_kundur_cvs_v3.m` line 39: assert string 同步更新
- `scenarios/kundur/config_simulink.py`: `_load_profile_ic` 函数中
  v3 IC schema check 同步更新 (现状: line ~165 `if raw.get('topology_variant') != 'v3_paper_kundur_16bus'`)

**Re-run NR:** §4.1-4.3 重跑一次, 确认 IC json topology_variant 字段更新。

> **REVIEW NOTE (4.5):** 这是隐藏依赖 — `_load_profile_ic` 严格 assert
> topology_variant 字符串。漏改会让所有 v3 profile loader 全部 raise
> ValueError。Pre-flight 1.2 已发现 PVS_W2 在 bus 11, 但
> topology_variant 字符串引用是 §4.4 才暴露的, **必须修不可漏**。

---

## 5. 重 build .slx

### 5.1 启动 build 异步任务

**Tool:** `simulink_run_script_async`

**Code:** `addpath('scenarios/kundur/simulink_models'); build_kundur_cvs_v3();`

**Timeout:** 400 s (Phase A++ rebuild 用了 146 s, 留余量)

**Output:** `kundur_cvs_v3.slx` + `kundur_cvs_v3_runtime.mat` 重生成

### 5.2 轮询完成

**Tool:** `simulink_poll_script` job_id=...

**等待:** done; 检查 important_lines 无 ERROR

**STOP IF:** build script 抛异常 → 大概率是 §2 的 edit 引入语法错误,
回滚 §2 的 edit + 重新 review。

### 5.3 验证 .slx 拓扑

**Tool:** `simulink_get_block_tree` model=`kundur_cvs_v3`

**Expected:**
- ✅ `PVS_W2` 仍存在
- ❌ `L_8_W2` 不再存在 (主块 + Csh_F + Csh_T + 对应 GND 全部消失)
- ❌ 任何含 `bus 11` / `_11_` 的块名不再存在

**Verify:** `Grep`-style filter on `block_tree` JSON output, 确认上述
3 项。

### 5.4 验证 PVS_W2 RConn 直接接 Bus 8

**Tool:** `simulink_explore_block` block_path=`kundur_cvs_v3/PVS_W2`

**Expected:** Pos/Neg ports 通过电气网络连接到 Bus 8 anchor 块 (具体
sink_blocks 列表应包含 bus 8 邻接元素如 L_7_8a/b/c 或 L_8_9a/b 或
L_8_16, 而 **不**包含 L_8_W2)。

> **REVIEW NOTE (5.4):** 这是 Task 1 是否真起作用的最直观验证。如果
> PVS_W2 还连到不存在的 L_8_W2, 说明 build 没正确清理。

### 5.5 验证 runtime.mat 内容

**Tool:** `simulink_run_script` (sync)

**Code:**
```matlab
S = load('scenarios/kundur/simulink_models/kundur_cvs_v3_runtime.mat');
fprintf('RESULT: WindAmp_2=%g WVmag_2=%g Wphase_2=%g\n', S.WindAmp_2, S.WVmag_2, S.Wphase_2);
% Bus 11 相关变量应不再出现 (前提是项目命名约定)
flds = fieldnames(S);
for i=1:length(flds), if contains(flds{i}, '11') || contains(flds{i}, 'bus11'), fprintf('RESULT: STILL HAS %s\n', flds{i}); end, end
```

**Expected:**
- `WindAmp_2 / WVmag_2 / Wphase_2` 仍存在 (W2 仍在, 只是 bus 改了)
- `Wphase_2` 数值与 Pre-flight 1.2.a 记录的可能不同 (现在反映 bus 8
  角度)
- 无含 "11" 字段名 (语义级)

---

## 6. 验证 NR + zero-action stability

### 6.1 30s zero-action smoke

**Tool:** `simulink_run_script_async`

**Code (probe):** seed runtime.mat → set 30s sim → 跑零动作 → 取 ω
trace 末尾 50 样本均值。

**Acceptance:**
- 无 sim 异常
- max|ω-1| < 5e-5 (= Phase B cell #0 baseline pattern)
- 各 ESS Pe 收敛到稳态

**STOP IF:** 30s 零动作 ω 漂移大或 sim crash → IC / NR 有问题, 回滚。

> **REVIEW NOTE (6.1):** Phase A 30s zero-action 历史值是 max|ω-1| ~
> 2.3e-5。Task 1 后该值若 > 5e-5, 说明 NR 解远离原解, 需检查 (可能
> bus 8 V/angle 受 W2 直接接入影响显著). 5e-5 = 0.0025 Hz, 完全可接受.

### 6.2 50 MW B14 trip 方向 sanity

**Tool:** `simulink_run_script_async`

**Code:** seed runtime + 设 `LoadStep_amp_bus14 = 50e6` → 跑 5s → 检查
ω 是否 freq DOWN (R 接通 = 接 50 MW load = 频率下降)。

**注意:** Task 1 不改 LS 机制 (LS 机制是 Task 2 的事), 因此 LS1 当前
仍是 step-on 方向 (= freq DOWN)。这只是 sanity check 确认扰动机制
post-Task 1 仍 work, 不期待 Task 2 的方向语义。

**Acceptance:**
- ω 信号 < 1.0 (freq DOWN, 因为 R-step-on 加 50 MW 负载)
- 无 NaN / Inf
- 无 sim crash

### 6.3 SHA-256 + workspace 清洁

**Tool:** `simulink_run_script` (sync)

**Code:** 计算新 `kundur_cvs_v3.slx` / `runtime.mat` / `kundur_ic_cvs_v3.json`
SHA-256, 与 Pre-flight 1.1.c 对比 → **应不同** (Task 1 改了文件)。
同时确认 base workspace 状态: `M_<i>=24, D_<i>=4.5, LoadStep_amp_bus*=0,
LoadStep_trip_amp_bus*=0` (= 默认值, 没残留 §6.2 的 50e6).

---

## 7. Acceptance gate (Task 1 完成判据)

| # | Gate | 工具 | 通过判据 |
|---|---|---|---|
| 1 | NR converged | §4 | `converged=true && closure_ok=true` |
| 2 | NR + build 无 ERROR | §4 + §5 | poll important_lines 无 "ERROR" |
| 3 | Block tree: 无 L_8_W2 / bus 11 | §5.3 | filter 0 hit |
| 4 | PVS_W2 直接接 bus 8 邻接块 | §5.4 | sink_blocks 含 L_7_8/L_8_9/L_8_16 之一, 不含 L_8_W2 |
| 5 | runtime.mat 无 "11" 语义字段 | §5.5 | 0 hit |
| 6 | 30s zero-action stable | §6.1 | max\|ω-1\| < 5e-5 |
| 7 | 50 MW B14 step-on 方向正确 | §6.2 | freq DOWN, 无 NaN |
| 8 | SHA-256 已变 (确实改了) | §6.3 | 三个文件 hash 全部 != Pre-flight 值 |
| 9 | topology_variant 同步更新 | §4.5 | IC json + build assert + factory _load_profile_ic 三处一致 |
| 10 | Phase A++ CCS path 仍能用 | (optional) | 跑 50 MW trip 方向 sanity, freq UP |

**全 10 项 PASS = Task 1 完成。** 任一 FAIL = STOP, 进 §8 回滚。

---

## 8. 回滚 (Rollback) 计划

### 8.1 触发条件

任一 acceptance gate FAIL, 或执行中 NR fail / build fail / sim crash。

### 8.2 回滚操作

```bash
git reset --hard pre-task-1-w2-bus8-2026-04-28
```

恢复:
- `build_kundur_cvs_v3.m`
- `compute_kundur_cvs_v3_powerflow.m`
- `kundur_ic_cvs_v3.json`
- `kundur_cvs_v3_runtime.mat`
- `kundur_cvs_v3.slx`
- `config_simulink.py` (如果 §4.5 改了 _load_profile_ic)

到 Task 1 之前状态。

### 8.3 回滚后验证

**Tool:** `simulink_run_script` 计算 SHA-256 三个文件, 应等于 Pre-flight
1.1.c 记录值。

> **REVIEW NOTE (8):** Git tag + SHA-256 双重保险。Phase D 已建立
> 此模式, 复用零成本。

---

## 9. Risk register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1-1 | NR 不收敛 (W2 直接接 bus 8 改变 NR initial guess) | LOW | HIGH | NR script 用 pre-Task IC 作 warm-start (如支持); 或调初猜 bus 8 V=1.02 pu |
| R1-2 | build script edit 引入语法错误 | LOW | MEDIUM | §2.3 全脚本 grep + Read 改后段 |
| R1-3 | topology_variant 字符串遗漏改 → factory raise ValueError | MEDIUM | MEDIUM | §4.5 三处同步改; §6.3 工厂 smoke import 验证 |
| R1-4 | runtime.mat workspace 残留 bus 11 项 → load_system 时报 unknown var | LOW | LOW | §5.5 字段名 grep |
| R1-5 | PVS_W2 块在新 build 没正确连到 bus 8 (端口连错) | LOW | HIGH | §5.4 explore_block 确认 sink_blocks |
| R1-6 | 30s zero-action ω 漂移 (NR 解显著变) | MEDIUM | LOW | 接受 max\|ω-1\| < 1e-4 (放宽 vs 5e-5) 作为 fallback |
| R1-7 | 50 MW B14 trip 方向反转 (Task 1 不应改 LS 机制) | LOW | HIGH | §6.2 必检方向; 反转 → 回滚, 排查 build 是否误改 LS 块 |
| R1-8 | Phase A++ CCS injection 路径 break (build 误删 LoadStepTrip 块) | LOW | MEDIUM | gate 10 sanity |

---

## 10. 执行顺序 (Step-by-step)

```text
A. Pre-flight (§1)
   A1. git status + tag
   A2. 当前模型 PRIMARY 验证 (block tree + workspace + SHA-256)

B. Edit (§2 + §3)
   B1. Read build_kundur_cvs_v3.m line 110-130 (line_defs 区)
   B2. Edit 删 L_8_W2 line_def
   B3. Read build_kundur_cvs_v3.m line 425-440 (src_meta 区)
   B4. Edit 改 W2 bus 11 → 8
   B5. Grep build script 残留检查
   B6. Read compute_kundur_cvs_v3_powerflow.m (全文一次)
   B7. Edit × 3 (bus list / branch list / W2 注入索引)
   B8. Grep NR script 残留检查

C. Topology variant 同步 (§4.5)
   C1. Edit compute_kundur_cvs_v3_powerflow.m: topology_variant 字段
   C2. Edit build_kundur_cvs_v3.m line 39 assert 字符串
   C3. Edit scenarios/kundur/config_simulink.py: _load_profile_ic 函数 v3 分支

D. NR run (§4)
   D1. simulink_run_script_async 跑 NR
   D2. simulink_poll_script 等 done
   D3. Read 新 IC json 头部确认 schema_version + topology_variant
   D4. STOP IF NR 不收敛

E. Build run (§5)
   E1. simulink_run_script_async 跑 build
   E2. simulink_poll_script 等 done
   E3. simulink_get_block_tree 确认 bus 11 / L_8_W2 已无
   E4. simulink_explore_block PVS_W2 确认连 bus 8
   E5. simulink_run_script (sync) 验证 runtime.mat 字段
   E6. STOP IF build fail or 拓扑不对

F. Stability sanity (§6)
   F1. 30s zero-action smoke
   F2. 50 MW B14 step-on 方向 sanity
   F3. (optional) 50 MW B14 trip 方向 sanity (Phase A++ CCS still works)
   F4. SHA-256 + workspace 清洁

G. Acceptance gate (§7)
   G1. 10 项 gate 全过 → Task 1 PASS
   G2. 任一 fail → §8 回滚

H. Verdict
   H1. 写 Task 1 verdict.md (路径 results/harness/kundur/cvs_v3_task_1/)
   H2. Git commit
```

---

## 11. 估时

| 阶段 | 时间 |
|---|---|
| A Pre-flight | 5 min |
| B Edit (build + NR + grep) | 15 min |
| C Topology variant 同步 | 5 min |
| D NR run + verify | 3 min (NR < 1 min + verify) |
| E Build run + verify | 5 min (build ~150s + verify) |
| F Stability sanity | 4 min |
| G Acceptance | 2 min |
| H Verdict + commit | 5 min |
| **Total** | **~45 min** |

---

## 12. 不在 Task 1 scope (留 Task 2/3)

- **不改 LoadStep IC** (= Task 2 的事, 即使 NR 重派也保持 bus 14/15 = 0
  pre-engaged 状态)
- **不改 LS dispatch 方向** (env 仍 step-on for LS1, Task 2 才反向)
- **不改 ESS Pm0 sign** (= Task 2 的副作用, Task 1 应该 Pm0 几乎不变,
  因为 W2 注入位置改但量级不变)
- **不改 action range 常量** (= Task 3 的事, 文档 only)
- **不改 reward / SAC / paper_eval / NE39 / v2 / SPS**

---

## 13. 输出文件

| 路径 | 内容 |
|---|---|
| `results/harness/kundur/cvs_v3_task_1/task_1_verdict.md` | TL;DR + acceptance gates 结果 + SHA-256 前后对比 + 30s/50MW probe 结果 + 影响范围声明 |
| Git commit | `feat(kundur-cvs-v3): Task 1 — W2 直连 Bus 8 (paper line 894 alignment)` |

---

## 14. Self-review (写完整体审)

| 检查项 | 状态 |
|---|---|
| Task 目标清晰 (paper 行号 + 物理修改) | ✓ |
| 影响文件全列 (5 个) | ✓ |
| 依赖顺序正确 (edit → NR → build) | ✓ |
| Pre-flight 含 Git tag + SHA-256 | ✓ |
| 关键 hidden risk (topology_variant 字符串) 已 §4.5 处理 | ✓ |
| Tool policy 合规 (MCP, no shell matlab) | ✓ |
| 长任务用 async + poll | ✓ |
| Acceptance gate 10 项 (覆盖 NR / build / 拓扑 / IC / runtime / sim) | ✓ |
| Risk register 8 条 + mitigation | ✓ |
| Rollback 单步 git reset | ✓ |
| Scope 隔离 (Task 1 不动 Task 2/3 的事) | ✓ |
| 估时合理 (~45 min) | ✓ |

> **FINAL REVIEW:** 写时审过的关键发现:
> 1. **R1-3 topology_variant 字符串** — 计划草稿原本只改 build + NR,
>    遗漏 `config_simulink.py` 的 `_load_profile_ic` 函数严格 assert
>    该字符串。**§4.5 修正补全三处同步**, 否则 v3 profile loader 直
>    接报错。
> 2. **R1-7 LS 方向反转检查** — 容易被忽略, build 修改可能误删 LS
>    块。§6.2 + gate 7 显式 sanity check 50 MW step-on freq DOWN 方向。
> 3. **§5.5 runtime.mat 字段 grep** — workspace var 命名约定可能含
>    "bus11" 子串, 漏清会让后续 sim 报 unknown var.
>
> 计划已具备可直接执行的细节程度, 不期待执行中再发现重大遗漏。
