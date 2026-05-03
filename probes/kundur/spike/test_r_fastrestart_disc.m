function test_r_fastrestart_disc()
%TEST_R_FASTRESTART_DISC  Test if R-block (Series RLC) responds to mid-sim
% workspace var change under Discrete + FastRestart.
%
% This is THE project blocker: in Phasor + FastRestart, R is compile-frozen
% (LoadStep doesn't propagate). Does Discrete share the same freeze?
%
% Protocol:
%   1. Build minimal Discrete model with R = workspace var R_amp
%   2. Enable FastRestart
%   3. Run sim 1 with R_amp = 1e6 (open-ish), measure I
%   4. Change R_amp = 10 (loaded), run sim 2 with FastRestart still on
%   5. Compare I_sim1 vs I_sim2: if I changes → R is dynamic, project unlocks
%      if I stays same → R is frozen even in Discrete

mdl = 'r_disc_fr_test';
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
load_system('powerlib');

% Discrete powergui
add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
set_param([mdl '/powergui'], 'SimulationMode', 'Discrete', 'SampleTime', '50e-6');
set_param(mdl, 'StopTime', '0.02', 'SolverType', 'Fixed-step', ...
    'Solver', 'FixedStepDiscrete', 'FixedStep', '50e-6', ...
    'SaveOutput', 'on', 'ReturnWorkspaceOutputs', 'on');

% Constant 230kV DC source
add_block('simulink/Sources/Constant', [mdl '/Vin'], ...
    'Position', [60 110 120 140], 'Value', '230e3');
add_block('powerlib/Electrical Sources/Controlled Voltage Source', ...
    [mdl '/CVS'], 'Position', [200 100 260 150]);
set_param([mdl '/CVS'], 'Source_Type', 'DC', 'Initialize', 'off', ...
    'Amplitude', '0', 'Phase', '0', 'Frequency', '0', 'Measurements', 'None');
add_line(mdl, 'Vin/1', 'CVS/1');

% R-load with workspace var Resistance
assignin('base', 'R_amp', 1e6);
add_block('powerlib/Elements/Series RLC Branch', [mdl '/Rload'], ...
    'Position', [320 100 370 130]);
set_param([mdl '/Rload'], 'BranchType', 'R', 'Resistance', 'R_amp');

add_block('powerlib/Elements/Ground', [mdl '/GND'], ...
    'Position', [380 130 420 160]);
add_line(mdl, 'CVS/RConn1', 'Rload/LConn1', 'autorouting', 'smart');
add_line(mdl, 'Rload/RConn1', 'GND/LConn1', 'autorouting', 'smart');

% Current measurement
add_block('powerlib/Measurements/Current Measurement', [mdl '/Imeas'], ...
    'Position', [280 100 300 130]);
% Reroute: CVS/RConn1 → Imeas/LConn1 → Rload/LConn1
delete_line(mdl, 'CVS/RConn1', 'Rload/LConn1');
add_line(mdl, 'CVS/RConn1', 'Imeas/LConn1', 'autorouting', 'smart');
add_line(mdl, 'Imeas/RConn1', 'Rload/LConn1', 'autorouting', 'smart');

add_block('simulink/Sinks/Out1', [mdl '/I_OUT'], ...
    'Position', [320 200 360 230]);
add_line(mdl, 'Imeas/1', 'I_OUT/1');

% Compile + first sim with R_amp = 1e6
fprintf('RESULT: ===== R-block FastRestart Discrete Test =====\n');
try
    set_param(mdl, 'SimulationCommand', 'update');
    fprintf('RESULT: compile_ok=true\n');
catch ME
    fprintf('RESULT: COMPILE FAIL: %s\n', ME.message);
    if bdIsLoaded(mdl), close_system(mdl, 0); end
    return;
end

% Enable FastRestart
try
    set_param(mdl, 'FastRestart', 'on');
    fprintf('RESULT: fastrestart_enabled=true\n');
catch ME
    fprintf('RESULT: FAST_RESTART_FAIL: %s\n', ME.message);
    if bdIsLoaded(mdl), close_system(mdl, 0); end
    return;
end

% Sim 1: R=1e6 (open-ish, expect I ≈ 0.23 A)
try
    assignin('base', 'R_amp', 1e6);
    simout1 = sim(mdl);
    yout1 = simout1.get('yout');
    I1_data = yout1{1}.Values.Data;
    I1_mean = mean(real(I1_data(end-100:end)));  % steady-state
    expected_I1 = 230e3 / 1e6;  % 0.23 A
    fprintf('RESULT: SIM1 R=1e6: I_meas_steady=%.6f A, expected=%.6f A\n', ...
        I1_mean, expected_I1);
catch ME
    fprintf('RESULT: SIM1 FAIL: %s\n', ME.message);
end

% Sim 2: R=10 (loaded, expect I ≈ 23000 A) — changed VIA WORKSPACE VAR
try
    assignin('base', 'R_amp', 10);
    simout2 = sim(mdl);
    yout2 = simout2.get('yout');
    I2_data = yout2{1}.Values.Data;
    I2_mean = mean(real(I2_data(end-100:end)));
    expected_I2 = 230e3 / 10;  % 23000 A
    fprintf('RESULT: SIM2 R=10: I_meas_steady=%.6f A, expected=%.6f A\n', ...
        I2_mean, expected_I2);

    % Decisive verdict
    ratio = abs(I2_mean) / max(abs(I1_mean), 1e-9);
    fprintf('RESULT: I_ratio_sim2_over_sim1=%.2f (expected ~100000 if R changed, ~1 if frozen)\n', ratio);
    if ratio > 1000
        fprintf('RESULT: VERDICT=DISCRETE_R_DYNAMIC — R-block responds to workspace var under FastRestart!\n');
    elseif ratio < 10
        fprintf('RESULT: VERDICT=DISCRETE_R_FROZEN — R compile-frozen even in Discrete mode (same as Phasor)\n');
    else
        fprintf('RESULT: VERDICT=AMBIGUOUS — partial response, investigate\n');
    end
catch ME
    fprintf('RESULT: SIM2 FAIL: %s\n', ME.message);
end

% Cleanup
try, set_param(mdl, 'FastRestart', 'off'); catch, end
if bdIsLoaded(mdl), close_system(mdl, 0); end
end
