function result = slx_powerlib_net_query(model_name, start_block, start_port)
%SLX_POWERLIB_NET_QUERY Enumerate all blocks/ports on a powerlib electrical net.
%
%   result = slx_powerlib_net_query(MODEL_NAME, START_BLOCK, START_PORT)
%
%   Powerlib (SimPowerSystems / Specialised Power Systems) physical
%   ports (LConn / RConn) are NOT visible to the standard Simulink
%   line-trace API. simulink_explore_block returns
%   is_connected=true with empty source_blocks/sink_blocks, which can
%   mislead callers into thinking a net has no other members.
%
%   This helper resolves the actual electrical net membership by walking
%   the connectivity returned by get_param(line, 'SrcBlockHandle') /
%   'DstBlockHandle' on the underlying physical lines, then deduplicating.
%
%   Inputs
%   ------
%     MODEL_NAME    char/string  Loaded Simulink model name.
%     START_BLOCK   char/string  Path of one block on the net of interest.
%     START_PORT    char/string  Port handle name on START_BLOCK ('LConn1',
%                                  'RConn1', etc.) — used as the entry
%                                  point into the connectivity graph.
%
%   Output
%   ------
%   A struct with fields:
%     net_id        char    — synthesized id ('start_block/port')
%     members       struct array with .block, .port — all (block,port) pairs
%                              on the same electrical net
%     anchor        struct  — the (block,port) used as entry point
%     supported     logical — true if the helper could resolve members;
%                              false on unsupported MATLAB version or when
%                              the start block is not powerlib physical.
%     reason        char    — fallback explanation if not supported.
%
%   Notes
%   -----
%   Uses get_param(line_handle, 'SrcBlockHandle') / 'DstBlockHandle' /
%   'Handle' walking on PortHandles.LConn / .RConn. Behavior verified in
%   R2025b. Older versions may differ; helper falls back to supported=false.
%
%   Project-neutral: contains no scenario-specific names. Project anchor
%   tests live under probes/ — see plan §3.D.1.

    arguments
        model_name   (1,:) char
        start_block  (1,:) char
        start_port   (1,:) char
    end

    result = struct( ...
        'net_id', '', ...
        'members', struct('block', {}, 'port', {}), ...
        'anchor', struct('block', start_block, 'port', start_port), ...
        'supported', false, ...
        'reason', '');

    if ~bdIsLoaded(model_name)
        try
            load_system(model_name);
        catch err
            result.reason = ['load_system failed: ' err.message];
            return;
        end
    end

    % Get port handles for the start block
    try
        ph = get_param(start_block, 'PortHandles');
    catch err
        result.reason = ['get_param PortHandles failed: ' err.message];
        return;
    end

    % Powerlib physical ports live in LConn or RConn
    if ~isfield(ph, 'LConn') && ~isfield(ph, 'RConn')
        result.reason = 'block has no LConn/RConn ports — not a powerlib physical block';
        return;
    end

    port_handle = i_resolve_port_handle(ph, start_port);
    if isempty(port_handle) || port_handle == -1
        result.reason = sprintf('port %s not found on block %s', start_port, start_block);
        return;
    end

    % Walk connectivity. Powerlib physical lines are accessible via
    % LineHandles or via get_param(port_handle, 'Line').
    visited_blocks = containers.Map('KeyType', 'char', 'ValueType', 'logical');
    members = struct('block', {}, 'port', {});

    % Seed: the start block + port itself
    visited_blocks(start_block) = true;
    members(end+1) = struct('block', start_block, 'port', start_port); %#ok<AGROW>

    try
        line_handle = get_param(port_handle, 'Line');
    catch
        line_handle = -1;
    end
    if line_handle == -1
        result.reason = 'port has no connected line';
        result.net_id = [start_block '/' start_port];
        result.members = members;
        result.supported = true;
        return;
    end

    % Collect all ports on the line (Src + Dst + branched)
    try
        all_port_handles = i_collect_line_ports(line_handle);
    catch err
        result.reason = ['line walk failed: ' err.message];
        return;
    end

    for k = 1:numel(all_port_handles)
        ph_handle = all_port_handles(k);
        try
            parent_handle = get_param(ph_handle, 'Parent');
            parent_path = getfullname(parent_handle);
            port_label = i_classify_port(parent_handle, ph_handle);
        catch
            continue;
        end
        if isempty(parent_path) || strcmp(parent_path, start_block) && strcmp(port_label, start_port)
            continue;
        end
        if isKey(visited_blocks, parent_path)
            % Same block, possibly different port — record it
        else
            visited_blocks(parent_path) = true;
        end
        members(end+1) = struct('block', parent_path, 'port', port_label); %#ok<AGROW>
    end

    result.net_id = [start_block '/' start_port];
    result.members = members;
    result.supported = true;
end


function ph_handle = i_resolve_port_handle(ph, port_label)
%I_RESOLVE_PORT_HANDLE Map textual port label like 'LConn1' to numeric handle.
    ph_handle = -1;
    if isempty(port_label)
        return;
    end
    if startsWith(port_label, 'LConn') && isfield(ph, 'LConn')
        idx = sscanf(port_label, 'LConn%d');
        if ~isempty(idx) && idx >= 1 && idx <= numel(ph.LConn)
            ph_handle = ph.LConn(idx);
        end
    elseif startsWith(port_label, 'RConn') && isfield(ph, 'RConn')
        idx = sscanf(port_label, 'RConn%d');
        if ~isempty(idx) && idx >= 1 && idx <= numel(ph.RConn)
            ph_handle = ph.RConn(idx);
        end
    end
end


function port_handles = i_collect_line_ports(line_handle)
%I_COLLECT_LINE_PORTS Enumerate all port handles on a (possibly branched) line.
    port_handles = [];
    if line_handle == -1
        return;
    end
    try
        src = get_param(line_handle, 'SrcPortHandle');
        if src ~= -1
            port_handles(end+1) = src; %#ok<AGROW>
        end
    catch
    end
    try
        dst_arr = get_param(line_handle, 'DstPortHandle');
        for k = 1:numel(dst_arr)
            if dst_arr(k) ~= -1
                port_handles(end+1) = dst_arr(k); %#ok<AGROW>
            end
        end
    catch
    end
    % Branched lines: descend into LineChildren
    try
        children = get_param(line_handle, 'LineChildren');
        for k = 1:numel(children)
            port_handles = [port_handles, i_collect_line_ports(children(k))]; %#ok<AGROW>
        end
    catch
    end
end


function port_label = i_classify_port(block_handle, port_handle)
%I_CLASSIFY_PORT Map a numeric port_handle back to a textual label.
    port_label = '';
    try
        ph = get_param(block_handle, 'PortHandles');
    catch
        return;
    end
    if isfield(ph, 'LConn')
        for k = 1:numel(ph.LConn)
            if ph.LConn(k) == port_handle
                port_label = sprintf('LConn%d', k);
                return;
            end
        end
    end
    if isfield(ph, 'RConn')
        for k = 1:numel(ph.RConn)
            if ph.RConn(k) == port_handle
                port_label = sprintf('RConn%d', k);
                return;
            end
        end
    end
    % Fallback: standard Inport / Outport
    if isfield(ph, 'Inport')
        for k = 1:numel(ph.Inport)
            if ph.Inport(k) == port_handle
                port_label = sprintf('Inport%d', k);
                return;
            end
        end
    end
    if isfield(ph, 'Outport')
        for k = 1:numel(ph.Outport)
            if ph.Outport(k) == port_handle
                port_label = sprintf('Outport%d', k);
                return;
            end
        end
    end
end
