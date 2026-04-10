%% fix_mechanical.m
% Fixes mechanical port connections for ALL generators/VSGs.
%
% Verified port maps (R2025b):
%
%   GENTPJ (G1, G2, G3):
%     LConn1 = Physical Signal (Efd excitation input)
%     LConn2 = Mechanical Rotational (shaft port A)
%     LConn3 = Mechanical Rotational (shaft port B)
%     RConn1 = Three-phase electrical composite
%     RConn2 = Electrical neutral
%
%   Simplified Generator (W1, W2, ES1-ES4):
%     LConn1 = Mechanical Rotational (shaft C)
%     LConn2 = Mechanical Rotational (shaft R / reference)
%     LConn3 = Physical Signal (?)
%     RConn1 = Three-phase electrical composite
%     RConn2 = Electrical neutral
%
%   Ideal Torque Source:
%     LConn1 = Mechanical Rotational C
%     RConn1 = Physical Signal S (torque input)
%     RConn2 = Mechanical Rotational R
%
%   PS Constant:
%     RConn1 = Physical Signal output

mdl = 'kundur_two_area';
cd(fileparts(mfilename('fullpath')));
if ~bdIsLoaded(mdl), load_system(mdl); end

fprintf('=== Fixing mechanical port connections ===\n\n');

fn = 60;
omega_s = 2*pi*fn;
Sn_gen = 900e6; Sn_w2 = 100e6; Sn_vsg = 200e6;

% {name, Pm, type}
% type: 'gentpj' = GENTPJ (mech ports LConn2,LConn3)
%       'simpgen' = Simplified Generator (mech ports LConn1,LConn2)
machines = {
    'G1',  Sn_gen*0.85, 'gentpj';
    'G2',  Sn_gen*0.78, 'gentpj';
    'G3',  Sn_gen*0.78, 'gentpj';
    'W1',  Sn_gen*0.78, 'simpgen';
    'W2',  Sn_w2*0.9,   'simpgen';
    'ES1', Sn_vsg*0.5,  'simpgen';
    'ES2', Sn_vsg*0.5,  'simpgen';
    'ES3', Sn_vsg*0.5,  'simpgen';
    'ES4', Sn_vsg*0.5,  'simpgen';
};

%% ========== Phase 1: Cleanup ==========
fprintf('--- Phase 1: Cleanup ---\n');
for k = 1:size(machines, 1)
    name = machines{k,1};
    mtype = machines{k,3};

    % Delete old prime mover blocks
    for prefix = {'Tm_', 'S2P_', 'Pm_'}
        blkPath = [mdl '/' prefix{1} name];
        try
            bph = get_param(blkPath, 'PortHandles');
            for p = [bph.LConn, bph.RConn, bph.Inport, bph.Outport]
                lh = get_param(p, 'Line'); if lh ~= -1, delete_line(lh); end
            end
            delete_block(blkPath);
            fprintf('  Deleted %s%s\n', prefix{1}, name);
        catch; end
    end

    % Determine which port is the shaft C port (needs torque source)
    genBlk = [mdl '/' name];
    ph = get_param(genBlk, 'PortHandles');

    if strcmp(mtype, 'gentpj')
        % GENTPJ: LConn2 = mech shaft (disconnect from MechRef)
        shaftIdx = 2;
    else
        % Simplified Generator: LConn1 = mech shaft
        shaftIdx = 1;
    end

    % Delete line on shaft port
    for attempt = 1:3
        lh = get_param(ph.LConn(shaftIdx), 'Line');
        if lh ~= -1
            try delete_line(lh); fprintf('  Cleared %s/LConn%d\n', name, shaftIdx);
            catch, break; end
        else, break;
        end
    end
end
fprintf('\n');

%% ========== Phase 2: Add prime movers ==========
fprintf('--- Phase 2: Add prime movers ---\n');
for k = 1:size(machines, 1)
    name  = machines{k,1};
    Pm    = machines{k,2};
    mtype = machines{k,3};
    Tm    = Pm / omega_s;

    genBlk = [mdl '/' name];
    genPos = get_param(genBlk, 'Position');
    gx = genPos(1);
    gy = mean(genPos([2,4]));

    % Ensure blocks are at positive coordinates
    pmX = max(gx - 210, 20);
    tsX = max(gx - 130, 80);

    tsName  = ['Tm_' name];
    pscName = ['Pm_' name];

    fprintf('  %s (%s): Tm=%.0f Nm ... ', name, mtype, Tm);

    % Add PS Constant
    add_block('fl_lib/Physical Signals/Sources/PS Constant', ...
        [mdl '/' pscName], 'Position', [pmX, gy-15, pmX+50, gy+15]);
    set_param([mdl '/' pscName], 'constant', num2str(Tm, '%.6g'));

    % Add Ideal Torque Source
    add_block('fl_lib/Mechanical/Mechanical Sources/Ideal Torque Source', ...
        [mdl '/' tsName], 'Position', [tsX, gy-25, tsX+60, gy+25]);

    % Wire signal: PS Constant → TS signal input
    add_line(mdl, [pscName '/RConn1'], [tsName '/RConn1']);

    % Wire shaft: TS mech port → Generator shaft port
    if strcmp(mtype, 'gentpj')
        % GENTPJ: shaft = LConn2. TS can connect via LConn1 or RConn2.
        add_line(mdl, [tsName '/RConn2'], [name '/LConn2']);
    else
        % Simplified Generator: shaft = LConn1.
        add_line(mdl, [tsName '/RConn2'], [name '/LConn1']);
    end

    % Wire reference: TS other mech port → MechRef
    add_line(mdl, [tsName '/LConn1'], 'MechRef/LConn1');

    fprintf('OK\n');
end

%% ========== Phase 3: GENTPJ Efd input ==========
% GENTPJ LConn1 is Efd (physical signal input). Need a PS Constant for it.
fprintf('\n--- Phase 3: GENTPJ Efd inputs ---\n');
for k = 1:3  % G1, G2, G3
    name = machines{k,1};
    efdName = ['Efd_' name];
    genBlk = [mdl '/' name];
    ph = get_param(genBlk, 'PortHandles');

    % Check if LConn1 (Efd) already has a connection
    lh = get_param(ph.LConn(1), 'Line');
    if lh ~= -1
        fprintf('  %s/LConn1 (Efd) already connected, skipping\n', name);
        continue;
    end

    % Add PS Constant for Efd (1.0 pu nominal)
    genPos = get_param(genBlk, 'Position');
    efdX = max(genPos(1) - 100, 20);
    efdY = genPos(2) + 10;

    try delete_block([mdl '/' efdName]); catch; end
    add_block('fl_lib/Physical Signals/Sources/PS Constant', ...
        [mdl '/' efdName], 'Position', [efdX, efdY, efdX+50, efdY+30]);
    set_param([mdl '/' efdName], 'constant', '1.0');
    add_line(mdl, [efdName '/RConn1'], [name '/LConn1']);
    fprintf('  %s: Efd=1.0 pu connected\n', name);
end

%% ========== Phase 4: Verify ==========
fprintf('\n--- Phase 4: Verify ---\n');
allOK = true;
for k = 1:size(machines, 1)
    name  = machines{k,1};
    mtype = machines{k,3};
    ph = get_param([mdl '/' name], 'PortHandles');

    if strcmp(mtype, 'gentpj')
        c1 = get_param(ph.LConn(1), 'Line') ~= -1;  % Efd
        c2 = get_param(ph.LConn(2), 'Line') ~= -1;  % shaft (torque src)
        c3 = get_param(ph.LConn(3), 'Line') ~= -1;  % ref
        ok = c1 && c2 && c3;
        fprintf('  %s (GENTPJ): Efd=%s Shaft=%s Ref=%s\n', name, tf(c1), tf(c2), tf(c3));
    else
        c1 = get_param(ph.LConn(1), 'Line') ~= -1;  % shaft (torque src)
        c2 = get_param(ph.LConn(2), 'Line') ~= -1;  % ref
        ok = c1 && c2;
        fprintf('  %s (SimpGen): Shaft=%s Ref=%s\n', name, tf(c1), tf(c2));
    end
    if ~ok, allOK = false; end
end

%% ========== Save ==========
save_system(mdl);
if allOK
    fprintf('\n=== All OK! Model saved. ===\n');
else
    fprintf('\n=== WARNING: Some ports unconnected. Model saved. ===\n');
end

fprintf('\nTest:\n');
fprintf('  set_param(''%s'', ''SimscapeLogType'', ''all'', ''StopTime'', ''3'');\n', mdl);
fprintf('  set_param(''%s/Trip14'', ''Time'', ''1'');\n', mdl);
fprintf('  out = sim(''%s'');\n', mdl);

function s = tf(v)
    if v, s = '✓'; else, s = '✗'; end
end
