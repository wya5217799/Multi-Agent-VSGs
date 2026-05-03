# Task 2 — Bus 14 IC 预接入 248 MW + LS1 反向 — 落实执行计划

**Date:** 2026-04-28
**Goal:** v3 IC 时 Bus 14 已挂 248 MW 负荷 (= paper "sudden load reduction"
的 pre-disturbance state); env LS1 dispatch 改为写 `LoadStep_amp_bus14 = 0`
让 R 跳到 1e9 ⇒ 248 MW load 突然断开 ⇒ freq UP (paper-faithful)。
**Paper PRIMARY:** line 993-994 — "sudden load **reduction** of 248 MW at bus 14"
**Pre-req:** Task 1 已 PASS (W2 直连 Bus 8, IC sha=`db974107…`)
**Constraint:** 仅 modeling layer + env disturbance dispatch; 不动 reward / SAC /
PHI / paper_eval / NE39 / v2 / SPS / Task 1 已完成的 W2 拓扑。
**Tool policy:** simulink-tools MCP only; 长任务 `simulink_run_script_async` +
`simulink_poll_script`; 短验证用 sync。

---

## 0. 关键设计决策

### 0.1 不新增 breaker 块, 复用 Phase A 的 R-tunable 机制

Series RLC R + workspace expression `Vbase_const^2 / max(LoadStep_amp_bus14, 1e-3)`
已经具备**双向**能力:
- amp = 0 ⇒ R ≈ 5e13 Ω ⇒ load 断开
- amp = X ⇒ R = V²/X ⇒ X 瓦 load 接通

Task 2 只改两个东西:
1. `LoadStep_amp_bus14` 默认值 (0 → 248e6) — 写入 build 生成的 `runtime.mat`
2. NR 把 248 MW 算进 bus 14 schedule

LS1 触发**反向**: env 在 dispatch LS1 时写 `LoadStep_amp_bus14 = 0` (= 让
R 跳到 1e9 = load 跳出 = freq UP), 而非原 `= 248e6`。

> **REVIEW NOTE (0.1):** 这是 Task 2 最 elegant 的简化。原 plan 假设需要
> 新 breaker 块, 实际 Phase A 的 R 机制已支持。**零新块, 仅改 IC 默认值
> + dispatch 方向。**

### 0.2 LS2 (Bus 15) 不改动

Paper line 994: "sudden load **increase** of 188 MW at bus 15" — paper LS2
是 0→188 MW step-on, **当前 v3 LS2 = step-on direction = paper-aligned**。
Task 2 不动 LS2 任何环节。

### 0.3 Phase A++ CCS injection 路径处置

Phase A++ 加的 `LoadStepTrip_bus14 / LoadStepTrip_bus15` Controlled Current
Source 路径在 Task 2 后**功能性冗余** (real trip 已通过 R-disengage 实现)。

决策: **保留** CCS 块 (零成本), 但 `LoadStep_trip_amp_bus*` workspace var
默认 0 (不激活), 不在 env LS1/LS2 主线 dispatch 中使用。可作 alternate
test mode (例如对比 "negative-load injection" vs "real R-disengage" 的物理
等价性诊断)。

> **REVIEW NOTE (0.3):** 不删 CCS 块降低 build 改动 surface, 也保留诊断
> 工具。如果未来发现 CCS 路径有问题, 可单独清理。

### 0.4 ESS Pm0 sign flip (重大下游影响)

NR 重派后 ESS Pm0 预计:
- pre-Task 2 (含 Task 1): -0.3691 sys-pu/ESS (absorb 模式)
- post-Task 2: 估算 ~+0.0625 sys-pu/ESS (generate 模式)

估算依据:
- 总负荷: 2734 + 248 = 2982 MW
- 固定发电: G1+G2+G3+W1+W2 = 700+700+719+700+100 = 2919 MW
- 损耗: ~37 MW (Task 1 NR 报 1.37%)
- ESS 群体净: 2982+37-2919 = +100 MW = +1.0 sys-pu
- Per ESS: +0.25 sys-pu = +0.125 vsg-pu (假设均分)

ESS Pm0 **符号翻转** = absorb → generate。Phase D D1+D2 audit 已 PRIMARY
确认 swing eq 形式 `M·ω̇ = Pm − Pe − D·(ω−1)` 对 Pm 符号无敏感性 (M1 fix
已 cover negative Pm 的 _Pe_prev fallback)。

> **REVIEW NOTE (0.4):** Pm0 翻号是物理结果, 不是 bug。Phase D 验证过
> negative Pm 工作; positive Pm 数学上同等 (只是 Pe = Pm 平衡点位置不
> 同)。**但 Phase A-D 所有 baseline 都需要 mini 重测**, 因为 Pe 平衡点
> 变了, 30s 零动作 ω-trace 会与 pre-Task 不同。

---

## 1. 影响文件清单

| 文件 | 现状 | 需改 |
|---|---|---|
| `scenarios/kundur/matlab_scripts/compute_kundur_cvs_v3_powerflow.m` | bus 14: `[PV, 1.00, P_ES_each_init, 0]`; 总 load 2734 MW | EDIT (add 248 MW @ bus 14) |
| `scenarios/kundur/simulink_models/build_kundur_cvs_v3.m` | `runtime_consts.LoadStep_amp_bus14 = 0`; topology_variant assert `'15bus_w2_at_bus8'` | EDIT (default 0 → 248e6; topology_variant 加 LS1 标记) |
| `scenarios/kundur/config_simulink.py` | `_load_profile_ic` v3 分支 topology_variant check | EDIT (字符串同步) |
| `probes/kundur/v3_dryrun/probe_5ep_smoke_mcp.m` | identity_ok 检查 topology_variant | EDIT (字符串同步) |
| `env/simulink/kundur_simulink_env.py` | LS1 dispatch: 写 `LoadStep_amp_bus14 = magnitude` (= 248e6) | EDIT (LS1 写 0; 同时考虑 magnitude 参数语义 — 见 §4) |
| `scenarios/kundur/kundur_ic_cvs_v3.json` | bus 14 无 load | REGENERATE (NR run) |
| `scenarios/kundur/simulink_models/kundur_cvs_v3_runtime.mat` | `LoadStep_amp_bus14 = 0` 默认 | REGENERATE (build run, 默认 248e6) |
| `scenarios/kundur/simulink_models/kundur_cvs_v3.slx` | 块结构同 | REBUILD (块不变, 只是 saved-state 刷新) |

> **REVIEW NOTE (1):** 7 个文件改 + 2 个再生 = 与 Task 1 同等 surface,
> 但 NR + env dispatch 是新 surface。env 改最敏感, 因为影响 RL training
> 行为。

---

## 2. Pre-flight

### 2.1 状态确认 + 备份

| Step | Tool | Action |
|---|---|---|
| 2.1.a | `Bash` | 确认 Task 1 verdict 存在 + IC sha = `db974107…` |
| 2.1.b | `Bash` | 备份 5 个文件: build / NR / config / probe / env → `*.pretask2.bak` |
| 2.1.c | `simulink_run_script` (sync) | SHA-256 三个 generated 文件 (.slx / runtime.mat / IC.json) → 记录 pre-Task 2 baseline |
| 2.1.d | `simulink_run_script` (sync) | 读 `runtime.mat.LoadStep_amp_bus14` 确认 = 0 (Task 1 后的状态) |

### 2.2 LS1 dispatch 现状 PRIMARY 验证

**Tool:** `Grep` 在 `env/simulink/kundur_simulink_env.py` 找
`loadstep_paper_bus14` / `LoadStep_amp_bus14` 引用 + `_apply_disturbance_backend`

**目的:** 找到 LS1 dispatch 的精确代码行 (which line writes 248e6 to
which workspace var) + 关联 magnitude 参数语义。

> **REVIEW NOTE (2.2):** 这步 PRIMARY 是 Task 2 关键。env 行为不能盲改,
> 必须先看清 magnitude 参数从哪来 / 写到哪去 / 与 disturbance_type 字符
> 串如何匹配。

---

## 3. NR 脚本 EDIT (第一阶段, 不改 build / env)

### 3.1 Read NR 脚本 bus_data 段

**Tool:** `Read` `compute_kundur_cvs_v3_powerflow.m` line 150-180 (bus_data
区) + line 165-180 (P_ES_each 在 outer iter 中的更新逻辑)

### 3.2 修改 bus 14 schedule

bus 14 当前 `[PV, 1.00, P_ES_each_init, 0]`。

**Target:** bus 14 加 248 MW PQ load offset:
```matlab
P_LS1_LOAD = 2.48;   % 248 MW = 2.48 sys-pu
bus_data(id2idx(14), :) = [PV, 1.00, P_ES_each_init - P_LS1_LOAD, 0];
```

注意: outer iter 内 update P_ES_each 时也要保持 offset:
```matlab
% Old: bus_data(id2idx(14), 3) = P_ES_each;
% New: bus_data(id2idx(14), 3) = P_ES_each - P_LS1_LOAD;
```

> **REVIEW NOTE (3.2):** Outer iter 在多处更新 bus_data 第3列。需要 grep
> NR 脚本确保**所有**更新点同步加 offset, 否则 NR 会算错 bus 14 schedule。

### 3.3 outer iter 残差计算

NR outer iter 通过调整 ESS group P_ES_each 让 G1 hit 700 MW。Bus 14 现有
+248 MW load offset, 总 system load 升, residual 升, ESS 群体须 generate
更多 (Pm0 翻号)。

**预期:** outer iter 自动收敛, P_ES_each 从 -0.369 翻到 ~+0.063 sys-pu。

> **REVIEW NOTE (3.3):** outer iter 无需逻辑改动, 它只看 G1 残差。Bus 14
> load offset 的影响通过 NR Y-bus / power-balance 自动传播。但 P_ES_each
> 的初值可能需要从 -0.369 改到 +0.1 让 outer iter 更快收敛。

### 3.4 P_ES_each 初值调整

**Read** NR script 找 `P_ES_each_init` 定义。如果 = -0.369 (matches Task 1
result), Task 2 后该值不再对 ESS 实际 Pm0 是好初值; 改成 +0.1 (估算
+0.063 的合理初值):
```matlab
P_ES_each_init = +0.1;   % Task 2: ESS group 转 generate 平衡 +248 MW @ bus 14
```

> **REVIEW NOTE (3.4):** Outer iter 通常对初值不敏感 (会迭代收敛), 但
> 把初值挪到正确符号区可避免边界情况。如果 Task 1 的 init 是
> hardcoded `-0.369`, 那这步是必需; 如果是从前一次 NR 读, 则可跳过。

### 3.5 P_load_total 报告更新

NR 脚本最后报 `P_load_total_sys_pu`。Task 2 后需更新预期值: -27.34 →
-29.82 (= 上一行 +2.48 提到的 248 MW LS1 load)。

无需代码改, 只是验证 NR 报告值。

### 3.6 topology_variant 字符串

**Edit** topology_variant: `'v3_paper_kundur_15bus_w2_at_bus8'` →
`'v3_paper_kundur_15bus_w2_at_bus8_ls1_preengaged'`

新字符串明确 LS1 IC 状态变更, 防止与 Task 1 IC 混淆。

---

## 4. env LS1 dispatch EDIT (第二阶段)

### 4.1 Read env disturbance dispatch

**Tool:** `Read` `env/simulink/kundur_simulink_env.py` `_apply_disturbance_backend`
全函数 + 类属性 `DISTURBANCE_TYPES_VALID` (= 在 `config_simulink.py`
里 `KUNDUR_DISTURBANCE_TYPES_VALID`)

**目的:** 看清:
- LS1 dispatch type 字符串 (e.g. `loadstep_paper_bus14`)
- magnitude 参数从哪来 (config 默认 / disturbance bus 字典 / 训练 sample)
- 写哪个 workspace var (`LoadStep_amp_bus14` 还是别的)

### 4.2 LS1 dispatch 反向

旧逻辑 (假设):
```python
if dist_type == 'loadstep_paper_bus14':
    self.bridge.set_workspace_var('LoadStep_amp_bus14', magnitude)  # = 248e6
```

新逻辑:
```python
if dist_type == 'loadstep_paper_bus14':
    # Task 2 (paper LS1 line 993): pre-engaged 248 MW at bus 14;
    # trigger = R disengages = load drops out = freq UP.
    self.bridge.set_workspace_var('LoadStep_amp_bus14', 0.0)
```

### 4.3 magnitude 参数语义重新定义

旧语义: magnitude = "要接入的 MW" (= 248e6 表示接 248 MW)
新语义 LS1 only: magnitude **不使用** (= 触发即让 LoadStep_amp_bus14 = 0,
完全断开 248 MW 全部)

但 random_bus 等 dispatch types 共享 magnitude 参数。需要决定:
- (a) LS1 dispatch type **完全忽略 magnitude**, 总是写 0 (= 完全断开)
- (b) magnitude 改为"剩余 load MW", e.g. magnitude=100e6 表示让 R 调到
     V²/100MW (= 还剩 100 MW load = 部分 trip)
- (c) magnitude 改为"trip MW", magnitude=248e6 表示完全 trip, magnitude<248e6
     表示部分 trip

**推荐: (a) — LS1 = 完全 trip, magnitude 忽略**。理由:
- paper line 993 "sudden load **reduction** of 248 MW" = 完整 248 MW 断开
- 简单, 不引入新语义模糊
- LS2 (step-on) 的 magnitude 仍正常工作 (写 188e6 即接 188 MW)

> **REVIEW NOTE (4.3):** 这是 env API 语义变化点。LS1 dispatch 变成
> "switch action" (开/关) 而非 "magnitude action"。需要在 env doc + RL
> training 注释里明确。

### 4.4 LS2 dispatch 不改

`loadstep_paper_bus15` dispatch 仍写 `LoadStep_amp_bus15 = magnitude` (= 188e6
默认), step-on 方向不变, paper-aligned。

### 4.5 random_bus dispatch 重检

`loadstep_paper_random_bus` 应该随机选 LS1 (trip) 或 LS2 (step-on)。
post-Task 2 两个方向不再同义。需检查 random_bus 是否需要更新逻辑。

> **REVIEW NOTE (4.5):** random_bus 在 paper Sec.IV-A "disturbance position
> and size random" 一致 — paper 训练时同样混合 LS1 / LS2。post-Task 2
> 的 v3 实际上更 paper-aligned, 因为 LS1 真是 trip 不是 step-on 假装。

### 4.6 Phase A++ CCS dispatch 处置

`loadstep_paper_trip_bus14 / loadstep_paper_trip_bus15` dispatch types (Phase
A++ 加的 CCS injection) **保留**, 改为 alternate "negative-load injection"
模式 (零成本, 别影响 RL training default)。**不**进 random_bus 默认池。

---

## 5. Build 脚本 EDIT (第三阶段)

### 5.1 修改 runtime_consts.LoadStep_amp_bus14 默认值

**Read** `build_kundur_cvs_v3.m` 找到 `runtime_consts.LoadStep_amp_bus14 = 0`
赋值行 (Phase A 加的)。

**Edit:** `0` → `248e6`

### 5.2 build script topology_variant assert

**Edit** assert string `'v3_paper_kundur_15bus_w2_at_bus8'` →
`'v3_paper_kundur_15bus_w2_at_bus8_ls1_preengaged'`

### 5.3 config_simulink.py topology_variant check

**Edit** `_load_profile_ic` v3 分支同步字符串。

### 5.4 probe_5ep_smoke_mcp.m identity_ok check

**Edit** 同步字符串。

### 5.5 build script "lines/loads/loadsteps" report 更新

build script 末尾报告字串 (e.g. `RESULT: lines=19, loads=2, ...`) 不变 —
Task 2 不改块结构, 只改 IC 数值。但建议 `RESULT:` 行加一条 LS1 IC 状态
确认:
```matlab
fprintf('RESULT: LS1 pre-engaged: LoadStep_amp_bus14_default=%g W (Task 2)\n', ...
        runtime_consts.LoadStep_amp_bus14);
```

> **REVIEW NOTE (5.5):** 可选, 只为执行日志可读性。

---

## 6. 执行顺序

```text
A. Pre-flight
   A1. 确认 Task 1 PASS, baseline SHA matches `db974107…`
   A2. 备份 5 文件 → .pretask2.bak
   A3. SHA-256 + workspace state 记录
   A4. Read env LS1 dispatch (找代码精确位置)

B. NR script edits
   B1. Read NR script bus_data + outer iter
   B2. Edit bus 14 schedule (load offset)
   B3. Edit outer iter loop (P_ES_each 更新位)
   B4. Edit P_ES_each_init (调正区间)
   B5. Edit topology_variant 字符串

C. topology_variant 同步 (4 处)
   C1. Edit build_kundur_cvs_v3.m assert
   C2. Edit config_simulink.py
   C3. Edit probe_5ep_smoke_mcp.m

D. env edits
   D1. Edit kundur_simulink_env.py LS1 dispatch (写 0 而非 magnitude)
   D2. (检查并 EDIT 如需要) random_bus 选择逻辑
   D3. Verify LS2 dispatch 未变

E. Build script edit
   E1. Edit `runtime_consts.LoadStep_amp_bus14 = 248e6`
   E2. Edit (可选) build report fprintf

F. NR run (async, ~75s)
   F1. simulink_run_script_async compute_kundur_cvs_v3_powerflow
   F2. simulink_poll_script
   F3. Verify converged + closure_ok
   F4. Read new IC json — confirm:
       - topology_variant 新值
       - vsg_pm0_pu 翻号 (~+0.06)
       - P_load_total_sys_pu = -29.82 (= -27.34 + -2.48)
   F5. STOP IF NR fail

G. Build run (async, ~140s)
   G1. simulink_run_script_async build_kundur_cvs_v3
   G2. simulink_poll_script
   G3. Verify build OK + lines=19 + loadsteps=2
   G4. Read new runtime.mat — confirm `LoadStep_amp_bus14 = 248e6`

H. Topology verify
   H1. simulink_get_block_tree (no new blocks expected; struct unchanged)
   H2. simulink_run_script: 验证 base ws `LoadStep_amp_bus14 = 248e6`
   H3. SHA-256 三文件全变

I. Stability sanity
   I1. 30s zero-action with new IC: ESS Pm0 generates, ω stable
       ↓ Phase A++ verdict 期望 max|ω-1| ≈ 1e-4 (与 pre-Task 同 order)
   I2. LS1 trigger probe: env-style write `LoadStep_amp_bus14 = 0` →
       freq UP (paper-faithful)
   I3. LS2 trigger probe: write `LoadStep_amp_bus15 = 188e6` →
       freq DOWN (= LS2 paper-aligned, 验证未误改)
   I4. (optional) Phase A++ CCS path: write `LoadStep_trip_amp_bus14 = 50e6` →
       freq UP (alternate mode 仍 work)

J. Acceptance gate (12 项)
   J 全 PASS → Task 2 完成
   J 任一 fail → §K 回滚

K. Rollback (if needed)
   K1. 恢复 5 文件 from .pretask2.bak
   K2. NR + build 重跑确认 SHA-256 回到 Task 1 baseline

L. Verdict + commit
   L1. 写 results/harness/kundur/cvs_v3_task_2/task_2_verdict.md
   L2. Git tag `task-2-bus14-preengage-2026-04-28`
```

---

## 7. Acceptance gate (12 项)

| # | Gate | 通过判据 |
|---|---|---|
| 1 | NR converged + closure_ok | `converged=true && closure_ok=true && residual<1e-3` |
| 2 | NR 报 `P_load_total_sys_pu` ≈ -29.82 | abs((P_load - (-29.82))) < 0.05 |
| 3 | NR 报 ESS Pm0 sign flipped | `vsg_pm0_pu[i] > 0` for all 4 (sign flip from -0.37 to >0) |
| 4 | NR 报 G1 residual < 1e-6 (G1 hit 700 MW exactly) | 同 Task 1 标准 |
| 5 | Build OK | poll important_lines no ERROR; lines=19; loadsteps=2 (块结构未变) |
| 6 | runtime.mat LoadStep_amp_bus14 默认 = 248e6 | `evalin('base','LoadStep_amp_bus14') == 248e6` |
| 7 | topology_variant 4 处一致 = `'..._ls1_preengaged'` | grep build/NR/factory/probe |
| 8 | SHA-256 三文件全变 | post != pre Task 2 baseline |
| 9 | 30s zero-action stable | max\|ω-1\|·50 < 0.5 Hz; no NaN/Inf |
| 10 | LS1 trigger (env write 0) freq UP | mean(om_finals) > 1.0 (FREQ_UP) |
| 11 | LS2 trigger (env write 188e6) freq DOWN | mean(om_finals) < 1.0 (FREQ_DOWN) |
| 12 | env LS1 dispatch 新代码 import 无 syntax/logic error | python -c "import …" PASS |

**全 12 PASS = Task 2 完成。**

---

## 8. Risk register

| ID | Risk | L | Impact | Mitigation |
|---|---|---|---|---|
| R2-1 | NR 不收敛 (load 增 248 MW shift NR equilibrium 显著) | MED | HIGH | P_ES_each_init 调到 +0.1 (合理符号区); 若仍不收敛, 用 Task 1 IC 作 warm-start; STOP rollback |
| R2-2 | bus 14 schedule outer iter 同步漏改 | MED | HIGH | §3.2 + §3.3 双重 grep 确认所有 P_ES_each update 点都加 offset |
| R2-3 | env LS1 dispatch 反向后 RL training 反应未测试 | LOW | MED | Task 2 不动 RL; 但 RL 训练假设 magnitude > 0 = "扰动量级", 现在 LS1 magnitude 被忽略可能让 SAC actor 困惑; **需 doc 明确** |
| R2-4 | random_bus 后续训练打击平衡破坏 | LOW | MED | post-Task 2 LS1=trip / LS2=step-on 反向, 但物理上方向**对称** (freq UP / DOWN), random 仍合理 |
| R2-5 | Phase A++ CCS path 退役不当 → 用户脚本依赖断 | LOW | LOW | 保留 CCS 块 + workspace var, 仅 default 0; 不主动删 |
| R2-6 | Phase D D-axis verdict 失效 (Pm0 翻号) | HIGH | LOW | Task 2 完成后明示 "Phase D 需重测", 不在 Task 2 内 |
| R2-7 | Pre-Task 2 备份 SHA 偏差 (Task 1 残留改动外漏) | LOW | MED | A3 SHA 必须 = Task 1 verdict 记录值 |
| R2-8 | env 改了但没 re-import → MATLAB engine 缓存旧 disturbance dispatch | LOW | LOW | env 是 Python 不缓存; MATLAB engine 不参与 dispatch 解析 |
| R2-9 | LoadStep_amp_bus14=248e6 时 Series RLC R 数值 (213 Ω) 在 Phasor solver 数值不稳 | LOW | MED | Phase A 已 PRIMARY 验证 R workspace expression Phasor 兼容; 248 MW (=213 Ω) 在 R-tuned 范围内 (Phase B 已扫到 248 MW PASS); 极低风险 |
| R2-10 | NR P_ES_each_init = +0.1 但 outer iter 收敛到 -0.x (= NR 解仍是 absorb 模式而非 generate) | LOW | HIGH | 不应发生 (load 增加时 NR 唯一解需 ESS generate 多), 若发生表明 outer iter 逻辑误解, **STOP 排查** |

---

## 9. STOP conditions

执行中 halt 并提示用户的硬条件:
- NR 不收敛 (residual > 1e-3)
- ESS Pm0 NR 解全部仍 < 0 (= sign flip 失败)
- build 抛异常或 lines/loadsteps 数量异常
- 30s zero-action 任一 NaN/Inf 或 max|ω-1| > 5 Hz (= IC 异常)
- LS1 trigger 后方向反 (freq DOWN 不是 UP)
- 任一 acceptance gate fail

---

## 10. Rollback

5 文件 `.pretask2.bak` 恢复 → 重跑 NR + build → SHA-256 验证 = Task 1
baseline (`db974107…` 等) → 状态完全回到 Task 1 完成时。

```bash
cp scenarios/kundur/matlab_scripts/compute_kundur_cvs_v3_powerflow.m.pretask2.bak scenarios/kundur/matlab_scripts/compute_kundur_cvs_v3_powerflow.m
cp scenarios/kundur/simulink_models/build_kundur_cvs_v3.m.pretask2.bak scenarios/kundur/simulink_models/build_kundur_cvs_v3.m
cp scenarios/kundur/config_simulink.py.pretask2.bak scenarios/kundur/config_simulink.py
cp probes/kundur/v3_dryrun/probe_5ep_smoke_mcp.m.pretask2.bak probes/kundur/v3_dryrun/probe_5ep_smoke_mcp.m
cp env/simulink/kundur_simulink_env.py.pretask2.bak env/simulink/kundur_simulink_env.py
# 然后重跑 NR + build 让 IC json + runtime.mat + .slx 同步回到 Task 1 后状态
```

---

## 11. 估时

| 阶段 | 时间 |
|---|---|
| A Pre-flight | 5 min |
| B NR edits | 10 min |
| C topology_variant 同步 | 5 min |
| D env edits + verify | 15 min |
| E build edits | 5 min |
| F NR run + verify | 3 min |
| G Build run + verify | 4 min |
| H Topology verify | 3 min |
| I Stability sanity (3-4 probes) | 8 min |
| J Acceptance | 3 min |
| L Verdict + commit | 5 min |
| **Total** | **~65 min** |

---

## 12. 不在 Task 2 scope (留 Task 3 / 后续)

- **不改 action range 常量** (DM/DD) — 留 Task 3 (doc only)
- **不改 reward / PHI / SAC / replay buffer / checkpoint / paper_eval**
- **不改 NE39 / v2 / SPS**
- **不改 Phase A++ CCS 块结构** (保留作 alternate)
- **不重测 Phase A-D 全部** — 仅 Task 2 内 mini sanity (gate 9-11);
  full Phase B/C/D 重测留给后续作"post-Task 2 baseline establish"

---

## 13. 输出

| 路径 | 内容 |
|---|---|
| `results/harness/kundur/cvs_v3_task_2/task_2_verdict.md` | 12 acceptance gates 结果 + SHA-256 前后 + NR 报告 (ESS Pm0 sign flip) + 30s/LS1/LS2 probe 结果 + 影响范围声明 |
| Git commit | `feat(kundur-cvs-v3): Task 2 — Bus 14 IC pre-engage 248 MW + LS1 reverse (paper line 993)` |

---

## 14. Self-review (写完整体审)

| 检查项 | 状态 |
|---|---|
| Task 目标清晰 (paper line 993 行号 + 物理修改 + env 反向) | ✓ |
| Task 1 baseline 依赖明确 (SHA = `db974107…`) | ✓ |
| 影响文件全列 (7 个 + 2 个 regenerate) | ✓ |
| 不新增 breaker 块 (复用 Phase A R 机制) — 设计简化 | ✓ |
| ESS Pm0 sign flip 明示 (= 物理结果不是 bug) | ✓ |
| LS2 不动 (paper-aligned 已经是) | ✓ |
| Phase A++ CCS 保留作 alternate | ✓ |
| topology_variant 4 处同步 | ✓ |
| env LS1 dispatch 反向 + magnitude 语义重定义 (a 模式) | ✓ |
| Acceptance gate 12 项 (NR / build / runtime / SHA / 拓扑 / 30s / LS1 / LS2 / Phase A++ / topology / env import) | ✓ |
| Risk register 10 条 + mitigation | ✓ |
| Rollback 单步 cp + 重跑 | ✓ |
| Scope 隔离 (Task 2 不动 Task 3 + RL training) | ✓ |
| 估时合理 (~65 min) | ✓ |

> **FINAL REVIEW** 关键发现:
> 1. **§0.1 复用 R 机制**: 不新增 breaker 块, 工作量从 plan-original 估
>    8h 降到 ~1h。是 plan-writing 过程最大简化。
> 2. **§4.3 magnitude 语义**: LS1 dispatch 后 magnitude 参数被忽略, 这是
>    需要 doc 明确的 API 变化。
> 3. **R2-2 outer iter 同步**: NR 脚本可能在多处 update bus_data 第 3 列,
>    需 grep 确认所有点都加 -P_LS1_LOAD offset, 否则 NR 收敛但解错。
> 4. **R2-10 sign flip 失败**: 极低概率但严重, 需在 NR poll 后 explicit
>    check `vsg_pm0_pu > 0` 才认 PASS。
> 5. **Phase D 重测留给后续**: Task 2 不重 Phase D, 但 verdict 必须明示
>    "Pm0 翻号 → Phase D 验证失效, 需 user 决定是否重测"。
>
> 计划已具备执行级细节。唯一风险点是 NR 收敛 (R2-1, R2-10), 已有 mitigation。
