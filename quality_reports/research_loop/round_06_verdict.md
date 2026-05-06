# R06 Verdict — 物理对齐 Audit (找到 eval critical bug)

**Status**: DONE (exp0+exp1+exp2+exp3 全完, **exp4 daemon 自跑了 5 ckpt, 没浪费**)
**Wall**: ~30 min (exp0 主上下文 10 min + exp1/2/3 三 agent fork 并行 ~3 min × 3 = 9 min + verdict 写 10 min)
**exp4 update**: R06 plan v2 标 exp4 由 exp0 gate kill, 但 daemon 在 background 跑完了 5 v1_5seed 200ep ckpt (exit=0, axes 未算). R07 修 axes.py 后顺手重 eval 这 5 个 → 多 5 个 P phase 数据点 (V1 长训对照).
**Trigger**: R05 verdict — 8 hyperparam 全 6-axis=0.037 attractor; R06 plan v2 audit-first pivot

---

## §1 实测 (4 audit 结果)

### exp0: attractor 性质诊断 (主上下文)
**verdict**: **(c) action 累积 range starvation**, 不是 (a) 真 attractor 也不是 (b) agents 不动

| 信号 | 项目 | paper | gap |
|---|---|---|---|
| 单 step \|ΔM\|max | 3-8.5 | — | act 中, 非 0 |
| 累积 ΔM range | 0.6-3.1 | 350 | 100-500× 偏小 |
| 累积 ΔD range | 0.7-6.3 | 700 | 100-1000× 偏小 |

详见 `audits/2026-05-07_attractor_nature.md`.

### exp1: eval 公式 audit (agent fork) — ⭐ critical bug found
**verdict**: **mismatch found**, 3 bug:

- **Bug-A (核心)**: `evaluation/paper_grade_axes.py` range axis 公式语义反了. axes.py 把 paper Sec.IV-B Eq.12 的 **action box bound 宽度** (`-100→+300`, 即 400) 当 **realized trajectory (max-min) span 期望值**, 反向惩罚 agent ΔH span 不够大. 但 paper §8.4 + Eq.17 (`r^h = -(ΔH_avg)^2`) 主张 ΔH avg **接近 0** (守恒约束).
- **Bug-B**: axes.py 写 `(-100, 250)` vs paper 文字 `(-100, +300)`; D 同理 (`500` vs `600`)
- **Bug-C**: line 138 `M=2H/2.0` 折算可疑

**R05 trace 验算** (agent 给的): `delta_M` 单 step 单 agent 峰值 ≈ 4.3, 4 agent mean 后正负相消 span < 1, 除以 paper 350 → ratio ≈ 0.003 → score = 0. **数学吻合 6-axis 全 0.037** (range axis floor + 几何均值 floor 复现实测 0.033-0.036).

→ R07 推荐: **方案 A2 改成 box 内满分, 越界扣分** (20 LOC), 重跑 `paper_grade_axes.py results/research_loop/eval_r05/`. 期望破 0.037.

详见 `audits/2026-05-07_eval_formula_audit.md`.

### exp2: action 语义 audit (agent fork) — 推翻 P 注入嫌疑
**verdict**: **paper M/D 直调 = project M/D 直调**, 数学等价**无 mismatch**

- paper Eq.1 swing 集总形式 (`H·dω + D·ω = Δu - ΔP`); Sec.II-A §1.1.1 显式忽略内环/PWM
- paper Eq.13 显式 `H_{i,t} = H_{i,0} + ΔH_{i,t}` — agent 直接更新系数
- project `base_env.py:288-289` `ss.GENCLS.set("M", ...)` 调 GENCLS M=2H 系数, ΔH = ΔM/2

**量级 gap 真因修正**:
- project `DM_MIN/DM_MAX = [-10, +30]` → ΔH range 20
- paper `[-100, +300]` → range 400
- **单步 20× 偏小**, 不是 100-1000×; R05 verdict 写的 100-1000× 混淆了 "单步 box width" vs "50-step 累积 saturation 后 trajectory span"

→ R07: **不要 rewrite env**. 副线候选: 扩 DM_MAX 30→300, 同步降 φ_h/φ_d 或归一化 ΔH/ΔD. 工作量 **low** (半天, 4 LOC + reward 平衡).

详见 `audits/2026-05-07_action_semantics_audit.md`.

### exp3: disturbance audit (agent fork) — 已对齐
**verdict**: paper §8.4 LS1 = **-2.48 sys_pu** @ Bus14, LS2 = **+1.88 sys_pu** @ Bus15. eval driver `eval_paper_spec_v2.py:40-43` 字面对齐.

⚠ **重大事实修正** (我之前 MEMORY 错): 老 feedback memo 写 `PAPER_LS_MAGNITUDE_SYS_PU = {14: 1.53, 15: 0.90}` 是 Simulink-discrete repo 的 calibrated 值. **ANDES paper 真值是 -2.48 / +1.88**.

train env uniform [0.5, 2.0] vs paper "50 不同 LS" — paper 未给训练 distribution, 不阻塞. R05 disturb_5x ([2.5, 10]) 6-axis 仍 0.037 进一步证伪 disturbance magnitude 是 root.

→ R07: **exp3 关闭, 不修**.

详见 `audits/2026-05-07_paper_disturbance_audit.md`.

---

## §2 6-axis paper alignment

R06 不重 eval (audit-only), 6-axis 数仍 R05 的 0.037 attractor.

**R07 修 axes.py 后期望**: range axis 从 0 跳到 ~0.7-1.0 (box 内 ΔH avg ≈ 0 满分), 几何均值
overall 从 0.037 跳到 ~0.3-0.5 (其他 4 axis 仍 0, 但 weighted 算法不同 floor 复活).

---

## §3 视觉对比

R06 0 train, 不生 fig. R07 修 axes.py + 重 eval R05 baseline_paper ckpt 后跟 paper Fig.7/9 对比, 看 ΔH/ΔD 是否物理上合理 (即使 axis 算法修了).

---

## §4 Hyperparam vs paper Table I

R06 audit 不动 hyperparam. R07 副线候选若启 → DM_MAX 30→300 + φ_h/φ_d 重平衡, 全部对齐 paper Table I.

---

## §5 信号 / wall ratio

| Round | wall | 信号 | ratio |
|---|---|---|---|
| R01-R04 | 120 min | 1 falsification (PHI_D 修对) | 1/120 |
| R05 | 20 min | 8 falsifications (hyperparam not root) | 8/20 |
| **R06** | **30 min** | **3 信号** (action range starvation 真因 + axes.py bug-A 找到 + P 注入嫌疑推翻) | **3/30 = 高** |

R06 audit 路径符合 user 工作流"思考方向"判断: 不机械 check, 找到 critical bug.

---

## §6 R07 衔接

**Phase E (audit-driven, 0 train)** 主路径:

1. 修 `evaluation/paper_grade_axes.py` Bug-A (range axis 改 box 内满分)
2. 顺手修 Bug-B (`(-100,250)` → `(-100,+300)`, D 同理)
3. (待定) Bug-C 折算检查 — 跟 base_env.py M_es 累积语义对比
4. 重跑 `python evaluation/paper_grade_axes.py results/research_loop/eval_r05/`
5. **同时重 eval R06 v1_5seed 200ep ckpt × 5 seed** (daemon 已跑 train, 缺 axes, 顺手补) → P phase 5seed mean±std 数据点
6. 看 R05 8 ckpt + R06 5 ckpt 6-axis 是否破 0.037

**预期信号**: range axis 0→0.7+, overall 0.037 → 0.3+ (即使 max_df/settling 仍 0)

**分支决策**:
- overall ≥ 0.5 → R08 = pure eval fix, 不重训, 直接生 fig 对比 paper
- 0.1 ≤ overall < 0.5 → R08 = 副线 DM_MAX 30→300 重训 R05 baseline 50ep × 1 seed, 看 max_df/settling/range 是否同时改善
- overall < 0.1 → 真 attractor (a) 复活, R08 = SAC entropy / reward shape sweep (但 exp1 bug 数学说不会到这)

**预估 wall**: R07 ~20 min (修 axes.py + 重 eval, 0 train).

---

## §7 关键 lesson (锁进 SKILL.md 候选)

1. **eval bug 比训练 bug 隐蔽**: R01-R05 ~120 min 烧 GPU 找 hyperparam, 实际 root 在 axes.py 公式语义错位. 任何 attractor / 平台 reach 不到 paper 的 case, **eval 公式 audit 应该是 R0 必跑**, 不是 R5 才想到
2. **agent fork 并行 audit 极度高效**: 3 audit serial 主上下文要 ~80 min, 并行 fork ~3 min × 3 + verdict 整合 10 min = 19 min, **4× 快**
3. **MEMORY 跨 repo 串风险**: ANDES vs Simulink-discrete 共享 user feedback memo, 但 constant 名/值不同 (PAPER_LS_MAGNITUDE 案例). audit 文档前必先 grep 验证 constant 在当前 repo 存在
4. **修正 R05 量级表述**: R05 verdict 写 "100-1000× 偏小" 混淆"单步 box width 20×"和"50-step 累积 saturation 后 100×". exp2 agent 给了精确分清

---

*Generated by main agent integrating exp0 (main) + exp1/exp2/exp3 (3 agent fork), 2026-05-07*
