# 物理环境最小验证计划

**目的**: 在继续任何 SAC 训练之前，验证 ANDES 物理环境是否能在原理上产生论文级别的频率响应。  
**预计耗时**: 1-2 小时（无训练，全是短仿真）  
**背景**: R01-R06 共 3 小时 GPU 训练，但从未验证"ANDES 能不能物理上达到 max_df=0.13 Hz"。R04 发现 adaptive controller = no_control (6-axis 同为 0.010)，这是环境物理不响应 H/D 调节的强信号。

---

## 实验 V1：静态 H 扫描（最关键）

**目标**: 确认在 ANDES 里，增大 H 是否单调降低 max_df。

**方法**:
- 不训练，不用 SAC
- 把 4 个 ESS 的 H 固定到不同值（不控制，保持静态）
- 跑 LS1 扰动（Bus14 -2.48 sys_pu，paper 标准）
- 记录 max|Δf| 和 settling

| 实验 | H_all (s) | 预期 max_df | 实测 max_df | 结论 |
|---|---|---|---|---|
| V1-a | 10 (当前 baseline) | — | ? | baseline |
| V1-b | 30 | 应低于 V1-a | ? | 验证单调性 |
| V1-c | 100 | 应明显降低 | ? | 中量级 |
| V1-d | 300 (paper scale) | 接近 0.13? | ? | paper 量级 |

**判定**:
- ✅ V1-d max_df ≤ 0.20 Hz → ANDES 物理可行，问题在 SAC 没学到大 H
- ❌ V1-d max_df 仍 > 0.40 Hz → 无 governor 是天花板，必须先加 governor 再训练

---

## 实验 V2：Governor on/off 对比

**目标**: 确认 IEEEG1 governor 是否是降低 max_df 的必要条件。

**方法**:
- 用 H=10（当前 baseline），不改 SAC
- 两组：无 governor（当前）vs 挂 IEEEG1+EXST1（V3 env，smoke 已 PASS）
- 跑 LS1，记录 max|Δf|、settling

| 实验 | Governor | H | max_df | settling |
|---|---|---|---|---|
| V2-a | 无（当前） | 10 | ? | ∞? |
| V2-b | IEEEG1+EXST1 | 10 | ? | ? |

**判定**:
- V2-b max_df 比 V2-a 降 ≥ 50% → governor 是必要条件，Phase B 优先级最高
- V2-b 无改善 → governor 不够，可能还需要 H₀ 量级修正

---

## 实验 V3：最优组合上限测试

**目标**: 找出 ANDES 在最理想配置下能达到的物理上限。

**方法**:
- H=300 + governor on + LS1
- 这是"如果 SAC 训练完美"的上界

| 实验 | H | Governor | max_df | settling | 可否达论文? |
|---|---|---|---|---|---|
| V3 | 300 | on | ? | ? | ? |

**判定**:
- max_df ≤ 0.20 Hz + settling ≤ 10 s → 论文复现物理上可行，继续训练
- max_df > 0.30 Hz → ANDES 与论文 Simulink 有结构性差异，需记录 deviation

---

## 决策树

```
V1 结果:
  H 单调降低 max_df?
  ├── 是 → V1-d max_df ≤ 0.20?
  │         ├── 是 → SAC 可以学到，优先修 axes.py + 扩 action range，再训练
  │         └── 否 → 需要 governor，做 V2
  └── 否 → ANDES 对 H 调节不响应
           → 必须先做 V2 (governor)，再重验 V1

V2 结果:
  Governor 改善 ≥ 50%?
  ├── 是 → 做 V3，确认上限
  └── 否 → ANDES vs Simulink 结构性差异，评估是否换后端

V3 结果:
  max_df ≤ 0.20 Hz?
  ├── 是 → 物理可行，R07 开始：修 axes.py + 修 action range + 加 governor + 重训
  └── 否 → 记录 ANDES 天花板，论文复现需声明 deviation
```

---

## 实现指引（给新对话）

**关键文件**:
- 环境入口: `env/andes/base_env.py` — `step()` / `reset()`
- V3 env（含 governor）: `env/andes/andes_vsg_env_v3.py`
- 扰动配置: `scenarios/kundur/disturbance_protocols.py`
- 评估入口: `scripts/research_loop/eval_paper_spec_v2.py`
- 论文 benchmark: `evaluation/paper_grade_axes.py::PAPER`

**V1 实现思路**:
```python
# 伪代码：固定 H，不训练，直接 eval
for H_val in [10, 30, 100, 300]:
    env.reset()
    # 强制所有 ESS: M = 2 * H_val
    for i in range(4):
        env.ss.GENCLS.set("M", env.vsg_idx[i], 2*H_val, attr='v')
    # 跑 LS1 episode（50 step）
    # 记录 freq trace → 算 max_df / settling
```

**输出格式**:
每个实验跑完填 [results/physics_validation/V{1,2,3}_results.json]，字段：
`H_val, governor_on, max_df_hz, final_df_hz, settling_s, raw_freq_trace`

---

## 成功标准

| 指标 | 通过线 | 含义 |
|---|---|---|
| V1 单调性 | H 每翻倍 max_df 降 ≥ 20% | ANDES 响应 H 调节 |
| V1-d max_df | ≤ 0.25 Hz | H 量级够用 |
| V2 governor 改善 | ≥ 50% max_df 降幅 | governor 必要 |
| V3 上限 | max_df ≤ 0.20 Hz | 论文复现物理可行 |

**任一指标不过 → 在继续 SAC 训练之前必须修对应的物理层问题。**

---

*写于 2026-05-07，基于 R01-R06 audit 结论。R04 adaptive=no_ctrl 信号促发此计划。*
