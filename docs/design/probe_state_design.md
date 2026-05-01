# Probe State — Design Document

**Status:** living spec  
**Created:** 2026-04-30  
**Owner:** Multi-Agent VSGs / Kundur CVS  
**Pair doc:** `docs/EVIDENCE_PROTOCOL.md` (code-time)；本文是 runtime-time

---

## 1. 问题陈述

当前 KD Kundur CVS 调试痛点:

| 痛点 | 后果 |
|---|---|
| 模型状态散在 10+ 个 verdict markdown | 决策时翻文件、漏信息、引错版本 |
| Historical verdict 在模型改后立即 stale 但无警示 | 用过期数据推导新结论 (e.g. Option E 假设 Bus 7/9 50× 更强基于过期理解) |
| FACT (合约代码) vs CLAIM (注释/docs) 混淆 | 项目刚加 `# FACT/# CLAIM` 头注释解决 code-time，runtime 同样问题未解 |
| 调试靠推理 + 历史 verdict，不靠实测 | Option E 1.5 day 浪费在 Phasor 衰减假设错 |
| 模型改了无 regression check | 不知什么 invariant 破了 |

根因: **runtime evidence discipline 缺失**。

---

## 2. 设计目标

| # | 目标 |
|---|---|
| O1 | runtime evidence chain (跟 code-time `# FACT` 注释配对) |
| O2 | 单一 ground-truth dump (state_snapshot.json) — 一处看全部 |
| O3 | 自动 regression check — 模型改前后 diff 显示哪些 FACT 变了 |
| O4 | 决策点 fact-based 而非 vibes — Plan 引用实测数字而非推理 |
| O5 | 跟现有 verdict / paper_eval 边界清晰 (不替代) |

---

## 3. 设计原则 (不可违反)

| # | 原则 | 含义 | 反例 |
|---|---|---|---|
| P1 | **discovery > declaration** | 实体从模型/代码自动发现 | `N_ESS = 4` 硬编码 |
| P2 | **MCP-first** | 复用 45 个 simulink-tools | 自己 reimplement find_system |
| P3 | **single source of truth** | dispatch 从 `_DISPATCH_TABLE` 来 | probe 自己维护一份 list |
| P4 | **versioned schema** | snapshot 含 schema_version | unversioned dump |
| P5 | **fail-soft per phase** | 单 phase 失败 set `phase.error` 字段, 其他 phase 继续. snapshot 是 partial-valid (含 errors[]). Type B invariants SKIP, Type A 仍 assert. | 一处 raise 全停; 或 partial snapshot 导致 invariant FAIL (用 SKIP 解) |
| P6 | **read-only** | 不改 .slx / 不留 base ws 残留 | dump 后留垃圾 var |

违反任一 = 设计倒退。pytest invariants 应能 enforce P1+P3+P4。

---

## 4. 架构

### 4.1 模块拆分

```
probes/kundur/probe_state/
  probe_state.py      — entry; class ModelStateProbe
  _discover.py        — Phase 1 静态 discovery (S1-S7)
  _nr_ic.py           — Phase 2 NR/IC JSON 读
  _dynamics.py        — Phase 3+4 动态 sim
  _verdict.py         — G1-G6 verdict logic
  _report.py          — JSON dump + Markdown
  README.md           — 调用示例

tests/test_state_invariants.py   — pytest fixture + assertions
```

### 4.2 数据流

```
   [.slx + runtime.mat]      [code: schema/config/dispatch]
            │                          │
            ▼                          ▼
       MCP simulink-tools          import + introspect
            │                          │
            └────────┬─────────────────┘
                     ▼
              ModelStateProbe
                     │
       ┌─────────────┼──────────────┬──────────┐
       ▼             ▼              ▼          ▼
   discovery    open-loop sim   per-dispatch  verdict
       │             │              sim        │
       └────────┬────┴──────┬───────┘──────────┘
                ▼           ▼
          state_snapshot.json + STATE_REPORT.md
                ▼
      pytest invariants (regression)
```

### 4.3 Phase 范围

| Phase | 内容 | Status |
|---|---|---|
| **A** | static + NR/IC + open-loop + per-dispatch + G1-G5 | 实施中 |
| B | + Trained policy ablation (P1-P7, G6 部分) | deferred |
| C | + φ 因果短训 (R2-R3, G6 完整) | deferred |
| D | skill 化 + hook auto-trigger | deferred |

---

## 5. 接口契约

### 5.1 `state_snapshot.json` schema (v1)

```
{
  "schema_version": int (1+),
  "timestamp": ISO8601,
  "git_head": str (commit sha),
  "model_path": str,
  "model_mtime": ISO8601,
  
  "phase1_topology": {
    "powergui_mode": "Phasor"|"Discrete"|"Continuous",
    "n_ess": int, "n_sg": int, "n_wind": int,
    "ess_bus": {name: int},
    "omega_vars": [str],
    "dispatch_types": [str],   // 来自 known_disturbance_types()
    "config": {phi_f, phi_h, phi_d, dist_min, dist_max, dm_min, dm_max, ...}
  },
  "phase2_nr_ic": {
    "vsg_pm0_pu": [float], "sg_pm0_sys_pu": [float],
    "aggregate_residual_pu": float,
    "v_mag_range": [float, float],
    "hidden_slack_check": bool
  },
  "phase3_open_loop": {
    "sim_seconds": float,
    "omega_per_agent": [{mean, std, sha256, max_minus_min}],
    "all_sha256_distinct": bool
  },
  "phase4_per_dispatch": {
    <dispatch_type>: {
      "max_abs_df_hz_per_agent": [float],
      "agents_responding_above_1mHz": int,
      "rf_local_share_per_agent": [float]
    }
  },
  "falsification_gates": {
    "G1_signal":      {verdict, evidence},
    "G2_measurement": {verdict, evidence},
    ...
  },
  "errors": [{phase, message}]
}
```

### 5.2 G-verdict 状态机

```
PENDING (尚未跑) → PASS / REJECT / UNKNOWN(数据不足)
```

verdict 不可逆推 — 重跑后是新 verdict，不修改旧 snapshot。

### 5.3 CLI

```
python -m probes.kundur.probe_state              # 全跑
python -m probes.kundur.probe_state --phase 1    # 单 phase
python -m probes.kundur.probe_state --diff <prev_snapshot.json>
```

### 5.4 pytest API — Type A vs Type B

invariants 拆 2 类, 调和 P5 fail-soft 跟 acceptance 语义:

**Type A — data-independent**
- 来源: paper FACT (kd_4agent_paper_facts.md) + 项目设计契约 + 物理不变量
- 例: `n_ess == 4`, `phi_f == 100`, `aggregate_residual_pu < 1e-6`, `schema_version == 1`
- 不依赖 phase 数据 → phase 失败不影响
- **任一 Type A FAIL = build script 改坏 / paper FACT 改 / 设计契约破** → 必须 STOP 调查

**Type B — data-required**
- 依赖具体 phase 输出
- 例: `phase3.all_sha256_distinct`, `falsification_gates.G1.verdict in ('PASS','REJECT')`
- phase 失败 → `phase.error` 字段在 → invariant `pytest.skip` (不 FAIL)
- 数据齐时 assert 期望状态 (G1 当前期望 REJECT 不是 PENDING)

```python
import pytest

def _load_latest():
    snap = _read_most_recent_snapshot()
    if snap is None:
        pytest.skip("no snapshot — run probe_state first")
    return snap

# Type A 模板
def test_<contract>():
    snap = _load_latest()
    assert snap[<path>] == <expected>, <msg>

# Type B 模板
def test_<state>():
    snap = _load_latest()
    phase = snap.get('<phase_key>')
    if phase is None or 'error' in phase:
        pytest.skip("phase not run / errored")
    assert phase[<field>] <op> <expected>
```

**第一次跑 (无 snapshot)**: 全 SKIP, pytest exit 0.
**phase 全 OK**: Type A + Type B 全 assert.
**phase 部分 fail-soft**: Type A 全 assert, Type B 部分 SKIP. pytest exit 0.

只有 Type A FAIL 才让 pytest exit ≠ 0. 这跟 P5 fail-soft 一致.

### 5.5 配置阈值 — externalized (F1)

阈值不在 code hardcode. 抽 `probes/kundur/probe_state/probe_config.py`:

| 字段 | default | calibration source |
|---|---:|---|
| `open_loop_min_samples` | 100 | Phasor SS SampleTime ≈ 0.05s × 5s = 100 |
| `agent_response_threshold_hz` | 1e-3 | Probe B verdict (sub-mHz = noise floor) |
| `sha_diversity_min_ratio` | 0.05 | per-agent std diff > 5% × mean |
| `open_loop_sim_seconds` | 5.0 | IC kickoff 通常 < 2s settle, 留 3s margin |
| `verdict_pass_diff_hz` | 0.05 | Probe E sign-pair acceptance |
| `verdict_abort_diff_hz` | 0.01 | Probe E sign-pair noise floor |

`@dataclass(frozen=True)`. 修改阈值改 config 不改 code; snapshot
`config_used` 字段记录跑时 config 快照, 可追溯.

### 5.6 Snapshot file management (F2)

- 路径: `results/harness/kundur/probe_state/`
- 命名: `state_snapshot_<UTC_ts>.json` (e.g. `_20260430T1700.json`)
- Baseline: 软链 `baseline.json -> state_snapshot_<ts>.json`,
  build/dispatch/schema 重大改后手动 rebase
- Retention: 保留全部不自动清; `probe_state --gc --keep N` 手动留最近 N
- Diff: `probe_state --diff a.json b.json` 输出字段级 changes;
  `--diff baseline latest` 短语糖

### 5.7 Dispatch metadata schema (F3)

`probes/kundur/probe_state/dispatch_metadata.py`:

```python
@dataclass(frozen=True)
class DispatchMeta:
    mag: float                # probe 用的 magnitude
    mag_unit: str             # "sys-pu (SG cap)" / "sys-pu (total budget)" / "W"
    t_trigger_s: float
    sim_seconds: float
    expected_min_df_hz: float # 历史 verdict 已知下限; 实测 < 此值 → flag
    physics_note: str         # 跳 admittance? injection? etc
    historical_source: str    # verdict ID / probe artifact path

DISPATCH_METADATA: dict[str, DispatchMeta] = {
    "pm_step_proxy_g2": DispatchMeta(
        mag=0.5, mag_unit="sys-pu (SG cap)",
        t_trigger_s=0.5, sim_seconds=5.0, expected_min_df_hz=0.05,
        physics_note="mechanical Pm on G2; 1.33-of-4 agents",
        historical_source="cvs_v3_probe_b/probe_b_pos_gen_b2.json"),
    "pm_step_hybrid_sg_es": DispatchMeta(
        mag=0.5, mag_unit="sys-pu (total budget)",
        t_trigger_s=0.5, sim_seconds=5.0, expected_min_df_hz=0.3,
        physics_note="SG.Pmg += 0.7M + ESS.Pm += -0.3M/N",
        historical_source="F4_V3_RETRAIN_FINAL_VERDICT.md"),
    "loadstep_paper_trip_bus14": DispatchMeta(
        mag=0.5, mag_unit="sys-pu → W via cfg.sbase_va",
        t_trigger_s=0.5, sim_seconds=5.0, expected_min_df_hz=0.005,
        physics_note="CCS injection at Bus 14; Phasor 衰减",
        historical_source="OPTION_E_ABORT_VERDICT"),
    # ... 按 known_disturbance_types() 全列
}
```

不在 dict 的 dispatch → probe 跑时 WARN + fallback (mag=0.5, sim=5),
phase4 输出 mark `metadata_missing=True`. 防新加 dispatch 漏 calibrate.

### 5.8 Probe self-test strategy (F4)

测 **probe 逻辑** 不测 model. 全 mock, 不依赖 simulink.

| test | 验证什么 |
|---|---|
| `test_type_a_runs_without_snapshot` | 无 baseline 时 Type A SKIP 不 raise |
| `test_type_b_skips_when_phase_errored` | mock phase3.error → SKIP |
| `test_discovery_naming_pattern_match` | mock TW vars → discover (n_ess, n_sg, n_wind) |
| `test_snapshot_serializer_roundtrip` | dump → reload → 字段相等 |
| `test_g1_verdict_logic_with_known_inputs` | mock phase4 → verdict 期望 |
| `test_dispatch_metadata_missing_flag` | dispatch 不在 dict → metadata_missing=True |

新加 invariant 类型时 (Type C 等) 同步加 self-test. 不加 = 不算 done.

---

## 6. 扩展点 (Phase B/C/D)

### 6.1 Phase B — trained policy (1 hr)

加 `_trained_policy.py` module:
- 复用 `paper_eval.py --zero-agent-idx` flag
- 输出 `phase5_trained_policy.{action_mean, ablation_diffs, rf_rh_rd_share}`
- 不破 schema_version 1 — 字段 additive

约束:
- 仍 read-only (不写 base ws, 不改 .slx)
- 失败 fail-soft (best.pt 找不到 → set error, skip)

### 6.2 Phase C — 因果短训 (2 hr)

加 `_causality.py`:
- 跑 200 ep × 2 配置 (φ_f=100 vs 0)
- 输出 `phase6_causality.{rf_drives_improvement: bool, evidence}`
- 触发 G6 verdict 更新

约束:
- 写 separate run dir (跟 production train 分开)
- run dir 标 `[PROBE]` prefix 防误用

### 6.3 Phase D — skill 化 (deferred)

包 `kundur-probe-state` skill + hook:

```yaml
PostToolUse:
  - tool_name: Edit
    file_pattern: "scenarios/kundur/**/*.{m,py,json}"
    action: Skill('kundur-probe-state', '--diff')
```

约束:
- skill 跑 ≤ 30 min wall (Tier 1+2 only, 不包 Phase C 短训)
- 失败时不 block edit, 仅 warn

---

## 7. Alternatives considered

| 方案 | Pro | Con | 决策 |
|---|---|---|---|
| A. 纯 MCP orchestration (无脚本) | 0 代码 | 无 automate, 输出散乱 | ❌ |
| B. Hardcoded script | 写得快 | 模型改了高维护 | ❌ |
| **C. Discovery-style + MCP-first** | 80% 模型改自动适应 | 初期 1 hr 多 | **✓ 选** |
| D. 直接 skill 化 | 长期省 friction | 用过 < 3 次先做过度工程 | deferred |
| E. 整合进 paper_eval | 共用 50-scenario eval | 混淆 evaluator vs probe 职责 | ❌ |
| F. MATLAB-only probe (.m script) | 无 Python 跨语言 | JSON 序列化痛苦, pytest 接不上 | ❌ |

---

## 8. 失效模式 + recovery

| 信号 | 含义 | 行动 |
|---|---|---|
| Discovery 找不到 ESS / SG | UserData tag 缺 / build script 改坏 | STOP, flag build script |
| Open-loop sim 不收敛 | 模型 broken (跟 probe 无关) | mark error, 仍跑后续 phase |
| MCP simulink_run_script hang > timeout | MATLAB engine 卡 | restart engine, retry 1×, 然后 STOP |
| schema_version mismatch (load 旧 snapshot) | snapshot 过期 | 跑 migration 或重 dump |
| pytest invariants 全 FAIL | 是 invariant 写错还是 model 真坏？ | review invariant 优先 |
| 全 phase OK 但 OOM | sim trace 累积 | 加 streaming dump, 拆 phase 跑 |

---

## 9. 跟其他系统的边界

| 系统 | 职责 | 跟 probe 关系 |
|---|---|---|
| `paper_eval.py` | trained policy → cum_unnorm + per-episode metric | probe 复用其 50-scenario 跑法 (Phase B); 不替代 |
| Verdict markdown (`OPTION_E_ABORT_VERDICT.md` 等) | 决策记录 + 时间戳 | probe = 状态; verdict = 决策。两者并存 |
| `INVALID_PAPER_ANCHOR.md` | paper anchor lock 状态 | probe G1-G6 输出可触发 lock 解锁 (long-term) |
| `# FACT/# CLAIM` 注释 (EVIDENCE_PROTOCOL) | code-time discipline | runtime probe 是配对系统 |
| `tests/` (pytest) | unit + integration | invariants 是 probe 的 assert 化 |
| `harness_*` MCP tool | training control | 不重叠; harness 管 train，probe 管 model |

---

## 10. 维护策略

### 10.1 模型改动 → probe 反应

| 改动类型 | 概率 | probe 反应 | 维护成本 |
|---|---:|---|---:|
| 加 dispatch type | 80% | 自动 enumerate (`_DISPATCH_TABLE`) | 0 |
| 加/改 ESS / SG / wind | 30% | discovery 自动 (UserData tag) | 0 |
| 加新 bus | 50% | PowerLib query 自动 | 0 |
| 改 ToWorkspace var 命名 | 10% | filter pattern 改 1 处 | 10 min |
| 改 reward 公式 | 20% | `_dynamics.py::compute_rf` 改 | 30 min |
| 改 schema (workspace_vars) | 30% | `_verdict.py::is_effective` 改 | 30 min |
| Phasor → Discrete | 70% (Plan G) | auto detect | 0 |

3 个月预期总维护 ~30-60 min (vs hardcoded 设计 3-5 hr)。

### 10.2 两种 version: schema_version vs implementation_version (F5)

snapshot 含两个 version 字段, 区分**数据格式**变化和**probe 算法**变化:

| 字段 | bump 触发 | 影响 |
|---|---|---|
| `schema_version` (e.g. 1 → 2) | snapshot **数据字段** 加/删/改语义 | 旧 snapshot pytest invariants 兼容性 |
| `implementation_version` (semver, e.g. 0.3.2 → 0.4.0) | probe **算法** 改 (verdict 逻辑、discovery 规则、阈值默认值) | 跨 implementation 比对要谨慎 |

#### schema_version bump 流程
```
schema 结构变 (e.g. 加 phase5_*) →
   1. bump schema_version: 1 → 2
   2. 旧 v1 snapshot 仍可 load (Type A invariants 跨 version 通过 _migrate_v1_to_v2() 转)
   3. 重跑 baseline → 新 v2 snapshot
   4. update STATE_REPORT.md template
```

#### implementation_version bump 流程
```
probe 算法改 (e.g. G1 verdict 阈值改, discovery 规则改) →
   1. bump implementation_version (semver minor 或 major)
   2. CHANGELOG 记录改了什么 + 影响哪些 verdict
   3. 旧 snapshot mark 'compared_with_impl' = old_version 警告
   4. 不需重跑全 baseline, 但 verdict 字段值跨 version 比要看 CHANGELOG
```

**关键区分**: schema 不变只是 verdict 算法改 → implementation_version bump,
schema_version 不动. 这样旧 snapshot 仍 readable 但 verdict 解读要看
CHANGELOG.

### 10.3 旧 snapshot 兼容

`_load_snapshot(path)` 检查 schema_version:
- 当前 version → 直接 load
- 旧 version → 调 `_migrate_v1_to_v2()` 或 raise (无 migration)

---

## 11. Open questions

| ID | 问题 | 谁回答 |
|---|---|---|
| OQ1 | Phase C 因果短训跑在何处? 单独 run dir? | Phase C plan 时定 |
| OQ2 | probe 失败是否 block CI / commit? | Phase D skill 化时定 |
| OQ3 | snapshot retention 软策略 (跑 5+ 次后看实际累积) | 跑过 5+ 次后定 |

**Scope**: KD CVS only. 不考虑跨 model (NE39 等) 复用. 若未来要扩 NE39 →
重新审 §6 扩展点 + §10 维护策略 + 整 §3 原则.

---

## 12. References

### 项目文件
- `docs/EVIDENCE_PROTOCOL.md` — code-time evidence discipline (pair doc)
- `docs/paper/kd_4agent_paper_facts.md` — paper canonical (对账依据)
- `results/harness/kundur/INVALID_PAPER_ANCHOR.md` — paper anchor lock 状态
- `scenarios/kundur/disturbance_protocols.py::_DISPATCH_TABLE` — dispatch single source
- `scenarios/kundur/workspace_vars.py::_SCHEMA` — schema single source
- `scenarios/kundur/config_simulink.py` — config single source
- `evaluation/paper_eval.py` — Phase B 复用入口
- `quality_reports/plans/2026-04-30_probe_state_kundur_cvs.md` — Phase A 实施 plan

### 外部模式
- Snapshot testing (Jest / Insta 风格): JSON dump + diff
- Architecture Decision Record (ADR): `docs/decisions/`
- pytest fixture + parametrize: 跨 model 复用 OQ2

---

## 13. 变更记录

| Date | Author | Change |
|---|---|---|
| 2026-04-30 | main session | 初稿，Phase A 启动前定 |

(后续每次 schema bump / Phase 启动追加一行)

---

*living spec — 改前讨论, 改后追加 §13*
