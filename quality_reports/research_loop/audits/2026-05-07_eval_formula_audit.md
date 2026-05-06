# exp1 — Eval 公式 audit (range axis)

**Scope**: 静态对比 paper §IV-B/C 公式 vs `evaluation/paper_grade_axes.py`，定位 R05 全 0.037 之 range axis 失分根因。

---

## §1 paper §IV-B / §IV-C range 定义

`docs/paper/kd_4agent_paper_facts.md`：

- **§2.3 / §7 / 速查表**（Sec.IV-B 文字）:
  > "ΔH_{es,i} ∈ [-100, +300]，ΔD_{es,i} ∈ [-200, +600]"
- **Eq.12** 是 **action 约束（box bound）**，不是观测到的 span。
- **Eq.13** 增量语义：`H_{i,t} = H_{i,0} + ΔH_{i,t}` → **ΔH_{i,t} 即 agent 当前 step 输出**（不是从 t=0 累积）。
- **§8.4 文字**："$\Delta H_{avg}$、$\Delta D_{avg}$ 维持低水平（系统总惯量/阻尼储备基本不变）" → 论文 explicit 主张：训练好的 agent 让 ΔH 输出**贴近 0**（约束 2 = 守恒）。
- Fig.7 中 ΔH/ΔD 曲线在 [-100, +300] 之内但 **不要求 span ≈ 400**。

→ paper 350 / 700 **不是测得的 span，是 box 约束的宽度**。

---

## §2 axes.py 实现

文件：`evaluation/paper_grade_axes.py`

**Benchmark 表（line 47-61）**：
```
dH_range=(-100.0, 250.0)   # LS1（与 paper Sec.IV-B 文字 +300 也不一致，差 50）
dD_range=(-200.0, 500.0)   # LS1（与 paper +600 不一致，差 100）
```

**Range 计算（line 125-128, 148-149, 175-186）**：
```python
H_full = np.array([s["M_es"] for s in tr]) / 2.0
dH = H - H[0:1]                              # H(t) − H(0) 累积位移
proj_dH_min, proj_dH_max = _action_range(dH) # 4-agent 平均后的 min/max
proj_dH_span = proj_dH_max - proj_dH_min     # 当作"realized span"
paper_dH_span = paper.dH_range[1] - paper.dH_range[0]  # = 350（box 宽）
dH_ratio = proj_dH_span / paper_dH_span      # 期望 ≈ 1
score = max(0, 1 - |1 - ratio| / 0.5)
```

→ axes.py 把 paper 的 **action box 宽** 当成 **realized trajectory 的 (max-min) span benchmark**。

---

## §3 比对结论

**[X] 不一致 — 类型 = paper 公式 vs axes 算法 语义错位**

| 项 | paper Sec.IV-B Eq.12 | axes.py |
|---|---|---|
| 350 / 700 是什么 | action **bound 宽度**（允许范围）| 期望的 **realized (max-min) span** |
| 含义 | "ΔH 不能超出此盒"（硬约束）| "训练好的 agent 应该把 ΔH 走完此盒"（错误语义）|
| paper 自己说什么 | §8.4 "ΔH_avg 维持低水平" → 应**接近 0** | 反过来惩罚 ΔH span 不够大 |

**额外细节偏差**：

1. axes.py `dH_range=(-100, +250)` ≠ paper `(-100, +300)`，差 14% bound 宽。
2. M=2H 转换：trace `M_es` 是项目 `H_es,i,0 + ΔH_i,t`（实际 H 量），axes.py `/2.0` 把 H 当 M=2H 折算 → **proj 端额外缩 2×**（可能项目的 trace 已是 H，不需折算；需对照 `env/andes/andes_vsg_env.py::step()` 才能定）。
3. `_action_range` 先 `mean(axis=1)` 再 min/max：4 agent **正负相消** → 平均曲线 span 远小于任一单 agent span，更小于 4 agent ΔH 集合 span。

**R05 trace 实测**（`ddic_r05_baseline_paper_s42_load_step_1.json`，前 10 step）：
- `delta_M` 每 step 4 agent 范围 ≈ [-2.2, +4.3]，**单 agent 峰值 ≈ 4**
- 平均后 dH 曲线 span 估算 < 1（agent 间正负相消）
- vs axes.py paper_dH_span = 350 → ratio ≈ 0.003 → score = 0
- 这正是项目 6-axis 全 fail 的 **range axis** 数学源头

---

## §4 字符级 fallback

不适用（§3 已判定为公式-语义不一致）。

---

## §5 R07 决策

**Mismatch found** → R07 必修，不进 exp2。

**3 个独立 bug，按修复优先级**：

### Bug-A（核心，必修）：range axis 语义反了

axes.py 假设 "agent 应填满 [-100, +300] 的 box"，但 paper §8.4 + Eq.17 ($r^h = -(\overline{\Delta H})^2$) 主张 "ΔH avg 应**接近 0**"。

**修法 2 选 1**：

- **(A1) 删 range axis**：6-axis → 4-axis（max_df / final_df / settling / smoothness）。Range 已被 smoothness 间接覆盖 — smoothness 高 ⇒ ΔH 不大幅振荡 ⇒ avg 自然不远离 0。
- **(A2) 改语义为"upper-bound check"**：`score = 1 if proj_span ≤ paper_bound_width else 1 - (proj/bound − 1)/tol`。即"在 box 内"得满分，越界扣分。配合 Eq.17 守恒目标。

**推荐 A2**（保留 6-axis 完整性 + 对接 paper 守恒约束）。

### Bug-B：benchmark 数值与 paper 文字不一致

`dH_range=(-100, 250)` → 改 `(-100, 300)`；`dD_range=(-200, 500)` → 改 `(-200, 600)`。
LS2 同步核对（`dH_range=(-100, 200)` / `dD_range=(-200, 300)` 来自 visual extraction，非 paper 文字 — 标注 visual 出处或对齐 LS1 box）。

### Bug-C：M=2H 折算可疑

确认 `env/andes/andes_vsg_env.py` step() 写 `M_es` 时是写 H 还是 2H。若是 H → 删 axes.py line 138 `/2.0`。

### R07 验证步骤

1. 实施 A2 + Bug-B fix（≤ 20 行改动）。
2. 不重训，直接重跑 `paper_grade_axes.py results/research_loop/eval_r05/`。
3. 期望：R05 8 ckpt overall 不再被 range axis 钉死在 0.037；其他 5 axis 真实成绩浮出。
4. 若浮出后仍 < 0.5 → range 不是唯一 bug，进 exp2 (action 语义 / scenario calibration)。
5. 若浮出 ≥ 0.5 → R07 = pure eval-side 修复，无需重训。

---

**字数**：约 580 字（不含代码块）。
