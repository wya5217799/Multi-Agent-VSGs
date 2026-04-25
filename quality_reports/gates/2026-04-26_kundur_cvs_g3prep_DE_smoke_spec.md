# G3-prep D/E — Kundur CVS 5-Episode Plumbing Smoke Spec

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg` @ `90a0314`
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** SPEC — design + reproducibility lock only. **No code change. No execution.** Awaits user authorisation to run.
**Predecessors:**
- Gate 3 entry plan — `2026-04-26_kundur_cvs_gate3_entry_plan.md` (commit `1143258`)
- D-pre NE39 baseline snapshot — `2026-04-26_ne39_baseline_snapshot.md` (commit `a12189e`)
- G3-prep-A profile JSON — `2026-04-26_kundur_cvs_g3prep_A_verdict.md` (commit `4587f66`)
- G3-prep-B `step_strategy` field — `2026-04-26_kundur_cvs_g3prep_B_verdict.md` (commit `c97cabb`)
- G3-prep-C CVS dispatch + 2 NEW `_cvs.m` — `2026-04-26_kundur_cvs_g3prep_C_verdict.md` (commit `90a0314`)

---

## TL;DR

5 ep 走通 reset / warmup / step / logging / bridge dispatch；**不**主张任何学习信号；
SAC gradient updates 必为 0（5×50 = 250 transitions « `WARMUP_STEPS = 2000`）；
任何 NaN / Inf / ω clip / wall-clock 超限即 hard abort。

**1 条阻塞性 open decision（§7 OD-1）：** `scenarios/kundur/config_simulink.py` 当前不 plumb
`step_strategy='cvs_signal'`，CVS profile 加载后 `BridgeConfig` 仍走 `phang_feedback` →
smoke 会**静默误路由**到 legacy step / warmup。修法：当 `KUNDUR_MODEL_PROFILE` 解析到
`kundur_cvs.json` 时设 `step_strategy='cvs_signal'`（≤ 5 行 additive）。**超出 G3-prep-C 范围，需 D 阶段授权方可改动。**spec 不替用户决定。

---

## 0. 严守边界（任何阶段不可触；与 §7 §8 重复但保留以便快速核对）

| Item | Status |
|---|---|
| `slx_helpers/vsg_bridge/slx_step_and_read.m` / `slx_episode_warmup.m` | UNCHANGED |
| `engine/simulink_bridge.py` 现有 phang_feedback 5/6-arg + 3-arg 路径 | UNCHANGED（仅 cvs_signal 早返回分支已 add，commit `90a0314`）|
| NE39 (`scenarios/new_england/*`, `env/simulink/ne39_*.py`, `env/simulink/_base.py`, NE39 `.slx` × 3) | UNCHANGED |
| legacy Kundur (`build_powerlib_kundur.m`, `build_kundur_sps.m`, `kundur_vsg.slx`, `kundur_vsg_sps.slx`, legacy `kundur_ic.json`, `compute_kundur_powerflow.m`) | UNCHANGED |
| `agents/`, `config.py`, `scenarios/contract.py`, `scenarios/config_simulink_base.py` | UNCHANGED |
| reward / observation / action / SAC 网络 / 超参 | UNCHANGED |
| `BridgeConfig` 字段集合 | UNCHANGED（不加新字段，§7 OD-1 修动作位于 `config_simulink.py` 内）|
| `M0_default=24, D0_default=18, Pm0=0.5, X_v=0.10, X_tie=0.30, X_inf=0.05, Pe_scale=1.0/Sbase` | UNCHANGED |
| D1/D2/D3/D4/D4-rev-B verdict 文件 | UNCHANGED |
| `BridgeConfig.__post_init__` `pe_measurement='vi'` validator | UNCHANGED（§7 OD-2 暂沿用 G3-prep-C placeholder 语义）|
| Gate 3 / SAC / RL / replay-buffer / training entry | NOT INVOKED |

---

## 1. Smoke 范围（5 ep, 不是训练）

### 1.1 验证目标（plumbing-only）

| 子系统 | 期望证明 |
|---|---|
| reset | env 重置→ NR-IC → ω = 1.0, δ = δ₀, Pe ≈ 0.5 pu |
| warmup | `bridge.warmup(0.5)` 走 `cvs_signal` 早返回 → `_warmup_cvs` → `slx_episode_warmup_cvs.m`，无 sim 错误，无 NaN |
| step | `bridge.step(...)` 走 `slx_step_and_read_cvs.m`，9-arg signature 一致，state schema (omega, Pe, rocof, delta, delta_deg) 无缺失 |
| logging | `training_log.json` / `run_meta.json` / 5 ep 物理摘要写入 `results/sim_kundur/runs/cvs_smoke_<timestamp>/`，schema 与 NE39 D-pre 同结构 |
| bridge dispatch | NE39 默认路径 byte-equivalent（额外加 §6.2 NE39 contamination tripwire 复跑确认）|

### 1.2 不验证的（不允许在 spec / verdict / commit message 中暗示）

- ❌ 学习收敛 / policy quality / reward 趋势：5 ep × 50 step = 250 transitions « `WARMUP_STEPS = 2000`，**SAC gradient updates 必为 0**，actor 仍是初始随机策略，`ep_reward` 是 random-action 噪声
- ❌ paper claim（reward / settled_rate / max_freq_dev / inertia 配额）
- ❌ `r_h / r_f / r_d` shares 含义（同上，无意义）
- ❌ 任何 hyperparameter / reward weight / network 结构判断
- ❌ Gate 3 / 50-ep baseline / 2000-ep paper-replication 任何子任务

### 1.3 episode / step / warmup 数

| 设定 | 值 | 来源 |
|---|---|---|
| `--episodes` | **5** | entry plan §3.2 G3-EP-4 default |
| `--resume` | `none` | clean run |
| seed | `42` | 复现 |
| `T_EPISODE` | 10 s | `config_simulink.py` L33（不动） |
| `STEPS_PER_EPISODE` | 50 | `config_simulink.py` L34 |
| `DT` | 0.2 s | `_CONTRACT.dt`（不动）|
| `WARMUP_STEPS` (SAC) | 2000 | `config.py`（不动；本 smoke 必触不到）|
| `BUFFER_SIZE` | 10000 | `config.py`（不动）|
| `T_WARMUP`（每 ep simulink warmup 时长）| 0.5 s | `scenarios/config_simulink_base.py`（不动）|
| reward weights `φ_f, φ_h, φ_d` | `100, 1, 1` | `config.py`（不动）|
| network | 4 × 128 FC | `config.py`（不动）|
| disturbance mode / amp | 沿用 `config_simulink.py` 默认（`Pm_step_amp` build 时 = 0；smoke 不注入额外扰动）| build 默认 |

---

## 2. PASS 条件（必须全部满足）

| # | 条件 | 阈值 | 来源 |
|---|---|---|---|
| P1 | sim / matlab.engine 错误 | 0 | entry plan §3.3 |
| P2 | NaN / Inf 出现于 ω, δ, Pe, reward 任意 trace | 0 | entry plan §3.3 |
| P3 | ω 进入 hard clip [0.7, 1.3] | 0 次 | entry plan §3.3 |
| P4 | `max_freq_dev_hz` 任意 ep | < 12 Hz | readiness §1 D5 batch 22 lesson；entry plan §4 |
| P5 | IntD 触及 ±π/2 | 0 次 | entry plan §3.3 |
| P6 | per-ep wall-clock | ≤ 5 min nominal | entry plan §3.3 G3-EP-5 |
| P7 | bridge dispatch 路由 | 5 ep 全部走 `slx_step_and_read_cvs.m` & `slx_episode_warmup_cvs.m`（§4 验证）| OD-1 一旦解决方可成立 |
| P8 | logging schema | `training_log.json` 含 `physics_summary` 5 项，键集合等于 NE39 D-pre baseline | §3 |
| P9 | NE39 contamination tripwire（§6.2）| `mean(ep_reward)` deviation ≤ 30% & `mean(max_freq_dev_hz)` deviation ≤ 30% & `settled_paper ≥ 0/3` & SAC updates = 0 | D-pre §5 |
| P10 | boundary file SHA-256 | §0 边界文件 SHA-256 与 D-pre §2 完全一致；只允许 `engine/simulink_bridge.py` 在 `aa348711…cd08b27d2` (post-C) | §6.1 |

---

## 3. ABORT 条件（任一触发立即停跑，不重试相同模型）

| 条件 | 触发动作 |
|---|---|
| ω clip 触碰（任意 ep / 任意 step）| stop run, dump traces, do NOT auto-rerun |
| NaN / Inf | stop run, capture stack |
| sim crash / matlab.engine error | stop run, capture MATLAB log |
| per-ep wall-clock > 10 min | stop run，suspect cache / compile pathology |
| reward 任一 step 非有限（`-inf` / `nan`）| stop run |
| IntD ±π/2 | abort 该 ep（mark FAIL），smoke 继续；末尾若 ≥ 1 ep 触发记 ABORT verdict |
| MATLAB shared session 断 | stop run, do NOT silent reconnect |

---

## 4. 诊断（diagnostic-only，记录但不 gating）

| 信号 | 记录 | 不 gating 原因 |
|---|---|---|
| per-ep δ-channel overshoot ratio | yes（沿用 D4-rev-B 计算口径）| diagnostic-only per D4-rev-B verdict |
| `r_h / r_f / r_d` shares | yes | random action，shares 无意义 |
| `ep_reward` 标量 | yes | random action 噪声 |
| `settled_paper` per ep | yes | warmup 期 |
| MATLAB engine wall-clock | yes | 工程性能基线 |

---

## 5. 复现锁（reproducibility lock）

### 5.1 命令（**仅当 OD-1 解决后**方可使用）

```bash
# 必须先在已运行 MCP MATLAB shared session 的 R2025b 实例中
# matlab.engine.shareEngine('mcp_shared')

# 启动 smoke（5 ep）
KUNDUR_MODEL_PROFILE="C:/Users/27443/Desktop/Multi-Agent  VSGs/.worktrees/kundur-cvs-phasor-vsg/scenarios/kundur/model_profiles/kundur_cvs.json" \
"C:/Users/27443/miniconda3/envs/andes_env/python.exe" \
  scenarios/kundur/train_simulink.py \
  --mode simulink \
  --episodes 5 \
  --resume none \
  --seed 42
```

环境约束：
- Python 解释器 **必须**用 `C:/Users/27443/miniconda3/envs/andes_env/python.exe`（系统 python 没 matlab.engine + torch）
- MCP MATLAB session **必须**已 shareEngine
- worktree 必须为 `feature/kundur-cvs-phasor-vsg`，HEAD `90a0314` 或后续未触 §0 边界的 commit

### 5.2 SHA-256 锁（pre-run 验证，与 G3-prep-C verdict §1 一致）

| File | SHA-256 |
|---|---|
| `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m` | `d3f732e31530900bed0a39fb35780ecdcbe687a7850e8ab451ddc126ed1824e0` |
| `slx_helpers/vsg_bridge/slx_episode_warmup_cvs.m` | `87efaa740c92544836afa7b2b5e0cefa0b651f76a1bde5e3d637d080edb5dcfb` |
| `engine/simulink_bridge.py` | `aa348711dd02dc6acb49d5f28b648a397b9121d2e0f3d608ab14841cd08b27d2` |
| `scenarios/kundur/simulink_models/kundur_cvs.slx` | `224c294c8d153202b8f82c70faef8e121e664f2afd7ae2a8a0c0852843e54447` |
| `scenarios/kundur/kundur_ic_cvs.json` | `b5c3e7869181aff618c6d904d5653ef9bca1fd8e9a576eb43e952a833ef0e34b` |
| `scenarios/kundur/model_profiles/kundur_cvs.json` | `ab89e82e62b102c0d1da9284367c22cbe00b8a10940147d4b24d8dd2a0eaf869` |

§0 边界文件（NE39/legacy/shared）SHA-256 锁见 D-pre `2026-04-26_ne39_baseline_snapshot.md` §2.1, §2.2, §2.3，pre-run `sha256sum` 必须 byte-for-byte 一致；任意一项 mismatch → 不启动 smoke、汇报偏差。

### 5.3 输出（gitignored）

- 主日志：`results/sim_kundur/runs/cvs_smoke_<YYYYMMDD_HHMMSS>/`
- 关键文件：`training_log.json`, `run_meta.json`, `run.log`, per-ep `physics_summary` 段
- `pip freeze` 快照：`results/sim_kundur/runs/cvs_smoke_<ts>/pip_freeze.txt`（启动脚本写入；如 train_simulink.py 不自动生成则需 spec verdict 阶段补一行外部命令；不在 spec 阶段决策）

### 5.4 git 状态

- 启动前 `git status --short` 必须 tracked-clean（`results/*` untracked + gitignored 允许）
- HEAD = `90a0314`（或后续未触 §0 边界的 commit；**OD-1 一旦改 `config_simulink.py` 落地，HEAD 前移**）
- `git_dirty` 字段写入 `run_meta.json` 由 train_simulink.py 自带逻辑负责

---

## 6. 验证子流程

### 6.1 Pre-run boundary check

`sha256sum` § 0 + § 5.2 全列文件，比对 D-pre §2 + G3-prep-C §1 锁定值；任何 mismatch 不启动。

### 6.2 NE39 contamination tripwire（与 D-pre §5 / G3-prep-C §4 同口径）

smoke 跑完之后立即做：

```bash
"C:/Users/27443/miniconda3/envs/andes_env/python.exe" \
  scenarios/new_england/train_simulink.py \
  --mode simulink --episodes 3 --resume none
```

| 指标 | D-pre baseline | post-C 已测 (commit `90a0314`) | 阈值 |
|---|---|---|---|
| `mean(ep_reward) over 3 ep` | -905.51 | -797.87 (11.9%) | dev ≤ 30% |
| `mean(max_freq_dev_hz)` | 12.39 | 11.51 (7.1%) | dev ≤ 30% |
| `settled_paper` count | 0/3 | 0/3 | not below 0/3 |
| SAC gradient updates | 0 | 0 | must = 0 |

注：reward 是负数，**deviation = `|post - base| / |base|`**，不要简单 `base*0.7 ≤ post ≤ base*1.3`。

### 6.3 Bridge-dispatch 路由验证（spec 不跑，仅记录验证手段）

在 smoke verdict 阶段（D/E commit），引用 `probes/kundur/gates/g3prep_C_cvs_dispatch_verify.py` 的复跑结果作为单元基线（5/5 PASS, wall-clock 0.94 s, commit `90a0314`），证明 dispatch path 在 boundary scope 内 byte-equivalent。**spec 阶段不需重复跑此 probe**。

---

## 7. Open decisions（spec 不替用户决定）

### OD-1（**阻塞**）— `config_simulink.py` 是否 plumb `step_strategy='cvs_signal'`

**问题**：当前 `scenarios/kundur/config_simulink.py:40-196` 从 `KUNDUR_MODEL_PROFILE` 加载 profile 后构造 `KUNDUR_BRIDGE_CONFIG`，但 **`step_strategy` 字段未注入**，默认走 `phang_feedback`。即使 env var 指向 `kundur_cvs.json`，`bridge.step()` 仍调用 `slx_step_and_read.m`（不是 `_cvs.m`）；`bridge.warmup()` 走 5/6-arg legacy 路径而非 `_warmup_cvs`。

**结果**：smoke 会**静默误路由**，跑出错的拓扑、错的 IC 结构、错的 Pe/ω 读法 —— 表面上没崩，但所有 5 ep 数据无效。

**最小修法（≤ 5 行 additive）**：在 `config_simulink.py:178` 之后加：

```python
step_strategy='cvs_signal' if KUNDUR_MODEL_PROFILE.model_name == 'kundur_cvs' else 'phang_feedback',
```

或等价的显式 if/else。**不修 BridgeConfig 接口（B 已加字段）**，不改 NE39 / shared layer。

**为何不在 spec 替用户做**：
- `config_simulink.py` 不在 G3-prep-C 已授权改动列表
- 改一行也是 **新文件改动 → 新 commit → 新授权 gate**
- spec 阶段的契约就是「不动代码，先汇报」

**3 条选择**（用户决定）：
1. **授权 G3-prep-D-config**：单独走一次 ≤5 行 commit + 单元验证（重新跑 G3-prep-C verification probe，应仍 5/5 PASS；并加一条 NE39 tripwire 3-ep 复跑），再启动 smoke
2. **绕过 config_simulink.py**：写 smoke 专用 launcher（如 `scenarios/kundur/train_simulink_cvs_smoke.py` 或显式 monkey-patch），直接构造 `BridgeConfig(step_strategy='cvs_signal', ...)`；优点 boundary 干净，缺点偏离 train_simulink.py 主入口、不再代表生产路径
3. **延后 smoke**：把 OD-1 留到 50-ep baseline 之前，spec 阶段就此封口

### OD-2 — `pe_measurement='vi'` validator placeholder

G3-prep-C verification probe 用 `vabc_signal="Vabc_unused_{idx}"` / `iabc_signal="Iabc_unused_{idx}"` 绕过 `BridgeConfig.__post_init__` 校验。CVS `.m` 不读这两路信号，但 placeholder 是 probe 局部 hack。

`config_simulink.py` 通过 `KUNDUR_BRIDGE_CONFIG` 已包含 `vabc_signal_template` / `iabc_signal_template`（来自 profile 或 base config），smoke 走 train_simulink.py 主入口大概率不需要 placeholder（profile JSON 内可填合法的 signal name 字符串而 `_cvs.m` 不读）。**spec 阶段不动 validator，OD-2 暂沿用 G3-prep-C 已有 boundary**。如 OD-1 选 path 1 / 2 时 smoke 启动遇到 validator error，再单独提 OD-2-fix。

### OD-3 — `pip freeze` 写入位置

`train_simulink.py` 是否自动 dump `pip_freeze.txt` 到 run dir？若否，spec verdict 阶段需在 launcher 外加一行 `"C:/.../python.exe" -m pip freeze > "$RUN_DIR/pip_freeze.txt"`，或单独 commit 一个 `scripts/dump_pip_freeze.py` 包装。**spec 阶段记开放，verdict 前补**。

### Entry plan §5 G3-EP-1..G3-EP-8 在 D/E 中的归属

| ID | 内容 | spec 是否解决 | 备注 |
|---|---|---|---|
| G3-EP-1 | A run yes/no/when | DONE | A 已 commit `4587f66` |
| G3-EP-2 | B vs C 顺序 | DONE | B `c97cabb` → C `90a0314` |
| G3-EP-3 | NE39 baseline 时机 | DONE | D-pre `a12189e` 在 B/C 前 |
| G3-EP-4 | smoke ep 数 5 vs 10 | **DONE in spec** | §1.3 fixed = 5 |
| G3-EP-5 | per-ep wall-clock 阈值 | **DONE in spec** | §2 P6 = 5 min nominal, §3 = 10 min hard abort |
| G3-EP-6 | IntD ±π/2 abort ep vs run | **DONE in spec** | §3 abort 该 ep, smoke 继续 |
| G3-EP-7 | δ_overshoot diagnostic 触发 | **DONE in spec** | §4 diagnostic-only, 不 gating |
| G3-EP-8 | smoke PASS 后是否自动 50 ep | **DONE in spec** | §8 NO，独立授权 |

---

## 8. 不授权事项（spec 阶段封口）

- ❌ 跑 smoke（OD-1 解决前**绝对**不跑，否则结果无效）
- ❌ 改 `config_simulink.py` / `train_simulink.py` / 任意 `.py` 任意 `.m` 任意 `.slx`
- ❌ 改 BridgeConfig 接口
- ❌ Gate 3 / 50-ep baseline / 2000-ep run
- ❌ NE39 / legacy 任何文件（snapshot 之外的复跑都需独立授权）
- ❌ reward / agent / SAC / network / hyperparameter
- ❌ commit 本 spec（先汇报等用户确认）
- ❌ 主 worktree（`fix/governance-review-followups`）任何动作

---

## 9. 下一步（gated on 用户）

| 选项 | 效果 |
|---|---|
| **commit spec only** | 锁定 spec；smoke 仍未跑；OD-1/2/3 仍需独立决策 |
| **OD-1 决策** + spec 修订 | 选 path 1/2/3；spec §7 OD-1 → DONE；后续可启动 smoke 或封口 |
| **hold** | 文件留 disk，不 commit；用户审 spec 后再决定 |

Gate 3 / SAC / RL 仍 **LOCKED**。本 spec 不启动任何 sim 任何训练。
