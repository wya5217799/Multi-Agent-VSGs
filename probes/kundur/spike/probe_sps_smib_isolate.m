function probe_sps_smib_isolate()
% probe_sps_smib_isolate  Bisect G3 SMIB compile failure.
% Builds 4 progressively-richer scratch models in memory and reports
% which step first fails compile.
%
%   I1: powergui Phasor + 1 CVS + R-load + GND  (already proven OK)
%   I2: powergui Phasor + 2 CVS in parallel through L  (key topology)
%   I3: I2 + Vmeas + Imeas + complex-power calc
%   I4: I3 + swing-eq feedback closing loop
%
% Read-only. Reports compile_ok per stage.

mdl = 'tmp_smib_iso';
Sbase = 100e6; Vbase = 230e3; fn = 50; wn = 2*pi*fn;
X_pu = 0.3;
L_H = X_pu * Vbase^2 / Sbase / wn;

stages = {'I1_single_cvs', 'I2_two_cvs_via_L', 'I3_with_meas', 'I4_with_swing'};

for k = 1:numel(stages)
    sname = stages{k};
    if bdIsLoaded(mdl), close_system(mdl, 0); end
    new_system(mdl);
    load_system('powerlib');

    add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
    set_param([mdl '/powergui'], 'SimulationMode', 'Phasor', 'frequency', '50');
    set_param(mdl, 'StopTime', '0.1', 'SolverType', 'Variable-step', ...
        'Solver', 'ode23t', 'MaxStep', '0.001');

    % --- Stage I1: single CVS + R-load + GND
    add_block('powerlib/Electrical Sources/Controlled Voltage Source', ...
        [mdl '/CVS_VSG'], 'Position', [400 100 460 160]);
    set_param([mdl '/CVS_VSG'], 'Source_Type', 'AC', ...
        'Amplitude', num2str(Vbase), 'Phase', '0', 'Frequency', '50', ...
        'Measurements', 'None');
    add_block('built-in/Constant', [mdl '/Vin_VSG'], ...
        'Position', [320 110 380 140], 'Value', [num2str(Vbase) '+0i']);
    add_line(mdl, 'Vin_VSG/1', 'CVS_VSG/1', 'autorouting', 'smart');
    add_block('powerlib/Elements/Ground', [mdl '/GND_VSG'], ...
        'Position', [400 200 440 230]);
    add_line(mdl, 'CVS_VSG/LConn1', 'GND_VSG/LConn1', 'autorouting', 'smart');

    if k == 1
        % Add a series R load to ground for I1
        add_block('powerlib/Elements/Series RLC Branch', [mdl '/R'], ...
            'Position', [520 100 580 160]);
        set_param([mdl '/R'], 'BranchType', 'R', 'Resistance', '100');
        add_block('powerlib/Elements/Ground', [mdl '/GND_R'], ...
            'Position', [620 200 660 230]);
        add_line(mdl, 'CVS_VSG/RConn1', 'R/LConn1', 'autorouting', 'smart');
        add_line(mdl, 'R/RConn1', 'GND_R/LConn1', 'autorouting', 'smart');
    else
        % Stage I2+: series L + Inf-bus CVS + GND
        add_block('powerlib/Elements/Series RLC Branch', [mdl '/L'], ...
            'Position', [520 100 580 160]);
        set_param([mdl '/L'], 'BranchType', 'L', 'Inductance', num2str(L_H));
        add_block('powerlib/Electrical Sources/Controlled Voltage Source', ...
            [mdl '/CVS_INF'], 'Position', [640 100 700 160]);
        set_param([mdl '/CVS_INF'], 'Source_Type', 'AC', ...
            'Amplitude', num2str(Vbase), 'Phase', '0', 'Frequency', '50', ...
            'Measurements', 'None');
        add_block('built-in/Constant', [mdl '/Vin_INF'], ...
            'Position', [560 30 620 60], 'Value', [num2str(Vbase) '+0i']);
        add_line(mdl, 'Vin_INF/1', 'CVS_INF/1', 'autorouting', 'smart');
        add_block('powerlib/Elements/Ground', [mdl '/GND_INF'], ...
            'Position', [640 200 680 230]);
        add_line(mdl, 'CVS_VSG/RConn1', 'L/LConn1', 'autorouting', 'smart');
        add_line(mdl, 'L/RConn1', 'CVS_INF/RConn1', 'autorouting', 'smart');
        add_line(mdl, 'CVS_INF/LConn1', 'GND_INF/LConn1', 'autorouting', 'smart');
    end

    if k >= 3
        % Add Vmeas and Imeas
        add_block('powerlib/Measurements/Voltage Measurement', ...
            [mdl '/Vmeas'], 'Position', [400 250 460 290]);
        add_line(mdl, 'CVS_VSG/RConn1', 'Vmeas/LConn1', 'autorouting', 'smart');
        add_line(mdl, 'CVS_VSG/LConn1', 'Vmeas/LConn2', 'autorouting', 'smart');

        add_block('powerlib/Measurements/Current Measurement', ...
            [mdl '/Imeas'], 'Position', [490 110 510 150]);
        delete_line(mdl, 'CVS_VSG/RConn1', 'L/LConn1');
        add_line(mdl, 'CVS_VSG/RConn1', 'Imeas/LConn1', 'autorouting', 'smart');
        add_line(mdl, 'Imeas/RConn1', 'L/LConn1', 'autorouting', 'smart');

        % Pe = (Vr*Ir + Vi*Ii) * 0.5 / Sbase
        add_block('simulink/Math Operations/Complex to Real-Imag', ...
            [mdl '/V_RI'], 'Position', [490 252 530 288]);
        set_param([mdl '/V_RI'], 'Output', 'Real and imag');
        add_line(mdl, 'Vmeas/1', 'V_RI/1', 'autorouting', 'smart');
        add_block('simulink/Math Operations/Complex to Real-Imag', ...
            [mdl '/I_RI'], 'Position', [490 320 530 356]);
        set_param([mdl '/I_RI'], 'Output', 'Real and imag');
        add_line(mdl, 'Imeas/1', 'I_RI/1', 'autorouting', 'smart');
        add_block('built-in/Product', [mdl '/VrIr'], ...
            'Position', [560 260 590 280], 'Inputs', '2');
        add_line(mdl, 'V_RI/1', 'VrIr/1', 'autorouting', 'smart');
        add_line(mdl, 'I_RI/1', 'VrIr/2', 'autorouting', 'smart');
        add_block('built-in/Product', [mdl '/ViIi'], ...
            'Position', [560 330 590 350], 'Inputs', '2');
        add_line(mdl, 'V_RI/2', 'ViIi/1', 'autorouting', 'smart');
        add_line(mdl, 'I_RI/2', 'ViIi/2', 'autorouting', 'smart');
        add_block('built-in/Sum', [mdl '/PSum'], ...
            'Position', [620 290 650 320], 'Inputs', '++');
        add_line(mdl, 'VrIr/1', 'PSum/1', 'autorouting', 'smart');
        add_line(mdl, 'ViIi/1', 'PSum/2', 'autorouting', 'smart');
        add_block('built-in/Gain', [mdl '/Pe_pu'], ...
            'Position', [670 290 720 320], 'Gain', num2str(0.5/Sbase));
        add_line(mdl, 'PSum/1', 'Pe_pu/1', 'autorouting', 'smart');

        add_block('simulink/Sinks/To Workspace', [mdl '/W_Pe'], ...
            'Position', [730 290 780 320], 'VariableName', 'Pe_ts', ...
            'SaveFormat', 'Timeseries');
        add_line(mdl, 'Pe_pu/1', 'W_Pe/1', 'autorouting', 'smart');
    end

    % Try compile
    fprintf('RESULT: ===== %s =====\n', sname);
    try
        evalc("set_param(mdl, 'SimulationCommand', 'update')");
        fprintf('RESULT:   compile_ok=1\n');
    catch e
        fprintf('RESULT:   compile_ok=0  err=%s\n', regexprep(e.message, '\s+', ' '));
        % Drill into specific error via lasterr
        try
            lerr = lasterror();
            if ~isempty(lerr.identifier)
                fprintf('RESULT:   id=%s\n', lerr.identifier);
            end
            % Try to get diagnostic via try sim
            try
                sim(mdl, 'StopTime', '0.001');
            catch e2
                fprintf('RESULT:   sim_diag=%s\n', regexprep(e2.message, '\s+', ' '));
            end
        catch
        end
        close_system(mdl, 0);
        continue;
    end

    % Try sim if compile passed
    try
        so = sim(mdl, 'StopTime', '0.05', 'SaveOutput', 'on', ...
            'ReturnWorkspaceOutputs', 'on');
        fprintf('RESULT:   sim_ok=1\n');
        if k >= 3
            pe = so.get('Pe_ts');
            if isa(pe, 'timeseries')
                fprintf('RESULT:   Pe_final=%.6f\n', pe.Data(end));
            end
        end
    catch e
        fprintf('RESULT:   sim_err=%s\n', regexprep(e.message, '\s+', ' '));
    end

    close_system(mdl, 0);
end

end
