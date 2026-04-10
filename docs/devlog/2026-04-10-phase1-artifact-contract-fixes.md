# 2026-04-10 Phase 1 Artifact Contract Fixes

## Metadata

- note_id: 2026-04-10-phase1-artifact-contract-fixes
- related_run_id: sim_kundur-standalone-3ep-smoke, sim_ne39-standalone-3ep-smoke
- related_commit: this commit
- related_plan: docs/superpowers/plans/2026-04-10-phase1-artifact-contract.md

## Context

Phase 1 added structured training artifacts:

- metrics.jsonl
- events.jsonl
- latest_state.json
- contract-based PASS/MARGINAL/FAIL verdicts

Code review found three contract gaps:

- Short smoke runs did not write latest_state.json.
- Verdicts could PASS when eval_reward and alpha were missing.
- Fresh runs appended metrics/events into previous run files.

## Root Causes

- ArtifactWriter only supported append mode and had no fresh-run reset path.
- compute_verdict treated eval_reward and alpha as optional even when the scenario contract configured thresholds for them.
- Training scripts wrote latest_state.json only on 50-episode intervals.
- `--resume none` normalized to `None`, but auto-resume still interpreted that as "no explicit resume" and loaded existing checkpoints.
- The repo-local `utils.python_env_check` import ran before the training scripts inserted the repo root into sys.path.

## Repair Path

- Added `ArtifactWriter(reset_existing=True)` to clear per-run artifact files before a fresh run.
- Fresh training runs reset both structured artifacts and legacy training_log.json.
- Training end writes a final latest_state.json snapshot, so short smoke runs still produce all required files.
- Verdict scoring now fails if eval_reward or alpha are absent while their thresholds are configured.
- Moved repo-root sys.path insertion before repo-local utility imports.
- Fixed `--resume none` so it disables auto-resume instead of triggering it.

## Verification

Commands run:

```text
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_artifact_writer.py tests/test_evaluate_run.py tests/test_python_env_check.py -v
```

Result:

```text
26 passed
```

Smoke checks:

```text
C:\Users\27443\miniconda3\envs\andes_env\python.exe scenarios/kundur/train_simulink.py --mode standalone --episodes 3 --resume none
C:\Users\27443\miniconda3\envs\andes_env\python.exe scenarios/new_england/train_simulink.py --mode standalone --episodes 3 --resume none
```

Both completed with exit code 0. For each scenario, metrics.jsonl had exactly 3 lines, training_log.json had exactly 3 episode rewards, and latest_state.json existed with episode 2.

Verdict smoke:

```text
C:\Users\27443\miniconda3\envs\andes_env\python.exe utils/evaluate_run.py --log-dir results/sim_kundur/logs/standalone --contract scenarios/contracts/sim_kundur.json
```

Result:

```text
Verdict: FAIL
Episodes evaluated: 3
Insufficient data: only 3 episodes (need >= 50)
```

## Follow-Up

- Keep per-run structured artifacts out of git unless a specific evidence record is needed.
- If Phase 1 evolves into a stable training artifact rule beyond smoke support, promote the rule to a decision record.
