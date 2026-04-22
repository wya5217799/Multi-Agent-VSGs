function result = slx_workspace_set(vars)
%SLX_WORKSPACE_SET Set MATLAB base-workspace variables from a scalar struct.

    result = struct( ...
        'ok', true, ...
        'vars_written', {{}}, ...
        'errors', {{}}, ...
        'error_message', '');

    try
        fields = fieldnames(vars);
        for i = 1:numel(fields)
            name = fields{i};
            assignin('base', name, vars.(name));
            result.vars_written{end + 1, 1} = name; %#ok<AGROW>
        end
    catch ME
        result.ok = false;
        result.error_message = char(ME.message);
        result.errors{end + 1, 1} = char(ME.message);
    end
end
