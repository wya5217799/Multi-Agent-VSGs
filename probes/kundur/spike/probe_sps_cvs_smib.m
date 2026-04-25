function probe_sps_cvs_smib()
% probe_sps_cvs_smib  Proper single-phase SMIB phasor closed loop.
%
% Topology:
%   [VSG CVS V*exp(j*delta)] -- L (jX) -- [Inf-bus CVS V*exp(j*0)] -- GND
%   Vmeas across L (or at VSG terminal); Imeas in series.
%   Pe = real(V_vsg * conj(I)) / Sbase, single-phase pu.
%
%   Swing eq: M*dω/dt = Pm - Pe - D*(ω-1) ;  dδ/dt = wn*(ω-1)
%
% Tests under powergui Phasor 50 Hz:
%   G3.1 zero_action steady-state — ω -> 1, δ converges to arcsin(Pm * X / V^2)
%   G3.2 Pm step at t=2s — damped swing
%   G3.3 high inertia (M0 doubled) — period elongates, peak smaller
%
% Read-only against project main artifacts. Scratch model in memory.

mdl = 'tmp_sps_smib';

scenarios = {
    'G3_1_zero_action',  'M0=12; D0=3; Pm_step_t=999; Pm_step_amp=0';
    'G3_2_pm_step',      'M0=12; D0=3; Pm_step_t=2.0; Pm_step_amp=0.1';
    'G3_3_high_inertia', 'M0=24; D0=3; Pm_step_t=2.0; Pm_step_amp=0.1';
};

for k = 1:size(scenarios, 1)
    sname = scenarios{k, 1};
    sopts = scenarios{k, 2};

    if bdIsLoaded(mdl), close_system(mdl, 0); end
    new_system(mdl);
    load_system('powerlib');

    eval(sopts);
    assignin('base', 'M0', M0);
    assignin('base', 'D0', D0);
    assignin('base', 'Pm_step_t', Pm_step_t);
    assignin('base', 'Pm_step_amp', Pm_step_amp);
    Pm0 = 0.5;          % nominal Pm pu
    Sbase = 100e6;
    Vbase = 230e3;
    fn = 50;
    wn = 2*pi*fn;
    X_pu = 0.3;
    L_H = X_pu * Vbase^2 / Sbase / wn;   % series inductance to inf-bus
    delta0_target = asin(Pm0 * X_pu);    % nominal equilibrium delta
    assignin('base', 'Pm0', Pm0);
    assignin('base', 'delta0', delta0_target);

    % powergui Phasor
    add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
    set_param([mdl '/powergui'], 'SimulationMode', 'Phasor', 'frequency', '50');
    set_param(mdl, 'StopTime', '5', 'SolverType', 'Variable-step', ...
        'Solver', 'ode23t', 'MaxStep', '0.005');

    % VSG CVS
    add_block('powerlib/Electrical Sources/Controlled Voltage Source', ...
        [mdl '/CVS_VSG'], 'Position', [400 100 460 160]);
    set_param([mdl '/CVS_VSG'], 'Source_Type', 'AC', ...
        'Amplitude', num2str(Vbase), 'Phase', '0', 'Frequency', '50', ...
        'Measurements', 'None');

    % Series L
    add_block('powerlib/Elements/Series RLC Branch', [mdl '/L'], ...
        'Position', [520 100 580 160]);
    set_param([mdl '/L'], 'BranchType', 'L', 'Inductance', num2str(L_H));

    % Inf-bus CVS (constant 1 + 0i  =  Vbase)
    add_block('powerlib/Electrical Sources/Controlled Voltage Source', ...
        [mdl '/CVS_INF'], 'Position', [640 100 700 160]);
    set_param([mdl '/CVS_INF'], 'Source_Type', 'AC', ...
        'Amplitude', num2str(Vbase), 'Phase', '0', 'Frequency', '50', ...
        'Measurements', 'None');

    add_block('built-in/Constant', [mdl '/Vinf'], ...
        'Position', [580 30 640 60], 'Value', [num2str(Vbase) '+0i']);
    add_line(mdl, 'Vinf/1', 'CVS_INF/1', 'autorouting', 'smart');

    add_block('powerlib/Elements/Ground', [mdl '/GND'], ...
        'Position', [400 200 440 230]);
    add_block('powerlib/Elements/Ground', [mdl '/GND_INF'], ...
        'Position', [640 200 680 230]);

    % Imeas in series between CVS_VSG and L
    add_block('powerlib/Measurements/Current Measurement', ...
        [mdl '/Imeas'], 'Position', [490 110 510 150]);

    add_line(mdl, 'CVS_VSG/RConn1', 'Imeas/LConn1', 'autorouting', 'smart');
    add_line(mdl, 'Imeas/RConn1', 'L/LConn1', 'autorouting', 'smart');
    add_line(mdl, 'L/RConn1', 'CVS_INF/RConn1', 'autorouting', 'smart');
    add_line(mdl, 'CVS_VSG/LConn1', 'GND/LConn1', 'autorouting', 'smart');
    add_line(mdl, 'CVS_INF/LConn1', 'GND_INF/LConn1', 'autorouting', 'smart');

    % Vmeas at VSG terminal (CVS_VSG terminals)
    add_block('powerlib/Measurements/Voltage Measurement', ...
        [mdl '/Vmeas'], 'Position', [400 250 460 290]);
    add_line(mdl, 'CVS_VSG/RConn1', 'Vmeas/LConn1', 'autorouting', 'smart');
    add_line(mdl, 'CVS_VSG/LConn1', 'Vmeas/LConn2', 'autorouting', 'smart');

    % Pe = real(V * conj(I)) / Sbase
    %     = (Vr*Ir + Vi*Ii) / Sbase    (single-phase phasor, peak)
    %     * 0.5  (peak phasors)
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

    % Swing eq
    add_block('built-in/Constant', [mdl '/Pm0c'], ...
        'Position', [40 380 70 400], 'Value', 'Pm0');
    add_block('built-in/Step', [mdl '/Pm_step'], ...
        'Position', [40 420 70 450]);
    set_param([mdl '/Pm_step'], 'Time', 'Pm_step_t', 'Before', '0', ...
        'After', 'Pm_step_amp', 'SampleTime', '0');
    add_block('built-in/Sum', [mdl '/Pm_total'], ...
        'Position', [110 395 140 425], 'Inputs', '++');
    add_line(mdl, 'Pm0c/1', 'Pm_total/1', 'autorouting', 'smart');
    add_line(mdl, 'Pm_step/1', 'Pm_total/2', 'autorouting', 'smart');

    add_block('built-in/Integrator', [mdl '/IntW'], ...
        'Position', [400 380 430 410], 'InitialCondition', '1');
    add_block('built-in/Constant', [mdl '/One'], ...
        'Position', [200 350 230 370], 'Value', '1');
    add_block('built-in/Sum', [mdl '/SumDw'], ...
        'Position', [260 380 290 410], 'Inputs', '+-');
    add_line(mdl, 'IntW/1', 'SumDw/1', 'autorouting', 'smart');
    add_line(mdl, 'One/1', 'SumDw/2', 'autorouting', 'smart');

    add_block('built-in/Gain', [mdl '/Dgain'], ...
        'Position', [310 460 350 480], 'Gain', 'D0');
    add_line(mdl, 'SumDw/1', 'Dgain/1', 'autorouting', 'smart');
    add_block('built-in/Sum', [mdl '/SwingSum'], ...
        'Position', [320 395 350 460], 'Inputs', '+--');
    add_line(mdl, 'Pm_total/1', 'SwingSum/1', 'autorouting', 'smart');
    add_line(mdl, 'Pe_pu/1', 'SwingSum/2', 'autorouting', 'smart');
    add_line(mdl, 'Dgain/1', 'SwingSum/3', 'autorouting', 'smart');
    add_block('built-in/Gain', [mdl '/Mgain'], ...
        'Position', [365 395 395 425], 'Gain', '1/M0');
    add_line(mdl, 'SwingSum/1', 'Mgain/1', 'autorouting', 'smart');
    add_line(mdl, 'Mgain/1', 'IntW/1', 'autorouting', 'smart');

    % delta integrator (initialised at delta0_target)
    add_block('built-in/Gain', [mdl '/wnG'], ...
        'Position', [310 280 350 310], 'Gain', num2str(wn));
    add_line(mdl, 'SumDw/1', 'wnG/1', 'autorouting', 'smart');
    add_block('built-in/Integrator', [mdl '/IntD'], ...
        'Position', [400 280 430 310], 'InitialCondition', 'delta0');
    add_line(mdl, 'wnG/1', 'IntD/1', 'autorouting', 'smart');

    % Build complex phasor V_VSG = Vbase * exp(j*delta)
    add_block('simulink/Math Operations/Trigonometric Function', ...
        [mdl '/cosD'], 'Position', [200 220 240 250], 'Operator', 'cos');
    add_block('simulink/Math Operations/Trigonometric Function', ...
        [mdl '/sinD'], 'Position', [200 180 240 210], 'Operator', 'sin');
    add_line(mdl, 'IntD/1', 'cosD/1', 'autorouting', 'smart');
    add_line(mdl, 'IntD/1', 'sinD/1', 'autorouting', 'smart');
    add_block('built-in/Gain', [mdl '/VrG'], ...
        'Position', [260 220 290 250], 'Gain', num2str(Vbase));
    add_block('built-in/Gain', [mdl '/ViG'], ...
        'Position', [260 180 290 210], 'Gain', num2str(Vbase));
    add_line(mdl, 'cosD/1', 'VrG/1', 'autorouting', 'smart');
    add_line(mdl, 'sinD/1', 'ViG/1', 'autorouting', 'smart');
    add_block('simulink/Math Operations/Real-Imag to Complex', ...
        [mdl '/RI2C'], 'Position', [320 195 360 235]);
    add_line(mdl, 'VrG/1', 'RI2C/1', 'autorouting', 'smart');
    add_line(mdl, 'ViG/1', 'RI2C/2', 'autorouting', 'smart');
    add_line(mdl, 'RI2C/1', 'CVS_VSG/1', 'autorouting', 'smart');

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
        'Position', [730 290 780 320], 'VariableName', 'Pe_ts', ...
        'SaveFormat', 'Timeseries');
    add_line(mdl, 'Pe_pu/1', 'W_Pe/1', 'autorouting', 'smart');

    fprintf('RESULT: ===== %s =====\n', sname);
    fprintf('RESULT:   M0=%g D0=%g Pm0=%g delta0=%.4f rad Pm_step_t=%g Pm_step_amp=%g\n', ...
        M0, D0, Pm0, delta0_target, Pm_step_t, Pm_step_amp);

    try
        evalc("set_param(mdl, 'SimulationCommand', 'update')");
        fprintf('RESULT:   compile_ok=1\n');
    catch e
        fprintf('RESULT:   compile_ok=0  err=%s\n', regexprep(e.message, '\s+', ' '));
        close_system(mdl, 0);
        continue;
    end

    try
        so = sim(mdl, 'StopTime', '5', 'SaveOutput', 'on', ...
            'ReturnWorkspaceOutputs', 'on');
        omega = so.get('omega_ts');
        delta_obj = so.get('delta_ts');
        pe_ts = so.get('Pe_ts');
        if isa(omega, 'timeseries')
            o = omega.Data;
            t = omega.Time;
            fprintf('RESULT:   omega_min=%.6f omega_max=%.6f omega_final=%.6f n_t=%d\n', ...
                min(o), max(o), o(end), numel(t));
            % settled check: last 1 s window
            mask = t >= t(end) - 1.0;
            o_tail = o(mask);
            fprintf('RESULT:   omega_tail_mean=%.6f tail_std=%.6f\n', ...
                mean(o_tail), std(o_tail));
        end
        if isa(delta_obj, 'timeseries')
            d = delta_obj.Data;
            fprintf('RESULT:   delta_init=%.4f delta_final=%.4f delta_min=%.4f delta_max=%.4f\n', ...
                d(1), d(end), min(d), max(d));
        end
        if isa(pe_ts, 'timeseries')
            p = pe_ts.Data;
            fprintf('RESULT:   Pe_init=%.4f Pe_final=%.4f Pe_min=%.4f Pe_max=%.4f\n', ...
                p(1), p(end), min(p), max(p));
        end
    catch e
        fprintf('RESULT:   sim_err=%s\n', regexprep(e.message, '\s+', ' '));
    end

    close_system(mdl, 0);
end

end
