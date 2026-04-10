%% fix_sm_r2025b.m
% Fix R2025b SM block compatibility issue
% Strategy: Replace G1-G8 SM blocks with Three-Phase Programmable Voltage Sources
% (since G1-G8 are PMSG wind farms with zero inertia, they behave as voltage sources)
% Keep G9, G10 as synchronous machines but fix their initialization

evalin('base', 'clear all');
evalin('base', 'run(''NE39bus_data.m'')');
load_system('powerlib');

%% Work on a fresh copy of the original model
src_model = 'NE39bus2_PQ';
dst_model = 'NE39bus_v2';

% Close if open, then copy
try close_system(dst_model, 0); catch, end
try delete([dst_model '.slx']); catch, end

load_system(src_model);
save_system(src_model, [pwd '/' dst_model '.slx']);
close_system(src_model, 0);
load_system(dst_model);

fprintf('=== Working on fresh copy: %s ===\n', dst_model);

%% Step 1: For G1-G8, replace internal SM with voltage source
% The generators are SubSystems with internal SM, turbines, etc.
% Plan: Delete the internal SM block and turbine regulators
%       Add a Three-Phase Programmable Voltage Source inside
%       Keep the external physical ports (A, B, C)

% Wind farm bus voltages from load flow (Bus kV)
wf_bus_kv = [345 22 22 22 22 22 22 22]; % G1=bus39@345kV, G2-G8=bus31-37@22kV
% Load flow voltages (pu) and angles from the Load Flow Bus blocks
wf_vlf = [1.03 0.982 0.9831 0.9972 1.012 1.049 1.063 1.028];
wf_angle = [0 0 2.466 4.423 3.398 5.698 8.494 2.181]; % degrees

% Frequency
fn = 60; % Hz (original model is 60Hz!)

for gi = 1:8
    gpath = sprintf('%s/G%d', dst_model, gi);
    fprintf('\n=== Processing G%d ===\n', gi);

    % List all blocks inside Gi
    try
        inner_blks = find_system(gpath, 'SearchDepth', 1, 'Type', 'block');
        for b = 1:length(inner_blks)
            nm = get_param(inner_blks{b}, 'Name');
            bt = get_param(inner_blks{b}, 'BlockType');
            fprintf('  Found: %s [%s]\n', nm, bt);
        end
    catch e
        fprintf('  Error listing blocks: %s\n', e.message);
        continue;
    end

    % Get the SM block path inside Gi
    sm_blk = find_system(gpath, 'SearchDepth', 2, 'MaskType', 'Synchronous Machine');
    if isempty(sm_blk)
        fprintf('  No SM found, skipping\n');
        continue;
    end

    % Get generator subsystem position
    gen_pos = get_param(gpath, 'Position');

    % Step A: Delete ALL lines inside the subsystem first
    lines = find_system(gpath, 'FindAll', 'on', 'SearchDepth', 1, 'Type', 'line');
    for l = 1:length(lines)
        try delete_line(gpath, lines(l)); catch, end
    end
    fprintf('  Deleted %d internal lines\n', length(lines));

    % Step B: Delete blocks except PMIOPorts
    % IMPORTANT: find_system returns the parent block at index 1, skip it!
    inner_blks = find_system(gpath, 'SearchDepth', 1, 'Type', 'block');
    to_delete = {};
    for b = 1:length(inner_blks)
        % Skip the parent subsystem itself
        if strcmp(inner_blks{b}, gpath)
            continue;
        end
        bt = get_param(inner_blks{b}, 'BlockType');
        nm = get_param(inner_blks{b}, 'Name');
        if strcmp(bt, 'PMIOPort')
            fprintf('  Keeping port: %s\n', nm);
            continue;
        end
        to_delete{end+1} = inner_blks{b};
    end
    for b = 1:length(to_delete)
        try
            nm = get_param(to_delete{b}, 'Name');
            delete_block(to_delete{b});
            fprintf('  Deleted: %s\n', nm);
        catch e
            fprintf('  Cannot delete %s: %s\n', to_delete{b}, e.message);
        end
    end

    % Add voltage source + series impedance inside Gi
    vsrc_name = sprintf('WF%d_Src', gi);
    vsrc_path = sprintf('%s/%s', gpath, vsrc_name);
    rlc_name = sprintf('Z%d', gi);
    rlc_path = sprintf('%s/%s', gpath, rlc_name);

    V_peak = wf_bus_kv(gi) * 1000 * wf_vlf(gi); % Voltage in V
    V_angle = wf_angle(gi);

    try
        % Use Three-Phase Source with internal impedance (EMF behind Zd')
        mc = evalin('base', 'mac_con');
        Sbase_va = mc(gi, 3) * 1e6; % Base MVA -> VA
        Vbase_v = wf_bus_kv(gi) * 1000; % kV -> V
        Zbase = Vbase_v^2 / Sbase_va;
        xd_prime = mc(gi, 7); % transient reactance pu
        ra = mc(gi, 5);
        R_ohm = max(ra * Zbase, 0.01);
        L_H = xd_prime * Zbase / (2*pi*fn);

        add_block('powerlib/Electrical Sources/Three-Phase Source', ...
            vsrc_path, 'Position', [120 50 220 150]);
        set_param(vsrc_path, ...
            'Voltage', num2str(V_peak), ...
            'PhaseAngle', num2str(V_angle), ...
            'Frequency', num2str(fn), ...
            'InternalConnection', 'Yg', ...
            'NonIdealSource', 'on', ...
            'SpecifyImpedance', 'on', ...
            'Resistance', num2str(R_ohm), ...
            'Inductance', num2str(L_H));
        fprintf('  Added %s: V=%gV, ang=%g, R=%.4f, L=%.6f\n', ...
            vsrc_name, V_peak, V_angle, R_ohm, L_H);
    catch e
        fprintf('  Failed to add source: %s\n', e.message);
        continue;
    end

    % Three-Phase Source has 3 RConn ports (A,B,C) and no LConn (internal ground)
    % Connect directly to PMIOPorts A,B,C
    ports = find_system(gpath, 'SearchDepth', 1, 'BlockType', 'PMIOPort');
    port_names = {};
    for p = 1:length(ports)
        port_names{end+1} = get_param(ports{p}, 'Name');
    end
    fprintf('  Physical ports: %s\n', strjoin(port_names, ', '));

    phase_map = {'A', 'B', 'C'};
    for p = 1:3
        port_blk = '';
        for pn = 1:length(port_names)
            if strcmpi(port_names{pn}, phase_map{p})
                port_blk = port_names{pn};
                break;
            end
        end
        if isempty(port_blk), continue; end
        try
            add_line(gpath, ...
                sprintf('%s/RConn%d', vsrc_name, p), ...
                sprintf('%s/RConn1', port_blk), ...
                'autorouting', 'smart');
            fprintf('  Connected: %s/RConn%d -> %s\n', vsrc_name, p, port_blk);
        catch e
            fprintf('  %s err: %s\n', phase_map{p}, e.message);
        end
    end
end

%% Step 2: Replace G9 and G10 SM blocks with voltage sources too
% R2025b SynchronousMachineInit has indexing bug with Standard SM params
% Replace with voltage sources behind impedance (same approach as G1-G8)
% G9 = Bus 38 (22kV), G10 = Bus 39 (345kV for G10 -> actually bus 30)
fprintf('\n=== Replacing G9 and G10 SM blocks (R2025b workaround) ===\n');

% G9: Bus 38, G10: Bus 39 (large slack bus)
retained_kv = [22 345];  % kV for G9, G10
retained_vlf = [1.027 1.03]; % pu voltage from load flow
retained_angle = [7.784 0]; % degrees
retained_H = [3.45 50.0]; % Inertia constants (used in VSG later)

for idx = 1:2
    gi = 8 + idx;
    gpath = sprintf('%s/G%d', dst_model, gi);
    fprintf('\n  Processing G%d\n', gi);

    % Delete all lines inside
    lines = find_system(gpath, 'FindAll', 'on', 'SearchDepth', 1, 'Type', 'line');
    for l = 1:length(lines)
        try delete_line(gpath, lines(l)); catch, end
    end

    % Delete all blocks except PMIOPorts
    inner_blks = find_system(gpath, 'SearchDepth', 1, 'Type', 'block');
    for b = 1:length(inner_blks)
        if strcmp(inner_blks{b}, gpath), continue; end
        bt = get_param(inner_blks{b}, 'BlockType');
        if strcmp(bt, 'PMIOPort'), continue; end
        try
            delete_block(inner_blks{b});
            fprintf('    Deleted: %s\n', get_param(inner_blks{b}, 'Name'));
        catch, end
    end

    % Add voltage source + series impedance
    vsrc_name = sprintf('SG%d_Src', gi);
    vsrc_path = sprintf('%s/%s', gpath, vsrc_name);
    rlc_name = sprintf('Z%d', gi);
    rlc_path = sprintf('%s/%s', gpath, rlc_name);

    V_peak = retained_kv(idx) * 1000 * retained_vlf(idx);
    V_angle = retained_angle(idx);

    % Use Three-Phase Source with internal impedance
    mc = evalin('base', 'mac_con');
    Sbase_va = mc(gi, 3) * 1e6;
    Vbase_v = retained_kv(idx) * 1000;
    Zbase = Vbase_v^2 / Sbase_va;
    xd_prime = mc(gi, 7);
    ra = mc(gi, 5);
    R_ohm = max(ra * Zbase, 0.01);
    L_H = xd_prime * Zbase / (2*pi*fn);

    add_block('powerlib/Electrical Sources/Three-Phase Source', ...
        vsrc_path, 'Position', [120 50 220 150]);
    set_param(vsrc_path, ...
        'Voltage', num2str(V_peak), ...
        'PhaseAngle', num2str(V_angle), ...
        'Frequency', num2str(fn), ...
        'InternalConnection', 'Yg', ...
        'NonIdealSource', 'on', ...
        'SpecifyImpedance', 'on', ...
        'Resistance', num2str(R_ohm), ...
        'Inductance', num2str(L_H));
    fprintf('    %s: V=%gV, R=%.4f, L=%.6f\n', vsrc_name, V_peak, R_ohm, L_H);

    % Wire directly to ports (Three-Phase Source has 3 RConn, no LConn)
    ports = find_system(gpath, 'SearchDepth', 1, 'BlockType', 'PMIOPort');
    phase_map = {'A', 'B', 'C'};
    for p = 1:3
        for pn = 1:length(ports)
            nm = get_param(ports{pn}, 'Name');
            if strcmpi(nm, phase_map{p})
                add_line(gpath, sprintf('%s/RConn%d', vsrc_name, p), ...
                    sprintf('%s/RConn1', nm), 'autorouting', 'smart');
                break;
            end
        end
    end

    fprintf('  G%d replaced: V=%gV, angle=%g deg (H=%.1fs for later VSG)\n', ...
        gi, V_peak, V_angle, retained_H(idx));
end

%% Step 3: Try simulation
save_system(dst_model);
fprintf('\n=== Attempting simulation ===\n');

set_param(dst_model, 'StopTime', '0.1');
try
    simOut = sim(dst_model, 'StopTime', '0.1');
    fprintf('SUCCESS! Simulation completed.\n');
catch me
    fprintf('FAIL: %s\n', me.message);
    if ~isempty(me.cause)
        fprintf('Cause: %s\n', me.cause{1}.message);
    end
    for s = 1:min(3, length(me.stack))
        fprintf('  at %s:%d\n', me.stack(s).file, me.stack(s).line);
    end
end

close_system(dst_model, 0);
fprintf('\n=== fix_sm_r2025b complete ===\n');
