function test_multisrc_coupling_disc()
%TEST_MULTISRC_COUPLING_DISC  F12 pre-flight: multi-source coupling in Discrete.
%
% Goal: prove that 2 swing-eq sources sharing a network bus DON'T
% spontaneously oscillate or diverge. SMIB Phase 0 only tested 1 source;
% v3 has 7 sources sharing 16-bus network. This catches the simplest
% failure mode of multi-source instability.
%
% Topology (2-source minimal network):
%
%   ESS_A (helper) → Three-Phase PI Line A → Bus
%   ESS_B (helper) → Three-Phase PI Line B → Bus
%   Bus → Three-Phase Series RLC Load (80 MW = 40 from each)
%
% Both sources have:
%   M=24, D=4.5, Pm=0.2 vsg-pu (40 MW @ 200 MVA)
%   Same V_emf (230 kV), same delta0 (0)
%
% Expected steady state:
%   Both omega = 1.0 (Pm = Pe at each source)
%   Pe per source ≈ 40 MW
%
% Acceptance:
%   P0.1 Compile passes
%   P0.2 Sim passes (5s, no instability)
%   P0.3 Both omega in 1.0 ± 0.001 over last 1s
%   P0.4 Both Pe ≈ Pm at steady state (within 5%)
%   P0.5 Sources don't anti-phase (omega_A and omega_B same to within 1e-4)

mdl = 'test_multisrc_coupling';
out_dir = fileparts(mfilename('fullpath'));

% ---- Global params ----
fn = 50;
wn = 2*pi*fn;
Sbase = 100e6;
Vbase = 230e3;
VSG_SN = 200e6;
P_load_total = 80e6;   % 80 MW total = 40 from each ESS at IC

R_std_perkm = 0.053;
L_std_perkm = 1.41e-3;
C_std_perkm = 0.009e-6;
line_len_km = 50;       % shorter than F11 (each source closer to bus)

R_3p = [R_std_perkm, 3 * R_std_perkm];
L_3p = [L_std_perkm, 3 * L_std_perkm];
C_3p = [C_std_perkm, 0.6 * C_std_perkm];

fprintf('RESULT: ===== F12: Multi-source Coupling Discrete =====\n');

% ---- Reset ----
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
load_system('powerlib');
load_system('sps_lib');

% ---- powergui Discrete + solver ----
add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
set_param([mdl '/powergui'], 'SimulationMode', 'Discrete', 'SampleTime', '50e-6');
set_param(mdl, 'StopTime', '5', 'SolverType', 'Fixed-step', ...
    'Solver', 'FixedStepAuto', 'FixedStep', '50e-6');

% ---- Global Clock (helper expects this) ----
add_block('built-in/Clock', [mdl '/Clock_global'], 'Position', [20 80 50 100]);

% ---- Workspace vars per source ----
% ESS_A (named ES101 to avoid v3 ESS clash)
assignin('base', 'wn_const',    double(wn));
assignin('base', 'Vbase_const', double(Vbase));
assignin('base', 'Sbase_const', double(Sbase));
assignin('base', 'Pe_scale',    double(1.0 / Sbase));

for src_id = {'ES101', 'ES102'}
    s = src_id{1};
    assignin('base', sprintf('M_%s', s), 24.0);
    assignin('base', sprintf('D_%s', s), 4.5);
    assignin('base', sprintf('Pm_%s', s), 0.4);     % sys-pu = 40 MW
    assignin('base', sprintf('delta0_%s', s), 0.0);
    assignin('base', sprintf('Vmag_%s', s), double(Vbase));
    assignin('base', sprintf('VSGScale_%s', s), double(Sbase / VSG_SN));
    assignin('base', sprintf('Pm_step_t_%s', s), 100.0);   % no step
    assignin('base', sprintf('Pm_step_amp_%s', s), 0.0);
end

addpath('C:/Users/27443/Desktop/Multi-Agent-VSGs-discrete/scenarios/kundur/simulink_models');

% ---- Build 2 ESS sources via helper ----
params = struct('fn', fn, 'wn', wn, 'Vbase', Vbase, 'Sbase', Sbase);

src_specs = {
    % name, bx, cy
    'ES101', 600, 200;
    'ES102', 600, 600;
};

for k = 1:size(src_specs, 1)
    src.name        = src_specs{k, 1};
    src.bus         = 0;   % unused in this minimal test
    src.stype       = 'ess';
    src.M_var       = sprintf('M_%s', src.name);
    src.D_var       = sprintf('D_%s', src.name);
    src.Pm_var      = sprintf('Pm_%s', src.name);
    src.delta0_var  = sprintf('delta0_%s', src.name);
    src.Vmag_var    = sprintf('Vmag_%s', src.name);
    src.scale_var   = sprintf('VSGScale_%s', src.name);
    src.Rdrop_var   = '';
    src.Lint_H      = 0.30 * (Vbase^2/VSG_SN) / wn;
    src.step_t_var  = sprintf('Pm_step_t_%s', src.name);
    src.step_amp_var = sprintf('Pm_step_amp_%s', src.name);

    geom.bx = src_specs{k, 2};
    geom.cy = src_specs{k, 3};
    geom.global_clock = 'Clock_global';
    geom.bus_anchor = '';

    build_dynamic_source_discrete(mdl, src, geom, params);
end

% ---- 3-phase Π line A (ES101 → Bus) ----
% Source has Zvsg per-phase RL between CVS and VImeas; line then connects VImeas to bus.
% We connect ES101 VImeas RConn1/2/3 → Π Line A LConn1/2/3 → bus
pi_path = sprintf('sps_lib/Power Grid Elements/Three-Phase\nPI Section Line');
add_block(pi_path, [mdl '/Line_A'], 'Position', [950 150 1030 250]);
set_param([mdl '/Line_A'], 'Length', num2str(line_len_km), 'Frequency', num2str(fn), ...
    'Resistances', mat2str(R_3p), 'Inductances', mat2str(L_3p), ...
    'Capacitances', mat2str(C_3p));

add_line(mdl, 'VImeas_ES101/RConn1', 'Line_A/LConn1', 'autorouting', 'smart');
add_line(mdl, 'VImeas_ES101/RConn2', 'Line_A/LConn2', 'autorouting', 'smart');
add_line(mdl, 'VImeas_ES101/RConn3', 'Line_A/LConn3', 'autorouting', 'smart');

% ---- 3-phase Π line B (ES102 → Bus) ----
add_block(pi_path, [mdl '/Line_B'], 'Position', [950 550 1030 650]);
set_param([mdl '/Line_B'], 'Length', num2str(line_len_km), 'Frequency', num2str(fn), ...
    'Resistances', mat2str(R_3p), 'Inductances', mat2str(L_3p), ...
    'Capacitances', mat2str(C_3p));

add_line(mdl, 'VImeas_ES102/RConn1', 'Line_B/LConn1', 'autorouting', 'smart');
add_line(mdl, 'VImeas_ES102/RConn2', 'Line_B/LConn2', 'autorouting', 'smart');
add_line(mdl, 'VImeas_ES102/RConn3', 'Line_B/LConn3', 'autorouting', 'smart');

% ---- Common Load (Y-grounded, 80 MW total) ----
load_path = sprintf('sps_lib/Passives/Three-Phase\nSeries RLC Load');
add_block(load_path, [mdl '/Load'], 'Position', [1100 350 1180 450]);
set_param([mdl '/Load'], ...
    'Configuration', 'Y (grounded)', ...
    'NominalVoltage', num2str(Vbase), 'NominalFrequency', num2str(fn), ...
    'ActivePower', num2str(P_load_total), ...
    'InductivePower', '0', 'CapacitivePower', '0');

% Tie Line_A RConn + Line_B RConn + Load LConn (per phase)
% Phase A bus
add_line(mdl, 'Line_A/RConn1', 'Load/LConn1', 'autorouting', 'smart');
add_line(mdl, 'Line_B/RConn1', 'Load/LConn1', 'autorouting', 'smart');
add_line(mdl, 'Line_A/RConn2', 'Load/LConn2', 'autorouting', 'smart');
add_line(mdl, 'Line_B/RConn2', 'Load/LConn2', 'autorouting', 'smart');
add_line(mdl, 'Line_A/RConn3', 'Load/LConn3', 'autorouting', 'smart');
add_line(mdl, 'Line_B/RConn3', 'Load/LConn3', 'autorouting', 'smart');

% ---- Override MaxDataPoints on loggers BEFORE sim ----
% Helper writes to omega_ts_<idx> with int idx for ESS, but src.name='ES101'/'ES102'
% so the helper's else branch will be used: omega_ts_ES101, omega_ts_ES102
set_param([mdl '/W_omega_ES101'], 'MaxDataPoints', 'inf');
set_param([mdl '/W_omega_ES102'], 'MaxDataPoints', 'inf');
set_param([mdl '/W_Pe_ES101'], 'MaxDataPoints', 'inf');
set_param([mdl '/W_Pe_ES102'], 'MaxDataPoints', 'inf');

% Save + compile
out_slx = fullfile(out_dir, [mdl '.slx']);
save_system(mdl, out_slx);

compile_ok = false;
try
    set_param(mdl, 'SimulationCommand', 'update');
    compile_ok = true;
    fprintf('RESULT: P0.1 compile PASS\n');
catch ME
    fprintf('RESULT: P0.1 compile FAIL: %s\n', ME.message);
    fprintf('RESULT: VERDICT=FAIL_COMPILE\n');
    return;
end

% ---- Run sim ----
t0 = tic;
try
    out = sim(mdl, 'StopTime', '5');
    elapsed = toc(t0);
    fprintf('RESULT: P0.2 sim PASS, wall=%.2fs (5s sim)\n', elapsed);
catch ME
    fprintf('RESULT: P0.2 sim FAIL: %s\n', ME.message);
    fprintf('RESULT: VERDICT=FAIL_SIM\n');
    return;
end

% ---- Read traces ----
% Helper writes integer-suffix vars for ESS: ES101 → 101, ES102 → 102
omega_A = out.get('omega_ts_101');
omega_B = out.get('omega_ts_102');
Pe_A = out.get('Pe_ts_101');
Pe_B = out.get('Pe_ts_102');

if isempty(omega_A) || isempty(omega_B)
    fprintf('RESULT: VERDICT=FAIL — missing omega traces\n');
    return;
end

% Steady-state window: last 1s
t = omega_A.Time;
mask = t > 4.0;
oA = omega_A.Data(mask);
oB = omega_B.Data(mask);
peA = Pe_A.Data(mask);
peB = Pe_B.Data(mask);

mean_oA = mean(oA); std_oA = std(oA);
mean_oB = mean(oB); std_oB = std(oB);
mean_peA = mean(peA); mean_peB = mean(peB);

fprintf('RESULT: ES101 omega mean=%.6f std=%.8f\n', mean_oA, std_oA);
fprintf('RESULT: ES102 omega mean=%.6f std=%.8f\n', mean_oB, std_oB);
fprintf('RESULT: ES101 Pe mean=%.4f Pm_target=0.20 (vsg-pu)\n', mean_peA);
fprintf('RESULT: ES102 Pe mean=%.4f Pm_target=0.20 (vsg-pu)\n', mean_peB);

% Antiphase check (relative diff)
omega_diff = abs(mean_oA - mean_oB);
fprintf('RESULT: |omega_A - omega_B| = %.8f (target < 1e-4)\n', omega_diff);

% Acceptance
p3_A = abs(mean_oA - 1.0) < 0.001 && std_oA < 0.0005;
p3_B = abs(mean_oB - 1.0) < 0.001 && std_oB < 0.0005;
% Pe at IC should ≈ Pm × scale = 0.4 × 0.5 = 0.2 vsg-pu (since Pe_pu in helper outputs vsg-pu via PeSrcPU later... actually Pe_ts is sys-pu)
% Pm_sys = 0.4 → Pe_sys ≈ 0.4 (40 MW / 100 MVA)
p4_A = abs(mean_peA - 0.4) < 0.05;
p4_B = abs(mean_peB - 0.4) < 0.05;
p5 = omega_diff < 1e-4;

fprintf('RESULT: P0.3 ES101 settle: %s\n', ternary(p3_A, 'PASS', 'FAIL'));
fprintf('RESULT: P0.3 ES102 settle: %s\n', ternary(p3_B, 'PASS', 'FAIL'));
fprintf('RESULT: P0.4 ES101 Pe match: %s\n', ternary(p4_A, 'PASS', 'FAIL'));
fprintf('RESULT: P0.4 ES102 Pe match: %s\n', ternary(p4_B, 'PASS', 'FAIL'));
fprintf('RESULT: P0.5 antiphase: %s\n', ternary(p5, 'PASS', 'FAIL'));

if p3_A && p3_B && p4_A && p4_B && p5
    fprintf('RESULT: VERDICT=PASS — multi-source coupling stable in Discrete\n');
else
    fprintf('RESULT: VERDICT=FAIL — diagnose above\n');
end

end

function s = ternary(cond, a, b)
if cond, s = a; else, s = b; end
end
