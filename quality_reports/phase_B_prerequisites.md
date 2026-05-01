# Phase B Prerequisites — verdict 2026-05-01

> Plan: `quality_reports/plans/2026-05-01_probe_state_phase_B.md` Step 0
> Probe under build: `probes/kundur/probe_state/_trained_policy.py`

## Step 0 acceptance — 5/5 PASS

| Check | Status | Evidence |
|---|---|---|
| `--zero-agent-idx` flag exists | ✅ | `evaluation/paper_eval.py:756`; range guard line 845-847 |
| `--scenario-set` accepts `test` | ✅ | `paper_eval.py:743` choices include `'test'` |
| `scenarios/kundur/scenario_sets/v3_paper_test_50.json` exists | ✅ | `ls` returns 8992 bytes, mtime 2026-04-27 |
| ≥ 1 best.pt exists matching active profile | ✅ | 8+ candidates under `results/sim_kundur/runs/` and `results/harness/kundur/cvs_v3_*/`. Newest 2026-04-30 10:28 |
| paper_eval output schema has needed fields | ✅ | line 670-707 emits `cumulative_reward_global_rf` (per run), `r_h_total` / `r_d_total` / `r_f_global_per_agent` (per episode) |

## Checkpoint selection — auto-search default

Auto-search rule (Plan §5 Step 2):

1. CLI override `--checkpoint <path>` (highest priority)
2. ENV override `KUNDUR_PROBE_CHECKPOINT=<path>`
3. Auto-search: ordered by mtime descending under
   - `results/harness/kundur` (priority — paper-anchor lock context)
   - `results/sim_kundur/runs`
   - `results/sim_kundur/archive`

Filter: path must contain `cvs_v3` or `kundur_simulink` (excludes NE39 / v2 / sps).

Profile match check: ckpt's `obs_dim` / `act_dim` must agree with active
`KUNDUR_MODEL_PROFILE` runtime config (else skip — it was trained for a
different topology).

### Current candidates (2026-05-01)

| mtime               | size  | path |
|---------------------|------:|------|
| 2026-04-30 10:28:51 | 9.1MB | `results/sim_kundur/runs/kundur_simulink_20260430_093132/checkpoints/best.pt` |
| 2026-04-30 04:17:13 | 9.1MB | `results/sim_kundur/runs/kundur_simulink_20260430_035814/...` |
| 2026-04-30 02:24:54 | 9.1MB | `results/harness/kundur/cvs_v3_e1_phi0_ablation/aborted_run_snapshot/.../best.pt` |
| 2026-04-30 02:04:38 | 9.1MB | `results/sim_kundur/runs/kundur_simulink_20260430_015448/...` |

Auto-search will pick the harness/cvs_v3 entry first (priority root match);
all 9.1MB suggests consistent shared-weights checkpoint format.

**Note**: probe is not pinning a specific ckpt at design time. The selection
rule re-evaluates at every run, so when a new ckpt drops the probe naturally
moves to it. This is by design (Plan §1: checkpoint discovery generic).

## paper_eval call shape (verified)

```python
cmd = [
    PY, "-m", "evaluation.paper_eval",
    "--scenario-set", "none",            # smoke; "test" for full
    "--n-scenarios", "5",                # smoke; manifest length overrides for "test"
    "--disturbance-mode", "gen",         # align with KUNDUR_DISTURBANCE_TYPE default
    "--seed-base", "42",
    "--policy-label", label,             # 'baseline' / 'zero_agent_<i>' / 'zero_all'
    "--output-json", str(out_json),      # REQUIRED
]
if ckpt_path is not None:
    cmd += ["--checkpoint", str(ckpt_path)]
if zero_idx is not None:
    cmd += ["--zero-agent-idx", str(zero_idx)]
```

## Notes for executor

- `--output-json` is REQUIRED (not `--out-dir` as design §6.1 implied).
- paper_eval bumps `KUNDUR_DISTURBANCE_TYPE` to `pm_step_proxy_random_gen`
  by default. We pass `--disturbance-mode gen` to align with this default
  and avoid ENV-coupled drift.
- paper_eval does NOT dump action sequences in current schema. Plan §4
  `action_mean` field will be `None` until paper_eval adds `--dump-actions`.
- Subprocess isolation: each run gets its own MATLAB engine (cold start
  ~30s × 6 runs = ~3min cold-start overhead in smoke mode; may be reduced
  later via worker pool, not in Phase B v1).

---

*Step 0 PASS — proceed to Step 1.*
