%% patch_ne39_faststart.m
% One-time patch for NE39bus_v2.slx:
%   1. VSG_ES{k}/M0  Value -> 'M0_val_ES{k}'    (RL inertia, workspace var)
%   2. VSG_ES{k}/D0  Value -> 'D0_val_ES{k}'    (RL damping, workspace var)
%   3. VSrc_ES{k}  PhaseAngle -> 'phAng_ES{k}'  (VSG delta feedback, deg)
%   4. Pe_{k}      Value -> 'Pe_ES{k}'           (P_e feedback, p.u. on VSG base)
%
% After patching, workspace-variable updates between FastRestart steps become
% the only mechanism for parameter changes (no set_param on mask values).
%
% Run once from MATLAB command window:
%   cd('C:\Users\27443\Desktop\Multi-Agent  VSGs\scenarios\new_england\simulink_models')
%   patch_ne39_faststart

mdl = 'NE39bus_v2';

% Load model if not already open
if ~bdIsLoaded(mdl)
    load_system(mdl);
end

% Initial phaseAngle values (degrees) from load-flow.
% These are the values currently hard-coded in VSrc_ES{k} — preserve them.
init_phAng = [-3.646, 0, 2.466, 4.423, 3.398, 5.698, 8.494, 2.181];
init_M0    = 12.0;   % from config_simulink.py VSG_M0
init_D0    =  3.0;   % from config_simulink.py VSG_D0
init_Pe    =  0.5;   % p.u. on VSG base (200 MVA), same as current Constant

fprintf('Patching %s for FastRestart workspace-variable control...\n', mdl);

for k = 1:8
    % --- M0, D0 inside VSG subsystem ---
    m0_path = sprintf('%s/VSG_ES%d/M0', mdl, k);
    d0_path = sprintf('%s/VSG_ES%d/D0', mdl, k);
    set_param(m0_path, 'Value', sprintf('M0_val_ES%d', k));
    set_param(d0_path, 'Value', sprintf('D0_val_ES%d', k));
    fprintf('  VSG_ES%d: M0/D0 -> workspace vars\n', k);

    % --- VSrc PhaseAngle (degrees) ---
    vsrc_path = sprintf('%s/VSrc_ES%d', mdl, k);
    set_param(vsrc_path, 'PhaseAngle', sprintf('phAng_ES%d', k));
    fprintf('  VSrc_ES%d: PhaseAngle -> phAng_ES%d (init %.3f deg)\n', ...
            k, k, init_phAng(k));

    % --- Pe Constant (p.u. on VSG base) ---
    pe_path = sprintf('%s/Pe_%d', mdl, k);
    set_param(pe_path, 'Value', sprintf('Pe_ES%d', k));
    fprintf('  Pe_%d: Value -> Pe_ES%d (init %.4f)\n', k, k, init_Pe);
end

% Pre-populate workspace so the model can compile without 'undefined variable'
fprintf('\nInitialising base workspace variables...\n');
for k = 1:8
    assignin('base', sprintf('M0_val_ES%d', k), init_M0);
    assignin('base', sprintf('D0_val_ES%d', k), init_D0);
    assignin('base', sprintf('phAng_ES%d',  k), init_phAng(k));
    assignin('base', sprintf('Pe_ES%d',     k), init_Pe);
end

% Save patched model
save_system(mdl);
fprintf('\nDone. %s saved.\n', mdl);
fprintf('Initial workspace variable values written to base workspace.\n');
fprintf('Run slx_warmup(''%s'', ...) to start a training episode.\n', mdl);
