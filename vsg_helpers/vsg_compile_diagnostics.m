function result = vsg_compile_diagnostics(model_name, mode)
%VSG_COMPILE_DIAGNOSTICS Run update/compile and return structured diagnostics.

    if nargin < 2 || isempty(mode), mode = 'update'; end
    load_system(char(model_name));

    result = struct( ...
        'ok', true, ...
        'mode', char(mode), ...
        'errors', {{}}, ...
        'warnings', {{}}, ...
        'raw_summary', '');

    try
        command = sprintf('set_param(''%s'', ''SimulationCommand'', ''Update'');', char(model_name));
        if strcmpi(char(mode), 'compile')
            command = sprintf('Simulink.BlockDiagram.compile(''%s''); Simulink.BlockDiagram.terminateCompilation(''%s'');', char(model_name), char(model_name));
        end
        captured_output = evalc(command);
        result.raw_summary = strtrim(char(captured_output));
        result.warnings = i_collect_messages(captured_output, 'warning', char(mode));
    catch ME
        result.ok = false;
        result.raw_summary = char(ME.message);
        result.errors = {struct( ...
            'block_path', '', ...
            'param_name', '', ...
            'message', char(ME.message), ...
            'severity', 'error', ...
            'phase', char(mode))};
    end
end

function messages = i_collect_messages(captured_output, severity, phase)
    messages = {};
    raw_lines = splitlines(string(captured_output));
    for i = 1:numel(raw_lines)
        line = strtrim(raw_lines(i));
        if line == ""
            continue;
        end
        if contains(lower(line), severity)
            messages{end + 1, 1} = struct( ... %#ok<AGROW>
                'block_path', '', ...
                'param_name', '', ...
                'message', char(line), ...
                'severity', severity, ...
                'phase', phase);
        end
    end
end
