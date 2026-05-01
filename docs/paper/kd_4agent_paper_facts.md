# KD 4-Agent 论文事实库

> **角色：** KD 4-agent 论文对照的**唯一规范文档（canonical reference）**。回答 "论文怎么说 X" 类问题前必读此文件，不再翻 PDF / 转录 / 其他论文目录文件。
>
> **Source paper:** Yang et al., *"A Distributed Dynamic Inertia-Droop Control Strategy Based on Multi-Agent Deep Reinforcement Learning for Multiple Paralleled VSGs,"* IEEE TPWRS, vol. 38, no. 6, pp. 5602–5617, Nov. 2023. DOI: 10.1109/TPWRS.2022.3221439.
>
> **Scope:** 修改版 Kundur 双区系统 + 4 ESS 主实验（Sec.III + Sec.IV-A 至 IV-E）。**不含**：Sec.IV-F 弱网 N=2/4/8 对比、Sec.IV-G NE39、Sec.IV-G 末尾的短路实验。
>
> **Source of truth:** 论文 PDF + `docs/paper/high_accuracy_transcription_v2.md`（保留作为兜底原文；与 PDF 交叉核实过 §IV-C 累积奖励公式、Fig.3 ESS bus 位置）。
>
> **维护规则:** 只写论文文字 / 公式 / 图表数值。**不**写项目实现、不写偏差、不写历史。论文不变 → 本文件不变。
>
> **写入触发:** 仅当（a）发现转录错误，或（b）§13 Q-list 中的歧义被原文重读消解时。
>
> **本文件统合了以下原文档（已归档至 [`archive/`](archive/)）：** `yang2023-fact-base.md`、`kundur-paper-project-terminology-dictionary.md`（论文侧术语部分）、`v3_paper_alignment_audit.md`（论文 MATCH 列）。归档文件不再维护——查询走本文件。
>
> **保留为 project-side 决策记录的兄弟文档（不在本文件 scope 内）：** `action-range-mapping-deviation.md`（Simulink-side）、`ode_paper_alignment_deviations.md`（ODE-side D1/D2/D3，2026-05-02）、`eval-disturbance-protocol-deviation.md`、`disturbance-protocol-mismatch-fix-report.md`、`kundur-cvs-loadstep-minimal-physical-fix.md`。回答"项目当前为何偏离论文"类问题去查这些。

---

## 0. 速查表（Quick Reference）

| 问 | 答 | 出处 |
|---|---|---|
| 控制对象 | 4 台并联 VSG 储能（ES1–ES4），每台一个 agent | Sec.IV-A |
| 系统 | 修改版 Kundur 双区，G4 → 风电场 W1，新增 100 MW 风电场 W2 在 Bus 8 | Sec.IV-A |
| ESS bus 位置 | ES1@Bus 12, ES2@Bus 16, ES3@Bus 14, ES4@Bus 15 | Fig.3 |
| 邻居数 m | 2（每 agent 通信收 2 个邻居频率） | obs 维度 = 3+2m = 7 |
| 控制步长 / episode 时长 | 0.2 s / 10 s（M=50 步） | Sec.IV-A, Table I |
| 训练集 / 测试集 | 100 / 50 个随机扰动场景 | Sec.IV-A |
| ΔH 范围 | $[-100, +300]$ | Sec.IV-B |
| ΔD 范围 | $[-200, +600]$ | Sec.IV-B |
| 奖励权重 | $\varphi_f=100, \varphi_h=1, \varphi_d=1$ | Sec.IV-B |
| 训练 episodes | 2000；500 ep 后稳定 | Table I, Sec.IV-B |
| 主结果（50 测试 ep 累积频率奖励） | DDIC −8.04 / 自适应惯量 [25] −12.93 / 无控制 −15.2 | Sec.IV-C |
| 通信延迟 0.2 s（DDIC, 50 ep cum） | −9.53 | Sec.IV-E |
| 通信失败影响 | "little influence"（Fig.10 三曲线接近，无具体数值） | Sec.IV-D |

---

## 0.5 论文的控制目标（双约束，Sec.I）

论文 Sec.I 末尾的目标声明（直接引用）：

> "the control objective is to suppress the power oscillation, **and avoid excessive inertia and droop parameter adjustments of the entire system** caused by the collective parameter adjustments. In other words, **under the condition that the total inertia and droop coefficient of the system is not changed as much as possible**, the power oscillation is suppressed by changing the parameter distribution in real time."

**两个并列约束**（不是主目标 + 正则化项关系，是同等重要的双目标）：

1. **目标 1（频率同步）：** 抑制功率/频率振荡 → 由奖励 $r^f$（Eq.15-16）实现
2. **目标 2（系统总储备守恒）：** 系统**总**惯量和**总**阻尼基本不变（即 $\sum\Delta H \approx 0$，$\sum\Delta D \approx 0$）→ 由奖励 $r^h$（Eq.17）和 $r^d$（Eq.18）的"先平均、再平方"形式实现

**为什么 $r^h, r^d$ 用 $-(\bar{\Delta})^2$ 不是 $-\overline{\Delta^2}$：**
后者会要求每个 agent 自己的调整量小（=保守）→ 能力浪费。前者只要求 4 个 agent 的调整量在**全局平均**上接近 0 → 允许 $\Delta H_1 = +200$ 同时 $\Delta H_2 = -200$（重新分布而非缩减）。这正好对应"changing the parameter distribution"而不是"shrinking the parameter range"。

**对实现的含义：** 优化器发现把惯量从 ES1 搬到 ES3 与全部不动是同样满分（只要 mean 守恒）；这是论文 Proposition 1 中"参数与扰动 $k_i$-比例分布"思想的工程化体现。

---

## 1. 系统物理模型（Sec.II-A）

### 1.1 单 VSG 摆动方程（Eq.1）

$$
H_{es,i}\,\Delta\dot{\omega}_i + D_{es,i}\,\Delta\omega_i = \Delta u_i - \Delta P_{es,i}
\tag{1}
$$

| 符号 | 含义 |
|---|---|
| $\Delta\omega_i$ | bus $i$ 的虚拟角频率偏差 |
| $\Delta\dot\omega_i$ | $\Delta\omega_i$ 的导数 |
| $H_{es,i}$ | 储能 $i$ 的虚拟惯量常数（"virtual inertia constant"） |
| $D_{es,i}$ | 储能 $i$ 的虚拟阻尼常数 |
| $\Delta u_i$ | 外部扰动（含本地负荷及通过导纳折算的远端扰动） |
| $\Delta P_{es,i}$ | 储能 $i$ 输出有功 |

**Eq.1 形式注记：** 论文 Eq.1 写为 $H\Delta\dot\omega + D\Delta\omega = \Delta u - \Delta P$，**前面无 `2` 系数、无 $\omega_s$ 系数**。属"控制派集总常数"形式，不直接等同于电机学惯例 $2H_{trad}/\omega_s$ 折算的 swing equation。**$H_{es}$ 的量纲（秒？p.u.？无量纲？）论文未明示**——见 §13 Q-A。

#### 1.1.1 模型尺度边界（关键，决定建模深度）

论文 Sec.II-A 在 Eq.1 之后明确给出尺度声明（直接引用）：

> "Although the inner loop control can also affect the stability of the system, it should be specially noted that this paper mainly studies the relatively slow dynamics of the electromechanical transient. Therefore, the dynamics of the inner loop can be neglected referring to [42]."

**论文研究的尺度：** 机电暂态（electromechanical transient）——典型时间常数秒级、信号在 Hz 级（系统频率附近的慢动态）。

**论文明确忽略的层级：**

| 层级 | 论文是否建模 | 依据 |
|---|---|---|
| 机电暂态（swing dynamics） | ✅ 建模（Eq.1） | Sec.II-A 主题 |
| 网络代数关系（导纳、电压角） | ✅ 建模（Eq.2-4） | Sec.II-A |
| 电压幅值动态 | ❌ 忽略 — "Assuming that the voltage magnitudes are constant"（Sec.II-A，Eq.3 推导前） | Sec.II-A |
| 内环控制（电压/电流 PI、PWM、切换动力学） | ❌ 忽略 | Sec.II-A 上述引文，依据 [42] |
| 电磁暂态（EMT，sub-cycle） | ❌ 不在尺度内 | 同上 |

**对实现的含义：**
- 不需要建三相 abc 模型
- 不需要 PWM 开关频率
- 不需要 dq 坐标内环 PI
- VSG 输出端电压幅值视为恒定（仅角度 $\theta$ 由摆动方程驱动）
- 仿真步长可粗（Sec.IV-A 给的控制步长 0.2 s 远大于 EMT 微秒级）

**参考文献：** [42] = Z. Wang et al., "Analysis of parameter influence on transient active power circulation among different generation units in microgrid," IEEE TIE, 2021。

### 1.2 网络功率方程（Eq.2-3）

纯感性线路下：

$$
P_i = \sum_{j=1}^{N} V_i V_j b_{ij}\sin(\theta_i - \theta_j)
\tag{2}
$$

电压幅值假定恒定 + 平衡点处线性化：

$$
\Delta P_{es,i} = \sum_{j=1}^{N} l_{ij}(\Delta\theta_i - \Delta\theta_j)
\tag{3}
$$

其中 $l_{ij} = \frac{\partial}{\partial\theta_j}\sum_{k=1}^{n} V_iV_kb_{ik}\sin(\theta_i - \theta_k)$；$L=[l_{ij}] \in \mathbb{R}^{N\times N}$ 是网络 Laplacian 矩阵（无向加权）。

### 1.3 矩阵形式（Eq.4）

$$
\begin{cases}
\Delta\dot\theta = \Delta\omega \\
\Delta\dot\omega = H_{es}^{-1}\Delta u - H_{es}^{-1}L\Delta\theta - H_{es}^{-1}D_{es}\Delta\omega
\end{cases}
\tag{4}
$$

$H_{es}=\operatorname{diag}\{H_{es,i}\}$，$D_{es}=\operatorname{diag}\{D_{es,i}\}$。

### 1.4 Kron Reduction（Remark 1）

> "The model (4) adopts Kron reduction and eliminates the bus with no energy storage."

- $\Delta u$ 既可表示储能 bus 的扰动，也可表示无储能 bus 的扰动（按导纳矩阵折算到各储能 bus）
- $\Delta u$ 各分量之和 = 无储能 bus 处的扰动总值
- **注意：** Kron reduction 是 Sec.II-B Proposition 1 推导的数学便利。Sec.IV 仿真用的是修改版 Kundur 全网络（详见 Sec.IV-A）。

### 1.5 Proposition 1（Sec.II-B，理论核心）

**命题原文（直接引用）：**

> 当各储能节点的惯量、阻尼参数和等效扰动都与 $k_i$ 成比例，即 $H_{es,i}=k_iH_{es,0}$，$D_{es,i}=k_iD_{es,0}$，$\Delta u_i = k_i\Delta u_0$，则所有节点的频率动态完全一致。

等价表述：$H_{es,i}/D_{es,i} = H_{es,0}/D_{es,0}$ 且 $D_{es,i}/\Delta u_i = D_{es,0}/\Delta u_0$ 在所有节点 $i$ 上一致。

**注：** $H_{es,0}, D_{es,0}, \Delta u_0$ 没有物理意义，是各节点的"代表值"。

**证明路径（Eq.5-10）：**
对系统 (4) 用 scaled Laplacian $\mathbf{K}^{-\frac{1}{2}}L\mathbf{K}^{-\frac{1}{2}}$ 对角化，传递函数形式：

$$
\Delta\omega(s) = \mathbf{K}^{-\frac{1}{2}}\mathbf{V}\mathbf{H}(s)\mathbf{V}^T\mathbf{K}^{-\frac{1}{2}}\Delta u(s)
\tag{5}
$$

其中 $h_k(s)=\frac{g_0(s)}{1+\frac{\lambda_k}{s}g_0(s)}$，$g_0(s)=\frac{1}{H_{es,0}s+D_{es,0}}$，$\lambda_k$ 为 scaled Laplacian 特征值，$\lambda_0=0$。

代入比例扰动 $\Delta u(s)=\mathbf{K}\mathbf{1}_N\frac{\Delta u_0}{s}$ 后化简（Eq.7-9）：

$$
\Delta\omega(s) = \frac{h_0(s)}{s}\Delta u_0\mathbf{1}_N
\tag{10}
$$

→ 所有储能 bus 频率响应相同，无差模分量、无振荡。

### 1.6 Remark 2（振荡根因）

> Proposition 1 仅给理想条件。实际中扰动位置不确定，参数不能始终与扰动成比例。**振荡根因 = 惯量-阻尼参数与各节点等效扰动的失配**。这说明"调整参数分布"是一条可行的振荡抑制路径。

---

## 2. MDP 表述（Sec.III-A）

### 2.1 形式化框架

部分可观测 Markov 博弈：tuple $\langle\mathcal{N}, S, A, T, R, \gamma\rangle$。

| 元素 | 含义 |
|---|---|
| $\mathcal{N}$ | agent 数 |
| $S$ | 所有 agent 观测的联合状态空间 |
| $A = A_1\times\cdots\times A_N$ | 联合动作空间，$A_i$ 为 agent $i$ 的动作集 |
| $T: S\times A \to \Delta(S)$ | 状态转移概率（**未知** → 用 model-free 算法） |
| $R_i: S\times A\times S \to \mathbb{R}$ | agent $i$ 的奖励函数 |
| $\gamma\in[0,1]$ | 折扣因子 |

状态转移：$s_{t+1}\sim\mathcal{P}(s_t, a_t, \varepsilon_t)$，其中 $\varepsilon_t$ 包含通信延迟、链路状态等不可观测因素。

**论文为何选 model-free（Sec.III-A 文字直接陈述）：**

> "The state transition is not only determined by the current state and the joint action, but also subject to various random factors $\varepsilon_t$, such as the communication delay, the communication link, and other generating units which cannot be observed. **It is intractable to describe the transition model accurately. To address this issue, the paper adopts the model-free algorithm in Section III-B.**"

→ 不是因为系统简单或方便选 model-free，而是论文论证转移模型**不可解析描述**（含通信延迟、链路、其他不可观测发电单元）→ 只能 model-free。这一论证决定了所有 SAC 选择的合理性。

### 2.2 观测向量（Eq.11）

$$
o_{i,t} = (\Delta P_{es,i,t},\ \Delta\omega_{i,t},\ \Delta\dot\omega_{i,t},\ \Delta\omega^c_{i,1,t},\ldots,\Delta\omega^c_{i,m,t},\ \Delta\dot\omega^c_{i,1,t},\ldots,\Delta\dot\omega^c_{i,m,t})
\tag{11}
$$

| 分量 | 含义 |
|---|---|
| $\Delta P_{es,i,t}$ | 本地储能出力 |
| $\Delta\omega_{i,t}, \Delta\dot\omega_{i,t}$ | 本地 bus 频率偏差及变化率 |
| $\Delta\omega^c_{i,j,t}, \Delta\dot\omega^c_{i,j,t}$ | 第 $j$ 个邻居（通过通信链路）的频率偏差及变化率 |
| $m$ | 邻居数 |

- 维度 = $3 + 2m$
- KD 实验中 $m=2$ → $\dim(o_i) = 7$
- 联合状态：$s_t = (o_{1,t},\ldots,o_{N,t})$
- **通信链路中断时：** $\Delta\omega^c_{i,j,t} = 0$，$\Delta\dot\omega^c_{i,j,t} = 0$
- **设计依据（Sec.III-A 文字）：** "**It is worth noting that the observable of the controller cannot be empty.** When the communication link from node $j$ to $i$ is broken, the variables $\Delta\omega^c_{i,j,t}$ and $\Delta\dot\omega^c_{i,j,t}$ are set to zero." → 含义：**写真实零值**进 obs 向量，不是 NaN / mask / 跳过；obs 维度始终保持 $3+2m$ 不变

### 2.3 动作（Eq.12-13）

动作向量 $a_{i,t} = (\Delta H_{es,i,t},\ \Delta D_{es,i,t})$ 受约束（Eq.12）：

$$
\begin{cases}
\Delta H_{es,i,\min} \le \Delta H_{es,i,t} \le \Delta H_{es,i,\max} \\
\Delta D_{es,i,\min} \le \Delta D_{es,i,t} \le \Delta D_{es,i,\max}
\end{cases}
\tag{12}
$$

**论文显式声明（Sec.III-A）：** "The action space of $a_{i,t}$ **is assumed to be continuous** and is restricted as follows"。
→ 这一连续性假定决定了算法选择必须是 policy gradient 类（SAC/PPO/DDPG），排除了 DQN 等离散动作方法。论文 Sec.I 已专门论证："the action space of the value-based DRL is discrete. The second category is the policy gradient method, which is suitable for continuous and high-dimensional action space."

> "The action range can be obtained by the small signal analysis in advance to maintain the small signal stability of the system."

更新规则（Eq.13，**增量语义**）：

$$
\begin{cases}
H_{es,i,t} = H_{es,i,0} + \Delta H_{es,i,t} \\
D_{es,i,t} = D_{es,i,0} + \Delta D_{es,i,t}
\end{cases}
\tag{13}
$$

**KD 实验中具体的 ΔH/ΔD 范围**（Sec.IV-B 文字）：
- $\Delta H_{es,i} \in [-100, +300]$
- $\Delta D_{es,i} \in [-200, +600]$
- $H_{es,i,0}$、$D_{es,i,0}$ 基值数值**论文未给**（见 §13 Q-D）

### 2.4 奖励（Eq.14-18）

#### 2.4.1 总奖励（Eq.14）

$$
r_{i,t} = \varphi_f r^f_{i,t} + \varphi_h r^h_{i,t} + \varphi_d r^d_{i,t}
\tag{14}
$$

KD 实验中：$\varphi_f=100$，$\varphi_h=1$，$\varphi_d=1$（Sec.IV-B 文字）。

#### 2.4.2 频率同步惩罚 $r^f$（Eq.15-16）

$$
r^f_{i,t} = -(\Delta\omega_{i,t} - \Delta\bar\omega_{i,t})^2 - \sum_{j=1}^{m}(\Delta\omega^c_{i,j,t} - \Delta\bar\omega_{i,t})^2 \eta_{j,t}
\tag{15}
$$

其中局部加权平均频率（Eq.16）：

$$
\Delta\bar\omega_{i,t} = \frac{\Delta\omega_{i,t} + \sum_{j=1}^{m}\Delta\omega^c_{i,j,t}\eta_{j,t}}{1 + \sum_{j=1}^{m}\eta_{j,t}}
\tag{16}
$$

| 符号 | 含义 |
|---|---|
| $\eta_{j,t}\in\{0,1\}$ | 通信链路 $j$ 是否正常（1=正常，0=中断） |
| $\Delta\bar\omega_{i,t}$ | agent $i$ 的局部加权平均（仅算自己 + 活跃邻居） |

**关键语义（论文文字直接说明，Sec.III-A）：**

> "When the frequency of all energy storage nodes is consistent during the transient process $\Delta\omega_{i,t} = \Delta\omega_{j,t}$, there will be no oscillation and the penalty for the frequency deviation of each agent should also be zero."

→ $r^f$ 衡量 **同步度**（节点之间一致性），**不衡量频率恢复度**（不要求 $\Delta\omega \to 0$）。所有节点偏差相同时（哪怕都偏离额定）$r^f=0$。

**通信中断处理：** 链路 $j$ 中断 → $\Delta\omega^c_{i,j,t} = 0$（错误值）→ Eq.16 分母自动变小（因 $\eta_{j,t}=0$），保证 $\Delta\bar\omega_{i,t}$ 仅基于活跃信息。

#### 2.4.3 惯量调整惩罚 $r^h$（Eq.17）

$$
r^h_{i,t} = -(\Delta H_{avg,i,t})^2
\tag{17}
$$

#### 2.4.4 阻尼调整惩罚 $r^d$（Eq.18）

$$
r^d_{i,t} = -(\Delta D_{avg,i,t})^2
\tag{18}
$$

**$\Delta H_{avg,i,t}$ / $\Delta D_{avg,i,t}$ 的来源（Sec.III-A 文字）：**

> "This paper assumes that there are distributed average inertia and droop adjustment estimators, similar to [45] in each energy storage agent. The energy storage agent can also obtain average parameter adjustments calculated by the grid operator."

- 由"分布式平均估计器"或网格运营商提供
- **公式形式：先平均、再平方**（即 $-(\bar{\Delta H})^2$，**不是** $-\overline{\Delta H^2}$）
- "average" 是按全局平均还是邻居平均，**论文未明确**（见 §13 Q-B）

#### 2.4.5 训练时不引入通信延迟（论文文字 + 论证）

**事实：**

> "complex communication conditions such as communication delay, data loss, and bad data, are not considered during the off-line training process. Only communication link outage is considered during the off-line training process, which is the most serious communication failure."

→ **训练阶段：** 仅 $\eta_{j,t}\in\{0,1\}$ 随机中断
→ **离线测试阶段：** 引入通信延迟（Sec.IV-E）

**论文给的论证（Sec.III-A，理解奖励语义的关键）：**

> "It is worth emphasizing that the agent can only obtain neighboring frequency information, rather than the global frequency information. The designed frequency reward is only related to the observed frequency. **If the observed $\Delta\omega^c_{i,j,t}$ is inconsistent with the actual value $\Delta\omega_{j,t}$, the frequency reward $r^f_{i,t}$ will be wrong during the training process.** To ensure that the reward function can correctly evaluate the action taken by the agent, complex communication conditions ... are not considered during the off-line training process."

**含义：**
- $r^f$ 是用 obs 中的邻居频率算的，不是用真实全局频率
- 通信延迟会让 obs ≠ actual → $r^f$ 算错 → SAC 拿到错误反馈
- 通信中断 ($\eta_j = 0$) 是"诚实的零"——obs 与 reward 都基于"我没收到"这个事实，一致；可学
- 故训练只引入中断，把延迟/丢包/坏值留给在线测试（届时不用 reward 函数）

**对在线控制（Sec.III-A 末段）：** "During the online control process, the reward function is no longer necessary for the controller. When the most serious communication failures have been considered during the training, the other communication conditions can also be handled during the online control."

### 2.5 总奖励 $r_{i,t}=0$ 充要条件（Sec.III-C 文字）

$$
r_{i,t} = 0 \iff (\Delta\omega_{i,t} = \Delta\bar\omega_{i,t}) \ \wedge\ (\Delta H_{avg,i,t} = 0) \ \wedge\ (\Delta D_{avg,i,t} = 0)
$$

单独 $r^f_{i,t}=0$ 仅需 $\Delta\omega_{i,t} = \Delta\bar\omega_{i,t}$（agent $i$ 与活跃邻居的均值一致）。

---

## 3. SAC 算法（Sec.III-B）

### 3.0 MARL 架构分类与论文选择（Sec.III-B 开头）

论文明确将 MARL 算法分为三类，并陈述为何选第三类：

| 架构 | 论文描述 | 论文评价 |
|---|---|---|
| **Decentralized**（独立学习） | "each agent regards other agents as part of the environment and directly applies the single-agent algorithm to interact with the environment [46]" | "ignoring the nature of multiagent environments, independent learning methods cannot guarantee the stationarity of the environment and may fail to converge [47]" |
| **Centralized** | "a centralized controller that can collect the joint state, action, and reward information of all agents" | "effectively alleviates the non-stationarity"，但"with the increase in the number of agents, the state space and computational complexity ... will increase significantly" |
| **Distributed**（论文选择） | "each agent can exchange information with neighboring nodes through a communication network" | "can not only maintain the scalability of decentralized learning but also alleviate the instability that may occur in independent learning" |

> "Hence, this paper adopts a distributed learning architecture."

**对实现的含义：**
- 每 agent 跑**自己**的 SAC（不是一个 SAC 控所有 agent）
- 但 obs 向量中包含邻居频率信息（Eq.11）→ 不是 decentralized
- 共享内容**仅限频率与频率变化率**，不共享 actor / critic 参数
- 训练时不需要 global state，仅 local + neighbor

### 3.1 最大熵 RL 目标（Eq.19）

$$
\max J(\pi) = \sum_t \mathbb{E}_{(s_t,a_t)\sim\rho_\pi}\gamma^t\bigl[r(s_t,a_t) + \alpha\cdot H(\pi(\cdot|s_t))\bigr]
\tag{19}
$$

$\alpha$：熵参数（决定熵相对奖励的重要性）；$H(\pi(\cdot|s_t))$：策略熵。

### 3.2 Q 函数（Eq.20）

$$
Q_\pi(s_t, a_t) = r(s_t, a_t) + \sum_{k=t+1}^{\infty}\mathbb{E}_{(s_t,a_t)\sim\rho_\pi}\bigl[\gamma^k r(s_k, a_k)\bigr]
\tag{20}
$$

### 3.3 Critic 损失（Eq.21）

$$
J_Q(\theta) = \mathbb{E}_{(s_t,a_t)\sim D}\left[\frac{1}{2}\Bigl(Q_\theta(s_t,a_t) - \bigl(r(s_t,a_t) + \gamma\,\mathbb{E}_{s_{t+1}\sim\rho}[V_{\bar\theta}(s_{t+1})]\bigr)\Bigr)^2\right]
\tag{21}
$$

$D$：经验回放缓冲；$V_{\bar\theta}$：目标网络估计 state-value。

### 3.4 Actor 损失（Eq.22）

$$
J_\pi(\phi) = \mathbb{E}_{s_t\sim D}\left[\mathbb{E}_{a_t\sim\pi_\phi}\bigl[\alpha\log\pi_\phi(a_t|s_t) - Q_\theta(s_t,a_t)\bigr]\right]
\tag{22}
$$

### 3.5 熵参数自学习（Eq.23）

$$
J(\alpha) = \mathbb{E}_{a_t\sim\pi_\phi}\bigl[-\alpha\log\pi_\phi(a_t|s_t) - \alpha\bar H\bigr]
\tag{23}
$$

$\bar H$：最小策略熵阈值。

---

## 4. DDIC 训练算法（Sec.III-C，Algorithm 1）

```
Algorithm 1. Training Process of the Proposed Algorithm
─────────────────────────────────────────────────────────
1:  Input: φ, θ
2:  for each agent i do
3:      Initialize the parameters of actor network π_{φ_i} randomly.
4:      Initialize the parameters of critic network Q_{θ_i} randomly.
5:      Initialize the empty replay buffer D_i.
6:  for each episode do:
7:      for each time step environment do:
8:          Obtain the parameter tuning action a_{i,t}
            based on actor network for each agent i.
9:          Execute action a_t = (a_{1,t}, ..., a_{N,t}).
10:         Obtain r_{i,t} and o_{i,t+1} for each agent i.
11:         Store transition (o_{i,t}, a_{i,t}, r_{i,t}, o_{i,t+1})
            into buffer D_i for each agent i.
12:     for each gradient step do:
13:         for each agent i do:
14:             Update the weights of actor network π_{φ_i}.
15:             Update the weights of critic network Q_{θ_i}.
16:             Clear the buffer D_i.            ← 见 §12.A
17: Output: φ, θ
```

**核心结构：**
- **网络参数独立**：每个储能 agent 拥有独立 actor + critic + replay buffer（不是参数共享 / CTDE）
- **distributed 学习架构**（Sec.III-B 术语，见 §3.0）：每 agent 仅依赖本地观测 + 邻居频率信息，但通过 obs（Eq.11）共享邻居频率——不是 decentralized 把别人当环境
- agent 数增加时，每个 agent 的网络维度不变 → scalable

---

## 5. 训练超参（Sec.IV-A，Table I）

| 参数 | 值 |
|---|---|
| Actor 学习率 | $3\times 10^{-4}$ |
| Critic 学习率 | $3\times 10^{-4}$ |
| $\alpha$ 学习率 | $3\times 10^{-4}$ |
| 训练 episodes | 2000 |
| 折扣因子 $\gamma$ | 0.99 |
| Mini-batch 大小 | 256 |
| Replay buffer 大小 | 10000 |
| 每 episode 步数 $M$ | 50 |

**网络结构（Sec.IV-A 文字）：**
- Actor 与 Critic 均为 4 层全连接，每层 128 个隐藏单元
- 框架：Python + PyTorch

---

## 6. 仿真设置（Sec.IV-A）

### 6.1 系统拓扑（修改版 Kundur 双区）

> "The simulation is carried out on the modified Kundur two-area system, including two wind farms and four energy storage systems."

**与经典 Kundur [49] 的修改：**
1. **G4 替换为同容量风电场（W1）** — Sec.IV-A "Generator 4 in Kundur two-area system is replaced by a wind farm with the same capacity."
2. **新增 100 MW 风电场（W2）于 Bus 8** — "a 100 MW wind farm is connected to bus 8"
3. **新增 4 台储能（ES1–ES4）"with loads, separately connected to different areas"** — 每台 ESS 母线**同时**挂载本地负荷

**4 ESS 母线位置（来自 Fig.3）：**

| ESS | bus |
|---|---|
| ES1 | Bus 12 |
| ES2 | Bus 16 |
| ES3 | Bus 14 |
| ES4 | Bus 15 |

**Fig.3 显示的通信链路：** 4 ESS 之间用绿色虚线表示通信链路；具体拓扑结构论文文字未给，需从图中识别（每 agent $m=2$ 邻居）。

**额定频率：** 50 Hz（Kundur 原系统约定，论文文字未单独声明，由 [49] 隐含）。

### 6.2 仿真参数

| 项 | 值 |
|---|---|
| 仿真工具 | MATLAB-Simulink，Python 通过接口控制 |
| 控制步长 $\Delta t$ | 0.2 s |
| 每 episode 仿真时长 | 10 s（即 $M=50$ 步） |
| 硬件 | Intel Core i7-11370 CPU @ 3.30 GHz（8 核）+ NVIDIA MX 450 GPU |

### 6.3 训练集 / 测试集

> "100 randomly generated data set is regarded as the training set. 50 randomly generated data set is regarded as the test set."

- 扰动位置和大小：按负荷和风电容量范围**随机生成**
- 通信链路故障：**随机生成**
- 训练集 / 测试集是否在整个训练过程中**固定**还是**每次重采样**：论文未明示（见 §13 Q-C）

---

## 7. 训练性能（Sec.IV-B）

**观察（Sec.IV-B 文字）：**

> "After 500 episodes, all the performance indexes gradually stabilize near the optimal value."

- **动作范围**（KD 实验具体值）：$\Delta H \in [-100, +300]$，$\Delta D \in [-200, +600]$
- **奖励权重**（KD 实验具体值）：$r_f = 100$，$r_h = 1$，$r_d = 1$（论文 Sec.IV-B 用 $r_*$ 符号；与 Eq.14 中的 $\varphi_*$ 对应）
- **Fig.4：** 训练曲线
  - (a) 总 episode reward + Inertia + Droop + 100×Frequency 分量
  - (b)–(e) ES1–ES4 各自 episode reward
  - 深色线 = 平均 episode reward，浅色 shade = 实际 episode 跨扰动的范围

---

## 8. 测试评价 — Load Step（Sec.IV-C）

### 8.1 测试集

50 个不同位置、不同大小的功率阶跃扰动，随机生成。

### 8.2 评价用频率奖励公式（Sec.IV-C 文字）

> "It should be noted that to illustrate the global performance of the system, the frequency reward used in the test set is **global**, rather than the sum of four locally available frequency rewards."

每 episode 的频率奖励（论文文字直接给的形式）：

$$
\text{(per-episode reward)} = -\sum_{t=1}^{M}\sum_{i=1}^{N}(f_{i,t} - \bar f_t)^2,\qquad \bar f_t = \sum_{i=1}^{N} f_{i,t}\big/N
$$

- $\bar f_t$：论文文字定义为 "the average frequency of all energy storage nodes at time step $t$"
- 参数：$M = 50$，$N = 4$
- **注：** 论文用的是 $f_{i,t}$（频率本身），不是 $\Delta f_{i,t}$（频率偏差）。但因为 $(f_i - \bar f)^2 = (\Delta f_i - \overline{\Delta f})^2$（减去均值消除常数偏移），两种写法数值等价

**关键差异 — 训练 vs 评价：**

| 阶段 | 用的奖励 | 平均范围 |
|---|---|---|
| 训练 | 各 agent 局部 $r^f_{i,t}$（Eq.15） | $\bar\omega$ 仅含 agent $i$ 自己 + 活跃邻居 |
| 测试评价 | **全局**频率奖励（上式） | $\bar f_t$ 是**全部 4 个 ESS 节点**的均值 |

**归一化：** 上述公式**外层无 $1/M$ 或 $1/N$**——只有 $\bar f_t$ 内部有 $1/N$。50 个测试 episode 的"累积奖励"是外层把 50 episode 的 per-episode reward 直接相加（Fig.5 是 running cumulative）。

### 8.3 50 测试 episode 累积奖励

| 方法 | 累积频率奖励 |
|---|---|
| **DDIC（提议方法）** | **−8.04** |
| 自适应惯量控制 [25] | −12.93 |
| 无额外控制 | **−15.2** |

来源：Sec.IV-C 文字 + Fig.5。

### 8.4 单 episode 数值（load step 1 / load step 2）

**扰动定义（Sec.IV-C 文字）：**

> "Load step 1 and load step 2 represent the sudden load reduction of 248 MW at bus 14 and the sudden load increase of 188 MW at bus 15, respectively."

| 场景 | 扰动 | 无控制 | DDIC |
|---|---|---|---|
| Load step 1 | Bus 14：负荷减少 248 MW | −1.61 | −0.68 |
| Load step 2 | Bus 15：负荷增加 188 MW | −0.80 | −0.52 |

**观察（Sec.IV-C 文字）：**
- 无控制时（Fig.6, Fig.8）：所有 ESS 惯量/阻尼参数相同 → 离扰动 bus 最近的节点频率变化最快（"the frequency of the bus which is the nearest to the disturbance bus changes the fastest"）
- ES1 + ES2 离扰动 bus 较远 → 频率变化较慢
- 频率失同步 → 引发振荡
- DDIC 控制时（Fig.7, Fig.9）：根据邻居频率动态调 H/D，让频率尽量同步；且 $\Delta H_{avg}$、$\Delta D_{avg}$ 维持低水平（系统总惯量/阻尼储备基本不变）

### 8.5 对应图

Fig.5（累积奖励对比）、Fig.6/8（无控制 load step 1/2）、Fig.7/9（DDIC load step 1/2）——详见 §15 图速查。

---

## 9. 通信失败（Sec.IV-D）

**设置：**
- 在 Sec.IV-C 测试集基础上，加入**随机**通信失败
- Fig.11 展示的具体场景：load step 1 + ES1 与 ES2 之间通信中断

**结果（Sec.IV-D 文字）：**

> "communication failure has little influence on the cumulative reward for frequency."

- **论文未给具体数值**（仅说"little influence"）
- Fig.10 展示三条累积奖励曲线：无控制 / DDIC / DDIC+通信失败 → 三曲线形态接近，DDIC+通信失败 ≈ DDIC

---

## 10. 通信延迟（Sec.IV-E）

**设置：**
- 邻居 ES 之间设置 **0.2 s** 通信延迟
- 基于 Sec.IV-C 测试集

**关键说明（论文文字）：**

> "It should be noted that communication delay is not considered during training."

→ 通信延迟仅在**离线测试**阶段引入；训练阶段无延迟（仅 $\eta\in\{0,1\}$ 随机中断）。

**结果：**

| 场景 | 50 测试 episode 累积奖励 |
|---|---|
| DDIC + 0.2 s 通信延迟 | **−9.53** |

→ 比无延迟 DDIC（−8.04）略差，但仍显著优于无控制（−15.2）。

**对应图：** Fig.12（累积奖励对比）、Fig.13（DDIC + 0.2 s 延迟下 load step 1 动态）——详见 §15。

---

## 11. Remark 3（Sec.III-C，对扩展性的说明）

> 当储能规模增大时，并非所有储能都能从邻居获得信息（受实际条件限制）。需要选择合适的 agent 与通信链路：
> - 离扰动 bus 较远且彼此接近的储能 → 频率动态相似 → 共用一个 agent 即可
> - 通信图的选择对决策影响很大；建议每 agent 尽量观察"频率差异较大"的节点
> → 让每个 agent 用部分可观测信息更准确地推断系统状态

（这是论文给的扩展性建议，KD 4-agent 主实验未应用。）

---

## 12. 陷阱速查（Common Traps）

正文已展开；此处只一行 + 跳转。读论文时易在这些点上滑过去。

| # | 容易这样错读 | 论文实际是这样 | 详见 |
|---|---|---|---|
| 12.A | 把 Algorithm 1 line 16 "Clear buffer" 当真 | 与 Table I (size=10000, batch=256, M=50) 内部矛盾——50 条经验填不出 256 batch；论文未给调和方案 | §4 + §5 |
| 12.B | 把 $r^f$ 当频率回额定值惩罚 | $r^f$ 衡量**节点间同步度**；所有节点同偏差时 $r^f=0$。频率恢复由 UFLS/governor 负责，不在论文 scope | §2.4.2 |
| 12.C | 把 $r^h, r^d$ 算成 $-\overline{\Delta_i^2}$（先平方再平均） | 论文 Eq.17-18 是 $-(\bar{\Delta})^2$（先平均再平方）。允许 $+200/-200$ 重新分布得满分；不奖励"每 agent 自己保守" | §0.5 + §2.4.3 |
| 12.D | 把 obs dim = 7 当通式 | 通式 $\dim(o_i) = 3+2m$；KD 实验 $m=2$ 才 7 | §2.2 |
| 12.E | 把"each agent independently"读作 decentralized | 论文是 **distributed**：obs 含邻居频率（Eq.11）。Sec.III-C "independently" 指**网络参数独立**，不是 Sec.III-B "independent learning = decentralized" | §3.0 |
| 12.F | 训练 $r^f$ 直接套到测试评价 | 训练 $\bar\omega$ = 局部加权均值（agent $i$ + 活跃邻居）；评价 $\bar f_t$ = 全局均值（所有 4 个 ESS） | §2.4.2 + §8.2 |
| 12.G | 在训练阶段加通信延迟 | 论文论证：obs ≠ actual → $r^f$ 训练时被算错。延迟只在离线测试（Sec.IV-E） | §2.4.5 |
| 12.H | 把 Bus 14/15 当成纯 ESS 终端而非 load 节点 | 论文 Sec.IV-A "with loads"——ESS 母线**同时挂载**本地负荷。Sec.IV-C 切的 248 MW 就是这本地负荷 | §6.1 |
| 12.I | 用电机学 $\frac{2H}{\omega_s}\dot\omega$ 直接对接 Eq.1 | 论文 Eq.1 是 $H\dot\omega + D\omega = \Delta u - \Delta P$（控制派集总形式，无 `2`、无 $\omega_s$）。$H$ 量纲未明示 | §1.1 + §13 Q-A |
| 12.J | 实现时去建 PWM / 电流环 / 三相切换 | Sec.II-A 明确尺度：仅机电暂态；内环、电压幅值动态、EMT 都不在论文 scope | §1.1.1 |
| 12.K | $\Delta\omega^c=0$ 当成"邻居数据缺失" | 论文 Sec.III-A "the observable cannot be empty"——写**真实零**进 obs 向量；维度始终 $3+2m$ | §2.2 |

---

## 13. 论文未明示项（无法从原文消除的歧义）

只列论文文字未给清楚的事项；不写解决方案（外部解决）。

| ID | 问题 | 出处 |
|---|---|---|
| Q-A | $H_{es,i}$ 的量纲（秒？p.u.？无量纲？）| Eq.1 形式 + ΔH 范围 [−100, 300] 都无单位标注 |
| Q-B | $\Delta H_{avg}$ / $\Delta D_{avg}$ 是全局均值还是邻居均值？ | Sec.III-A 仅说 "distributed average estimators ... or grid operator" |
| Q-C | 训练 100 / 测试 50 场景是固定不变还是每 reset 重采样？ | Sec.IV-A 仅说 "randomly generated"，未明确生命周期 |
| Q-D | $H_{es,i,0}$、$D_{es,i,0}$ 基值数值是多少？ | 给 Δ 范围而未给 baseline |
| Q-E | 每 episode 多少次梯度更新（Algorithm 1 line 12 内层循环次数）？ | Algorithm 1 + Table I 均未指定 |
| Q-F | 4 ESS 之间的具体通信拓扑（每 agent 哪两个邻居）？ | Sec.IV-A 未给文字；需从 Fig.3 通信链路（绿虚线）视觉识别 |
| Q-G | Algorithm 1 line 16 buffer clear 与 Table I (size=10000, batch=256) 矛盾如何调和？ | 论文内部矛盾，未给调和说明（见 §12.A） |

---

## 14. 公式速查（Eq.1-23）

按论文编号一行索引；详式见对应正文段落。

| Eq | 内容（一行）| 章节 | 本文位置 |
|---|---|---|---|
| 1 | 单 VSG 摆动 $H\Delta\dot\omega + D\Delta\omega = \Delta u - \Delta P$（控制派形式） | II-A | §1.1 |
| 2 | 网络功率 $P_i = \sum_j V_iV_jb_{ij}\sin(\theta_i-\theta_j)$ | II-A | §1.2 |
| 3 | 线性化 $\Delta P_{es,i} = \sum_j l_{ij}(\Delta\theta_i-\Delta\theta_j)$ | II-A | §1.2 |
| 4 | swing+网络合并矩阵形式 ($H^{-1}\Delta u - H^{-1}L\Delta\theta - H^{-1}D\Delta\omega$) | II-A | §1.3 |
| 5 | scaled Laplacian 对角化 $\Delta\omega(s) = K^{-1/2}VH(s)V^TK^{-1/2}\Delta u(s)$ | II-B | §1.5 |
| 6 | $h_k(s) = g_0(s) / (1 + \frac{\lambda_k}{s}g_0(s))$ | II-B | §1.5 |
| 7-9 | Proposition 1 推导中间步骤（$v_0$ 展开 + 正交性） | II-B | §1.5 |
| 10 | 同步等价 $\Delta\omega(s) = \frac{h_0(s)}{s}\Delta u_0\mathbf{1}_N$（所有节点频率响应相同） | II-B | §1.5 |
| 11 | 观测 $o_{i,t} = (\Delta P_{es,i}, \Delta\omega_i, \Delta\dot\omega_i, \Delta\omega^c_{i,1..m}, \Delta\dot\omega^c_{i,1..m})$，$\dim = 3+2m$ | III-A | §2.2 |
| 12 | 动作约束 $\Delta H_i \in [\Delta H_{\min}, \Delta H_{\max}]$，$\Delta D_i \in [\Delta D_{\min}, \Delta D_{\max}]$ | III-A | §2.3 |
| 13 | 参数更新 $H_{i,t} = H_{i,0} + \Delta H_{i,t}$（增量语义） | III-A | §2.3 |
| 14 | 总奖励 $r_i = \varphi_f r^f_i + \varphi_h r^h_i + \varphi_d r^d_i$ | III-A | §2.4.1 |
| 15 | $r^f_i = -(\Delta\omega_i - \bar{\Delta\omega}_i)^2 - \sum_j(\Delta\omega^c_{i,j} - \bar{\Delta\omega}_i)^2\eta_j$ | III-A | §2.4.2 |
| 16 | $\bar{\Delta\omega}_i = (\Delta\omega_i + \sum_j\Delta\omega^c_{i,j}\eta_j) / (1 + \sum_j\eta_j)$ | III-A | §2.4.2 |
| 17 | $r^h_i = -(\Delta H_{avg,i})^2$（先平均、再平方） | III-A | §2.4.3 |
| 18 | $r^d_i = -(\Delta D_{avg,i})^2$ | III-A | §2.4.4 |
| 19 | SAC 最大熵目标 $\max J(\pi) = \sum_t \mathbb{E}[\gamma^t(r + \alpha H(\pi))]$ | III-B | §3.1 |
| 20 | Q 函数 $Q_\pi(s,a) = r + \sum_{k>t}\mathbb{E}[\gamma^k r_k]$ | III-B | §3.2 |
| 21 | Critic loss $J_Q = \mathbb{E}[\frac{1}{2}(Q - (r + \gamma\mathbb{E}[V_{\bar\theta}]))^2]$ | III-B | §3.3 |
| 22 | Actor loss $J_\pi = \mathbb{E}[\alpha\log\pi - Q]$（KL 形式） | III-B | §3.4 |
| 23 | 熵参数 loss $J(\alpha) = \mathbb{E}[-\alpha\log\pi - \alpha\bar H]$（auto-α） | III-B | §3.5 |

---

## 15. 图速查（Fig.1-13，KD 4-agent 范围）

不在 KD 4-agent 主实验内的图（Fig.14-21）已剔除。

| Fig | 内容 | 章节 | 本文位置 |
|---|---|---|---|
| 1 | 整体控制架构（n 个 ESS + 通信 + 协调）| III | — |
| 2 | DDIC 框架图（actor/critic + buffer + 邻居信息） | III-C | §4 |
| 3 | 修改版 Kundur 单线图（4 ESS bus 位置 + 绿色虚线通信链路 + W1/W2 + G1/G2/G3）| IV-A | §6.1 |
| 4 | 训练性能（5 子图：a=Total + 100×Frequency + Inertia + Droop；b-e=ES1-ES4 各自 episode reward）| IV-B | §7 |
| 5 | 50 测试 ep 累积频率奖励对比（无控制 / 自适应惯量 [25] / DDIC，三曲线终点 −15.2 / −12.93 / −8.04） | IV-C | §8.3 |
| 6 | 无控制下 load step 1 系统动态（$\Delta P_{es}$ + $\Delta f_{es}$，4 条 ESS 曲线，6 s 窗口） | IV-C | §8.4 |
| 7 | DDIC 控制下 load step 1（4 子图：$\Delta P$ / $\Delta f$ / $\Delta H$ / $\Delta D$，含 $H_{avg}$ / $D_{avg}$ 虚线） | IV-C | §8.4 |
| 8 | 无控制下 load step 2 | IV-C | §8.4 |
| 9 | DDIC 控制下 load step 2 | IV-C | §8.4 |
| 10 | 通信失败累积奖励对比（无控制 / DDIC / DDIC+comm-fail，三曲线接近）| IV-D | §9 |
| 11 | DDIC + 通信失败下 load step 1（ES1-ES2 通信中断）| IV-D | §9 |
| 12 | 通信延迟累积奖励对比（DDIC+0.2s delay 终点 −9.53）| IV-E | §10 |
| 13 | DDIC + 0.2 s 通信延迟下 load step 1 | IV-E | §10 |

---

## 16. 关键外部引用（影响 KD 4-agent 解读的 5 个引用）

论文引用很多文献做对比/铺垫；这里只列**直接影响 KD 4-agent 实现或解读**的 5 个，注明它在论文中扮演什么角色。

| 引用 | 论文中作用 | 具体出处（论文章节）| 影响 |
|---|---|---|---|
| [25] Fu et al., "Power oscillation suppression in multi-VSG grid with adaptive virtual inertia," Int. J. Elect. Power Energy Syst. 135, 2022 | **Baseline 对比方法**（"adaptive inertia control"） | Sec.IV-C 与 Sec.IV-G | KD 实验中 −12.93 cum 那条曲线就是这个方法。要复现完整对比必须实现它 |
| [42] Z. Wang et al., "Analysis of parameter influence on transient active power circulation among different generation units in microgrid," IEEE TIE 68(1):248-257, 2021 | **"内环可忽略"的论证依据** | Sec.II-A Eq.1 后 | 见 §1.1.1。它支持的是"机电暂态时间尺度上内环 PI/PWM 可被压平" |
| [45] Freeman et al., "Stability and convergence properties of dynamic average consensus estimators," 45th IEEE CDC, 2006 | **"分布式平均估计器"的引用源** | Sec.III-A，$r^h$/$r^d$ 段 | 用于解释 $\Delta H_{avg}$/$\Delta D_{avg}$ 的获取方式（但论文未给具体协议——见 Q-B） |
| [48] Haarnoja et al., "Soft actor-critic," ICML 2018 | **SAC 原始论文** | Sec.III-B | Eq.19-23 直接来自这里。论文未指明用 fixed-α 还是 auto-α，但 Eq.23 含 $J(\alpha)$ → 可推论为 auto-α 变体 |
| [49] Kundur, *Power System Stability and Control*, 1994 | **底层物理系统参考** | Sec.IV-A："The parameters of the generators can be obtained from the classic Kundur two-area system [49]" | 4 SG 的 $H$/$D$/$R$ 参数、线路阻抗、负荷/容性补偿来源；论文不重列 → 复现需直接查 [49] |

**实现含义：** 完整复现 KD 4-agent 实验需要 [25]+[49] 至少；[42] 给建模依据；[45]/[48] 是算法层引用，标准 SAC 实现已隐含。

---

*End of `kd_4agent_paper_facts.md`*
*Maintained for: KD 4-agent 论文对照（替代直接读 PDF）*
*Last verified against PDF: 2026-05-01（§IV-C 累积奖励公式 + Fig.3 ESS bus 位置）*
