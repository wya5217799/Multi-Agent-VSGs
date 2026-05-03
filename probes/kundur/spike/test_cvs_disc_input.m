function test_cvs_disc_input()
%TEST_CVS_DISC_INPUT  Test 3 input patterns for powerlib CVS in Discrete mode.
% Pattern A: Constant scalar real
% Pattern B: Sinusoid (real-valued time-varying)
% Pattern C: Complex phasor (current Phasor pattern, expected to FAIL)
mdl = 'cvs_disc_test';
patterns = {'A_const_real', 'B_sin_real', 'C_complex_phasor'};
results = cell(numel(patterns), 1);

for p = 1:numel(patterns)
    pname = patterns{p};
    if bdIsLoaded(mdl), close_system(mdl, 0); end
    new_system(mdl);
    load_system('powerlib');

    % Discrete powergui 50 us
    add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
    set_param([mdl '/powergui'], 'SimulationMode', 'Discrete', 'SampleTime', '50e-6');
    set_param(mdl, 'StopTime', '0.05', 'SolverType', 'Fixed-step', ...
        'Solver', 'FixedStepDiscrete', 'FixedStep', '50e-6', ...
        'SaveOutput', 'on', 'ReturnWorkspaceOutputs', 'on');

    % Add CVS — same block path as v3 build script
    add_block('powerlib/Electrical Sources/Controlled Voltage Source', ...
        [mdl '/CVS'], 'Position', [200 100 260 150]);
    set_param([mdl '/CVS'], 'Source_Type', 'DC', 'Initialize', 'off', ...
        'Amplitude', '0', 'Phase', '0', 'Frequency', '0', 'Measurements', 'None');

    compile_ok = false;
    sim_ok = false;
    v_min = NaN; v_max = NaN; n_samples = 0;
    err_msg = '';

    try
        % Input pattern
        switch pname
            case 'A_const_real'
                add_block('simulink/Sources/Constant', [mdl '/Vin'], ...
                    'Position', [80 110 140 140], 'Value', '230e3');
                add_line(mdl, 'Vin/1', 'CVS/1');
            case 'B_sin_real'
                add_block('simulink/Sources/Sine Wave', [mdl '/Vin'], ...
                    'Position', [80 110 140 140], 'Amplitude', '230e3', ...
                    'Frequency', '2*pi*50', 'Phase', '0');
                add_line(mdl, 'Vin/1', 'CVS/1');
            case 'C_complex_phasor'
                add_block('simulink/Sources/Constant', [mdl '/Vr'], ...
                    'Position', [60 90 100 110], 'Value', '230e3');
                add_block('simulink/Sources/Constant', [mdl '/Vi'], ...
                    'Position', [60 130 100 150], 'Value', '0');
                add_block('simulink/Math Operations/Real-Imag to Complex', ...
                    [mdl '/RI2C'], 'Position', [130 100 170 140]);
                add_line(mdl, 'Vr/1', 'RI2C/1');
                add_line(mdl, 'Vi/1', 'RI2C/2');
                add_line(mdl, 'RI2C/1', 'CVS/1');
        end

        % R load + GND + Vmeas + Outport
        add_block('powerlib/Elements/Series RLC Branch', [mdl '/Rload'], ...
            'Position', [320 100 370 130]);
        set_param([mdl '/Rload'], 'BranchType', 'R', 'Resistance', '100');
        add_block('powerlib/Elements/Ground', [mdl '/GND'], ...
            'Position', [380 130 420 160]);
        add_block('powerlib/Measurements/Voltage Measurement', [mdl '/Vmeas'], ...
            'Position', [200 200 260 230]);
        add_line(mdl, 'CVS/RConn1', 'Rload/LConn1', 'autorouting', 'smart');
        add_line(mdl, 'Rload/RConn1', 'GND/LConn1', 'autorouting', 'smart');
        add_line(mdl, 'CVS/RConn1', 'Vmeas/LConn1', 'autorouting', 'smart');
        add_line(mdl, 'CVS/LConn1', 'Vmeas/LConn2', 'autorouting', 'smart');

        % Outport (auto-logged via simout.yout)
        add_block('simulink/Sinks/Out1', [mdl '/V_OUT_PORT'], ...
            'Position', [320 200 360 230]);
        add_line(mdl, 'Vmeas/1', 'V_OUT_PORT/1');

        % Try compile via update_model
        set_param(mdl, 'SimulationCommand', 'update');
        compile_ok = true;
    catch ME
        err_msg = sprintf('BUILD/COMPILE: %s', truncate(ME.message, 250));
    end

    if compile_ok
        try
            simout = sim(mdl);
            sim_ok = true;
            % Try multiple ways to retrieve voltage
            yout = simout.get('yout');
            if ~isempty(yout)
                v_data = yout{1}.Values.Data;
                v_min = min(real(v_data(:)));
                v_max = max(real(v_data(:)));
                n_samples = numel(v_data);
            end
        catch ME
            err_msg = sprintf('SIM: %s', truncate(ME.message, 250));
        end
    end

    results{p} = struct('pattern', pname, 'compile_ok', compile_ok, ...
        'sim_ok', sim_ok, 'v_min', v_min, 'v_max', v_max, ...
        'n_samples', n_samples, 'err', err_msg);
end

if bdIsLoaded(mdl), close_system(mdl, 0); end

% Report
fprintf('RESULT: ===== CVS Discrete Mode Input Pattern Test =====\n');
for p = 1:numel(results)
    r = results{p};
    if r.sim_ok
        fprintf('RESULT: %s | compile=PASS sim=PASS V=[%.1f,%.1f] n=%d\n', ...
            r.pattern, r.v_min, r.v_max, r.n_samples);
    elseif r.compile_ok
        fprintf('RESULT: %s | compile=PASS sim=FAIL err=%s\n', r.pattern, r.err);
    else
        fprintf('RESULT: %s | compile=FAIL err=%s\n', r.pattern, r.err);
    end
end
end

function s_out = truncate(s, n)
if length(s) > n
    s_out = [s(1:n) '...'];
else
    s_out = s;
end
end
