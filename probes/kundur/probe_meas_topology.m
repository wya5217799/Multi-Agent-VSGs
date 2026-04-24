function results = probe_meas_topology(model_name, run_dir, opts)
%PROBE_MEAS_TOPOLOGY  Read-only topology audit for Meas_ES{i} in Kundur SPS.
%
%   purpose: Confirm/deny RC-A — Meas_ES{i} blocks measuring current from
%            wrong topology location (not ESS branch current).
%
%   Reads PortConnectivity and block handles; NO set_param, NO sim, NO save.
%   Writes run_dir/attachments/<output_filename>.

if nargin < 1; model_name = 'kundur_vsg_sps'; end
if nargin < 2; run_dir    = fullfile(pwd, 'run_probe'); end
if nargin < 3; opts = struct(); end
if ~isfield(opts, 'output_filename')
    opts.output_filename = 'meas_topology_audit.json';
end

att_dir = fullfile(run_dir, 'attachments');
if ~exist(att_dir, 'dir'); mkdir(att_dir); end

if ~bdIsLoaded(model_name)
    load_system(model_name);
end

% Verify model is not dirty before reading (should never be — read-only probe)
dirty_before = strcmp(get_param(model_name, 'Dirty'), 'on');
fprintf('RESULT: model_dirty_before=%d\n', dirty_before);

meas_names   = {'Meas_ES1', 'Meas_ES2', 'Meas_ES3', 'Meas_ES4'};
branch_names = {'L_7_12',   'L_8_16',   'L_10_14',  'L_9_15'};
vsrc_names   = {'VSrc_ES1', 'VSrc_ES2', 'VSrc_ES3', 'VSrc_ES4'};
gen_src_names = {'GSrc_G1', 'GSrc_G2', 'GSrc_G3', 'WSrc_W1', 'WSrc_W2'};
all_known = [meas_names, branch_names, vsrc_names, gen_src_names];

% --- Build handle registry ---
h_reg = struct();
for k = 1:length(all_known)
    nm = all_known{k};
    try
        h_reg.(nm) = get_param([model_name '/' nm], 'Handle');
    catch
        h_reg.(nm) = -1;
    end
end

fprintf('RESULT: === Handle Registry ===\n');
fns = fieldnames(h_reg);
for k = 1:length(fns)
    fprintf('RESULT: %s = %.4f\n', fns{k}, h_reg.(fns{k}));
end

% --- Audit Meas_ES{i} PortConnectivity ---
fprintf('RESULT: === Meas_ES{i} Port Topology ===\n');
meas_results = cell(1, 4);
for i = 1:4
    r = struct();
    r.meas      = meas_names{i};
    r.expected_branch = branch_names{i};
    r.expected_vsrc   = vsrc_names{i};
    r.handle          = h_reg.(meas_names{i});

    try
        r.block_type = get_param([model_name '/' meas_names{i}], 'BlockType');
    catch
        r.block_type = 'error';
    end

    try
        pc = get_param([model_name '/' meas_names{i}], 'PortConnectivity');
        r.ports = {};
        all_dst_h = [];
        for p = 1:length(pc)
            pinfo.type        = pc(p).Type;
            pinfo.num_dst     = length(pc(p).DstBlock);
            pinfo.dst_handles = pc(p).DstBlock(:)';
            pinfo.dst_names   = {};
            for d = 1:length(pc(p).DstBlock)
                pinfo.dst_names{end+1} = resolve_block_h(pc(p).DstBlock(d), model_name);
            end
            r.ports{end+1} = pinfo;
            all_dst_h = [all_dst_h; pc(p).DstBlock(:)]; %#ok<AGROW>
            fprintf('RESULT: %s.%s num_dst=%d dst=[%s]\n', ...
                meas_names{i}, pc(p).Type, pinfo.num_dst, ...
                strjoin(pinfo.dst_names, ', '));
        end

        all_dst_h = unique(all_dst_h(all_dst_h > 0));
        h_branch  = h_reg.(branch_names{i});
        h_vsrc    = h_reg.(vsrc_names{i});
        r.connects_to_expected_branch = any(abs(all_dst_h - h_branch) < 0.5);
        r.connects_to_expected_vsrc   = any(abs(all_dst_h - h_vsrc)   < 0.5);

        % Check if connected to any generator source
        r.connects_to_gen_src = false;
        for g = 1:length(gen_src_names)
            h_gen = h_reg.(gen_src_names{g});
            if h_gen > 0 && any(abs(all_dst_h - h_gen) < 0.5)
                r.connects_to_gen_src = true;
                r.connected_gen_src = gen_src_names{g};
            end
        end

        fprintf('RESULT: %s summary: branch=%d vsrc=%d gen_src=%d\n', ...
            meas_names{i}, r.connects_to_expected_branch, ...
            r.connects_to_expected_vsrc, r.connects_to_gen_src);
    catch ME
        r.error = ME.message;
        fprintf('RESULT: %s PortConnectivity ERROR: %s\n', meas_names{i}, ME.message);
    end

    meas_results{i} = r;
end

% --- Audit branch lines PortConnectivity ---
fprintf('RESULT: === Branch Line Topology ===\n');
branch_results = cell(1, 4);
for i = 1:4
    r = struct();
    r.branch = branch_names{i};

    try
        pc = get_param([model_name '/' branch_names{i}], 'PortConnectivity');
        r.ports = {};
        for p = 1:length(pc)
            pinfo.type        = pc(p).Type;
            pinfo.num_dst     = length(pc(p).DstBlock);
            pinfo.dst_handles = pc(p).DstBlock(:)';
            pinfo.dst_names   = {};
            for d = 1:length(pc(p).DstBlock)
                pinfo.dst_names{end+1} = resolve_block_h(pc(p).DstBlock(d), model_name);
            end
            r.ports{end+1} = pinfo;
            fprintf('RESULT: %s.%s num_dst=%d dst=[%s]\n', ...
                branch_names{i}, pc(p).Type, pinfo.num_dst, ...
                strjoin(pinfo.dst_names, ', '));
        end
    catch ME
        r.error = ME.message;
        fprintf('RESULT: %s ERROR: %s\n', branch_names{i}, ME.message);
    end

    branch_results{i} = r;
end

% --- RC-A verdict from connectivity ---
fprintf('RESULT: === RC-A Connectivity Verdict ===\n');
rc_a_count = 0;
for i = 1:4
    r = meas_results{i};
    if isfield(r, 'connects_to_expected_branch') && ...
       ~r.connects_to_expected_branch && ~r.connects_to_expected_vsrc
        rc_a_count = rc_a_count + 1;
        fprintf('RESULT: RC-A CONFIRMED %s: not connected to %s or %s\n', ...
            meas_names{i}, branch_names{i}, vsrc_names{i});
    elseif isfield(r, 'connects_to_expected_branch') && r.connects_to_expected_branch
        fprintf('RESULT: RC-A NOT CONFIRMED %s: IS connected to %s\n', ...
            meas_names{i}, branch_names{i});
    elseif isfield(r, 'connects_to_expected_vsrc') && r.connects_to_expected_vsrc
        fprintf('RESULT: RC-A NOT CONFIRMED %s: IS connected to %s\n', ...
            meas_names{i}, vsrc_names{i});
    end
end
fprintf('RESULT: rc_a_confirmed_count=%d of 4\n', rc_a_count);

% --- Check dirty state after (read-only, should be unchanged) ---
dirty_after = strcmp(get_param(model_name, 'Dirty'), 'on');
fprintf('RESULT: model_dirty_after=%d\n', dirty_after);
if dirty_after
    fprintf('RESULT: WARNING model unexpectedly dirty — closing without saving\n');
    close_system(model_name, 0);
end

% --- Write artifact ---
out.schema_version    = 1;
out.scenario_id       = 'kundur';
out.model_name        = model_name;
out.purpose           = 'RC-A topology audit: Meas_ES{i} connection location';
out.handle_registry   = h_reg;
out.meas_results      = meas_results;
out.branch_results    = branch_results;
out.rc_a_count        = rc_a_count;
out.provenance.probe_file     = 'probes/kundur/probe_meas_topology.m';
out.provenance.read_only      = true;
out.provenance.set_param_used = false;
out.provenance.sim_run        = false;
out.provenance.model_dirty_before = dirty_before;
out.provenance.model_dirty_after  = dirty_after;
out.provenance.run_timestamp  = datestr(now, 'yyyy-mm-dd HH:MM:SS');

out_path = fullfile(att_dir, opts.output_filename);
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(out));
fclose(fid);

fprintf('RESULT: meas_topology_audit written to %s rc_a_count=%d\n', out_path, rc_a_count);
results = out;
end

% =========================================================================
function name = resolve_block_h(h, model_name)
if isnan(h) || h <= 0
    name = sprintf('invalid(%.0f)', h);
    return
end
try
    n = get_param(h, 'Name');
    p = get_param(h, 'Parent');
    if strcmp(p, model_name)
        name = n;
    else
        name = sprintf('NESTED:%s/%s', p, n);
    end
catch
    name = sprintf('h=%.4f', h);
end
end
