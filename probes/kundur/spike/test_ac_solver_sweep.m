function test_ac_solver_sweep()
%TEST_AC_SOLVER_SWEEP  AC dynamics speed sweep across powergui Discrete solvers
% × sample times. Realistic workload (RLC ladder + AC source, 1s sim).

mdl = 'ac_speed_test';
solvers = {'Tustin/Backward Euler (TBE)', 'Tustin', 'Backward Euler'};
sample_times = [25e-6, 50e-6, 100e-6, 200e-6];
sim_duration = 1.0;
results = struct('solver', {}, 'sample_time', {}, 'wall_s', {}, ...
    'I_rms', {}, 'compile_ok', {}, 'err', {});

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

        % AC source + RL line + R load
        add_block('powerlib/Electrical Sources/AC Voltage Source', [mdl '/Vac'], ...
            'Position', [60 100 120 150]);
        set_param([mdl '/Vac'], 'Amplitude', '230', 'Phase', '0', 'Frequency', '50');
        add_block('powerlib/Elements/Series RLC Branch', [mdl '/Line'], ...
            'Position', [180 100 230 130]);
        set_param([mdl '/Line'], 'BranchType', 'RL', 'Resistance', '10', 'Inductance', '0.01');
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
        I_rms = NaN;
        try
            set_param(mdl, 'SimulationCommand', 'update');
            compile_ok = true;
            sim(mdl); % warm-up
            t0 = tic;
            simout = sim(mdl);
            wall_s = toc(t0);
            yout = simout.get('yout');
            I_data = real(yout{1}.Values.Data);
            % RMS over second half (steady state)
            mid = floor(numel(I_data) / 2);
            I_rms = sqrt(mean(I_data(mid:end).^2));
        catch ME
            err_msg = truncate(ME.message, 150);
        end

        results(idx).solver = sol;
        results(idx).sample_time = ts;
        results(idx).wall_s = wall_s;
        results(idx).I_rms = I_rms;
        results(idx).compile_ok = compile_ok;
        results(idx).err = err_msg;
    end
end

if bdIsLoaded(mdl), close_system(mdl, 0); end
% Analytical RMS: |Z| = sqrt(60^2 + (2π·50·0.01)^2) ≈ sqrt(3600+9.87) ≈ 60.08
% I_rms = 230/sqrt(2) / 60.08 ≈ 2.708 A peak / sqrt(2) ≈ but actually 230 is peak so
% I_rms = (230/sqrt(2)) / 60.08 ≈ 2.708 A
fprintf('RESULT: ===== AC Speed Sweep (sim=%.1fs, expected I_rms≈2.71A) =====\n', sim_duration);
for k = 1:numel(results)
    r = results(k);
    if r.compile_ok && ~isnan(r.wall_s)
        fprintf('RESULT: solver=%-30s ts=%-3dμs wall=%.4fs I_rms=%.4fA\n', ...
            r.solver, round(r.sample_time*1e6), r.wall_s, r.I_rms);
    else
        fprintf('RESULT: solver=%-30s ts=%-3dμs FAIL: %s\n', ...
            r.solver, round(r.sample_time*1e6), r.err);
    end
end
end

function s_out = truncate(s, n)
if length(s) > n, s_out = [s(1:n) '...']; else, s_out = s; end
end
