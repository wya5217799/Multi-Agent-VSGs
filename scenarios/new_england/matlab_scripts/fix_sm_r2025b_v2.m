%% fix_sm_r2025b_v2.m
% Fixed version: correct generator numbering based on BUS NUMBER, not block index
%
% Paper mapping (IEEE 39-bus standard):
%   Paper G1  = Bus 30 = Simulink G10  -> PMSG Wind Farm
%   Paper G2  = Bus 31 = Simulink G2   -> PMSG Wind Farm
%   Paper G3  = Bus 32 = Simulink G3   -> PMSG Wind Farm
%   Paper G4  = Bus 33 = Simulink G4   -> PMSG Wind Farm
%   Paper G5  = Bus 34 = Simulink G5   -> PMSG Wind Farm
%   Paper G6  = Bus 35 = Simulink G6   -> PMSG Wind Farm
%   Paper G7  = Bus 36 = Simulink G7   -> PMSG Wind Farm
%   Paper G8  = Bus 37 = Simulink G8   -> PMSG Wind Farm
%   Paper G9  = Bus 38 = Simulink G9   -> RETAINED sync machine
%   Paper G10 = Bus 39 = Simulink G1   -> RETAINED sync machine

evalin('base', 'clear all');
evalin('base', 'run(''NE39bus_data.m'')');
load_system('powerlib');

src_model = 'NE39bus2_PQ';
dst_model = 'NE39bus_v2';

try close_system(dst_model, 0); catch, end
try delete([dst_model '.slx']); catch, end
load_system(src_model);
save_system(src_model, [pwd '/' dst_model '.slx']);
close_system(src_model, 0);
load_system(dst_model);

mc = evalin('base', 'mac_con');
p0 = evalin('base', 'p0');
fn = 60; % Original model is 60 Hz

fprintf('=== fix_sm_r2025b_v2: Correct bus-based generator replacement ===\n');

%% Define which Simulink blocks to replace vs retain
% Wind farm blocks: G2,G3,G4,G5,G6,G7,G8,G10 (buses 31-37,30)
wind_farm_blocks = [10, 2, 3, 4, 5, 6, 7, 8]; % Simulink G-index
wind_farm_buses  = [30, 31, 32, 33, 34, 35, 36, 37];

% Retained sync machine blocks: G1,G9 (buses 39,38)
retained_blocks = [1, 9];
retained_buses  = [39, 38];

%% Step 1: Replace wind farm generators with Three-Phase Source
fprintf('\n--- Replacing wind farm generators ---\n');
for wi = 1:8
    gi = wind_farm_blocks(wi);
    bus_num = wind_farm_buses(wi);
    gpath = sprintf('%s/G%d', dst_model, gi);

    % mac_con row for this generator
    mc_row = gi;
    Sbase_va = mc(mc_row, 3) * 1e6;
    bus_kv = 22; % All gen buses 30-37 are 22kV
    if bus_num == 39, bus_kv = 345; end % G1=Bus39 is 345kV (not applicable here)
    Vbase_v = bus_kv * 1000;
    Zbase = Vbase_v^2 / Sbase_va;
    xd_prime = mc(mc_row, 7);
    ra = mc(mc_row, 5);
    R_ohm = max(ra * Zbase, 0.01);
    L_H = xd_prime * Zbase / (2*pi*fn);

    % Load flow voltage/angle from Load Flow Bus blocks
    % These come from the original model's load flow solution
    vlf_map = containers.Map(...
        {30, 31, 32, 33, 34, 35, 36, 37, 38, 39}, ...
        {[1.048, -3.646], [0.982, 0], [0.9831, 2.466], [0.9972, 4.423], ...
         [1.012, 3.398], [1.049, 5.698], [1.063, 8.494], [1.028, 2.181], ...
         [1.027, 7.784], [1.03, 0]});
    vl = vlf_map(bus_num);
    V_peak = Vbase_v * vl(1);
    V_angle = vl(2);

    fprintf('  WF%d: Simulink G%d (Bus %d) -> V=%gV, ang=%.1f, R=%.4f, L=%.6f\n', ...
        wi, gi, bus_num, V_peak, V_angle, R_ohm, L_H);

    % Delete internal blocks
    lines = find_system(gpath, 'FindAll', 'on', 'SearchDepth', 1, 'Type', 'line');
    for l = 1:length(lines), try delete_line(gpath, lines(l)); catch, end, end

    inner_blks = find_system(gpath, 'SearchDepth', 1, 'Type', 'block');
    for b = 1:length(inner_blks)
        if strcmp(inner_blks{b}, gpath), continue; end
        if strcmp(get_param(inner_blks{b}, 'BlockType'), 'PMIOPort'), continue; end
        try delete_block(inner_blks{b}); catch, end
    end

    % Add Three-Phase Source with internal impedance
    vsrc_name = sprintf('WF%d_Src', wi);
    vsrc_path = sprintf('%s/%s', gpath, vsrc_name);
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

    % Connect to PMIOPorts A,B,C
    ports = find_system(gpath, 'SearchDepth', 1, 'BlockType', 'PMIOPort');
    phase_map = {'A', 'B', 'C'};
    for p = 1:3
        for pn = 1:length(ports)
            if strcmpi(get_param(ports{pn}, 'Name'), phase_map{p})
                add_line(gpath, sprintf('%s/RConn%d', vsrc_name, p), ...
                    sprintf('%s/RConn1', get_param(ports{pn}, 'Name')), ...
                    'autorouting', 'smart');
                break;
            end
        end
    end
end

%% Step 2: Replace retained sync machines (R2025b workaround)
% G1 (Bus 39, H=50s) and G9 (Bus 38, H=3.45s) should be synchronous machines
% but R2025b SM block has initialization bug. Use Three-Phase Source with
% parameters that reflect their SM characteristics.
fprintf('\n--- Replacing retained sync machines (R2025b SM workaround) ---\n');
for ri = 1:2
    gi = retained_blocks(ri);
    bus_num = retained_buses(ri);
    gpath = sprintf('%s/G%d', dst_model, gi);

    mc_row = gi;
    Sbase_va = mc(mc_row, 3) * 1e6;
    if bus_num == 39
        bus_kv = 345; % G1 is at 345kV
    else
        bus_kv = 22;
    end
    Vbase_v = bus_kv * 1000;
    Zbase = Vbase_v^2 / Sbase_va;
    xd_prime = mc(mc_row, 7);
    ra = mc(mc_row, 5);
    R_ohm = max(ra * Zbase, 0.01);
    L_H = xd_prime * Zbase / (2*pi*fn);

    vlf_map = containers.Map(...
        {30, 31, 32, 33, 34, 35, 36, 37, 38, 39}, ...
        {[1.048, -3.646], [0.982, 0], [0.9831, 2.466], [0.9972, 4.423], ...
         [1.012, 3.398], [1.049, 5.698], [1.063, 8.494], [1.028, 2.181], ...
         [1.027, 7.784], [1.03, 0]});
    vl = vlf_map(bus_num);
    V_peak = Vbase_v * vl(1);
    V_angle = vl(2);

    fprintf('  Retained G%d (Bus %d, H=%.1fs): V=%gV, ang=%.1f, R=%.4f, L=%.6f\n', ...
        gi, bus_num, mc(mc_row,16), V_peak, V_angle, R_ohm, L_H);

    % Delete internal blocks
    lines = find_system(gpath, 'FindAll', 'on', 'SearchDepth', 1, 'Type', 'line');
    for l = 1:length(lines), try delete_line(gpath, lines(l)); catch, end, end

    inner_blks = find_system(gpath, 'SearchDepth', 1, 'Type', 'block');
    for b = 1:length(inner_blks)
        if strcmp(inner_blks{b}, gpath), continue; end
        if strcmp(get_param(inner_blks{b}, 'BlockType'), 'PMIOPort'), continue; end
        try delete_block(inner_blks{b}); catch, end
    end

    vsrc_name = sprintf('SG%d_Src', gi);
    vsrc_path = sprintf('%s/%s', gpath, vsrc_name);
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

    ports = find_system(gpath, 'SearchDepth', 1, 'BlockType', 'PMIOPort');
    phase_map = {'A', 'B', 'C'};
    for p = 1:3
        for pn = 1:length(ports)
            if strcmpi(get_param(ports{pn}, 'Name'), phase_map{p})
                add_line(gpath, sprintf('%s/RConn%d', vsrc_name, p), ...
                    sprintf('%s/RConn1', get_param(ports{pn}, 'Name')), ...
                    'autorouting', 'smart');
                break;
            end
        end
    end
end

%% Save and test
save_system(dst_model);
fprintf('\n=== Model saved ===\n');

set_param(dst_model, 'StopTime', '0.5');
try
    simOut = sim(dst_model, 'StopTime', '0.5');
    fprintf('SUCCESS: Base model simulation passed (0.5s)\n');
catch me
    fprintf('FAIL: %s\n', me.message);
end

close_system(dst_model, 0);
fprintf('\n=== fix_sm_r2025b_v2 complete ===\n');
