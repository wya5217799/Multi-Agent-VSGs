# Kundur SPS Workpoint Alignment Diagnostic Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine whether the Kundur SPS/Phasor candidate's actual electrical operating point matches the Newton-Raphson power-flow operating point, then apply the smallest validated repair before returning to Smoke Bridge, 20-episode training, or `.slx` cutover.

**Architecture:** This is a root-cause diagnostic plan, not an RL tuning plan. It treats `gen_emf_deg` versus terminal bus angle as a hypothesis to test, not as a pre-accepted fix; every Simulink read, patch, or runtime check goes through MCP/Simulink-toolbox tools with explicit readback or compile/runtime verification. Exploratory model edits are never saved unless the hypothesis is confirmed and the fix task explicitly says to save.

**Tech Stack:** MATLAB/Simulink SPS `powergui(Phasor)`, repository MCP tools, `simulink-toolbox` MCP routing, existing VSG bridge helpers under `slx_helpers/vsg_bridge/`, Kundur scenario files under `scenarios/kundur/`, and harness evidence under `results/harness/kundur/`.

---

## Scope

This plan replaces the original Task 9 execution order for the current failure mode:

- Observed symptom: `ESS1 Pe = -7.025 pu` from VxI measurement while the expected equilibrium value is about `+0.2 pu` on system base.
- Core question: Does the actual SPS fixed-source network operating point match the `compute_kundur_powerflow` Newton-Raphson operating point?
- Current strong evidence:
  - `pe_vi_scale=0.5` is already configured for SPS peak phasors and only addresses a 2x scale issue.
  - current `kundur_ic.json` has `vsg_delta0_deg[1] = 12.620902...` and `gen_emf_deg[1] = 32.3859`.
  - `build_kundur_sps.m` uses `gen_emf_deg` for fixed conventional/wind source `PhaseAngle`.
  - the same fixed sources are non-ideal and specify source impedance, so `gen_emf_deg` is not automatically wrong; it must be tested against measured SPS bus angles and Pe.

## Non-Goals

- Do not launch 20-episode training until this plan's physical gates pass.
- Do not change reward, SAC hyperparameters, observation/action spaces, or training scripts.
- Do not increase warmup as a physics fix.
- Do not treat `pe_vi_scale` or current sign as the main line unless direct VxI evidence contradicts the current assumption.
- Do not add a new harness task, engine module, or generic utility.
- Do not save exploratory Simulink patches into the candidate `.slx`.
- Do not parse `.slx` XML; use Simulink MCP discovery and trace tools.

## Reusable Probe Placement

The diagnostic MATLAB bodies in this plan should be made reusable before repeated execution.

- Put Kundur-specific, model-semantic diagnostics under `probes/kundur/`.
- Do not put these probes under `scripts/`; `scripts/` is for general repo helpers, while this work is bound to Kundur SPS electrical semantics.
- Do not put these probes under `scenarios/kundur/simulink_models/`; that directory should keep builders/exporters and model-side assets, not reusable diagnosis probes.
- Keep MCP tools as the control surface: use `simulink_load_model`, `simulink_query_params`, `simulink_patch_and_verify`, and snapshots for discovery/readback; use the probe scripts through `simulink_run_script` or `simulink_run_script_async` only for tightly coupled calculations, sweeps, or temporary probe insertion.

Create these reusable probes as part of this plan:

- `probes/kundur/probe_sps_workpoint_alignment.m`
  - Computes/writes `nr_reference.json`, `ess1_vi_baseline.json`, `bus7_angle_probe.json`, and `ess1_phang_sweep.json`.
  - Accepts `(model_name, run_dir, mode)` where `mode` is one of `nr_only`, `vi_only`, `bus7_only`, `sweep_only`, or `all`.
  - Prints stable `RESULT:` lines so MCP quiet runners can capture key fields.
- `probes/kundur/probe_sps_source_angle_hypotheses.m`
  - Runs the source-angle comparison matrix from Task 6.
  - Restores all patched source parameters in an `onCleanup` handler and never saves the model.
  - Writes `source_angle_experiments.json`.

The inline MATLAB snippets below are the concrete implementation bodies for those probes. During execution, move them into the probe files first, then invoke the probes via MCP instead of pasting one-off scripts.

## Files And Artifacts

### Read

- `engine/harness_reference.py`
- `scenarios/contract.py`
- `docs/harness/2026-04-05-simulink-harness-v1.md`
- `results/harness/README.md`
- `docs/devlog/commit-guidelines.md`
- `scenarios/kundur/kundur_ic.json`
- `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m`
- `scenarios/kundur/simulink_models/build_kundur_sps.m`
- `scenarios/kundur/simulink_models/export_kundur_semantic_manifest.m`
- `slx_helpers/vsg_bridge/slx_extract_state.m`
- `scenarios/kundur/config_simulink.py`

### Create Reusable Probes

- `probes/kundur/probe_sps_workpoint_alignment.m`
- `probes/kundur/probe_sps_source_angle_hypotheses.m`

### Generate

- `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/manifest.json`
- `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/scenario_status.json`
- `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/model_inspect.json`
- `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/model_diagnose.json`
- `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/model_report.json`
- `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/summary.md`
- `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/semantic_manifest.json`
- `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/nr_reference.json`
- `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/ess1_vi_baseline.json`
- `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/bus7_angle_probe.json`
- `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/ess1_phang_sweep.json`
- `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/source_angle_experiments.json`

### Modify Only After Root Cause Is Confirmed

- `scenarios/kundur/simulink_models/build_kundur_sps.m`
- `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m`
- `scenarios/kundur/simulink_models/build_powerlib_kundur.m`
- `scenarios/kundur/kundur_ic.json`
- `scenarios/kundur/NOTES.md`
- `docs/paper/experiment-index.md`

## MCP-First Simulink Policy

Use the repository's project routing first, then `simulink-toolbox` for concrete model operations.

- Model discovery: `simulink_load_model`, `simulink_model_status`, `simulink_get_block_tree`, `simulink_explore_block`, `simulink_describe_block_ports`, `simulink_trace_port_connections`.
- Parameter reads: `simulink_query_params`.
- Parameter writes: `simulink_patch_and_verify`; use `simulink_set_block_params` only when a batch cannot be represented atomically, then verify with `simulink_query_params` and `simulink_compile_diagnostics`.
- Runtime checks: `simulink_runtime_reset`, `simulink_workspace_set`, `simulink_run_window`, `simulink_signal_snapshot`, `simulink_step_diagnostics`.
- Long sweeps or tightly coupled MATLAB loops: `simulink_run_script_async` plus `simulink_poll_script`.
- Short aggregation scripts: `simulink_run_script`, only when no dedicated MCP tool can compute the required derived quantities.
- Screenshots, if needed for review: `simulink_screenshot`.
- Save and close only after confirmed fixes: `simulink_save_model`, `simulink_close_model`.

## Decision Criteria

Continue to Smoke Bridge only if all hard criteria pass:

- `slx_extract_state` VxI Pe equals independent manual VxI calculation for ESS1 within numerical tolerance.
- SPS measured Bus7 voltage angle is within `1 deg` of NR `main_bus_ang_abs_deg(1)`.
- ESS1 `phAng_ES1` sweep zero-crossing is within `1 deg` of the NR Bus7 operating angle.
- ESS1 Pe is positive and close to expected equilibrium, not `-7 pu` scale.
- all four ESS Pe signs and magnitudes are physically plausible.
- warmup/technical reset leaves `omega` near `1.0 pu` without a long physics-compensation warmup.

If any hard criterion fails, do not run training; return to the model-side diagnosis tasks below.

---

### Task 0: Add Reusable Kundur Workpoint Probes

**Files:**
- Create: `probes/kundur/probe_sps_workpoint_alignment.m`
- Create: `probes/kundur/probe_sps_source_angle_hypotheses.m`

- [ ] **Step 1: Create the reusable workpoint probe contract**

```text
Step 1: Add `probe_sps_workpoint_alignment.m` with stable inputs and artifacts.
  Tool: apply_patch for the file creation.
  Combine: implementation bodies come from Tasks 2-5 below.
  Verify: the file exposes `function results = probe_sps_workpoint_alignment(model_name, run_dir, mode)` and prints only stable `RESULT:` summary lines for machine capture.
```

Required function contract:

```matlab
function results = probe_sps_workpoint_alignment(model_name, run_dir, mode)
% PROBE_SPS_WORKPOINT_ALIGNMENT
% Reusable Kundur SPS/Phasor workpoint diagnostic.
%
% Modes:
%   nr_only    - write nr_reference.json
%   vi_only    - write ess1_vi_baseline.json
%   bus7_only  - write bus7_angle_probe.json
%   sweep_only - write ess1_phang_sweep.json
%   all        - run all modes above
%
% Contract:
%   - No saved model edits.
%   - JSON artifacts are written under run_dir/attachments.
%   - RESULT lines summarize pass/fail and key angles/Pe values.
```

- [ ] **Step 2: Create the reusable source-angle hypothesis probe contract**

```text
Step 2: Add `probe_sps_source_angle_hypotheses.m` for the Task 6 comparison matrix.
  Tool: apply_patch for the file creation.
  Combine: implementation body comes from Task 6; wrap all temporary parameter edits in `onCleanup`.
  Verify: the function restores baseline `GSrc_*` / `WSrc_*` parameters and closes without saving if an experiment fails.
```

Required function contract:

```matlab
function results = probe_sps_source_angle_hypotheses(model_name, run_dir)
% PROBE_SPS_SOURCE_ANGLE_HYPOTHESES
% Reusable unsaved comparison of EMF-angle and terminal-angle source semantics.
%
% Contract:
%   - Read baseline source parameters first.
%   - Run baseline, G1-terminal-only, all-terminal, and EMF-restore rows.
%   - Restore every patched source parameter with onCleanup.
%   - Write run_dir/attachments/source_angle_experiments.json.
%   - Do not call save_system.
```

- [ ] **Step 3: Smoke the probe entry points without running long sweeps**

```text
Step 3: Verify the probes can be invoked through MCP.
  Tool: simulink_run_script
  Combine: call each probe in its cheapest mode: `probe_sps_workpoint_alignment('kundur_vsg_sps', run_dir, 'nr_only')`; for source-angle probe, call a dry-run/baseline-only mode if implemented, otherwise skip until Task 6.
  Verify: `RESULT:` lines appear, artifacts are written under `results/harness/.../attachments`, and no model dirty state is persisted.
```

---

### Task 1: Create The Evidence Run And Baseline Model Record

**Files:**
- Generate: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/manifest.json`
- Generate: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/scenario_status.json`
- Generate: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/model_inspect.json`
- Generate: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/semantic_manifest.json`

- [ ] **Step 1: Resolve the Kundur scenario**

```text
Step 1: Confirm the supported scenario and model identity.
  Tool: scenario_status
  Combine: read `engine/harness_reference.py` and `scenarios/contract.py` only as project-rule context.
  Verify: scenario_id=`kundur`, registered canonical model remains `kundur_vsg`, and SPS candidate model is treated as a candidate/shadow model until cutover.
```

- [ ] **Step 2: Load the SPS candidate without mutating it**

```text
Step 2: Load `kundur_vsg_sps` and check dirty/status metadata.
  Tool: simulink_load_model
  Combine: simulink_model_status
  Verify: model is loaded, `dirty=false` before diagnostics begin, and file path resolves under `scenarios/kundur/simulink_models/`.
```

- [ ] **Step 3: Inspect solver and compile status**

```text
Step 3: Establish compile and solver baseline.
  Tool: simulink_solver_audit
  Combine: simulink_compile_diagnostics
  Verify: `powergui` is Phasor, no Simscape SolverConfig block is active on the SPS route, and compile diagnostics do not show structural errors before Pe diagnosis.
```

- [ ] **Step 4: Export the semantic manifest as a fact artifact**

```text
Step 4: Export candidate semantic facts.
  Tool: simulink_run_script
  Combine: export_kundur_semantic_manifest is a short aggregation script already present in the repo.
  Verify: `attachments/semantic_manifest.json` exists and records `solver.family=sps_phasor`, `measurement.mode=vi`, and `phase_command_mode=absolute_with_loadflow`.
```

Use this MATLAB payload through `simulink_run_script`:

```matlab
repo = pwd;
model_name = 'kundur_vsg_sps';
out_path = fullfile(repo, 'results', 'harness', 'kundur', ...
    '20260424-kundur-sps-workpoint-alignment', 'attachments', ...
    'semantic_manifest.json');
addpath(fullfile(repo, 'scenarios', 'kundur', 'simulink_models'));
load_system(model_name);
payload = export_kundur_semantic_manifest(model_name, out_path);
fprintf('RESULT: semantic_manifest=%s\n', jsonencode(payload));
```

Expected result:

```text
RESULT: semantic_manifest={"schema_version":1,...}
```

---

### Task 2: Lock The Newton-Raphson Reference Values

**Files:**
- Generate: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/nr_reference.json`
- Read: `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m`
- Read: `scenarios/kundur/kundur_ic.json`

- [ ] **Step 1: Recompute the NR power-flow reference without changing the model**

```text
Step 1: Run the existing NR reference calculation and write a compact reference artifact.
  Tool: simulink_run_script
  Combine: compute_kundur_powerflow is a tightly coupled MATLAB calculation outside direct Simulink signal reads.
  Verify: artifact contains `converged=true`, `max_mismatch`, `main_bus_ang_abs_deg`, `ess_delta_deg`, `gen_delta_deg`, `G1_emf_deg`, and `gen_emf_deg_ext`.
```

Use this MATLAB payload through `simulink_run_script`:

```matlab
% Preferred after Task 0:
%   addpath(fullfile(pwd, 'probes', 'kundur'));
%   results = probe_sps_workpoint_alignment('kundur_vsg_sps', ...
%       fullfile(pwd, 'results', 'harness', 'kundur', ...
%       '20260424-kundur-sps-workpoint-alignment'), 'nr_only');
% The body below is the implementation content for that reusable probe mode.
repo = pwd;
addpath(fullfile(repo, 'scenarios', 'kundur', 'matlab_scripts'));
json_path = fullfile(repo, 'scenarios', 'kundur', 'kundur_ic.json');
out_path = fullfile(repo, 'results', 'harness', 'kundur', ...
    '20260424-kundur-sps-workpoint-alignment', 'attachments', ...
    'nr_reference.json');
pf = compute_kundur_powerflow(json_path);
ref = struct();
ref.converged = logical(pf.converged);
ref.iterations = pf.iterations;
ref.max_mismatch = pf.max_mismatch;
ref.bus_ids = pf.bus_ids(:)';
ref.main_bus_ang_abs_deg = pf.main_bus_ang_abs_deg(:)';
ref.ess_delta_deg = pf.ess_delta_deg(:)';
ref.gen_delta_deg = pf.gen_delta_deg(:)';
ref.G1_terminal_deg = 20.0;
ref.G1_emf_deg = pf.G1_emf_deg;
ref.gen_emf_deg_ext = pf.gen_emf_deg_ext(:)';
fid = fopen(out_path, 'w');
fprintf(fid, '%s\n', jsonencode(ref));
fclose(fid);
fprintf('RESULT: nr_converged=%d max_mismatch=%.3e bus7_abs=%.6f ess1_delta=%.6f G1_terminal=%.6f G1_emf=%.6f\n', ...
    ref.converged, ref.max_mismatch, ref.main_bus_ang_abs_deg(1), ...
    ref.ess_delta_deg(1), ref.G1_terminal_deg, ref.G1_emf_deg);
```

- [ ] **Step 2: Confirm the key angle semantics in the artifact summary**

```text
Step 2: Record the reference-angle relationship.
  Tool: simulink_run_script
  Combine: no model mutation; compute only the comparison fields.
  Verify: `ESS1 delta - Bus7_abs` equals the SMIB equilibrium offset, while `G1_emf - G1_terminal` remains a separate conventional-source hypothesis.
```

Expected interpretation:

```text
ESS1 delta is an internal/source angle.
NR Bus7_abs is the terminal bus voltage angle.
The plan must compare both against SPS-measured angles before choosing a fix.
```

---

### Task 3: Verify The ESS1 VxI Pe Extraction Path

**Files:**
- Generate: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/ess1_vi_baseline.json`
- Read: `slx_helpers/vsg_bridge/slx_extract_state.m`

- [ ] **Step 1: Trace the ESS1 measurement blocks**

```text
Step 1: Locate ESS1 source and V-I measurement wiring.
  Tool: simulink_get_block_tree
  Combine: simulink_explore_block on `kundur_vsg_sps/VSrc_ES1` and `kundur_vsg_sps/Meas_ES1`
  Verify: `VSrc_ES1.PhaseAngle=phAng_ES1`, `Meas_ES1` logs `Vabc_ES1` and `Iabc_ES1`, and no feedback-only Pe path is being used for the SPS candidate.
```

- [ ] **Step 2: Read the V-I measurement parameters**

```text
Step 2: Read ESS1 source and measurement parameters.
  Tool: simulink_query_params
  Combine: query `Voltage`, `PhaseAngle`, `Frequency`, `NonIdealSource`, `SpecifyImpedance`, `Resistance`, and `Inductance` on `VSrc_ES1`; query voltage/current measurement modes on `Meas_ES1`.
  Verify: readback matches the SPS candidate contract and is written into `model_inspect.json`.
```

- [ ] **Step 3: Run a short clean window and snapshot ESS1 signals**

```text
Step 3: Capture ESS1 Vabc/Iabc/omega/delta after a short window.
  Tool: simulink_runtime_reset
  Combine: simulink_workspace_set for `phAng_ES1..4`, `Pe_ES1..4`, `M0_val_ES1..4`, `D0_val_ES1..4`; then simulink_run_window.
  Verify: simulink_signal_snapshot returns nonempty `Vabc_ES1`, `Iabc_ES1`, `omega_ES1`, and `delta_ES1`.
```

- [ ] **Step 4: Compute independent raw Pe and compare with `slx_extract_state`**

```text
Step 4: Compute real/imag, magnitudes, angles, raw power, and scaled Pe.
  Tool: simulink_run_script
  Combine: use a short script because the raw complex vector calculation is derived evidence not exposed by a single signal snapshot call.
  Verify: manual `0.5 * real(sum(Vabc .* conj(Iabc))) / Sbase` equals the bridge Pe value for ESS1 within floating-point tolerance.
```

Use this MATLAB payload through `simulink_run_script` after the short run:

```matlab
% Preferred after Task 0:
%   addpath(fullfile(pwd, 'probes', 'kundur'));
%   results = probe_sps_workpoint_alignment('kundur_vsg_sps', ...
%       fullfile(pwd, 'results', 'harness', 'kundur', ...
%       '20260424-kundur-sps-workpoint-alignment'), 'vi_only');
% The body below is the implementation content for that reusable probe mode.
repo = pwd;
addpath(fullfile(repo, 'slx_helpers', 'vsg_bridge'));
out_path = fullfile(repo, 'results', 'harness', 'kundur', ...
    '20260424-kundur-sps-workpoint-alignment', 'attachments', ...
    'ess1_vi_baseline.json');
model_name = 'kundur_vsg_sps';
Sbase = 100e6;
vi_scale = 0.5;
simOut = sim(model_name, 'StopTime', '0.05');
V_ts = simOut.get('Vabc_ES1');
I_ts = simOut.get('Iabc_ES1');
V = V_ts.Data(end, :);
I = I_ts.Data(end, :);
raw_W = real(sum(V .* conj(I)));
Pe_sys_pu = vi_scale * raw_W / Sbase;
cfg = slx_build_bridge_config('', '', 'omega_ES{idx}', 'Vabc_ES{idx}', ...
    'Iabc_ES{idx}', '', [model_name '/VSrc_ES{idx}'], 200e6, ...
    'delta_ES{idx}', '', 'M0_val_ES{idx}', 'D0_val_ES{idx}', ...
    'vi', 'absolute_with_loadflow', zeros(1, 4), 1.0, ...
    'PeFb_ES{idx}', vi_scale);
[state, meas_failures] = slx_extract_state(simOut, 1:4, cfg, Sbase);
out = struct();
out.V_real = real(V);
out.V_imag = imag(V);
out.V_mag = abs(V);
out.V_angle_deg = angle(V) * 180/pi;
out.I_real = real(I);
out.I_imag = imag(I);
out.I_mag = abs(I);
out.I_angle_deg = angle(I) * 180/pi;
out.raw_W_before_peak_scale = raw_W;
out.vi_scale = vi_scale;
out.Pe_sys_pu = Pe_sys_pu;
out.slx_extract_state_Pe_sys_pu = state.Pe(1);
out.slx_extract_state_failures = meas_failures;
out.diff_manual_minus_extract = Pe_sys_pu - state.Pe(1);
fid = fopen(out_path, 'w');
fprintf(fid, '%s\n', jsonencode(out));
fclose(fid);
fprintf('RESULT: ESS1_raw_W=%.6e ESS1_Pe_manual=%.9f ESS1_Pe_extract=%.9f diff=%.3e VangA=%.6f IangA=%.6f\n', ...
    raw_W, Pe_sys_pu, state.Pe(1), out.diff_manual_minus_extract, ...
    out.V_angle_deg(1), out.I_angle_deg(1));
```

Decision:

- If manual Pe differs from `slx_extract_state`, fix the extraction path before any model physics changes.
- If manual Pe matches `slx_extract_state`, the Pe anomaly is physical/model-side and the next task must measure Bus7.

---

### Task 4: Measure The Actual SPS Bus7 Voltage Angle

**Files:**
- Generate: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/bus7_angle_probe.json`
- Read: `scenarios/kundur/simulink_models/build_kundur_sps.m`

- [ ] **Step 1: Locate Bus7 representatives through MCP discovery**

```text
Step 1: Locate the Bus7 electrical node in the built model.
  Tool: simulink_get_block_tree
  Combine: simulink_explore_block on `kundur_vsg_sps/L_7_12`, `kundur_vsg_sps/Load7`, `kundur_vsg_sps/Shunt7`, and `kundur_vsg_sps/L_7_8a`
  Verify: the Bus7 side of `L_7_12` and the Bus12/ESS1 side are distinguishable before adding any temporary measurement.
```

- [ ] **Step 2: Trace the Bus7-to-ESS1 connection**

```text
Step 2: Confirm the physical connection from ESS1 terminal to Bus7.
  Tool: simulink_describe_block_ports
  Combine: simulink_trace_port_connections from the Bus7-side port of `L_7_12` and the ESS-side port connected to `Meas_ES1`.
  Verify: trace shows `VSrc_ES1 -> Meas_ES1 -> Bus12 -> L_7_12 -> Bus7`; record exact port paths in `model_diagnose.json`.
```

- [ ] **Step 3: Add a temporary Bus7 voltage probe without saving**

```text
Step 3: Add diagnostic-only Bus7 voltage logging.
  Tool: simulink_library_lookup
  Combine: if no existing bus-voltage logger is present, use simulink_run_script for the tightly coupled insert-and-log operation because adding an SPS measurement in series requires line rewiring not exposed as one atomic MCP operation.
  Verify: simulink_compile_diagnostics passes after the temporary probe is inserted, and simulink_model_status reports `dirty=true` only for the unsaved diagnostic session.
```

Use this insertion rule:

```text
Prefer a Three-Phase Voltage Measurement block if the library lookup confirms it exists.
If only Three-Phase V-I Measurement is available, insert it temporarily in series on the Bus7 side of `L_7_12`, log its voltage output as `Vabc_Bus7_probe`, and close the model without saving after the probe run.
```

- [ ] **Step 4: Run a short window and compare three angles**

```text
Step 4: Compare NR Bus7, SPS Bus7, and ESS1 source/terminal angles.
  Tool: simulink_runtime_reset
  Combine: simulink_run_window, then simulink_signal_snapshot for `Vabc_Bus7_probe`, `Vabc_ES1`, and `Iabc_ES1`.
  Verify: `bus7_angle_probe.json` contains NR `bus7_abs`, SPS `bus7_abs_measured`, ESS1 voltage/source angle, ESS1 current angle, and ESS1 Pe.
```

Use this MATLAB payload through `simulink_run_script` only for the angle calculation after snapshots exist:

```matlab
% Preferred after Task 0:
%   addpath(fullfile(pwd, 'probes', 'kundur'));
%   results = probe_sps_workpoint_alignment('kundur_vsg_sps', ...
%       fullfile(pwd, 'results', 'harness', 'kundur', ...
%       '20260424-kundur-sps-workpoint-alignment'), 'bus7_only');
% The body below is the implementation content for that reusable probe mode.
repo = pwd;
out_path = fullfile(repo, 'results', 'harness', 'kundur', ...
    '20260424-kundur-sps-workpoint-alignment', 'attachments', ...
    'bus7_angle_probe.json');
nr_path = fullfile(repo, 'results', 'harness', 'kundur', ...
    '20260424-kundur-sps-workpoint-alignment', 'attachments', ...
    'nr_reference.json');
nr = jsondecode(fileread(nr_path));
V7 = Vabc_Bus7_probe.Data(end, :);
Ves = Vabc_ES1.Data(end, :);
Ies = Iabc_ES1.Data(end, :);
out = struct();
out.nr_bus7_abs_deg = nr.main_bus_ang_abs_deg(1);
out.sps_bus7_phaseA_angle_deg = angle(V7(1)) * 180/pi;
out.ess1_phaseA_angle_deg = angle(Ves(1)) * 180/pi;
out.ess1_current_phaseA_angle_deg = angle(Ies(1)) * 180/pi;
out.ess1_delta0_json_deg = nr.ess_delta_deg(1);
out.angle_error_bus7_deg = out.sps_bus7_phaseA_angle_deg - out.nr_bus7_abs_deg;
out.ess1_minus_bus7_deg = out.ess1_phaseA_angle_deg - out.sps_bus7_phaseA_angle_deg;
fid = fopen(out_path, 'w');
fprintf(fid, '%s\n', jsonencode(out));
fclose(fid);
fprintf('RESULT: nr_bus7=%.6f sps_bus7=%.6f ess1_v=%.6f angle_error=%.6f ess1_minus_bus7=%.6f\n', ...
    out.nr_bus7_abs_deg, out.sps_bus7_phaseA_angle_deg, ...
    out.ess1_phaseA_angle_deg, out.angle_error_bus7_deg, ...
    out.ess1_minus_bus7_deg);
```

Decision:

- If SPS Bus7 is close to NR Bus7 and Pe is still `-7 pu`, investigate V/I sign convention and measurement orientation next.
- If SPS Bus7 is far above ESS1 source angle and far from NR Bus7, Pe being negative is a physical consequence of the wrong network operating point.
- If SPS Bus7 is far from NR Bus7, do not continue to Smoke Bridge.

- [ ] **Step 5: Close or revert the temporary probe session**

```text
Step 5: Ensure temporary measurement edits are not saved.
  Tool: simulink_close_model
  Combine: close with discard/without saving after artifacts are written.
  Verify: reload with simulink_load_model and simulink_model_status; `dirty=false`, and the diagnostic-only probe block is absent from the persisted candidate model.
```

---

### Task 5: Sweep ESS1 Source Angle To Find The SPS Zero-Crossing

**Files:**
- Generate: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/ess1_phang_sweep.json`

- [ ] **Step 1: Lock baseline parameters before the sweep**

```text
Step 1: Read baseline `VSrc_ES1` and workspace-command semantics.
  Tool: simulink_query_params
  Combine: query `kundur_vsg_sps/VSrc_ES1` for `PhaseAngle`, `Voltage`, `Resistance`, and `Inductance`; query `VSrc_ES2..4` for their PhaseAngle expressions.
  Verify: baseline `PhaseAngle=phAng_ES1` and the sweep changes only the base workspace variable, not the block mask.
```

- [ ] **Step 2: Run a controlled phAng sweep**

```text
Step 2: Sweep `phAng_ES1` from 0 deg to 40 deg while holding all other variables fixed.
  Tool: simulink_run_script_async
  Combine: simulink_poll_script every 5-10 seconds because repeated short simulations can exceed synchronous runtime limits.
  Verify: result artifact records `angle_deg`, `Pe_sys_pu`, `V_phaseA_angle_deg`, `I_phaseA_angle_deg`, and `omega` for each sweep point.
```

Use this MATLAB payload through `simulink_run_script_async`:

```matlab
% Preferred after Task 0:
%   addpath(fullfile(pwd, 'probes', 'kundur'));
%   results = probe_sps_workpoint_alignment('kundur_vsg_sps', ...
%       fullfile(pwd, 'results', 'harness', 'kundur', ...
%       '20260424-kundur-sps-workpoint-alignment'), 'sweep_only');
% The body below is the implementation content for that reusable probe mode.
repo = pwd;
model_name = 'kundur_vsg_sps';
out_path = fullfile(repo, 'results', 'harness', 'kundur', ...
    '20260424-kundur-sps-workpoint-alignment', 'attachments', ...
    'ess1_phang_sweep.json');
load_system(model_name);
Sbase = 100e6;
vi_scale = 0.5;
angles = 0:2.5:40;
results = struct([]);
for k = 1:numel(angles)
    assignin('base', 'phAng_ES1', angles(k));
    simOut = sim(model_name, 'StopTime', '0.05');
    V = simOut.get('Vabc_ES1').Data(end, :);
    I = simOut.get('Iabc_ES1').Data(end, :);
    omega = simOut.get('omega_ES1').Data(end);
    Pe = vi_scale * real(sum(V .* conj(I))) / Sbase;
    results(k).angle_deg = angles(k);
    results(k).Pe_sys_pu = Pe;
    results(k).V_phaseA_angle_deg = angle(V(1)) * 180/pi;
    results(k).I_phaseA_angle_deg = angle(I(1)) * 180/pi;
    results(k).omega = omega;
end
zero_cross = NaN;
for k = 2:numel(results)
    p0 = results(k-1).Pe_sys_pu;
    p1 = results(k).Pe_sys_pu;
    if p0 == 0
        zero_cross = results(k-1).angle_deg;
        break;
    end
    if sign(p0) ~= sign(p1)
        a0 = results(k-1).angle_deg;
        a1 = results(k).angle_deg;
        zero_cross = a0 + (0 - p0) * (a1 - a0) / (p1 - p0);
        break;
    end
end
out = struct();
out.results = results;
out.zero_cross_deg = zero_cross;
fid = fopen(out_path, 'w');
fprintf(fid, '%s\n', jsonencode(out));
fclose(fid);
fprintf('RESULT: ESS1_sweep_zero_cross_deg=%.6f points=%d\n', zero_cross, numel(results));
```

Decision:

- If zero-crossing is close to NR Bus7 angle, the ESS source-to-bus relationship is probably correct and the root cause lies elsewhere.
- If zero-crossing is above `20 deg` while NR Bus7 is around the lower Bus7 reference angle, the SPS network operating point is shifted away from NR.

- [ ] **Step 3: Restore the baseline workspace angle**

```text
Step 3: Restore `phAng_ES1` to the JSON/load-flow value after the sweep.
  Tool: simulink_workspace_set
  Combine: read `kundur_ic.json` to set `phAng_ES1=12.620902455474292` and leave `phAng_ES2..4` at their JSON values.
  Verify: one final `simulink_signal_snapshot` shows `phAng_ES1`-driven voltage returned to the baseline angle.
```

---

### Task 6: Test Source-Angle Hypotheses With Minimal Unsaved Patches

**Files:**
- Create: `probes/kundur/probe_sps_source_angle_hypotheses.m` if Task 0 has not already created it
- Generate: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/source_angle_experiments.json`

This task does not implement the fix. It tests whether conventional fixed-source angle semantics are the root cause.

Preferred execution after Task 0:

```text
Step 0: Invoke the reusable source-angle hypothesis probe.
  Tool: simulink_run_script_async
  Combine: add `probes/kundur` to the MATLAB path and call `probe_sps_source_angle_hypotheses('kundur_vsg_sps', run_dir)`.
  Verify: poll until complete; artifact contains baseline, G1-terminal-only, all-terminal, and restored-EMF rows; model is restored and not saved.
```

- [ ] **Step 1: Read baseline conventional-source parameters**

```text
Step 1: Read all conventional/wind source parameters before any patch.
  Tool: simulink_query_params
  Combine: query `GSrc_G1`, `GSrc_G2`, `GSrc_G3`, `WSrc_W1`, and `WSrc_W2`.
  Verify: record `Voltage`, `PhaseAngle`, `NonIdealSource`, `SpecifyImpedance`, `Resistance`, and `Inductance` in `source_angle_experiments.json`.
```

- [ ] **Step 2: Experiment A, baseline rerun**

```text
Step 2: Rerun baseline with current `gen_emf_deg` source angles.
  Tool: simulink_runtime_reset
  Combine: simulink_run_window and simulink_signal_snapshot for ESS Pe and Bus7 probe if still available in the diagnostic session.
  Verify: baseline reproduces the Pe anomaly before any comparison patch is applied.
```

- [ ] **Step 3: Experiment B, G1 terminal-angle-only patch**

```text
Step 3: Patch only `GSrc_G1.PhaseAngle` from current EMF angle to `20.0` terminal angle.
  Tool: simulink_patch_and_verify
  Combine: simulink_compile_diagnostics, simulink_runtime_reset, simulink_run_window, simulink_signal_snapshot.
  Verify: readback shows only G1 source angle changed, compile passes, and artifact records ESS1 Pe and SPS Bus7 angle.
```

Decision:

- If G1-only terminal angle shifts Bus7 strongly toward NR but does not fully fix ESS Pe, test all conventional/wind terminal angles.
- If G1-only terminal angle worsens results, restore baseline and test impedance/network mismatch instead of adopting terminal angles.

- [ ] **Step 4: Experiment C, all conventional/wind terminal angles**

```text
Step 4: Patch all fixed sources to NR terminal bus voltage angles, keeping source impedance unchanged.
  Tool: simulink_patch_and_verify
  Combine: values come from `nr_reference.json`: G1 terminal `20.0`, G2/G3/W1/W2 from `gen_delta_deg`.
  Verify: readback shows only source `PhaseAngle` fields changed, compile passes, ESS1 Pe moves toward expected positive value, and all four ESS Pe values remain plausible.
```

- [ ] **Step 5: Experiment D, impedance-semantics control**

```text
Step 5: If terminal-angle-only looks promising, test whether the fixed source is acting as a terminal source or internal EMF source.
  Tool: simulink_patch_and_verify
  Combine: run a paired control where angles return to EMF values but source impedance settings remain unchanged; do not change impedance and angle in the same comparison row unless the prior rows isolate the effect.
  Verify: artifact shows which single variable explains the Pe sign and magnitude shift.
```

- [ ] **Step 6: Restore the exact baseline or close without saving**

```text
Step 6: Discard exploratory source-angle patches.
  Tool: simulink_patch_and_verify
  Combine: restore baseline `PhaseAngle`, `NonIdealSource`, `SpecifyImpedance`, `Resistance`, and `Inductance` from Step 1; then simulink_close_model without saving if the session was diagnostic-only.
  Verify: reload candidate and query the same parameters; persisted model is unchanged.
```

Decision:

- If terminal angles fix Bus7 and ESS Pe while EMF angles reproduce the fault, implement the terminal-angle source initialization fix in Task 7.
- If EMF angles are required but Bus7 still differs from NR, investigate conventional-source impedance, line/load parameter mismatch, and power-flow model mismatch before changing angle semantics.
- If neither angle hypothesis changes the result materially, revisit measurement placement and current orientation with the Task 3/4 evidence.

---

### Task 7: Implement The Smallest Confirmed Fix

**Files:**
- Modify only if confirmed: `scenarios/kundur/simulink_models/build_kundur_sps.m`
- Modify only if confirmed: `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m`
- Modify only if confirmed: `scenarios/kundur/simulink_models/build_powerlib_kundur.m`
- Modify only if confirmed: `scenarios/kundur/kundur_ic.json`

Choose exactly one repair branch.

## Branch 7A: Fixed Sources Represent Terminal Voltage Sources

Use this branch only if Task 6 proves terminal angles align SPS Bus7 with NR and restore ESS Pe.

- [ ] **Step 1: Add terminal-angle fields to the power-flow artifact path**

```text
Step 1: Extend power-flow outputs so terminal and EMF angles are both explicit.
  Tool: no Simulink edit; code edit via apply_patch.
  Combine: `compute_kundur_powerflow.m` already has terminal angles for G2/G3/W1/W2 as `gen_delta_deg` and G1 terminal as `BUS1_ABS_DEG`.
  Verify: `compute_kundur_powerflow` output includes explicit terminal fields and still reports `converged=true`.
```

Required semantic fields:

```text
pf.G1_terminal_deg = BUS1_ABS_DEG
pf.gen_terminal_deg_ext = gen_delta_deg
pf.G1_emf_deg remains available as metadata
pf.gen_emf_deg_ext remains available as metadata
```

- [ ] **Step 2: Write terminal fields into `kundur_ic.json`**

```text
Step 2: Preserve both terminal and EMF metadata in the JSON IC file.
  Tool: no Simulink edit; code edit via apply_patch.
  Combine: update the JSON-writing path in `build_powerlib_kundur.m`.
  Verify: `kundur_ic.json` contains `gen_terminal_deg`, `wind_terminal_deg`, `gen_emf_deg`, and `wind_emf_deg` with clear units.
```

- [ ] **Step 3: Change `build_kundur_sps.m` to initialize fixed sources from terminal angles**

```text
Step 3: Use terminal bus voltage angles for fixed source PhaseAngle in the SPS candidate.
  Tool: no direct model patch; edit the builder so the model is reproducible.
  Combine: keep EMF angles in JSON as metadata; do not delete them.
  Verify: rebuilding the SPS model gives `GSrc_G1.PhaseAngle=20.0` and G2/G3/W1/W2 terminal angles from JSON.
```

Required behavior:

```text
if terminal angle fields exist:
    use terminal angles for fixed Three-Phase Source PhaseAngle
else:
    fail fast with a clear error for the SPS candidate build
```

Do not silently fall back to EMF angles on the SPS path after this branch is chosen.

## Branch 7B: Fixed Sources Represent Internal EMF Behind Impedance

Use this branch only if Task 6 proves EMF angles are conceptually right but the SPS working point still does not match NR.

- [ ] **Step 1: Do not change source angles**

```text
Step 1: Preserve `gen_emf_deg` as the fixed source PhaseAngle.
  Tool: no edit.
  Combine: use Task 4/6 evidence to identify the mismatch source.
  Verify: source-angle readback remains at EMF values and the next diagnosis targets impedance, load, line, or per-unit conversion.
```

- [ ] **Step 2: Compare source impedance and NR impedance assumptions**

```text
Step 2: Audit source impedance values against `compute_kundur_powerflow.m`.
  Tool: simulink_query_params
  Combine: read `GSrc_*` and `WSrc_*` Resistance/Inductance; compare with the `R_gen_pu_val` and `X_gen_pu_val` conversion in the NR script.
  Verify: artifact states whether source impedance matches NR; if not, patch only the mismatched impedance values with `simulink_patch_and_verify`.
```

- [ ] **Step 3: If impedance must change, update the builder before saving a model**

```text
Step 3: Make the confirmed impedance fix reproducible.
  Tool: no direct save before builder edit.
  Combine: edit `build_kundur_sps.m`, rebuild, then verify with MCP readback.
  Verify: generated `.slx` matches code and passes compile/runtime gates.
```

---

### Task 8: Rebuild And Verify The Candidate After The Fix

**Files:**
- Modify after confirmed fix: `scenarios/kundur/simulink_models/kundur_vsg_sps.slx`
- Generate/update: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/model_patch_verify.json`
- Generate/update: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/model_diagnose.json`
- Generate/update: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/model_report.json`

- [ ] **Step 1: Rebuild the SPS candidate from the edited builder**

```text
Step 1: Rebuild `kundur_vsg_sps.slx` from reproducible code.
  Tool: simulink_run_script_async
  Combine: run `build_kundur_sps` as a replayable builder; poll with `simulink_poll_script`.
  Verify: builder completes, saves `kundur_vsg_sps.slx`, and prints structural check OK.
```

- [ ] **Step 2: Reload and verify source parameters**

```text
Step 2: Verify the rebuilt model, not the in-memory exploratory model.
  Tool: simulink_close_model
  Combine: simulink_load_model, simulink_query_params for `VSrc_ES1`, `GSrc_G1`, `GSrc_G2`, `GSrc_G3`, `WSrc_W1`, `WSrc_W2`.
  Verify: readback matches the confirmed fix branch and no diagnostic-only Bus7 probe block exists in the saved model.
```

- [ ] **Step 3: Compile and run short physical gates**

```text
Step 3: Re-run compile/runtime checks on the rebuilt candidate.
  Tool: simulink_compile_diagnostics
  Combine: simulink_solver_audit, simulink_runtime_reset, simulink_run_window, simulink_signal_snapshot, simulink_step_diagnostics.
  Verify: no structural compile errors; `omega` stays near `1.0`; ESS1 Pe is positive and near expected scale; all four ESS Pe signs and magnitudes are plausible.
```

- [ ] **Step 4: Repeat Tasks 3-5 on the fixed model**

```text
Step 4: Re-run VxI, Bus7 angle, and ESS1 sweep checks.
  Tool: simulink_signal_snapshot
  Combine: simulink_run_script for derived calculations and simulink_run_script_async for the sweep.
  Verify: updated artifacts show VxI calculation consistency, SPS Bus7 aligned with NR Bus7, and ESS1 zero-crossing near the NR Bus7 angle.
```

- [ ] **Step 5: Run the existing zero-action physical validation**

```text
Step 5: Run the reusable Kundur SPS zero-action validation only after MCP gates pass.
  Tool: shell command for the existing Python probe, because it exercises the Python bridge episode path.
  Combine: keep Simulink MCP evidence as the prerequisite; this probe is not a substitute for Tasks 3-5.
  Verify: `probes/kundur/validate_phase3_zero_action.py` reports all hard gates PASS.
```

Run:

```bash
python probes/kundur/validate_phase3_zero_action.py
```

Expected:

```text
VERDICT: ALL PASS
```

---

### Task 9: Decide Whether To Resume Smoke Bridge And Training

**Files:**
- Update: `scenarios/kundur/NOTES.md`
- Update after gates pass: `docs/paper/experiment-index.md`
- Generate/update: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/summary.md`

- [ ] **Step 1: Write the model-side conclusion**

```text
Step 1: Record which hypothesis was confirmed.
  Tool: no Simulink edit.
  Combine: summarize artifacts from Tasks 1-8.
  Verify: `scenarios/kundur/NOTES.md` states which assumptions were confirmed, which attempts were invalid, and whether the final route is terminal bus angle or internal EMF plus impedance.
```

- [ ] **Step 2: Produce the harness model report**

```text
Step 2: Aggregate a compact machine-first report.
  Tool: model_report
  Combine: include paths to all attachment JSON files.
  Verify: report has no profile/manifest drift and no unresolved model-side physical fault.
```

- [ ] **Step 3: Resume Smoke Bridge only if model gates pass**

```text
Step 3: Run Smoke Bridge as a bridge from model validity to training entry.
  Tool: train_smoke_start
  Combine: train_smoke_poll until pass/fail verdict.
  Verify: smoke_passed=true; if smoke fails, route back to Model Harness/diagnosis instead of training.
```

- [ ] **Step 4: Run 20-episode training only after smoke passes**

```text
Step 4: Launch the short training check through the registered launch path.
  Tool: get_training_launch_status
  Combine: launch the returned Kundur command exactly once, then observe with training_status.
  Verify: training starts cleanly at episode 1 with no systemic `omega_saturated`, `Pe=0`, or `Pe=-7 pu` failure mode.
```

Run only after Step 3 passes:

```bash
python scenarios/kundur/train_simulink.py --mode simulink --episodes 20
```

- [ ] **Step 5: Cut over `.slx` only after training evidence is clean**

```text
Step 5: Promote the SPS candidate to canonical Kundur model only after all gates pass.
  Tool: simulink_save_model
  Combine: simulink_close_model before filesystem archival/rename.
  Verify: `scenario_status` still resolves `kundur -> kundur_vsg`, canonical file reloads cleanly, and `model_inspect` reports no profile/manifest drift.
```

Do not cut over if any of these remain unresolved:

- SPS Bus7 angle differs materially from NR Bus7.
- ESS1 Pe is negative or `-7 pu` scale.
- `slx_extract_state` manual Pe comparison fails.
- zero-action validation fails a hard gate.
- Smoke Bridge fails.

---

## Commit And Devlog Guidance

Use one commit per confirmed intent:

```bash
git add results/harness/kundur/20260424-kundur-sps-workpoint-alignment scenarios/kundur/NOTES.md docs/paper/experiment-index.md
git commit -m "docs: record kundur sps workpoint diagnosis"
```

If a model/builder fix is implemented:

```bash
git add scenarios/kundur/simulink_models/build_kundur_sps.m scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m scenarios/kundur/simulink_models/build_powerlib_kundur.m scenarios/kundur/kundur_ic.json scenarios/kundur/simulink_models/kundur_vsg_sps.slx scenarios/kundur/NOTES.md
git commit -m "fix: align kundur sps source initialization with power flow"
```

Write a devlog if the run confirms a new root cause, rules out source-angle semantics, or chooses terminal-angle initialization over internal-EMF initialization.

## Self-Review Checklist

- This plan starts with diagnosis and blocks RL training until model-side physical evidence passes.
- Every Simulink model read uses `simulink_*` discovery/query/snapshot tools.
- Repeated Kundur-specific diagnostics are planned as reusable probes under `probes/kundur/`, not one-off scripts under `scripts/`.
- Every exploratory patch uses `simulink_patch_and_verify` and is restored or discarded before save.
- `simulink_run_script` is limited to existing aggregation scripts or derived complex calculations.
- `simulink_run_script_async` is limited to the phAng sweep and model rebuild.
- `gen_emf_deg` is treated as a hypothesis, not a pre-accepted bug.
- No new harness task, engine module, or utility is introduced.
- All generated evidence lives under `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/`.
