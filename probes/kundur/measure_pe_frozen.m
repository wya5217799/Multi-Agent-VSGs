%MEASURE_PE_FROZEN  Measure Pe_static at test angles using M=1e9 (frozen delta).
%
% Strategy: Set M0=1e9 (virtual infinite inertia) so d(omega)/dt ≈ 0 and
%   delta stays at the initial angle while the Pe filter settles.
%   After T_meas=300ms (>> 5 × 20ms filter tau), PeFb ≈ Pe_static(delta_test).
%   Apply SMIB formula to estimate equilibrium angle:
%     K_i      = PeFb_i / sin(delta_test_i [rad])
%     delta_eq_i = arcsin(Pe_nom_i / K_i)
%
% Output: prints RESULT: lines. Copy delta_eq to kundur_ic.json → rebuild.
% Usage:  run from MATLAB with kundur_vsg.slx on path.

%% ---- config ---------------------------------------------------------------
mdl       = 'kundur_vsg';
T_meas    = 0.30;   % s — >> 5×tau_filter
M_frozen  = 1e9;    % virtual infinite inertia: freezes delta
D_nom     = 3.0;
N_VSG     = 4;
pe_nom_vsg = [1.8725, 1.8419, 1.7888, 1.9154];  % VSG-base pu (from kundur_ic.json)

%% ---- paths ----------------------------------------------------------------
script_dir = fileparts(mfilename('fullpath'));
repo_root  = fileparts(fileparts(script_dir));
model_dir  = fullfile(repo_root, 'scenarios', 'kundur', 'simulink_models');
addpath(model_dir);
addpath(fullfile(repo_root, 'slx_helpers'));

%% ---- load model + read baked ICs -----------------------------------------
if bdIsLoaded(mdl)
    set_param(mdl, 'FastRestart', 'off');
else
    load_system(fullfile(model_dir, [mdl '.slx']));
end

delta_test_deg = zeros(1, N_VSG);
for i = 1:N_VSG
    intd_path = sprintf('%s/VSG_ES%d/IntD', mdl, i);
    ic_str    = get_param(intd_path, 'InitialCondition');
    delta_test_deg(i) = str2double(ic_str) * (180/pi);
end
fprintf('RESULT: test angles (baked IntD ICs, deg) = [%.4f, %.4f, %.4f, %.4f]\n', ...
    delta_test_deg);

%% ---- set workspace vars ---------------------------------------------------
for i = 1:N_VSG
    assignin('base', sprintf('M0_val_ES%d', i), M_frozen);
    assignin('base', sprintf('D0_val_ES%d', i), D_nom);
    assignin('base', sprintf('Pe_ES%d',     i), pe_nom_vsg(i));
    assignin('base', sprintf('phAng_ES%d',  i), delta_test_deg(i));
    assignin('base', sprintf('wref_%d',     i), 1.0);
end
assignin('base', 'TripLoad1_P', 248e6 / 3);
assignin('base', 'TripLoad2_P', 0.0);

%% ---- compile + run --------------------------------------------------------
try, set_param(mdl, 'FastRestart', 'off'); catch, end
set_param(mdl, 'FastRestart', 'on');
set_param(mdl, 'StopTime', num2str(T_meas, '%.3f'));
fprintf('RESULT: running %.3f s with M=%.0e (frozen delta)...\n', T_meas, M_frozen);
simOut = sim(mdl);
fprintf('RESULT: sim done\n');

%% ---- read PeFb and omega at end -----------------------------------------
pe_static  = zeros(1, N_VSG);
omega_end  = zeros(1, N_VSG);
delta_end  = zeros(1, N_VSG);

for i = 1:N_VSG
    try
        pe_ts = simOut.get(sprintf('PeFb_ES%d', i));
        pe_static(i) = pe_ts.Data(end);
    catch
        pe_static(i) = NaN;
        fprintf('RESULT: WARNING PeFb_ES%d not found in simOut\n', i);
    end
    try
        w_ts = simOut.get(sprintf('omega_ES%d', i));
        omega_end(i) = w_ts.Data(end);
    catch
        omega_end(i) = NaN;
    end
    try
        d_ts = simOut.get(sprintf('delta_ES%d', i));
        delta_end(i) = d_ts.Data(end) * (180/pi);
    catch
        delta_end(i) = NaN;
    end
end

%% ---- SMIB estimate --------------------------------------------------------
delta_eq_deg = zeros(1, N_VSG);
for i = 1:N_VSG
    if isnan(pe_static(i)) || pe_static(i) <= 0
        delta_eq_deg(i) = NaN;
        fprintf('RESULT: WARNING ES%d pe_static=%.4f invalid\n', i, pe_static(i));
        continue;
    end
    ratio = pe_nom_vsg(i) / pe_static(i) * sind(delta_test_deg(i));
    if abs(ratio) <= 1.0
        delta_eq_deg(i) = asind(ratio);
    else
        delta_eq_deg(i) = NaN;
        fprintf('RESULT: WARNING ES%d SMIB ratio=%.4f out of [-1,1]\n', i, ratio);
    end
end

%% ---- report ---------------------------------------------------------------
fprintf('\n=== Frozen-delta Pe measurement (T=%.0f ms, M=%.0e) ===\n', ...
    T_meas*1000, M_frozen);
fprintf('  %-6s  %-14s  %-14s  %-12s  %-12s  %-14s\n', ...
    'VSG', 'delta_test [deg]', 'delta_end [deg]', 'omega_end', ...
    'PeFb [vsg]', 'delta_eq [deg]');
for i = 1:N_VSG
    fprintf('  ES%-4d  %+12.4f    %+12.4f    %10.6f    %10.6f    %+12.4f\n', ...
        i, delta_test_deg(i), delta_end(i), omega_end(i), pe_static(i), delta_eq_deg(i));
end
fprintf('\nRESULT: pe_static_vsg  = [%.4f, %.4f, %.4f, %.4f]\n', pe_static);
fprintf('RESULT: delta_eq_deg   = [%.4f, %.4f, %.4f, %.4f]\n', delta_eq_deg);
fprintf('RESULT: pe_nom_vsg     = [%.4f, %.4f, %.4f, %.4f]\n', pe_nom_vsg);
fprintf('RESULT: Pe ratio (meas/nom) = [%.3f, %.3f, %.3f, %.3f]\n', ...
    pe_static ./ pe_nom_vsg);

%% ---- restore + close ------------------------------------------------------
set_param(mdl, 'FastRestart', 'off');
close_system(mdl, 0);
fprintf('RESULT: model closed (no save)\n');
