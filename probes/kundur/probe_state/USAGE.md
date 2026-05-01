# probe_state 使用指南 (操作者)

> **本文档 = 操作者实操手册**. 命令 / workflow / 故障排查 / 何时跑.
>
> 同目录 sibling docs (边界严格不重叠):
> - `README.md` — 设计原理 / scope / 为什么这么设计 (开发者读)
> - `AGENTS.md` — AI agent 决策表 + JSON contract + hard rules (AI 读)
>
> 本文不重复 sibling 内容: 不解释设计原则 (见 README), 不列 JSON
> 字段 schema (见 AGENTS).

## 这玩意是什么

Kundur CVS Simulink 模型的**运行时 ground-truth 探针**.
不靠推理 / 不靠历史 verdict — 跑一次, 拿到当前模型实际状态:

- 拓扑 / NR / 配置 (Phase 1+2, 静态)
- 动态信号 (Phase 3+4, 跑 sim)
- trained-policy 是否真用 4 agent (Phase 5, ablation)
- φ_f reward penalty 是不是因果 driver (Phase 6, 短训 + R1)

输出 6 个 falsification gates G1-G6, 全 PASS = paper anchor 解锁条件满足.

---

## 文件位置

```
probes/kundur/probe_state/      ← 探针 13 模块
    README.md                   ← 设计原理 + 命令快查
    USAGE.md                    ← 你正读的这份 (操作手册)
    __main__.py                 ← CLI 入口 (python -m ...)
    probe_state.py              ← 编排器 (ModelStateProbe class)
    probe_config.py             ← 阈值 + impl_version (F1+F5)
    _discover.py                ← Phase 1 静态发现
    _nr_ic.py                   ← Phase 2 NR/IC 读 JSON
    _dynamics.py                ← Phase 3+4 动态 sim
    _trained_policy.py          ← Phase 5 ablation (Phase B)
    _causality.py               ← Phase 6 短训 (Phase C)
    _verdict.py                 ← G1-G6 verdict 逻辑
    _report.py                  ← JSON + Markdown 输出
    _diff.py                    ← snapshot diff CLI
    dispatch_metadata.py        ← 22 dispatch 配置 (mag / sim_s / floor / ceiling)

results/harness/kundur/probe_state/   ← 输出
    state_snapshot_<TS>.json    ← 完整数据 (FACT)
    STATE_REPORT_<TS>.md        ← 人读报告
    state_snapshot_latest.json  ← alias to most-recent run
    baseline.json               ← G3 baseline (手动 promote 后才有)

results/sim_kundur/runs/probe_phase_c_*  ← Phase 6 短训 run dir
quality_reports/                ← 各 phase 计划 + prereq + verdict 文档
tests/                          ← invariants + self-test
```

---

## 前置 / 一次性准备

```bash
# Python 用项目 conda env (含 matlab.engine)
PY="C:/Users/27443/miniconda3/envs/andes_env/python.exe"

# (一次性 sanity)
$PY -m probes.kundur.probe_state --help     # 看可选 flag
$PY -m pytest tests/test_probe_internal.py  # 33 个 mock 测试, ~0.2s
```

---

## 5 个常用 workflow

### 1. 改了 build 脚本 / IC / dispatch table 后 — 跑全 phase

```bash
$PY -m probes.kundur.probe_state \
    --phase 1,2,3,4 \
    --sim-duration 3.0
```

**wall**: ~80 s (含 MATLAB cold start 6 s + Phase 4 跑 12 dispatch ~50 s)

看输出:

```
results/harness/kundur/probe_state/state_snapshot_<TS>.json
results/harness/kundur/probe_state/STATE_REPORT_<TS>.md
```

打开 `STATE_REPORT_*.md`, 看顶部 G1-G5 全 PASS = 改动没破信号层.

---

### 2. 看 trained policy 是不是真用 4 agent — 跑 Phase 5

```bash
$PY -m probes.kundur.probe_state \
    --phase 5 \
    --phase-b-n-scenarios 5
```

**wall**: ~3-5 min (6 paper_eval cold-start × ~30 s each)

输出 G6_partial verdict + ablation_diffs (per-agent contribution).

需要前置: 至少 1 个 v3 best.pt 在 `results/sim_kundur/runs/`. 自动 search,
取最新. CLI 也可指定: `--checkpoint <path>`.

---

### 3. 验 φ_f penalty 是 driver — 跑 Phase 6 (短训 + R1)

```bash
# smoke (10 ep, plumbing-only) — ~5 min
$PY -m probes.kundur.probe_state \
    --phase 5,6 \
    --phase-c-mode smoke

# full (200 ep, 真信号) — ~50 min wall
$PY -m probes.kundur.probe_state \
    --phase 5,6 \
    --phase-c-mode full \
    --phase-b-n-scenarios 5 \
    --phase-c-eval-n-scenarios 5
```

**重要**: Phase 6 占 MATLAB engine 排他 ~小时级, 不要并行跑其他 train.

输出 G6 完整 verdict (`scope=g6_complete`):
- PASS = trained policy 真用 ≥2 agent + 比 zero_all 显著好 + φ_f penalty 是 driver
- REJECT = 退化 / spurious / no improvement
- PENDING = 数据不足 (ckpt 缺 / 200 ep 未收敛)

---

### 4. 跟历史 baseline 比 — diff workflow

```bash
# (一次性) 把 V1 full mode 跑出的好 snapshot 设为 baseline
$PY -m probes.kundur.probe_state \
    --promote-baseline results/harness/kundur/probe_state/state_snapshot_20260501T074245.json

# 输出 (示例):
# src:    .../state_snapshot_20260501T074245.json
# dst:    .../baseline.json
# new baseline verdicts: G1=PENDING  G2=PASS  G3=PENDING  G4=PENDING  G5=PASS  G6=PASS

# 之后每次跑完探针, 一行看 diff:
$PY -m probes.kundur.probe_state --diff baseline latest

# 等价于 explicit 路径:
$PY -m probes.kundur.probe_state \
    --diff results/harness/kundur/probe_state/baseline.json \
           results/harness/kundur/probe_state/state_snapshot_latest.json
```

`baseline.json` 现有时, `--promote-baseline` 会先备份到 `baseline.json.bak`.

`--diff` 输出按 section 分组的字段级 changes:
- `[falsification_gates]` G1-G6 verdict 变化
- `[phase4_per_dispatch]` dispatch 数据 delta
- `[implementation_version]` 探针自身算法 bump
- `[schema_version]` snapshot schema bump (这种是大事, 跑 migration)

---

### 5. 跑 pytest 验探针自身没坏

```bash
$PY -m pytest tests/test_state_invariants.py tests/test_probe_internal.py -v
```

期望: **51 PASS / 7 SKIP** (SKIP = phase data absent in latest snapshot;
Type B 设计如此).

任意 **Type A FAIL** = paper FACT 不对 (n_ess≠4 / phi_f≠100 之类) →
**STOP**, 看 build script 改了什么.

---

## 输出怎么读

### `STATE_REPORT_<TS>.md` 顶部速查

```markdown
| Gate                  | Verdict     | Evidence
| G1_signal             | ✅ PASS     | best dispatch 'pm_step_hybrid_sg_es' excites 4 agents > 1 mHz
| G2_measurement        | ✅ PASS     | open-loop omega sha256: 4/4 distinct
| G3_gradient           | ✅ PASS     | 12 of 12 dispatches show non-degenerate per-agent share gradient
| G4_position           | ✅ PASS     | 2 distinct responder signatures across 12 dispatches
| G5_trace              | ✅ PASS     | largest std-diff = 2.127e-03 pu in 'pm_step_proxy_bus9'
| G6_trained_policy     | ✅ PASS     | G6_partial=PASS, R1=PASS; ...
```

**全 PASS** = paper anchor 解锁条件满足.
**任一 REJECT** = 见 `evidence` 字段查具体故障.
**PENDING** = 该 phase 没跑 / 数据不足, 不算失败.

### Phase 4 表 (跑 phase 4 后)

```
| dispatch                   | family       | mag | agents>1mHz | max|Δf| Hz | expected≥ Hz | floor    |
| pm_step_hybrid_sg_es       | hybrid       | 0.5 | 4           | 0.121      | 0.3000       | ⚠️ below |
| pm_step_proxy_g2           | sg_pm_step   | 0.5 | 3           | 0.151      | 0.0500       | ✅       |
```

**`⚠️ below`** = 实测 < `expected_min_df_hz` (历史已知下限). 信号比预期弱
→ 模型可能退化 / build drift. 看 `historical_source` 字段查 floor 来源.

**`⚠️ above`** = 实测 > `expected_max_df_hz` (上限, 仅 F4 hybrid 设了).
runaway divergence / 阻尼崩.

---

## paper-anchor lock 解锁判定

CLAUDE.md hard rule: **G1-G6 全 PASS 才能引 paper 数字 / 跑 PHI sweep**.

跨 snapshot 也可以满足:
- G1-G5 fresh PASS (< 7 day age) 来自 `--phase 1,2,3,4` snapshot
- G6 PASS 来自 `--phase 5,6 --phase-c-mode full` snapshot

写 verdict markdown 引用两份 snapshot 即可 (示例:
`quality_reports/phase_C_R1_verdict_20260501T074245.md`).

---

## 故障排查

### 跑不动 — MATLAB 没启动

```
RuntimeError: matlab.engine not available
```

- 检查 `andes_env` 是不是用对了路径 (CLAUDE.md 限定: 必须用 conda env 完整路径)
- `matlab.engine` 装了吗: `pip install matlabengine`

### Phase 4 全 dispatch error

`paper_eval` 子进程崩, 看 `phase4.dispatches.<name>.error`. 常见:
- MATLAB engine 卡死 → restart MATLAB / 关 .slx 重 launch
- Production train 在跑 → 等它结束 (engine 排他)

### Phase 6 短训不收敛 (no best.pt)

10 ep smoke 大概率 no best.pt — 这是设计 (smoke = plumbing only).
Full mode 200 ep 应出 best.pt; 不出 → check `results/sim_kundur/runs/probe_phase_c_*/training_log.json`
看 NaN / divergence.

### G1 PENDING 不动 — Phase 4 没跑

G1 verdict 需要 `phase4_per_dispatch` 数据. 跑过 `--phase 1,2,3,4` 后才有.
单跑 `--phase 5,6` snapshot 没 G1 数据是预期.

### `--diff baseline latest` 报 baseline 不存在

```
FileNotFoundError: baseline alias unresolved: .../baseline.json does not exist.
Run `python -m probes.kundur.probe_state --promote-baseline <snapshot.json>` to set one.
```

按 hint 跑 `--promote-baseline` 一次即可.

---

## 何时跑 / 何时跳

| 改动 | 跑什么 | wall |
|---|---|---|
| build script (`build_kundur_cvs_v3.m`) | 1,2,3,4 | ~80 s |
| IC JSON re-derive | 2 (足够) | ~1 s |
| dispatch table 加新条目 | 1,4 | ~70 s |
| `config_simulink.PHI_*` 改值 | 5,6 (验 trained policy 仍 healthy) | 5 min smoke / 50 min full |
| trained ckpt 重新 train | 5 | 5 min |
| φ_f reward formulation 改 | 5,6 full | 50 min |
| 探针自身改 (probe_*.py) | pytest only | 0.2 s |
| 啥都没改, 例行 sanity | --diff baseline latest | < 1 s |

---

## 高级 — 6 个 phase 拆开跑

```bash
# 单跑某 phase (前提: 之前已跑过让 phase data 在 snapshot 里)
$PY -m probes.kundur.probe_state --phase 5

# skip MATLAB-bound phase, 只跑 phase 2 (NR/IC 静态)
$PY -m probes.kundur.probe_state --no-mcp

# 改输出目录 (e.g. 实验隔离)
$PY -m probes.kundur.probe_state --phase 1 --output-dir results/harness/kundur/probe_state_exp1
```

注意: Phase 5/6 之间有依赖 (Phase 6 复用 Phase 5 baseline). 推荐
`--phase 5,6` 一次跑, 而不是分两次 (避免 latest snapshot 数据不齐).

---

## 版本 / CHANGELOG

`probes/kundur/probe_state/probe_config.py::IMPLEMENTATION_VERSION` 记当前
探针算法版本. snapshot 也写这个字段. `--diff` 看到 impl_version bump 会
warn — verdict 数值跨版本要看 CHANGELOG (在 `probe_config.py` docstring).

`schema_version` (`probe_state.py::SCHEMA_VERSION`) 是 snapshot **数据格式**
版本. bump 才需要 migration; 当前 = 1.

---

*end — 简单优先, 通用为本.*
