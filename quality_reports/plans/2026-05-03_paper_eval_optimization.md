# `evaluation/paper_eval.py` 优化计划

**Status:** SUPERSEDED (2026-05-03 by `2026-05-03_paper_eval_metrics_extract.md`)
**Reason:** 11 项 roadmap 框架被否决；改为按 deep-module 视角拆分独立 ticket。本文件保留作 scope 参考。
**Date:** 2026-05-03
**Scope:** `evaluation/paper_eval.py` (947 行 [FACT, `wc -l` 5-03]) 的评估方法学与工程结构优化
**Out-of-scope:** Paper-anchor 三层 G1-G6（不在本计划解决，详 CLAUDE.md PAPER-ANCHOR HARD RULE）；env / bridge / .slx / reward formula 改动（违反 paper_eval.py:19-23 hard boundary）

> **CLAIM 警示**: 本计划解决的是"评估工具的可信度与吞吐"，不是"paper 数字是否对齐"。后者由 G1-G6 verdict 决定，与本计划正交。任何工具优化都不会让 `cum_unnorm vs -8.04` 的对账从 INVALID 转 VALID。

---

## 1. 现状核对（用户 11 条观测 → 代码 FACT）

| # | 用户观测 | 代码核对 | 验证位置 |
|---|---|---|---|
| 1 | 943 行单文件 | **FACT** 947 行 | `wc -l evaluation/paper_eval.py` |
| 2 | 无单测 | **FACT** `evaluation/` 仅 `paper_eval.py` + `__init__.py` | `find evaluation/ -name '*.py'` |
| 3 | 每次 cold-start MATLAB | **FACT** `KundurSimulinkEnv(training=False)` 在 `main()` 单次构造 | paper_eval.py:793-796 |
| 4 | 无批量评估 API | **FACT** CLI 单 `--checkpoint`，无 `--batch` / 多 ablation | paper_eval.py:722-768 |
| 5 | 无 bootstrap CI | **FACT** `summary` 只有 mean/min/max；无 std/CI 字段 | paper_eval.py:589-604 |
| 6 | scenario 集冲突（inline vs manifest） | **FACT** `generate_scenarios(seed=42)` (132-157) ≠ `load_manifest(test)` (886-895) | paper_eval.py:132/880 |
| 7 | disturbance mode + env-var 双控 | **FACT** `KUNDUR_DISTURBANCE_TYPE.startswith("loadstep_paper_/ptdf_")` 静默 bypass CLI mode 分支 | paper_eval.py:433-440 |
| 8 | settle tol 5 mHz 硬编码 | **FACT** `SETTLE_TOL_HZ = 0.005` 模块常量，无 CLI override | paper_eval.py:52 |
| 9 | PHI 权重不写 metadata | **FACT** `result_to_dict` 输出无 `phi_f / phi_h / phi_d` 字段 | paper_eval.py:660-712 |
| 10 | r_f_share 用 abs() 非论文公式 | **FACT** `abs(rf) + abs(rh) + abs(rd)` 三项绝对值归一化 | paper_eval.py:583-587 |

10/10 观测全部代码 FACT 确认。设计合理处（公式即代码 / per-agent 分解 / sha256 / ablation flag / paper-anchor 免责）也全部 FACT 验证。

---

## 2. 优先级分组（按"出错代价 × 修复成本"反向排序）

### P0 — Correctness Blockers（影响数字可信度）
跨 run / 跨 ckpt 数字不可比 → 用户已经在 Round 1 vs Round 2 踩过坑。

- **P0a**: scenario 集单一真值（解决观测 #6）
- **P0b**: PHI 权重写入输出 metadata（解决观测 #9）
- **P0c**: disturbance mode 优先级显式化（解决观测 #7）

### P1 — Throughput（影响开发节奏）
单次评估时长 25-50 min × 7 ablation suite。

- **P1a**: batch CLI（解决观测 #3+#4，单次 cold-start 跑多 ckpt × 多 ablation）

### P2 — Statistical Defensibility & Structure（影响结论强度与维护成本）
- **P2a**: bootstrap CI on summary metrics（解决观测 #5）
- **P2b**: 单测覆盖核心 metric helpers（解决观测 #2）
- **P2c**: 文件分层 metrics / runner / output（解决观测 #1）

### P3 — Polish（低优先级配置化）
- **P3a**: `--settle-tol-hz` CLI flag（解决观测 #8）
- **P3b**: r_f_share 用论文 r_h / r_d 公式或重命名为 `r_h_abs_share_pct`（解决观测 #10）

---

## 3. 详细实施

### P0a — Scenario 集单一真值
**问题**: `--scenario-set none` 走 `generate_scenarios(seed=42, n=50)` 内联 RNG；`--scenario-set test` 走固定 manifest。两套 scenario 物理上不同，数字不可对照。

**改动**:
1. **删除 `generate_scenarios()` inline 模式**，或退化为 dev-only debug 路径（`--scenario-set debug-inline`），输出 metadata 必须含 `"scenario_source": "debug_inline_seed_42"`，且 JSON 文件名加 `_DEBUG` 后缀。
2. **要求生产 run 必须 `--scenario-set {train,test}`**：CLI 默认从 `none` 改为强制要求显式选择，无默认值（`required=True`）。
3. **Output JSON 加字段**:
   ```python
   "scenario_provenance": {
       "source": "manifest" | "debug_inline",
       "manifest_path": str | None,
       "manifest_sha256": str | None,
       "n_scenarios": int,
       "seed_base": int,
   }
   ```

**Files**: `evaluation/paper_eval.py` (CLI parser, `evaluate_policy`, `result_to_dict`)
**Test**: 新增 `tests/evaluation/test_scenario_provenance.py` — assert 每个 EvalResult 都带 manifest_sha256，inline 模式拒绝在 manifest_path 已设的情况下启动。
**Effort**: ~2h

### P0b — PHI 权重写入输出 metadata
**问题**: `total_reward = PHI_F·r_f + PHI_H·r_h + PHI_D·r_d` 但输出 JSON 不带 PHI 值。Round 1 (`PHI_F=100`) 与 Round 2 (`PHI_F=300`) JSON 数字不可同表对比，但代码不阻止。

**改动**:
1. 启动时从 `scenarios.kundur.config_simulink` 读取 `PHI_F / PHI_H / PHI_D`（如未来变更也可读 env 内部 attr）。
2. `result_to_dict` 顶层加：
   ```python
   "reward_weights": {
       "phi_f": float(env._PHI_F if hasattr(env, "_PHI_F") else <config>.PHI_F),
       "phi_h": ...,
       "phi_d": ...,
       "settle_tol_hz": SETTLE_TOL_HZ,  # 顺便把 P3a 之前的常量也曝露
   }
   ```
3. 跨 run 对账脚本（不在本计划，下游消费）应在合并 JSON 前 assert 三组 PHI 一致。

**Files**: `evaluation/paper_eval.py` (`result_to_dict`)
**Effort**: ~30 min

### P0c — Disturbance Mode 优先级显式化
**问题**: paper_eval.py:433-440：`KUNDUR_DISTURBANCE_TYPE.startswith("loadstep_paper_" / "loadstep_ptdf_")` 时静默 bypass CLI `disturbance_mode` 分支（445-463 整段不执行）。错配（如设了 env-var 又传了 `--disturbance-mode gen`）会安静地用 LoadStep 协议，CLI 参数被忽略。

**改动**:
1. 启动时显式校验冲突：
   ```python
   _env_type = os.environ.get("KUNDUR_DISTURBANCE_TYPE", "")
   _is_loadstep = _env_type.startswith(("loadstep_paper_", "loadstep_ptdf_"))
   if _is_loadstep and args.disturbance_mode != "bus":  # bus 是 default，可视为未指定
       raise SystemExit(
           f"Conflict: KUNDUR_DISTURBANCE_TYPE={_env_type} forces LoadStep "
           f"dispatch (bus field informational), but --disturbance-mode="
           f"{args.disturbance_mode} requested. Either unset env-var or "
           f"omit --disturbance-mode."
       )
   ```
2. Output JSON 加 `"disturbance_resolution"` 字段，记录最终生效的 `(env_type, cli_mode, dispatch_path)`，artifact 后期可审计。

**Files**: `evaluation/paper_eval.py` (`main`)
**Effort**: ~30 min

### P1a — Batch CLI
**问题**: 7 ckpt × 4 ablation = 28 次 invoke，每次 30-60s cold start [CLAIM, 用户估计未独立计时] = 14-28 min 纯启动浪费。

**改动**:
1. 新增 `--batch-spec PATH` 接受一个 JSON 描述：
   ```json
   {
     "checkpoints": ["results/.../best.pt", "results/.../ep400.pt"],
     "ablations": [
       {"label": "full", "zero_agent_idx": null},
       {"label": "ablate_es1", "zero_agent_idx": 0},
       {"label": "ablate_es2", "zero_agent_idx": 1}
     ],
     "scenario_set": "test",
     "disturbance_mode": "bus",
     "output_dir": "results/eval/batch_2026-05-03/"
   }
   ```
2. 单次 `KundurSimulinkEnv(training=False)` 构造，循环跑 (ckpt, ablation) 笛卡尔积，每个 run 独立 JSON 输出。
3. 单 ckpt CLI 路径保留（向后兼容），`--batch-spec` 与 `--checkpoint` 互斥。
4. 复用同一 env 时检查：每个 episode 已 `env.reset()`，scenario_idx 起点重置即可，无 leakage 风险（既有代码已经在 loop 内每 scenario reset）。

**Files**:
- `evaluation/paper_eval.py` 新增 `run_batch(spec_path: Path)` 函数（或抽到新模块 `evaluation/batch_runner.py`，与 P2c 协调）
- `tests/evaluation/test_batch_spec.py` — 解析 / 互斥校验

**Effort**: ~3h（含 spec schema + 测试）
**ROI**: 28 次 invoke × 45s cold start [CLAIM] ≈ 21 min 节省/批；预期一周跑 2-3 批 → 1h+/周。

### P2a — Bootstrap CI
**问题**: `summary` 给 50 scenario 的 mean，但两个策略相差 0.05 per_M 是否显著？无 CI 无从判断。

**改动**:
1. 新 helper `_bootstrap_ci(values: list[float], n_resample: int = 1000, alpha: float = 0.05) -> dict`：返回 `{mean, std, ci_lo, ci_hi, n_resample}`。
2. `summary` 关键字段升级：
   - `max_freq_dev_hz_mean` → 加 `_ci95_lo / _ci95_hi`
   - `rocof_hz_per_s_mean` → 同
   - `rh_share_pct_mean` → 同
   - `cumulative_reward_global_rf` → 加 `unnormalized_per_scenario_ci95`
3. `result_to_dict` 输出 `summary["bootstrap"]: {n_resample, alpha, seed}` 用于复现。
4. `numpy.random.default_rng(seed_base + 7919)` 固定 bootstrap 种子，避免 CI 在跑两次出微差。

**Files**: `evaluation/paper_eval.py`
**Test**: `test_bootstrap_ci_reproducible`（同 seed 两次结果 byte-equal）
**Effort**: ~2h

### P2b — 单测核心 metric helpers
**问题**: `_compute_global_rf_unnorm` / `_compute_global_rf_per_agent` / `_compute_per_agent_omega_summary` / `_settling_time_s` / `_rocof_max` 共 ~150 行核心逻辑无 pytest，重构风险高。

**改动**:
新建 `tests/evaluation/test_metric_helpers.py`：
1. `test_global_rf_zero_when_synchronous` — 4 agent 同步频率 → r_f_global = 0
2. `test_global_rf_per_agent_sums_to_global` — sum(per_agent) == global
3. `test_max_abs_df_per_agent_distinct` — 4 unique trajectories → 4 unique max
4. `test_omega_summary_sha256_distinct_for_distinct_traces`
5. `test_settling_time_returns_none_when_oscillating`
6. `test_rocof_zero_for_constant_trace`
7. `test_r_f_local_per_agent_eta1_ring_topology` — 用合成 trace 验证 ring adjacency 正确

**不测**: `evaluate_policy` 本身（需 MATLAB env，集成测试范畴，下游 G2/G3 验证替代）。

**Files**: `tests/evaluation/test_metric_helpers.py` (新), `tests/evaluation/__init__.py`
**Effort**: ~3h
**Coverage target**: 7 个 metric helpers 100% line coverage

### P2c — 文件分层
**问题**: 947 行单文件混杂 dataclass / metric helpers / scenario gen / evaluator core / CLI。

**改动**: 拆分（保持向后兼容入口 `python -m evaluation.paper_eval`）：

```
evaluation/
├── __init__.py
├── paper_eval.py           # CLI entry only (~150 lines after split)
├── metrics.py              # _compute_global_rf_unnorm, _rocof_max, _settling_time_s,
│                           # _compute_per_agent_*, _bootstrap_ci (P2a)
├── result_schema.py        # PerEpisodeMetrics, EvalResult dataclasses,
│                           # result_to_dict, schema_version constant
├── policy_selectors.py     # make_zero_action_selector, make_policy_selector,
│                           # zero-agent-idx wrapper logic
├── scenario_provenance.py  # generate_scenarios (debug-only),
│                           # manifest sha256 helper (P0a)
├── runner.py               # evaluate_policy core loop
└── batch_runner.py         # run_batch (P1a)
```

**保留入口**: `python -m evaluation.paper_eval` 继续工作，仅 import re-route。

**Files**: 所有 `evaluation/*.py`
**Effort**: ~4h（含 import 重连 + 全测试通过）
**前置**: P2b 必须先完成（先有测试再重构）。

### P3a — Settle Tol CLI Flag
```python
p.add_argument("--settle-tol-hz", type=float, default=SETTLE_TOL_HZ,
               help="Frequency settling tolerance in Hz; paper unspecified, "
                    "project default 0.005 Hz (= 0.01%% × 50 Hz).")
```
透传到 `_settling_time_s`；输出 metadata 加 `"settle_tol_hz": float`（与 P0b 同位置）。
**Effort**: ~15 min

### P3b — r_f_share 公式诚实化
**问题**: 现有公式 `abs(rf) + abs(rh) + abs(rd)` 是项目自定 metric，命名 `rh_share_pct_mean` 暗示与 paper 对应但实际不是。

**两个选项**:
- **B1（保守）**: 重命名 `rh_share_pct_mean` → `rh_abs_share_pct_mean`，docstring 写明"项目自定，非 paper 公式"。
- **B2（修正）**: 改用 paper r_h 公式（论文 Eq.X）—— **需先核对 `docs/paper/kd_4agent_paper_facts.md` §IV-C r_h 定义**，可能涉及 paper 没给绝对量级（只有比例），因此 B1 更安全。

**默认 B1**。在 P0b 输出 metadata 顺便加 `"rh_share_definition": "abs(rh) / (abs(rf) + abs(rh) + abs(rd)), project-specific, NOT paper Eq."`。

**Effort**: ~30 min

---

## 4. 实施顺序与依赖

```
P0b (PHI metadata)  ──┐
P0c (mode 冲突)      ──┼─→ P0a (scenario provenance)  ──┐
P3a (settle CLI)    ──┘                                  │
                                                          ├─→ P1a (batch)
P2b (单测) ─────────────────────────────────────────→ P2c (拆分)
                                                          │
                                                          └─→ P2a (CI)
                                                              P3b (rename)
```

**Phase 1**（~4h）: P0b + P0c + P3a + P0a — 全部 metadata / 校验级，不动核心逻辑
**Phase 2**（~3h）: P2b — 单测打底
**Phase 3**（~7h）: P2c (拆分) + P1a (batch) — 重构与吞吐
**Phase 4**（~2.5h）: P2a (CI) + P3b (rename)

**总工作量**: ~16.5h，可分 3-4 个 session。

---

## 5. 验证门

每个 P-task 完成后必须：
1. **Regression**: 用既有 `results/eval/loadstep_ptdf_round_2_*.json` 对应输入跑一次新版 paper_eval，输出 JSON 中（除新加字段外）所有数字必须 byte-equal 旧版。
2. **Lint**: `ruff check evaluation/ tests/evaluation/` clean。
3. **Test**: `pytest tests/evaluation/ -v` 全 pass。
4. **PHI consistency check**: P0b 完成后，对历史 Round 1 vs Round 2 JSON 跑一次"PHI 不一致拒合并"脚本（新增于本计划之外），验证能拦下旧报告。

---

## 6. 不做的事（明确边界）

- ❌ 不改 paper formula `_compute_global_rf_unnorm`（受 hard boundary line 19-23）
- ❌ 不改 env / bridge / reward 计算
- ❌ 不解锁 `paper_comparison_enabled = False`（受 PAPER-ANCHOR LOCK，G1-G6 责任）
- ❌ 不加自动 ablation suite 调度（保持 batch-spec 显式声明，不智能化）
- ❌ 不改 NE39（hard boundary 明确"No NE39"）

---

## 7. 风险

| 风险 | 缓解 |
|---|---|
| 拆分 P2c 后 import 路径变化破坏下游消费脚本（plot, compare） | 在 `evaluation/paper_eval.py` 顶部 re-export 关键 symbol（`from .metrics import _compute_global_rf_unnorm` 等），保持向后兼容 |
| Bootstrap CI 引入 rng 状态污染 | 用 `np.random.default_rng(seed_base + 7919)` 独立流，不复用 scenario rng |
| Batch runner 单次 env 复用产生跨 ckpt leakage | 每 ckpt 跑前 `env.reset()` + `agent.load()` 重置；测试中 assert ckpt A 跑两遍 byte-equal |
| Round 1 历史 JSON 缺 phi_* 字段，下游脚本崩 | 下游脚本 `result.get("reward_weights", {"phi_f": 100, ...})` fallback 默认值 + 显式 deprecation warning |

---

## 8. 待用户确认的开放问题

1. **P0a 默认行为**: 是否同意把 `--scenario-set` 改 required（无默认）？这会破坏所有现存调用方约定。备选：保留 `default="test"` 但 inline 模式仅在 `KUNDUR_PAPER_EVAL_DEBUG=1` 下可用。
2. **P3b 选项**: B1（rename + 备注）还是 B2（重写为 paper r_h）？后者需先做 paper 公式核对（~1h）。
3. **P1a Batch 输出布局**: `results/eval/batch_<date>/<ckpt_stem>_<ablation_label>.json` 单文件 per (ckpt, ablation)？还是合并成单 batch.json？前者便于现有 plot 脚本复用，后者便于 cross-ablation 统计。
4. **P2c 是否做**: 拆分 ~4h 工作，但收益是长期维护性。如果 paper_eval 接近 frozen，可推迟至 Round 3 之后。

未答前不启动 Phase 3。

---

**Approved?** [PENDING USER]
