function result = vsg_solver_warning_summary(model_name, run_code_or_file, timeout_sec, warning_patterns, collapse_duplicates)
%VSG_SOLVER_WARNING_SUMMARY  Collapse solver/stiffness warnings from captured output.

    if nargin < 3 || isempty(timeout_sec), timeout_sec = 60; end %#ok<NASGU>
    if nargin < 4 || isempty(warning_patterns)
        warning_patterns = {
            'warning', 'minimum step', 'min step', 'step size', ...
            'solver', 'stiff', 'algebraic', 'consecutive minimum'
        };
    end
    if nargin < 5 || isempty(collapse_duplicates), collapse_duplicates = true; end

    load_system(char(model_name));

    result = struct( ...
        'ok', true, ...
        'first_occurrence_time', [], ...
        'last_occurrence_time', [], ...
        'unique_warning_types', 0, ...
        'collapsed_warnings', {{}}, ...
        'stiffness_detected', false, ...
        'likely_stuck_time', [], ...
        'suggested_next_checks', {{}}, ...
        'raw_summary', '', ...
        'error_message', '');

    lastwarn('');
    [captured_output, caught_error] = i_run_target(char(run_code_or_file));
    [warn_msg, ~] = lastwarn;

    warning_lines = i_collect_warning_lines(captured_output, warning_patterns);
    if ~isempty(strtrim(warn_msg))
        warning_lines{end + 1, 1} = char(warn_msg); %#ok<AGROW>
    end

    collapsed = i_collapse_warnings(warning_lines, logical(collapse_duplicates));
    [first_time, last_time, likely_stuck_time] = i_time_summary(collapsed);
    stiffness_detected = i_detect_stiffness(collapsed);

    result.collapsed_warnings = collapsed;
    result.unique_warning_types = numel(collapsed);
    result.first_occurrence_time = first_time;
    result.last_occurrence_time = last_time;
    result.likely_stuck_time = likely_stuck_time;
    result.stiffness_detected = stiffness_detected;
    result.raw_summary = strtrim(char(captured_output));
    result.suggested_next_checks = i_suggest_next_checks(stiffness_detected, likely_stuck_time, collapsed);

    if ~isempty(caught_error)
        result.ok = false;
        result.error_message = char(caught_error.message);
        raw_parts = {result.raw_summary, char(caught_error.message)};
        result.raw_summary = strjoin(raw_parts(~cellfun(@isempty, raw_parts)), newline);
    end
end

function [captured_output, caught_error] = i_run_target(run_code_or_file)
    caught_error = [];
    captured_output = '';

    if exist(run_code_or_file, 'file') == 2
        escaped = strrep(run_code_or_file, '''', '''''');
        command = sprintf('run(''%s'');', escaped);
    else
        command = run_code_or_file;
    end

    try
        captured_output = evalc(command);
    catch ME
        caught_error = ME;
    end
end

function lines = i_collect_warning_lines(captured_output, warning_patterns)
    lines = {};
    raw_lines = splitlines(string(captured_output));
    normalized_patterns = lower(string(warning_patterns));

    for i = 1:numel(raw_lines)
        line = strtrim(raw_lines(i));
        if line == ""
            continue;
        end
        line_lower = lower(line);
        if startsWith(line_lower, "warning") || any(contains(line_lower, normalized_patterns))
            lines{end + 1, 1} = char(line); %#ok<AGROW>
        end
    end
end

function collapsed = i_collapse_warnings(lines, collapse_duplicates)
    collapsed = {};
    if isempty(lines)
        return;
    end

    if ~collapse_duplicates
        for i = 1:numel(lines)
            line = char(lines{i});
            line_time = i_extract_time(line);
            collapsed{end + 1, 1} = struct( ... %#ok<AGROW>
                'signature', line, ...
                'count', 1, ...
                'first_time', line_time, ...
                'last_time', line_time, ...
                'example', line, ...
                'min_step', i_extract_min_step(line));
        end
        return;
    end

    groups = containers.Map('KeyType', 'char', 'ValueType', 'any');
    order = {};
    for i = 1:numel(lines)
        line = char(lines{i});
        signature = i_signature(line);
        line_time = i_extract_time(line);
        min_step = i_extract_min_step(line);
        if ~isKey(groups, signature)
            groups(signature) = struct( ...
                'signature', signature, ...
                'count', 1, ...
                'first_time', line_time, ...
                'last_time', line_time, ...
                'example', line, ...
                'min_step', min_step);
            order{end + 1, 1} = signature; %#ok<AGROW>
        else
            entry = groups(signature);
            entry.count = entry.count + 1;
            if isempty(entry.first_time) && ~isempty(line_time)
                entry.first_time = line_time;
            end
            if ~isempty(line_time)
                entry.last_time = line_time;
            end
            if isempty(entry.min_step) || (~isempty(min_step) && min_step < entry.min_step)
                entry.min_step = min_step;
            end
            groups(signature) = entry;
        end
    end

    for i = 1:numel(order)
        collapsed{end + 1, 1} = groups(order{i}); %#ok<AGROW>
    end
end

function signature = i_signature(line)
    signature = lower(char(line));
    signature = regexprep(signature, '[0-9]+(?:\.[0-9]+)?(?:e[+\-]?[0-9]+)?', '<num>');
end

function line_time = i_extract_time(line)
    line_time = [];
    tokens = regexp(char(line), '(?:t|time)\s*=?\s*([0-9]+(?:\.[0-9]+)?(?:[eE][+\-]?[0-9]+)?)', 'tokens', 'once');
    if isempty(tokens)
        return;
    end
    value = str2double(tokens{1});
    if ~isnan(value)
        line_time = value;
    end
end

function min_step = i_extract_min_step(line)
    min_step = [];
    tokens = regexp(char(line), 'min(?:imum)?\s+step(?:\s+size)?\s*(?:=|is)?\s*([0-9]+(?:\.[0-9]+)?(?:[eE][+\-]?[0-9]+)?)', 'tokens', 'once');
    if isempty(tokens)
        return;
    end
    value = str2double(tokens{1});
    if ~isnan(value)
        min_step = value;
    end
end

function [first_time, last_time, likely_stuck_time] = i_time_summary(collapsed)
    first_time = [];
    last_time = [];
    likely_stuck_time = [];
    time_values = [];
    repeated_times = [];

    for i = 1:numel(collapsed)
        item = collapsed{i};
        if ~isempty(item.first_time)
            time_values(end + 1, 1) = item.first_time; %#ok<AGROW>
        end
        if ~isempty(item.last_time)
            time_values(end + 1, 1) = item.last_time; %#ok<AGROW>
        end
        if item.count > 1 && ~isempty(item.first_time) && ~isempty(item.last_time) && abs(item.first_time - item.last_time) < 1e-12
            repeated_times(end + 1, 1) = item.first_time; %#ok<AGROW>
        end
    end

    if ~isempty(time_values)
        first_time = min(time_values);
        last_time = max(time_values);
    end
    if ~isempty(repeated_times)
        likely_stuck_time = repeated_times(1);
    elseif ~isempty(last_time)
        likely_stuck_time = last_time;
    end
end

function tf = i_detect_stiffness(collapsed)
    tf = false;
    patterns = {'minimum step', 'min step', 'step size', 'stiff', 'algebraic', 'solver'};
    for i = 1:numel(collapsed)
        text = lower(char(collapsed{i}.example));
        if any(cellfun(@(pattern) contains(text, pattern), patterns))
            tf = true;
            return;
        end
    end
end

function suggestions = i_suggest_next_checks(stiffness_detected, likely_stuck_time, collapsed)
    suggestions = {};
    if isempty(collapsed)
        suggestions{end + 1, 1} = 'No matching warnings were captured; re-run with broader warning patterns or a shorter diagnostic window.'; %#ok<AGROW>
        return;
    end

    if stiffness_detected
        suggestions{end + 1, 1} = 'Audit discontinuous event sources near the stuck time.'; %#ok<AGROW>
        suggestions{end + 1, 1} = 'Review solver diagnostics and Simscape solver configuration for minimum-step or stiffness limits.'; %#ok<AGROW>
    end
    if ~isempty(likely_stuck_time)
        suggestions{end + 1, 1} = sprintf('Run simulink_step_diagnostics around t=%.6g s to confirm whether progress stops there.', likely_stuck_time); %#ok<AGROW>
    end
    suggestions{end + 1, 1} = 'If warnings cluster around one event, inspect breaker/step sample times and warmup boundaries.'; %#ok<AGROW>
end
