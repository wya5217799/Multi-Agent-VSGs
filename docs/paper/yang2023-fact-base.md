# Yang et al. TPWRS 2023 — 结构化事实基底

> **用途：** 本文档是复现该论文时唯一的事实参考基底。  
> **维护规则：** 只写已核实事实；不确定点必须明确标注；新核实内容增量插入原有结构，不另开文件。  
> **优先级：** 本文档 > 任何临时分析 > 模型的自由推断。

---

## 0. 基本信息

| 字段 | 内容 |
|------|------|
| 标题 | A Distributed Dynamic Inertia-Droop Control Strategy Based on Multi-Agent Deep Reinforcement Learning for Multiple Paralleled VSGs |
| 期刊 | IEEE Transactions on Power Systems |
| DOI | 10.1109/TPWRS.2022.3221439 |
| 投稿 | 2022-05-02；修改 2022-09-29；录用 2022-11-04；发表 2022-11-11；当前版本 2023-10-20 |
| 作者 | Qiufan Yang, Linfang Yan, Xia Chen, Yin Chen（通信）, Jinyu Wen |
| 单位 | 华中科技大学 SEEE；国网苏州城市能源研究院 |
| 论文编号 | TPWRS-00646-2022 |

---

## 1. 核心问题定义

**原文直接陈述（Abstract + Sec.I）：**

- 多台 VSG 并网时，若惯量-阻尼参数与等效扰动存在分布失配，会产生功率振荡。
- 目标：实时协调调整多 VSG 的惯量/阻尼参数分布，以抑制振荡，同时避免系统整体参数储备的过度调整。
- 方法类别：模型无关（model-free）、分布式（distributed）、多智能体深度强化学习（MADRL）。

**论文明确不解决的问题（推论，有文本支撑）：**

- 不恢复频率到额定值（奖励目标是节点间同步，不是回 50 Hz / 60 Hz）。
- 每台储能独立控制自身参数，但研究对象是多台协作的整体效果，而非单台孤立性能。
- 不给出模型——transition function 未知，model-free。

---

## 2. 系统模型

### 2.1 VSG 动力学方程（Sec.II-A，Eq.1）

$$H_{es,i}\Delta\dot{\omega}_i + D_{es,i}\Delta\omega_i = \Delta u_i - \Delta P_{es,i}$$

- $H_{es,i}$：虚拟惯量常数（论文称"virtual inertia constant"）  
  > **Q7 原文事实（2026-04-21 核查 `high_accuracy_transcription_cn.md`）：** 论文对 $H_{es}$ 的全部描述仅有"虚拟惯量常数"（Sec.II-A Eq.1 后注释、Eq.4 后注释），**未给出量纲**（秒？p.u.？无量纲？均无明示）。Eq.(1) 原文形式为 $H\Delta\dot\omega + D\Delta\omega = \Delta u - \Delta P$——**无 `2` 系数、无 `ω_s` 系数**，属控制派集总常数形式，不等同于电机学标准 $2H_{trad}/\omega_s$ 折算。Sec.IV-B 只给 $\Delta H$ 调节范围 $[-100,300]$，不给基准 $H_{es,0}$ 数值。
  >
  > **项目工作假设（推断，非论文事实）：** 代码 `env/ode/power_system.py:204` 实现 `2H_code·ωdot = ω_s·(Δu - coupling) - D·ω`（电机学标准形式，rad/s 基值），与论文 Eq.(1) 集总形式通过数值映射 $H_{paper} = 2·H_{code}$ 可做 RHS 等价。选用电机学形式是为与 Simulink 发电机模型 [49] 阻抗基值对齐，**该 2 倍映射为项目推断**，论文未明示、也未否定。引用该映射时必须标注"项目推断"；不得以"论文事实"名义引用。详见 `env/ode/NOTES.md` M1 段。
- $D_{es,i}$：虚拟阻尼常数
- $\Delta\omega_i$：频率偏差（p.u.，相对于额定角频率）
- $\Delta u_i$：等效外部扰动（包括本地负荷和通过导纳矩阵折算的外部扰动）
- $\Delta P_{es,i}$：储能出力

**注：** 内环控制动态在该论文中被忽略（文中明确说明，只研究机电暂态的相对慢动态，Eq.1 前文字）。

### 2.2 矩阵形式（Eq.4）

$$\Delta\dot{\theta} = \Delta\omega, \quad \Delta\dot{\omega} = H_{es}^{-1}\Delta u - H_{es}^{-1}L\Delta\theta - H_{es}^{-1}D_{es}\Delta\omega$$

- $L$：Kron-reduced 后加权网络 Laplacian 矩阵
- $H_{es} = \operatorname{diag}\{H_{es,i}\}$，$D_{es} = \operatorname{diag}\{D_{es,i}\}$
- Kron reduction 已消去无储能节点（Remark 1）

### 2.3 Proposition 1（Sec.II-B，核心理论依据）

**论文原文直接给出的命题（非推论）：**

> 当各储能节点的惯量参数、阻尼参数和等效扰动均与 $k_i$ 成比例，即 $H_{es,i}=k_i H_{es0}$，$D_{es,i}=k_i D_{es0}$，$\Delta u_i = k_i \Delta u_0$，则所有节点的频率动态完全一致。

**证明路径：** 通过 scaled Laplacian 特征分解 (Eq.5-10) 得到 $\Delta\omega(s) = \frac{h_0(s)}{s}\Delta u_0 \mathbf{1}_N$，即所有节点频率响应相同。

**Remark 2（论文明确说明）：** Proposition 1 仅提供理想条件，实际中扰动位置不确定，参数不能始终与扰动成比例。故振荡根本原因是参数分布与各节点等效扰动的失配。

---

## 3. DDIC 方法结构

### 3.1 问题建模

- 表述为**部分可观察 Markov 博弈**（Partially Observable Markov Game）
- 元组：$\mathcal{N}, S, A, T, R, \gamma$
- $T$ 未知（model-free 的依据）

### 3.2 观测向量（Eq.11）

$$o_{i,t} = (\Delta P_{es,i,t},\ \Delta\omega_{i,t},\ \Delta\dot{\omega}_{i,t},\ \Delta\omega^c_{i,1,t},\ldots,\Delta\omega^c_{i,m,t},\ \Delta\dot{\omega}^c_{i,1,t},\ldots,\Delta\dot{\omega}^c_{i,m,t})$$

- 维度 = $3 + 2m$，其中 $m$ 是邻居数
- 当 $m=2$：维度 = 7（**这是 Kundur 和 NE39 场景下的具体值，不是通用公式**）
- 通信中断时，$\Delta\omega^c_{i,j,t} = 0$，$\Delta\dot{\omega}^c_{i,j,t} = 0$（论文 Sec.III-A 直接说明）

### 3.3 动作（Eq.12-13）

- $a_{i,t} = (\Delta H_{es,i,t},\ \Delta D_{es,i,t})$，连续动作空间
- 范围通过小信号稳定性分析预先确定（论文文字描述，未给出具体计算方法）
- 更新规则：$H_{es,i,t} = H_{es,i,0} + \Delta H_{es,i,t}$，$D_{es,i,t} = D_{es,i,0} + \Delta D_{es,i,t}$

**论文给出的具体参数范围（Sec.IV-B 训练性能描述中）：**
- $\Delta H_{es,i}$：$[-100, 300]$
- $\Delta D_{es,i}$：$[-200, 600]$

### 3.4 奖励函数（Eq.14-18）— 最重要的实现依据

**总奖励（Eq.14）：**
$$r_{i,t} = \varphi_f r^f_{i,t} + \varphi_h r^h_{i,t} + \varphi_d r^d_{i,t}$$

**r_f — 频率同步惩罚（Eq.15-16）：**
$$r^f_{i,t} = -(\Delta\omega_{i,t} - \Delta\bar{\omega}_{i,t})^2 - \sum_{j=1}^{m}(\Delta\omega^c_{i,j,t} - \Delta\bar{\omega}_{i,t})^2 \eta_{j,t}$$

$$\Delta\bar{\omega}_{i,t} = \frac{\Delta\omega_{i,t} + \sum_{j=1}^{m}\Delta\omega^c_{i,j,t}\eta_{j,t}}{1 + \sum_{j=1}^{m}\eta_{j,t}}$$

- $\eta_{j,t} \in \{0,1\}$：通信链路 $j$ 是否正常
- $\Delta\bar{\omega}_{i,t}$：**局部加权平均频率**（仅基于 agent $i$ 及其活跃邻居）
- 惩罚的是各节点频率偏离**局部平均**的程度，**不是**偏离额定频率的程度

> **核心语义：r_f 衡量同步度，不衡量频率恢复度。**  
> 当所有节点偏差相同时（哪怕都偏离额定），r_f = 0。

**r_h — 惯量调整惩罚（Eq.17）：**
$$r^h_{i,t} = -(\Delta H_{avg,i,t})^2$$

**r_d — 阻尼调整惩罚（Eq.18）：**
$$r^d_{i,t} = -(\Delta D_{avg,i,t})^2$$

- $\Delta H_{avg,i,t}$ 和 $\Delta D_{avg,i,t}$ 是平均惯量/阻尼调整量（全局平均）
- 论文说明：通过"分布式平均估计器"或网格运营商获得（Sec.III-A 第4项文字说明）
- **公式含义：对全局平均调整量的平方惩罚，即 $-(\text{mean}(\Delta H_i))^2$**

**权重系数（论文 Sec.IV-B 明确给出）：**
- $\varphi_f = 100$，$\varphi_h = 1$，$\varphi_d = 1$

**r_i = 0 的充要条件（论文文字 Sec.III-A）：**  
总奖励 $r_{i,t}$ 最大（= 0）当且仅当三项同时满足：$\Delta\omega_{i,t} = \Delta\bar{\omega}_{i,t}$（r_f=0），$\Delta H_{avg,i,t} = 0$（r_h=0），$\Delta D_{avg,i,t} = 0$（r_d=0）。  
单独 r_f = 0 的条件仅为 $\Delta\omega_{i,t} = \Delta\bar{\omega}_{i,t}$（即该 agent 与邻居频率一致）。

---

## 4. 算法结构（DDIC，Algorithm 1）

### 4.1 伪代码结构（原文 Algorithm 1，p.8）

```
for each agent i:
    初始化 actor π_{φ_i}
    初始化 critic Q_{θ_i}
    初始化空 replay buffer D_i

for each episode:
    for each time step:
        获取动作 a_{i,t}
        执行联合动作 a_t
        获取 r_{i,t} 和 o_{i,t+1}
        存入 (o_{i,t}, a_{i,t}, r_{i,t}, o_{i,t+1}) → D_i

    for each gradient step:
        for each agent i:
            更新 actor π_{φ_i}
            更新 critic Q_{θ_i}
    Clear buffer D_i   ← 【争议点，见第 7 节】
```

### 4.2 学习架构

- **分布式学习**（不是集中式，不是完全去中心化）
- 每个储能有独立的 actor 和 critic（**independent learner**）
- 训练时只需邻居频率信息，不需要全局信息
- 框架：SAC（soft actor-critic，最大熵 RL）

### 4.3 网络结构（Table I + Sec.IV-A 文字）

- Actor 和 Critic：均为 4 层全连接，每层 128 个隐藏单元
- 框架：Python + PyTorch

---

## 5. 超参数（Table I，Sec.IV-A）

| 参数 | 值 |
|------|----|
| Actor 学习率 | $3 \times 10^{-4}$ |
| Critic 学习率 | $3 \times 10^{-4}$ |
| $\alpha$ 学习率 | $3 \times 10^{-4}$ |
| 训练 episodes | 2000 |
| 折扣因子 $\gamma$ | 0.99 |
| Mini-batch size | 256 |
| Replay buffer size | 10000 |
| 每 episode 步数 $M$ | 50 |

---

## 6. 实验设置

### 6.1 主实验系统（Sec.IV-A）

- **系统：** 改进 Kundur 两区域系统
- **修改：** 发电机 4 替换为同容量风电场；母线 8 增加 100 MW 风电场
- **储能：** 4 台储能（分别接于不同区域）
- **控制步长：** 0.2 s
- **每 episode 仿真时间：** 10 s（即 $M=50$ 步）
- **仿真工具：** MATLAB-Simulink（由 Python 控制）
- **硬件：** Intel Core i7-11370 CPU @ 3.30 GHz（8 核）+ NVIDIA MX 450 GPU

### 6.2 数据集（Sec.IV-A）

- 训练集：**100 个随机生成**的扰动场景
- 测试集：**50 个随机生成**的扰动场景
- 扰动内容：扰动位置和大小随机（基于负荷和风电容量范围）；通信链路故障随机

> **待核实点 1：** 论文仅说"randomly generated"，未明确说明训练集与测试集在 episode 级别是固定的还是每次重新采样的。"100 train / 50 test fixed scenarios"是合理推断，但**非论文原文明确表述**。

### 6.3 对比方法

- 无控制（baseline）
- 自适应惯量控制（文献 [25]，线性方法）
- 集中式 DRL（SAC，弱网实验 Sec.IV-F 对比）

### 6.4 评价指标

- 频率累积奖励（Sec.IV-C 文字，使用**全局**频率奖励）：

$$-\sum_{t=1}^{M}\sum_{i=1}^{N}(\Delta f_{i,t} - \bar{f}_t)^2, \quad \bar{f}_t = \frac{1}{N}\sum_{i=1}^N \Delta f_{i,t}$$

> **注意（OCR 待核实 Q8）：** 上述公式来自原文 Sec.IV-C 段落，但该段落 OCR 严重损坏（原始转录含乱码），$\sum$ 之前是否有 $1/M$ 或 $1/N$ 归一化系数**无法从转录稿确认**。以上公式为从可辨字符推断的最可能形式。  
> 原文明确的内容：(1) 使用全局 $\bar{f}_t$，不是局部 r_f；(2) $M=50, N=4$；(3) 50 个测试 episode 的累积奖励数值 −8.04 / −12.93 / −15.2。

**注意：测试集评价时使用的是全局频率奖励，而不是训练时各 agent 的局部 r_f（Sec.IV-C 明确说明）。**

### 6.5 主要定量结果（Sec.IV-C）

| 方法 | 50测试 episode 累积奖励 |
|------|------------------------|
| 提议方法（DDIC） | −8.04 |
| 自适应惯量控制 | −12.93 |
| 无额外控制 | −15.2 |

单 episode 对比（load step 1 / load step 2）：
- 无控制：−1.61 / −0.80
- DDIC：−0.68 / −0.52

### 6.6 NE39 实验（Sec.IV-G）

- 修改版 New England 39 节点系统（详细全阶模型）
- 每个储能接收 **2 个邻居节点**的频率信息
- 测试场景：风电场 2 故障跳闸 + 时变随机通信延迟（高斯分布）
- 通信延迟：不同链路均值不同（具体数值论文未给出，只在图中展示）
- 定量结果：论文 Sec.IV-G 未给出与 NE 系统对应的累积奖励数值（只有图）

---

## 7. 已核实事实与易误读点

### 7.1 Algorithm 1 vs Table I 的内部矛盾（已核实）

**事实：**

- Algorithm 1 第 16 行：`Clear buffer D_i`（在 gradient step 之后，每 episode 清空）
- Table I：buffer_size = 10000，batch_size = 256，$M$ = 50

**矛盾：** 每 episode 最多产生 50 条经验。若每 episode 清空 buffer，则 batch_size=256 在理论上不可能满足（无法从 50 条中采样 256 条）。

**结论（已核实，非推论）：** 伪代码与超参数表存在内部矛盾。两者不可同时成立。

**项目决策（见 `docs/decisions/2026-04-10-paper-baseline-contract.md`）：**  
以 Table I 为准，不清空 buffer（标准 off-policy SAC 做法），并标注这是有依据的工程性偏差。

### 7.2 r_f 是相对同步惩罚，不是绝对频率恢复惩罚（已核实）

**原文直接陈述（Sec.III-A，Eq.15-16 文字说明）：**

> "When the frequency of all energy storage nodes is consistent during the transient process $\Delta\omega_{i,t}=\Delta\omega_{j,t}$, there will be no oscillation and the penalty for the frequency deviation of each agent should also be zero."

$r^f = 0$ 的条件是各节点频率相同，**而不是**频率偏差为零。

**论文没有要求频率回额定值**。频率恢复由 UFLS / governor 负责，不在本文讨论范围。

### 7.3 r_h 和 r_d 是 (ΔH̄)² 而非 mean(Δ²)（公式形式已核实；计算方式见 Q2）

- Eq.17：$r^h = -(\Delta H_{avg})^2$，即先取平均再平方（$-(\bar{\Delta H})^2$）
- Eq.18：$r^d = -(\Delta D_{avg})^2$，同上
- $(\text{mean}(x))^2 \neq \text{mean}(x^2)$，后者多了方差项 $\text{var}(x)$

> **与 Q2 的关系：** 公式结构 $-(\Delta H_{avg})^2$ 来自原文 Eq.17，已核实。但 $\Delta H_{avg}$ 的分布式计算协议（全局均值 vs. 邻居均值）未在原文给出，见 §8 Q2。

### 7.4 观测维度 7 是特例，不是通用公式（已核实）

- 通用公式：$\dim(o_i) = 3 + 2m$（$m$ 为邻居数）
- 论文实验中 $m=2$，所以 $\dim = 7$
- 若 $m \neq 2$，维度变化

### 7.5 每个 agent 拥有独立参数（已核实，Sec.III-B + Algorithm 1）

- 论文是 **independent learner**，每个储能的 actor/critic 参数独立训练
- **不是** 参数共享（parameter sharing / CTDE）
- 项目 Simulink 路径当前使用参数共享 SAC，是**与论文的已知偏差**（见 `paper-baseline-contract.md`）

### 7.6 训练时不使用通信延迟，仅考虑通信中断（已核实，Sec.III-A）

> "complex communication conditions such as communication delay, data loss, and bad data, are not considered during the off-line training process. Only communication link outage is considered."

- 通信延迟是**离线测试**场景（Sec.IV-E），不在训练中引入
- 通信中断（$\eta_j = 0$）在训练中随机引入

### 7.7 测试集评价与训练奖励使用不同公式（已核实，Sec.IV-C 文字）

- 训练：各 agent 使用局部 $r^f_{i,t}$（只看邻居）
- 测试评价：使用**全局**频率奖励（所有节点的全局平均）

---

## 8. 仍待核实的问题

| 编号 | 问题 | 当前状态 | 原文位置 |
|------|------|---------|---------|
| Q1 | 训练集/测试集是否在整个训练过程中固定不变，还是每次 reset 重新采样？ | 推断为固定，但原文仅说"randomly generated" | Sec.IV-A |
| Q2 | $\Delta H_{avg,i,t}$ 和 $\Delta D_{avg,i,t}$ 的具体计算方式（全局均值 vs 邻居均值） | 推断为全局均值（"distributed average estimators"），但协议未给出 | Sec.III-A Reward 段 |
| Q3 | NE39 实验的通信拓扑（每 agent 连哪两个邻居）| 只说"each agent can receive the frequency information of two neighboring nodes"，未给图 | Sec.IV-G |
| Q4 | 弱网实验的系统参数来源 | 引用了 [22]，未在论文中列出 | Sec.IV-F |
| Q5 | Kundur 系统中 4 台储能的具体连接位置（哪几个母线） | 原文"separately connected to different areas"，未给出母线编号，参见 Fig.3 | Sec.IV-A |
| Q6 | 每 episode 执行多少次梯度更新（gradient steps）| Table I 和 Algorithm 1 均未指定该数值 | Table I / Algorithm 1 |
| Q7 | $H_{es,i}$ 的量纲与传统同步机 H（秒）的关系 | **原文未给量纲**（2026-04-21 核查 `high_accuracy_transcription_cn.md`）。Eq.(1) 无 `2`、无 `ω_s` 系数，属控制派集总形式。项目工作假设 $H_{paper}=2·H_{code}$ 为**推断**，非论文事实。详见 §2.1 Q7 段 | Sec.II-A Eq.1；Sec.IV-B |
| Q8 | 测试集评价公式的归一化系数（是否含 1/M 或 1/N） | 原文该段 OCR 损坏，无法从转录稿核实 | Sec.IV-C |

---

## 9. 引用定位索引

| 内容 | 位置 |
|------|------|
| VSG 动力学方程 | Sec.II-A，Eq.1 |
| Kron reduction 说明 | Sec.II-A，Remark 1 |
| Proposition 1（理想参数比例条件）| Sec.II-B，命题+证明 Eq.5-10 |
| Remark 2（振荡根因） | Sec.II-B，Remark 2 |
| 观测向量定义 | Sec.III-A-1，Eq.11 |
| 动作定义及更新规则 | Sec.III-A-2，Eq.12-13 |
| 奖励函数总公式 | Sec.III-A-4，Eq.14 |
| r_f 及 ω̄ 定义 | Sec.III-A-4，Eq.15-16 |
| r_h / r_d 定义 | Sec.III-A-4，Eq.17-18 |
| SAC 目标函数 | Sec.III-B，Eq.19-23 |
| DDIC 伪代码 | Sec.III-C，Algorithm 1（p.8） |
| 超参数表 | Sec.IV-A，Table I |
| 仿真设置 | Sec.IV-A |
| 参数范围 $[-100,300]$ / $[-200,600]$ | Sec.IV-B（文字描述） |
| 权重系数 $\varphi_f=100, \varphi_h=1, \varphi_d=1$ | Sec.IV-B（文字描述） |
| 测试集奖励计算公式（全局）| Sec.IV-C（文字描述） |
| 通信失败测试 | Sec.IV-D |
| 通信延迟测试（0.2 s） | Sec.IV-E |
| 弱网实验（N=2,4,8 对比集中式 DRL）| Sec.IV-F |
| NE39 实验 | Sec.IV-G |

---

## 10. 项目实现偏差备案

本节记录当前项目与论文的已知偏差及其决策依据。

| 偏差项 | 论文原始 | 项目当前 | 决策文档 |
|--------|----------|----------|---------|
| Buffer 清空策略 | Algorithm 1：每 episode 清空 | 不清空（Table I 依据） | `2026-04-10-paper-baseline-contract.md` §Q3 |
| SAC 实例化（Simulink 路径）| 独立参数 per agent | 参数共享（CTDE） | `2026-04-10-paper-baseline-contract.md` §Q4 |
| ANDES 路径 r_f | 相对同步（同论文）| 相对同步 + PHI_ABS=50 绝对项（扩展） | `2026-04-10-paper-baseline-contract.md` §Q2 |
| 动作范围 | $\Delta H \in [-100,300]$，$\Delta D \in [-200,600]$ | $\Delta M \in [-6,18]$（M=2H），$\Delta D \in [-1.5,4.5]$ | 不同的基值（H₀/D₀ scale 不同） |
| Buffer 大小 | 10000 | 50 000 ~ 100 000 | 工程扩展，不影响方法正确性 |
| 奖励频率单位 | Δω（单位不明，见 Q7） | Hz（Δω_pu × F_NOM） | Q7 待核实；若论文用 p.u. 则 r_f 差 F_NOM²=2500× |
| 默认训练 episodes | 2000 | 500（MAX_EPISODES=2000） | 工程效率；复现论文需用 --episodes 2000 |
| Kundur T_EPISODE | 10s（M=50，Sec.IV-A） | 5s（M=25） | 工程决策：Kundur nadir 在 2-3s 内出现，5s 已够学习信号；NE39 保持 10s |

**2026-04-14 一致性修复（已应用）：**

| 修复项 | 修复前 | 修复后 | 依据 |
|--------|--------|--------|------|
| ANDES 动作映射 | 非零中心：a=0→ΔM=10 | 零中心：a=0→ΔM=0 | Eq.12-13（增量语义） |
| ANDES r_h/r_d | 用归一化动作 `(a_avg)²` | 用物理量 `(ΔH_avg)²` | Eq.17-18 |
| NE39 PHI_F | 200 | 100 | Table I φ_f=100 |

---

*最后更新：2026-04-14*  
*更新人：（新核实内容请注明具体依据）*
