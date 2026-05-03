function test_integrator_options()
%TEST_INTEGRATOR_OPTIONS  Compare Continuous vs Discrete-Time Integrator
% in fixed-step Discrete simulation. swing-eq IntW/IntD currently uses
% Continuous Integrator — verify it works in Discrete mode and compare speed
% vs Discrete-Time Integrator (Forward/Backward Euler).

mdl = 'int_test';
patterns = {'A_continuous', 'B_disc_forward_euler', 'C_disc_backward_euler'};
results = cell(numel(patterns), 1);
sim_duration = 1.0;

for p = 1:numel(patterns)
    pname = patterns{p};
    if bdIsLoaded(mdl), close_system(mdl, 0); end
    new_system(mdl);
    load_system('powerlib');

    add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
    set_param([mdl '/powergui'], 'SimulationMode', 'Discrete', 'SampleTime', '50e-6');
    set_param(mdl, 'StopTime', sprintf('%g', sim_duration), ...
        'SolverType', 'Fixed-step', 'Solver', 'FixedStepDiscrete', ...
        'FixedStep', '50e-6', ...
        'SaveOutput', 'on', 'ReturnWorkspaceOutputs', 'on');

    % Constant input 1.0 → integrator → output (expected = t)
    add_block('simulink/Sources/Constant', [mdl '/Vin'], ...
        'Position', [60 100 120 130], 'Value', '1.0');

    compile_ok = false;
    err_msg = '';
    wall_s = NaN;
    out_final = NaN;
    try
        switch pname
            case 'A_continuous'
                add_block('simulink/Continuous/Integrator', [mdl '/Int'], ...
                    'Position', [180 95 220 135], 'InitialCondition', '0');
            case 'B_disc_forward_euler'
                add_block('simulink/Discrete/Discrete-Time Integrator', [mdl '/Int'], ...
                    'Position', [180 95 220 135], 'InitialCondition', '0', ...
                    'IntegratorMethod', 'Integration: Forward Euler', ...
                    'SampleTime', '50e-6');
            case 'C_disc_backward_euler'
                add_block('simulink/Discrete/Discrete-Time Integrator', [mdl '/Int'], ...
                    'Position', [180 95 220 135], 'InitialCondition', '0', ...
                    'IntegratorMethod', 'Integration: Backward Euler', ...
                    'SampleTime', '50e-6');
        end
        add_line(mdl, 'Vin/1', 'Int/1');
        add_block('simulink/Sinks/Out1', [mdl '/Y_OUT'], ...
            'Position', [280 95 320 135]);
        add_line(mdl, 'Int/1', 'Y_OUT/1');

        set_param(mdl, 'SimulationCommand', 'update');
        compile_ok = true;
        sim(mdl); % warm-up
        t0 = tic;
        simout = sim(mdl);
        wall_s = toc(t0);
        yout = simout.get('yout');
        y_data = yout{1}.Values.Data;
        out_final = y_data(end);
    catch ME
        err_msg = truncate(ME.message, 200);
    end

    results{p} = struct('pattern', pname, 'compile_ok', compile_ok, ...
        'wall_s', wall_s, 'out_final', out_final, 'err', err_msg);
end

if bdIsLoaded(mdl), close_system(mdl, 0); end
fprintf('RESULT: ===== Integrator Options Discrete (sim=%.2fs, expected y_final=1.0) =====\n', sim_duration);
for p = 1:numel(results)
    r = results{p};
    if r.compile_ok
        fprintf('RESULT: %s | wall=%.4fs y_final=%.6f (err=%.2e)\n', ...
            r.pattern, r.wall_s, r.out_final, abs(r.out_final - 1.0));
    else
        fprintf('RESULT: %s | FAIL: %s\n', r.pattern, r.err);
    end
end
end

function s_out = truncate(s, n)
if length(s) > n, s_out = [s(1:n) '...']; else, s_out = s; end
end
