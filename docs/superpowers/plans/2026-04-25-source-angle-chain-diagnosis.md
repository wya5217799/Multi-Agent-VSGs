# Kundur SPS — Source-Angle Chain Diagnosis

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Determine where in the chain `phAng_ES{i} → SPS ESS terminal bus angle` the ~11–16° error originates.

**Architecture:** Read-only audit + two targeted simulation probes. No model topology changes. No prohibited-file edits. Output: `source_angle_chain_diagnosis.json`.

**Tech stack:** MATLAB SPS Phasor / simulink_run_script MCP tool.

---

## Inherited constraints

```
Prohibited (no edit): build_kundur_sps.m  build_powerlib_kundur.m
                      compute_kundur_powerflow.m  kundur_ic.json
                      kundur_vsg_sps.slx  config_simulink.py
Smoke Bridge / training / cutover: blocked
simulink_save_model: prohibited
```

---

## Known facts (do not re-derive)

```
kundur_ic.json.vsg_delta0_deg = [12.621, 4.685, 6.227, 3.323] deg  (NR ESS delta/EMF angles)
build_kundur_sps.m line 137:  assignin('base', 'phAng_ES{i}', ess_delta0_deg(i))
build_kundur_sps.m line 129:  set_param(VSrc_ESi, 'PhaseAngle', 'phAng_ES{i}')
build_kundur_sps.m line 107:  powergui SimulationMode = 'Phasor'
probe StopTime = 0.05 s
angle extraction (probe line 226-227):
    V_cmplx = V_row(1) + 1j*V_row(2)   % Va + j*Vb
    sps_ang_raw = angle(V_cmplx) * 180/pi
NR ESS bus angles (like-for-like run): Bus12=10.917°, Bus16=2.975°, Bus14=4.481°, Bus15=1.612°
Observed SPS ESS bus (emf_reference): Bus12=0.164°, Bus16=-9.194°, Bus14=-6.383°, Bus15=-9.760°
```

---

## Task A — Verify angle extraction formula in Phasor mode

**Read-only. No simulation.**

In SPS Phasor mode the `Three-Phase V-I Measurement` outputs instantaneous waveform samples, not raw phasors. Each output column is:

```
V_a(t) = |V| * cos(2π*50*t + φ_a)
V_b(t) = |V| * cos(2π*50*t + φ_a - 120°)
```

The probe extracts angle as `angle(V_a + j*V_b)`. This is **not** the standard positive-sequence angle extraction (which uses the Clarke transform or phase-A-only formula). Check whether the formula recovers φ_a correctly.

- [ ] Compute analytically: for φ_a = 10.917° and t = 0.05 s (= 2.5 cycles, 50 Hz):

```matlab
% Run in simulink_run_script (no model needed)
phi_a_nr = 10.917 * pi/180;
t_end    = 0.05;
omega    = 2*pi*50;

Va = cos(omega*t_end + phi_a_nr);
Vb = cos(omega*t_end + phi_a_nr - 2*pi/3);
extracted = angle(Va + 1j*Vb) * 180/pi;

fprintf('RESULT: Va=%.6f  Vb=%.6f\n', Va, Vb);
fprintf('RESULT: extracted_angle_deg=%.4f (expected 10.917)\n', extracted);
fprintf('RESULT: error_deg=%.4f\n', extracted - 10.917);
```

- [ ] Also compute the correct Clarke-based extraction for comparison:

```matlab
% Correct positive-sequence angle at t=0.05 s
Vc = cos(omega*t_end + phi_a_nr + 2*pi/3);
Va_alpha = (2/3)*(Va - 0.5*Vb - 0.5*Vc);
Va_beta  = (2/3)*(sqrt(3)/2*Vb - sqrt(3)/2*Vc);
correct_angle = (atan2(Va_beta, Va_alpha) - omega*t_end) * 180/pi;
fprintf('RESULT: correct_angle_deg=%.4f\n', mod(correct_angle+180,360)-180);
```

**STOP A1:** If `extracted_angle_deg` is NOT close to 10.917° (error > 1°) → the angle extraction formula is wrong. Record the systematic error. Continue to Task B.

**STOP A2:** If `extracted_angle_deg ≈ 10.917°` (error < 0.1°) → angle extraction formula is correct. The error originates elsewhere. Continue to Task B.

---

## Task B — Real sim t_stop sweep (probe formula vs actual Vabc_ES1)

**Single-ESS. emf_reference generator angles. Real `sim()` calls at 6 t_stop values.**

Load model, set emf_reference angles, run 6 short sims, read actual Vabc_ES1.Data(end,:), apply probe formula. If the probe formula extracts a time-varying angle from a Phasor-mode steady-state output, the result will oscillate with period 1/50 = 0.02 s.

- [ ] Run in `simulink_run_script`:

```matlab
addpath('C:\Users\27443\Desktop\Multi-Agent  VSGs\scenarios\kundur\matlab_scripts');
addpath('C:\Users\27443\Desktop\Multi-Agent  VSGs\slx_helpers');

model_name = 'kundur_vsg_sps';
load_system(model_name);

% emf_reference generator angles
set_param([model_name '/GSrc_G1'], 'PhaseAngle', '32.385875');
set_param([model_name '/GSrc_G2'], 'PhaseAngle', '29.053883');
set_param([model_name '/GSrc_G3'], 'PhaseAngle', '19.374872');
set_param([model_name '/WSrc_W1'], 'PhaseAngle', '17.069560');
set_param([model_name '/WSrc_W2'], 'PhaseAngle',  '4.883907');
assignin('base', 'phAng_ES1', 12.620902);   % NR delta angle [deg]

t_stops = {'0.01','0.02','0.03','0.04','0.05','0.10'};
fprintf('RESULT: t_stop_sec  probe_angle_deg\n');
for k = 1:length(t_stops)
    simOut = sim(model_name, 'StopTime', t_stops{k});
    Vabc_ts = simOut.get('Vabc_ES1');
    V_row   = Vabc_ts.Data(end, :);
    probe_angle = angle(V_row(1) + 1j*V_row(2)) * 180/pi;
    fprintf('RESULT: %s  %.4f\n', t_stops{k}, probe_angle);
end
```

**STOP B1:** If `probe_angle` varies across t_stop values (range > 2°) → probe formula aliases with instantaneous phase at t_stop. `MEASUREMENT_EXTRACTION_OFFSET` is the likely root cause. Continue to Task C regardless.

**STOP B2:** If `probe_angle` is constant across t_stop values (range < 0.5°) → formula is stable; error is not a t_stop artifact. Continue to Task C.

---

## Task C — Mandatory dual-formula real model validation

**Unconditional — execute regardless of B1 or B2.**

Run one sim with emf_reference config, read Vabc_ES1, extract Bus12 angle with **both** the probe formula and the Clarke formula. Compare both to NR Bus12 = 10.917°.

- [ ] Run in `simulink_run_script` (model already loaded from Task B; generator angles already set):

```matlab
% model still loaded with emf_reference angles from Task B
model_name = 'kundur_vsg_sps';
omega  = 2*pi*50;
t_end  = 0.05;

simOut  = sim(model_name, 'StopTime', '0.05');
Vabc_ts = simOut.get('Vabc_ES1');
V_row   = Vabc_ts.Data(end, :);
Va = V_row(1);  Vb = V_row(2);  Vc = V_row(3);

% --- Probe formula (as used in static_workpoint_gate probe) ---
probe_angle = angle(Va + 1j*Vb) * 180/pi;

% --- Clarke positive-sequence formula ---
Va_alpha = (2/3)*(Va - 0.5*Vb - 0.5*Vc);
Va_beta  = (2/3)*(sqrt(3)/2*(Vb - Vc));
clarke_angle_raw = atan2(Va_beta, Va_alpha) * 180/pi;
clarke_angle_phasor = mod(clarke_angle_raw - omega*t_end*180/pi + 180, 360) - 180;

fprintf('RESULT: probe_formula_angle=%.4f\n',  probe_angle);
fprintf('RESULT: clarke_phasor_angle=%.4f\n',  clarke_angle_phasor);
fprintf('RESULT: NR_Bus12_expected=10.917\n');
fprintf('RESULT: probe_error=%.4f\n',  probe_angle  - 10.917);
fprintf('RESULT: clarke_error=%.4f\n', clarke_angle_phasor - 10.917);
```

**STOP C1:** If `clarke_phasor_angle ≈ 10.917°` (error < 1°) but `probe_angle` is far off → root cause is the probe extraction formula. Verdict = `MEASUREMENT_EXTRACTION_OFFSET`. Continue to Task D.

**STOP C2:** If both formulas give wrong angles (both error > 1°) → extraction formula is not the root cause. Record both values and await human decision before any further action. Still write Task D artifact with verdict = `ROOT_CAUSE_STILL_UNRESOLVED`.

---

## Task D — Write artifact

- [ ] Write `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/source_angle_chain_diagnosis.json`:

```json
{
  "schema_version": 1,
  "scenario_id": "kundur",
  "question": "Why does phAng_ES{i} = NR_delta not produce the expected ESS terminal bus angle?",
  "chain_links_checked": [
    "kundur_ic.json.vsg_delta0_deg (units: degrees, values correct)",
    "build_kundur_sps.m assignin(base, phAng_ES{i}, deg_value)",
    "VSrc_ES{i} PhaseAngle = expression phAng_ES{i}",
    "powergui mode = Phasor",
    "probe angle extraction: angle(Va + j*Vb) at t=t_stop",
    "probe t_stop = 0.05 s = 2.5 cycles"
  ],
  "task_a_result": "...",
  "task_b_result": "...",
  "task_c_result": "...",
  "verdict": "MEASUREMENT_EXTRACTION_OFFSET | PHANG_NOT_APPLIED | PHANG_REFERENCE_OFFSET | ROOT_CAUSE_STILL_UNRESOLVED",
  "verdict_detail": "...",
  "provenance": {
    "no_model_modified": true,
    "run_timestamp": "2026-04-25",
    "agent": "claude-sonnet-4-6"
  }
}
```

---

## STOP conditions

```
STOP A1: angle extraction formula confirmed wrong → record, continue to D
STOP B1: extracted angle oscillates with t_stop → root cause confirmed measurement formula → go to D
STOP B2: extraction stable → continue to C
STOP C1: Clarke formula correct, probe formula wrong → verdict MEASUREMENT_EXTRACTION_OFFSET → go to D
STOP C2: both formulas wrong → stop, await human decision
STOP D:  artifact written → STOP. Do not proceed to model edits or gate re-runs.
```

## Prohibited inference chains

```
formula_is_wrong → patch the probe
voltage_sign_issue → flip source polarity in build script
any_finding → start Smoke Bridge or training
```

Evidence → artifact → human decision. Nothing else.
