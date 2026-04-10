function result = vsg_step_diagnostics(model_name, start_time, stop_time, varargin)
%VSG_STEP_DIAGNOSTICS Run a short simulation window and summarize warnings/errors.

    options = i_parse_options(varargin{:});
    load_system(char(model_name));
    set_param(char(model_name), 'SimulationMode', char(options.simulation_mode));

    result = struct( ...
        'ok', true, ...
        'status', 'success', ...
        'elapsed_sec', 0, ...
        'sim_time_reached', double(stop_time), ...
        'warning_count', 0, ...
        'error_count', 0, ...
        'top_warnings', {{}}, ...
        'top_errors', {{}}, ...
        'timed_out_in', '', ...
        'raw_summary', '');

    t0 = tic;
    try
        sim_out = evalc(sprintf('sim(''%s'', ''StartTime'', ''%s'', ''StopTime'', ''%s'');', ...
            char(model_name), num2str(start_time), num2str(stop_time)));
        result.raw_summary = strtrim(char(sim_out));
        warnings = i_collect_lines(sim_out, 'warning', options.max_warning_lines);
        result.warning_count = numel(warnings);
        result.top_warnings = warnings;
    catch ME
        result.ok = false;
        result.status = 'sim_error';
        result.error_count = 1;
        result.top_errors = {struct('signature', 'sim_error', 'count', 1, 'example', char(ME.message), 'time', [])};
        result.raw_summary = char(ME.message);
    end
    result.elapsed_sec = toc(t0);
end

function options = i_parse_options(varargin)
    options = struct('timeout_sec', 120, 'simulation_mode', 'normal', 'capture_warnings', true, 'max_warning_lines', 20);
    for i = 1:2:numel(varargin)
        key = char(varargin{i});
        if i + 1 > numel(varargin)
            continue;
        end
        options.(key) = varargin{i + 1};
    end
end

function groups = i_collect_lines(captured_output, severity, max_items)
    groups = {};
    raw_lines = splitlines(string(captured_output));
    current_warning = "";
    for i = 1:numel(raw_lines)
        line = i_normalize_line(raw_lines(i));
        if line == ""
            continue;
        end

        if i_is_warning_start(line, severity)
            if current_warning ~= ""
                groups = i_append_group(groups, current_warning, max_items);
                if numel(groups) >= double(max_items)
                    return;
                end
            end
            current_warning = line;
            continue;
        end

        if current_warning == ""
            continue;
        end

        if i_is_warning_metadata(line)
            groups = i_append_group(groups, current_warning, max_items);
            if numel(groups) >= double(max_items)
                return;
            end
            current_warning = "";
            continue;
        end

        current_warning = strtrim(current_warning + " " + line);
    end

    if current_warning ~= "" && numel(groups) < double(max_items)
        groups = i_append_group(groups, current_warning, max_items);
    end
end

function line = i_normalize_line(raw_line)
    line = strtrim(string(raw_line));
    line = erase(line, sprintf('\b'));
    line = regexprep(line, '\s+', ' ');
    line = strtrim(line);
end

function tf = i_is_warning_start(line, severity)
    line_lower = lower(line);
    tf = contains(line_lower, severity) || contains(line, "警告");
end

function tf = i_is_warning_metadata(line)
    tf = startsWith(line, ">") || contains(line, "位置：") || contains(lower(line), "line ") || contains(lower(line), "location:");
end

function groups = i_append_group(groups, warning_text, max_items)
    if numel(groups) >= double(max_items)
        return;
    end
    groups{end + 1, 1} = struct( ... %#ok<AGROW>
        'signature', char(warning_text), ...
        'count', 1, ...
        'example', char(warning_text), ...
        'time', []);
end
