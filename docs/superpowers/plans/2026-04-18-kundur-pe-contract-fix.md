# Kundur Pe 观测契约与 VSG_P0 真源修复计划

**日期**: 2026-04-18
**场景**: Kundur Simulink 主线（`kundur_vsg.slx` + `train_simulink.py`）
**作用域**: Paper Track — Kundur 训练路径；不含 NE39；不含 KundurStandaloneEnv（ODE 后端）
**状态**: Planned — 未执行

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

## 3. Phase 1 —— 原子提交实施清单

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

#### `slx_helpers/slx_load_kundur_ic.m`
- 入口 `ic = slx_load_kundur_ic(json_path)`
- 返回 struct，做与 Python 等价的校验
- `ic.vsg_p0_vsg_base_pu` 保证为 `1×4 double row vector`
- 校验失败直接 `error`

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

#### [slx_helpers/slx_build_bridge_config.m](../../../slx_helpers/slx_build_bridge_config.m)
- 新增入参 + struct 字段 `pe_feedback_signal`
- `feedback` 模式支持

#### [slx_helpers/slx_step_and_read.m](../../../slx_helpers/slx_step_and_read.m)
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

## 4. Phase 2 —— 单位守恒探针

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

## 5. Phase 3 —— 零动作物理验证

**目标**：在契约修复后，判断物理 IC 是否单独需要标定。

### 5.1 跑法
- 零动作 10 s 仿真（`action=[0,0]`）
- 采样点：`t ∈ [8.0, 10.0]` s 作为"稳态窗"

### 5.2 判据（全满足 = 契约修复充分）
- 稳态窗内 `max|PeFb_ES{i} − VSG_P0_VSG_BASE[i]| / VSG_P0_VSG_BASE[i] < 5%`
- 全过程 `IntW` 未触限（无 `0.7` 或 `1.3` 撞限）
- 稳态窗内 `max|ω − 1| < 0.002 pu`（= ±0.1 Hz）
- `δ` 稳态窗内漂移 `< 1°/秒`

### 5.3 分支
- **全绿** → 进 Phase 4
- **任一红** → Phase 5（物理 IC 标定）

---

## 6. Phase 4 —— Smoke + 短训练

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

## 7. Phase 5 —— 物理 IC 标定（条件触发）

**仅**在 Phase 3 失败（零动作物理仍漂）时启动。

### 7.1 Schema 扩展
在 `kundur_ic.json` schema_version 升级至 2，新增字段：
- `vlf_gen`, `vlf_wind`, `vlf_ess`（均为 `[[V_pu, angle_deg], ...]`）
- `calibration_status = "calibrated"`
- `source_hash` 从 legacy string hash 切换为绑**生成器工件 SHA**，覆盖至少：
  - 生成器脚本 SHA
  - `build_powerlib_kundur.m` 关键参数 SHA：`Sbase`、`VSG_SN`、`line_defs`、阻抗参数、负荷/风场初值
- `kundur_ic.py` / `slx_load_kundur_ic.m` 增加 schema_version 2 分支（向后兼容 v1 读取用于诊断）

### 7.2 求解器路线（代价从低到高，依次尝试）
1. **Simulink 自洽稳态**：跑长时间零动作取末态作为 IC 快照
2. **Python NR 潮流**：独立实现，输出写入 `kundur_ic.json`
3. **外部工具（最后手段）**：powergui 兼容层

### 7.3 验证
- 重新跑 Phase 2 + Phase 3，全绿后进 Phase 4

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

**End of plan. Execute only after explicit approval.**
