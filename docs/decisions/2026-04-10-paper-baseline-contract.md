# Paper Baseline Contract — Yang et al. TPWRS 2023

**Date:** 2026-04-10  
**Scope:** Defines the implementation choices that constitute "faithful reproduction"  
**Status:** Active — governs all Simulink and ANDES reward modifications

---

## Question 1 — Which backend is the primary target?

**Decision:** Simulink (Kundur + NE39) is the primary reproduction target.  
ANDES is the reference backend for sanity-checking reward behavior without MATLAB overhead.

**Rationale:** The paper's Fig. 4–13 training curves are generated from a time-domain
power system simulator, not a reduced ODE. Simulink is the closest available equivalent.

---

## Question 2 — Reward formula (paper vs engineering)

**Decision:** Implement paper's Eq. 14–18 strictly.

### r_f (Eq. 15–16) — Relative synchronization penalty

```
ω̄_i  = mean(Δω_i, Δω_{j∈N_i_active})          # local group average, Hz
r_f_i = -(Δω_i - ω̄_i)²
        - Σ_{j∈N_i} (Δω_j - ω̄_i)² · η_j       # η_j = comm success mask
```

**Why relative, not absolute:**  
The paper's core claim is oscillation suppression (inter-area sync), not frequency
restoration. The relative formula rewards agents for having *the same* frequency
deviation as their neighbors — even if all are off-nominal. This is intentional: UFLS
and governor response handle nominal restoration; the RL agent handles sync.

### r_h, r_d (Eq. 17–18) — Mean control effort penalty

```
ΔH̄   = mean_i(ΔH_i) = mean_i(delta_M_i / 2)   # mean inertia adjustment
ΔD̄   = mean_i(ΔD_i) = mean_i(delta_D_i)        # mean damping adjustment
r_h  = -(ΔH̄)²
r_d  = -(ΔD̄)²
```

**Why (mean(Δ))² not mean(Δ²):**  
The paper penalizes collective average effort, not the variance of individual actions.
`mean(Δ²) = mean(Δ)² + var(Δ)` — the old formula over-penalizes heterogeneous actions.

### Total per-agent reward

```
r_i = φ_f · r_f_i + φ_h · r_h + φ_d · r_d
    = φ_f · r_f_i - φ_h · (ΔH̄)² - φ_d · (ΔD̄)²
```

**Weights used:**
- Kundur: φ_f = 100, φ_h = 1, φ_d = 1  (unchanged)
- NE39:   φ_f = 200, φ_h = 1, φ_d = 1  (unchanged)

**What is NOT in this baseline:**  
The `PHI_ABS * (-Δω_i²)` absolute frequency penalty present in the ANDES backend
is an engineering addition beyond the paper. It is intentionally excluded from the
Simulink baseline. If ablation suggests it helps, it can be re-added as a labeled
extension with its own weight `φ_abs`.

---

## Question 3 — Buffer strategy

**Decision:** Accumulate buffer across episodes (do NOT clear per episode).

**Paper contradiction:** Algorithm 1 line 16 says "Clear buffer D_i", but Table I
specifies buffer_size=10000, batch_size=256, M=50 (steps/episode). Sampling 256
from 50 is mathematically impossible if the buffer is cleared each episode. The
pseudocode is inconsistent with the hyperparameter table. We treat the table as
authoritative.

**Engineering rationale:** Standard off-policy SAC is designed for experience reuse.
Clearing the buffer each episode converts SAC into an on-policy-style algorithm with
poor sample efficiency. This is an explicit deviation with documented justification.

**Buffer sizes in use:**
- Simulink Kundur: 100 000  (config_simulink.py; aligned with NE39)
- Simulink NE39:  100 000

**Minimum ablation commitment:** Before finalizing any paper results, run one
comparison: 2000-episode Kundur training with `CLEAR_BUFFER_PER_EPISODE=True`
vs `False`. Record both training curves.

---

## Question 4 — Parameter sharing vs independent agents

**Decision:** Keep current split:
- Simulink path: parameter-sharing SAC (`sac_agent_standalone.py`, CTDE paradigm)  
- ANDES/ODE path: independent per-agent SAC (`agents/ma_manager.py`)

**Note:** The paper describes independent agents. The Simulink path deviates.
This is flagged as a known gap; architectural unification is deferred until
reward alignment is validated.

---

## Modification log

| Date | File | Change |
|------|------|--------|
| 2026-04-10 | `kundur_simulink_env.py` | r_f: absolute → relative sync; r_h/r_d: mean(a²) → (mean(ΔH̄))² |
| 2026-04-10 | `ne39_simulink_env.py` | same as above |

---

## 2026-04-28 Credibility Close — HPO 前接口层锁定

**Scope:** Kundur Simulink 路径接口层 5 项裁决（不动物理层、bridge/helper、SAC、reward 公式结构、NE39）。
**Verdict:** `results/harness/kundur/cvs_v3_credibility_close/credibility_close_verdict.md`

### 裁决表

| # | 项 | 裁决 | 理由 |
|---|---|---|---|
| 1 | 动作范围 ΔM∈[-6,18]/ΔD∈[-1.5,4.5] | **保留** | Phase C 实证：paper-literal L3 范围 M=1 corner ROCOF=9.8 Hz/s 危险；当前 L0 范围全 corner 稳定，且 Phase D 已验证 18× tau 杠杆。Q7 量纲未解前不机械采纳论文字面值。详见 `docs/paper/action-range-mapping-deviation.md` |
| 2 | 奖励权重 PHI_H/PHI_D | **锁定 0.0001 + 删 env-var override** | env-var 是 sweep 用的，HPO 必须搜固定 reward。0.0001 由 Q7 量纲映射推出（ΔM 比论文 ΔH 小 33×，ΔM² 小 ~1100×）；ablation 改常量 |
| 3 | 训练扰动幅度 DIST_MAX | **0.5 → 1.0 sys-pu** | paper_eval no-control = -6.11 vs 论文 -15.20，gap 与扰动量级高度相关；DIST_MAX=0.5 可能显著 under-excite system，因此提升训练扰动上限到 1.0 sys-pu，并用 no-control paper_eval 复测校准。**不声称已完全证明 2.5× 缺口只由 DIST_MAX 解释。** |
| 4 | Buffer 不清空 | **保留** | off-policy SAC 标准做法；论文 Algorithm 1 与 Table I 内部矛盾（M=50 步 vs batch=256），项目以 Table I 为准。已在 §Q3 备案 |
| 5 | T_WARMUP=10s | **保留** + 注释升级 | post_task_mini 实证 t=10 s 残差 < 0.5 mHz；旧注释 "smoke-stage" 改为 "production locked" |

### 同步修改

- `scenarios/kundur/config_simulink.py`：
  - `DEFAULT_KUNDUR_MODEL_PROFILE` → `kundur_cvs_v3.json`（v2 5-bus 不再是 paper-aligned 默认）
  - `PHI_H = PHI_D = 0.0001`（删除 `KUNDUR_PHI_H` / `KUNDUR_PHI_D` env-var override）
  - `DIST_MAX = 1.0`（保留 `DIST_MIN = 0.1`）
  - `KUNDUR_DISTURBANCE_TYPE` 默认 `loadstep_paper_random_bus`（保留 env-var override）
  - `T_WARMUP = 10.0` 注释升级为 production locked
- `docs/paper/yang2023-fact-base.md` §10 表新增 5 行
- `scenarios/kundur/NOTES.md` 顶部加 credibility-close 标记
- `results/harness/kundur/cvs_v3_credibility_close/credibility_close_verdict.md` 新增/更新

### 未触动

物理层（拓扑/IC/.slx/runtime.mat/NR 脚本）、bridge/helper、SAC 架构、reward 公式结构、NE39 任何文件。

---

## 2026-04-29 Eval 协议偏差备案 — 方案 B

**Scope:** Kundur paper_eval 协议选择（不动物理层 / build / .slx / NE39 / SAC 架构）。
**完整 deviation：** `docs/paper/eval-disturbance-protocol-deviation.md`

### 上下文

paper_eval 默认协议从 commit `a9ad2ea` 锁定为 `loadstep_paper_random_bus`（训练）/ `pm_step_proxy_random_bus`（eval, paper_eval.py:488 setdefault）。后续 commit `32c7511` 让 paper_eval 真正受 `KUNDUR_DISTURBANCE_TYPE` env-var 控制；commit `4902caf` 在 env._reset_backend v3 路径恢复 LoadStep IC。

### 实测发现

5-scenario smoke (DIST=[0.1,1.0] sys-pu, M=24, D=4.5, zero-action)：

| 协议 | max\|Δf\| (5 scenarios) | cum_unnorm |
|---|---|---:|
| `pm_step_proxy_random_bus` (default) | [0.08, 0.41] Hz varied | -2.67 |
| `loadstep_paper_random_bus` (R-mode, pre-fix) | 0.0091 × 5 bit-identical | -0.0038 |
| `loadstep_paper_random_bus` (R-mode, post 4902caf) | 0.0091 × 5 bit-identical | -0.0038 |
| `loadstep_paper_trip_random_bus` (CCS-mode) | [0.0093, 0.0098] | -0.0041 |

LoadStep R-mode 与 CCS-mode 都不能产生有效扰动信号。R-mode 因 Series RLC R 块 Resistance 在 .slx 编译时冻结；CCS-mode 因 Bus 14/15 ESS 端电气距离离 load center 远（推测）。

### 裁决

**方案 B**：接受 `pm_step_proxy_random_bus` 为 v3 paper_eval 的 de facto 协议。

- 论文 cum_unnorm (-8.04 / -15.20) 不可直接对账（协议不同）
- trained vs no_control 在项目内部协议下比较仍有效（这是 RL 是否工作的内部判定）
- 未来若需论文真值对账：方案 A（重做物理层 LoadStep 块）或方案 B（重审 v3 拓扑），均破 credibility close 锁定

### 同步修改

- `docs/paper/eval-disturbance-protocol-deviation.md`（NEW，主备案）
- `docs/paper/yang2023-fact-base.md` §10 表新增一行
- `scenarios/kundur/NOTES.md` 顶部加 2026-04-29 段
- `docs/decisions/2026-04-10-paper-baseline-contract.md` 末尾追加（本段）

### 未触动

物理层、bridge / helper、SAC 架构、reward 公式结构、NE39、build / .slx / runtime.mat / IC。
