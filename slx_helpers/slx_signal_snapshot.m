function result = slx_signal_snapshot(model_name, time_s, signals, allow_partial)
%SLX_SIGNAL_SNAPSHOT  Read logged/to-workspace/block-output values at a target time.

    if nargin < 4 || isempty(allow_partial), allow_partial = false; end

    model_name = char(model_name);
    load_system(model_name);

    specs = i_normalize_specs(signals);
    result = struct( ...
        'time_s', double(time_s), ...
        'values', {{}}, ...
        'missing_signals', {{}}, ...
        'units', {{}}, ...
        'read_ok', true, ...
        'warnings', {{}}, ...
        'error_message', '');

    cleanup_items = {};
    cleaner = onCleanup(@() i_cleanup_items(cleanup_items));

    for i = 1:numel(specs)
        spec = specs{i};
        if strcmp(spec.source, 'block')
            [spec, cleanup_info, warn_msg] = i_prepare_block_probe(spec);
            specs{i} = spec;
            if ~isempty(cleanup_info)
                cleanup_items{end + 1, 1} = cleanup_info; %#ok<AGROW>
            end
            if ~isempty(warn_msg)
                result.warnings{end + 1, 1} = warn_msg; %#ok<AGROW>
            end
        end
    end

    sim_out = [];
    try
        sim_in = Simulink.SimulationInput(model_name);
        sim_in = sim_in.setModelParameter( ...
            'StartTime', '0', ...
            'StopTime', num2str(double(time_s)), ...
            'CaptureErrors', 'on', ...
            'SignalLogging', 'on');
        [~, sim_out] = evalc('sim(sim_in)');
    catch ME
        result.read_ok = false;
        result.error_message = char(ME.message);
        result.warnings{end + 1, 1} = char(ME.message); %#ok<AGROW>
        return;
    end

    values = {};
    units = {};
    missing = {};
    for i = 1:numel(specs)
        spec = specs{i};
        try
            [value, unit] = i_read_spec(sim_out, spec, double(time_s));
            values{end + 1, 1} = struct('signal', spec.signal_key, 'value', value, 'unit', unit); %#ok<AGROW>
            units{end + 1, 1} = struct('signal', spec.signal_key, 'unit', unit); %#ok<AGROW>
        catch ME
            missing{end + 1, 1} = spec.signal_key; %#ok<AGROW>
            result.warnings{end + 1, 1} = sprintf('%s: %s', spec.signal_key, ME.message); %#ok<AGROW>
            if ~logical(allow_partial)
                result.read_ok = false;
            end
        end
    end

    result.values = values;
    result.units = units;
    result.missing_signals = missing;
    if ~isempty(missing) && ~logical(allow_partial)
        result.read_ok = false;
    end

    clear cleaner; %#ok<NASGU>
end

function specs = i_normalize_specs(signals)
    specs = {};
    if isempty(signals)
        return;
    end

    if iscell(signals)
        raw_items = signals;
    else
        raw_items = num2cell(signals);
    end

    for i = 1:numel(raw_items)
        item = raw_items{i};
        if ischar(item) || isstring(item)
            specs{end + 1, 1} = i_parse_string_spec(char(item)); %#ok<AGROW>
        elseif isstruct(item)
            if isfield(item, 'block_path')
                port_index = 1;
                if isfield(item, 'port_index') && ~isempty(item.port_index)
                    port_index = double(item.port_index);
                end
                specs{end + 1, 1} = struct( ...
                    'source', 'block', ...
                    'name', '', ...
                    'block_path', char(string(item.block_path)), ...
                    'port_index', port_index, ...
                    'signal_key', sprintf('block:%s:%d', char(string(item.block_path)), port_index), ...
                    'probe_var_name', '', ...
                    'probe_block_path', '');
            elseif isfield(item, 'name')
                specs{end + 1, 1} = i_parse_string_spec(char(string(item.name))); %#ok<AGROW>
            end
        end
    end
end

function spec = i_parse_string_spec(text)
    spec = struct('source', 'auto', 'name', text, 'block_path', '', 'port_index', 1, 'signal_key', text, 'probe_var_name', '', 'probe_block_path', '');
    if startsWith(text, 'logsout:')
        spec.source = 'logsout';
        spec.name = extractAfter(string(text), "logsout:");
        spec.signal_key = text;
    elseif startsWith(text, 'toworkspace:')
        spec.source = 'toworkspace';
        spec.name = extractAfter(string(text), "toworkspace:");
        spec.signal_key = text;
    elseif startsWith(text, 'block:')
        rest = char(extractAfter(string(text), "block:"));
        tokens = regexp(rest, '^(.*):([0-9]+)$', 'tokens', 'once');
        if ~isempty(tokens)
            spec.source = 'block';
            spec.block_path = tokens{1};
            spec.port_index = str2double(tokens{2});
            spec.signal_key = text;
        end
    end
end

function [spec, cleanup_info, warn_msg] = i_prepare_block_probe(spec)
    cleanup_info = [];
    warn_msg = '';
    port_handles = get_param(spec.block_path, 'PortHandles');
    if ~isfield(port_handles, 'Outport') || numel(port_handles.Outport) < spec.port_index
        warn_msg = sprintf('Could not enable logging for %s: output port %d is unavailable.', spec.block_path, spec.port_index);
        return;
    end

    line_handle = get_param(port_handles.Outport(spec.port_index), 'Line');
    if isempty(line_handle) || double(line_handle) < 0
        warn_msg = sprintf('Could not enable logging for %s: output port %d is not connected.', spec.block_path, spec.port_index);
        return;
    end

    parent_system = get_param(spec.block_path, 'Parent');
    probe_block_name = sprintf('%s/slx_snapshot_probe_%d', parent_system, spec.port_index);
    probe_var_name = matlab.lang.makeValidName(sprintf('slx_snapshot_probe_%d_%d', abs(round(double(line_handle))), spec.port_index));

    probe_block_path = add_block('simulink/Sinks/To Workspace', probe_block_name, ...
        'MakeNameUnique', 'on', ...
        'VariableName', probe_var_name, ...
        'SaveFormat', 'Timeseries');
    add_line(parent_system, sprintf('%s/%d', get_param(spec.block_path, 'Name'), spec.port_index), ...
        sprintf('%s/1', get_param(probe_block_path, 'Name')), 'autorouting', 'on');

    cleanup_info = struct( ...
        'kind', 'probe_block', ...
        'block_path', char(probe_block_path), ...
        'var_name', probe_var_name);

    spec.probe_var_name = probe_var_name;
    spec.probe_block_path = char(probe_block_path);
    spec.signal_key = sprintf('block:%s:%d', spec.block_path, spec.port_index);
end

function i_cleanup_items(cleanup_items)
    for i = 1:numel(cleanup_items)
        entry = cleanup_items{i};
        try
            if strcmp(entry.kind, 'probe_block')
                if bdIsLoaded(bdroot(entry.block_path)) && ~isempty(find_system(bdroot(entry.block_path), 'SearchDepth', Inf, 'BlockType', 'ToWorkspace', 'Name', get_param(entry.block_path, 'Name')))
                    delete_block(entry.block_path);
                end
                if evalin('base', sprintf('exist(''%s'', ''var'')', entry.var_name))
                    evalin('base', sprintf('clear(''%s'')', entry.var_name));
                end
            end
        catch
        end
    end
end

function [value, unit] = i_read_spec(sim_out, spec, time_s)
    unit = '';
    switch spec.source
        case 'logsout'
            obj = i_get_logsout_signal(sim_out, char(spec.name));
            [value, unit] = i_extract_value(obj, time_s);
        case 'toworkspace'
            obj = i_get_toworkspace_signal(sim_out, char(spec.name));
            [value, unit] = i_extract_value(obj, time_s);
        case 'block'
            if isempty(spec.probe_var_name)
                error('Temporary block probe could not be enabled.');
            end
            obj = i_get_toworkspace_signal(sim_out, spec.probe_var_name);
            [value, unit] = i_extract_value(obj, time_s);
        otherwise
            try
                obj = i_get_toworkspace_signal(sim_out, char(spec.name));
                [value, unit] = i_extract_value(obj, time_s);
                return;
            catch
            end
            obj = i_get_logsout_signal(sim_out, char(spec.name));
            [value, unit] = i_extract_value(obj, time_s);
    end
end

function obj = i_get_logsout_signal(sim_out, name)
    logsout = sim_out.get('logsout');
    if isempty(logsout)
        error('logsout is empty.');
    end
    try
        names = logsout.getElementNames;
        if isstring(names)
            names = cellstr(names);
        end
        if ~any(strcmp(names, name))
            error('Signal "%s" not found in logsout.', name);
        end
    catch ME
        if ~contains(ME.message, 'not found in logsout')
            rethrow(ME);
        end
        error(ME.message);
    end
    obj = logsout.getElement(name);
    if isempty(obj)
        error('Signal "%s" not found in logsout.', name);
    end
end

function obj = i_get_toworkspace_signal(sim_out, name)
    try
        obj = sim_out.get(name);
        if ~isempty(obj)
            return;
        end
    catch
    end
    if evalin('base', sprintf('exist(''%s'', ''var'')', name))
        obj = evalin('base', name);
        return;
    end
    error('Signal "%s" not found in SimulationOutput or base workspace.', name);
end

function [value, unit] = i_extract_value(obj, time_s)
    unit = '';
    if isa(obj, 'Simulink.SimulationData.Signal')
        [value, unit] = i_extract_value(obj.Values, time_s);
        return;
    end
    if isa(obj, 'timeseries')
        ts = resample(obj, time_s);
        value = squeeze(ts.Data(end, :, :, :, :, :));
        try
            unit = char(ts.DataInfo.Units);
        catch
            unit = '';
        end
        return;
    end
    if isstruct(obj) && isfield(obj, 'time') && isfield(obj, 'signals')
        times = obj.time;
        idx = find(times <= time_s, 1, 'last');
        if isempty(idx)
            idx = 1;
        end
        values = obj.signals.values;
        if ndims(values) >= 2
            value = squeeze(values(idx, :, :, :, :, :));
        else
            value = values(idx);
        end
        return;
    end
    if isnumeric(obj) || islogical(obj)
        value = obj;
        return;
    end
    error('Unsupported logged value type: %s', class(obj));
end
