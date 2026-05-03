function test_3phase_network_disc()
%TEST_3PHASE_NETWORK_DISC  F11 pre-flight: 3-phase network blocks in Discrete.
%
% Goal: prove that the 3-phase network blocks (Three-Phase PI Section Line +
% Three-Phase Series RLC Load) work in Discrete mode AT v3-SCALE PARAMS
% (230 kV LL, 100 km lines, 100+ MW loads). This is the most critical
% pre-flight for Phase 1.1+ network 3-phase migration.
%
% Topology (minimal closed AC loop):
%   Three-Phase Source (230kV LL, 50Hz, Y-grounded)
%     → Three-Phase PI Section Line (100 km, v3 std params)
%       → Three-Phase V-I Measurement
%         → Three-Phase Series RLC Load (100 MW, Y-grounded)
%           → ground (internal)
%
% Acceptance criteria:
%   P0.1 Compile passes (0 errors)
%   P0.2 Sim runs to completion (1s sim, no instability)
%   P0.3 Steady-state I_rms ≈ V_LL / (sqrt(3) × |Z_load|) within ±10%
%        For 100 MW load at 230 kV LL: I_rms ≈ 251 A per phase
%   P0.4 Steady-state P_meas ≈ 100 MW within ±10%
%
% Failure modes captured:
%   - FAIL_BUILD: block placement / wiring error
%   - FAIL_COMPILE: domain mismatch / signal port issue
%   - FAIL_DRIFT: I_rms or P way off → block params wrong or topology bug
%   - FAIL_SLOW: sim wall > 5× real-time → speed concern for v3-scale

mdl = 'test_3phase_net';
out_dir = fileparts(mfilename('fullpath'));

% ---- Parameters ----
fn = 50;
Vbase = 230e3;       % LL RMS
P_load = 100e6;      % 100 MW

% v3 standard line params (per-km)
R_std_perkm = 0.053;    % Ω/km positive sequence
L_std_perkm = 1.41e-3;  % H/km positive sequence
C_std_perkm = 0.009e-6; % F/km positive sequence
line_len_km = 100;

% Convert to 3-phase block format [R1 R0]:
% Without zero-sequence data, use [R1, 3*R1] as standard approximation
R_3p = [R_std_perkm,       3 * R_std_perkm];
L_3p = [L_std_perkm,       3 * L_std_perkm];
C_3p = [C_std_perkm, 0.6 * C_std_perkm];

% Expected I_rms per phase (loaded line with small line drop)
% Iphase = P_3ph / (sqrt(3) * V_LL)
expected_I_rms = P_load / (sqrt(3) * Vbase);
fprintf('RESULT: ===== F11: 3-phase Network in Discrete =====\n');
fprintf('RESULT: Vbase=%g LL, P_load=%g W, expected_I=%.1f A\n', ...
    Vbase, P_load, expected_I_rms);

% ---- Reset ----
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
load_system('powerlib');
load_system('sps_lib');

% ---- powergui Discrete 50us ----
add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
set_param([mdl '/powergui'], 'SimulationMode', 'Discrete', 'SampleTime', '50e-6');
set_param(mdl, 'StopTime', '0.5', 'SolverType', 'Fixed-step', ...
    'Solver', 'FixedStepAuto', 'FixedStep', '50e-6');

% ---- Three-Phase Source (Y-grounded, 230 kV LL, 50 Hz, ideal) ----
add_block('sps_lib/Sources/Three-Phase Source', [mdl '/Src'], ...
    'Position', [200 100 280 200]);
set_param([mdl '/Src'], ...
    'InternalConnection', 'Yg', ...
    'Voltage', num2str(Vbase), ...
    'PhaseAngle', '0', ...
    'Frequency', num2str(fn), ...
    'NonIdealSource', 'on', ...
    'SpecifyImpedance', 'on', ...
    'ShortCircuitLevel', '10000e6', ...   % 10 GVA (very stiff but not ideal)
    'BaseVoltage', num2str(Vbase), ...
    'XRratio', '7');

% ---- Three-Phase PI Section Line (100 km, v3 std params) ----
pi_path = sprintf('sps_lib/Power Grid Elements/Three-Phase\nPI Section Line');
add_block(pi_path, [mdl '/Line'], 'Position', [350 100 430 200]);
set_param([mdl '/Line'], ...
    'Length', num2str(line_len_km), ...
    'Frequency', num2str(fn), ...
    'Resistances', mat2str(R_3p), ...
    'Inductances', mat2str(L_3p), ...
    'Capacitances', mat2str(C_3p));

add_line(mdl, 'Src/RConn1', 'Line/LConn1', 'autorouting', 'smart');
add_line(mdl, 'Src/RConn2', 'Line/LConn2', 'autorouting', 'smart');
add_line(mdl, 'Src/RConn3', 'Line/LConn3', 'autorouting', 'smart');

% ---- Three-Phase V-I Measurement ----
add_block('powerlib/Measurements/Three-Phase V-I Measurement', ...
    [mdl '/VImeas'], 'Position', [500 100 580 200]);
set_param([mdl '/VImeas'], 'VoltageMeasurement', 'phase-to-ground', ...
    'CurrentMeasurement', 'yes', ...
    'SetLabelV', 'on', 'LabelV', 'Vabc_load', ...
    'SetLabelI', 'on', 'LabelI', 'Iabc_load');

add_line(mdl, 'Line/RConn1', 'VImeas/LConn1', 'autorouting', 'smart');
add_line(mdl, 'Line/RConn2', 'VImeas/LConn2', 'autorouting', 'smart');
add_line(mdl, 'Line/RConn3', 'VImeas/LConn3', 'autorouting', 'smart');

% ---- Three-Phase Series RLC Load (100 MW, Y-grounded) ----
load_path = sprintf('sps_lib/Passives/Three-Phase\nSeries RLC Load');
add_block(load_path, [mdl '/Load'], 'Position', [620 100 700 200]);
set_param([mdl '/Load'], ...
    'Configuration', 'Y (grounded)', ...
    'NominalVoltage', num2str(Vbase), ...
    'NominalFrequency', num2str(fn), ...
    'ActivePower', num2str(P_load), ...
    'InductivePower', '0', ...
    'CapacitivePower', '0');

add_line(mdl, 'VImeas/RConn1', 'Load/LConn1', 'autorouting', 'smart');
add_line(mdl, 'VImeas/RConn2', 'Load/LConn2', 'autorouting', 'smart');
add_line(mdl, 'VImeas/RConn3', 'Load/LConn3', 'autorouting', 'smart');

% ---- Pe / I logging via broadcast tags ----
add_block('built-in/From', [mdl '/FromV'], 'Position', [500 280 540 300], ...
    'GotoTag', 'Vabc_load');
add_block('built-in/From', [mdl '/FromI'], 'Position', [500 320 540 340], ...
    'GotoTag', 'Iabc_load');

add_block('built-in/Product', [mdl '/Pinst'], ...
    'Position', [580 290 610 320], 'Inputs', '2');
add_line(mdl, 'FromV/1', 'Pinst/1');
add_line(mdl, 'FromI/1', 'Pinst/2');

add_block('built-in/Sum', [mdl '/Psum'], ...
    'Position', [630 290 660 310], 'IconShape', 'rectangular', ...
    'Inputs', '+', 'CollapseMode', 'All dimensions', 'CollapseDim', '1');
add_line(mdl, 'Pinst/1', 'Psum/1');

add_block('simulink/Sinks/To Workspace', [mdl '/P_log'], ...
    'Position', [680 290 720 310], 'VariableName', 'P_inst', ...
    'SaveFormat', 'Timeseries', 'MaxDataPoints', 'inf');
add_line(mdl, 'Psum/1', 'P_log/1');

add_block('simulink/Sinks/To Workspace', [mdl '/I_log'], ...
    'Position', [550 360 590 380], 'VariableName', 'Iabc_ts', ...
    'SaveFormat', 'Timeseries', 'MaxDataPoints', 'inf');
add_line(mdl, 'FromI/1', 'I_log/1');

add_block('simulink/Sinks/To Workspace', [mdl '/V_log'], ...
    'Position', [550 400 590 420], 'VariableName', 'Vabc_ts', ...
    'SaveFormat', 'Timeseries', 'MaxDataPoints', 'inf');
add_line(mdl, 'FromV/1', 'V_log/1');

% ---- Save + compile + sim ----
out_slx = fullfile(out_dir, [mdl '.slx']);
save_system(mdl, out_slx);

% Compile diagnostic
compile_ok = false;
try
    set_param(mdl, 'SimulationCommand', 'update');
    compile_ok = true;
    fprintf('RESULT: P0.1 compile PASS\n');
catch ME
    fprintf('RESULT: P0.1 compile FAIL: %s\n', ME.message);
    fprintf('RESULT: VERDICT=FAIL_COMPILE\n');
    return;
end

% Run sim
t0 = tic;
sim_ok = false;
try
    out = sim(mdl, 'StopTime', '0.5');
    sim_ok = true;
    elapsed = toc(t0);
    fprintf('RESULT: P0.2 sim PASS, wall=%.2fs (0.5s sim)\n', elapsed);
catch ME
    fprintf('RESULT: P0.2 sim FAIL: %s\n', ME.message);
    fprintf('RESULT: VERDICT=FAIL_SIM\n');
    return;
end

% Read traces
P_ts = out.get('P_inst');
I_ts = out.get('Iabc_ts');
V_ts = out.get('Vabc_ts');

if isempty(P_ts) || isempty(I_ts)
    fprintf('RESULT: VERDICT=FAIL — no logged data\n');
    return;
end

% Steady state: t > 0.2s (after transient)
t = P_ts.Time;
mask = t > 0.2;
Pd = P_ts.Data(mask);
Id = I_ts.Data(mask, :);    % (n, 3) for 3 phases
Vd = V_ts.Data(mask, :);

% RMS over the steady-state window
% I_rms per phase over window
I_rms_per_phase = sqrt(mean(Id.^2, 1));   % (1, 3)
V_rms_per_phase = sqrt(mean(Vd.^2, 1));   % (1, 3)
fprintf('RESULT: I_rms per phase = [%.1f, %.1f, %.1f] A\n', ...
    I_rms_per_phase(1), I_rms_per_phase(2), I_rms_per_phase(3));
fprintf('RESULT: V_rms per phase = [%.1f, %.1f, %.1f] V\n', ...
    V_rms_per_phase(1), V_rms_per_phase(2), V_rms_per_phase(3));

% Mean instantaneous P (averaged over window)
P_mean = mean(Pd);
fprintf('RESULT: P_mean (instantaneous V·I sum) = %.3e W (target=%.3e)\n', ...
    P_mean, P_load);

% P0.3 + P0.4 check
mean_I = mean(I_rms_per_phase);
I_err = abs(mean_I - expected_I_rms) / expected_I_rms;
P_err = abs(P_mean - P_load) / P_load;

fprintf('RESULT: I error vs expected = %.1f%%\n', I_err * 100);
fprintf('RESULT: P error vs target = %.1f%%\n', P_err * 100);

p3_pass = I_err < 0.10;   % within 10%
p4_pass = P_err < 0.10;
p_speed_pass = elapsed < 2.5;   % 0.5s sim < 2.5s wall = 5x slower than RT

fprintf('RESULT: P0.3 I match: %s\n', ternary(p3_pass, 'PASS', 'FAIL'));
fprintf('RESULT: P0.4 P match: %s\n', ternary(p4_pass, 'PASS', 'FAIL'));
fprintf('RESULT: speed: %s (target < 2.5s wall for 0.5s sim)\n', ...
    ternary(p_speed_pass, 'PASS', 'FAIL'));

if p3_pass && p4_pass
    fprintf('RESULT: VERDICT=PASS — 3-phase network blocks work at v3-scale\n');
else
    fprintf('RESULT: VERDICT=FAIL — diagnose: I_err=%.1f%%, P_err=%.1f%%\n', ...
        I_err*100, P_err*100);
end

end

function s = ternary(cond, a, b)
if cond, s = a; else, s = b; end
end
