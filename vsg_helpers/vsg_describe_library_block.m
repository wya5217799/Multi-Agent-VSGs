function result = vsg_describe_library_block(library_path)
%VSG_DESCRIBE_LIBRARY_BLOCK Describe a library block using its exact path.

    result = struct( ...
        'exists', false, ...
        'dialog_params', {{}}, ...
        'default_values', struct(), ...
        'port_schema', {{}}, ...
        'mask_type', '', ...
        'reference_block', '', ...
        'error', '');

    try
        load_system(bdroot(char(library_path)));
        get_param(char(library_path), 'Handle');
        [defaults, param_names] = i_dialog_defaults(char(library_path));
        result.exists = true;
        result.dialog_params = param_names;
        result.default_values = defaults;
        result.port_schema = i_port_schema(char(library_path));
        result.mask_type = char(string(get_param(char(library_path), 'MaskType')));
        result.reference_block = char(string(get_param(char(library_path), 'ReferenceBlock')));
    catch ME
        result.error = char(ME.message);
    end
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

function schema = i_port_schema(block_path)
    schema = {};
    try
        ph = get_param(block_path, 'PortHandles');
        fields = fieldnames(ph);
        for i = 1:numel(fields)
            kind = fields{i};
            handles = ph.(kind);
            for j = 1:numel(handles)
                schema{end + 1, 1} = struct( ... %#ok<AGROW>
                    'name', sprintf('%s%d', kind, j), ...
                    'label', '', ...
                    'domain', '', ...
                    'port_type', kind);
            end
        end
    catch
    end
end
