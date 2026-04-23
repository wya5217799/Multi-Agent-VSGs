# ODE Model Notes

> 修 ODE 模型前必读。与 `docs/paper/yang2023-fact-base.md` 一致。

## ODE 方法边界（项目决策，非论文事实）

**ODE 是 Prop.1 推导用的低保真替身，不承担与 Simulink 图点对点对齐的责任。**

- 论文 Fig.4–21 均由 Matlab-Simulink 生成，不由 ODE 路径负责。
- ODE 路径目标：在 ODE 能力边界内，贴近论文建模目标、实验覆盖、图表形态；关键数值差距须记录为证据，不得滑向"不做数值对标"。
- "图能画出来" ≠ "动力学真实对应"（典型反例：Fig.20(a) 随机延迟柱图为装饰，非真实延迟）。
- 以下属于方法/分辨率不可达的 C 类边界，不进开发计划：电压动态、电磁暂态、风机/同步机全阶动态、短路电流、亚控制步通信周期。
- 文档分区：论文已核实事实 → `docs/paper/yang2023-fact-base.md`；项目口径/决策 → 本文件或 `docs/decisions/`；不得混写。

## Governor 默认策略（项目决策）

**governor 默认关闭**（`ODE_GOVERNOR_ENABLED=False`）。论文 Eq.(1)–(4) 不含 governor 状态，开启会将状态从 2N 变为 3N，偏离论文简化模型。

- `train_ode.py`（Kundur / NE39）与所有 evaluate 脚本：**不得**默认开启 governor。
- 仅在"扩展实验分支"场景下允许开启，且须在图注中标明"3N 状态空间（含 governor）"。
- 接口已支持传参（`governor_enabled=True`），默认值必须保持 `False`。

## 能力开关（config.py）

| 开关 | 默认 | 作用 | 成本 |
|---|---|---|---|
| `ODE_HETEROGENEOUS` | False | 按 `ODE_H_SPREAD` 生成 per-node H/D | 无性能影响 |
| `ODE_NETWORK_MODE` | 'linear' | 'nonlinear' 时用 `Σ B_ij sin(θ_i-θ_j)` | +~30 % step 时间 |
| `ODE_GOVERNOR_ENABLED` | False | 加一阶 droop + τ_G 汽轮机滞后；状态 2N→3N | +~10 % step 时间 |
| (事件 API) | — | `EventSchedule` 传入 `reset(event_schedule=...)` | 对齐 step 边界 |

## 默认 = 论文 Eq.4 对齐

所有开关默认 off 时，`PowerSystem` / `MultiVSGEnv` 行为 baseline-preserving（兼容性门控验证）。
可用 `tests/test_ode_physics_gates.py` 验证。

## 事件 API

`utils/ode_events.py` 提供：
- `DisturbanceEvent(t, delta_u)` — 将当前 Δu 全量替换为新值（所有母线）
- `LineTripEvent(t, bus_i, bus_j)` — 将 B[i,j]=B[j,i]=0 并重建 L
- `EventSchedule(events=(...))` — 冻结的事件序列；必须按 t 单调不减

事件在 step 边界生效（step-boundary 语义）：t=0 事件在 `reset()` 内立即应用；t>0 事件用 `max(0, round(t/dt) - 1) == step_idx` 匹配，已知存在一步提前偏差。亚步精度不支持——若需要，把 dt 调小。

## 观测归一化口径（M3a 核查结论）

| 路径 | omega_dot 归一化系数 | 代码位置 |
|---|---|---|
| Kundur ODE (`MultiVSGEnv`) | `/25.0` | `env/ode/multi_vsg_env.py:217` |
| NE39/scalability (`ScalableVSGEnv`) | `/5.0` | `scenarios/scalability/train.py:163` |

**差异 5 倍，来源不明**。两条路径 H/D/Δu 量级相同，omega_dot 物理范围应相近，差异可能为笔误。

**未统一前**：跨路径（Kundur vs NE39）的观测尺度比较结论须标注"obs 归一化尺度未统一（M3a 未收敛）"，不得作为正式对标证据。

**下一步**：M3 收敛后（依赖 M1 奖励口径），再决定统一到哪个系数，并同步更新两条路径。

## 已知限制

1. **事件只对齐 step 边界**（<0.2 s 误差）。
2. **governor R / τ_G 全节点共享**——若需要异构 governor，仿 heterogeneity helper 扩展即可。
3. **nonlinear 的 `_coupling` 是 O(N²)**。N=4/10 没问题，N>>100 需要向量化/稀疏化。
4. **governor 不参与 RL 动作空间**——RL agent 只调 H, D；governor 作为背景一次调频动力学。

## 已核实事实

- ODE 现有状态：`[Δθ, Δω]` (2N)，governor 开启后扩为 `[Δθ, Δω, P_gov]` (3N)。
- Gate 目标：`ω_n ≈ 0.6 Hz, ζ ≈ 0.05, Δf_peak ≈ 0.4 Hz`（H=24, D=18, B_tie=4）。

## Eq.(1) 单位口径（M1 · 2026-04-21 修订）

**论文原文事实（核查 `C:\Users\27443\Desktop\论文\high_accuracy_transcription_cn.md` Eq.(1)/(4) 行 67-103）**：

论文 Eq.(1)（Sec.II-A）原文形式：`H_es·Δω̇ + D_es·Δω = Δu - ΔP_es`。
- 原文**无 `2` 系数、无 `ω_s` 系数**——属控制派集总常数形式。
- 对 H 仅称"虚拟惯量常数"（Sec.II-A、Sec.II-A Eq.4 后注释），**未给量纲**（秒？p.u.？无量纲？均无明示）。
- Δω 的基值（p.u. 还是 rad/s）**原文未明示**。
- Sec.IV-B 只给 $\Delta H$ 调节范围 $[-100,300]$，不给基准 $H_{es,0}$ 数值。

**代码实现（`power_system.py:205`）**：`2H_code·Δω̇ = ω_s·(Δu-L·Δθ) - D·Δω`（电机学标准形式，Δω 为 rad/s）。

**项目工作假设（推断，非论文事实）**：若假设论文 Δω 为 p.u. 基值，则将 Δω_pu = Δω_rad/ω_s 代入，两侧乘 ω_s：
```
H_paper · Δω̇_rad = ω_s·(Δu - L·Δθ) - D · Δω_rad
```
与代码对比 → 数值映射 `H_paper = 2·H_code`。

**该映射是工程推断，不是论文结论。** 论文未说 Δω 是 p.u.，未说 H 是 $M = 2H_{trad}$，也未明示折算关系。选用电机学形式是为了与 Simulink 发电机模型 [49] 阻抗基值对齐，不是为了复现论文 Eq.(1) 的原始系数。

**数值换算（基于上述工作假设）**：
- H_code = 24 s → H_paper = **48**（假设下）
- ΔH_code ∈ [-16.1, 72] → ΔH_paper ∈ [-32.2, 144]（假设下）
- vs 论文 Sec.IV-B `ΔH∈[-100,300]`：差距 2-3×；**不得以"论文事实"口径声称该映射后的"量纲等价"**。

**M3/M4 下游结论（在工作假设下成立）**：
- **M3 选版**：论文 Eq.(17)/(18) 为物理量 `(ΔH̄)²`/`(ΔD̄)²`，两条 ODE 路径统一到**物理量版**（去掉 Kundur MultiVSGEnv 的 `/_dh_scale²` 归一化）。
- **M4 A 版**：当前动作范围与论文 [-100,300] 在 2·H 映射下差 2-3×。引用该映射时**必须同时引用本 NOTES 的"项目推断"声明**；冻结 ODE 正式对标结论，直到 B 版重训。

**证据链**：
- 论文原文：`C:\Users\27443\Desktop\论文\high_accuracy_transcription_cn.md` Eq.(1)/(4) 行 67-103（原文对 H 量纲全部描述已穷举，仅"虚拟惯量常数"一词）
- fact-base：`docs/paper/yang2023-fact-base.md` §2.1 Q7 段已同步修订为"原文未给量纲 + 项目工作假设"
- 验证脚本：`tests/test_eq1_unit_verification.py`（**验证的是代码自洽 + ω_s 缩放 + 稳态解析，不证明论文等价**）

## 时变通信时延（M7 · 2026-04-21）

`ScalableVSGEnv(comm_delay_gaussian={'mean_range':(lo,hi), 'std':σ, 'rng_seed':int})` 启用高斯时变时延。三要素：

1. **高斯分布**: 每步每链路独立 `d ~ N(μ_ij, σ)`, clip≥0, `d_steps = round(d/dt)`.
2. **多链路不同均值**: reset 时 `μ_ij ~ U(lo, hi)`, 对称 `μ_ij = μ_ji` (同链路双向一致); 8 节点环形至少 3 个不同 μ (由 seed 固定).
3. **真进入观测链路**: `_build_obs_gaussian_delay` 先 append 邻居当前 ω/ω̇ 到环形 buffer, 再回溯 `d_steps` 步读出; `d_steps=0 → 当前即时`, `d_steps=K → K 步前`.

状态:
- `env._delay_trace`: `list[dict[(i,j), d_sec]]`, 每步一项 (含 reset 初始化一项, 共 `STEPS_PER_EPISODE+1`).
- `env._link_means`: `dict[(i,j), μ]`, 对称.
- `env._gaussian_buffers`: `dict[(i,j,'omega'|'omega_dot'), deque]`, maxlen = `ceil((μ_max+4σ)/dt)+1`.

与 `comm_delay_steps` **互斥**, 同传抛 ValueError.

**Fig.20 (a)(b) 共享序列**: `plotting/replot_fig17_21.py` Fig.20 段改为一次 episode + 共享 `env._delay_trace` — (a) 柱图 = 各链路每步延迟均值, (b) 频率 = 同一 episode 的 `info['freq_hz']`; 旧 `rng.uniform(0.0, 0.3)` 装饰路径已移除.

验证: `tests/test_m7_gaussian_delay.py` 7 tests.

## P0/P1 前置核实条件闭合（2026-04-21）

**P0-测试: 固定评估集标准化**
- Kundur `evaluate_ode.py`: `generate_test_scenarios(n=None)` 默认读 `cfg.N_TEST_SCENARIOS`, `TEST_SEED=99` + metadata print。
- scalability `train.py`:
  - `generate_ne_test_scenarios(n_agents, n=None, seed=None)`: 默认 `cfg.N_TEST_SCENARIOS` + `NE_TEST_SEED=2000`
  - `build_test_set_metadata(...)` 导出 n_test/seed/generator_version 字典
  - `compute_test_reward` / `compute_no_control_reward` 改 `random_disturbance=False` + 显式 `delta_u` 列表（两个函数签名改为 `(n_agents, manager=None, scenarios=None, n_test=None, seed=None)`）
  - `main` 写 `results/scalability/run_meta.json`
- NE39 `train_ode.py`: Fig.17-21 图表扰动为显式 delta_u（风电跳闸/短路），本就固定，不走评估集路径。

**P1: 完整 seed 协议**
- 新增 `utils/seed_utils.py::seed_everything(seed)`：
  - 覆盖 `python random` / `numpy.random` 全局 / `torch` CPU+CUDA / `PYTHONHASHSEED`
  - 返回 `dict[str, int]` 供 metadata 写入
  - 非法 seed 抛 `ValueError`
- Kundur `train_ode.py`: `seed_everything(args.seed)` 移至 `MultiAgentManager` 构造前；warmup action 用 `warmup_rng = np.random.default_rng(args.seed)` 替代全局 `np.random.uniform`。
- scalability `train_one`: 同上改造；`main` 另加 `run_meta.json`（含 seed_protocol + per-N test_set metadata）。
- Replay buffer `sample` 的 `np.random.randint` 保留全局依赖，但由 `seed_everything` 的 `np.random.seed` 覆盖，端到端可复现（由 `test_env_seed_reproducible_after_seed_everything` 验证）。

**验证集**
- `tests/test_p0_p1_seed_fixed_set.py` 14 tests（固定集 reproducibility + seed_everything 四源覆盖 + compute_*_reward 确定性）。
- ODE 主回归：M7 (7) + M6b2/M8b (7) + M1 (5) + Prop.1 (4) + P0/P1 (14) = **37/37 pass**。

**硬规则解冻**
- 计划 §P0/§P1 的"正式证据冻结"条款：本提交后 Kundur + scalability/NE39-ODE 路径已全部具备固定集 + seed 协议 + metadata sidecar，可支持正式对标证据输出。
- 唯一例外仍然存在的阻断：M4 动作范围（冻结待 B 版重训）+ K1/K2/K3 Kron reduction（独立排期）。

## 邻居通信拓扑（N8 · 2026-04-21）

代码与论文"每节点 2 邻居"一致：

| 路径 | 实现 | 拓扑 | 每节点邻居数 |
|---|---|---|---|
| Kundur ODE | `config.py:79 COMM_ADJACENCY` | 4 节点环形 `{0:[1,3], 1:[0,2], 2:[1,3], 3:[2,0]}` | 2 |
| NE39 / scalability | `scenarios/scalability/train.py:35 make_ring_topology(N)` | N 节点环形（N=2/4/8） | 2 |

论文 IV-F 要求"每节点 2 邻居"，代码实现已满足。无待办。

## NE39 拓扑：项目 8-chain vs 论文真实拓扑（N6 · 2026-04-21）

**项目当前使用**: `make_chain_BV(N=8)` 合成链状拓扑（`scenarios/scalability/train.py:43`），B 矩阵为链式耦合 `b_intra=10.0, b_tie=2.0`。

**论文 Fig.16**: "改进 New England 系统的单线图"——完整 39 母线 + 10 台同步机（modified 版本：8 台 G 替换为风电 + 8 ESS 挂 Bus40-47）。

**差异**：项目 8-chain 是"替代拓扑"，非论文真实 NE39 拓扑的 Kron 约化结果。L 矩阵特征谱、振荡模态、功率分配与真实 NE39 存在未量化差距。

**报告/图表使用规则**：
- 引用论文 Fig.16 单线图（若复现）时，必须加图注："示意/真实 NE39 拓扑 — 项目 ODE 训练使用合成 8-chain 等效，非 Kron 约化；等价性未论证。"
- `plotting/generate_fig16.py` 当前为 scalability 条形图（观测维度/训练集/性能），与论文 Fig.16 编号冲突；文件 docstring 已标注"非论文 Fig.16 单线图"。
- 正式结论/图表包输出时须挂载 M0 局限性声明 + K1/K2 "未做 · provisional" 标记。

## 试过没用的

- 高斯 delay buffer 初版"先读 buf[-1] 再 append": `d_steps=0` 语义变成"延迟 1 步", `test_zero_delay_matches_nondelayed_obs` 失败. 改为"先 append 再回溯"修复.
- P0-测试初版"`random_disturbance=True + env.seed(seed+ep)`"虽然同 seed 可复现, 但扰动不可枚举 + 跨代码修改 `reset` 逻辑易漂移. 改为显式 `delta_u` 列表 + `generate_ne_test_scenarios` 生成器方案.
- `scalability/train.py` 里工具函数叫 `test_set_metadata` 被 pytest 按 `test_*` 收集, 报 `fixture 'n_agents' not found`. 重命名 `build_test_set_metadata` 修复.
