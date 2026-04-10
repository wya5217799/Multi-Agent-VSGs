function result = vsg_preflight(lib_name, block_display_name)
%VSG_PREFLIGHT Query a library block by display name before placement.

    load_system(char(lib_name));
    matches = i_find_matches(char(lib_name), char(block_display_name));

    if isempty(matches)
        result = struct( ...
            'found', false, ...
            'handle', 0, ...
            'params_main', {{}}, ...
            'params_unit', {{}}, ...
            'defaults', struct(), ...
            'ports', {{}}, ...
            'error', sprintf('Block "%s" not found in %s', char(block_display_name), char(lib_name)));
        return;
    end

    block_path = matches{1};
    [defaults, param_names] = i_dialog_defaults(block_path);
    ports = i_ports(block_path);
    result = struct( ...
        'found', true, ...
        'handle', double(get_param(block_path, 'Handle')), ...
        'params_main', {param_names}, ...
        'params_unit', {{}}, ...
        'defaults', defaults, ...
        'ports', {ports}, ...
        'error', '');
end

function matches = i_find_matches(lib_name, block_display_name)
    matches = i_find_by_name(lib_name, block_display_name);
    if ~isempty(matches)
        return;
    end

    all_blocks = i_find_all_blocks(lib_name);
    target = i_normalize_label(block_display_name);
    matches = {};

    for i = 1:numel(all_blocks)
        block_path = all_blocks{i};
        labels = {
            i_safe_get(block_path, 'Name'), ...
            i_safe_get(block_path, 'MaskType')
        };
        if any(cellfun(@(label) strcmp(i_normalize_label(label), target), labels))
            matches{end + 1, 1} = block_path; %#ok<AGROW>
        end
    end
end

function matches = i_find_by_name(lib_name, block_display_name)
    try
        matches = find_system(lib_name, ...
            'LookUnderMasks', 'all', ...
            'FollowLinks', 'on', ...
            'MatchFilter', @Simulink.match.allVariants, ...
            'Name', block_display_name);
    catch
        matches = find_system(lib_name, ...
            'LookUnderMasks', 'all', ...
            'FollowLinks', 'on', ...
            'Name', block_display_name);
    end
end

function all_blocks = i_find_all_blocks(lib_name)
    try
        all_blocks = find_system(lib_name, ...
            'LookUnderMasks', 'all', ...
            'FollowLinks', 'on', ...
            'MatchFilter', @Simulink.match.allVariants, ...
            'Type', 'block');
    catch
        all_blocks = find_system(lib_name, ...
            'LookUnderMasks', 'all', ...
            'FollowLinks', 'on', ...
            'Type', 'block');
    end
end

function value = i_safe_get(block_path, param_name)
    try
        value = char(string(get_param(block_path, param_name)));
    catch
        value = '';
    end
end

function value = i_normalize_label(raw)
    value = regexprep(char(string(raw)), '\s+', ' ');
    value = strtrim(value);
end

function [defaults, param_names] = i_dialog_defaults(block_path)
    defaults = struct();
    param_names = {};
    try
        dp = get_param(block_path, 'DialogParameters');
        param_names = fieldnames(dp);
        for i = 1:numel(param_names)
            pname = param_names{i};
            try
                defaults.(pname) = char(string(get_param(block_path, pname)));
            catch
                defaults.(pname) = '';
            end
        end
    catch
    end
end

function ports = i_ports(block_path)
    ports = {};
    try
        ph = get_param(block_path, 'PortHandles');
        fields = fieldnames(ph);
        for i = 1:numel(fields)
            kind = fields{i};
            handles = ph.(kind);
            for j = 1:numel(handles)
                ports{end + 1, 1} = struct( ... %#ok<AGROW>
                    'name', sprintf('%s%d', kind, j), ...
                    'label', '', ...
                    'domain', '', ...
                    'port_type', kind);
            end
        end
    catch
    end
end
