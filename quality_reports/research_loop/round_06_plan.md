# R06 Plan — 物理对齐 Audit (强 pivot)

**Phase**: Audit (R05 attractor 触发, per SKILL.md Explore→Exploit→Audit 工作流)
**Status**: DRAFT v2 (2026-05-07 优化: 加 exp0 attractor 性质诊断, 修 exp3 constant 错指, exp4 标 background)
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

## 跑啥 (K=5, exp0 attractor 性质诊断 + 主 audit + 1 长训对照)

```
exp0: r06_attractor_nature_diagnosis        cpu, 0 train, ~10 min 主上下文人工   priority=11 (最高, gates R06 整体)
      工作:
        1. 读 R05 8 ckpt traces JSON (results/research_loop/r05_*_s42/traces*.json)
        2. 算每 arm 的 ΔH / ΔD 实际幅度 (max - min over episode)
        3. 算 6-axis 0.037 中 smoothness (axis 4-5) 占几何均值贡献多少
        4. 决策:
           (a) 真 attractor — agents 真的训了, 卡在 reward landscape 局部 → exp1-3 audit 继续
           (b) 假象 — ΔH/ΔD < 1 (agents 几乎不动), smoothness 0.99 是因为不动反而平滑
               → root cause 是 SAC 探索/entropy/reward shape, **不是 eval 公式**
               → R06 整体方向变, exp1-3 audit 无意义, 改 R07 = entropy/reward shape sweep
      out: quality_reports/research_loop/audits/2026-05-07_attractor_nature.md
      理由: R05 8 arms 全 0.037 是 attractor 还是 "agents 不动 + smoothness 高分" 假象?
            range axis = 0 印证 (b) 嫌疑. 必须先验, 不然 audit 找错方向.

exp1: r06_eval_formula_audit                cpu, 0 train, ~30 min 主上下文人工
      工作:
        1. 读 docs/paper/kd_4agent_paper_facts.md §IV-C eval 公式
        2. 比较 evaluation/paper_grade_axes.py 的 max_df / settling / range 计算
        3. 找 mismatches (单位 / 窗口 / 归一化)
        4. **fallback**: 若 axes.py 数学跟 paper §IV-C 代码层一致, 不止比"代码 vs 代码",
           字符级比 paper §IV-C 原公式 LaTeX vs axes.py 逐符号 (变量名/下标/积分上下限/sign)
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
        1. 读 docs/paper/kd_4agent_paper_facts.md disturbance 段 (paper §III/§IV LS 描述)
        2. 读 ANDES env DIST_MIN/DIST_MAX (env/andes/andes_vsg_env.py:66-67 = 0.5/2.0 sys_pu)
        3. 对比 paper LS magnitude (cum_rf -1.61 sys_pu) 跟 ANDES uniform [0.5, 2.0] mean 1.25
        4. 若 paper 用固定 LS=1.61 而项目 random uniform, 即使 mean 接近也分布不同 → 改 fixed LS
      out: audits/2026-05-07_paper_disturbance_audit.md
      priority=9
      ⚠ 修正: 老 plan 引用 disturbance_protocols.py PAPER_LS_MAGNITUDE_SYS_PU=(1.53, 0.90)
        是错的 — 那是 Simulink-discrete repo 的 constant, ANDES repo 不存在.
        L4 commit (e40ff06) audit 时已验. 改查 paper_facts.md, 不查代码 constant.

exp4: r06_v1_env_5seed_200ep_smoke (副线)   gpu × 5, 200ep, ~30 min wall
      ckpt: fresh V1 env, PHI_D=1.0, λ=0.01, 5 seed 42-46
      cmd: DEVICE=cuda LAMBDA_SMOOTH=0.01 PYTHONUNBUFFERED=1 \
           python scenarios/kundur/train_andes.py --episodes 200 --seed {S} --phi-d 1.0 \
           --save-dir results/research_loop/r06_v1_5seed_200ep_s{S}
      goal: 给 R05 V1 30ep 0.037 一个 5seed 长训对照点 — 万一 200ep 训练能跳出 attractor
      priority=6 (副线, audits done 后看是否 kill)
      **timing**: BACKGROUND, 主上下文跑 exp0-3 时同步起 (audit 是 CPU 人工, exp4 GPU,
        不冲突 wall). 在 exp0 完成后启 (~10 min 后), exp4 30 min 跑完时 audit 还在跑.
      ⚠ exp0 若 verdict (b) 假象 → kill exp4 (V1 200ep 也不会破假象), 转 R07 reward shape sweep
```

## 期 (G1-G6)
- exp0: 决定 R06 整体方向 — (a) 真 attractor / (b) agents 不动假象
- exp1: 找到 ≥ 1 个 eval 公式 mismatch, 算"项目修正后 6-axis", 看是否 ≥ 0.10
- exp2: 写出 action semantic deviation, 给 R07 是否 rewrite env 决策
- exp3: 算出 paper LS 在 ANDES PQ 应该是几, R07 用这个值重 eval
- exp4: 5seed mean overall 看是否 > 0.04 (R05 V1 30ep 0.037)

## 不行咋办
- exp0 verdict (b) 假象 → R06 整体重写, exp1-3 audit 暂停, R07 = SAC entropy / reward shape sweep
- audits 全 "公式一致, 物理语义一致" → R07 是 reward 公式重写 (e.g. r_h 用 per-agent abs 而非 mean-then-square)
- audit 找到 1 个 critical mismatch → R07 = E phase: 修 + 重 eval R05 已 train 8 ckpt (0 train, ~10 min)
- exp4 V1 5seed 200ep ≥ 0.05 → V1 env 有训练时长效应, R07 用 V1 长训作主线

## R07 衔接 (per SKILL.md Phase 契约)
依 audits 结果定 R07 Phase:
- exp0 (b) 假象 → R07 **Phase E**: SAC entropy / reward shape × 6 arm × 50 ep × 1 seed parallel
- mismatch 找到 → R07 **Phase E (audit-driven)**: 修 evaluator + 重 eval R05 8 ckpt (0 train, ~10 min)
- mismatch 没找到 + exp0 (a) → R07 **Phase Audit**: action semantics rewrite (大动) OR reward 公式重设计
- exp4 200ep 跳出 → R07 **Phase P**: 5seed × 500ep V1 长训定稿

## §note
- R06 主要是 audit, 不靠 daemon 跑训练; 主 work 在 AI 主上下文做
- exp4 副线副 daemon, 完后回看 audit 决定是否需要

---

# §Done (post-execution append)
(待 R06 audits + exp4 完成后填)
