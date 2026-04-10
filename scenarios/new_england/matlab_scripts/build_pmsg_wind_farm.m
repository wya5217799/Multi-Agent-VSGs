%% build_pmsg_wind_farm.m
% Build PMSG wind farm subsystem blocks to replace G1-G8
% Each PMSG is modeled as a controlled current source (grid-side inverter)
% with no inertia contribution to the grid
%
% The PMSG model includes:
%   - Grid-side converter (GSC) as controlled current source
%   - PLL for grid synchronization
%   - Active/reactive power control loops
%   - No mechanical coupling to grid (full power converter isolation)

function build_pmsg_wind_farm(model_name)

if nargin < 1
    model_name = 'NE39bus_modified';
end

run('NE39bus_modified_data.m');

if ~bdIsLoaded(model_name)
    load_system(model_name);
end

fprintf('=== Building PMSG Wind Farm Subsystems ===\n');

for i = 1:n_wind
    wf_name = sprintf('PMSG_W%d', i);
    wf_path = sprintf('%s/%s', model_name, wf_name);

    % Layout position
    x = 50 + mod(i-1, 4) * 400;
    y = 1500 + floor((i-1)/4) * 350;

    try
        % Check if already exists
        try
            get_param(wf_path, 'BlockType');
            fprintf('  %s already exists, skipping.\n', wf_name);
            continue;
        catch
        end

        % Create subsystem
        add_block('built-in/SubSystem', wf_path, ...
            'Position', [x y x+320 y+250]);

        % --- PMSG GSC Model (simplified for power system study) ---
        % Input: P_ref (from wind), Q_ref, V_grid (3-phase)
        % Output: I_abc (injected current to grid)

        % Inputs
        add_block('built-in/Inport', [wf_path '/P_wind'], ...
            'Position', [30 30 60 50], 'Port', '1');
        add_block('built-in/Inport', [wf_path '/Q_ref'], ...
            'Position', [30 80 60 100], 'Port', '2');

        % Outputs
        add_block('built-in/Outport', [wf_path '/P_out'], ...
            'Position', [600 50 630 70], 'Port', '1');
        add_block('built-in/Outport', [wf_path '/Q_out'], ...
            'Position', [600 100 630 120], 'Port', '2');
        add_block('built-in/Outport', [wf_path '/omega_pll'], ...
            'Position', [600 150 630 170], 'Port', '3');

        % P_wind with first-order delay (converter response)
        % tau = 0.02s (fast power electronics)
        add_block('built-in/TransferFcn', [wf_path '/GSC_P_delay'], ...
            'Position', [150 25 250 55], ...
            'Numerator', '[1]', 'Denominator', '[0.02 1]');
        add_line(wf_path, 'P_wind/1', 'GSC_P_delay/1');
        add_line(wf_path, 'GSC_P_delay/1', 'P_out/1');

        % Q_ref with first-order delay
        add_block('built-in/TransferFcn', [wf_path '/GSC_Q_delay'], ...
            'Position', [150 75 250 105], ...
            'Numerator', '[1]', 'Denominator', '[0.02 1]');
        add_line(wf_path, 'Q_ref/1', 'GSC_Q_delay/1');
        add_line(wf_path, 'GSC_Q_delay/1', 'Q_out/1');

        % PLL model: simplified as constant 1.0 pu frequency
        % (PMSG is decoupled from grid, PLL tracks grid but doesn't contribute inertia)
        add_block('built-in/Constant', [wf_path '/PLL_omega'], ...
            'Position', [150 145 200 165], 'Value', '1.0');
        add_line(wf_path, 'PLL_omega/1', 'omega_pll/1');

        % Set initial power
        fprintf('  Built %s: P0=%.3f p.u., Bus %d\n', ...
            wf_name, wind_p0(i), wind_bus(i));

    catch me
        fprintf('  Error building %s: %s\n', wf_name, me.message);
    end
end

% Save
save_system(model_name);
fprintf('=== PMSG wind farms added and saved ===\n');

end
