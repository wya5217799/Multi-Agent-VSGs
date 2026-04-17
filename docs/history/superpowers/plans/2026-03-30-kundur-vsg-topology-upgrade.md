# Kundur VSG Full Topology Upgrade — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `build_powerlib_kundur.m` from 4-bus simplified to full 16-bus Modified Kundur Two-Area System with G1-G3 conventional generators, W1/W2 wind farms, and 4 ESS/VSG units, all RL-training-ready.

**Architecture:** Rewrite the MATLAB build script to construct a 16-bus powerlib model. G1-G3 use signal-domain swing equations with governor droop (same subsystem pattern as VSGs but no RL input). W1/W2 are constant-power Three-Phase Sources. The existing VSG_ES1-ES4 subsystem structure, ToWorkspace loggers, and RL signal interface are preserved. Python-side changes are minimal (config updates for breaker paths and disturbance bus indices).

**Tech Stack:** MATLAB/Simulink R2025b (powerlib), Python 3.x (Gymnasium), existing SimulinkBridge + vsg_step_and_read.m

**Spec:** `docs/superpowers/specs/2026-03-30-kundur-vsg-topology-upgrade-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `scenarios/kundur/simulink_models/build_powerlib_kundur.m` | **Rewrite** | Build full 16-bus model with G1-G3, W1/W2, ES1-ES4 |
| `scenarios/kundur/config_simulink.py` | **Modify** | Update disturbance bus indices, breaker paths, load values |
| `env/simulink/kundur_simulink_env.py` | **Modify** | Update `_apply_disturbance_backend` breaker mapping |
| `vsg_helpers/vsg_step_and_read.m` | **No change** | Already generic (template-based paths) |
| `engine/simulink_bridge.py` | **No change** | Already generic |

---

### Task 1: Rewrite build script — Parameters and System Constants

**Files:**
- Modify: `scenarios/kundur/simulink_models/build_powerlib_kundur.m:1-100`

This task replaces the parameter section with full Kundur system data.

- [ ] **Step 1: Replace parameter section (lines 1-97)**

Replace the entire parameter section of `build_powerlib_kundur.m` with the expanded version below. This keeps fn=50, Sbase=100e6, Vbase=230e3, but adds G1-G3 and W1/W2 parameters, full line table (20 lines), full load table, and VSG connection parameters.

```matlab
%% build_powerlib_kundur.m
% Build Modified Kundur Two-Area System (Yang et al. TPWRS 2023)
% Full 16-bus topology with powerlib for MADRL VSG control.
%
% Architecture:
%   - 3 Conventional Generators (G1-G3): signal-domain swing equation
%     with governor droop, fed to Three-Phase Programmable Voltage Source
%   - 2 Wind Farms (W1, W2): constant-power Three-Phase Source (no freq response)
%   - 4 VSG/ESS (ES1-ES4): signal-domain swing equation with RL-controlled dM/dD
%   - Full Kundur two-area transmission network (20 PI-section lines)
%   - Loads at Bus7 (967 MW) and Bus9 (1767 MW) + shunt compensation
%   - Switchable disturbance loads at Bus14 (248 MW) and Bus15 (188 MW)
%   - ToWorkspace loggers for Python co-simulation
%
% Uses powerlib blocks exclusively (not ee_lib).
% Phasor mode + ode4 fixed-step for RL training speed.
%
% Reference: Yang et al., IEEE TPWRS 2023, DOI: 10.1109/TPWRS.2022.3221439

clear all; close all; clc;

%% ======================================================================
%  Parameters
%% ======================================================================
fn = 50;                  % System frequency (Hz) — Kundur original
wn = 2*pi*fn;             % Angular frequency (rad/s)
Sbase = 100e6;            % System base (VA) = 100 MVA
Vbase = 230e3;            % Transmission voltage (V)
Zbase = Vbase^2 / Sbase;  % 529 ohm

% --- Conventional Generator Parameters (Kundur textbook) ---
% G1, G2 (Area 1): H=6.5s, Sn=900 MVA
% G3 (Area 2):     H=6.175s, Sn=900 MVA
gen_params = struct();
gen_params(1).name = 'G1';  gen_params(1).bus = 1;  gen_params(1).H = 6.5;
gen_params(1).Sn = 900e6;   gen_params(1).D = 5.0;  gen_params(1).R = 0.05;
gen_params(1).P0 = 700e6;   gen_params(1).V0 = 1.03;  gen_params(1).A0 = 20.0;

gen_params(2).name = 'G2';  gen_params(2).bus = 2;  gen_params(2).H = 6.5;
gen_params(2).Sn = 900e6;   gen_params(2).D = 5.0;  gen_params(2).R = 0.05;
gen_params(2).P0 = 700e6;   gen_params(2).V0 = 1.01;  gen_params(2).A0 = 10.0;

gen_params(3).name = 'G3';  gen_params(3).bus = 3;  gen_params(3).H = 6.175;
gen_params(3).Sn = 900e6;   gen_params(3).D = 5.0;  gen_params(3).R = 0.05;
gen_params(3).P0 = 700e6;   gen_params(3).V0 = 1.03;  gen_params(3).A0 = -10.0;
n_gen = 3;

% --- Wind Farm Parameters ---
% W1 at Bus4: replaces G4, ~900 MVA capacity, no freq response
% W2 at Bus8: 100 MW, no freq response
wind_params = struct();
wind_params(1).name = 'W1'; wind_params(1).bus = 4;
wind_params(1).P0 = 700e6;  wind_params(1).Sn = 900e6;
wind_params(1).V0 = 1.01;   wind_params(1).A0 = -20.0;

wind_params(2).name = 'W2'; wind_params(2).bus = 8;
wind_params(2).P0 = 100e6;  wind_params(2).Sn = 200e6;
wind_params(2).V0 = 1.00;   wind_params(2).A0 = -5.0;
n_wind = 2;

% --- VSG/ESS Parameters (Yang et al.) ---
n_vsg = 4;
VSG_M0 = 12.0;            % M = 2H (s), H0 = 6.0 s
VSG_D0 = 3.0;             % Damping (p.u.)
VSG_SN = 200e6;            % VSG rated power (VA) = 200 MVA
VSG_P0 = 0.5;             % Initial active power (p.u. on VSG base) = 100 MW

vsg_params = struct();
vsg_params(1).name = 'ES1'; vsg_params(1).conn_bus = 7;  vsg_params(1).own_bus = 12;
vsg_params(1).V0 = 1.02;    vsg_params(1).A0 = 5.0;
vsg_params(2).name = 'ES2'; vsg_params(2).conn_bus = 8;  vsg_params(2).own_bus = 16;
vsg_params(2).V0 = 1.00;    vsg_params(2).A0 = -3.0;
vsg_params(3).name = 'ES3'; vsg_params(3).conn_bus = 10; vsg_params(3).own_bus = 14;
vsg_params(3).V0 = 1.01;    vsg_params(3).A0 = -8.0;
vsg_params(4).name = 'ES4'; vsg_params(4).conn_bus = 9;  vsg_params(4).own_bus = 15;
vsg_params(4).V0 = 1.02;    vsg_params(4).A0 = -12.0;

% --- Generator internal impedance (all machines, on Sbase) ---
R_gen_pu = 0.003;
X_gen_pu = 0.30;
R_gen = R_gen_pu * Zbase;                % ohm
L_gen = X_gen_pu * Zbase / (2*pi*fn);   % H

% --- Transmission Line Parameters ---
% Kundur standard: R=0.053 Ohm/km, L=1.41 mH/km, C=0.009 uF/km
R_km = 0.053;  L_km = 1.41;  C_km = 0.009;

% Full line table: [from_bus, to_bus, length_km, parallel_count]
line_table = {
    'L_1_5',   1,  5,    5, 1;    % Gen1 step-up equivalent
    'L_2_6',   2,  6,    5, 1;    % Gen2 step-up equivalent
    'L_3_10',  3,  10,   5, 1;    % Gen3 step-up equivalent
    'L_4_9',   4,  9,    5, 1;    % W1 step-up equivalent
    'L_5_6a',  5,  6,   25, 1;    % Intra-Area 1
    'L_5_6b',  5,  6,   25, 1;
    'L_6_7a',  6,  7,   10, 1;
    'L_6_7b',  6,  7,   10, 1;
    'L_7_8a',  7,  8,  110, 1;    % Tie lines (weak)
    'L_7_8b',  7,  8,  110, 1;
    'L_7_8c',  7,  8,  110, 1;
    'L_8_9a',  8,  9,   10, 1;    % Intra-Area 2
    'L_8_9b',  8,  9,   10, 1;
    'L_9_10a', 9,  10,  25, 1;
    'L_9_10b', 9,  10,  25, 1;
};
% VSG connection lines (short, low impedance)
R_vsg_km = 0.01;  L_vsg_km = 0.5;  C_vsg_km = 0.009;
vsg_line_table = {
    'L_7_12',  7,  12, 1;    % ES1 connection
    'L_8_16',  8,  16, 1;    % ES2 connection
    'L_10_14', 10, 14, 1;    % ES3 connection
    'L_9_15',  9,  15, 1;    % ES4 connection
    'L_8_W2',  8,  13, 1;    % W2 connection (via Bus13)
};

% --- Load Parameters ---
% Loads and shunt compensation (Kundur standard)
load_table = {
    'Load7',   7,  967e6,  100e6;   % Bus7: 967 MW + j100 Mvar
    'Load9',   9,  1767e6, 100e6;   % Bus9: 1767 MW + j100 Mvar
};
shunt_table = {
    'Shunt7',  7,  0,  200e6;   % 200 Mvar capacitive (Q negative = cap)
    'Shunt9',  9,  0,  350e6;   % 350 Mvar capacitive
};
% Disturbance loads (switchable via breaker)
trip_table = {
    'Trip_Load1', 14, 248e6,  0;    % Load Step 1: 248 MW at Bus14
    'Trip_Load2', 15, 188e6,  0;    % Load Step 2: 188 MW at Bus15
};
```

- [ ] **Step 2: Verify syntax**

Open MATLAB, `cd` to the script directory, and run just the parameter section (copy-paste lines 1-100 into command window). Verify no errors. Expected: all variables defined in workspace.

- [ ] **Step 3: Commit parameters**

```bash
git add scenarios/kundur/simulink_models/build_powerlib_kundur.m
git commit -m "refactor(simulink): expand build script parameters to full 16-bus Kundur"
```

---

### Task 2: Build Conventional Generator Subsystem (SG_Gen)

**Files:**
- Modify: `scenarios/kundur/simulink_models/build_powerlib_kundur.m` (add after parameter section)

G1-G3 use the same signal-domain swing equation as the VSG subsystem, but with two differences:
1. **Governor droop:** `P_ref = P0 - (omega - 1.0) * Sn / R` provides frequency-dependent power adjustment
2. **No RL input:** `delta_M` and `delta_D` ports are removed; H and D are fixed constants

- [ ] **Step 1: Add `build_sg_gen` helper function**

Add this function at the **end** of the file (MATLAB allows nested functions at end of script in R2016b+):

```matlab
function build_sg_gen(mdl, name, pos, H, D, Sn, P0_W, V0, A0, R_droop, fn, Vbase, R_gen, L_gen)
%BUILD_SG_GEN  Build a conventional generator subsystem with governor droop.
%
%   Signal-domain swing equation:
%     M = 2*H, fixed
%     d(omega)/dt = (1/M) * (P_mech - P_e - D*(omega-1))
%     P_mech = P0 - (omega-1) * Sn / (R * Sbase)   (governor droop)
%     d(delta)/dt = wn * (omega - 1)

    wn = 2*pi*fn;
    Sbase = 100e6;
    M = 2 * H;
    P0_pu = P0_W / Sn;           % p.u. on machine base
    droop_gain = Sn / (R_droop * Sbase);  % droop slope on system base

    sg_path = [mdl '/' name];
    add_block('built-in/SubSystem', sg_path, 'Position', pos);

    % --- Inputs: P_e (from V-I measurement power calc) ---
    add_block('built-in/Inport', [sg_path '/P_e'], ...
        'Position', [30 80 60 94], 'Port', '1');

    % --- Outputs: omega, delta ---
    add_block('built-in/Outport', [sg_path '/omega'], ...
        'Position', [700 30 730 44], 'Port', '1');
    add_block('built-in/Outport', [sg_path '/delta'], ...
        'Position', [700 250 730 264], 'Port', '2');

    % --- Constants ---
    add_block('built-in/Constant', [sg_path '/M_const'], ...
        'Position', [400 10 440 30], 'Value', num2str(M));
    add_block('built-in/Constant', [sg_path '/D_const'], ...
        'Position', [100 130 140 150], 'Value', num2str(D));
    add_block('built-in/Constant', [sg_path '/P0_const'], ...
        'Position', [30 30 70 50], 'Value', num2str(P0_pu));
    add_block('built-in/Constant', [sg_path '/droop_gain'], ...
        'Position', [100 170 160 190], 'Value', num2str(droop_gain));
    add_block('built-in/Constant', [sg_path '/wn_const'], ...
        'Position', [300 240 340 260], 'Value', num2str(wn));

    % omega_error = omega - 1.0
    add_block('built-in/Constant', [sg_path '/one'], ...
        'Position', [450 70 480 90], 'Value', '1.0');
    add_block('built-in/Sum', [sg_path '/SumErr'], ...
        'Position', [510 50 540 80], 'Inputs', '+-');

    % Governor: P_mech = P0 - droop_gain * omega_error
    add_block('built-in/Product', [sg_path '/MulDroop'], ...
        'Position', [200 150 230 185], 'Inputs', '**');
    add_block('built-in/Sum', [sg_path '/SumGov'], ...
        'Position', [280 40 310 75], 'Inputs', '+-');

    % D_term = D * omega_error
    add_block('built-in/Product', [sg_path '/MulD'], ...
        'Position', [280 110 310 145], 'Inputs', '**');

    % P_accel = P_mech - P_e - D_term
    add_block('built-in/Sum', [sg_path '/SumP'], ...
        'Position', [350 60 380 120], 'Inputs', '+--');

    % d_omega = P_accel / M
    add_block('built-in/Product', [sg_path '/DivM'], ...
        'Position', [420 60 450 100], 'Inputs', '*/');

    % Integrator for omega (IC=1.0, limits [0.9, 1.1])
    add_block('built-in/Integrator', [sg_path '/IntW'], ...
        'Position', [480 60 520 100], ...
        'InitialCondition', '1.0', ...
        'UpperSaturationLimit', '1.1', ...
        'LowerSaturationLimit', '0.9');

    % Integrator for delta
    delta0_rad = A0 * pi / 180;
    add_block('built-in/Integrator', [sg_path '/IntD'], ...
        'Position', [450 230 490 270], ...
        'InitialCondition', num2str(delta0_rad));

    % d(delta)/dt = wn * omega_error
    add_block('built-in/Product', [sg_path '/MulWn'], ...
        'Position', [370 230 400 265], 'Inputs', '**');

    % === Wiring ===
    % omega -> output + feedback
    add_line(sg_path, 'IntW/1', 'omega/1');
    add_line(sg_path, 'IntW/1', 'SumErr/1');
    add_line(sg_path, 'one/1', 'SumErr/2');

    % omega_error -> governor droop, D_term, delta integrator
    add_line(sg_path, 'SumErr/1', 'MulDroop/2');
    add_line(sg_path, 'droop_gain/1', 'MulDroop/1');
    add_line(sg_path, 'SumErr/1', 'MulD/2');
    add_line(sg_path, 'D_const/1', 'MulD/1');
    add_line(sg_path, 'SumErr/1', 'MulWn/2');
    add_line(sg_path, 'wn_const/1', 'MulWn/1');

    % Governor: P_mech = P0 - droop_gain * omega_error
    add_line(sg_path, 'P0_const/1', 'SumGov/1');
    add_line(sg_path, 'MulDroop/1', 'SumGov/2');

    % P_accel = P_mech - P_e - D_term
    add_line(sg_path, 'SumGov/1', 'SumP/1');
    add_line(sg_path, 'P_e/1', 'SumP/2');
    add_line(sg_path, 'MulD/1', 'SumP/3');

    % d_omega = P_accel / M
    add_line(sg_path, 'SumP/1', 'DivM/1');
    add_line(sg_path, 'M_const/1', 'DivM/2');
    add_line(sg_path, 'DivM/1', 'IntW/1');

    % delta
    add_line(sg_path, 'MulWn/1', 'IntD/1');
    add_line(sg_path, 'IntD/1', 'delta/1');
end
```

- [ ] **Step 2: Add main section that builds G1-G3 using the helper**

Add this section after Step 1 (powergui) in the main script body, before the VSG section:

```matlab
%% ======================================================================
%  Step 2: Build Conventional Generators (G1-G3)
%% ======================================================================
fprintf('\n=== Building Conventional Generators ===\n');

% Layout: G1,G2 on left (Area 1), G3 on right (Area 2)
gen_pos = {[50 100 170 200], [50 350 170 450], [1200 100 1320 200]};

for i = 1:n_gen
    gp = gen_params(i);
    build_sg_gen(mdl, gp.name, gen_pos{i}, ...
        gp.H, gp.D, gp.Sn, gp.P0, gp.V0, gp.A0, gp.R, fn, Vbase, R_gen, L_gen);

    % Three-Phase Source driven by SG subsystem
    src_name = sprintf('VSrc_%s', gp.name);
    src_path = [mdl '/' src_name];
    bx = gen_pos{i}(1); by = gen_pos{i}(4) + 50;
    V_src = Vbase * gp.V0;

    add_block('powerlib/Electrical Sources/Three-Phase Source', ...
        src_path, 'Position', [bx by bx+80 by+80]);
    set_param(src_path, ...
        'Voltage', num2str(V_src), ...
        'PhaseAngle', num2str(gp.A0), ...
        'Frequency', num2str(fn), ...
        'InternalConnection', 'Yg', ...
        'Resistance', num2str(R_gen), ...
        'Inductance', num2str(L_gen));

    % V-I Measurement
    meas_name = sprintf('Meas_%s', gp.name);
    add_block('powerlib/Measurements/Three-Phase V-I Measurement', ...
        [mdl '/' meas_name], 'Position', [bx+120 by bx+200 by+80]);
    set_param([mdl '/' meas_name], ...
        'VoltageMeasurement', 'phase-to-ground', ...
        'CurrentMeasurement', 'yes');

    % Wire Source -> Measurement
    for p = 1:3
        add_line(mdl, sprintf('%s/RConn%d', src_name, p), ...
            sprintf('%s/LConn%d', meas_name, p), 'autorouting', 'smart');
    end

    % ToWorkspace loggers for omega (for monitoring, not RL obs)
    log_name = sprintf('Log_omega_%s', gp.name);
    add_block('built-in/ToWorkspace', [mdl '/' log_name], ...
        'Position', [bx+200 gen_pos{i}(2) bx+260 gen_pos{i}(2)+20], ...
        'VariableName', sprintf('omega_%s', gp.name), ...
        'SaveFormat', 'Timeseries');
    add_line(mdl, sprintf('%s/1', gp.name), [log_name '/1'], 'autorouting', 'smart');

    fprintf('  Built %s at Bus%d: H=%.1fs, Sn=%.0fMVA, R=%.2f\n', ...
        gp.name, gp.bus, gp.H, gp.Sn/1e6, gp.R);
end
```

- [ ] **Step 3: Commit**

```bash
git add scenarios/kundur/simulink_models/build_powerlib_kundur.m
git commit -m "feat(simulink): add SG_Gen subsystem with governor droop for G1-G3"
```

---

### Task 3: Add Wind Farms W1 and W2

**Files:**
- Modify: `scenarios/kundur/simulink_models/build_powerlib_kundur.m`

Wind farms are simple: constant-power Three-Phase Sources with internal impedance but no swing equation.

- [ ] **Step 1: Add wind farm section after generators**

```matlab
%% ======================================================================
%  Step 3: Build Wind Farms (W1, W2) — constant power, no freq response
%% ======================================================================
fprintf('\n=== Building Wind Farms ===\n');

wind_pos = {[1200 350 1280 430], [650 600 730 680]};

for i = 1:n_wind
    wp = wind_params(i);
    src_name = sprintf('VSrc_%s', wp.name);
    src_path = [mdl '/' src_name];
    bx = wind_pos{i}(1); by = wind_pos{i}(2);
    V_src = Vbase * wp.V0;

    add_block('powerlib/Electrical Sources/Three-Phase Source', ...
        src_path, 'Position', [bx by bx+80 by+80]);
    set_param(src_path, ...
        'Voltage', num2str(V_src), ...
        'PhaseAngle', num2str(wp.A0), ...
        'Frequency', num2str(fn), ...
        'InternalConnection', 'Yg', ...
        'Resistance', num2str(R_gen), ...
        'Inductance', num2str(L_gen));

    % V-I Measurement
    meas_name = sprintf('Meas_%s', wp.name);
    add_block('powerlib/Measurements/Three-Phase V-I Measurement', ...
        [mdl '/' meas_name], 'Position', [bx+120 by bx+200 by+80]);
    set_param([mdl '/' meas_name], ...
        'VoltageMeasurement', 'phase-to-ground', ...
        'CurrentMeasurement', 'yes');

    for p = 1:3
        add_line(mdl, sprintf('%s/RConn%d', src_name, p), ...
            sprintf('%s/LConn%d', meas_name, p), 'autorouting', 'smart');
    end

    fprintf('  Built %s at Bus%d: P=%.0fMW (constant)\n', ...
        wp.name, wp.bus, wp.P0/1e6);
end
```

- [ ] **Step 2: Commit**

```bash
git add scenarios/kundur/simulink_models/build_powerlib_kundur.m
git commit -m "feat(simulink): add W1/W2 constant-power wind farm sources"
```

---

### Task 4: Keep VSG Subsystems (ES1-ES4) — Adapt positions only

**Files:**
- Modify: `scenarios/kundur/simulink_models/build_powerlib_kundur.m`

The existing VSG subsystem code (Step 2 in current script, lines 121-254) is mostly correct. We need to:
1. Update layout positions to fit the 16-bus diagram
2. Update initial angle values from the `vsg_params` struct
3. Keep all 5 inputs (omega_ref, delta_M, delta_D, P_ref, P_e) and 3 outputs (omega, delta, P_out)

- [ ] **Step 1: Update VSG section to use `vsg_params` struct**

Replace the hardcoded `vsg_pos_x/vsg_pos_y` and `vlf` arrays with positions derived from the full layout. The VSG subsystem internal structure (swing equation, integrators, wiring) stays identical — only positions and initial conditions change.

```matlab
%% ======================================================================
%  Step 4: Build VSG/ESS subsystems (ES1-ES4, RL-controlled)
%% ======================================================================
fprintf('\n=== Building VSG subsystems ===\n');

% Layout positions (spread across the 16-bus diagram)
% ES1 near Bus7 (Area 1), ES2 near Bus8 (tie), ES3 near Bus10 (Area 2), ES4 near Bus9
vsg_pos = {[450 500 570 600], [650 750 770 850], [1050 500 1170 600], [850 500 970 600]};

for i = 1:n_vsg
    vp = vsg_params(i);
    vsg_name = sprintf('VSG_ES%d', i);
    vsg_path = [mdl '/' vsg_name];
    pos = vsg_pos{i};

    % Create subsystem (same internal structure as before)
    add_block('built-in/SubSystem', vsg_path, 'Position', pos);

    % 5 inputs: omega_ref, delta_M, delta_D, P_ref, P_e
    input_names = {'omega_ref', 'delta_M', 'delta_D', 'P_ref', 'P_e'};
    for k = 1:5
        inp = sprintf('%s/In%d', vsg_path, k);
        add_block('built-in/Inport', inp, ...
            'Position', [30, 20+(k-1)*50, 60, 34+(k-1)*50], 'Port', num2str(k));
        set_param(inp, 'Name', input_names{k});
    end

    % 3 outputs: omega, delta, P_out
    output_names = {'omega', 'delta', 'P_out'};
    for k = 1:3
        outp = sprintf('%s/Out%d', vsg_path, k);
        add_block('built-in/Outport', outp, ...
            'Position', [700, 30+(k-1)*80, 730, 44+(k-1)*80], 'Port', num2str(k));
        set_param(outp, 'Name', output_names{k});
    end

    % --- Internal swing equation (IDENTICAL to previous version) ---
    % M_total = M0 + delta_M, D_total = D0 + delta_D
    % d(omega)/dt = (1/M_total) * (P_ref - P_e - D_total * (omega - omega_ref))
    % d(delta)/dt = wn * (omega - omega_ref)
    % P_out = P_ref - D_total * (omega - omega_ref)

    add_block('built-in/Constant', [vsg_path '/M0'], ...
        'Position', [100 10 150 30], 'Value', num2str(VSG_M0));
    add_block('built-in/Constant', [vsg_path '/D0'], ...
        'Position', [100 60 150 80], 'Value', num2str(VSG_D0));
    add_block('built-in/Constant', [vsg_path '/wn'], ...
        'Position', [300 260 350 280], 'Value', num2str(wn));

    add_block('built-in/Sum', [vsg_path '/SumM'], ...
        'Position', [180 15 210 45], 'Inputs', '++');
    add_line(vsg_path, 'M0/1', 'SumM/1');
    add_line(vsg_path, 'delta_M/1', 'SumM/2');

    add_block('built-in/Sum', [vsg_path '/SumD'], ...
        'Position', [180 65 210 95], 'Inputs', '++');
    add_line(vsg_path, 'D0/1', 'SumD/1');
    add_line(vsg_path, 'delta_D/1', 'SumD/2');

    add_block('built-in/Sum', [vsg_path '/SumW'], ...
        'Position', [350 120 380 150], 'Inputs', '+-');

    add_block('built-in/Product', [vsg_path '/MulD'], ...
        'Position', [420 80 450 110], 'Inputs', '**');

    add_block('built-in/Sum', [vsg_path '/SumP'], ...
        'Position', [490 80 520 140], 'Inputs', '+--');

    add_block('built-in/Product', [vsg_path '/DivM'], ...
        'Position', [550 80 580 120], 'Inputs', '*/');

    add_block('built-in/Integrator', [vsg_path '/IntW'], ...
        'Position', [620 80 660 120], ...
        'InitialCondition', '1.0', ...
        'UpperSaturationLimit', '1.1', ...
        'LowerSaturationLimit', '0.9');

    delta0_rad = vp.A0 * pi / 180;
    add_block('built-in/Integrator', [vsg_path '/IntD'], ...
        'Position', [500 240 540 280], ...
        'InitialCondition', num2str(delta0_rad));

    % Wiring (identical to original)
    add_line(vsg_path, 'IntW/1', 'omega/1');
    add_line(vsg_path, 'IntW/1', 'SumW/1');
    add_line(vsg_path, 'omega_ref/1', 'SumW/2');
    add_line(vsg_path, 'SumD/1', 'MulD/1');
    add_line(vsg_path, 'SumW/1', 'MulD/2');
    add_line(vsg_path, 'P_ref/1', 'SumP/1');
    add_line(vsg_path, 'P_e/1', 'SumP/2');
    add_line(vsg_path, 'MulD/1', 'SumP/3');
    add_line(vsg_path, 'SumP/1', 'DivM/1');
    add_line(vsg_path, 'SumM/1', 'DivM/2');
    add_line(vsg_path, 'DivM/1', 'IntW/1');

    add_block('built-in/Product', [vsg_path '/MulWn'], ...
        'Position', [420 240 450 280], 'Inputs', '**');
    add_line(vsg_path, 'wn/1', 'MulWn/1');
    add_line(vsg_path, 'SumW/1', 'MulWn/2');
    add_line(vsg_path, 'MulWn/1', 'IntD/1');
    add_line(vsg_path, 'IntD/1', 'delta/1');

    add_block('built-in/Sum', [vsg_path '/SumPout'], ...
        'Position', [490 310 520 340], 'Inputs', '+-');
    add_line(vsg_path, 'P_ref/1', 'SumPout/1');
    add_line(vsg_path, 'MulD/1', 'SumPout/2');
    add_line(vsg_path, 'SumPout/1', 'P_out/1');

    fprintf('  Built %s (Bus%d -> Bus%d)\n', vsg_name, vp.own_bus, vp.conn_bus);
end
```

- [ ] **Step 2: Add VSG Three-Phase Sources + V-I Measurements + signal connections + ToWorkspace loggers**

This is identical to the original script's Step 3 + Step 6, just using `vsg_params` for positions and initial values. Keep the same block naming (`VSrc_ES{i}`, `Meas_ES{i}`, `dM_{i}`, `dD_{i}`, `Log_omega_ES{i}`, etc.) so the Python side doesn't need changes.

```matlab
%% ======================================================================
%  Step 5: VSG Electrical Interface (Sources + V-I + Loggers)
%% ======================================================================
fprintf('\n=== Adding VSG electrical interface ===\n');

vsg_src_names = cell(1, n_vsg);
vsg_meas_names = cell(1, n_vsg);

for i = 1:n_vsg
    vp = vsg_params(i);
    bx = vsg_pos{i}(1); by = vsg_pos{i}(4) + 50;
    V_src = Vbase * vp.V0;

    src_name = sprintf('VSrc_ES%d', i);
    src_path = [mdl '/' src_name];
    vsg_src_names{i} = src_name;
    add_block('powerlib/Electrical Sources/Three-Phase Source', ...
        src_path, 'Position', [bx by bx+80 by+80]);
    set_param(src_path, ...
        'Voltage', num2str(V_src), ...
        'PhaseAngle', num2str(vp.A0), ...
        'Frequency', num2str(fn), ...
        'InternalConnection', 'Yg', ...
        'Resistance', num2str(R_gen), ...
        'Inductance', num2str(L_gen));

    meas_name = sprintf('Meas_ES%d', i);
    meas_path = [mdl '/' meas_name];
    vsg_meas_names{i} = meas_name;
    add_block('powerlib/Measurements/Three-Phase V-I Measurement', ...
        meas_path, 'Position', [bx+120 by bx+200 by+80]);
    set_param(meas_path, ...
        'VoltageMeasurement', 'phase-to-ground', ...
        'CurrentMeasurement', 'yes');

    for p = 1:3
        add_line(mdl, sprintf('%s/RConn%d', src_name, p), ...
            sprintf('%s/LConn%d', meas_name, p), 'autorouting', 'smart');
    end

    % V-I loggers
    for ml = 1:2
        tags = {'Vabc', 'Iabc'};
        log_name = sprintf('Log_%s_ES%d', tags{ml}, i);
        add_block('built-in/ToWorkspace', [mdl '/' log_name], ...
            'Position', [bx+250 by+(ml-1)*40 bx+310 by+(ml-1)*40+20], ...
            'VariableName', sprintf('%s_ES%d', tags{ml}, i), ...
            'SaveFormat', 'Timeseries');
        add_line(mdl, sprintf('%s/%d', meas_name, ml), ...
            [log_name '/1'], 'autorouting', 'smart');
    end

    % Signal inputs (dM, dD, wref, Pref, Pe) and output loggers
    vsg_name = sprintf('VSG_ES%d', i);
    const_defs = {
        sprintf('wref_%d', i),  '1.0';
        sprintf('dM_%d', i),    '0';
        sprintf('dD_%d', i),    '0';
        sprintf('Pref_%d', i),  num2str(VSG_P0);
        sprintf('Pe_%d', i),    num2str(VSG_P0);
    };
    for cb = 1:size(const_defs, 1)
        cname = const_defs{cb, 1};
        cval = const_defs{cb, 2};
        cx = vsg_pos{i}(1) - 120;
        cy = vsg_pos{i}(2) - 10 + (cb-1) * 25;
        add_block('built-in/Constant', [mdl '/' cname], ...
            'Position', [cx cy cx+40 cy+15], 'Value', cval);
        add_line(mdl, [cname '/1'], sprintf('%s/%d', vsg_name, cb), ...
            'autorouting', 'smart');
    end

    out_names = {'omega', 'delta', 'P_out'};
    for out_idx = 1:3
        log_name = sprintf('Log_%s_ES%d', out_names{out_idx}, i);
        lx = vsg_pos{i}(3) + 30;
        ly = vsg_pos{i}(2) - 10 + (out_idx-1) * 30;
        add_block('built-in/ToWorkspace', [mdl '/' log_name], ...
            'Position', [lx ly lx+60 ly+20], ...
            'VariableName', sprintf('%s_ES%d', out_names{out_idx}, i), ...
            'SaveFormat', 'Timeseries');
        add_line(mdl, sprintf('%s/%d', vsg_name, out_idx), ...
            [log_name '/1'], 'autorouting', 'smart');
    end

    fprintf('  VSG_ES%d: source + measurement + loggers connected.\n', i);
end
```

- [ ] **Step 3: Commit**

```bash
git add scenarios/kundur/simulink_models/build_powerlib_kundur.m
git commit -m "feat(simulink): adapt VSG ES1-ES4 layout for 16-bus topology"
```

---

### Task 5: Build Full 16-Bus Transmission Network

**Files:**
- Modify: `scenarios/kundur/simulink_models/build_powerlib_kundur.m`

This is the biggest structural change: replacing 3 lines with 20 lines and wiring the full bus network.

- [ ] **Step 1: Add helper function for PI section lines**

```matlab
function add_pi_line(mdl, name, pos, R_km, L_km, C_km, len_km, fn)
%ADD_PI_LINE  Add a Three-Phase PI Section Line with auto-converted params.
    Zbase_dummy = 1;  % params already in physical units per km
    R_ohm = R_km * len_km;
    L_H = L_km * 1e-3 * len_km;      % mH/km -> H total
    C_F = C_km * 1e-6 * len_km;      % uF/km -> F total

    R_str = sprintf('[%g %g]', R_ohm, R_ohm*3);
    L_str = sprintf('[%g %g]', L_H, L_H*3);
    C_str = sprintf('[%g %g]', C_F, C_F/3);

    add_block('powerlib/Elements/Three-Phase PI Section Line', ...
        [mdl '/' name], 'Position', pos);
    set_param([mdl '/' name], ...
        'Frequency', num2str(fn), ...
        'Resistances', R_str, ...
        'Inductances', L_str, ...
        'Capacitances', C_str, ...
        'Length', '1');  % Total values already computed
end
```

- [ ] **Step 2: Add main network and bus wiring**

This section adds all 20 lines and wires them to create the full Kundur bus network. Buses are implicit nodes (wire junctions). Each generator/VSG/wind farm connects to its bus via its V-I measurement block's RConn ports. Lines connect buses together.

```matlab
%% ======================================================================
%  Step 6: Full Transmission Network (15 main + 5 VSG connection lines)
%% ======================================================================
fprintf('\n=== Building transmission network ===\n');

% --- Main transmission lines ---
% Auto-position based on from/to bus geometry
for k = 1:size(line_table, 1)
    name = line_table{k, 1};
    len = line_table{k, 4};
    % Position calculated from bus layout (simplified: row-based)
    pos = [300 + k*70, 900, 380 + k*70, 940];
    add_pi_line(mdl, name, pos, R_km, L_km, C_km, len, fn);
    fprintf('  %s: %.0f km\n', name, len);
end

% --- VSG connection lines (short, low impedance) ---
for k = 1:size(vsg_line_table, 1)
    name = vsg_line_table{k, 1};
    pos = [300 + k*70, 960, 380 + k*70, 1000];
    add_pi_line(mdl, name, pos, R_vsg_km, L_vsg_km, C_vsg_km, vsg_line_table{k, 4}, fn);
    fprintf('  %s: VSG connection\n', name);
end

%% ======================================================================
%  Step 7: Wire bus network
%% ======================================================================
fprintf('\n=== Wiring bus network ===\n');

% Helper: connect two blocks at their 3-phase ports
% side: 'L' = LConn, 'R' = RConn
wire3 = @(from, fs, to, ts) arrayfun(@(p) ...
    add_line(mdl, sprintf('%s/%sConn%d',from,fs,p), ...
                  sprintf('%s/%sConn%d',to,ts,p), ...
                  'autorouting','smart'), 1:3, 'Uni', false);

% --- Bus 1: G1 -> L_1_5 ---
wire3('Meas_G1', 'R', 'L_1_5', 'L');

% --- Bus 2: G2 -> L_2_6 ---
wire3('Meas_G2', 'R', 'L_2_6', 'L');

% --- Bus 3: G3 -> L_3_10 ---
wire3('Meas_G3', 'R', 'L_3_10', 'L');

% --- Bus 4: W1 -> L_4_9 ---
wire3('Meas_W1', 'R', 'L_4_9', 'L');

% --- Bus 5: L_1_5/R -> L_5_6a/L, L_5_6b/L ---
wire3('L_1_5', 'R', 'L_5_6a', 'L');
wire3('L_1_5', 'R', 'L_5_6b', 'L');

% --- Bus 6: L_5_6a/R, L_5_6b/R, L_2_6/R -> L_6_7a/L, L_6_7b/L ---
wire3('L_5_6a', 'R', 'L_6_7a', 'L');
wire3('L_5_6a', 'R', 'L_6_7b', 'L');
wire3('L_5_6b', 'R', 'L_5_6a', 'R');  % join at Bus6
wire3('L_2_6', 'R', 'L_5_6a', 'R');   % join at Bus6

% --- Bus 7: L_6_7a/R, L_6_7b/R -> ties, loads, ES1 ---
wire3('L_6_7a', 'R', 'L_7_8a', 'L');
wire3('L_6_7a', 'R', 'L_7_8b', 'L');
wire3('L_6_7a', 'R', 'L_7_8c', 'L');
wire3('L_6_7a', 'R', 'L_7_12', 'L');   % ES1 connection line
wire3('L_6_7b', 'R', 'L_6_7a', 'R');   % join at Bus7

% --- Bus 8: L_7_8a/R, L_7_8b/R, L_7_8c/R -> L_8_9, L_8_16, L_8_W2 ---
wire3('L_7_8a', 'R', 'L_8_9a', 'L');
wire3('L_7_8a', 'R', 'L_8_9b', 'L');
wire3('L_7_8a', 'R', 'L_8_16', 'L');   % ES2 connection line
wire3('L_7_8a', 'R', 'L_8_W2', 'L');   % W2 connection line
wire3('L_7_8b', 'R', 'L_7_8a', 'R');   % join at Bus8
wire3('L_7_8c', 'R', 'L_7_8a', 'R');   % join at Bus8

% --- Bus 9: L_8_9a/R, L_8_9b/R, L_4_9/R -> L_9_10, L_9_15 ---
wire3('L_8_9a', 'R', 'L_9_10a', 'L');
wire3('L_8_9a', 'R', 'L_9_10b', 'L');
wire3('L_8_9a', 'R', 'L_9_15', 'L');   % ES4 connection line
wire3('L_8_9b', 'R', 'L_8_9a', 'R');   % join at Bus9
wire3('L_4_9', 'R', 'L_8_9a', 'R');    % join at Bus9

% --- Bus 10: L_9_10a/R, L_9_10b/R, L_3_10/R -> L_10_14 ---
wire3('L_9_10a', 'R', 'L_10_14', 'L');   % ES3 connection line
wire3('L_9_10b', 'R', 'L_9_10a', 'R');   % join at Bus10
wire3('L_3_10', 'R', 'L_9_10a', 'R');    % join at Bus10

% --- Bus 12 (ES1): L_7_12/R -> Meas_ES1/R ---
wire3('L_7_12', 'R', 'Meas_ES1', 'R');

% --- Bus 13/W2: L_8_W2/R -> Meas_W2/R ---
wire3('L_8_W2', 'R', 'Meas_W2', 'R');

% --- Bus 14 (ES3): L_10_14/R -> Meas_ES3/R ---
wire3('L_10_14', 'R', 'Meas_ES3', 'R');

% --- Bus 15 (ES4): L_9_15/R -> Meas_ES4/R ---
wire3('L_9_15', 'R', 'Meas_ES4', 'R');

% --- Bus 16 (ES2): L_8_16/R -> Meas_ES2/R ---
wire3('L_8_16', 'R', 'Meas_ES2', 'R');

fprintf('  Network wired: 20 lines, 16 buses.\n');
```

- [ ] **Step 3: Commit**

```bash
git add scenarios/kundur/simulink_models/build_powerlib_kundur.m
git commit -m "feat(simulink): add full 16-bus Kundur transmission network"
```

---

### Task 6: Add Loads, Shunt Compensation, and Disturbance Breakers

**Files:**
- Modify: `scenarios/kundur/simulink_models/build_powerlib_kundur.m`

- [ ] **Step 1: Add loads and shunt compensation at Bus7 and Bus9**

```matlab
%% ======================================================================
%  Step 8: Loads and Shunt Compensation
%% ======================================================================
fprintf('\n=== Adding loads and shunt compensation ===\n');

% Loads at Bus7 and Bus9 (connected to Bus7 node = L_6_7a/RConn, Bus9 node = L_8_9a/RConn)
bus_node = struct('bus7', 'L_6_7a', 'bus9', 'L_8_9a');

for k = 1:size(load_table, 1)
    lname = load_table{k, 1};
    lbus = load_table{k, 2};
    lP = load_table{k, 3};
    lQ = load_table{k, 4};

    pos = [500 + k*150, 1050, 560 + k*150, 1090];
    add_block('powerlib/Elements/Three-Phase Series RLC Load', ...
        [mdl '/' lname], 'Position', pos);
    set_param([mdl '/' lname], ...
        'NominalVoltage', num2str(Vbase), ...
        'NominalFrequency', num2str(fn), ...
        'ActivePower', num2str(lP), ...
        'InductivePower', num2str(lQ), ...
        'CapacitivePower', '0');

    if lbus == 7
        wire3(bus_node.bus7, 'R', lname, 'L');
    elseif lbus == 9
        wire3(bus_node.bus9, 'R', lname, 'L');
    end
    fprintf('  %s at Bus%d: P=%.0fMW, Q=%.0fMvar\n', lname, lbus, lP/1e6, lQ/1e6);
end

% Shunt capacitive compensation
for k = 1:size(shunt_table, 1)
    sname = shunt_table{k, 1};
    sbus = shunt_table{k, 2};
    sP = shunt_table{k, 3};     % ~0
    sQ = shunt_table{k, 4};     % positive = capacitive MVAr

    pos = [500 + k*150, 1110, 560 + k*150, 1150];
    add_block('powerlib/Elements/Three-Phase Series RLC Load', ...
        [mdl '/' sname], 'Position', pos);
    set_param([mdl '/' sname], ...
        'NominalVoltage', num2str(Vbase), ...
        'NominalFrequency', num2str(fn), ...
        'ActivePower', '1000', ...
        'InductivePower', '0', ...
        'CapacitivePower', num2str(sQ));

    if sbus == 7
        wire3(bus_node.bus7, 'R', sname, 'L');
    elseif sbus == 9
        wire3(bus_node.bus9, 'R', sname, 'L');
    end
    fprintf('  %s at Bus%d: Q_cap=%.0fMvar\n', sname, sbus, sQ/1e6);
end
```

- [ ] **Step 2: Add disturbance breakers at Bus14 and Bus15**

```matlab
%% ======================================================================
%  Step 9: Disturbance Breakers (Load Step events)
%% ======================================================================
fprintf('\n=== Adding disturbance breakers ===\n');

% Breaker_1: at Bus14 (ES3 bus), initially closed, 248 MW load
% When breaker opens -> load disconnects -> generation surplus -> freq rises
% Breaker_2: at Bus15 (ES4 bus), initially open, 188 MW load
% When breaker closes -> load connects -> generation deficit -> freq drops

brk_defs = {
    'Breaker_1', 'L_10_14', 'R',  248e6, 'closed', '[100]';   % Bus14
    'Breaker_2', 'L_9_15',  'R',  188e6, 'open',   '[100]';   % Bus15
};

for k = 1:size(brk_defs, 1)
    brk_name = brk_defs{k, 1};
    bus_line = brk_defs{k, 2};
    bus_side = brk_defs{k, 3};
    trip_P = brk_defs{k, 4};
    init_state = brk_defs{k, 5};
    switch_times = brk_defs{k, 6};

    pos_brk = [800 + k*120, 1050, 860 + k*120, 1090];
    pos_load = [800 + k*120, 1110, 860 + k*120, 1150];

    add_block('powerlib/Elements/Three-Phase Breaker', ...
        [mdl '/' brk_name], 'Position', pos_brk);
    set_param([mdl '/' brk_name], ...
        'SwitchTimes', switch_times, ...
        'InitialState', init_state, ...
        'BreakerResistance', '0.01', ...
        'SnubberResistance', '1e6', ...
        'SnubberCapacitance', 'inf');

    trip_load_name = sprintf('TripLoad_%d', k);
    add_block('powerlib/Elements/Three-Phase Series RLC Load', ...
        [mdl '/' trip_load_name], 'Position', pos_load);
    set_param([mdl '/' trip_load_name], ...
        'NominalVoltage', num2str(Vbase), ...
        'NominalFrequency', num2str(fn), ...
        'ActivePower', num2str(trip_P), ...
        'InductivePower', '0', ...
        'CapacitivePower', '0');

    % Wire: Bus node -> Breaker -> TripLoad
    wire3(bus_line, bus_side, brk_name, 'L');
    wire3(brk_name, 'R', trip_load_name, 'L');

    fprintf('  %s -> %s: P=%.0fMW, init=%s\n', ...
        brk_name, trip_load_name, trip_P/1e6, init_state);
end
```

- [ ] **Step 3: Commit**

```bash
git add scenarios/kundur/simulink_models/build_powerlib_kundur.m
git commit -m "feat(simulink): add loads, shunt compensation, and disturbance breakers"
```

---

### Task 7: Solver Settings, Clock, Save, and Test Simulation

**Files:**
- Modify: `scenarios/kundur/simulink_models/build_powerlib_kundur.m`

- [ ] **Step 1: Add final sections (clock, solver, save, test)**

```matlab
%% ======================================================================
%  Step 10: Clock logger
%% ======================================================================
add_block('built-in/Clock', [mdl '/Clock'], 'Position', [20 80 50 100]);
add_block('built-in/ToWorkspace', [mdl '/Log_time'], ...
    'Position', [80 80 140 100], ...
    'VariableName', 'sim_time', 'SaveFormat', 'Timeseries');
add_line(mdl, 'Clock/1', 'Log_time/1');

%% ======================================================================
%  Step 11: Solver settings
%% ======================================================================
set_param([mdl '/powergui'], 'SimulationMode', 'Phasor', 'Frequency', num2str(fn));
set_param(mdl, ...
    'StopTime', '10.0', ...
    'SolverType', 'Fixed-step', ...
    'Solver', 'ode4', ...
    'FixedStep', '0.001');

%% ======================================================================
%  Step 12: Save model
%% ======================================================================
model_path = fullfile(model_dir, [mdl '.slx']);
save_system(mdl, model_path);
fprintf('\n=== Model saved to %s ===\n', model_path);

%% ======================================================================
%  Step 13: Test simulation (1 second)
%% ======================================================================
fprintf('\n=== Running 1-second test simulation ===\n');
try
    simOut = sim(mdl, 'StopTime', '1.0');
    fprintf('SUCCESS! 1-second simulation completed.\n');

    % Check VSG outputs
    for i = 1:n_vsg
        try
            ts = simOut.get(sprintf('omega_ES%d', i));
            fprintf('  omega_ES%d: %d samples, final=%.6f\n', i, length(ts.Data), ts.Data(end));
        catch
            fprintf('  omega_ES%d: not found\n', i);
        end
    end
    % Check gen outputs
    for i = 1:n_gen
        try
            ts = simOut.get(sprintf('omega_%s', gen_params(i).name));
            fprintf('  omega_%s: %d samples, final=%.6f\n', gen_params(i).name, length(ts.Data), ts.Data(end));
        catch
            fprintf('  omega_%s: not found\n', gen_params(i).name);
        end
    end
catch me
    fprintf('SIMULATION FAILED: %s\n', me.message);
    if ~isempty(me.cause)
        for ci = 1:length(me.cause)
            fprintf('  Cause %d: %s\n', ci, me.cause{ci}.message);
        end
    end
end

fprintf('\n=== build_powerlib_kundur done ===\n');
fprintf('Full Modified Kundur Two-Area System\n');
fprintf('Generators: G1-G3 (conventional), W1-W2 (wind), ES1-ES4 (VSG/ESS)\n');
fprintf('Buses: 16, Lines: 20, Frequency: %d Hz, Sbase: %.0f MVA\n', fn, Sbase/1e6);
```

- [ ] **Step 2: Run the full build script in MATLAB**

```matlab
cd('C:\Users\27443\Desktop\Multi-Agent  VSGs\scenarios\kundur\simulink_models')
build_powerlib_kundur
```

Expected output: All sections print success, 1-second test simulation passes, all `omega_ES*` and `omega_G*` signals logged.

- [ ] **Step 3: Commit**

```bash
git add scenarios/kundur/simulink_models/build_powerlib_kundur.m
git commit -m "feat(simulink): complete 16-bus Kundur model with test simulation"
```

---

### Task 8: Update Python Configuration

**Files:**
- Modify: `scenarios/kundur/config_simulink.py:59-93`

- [ ] **Step 1: Update config_simulink.py**

Replace the Electrical Network and Disturbance sections. The B_MATRIX is no longer needed (Simulink handles the network), but keep it for the standalone ODE env. Update disturbance bus indices and breaker mapping.

```python
# ========== Electrical Network ==========
# Full 16-bus Modified Kundur topology is in the Simulink model.
# B_MATRIX below is for the KundurStandaloneEnv (4-bus Kron-reduced ODE).
B_MATRIX = np.array([
    [0,  10,  0,  0],
    [10,  0,  2,  0],
    [0,   2,  0, 10],
    [0,   0, 10,  0],
], dtype=np.float64)

# Generator initial dispatch (p.u. on VSG base = 200 MVA)
VSG_P0 = 0.5           # 100 MW each = 400 MW total

# Load (original Kundur values, for reference)
LOAD_BUS7_MW = 967.0
LOAD_BUS9_MW = 1767.0

# Bus voltage
V_BUS = np.array([1.03, 1.01, 1.01, 1.03])
VSG_BUS_VN = 20.0      # kV

# ========== Disturbance ==========
DIST_MIN = 1.0          # p.u. (on system base)
DIST_MAX = 3.0

# ========== Breaker Mapping for Simulink ==========
# Breaker_1: Bus14 (near ES3), initially closed with 248 MW load
#   Open breaker -> load reduction -> freq rises
# Breaker_2: Bus15 (near ES4), initially open with 188 MW load
#   Close breaker -> load increase -> freq drops
BREAKER_MAP = {
    'load_decrease': {'breaker': 'Breaker_1', 'action': 'open'},
    'load_increase': {'breaker': 'Breaker_2', 'action': 'close'},
}

# ========== Test Scenarios (Section IV-C, Yang et al.) ==========
# Load Step 1: Bus14 load trip (248 MW reduction)
SCENARIO1_BREAKER = 'Breaker_1'
SCENARIO1_TIME = 0.5

# Load Step 2: Bus15 load connection (188 MW increase)
SCENARIO2_BREAKER = 'Breaker_2'
SCENARIO2_TIME = 0.5
```

- [ ] **Step 2: Commit**

```bash
git add scenarios/kundur/config_simulink.py
git commit -m "refactor(config): update Simulink config for 16-bus Kundur topology"
```

---

### Task 9: Update Simulink Environment Disturbance Method

**Files:**
- Modify: `env/simulink/kundur_simulink_env.py:714-734`

- [ ] **Step 1: Update `_apply_disturbance_backend` in `KundurSimulinkEnv`**

The current implementation maps `bus_idx < 2` to `Breaker_1` and others to `Breaker_2`. With the new topology, we need a cleaner mapping: negative magnitude → open Breaker_1 (load decrease at Bus14), positive magnitude → close Breaker_2 (load increase at Bus15).

Replace lines 714-734:

```python
    def _apply_disturbance_backend(
        self, bus_idx: Optional[int], magnitude: float
    ) -> None:
        """Apply disturbance via breaker switching in the Simulink model.

        In the full 16-bus Kundur model:
        - Breaker_1 at Bus14: initially closed (248 MW). Open to reduce load.
        - Breaker_2 at Bus15: initially open (188 MW). Close to increase load.
        """
        try:
            mdl = self.bridge.cfg.model_name
            trip_time = self._sim_time + 0.01

            if magnitude is not None and magnitude < 0:
                # Load decrease: open Breaker_1 (trip 248 MW at Bus14)
                brk = 'Breaker_1'
            else:
                # Load increase: close Breaker_2 (connect 188 MW at Bus15)
                brk = 'Breaker_2'

            self.bridge.session.call(
                "set_param",
                f"{mdl}/{brk}",
                "SwitchTimes", f"[{trip_time:.4f}]",
                nargout=0,
            )
            print(
                f"[Kundur-Simulink] Disturbance: {brk} "
                f"at t={trip_time:.2f}s (mag={magnitude})"
            )
        except Exception as exc:
            print(f"[Kundur-Simulink] Disturbance failed: {exc}")
```

- [ ] **Step 2: Commit**

```bash
git add env/simulink/kundur_simulink_env.py
git commit -m "fix(simulink): update disturbance method for 16-bus breaker topology"
```

---

### Task 10: End-to-End Validation

**Files:**
- No new files. Uses existing `scenarios/kundur/train_simulink.py` and MATLAB.

- [ ] **Step 1: Build the model in MATLAB**

Open MATLAB, run:
```matlab
cd('C:\Users\27443\Desktop\Multi-Agent  VSGs\scenarios\kundur\simulink_models')
build_powerlib_kundur
```

Verify: "SUCCESS! 1-second simulation completed" and all omega signals are near 1.0 (no large frequency deviations at steady state).

- [ ] **Step 2: Run a single training episode from Python**

```bash
cd "C:\Users\27443\Desktop\Multi-Agent  VSGs"
python -c "
from env.simulink.kundur_simulink_env import KundurSimulinkEnv
env = KundurSimulinkEnv()
obs, info = env.reset()
print('Reset OK, obs shape:', obs.shape)
# Apply disturbance
env.apply_disturbance(magnitude=-2.48)  # 248 MW load trip
# Run 5 steps with zero action
import numpy as np
for step in range(5):
    action = np.zeros((4, 2))
    obs, reward, term, trunc, info = env.step(action)
    print(f'Step {step}: freq_hz={info[\"freq_hz\"]}, reward_mean={reward.mean():.2f}')
env.close()
print('Done!')
"
```

Expected: frequencies should deviate from 50 Hz after disturbance, rewards should be negative.

- [ ] **Step 3: Verify frequency response qualitatively matches Yang2023 Fig.6**

After Load Step 1 (248 MW trip at Bus14):
- All ES frequencies should rise (positive deviation)
- ES3/ES4 (closer to Bus14) should deviate more than ES1/ES2
- Steady state should settle around +0.075 Hz (depends on H0/D0 calibration)

If frequency deviations are too large or too small, this indicates a calibration issue (H0/D0 values need tuning) — but that's a separate calibration task, not a code bug.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(simulink): complete 16-bus Modified Kundur model with end-to-end validation"
```
