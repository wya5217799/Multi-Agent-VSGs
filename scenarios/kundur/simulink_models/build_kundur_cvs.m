function build_kundur_cvs()
% build_kundur_cvs  Stage 2 D2 — full 7-bus Kundur CVS Phasor model
% with per-VSG swing-equation closure, fed by NR initial condition.
%
% Topology (unchanged from D1, see Stage 2 Day 1 verdict):
%   7 buses : Bus_V1..V4 (driven CVS terminals), Bus_A, Bus_B (junctions
%             with constant-impedance load), Bus_INF (AC Voltage Source).
%   Branches : L_v_1..4 (X=0.10 pu), L_tie (0.30 pu), L_inf (0.05 pu).
%   Loads    : Load_A, Load_B (R-only, Y-shunt model in NR).
%
% New in D2 (vs D1 structural-only build):
%   - Reads kundur_ic_cvs.json (Newton-Raphson initial condition) for
%     delta0_i / V_mag_i / Pm0_i. Hand-calc is forbidden in P4 by plan §3.
%   - Adds per-VSG swing equation closure (IntW + IntD + cos/sin + RI2C),
%     wired to a Pe measurement (V·conj(I)·0.5/Sbase pu) at each terminal.
%   - To-workspace loggers omega_ts_i / delta_ts_i / Pe_ts_i (Timeseries).
%   - Per-agent base-ws variables M_i / D_i / Pm_i / delta0_i / Vmag_i
%     so that downstream resets / D3+ gates can mutate them per episode.
%
% Engineering contracts honored (cvs_design.md):
%   H1 driven CVS  : Source_Type=DC, Initialize=off, Measurements=None
%   H2 CVS input   : RI2C(double, double) — uniform across all 4 VSGs
%   H3 inf-bus     : powerlib AC Voltage Source (no inport)
%   H4 solver      : powergui Phasor 50 Hz, ode23t variable, MaxStep=0.005
%   H5 base ws     : every numeric forced to double()
%   D-CVS-9/10/11  : DC + Initialize=off ; AC src for inf-bus ; double types
%
% NOT in scope for D2:
%   - Disturbance injection (D4/Gate 2)
%   - 30 s zero-action stability (D3/Gate 1)
%   - SAC / RL training (Gate 3)

mdl = 'kundur_cvs';
out_dir   = fileparts(mfilename('fullpath'));
out_slx   = fullfile(out_dir, [mdl '.slx']);
ic_path   = fullfile(fileparts(out_dir), 'kundur_ic_cvs.json');

% ---- Read NR initial condition (plan §3: hand-calc forbidden after D1) ----
ic_text = fileread(ic_path);
ic = jsondecode(ic_text);
delta0_rad = double(ic.vsg_internal_emf_angle_rad(:));
v_mag_pu   = double(ic.vsg_terminal_voltage_mag_pu(:));
Pm0_pu     = double(ic.vsg_pm0_pu(:));
assert(numel(delta0_rad) == 4, 'kundur_ic_cvs.json must have 4 VSG entries');
assert(ic.powerflow.converged, 'kundur_ic_cvs.json reports NR did not converge');

% ---- Physical parameters (force double per H5) ----
fn       = 50;
wn       = double(2*pi*fn);
Sbase    = double(100e6);
Vbase    = double(230e3);
Zbase    = double(Vbase^2 / Sbase);

X_v_pu   = 0.10;
X_tie_pu = 0.30;
X_inf_pu = 0.05;

L_v_H    = double(X_v_pu   * Zbase / wn);
L_tie_H  = double(X_tie_pu * Zbase / wn);
L_inf_H  = double(X_inf_pu * Zbase / wn);

% ---- Constant-impedance loads (R-only, single-phase phasor) ----
P_loadA_pu = 0.4;
P_loadB_pu = 0.4;
R_loadA = double(Vbase^2 / (P_loadA_pu * Sbase));   % Ohm
R_loadB = double(Vbase^2 / (P_loadB_pu * Sbase));   % Ohm

% ---- VSG defaults ----
% Project paper-baseline (per D4.2 audit + plan-author decision 2026-04-26):
%   H_ES0 = 24, D_ES0 = 18  (config.py L32-33; modal calibration target
%   omega_n ~ 0.6 Hz, zeta ~ 0.048 in the ANDES reduced-network model).
%   With M = 2*H/omega_s and omega_s = 1 pu, M_pu = 2*H_pu = 48; here we use
%   M0_default = 24 (i.e. M ~ H in the project's pu convention, matching the
%   ANDES/ODE/Simulink-fallback path env/simulink/simulink_vsg_env.py L54-55).
% Note: paper Yang TPWRS 2023 does NOT specify a numeric D0 or H0 baseline.
%   The 24 / 18 pair is a project-side modal calibration target, not a paper
%   value. The pre-D4.2 spike artefact (M0=12, D0=3 from build_kundur_cvs_p2.m
%   / cvs_design.md D-CVS-6) gave zeta ~ 0.0077 — extreme under-damping that
%   blocked any Gate 2 settle target. See:
%     quality_reports/gates/2026-04-26_kundur_cvs_p4_d4p2_readonly_audit.md
M0_default = 24.0;
D0_default = 18.0;

% ---- Reset model ----
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
load_system('powerlib');

% ---- powergui Phasor (H4) ----
add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
set_param([mdl '/powergui'], 'SimulationMode', 'Phasor', 'frequency', '50');
set_param(mdl, 'StopTime', '0.5', 'SolverType', 'Variable-step', ...
    'Solver', 'ode23t', 'MaxStep', '0.005');

% ---- Per-VSG and shared base-ws scalars (H5: every value double) ----
for i = 1:4
    assignin('base', sprintf('M_%d',      i), double(M0_default));
    assignin('base', sprintf('D_%d',      i), double(D0_default));
    assignin('base', sprintf('Pm_%d',     i), double(Pm0_pu(i)));
    assignin('base', sprintf('delta0_%d', i), double(delta0_rad(i)));
    assignin('base', sprintf('Vmag_%d',   i), double(v_mag_pu(i) * Vbase));
    % D4 disturbance gating (FR-tunable Constant path; default = no step):
    %   Pm_step_t_i:   step time (s)        — Constant block driving Relational Operator
    %   Pm_step_amp_i: step amplitude (pu)  — Constant block multiplied by step indicator
    % Default amp = 0 → indicator irrelevant, no perturbation; equivalent to D3.
    assignin('base', sprintf('Pm_step_t_%d',   i), double(5.0));
    assignin('base', sprintf('Pm_step_amp_%d', i), double(0.0));
end
assignin('base', 'wn_const',    double(wn));
assignin('base', 'Vbase_const', double(Vbase));
assignin('base', 'Sbase_const', double(Sbase));
% Pe_scale: in our pu convention NR computes P_pu = V_pu·conj(I_pu) directly
% (no 0.5 factor). To match this, sim's Pe formula divides by Sbase only —
% NOT by 2*Sbase. Verified by analytic NR-IC consistency (D2): with
% Pe_scale=0.5/Sbase, sim's Pe_t0 = 0.25 pu while NR's P_inj = 0.5 pu (factor
% 2 off, breaking the IC). With Pe_scale=1.0/Sbase, sim's Pe_t0 matches NR.
% (P2's `0.5/Sbase` was a separate convention that worked only because the
% closed swing-eq self-corrected δ to a different equilibrium — it produces
% larger |δ|max than NR predicts and is not suitable as a verified IC.)
assignin('base', 'Pe_scale',    double(1.0 / Sbase));
assignin('base', 'L_v_H',       double(L_v_H));
assignin('base', 'L_tie_H',     double(L_tie_H));
assignin('base', 'L_inf_H',     double(L_inf_H));
assignin('base', 'R_loadA',     double(R_loadA));
assignin('base', 'R_loadB',     double(R_loadB));

% ---- Inter-area tie + anchor link ----
add_block('powerlib/Elements/Series RLC Branch', [mdl '/L_tie'], ...
    'Position', [780 360 840 410]);
set_param([mdl '/L_tie'], 'BranchType', 'L', 'Inductance', 'L_tie_H');

add_block('powerlib/Elements/Series RLC Branch', [mdl '/L_inf'], ...
    'Position', [900 360 960 410]);
set_param([mdl '/L_inf'], 'BranchType', 'L', 'Inductance', 'L_inf_H');

% ---- Bus_INF (AC Voltage Source per D-CVS-10) ----
add_block('powerlib/Electrical Sources/AC Voltage Source', ...
    [mdl '/AC_INF'], 'Position', [1020 360 1080 410]);
set_param([mdl '/AC_INF'], 'Amplitude', num2str(Vbase), ...
    'Phase', '0', 'Frequency', '50');
add_block('powerlib/Elements/Ground', [mdl '/GND_INF'], ...
    'Position', [1020 440 1060 470]);
add_line(mdl, 'AC_INF/RConn1', 'L_inf/RConn1', 'autorouting', 'smart');
add_line(mdl, 'AC_INF/LConn1', 'GND_INF/LConn1', 'autorouting', 'smart');

% ---- L_tie/RConn1 (= Bus_B node) ↔ L_inf/LConn1 ----
add_line(mdl, 'L_tie/RConn1', 'L_inf/LConn1', 'autorouting', 'smart');

% ---- Load_A on Bus_A ----
add_block('powerlib/Elements/Series RLC Branch', [mdl '/Load_A'], ...
    'Position', [700 460 760 510]);
set_param([mdl '/Load_A'], 'BranchType', 'R', 'Resistance', 'R_loadA');
add_block('powerlib/Elements/Ground', [mdl '/GND_LA'], ...
    'Position', [700 530 740 560]);
add_line(mdl, 'Load_A/RConn1', 'GND_LA/LConn1', 'autorouting', 'smart');
add_line(mdl, 'L_tie/LConn1',  'Load_A/LConn1', 'autorouting', 'smart');

% ---- Load_B on Bus_B ----
add_block('powerlib/Elements/Series RLC Branch', [mdl '/Load_B'], ...
    'Position', [880 460 940 510]);
set_param([mdl '/Load_B'], 'BranchType', 'R', 'Resistance', 'R_loadB');
add_block('powerlib/Elements/Ground', [mdl '/GND_LB'], ...
    'Position', [880 530 920 560]);
add_line(mdl, 'Load_B/RConn1', 'GND_LB/LConn1', 'autorouting', 'smart');
add_line(mdl, 'L_tie/RConn1',  'Load_B/LConn1', 'autorouting', 'smart');

% ---- Global clock for D4 disturbance step indicator (FR-tunable path) ----
% Plan §2 E5: disturbance via base-ws Constant + comparator, NOT TripLoad.
% 4 VSGs share one Clock; each VSG owns its (Pm_step_t_i, Pm_step_amp_i) consts.
add_block('simulink/Sources/Clock', [mdl '/Clock_global'], ...
    'Position', [200 700 230 730], 'DisplayTime', 'off');

% ---- 4 driven CVS clusters with full swing-equation closure ----
% Layout per VSG:
%   row i, cy = 80 + (i-1)*180
%   bx = 1000 (CVS column anchor)
%   left of bx: swing-eq + cos/sin/RI2C
%   right of bx: Imeas + L_v + Vmeas + Pe (V*conj(I))
for i = 1:4
    cy = 80 + (i-1)*180;
    bx = 1000;

    cvs   = sprintf('CVS_VSG%d', i);
    Lv    = sprintf('L_v_%d', i);
    gnd   = sprintf('GND_VSG%d', i);
    intW  = sprintf('IntW_%d', i);
    intD  = sprintf('IntD_%d', i);
    cosD  = sprintf('cosD_%d', i);
    sinD  = sprintf('sinD_%d', i);
    VrG   = sprintf('VrG_%d', i);
    ViG   = sprintf('ViG_%d', i);
    ri2c  = sprintf('RI2C_%d', i);

    % --- Electrical: CVS, Imeas, L_v, GND, Vmeas ---
    add_block('powerlib/Electrical Sources/Controlled Voltage Source', ...
        [mdl '/' cvs], 'Position', [bx cy bx+60 cy+50]);
    set_param([mdl '/' cvs], ...
        'Source_Type', 'DC', 'Initialize', 'off', ...
        'Amplitude', num2str(Vbase), 'Phase', '0', 'Frequency', '0', ...
        'Measurements', 'None');

    add_block('powerlib/Measurements/Current Measurement', ...
        [mdl '/Imeas_' num2str(i)], 'Position', [bx+90 cy+10 bx+110 cy+40]);

    add_block('powerlib/Elements/Series RLC Branch', [mdl '/' Lv], ...
        'Position', [bx+150 cy bx+200 cy+30]);
    set_param([mdl '/' Lv], 'BranchType', 'L', 'Inductance', 'L_v_H');

    add_block('powerlib/Elements/Ground', [mdl '/' gnd], ...
        'Position', [bx cy+70 bx+40 cy+100]);

    add_block('powerlib/Measurements/Voltage Measurement', ...
        [mdl '/Vmeas_' num2str(i)], 'Position', [bx+50 cy+110 bx+110 cy+150]);

    add_line(mdl, [cvs '/RConn1'],            ['Imeas_' num2str(i) '/LConn1'], 'autorouting', 'smart');
    add_line(mdl, ['Imeas_' num2str(i) '/RConn1'], [Lv '/LConn1'],              'autorouting', 'smart');
    add_line(mdl, [cvs '/LConn1'],            [gnd '/LConn1'],                  'autorouting', 'smart');
    add_line(mdl, [cvs '/RConn1'],            ['Vmeas_' num2str(i) '/LConn1'], 'autorouting', 'smart');
    add_line(mdl, [cvs '/LConn1'],            ['Vmeas_' num2str(i) '/LConn2'], 'autorouting', 'smart');

    % VSG1, VSG2 -> Bus_A; VSG3, VSG4 -> Bus_B
    if i <= 2
        add_line(mdl, [Lv '/RConn1'], 'L_tie/LConn1', 'autorouting', 'smart');
    else
        add_line(mdl, [Lv '/RConn1'], 'L_tie/RConn1', 'autorouting', 'smart');
    end

    % --- Pe = Re(V * conj(I)) * 0.5 / Sbase  (single-phase peak phasor) ---
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

    % --- Pm step gating (FR-tunable path; D4 Gate 2 disturbance) ---
    % step_pulse_i(t) = (t >= Pm_step_t_i ? 1 : 0) * Pm_step_amp_i
    % Pm_total_i      = Pm_i_c + step_pulse_i
    add_block('simulink/Sources/Constant', [mdl '/Pm_step_t_c_' num2str(i)], ...
        'Position', [bx-560 cy+130 bx-520 cy+150], ...
        'Value', sprintf('Pm_step_t_%d', i));
    add_block('simulink/Logic and Bit Operations/Relational Operator', ...
        [mdl '/GE_' num2str(i)], ...
        'Position', [bx-500 cy+115 bx-470 cy+145], 'Operator', '>=');
    add_line(mdl, 'Clock_global/1',                    ['GE_' num2str(i) '/1']);
    add_line(mdl, ['Pm_step_t_c_' num2str(i) '/1'],    ['GE_' num2str(i) '/2']);

    add_block('simulink/Signal Attributes/Data Type Conversion', ...
        [mdl '/Cast_' num2str(i)], ...
        'Position', [bx-460 cy+115 bx-430 cy+140], 'OutDataTypeStr', 'double');
    add_line(mdl, ['GE_' num2str(i) '/1'], ['Cast_' num2str(i) '/1']);

    add_block('simulink/Sources/Constant', [mdl '/Pm_step_amp_c_' num2str(i)], ...
        'Position', [bx-460 cy+155 bx-420 cy+175], ...
        'Value', sprintf('Pm_step_amp_%d', i));

    add_block('simulink/Math Operations/Product', [mdl '/PmStepMul_' num2str(i)], ...
        'Position', [bx-410 cy+125 bx-385 cy+150], 'Inputs', '2');
    add_line(mdl, ['Cast_' num2str(i) '/1'],            ['PmStepMul_' num2str(i) '/1']);
    add_line(mdl, ['Pm_step_amp_c_' num2str(i) '/1'],   ['PmStepMul_' num2str(i) '/2']);

    % --- Swing equation: dω/dt = (Pm_total - Pe - D*(ω-1)) / M ---
    add_block('simulink/Sources/Constant', [mdl '/Pm_' num2str(i) '_c'], ...
        'Position', [bx-450 cy+50 bx-410 cy+70], 'Value', sprintf('Pm_%d', i));
    add_block('simulink/Math Operations/Sum', [mdl '/PmTotal_' num2str(i)], ...
        'Position', [bx-380 cy+70 bx-350 cy+100], 'Inputs', '++');
    add_line(mdl, ['Pm_' num2str(i) '_c/1'],     ['PmTotal_' num2str(i) '/1']);
    add_line(mdl, ['PmStepMul_' num2str(i) '/1'], ['PmTotal_' num2str(i) '/2']);

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
    add_line(mdl, ['PmTotal_' num2str(i) '/1'], ['SwingSum_' num2str(i) '/1']);
    add_line(mdl, ['Pe_pu_' num2str(i) '/1'],   ['SwingSum_' num2str(i) '/2']);
    add_line(mdl, ['Dgain_' num2str(i) '/1'],   ['SwingSum_' num2str(i) '/3']);

    add_block('simulink/Math Operations/Gain', [mdl '/Mgain_' num2str(i)], ...
        'Position', [bx-225 cy+50 bx-200 cy+70], 'Gain', sprintf('1/M_%d', i));
    add_line(mdl, ['SwingSum_' num2str(i) '/1'], ['Mgain_' num2str(i) '/1']);
    add_line(mdl, ['Mgain_' num2str(i) '/1'],    [intW '/1']);

    % --- delta integrator: dδ/dt = wn*(ω-1) ---
    add_block('simulink/Math Operations/Gain', [mdl '/wnG_' num2str(i)], ...
        'Position', [bx-300 cy-50 bx-270 cy-25], 'Gain', 'wn_const');
    add_line(mdl, ['SumDw_' num2str(i) '/1'], ['wnG_' num2str(i) '/1']);

    add_block('simulink/Continuous/Integrator', [mdl '/' intD], ...
        'Position', [bx-200 cy-50 bx-170 cy-20], ...
        'InitialCondition', sprintf('delta0_%d', i));
    add_line(mdl, ['wnG_' num2str(i) '/1'], [intD '/1']);

    % --- cos/sin -> V_mag scaling -> RI2C -> CVS ---
    add_block('simulink/Math Operations/Trigonometric Function', ...
        [mdl '/' cosD], 'Position', [bx-100 cy-30 bx-70 cy-10], 'Operator', 'cos');
    add_block('simulink/Math Operations/Trigonometric Function', ...
        [mdl '/' sinD], 'Position', [bx-100 cy-60 bx-70 cy-40], 'Operator', 'sin');
    add_line(mdl, [intD '/1'], [cosD '/1']);
    add_line(mdl, [intD '/1'], [sinD '/1']);

    add_block('simulink/Math Operations/Gain', [mdl '/' VrG], ...
        'Position', [bx-50 cy-30 bx-20 cy-10], 'Gain', sprintf('Vmag_%d', i));
    add_block('simulink/Math Operations/Gain', [mdl '/' ViG], ...
        'Position', [bx-50 cy-60 bx-20 cy-40], 'Gain', sprintf('Vmag_%d', i));
    add_line(mdl, [cosD '/1'], [VrG '/1']);
    add_line(mdl, [sinD '/1'], [ViG '/1']);

    add_block('simulink/Math Operations/Real-Imag to Complex', ...
        [mdl '/' ri2c], 'Position', [bx-10 cy-50 bx+30 cy-15]);
    add_line(mdl, [VrG '/1'], [ri2c '/1']);
    add_line(mdl, [ViG '/1'], [ri2c '/2']);
    add_line(mdl, [ri2c '/1'], [cvs '/1']);

    % --- ToWorkspace loggers ---
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

% ---- Save ----
save_system(mdl, out_slx);

fprintf('RESULT: kundur_cvs.slx saved at %s\n', out_slx);
fprintf('RESULT: 7-bus topology + 4 swing-eq closures (D2)\n');
fprintf('RESULT: NR IC delta0 (rad) = [%.4f %.4f %.4f %.4f]\n', delta0_rad);
fprintf('RESULT: NR IC Pm0   (pu)  = [%.4f %.4f %.4f %.4f]\n', Pm0_pu);
fprintf('RESULT: NR IC Vmag  (pu)  = [%.4f %.4f %.4f %.4f]\n', v_mag_pu);

end
