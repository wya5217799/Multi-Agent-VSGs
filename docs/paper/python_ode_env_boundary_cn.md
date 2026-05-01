# Python ODE 环境设计边界文档

> 文件建议路径：`docs/design/python_ode_env_boundary.md`  
> 适用范围：KD 4-agent / 修改版 Kundur / 4 ESS / DDIC 论文机制复现  
> 文档目的：明确 Python ODE 环境**要实现什么**、**不实现什么**、**验收边界是什么**。  
> 核心原则：训练环境优先复现论文的机电暂态控制关系；Simulink 用作后续工程验证，而不是第一训练主环境。

> **🛈 2026-05-02 SCOPE BANNER (D2/D3 reclassification)**
>
> 本文件是**项目自定的工程契约**，不是论文事实。下列章节经评审后**重分类**：
> - **§12（积分器选择）/ §13（Reset 签名）/ §14（Step 签名）/ §15（terminated/truncated）**
>   → 这些是 **Gymnasium ≥0.26 单 agent 工程惯例**，不是论文不变量。
>   论文 §III/§IV 未对返回签名、积分器、`terminated`/`truncated` 拆分作任何要求。
> - 多 agent 项目 (PettingZoo/MARLlib 生态) 普遍用 `dict[int, ndarray]` 动作 + 单 `done`，
>   与本项目 `MultiAgentManager.select_actions` 一致。
>
> **当前对齐方案 (Plan 2026-05-02)：** 加性扩展接口 — `reset(scenario=...)` 关键字可选、
> `info` 字典扩展 (`action_clip` / `termination_reason` / `reward_components`)，
> 旧 caller 签名不破坏。详见
> `docs/paper/ode_paper_alignment_deviations.md` D2 节。
>
> **§16（Scenario 集合）/ §10（Reward 公式）/ §22（硬不变量 1-5/8-10）仍按本文档执行**——
> 这些是 paper-anchored 部分。
>
> 本文件其他章节维持原状。

---

## 1. 背景与定位

本环境用于复现 Yang et al. 2023 中 KD 4-agent DDIC 主实验的控制机制。

论文主模型不是三相电磁暂态模型，也不是器件级 VSG/逆变器模型。论文研究尺度是**机电暂态**，核心关系是：

```math
\Delta\dot{\theta} = \Delta\omega
```

```math
\Delta\dot{\omega}
=
H^{-1}\Delta u
-
H^{-1}L\Delta\theta
-
H^{-1}D\Delta\omega
```

因此，本 Python ODE 环境的定位是：

```text
paper-faithful mechanism environment
```

而不是：

```text
high-fidelity power-electronics simulator
```

它要回答的问题是：

```text
在论文抽象的机电暂态模型下，多智能体 SAC 是否能通过调整 H/D 分布抑制 ESS 之间的频率差异？
```

它不负责回答：

```text
真实电力器件、三相电磁暂态、内环控制、Simulink Phasor 细节下策略是否完全成立？
```

这些问题应留给 Simulink 验证层。

---

## 2. 总体目标

Python ODE 环境必须支持以下目标：

1. 建立 4 个 ESS/VSG 节点的低阶机电暂态模型。
2. 通过等效网络耦合矩阵 `L` 产生 ESS 节点间的频率差异。
3. 通过等效扰动 `Δu(t)` 表示负荷/风电扰动对各 ESS 节点的影响。
4. 每个 agent 输出连续动作 `[ΔH_i, ΔD_i]`。
5. 环境根据动作更新 `H_i`、`D_i`。
6. 环境返回每个 agent 的局部观测。
7. 环境计算论文式局部 reward。
8. 环境支持训练集/测试集 scenario。
9. 环境支持 no-control、manual policy、trained policy 的评估。
10. 环境提供足够诊断信息，用于判断失败来自：
    - 物理模型；
    - reward 实现；
    - 动作语义；
    - 训练算法；
    - scenario 设计；
    - 数值积分。

---

## 3. 非目标

第一版 Python ODE 环境**不得实现**以下内容：

```text
三相 abc 波形
PWM 开关
dq 坐标内环
电流环 PI
电压环 PI
PLL
逆变器电磁暂态
Controlled Voltage Source
RLC Load block
CCS Load
Simulink powergui
Simulink FastRestart
real/complex signal routing
MATLAB Engine
SG governor
SG AVR/exciter
断路器暂态
离散电磁暂态微秒级步长
```

原因：

这些属于 Simulink/电力器件层，不属于论文 ODE 抽象层。提前引入这些内容会把训练问题变成仿真平台工程问题，偏离 paper-first reproduction。

---

## 4. 模型状态边界

第一版只建 4 个 ESS 的慢变量。

状态向量：

```text
x = [
  Δθ_1, Δθ_2, Δθ_3, Δθ_4,
  Δω_1, Δω_2, Δω_3, Δω_4
]
```

维度：

```text
state_dim = 8
```

其中：

| 变量 | 含义 |
|---|---|
| `Δθ_i` | 第 i 个 ESS bus 的角度偏差 |
| `Δω_i` | 第 i 个 ESS bus 的频率偏差 |
| `Δωdot_i` | 由 ODE RHS 计算，不作为独立状态存储 |
| `ΔP_es_i` | 由 `L @ Δθ` 计算，不作为独立状态存储 |

第一版不加入额外状态，例如：

```text
电压幅值状态
电流状态
PLL 状态
滤波器状态
SG 转子状态
governor 状态
AVR 状态
```

---

## 5. 动力学方程

ODE RHS 必须按以下结构实现：

```python
def rhs(t, x, H, D, L, disturbance):
    theta = x[:4]
    omega = x[4:]

    delta_u = disturbance(t)

    delta_p_es = L @ theta

    omega_dot = inv(H) @ (
        delta_u
        - delta_p_es
        - D @ omega
    )

    theta_dot = omega

    return concat(theta_dot, omega_dot)
```

工程实现时不一定真的构造 `inv(H)`，可以直接逐元素除：

```python
omega_dot = (delta_u - delta_p_es - D_diag * omega) / H_diag
```

必须满足：

```text
H_diag.shape == (4,)
D_diag.shape == (4,)
L.shape == (4, 4)
delta_u.shape == (4,)
```

---

## 6. 网络耦合矩阵 L

### 6.1 第一版要求

第一版使用 4×4 等效 Laplacian 矩阵 `L`。

必须满足：

```text
L.shape == (4, 4)
L = L.T
sum(L[i, :]) ≈ 0
L[i, i] > 0
L[i, j] <= 0, i != j
```

`L` 不应硬编码在 step 函数内部，而应由配置传入。

### 6.2 初始 L 的来源

允许两种来源：

#### A. Paper-minimal L

手工构造一个能产生差模动态的 4 节点 Laplacian。

适合第一版打通训练。

#### B. Kundur-calibrated L

后续通过 Kundur Ybus / Kron reduction / small-signal probing 得到 4 ESS 等效耦合。

这属于校准阶段，不应阻塞第一版 ODE 环境。

---

## 7. 扰动模型边界

### 7.1 扰动只进入 `Δu(t)`

ODE 环境不建真实负荷器件。所有外部扰动统一表示为：

```text
Δu(t) ∈ R^4
```

这代表扰动折算到 4 个 ESS 节点后的等效输入。

### 7.2 必须支持的扰动类型

#### 7.2.1 单节点等效扰动

```text
Δu = [A, 0, 0, 0]
```

用途：

```text
debug
ODE sanity
agent response check
```

#### 7.2.2 Bus14 等效扰动

```text
Δu = k14 * A
```

其中：

```text
k14.shape == (4,)
```

用于模拟论文 Load step 1：

```text
Bus 14 负荷减少 248 MW
```

#### 7.2.3 Bus15 等效扰动

```text
Δu = k15 * A
```

用于模拟论文 Load step 2：

```text
Bus 15 负荷增加 188 MW
```

#### 7.2.4 随机场景扰动

用于训练/测试集：

```text
random_train_scenario
random_test_scenario
```

### 7.3 扰动 scenario 必须包含

```yaml
scenario_id: str
disturbance_type: str
disturbance_time: float
disturbance_magnitude: float
disturbance_vector: [float, float, float, float]
communication_outage_pattern: ...
seed: int
```

### 7.4 扰动边界

不得在 ODE 环境中实现：

```text
R-block
R-bank
CCS
RLC Load
breaker
switch
Simulink LoadStep block
```

这些是 Simulink 验证层的内容。

---

## 8. 动作语义

每个 agent 的动作：

```text
a_i = [ΔH_i, ΔD_i]
```

整体 action：

```text
action.shape == (4, 2)
```

动作更新规则：

```text
H_i = H0_i + ΔH_i
D_i = D0_i + ΔD_i
```

默认论文动作范围：

```text
ΔH_i ∈ [-100, +300]
ΔD_i ∈ [-200, +600]
```

### 8.1 H0 / D0 边界

论文未明确给出 `H0_i`、`D0_i` 具体数值，因此在本环境中：

```text
H0
D0
```

属于校准参数，而不是论文硬事实。

要求：

1. `H0`、`D0` 必须配置化。
2. 不得散落硬编码在多个文件中。
3. 每次训练日志必须记录 `H0`、`D0`。
4. 如果动作导致 `H_i <= 0` 或 `D_i <= 0`，必须 hard fail 或显式 clip 并记录。

### 8.2 Clip 规则

如果使用 clip，必须在 `info` 中记录：

```python
info["action_clip"] = {
    "H_clipped": bool,
    "D_clipped": bool,
    "H_min": float,
    "D_min": float,
}
```

禁止静默 clip。

---

## 9. 观测语义

每个 agent 的 observation 必须是 7 维：

```text
o_i = [
  ΔP_es_i,
  Δω_i,
  Δωdot_i,
  Δω_neighbor_1,
  Δω_neighbor_2,
  Δωdot_neighbor_1,
  Δωdot_neighbor_2
]
```

整体 observation：

```text
obs.shape == (4, 7)
```

其中：

```text
ΔP_es = L @ Δθ
Δωdot = ODE RHS 中的 omega_dot
```

### 9.1 邻居拓扑

通信拓扑必须配置化。

示例：

```yaml
neighbors:
  0: [1, 2]
  1: [0, 3]
  2: [0, 3]
  3: [1, 2]
```

第一版要求：

```text
每个 agent 正好 2 个邻居
```

因为 KD 4-agent 论文主实验中：

```text
m = 2
obs_dim = 3 + 2m = 7
```

### 9.2 通信中断

通信中断时：

```text
η_j = 0
neighbor_Δω = 0
neighbor_Δωdot = 0
```

禁止使用：

```text
NaN
None
mask-only without value
variable-length observation
```

观测维度必须始终保持 7。

---

## 10. Reward 语义

总 reward：

```text
r_i = φ_f r_f_i + φ_h r_h_i + φ_d r_d_i
```

默认权重：

```text
φ_f = 100
φ_h = 1
φ_d = 1
```

### 10.1 频率同步 reward

`r_f` 衡量的是：

```text
本地 ESS 频率与活跃邻居频率的一致性
```

不是：

```text
频率是否恢复到 50 Hz
```

硬边界：

```text
如果所有活跃 ESS/邻居频率完全一致，则 r_f_i = 0
```

即使它们共同偏离额定频率，也不能额外惩罚。

### 10.2 H/D 平均调整 reward

`r_h`、`r_d` 必须惩罚平均调整，而不是每个 agent 的动作幅度。

应实现：

```text
r_h = -(mean(ΔH))^2
r_d = -(mean(ΔD))^2
```

不得实现为：

```text
r_h = -mean(ΔH^2)
r_d = -mean(ΔD^2)
```

这是硬边界。

原因：

论文目标是允许 H/D 在 agent 之间重新分布，同时约束系统总调整量，而不是鼓励每个 agent 都不动。

### 10.3 Reward 分解日志

每一步必须记录：

```python
info["reward_components"] = {
    "r_f": list[float],
    "r_h": list[float],
    "r_d": list[float],
    "total": list[float],
    "phi_f": float,
    "phi_h": float,
    "phi_d": float,
}
```

---

## 11. 训练 reward 与评价 reward 的边界

训练 reward 使用局部观测：

```text
agent 自己 + 活跃邻居
```

评价 reward 使用全局频率同步指标：

```text
R_global = -sum_t sum_i (f_i,t - mean(f_t))^2
```

必须分开实现：

```text
training_reward()
evaluation_reward()
```

禁止训练时偷偷用全局评价 reward。

---

## 12. 时间步长与积分器

默认论文时间设置：

```text
control_dt = 0.2 s
episode_length = 10.0 s
steps_per_episode = 50
```

ODE 内部积分建议第一版使用固定步长 RK4：

```text
ode_dt = 0.005 s 或 0.01 s
substeps = control_dt / ode_dt
```

第一版不建议使用 adaptive solver。

原因：

```text
RL 训练更需要稳定、可重复、易 debug 的环境；
adaptive solver 会引入额外不确定性和调试复杂度。
```

---

## 13. Reset 语义

默认 reset 到平衡点：

```text
Δθ = [0, 0, 0, 0]
Δω = [0, 0, 0, 0]
t = 0
```

reset 必须支持显式 scenario：

```python
obs, info = env.reset(scenario=scenario)
```

训练模式下可以从 train scenario set 采样。

评价模式下必须显式遍历 test scenario set。

---

## 14. Step 语义

`env.step(action)` 必须执行以下流程：

1. 校验 action shape：

```text
action.shape == (4, 2)
```

2. 将 action 转为 `H`、`D`：

```text
H = H0 + ΔH
D = D0 + ΔD
```

3. 根据 scenario 和当前时间生成：

```text
Δu(t)
```

4. 用固定步长 RK4 积分 `control_dt = 0.2 s`。

5. 更新状态：

```text
Δθ
Δω
```

6. 计算：

```text
ΔP_es = L @ Δθ
Δωdot = rhs_omega(...)
```

7. 构造 `obs_next.shape == (4, 7)`。

8. 计算 `reward.shape == (4,)`。

9. 返回：

```python
obs_next, reward, terminated, truncated, info
```

其中：

```text
terminated = 数值失败 / 安全失败
truncated = episode 到 50 step
```

---

## 15. 数值安全边界

环境必须检测：

```text
NaN
Inf
H <= 0
D <= 0
abs(Δω) 过大
abs(Δθ) 过大
积分失败
```

建议默认阈值：

```yaml
min_H: 1.0e-6
min_D: 1.0e-6
max_abs_dw: 10.0
max_abs_theta: 10.0
```

数值失败时必须返回：

```python
terminated = True
info["termination_reason"] = "..."
```

禁止 silent fail。

---

## 16. Scenario 集合

必须支持固定 train/test split：

```text
train_scenarios = 100
test_scenarios = 50
```

scenario 生成必须 seed-controlled。

要求：

1. 同一个 seed 生成完全相同 scenario。
2. 训练日志记录 scenario seed。
3. evaluation 不得临时重新采样 test set。
4. 每个 scenario 有稳定 ID。

---

## 17. 诊断输出

每个 episode 至少可以导出：

```text
time
Δθ_trace
Δω_trace
Δωdot_trace
ΔP_es_trace
Δu_trace
H_trace
D_trace
action_trace
reward_component_trace
communication_eta_trace
global_eval_reward
termination_reason
```

这些诊断必须能回答：

1. 扰动有没有进入系统？
2. 不同 ESS 有没有产生不同频率动态？
3. action 有没有改变 H/D？
4. H/D 改变后动力学有没有变化？
5. reward 分解是否合理？
6. 训练提升是否来自 r_f，而不是 reward bug？
7. trained policy 是否真的优于 no-control？

---

## 18. Gate 设计

### Gate 1：ODE 物理 sanity

运行 no-control 单扰动测试。

通过标准：

```text
无 NaN/Inf
Δω 有非零响应
至少两个 ESS 的 Δω 轨迹不同
改变 disturbance_vector 后响应形状改变
```

失败含义：

```text
L、Δu、积分器或状态方程有问题。
```

---

### Gate 2：Proposition 1 机制 sanity

构造比例条件：

```text
H_i ∝ k_i
D_i ∝ k_i
Δu_i ∝ k_i
```

通过标准：

```text
4 个 ESS 的频率轨迹接近一致
差模振荡接近消失
```

失败含义：

```text
论文核心机制未被正确实现。
```

---

### Gate 3：Reward sanity

构造三组手工动作：

```text
A: ΔH = [0, 0, 0, 0]
B: ΔH = [+a, -a, 0, 0]
C: ΔH = [+a, +a, +a, +a]
```

通过标准：

```text
B 的 mean(ΔH) ≈ 0，因此不应被 r_h 惩罚
C 的 mean(ΔH) ≠ 0，因此应被 r_h 惩罚
ΔD 同理
```

失败含义：

```text
r_h / r_d 实现错了。
```

---

### Gate 4：RL plumbing sanity

运行短训练。

通过标准：

```text
训练可完成
buffer 收到 transition
actor/critic loss 有限
action 不是常数
reward components 正常记录
trained policy 与 no-control 行为不同
```

失败含义：

```text
RL 接口、数据流、动作缩放或 reward 尺度有问题。
```

---

### Gate 5：paper-direction sanity

运行固定 train/test split。

通过标准：

```text
trained_policy 的 global_eval_reward 优于 no_control
测试使用固定 50 个 scenario
训练 reward 和评价 reward 分离
```

第一版不要求数值直接达到论文 `-8.04`，但必须方向正确。

---

## 19. 推荐文件结构

```text
env/ode/kundur_4agent_ode_env.py
env/ode/ode_dynamics.py
env/ode/network.py
env/ode/scenario.py
env/ode/reward.py
env/ode/observations.py
env/ode/integrators.py

scenarios/kundur/train_ode.py
scenarios/kundur/eval_ode.py
scenarios/kundur/generate_ode_scenarios.py

tests/test_ode_dynamics.py
tests/test_ode_reward.py
tests/test_ode_observation.py
tests/test_ode_scenarios.py

quality_reports/gates/
```

---

## 20. 配置表面

建议配置项：

```yaml
num_agents: 4

time:
  control_dt: 0.2
  episode_seconds: 10.0
  ode_dt: 0.01
  integrator: rk4

base_params:
  H0: [ ... ]
  D0: [ ... ]

action_bounds:
  delta_H: [-100, 300]
  delta_D: [-200, 600]

reward_weights:
  phi_f: 100
  phi_h: 1
  phi_d: 1

network:
  L: ...

communication:
  neighbors:
    0: [1, 2]
    1: [0, 3]
    2: [0, 3]
    3: [1, 2]
  outage_mode: fixed_or_random

scenario_set:
  train_count: 100
  test_count: 50
  seed: 2026
```

---

## 21. 与 Simulink 的关系

Python ODE 是：

```text
paper-first reproduction environment
```

Simulink 是：

```text
engineering validation environment
```

推荐工作流：

```text
1. Python ODE 先复现论文机制
2. Python ODE 先验证 SAC 能否学出 DDIC > no-control
3. 再把 ODE 中成功的策略/机制拿到 Simulink 验证
4. Simulink 失败时，先判断是模型层级不一致还是算法失败
```

不得把 Simulink 的工程问题倒灌进 ODE 第一版，例如：

```text
Phasor real/complex 类型错误
FastRestart 参数冻结
R-block runtime tunability
Controlled Voltage Source 输入限制
powergui Discrete/Phasor 兼容性
```

这些不是 ODE 环境要解决的问题。

---

## 22. 硬性不变量

以下不变量不得违反：

1. 只针对 KD 4-agent。
2. 只建 4 个 ESS 的 `Δθ/Δω`。
3. action 必须是连续 `[ΔH, ΔD]`。
4. reward 的 `r_f` 只衡量同步，不衡量回额定频率。
5. `r_h/r_d` 必须是先平均再平方。
6. 训练阶段只支持通信中断，不引入通信延迟。
7. 训练 reward 与全局评价 reward 必须分离。
8. ODE 中不得引入 Simulink 器件细节。
9. scenario 必须 seed-controlled。
10. 所有关键物理量和 reward 分解必须可记录。

---

## 23. 第一版 Definition of Done

第一版完成标准：

```text
[ ] 能运行 50-step episode
[ ] obs.shape == (4, 7)
[ ] action.shape == (4, 2)
[ ] no-control 扰动产生非零频率响应
[ ] 至少两个 ESS 频率轨迹不同
[ ] Proposition 1 sanity gate 通过
[ ] reward sanity gate 通过
[ ] train/test scenario split 可重复
[ ] 短 SAC 训练不数值崩溃
[ ] evaluation 能比较 no-control vs trained/fixed policy
[ ] 日志足够解释成功或失败
```

---

## 24. 暂不实现，除非显式批准

以下内容不进入第一版：

```text
NE39
N=2/4/8 弱网对比
短路实验
Simulink bridge
MATLAB Engine
SG 详细动态
governor / AVR / exciter
dq 控制
真实 LoadStep block emulation
policy 自动迁移到 Simulink
通信延迟训练
adaptive inertia baseline [25]
完整 paper 数值对齐
```

---

## 25. 最终判断标准

这个 ODE 环境成功，不等于 Simulink 高保真验证成功。

它的成功标准是：

```text
在论文抽象层级下，正确实现 KD 4-agent DDIC 的物理机制、MDP 接口、reward 语义和训练/评价协议。
```

如果 ODE 成功而 Simulink 失败，优先解释为：

```text
Simulink 当前物理建模层级、扰动注入机制、信号尺度或平台约束与论文抽象模型不一致。
```

如果 ODE 也失败，才应优先怀疑：

```text
论文理解
reward 实现
动作范围
H/D 基值
SAC 训练协议
scenario 设计
```

---
