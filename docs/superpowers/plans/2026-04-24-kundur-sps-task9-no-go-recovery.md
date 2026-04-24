# Kundur SPS Task 9 NO-GO Recovery Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze the failed Task 9 path as a NO-GO decision. The core problem is that the Kundur SPS/Phasor static workpoint is not aligned with the NR power-flow reference — Branch 7A only improved Pe sign while Pe magnitude jumped to +4.032 pu against an expected +0.2 pu. Establish a reusable static workpoint gate, collect read-only parameter parity evidence, and stop at each evidence boundary for human review before any model fix is authorized.

**Problem framing:** The root cause of the workpoint misalignment is unknown. Source-angle semantics is one candidate. Other candidates that must be audited equally are: angle reference convention, line model parity (NR uses PI line charging; SPS uses RL-only branches), source impedance conversion, load/shunt parity, base conversion, and measurement point mapping. No candidate is promoted to confirmed root cause without NR-variant evidence.

**Architecture:** This is a model-side root-cause recovery plan. It does not tune SAC, reward, VSG M/D, warmup, omega limits, or training scripts. The plan treats the current terminal-angle Branch 7A as invalidated until direct static workpoint evidence proves otherwise.

**Execution Surface:** Default execution surface is MCP. Shell/MATLAB direct execution is allowed only for file edits, existing Python validation scripts, or tightly coupled probe scripts invoked through `simulink_run_script` / `simulink_run_script_async`.

**Tech Stack:** MATLAB/Simulink SPS Phasor model `kundur_vsg_sps`, MCP Simulink tools, reusable probes under `probes/kundur/`, NR reference from `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m`, and evidence under `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/`.

---

## First Execution Batch

Run Tasks 0-2 and Task 3A in the first execution batch.

Amendment 1 (2026-04-25): human review found evidence-boundary defects after
Task 3A. Insert Task 3B before Task 4. Task 4 remains blocked until Task 3B
writes its evidence-boundary artifact and stops for review.

```text
Allowed in first batch:
  Task 0: Freeze Task 9 as NO-GO
  Task 1: Fix the source-angle experiment gate
  Task 2: Run reusable static workpoint gate baseline
  Task 3A: Run read-only SPS-vs-NR parameter parity audit

Blocked in first batch:
  Task 3B: Evidence boundary repair (requires human review after Task 3A)
  Task 4: NR line-charging variants (requires human review to select branch)
  Task 5: model fix (requires confirmed root cause)
  Task 6: rebuild and zero-action validation (requires Task 5)
  Task 7: Smoke Bridge / training / cutover (requires all model gates)
```

Task 3A is allowed in the first batch because it is **read-only**: it reads files and model parameters but does not patch, save, or modify any `.slx`, builder script, or `kundur_ic.json`. Running it in parallel with Task 2 adds evidence without increasing risk.

**Hard boundary: after Task 3A completes, STOP. Wait for human review before any further action.**

First-batch stop condition — all four must be satisfied:

```text
task9_no_go_decision.json is written
static_workpoint_gate.json is written (Task 2 reusable gate output)
parameter_parity_audit.json is written (Task 3A read-only evidence)
summary.md and NOTES.md clearly state NO-GO and do not recommend Smoke Bridge
```

After these are complete, the agent must stop and present the evidence. The next branch (line_charging / source_impedance / measurement_mapping / other) must be explicitly chosen by the user or lead agent after reviewing both artifacts. An agent may not infer the branch from artifact content alone.

If review identifies evidence-quality or workspace-contamination issues, the
only authorized next action is Task 3B. Task 3B does not authorize Task 4 by
itself; it only repairs the plan boundary and evidence record needed before a
separate Task 4 authorization.

## Current Verdict

Task 9 is not allowed to continue on the original Smoke Bridge and training path.

Current gate values:

```text
model_gate_passed=false
smoke_bridge_allowed=false
training_allowed=false
cutover_allowed=false
```

Reasons:

- `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/model_patch_verify.json` records Branch 7A as `pe_sign_ok=true`, but ESS1 Pe after the terminal-angle change is `+4.0321907579313443 pu`.
- `scenarios/kundur/kundur_ic.json` has `vsg_p0_vsg_base_pu=[0.1,0.1,0.1,0.1]`; with `VSG_SN=200 MVA` and `SBASE=100 MVA`, the expected system-base Pe is `+0.2 pu` for each ESS.
- `+4.03 pu` is a hard physical gate failure. Pe sign improvement is not workpoint alignment.
- `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/summary.md` is stale because it still recommends `Run train_smoke`.
- `scenarios/kundur/NOTES.md` is stale because it still treats terminal angle initialization as the confirmed fix.

Do not update `docs/paper/experiment-index.md` for a paper-facing training result until model gates, Smoke Bridge, and the 20-episode run all pass.

---

## Known Evidence

Use these facts as the starting state. Do not re-derive them from memory.

```text
NR Bus main angles, abs frame [Bus7, Bus8, Bus10, Bus9]:
  [10.913127677225445, 2.9712307723444127, 4.5191269028534364, 1.6089023192225262]

NR ESS delta angles [ES1, ES2, ES3, ES4]:
  [12.620902455474292, 4.684639481298249, 6.22704292802855, 3.3232701266669054]

Expected Pe on system base:
  [0.2, 0.2, 0.2, 0.2] pu

EMF-source baseline evidence:
  ESS1 Pe = -3.536954155800538 pu
  SPS measured main bus angles = [15.180089409742246, 5.9013365191946505, 9.2872197552380715, 5.4134858434722366]
  Main bus angle errors vs NR = [4.2669617325168012, 2.9301057468502378, 4.7680928523846351, 3.8045835242497104] deg

Terminal-all Branch 7A evidence:
  ESS1 Pe = +4.0321907579313443 pu
  VxI manual Pe and slx_extract_state Pe match exactly for ESS1
  Direct Bus7/8/9/10 angles after saved Branch 7A have not yet been recorded as a complete four-ESS static matrix
```

Do not cite `source_angle_experiments.json` field `conclusion.terminal_fix_promising=true` as a valid conclusion. That field was based on sign only and is now invalidated.

---

## Hard Gates

The model can re-enter Smoke Bridge only after all hard gates pass.

Use these thresholds for the static gates:

```text
all reported angles normalized to the same absolute simulation frame
manual_vi_diff_abs <= 1e-6 pu
abs(sps_main_bus_angle_deg - nr_main_bus_angle_deg) <= 1.0 deg for Bus7, Bus8, Bus10, Bus9
abs((ess_angle_deg - main_bus_angle_deg) - nr_expected_angle_diff_deg) <= 1.0 deg for all four ESS
abs(Pe_sys_pu - expected_Pe_sys_pu) <= 0.05 pu for all four ESS
no ESS Pe has the wrong sign
no ESS Pe has multi-pu magnitude
validate_phase3_zero_action.py hard verdict PASS
```

The final zero-action validation keeps its existing stricter dynamic criteria:

```text
C0 early Pe convergence < 10 percent by step 5
C1 steady Pe deviation < 5 percent
C3 omega deviation < 0.002 pu
C4 delta drift < 1 deg/step
C5 no -90 deg false stability
```

---

## Angle Reference Normalization

All static matrix angle comparisons must use one reference convention.

```text
angle_unit=deg
reference_frame=absolute_simulation_frame
normalization=wrap_to_180
range=[-180, 180)
```

Required helper behavior for every angle field:

```matlab
function y = wrap_to_180(x)
    y = mod(x + 180, 360) - 180;
end

function d = angle_diff_deg(a, b)
    d = wrap_to_180(a - b);
end
```

Rules:

- Store raw measured angles and normalized angles when possible.
- Gate comparisons must use `angle_diff_deg`, not naked subtraction.
- NR angles, SPS bus angles, ESS source/terminal angles, and source `PhaseAngle` readback must state the frame and normalization in the artifact.
- `source PhaseAngle` semantics and `VSrc_ES{i}.PhaseAngle=phAng_ES{i}` command semantics must be recorded separately; do not infer one from the other.

---

## Files And Artifacts

Read before implementation:

- `engine/harness_reference.py`
- `scenarios/contract.py`
- `docs/harness/2026-04-05-simulink-harness-v1.md`
- `results/harness/README.md`
- `docs/devlog/commit-guidelines.md`
- `docs/superpowers/plans/2026-04-24-kundur-sps-workpoint-alignment.md`
- `scenarios/kundur/NOTES.md`
- `scenarios/kundur/kundur_ic.json`
- `scenarios/kundur/config_simulink.py`
- `scenarios/kundur/model_profiles/kundur_sps_candidate.json`
- `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m`
- `scenarios/kundur/simulink_models/build_kundur_sps.m`
- `scenarios/kundur/simulink_models/build_powerlib_kundur.m`
- `slx_helpers/vsg_bridge/slx_extract_state.m`
- `probes/kundur/probe_sps_workpoint_alignment.m`
- `probes/kundur/probe_sps_source_angle_hypotheses.m`
- `probes/kundur/validate_phase3_zero_action.py`

Modify or create during this recovery:

- Create (Task 0): `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/task9_no_go_decision.json`
- Create (Task 2, reusable gate): `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/static_workpoint_gate.json`
- Create (Task 3A, read-only, first batch): `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/parameter_parity_audit.json`
- Create (Task 3B, evidence-boundary repair): `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/task3b_evidence_boundary_review.json`
- Create after Task 2+3A+3B review: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/nr_variant_line_charging.json`
- Modify: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/summary.md`
- Modify: `scenarios/kundur/NOTES.md`
- Modify if needed: `probes/kundur/probe_sps_source_angle_hypotheses.m`
- Modify if needed: `probes/kundur/probe_sps_workpoint_alignment.m`
- Create (reusable gate probe): `probes/kundur/probe_sps_static_workpoint_gate.m`
- Modify if needed (Task 3B only, evidence bug fix): `probes/kundur/probe_sps_static_workpoint_gate.m`
- Create (read-only parity probe): `probes/kundur/probe_sps_parameter_parity_audit.m`
- Create if NR-only variant needed: `probes/kundur/probe_kundur_nr_parity_variants.m`

**PROHIBITED until root cause is confirmed and Task 2 review has been completed:**

- `scenarios/kundur/simulink_models/build_kundur_sps.m`
- `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m`
- `scenarios/kundur/simulink_models/build_powerlib_kundur.m`
- `scenarios/kundur/kundur_ic.json`
- `scenarios/kundur/simulink_models/kundur_vsg_sps.slx`
- `docs/paper/experiment-index.md`

These files must not be edited, patched, or overwritten during Tasks 0-4 or in any probe run, regardless of what a probe result suggests. Only Task 5 (Implement Only The Confirmed Static Network Fix) may modify these files, and only after the Task 2 matrix review has explicitly authorized a specific fix branch.

---

## Plan Horizon and Replanning Policy

Each execution batch has a short, bounded horizon. Agents must not cross a batch boundary without a new plan or explicit human authorization.

Rules:

```text
1. Each batch ends at a concrete artifact or gate.
   Do not continue until that artifact exists and has been reviewed.

2. If new evidence invalidates the current working hypothesis, STOP immediately.
   Do not continue downstream tasks because they are already written in this plan.
   Write a plan amendment or ask for human direction before proceeding.

3. If the next action is outside the authorized batch, write a new plan or plan amendment first.
   Probe results may guide replanning. They do not authorize scope expansion automatically.

4. Exploratory actions (probing a branch not in the authorized batch, trying a parameter fix
   "just to see") are prohibited unless explicitly listed in an authorized task step.

5. Every plan amendment must state:
   - what new evidence triggered the amendment
   - which old assumption was invalidated
   - what is now authorized
   - what remains prohibited
   - what artifact ends the next batch
```

### Amendment 1: Evidence Boundary Repair Before Task 4

New evidence that triggered this amendment:

```text
1. Task 3A review found prohibited production files dirty before Task 4:
   build_kundur_sps.m, compute_kundur_powerflow.m, build_powerlib_kundur.m,
   kundur_ic.json, kundur_vsg_sps.slx, and config_simulink.py.
2. static_workpoint_gate.json records sps_main_bus_angle_deg as an ESS terminal
   voltage proxy, not a direct Bus7/8/10/9 measurement.
3. static_workpoint_gate.json has an evidence-recording bug: ess_rows.block
   is VSrc_ES4 for all rows because the probe reuses a stale row struct.
4. scenarios/kundur/NOTES.md still contains stale Branch 7A confirmed language
   that conflicts with the Task 9 NO-GO decision.
```

Old assumptions invalidated:

```text
1. Task 2 output is still a useful failure gate, but it is not a clean direct
   main-bus angle matrix.
2. Task 0-3A did not leave the evidence boundary clean enough to enter Task 4.
3. Human review of Task 2+3A is not sufficient unless the dirty production-file
   state and artifact limitations are recorded first.
```

Now authorized:

```text
Task 3B only:
  - Update NOTES.md so the active state says Branch 7A is invalidated by Pe
    magnitude and static workpoint gates.
  - Fix or clearly label the static gate probe evidence bug in
    probe_sps_static_workpoint_gate.m.
  - Write task3b_evidence_boundary_review.json documenting dirty production
    files, Task 2 artifact limitations, and the exact remaining Task 4 block.
```

Still prohibited:

```text
Task 4 is not authorized by this amendment.
No NR variant may be run inside Task 3B.
No Simulink model may be saved.
No production model/reference files may be edited:
  build_kundur_sps.m
  build_powerlib_kundur.m
  compute_kundur_powerflow.m
  kundur_ic.json
  kundur_vsg_sps.slx
  config_simulink.py
No training, Smoke Bridge, cutover, or paper-facing experiment update is allowed.
```

Artifact ending the amended batch:

```text
results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/task3b_evidence_boundary_review.json
```

Prohibited inference chains — an agent must not internally reason its way to any of these:

```text
line charging looks suspicious → patch build_kundur_sps.m
source impedance looks suspicious → change .slx
angle result looks better → start Smoke Bridge
Pe sign improved → run training
probe output contradicts hypothesis → try another source-angle mode without authorization
```

Evidence may trigger a new plan. It does not trigger an action.

### Amendment 2: Measurement Point Mapping Branch After Batch 3

New evidence that triggered this amendment:

```text
NR line-charging variant (Batch 3 / Task 4) rejected:
  NR without line-charging moved Bus angles further from SPS EMF-baseline.
  delta_mae = -0.036 deg (wrong direction).
  Branch 5A / line-charging parity is excluded.
```

Old assumption invalidated:

```text
Line-charging mismatch was the primary root-cause candidate.
It is now excluded. The angle bias source is elsewhere.
```

Now authorized:

```text
Measurement Point Mapping — read-only / probe-only:
  Read model topology to identify which physical node the SPS angle measurement
  corresponds to, and compare it to the NR Bus 7/8/10/9 terminal bus voltage angle.
  Write measurement_point_mapping.json and a short summary.
  STOP after writing these two outputs.
```

Still prohibited:

```text
Any edit to SPS/SLX, build scripts, bridge files, kundur_ic.json, or training scripts.
Auto-entry into source impedance, angle reference, transformer taps, load sign,
or generator model branches without explicit human authorization after mapping review.
```

Artifact ending this batch:

```text
results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/measurement_point_mapping.json
```

---

## Mandatory STOP Triggers

The agent must stop immediately and report to the user or lead agent if any of the following conditions are detected:

```text
1. Any ESS Pe has multi-pu magnitude (abs(Pe_sys_pu) > 1.0 pu) under any configuration.
2. Any source-angle configuration improves Pe sign but fails the Pe magnitude gate
   (abs(Pe_sys_pu - expected_Pe_sys_pu) > 0.05 pu).
3. SPS/NR main-bus angle error exceeds 1.0 deg for any bus after a source-angle patch.
4. Simulink model is dirty after a probe returns (onCleanup did not fire correctly).
5. Probe output contradicts the current working hypothesis.
6. A diagnostic branch (e.g., Task 4 NR variants) is not explicitly authorized by the current batch.
7. A proposed action would modify any of: build_kundur_sps.m, build_powerlib_kundur.m,
   compute_kundur_powerflow.m, kundur_ic.json, kundur_vsg_sps.slx, or any training script —
   before root-cause confirmation and explicit Task 2+3A+3B review authorization.
8. Task 4 is about to run before task3b_evidence_boundary_review.json exists and has
   been reviewed after the Amendment 1 evidence-boundary repair.
9. The agent has spent ~5000 tokens with no passing gate, no confirmed tool call, and no
   artifact written (token circuit-breaker).
```

On any STOP trigger: write a short observation to the relevant NOTES.md or summary.md, present findings to the user, and do not proceed.

---

## Simulink Policy

Use MCP tools for model operations.

```text
Step: Load or inspect models
  Tool: simulink_load_model, simulink_model_status, simulink_get_block_tree, simulink_explore_block
  Verify: model is loaded, dirty state is known, candidate remains `kundur_vsg_sps`

Step: Read parameters
  Tool: simulink_query_params
  Verify: readback is written into the relevant JSON artifact

Step: Temporary source-angle patch
  Tool: simulink_patch_and_verify
  Verify: query params after patch, run short check, restore with readback, close without saving

Step: Tightly coupled static probe or NR variant
  Tool: simulink_run_script or simulink_run_script_async
  Verify: stable `RESULT:` lines and JSON artifacts under `results/harness/.../attachments`
```

### Dirty-State Protection (mandatory for every probe in this plan)

1. **Before every probe:** call `simulink_model_status` and record the dirty flag. If the model is already dirty before the probe starts, stop and investigate — do not run the probe on an unsaved intermediate state.

2. **All temporary parameter changes** (source PhaseAngle, VSrc params, line variants) MUST be wrapped in an `onCleanup` object in the MATLAB probe function. The cleanup must restore every patched parameter to its pre-probe value.

3. **After every probe:** call `simulink_model_status` again. If the model is dirty after the probe returns, the `onCleanup` did not fire correctly. In that case:
   - Do NOT save the model.
   - Close the model without saving using `simulink_close_model` (close_without_saving=true).
   - Reload from disk using `simulink_load_model` before any further operation.

4. **`simulink_save_model` is prohibited** in Tasks 0-4 and in any exploratory probe. It may only be called in Task 5 or later, and only when the task step explicitly says "save after confirmation". No probe, gate check, or diagnostic step is authorized to save.

---

### Task 0: Freeze Task 9 As NO-GO

**Files:**
- Create: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/task9_no_go_decision.json`
- Modify: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/summary.md`
- Modify: `scenarios/kundur/NOTES.md`

- [ ] **Step 1: Write the machine-readable NO-GO artifact**

Create `task9_no_go_decision.json` with this exact semantic shape:

```json
{
  "schema_version": 1,
  "scenario_id": "kundur",
  "run_id": "20260424-kundur-sps-workpoint-alignment",
  "decision": "NO_GO",
  "model_gate_passed": false,
  "smoke_bridge_allowed": false,
  "training_allowed": false,
  "cutover_allowed": false,
  "invalidated_conclusions": [
    {
      "field": "source_angle_experiments.conclusion.terminal_fix_promising",
      "reason": "The old criterion used Pe sign only. Terminal-all Pe is +4.032 pu while expected Pe is +0.2 pu."
    },
    {
      "field": "model_patch_verify.pe_sign_ok",
      "reason": "Pe sign is insufficient. Magnitude and static workpoint gates failed."
    }
  ],
  "blocking_fault": {
    "class": "sps_static_workpoint_alignment",
    "summary": "Kundur SPS/Phasor candidate is not aligned with NR static workpoint.",
    "evidence": {
      "expected_ess_pe_sys_pu": [0.2, 0.2, 0.2, 0.2],
      "emf_baseline_ess1_pe_sys_pu": -3.536954155800538,
      "terminal_all_ess1_pe_sys_pu": 4.0321907579313443,
      "emf_baseline_bus_angle_error_deg": [4.2669617325168012, 2.9301057468502378, 4.7680928523846351, 3.8045835242497104]
    }
  },
  "blocked_actions": [
    "train_smoke_start",
    "train_smoke_poll",
    "python scenarios/kundur/train_simulink.py --mode simulink --episodes 20",
    "simulink_save_model for cutover",
    "canonical .slx promotion"
  ],
  "next_required_plan": "2026-04-24-kundur-sps-task9-no-go-recovery.md"
}
```

Verify:

```powershell
Get-Content -LiteralPath 'results\harness\kundur\20260424-kundur-sps-workpoint-alignment\attachments\task9_no_go_decision.json' -Encoding UTF8
```

Expected: JSON parses visually and contains all four `*_allowed=false` fields.

- [ ] **Step 2: Replace stale summary recommendation**

Edit `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/summary.md` so it starts with:

```markdown
Run status: `failed`

Task 9 verdict: `NO_GO`

Blocked:
- Smoke Bridge
- 20-episode training
- SPS candidate cutover

Reason:
- Branch 7A terminal-angle change made ESS1 Pe positive, but Pe is +4.032 pu instead of the expected +0.2 pu.
- The previous `terminal_fix_promising=true` conclusion used Pe sign only and is invalidated.

Next action:
- Run the four-ESS static workpoint matrix first. Do not start parameter parity, line charging, or other root-cause branches until the matrix has been reviewed.
```

Verify:

```powershell
Select-String -LiteralPath 'results\harness\kundur\20260424-kundur-sps-workpoint-alignment\summary.md' -Pattern 'NO_GO|Smoke Bridge|4.032|terminal_fix_promising'
```

Expected: all four patterns are present.

- [ ] **Step 3: Correct `scenarios/kundur/NOTES.md` active state**

Replace the current "Branch 7A confirmed" wording in `scenarios/kundur/NOTES.md` with:

```markdown
- SPS candidate `kundur_vsg_sps` is currently blocked at Task 9 NO-GO (2026-04-24).
  Branch 7A terminal-angle initialization is invalidated as a complete fix:
  ESS1 Pe changed from -3.537 pu to +4.032 pu, but expected Pe is about +0.2 pu.
  Pe sign improvement is not workpoint alignment.
  Smoke Bridge, 20-episode training, and `.slx` cutover are blocked until static workpoint gates pass.
  Next diagnosis: compare NR vs SPS static workpoint for all four ESS/main-bus pairs and audit SPS-vs-NR parameter parity.
```

Verify:

```powershell
Select-String -LiteralPath 'scenarios\kundur\NOTES.md' -Pattern 'NO-GO|4.032|Smoke Bridge|blocked|Pe sign'
```

Expected: the active note no longer says to run Smoke Bridge next.

---

### Task 1: Fix The Source-Angle Experiment Gate

**Files:**
- Modify: `probes/kundur/probe_sps_source_angle_hypotheses.m`
- Generate/update: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/source_angle_experiments.json`

- [ ] **Step 1: Replace sign-only terminal gate**

Current bad logic:

```matlab
conclusion.terminal_fix_promising = (exp_C.Pe_sys_pu > 0) && (exp_A.Pe_sys_pu < 0);
```

Replace it with magnitude-aware fields. Use the expected system-base Pe from `kundur_ic.json` instead of a hardcoded `0.2` inside the probe.

Required logic:

```matlab
expected_pe_sys = 0.1 * (200e6 / 100e6);  % fallback only if JSON read fails
try
    repo = fileparts(fileparts(fileparts(mfilename('fullpath'))));
    addpath(fullfile(repo, 'slx_helpers', 'vsg_bridge'));
    ic = slx_load_kundur_ic(fullfile(repo, 'scenarios', 'kundur', 'kundur_ic.json'));
    expected_pe_sys = ic.vsg_p0_vsg_base_pu(1) * (200e6 / 100e6);
catch
end

abs_tol = 0.05;
sign_improved = (exp_C.Pe_sys_pu > 0) && (exp_A.Pe_sys_pu < 0);
terminal_magnitude_ok = abs(exp_C.Pe_sys_pu - expected_pe_sys) <= abs_tol;

conclusion.expected_ess1_pe_sys_pu = expected_pe_sys;
conclusion.abs_tol_sys_pu = abs_tol;
conclusion.terminal_sign_improved = sign_improved;
conclusion.terminal_magnitude_ok = terminal_magnitude_ok;
conclusion.terminal_fix_promising = sign_improved && terminal_magnitude_ok;
conclusion.invalid_if_sign_only = sign_improved && ~terminal_magnitude_ok;
```

Verify:

```text
RESULT: ... terminal_fix_promising=0
```

Expected for current evidence: `terminal_sign_improved=true`, `terminal_magnitude_ok=false`, `terminal_fix_promising=false`.

- [ ] **Step 2: Re-run the source-angle hypothesis probe without saving the model**

Use MCP:

```text
Step: Run source-angle gate with restored current model state.
  Tool: simulink_run_script_async
  Combine: add `probes/kundur` to MATLAB path and call:
           probe_sps_source_angle_hypotheses('kundur_vsg_sps', fullfile(pwd, 'results', 'harness', 'kundur', '20260424-kundur-sps-workpoint-alignment'))
  Verify: source params are restored by `onCleanup`; no `save_system` call; JSON conclusion has `terminal_fix_promising=false`.
```

Do not proceed if the model remains dirty after the probe. Close without saving and reload before any further diagnosis.

---

### Task 2: Build Reusable Static Workpoint Gate Baseline

**Files:**
- Create (primary): `probes/kundur/probe_sps_static_workpoint_gate.m`
- Generate: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/static_workpoint_gate.json`
- Retire: `probe_sps_static_workpoint_matrix.m` — use the gate probe instead

**Design intent:** This probe is a **long-term reusable model quality gate**, not a one-off Task 9 debug script. After this recovery, it should be runnable before any model change, after every rebuild, and before every Smoke Bridge attempt — always producing the same JSON schema so artifacts can be compared directly across runs.

**Nature of this task:** `static_workpoint_gate.json` is routing evidence, not a root-cause conclusion. It characterizes the four ESS/main-bus pairs across multiple source-angle configurations by measuring Pe, angle difference, main-bus angle error, and manual VxI consistency. It can tell which configurations fail the static gates and which is least wrong. It cannot identify *why* a configuration fails. Do not declare a root cause inside this task.

This task ends the evidence-collection half of the first batch. Continue to Task 3A (read-only parameter audit) before stopping. STOP after Task 3A completes.

- [ ] **Step 1: Create the reusable static workpoint gate probe**

Create `probes/kundur/probe_sps_static_workpoint_gate.m` as a new file. The required function signature is:

```matlab
function results = probe_sps_static_workpoint_gate(model_name, run_dir, opts)
% opts is a struct with optional fields:
%   opts.source_angle_modes  — cell array of mode labels, default {'persisted_current','emf_reference','terminal_reference'}
%   opts.gate_thresholds     — struct with fields angle_deg (default 1.0), pe_pu (default 0.05), vi_diff (default 1e-6)
%   opts.output_filename     — default 'static_workpoint_gate.json'
%   opts.allow_temporary_source_patch — default true; set false for read-only runs
```

The `source_angle_modes` parameter is extensible: future hypotheses can be added by passing a new label without rewriting the probe.

Required behavior:

```text
- Load `nr_reference.json` from run_dir; if missing, compute it first using `compute_kundur_powerflow`.
- Read current persisted source PhaseAngle values for GSrc_G1, GSrc_G2, GSrc_G3, WSrc_W1, WSrc_W2.
- Read VSrc_ES1..4 parameters: Voltage, PhaseAngle, Frequency, NonIdealSource, SpecifyImpedance, Resistance, Inductance.
- Normalize all NR and SPS angles with `wrap_to_180`; compute all angle errors with `angle_diff_deg`.
- For each mode in source_angle_modes, run without saving; restore all source params through onCleanup.
- Measure all four ESS pairs: ES1/Bus7, ES2/Bus8, ES3/Bus10, ES4/Bus9.
- For each ESS pair, record commanded source angle and measured ESS terminal V-I angle and Pe.
- Compute manual V×I Pe and compare with slx_extract_state Pe.
- Write output_filename under run_dir/attachments/.
- Print one RESULT line per configuration.
```

Source-angle configuration semantics:

```text
`persisted_current` answers: what is the saved candidate doing now?
`emf_reference` answers: what happens if conventional/wind fixed sources use internal EMF angles?
`terminal_reference` answers: what happens if conventional/wind fixed sources use terminal bus voltage angles?

None of these labels means the configuration is physically correct. Correctness is decided only by the static gates.
```

Required top-level JSON schema (shared by Task 2 baseline, Task 6 post-fix, and model_report):

```json
{
  "schema_version": 2,
  "scenario_id": "kundur",
  "model_name": "kundur_vsg_sps",
  "run_id": "20260424-kundur-sps-workpoint-alignment",
  "probe_config": {
    "source_angle_modes": ["persisted_current", "emf_reference", "terminal_reference"],
    "gate_thresholds": {
      "angle_deg": 1.0,
      "pe_pu": 0.05,
      "vi_diff": 1e-6
    },
    "output_filename": "static_workpoint_gate.json"
  },
  "angle_convention": {
    "unit": "deg",
    "reference_frame": "absolute_simulation_frame",
    "normalization": "wrap_to_180",
    "range": "[-180, 180)"
  },
  "nr_reference": {
    "main_bus_angles_deg": {"Bus7": 10.9131, "Bus8": 2.9712, "Bus10": 4.5191, "Bus9": 1.6089},
    "ess_angles_deg": {"ES1": 12.6209, "ES2": 4.6846, "ES3": 6.2270, "ES4": 3.3233}
  },
  "sps_readback": {
    "GSrc_G1_phase_angle_deg": null,
    "GSrc_G2_phase_angle_deg": null,
    "GSrc_G3_phase_angle_deg": null,
    "WSrc_W1_phase_angle_deg": null,
    "WSrc_W2_phase_angle_deg": null
  },
  "configs": [
    {
      "config_label": "emf_reference",
      "config_semantics": "conventional/wind source PhaseAngle values set to internal EMF angles; no correctness claim",
      "source_phase_angles_deg": {
        "GSrc_G1": 32.3859,
        "GSrc_G2": 29.0539,
        "GSrc_G3": 19.3749,
        "WSrc_W1": 17.0696,
        "WSrc_W2": 4.8839
      },
      "vsrc_readback": [
        {
          "block": "kundur_vsg_sps/VSrc_ES1",
          "PhaseAngle": "phAng_ES1",
          "Voltage": "230000",
          "Frequency": "50",
          "NonIdealSource": "on",
          "SpecifyImpedance": "on",
          "Resistance": "0.7935",
          "Inductance": "0.25258"
        }
      ],
      "ess_rows": [
        {
          "ess": "ES1",
          "main_bus": "Bus7",
          "nr_main_bus_angle_raw_deg": 10.913127677225445,
          "nr_main_bus_angle_deg": 10.913127677225445,
          "sps_main_bus_angle_raw_deg": 15.180089409742246,
          "sps_main_bus_angle_deg": 15.180089409742246,
          "nr_ess_angle_raw_deg": 12.620902455474292,
          "nr_ess_angle_deg": 12.620902455474292,
          "sps_ess_angle_raw_deg": 12.620902455474292,
          "sps_ess_angle_deg": 12.620902455474292,
          "vsrc_phaseangle_expression": "phAng_ES1",
          "vsrc_phaseangle_command_deg": 12.620902455474292,
          "nr_angle_diff_deg": 1.7077747782488473,
          "sps_angle_diff_deg": -2.559186954267954,
          "main_bus_angle_error_deg": 4.2669617325168012,
          "angle_diff_error_deg": -4.2669617325168012,
          "expected_pe_sys_pu": 0.2,
          "measured_pe_sys_pu": -3.536954155800538,
          "manual_vi_pe_sys_pu": -3.536954155800538,
          "manual_vi_diff_abs": 0.0,
          "passes_angle_gate": false,
          "passes_pe_gate": false
        }
      ],
      "gate_results": {
        "all_angle_gates_pass": false,
        "all_pe_gates_pass": false,
        "all_vi_gates_pass": true
      },
      "aggregate_errors": {
        "mean_main_bus_angle_error_deg": 3.94,
        "max_main_bus_angle_error_deg": 4.77,
        "mean_pe_error_pu": 3.74,
        "max_pe_error_pu": 3.74
      }
    }
  ],
  "provenance": {
    "probe_file": "probes/kundur/probe_sps_static_workpoint_gate.m",
    "run_timestamp": "",
    "matlab_model_dirty_before": false,
    "matlab_model_dirty_after": false
  }
}
```

After all configs are measured, the probe appends a single `verdict_summary` object at the end of the JSON:

```json
{
  "verdict_summary": {
    "any_config_passes_all_static_gates": false,
    "best_config_by_pe_error": "emf_reference",
    "best_config_by_angle_error": "emf_reference",
    "terminal_reference_has_multi_pu_pe": true,
    "emf_reference_has_negative_pe": true,
    "recommended_next_branch": "review_required"
  }
}
```

Rules for `verdict_summary`:
- `any_config_passes_all_static_gates`: true only if at least one config has `all_angle_gates_pass=true` AND `all_pe_gates_pass=true` for all four ESS rows.
- `best_config_by_pe_error`: label of the config with the smallest mean `abs(measured_pe_sys_pu - expected_pe_sys_pu)` across four ESS.
- `best_config_by_angle_error`: label of the config with the smallest mean `main_bus_angle_error_deg` across four ESS.
- `terminal_reference_has_multi_pu_pe`: true if any ESS in `terminal_reference` has `abs(measured_pe_sys_pu) > 1.0 pu`.
- `emf_reference_has_negative_pe`: true if any ESS in `emf_reference` has `measured_pe_sys_pu < 0`.
- `recommended_next_branch`: **MUST be `"review_required"` in the first execution batch.** The probe is not authorized to write any other value (e.g., `"line_charging"`, `"source_impedance"`). The next branch is selected by human review only.

The numbers above illustrate known EMF-baseline values for ES1; the probe must compute the live values for every row.

- [ ] **Step 2: Measure current saved Branch 7A directly**

Run:

```text
Step: Measure `persisted_current`.
  Tool: simulink_load_model
  Combine: simulink_query_params for GSrc/WSrc source PhaseAngle values and VSrc_ES1..4 readback;
           then simulink_run_script_async for the gate probe:
           probe_sps_static_workpoint_gate('kundur_vsg_sps', run_dir)
  Verify: JSON sps_readback records persisted source angles; JSON includes VSrc_ES1..4 readback;
          provenance.matlab_model_dirty_after=false.
```

Expected current saved source angles if Branch 7A is persisted:

```text
GSrc_G1=20
GSrc_G2=15.9238
GSrc_G3=6.2138
WSrc_W1=3.3236
WSrc_W2=2.9881
```

If source readback does not match those values, record the actual values and treat `persisted_current` as a separate configuration.

- [ ] **Step 3: Compare EMF vs terminal configurations with complete gates**

Run:

```text
Step: Compare source-angle configurations.
  Tool: simulink_run_script_async
  Combine: probe_sps_static_workpoint_gate('kundur_vsg_sps', run_dir)
  Verify: static_workpoint_gate.json contains configs for emf_reference, terminal_reference, and persisted_current;
          verdict_summary.recommended_next_branch = "review_required";
          provenance.matlab_model_dirty_after = false.
```

Decision (observation only — do not act on these without human authorization):

```text
If terminal_reference has any Pe near +4 pu or any multi-pu Pe → record in verdict_summary; Branch 7A remains invalid.
If emf_reference has Bus7/8/10/9 angle errors around 3-5 deg and Pe negative → record; source-angle semantics alone are not the root cause.
If neither configuration passes all angle and Pe gates → record; continue to Task 3A for parameter parity evidence.
```

Task 2 completion condition:

```text
static_workpoint_gate.json is written with all three configs and a verdict_summary.
Continue to Task 3A immediately — do not stop between Task 2 and Task 3A.
STOP after Task 3A.
```

---

### Task 3A: Read-Only SPS-vs-NR Parameter Parity Audit

**Batch:** First batch — allowed immediately after Task 2 gate baseline is written, without waiting for human review.

**Constraint: this task is strictly read-only.** It may read files, read model parameters via `simulink_query_params`, and write the `parameter_parity_audit.json` artifact. It must not patch any model parameter, must not call `simulink_patch_and_verify`, and must not modify any production file. If any step would require a model change to proceed, stop and record the blocker in the artifact.

**Design intent:** This audit is a **reusable model gate**. After this recovery it can be re-run via `probe_sps_parameter_parity_audit` after every builder change to detect parity regressions.

**Files:**
- Create (reusable probe): `probes/kundur/probe_sps_parameter_parity_audit.m`
- Create: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/parameter_parity_audit.json`
- Read only: `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m`
- Read only: `scenarios/kundur/simulink_models/build_kundur_sps.m`

- [ ] **Step 1: Compare line model parity first**

Record this known likely mismatch:

```text
compute_kundur_powerflow.m:
  uses PI line model with C_std=0.009e-6 F/km and C_short=0.009e-6 F/km
  adds ysh = 1j * B_tot * Zbase / 2 at both ends of every line

build_kundur_sps.m:
  uses Three-Phase Series RLC Branch with BranchType='RL'
  sets Resistance and Inductance only
  does not set line capacitance on transmission lines
```

Write `parameter_parity_audit.json` with:

```json
{
  "schema_version": 1,
  "line_model": {
    "nr_model": "PI",
    "nr_has_line_charging": true,
    "sps_branch_type": "RL",
    "sps_has_line_charging": false,
    "known_parity_mismatch": true,
    "candidate_root_cause": "possible — requires NR-only variant confirmation before any SPS edit",
    "confirmed_root_cause": false,
    "confirmation_method": "run probe_kundur_nr_parity_variants: if nr_no_line_charging moves Bus7/8/10/9 toward SPS EMF-baseline angles, line charging parity is primary candidate; otherwise continue audit"
  }
}
```

Do not write `"confirmed_root_cause": true` or `"candidate_root_cause": true` (boolean) in this task. The line charging mismatch is a documented parity observation, not a proven explanation of the angle errors.

Verify:

```powershell
Select-String -LiteralPath 'results\harness\kundur\20260424-kundur-sps-workpoint-alignment\attachments\parameter_parity_audit.json' -Pattern 'line_charging|candidate_root_cause'
```

Expected: both patterns are present.

- [ ] **Step 2: Audit load and shunt parity**

Record these rows:

```text
Bus7 NR: P=-967/100 pu, Q=+1.0 pu after Load7 inductive 100 Mvar and Shunt7 capacitive 200 Mvar
Bus7 SPS: Load7 ActivePower=967e6, InductivePower=100e6, Shunt7 CapacitivePower=200e6

Bus9 NR: P=-1767/100 pu, Q=+2.5 pu after Load9 inductive 100 Mvar and Shunt9 capacitive 350 Mvar
Bus9 SPS: Load9 ActivePower=1767e6, InductivePower=100e6, Shunt9 CapacitivePower=350e6

Bus14 NR: P=P_ES3_sys - 248e6/Sbase
Bus14 SPS: TripLoad1 ActivePower='TripLoad1_P * 3' and config default is 248e6/3 W per phase

Bus15 NR: TripLoad2=0 at episode start
Bus15 SPS: TripLoad2_P=0 and CapacitivePower=1 VAR floor
```

Decision:

```text
If these rows match, do not spend time on load P/Q sign before testing line charging.
If any row differs, isolate that row in an NR variant before editing the SPS model.
```

- [ ] **Step 3: Audit source impedance parity**

Record:

```text
compute_kundur_powerflow.m conventional sources:
  R_gen_pu_val = 0.003 * (Sbase / 900e6)
  X_gen_pu_val = 0.30  * (Sbase / 900e6)

build_kundur_sps.m conventional sources:
  GSrc/WSrc NonIdealSource='on'
  SpecifyImpedance='on'
  Resistance and Inductance read back from model params

compute_kundur_powerflow.m VSG sources:
  R_vsg_pu_val = 0.003 * (Sbase / VSG_SN)
  X_vsg_sys = 0.30 * (Sbase / VSG_SN)

build_kundur_sps.m VSG sources:
  VSrc_ES* NonIdealSource='on'
  Resistance and Inductance read back from model params
```

Use MCP:

```text
Step: Read source impedance params.
  Tool: simulink_query_params
  Combine: query GSrc_G1/G2/G3, WSrc_W1/W2, VSrc_ES1..4 for Resistance and Inductance.
  Verify: append Ohm/H values and converted pu values to `parameter_parity_audit.json`.
```

Decision (observation only — recorded in artifact, not acted upon):

```text
If line charging is mismatched, record it. Do not edit any file.
If source impedance conversion differs from NR, record it. Do not edit any file.
All findings are evidence for the human review that follows Task 3A.
```

Task 3A completion condition:

```text
parameter_parity_audit.json is written.
All fields are read-only evidence: no action has been taken on any mismatch.
STOP. Present both static_workpoint_gate.json and parameter_parity_audit.json for human review.
Wait for explicit authorization before proceeding to Task 4.
```

---

### Task 3B: Evidence Boundary Repair Before NR Variant

**Batch:** Amendment 1 evidence-boundary batch. This task is authorized only
after Task 3A review identifies evidence-quality or workspace-contamination
issues. It must complete and stop before Task 4 can be authorized.

**Constraint: this task does not run a diagnostic branch.** It may edit
documentation, fix the reusable static gate probe's evidence-recording bug, and
write one boundary artifact. It must not run `probe_kundur_nr_parity_variants`,
must not patch or save any Simulink model, and must not edit any production
model/reference file.

**Files:**
- Modify: `scenarios/kundur/NOTES.md`
- Modify: `probes/kundur/probe_sps_static_workpoint_gate.m`
- Create: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/task3b_evidence_boundary_review.json`
- Read only: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/static_workpoint_gate.json`
- Read only: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/parameter_parity_audit.json`

- [ ] **Step 1: Record the contamination boundary**

Run:

```powershell
git status --short -- scenarios/kundur/config_simulink.py `
  scenarios/kundur/kundur_ic.json `
  scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m `
  scenarios/kundur/simulink_models/build_kundur_sps.m `
  scenarios/kundur/simulink_models/build_powerlib_kundur.m `
  scenarios/kundur/simulink_models/kundur_vsg_sps.slx
```

Expected: if any path is dirty, Task 4 remains blocked until the dirty state is
recorded in `task3b_evidence_boundary_review.json`. Do not revert these files
unless the human explicitly asks for that operation.

- [ ] **Step 2: Correct `scenarios/kundur/NOTES.md` active state**

Replace stale Branch 7A confirmed language with this active note:

```markdown
- SPS candidate `kundur_vsg_sps` remains blocked at Task 9 NO-GO.
  Branch 7A terminal-angle initialization is invalidated as a complete fix:
  ESS Pe magnitude is multi-pu while the expected per-ESS Pe is about +0.2 pu.
  Task 2/3A review also found evidence-boundary issues before Task 4:
  current static angle evidence uses ESS terminal voltage as a proxy for the
  main bus angle, and production model/reference files are dirty from earlier
  Branch 7A work.
  Smoke Bridge, 20-episode training, `.slx` cutover, and NR-variant Task 4 are
  blocked until Task 3B writes its boundary artifact and receives review.
```

Remove or rewrite any nearby text that says Branch 7A is confirmed, root cause
is fixed, or Smoke Bridge/training is the next action.

Verify:

```powershell
Select-String -LiteralPath 'scenarios\kundur\NOTES.md' `
  -Pattern 'NO-GO|Branch 7A|invalidated|Task 3B|Task 4|blocked'
Select-String -LiteralPath 'scenarios\kundur\NOTES.md' `
  -Pattern 'confirmed|root cause.*fixed|Smoke Bridge.*next'
```

Expected: the first command finds the active blocked state. The second command
must not find an active recommendation that contradicts NO-GO.

- [ ] **Step 3: Fix the static gate probe evidence-recording bug**

Patch `probes/kundur/probe_sps_static_workpoint_gate.m` so `row` is not reused
between unrelated loops. In the VSrc readback loop, initialize a fresh struct:

```matlab
for i = 1:4
    blk = sprintf('%s/VSrc_ES%d', model_name, i);
    row = struct();
    row.block = blk;
    for p = 1:length(vsrc_param_names)
        pn = vsrc_param_names{p};
        try; row.(pn) = get_param(blk, pn); catch; row.(pn) = ''; end
    end
    vsrc_readback{i} = row;
end
```

In the ESS row loop, initialize a fresh row and record the intended VSrc block:

```matlab
for i = 1:4
    bi = ess_bus_idx(i);
    row = struct();
    row.block     = sprintf('%s/VSrc_ES%d', model_name, i);
    row.ess       = ess_labels{i};
    row.main_bus  = bus_labels{bi};
    row.sps_angle_measurement_scope = ...
        'ESS terminal V angle proxy; no direct Bus7/8/10/9 measurement block';
```

Do not re-run the static gate in this task unless a separate human instruction
explicitly authorizes it. The fix is for future evidence quality; it does not
retroactively change `static_workpoint_gate.json`.

Verify:

```powershell
Select-String -LiteralPath 'probes\kundur\probe_sps_static_workpoint_gate.m' `
  -Pattern 'row = struct|sps_angle_measurement_scope|VSrc_ES%d'
```

- [ ] **Step 4: Write the evidence-boundary artifact**

Create `task3b_evidence_boundary_review.json` with this semantic shape:

```json
{
  "schema_version": 1,
  "scenario_id": "kundur",
  "run_id": "20260424-kundur-sps-workpoint-alignment",
  "task": "task3b_evidence_boundary_review",
  "decision": "TASK4_STILL_BLOCKED",
  "triggering_evidence": [
    "static_workpoint_gate uses ESS terminal voltage angle as proxy, not direct Bus7/8/10/9 measurement",
    "static_workpoint_gate ess_rows.block was stale VSrc_ES4 for all rows before Task 3B probe fix",
    "production model/reference files were dirty before NR-variant Task 4"
  ],
  "dirty_production_files": [
    "scenarios/kundur/config_simulink.py",
    "scenarios/kundur/kundur_ic.json",
    "scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m",
    "scenarios/kundur/simulink_models/build_kundur_sps.m",
    "scenarios/kundur/simulink_models/build_powerlib_kundur.m",
    "scenarios/kundur/simulink_models/kundur_vsg_sps.slx"
  ],
  "artifact_limitations": {
    "static_workpoint_gate_main_bus_angle": "proxy_only",
    "direct_bus_angle_matrix_available": false,
    "pe_gate_still_valid": true,
    "parameter_parity_audit_read_only": true
  },
  "edits_authorized_in_task3b": [
    "scenarios/kundur/NOTES.md active-state correction",
    "probes/kundur/probe_sps_static_workpoint_gate.m evidence-recording bug fix"
  ],
  "edits_still_prohibited": [
    "scenarios/kundur/simulink_models/build_kundur_sps.m",
    "scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m",
    "scenarios/kundur/simulink_models/build_powerlib_kundur.m",
    "scenarios/kundur/kundur_ic.json",
    "scenarios/kundur/simulink_models/kundur_vsg_sps.slx",
    "training scripts",
    "docs/paper/experiment-index.md"
  ],
  "task4_preconditions": [
    "human review accepts this Task 3B artifact",
    "human explicitly authorizes exactly one NR variant branch",
    "Task 4 run records that dirty production files are not being edited or saved"
  ],
  "recommended_next_branch_after_review": "line_charging_nr_variant_only"
}
```

Use the observed `git status --short` values from Step 1. Do not claim files are
clean unless the command shows they are clean.

Verify:

```powershell
Get-Content -LiteralPath 'results\harness\kundur\20260424-kundur-sps-workpoint-alignment\attachments\task3b_evidence_boundary_review.json' -Encoding UTF8
Select-String -LiteralPath 'results\harness\kundur\20260424-kundur-sps-workpoint-alignment\attachments\task3b_evidence_boundary_review.json' `
  -Pattern 'TASK4_STILL_BLOCKED|proxy_only|line_charging_nr_variant_only'
```

Task 3B completion condition:

```text
task3b_evidence_boundary_review.json is written.
NOTES.md no longer contains an active Branch 7A confirmed / run Smoke Bridge next conclusion.
probe_sps_static_workpoint_gate.m no longer leaks VSrc_ES4 into every ESS row.
No NR variant has been run.
No production model/reference file has been edited by Task 3B.
STOP. Present the Task 3B artifact for review before Task 4.
```

---

### Task 4: Test NR Variants Before Editing SPS

**Blocked until:** Task 2 and Task 3A have both produced their artifacts, Task 3B has produced `task3b_evidence_boundary_review.json`, and human review has explicitly selected one NR-variant question (e.g., line charging). Do not run Task 4 in the first execution batch or inside Task 3B.

**Files:**
- Create if needed: `probes/kundur/probe_kundur_nr_parity_variants.m`
- Generate: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/nr_variant_line_charging.json`

- [ ] **Step 1: Create an NR-only variant probe for line charging**

Create a probe that reuses the NR network math but toggles line charging without changing production `compute_kundur_powerflow.m`.

Required function signature:

```matlab
function results = probe_kundur_nr_parity_variants(run_dir)
```

Required output:

```json
{
  "schema_version": 1,
  "variants": [
    {
      "label": "nr_with_line_charging",
      "C_std_F_per_km": 9e-9,
      "C_short_F_per_km": 9e-9,
      "main_bus_ang_abs_deg": [10.913127677225445, 2.9712307723444127, 4.5191269028534364, 1.6089023192225262]
    },
    {
      "label": "nr_no_line_charging",
      "C_std_F_per_km": 0.0,
      "C_short_F_per_km": 0.0,
      "main_bus_ang_abs_deg": []
    }
  ],
  "comparison_to_sps_emf_baseline": {
    "sps_emf_baseline_main_bus_ang_deg": [15.180089409742246, 5.9013365191946505, 9.2872197552380715, 5.4134858434722366],
    "which_nr_variant_is_closer": ""
  }
}
```

Verify:

```text
RESULT: nr_no_line_charging_bus7=... closer_to_sps_emf_baseline=...
```

- [ ] **Step 2: Decide whether line charging explains the 3-5 deg angle errors**

Decision:

```text
If `nr_no_line_charging` moves Bus7/8/10/9 toward the SPS EMF-baseline angles,
  line charging parity is the primary root-cause candidate — record in artifact, stop, wait for review.
If it does not,
  record which variant is closer; stop, wait for review before trying source impedance or other branches.
```

Only one NR-variant branch is tested per Task 4 run. Do not simultaneously test line charging and source impedance. Do not edit `build_kundur_sps.m` in this task.

---

### Task 5: Implement Only The Confirmed Static Network Fix

**Blocked until:** A root cause is confirmed by Task 2 plus a selected follow-up diagnostic. Do not run Task 5 in the first execution batch.

**Files:**
- Modify only after confirmation: `scenarios/kundur/simulink_models/build_kundur_sps.m`
- Modify only after confirmation: `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m`
- Modify only after confirmation: `scenarios/kundur/simulink_models/build_powerlib_kundur.m`
- Modify only after confirmation: `scenarios/kundur/kundur_ic.json`
- Modify only after confirmation: `scenarios/kundur/simulink_models/kundur_vsg_sps.slx`

Choose exactly one branch.

#### Branch 5A: Line Charging Parity Is Confirmed

Use this branch only if Task 4 shows NR-without-line-charging aligns with the old SPS EMF-baseline angle errors.

- [ ] **Step 1: Decide the direction of truth**

Decision rule:

```text
If Yang/Kundur reference and existing NR code require PI line charging, fix SPS to include line charging.
If the active reproduction path intentionally omits line charging in SPS, change the NR reference to omit it and regenerate `kundur_ic.json`.
```

Default engineering choice:

```text
Prefer fixing SPS to match the NR PI line model, because `compute_kundur_powerflow.m` currently models C_std/C_short explicitly and uses those values to produce the reference workpoint.
```

- [ ] **Step 2: Implement line charging in the builder, not by manual `.slx` patch**

Preferred options in order:

```text
Option 1: Use a Three-Phase Series RLC Branch mode that supports R, L, and C line parameters directly.
Option 2: Add explicit half-line shunt capacitance at each line end so the SPS model matches the PI Ybus.
```

Verify with MCP:

```text
Step: Rebuild candidate from builder.
  Tool: simulink_run_script_async
  Combine: run `build_kundur_sps`; poll until complete.
  Verify: source params, line/shunt params, and compile diagnostics are clean.
```

Do not save exploratory manual patches.

#### Branch 5B: Source Impedance Parity Is Confirmed

Use this branch only if source impedance conversion differs from NR and line charging does not explain the angle errors.

- [ ] **Step 1: Patch the builder conversion**

Required approach:

```text
Change source impedance conversion in `build_kundur_sps.m`.
Keep EMF and terminal angle fields both available in `kundur_ic.json`.
Do not delete metadata fields.
```

Verify:

```text
Read GSrc/WSrc/VSrc Resistance and Inductance with `simulink_query_params`.
Convert back to pu and compare with NR fields in `parameter_parity_audit.json`.
```

#### Branch 5C: Measurement Point Mapping Is Confirmed

Use this branch only if parameter parity is correct but measured bus angles or Pe are taken from the wrong node.

- [ ] **Step 1: Fix probe and bridge measurement mapping first**

Required approach:

```text
Correct `probes/kundur/*` and `slx_helpers/vsg_bridge/slx_extract_state.m` only if direct evidence shows the wrong node or sign convention is being measured.
```

Verify:

```text
manual VxI Pe equals slx_extract_state Pe for all four ESS
main-bus voltage probes measure Bus7/8/10/9, not ESS internal or source nodes
```

---

### Task 6: Rebuild And Re-run Model Gates

**Blocked until:** Task 5 has implemented a confirmed model-side fix. Do not run Task 6 in the first execution batch.

**Files:**
- Update: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/model_patch_verify.json`
- Update: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/model_diagnose.json`
- Update: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/model_report.json`
- Update: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/summary.md`

- [ ] **Step 1: Re-run reusable static workpoint gate after the confirmed fix**

Use the **same probe** created in Task 2 — do not write new validation logic.

```text
Step: Re-run static workpoint gate.
  Tool: simulink_run_script_async
  Combine: call probe_sps_static_workpoint_gate('kundur_vsg_sps', run_dir)
  Verify: all static hard gates pass for the chosen source-angle semantics and all four ESS rows;
          provenance.matlab_model_dirty_after = false;
          artifact schema_version matches Task 2 baseline (enables direct comparison).
```

Expected gate results:

```text
gate_results.all_angle_gates_pass = true
gate_results.all_pe_gates_pass = true
gate_results.all_vi_gates_pass = true
verdict_summary.any_config_passes_all_static_gates = true
```

- [ ] **Step 2: Run zero-action validation only after static gates pass**

Run:

```powershell
$env:KUNDUR_MODEL_PROFILE='C:\Users\27443\Desktop\Multi-Agent  VSGs\scenarios\kundur\model_profiles\kundur_sps_candidate.json'
python probes/kundur/validate_phase3_zero_action.py
```

Expected:

```text
VERDICT: ALL PASS
```

If any C0/C1/C3/C4/C5 hard criterion fails, do not proceed to Smoke Bridge. Return to static or bridge diagnosis depending on the failure.

- [ ] **Step 3: Produce model_report only after model-side evidence is complete**

Use MCP:

```text
Step: Aggregate model report.
  Tool: model_report
  Combine: include `task9_no_go_decision.json`, `static_workpoint_matrix.json`, `parameter_parity_audit.json`, `nr_variant_line_charging.json`, and zero-action output.
  Verify: report does not recommend `Run train_smoke` unless static and zero-action hard gates pass.
```

---

### Task 7: Resume Smoke Bridge Only If Gates Pass

**Blocked until:** static gates, zero-action gates, and `model_report` all pass after a confirmed fix. Do not run Task 7 in the first execution batch.

**Files:**
- Update after pass: `scenarios/kundur/NOTES.md`
- Update after pass: `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/summary.md`
- Update after training evidence exists: `docs/paper/experiment-index.md`

- [ ] **Step 1: Confirm launch status**

Use:

```text
Step: Get registered launch command.
  Tool: get_training_launch_status
  Combine: scenario_id=`kundur`
  Verify: returned command points to `scenarios/kundur/train_simulink.py` and profile is explicitly SPS candidate if needed.
```

- [ ] **Step 2: Run Smoke Bridge**

Use:

```text
Step: Smoke Bridge.
  Tool: train_smoke_start
  Combine: train_smoke_poll until pass/fail.
  Verify: smoke_passed=true.
```

If Smoke Bridge fails, stop and route back to Model Harness/diagnosis. Do not run 20 episodes.

- [ ] **Step 3: Run 20-episode training only after Smoke Bridge passes**

Run exactly once:

```powershell
$env:KUNDUR_MODEL_PROFILE='C:\Users\27443\Desktop\Multi-Agent  VSGs\scenarios\kundur\model_profiles\kundur_sps_candidate.json'
python scenarios/kundur/train_simulink.py --mode simulink --episodes 20
```

Observe:

```text
Tool: training_status
Verify: episode 1 starts cleanly; no systemic omega_saturated, Pe=0, Pe=-7 pu, or Pe=+4 pu failure mode.
```

- [ ] **Step 4: Decide cutover only after clean training evidence**

Do not cut over if any of these remain:

```text
SPS Bus7/8/10/9 angle differs from NR by more than 1 deg
any ESS Pe misses expected Pe by more than 0.05 pu in static gate
manual VxI comparison fails
zero-action validation fails
Smoke Bridge fails
20-episode training shows systemic physical anomalies
```

---

## Execution Batch Map

Each batch has a mandatory stop. Do not cross a batch boundary without new plan authorization.

```text
Batch 1 — Evidence collection (first execution batch, this plan)
  Task 0: Freeze Task 9 as NO-GO; write task9_no_go_decision.json
  Task 1: Fix sign-only source-angle gate; re-run probe_sps_source_angle_hypotheses
  Task 2: Run reusable static workpoint gate baseline; write static_workpoint_gate.json
  Task 3A: Run read-only parameter parity audit; write parameter_parity_audit.json
  STOP — present both artifacts for human review

Batch 2 — Evidence boundary repair (Amendment 1, authorized by review)
  Task 3B: Repair evidence boundary; write task3b_evidence_boundary_review.json
  STOP — present Task 3B artifact; do not run NR variants

Batch 3 — Targeted NR variant (COMPLETED — line-charging hypothesis rejected)
  Task 4: NR line-charging variant ran → nr_variant_line_charging.json written
  Result: NR without line-charging moved Bus7/8/10/9 angles further from SPS EMF-baseline;
          delta_mae = -0.036 deg (wrong direction). Hypothesis rejected.
  Branch 5A / line-charging parity: EXCLUDED. No SPS line-charging edits authorized.
  STOP — line-charging result presented; Amendment 2 records next authorized branch.

  ── Next Authorized Branch / 当前授权分支 (Amendment 2) ─────────────────────────
  Branch: Measurement Point Mapping (read-only / probe-only)
  Goal: confirm whether the SPS angle measurement and NR bus voltage angle
        correspond to the same physical node.
  NR comparison targets: Bus 7 / Bus 8 / Bus 10 / Bus 9 terminal bus voltage angle.
  SPS candidates to distinguish:
    - main-grid bus node (measurement block directly on Bus7/8/10/9)
    - ESS local bus (transformer secondary or ESS terminal node)
    - converter-side node (VSrc output terminal)
    - grid-side node (line-side of ESS transformer)
    - internal EMF / control angle (VSrc PhaseAngle command value)
  Allowed actions: read files, read model parameters via simulink_query_params,
                   read model topology via simulink_get_block_tree / simulink_explore_block,
                   write measurement_point_mapping.json and a short summary text.
  Prohibited: any edit to SPS/SLX files, slx_helpers/vsg_bridge/slx_extract_state.m,
              build_kundur_sps.m, build_powerlib_kundur.m, compute_kundur_powerflow.m,
              kundur_ic.json, probes that set_param or save model state, any training script.
  Must STOP after measurement_point_mapping.json + summary are written.
  Do NOT auto-enter source impedance, angle reference, transformer taps, load sign,
  or generator model branches without explicit human authorization.
  ─────────────────────────────────────────────────────────────────────────────────

Batch 4 — Confirmed model fix (one fix only, authorized by root-cause confirmation)
  Task 5: Implement only the confirmed branch (5A, 5B, or 5C); no opportunistic extras
  STOP — present what changed; do not run any gate yet

Batch 5 — Post-fix verification
  Re-run probe_sps_static_workpoint_gate (Task 2 probe reused)
  Re-run probe_sps_parameter_parity_audit if relevant
  Run zero-action validation only after static gates pass
  STOP — present gate results before any training action

Batch 6 — Training path (all model gates must have passed in Batch 5)
  Task 7: Run Smoke Bridge
  Run 20-episode training only if Smoke Bridge passes
  Decide cutover only after clean training evidence
```

---

## Commit Guidance

Commit the recovery in small, evidence-based commits.

First documentation/evidence commit:

```powershell
git add scenarios/kundur/NOTES.md `
  results/harness/kundur/20260424-kundur-sps-workpoint-alignment/summary.md `
  results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/task9_no_go_decision.json `
  docs/superpowers/plans/2026-04-24-kundur-sps-task9-no-go-recovery.md
git commit -m "docs: record kundur sps task9 no-go"
```

Probe/gate commit:

```powershell
git add probes/kundur/probe_sps_source_angle_hypotheses.m `
  probes/kundur/probe_sps_static_workpoint_gate.m `
  probes/kundur/probe_sps_parameter_parity_audit.m `
  probes/kundur/probe_kundur_nr_parity_variants.m `
  results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/static_workpoint_gate.json `
  results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/parameter_parity_audit.json `
  results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/nr_variant_line_charging.json
git commit -m "fix: harden kundur sps workpoint gates"
```

Model fix commit only after root cause is confirmed:

```powershell
git add scenarios/kundur/simulink_models/build_kundur_sps.m `
  scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m `
  scenarios/kundur/simulink_models/build_powerlib_kundur.m `
  scenarios/kundur/kundur_ic.json `
  scenarios/kundur/simulink_models/kundur_vsg_sps.slx `
  results/harness/kundur/20260424-kundur-sps-workpoint-alignment
git commit -m "fix: align kundur sps static network with nr workpoint"
```

Write a devlog if the recovery confirms line charging, source impedance, or measurement mapping as the durable root cause.

---

## Self-Review Checklist

- Task 9 is explicitly frozen as NO-GO before any new model work.
- The old `terminal_fix_promising=true` sign-only conclusion is invalidated.
- The plan blocks Smoke Bridge, training, and cutover until model hard gates pass.
- The next probe measures all four ESS/main-bus pairs, not ESS1 only.
- Direct terminal Branch 7A Bus7/8/10/9 angles are required before any new source-angle conclusion.
- Parameter parity checks start with the known PI-line-vs-RL-line mismatch.
- NR variants are tested before editing the SPS builder.
- No exploratory model patch is saved.
- No RL, reward, VSG M/D, warmup, or omega-limit tuning is used to mask static workpoint errors.
- Problem is framed as NR/SPS static workpoint misalignment, not as a source-angle-only issue.
- Static workpoint gate probe (`probe_sps_static_workpoint_gate.m`) is designed for reuse across rebuild, post-fix, and pre-Smoke-Bridge runs.
- Parameter parity audit (`probe_sps_parameter_parity_audit.m`) is read-only and runs in the first batch without waiting for human review.
- JSON schema is unified (schema_version=2) so Task 2 baseline and Task 6 post-fix artifacts can be directly compared.
- Plan Horizon and Replanning Policy chapter is present and prohibits evidence-triggered autonomous scope expansion.
- Mandatory STOP triggers are enumerated; agents must halt and report on any trigger.
- Amendment 1 inserts Task 3B before Task 4 and records the evidence-boundary repair requirement.
- Six-batch execution map is present; no batch crosses into the next without human authorization.
- Task 4 tests only one selected NR-variant branch per run; multiple branches are not tested simultaneously.
- Task 6 reuses the Task 2 probe rather than writing new validation logic.
