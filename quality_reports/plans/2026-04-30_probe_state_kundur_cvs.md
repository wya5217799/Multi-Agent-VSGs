# Plan: KD Kundur CVS 模型探针 — `probe_state`

**日期:** 2026-04-30
**目的:** 未来调试 kundur_cvs_v3 时一次性拿到模型运行时 ground truth，
不靠推理 / 不靠历史 verdict。类比软件 testing 的 fixture + invariants。
**当前会话不执行**，本 plan 留给新窗口。

---

## 1. 类比定位

| 软件 testing 概念 | 本探针对应 |
|---|---|
| test fixture | `probe_state.py` 一次跑全部 dump |
| invariant assertion | G1-G6 falsification gates 自动评估 |
| snapshot test | `state_snapshot.json` (versioned) + diff |
| pytest hook | 改 build/dispatch/schema 后自动跑探针 (deferred to Phase D) |
| FACT vs CLAIM 注释 (code-time) | 探针 (runtime) — 完整 evidence chain |

---

## 2. 范围

**做**:
- 模型现状 dump → JSON + Markdown
- 自动 G1-G6 verdict
- pytest invariants

**不做**:
- 改 build / .slx / IC / runtime.mat
- 改 reward / SAC / env / bridge
- 跑短训 (deferred Phase C)
- skill 化 (deferred Phase D)

---

## 3. 设计原则（**最重要部分，不能违反**）

| 原则 | 含义 | 反例（禁止） |
|---|---|---|
| **discovery > declaration** | 从模型/代码自动发现实体 | `N_ESS = 4` 硬编码 |
| **MCP-first** | 最大复用现有 45 个 simulink-tools MCP | 自己 reimplement find_system |
| **single source of truth** | dispatch type 从 `_DISPATCH_TABLE.keys()` 来 | 探针自己维护一份 list |
| **versioned schema** | `state_snapshot.json` 含 `schema_version` | unversioned dump |
| **fail-soft per phase** | 单 phase 失败 set `phase.error`, 不影响其他 phase. 对应 Type B invariants SKIP (不 FAIL). Type A invariants 永远 assert (跟 phase 状态无关). | 一处 raise 全停; 或 phase 失败导致 invariant FAIL |
| **read-only** | 探针不写 base ws / 不改 .slx | dump 后留垃圾 var |

违反任一原则 = 设计倒退。

---

## 4. Phase 范围（本 plan 只做 A，B/C 后续）

| Phase | 内容 | 何时做 | 成本 |
|---|---|---|---|
| **A (本 plan)** | static + NR/IC + open-loop + per-dispatch signal + G1-G5 verdict | 现在 | 2-3 hr |
| B | + Trained policy ablation (P1-P7) | 用过 A 之后再说 | 1 hr |
| C | + φ 因果短训 (R2-R3, G6) | 真要解锁 paper anchor | 2 hr |
| D | skill 化 + hook auto-trigger | 用过 3+ 次后 | 1 day |

---

## 5. 实施 step 清单

### Step 0 — Prerequisite check (~15 min, MUST 先跑)

修弱点 #2 (discovery 假设错): build script **没**给 G1/G2/G3/ES1-4 source 块
打 `UserData.mode=ess/sg` tag。Plan 不能依赖 `UserData.mode` discovery。

实际可用 discovery 入口（grep 已 verify, 2026-04-30）：
- `find_system(BlockType='ToWorkspace')` + filter `VariableName starts with 'W_omega_'`
- 命名约定: `W_omega_ESi` (ESS i), `W_omega_Gj` (SG j), `W_omega_Wk` (wind k)
- ESS 数 = `len([v for v in tw_vars if v starts 'W_omega_ES'])`
- SG 数 / wind 数同理

Step 0 acceptance:

```python
# 在 _discover.py 顶部 unit test 形式
def test_naming_convention_discoverable():
    tw_vars = mcp.find_system(BlockType='ToWorkspace', VariableName_pattern='omega_*')
    ess_count = sum(1 for v in tw_vars if 'omega_ES' in v)
    sg_count = sum(1 for v in tw_vars if 'omega_G' in v and not 'omega_GND' in v)
    assert ess_count >= 4, f"build script changed: ess discovery returns {ess_count}"
    assert sg_count >= 3
```

如果命名约定**改了**（build 重构）→ Step 0 fail → STOP, executor 必须先
读最新 build 重新 verify discovery 入口。

不要尝试"自动 fallback 到别的 discovery" — naming convention 改是 build
重构信号, plan 重新审。

### Step 1 — Module 骨架 (~30 min)

新建 `probes/kundur/probe_state/` 目录:

```
probes/kundur/probe_state/
  __init__.py
  probe_state.py      — 主 entry; class ModelStateProbe
  _discover.py        — Phase 1 静态 discovery
  _nr_ic.py           — Phase 2 NR/IC 读 JSON
  _dynamics.py        — Phase 3+4 动态 sim
  _verdict.py         — G1-G5 verdict logic
  _report.py          — JSON dump + Markdown
  README.md           — 设计简述 + 调用示例
```

`__main__.py` 用法:

```bash
PY=".../andes_env/python.exe"
$PY -m probes.kundur.probe_state           # 全跑
$PY -m probes.kundur.probe_state --phase 1 # 仅静态
$PY -m probes.kundur.probe_state --phase 4 # 仅 per-dispatch (假设前面已 dump)
```

**验收**:
- [ ] 目录建好、`__main__` 路由 phase 选择
- [ ] `--help` 输出可读

---

### Step 2 — Phase 1 静态 discovery (~45 min)

**目标**: dump 模型拓扑、块参数、workspace var、Solver 配置。**0 hardcode**。

发现策略:

| 实体 | 发现方法 |
|---|---|
| 4 ESS / 3 SG / 2 wind | `find_system(BlockType='ToWorkspace')` + filter `VariableName matches 'W_omega_(ES\\|G\\|W)\\d+'` (Step 0 verified) |
| omega_ts var | 同上, 用 `get_param(blk, 'VariableName')` 拿实际 ts 名 |
| Bus anchor | `power_analyze` 或 `simulink_powerlib_net_query` 遍历每 bus |
| Dispatch types | `from disturbance_protocols import known_disturbance_types` |
| φ / DIST / DM/DD | `from config_simulink import PHI_F, PHI_H, ...` |

**输出 JSON 字段** (示意):

```json
"phase1_topology": {
  "powergui_mode": "Phasor",
  "n_ess": 4, "n_sg": 3, "n_wind": 2,
  "ess_bus": {"ES1": 12, "ES2": 16, ...},
  "omega_vars": ["omega_ts_1", ...],
  "dispatch_types_total": 21,
  "config": {"phi_f": 100, "phi_h": 5e-4, "dist_max": 1.0, ...}
}
```

**验收**:
- [ ] 跑一次输出 phase1 JSON
- [ ] 没有任何 hardcode `4` / `omega_ts_1`
- [ ] 用 `simulink_get_block_tree` MCP 调用 ≥ 1 次
- [ ] 模型改成 5 ESS 探针自动 report n_ess=5（不用改代码）

---

### Step 3 — Phase 2 NR/IC 读 JSON (~10 min)

读 `kundur_ic_cvs_v3.json` → 提取 vsg_pm0_pu, sg_pm0_sys_pu, V_mag/V_ang,
aggregate_residual_pu, hidden_slack_check.

**纯 file IO，零 MATLAB**。

**验收**:
- [ ] phase2 JSON 输出含 5 字段
- [ ] aggregate_residual_pu < 1e-6 (现 IC 应过)

---

### Step 4 — Phase 3 Open-loop sim (~30 min)

跑 5s sim 无扰动 (零所有 Pm-step + 零所有 LoadStep amp)，提取
omega_ts_1..N，算:

- per-agent: `mean`, `std (post 2s)`, `sha256(values)`, `max-min spread`
- aggregate: `all_sha256_distinct`, `max - min std across agents`

用 `simulink_run_script_async` + poll。失败处理: 单 phase 失败 set
`phase3.error = "msg"`，不影响 phase 4。

**验收**:
- [ ] sim 跑出 omega traces n > 100 sample
- [ ] 4 sha256 全异 (现 build 应过)
- [ ] 失败时 JSON 输出 `error` 字段，整 probe 不崩

---

### Step 5 — Phase 4 Per-dispatch signal (~60 min)

**F3 修复**: 不同 dispatch 物理意义不同, 跨 dispatch 比较有 systematic
bias. 新建 `probes/kundur/probe_state/dispatch_metadata.py`, schema +
完整字典见 **design §5.5**. 此 step 实施: 按 design schema 填 KD 全
dispatch (来自 `known_disturbance_types()`), 缺 metadata 的跑时 WARN +
mark `metadata_missing=True`.

对每个 effective dispatch type 跑一次 (用其 metadata 的 mag/sim_s)，记录:

- per-agent `max|Δf|`, nadir, peak, r_f_local share
- `agents_responding_above_1mHz`

**Effective dispatch 自动 filter**:

```python
from scenarios.kundur.workspace_vars import spec_for, PROFILE_CVS_V3
def is_effective(dispatch_type) -> bool:
    # 通过 dispatch -> adapter -> resolved workspace var key -> effective_in_profile 检查
    ...
```

不在 effective list 的 dispatch (LoadStep R, CCS Trip, CCS Load Center)
跳过 sim，只 dump schema metadata。

预期数据点 (跑当前 model):

| dispatch | agents_responding | max|Δf| (Hz) |
|---|---|---|
| pm_step_proxy_g2 | 1 | ~0.097 |
| pm_step_proxy_random_gen | 1.33 (avg) | ~0.05 |
| pm_step_hybrid_sg_es | 4 | ~0.65 mean |

**验收**:
- [ ] effective dispatch 全跑过、其他 skip
- [ ] hybrid_sg_es 的 max|Δf| 实测 > 0.3 Hz (跟 F4 v3 monitor 对账)

---

### Step 6 — G1-G5 verdict logic (~30 min)

从 phase 3+4 数据自动算:

| Gate | 逻辑 |
|---|---|
| G1 信号 | ≥ 1 dispatch 让 ≥ 2 agents 响应 (>1e-3 Hz) |
| G2 测量 | phase3.all_sha256_distinct == True |
| G3 梯度 | per-agent r_f_share max-min > 5% × mean |
| G4 位置 | 不同 bus 的 dispatch 产生不同 mode shape signature (此 phase A 简化: 仅 SG-side dispatch 间对比) |
| G5 trace | 任一 dispatch 下 4 agents 响应 std diff > noise floor |

每 gate verdict ∈ {PASS, REJECT, PENDING}。

**输出**:

```json
"falsification_gates": {
  "G1_signal": {"verdict": "REJECT", 
                "evidence": "no dispatch produces ≥2 agents responding"},
  "G2_measurement": {"verdict": "PASS", "evidence": "..."},
  ...
}
```

**验收**:
- [ ] 5 gate 全有 verdict
- [ ] verdict 跟 historical (Probe B 1.33-of-4) 一致

---

### Step 7 — JSON dump + Markdown report (~30 min)

输出位置: `results/harness/kundur/probe_state/state_snapshot_<timestamp>.json`
+ `STATE_REPORT_<timestamp>.md`

JSON schema 顶层:

```json
{
  "schema_version": 1,
  "timestamp": "...",
  "git_head": "...",
  "phase1_topology": {...},
  "phase2_nr_ic": {...},
  "phase3_open_loop": {...},
  "phase4_per_dispatch": {...},
  "falsification_gates": {...},
  "errors": []
}
```

Markdown report 含:
- 顶部速查表（关键数字）
- G1-G5 verdict 表
- 偏差表（项目 vs paper FACT 数值对照）
- per-dispatch signal 表

**验收**:
- [ ] JSON 写出 + 可被另一个脚本 load
- [ ] MD 在 GitHub-flavored markdown viewer 渲染干净

---

### Step 8 — pytest invariants (~30 min)

修弱点 #1 (chicken-and-egg) + #3 (fail-soft 跟 acceptance 矛盾): invariants
拆 **Type A** (data-independent, 不依赖 baseline) 和 **Type B** (data-required,
phase 数据缺时 SKIP 不 FAIL).

新建 `tests/test_state_invariants.py`:

```python
import pytest

def _load_latest():
    """Load most recent snapshot. SKIP test if no snapshot exists."""
    snap = ...
    if snap is None:
        pytest.skip("no snapshot yet — run probe_state first")
    return snap

# ---- Type A: data-independent (硬编码自 paper FACT + 已知设计契约) ----
# 这些 invariants 第一次跑就该 PASS, 不需 baseline.

def test_schema_version_known():
    snap = _load_latest()
    assert snap['schema_version'] == 1

def test_paper_fact_n_ess_eq_4():
    """Paper Sec.IV-A: 4 ESS. 项目设计契约."""
    snap = _load_latest()
    assert snap['phase1_topology']['n_ess'] == 4

def test_paper_fact_n_sg_eq_3():
    """Paper Sec.IV-A: G1/G2/G3 (G4 已 replaced by W1)."""
    snap = _load_latest()
    assert snap['phase1_topology']['n_sg'] == 3

def test_nr_consistency():
    """NR 物理不变量, 不依赖 baseline."""
    snap = _load_latest()
    nr = snap['phase2_nr_ic']
    assert nr['aggregate_residual_pu'] < 1e-6, \
        f"NR diverged: {nr['aggregate_residual_pu']}"

def test_phi_f_paper_aligned():
    """Paper Table I: phi_f=100. 项目应一致."""
    snap = _load_latest()
    assert snap['phase1_topology']['config']['phi_f'] == 100.0

# ---- Type B: data-required (phase 数据齐时才 assert) ----
# phase 失败 → 数据缺 → SKIP. fail-soft per phase 兼容.

def test_omega_per_agent_distinct():
    snap = _load_latest()
    p3 = snap.get('phase3_open_loop')
    if p3 is None or 'error' in p3:
        pytest.skip("phase3 not run / errored")
    assert p3['all_sha256_distinct'], "G2 measurement collapsed"

def test_at_least_one_effective_dispatch():
    snap = _load_latest()
    p4 = snap.get('phase4_per_dispatch')
    if not p4:
        pytest.skip("phase4 not run")
    g1 = snap['falsification_gates'].get('G1_signal', {})
    if g1.get('verdict') == 'PENDING':
        pytest.skip("G1 PENDING — insufficient phase4 data")
    # 已知历史: G1 当前是 REJECT. 不强制 PASS, 但 verdict 必须明确.
    assert g1['verdict'] in ('PASS', 'REJECT'), g1
```

**5 个 Type A + 2 个 Type B** = 第一次跑能 PASS Type A, Type B 看 phase
数据有无 SKIP 或 PASS. **不会因为 phase 失败导致整 pytest run FAIL**.

**验收**:
- [ ] 文件含至少 5 Type A + 2 Type B
- [ ] 第一次跑 (无 snapshot) → 全 SKIP (`_load_latest` 返回 None 时所有
  test skip), pytest exit code = 0
- [ ] 跑过 probe 后 → Type A 全 PASS; Type B 视 phase 数据 PASS or SKIP
- [ ] 已知 G1 REJECT 状态下, `test_at_least_one_effective_dispatch` 仍 PASS
  (verdict 不是 PENDING 即可)

---

### Step 8.5 — Probe self-test (~20 min, F4 修复)

probe 自己是代码, 也会有 bug. 加 `tests/test_probe_internal.py` 测
**probe 逻辑**(不是 model invariants), 测试策略见 **design §5.6**.

**验收**: ≥ 5 test, `pytest tests/test_probe_internal.py -v` 全 PASS,
**不依赖 simulink** (纯 python mock).
覆盖: Type A SKIP 行为 / Type B SKIP-on-error / discovery pattern /
serializer roundtrip / verdict logic 各 1 test.

---

### Step 9 — 全 probe 一次性 smoke run (~15 min)

`$PY -m probes.kundur.probe_state` 跑完整流程。

修弱点 #3: pytest acceptance 跟 fail-soft 调和 — 用 Type A/B 区分语义.

**验收** (注意 acceptance 不再是 "全 PASS" 而是 "已知预期一致"):
- [ ] 总 wall time < 60 min (含 buffer; 原估 30 min 太乐观)
- [ ] `state_snapshot_<ts>.json` 写出, `schema_version == 1`
- [ ] `STATE_REPORT_<ts>.md` 可读
- [ ] **Type A invariants 全 PASS** (data-independent, 物理 + 设计契约)
- [ ] **Type B invariants 状态符合预期**:
  - 全 phase OK → Type B 全 PASS
  - 某 phase fail-soft errored → 对应 Type B SKIP (不 FAIL)
- [ ] 无 Type A FAIL — 任一 Type A FAIL 是 build script 改坏或 paper FACT 改了, 必须 STOP 调查
- [ ] 无残留 base ws var (跑前后 `evalin('base', 'who')` diff 为空)
- [ ] G1-G5 verdict 跟历史一致 (G1=REJECT under hybrid 已知, G2=PASS 期望)

---

## 6. 失败信号 + 中止条件

| 信号 | 含义 | 行动 |
|---|---|---|
| Discovery 找不到 4 ESS | build script 改坏了 / UserData tag missing | STOP，先看 build script |
| Open-loop sim 不收敛 | 模型本身 broken (跟探针无关) | STOP，flag 已知 issue |
| MCP simulink_run_script 长时间 hang | MATLAB engine 卡死 | restart engine, retry 1 次后 STOP |
| pytest 全 FAIL | invariant 写错 | review invariant 而非 model |
| 所有 phase 单独 OK 但全跑 OOM | sim trace 累积内存 | 加 streaming dump 或拆 phase 跑 |

---

## 7. Scope 边界

不做: Phase B/C/D 任一内容 (见 §4)。不跨 model 复用 (KD CVS only)。

---

## 8. References (executor 必读)

| 文件 | 用途 |
|---|---|
| `docs/paper/kd_4agent_paper_facts.md` | paper canonical (对账) |
| `results/harness/kundur/INVALID_PAPER_ANCHOR.md` | paper anchor lock 状态 |
| `scenarios/kundur/disturbance_protocols.py` line 756-812 | dispatch types 单一真值 |
| `scenarios/kundur/workspace_vars.py` | schema (effective_in_profile 来源) |
| `scenarios/kundur/config_simulink.py` line 91/114/115/224/232 | φ/DIST/DM/DD 当前值 |
| `scenarios/kundur/kundur_ic_cvs_v3.json` | NR/IC ground truth |
| `evaluation/paper_eval.py` | reward 公式实现 (Phase 4 r_f 算法引用) |

---

## 9. MCP 工具速查（不重复读 AGENTS.md）

| 用途 | tool |
|---|---|
| 块发现 | `simulink_get_block_tree`, `find_system` via run_script |
| 块参数 | `simulink_query_params` |
| Bus 分析 | `simulink_powerlib_net_query` |
| Sim 短跑 | `simulink_run_script` (≤ 60s) |
| Sim 长跑 | `simulink_run_script_async` + `simulink_poll_script` |
| Solver 配置 | `simulink_solver_audit` |
| 模型加载 | `simulink_load_model` / `simulink_close_model` |

---

## 10. 时间预算 (含 +50% buffer, 原 4.5 hr 乐观估计)

| Step | 净估 | 含 buffer |
|---|---|---|
| 0 prerequisite check | 15 min | 20 min |
| 1 骨架 | 30 min | 45 min |
| 2 静态 | 45 min | 75 min |
| 3 NR/IC | 10 min | 15 min |
| 4 open-loop | 30 min | 45 min |
| 5 per-dispatch | 60 min | 90 min |
| 6 verdict | 30 min | 45 min |
| 7 dump | 30 min | 45 min |
| 8 pytest | 30 min | 45 min |
| 9 smoke | 15 min | 30 min |
| **总** | **~4.75 hr** | **~7.5 hr** |

按 7.5 hr 规划. MCP 调用次数多 / sim wait 长是常见超时来源.

---

## 12. 设计 self-review (写完一遍后跑一次)

写完 Step 1-9 后回头核对:

- [ ] 没有 `n_ess = 4` / `omega_ts_1` 等 hardcode (grep 验)
- [ ] dispatch types 来自 `known_disturbance_types()`，不是探针自己 list
- [ ] 每 phase 失败独立、不冒泡
- [ ] JSON 字段全有 type 注释 (字典 schema 文档化)
- [ ] 没改 base ws / .slx (跑前后 git status clean except probe 目录)

self-review 任一项 fail → 不算完成，返修。

---

## 13. 完成后下一步（不在本 plan）

- 跑 baseline probe → 拿到 ground truth state
- 用这个 ground truth 重写 Plan v3 / v4 (现用实测数字而非推理)
- 决定追 paper +47% 的下一步 (Decision 0 in 之前讨论)

---

*end of plan — keep simple*
