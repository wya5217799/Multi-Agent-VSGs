# exp2 — Action 物理语义 audit (2026-05-07)

## §1 Paper action 语义 (§II-B + Eq.12-13)

Paper Eq.1 swing: $H_{es,i}\Delta\dot\omega_i + D_{es,i}\Delta\omega_i = \Delta u_i - \Delta P_{es,i}$

Action (Eq.12-13, Sec.III-A): $a_{i,t} = (\Delta H_{es,i,t}, \Delta D_{es,i,t})$, **直接更新 swing 系数本身**:
$$H_{es,i,t} = H_{es,i,0} + \Delta H_{es,i,t}, \quad D_{es,i,t} = D_{es,i,0} + \Delta D_{es,i,t}$$

KD 实验 (Sec.IV-B): $\Delta H \in [-100, +300]$, $\Delta D \in [-200, +600]$, baseline $H_{es,0}, D_{es,0}$ **未给** (Q-D).

**核心**: paper 把 ESS 抽象为 "virtual inertia / damping 常数" — agent action **直调 swing 方程的 H/D 系数**, 不是 ESS P 注入. ESS 的 P 注入 ($\Delta P_{es,i}$) 是 swing 方程**右侧的状态变量**, 由摆动动力学+网络 Laplacian (Eq.2-4) 自洽求解, **不是 SAC 控制对象**. Sec.II-A 明确 "the dynamics of the inner loop can be neglected" — paper 不建 PWM/电流环, $\Delta P_{es}$ 是机电暂态尺度上由 (H, D, $\Delta\omega$, $\Delta u$) 决定的因变量.

→ Paper action 语义 = **(A) H/D 系数直调** (control-派集总形式).

## §2 Project action 实现 (`env/andes/base_env.py::step`)

LOC 268-289:
```python
delta_M[i] = a[0] * self.DM_MAX if a[0] >= 0 else a[0] * (-self.DM_MIN)
delta_D[i] = a[1] * self.DD_MAX if a[1] >= 0 else a[1] * (-self.DD_MIN)
M_new[i] = max(self.M0[i] + delta_M[i], 0.2)
...
self.ss.GENCLS.set("M", self.vsg_idx[i], M_interp, attr='v')
self.ss.GENCLS.set("D", self.vsg_idx[i], D_interp, attr='v')
```

Project action → 直写 ANDES `GENCLS.M` / `GENCLS.D` (M = 2H 经典模型系数). **无任何 P 注入** (`PV.set("p0", ...)` 仅 reset 时扰动用; `PMG_STEP_AMP` 不存在).

→ Project action 语义 = **(A) GENCLS.M/D 直调** (M = 2H, ΔH = ΔM/2).

## §3 比对结论

- [x] **paper H/D 直调 vs project M/D 直调 → 一致** (M = 2H 是 ANDES GENCLS 的二阶量纲转换, 物理等价)
- [ ] paper P 注入 vs project P 注入 — 不适用 (paper 不是 P 注入)
- [ ] paper P 注入 vs project M 直调 — **suspect 错** (paper 也直调系数)

**关键证据**:
1. Paper Eq.1 swing 把 H, D 当**集总系数** (Sec.II-A "control-派" 形式, §1.1), 不是积分时变量
2. Paper Eq.13 显式写 $H_{i,t} = H_{i,0} + \Delta H_{i,t}$ — 直接系数加法
3. Paper Sec.II-A 引用 [42] 把内环/PWM 压扁 → ESS 的 $\Delta P_{es}$ 不是 SAC 控制量, 是 swing 状态变量
4. Project `delta_M/2 = delta_H` 对账 (base_env.py:490 `ah_avg = mean(delta_M)/2`), 量纲一致

→ **量级 gap 不是物理语义不一致**, 是同一类 actuation 下:
- Paper $\Delta H \in [-100, +300]$ (range 400), baseline 未知 (大概率 SI 100s 级)
- Project DM_MIN/DM_MAX = [-10, +30] → ΔH = [-5, +15] (range 20), VSG_M0=20 (H0=10s)

**Project ΔH range 比 paper 小 20×** — 这才是 R05 "项目 ΔH range 70× 偏小" 的真实成因 (项目环境硬限 + paper baseline 未知导致绝对值不可比, 但 range 比例可比).

## §4 R07 工作量

**不需要 rewrite env step()** (语义已正确). 唯一物理 mismatch 是 action **数值范围** 受限:

| 修改项 | LOC | 工作量 |
|---|---|---|
| `base_env.py` DM_MIN/DM_MAX, DD_MIN/DD_MAX 扩到 paper 比例 (range 400/800 vs paper baseline 假设) | 4 LOC (52-59) | trivial |
| `_compute_rewards` ΔH/ΔD 量纲不变 (Eq.17-18 已是 ΔM/2 = ΔH, 一致) | 0 | — |
| Obs vector (`_build_obs`) 不依赖 M_es/D_es | 0 | — |
| `M_new = max(M0 + delta_M, 0.2)` 下界 clamp | 留意是否在新 range 触发 | trivial |
| Substep 插值/TDS 稳定性 — 大 ΔM (e.g. M ∈ [0.2, 200]) 可能触发 ANDES 发散, **N_SUBSTEPS=5 可能不够** | 视测试 | low-mid |

**工作量: low** (半天). 主要风险在 ANDES TDS 稳定性 (大幅参数突变), 不在 env 重写.

## §5 R07 决策

**不要 rewrite env 为 P 注入**. Paper 也是 H/D 系数直调, project 语义已正确.

**R07 真实动作**: 把 action range bug 当 hyperparam 扩展处理, 进 exp1 audit 路线:

1. **R07 候选 arm**: 解锁 `DM_MAX/DD_MAX` 到 paper-scale (e.g. DM_MAX=300, DD_MAX=600 假设 baseline H0=10 一致), 对比 ΔH/ΔD range 是否能逼近 paper 350/1000
2. **预期 effect**: 量级直接打开, 但 reward function ($r_h, r_d$ 二次惩罚) 会 dominate; 必须同步降低 $\varphi_h, \varphi_d$ 或归一化 ΔH/ΔD (R05 P0 saturation 已发现)
3. **TDS 稳定性 gate**: 跑 1 short trial 验证 N_SUBSTEPS=5 在 DM_MAX=300 下不发散
4. **不重写 env**, 仅改常量 + 训练 hyperparam

R05 verdict 中 "(c) 累积 ΔH/ΔD range 偏小" 仍 valid, 但归因从 "物理语义不可比" 修正为 "action range 硬限 + 奖励权重不平衡". exp1 audit 路线继续走.

---
**~520 字, 给 R07 明确动作.**
