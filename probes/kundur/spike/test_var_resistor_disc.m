function test_var_resistor_disc()
%TEST_VAR_RESISTOR_DISC  Test if Variable Resistor (signal-driven R)
% changes during sim under Discrete + FastRestart.
%
% This is the ACTUAL v3 LoadStep mechanism — Series RLC R was already
% replaced with Variable Resistor (build_kundur_cvs_v3.m line 135-157).
% Question: does Variable Resistor's R change mid-sim in Discrete mode?

mdl = 'varR_disc_fr_test';
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
load_system('powerlib');

% Discrete powergui
add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
set_param([mdl '/powergui'], 'SimulationMode', 'Discrete', 'SampleTime', '50e-6');
set_param(mdl, 'StopTime', '0.04', 'SolverType', 'Fixed-step', ...
    'Solver', 'FixedStepDiscrete', 'FixedStep', '50e-6', ...
    'SaveOutput', 'on', 'ReturnWorkspaceOutputs', 'on');

% DC source 230V
add_block('simulink/Sources/Constant', [mdl '/Vin'], ...
    'Position', [60 110 120 140], 'Value', '230');
add_block('powerlib/Electrical Sources/Controlled Voltage Source', ...
    [mdl '/CVS'], 'Position', [200 100 260 150]);
set_param([mdl '/CVS'], 'Source_Type', 'DC', 'Initialize', 'off', ...
    'Amplitude', '0', 'Phase', '0', 'Frequency', '0', 'Measurements', 'None');
add_line(mdl, 'Vin/1', 'CVS/1');

% R-driver: stepping signal — t<0.02s: R=1e6, t>=0.02s: R=10
add_block('simulink/Sources/Step', [mdl '/RStep'], ...
    'Position', [320 50 380 80], 'Time', '0.02', 'Before', '1e6', 'After', '10');

% Variable Resistor (signal-driven R, the actual block v3 uses)
add_block('powerlib/Elements/Variable Resistor', [mdl '/Rvar'], ...
    'Position', [320 100 370 140]);
add_line(mdl, 'RStep/1', 'Rvar/1');

add_block('powerlib/Elements/Ground', [mdl '/GND_R'], ...
    'Position', [380 130 420 160]);
add_block('powerlib/Elements/Ground', [mdl '/GND_S'], ...
    'Position', [200 170 240 200]);
add_line(mdl, 'CVS/RConn1', 'Rvar/LConn1', 'autorouting', 'smart');
add_line(mdl, 'Rvar/RConn1', 'GND_R/LConn1', 'autorouting', 'smart');
add_line(mdl, 'CVS/LConn1', 'GND_S/LConn1', 'autorouting', 'smart');

% Current measurement on the loop
add_block('powerlib/Measurements/Current Measurement', [mdl '/Imeas'], ...
    'Position', [275 100 295 130]);
delete_line(mdl, 'CVS/RConn1', 'Rvar/LConn1');
add_line(mdl, 'CVS/RConn1', 'Imeas/LConn1', 'autorouting', 'smart');
add_line(mdl, 'Imeas/RConn1', 'Rvar/LConn1', 'autorouting', 'smart');

add_block('simulink/Sinks/Out1', [mdl '/I_OUT'], ...
    'Position', [320 200 360 230]);
add_line(mdl, 'Imeas/1', 'I_OUT/1');

fprintf('RESULT: ===== Variable Resistor Discrete Test =====\n');
try
    set_param(mdl, 'SimulationCommand', 'update');
    fprintf('RESULT: compile_ok=true\n');
catch ME
    fprintf('RESULT: COMPILE FAIL: %s\n', ME.message);
    if bdIsLoaded(mdl), close_system(mdl, 0); end
    return;
end

try
    simout = sim(mdl);
    yout = simout.get('yout');
    I_data = real(yout{1}.Values.Data);
    t_data = yout{1}.Values.Time;

    % Sample I before step (t=0.01s) and after step (t=0.035s)
    [~, idx_before] = min(abs(t_data - 0.01));
    [~, idx_after]  = min(abs(t_data - 0.035));
    I_before = I_data(idx_before);
    I_after  = I_data(idx_after);
    expected_before = 230 / 1e6;  % 0.00023 A
    expected_after  = 230 / 10;   % 23 A

    fprintf('RESULT: I_before_step (R=1e6) = %.6f A, expected ~%.6f A\n', I_before, expected_before);
    fprintf('RESULT: I_after_step  (R=10)  = %.6f A, expected ~%.6f A\n', I_after, expected_after);
    ratio = abs(I_after) / max(abs(I_before), 1e-9);
    fprintf('RESULT: ratio_after_over_before = %.2f (expected ~100000 if R dynamic, ~1 if frozen)\n', ratio);
    if ratio > 1000
        fprintf('RESULT: VERDICT=VAR_R_DYNAMIC — Variable Resistor responds to signal in Discrete mid-sim. UNLOCKS LoadStep.\n');
    elseif ratio < 10
        fprintf('RESULT: VERDICT=VAR_R_FROZEN — Variable Resistor signal input ignored. Project blocker remains.\n');
    else
        fprintf('RESULT: VERDICT=AMBIGUOUS — partial response, check waveform\n');
    end
catch ME
    fprintf('RESULT: SIM FAIL: %s\n', ME.message);
end

if bdIsLoaded(mdl), close_system(mdl, 0); end
end
