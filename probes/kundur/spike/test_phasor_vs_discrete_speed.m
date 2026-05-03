function test_phasor_vs_discrete_speed()
%TEST_PHASOR_VS_DISCRETE_SPEED  Compare wall-clock for IDENTICAL minimal
% AC network in Phasor vs Discrete modes. Fundamental input to RL feasibility.
%
% Network: 50Hz AC source 230V → R-L line (100Ω, 0.1H) → R-load 50Ω → GND
% Sim: 1.0 second
%
% Reports: wall-clock × mode + relative slowdown factor

mdl = 'speed_compare';
modes = {'Phasor', 'Discrete'};
sim_duration = 1.0;
results = struct('mode', {}, 'wall_s', {}, 'compile_ok', {}, 'err', {});

for m = 1:numel(modes)
    mode = modes{m};
    if bdIsLoaded(mdl), close_system(mdl, 0); end
    new_system(mdl);
    load_system('powerlib');

    add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
    if strcmp(mode, 'Phasor')
        set_param([mdl '/powergui'], 'SimulationMode', 'Phasor', 'frequency', '50');
        set_param(mdl, 'StopTime', sprintf('%g', sim_duration), ...
            'SolverType', 'Variable-step', 'Solver', 'ode23t', 'MaxStep', '0.005', ...
            'SaveOutput', 'on', 'ReturnWorkspaceOutputs', 'on');
    else
        set_param([mdl '/powergui'], 'SimulationMode', 'Discrete', ...
            'SampleTime', '50e-6', 'SolverType', 'Tustin/Backward Euler (TBE)');
        set_param(mdl, 'StopTime', sprintf('%g', sim_duration), ...
            'SolverType', 'Fixed-step', 'Solver', 'FixedStepDiscrete', ...
            'FixedStep', '50e-6', ...
            'SaveOutput', 'on', 'ReturnWorkspaceOutputs', 'on');
    end

    % AC source 230V, 50Hz — explicit frequency setting
    add_block('powerlib/Electrical Sources/AC Voltage Source', [mdl '/Vac'], ...
        'Position', [60 100 120 150]);
    set_param([mdl '/Vac'], 'Amplitude', '230', 'Phase', '0', ...
        'Frequency', '50', 'SampleTime', '0', 'Measurements', 'None');

    % Series R-L (line model: R=10Ω, L=0.01H)
    add_block('powerlib/Elements/Series RLC Branch', [mdl '/Line'], ...
        'Position', [180 100 230 130]);
    set_param([mdl '/Line'], 'BranchType', 'RL', ...
        'Resistance', '10', 'Inductance', '0.01');

    % R load 50Ω
    add_block('powerlib/Elements/Series RLC Branch', [mdl '/Rload'], ...
        'Position', [280 100 330 130]);
    set_param([mdl '/Rload'], 'BranchType', 'R', 'Resistance', '50');

    add_block('powerlib/Elements/Ground', [mdl '/GND_l'], ...
        'Position', [340 130 380 160]);
    add_block('powerlib/Elements/Ground', [mdl '/GND_r'], ...
        'Position', [60 160 100 190]);

    add_line(mdl, 'Vac/RConn1', 'Line/LConn1', 'autorouting', 'smart');
    add_line(mdl, 'Line/RConn1', 'Rload/LConn1', 'autorouting', 'smart');
    add_line(mdl, 'Rload/RConn1', 'GND_l/LConn1', 'autorouting', 'smart');
    add_line(mdl, 'Vac/LConn1', 'GND_r/LConn1', 'autorouting', 'smart');

    add_block('powerlib/Measurements/Current Measurement', [mdl '/Imeas'], ...
        'Position', [240 200 260 230]);
    add_block('simulink/Sinks/Out1', [mdl '/I_OUT'], ...
        'Position', [300 200 340 230]);
    add_line(mdl, 'Imeas/1', 'I_OUT/1');

    compile_ok = false;
    err_msg = '';
    wall_s = NaN;
    try
        set_param(mdl, 'SimulationCommand', 'update');
        compile_ok = true;
        % Warm-up sim (excluded from timing)
        sim(mdl);
        % Timed sim
        t0 = tic;
        sim(mdl);
        wall_s = toc(t0);
    catch ME
        err_msg = sprintf('%s: %s', mode, truncate(ME.message, 200));
    end

    results(m).mode = mode;
    results(m).wall_s = wall_s;
    results(m).compile_ok = compile_ok;
    results(m).err = err_msg;
end

if bdIsLoaded(mdl), close_system(mdl, 0); end
fprintf('RESULT: ===== Phasor vs Discrete Speed (sim_duration=%.2fs) =====\n', sim_duration);
phasor_wall = NaN; discrete_wall = NaN;
for k = 1:numel(results)
    r = results(k);
    if r.compile_ok
        fprintf('RESULT: mode=%-10s wall=%.4fs\n', r.mode, r.wall_s);
        if strcmp(r.mode, 'Phasor'), phasor_wall = r.wall_s; end
        if strcmp(r.mode, 'Discrete'), discrete_wall = r.wall_s; end
    else
        fprintf('RESULT: mode=%-10s FAIL: %s\n', r.mode, r.err);
    end
end
if ~isnan(phasor_wall) && ~isnan(discrete_wall)
    slowdown = discrete_wall / phasor_wall;
    fprintf('RESULT: Discrete/Phasor speed ratio = %.2fx (Discrete is %.1fx slower)\n', slowdown, slowdown);
end
end

function s_out = truncate(s, n)
if length(s) > n, s_out = [s(1:n) '...']; else, s_out = s; end
end
