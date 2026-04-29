# Plan: Kundur CVS 算法层重构 (C1 + C4，C2 deferred)

**Status:** APPROVED (顺序确认 2026-04-29)
**Date:** 2026-04-29
**Branch:** main
**Scope:** Kundur CVS Simulink 算法层（env + 训练循环 + 调用站）。不动 NE39 / ANDES / ODE / bridge.warmup / .m / .slx / paper baseline contract。

---

## 0. 出发点

前次架构审查（2026-04-29）提出 4 个 deepening candidates：

| ID | 主题 | 状态 |
|---|---|---|
| C1 | DisturbanceProtocol seam — 抽取 240 行 god method | TODO |
| C2 | Bridge-profile 判别联合 — 重构 `BridgeConfig` 50 字段 + 5 处 `model_name` 分支 | DEFERRED |
| C3 | Workspace-var schema — Python↔MATLAB 类型化契约 | **DONE** (commits dcd87f6 / fa44cba / aad5359) |
| C4 | Scenario value object — 收敛 4 个 disturbance 入口 | TODO |

**确认顺序：P0 → C1 → C4 → (C2 推迟)**

理由（C1 先于 C4）：C1 把 dispatch 抽成 4 个独立可测的 adapter；C4 之后只需一行 `Scenario → Protocol` 解析。若 C4 先做，会把 Scenario 接到一个即将删除的 240 行 god method 上，胶水代码注定丢弃。

C2 推迟：跨 NE39，规模独立成项目；等 C1+C4 落地观察一周再决策。

---

## 1. 锁定不动（paper baseline contract）

不允许触碰：
- `T_WARMUP`, `PHI_F`, `PHI_H`, `PHI_D`, `DIST_MIN`, `DIST_MAX`
- `KUNDUR_DISTURBANCE_TYPE` 默认值
- `DEFAULT_KUNDUR_MODEL_PROFILE = kundur_cvs_v3`
- `_compute_reward` 公式（paper Eq.14-18）
- `_build_obs` 公式（paper Sec.III-C, Eq.11）
- `effective_in_profile` 集合（仅靠物理修复推进，重构不动）
- `bridge.warmup` / `_warmup_cvs` / build_kundur_cvs_v3.m / runtime.mat

---

## 2. 阶段计划

### P0 — C3 完整收口（轻量验收 + 文档）

**实际状态发现**：env 里 25 处 `apply_workspace_var` 调用站**全部**已迁移到 `self._ws(...)`（C3a 已完成的工作比假设更彻底）。所以 P0 不再是迁移代码，而是**收尾**。

**Scope:**
- 跑 `pytest tests/test_kundur_workspace_vars.py -v` 确认全 green
- `grep -nE "apply_workspace_var\\(['\"]"` 在 `env/simulink/` 下应返回 0 行（验证无遗漏 bare-string）
- 更新 `scenarios/kundur/NOTES.md`：增加 "Workspace var schema 是 Python↔MATLAB 唯一约定层" 条目
- 新 ADR：`docs/decisions/2026-04-29-kundur-workspace-var-schema-boundary.md`
  - 记录 C3 的范围边界（覆盖 env，不覆盖 bridge.warmup / NE39 / SPS）
  - 记录 name-valid vs effective 的契约语义
  - 记录"effective 集合靠物理修复推进"的硬规则

**不动：** 任何代码。

**估时：** 30 min。**Commits:** 1 个（仅文档）。

**门控：** `pytest tests/test_kundur_workspace_vars.py` green + grep 0 命中。

---

### P1 — C1 设计 (no-code)

**目标：** 把 14 类 disturbance type 映射到 4 个 protocol adapter，写出契约表，**先不写代码**。

**产物：** `docs/superpowers/plans/2026-04-29-c1-disturbance-protocol-design.md`

必须包含：
1. **14 type → 4 adapter 归属表**：
   | type | adapter | workspace key | sign | magnitude semantic | other-family silenced |
   |---|---|---|---|---|---|
   | pm_step_proxy_bus7 | EssPmStepProxy | PM_STEP_AMP[0] | signed | divided by n_targets | PMG zeroed |
   | pm_step_proxy_bus9 | EssPmStepProxy | PM_STEP_AMP[3] | signed | divided by n_targets | PMG zeroed |
   | pm_step_single_vsg | EssPmStepProxy | PM_STEP_AMP[DISTURBANCE_VSG_INDICES] | signed | full | PMG zeroed |
   | pm_step_proxy_random_bus | EssPmStepProxy (random target) | PM_STEP_AMP[0\|3] | signed | full | PMG zeroed |
   | pm_step_proxy_g1/g2/g3 | SgPmgStepProxy | PMG_STEP_AMP[g] | signed | full (sys-pu) | ESS PM zeroed |
   | pm_step_proxy_random_gen | SgPmgStepProxy (random) | PMG_STEP_AMP[1\|2\|3] | signed | full | ESS PM zeroed |
   | loadstep_paper_bus14 | LoadStepRBranch | LOAD_STEP_AMP[14] | n/a | **IGNORED** (always 248MW trip) | PM + PMG zeroed |
   | loadstep_paper_bus15 | LoadStepRBranch | LOAD_STEP_AMP[15] | n/a | abs(magnitude) × Sbase | PM + PMG zeroed |
   | loadstep_paper_random_bus | LoadStepRBranch (random) | both | n/a | per-bus | PM + PMG zeroed |
   | loadstep_paper_trip_bus14/15 | LoadStepCcsInjection | LOAD_STEP_TRIP_AMP[bus] | n/a | abs × Sbase | PM + PMG zeroed |
   | loadstep_paper_trip_random_bus | LoadStepCcsInjection (random) | both | n/a | per-bus | PM + PMG zeroed |

2. **Protocol 接口签名（候选）**：
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
   `DisturbanceTrace` 是 dataclass，记录 (target_label, written_keys, written_values)，给监控/日志用。

3. **Adapter 内部状态**（构造参数）：
   - `EssPmStepProxy(target_indices: tuple[int, ...] | "random_bus" | "single_vsg")`
   - `SgPmgStepProxy(target_g: int | "random")`
   - `LoadStepRBranch(target_bus: int | "random")`
   - `LoadStepCcsInjection(target_bus: int | "random")`

4. **Resolver**: 14 string keys → adapter instance，存为 module-level 字典或工厂函数。

5. **风险表**：
   - LS1 IGNORE magnitude 行为是隐性的（god method 注释里），新 adapter 必须显式记录
   - `random_*` 类型的 RNG 来源（必须用 env 传入的 `np_random`，不能 `np.random` 模块全局）
   - `_ws(..., require_effective=True)` 何时打开：仅 LoadStep 系列在物理修复前保持 `True`
   - "silence others" 责任：哪个 adapter 负责清零非自家 family，必须保留 god method 现有语义

**门控：** 风险表与 `scenarios/kundur/NOTES.md §"2026-04-29 Eval 协议偏差"` 对账无矛盾；表格被你 review 通过后才进 P2。

**估时：** 30 min。**Commits:** 1（仅文档）。

---

### P2 — C1 实现

**Scope:**
- 新文件：`scenarios/kundur/disturbance_protocols.py`
  - `DisturbanceProtocol` Protocol
  - `DisturbanceTrace` dataclass
  - 4 个 adapter class（含上面的 random / single 子情况）
  - `resolve_disturbance(disturbance_type: str, ...) -> DisturbanceProtocol` 工厂
- 改 `env/simulink/kundur_simulink_env.py`：
  - `_apply_disturbance_backend` 收缩为 ~10 行：分支 SPS/legacy → CVS path → resolve protocol → `protocol.apply(...)`
  - `_disturbance_type` 字段保留（C4 才动）
  - `DISTURBANCE_VSG_INDICES` class attr 仍由 EssPmStepProxy 在 single_vsg 模式下读取
- 新文件：`tests/test_disturbance_protocols.py`
  - Fake `Bridge` 记录每次 `apply_workspace_var` 调用
  - 14 个参数化测试：每种 disturbance_type 在 v3 profile 下的 baseline write log（key + value）字节级对照
  - 显式断言：LS1 IGNORE magnitude；`require_effective=True` 在 LoadStep 路径生效；`silence others` 集合
  - Adapter 单测：sign 处理、target indices 解析、RNG 注入

**不动：** bridge / warmup / .m / .slx / config / SAC / reward / paper_eval / NE39 / train_simulink.py。

**门控：**
1. `pytest tests/test_disturbance_protocols.py -v` 全 green
2. `pytest tests/test_kundur_workspace_vars.py -v` 仍 green（无回归）
3. **行为字节级回归**：用 fake bridge 跑旧 god method（保留一份未删除的 `_apply_disturbance_backend_legacy` 在测试 fixture 里）vs 新 adapter，写日志逐字节对比。14 type × 2 sign × 多个 target = ~60 case 全部 PASS
4. （可选，由你决定）5-ep cold smoke 真 MATLAB：跑 `disturbance_type=pm_step_proxy_g1` + `disturbance_type=loadstep_paper_random_bus`，看 reward / freq_dev 与 baseline run 一致

**估时：** 1.5 h。**Commits:** 1 个（含新文件 + env 收缩 + 测试）。

**STOP verdict（必须写）：** 新 adapter 的契约边界（write what / silence what / IGNORE magnitude / require_effective），与 god method 的差异（应当为 0）。

---

### P3 — C4 设计 (no-code)

**目标：** 定义 `Scenario` 如何成为 env 的一等输入，**先不写代码**。

**产物：** `docs/superpowers/plans/2026-04-29-c4-scenario-vo-design.md`

必须包含：
1. **新 env API**：
   ```python
   def reset(
       self,
       *,
       seed: Optional[int] = None,
       scenario: Optional[Scenario] = None,
       options: Optional[dict] = None,  # 兼容 Gymnasium 调用方
   ) -> Tuple[np.ndarray, dict]: ...
   ```
   - `scenario` 优先级 > `options['disturbance_magnitude']` > 随机
   - 内部存 `self._episode_scenario`
2. **触发时间下沉**：`step == int(0.5 / DT)` 移到 `step()` 内部，不再由 train loop 调用
3. **`apply_disturbance` 公开 API 处理**：
   - 决定 A：保留作 public，发 `DeprecationWarning`，仍能跑（下游 probe 可能调用）
   - 决定 B：直接 raise，强迫所有 caller 走 Scenario API
   - **建议 A**（保留兼容，给一个 release 周期）
4. **`_disturbance_type` 私有字段处理**：仍存在，但仅被 `_resolve_protocol(scenario)` 派生；不再允许外部直接赋值（加 `__slots__` 或 `@property` 拦截）
5. **调用站迁移表**：

   | file | 旧 | 新 |
   |---|---|---|
   | `train_simulink.py:474-486` | `_ep_disturbance` closure 返回 `(mag, type_override)` | 返回 `Scenario` 对象 |
   | `train_simulink.py:491-494` | `env._disturbance_type = ...; env.reset(options=...)` | `env.reset(scenario=scenario)` |
   | `train_simulink.py:597-600` | 同上（每 episode 头部） | 同上 |
   | `train_simulink.py:619-621` | `env.apply_disturbance(magnitude=dist_mag)` 在 step 循环里 | **删除**（env.step 内部触发） |
   | `evaluation/paper_eval.py` | （扫描后填表） | （同上） |
6. **Scenario 字段扩展决策**：当前 `scenario_loader.Scenario` 只覆盖 train 用的随机 disturbance，paper_eval 用的固定 disturbance 是否走同一字段族？是 → 一致；不是 → 加 `EvalScenario` 类。
   **建议**：复用现有 `Scenario`，paper_eval 内部构造一个固定 `Scenario(kind='gen', target=2, magnitude=2.0)` 即可，不分裂类层级。

**门控：** API 设计与 P2 实现的 `resolve_disturbance` 互相对得上（`Scenario → disturbance_type str → Protocol` 链路一致）。

**估时：** 30 min。**Commits:** 1（仅文档）。

---

### P4 — C4 实现

**两个 commit 拆分：**

**Commit 4a — env API 改造**：
- 改 `env/simulink/kundur_simulink_env.py`：
  - `reset` 签名增加 `scenario` 参数
  - 内部存 `_episode_scenario`，从中派生 `_disturbance_type` + 触发时的 `magnitude`
  - `step()` 内检测 `step == int(0.5 / DT)` → 调用内部 `_trigger_episode_disturbance()`
  - `apply_disturbance` 保留 + `DeprecationWarning`
- 测试：扩展 `tests/test_disturbance_protocols.py` 增加 Scenario→Protocol 链路 smoke

**Commit 4b — 调用站迁移**：
- 改 `scenarios/kundur/train_simulink.py`：
  - 删除 `_ep_disturbance` closure
  - 删除 `env._disturbance_type = _dtype_override`（5 处）
  - 删除 step 循环里的 `env.apply_disturbance(magnitude=dist_mag)`
  - 改用 `scenario = SCENARIO_SET.scenarios[ep % n] if ... else build_random_scenario(rng); env.reset(scenario=scenario)`
- 改 `evaluation/paper_eval.py`：同步迁移
- 验证 `tests/test_kundur_workspace_vars.py` + `tests/test_disturbance_protocols.py` 仍 green

**门控：**
1. 5-ep cold smoke ×2：随机模式 + scenario_set 模式，reward / freq_dev 与最近一次 baseline run 一致（容差 ±5%，因 RNG 种子链路可能微变；若超容差需排查 RNG 注入路径）
2. `paper_eval` 1-ep smoke：固定 `Scenario(kind='gen', target=2, magnitude=2.0)`，metrics 与 baseline 字节级一致
3. `monitor` 路径（`events.jsonl`, `training_status.json`）字段不变
4. `grep -n "_disturbance_type\\s*=" scenarios/kundur/ evaluation/` 应无剩余赋值（除 env 内部派生）

**估时：** 2 h。**Commits:** 2 个。

**STOP verdict（必须写）：** Scenario API 的 backward compat 矩阵，确认 paper_eval 与 train 共用同一 Scenario 路径无歧义。

---

### P5 — 文档 + 回顾

**Scope:**
- 更新 `scenarios/kundur/NOTES.md` 已知事实：
  - "Disturbance dispatch via `disturbance_protocols.py` adapter layer"
  - "Scenario VO 是 episode-level 唯一入口"
- 更新 `CLAUDE.md` 常见修改点定位表：
  - 增加 "Disturbance dispatch (Kundur CVS) → `scenarios/kundur/disturbance_protocols.py`"
  - 增加 "Scenario VO contract → `scenarios/kundur/scenario_loader.py::Scenario`"
- 新 ADR：`docs/decisions/2026-04-29-kundur-cvs-disturbance-protocol-and-scenario-vo.md`
  - 记录 C1+C4 的契约
  - 记录 C2 deferred 的原因（NE39 跨场景 + 50 字段 BridgeConfig 重构）
  - 记录推迟决策的复议条件（如：再次出现 `model_name` 分支 drift bug → 触发 C2）

**估时：** 30 min。**Commits:** 1。

---

## 3. 总览

| 阶段 | 估时 | Commits | 改动文件 | 门控 |
|---|---|---|---|---|
| P0 | 30m | 1 | NOTES.md + 1 ADR | tests green + grep 0 |
| P1 | 30m | 1 | 1 plan doc | 风险表 review |
| P2 | 1.5h | 1 | disturbance_protocols.py + env shrink + 1 test file | 60-case fake-bridge 字节级 |
| P3 | 30m | 1 | 1 plan doc | API 与 P2 一致 |
| P4 | 2h | 2 | env API + train + paper_eval + tests | 5-ep smoke ×2 + paper_eval 1-ep |
| P5 | 30m | 1 | NOTES + CLAUDE.md + 1 ADR | — |
| **合计** | **~5h** | **7** | | |

每个 commit 独立可 `git revert`。

---

## 4. 不做（明确范围外）

- 不动 NE39 / ANDES / ODE 任何路径
- 不动 `bridge.warmup` / `_warmup_cvs` / build_kundur_cvs_v3.m / kundur_cvs_v3_runtime.mat
- 不动 `BridgeConfig` 字段（C2 范围）
- 不改 paper baseline contract（见 §1）
- 不改 reward formula（_compute_reward）
- 不改 obs formula（_build_obs）
- 不改 SAC agent / multi_agent_sac_manager
- 不启动训练（5-ep smoke = cold-start 50 step × 4 agent，不计入 results/）
- 不 merge `*.pretask*.bak` 临时备份文件
- 不动 `effective_in_profile` 集合（物理修复才能改）

---

## 5. 风险与回滚

**主要风险：**
1. C1 的 14 type → 4 adapter 归属表归错 → P1 风险表 review 拦截
2. C4 的触发时间下沉改变 RNG 调用顺序 → 5-ep smoke 的容差测试拦截；若超容差需排查
3. paper_eval 的 Scenario 路径与 train 不一致 → P4 commit 4b 的 paper_eval 1-ep smoke 拦截

**回滚策略：**
- 每阶段独立 commit，独立可 `git revert <sha>`
- 若 P2 字节级回归失败，保留 god method legacy 拷贝在 fixture 里直到 P4 完成
- 若 P4 commit 4a 失败（API 改造），revert 4a，C4 整阶段终止；C1 (P2) 仍保留为净增益

---

## 6. 进入条件

进入本计划要求：
- [ ] git working tree clean（仅 untracked 允许）— 当前满足
- [ ] C3 4 个 commit 已 push（aad5359 是 HEAD）— 当前满足
- [ ] `tests/test_kundur_workspace_vars.py` green — P0 验证

---

**等待用户授权进入 P0。** P0 是文档收尾 + 测试验证，无代码改动。
