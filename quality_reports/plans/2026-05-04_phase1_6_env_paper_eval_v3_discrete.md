# Plan: Phase 1.6 — Env config + paper_eval propagation to v3 Discrete

**Status**: DRAFT
**Estimated**: 1.5–2 hr | **Actual**: TBD
**Trigger**: P0-1e (B1-B4) merged → Stage 0 inspection 输出 / handoff 决策矩阵 "1-2 个小 config drift" → "Phase 1.6 minimal plan"
**Supersedes**: none

---

## §0 Quickstart for Fresh Session (READ FIRST)

> 本章节是 self-contained handoff — 新会话不需任何额外 conversation history 即可执行 Phase 1.6。
> 注：`quality_reports/session_logs/` 在 .gitignore，所以 handoff 永久 context 嵌入在此 (plan committed)。

### §0.1 验证当前状态（必跑）

```bash
cd "C:\Users\27443\Desktop\Multi-Agent-VSGs-discrete"   # 必须用此 worktree
git rev-parse --abbrev-ref HEAD                          # 期望: discrete-rebuild
git log --oneline -5                                     # 期望 HEAD: P0-1e commit (含 plan)
git status                                               # 期望: clean (results/harness 未跟踪除外)
```

⚠️ **不要在** `pensive-goldberg-c29299` 或主 `Multi-Agent  VSGs` worktree 工作 — 会偏差。

### §0.2 P0-1e 已完成（2026-05-04）— 4 fix 摘要

| ID | 文件:行 | 修了什么 | Verify |
|----|---------|----------|--------|
| **B1** | `evaluation/paper_eval.py:1045` | `os.environ[X]=` → `setdefault` (CLI 现在可切 v3 Discrete) | 56 passed |
| **B2** | `env/simulink/kundur_simulink_env.py:881-922` | 删 4 死写 (LOAD_STEP_AMP/_TRIP_AMP[14/15] post-Phase-1.5 deprecated) | 156 passed |
| **B3** | `scenarios/kundur/disturbance_protocols.py` LoadStepRBranch.apply() | 强制 PAPER_LS_MAGNITUDE_SYS_PU (1.53 bus14, 0.90 bus15)，caller magnitude IGNORED with warn-once | 158 passed (+2 new) |
| **B4** | dispatch_metadata + config_simulink + disturbance_protocols + tests | 归档 3 `loadstep_paper_trip_*` (CCS family), `LoadStepCcsInjection` 标 DEPRECATED 保留体 | 110 passed |

**Combined**: 283 passed across 6 affected suites, 0 new failures.

### §0.3 4 个 pre-existing test_probe_internal failures (PHASE 1.7 follow-up，**不修**)

- `test_dispatch_metadata_coverage_against_known_types` — 缺 `pm_step_hybrid_sg_es_probe_g2` METADATA
- `test_g4_dispatch_metadata_g_dispatches_have_design_5_7_floors`
- `test_i5_dispatch_metadata_hybrid_has_ceiling`
- `test_p2b_g4_uses_thresholds_singleton`

Verified pre-existing on c202fb0 via `git stash` + rerun。**Phase 1.6 scope discipline: 不修这些。**

### §0.4 Phase 1.6 必要 env-var (PowerShell)

```powershell
$env:KUNDUR_MODEL_PROFILE = "C:\Users\27443\Desktop\Multi-Agent-VSGs-discrete\scenarios\kundur\model_profiles\kundur_cvs_v3_discrete.json"
$env:KUNDUR_DISTURBANCE_TYPE = "loadstep_paper_random_bus"
```

### §0.5 不要做的事（严格）

- ❌ 不要在错的 worktree 工作（必须 `Multi-Agent-VSGs-discrete`）
- ❌ 不要重启 CCS injection 路径（62× 弱于 paper anchor 实测）
- ❌ 不要修 §0.3 4 个 pre-existing failures（Phase 1.7 follow-up）
- ❌ 不要直接进 Phase 1.7 RL training 而不先 Phase 1.6 ALL_PASS
- ❌ 不要相信 agent "pytest pass" 当物理验收（必须主会话 MATLAB run paper_reward 数值）
- ❌ 不要把 B3 magnitude lock 当 bug — 它是 paper-anchor 守门设计
- ❌ 不要 commit Phase 1.6 after smoke fail = SUCCESS（G1.6-A/B/C 必须 PASS）
- ❌ 不要挪 §1 阈值（engineering_philosophy.md §6 anti-goalpost）

### §0.6 必读文件（按顺序）

1. **本文件 §0-§6** ← Phase 1.6 plan, 必读首先
2. `quality_reports/plans/2026-05-04_phase1_5_paper_lumped.md` ← Phase 1.5 plan + acceptance gates
3. `quality_reports/reviews/2026-05-04_route_audit.md` ← 严格 audit framework (W1-W8 弱项)
4. `docs/paper/kd_4agent_paper_facts.md` §1.1.1 / §6.2 / §8.4 / §12 ← paper anchor 数字
5. `quality_reports/plans/2026-05-03_engineering_philosophy.md` ← 13 原则（重点 §6 anti-goalpost / §13 honest ignorance）

### §0.7 P0-1e 估时校准 datapoint（新增）

| Cycle | Estimate | Actual | 备注 |
|---|---|---|---|
| P0-1e (B1+B2+B3+B4 cleanup) | 1.5 hr | ~50 min wall | 4 agent 并行 + 主验证 |

**Pattern**: cleanup cycles 估时偏保守。Phase 1.6 smoke physics cycles 不能套此 trend。Phase 1.5 attempt 1 数据点显示 physics smoke cycles 可能 100% 失败 + 100% revert（建模假设错时是 100%，不是估时偏差），budget cap 严格执行。

---

## §0a Context

P0-1d (Phase 1.5 paper-lumped reroute, commit c202fb0) 完成 + P0-1e (B1/B2/B3/B4 cleanup, this cycle) 完成后，剩余 Phase 1.6 作用是：让 `paper_eval.py` 与训练 pipeline 在 v3 Discrete profile 下端到端可跑（smoke validation），把 Z route 留下的 90% wiring 推到 100%。

**核心新事实**（来自 Stage 0 + RL pipeline audit）：

- `train_simulink.py`: profile-aware via `KUNDUR_MODEL_PROFILE` env-var ✓
- RL agent dim: obs=7 (3 local + 2×2 邻居), action=2 (ΔH/ΔD), 4-agent ring — 与 paper Eq.11-13 / Sec.IV-A 一致 ✓
- B1 fix 后 `paper_eval.py` CLI 可切 v3 Discrete profile via `KUNDUR_MODEL_PROFILE` ✓
- B3 fix 后 `loadstep_paper_*` family 强制 paper magnitude (1.53/0.90 sys-pu)，消除训练/eval magnitude drift ✓
- B2/B4: 死代码清理，schema-code 一致

**未验证（Phase 1.6 必须做）**：
1. `paper_eval.py --profile=v3_discrete` smoke run（1-2 episode）— 是否真的端到端跑通
2. `train_simulink.py --episodes 5 --scenario-set none` smoke on v3 Discrete — RL training loop 是否能 step + apply_disturbance + write_H_D + read_omega/Pe
3. 信号验证：`KUNDUR_DISTURBANCE_TYPE=loadstep_paper_random_bus` 下，B3 magnitude lock 实际产出 paper_reward ≈ -1.61 (LS1) / -0.80 (LS2) — paper-anchor 仍达成

## §1 Acceptance Gates (PRE-REGISTERED, IMMUTABLE)

| ID | Threshold | Measurement | Verdict |
|---|---|---|---|
| **G1.6-A** | paper_eval.py CLI 用 `KUNDUR_MODEL_PROFILE=...kundur_cvs_v3_discrete.json` 跑 1 episode 不报错 | `python -m evaluation.paper_eval --episodes 1 --run-id phase1_6_smoke` exit code 0 | TBD |
| **G1.6-B** | `train_simulink.py --episodes 5` smoke on v3 Discrete 不报错 + 完成 5 episode + 写 results dir | exit code 0 + `results/sim_kundur/runs/phase1_6_train_smoke/` 存在 + `training_log.npz` ≥ 5 行 | TBD |
| **G1.6-C** | B3 magnitude lock 实测：`loadstep_paper_random_bus` 5 ep avg paper_reward ∈ [-2.0, -0.6] | parse smoke run output for `paper_reward` field per episode | TBD |
| **G1.6-D** | 联合 pytest（B1-B4 affected suites）no new failure vs P0-1e baseline | `pytest tests/test_paper_eval_runner test_evaluate_policy_integration test_kundur_workspace_vars test_disturbance_protocols test_phase1_5_paper_lumped` → 283 passed | PASS (P0-1e 已验) |
| **G1.6-E** | 4 pre-existing test_probe_internal failures 在 follow-up §5.1 文档化（不修） | follow-up 列表存在 + commit refs | TBD |

## §2 TodoWrite Mapping (1:1)

| Todo content | Step |
|---|---|
| Smoke run paper_eval.py on v3 Discrete | §3.1 |
| Smoke run train_simulink.py 5-ep on v3 Discrete | §3.2 |
| Verify B3 magnitude lock paper-reward in smoke output | §3.3 |
| Document 4 pre-existing failures as Phase 1.7 follow-up | §3.4 |

## §3 Steps (atomic, file-level)

### 1. paper_eval smoke (G1.6-A)

- 1.1 在 PowerShell 设 `$env:KUNDUR_MODEL_PROFILE="<repo>/scenarios/kundur/model_profiles/kundur_cvs_v3_discrete.json"`
- 1.2 在 PowerShell 设 `$env:KUNDUR_DISTURBANCE_TYPE="loadstep_paper_random_bus"`
- 1.3 跑 `python -m evaluation.paper_eval --episodes 1 --run-id phase1_6_paper_eval_smoke 2>&1 | tee results/phase1_6_paper_eval.log`
- 1.4 验：exit code = 0；output dir 存在；至少 1 episode 写入 `paper_reward` 字段
- 1.5 若 fail：grep error → patch（最多 30 min budget；超过则 ROLLBACK，开 Phase 1.6.1 micro-cycle 单查 paper_eval）

### 2. train_simulink smoke (G1.6-B)

- 2.1 同上 env-var 设置
- 2.2 跑 `python scenarios/kundur/train_simulink.py --mode simulink --episodes 5 --update-repeat 1 --run-id phase1_6_train_smoke 2>&1 | tee results/phase1_6_train.log`
- 2.3 验：exit code = 0；`results/sim_kundur/runs/phase1_6_train_smoke/training_log.npz` 至少 5 episode；reward field 不全 NaN
- 2.4 若 fail：grep error → patch（30 min budget；超过则 ROLLBACK + Phase 1.6.2）

### 3. B3 magnitude lock signal verification (G1.6-C)

- 3.1 从 step 1 + step 2 的输出 parse paper_reward per episode
- 3.2 验：均值在 [-2.0, -0.6]（paper LS1=-1.61 / LS2=-0.80 的 ±25% band）
- 3.3 若超出 band：检查 B3 `_warned_keys` log — 若有警告说明 magnitude 被 override，路径正确；若无警告且数值不对，说明 dispatch 没走 LoadStepRBranch（adapter routing bug）

### 4. Pre-existing failure documentation (G1.6-E)

- 4.1 创建 `quality_reports/audits/2026-05-04_pre_existing_test_probe_internal_failures.md`
- 4.2 内容：4 个 failure 名 + 来源 commit 推断 + 建议 Phase 1.7 follow-up cycle 单独修
  - `test_dispatch_metadata_coverage_against_known_types` — 缺 `pm_step_hybrid_sg_es_probe_g2` METADATA
  - `test_g4_dispatch_metadata_g_dispatches_have_design_5_7_floors` — design-floor 阈值漂移
  - `test_i5_dispatch_metadata_hybrid_has_ceiling` — hybrid ceiling 阈值
  - `test_p2b_g4_uses_thresholds_singleton` — singleton wiring drift
- 4.3 在 audit 文件 footer 标 "do not fix in Phase 1.6 — scope discipline; Phase 1.7 cleanup cycle"

## §4 Risks

- **R1**: paper_eval smoke fail（B1 fix 不全）— mitigation: 30 min budget cap + rollback
- **R2**: train_simulink smoke fail (e.g., MATLAB engine crash on first reset)— mitigation: 30 min budget + Phase 1.6.2 micro
- **R3**: B3 paper_reward out-of-band (G1.6-C) — mitigation: 不挪阈，开 G1.6-C diagnostic（可能是 phi_resweep 漂移 / Pm_step 量纲漂移）

## §5 Out of scope

- `pm_step_hybrid_sg_es_probe_g2` METADATA 补缺（4 个 pre-existing failure 之一）— Phase 1.7 follow-up
- 其他 3 个 test_probe_internal design-floor failure — 同上
- RL agent 收敛验证（5 ep smoke 不验 convergence）— Phase 1.7 trial training
- v3 Discrete 性能 / FastRestart 集成 — Phase 1.5+ optimization (deferred per §6 of phase1_progress doc)
- New England NE39 v3 Discrete 等价 — out of branch scope

## §6 References

- `quality_reports/plans/2026-05-04_phase1_5_paper_lumped.md` — Phase 1.5 plan (P0-1d, c202fb0)
- `quality_reports/session_logs/2026-05-04_p0-1d_handoff.md` — handoff context
- `quality_reports/reviews/2026-05-04_route_audit.md` — strict audit
- B1-B4 commit (this cycle, P0-1e) — TBD hash
- Stage 0 inspection: this session main thread

---

# §Done Summary (append-only, post-execution)

**Commit**: TBD
**Gate verdicts**: TBD
**Estimate vs actual**: 1.5–2 hr est / TBD
**Surprises**: TBD
