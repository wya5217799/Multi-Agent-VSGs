---
note_id: devlog-2026-04-11-python-runtime-alignment-and-optional-andes-skip
scenario_id: kundur
related_run_id: none
related_commit: this commit
status: closed
tags: [tests, environment, regression]
---

# Context

Full Windows-side regression looked broken for two different reasons that were
easy to conflate: pytest was running under Python 3.12 while the active
MATLAB/RL stack lived under Python 3.14, and an ANDES-only quick script was
crashing collection on machines where ANDES is intentionally not installed.

# Evidence

- `python` resolved to `Python312`, while `py -3.14` resolved to the workspace
  runtime that already had `gymnasium` and `matlabengine` installed.
- The earlier `ModuleNotFoundError: gymnasium` was therefore an interpreter
  mismatch, not a missing repo dependency.
- `tests/test_ne_substep_quick.py` imported `env.andes.andes_ne_env` at module
  import time, so `py -3.14 -m pytest -q` could not complete on Windows
  workspaces that keep ANDES only in WSL.

# What Changed

- Added `utils/gym_compat.py` and routed the Simulink env modules through it so
  import-time contracts stay usable in dependency-light Python environments.
- Marked `tests/test_ne_substep_quick.py` as an optional ANDES test and delayed
  the ANDES env import until the dependency is present.
- Re-ran regression with `py -3.14 -m pytest -q` so the validation uses the
  same Windows interpreter as the MATLAB engine stack.

# Outcome

- Windows full regression now completes under the correct interpreter:
  `373 passed, 26 skipped`.
- Optional ANDES coverage no longer blocks unrelated Simulink and harness
  regression on this workspace.

# Next

- Keep Windows regression commands pinned to `py -3.14` unless the default
  `python` launcher is realigned.
