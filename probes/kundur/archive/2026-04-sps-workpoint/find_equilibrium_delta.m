%FIND_EQUILIBRIUM_DELTA  High-damping simulation to find VSG equilibrium angles.
%
% Purpose: vlf_ess (rotor angle ICs) are stale after the impedance fix.  At
%   the old angles [18,10,7,12]° the electrical power is 5-8x the mechanical
%   reference, driving the swing equation out of equilibrium immediately.
%   This probe runs 60 s with D0=50 (10x nominal) to quickly damp transients
%   and let each VSG settle to the true equilibrium delta where Pe = Pe_ref.
%
% Output: prints RESULT lines with converged delta_deg values.
%   Copy the values into kundur_ic.json (vsg_delta0_deg) then rebuild .slx.
%
% Usage: run from any MATLAB path with kundur_vsg.slx on the path.

%% ---- config ---------------------------------------------------------------
mdl          = 'kundur_vsg';
D_high       = 50.0;   % overdamped (nominal D0 = 3.0)
T_sim        = 60.0;   % seconds — enough to damp and converge
N_VSG        = 4;

% pe_nominal in VSG-base pu (from kundur_ic.json / config_simulink.py)
pe_nominal_vsg = [1.8725, 1.8419, 1.7888, 1.9154];

%% ---- locate model ---------------------------------------------------------
script_dir   = fileparts(mfilename('fullpath'));        % probes/kundur/
repo_root    = fileparts(fileparts(script_dir));        % repo root
model_dir    = fullfile(repo_root, 'scenarios', 'kundur', 'simulink_models');
addpath(model_dir);
addpath(fullfile(repo_root, 'slx_helpers'));

%% ---- load model -----------------------------------------------------------
if bdIsLoaded(mdl)
    set_param(mdl, 'FastRestart', 'off');
else
    load_system(fullfile(model_dir, [mdl '.slx']));
end

% --- Read baked-in IntD ICs from current model (preserve them) -------------
% We start from the existing vlf_ess angles and let high-D dynamics settle.
% Overriding to 0 causes VSG/network angle mismatch and immediate pole-slip.
delta0_baked = zeros(1, N_VSG);
for i = 1:N_VSG
    intd_path = sprintf('%s/VSG_ES%d/IntD', mdl, i);
    ic_str = get_param(intd_path, 'InitialCondition');
    delta0_baked(i) = str2double(ic_str) * (180/pi);  % rad → deg
end
fprintf('RESULT: baked IntD ICs (deg) = [%.3f, %.3f, %.3f, %.3f]\n', delta0_baked);

%% ---- set workspace variables ----------------------------------------------
for i = 1:N_VSG
    assignin('base', sprintf('M0_val_ES%d', i), 8.0);   % nominal M
    assignin('base', sprintf('D0_val_ES%d', i), D_high);
    assignin('base', sprintf('Pe_ES%d',     i), pe_nominal_vsg(i));
    assignin('base', sprintf('phAng_ES%d',  i), delta0_baked(i));  % match model IC
    assignin('base', sprintf('wref_%d',     i), 1.0);
end

% Disturbance loads at nominal (no trip)
assignin('base', 'TripLoad1_P', 248e6 / 3);
assignin('base', 'TripLoad2_P', 0.0);

%% ---- compile + run --------------------------------------------------------
% FastRestart off → on forces Simscape to recompile and resolve ICs.
try
    set_param(mdl, 'FastRestart', 'off');
catch
end
set_param(mdl, 'FastRestart', 'on');

set_param(mdl, 'StopTime', num2str(T_sim, '%.1f'));
fprintf('RESULT: running %g s high-D simulation (D=%g)...\n', T_sim, D_high);
simOut = sim(mdl);
fprintf('RESULT: simulation complete\n');

%% ---- read converged state -------------------------------------------------
delta_eq_deg = zeros(1, N_VSG);
omega_final  = zeros(1, N_VSG);
pe_final_vsg = zeros(1, N_VSG);

for i = 1:N_VSG
    try
        d_ts = simOut.get(sprintf('delta_ES%d', i));
        delta_eq_deg(i) = d_ts.Data(end) * (180 / pi);
    catch
        delta_eq_deg(i) = NaN;
    end
    try
        w_ts = simOut.get(sprintf('omega_ES%d', i));
        omega_final(i) = w_ts.Data(end);
    catch
        omega_final(i) = NaN;
    end
    try
        pe_ts = simOut.get(sprintf('PeFb_ES%d', i));
        pe_final_vsg(i) = pe_ts.Data(end);
    catch
        pe_final_vsg(i) = NaN;
    end
end

%% ---- report ---------------------------------------------------------------
fprintf('\n=== Equilibrium search results (T=%.0f s, D=%.0f) ===\n', T_sim, D_high);
fprintf('  %-6s  %-12s  %-12s  %-12s  %-12s\n', ...
    'VSG', 'delta_eq [°]', 'omega_final', 'PeFb [vsg]', 'Pe_nom [vsg]');
for i = 1:N_VSG
    fprintf('  ES%-4d  %+10.4f    %10.6f    %10.6f    %10.6f\n', ...
        i, delta_eq_deg(i), omega_final(i), pe_final_vsg(i), pe_nominal_vsg(i));
end

fprintf('\nRESULT: delta_eq_deg = [%.4f, %.4f, %.4f, %.4f]\n', delta_eq_deg);
fprintf('RESULT: Copy above values to kundur_ic.json "vsg_delta0_deg" then rebuild .slx\n');

%% ---- restore model (don't save IC overrides) ------------------------------
for i = 1:N_VSG
    intd_path = sprintf('%s/VSG_ES%d/IntD', mdl, i);
    try
        set_param(intd_path, 'InitialCondition', '0.0');  % keep as 0; build script sets it
    catch
    end
end
set_param(mdl, 'FastRestart', 'off');
close_system(mdl, 0);  % close without saving
fprintf('RESULT: model closed without saving (IC overrides discarded)\n');
