%% upgrade_generators.m
% Upgrades G1-G3 from Simplified Generator to Synchronous Machine GENTPJ
% (IEEE standard full-order synchronous machine model with built-in H, D)
%
% GENTPJ port map (verified R2025b):
%   LConn1 = Physical signal input (Efd excitation)
%   LConn2 = Mechanical shaft (C)
%   LConn3 = Mechanical reference (R)
%   RConn1 = Physical signal output (measurements)
%   RConn2 = Composite 3-phase terminal
%
% Solver must connect to mechanical reference network.

mdl = 'kundur_two_area';

if ~bdIsLoaded(mdl)
    load_system(mdl);
end

fprintf('Upgrading generators in %s...\n', mdl);

%% ========== Parameters ==========
% Kundur standard generator parameters (Table 12.4, [49])
% G1, G2 (Area 1): H=6.5s
% G3 (Area 2): H=6.175s

gen_params = struct();

% G1 - Bus 1, Area 1 (Swing)
gen_params.G1.SRated = '900e6';
gen_params.G1.VRated = '20e3';
gen_params.G1.H = '6.5';
gen_params.G1.Pt0 = '700e6';
gen_params.G1.Qt0 = '185e6';
gen_params.G1.source_type = 'ee.enum.sm.load_flow_source_type.Swing';
gen_params.G1.Vmag0 = '20e3';
gen_params.G1.Vang0 = '0';

% G2 - Bus 2, Area 1 (PV)
gen_params.G2.SRated = '900e6';
gen_params.G2.VRated = '20e3';
gen_params.G2.H = '6.5';
gen_params.G2.Pt0 = '700e6';
gen_params.G2.Qt0 = '235e6';
gen_params.G2.source_type = 'ee.enum.sm.load_flow_source_type.PV';
gen_params.G2.Vmag0 = '20e3';
gen_params.G2.Vang0 = '0';

% G3 - Bus 3, Area 2 (PV)
gen_params.G3.SRated = '900e6';
gen_params.G3.VRated = '20e3';
gen_params.G3.H = '6.175';
gen_params.G3.Pt0 = '719e6';
gen_params.G3.Qt0 = '176e6';
gen_params.G3.source_type = 'ee.enum.sm.load_flow_source_type.PV';
gen_params.G3.Vmag0 = '20e3';
gen_params.G3.Vang0 = '0';

% Common Kundur parameters for all three generators
common_params = {
    'FRated', '60'
    'nPolePairs', '1'
    'Ra', '0.0025'
    'Xl', '0.2'
    'Xd', '1.8'
    'Xq', '1.7'
    'Xdd', '0.3'
    'Xqd', '0.55'
    'Xddd', '0.25'
    'Xqdd', '0.25'
    'Td0d', '8.0'
    'Tq0d', '0.4'
    'Td0dd', '0.03'
    'Tq0dd', '0.05'
};

%% ========== Replace each generator ==========
genNames = {'G1', 'G2', 'G3'};

for g = 1:length(genNames)
    gn = genNames{g};
    blk = [mdl '/' gn];
    fprintf('  Replacing %s...\n', gn);

    % Get current position
    pos = get_param(blk, 'Position');

    % Delete old Simplified Generator and its connections
    % First find and delete all connected lines
    ph = get_param(blk, 'PortHandles');
    allPorts = [ph.LConn, ph.RConn, ph.Inport, ph.Outport];
    for p = 1:length(allPorts)
        lineH = get_param(allPorts(p), 'Line');
        if lineH ~= -1
            delete_line(lineH);
        end
    end
    delete_block(blk);

    % Add GENTPJ block
    add_block('ee_lib/Electromechanical/Synchronous/Synchronous Machine GENTPJ', ...
        blk, 'Position', pos);

    % Set specific parameters
    gp = gen_params.(gn);
    set_param(blk, 'SRated', gp.SRated, 'VRated', gp.VRated);
    set_param(blk, 'source_type', gp.source_type);
    set_param(blk, 'Vmag0', gp.Vmag0, 'Vang0', gp.Vang0);
    set_param(blk, 'Pt0', gp.Pt0, 'Qt0', gp.Qt0);

    % H is not directly a parameter of GENTPJ - it uses internal rotor dynamics
    % Actually check if H exists as parameter
    try
        set_param(blk, 'H', gp.H);
    catch
        % H might not be a direct parameter. GENTPJ uses internal inertia.
        % The machine's mechanical dynamics are built-in.
        fprintf('    Note: H not settable directly for GENTPJ\n');
    end

    % Set common electrical parameters
    for i = 1:size(common_params, 1)
        set_param(blk, common_params{i,1}, common_params{i,2});
    end

    % Add exciter input (constant Efd = 1.0 pu for now)
    efdBlk = [mdl '/' gn '_Efd'];
    s2psBlk = [mdl '/' gn '_S2PS'];
    add_block('simulink/Sources/Constant', efdBlk, ...
        'Position', [pos(1)-120, pos(2), pos(1)-90, pos(2)+20]);
    set_param(efdBlk, 'Value', '1.0');
    add_block('nesl_utility/Simulink-PS Converter', s2psBlk, ...
        'Position', [pos(1)-70, pos(2), pos(1)-40, pos(2)+20]);

    % Add measurement output terminator
    ps2sBlk = [mdl '/' gn '_PS2S'];
    termBlk = [mdl '/' gn '_Term'];
    add_block('nesl_utility/PS-Simulink Converter', ps2sBlk, ...
        'Position', [pos(3)+20, pos(2), pos(3)+50, pos(2)+20]);
    add_block('simulink/Sinks/Terminator', termBlk, ...
        'Position', [pos(3)+70, pos(2), pos(3)+90, pos(2)+20]);

    % Wire exciter: Constant -> S2PS -> SM/LConn1
    add_line(mdl, [gn '_Efd/1'], [gn '_S2PS/1']);
    add_line(mdl, [gn '_S2PS/RConn1'], [gn '/LConn1']);

    % Wire measurement: SM/RConn1 -> PS2S -> Term
    add_line(mdl, [gn '/RConn1'], [gn '_PS2S/LConn1']);
    add_line(mdl, [gn '_PS2S/1'], [gn '_Term/1']);

    % Wire mechanical: SM/LConn2 (shaft) -> MechRef, SM/LConn3 (ref) -> MechRef
    add_line(mdl, [gn '/LConn2'], 'MechRef/LConn1');
    add_line(mdl, [gn '/LConn3'], 'MechRef/LConn1');

    % Wire 3ph output: SM/RConn2 -> corresponding line
    % G1 -> L_1_5, G2 -> L_2_6, G3 -> L_3_10
    lineMap = containers.Map({'G1','G2','G3'}, {'L_1_5','L_2_6','L_3_10'});
    targetLine = lineMap(gn);
    add_line(mdl, [gn '/RConn2'], [targetLine '/LConn1']);

    fprintf('    %s upgraded to GENTPJ\n', gn);
end

%% ========== Fix Solver connection ==========
% Move solver from GND to MechRef (GENTPJ needs solver on mech network)
try
    % Find and delete old solver-GND connection
    phSolver = get_param([mdl '/Solver'], 'PortHandles');
    lineH = get_param(phSolver.RConn(1), 'Line');
    if lineH ~= -1
        delete_line(lineH);
    end
catch; end

% Connect solver to MechRef
add_line(mdl, 'Solver/RConn1', 'MechRef/LConn1');
fprintf('  Solver reconnected to MechRef\n');

%% ========== Save ==========
save_system(mdl);
fprintf('Upgrade complete! Model saved.\n');
fprintf('Run sim(''%s'', ''StopTime'', ''1'') to test.\n', mdl);
