%% probe_sps_minimal.m
% Phase 0 Task 0.2 — SPS Phasor mode feasibility probe.
%
% Tests: in SPS Phasor mode (SimulationMode='Phasor'), does setting
%   Three-Phase Source PhaseAngle = workspace variable (power-flow angle)
%   give Pe ≈ Pe_nominal at t=0 with NO warmup transient?
%
% Architecture per NE39bus_v2 pattern:
%   Three-Phase Source (phAng=workspace) → V-I Meas → RLC Load → GND
%   Active & Reactive Power block reads V,I → log Pe
%
% Parameters: 100 MVA base, 230 kV, 50 Hz, single VSG (ES1-like)

mdl = 'probe_sps_minimal';
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
load_system('powerlib');

%% --- System parameters ---
fn    = 50;           % Hz
Vbase = 230e3;        % V (line-line RMS)
Sbase = 100e6;        % VA
VSG_SN = 200e6;       % VSG rated VA
P0_pu  = 0.9;         % VSG P0 in VSG-base pu → P0_W = P0_pu * VSG_SN
P0_W   = P0_pu * VSG_SN;  % 180 MW

% VSG internal impedance (same as build_powerlib_kundur.m)
R_vsg_pu = 0.003 * (Sbase / VSG_SN);
X_vsg_pu = 0.30  * (Sbase / VSG_SN);
Zbase_vsg = Vbase^2 / Sbase;
R_vsg = R_vsg_pu * Zbase_vsg;
L_vsg = X_vsg_pu * Zbase_vsg / (2*pi*fn);

% Power-flow angle: delta0 ≈ arcsin(P0_sys * X_vsg_sys / V^2)
% P0_sys = P0_W / Sbase * (Sbase/Sbase) = P0_W/Sbase pu on Sbase
% X_vsg_sys = 0.15 pu → X_vsg_ohm = 0.15 * Zbase_vsg
P0_sys_pu = P0_W / Sbase;
X_vsg_sys = X_vsg_pu * Zbase_vsg;   % ohm
% Simple SMIB approx: delta0 = arcsin(P0_sys * X / V_pu^2) in radians
delta0_rad  = asin(P0_sys_pu * X_vsg_pu);  % pu impedance, pu voltages → rad
delta0_deg  = delta0_rad * 180/pi;
fprintf('Computed delta0 = %.4f deg (%.4f rad)\n', delta0_deg, delta0_rad);

% Set workspace phAng for Three-Phase Source
assignin('base', 'phAng_probe', delta0_deg);

%% --- powergui: Phasor, 50 Hz ---
add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 120 60]);
set_param([mdl '/powergui'], 'SimulationMode', 'Phasor');
set_param([mdl '/powergui'], 'frequency',      num2str(fn));
set_param([mdl '/powergui'], 'Pbase',          num2str(Sbase));

%% --- Three-Phase Source (NE39 pattern: PhaseAngle = workspace var) ---
add_block('powerlib/Electrical Sources/Three-Phase Source', ...
    [mdl '/Src'], 'Position', [120 100 200 160]);
set_param([mdl '/Src'], 'Voltage',          num2str(Vbase));
set_param([mdl '/Src'], 'PhaseAngle',       'phAng_probe');
set_param([mdl '/Src'], 'Frequency',        num2str(fn));
set_param([mdl '/Src'], 'InternalConnection','Yg');
set_param([mdl '/Src'], 'NonIdealSource',   'on');
set_param([mdl '/Src'], 'SpecifyImpedance', 'on');
set_param([mdl '/Src'], 'Resistance',       num2str(R_vsg));
set_param([mdl '/Src'], 'Inductance',       num2str(L_vsg));

%% --- Three-Phase V-I Measurement ---
add_block('powerlib/Measurements/Three-Phase V-I Measurement', ...
    [mdl '/Meas'], 'Position', [250 100 330 160]);
set_param([mdl '/Meas'], 'VoltageMeasurement', 'phase-to-ground');
set_param([mdl '/Meas'], 'CurrentMeasurement', 'yes');

%% --- Three-Phase Parallel RLC Load (as bus/load) ---
add_block('powerlib/Elements/Three-Phase Parallel RLC Load', ...
    [mdl '/Load'], 'Position', [390 100 470 160]);
set_param([mdl '/Load'], 'NominalVoltage',   num2str(Vbase));
set_param([mdl '/Load'], 'NominalFrequency', num2str(fn));
set_param([mdl '/Load'], 'ActivePower',      num2str(P0_W));
set_param([mdl '/Load'], 'InductivePower',   '0');
set_param([mdl '/Load'], 'CapacitivePower',  '0');

%% --- Active & Reactive Power block ---
add_block('powerlib/Measurements/Three-Phase Instantaneous Active & Reactive Power', ...
    [mdl '/PQ'], 'Position', [250 220 370 270]);

%% --- ToWorkspace: log Pe ---
add_block('simulink/Sinks/To Workspace', [mdl '/Log_P'], ...
    'Position', [410 220 470 260], ...
    'VariableName', 'Pe_probe', 'SaveFormat', 'Timeseries');
add_block('simulink/Sinks/To Workspace', [mdl '/Log_Q'], ...
    'Position', [410 275 470 315], ...
    'VariableName', 'Qe_probe', 'SaveFormat', 'Timeseries');

%% --- Connect physical ports: Src → Meas → Load ---
add_line(mdl, 'Src/RConn1', 'Meas/LConn1', 'autorouting','smart');
add_line(mdl, 'Src/RConn2', 'Meas/LConn2', 'autorouting','smart');
add_line(mdl, 'Src/RConn3', 'Meas/LConn3', 'autorouting','smart');
add_line(mdl, 'Meas/RConn1', 'Load/LConn1', 'autorouting','smart');
add_line(mdl, 'Meas/RConn2', 'Load/LConn2', 'autorouting','smart');
add_line(mdl, 'Meas/RConn3', 'Load/LConn3', 'autorouting','smart');

%% --- Connect signal ports: Meas → PQ → Log ---
add_line(mdl, 'Meas/1', 'PQ/1', 'autorouting','smart');  % Vabc
add_line(mdl, 'Meas/2', 'PQ/2', 'autorouting','smart');  % Iabc
add_line(mdl, 'PQ/1',   'Log_P/1', 'autorouting','smart');
add_line(mdl, 'PQ/2',   'Log_Q/1', 'autorouting','smart');

%% --- Solver ---
set_param(mdl, 'StopTime', '0.1', 'SolverType', 'Variable-step', ...
    'Solver', 'ode23t', 'MaxStep', '0.001');

%% --- Run ---
fprintf('\nRunning probe_sps_minimal (Phasor 50Hz, 100ms)...\n');
fprintf('  phAng_probe = %.4f deg, P0_nominal = %.1f MW\n', delta0_deg, P0_W/1e6);

simOut = sim(mdl);
P_ts = simOut.get('Pe_probe');

%% --- Evaluate ---
snap_t = [0.001, 0.01, 0.05, 0.1];
fprintf('\n=== Pe(t) vs Pe_nominal = %.1f MW ===\n', P0_W/1e6);
for t = snap_t
    [~,k] = min(abs(P_ts.Time - t));
    ratio = P_ts.Data(k) / P0_W;
    fprintf('  t=%.3fs  Pe=%.3f MW  ratio=%.4f\n', P_ts.Time(k), P_ts.Data(k)/1e6, ratio);
end

ratio_1ms = P_ts.Data(find(P_ts.Time >= 0.001, 1)) / P0_W;
if abs(ratio_1ms - 1) < 0.05
    fprintf('\nRESULT: Phasor IC WORKS — Pe=%.1f%% nominal at t=1ms\n', ratio_1ms*100);
    fprintf('RESULT: probe_sps_minimal PASS\n');
else
    fprintf('\nRESULT: Phasor IC OFF — Pe=%.1f%% nominal at t=1ms\n', ratio_1ms*100);
    fprintf('RESULT: probe_sps_minimal FAIL — check delta0 calculation\n');
end

close_system(mdl, 0);
