# Plan: ANDES 6-axis paper alignment 恢复路径

**Status**: DRAFT
**Estimated**: 4 phase × 1-2 day = 4-8 day
**Trigger**: `quality_reports/audits/2026-05-07_andes_6axis_failure_analysis.md` 失败分析

> **目标**: 把 6-axis overall score 从 0.036 提到 ≥ 0.5, 论文级 = 0.7+.
>
> 不追求 1.0 (论文系统底层不可知, ANDES 数值不同必有偏差),
> 但要让 6 个 axis 都进入"论文级一致"区间 (single axis ≥ 0.5).

---

## §1 Acceptance Gates (PRE-REGISTERED, IMMUTABLE)

| ID | Threshold | Measurement | Verdict |
|---|---|---|---|
| G1 | 6-axis overall score ≥ 0.5 (LS1 + LS2 mean, V2 env, best ckpt) | `python evaluation/paper_grade_axes.py` mean of LS1/LS2 overall | TBD |
| G2 | max\|Δf\| ≤ 0.20 Hz (LS1 / LS2 best ckpt) | 6-axis Axis-1 score ≥ 0.30 | TBD |
| G3 | settling_s ≤ 6 s (LS1 best) | 6-axis Axis-3 score ≥ 0.20 | TBD |
| G4 | ΔH range ≥ 100 (LS1 DDIC best) | 6-axis Axis-4: project span / paper span ≥ 0.30 | TBD |
| G5 | ΔH/ΔD smoothness std ≤ 1.0 (LS1 DDIC best) | 6-axis Axis-5/6 score ≥ 0.7 | TBD |
| G6 | DDIC > Adaptive > NoCtrl 6-axis ranking 保持 | mean overall score order | TBD |

**几何均值约束**: G1 要求 6 axis 都 > 0, 任一 axis 0 → overall=0 → fail.

---

## §2 Steps

### Phase A — Action smoothing (项目内, 0 物理改动)

期望提升: smoothness axis 0.7→1.0, overall 0.04→0.06.

1. Edit `env/andes/base_env.py:_compute_rewards` — 加 `r_smooth = -λ_smooth · Σ_i (Δa_{i,t} - Δa_{i,t-1})²`
   - 参数: λ_smooth = 0.01 (经验值, 待 sweep)
2. Edit `env/andes/base_env.py` — `INCLUDE_OWN_ACTION_OBS = True` (让 actor 看到 last action)
3. Edit `agents/sac.py` — 检查 `target_entropy` 设置, 必要时调到 -2 (鼓励 deterministic)
4. Run smoke: 1 seed × 30 ep V2 env, 验证 critic loss 不爆 + ΔH std 下降
5. 6-axis 评估: 期望 smoothness axis ≥ 0.85

**Acceptance**: smoothness axis ≥ 0.85 (LS1 DDIC). 其他 axis 不要变差.

### Phase B — 启 IEEEG1 governor + EXST1 AVR

期望提升: max_df 0 → 0.4, final_df 0 → 0.4, settling 0 → 0.3, **同时 3 axis**.

1. Inspect `andes/cases/kundur/kundur_full.xlsx` — 确认 GENROU 是否有 GovExciter 关联
2. Edit `env/andes/andes_vsg_env.py::_build_system` — 在 `ss.setup()` 后添加:
   - `ss.add("IEEEG1", {"idx": f"GOV_{i}", "syn": f"GENROU_{i}", ...})` × 4
   - `ss.add("EXST1", {"idx": f"AVR_{i}", "syn": f"GENROU_{i}", ...})` × 4
3. WSL smoke: power flow + TDS 不发散
4. Re-eval no-control LS1/LS2 → 期望 max_df 0.6 → 0.3
5. 落 deviation 文档: `docs/paper/andes_governor_deviation.md` 声明启用 governor 是离开论文
   §II-A literal 但贴近论文实际系统 (Kundur [49] 经典含 governor + AVR)

**Acceptance**: no-ctrl LS1 max_df ≤ 0.30 Hz (论文 0.13). settling_s ≤ 6s.
**Risk**: ANDES IEEEG1 add API 可能与项目代码不兼容 — fallback: 用 GovActuator 替代或读 ANDES doc.

### Phase C — 重选 H₀ baseline (range axis 修复)

期望提升: range axis 0 → 0.5, **同时 ΔH 和 ΔD 两个 axis**.

1. Edit `env/andes/andes_vsg_env_v2.py`:
   - `VSG_M0 = 100.0` (H₀=50s, 与论文 ΔH=[-100,300] 物理一致)
   - `D0_HETEROGENEOUS = np.array([100, 80, 30, 50])` (按比例放大 5×)
   - `DM_MIN, DM_MAX = -100, 300` (paper-literal)
   - `DD_MIN, DD_MAX = -100, 250`
2. WSL smoke: V2v3 env 加载 + power flow 收敛
3. 跑 1 seed × 30 ep V2v3 + Phase A smoothing + Phase B governor → 验证训练不发散
4. 6-axis 评估: 期望 ΔH range axis 0 → 0.5

**Acceptance**: ΔH/ΔD range axis 都 ≥ 0.30 (LS1 DDIC).
**Risk**: H₀=50 可能让系统过 over-damped → max_df 反而升 / Δf 不响应扰动.
**Mitigation**: 先做 Phase C-pre: H₀=20/30/50/80 不带训练扫拓扑稳定性.

### Phase D — 整体重训 + 6-axis 重评

把 Phase A/B/C 三处改动合并, 重训 5 seed × 500 ep + V2v3 env (governor + H₀=50 + smoothing).

1. 新建 `env/andes/andes_vsg_env_v3.py` — 子类 V2 + Phase B governor + Phase C 新 baseline
2. 新建 `scenarios/kundur/train_andes_v3.py` — 包装器
3. 新建 `scenarios/kundur/_run_v3_5seed.sh` — 5 seed × 500 ep × 顺序跑
4. WSL 后台启动 (run_in_background=true), 预计 6-8 hr
5. 完成后: `EVAL_PAPER_SPEC_ENV=v3 ... python scenarios/kundur/_eval_paper_specific.py`
6. `python evaluation/paper_grade_axes.py results/andes_eval_paper_specific_v3/` → ranking
7. 期望: best ckpt overall ≥ 0.5

**Acceptance**: G1 PASS (overall ≥ 0.5).

### Phase E — 落 verdict + 更新文档

1. Write `quality_reports/verdicts/2026-05-07_andes_v3_recovery_verdict.md`
2. 更新 `docs/paper/andes_replication_status_2026-05-07_6axis.md` §3 ranking 表
3. 更新 `scenarios/kundur/NOTES_ANDES.md` §1 量级表
4. 更新 `paper/figures/MODELS_INDEX.md` — 加 V3 variant
5. 重画 fig6/7/8/9 用 V3 best ckpt, `PAPER_FIG_VARIANT=v3env_<best_ckpt>`

---

## §3 Risks

- **R1**: Phase B governor 让系统 over-damped → max_df 反而下降但 ranking 失真
  - **Mitigation**: 先 ablation: V2 + governor (no smoothing, no H₀ change) 跑 1 seed 看
    max_df 改善幅度
- **R2**: Phase C H₀=50 让 power flow 不收敛或 TDS 发散
  - **Mitigation**: 4 个 H₀ 候选先 power flow 验证 + 5 step TDS smoke, 再选可行的
- **R3**: Phase A smoothing penalty 让 cum_rf ranking 退化
  - **Mitigation**: 实测 λ_smooth ∈ {0.001, 0.01, 0.1} 三档 sweep
- **R4**: 整体重训 5 seed × 500 ep × ANDES 单进程 ~6-8 hr, WSL 资源占用
  - **Mitigation**: Phase D 用户授权后再启动. 保留 V1/V2 model dir 不删
- **R5**: 启 governor 偏离论文 §II-A literal scope → paper writing 需声明
  - **Mitigation**: 写 `docs/paper/andes_governor_deviation.md` 解释 Kundur [49] 隐含 governor

---

## §4 Out of scope

- **不做** AVR/Governor 内环建模超越 IEEEG1/EXST1 标准
- **不做** ANDES Kundur full case 修改 (W1/W2 / 4 ESS 拓扑保持当前)
- **不做** evaluation/metrics.py reward 公式改动 (Eq.15-18 实现已等价论文)
- **不做** 改 dt / M / episode 时长 (与论文一致, 不动)
- **不做** 通信失败 / 通信延迟实验 (Sec.IV-D/E 等 G1-G6 物理 PASS 后再做)

---

## §5 References

- 失败分析: `quality_reports/audits/2026-05-07_andes_6axis_failure_analysis.md`
- 6-axis 评估: `evaluation/paper_grade_axes.py`
- 论文事实: `docs/paper/kd_4agent_paper_facts.md` §13 (Q-D, Q-H, Q-A)
- ANDES IEEEG1 doc: https://docs.andes.app/en/latest/groupdoc/TurbineGov.html#ieeeg1
- ANDES EXST1 doc: https://docs.andes.app/en/latest/groupdoc/Exciter.html#exst1

---

# §Done Summary (append-only, post-execution)

(待 Phase A-E 全部完成后填写)
