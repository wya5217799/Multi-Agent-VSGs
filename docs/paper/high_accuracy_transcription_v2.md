# A Distributed Dynamic Inertia-Droop Control Strategy Based on Multi-Agent Deep Reinforcement Learning for Multiple Paralleled VSGs

**Qiufan Yang, Linfang Yan, Xia Chen, Yin Chen, and Jinyu Wen**

**Source type**: IEEE Transactions on Power Systems paper

**Manuscript information**  
Manuscript received 2 May 2022; revised 29 September 2022; accepted 4 November 2022. Date of publication 11 November 2022; date of current version 20 October 2023. This work was supported by the National Natural Science Foundation of China under Grants U22A6007 and 52222703. Paper no. TPWRS-00646-2022. (Corresponding author: Yin Chen.)

Qiufan Yang, Xia Chen, Yin Chen, and Jinyu Wen are with the State Key Laboratory of Advanced Electromagnetic Engineering and Technology, and School of Electrical and Electronic Engineering, Huazhong University of Science and Technology, Wuhan 430074, China (e-mail: yangqiufan@hust.edu.cn; cxhust@foxmail.com; 313862091cy@gmail.com; jinyu.wen@hust.edu.cn).

Linfang Yan is with the State Grid (Suzhou) City and Energy Research Institute, Suzhou, Jiangsu 215000, China (e-mail: linfyan@hust.edu.cn).

Color versions of one or more figures in this article are available at https://doi.org/10.1109/TPWRS.2022.3221439.

Digital Object Identifier 10.1109/TPWRS.2022.3221439

> Conversion note: this is a high-accuracy transcription-oriented Markdown conversion. No paraphrasing was intentionally introduced. Where source glyphs or structure remained ambiguous after review, they are marked with `[UNCERTAIN: ...]` or `[CHECK NEEDED: ...]`.

## Abstract

The virtual synchronous generator (VSG) control
method for energy storage is a promising way to improve the
frequency stability of the power system with large-scale renewable
energy. However, due to the mismatch parameters, power oscillations may occur when multiple VSGs are connected in parallel
to the grid. In this paper, the relationship between oscillation and
the inertia-droop parameters distribution of multiple paralleled
VSGs is derived by the simplified frequency response model. Furthermore, to coordinate the inertia-droop parameters of paralleled
VSGs for oscillation damping, this paper formulates the parameter
tuning problem as a Markov game with an unknown transition
function and proposes a distributed dynamic inertia-droop control strategy based on multi-agent deep reinforcement learning
(MADRL). Based on the local and adjacent VSG information,
each agent learns the optimal inertia-droop control parameters
independently by interacting with the environment. The soft-actorcritic (SAC) framework is introduced to train each agent. The
well-trained agent can modify the parameters of VSG dynamically to suppress the power oscillation under different operating
conditions. Finally, several time-domain results demonstrate the
effectiveness and robustness of the proposed approach.

**Index Terms** — Energy storage, inertia control, droop control,
multi-agent reinforcement learning, oscillation damping.

# I. INTRODUCTION
TO COMBAT climate change and reduce carbon emissions,
massive renewable energy units such as wind turbines
and photovoltaics, gradually replace the traditional synchronous
generators to penetrate the power system [1]. Despite climate
change can be mitigated, the large-scale integration of renewable
energy will bring great challenges to the stability of the power
system [2]. The frequency stability has been a specially raised
concern [3], [4]. The converter-interfaced renewable energy

generation cannot provide rotor inertia and governor damping as
conventional generators. Moreover, the fluctuating output power
of renewable energy sources causes a great disturbance in the
system. These factors cause the decline of frequency stability.
Several studies have been carried out to solve the problem of
decreasing frequency stability caused by a lack of rotational
inertia and damping. The most widely studied strategies are
using converters to mimic synchronous machine characteristics
[5], such as virtual inertia control [3], droop control [6], and
VSG [7]. VSG combines the advantages of both inertia control
and droop control and has attracted more attention than others
[8]. In [7], an extended virtual synchronous generator (EVSG)
is proposed to stabilize the system frequency by combining
the concept of the virtual rotor, the virtual primary, and the
virtual secondary controllers, whose parameters are designed
by the [UNCERTAIN: source glyph corrupted before "robust"; original PDF shows a special symbol] robust control method. A practical parameter design principle for VSG has been proposed in [9]. The model
predictive control-based VSG control strategy is proposed in
[10] to enhance voltage and frequency stability. However, these
strategies focus on enhancing robust and frequency dynamics of
VSG control for a single energy storage system in an isolated
system.
As the number of energy storage systems supporting the
frequency increases, there will be multiple paralleled VSGs in
practical applications. Although VSG provides the alternative
grid-friendly mode for the converter to support system frequency, the dynamics of the VSGs may interact with each other
in the paralleled VSGs system and causes power oscillation.
Some studies [11], [12] have shown that the distribution of
inertia and droop parameters in a power system has an important
influence on the frequency dynamics of each bus.
There are also some literatures on VSG optimization to
improve the frequency dynamics by adjusting virtual inertia
and damping coefficient in recent years. Based on the system
frequency response (SFR) model, a linear quadratic regulator
(LQR) [13] is adopted to adaptively adjust the emulated inertia
and damping constants according to the frequency disturbance
in the system. But the model cannot consider the difference in
the frequency response of different nodes. The particle swarm
optimization [14] is used to calculate VSG parameters based on
the detailed small signal model of multiple VSGs. The residue
index and hybrid PSO are adopted in [15] to achieve optimal damping characteristics. However, the optimization method
of these multiple inverter parameters is non-real-time and

<!-- PAGE BREAK -->

<!-- Page 2 -->
centralized based on the fixed operating condition. The optimization objective is the eigenvalues of the system. The eigenvalues do not change with the position and size of the system
disturbance. These methods are not suitable for time-varying
operations.
To solve the optimization operation for multiple inverterbased resources under different operating conditions, the realtime cooperative control strategy is an effective way. In [16],
the simultaneous complex power sharing and voltage regulation among multiple voltage source inverters are achieved in
distributed control manner. Nevertheless, each controller needs
to know the information of all other inverters. A unified fully
distributed cooperative secondary voltage control method has
been proposed in [17] to converge the voltages to a range.
For the problem in distributed control, such as convergence
rate, communication delays, and sensor/actuator faults, ref.
[18], [19], [20], [21] have proposed novel strategies to address
these problems. However, these voltage source inverter control
methods are based on droop-based control methods rather than
VSG. These cooperative control strategies for multiple inverters
focus on the accuracy of the power sharing and the secondary
control, rather than the system dynamics. The power oscillation
of multiple VSGs cannot be suppressed by these cooperative
control strategies.
Researchers have established some methods to suppress the
power oscillation in the paralleled VSGs system. The methods of
oscillation suppression can be summarized into two categories.
The first is to adjust the power during the secondary control
process. In [22], a novel secondary frequency control strategy
for distributed VSGs with the consensus algorithm based on
the event-triggered mechanism is proposed to suppress the oscillations and restore the frequency. However, this approach
adopts linear control and is not suitable for complex nonlinear power systems. The model-free distributed adaptive fuzzy
control approach is achieved for the multi-generator system to
address the system’s uncertain nonlinear dynamics and enhance
the frequency stability [23]. Nevertheless, not all energy storage
should be involved in the secondary frequency recovery process
due to limited energy storage capacity. The second method is
to adjust the swing equation of VSGs in the primary control.
An additional damping strategy is designed by the acceleration
control with a disturbance compensation in [24]. In [8], [25], the
inertia switching strategy is adopted to obtain a better frequency
dynamic. However, the effect of power oscillation suppression
is greatly influenced by the parameter of the inertia adjustment,
which is hard to determine. The virtual reactance adjustment is
applied in [26] to weaken the power oscillations. But the virtual
reactance required is also difficult to determine [22].
Based on an accurate dynamic system model, the above
model-based methods can design the optimal control parameters and achieve good frequency performance. However, many
uncertainties are difficult to obtain in the actual system. For
example, the system parameters and mathematical model of the
system cannot be accurately obtained. Moreover, the operating
conditions are diverse. These factors greatly affect the effectiveness of the above methods. Recently, the model-free approaches
do not depend on the accurate model and have attracted more

attention in smart grid applications [27]. A top-quality control
strategy can be learned by interacting with the environment
based on deep reinforcement learning (DRL). In recent years, the
DRL algorithms can be divided into two categories. The first is
the value-based method, such as Deep Q-Network (DQN) [28].
And many extended DQN algorithms have been proposed to
improve the performance of DQN, such as Double DQN [29].
However, the action space of the value-based DRL is discrete.
The second category is the policy gradient method, which is
suitable for continuous and high-dimensional action space.
There is a growing body of literature that adopts the DRL
based on policy gradient to enhance frequency stability. Ref.
[30] proposes a multi-band power system stabilizer based on the
proximal policy optimization (PPO) algorithm to dampen multimode oscillations. Asynchronous advantage actor-critic (A3C)
is introduced to provide optimal real-time parameters for the
proposed PR-PSS [31]. The soft-actor-critic (SAC) algorithm
is adopted [32] for the real-time control parameters of energy
storage to dampen the power oscillation. As for VSG, the deep
deterministic policy gradient (DDPG) algorithm is introduced
to obtain the optimal virtual inertia and damping factor [33].
However, the control objective of the above DRL-based
method is a single device. In [34], the DDPG algorithm is
adopted for multiple devices to dampen low-frequency oscillations. The training method is a centralized way by a single agent.
As a large number of energy storage power stations supporting
power grid frequency are connected to the system, the calculation dimension and training time using the centralized training
method of a single agent will increase exponentially [35]. Due
to its scalability, the multi-agent DRL (MADRL) approach is
an effective way to solve problems involving multiple agents.
The MADRL has been applied in load frequency control [36]
through centralized learning and decentralized implementation.
Based on multi-agent quantum deep reinforcement learning, the
adaptive optimal cooperative control strategy is proposed in [37]
for distributed frequency control. A MADRL approach is also
applied in the decentralized inverter-based secondary voltage
control [38], volt-var control in active distribution networks
[39], and nonconvex economic dispatch [40]. Compared with
DRL algorithms adopted by each agent in the aforementioned
MADRL during the training process, SAC is a heterogeneous
strategy action-evaluation algorithm based on the maximum
entropy RL framework. SAC adds the entropy value of the policy
to the original objective function to improve the exploration
efficiency, making the control performance superior. However,
to the best of the author’s knowledge, this is the first study to
apply MADRL based on SAC for cooperative control of multiple
energy storages with inertia and droop control to suppress the
power oscillation.
Inspired by these studies, a MADRL-based distributed control
strategy is proposed to coordinate the real-time optimal inertia
and droop parameters of multiple energy storages with VSG.
Especially, the control objective is to suppress the power oscillation, and avoid excessive inertia and droop parameter adjustments of the entire system caused by the collective parameter
adjustments. In other words, under the condition that the total inertia and droop coefficient of the system is not changed as much

<!-- PAGE BREAK -->

<!-- Page 3 -->
as possible, the power oscillation is suppressed by changing the
parameter distribution in real time. The main contributions of
this paper are summarized as follows.
1) By establishing a simplified system model with multiple
inertial and droop support energy storages, the mechanism
of frequency oscillation is revealed, and the ideal condition
of the same frequency dynamics of all energy storage
nodes is given.
2) The coordination adjustment of inertia and droop parameters of multiple energy storages is formulated as a Markov
Game without knowing the transition function. Compared
with the non-real-time parameter optimization method of
VSG in [13], [14], a novel MADRL-based distributed
control strategy is proposed to coordinate the real-time
inertia and droop parameters adjustments for power oscillation suppression. Compared with the model-based
adaptive control [8], [25], the proposed control strategy
has strong robustness and can achieve better frequency
oscillation suppression under communication delay and
communication link interruption.
3) Compared with the centralized DRL [34], the proposed
method only requires local observation and neighboring
information during the training and control process. The
fully distributed control framework makes the proposed
method scalable. Besides, because the dimensions of the
neural network of each agent will not increase with the
increase of the energy storage scale, the proposed control
has better training stability. Compared with the DDPG
adopted in existing MADRL literature [39], the independent learner adopts the SAC algorithm to learn the
real-time optimal parameters for energy storage, which
can realize the continuous adjustment of parameters and
have better online control performance.
The rest of this paper is organized as follows. The mechanism
analysis of multiple energy storage systems to support frequency
is presented in Section II. Section III proposes the distributed
dynamic inertia-droop control strategy. Section IV carries out
several simulation studies to validate the effectiveness of the
proposed distributed control strategy. Finally, Section V concludes the paper.


According to research results in [41], the grid-forming device improves
the frequency dynamics better than the grid-following device.
Moreover, since there are many synchronous generators in the
real power system, the frequency change rate of the rotor of
the synchronous generators should not be too large. The inertial
part in VSG directly affects the frequency change rate. The distribution of inertia has a great influence on the system dynamics
[11], [12]. Thus, this paper mainly considers energy storage with
grid-forming control based on VSG. The dynamic equation of
the energy storage to enhance frequency can be written as

$$
H_{es i}\Delta \dot{\omega}_i + D_{es i}\Delta \omega_i = \Delta u_i - \Delta P_{es i}
\tag{1}
$$

where $\Delta \omega_i$ is the virtual angle frequency deviation of the voltage
bus $i$; $\Delta \dot{\omega}_i$ is the derivative of $\Delta \omega_i$; $H_{es i}$ and $D_{es i}$ denote the
virtual inertia constant and virtual droop constant of energy
storage $i$, respectively; $\Delta u_i$ is the outside disturbance such as
local load; $\Delta P_{es i}$ is the output active power of energy storage $i$ to
support grid frequency. Although the inner loop control can also
affect the stability of the system, it should be specially noted
that this paper mainly studies the relatively slow dynamics of
the electromechanical transient. Therefore, the dynamics of the
inner loop can be neglected referring to [42].

For the $i$-th bus in the grid, considering the purely inductive
lines, the output power $P_i$ can be expressed as

$$
P_i = \sum_{j=1}^{N} V_i V_j b_{ij}\sin(\theta_i - \theta_j)
\tag{2}
$$

where $V_i$ is the voltage magnitude of bus $i$; $b_{ij}$ is the line
susceptance between bus $i$ and bus $j$; $\theta_i$ is the voltage angle
deviation from the synchronously rotating reference of bus $i$.

Assuming that the voltage magnitudes are constant and linearizing the model at the equilibrium, the electrical power of
energy storage can be given as

$$
\Delta P_{es i} = \sum_{j=1}^{N} l_{ij}(\Delta \theta_i - \Delta \theta_j)
\tag{3}
$$

where

$$
l_{ij} = \frac{\partial}{\partial \theta_j}\sum_{k=1}^{n} V_i V_k b_{ik}\sin(\theta_i - \theta_k).
$$

$L=[l_{ij}] \in \mathbb{R}^{N\times N}$ is the undirected weighted network Laplacian matrix. The system
dynamics can be rewritten in matrix form as

$$
\begin{cases}
\Delta \dot{\theta} = \Delta \omega \\
\Delta \dot{\omega} = H_{es}^{-1}\Delta u - H_{es}^{-1}L\Delta \theta - H_{es}^{-1}D_{es}\Delta \omega
\end{cases}
\tag{4}
$$

where $\Delta \omega$, $\Delta \theta$, and $\Delta u$ are the column vector of frequency
deviations, voltage angle deviations, and outside disturbances;
$H_{es} = \operatorname{diag}\{H_{es i}\}$ and $D_{es} = \operatorname{diag}\{D_{es i}\}$ are the diagonal
matrix of virtual inertia and virtual droop constant.

Remark 1: The model (4) adopts Kron reduction and eliminates the bus with no energy storage, which can be referred to
[44]. Therefore, $\Delta u$ can not only represent the power disturbance at the energy storage bus, but also can denote the power
disturbance at the bus without any energy storage. When the disturbance occurs at the non-energy storage bus, $\Delta u$ is the power
disturbance vector converted to each energy storage bus according to the admittance matrix. The sum of the elements in $\Delta u$ is
equal to the power disturbance at the non-energy storage bus.

# II. SYSTEM MODEL AND ANALYSIS

<!-- PAGE BREAK -->

<!-- Page 4 -->
## B. Mechanism Analysis for Multiple Energy Storage Systems

This paper focuses on the influence of disturbance on the
frequency variation of each energy storage bus. From (4), it can
be easily found that the frequency of each energy storage bus
will be affected by inertia distribution $H_{es}$, droop distribution
$D_{es}$, disturbance distribution $\Delta u$, and network $L$. The dynamics
of frequency at the energy storage bus will be influenced by
other buses through the network $L$. When the frequencies of
the distributed energy storages are quite different, large power
and frequency oscillations will occur. However, appropriate $H_{es}$
and $D_{es}$ can make all energy storage node frequencies identical
during the transient process. The proposition and proof are as
follows.

**Proposition 1:** When the inertia parameters, droop parameters
and equivalent disturbances of the energy storage nodes are all
proportional to $k_i$, i.e., $H_{es i}=k_iH_{es0}$, $D_{es i}=k_iD_{es0}$, and $\Delta u_i
= k_i\Delta u_0$, the frequency dynamics of all nodes are completely
consistent.

It should be noted that $H_{es0}$, $D_{es0}$, and $\Delta u_0$ have no actual
physical meanings and can be regarded as the representative
values of all nodes. The values of each energy storage node are
proportional to the representative values and the proportion coefficients are all $k_i$. Equivalently, the ratios $H_{es i}/D_{es i} = H_{es0}/D_{es0}$,
$D_{es i}/\Delta u_i = D_{es0}/\Delta u_0$ are uniform over node $i$.

*Proof:* It can be seen from [43] that for the units with proportional inertia parameters and droop parameters, the dynamics
of the system (4) can be diagonalized in the form of a transfer
function as follows

$$
\Delta \omega(s) = \mathbf{K}^{-\frac{1}{2}}\mathbf{V}\mathbf{H}(s)\mathbf{V}^{T}\mathbf{K}^{-\frac{1}{2}}\Delta u(s)
\tag{5}
$$

where $\mathbf{K}=\operatorname{diag}\{k_i\}$ is the diagonal matrix of the proportional
parameters. The column vectors of $\mathbf{V}$ are the unit orthogonal
eigenvectors of the scaled Laplacian matrix $\mathbf{K}^{-\frac{1}{2}}L\mathbf{K}^{-\frac{1}{2}}$. $\mathbf{H}(s)$
is the diagonal matrix with the elements $h_k(s)$.

$$
h_k(s)=\frac{g_0(s)}{1+\frac{\lambda_k}{s}g_0(s)},\quad k=0,1,\ldots,N-1.
\tag{6}
$$

where $g_0(s)=\dfrac{1}{H_{es0}s + D_{es0}}$. $\lambda_k$ is the eigenvalue of the scaled
Laplacian matrix and $\lambda_0 = 0$. The eigenvector corresponding to
$\lambda_0$ is
$$
v_0=\left(\sum_{i=1}^{N}k_i\right)^{-\frac{1}{2}}\mathbf{K}^{\frac{1}{2}}\mathbf{1}_N.
$$
The unitary matrix $\mathbf{V}$ can be
rewritten as $\mathbf{V}=[\,v_0\ \ \mathbf{V}_1\,]$.

For the disturbance $\Delta u(s)=\mathbf{K}\mathbf{1}_N\frac{1}{s}\Delta u_0$, the frequency response can be expressed as

$$
\begin{aligned}
\Delta \omega(s)
&= \mathbf{K}^{-\frac{1}{2}}\mathbf{V}\mathbf{H}(s)\mathbf{V}^{T}\mathbf{K}^{-\frac{1}{2}}\mathbf{K}\mathbf{1}_N\frac{1}{s}\Delta u_0 \\
&= \mathbf{K}^{-\frac{1}{2}}
\begin{bmatrix} v_0 & \mathbf{V}_1 \end{bmatrix}
\begin{bmatrix} h_0(s) & \\ & \tilde{\mathbf{H}}(s) \end{bmatrix}
\begin{bmatrix} v_0 & \mathbf{V}_1 \end{bmatrix}^{T}
\mathbf{K}^{-\frac{1}{2}}\mathbf{K}\mathbf{1}_N\frac{1}{s}\Delta u_0 \\
&= \mathbf{K}^{-\frac{1}{2}}\left(v_0v_0^{T}h_0(s)+\mathbf{V}_1\tilde{\mathbf{H}}(s)\mathbf{V}_1^{T}\right)\mathbf{K}^{-\frac{1}{2}}\mathbf{K}\mathbf{1}_N\frac{1}{s}\Delta u_0
\end{aligned}
\tag{7}
$$

where $\tilde{\mathbf{H}}(s)=\operatorname{diag}\{h_1(s),\ldots,h_{N-1}(s)\}$.

Substituting the expression of $v_0$ into (7) derives the following
decomposition

$$
\begin{aligned}
\Delta \omega(s)
&= \mathbf{K}^{-\frac{1}{2}}
\left(
\left(\sum_{i=1}^{N}k_i\right)^{-1}
\mathbf{K}^{\frac{1}{2}}\mathbf{1}_N\mathbf{1}_N^{T}\mathbf{K}^{\frac{1}{2}}h_0(s)
+ \mathbf{V}_1\tilde{\mathbf{H}}(s)\mathbf{V}_1^{T}
\right)
\mathbf{K}^{-\frac{1}{2}}\mathbf{K}\mathbf{1}_N\frac{1}{s}\Delta u_0 \\
&= \frac{\mathbf{1}_N\mathbf{1}_N^{T}}{\sum_{i=1}^{N}k_i}\mathbf{K}\mathbf{1}_N\frac{h_0(s)}{s}\Delta u_0
+ \mathbf{K}^{-\frac{1}{2}}\mathbf{V}_1\tilde{\mathbf{H}}(s)\mathbf{V}_1^{T}\mathbf{K}^{\frac{1}{2}}\mathbf{1}_N\frac{1}{s}\Delta u_0 \\
&= \frac{h_0(s)}{s}\Delta u_0\mathbf{1}_N
+ \mathbf{K}^{-\frac{1}{2}}\mathbf{V}_1\tilde{\mathbf{H}}(s)\mathbf{V}_1^{T}\mathbf{K}^{\frac{1}{2}}\mathbf{1}_N\frac{1}{s}\Delta u_0
\end{aligned}
\tag{8}
$$

Since the vectors of $\mathbf{V}$ are orthogonal $\mathbf{V}_1^{T}v_0 = \mathbf{0}_N$, the
following equation can be derived as

$$
\mathbf{V}_1^{T}\mathbf{K}^{\frac{1}{2}}\mathbf{1}_N = \mathbf{0}_N
\tag{9}
$$

Substituting (9) into (8) yields

$$
\Delta \omega(s)=\frac{h_0(s)}{s}\Delta u_0\mathbf{1}_N
\tag{10}
$$

From (10), it reveals that the frequency dynamics of all energy
storage buses are the same.

From the derivation above, it can be concluded that for different disturbances, appropriate distribution of $H_{es}$ and $D_{es}$
can suppress the oscillation among grid-forming energy storage
systems. Hence, adjusting the distribution of inertia and droop
parameters of all supported energy storage systems in the system
is one of the most effective ways to support the system frequency.

Remark 2: Proposition 1 just provides an ideal inertia-droop
parameter condition in which the frequency dynamics of all
nodes can remain consistent. Since the location of the disturbance is uncertain, the parameters of VSG cannot always be
proportional to the equivalent disturbance of each node in practice. However, it can be concluded from Proposition 1 that the
root cause of the difference in frequency dynamics of different
nodes is the mismatch between the inertia-droop parameters
and the equivalent disturbances of each node. It illustrates the
feasibility of the method of adjusting the inertia and droop
parameters distribution to dampen the oscillations and improve
the frequency dynamics.

# III. PROPOSED DISTRIBUTED CONTROL APPROACH
Although the optimal distribution of virtual inertia and droop
coefficient for each energy storage to support the system frequency can be obtained in a specific disturbance scenario according to the analysis in Section II, the disturbance location and size
in a real power system are uncertain. Fixed virtual inertia and
droop coefficients definitely cannot meet the requirements of
the oscillation damping under different disturbance scenarios.

<!-- PAGE BREAK -->

<!-- Page 5 -->

**Figure 1.** The proposed control architecture.

Moreover, the centralized real-time parameter tuning method
has the drawback of a single point of failure. Therefore, in this
section, a distributed dynamic inertial-droop parameter tuning
method is proposed.

## A. Problem Formulation

To improve the dynamic characteristics of the system frequency and suppress oscillation under any possible disturbance,
the cooperative optimization of the distribution of the inertia and
droop coefficients of energy storage systems can be regarded as
a sequential decision-making problem. The proposed control
structure is shown in Fig. 1. At time $t$, based on the local energy
storage agent observation $o_{i,t}$, including the energy storage output, the bus frequency, and the acquired adjacent bus frequency,
each energy storage controller chooses to increase or decrease
the inertia and droop parameters $a_{i,t}$. Then, the frequency and the
inertia-droop parameters are changed to a new one under the
joint action $(a_{1,t}, a_{2,t}, a_{3,t}\ldots)$. To ensure the plug-and-play
of the energy storage and reduce the burden of the centralized
controller, each energy storage can only obtain the information
of local and adjacent nodes. The above co-tuning problem of
inertia and droop parameters can be expressed as a partially
observable Markov game, which is the multiagent extension of
the Markov decision process (MDP). It can be defined by the
tuple $\mathcal{N}, S, A, T, R, \gamma$. $\mathcal{N}$ is the number of agents. $S$ denotes
the set of states observed by all agents. $A=A_1\times \cdots \times A_N$ denotes
the set of actions of all agents. $A_i$ is the action set of agent $i$.
$S \times A$ represents the set of $(s, a)$ for any state $s \in S$ under any
joint action $a \in A$. $T:S \times A \to \Delta(S)$ represents the transition probability from any state $s \in S$ to any state $s' \in S$ for any
joint action $a \in A$. $S \times A \times S$ represents the set of $(s, a, s')$ for
a transition from $(s, a)$ to $s' \in S$. $R_i:S \times A \times S \to \mathbb{R}$. $R$ is the
set of reward functions that determines the possible immediate
reward received by each agent for a transition from $(s, a)$ to $s'$.
$\gamma \in [0,1]$ is the discount factor to trade off the current and future
rewards.

1) *State:* Each energy storage agent will make the inertia
and droop parameters tuning decisions to suppress the
frequency oscillation and avoid excessive reserve capacity adjustment based on the local observation $o_{i,t}$. The
observation of agent $i$ at time step $t$ is defined as

$$
o_{i,t} = (\Delta P_{es i,t}, \Delta \omega_{i,t}, \Delta \dot{\omega}_{i,t}, \Delta \omega^c_{i,1,t}, \ldots, \Delta \omega^c_{i,m,t},
\Delta \dot{\omega}^c_{i,1,t}, \ldots, \Delta \dot{\omega}^c_{i,m,t})
\tag{11}
$$

where $\Delta P_{es i,t}$ is the support power of local energy storage
$i$ at time step $t$; $\Delta \omega_{i,t}$ and $\Delta \dot{\omega}_{i,t}$ are the frequency deviation
of the local bus $i$ and its change rate at time step $t$, respectively; $\Delta \omega^c_{i,1,t},\ldots,\Delta \omega^c_{i,m,t}$ and $\Delta \dot{\omega}^c_{i,1,t},\ldots,\Delta \dot{\omega}^c_{i,m,t}$ are
the acquired adjacent bus frequency deviations and their
change rates through communication link at time step
$t$, respectively; $m$ is the number of the adjacent nodes.
By combining the observations of all agents, the state
of the system at time step $t$ can be represented as $s_t =
(o_{i,t},\ldots,o_{N,t})$.

It is worth noting that the observable of the controller
cannot be empty. When the communication link from node
$j$ to $i$ is broken, the variables $\Delta \omega^c_{i,j,t}$ and $\Delta \dot{\omega}^c_{i,j,t}$ are set to
zero.

2) *Action:* The local action $a_{i,t} = (\Delta H_{es i,t}, \Delta D_{es i,t})$ represents the inertia and droop parameter corrections for
energy storage $i$ at time step $t$. The action space of $a_{i,t}$
is assumed to be continuous and is restricted as follows

$$
\begin{cases}
\Delta H_{es i,\min} \le \Delta H_{es i,t} \le \Delta H_{es i,\max} \\
\Delta D_{es i,\min} \le \Delta D_{es i,t} \le \Delta D_{es i,\max}
\end{cases}
\tag{12}
$$

where $\Delta H_{es i,\min}$ and $\Delta H_{es i,\max}$ are the minimum and
maximum value of the inertia correction for energy storage
$i$, respectively; $\Delta D_{es i,\min}$ and $\Delta D_{es i,\max}$ are the minimum and maximum value of the droop correction for
energy storage $i$, respectively. The action range can be obtained by the small signal analysis in advance to maintain
the small signal stability of the system. The joint action
at time step $t$ can be expressed as $a_t = (a_{i,t},\ldots,a_{N,t})$.
The corrected inertia and droop parameter of each energy
storage can be expressed as

$$
\begin{cases}
H_{es i,t} = H_{es i,0} + \Delta H_{es i,t} \\
D_{es i,t} = D_{es i,0} + \Delta D_{es i,t}
\end{cases}
\tag{13}
$$

where $H_{es i,0}$ and $D_{es i,0}$ are the initial inertia and droop
parameters of the energy storage $i$, respectively.

3) *State transition:* The system state transition process from
$s_t$ to $s_{t+1}$ with the joint action $a_t$ can be denoted as
$s_{t+1}\sim \mathcal{P}(s_t, a_t, \varepsilon_t)$. The state transition is not only determined by the current state and the joint action, but
also subject to various random factors $\varepsilon_t$, such as the
communication delay, the communication link, and other
generating units which cannot be observed. It is intractable
to describe the transition model accurately. To address
this issue, the paper adopts the model-free algorithm in
Section III-B.

4) *Reward:* Each energy storage agent $i$ will receive a local
reward $r_{i,t}$ when the system state changes from $s_t$ to $s_{t+1}$.

<!-- PAGE BREAK -->

<!-- Page 6 -->
Since the control objective is to suppress the frequency
oscillation and avoid the excessive adjustment of the inertia and droop reserve capacity for the whole system, the
reward function $r_{i,t}$ for each energy storage agent $i$ at time
step $t$ can be divided into three parts: the penalty for the
frequency deviation from synchrony $r^f_{i,t}$, the penalty for
the global inertia parameter adjustment $r^h_{i,t}$ and the penalty
for the global droop parameter adjustment $r^d_{i,t}$. The reward
function is defined as

$$
r_{i,t} = \varphi_f r^f_{i,t} + \varphi_h r^h_{i,t} + \varphi_d r^d_{i,t}
\tag{14}
$$

where $\varphi_f$, $\varphi_h$, and $\varphi_d$ are the weight coefficients.

When the frequency of all energy storage nodes is consistent
during the transient process $\Delta \omega_{i,t}=\Delta \omega_{j,t}$, there will be no
oscillation and the penalty for the frequency deviation of each
agent should also be zero. The frequency deviation cost from
synchrony for the energy storage $i$ can be designed as

$$
r^f_{i,t} = -(\Delta \omega_{i,t} - \Delta \bar{\omega}_{i,t})^2 - \sum_{j=1}^{m}(\Delta \omega^c_{i,j,t} - \Delta \bar{\omega}_{i,t})^2 \eta_{j,t}
\tag{15}
$$

where $\eta_{j,t}$ is used to judge whether the communication link $j$ is
broken ($\eta_{j,t}=0$) or not ($\eta_{j,t}=1$); $\Delta \bar{\omega}_{i,t}$ is the observed average
frequency for energy storage $i$ at time step $t$, whose expression
is as follows

$$
\Delta \bar{\omega}_{i,t} =
\left(
\Delta \omega_{i,t} + \sum_{j=1}^{m}\Delta \omega^c_{i,j,t}\eta_{j,t}
\right)
\Big/
\left(
1 + \sum_{j=1}^{m}\eta_{j,t}
\right)
\tag{16}
$$

When the communication link from node $j$ to node $i$ at time
step $t$ is broken, the obtained frequency information $\Delta \omega^c_{i,j,t}$
will be zero, which is incorrect. Hence, for the energy storage $i$ at time step $t$, the number of neighboring nodes whose
information can be correctly obtained is $\sum_{j=1}^{m}\eta_{j,t}$. The sum
of the correct frequency obtained from the neighboring nodes
is $\sum_{j=1}^{m}\Delta \omega^c_{i,j,t}\eta_{j,t}$. Equation (16) represents the estimation of
the global average frequency for energy storage $i$ based on the
obtained frequency of neighboring nodes and its frequency.

It is worth emphasizing that the agent can only obtain neighboring frequency information, rather than the global frequency
information. The designed frequency reward is only related to
the observed frequency. If the observed $\Delta \omega^c_{i,j,t}$ is inconsistent
with the actual value $\Delta \omega_{j,t}$, the frequency reward $r^f_{i,t}$ will be
wrong during the training process. To ensure that the reward
function can correctly evaluate the action taken by the agent,
complex communication conditions such as communication delay, data loss, and bad data, are not considered during the off-line
training process. Only communication link outage is considered
during the off-line training process, which is the most serious
communication failure. During the online control process, the
reward function is no longer necessary for the controller. When
the most serious communication failures have been considered
during the training, the other communication conditions can also
be handled during the online control.

Since the global inertia adjustment and the global droop
adjustment are affected by all energy storage actions, the local
information is not enough for the penalties for these adjustments.
This paper assumes that there are distributed average inertia
and droop adjustment estimators, similar to [45] in each energy
storage agent. The energy storage agent can also obtain average
parameter adjustments calculated by the grid operator. The
penalty for the inertia adjustment $r^h_{i,t}$ and droop adjustment $r^d_{i,t}$
can be calculated as

$$
r^h_{i,t} = -(\Delta H_{avg i,t})^2
\tag{17}
$$

$$
r^d_{i,t} = -(\Delta D_{avg i,t})^2
\tag{18}
$$

where $\Delta H_{avg i,t}$ and $\Delta D_{avg i,t}$ are the average inertia and droop
adjustments for energy storage $i$ at time step $t$, respectively.

## B. Multiagent Deep Reinforce Learning

Faced with large-scale and complex sequential decision-making problems, a single-agent system cannot realize the cooperative or competitive relationship among multiple decision-makers. Therefore, based on DRL model, it is extended to a
multiagent system that cooperates, communicates, and competes
among multiple agents.

According to the multiagent learning structure, MARL algorithms can be divided into decentralized, distributed, and centralized. In decentralized learning, each agent regards other agents
as part of the environment and directly applies the single-agent
algorithm to interact with the environment [46]. Due to ignoring
the nature of multiagent environments, independent learning
methods cannot guarantee the stationarity of the environment
and may fail to converge [47]. In centralized learning, it is
assumed that there is a centralized controller that can collect
the joint state, action, and reward information of all agents. It
effectively alleviates the non-stationarity of multi-agent environments. However, with the increase in the number of agents,
the state space and computational complexity of centralized
learning will increase significantly. Hence, this paper adopts
a distributed learning architecture. In distributed learning, each
agent can exchange information with neighboring nodes through
a communication network. The distributed structure can not
only maintain the scalability of decentralized learning but also
alleviate the instability that may occur in independent learning.

For each reinforcement learning agent, the current state-of-the-art continuous control model-free reinforcement learning
algorithm, SAC [48], is adopted in this paper. SAC is a heterogeneous strategy action-evaluation algorithm based on the
maximum entropy RL framework, which aims to solve the problems of high sample complexity and low stability of model-free
DRL methods. In other words, its goal is to complete the task
as randomly as possible. To improve exploration efficiency,
the maximum entropy RL framework adopted by SAC adds
the entropy value of the policy to the original reward item. The
objective function is as follows

$$
\max J(\pi) = \sum_t \mathbb{E}_{(s_t,a_t)\sim \rho_\pi}\gamma^t \left[r(s_t,a_t) + \alpha \cdot H(\pi(\cdot|s_t))\right]
\tag{19}
$$

where $\alpha$ is the entropy parameter, which determines the relative
importance of entropy relative to reward. $H(\pi(\cdot|s_t))$ is the
entropy of the policy $\pi$. The policy is updated iteratively by
alternately executing the policy actor and critic in SAC. The
Q-value function in policy critic is calculated as follows

$$
Q_\pi(s_t,a_t) = r(s_t,a_t) + \sum_{k=t+1}^{\infty}\mathbb{E}_{(s_t,a_t)\sim \rho_\pi}\left[\gamma^k r(s_k,a_k)\right]
\tag{20}
$$

To adapt to continuous state space and action space, actor
and critic functions are represented by the parameterized neural
networks $\pi_\phi(a_t|s_t)$ and $Q_\theta(s_t,a_t)$, respectively. $\phi$ and $\theta$ are the
neural network parameters. The parameter of the critic network
is trained by minimizing the squared residual error as follows

$$
J_Q(\theta)=\mathbb{E}_{(s_t,a_t)\sim D}\left[\frac{1}{2}\left(Q_\theta(s_t,a_t)-\left(r(s_t,a_t)+\gamma \mathbb{E}_{s_{t+1}\sim \rho}\left[V_{\bar{\theta}}(s_{t+1})\right]\right)\right)^2\right]
\tag{21}
$$

where $D$ is the data buffer pool of the experience playback mechanism; $V_{\bar{\theta}}(s_{t+1})$ is the target network to estimate the state-value
function.

The parameter of the actor network is trained by minimizing
the expected Kullback-Leibler (KL) divergence as

$$
J_\pi(\phi) = \mathbb{E}_{s_t\sim D}\left[\mathbb{E}_{a_t\sim \pi_\phi}\left[\alpha \log \pi_\phi(a_t|s_t) - Q_\theta(s_t,a_t)\right]\right]
\tag{22}
$$

The learning objective for the parameter $\alpha$ is updated as
follows

$$
J(\alpha)=\mathbb{E}_{a_t\sim \pi_\phi}\left[-\alpha \log \pi_\phi(a_t|s_t)-\alpha \bar{H}\right]
\tag{23}
$$

where $\bar{H}$ is the minimum policy entropy value.

## C. Proposed DDIC Algorithm
Based on the above theory, the MADRAL-based distributed
dynamic inertia-droop control (DDIC) strategy is proposed,
which adopts the distributed learning architecture with SAC
framework. The framework of the proposed DDIC is depicted
in Fig. 2. Each energy storage agent obtains frequency information of adjacent nodes through the distributed communication

network. The parameter tuning policy of each agent is trained
with SAC algorithm based on the local and adjacent information.
According to the analysis in Section II, the frequency dynamics
of each node are different after disturbance. Thus, the current
state can be estimated by considering the frequencies of local
and neighboring nodes together as observation values oi,t . For
simplicity, only one actor network and one critic network are
shown in Fig. 2.
Each energy storage agent learns the dynamic inertia-droop
control strategy independently with the SAC algorithm. Based
on oi,t , the actor network i takes the parameter tuning action
ai,t . The joint action at = (a1,t , …, aN,t ) and the current state
determine the next state of the environment and the reward
function of each agent. The observation oi,t , the action ai,t ,
the reward ri,t , and the next observation oi,t+1 are stored in the
relay buffer Di to train each energy storage agent. By interacting
with the environment, the critic network, the actor network, and
the entropy parameter a in the SAC algorithm of each agent
are updated in (21), (22), and (23). And each agent can better
learn the dynamics of the distributed dynamic inertia and the
droop control. Each energy storage agent only needs to acquire
the neighboring frequency dynamics and local observations
during the training process. The pseudocode of the proposed
MADRL-based algorithm is shown in Algorithm 1. It indicates
that the structure of the proposed dynamic inertia-droop control
strategy is distributed. The method only requires a communication network that exchanges frequency information between
neighboring agents. As the number of energy storage increases,
the computational complexity for each energy storage agent does
not increase. Hence, the proposed control can meet the needs of
large-scale energy storage to support the power grid.
It is easy to find that the best reward ri,t for each agent is
zero only when Δωi,t = Δω̄i,t , ΔHavgi,t = 0 and ΔDavgi,t =
0 in (14). When each agent can obtain the information of at
least one neighboring node, Δω̄i,t will consider the frequency
of the neighboring node. If there are differences between node
frequencies at time t, the reward ri,t of each agent is not the
best. The agent will modify the parameters of the policy network
to improve the reward until Δωi,t = Δω̄i,t , ΔHavgi,t = 0 and

<!-- PAGE BREAK -->

<!-- Page 8 -->
**Algorithm 1. Training Process of the Proposed Algorithm**

1. Input: `φ, θ`
2. for each agent `i` do
3. Initialize the parameters of actor network `π_{φ_i}` randomly.
4. Initialize the parameters of critic network `Q_{θ_i}` randomly.
5. Initialize the empty replay buffer `D_i`.
6. for each episode do:
7. for each time step environment do:
8. Obtain the parameter tuning action `a_{i,t}` based on actor network for each agent `i`.
9. Execute action `a_t = (a_{1,t}, ..., a_{N,t})`.
10. Obtain `r_{i,t}` and `o_{i,t+1}` for each agent `i`.
11. Store transition `(o_{i,t}, a_{i,t}, r_{i,t}, o_{i,t+1})` into buffer `D_i` for each agent `i`.
12. for each gradient step do:
13. for each agent `i` do:
14. Update the weights of actor network `π_{φ_i}`.
15. Update the weights of critic network `Q_{θ_i}`.
16. Clear the buffer `D_i`.
17. Output: `φ, θ`


1: Input: φ, θ
2: for each agent i do
3: Initialize the parameters of actor network π φi
randomly.
4: Initialize the parameters of critic network Qθ i
randomly.
5: Initialize the empty replay buffer Di .
6: for each episode do:
7: for each time step environment do:
8:
Obtain the parameter tuning action ai,t based on
actor network for each agent i.
9:
Execute action at = (a1,t , …, aN,t ).
10:
Obtain ri,t and oi,t+1 for each agent i.
11:
Store transition (oi,t ,ai,t ,ri,t ,oi,t+1 ) into buffer Di
for each agent i.
12: for each gradient step do:
13:
for each agent i do:
14:
Update the weights of actor network π φi .
15:
Update the weights of critic network Qθ i .
16:
Clear the buffer Di .
17: Output: φ, θ
ΔDavgi,t = 0 at every time of each episode during the training
process. When the frequency of each agent can be obtained by at
least another agent, the designed reward will guide the actions
of the policy network of each agent to achieve the frequency
dynamics of all nodes consistent during the training process.
Remark 3: In this paper, each energy storage device participating in the frequency regulation has an agent. However, with
the scale of energy storage increasing, not all energy storage
systems can receive information from neighboring nodes due to
the limitations of practical conditions. It is necessary to choose
the appropriate agents and communication links to achieve better
power oscillation suppression. For the energy storage devices
located close to each other and far away from the disturbance,
the frequency dynamics of these energy storage nodes are very
similar. Only one agent is necessary for these energy storage
devices. It is also very important to determine the communication link between agents for receiving neighboring information.
Different communication graphs will have a great influence on
the decision made by the agents. It is better for agents to observe
as many nodes with large frequency differences as possible.
Therefore, the state of the system can be determined more
correctly by each agent with partial observation.
# IV. CASE STUDY
In this section, the effectiveness of the proposed distributed
dynamic inertia-droop control strategy is validated through the
time-domain simulation analysis. The details about the simulation setup are provided in Section IV-A. Then, the training
process is given in Section IV-B. The system dynamic results
under multiple operation conditions are shown in Section IV-C
to E. To demonstrate the practicability of the proposed method,
the performances of the proposed method in weak grids and New
England System are shown in Section IV-F to G.

**Figure 3.** Fig. 3.

The single-line diagram of the modified Kundur two-area system.

**Table I. Hyper-Parameters of Learning Algorithm**

| Parameter | Value |
|---|---:|
| Learning rate for actor | `3×10^-4` |
| Learning rate for critic | `3×10^-4` |
| Learning rate for `α` | `3×10^-4` |
| Training episodes | `2000` |
| Discount factor `γ` | `0.99` |
| Mini-batch size | `256` |
| Replay buffer size | `10000` |
| Step in each episode `M` | `50` |



## A. Simulation Setup
The simulation is carried out on the modified Kundur two-area
system, including two wind farms and four energy storage systems. The line diagram of the modified system is shown in Fig. 3.
The parameters of the generators can be obtained from the classic
Kundur two-area system [49]. Generator 4 in Kundur two-area
system is replaced by a wind farm with the same capacity.
Besides, a 100MW wind farm is connected to bus 8. Four energy
storage systems with loads are also separately connected to
different areas in the system. The performance of the system
is evaluated under the time-domain simulation. According to
the analysis result in Section II, the power oscillation is caused
by the mismatch between the position of the disturbance and
the control parameters of energy storage. To train and test the
agents of the proposed control method, the location and size of
the disturbance are generated randomly according to the load
and wind farm capability. Communication link failure is also
generated randomly. 100 randomly generated data set is regarded
as the training set. 50 randomly generated data set is regarded
as the test set.
The hyper-parameters of the independent learning algorithm
and proposed approach for each energy storage system are the
same, which are listed in Table I. Both the critic network and
the actor network contain 4 fully connected layers. Each layer
consists of 128 hidden units. The proposed controller is implanted by Python with Pytorch. The time-domain simulation is
executed by Matlab-Simulink and can be controlled by Python.
The control step is set to 0.2 s and the total simulation time for
each episode is set to 10 s. The hardware is a computer with an
8-core Intel CoreTM i7-11370 CPU @ 3.30 GHz and 1 NVIDIA
MX 450 GPU.

<!-- PAGE BREAK -->

<!-- Page 9 -->
**Figure 5.** Fig. 5.

Cumulative reward on the test set.

**Figure 6.** Fig. 6.

System dynamics without the proposed control in load step 1.

**Figure 4.** Fig. 4. Training performance of the multiagent learning. (a) Total episode
reward; (b) ES1 episode reward; (c) ES2 episode reward; (d) ES3 episode reward;
(e) ES4 episode reward.

## B. Training Performance
In this case, the training process of the proposed distributed
dynamic inertia-droop control for four energy storages is shown
in Fig. 4. The darker curve and corresponding lighter shade
represent the average and actual episode reward for each disturbance, respectively. The parameter range of inertia and droop
for each energy storage is from −100 to 300 and from −200 to
600, respectively. The weight coefficients in the reward function
for each energy storage are set as rf = 100, rh = 1, and rd = 1.
As shown in Fig. 4(a), in the initial training stage, the penalty
to frequency synchronization, average regulated inertia, and
droop coefficient are severely large due to the disorder of system
inertia and droop parameter adjustment. As the training of the
interaction between distributed controllers and the grid goes on,
the distributed controllers gradually store better performance in
the replay buffer and learn to improve the distributed dynamic
inertia-droop control strategy. After 500 episodes, all the performance indexes gradually stabilize near the optimal value.
The training reward curves of four energy storage distributed
controllers are depicted in Fig. 4(b)∼(e). It can be observed that
four distributed controllers can learn the dynamic inertia-droop
control strategy simultaneously. Therefore, the training performance illustrates that the proposed approach can learn a stable
distributed dynamic inertia-droop control strategy.
## C. Distributed Control Dynamics Under Load Step
In this case, the well-trained agents in case B are adopted to
demonstrate the proposed distributed control dynamics under
different load steps. Fifty power step disturbances with different
positions and sizes are randomly generated as a test set to
simulate the disturbances that the power grid might face. To
demonstrate the superiority of the proposed strategy, the adaptive

inertia control proposed in [25] is compared with the proposed
strategy. The cumulative reward of frequency is shown in Fig. 5.
It should be noted that to illustrate the global performance of the
system, the frequency reward used in the test set is global, rather
than the sum of four locally available frequency rewards. The
frequency reward of each episode for all three control methods
N

¯ 2 ¯ N fi,t /N
is calculated as − M
t=1
i=1 (fi,t − ft ) . ft =
i=1
is the average frequency of all energy storage nodes at time step
t. M is the step number of each episode. The time step of each
episode for the methods being compared is the same as that for
the proposed control method. For the simulation case in this
paper, M = 50, N = 4.
It can be observed from Fig. 5 that the reward curve with the
proposed control is always much higher than that with adaptive
inertia control and without additional control. The frequency
cumulative rewards for 50 test episodes are −8.04, −12.93,
and −15.2, respectively. For the complex power system with
synchronous generators and other devices, too many uncertainties are not observed. The adaptive inertia control [25] only
linearly modifying the inertia has a limited effect on frequency
improvement. From the frequency reward metrics, the proposed
distributed dynamic inertia-droop control has generality and can
greatly improve the frequency dynamic performance.
To evaluate the transient performance of the proposed control
strategy in detail, the time-domain simulation results of two
different test episodes have been shown in Figs. 6∼9. Load step
1 and load step 2 represent the sudden load reduction of 248MW
at bus 14 and the sudden load increase of 188MW at bus 15,
respectively. As shown in Figs. 6 and 8, due to the identical

<!-- PAGE BREAK -->

<!-- Page 10 -->
**Figure 9.** Fig. 9.
**Figure 7.** Fig. 7.

System dynamics with the proposed control in load step 2.

System dynamics with the proposed control in load step 1.

respectively. When the frequency change direction of the bus
with a larger frequency deviation is in the direction of the average frequency, the controller will reduce the inertia and droop
parameters of energy storage and make the bus frequency close
to the average frequency quickly. Moreover, the average values
of the modified inertia and droop parameters are at a low level.
It means that the rotation reserve and primary frequency reserve
capacity of the whole system are basically unchanged. As a
result, the oscillations in both the frequencies and powers can
be obviously decreased with the proposed distributed dynamic
inertia-droop control strategy.
**Figure 8.** Fig. 8.

System dynamics without the proposed control in load step 2.

inertia and droop parameters of all ESs, the frequency of the bus
which is the nearest to the disturbance bus changes the fastest.
The frequency of the bus where ES1 and ES2 are located changes
relatively slowly as they are relatively far from the disturbance
bus. Frequency oscillations are caused by frequency changes
that are out of synchronization.
In comparison, the inertia and droop parameters of energy
storage are dynamically adjusted according to the frequency of
adjacent nodes and their frequency status information to keep
the frequency as consistent as possible in Figs. 7 and 9. Before
applying the proposed control method, the frequency rewards for
load step 1 and load step 2 are −1.61 and −0.80, respectively.
The frequency rewards have been increased to −0.68 and −0.52
with the proposed dynamic inertia and droop control method,

## D. Performance Under Communication Failure
In this case, the time simulation is conducted to verify the
resiliency of the proposed distributed dynamic inertia-droop
controller under the communication link failure. Based on the
test set mentioned in Section IV-C, a random communication
failure is set. The comparison of the cumulative reward of
frequency is shown in Fig. 10. The comparison results demonstrate that communication failure has little influence on the
cumulative reward for frequency. Moreover, the time-domain
simulation waveform of load step 1 under communication failure
is shown in Fig. 11. The communication between ES1 and ES2
is interrupted. Comparing Fig. 11 with Fig. 6, the frequency and
power oscillations of the system can be suppressed effectively
even if one communication channel is interrupted. Therefore,
the proposed distributed control strategy has the resilience to
communication failure.

<!-- PAGE BREAK -->

<!-- Page 11 -->
**Figure 10.** Fig. 10.

Cumulative reward comparison under communication failure.

**Figure 13.** Fig. 13. System dynamics with the proposed control in load step 1 under 0.2 s
communication delay.

It should be noted that communication delay is not considered
during training. The above results demonstrate that the proposed
control strategy is not strongly dependent on the real-time state
information of neighbor ES and has strong robustness. The
proposed controller can adapt to the complex communication
environment.
## F. Performance in Weak Grids
**Figure 11.** Fig. 11. System dynamics with the proposed control in load step 1 under
communication failure.

**Figure 12.** Fig. 12.

Cumulative reward comparison under communication delay.

## E. Performance Under Communication Delay
Communication delay is a non-negligible factor in distributed
control, which may affect the stability of the system. This case
investigates the impact of communication delay on the proposed
distributed dynamic inertia-droop control performance. Based
on the test set mentioned in Section IV-C, 0.2 s communication
delay has been set between the neighbor ESs. The cumulative
reward comparison under communication delay is depicted in
**Figure 12.** Fig. 12. The frequency cumulative reward for 50 test episodes
with the proposed control under communication delay is −9.53.
It can be seen that the oscillation suppression effect is decreased
when the communication delay occurs. However, the frequency
stability has still been enhanced with the proposed approach.
Fig. 13 illustrates the system dynamics under 0.2 s communication delay. The oscillation is also effectively suppressed.

In this case, the systems supported only by energy storage
systems are conducted to study the effectiveness of the proposed
method in weak grids. The parameters can refer to [22]. Meanwhile, to study the adaptability of the proposed method to the
scale of energy storage systems, the number of energy storage
systems is set to 2, 4, and 8, respectively. To demonstrate the
optimality of the proposed method, the centralized DRL method
with SAC is compared with the proposed method. The centralized DRL can receive the frequency and power information of
all energy storage nodes accurately. Based on all energy storage
information, the centralized DRL adjusts the inertia and droop
parameters of all energy storage systems.
The training performance of the proposed DRL method and
centralized method is shown in Fig. 14 when the number of
energy storage systems is 2, 4, and 8, respectively. The training
result has illustrated that as the number of energy storage systems
increases, it is difficult for the centralized DRL control to obtain
stable results in 2000 training episodes due to the increase in the
dimensions of the policy network and critic network. However,
since the dimension of the network of the proposed strategy will
not increase with the number of energy storage, the proposed
control can still converge to stability.
Fig. 15 shows the cumulative rewards of the centralized DRL
control and the proposed control under different number of energy storage systems. It should be mentioned that the cumulative
reward of the centralized DRL control is not shown in Fig. 15(c)
due to its unstable training performance in Fig. 14(c). When
the amount of energy storage is 2, the cumulative value of the
centralized DRL method is −34.69, which is slightly higher
than the cumulative reward of the proposed control (−36.46).
The control performance of the proposed method can be close
to that of the centralized DRL method in a small-scale system.
It illustrates the optimality of the proposed control method.

<!-- PAGE BREAK -->

<!-- Page 12 -->
**Figure 16.** Fig. 16.

The single-line diagram of the modified New England system.

**Figure 17.** Fig. 17.
system.

Training performance of the proposed method in New England

**Figure 14.** Fig. 14. Comparison of the training performance between the proposed
method and centralized DRL under different amounts of energy storage systems.

When the number of energy storage systems increases, the
control performance of the centralized control deteriorates
rapidly due to the increase in input and output dimensions of
the network. On the contrary, the proposed control strategy has
a higher cumulative reward and better control performance due
to its scalability. The simulation result shows that the proposed
method can adapt to the increase in the number of agents. The
above results also show that the proposed control can adapt to
the weak grid.
## G. Performance in New England System

**Figure 15.** Fig. 15. Cumulative reward comparison under different amounts of energy
storage systems.

To verify the control performance of the proposed control in
the practical system, the detailed full order model of the modified
New England system has been established as shown in Fig. 16.
Each energy storage agent can receive the frequency information
of two neighboring nodes by communication links. The training
performance in Fig. 17 demonstrates that the proposed method
can still converge to stability in the practical system. Figs. 18, 19,
and 20 show the frequency dynamics without additional control,
with the adaptive inertia control proposed in [25] and with the
proposed dynamic inertia and droop control method under the
wind farm 2 fault trip, respectively. To demonstrate the effectiveness of the proposed method under time-varying communication
delay, the communication delay is generated randomly by
Gaussian distribution and the mean values of the communication

<!-- PAGE BREAK -->

<!-- Page 13 -->
**Figure 18.** Fig. 18.

Frequency dynamics without additional control method.

**Figure 20.** Fig. 20. System dynamics with the proposed control method at the communication period of 0.2 s under time-varying communication delay.

**Figure 19.** Fig. 19. Frequency dynamics with the adaptive inertia control proposed in
[25]. (a) The communication period is 0.01 s; (b) the communication period is
0.2 s.

**Figure 21.** Fig. 21.

System dynamics under the short circuit fault.

# V. CONCLUSION
delay of different communication links are different. The communication delay between energy storage system 1 and energy
storage system 8 is depicted in Fig. 20(a). Comparing Figs. 18
with 20, it can be seen that the proposed method can effectively
suppress the frequency oscillation caused by large active power
disturbance under time-varying communication delay. It can be
seen from Fig. 19 that although adaptive inertia can suppress
oscillation at a lower communication period of 0.01 s, it cannot
suppress oscillation at a higher communication period of 0.2 s.
Because the action of the adaptive control method is remarkably
correlated linearly with the frequency and the rate of change
of frequency. This method requires high communication speed.
Compared with the adaptive inertia control shown in Fig. 19, the
proposed method shown in Fig. 20 can suppress the oscillation
more quickly at a higher communication period of 0.2 s and the
synchrony of each node frequency is better.
To show the performance of the proposed method under the
short circuit faults, a three-phase short circuit is applied at bus
3 at t = 0.2 s. The line between bus 3 and bus 4 is tripped after
100 ms. The frequency dynamics of energy storage 1 is shown
in Fig. 21. The simulation result illustrates that the proposed
method can suppress the peak of the oscillation and remain stable
after a short circuit fault.

In this paper, we have analyzed the relationship between the
transient oscillation and the disturbances, as well as the relationship between oscillation and the inertia-droop distributions
of multiple VSGs. According to the simplified frequency model,
when the inertia parameter, the droop parameter, and the equivalent disturbance of each VSG are proportional, the frequencies
of all VSGs are synchronized. In other words, the oscillation can
be damped by modifying the inertia and droop parameter distribution in terms of the different disturbances. To adapt to different
operating conditions and disturbances, the distributed dynamic
inertia-droop control strategy based on MADRL is proposed.
The parameter dynamic tuning problem in a multi-agent environment is formulated as a Markov game. The optimal inertiadroop control strategy is learned by the SAC-based model-free
method. The modified Kundur two-area system, including two
wind farms and four energy storage systems, is built to test the
effectiveness of the proposed control method. The time-domain
simulation results show that the proposed control strategy can
suppress the power oscillation by modifying the inertia and
droop parameter distribution. The comparison with the centralized DRL under different amounts of energy storage systems has
shown that the proposed method is scalable for its distributed
training and control structure. The comparison with the conventional adaptive inertia control demonstrates that the proposed

<!-- PAGE BREAK -->

<!-- Page 14 -->
control strategy has a better oscillation suppression effect under
complex operating conditions. Moreover, the proposed control
is robust to communication interruption and time delay.
Although extensive simulations show the advantages of the
proposed distributed dynamic inertia-droop control strategy
based on MADRL, the proposed MADRL method still faces
several challenges due to its partial observability and controllability. One challenge is non-stationarity. Multiple agents learn
at the same time. The action taken by one agent affects the
reward of other agents and the evolution of the state, which
invalidates the stationarity assumption of single-agent DRL. The
other challenge is theoretical analysis. Multiple agents usually
cannot know the complete information about the state of the environment. In these situations, the multiple agents should make
the nearly optimal decision during each time step according to
the partially observed information of the environment. It may
also influence optimality. These challenges will be considered
in our future work.
# REFERENCES
[1] X. Chen et al., “Pathway toward carbon-neutral electrical systems in China
by mid-century with negative CO2 abatement costs informed by highresolution modeling,” Joule, vol. 5, no. 10, pp. 2715–2741, Oct. 2021.
[2] Y. Chen, S. M. Mazhari, C. Y. Chung, S. O. Faried, and B. C. Pal, “Rotor
angle stability prediction of power systems with high wind power penetration using a stability index vector,” IEEE Trans. Power Syst., vol. 35,
no. 6, pp. 4632–4643, Nov. 2020.
[3] N. Sockeel, J. Gafford, B. Papari, and M. Mazzola, “Virtual inertia
emulator-based model predictive control for grid frequency regulation
considering high penetration of inverter-based energy storage system,”
IEEE Trans. Sustain. Energy, vol. 11, no. 4, pp. 2932–2939, Oct. 2020.
[4] E. Alves, G. Bergna-Diaz, D. Brandao, and E. Tedeschi, “Sufficient
conditions for robust frequency stability of AC power systems,” IEEE
Trans. Power Syst., vol. 36, no. 3, pp. 2684–2692, May 2021.
[5] Q. C. Zhong and G. Weiss, “Synchronverters: Inverters that mimic
synchronous generators,” IEEE Trans. Ind. Electron., vol. 58, no. 4,
pp. 1259–1267, Apr. 2011.
[6] X. Meng, J. Liu, and Z. Liu, “A generalized droop control for gridsupporting inverter based on comparison between traditional droop control
and virtual synchronous generator control,” IEEE Trans. Power Electron.,
vol. 34, no. 6, pp. 5416–5438, Jun. 2019.
[7] A. Fathi, Q. Shafiee, and H. Bevrani, “Robust frequency control of microgrids using an extended virtual synchronous generator,” IEEE Trans.
Power Syst., vol. 33, no. 6, pp. 6289–6297, Nov. 2018.
[8] M. Chen, D. Zhou, C. Wu, and F. Blaabjerg, “Characteristics of parallel
inverters applying virtual synchronous generator control,” IEEE Trans.
Smart Grid, vol. 12, no. 6, pp. 4690–4701, Nov. 2021.
[9] K. Jiang, H. Su, H. Lin, K. He, H. Zeng, and Y. Che, “A practical secondary
frequency control strategy for virtual synchronous generator,” IEEE Trans.
Smart Grid, vol. 11, no. 3, pp. 2734–2736, May 2020.
[10] B. Long, Y. Liao, K. T. Chong, J. Rodríguez, and J. M. Guerrero, “MPCcontrolled virtual synchronous generator to enhance frequency and voltage
dynamic performance in islanded microgrids,” IEEE Trans. Smart Grid,
vol. 12, no. 2, pp. 953–964, Mar. 2021.
[11] B. K. Poolla, S. Bolognani, and F. D¨orfler, “Optimal placement of virtual
inertia in power grids,” IEEE Trans. Autom. Control, vol. 62, no. 12,
pp. 6209–6220, Dec. 2017.
[12] D. Groß, S. Bolognani, B. K. Poolla, and F. D¨orfler, “Increasing the
resilience of low-inertia power systems by virtual inertia and damping,”
in Proc. Int. Inst. Res. Educ. Power Syst. Dyn., 2017, Art. no. 64.
[13] U. Markovic, Z. Chu, P. Aristidou, and G. Hug, “LQR-based adaptive
virtual synchronous machine for power systems with high inverter penetration,” IEEE Trans. Sustain. Energy, vol. 10, no. 3, pp. 1501–1512,
Jul. 2019.
[14] B. Pournazarian, R. Sangrody, M. Lehtonen, G. B. Gharehpetian, and
E. Pouresmaeil, “Simultaneous optimization of virtual synchronous generators parameters and virtual impedances in islanded microgrids,”
IEEE Trans. Smart Grid, vol. 13, no. 6, pp. 4202–4217, Nov. 2022,
doi: 10.1109/TSG.2022.3186165.

[15] P. Sun, J. Yao, Y. Zhao, X. Fang, and J. Cao, “Stability assessment
and damping optimization control of multiple grid-connected virtual
synchronous generators,” IEEE Trans. Energy Convers., vol. 36, no. 4,
pp. 3555–3567, Dec. 2021.
[16] J. Duarte, M. Velasco, P. Marti, A. Camacho, J. Miret, and C. Alfaro,
“Decoupled simultaneous complex power sharing and voltage regulation
in Islanded AC microgrids,” IEEE Trans. Ind. Electron., early access, Jun.
07, 2022, doi: 10.1109/TIE.2022.3179553.
[17] C. Zhang, X. Dou, L. Wang, Y. Dong, and Y. Ji, “Distributed cooperative
voltage control for grid-following and grid-forming distributed generators
in islanded microgrids,” IEEE Trans. Power Syst., early access, Mar.
10, 2022, doi: 10.1109/TPWRS.2022.3158306.
[18] R. Lu, J. Wang, and Z. Wang, “Distributed observer-based finite-time
control of AC microgrid under attack,” IEEE Trans. Smart Grid, vol. 12,
no. 1, pp. 157–168, Jan. 2021.
[19] Y. Du, H. Tu, H. Yu, and S. Lukic, “Accurate consensus-based distributed
averaging with variable time delay in support of distributed secondary control algorithms,” IEEE Trans. Smart Grid, vol. 11, no. 4, pp. 2918–2928,
Jul. 2020.
[20] N. M. Dehkordi and S. Z. Moussavi, “Distributed resilient adaptive control
of islanded microgrids under sensor/actuator faults,” IEEE Trans. Smart
Grid, vol. 11, no. 3, pp. 2699–2708, May 2020.
[21] M. A. Shahab, B. Mozafari, S. Soleymani, N. M. Dehkordi, H. M.
Shourkaei, and J. M. Guerrero, “Distributed consensus-based fault tolerant
control of Islanded microgrids,” IEEE Trans. Smart Grid, vol. 11, no. 1,
pp. 37–47, Jan. 2020.
[22] M. Shi, X. Chen, J. Zhou, Y. Chen, J. Wen, and H. He, “Frequency
restoration and oscillation damping of distributed VSGs in microgrid with
low bandwidth communication,” IEEE Trans. Smart Grid, vol. 12, no. 2,
pp. 1011–1021, Mar. 2021.
[23] Y. Xu, W. Zhang, M.-Y. Chow, H. Sun, H. B. Gooi, and J. Peng, “A
distributed model-free controller for enhancing power system transient frequency stability,” IEEE Trans. Ind. Inform., vol. 15, no. 3, pp. 1361–1371,
Mar. 2019.
[24] M. Chen, D. Zhou, and F. Blaabjerg, “Active power oscillation damping
based on acceleration control in paralleled virtual synchronous generators
system,” IEEE Trans. Power Electron., vol. 36, no. 8, pp. 9501–9510,
Aug. 2021.
[25] S. Fu et al., “Power oscillation suppression in multi-VSG grid with
adaptive virtual inertia,” Int. J. Elect. Power Energy Syst., vol. 135, 2022,
Art. no. 107472.
[26] J. Liu, Y. Miura, H. Bevrani, and T. Ise, “Enhanced virtual synchronous
generator control for parallel inverters in microgrids,” IEEE Trans. Smart
Grid, vol. 8, no. 5, pp. 2268–2277, Sep. 2017.
[27] Y. Zhang, X. Shi, H. Zhang, Y. Cao, and V. Terzija, “Review on deep
learning applications in frequency analysis and control of modern power
system,” Int. J. Elect. Power Energy Syst., vol. 136, 2022, Art. no. 107744.
[28] V. Mnih et alet al., “Human-level control through deep reinforcement
learning,” Nature, vol. 518, no. 7540, pp. 529–533, 2015.
[29] H. Van Hasselt, A. Guez, and D. Silver, “Deep reinforcement learning with double Q-learning,” in Proc. AAAI Conf. Artif. Intell., 2016,
pp. 2094–2100.
[30] G. Zhang, W. Hu, J. Zhao, D. Cao, Z. Chen, and F. Blaabjerg, “A novel
deep reinforcement learning enabled multi-band PSS for multi-mode oscillation control,” IEEE Trans. Power Syst., vol. 36, no. 4, pp. 3794–3797,
Jul. 2021.
[31] G. Zhang et al., “Deep reinforcement learning-based approach for proportional resonance power system stabilizer to prevent ultra-low-frequency
oscillations,” IEEE Trans. Smart Grid, vol. 11, no. 6, pp. 5260–5272,
Nov. 2020.
[32] T. Li et al., “Mechanism analysis and real-time control of energy storage
based grid power oscillation damping: A soft actor-critic approach,” IEEE
Trans. Sustain. Energy, vol. 12, no. 4, pp. 1915–1926, Oct. 2021.
[33] Y. Li et al., “Data-driven optimal control strategy for virtual synchronous
generator via deep reinforcement learning approach,” J. Modern Power
Syst. Clean Energy, vol. 9, no. 4, pp. 919–929, Jul. 2021.
[34] P. Gupta, A. Pal, and V. Vittal, “Coordinated wide-area damping control
using deep neural networks and reinforcement learning,” IEEE Trans.
Power Syst., vol. 37, no. 1, pp. 365–376, Jan. 2022.
[35] H. Liu and W. Wu, “Online multi-agent reinforcement learning for decentralized inverter-based volt-var control,” IEEE Trans. Smart Grid, vol. 12,
no. 4, pp. 2980–2990, Jul. 2021.
[36] Z. Yan and Y. Xu, “A multi-agent deep reinforcement learning method for
cooperative load frequency control of a multi-area power system,” IEEE
Trans. Power Syst., vol. 35, no. 6, pp. 4599–4608, Nov. 2020.

<!-- PAGE BREAK -->

<!-- Page 15 -->
[37] Y. Xu, R. Yan, Y. Wang, and D. Jiahong, “A multi-agent quantum deep reinforcement learning method for distributed frequency control of islanded
microgrids,” IEEE Trans. Control Netw. Syst., early access, Jan. 05, 2022,
doi: 10.1109/TCNS.2022.3140702.
[38] D. Chen et al., “PowerNet: Multi-agent deep reinforcement learning for
scalable powergrid control,” IEEE Trans. Power Syst., vol. 37, no. 2,
pp. 1007–1017, Mar. 2022.
[39] X. Sun and J. Qiu, “Two-stage volt/var control in active distribution
networks with multi-agent deep reinforcement learning method,” IEEE
Trans. Smart Grid, vol. 12, no. 4, pp. 2903–2912, Jul. 2021.
[40] L. Ding, Z. Lin, X. Shi, and G. Yan, “Target-value-competition-based
multi-agent deep reinforcement learning algorithm for distributed nonconvex economic dispatch,” IEEE Trans. Power Syst., early access, Mar.
16, 2022, doi: 10.1109/TPWRS.2022.3159825.
[41] B. K. Poolla, D. Groß, and F. Dörfler, “Placement and implementation
of grid-forming and grid-following virtual inertia and fast frequency response,” IEEE Trans. Power Syst., vol. 34, no. 4, pp. 3035–3046, Jul. 2019.
[42] Z. Wang, H. Yi, F. Zhuo, J. Wu, and C. Zhu, “Analysis of parameter
influence on transient active power circulation among different generation
units in microgrid,” IEEE Trans. Ind. Electron., vol. 68, no. 1, pp. 248–257,
Jan. 2021.
[43] F. Paganini and E. Mallada, “Global analysis of synchronization performance for power systems: Bridging the theory-practice gap,” IEEE Trans.
Autom. Control, vol. 65, no. 7, pp. 3007–3022, Jul. 2020.
[44] T. Ishizaki, A. Chakrabortty, and J. Imura, “Graph-theoretic analysis of
power systems,” Proc. IEEE, vol. 106, no. 5, pp. 931–952, May 2018.
[45] R. A. Freeman, P. Yang, and K. M. Lynch, “Stability and convergence
properties of dynamic average consensus estimators,” in Proc. 45th IEEE
Conf. Decis. Control, 2006, pp. 338–343.
[46] M. Tan, “Multi-agent reinforcement learning: Independent vs. cooperative
agents,” in Proc. 10th Int. Conf. Mach. Learn., 1993, pp. 330–337.
[47] Y. Shoham, R. Powers, and T. Grenager, “If multi-agent learning is the
answer, what is the question?,” Artif. Intell., vol. 171, no. 7, pp. 365–377,
Mar. 2008.
[48] T. Haarnoja et al., “Soft actor-critic: Off-policy maximum entropy deep
reinforcement learning with a stochastic actor,” in Proc. Int. Conf. Mach.
Learn., 2018, pp. 1861–1870.
[49] P. Kundur, Power System Stability and Control. New York, NY, USA:
McGraw-Hill 1994.

## Biography

Qiufan Yang received the B.S. degree in electrical
engineering in 2019 from the Huazhong University
of Science and Technology, Wuhan, China, where
he is currently working toward the Ph.D. degree in
electrical engineering. His research interests include
microgrids, distributed control, and energy storage
control technology.

## Biography

Linfang Yan received the B.S. and Ph.D. degrees in
electrical engineering from the Huazhong University
of Science and Technology, Wuhan, China, in 2017
and 2022, respectively. He is currently a Researcher
with the State Grid (Suzhou) City & Energy Research
Institute, Suzhou, China. His research interests include deep reinforcement learning, electric vehicle
charging, smart home, P2P energy trading, distributed
control, and hybrid energy storage.

## Biography

Xia Chen (Senior Member, IEEE) received the B.S.
degree in power system and its automaton from the
Wuhan University of Technology, Wuhan, China, in
2006, and the M.S. and Ph.D. degrees in electrical
engineering from the Huazhong University of Science
and Technology (HUST), Wuhan, China, in 2008 and
2012, respectively. From 2012 to 2015, she was a
Postdoctoral Research Fellow with The University
of Hong Kong, Hong Kong. In 2015, she joined the
HUST and is currently an Associate Professor with
the School of Electrical and Electronic Engineering,
HUST. Her research interests include distributed control technology in microgrid, renewable energy integration technologies, and new smart grid device.

## Biography

Yin Chen received the B.S. degree in electrical engineering from the Huazhong University of Science and
Technology, Wuhan, China, in 2009, the M.S. degree
in electrical engineering from Zhejiang University,
Hangzhou, China, in 2014, and the Ph.D. degree in
electrical engineering from the University of Strathclyde, Glasgow, U.K., in 2020. He is currently a Postdoctoral Researcher. His research interests include
the modeling of power electronic converters, grid
integration of renewable power, and stability analysis
of the HVDC transmission systems.

## Biography

Jinyu Wen (Member, IEEE) received the B.Eng.
and Ph.D. degrees in electrical engineering from
the Huazhong University of Science and Technology
(HUST), Wuhan, China, in 1992 and 1998, respectively. He was a Visiting Student from 1996 to 1997
and Research Fellow from 2002 to 2003 with the
University of Liverpool, Liverpool, U.K., and a Senior
Visiting Researcher with the University of Texas at
Arlington, Arlington, TX, USA, in 2010. From 1998
to 2002, he was a Director Engineer with XJ Electric
Co. Ltd. in China. In 2003, he joined the HUST and
is currently a Professor with HUST. His research interests include renewable
energy integration, energy storage application, dc grid, and power system
operation and control.

<!-- PAGE BREAK -->

<!-- Page 16 -->
