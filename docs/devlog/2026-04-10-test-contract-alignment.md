# 2026-04-10 Test Contract Alignment

## Metadata

- note_id: 2026-04-10-test-contract-alignment
- related_run_id: none
- related_commit: this commit

## Context

Recent cleanup separated runtime artifacts from tracked source files and
introduced a per-run training protocol. The remaining test changes are not
workspace hygiene changes; they align test expectations with the current paper
contract and lightweight research workflow.

## Technical Judgments

- Reward tests should follow the paper Eq. 17 interpretation used by the
  current Simulink environments:
  `r_h = -PHI_H * (mean(delta_M / 2))^2`.
- The reward penalty is a coordination penalty on the global mean adjustment,
  not a per-agent effort penalty on `mean(action_i^2)`.
- Raw opposing actions are not a reliable cancellation test because the
  action-to-delta-M mapping is affine and asymmetric.
- Simulink bridge reset tests should assert that feedback state is cleared
  (`_Pe_prev`, `_delta_prev_deg`) instead of asserting that historical private
  attributes never existed.
- Training and monitor tests should skip gracefully when optional local
  dependencies or generated training artifacts are absent.

## Verification

Command run:

```text
pytest tests/test_fixes.py tests/test_simulink_bridge.py tests/test_monitor.py tests/test_training.py -q
```

Result:

```text
28 passed
```

## Follow-Up

- Keep training outputs under the existing `run_protocol` layout.
- Do not add a new artifact abstraction unless output paths fork again.
- Treat ANDES and ODE as paper comparison backends, not legacy code to archive.
