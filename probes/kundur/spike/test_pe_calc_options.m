function test_pe_calc_options()
%TEST_PE_CALC_OPTIONS  Compare Pe calculation patterns in Discrete mode.
% Setup: V(t) = 100·sin(2π·50·t), I(t) = 1·sin(2π·50·t)  (same phase)
% Expected average P = 0.5·V_peak·I_peak·cos(0) = 50 W
%
% Patterns:
%   A. V·I → 1st-order LPF (τ=20ms)
%   B. V·I → Discrete Mean Value over 20ms window
%   C. (no test — 3-phase requires more wiring; deferred)
%
% Reports: settling time + steady-state P + speed (relative).

mdl = 'pe_disc_test';
patterns = {'A_lpf_1st', 'B_mean_window'};
results = cell(numel(patterns), 1);

for p = 1:numel(patterns)
    pname = patterns{p};
    if bdIsLoaded(mdl), close_system(mdl, 0); end
    new_system(mdl);
    load_system('powerlib');

    add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
    set_param([mdl '/powergui'], 'SimulationMode', 'Discrete', 'SampleTime', '50e-6');
    set_param(mdl, 'StopTime', '0.20', 'SolverType', 'Fixed-step', ...
        'Solver', 'FixedStepDiscrete', 'FixedStep', '50e-6', ...
        'SaveOutput', 'on', 'ReturnWorkspaceOutputs', 'on');

    % Synthesize V and I sinusoids
    add_block('simulink/Sources/Sine Wave', [mdl '/Vsig'], ...
        'Position', [60 80 120 110], 'Amplitude', '100', ...
        'Frequency', '2*pi*50', 'Phase', '0');
    add_block('simulink/Sources/Sine Wave', [mdl '/Isig'], ...
        'Position', [60 140 120 170], 'Amplitude', '1', ...
        'Frequency', '2*pi*50', 'Phase', '0');

    % V·I product (instantaneous power, oscillates at 100 Hz around 50 W)
    add_block('simulink/Math Operations/Product', [mdl '/VI'], ...
        'Position', [180 110 220 140], 'Inputs', '2');
    add_line(mdl, 'Vsig/1', 'VI/1');
    add_line(mdl, 'Isig/1', 'VI/2');

    compile_ok = false;
    err_msg = '';
    try
        switch pname
            case 'A_lpf_1st'
                % 1st-order Discrete LPF: H(z) = a / (1 - (1-a)·z^-1), a = dt/(τ+dt)
                % τ=20ms, dt=50μs → a = 50e-6/(20e-3+50e-6) ≈ 0.002494
                add_block('simulink/Discrete/Discrete Filter', [mdl '/Pe_filt'], ...
                    'Position', [280 110 340 140], ...
                    'Numerator', '0.002494', ...
                    'Denominator', '[1 -0.997506]', ...
                    'SampleTime', '50e-6');
                add_line(mdl, 'VI/1', 'Pe_filt/1');
                add_block('simulink/Sinks/Out1', [mdl '/Pe_OUT'], ...
                    'Position', [380 110 420 140]);
                add_line(mdl, 'Pe_filt/1', 'Pe_OUT/1');
            case 'B_mean_window'
                % Discrete Mean over 20ms = 400 samples at 50μs
                % Use Moving Average via dsp toolbox if available, else
                % simulink/Discrete/Discrete-Time Integrator + division
                % Simpler: use built-in 'Mean (Variable Frequency)' if exists,
                % else use an FIR filter with all-equal coefficients.
                add_block('simulink/Discrete/Discrete FIR Filter', [mdl '/Pe_mean'], ...
                    'Position', [280 110 340 140], ...
                    'Coefficients', sprintf('ones(1,%d)/%d', 400, 400), ...
                    'SampleTime', '50e-6');
                add_line(mdl, 'VI/1', 'Pe_mean/1');
                add_block('simulink/Sinks/Out1', [mdl '/Pe_OUT'], ...
                    'Position', [380 110 420 140]);
                add_line(mdl, 'Pe_mean/1', 'Pe_OUT/1');
        end
        set_param(mdl, 'SimulationCommand', 'update');
        compile_ok = true;
    catch ME
        err_msg = sprintf('BUILD: %s', truncate(ME.message, 200));
    end

    if compile_ok
        try
            t0 = tic;
            simout = sim(mdl);
            t_sim = toc(t0);
            yout = simout.get('yout');
            P_data = yout{1}.Values.Data;
            t_data = yout{1}.Values.Time;
            % Steady-state value (last 20ms mean)
            mask_ss = t_data > 0.18;
            P_ss = mean(P_data(mask_ss));
            % Settling time: when |P - 50| < 1 (within 2% of expected)
            P_err = abs(P_data - 50);
            idx_settled = find(P_err < 1, 1, 'first');
            if isempty(idx_settled)
                t_settle = NaN;
            else
                t_settle = t_data(idx_settled);
            end
            results{p} = struct('pattern', pname, 'sim_ok', true, ...
                'P_ss', P_ss, 't_settle', t_settle, 't_sim', t_sim, 'err', '');
        catch ME
            results{p} = struct('pattern', pname, 'sim_ok', false, ...
                'P_ss', NaN, 't_settle', NaN, 't_sim', NaN, 'err', ME.message);
        end
    else
        results{p} = struct('pattern', pname, 'sim_ok', false, ...
            'P_ss', NaN, 't_settle', NaN, 't_sim', NaN, 'err', err_msg);
    end
end

if bdIsLoaded(mdl), close_system(mdl, 0); end
fprintf('RESULT: ===== Pe Calc Options Discrete (expected P_ss=50W) =====\n');
for p = 1:numel(results)
    r = results{p};
    if r.sim_ok
        fprintf('RESULT: %s | P_ss=%.3f W, t_settle=%.4f s, sim_wall=%.3f s\n', ...
            r.pattern, r.P_ss, r.t_settle, r.t_sim);
    else
        fprintf('RESULT: %s | FAIL: %s\n', r.pattern, r.err);
    end
end
end

function s_out = truncate(s, n)
if length(s) > n, s_out = [s(1:n) '...']; else, s_out = s; end
end
