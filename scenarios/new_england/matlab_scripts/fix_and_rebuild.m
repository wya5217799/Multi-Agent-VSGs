%% fix_and_rebuild.m
% Fix the two issues from first build attempt:
%   1. Wind farm inertia: modify mac_con matrix directly (H=0.05, D=0)
%   2. VSG Integrator: use correct param names for R2025b

run('NE39bus_modified_data.m');

dst_model = 'NE39bus_modified';
if bdIsLoaded(dst_model), close_system(dst_model, 0); end
load_system(dst_model);

%% ======================================================================
%  FIX 1: Modify mac_con to set G1-G8 as PMSG (near-zero inertia)
%  Column 16 = H (inertia constant), Column 17 = D (damping)
%% ======================================================================
fprintf('=== Fix 1: Setting G1-G8 inertia via mac_con ===\n');

% The model uses mac_con from the workspace/data file
% Column 16 = H(sec), Column 17 = D(pu)
% G1-G8 = rows 1-8, G9 = row 9, G10 = row 1

% Create modified mac_con with near-zero H for G1-G8
mac_con_mod = mac_con;  % from NE39bus_modified_data.m (which runs NE39bus_data.m)
for k = 1:8
    mac_con_mod(k, 16) = 0.05;  % H = 0.05s (near-zero inertia, PMSG)
    mac_con_mod(k, 17) = 0.0;   % D = 0 (no damping from PMSG)
end
fprintf('  G1-G8: H = 0.05s, D = 0.0\n');
fprintf('  G9:  H = %.2fs (retained)\n', mac_con_mod(9, 16));
fprintf('  G10: H = %.2fs (retained)\n', mac_con_mod(10, 16));

% Assign modified mac_con to base workspace (model reads from base ws)
assignin('base', 'mac_con', mac_con_mod);
fprintf('  mac_con updated in base workspace.\n');

% Also need p0 and Pn in base workspace
assignin('base', 'p0', p0);
assignin('base', 'Pn', Pn);

%% ======================================================================
%  FIX 2: Delete broken VSG subsystems and rebuild with correct params
%% ======================================================================
fprintf('\n=== Fix 2: Rebuilding VSG-ESS Subsystems ===\n');

for i = 1:n_ess
    vsg_name = sprintf('VSG_ES%d', i);
    vsg_path = sprintf('%s/%s', dst_model, vsg_name);

    % Delete existing broken subsystem
    try
        delete_block(vsg_path);
        fprintf('  Deleted broken %s\n', vsg_name);
    catch
    end

    % Layout position
    x = 50 + mod(i-1, 4) * 400;
    y = 1500 + floor((i-1)/4) * 350;

    % Create subsystem
    add_block('built-in/SubSystem', vsg_path, ...
        'Position', [x y x+300 y+250]);

    % ---- Input Ports ----
    add_block('built-in/Inport', [vsg_path '/omega_ref'], ...
        'Position', [30 30 60 50], 'Port', '1');
    add_block('built-in/Inport', [vsg_path '/delta_M'], ...
        'Position', [30 80 60 100], 'Port', '2');
    add_block('built-in/Inport', [vsg_path '/delta_D'], ...
        'Position', [30 130 60 150], 'Port', '3');
    add_block('built-in/Inport', [vsg_path '/P_ref'], ...
        'Position', [30 180 60 200], 'Port', '4');
    add_block('built-in/Inport', [vsg_path '/P_e'], ...
        'Position', [30 230 60 250], 'Port', '5');

    % ---- Output Ports ----
    add_block('built-in/Outport', [vsg_path '/omega'], ...
        'Position', [750 80 780 100], 'Port', '1');
    add_block('built-in/Outport', [vsg_path '/delta'], ...
        'Position', [750 180 780 200], 'Port', '2');
    add_block('built-in/Outport', [vsg_path '/P_out'], ...
        'Position', [750 280 780 300], 'Port', '3');

    % ---- M_total = M0 + delta_M, clamped to [6, 30] ----
    add_block('built-in/Constant', [vsg_path '/M0'], ...
        'Position', [100 65 150 85], 'Value', num2str(VSG_M0));
    add_block('built-in/Sum', [vsg_path '/Sum_M'], ...
        'Position', [190 70 220 90], 'Inputs', '++');
    add_line(vsg_path, 'M0/1', 'Sum_M/1');
    add_line(vsg_path, 'delta_M/1', 'Sum_M/2');

    add_block('built-in/Saturate', [vsg_path '/Sat_M'], ...
        'Position', [240 68 270 92], ...
        'UpperLimit', '30', 'LowerLimit', '6');
    add_line(vsg_path, 'Sum_M/1', 'Sat_M/1');

    % ---- D_total = D0 + delta_D, clamped to [1.5, 7.5] ----
    add_block('built-in/Constant', [vsg_path '/D0'], ...
        'Position', [100 120 150 140], 'Value', num2str(VSG_D0));
    add_block('built-in/Sum', [vsg_path '/Sum_D'], ...
        'Position', [190 125 220 145], 'Inputs', '++');
    add_line(vsg_path, 'D0/1', 'Sum_D/1');
    add_line(vsg_path, 'delta_D/1', 'Sum_D/2');

    add_block('built-in/Saturate', [vsg_path '/Sat_D'], ...
        'Position', [240 123 270 147], ...
        'UpperLimit', '7.5', 'LowerLimit', '1.5');
    add_line(vsg_path, 'Sum_D/1', 'Sat_D/1');

    % ---- Swing Equation ----
    % omega_error = omega_fb - omega_ref
    add_block('built-in/Sum', [vsg_path '/omega_err'], ...
        'Position', [350 30 380 60], 'Inputs', '+-');

    % D_damping = D_total * omega_error
    add_block('built-in/Product', [vsg_path '/Prod_D'], ...
        'Position', [410 100 440 140], 'Inputs', '**');
    add_line(vsg_path, 'Sat_D/1', 'Prod_D/1');
    add_line(vsg_path, 'omega_err/1', 'Prod_D/2');

    % P_accel = P_ref - P_e - D_damping
    add_block('built-in/Sum', [vsg_path '/Sum_P'], ...
        'Position', [480 170 510 210], 'Inputs', '+--');
    add_line(vsg_path, 'P_ref/1', 'Sum_P/1');
    add_line(vsg_path, 'P_e/1', 'Sum_P/2');
    add_line(vsg_path, 'Prod_D/1', 'Sum_P/3');

    % d(omega)/dt = P_accel / M_total
    add_block('built-in/Product', [vsg_path '/Div_M'], ...
        'Position', [540 150 570 180], 'Inputs', '*/');
    add_line(vsg_path, 'Sum_P/1', 'Div_M/1');
    add_line(vsg_path, 'Sat_M/1', 'Div_M/2');

    % omega integrator with saturation [0.9, 1.1]
    add_block('built-in/Integrator', [vsg_path '/Int_omega'], ...
        'Position', [600 150 640 175], ...
        'InitialCondition', '1.0', ...
        'LimitOutput', 'on', ...
        'UpperSaturationLimit', '1.1', ...
        'LowerSaturationLimit', '0.9');
    add_line(vsg_path, 'Div_M/1', 'Int_omega/1');

    % Feedback: omega -> omega_error
    add_line(vsg_path, 'Int_omega/1', 'omega_err/1');
    add_line(vsg_path, 'omega_ref/1', 'omega_err/2');

    % delta integrator: d(delta)/dt = omega_n * (omega - 1)
    add_block('built-in/Constant', [vsg_path '/One'], ...
        'Position', [560 220 590 240], 'Value', '1.0');
    add_block('built-in/Sum', [vsg_path '/Sum_dev'], ...
        'Position', [620 210 640 230], 'Inputs', '+-');
    add_line(vsg_path, 'Int_omega/1', 'Sum_dev/1');
    add_line(vsg_path, 'One/1', 'Sum_dev/2');

    add_block('built-in/Gain', [vsg_path '/omega_n'], ...
        'Position', [660 210 700 230], 'Gain', num2str(omega_n));
    add_line(vsg_path, 'Sum_dev/1', 'omega_n/1');

    add_block('built-in/Integrator', [vsg_path '/Int_delta'], ...
        'Position', [720 210 760 235], ...
        'InitialCondition', '0');
    add_line(vsg_path, 'omega_n/1', 'Int_delta/1');

    % ---- Output Connections ----
    add_line(vsg_path, 'Int_omega/1', 'omega/1');
    add_line(vsg_path, 'Int_delta/1', 'delta/1');
    add_line(vsg_path, 'Sum_P/1', 'P_out/1');

    fprintf('  Built %s: M0=%.1f, D0=%.1f, omega_n=%.1f\n', ...
        vsg_name, VSG_M0, VSG_D0, omega_n);
end

%% ======================================================================
%  Save and verify
%% ======================================================================
save_system(dst_model);
fprintf('\n=== Model saved: %s.slx ===\n', dst_model);

% Verify VSG blocks exist
for i = 1:n_ess
    vsg_path = sprintf('%s/VSG_ES%d', dst_model, i);
    try
        bt = get_param(vsg_path, 'BlockType');
        ports = get_param(vsg_path, 'Ports');
        fprintf('  VSG_ES%d: OK (type=%s, ports=[%s])\n', i, bt, num2str(ports));
    catch me
        fprintf('  VSG_ES%d: MISSING - %s\n', i, me.message);
    end
end

% Save the modified data file for the model to use
save('NE39bus_workspace.mat', 'mac_con', 'p0', 'Pn', 'line', ...
    'AVR_Data', 'MB', 'Bus', 'C0', 'L0', 'R0', 'Ns', 's');
fprintf('\nWorkspace data saved to NE39bus_workspace.mat\n');

fprintf('\n========================================\n');
fprintf('Model fix complete!\n');
fprintf('  G1-G8 inertia set via mac_con matrix\n');
fprintf('  8 VSG subsystems rebuilt with correct Integrator params\n');
fprintf('========================================\n');
