function probe_sps_cvs_swing_loop()
% probe_sps_cvs_swing_loop  Single-phase SMIB closed-loop test.
% VSG swing equation drives a magnitude-angle phasor into SPS native CVS,
% feeds an R load behind a Voltage Measurement, and observes omega/delta
% response under powergui Phasor mode.
%
% Tests:
%   G2.1  zero-action 5 s steady-state — omega should stay at 1.0 pu
%   G2.2  small-step Pm increase at t=2 s — omega should swing then settle
%   G2.3  H change (M0 12 -> 24) — oscillation period should lengthen
%
% Read-only against project main artifacts. Builds scratch model in memory.
%
% Topology (single-phase phasor SMIB):
%   [Pm const] -> + -> [Sum] -> [/M] -> [IntW] -> omega
%   [Pe meas]  -> -      ^
%   [D*(omega-1)] -------'
%   omega-1 -> wn -> [IntD] -> delta
%   [V_mag=1.0 const, delta] -> [Magnitude-Angle to Complex] -> [SPS CVS]
%   [SPS CVS] -> R_load -> GND
%   [V Meas across R] and [I Meas in series with R] -> Pe = (V * conj(I)).real

mdl = 'tmp_sps_swing';

scenarios = {
    'G2_1_zero_action',  'M0=12; D0=3; Pm_step_t=999; Pm_step_amp=0';
    'G2_2_pm_step',      'M0=12; D0=3; Pm_step_t=2.0; Pm_step_amp=0.1';
    'G2_3_high_inertia', 'M0=24; D0=3; Pm_step_t=2.0; Pm_step_amp=0.1';
};

for k = 1:size(scenarios, 1)
    sname = scenarios{k, 1};
    sopts = scenarios{k, 2};

    if bdIsLoaded(mdl), close_system(mdl, 0); end
    new_system(mdl);
    load_system('powerlib');

    % Parse opts -> assignin base
    eval(sopts);
    assignin('base', 'M0', M0);
    assignin('base', 'D0', D0);
    assignin('base', 'Pm_step_t', Pm_step_t);
    assignin('base', 'Pm_step_amp', Pm_step_amp);
    Pm0 = 0.5;          % nominal Pm pu
    V_mag = 1.0;        % VSG terminal magnitude pu
    R_load_pu = 2.0;    % R load (pu) so Pe nominal ~ V^2/R = 0.5 pu
    Sbase = 100e6;
    Vbase = 230e3;
    Zbase = Vbase^2 / Sbase;
    R_load = R_load_pu * Zbase;
    fn = 50;
    wn = 2*pi*fn;

    assignin('base', 'Pm0', Pm0);

    % powergui Phasor 50 Hz
    add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
    set_param([mdl '/powergui'], 'SimulationMode', 'Phasor', 'frequency', '50');
    set_param(mdl, 'StopTime', '5', 'SolverType', 'Variable-step', ...
        'Solver', 'ode23t', 'MaxStep', '0.005');

    % SPS CVS
    add_block('powerlib/Electrical Sources/Controlled Voltage Source', ...
        [mdl '/CVS'], 'Position', [400 100 460 160]);
    set_param([mdl '/CVS'], 'Source_Type', 'AC', ...
        'Amplitude', num2str(Vbase), 'Phase', '0', 'Frequency', '50', ...
        'Measurements', 'None');

    add_block('powerlib/Elements/Ground', [mdl '/GND'], 'Position', [400 200 440 230]);
    add_block('powerlib/Elements/Series RLC Branch', [mdl '/R'], ...
        'Position', [520 100 580 160]);
    set_param([mdl '/R'], 'BranchType', 'R', 'Resistance', num2str(R_load));
    add_block('powerlib/Elements/Ground', [mdl '/GND2'], 'Position', [620 200 660 230]);

    add_line(mdl, 'CVS/RConn1', 'R/LConn1', 'autorouting', 'smart');
    add_line(mdl, 'CVS/LConn1', 'GND/LConn1', 'autorouting', 'smart');
    add_line(mdl, 'R/RConn1', 'GND2/LConn1', 'autorouting', 'smart');

    % Voltage Measurement across CVS terminals
    add_block('powerlib/Measurements/Voltage Measurement', ...
        [mdl '/Vmeas'], 'Position', [520 250 580 290]);
    add_line(mdl, 'CVS/RConn1', 'Vmeas/LConn1', 'autorouting', 'smart');
    add_line(mdl, 'CVS/LConn1', 'Vmeas/LConn2', 'autorouting', 'smart');

    % Pe = |V|^2 / R / Sbase  (resistive load, peak phasor scaled by 0.5)
    add_block('simulink/Math Operations/Complex to Magnitude-Angle', ...
        [mdl '/V_MA'], 'Position', [620 250 660 280]);
    set_param([mdl '/V_MA'], 'Output', 'Magnitude');
    add_line(mdl, 'Vmeas/1', 'V_MA/1', 'autorouting', 'smart');
    add_block('built-in/Math', [mdl '/VmagSq'], ...
        'Position', [690 252 730 278], 'Operator', 'square');
    add_line(mdl, 'V_MA/1', 'VmagSq/1', 'autorouting', 'smart');
    add_block('built-in/Gain', [mdl '/Pe_pu'], 'Position', [760 252 810 278], ...
        'Gain', num2str(0.5/(R_load*Sbase)));
    add_line(mdl, 'VmagSq/1', 'Pe_pu/1', 'autorouting', 'smart');

    % Swing equation
    % Pm with step
    add_block('built-in/Constant', [mdl '/Pm0'], 'Position', [40 380 70 400], 'Value', 'Pm0');
    add_block('built-in/Step', [mdl '/Pm_step'], 'Position', [40 420 70 450]);
    set_param([mdl '/Pm_step'], 'Time', 'Pm_step_t', 'Before', '0', ...
        'After', 'Pm_step_amp');
    add_block('built-in/Sum', [mdl '/Pm_total'], 'Position', [110 395 140 425], 'Inputs', '++');
    add_line(mdl, 'Pm0/1', 'Pm_total/1', 'autorouting', 'smart');
    add_line(mdl, 'Pm_step/1', 'Pm_total/2', 'autorouting', 'smart');

    % omega-1
    add_block('built-in/Integrator', [mdl '/IntW'], 'Position', [400 380 430 410], ...
        'InitialCondition', '1');
    add_block('built-in/Constant', [mdl '/One'], 'Position', [200 350 230 370], 'Value', '1');
    add_block('built-in/Sum', [mdl '/SumDw'], 'Position', [260 380 290 410], 'Inputs', '+-');
    add_line(mdl, 'IntW/1', 'SumDw/1', 'autorouting', 'smart');
    add_line(mdl, 'One/1', 'SumDw/2', 'autorouting', 'smart');

    % D*(omega-1)
    add_block('built-in/Gain', [mdl '/Dgain'], 'Position', [310 460 350 480], ...
        'Gain', 'D0');
    add_line(mdl, 'SumDw/1', 'Dgain/1', 'autorouting', 'smart');

    % Sum: Pm - Pe - D*dw
    add_block('built-in/Sum', [mdl '/SwingSum'], ...
        'Position', [320 395 350 460], 'Inputs', '+--');
    add_line(mdl, 'Pm_total/1', 'SwingSum/1', 'autorouting', 'smart');
    add_line(mdl, 'Pe_pu/1', 'SwingSum/2', 'autorouting', 'smart');
    add_line(mdl, 'Dgain/1', 'SwingSum/3', 'autorouting', 'smart');
    add_block('built-in/Gain', [mdl '/Mgain'], 'Position', [365 395 395 425], ...
        'Gain', '1/M0');
    add_line(mdl, 'SwingSum/1', 'Mgain/1', 'autorouting', 'smart');
    add_line(mdl, 'Mgain/1', 'IntW/1', 'autorouting', 'smart');

    % delta = integral( wn*(omega-1) )
    add_block('built-in/Gain', [mdl '/wnG'], 'Position', [310 280 350 310], 'Gain', num2str(wn));
    add_line(mdl, 'SumDw/1', 'wnG/1', 'autorouting', 'smart');
    add_block('built-in/Integrator', [mdl '/IntD'], 'Position', [400 280 430 310], ...
        'InitialCondition', '0');
    add_line(mdl, 'wnG/1', 'IntD/1', 'autorouting', 'smart');

    % Build complex phasor: V_mag * exp(j*delta) = V_mag*cos(delta) + j*V_mag*sin(delta)
    add_block('simulink/Math Operations/Trigonometric Function', [mdl '/cosD'], ...
        'Position', [200 220 240 250], 'Operator', 'cos');
    add_block('simulink/Math Operations/Trigonometric Function', [mdl '/sinD'], ...
        'Position', [200 180 240 210], 'Operator', 'sin');
    add_line(mdl, 'IntD/1', 'cosD/1', 'autorouting', 'smart');
    add_line(mdl, 'IntD/1', 'sinD/1', 'autorouting', 'smart');
    add_block('built-in/Gain', [mdl '/VrG'], 'Position', [260 220 290 250], ...
        'Gain', num2str(Vbase));
    add_block('built-in/Gain', [mdl '/ViG'], 'Position', [260 180 290 210], ...
        'Gain', num2str(Vbase));
    add_line(mdl, 'cosD/1', 'VrG/1', 'autorouting', 'smart');
    add_line(mdl, 'sinD/1', 'ViG/1', 'autorouting', 'smart');
    add_block('simulink/Math Operations/Real-Imag to Complex', [mdl '/RI2C'], ...
        'Position', [320 195 360 235]);
    add_line(mdl, 'VrG/1', 'RI2C/1', 'autorouting', 'smart');
    add_line(mdl, 'ViG/1', 'RI2C/2', 'autorouting', 'smart');
    add_line(mdl, 'RI2C/1', 'CVS/1', 'autorouting', 'smart');

    % Loggers
    add_block('simulink/Sinks/To Workspace', [mdl '/W_omega'], ...
        'Position', [460 380 510 400], 'VariableName', 'omega_ts', ...
        'SaveFormat', 'Timeseries');
    add_line(mdl, 'IntW/1', 'W_omega/1', 'autorouting', 'smart');
    add_block('simulink/Sinks/To Workspace', [mdl '/W_delta'], ...
        'Position', [460 280 510 300], 'VariableName', 'delta_ts', ...
        'SaveFormat', 'Timeseries');
    add_line(mdl, 'IntD/1', 'W_delta/1', 'autorouting', 'smart');
    add_block('simulink/Sinks/To Workspace', [mdl '/W_Pe'], ...
        'Position', [820 252 870 278], 'VariableName', 'Pe_ts', ...
        'SaveFormat', 'Timeseries');
    add_line(mdl, 'Pe_pu/1', 'W_Pe/1', 'autorouting', 'smart');

    fprintf('RESULT: ===== %s =====\n', sname);
    fprintf('RESULT:   M0=%g D0=%g Pm_step_t=%g Pm_step_amp=%g\n', ...
        M0, D0, Pm_step_t, Pm_step_amp);

    % Try compile
    try
        evalc("set_param(mdl, 'SimulationCommand', 'update')");
        fprintf('RESULT:   compile_ok=1\n');
    catch e
        fprintf('RESULT:   compile_ok=0  err=%s\n', regexprep(e.message, '\s+', ' '));
        close_system(mdl, 0);
        continue;
    end

    % Try sim
    try
        so = sim(mdl, 'StopTime', '5', 'SaveOutput', 'on', ...
            'ReturnWorkspaceOutputs', 'on');
        omega = so.get('omega_ts');
        delta_ts_obj = so.get('delta_ts');
        pe_ts = so.get('Pe_ts');
        if isa(omega, 'timeseries')
            o = omega.Data;
            t = omega.Time;
            fprintf('RESULT:   omega_min=%.6f omega_max=%.6f omega_final=%.6f n_t=%d\n', ...
                min(o), max(o), o(end), numel(t));
        end
        if isa(delta_ts_obj, 'timeseries')
            d = delta_ts_obj.Data;
            fprintf('RESULT:   delta_final_rad=%.4f delta_max=%.4f\n', d(end), max(abs(d)));
        end
        if isa(pe_ts, 'timeseries')
            p = pe_ts.Data;
            fprintf('RESULT:   Pe_final=%.4f Pe_min=%.4f Pe_max=%.4f\n', ...
                p(end), min(p), max(p));
        end
    catch e
        fprintf('RESULT:   sim_err=%s\n', regexprep(e.message, '\s+', ' '));
    end

    close_system(mdl, 0);
end

end
