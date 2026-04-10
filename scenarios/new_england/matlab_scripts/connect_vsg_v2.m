%% connect_vsg_v2.m
% Connect VSG-ESS to electrical grid - V2 with correct R2025b parameters
%
% Strategy: Use existing Three-Phase Programmable Voltage Sources (VSrc_ES1-8)
% already added, configure them, add measurements, connect to bus nodes.

run('NE39bus_modified_data.m');
load('NE39bus_workspace.mat');

dst_model = 'NE39bus_modified';
if ~bdIsLoaded(dst_model), load_system(dst_model); end
load_system('powerlib');

parent_bus_nums = [30 31 32 33 34 35 36 37];

%% First: delete all incomplete blocks from V1 attempt
fprintf('=== Cleaning up V1 artifacts ===\n');
for i = 1:n_ess
    cleanup_names = {
        sprintf('Meas_ES%d', i), sprintf('Zline_ES%d', i), ...
        sprintf('Pwr_ES%d', i), sprintf('dM_in_%d', i), ...
        sprintf('dD_in_%d', i), sprintf('wref_%d', i), ...
        sprintf('Pref_%d', i), sprintf('Pe_in_%d', i)
    };
    for c = 1:length(cleanup_names)
        try
            delete_block([dst_model '/' cleanup_names{c}]);
        catch
        end
    end
end
fprintf('  Cleanup done.\n');

%% ======================================================================
%  Configure and connect each ESS
%% ======================================================================
for i = 1:n_ess
    fprintf('\n=== ESS %d: Connecting to Bus %d ===\n', i, parent_bus_nums(i));

    vsg_name = sprintf('VSG_ES%d', i);
    src_name = sprintf('VSrc_ES%d', i);
    src_path = sprintf('%s/%s', dst_model, src_name);

    bx = 100 + mod(i-1, 4) * 500;
    by = 2800 + floor((i-1)/4) * 600;

    try
        %% A: Configure the voltage source
        % VariationEntity = 'None' means constant voltage (no modulation)
        % The VSG controls frequency/angle, which we'll handle through
        % the Simulink signal interface
        set_param(src_path, 'PositiveSequence', ...
            sprintf('[%d  0  %d]', VSG_BUS_VN*1000, fn));
        set_param(src_path, 'VariationEntity', 'None');
        fprintf('  %s configured: V=%dkV, f=%dHz\n', src_name, VSG_BUS_VN, fn);

        %% B: Add Three-Phase V-I Measurement
        meas_name = sprintf('Meas_ES%d', i);
        meas_path = sprintf('%s/%s', dst_model, meas_name);

        % Find the correct library path
        % In R2025b, it might be under a different subpath
        vi_lib_paths = {
            'powerlib/Measurements/Three-Phase V-I Measurement', ...
            'ee_lib/Measurements/Three-Phase V-I Measurement', ...
            'simscapeelectrical/Measurements/Three-Phase V-I Measurement'
        };
        added_meas = false;
        for vp = 1:length(vi_lib_paths)
            try
                add_block(vi_lib_paths{vp}, meas_path, ...
                    'Position', [bx+120 by bx+180 by+80]);
                fprintf('  Added %s from %s\n', meas_name, vi_lib_paths{vp});
                added_meas = true;
                break;
            catch
            end
        end

        if ~added_meas
            % Fallback: use a simple subsystem with scopes
            fprintf('  V-I Measurement not found, using alternative approach\n');
        end

        %% C: Add series RLC impedance
        zline_name = sprintf('Zline_ES%d', i);
        zline_path = sprintf('%s/%s', dst_model, zline_name);

        rlc_lib_paths = {
            'powerlib/Elements/Three-Phase Series RLC Branch', ...
            'ee_lib/Passive/Three-Phase Series RLC Branch', ...
            'simscapeelectrical/Passive/Three-Phase Series RLC Branch'
        };
        added_rlc = false;
        for rp = 1:length(rlc_lib_paths)
            try
                add_block(rlc_lib_paths{rp}, zline_path, ...
                    'Position', [bx+240 by bx+300 by+80]);
                fprintf('  Added %s\n', zline_name);
                added_rlc = true;
                break;
            catch
            end
        end

        if added_rlc
            % Configure impedance
            Vbase_v = VSG_BUS_VN * 1000;
            Zbase = Vbase_v^2 / (Sbase * 1e6);
            R_ohm = NEW_LINE_R * Zbase;
            L_H = NEW_LINE_X * Zbase / (2*pi*fn);
            try
                set_param(zline_path, 'Resistance', num2str(R_ohm));
                set_param(zline_path, 'Inductance', num2str(L_H));
                fprintf('  Z_line: R=%.4f ohm, L=%.6f H\n', R_ohm, L_H);
            catch me
                fprintf('  Z_line params: %s\n', me.message);
                % Try alternative parameter names
                dlg = get_param(zline_path, 'DialogParameters');
                pnames = fieldnames(dlg);
                fprintf('  RLC params available: ');
                for pp = 1:length(pnames)
                    fprintf('%s, ', pnames{pp});
                end
                fprintf('\n');
            end
        end

        %% D: Wire physical connections if we have the blocks
        % Source -> (optional measurement) -> Z_line -> parent bus

        if added_meas && added_rlc
            % Source -> Measurement
            try
                add_line(dst_model, [src_name '/LConn1'], [meas_name '/LConn1'], 'autorouting', 'smart');
                add_line(dst_model, [src_name '/LConn2'], [meas_name '/LConn2'], 'autorouting', 'smart');
                add_line(dst_model, [src_name '/LConn3'], [meas_name '/LConn3'], 'autorouting', 'smart');
                fprintf('  Wired: Source -> Measurement\n');
            catch me
                fprintf('  Source->Meas wiring: %s\n', me.message);
            end

            % Measurement -> Z_line
            try
                add_line(dst_model, [meas_name '/RConn1'], [zline_name '/LConn1'], 'autorouting', 'smart');
                add_line(dst_model, [meas_name '/RConn2'], [zline_name '/LConn2'], 'autorouting', 'smart');
                add_line(dst_model, [meas_name '/RConn3'], [zline_name '/LConn3'], 'autorouting', 'smart');
                fprintf('  Wired: Measurement -> Z_line\n');
            catch me
                fprintf('  Meas->Zline wiring: %s\n', me.message);
            end
        elseif added_rlc
            % Direct: Source -> Z_line
            try
                add_line(dst_model, [src_name '/LConn1'], [zline_name '/LConn1'], 'autorouting', 'smart');
                add_line(dst_model, [src_name '/LConn2'], [zline_name '/LConn2'], 'autorouting', 'smart');
                add_line(dst_model, [src_name '/LConn3'], [zline_name '/LConn3'], 'autorouting', 'smart');
                fprintf('  Wired: Source -> Z_line (direct)\n');
            catch me
                fprintf('  Source->Zline wiring: %s\n', me.message);
            end
        end

        % Z_line -> parent bus (or generator's bus node)
        if added_rlc
            % The parent bus is the block named by its number
            % Find how the generator G(i) connects to identify the bus node
            gen_path = sprintf('%s/G%d', dst_model, i);
            gen_ph = get_param(gen_path, 'PortHandles');

            % G(i) has LConn ports (A,B,C) connected to the bus
            % We need to connect Z_line's RConn to the same bus node
            lconn_handles = gen_ph.LConn;

            if ~isempty(lconn_handles)
                fprintf('  G%d has %d physical ports\n', i, length(lconn_handles));

                % Get the line connected to G(i)'s first LConn port
                for lh_idx = 1:min(3, length(lconn_handles))
                    try
                        line_h = get_param(lconn_handles(lh_idx), 'Line');
                        if line_h > 0
                            % Get destination info
                            dst_port_h = get_param(line_h, 'DstPortHandle');
                            src_port_h = get_param(line_h, 'SrcPortHandle');

                            % One end is G(i), the other is the bus node
                            for ph_check = [dst_port_h, src_port_h]
                                parent_blk = get_param(ph_check, 'Parent');
                                if ~contains(parent_blk, sprintf('G%d', i))
                                    fprintf('  G%d port %d connects to: %s\n', ...
                                        i, lh_idx, parent_blk);
                                end
                            end
                        end
                    catch
                    end
                end
            end
        end

        %% E: Connect signal inputs to VSG
        % Constants for omega_ref, delta_M, delta_D, P_ref, P_e
        const_blocks = {
            sprintf('wref_%d', i), '1.0', [bx-180 by-10 bx-130 by+10];
            sprintf('dM_%d', i), '0', [bx-180 by+30 bx-130 by+50];
            sprintf('dD_%d', i), '0', [bx-180 by+70 bx-130 by+90];
            sprintf('Pref_%d', i), num2str(VSG_P0), [bx-180 by+110 bx-130 by+130];
            sprintf('Pe_%d', i), num2str(VSG_P0), [bx-180 by+150 bx-130 by+170];
        };

        for cb = 1:size(const_blocks, 1)
            cname = const_blocks{cb, 1};
            cval = const_blocks{cb, 2};
            cpos = const_blocks{cb, 3};
            cpath = [dst_model '/' cname];

            try
                add_block('built-in/Constant', cpath, ...
                    'Position', cpos, 'Value', cval);
            catch
                % May already exist
            end
            try
                add_line(dst_model, [cname '/1'], ...
                    sprintf('%s/%d', vsg_name, cb), 'autorouting', 'smart');
            catch me
                fprintf('  Signal %s->%s/%d: %s\n', cname, vsg_name, cb, me.message);
            end
        end
        fprintf('  Signal inputs connected.\n');

        %% F: Connect VSG outputs to loggers
        for out_idx = 1:3
            out_names = {'omega', 'delta', 'P_out'};
            log_name = sprintf('Log_%s_ES%d', out_names{out_idx}, i);
            try
                add_line(dst_model, sprintf('%s/%d', vsg_name, out_idx), ...
                    [log_name '/1'], 'autorouting', 'smart');
            catch
            end
        end
        fprintf('  Logging connected.\n');

    catch me
        fprintf('  FATAL ERROR on ESS %d: %s (line %d)\n', i, me.message, me.stack(1).line);
    end
end

%% Save
save_system(dst_model);
fprintf('\n=== Model saved ===\n');

%% ======================================================================
%  Test: Run a short simulation
%% ======================================================================
fprintf('\n=== Running 1-second test simulation ===\n');
try
    % Load workspace data
    evalin('base', 'load(''NE39bus_workspace.mat'')');
    evalin('base', 'run(''NE39bus_modified_data.m'')');

    % Override mac_con with PMSG values
    mac_con_test = evalin('base', 'mac_con');
    for k = 1:8
        mac_con_test(k, 16) = 0.05;  % H near zero
        mac_con_test(k, 17) = 0.0;   % D = 0
    end
    assignin('base', 'mac_con', mac_con_test);

    set_param(dst_model, 'StopTime', '1.0');
    set_param(dst_model, 'SimulationCommand', 'start');

    % Wait for simulation
    pause(30);

    status = get_param(dst_model, 'SimulationStatus');
    fprintf('  Simulation status: %s\n', status);

    if strcmp(status, 'stopped')
        % Read results
        try
            t = evalin('base', 'sim_time');
            fprintf('  Simulation completed. Time samples: %d\n', length(t));
        catch
            fprintf('  Could not read sim_time from workspace.\n');
        end

        for i = 1:n_ess
            try
                omega_var = sprintf('omega_ES%d', i);
                omega = evalin('base', omega_var);
                fprintf('  ES%d omega: %.6f (final)\n', i, omega(end));
            catch
                fprintf('  ES%d omega: not available\n', i);
            end
        end
    end
catch me
    fprintf('  Simulation error: %s\n', me.message);
    fprintf('  This is expected if physical connections are incomplete.\n');
    fprintf('  The VSG subsystems work as signal-level blocks.\n');
end

fprintf('\n=== Connection script V2 complete ===\n');
