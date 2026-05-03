function test_dynamic_source_helper()
%TEST_DYNAMIC_SOURCE_HELPER  Validate build_dynamic_source_discrete on 1 source.
%
% Phase 1.1 helper validation. Builds a minimal 1-source-1-load model using
% build_dynamic_source_discrete() and runs the same oracle as Phase 0 SMIB.
%
% Expected: same/similar result to build_minimal_smib_discrete (max|Δf| > 0.3 Hz
% on 248 MW step). If matches, helper is sound and we can scale to 7 sources.
%
% Differences vs build_minimal_smib_discrete:
%   - Uses helper function (not inline blocks)
%   - Source meta passed as struct (matches v3 src_meta row)
%   - Helper produces per-source IntD/IntW (not anonymous Int blocks)
%   - Helper includes Pm-step gating (set step_amp=0 to disable)

mdl = 'test_helper_smib';
out_dir = fileparts(mfilename('fullpath'));
out_slx = fullfile(out_dir, [mdl '.slx']);

% Global params
fn    = 50;
wn    = 2*pi*fn;
Sbase = 100e6;
Vbase = 230e3;
VSG_SN = 200e6;

% Reset model
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
load_system('powerlib');

% powergui Discrete
add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
set_param([mdl '/powergui'], 'SimulationMode', 'Discrete', 'SampleTime', '50e-6');
set_param(mdl, 'StopTime', '5', 'SolverType', 'Fixed-step', ...
    'Solver', 'FixedStepAuto', 'FixedStep', '50e-6');

% Global Clock (helper expects this)
add_block('built-in/Clock', [mdl '/Clock_global'], 'Position', [20 80 50 100]);

% Workspace vars (mimics v3 base-ws contract)
assignin('base', 'wn_const',    double(wn));
assignin('base', 'Vbase_const', double(Vbase));
assignin('base', 'Sbase_const', double(Sbase));
assignin('base', 'Pe_scale',    double(1.0 / Sbase));
assignin('base', 'M_es1_test',     24.0);
assignin('base', 'D_es1_test',     4.5);
assignin('base', 'Pm_es1_test',    0.4);     % sys-pu = 40 MW
assignin('base', 'delta0_es1_test', 0.0);
assignin('base', 'Vmag_es1_test',   double(Vbase));    % V_emf_pu × Vbase, here pu=1.0
assignin('base', 'VSGScale_es1_test', double(Sbase / VSG_SN));
assignin('base', 'Pm_step_t_es1_test',   100.0);
assignin('base', 'Pm_step_amp_es1_test', 0.0);
assignin('base', 'LoadStep_amp_W',  248e6);
assignin('base', 'LoadStep_t_s',    2.0);

% Source meta (1 ESS for testing)
src.name        = 'ES1';
src.stype       = 'ess';
src.bus         = 12;
src.M_var       = 'M_es1_test';
src.D_var       = 'D_es1_test';
src.Pm_var      = 'Pm_es1_test';
src.delta0_var  = 'delta0_es1_test';
src.Vmag_var    = 'Vmag_es1_test';
src.scale_var   = 'VSGScale_es1_test';
src.Rdrop_var   = '';
src.Lint_H      = 0.30 * (Vbase^2/VSG_SN) / wn;
src.step_t_var  = 'Pm_step_t_es1_test';
src.step_amp_var = 'Pm_step_amp_es1_test';

geom.bx = 600;
geom.cy = 300;
geom.global_clock = 'Clock_global';
geom.bus_anchor = '';  % placeholder; we wire to Zvsg+Load directly below

params.fn = fn; params.wn = wn; params.Vbase = Vbase; params.Sbase = Sbase;

% Add the dynamic source
addpath('C:/Users/27443/Desktop/Multi-Agent-VSGs-discrete/scenarios/kundur/simulink_models');
build_dynamic_source_discrete(mdl, src, geom, params);

% ===================================================================
% Connect VImeas RConn (bus side) → series Z → Load_const + Breaker→Load_step
% ===================================================================
% Internal impedance Z (R+L per phase, repeating SMIB pattern but per-phase)
R_vsg = 0.003 * (Vbase^2/VSG_SN);
L_vsg = src.Lint_H;

vimeas_blk = sprintf('VImeas_%s', src.name);

% Use Three-Phase Series RLC Branch on each phase (single-phase R+L)
add_block('spsSeriesRLCBranchLib/Series RLC Branch', [mdl '/Zvsg_A'], ...
    'Position', [950 195 990 235]);
set_param([mdl '/Zvsg_A'], 'BranchType', 'RL', ...
    'Resistance', num2str(R_vsg), 'Inductance', num2str(L_vsg));
add_block('spsSeriesRLCBranchLib/Series RLC Branch', [mdl '/Zvsg_B'], ...
    'Position', [950 245 990 285]);
set_param([mdl '/Zvsg_B'], 'BranchType', 'RL', ...
    'Resistance', num2str(R_vsg), 'Inductance', num2str(L_vsg));
add_block('spsSeriesRLCBranchLib/Series RLC Branch', [mdl '/Zvsg_C'], ...
    'Position', [950 295 990 335]);
set_param([mdl '/Zvsg_C'], 'BranchType', 'RL', ...
    'Resistance', num2str(R_vsg), 'Inductance', num2str(L_vsg));

add_line(mdl, [vimeas_blk '/RConn1'], 'Zvsg_A/LConn1', 'autorouting', 'smart');
add_line(mdl, [vimeas_blk '/RConn2'], 'Zvsg_B/LConn1', 'autorouting', 'smart');
add_line(mdl, [vimeas_blk '/RConn3'], 'Zvsg_C/LConn1', 'autorouting', 'smart');

% Constant load (matches Pm = 40 MW)
load_path = sprintf('sps_lib/Passives/Three-Phase\nSeries RLC Load');
add_block(load_path, [mdl '/Load_const'], 'Position', [1050 195 1130 335]);
set_param([mdl '/Load_const'], 'Configuration', 'Y (grounded)', ...
    'NominalVoltage', num2str(Vbase), 'NominalFrequency', num2str(fn), ...
    'ActivePower', '40e6', 'InductivePower', '0', 'CapacitivePower', '0');
add_line(mdl, 'Zvsg_A/RConn1', 'Load_const/LConn1', 'autorouting', 'smart');
add_line(mdl, 'Zvsg_B/RConn1', 'Load_const/LConn2', 'autorouting', 'smart');
add_line(mdl, 'Zvsg_C/RConn1', 'Load_const/LConn3', 'autorouting', 'smart');

% LoadStep: Three-Phase Breaker + Three-Phase Series RLC Load (248 MW @ t=2s)
add_block('sps_lib/Power Grid Elements/Three-Phase Breaker', [mdl '/Breaker'], ...
    'Position', [1050 380 1130 460]);
set_param([mdl '/Breaker'], 'InitialState', 'open', ...
    'SwitchA', 'on', 'SwitchB', 'on', 'SwitchC', 'on', ...
    'External', 'off', 'SwitchTimes', '[LoadStep_t_s]');

add_block(load_path, [mdl '/Load_step'], 'Position', [1170 380 1240 460]);
set_param([mdl '/Load_step'], 'Configuration', 'Y (grounded)', ...
    'NominalVoltage', num2str(Vbase), 'NominalFrequency', num2str(fn), ...
    'ActivePower', 'LoadStep_amp_W', 'InductivePower', '0', 'CapacitivePower', '0');

add_line(mdl, 'Zvsg_A/RConn1', 'Breaker/LConn1', 'autorouting', 'smart');
add_line(mdl, 'Zvsg_B/RConn1', 'Breaker/LConn2', 'autorouting', 'smart');
add_line(mdl, 'Zvsg_C/RConn1', 'Breaker/LConn3', 'autorouting', 'smart');
add_line(mdl, 'Breaker/RConn1', 'Load_step/LConn1', 'autorouting', 'smart');
add_line(mdl, 'Breaker/RConn2', 'Load_step/LConn2', 'autorouting', 'smart');
add_line(mdl, 'Breaker/RConn3', 'Load_step/LConn3', 'autorouting', 'smart');

% Save
save_system(mdl, out_slx);
fprintf('RESULT: test_helper_smib built at %s\n', out_slx);
fprintf('RESULT: src=%s bx=%d cy=%d\n', src.name, geom.bx, geom.cy);

end
