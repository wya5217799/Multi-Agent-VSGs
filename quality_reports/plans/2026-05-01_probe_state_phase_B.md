# Plan: Probe State Phase B — Trained Policy Ablation

**日期:** 2026-05-01
**前置:** Phase A 已完成 (`probes/kundur/probe_state/` 全部 9 step + Type A/B 拆 + self-test)
**设计源:** `docs/design/probe_state_design.md` §6.1
**目的:** 给已有 probe 加 trained-policy ablation phase, 触发 G6 verdict (部分).
**当前会话不执行**, plan 留给新窗口.

---

## 1. 目标 + 通用性约束 (**最重要, 不能违反**)

模型是会动的: KD CVS .slx 重 build / disturbance 表加新条目 / IC 重算 / N_ESS 改 5
都属于"模型修改". 探针 Phase B 必须**不需要改 Python 代码**就能跑过.

| 通用性约束 | 含义 | 反例(禁止) |
|---|---|---|
| **N_ESS 自适应** | ablation 迭代 `range(phase1.n_ess)`, 不写 `range(4)` | hardcode `for i in (0,1,2,3)` |
| **checkpoint discovery** | best.pt 按规则搜, 不写死路径 | `best_pt = "results/.../20260430.../best.pt"` |
| **scenario set 自适应** | 用 `--scenario-set test` 或 manifest 文件名, 跑时再读长度 | hardcode `n_scenarios=50` |
| **paper_eval 当 black-box** | 探针只通过 CLI / JSON 输出消费 paper_eval | 探针自己 reimplement reward 公式 |
| **schema additive** | snapshot.phase5_trained_policy = {...} 新加字段, schema_version=1 不动 | bump schema_version, 破 Phase A invariants |
| **G6 verdict 显式定义** | 在 _verdict.py 写 G6 公式 + 阈值, 跟 G1-G5 一致风格 | 改一改就 G6 结果, 无 verdict logic |
| **read-only** | 不写 base ws / 不改 .slx / 不动 checkpoint | dump 后留垃圾 var; ckpt mutation |
| **fail-soft 多层** | best.pt 缺 / paper_eval crash / 单 ablation fail 各自 skip; phase5 整体 error → Type B SKIP, Type A 仍 PASS | 一处 fail 全 phase 5 红 |

违反任一 = Phase B 通用性破坏, plan 重审.

---

## 2. 范围

**做**:
- `_trained_policy.py` 模块: discover ckpt → 跑 baseline + N+1 ablation runs → 提 metric
- snapshot.phase5_trained_policy 字段 (additive)
- G6 verdict logic + evidence string
- Type B invariants 加 ≥ 2 条 (fail-soft 兼容)
- Phase B self-test 加 ≥ 3 条 (mock paper_eval 输出)

**不做**:
- Phase C 短训 (φ 因果) — 留给 G6 完整版
- Phase D skill 化
- Re-run paper_eval 历史 fixture 数据 (Phase B 用 fresh runs)
- 重 train SAC (probe = read-only)

---

## 3. paper_eval 接口 contract (executor 读这部分)

> **2026-05-01 self-review 修正**: 实际 CLI 跟设计 §6.1 描述有差距, 下表是
> grep verify 过的真实 flag 名 (`evaluation/paper_eval.py` line 716-792).

| flag | 必填 | 用途 | Phase B 用法 |
|---|---|---|---|
| `--checkpoint <path>` | 否 | SAC ckpt 路径; 缺省 = zero-action baseline | baseline / 4 ablation 走 ckpt; zero_all 不传 |
| `--zero-agent-idx <i>` | 否 | 强制 agent i 出零动作 (range guard `[0, env.N_ESS)`) | 0..N_ESS-1 + 不传 (= baseline) |
| `--scenario-set {none,train,test}` | 否 (default `none`) | none=inline 生成器; train/test=manifest | Phase B 默认 `test` (50 ep); smoke = `none` + `--n-scenarios 5` |
| `--n-scenarios <int>` | 否 (default 50) | inline mode 用 (manifest 模式被 manifest 长度覆盖) | smoke 5 / full 50 |
| `--disturbance-mode {bus,gen,vsg,hybrid,ccs_load}` | 否 (default `bus`) | 决定 dispatch 协议族 | **必传 `gen`** 跟 KUNDUR_DISTURBANCE_TYPE 默认 (pm_step_proxy_random_gen) 对齐, 避免 ENV-coupled drift |
| `--seed-base <int>` | 否 (default 42) | 确定性种子 | 探针固定 42, 跑可重现 |
| `--policy-label <str>` | 否 | 标签写进输出 JSON | 传 ablation label (`baseline` / `zero_agent_0` / ...) |
| `--output-json <path>` | **是** | 单一 JSON 落盘路径 | `tmp_out / f"{label}.json"` |

**注意**: 没有 `--out-dir`. 是 `--output-json` 单文件路径. 探针自己拼 6 个不同
路径.

**输出 JSON schema** (sed verify line 670-707):

```jsonc
{
  "checkpoint_path": "...",
  "policy_label": "...",
  "n_scenarios": int,
  "cumulative_reward_global_rf": float,    // = "cum_unnorm" 在 paper anchor
  "summary": {...},
  "per_episode_metrics": [
    {
      "scenario_idx": int,
      "r_f_global_unnormalized": float,    // per-ep r_f
      "r_h_total": float,                  // per-ep r_h
      "r_d_total": float,                  // per-ep r_d
      "max_freq_dev_hz": float,
      "r_f_global_per_agent": [float * n_agents],
      ...
    }
  ],
  ...
}
```

探针消费这 4 个字段:
1. `cumulative_reward_global_rf` → r_f_global per run
2. `sum(per_episode_metrics[*].r_h_total)` → r_h_global per run (探针自己 sum)
3. `sum(per_episode_metrics[*].r_d_total)` → r_d_global per run
4. `per_episode_metrics[*].r_f_global_per_agent` → 用于 baseline `rf_rh_rd_share`

**调用模式** (subprocess):

```python
out_json = tmp_out / f"{label}.json"
cmd = [
    PY, "-m", "evaluation.paper_eval",
    "--scenario-set", scenario_set,    # 'test' or 'none'
    "--n-scenarios", str(n_scenarios), # 仅 none 模式生效
    "--disturbance-mode", "gen",
    "--seed-base", "42",
    "--policy-label", label,
    "--output-json", str(out_json),
]
if ckpt_path is not None:                 # zero_all run = 不传 --checkpoint
    cmd += ["--checkpoint", str(ckpt_path)]
if zero_idx is not None:
    cmd += ["--zero-agent-idx", str(zero_idx)]
subprocess.run(cmd, timeout=900, check=False)
```

不用 import paper_eval 内部 (subprocess 隔离 → MATLAB engine 独立 → 一个 ablation
crash 不影响下一个; 也保证 base ws 不污染 — 子进程 MATLAB 独立).

---

## 4. Phase 范围 (本 plan 只做 Phase B; G6 部分)

设计 §6.1 给 1 hr 太乐观. 实际:
- 1 sim wall ≈ 2-3 min (含 cold start 摊销)
- 6 ablation runs (baseline + N=4 zero-i + zero-all) × 5 ep smoke = ~20 min
- 6 ablation × 50 ep full = ~3 hr **(prod mode)**

本 plan **smoke 默认** (5 ep), full 用 `--phase-b-mode full` flag.

---

## 5. 实施 Step 清单

### Step 0 — Prerequisite check (~15 min, MUST 先跑)

确认设计假设还成立, 跟 Phase A Step 0 同结构:

- [ ] paper_eval `--zero-agent-idx` flag 存在 (`grep -n "zero_agent" evaluation/paper_eval.py`)
- [ ] paper_eval `--scenario-set` 接受 `test`
- [ ] `scenarios/kundur/scenario_sets/v3_paper_test_50.json` 存在
- [ ] 至少 1 个 best.pt 存在 (find results/{harness,sim_kundur} -name best.pt) → 选最新匹配 v3 的
- [ ] paper_eval 输出 JSON 有 r_f_global / cum_unnorm 字段 (跑 1 次 zero-action baseline 5 ep verify)

任一 fail → STOP, plan 重审 (不要"自动 fallback").

**成果**: 一份 `phase_B_prerequisites.md` 记录 ckpt 选哪个 + 为什么.

---

### Step 1 — `_trained_policy.py` 骨架 (~30 min)

新建 `probes/kundur/probe_state/_trained_policy.py`. 公开 entry point:

```python
def run_trained_policy_ablation(probe: "ModelStateProbe") -> dict[str, Any]:
    """Phase 5: ablation sweep. Returns snapshot.phase5_trained_policy dict."""
```

模块内部职责:
- `_discover_checkpoint()` — search rule, 返 Path or None
- `_run_paper_eval(ckpt, label, zero_idx, scenario_set, n_scenarios, out_dir) -> dict`
- `_extract_metrics(eval_json) -> dict` (action_mean, r_f_global, r_h_global, r_d_global)
- `_compute_ablation_diffs(baseline, ablations) -> dict`

接到 orchestrator:
- `probe_state.py::ModelStateProbe.run` 加 phase 5 (after phase 4)
- `__main__.py --phase` 接受 `5`
- `__main__.py --phase-b-mode {smoke,full}` 控制 ep 数

**验收**:
- [ ] `--help` 列出 `--phase 5` 跟 `--phase-b-mode`
- [ ] `--phase 5 --no-mcp` 跑 → fail-soft skip (无 MATLAB → ckpt eval 不可能, 全 skip)
- [ ] phase5_trained_policy 字段 schema_version 仍 = 1

---

### Step 2 — checkpoint discovery (~30 min)

**通用性核心**. 不 hardcode 路径.

#### 选择规则 (按优先级)

```
1. CLI override:  $PY -m probes.kundur.probe_state --checkpoint <path>
2. ENV override:  KUNDUR_PROBE_CHECKPOINT=<path>
3. Auto-search:   按下列规则在 results/ 树下查
```

#### Auto-search (返第一个匹配)

```python
search_roots = [REPO_ROOT / "results/harness/kundur",
                REPO_ROOT / "results/sim_kundur/runs",
                REPO_ROOT / "results/sim_kundur/archive"]
for root in search_roots:
    candidates = sorted(root.rglob("best.pt"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    for cand in candidates:
        if not _checkpoint_matches_active_profile(cand):
            continue   # 跳 v2 / NE39 ckpt
        return cand
return None  # → fail-soft skip
```

#### `_checkpoint_matches_active_profile`

ckpt 旁边一般有 `training_log.npz` 或 run-time meta. 比较 obs_dim / act_dim
跟 `phase1_topology.config` (M0/D0/n_ess). 不一致 → 跳 (那是给别的拓扑训的).

实在没办法对齐 → 走 ckpt 名字含 `cvs_v3` 或 `kundur_simulink` 的 path filter.

**验收**:
- [ ] 现仓库现有 ckpt 中找到 ≥ 1 个 (有 best.pt 的 = 多条)
- [ ] 模型 N_ESS 改 5 (假想) → discover 仍跑 (不 hardcode 4)
- [ ] CLI override 比 auto-search 优先 (test: 传任意 path → snapshot 写它)
- [ ] 找不到 → snapshot.phase5_trained_policy = `{"error": "no_matching_checkpoint", ...}`, 不 raise

---

### Step 3 — Ablation 跑法 (~45 min)

#### Run matrix (N+2 runs, N = phase1.n_ess)

| label | --zero-agent-idx | 含义 |
|---|---|---|
| `baseline` | (none) | trained policy 不 zero |
| `zero_agent_0` | 0 | agent 0 出零动作 |
| ... | ... | ... |
| `zero_agent_{N-1}` | N-1 | agent N-1 出零动作 |
| `zero_all` | (special) | 跑 paper_eval 不带 --checkpoint = 全零 baseline |

`N+2` runs total (KD: 6 runs).

#### Smoke vs full

| mode | scenario-set | n_scenarios | 估算 wall |
|---|---|---|---|
| smoke (default) | none | 5 | ~15 min |
| full | test | 50 (manifest 长度) | ~3 hr |

#### 串行执行, 单点 fail-soft

每个 run 自己一个 try/except. 任一 run fail → 该 run 写 `{"error": ...}`, 其他 run
继续. 全 fail → phase5 整体 error.

```python
for label, zero_idx in run_matrix:
    try:
        eval_json = _run_paper_eval(ckpt, label, zero_idx, scenario_set, n, tmp_out)
        runs[label] = _extract_metrics(eval_json)
    except Exception as exc:
        logger.warning("ablation %s FAILED: %s", label, exc)
        runs[label] = {"error": f"{type(exc).__name__}: {exc}"}
```

**验收**:
- [ ] smoke run 跑出 N+2 个 sub-result
- [ ] 杀掉 1 个 ablation run mid-flight (Ctrl-C 测 wrapper) → 其他 run 不受影响
- [ ] 单 ablation timeout (paper_eval >900s) → run 标 timeout, 其他继续

---

### Step 4 — Metric 公式 + ablation_diffs (~30 min)

每 run 提:

| metric | 公式 (与 §3 字段名对齐) | 来源 |
|---|---|---|
| `r_f_global` | paper_eval JSON `cumulative_reward_global_rf` | paper §IV-C / paper_eval line 564 |
| `r_h_global` | `sum(per_episode_metrics[*].r_h_total)` (探针自 sum) | paper_eval line 692 |
| `r_d_global` | `sum(per_episode_metrics[*].r_d_total)` | paper_eval line 693 |
| `action_mean` | paper_eval **不直接 dump 动作 trace**; Phase B v1 写 None, 留 placeholder | (未来 Phase B' 接入) |

**注意**: `action_mean` 是设计文档 §6.1 列的字段, 但 paper_eval 当前不输出 raw
action 序列. Phase B v1 写 `None` 或缺字段, 不阻塞 G6 verdict (G6 只用 r_f_global
+ ablation_diffs). 真要 action_mean → 后续给 paper_eval 加 `--dump-actions` flag,
另起 plan.

`ablation_diffs` = per-agent improvement attribution:

```
# r_f 是负 reward (paper §IV-C: r_f = -Σ_t Σ_i Δf². 越接近 0 越好)
# zero_agent_i 把 i 拉成 no-control, 通常 r_f 更负 ⇒ diff < 0
ablation_diffs[i] = r_f_global(zero_agent_i) - r_f_global(baseline)
                    # i 越重要, ablation_diffs[i] 越**负** (绝对值越大)
```

`agent_contributes[i]` = `ablation_diffs[i] < -NOISE_THRESHOLD` (默认 NOISE = 1e-3 sys-pu²;
负方向阈值 = i 的贡献显著降级 baseline).

边界: 若 zero_i 反而比 baseline 好 (`diff > 0`), agent_contributes[i] = False
(不算贡献; 这种情况通常说 i 学坏 / 过 active).

`rf_rh_rd_share` = baseline 的 `(|r_f|, |r_h|, |r_d|) / (|r_f| + |r_h| + |r_d|)` 三分量比 (用绝对值
因为 r_f/r_h/r_d 都 ≤ 0 而 share 想表达"哪个项主导 reward").

不 hardcode 公式数字以外的项 — N (= len(ablation_diffs)) = phase1.n_ess.

**验收**:
- [ ] N=4 时 ablation_diffs 4 个值, N=5 假想模型自动出 5 个
- [ ] 单 run error → 该 i 的 diff = None, 不 raise
- [ ] phase5 输出含 baseline + N+1 runs metric + ablation_diffs + agent_contributes (bool list)

---

### Step 5 — G6 verdict 定义 (~20 min)

**G6 = "trained policy 真实使用 ≥ K 个 agent (= 不退化为 ES1-mimic)"**

| Verdict | 条件 (r_f 是负 reward, 越大越好) | 含义 |
|---|---|---|
| PASS   | `sum(agent_contributes) >= K` AND `baseline.r_f_global > zero_all.r_f_global + IMPROVE_TOL` | policy 用 ≥ K agent + 比全零基线显著好 |
| REJECT | `sum(agent_contributes) < K` OR `baseline.r_f_global - zero_all.r_f_global <= IMPROVE_TOL` | policy 退化 / 没学到 |
| PENDING | ckpt 缺 / baseline 或 zero_all 缺 / phase5 总错 | 信息不足 |

阈值 (写成 phase5 字段方便回溯, NOT hardcode 在 verdict logic 里):
- `K = 2` — 跟 G1 (≥ 2 agents responding) 同风格
- `NOISE_THRESHOLD = 1e-3` sys-pu² — agent_contributes 触发线
- `IMPROVE_TOL = 0.5` sys-pu² 绝对值 (r_f 量级 ~-15 时 0.5 ≈ 3%; 项目历史
  baseline ≈ -16 vs zero_all ≈ -15.20 → diff ≈ -0.8, 在 tol 边缘 → 跟历史观察
  一致, REJECT 的可能性高 — 这就是探针目的, 不是 bug)

加到 `_verdict.py::compute_gates`, 跟 G1-G5 同 style (verdict / evidence / extras).

**验收**:
- [ ] _verdict.py 有 `_g6_trained_policy(snap)` 函数
- [ ] phase5 缺时 verdict = PENDING (不 raise)
- [ ] canned snapshot 测 (test_probe_internal): 4 agent contribute → PASS, 1 contribute → REJECT
- [ ] G6 写入 `falsification_gates.G6_trained_policy`

---

### Step 6 — Snapshot schema 加 phase5 (~15 min)

```jsonc
"phase5_trained_policy": {
  "checkpoint_path": "results/.../best.pt",     // 实际选中的路径
  "checkpoint_mtime": "2026-04-30T01:54:48",
  "checkpoint_match_strategy": "auto-search v3 path filter",
  "mode": "smoke",                              // 'smoke' | 'full'
  "scenario_set": "none",                       // 'none' | 'train' | 'test'
  "n_scenarios": 5,                             // 实际跑的数 (manifest 模式 = 长度)
  "disturbance_mode": "gen",                    // CLI 传给 paper_eval
  "n_agents": 4,                                // = phase1.n_ess
  "noise_threshold_sys_pu_sq": 1e-3,
  "runs": {
    "baseline":     {"r_f_global": float, "r_h_global": float, "r_d_global": float, "action_mean": null},
    "zero_agent_0": {...},
    "zero_agent_1": {...},
    "zero_agent_2": {...},
    "zero_agent_3": {...},
    "zero_all":     {...}
  },
  "ablation_diffs":    [float | null] * n_agents,   // null = 该 run errored
  "agent_contributes": [bool | null]  * n_agents,
  "rf_rh_rd_share":    {"rf": float, "rh": float, "rd": float},   // baseline 三分量比
  "errors": [/* per-run error tags */]
}
```

`schema_version` 顶层不变 (= 1). 字段 additive.

`_report.py` 加 phase 5 section (跟 phase 1-4 同 style: error / not_run / 表).

**验收**:
- [ ] state_snapshot_latest.json 出 `phase5_trained_policy` 键
- [ ] STATE_REPORT_*.md 显示 G6 + ablation table
- [ ] schema_version still == 1
- [ ] phase 1-4 字段 binary identical (只加新键, 不改老键)

---

### Step 7 — Type B invariants ≥ 2 条 (~20 min)

加在 `tests/test_state_invariants.py`:

```python
@pytest.mark.typeB
def test_typeB_phase5_ablation_signal_nontrivial(snap):
    """G6 PASS 条件最小检查: 任一 ablation diff > NOISE."""
    p5 = snap.get("phase5_trained_policy") or {}
    if "error" in p5 or not p5:
        pytest.skip("phase5 not run / errored")
    diffs = [d for d in p5.get("ablation_diffs", []) if d is not None]
    if not diffs:
        pytest.skip("no successful ablation runs")
    NOISE = p5.get("noise_threshold_sys_pu_sq", 1e-3)
    assert max(abs(d) for d in diffs) > NOISE, (
        f"all ablation diffs below noise floor {NOISE}: {diffs}"
    )

@pytest.mark.typeB
def test_typeB_g6_decided(snap):
    """phase5 跑过 → G6 verdict 不 PENDING."""
    p5 = snap.get("phase5_trained_policy") or {}
    if "error" in p5 or not p5 or not p5.get("runs"):
        pytest.skip("phase5 not run / no runs data")
    g6 = (snap.get("falsification_gates") or {}).get("G6_trained_policy", {})
    assert g6.get("verdict") in {"PASS", "REJECT"}, (
        f"G6 should be decided when phase5 has runs data: {g6!r}"
    )
```

**禁止**: 不要在 Type A 加 G6 相关 assert (G6 依赖 trained policy state, 不是 paper FACT).

**验收**:
- [ ] 文件 ≥ 5 Type A + ≥ 5 Type B (Phase A 5+3 + Phase B +2)
- [ ] phase5 缺时全 SKIP (不 FAIL)
- [ ] phase5 跑过时 G6 PASS / REJECT 都触发 typeB_g6_decided PASS

---

### Step 8 — Phase B self-test (~20 min)

加在 `tests/test_probe_internal.py`:

```python
def test_phase_b_checkpoint_discovery_returns_none_on_empty_repo(tmp_path, monkeypatch):
    """无 ckpt 时 _discover_checkpoint() 返 None, 不 raise."""

def test_phase_b_ablation_diffs_per_agent_count_matches_n_ess():
    """canned: phase5 输出 ablation_diffs 长度 == phase1.n_ess (通用性)."""

def test_phase_b_g6_verdict_pass_on_4_contributors():
    """canned snapshot, 4 agents 都 contribute, G6 = PASS."""

def test_phase_b_g6_verdict_reject_on_1_contributor():
    """canned snapshot, 只 1 agent contribute, G6 = REJECT."""

def test_phase_b_g6_verdict_pending_when_phase5_missing():
    """phase5 缺 → G6 PENDING."""
```

纯 Python mock (paper_eval JSON 替换为字典). 不 launch MATLAB.

**验收**:
- [ ] ≥ 5 test, 全 PASS
- [ ] 不 trigger MATLAB cold start

---

### Step 9 — End-to-end smoke + self-review (~30 min)

```bash
$PY -m probes.kundur.probe_state                            # phase 1-5 smoke (~20 min)
$PY -m pytest tests/test_state_invariants.py tests/test_probe_internal.py -v
```

**验收** (跟 Phase A 同语义, Type A all PASS / Type B SKIP-not-FAIL):
- [ ] 总 wall < 60 min smoke / < 4 hr full
- [ ] schema_version still == 1
- [ ] phase1-4 输出跟 Phase A baseline binary identical (除 timestamp / git_head)
- [ ] phase5_trained_policy 含 ≥ 6 runs entries (baseline + N+1 ablation + zero_all)
- [ ] G6 verdict ∈ {PASS, REJECT, PENDING}, 评估有 evidence 字符串
- [ ] Type A all PASS (5/5)
- [ ] Type B SKIP-or-PASS, 无 FAIL
- [ ] 无 base ws 残留 (跑前后 `evalin('base', 'who')` 无新 var; 由 paper_eval subprocess 保证 — 子进程退出后 MATLAB workspace 不污染父探针 session)
- [ ] git diff 仅 probes/kundur/probe_state/, tests/, 可选 results/harness/kundur/probe_state/

---

## 6. 失败信号 + 中止条件

| 信号 | 含义 | 行动 |
|---|---|---|
| 全 ckpt search 返 None | repo 没 trained ckpt 或 active profile 改了 | snapshot.phase5 = error, Type B SKIP. NOT 中止 (probe 仍可用 phase 1-4) |
| paper_eval 跑 > 900s | env init 卡死 / 单 ep 死循环 | timeout=900 → 该 run skip, 其他继续 |
| ablation_diffs 全 ≈ 0 | 已知历史: trained policy 退化 | G6 = REJECT (非中止 — 这就是探针目的) |
| phase5 全 run error | paper_eval crash 系统性 | snapshot.phase5.error, G6 PENDING. STOP, 调 paper_eval 再 retry |
| G6 PASS 但 Type A FAIL | paper FACT 不一致 | 跟 G6 verdict 无关. STOP, 看 build script |
| schema_version != 1 | 字段不是 additive 加的 | 错改了 schema. revert |

---

## 7. References (executor 必读)

| 文件 | 用途 |
|---|---|
| `docs/design/probe_state_design.md` §6.1 | Phase B 设计源 |
| `evaluation/paper_eval.py` line 719-760 | --checkpoint / --zero-agent-idx / --scenario-set CLI |
| `evaluation/paper_eval.py` line 619-680 | 输出 JSON schema |
| `scenarios/kundur/scenario_sets/v3_paper_test_50.json` | full mode scenario manifest |
| `probes/kundur/probe_state/_verdict.py` | G1-G5 风格参考, G6 加这里 |
| `probes/kundur/probe_state/_dynamics.py` | fail-soft 写法参考 |
| `tests/test_state_invariants.py` | Type A/B 拆法参考 |
| `results/harness/kundur/cvs_v3_*/` | 现有 best.pt 候选 |

---

## 8. 时间预算 (含 +50% buffer)

| Step | 净估 | 含 buffer |
|---|---|---|
| 0 prereq | 15 min | 25 min |
| 1 骨架 | 30 min | 45 min |
| 2 ckpt discovery | 30 min | 45 min |
| 3 ablation runner | 45 min | 70 min |
| 4 metric 公式 | 30 min | 45 min |
| 5 G6 verdict | 20 min | 30 min |
| 6 schema | 15 min | 25 min |
| 7 invariants | 20 min | 30 min |
| 8 self-test | 20 min | 30 min |
| 9 smoke (smoke mode) | 30 min | 45 min |
| **总** | **~4.25 hr** | **~6.5 hr** |

设计 §6.1 估的 1 hr 不切实际 — 但 6.5 hr 已含 fresh-window cold-start + bug fix.

full mode (50 ep) 额外 +3 hr 跑时间, 不在本 plan 接受 — 走单独 launcher.

---

## 9. 设计 self-review (写完一遍后跑一次)

- [ ] 没有 `n_agents = 4` / `for i in (0,1,2,3)` 等 hardcode (grep verify)
- [ ] checkpoint path 不在 Python 代码字符串里 (grep `\.pt['\"]` 全文应只在 fixture / test mock)
- [ ] phase5 字段全 additive, schema_version still == 1
- [ ] G6 verdict 跟 G1-G5 同 verdict struct (verdict / evidence / extras)
- [ ] paper_eval 调用走 subprocess, 不 import 内部
- [ ] fail-soft 三层: ckpt 缺 / single run / phase5 总 — 都有路径
- [ ] Type A 不被 Phase B 改 (Phase A invariants 全 PASS)
- [ ] 不写 base ws / 不动 .slx / 不 mutate ckpt

self-review 任一 fail → 不算完成, 返修.

---

## 10. 完成后下一步 (不在本 plan)

- 跑 full-mode (50 ep) 拿稳数 → 写一份 verdict markdown
- 用 G6 PASS/REJECT 状态决定要不要 Phase C (因果短训) 解锁 paper anchor
- Phase D skill 化 (跑 ≥ 3 次后)

---

## 11. 通用性回归测试 (Phase B 完成时)

确认 KD CVS 修改后 probe 仍能跑. 模拟"模型改"的几种情况:

| 模拟改动 | 预期 probe 行为 |
|---|---|
| `KUNDUR_MODEL_PROFILE` 切到假想 v4 (n_ess=5) | phase1 报 n_ess=5; phase5 ablation 跑 5+2=7 runs; G6 仍工作 |
| 删全部 `best.pt` (从 results/) | phase1-4 PASS; phase5 = error: no checkpoint; G6 = PENDING; Type B SKIP |
| `disturbance_protocols._DISPATCH_TABLE` 加新条目 | phase1 自动多 1; dispatch_metadata coverage_check FAIL → self-test 提示加 metadata |
| 改 paper_eval `--zero-agent-idx` 默认或参数名 | Phase B Step 0 prereq fail → STOP rebuild |

写一份 `tests/test_phase_b_generality.py` (可后置) 跑这 4 case (前 3 case 用 monkeypatch /
环境变量, 第 4 case 是手动 prereq).

**Phase B 完成定义** = Step 1-9 通过 + §11 4 case 中至少前 3 case 验过.

---

*end of plan — keep simple, keep generic*
