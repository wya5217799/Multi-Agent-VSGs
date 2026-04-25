# Kundur CVS Phasor — Stage 2 Readiness Plan

**Date:** 2026-04-25
**Branch:** `feature/kundur-cvs-phasor-vsg`
**Type:** READINESS PLAN — 不实施，不进 RL 训练，不动主线模型
**Predecessor:**
- [Stage 1 Handoff](2026-04-25_kundur_cvs_stage1_handoff.md)
- [cvs_design.md](../../docs/design/cvs_design.md)
- [Pre-Flight Verdict](../audits/2026-04-25_cvs_phasor_preflight.md)
- 约束文档（main worktree）`docs/superpowers/plans/2026-04-25-kundur-cvs-rewrite-constraints.md`

---

## TL;DR

Stage 1 已 PASS 全部 P1/P2/P3 + Spike + Pre-Flight Q1/Q2/Q3，技术 unlock 完成。本 readiness plan 把 5 天 P4+ 改造拆成 5 个 Day，每 Day 有明确入/出口、可复现脚本目标、判据；同时把 NE39 baseline 快照规范化，把 IC 升级路径锁死，把 RL 训练 entry 控制在 Gate 3 + 50 ep baseline 之内。

**本 plan 不实施任何上述 Day 任务。** 完成审查后，由用户授权进入 Stage 2 Day 1。

---

## 0. 范围与边界（贯穿 Stage 2 全程）

### 允许改

- `feature/kundur-cvs-phasor-vsg` 分支内的新增模型 / 探针 / IC 文件（**新文件优先**，避免改既有主线）
- `scenarios/kundur/model_profiles/kundur_cvs.json`（新文件）
- `scenarios/kundur/kundur_ic_cvs.json`（新文件，**不覆写** `kundur_ic.json`）
- `scenarios/kundur/simulink_models/build_kundur_cvs.m`（新文件）
- 新建独立 step/warmup `.m`（如 `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m`，**仅** Gate 3 阶段触及；Day 1-4 不修共享层）

### 禁止改

| 项目 | 禁止理由 |
|---|---|
| `scenarios/kundur/kundur_vsg.slx` (legacy ee 主线) | 不属 CVS 路线 |
| `scenarios/kundur/kundur_vsg_sps.slx` (旧 SPS) | 已作废，留作证据 |
| `scenarios/kundur/kundur_ic.json` | 现 ANDES / legacy 路径仍依赖 |
| `scenarios/contract.py::KUNDUR` | single source of truth (约束 H6) |
| `slx_helpers/vsg_bridge/slx_step_and_read.m` / `slx_episode_warmup.m` | 共享层，NE39 也用（约束 H3） |
| `engine/simulink_bridge.py` | Day 1-4 不动；Day 5 仅在 Gate 2 PASS 后加 step_strategy 字段（new field, 不改原字段） |
| `env/simulink/_base.py` / `kundur_simulink_env.py` | 不在 P4 范围 |
| reward / observation / action 公式 (`env/simulink/_base.py::_compute_reward` 等) | 论文复现契约 (约束 H5) |
| `agents/` 任何文件 (SAC / 网络) | 论文复现契约 |
| 训练超参 (`scenarios/kundur/config_simulink.py` LR / BATCH / 等) | 论文复现契约 |
| NE39 任何文件 | 约束 H3 |
| ANDES 路径 | 不在 CVS 范围 |
| 主 worktree governance-review-followups 状态 | 已隔离，不动 |

### 不进入 RL 训练

- Day 1-4 完全无 SAC / replay buffer / 训练入口
- Day 5 只跑 50 ep baseline（**不**是 paper 的 2000 ep 复现），且仅在 Gate 2 PASS 后启动
- Day 5 baseline 必须有显式 early-stop / abort criteria，命中即停

---

## 1. 5 工作日预算拆分

每天产出：脚本 + 模型/数据工件 + verdict 报告 + （可选）commit。

| Day | 目标 | 入口条件 | 出口判据 |
|---|---|---|---|
| **D1** | 真实 Kundur 7-bus CVS 拓扑迁移设计 | Stage 1 P1/P2/P3 PASS（已满足） | 完整 7-bus build_kundur_cvs.m 编译 + 0.5s sim 通过 |
| **D2** | 正式 NR IC 替代手算 IC | D1 PASS | NR IC 喂入 D1 模型 0.5s sim 通过 + 工作点验证 |
| **D3** | 30s zero-action 稳定性 gate（Gate 1）| D2 PASS | 30s zero-action 稳态 + IntD margin + Pe 平衡 |
| **D4** | disturbance sweep gate（Gate 2）| D3 PASS | dist∈{0.05, 0.1, 0.2, 0.3, 0.5} pu，max_freq_dev 与 dist 线性 R²>0.9 |
| **D5** | 50 ep baseline training gate（Gate 3 入口 + stop criteria）| D4 PASS | 50 ep abort criteria 写明，**本 plan 不跑** |

总 budget：5 工作日 ≈ 35-40 小时 effective work；实际 wall-clock 含 NR/sim 跑时取上限。

---

### Day 1 — 真实 Kundur 7-bus CVS 拓扑迁移设计

**目标**：把 P1/P2 的 BUS_left—L_tie—BUS_right 简化拓扑升级为 paper Sec.IV-A 的 4 VSG + inter-area + load 拓扑。

**输入工件**：
- `probes/kundur/gates/build_kundur_cvs_p2.m`（P2 4-VSG swing-eq 闭环模板）
- `scenarios/kundur/simulink_models/build_powerlib_kundur.m`（legacy ee 路线的 4-VSG 拓扑参考，**只读引用拓扑结构，不复制 ee_lib 块**）
- `docs/paper/yang2023-fact-base.md`（Sec.IV-A 物理参数）

**输出工件**：
- `scenarios/kundur/simulink_models/build_kundur_cvs.m`（新文件，4 VSG + 7-bus + 2 area + load + AC inf-bus）
- `probes/kundur/gates/p4_d1_topology_check.py`（编译 + 0.5s 静态 sim probe）
- `quality_reports/gates/2026-04-26_kundur_cvs_p4_d1_topology.md`（verdict）

**判据**：
- ✅ build_kundur_cvs.m 跑完无 error，模型 saved
- ✅ `simulink_compile_diagnostics(mode='update')` 0 errors / 0 warnings
- ✅ `simulink_step_diagnostics(0 → 0.5s)` status=success, 0 errors
- ✅ 全 4 driven CVS 输入都走 RI2C complex 路径（D-CVS-1 + cvs_design.md H2）
- ✅ Source_Type=DC + Initialize=off（cvs_design.md D-CVS-9）
- ✅ inf-bus = AC Voltage Source（cvs_design.md D-CVS-10）
- ✅ 7-bus 拓扑节点与 paper Sec.IV-A Fig 17 对应（手工 cross-check）

**禁止**：
- 不接 swing-eq 信号链（D2 才接）；纯结构验证，CVS 输入用静态 RI2C(constant Vr, constant Vi)
- 不复用 legacy ee_lib 块（CVS Phasor 路线全 powerlib SPS）
- 不改 NE39 / bridge / reward / agent
- 不写 RL 训练相关代码

**失败信号**：
- `复信号不匹配 / Mux 输入端口 N` → 检查所有 CVS 输入是否统一 RI2C complex
- `数据类型不匹配 / int64` → 检查所有 base ws 数值显式 double

---

### Day 2 — 正式 NR IC 替代手算 IC

**目标**：把 P3 手算 NR（`θ_right = asin(2*Pm0*X_tie)`）替换为正式 Newton-Raphson 潮流，生成完整 7-bus IC + 4 VSG 内电势角 δ_i。

**输入工件**：
- D1 模型 `kundur_vsg_cvs.slx`
- `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m`（已存在，legacy 用于 ee 主线）

**输出工件**：
- `scenarios/kundur/matlab_scripts/compute_kundur_cvs_powerflow.m`（**新文件**，**不覆写** legacy；可 fork 自 legacy 但修改输出 schema 适配 CVS IC）
- `scenarios/kundur/kundur_ic_cvs.json`（**新文件**，schema 含 `delta0_vsg_rad[4]`、`Pm0_vsg_pu[4]`、`v_mag_vsg_pu[4]`、`Pe_target_vsg_pu[4]`）
- `probes/kundur/gates/p4_d2_nr_ic_validate.py`（NR IC 喂入 D1 模型，0.5s sim 验证）
- `quality_reports/gates/2026-04-26_kundur_cvs_p4_d2_nr_ic.md`

**IC 验证指标**（4 项必须全 PASS）：
| 指标 | 阈值 | 测量方式 |
|---|---|---|
| Pe ≈ Pm0 | per-agent \|Pe_tail - Pm0\| / Pm0 < 5% | 0.5s sim tail mean |
| ω ≈ 1 | per-agent \|ω_tail_mean - 1\| < 1e-3 | 同上 |
| IntD margin | per-agent \|delta\|max < π/2 - 0.05 (即 <1.521 rad) | 全程 max |
| inter-agent sync | (max ω - min ω over agents) < 1e-3 (在 0.5s 内) | tail mean per agent → spread |

**手算 IC 边界**：
- ✅ **允许**用于 P1/P2/P3 spike 阶段（已完成）
- ❌ **禁止**用于 P4 任何 gate（D1-D5）
- 任何 P4 IC 必须可追溯到 NR 输出 + JSON 校验和

**禁止**：
- 不修改 legacy `compute_kundur_powerflow.m`（保留向后兼容）
- 不覆写 `kundur_ic.json`（新建独立 `kundur_ic_cvs.json`）
- 不接 swing-eq 反馈以外的扰动 / SAC / RL

**失败信号**：
- NR 不收敛（max_mismatch > 1e-5 pu）→ 检查 Y-bus 构造 / Pm 注入设置
- sin_arg = Pm * X / V > 1 → P 太大（需要降 Pm0）或 X 太大（拓扑参数错）
- 任一 IC 验证指标 FAIL → 不进 D3，回到 NR 调试

---

### Day 3 — 30s zero-action 稳定性 gate (Gate 1)

**目标**：约束文档 §6 Gate 1 — 30s zero-action ω 全程稳态，IntD 不漂，Pe 平衡。

**输入工件**：D2 模型 + NR IC

**输出工件**：
- `probes/kundur/gates/p4_d3_gate1_30s_zero_action.py`
- 数据：`results/cvs_gate1/<timestamp>/{omega_ts.npz, delta_ts.npz, Pe_ts.npz}`（仅本分支，**不**进 main）
- `quality_reports/gates/2026-04-26_kundur_cvs_p4_d3_gate1.md`

**Gate 1 判据**（约束文档 §6 Gate 1）：
- ✅ 30s zero-action：4 VSG 全程 ω ∈ [0.999, 1.001] pu
- ✅ IntD 全程 \|delta\| < π/2 - 0.05（不触钳位）
- ✅ Pe 全程在 IC nominal 的 ±5% 内
- ✅ ω clip [0.7, 1.3] 全程不触
- ✅ inter-agent sync (tail 5s window) < 1e-3 pu

**Stop / abort criteria**：
- 任一指标 FAIL → 回到 D2 调 IC 或 D1 调拓扑
- sim 出错（NaN / Inf / early termination）→ 回 D1 检查模型 / 求解器
- 累计 D1+D2+D3 wall-clock > 3 工作日 → 升级为决策门，可能回退到 P1 ANDES paper profile

**禁止**：
- 不接 SAC、不改 reward、不进 RL training
- 不做 disturbance（D4 才做）
- 不调权 / 调超参

---

### Day 4 — disturbance sweep gate (Gate 2)

**目标**：约束文档 §6 Gate 2 — disturbance 阶跃响应线性 + 阻尼正常。

**输入条件**：D3 PASS

**输出工件**：
- `probes/kundur/gates/p4_d4_gate2_dist_sweep.py`
- `results/cvs_gate2/<timestamp>/{trace_per_dist.npz, summary.json}`
- `quality_reports/gates/2026-04-26_kundur_cvs_p4_d4_gate2.md`

**Sweep 范围**：dist_amp ∈ {0.05, 0.1, 0.2, 0.3, 0.5} pu，per amplitude × 3 seeds（共 15 runs，每 run 30s）

**扰动注入路径**（cvs_design.md §2 E5）：
- 通过 base ws 数值（`Pm_step_t`、`Pm_step_amp` 已在 P2/P3 模型支持）
- **不**用 TripLoad / breaker（FR-nontunable，silent ignore，约束 R2）

**Gate 2 判据**（约束文档 §6 Gate 2）：
- ✅ max_freq_dev 与 dist 线性相关 R² > 0.9
- ✅ 0.5 pu 扰动下 max_freq_dev ≤ 5 Hz（远低于 IntW clip 15 Hz）
- ✅ peak/steady ≤ 1.5（过冲 < 50%）
- ✅ settle time ≤ 5s（阻尼回到稳态）
- ✅ 任一 amplitude × seed 不触 ω clip [0.7, 1.3]

**失败判据**：
- R² ≤ 0.9 → 系统非线性 / 振荡未阻尼，怀疑 D 太小或 IC 偏移
- 0.5 pu 下 max_freq_dev > 5 Hz → 物理参数错位（可能 X_line 错 / Pm0 错 / D 错）
- ω 触 clip → 立即停 sweep，记录失败 amplitude，回 D2/D3 调

**日志产物**：
- 每 (amplitude, seed) 一组 (omega_ts, delta_ts, Pe_ts) 时序
- summary.json：{R², max_freq_dev_per_amp, settle_per_amp, clip_hit_count}

**禁止**：
- 不接 SAC、不改 reward、不进 RL training
- 不做 dist > 0.5 pu（约束文档 Gate 2 上限）

---

### Day 5 — 50 ep baseline training gate (Gate 3) — 入口条件 + stop criteria

**目标**：定义 Gate 3 入口/出口/abort/复现条件。**本 plan 不跑 50 ep**，由用户在 D4 PASS 后另行授权启动。

**入口条件**（必须全满足才允许启动 50 ep）：
- ✅ Gate 1 (D3) PASS
- ✅ Gate 2 (D4) PASS
- ✅ NE39 baseline 快照已记录（见 §2）
- ✅ `scenarios/kundur/model_profiles/kundur_cvs.json` 写完（约束文档 S1）
- ✅ bridge.py `step_strategy` 字段加好（**仅加新字段**，不改原字段；约束文档 S4）
- ✅ 新 step/warmup .m: `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m`、`slx_episode_warmup_cvs.m`（独立文件，不改 NE39 共享层）
- ✅ 50 ep baseline 命令已固定 + 显式日志路径
- ✅ 用户显式授权启动训练（command 必须由用户发起，不在 plan 自动跑）

**Baseline scope**：
- 50 ep（不是 2000 ep paper 复现）
- 现有 reward / SAC / hidden 层 / LR 不变
- 仅替换 env 后端为 `kundur_vsg_cvs.slx` profile
- random seed 固定（reproducibility）

**Early stop / abort criteria**（命中任一即停）：
- ω 触 clip [0.7, 1.3] 任一 ep
- max_freq_dev > 12 Hz（约束文档 batch 22 教训）
- IntD 触 ±π/2 任一 step
- sim() crash / NaN / Inf
- r_h share of \|reward\| > 60%（约束文档 batch 22：r_h 占 79.2% 是物理饱和信号）
- 累计 wall-clock > 4 小时仍未完成 50 ep

**Verdict 标准**（50 ep 完整跑完后判定）：
- 后 25 ep avg reward > 前 25 ep（学习信号存在）
- max_freq_dev 全程不触 clip
- r_h share of \|reward\| < 50%
- settled_rate ≥ 60%（最后 10 step ω 在 ±0.1 Hz 内）

**Verdict 三态**：
- **PASS** → 允许进入约束文档 5 天改造的"5-day-baseline"，但仍**不**直接启动 paper 2000 ep 复现
- **CONDITIONAL** → 列明工程问题，不进 2000 ep
- **FAIL** → 回退到 P1 ANDES paper profile / P2 ee_lib 工程修补

**复现条件**：
- seed = 42（固定）
- model 文件 SHA256 → `quality_reports/gates/<date>_kundur_cvs_p4_d5_gate3.md`
- IC json SHA256
- python env 锁（`pip freeze` 输出存档）
- training command verbatim
- 数据存放：`results/sim_kundur/runs/cvs_baseline_<timestamp>/`（**仅**本分支，**不**进 main）

**Metrics 记录**（per-ep）：
- ep_reward, r_f_share, r_h_share, r_d_share
- max_freq_dev, ω_min, ω_max
- max\|delta\|, IntD_clip_hit_count
- settled_rate (last 10 step within ±0.1 Hz)
- wall-clock per ep

**禁止**：
- 不改 reward / agent / 训练超参
- 不跑 > 50 ep
- 不在主 worktree 跑（worktree 隔离，避免污染）
- 不在没有 D4 PASS verdict 的情况下启动

---

## 2. NE39 baseline 快照（**仅 snapshot，不改造**）

### 目标

为约束文档 R1（NE39 路径污染检测）建立 baseline 数值参考。任何 CVS 改造涉及共享层（bridge.py 加 step_strategy 字段时）必须在前后跑 NE39 短跑，比对偏差 > 30% 视为污染回滚。

### 范围（必须严格限定）

- **只读取**当前 NE39 状态，**不改任何 NE39 文件**
- 跑 NE39 现有 train_simulink 短跑，记录数值
- 不改 NE39 配置 / 拓扑 / SAC / reward
- 不试图修复 NE39 已知问题

### 快照内容

`quality_reports/gates/2026-04-26_ne39_baseline_snapshot.md` 必须含：

| 字段 | 内容来源 |
|---|---|
| commit_sha | `git rev-parse HEAD` (main worktree) |
| ne39_model_path | `scenarios/new_england/simulink_models/NE39bus_v2.slx` |
| ne39_config | `scenarios/new_england/config_simulink.py`（关键字段：`DT`, `T_EPISODE`, `STEPS_PER_EPISODE`, `DIST_MIN/MAX`, `PHI_F/H/D`, `phang_feedback_gain`, `init_phang`） |
| ne39_bridge_config | `scenarios/new_england/config_simulink.py::NE39_BRIDGE_CONFIG`（`pe_measurement`, `phase_command_mode`, `pe_vi_scale`, `phase_feedback_gain`, `init_phang`） |
| latest_training_run | 最近一次 100+ ep run 的 `results/sim_ne39/runs/<latest>/training_log.npz` 路径 + reward / max_freq_dev 量级 |
| short_run_3ep | 跑 `python scenarios/new_england/train_simulink.py --mode simulink --episodes 3 --resume none` 取 reward_mean / max_freq_dev_mean / settled_rate |
| 已知问题 | 从 `scenarios/new_england/NOTES.md` 抄录"现在在修"段（不改） |
| 不可触碰范围 | `slx_helpers/vsg_bridge/slx_step_and_read.m` (phang feedback) / `slx_episode_warmup.m` (6-arg path) / `engine/simulink_bridge.py` 现有 phang_feedback 路径 / `scenarios/contract.py::NE39` |
| 污染检测阈值 | reward 量级偏差 > 30% / max_freq_dev 偏差 > 30% / settled_rate 偏差 > 20pp 任一 → 视为 R1 触发，回滚 |

### 执行规则

- 在新分支 `feature/kundur-cvs-phasor-vsg` 上跑（NOT 主 worktree）
- 跑完短跑后**回滚**所有 NE39 改动（应该是 0，因为不改）
- 跑完短跑后**不 commit** results/，仅 commit `quality_reports/gates/2026-04-26_ne39_baseline_snapshot.md`
- 跑完后立即恢复模型 FastRestart=off + base ws 默认（避免污染后续 sim）

### 何时执行

- 在 D5 入口条件检查中**必须先满足**
- 时间节点：D4 PASS 之后、Gate 3 启动之前
- 时长：30-45 min（含模型加载 + 3 ep 跑 + 报告写）

---

## 3. NR IC 替代方案（锁死）

### 强制约束

| 阶段 | IC 来源 | 允许 |
|---|---|---|
| Spike (G3.1-3.3) | 手算 SMIB `asin(Pm0 * X)` | ✅ 已完成 |
| Gate P1 | 静态 Constant Vr/Vi 预设 | ✅ 已完成 |
| Gate P2 | 手算 SMIB | ✅ 已完成 |
| Gate P3 | 手算 NR (P3 文档已写明) | ✅ 已完成 |
| **Day 1+（任何 P4 Gate）** | **正式 NR via `compute_kundur_cvs_powerflow.m`** | **强制** |
| 任何后续训练 | 正式 NR | 强制 |

**手算 IC 在 Day 1 之后任何代码使用 = 视为违规**，必须立即停手并回到 NR 路径。

### IC 验证指标（4 项，per-agent，全 PASS 才放行）

| 指标 | 阈值 | 测量 |
|---|---|---|
| `Pe ≈ Pm0` | \|Pe_tail_mean - Pm0\| / Pm0 < 5% | 0.5s sim tail (last 0.2s) mean |
| `ω ≈ 1` | \|ω_tail_mean - 1\| < 1e-3 | 同上 |
| `IntD margin` | \|delta\|_max < π/2 - 0.05 = 1.521 rad | 全程 max |
| `inter-agent sync` | (max ω - min ω) over 4 agents < 1e-3 | tail mean spread |

### NR 输出 schema (`kundur_ic_cvs.json`)

```json
{
  "schema_version": 1,
  "source": "compute_kundur_cvs_powerflow.m",
  "timestamp": "2026-04-26T<HH:MM:SS>",
  "powerflow": {
    "converged": true,
    "max_mismatch_pu": 1.2e-7,
    "iterations": 4
  },
  "vsg_internal_emf_angle_rad": [δ1, δ2, δ3, δ4],
  "vsg_terminal_voltage_mag_pu": [V1, V2, V3, V4],
  "vsg_terminal_voltage_angle_rad": [θ1, θ2, θ3, θ4],
  "vsg_pm0_pu": [Pm1, Pm2, Pm3, Pm4],
  "vsg_pe_target_pu": [Pe1, Pe2, Pe3, Pe4],
  "bus_voltages": { "<bus_id>": {"v_mag_pu": ..., "v_ang_rad": ...} },
  "x_line_pu": [...],
  "x_tie_pu": [...],
  "physical_invariants_checked": ["sin_arg_in_range", "p_balance_per_bus"]
}
```

### NR 实现入口

- 复用 `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m` 的 NR 内核（Y-bus、迭代、收敛判据）
- 改写输出 schema → `kundur_ic_cvs.json`
- legacy `compute_kundur_powerflow.m` 不动

---

## 4. P4 Gate 1 边界

### 输入

- D1 模型 `kundur_vsg_cvs.slx`（完整 7-bus + 4 driven CVS + AC inf-bus）
- D2 NR IC `kundur_ic_cvs.json`

### 输出

- 30s zero-action sim 通过约束文档 §6 Gate 1 标准
- verdict 报告 + raw timeseries + summary.json

### 严格禁止项

| 禁止项 | 理由 |
|---|---|
| 不接 SAC | RL 训练在 Gate 3 才允许 |
| 不改 reward | 论文复现契约 |
| 不进 RL training | Gate 3 入口条件未满足 |
| 不动 NE39 | 约束 H3 |
| 不改 bridge.py | Day 5 才碰 |
| 不动 contract.py KUNDUR | 约束 H6 |
| 不试 dist 扰动 | Gate 2 范围 |
| 不调 IntW clip 范围 | 物理参数 |
| 不放宽稳态阈值 | 不掩盖根因 |

### 失败回退

- 任一指标 FAIL → 回 D2 调 IC 或 D1 调拓扑
- 累计 D1+D2+D3 wall-clock > 3 工作日 → 决策门，可能回退到 P1/P2 替代

---

## 5. P4 Gate 2 边界

### 启动条件

**仅在 Gate 1 (D3) PASS 后启动**。Gate 1 FAIL → 不允许进入 Gate 2。

### 内容

disturbance sweep：dist_amp ∈ {0.05, 0.1, 0.2, 0.3, 0.5} pu × 3 seeds = 15 runs × 30s

扰动注入：通过 base ws `Pm_step_t` / `Pm_step_amp`（FR-tunable 路径，不用 TripLoad）

### 失败判据

- R² < 0.9 → 非线性振荡 / 阻尼不足
- 0.5 pu 下 max_freq_dev > 5 Hz → 物理参数错位
- 任何 amplitude × seed 触 ω clip [0.7, 1.3] → 立即停 sweep，记录失败点

### 日志产物（必须）

| 文件 | 内容 |
|---|---|
| `results/cvs_gate2/<timestamp>/trace_dist_<amp>_seed<s>.npz` | 每 (amp, seed) 时序 (omega_ts, delta_ts, Pe_ts) |
| `results/cvs_gate2/<timestamp>/summary.json` | {R², max_freq_dev_per_amp, settle_per_amp, clip_hit_count, all_dist_amps, all_seeds} |
| `quality_reports/gates/2026-04-26_kundur_cvs_p4_d4_gate2.md` | verdict + 数值汇总 + 失败点（如有）|

### 严格禁止项

- 不接 SAC、不改 reward、不进 RL training
- 不做 dist > 0.5 pu
- 不超过 5 个 amplitude（约束文档明确范围）

---

## 6. Gate 3 / training baseline 50 ep

### 启动条件

**仅在 Gate 2 (D4) PASS 后启动**。

### 性质

50 ep 是 **baseline**，不是正式 paper 复现训练（paper Sec.IV-A 是 2000 ep）。目的：
- 验证 RL agent 能在新 CVS 后端上正常 step / reward / update
- 探测 ep 级别有无意外（reward 极端值 / sim crash / FR cache stale）
- 不期待收敛，仅期待**学习信号存在**（后 25 ep avg > 前 25 ep）

### Early stop / abort criteria

| 触发 | 行动 |
|---|---|
| ω 触 clip [0.7, 1.3] 任一 ep | 立即停，写 verdict=FAIL |
| max_freq_dev > 12 Hz | 同上 |
| IntD 触 ±π/2 任一 step | 同上 |
| sim() crash / NaN / Inf | 同上 |
| r_h share of \|reward\| > 60% | 同上 (batch 22 教训) |
| 累计 wall-clock > 4 小时仍未完 50 ep | 同上 |

### 50 ep 完成后 verdict 标准

- 后 25 ep avg reward > 前 25 ep
- max_freq_dev 全程不触 clip
- r_h share of \|reward\| < 50%
- settled_rate ≥ 60%

### 复现条件（Gate 3 必须记录）

| 字段 | 来源 |
|---|---|
| seed | 42（固定）|
| model SHA256 | `kundur_vsg_cvs.slx` |
| IC SHA256 | `kundur_ic_cvs.json` |
| python env | `pip freeze` 存档 |
| training command verbatim | 完整命令行 |
| commit SHA at run | `git rev-parse HEAD` (本分支) |
| 数据路径 | `results/sim_kundur/runs/cvs_baseline_<timestamp>/` |

### Per-ep metrics（必须记录）

- ep_reward, r_f_share, r_h_share, r_d_share
- max_freq_dev, ω_min, ω_max
- max\|delta\|, IntD_clip_hit_count
- settled_rate (last 10 step within ±0.1 Hz)
- wall-clock per ep

### 严格禁止项

- 不改 reward 公式 / agent 网络 / 超参
- 不跑 > 50 ep（baseline 性质，不是 production）
- 不在主 worktree 跑（隔离 worktree）
- 不在 D4 PASS verdict 缺失情况下启动
- 不自动启动；必须由用户发起 training command

### Verdict 三态

| Verdict | 含义 | 下一步 |
|---|---|---|
| **PASS** | 学习信号存在 + 数值稳定 | 允许进入约束文档 5 天改造的 5-day-baseline，仍**不**进 paper 2000 ep |
| **CONDITIONAL** | 部分 PASS + 列明工程问题 | 不进 2000 ep，由用户决定下一步 |
| **FAIL** | 任一 abort criteria 命中或 verdict 标准未满足 | 回 P1 ANDES paper profile / P2 ee_lib 工程修补 |

---

## 7. 风险登记 + 缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| D1 7-bus 拓扑构造 bug（节点漏接、phase 错） | 中 | D1 FAIL | 用 MCP `simulink_explore_block` / `simulink_trace_port_connections` 验证连接；与 paper Fig 17 cross-check |
| D2 NR 不收敛 | 低 | D2 FAIL | legacy `compute_kundur_powerflow.m` 已收敛过，结构相同；复用 Y-bus 构造 |
| D3 IntD 漂移大 | 中 | D3 FAIL | 复用 cvs_design.md §3.3 fallback：warmup 期间冻结 IntD（IntD 输入接 0） |
| D4 sweep 非线性 | 中 | D4 FAIL | 检查 D 是否过小（约束文档 D-CVS-6 D=3）；考虑 D=5 试一次（**仅** debug 用，不进主线）|
| Gate 3 50 ep 数值崩 | 中 | D5 FAIL | 缩小 dist 范围至 0.05-0.2 pu；NOT 改 reward / agent |
| NE39 baseline snapshot 时改了文件 | 低 | R1 触发 | 跑前后 `git status` snap；任何 modified 立即回滚 |
| 主 worktree 被污染 | 低 | governance work 受影响 | 隔离 worktree 严格；所有 commit 都在 `.worktrees/kundur-cvs-phasor-vsg/` |
| 累计超 5 工作日 | 中 | 预算超 | D3 wall-clock cutoff (3d cumulative) → 决策门 |

---

## 8. 完成定义

Stage 2 readiness plan 完成 = 本文件存在 + 满足以下：
- ✅ 5 day budget 拆分明确
- ✅ NE39 baseline snapshot 范围 + 内容 + 阈值已定义
- ✅ NR IC 强制 + 验证指标已锁
- ✅ Gate 1/2/3 入口/出口/abort/复现条件已写明
- ✅ 禁止项列表完整
- ✅ 主 worktree governance state 未触动

进入 Stage 2 Day 1 = 用户在本 plan 上批注"approve, start D1"或等价指令。

---

## 9. 不在本 plan 范围

- ❌ 实施任何 D1-D5 任务
- ❌ 跑 NE39 baseline snapshot
- ❌ 跑 NR
- ❌ 改任何 Simulink 主线模型
- ❌ 改 env / bridge / reward / agent
- ❌ 进入 P4 实施
- ❌ 启动 RL 训练
- ❌ 触主 worktree governance state

本 plan **仅是一份组织 + 技术前置文档**，由用户审查后决定是否启动 Stage 2。
