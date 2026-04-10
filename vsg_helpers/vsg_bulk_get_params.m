function result = vsg_bulk_get_params(model_name, block_paths, param_names)
%VSG_BULK_GET_PARAMS Read selected parameters from many blocks in one call.

    if nargin < 3 || isempty(param_names)
        result = struct('items', {{}});
        return;
    end

    load_system(char(model_name));

    n = numel(block_paths);
    items = cell(n, 1);
    for i = 1:n
        blk = char(block_paths{i});
        item = struct('block_path', blk, 'params', struct(), 'missing_params', {{}}, 'error', '');
        try
            for j = 1:numel(param_names)
                pname = char(param_names{j});
                try
                    value = get_param(blk, pname);
                    item.params.(pname) = i_to_string(value);
                catch
                    item.missing_params{end + 1, 1} = pname; %#ok<AGROW>
                end
            end
        catch ME
            item.error = char(ME.message);
        end
        items{i} = item;
    end

    result = struct('items', {items});
end

function value = i_to_string(raw)
    if ischar(raw) || isstring(raw)
        value = char(raw);
    elseif isnumeric(raw) && isscalar(raw)
        value = num2str(raw);
    else
        value = mat2str(raw);
    end
end
