# ODE 实现现状分析报告

**日期**：2026-04-21
**范围**：`env/ode/`、`scenarios/{kundur,new_england,scalability}/`、`tests/`、`plotting/`、当前 `results/` 产物
**基线**：两轮独立审计（Claude 静态代码盘点 + Codex 代码/产物/基准）交叉比对后的共识版本

---

## 0. 方法与证据来源

| 证据类型 | 来源 | 用途 |
|---|---|---|
| 静态代码审计 | `env/ode/*.py`、训练/评估脚本、绘图脚本 | 结构与接口盘点 |
| 测试运行 | `pytest tests/ -q`（2026-04-21 运行） | 回归状态：**75 passed / 0 failed**（Claude 3.84 s, Codex 3.37 s） |
| 仿真基准 | Codex 实测（未单独复跑） | Kundur N=4 线性 ~1244 steps/s, N=8 线性 ~1239, N=8 非线性 ~846 |
| 训练产物 | `results/training_log.npz`、`results/train_ode_recalib.log`、`results/models/` | 训练可用性与策略质量 |
| 活代码实测 | `python -c "from env.factory import make_env; make_env('kundur','ode')"` | 统一工厂入口可用性 |

本报告中凡"Codex 审计发现"的性能与训练指标均标注来源；其余为 Claude 直接在代码/产物/Python 运行上复现。

---

## 1. 能力盘点

### 1.1 建模核心 — **核心可用，低保真**

- 2N 状态 `[Δθ, Δω]` 摆动方程，可选 governor 扩展到 3N — [env/ode/power_system.py:31](../env/ode/power_system.py)
- 线性 `L·θ` / 非线性 `V_i V_j B_ij sin(θ_i-θ_j)` 两种耦合模式，由 `network_mode` 切换 — [env/ode/power_system.py:168](../env/ode/power_system.py)
- 数值积分：`scipy.solve_ivp(RK45)`，`rtol=1e-6`、`atol=1e-8`、控制步内 `max_step=dt/10`；dt=0.2 s — [env/ode/power_system.py:227](../env/ode/power_system.py)
- 显式 Governor 下垂（默认关闭，`ODE_GOVERNOR_ENABLED=False`） — [config.py:272](../config.py)
- **不是 Simulink 等价**：无电压动态、无电磁暂态、无真实短路电流、无风机/同步机全阶模型、无 Kron 归约流程
- 定位：低保真频率动态原型，不能作为论文 Simulink 图的点对点替身

### 1.2 场景覆盖 — **Kundur 可用，NE39 / Scalability 是合成替代**

| 场景 | 环境类 | 拓扑真实性 |
|---|---|---|
| Kundur 4 节点 | `MultiVSGEnv` | 4×4 B 矩阵 + 环形通信，用于论文 Kundur 算例 |
| NE39 | `ScalableVSGEnv`（走 `scenarios/new_england/train_ode.py`） | **合成 8 节点环/链**，不是真实 IEEE 39-bus |
| Scalability 扫描 | `ScalableVSGEnv` | N∈{2,4,8}，`make_chain_BV` 合成拓扑 — [scenarios/scalability/train.py:43](../scenarios/scalability/train.py) |

真实 Kron 归约在 NOTES 里已明确标为不做。

### 1.3 训练支持 — **Kundur 闭环成型，NE39/Scalability 有脚本无产物**

- `scenarios/kundur/train_ode.py`：100 固定训练场景 + 2000 episodes + warmup + 独立 SAC + checkpoint + `training_log.npz` — 端到端可跑
- `scenarios/new_england/train_ode.py`：调用 `train_one(N=8, fn=60.0)` 并写 `results/new_england/`；**当前 `results/new_england/` 不存在**，无法确认已跑通
- `scenarios/scalability/train.py`：`main()` 会写 `results/scalability/scalability_log.json` — [scenarios/scalability/train.py:601](../scenarios/scalability/train.py)；**当前 `results/scalability/` 不存在**
- **统一工厂入口 `env.factory.make_env("kundur","ode")` 当前是坏的**（见 §5）

### 1.4 扰动 / 事件 — **初步具备，事件语义有限**

- 支持项：静态 `delta_u`、训练时随机扰动（1–3 母线，seeded）、固定测试集扰动、通信链路故障、强制通信链路失效 — [env/ode/multi_vsg_env.py:86](../env/ode/multi_vsg_env.py)
- `DisturbanceEvent` / `LineTripEvent` / `EventSchedule`：按控制步边界触发，**非子步精度**；`t>0` 事件按 `round(t/dt)-1` 在区间起点提前应用 — [utils/ode_events.py](../utils/ode_events.py)、[env/ode/power_system.py:133](../env/ode/power_system.py)
- 已落实的守卫：自环 `bus_i==bus_j` 拒绝、重复边检测、事件时间非递减校验
- NE39 脚本里的"风电跳闸 / 短路"主要是等效 `delta_u` 扰动，不是真实短路模型

### 1.5 参数化 — **功能较多，论文对齐不完整**

- 支持项：H/D 动作增量、异质 H/D、线性/非线性网络、governor 开关、通信故障概率、固定步延迟、可扩展 N
- **动作范围不对齐论文**（已在 config 内显式标注为"工作假设"）：
  - 代码：`ΔH ∈ [-16.1, 72]`，`ΔD ∈ [-14, 54]` — [config.py:49-50](../config.py)
  - 论文 Sec. IV-B：`ΔH ∈ [-100, 300]`，`ΔD ∈ [-200, 600]`
  - `config.py:41-47` 已用 `[M4 A 版口径核查]` 注释交代差异及换算工作假设
  - **但 [scenarios/kundur/train_ode.py:9](../scenarios/kundur/train_ode.py) 脚本 docstring 仍写着论文范围**，与实际运行参数不一致——属于文档/注释 vs 代码漂移

### 1.6 复现性 / 种子 — **Kundur 完整，NE39 评估未绑定**

- `utils/seed_utils.py::seed_everything()` 覆盖 python/numpy/torch/PYTHONHASHSEED（P1 协议）
- Kundur 训练：`seed_everything(args.seed)` + 100 固定训练集 + 写 `run_meta.json` — 代码路径完整 — [scenarios/kundur/train_ode.py:65,242](../scenarios/kundur/train_ode.py)
- Kundur 评估：50 固定测试集、`TEST_SEED=99`、deterministic policy — [scenarios/kundur/evaluate_ode.py:119](../scenarios/kundur/evaluate_ode.py)
- **Scalability** 测试集：`NE_TEST_SEED=2000` + `run_meta.json` ok
- **NE39 评估（`scenarios/new_england/train_ode.py`）未绑定固定测试集**，用 ad-hoc `fault_du` 向量

### 1.7 数据记录 — **能保存基础产物，不够统一**

| 路径 | 写入方 | 格式 | 当前存在 |
|---|---|---|---|
| `results/training_log.npz` | Kundur `train_ode.py:217` | numpy npz | ✅ 130 KB |
| `results/run_meta.json` | Kundur `train_ode.py:242`（代码） | JSON | ❌ **当前产物里没有**（代码会写但此次 2000 集产物缺失） |
| `results/models/{ep_500,ep_1000,ep_1500,ep_2000,final}/agent_{0-3}.pt` | Kundur 训练 | torch state_dict | ✅ 完整 |
| `results/new_england/training_log.json` | NE39 `train_ode.py:80` | JSON | ❌ 未跑 |
| `results/scalability/scalability_log.json` | `scalability/train.py:601` | JSON | ❌ 未跑 |

ODE 训练**未接入 Simulink 那套 `metrics.jsonl` / `training_status.json` 控制面**；`TrainingMonitor` 主要输出到 stdout，结构化可观测性弱。

### 1.8 图表 / 分析 — **Kundur 完整，NE39 存在具体 bug**

- **Kundur Fig.4–13**：`scenarios/kundur/evaluate_ode.py` 支持训练曲线、累计奖励、两类 load step、通信故障、通信延迟 — 端到端可用
- **Scalability Fig.14/15**：在 `scenarios/scalability/train.py` 内实现；`plotting/generate_fig16.py` 读同样的 `scalability_log.json` — 生产者与消费者格式对齐，**只缺产物**
- **NE39 Fig.17–21 存在两处具体缺陷**：
  1. [scenarios/new_england/train_ode.py:259](../scenarios/new_england/train_ode.py) 的 Fig.20(a) 通信延迟条用 `rng.uniform(0.0, 0.3, size=len(t_arr))` **装饰性随机延迟**，**不是**实际运行的 delay trace
  2. [plotting/replot_fig17_21.py](../plotting/replot_fig17_21.py) 内部 50/60 Hz 基准不一致：
     - 第 125、156、178 行 no-control / adaptive 部分用 `f - 50.0`（隐含 50 Hz）
     - 第 197 行 RL 延迟部分传 `fn=60.0`（NE39 正确频率）
     - 同一文件对同一 NE39 场景混用了两套频率基准
- 论文样式层（`paper_style.py`）已应用，IEEE rcParams + LaTeX 标签齐全

### 1.9 测试覆盖 — **物理保真有门控，RL 接口无单测**

- **75/75 通过**，~3.4 s；覆盖摆动方程、RK45 自洽、Laplacian 重建、线路跳闸、非线性 vs 线性、governor、异质化、Prop.1、种子复现、高斯延迟、P0/P1 固定测试集
- 仍未覆盖：奖励函数正确性、观测归一化、动作解码、多智能体接口、训练收敛性
- 测试套件里有一条 `test_unit_conversion_table`（`test_eq1_unit_verification.py:142`）是 `2H==2H` 的同义反复，docstring 已标 "non-assert"

---

## 2. 当前产物状态（实测）

```
results/
├── training_log.npz            130 KB, 2026-04-20 22:59   ✅ Kundur 2000 集训练日志
├── train_ode_recalib.log       55 KB                       ✅ 训练 stdout
├── models/
│   ├── ep_500/  ep_1000/  ep_1500/  ep_2000/              ✅ 阶段性 checkpoint
│   └── final/agent_{0-3}.pt                                ✅ 最终 checkpoint
├── phase3_validation.log, sim_kundur/, sim_ne39/, harness/  # 非 ODE
└── new_england/        — 缺
    scalability/        — 缺
    run_meta.json       — 缺（虽然 train_ode.py:242 会写，但这次产物里没有）
```

---

## 3. 性能与训练质量

### 3.1 仿真性能（Codex 实测，Claude 未复跑）

- **ODE 单独跑**：Kundur N=4 线性 ~1244 steps/s，N=8 线性 ~1239 steps/s，N=8 非线性 ~846 steps/s
- 10 s episode ≈ 0.04 s（N=4 线性）/ 0.059 s（N=8 非线性）
- **瓶颈在 PyTorch SAC 更新，不在 ODE 积分**

### 3.2 Kundur 训练质量（基于 `results/training_log.npz` + `train_ode_recalib.log`，Codex 解读）

| 指标 | 值 |
|---|---|
| 总时长 | 3272 s（2000 episodes, 100 000 control steps） |
| 训练吞吐 | ~30.6 train steps/s |
| 最终 50 集平均 reward | **-144.43** |
| 单集最佳 | **-15.19**（ep 1305） |
| 后期警告 | 大量 `early_stopping` 与 `reward_component_ratio` warning |

### 3.3 最终策略在固定 50 测试集的表现

| 方法 | 频率同步指标（越大越好） |
|---|---|
| 无控制 | -1.004 |
| 自适应惯量 | -0.769 |
| **RL（本项目）** | **-0.388**，49/50 场景优于无控制 |

**行为悖论**：按论文式全局频率同步指标 RL 明显赢，**但** 按环境总 reward 看，deterministic policy 在 Load Step 下会产生很大的 `r_h`/`r_d` 惩罚——说明策略学到了"猛调 H/D 换频率"，频率指标优而内部 reward 惩罚重。训练**可跑但不稳**。

---

## 4. 进度汇总

### 基本完成
- ODE 核心仿真器、Kundur 4-agent 环境、SAC 训练闭环、固定测试集、基础评估脚本
- 事件、非线性、governor、异质参数、通信延迟扩展能力已有测试门控
- 75/75 回归通过，代码级自洽状态良好
- 当前已有 Kundur ODE 2000 集训练产物与最终 checkpoint

### 有实现但不能算完成
- **NE39 / Scalability**：脚本齐全，当前无任何产物，无法声明"跑通"
- **NE39 绘图**：真实问题不是格式不匹配（`.json↔.json` 是一致的），而是 `replot_fig17_21.py` **50/60 Hz 基准不一致** + `train_ode.py` Fig.20 延迟条是**装饰性随机数**
- **训练稳定性**：2000 集可跑但后期警告多，策略行为悖论表明奖励结构与学习目标未充分对齐
- **统一入口**：`env.factory` 的两条 ODE 路径**实测完全坏**

### 关键缺失
1. `env.factory.make_env("kundur","ode")` 与 `make_env("ne39","ode")` **都无法成功实例化**（双重 bug，见 §5）
2. Kundur 训练 docstring 写论文参数范围、代码跑缩放范围，文档 vs 代码漂移
3. 当前 Kundur 产物缺 `run_meta.json`，seed/protocol 证据链不完整
4. NE39 真实拓扑与真实故障语义缺失（按"合成 8 节点替代"定位更诚实）
5. ODE 结果未写入 `docs/paper/experiment-index.md`

### 距离"当前阶段训练环境"
- 作为**快速独立 RL 原型**（Kundur only）：**已可用**
- 作为**当前论文复现主线**：不够。AGENTS.md 明确主线是 Simulink；ODE 更适合做低保真原型、回归测试、快速 sanity check

---

## 5. 关键短板（按对当前使用价值的影响排序）

### S1. 统一工厂入口完全坏 — 最高优先级

实测：
```bash
$ python -c "from env.factory import make_env; make_env('kundur','ode')"
ModuleNotFoundError: No module named 'scenarios.kundur.config'
```

双重 bug，见 [env/factory.py:39-59](../env/factory.py)：

| 问题 | 位置 | 证据 |
|---|---|---|
| ① 导入不存在的模块 | `import scenarios.kundur.config as cfg` 行 41 | `scenarios/kundur/` 下只有 `config_simulink.py` |
| ② 位置参数签名不匹配 | `MultiVSGEnv(cfg, **kwargs)` 行 42 | `MultiVSGEnv.__init__(random_disturbance=True, comm_fail_prob=None, comm_delay_steps=0, forced_link_failures=None)` 不接受 `cfg` |

即便把 ① 改为 `import config as cfg`（项目根），② 的位置参数仍会把 `cfg` 对象塞进 `random_disturbance` 参数。NE39 同款问题（行 56-59）。

实际使用上**依赖直跑专用脚本**（`scenarios/kundur/train_ode.py` 直接 `import config as cfg`），统一工厂接口名存实亡。

### S2. 训练稳定性与奖励对齐

2000 集最终均值 -144.43 vs 最佳 -15.19，后期大量 early stopping——策略后期退化。deterministic 评估下 H/D 惩罚被拉得很大，说明当前奖励权重 / 动作范围组合下，策略在"频率指标"和"调节代价"之间无法稳定收敛。

### S3. NE39 绘图内部频率不一致

`plotting/replot_fig17_21.py` 同一文件混用 50 Hz（no-control / adaptive）与 60 Hz（RL 延迟）基准。NE39 在 CLAUDE.md 中已明确应为 60 Hz。直接出图会产生"看起来偏差很大但实则基准错了"的误导性图表。

### S4. NE39 Fig.20 延迟条是装饰

`scenarios/new_england/train_ode.py:259` 用 `rng.uniform(0.0, 0.3)` 填 Fig.20(a) 通信延迟条——与 RL 实际经历的延迟没有数据关联。图表可视但不可信。

### S5. 产物链路空缺

`results/new_england/`、`results/scalability/` 目录不存在；Kundur 产物缺 `run_meta.json`。Figure 17-21 与 Fig.16 的**消费端**代码是能跑的，卡在**生产端没跑**而已（修了 S1 之后成本不高）。

---

## 6. 总体结论

**当前 ODE 处于"核心仿真 + Kundur 训练闭环成型的低保真原型阶段"。** 它不是空架子：核心 ODE、RL 环境、SAC 训练、事件扩展、测试集和部分图表都已落地并通过 75 项回归，并有 2000 集训练产物和最终 checkpoint。但**不是 Simulink 的替代品**，也**不是**当前仓库的 active reproduction path。

### 从"当前阶段需求"看
- 用于**快速算法管线验证、低成本 sanity check、训练 Kundur 原型策略**：**基本够用**
- 用于**论文复现主线或作为正式训练证据**：**不够**

### 最小修改原则下最关键的几项
按修复成本 × 影响排序：

| 优先级 | 修什么 | 成本 | 影响 |
|---|---|---|---|
| P0 | 修 `env/factory.py` 的 ODE 入口（改 `import config as cfg` + 改用 kwargs） | 小 | 统一入口可用，下游 runner 才能真用 |
| P0 | 对齐 `scenarios/kundur/train_ode.py` docstring 与实际 `config.py` 动作范围，或把 config 内"工作假设"注解传播出去 | 极小 | 消除文档 vs 代码漂移 |
| P1 | 修 `plotting/replot_fig17_21.py` 的 50/60 Hz 基准一致性 | 小 | NE39 图表可信 |
| P1 | 给当前 / 后续 ODE 训练补齐 `run_meta.json` 写盘（或补齐当前这次已跑的元数据） | 小 | 证据链可追溯 |
| P2 | 把 Fig.20 延迟条改成实际 delay trace（当前 `ScalableVSGEnv` 的 `comm_delay_gaussian` 支持 `_delay_trace` 导出） | 中 | 图表语义真实 |
| P2 | 跑 Scalability sweep、NE39 训练，落地产物到 `results/scalability/`、`results/new_england/` | 中-大 | 解锁 Fig.14-16、Fig.17-21 |
| P3 | 明确把 NE39 ODE 标为"合成 8 节点替代"，或在论文描述中与 Simulink NE39 做明确区分 | 小 | 诚信定位 |

---

## 附录 A：已独立验证的事实清单

本报告中以下关键事实均由 Claude 在 2026-04-21 直接复核（代码路径 + 实运行 + 产物目录）：

- [x] `env/factory.py` 的两条 ODE 路径运行时抛 `ModuleNotFoundError`
- [x] `MultiVSGEnv.__init__` 签名不接受 `cfg` 位置参数（`env/ode/multi_vsg_env.py:21-22`）
- [x] `scenarios/kundur/` 下只有 `config_simulink.py`，无 `config.py`
- [x] `scenarios/new_england/` 下只有 `config_simulink.py`，无 `config.py`
- [x] `results/training_log.npz`（130 KB, 2026-04-20）存在；`results/models/final/agent_{0-3}.pt` 存在
- [x] `results/new_england/`、`results/scalability/`、`results/run_meta.json` **不存在**
- [x] Kundur `train_ode.py:217` 写 `training_log.npz`；NE39 `train_ode.py:80` 写 `training_log.json`；`replot_fig17_21.py:74` 读 `training_log.json` — **NE39 链路格式其实一致**
- [x] `scenarios/scalability/train.py:601` 写 `scalability_log.json`，`plotting/generate_fig16.py:25` 读同路径 — **生产者存在**
- [x] `config.py:49-50` 代码动作范围 `[-16.1, 72] / [-14, 54]`，与 Kundur `train_ode.py:9` docstring 写的论文范围 `[-100, 300] / [-200, 600]` 不一致；`config.py:41-47` 已显式标注该差异
- [x] `scenarios/new_england/train_ode.py:259` Fig.20(a) 使用 `rng.uniform(0.0, 0.3)` 随机延迟
- [x] `plotting/replot_fig17_21.py` 第 125/156/178 行用 `- 50.0`，第 197 行传 `fn=60.0` — 基准不一致
- [x] 75/75 测试通过（2026-04-21）

以下数据来自 Codex 审计、Claude 未单独复跑，但源路径已确认可复核：

- [ ] 仿真 benchmark（1244 / 1239 / 846 steps/s）
- [ ] 训练时长 3272 s、最终 50 集均值 -144.43、最佳 -15.19
- [ ] 固定 50 测试集上 RL -0.388 vs 无控制 -1.004 vs 自适应 -0.769（49/50 优于无控制）

---

## 附录 B：早期报告的事实修正

本节记录本报告合并前两轮独立盘点时发现的具体错误，留作审计追溯：

| 错误陈述（早期 Claude 报告） | 实际事实 |
|---|---|
| "`results/` 训练产物目录已于 2026-04-06 全部清理" | `results/` 当前非空，有 `training_log.npz` + `models/{ep_500..2000,final}` + `train_ode_recalib.log` |
| "NE39 绘图脚本 `.json` 读 vs 训练 `.npz` 写，格式不匹配" | NE39 两端都是 `training_log.json`；Kundur 两端都是 `.npz`；**格式本来一致**。真问题是 NE39 产物未生成 + `replot_fig17_21.py` 内部 50/60 Hz 不一致 |
| "`plotting/generate_fig16.py` 没有生产者" | 生产者是 `scenarios/scalability/train.py:601`；真问题是当前未跑产物 |
| （遗漏）`env.factory` ODE 入口状态 | 实测完全坏（双重 bug，见 §5.S1） |

早期 Codex 报告中亦有一处略过度：将"ODE 不是当前 active reproduction path"作为判断 ODE 实现价值的依据——这属于仓库策略层面，不应混入"实现现状"技术评价。本合并版已剥离。
