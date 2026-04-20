# Kundur ODE Gate Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 ODE 基线模型的三个物理错误，使闸门检查可以通过，进而解锁 RL 训练。

**Architecture:** 根因分析（55.md）发现原计划 Task 1+2 完成后仍有三个残余问题：LOAD_STEP_1 不平衡导致 CofI 永久漂移、B_tie=5 导致振荡频率只有 0.5 Hz、闸门第4项（settle_t）在物理上不可能满足（τ=160s）。修复这三个问题 + 完成原计划 Task 3/4。

**Tech Stack:** Python, NumPy, SciPy（FFT），`env/ode/power_system.py`，`config.py`

---

## 背景：已完成 vs 待完成

| 任务 | 状态 | 说明 |
|---|---|---|
| Task 1 — ω_s 因子 | ✅ 已完成 | `power_system.py` 已加 `self.omega_s = 2π×fn` |
| Task 2 — 物理参数 | ✅ 已完成 | H=80, D=1, DH/DD 范围已更新 |
| **Gate-Fix A — LOAD_STEP_1** | ✅ 已完成 | `[0,0,-2.48,0]` → `[2.48,0,-2.48,0]` |
| **Gate-Fix B — B_tie** | ✅ 已完成 | B_tie 5 → 20，ω_n≈1 Hz |
| **Gate-Fix C — 闸门第4项** | ✅ 已完成 | 去掉 settle_t 条件，3项闸门 |
| Task 3 — 观测归一化 | ⬜ 待完成 | `multi_vsg_env.py` omega_dot /10 |
| Task 4 — 绘图单位换算 | ⬜ 待完成 | `evaluate_ode.py` P→MW |
| 闸门验证 | ⬜ 待完成 | 运行 `scripts/check_ode_baseline.py` |
| RL 训练 | ⬜ 待完成 | 闸门通过后启动 |

---

## 根因速查

| 层次 | 问题 | 修法 |
|---|---|---|
| 1 | 闸门测的是频率调节，ODE 设计的是频率同步 | 去掉 settle_t，只测振荡特性 |
| 2 | LOAD_STEP_1 不平衡 → CofI 漂移 1.92 Hz/10s | 改为平衡扰动 [2.48,0,-2.48,0] |
| 3 | B_tie=5 → ω_n≈0.5 Hz（目标 1 Hz） | B_tie 改 20 → ω_n≈1 Hz |
| 4 | ω_s 修复正确，但 B_MATRIX 太小才是频率低的原因 | 已由层次3覆盖 |
| 5 | 计划预估"改前~0.3 Hz"，实际 0.09 Hz（3× 差距） | 不修，仅记录 |

---

## Task 3: multi_vsg_env.py — 观测归一化

**Files:**
- Modify: `env/ode/multi_vsg_env.py`（约第 202-219 行）

**背景：** 新参数下（H=80, ω_s=314）`omega_dot` 峰值约 ±6 rad/s²，原归一化 `/5.0` 截断严重，改 `/10.0`。

- [ ] **Step 1: 确认当前归一化位置**

```bash
grep -n "omega_dot" env/ode/multi_vsg_env.py
```

Expected: 找到 `/5.0` 的归一化行（自身和邻居各一处）。

- [ ] **Step 2: 修改 omega_dot 归一化**

在 `multi_vsg_env.py` 找到两处 `omega_dot` 归一化，把 `/5.0` 改为 `/10.0`：

```python
# 自身 omega_dot（示例行，以实际 grep 结果为准）
o[2] = state['omega_dot'][i] / 10.0    # 原: / 5.0

# 邻居 omega_dot
o[3 + cfg.MAX_NEIGHBORS + k] = state['omega_dot'][j] / 10.0  # 原: / 5.0
```

注意：`omega`（频率偏差）归一化 `/3.0` 不变。

- [ ] **Step 3: 快速验证不崩溃**

```bash
python -c "
import config as cfg, numpy as np
from env.ode.multi_vsg_env import MultiVSGEnv
env = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
obs = env.reset(delta_u=cfg.LOAD_STEP_1)
print('obs shape:', obs.shape, 'max:', np.abs(obs).max())
fixed = {i: np.zeros(cfg.ACTION_DIM, dtype=np.float32) for i in range(cfg.N_AGENTS)}
_, _, _, info = env.step(fixed)
print('step ok, time:', info['time'])
"
```

Expected: 无异常，obs max 在合理范围（< 5）。

- [ ] **Step 4: Commit**

```bash
git add env/ode/multi_vsg_env.py
git commit -m "fix(ode): omega_dot normalization /5->10 for H=80 params"
```

---

## Task 4: evaluate_ode.py — P_es 单位换算 MW

**Files:**
- Modify: `scenarios/kundur/evaluate_ode.py`

**背景：** `P_es` 是 p.u.，图纵轴应显示 MW（×100）。涉及 `plot_no_control`、`plot_rl_control`、`plot_fig13` 三个函数。

- [ ] **Step 1: 定位需改的绘图函数**

```bash
grep -n "P_es\|ylabel.*P_es\|S_BASE" scenarios/kundur/evaluate_ode.py
```

Expected: 找到 3 个函数中 `P_es` 绘图和 ylabel 行。

- [ ] **Step 2: 在每个绘图函数中换算**

在每处 `P_es` 绘图前加换算，并改 ylabel：

```python
# 旧（p.u.）:
ax.plot(t, traj['P_es'][:, i], ...)
ax.set_ylabel(r'(a) $\Delta\,P_{\mathrm{es}}$(p.u.)', ...)

# 新（MW）:
P_mw = traj['P_es'] * cfg.S_BASE   # p.u. → MW
ax.plot(t, P_mw[:, i], ...)
ax.set_ylabel(r'(a) $\Delta\,P_{\mathrm{es}}$(MW)', ...)
```

- [ ] **Step 3: 确认 cfg.S_BASE 已导入**

```bash
grep -n "import config\|import cfg\|S_BASE" scenarios/kundur/evaluate_ode.py | head -5
```

如未导入，在文件顶部加 `import config as cfg`。

- [ ] **Step 4: Commit**

```bash
git add scenarios/kundur/evaluate_ode.py
git commit -m "fix(ode): P_es unit conversion p.u.->MW in evaluate plots"
```

---

## Task 5: 运行闸门检查并验证

**Files:**
- Run: `scripts/check_ode_baseline.py`

- [ ] **Step 1: 运行闸门检查**

```bash
cd "C:\Users\27443\Desktop\Multi-Agent  VSGs"
python scripts/check_ode_baseline.py
```

Expected 输出：
```
主振荡频率: ~1.0 Hz  (目标 0.8~1.5)
Δf 峰值:   ~0.12 Hz  (目标 0.08~0.18)
ΔP_es 峰值: ~300-400 MW   (目标 200~500)

✅ 闸门通过，可进入 RL 训练
```

- [ ] **Step 2: 若振荡频率不在 [0.8, 1.5]**

检查 B_MATRIX 是否正确更新（B_tie=20）：
```bash
python -c "import config as cfg; print(cfg.B_MATRIX)"
```
期望: `[0,20,0,0],[20,0,20,0],[0,20,0,20],[0,0,20,0]`

- [ ] **Step 3: 若 Δf 峰值不在 [0.08, 0.18]**

检查 LOAD_STEP_1 是否平衡：
```bash
python -c "import config as cfg; print(cfg.LOAD_STEP_1)"
```
期望: `[2.48, 0. , -2.48, 0.]`

- [ ] **Step 4: 若 ΔP_es 峰值不在 [200, 500]**

检查 S_BASE = 100.0 且 B_MATRIX 已更新为 B_tie=20。  
若 ΔP_es 超过 500 MW，适当降低 LOAD_STEP 幅值（如改 1.5）。

- [ ] **Step 5: 闸门通过后 commit**

```bash
git add scripts/check_ode_baseline.py config.py
git commit -m "fix(ode): gate check pass — balanced LOAD_STEP, B_tie=20, 3-criterion gate"
```

---

## 预期结果对比

| 指标 | 修前（根因分析实测） | 修后预期 | 论文 Fig 6 |
|---|---|---|---|
| 主振荡频率 | 0.09 Hz (B_tie=5) → 0.5 Hz (B_tie=5+ω_s) | ~1.0 Hz (B_tie=20) | ~1 Hz |
| Δf 峰值 | ~1.92 Hz（CofI 漂移） | ~0.12 Hz（平衡扰动） | ~0.13 Hz |
| ΔP_es 峰值 | ~30 MW | ~300-400 MW | ~400 MW |
| settle_t | 永不收敛（τ=160s） | 不测（物理不可能） | N/A |

---

## 执行顺序

```
Task 3 → Task 4 → Task 5（闸门） → RL 训练
                      ↓ 失败
                   调参 → 重跑闸门
```
