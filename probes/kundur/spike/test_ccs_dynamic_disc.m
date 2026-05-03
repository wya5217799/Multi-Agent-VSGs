function test_ccs_dynamic_disc()
%TEST_CCS_DYNAMIC_DISC  Test if CCS responds to signal input mid-sim under
% Discrete + FastRestart. Uses simple closed-loop topology (CCS feeding R).
%
% Topology:  CCS(signal=Step 0→5A) → Rload(10Ω) → CCS_return
% Expected V across Rload: before step = 0, after step = 50V (I·R = 5·10)

mdl = 'ccs_disc_fr_test';
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
load_system('powerlib');

add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
set_param([mdl '/powergui'], 'SimulationMode', 'Discrete', 'SampleTime', '50e-6');
set_param(mdl, 'StopTime', '0.05', 'SolverType', 'Fixed-step', ...
    'Solver', 'FixedStepDiscrete', 'FixedStep', '50e-6', ...
    'SaveOutput', 'on', 'ReturnWorkspaceOutputs', 'on');

% Step input 0 → 5A at t=0.025s
add_block('simulink/Sources/Step', [mdl '/IStep'], ...
    'Position', [60 80 120 110], 'Time', '0.025', 'Before', '0', 'After', '5');

% Controlled Current Source
add_block('powerlib/Electrical Sources/Controlled Current Source', ...
    [mdl '/CCS'], 'Position', [200 80 260 130]);
set_param([mdl '/CCS'], 'Source_Type', 'DC', 'Initialize', 'off', ...
    'Amplitude', '0', 'Phase', '0', 'Frequency', '0', 'Measurements', 'None');
add_line(mdl, 'IStep/1', 'CCS/1');

% Rload 10 Ω in series (CCS forces current through it)
add_block('powerlib/Elements/Series RLC Branch', [mdl '/Rload'], ...
    'Position', [320 80 370 110]);
set_param([mdl '/Rload'], 'BranchType', 'R', 'Resistance', '10');

% Voltage measurement across Rload
add_block('powerlib/Measurements/Voltage Measurement', [mdl '/Vmeas'], ...
    'Position', [320 160 380 190]);

% Single GND for return (one terminal of Rload to GND)
add_block('powerlib/Elements/Ground', [mdl '/GND_R'], ...
    'Position', [400 80 440 110]);
add_block('powerlib/Elements/Ground', [mdl '/GND_C'], ...
    'Position', [200 160 240 190]);

% Wiring: CCS+ → Rload → GND_R; CCS- → GND_C; Vmeas across Rload
add_line(mdl, 'CCS/RConn1', 'Rload/LConn1', 'autorouting', 'smart');
add_line(mdl, 'Rload/RConn1', 'GND_R/LConn1', 'autorouting', 'smart');
add_line(mdl, 'CCS/LConn1', 'GND_C/LConn1', 'autorouting', 'smart');
add_line(mdl, 'Rload/LConn1', 'Vmeas/LConn1', 'autorouting', 'smart');
add_line(mdl, 'Rload/RConn1', 'Vmeas/LConn2', 'autorouting', 'smart');

add_block('simulink/Sinks/Out1', [mdl '/V_OUT'], ...
    'Position', [410 160 450 190]);
add_line(mdl, 'Vmeas/1', 'V_OUT/1');

fprintf('RESULT: ===== CCS Dynamic Discrete Test =====\n');
try
    set_param(mdl, 'SimulationCommand', 'update');
    set_param(mdl, 'FastRestart', 'on');
    simout = sim(mdl);
    yout = simout.get('yout');
    V_data = real(yout{1}.Values.Data);
    t_data = yout{1}.Values.Time;

    [~, idx_before] = min(abs(t_data - 0.015));
    [~, idx_after]  = min(abs(t_data - 0.045));
    V_before = V_data(idx_before);
    V_after  = V_data(idx_after);

    fprintf('RESULT: V_before_step (CCS=0)  = %.4f V, expected ~0.0 V\n', V_before);
    fprintf('RESULT: V_after_step  (CCS=5A) = %.4f V, expected ~50.0 V (5A * 10Ω)\n', V_after);
    delta = V_after - V_before;
    if abs(delta - 50.0) < 5
        fprintf('RESULT: VERDICT=CCS_DYNAMIC — CCS signal change propagates correctly. UNLOCKS Bus 7/9 LoadStep alternative.\n');
    elseif abs(delta) < 5
        fprintf('RESULT: VERDICT=CCS_FROZEN — CCS signal input ignored.\n');
    else
        fprintf('RESULT: VERDICT=CCS_PARTIAL delta=%.4f V (expected 50.0)\n', delta);
    end
    set_param(mdl, 'FastRestart', 'off');
catch ME
    fprintf('RESULT: FAIL: %s\n', ME.message);
end

if bdIsLoaded(mdl), close_system(mdl, 0); end
end
