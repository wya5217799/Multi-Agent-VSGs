%% inspect_model.m
% Inspects the kundur_two_area Simulink model structure and prints a
% complete summary of all blocks, connections, and parameters.
% Run this in MATLAB to understand the current model state.

mdl = 'kundur_two_area';

%% Load model
cd(fileparts(mfilename('fullpath')));
if ~exist([mdl '.slx'], 'file')
    error('Model %s.slx not found. Run build_kundur_simulink.m first.', mdl);
end
if ~bdIsLoaded(mdl)
    load_system(mdl);
end

fprintf('============================================================\n');
fprintf('  Model Inspection: %s\n', mdl);
fprintf('============================================================\n\n');

%% 1. Solver & Simulation Settings
fprintf('--- 1. Simulation Settings ---\n');
fprintf('  Solver      : %s\n', get_param(mdl, 'Solver'));
fprintf('  StopTime    : %s s\n', get_param(mdl, 'StopTime'));
fprintf('  RelTol      : %s\n', get_param(mdl, 'RelTol'));
fprintf('  MaxStep     : %s\n', get_param(mdl, 'MaxStep'));
fprintf('  SimscapeLog : %s\n', get_param(mdl, 'SimscapeLogType'));
fprintf('\n');

%% 2. All Blocks — categorize by type
allBlocks = find_system(mdl, 'SearchDepth', 1, 'Type', 'block');
% Remove model root
allBlocks = allBlocks(2:end);

% Categorize
generators = {};
vsgs = {};
windFarms = {};
tlines = {};
loads = {};
switches = {};
references = {};
converters = {};
sources = {};
sinks = {};
others = {};

for k = 1:length(allBlocks)
    bPath = allBlocks{k};
    bName = get_param(bPath, 'Name');
    bType = get_param(bPath, 'BlockType');

    % Try to get MaskType for Simscape blocks
    maskType = '';
    try maskType = get_param(bPath, 'MaskType'); catch; end

    if startsWith(bName, 'G') && ~startsWith(bName, 'GND')
        generators{end+1} = bPath; %#ok<*SAGROW>
    elseif startsWith(bName, 'ES')
        vsgs{end+1} = bPath;
    elseif startsWith(bName, 'W')
        windFarms{end+1} = bPath;
    elseif startsWith(bName, 'L_')
        tlines{end+1} = bPath;
    elseif contains(bName, 'Load') || contains(bName, 'Shunt') || startsWith(bName, 'DLoad')
        loads{end+1} = bPath;
    elseif startsWith(bName, 'SW')
        switches{end+1} = bPath;
    elseif contains(bName, 'Ref') || contains(bName, 'GND') || contains(bName, 'Solver')
        references{end+1} = bPath;
    elseif contains(bName, 'S2PS') || contains(bName, 'PS2S')
        converters{end+1} = bPath;
    elseif contains(bName, 'Trip') || contains(bName, 'Efd') || contains(bName, '_val')
        sources{end+1} = bPath;
    elseif contains(bName, 'Term') || contains(bName, 'Scope')
        sinks{end+1} = bPath;
    else
        others{end+1} = bPath;
    end
end

%% 3. Print Generators
fprintf('--- 2. Generators (G1-G3) ---\n');
for k = 1:length(generators)
    bPath = generators{k};
    bName = get_param(bPath, 'Name');
    bType = get_param(bPath, 'BlockType');
    maskType = ''; try maskType = get_param(bPath, 'MaskType'); catch; end

    fprintf('  [%s] BlockType=%s', bName, bType);
    if ~isempty(maskType), fprintf(', Mask=%s', maskType); end
    fprintf('\n');

    % Print key parameters based on block type
    genParams = {'SRated','VRated','FRated','Ra','Xd','Xq','Xdd','Xqd', ...
                 'Td0d','Tq0d','source_type','Pt0','Qt0','Vmag0', ...
                 'RatedPower','RotorInertia','RotorDamping','Fdroop','VinternalRMS'};
    for p = 1:length(genParams)
        try
            val = get_param(bPath, genParams{p});
            if ischar(val) && length(val) < 60
                fprintf('    %-20s = %s\n', genParams{p}, val);
            end
        catch; end
    end

    % Print port connectivity
    print_ports(bPath);
    fprintf('\n');
end

%% 4. Print Wind Farms
fprintf('--- 3. Wind Farms (W1, W2) ---\n');
for k = 1:length(windFarms)
    bPath = windFarms{k};
    bName = get_param(bPath, 'Name');
    fprintf('  [%s]\n', bName);
    wfParams = {'RatedPower','FRated','VinternalRMS','RotorInertia','RotorDamping','Fdroop'};
    for p = 1:length(wfParams)
        try
            val = get_param(bPath, wfParams{p});
            fprintf('    %-20s = %s\n', wfParams{p}, val);
        catch; end
    end
    print_ports(bPath);
    fprintf('\n');
end

%% 5. Print VSGs
fprintf('--- 4. VSGs (ES1-ES4) ---\n');
for k = 1:length(vsgs)
    bPath = vsgs{k};
    bName = get_param(bPath, 'Name');
    fprintf('  [%s]\n', bName);
    vsgParams = {'RatedPower','FRated','VinternalRMS','RotorInertia','RotorDamping','Fdroop'};
    for p = 1:length(vsgParams)
        try
            val = get_param(bPath, vsgParams{p});
            fprintf('    %-20s = %s\n', vsgParams{p}, val);
        catch; end
    end
    print_ports(bPath);
    fprintf('\n');
end

%% 6. Print Transmission Lines
fprintf('--- 5. Transmission Lines (%d total) ---\n', length(tlines));
fprintf('  %-12s  %8s  %8s  %8s  %8s\n', 'Name', 'Length', 'R', 'L', 'Cl');
fprintf('  %-12s  %8s  %8s  %8s  %8s\n', '', '(km)', '(Ohm/km)', '(mH/km)', '(uF/km)');
fprintf('  %s\n', repmat('-', 1, 56));
for k = 1:length(tlines)
    bPath = tlines{k};
    bName = get_param(bPath, 'Name');
    len = ''; R = ''; L = ''; Cl = '';
    try len = get_param(bPath, 'length'); catch; end
    try R = get_param(bPath, 'R'); catch; end
    try L = get_param(bPath, 'L'); catch; end
    try Cl = get_param(bPath, 'Cl'); catch; end
    fprintf('  %-12s  %8s  %8s  %8s  %8s\n', bName, len, R, L, Cl);
end
fprintf('\n');

%% 7. Print Loads
fprintf('--- 6. Loads & Shunt Compensation ---\n');
for k = 1:length(loads)
    bPath = loads{k};
    bName = get_param(bPath, 'Name');
    P = ''; Q = ''; V = ''; structure = '';
    try P = get_param(bPath, 'P'); catch; end
    try Q = get_param(bPath, 'Qpos'); catch; end
    try V = get_param(bPath, 'VRated'); catch; end
    try structure = get_param(bPath, 'component_structure'); catch; end
    fprintf('  [%-10s]  P=%s W, Q=%s VAr, V=%s V, type=%s\n', bName, P, Q, V, structure);
    print_ports(bPath);
end
fprintf('\n');

%% 8. Print Switches
fprintf('--- 7. Switches (Disturbance Mechanism) ---\n');
for k = 1:length(switches)
    bPath = switches{k};
    bName = get_param(bPath, 'Name');
    fprintf('  [%s]\n', bName);
    print_ports(bPath);
end
% Also print Trip blocks
for k = 1:length(sources)
    bPath = sources{k};
    bName = get_param(bPath, 'Name');
    if startsWith(bName, 'Trip')
        tripTime = ''; before = ''; after = '';
        try tripTime = get_param(bPath, 'Time'); catch; end
        try before = get_param(bPath, 'Before'); catch; end
        try after = get_param(bPath, 'After'); catch; end
        fprintf('  [%-10s]  Time=%s, Before=%s, After=%s\n', bName, tripTime, before, after);
    end
end
fprintf('\n');

%% 9. Print References & Infrastructure
fprintf('--- 8. References & Infrastructure ---\n');
for k = 1:length(references)
    bPath = references{k};
    bName = get_param(bPath, 'Name');
    bType = get_param(bPath, 'BlockType');
    fprintf('  [%-12s]  BlockType=%s\n', bName, bType);
end
fprintf('\n');

%% 10. Network Topology (Connection Map)
fprintf('--- 9. Network Topology (Connection Map) ---\n');
fprintf('  Finding all physical connections...\n\n');

lines = find_system(mdl, 'SearchDepth', 1, 'FindAll', 'on', 'Type', 'line');
connMap = {};
for k = 1:length(lines)
    try
        srcH = get_param(lines(k), 'SrcBlockHandle');
        dstH = get_param(lines(k), 'DstBlockHandle');
        srcName = get_param(srcH, 'Name');
        dstName = get_param(dstH, 'Name');
        srcPort = get_param(get_param(lines(k), 'SrcPortHandle'), 'PortType');
        srcPortN = get_param(get_param(lines(k), 'SrcPortHandle'), 'PortNumber');
        dstPort = get_param(get_param(lines(k), 'DstPortHandle'), 'PortType');
        dstPortN = get_param(get_param(lines(k), 'DstPortHandle'), 'PortNumber');

        srcName = strrep(srcName, newline, ' ');
        dstName = strrep(dstName, newline, ' ');

        connStr = sprintf('  %s/%s%d  -->  %s/%s%d', ...
            srcName, srcPort, srcPortN, dstName, dstPort, dstPortN);
        connMap{end+1} = connStr;
    catch
        % Skip lines that don't have standard src/dst (branches)
    end
end

% Sort and print
connMap = sort(connMap);
for k = 1:length(connMap)
    fprintf('%s\n', connMap{k});
end

%% 11. Summary
fprintf('\n--- 10. Summary ---\n');
fprintf('  Generators (GENTPJ/SimpGen) : %d\n', length(generators));
fprintf('  Wind Farms                   : %d\n', length(windFarms));
fprintf('  VSGs (ES1-ES4)              : %d\n', length(vsgs));
fprintf('  Transmission Lines           : %d\n', length(tlines));
fprintf('  Loads/Shunts                 : %d\n', length(loads));
fprintf('  Switches                     : %d\n', length(switches));
fprintf('  References/Infra             : %d\n', length(references));
fprintf('  Signal Converters            : %d\n', length(converters));
fprintf('  Signal Sources               : %d\n', length(sources));
fprintf('  Signal Sinks                 : %d\n', length(sinks));
fprintf('  Other                        : %d\n', length(others));
fprintf('  Total blocks                 : %d\n', length(allBlocks));
fprintf('\n============================================================\n');
fprintf('  Inspection complete.\n');
fprintf('============================================================\n');

%% ========== Helper Function ==========
function print_ports(blkPath)
    ph = get_param(blkPath, 'PortHandles');
    nL = length(ph.LConn);
    nR = length(ph.RConn);
    nI = length(ph.Inport);
    nO = length(ph.Outport);
    fprintf('    Ports: LConn=%d, RConn=%d, Inport=%d, Outport=%d\n', nL, nR, nI, nO);

    % Show what each port connects to
    for p = 1:nL
        lineH = get_param(ph.LConn(p), 'Line');
        if lineH ~= -1
            try
                dstH = get_param(lineH, 'DstBlockHandle');
                if dstH ~= -1
                    dstName = strrep(get_param(dstH, 'Name'), newline, ' ');
                    fprintf('      LConn%d --> %s\n', p, dstName);
                end
            catch; end
            try
                srcH = get_param(lineH, 'SrcBlockHandle');
                if srcH ~= -1
                    srcName = strrep(get_param(srcH, 'Name'), newline, ' ');
                    fprintf('      LConn%d <-- %s\n', p, srcName);
                end
            catch; end
        else
            fprintf('      LConn%d : UNCONNECTED\n', p);
        end
    end
    for p = 1:nR
        lineH = get_param(ph.RConn(p), 'Line');
        if lineH ~= -1
            try
                dstH = get_param(lineH, 'DstBlockHandle');
                if dstH ~= -1
                    dstName = strrep(get_param(dstH, 'Name'), newline, ' ');
                    fprintf('      RConn%d --> %s\n', p, dstName);
                end
            catch; end
        else
            fprintf('      RConn%d : UNCONNECTED\n', p);
        end
    end
end
