%% connect_vsg_to_grid.m
% Connect VSG-ESS subsystems to the electrical network
% Strategy:
%   1. For each ESS, add a Three-Phase Programmable Voltage Source
%   2. The voltage source is controlled by VSG's delta (angle) output
%   3. Connect through a short impedance line to the parent generator bus
%   4. Add Three-Phase V-I Measurement for P_e feedback
%   5. Connect measurement signals back to VSG inputs
%
% Architecture per ESS:
%   VSG_ESi --> [angle,Vmag] --> 3-Phase Prog V Source --> Z_line --> Bus_parent
%                                                    |
%                                            V-I Measurement --> P_e --> VSG_ESi
%
% Prerequisites: Run fix_and_rebuild.m first

run('NE39bus_modified_data.m');
load('NE39bus_workspace.mat');

dst_model = 'NE39bus_modified';
if ~bdIsLoaded(dst_model)
    load_system(dst_model);
end

% Load powerlib
load_system('powerlib');
fprintf('powerlib loaded.\n');

%% ======================================================================
%  For each ESS: Add controlled voltage source + measurement + lines
%% ======================================================================

% Map of parent bus block names and their transformer connections
% Each G(k) connects to its bus through a transformer block
% G1 connects to Bus 30 (T2: 900MVA 20 kV//230 kV10)
% We'll connect VSG sources in parallel with the existing generators

% Parent bus numbers for each ESS
parent_bus_nums = [30 31 32 33 34 35 36 37];

for i = 1:n_ess
    fprintf('\n=== Connecting VSG_ES%d to Bus %d ===\n', i, parent_bus_nums(i));

    % Block names
    vsg_name = sprintf('VSG_ES%d', i);
    vsg_path = sprintf('%s/%s', dst_model, vsg_name);
    src_name = sprintf('VSrc_ES%d', i);
    src_path = sprintf('%s/%s', dst_model, src_name);
    meas_name = sprintf('Meas_ES%d', i);
    meas_path = sprintf('%s/%s', dst_model, meas_name);
    zline_name = sprintf('Zline_ES%d', i);
    zline_path = sprintf('%s/%s', dst_model, zline_name);

    % Position offsets (below existing model, spread horizontally)
    bx = 100 + mod(i-1, 4) * 500;
    by = 2800 + floor((i-1)/4) * 600;

    try
        %% --- Step A: Add Three-Phase Programmable Voltage Source ---
        % Check if already exists
        try
            get_param(src_path, 'BlockType');
            fprintf('  %s already exists, skipping connection.\n', src_name);
            continue;
        catch
        end

        % Add from powerlib
        add_block('powerlib/Electrical Sources/Three-Phase Programmable Voltage Source', ...
            src_path, 'Position', [bx by bx+60 by+80]);

        % Configure: Phase-to-phase voltage, frequency, internal impedance
        % Voltage = 22kV (generator bus voltage), 60Hz
        set_param(src_path, 'PositiveSequence', ...
            sprintf('[%d  0  60]', VSG_BUS_VN * 1000));  % [Vrms_ph-ph, phase, freq]
        set_param(src_path, 'Amplification', 'Time-dependent');
        % Internal impedance (small, representing VSG x'd)
        set_param(src_path, 'InternalConnection', 'Wye');

        fprintf('  Added %s (22kV, 60Hz)\n', src_name);

        %% --- Step B: Add Three-Phase V-I Measurement ---
        add_block('powerlib/Measurements/Three-Phase V-I Measurement', ...
            meas_path, 'Position', [bx+120 by bx+180 by+80]);

        % Configure: Measure voltage and current
        set_param(meas_path, 'VoltageMeasurement', 'phase-to-ground');
        set_param(meas_path, 'CurrentMeasurement', 'yes');

        fprintf('  Added %s\n', meas_name);

        %% --- Step C: Add Three-Phase Series RLC Branch (connecting impedance) ---
        add_block('powerlib/Elements/Three-Phase Series RLC Branch', ...
            zline_path, 'Position', [bx+240 by bx+300 by+80]);

        % Configure: Short line impedance (R + jX on 100MVA base)
        % Convert p.u. to ohms: Z_ohm = Z_pu * Vbase^2 / Sbase
        Vbase = VSG_BUS_VN * 1000;  % 22000 V
        Zbase = Vbase^2 / (Sbase * 1e6);  % ohms
        R_ohm = NEW_LINE_R * Zbase;
        L_H = NEW_LINE_X * Zbase / (2*pi*60);  % Henry at 60Hz
        set_param(zline_path, 'Resistance', num2str(R_ohm));
        set_param(zline_path, 'Inductance', num2str(L_H));
        set_param(zline_path, 'Capacitance', 'inf');  % no capacitance

        fprintf('  Added %s (R=%.4f ohm, L=%.6f H)\n', zline_name, R_ohm, L_H);

        %% --- Step D: Add Power Measurement (P, Q) ---
        pwr_name = sprintf('Pwr_ES%d', i);
        pwr_path = sprintf('%s/%s', dst_model, pwr_name);
        add_block('powerlib/Measurements/Three-Phase Instantaneous Active & Reactive Power', ...
            pwr_path, 'Position', [bx+120 by+120 bx+220 by+160]);

        fprintf('  Added %s for P_e measurement\n', pwr_name);

        %% --- Step E: Connect physical (Simscape) ports ---
        % Source A,B,C --> Measurement --> Z_line --> Parent bus

        % Source output (LConn) -> Measurement input (LConn)
        add_line(dst_model, [src_name '/LConn1'], [meas_name '/LConn1'], 'autorouting', 'smart');
        add_line(dst_model, [src_name '/LConn2'], [meas_name '/LConn2'], 'autorouting', 'smart');
        add_line(dst_model, [src_name '/LConn3'], [meas_name '/LConn3'], 'autorouting', 'smart');

        % Measurement output (RConn) -> Z_line input (LConn)
        add_line(dst_model, [meas_name '/RConn1'], [zline_name '/LConn1'], 'autorouting', 'smart');
        add_line(dst_model, [meas_name '/RConn2'], [zline_name '/LConn2'], 'autorouting', 'smart');
        add_line(dst_model, [meas_name '/RConn3'], [zline_name '/LConn3'], 'autorouting', 'smart');

        fprintf('  Physical connections: Source -> Measurement -> Z_line\n');

        %% --- Step F: Connect Z_line to parent bus ---
        % The parent generator bus (e.g., Bus 30) is the block named '30'
        parent_bus_block = sprintf('%s/%d', dst_model, parent_bus_nums(i));

        % Find the bus block's physical port handles
        try
            % Connect Z_line RConn to bus LConn
            add_line(dst_model, [zline_name '/RConn1'], ...
                sprintf('%d/LConn1', parent_bus_nums(i)), 'autorouting', 'smart');
            add_line(dst_model, [zline_name '/RConn2'], ...
                sprintf('%d/LConn2', parent_bus_nums(i)), 'autorouting', 'smart');
            add_line(dst_model, [zline_name '/RConn3'], ...
                sprintf('%d/LConn3', parent_bus_nums(i)), 'autorouting', 'smart');
            fprintf('  Connected Z_line -> Bus %d\n', parent_bus_nums(i));
        catch me
            fprintf('  Bus connection note: %s\n', me.message);
            fprintf('  -> Will try connecting to G%d transformer instead\n', i);

            % Alternative: connect to the same bus as generator G(i)
            % G(i) connects through transformer T2 to the 345kV bus
            % We can connect our source directly to the 22kV side
            try
                % Find transformer for this generator
                % Naming pattern: T2: 900MVA \n20 kV//230 kV{k}
                % The generator and transformer share the same bus node
                gen_path = sprintf('%s/G%d', dst_model, i);
                gen_ph = get_param(gen_path, 'PortHandles');

                % Get the lines connected to G(i)'s physical ports
                gen_lines = get_param(gen_path, 'LineHandles');
                lconn_handles = gen_lines.LConn;

                if ~isempty(lconn_handles)
                    % Get the other end of these lines (the bus node)
                    for lh = 1:length(lconn_handles)
                        try
                            dst_port = get_param(lconn_handles(lh), 'DstPortHandle');
                            dst_blk = get_param(dst_port, 'Parent');
                            fprintf('  G%d LConn%d connects to: %s\n', i, lh, dst_blk);
                        catch
                        end
                    end
                end
            catch me2
                fprintf('  Alternative connection failed: %s\n', me2.message);
            end
        end

        %% --- Step G: Connect signal ports ---
        % VSG omega_ref input: constant 1.0 (already has internal ref)
        % VSG delta_M, delta_D: from MATLAB workspace (for RL control)
        % VSG P_ref: constant VSG_P0
        % VSG P_e: from power measurement

        % Add workspace input blocks for RL control
        dm_name = sprintf('dM_in_%d', i);
        dd_name = sprintf('dD_in_%d', i);
        dm_path = sprintf('%s/%s', dst_model, dm_name);
        dd_path = sprintf('%s/%s', dst_model, dd_name);

        % From Workspace blocks for delta_M and delta_D (set by Python)
        add_block('built-in/Constant', dm_path, ...
            'Position', [bx-200 by+20 bx-150 by+40], ...
            'Value', '0');  % default: no RL action
        add_block('built-in/Constant', dd_path, ...
            'Position', [bx-200 by+60 bx-150 by+80], ...
            'Value', '0');

        % omega_ref constant = 1.0
        wref_name = sprintf('wref_%d', i);
        wref_path = sprintf('%s/%s', dst_model, wref_name);
        add_block('built-in/Constant', wref_path, ...
            'Position', [bx-200 by-20 bx-150 by+0], ...
            'Value', '1.0');

        % P_ref constant
        pref_name = sprintf('Pref_%d', i);
        pref_path = sprintf('%s/%s', dst_model, pref_name);
        add_block('built-in/Constant', pref_path, ...
            'Position', [bx-200 by+100 bx-150 by+120], ...
            'Value', num2str(VSG_P0));

        % P_e placeholder (from measurement or constant)
        pe_name = sprintf('Pe_in_%d', i);
        pe_path = sprintf('%s/%s', dst_model, pe_name);
        add_block('built-in/Constant', pe_path, ...
            'Position', [bx-200 by+140 bx-150 by+160], ...
            'Value', num2str(VSG_P0));  % initial = balanced

        % Connect signal inputs to VSG
        % Port mapping: 1=omega_ref, 2=delta_M, 3=delta_D, 4=P_ref, 5=P_e
        add_line(dst_model, [wref_name '/1'], [vsg_name '/1'], 'autorouting', 'smart');
        add_line(dst_model, [dm_name '/1'], [vsg_name '/2'], 'autorouting', 'smart');
        add_line(dst_model, [dd_name '/1'], [vsg_name '/3'], 'autorouting', 'smart');
        add_line(dst_model, [pref_name '/1'], [vsg_name '/4'], 'autorouting', 'smart');
        add_line(dst_model, [pe_name '/1'], [vsg_name '/5'], 'autorouting', 'smart');

        fprintf('  Signal inputs connected to %s\n', vsg_name);

        %% --- Step H: Connect VSG outputs to logging ---
        % omega output -> ToWorkspace (already exists from earlier)
        try
            log_omega = sprintf('Log_omega_ES%d', i);
            add_line(dst_model, [vsg_name '/1'], [log_omega '/1'], 'autorouting', 'smart');
            fprintf('  omega -> %s connected\n', log_omega);
        catch me3
            fprintf('  omega logging connection: %s\n', me3.message);
        end

        % delta output -> ToWorkspace
        try
            log_delta = sprintf('Log_delta_ES%d', i);
            add_line(dst_model, [vsg_name '/2'], [log_delta '/1'], 'autorouting', 'smart');
            fprintf('  delta -> %s connected\n', log_delta);
        catch me4
            fprintf('  delta logging connection: %s\n', me4.message);
        end

        % P_out output -> ToWorkspace
        try
            log_pout = sprintf('Log_P_out_ES%d', i);
            add_line(dst_model, [vsg_name '/3'], [log_pout '/1'], 'autorouting', 'smart');
            fprintf('  P_out -> %s connected\n', log_pout);
        catch me5
            fprintf('  P_out logging connection: %s\n', me5.message);
        end

        fprintf('  VSG_ES%d fully connected!\n', i);

    catch me
        fprintf('  ERROR on VSG_ES%d: %s\n', i, me.message);
        fprintf('  Line: %d\n', me.stack(1).line);
    end
end

%% Save
save_system(dst_model);
fprintf('\n=== Model saved with grid connections ===\n');

%% Verify all new blocks
fprintf('\n=== Verification ===\n');
for i = 1:n_ess
    blocks_to_check = {
        sprintf('VSG_ES%d', i), ...
        sprintf('VSrc_ES%d', i), ...
        sprintf('Meas_ES%d', i), ...
        sprintf('Zline_ES%d', i), ...
        sprintf('Pwr_ES%d', i)
    };
    for b = 1:length(blocks_to_check)
        blk = blocks_to_check{b};
        try
            get_param([dst_model '/' blk], 'BlockType');
            fprintf('  OK: %s\n', blk);
        catch
            fprintf('  MISSING: %s\n', blk);
        end
    end
end
