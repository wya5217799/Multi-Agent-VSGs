function test_ic_delta_mapping_disc()
%TEST_IC_DELTA_MAPPING_DISC  F13 pre-flight: NR IC time-domain mapping verification.
%
% Goal: prove that the time-domain interpretation of v3 NR's complex-phasor IC
% (V_emf_pu × Vbase × sqrt(2/3) × sin(ωt + δ)) gives ELECTRICALLY EQUIVALENT
% steady-state to what Phasor would. Test with non-zero δ0 (the realistic v3
% case where δ ∈ [0, 0.3] rad per source).
%
% Topology (SMIB with non-zero δ):
%   ESS source via helper (δ0 = 0.1 rad ≈ 5.73°)
%     → Three-Phase PI Section Line (50 km)
%       → Three-Phase V-I Meas
%         → Three-Phase Voltage Reference (Three-Phase Source NonIdeal at δ=0)
%
% Physics expectation (steady-state):
%   Pe = (V_emf × V_ref × sin(Δδ)) / X_total  in vsg-pu
%   where:
%     V_emf = V_ref = Vbase (1 pu)
%     Δδ = 0.1 rad (source ahead of ref)
%     X_total = X_vsg + X_line ≈ 0.30 + small ≈ 0.31 pu vsg-base
%   Pe ≈ 1·1·sin(0.1) / 0.31 = 0.0998 / 0.31 = 0.322 vsg-pu
%   Convert to sys-pu: Pe_sys = 0.322 × (200/100) = 0.644 sys-pu
%   wait Pm is in sys-pu, scale = Sbase/VSG_SN = 100/200 = 0.5
%   Pe_sys = 0.322 × scale_inv = 0.322 / (1/0.5) = 0.322 × 2 ... no
%
%   Re-derive cleanly:
%     - Pe in vsg-pu (vsg-base 200 MVA): Pe_vsg = V² × sin(δ) / X_vsg_pu
%     - X_vsg_pu = 0.30 (vsg-base)
%     - Pe_vsg ≈ 1 × sin(0.1) / 0.30 = 0.333 vsg-pu
%     - In MW: Pe = 0.333 × 200 = 66.5 MW
%     - In sys-pu (sys-base 100 MVA): Pe_sys = 66.5 / 100 = 0.665 sys-pu
%
% For ω to settle at 1.0, Pm_sys must match Pe_sys:
%   Pm_sys = 0.665 (target)
%
% Acceptance:
%   P0.1 Compile passes
%   P0.2 Sim passes (5s)
%   P0.3 ω settle to 1.0 ± 0.001 (proves IC is electrically valid)
%   P0.4 Pe ≈ Pm_sys within 5% (proves time-domain mapping correct)

mdl = 'test_ic_delta_mapping';
out_dir = fileparts(mfilename('fullpath'));

% ---- Params ----
fn = 50; wn = 2*pi*fn;
Sbase = 100e6;
Vbase = 230e3;
VSG_SN = 200e6;

% Non-zero δ0
delta0_rad = 0.10;        % 5.73°
V_emf_pu  = 1.00;         % 1 pu vsg-base
X_vsg_pu_vsgbase = 0.30;  % v3 spec

% Predicted Pe
Pe_vsg = V_emf_pu^2 * sin(delta0_rad) / X_vsg_pu_vsgbase;     % vsg-pu
Pe_sys_predicted = Pe_vsg * (VSG_SN / Sbase);
Pm_sys_target = Pe_sys_predicted;   % set Pm = predicted Pe → ω settles at 1

fprintf('RESULT: ===== F13: IC δ Mapping Test =====\n');
fprintf('RESULT: δ0 = %.4f rad (%.2f°), V_emf = %.3f pu_vsg\n', ...
    delta0_rad, rad2deg(delta0_rad), V_emf_pu);
fprintf('RESULT: predicted Pe_vsg = %.4f, Pe_sys = %.4f, Pm_sys_target = %.4f\n', ...
    Pe_vsg, Pe_sys_predicted, Pm_sys_target);

% ---- Reset ----
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
load_system('powerlib');
load_system('sps_lib');

% ---- Workspace ----
assignin('base', 'wn_const', double(wn));
assignin('base', 'Vbase_const', double(Vbase));
assignin('base', 'Sbase_const', double(Sbase));
assignin('base', 'Pe_scale', double(1.0/Sbase));
assignin('base', 'M_201', 24.0);
assignin('base', 'D_201', 4.5);
assignin('base', 'Pm_201', double(Pm_sys_target));
assignin('base', 'delta0_201', double(delta0_rad));
assignin('base', 'Vmag_201', double(V_emf_pu * Vbase));
assignin('base', 'VSGScale_201', double(Sbase / VSG_SN));
assignin('base', 'Pm_step_t_201', 100.0);
assignin('base', 'Pm_step_amp_201', 0.0);

% ---- powergui Discrete + solver ----
add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
set_param([mdl '/powergui'], 'SimulationMode', 'Discrete', 'SampleTime', '50e-6');
set_param(mdl, 'StopTime', '5', 'SolverType', 'Fixed-step', ...
    'Solver', 'FixedStepAuto', 'FixedStep', '50e-6');

add_block('built-in/Clock', [mdl '/Clock_global'], 'Position', [20 80 50 100]);

% ---- 1 ESS via helper (with δ0 = 0.1) ----
addpath('C:/Users/27443/Desktop/Multi-Agent-VSGs-discrete/scenarios/kundur/simulink_models');
params = struct('fn', fn, 'wn', wn, 'Vbase', Vbase, 'Sbase', Sbase);
src.name = 'ES201';
src.bus = 0;
src.stype = 'ess';
src.M_var = 'M_201';
src.D_var = 'D_201';
src.Pm_var = 'Pm_201';
src.delta0_var = 'delta0_201';
src.Vmag_var = 'Vmag_201';
src.scale_var = 'VSGScale_201';
src.Rdrop_var = '';
src.Lint_H = X_vsg_pu_vsgbase * (Vbase^2/VSG_SN) / wn;
src.step_t_var = 'Pm_step_t_201';
src.step_amp_var = 'Pm_step_amp_201';

geom.bx = 600;
geom.cy = 300;
geom.global_clock = 'Clock_global';
geom.bus_anchor = '';
build_dynamic_source_discrete(mdl, src, geom, params);

% ---- 3-phase Π line (short) connecting ESS VImeas to reference ----
% Use minimal line so we can compare directly to predicted Pe (X_vsg dominant)
% NOTE: line adds shunt C per end; small but nonzero. Keep length=1km.
R_3p = [0.053, 3*0.053];
L_3p = [1.41e-3, 3*1.41e-3];
C_3p = [0.009e-6, 0.6*0.009e-6];

pi_path = sprintf('sps_lib/Power Grid Elements/Three-Phase\nPI Section Line');
add_block(pi_path, [mdl '/Line'], 'Position', [950 250 1030 350]);
set_param([mdl '/Line'], 'Length', '1', 'Frequency', num2str(fn), ...
    'Resistances', mat2str(R_3p), 'Inductances', mat2str(L_3p), ...
    'Capacitances', mat2str(C_3p));

add_line(mdl, 'VImeas_ES201/RConn1', 'Line/LConn1', 'autorouting', 'smart');
add_line(mdl, 'VImeas_ES201/RConn2', 'Line/LConn2', 'autorouting', 'smart');
add_line(mdl, 'VImeas_ES201/RConn3', 'Line/LConn3', 'autorouting', 'smart');

% ---- Three-Phase Source as voltage reference (NonIdeal Yg, δ_ref = 0) ----
add_block('sps_lib/Sources/Three-Phase Source', [mdl '/Vref'], ...
    'Position', [1100 250 1180 350]);
set_param([mdl '/Vref'], ...
    'InternalConnection', 'Yg', ...
    'Voltage', num2str(Vbase), ...
    'PhaseAngle', '0', ...
    'Frequency', num2str(fn), ...
    'NonIdealSource', 'on', ...
    'SpecifyImpedance', 'on', ...
    'ShortCircuitLevel', '100000e6', ...   % very stiff (~infinite bus)
    'BaseVoltage', num2str(Vbase), 'XRratio', '7');

add_line(mdl, 'Line/RConn1', 'Vref/RConn1', 'autorouting', 'smart');
add_line(mdl, 'Line/RConn2', 'Vref/RConn2', 'autorouting', 'smart');
add_line(mdl, 'Line/RConn3', 'Vref/RConn3', 'autorouting', 'smart');

% ---- Override loggers ----
set_param([mdl '/W_omega_ES201'], 'MaxDataPoints', 'inf');
set_param([mdl '/W_Pe_ES201'], 'MaxDataPoints', 'inf');
set_param([mdl '/W_delta_ES201'], 'MaxDataPoints', 'inf');

% ---- Save + compile + sim ----
out_slx = fullfile(out_dir, [mdl '.slx']);
save_system(mdl, out_slx);

try
    set_param(mdl, 'SimulationCommand', 'update');
    fprintf('RESULT: P0.1 compile PASS\n');
catch ME
    fprintf('RESULT: P0.1 FAIL: %s\nVERDICT=FAIL_COMPILE\n', ME.message);
    return;
end

t0 = tic;
try
    out = sim(mdl, 'StopTime', '5');
    fprintf('RESULT: P0.2 sim PASS, wall=%.2fs\n', toc(t0));
catch ME
    fprintf('RESULT: P0.2 FAIL: %s\nVERDICT=FAIL_SIM\n', ME.message);
    return;
end

% ---- Read & verify ----
omega = out.get('omega_ts_201');
Pe = out.get('Pe_ts_201');
delta = out.get('delta_ts_201');

t = omega.Time;
mask = t > 4.0;
od = omega.Data(mask);
pd = Pe.Data(mask);
dd = delta.Data(mask);

mean_o = mean(od);
mean_p = mean(pd);
mean_d = mean(dd);

fprintf('RESULT: late ω mean=%.6f std=%.8f\n', mean_o, std(od));
fprintf('RESULT: late Pe mean=%.4f sys-pu (predicted=%.4f)\n', mean_p, Pe_sys_predicted);
fprintf('RESULT: late δ mean=%.4f rad (IC=%.4f, Δ=%.5f)\n', mean_d, delta0_rad, mean_d-delta0_rad);

p3 = abs(mean_o - 1.0) < 0.001;
p4 = abs(mean_p - Pe_sys_predicted) < 0.05 * abs(Pe_sys_predicted);

fprintf('RESULT: P0.3 ω=1: %s (dev=%.6f)\n', ternary(p3, 'PASS', 'FAIL'), abs(mean_o-1.0));
fprintf('RESULT: P0.4 Pe match: %s (err=%.1f%%)\n', ternary(p4, 'PASS', 'FAIL'), ...
    100 * abs(mean_p - Pe_sys_predicted) / abs(Pe_sys_predicted));

if p3 && p4
    fprintf('RESULT: VERDICT=PASS — IC δ time-domain mapping electrically equivalent\n');
else
    fprintf('RESULT: VERDICT=FAIL — diagnose above\n');
end

end

function s = ternary(cond, a, b)
if cond, s = a; else, s = b; end
end
