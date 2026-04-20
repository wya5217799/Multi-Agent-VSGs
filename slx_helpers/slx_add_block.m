function summary = slx_add_block(source_block, destination_block, params, make_name_unique)
%SLX_ADD_BLOCK Add a block from a library and optionally set dialog params.

    if nargin < 3 || isempty(params), params = struct(); end
    if nargin < 4, make_name_unique = true; end

    summary = struct( ...
        'ok', false, ...
        'block_path', char(destination_block), ...
        'important_lines', {{}}, ...
        'error_message', '');

    try
        if logical(make_name_unique)
            actual_path = add_block(char(source_block), char(destination_block), 'MakeNameUnique', 'on');
        else
            actual_path = add_block(char(source_block), char(destination_block), 'MakeNameUnique', 'off');
        end
        if isnumeric(actual_path)
            actual_path = getfullname(actual_path);
        elseif isstring(actual_path)
            actual_path = char(actual_path);
        end
        if isstruct(params)
            fields = fieldnames(params);
            for i = 1:numel(fields)
                set_param(actual_path, fields{i}, char(string(params.(fields{i}))));
            end
        end
        summary.ok = true;
        summary.block_path = char(actual_path);
        summary.important_lines = {sprintf('Added block %s', char(actual_path))};
    catch ME
        summary.error_message = char(ME.message);
    end
end
