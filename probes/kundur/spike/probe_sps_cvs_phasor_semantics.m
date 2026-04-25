function probe_sps_cvs_phasor_semantics()
% probe_sps_cvs_phasor_semantics  Read Voltage Measurement output of
% SPS native CVS under powergui Phasor mode for several input scalars.
% Determines whether the input is treated as: instantaneous voltage,
% real phasor magnitude, or complex phasor.
%
% Read-only. Scratch model in memory; no save.

mdl = 'tmp_cvs_phasor_sem';

scenarios = {
    'A_const_100',     'real',     '100';
    'B_const_230k',    'real',     '230e3';
    'C_complex_100p0', 'complex',  '100+0i';
    'D_complex_0p100', 'complex',  '0+100i';
    'E_sinusoid_100',  'sin',      '100';   % amplitude 100, 50 Hz
};

for k = 1:size(scenarios, 1)
    sname  = scenarios{k, 1};
    stype  = scenarios{k, 2};
    sval   = scenarios{k, 3};

    if bdIsLoaded(mdl), close_system(mdl, 0); end
    new_system(mdl);
    load_system('powerlib');

    add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
    set_param([mdl '/powergui'], 'SimulationMode', 'Phasor', 'frequency', '50');
    set_param(mdl, 'StopTime', '0.05', 'SolverType', 'Variable-step', ...
        'Solver', 'ode23t', 'MaxStep', '0.001');

    % CVS with voltage measurement
    add_block('powerlib/Electrical Sources/Controlled Voltage Source', ...
        [mdl '/CVS'], 'Position', [200 100 260 160]);
    set_param([mdl '/CVS'], 'Source_Type', 'AC', 'Amplitude', '1', ...
        'Phase', '0', 'Frequency', '50', 'Measurements', 'Voltage');

    add_block('powerlib/Elements/Ground', [mdl '/GND'], 'Position', [200 200 240 230]);
    add_block('powerlib/Elements/Series RLC Branch', [mdl '/R'], ...
        'Position', [320 100 380 160]);
    set_param([mdl '/R'], 'BranchType', 'R', 'Resistance', '1');

    add_line(mdl, 'CVS/RConn1', 'R/LConn1', 'autorouting', 'smart');
    add_line(mdl, 'CVS/LConn1', 'GND/LConn1', 'autorouting', 'smart');
    add_block('powerlib/Elements/Ground', [mdl '/GND2'], 'Position', [420 200 460 230]);
    add_line(mdl, 'R/RConn1', 'GND2/LConn1', 'autorouting', 'smart');

    % Input source
    if strcmp(stype, 'sin')
        add_block('built-in/Sin', [mdl '/Vin'], 'Position', [80 110 130 140]);
        set_param([mdl '/Vin'], 'Amplitude', sval, ...
            'Frequency', num2str(2*pi*50), 'Phase', '0', 'SampleTime', '0');
    else
        add_block('built-in/Constant', [mdl '/Vin'], 'Position', [80 110 130 140]);
        set_param([mdl '/Vin'], 'Value', sval);
    end
    add_line(mdl, 'Vin/1', 'CVS/1', 'autorouting', 'smart');

    % Read voltage measurement output via Goto
    % CVS Measurements=Voltage adds a goto with tag 'CVS' typically;
    % use explicit Voltage Measurement block instead for stability
    add_block('powerlib/Measurements/Voltage Measurement', ...
        [mdl '/Vmeas'], 'Position', [320 250 380 290]);
    add_line(mdl, 'CVS/RConn1', 'Vmeas/LConn1', 'autorouting', 'smart');
    add_line(mdl, 'CVS/LConn1', 'Vmeas/LConn2', 'autorouting', 'smart');

    add_block('simulink/Sinks/To Workspace', [mdl '/Vout'], ...
        'Position', [420 255 470 285], 'VariableName', 'Vout_ts', ...
        'SaveFormat', 'Timeseries');
    add_line(mdl, 'Vmeas/1', 'Vout/1', 'autorouting', 'smart');

    % Run sim
    sim_ok = false;
    final_v_str = '';
    try
        so = sim(mdl, 'StopTime', '0.05', 'SaveOutput', 'on', ...
            'ReturnWorkspaceOutputs', 'on');
        v_ts = so.get('Vout_ts');
        if isa(v_ts, 'timeseries') && ~isempty(v_ts.Data)
            d = v_ts.Data;
            last = d(end, :, :);
            if ~isreal(last)
                final_v_str = sprintf('%.4f%+.4fj', real(last), imag(last));
            else
                final_v_str = sprintf('%.4f', last);
            end
            sim_ok = true;
        else
            final_v_str = 'no_data';
        end
    catch e
        final_v_str = regexprep(e.message, '\s+', ' ');
    end

    fprintf('RESULT: %s | input_type=%s | input_val=%s | sim_ok=%d | Vmeas_final=%s\n', ...
        sname, stype, sval, sim_ok, final_v_str);

    close_system(mdl, 0);
end

end

function tf = iscomplex(x)
tf = ~isreal(x);
end
