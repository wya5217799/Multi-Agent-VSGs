---
note_id: devlog-2026-04-11-simulink-run-artifact-locality
scenario_id: kundur, ne39
related_run_id: explicit-path-standalone-smoke-20260411
related_commit: this commit
status: closed
tags: [simulink, training, artifacts, debug]
---

# Context

Simulink training had two artifact paths in practice:

- default-managed runs under `results/sim_*/runs/<run_id>/`
- explicit paths passed by harness smoke or manual runs

A review found that explicit-path runs could write checkpoints and logs to the
requested directory while `run_meta.json` and `training_status.json` went to an
unrelated auto-generated run directory.

# Evidence

- Failing regression reproduced for Kundur and NE39 by parsing explicit
  `<root>/checkpoints` and `<root>/logs/training_log.json` paths.
- The failure was caused by unconditional `args.run_dir` assignment in
  `parse_args()`, plus a second default run-dir assignment in `train(args)`.

# What Changed

- Added `infer_run_dir_from_output_paths()` to centralize the standard
  explicit-path layout rule.
- Kundur and NE39 now infer `run_dir=<root>` when explicit paths use
  `<root>/checkpoints` and `<root>/logs/training_log.json`.
- Default-managed runs still create isolated `results/sim_*/runs/<run_id>/`
  directories.
- Non-standard explicit paths avoid unrelated generated run roots and keep the
  compatibility fallback to `checkpoint_dir`.
- Eval metrics and monitor physics checks from this training-artifact pass were
  kept in the same commit because they share the same structured logging
  contract.

# Verification

Commands run:

```text
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_structural_fixes.py::TestRunIsolation::test_kundur_explicit_checkpoint_and_log_paths_are_preserved tests/test_structural_fixes.py::TestRunIsolation::test_ne39_explicit_checkpoint_and_log_paths_are_preserved -q
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m py_compile scenarios\kundur\train_simulink.py scenarios\new_england\train_simulink.py utils\run_protocol.py
C:\Users\27443\miniconda3\envs\andes_env\python.exe -m pytest tests/test_run_protocol.py tests/test_structural_fixes.py tests/test_monitor.py tests/test_evaluate_run.py tests/test_artifact_writer.py tests/test_fixes.py tests/test_run_meta.py -q
```

Results:

```text
explicit-path regression tests: 2 passed
related regression suite: 113 passed, 4 skipped
py_compile: exit 0
```

Smoke checks:

```text
Kundur explicit-path standalone 1 episode: all requested artifacts present under explicit root
NE39 explicit-path standalone 1 episode: all requested artifacts present under explicit root
```

Full `pytest -q` was attempted but collection still fails on the pre-existing
missing optional dependency:

```text
ModuleNotFoundError: No module named 'andes'
```

# Outcome

Explicit harness/manual runs now remain complete under their requested run root:

- `run_meta.json`
- `training_status.json`
- `logs/metrics.jsonl`
- `logs/events.jsonl`
- `logs/training_log.json`
- `checkpoints/*.pt`

# Next

- Keep ANDES/ODE logging out of this repair line unless a future task explicitly
  reopens those training paths.
