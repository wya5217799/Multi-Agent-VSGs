function verify_kundur_cvs_topology()
% verify_kundur_cvs_topology  D1 — structural inventory + connection trace.
%
% Simscape physical-domain nodes are realized by multiple co-attached lines
% (each add_line creates a separate line that joins the implicit node), so
% a naive single-line walker cannot enumerate "all blocks at Bus_A". Instead
% we dump:
%   1. block-type counts (must match the build script's intent),
%   2. every signal-domain line  (Vr/Vi -> RI2C -> CVS),
%   3. every physical-connection line (src,dst both in connection ports).
% The verdict report cross-checks these against the build_kundur_cvs.m
% add_line sequence to confirm the 7-bus topology.

mdl = 'kundur_cvs';
if ~bdIsLoaded(mdl)
    here = fileparts(mfilename('fullpath'));
    slx_path = fullfile(here, '..', '..', '..', ...
        'scenarios','kundur','simulink_models','kundur_cvs.slx');
    load_system(slx_path);
end

% --- 1. Block-type counts ---
all_blocks = find_system(mdl, 'SearchDepth', 1, 'Type', 'block');
fprintf('RESULT: total blocks = %d\n', numel(all_blocks));

types = struct( ...
    'CVS_VSG',  numel(find_system(mdl, 'Regexp','on','Name','^CVS_VSG\d$')), ...
    'AC_INF',   numel(find_system(mdl, 'Name','AC_INF')), ...
    'L_v',      numel(find_system(mdl, 'Regexp','on','Name','^L_v_\d$')), ...
    'L_tie',    numel(find_system(mdl, 'Name','L_tie')), ...
    'L_inf',    numel(find_system(mdl, 'Name','L_inf')), ...
    'Load_A',   numel(find_system(mdl, 'Name','Load_A')), ...
    'Load_B',   numel(find_system(mdl, 'Name','Load_B')), ...
    'RI2C',     numel(find_system(mdl, 'Regexp','on','Name','^RI2C_\d$')), ...
    'Vr',       numel(find_system(mdl, 'Regexp','on','Name','^Vr_\d$')), ...
    'Vi',       numel(find_system(mdl, 'Regexp','on','Name','^Vi_\d$')), ...
    'GND_VSG',  numel(find_system(mdl, 'Regexp','on','Name','^GND_VSG\d$')), ...
    'GND_LA',   numel(find_system(mdl, 'Name','GND_LA')), ...
    'GND_LB',   numel(find_system(mdl, 'Name','GND_LB')), ...
    'GND_INF',  numel(find_system(mdl, 'Name','GND_INF')), ...
    'powergui', numel(find_system(mdl, 'Name','powergui')) ...
);
fprintf('RESULT: counts CVS_VSG=%d AC_INF=%d L_v=%d L_tie=%d L_inf=%d Load_A=%d Load_B=%d RI2C=%d Vr=%d Vi=%d GND_VSG=%d GND_LA=%d GND_LB=%d GND_INF=%d powergui=%d\n', ...
    types.CVS_VSG, types.AC_INF, types.L_v, types.L_tie, types.L_inf, ...
    types.Load_A, types.Load_B, types.RI2C, types.Vr, types.Vi, ...
    types.GND_VSG, types.GND_LA, types.GND_LB, types.GND_INF, types.powergui);

% --- 2. Per-VSG static config (D-CVS-9 / H1) ---
for i = 1:4
    b = sprintf('%s/CVS_VSG%d', mdl, i);
    fprintf('RESULT: VSG%d Source_Type=%s Initialize=%s Measurements=%s\n', ...
        i, get_param(b,'Source_Type'), get_param(b,'Initialize'), get_param(b,'Measurements'));
end

% --- 3. Signal-domain wiring (Vr_i, Vi_i -> RI2C_i -> CVS_VSG_i) ---
for i = 1:4
    cvs = sprintf('%s/CVS_VSG%d', mdl, i);
    ph  = get_param(cvs, 'PortHandles');
    p   = ph.Inport(1);
    ln  = get_param(p, 'Line');
    src_name = '-';
    if ln ~= -1
        sp = get_param(ln, 'SrcPortHandle');
        if sp ~= -1
            src_name = get_param(get_param(sp,'Parent'),'Name');
        end
    end
    fprintf('RESULT: VSG%d CVS Inport <- %s\n', i, src_name);
end

% --- 4. Physical-connection lines ---
all_lines = find_system(mdl, 'FindAll','on', 'Type','line');
fprintf('RESULT: --- physical connection lines ---\n');
for k = 1:numel(all_lines)
    ln = all_lines(k);
    sp = get_param(ln, 'SrcPortHandle');
    dps = get_param(ln, 'DstPortHandle');
    if sp ~= -1
        src_name = get_param(get_param(sp,'Parent'),'Name');
        src_type = get_param(sp, 'PortType');
    else
        src_name = '?'; src_type = '?';
    end
    dpnames = {};
    for j = 1:numel(dps)
        if dps(j) ~= -1
            dpnames{end+1} = get_param(get_param(dps(j),'Parent'),'Name'); %#ok<AGROW>
        end
    end
    if strcmp(src_type, 'connection')
        fprintf('RESULT: ln=%g %s --> %s\n', ln, src_name, strjoin(dpnames,','));
    end
end

% --- 5. PowerGui mode ---
fprintf('RESULT: powergui SimulationMode=%s frequency=%s\n', ...
    get_param([mdl '/powergui'],'SimulationMode'), ...
    get_param([mdl '/powergui'],'frequency'));

end
