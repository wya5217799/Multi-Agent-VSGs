# Pe Magnitude Diagnosis — SPS Kundur

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.
> **REQUIRED PRE-READ:** `docs/superpowers/plans/2026-04-24-kundur-sps-investigation-constraints.md` — 硬约束文件，执行前必读，优先级高于本计划所有内容。

**Goal:** Identify why terminal_reference Pe reads 2.9–4.1 pu (expected 0.2 pu) — narrow to one of six candidate root causes using only read-only probe runs.

**Architecture:** Pure diagnosis pass. Load model, read workspace/signals, compute expected values analytically, write artifact. No model edits. No simulink_save_model.

**Tech stack:** `simulink_run_script` MCP tool / `simulink_model_status` / `simulink_close_model` / Edit (probe files only, not production).

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
STOP if: model left dirty, approaching non-authorized scope
Additional (this batch): do NOT adjust Sbase, vi_scale, or any gate threshold
                         to "make Pe pass" — diagnosis only
```

---

## Current facts

```
Expected Pe per ESS:   0.2 pu  (system base 100 MVA = 20 MW)
                       Source: kundur_ic.json vsg_p0_vsg_base_pu = 0.1 pu_vsg × (200/100) = 0.2 pu_sys
Measured Pe (terminal_reference): 2.9–4.1 pu → 20x too large
Probe formula (gate file, line 231-232):
    raw_W   = real(sum(V_row .* conj(I_row)));   % V_row, I_row = last row of Vabc/Iabc
    Pe_meas = vi_scale * raw_W / Sbase;          % vi_scale=0.5, Sbase=100e6
V phasor known:   |Va| ≈ 185.6 kV  (from source_angle_chain_diagnosis.json)
I phasor unknown: never directly read — first diagnostic gap
Model: kundur_vsg_sps (SPS/Phasor, pe_measurement='vi')
VSrc impedance: R=0.7935 Ω, L=0.25258 H  (= Xd=0.15 pu sys-base at 50 Hz)
```

Six candidate root causes (mutually exclusive):
```
RC-A  Wrong measurement point  — Meas_ES{i} placed upstream of bus (measures source internal current)
RC-B  V×I phasor interpretation error — SPS outputs RMS phasors but vi_scale=0.5 assumes peak
       [Note: this would give Pe = 0.5× actual, NOT 20×, so unlikely to be primary]
RC-C  Sbase/unit mismatch — Sbase hardcoded to 100e6 but model internal scale differs
RC-D  Large circulating current — phAng_ES{i} vs network bus angle mismatch drives big I through small Z
RC-E  Double-scale factor — some block applies an extra gain before the ToWorkspace signal
RC-F  True model power is genuinely large (model state is physically wrong, not a measurement artefact)
```

---

## Task A — Read raw Vabc/Iabc magnitudes + compute expected current

**Purpose:** Determine |Ia| at the measurement point. If |Ia| >> expected (50 A RMS), narrows to RC-A, RC-D, or RC-F. If |Ia| is correct, narrows to RC-B or RC-C.

Expected |Ia| at 20 MW (0.2 pu, unity PF): I_rms = 20e6 / (3 × 132.8e3) ≈ 50 A → peak ≈ 71 A.

- [ ] Run in `simulink_run_script` (timeout 60 s):

```matlab
model_path = 'C:\Users\27443\Desktop\Multi-Agent  VSGs\scenarios\kundur\simulink_models\kundur_vsg_sps';
model_name = 'kundur_vsg_sps';
addpath('C:\Users\27443\Desktop\Multi-Agent  VSGs\scenarios\kundur\matlab_scripts');
addpath('C:\Users\27443\Desktop\Multi-Agent  VSGs\slx_helpers');

load_system(model_path);

% Set workspace for terminal_reference (same as Batch 6)
ic_delta = [12.620902, 4.684639, 6.227043, 3.323270];
for i = 1:4
    assignin('base', sprintf('phAng_ES%d', i), ic_delta(i));
    assignin('base', sprintf('Pe_ES%d',     i), 0.1);
    assignin('base', sprintf('M0_val_ES%d', i), 12.0);
    assignin('base', sprintf('D0_val_ES%d', i), 3.0);
end
assignin('base', 'TripLoad1_P', 248e6/3);
assignin('base', 'TripLoad2_P', 0.0);

% terminal_reference generator angles
set_param([model_name '/GSrc_G1'], 'PhaseAngle', '20.0');
set_param([model_name '/GSrc_G2'], 'PhaseAngle', '15.923822');
set_param([model_name '/GSrc_G3'], 'PhaseAngle', '6.213836');
set_param([model_name '/WSrc_W1'], 'PhaseAngle', '3.323605');
set_param([model_name '/WSrc_W2'], 'PhaseAngle', '2.988130');

simOut = sim(model_name, 'StopTime', '0.05');

Sbase   = 100e6;
vi_scale = 0.5;

for i = 1:4
    Vabc_ts = simOut.get(sprintf('Vabc_ES%d', i));
    Iabc_ts = simOut.get(sprintf('Iabc_ES%d', i));
    V_row = Vabc_ts.Data(end, :);
    I_row = Iabc_ts.Data(end, :);

    Va_mag = abs(V_row(1));
    Ia_mag = abs(I_row(1));
    raw_W  = real(sum(V_row .* conj(I_row)));
    Pe_meas = vi_scale * raw_W / Sbase;

    % Expected values at 20 MW unity-PF
    Vbase_LN_rms = 230e3 / sqrt(3);       % 132.8 kV RMS
    Ia_expected_rms = 20e6 / (3 * Vbase_LN_rms);   % ~50 A
    Ia_expected_peak = Ia_expected_rms * sqrt(2);   % ~71 A

    fprintf('RESULT: ESS%d Va_mag_kV=%.3f Ia_mag_A=%.3f Pe_pu=%.4f Ia_expected_peak_A=%.1f ratio_I=%.2f\n', ...
        i, Va_mag/1e3, Ia_mag, Pe_meas, Ia_expected_peak, Ia_mag / Ia_expected_peak);
end

dirty = get_param(model_name, 'Dirty');
fprintf('RESULT: model_dirty=%s\n', dirty);
close_system(model_name, 0);
fprintf('RESULT: model_closed=true\n');
```

**Expected RESULT lines:** `ratio_I` close to 1.0 → RC-B/RC-C likely. `ratio_I >> 1` (e.g. > 5) → RC-A/RC-D/RC-F likely.

---

## Task B — Check if P_out or PeGain signals are available in simOut

**Purpose:** If `P_out_ES{i}` or `PeFb_ES{i}` is logged, read it as an independent Pe cross-check without V×I formula.

- [ ] Run in `simulink_run_script` (re-use simOut from Task A, or reload — if Task A already closed model, run this immediately after A's sim before close_system):

```matlab
% Append to Task A script, before close_system:
for i = 1:4
    try
        pout_ts = simOut.get(sprintf('P_out_ES%d', i));
        vsg_sn = 200e6;
        Pe_pout = pout_ts.Data(end) * (vsg_sn / Sbase);
        fprintf('RESULT: ESS%d Pe_pout_pu=%.4f\n', i, Pe_pout);
    catch
        fprintf('RESULT: ESS%d P_out_not_logged\n', i);
    end
    try
        pefb_ts = simOut.get(sprintf('PeFb_ES%d', i));
        vsg_sn = 200e6;
        Pe_fb = pefb_ts.Data(end) * (vsg_sn / Sbase);
        fprintf('RESULT: ESS%d Pe_feedback_pu=%.4f\n', i, Pe_fb);
    catch
        fprintf('RESULT: ESS%d PeFb_not_logged\n', i);
    end
end
```

**Combine Tasks A and B** into one `simulink_run_script` call (signal reads must happen before `close_system`).

---

## Task C — Analytical Pe bound using known V and impedance

**Purpose:** Compute the maximum possible Pe from the known source angle vs bus angle difference, using circuit analysis. If the analytical Pe ≈ measured Pe → RC-F (model physics is genuinely wrong). If analytical Pe << measured Pe → RC-A/RC-E (measurement point or gain error).

- [ ] Run in `simulink_run_script` (pure math, no model needed):

```matlab
% Analytical Pe bound for terminal_reference ESS1
% Source: phAng_ES1=12.621 deg, Bus angle≈9.815 deg (from Batch 6)
% Impedance: R=0.7935 Ohm, X=2*pi*50*0.25258=79.3 Ohm at 50 Hz
% Vbase_LN_peak = (230e3/sqrt(3))*sqrt(2) = 187.8 kV

Va_mag_peak = 185.6e3;   % observed from source_angle_chain_diagnosis
phi_src = 12.621 * pi/180;
phi_bus = 9.815 * pi/180;

E_src = Va_mag_peak * exp(1j * phi_src);
V_bus = Va_mag_peak * exp(1j * phi_bus);   % assume |V_bus| ≈ |E_src|

R = 0.7935; X = 2*pi*50*0.25258;
Z = R + 1j*X;

I_peak = (E_src - V_bus) / Z;
I_mag  = abs(I_peak);

% 3-phase power from source terminal (peak phasors, vi_scale=0.5 convention)
raw_W_analytic = real(E_src * conj(I_peak)) * 3;
Pe_analytic = 0.5 * raw_W_analytic / 100e6;

fprintf('RESULT: I_peak_A=%.2f I_mag_A=%.2f\n', real(I_peak), I_mag);
fprintf('RESULT: Pe_analytic_pu=%.4f (from source terminal)\n', Pe_analytic);
fprintf('RESULT: I_ratio_vs_expected=%.2f\n', I_mag / (20e6*2/(3*185.6e3)));
```

**Interpretation:** If `Pe_analytic_pu ≈ 0.2–0.4` → the circuit physics predict low Pe, but probe reads 4 → measurement artefact (RC-A or RC-E). If `Pe_analytic_pu ≈ 4` → the model is genuinely in an over-powered state (RC-F).

---

## Task D — Write diagnostic artifact

- [ ] After Tasks A–C complete, write `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/pe_magnitude_diagnosis.json`:

```json
{
  "schema_version": 1,
  "scenario_id": "kundur",
  "purpose": "Diagnose Pe = 20x too large (measured 2.9-4.1 pu, expected 0.2 pu)",
  "current_facts": {
    "expected_pe_sys_pu": 0.2,
    "measured_pe_terminal_ref_pu": [4.056, 2.866, 3.858, 3.442],
    "vi_scale": 0.5,
    "Sbase_VA": 100e6,
    "formula": "Pe = vi_scale * real(sum(V .* conj(I))) / Sbase"
  },
  "task_a": {
    "Va_mag_kV": "<fill>",
    "Ia_mag_A_per_ESS": "<fill>",
    "Ia_expected_peak_A": 71.1,
    "ratio_I": "<fill>",
    "Pe_vi_computed_pu": "<fill>"
  },
  "task_b": {
    "P_out_available": "<fill true/false>",
    "Pe_pout_pu": "<fill or null>",
    "PeFb_available": "<fill true/false>",
    "Pe_feedback_pu": "<fill or null>"
  },
  "task_c": {
    "Pe_analytic_pu": "<fill>",
    "I_analytic_A": "<fill>",
    "I_ratio_vs_expected": "<fill>"
  },
  "verdict": "<RC-A | RC-B | RC-C | RC-D | RC-E | RC-F | INCONCLUSIVE>",
  "verdict_detail": "<fill from evidence>",
  "next_authorized_step": "awaiting human authorization",
  "provenance": {
    "no_model_saved": true,
    "run_timestamp": "2026-04-25",
    "agent": "claude-sonnet-4-6"
  }
}
```

Populate all `<fill>` fields from actual RESULT lines before writing.

---

## STOP conditions

```
STOP immediately if:
- model left dirty (close_system(..., 0) then reload from disk)
- about to edit any prohibited production file
- about to run Smoke Bridge, training, or cutover
- about to adjust vi_scale, Sbase, or gate threshold to "fix" Pe
- Task C analytical Pe ≈ measured Pe (RC-F confirmed) → write artifact, STOP, report
- task result contradicts working hypothesis → write artifact, STOP, report
```

**After STOP:** write pe_magnitude_diagnosis.json → update summary.md → update NOTES.md → report.
