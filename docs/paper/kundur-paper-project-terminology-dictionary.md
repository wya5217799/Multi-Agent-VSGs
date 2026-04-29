# Kundur 论文-项目术语字典与彻底解决路线图

**Date:** 2026-04-30
**Scope:** Yang et al. TPWRS 2023 修改版 Kundur 双区系统的论文文字 ↔ 项目实现的系统性映射
**Status:** Canonical reference — 所有 Kundur paper-alignment 决策必须先过这份字典
**Sources:**
- 论文转译：`docs/paper/high_accuracy_transcription_v2.md`（line 引用本文中标 P-line）
- 论文事实库：`docs/paper/yang2023-fact-base.md`
- 现有偏差备案：`docs/paper/{action-range-mapping,eval-disturbance-protocol}-deviation.md`，`docs/paper/disturbance-protocol-mismatch-fix-report.md`
- 项目 v3 build：`scenarios/kundur/simulink_models/build_kundur_cvs_v3.m`（line 引用本文中标 B-line）

---

## 0. TL;DR

**根因（root cause）：** 项目把论文当字符串复刻（"Bus 14/15"、"LoadStep 248 MW"、"r_f 公式"、"47% improvement"），没把论文当物理模型核对（"Bus 14/15 在 *本拓扑* 是什么 bus？"、"breaker 跟 RLC 串联电阻数学等价但物理过程是不是？"、"r_f 的 Δω 是 pu 还是 Hz？"、"47% 是基于哪个 reference 的相对值？"）。每发现一处不对，零散地写一份 deviation 报告，没把所有 case 归到一个统一的字典上。

**本文档的功能：**
1. **§2** 提供完整的论文 ↔ 项目术语字典 — 每条术语都标注「论文文字含义」「项目实现含义」「是否一致」，杜绝下次还机械搬运。
2. **§3** 在字典基础上把所有偏差登记到一张表，按 Tier A/B/C/D 分类。
3. **§5–6** 给一棵决策树：哪些必须修、哪些可计算性对齐、哪些接受 deviation。
4. **§7** 列禁止再做的操作（防止已经验证过没用的事再来一遍）。

**核心结论：** 接下来 paper alignment 的工作分三层：
- **Layer 1（已完成 / 本文档）**：把每个论文术语在项目中的实际指代写下来，杜绝「机械复刻」类失误；
- **Layer 2（独立 issue）**：解 Q7（H 单位）与 Q8（r_f 归一化），让数值对账有定义；
- **Layer 3（破锁，按需）**：物理层重做拓扑/扰动机制以拿到 paper-faithful 数值（Option E/G in `disturbance-protocol-mismatch-fix-report.md`）。

不在 Layer 3 之前盲目调超参；不在 Layer 2 之前盲目对账数字。

---

## 1. 根因诊断：四个被「文字-物理混淆」拖坏的样本

| # | 论文文字（PRIMARY） | 项目实现 | 文字层 | 物理层 |
|---|---|---|---|---|
| 1 | Bus 14, Bus 15 (P-line 993) | v3 拓扑：Bus 14 = ES3 终端，Bus 15 = ES4 终端，1 km Pi-line 远离 Bus 10/Bus 9 load center | ✅ "字面 bus 编号一样" | ❌ Bus 14/15 在 v3 是 ESS 终端短桩；论文 Fig.3 中应是 load 节点。Bus 7（967 MW）+ Bus 9（1767 MW）才是 v3 真实 load center |
| 2 | "sudden load reduction of 248 MW at bus 14" (P-line 993) | Series RLC Branch with `Resistance = V²/LoadStep_amp`，写 `LoadStep_amp_bus14 = 248e6` | ✅ "也是切 248 MW 等效负荷"（V²/R 数值对得上）| ❌ 论文 = breaker on/off（电气网络突变）；项目 = .slx 编译时常数（FastRestart 下 workspace 改值不重新求值，5 scenarios bit-identical，max\|Δf\|=0.0091 Hz 全是 IC kickoff 残留） |
| 3 | r_f 公式（P-line 591-595）+ test-set cum 公式（P-line 970-979）| 项目用 Hz 单位（`Δω_pu × F_NOM`），sum 公式照抄但 `M=25` vs paper `M=50`，归一化系数不知道 | ✅ "公式形状一致" | ❌ Δω 单位（pu / Hz）未确定（Q7 + Q8 OCR 损坏），归一化系数（1/M? 1/N?）未确定。-15.20 vs -395.74 这种几个数量级差完全可能由单位差异解释 |
| 4 | "the proposed control has greatly improve... cumulative reward -8.04 vs -15.20" (P-line 982-984) | 项目最佳 P0' v2 trained = -19.54，no_control = -21.73，improvement = 10% | ✅ "也用 cum reward 来比" | ❌ 项目协议（Pm-step proxy at ESS internal）≠ 论文协议（network LoadStep at load bus），baseline 与 trained 都在不同 reward landscape 下，**直接对比 47% vs 10% 是 apples vs oranges**（详见 `eval-disturbance-protocol-deviation.md` + `disturbance-protocol-mismatch-fix-report.md`） |

**模式总结：**
> 复刻论文文字（变量名、公式形状、bus 编号、数值靶子），不复刻论文物理（变量在 *本拓扑* 中的电气位置、扰动信号实际进入网络的通道、单位空间、对比基准的协议）。

**反向防御原则：每次引用论文术语前，问三句：**
1. 这个 bus / 块 / 信号在 *项目当前拓扑* 中**电气上**是什么？（不是字面编号一样就一样）
2. 论文这个公式的**单位空间**是什么？（pu / Hz / sec / ω_n 频率单位都要核对）
3. 这个数值靶子是在**什么协议下**算出来的？（同协议的对比才有意义）

---

## 2. 论文 ↔ 项目 Kundur 术语字典

### 2.1 物理拓扑层（Topology）

| 论文术语 | 论文 PRIMARY | 项目 v3 实现 PRIMARY | 状态 | 说明 |
|---|---|---|---|---|
| **Modified Kundur two-area system** | P-line 889-893：参考 [49] Kundur 经典双区，G4 替换为同容量风电 | `kundur_cvs_v3.slx`（16-bus，Phasor solver）；3 SG（G1/G2/G3）+ 2 PVS（W1/W2）+ 4 ESS swing-eq | ✅ 一致（拓扑变种 `v3_paper_kundur_15bus_w2_at_bus8_ls1_preengaged`，B-line 39-40）| Task 1（2026-04-28）把 W2 从中间节点 Bus 11 直接挪到 Bus 8，与 paper line 894 对齐 |
| **G4 → wind farm** | P-line 893：G4 替换为同容量风电场（200 MVA） | v3 中 G4 不存在，由 W1（PVS at Bus 4）替代；Bus 4 → Bus 9 经 L_4_9（B-line 105）| ✅ | "同容量"在 v3 = 200 MVA，与论文一致 |
| **100 MW wind farm at bus 8** | P-line 894 | v3：W2 PVS 直接接 Bus 8（Task 1 修复，B-line 60-62）| ✅ | 历史 bug：v3 早期把 W2 接在 Bus 11 中介节点，2026-04-28 修复为 paper-faithful |
| **Bus 7（load center）** | 论文 Fig.3（图未在转录稿中，但 [49] 经典 Kundur 给出）| v3 Bus 7：967 MW + 100 Mvar load + 200 Mvar shunt cap（B-line 124, 127）| ✅ | 真实 load center |
| **Bus 9（load center）** | 论文 Fig.3 | v3 Bus 9：1767 MW + 100 Mvar load + 350 Mvar shunt cap（B-line 125, 128）| ✅ | 真实 load center |
| **Bus 14 / Bus 15（论文文字 PRIMARY，case 1）** | P-line 993-994："sudden load reduction of 248MW at bus 14 ... load increase of 188MW at bus 15" | v3：Bus 14 = ES3 内电势节点终端，连接 Bus 10 经 L_10_14（1 km Pi-line）；Bus 15 = ES4 终端，连接 Bus 9 经 L_9_15（1 km Pi-line）| ⚠️ **物理位置不一致** | 论文中 Bus 14/15 是 *load* bus；v3 中是 *ESS terminal* bus，1 km Pi-line 从 load center 隔开。LoadStep 块虽然字面挂在 Bus 14/15，但**电气距离上偏离 paper 想表达的"在 load center 切负荷"**。详见 §3 row D-T1 |
| **4 ESS "separately connected to different areas"** | P-line 896-897 | v3：ES1@Bus 12，ES2@Bus 16，ES3@Bus 14，ES4@Bus 15（B-line 45-46） | ⚠️ **electrical-area mismatch** | 论文未给具体 bus 编号（Q5 未确认），项目按 v3 spec 选定 4 个不同区域终端。**2026-04-30 Probe B 实证**（`results/harness/kundur/cvs_v3_probe_b/PROBE_B_STOP_VERDICT.md`）：项目假设 ES1+ES2 同属 area 1，ES3+ES4 同属 area 2；但 SG-side sign-pair pair（G1/G2/G3 各 ±0.5 sys-pu）显示 G1+G2 → 仅 ES1 响应，G3 → ES3+ES4 响应，**ES2 (Bus 16) 在所有 3 个 SG-side 扰动下都是 noise floor**（std ~ 5e-6 pu）。ES2 是 universal dead agent under any `pm_step_proxy_g*` protocol。详见 §3 row D-T6 |
| **Kron reduction** | Eq.4 + Remark 1（fact-base §2.2）："eliminates the bus with no energy storage" | v3 保留完整 16-bus（无 Kron 化简）| ⚠️ 概念 vs 实现差异 | 论文是用 Kron-reduced 矩阵推 Proposition 1（理论分析）；论文 Sec.IV 实验用的是 *full Kundur* + Simulink，未做 Kron 化简。项目 v3 也用 full topology → 与论文实验路径一致，与论文理论部分不一致是正常 |
| **Pi-line 1 km from load to ESS** | 论文 Fig.3 中通常画为短桩（ESS 接入点）| L_7_12 / L_8_16 / L_10_14 / L_9_15 都是 1 km, R_short=0.01, L_short=0.5e-3, C_short=0.009e-6（B-line 117-120 vs 96-98）| ✅ 与 v3 spec 一致 | spec 来源：`build_kundur_cvs_v3.m` 注释 |

**关键 take-away：项目 v3 中真正的 paper-Fig.3-load-bus 是 Bus 7 和 Bus 9，不是 Bus 14/15。** Bus 14/15 是 ESS 接入点。如果要做 paper-faithful 的"在 load 节点切负荷"，扰动应该发生在 Bus 7/9（参见 `disturbance-protocol-mismatch-fix-report.md` Option E）。

### 2.2 扰动层（Disturbance）

| 论文术语 | 论文 PRIMARY | 项目 v3 实现 | 状态 | 说明 |
|---|---|---|---|---|
| **"Load step 1: 248 MW reduction at bus 14"** | P-line 993 | LoadStep_bus14：Series RLC R 块，Resistance=`Vbase²/max(LoadStep_amp_bus14, 1e-3)`；IC = 248e6 W（B-line 209-225）；触发 = env 写 0 → R 解列 → freq UP（B-line 211-215）| ⚠️ **机制错位 + 信号弱** | 字面（V²/R）量纲对，物理过程错。Series RLC R 的 Resistance 在 .slx 编译时冻结，FastRestart 下运行时改 workspace var 不重新求值（`eval-disturbance-protocol-deviation.md`§2.1）。Smoke 实测 5 scenarios bit-identical，max\|Δf\|=0.0091 Hz 全是 IC kickoff 残留。详见 §3 row D-T2 |
| **"Load step 2: 188 MW increase at bus 15"** | P-line 994 | LoadStep_bus15：同上结构，IC = 0；触发 = env 写 188e6 → R 接通 → freq DOWN | ⚠️ 同上 | 同 LS1 |
| **Breaker semantics（隐含）** | P-line 993 "sudden" 意味着断路器跳闸/合闸 | 项目用 R 切换模拟（V²/R = P_load）| ⚠️ | 数学等价，但 Phasor solver 下 R 块编译期冻结。要 paper-faithful breaker 需 Switch + R-bank 拓扑（Option G in fix report） |
| **CCS injection（项目扩展，非论文）** | — | LoadStep_trip_amp_busXX：Controlled Current Source + Constant 块，Constant.Value 表达式每 sim chunk 重 evaluate（B-line 396-414 之类）| ⚠️ 弱信号 | Smoke 实测 max\|Δf\|=[0.0093,0.0098] Hz，比 Pm-step proxy 同 magnitude 弱 ~40×。Bus 14/15 离 load center 远，注入效率低 |
| **Pm-step proxy（项目扩展，非论文）** | — | 在 G1/G2/G3 / ES1-4 的 swing-eq Pm 输入端注入 Constant→Product 链，由 workspace var `Pm_step_amp_<i>` 驱动；Constant 真正可调 | ⚠️ 信号正常但**物理通道是 mechanical input，不是 electrical network**（详见 `disturbance-protocol-mismatch-fix-report.md`§1.3-1.5）| Smoke max\|Δf\|=[0.08,0.41] Hz；4-ESS spatial pattern 偏弱（target 单点摆，其他 ≈0），导致 r_f 信号 spatial structure 不像论文 LoadStep 触发的 mode shape |
| **DIST_MAX scaling** | 论文未给具体 magnitude PDF | DIST_MAX=1.0 sys-pu (~100 MW)，2026-04-28 锁定（CLAUDE.md fact-base §10）| ✅ 工程决策 | 提升后用 no-control paper_eval 复测校准 |
| **Communication link failure** | P-line 902-903 + Sec.III-A："generated randomly" | env 实现：`COMM_FAIL_PROB`（config_simulink_base），观察通道 η_j 随机为 0 | ✅ | 与论文一致 |

**关键 take-away：v3 当前 production eval 协议是 Pm-step proxy（`pm_step_proxy_random_bus`，`eval-disturbance-protocol-deviation.md` 决议）。** 这意味着 v3 cum_unnorm 跟论文 -8.04 / -15.20 **不可直接对账**。要解锁论文级 RL improvement，必须走 fix report 的 Option E/G（破物理层 credibility close 锁）。

### 2.3 VSG 模型层（Dynamics）

| 论文术语 | 论文 PRIMARY | 项目 v3 实现 | 状态 | 说明 |
|---|---|---|---|---|
| **VSG 摆动方程 Eq.1** | $H\Delta\dot\omega + D\Delta\omega = \Delta u - \Delta P$（P-line 250），无 `2`、无 `ω_s` 系数（控制派集总形式，fact-base §2.1 Q7） | 项目 ODE 路径（历史）：`2H_code·ωdot = ω_s·(Δu - coupling) - D·ω`（电机学标准 rad/s 基值）；Simulink 路径：M=2H 同电机学传统 | ⚠️ Q7 未解决 | "H_paper = 2·H_code" 是项目工作假设（不是论文事实）；引用必须标"项目推断"（fact-base §2.1）；详细解释见 `action-range-mapping-deviation.md` §5 |
| **H 量纲** | 未给（fact-base §8 Q7） | 项目用 sec（电机学惯例）| ⚠️ unresolved | 不要在 Q7 解决前机械按 paper-literal [-100,300] 设 ΔH |
| **D 量纲** | 同 H 未明示 | 项目 vsg-pu | ⚠️ unresolved | 同上 |
| **H_es,0 baseline 数值** | 未给（fact-base §3.3）| ESS_M0=24（=2·H=12，B-line 86, 93）；以 [49] 经典 Kundur 6.5/6.5/6.175 推 G1-G3 | ✅ 项目工程选择 | 与 [49] 经典对齐 |
| **D_es,0 baseline 数值** | 未给 | ESS_D0=4.5 vsg-pu（B-line 94）| ✅ 项目选择 | Phase C 实测 floor-clip 验证（`action-range-mapping-deviation.md`§4.1）|
| **ΔH 范围** | P-line 938："$-100$ to $300$"（无单位） | DM_MIN=-6, DM_MAX=18 | ⚠️ deviation, documented | 33× narrower than paper-literal；详见 `action-range-mapping-deviation.md` |
| **ΔD 范围** | P-line 938-939："$-200$ to $600$" | DD_MIN=-1.5, DD_MAX=4.5 | ⚠️ deviation, documented | 133× narrower；同上 |
| **Inner-loop dynamics 忽略** | P-line 261-263：ignore inner loop, only e-mech transient | 项目 Simulink 主线：内环用 swing-eq + IntD/IntW 积分器，没有完整 PWM/三相控制 | ✅ | 与论文一致 |
| **Voltage 假定 constant** | P-line 277 "Assuming voltage magnitudes are constant" | v3 ESS 用 CVS（恒压源）实现，VSG_CVS 内电势 |E| 固定，仅 angle 由 swing eq 决定 | ✅ | 与论文一致；这是为何叫 "CVS" path |

### 2.4 RL 训练层（Training）

| 论文术语 | 论文 PRIMARY | 项目实现 | 状态 | 说明 |
|---|---|---|---|---|
| **观测向量** Eq.11 | $o_i = (\Delta P_{es,i}, \Delta\omega_i, \Delta\dot\omega_i, \Delta\omega^c_{i,1..m}, \Delta\dot\omega^c_{i,1..m})$，dim = 3+2m | 项目 m=2 → dim=7 | ✅ | 与论文一致 |
| **m 邻居数** | P-line 1154 "two neighboring nodes"（NE39 部分明确）| Kundur + NE39 都 m=2，组成 ring topology（CLAUDE.md "Communication Topology"）| ✅ | |
| **动作语义增量** | Eq.12-13：$H_{i,t}=H_{i,0}+\Delta H_{i,t}$ | env 用 zero-centered action mapping → ΔM/ΔD（`env/simulink/kundur_simulink_env.py:_map_zero_centered_action`）| ✅ | 2026-04-14 修复（fact-base §10）|
| **r_f 频率同步惩罚** Eq.15 | $r_f = -(\Delta\omega - \bar{\Delta\omega})^2 - \Sigma_j (\Delta\omega^c_j - \bar{\Delta\omega})^2 \eta_j$ | env `_compute_reward()` 实现，单位 Hz（`Δω_pu × F_NOM`，fact-base §10 row "奖励频率单位"）| ⚠️ unit Q8 unresolved | 论文未明确 Δω 单位；若论文用 pu，则 r_f 量级差 F_NOM²=2500× |
| **r_h, r_d 调整惩罚** Eq.17-18 | $-(\Delta H_{avg})^2$，$-(\Delta D_{avg})^2$（先平均再平方）| 已修复用 physical 量（fact-base §10 row）；avg 计算方式（global vs neighbor）= Q2 unresolved | ⚠️ Q2 unresolved | 当前用 global（"distributed average estimator"），论文协议未给 |
| **权重 φ_f / φ_h / φ_d** | P-line 940："rf=100, rh=1, rd=1"（变量名稍乱，应为 φ）| `PHI_F=100`（默认），Kundur 主线 `PHI_H=PHI_D=1e-4`（2026-04-28 lock）| ⚠️ φ_h/φ_d 偏离论文 | 项目论证：1e-4 是从 r_f vs r_h/r_d 的 magnitude 平衡校准来的，论文 1.0 在项目动作范围下会让 r_h/r_d 主导（详见 lock 决策）|
| **Replay buffer size** | Table I = 10000 | 50000 ~ 100000（fact-base §10）| ⚠️ documented | 工程扩展，不影响方法正确性 |
| **Mini-batch size** | Table I = 256 | 256（一致）| ✅ | |
| **每 episode steps M** | Table I + Sec.IV-A = 50（DT=0.2s, T=10s）| Kundur: STEPS=50, T=10s（config_simulink.py line 64-65 + CLAUDE.md "Simulink 主线"）| ✅ Kundur | NE39 differs（fact-base §10 row "Kundur T_EPISODE"）|
| **Buffer clear per episode** | Algorithm 1 line 16："Clear buffer D_i" | `CLEAR_BUFFER_PER_EPISODE = False`（标准 off-policy SAC 做法）| ⚠️ documented | Algorithm 1 与 Table I 内部矛盾（fact-base §7.1），项目按 Table I（buffer size 10000 + batch 256 → 不可能 per-episode clear）|
| **Independent learner per agent** | fact-base §7.5 "每 agent 独立参数" | Kundur Simulink 主线当前用参数共享 SAC（CTDE 风格） | ⚠️ documented | 与论文已知偏差，列在 fact-base §10 row "SAC 实例化" |
| **Training set 100 / Test set 50** | P-line 904-906 | `evaluation/paper_eval.py` 使用 `--n-scenarios 50 --seed-base 42`（与文档一致）| ✅ | |
| **Train/test 是否每 reset 重采样** | unresolved Q1 | 项目实现：scenario 由 seed-base + index 决定，固定 50 个场景重复 | ✅ assumption | 与"fixed scenarios"假设一致 |
| **训练时不引入 comm-delay** | P-line 627-630 | 项目训练：仅 comm-fail（η_j ∈ {0,1}），不加 delay | ✅ | 与论文一致；delay 是 Sec.IV-E offline test |

### 2.5 评估层（Evaluation）

| 论文术语 | 论文 PRIMARY | 项目实现 | 状态 | 说明 |
|---|---|---|---|---|
| **测试集 frequency reward** | P-line 970-979（OCR 损坏，fact-base §6.4 Q8）："$-\sum_t \sum_i (\Delta f_{i,t} - \bar f_t)^2$, $\bar f_t = \sum_i \Delta f_{i,t}/N$" | `evaluation/paper_eval.py::compute_global_freq_reward` | ✅ formula shape | Q8: 1/M / 1/N 归一化系数未确认 |
| **DDIC cum reward 50 ep** | -8.04（P-line 982-983）| 项目 P0' v2 trained = -19.54 | ⚠️ 不可直接对账 | 协议不同（`eval-disturbance-protocol-deviation.md`）|
| **Adaptive inertia [25] cum** | -12.93 | 项目未实现 [25] 对比方法 | ⚠️ N/A | 不在当前 scope |
| **No-control cum** | -15.20（P-line 984）| 项目 P0' v2 = -21.73 | ⚠️ baseline gap -6.5 | 仍是协议差异（disturbance-protocol-mismatch-fix-report §1.1）|
| **Single-episode load step 1 / 2** | -1.61 / -0.80（no-ctrl）；-0.68 / -0.52（DDIC）（P-line 1031-1034） | 项目 v3 LoadStep 协议被破（信号 0.0091 Hz），不能复现 | ⚠️ 协议失效 | 详见 §3 row D-T2 |
| **Comm-failure cum** | "little influence on the cumulative reward"（P-line 1041-1042）| 未独立实验 | ⚠️ N/A | |
| **Comm-delay cum** | -9.53（P-line 1085）| 未独立实验 | ⚠️ N/A | |
| **47% RL improvement** | (-8.04 - (-15.20)) / -15.20 = 47.1%（项目算式，非论文文字）| (-19.54 - (-21.73)) / -21.73 = 10.1% | ⚠️ apples vs oranges | 不同 reward landscape，项目 10% 不能解读为"达到 paper 47% 的 21%"|

---

## 3. 偏差完整登记（Deviation Registry）

按处置层分四类（Tier）：
- **Tier A — Physics-essential**：物理层不一致；要拿 paper-faithful 数值对账必须修
- **Tier B — Dimensional / Calibration**：单位空间或归一化未确定；先解 ambiguity 再决定
- **Tier C — Engineering deviation, documented**：项目工程选择，理由充分，接受
- **Tier D — Paper-side ambiguity**：论文本身未给清楚，无修复目标

| ID | 偏差名 | Tier | PRIMARY 链接 | 当前状态 | 解决路径 |
|---|---|---|---|---|---|
| D-T1 | Bus 14/15 是 ESS 终端而非 load 节点 | A | §2.1 row "Bus 14 / Bus 15"，本文档 case 1 | 字面 bus 编号一致，物理位置错位（1 km Pi-line 远离 load center Bus 7/9）| Option E：在 Bus 7/9 注入扰动（CCS at load center），破 credibility close 锁。详见 `disturbance-protocol-mismatch-fix-report.md` |
| D-T2 | LoadStep R 块 .slx-compile-frozen | A | `eval-disturbance-protocol-deviation.md`§2.1，本文档 case 2 | LoadStep_bus14/15 路径已**事实上失效**（5 scenarios bit-identical 实证）；production 走 `pm_step_proxy_random_bus` | Option G：Switch+R-bank 拓扑替代 Series RLC R，破 credibility close 锁；或 Option E（CCS）|
| D-T3 | Pm-step proxy 是 mechanical input，不是 network electrical | A | `disturbance-protocol-mismatch-fix-report.md`§1.3-1.5 | Production 协议默认；4-ESS 缺 mode-shape spatial structure，r_f signal 类不像 paper LoadStep | 同 D-T1/D-T2；fix report Option B（SG-side cheap pilot）作为 0-cost 探索 |
| D-T4 | 47% improvement 不能与 10% improvement 直接对比 | A | 本文档 case 4，`disturbance-protocol-mismatch-fix-report.md`§1.1 | 协议不同 → 不同 reward landscape | 物理层修好后重新评估；不修则永远是 apples vs oranges |
| D-T5 | Bus 14/15 LoadStep 块 build 注释自相矛盾 | A（doc bug）| `build_kundur_cvs_v3.m` B-line 13 ("LoadStep on Bus 7/9") vs B-line 154-156（实际挂在 Bus 14/15）| 注释错误 / 实现错位（不知是注释错还是设计漂移）| 简单修：把 B-line 13 注释改成"Bus 14/15"，或重新审 spec 决定真实位置 |
| D-T6 | ES2 (Bus 16) 在 SG-side 协议下是 universal dead agent (per-agent learning signal = 0) | A | `results/harness/kundur/cvs_v3_probe_b/PROBE_B_STOP_VERDICT.md`（2026-04-30 Probe B sign-pair G1/G2/G3）| 实证：G1/G2 仅 ES1 响应（ES2 std=5e-6 pu）；G3 仅 ES3+ES4 响应（ES1+ES2 都死）。期望训练 random_gen 下 ES2 在 0% scenarios 收到 r_f gradient。RL 4-agent coordination paper claim 在此协议下结构性不可达 | 同 D-T1/D-T3：要破协议级 1-of-4 限制必须 (a) Option F 多点 Pm-step（仍可能漏 ES2 — 需加 ESS-direct injection），或 (b) Option E network LoadStep at Bus 7/9（理论上 admittance matrix 让 4 ESS 都看到信号；待物理实证）|
| D-Q7 | H/D 量纲未给 → ΔH/ΔD 范围 33×/133× narrower | B | `action-range-mapping-deviation.md`，fact-base §8 Q7 | documented deviation；当前 ΔM=[-6,+18] / ΔD=[-1.5,+4.5] | Q7 解决（联系作者 / 跨论文比对 / 标准约定识别）后 re-derive |
| D-Q8 | r_f / cum reward 公式 unit + 归一化未确定 | B | fact-base §6.4 Q8 + §8 Q8，本文档 case 3 | 项目用 Hz；归一化 sum-only（无 1/M 1/N） | Q8 OCR 重读 / 联系作者；解后才能做 cum_unnorm 数值对账 |
| D-Q1 | Train/test 是否每 reset 重采样未确定 | B | fact-base §6.2 Q1 | 假设固定 100/50；项目按这个跑 | 联系作者；当前假设合理 |
| D-Q2 | $\Delta H_{avg}$ 计算协议（global vs neighbor avg）| B | fact-base §8 Q2 | 项目用 global（"distributed average estimator"） | 论文未明确；当前合理 |
| D-Q5 | 4 ESS 具体 bus 位置 | B | fact-base §8 Q5 | 论文 "separately connected to different areas"；项目 Bus 12/16/14/15 | 接受；只要 4 个不同区域即可 |
| D-Q6 | 每 episode gradient steps 数 | B | fact-base §8 Q6 | 项目按 every-step + warmup 1000 | 接受 |
| D-E1 | Buffer clear strategy（Algorithm 1 vs Table I）| C | fact-base §7.1, §10 | 不清空（按 Table I）| 已决；接受 |
| D-E2 | Independent learner vs parameter sharing | C | fact-base §7.5, §10 | Simulink Kundur 主线参数共享 | 已决（CTDE）；接受 |
| D-E3 | Replay buffer 50000 vs paper 10000 | C | fact-base §10 | 工程扩展 | 接受；不影响方法 |
| D-E4 | Episode count 500 vs paper 2000 | C | fact-base §10 | 工程效率默认；复现需 `--episodes 2000` | 接受 |
| D-E5 | Kundur T_EPISODE 5s vs paper 10s | C | fact-base §10 | 已修：Kundur 现 10s（M=50）= paper（config_simulink.py:64-65 + CLAUDE.md "Simulink 主线"）| ✅ 已对齐（曾偏差，已修复）|
| D-E6 | PHI_H = PHI_D = 1e-4 vs paper 1.0 | C | CLAUDE.md fact-base §10 row "PHI 锁定" | r_f vs r_h/r_d magnitude balance；2026-04-28 lock | 接受 |
| D-E7 | DIST_MAX 1.0 sys-pu | C | fact-base §10 row | 2026-04-28 lock，与 paper baseline -15.20 复测校准 | 接受 |
| D-E8 | Default disturbance type `pm_step_proxy_random_bus` | C | `eval-disturbance-protocol-deviation.md` | 物理层 LoadStep 失效 → 退到 Pm-step proxy | 接受为 v3 de facto；解锁需 D-T1/D-T2 修 |
| D-E9 | Wind farm W2 from Bus 11 → Bus 8 直接 | C | B-line 60-62 (Task 1, 2026-04-28) | 已修复 | ✅ 已对齐 |
| D-E10 | Build script 注释 "Bus 7/9 LoadStep" 与实现 "Bus 14/15" 冲突 | C（doc-bug）| B-line 13 vs B-line 154-156 | 待清理（同 D-T5）| 改注释 |

---

## 4. 偏差分类原则（Why Tier ABCD）

### 4.1 Tier A — 物理对齐缺口

**判据：** 不修则**论文数值靶子永远不可对账**，且 RL 学到的 policy 在 paper-class 协议下不一定 generalize。

**典型：** D-T1 ~ D-T5。

**处置：** 进 fix report 决策树，选 Option B/E/G。**禁止**在 Tier A 未修前调超参追靶子（会得到 over-fit 到错协议的 policy）。

### 4.2 Tier B — 维度/单位 ambiguity

**判据：** 论文未给清楚（OCR 损坏 / 关键术语未定义），项目按合理假设走，但**对账数字时差异可能由这个决定**。

**典型：** D-Q7 / D-Q8。

**处置：**
1. 第一优先级：通过 cross-reference paper / 联系作者 / 跨 Yang 团队论文核对 等手段**消除 ambiguity**。
2. 没消除前，**禁止**直接用 paper-literal 数字（[-100, 300] / -8.04 / -15.20）做项目决策的硬约束。
3. 已 documented 偏差是当前正确做法。

### 4.3 Tier C — 已 documented 工程偏差

**判据：** 项目主动选择偏离论文，理由充分（工程效率 / 数值稳定 / 工程实践 / Algorithm-vs-Table 内部矛盾），已写决策文档。

**典型：** D-E1 ~ D-E10。

**处置：** **不动**。每条都有决策依据。reviewer 提出"为何与论文不同"时直接指向 fact-base §10 + 决策文档。

### 4.4 Tier D — 论文侧 ambiguity（无 owner）

**判据：** 同 Tier B，但项目当前已经按假设跑通，没有压力解。

**典型：** D-Q1, D-Q2, D-Q5, D-Q6。

**处置：** 列入 fact-base §8，遇到论文作者 / 高 priority 复现需求时再消除。

---

## 5. 解决路线图（Resolution Roadmap）

### Phase 1：字典锁定（本文档，已完成）

**Deliverable：** §2 字典 + §3 偏差登记。
**Output：** 这份 markdown。
**Cost：** ~0（doc only）。
**Acceptance criteria：**
- [x] 每个论文术语都有项目对应 + 一致性标注
- [x] 每个已知偏差都登记到 §3 表
- [x] 每个 Tier A 偏差有具体修复路径指向

### Phase 2：单位/度量对齐（Tier B 解 ambiguity）

**Deliverable：** Q7（H 单位）+ Q8（r_f 归一化）的 resolution 决策。

**子任务：**
- **Q7-resolve：** 联系作者 / 找 Yang 同团队 prior publications / 找 TPWRS 同结构（H·ω̇+D·ω 集总形式）的 reference paper 看其约定单位。如果 Q7 解出 `H_paper = 2·H_code` 是 paper convention，则 ΔH=300 ⇒ ΔM=600，仍需 Phase C 物理校准（floor-clip）。如果 Q7 解出 `H_paper` 是某 base 的 pu，需重新 derive ESS_M0。
- **Q8-resolve：** 重做 Sec.IV-C OCR（更高分辨率原 PDF 重转），或对比同段 Eq.15 的 r_f 公式确认 Δω 单位。

**Output：** 更新 `action-range-mapping-deviation.md` + 在本字典 §2.3/§2.5 把 Q7/Q8 状态改 ✅。

**Cost：** 1-2 周（取决于联系作者是否有响应）。

**Acceptance criteria：**
- [ ] Q7 给出 H_paper 单位决议（或确认无法决议）
- [ ] Q8 给出 cum reward 公式 1/M 1/N 归一化决议
- [ ] 用决议后单位重新计算项目 cum_unnorm vs paper -15.20，看 baseline gap 是否仍 -6.5（如果不是则单位差异是部分根因）

### Phase 3：物理层重做（Tier A，破 credibility close 锁）

**Deliverable：** v3 拓扑能产生 paper-faithful 的 4-ESS desync mode shape。

**触发条件（任一）：**
- 论文级数值对账（cum_unnorm ≈ -15.20 no-ctrl, ≈ -8.04 trained）成为 binding 验收标准
- Phase 2 Q8 解决后 baseline gap 仍 > 3（说明协议差异是主因）

**子任务（按 fix report 决策树）：**
1. **Phase 3a (cheap pilot)：** Option B — `KUNDUR_DISTURBANCE_TYPE=pm_step_proxy_random_gen` (SG-side)，0 code 改，~30 min validation，看 no-ctrl cum_unnorm 是否进 [-18, -15]。
2. **Phase 3b：** 按 Phase 3a 结果走 Option E（CCS at Bus 7/9）或 Option G（Switch+R-bank at Bus 14/15）。两者都需重 `build_kundur_cvs_v3.m` + 重 NR + 重 IC + 重 smoke + 重 train。
3. **Phase 3c：** Phase 3b 后重训 + paper_eval 4-policy（no_control, ep50, best, ep_max）；目标 RL improvement > 30%。

**Cost：** 1-4 天 build + retrain（按选哪个 option）。

**Acceptance criteria：**
- [ ] no-ctrl cum_unnorm ∈ [-17, -13]（接近 paper -15.20）
- [ ] trained cum_unnorm < no-ctrl × 70%（≥ 30% improvement）
- [ ] 4 ESS Δω peak 在 LoadStep trigger 后呈 mode-shape pattern（非单点摆）

---

## 6. 决策树

```
你现在想做什么？
│
├── (A) 引用 paper 的某个 bus / 公式 / 数字
│   → 先查 §2 字典，看项目当前实现的指代是不是同一个东西
│   → 如果不是同一个，走 (B) 或者 (C)
│
├── (B) 修一个 paper-misalignment bug
│   ↓
│   先到 §3 表查它的 Tier
│   ├── Tier A → 必须改物理层。先看 fix report 决策树，破不破 credibility close 锁。
│   │           **不要**先调超参 / reward 权重 / 训练时长。
│   ├── Tier B → 先解 Q7/Q8 ambiguity，再决定是否修 implementation。
│   │           **不要**机械按 paper-literal 数字硬改 implementation。
│   ├── Tier C → 不动。这个偏差已经 documented，理由在引用的决策文档里。
│   │           如果你认为 documented rationale 不再成立，先 challenge rationale，再改。
│   └── Tier D → 接受 ambiguity。如果是 binding requirement 就联系作者。
│
├── (C) 跑 paper_eval 看数字
│   ↓
│   先 acknowledge 当前协议 = `pm_step_proxy_random_bus`（D-E8）
│   ├── 关心 trained vs no_control RL improvement → 在同协议下比较，10% 是当前 ground truth
│   ├── 关心 cum_unnorm vs paper -8.04 / -15.20 → **不可直接对账**（D-T4）
│   └── 想达到 paper 数字 → 走 Phase 3
│
├── (D) 调超参追改善
│   ↓
│   先确认所有 Tier A 都 close（D-T1~D-T5）
│   ├── 否 → STOP。先 fix Tier A，否则 RL 在错 reward landscape 下 overfit
│   └── 是 → 进 HPO（fact-base §10 PHI lock 之后 + Phase 3b 物理层修好之后）
│
└── (E) 添加新论文术语 / 新公式 / 新数值靶子
    → 先扩 §2 字典对应小节
    → 再扩 §3 偏差表
    → 写代码前 commit 字典更新
    → 防再次"机械文字转译"
```

---

## 7. 反对操作清单（What NOT To Do）

下列操作已经被验证过没用 / 走偏 / 浪费 token：

### 7.1 不要做的

1. **不要在 Q7/Q8 解决前用 paper-literal 数字做项目硬约束**。`ΔH ∈ [-100, 300]` 直接搬过来 → Phase C 实测 87% floor-clip → SAC 学不到（`action-range-mapping-deviation.md`§4.2-4.3）。
2. **不要把 Bus 14/15 当 paper Bus 14/15 字面对待**。v3 中 Bus 14/15 是 ESS terminal，不是 load center。LoadStep at Bus 14/15 ≠ paper LoadStep at "load bus"。
3. **不要假设 LoadStep R 块的 Resistance 表达式 runtime 改值有效**。`eval-disturbance-protocol-deviation.md` 实测 5 scenarios bit-identical 已证伪。
4. **不要直接对账项目 cum_unnorm vs paper -8.04 / -15.20**。协议不同 → 不同 reward landscape → apples vs oranges（`disturbance-protocol-mismatch-fix-report.md`§1.1）。
5. **不要在 Tier A 偏差未修前盲目调 PHI / lr / batch / network width 追改善**。RL 会 overfit 到错协议的 reward landscape。`p0_v2_paper_eval_verdict.md` 已证：调 PHI 到 r_f% target band，trained policy eval 性能没相应提升。
6. **不要在没读 §3 偏差登记前提"为何 X 偏离论文"**。所有 Tier C 都有决策文档，先看 rationale 再 challenge。
7. **不要把 Algorithm 1 与 Table I 同时奉为真。** 它们内部矛盾（fact-base §7.1）。Buffer 大小 10000 + batch 256 + per-episode clear 在 M=50 时不可能同时成立。项目按 Table I（即不清空）。
8. **不要尝试改 Phasor solver 为 Discrete solver 让 Variable Resistor 工作**。Solver 切换是物理层根本变更，影响所有 source / network / IC，> 1 周成本（fix report §2.5 Option C）。
9. **不要写一份新的偏差报告**。先看本字典 §3 是否已登记。已登记则 update 状态；未登记则在表中添加新行后再写细节文档。
10. **不要把 4 ESS spatial pattern 当成"4 个独立 single-agent"。** Yang 2023 的 RL 学的是 cooperative sync，依赖 mode-shape 触发的 4-ESS desync。Pm-step proxy 单点摆 → 不能学这个 pattern（`disturbance-protocol-mismatch-fix-report.md`§1.6）。

### 7.2 不要立刻做的（需先 demonstrating prerequisite）

1. **不要立刻跑 HPO**。先 close Tier A（fix report Phase 3）和 Tier B Q8（确认 cum 可对账）。
2. **不要立刻破 credibility close 锁。** 先用 Option B（SG-side, 0 code）验证物理方向，再决定破不破。

---

## 8. 引用与依据（References）

### 8.1 论文 PRIMARY
| 内容 | line / 段 |
|---|---|
| 全文转译 | `docs/paper/high_accuracy_transcription_v2.md` |
| Eq.1 摆动方程 | P-line 250 |
| Sec.II-A 模型 | P-line 247-310 |
| Eq.4 矩阵形式 | P-line 295-300 |
| Sec.III-A 观测/动作/奖励 | P-line 466-660 |
| Sec.IV-A 仿真设置 | P-line 887-916 |
| Sec.IV-B 训练性能（含动作范围 / 权重）| P-line 933-953 |
| Sec.IV-C cum reward + LoadStep 1/2 | P-line 954-996 |
| Algorithm 1 | P-line 789-806 |
| Table I 超参 | P-line 873-885 |

### 8.2 项目 PRIMARY
| 内容 | path |
|---|---|
| Build script | `scenarios/kundur/simulink_models/build_kundur_cvs_v3.m` |
| Env entry | `env/simulink/kundur_simulink_env.py` |
| Config | `scenarios/kundur/config_simulink.py` |
| Disturbance protocols | `scenarios/kundur/disturbance_protocols.py` |
| Workspace var schema | `scenarios/kundur/workspace_vars.py` |
| Eval | `evaluation/paper_eval.py` |
| Modification notes | `scenarios/kundur/NOTES.md` |
| Fact base | `docs/paper/yang2023-fact-base.md` |

### 8.3 已有偏差文档（被本字典统合）
| 偏差 | 详细文档 |
|---|---|
| ΔH/ΔD 范围 (D-Q7) | `docs/paper/action-range-mapping-deviation.md` |
| Eval disturbance 协议 (D-T2/D-E8) | `docs/paper/eval-disturbance-protocol-deviation.md` |
| Disturbance 协议 root cause (D-T1/T2/T3/T4) | `docs/paper/disturbance-protocol-mismatch-fix-report.md` |
| Buffer / SAC 偏差 (D-E1/E2) | `docs/decisions/2026-04-10-paper-baseline-contract.md` |
| CVS v3 credibility close (D-E6/E7/E8/E9) | `docs/decisions/2026-04-10-paper-baseline-contract.md` §2026-04-28 |
| C1+C4 disturbance dispatch + Scenario VO | `docs/decisions/2026-04-29-kundur-cvs-disturbance-protocol-and-scenario-vo.md` |
| C3 workspace var schema | `docs/decisions/2026-04-29-kundur-workspace-var-schema-boundary.md` |

### 8.4 关键证据 verdict
| 论点 | 证据 |
|---|---|
| LoadStep R-mode bit-identical（信号失效）| `results/harness/kundur/cvs_v3_eval_fix_smoke/loadstep_metrics.json` (Smoke A) |
| LoadStep CCS-mode 0.01 Hz 弱信号 | 同上 (Smoke D) |
| Pm-step proxy 信号正常 | 同上 (Smoke B) |
| Pm-step ESS-side 单点摆 spatial pattern | `disturbance-protocol-mismatch-fix-report.md`§1.4-1.5 |
| Phase C floor-clip empirical | `results/harness/kundur/cvs_v3_phase_c/phase_c_action_range_verdict.md` |
| Credibility close 4/4 PASS | `results/harness/kundur/cvs_v3_credibility_close/credibility_close_verdict.md` |
| P0' v2 trained -19.54 vs no_ctrl -21.73 | `p0_v2_paper_eval_verdict.md` |

---

## 9. 状态与维护（Status & Maintenance）

### 9.1 当前状态（2026-04-30）
- **Phase 1 字典锁定：** ✅ 本文档落地
- **Phase 2 单位对齐：** ⏳ Q7/Q8 unresolved，无 owner
- **Phase 3 物理层重做：** ⏳ awaiting user 裁决（fix report Step 0）
- **Probe B (2026-04-30)：** ✅ 完成。Measurement 层清白（per-agent omega 不 collapsed），但实证 audit R5 + 新发现 D-T6（ES2 dead agent）。证伪了"4-agent collapse"假设，证实了"single-point disturbance → 1-2/4 agent learning signal"假设。详见 `results/harness/kundur/cvs_v3_probe_b/PROBE_B_STOP_VERDICT.md`

### 9.2 维护规则
1. **新增 paper 术语 → 字典 §2 加行 + §3 加行（如有偏差）**。先扩字典再写代码。
2. **修一个偏差 → 更新 §3 表 status + 链接 commit**。
3. **新发现一个偏差 → §3 加行 + Tier 标注 + 决定走哪个 phase**。
4. **状态字段允许：** ✅ 一致 / ⚠️ 偏差但 documented / ❌ 偏差未 documented（不允许长期存在 ❌）。

### 9.3 Owner & 审阅
本文档是 Kundur paper-alignment 的 canonical reference。任何与论文相关的 PR/决策必须**先**对照这份字典：
- 引用的 paper 术语在 §2 是否已登记？
- 涉及的偏差在 §3 是否已记录？Tier 是否准确？
- 提议的修改属于 Phase 1/2/3 哪一阶段？

未对照 → reviewer 应要求作者先更新字典再合并。

### 9.4 反向 ledger（防"论文-项目脱钩"再发）
作为本字典的 byproduct，从此 *任何* 引用 paper 数字 / bus 编号 / 公式形状的代码或文档，必须满足：

```python
# 反例（机械搬运）
target = paper_results["DDIC"]  # -8.04
project_score = ...
assert abs(target - project_score) < TOL  # 不可能成立 — 协议不同

# 正例（带字典核对）
# Per `docs/paper/kundur-paper-project-terminology-dictionary.md` §2.5 row "DDIC cum":
# 项目 cum_unnorm 与论文 -8.04 不可直接对账 (D-T4 in §3, fix report §1.1)
# 比较应在同协议下：trained vs no_control under pm_step_proxy_random_bus
trained_score = run_paper_eval(policy="trained_best", protocol=PROTOCOL_V3)
no_ctrl_score = run_paper_eval(policy="no_control",   protocol=PROTOCOL_V3)
improvement = (trained_score - no_ctrl_score) / no_ctrl_score
print(f"RL improvement under v3 protocol: {improvement*100:.1f}%")
```

任何引用 paper 的 PR description 或 commit message 中**应**带上字典 §2 row 链接 + §3 Tier 标注。

---

## 10. Appendix — 高速核查清单（Quick Audit Before Touching Code）

修代码前 30 秒走完：

- [ ] 我要引用的 paper 术语在 §2 哪一行？
- [ ] 那一行的"项目实现"列写的是什么？是不是我要触碰的同一对象？
- [ ] 那一行状态是 ✅ / ⚠️？如果 ⚠️，§3 表对应的 Tier 是 A/B/C/D？
- [ ] 我要做的修改是 Phase 1（doc）/ Phase 2（dimension）/ Phase 3（physics）？
- [ ] 是不是 §7 反对操作清单里的事？
- [ ] 决策树 §6 把我导向哪个 branch？

任一项 unclear → STOP，先把字典 / 偏差表搞清楚再写代码。

---

*End of `kundur-paper-project-terminology-dictionary.md`*
*维护人：项目主线（Kundur paper-alignment scope）*
*Last updated: 2026-04-30*
