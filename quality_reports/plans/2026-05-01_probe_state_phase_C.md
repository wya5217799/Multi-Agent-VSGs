# Plan: Probe State Phase C — Causality Short-Train (R1)

**日期:** 2026-05-01
**前置:** Phase A + B 已完成 (probe + G1-G6 verdict 全 wired up)
**设计源:** `docs/design/probe_state_design.md` §6.2
**目的:** 触发 G6 完整 verdict, 验 r_f penalty 是 trained-policy improvement 的**因果驱动**而非 spurious (R1 反证)
**当前会话不执行**, plan 留给新窗口.

---

## 1. 范围 (跟设计 §6.2 一致, 不扩展)

设计 §6.2 写的是 **"200 ep × 2 配置 (φ_f=100 vs 0)"**. 这是 R1 only — 测 r_f
penalty 是不是 driver. R2 / R3 (φ_h / φ_d 同款 ablation train) **deferred 到
Phase C v2**, 单独 plan, 不在本 plan scope.

理由:
- Phase C v1 (R1) 已经 ~1 fresh train × 200 ep × ~5-15 min/ep wall = ~20-50 hr
- R2 + R3 各 1 fresh train = 再加 ~40-100 hr = unmanageable in single sweep
- R1 PASS / REJECT 信号决定是否继续 R2/R3 — 先收敛 R1 再说

**做**:
- 1 fresh train: φ_f=0 (φ_h, φ_d 保持 default 5e-4)
- baseline 复用 Phase B auto-discovered ckpt (φ_f=100 production)
- eval 两 ckpt 用 paper_eval, 5 ep smoke / 50 ep full
- G6 完整 verdict logic
- snapshot.phase6_causality 字段 (additive, schema_version=1 不动)
- ≥ 2 Type B invariants
- ≥ 3 self-test (mock train output)

**不做**:
- R2 / R3 (φ_h=0 / φ_d=0 train) — Phase C v2
- φ_f=0 + φ_h=0 + φ_d=0 联合 train (ablation matrix 爆炸)
- 任何修改 SAC code / reward formula / config defaults
- 替换或修改 production ckpt
- Phase D skill 化

---

## 2. 通用性约束 (**最重要, 不能违反**)

跟 Phase B 同 caveat: KD CVS 模型 / config / 训练脚本 任意改动后, Phase C
探针仍能跑.

| 约束 | 含义 | 反例(禁止) |
|---|---|---|
| **N_ESS 自适应** | eval 走 paper_eval, n_agents 来自 ckpt | hardcode `n_agents=4` 在 verdict |
| **PHI control = ENV var** | 通过 `KUNDUR_PHI_F=0` ENV 走, 不改 config_simulink | 写一个 special config 覆盖 PHI_F |
| **Run dir = `--run-id` flag** | train 输出 isolated, 不动 production | 写到 `results/sim_kundur/runs/` 默认根 |
| **train script 当 black-box (CLI 接口可扩展)** | subprocess + CLI; 不 import 内部. CLI 层 1-2 行 `--run-id` 加 fallback 是 OK 的 (接口扩展非逻辑改) | `from scenarios.kundur.train_simulink import main`; 改 reward / SAC update / loss |
| **paper_eval 复用 Phase B** | 同一调用 wrapper, 同一 JSON schema | reimplement metric extraction |
| **schema additive** | snapshot.phase6_causality 加, schema_version=1 不动 | bump schema |
| **G6 完整 = 复合 verdict** | combine G6-部分 (Phase B) + R1 verdict | 单 R1 替代 G6, 破 Phase B 兼容 |
| **read-only on production** | 不改 production ckpt; 不删 results/ 现有 run | accidentally `--resume` production ckpt |
| **fail-soft 多层** | train fail / eval fail / NaN / OOM 各自 SKIP | 一处 fail 全 phase 6 红 |
| **paper-anchor lock 守门** | G1-G6 不全 PASS 时拒绝跑 (CLAUDE.md hard rule) | 强行启动 train ignore lock |

违反任一 = Phase C 通用性破坏, plan 重审.

---

## 3. R1 数学定义 (设计 §6.2 没明写, 这里 derive)

**R1 假设**: trained policy 的 r_f_global improvement 来自 r_f penalty 的训练梯度.

**R1 反证条件 (REJECT)**: φ_f=0 训出的 ckpt 在 eval 时 r_f_global ≈ baseline (φ_f=100)
ckpt 的 r_f_global → r_f penalty 不是 driver, improvement 是 spurious / 巧合.

**R1 PASS 公式**:
```
r_f(no_rf) - r_f(baseline) > IMPROVE_TOL_R1
```
- `r_f(no_rf)` = paper_eval 跑 φ_f=0 ckpt 的 cumulative_reward_global_rf.unnormalized
- `r_f(baseline)` = paper_eval 跑 φ_f=100 ckpt 的同字段 (= Phase B baseline run)
- r_f 是负 reward, 越接近 0 越好. PASS = no_rf 显著差 (= 没 r_f penalty 学不出 r_f improvement)
- `IMPROVE_TOL_R1 = 0.5` sys-pu² (跟 Phase B G6 IMPROVE_TOL 同量级)

**R1 PENDING**: ckpt_no_rf 缺 (train fail) 或 baseline 缺 (Phase B 未跑过).

**G6 完整 verdict** (Phase C 完成后替代 Phase B G6-部分):
```
G6_complete = G6_partial(Phase B) AND R1
```
- 任一 REJECT → G6 整体 REJECT
- 任一 PENDING → G6 PENDING
- 都 PASS → G6 完整 PASS

具体 evidence 字段:
- `g6_partial_verdict`: PASS/REJECT/PENDING 复制自 Phase B
- `r1_verdict`: PASS/REJECT/PENDING from this plan
- `improvement_no_rf_minus_baseline`: 数值

---

## 4. PAPER-ANCHOR LOCK 守门 (硬阻塞)

用户 CLAUDE.md hard rule: **G1-G6 verdict 不全 PASS 的状态下禁启动 PHI sweep**.

φ_f=0 train **字面是 PHI sweep**, 红区. Phase C Step 0 必须 verify:

```python
fresh_verdicts_required = {"G1", "G2", "G3", "G4", "G5"}  # G6 自己就是 Phase C target
for g in fresh_verdicts_required:
    v = snap['falsification_gates'][g]
    assert v['verdict'] == 'PASS', f"{g} not PASS — paper-anchor lock blocks Phase C"
```

不可绕过. 当前状态 (Phase B smoke 后):
- G1 PENDING (phase 4 未全)
- G2 PASS ✅
- G3 PENDING (phase 4 未全)
- G4 PENDING (phase 4 未全)
- G5 PASS ✅
- G6 PASS (Phase B-部分)

**Phase C 启动前必须先跑 Phase 4 全 dispatch sweep, 让 G1/G3/G4 决断**. 这是 plan
Step 0 第 1 项.

若 G1/G3/G4 任一 REJECT → paper-anchor lock 状态恶化 → Phase C 跑也无意义 →
STOP, 重审 model integrity.

---

## 5. Run-dir 隔离 (通用性核心)

Phase C 跑 1 fresh train, 占 MATLAB engine ~小时级. 不能污染 production.

### 隔离机制 — D-minimal CLI flag

**Step 0 finding (2026-05-01):** train_simulink.py 原本不接 `--run-id` (line 223
强制 `args.run_id = generate_run_id(...)` 覆盖任何外部输入). 评 4 个隔离方案 (A
ENV var / B post-rename / C metadata-only / D-minimal CLI flag), **选 D-minimal**:
2 行 train_simulink.py 改 (`parser.add_argument("--run-id", default=None)` + fallback
`args.run_id = args.run_id or generate_run_id(...)`). 见 `phase_C_prerequisites.md`.

理由:
- 语义最干净 (run_id 是启动参数, 走 argparse)
- 默认行为 100% 兼容 (production launcher 不传 → fallback to 原 generate_run_id)
- 影响面最小 (仅 Kundur train_simulink.py; NE39 / standalone 不动)
- 工程审计 (`ps` / shell history 留 `--run-id <X>` 显式记录)
- 不破 plan §2 边界: CLI 接口扩展 ≠ train 逻辑改动

### Phase C train 命令模板

```bash
PY=...andes_env/python.exe
KUNDUR_PHI_F=0  $PY scenarios/kundur/train_simulink.py \
    --mode simulink \
    --episodes 200 \
    --run-id "probe_phase_c_no_rf_20260501T060000" \
    --seed 42 \
    --resume none
# 输出: results/sim_kundur/runs/probe_phase_c_no_rf_20260501T060000/
```

### Run-id naming convention

`probe_phase_c_<config_label>_<UTC_TS>`:
- `config_label` ∈ {`no_rf`, `no_rh` (Phase C v2), `no_rd` (Phase C v2)}
- `UTC_TS` = `YYYYMMDDTHHMMSS`

后续清理 / archive 走 path-prefix glob `probe_phase_c_*` (区别 production
`kundur_simulink_*` 命名).

### Production 隔离保证

- **不 `--resume` 任何 production ckpt** (`--resume none` 强制 fresh start)
- **不 reuse production scenario_sets** (用默认 random per-episode 即可,
  paper_eval eval 时再用 fixed seed)
- **不修改 production config 文件** (PHI 走 ENV, 不改 .py)
- **不传 `--run-id` 时行为完全不变**: 默认 `args.run_id = None or
  generate_run_id(...)` = 走原 auto-gen 路径 (verified 已有 launchers 不破)

---

## 6. 实施 Step 清单

### Step 0 — Prerequisite + paper-anchor lock check (~30 min, MUST 先跑)

3 项必须 PASS:

1. **paper-anchor gate** (§4):
   ```bash
   $PY -m probes.kundur.probe_state --phase 4
   ```
   读 latest snapshot, 校 G1/G2/G3/G4/G5 全 PASS. 任一非 PASS → STOP.

2. **train script API stable**:
   ```bash
   $PY scenarios/kundur/train_simulink.py --help  # 必含 --run-id, --episodes, --resume, --seed
   ```
   缺任一 flag → train_simulink.py 改了 API → STOP, plan 重审.

3. **PHI ENV var control verified** (现 grep 已 verify, runtime 再 sanity):
   ```bash
   KUNDUR_PHI_F=0 $PY -c "from scenarios.kundur.config_simulink import PHI_F; assert PHI_F == 0.0"
   ```

**成果**: `quality_reports/phase_C_prerequisites.md` 记 ckpt baseline path,
G1-G5 fresh verdict snapshot path, train_simulink.py git rev.

---

### Step 1 — `_causality.py` 骨架 (~30 min)

新建 `probes/kundur/probe_state/_causality.py`. 公开 entry:

```python
def run_causality_short_train(probe: "ModelStateProbe") -> dict[str, Any]:
    """Phase 6 — R1 ablation: train phi_f=0 ckpt, eval, compare to baseline."""
```

模块内部:
- `_run_short_train(config_label, phi_f, episodes, run_id) -> Path | None` (subprocess)
- `_eval_ckpt(ckpt, n_scenarios) -> dict | None` (复用 Phase B `_run_paper_eval`)
- `_compute_r1_verdict(baseline_eval, no_rf_eval) -> dict`
- `_resolve_baseline_eval(probe) -> dict | None` — 复用 Phase B phase5 baseline run output

接到 orchestrator:
- `probe_state.py::ALL_PHASES = (1,2,3,4,5,6)`
- `__main__.py --phase` 接受 `6`
- `__main__.py --phase-c-mode {smoke,full}` (smoke ep=10 仅做 plumbing 测试 NOT
  causal signal; full ep=200 是真正的因果短训)
- `__main__.py --phase-c-baseline-eval-from-snapshot` (默认 True — 复用 Phase B
  跑过的 baseline eval; 否则现跑 1 个 baseline eval)

**验收**:
- [ ] `--help` 列出 `--phase 6`, `--phase-c-mode`
- [ ] `--phase 6 --no-mcp` → fail-soft skip (无 MATLAB)
- [ ] schema_version 仍 = 1

---

### Step 2 — Short-train wrapper (~45 min)

#### subprocess 调用 (利用现有 CLI, 不改 train_simulink.py)

```python
def _run_short_train(
    *, config_label: str, phi_f: float, phi_h: float, phi_d: float,
    episodes: int, run_id: str, seed: int = 42,
    timeout_s: int = 86400,  # 24 hr ceiling for one short-train
) -> Path | None:
    env = {**os.environ,
           "KUNDUR_PHI_F": str(phi_f),
           "KUNDUR_PHI_H": str(phi_h),
           "KUNDUR_PHI_D": str(phi_d)}
    cmd = [sys.executable, "scenarios/kundur/train_simulink.py",
           "--mode", "simulink",
           "--episodes", str(episodes),
           "--run-id", run_id,
           "--seed", str(seed),
           "--resume", "none"]
    result = subprocess.run(cmd, env=env, cwd=REPO_ROOT, ..., timeout=timeout_s)
    if result.returncode != 0:
        return None
    # Find best.pt under run_dir; if None, train didn't converge to checkpoint
    run_dir = REPO_ROOT / "results/sim_kundur/runs" / run_id
    best = run_dir / "checkpoints" / "best.pt"
    return best if best.exists() else None
```

#### Smoke vs Full

| mode | episodes | 估算 wall (Kundur Simulink, single fresh train) |
|---|---|---|
| smoke (default) | 10 | ~30-60 min (plumbing test only — 不出因果 signal) |
| full | 200 | ~10-50 hr (设计 §6.2; 真正 R1 信号) |

**fail-soft**:
- subprocess returncode ≠ 0 → 跳过 train, 标 `train_failed`, R1 = PENDING
- best.pt 不存在 (train 不收敛 / NaN) → 同上
- timeout 24 hr → 同上

**验收**:
- [ ] smoke mode 跑通 (10 ep ~30-60 min wall, 输出 best.pt 或文件 logged not converged)
- [ ] run_dir = `probe_phase_c_no_rf_<TS>` (可 grep verify)
- [ ] train fail 不 raise, snapshot.phase6 包 error 字段
- [ ] **不动** production `results/sim_kundur/runs/kundur_simulink_*/` (git diff 验)

---

### Step 3 — Eval wrapper + R1 公式 (~30 min)

复用 Phase B `_trained_policy._run_paper_eval` (subprocess + JSON parse).

```python
def _eval_ckpt(ckpt_path: Path, n_scenarios: int = 5) -> dict[str, Any]:
    # exact same shape as Phase B baseline run
    from probes.kundur.probe_state._trained_policy import _run_paper_eval, _RunSpec, _extract_metrics
    spec = _RunSpec(label="phase_c_no_rf", zero_agent_idx=None, use_checkpoint=True)
    with tempfile.TemporaryDirectory() as tmp:
        out_json = Path(tmp) / "no_rf.json"
        eval_dict = _run_paper_eval(spec=spec, checkpoint=ckpt_path,
                                     scenario_set="none", n_scenarios=n_scenarios,
                                     out_json=out_json)
        return _extract_metrics(eval_dict)
```

#### Baseline 复用

`_resolve_baseline_eval(probe)`:
- 优先读 `probe.snapshot.phase5_trained_policy.runs.baseline` (= Phase B 已跑过)
- 没有 → 现跑 1 个 baseline eval (只占 ~30-60s)

**好处**: Phase B + C 同 eval pipeline → 数值可比.

#### R1 公式 (§3 已 derive)

```python
IMPROVE_TOL_R1 = 0.5  # sys-pu²; same as Phase B G6 IMPROVE_TOL

def _compute_r1_verdict(baseline_eval, no_rf_eval) -> dict:
    if "error" in baseline_eval or "error" in no_rf_eval:
        return {"verdict": "PENDING", "evidence": "baseline or no_rf eval errored"}
    if "r_f_global" not in baseline_eval or "r_f_global" not in no_rf_eval:
        return {"verdict": "PENDING", "evidence": "missing r_f_global"}
    base_rf = baseline_eval["r_f_global"]
    no_rf_rf = no_rf_eval["r_f_global"]
    diff = no_rf_rf - base_rf  # >0 means no_rf is better (less negative); <0 means baseline better
    pass_cond = diff < -IMPROVE_TOL_R1  # baseline beats no_rf significantly
    return {
        "verdict": "PASS" if pass_cond else "REJECT",
        "evidence": f"baseline.r_f={base_rf:+.3f} vs no_rf.r_f={no_rf_rf:+.3f} "
                    f"(Δ={diff:+.3f}, IMPROVE_TOL={IMPROVE_TOL_R1})",
        "improvement_baseline_minus_no_rf": -diff,
    }
```

**验收**:
- [ ] baseline 复用 Phase B → snapshot 体现 (字段 `baseline_source: "phase5"` or `"fresh"`)
- [ ] R1 PENDING 时 G6 完整 = PENDING
- [ ] R1 PASS / REJECT 时 G6 完整 follows G6_partial AND R1

---

### Step 4 — G6 完整 verdict (~20 min)

更新 `_verdict.py::_g6_trained_policy` 包含 R1:

```python
def _g6_trained_policy(snap: dict) -> dict:
    # Phase B G6_partial logic 不变
    g6_partial = _g6_partial(snap)  # rename existing logic

    # Phase C 加: 找 phase6_causality 数据
    p6 = snap.get("phase6_causality") or {}
    r1 = p6.get("r1_verdict") if isinstance(p6, dict) and "error" not in p6 else None

    if r1 is None or r1.get("verdict") == "PENDING":
        # G6 完整 PENDING (Phase C 没跑 / 跑了 but PENDING)
        return _verdict(
            "PENDING",
            f"G6_partial={g6_partial['verdict']}; R1=PENDING/missing",
            g6_partial=g6_partial, r1=r1,
        )
    # G6 完整 = AND
    if g6_partial["verdict"] == "PASS" and r1["verdict"] == "PASS":
        out_v = "PASS"
    elif g6_partial["verdict"] == "REJECT" or r1["verdict"] == "REJECT":
        out_v = "REJECT"
    else:
        out_v = "PENDING"
    return _verdict(
        out_v,
        f"G6_partial={g6_partial['verdict']}, R1={r1['verdict']}",
        g6_partial=g6_partial, r1=r1,
    )
```

**注意**: 保留 Phase B G6 行为不变 (when phase6 absent, G6 = G6_partial). 也即
`_g6_partial` 是 `_g6_trained_policy` 的旧 body, 抽出来.

**验收**:
- [ ] phase 6 absent: G6 = G6_partial (Phase B 行为, 兼容)
- [ ] phase 6 present + R1 PASS + G6_partial PASS: G6 完整 PASS
- [ ] phase 6 present + R1 REJECT: G6 完整 REJECT (即使 G6_partial PASS)
- [ ] Phase A pytest 全 PASS (Phase B G6 PASS 状态保持)

---

### Step 5 — Snapshot schema 加 phase6 (~15 min)

```jsonc
"phase6_causality": {
  "mode": "smoke" | "full",
  "ablation_config": "no_rf",  // R2/R3 留 future
  "phi_f_used": 0.0,
  "phi_h_used": 5e-4,
  "phi_d_used": 5e-4,
  "episodes_planned": 200,
  "episodes_completed": int | null,
  "run_id": "probe_phase_c_no_rf_20260501T060000",
  "run_dir": "results/sim_kundur/runs/probe_phase_c_no_rf_<TS>",
  "no_rf_checkpoint": "...best.pt" | null,
  "no_rf_eval": {r_f_global, r_h_global, r_d_global, n_episodes, ...},
  "baseline_eval": {...},
  "baseline_source": "phase5" | "fresh",
  "improve_tol_r1_sys_pu_sq": 0.5,
  "r1_verdict": {verdict, evidence, improvement_baseline_minus_no_rf},
  "wall_train_s": float,
  "wall_eval_s": float,
  "errors": [...]
}
```

`schema_version` 顶层不变 (= 1). additive.

`_report.py` 加 phase 6 section (跟 phase 5 同 style: error / not_run / table).

**验收**:
- [ ] state_snapshot.json 出 `phase6_causality` 键
- [ ] STATE_REPORT_*.md 显示 R1 + G6 完整 一行
- [ ] schema_version still == 1
- [ ] phase 1-5 字段 binary identical (除 timestamp / git_head)

---

### Step 6 — Type B invariants ≥ 2 (~20 min)

加 `tests/test_state_invariants.py`:

```python
@pytest.mark.typeB
def test_typeB_phase6_r1_signal_or_skip(snap):
    """R1 verdict 必须 PASS / REJECT / PENDING 三选一 (非空)."""
    p6 = snap.get("phase6_causality") or {}
    if "error" in p6 or not p6:
        pytest.skip("phase6 not run / errored")
    r1 = p6.get("r1_verdict") or {}
    if not r1:
        pytest.skip("r1_verdict empty")
    assert r1.get("verdict") in {"PASS", "REJECT", "PENDING"}, (
        f"R1 verdict invalid: {r1!r}"
    )

@pytest.mark.typeB
def test_typeB_g6_full_decided_or_skip(snap):
    """G6 完整: phase6 present 时 G6 应跟 G6_partial AND R1 复合 verdict 一致."""
    p6 = snap.get("phase6_causality") or {}
    if "error" in p6 or not p6:
        pytest.skip("phase6 not run / errored")
    g6 = (snap.get("falsification_gates") or {}).get("G6_trained_policy", {})
    # Verdict 不能 PENDING (除非 R1 PENDING) — 业务逻辑测试见 self-test
    extras = g6.get("g6_partial") or {}
    r1 = g6.get("r1") or {}
    if r1.get("verdict") == "PENDING":
        pytest.skip("R1 PENDING blocks G6 完整")
    if extras.get("verdict") == "PENDING":
        pytest.skip("G6_partial PENDING blocks G6 完整")
    assert g6.get("verdict") in {"PASS", "REJECT"}, g6
```

**验收**:
- [ ] 文件 ≥ 5 Type A + ≥ 7 Type B (Phase A 5+3 + B 2 + C 2)
- [ ] phase6 缺时全 SKIP (不 FAIL)
- [ ] phase6 跑过, R1 PASS/REJECT 都触发 typeB_g6_full_decided PASS

---

### Step 7 — Phase C self-test ≥ 3 (~30 min)

加 `tests/test_probe_internal.py`:

```python
def test_phase_c_short_train_returns_none_on_failure(monkeypatch, tmp_path):
    """train subprocess returncode ≠ 0 → returns None, no raise."""
    # mock subprocess.run to fail
    ...

def test_phase_c_r1_pass_baseline_beats_no_rf():
    from probes.kundur.probe_state._causality import _compute_r1_verdict
    base = {"r_f_global": -10.0}
    no_rf = {"r_f_global": -15.0}  # baseline 5 sys-pu² better
    out = _compute_r1_verdict(base, no_rf)
    assert out["verdict"] == "PASS"

def test_phase_c_r1_reject_no_rf_equals_baseline():
    from probes.kundur.probe_state._causality import _compute_r1_verdict
    base = {"r_f_global": -10.0}
    no_rf = {"r_f_global": -10.1}  # diff 0.1, < IMPROVE_TOL=0.5
    out = _compute_r1_verdict(base, no_rf)
    assert out["verdict"] == "REJECT"

def test_phase_c_r1_pending_when_baseline_errored():
    from probes.kundur.probe_state._causality import _compute_r1_verdict
    out = _compute_r1_verdict({"error": "x"}, {"r_f_global": -10.0})
    assert out["verdict"] == "PENDING"

def test_phase_c_g6_complete_pass_when_partial_and_r1_both_pass():
    from probes.kundur.probe_state import _verdict
    snap = {
        "phase5_trained_policy": {  # Phase B canned PASS
            "k_required_contributors": 2, "improve_tol_sys_pu_sq": 0.5,
            "agent_contributes": [True]*4,
            "ablation_diffs": [-2.0,-1.5,-1.0,-0.5],
            "runs": {"baseline": {"r_f_global": -10.0},
                     "zero_all": {"r_f_global": -16.0}},
        },
        "phase6_causality": {
            "r1_verdict": {"verdict": "PASS", "evidence": "..."},
        },
    }
    g6 = _verdict.compute_gates(snap)["G6_trained_policy"]
    assert g6["verdict"] == "PASS"

def test_phase_c_g6_complete_reject_on_r1_reject():
    """R1 REJECT overrides G6_partial PASS → G6 完整 REJECT."""
    ...

def test_phase_c_g6_pending_when_phase6_absent_keeps_phase_b_behavior():
    """Backward-compat: no phase6 → G6 = G6_partial (Phase B 行为)."""
    ...
```

**验收**:
- [ ] ≥ 5 test, 全 PASS
- [ ] 不 launch MATLAB / train (mock only)
- [ ] Phase B G6 行为 (phase 6 absent) 不破坏 — 5 个 Phase B G6 self-test 全 PASS

---

### Step 8 — Smoke run (~1 hr; full mode 单独 launcher 不在 plan)

```bash
# Phase C smoke = 10 ep, plumbing-only (不要期望出因果 signal)
$PY -m probes.kundur.probe_state --phase 6 --phase-c-mode smoke
```

**预期 wall**: ~30-60 min (10 ep × ~3-5 min + paper_eval 2 cold-start ~30s).

**预期 verdict**:
- 10 ep 训出来的 ckpt R1 大概率是 REJECT 或 PENDING (10 ep too few to learn r_f
  control). **这本身不是 plan failure** — smoke 是 plumbing 测试. 
- 真正信号要 full mode (200 ep, ~hours wall), 单独 launcher.

**Plan §11 验收 (smoke)**:
- [ ] phase6_causality 字段写入, schema_version=1
- [ ] STATE_REPORT_*.md 显示 phase 6 section + G6 完整
- [ ] Type B Phase C invariants PASS or SKIP, 无 FAIL
- [ ] 不污染 production: `results/sim_kundur/runs/kundur_simulink_*` git status clean
- [ ] new run dir 名 starts with `probe_phase_c_` (grep verify)
- [ ] Phase B G6 PASS 兼容 (phase 6 absent 模式下 G6 仍跟 Phase B 一致)

---

### Step 9 — Full mode + verdict markdown (不在本 plan, 单独 launcher)

跑完 smoke + invariants 全过后, 走单独 launcher:

```bash
# (separate session; ~1 day wall)
$PY -m probes.kundur.probe_state --phase 6 --phase-c-mode full
```

跑完后写 `quality_reports/phase_C_R1_verdict_<TS>.md`:
- baseline.r_f vs no_rf.r_f 数值
- R1 verdict (PASS/REJECT)
- G6 完整 verdict
- 跟 paper-anchor lock 状态对照: Phase A G1-G5 PASS + Phase B G6_partial PASS +
  Phase C R1 PASS = paper anchor 部分解锁 (R2/R3 仍 deferred)

---

## 7. 失败信号 + 中止条件

| 信号 | 含义 | 行动 |
|---|---|---|
| Step 0 paper-anchor gate fail (G1/G3/G4 PENDING/REJECT) | model state 不健康 | STOP, 跑 Phase 4 全 dispatch / model 修. NOT 强行启动 |
| `--run-id` flag 不在 train_simulink CLI | API 改了 | STOP, plan 重审 |
| `KUNDUR_PHI_F` ENV 不再生效 (=100 hardcoded) | config_simulink 改 | STOP, 找 config 直接 override 路径 |
| short_train timeout 24 hr | train 卡死 | mark train_failed, R1 PENDING. NOT 强行延长 |
| best.pt 不存在 (train 跑完无 ckpt) | train 不收敛 / NaN | mark no_converge, R1 PENDING |
| Phase B G6_partial REJECT in current snap | trained policy 已经退化, R1 测无意义 | STOP, 先重 train production (本 plan 不做) |
| Eval r_f_global = NaN | paper_eval crash / scenarios 漂移 | mark eval_failed, R1 PENDING |
| Production results/ git status 出现新 commit/file | 隔离失效 | STOP, 不可继续 |

---

## 8. 通用性回归测试 (Phase C 完成时)

跟 Phase B §11 同 4 case + 2 Phase C 特殊 case:

| 模拟改动 | 预期 probe 行为 |
|---|---|
| `KUNDUR_PHI_F` ENV var 不生效 | Step 0 verify fail → STOP |
| `--run-id` CLI flag 取消 | Step 0 verify fail → STOP |
| n_ess 改成 5 (假想 v4) | train 自适应 (config 来自 contract); paper_eval 自适应; R1 公式不依赖 n_ess |
| 删全部 best.pt | Phase B baseline = error, R1 = PENDING (chain effect 跨 phase) |
| Production train 期间运行 | 隔离 OK (不同 run_id, 不同 dir); MATLAB engine 占用是物理冲突, 不在 probe scope |
| paper_eval API 改 | Phase B Step 0 prereq 已守 |

`tests/test_phase_c_generality.py` (可后置) 跑前 4 case (用 monkeypatch / ENV).

**Phase C 完成定义** = Step 1-8 通过 + smoke 全 acceptance + 前 4 case 至少 3 case 验过.

---

## 9. References (executor 必读)

| 文件 | 用途 |
|---|---|
| `docs/design/probe_state_design.md` §6.2 | Phase C 设计源 |
| `scenarios/kundur/train_simulink.py` line 139-235 | --run-id, --episodes, --resume CLI |
| `scenarios/kundur/config_simulink.py` line 91/114/115 | KUNDUR_PHI_{F,H,D} ENV var |
| `utils/run_protocol.py::get_run_dir` | run_dir = `results/sim_<scenario>/runs/<run_id>/` |
| `probes/kundur/probe_state/_trained_policy.py` | Phase B `_run_paper_eval` 复用 |
| `probes/kundur/probe_state/_verdict.py::_g6_trained_policy` | Phase B G6_partial logic |
| `quality_reports/plans/2026-05-01_probe_state_phase_B.md` | 上一 phase plan, 风格参考 |
| CLAUDE.md "PAPER-ANCHOR HARD RULE" | G1-G6 verdict 不全 PASS 禁 PHI sweep |

---

## 10. 时间预算 (含 +50% buffer; 2026-05-01 calibrated against actual run)

### Code + smoke (Step 0-8) — predictions stand

| Step | 净估 | 含 buffer |
|---|---|---|
| 0 prereq + paper-anchor gate | 30 min | 45 min |
| 1 骨架 | 30 min | 45 min |
| 2 short-train wrapper (代码, 不含 train wall) | 45 min | 70 min |
| 3 eval + R1 公式 | 30 min | 45 min |
| 4 G6 完整 verdict | 20 min | 30 min |
| 5 schema | 15 min | 25 min |
| 6 invariants | 20 min | 30 min |
| 7 self-test | 30 min | 45 min |
| 8 smoke (含 train ~30-60 min) | 60 min | 90 min |
| **代码 + smoke 合计** | **~4.7 hr** | **~7 hr** |

### Full mode (Step 9) — **revised 2026-05-01 from actual 47-min run**

| stage | original plan estimate | **actual measurement** | revised budget (含 buffer) |
|---|---|---|---|
| Phase 5 (5 ep × 6 paper_eval cold-starts) | ~10-15 min | **6.2 min** (374.8 s) | 10 min |
| Phase 6 short-train (200 ep, φ_f=0) | **~10-50 hr** ⚠️ | **40 min** (2402.8 s; ~12 s/ep) | 60 min |
| Phase 6 eval (5 ep paper_eval) | ~30-60 s | 62.2 s | 90 s |
| **full-mode total** | **10-50 hr** | **47 min** | **~75 min** |

**Calibration root cause**: original plan §10 conflated **production train**
speed (~3-5 min/ep, full update_repeat + manifest scenarios) with
**short-train** speed used by Phase C (`scenario_set=none`, default config).
Verified at ckpt mtime gaps in
`probe_phase_c_no_rf_20260501T070140/checkpoints/`: ep50→ep100 = 597 s,
ep100→ep150 = 598 s, all ≈ 12 s/ep linearly — well under 1 hr full-200-ep.

Actual V1 full-mode total wall = `2839.8 s ≈ 47 min` per snapshot
`state_snapshot_20260501T074245.json`. Verdict markdown:
`quality_reports/phase_C_R1_verdict_20260501T074245.md` §5.

**Implication**: `--phase-c-mode full` is **practical for routine use**
(~1 hr ≪ original 10-50 hr ceiling). Operators can re-run V1 after model
modifications without scheduling-overhead concerns. The "10-50 hr"
reservation in CLAUDE.md / plan history was protecting against a
non-existent worst case.

---

## 11. 设计 self-review (写完一遍后跑一次)

- [ ] 没有 hardcode `phi_f = 0` / `n_agents = 4` / `episodes = 200` 在 verdict logic
- [ ] PHI 控制走 ENV var, 不写新 config 文件
- [ ] run_dir 用 `--run-id` flag, 不 hardcode 路径
- [ ] train_simulink 当 black-box (subprocess + JSON / file outputs)
- [ ] paper_eval 调用复用 Phase B wrapper, 不 reimplement
- [ ] phase6 字段全 additive, schema_version still == 1
- [ ] G6 完整 = G6_partial AND R1, 不破 Phase B 行为 (phase6 absent 模式下 G6 = G6_partial)
- [ ] paper-anchor gate Step 0 写死, 不可绕过
- [ ] production results/ 不被污染 (run_id prefix + git status 验)
- [ ] 不修改 SAC code / reward formula / production ckpt

self-review 任一 fail → 不算完成, 返修.

---

## 12. 完成后下一步 (不在本 plan)

- 跑 full-mode (200 ep, ~hours wall) 拿真正 R1 信号
- 写 R1 verdict markdown
- 决定 R2 / R3 是否启动 (各需 1 fresh train, ~每个 10-50 hr)
- 若 G6 完整 PASS → 触发 `INVALID_PAPER_ANCHOR.md` lock 部分解锁
- Phase C v2 plan (R2/R3) — separate plan, 不本 plan scope

---

*end of plan — keep simple, keep generic*
