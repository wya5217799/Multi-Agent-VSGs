# PHI Root-Cause Diagnostic Verdict

**Date:** 2026-04-29 15:58–15:59 (~1 min wall, single MATLAB cold start)
**Trigger:** User指令 — read-only diagnostic 解释为什么 Δω_i - ω̄_i ≈ 0
**Status:** **CLASSIFICATION: C-partial → 真因不是物理强同步，而是 PHI sweep 用了 weak-signal disturbance protocol。**
**Probe:** `probes/kundur/v3_dryrun/_phi_root_cause.py`（read-only，instance attr 路径未触模型/reward/config locked constants）

---

## 1. Diagnostic Evidence Table

### [1] Logger identity（acceptance gate A）

通过 MATLAB find_system + PortConnectivity tracing：

| ToWorkspace var | TW block | Source block | Port |
|---|---|---|---|
| omega_ts_1 | `kundur_cvs_v3/W_omega_ES1` | `kundur_cvs_v3/IntW_ES1` | 1 |
| omega_ts_2 | `kundur_cvs_v3/W_omega_ES2` | `kundur_cvs_v3/IntW_ES2` | 1 |
| omega_ts_3 | `kundur_cvs_v3/W_omega_ES3` | `kundur_cvs_v3/IntW_ES3` | 1 |
| omega_ts_4 | `kundur_cvs_v3/W_omega_ES4` | `kundur_cvs_v3/IntW_ES4` | 1 |

✅ 4 个 distinct ω 源块 (IntW_ES1..4)，**不是 measurement artifact (A)**。

### [2] Disturbance routing（acceptance gate B）

amp=+0.5 sys-pu, target=ES1 (idx 0), single_vsg dispatch:

| workspace var | value | expected | OK? |
|---|---:|---:|---|
| Pm_step_amp_1 | +0.5 | +0.5 | ✅ |
| Pm_step_amp_2 | 0 | 0 | ✅ |
| Pm_step_amp_3 | 0 | 0 | ✅ |
| Pm_step_amp_4 | 0 | 0 | ✅ |
| PmgStep_amp_1..3 | 0,0,0 | 0,0,0 | ✅ |
| LoadStep_amp_bus14 | 2.48e8 | 2.48e8 (IC retained) | ✅ |
| LoadStep_amp_bus15 | 0 | 0 | ✅ |

✅ Routing CLEAN，仅 ES1 被扰动；其他 source 全静默。**不是 routing artifact (B)**。

### [3] Physics @ amp=+0.5 sys-pu (Pm-step ES1, zero-action)

| 量 | 值 |
|---|---:|
| max\|Δf\|_1 (ES1) | **0.234 Hz** |
| max\|Δf\|_2 (ES2) | 0.001 Hz |
| max\|Δf\|_3 (ES3) | 0.002 Hz |
| max\|Δf\|_4 (ES4) | 0.009 Hz |
| pairwise_max overall | **0.235 Hz** |
| common_mode_max | 0.058 Hz |
| differential_max per agent | [0.175, 0.058, 0.058, 0.060] |
| **diff / common 比** | **[3.0, 0.99, 0.98, 1.03]** |
| r_f_i unscaled per agent | [-8.0e-5, -8.2e-5, -2.1e-7, -8.1e-5] |
| **r_f total (PHI_F=100 scaled)** | **-0.0243** |

### [4] Sensitivity @ amp=+1.0 sys-pu

| 量 | 值 |
|---|---:|
| max\|Δf\|_1 (ES1) | **0.476 Hz** |
| pairwise_max overall | **0.477 Hz** |
| common_mode_max | 0.119 Hz |
| differential_max per agent | [0.357, 0.118, 0.118, 0.120] |
| diff / common 比 | [3.0, 0.99, 0.99, 1.01] |
| r_f total (PHI_F=100 scaled) | **-0.0936** (~4× 增长，与 amp²/0.5²=4 一致 ✅) |

线性度通过（amp 翻倍 → r_f 涨 4×，Δω² 关系），物理响应合理。

---

## 2. Root cause classification

按 spec 规则:
- 不能说 "strong synchronization" 除非 logger + routing 都验证 — 都验证了 ✅
- 不能说 "reward formula issue" 除非 raw differential 大但 r_f 仍 ≈ 0 — raw differential **大**且 r_f **不为零** (-0.024 / -0.094 scaled)

**Probe 算法分类: C-partial — physical differential exists AND r_f reflects it**

但 c-partial 的 label 已经否定了"物理强同步"假设。**raw 物理 IS desynchronized**:
- ES1 ω 摆 0.234-0.476 Hz
- ES2/3/4 ω 摆 0.001-0.009 Hz
- 这不是 "all 4 ESS synchronized to same ω"，而是 "ES1 alone moves, others stay near nominal"

差距 0.234 Hz vs 0.001 Hz = **234× 比值**。这是高度 desync，不是 sync。

那么"PHI sweep 显示 r_f% ≈ 0"的真因是什么？

---

## 3. 真因（probe 翻转的核心 finding）

回看 `probes/kundur/v3_dryrun/_phi_resweep.py` line 59:

```python
os.environ.setdefault("KUNDUR_DISTURBANCE_TYPE", "loadstep_paper_random_bus")
```

PHI sweep 在 **loadstep_paper_random_bus** 协议下跑！而 commit `97f6d3a` 已记录：

> "loadstep_paper_random_bus (R-mode): max\|df\| = 0.0091 Hz × 5 bit-identical, cum_unnorm = -0.0038. ... Series RLC R 块 Resistance 在 .slx 编译时冻结，运行时 workspace var 改不生效。"

即 PHI sweep 的 disturbance **完全没有真正触发**！系统只看到 IC kickoff 残留。max\|df\| ≈ 0.015 Hz 全部来自 IC noise，不是 Pm-step / LoadStep 真正应用。

在那个 weak-signal protocol 下：
- 4 ESS 在 IC 噪声里几乎共振（确实近似同步）
- (Δω_i - ω̄_i)² ≈ 0 不是因为强同步，而是因为**根本没扰动**
- r_f 量级 5e-5 per episode（每 step ~1e-6 ≈ 1e-3 Hz²）

而 root-cause probe 用 **pm_step_proxy single_vsg** 协议（Pm-step Constant→workspace 链真正可调）：
- ES1 真实摆 0.234-0.476 Hz
- ES2/3/4 几乎不动 → 强 desync
- r_f scaled = -0.024 to -0.094 per episode（**比 PHI sweep 报的 5e-5 大 500-2000×**）

---

## 4. 推算：用对的 disturbance protocol 时 PHI 到 r_f% 的映射

PHI sweep cell PHI=1e-4 (locked) 在 weak-signal 下报 r_f%=0.20%。
若改用 pm_step_proxy_random_bus（DIST_MAX=1.0 sys-pu），expected:

| 项 | 估算 |
|---|---:|
| typical \|r_f\| per ep (random magnitude in [0.1,1.0], peak ~ 0.234 / 0.5) | ~ 5e-4 (scaled by mean magnitude²) |
| r_f scaled by PHI_F=100 | ~ 0.05 |
| (ΔH_avg)² ≈ 300 (locked H₀=12 + ΔH range) | unchanged |
| r_h scaled (PHI_H=1e-4) | ~ 0.030 |
| r_d scaled (PHI_D=1e-4) | ~ 0.006 |

**r_f% = 0.05 / (0.05 + 0.030 + 0.006) ≈ 58%**

PHI=1e-3: r_h scaled ≈ 0.30 → r_f% ≈ 0.05/(0.05+0.30+0.06) ≈ 12%（**进入 3-8% 上限**）
PHI=1e-2: r_h scaled ≈ 3.0 → r_f% ≈ 1.4%
PHI=1e-1: r_h scaled ≈ 30 → r_f% ≈ 0.14%

**结论**: 在正确的 disturbance protocol 下，**locked PHI=1e-4 实际给 r_f% ≈ 58%**（远超 target band）；PHI=1e-3 给 ~12%。**target band [3, 8] 落在 PHI ∈ [3e-3, 5e-3] 附近**。

---

## 5. STOP — 翻转 PHI sweep verdict

之前的 phi_resweep_verdict.md 推断 "PHI 不是有效旋钮 / r_f 量级被架构限制" — **这个结论是基于 weak-signal disturbance protocol，不可信**。

**修正版结论**:

1. ✅ Logger identity 健康 (4 distinct IntW sources)
2. ✅ Disturbance routing clean
3. ✅ pm_step_proxy 协议下 ES1 真实摆动 0.234-0.476 Hz；ES2/3/4 几乎不动 → high desync
4. ✅ r_f 公式正确反映 desync（ES1 + 邻居 ES2/ES4 都贡献 -8e-5 量级，仅与 ES1 不连的 ES3 贡献 ~0）
5. ❌ phi_resweep 用了 loadstep_paper_random_bus（已文档化为 weak-signal）→ 整轮 sweep 数据**对 PHI 决策意义不可靠**

---

## 6. 推荐下一步

### 优先级 P0 — 重跑 PHI sweep 用对的 protocol

修改 `probes/kundur/v3_dryrun/_phi_resweep.py` line 59：
```python
os.environ.setdefault("KUNDUR_DISTURBANCE_TYPE", "pm_step_proxy_random_bus")
```

3 cells × 100 ep × 13s/ep ≈ 65 min。预期能找到 PHI ∈ [1e-3, 1e-2] 给 r_f% ∈ [3, 8]。

### 优先级 P1 — 用最优 PHI 训练 + 评估

最优 PHI 选好后用 train_simulink.py 跑 2000-ep baseline（替代当前 P0），然后 paper_eval 4-policy 对比 trained policy 是否真正学到 minimize r_f（不只是 minimize r_h）。

### 不需要

- ❌ 不动 reward formula（C-partial 证明 formula working as designed）
- ❌ 不动 v3 物理层（routing + logger 健康）
- ❌ 不重做 LoadStep architecture（pm_step_proxy 已经是 working protocol，论文对账已 documented deviation）

---

## 7. Artifacts

```
results/harness/kundur/cvs_v3_phi_root_cause/
  diagnostic_raw.json         ← 全量数据 (logger + 2 cells + classification)
  probe_stdout.log            ← console 完整输出
  phi_root_cause_verdict.md   ← 本文件
```

probe: `probes/kundur/v3_dryrun/_phi_root_cause.py` (192 lines, read-only via env instance + bridge.session.eval)

未触动: 物理层 / build / .slx / IC / runtime.mat / bridge code / config locked constants / reward formula / SAC / NE39 / training。env._disturbance_type 和 DISTURBANCE_VSG_INDICES 是 instance attribute 改写（仅本 probe 进程内有效，不影响其他 process / 不写盘）。

---

## STOP — 等用户裁决

**本次只 commit verdict + probe + diagnostic raw（read-only diagnostic + 文档），不动代码 / config / 物理层。**

下一步候选:
- (1) 接受这个翻转，进 P0 (重跑 PHI sweep with pm_step_proxy)
- (2) 推迟，把这次 finding 仅作 archival 记录，回到 P0 baseline trained policy 数据为准
- (3) 其他
