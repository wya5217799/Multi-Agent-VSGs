function test_solver_speed_disc()
%TEST_SOLVER_SPEED_DISC  Compare wall-clock for variants of Discrete solver
% on identical small RLC network.
%
% Sweeps powergui solver (Tustin / Backward Euler / Trapezoidal) ×
% sample time (25e-6, 50e-6, 100e-6, 200e-6).
%
% Reports wall-clock for fixed sim duration + steady-state error vs analytical.

mdl = 'speed_disc_test';
solvers = {'Tustin/Backward Euler (TBE)', 'Tustin', 'Backward Euler'};
sample_times = [25e-6, 50e-6, 100e-6, 200e-6];
sim_duration = 0.1;
results = struct('solver', {}, 'sample_time', {}, 'wall_s', {}, ...
    'I_steady', {}, 'compile_ok', {}, 'err', {});

idx = 0;
for s = 1:numel(solvers)
    sol = solvers{s};
    for st = 1:numel(sample_times)
        ts = sample_times(st);
        idx = idx + 1;

        if bdIsLoaded(mdl), close_system(mdl, 0); end
        new_system(mdl);
        load_system('powerlib');

        add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
        set_param([mdl '/powergui'], 'SimulationMode', 'Discrete', ...
            'SampleTime', sprintf('%g', ts), 'SolverType', sol);
        set_param(mdl, 'StopTime', sprintf('%g', sim_duration), ...
            'SolverType', 'Fixed-step', 'Solver', 'FixedStepDiscrete', ...
            'FixedStep', sprintf('%g', ts), ...
            'SaveOutput', 'on', 'ReturnWorkspaceOutputs', 'on');

        add_block('simulink/Sources/Constant', [mdl '/Vin'], ...
            'Position', [60 110 120 140], 'Value', '230');
        add_block('powerlib/Electrical Sources/Controlled Voltage Source', ...
            [mdl '/CVS'], 'Position', [200 100 260 150]);
        set_param([mdl '/CVS'], 'Source_Type', 'DC', 'Initialize', 'off', ...
            'Amplitude', '0', 'Phase', '0', 'Frequency', '0', 'Measurements', 'None');
        add_line(mdl, 'Vin/1', 'CVS/1');

        add_block('powerlib/Elements/Series RLC Branch', [mdl '/Rload'], ...
            'Position', [320 100 370 130]);
        set_param([mdl '/Rload'], 'BranchType', 'R', 'Resistance', '10');
        add_block('powerlib/Elements/Ground', [mdl '/GND'], ...
            'Position', [380 130 420 160]);
        add_line(mdl, 'CVS/RConn1', 'Rload/LConn1', 'autorouting', 'smart');
        add_line(mdl, 'Rload/RConn1', 'GND/LConn1', 'autorouting', 'smart');
        add_line(mdl, 'CVS/LConn1', 'GND/LConn1', 'autorouting', 'smart');

        add_block('powerlib/Measurements/Current Measurement', [mdl '/Imeas'], ...
            'Position', [275 100 295 130]);
        delete_line(mdl, 'CVS/RConn1', 'Rload/LConn1');
        add_line(mdl, 'CVS/RConn1', 'Imeas/LConn1', 'autorouting', 'smart');
        add_line(mdl, 'Imeas/RConn1', 'Rload/LConn1', 'autorouting', 'smart');

        add_block('simulink/Sinks/Out1', [mdl '/I_OUT'], ...
            'Position', [320 200 360 230]);
        add_line(mdl, 'Imeas/1', 'I_OUT/1');

        compile_ok = false;
        err_msg = '';
        try
            set_param(mdl, 'SimulationCommand', 'update');
            compile_ok = true;
        catch ME
            err_msg = sprintf('COMPILE: %s', truncate(ME.message, 150));
        end

        I_steady = NaN;
        wall_s = NaN;
        if compile_ok
            try
                t0 = tic;
                simout = sim(mdl);
                wall_s = toc(t0);
                yout = simout.get('yout');
                I_data = real(yout{1}.Values.Data);
                I_steady = mean(I_data(end-10:end));
            catch ME
                err_msg = sprintf('SIM: %s', truncate(ME.message, 150));
            end
        end

        results(idx).solver = sol;
        results(idx).sample_time = ts;
        results(idx).wall_s = wall_s;
        results(idx).I_steady = I_steady;
        results(idx).compile_ok = compile_ok;
        results(idx).err = err_msg;
    end
end

if bdIsLoaded(mdl), close_system(mdl, 0); end
fprintf('RESULT: ===== Solver Speed Sweep Discrete (sim_duration=%.3fs, expected I=23.0A) =====\n', sim_duration);
for k = 1:numel(results)
    r = results(k);
    if r.compile_ok && ~isnan(r.wall_s)
        fprintf('RESULT: solver=%-15s ts=%.0fμs wall=%.4fs I=%.4fA\n', ...
            r.solver, r.sample_time*1e6, r.wall_s, r.I_steady);
    else
        fprintf('RESULT: solver=%-15s ts=%.0fμs FAIL: %s\n', ...
            r.solver, r.sample_time*1e6, r.err);
    end
end
end

function s_out = truncate(s, n)
if length(s) > n, s_out = [s(1:n) '...']; else, s_out = s; end
end
