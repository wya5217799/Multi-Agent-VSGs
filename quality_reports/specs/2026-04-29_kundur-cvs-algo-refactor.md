# Requirements Spec: Kundur CVS 算法层重构 (C1 + C4)

**Date:** 2026-04-29
**Status:** APPROVED (用户 2026-04-29 批准 + 3 项 spec 调整)
**Author:** Claude (基于代码现状决定 fuzzy points)
**Approval modifications:**
- M2 改为软目标 ≤30 行 / 硬上限 ≤45 行 / 30-45 行需 verdict 解释 (§4.5)
- byte-level 范围窄化为 §4.6 deterministic oracle (排除 run_id/timestamp/路径/日志顺序)
- C2 trigger 删除 calendar safety net，仅保留 3 条架构漂移触发 (§4.4)
**Plan:** `docs/superpowers/plans/2026-04-29-kundur-cvs-algo-refactor.md`
**Related ADRs:**
- `docs/decisions/2026-04-10-paper-baseline-contract.md` (paper baseline lock)
- `docs/decisions/2026-04-24-kundur-intent-manifest-boundary.md` (intent manifest scope)
- `docs/decisions/2026-04-29-kundur-workspace-var-schema-boundary.md` (P0 输出，待写)

**Dependency:**
- C3 已完成 (commits dcd87f6 / fa44cba / aad5359)
- 工作树 clean (除 untracked) — 验证: `git status --short | grep -v "^??" | wc -l` == 0

---

## 1. 背景与动机

前次架构审查 (`/improve-codebase-architecture`, 2026-04-29) 在 Kundur CVS Simulink 算法层识别 4 个 deepening candidates (C1-C4)，C3 (workspace-var schema) 已落 4 commits。本 spec 覆盖 C1 + C4，C2 (BridgeConfig 判别联合) deferred。

**核心痛点:**
1. `KundurSimulinkEnv._apply_disturbance_backend` 是 240 行的 god method，14 类 disturbance 通过 if/elif 字符串 dispatch，新增类型要改 3 处文件
2. 单一 episode 的 disturbance 通过 4 个独立路径进 env：`_disturbance_type` 私有写、`apply_disturbance(magnitude=...)` 直调、`reset(options=...)` 字典、`KUNDUR_DISTURBANCE_TYPE` env-var
3. `_disturbance_type` 私有字段被 8 处生产代码外部写入 (paper_eval × 5、train × 2、probe × 1)

**目标:** 把 dispatch 抽成 4 个可独立测试的 adapter (C1)，把 4 个 disturbance 入口塌成单一 `Scenario` value object (C4)。

---

## 2. 范围 (Scope)

### 2.1 In Scope

| 文件 | 改动类型 | 阶段 |
|---|---|---|
| `scenarios/kundur/disturbance_protocols.py` | 新建 | P2 |
| `tests/test_disturbance_protocols.py` | 新建 | P2 |
| `env/simulink/kundur_simulink_env.py` | `_apply_disturbance_backend` 收缩 (P2) + `reset` 增加 scenario 参数 (P4a) | P2, P4a |
| `scenarios/kundur/train_simulink.py` | 删除 `_ep_disturbance` closure + 5 处 `_disturbance_type` 写 + step 循环 `apply_disturbance` 调用 | P4b |
| `evaluation/paper_eval.py` | 删除 5 处 `_disturbance_type` 写 + 1 处 `apply_disturbance` 调用，迁移到 Scenario API | P4b |
| `scenarios/kundur/NOTES.md` | 增加 schema + protocol + Scenario VO 三条已知事实 | P0, P5 |
| `CLAUDE.md` | 修改"常见修改点定位"表 | P5 |
| `docs/decisions/2026-04-29-kundur-workspace-var-schema-boundary.md` | 新建 (C3 ADR) | P0 |
| `docs/decisions/2026-04-29-kundur-cvs-disturbance-protocol-and-scenario-vo.md` | 新建 (C1+C4 ADR) | P5 |
| `tests/test_kundur_workspace_vars.py` | 可能需要小幅扩展 (Scenario→Protocol smoke) | P4a |

### 2.2 Out of Scope

| 路径 | 不改原因 |
|---|---|
| `engine/simulink_bridge.py` (warmup/`_warmup_cvs`/step) | C2 deferred 范围 |
| `scenarios/kundur/config_simulink.py` (BridgeConfig + make_bridge_config) | C2 deferred 范围 |
| `scenarios/kundur/simulink_models/build_kundur_cvs_v3.m` | 物理层 |
| `scenarios/kundur/kundur_cvs_v3_runtime.mat` / `.slx` | 物理层 |
| `env/simulink/_base.py` (`_compute_reward`, `_build_obs`) | paper baseline contract |
| `env/simulink/ne39_simulink_env.py` + NE39 训练路径 | 跨场景，C2 范围 |
| `env/andes/` + ANDES/ODE 路径 | 历史遗留 |
| `agents/` (SAC, multi_agent_sac_manager) | 训练算法 |
| `probes/kundur/**` | 调用旧 `apply_disturbance` API 的代码 — 走 DeprecationWarning 兼容 |
| `tests/test_perf_episode_length.py`, `tests/test_fixes.py`, `scripts/profile_one_episode.py` | 同上 |
| `scenarios/new_england/**`, `scenarios/kundur/evaluate_simulink.py` | 独立调用站，DeprecationWarning 路径仍可用 |
| `effective_in_profile` 集合 (workspace_vars schema) | 物理修复才能改 |

### 2.3 Locked Constants (paper baseline contract — 见 `docs/decisions/2026-04-10-paper-baseline-contract.md`)

不允许触碰任何这些值：
- `T_WARMUP`, `PHI_F`, `PHI_H`, `PHI_D`, `DIST_MIN`, `DIST_MAX`
- `KUNDUR_DISTURBANCE_TYPE` 默认值
- `DEFAULT_KUNDUR_MODEL_PROFILE = kundur_cvs_v3`
- `T_EPISODE`, `N_SUBSTEPS`, `STEPS_PER_EPISODE`
- `_compute_reward` 公式 (paper Eq.14-18)
- `_build_obs` 公式 (paper Sec.III-C, Eq.11)
- `DELTA_M_MAX_PER_STEP`, `DELTA_D_MAX_PER_STEP` rate limits
- `OMEGA_SAT_DETECT_HZ`, `TDS_FAIL_PENALTY`

---

## 3. Requirements

### 3.1 MUST (非协商)

| ID | Requirement | Clarity |
|---|---|---|
| M1 | C1 抽取后 `_apply_disturbance_backend` 的字节级 write log 与重构前一致，14 个 type × ≥2 个 sign × 2-3 个 target 共 ≥60 个 case 全部 PASS | CLEAR |
| M2 | C1 完成后 `_apply_disturbance_backend` 函数体目标 ≤ 30 行 (含 SPS legacy 兼容分支)，硬上限 ≤ 45 行；若 30 < 行数 ≤ 45 必须在 P2 verdict 解释合理性 (e.g. SPS legacy 分支必要、注释/类型签名占用) | CLEAR — 见 §4.5 |
| M3 | C4 完成后 `train_simulink.py` 中无 `env._disturbance_type =` 私有写 | CLEAR |
| M4 | C4 完成后 `evaluation/paper_eval.py` 中无 `env._disturbance_type =` 私有写 | CLEAR |
| M5 | C4 完成后 `scenarios/kundur/train_simulink.py` 中 `_ep_disturbance` closure 被删除，episode-level disturbance 通过 `scenario` 参数传入 `env.reset()` | CLEAR |
| M6 | `env.apply_disturbance` 公开 API 在 C4 后**保留可调用**，发出 `DeprecationWarning`，行为等价于内部构造 `Scenario` 后调用新路径 | CLEAR |
| M7 | C1 + C4 全程 `tests/test_kundur_workspace_vars.py` + 新建 `tests/test_disturbance_protocols.py` 全 green | CLEAR |
| M8 | P2 5-ep cold smoke 与 baseline run **byte-level identical on deterministic oracle** (定义见 §4.6)：仅比对 `mean_reward`, `max_freq_dev_hz`, `M[i]`, `D[i]` per step + adapter write log (key/value)，**排除** `run_id`、timestamp、wall-clock、路径、日志顺序、TB scalar 时间轴 | CLEAR — 见 §4.2, §4.6 |
| M9 | P4 5-ep cold smoke 与 baseline run 容差 ≤ ±1% on `mean_reward` (绝对值) 和 `max_freq_dev_hz` (因 P4 统一 `np.random` ↔ `env.np_random`)，比对范围同 §4.6 deterministic oracle 字段 | CLEAR — 见 §4.2 |
| M10 | P4 paper_eval 1-ep smoke 在固定 `Scenario(kind='gen', target=2, magnitude=2.0)` 下与 baseline byte-level identical on deterministic oracle (§4.6)，paper_eval 不依赖 train 端的 `np.random.uniform` | CLEAR |
| M11 | 不动 §2.3 锁定常量 | CLEAR |
| M12 | 不改 §2.2 范围外文件 (允许例外: 文档 .md / NOTES.md / CLAUDE.md) | CLEAR |
| M13 | C3 schema 的 `effective_in_profile` 集合保持不变 (LoadStep 系列在 v3 仍 not-effective) | CLEAR |
| M14 | 每阶段独立 commit，独立可 `git revert` (P2 一个、P4 拆 4a/4b、P0/P1/P3/P5 各一) | CLEAR |
| M15 | 每阶段结束输出 STOP verdict (`results/harness/.../verdict.md`)，含 测试结果 + diff 摘要 + next-stage 进入条件 | CLEAR |

### 3.2 SHOULD (强偏好)

| ID | Requirement | Clarity |
|---|---|---|
| S1 | Adapter 通过 Protocol 定义而非抽象基类 (Python 鸭子类型) | CLEAR |
| S2 | Adapter 接收 RNG 作为 `.apply()` 调用参数 (无状态 adapter) | CLEAR — 见 §4.1 |
| S3 | `DisturbanceTrace` dataclass 记录每次 dispatch 的 (target_label, written_keys, written_values)，用于监控 + 测试断言 | CLEAR |
| S4 | `resolve_disturbance(disturbance_type: str) -> DisturbanceProtocol` 工厂函数集中处理 14 个 string key → adapter 实例的映射 | CLEAR |
| S5 | C4 后 `Scenario` 字段不分裂 (paper_eval 复用 `scenarios/kundur/scenario_loader.py::Scenario`) | CLEAR — 见 §4.4 |
| S6 | C4 触发时间 `step == int(0.5 / DT)` 移到 env 内部，train_simulink step 循环不再含触发逻辑 | CLEAR |
| S7 | P0/P1/P3 仅文档改动，单 commit 干净 | CLEAR |
| S8 | C1 + C4 完成后存在一个 ADR (`2026-04-29-kundur-cvs-disturbance-protocol-and-scenario-vo.md`) 显式记录 C2 deferred 决策与复议触发条件 | CLEAR |

### 3.3 MAY (可选)

| ID | Requirement | Clarity |
|---|---|---|
| Y1 | P2 阶段保留旧 `_apply_disturbance_backend` 的拷贝在 `tests/_disturbance_backend_legacy.py` 作为字节级回归 oracle，P4 完成后删除 | CLEAR |
| Y2 | C1 adapter 类提供 `__repr__` 含 target descriptor，方便日志阅读 | CLEAR |
| Y3 | P4 中提供一个 `migrate_disturbance_type_to_scenario(disturbance_type, magnitude)` helper，给下游 probe 平滑迁移 | CLEAR |
| Y4 | 真 MATLAB 5-ep smoke 由用户决定是否触发 (默认仅 fake bridge 字节级回归) | CLEAR |

---

## 4. 决策日志 (Fuzzy Points 定锚)

### 4.1 Point 1 — Adapter 的 RNG 注入契约 → (a) 显式注入

**现状**: `_apply_disturbance_backend` 直接读 `self.np_random`，共 8 处:
- line 229, 325, 326, 570 (非 dispatch 路径)
- line 862, 872, 971, 1010 (dispatch 路径)

**决策**: Adapter 走方案 (a) — 每次 `.apply()` 调用接收 `rng: np.random.Generator` 参数。

**理由**:
- 无状态 adapter，单测可用 fixed seed 注入，不与 env 实例耦合
- 符合 Python `Protocol` 鸭子类型惯用法 — 方法接收所需依赖
- env 持有 `self.np_random`，每次 dispatch 取 `rng=self.np_random` 传入即可，无破坏性
- 方案 (b) (构造时持引用) 在测试 fixture 重建 adapter 时容易忘记重置 rng；方案 (c) (env 在外面解析 random target) 把 random_bus / random_gen 的逻辑分裂在 env 与 adapter 两端，反而增加耦合

**Protocol 签名**:
```python
class DisturbanceProtocol(Protocol):
    def apply(
        self,
        bridge: SimulinkBridge,
        magnitude_sys_pu: float,
        rng: np.random.Generator,
        t_now: float,
        cfg: BridgeConfig,
    ) -> DisturbanceTrace: ...
```

### 4.2 Point 2 — 5-ep smoke 容差

**现状**:
- `_apply_disturbance_backend` dispatch 路径用 `self.np_random` 调用 0-1 次 (random_bus/gen 才调用)
- `train_simulink.py:_ep_disturbance` closure 用 **module-level** `np.random.uniform` + `np.random.random` (不同 RNG 流，由 `np.random.seed(args.seed)` 在 train 入口播种)

**决策分两阶段**:

**P2 (C1 only)**: byte-level identical for `mean_reward`, `max_freq_dev_hz`, `M[i]`, `D[i]` per step。
- 理由: C1 仅抽取，不改 RNG 调用顺序、次数、源
- 验证手段: 对 14 type × 2 sign × 2 target = ~56 case 跑 fake bridge，比对 write log JSON 字节级
- 真 MATLAB 5-ep smoke 由用户决定是否跑 (Y4)；若跑则 byte-level 同样要求

**P4 (C4)**: 容差 ≤ ±1% on `mean_reward` 与 `max_freq_dev_hz`。
- 理由: C4 把 `train_simulink._ep_disturbance` 用 `np.random` 改成 `env.np_random` (统一 RNG 源)，调用顺序合法变化
- paper_eval 1-ep smoke 仍要 byte-level (paper_eval 不依赖 `np.random`，固定 magnitude/target)
- 若超 ±1%: 排查路径，**不放任**

**Failure mode**:
- P2 byte-level FAIL → 立即定位 RNG order 引入点，**不进入 P3**
- P4 ±1% FAIL → 拉 baseline run 对照，定位是否引入了非预期的 RNG 消费

### 4.3 Point 3 — `apply_disturbance` 公开 API 处理 → (a) DeprecationWarning + 内部转发

**现状 (扫描 2026-04-29)**: 13 个生产调用站使用 `env.apply_disturbance(...)`:
- `evaluation/paper_eval.py:260` (1)
- `scenarios/kundur/train_simulink.py:276, 621` (2 — eval 函数 + train 循环)
- `scenarios/kundur/evaluate_simulink.py:145` (1)
- `probes/kundur/diagnose_*.py` (3 个 probe 文件)
- `probes/kundur/v3_dryrun/*.py` (3 个 probe 文件)
- `scripts/profile_one_episode.py:35` (1)
- `tests/test_perf_episode_length.py` × 2, `tests/test_fixes.py` (monkey-patch only)

**决策**: 走方案 (a):
- 保留 `apply_disturbance(bus_idx=None, magnitude=None)` 公开签名
- 添加 `warnings.warn("apply_disturbance is deprecated; use reset(scenario=...)", DeprecationWarning, stacklevel=2)`
- 内部行为: 用 caller 传入的 `magnitude` (或 `_get_random_magnitude_from_dist_range()` 当 `magnitude=None`) 加上当前 `self._disturbance_type` 派生 `Scenario` 实例，调用 `_dispatch_via_protocol(scenario)`

**理由**:
- 13 个生产调用站直接 raise 会全炸；其中 6 个是 probe (研究产物)，破坏它们违背"重构不改语义"原则
- DeprecationWarning 给一个 release 周期 (= 一次 paper_eval 验收) 让下游迁移
- `train_simulink.py` 在 P4b 阶段主动迁移其 2 处调用 (line 276 eval 函数 + line 621 step 循环)，作为示范

**何时删除 deprecated API**: 待用户在 C2 阶段或更晚显式批准；本 spec 不规定时限。

### 4.4 Point 4 — C2 deferred 复议触发条件

**现状 (扫描 2026-04-29)**: 当前生产代码 `model_name` 分支 = **7 处**:
- `env/simulink/kundur_simulink_env.py:649, 814` (2)
- `scenarios/kundur/train_simulink.py:65, 67` (2 — IC path)
- `scenarios/kundur/config_simulink.py:139, 146, 346` (3)

(不计 `.bak` 文件、`docs/`、`tests/test_harness_registry.py` 测的 `kundur_vsg` 旧 model)

**决策**: C2 复议触发条件 — 仅架构漂移触发 (任一满足):

1. **新分支 trigger**: 生产代码出现第 8+ 个 `if cfg.model_name in (...)` 或 `if profile.model_name == 'kundur_*'` 分支 (排除 `.bak`/`tests`/`docs`)
2. **新 profile trigger**: 添加第 3 个 Kundur profile (例如 `kundur_cvs_v4`、`kundur_phasor_*`)，破坏 v2/v3 二选一
3. **跨场景 trigger**: NE39 也开始引入 `cvs_signal` / `phang_feedback` 类似的双 step_strategy

**为什么不设日历兜底 (calendar safety net)**: 日历触发是弱信号；如果架构没漂移，3 个月回顾本身无产物。本规则仅在出现**具体架构信号**时触发 C2 复议，避免低优 review 噪声。

**记录方式**: 上述 3 条触发条件写入 `docs/decisions/2026-04-29-kundur-cvs-disturbance-protocol-and-scenario-vo.md` 的 "Deferred decisions — C2" 段落。任何满足触发条件的 PR 必须在描述中显式提及"触发 C2 复议"。

### 4.5 M2 行数门控的软/硬阈值理由

**软目标 ≤ 30 行 + 硬上限 ≤ 45 行 + 30 < 行数 ≤ 45 时 verdict 解释。**

**为什么不硬卡 30 行**: 硬限会激励"为达标而拆"的反模式 — 把 SPS legacy 兼容分支强行拆成无意义的 helper、把 docstring/类型签名压缩到难读、为了少 1 行删掉关键注释。这种代码最终更难维护，违背 C1 的本意。

**为什么硬上限 ≤ 45**: 防止退化到 god method。原 god method 是 240 行；C1 之后即便容纳 SPS legacy 分支 + Pm-step CVS path resolve + adapter dispatch + logging，~30 行已绰绰有余。给 15 行 buffer (50% 余量) 处理边缘情况。

**为什么 30 < 行数 ≤ 45 强制解释**: 维持纪律，避免 buffer 被默认占满。verdict 必须列举每行超过 30 的代码段并说明不可压缩的原因 (e.g. "SPS legacy 兼容 if 分支占 8 行，删除会破坏 NE39 间接调用路径")。

**测量方法**: `wc -l` 数函数体行数 (包含 def 行、含空行)，`cloc` 备选 (排除空行)。统一用 `wc -l` 简化判定。

### 4.6 Deterministic Oracle 定义 (P2/P4 byte-level 比对的精确范围)

**byte-level identical on deterministic oracle** 仅指以下字段在重构前后逐字节相同；超出此范围的差异**不计入**通过/失败判定。

**INCLUDED (必须 byte-level 一致)**:
- `mean_reward` per episode (训练 log `episode_rewards[i]`)
- `max_freq_dev_hz` per episode (`physics_summary[i]['max_freq_dev_hz']`)
- `mean_freq_dev_hz` per episode (`physics_summary[i]['mean_freq_dev_hz']`)
- `M[i]`, `D[i]` per step (env.step 后 `info['M']`, `info['D']`)
- `omega[i]` per step (`info['omega']`)
- `P_es[i]` per step (`info['P_es']`)
- `r_f`, `r_h`, `r_d` per episode (`reward_components`)
- adapter write log: 每次 dispatch 写入的 (workspace_var_name, value) 序列 (用于 P2 fake bridge 字节级回归)
- `omega_trace` per episode (`physics_summary[i]['omega_trace']` — 50×N_AGENTS 浮点)

**EXCLUDED (允许差异，不参与判定)**:
- `run_id` (含 timestamp 后缀)
- `started_at` / `finished_at` / `last_updated` 等 ISO timestamp
- wall-clock duration / 总训练时间
- 输出路径 (`results/sim_kundur/runs/<run_id>/...`)
- 日志行顺序 (live.log / stdout / stderr — async writer 顺序非确定)
- TensorBoard scalar 时间轴 (`add_scalar` 调用时刻)
- `monitor.export_csv` / `monitor_state.json` 中的 timestamp 字段
- `kundur_runtime_facts` 中的路径/sha256 (sha256 应当一致，但若环境变量改变则跳过比对)
- DeprecationWarning stderr 输出 (P4 后会出现，oracle 不计)
- `tqdm` 进度条字符串

**比对实现**:
- P2: fake bridge 写日志 → 序列化为 JSON → `diff` 字节级
- P2/P4 真 MATLAB smoke: 训练完成后从 `training_log.json` 提取 INCLUDED 字段 → 序列化为 canonical JSON (sort_keys + 固定 float repr) → `diff`
- P4 paper_eval: `paper_eval` 的 metrics dict 提取 INCLUDED 字段 → canonical JSON → `diff`

**容差例外** (M9): P4 训练 smoke 因 RNG 源统一而合法漂移，`mean_reward` 与 `max_freq_dev_hz` 容差 ≤ ±1%；其他 INCLUDED 字段不强制 (RNG 漂移会扩散到 `omega`/`P_es`/`M`/`D`，无固定容差，作为 noise 接受)。

**Failure mode**:
- INCLUDED 字段在 P2 不一致 → 立即定位 (基本是 RNG 调用顺序错位或 adapter 写入缺漏)
- INCLUDED 字段在 P4 超 ±1% → 排查是否引入了非预期的 RNG 消费 (例如 closure 多次重建)

---

## 5. 验收测试 (Acceptance Tests)

### 5.1 P0 (C3 收尾)
- `pytest tests/test_kundur_workspace_vars.py -v` 全 green
- `grep -nE "apply_workspace_var\\(['\"]"` 在 `env/simulink/` 命中 0 行
- `docs/decisions/2026-04-29-kundur-workspace-var-schema-boundary.md` 存在且含 §1 范围、§2 name-valid vs effective 契约、§3 effective 集合的硬规则
- `scenarios/kundur/NOTES.md` 含一条 "Workspace var schema (workspace_vars.py) 是 Python↔MATLAB 唯一约定层" 已知事实

### 5.2 P2 (C1 实现)
- `pytest tests/test_disturbance_protocols.py -v` 全 green，覆盖率 ≥ 90% (按 `pytest --cov=scenarios.kundur.disturbance_protocols`)
- `pytest tests/test_kundur_workspace_vars.py -v` 仍 green
- 14 个 disturbance type × 2 sign × ≥2 target = ≥56 case 字节级回归 PASS — oracle = `tests/_disturbance_backend_legacy.py` 中保留的旧 god method 拷贝；比对范围 = §4.6 INCLUDED 中的 adapter write log 部分
- `_apply_disturbance_backend` 函数体行数 ≤ 30 (M2 软目标)；如 30 < 行数 ≤ 45 必须在 verdict 解释 (M2)
- (可选 Y4) 真 MATLAB 5-ep cold smoke 在 `disturbance_type=pm_step_proxy_g1`、`pm_step_proxy_random_bus`、`loadstep_paper_random_bus` 三种下，与最近一次 baseline run byte-level identical on §4.6 INCLUDED 字段 (M8)

### 5.3 P4 (C4 实现)
- `pytest tests/` 全 green
- `grep -nE "env\\._disturbance_type\\s*="` 在 `scenarios/kundur/`、`evaluation/` 命中 0 行
- `train_simulink.py` 中无 `_ep_disturbance` 函数定义
- 真 MATLAB 5-ep cold smoke ×2:
  - 模式 1: 随机 disturbance (无 `--scenario-set`)，与 baseline run 容差 ≤ ±1% on `mean_reward` 与 `max_freq_dev_hz` (M9, §4.6 容差例外)
  - 模式 2: `--scenario-set test`，与 baseline run 容差同上
- paper_eval 1-ep smoke 在固定 `Scenario(kind='gen', target=2, magnitude=2.0)` 下与 baseline byte-level identical on §4.6 INCLUDED 字段 (M10)

### 5.4 P5 (文档)
- `docs/decisions/2026-04-29-kundur-cvs-disturbance-protocol-and-scenario-vo.md` 存在
- `CLAUDE.md` 含 "Disturbance dispatch (Kundur CVS) → `scenarios/kundur/disturbance_protocols.py`"、"Scenario VO contract → `scenarios/kundur/scenario_loader.py::Scenario`" 两条
- `scenarios/kundur/NOTES.md` 含三条新已知事实

---

## 6. 风险与回滚

### 6.1 主要风险

| ID | 风险 | 触发条件 | 缓解 |
|---|---|---|---|
| R1 | 14 type → 4 adapter 归属表归错 (例如 LS1 IGNORE magnitude 行为遗失) | P2 字节级回归在 LS1 case 上 FAIL | P1 设计阶段输出归属表，由用户 review；P2 oracle 用旧 god method 拷贝 |
| R2 | C4 改 RNG 源后训练曲线漂移 | P4 5-ep smoke 超 ±1% 容差 | 保留 baseline run；超容差时 git bisect 定位引入点 |
| R3 | DeprecationWarning 在 paper_eval 触发后污染日志 | paper_eval 跑大量 episode 时 stderr 噪声 | 在 paper_eval 顶部加 `warnings.simplefilter('once', DeprecationWarning)` 或 P4b 同步迁移 paper_eval |
| R4 | 13 个 probe 调用站中某个隐式依赖 `env._disturbance_type` 私有字段读取 | 用户跑特定 probe 时 AttributeError | C4 保留 `_disturbance_type` 字段作为只读属性 (`@property`)，由 `Scenario` 派生 |
| R5 | C2 触发条件被遗忘 | 6 个月后又出现 model_name 分支 drift | ADR 中显式记录 4 条触发；`grep "model_name" --include="*.py"` 计数器作为 monitor (可选) |

### 6.2 回滚策略

- 每阶段独立 commit，独立 `git revert <sha>` 干净
- P2 失败 → revert P2 commit，C1 整阶段失败，C3 + C4 仍可独立推进
- P4a 失败 → revert P4a，env API 不变，C4 整阶段失败，C1 仍保留为净增益
- P4b 失败 → revert P4b，env API 已升级但调用站未迁移 (degenerate state)，可单独修；最坏 revert P4a + P4b 回到 C1-完成态
- 极端情况 (整体 C1 + C4 决策错误): revert P0/P1/P2/P3/P4/P5 全部，回到 C3 收口前状态 (hash aad5359)

---

## 7. 估时与门控

| 阶段 | 估时 | Commits | 门控 (摘要) |
|---|---|---|---|
| P0 | 30m | 1 | tests green + grep 0 + ADR exists |
| P1 | 30m | 1 | 风险表 review pass |
| P2 | 1.5h | 1 | 56-case 字节级 PASS + M2 行数门控 |
| P3 | 30m | 1 | API 与 P2 一致 |
| P4a | 1h | 1 | env 单测 + 兼容矩阵 |
| P4b | 1h | 1 | 5-ep smoke ×2 + paper_eval byte-exact |
| P5 | 30m | 1 | 文档 + ADR exists |
| **合计** | **~5h** | **7** | |

---

## 8. 进入条件

- [x] git working tree clean (除 untracked) — 2026-04-29 verified
- [x] C3 commits 已 push (HEAD = aad5359) — verified
- [x] `tests/test_kundur_workspace_vars.py` 当前 green (将由 P0 验证)
- [ ] 用户批准本 spec

---

## 9. 不做 (Negative Scope，重申)

- 不动 §2.3 paper baseline 锁定常量
- 不动 §2.2 out-of-scope 文件 (除允许的 .md 文档)
- 不动 NE39 / ANDES / ODE / SPS legacy 任何路径
- 不动 `bridge.warmup` / `_warmup_cvs` / build_kundur_cvs_v3.m / `runtime.mat` / `.slx`
- 不动 BridgeConfig 50 字段 (C2 范围)
- 不动 `effective_in_profile` 集合 (workspace_vars schema)
- 不改 reward / obs formula
- 不改 SAC / multi_agent_sac_manager
- 不启动任何训练 (smoke = ≤5 ep cold-start，不计入 results/)
- 不 merge 任何 `*.pretask*.bak` 文件
- 不删除 deprecated `apply_disturbance` API (本 spec 范围内)
- 不 raise 在 deprecated API 上 (本 spec 范围内)

---

## 10. 决策审批

请用户批准:
- [ ] §3 Requirements (M1-M15, S1-S8, Y1-Y4)
- [ ] §4 4 个 fuzzy points 的决策与理由
- [ ] §6 回滚策略
- [ ] §7 估时与门控
- [ ] 进入 P0

批准后:
1. 将本 spec 状态从 "AWAITING APPROVAL" 改为 "APPROVED"
2. commit spec
3. 进入 P0
