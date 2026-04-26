function probe_sps_cvs_phasor_input()
% probe_sps_cvs_phasor_input  Determine input signal semantics of
% SPS native Controlled Voltage Source under powergui Phasor mode.
%
% Read-only feasibility check. Builds a scratch model in memory (no save).
% Tests three input formats and records compile/sim outcome:
%   T1: real-valued instantaneous sinusoid (sin(wt))
%   T2: real-valued constant (DC mode 1.0)
%   T3: complex constant (1 + 0j)  [Phasor representation]
%
% For each test: try compile; if compile passes try 0.1 s sim; capture
% any voltage at a Voltage Measurement block.

mdl = 'tmp_cvs_phasor_input';
results = struct();

tests = {'T1_sinusoid', 'T2_real_const', 'T3_complex_const'};

for k = 1:numel(tests)
    tname = tests{k};
    if bdIsLoaded(mdl), close_system(mdl, 0); end
    new_system(mdl);
    load_system('powerlib');

    % powergui Phasor 50 Hz
    add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
    set_param([mdl '/powergui'], 'SimulationMode', 'Phasor', ...
        'frequency', '50');

    % Solver
    set_param(mdl, 'StopTime', '0.1', 'SolverType', 'Variable-step', ...
        'Solver', 'ode23t', 'MaxStep', '0.001');

    % SPS CVS
    add_block('powerlib/Electrical Sources/Controlled Voltage Source', ...
        [mdl '/CVS'], 'Position', [200 100 260 160]);
    set_param([mdl '/CVS'], 'Source_Type', 'AC', 'Amplitude', '1', ...
        'Phase', '0', 'Frequency', '50', 'Measurements', 'Voltage');

    % Ground for one terminal
    add_block('powerlib/Elements/Ground', [mdl '/GND'], 'Position', [200 200 240 230]);

    % Resistive load
    add_block('powerlib/Elements/Series RLC Branch', [mdl '/R'], ...
        'Position', [320 100 380 160]);
    set_param([mdl '/R'], 'BranchType', 'R', 'Resistance', '1');

    add_line(mdl, 'CVS/RConn1', 'R/LConn1', 'autorouting', 'smart');
    add_line(mdl, 'CVS/LConn1', 'GND/LConn1', 'autorouting', 'smart');

    % Second ground at far side of R
    add_block('powerlib/Elements/Ground', [mdl '/GND2'], 'Position', [420 200 460 230]);
    add_line(mdl, 'R/RConn1', 'GND2/LConn1', 'autorouting', 'smart');

    % Input signal — varies per test
    switch tname
        case 'T1_sinusoid'
            add_block('built-in/Sin', [mdl '/Vin'], 'Position', [80 110 130 140]);
            set_param([mdl '/Vin'], 'Amplitude', '1', 'Frequency', num2str(2*pi*50), 'Phase', '0');
            in_path = [mdl '/Vin'];
        case 'T2_real_const'
            add_block('built-in/Constant', [mdl '/Vin'], 'Position', [80 110 130 140]);
            set_param([mdl '/Vin'], 'Value', '1');
            in_path = [mdl '/Vin'];
        case 'T3_complex_const'
            add_block('built-in/Constant', [mdl '/Vin'], 'Position', [80 110 130 140]);
            set_param([mdl '/Vin'], 'Value', '1+0i');
            in_path = [mdl '/Vin'];
    end
    add_line(mdl, [get_param(in_path, 'Name') '/1'], 'CVS/1', 'autorouting', 'smart');

    % Try compile
    fprintf('RESULT: ---- %s ----\n', tname);
    try
        evalc("set_param(mdl, 'SimulationCommand', 'update')");
        compile_ok = true;
        compile_err = '';
    catch e
        compile_ok = false;
        compile_err = regexprep(e.message, '\s+', ' ');
    end
    fprintf('RESULT:   compile_ok=%d\n', compile_ok);
    if ~compile_ok
        fprintf('RESULT:   compile_err=%s\n', compile_err);
    end

    % Try sim
    sim_ok = false;
    sim_err = '';
    if compile_ok
        try
            so = sim(mdl, 'StopTime', '0.05', 'SaveOutput', 'on');
            sim_ok = true;
        catch e
            sim_err = regexprep(e.message, '\s+', ' ');
        end
    end
    fprintf('RESULT:   sim_ok=%d\n', sim_ok);
    if ~sim_ok && ~isempty(sim_err)
        fprintf('RESULT:   sim_err=%s\n', sim_err);
    end

    close_system(mdl, 0);
end

end
