function result = slx_trace_port_connections(model_name, block_path, port_kind, port_index)
% SLX_TRACE_PORT_CONNECTIONS  Trace the line tree attached to a specific block port.
%
%   Returns: ok, src, dsts, branch_count, line_handle, all_connected_ports, error_message
%   Each endpoint is a struct: block_path, port_kind, port_index, handle.

    empty_ep = struct('block_path', '', 'port_kind', '', 'port_index', 0, 'handle', 0);
    result = struct('ok', false, 'src', empty_ep, 'dsts', {{}}, ...
                    'branch_count', 0, 'line_handle', 0, ...
                    'all_connected_ports', {{}}, 'error_message', '');
    try
        ph       = get_param(char(block_path), 'PortHandles');
        kind_str = upper(strtrim(char(port_kind)));
        switch kind_str
            case 'INPORT',  ports = ph.Inport;
            case 'OUTPORT', ports = ph.Outport;
            case 'ENABLE',  ports = ph.Enable;
            case 'TRIGGER', ports = ph.Trigger;
            case 'LCONN',   ports = ph.LConn;
            case 'RCONN',   ports = ph.RConn;
            otherwise
                result.error_message = ['Unknown port kind: ', char(port_kind)];
                return;
        end

        idx = double(port_index);
        if isempty(ports) || idx < 1 || idx > numel(ports)
            result.error_message = sprintf('Port index %d out of range (1..%d)', idx, numel(ports));
            return;
        end

        port_h = ports(idx);
        line_h = get_param(port_h, 'Line');
        if ~isnumeric(line_h) || line_h <= 0
            result.ok = true;   % valid: port exists but has no line
            return;
        end

        result.line_handle = line_h;

        src_h      = get_param(line_h, 'SrcPortHandle');
        result.src = make_endpoint(src_h);

        dst_handles          = collect_dst_handles(line_h);
        result.branch_count  = max(0, numel(dst_handles) - 1);

        dsts      = {};
        all_ports = {};
        for i = 1:numel(dst_handles)
            ep = make_endpoint(dst_handles(i));
            dsts{end+1} = ep; %#ok<AGROW>
            if ~isempty(ep.block_path)
                all_ports{end+1} = ep.block_path; %#ok<AGROW>
            end
        end
        result.dsts               = dsts;
        result.all_connected_ports = all_ports;
        result.ok = true;
    catch ME
        result.error_message = ME.message;
    end
end

% -------------------------------------------------------------------------
function handles = collect_dst_handles(line_h)
    direct = get_param(line_h, 'DstPortHandle');
    if isnumeric(direct) && numel(direct) == 1 && direct == -1
        direct = [];
    end
    children = get_param(line_h, 'LineChildren');
    if isnumeric(children) && numel(children) == 1 && children == -1
        children = [];
    end
    handles = direct(:)';
    for cl = children(:)'
        handles = [handles, collect_dst_handles(cl)]; %#ok<AGROW>
    end
end

% -------------------------------------------------------------------------
function ep = make_endpoint(port_h)
    ep = struct('block_path', '', 'port_kind', '', 'port_index', 0, 'handle', double(port_h));
    if ~isnumeric(port_h) || port_h <= 0
        return;
    end
    try
        ep.block_path  = char(get_param(port_h, 'Parent'));
        ep.port_kind   = char(get_param(port_h, 'PortType'));
        ep.port_index  = double(get_param(port_h, 'PortNumber'));
    catch
    end
end
