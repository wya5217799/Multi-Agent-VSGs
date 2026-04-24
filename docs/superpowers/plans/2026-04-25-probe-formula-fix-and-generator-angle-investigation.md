# Probe Formula Fix + Generator Angle Investigation

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.
> **REQUIRED PRE-READ:** `docs/superpowers/plans/2026-04-24-kundur-sps-investigation-constraints.md` — 硬约束文件，执行前必读，优先级高于本计划所有内容。

**Goal:** Fix the -15° systematic bias in the three ESS angle probe files, then re-run the static workpoint gate probe to collect corrected readings for all three generator configs (including terminal_reference), quantifying the 4.25° residual.

**Architecture:** Edit-only pass on probe files (not production), then one `simulink_run_script` call to run the existing gate probe, then write artifact. No model edits, no `simulink_save_model`.

**Tech stack:** MATLAB SPS Phasor / `simulink_run_script` MCP tool / Edit tool.

---

## Inherited constraints (from 2026-04-24-kundur-sps-investigation-constraints.md)

```
Prohibited edits: build_kundur_sps.m  build_powerlib_kundur.m
                  compute_kundur_powerflow.m  kundur_ic.json
                  kundur_vsg_sps.slx  config_simulink.py
                  slx_extract_state.m  experiment-index.md
                  any training scripts
Prohibited actions: simulink_save_model, Smoke Bridge, training, cutover
Model-dirty rule: close without saving if dirty; reload from disk
STOP if: Pe > 1.0 pu on any ESS, or model left dirty, or approaching non-authorized scope
```

## Root cause (from source_angle_chain_diagnosis.json)

```
SPS Phasor mode outputs complex phasors (isreal=0).
Correct extraction:  angle(V_row(1))               → 15.164° for Bus12 (emf_reference)
Buggy extraction:    angle(V_row(1) + 1j*V_row(2)) → 0.164°  (= correct - 15° exactly)
Analytical proof: angle(Va + j*Vb) = angle(Va) + atan2(-0.5, 1.866) = angle(Va) - 15°
```

---

## Task A — Fix probe formula in three files

**Files to modify (all in `probes/kundur/`, NOT in prohibited list):**
- Modify: `probes/kundur/probe_sps_static_workpoint_gate.m:226`
- Modify: `probes/kundur/probe_sps_workpoint_alignment.m:240`
- Modify: `probes/kundur/probe_sps_source_angle_hypotheses.m:163-164`

### A1 — Fix probe_sps_static_workpoint_gate.m

- [ ] Read file around line 226 to confirm current text, then apply Edit:

```
OLD (line 226):
    V_cmplx = V_row(1) + 1j*V_row(2);

NEW:
    V_cmplx = V_row(1);   % complex phasor: angle(Va) is phase-A angle directly
```

Line 227 (`sps_ang_raw = angle(V_cmplx) * 180/pi;`) is unchanged — it already calls `angle()` on V_cmplx.

### A2 — Fix probe_sps_workpoint_alignment.m

- [ ] Read file around line 240 to confirm current text, then apply Edit:

```
OLD (line 240):
    V_ang_k = angle(V_row(1) + 1j*V_row(2)) * 180/pi;

NEW:
    V_ang_k = angle(V_row(1)) * 180/pi;   % complex phasor: direct phase-A angle
```

### A3 — Fix probe_sps_source_angle_hypotheses.m

- [ ] Read file around lines 163–164 to confirm current text, then apply Edit for both V and I:

```
OLD (lines 163–164):
    V_ang   = angle(V_row(1) + 1j*V_row(2)) * 180/pi;
    I_ang   = angle(I_row(1) + 1j*I_row(2)) * 180/pi;

NEW:
    V_ang   = angle(V_row(1)) * 180/pi;   % complex phasor
    I_ang   = angle(I_row(1)) * 180/pi;   % complex phasor
```

### A4 — Quick sanity-check via simulink_run_script

- [ ] Run in `simulink_run_script` (no model needed, pure math):

```matlab
% Verify the fix is arithmetically correct for complex phasors
phi_a = 15.1643 * pi/180;
Va = exp(1j*phi_a);   % unit complex phasor, phase = 15.1643°

old_result = angle(Va + 1j * Va*exp(-1j*2*pi/3)) * 180/pi;
new_result = angle(Va) * 180/pi;

fprintf('RESULT: old_formula=%.4f (expected ~0.164)\n', old_result);
fprintf('RESULT: new_formula=%.4f (expected 15.1643)\n', new_result);
fprintf('RESULT: fix_correct=%d\n', abs(new_result - 15.1643) < 0.001);
```

Expected `important_lines`:
```
RESULT: old_formula=0.1643 (expected ~0.164)
RESULT: new_formula=15.1643 (expected 15.1643)
RESULT: fix_correct=1
```

---

## Task B — Re-run static workpoint gate with corrected formula

**Purpose:** Collect corrected Bus12/16/14/15 angles for all three configs (emf_reference, terminal_reference, persisted_current). The terminal_reference config answers the generator-angle residual question: if Bus12 → 10.917° with terminal_reference, the 4.25° residual is fully explained by generator source angle choice.

**No new probe script needed.** `probe_sps_static_workpoint_gate.m` already runs all three configs.

### B1 — Set up run directory reference file

The probe reads `run_dir/attachments/nr_reference.json`. Confirm it exists:

- [ ] Run in `simulink_run_script`:

```matlab
run_dir = 'C:\Users\27443\Desktop\Multi-Agent  VSGs\results\harness\kundur\20260424-kundur-sps-workpoint-alignment';
ref_path = fullfile(run_dir, 'attachments', 'nr_reference.json');
fprintf('RESULT: nr_reference_exists=%d\n', isfile(ref_path));
```

If `nr_reference_exists=0`: the probe will fail. In that case, skip to B1-fallback (below). If `=1`: proceed to B2.

**B1-fallback** (only if nr_reference.json is absent):

- [ ] Run the probe with an explicit `opts.nr_bus_angles` override by using a standalone script in `simulink_run_script` (see B2-standalone below).

### B2 — Run the corrected gate probe

- [ ] Run in `simulink_run_script` (timeout 300 s):

```matlab
addpath('C:\Users\27443\Desktop\Multi-Agent  VSGs\probes\kundur');
addpath('C:\Users\27443\Desktop\Multi-Agent  VSGs\scenarios\kundur\matlab_scripts');
addpath('C:\Users\27443\Desktop\Multi-Agent  VSGs\slx_helpers');

model_name = 'kundur_vsg_sps';
model_path = 'C:\Users\27443\Desktop\Multi-Agent  VSGs\scenarios\kundur\simulink_models\kundur_vsg_sps';
run_dir    = 'C:\Users\27443\Desktop\Multi-Agent  VSGs\results\harness\kundur\20260424-kundur-sps-workpoint-alignment';

load_system(model_path);

opts.output_filename = 'static_workpoint_gate_formula_fixed.json';
results = probe_sps_static_workpoint_gate(model_name, run_dir, opts);

% Print key angles for each config
for c = 1:length(results.configs)
    cfg = results.configs(c);
    fprintf('RESULT: config=%s\n', cfg.label);
    for r = 1:length(cfg.ess_rows)
        row = cfg.ess_rows(r);
        fprintf('RESULT:   ESS%d bus_angle=%.4f  NR=%.4f  error=%.4f  Pe=%.4f\n', ...
            r, row.sps_main_bus_angle_deg, row.nr_ess_bus_angle_deg, ...
            row.main_bus_angle_error_deg, row.measured_pe_sys_pu);
    end
end

% Check dirty + close
dirty = get_param(model_name, 'Dirty');
fprintf('RESULT: model_dirty=%s\n', dirty);
close_system(model_name, 0);
fprintf('RESULT: model_closed_no_save=true\n');
```

**B2-standalone** (fallback if the function call fails or nr_reference.json is absent):

- [ ] Run standalone minimal probe in `simulink_run_script` (timeout 300 s):

```matlab
model_path = 'C:\Users\27443\Desktop\Multi-Agent  VSGs\scenarios\kundur\simulink_models\kundur_vsg_sps';
model_name = 'kundur_vsg_sps';
addpath('C:\Users\27443\Desktop\Multi-Agent  VSGs\scenarios\kundur\matlab_scripts');
addpath('C:\Users\27443\Desktop\Multi-Agent  VSGs\slx_helpers');

load_system(model_path);

% NR ESS bus angles (from ess_terminal_angle_comparison.json)
nr_bus = [10.917, 2.975, 4.481, 1.612];  % Bus12, Bus16, Bus14, Bus15

% Workspace defaults (from kundur_ic.json)
ic_delta = [12.620902, 4.684639, 6.227043, 3.323270];
for i = 1:4
    assignin('base', sprintf('phAng_ES%d', i), ic_delta(i));
    assignin('base', sprintf('Pe_ES%d',     i), 0.1);
    assignin('base', sprintf('M0_val_ES%d', i), 12.0);
    assignin('base', sprintf('D0_val_ES%d', i), 3.0);
end
assignin('base', 'TripLoad1_P', 248e6/3);
assignin('base', 'TripLoad2_P', 0.0);

% Generator angle configs to test
configs = struct();
configs(1).label  = 'emf_reference';
configs(1).G1 = '32.385875'; configs(1).G2 = '29.053883'; configs(1).G3 = '19.374872';
configs(1).W1 = '17.069560'; configs(1).W2 =  '4.883907';

configs(2).label  = 'terminal_reference';
configs(2).G1 = '20.0';      configs(2).G2 = '15.923822'; configs(2).G3 = '6.213836';
configs(2).W1 =  '3.323605'; configs(2).W2 =  '2.988130';

for c = 1:2
    cfg = configs(c);
    set_param([model_name '/GSrc_G1'], 'PhaseAngle', cfg.G1);
    set_param([model_name '/GSrc_G2'], 'PhaseAngle', cfg.G2);
    set_param([model_name '/GSrc_G3'], 'PhaseAngle', cfg.G3);
    set_param([model_name '/WSrc_W1'], 'PhaseAngle', cfg.W1);
    set_param([model_name '/WSrc_W2'], 'PhaseAngle', cfg.W2);

    fprintf('RESULT: --- config=%s ---\n', cfg.label);
    for i = 1:4
        simOut = sim(model_name, 'StopTime', '0.05');
        Vabc_ts = simOut.get(sprintf('Vabc_ES%d', i));
        V_row = Vabc_ts.Data(end,:);
        bus_ang = angle(V_row(1)) * 180/pi;   % CORRECTED formula
        err = bus_ang - nr_bus(i);
        fprintf('RESULT:   ESS%d  bus_angle=%.4f  NR=%.4f  error=%.4f\n', i, bus_ang, nr_bus(i), err);
    end
end

dirty = get_param(model_name, 'Dirty');
fprintf('RESULT: model_dirty=%s\n', dirty);
close_system(model_name, 0);
fprintf('RESULT: model_closed_no_save=true\n');
```

**Expected outcome:**

| Config | Expected Bus12 (corrected formula) | Passes 1° gate? |
|---|---|---|
| emf_reference | ≈ 15.164° (error ≈ +4.25°) | No |
| terminal_reference | ≈ 10.917° ± ? | TBD — this is what we're measuring |

**STOP B1:** If terminal_reference Bus12 error < 1° for all 4 ESS → 4.25° residual is entirely explained by generator angle config. Verdict = `GENERATOR_ANGLE_CONFIG_MISMATCH`. Both fixes needed for gate pass.

**STOP B2:** If terminal_reference error > 1° → additional residual exists beyond generator angle. Record both values and report.

---

## Task C — Write artifact and update state files

### C1 — Write verification artifact

- [ ] Write `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/probe_formula_fix_verification.json`:

```json
{
  "schema_version": 1,
  "scenario_id": "kundur",
  "purpose": "Verify probe formula fix (-15 deg bias) and collect corrected Bus angle readings for all configs",
  "fix_applied": {
    "files_changed": [
      "probes/kundur/probe_sps_static_workpoint_gate.m:226",
      "probes/kundur/probe_sps_workpoint_alignment.m:240",
      "probes/kundur/probe_sps_source_angle_hypotheses.m:163-164"
    ],
    "old_formula": "angle(V_row(1) + 1j*V_row(2)) * 180/pi",
    "new_formula": "angle(V_row(1)) * 180/pi",
    "bias_removed_deg": -15.0
  },
  "sanity_check": {
    "phi_a_test_deg": 15.1643,
    "old_formula_result_deg": "<fill from A4>",
    "new_formula_result_deg": "<fill from A4>",
    "fix_correct": "<fill from A4>"
  },
  "corrected_bus_angles": {
    "emf_reference": {
      "Bus12_deg": "<fill>", "Bus16_deg": "<fill>", "Bus14_deg": "<fill>", "Bus15_deg": "<fill>",
      "mean_error_deg": "<fill>", "max_error_deg": "<fill>", "gate_pass": false
    },
    "terminal_reference": {
      "Bus12_deg": "<fill>", "Bus16_deg": "<fill>", "Bus14_deg": "<fill>", "Bus15_deg": "<fill>",
      "mean_error_deg": "<fill>", "max_error_deg": "<fill>", "gate_pass": "<fill>"
    }
  },
  "generator_angle_verdict": "<GENERATOR_ANGLE_CONFIG_MISMATCH | RESIDUAL_UNRESOLVED>",
  "generator_angle_verdict_detail": "<fill from B results>",
  "provenance": {
    "no_model_saved": true,
    "run_timestamp": "2026-04-25",
    "agent": "claude-sonnet-4-6"
  }
}
```

Populate all `<fill>` fields from the actual Task B `RESULT:` output lines before writing.

### C2 — Update summary.md current-state section

- [ ] Overwrite the current-state section of `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/summary.md` to reflect:
  - New verdict based on Task B outcome (STOP B1 or B2)
  - Append Batch 6 evidence entry

### C3 — Update NOTES.md "现在在修"

- [ ] Update `scenarios/kundur/NOTES.md` "现在在修" section to reflect corrected gate state and next authorized step.

---

## STOP conditions (inherited + batch-specific)

```
STOP immediately if:
- Pe > 1.0 pu on any ESS during B2 sim
- Model left dirty after probe (close_system(..., 0) then reload from disk)
- About to edit any prohibited production file
- About to run Smoke Bridge, training, or cutover
- Task B result is surprising / contradicts working hypothesis → report, do not extend plan
```

**After STOP:** update summary.md → update NOTES.md → report in STOP format.
