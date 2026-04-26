%% probe_sps_minimal.m
% G0 Feasibility Probe — SPS Phasor mode baseline check.
%
% Tests: in SPS Phasor mode (SimulationMode='Phasor'), does setting
%   Three-Phase Source PhaseAngle = workspace variable (power-flow angle)
%   give Pe ≈ Pe_nominal at t≈0 with NO warmup transient?
%
% Architecture:
%   Three-Phase Source (phAng=workspace) → V-I Meas → RLC Load → GND
%   Pe estimated from logged Vabc magnitude (MATLAB post-processing,
%   no SPS PQ block required — powerlib/Measurements is empty in R2025b).
%
% PASS CRITERION: |Pe_est(1ms) / Pe_nominal - 1| < 0.05
%
% Block paths confirmed working in R2025b:
%   powerlib/powergui
%   powerlib/Electrical Sources/Three-Phase Source
%   powerlib/Measurements/Three-Phase V-I Measurement
%   powerlib/Elements/Three-Phase Parallel RLC Load

mdl = 'probe_sps_minimal';
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
load_system('powerlib');

%% --- System parameters ---
fn    = 50;           % Hz
Vbase = 230e3;        % V (line-line RMS)
Sbase = 100e6;        % VA
VSG_SN = 200e6;       % VSG rated VA
P0_pu  = 0.9;         % VSG P0 in VSG-base pu
P0_W   = P0_pu * VSG_SN;  % 180 MW

% VSG internal impedance (system base)
R_vsg_pu = 0.003 * (Sbase / VSG_SN);
X_vsg_pu = 0.30  * (Sbase / VSG_SN);
Zbase_vsg = Vbase^2 / Sbase;
R_vsg = R_vsg_pu * Zbase_vsg;
L_vsg = X_vsg_pu * Zbase_vsg / (2*pi*fn);

% Load resistance per phase (balanced resistive load, L=0 C=0)
% P0_W / 3 per phase; V_phase_rms = Vbase/sqrt(3)
V_phase_rms = Vbase / sqrt(3);
R_load_per_phase = V_phase_rms^2 / (P0_W / 3);

% Power-flow angle
P0_sys_pu = P0_W / Sbase;
delta0_rad = asin(P0_sys_pu * X_vsg_pu);
delta0_deg = delta0_rad * 180/pi;
fprintf('Computed delta0 = %.4f deg (%.4f rad)\n', delta0_deg, delta0_rad);
fprintf('V_phase_rms_nominal = %.2f kV, R_load/phase = %.4f ohm\n', ...
    V_phase_rms/1e3, R_load_per_phase);

assignin('base', 'phAng_probe', delta0_deg);

%% --- powergui: Phasor, 50 Hz ---
add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 120 60]);
set_param([mdl '/powergui'], 'SimulationMode', 'Phasor');
set_param([mdl '/powergui'], 'frequency',      num2str(fn));
set_param([mdl '/powergui'], 'Pbase',          num2str(Sbase));

%% --- Three-Phase Source ---
add_block('powerlib/Electrical Sources/Three-Phase Source', ...
    [mdl '/Src'], 'Position', [120 100 200 160]);
set_param([mdl '/Src'], 'Voltage',            num2str(Vbase));
set_param([mdl '/Src'], 'PhaseAngle',         'phAng_probe');
set_param([mdl '/Src'], 'Frequency',          num2str(fn));
set_param([mdl '/Src'], 'InternalConnection', 'Yg');
set_param([mdl '/Src'], 'NonIdealSource',     'on');
set_param([mdl '/Src'], 'SpecifyImpedance',   'on');
set_param([mdl '/Src'], 'Resistance',         num2str(R_vsg));
set_param([mdl '/Src'], 'Inductance',         num2str(L_vsg));

%% --- Three-Phase V-I Measurement ---
add_block('powerlib/Measurements/Three-Phase V-I Measurement', ...
    [mdl '/Meas'], 'Position', [250 100 330 160]);
set_param([mdl '/Meas'], 'VoltageMeasurement', 'phase-to-ground');
set_param([mdl '/Meas'], 'CurrentMeasurement', 'yes');

%% --- Three-Phase Parallel RLC Load ---
add_block('powerlib/Elements/Three-Phase Parallel RLC Load', ...
    [mdl '/Load'], 'Position', [390 100 470 160]);
set_param([mdl '/Load'], 'NominalVoltage',   num2str(Vbase));
set_param([mdl '/Load'], 'NominalFrequency', num2str(fn));
set_param([mdl '/Load'], 'ActivePower',      num2str(P0_W));
set_param([mdl '/Load'], 'InductivePower',   '0');
set_param([mdl '/Load'], 'CapacitivePower',  '0');

%% --- ToWorkspace: log Vabc and Iabc ---
add_block('simulink/Sinks/To Workspace', [mdl '/Log_V'], ...
    'Position', [370 200 430 230], ...
    'VariableName', 'Vabc_probe', 'SaveFormat', 'Timeseries');
add_block('simulink/Sinks/To Workspace', [mdl '/Log_I'], ...
    'Position', [370 240 430 270], ...
    'VariableName', 'Iabc_probe', 'SaveFormat', 'Timeseries');

%% --- Connect physical ports: Src → Meas → Load ---
add_line(mdl, 'Src/RConn1', 'Meas/LConn1', 'autorouting','smart');
add_line(mdl, 'Src/RConn2', 'Meas/LConn2', 'autorouting','smart');
add_line(mdl, 'Src/RConn3', 'Meas/LConn3', 'autorouting','smart');
add_line(mdl, 'Meas/RConn1', 'Load/LConn1', 'autorouting','smart');
add_line(mdl, 'Meas/RConn2', 'Load/LConn2', 'autorouting','smart');
add_line(mdl, 'Meas/RConn3', 'Load/LConn3', 'autorouting','smart');

%% --- Connect signal ports: Meas ports → Log ---
% Port 1 = Vabc, Port 2 = Iabc
add_line(mdl, 'Meas/1', 'Log_V/1', 'autorouting','smart');
add_line(mdl, 'Meas/2', 'Log_I/1', 'autorouting','smart');

%% --- Solver ---
set_param(mdl, 'StopTime', '0.1', 'SolverType', 'Variable-step', ...
    'Solver', 'ode23t', 'MaxStep', '0.001');

%% --- Run ---
fprintf('\nRunning probe_sps_minimal (Phasor 50Hz, 100ms)...\n');
fprintf('  phAng_probe = %.4f deg, P0_nominal = %.1f MW\n', delta0_deg, P0_W/1e6);

simOut = sim(mdl);
V_ts = simOut.get('Vabc_probe');

%% --- Post-processing: estimate Pe from Va magnitude ---
% In SPS Phasor mode, V-I Measurement Vabc output may be:
%   (a) complex phasors [Va, Vb, Vc] — take abs()
%   (b) real signals [Va_real, Va_imag, Vb_real, ...] — reshape
% Use abs() to get RMS amplitude regardless of representation.
snap_t = [0.001, 0.01, 0.05, 0.1];
fprintf('\n=== Pe_est(t) vs Pe_nominal = %.1f MW ===\n', P0_W/1e6);

passed = false;
for i = 1:numel(snap_t)
    t = snap_t(i);
    [~,k] = min(abs(V_ts.Time - t));
    V_row = V_ts.Data(k,:);   % row at time k
    % V-I Measurement in SPS Phasor mode outputs PEAK (not RMS) amplitude.
    Va_peak = abs(V_row(1));
    Va_rms  = Va_peak / sqrt(2);
    Pe_est  = 3 * Va_rms^2 / R_load_per_phase;
    ratio  = Pe_est / P0_W;
    fprintf('  t=%.3fs  |Va_peak|=%.2f kV  Va_rms=%.2f kV  Pe_est=%.3f MW  ratio=%.4f\n', ...
        t, Va_peak/1e3, Va_rms/1e3, Pe_est/1e6, ratio);
    if t <= 0.001 && abs(ratio - 1) < 0.05
        passed = true;
    end
end

if passed
    fprintf('\nRESULT: Phasor IC WORKS — Pe within 5%% nominal at t=1ms\n');
    fprintf('RESULT: probe_sps_minimal PASS\n');
else
    fprintf('\nRESULT: Phasor IC OFF — Pe not within 5%% nominal at t=1ms\n');
    fprintf('RESULT: probe_sps_minimal FAIL — check delta0 calculation or V-I format\n');
end

close_system(mdl, 0);
