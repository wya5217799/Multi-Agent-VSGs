# Kundur Pe 观测契约与 VSG_P0 真源修复计划

**日期**: 2026-04-18
**场景**: Kundur Simulink 主线（`kundur_vsg.slx` + `train_simulink.py`）
**作用域**: Paper Track — Kundur 训练路径；不含 NE39；不含 KundurStandaloneEnv（ODE 后端）
**状态**: Phase 1 ✅ (commit `ce9acc5`) | Phase 2 ✅ (commit `fa23a6f`) | Phase 3-4 待执行 | Phase 5 ✅ phAng 修复 (commit `1ef852e`) | Phase 5b 🔄 B3 ✅ NR 潮流 | B4 ✅ 重建完成 | B5 ❌ Phase 3 仍 FAIL (T_WARMUP 未生效，delta=-90° 触限)

---

## 1. 背景

### 1.1 症状
Kundur Simulink 训练连续三轮在 500 ep 后 `settled_rate=0`、`mean_reward ≈ -313~-392`。`omega_saturated` 从第 0 步即打满 ±15 Hz。

### 1.2 已排除的诊断方向（见 `scenarios/kundur/NOTES.md`）
- `DIST_MAX 3.0→1.5`：单独无效
- 删除 `omega_unstable` 早停：单独无效
- M/D rate limiting：单独无效

上述均为治症状，未触及根因。

### 1.3 本次识别的根因（两个并列契约错误）

**契约错误 1：Pe 观测语义错位**
- 模型内部：`PSens_ES* → PS2S → PeGain_ES*(1/VSG_SN) → VSG port 5`，swing 方程吃**真实电功率**
- Python 训练侧：`state.Pe` 通过 `pe_measurement='pout'` 读 `P_out_ES* = P_ref − D·Δω`，是 **swing 方程输出**，不是真实注入
- 后果：`obs[:,0] = _P_es/NORM_P` 每步都是失真量；critic/policy 基于失真观测学习；ω 饱和时观测反而"看似正常"，对真实偏差可辨识性显著下降

**契约错误 2：`VSG_P0` 三处分叉（值 + 形状 + 单位）**

| 位置 | 值 | 形状 | 单位 |
|---|---|---|---|
| [build_powerlib_kundur.m:115](../../../scenarios/kundur/simulink_models/build_powerlib_kundur.m) | `[1.8725, 1.8419, 1.7888, 1.9154]` | 4 元向量 | VSG-base pu |
| [config_simulink.py:69](../../../scenarios/kundur/config_simulink.py) | `1.87` | 标量 | VSG-base pu |
| [kundur_simulink_env.py:65](../../../env/simulink/kundur_simulink_env.py) | `0.5` | 标量 | VSG-base pu（reset）；运行中被 `state.Pe`（system-base pu）覆盖 |

reset 第 0 帧 `obs[:,0]` 用的是 VSG-base `0.5`，step 中是 system-base；**口径都踩错**。

### 1.4 本次**不**处理的问题
- 阻抗修复（commit `216d8b9`）后的物理 IC 重标定 — **归属 Phase 5**，仅在契约修完后物理仍漂时启动
- `KundurStandaloneEnv` 的 `_P_mech = 0.5`（ODE 后端）— 留 TODO
- NE39 路径 — 不受影响

---

## 2. 最终契约（已拍板，不再讨论）

### 2.1 信号路径
- 训练功率观测 = **`PeGain_ES*` 输出**（= 真正送入 VSG port 5 的标量，单位 VSG-base pu）
- 在 build 脚本中新增 `ToWorkspace` 日志，信号名 **`PeFb_ES{idx}`**
- `slx_step_and_read.m` 新增 `feedback` measurement mode，**唯一一处**做 VSG-base→system-base 换算
- `P_out_ES*` 保留但降级为 debug-only，不再参与训练观测
- Kundur 训练主线 `pe_measurement='feedback'`；`pout` 禁令**放在场景配置层断言**，不放进 shared engine

### 2.2 单位契约
- 模型内部（port 5 / `PeFb_ES*`）：**VSG-base pu**
- Python 侧（`state.Pe` / `_P_es` / `obs[:,0]` / `info["P_es"]` / 训练统计）：统一 **system-base pu**
- 换算点唯一：`slx_step_and_read.m` 的 `feedback` 分支（`state.Pe = PeFb × VSG_SN/SBASE`）
- JSON canonical source 只保留 VSG-base pu 一份真值；system-base 由读取端派生

### 2.3 Canonical source
- 文件：`scenarios/kundur/kundur_ic.json`（首次落地即最终名，不走 `*_seed → final` 重命名）
- 入口：
  - Python：`scenarios/kundur/kundur_ic.py`（frozen dataclass + 校验）
  - MATLAB：`slx_helpers/slx_load_kundur_ic.m`（struct 校验）
- 三个读取点（build / config / env reset）**禁止直写 `jsondecode`**
- Python loader 保持 **base-agnostic**：不 import `config_simulink.py`；所有 VSG-base→system-base 换算均由调用方显式传入 `vsg_sn_mva` / `sbase_mva`
- `source_hash` 语义钉死：`sha256:<hex>`，表示"上游来源工件"的 hash
  - Phase 1：hash legacy source 字符串 `"build_powerlib_kundur.m:VSG_P0=[1.8725,1.8419,1.7888,1.9154]"`
  - Phase 5：切换绑生成器/标定器输出工件 hash（字段名不变，语义连续）

### 2.4 形状
- `_P_es` reset 初值：**4 元 per-agent 向量**（system-base），从 canonical source 派生
- `pe0_default_vsg`：从标量放宽为 `float | Sequence[float]`；**所有实际使用点**（warmup 写 `Pe_ES{i}`、seed `_Pe_prev`）都要跟进

### 2.5 分层纪律
- `engine/simulink_bridge.py` 只做结构校验（`feedback` 模式必带 `pe_feedback_signal`、`pe0_default_vsg` 长度匹配 `n_agents`）
- 场景专属断言（Kundur 主线禁 `pout`）放在 `scenarios/kundur/config_simulink.py` 或 `scenarios/kundur/train_simulink.py` 入口

### 2.6 作用域边界
- `KundurStandaloneEnv._P_mech = 0.5` 不动
- TODO 落三处：
  - [kundur_simulink_env.py:396](../../../env/simulink/kundur_simulink_env.py)（`_P_mech` 初始化附近）
  - [kundur_simulink_env.py:475](../../../env/simulink/kundur_simulink_env.py)（reset 中 `_P_mech` 附近）
  - [scenarios/kundur/NOTES.md](../../../scenarios/kundur/NOTES.md)"已知事实"段

---

## 3. Phase 1 —— 原子提交实施清单 ✅ 完成（commit `ce9acc5`）

**目标**：收敛 Pe 观测契约 + VSG_P0 真源，不做物理标定，不含验证 probe 本身。

**提交纪律**：以下所有文件改动必须在同一次 commit，提交前重建 `kundur_vsg.slx`，否则模型—代码半成品态会在 smoke 崩。

### 3.1 新增文件

#### `scenarios/kundur/kundur_ic.json`
```json
{
  "schema_version": 1,
  "calibration_status": "placeholder_pre_impedance_fix",
  "vsg_p0_vsg_base_pu": [1.8725, 1.8419, 1.7888, 1.9154],
  "units": {
    "vsg_p0_vsg_base_pu": "pu_on_vsg_base"
  },
  "source_hash": "sha256:<legacy-source-hash>"
}
```
- `<legacy-source-hash>` 在提交前计算：`sha256("build_powerlib_kundur.m:VSG_P0=[1.8725,1.8419,1.7888,1.9154]")` 的 hex

#### `scenarios/kundur/kundur_ic.py`
- Frozen dataclass `KundurIC`
- 入口 `load_kundur_ic(path=None) -> KundurIC`
- 校验：
  - `schema_version == 1`
  - `calibration_status` ∈ `{"placeholder_pre_impedance_fix", "calibrated"}`
  - `vsg_p0_vsg_base_pu` 长度 = 4、全为正、全为 `float`
  - `units.vsg_p0_vsg_base_pu == "pu_on_vsg_base"` 精确匹配
  - `source_hash` 前缀 `"sha256:"` + 64 位 hex
- 显式换算方法：`to_sbase_pu(*, vsg_sn_mva: float, sbase_mva: float) -> np.ndarray`
- 约束：**不得** import `scenarios.kundur.config_simulink`；避免 loader 与场景配置形成循环依赖

#### `slx_helpers/slx_load_kundur_ic.m` ← ⚠️ 位置错误（已实现但应移走）
- 入口 `ic = slx_load_kundur_ic(json_path)`
- 返回 struct，做与 Python 等价的校验
- `ic.vsg_p0_vsg_base_pu` 保证为 `1×4 double row vector`
- 校验失败直接 `error`
- **层级违规**：函数 100% Kundur-specific，违反 slx_helpers/ "无模型专用逻辑" 规定。
  Phase 1 执行时已落地于此（计划文件本身写错了位置）。
  后续 cleanup ticket：移到 `scenarios/kundur/kundur_load_ic.m`，按路 1 命名约定重命名。
  当前不影响 Phase 2-4 执行，移位优先级在本计划收工后。

### 3.2 修改文件

#### [scenarios/kundur/simulink_models/build_powerlib_kundur.m](../../../scenarios/kundur/simulink_models/build_powerlib_kundur.m)
- 删除 line 115 裸 `VSG_P0 = [1.8725, ...]`
- 改为基于脚本真实路径加载：
  ```matlab
  script_dir = fileparts(mfilename('fullpath'));
  scenario_dir = fileparts(script_dir);
  ic = slx_load_kundur_ic(fullfile(scenario_dir, 'kundur_ic.json'));
  VSG_P0 = ic.vsg_p0_vsg_base_pu;
  ```
- `PeGain_ES%d` 输出新增 `ToWorkspace` 块，`VariableName = 'PeFb_ES%d'`、`SaveFormat = 'Timeseries'`
- `P_out_ES%d` 保留，注释 `% DEBUG ONLY — not for training observation`

#### [scenarios/kundur/config_simulink.py](../../../scenarios/kundur/config_simulink.py)
- 删除 line 69 裸 `VSG_P0 = 1.87`
- 新增：
  ```python
  from scenarios.config_simulink_base import VSG_SN
  from scenarios.kundur.kundur_ic import load_kundur_ic
  _ic = load_kundur_ic()
  VSG_P0_VSG_BASE: np.ndarray = np.asarray(_ic.vsg_p0_vsg_base_pu, dtype=np.float64)  # shape (4,)
  VSG_P0_SBASE: np.ndarray = _ic.to_sbase_pu(vsg_sn_mva=VSG_SN, sbase_mva=SBASE)
  ```
- `KUNDUR_BRIDGE_CONFIG`:
  - `pe_measurement='feedback'`
  - 新增 `pe_feedback_signal='PeFb_ES{idx}'`
  - `pe0_default_vsg = tuple(VSG_P0_VSG_BASE.tolist())`
- 入口硬失败（在 `KUNDUR_BRIDGE_CONFIG` 构造后）：
  ```python
  if KUNDUR_BRIDGE_CONFIG.pe_measurement != 'feedback':
      raise ValueError(
          "Kundur main training path must use 'feedback' mode; 'pout' is debug only."
      )
  ```

#### [engine/simulink_bridge.py](../../../engine/simulink_bridge.py)
- `PE_MEASUREMENT_MODES` 添加 `"feedback"`
- `BridgeConfig` 新增字段 `pe_feedback_signal: str = ''`
- `pe0_default_vsg` 类型签名 `float | Sequence[float]`
- **新增 helper**（必须用，不能只改签名）:
  ```python
  def _normalize_per_agent_vector(name: str, value, n_agents: int) -> np.ndarray:
      """Validate scalar or sequence; broadcast to shape (n_agents,)."""
      arr = np.atleast_1d(np.asarray(value, dtype=np.float64))
      if arr.size == 1:
          arr = np.full(n_agents, arr.item())
      if arr.shape != (n_agents,):
          raise ValueError(f"{name}: expected scalar or length-{n_agents} sequence, got {arr.shape}")
      return arr
  ```
- 所有使用 `pe0_default_vsg` 的点切过 helper：
  - warmup 时 `assignin('base', 'Pe_ES{i}', ...)` 的 `{i}` 索引值取自 helper 输出的第 `i` 位
  - `_Pe_prev` seed 用 helper 输出
  - 结构校验 `__post_init__`：`feedback` 模式必带非空 `pe_feedback_signal`
- **不要**在此文件写 Kundur 专属 `pout` 禁令

#### [slx_helpers/vsg_bridge/slx_build_bridge_config.m](../../../slx_helpers/vsg_bridge/slx_build_bridge_config.m)
- 新增入参 + struct 字段 `pe_feedback_signal`
- `feedback` 模式支持

#### [slx_helpers/vsg_bridge/slx_step_and_read.m](../../../slx_helpers/vsg_bridge/slx_step_and_read.m)
- 新增 `feedback` 分支（与 `vi` / `pout` 平级）：
  ```matlab
  if strcmp(pe_mode, 'feedback')
      pefb_name = strrep(cfg.pe_feedback_signal, '{idx}', num2str(idx));
      pefb_ts = simOut.get(pefb_name);
      state.Pe(i) = pefb_ts.Data(end) * (cfg.vsg_sn / sbase_va);  % VSG-base pu → system-base pu
      pe_read = true;
  end
  ```
- `pout` 分支保留，但不再给 Kundur 默认使用（由场景配置决定）

#### [env/simulink/kundur_simulink_env.py](../../../env/simulink/kundur_simulink_env.py)
- 删除 line 65 `VSG_P0: float = 0.5`
- 导入 `from scenarios.kundur.config_simulink import VSG_P0_SBASE`
- `KundurSimulinkEnv.reset()` 中 `_P_es` 初始化：
  ```python
  self._P_es = VSG_P0_SBASE.copy()  # 4-vector, system-base pu
  ```
- StandaloneEnv 路径保留，在 line 396 与 line 475 附近添加 TODO 注释：
  ```python
  # TODO(2026-04-18 Kundur Pe contract fix): _P_mech=0.5 is VSG-base pu,
  # inconsistent with SimulinkEnv path which uses VSG_P0_SBASE. ODE backend
  # not in scope for this fix. Track in scenarios/kundur/NOTES.md.
  ```

#### [scenarios/kundur/NOTES.md](../../../scenarios/kundur/NOTES.md)
- "已知事实"段新增一条：
  > `KundurStandaloneEnv`（ODE 后端）的 `_P_mech = 0.5` 与 Simulink 主线 `VSG_P0_SBASE`（4 元向量）不一致；ODE 路径未列入本次 Pe 契约修复（2026-04-18）。若重启 ODE 路径需单独对齐。

### 3.3 Phase 1 提交不包含
- `probes/kundur/probe_zero_action_pe_alignment.m`（归 Phase 2）
- 零动作 10s 仿真结果（归 Phase 3）
- 50 ep 短训练（归 Phase 4）
- 物理 IC 重标定 / `vlf_*` 字段（归 Phase 5）

---

## 4. Phase 2 —— 单位守恒探针 ✅ 完成（commit `fa23a6f`）

**目标**：验证 Phase 1 的单位契约端到端闭合。

### 4.1 新增文件：`probes/kundur/probe_zero_action_pe_alignment.m`
- 加载 slx，跑零动作 1 s 仿真
- 同时采集：
  - MATLAB 侧：`PeFb_ES{i}[end]`（VSG-base pu）
  - Python 侧（通过 bridge 单步后 inspect）：`state.Pe[i]`（system-base pu）
- 计算 `err = state.Pe[i] - PeFb_ES{i}[end] * (VSG_SN/SBASE)`
- **判据**（双条件 OR）：
  - `abs(err) < 1e-6`
  - `rel_err = abs(err) / max(abs(state.Pe[i]), 1e-9) < 1e-6`
- 另外输出：`P_out_ES{i}[end]`、`omega_ES{i}[end]`、`delta_ES{i}[end]`、`IntW.Data[end]` 触限标志

### 4.2 通过标准
- 全 4 个 VSG 单位守恒判据通过
- 否则 Phase 1 有换算链漏，不得进 Phase 3

---

## 5. Phase 3 —— 零动作物理验证 ❌ 需重跑（方法已修正）

**目标**：在契约修复后，判断物理 IC 是否单独需要标定。

### 5.0 执行记录（2026-04-18，首次探针结果及结论）

首次用 `probe_zero_action_pe_alignment.m`（单次 10.5s 长仿真）跑出全红结果：
omega ≈ 0.85–0.91（偏 9–15%），delta_deg ≈ −19000 至 −24000°，PeFb 剧烈振荡。

**结论：probe 设计问题，不是 IC 问题，不触发 Phase 5。**

根因：
1. `phAng_ES{i} = 0.0` 对全部 4 个 VSG 写死，10.5s 内从不更新。Kundur 模型的受控 VS source phase = 外部 workspace 变量，训练里每步 0.2s 后才回写测量 delta，probe 的单次长仿真跳过了这个反馈 → VS angle 与 rotor angle 持续错位 → 发散。
2. Kundur 2-arg warmup 不回写 delta→phAng（NE39 5-arg warmup 有此步骤）。Python bridge（`simulink_bridge.py:459`）warmup 后也种 `_delta_prev_deg = zeros`，故第 1 拍同样写 phAng=0——这不是探针特有缺陷，训练主路径也如此。**不同之处**：训练每 0.2s 后从第 2 拍起进入真实 delta→phAng 反馈，第 1 拍为可接受过渡；探针把 phAng=0 的状态维持全程 10s，系统必然发散。

附加发现：
- `IntW_ES*` 未在 model build 脚本中导出 ToWorkspace → probe 报 N/A，无法验证积分饱和
- Phase 2 unit alignment（`err = pe_sbase − PeFb*(VSG_SN/SBASE)`）是数学恒等式，err 必然为 0，不验证实际契约闭合

Phase 5 保持待命，不因本次结果触发。

### 5.1 跑法（修正版）

**必须用 Python bridge 跑零动作 episode，不得用单次长仿真 MATLAB probe。**

原因：Kundur 模型 phAng 依赖外部回写；只有 bridge step 路径才能每 0.2s 更新一次，让系统进入真实 delta→phAng 反馈（从第 2 拍起）。单次长仿真 MATLAB loop 若实现 step-by-step phAng 回写也可接受，但 bridge 路径更贴近训练主路径。

执行方式：
```python
# 在 scenarios/kundur/train_simulink.py 或单独脚本中
env = KundurSimulinkEnv(cfg=KUNDUR_BRIDGE_CONFIG)
obs = env.reset()
for _ in range(n_steps):           # n_steps = 50 步 = 10s（dt=0.2s）
    action = np.zeros(env.action_space.shape)   # delta_M=0, delta_D=0
    obs, reward, done, info = env.step(action)
    # 记录 info["Pe"], info["omega"], info["IntW"]（如有）
```

稳态窗：步序 40–50（对应 t ∈ [8.0, 10.0]s）。

### 5.2 判据（全满足 = 契约修复充分）
- 稳态窗内 `max|Pe_ES{i} − VSG_P0_SBASE[i]| / VSG_P0_SBASE[i] < 5%`（system-base pu）
- 全过程 `info["IntW"]`（若可读）未触限（无 `0.7` 或 `1.3` 撞限）；IntW 不可读时该条免检
- 稳态窗内 `max|ω − 1| < 0.002 pu`（= ±0.1 Hz，50Hz 系统）
- `δ` 稳态窗内漂移 `< 1°/步`（约 5°/s）

### 5.3 前置补丁（执行前需确认）
- [ ] `IntW_ES{i}` ToWorkspace 块是否在 model 中存在？若无，在 build 脚本补上，否则该指标无法监控
- [ ] 确认 `KundurSimulinkEnv.step()` 的 `info` 字典包含 `Pe`、`omega`，以及 `IntW`（如已接入）

### 5.4 分支
- **全绿** → 进 Phase 4
- **任一红** → Phase 5（物理 IC 标定）
- **IntW 全程 N/A** → 视为该条免检，不阻塞进 Phase 4，但在 NOTES 标注

---

## 6. Phase 4 —— Smoke + 短训练 ⏳ 待执行（Phase 3 全绿后）

仅在 Phase 3 全绿时执行。

### 6.1 1 ep smoke
- 生成稳定 `run_id`，例如 `20260418-kundur-pe-contract-smoke`
- 跑 `harness_train_smoke_full(scenario_id='kundur', run_id=run_id, goal='validate Kundur training entry after Pe contract fix', episodes=1, mode='simulink')`
- 若返回 `status='running'`，继续 `harness_train_smoke_poll(scenario_id='kundur', run_id=run_id)` 直到完成
- 判据：训练主路径 `state.Pe` 来源为 `PeFb_ES*`（不走 `pout`）；日志无 measurement failure

### 6.2 50 ep 短训练
- `omega_saturated_rate < 30%`（基线 100% 显著下降）
- `settled_rate ≥ 10%`
- `mean_freq_dev < 3 Hz`

### 6.3 分支
- 全绿 → 计划收工，NOTES 归档
- 任一红 → 回查契约 or 进 Phase 5

---

## 7. Phase 5 —— phAng 初始化修复（已触发，Phase 3 失败）

**根因（2026-04-18 确认）**：Kundur warmup 走 3-arg `slx_warmup` 路径，phAng_ES{i} 硬写 0°，但模型 delta IC = vlf_ess[:, 1] = [18, 10, 7, 12]°。电压源与转子角不匹配 → 第 1 步 omega 已 0.82~0.88。NE39 通过 5-arg warmup 读回 delta_deg 解决了同样问题；Kundur 漏了这一步。

### 7.0 执行注意点（已评审）

1. `delta0_deg` 不止验长度，还需验 `np.isfinite(arr).all()`
2. `kundur_ic.py` fallback 常量带注释，注明来源 `build_powerlib_kundur.m vlf_ess(:,2)`，防魔法数漂移
3. 同步补测试覆盖三个行为：
   - 老的 3-arg warmup 分支（`delta0_deg=()` 时）行为不变
   - 新的 `delta0_deg` 非空时走 full slx_warmup
   - `_delta_prev_deg` 来自 warmup 返回值；`_Pe_prev` 仍是 nominal seed（不用 warmup Pe，因 `warmup_extract_state` 无 feedback 分支）

### 7.1 实施清单（6 步，最小改动）

#### 7.1.1 `scenarios/kundur/kundur_ic.json`
- 加可选字段 `vsg_delta0_deg: [18.0, 10.0, 7.0, 12.0]`
- schema_version **不变**（字段可选，向后兼容）

#### 7.1.2 `scenarios/kundur/kundur_ic.py`
- `KundurIC` 加 `vsg_delta0_deg: tuple[float, ...]`
- 缺失时 fallback `(18.0, 10.0, 7.0, 12.0)`，带注释：
  ```python
  # Source: build_powerlib_kundur.m vlf_ess(:,2) — VSG rotor angle ICs [deg]
  _DELTA0_DEG_DEFAULT = (18.0, 10.0, 7.0, 12.0)
  ```
- 验证：长度=4 **且** `np.isfinite(arr).all()`

#### 7.1.3 `engine/simulink_bridge.py` — `BridgeConfig`
- 加字段 `delta0_deg: tuple[float, ...] = ()`
- `__post_init__` 验证：非空时长度=n_agents **且** 所有值 isfinite

#### 7.1.4 `engine/simulink_bridge.py` — `SimulinkBridge.warmup()`
- `delta0_deg` 非空 → 走 full slx_warmup（5-arg/6-arg，与 NE39 `_reset_backend` 同构）：
  - 构造 `kundur_ip.*` struct 赋值串（eval 注入 MATLAB workspace）
  - 调 `slx_warmup(model_name, agent_ids, sbase_va, cfg_struct, kundur_ip, do_recompile)`，`nargout=2`
  - 校验 `warmup_status["success"]`
  - `self._delta_prev_deg = warmup_state["delta_deg"]`（clamp ±90°）
  - `self._Pe_prev = pe_nominal_vsg_arr / pe_scale`（**保持 nominal**，不用 warmup Pe）
- `delta0_deg` 为空 → 保持 3-arg 旧路径（不动）

#### 7.1.5 `scenarios/kundur/config_simulink.py`
- `KUNDUR_BRIDGE_CONFIG` 加 `delta0_deg=tuple(_ic.vsg_delta0_deg)`

#### 7.1.6 `probes/kundur/validate_phase3_zero_action.py`
- 第 156 行 `\u2212`（`−`）→ `-`（独立 Unicode fix）

### 7.2 不做的事
- **不升 schema_version**（字段可选，现有 v1 reader 不受影响）
- **不改 `warmup_extract_state`**（留 feedback 分支给后续）
- **不改 NE39 路径**（NE39 绕过 `bridge.warmup()`，不受影响）
- **不做全 NR 潮流标定**（先验证 vlf_ess 角度够不够，够了就不需要）

### 7.3 测试覆盖（新增，见执行注意点 3）

| 测试用例 | 验证内容 |
|---------|---------|
| `test_warmup_3arg_unchanged` | `delta0_deg=()` → 走旧路径，`_delta_prev_deg=zeros` |
| `test_warmup_5arg_delta_seeded` | `delta0_deg=(18,10,7,12)` → 走 5-arg，`_delta_prev_deg` 非零 |
| `test_warmup_pe_prev_nominal` | 无论哪条路径，`_Pe_prev` = nominal seed |

### 7.4 验证
- 修完后重跑 `probes/kundur/validate_phase3_zero_action.py`（Phase 3）
- 全绿后进 Phase 4

---

## 7.5 Phase 5 执行结果 ❌ Phase 3 仍失败（commit `1ef852e`，2026-04-18）

6步代码改动已实施，42个单元测试通过，但 Phase 3 重跑结果：
- omega 第1步已 0.82-0.88（与 Phase 5 前完全相同）
- C1 Pe 偏差 330-680%（物理无意义，系统已发散）
- C4 delta_drift = 0.000 deg/step（全程不变，异常）

**结论**：Phase 5 改动可能未生效，或 [18,10,7,12]° 本身是错的 IC。需系统诊断。

---

## 7.6 Phase 5 根因诊断计划（Phase 3 二次失败后）

### 关键未知（按排查优先级）

| # | 问题 | 诊断方法 | 能解释什么 |
|---|------|----------|------------|
| U1 | 6-arg warmup 后 `_delta_prev_deg` 是多少？ | probe reset 后打印该值 | 是否成功种 [18,10,7,12]，还是 [0,0,0,0] |
| U2 | 第 1 步 delta_deg 读回什么？ | probe 前5步打印 `_delta_prev_deg` | 读 0 → 信号断；变化 → delta 在走 |
| U3 | 6-arg warmup 后模型 omega 已在什么值？ | 从 `warmup_state` 读 omega | warmup 期间已发散 → IC 问题 |

### 诊断步骤（顺序，每步汇报再决策）

**Step D1**：在 `validate_phase3_zero_action.py` reset 后打印 `_delta_prev_deg` / `_Pe_prev`，前5步打印 `_delta_prev_deg`。
- U1=[0,0,0,0] → 走 6-arg 路径但未种对，调查 kundur_ip 传参
- U1=[18,10,7,12] + step 1 后 delta clip → warmup 内已发散，IC 值本身错误
- U2=读 0 → `delta_ES{i}` 信号断（模型未重建？）

**Step D2（视 D1 结论）**：
- 若 IC 错误 → 检查 slx_warmup 6-arg 内 omega 读回（`warmup_state["omega"]`），确认发散发生在 warmup 期
- 若传参 bug → 调试 `session.eval("kundur_ip", nargout=1)` 返回值

**Step D3（视 D2 结论）**：
- IC 错误且确认 → 触发 Phase 5b：运行 NR 潮流重算正确 delta IC
- 传参 bug → 修复并重测

### D1/D2 执行结果（2026-04-18）

```
[DIAG] warmup_state raw delta_deg=[-312°, -874°, -885°, -899°]  omega=[0.816, 0.846, 0.892, 0.846]
POST-WARMUP _delta_prev_deg: [-90. -90. -90. -90.]
```

**结论**：
- 6-arg warmup 正确执行（phAng 种对了 [18,10,7,12]°）
- 但 0.5s warmup 内 omega 已崩到 0.82-0.89，delta 螺旋到 -300° ~ -900°
- Phase 5 phAng 修复不是根因。**真正根因**：`vlf_ess` 是阻抗修复（commit 216d8b9）前的旧值，模型编译 IC 与当前网络参数不一致 → t=0 时 P_e_actual ≠ P_ref_nominal → swing 方程失衡 → omega 立即下降

---

## 7.7 Phase 5b — 物理 IC 重标定

**目标**：找到当前网络参数下的真实均衡 delta，更新 `vlf_ess`，重建模型。

### 步骤

**Step B1（MATLAB 探针）**：运行极短仿真（0.01s），检查 phAng=[18,10,7,12]° 时 PeFb_ES{i}[0] 实际值。若 P_e ≠ 1.87 pu → IC 确认错误。

**Step B2（找均衡角度）**：方法选一：
- 选项 A：MATLAB NR 潮流（精确，但需要手写潮流方程）
- 选项 B：MATLAB 仿真 + 大阻尼（D=50 替代 D=5），跑 60s，omega 收敛后读 delta_deg 均衡值
- 选项 C：在 Python bridge 里跑带 Pe 反馈的长 episode，找 omega=1.0 时的 delta

**Step B3**：更新 `build_powerlib_kundur.m` 的 `vlf_ess` 矩阵（4 行 2 列，[V_pu, delta_deg]）。

**Step B4**：重建 `kundur_vsg.slx`（运行 `build_powerlib_kundur.m`）。

**Step B5**：重跑 Phase 3 验证。

---

### 7.7 执行记录（2026-04-19）

#### B1 结果 ✅（上一 session 确认）
`probes/kundur/measure_pe_frozen.m` 实测：PeFb 值比 Pe_mech 高 30-44×，完全不物理。IC 确认错误。

#### B2 方法筛选结果

**选项 B（大阻尼动力学仿真）❌ 所有变体全部失败**：
- D=50，60s，从 0° 启：delta → -∞，omega 钳在 0.7
- D=50，60s，从 [18,10,7,12]°：同上，Pe_excess >> D×0.3，高阻尼恢复力不够
- 从 1° 小角出发（分析排除）：omega 打上限 1.3，delta 几百 ms 内飞到数百度
- 短仿真 1s + D=3（分析排除）：恢复力仅 0.9 pu，同样被 Pe_excess 压垮
- **根本教训**：任何偏离均衡的初始角都导致快速饱和，动力学仿真无法搜索均衡

**选项 C（Python bridge 长 episode）❌ 分析排除**：
- 依赖 PeFb 信号，而 PeFb 已确认单位异常（测量值 30-44× 偏高），反推路线无效

**选项 A（NR 潮流）✅ 选定并实现（2026-04-19）**

理论依据（从 VSG IntD/IntW 动力学严格推导）：
- 稳态条件：ω=1 → dδ/dt=0 → P_ref = P_e
- 电气功率：`P_e_vsg = (E·V_main·sin(δ−θ)/X_vsg_sys) × Sbase/VSG_SN`
- 均衡角：`sin(δ−θ) = P0_vsg_base × (VSG_SN/Sbase) × X_vsg_sys / V_main`
- θ_main 由 NR 潮流给出；δ 为 VSG CVS 内电势角（= IntD IC），绝对仿真帧

#### B3 结果 ✅（2026-04-19 实现）

**新增文件**：`slx_helpers/compute_kundur_powerflow.m`
- 15 母线（bus IDs 1-16，跳过 13），PI 线路模型构建 Ybus
- Bus 类型：Slack=Bus1(G1, V=1.03)，PV=Bus2/3/4(G2/G3/W1)，PQ=其余
- 含 ESS 注入（P_ES_sys = P0_vsg_base × VSG_SN/Sbase）和 TripLoad1（Bus14, 248MW）
- 标准极坐标 Newton-Raphson，tol=1e-8，max_iter=50
- 输出：`pf.ess_delta_deg`（4×1，绝对仿真帧），`pf.converged`，`pf.max_mismatch`
- sin_arg 越界时给警告并 clamp，不 error（兼容当前 stale P0）

**修改文件**：`scenarios/kundur/simulink_models/build_powerlib_kundur.m`
- 加 addpath 保护（standalone 运行也能找到 slx_helpers/）
- 调用 `compute_kundur_powerflow(ic_path)` → 得 `ess_delta0_deg`
- `vlf_ess = [ones(4,1), ess_delta0_deg(:)]`（不再硬编码 [18,10,7,12]°）
- build 完成后自动写回 `kundur_ic.json`（`calibration_status='powerflow_parametric'`，含 `powerflow_meta`）

**修改文件**：`slx_helpers/slx_load_kundur_ic.m`
- `valid_statuses` 加入 `'powerflow_parametric'`

**修改文件**：`scenarios/kundur/NOTES.md`
- 记录全部失败路线 + Phase 6 NR 潮流参数化方案

#### 已知限制（待 B4/B5 解决）
- 当前 P0（≈1.87 pu on 200MVA）是 placeholder_pre_impedance_fix，潮流以此为 ESS 注入量运行，G1（松弛母线）会吸收多余功率。潮流数值上收敛，delta0 与 P0 自洽。**P0 重校准是独立 TODO**，更新 P0 后重跑 build 脚本即自动更新 delta0。
- sin_arg ≈ 0.56（当前 P0），δ−θ_main ≈ 34°，物理可行（< 90°）。

#### B4 ✅ 完成（2026-04-19，最终 job aa9284de）

两轮修复迭代后完成：

**第一轮（job 9127fd57）— EMF 角 + IL_specify 修复**：
- Zess RLC 三相块设置 `IL_specify='on'` + AC 相量初始电流（从 NR 潮流反算）
- 模型编译通过，但 Phase 3 仍 FAIL
- 根因：Simscape 本地固步长求解器 DC 初始化将 IL 置 0，AC 激励下 IL 参数无效

**第二轮（job aa9284de）— P_ref 斜坡 X0=0 修复**（最终版）：
- `build_powerlib_kundur.m` ConvGen P0_ramp：`X0=num2str(P0_pu)` → `X0='0'`
- `build_powerlib_kundur.m` VSG PrefRamp：`X0=num2str(VSG_P0(i))` → `X0='0'`
- `scenarios/kundur/config_simulink.py` 新增 `T_WARMUP = 3.0` override
- NR 潮流收敛（max_mismatch=1.38e-12），1s test simulation 通过，JSON 已更新

#### B5 ❌ Phase 3 仍失败（2026-04-19，phase3_result.txt）

**验证结果**：
- "warmup ~0.5 s"：T_WARMUP=3.0 override **未被 validate 脚本读到**（脚本 import 路径绕过了 config_simulink.py override）
- POST-WARMUP delta=[-90, -90, -90, -90]°（仍触下限）
- POST-WARMUP Pe=[0.2, 0.2, 0.2, 0.2]（nominal seed，正常）
- Step 1 (t=3.2s)：omega=[0.74, 0.75, 0.83, 0.74]，Pe=[3.56, -2.62, 2.39, -4.10]
- C1: FAIL（Pe 偏差 2197%-11474%）；C2: WARN；C3: FAIL（omega 偏差 0.17-0.26 pu）；C4: PASS
- VERDICT: FAIL (C1, C3) → 仍触发 Phase 5 IC 标定

**诊断**：
- C4 PASS 而 delta=-90° → IntD 触下限后停止（hard clamp），非慢速漂移
- 即使 T_WARMUP=3.0 能生效，P_ref 斜坡（T_ramp=2s）若在最初 0.1s 内已触发 omega 冲击，延长 warmup 也不足以恢复
- ConvGen G2（M=9s，P0=7 pu）t=0 P_accel = 7/9 ≈ 0.78 pu/s；X0=0 后 P_ref(t=0)=0，P_accel = -Pe(t=0)/M。若 Pe(0)=0（Simscape DC IC），P_accel=0 ✓；但若电气系统在 ConvGen 侧仍瞬间产生非零 Pe（通过网络耦合 VSG），则问题仍存

**下一步（B6，待执行）**：
1. 读 `probes/kundur/validate_phase3_zero_action.py` 第 1-50 行，追查 T_WARMUP import 路径
2. 确认 `slx_helpers/slx_warmup.m` 内 t_warmup 参数实际来源（是否来自 bridge config 还是硬编码）
3. 若 T_WARMUP=3.0 修复后 delta 仍 -90°：考虑在 warmup 期间 freeze ConvGen delta（hold_omega=true 模式），让电气系统在零机械输入下建立稳态再释放

---

## 8. 验收总目标

| 项 | 判据 |
|---|---|
| Kundur 训练主路径 `state.Pe` 来源 | `PeFb_ES*`（非 `P_out`） |
| `state.Pe` / `_P_es` / `obs[:,0]` 口径 | system-base pu |
| reset 第 0 帧 `obs[:,0]` | 4 元向量，与 step 中同口径 |
| `VSG_P0` 真源 | `scenarios/kundur/kundur_ic.json` 唯一 |
| 单位守恒探针 | `abs<1e-6 OR rel<1e-6` |
| 零动作 10s | IntW 无触限；ω 稳态偏差 < ±0.1 Hz |
| 50 ep 短训练 | `settled_rate ≥ 10%` |
| Standalone env | 未受影响（`_P_mech=0.5` 保留，TODO 已落） |

---

## 9. 附录

### 9.1 数据流（Phase 1 之后）

```
[Power Sensor] ──► [PS2S] ──► [Gain 1/VSG_SN] ──┬──► VSG port 5 (swing Pe, VSG-base pu)
                                                 │
                                                 └──► [ToWorkspace PeFb_ES{i}]
                                                              │
                                                              ▼
                                              slx_step_and_read.m (feedback branch)
                                                              │
                                                × (VSG_SN/SBASE)  ◄─── 唯一换算点
                                                              │
                                                              ▼
                                                   state.Pe (system-base pu)
                                                              │
                                                              ▼
                                           env._P_es ──► obs[:,0] ──► SAC actor/critic
```

`P_out_ES*` 侧道并存：swing 方程输出（= P_ref − D·Δω），仅作 debug，不再进入 `state.Pe`。

### 9.2 TODO 清单（执行前汇总）
1. 计算 `legacy-source-hash`（Windows-safe）：
   `python -c "import hashlib; s='build_powerlib_kundur.m:VSG_P0=[1.8725,1.8419,1.7888,1.9154]'; print(hashlib.sha256(s.encode('utf-8')).hexdigest())"`
2. 确认 `KundurIC.to_sbase_pu(vsg_sn_mva=VSG_SN, sbase_mva=SBASE)` 返回预期 4 元 system-base 向量，且 loader 不 import `config_simulink.py`
3. 重建 `kundur_vsg.slx` 前先备份当前 .slx
4. Phase 1 提交前本地跑 `python -c "from scenarios.kundur.kundur_ic import load_kundur_ic; print(load_kundur_ic())"` 确认加载正常

### 9.3 失败回滚
- Phase 1 单次提交若 Phase 2 不通过，`git revert` 该 commit；`kundur_vsg.slx` 从备份恢复
- 不要分步骤回滚（半成品态更糟）

---

---

## 10. 边界 Cleanup Ticket（计划外发现，本计划收工后处理）

### 10.1 根因
`slx_helpers/` 边界只有 README，无测试 / CI / 启动路径约束兜底，且 `MatlabSession` 启动时自动 `addpath(slx_helpers)`，把违规成本降到了零——放进去就能被所有入口找到，放在正确位置反而需要额外配置。本计划 Section 3.1 自身就是第一个违规者：设计时未对照 README 规定，直接把 Kundur 专用函数写进共享层。
（注：不是"MATLAB 注定漂移"，是这个仓库缺对该边界的机器约束。）

### 10.2 发现的违规文件
| 文件 | 当前位置 | 违规原因 | 正确位置 |
|------|----------|----------|----------|
| `slx_load_kundur_ic.m` | `slx_helpers/` | 函数名含 `kundur`，字段全 Kundur-specific | `scenarios/kundur/` |
| `slx_warmup.m`（部分） | `slx_helpers/` | nargin==2 分支为 Kundur 特化，README 未说明例外 | **降级：共享 API 债务，不与 slx_load_kundur_ic.m 并列。** 被 Python bridge / NE39 env / probe 共同调用，牵涉面更广，单独立 ticket 处理 |

### 10.3 根本修法（推荐：路 1）
1. 命名前缀约定：`slx_*.m` 通用，`kundur_*.m` Kundur 专用（放 `scenarios/kundur/`），`ne39_*.m` NE39 专用
2. CI 校验脚本：检查**文件名 × 目录归属**（不用 grep 内容，误报太多）：
   - `slx_*.m` 只允许在 `slx_helpers/`
   - `kundur_*.m` 只允许在 `scenarios/kundur/`
   - `ne39_*.m` 只允许在 `scenarios/new_england/`
3. 搬走 `slx_load_kundur_ic.m` 后，以下三处都要补 addpath：
   - `engine/matlab_session.py`（按场景动态加）
   - `probes/kundur/probe_zero_action_pe_alignment.m`（直接 MATLAB 入口）
   - `scenarios/kundur/simulink_models/build_powerlib_kundur.m`（build 脚本入口）

### 10.4 本计划不处理
当前 slx_load_kundur_ic.m 在错位置不影响 Phase 3-4 执行（addpath 能找到）。cleanup 优先级：本计划收工后，独立 commit。

---

**End of plan. Execute only after explicit approval.**
