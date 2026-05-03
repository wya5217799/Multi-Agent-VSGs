function test_fastrestart_scale()
%TEST_FASTRESTART_SCALE  Verify FastRestart works with multi-source v3-scale
% network in Discrete mode. Uses 4 independent {AC source + R-L line + Variable
% R load + GND} branches (no parallel-node wiring complications).

mdl = 'fr_scale_test';
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
load_system('powerlib');

add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
set_param([mdl '/powergui'], 'SimulationMode', 'Discrete', 'SampleTime', '50e-6', ...
    'SolverType', 'Tustin/Backward Euler (TBE)');
set_param(mdl, 'StopTime', '0.1', 'SolverType', 'Fixed-step', ...
    'Solver', 'FixedStepDiscrete', 'FixedStep', '50e-6', ...
    'SaveOutput', 'on', 'ReturnWorkspaceOutputs', 'on');

n_sources = 4;
% 4 independent {AC source + R-L + Variable R load + GND} chains
for i = 1:n_sources
    src = sprintf('Vac_%d', i);
    line_blk = sprintf('Line_%d', i);
    R_blk = sprintf('Rload_%d', i);
    R_drv = sprintf('RDrv_%d', i);
    gnd_s = sprintf('GND_S_%d', i);
    gnd_r = sprintf('GND_R_%d', i);
    cy = 100 + (i-1) * 200;

    add_block('powerlib/Electrical Sources/AC Voltage Source', [mdl '/' src], ...
        'Position', [60 cy-25 120 cy+25]);
    set_param([mdl '/' src], 'Amplitude', '230', 'Phase', sprintf('%g', (i-1)*30), ...
        'Frequency', '50', 'SampleTime', '0', 'Measurements', 'None');

    add_block('powerlib/Elements/Series RLC Branch', [mdl '/' line_blk], ...
        'Position', [180 cy-15 230 cy+15]);
    set_param([mdl '/' line_blk], 'BranchType', 'RL', 'Resistance', '5', 'Inductance', '0.005');

    % Variable R per source, driven by per-source R_amp_i workspace var
    var_name = sprintf('R_amp_%d', i);
    assignin('base', var_name, 100);
    add_block('simulink/Sources/Constant', [mdl '/' R_drv], ...
        'Position', [260 cy-50 320 cy-30], 'Value', var_name);
    add_block('powerlib/Elements/Variable Resistor', [mdl '/' R_blk], ...
        'Position', [290 cy-15 340 cy+25]);
    add_line(mdl, [R_drv '/1'], [R_blk '/1']);

    add_block('powerlib/Elements/Ground', [mdl '/' gnd_r], ...
        'Position', [360 cy+15 400 cy+45]);
    add_block('powerlib/Elements/Ground', [mdl '/' gnd_s], ...
        'Position', [60 cy+50 100 cy+80]);

    add_line(mdl, [src '/RConn1'], [line_blk '/LConn1'], 'autorouting', 'smart');
    add_line(mdl, [line_blk '/RConn1'], [R_blk '/LConn1'], 'autorouting', 'smart');
    add_line(mdl, [R_blk '/RConn1'], [gnd_r '/LConn1'], 'autorouting', 'smart');
    add_line(mdl, [src '/LConn1'], [gnd_s '/LConn1'], 'autorouting', 'smart');
end

n_blks = numel(find_system(mdl, 'Type', 'Block'));
fprintf('RESULT: ===== FastRestart Scale Test (n_blocks=%d, %d sources) =====\n', n_blks, n_sources);

try
    set_param(mdl, 'SimulationCommand', 'update');
    fprintf('RESULT: compile_ok=true\n');
catch ME
    fprintf('RESULT: COMPILE FAIL: %s\n', ME.message);
    if bdIsLoaded(mdl), close_system(mdl, 0); end
    return;
end

try
    set_param(mdl, 'FastRestart', 'on');
    fprintf('RESULT: fastrestart_enabled=true\n');
catch ME
    fprintf('RESULT: FAST_RESTART_FAIL: %s\n', ME.message);
end

% First sim (no FastRestart benefit yet — initial compilation)
amps_iter = [100, 50, 25, 200, 75];
wall_times = zeros(numel(amps_iter), 1);
for k = 1:numel(amps_iter)
    for i = 1:n_sources
        assignin('base', sprintf('R_amp_%d', i), amps_iter(k) * (1 + 0.1*i));
    end
    t0 = tic;
    sim(mdl);
    wall_times(k) = toc(t0);
end

for k = 1:numel(amps_iter)
    fprintf('RESULT: sim_%d wall=%.4fs (R_base=%d)\n', k, wall_times(k), amps_iter(k));
end

mean_first = wall_times(1);
mean_subseq = mean(wall_times(2:end));
fprintf('RESULT: first_sim=%.4fs, mean_subsequent=%.4fs, FastRestart_speedup=%.2fx\n', ...
    mean_first, mean_subseq, mean_first / max(mean_subseq, 1e-9));

set_param(mdl, 'FastRestart', 'off');
if bdIsLoaded(mdl), close_system(mdl, 0); end
end
