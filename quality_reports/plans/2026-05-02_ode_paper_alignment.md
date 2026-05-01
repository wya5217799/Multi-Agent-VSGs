# Plan · KD ODE 与论文对齐（不含 Simulink 桥）

| 字段 | 值 |
|---|---|
| Status | DRAFT |
| 创建 | 2026-05-02 |
| 范围 | KD (Kundur 4-agent) ODE 训练环境 |
| 不含 | Simulink CVS 桥 / NE39 / governor / SG 详细动态 |
| 参照文档 | `docs/paper/python_ode_env_boundary_cn.md` (项目自定边界) + `docs/paper/kd_4agent_paper_facts.md` (paper 事实) |
| 关联探针目录 | `probes/kundur/` (新增 `ode_gate{1..5}.py`) |

---

## 0. 已冻结的 3 个决策

### D1 · 动作范围保留 `[-16.1, 72] / [-14, 54]`，按"机制对齐而非数字对齐"在 §10 备案
- **理由 [CLAIM]**：paper `[-100, +300]` 是相对 paper 自身 H0 的比例（H0 未给数值），按 paper H_max ≈ 4·H0 解读，项目 H0=24 下绝对范围 ≈ [+72]
- **物理硬约束**：`H≥8` floor 与 `D≥0.1` floor 不可越过
- **不改** `config.py` 的 `DH_MIN/DH_MAX/DD_MIN/DD_MAX` 数值
- **改** 备案到 `docs/paper/kd_4agent_paper_facts.md` §10（项目偏差登记）+ `scenarios/kundur/NOTES.md`

### D2 · 加性扩展接口，**不**破坏 caller 签名
- 拒绝 boundary doc §13/§14 (gym-style `(terminated, truncated)` + `Scenario` 强参) 作为 paper-alignment 判据 —— 这是 gymnasium 工程惯例，paper 没要求
- 保留 `dict[int, ndarray]` actions（与 `MultiAgentManager.select_actions` 接口一致）
- 保留 `(obs, rewards, done, info)` 4-tuple（与 Simulink env 一致）
- 通过 `info` 扩展 + `reset()` 关键字加性扩展达成 §15/§16 要求
- 详见 D2 深度分析（本会话上文）

### D3 · 积分器 RK45 → 固定步长 RK4
- 理由 [CLAIM]：`solve_ivp(RK45, rtol=1e-6)` 自适应步长引入不可重复性；RL 训练需 byte-级可重复
- `dt_ode = 0.01s`，substeps = `dt_control / dt_ode` = 20
- **改** `env/ode/power_system.py::PowerSystem.step()` 的 `solve_ivp` 调用为自实现 RK4

---

## 1. 阶段总览（门控前置）

```
Stage 0  口径冻结 + 项目偏差备案                              [≤30min]
Stage 1  数值积分 + 安全边界 (D3 + §15)                       [~0.5d]
Stage 2  ODEScenario VO + manifest + 加性 reset(scenario=)    [~0.5d]
Stage 3  info 扩展 + Reward 训练/评价分离 (§10.3 + §11)        [~0.5d]
Stage 4  Caller 迁移 + 旧接口保留兼容                          [~0.25d]
Stage 5  Gate 1-5 全过 verdict                                [~1d]
                                                  共计 ~3 天
```

---

## 2. 阶段详表

### Stage 0 · 口径冻结 + 项目偏差备案

**前置**：用户确认 D1/D2/D3。

**做**：
1. 在 `docs/paper/kd_4agent_paper_facts.md` §10（项目偏差）追加：
   - 动作范围解读（D1）
   - ODE 接口形态选择（D2）
   - 固定 RK4 vs paper 未指定 solver（D3）
2. 在 `scenarios/kundur/NOTES.md` 追加"ODE 修模须知"：动作范围按相对 H0 ≈ 4× 解读

**通过判据**：
- 上述 2 文件 commit
- 用户书面确认（一次回复"OK"即可）

**失败回退**：D1 重审（动作范围争议是最大不确定项）

---

### Stage 1 · 数值积分 + 安全边界

**前置**：Stage 0 PASS。

**改 `env/ode/power_system.py`**：
1. `PowerSystem.step()` 内 `solve_ivp(RK45, ...)` → 自实现固定 RK4：
   ```python
   def _rk4_step(self, t0, x0, dt):
       k1 = self._dynamics(t0,        x0)
       k2 = self._dynamics(t0+dt/2,   x0 + dt/2 * k1)
       k3 = self._dynamics(t0+dt/2,   x0 + dt/2 * k2)
       k4 = self._dynamics(t0+dt,     x0 + dt   * k3)
       return x0 + dt/6 * (k1 + 2*k2 + 2*k3 + k4)
   ```
   - `n_substeps = int(round(self.dt / 0.01))` (= 20)
   - `dt_substep = self.dt / n_substeps`
2. NaN / Inf / `H≤0` / `D≤0` / `|Δω|>10 rad/s` / `|Δθ|>10 rad` 检测：违反 → `step()` 返回时附 `info["termination_reason"]`，env 层 `done=True`

**改 `env/ode/multi_vsg_env.py::step()`**：
- 捕获 `power_system` 端的 `termination_reason`，置 `done=True`
- 现有 `np.maximum(H_es, 8.0)` / `np.maximum(D_es, 0.1)` 改为：先记 clip 触发布尔到局部 dict，再 clip，最后写入 `info["action_clip"]`

**通过判据 [FACT 探针]**：
- 新建 `probes/kundur/ode_gate1_sanity.py`：no-control 单 bus 扰动跑 50 step → 无 NaN，至少 2 个 ESS 频率轨迹相对欧氏距离 > 1e-3
- RK4 vs RK45 在同 scenario 下 step=50 终态 `omega` 差 < 1e-3 (绝对量级)
- 注入 `delta_u = [NaN, 0, 0, 0]` scenario → `done=True` 且 `info["termination_reason"]` 非空字符串

**失败回退**：
- RK4/RK45 偏差 > 1e-3 → `n_substeps` 加到 50；仍不行 → 暂留 RK45 但加 `seed` 固定测试
- Gate 1 fail（频率轨迹相同）→ 回查 L 矩阵生成（`build_laplacian` 新单测）

---

### Stage 2 · ODEScenario VO + manifest + 加性 `reset(scenario=)`

**前置**：Stage 1 PASS。

**新增 `env/ode/ode_scenario.py`**：
```python
@dataclass(frozen=True)
class ODEScenario:
    scenario_idx: int
    delta_u: tuple[float, float, float, float]
    comm_failed_links: tuple[tuple[int, int], ...] = ()
    seed_base: int = 0

@dataclass
class ODEScenarioSet:
    schema_version: int        # = 1
    name: str                   # 'kd_train_100' / 'kd_test_50'
    n_scenarios: int
    seed_base: int
    scenarios: list[ODEScenario]

def generate_scenarios(n: int, seed: int, name: str) -> ODEScenarioSet: ...
def serialize(s: ODEScenarioSet) -> dict: ...
def deserialize(d: dict) -> ODEScenarioSet: ...
def save_manifest(s, path) -> None: ...
def load_manifest(path) -> ODEScenarioSet: ...
```
**生成器逻辑**：复制 `train_ode.py:31-57` 的 `generate_scenario_set` 主体；不改语义，只重塑成 dataclass + 持久化。

**新增 manifest 路径**：
- `scenarios/kundur/ode_scenario_sets/kd_train_100.json`
- `scenarios/kundur/ode_scenario_sets/kd_test_50.json`
- 提供 CLI: `python -m env.ode.ode_scenario --regenerate`

**改 `env/ode/multi_vsg_env.py::reset()` 加性扩展**：
```python
def reset(self, *, scenario: ODEScenario | None = None,
          delta_u=None, event_schedule=None):
    if scenario is not None:
        self.current_delta_u = np.asarray(scenario.delta_u, dtype=np.float64).copy()
        self.forced_link_failures = list(scenario.comm_failed_links) or None
        self.ps.reset(delta_u=self.current_delta_u)
        self.step_count = 0
        ...   # 复用现有初始化路径
        return self._build_observations(self.ps.get_state())
    # else: 现有路径完全不变
```

**通过判据 [FACT 探针]**：
- 新建 `probes/kundur/ode_scenario_manifest.py`：用 seed=42 生成两次 train_100 → JSON bytes 完全相等
- 旧 caller `env.reset(delta_u=LOAD_STEP_1)` 不改一行代码仍跑通 (regression test)

**失败回退**：bytes 不等 → 回查 numpy `default_rng` 版本依赖；加 numpy 版本下界到 `pyproject.toml`

---

### Stage 3 · info 扩展 + Reward 训练/评价分离

**前置**：Stage 2 PASS。

**新增 `env/ode/reward.py`**：
```python
def training_reward_local(state, delta_H, delta_D, comm_eta, ...) -> dict:
    """Eq.14-18, 局部 r_f + 全局 r_h/r_d (mean-then-square)."""
    # 复制 multi_vsg_env._compute_rewards 内容，无语义改动

def evaluation_reward_global(freq_trace_hz: np.ndarray) -> float:
    """§11 + Sec.IV-C: -Σ_t Σ_i (f_i,t - mean(f_t))^2 over Hz."""
    f_bar = freq_trace_hz.mean(axis=1, keepdims=True)
    return float(-np.sum((freq_trace_hz - f_bar) ** 2))
```

**改 `env/ode/multi_vsg_env.py::step()` info**：
```python
info["reward_components"] = {
    "r_f_per_agent": [...],     # length N
    "r_h_per_agent": [...],
    "r_d_per_agent": [...],
    "phi_f": cfg.PHI_F, "phi_h": cfg.PHI_H, "phi_d": cfg.PHI_D,
    "r_f_total": r_f_sum,        # 与现 info['r_f'] 数值一致 (兼容)
    "r_h_total": r_h_sum,
    "r_d_total": r_d_sum,
}
info["action_clip"] = {"H_clipped": bool, "D_clipped": bool, "H_min_post_clip": float, "D_min_post_clip": float}
info["termination_reason"] = ""  # 默认空，安全失败时填字符串
```
**保留 `info['r_f']`、`info['r_h']`、`info['r_d']`、`info['max_freq_deviation_hz']`** —— 旧 caller 不需改。

**通过判据 [FACT 探针]**：
- 新建 `probes/kundur/ode_gate3_reward_sanity.py`：手工 `ΔH = [+a, -a, 0, 0]` (mean=0) → `info["reward_components"]["r_h_total"]` 严格等于 0；`ΔH = [+a, +a, +a, +a]` → 严格 < 0
- `evaluation_reward_global(constant_freq) == 0`
- 旧 `info['r_f']` 与新 `info['reward_components']['r_f_total']` 数值相等

**失败回退**：reward 数值与旧版不等 → 回查公式抄写（M3 mean-then-square 不能动）

---

### Stage 4 · Caller 迁移

**前置**：Stage 3 PASS。

**改 `scenarios/kundur/train_ode.py`**：
1. `from env.ode.ode_scenario import load_manifest, generate_scenarios`
2. `train_scenarios = load_manifest(...)` 替代 inline `generate_scenario_set(...)`，inline 函数标 `# DEPRECATED, use env.ode.ode_scenario`
3. `obs = env.reset(scenario=train_scenarios[scenario_idx])` 替代旧 `env.reset(delta_u=delta_u)` + 直接 set `forced_link_failures` 属性
4. 训练 metadata 中记录 `scenario_set_path` 而不是仅 `seed`

**改 `scenarios/kundur/evaluate_ode.py`**：
1. `test_scenarios = load_manifest(... 'kd_test_50.json')` 替代 inline `generate_test_scenarios(...)`
2. `evaluation_reward_global(traj['freq'])` 替代 inline `compute_freq_sync_reward(...)` —— 旧函数标 deprecated 但留着（`run_episode` 调用点先不动，免得改 plotting 链路）

**不改**：
- `scenarios/scalability/train.py`（不在本计划范围）
- `tests/test_ode_*`（兼容性已通过加性设计保证，跑过即可）
- `env/factory.py` / `env/gym_adapter.py`（CLAUDE.md 已记 broken；不在本计划范围）

**通过判据**：
- `python scenarios/kundur/train_ode.py --episodes 5 --seed 42` 跑通无 traceback
- `training_log.npz` 输出完整字段
- `run_meta.json` 含 `scenario_set_path`

**失败回退**：迁移后训练曲线显著变化 → 回查 manifest 与 inline 生成器是否 byte-equal（应等）

---

### Stage 5 · Gate 1-5 全过 verdict

**前置**：Stage 4 PASS。

**新增 `probes/kundur/ode_gate{1..5}.py`** (每个 ≤120 行)：

| Gate | 测试 | 通过判据 |
|---|---|---|
| 1 (sanity) | no-control 单扰动 | 无 NaN；至少 2 ESS Δω 轨迹 distinct (与 Stage 1 重叠，提为正式 gate) |
| 2 (Prop.1) | 比例条件 H_i ∝ k_i ∧ D_i ∝ k_i ∧ Δu_i ∝ k_i | 4 ESS 频率轨迹相对差 < 5% peak |
| 3 (reward) | 手工 ΔH (mean=0 / mean≠0) | 与 Stage 3 重叠，提为正式 gate |
| 4 (RL plumbing) | 50 episode 短训练 | actor/critic loss 有限；action 非常数（std > 0.05）；buffer 收到 transition |
| 5 (paper-direction) | 100 train / 50 test | trained `evaluation_reward_global` mean > no-control mean（**方向正确即可，不要求 paper -8.04**）|

**输出**：`quality_reports/verdicts/2026-05-02_ode_gate_1to5.md`，含每个 gate 的 sha256 + run timestamp + 数值 + 判据通过/失败。

**失败回退**：
- G2 fail → 物理层（L 矩阵）回查
- G4 fail → SAC 超参（不在本计划范围，记 INCONCLUSIVE 后停手）
- G5 fail 但 G1-G4 全过 → 记 INCONCLUSIVE，本计划止步于 G4，不强行通过 G5

---

## 3. 文件清单

### 改（5 个）
- `env/ode/multi_vsg_env.py` — `reset(scenario=...)` 加性 + `info` 扩展 + `done` 安全失败路径
- `env/ode/power_system.py` — RK4 自实现 + 数值安全
- `scenarios/kundur/train_ode.py` — 迁移到 manifest
- `scenarios/kundur/evaluate_ode.py` — 迁移到 manifest + `evaluation_reward_global`
- `docs/paper/kd_4agent_paper_facts.md` §10 — D1/D2/D3 备案

### 新增（8 个）
- `env/ode/ode_scenario.py` — VO + manifest 读写
- `env/ode/reward.py` — train/eval reward 分离
- `scenarios/kundur/ode_scenario_sets/kd_train_100.json` — 持久化
- `scenarios/kundur/ode_scenario_sets/kd_test_50.json`
- `probes/kundur/ode_gate1_sanity.py`
- `probes/kundur/ode_gate2_proposition1.py`
- `probes/kundur/ode_gate3_reward_sanity.py`
- `probes/kundur/ode_gate4_rl_plumbing.py`
- `probes/kundur/ode_gate5_paper_direction.py`
- `quality_reports/verdicts/2026-05-02_ode_gate_1to5.md`

### 不改 / 不动（明示）
- `config.py` 数值（仅注释）
- `agents/ma_manager.py` / `agents/sac.py`
- `env/factory.py` / `env/gym_adapter.py`（已记 broken，不修）
- 任何 Simulink / NE39 / scalability 文件
- `tests/test_ode_*`（加性设计保证兼容；不达标再单独修）

---

## 4. 范围外（明示）

- ❌ Simulink CVS 桥 / 适配器
- ❌ 改 `H_ES0/D_ES0` 数值
- ❌ 改 paper 动作范围至 `[-100, +300]`（D1 决策保留）
- ❌ 重构 `MultiAgentManager` 接口（D2 决策保留 dict）
- ❌ NE39 / scalability
- ❌ governor / SG 详细动态
- ❌ Gate 5 数值达到 paper -8.04（方向正确即过）

---

## 5. 风险登记

| 风险 | 触发条件 | 缓解 |
|---|---|---|
| RK4 与 RK45 数值漂移 > 1e-3 | Stage 1 通过判据 | 加 substeps；仍不行回滚 RK45 + 固定 seed |
| Manifest 跨 numpy 版本不可重现 | Stage 2 探针 fail | `pyproject.toml` 加 numpy 版本下界 |
| Gate 5 fail 但 G1-G4 过 | Stage 5 | 记 INCONCLUSIVE，止步于 G4；下一阶段 SAC 超参由独立计划处理 |
| train_ode.py 迁移后训练曲线变化 | Stage 4 通过判据 | 验证 manifest = 旧 inline 生成器 byte-equal；不等就退回 |
| docs/paper/python_ode_env_boundary_cn.md §13/§14 与本计划接口形态分歧 | 任何阶段 | 在 Stage 0 备案中显式登记"§13/§14 是 gym 工程惯例，非 paper 不变量"，更新该 doc |

---

## 6. 完成判据（DoD）

- [ ] D1/D2/D3 备案 commit
- [ ] Stage 1-4 全过其各自通过判据
- [ ] Gate 1/2/3/4 PASS（Gate 5 可记 INCONCLUSIVE）
- [ ] `python scenarios/kundur/train_ode.py --episodes 100 --seed 42` 跑通且 metadata 含 `scenario_set_path`
- [ ] `python scenarios/kundur/evaluate_ode.py` 跑通输出 Fig 4-13
- [ ] verdict 文件 commit

---

## 7. 待用户书面确认

- [ ] D1/D2/D3 决策按本文档第 0 节执行
- [ ] 计划范围与排除项无遗漏
- [ ] Stage 5 G5 fail 时止步于 G4（不进入 SAC 超参 sweep）
