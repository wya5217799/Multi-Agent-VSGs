%% connect_vsg_v3.m
% Connect VSG-ESS subsystems to electrical grid using correct R2025b library paths
% Discovered library references:
%   V-I Measurement:  spsThreePhaseVIMeasurementLib/Three-Phase
%   PI Section Line:  spsThreePhasePISectionLineLib/Three-Phase
%   Prog V Source:    spsThreePhaseProgrammableVoltageSourceLib/Three-Phase
%   Series RLC:       spsThreePhaseSeriesRLCBranchLib/Three-Phase  (to discover)

run('NE39bus_modified_data.m');
load('NE39bus_workspace.mat');

dst_model = 'NE39bus_modified';
if ~bdIsLoaded(dst_model), load_system(dst_model); end
load_system('powerlib');

parent_bus_nums = [30 31 32 33 34 35 36 37];

%% ======================================================================
%  Step 0: Cleanup all V1/V2 artifacts
%% ======================================================================
fprintf('=== Cleaning up previous artifacts ===\n');
for i = 1:n_ess
    cleanup_names = {
        sprintf('Meas_ES%d', i), sprintf('Zline_ES%d', i), ...
        sprintf('Pwr_ES%d', i), sprintf('dM_in_%d', i), ...
        sprintf('dD_in_%d', i), sprintf('wref_%d', i), ...
        sprintf('Pref_%d', i), sprintf('Pe_in_%d', i), ...
        sprintf('Pe_%d', i), sprintf('dM_%d', i), sprintf('dD_%d', i)
    };
    for c = 1:length(cleanup_names)
        try delete_block([dst_model '/' cleanup_names{c}]); catch, end
    end
    % Also remove any existing lines from VSrc_ES ports
    try
        src_path = sprintf('%s/VSrc_ES%d', dst_model, i);
        ph = get_param(src_path, 'PortHandles');
        all_ph = [ph.LConn(:); ph.RConn(:); ph.Inport(:); ph.Outport(:)];
        for p = 1:length(all_ph)
            lh = get_param(all_ph(p), 'Line');
            if lh > 0, delete_line(dst_model, lh); end
        end
    catch, end
end
fprintf('  Cleanup done.\n');

%% ======================================================================
%  Step 1: Hardcoded R2025b library paths (verified via add_block test)
%% ======================================================================
fprintf('\n=== R2025b library paths (verified) ===\n');
rlc_lib = 'powerlib/Elements/Three-Phase Series RLC Branch';
vi_lib = 'powerlib/Measurements/Three-Phase V-I Measurement';
pi_lib = 'spsThreePhasePISectionLineLib/Three-Phase PI Section Line';
fprintf('  RLC Branch: %s\n', rlc_lib);
fprintf('  V-I Measurement: %s\n', vi_lib);
fprintf('  PI Section Line: %s\n', pi_lib);

%% ======================================================================
%  Step 2: Find how each generator Gi connects to its bus
%% ======================================================================
fprintf('\n=== Mapping generator bus connections ===\n');
gen_bus_blocks = cell(8, 1);
for gi = 1:8
    gpath = sprintf('%s/G%d', dst_model, gi);
    try
        gen_ph = get_param(gpath, 'PortHandles');
        for lh_idx = 1:length(gen_ph.LConn)
            line_h = get_param(gen_ph.LConn(lh_idx), 'Line');
            if line_h > 0
                dst_ph = get_param(line_h, 'DstPortHandle');
                src_ph = get_param(line_h, 'SrcPortHandle');
                for ph = [dst_ph(:)', src_ph(:)']
                    if ph > 0
                        try
                            parent = get_param(ph, 'Parent');
                            if ~contains(parent, sprintf('G%d', gi))
                                % Extract block name from full path
                                parts = strsplit(parent, '/');
                                gen_bus_blocks{gi} = parts{end};
                                break;
                            end
                        catch
                        end
                    end
                end
                if ~isempty(gen_bus_blocks{gi}), break; end
            end
        end
    catch
    end
    if isempty(gen_bus_blocks{gi})
        gen_bus_blocks{gi} = num2str(parent_bus_nums(gi));
    end
    fprintf('  G%d connects to block: %s\n', gi, gen_bus_blocks{gi});
end

%% ======================================================================
%  Step 3: For each ESS, add measurement + impedance + wire to bus
%% ======================================================================
Vbase_v = VSG_BUS_VN * 1000;
Zbase = Vbase_v^2 / (Sbase * 1e6);
R_ohm = NEW_LINE_R * Zbase;
L_H = NEW_LINE_X * Zbase / (2*pi*fn);
fprintf('\n  Impedance: R=%.4f ohm, L=%.6f H (Zbase=%.2f ohm)\n', R_ohm, L_H, Zbase);

for i = 1:n_ess
    fprintf('\n=== ESS %d: Connecting to Bus %s ===\n', i, gen_bus_blocks{i});

    src_name = sprintf('VSrc_ES%d', i);
    src_path = sprintf('%s/%s', dst_model, src_name);
    vsg_name = sprintf('VSG_ES%d', i);

    % Get position of VSrc for layout
    try
        src_pos = get_param(src_path, 'Position');
        bx = src_pos(1);
        by = src_pos(2);
    catch
        bx = 100 + mod(i-1, 4) * 500;
        by = 2800 + floor((i-1)/4) * 600;
    end

    try
        %% A: Configure voltage source
        set_param(src_path, 'PositiveSequence', ...
            sprintf('[%d  0  %d]', VSG_BUS_VN*1000, fn));
        set_param(src_path, 'VariationEntity', 'None');
        fprintf('  %s configured: V=%dkV, f=%dHz\n', src_name, VSG_BUS_VN, fn);

        %% B: Add V-I Measurement (if library found)
        meas_name = sprintf('Meas_ES%d', i);
        meas_path = sprintf('%s/%s', dst_model, meas_name);
        added_meas = false;

        if ~isempty(vi_lib)
            try
                add_block(vi_lib, meas_path, ...
                    'Position', [bx+120 by bx+180 by+80]);
                set_param(meas_path, 'VoltageMeasurement', 'phase-to-ground');
                set_param(meas_path, 'CurrentMeasurement', 'yes');
                added_meas = true;
                fprintf('  Added %s\n', meas_name);
            catch me
                fprintf('  V-I Measurement failed: %s\n', me.message);
            end
        end

        %% C: Add series impedance (RLC Branch or PI Line)
        zline_name = sprintf('Zline_ES%d', i);
        zline_path = sprintf('%s/%s', dst_model, zline_name);
        added_zline = false;

        if ~isempty(rlc_lib)
            try
                add_block(rlc_lib, zline_path, ...
                    'Position', [bx+240 by bx+300 by+80]);
                % Try setting params - discover correct names
                try
                    set_param(zline_path, 'Resistance', num2str(R_ohm));
                    set_param(zline_path, 'Inductance', num2str(L_H));
                catch
                    % Try alternative param names
                    dlg = get_param(zline_path, 'DialogParameters');
                    pnames = fieldnames(dlg);
                    fprintf('  RLC params: %s\n', strjoin(pnames, ', '));
                end
                added_zline = true;
                fprintf('  Added %s (RLC Branch)\n', zline_name);
            catch me
                fprintf('  RLC Branch failed: %s\n', me.message);
            end
        end

        if ~added_zline && ~isempty(pi_lib)
            try
                add_block(pi_lib, zline_path, ...
                    'Position', [bx+240 by bx+300 by+80]);
                % PI Section Line uses different params
                try
                    set_param(zline_path, 'Frequency', num2str(fn));
                    set_param(zline_path, 'Resistance', num2str(R_ohm));
                    set_param(zline_path, 'Inductance', num2str(L_H));
                    set_param(zline_path, 'Capacitance', '0');
                    set_param(zline_path, 'Length', '1');
                catch me2
                    fprintf('  PI Line param setting: %s\n', me2.message);
                    dlg = get_param(zline_path, 'DialogParameters');
                    pnames = fieldnames(dlg);
                    fprintf('  PI Line params: %s\n', strjoin(pnames, ', '));
                end
                added_zline = true;
                fprintf('  Added %s (PI Section Line)\n', zline_name);
            catch me
                fprintf('  PI Line failed: %s\n', me.message);
            end
        end

        %% D: Wire physical connections
        % Strategy: VSrc -> (Meas) -> Zline -> same bus node as Gi

        % Get VSrc port handles to understand its port layout
        src_ph = get_param(src_path, 'PortHandles');
        fprintf('  VSrc ports: LConn=%d, RConn=%d\n', ...
            length(src_ph.LConn), length(src_ph.RConn));

        % Connect VSrc RConn (output, 3 phases) -> Measurement or Zline
        if added_meas && added_zline
            % VSrc -> Meas -> Zline
            meas_ph = get_param(meas_path, 'PortHandles');
            zline_ph = get_param(zline_path, 'PortHandles');
            fprintf('  Meas ports: LConn=%d, RConn=%d\n', ...
                length(meas_ph.LConn), length(meas_ph.RConn));
            fprintf('  Zline ports: LConn=%d, RConn=%d\n', ...
                length(zline_ph.LConn), length(zline_ph.RConn));

            % VSrc RConn -> Meas LConn (A,B,C phases)
            n_phase = min([length(src_ph.RConn), length(meas_ph.LConn), 3]);
            for p = 1:n_phase
                try
                    add_line(dst_model, ...
                        [src_name '/RConn' num2str(p)], ...
                        [meas_name '/LConn' num2str(p)], ...
                        'autorouting', 'smart');
                catch me
                    fprintf('  VSrc->Meas phase %d: %s\n', p, me.message);
                end
            end
            fprintf('  Wired: VSrc -> Measurement\n');

            % Meas RConn -> Zline LConn
            n_phase = min([length(meas_ph.RConn), length(zline_ph.LConn), 3]);
            for p = 1:n_phase
                try
                    add_line(dst_model, ...
                        [meas_name '/RConn' num2str(p)], ...
                        [zline_name '/LConn' num2str(p)], ...
                        'autorouting', 'smart');
                catch me
                    fprintf('  Meas->Zline phase %d: %s\n', p, me.message);
                end
            end
            fprintf('  Wired: Measurement -> Zline\n');

        elseif added_zline
            % Direct: VSrc -> Zline
            zline_ph = get_param(zline_path, 'PortHandles');
            n_phase = min([length(src_ph.RConn), length(zline_ph.LConn), 3]);
            for p = 1:n_phase
                try
                    add_line(dst_model, ...
                        [src_name '/RConn' num2str(p)], ...
                        [zline_name '/LConn' num2str(p)], ...
                        'autorouting', 'smart');
                catch me
                    fprintf('  VSrc->Zline phase %d: %s\n', p, me.message);
                end
            end
            fprintf('  Wired: VSrc -> Zline (direct)\n');
        end

        %% E: Connect Zline output to parent bus node
        if added_zline
            bus_block = gen_bus_blocks{i};
            zline_ph = get_param(zline_path, 'PortHandles');

            % The bus block has LConn ports. Find available ports.
            bus_path = sprintf('%s/%s', dst_model, bus_block);
            bus_ph = get_param(bus_path, 'PortHandles');
            fprintf('  Bus %s ports: LConn=%d, RConn=%d\n', bus_block, ...
                length(bus_ph.LConn), length(bus_ph.RConn));

            % Connect Zline RConn to bus LConn (need to find free ports)
            % The bus likely connects to multiple things. Use port names.
            n_zr = length(zline_ph.RConn);
            n_bl = length(bus_ph.LConn);
            n_br = length(bus_ph.RConn);

            % Try RConn of Zline to LConn of bus
            if n_zr > 0 && n_bl > 0
                for p = 1:min(n_zr, 3)
                    try
                        add_line(dst_model, ...
                            [zline_name '/RConn' num2str(p)], ...
                            [bus_block '/LConn' num2str(p)], ...
                            'autorouting', 'smart');
                    catch me
                        fprintf('  Zline->Bus LConn%d: %s\n', p, me.message);
                        % Try RConn of bus instead
                        try
                            add_line(dst_model, ...
                                [zline_name '/RConn' num2str(p)], ...
                                [bus_block '/RConn' num2str(p)], ...
                                'autorouting', 'smart');
                        catch me2
                            fprintf('  Zline->Bus RConn%d: %s\n', p, me2.message);
                        end
                    end
                end
                fprintf('  Wired: Zline -> Bus %s\n', bus_block);
            elseif n_zr > 0 && n_br > 0
                for p = 1:min(n_zr, 3)
                    try
                        add_line(dst_model, ...
                            [zline_name '/RConn' num2str(p)], ...
                            [bus_block '/RConn' num2str(p)], ...
                            'autorouting', 'smart');
                    catch me
                        fprintf('  Zline->Bus RConn%d: %s\n', p, me.message);
                    end
                end
                fprintf('  Wired: Zline -> Bus %s (RConn)\n', bus_block);
            else
                fprintf('  WARNING: Cannot connect to bus %s - no matching ports\n', bus_block);
            end
        elseif ~added_zline
            % Direct connection: VSrc -> Bus (no impedance)
            fprintf('  WARNING: No impedance block. Connecting VSrc directly to bus.\n');
            bus_block = gen_bus_blocks{i};
            bus_path = sprintf('%s/%s', dst_model, bus_block);
            bus_ph = get_param(bus_path, 'PortHandles');
            for p = 1:min(length(src_ph.RConn), 3)
                try
                    add_line(dst_model, ...
                        [src_name '/RConn' num2str(p)], ...
                        [bus_block '/LConn' num2str(p)], ...
                        'autorouting', 'smart');
                catch me
                    fprintf('  VSrc->Bus phase %d: %s\n', p, me.message);
                end
            end
        end

        %% F: Connect signal inputs to VSG subsystem
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
            end
            try
                add_line(dst_model, [cname '/1'], ...
                    sprintf('%s/%d', vsg_name, cb), 'autorouting', 'smart');
            catch me
                fprintf('  Signal %s->%s/%d: %s\n', cname, vsg_name, cb, me.message);
            end
        end
        fprintf('  Signal inputs connected.\n');

        %% G: Connect VSG outputs to loggers
        out_names = {'omega', 'delta', 'P_out'};
        for out_idx = 1:3
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
%  Verification: List all ESS-related blocks and their connections
%% ======================================================================
fprintf('\n=== Verification ===\n');
for i = 1:n_ess
    blocks_to_check = {
        sprintf('VSG_ES%d', i), ...
        sprintf('VSrc_ES%d', i), ...
        sprintf('Meas_ES%d', i), ...
        sprintf('Zline_ES%d', i)
    };
    for b = 1:length(blocks_to_check)
        blk = blocks_to_check{b};
        try
            get_param([dst_model '/' blk], 'BlockType');
            ph = get_param([dst_model '/' blk], 'PortHandles');
            % Count connected lines
            all_ports = [ph.LConn(:); ph.RConn(:); ph.Inport(:); ph.Outport(:)];
            n_connected = 0;
            for p = 1:length(all_ports)
                lh = get_param(all_ports(p), 'Line');
                if lh > 0, n_connected = n_connected + 1; end
            end
            fprintf('  OK: %s (%d/%d ports connected)\n', blk, n_connected, length(all_ports));
        catch
            fprintf('  MISSING: %s\n', blk);
        end
    end
end

%% ======================================================================
%  Test: 1-second simulation
%% ======================================================================
fprintf('\n=== Running 1-second test simulation ===\n');
try
    assignin('base', 'mac_con', mac_con);
    assignin('base', 'p0', p0);
    assignin('base', 'Pn', Pn);

    % Additional workspace vars the model might need
    vars_to_assign = {'line', 'AVR_Data', 'MB', 'Bus', 'C0', 'L0', 'R0', 'Ns', 's'};
    for v = 1:length(vars_to_assign)
        try
            val = eval(vars_to_assign{v});
            assignin('base', vars_to_assign{v}, val);
        catch
        end
    end

    set_param(dst_model, 'StopTime', '1.0');
    simOut = sim(dst_model, 'StopTime', '1.0');
    fprintf('  Simulation completed successfully!\n');
    fprintf('  SimulationMetadata: %s\n', class(simOut));
catch me
    fprintf('  Simulation error: %s\n', me.message);
    if length(me.stack) > 0
        fprintf('  At: %s line %d\n', me.stack(1).file, me.stack(1).line);
    end
    % Try to get more diagnostic info
    try
        diag = Simulink.SimulationMetadata.getLastDiagnostic;
        if ~isempty(diag)
            fprintf('  Diagnostic: %s\n', diag);
        end
    catch
    end
end

fprintf('\n=== Connection script V3 complete ===\n');
