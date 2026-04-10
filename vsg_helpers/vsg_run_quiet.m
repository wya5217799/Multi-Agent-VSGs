function summary = vsg_run_quiet(code_or_file)
%VSG_RUN_QUIET Run MATLAB code or a script while returning structured output.

    t0 = tic;
    lastwarn('');
    summary = struct( ...
        'ok', true, ...
        'elapsed', 0, ...
        'n_warnings', 0, ...
        'n_errors', 0, ...
        'error_message', '', ...
        'important_lines', {{}});

    [captured_output, caught_error] = i_run_target(code_or_file);
    [warn_msg, ~] = lastwarn;

    important_lines = i_collect_important_lines(captured_output);
    if ~isempty(strtrim(warn_msg))
        important_lines{end + 1, 1} = char(warn_msg); %#ok<AGROW>
    end

    summary.elapsed = toc(t0);
    summary.important_lines = important_lines;
    summary.n_warnings = sum(startsWith(lower(string(important_lines)), "warning"));
    if ~isempty(caught_error)
        summary.ok = false;
        summary.n_errors = 1;
        summary.error_message = char(caught_error.message);
        summary.important_lines{end + 1, 1} = char(caught_error.message); %#ok<AGROW>
    end
end

function [captured_output, caught_error] = i_run_target(code_or_file)
    caught_error = [];
    captured_output = '';

    if exist(code_or_file, 'file') == 2
        escaped = strrep(code_or_file, '''', '''''');
        command = sprintf('run(''%s'');', escaped);
    else
        command = code_or_file;
    end

    try
        captured_output = evalc(command);
    catch ME
        caught_error = ME;
        if isempty(captured_output)
            captured_output = ME.message;
        end
    end
end

function important_lines = i_collect_important_lines(captured_output)
    important_lines = {};
    raw_lines = splitlines(string(captured_output));
    for i = 1:numel(raw_lines)
        line = strtrim(raw_lines(i));
        if line == ""
            continue;
        end
        line_lower = lower(line);
        if startsWith(line_lower, "warning") || startsWith(line_lower, "error") || startsWith(line_lower, "result") ...
                || contains(line_lower, "warning") || contains(line_lower, "error")
            important_lines{end + 1, 1} = char(line); %#ok<AGROW>
        end
    end
end
