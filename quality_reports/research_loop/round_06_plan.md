# R06 Plan — 物理对齐 Audit (强 pivot)

**Status**: DRAFT
**Date**: 2026-05-07
**Trigger**: R05 verdict — 8 hyperparam 维度全 falsified 6-axis=0.037 attractor; 必须 pivot 到物理对齐 audit

## 上轮
R05 8 arm × 30ep × 1 seed × {V1/V2/V3/PHI_D=1/5/λ=0/action 2x/disturb 5x} 全 6-axis = **0.037**.
H1-H5 全 falsified. R01-R05 共 ~3 hr 把 6-axis 从 0.035→0.037, 改善 5%.

## 关键认知 reset
- **Hyperparam 不是 root cause** (R05 已穷尽证明)
- **smoothness axis 0.99 是 trap** (1 个 axis 接近 paper ≠ 6-axis paper-match, 几何均值需全部 ≥ 0.X)
- **train reward 不是 paper-grade proxy** (R05 -5K 和 -99K arm 6-axis 都 0.037)
- 真 root cause 候选: eval 公式 / action 物理语义 / disturbance protocol — 都是非训练问题

## 假设 (R06 = audit-first, train-second)

H1 (R06 主验): paper 计算 max_df/settling/range 用的物理量纲 跟项目不同 → 项目 0.037 实际等价 paper 的 ≥ 0.5
   - 例如 paper 用 |Δω rad/s| 而非 |Δf Hz|; paper 计算 ΔH 用 effective inertia 而非 GENCLS.M

H2: paper §II-B "ESS P 注入" 跟项目 "GENCLS.M/D 直接调" 物理语义不一致 → ΔH range 物理上限被项目 hardcap 在 ~1
   - 要还原, 需改 env 用 P 注入仿真 effective inertia 模式

H3: paper LS magnitude calibration 跟项目不同 → cum_rf -1.61 vs -0.13 是 disturbance 公式不同, 不是 5× scale 问题

## 跑啥 (K=4, 主 audit + 1 长训对照)

```
exp1: r06_eval_formula_audit                cpu, 0 train, ~30 min 主上下文人工
      工作:
        1. 读 docs/paper/kd_4agent_paper_facts.md §IV-C eval 公式
        2. 比较 evaluation/paper_grade_axes.py 的 max_df / settling / range 计算
        3. 找 mismatches (单位 / 窗口 / 归一化)
      out: quality_reports/research_loop/audits/2026-05-07_eval_formula_audit.md
      priority=10  (gates R07 决策)

exp2: r06_action_semantics_audit            cpu, 0 train, ~30 min 主上下文人工
      工作:
        1. 读 paper §II-B "ESS P 注入" + Eq.6-10
        2. 对比 env/andes/base_env.py step() 的 GENCLS.set("M", ...) / set("D", ...)
        3. 写 deviation 文档: 项目 直接调 M/D 参数 vs paper P 注入 effective inertia
        4. 决策 R07 是否要重写 env 用 P 注入模式 (大改, 风险高)
      out: audits/2026-05-07_action_semantics_audit.md
      priority=10

exp3: r06_paper_disturbance_audit           cpu, 0 train, ~20 min 主上下文人工
      工作:
        1. 读 docs/paper/kd_4agent_paper_facts.md disturbance 段
        2. 读 disturbance_protocols.py PAPER_LS_MAGNITUDE_SYS_PU 真值 (1.53 / 0.90)
        3. 对比 evaluate_andes.py legacy {"PQ_Bus14": -2.48} 是 system_pu 还是 local
        4. 算 paper LS 在 ANDES PQ.Ppf 应该是几
      out: audits/2026-05-07_paper_disturbance_audit.md
      priority=9

exp4: r06_v1_env_5seed_200ep_smoke (副线)   gpu × 5, 200ep, ~30 min wall
      ckpt: fresh V1 env, PHI_D=1.0, λ=0.01, 5 seed 42-46
      cmd: DEVICE=cuda LAMBDA_SMOOTH=0.01 PYTHONUNBUFFERED=1 \
           python scenarios/kundur/train_andes.py --episodes 200 --seed {S} --phi-d 1.0 \
           --save-dir results/research_loop/r06_v1_5seed_200ep_s{S}
      goal: 给 R05 V1 30ep 0.037 一个 5seed 长训对照点 — 万一 200ep 训练能跳出 attractor
      priority=6 (副线, audits done 后看是否 kill)
```

## 期 (G1-G6)
- exp1: 找到 ≥ 1 个 eval 公式 mismatch, 算"项目修正后 6-axis", 看是否 ≥ 0.10
- exp2: 写出 action semantic deviation, 给 R07 是否 rewrite env 决策
- exp3: 算出 paper LS 的真实 PQ 数值, R07 用这个值重 eval
- exp4: 5seed mean overall 看是否 > 0.04 (R05 V1 30ep 0.037)

## 不行咋办
- audits 全 "公式一致, 物理语义一致" → R07 是 reward 公式重写 (e.g. r_h 用 per-agent abs 而非 mean-then-square)
- audit 找到 1 个 critical mismatch → R07 修正, eval 重跑, 看 6-axis 是否跳到 ≥ 0.10
- exp4 V1 5seed 200ep ≥ 0.05 → V1 env 有训练时长效应, R07 用 V1 长训作主线

## R07 衔接
依 audits 结果定:
- mismatch 找到 → R07 = 修 evaluator + 重 eval R05 8 arms (无需重训)
- mismatch 没找到 → R07 = action semantics rewrite (大动) OR reward 公式重设计

## §note
- R06 主要是 audit, 不靠 daemon 跑训练; 主 work 在 AI 主上下文做
- exp4 副线副 daemon, 完后回看 audit 决定是否需要

---

# §Done (post-execution append)
(待 R06 audits + exp4 完成后填)
