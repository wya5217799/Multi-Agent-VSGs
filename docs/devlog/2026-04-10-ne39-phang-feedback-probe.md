# 2026-04-10 NE39 phAng Feedback Repair

## Metadata

- note_id: 2026-04-10-ne39-phang-feedback-probe
- related_run_id: `ne39_phang_fix_smoke_20260410d`
- related_commit: this commit

## Context

NE39 Simulink training had a suspected closed-loop feedback issue on:

```text
delta_deg -> phAng_ES* -> VSrc PhaseAngle
```

The existing MCP tools could verify that parameters and simulations were reachable, but they did not provide a repeatable health check for the physical feedback semantics.

## Initial Probe Findings

The initial `vsg_probe_ne39_phang_sensitivity.m` helper ran through MCP and produced stable `RESULT:` fields. The first probe classified the model as `fail`.

Observed evidence:

- `phAng_ES1` is wired into `VSrc_ES1` `PhaseAngle`.
- A first version of the `phAng +30deg` perturbation produced `max_abs_dPe=0` because the test changed warmup initial phase, then the first step overwrote it with warmup `delta_deg`.
- Low/base/high M/D changed omega and delta, but Pe stayed unchanged.
- Open-loop no-delta mode produced zero Pe drift.
- Warmup returned all-zero delta values instead of preserving load-flow initial angles.
- The base delta writeback exceeded the configured reasonable range, with `max_abs_delta_deg 189.252`.

Follow-up ad hoc MCP experiments clarified the split:

- `phAng_ES1` does affect electrical power when injected directly between FastRestart steps: `max_abs_dPe=0.159784` to `0.183724`.
- M/D affects VSG internal `omega` and `delta`.
- Disabling delta feedback freezes Pe across steps, proving the electrical side is open-loop without phase feedback.
- Raw VSG `delta_deg` can exceed hundreds of degrees and must not be used as an absolute VSrc phase angle.

## Root Cause

The failure was not FastRestart failing to reevaluate workspace variables.

The root cause was feedback semantics:

- `phAng_ES{k}` is an absolute VSrc phase-angle command in degrees.
- `delta_deg` is the VSG internal rotor angle output.
- The old writeback used raw `delta_deg` as `phAng_ES{k}`.
- Warmup returns all-zero `delta_deg`, so the first step overwrote the load-flow initial phase angles with zero.
- Later steps could feed raw angles above 180 degrees into VSrc, producing nonphysical electrical power swings.

## Repair

`vsg_step_and_read.m` now separates raw diagnostic delta from the command written to the voltage source:

```text
phAng_cmd_deg(k) = wrapTo180(init_loadflow_phAng(k) + wrapTo180(delta_deg(k)))
```

The helper still returns raw `state.delta_deg` for observation and debugging, and now also returns `state.phAng_cmd_deg` so probes can verify what was actually written to `phAng_ES{k}`.

`vsg_probe_ne39_phang_sensitivity.m` was updated to:

- test step-to-step `phAng` injection rather than warmup-only phase changes,
- report `phAngCmd`,
- verify two-step closed-loop boundedness,
- keep the open-loop no-delta frozen case as a control.

`vsg_close_model.m` now disables FastRestart before closing a loaded model, preventing cleanup failures after training smoke runs.

## Verification

MCP probe:

```text
simulink_run_script("vsg_probe_ne39_phang_sensitivity", timeout_sec=300)
```

Result:

```text
classification = pass
phAng_affects_Pe=1
MD_affects_state=1
open_loop_no_delta_frozen=1
delta_reasonable=1
warmup_preserved=1
closed_loop_two_step_bounded=1
closed_loop_two_step_finite=1
```

NE39 FastRestart smoke:

```text
simulink_run_script("smoke_test_ne39_faststart", timeout_sec=180)
```

Result:

```text
ok=true
vsg_warmup (NE39) completed
no surfaced MATLAB errors
```

FastRestart close cleanup:

```text
load NE39bus_v2
set FastRestart on
vsg_close_model("NE39bus_v2")
```

Result:

```text
close_loaded_after=0
```

Train smoke:

```text
harness_train_smoke_start(run_id="ne39_phang_fix_smoke_20260410d", scenario_id="ne39", episodes=1, mode="simulink")
harness_train_smoke_poll(...)
```

Result:

```text
exit_code=0
smoke_passed=true
episodes_completed=1
last_10_reward_mean=-27396.6738
last_max_freq_dev_hz=11.1059
```

## Follow-Up

- The closed-loop interface blocker is repaired, but one-episode train smoke still reports high maximum frequency deviation (`11.1059 Hz`).
- Treat reward tuning, disturbance magnitude, and action-range calibration as the next layer. Do not interpret this repair as training convergence.
- Keep `vsg_probe_ne39_phang_sensitivity.m` as the regression probe for future NE39 Simulink feedback changes.
