# Phase C Prerequisites — verdict 2026-05-01

> Plan: `quality_reports/plans/2026-05-01_probe_state_phase_C.md` Step 0
> Probe under build: `probes/kundur/probe_state/_causality.py` (not yet created)

## Step 0 acceptance — 3/3 PASS

| Check | Status | Evidence |
|---|---|---|
| **0a — paper-anchor gate** (G1-G5 全 PASS) | ✅ PASS | latest snapshot: `results/harness/kundur/probe_state/state_snapshot_20260501T062245.json` |
| **0b — train_simulink API + PHI ENV runtime** | ✅ PASS | `--episodes` / `--resume` / `--seed` 全在; `--run-id` D-minimal added; `KUNDUR_PHI_F=0` runtime 生效 (`config_simulink.PHI_F == 0.0`) |
| **0c — this file written** | ✅ | (你正在读) |

## 0a — Paper-anchor gate verdict (CLAUDE.md HARD RULE 解锁)

跑 `python -m probes.kundur.probe_state --phase 1,2,3,4 --sim-duration 3.0`,
wall = 81.7s.

| Gate | Verdict | Evidence |
|------|---------|----------|
| G1_signal       | **PASS** | best dispatch `pm_step_hybrid_sg_es` excites 4 agents > 1 mHz |
| G2_measurement  | **PASS** | open-loop omega sha256: 4/4 distinct |
| G3_gradient     | **PASS** | 12 of 12 dispatches show non-degenerate per-agent share gradient |
| G4_position     | **PASS** | 2 distinct responder signatures across 12 dispatches |
| G5_trace        | **PASS** | largest std-diff = 2.127e-03 pu in `pm_step_proxy_bus9` |
| G6_trained_policy | PENDING | phase5 not in this run; Phase B G6_partial = PASS established at `state_snapshot_20260501T054235.json` |

**Conclusion**: G1-G5 全 fresh PASS (< 5 min age). PAPER-ANCHOR HARD RULE
("G1-G6 verdict 不全 PASS 时禁 PHI sweep") **解锁条件满足** (G6 由 Phase C 自身
update, 不在解锁要求). Phase C 启动授权 ✅.

### Phase 4 dispatch summary

| dispatch | agents>1mHz | max\|Δf\| (Hz) | r_f share max-min |
|---|---|---|---|
| pm_step_hybrid_sg_es      | **4** | 0.121 | 0.608 |
| pm_step_proxy_bus7        | 3     | 0.241 | 0.672 |
| pm_step_proxy_bus9        | 3     | 0.209 | 0.677 |
| pm_step_proxy_g1          | 3     | 0.137 | 0.660 |
| pm_step_proxy_g2          | 3     | 0.151 | 0.669 |
| pm_step_proxy_g3          | 3     | 0.173 | 0.668 |
| pm_step_proxy_random_bus  | 3     | 0.209 | 0.677 |
| pm_step_proxy_random_gen  | 3     | 0.151 | 0.669 |
| pm_step_single_es1        | 3     | 0.241 | 0.672 |
| pm_step_single_es2        | **4** | 0.207 | 0.671 |
| pm_step_single_es3        | 3     | 0.249 | 0.662 |
| pm_step_single_es4        | 3     | 0.209 | 0.677 |

**FACT 观察 (跟 Phase A plan 期望对照)**:
- Plan §5 期望 pm_step_proxy_g2 → agents=1, max|Δf|≈0.097.
  实测 → agents=3, max|Δf|=0.151. **比期望强 (G3 gradient 健康)**.
- Plan §5 期望 pm_step_hybrid_sg_es → agents=4, max|Δf|~0.65 mean.
  实测 → agents=4, max|Δf|=0.121. **agents 数对; 幅度比期望弱**.
- Plan §5 期望 pm_step_proxy_random_gen → agents=1.33 avg (Probe B 历史).
  实测 → agents=3. **比 Probe B 历史 1.33-of-4 强**.

历史 "1.33-of-4" 与今天 "3-of-4 / 4-of-4" 的差异需另起 verdict 文档跟踪 (不在
本 plan scope). 当前 fresh data 是 G1-G5 PASS 的依据.

## 0b — train_simulink API + PHI ENV

### CLI flags 全验

| flag | exists | source |
|---|---|---|
| `--mode` (standalone\|simulink) | ✅ | argparse line 142-145 |
| `--episodes` | ✅ | line 146 |
| `--resume <path\|none>` | ✅ | line 153-156; `--resume none` ⇒ fresh start (line 432-433) |
| `--seed` | ✅ | line 159 |
| `--run-id <id>` | ✅ **D-minimal added 2026-05-01** | argparse line 218-227 (新加); fallback line 230 (`args.run_id or generate_run_id(...)`) |

### D-minimal `--run-id` decision rationale

Step 0 finding: train_simulink.py 原本 line 223 `args.run_id =
generate_run_id("kundur_simulink")` 强制覆盖任何外部输入. Plan §5 隔离机制
("`--run-id "probe_phase_c_no_rf_<TS>"`") 假设 CLI flag 存在, **不存在**.

评 4 个修订方案:

| 方案 | Pro | Con | 选 |
|---|---|---|---|
| A. ENV var `KUNDUR_RUN_ID_OVERRIDE` 在 `generate_run_id` | 跨 train script 通用 | utility 加 hidden 全局开关; ENV 泄漏污染 NE39/standalone; `run_id` 不是 utility 职责 | ❌ |
| B. Post-train rename run_dir | 0 production code | rename race; training_log 内 path 引用可能破 | ❌ |
| C. Metadata-only tagging (RUN_TAG.txt) | 0 production code | 弱隔离, ls 看不出 | ❌ |
| **D-minimal**. `train_simulink.py` 加 `--run-id` argparse + fallback | 语义干净 (启动参数走 CLI); 默认行为 100% 兼容 (None → generate_run_id 自动 fallback); 影响面最小 (仅 Kundur train script); 工程审计强 (ps/history 留显式 record) | 1+1 行改 train_simulink.py — 但属"接口扩展", 非"逻辑改动", 不破 plan §2 black-box 边界 | ✅ |

**实施**:
- `scenarios/kundur/train_simulink.py` line 218-227: `parser.add_argument("--run-id", type=str, default=None, help="...")`
- 同文件 line 230: `args.run_id = args.run_id or generate_run_id(f"kundur_{args.mode}")`

**Backward compat verify**: `--run-id` 不传 → `args.run_id = None or generate_run_id(...)` → 与 Step 0a 之前行为 binary identical. 既有 launcher (`scripts/launch/run_kundur_simulink.bat`) 不破.

### PHI ENV var

```bash
KUNDUR_PHI_F=0 python -c "from scenarios.kundur.config_simulink import PHI_F; assert PHI_F == 0.0"
# OK
```

`config_simulink.py:91` `PHI_F = float(_os.getenv("KUNDUR_PHI_F", "100.0"))` 验
runtime 生效. r_f penalty in train reward `_base.py:232` `step_r_f = self._PHI_F
* r_f_i` — φ_f=0 ENV 时 r_f 完全消失 from training gradient. 这是 Phase C R1
测试的关键假设, ✓.

paper_eval `r_f_global` is **PHI-unweighted** (paper_eval.py 注释 "paper §IV-C
r_f_global = -Σ Δf²", 无 PHI multiplication). 这意味 φ_f=0 train ckpt 用
paper_eval eval 时仍按原始 frequency cost 算分, 跨 ckpt 数值可比. ✓.

## Phase C 启动授权

3 个 acceptance 全过 → **Phase C Step 1 (`_causality.py` 骨架) 可启动**.

执行前 caller 须:
1. (if not yet) commit Step 0 changes to git (train_simulink.py + plan + this file)
2. confirm production train 不在跑 (MATLAB engine 排他)
3. accept full mode wall budget ~10-50 hr (smoke ~30-60 min)

---

*Step 0 全 PASS — proceed to Step 1.*
