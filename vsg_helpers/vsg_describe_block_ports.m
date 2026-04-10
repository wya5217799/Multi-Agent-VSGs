function summary = vsg_describe_block_ports(model_name, block_path)
%VSG_DESCRIBE_BLOCK_PORTS Describe block ports in stable order.

    load_system(char(model_name));
    summary = struct('block_path', char(block_path), 'ports', {{}}, 'error_message', '');

    try
        port_handles = get_param(char(block_path), 'PortHandles');
        fields = fieldnames(port_handles);
        ports = {};
        for i = 1:numel(fields)
            kind = fields{i};
            handles = port_handles.(kind);
            if isempty(handles)
                continue;
            end
            for j = 1:numel(handles)
                handle = handles(j);
                line_handles = i_line_handles(handle);
                ports{end + 1, 1} = struct( ... %#ok<AGROW>
                    'kind', kind, ...
                    'index', j, ...
                    'handle', double(handle), ...
                    'is_connected', ~isempty(line_handles), ...
                    'line_handles', double(line_handles), ...
                    'connected_block_paths', {i_connected_blocks(line_handles)});
            end
        end
        summary.ports = ports;
    catch ME
        summary.error_message = char(ME.message);
    end
end

function line_handles = i_line_handles(port_handle)
    line_handles = [];
    try
        line_value = get_param(port_handle, 'Line');
        if ~isempty(line_value) && all(line_value ~= -1)
            line_handles = line_value(:)';
            return;
        end
    catch
    end

    try
        line_value = get_param(port_handle, 'LineHandles');
        if ~isempty(line_value)
            line_handles = line_value(:)';
        end
    catch
    end
end

function blocks = i_connected_blocks(line_handles)
    blocks = {};
    for i = 1:numel(line_handles)
        line_handle = line_handles(i);
        if isempty(line_handle) || line_handle == -1
            continue;
        end
        try
            src_handle = get_param(line_handle, 'SrcBlockHandle');
            if ~isempty(src_handle) && src_handle ~= -1
                blocks{end + 1, 1} = getfullname(src_handle); %#ok<AGROW>
            end
        catch
        end
        try
            dst_handles = get_param(line_handle, 'DstBlockHandle');
            for j = 1:numel(dst_handles)
                if dst_handles(j) ~= -1
                    blocks{end + 1, 1} = getfullname(dst_handles(j)); %#ok<AGROW>
                end
            end
        catch
        end
    end
    if isempty(blocks)
        return;
    end
    [~, ia] = unique(blocks, 'stable');
    blocks = blocks(sort(ia));
end
