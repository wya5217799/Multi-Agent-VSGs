function build_kundur_cvs_p2()
% build_kundur_cvs_p2  Gate P2 — 4-CVS + 4 swing-eq closed-loop model.
%
% Adds per-VSG swing-equation signal chain on top of the P1 structural model:
%   For each i = 1..4:
%     IntW_i, IntD_i (Integrators)
%     swing eq:  Pm_i - Pe_i - D_i*(omega_i-1) -> /M_i -> IntW_i (omega_i)
%     wn*(omega_i - 1) -> IntD_i (delta_i)
%     cos(delta_i), sin(delta_i) -> Vbase*cos / Vbase*sin -> RI2C -> CVS_VSG_i
%     Vmeas_i across CVS_VSG_i; Imeas_i in series CVS_VSG_i -> L_line_i
%     Pe_i = real(V * conj(I)) * 0.5 / Sbase pu  (per-phase peak phasor scaling)
%
% Per-agent base ws variables (driven by reset_workspace in Python probe):
%   M_i, D_i, Pm_i, delta0_i  for i=1..4
%   plus shared: wn_const, Vbase_const, Sbase_const, Pe_scale, L_line_H, L_tie_H
%
% Per-agent ToWorkspace loggers:
%   omega_ts_i, delta_ts_i, Pe_ts_i (Timeseries)

mdl = 'kundur_cvs_p2';
out_dir = fileparts(mfilename('fullpath'));
out_slx = fullfile(out_dir, [mdl '.slx']);

fn = 50; wn = 2*pi*fn;
Sbase = 100e6; Vbase = 230e3;
X_line_pu = 0.10; X_tie_pu = 0.30;
L_line_H = double(X_line_pu * Vbase^2 / Sbase / wn);
L_tie_H  = double(X_tie_pu  * Vbase^2 / Sbase / wn);

% Per-VSG nominal delta (rad) — from Pm0=0.5, X_line, V=Vbase as approx SMIB
delta0_default = double(asin(0.5 * X_line_pu));   % ~0.05 rad

if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
load_system('powerlib');

% powergui Phasor
add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
set_param([mdl '/powergui'], 'SimulationMode', 'Phasor', 'frequency', '50');
set_param(mdl, 'StopTime', '0.5', 'SolverType', 'Variable-step', ...
    'Solver', 'ode23t', 'MaxStep', '0.005');

% L_tie and AC_INF anchor
add_block('powerlib/Elements/Series RLC Branch', [mdl '/L_tie'], ...
    'Position', [800 350 850 400]);
set_param([mdl '/L_tie'], 'BranchType', 'L', 'Inductance', num2str(L_tie_H));
add_block('powerlib/Electrical Sources/AC Voltage Source', ...
    [mdl '/AC_INF'], 'Position', [700 460 760 510]);
set_param([mdl '/AC_INF'], 'Amplitude', num2str(Vbase), 'Phase', '0', 'Frequency', '50');
add_block('powerlib/Elements/Ground', [mdl '/GND_INF'], ...
    'Position', [700 540 740 570]);
add_line(mdl, 'AC_INF/RConn1', 'L_tie/LConn1', 'autorouting', 'smart');
add_line(mdl, 'AC_INF/LConn1', 'GND_INF/LConn1', 'autorouting', 'smart');

% Set per-agent base ws defaults (force double)
for i = 1:4
    assignin('base', sprintf('M_%d', i),      double(12.0));
    assignin('base', sprintf('D_%d', i),      double(3.0));
    assignin('base', sprintf('Pm_%d', i),     double(0.5));
    assignin('base', sprintf('delta0_%d', i), double(delta0_default));
end
assignin('base', 'wn_const',    double(wn));
assignin('base', 'Vbase_const', double(Vbase));
assignin('base', 'Sbase_const', double(Sbase));
assignin('base', 'Pe_scale',    double(0.5 / Sbase));
assignin('base', 'L_line_H',    L_line_H);
assignin('base', 'L_tie_H',     L_tie_H);

for i = 1:4
    cy = 80 + (i-1)*180;
    bx = 1000;   % column x for VSG cluster

    cvs   = sprintf('CVS_VSG%d', i);
    Lline = sprintf('L_line_%d', i);
    gnd   = sprintf('GND_%d', i);
    intW  = sprintf('IntW_%d', i);
    intD  = sprintf('IntD_%d', i);
    cosD  = sprintf('cosD_%d', i);
    sinD  = sprintf('sinD_%d', i);
    VrG   = sprintf('VrG_%d', i);
    ViG   = sprintf('ViG_%d', i);
    ri2c  = sprintf('RI2C_%d', i);

    % --- Electrical: CVS, Imeas, L_line, GND ---
    add_block('powerlib/Electrical Sources/Controlled Voltage Source', ...
        [mdl '/' cvs], 'Position', [bx cy bx+60 cy+50]);
    set_param([mdl '/' cvs], 'Source_Type', 'DC', 'Initialize', 'off', ...
        'Amplitude', num2str(Vbase), 'Phase', '0', 'Frequency', '0', ...
        'Measurements', 'None');
    add_block('powerlib/Measurements/Current Measurement', ...
        [mdl '/Imeas_' num2str(i)], 'Position', [bx+90 cy+10 bx+110 cy+40]);
    add_block('powerlib/Elements/Series RLC Branch', [mdl '/' Lline], ...
        'Position', [bx+150 cy bx+200 cy+30]);
    set_param([mdl '/' Lline], 'BranchType', 'L', 'Inductance', 'L_line_H');
    add_block('powerlib/Elements/Ground', [mdl '/' gnd], ...
        'Position', [bx cy+70 bx+40 cy+100]);
    add_block('powerlib/Measurements/Voltage Measurement', ...
        [mdl '/Vmeas_' num2str(i)], 'Position', [bx+50 cy+110 bx+110 cy+150]);

    add_line(mdl, [cvs '/RConn1'], ['Imeas_' num2str(i) '/LConn1'], 'autorouting', 'smart');
    add_line(mdl, ['Imeas_' num2str(i) '/RConn1'], [Lline '/LConn1'], 'autorouting', 'smart');
    add_line(mdl, [cvs '/LConn1'], [gnd '/LConn1'], 'autorouting', 'smart');
    add_line(mdl, [cvs '/RConn1'], ['Vmeas_' num2str(i) '/LConn1'], 'autorouting', 'smart');
    add_line(mdl, [cvs '/LConn1'], ['Vmeas_' num2str(i) '/LConn2'], 'autorouting', 'smart');

    if i <= 2
        add_line(mdl, [Lline '/RConn1'], 'L_tie/LConn1', 'autorouting', 'smart');
    else
        add_line(mdl, [Lline '/RConn1'], 'L_tie/RConn1', 'autorouting', 'smart');
    end

    % --- Pe = real(V * conj(I)) * 0.5 / Sbase ---
    add_block('simulink/Math Operations/Complex to Real-Imag', ...
        [mdl '/V_RI_' num2str(i)], 'Position', [bx+220 cy+110 bx+260 cy+150]);
    set_param([mdl '/V_RI_' num2str(i)], 'Output', 'Real and imag');
    add_line(mdl, ['Vmeas_' num2str(i) '/1'], ['V_RI_' num2str(i) '/1'], 'autorouting', 'smart');
    add_block('simulink/Math Operations/Complex to Real-Imag', ...
        [mdl '/I_RI_' num2str(i)], 'Position', [bx+220 cy+170 bx+260 cy+210]);
    set_param([mdl '/I_RI_' num2str(i)], 'Output', 'Real and imag');
    add_line(mdl, ['Imeas_' num2str(i) '/1'], ['I_RI_' num2str(i) '/1'], 'autorouting', 'smart');

    add_block('simulink/Math Operations/Product', [mdl '/VrIr_' num2str(i)], ...
        'Position', [bx+290 cy+110 bx+320 cy+135], 'Inputs', '2');
    add_line(mdl, ['V_RI_' num2str(i) '/1'], ['VrIr_' num2str(i) '/1']);
    add_line(mdl, ['I_RI_' num2str(i) '/1'], ['VrIr_' num2str(i) '/2']);
    add_block('simulink/Math Operations/Product', [mdl '/ViIi_' num2str(i)], ...
        'Position', [bx+290 cy+170 bx+320 cy+195], 'Inputs', '2');
    add_line(mdl, ['V_RI_' num2str(i) '/2'], ['ViIi_' num2str(i) '/1']);
    add_line(mdl, ['I_RI_' num2str(i) '/2'], ['ViIi_' num2str(i) '/2']);
    add_block('simulink/Math Operations/Sum', [mdl '/PSum_' num2str(i)], ...
        'Position', [bx+350 cy+140 bx+380 cy+170], 'Inputs', '++');
    add_line(mdl, ['VrIr_' num2str(i) '/1'], ['PSum_' num2str(i) '/1']);
    add_line(mdl, ['ViIi_' num2str(i) '/1'], ['PSum_' num2str(i) '/2']);
    add_block('simulink/Math Operations/Gain', [mdl '/Pe_pu_' num2str(i)], ...
        'Position', [bx+400 cy+140 bx+440 cy+170], 'Gain', 'Pe_scale');
    add_line(mdl, ['PSum_' num2str(i) '/1'], ['Pe_pu_' num2str(i) '/1']);

    % --- Swing eq ---
    add_block('simulink/Sources/Constant', [mdl '/Pm_' num2str(i) '_c'], ...
        'Position', [bx-450 cy+50 bx-410 cy+70], 'Value', sprintf('Pm_%d', i));
    add_block('simulink/Continuous/Integrator', [mdl '/' intW], ...
        'Position', [bx-200 cy+40 bx-170 cy+70], 'InitialCondition', '1');
    add_block('simulink/Sources/Constant', [mdl '/One_' num2str(i)], ...
        'Position', [bx-360 cy+10 bx-330 cy+30], 'Value', '1');
    add_block('simulink/Math Operations/Sum', [mdl '/SumDw_' num2str(i)], ...
        'Position', [bx-300 cy+40 bx-270 cy+70], 'Inputs', '+-');
    add_line(mdl, [intW '/1'], ['SumDw_' num2str(i) '/1']);
    add_line(mdl, ['One_' num2str(i) '/1'], ['SumDw_' num2str(i) '/2']);
    add_block('simulink/Math Operations/Gain', [mdl '/Dgain_' num2str(i)], ...
        'Position', [bx-300 cy+100 bx-270 cy+120], 'Gain', sprintf('D_%d', i));
    add_line(mdl, ['SumDw_' num2str(i) '/1'], ['Dgain_' num2str(i) '/1']);
    add_block('simulink/Math Operations/Sum', [mdl '/SwingSum_' num2str(i)], ...
        'Position', [bx-260 cy+50 bx-230 cy+110], 'Inputs', '+--');
    add_line(mdl, ['Pm_' num2str(i) '_c/1'], ['SwingSum_' num2str(i) '/1']);
    add_line(mdl, ['Pe_pu_' num2str(i) '/1'], ['SwingSum_' num2str(i) '/2']);
    add_line(mdl, ['Dgain_' num2str(i) '/1'], ['SwingSum_' num2str(i) '/3']);
    add_block('simulink/Math Operations/Gain', [mdl '/Mgain_' num2str(i)], ...
        'Position', [bx-225 cy+50 bx-200 cy+70], 'Gain', sprintf('1/M_%d', i));
    add_line(mdl, ['SwingSum_' num2str(i) '/1'], ['Mgain_' num2str(i) '/1']);
    add_line(mdl, ['Mgain_' num2str(i) '/1'], [intW '/1']);

    % --- delta integrator ---
    add_block('simulink/Math Operations/Gain', [mdl '/wnG_' num2str(i)], ...
        'Position', [bx-300 cy-50 bx-270 cy-25], 'Gain', 'wn_const');
    add_line(mdl, ['SumDw_' num2str(i) '/1'], ['wnG_' num2str(i) '/1']);
    add_block('simulink/Continuous/Integrator', [mdl '/' intD], ...
        'Position', [bx-200 cy-50 bx-170 cy-20], 'InitialCondition', sprintf('delta0_%d', i));
    add_line(mdl, ['wnG_' num2str(i) '/1'], [intD '/1']);

    % --- cos/sin -> RI2C -> CVS ---
    add_block('simulink/Math Operations/Trigonometric Function', ...
        [mdl '/' cosD], 'Position', [bx-100 cy-30 bx-70 cy-10], 'Operator', 'cos');
    add_block('simulink/Math Operations/Trigonometric Function', ...
        [mdl '/' sinD], 'Position', [bx-100 cy-60 bx-70 cy-40], 'Operator', 'sin');
    add_line(mdl, [intD '/1'], [cosD '/1']);
    add_line(mdl, [intD '/1'], [sinD '/1']);
    add_block('simulink/Math Operations/Gain', [mdl '/' VrG], ...
        'Position', [bx-50 cy-30 bx-20 cy-10], 'Gain', 'Vbase_const');
    add_block('simulink/Math Operations/Gain', [mdl '/' ViG], ...
        'Position', [bx-50 cy-60 bx-20 cy-40], 'Gain', 'Vbase_const');
    add_line(mdl, [cosD '/1'], [VrG '/1']);
    add_line(mdl, [sinD '/1'], [ViG '/1']);
    add_block('simulink/Math Operations/Real-Imag to Complex', ...
        [mdl '/' ri2c], 'Position', [bx-10 cy-50 bx+30 cy-15]);
    add_line(mdl, [VrG '/1'], [ri2c '/1']);
    add_line(mdl, [ViG '/1'], [ri2c '/2']);
    add_line(mdl, [ri2c '/1'], [cvs '/1']);

    % --- Loggers ---
    add_block('simulink/Sinks/To Workspace', [mdl '/W_omega_' num2str(i)], ...
        'Position', [bx-150 cy+45 bx-110 cy+60], ...
        'VariableName', sprintf('omega_ts_%d', i), 'SaveFormat', 'Timeseries');
    add_line(mdl, [intW '/1'], ['W_omega_' num2str(i) '/1']);
    add_block('simulink/Sinks/To Workspace', [mdl '/W_delta_' num2str(i)], ...
        'Position', [bx-150 cy-45 bx-110 cy-30], ...
        'VariableName', sprintf('delta_ts_%d', i), 'SaveFormat', 'Timeseries');
    add_line(mdl, [intD '/1'], ['W_delta_' num2str(i) '/1']);
    add_block('simulink/Sinks/To Workspace', [mdl '/W_Pe_' num2str(i)], ...
        'Position', [bx+450 cy+145 bx+490 cy+165], ...
        'VariableName', sprintf('Pe_ts_%d', i), 'SaveFormat', 'Timeseries');
    add_line(mdl, ['Pe_pu_' num2str(i) '/1'], ['W_Pe_' num2str(i) '/1']);
end

save_system(mdl, out_slx);
fprintf('RESULT: kundur_cvs_p2 saved at %s\n', out_slx);

end
