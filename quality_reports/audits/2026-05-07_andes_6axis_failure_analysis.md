# Audit: ANDES 论文复现 6-Axis 失败原因分析

**Status**: FINAL
**Date**: 2026-05-07
**Triggered by**: 6-axis evaluator (`evaluation/paper_grade_axes.py`) 推翻 2026-05-06 cum_rf 单维 verdict
**Data**: `results/andes_paper_alignment_6axis_2026-05-07.json`
**Sources**:
  - 论文图视觉: `C:\Users\27443\Desktop\一切\论文\Figure.paper\{6,7,8,9}.png`
  - 项目实测: `results/andes_eval_paper_specific_v2_envV2_hetero/`
  - 论文事实: `docs/paper/kd_4agent_paper_facts.md`

---

## §1 失败定义

**6-axis paper-alignment 评估**：
- 论文 = 1.0 (Fig.6/7/8/9 视觉提取的 6 个动态指标 benchmark)
- 项目 21 个 ckpt overall score 0.033-0.036 / 1.0
- DDIC vs no-control: 0.034 vs 0.010 (ranking 一致, 量级失真)

**失败程度**: 5/6 axis 全部得 0 分, 仅 smoothness 偶尔 0.7-0.9.

| Axis | 论文 LS1 | 项目 LS1 best | 倍数差 | Score |
|---|---|---|---|---|
| max \|Δf\| | 0.13 Hz | 0.41 Hz | 3.2× | 0 |
| final \|Δf\|@6s | 0.08 Hz | 0.18 Hz | 2.3× | 0 |
| settling_s | 3 s | ∞ (10s 不收敛) | 质性失败 | 0 |
| ΔH range (DDIC) | 350 | 5 | 70× 偏小 | 0 |
| ΔD range (DDIC) | 700 | 15 | 47× 偏小 | 0 |
| ΔH/ΔD smoothness | std~0 | std 2-22 | — | 0.5-0.9 |

---

## §2 失败原因分类 (按 axis)

### F1. ΔH/ΔD range 70×/47× 偏小 — **最严重**

**症状**: agent 实际只用 ~5 (LS1 ΔH) / ~15 (LS1 ΔD) 的范围, 论文 350/700.

**根因**: H₀ baseline 选择限制了允许的 Δ 范围.

| 维度 | 项目 | 论文 (推断) |
|---|---|---|
| H₀ | 10 s (V1) / 15 s (V2) | 未明示 (Q-D), 但 ΔH=[-100, 300] 暗示 H₀ ≥ 100 |
| ΔH 设定范围 | [-12, 40] (V2) / [-10, 30] (V1) | [-100, 300] (paper-literal) |
| ΔH 实际用范围 | ~5 | ~350 |

H₀=10 时若直接用论文 ΔH=-100 → H_target=-90 物理不可行. Phase C 验证 87% floor-clip → SAC
不能学.

**为什么 actor 还压缩到 5**: 实际配置 ΔH=[-12, 40] 但 actor 输出大部分时间在 [-1, 1]
(tanh squashing) → effective range ~5.

**修法**: 三选一
- a) **重选 H₀=100** → ΔH 设定 [-100, 300] 物理可行, 但偏离 Kundur [49] 经典惯量基值
- b) **保持 H₀=10**, 论文范围按比例缩到 [-10, 30] (项目当前) → 永远不可能匹配 350 range
- c) **训练时强制 actor 探索全部范围** (entropy regularization) → 仅微调

**ROI**: 高 (a 选项一次性解决 ΔH/ΔD 两个 axis)
**成本**: 高 (重训, 可能破坏 V1 已训 model 的 ranking)

### F2. max\|Δf\| 3-4× 偏大 — 系统欠阻尼

**症状**: 项目 max\|Δf\| 0.41 Hz (LS1 best) vs 论文 0.13 Hz.

**根因**: 系统总阻尼不足. 4 主要来源:

1. **GENROU D=0**: ANDES `kundur_full.xlsx` 的 4 同步发电机 D=0 (实测验证).
   - 论文用经典 Kundur [49] 但是否启 governor 未明示
   - 项目无 governor → 大扰动后 SG 没有调速反馈 → 频率偏差大
2. **GENCLS-only ESS**: 4 ESS 用 GENCLS (经典摆动), 没有 inner-loop / power electronics damping
   - 论文 §II-A 自己声明"忽略 inner loop"
   - 但论文系统可能含外部 governor / AVR 提供整体阻尼
3. **ESS 容量相对扰动幅值大**: LS1=2.48 pu (248 MW) vs 4 ESS 总 800 MVA = 31% 比例
4. **ΔH/ΔD agent 调节力不足** (见 F1): agent 最多调 ±5/±15, 顶不住大扰动

**修法**:
- 启 ANDES IEEEG1 governor + EXST1 AVR (改善 1, 2)
- 增 VSG_SN 减相对扰动幅值 (改善 3, 但偏离 baseline)
- 修 F1 提供更大 agent 调节力 (改善 4)

**ROI**: 高 (启 governor 同时改善 max_df / final_df / settling 三个 axis)
**成本**: 中 (论文 §II-A "ignore inner loop" scope 是否覆盖 governor 论文未明)

### F3. final\|Δf\|@6s 2.5× 偏大 — 不收敛

**症状**: 项目 t=6s 时仍 0.18 Hz, 论文 0.08 Hz residual. 项目 t=10s 仍 0.16-0.21 Hz.

**根因**: F2 系统欠阻尼 + load step 永久偏置导致频率永久偏差.

**关键认知修正**: 论文 final Δf @ 6s **不是 0** 而是 0.08 Hz (load step residual). 我之前估值
0.02 Hz **错了** — 论文系统在 6s 时已 settle 到稳态偏差 0.08 Hz, 项目在 10s 时仍 0.18 Hz
oscillating.

**修法**: 同 F2 启 governor.

### F4. settling_s = ∞ — 10s 内不收敛

**症状**: 项目所有 ckpt 的 max\|Δf\| 在 10s 内**永远** > 0.05 Hz, 论文 ~3s 内进入 ±0.02 Hz of
residual.

**根因**: F2 + F3 + actor 输出 stochastic 让 H/D step-to-step 跳跃 → 系统持续被 perturb →
永远不 settle.

**修法**: F2 (governor) + F5 (action smoothing) 双管齐下.

### F5. ΔH/ΔD smoothness — actor 输出锯齿

**症状**: 项目最佳 ckpt (`balanced_seed46_best`) ΔH avg curve std=2.34 / step (LS1),
`phase3v2_seed44` ΔD std=22.28. 论文 ΔH/ΔD avg curve **平滑收敛**到稳态.

**根因**: SAC actor 输出是 stochastic Gaussian, 每 step 重采样 → step-to-step jump 随机性大
→ ΔH/ΔD 在 [10, 35] 之间高频锯齿.

**修法**:
- **deterministic eval** — 用 actor.deterministic 而非 sample (项目当前 `_make_ddic_controller`
  已用 `actor.deterministic`, 但 std 仍大说明 actor 学到的 mean 本身就不稳)
- **action-smoothing reward penalty** — 训练 reward 加 \|a_t - a_{t-1}\|² 项, 鼓励 smooth control
- **temporal regularization** — 训练时把 obs 加上 last action (项目 `INCLUDE_OWN_ACTION_OBS=False`
  当前)

**ROI**: 中 (smoothness 是唯一项目内可改 axis, 不离开论文 scope)
**成本**: 低 (改 reward + 重训, 不需 env 物理改动)

### F6. cum_rf "假阳性"

**症状**: 旧 verdict 用 cum_rf 单维, phase3v2_seed44 LS1 -0.722 vs paper -0.68 = 6.2% diff
"paper-grade".

**根因**: cum_rf = Σ_t Σ_i (f_i - f̄)² 是 **sync 偏差积分**, 对 step-jitter 不敏感:
- 4 节点频率高频锯齿 → 节点间相对偏差小 → cum_rf 小
- agent 用 stochastic action 让 H/D 乱跳 → 增加 sync 但不影响 cum_rf
- 结果: cum_rf 反映"4 节点 sync 度", **不反映"agent 在做正确控制"**

**修法**: 已落 — 改用 6-axis 几何均值.

**教训**: 单维 metric 永远不够, 必须 holistic.

---

## §3 失败的二级原因 (元方法)

### M1. 评判 metric 选错

**问题**: 旧评判用 cum_rf 一个维度, geometric mean 没 enforced.

**机制**: 任何单维 metric 都可能被 cherry-pick: 项目能在该维度上"凑", 但其他物理维度 fail.

**修复**: 6-axis 几何均值, 任一项 0 → 总分 0.

### M2. 论文图视觉特征量化滞后

**问题**: 之前 4 轮分析都用粗估值 (max_df 0.12 / final_df 0.02 / settling 3s), 没逐张图量化.

**机制**: 看图说"差不多", 但实际**论文 final_df=0.08 Hz residual** (load step 永久偏置), 不是
0.02. 评判标准本身错了.

**修复**: 2026-05-07 重读 Fig.6/7/8/9 提取真实数值, 落到 `evaluation/paper_grade_axes.py::PAPER`
benchmark.

### M3. 训练失败被 cum_rf 掩盖

**问题**: 训练完看 cum_rf "9.4% diff" 就 declare 成功, 没看 ΔH/ΔD 时序图.

**机制**: cum_rf 不区分"agent 学到 smooth control 让节点同步" vs "agent 用 stochastic action
让 sync 量级偶然匹配".

**修复**: 训练完后必须看 fig7/9 ΔH/ΔD curve, 非平滑直接拒收.

---

## §4 哪些做对了

避免方向归零:
- ✅ Reward 公式实现 (Eq.15-18) 与论文等价
- ✅ MDP / SAC / Algorithm 1 实现 (Eq.11-23 + 训练循环)
- ✅ 修改 Kundur 拓扑 (4 ESS @ 12/14/15/16 + W1/W2 + G4→W1)
- ✅ dt=0.2s / M=50 / episode=10s (2026-05-05 dt fix)
- ✅ DDIC > Adaptive > NoCtrl ranking (n=5 seed 验证)
- ✅ 6-axis 评估流程落代码 (`evaluation/paper_grade_axes.py`)

机制层面正确, **物理量级**全部 fail. 这是 ANDES + GENCLS-only + Kundur full GENROU D=0 的天花板.

---

## §5 失败 root cause 树

```
6-axis 全 fail (overall 0.036)
├── F1. ΔH/ΔD range 70×/47× 偏小
│   └── H₀=10 选择 (Kundur [49] 经典) → ΔH paper-literal 物理不可行
│       └── 论文 H₀ 未明示 (Q-D)
│       └── Phase C floor 验证 paper-literal 87% clip
│
├── F2/F3/F4. max_df / final_df / settling 全失败
│   ├── ANDES kundur_full GENROU D=0 (无 governor)
│   ├── GENCLS-only ESS (无 inner-loop damping)
│   ├── 扰动相对幅值 31%
│   └── F1 让 agent 调节力不足
│
└── F5. ΔH/ΔD smoothness fail
    ├── SAC stochastic actor (deterministic eval 也学到不稳 mean)
    ├── reward 无 action-smoothing penalty
    └── obs 不含 last action

二级:
├── M1. cum_rf 单维 cherry-pick
├── M2. 论文 benchmark 之前用估值, 不准
└── M3. 训练完没看时序图, 只看积分量
```

---

## §6 与论文 scope 的边界

论文 §II-A 明说: *"this paper mainly studies the relatively slow dynamics of the
electromechanical transient. Therefore, the dynamics of the inner loop can be neglected
referring to [42]."*

**含糊地带**:
- governor (IEEEG1) 是否在 "inner loop" 范围内? 论文未明.
- 项目当前忽略 governor → 系统 D=0, 物理动态无法匹配论文图.
- 启 governor 是项目偏离, 但**论文系统隐含含 governor** (Kundur [49] 经典 Power System
  Stability and Control 默认 4 SG 配 governor + AVR).

**结论**: 项目走"严格 §II-A literal" 路线 → 物理失配; 走"启 governor 让物理对齐" 路线 → 偏离
§II-A literal 但贴近论文实际系统. 选 b 路是必要 deviation, 应在 paper writing 中显式声明.

---

## §7 References

- 6-axis evaluator: `evaluation/paper_grade_axes.py`
- 完整数据: `results/andes_paper_alignment_6axis_2026-05-07.json`
- 真实状态: `docs/paper/andes_replication_status_2026-05-07_6axis.md`
- 论文 Q-D / Q-H: `docs/paper/kd_4agent_paper_facts.md` §13
- Recovery plan: `quality_reports/plans/2026-05-07_andes_6axis_recovery.md`
