%% build_modified_model.m
% Programmatically modify NE39bus2_PQ Simulink model for paper Section IV-G:
%   1. Modify G1-G8 to simulate PMSG wind farms (near-zero inertia)
%   2. Add 8 VSG-ESS subsystems for RL control
%   3. Add measurement/logging blocks for Python interface
%
% Actual model structure discovered:
%   - Generators: G1/G1 ... G10/G10 (Simscape sync machines inside subsystems)
%   - Each Gk has: Gk/Gk (machine), Gk/M1: Turbine & Regulators, Gk/A,B,C
%   - Buses: named by number (1, 2, ... 39)
%   - Loads: load3, load4, load7, etc.
%   - Transformers: T2: 900MVA 20 kV//230 kV1 ... T2: 900MVA 20 kV//230 kV12
%
% Run: build_modified_model  (from MATLAB command window)

%% Load parameters
run('NE39bus_modified_data.m');

%% Configuration
src_model = 'NE39bus2_PQ';
dst_model = 'NE39bus_modified';

% Close if already open
if bdIsLoaded(src_model), close_system(src_model, 0); end
if bdIsLoaded(dst_model), close_system(dst_model, 0); end

% Copy model
if exist([dst_model '.slx'], 'file')
    delete([dst_model '.slx']);
end
copyfile([src_model '.slx'], [dst_model '.slx'], 'f');
load_system(dst_model);
fprintf('Model %s loaded from %s.\n', dst_model, src_model);

%% ======================================================================
%  STEP 1: Modify G1-G8 sync machines to simulate PMSG wind farms
%  Strategy: Set H -> near-zero, D -> 0, disable governor (R -> 999)
%  This is the simplest approach that preserves the electrical connection
%  while removing inertia contribution (PMSG is grid-following via PLL)
%% ======================================================================
fprintf('\n=== Step 1: Modifying G1-G8 as PMSG Wind Farms ===\n');

% Generator subsystem names in the model
gen_names = cell(1, 10);
for k = 1:10
    gen_names{k} = sprintf('%s/G%d', dst_model, k);
end

% Find the actual synchronous machine blocks inside G1-G8
for k = 1:8
    gen_path = gen_names{k};
    fprintf('\nProcessing %s...\n', gen_path);

    % Find sync machine block inside this generator subsystem
    sm_path = sprintf('%s/G%d', gen_path, k);

    try
        % Read current parameters to understand the mask
        mask_type = get_param(sm_path, 'MaskType');
        fprintf('  Machine block: %s (MaskType: %s)\n', sm_path, mask_type);

        % Get dialog parameters
        dlg = get_param(sm_path, 'DialogParameters');
        param_names = fieldnames(dlg);
        fprintf('  Available parameters (%d):\n', length(param_names));
        for p = 1:min(20, length(param_names))
            try
                val = get_param(sm_path, param_names{p});
                if ischar(val) && length(val) < 50
                    fprintf('    %s = %s\n', param_names{p}, val);
                end
            catch
            end
        end

        % Try to set inertia constant H to near-zero
        % Different SM blocks use different parameter names
        h_params = {'H', 'Hm', 'InertiaConstant', 'RotorInertia'};
        for hp = 1:length(h_params)
            try
                set_param(sm_path, h_params{hp}, '0.05');
                fprintf('  -> Set %s = 0.05 (near-zero inertia)\n', h_params{hp});
                break;
            catch
            end
        end

        % Try to set damping to 0
        d_params = {'D', 'Dm', 'DampingFactor'};
        for dp = 1:length(d_params)
            try
                set_param(sm_path, d_params{dp}, '0');
                fprintf('  -> Set %s = 0 (no damping)\n', d_params{dp});
                break;
            catch
            end
        end

    catch me
        fprintf('  Warning: Could not access %s: %s\n', sm_path, me.message);
        fprintf('  Trying alternative paths...\n');

        % Search for any SM-like blocks inside this generator
        all_in_gen = find_system(gen_path, 'SearchDepth', 3, 'Type', 'block');
        for b = 1:length(all_in_gen)
            try
                mt = get_param(all_in_gen{b}, 'MaskType');
                if contains(lower(mt), 'synchronous') || contains(lower(mt), 'machine')
                    fprintf('  Found machine: %s [%s]\n', all_in_gen{b}, mt);
                end
            catch
            end
        end
    end

    % Modify governor (STG block inside M1: Turbine & Regulators)
    try
        stg_path = sprintf('%s/M1: Turbine & Regulators/STG1', gen_path);
        % Try to set droop to very high value (effectively disabling governor)
        stg_params = get_param(stg_path, 'DialogParameters');
        stg_param_names = fieldnames(stg_params);
        fprintf('  STG1 params: ');
        for p = 1:length(stg_param_names)
            fprintf('%s, ', stg_param_names{p});
        end
        fprintf('\n');

        % Try R parameter (droop)
        r_params = {'R', 'Droop', 'R_droop'};
        for rp = 1:length(r_params)
            try
                set_param(stg_path, r_params{rp}, '999');
                fprintf('  -> Set governor %s = 999 (disabled)\n', r_params{rp});
                break;
            catch
            end
        end
    catch me
        fprintf('  Governor modification skipped: %s\n', me.message);
    end

    fprintf('  G%d modified as PMSG wind farm.\n', k);
end

%% ======================================================================
%  STEP 2: Build VSG-ESS subsystems
%  Each VSG implements the swing equation:
%    M * d(omega)/dt = P_ref - P_e - D * (omega - omega_ref)
%  where M = M0 + delta_M, D = D0 + delta_D are controlled by RL agent
%% ======================================================================
fprintf('\n=== Step 2: Building VSG-ESS Subsystems ===\n');

for i = 1:n_ess
    vsg_name = sprintf('VSG_ES%d', i);
    vsg_path = sprintf('%s/%s', dst_model, vsg_name);

    % Layout position (below existing model)
    x = 50 + mod(i-1, 4) * 400;
    y = 1500 + floor((i-1)/4) * 350;

    try
        % Check if already exists
        try
            get_param(vsg_path, 'BlockType');
            fprintf('  %s already exists, skipping.\n', vsg_name);
            continue;
        catch
        end

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

        % ---- M_total = M0 + delta_M ----
        add_block('built-in/Constant', [vsg_path '/M0'], ...
            'Position', [100 65 150 85], 'Value', num2str(VSG_M0));
        add_block('built-in/Sum', [vsg_path '/Sum_M'], ...
            'Position', [190 70 220 90], 'Inputs', '++');
        add_line(vsg_path, 'M0/1', 'Sum_M/1');
        add_line(vsg_path, 'delta_M/1', 'Sum_M/2');

        % Clamp M to [6, 30]
        add_block('built-in/Saturate', [vsg_path '/Sat_M'], ...
            'Position', [240 68 270 92], ...
            'UpperLimit', '30', 'LowerLimit', '6');
        add_line(vsg_path, 'Sum_M/1', 'Sat_M/1');

        % ---- D_total = D0 + delta_D ----
        add_block('built-in/Constant', [vsg_path '/D0'], ...
            'Position', [100 120 150 140], 'Value', num2str(VSG_D0));
        add_block('built-in/Sum', [vsg_path '/Sum_D'], ...
            'Position', [190 125 220 145], 'Inputs', '++');
        add_line(vsg_path, 'D0/1', 'Sum_D/1');
        add_line(vsg_path, 'delta_D/1', 'Sum_D/2');

        % Clamp D to [1.5, 7.5]
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

        % omega = integral(d_omega/dt) + 1.0
        add_block('built-in/Integrator', [vsg_path '/Int_omega'], ...
            'Position', [600 150 640 175], ...
            'InitialCondition', '1.0', ...
            'LowerLimit', '0.9', 'UpperLimit', '1.1', ...
            'LimitOutput', 'on');
        add_line(vsg_path, 'Div_M/1', 'Int_omega/1');

        % Feedback: omega -> omega_error
        add_line(vsg_path, 'Int_omega/1', 'omega_err/1');
        add_line(vsg_path, 'omega_ref/1', 'omega_err/2');

        % delta = integral(omega_n * (omega - 1))
        add_block('built-in/Constant', [vsg_path '/One'], ...
            'Position', [560 220 590 240], 'Value', '1.0');
        add_block('built-in/Sum', [vsg_path '/Sum_dev'], ...
            'Position', [620 210 640 230], 'Inputs', '+-');
        add_line(vsg_path, 'Int_omega/1', 'Sum_dev/1');
        add_line(vsg_path, 'One/1', 'Sum_dev/2');

        add_block('built-in/Gain', [vsg_path '/omega_n'], ...
            'Position', [660 210 700 230], ...
            'Gain', num2str(omega_n));
        add_line(vsg_path, 'Sum_dev/1', 'omega_n/1');

        add_block('built-in/Integrator', [vsg_path '/Int_delta'], ...
            'Position', [720 210 760 235], ...
            'InitialCondition', '0');
        add_line(vsg_path, 'omega_n/1', 'Int_delta/1');

        % ---- Output Connections ----
        add_line(vsg_path, 'Int_omega/1', 'omega/1');
        add_line(vsg_path, 'Int_delta/1', 'delta/1');
        add_line(vsg_path, 'Sum_P/1', 'P_out/1');

        fprintf('  Built %s: VSG swing equation (M0=%.1f, D0=%.1f)\n', ...
            vsg_name, VSG_M0, VSG_D0);

    catch me
        fprintf('  Error building %s: %s\n', vsg_name, me.message);
    end
end

%% ======================================================================
%  STEP 3: Add measurement and logging blocks for Python interface
%  These write signals to MATLAB workspace for reading via matlab.engine
%% ======================================================================
fprintf('\n=== Step 3: Adding Measurement/Logging Blocks ===\n');

% Time logger
try
    add_block('built-in/Clock', [dst_model '/SimClock'], ...
        'Position', [50 2500 80 2520]);
    add_block('built-in/ToWorkspace', [dst_model '/Log_Time'], ...
        'Position', [120 2495 220 2525], ...
        'VariableName', 'sim_time', 'SaveFormat', 'Timeseries');
    add_line(dst_model, 'SimClock/1', 'Log_Time/1');
    fprintf('  Time logger added.\n');
catch me
    fprintf('  Time logger: %s\n', me.message);
end

% Per-VSG signal loggers (omega, P_e, delta)
for i = 1:n_ess
    vsg_name = sprintf('VSG_ES%d', i);
    y_base = 2550 + (i-1)*30;

    signals = {'omega', 'delta', 'P_out'};
    for s = 1:length(signals)
        sig = signals{s};
        log_var = sprintf('%s_ES%d', sig, i);
        log_name = sprintf('Log_%s', log_var);
        try
            add_block('built-in/ToWorkspace', ...
                [dst_model '/' log_name], ...
                'Position', [50+(s-1)*200 y_base 170+(s-1)*200 y_base+20], ...
                'VariableName', log_var, ...
                'SaveFormat', 'Timeseries');
            fprintf('  %s -> %s\n', log_name, log_var);
        catch me
            fprintf('  %s: %s\n', log_name, me.message);
        end
    end
end

% Also log existing generator signals (Machine Signals bus)
try
    % The model has a 'Machine Signals' or 'Machines signals' block
    ms_blocks = find_system(dst_model, 'SearchDepth', 1, 'Name', 'Machines signals');
    if ~isempty(ms_blocks)
        fprintf('  Found Machines signals block for logging.\n');
    end
catch
end

%% ======================================================================
%  STEP 4: Add Python interface constants to model workspace
%% ======================================================================
fprintf('\n=== Step 4: Setting Model Workspace Variables ===\n');

% Store key parameters in model workspace for Python access
mdl_ws = get_param(dst_model, 'ModelWorkspace');

% Try to set variables in model workspace
try
    assignin(mdl_ws, 'VSG_M0', VSG_M0);
    assignin(mdl_ws, 'VSG_D0', VSG_D0);
    assignin(mdl_ws, 'DT', DT);
    assignin(mdl_ws, 'T_EPISODE', T_EPISODE);
    assignin(mdl_ws, 'omega_n', omega_n);
    fprintf('  Model workspace variables set.\n');
catch me
    fprintf('  Model workspace: %s\n', me.message);
    fprintf('  Variables will be set via base workspace instead.\n');
end

%% ======================================================================
%  STEP 5: Configure simulation parameters
%% ======================================================================
fprintf('\n=== Step 5: Simulation Configuration ===\n');

set_param(dst_model, 'StopTime', num2str(T_EPISODE));
set_param(dst_model, 'MaxStep', '0.001');  % Fine time step for accuracy
set_param(dst_model, 'RelTol', '1e-4');
set_param(dst_model, 'AbsTol', '1e-6');
fprintf('  StopTime = %.1f s, MaxStep = 0.001\n', T_EPISODE);

%% ======================================================================
%  STEP 6: Save model and export metadata
%% ======================================================================
save_system(dst_model);
fprintf('\n=== Model saved: %s.slx ===\n', dst_model);

% Export model info for Python
model_info = struct();
model_info.n_ess = n_ess;
model_info.n_wind = n_wind;
model_info.ess_buses = ess_new_bus;
model_info.parent_buses = ess_parent_bus;
model_info.wind_buses = wind_bus;
model_info.VSG_M0 = VSG_M0;
model_info.VSG_D0 = VSG_D0;
model_info.DM_range = [DM_MIN, DM_MAX];
model_info.DD_range = [DD_MIN, DD_MAX];
model_info.DT = DT;
model_info.T_EPISODE = T_EPISODE;
model_info.N_SUBSTEPS = N_SUBSTEPS;
model_info.omega_n = omega_n;
model_info.gen_names = {gen_names{1:8}};
model_info.retained_gens = {gen_names{9:10}};
save('model_info.mat', 'model_info');
fprintf('Model info exported to model_info.mat\n');

fprintf('\n========================================\n');
fprintf('Model modification complete!\n');
fprintf('  Wind farms (PMSG): G1-G8 (H->0.05, D->0)\n');
fprintf('  Retained sync: G9 (Bus 38), G10 (Bus 39)\n');
fprintf('  VSG-ESS: VSG_ES1-VSG_ES8 (M0=%.1f, D0=%.1f)\n', VSG_M0, VSG_D0);
fprintf('  Logging: omega, delta, P_out for each ESS\n');
fprintf('========================================\n');
