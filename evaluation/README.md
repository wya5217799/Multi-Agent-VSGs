# `evaluation/` — paper_eval usage guide

> **PAPER-ANCHOR LOCK is permanently engaged in this module.** Output JSON
> always carries `paper_comparison_enabled: false` and `cum_unnorm` vs
> `-8.04 / -15.20` is INVALID for paper-claim attribution until the
> Signal/Measurement/Causality G1-G6 verdicts are signed off (see project
> root `CLAUDE.md` § PAPER-ANCHOR HARD RULE). Use this evaluator for
> **project-internal regression and ablation comparison**, not for paper
> reproduction claims.

## Modules

| File | Purpose |
|---|---|
| `metrics.py` | Pure-numpy paper §IV-C helpers (`_compute_global_rf_*`, `_rocof_max`, `_settling_time_s`, `_bootstrap_ci`, …) + dataclasses + `generate_scenarios`. Reusable across NE39/Kundur. |
| `runner_helpers.py` | Kundur-runner-shape helpers (`_resolve_disturbance_dispatch`, `_build_runner_config`, `_compute_scenario_provenance`). Reads env attribute shape (`env._PHI_F`, etc.) + writes stderr. |
| `paper_eval.py` | `evaluate_policy` (per-suite loop) + `run_single_eval` (one cell, end-to-end) + `run_batch` (cartesian product) + CLI `main()`. |

## Two run modes (mutually exclusive)

```
single-cell mode:  --checkpoint <ckpt.pt>  --output-json <out.json>
batch mode:        --batch-spec <spec.json>
```

Argparse rejects passing both. `--checkpoint` may be omitted for the zero-action baseline.

### Single-cell mode example

```bash
python -m evaluation.paper_eval \
    --checkpoint results/.../best.pt \
    --output-json results/eval/best_ep253.json \
    --scenario-set test \
    --n-scenarios 50
```

### Batch mode example

```bash
python -m evaluation.paper_eval --batch-spec batch_specs/round1_ablation.json
```

`batch_specs/round1_ablation.json`:
```json
{
  "checkpoints": [
    "results/.../best.pt",
    "results/.../ep400.pt"
  ],
  "ablations": [
    {"label": "full",       "zero_agent_idx": null},
    {"label": "ablate_es1", "zero_agent_idx": 0},
    {"label": "ablate_es2", "zero_agent_idx": 1},
    {"label": "ablate_es3", "zero_agent_idx": 2},
    {"label": "ablate_es4", "zero_agent_idx": 3}
  ],
  "output_dir": "results/eval/round1_batch_2026-05-03/",
  "scenario_set": "test",
  "settle_tol_hz": 0.005,
  "n_scenarios": 50,
  "seed_base": 42,
  "disturbance_mode": null
}
```

Outputs (per cell):
```
results/eval/round1_batch_2026-05-03/
├── _batch_summary.json                  # n_pass / n_fail / per-cell paths + errors
├── best__full.json
├── best__ablate_es1.json
├── …
└── ep400__ablate_es4.json
```

**Why batch matters**: each new env construction triggers a 30–60 s MATLAB cold-start. A 7-ckpt × 4-ablation suite (28 cells) under single-cell mode costs ~14–28 min in cold-starts alone. Batch mode pays this once and reuses the env for all 28 cells.

## CLI reference

| Flag | Default | Notes |
|---|---|---|
| `--checkpoint PATH` | `None` | mutex with `--batch-spec`; omit → zero-action baseline |
| `--batch-spec PATH` | `None` | mutex with `--checkpoint`; per-cell JSONs land in `spec.output_dir` |
| `--output-json PATH` | `None` | required in single-cell mode (else exit 2); ignored in batch |
| `--n-scenarios N` | `50` | overridden by manifest length when `--scenario-set != none` |
| `--seed-base N` | `42` | controls inline scenario RNG + bootstrap CI seed (offset 7919) |
| `--policy-label STR` | `<ckpt-stem>` | identifier in JSON; auto from ckpt filename |
| `--disturbance-mode {bus,gen,vsg,hybrid,ccs_load}` | `None` | see § dispatch resolution below |
| `--settle-tol-hz FLOAT` | `0.005` | settling tolerance in Hz; recorded in `runner_config.settle_tol_hz` |
| `--scenario-set {none,train,test}` | `none` | `train`/`test` load fixed manifest; sha256 in `runner_config.scenario_provenance` |
| `--scenario-set-path PATH` | `None` | override default manifest path |
| `--zero-agent-idx N` | `None` | force agent N to output zero action (B-a ablation) |

## Dispatch resolution (`--disturbance-mode` ↔ `KUNDUR_DISTURBANCE_TYPE`)

A3+ semantics. Three zones depending on whether `KUNDUR_DISTURBANCE_TYPE` env-var starts with `loadstep_paper_*` or `loadstep_ptdf_*`:

| CLI `--disturbance-mode` | Env-var matches `loadstep_*`? | Result |
|---|---|---|
| explicit (e.g. `gen`) | yes | **`SystemExit`** — operator must pick one |
| `None` (default) | yes | **stderr WARN** + use env-var; `runner_config.dispatch_resolution.implicit_conflict_warned=true` |
| any | no | clean — CLI mode (or `bus` default) determines `bus_choices` |

Production probes pair env-var + CLI mode intentionally (e.g. `probe_b_sign_pair` sets `KUNDUR_DISTURBANCE_TYPE=pm_step_proxy_random_es1` + `--disturbance-mode vsg`). The mutex is **only** between explicit-CLI and `loadstep_*` env-var.

## Relevant env-vars

| Env-var | Read by | Effect |
|---|---|---|
| `KUNDUR_DISTURBANCE_TYPE` | env construction + dispatch resolver | sets disturbance protocol; `loadstep_*` triggers SystemExit if combined with explicit CLI mode |
| `KUNDUR_PHI_F` | `config_simulink.py` | reward weight on freq deviation; default 100.0 (paper-faithful) |
| `KUNDUR_PHI_H` / `KUNDUR_PHI_D` | `config_simulink.py` | reward weight on H / D action; default 5e-4 (post-resweep lock) |
| `KUNDUR_PHI_H_PER_AGENT` / `KUNDUR_PHI_D_PER_AGENT` | env construction | comma-separated 4-value override; runner_config records the resolved list |
| `KUNDUR_DIST_MAX` | `config_simulink.py` | disturbance magnitude upper bound |
| `KUNDUR_MODEL_PROFILE` | env construction | Simulink model profile JSON path; `main()` forces `kundur_cvs_v3.json` |

All resolved values land in `runner_config` of the output JSON (single source of truth for cross-run audit).

## Output JSON schema (v3, 2026-05-03)

```
{
  "schema_version": 3,
  "paper_comparison_enabled": false,
  "paper_comparison_lock_reason": "INCONCLUSIVE_STOP_REQUIRED ...",
  "runner_config": {
    "phi_f":  100.0,
    "phi_h":  5e-4,
    "phi_d":  5e-4,
    "phi_h_per_agent": null,
    "phi_d_per_agent": null,
    "settle_tol_hz":   0.005,
    "settle_window_s": 1.0,
    "dispatch_resolution": {
      "env_type": "pm_step_proxy_random_gen",
      "cli_mode": "gen",
      "dispatch_path": "pm_step_proxy",
      "implicit_conflict_warned": false
    },
    "scenario_provenance": {
      "source": "manifest",
      "scenario_set": "test",
      "manifest_path": "scenarios/.../v3_paper_test_50.json",
      "manifest_sha256_16": "abcd1234567890ef",
      "n_scenarios": 50
    },
    "bootstrap_config": {
      "n_resample": 1000,
      "alpha": 0.05,
      "seed_offset": 7919,
      "seed_resolved": 7961
    }
  },
  "checkpoint_path": "...",
  "policy_label": "best_ep253",
  "n_scenarios": 50,
  "seed_base": 42,
  "cumulative_reward_global_rf": {
    "unnormalized": -16.14,
    "per_M": -0.323,
    "per_M_per_N": -0.0807,
    "paper_target_unnormalized": -8.04,        // INVALID for direct comparison per LOCK
    "paper_no_control_unnormalized": -15.20,    // INVALID for direct comparison per LOCK
    "deltas_vs_paper": {
      "vs_ddic_unnorm": -8.10,
      "vs_no_control_unnorm": -0.94,
      "ratio_vs_ddic": 2.01
    }
  },
  "summary": {
    "n_scenarios": 50, "n_steps_per_ep": 50, "n_agents": 4, "total_steps": 2500,
    "max_freq_dev_hz_mean": 0.45, "max_freq_dev_hz_min": 0.10, "max_freq_dev_hz_max": 1.20,
    "max_freq_dev_hz_ci95":     {mean, std, ci_lo, ci_hi, n, n_resample, alpha},
    "rocof_hz_per_s_mean": 4.5, "rocof_hz_per_s_max": 12.5,
    "rocof_hz_per_s_ci95":      { … },
    "settled_pct": 80.0, "settled_time_s_mean": 0.42,
    "tds_failed_count": 0, "nan_inf_count": 0,
    "rh_abs_share_pct_mean":    5.6,    // NOT paper formula — |·|-normalized share
    "rh_abs_share_pct_ci95":    { … },
    "r_f_global_unnorm_ci95":   { … }
  },
  "per_episode_metrics": [ /* one entry per scenario; per-agent decomposition for Probe B */ ],
  "figures": [],
  "omega_source_paths": [ /* Kundur cvs_v3 4 ESS omega Timeseries metadata */ ]
}
```

### Schema versioning

| Version | Date | Change |
|---|---|---|
| 1 | pre-2026-05-03 | original |
| 2 | 2026-05-03 (`ab1d480`) | additive: top-level `runner_config` block |
| 3 | 2026-05-03 (`9733ef0`) | **breaking**: `summary["rh_share_pct_mean"]` → `summary["rh_abs_share_pct_mean"]` |

Consumers should gate via `schema_version >= N` checks before reading new fields.

## Common patterns

### A. Single ckpt eval, paper-test scenario set
```bash
python -m evaluation.paper_eval \
    --checkpoint results/.../best.pt \
    --output-json results/eval/best.json \
    --scenario-set test
```

### B. Zero-action baseline
```bash
python -m evaluation.paper_eval \
    --output-json results/eval/zero_baseline.json \
    --scenario-set test
```

### C. Ablation suite across multiple ckpts (batch mode)
See § batch mode example above.

### D. Single-agent ablation, single ckpt
```bash
python -m evaluation.paper_eval \
    --checkpoint results/.../best.pt \
    --output-json results/eval/best_ablate_es3.json \
    --zero-agent-idx 2 \
    --policy-label "best_ablate_es3"
```

### E. Compare two PHI sweeps with cross-run audit
```bash
KUNDUR_PHI_F=100 python -m evaluation.paper_eval ... --output-json a.json
KUNDUR_PHI_F=300 python -m evaluation.paper_eval ... --output-json b.json
# a.json["runner_config"]["phi_f"] == 100
# b.json["runner_config"]["phi_f"] == 300
# A consumer comparing total_reward MUST assert phi_f match before merging.
```

## Programmatic use (from agent / probe code)

```python
from evaluation.paper_eval import run_single_eval, run_batch
from env.simulink.kundur_simulink_env import KundurSimulinkEnv
from pathlib import Path

env = KundurSimulinkEnv(training=False)  # 1 cold-start

result, runner_config = run_single_eval(
    env=env,
    ckpt_path=Path("results/.../best.pt"),
    zero_agent_idx=None,
    scenario_set="test",
    scenario_set_path=None,
    n_scenarios=50,
    seed_base=42,
    disturbance_mode_cli=None,
    settle_tol_hz=0.005,
    output_path=Path("out.json"),
)
# result is EvalResult dataclass; runner_config is dict

# Or batch:
spec = {
    "checkpoints": ["a.pt", "b.pt"],
    "ablations":   [{"label": "full", "zero_agent_idx": None}],
    "output_dir":  "results/eval/programmatic/",
    "scenario_set": "test", "n_scenarios": 50, "seed_base": 42,
    "settle_tol_hz": 0.005, "disturbance_mode": None,
    "scenario_set_path": None,
}
summary = run_batch(env=env, batch_spec=spec)
# summary keys: n_cells / n_pass / n_fail / total_time_s / results
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `SystemExit: explicit --disturbance-mode=… conflicts with KUNDUR_DISTURBANCE_TYPE=loadstep_…` | shell has loadstep env-var set + you passed CLI mode | unset env-var or omit CLI mode |
| stderr WARN: `--disturbance-mode unspecified but KUNDUR_DISTURBANCE_TYPE=loadstep_… forces loadstep` | implicit conflict; env-var precedence is in effect | OK if intended; check `runner_config.dispatch_resolution.implicit_conflict_warned` |
| exit 2 with `--output-json is required in single-cell mode` | single-cell call missing output path | add `--output-json` or switch to `--batch-spec` |
| `ValueError: scenarios contain bus values outside …` | manifest has paper-LoadStep buses but env-var isn't loadstep | export `KUNDUR_DISTURBANCE_TYPE=loadstep_paper_*` or filter manifest |
| `FileNotFoundError: scenario manifest not found` | path typo or manifest not generated | check `scenarios/kundur/scenario_sets/` |
| `paper_comparison_enabled: false` in output | always — PAPER-ANCHOR LOCK | not a bug; LOCK requires G1-G6 to unlock |

## Tests

```bash
python -m pytest tests/test_metrics.py tests/test_paper_eval_runner.py tests/test_evaluate_policy_integration.py
```

85 tests, ~0.5 s. No MATLAB required (stub env in integration tests).

## See also

- `CLAUDE.md` § PAPER-ANCHOR HARD RULE — why paper number reproduction is gated
- `docs/paper/kd_4agent_paper_facts.md` — paper §IV-C formula reference (the metric helpers implement these)
- `docs/paper/archive/yang2023-fact-base.md §10` — historical LOCK rationale
- `quality_reports/plans/2026-05-03_paper_eval_*.md` — design plans for the optimization tickets
